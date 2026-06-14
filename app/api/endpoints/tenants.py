import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_db
from app.api.dependencies import get_tenant_context, TenantContext
from app.models.tenant import Tenant
from app.models.api_key import ApiKey
from app.tasks.registry import TASK_REGISTRY

router = APIRouter()

class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_in: TenantCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    if not ctx.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only global administrators can register tenants."
        )
    
    # Check if slug is already taken
    existing_result = await db.execute(select(Tenant).filter(Tenant.slug == tenant_in.slug))
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant slug '{tenant_in.slug}' is already taken."
        )
    
    new_tenant = Tenant(
        name=tenant_in.name,
        slug=tenant_in.slug,
        is_active=True
    )
    db.add(new_tenant)
    await db.commit()
    await db.refresh(new_tenant)
    return new_tenant

@router.get("/")
async def list_tenants(
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    if not ctx.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only global administrators can list tenants."
        )
    
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return result.scalars().all()

@router.post("/{tenant_id}/keys", status_code=status.HTTP_201_CREATED)
async def create_tenant_key(
    tenant_id: UUID,
    key_in: ApiKeyCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_async_db)
):
    if not ctx.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only global administrators can create tenant API keys."
        )
    
    # 1. Validate that the tenant exists
    tenant_result = await db.execute(select(Tenant).filter(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found."
        )
        
    # 2. Validate scopes
    for scope in key_in.scopes:
        if scope == "*":
            continue
        if scope.startswith("task:"):
            task_name = scope.split(":", 1)[1]
            if task_name not in TASK_REGISTRY:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid scope: task '{task_name}' is not registered."
                )
        elif scope.startswith("priority:"):
            priority_val = scope.split(":", 1)[1]
            if priority_val not in ["high", "default", "low"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid scope: priority '{priority_val}' is invalid. Use 'high', 'default', or 'low'."
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope format: '{scope}'. Must be '*' or start with 'task:' or 'priority:'."
            )
            
    # 3. Create key
    new_key_str = f"tenant_{secrets.token_hex(20)}"
    new_key = ApiKey(
        key=new_key_str,
        name=key_in.name,
        scopes=key_in.scopes,
        is_active=True,
        tenant_id=tenant_id
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    
    return {
        "id": str(new_key.id),
        "name": new_key.name,
        "key": new_key_str,  # Returned only once on creation
        "scopes": new_key.scopes,
        "tenant_id": str(new_key.tenant_id),
        "is_active": new_key.is_active,
        "created_at": new_key.created_at.isoformat()
    }
