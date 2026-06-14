import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, func, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base

class UserTenant(Base):
    __tablename__ = "user_tenants"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), default="member", nullable=False) # owner, admin, member
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "tenant_id"),
    )

    user = relationship("User")
    tenant = relationship("Tenant")
