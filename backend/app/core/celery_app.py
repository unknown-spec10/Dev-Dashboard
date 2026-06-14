import logging
from celery import Celery
from celery.signals import after_setup_task_logger
from kombu import Queue
from app.core.config import settings

celery = Celery(
    "dev_dashboard",
    broker=settings.REDIS_URI,
    backend=settings.REDIS_URI
)

# Celery Configurations
celery.conf.update(
    task_track_started=True,
    result_extended=True,
    timezone="UTC",
    enable_utc=True,
)

# 1. Define Priority Queues (high, default, low)
celery.conf.task_queues = (
    Queue("high", routing_key="high"),
    Queue("celery", routing_key="default"), # Default queue
    Queue("low", routing_key="low"),
)
celery.conf.task_default_queue = "celery"
celery.conf.task_default_exchange = "celery"
celery.conf.task_default_routing_key = "default"

# 2. Celery Beat Schedule
celery.conf.beat_schedule = {
    "system-heartbeat-every-30s": {
        "task": "app.core.celery_app.heartbeat_task",
        "schedule": 30.0,
    }
}

# Define the recurring heartbeat task
@celery.task(name="app.core.celery_app.heartbeat_task")
def heartbeat_task():
    logger = logging.getLogger(__name__)
    # Logs only to stdout (logger) to prevent PostgreSQL table clutter
    logger.info("System Health Check: Celery Beat heartbeat processed. Worker is active.")

# 3. Logging Interceptor (after_setup_task_logger signal)
@after_setup_task_logger.connect
def setup_task_logger(logger, *args, **kwargs):
    from app.core.logging_handler import RedisPubSubLogHandler
    
    # Avoid duplicate registrations
    for h in logger.handlers:
        if h.__class__.__name__ == "RedisPubSubLogHandler":
            return
            
    handler = RedisPubSubLogHandler()
    # Format to keep just the raw log message for console websocket pushing
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Autodiscover task modules under app
celery.autodiscover_tasks(["app"])
