from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.core.database import async_session_maker
from app.api.dependencies import seed_api_key_if_missing

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed the default admin API key on startup
    async with async_session_maker() as session:
        try:
            await seed_api_key_if_missing(session)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error seeding API key: {e}")
    yield

app = FastAPI(title="Dev Dashboard API", lifespan=lifespan)

# Configure CORS so development clients can interact with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to Dev Dashboard API", "version": "1.0.0"}
