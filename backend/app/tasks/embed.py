import time
import logging
import json
import random
import redis
from celery.utils.log import get_task_logger
from app.core.celery_app import celery
from app.core.database import get_sync_db
from app.core.config import settings
from app.models.job import Job, JobStatus
from app.models.document import DocumentEmbedding

logger = get_task_logger(__name__)

def publish_status_update(redis_client, job_id, status, progress, tenant_id):
    payload = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "tenant_id": str(tenant_id)
    }
    redis_client.publish("job_status_updates", json.dumps(payload))

@celery.task(bind=True, name="app.tasks.embed.embedding_pipeline_task")
def embedding_pipeline_task(self, job_id: str, text: str):
    redis_client = redis.Redis.from_url(settings.REDIS_URI)
    cancel_key = f"cancel:{job_id}"
    
    # Split text into paragraphs (double newline separator)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = ["Default dummy content paragraph for embedding."]
        
    total_chunks = len(paragraphs)
    
    with get_sync_db() as session:
        job = session.query(Job).filter(Job.id == job_id).first()
        
        # Guard: Raise a loud ValueError if the job record is missing
        if job is None:
            raise ValueError(f"Job {job_id} not found in database — cannot tag embeddings.")

        try:
            # Check cancellation before starting
            if redis_client.exists(cancel_key):
                job.status = JobStatus.CANCELLED
                session.commit()
                publish_status_update(redis_client, job_id, JobStatus.CANCELLED, 0, job.tenant_id)
                logger.info("Embedding cancelled before starting.")
                redis_client.delete(cancel_key)
                return

            # Start Embedding
            job.status = JobStatus.RUNNING
            session.commit()
            publish_status_update(redis_client, job_id, JobStatus.RUNNING, 0, job.tenant_id)
            logger.info(f"Splitting input text into {total_chunks} chunk(s) for vector generation...")
            time.sleep(1)

            for i, paragraph in enumerate(paragraphs):
                # Cooperative cancellation check
                if redis_client.exists(cancel_key):
                    job.status = JobStatus.CANCELLED
                    session.commit()
                    publish_status_update(
                        redis_client, 
                        job_id, 
                        JobStatus.CANCELLED, 
                        int((i / total_chunks) * 100), 
                        job.tenant_id
                    )
                    logger.info("Embedding cancelled cooperatively mid-process.")
                    redis_client.delete(cancel_key)
                    return
                
                logger.info(f"Generating 1536-dimensional vector for chunk {i + 1}/{total_chunks}...")
                time.sleep(1.5) # Simulate API latency
                
                # Generate random 1536-d float array representation
                dummy_vector = [random.uniform(-1.0, 1.0) for _ in range(1536)]
                
                # Save to pgvector document_embeddings table
                doc = DocumentEmbedding(
                    job_id=job.id,
                    tenant_id=job.tenant_id,  # Tag embedding with tenant_id for isolation
                    content=paragraph,
                    embedding=dummy_vector
                )
                session.add(doc)
                session.commit() # Save chunk immediately to DB
                
                # Update progress
                progress_percentage = int(((i + 1) / total_chunks) * 100)
                self.update_state(state="RUNNING", meta={"progress": progress_percentage})
                publish_status_update(redis_client, job_id, JobStatus.RUNNING, progress_percentage, job.tenant_id)
                logger.info(f"Successfully upserted vector embedding for chunk {i + 1} to database.")

            # Complete
            job.status = JobStatus.DONE
            job.result = {
                "status": "success",
                "chunks_processed": total_chunks,
                "vector_dimensions": 1536
            }
            session.commit()
            publish_status_update(redis_client, job_id, JobStatus.DONE, 100, job.tenant_id)
            logger.info("Text embedding pipeline finished successfully.")

        except Exception as e:
            session.refresh(job)
            if job.status == JobStatus.CANCELLED:
                logger.info("Embedding cancellation finalized after exception.")
                return
            
            job.status = JobStatus.FAILED
            job.result = {"error": str(e)}
            session.commit()
            publish_status_update(redis_client, job_id, JobStatus.FAILED, 0, job.tenant_id)
            logger.error(f"Embedding pipeline failed: {str(e)}")
