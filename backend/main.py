from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from core.config import settings
from core.neo4j_conn import neo4j_conn
from api import repos, chat, auth
import logging
import uvicorn
from contextlib import asynccontextmanager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting CompassChat backend...")
    
    try:
        # Initialize Neo4j indexes
        neo4j_conn.create_indexes()
        logger.info("Neo4j indexes initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j indexes: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down CompassChat backend...")
    try:
        neo4j_conn.close()
        logger.info("Neo4j connection closed")
    except Exception as e:
        logger.error(f"Error closing Neo4j connection: {e}")


# Create FastAPI app
app = FastAPI(
    title="CompassChat API",
    description="Chat with your code using AI-powered analysis",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(repos.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "CompassChat API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test Neo4j connection
        with neo4j_conn.get_session() as session:
            session.run("RETURN 1")
        
        return {
            "status": "healthy",
            "neo4j": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )
