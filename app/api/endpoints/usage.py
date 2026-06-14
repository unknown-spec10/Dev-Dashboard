from uuid import UUID
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.database import get_async_db
from app.api.dependencies import get_tenant_context, TenantContext
from app.models.usage_log import UsageLog
from app.models.usage_alert import UsageAlert
from app.models.proxy_key import ProxyKey

router = APIRouter()

@router.get("/")
async def get_usage_logs(
    tenant_id: UUID | None = None,
    limit: int = 100,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    query = select(UsageLog).options(selectinload(UsageLog.proxy_key)).order_by(UsageLog.created_at.desc()).limit(limit)
    
    # Enforce tenant isolation
    if not ctx.is_admin:
        query = query.filter(UsageLog.tenant_id == ctx.tenant_id)
    elif tenant_id:
        query = query.filter(UsageLog.tenant_id == tenant_id)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": str(l.id),
            "proxy_key_id": str(l.proxy_key_id) if l.proxy_key_id else None,
            "proxy_key_name": l.proxy_key.name if l.proxy_key else "Revoked Key",
            "tenant_id": str(l.tenant_id),
            "provider": l.provider,
            "model": l.model,
            "prompt_tokens": l.prompt_tokens,
            "completion_tokens": l.completion_tokens,
            "latency_ms": l.latency_ms,
            "estimated_cost_usd": float(l.estimated_cost_usd),
            "status_code": l.status_code,
            "created_at": l.created_at.isoformat()
        }
        for l in logs
    ]

@router.get("/summary")
async def get_usage_summary(
    tenant_id: UUID | None = None,
    days: int = 7,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    # Enforce tenant isolation
    target_tenant_id = ctx.tenant_id
    if ctx.is_admin and tenant_id:
        target_tenant_id = tenant_id

    start_date = datetime.utcnow() - timedelta(days=days)

    # 1. Total spent and request counts
    base_query = select(UsageLog).filter(UsageLog.created_at >= start_date)
    if target_tenant_id:
        base_query = base_query.filter(UsageLog.tenant_id == target_tenant_id)
    
    # Run queries
    db_res = await db.execute(base_query)
    logs = db_res.scalars().all()

    total_cost = sum(float(l.estimated_cost_usd) for l in logs)
    total_requests = len(logs)

    # 2. Cost by provider
    cost_by_provider = {}
    cost_by_model = {}
    cost_by_project = {}
    cost_by_day = {}

    # Initialize daily costs for the line chart
    for i in range(days):
        d_str = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        cost_by_day[d_str] = 0.0

    # Load proxy keys to map project names
    key_result = await db.execute(select(ProxyKey))
    key_map = {k.id: k.name for k in key_result.scalars().all()}

    for l in logs:
        # Cost by provider
        prov = l.provider
        cost_by_provider[prov] = cost_by_provider.get(prov, 0.0) + float(l.estimated_cost_usd)
        
        # Cost by model
        md = l.model
        cost_by_model[md] = cost_by_model.get(md, 0.0) + float(l.estimated_cost_usd)
        
        # Cost by project (Proxy Key)
        pkey_name = key_map.get(l.proxy_key_id, "Revoked/System Key") if l.proxy_key_id else "System Key"
        cost_by_project[pkey_name] = cost_by_project.get(pkey_name, 0.0) + float(l.estimated_cost_usd)

        # Cost by day
        day_str = l.created_at.strftime("%Y-%m-%d")
        if day_str in cost_by_day:
            cost_by_day[day_str] += float(l.estimated_cost_usd)

    # Format daily chart data sorted chronologically
    daily_chart = [
        {"date": date, "cost": round(cost, 4)}
        for date, cost in sorted(cost_by_day.items())
    ]

    return {
        "total_cost_usd": round(total_cost, 4),
        "total_requests": total_requests,
        "cost_by_provider": {k: round(v, 4) for k, v in cost_by_provider.items()},
        "cost_by_model": {k: round(v, 4) for k, v in cost_by_model.items()},
        "cost_by_project": {k: round(v, 4) for k, v in cost_by_project.items()},
        "daily_chart": daily_chart
    }

@router.get("/alerts")
async def get_usage_alerts(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    query = select(UsageAlert).order_by(UsageAlert.created_at.desc())
    if not ctx.is_admin:
        query = query.filter(UsageAlert.tenant_id == ctx.tenant_id)
        
    result = await db.execute(query)
    alerts = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "tenant_id": str(a.tenant_id),
            "proxy_key_id": str(a.proxy_key_id),
            "alert_type": a.alert_type,
            "message": a.message,
            "is_read": a.is_read,
            "created_at": a.created_at.isoformat()
        }
        for a in alerts
    ]

@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(select(UsageAlert).filter(UsageAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found."
        )

    # Check permission
    if not ctx.is_admin and alert.tenant_id != ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )

    alert.is_read = True
    await db.commit()
    return {"message": "Alert marked as read"}
