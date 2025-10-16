"""
Main FastAPI application for DES Formulation System Web Backend

This module initializes the FastAPI app, configures middleware,
registers API routers, and provides the entry point for the server.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_web_config
from utils.agent_loader import initialize_agent
from api import tasks, recommendations, feedback, statistics

# Configure logging
web_config = get_web_config()
logging.basicConfig(
    level=getattr(logging, web_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app.

    Handles startup and shutdown events:
    - Startup: Initialize DESAgent
    - Shutdown: Cleanup resources
    """
    # Startup
    logger.info("Starting DES Formulation System Web Backend...")
    try:
        initialize_agent()
        logger.info("✓ DESAgent initialized successfully")
    except Exception as e:
        logger.error(f"✗ Failed to initialize DESAgent: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down DES Formulation System Web Backend...")


# Create FastAPI app
app = FastAPI(
    title="DES Formulation System API",
    version="1.0.0",
    description=(
        "REST API for Deep Eutectic Solvent (DES) formulation recommendation "
        "and experimental feedback management."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=web_config.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(f"CORS enabled for origins: {web_config.get_cors_origins_list()}")

# Register API routers
app.include_router(
    tasks.router,
    prefix="/api/v1/tasks",
    tags=["Tasks"]
)

app.include_router(
    recommendations.router,
    prefix="/api/v1/recommendations",
    tags=["Recommendations"]
)

app.include_router(
    feedback.router,
    prefix="/api/v1/feedback",
    tags=["Feedback"]
)

app.include_router(
    statistics.router,
    prefix="/api/v1/statistics",
    tags=["Statistics"]
)

# Root endpoint
@app.get("/", tags=["Health"])
async def root():
    """
    Root endpoint - API health check.

    Returns basic information about the API.
    """
    return {
        "name": "DES Formulation System API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Returns:
        JSON response with system health status
    """
    return {
        "status": "healthy",
        "service": "DES Formulation System API",
        "version": "1.0.0"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler for uncaught exceptions.

    Args:
        request: FastAPI request object
        exc: Exception instance

    Returns:
        JSONResponse with error details
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "detail": str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=web_config.api_host,
        port=web_config.api_port,
        reload=web_config.api_reload,
        log_level=web_config.log_level.lower()
    )
