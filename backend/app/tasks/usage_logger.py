import json
import logging
import hashlib
from datetime import datetime
from uuid import UUID
from app.core.celery_app import celery
from app.core.database import get_sync_db
from app.core.redis_client import get_redis_client
from app.models.usage_log import UsageLog
from app.models.usage_alert import UsageAlert
from app.models.proxy_key import ProxyKey
from app.models.tenant import Tenant
from app.models.job import Job
from app.models.job_log import JobLog
from app.models.provider_key import ProviderKey
import tiktoken

logger = logging.getLogger(__name__)

# Standard model prices in USD per 1M tokens (input / output)
MODEL_PRICING = {
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "llama-3-70b": {"input": 0.59, "output": 0.79},
    "llama-3-8b": {"input": 0.05, "output": 0.10},
    "llama3-70b": {"input": 0.59, "output": 0.79},
    "llama3-8b": {"input": 0.05, "output": 0.10},
}

def count_tokens_openai(text: str, model: str) -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception:
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            return len(text) // 4
    return len(encoding.encode(text))

def estimate_tokens(text: str, provider: str, model: str) -> int:
    if not text:
        return 0
    if provider in ["openai", "groq"]:
        return count_tokens_openai(text, model)
    else:
        # Fallback estimation for Anthropic or others
        return len(text) // 4

def extract_prompt_text(req_body_str: str) -> str:
    if not req_body_str:
        return ""
    try:
        body = json.loads(req_body_str)
        if "messages" in body:
            parts = []
            for m in body["messages"]:
                if isinstance(m, dict):
                    content = m.get("content", "")
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        # Handle content list blocks
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                parts.append(block.get("text", ""))
            return " ".join(parts)
        elif "prompt" in body:
            return str(body["prompt"])
    except Exception:
        pass
    return req_body_str

def extract_completion_text(res_body_str: str) -> str:
    if not res_body_str:
        return ""
    try:
        res_json = json.loads(res_body_str)
        if "choices" in res_json and len(res_json["choices"]) > 0:
            first_choice = res_json["choices"][0]
            if "message" in first_choice and isinstance(first_choice["message"], dict):
                return first_choice["message"].get("content", "")
            elif "text" in first_choice:
                return first_choice["text"]
        elif "content" in res_json and isinstance(res_json["content"], list):
            # Anthropic messages JSON format
            return " ".join([c.get("text", "") for c in res_json["content"] if isinstance(c, dict) and c.get("type") == "text"])
    except Exception:
        pass
    return res_body_str

def calculate_cost(model: str, p_tok: int, c_tok: int) -> float:
    model_lower = model.lower()
    pricing = None
    for k, v in MODEL_PRICING.items():
        if k in model_lower:
            pricing = v
            break
    if not pricing:
        # Default fallback pricing
        pricing = {"input": 1.00, "output": 3.00}
    
    input_cost = (p_tok / 1_000_000.0) * pricing["input"]
    output_cost = (c_tok / 1_000_000.0) * pricing["output"]
    return input_cost + output_cost

@celery.task(name="app.tasks.usage_logger.log_proxy_usage")
def log_proxy_usage(
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
        # 1. Resolve token counts
        if prompt_tokens <= 0 and request_body:
            prompt_text = extract_prompt_text(request_body)
            prompt_tokens = estimate_tokens(prompt_text, provider, model)
            
        if completion_tokens <= 0 and response_body:
            completion_text = extract_completion_text(response_body)
            completion_tokens = estimate_tokens(completion_text, provider, model)

        # Ensure we don't have negative numbers
        prompt_tokens = max(0, prompt_tokens)
        completion_tokens = max(0, completion_tokens)

        # 2. Calculate estimated cost
        cost = calculate_cost(model, prompt_tokens, completion_tokens)
        if status_code >= 400:
            # Failed requests cost nothing
            cost = 0.0

        # 3. Save DB Log record
        with get_sync_db() as session:
            log = UsageLog(
                proxy_key_id=UUID(proxy_key_id) if proxy_key_id else None,
                tenant_id=UUID(tenant_id),
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=cost,
                status_code=status_code
            )
            session.add(log)
            session.commit()

            # 4. Update Redis Spend Cap Counter
            redis_client = get_redis_client()
            ym = datetime.utcnow().strftime("%Y_%m")
            spend_key = f"proxy_key:spend:{key_hash}:{ym}"
            
            try:
                new_spend = redis_client.incrbyfloat(spend_key, cost)
            except Exception as e:
                logger.error(f"Failed to increment Redis spend: {e}")
                # Fallback to loading and caching new sum
                return

            # 5. Check spend thresholds and issue alerts
            if monthly_cap_usd > 0.0:
                warning_80_key = f"proxy_key:alert_sent:80:{key_hash}:{ym}"
                warning_100_key = f"proxy_key:alert_sent:100:{key_hash}:{ym}"

                # Check 100% threshold
                if new_spend >= monthly_cap_usd:
                    if not redis_client.get(warning_100_key):
                        # Get key details for description
                        pkey = session.get(ProxyKey, UUID(proxy_key_id))
                        name = pkey.name if pkey else "Proxy Key"
                        
                        alert = UsageAlert(
                            tenant_id=UUID(tenant_id),
                            proxy_key_id=UUID(proxy_key_id),
                            alert_type="spend_limit_exceeded",
                            message=f"Spend cap reached: Proxy Key '{name}' has reached its monthly cap of ${monthly_cap_usd:.2f} (current spend: ${new_spend:.2f}).",
                            is_read=False
                        )
                        session.add(alert)
                        session.commit()
                        redis_client.setex(warning_100_key, 2592000, "1") # 30 days cache
                # Check 80% threshold
                elif new_spend >= 0.8 * monthly_cap_usd:
                    if not redis_client.get(warning_80_key):
                        pkey = session.get(ProxyKey, UUID(proxy_key_id))
                        name = pkey.name if pkey else "Proxy Key"
                        
                        alert = UsageAlert(
                            tenant_id=UUID(tenant_id),
                            proxy_key_id=UUID(proxy_key_id),
                            alert_type="spend_warning_80",
                            message=f"Spend warning (80%): Proxy Key '{name}' is approaching its monthly cap (current spend: ${new_spend:.2f} of ${monthly_cap_usd:.2f}).",
                            is_read=False
                        )
                        session.add(alert)
                        session.commit()
                        redis_client.setex(warning_80_key, 2592000, "1") # 30 days cache

    except Exception as e:
        logger.error(f"Error executing usage logging task: {e}")
