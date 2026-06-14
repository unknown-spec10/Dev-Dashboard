import time
import logging
import json
import redis
from celery.utils.log import get_task_logger
from app.core.celery_app import celery
from app.core.database import get_sync_db
from app.core.config import settings
from app.models.job import Job, JobStatus

logger = get_task_logger(__name__)

def publish_status_update(redis_client, job_id, status, progress, tenant_id):
    payload = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "tenant_id": str(tenant_id)
    }
    redis_client.publish("job_status_updates", json.dumps(payload))

@celery.task(bind=True, name="app.tasks.ingest.repo_ingestion_task")
def repo_ingestion_task(self, job_id: str, repo_url: str):
    redis_client = redis.Redis.from_url(settings.REDIS_URI)
    cancel_key = f"cancel:{job_id}"
    
    mock_files = [
        "README.md",
        "package.json",
        "src/main.jsx",
        "src/App.jsx",
        "vite.config.js"
    ]
    
    with get_sync_db() as session:
        job = session.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found in database.")
            return

        try:
            # Check cancellation before starting
            if redis_client.exists(cancel_key):
                job.status = JobStatus.CANCELLED
                session.commit()
                publish_status_update(redis_client, job_id, JobStatus.CANCELLED, 0, job.tenant_id)
                logger.info("Ingestion cancelled before starting.")
                redis_client.delete(cancel_key)
                return

            # Start Ingestion
            job.status = JobStatus.RUNNING
            session.commit()
            publish_status_update(redis_client, job_id, JobStatus.RUNNING, 0, job.tenant_id)
            logger.info(f"Cloning repository: {repo_url}...")
            time.sleep(1)

            for i, file_path in enumerate(mock_files):
                # Cooperative cancellation check
                if redis_client.exists(cancel_key):
                    job.status = JobStatus.CANCELLED
                    session.commit()
                    publish_status_update(
                        redis_client, 
                        job_id, 
                        JobStatus.CANCELLED, 
                        int((i / len(mock_files)) * 100), 
                        job.tenant_id
                    )
                    logger.info("Ingestion cancelled cooperatively mid-process.")
                    redis_client.delete(cancel_key)
                    return
                
                logger.info(f"Analyzing file structure: {file_path}")
                time.sleep(1.2) # Simulate processing time
                
                # Update progress
                progress_percentage = int(((i + 1) / len(mock_files)) * 100)
                self.update_state(state="RUNNING", meta={"progress": progress_percentage})
                publish_status_update(redis_client, job_id, JobStatus.RUNNING, progress_percentage, job.tenant_id)

            # Ingestion Complete
            job.status = JobStatus.DONE
            job.result = {
                "status": "success",
                "repo_url": repo_url,
                "files_count": len(mock_files),
                "files": mock_files
            }
            session.commit()
            publish_status_update(redis_client, job_id, JobStatus.DONE, 100, job.tenant_id)
            logger.info("Ingestion completed successfully.")

        except Exception as e:
            session.refresh(job)
            if job.status == JobStatus.CANCELLED:
                logger.info("Ingestion cancellation finalized after exception.")
                return
            
            job.status = JobStatus.FAILED
            job.result = {"error": str(e)}
            session.commit()
            publish_status_update(redis_client, job_id, JobStatus.FAILED, 0, job.tenant_id)
            logger.error(f"Ingestion failed: {str(e)}")
