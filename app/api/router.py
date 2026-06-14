from fastapi import APIRouter
from app.api.endpoints import jobs, metrics, auth, tenants, vault, proxy_keys, proxy, usage

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(vault.router, prefix="/vault", tags=["vault"])
api_router.include_router(proxy_keys.router, prefix="/proxy-keys", tags=["proxy-keys"])
api_router.include_router(proxy.router, prefix="/proxy", tags=["proxy"])
api_router.include_router(usage.router, prefix="/usage", tags=["usage"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
