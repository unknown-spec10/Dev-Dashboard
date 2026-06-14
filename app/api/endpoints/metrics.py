from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_db
from app.models.job import Job, JobStatus
from app.models.tenant import Tenant
from app.models.api_key import ApiKey
from app.models.document import DocumentEmbedding
from app.api.dependencies import get_tenant_context, TenantContext

router = APIRouter()

@router.get("/")
async def get_metrics(
    tenant_id: Optional[UUID] = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get general metrics (throughput, duration, failure rate).
    Filtered by tenant context for tenant-scoped users.
    """
    query_total = select(func.count(Job.id))
    query_failed = select(func.count(Job.id)).filter(Job.status == JobStatus.FAILED)
    query_done = select(Job).filter(Job.status == JobStatus.DONE)
    
    if ctx.is_admin:
        if tenant_id:
            tenant_res = await db.execute(select(Tenant).filter(Tenant.id == tenant_id))
            tenant = tenant_res.scalar_one_or_none()
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tenant with ID {tenant_id} not found."
                )
            query_total = query_total.filter(Job.tenant_id == tenant_id)
            query_failed = query_failed.filter(Job.tenant_id == tenant_id)
            query_done = query_done.filter(Job.tenant_id == tenant_id)
    else:
        query_total = query_total.filter(Job.tenant_id == ctx.tenant_id)
        query_failed = query_failed.filter(Job.tenant_id == ctx.tenant_id)
        query_done = query_done.filter(Job.tenant_id == ctx.tenant_id)
        
    result_total = await db.execute(query_total)
    total_jobs = result_total.scalar() or 0
    
    result_failed = await db.execute(query_failed)
    failed_jobs = result_failed.scalar() or 0
    
    result_done = await db.execute(query_done)
    done_jobs = result_done.scalars().all()
    total_done = len(done_jobs)
    
    failure_rate = (failed_jobs / total_jobs * 100) if total_jobs > 0 else 0.0
    
    total_duration = 0.0
    for job in done_jobs:
        if job.updated_at and job.created_at:
            total_duration += (job.updated_at - job.created_at).total_seconds()
            
    avg_duration = (total_duration / total_done) if total_done > 0 else 0.0
    
    return {
        "throughput": total_jobs,
        "avg_duration_seconds": round(avg_duration, 1),
        "failure_rate": round(failure_rate, 1)
    }

@router.get("/tenants")
async def get_tenants_metrics(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List usage metrics aggregated by tenant (Admin only).
    """
    if not ctx.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only global administrators can view tenant aggregates."
        )
    
    tenants_res = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = tenants_res.scalars().all()
    
    metrics_report = []
    for tenant in tenants:
        tenant_id = tenant.id
        
        # 1. Total jobs submitted by tenant
        res_total = await db.execute(select(func.count(Job.id)).filter(Job.tenant_id == tenant_id))
        total_jobs = res_total.scalar() or 0
        
        # 2. Failed jobs count
        res_failed = await db.execute(
            select(func.count(Job.id)).filter(Job.tenant_id == tenant_id, Job.status == JobStatus.FAILED)
        )
        failed_jobs = res_failed.scalar() or 0
        
        # 3. Successful done jobs
        res_done = await db.execute(
            select(Job).filter(Job.tenant_id == tenant_id, Job.status == JobStatus.DONE)
        )
        done_jobs = res_done.scalars().all()
        total_done = len(done_jobs)
        
        # 4. Embedded documents count in pgvector
        res_docs = await db.execute(
            select(func.count(DocumentEmbedding.id)).filter(DocumentEmbedding.tenant_id == tenant_id)
        )
        doc_count = res_docs.scalar() or 0
        
        # Calculate aggregates
        failure_rate = (failed_jobs / total_jobs * 100) if total_jobs > 0 else 0.0
        success_rate = (total_done / total_jobs * 100) if total_jobs > 0 else 0.0
        
        total_duration = 0.0
        for job in done_jobs:
            if job.updated_at and job.created_at:
                total_duration += (job.updated_at - job.created_at).total_seconds()
                
        avg_duration = (total_duration / total_done) if total_done > 0 else 0.0
        
        # Count active API keys issued for tenant
        res_keys = await db.execute(
            select(func.count(ApiKey.id)).filter(ApiKey.tenant_id == tenant_id, ApiKey.is_active == True)
        )
        active_keys = res_keys.scalar() or 0
        
        metrics_report.append({
            "tenant_id": str(tenant_id),
            "name": tenant.name,
            "slug": tenant.slug,
            "is_active": tenant.is_active,
            "throughput": total_jobs,
            "success_rate": round(success_rate, 1),
            "failure_rate": round(failure_rate, 1),
            "avg_duration_seconds": round(avg_duration, 1),
            "document_count": doc_count,
            "active_keys": active_keys
        })
        
    return metrics_report
