import unittest
import json
import hashlib
from datetime import datetime
from uuid import uuid4
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient
from app.main import app
from app.core.vault import encrypt_key, decrypt_key
from app.models.tenant import Tenant
from app.models.api_key import ApiKey
from app.models.provider_key import ProviderKey
from app.models.proxy_key import ProxyKey
from app.core.redis_client import get_redis_client

class TestProxyVault(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.headers = {"Authorization": "Bearer dev-dashboard-super-key"}
        self.redis = get_redis_client()

    def tearDown(self):
        # Clean up Redis keys
        keys = self.redis.keys("proxy_key:*")
        if keys:
            self.redis.delete(*keys)

    def test_vault_encryption(self):
        secret = "sk-test-key-123456"
        encrypted = encrypt_key(secret)
        self.assertNotEqual(secret, encrypted)
        
        decrypted = decrypt_key(encrypted)
        self.assertEqual(secret, decrypted)

    async def test_integration_flow(self):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # 1. Create a Tenant
            tenant_slug = f"test-tenant-{uuid4().hex[:6]}"
            tenant_res = await ac.post(
                "/api/tenants/",
                json={"name": "Test Tenant", "slug": tenant_slug},
                headers=self.headers
            )
            self.assertEqual(tenant_res.status_code, 201)
            tenant_data = tenant_res.json()
            tenant_id = tenant_data["id"]

            # 2. Store OpenAI Key in Vault
            vault_res = await ac.post(
                "/api/vault/",
                json={
                    "tenant_id": tenant_id,
                    "provider": "openai",
                    "key": "sk-real-openai-key-999"
                },
                headers=self.headers
            )
            self.assertEqual(vault_res.status_code, 201)
            vault_data = vault_res.json()
            self.assertEqual(vault_data["provider"], "openai")
            self.assertEqual(vault_data["key_hint"], "-999")

            # 3. Create a Proxy Key with Spend Cap
            proxy_res = await ac.post(
                "/api/proxy-keys/",
                json={
                    "tenant_id": tenant_id,
                    "name": "Test Proxy Project Key",
                    "allowed_providers": ["openai", "groq"],
                    "monthly_cap_usd": 5.0
                },
                headers=self.headers
            )
            self.assertEqual(proxy_res.status_code, 201)
            proxy_data = proxy_res.json()
            proxy_key_val = proxy_data["key"]
            proxy_key_id = proxy_data["id"]
            
            self.assertTrue(proxy_key_val.startswith(f"dd-{tenant_slug}-"))

            # 4. Mock the proxy request to OpenAI (successful response)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.aread = AsyncMock(return_value=json.dumps({
                "choices": [{"message": {"content": "Hello world"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}
            }).encode())

            # Mock the async stream context manager
            mock_stream_ctx = MagicMock()
            mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

            with patch("httpx.AsyncClient.stream", return_value=mock_stream_ctx):
                with patch("app.tasks.usage_logger.log_proxy_usage.delay") as mock_celery_task:
                    # Call proxy
                    headers = {"Authorization": f"Bearer {proxy_key_val}"}
                    proxy_call_res = await ac.post(
                        "/api/proxy/openai/v1/chat/completions",
                        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                        headers=headers
                    )
                    self.assertEqual(proxy_call_res.status_code, 200)
                    self.assertEqual(proxy_call_res.json()["choices"][0]["message"]["content"], "Hello world")
                    
                    # Check that Celery background task was enqueued
                    mock_celery_task.assert_called_once()

            # 5. Test Fallback Routing
            # Configure fallback rule: if openai:gpt-4o fails, use groq:llama-3-70b
            fallback_rules = {
                "openai:gpt-4o": {
                    "provider": "groq",
                    "model": "llama-3-70b"
                }
            }
            fallback_res = await ac.put(
                f"/api/proxy-keys/{proxy_key_id}/fallback",
                json={"fallback_mappings": fallback_rules},
                headers=self.headers
            )
            self.assertEqual(fallback_res.status_code, 200)

            # Store Groq key in Vault (required for fallback decryption)
            await ac.post(
                "/api/vault/",
                json={
                    "tenant_id": tenant_id,
                    "provider": "groq",
                    "key": "gsk-groq-key-777"
                },
                headers=self.headers
            )

            # Mock: first call to OpenAI returns 429, second call to Groq returns 200
            mock_429_response = MagicMock()
            mock_429_response.status_code = 429
            mock_429_response.headers = {}
            mock_429_response.aread = AsyncMock(return_value=b"Rate limit exceeded")

            mock_200_response = MagicMock()
            mock_200_response.status_code = 200
            mock_200_response.headers = {"content-type": "application/json"}
            mock_200_response.aread = AsyncMock(return_value=json.dumps({
                "choices": [{"message": {"content": "Fallback response"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4}
            }).encode())

            # Setup side effect for stream context manager: first returns 429, second 200
            mock_stream_ctx_429 = MagicMock()
            mock_stream_ctx_429.__aenter__ = AsyncMock(return_value=mock_429_response)
            mock_stream_ctx_429.__aexit__ = AsyncMock(return_value=None)

            mock_stream_ctx_200 = MagicMock()
            mock_stream_ctx_200.__aenter__ = AsyncMock(return_value=mock_200_response)
            mock_stream_ctx_200.__aexit__ = AsyncMock(return_value=None)

            with patch("httpx.AsyncClient.stream", side_effect=[mock_stream_ctx_429, mock_stream_ctx_200]):
                with patch("app.tasks.usage_logger.log_proxy_usage.delay") as mock_celery_task:
                    headers = {"Authorization": f"Bearer {proxy_key_val}"}
                    proxy_call_res = await ac.post(
                        "/api/proxy/openai/v1/chat/completions",
                        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                        headers=headers
                    )
                    self.assertEqual(proxy_call_res.status_code, 200)
                    self.assertEqual(proxy_call_res.json()["choices"][0]["message"]["content"], "Fallback response")
                    self.assertEqual(mock_celery_task.call_count, 1)

            # 6. Test Spend Cap Exceeded (402 Payment Required)
            # Set monthly spend in Redis to $5.50 (which exceeds the $5.00 limit)
            ym = datetime.utcnow().strftime("%Y_%m")
            key_hash = hashlib.sha256(proxy_key_val.encode()).hexdigest()
            self.redis.set(f"proxy_key:spend:{key_hash}:{ym}", "5.50")

            headers = {"Authorization": f"Bearer {proxy_key_val}"}
            proxy_call_res = await ac.post(
                "/api/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                headers=headers
            )
            self.assertEqual(proxy_call_res.status_code, 402)
            self.assertEqual(proxy_call_res.json()["detail"], "Monthly spend cap exceeded for this proxy key.")

if __name__ == "__main__":
    unittest.main()
