import time
import json
import hashlib
import logging
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import StreamingResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.database import get_async_db
from app.models.proxy_key import ProxyKey
from app.models.provider_key import ProviderKey
from app.models.tenant import Tenant
from app.models.usage_log import UsageLog
from app.core.vault import decrypt_key
from app.core.redis_client import get_redis_client
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()

PROVIDER_URLS = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "groq": "https://api.groq.com/openai"
}

def get_current_year_month() -> str:
    return datetime.utcnow().strftime("%Y_%m")

async def get_proxy_key_cached(key_hash: str, db: AsyncSession) -> dict | None:
    redis_client = get_redis_client()
    cache_key = f"proxy_key:active:{key_hash}"
    
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.error(f"Redis get failed: {e}")

    # Fallback to DB
    result = await db.execute(
        select(ProxyKey)
        .options(selectinload(ProxyKey.tenant))
        .filter(ProxyKey.key_hash == key_hash, ProxyKey.is_active == True)
    )
    key_obj = result.scalar_one_or_none()
    
    if not key_obj or not key_obj.tenant or not key_obj.tenant.is_active:
        return None

    data = {
        "id": str(key_obj.id),
        "tenant_id": str(key_obj.tenant_id),
        "tenant_slug": key_obj.tenant.slug,
        "is_active": key_obj.is_active,
        "allowed_providers": key_obj.allowed_providers,
        "monthly_cap_usd": float(key_obj.monthly_cap_usd),
        "fallback_mappings": key_obj.fallback_mappings
    }

    try:
        redis_client.setex(cache_key, 3600, json.dumps(data)) # Cache for 1 hour
    except Exception as e:
        logger.error(f"Redis set failed: {e}")
        
    return data

async def get_monthly_spend(proxy_key_id: str, key_hash: str, db: AsyncSession) -> float:
    redis_client = get_redis_client()
    ym = get_current_year_month()
    spend_key = f"proxy_key:spend:{key_hash}:{ym}"
    
    try:
        spend = redis_client.get(spend_key)
        if spend is not None:
            return float(spend)
    except Exception as e:
        logger.error(f"Redis spend get failed: {e}")

    # Load from DB
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(UsageLog.estimated_cost_usd)
        .filter(
            UsageLog.proxy_key_id == UUID(proxy_key_id),
            UsageLog.created_at >= start_of_month
        )
    )
    costs = result.scalars().all()
    total_spend = sum(float(c) for c in costs)

    try:
        redis_client.setex(spend_key, 86400, f"{total_spend:.6f}") # Cache for 1 day
    except Exception as e:
        logger.error(f"Redis spend set failed: {e}")

    return total_spend

async def get_decrypted_provider_key(tenant_id: str, provider: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(ProviderKey).filter(
            ProviderKey.tenant_id == UUID(tenant_id),
            ProviderKey.provider == provider,
            ProviderKey.is_active == True
        )
    )
    pkey = result.scalar_one_or_none()
    if not pkey:
        return None
    return decrypt_key(pkey.encrypted_key)

def trigger_async_logging(
    proxy_key_id: str,
    tenant_id: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    request_body: str,
    response_body: str,
    latency_ms: int,
    status_code: int,
    key_hash: str,
    monthly_cap_usd: float
):
    try:
        # Import celery task dynamically to avoid circular dependencies
        from app.tasks.usage_logger import log_proxy_usage
        log_proxy_usage.delay(
            proxy_key_id=proxy_key_id,
            tenant_id=tenant_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_body=request_body,
            response_body=response_body,
            latency_ms=latency_ms,
            status_code=status_code,
            key_hash=key_hash,
            monthly_cap_usd=monthly_cap_usd
        )
    except Exception as e:
        logger.error(f"Failed to enqueue usage logger task: {e}")

@router.api_route("/{provider}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def wildcard_proxy(
    provider: str,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    provider_lower = provider.lower()
    if provider_lower not in PROVIDER_URLS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider}' is not supported."
        )

    # 1. Extract API key (bearer token)
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header."
        )
    
    token = auth_header.split(" ", 1)[1]
    key_hash = hashlib.sha256(token.encode()).hexdigest()

    # 2. Validate token
    proxy_key = await get_proxy_key_cached(key_hash, db)
    if not proxy_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive proxy key."
        )

    if provider_lower not in proxy_key["allowed_providers"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Proxy key is not authorized to access provider '{provider}'."
        )

    # 3. Check Spend Cap
    monthly_cap = proxy_key["monthly_cap_usd"]
    if monthly_cap > 0.0:
        current_spend = await get_monthly_spend(proxy_key["id"], key_hash, db)
        if current_spend >= monthly_cap:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Monthly spend cap exceeded for this proxy key."
            )

    # 4. Decrypt provider key
    real_key = await get_decrypted_provider_key(proxy_key["tenant_id"], provider_lower, db)
    if not real_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Real provider key for '{provider}' is not configured in the vault."
        )

    # 5. Read Request Content
    req_body = await request.body()
    req_body_str = req_body.decode("utf-8") if req_body else ""
    
    # Try parsing JSON to extract model and stream
    req_json = {}
    is_streaming = False
    requested_model = "unknown"
    if req_body_str:
        try:
            req_json = json.loads(req_body_str)
            requested_model = req_json.get("model", "unknown")
            is_streaming = req_json.get("stream", False)
        except Exception:
            pass

    # Helper function to execute request with error recovery / fallback routing
    async def execute_proxy_request(target_provider: str, target_model: str, payload_json: dict):
        base_url = PROVIDER_URLS[target_provider]
        target_url = f"{base_url}/{path}"
        
        # Prepare headers
        headers = {}
        for k, v in request.headers.items():
            k_lower = k.lower()
            if k_lower in ["host", "authorization", "x-api-key", "content-length"]:
                continue
            headers[k] = v

        # Set appropriate Auth headers
        target_key = real_key
        if target_provider != provider_lower:
            # If fallback triggered, decrypt the backup provider's key
            target_key = await get_decrypted_provider_key(proxy_key["tenant_id"], target_provider, db)
            if not target_key:
                raise ValueError(f"Fallback provider key for '{target_provider}' not found.")

        if target_provider == "openai" or target_provider == "groq":
            headers["Authorization"] = f"Bearer {target_key}"
        elif target_provider == "anthropic":
            headers["x-api-key"] = target_key
            headers["anthropic-version"] = "2023-06-01" # Default anthropic version header if not present
            if "anthropic-version" in request.headers:
                headers["anthropic-version"] = request.headers["anthropic-version"]

        # Ensure include_usage is true for OpenAI streaming
        if is_streaming and target_provider == "openai":
            if "stream_options" not in payload_json:
                payload_json["stream_options"] = {"include_usage": True}

        # Modify model in body if fallback model mapping is used
        if target_model != requested_model:
            payload_json["model"] = target_model

        data_to_send = json.dumps(payload_json) if payload_json else req_body

        async with httpx.AsyncClient(timeout=60.0) as client:
            start_time = time.time()
            try:
                # We use stream=True to handle both streaming and non-streaming in a unified manner
                # and inspect headers/status code before deciding to stream back or trigger fallback.
                async with client.stream(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=data_to_send,
                    params=dict(request.query_params)
                ) as response:
                    latency = int((time.time() - start_time) * 1000)

                    # Trigger fallback routing on 429 (Rate Limit) or 5xx (Server Error)
                    if response.status_code in [429, 500, 502, 503, 504]:
                        fallback_key = f"{target_provider}:{target_model}"
                        if fallback_key in proxy_key["fallback_mappings"]:
                            fb_conf = proxy_key["fallback_mappings"][fallback_key]
                            fb_provider = fb_conf.get("provider")
                            fb_model = fb_conf.get("model")
                            
                            logger.warning(f"Request failed with {response.status_code}. Retrying fallback: {fb_provider}/{fb_model}")
                            return await execute_proxy_request(fb_provider, fb_model, payload_json)
                    
                    # Process response
                    if is_streaming and response.status_code == 200:
                        # Yield chunks and capture response for usage logger
                        async def sse_generator():
                            accumulated = []
                            usage_block = None
                            
                            async for chunk in response.aiter_text():
                                yield chunk
                                accumulated.append(chunk)
                                
                                # Try parsing OpenAI stream usage block
                                if "usage" in chunk:
                                    try:
                                        # Simple text extraction for final usage chunk
                                        for line in chunk.split("\n"):
                                            if line.startswith("data:"):
                                                data_str = line[5:].strip()
                                                if data_str and data_str != "[DONE]":
                                                    chunk_data = json.loads(data_str)
                                                    if "usage" in chunk_data and chunk_data["usage"]:
                                                        usage_block = chunk_data["usage"]
                                    except Exception:
                                        pass

                            # Log telemetry asynchronously after stream ends
                            total_latency = int((time.time() - start_time) * 1000)
                            full_resp = "".join(accumulated)
                            
                            p_tok = usage_block.get("prompt_tokens", 0) if usage_block else 0
                            c_tok = usage_block.get("completion_tokens", 0) if usage_block else 0
                            
                            trigger_async_logging(
                                proxy_key_id=proxy_key["id"],
                                tenant_id=proxy_key["tenant_id"],
                                provider=target_provider,
                                model=target_model,
                                prompt_tokens=p_tok,
                                completion_tokens=c_tok,
                                request_body=req_body_str,
                                response_body=full_resp,
                                latency_ms=total_latency,
                                status_code=response.status_code,
                                key_hash=key_hash,
                                monthly_cap_usd=monthly_cap
                            )

                        return StreamingResponse(
                            sse_generator(),
                            status_code=response.status_code,
                            headers=dict(response.headers)
                        )
                    else:
                        # Read entire response
                        content = await response.aread()
                        content_str = content.decode("utf-8") if content else ""
                        
                        # Parse usage from response if present
                        p_tok, c_tok = 0, 0
                        if response.status_code == 200 and content_str:
                            try:
                                res_json = json.loads(content_str)
                                if "usage" in res_json:
                                    p_tok = res_json["usage"].get("prompt_tokens", 0)
                                    c_tok = res_json["usage"].get("completion_tokens", 0)
                            except Exception:
                                pass

                        trigger_async_logging(
                            proxy_key_id=proxy_key["id"],
                            tenant_id=proxy_key["tenant_id"],
                            provider=target_provider,
                            model=target_model,
                            prompt_tokens=p_tok,
                            completion_tokens=c_tok,
                            request_body=req_body_str,
                            response_body=content_str,
                            latency_ms=latency,
                            status_code=response.status_code,
                            key_hash=key_hash,
                            monthly_cap_usd=monthly_cap
                        )

                        return Response(
                            content=content,
                            status_code=response.status_code,
                            headers=dict(response.headers)
                        )

            except Exception as e:
                # Handle connection errors or fallback triggers
                logger.error(f"Proxy request failed: {e}")
                # Try fallback logic if mapping exists
                fallback_key = f"{target_provider}:{target_model}"
                if fallback_key in proxy_key["fallback_mappings"]:
                    fb_conf = proxy_key["fallback_mappings"][fallback_key]
                    fb_provider = fb_conf.get("provider")
                    fb_model = fb_conf.get("model")
                    
                    logger.warning(f"Connection exception. Retrying fallback: {fb_provider}/{fb_model}")
                    return await execute_proxy_request(fb_provider, fb_model, payload_json)
                
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Proxy error connecting to provider: {str(e)}"
                )

    return await execute_proxy_request(provider_lower, requested_model, req_json)
