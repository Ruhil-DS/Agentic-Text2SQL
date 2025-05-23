from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os

from app.api.routes import router
from app.core.config import settings
from app.core.logger import app_logger
from app.utils.prompt_initializer import prompt_initializer

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup"""
    app_logger.info("Initializing application")
    
    # Initialize default prompts in MongoDB
    try:
        prompt_initializer.initialize_default_prompts()
    except Exception as e:
        app_logger.error(f"Error initializing prompts: {str(e)}")

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Welcome to Agentic Text2SQL API",
        "version": "1.0.0",
        "docs_url": "/docs"
    }

if __name__ == "__main__":
    # Get the port from environment variable or default to 8000
    port = int(os.environ.get("PORT", 8000))
    
    app_logger.info(f"Starting Agentic Text2SQL API on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True) 