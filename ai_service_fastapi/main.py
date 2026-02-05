# main.py - FastAPI Application Entry Point

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import connect_database, disconnect_database
from rabbitmq.connection import connect_rabbitmq, disconnect_rabbitmq
from rabbitmq.consumer import setup_consumers
from routes.scoring import router as scoring_router
from routes.matching import router as matching_router
from routes.chat import router as chat_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    settings = get_settings()
    logger.info("Starting AI Service...")
    logger.info(f"ChromaDB Path: {settings.CHROMA_DB_PATH}")

    # Startup
    try:
        # Connect to database
        await connect_database()
        logger.info("Database connected")
    except Exception as e:
        logger.warning(f"Database connection failed (will retry on demand): {e}")

    try:
        # Connect to RabbitMQ
        rabbitmq = await connect_rabbitmq()
        logger.info("RabbitMQ connected")

        # Setup consumers
        consumer = await setup_consumers(rabbitmq)
        logger.info("Event consumers started")
    except Exception as e:
        logger.warning(f"RabbitMQ connection failed (events disabled): {e}")

    # Initialize services (preload embeddings)
    try:
        from services.vector_search import get_job_matcher
        from services.scoring_engine import get_scoring_engine

        matcher = get_job_matcher()
        logger.info(f"ChromaDB initialized with {matcher.get_collection_stats()['total_indexed']} freelancers")

        engine = get_scoring_engine()
        logger.info("Scoring engine initialized")
    except Exception as e:
        logger.warning(f"Service initialization warning: {e}")

    logger.info("AI Service started successfully!")
    logger.info(f"API available at http://{settings.HOST}:{settings.PORT}/docs")

    yield  # Application runs here

    # Shutdown
    logger.info("Shutting down AI Service...")

    try:
        await disconnect_rabbitmq()
        logger.info("RabbitMQ disconnected")
    except Exception as e:
        logger.warning(f"RabbitMQ disconnect error: {e}")

    try:
        await disconnect_database()
        logger.info("Database disconnected")
    except Exception as e:
        logger.warning(f"Database disconnect error: {e}")

    logger.info("AI Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="BidWise AI Service",
    description="""
## AI-Powered Freelancer Scoring and Job Matching Service

This service provides:
- **Freelancer Scoring**: AI-powered scoring based on experience, education, reviews, and more
- **Semantic Job Matching**: Find the best freelancers for any job using vector similarity search
- **Event-Driven Architecture**: Async RabbitMQ integration for real-time processing

### Features
- ChromaDB for vector storage
- HuggingFace embeddings for semantic search
- Google Gemini AI integration
- Async RabbitMQ consumers
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(scoring_router)
app.include_router(matching_router)
app.include_router(chat_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "BidWise AI Service",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/scoring/health",
    }


# Run with uvicorn
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
