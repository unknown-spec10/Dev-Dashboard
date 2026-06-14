# A registry mapping user-facing job names to Celery task paths
TASK_REGISTRY = {
    "sleep_task": "app.tasks.dummy.sleep_task",
    "repo_ingestion": "app.tasks.ingest.repo_ingestion_task",
    "embedding_pipeline": "app.tasks.embed.embedding_pipeline_task"
}
