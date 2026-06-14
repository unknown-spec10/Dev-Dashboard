import uuid
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.models.base import Base

class ProxyKey(Base):
    __tablename__ = "proxy_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), unique=True, index=True, nullable=False) # SHA256 of token
    allowed_providers = Column(JSONB, nullable=False, default=list) # e.g. ["openai", "anthropic", "groq"]
    monthly_cap_usd = Column(Numeric(10, 2), nullable=False, default=0.00)
    fallback_mappings = Column(JSONB, nullable=False, default=dict) # e.g. {"openai:gpt-4o": {"provider": "groq", "model": "llama-3-70b"}}
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
