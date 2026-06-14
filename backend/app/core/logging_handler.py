import json
import logging
from datetime import datetime, timezone
import redis
from celery import current_task
from app.core.config import settings
from app.core.database import get_sync_db
from app.models.job_log import JobLog

class RedisPubSubLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis_client = redis.Redis.from_url(settings.REDIS_URI)

    def emit(self, record):
        try:
            # Capture only when executing within an active Celery task context
            if not current_task or not current_task.request or not current_task.request.id:
                return
            
            job_id = current_task.request.id
            message_text = self.format(record)
            
            level_name = record.levelname
            if level_name == "WARN":
                level_name = "WARNING"
            elif level_name in ["CRITICAL", "FATAL"]:
                level_name = "ERROR"
            elif level_name not in ["INFO", "WARNING", "ERROR"]:
                level_name = "INFO"

            now = datetime.now(timezone.utc)
            
            # 1. Write log line to PostgreSQL using pooled database session
            log_entry = JobLog(
                job_id=job_id,
                level=level_name,
                message=message_text,
                created_at=now
            )
            with get_sync_db() as session:
                session.add(log_entry)
            
            # 2. Publish to Redis Pub/Sub for WebSocket clients
            channel = f"job_logs:{job_id}"
            payload = {
                "id": str(log_entry.id),
                "job_id": job_id,
                "level": level_name,
                "message": message_text,
                "created_at": now.isoformat()
            }
            self.redis_client.publish(channel, json.dumps(payload))
            
        except Exception:
            # Prevent logging errors from crashing the task execution
            self.handleError(record)
