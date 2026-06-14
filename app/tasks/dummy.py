import time
import logging
import json
import redis
from celery.utils.log import get_task_logger
from app.core.celery_app import celery
from app.core.database import get_sync_db
from app.core.config import settings
from app.models.job import Job, JobStatus
from app.models.job_log import JobLog, LogLevel

logger = get_task_logger(__name__)

def log_to_db(session, job_id, level, message):
    log_entry = JobLog(job_id=job_id, level=level, message=message)
    session.add(log_entry)
    session.commit()
    logger.info(f"[{level}] Job {job_id}: {message}")

def publish_status_update(redis_client, job_id, status, progress, tenant_id):
    payload = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "tenant_id": str(tenant_id)
    }
    redis_client.publish("job_status_updates", json.dumps(payload))

@celery.task(bind=True, name="app.tasks.dummy.sleep_task")
def sleep_task(self, job_id: str, duration: int = 10):
    redis_client = redis.Redis.from_url(settings.REDIS_URI)
    cancel_key = f"cancel:{job_id}"

    with get_sync_db() as session:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found in database.")
            return

        try:
            # Check if already cancelled before starting
            if redis_client.exists(cancel_key):
                job.status = JobStatus.CANCELLED
                session.commit()
                log_to_db(session, job.id, LogLevel.INFO, "Task cancelled before starting.")
                publish_status_update(redis_client, job_id, JobStatus.CANCELLED, 0, job.tenant_id)
                redis_client.delete(cancel_key)
                return

            # Start execution
            job.status = JobStatus.RUNNING
            session.commit()
            log_to_db(session, job.id, LogLevel.INFO, "Task started.")
            publish_status_update(redis_client, job_id, JobStatus.RUNNING, 0, job.tenant_id)

            # Cooperative sleep loop
            for i in range(duration):
                time.sleep(1)
                
                progress_percentage = int(((i + 1) / duration) * 100)
                self.update_state(state="RUNNING", meta={"progress": progress_percentage})
                publish_status_update(redis_client, job_id, JobStatus.RUNNING, progress_percentage, job.tenant_id)

                # Check for cooperative cancellation
                if redis_client.exists(cancel_key):
                    # We don't overwrite if it's already CANCELLED, but ensure database state is aligned
                    if job.status != JobStatus.CANCELLED:
                        job.status = JobStatus.CANCELLED
                        session.commit()
                    log_to_db(session, job.id, LogLevel.INFO, "Task cancelled cooperatively during execution.")
                    publish_status_update(redis_client, job_id, JobStatus.CANCELLED, progress_percentage, job.tenant_id)
                    redis_client.delete(cancel_key)
                    return

            # Complete task
            job.status = JobStatus.DONE
            job.result = {"result": "success", "duration_seconds": duration}
            session.commit()
            log_to_db(session, job.id, LogLevel.INFO, "Task completed successfully.")
            publish_status_update(redis_client, job_id, JobStatus.DONE, 100, job.tenant_id)

        except Exception as e:
            session.refresh(job)
            if job.status == JobStatus.CANCELLED:
                log_to_db(session, job.id, LogLevel.INFO, "Task cancellation finalized after exception.")
                return
            
            job.status = JobStatus.FAILED
            job.result = {"error": str(e)}
            session.commit()
            log_to_db(session, job.id, LogLevel.ERROR, f"Task failed with error: {str(e)}")
            publish_status_update(redis_client, job_id, JobStatus.FAILED, 0, job.tenant_id)
