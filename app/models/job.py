import enum
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.models.base import Base

class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    
    # Storing as String to make future database schema migrations (e.g. adding statuses) painless,
    # while validating using Python's enum at the API/Worker levels.
    status = Column(String(50), default=JobStatus.PENDING, nullable=False)
    priority = Column(String(50), default="default", nullable=False) # high, default, low
    payload = Column(JSONB, nullable=False, default=dict)
    result = Column(JSONB, nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")
    tenant = relationship("Tenant")

