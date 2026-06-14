import uuid
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base

class UsageAlert(Base):
    __tablename__ = "usage_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    proxy_key_id = Column(UUID(as_uuid=True), ForeignKey("proxy_keys.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False) # e.g. 'spend_warning_80', 'spend_limit_exceeded'
    message = Column(String(500), nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    proxy_key = relationship("ProxyKey")
    tenant = relationship("Tenant")
