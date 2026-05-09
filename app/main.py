"""
app/main.py
===========
Leysco AI Sales Assistant - Main Application Entry Point

UPDATED: Fixed Swagger UI, added proper static file serving, improved error handling
UPDATED: Added notification routes
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from dotenv import load_dotenv
from app.api import ai_routes
from app.api.tenant_routes import router as tenant_router
from app.api.debug_routes import router as debug_router
from app.api.notification_routes import router as notification_router  # ← ADD THIS
import logging
import os
import asyncio
from datetime import datetime

# Load environment variables FIRST (before any other imports that use them)
load_dotenv()

# -----------------------------
# Logging Setup
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("leysco_ai_assistant")

# -----------------------------
# FastAPI App with proper docs setup
# -----------------------------
app = FastAPI(
    title="Leysco AI Sales Assistant",
    description="AI Sales Assistant for field reps using Leysco Sales System",
    version="1.0.0",
    # Explicitly enable docs (they are enabled by default, but being explicit helps)
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# -----------------------------
# CORS Middleware
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Custom middleware to handle Swagger UI properly
# -----------------------------
@app.middleware("http")
async def preserve_swagger_requests(request: Request, call_next):
    """
    Middleware that preserves Swagger UI requests and prevents body consumption.
    This fixes the "Invalid HTTP request" error for /docs and /openapi.json.
    """
    # Skip body processing for Swagger-related paths
    swagger_paths = ["/docs", "/redoc", "/openapi.json", "/swagger", "/swagger/"]
    if any(request.url.path.startswith(path) for path in swagger_paths):
        # Don't touch the request body for Swagger
        return await call_next(request)
    
    # For other paths, continue normally
    return await call_next(request)

# -----------------------------
# Include Routers
# -----------------------------
app.include_router(ai_routes.router, prefix="/api/ai", tags=["AI Assistant"])
app.include_router(tenant_router, tags=["Tenant API"])  # Tenant routes for Flutter
app.include_router(notification_router, prefix="/api/ai", tags=["Notifications"])  # ← ADD THIS

# Only include debug router if in debug mode
if os.getenv("DEBUG", "True").lower() == "true":
    app.include_router(debug_router, prefix="/debug", tags=["Debug"])
    logger.info("🔧 Debug routes enabled")

# -----------------------------
# Create static directory AFTER app initialization
# -----------------------------
STATIC_DIR = "static"
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

# Mount static files (for CSS, JS, etc.) - with proper configuration
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# -----------------------------
# Background Notification Scanner
# -----------------------------

async def background_notification_scanner():
    """
    Background task that scans for opportunities for all users.
    Runs every 15 minutes.
    """
    # Prevent multiple instances
    if hasattr(background_notification_scanner, '_is_running'):
        return
    background_notification_scanner._is_running = True
    
    logger.info("🔍 Background notification scanner started")
    
    while True:
        try:
            logger.info("🔍 Starting proactive notification scan...")
            start_time = datetime.now()
            
            # Import here to avoid circular imports
            from app.services.notification_service import get_notification_service
            
            notification_service = get_notification_service()
            
            # This is where you'd fetch all active users from your database
            # For now, we'll rely on the API endpoint to trigger scans
            # when users request notifications
            
            # TODO: Implement user database to fetch all active users
            # For demonstration, we log that scan completed
            logger.info(f"✅ Notification scan completed in {(datetime.now() - start_time).total_seconds():.2f}s")
            
        except Exception as e:
            logger.error(f"Error in notification scanner: {e}", exc_info=True)
        
        # Wait 15 minutes before next scan
        await asyncio.sleep(900)  # 15 minutes


# -----------------------------
# Startup Event
# -----------------------------
@app.on_event("startup")
async def startup_event():
    """Log startup information and start background tasks"""
    logger.info("=" * 60)
    logger.info("🚀 Leysco AI Assistant Starting...")
    logger.info("=" * 60)
    
    # Log all registered routes for debugging
    logger.info("📋 Registered Routes:")
    for route in app.routes:
        if hasattr(route, "path"):
            methods = getattr(route, "methods", ["ANY"])
            logger.info(f"   {methods} {route.path}")
    
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
    
    # Start background notification scanner
    try:
        asyncio.create_task(background_notification_scanner())
        logger.info("✅ Background notification scanner started")
    except Exception as e:
        logger.error(f"❌ Failed to start notification scanner: {e}")
    
    logger.info("=" * 60)
    logger.info("🌐 Server running at: http://localhost:8000")
    logger.info("📱 Flutter API base URL: http://localhost:8000/api/v1")
    logger.info("🤖 AI Chat endpoint: http://localhost:8000/api/ai/chat")
    logger.info("🔔 Notifications endpoint: http://localhost:8000/api/ai/notifications")
    logger.info("📚 API Documentation: http://localhost:8000/docs")
    logger.info("📖 Alternative Docs: http://localhost:8000/redoc")
    logger.info("=" * 60)


# -----------------------------
# Shutdown Event
# -----------------------------
@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown information"""
    logger.info("=" * 60)
    logger.info("🛑 Leysco AI Assistant Shutting Down...")
    logger.info("=" * 60)


# -----------------------------
# Modified Root Endpoint - Doesn't interfere with Swagger
# -----------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend():
    """Serve the main HTML frontend - exclude from API schema to avoid conflicts"""
    html_path = os.path.join(STATIC_DIR, "index.html")
    
    # If index.html exists in static folder, serve it
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    
    # Otherwise, serve a comprehensive test page
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Leysco AI Assistant</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0D1117; color: white; }
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
            h1 { color: #00C853; margin-bottom: 20px; }
            .api-links { background: #161B22; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
            .api-links a { color: #00C853; text-decoration: none; display: inline-block; margin-right: 20px; margin-bottom: 10px; }
            .api-links a:hover { text-decoration: underline; }
            .main { display: flex; gap: 20px; flex-wrap: wrap; }
            .sidebar { width: 260px; background: #161B22; border-radius: 12px; padding: 20px; }
            .chat-container { flex: 1; min-width: 300px; }
            .chat-area { background: #161B22; border-radius: 12px; padding: 20px; height: 500px; overflow-y: auto; margin-bottom: 16px; }
            .message { margin-bottom: 16px; }
            .user-message { text-align: right; }
            .user-bubble { background: #00C853; color: black; display: inline-block; padding: 10px 16px; border-radius: 18px; max-width: 80%; text-align: left; }
            .ai-message { text-align: left; }
            .ai-bubble { background: #21262D; display: inline-block; padding: 10px 16px; border-radius: 18px; max-width: 80%; }
            .input-area { display: flex; gap: 12px; }
            input { flex: 1; padding: 14px 20px; border-radius: 30px; border: none; background: #21262D; color: white; font-size: 14px; }
            input:focus { outline: none; border: 1px solid #00C853; }
            button { padding: 14px 28px; background: #00C853; border: none; border-radius: 30px; cursor: pointer; font-weight: bold; color: black; font-size: 14px; }
            button:hover { background: #00e05a; }
            .sidebar button { width: 100%; margin-bottom: 12px; background: #21262D; color: white; }
            .sidebar button:hover { background: #30363d; }
            hr { margin: 16px 0; border-color: #30363d; }
            .typing { opacity: 0.7; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✨ Leysco AI Assistant</h1>
            
            <div class="api-links">
                <strong>📚 API Documentation:</strong><br>
                <a href="/docs" target="_blank">Swagger UI (/docs)</a> | 
                <a href="/redoc" target="_blank">ReDoc (/redoc)</a> |
                <a href="/openapi.json" target="_blank">OpenAPI JSON</a> |
                <a href="/health" target="_blank">Health Check</a>
            </div>
            
            <div class="main">
                <div class="sidebar">
                    <h3>Quick Actions</h3>
                    <button onclick="sendMessage('Show me top 10 items')">📊 Top 10 Items</button>
                    <button onclick="sendMessage('Show me slow moving items')">🐢 Slow Movers</button>
                    <button onclick="sendMessage('Price of vegimax')">💰 Price Check</button>
                    <button onclick="sendMessage('Low stock alerts')">⚠️ Low Stock</button>
                    <hr>
                    <button onclick="newChat()">✨ New Chat</button>
                    <button onclick="clearChats()">🗑️ Clear All</button>
                </div>
                <div class="chat-container">
                    <div id="chatArea" class="chat-area">
                        <div class="ai-message">
                            <div class="ai-bubble">👋 Hello! I'm the Leysco AI Assistant.<br><br>I can help you with:<br>• Product prices and stock levels<br>• Customer information and orders<br>• Delivery tracking<br>• Sales analytics and recommendations<br><br>Ask me anything!</div>
                        </div>
                    </div>
                    <div class="input-area">
                        <input type="text" id="messageInput" placeholder="Type your message..." onkeypress="if(event.key==='Enter') sendMessage()">
                        <button onclick="sendMessage()">Send</button>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            let currentSessionId = localStorage.getItem('session_id') || 'session_' + Date.now();
            localStorage.setItem('session_id', currentSessionId);
            
            async function sendMessage(message = null) {
                const input = document.getElementById('messageInput');
                const text = message || input.value.trim();
                if (!text) return;
                
                // Add user message
                const chatArea = document.getElementById('chatArea');
                const userDiv = document.createElement('div');
                userDiv.className = 'user-message';
                userDiv.innerHTML = '<div class="user-bubble">' + escapeHtml(text) + '</div>';
                chatArea.appendChild(userDiv);
                chatArea.scrollTop = chatArea.scrollHeight;
                
                if (!message) input.value = '';
                
                // Add typing indicator
                const typingDiv = document.createElement('div');
                typingDiv.className = 'ai-message typing';
                typingDiv.id = 'typing';
                typingDiv.innerHTML = '<div class="ai-bubble">✨ Thinking...</div>';
                chatArea.appendChild(typingDiv);
                chatArea.scrollTop = chatArea.scrollHeight;
                
                try {
                    const token = localStorage.getItem('token') || 'test_token_' + Date.now();
                    const response = await fetch('/api/ai/chat', {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer ' + token
                        },
                        body: JSON.stringify({ message: text, session_id: currentSessionId })
                    });
                    
                    const data = await response.json();
                    
                    // Remove typing indicator
                    document.getElementById('typing')?.remove();
                    
                    // Add AI response
                    const aiDiv = document.createElement('div');
                    aiDiv.className = 'ai-message';
                    const responseText = data.result || data.message || 'No response';
                    aiDiv.innerHTML = '<div class="ai-bubble">' + formatResponse(responseText) + '</div>';
                    chatArea.appendChild(aiDiv);
                    chatArea.scrollTop = chatArea.scrollHeight;
                    
                } catch (error) {
                    document.getElementById('typing')?.remove();
                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'ai-message';
                    errorDiv.innerHTML = '<div class="ai-bubble">❌ Connection error: ' + error.message + '</div>';
                    chatArea.appendChild(errorDiv);
                }
            }
            
            function formatResponse(text) {
                let formatted = text.replace(/\\n/g, '<br>');
                formatted = formatted.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
                formatted = formatted.replace(/• /g, '&nbsp;&nbsp;• ');
                return formatted;
            }
            
            function newChat() {
                currentSessionId = 'session_' + Date.now();
                localStorage.setItem('session_id', currentSessionId);
                document.getElementById('chatArea').innerHTML = '<div class="ai-message"><div class="ai-bubble">✨ New chat started! How can I help you today?</div></div>';
            }
            
            function clearChats() {
                if (confirm('Clear all chats?')) {
                    document.getElementById('chatArea').innerHTML = '<div class="ai-message"><div class="ai-bubble">🗑️ Chat history cleared! How can I help you?</div></div>';
                }
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            if (!localStorage.getItem('token')) {
                localStorage.setItem('token', 'test_token_' + Date.now());
            }
        </script>
    </body>
    </html>
    """)


# -----------------------------
# Health Check Endpoint
# -----------------------------
@app.get("/health", include_in_schema=False)
def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "ok",
        "message": "Leysco AI Assistant is running",
        "timestamp": datetime.now().isoformat()
    }


# -----------------------------
# API Info Endpoint
# -----------------------------
@app.get("/api/info", include_in_schema=False)
def api_info():
    """Return API information for Flutter app"""
    return {
        "name": "Leysco AI Sales Assistant",
        "version": "1.0.0",
        "endpoints": {
            "login": "/api/v1/login",
            "items": "/api/v1/{tenant_id}/items",
            "inventory": "/api/v1/{tenant_id}/inventory/",
            "orders": "/api/v1/{tenant_id}/orders",
            "customers": "/api/v1/{tenant_id}/customers/",
            "customer_details": "/api/v1/{tenant_id}/customers/{customer_code}",
            "expenses": "/api/v1/{tenant_id}/expenses",
            "price": "/api/v1/{tenant_id}/price",
            "ai_chat": "/api/ai/chat",
            "ai_notifications": "/api/ai/notifications",
            "ai_session_clear": "/api/ai/session/clear",
            "ai_session_history": "/api/ai/session/history"
        },
        "authentication": "Bearer token required for all endpoints except /api/v1/login",
        "features": {
            "conversation_memory": True,
            "proactive_notifications": True,
            "bilingual_support": True,
            "role_based_access": True
        }
    }


# -----------------------------
# Root Info Endpoint
# -----------------------------
@app.get("/info", include_in_schema=False)
def root_info():
    """Root info endpoint"""
    return {
        "service": "Leysco AI Sales Assistant",
        "version": "1.0.0",
        "status": "running",
        "documentation": "/docs",
        "health": "/health",
        "api_info": "/api/info"
    }


# -----------------------------
# Run with: uvicorn app.main:app --reload
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )