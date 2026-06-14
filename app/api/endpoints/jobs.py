import asyncio
import json
import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import redis
import redis.asyncio

from app.core.database import get_async_db, async_session_maker
from app.core.celery_app import celery
from app.core.config import settings
from app.models.job import Job, JobStatus
from app.models.api_key import ApiKey
from app.models.tenant import Tenant
from app.tasks.registry import TASK_REGISTRY
from app.schemas.job import JobCreate, JobOut, JobDetailOut
from app.api.dependencies import get_tenant_context, TenantContext, verify_ws_token, check_scopes

router = APIRouter()
logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000000'

def get_job_progress(job_id: str, job_status: str) -> int:
    if job_status == JobStatus.DONE:
        return 100
    if job_status in [JobStatus.FAILED, JobStatus.CANCELLED]:
        return 0
    try:
        res = celery.AsyncResult(job_id)
        if res.state == "RUNNING" and res.info:
            return res.info.get("progress", 0)
    except Exception:
        pass
    return 0

@router.post("/", response_model=JobOut)
async def create_job(
    job_in: JobCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    if job_in.name not in TASK_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Task '{job_in.name}' is not registered.")
    
    priority = job_in.priority or "default"
    if priority not in ["high", "default", "low"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid priority. Use 'high', 'default', or 'low'."
        )

    # 1. Enforce API Key Scopes
    check_scopes(ctx.scopes, job_in.name, priority)

    # 2. Determine Tenant ID
    if ctx.is_admin:
        # Global admin can assign to any tenant or defaults to 'default' tenant
        if job_in.tenant_id:
            tenant_res = await db.execute(select(Tenant).filter(Tenant.id == job_in.tenant_id))
            tenant = tenant_res.scalar_one_or_none()
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Requested tenant '{job_in.tenant_id}' does not exist."
                )
            target_tenant_id = job_in.tenant_id
        else:
            target_tenant_id = UUID(DEFAULT_TENANT_ID)
    else:
        # Tenant key is locked to their own tenant context
        target_tenant_id = ctx.tenant_id

    # 3. Save job to PostgreSQL
    db_job = Job(
        name=job_in.name,
        payload=job_in.payload,
        status=JobStatus.PENDING,
        priority=priority,
        tenant_id=target_tenant_id
    )
    db.add(db_job)
    await db.commit()
    await db.refresh(db_job)

    # 4. Determine Queue Routing
    queue_name = "celery" # default
    if priority == "high":
        queue_name = "high"
    elif priority == "low":
        queue_name = "low"

    # 5. Trigger Celery Task dynamically
    task_path = TASK_REGISTRY[job_in.name]
    celery.send_task(
        task_path,
        args=[str(db_job.id)],
        kwargs=job_in.payload,
        task_id=str(db_job.id),
        queue=queue_name
    )

    db_job.progress = 0
    return db_job

@router.get("/", response_model=List[JobOut])
async def list_jobs(
    tenant_id: Optional[UUID] = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    query = select(Job).order_by(Job.created_at.desc())
    
    if ctx.is_admin:
        # Admin can view all or filter by specific tenant_id
        if tenant_id:
            # Validate tenant exists to prevent returning empty list on typo
            tenant_res = await db.execute(select(Tenant).filter(Tenant.id == tenant_id))
            tenant = tenant_res.scalar_one_or_none()
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tenant with ID {tenant_id} not found."
                )
            query = query.filter(Job.tenant_id == tenant_id)
    else:
        # Tenant keys strictly isolated to their own tenant
        query = query.filter(Job.tenant_id == ctx.tenant_id)
        
    result = await db.execute(query)
    jobs = result.scalars().all()
    for job in jobs:
        job.progress = get_job_progress(str(job.id), job.status)
    return jobs

@router.get("/{job_id}", response_model=JobDetailOut)
async def get_job(
    job_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(
        select(Job).options(selectinload(Job.logs)).filter(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Enforce tenant isolation
    if not ctx.is_admin and job.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job.progress = get_job_progress(str(job.id), job.status)
    return job

@router.delete("/{job_id}", response_model=JobOut)
async def cancel_job(
    job_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(select(Job).filter(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Enforce tenant isolation
    if not ctx.is_admin and job.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status in [JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED]:
        job.progress = get_job_progress(str(job.id), job.status)
        return job

    # 1. Update DB state to CANCELLED
    job.status = JobStatus.CANCELLED
    await db.commit()
    await db.refresh(job)

    # 2. Write cooperative cancellation flag to Redis (1 hour TTL)
    r = redis.Redis.from_url(settings.REDIS_URI)
    cancel_key = f"cancel:{job_id}"
    r.setex(cancel_key, 3600, 1)

    # 3. Publish cancel update immediately to status WebSocket
    payload = {
        "job_id": str(job_id),
        "status": JobStatus.CANCELLED,
        "progress": 0,
        "tenant_id": str(job.tenant_id)
    }
    r.publish("job_status_updates", json.dumps(payload))

    # 4. Revoke task in Celery broker (clears queue if pending)
    celery.control.revoke(str(job_id))

    job.progress = 0
    return job

# WebSocket 1: Global Status Broadcast
@router.websocket("/stream")
async def stream_global_status(websocket: WebSocket, token: str):
    ws_ctx = verify_ws_token(token)
    if not ws_ctx:
        # Reject connections with invalid token
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await websocket.accept()
    
    tenant_id = ws_ctx.get("tenant_id")
    is_admin = (tenant_id is None)
    
    r = redis.asyncio.from_url(settings.REDIS_URI)
    pubsub = r.pubsub()
    await pubsub.subscribe("job_status_updates")
    
    try:
        while True:
            # Periodically poll Redis pubsub for status updates
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                data_str = message["data"].decode("utf-8")
                data = json.loads(data_str)
                
                # Filter status update by tenant context
                msg_tenant_id = data.get("tenant_id")
                if is_admin or msg_tenant_id == tenant_id:
                    await websocket.send_text(data_str)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe("job_status_updates")
        await pubsub.close()
        await r.close()

# WebSocket 2: Job-Specific Real-time Log Stream
@router.websocket("/{job_id}/stream")
async def stream_job_logs(websocket: WebSocket, job_id: UUID, token: str):
    ws_ctx = verify_ws_token(token)
    if not ws_ctx:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    tenant_id = ws_ctx.get("tenant_id")
    is_admin = (tenant_id is None)

    # 1. Fetch historical logs from database first (for visual persistence)
    async with async_session_maker() as session:
        # Fetch job to verify existence and tenant ownership
        job_res = await session.execute(select(Job).filter(Job.id == job_id))
        job = job_res.scalar_one_or_none()
        if not job:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
            
        if not is_admin and str(job.tenant_id) != tenant_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        from app.models.job_log import JobLog
        res = await session.execute(
            select(JobLog).filter(JobLog.job_id == job_id).order_by(JobLog.created_at.asc())
        )
        existing_logs = res.scalars().all()
        await websocket.accept()
        
        for log in existing_logs:
            log_payload = {
                "id": str(log.id),
                "job_id": str(job_id),
                "level": log.level,
                "message": log.message,
                "created_at": log.created_at.isoformat()
            }
            await websocket.send_json(log_payload)

    # 2. Subscribe to Redis log updates for this job
    r = redis.asyncio.from_url(settings.REDIS_URI)
    pubsub = r.pubsub()
    channel = f"job_logs:{job_id}"
    await pubsub.subscribe(channel)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                data = message["data"].decode("utf-8")
                await websocket.send_text(data)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await r.close()
