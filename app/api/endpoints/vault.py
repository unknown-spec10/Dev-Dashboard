from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_db
from app.api.dependencies import get_tenant_context, TenantContext
from app.models.tenant import Tenant
from app.models.provider_key import ProviderKey
from app.core.vault import encrypt_key

router = APIRouter()

class ProviderKeyCreate(BaseModel):
    tenant_id: UUID
    provider: str = Field(..., min_length=1, max_length=50)
    key: str = Field(..., min_length=1)

class ProviderKeyUpdate(BaseModel):
    key: str = Field(..., min_length=1)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_provider_key(
    key_in: ProviderKeyCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    if not ctx.is_admin and ctx.tenant_id != key_in.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to manage keys for this organization."
        )

    # 1. Validate tenant exists
    tenant_result = await db.execute(select(Tenant).filter(Tenant.id == key_in.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {key_in.tenant_id} not found."
        )

    # 2. Check if a key for this provider is already configured for this tenant
    provider_lower = key_in.provider.lower()
    existing_result = await db.execute(
        select(ProviderKey).filter(
            ProviderKey.tenant_id == key_in.tenant_id,
            ProviderKey.provider == provider_lower
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Key for provider '{key_in.provider}' already configured for this tenant. Use PUT to rotate it."
        )

    # 3. Encrypt and save key
    encrypted_val = encrypt_key(key_in.key)
    hint = key_in.key[-4:] if len(key_in.key) >= 4 else "key"

    new_pkey = ProviderKey(
        tenant_id=key_in.tenant_id,
        provider=provider_lower,
        encrypted_key=encrypted_val,
        key_hint=hint,
        is_active=True
    )
    db.add(new_pkey)
    await db.commit()
    await db.refresh(new_pkey)

    return {
        "id": str(new_pkey.id),
        "tenant_id": str(new_pkey.tenant_id),
        "provider": new_pkey.provider,
        "key_hint": new_pkey.key_hint,
        "is_active": new_pkey.is_active,
        "created_at": new_pkey.created_at.isoformat()
    }

@router.get("/")
async def list_provider_keys(
    tenant_id: UUID | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    target_tenant_id = tenant_id
    if not ctx.is_admin:
        if tenant_id and tenant_id != ctx.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to list keys for this organization."
            )
        target_tenant_id = ctx.tenant_id

    query = select(ProviderKey)
    if target_tenant_id:
        query = query.filter(ProviderKey.tenant_id == target_tenant_id)
    query = query.order_by(ProviderKey.created_at.desc())

    result = await db.execute(query)
    keys = result.scalars().all()

    return [
        {
            "id": str(k.id),
            "tenant_id": str(k.tenant_id),
            "provider": k.provider,
            "key_hint": k.key_hint,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat()
        }
        for k in keys
    ]

@router.put("/{key_id}")
async def rotate_provider_key(
    key_id: UUID,
    key_in: ProviderKeyUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(select(ProviderKey).filter(ProviderKey.id == key_id))
    pkey = result.scalar_one_or_none()
    if not pkey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider key with ID {key_id} not found."
        )

    if not ctx.is_admin and ctx.tenant_id != pkey.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to manage keys for this organization."
        )

    encrypted_val = encrypt_key(key_in.key)
    hint = key_in.key[-4:] if len(key_in.key) >= 4 else "key"

    pkey.encrypted_key = encrypted_val
    pkey.key_hint = hint
    
    await db.commit()
    await db.refresh(pkey)

    return {
        "id": str(pkey.id),
        "tenant_id": str(pkey.tenant_id),
        "provider": pkey.provider,
        "key_hint": pkey.key_hint,
        "is_active": pkey.is_active,
        "created_at": pkey.created_at.isoformat()
    }

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_key(
    key_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(select(ProviderKey).filter(ProviderKey.id == key_id))
    pkey = result.scalar_one_or_none()
    if not pkey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider key with ID {key_id} not found."
        )

    if not ctx.is_admin and ctx.tenant_id != pkey.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete keys for this organization."
        )

    await db.delete(pkey)
    await db.commit()
    return None
