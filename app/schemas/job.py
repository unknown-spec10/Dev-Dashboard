from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.models.job import JobStatus
from app.models.job_log import LogLevel

class JobBase(BaseModel):
    name: str
    payload: Dict[str, Any] = {}

class JobCreate(JobBase):
    priority: Optional[str] = "default"  # high, default, low
    tenant_id: Optional[UUID] = None

class JobLogOut(BaseModel):
    id: UUID
    job_id: UUID
    level: LogLevel
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class JobOut(BaseModel):
    id: UUID
    name: str
    status: JobStatus
    priority: str
    payload: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    progress: Optional[int] = 0  # Added to track active running task progress percentage
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class JobDetailOut(JobOut):
    logs: List[JobLogOut] = []

    model_config = ConfigDict(from_attributes=True)
