import secrets
import hashlib
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_db
from app.api.dependencies import get_tenant_context, TenantContext
from app.models.tenant import Tenant
from app.models.proxy_key import ProxyKey
from app.core.redis_client import get_redis_client

router = APIRouter()

class ProxyKeyCreate(BaseModel):
    tenant_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    allowed_providers: List[str] = Field(default_factory=list)
    monthly_cap_usd: float = Field(default=0.0, ge=0.0)

class ProxyKeyFallbackUpdate(BaseModel):
    fallback_mappings: Dict[str, Any] = Field(default_factory=dict)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def evict_key_cache(key_hash: str):
    try:
        redis_client = get_redis_client()
        redis_client.delete(f"proxy_key:active:{key_hash}")
    except Exception as e:
        # Don't fail the request if Redis is down, but log it
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to evict Redis cache for key hash {key_hash}: {e}")

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_proxy_key(
    key_in: ProxyKeyCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    if not ctx.is_admin and ctx.tenant_id != key_in.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to create proxy keys for this organization."
        )

    # 1. Validate tenant exists
    tenant_result = await db.execute(select(Tenant).filter(Tenant.id == key_in.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {key_in.tenant_id} not found."
        )

    # 2. Generate random hex and token
    random_hex = secrets.token_hex(16)
    token = f"dd-{tenant.slug}-{random_hex}"
    key_hash = hash_token(token)

    # 3. Create db record
    new_key = ProxyKey(
        tenant_id=key_in.tenant_id,
        name=key_in.name,
        key_hash=key_hash,
        allowed_providers=[p.lower() for p in key_in.allowed_providers],
        monthly_cap_usd=key_in.monthly_cap_usd,
        fallback_mappings={},
        is_active=True
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)

    # Evict cache (just in case)
    evict_key_cache(key_hash)

    return {
        "id": str(new_key.id),
        "tenant_id": str(new_key.tenant_id),
        "name": new_key.name,
        "key": token, # Returned ONLY once on creation
        "allowed_providers": new_key.allowed_providers,
        "monthly_cap_usd": float(new_key.monthly_cap_usd),
        "fallback_mappings": new_key.fallback_mappings,
        "is_active": new_key.is_active,
        "created_at": new_key.created_at.isoformat()
    }

@router.get("/")
async def list_proxy_keys(
    tenant_id: UUID | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    target_tenant_id = tenant_id
    if not ctx.is_admin:
        if tenant_id and tenant_id != ctx.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to list proxy keys for this organization."
            )
        target_tenant_id = ctx.tenant_id

    query = select(ProxyKey)
    if target_tenant_id:
        query = query.filter(ProxyKey.tenant_id == target_tenant_id)
    query = query.order_by(ProxyKey.created_at.desc())

    result = await db.execute(query)
    keys = result.scalars().all()

    return [
        {
            "id": str(k.id),
            "tenant_id": str(k.tenant_id),
            "name": k.name,
            "key_hint": f"dd-{k.tenant.slug}-..." if k.tenant else "dd-...",
            "allowed_providers": k.allowed_providers,
            "monthly_cap_usd": float(k.monthly_cap_usd),
            "fallback_mappings": k.fallback_mappings,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat()
        }
        for k in keys
    ]

@router.put("/{key_id}/fallback")
async def update_key_fallback(
    key_id: UUID,
    fallback_in: ProxyKeyFallbackUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(select(ProxyKey).filter(ProxyKey.id == key_id))
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proxy key with ID {key_id} not found."
        )

    if not ctx.is_admin and ctx.tenant_id != key_obj.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to manage this proxy key."
        )

    key_obj.fallback_mappings = fallback_in.fallback_mappings
    await db.commit()
    await db.refresh(key_obj)

    # Evict cache to force reload in proxy
    evict_key_cache(key_obj.key_hash)

    return {
        "id": str(key_obj.id),
        "fallback_mappings": key_obj.fallback_mappings
    }

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy_key(
    key_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(select(ProxyKey).filter(ProxyKey.id == key_id))
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proxy key with ID {key_id} not found."
        )

    if not ctx.is_admin and ctx.tenant_id != key_obj.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this proxy key."
        )

    key_hash = key_obj.key_hash
    await db.delete(key_obj)
    await db.commit()

    # Evict cache synchronously
    evict_key_cache(key_hash)

    return None
