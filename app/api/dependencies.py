from dataclasses import dataclass
from uuid import UUID
import hmac
import hashlib
import base64
import time
import json
from fastapi import Security, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.database import get_async_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.models.user_tenant import UserTenant
from app.models.tenant import Tenant
from app.core.auth_jwt import decode_access_token
from app.core.config import settings

@dataclass
class TenantContext:
    tenant_id: UUID | None
    tenant_slug: str | None
    scopes: list[str]
    is_admin: bool

security = HTTPBearer(auto_error=False)

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_async_db)
) -> ApiKey:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key."
        )
    
    key_val = credentials.credentials
    result = await db.execute(
        select(ApiKey)
        .options(selectinload(ApiKey.tenant))
        .filter(ApiKey.key == key_val, ApiKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API Key."
        )
        
    # Check tenant active status if key is scoped to a tenant
    if api_key.tenant_id is not None:
        if not api_key.tenant or not api_key.tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant is suspended."
            )
    
    return api_key

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header."
        )
    
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token."
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload."
        )
        
    result = await db.execute(select(User).filter(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found."
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated."
        )
        
    return user

async def get_tenant_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_async_db)
) -> TenantContext:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header."
        )
        
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if payload is not None:
        # JWT Flow
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token payload."
            )
            
        user_res = await db.execute(select(User).filter(User.id == UUID(user_id)))
        user = user_res.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or suspended user session."
            )
            
        tenant_id_str = request.headers.get("x-tenant-id")
        
        if user.is_admin:
            if tenant_id_str:
                try:
                    t_id = UUID(tenant_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid Tenant ID format.")
                t_res = await db.execute(select(Tenant).filter(Tenant.id == t_id))
                tenant = t_res.scalar_one_or_none()
                if not tenant:
                    raise HTTPException(status_code=404, detail="Tenant not found.")
                return TenantContext(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    scopes=["*"],
                    is_admin=True
                )
            return TenantContext(
                tenant_id=None,
                tenant_slug=None,
                scopes=["*"],
                is_admin=True
            )
        else:
            # Regular User
            if tenant_id_str:
                try:
                    t_id = UUID(tenant_id_str)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid Tenant ID format.")
                
                ut_res = await db.execute(
                    select(UserTenant)
                    .options(selectinload(UserTenant.tenant))
                    .filter(UserTenant.user_id == user.id, UserTenant.tenant_id == t_id)
                )
                user_tenant = ut_res.scalar_one_or_none()
                if not user_tenant or not user_tenant.tenant:
                    raise HTTPException(status_code=403, detail="Access to this tenant is denied.")
                
                return TenantContext(
                    tenant_id=user_tenant.tenant_id,
                    tenant_slug=user_tenant.tenant.slug,
                    scopes=["*"],
                    is_admin=False
                )
            else:
                # Default to first associated tenant
                ut_res = await db.execute(
                    select(UserTenant)
                    .options(selectinload(UserTenant.tenant))
                    .filter(UserTenant.user_id == user.id)
                    .order_by(UserTenant.created_at.asc())
                )
                user_tenants = ut_res.scalars().all()
                if not user_tenants:
                    return TenantContext(
                        tenant_id=None,
                        tenant_slug=None,
                        scopes=[],
                        is_admin=False
                    )
                first = user_tenants[0]
                return TenantContext(
                    tenant_id=first.tenant_id,
                    tenant_slug=first.tenant.slug if first.tenant else None,
                    scopes=["*"],
                    is_admin=False
                )
    else:
        # Fallback to static API key verification
        api_key = await verify_api_key(credentials, db)
        return TenantContext(
            tenant_id=api_key.tenant_id,
            tenant_slug=api_key.tenant.slug if api_key.tenant else None,
            scopes=api_key.scopes,
            is_admin=(api_key.tenant_id is None)
        )


def check_scopes(scopes: list[str], task_name: str, priority: str):
    if "*" in scopes:
        return
        
    task_scope = f"task:{task_name}"
    if task_scope not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API Key lacks scope required to run task: '{task_name}'."
        )
        
    priority_scope = f"priority:{priority.lower()}"
    if priority_scope not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API Key lacks scope required for priority: '{priority}'."
        )

def check_api_key_scopes(api_key: ApiKey, task_name: str, priority: str):
    check_scopes(api_key.scopes, task_name, priority)

# WebSocket token signing/verification helpers
def generate_ws_token(tenant_id: UUID | None, scopes: list[str]) -> str:
    secret_bytes = settings.SECRET_KEY.encode("utf-8")
    payload = {
        "tenant_id": str(tenant_id) if tenant_id else None,
        "scopes": scopes,
        "expires": int(time.time()) + 30  # 30s expiration
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8")
    
    signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8")
    
    return f"{payload_b64}.{signature_b64}"

def verify_ws_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature_b64 = parts
        
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        signature_bytes = base64.urlsafe_b64decode(signature_b64.encode("utf-8"))
        
        secret_bytes = settings.SECRET_KEY.encode("utf-8")
        expected_signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(signature_bytes, expected_signature):
            return None
            
        payload = json.loads(payload_bytes.decode("utf-8"))
        if int(time.time()) > payload.get("expires", 0):
            return None
            
        return payload
    except Exception:
        return None

# Seed function to initialize the default API key
async def seed_api_key_if_missing(db: AsyncSession):
    default_key = "dev-dashboard-super-key"
    result = await db.execute(select(ApiKey).filter(ApiKey.key == default_key))
    existing_key = result.scalar_one_or_none()
    
    if not existing_key:
        new_key = ApiKey(
            key=default_key,
            name="Default Administrator Key",
            scopes=["*"],  # Full access
            is_active=True
        )
        db.add(new_key)
        await db.commit()
