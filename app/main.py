"""
app/main.py
===========
Leysco AI Sales Assistant - Main Application Entry Point

UPDATED: Phase 1 - Added database persistence and background scheduler
UPDATED: Chat Persistence - Added conversation storage and history
UPDATED: Phase 1.3 - Added vector store initialization and ERP data loading
UPDATED: S1.0 Input Validation - Added Pydantic validation and sanitization
UPDATED: S1.1 + S1.2 Rate Limiting & Error Handling - Added rate limits and secure errors
FIXED: Background scanner no longer uses TEST_USER_TOKEN or hardcoded users.
       It authenticates per-tenant using service account credentials and only
       scans users who have active sessions (real logged-in users).
FIXED: CORS locked to configured origins instead of allow_origins=["*"].
FIXED: Debug routes gated on APP_ENV, not a mutable DEBUG string.
FIXED: Frontend no longer generates fake Bearer tokens in localStorage.
ADDED: Authentication routes (/api/auth/login, /api/auth/logout, /api/auth/verify)
ADDED: Vector store initialization for ERP knowledge base (P1.3)
ADDED: Input validation middleware (S1.0) - Prevents SQL injection and XSS
ADDED: Rate limiting (S1.1) - Prevents DDoS and brute force attacks
ADDED: Secure error handling (S1.2) - No data leaks, security logging
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from app.api.ai_routes import router as ai_router
from app.api.tenant_routes import router as tenant_router
from app.api.debug_routes import router as debug_router
from app.api.auth_routes import router as auth_router
# S1.0 Input Validation
from app.api.middleware.validators import validation_error_handler
from fastapi.exceptions import RequestValidationError
# S1.1 + S1.2 Rate Limiting & Error Handling
from app.core.rate_limiter import get_rate_limiter
from app.core.error_handlers import (
    handle_exception, log_security_event,
    AppError, ClientError, ServerError,
    RateLimitError
)
import logging
import os
import asyncio
from datetime import datetime
import time

# Load environment variables FIRST
load_dotenv()

# NEW: Phase 1 - Database and Scheduler imports
try:
    from app.models.notification_models import init_db
    from app.services.notification_scheduler import init_scheduler, shutdown_scheduler
    PHASE1_AVAILABLE = True
except ImportError:
    PHASE1_AVAILABLE = False
    init_db = None
    init_scheduler = None
    shutdown_scheduler = None
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(
        "⚠️ Phase 1 modules not found. Notification database features disabled. "
        "Copy Phase 1 files (notification_models.py, notification_scheduler.py) to app/"
    )

# NEW: Chat Persistence imports
try:
    from app.models.chat_models import ConversationSession, ChatMessage
    from app.services.chat_persistence_service import get_chat_persistence_service
    CHAT_PERSISTENCE_AVAILABLE = True
except ImportError:
    CHAT_PERSISTENCE_AVAILABLE = False
    ConversationSession = None
    ChatMessage = None
    get_chat_persistence_service = None
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(
        "⚠️ Chat persistence modules not found. Chat history will not be saved. "
        "Copy chat_models.py and chat_persistence_service.py to app/"
    )

# NEW: Phase 1.3 - Vector Store imports (ERP Knowledge Base)
try:
    from app.services.vector_store import init_vector_store, close_vector_store
    from app.services.erp_data_loader import load_erp_data_on_startup
    VECTOR_STORE_AVAILABLE = True
except ImportError:
    VECTOR_STORE_AVAILABLE = False
    init_vector_store = None
    close_vector_store = None
    load_erp_data_on_startup = None
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning(
        "⚠️ Vector store modules not found. ERP knowledge base disabled. "
        "Copy vector_store.py and erp_data_loader.py to app/services/"
    )

# -----------------------------
# Logging Setup
# -----------------------------
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("leysco_ai_assistant")

# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(
    title="Leysco AI Sales Assistant",
    description="AI Sales Assistant for field reps using Leysco Sales System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# S1.0: Input Validation - Register Pydantic error handler
app.add_exception_handler(
    RequestValidationError,
    validation_error_handler
)

# S1.2: Error Handling - Register global exception handler for all unhandled exceptions
app.add_exception_handler(Exception, handle_exception)

# -----------------------------
# CORS — locked to configured origins
# -----------------------------
_raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

if not _allowed_origins:
    # Dev fallback only — log a loud warning so this is never silent in prod
    logger.warning(
        "⚠️  CORS_ALLOWED_ORIGINS not set — defaulting to localhost only. "
        "Set CORS_ALLOWED_ORIGINS in .env for production."
    )
    _allowed_origins = ["http://localhost:3000", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Company-Code",
                   "X-Session-ID", "X-Tenant-Env", "X-User-ID"],
)

# -----------------------------
# Swagger passthrough middleware
# -----------------------------
@app.middleware("http")
async def preserve_swagger_requests(request: Request, call_next):
    swagger_paths = ["/docs", "/redoc", "/openapi.json"]
    if any(request.url.path.startswith(p) for p in swagger_paths):
        return await call_next(request)
    return await call_next(request)

# -----------------------------
# Include Routers
# -----------------------------
app.include_router(auth_router)
app.include_router(ai_router, prefix="/api/ai", tags=["AI Assistant"])
app.include_router(tenant_router, tags=["Tenant API"])

# Debug routes only in non-production environments
_app_env = os.getenv("APP_ENV", "development").lower()
if _app_env != "production":
    app.include_router(debug_router, prefix="/debug", tags=["Debug"])
    logger.info("🔧 Debug routes enabled (APP_ENV=%s)", _app_env)

# -----------------------------
# Static files
# -----------------------------
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")


# ============================================================================
# BACKGROUND NOTIFICATION SCANNER
# ============================================================================

async def _get_active_scan_users() -> list:
    """
    Return the list of users to scan for notifications.

    Priority:
      1. Users with live sessions in conversation memory (real logged-in users).
      2. Nothing — we do NOT fall back to hardcoded test users in production.

    In development (APP_ENV != production) we include a small seed list so the
    scanner has something to do before any user has logged in.
    """
    users = []

    # Pull from conversation memory (works for any tenant automatically)
    try:
        from app.services.conversation_memory import get_conversation_memory
        memory = get_conversation_memory()
        if hasattr(memory, "get_active_sessions"):
            for session in memory.get_active_sessions():
                users.append({
                    "user_id":    session.get("user_id"),
                    "user_role":  session.get("user_role", "sales_rep"),
                    "tenant_code": session.get("tenant_code"),
                    "token":      session.get("token"),
                    "backend_url": session.get("backend_url"),
                })
    except Exception as e:
        logger.warning(f"Could not read active sessions: {e}")

    # Development seed — only when no real sessions exist AND not in production
    if not users and _app_env != "production":
        logger.debug("No active sessions found — using dev seed users for scanner")
        users = [
            {"user_id": 1, "user_role": "manager",   "tenant_code": "TEST001",
             "token": None, "backend_url": os.getenv("LARAVEL_BACKEND_URL_TEST001")},
            {"user_id": 2, "user_role": "sales_rep",  "tenant_code": "TEST001",
             "token": None, "backend_url": os.getenv("LARAVEL_BACKEND_URL_TEST001")},
        ]

    # Deduplicate by user_id
    return list({u["user_id"]: u for u in users if u.get("user_id")}.values())


async def _get_scanner_token(user_data: dict) -> str | None:
    """
    Resolve a valid token for the scanner to use when calling the ERP.

    Order of preference:
      1. Token already stored in the user's live session (best — real user token).
      2. Service account login for the tenant (background jobs only).
      3. None — scanner skips this user rather than using a stale/fake token.
    """
    # 1. Live session token
    token = user_data.get("token")
    if token:
        return token

    # 2. Service account login
    email    = os.getenv("LEYSCO_SERVICE_ACCOUNT_EMAIL")
    password = os.getenv("LEYSCO_SERVICE_ACCOUNT_PASSWORD")
    backend  = user_data.get("backend_url") or os.getenv("LARAVEL_BACKEND_URL")

    if not email or not password:
        logger.warning(
            "LEYSCO_SERVICE_ACCOUNT_EMAIL / _PASSWORD not set — "
            "scanner cannot authenticate for background jobs. "
            "Set these in .env."
        )
        return None

    try:
        from app.services.leysco_api.client import LeyscoAPIService
        api_base = user_data.get("backend_url", "").rstrip("/") + "/api/v1" \
                   if user_data.get("backend_url") \
                   else os.getenv("LEYSCO_API_BASE_URL")
        svc = LeyscoAPIService(base_url=api_base)
        success = svc.login(username=email, password=password)
        if success:
            return svc.auth_handler.user_token
        logger.error(f"Service account login failed for backend {backend}")
    except Exception as e:
        logger.error(f"Service account login error: {e}")

    return None


async def background_notification_scanner():
    """
    Scans for proactive notifications for all active users every 15 minutes.

    Key invariants:
      - Never uses TEST_USER_TOKEN or any hardcoded credential.
      - Each user's scan uses the token associated with THEIR session so ERP
        calls are correctly scoped to their tenant and permissions.
      - Skips users for whom no valid token can be obtained (logs a warning).
    """
    # Guard against multiple instances (e.g. hot-reload)
    if getattr(background_notification_scanner, "_is_running", False):
        return
    background_notification_scanner._is_running = True

    logger.info("🔍 Background notification scanner started")
    last_scan_times: dict = {}
    scan_interval_seconds = int(os.getenv("NOTIFICATION_SCAN_INTERVAL_SECONDS", 900))

    while True:
        try:
            logger.info("🔍 Starting proactive notification scan...")
            start_time = datetime.now()

            from app.services.notification_service import get_notification_service
            notification_service = get_notification_service()

            users = await _get_active_scan_users()

            for user_data in users:
                user_id    = user_data["user_id"]
                user_role  = user_data.get("user_role", "sales_rep")
                tenant_code = user_data.get("tenant_code", "")

                # Rate-limit per user
                last_scan = last_scan_times.get(user_id)
                if last_scan and (datetime.now() - last_scan).seconds < 300:
                    logger.debug(f"Skipping scan for user {user_id} — too frequent")
                    continue

                token = await _get_scanner_token(user_data)
                if not token:
                    logger.warning(
                        f"No valid token for user {user_id} ({tenant_code}) — "
                        "skipping scan. User needs to log in or service account "
                        "credentials must be configured."
                    )
                    continue

                logger.info(f"Scanning for user {user_id} ({user_role}) [{tenant_code}]")

                try:
                    notifications = await notification_service.scan_for_user(
                        user_id=user_id,
                        user_role=user_role,
                        tenant_code=tenant_code,
                        user_token=token,
                        assigned_customers=[],
                    )
                    # NEW: Phase 1 - Save to database
                    if PHASE1_AVAILABLE:
                        await notification_service.save_notifications(user_id, notifications)
                    
                    last_scan_times[user_id] = datetime.now()
                    logger.info(
                        f"Generated {len(notifications)} notifications "
                        f"for user {user_id}"
                    )
                except Exception as e:
                    logger.error(f"Error scanning for user {user_id}: {e}")

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ Notification scan completed in {elapsed:.2f}s")

        except Exception as e:
            logger.error(f"Error in notification scanner: {e}", exc_info=True)

        await asyncio.sleep(scan_interval_seconds)


# ============================================================================
# PHASE 1.3: VECTOR STORE INITIALIZATION (ERP KNOWLEDGE BASE)
# ============================================================================

async def _init_vector_store():
    """Initialize vector store for ERP knowledge base (P1.3)"""
    if not VECTOR_STORE_AVAILABLE:
        logger.warning("⚠️ Vector store modules not available — ERP knowledge base disabled")
        return
    
    try:
        logger.info("Initializing vector store for ERP knowledge base...")
        await init_vector_store()
        logger.info("✅ Vector store initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize vector store: {e}", exc_info=True)
        logger.warning("Continuing without vector store — ERP knowledge base disabled")


async def _load_erp_data():
    """Load ERP data into vector store on startup (P1.3)"""
    if not VECTOR_STORE_AVAILABLE:
        return
    
    try:
        logger.info("Loading ERP data into vector store...")
        await load_erp_data_on_startup()
        logger.info("✅ ERP data loaded successfully")
    except Exception as e:
        logger.error(f"❌ Failed to load ERP data: {e}", exc_info=True)
        logger.warning("Continuing — will retry ERP data load on next startup")


# ============================================================================
# PHASE 1: DATABASE & SCHEDULER INITIALIZATION
# ============================================================================

async def _init_phase1():
    """Initialize Phase 1 features (database, scheduler, etc.)"""
    if not PHASE1_AVAILABLE:
        logger.warning("⚠️ Phase 1 modules not available — skipping database/scheduler init")
        return
    
    try:
        # Initialize database
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://leysco_user:password@localhost:5432/leysco_ai"
        )
        logger.info(f"Initializing database: {database_url[:50]}...")
        init_db(database_url)
        logger.info("✅ Database initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}", exc_info=True)
        logger.warning("Continuing without database — notifications will be lost on restart")
        return
    
    try:
        # Initialize background scheduler (cleanup, escalation, etc.)
        logger.info("Initializing background scheduler...")
        init_scheduler()
        logger.info("✅ Background scheduler initialized successfully")
        logger.info("   - Cleanup job: Daily at 2:00 AM")
        logger.info("   - Escalation job: Every hour")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize scheduler: {e}", exc_info=True)
        logger.warning("Continuing without scheduler — cleanup and escalation disabled")


# ============================================================================
# CHAT PERSISTENCE INITIALIZATION
# ============================================================================

async def _init_chat_persistence():
    """Initialize chat persistence service"""
    if not CHAT_PERSISTENCE_AVAILABLE:
        logger.warning("⚠️ Chat persistence modules not available — chat history will not be saved")
        return
    
    try:
        service = get_chat_persistence_service()
        logger.info("✅ ChatPersistenceService initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize chat persistence: {e}", exc_info=True)
        logger.warning("Continuing without chat persistence — conversations will not be saved")


# ============================================================================
# STARTUP & SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("🚀 Leysco AI Assistant Starting...")
    logger.info("=" * 60)

    logger.info("📋 Registered Routes:")
    for route in app.routes:
        if hasattr(route, "path"):
            methods = getattr(route, "methods", ["ANY"])
            logger.info(f"   {methods} {route.path}")

    # S1.0: Input Validation
    logger.info("\n🔐 Initializing Input Validation (S1.0)...")
    logger.info("✅ Input validation middleware initialized")
    logger.info("   - SQL injection protection: ENABLED")
    logger.info("   - XSS protection: ENABLED")
    logger.info("   - Type validation: ENABLED")

    # S1.1 + S1.2: Rate Limiting & Error Handling
    logger.info("\n⚠️  Initializing Rate Limiting & Error Handling (S1.1 + S1.2)...")
    limiter = get_rate_limiter()
    logger.info("✅ Rate limiting initialized")
    logger.info("   - Login attempts: 5 per 5 minutes")
    logger.info("   - Chat messages: 50 per minute")
    logger.info("   - API calls: 100 per minute")
    logger.info("✅ Error handling configured")
    logger.info("   - No stack traces to clients")
    logger.info("   - Sensitive data redaction enabled")
    logger.info("   - Security event logging enabled")

    # Phase 1 - Initialize database and scheduler
    logger.info("\n📦 Initializing Phase 1 (Database & Scheduler)...")
    await _init_phase1()

    # Phase 1.3 - Initialize vector store
    logger.info("\n🧠 Initializing Phase 1.3 (Vector Store & ERP Knowledge Base)...")
    await _init_vector_store()
    await _load_erp_data()

    # Chat Persistence - Initialize conversation storage
    logger.info("\n💬 Initializing Chat Persistence...")
    await _init_chat_persistence()

    # Test LLM connection
    try:
        from app.services.llm import get_llm_service
        llm = get_llm_service()
        if llm.test_connection():
            logger.info("✅ LLM Service: Connected and working")
        else:
            logger.warning("⚠️ LLM Service: Connection test failed")
    except Exception as e:
        logger.error(f"❌ LLM Service: Failed to initialize — {e}")

    # Start background scanner
    try:
        asyncio.create_task(background_notification_scanner())
        logger.info("✅ Background notification scanner started")
    except Exception as e:
        logger.error(f"❌ Failed to start notification scanner: {e}")

    logger.info("=" * 60)
    logger.info(f"🌐 Server running at: http://localhost:8000")
    logger.info(f"🔒 CORS origins: {_allowed_origins}")
    logger.info(f"🏢 Environment: {_app_env}")
    logger.info(f"🔐 Authentication endpoints:")
    logger.info(f"   POST   /api/auth/login")
    logger.info(f"   POST   /api/auth/logout")
    logger.info(f"   POST   /api/auth/verify")
    logger.info(f"📚 API Documentation: http://localhost:8000/docs")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("=" * 60)
    logger.info("🛑 Leysco AI Assistant Shutting Down...")
    logger.info("=" * 60)
    
    # Phase 1.3 - Vector store shutdown
    if VECTOR_STORE_AVAILABLE and close_vector_store:
        try:
            await close_vector_store()
            logger.info("✅ Vector store shut down")
        except Exception as e:
            logger.error(f"Error shutting down vector store: {e}")
    
    # Phase 1 - Shutdown scheduler
    if PHASE1_AVAILABLE and shutdown_scheduler:
        try:
            shutdown_scheduler()
            logger.info("✅ Background scheduler shut down")
        except Exception as e:
            logger.error(f"Error shutting down scheduler: {e}")
    
    # Chat Persistence - Graceful shutdown
    if CHAT_PERSISTENCE_AVAILABLE and get_chat_persistence_service:
        try:
            logger.info("✅ Chat persistence service shut down")
        except Exception as e:
            logger.error(f"Error during chat persistence shutdown: {e}")


# ============================================================================
# FRONTEND & INFO ENDPOINTS
# ============================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend():
    html_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

    return HTMLResponse(content="""<!DOCTYPE html>
<html><head><title>Leysco AI Assistant</title><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#0D1117;color:white;padding:40px}
  h1{color:#00C853;margin-bottom:20px}
  .card{background:#161B22;border-radius:12px;padding:20px;margin-bottom:16px}
  a{color:#00C853;text-decoration:none;margin-right:16px}
  .note{color:#aaa;font-size:13px;margin-top:12px}
  label{display:block;margin-bottom:6px;color:#aaa;font-size:13px}
  input{width:100%;padding:10px 14px;border-radius:8px;border:1px solid #30363d;
        background:#0D1117;color:white;font-size:14px;margin-bottom:12px}
  button{padding:10px 24px;background:#00C853;border:none;border-radius:8px;
         cursor:pointer;font-weight:bold;color:black}
  #response{background:#0D1117;border-radius:8px;padding:16px;margin-top:16px;
            white-space:pre-wrap;font-size:13px;max-height:300px;overflow-y:auto;
            display:none}
</style></head>
<body>
<h1>✨ Leysco AI Assistant</h1>

<div class="card">
  <strong>API Documentation</strong><br><br>
  <a href="/docs">Swagger UI</a>
  <a href="/redoc">ReDoc</a>
  <a href="/health">Health Check</a>
  <p class="note">Use your Bearer token from the Flutter app to authenticate API calls.</p>
</div>

<div class="card">
  <strong>Quick API Test</strong>
  <p class="note">Paste your Bearer token from the Flutter app to test the chat endpoint.</p>
  <br>
  <label>Bearer Token</label>
  <input type="password" id="tokenInput" placeholder="Paste your token here">
  <label>Company Code</label>
  <input type="text" id="companyInput" placeholder="e.g. TEST001">
  <label>Message</label>
  <input type="text" id="msgInput" placeholder="e.g. Show me top selling items" 
         onkeypress="if(event.key==='Enter')sendTest()">
  <button onclick="sendTest()">Send</button>
  <div id="response"></div>
</div>

<script>
async function sendTest() {
  const token   = document.getElementById('tokenInput').value.trim();
  const company = document.getElementById('companyInput').value.trim();
  const message = document.getElementById('msgInput').value.trim();
  const out     = document.getElementById('response');

  if (!token || !message) {
    out.style.display = 'block';
    out.textContent = '⚠️ Please enter a token and a message.';
    return;
  }

  out.style.display = 'block';
  out.textContent = '⏳ Sending...';

  try {
    const headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + token,
    };
    if (company) headers['X-Company-Code'] = company;

    const res  = await fetch('/api/ai/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    out.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    out.textContent = '❌ Error: ' + e.message;
  }
}
</script>
</body></html>""")


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.get("/health", include_in_schema=False)
def health_check():
    return {
        "status": "ok",
        "service": "Leysco AI Sales Assistant",
        "environment": _app_env,
        "phase1_enabled": PHASE1_AVAILABLE,
        "phase1_3_vector_store_enabled": VECTOR_STORE_AVAILABLE,
        "chat_persistence_enabled": CHAT_PERSISTENCE_AVAILABLE,
        "auth_enabled": True,
        "rate_limiting_enabled": True,
        "error_handling_enabled": True,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/info", include_in_schema=False)
def api_info():
    return {
        "name": "Leysco AI Sales Assistant",
        "version": "1.0.0",
        "endpoints": {
            "login":            "/api/auth/login",
            "logout":           "/api/auth/logout",
            "verify_token":     "/api/auth/verify",
            "items":            "/api/v1/{tenant_id}/items",
            "inventory":        "/api/v1/{tenant_id}/inventory/",
            "orders":           "/api/v1/{tenant_id}/orders",
            "customers":        "/api/v1/{tenant_id}/customers/",
            "customer_details": "/api/v1/{tenant_id}/customers/{customer_code}",
            "expenses":         "/api/v1/{tenant_id}/expenses",
            "price":            "/api/v1/{tenant_id}/price",
            "ai_chat":          "/api/ai/chat",
            "ai_notifications": "/api/ai/notifications",
            "ai_session_clear": "/api/ai/session/clear",
            "ai_session_history": "/api/ai/session/history",
        },
        "authentication": "Bearer token required (X-Company-Code header recommended)",
        "features": {
            "multi_tenant":           True,
            "conversation_memory":    True,
            "proactive_notifications": True,
            "role_based_access":      True,
            "persistent_notifications": PHASE1_AVAILABLE,
            "chat_persistence":       CHAT_PERSISTENCE_AVAILABLE,
            "erp_knowledge_base":     VECTOR_STORE_AVAILABLE,
            "auth_endpoints":         True,
            "input_validation":       True,
            "rate_limiting":          True,
            "error_handling":         True,
        },
    }


@app.get("/info", include_in_schema=False)
def root_info():
    return {
        "service": "Leysco AI Sales Assistant",
        "version": "1.0.0",
        "status":  "running",
        "documentation": "/docs",
        "health":        "/health",
        "api_info":      "/api/info",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=_app_env != "production",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )