import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import router
from app.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("effiflo-dev-unifier")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Dev Profile Unifier started")
    yield
    # Shutdown actions
    logger.info("Dev Profile Unifier shutting down")

app = FastAPI(
    title="Dev Profile Unifier",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(router)
