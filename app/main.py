from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from app.api import ai_routes
from app.api.debug_routes import router as debug_router
import logging
import os

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
# Include Routers
# -----------------------------
app.include_router(ai_routes.router, prefix="/api/ai", tags=["AI Assistant"])
app.include_router(debug_router,     prefix="/debug",  tags=["Debug"])

# -----------------------------
# Serve Frontend HTML
# -----------------------------
# Create a static directory if it doesn't exist
STATIC_DIR = "static"
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

# Mount static files (for CSS, JS, etc.)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main HTML frontend"""
    html_path = os.path.join(STATIC_DIR, "index.html")
    
    # If index.html exists in static folder, serve it
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    
    # Otherwise, serve a simple test page
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Leysco AI Assistant</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial; background: #0D1117; color: white; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            .chat-area { background: #161B22; border-radius: 12px; padding: 20px; height: 400px; overflow-y: auto; margin-bottom: 20px; }
            .message { margin-bottom: 16px; }
            .user-message { text-align: right; }
            .user-bubble { background: #00C853; color: black; display: inline-block; padding: 10px 16px; border-radius: 18px; max-width: 70%; }
            .ai-message { text-align: left; }
            .ai-bubble { background: #21262D; display: inline-block; padding: 10px 16px; border-radius: 18px; max-width: 70%; }
            input { width: 80%; padding: 12px; border-radius: 30px; border: none; background: #21262D; color: white; }
            button { padding: 12px 24px; background: #00C853; border: none; border-radius: 30px; cursor: pointer; font-weight: bold; }
            .sidebar { width: 250px; float: left; background: #161B22; padding: 20px; border-radius: 12px; margin-right: 20px; }
            .main { display: flex; }
            .chat-container { flex: 1; }
            h2 { color: #00C853; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✨ Leysco AI Assistant</h1>
            <div class="main">
                <div class="sidebar">
                    <h3>Quick Actions</h3>
                    <button onclick="sendMessage('Show me top 10 items')">Top 10 Items</button><br><br>
                    <button onclick="sendMessage('Show me slow moving items')">Slow Movers</button><br><br>
                    <button onclick="sendMessage('Price of vegimax')">Price Check</button><br><br>
                    <button onclick="sendMessage('Low stock alerts')">Low Stock</button><br><br>
                    <hr>
                    <button onclick="newChat()">New Chat</button>
                    <button onclick="clearChats()">Clear All</button>
                </div>
                <div class="chat-container">
                    <div id="chatArea" class="chat-area">
                        <div class="ai-message"><div class="ai-bubble">👋 Hello! I'm the Leysco AI Assistant. Ask me anything about products, pricing, or inventory!</div></div>
                    </div>
                    <div>
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
                typingDiv.className = 'ai-message';
                typingDiv.id = 'typing';
                typingDiv.innerHTML = '<div class="ai-bubble">✨ Thinking...</div>';
                chatArea.appendChild(typingDiv);
                chatArea.scrollTop = chatArea.scrollHeight;
                
                try {
                    const response = await fetch('/api/ai/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: text, session_id: currentSessionId })
                    });
                    
                    const data = await response.json();
                    
                    // Remove typing indicator
                    document.getElementById('typing')?.remove();
                    
                    // Add AI response
                    const aiDiv = document.createElement('div');
                    aiDiv.className = 'ai-message';
                    aiDiv.innerHTML = '<div class="ai-bubble">' + escapeHtml(data.result || data.message || 'No response') + '</div>';
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
            
            function newChat() {
                currentSessionId = 'session_' + Date.now();
                localStorage.setItem('session_id', currentSessionId);
                document.getElementById('chatArea').innerHTML = '<div class="ai-message"><div class="ai-bubble">👋 New chat started! How can I help you today?</div></div>';
            }
            
            function clearChats() {
                if (confirm('Clear all chats?')) {
                    document.getElementById('chatArea').innerHTML = '<div class="ai-message"><div class="ai-bubble">👋 Chat history cleared! How can I help you?</div></div>';
                }
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
        </script>
    </body>
    </html>
    """)

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