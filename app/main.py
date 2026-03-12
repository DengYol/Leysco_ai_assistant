from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.api import ai_routes
from app.api.debug_routes import router as debug_router
import logging

# Load environment variables FIRST (before any other imports that use them)
load_dotenv()

# -----------------------------
# Logging Setup
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("leysco_ai_assistant")

# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(
    title="Leysco AI Sales Assistant",
    description="AI Sales Assistant for field reps using Leysco Sales System",
    version="1.0.0"
)

# -----------------------------
# CORS Middleware (optional)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Include Routers
# -----------------------------
app.include_router(ai_routes.router, prefix="/api/ai", tags=["AI Assistant"])
app.include_router(debug_router,     prefix="/debug",  tags=["Debug"])

# -----------------------------
# Health Check Endpoint
# -----------------------------
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Leysco AI Assistant is running"}

# -----------------------------
# Startup Event
# -----------------------------
@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    logger.info("=" * 60)
    logger.info("🚀 Leysco AI Assistant Starting...")
    logger.info("=" * 60)
    
    # Test LLM connection
    try:
        from app.services.llm_service import LLMService
        llm = LLMService()
        if llm.test_connection():
            logger.info("✅ LLM Service: Connected and working")
        else:
            logger.warning("⚠️ LLM Service: Connection test failed")
    except Exception as e:
        logger.error(f"❌ LLM Service: Failed to initialize - {e}")
    
    logger.info("=" * 60)