from contextlib import contextmanager
from typing import AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Async database setup (for FastAPI)
async_engine = create_async_engine(settings.POSTGRES_ASYNC_URI, echo=False, future=True)
async_session_maker = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

# Sync database setup (for Celery workers)
sync_engine = create_engine(settings.POSTGRES_SYNC_URI, echo=False, future=True)
sync_session_maker = sessionmaker(
    bind=sync_engine, expire_on_commit=False
)

@contextmanager
def get_sync_db():
    session = sync_session_maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
