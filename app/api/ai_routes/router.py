"""Main router that includes all AI-related endpoints"""

from fastapi import APIRouter
from .chat import router as chat_router
from .quotation_endpoints import router as quotation_router
from .session_endpoints import router as session_router
from .notification_endpoints import router as notification_router
from .proactive_endpoints import router as proactive_router
from .analytics_endpoints import router as analytics_router
from .feedback_endpoints import router as feedback_router
from .forecast_endpoints import router as forecast_router
from .anomaly_endpoints import router as anomaly_router
from .knowledge_endpoints import router as knowledge_router
from .graph_endpoints import router as graph_router
from .dashboard_endpoints import router as dashboard_router

# Create main router
router = APIRouter()

# Include all sub-routers with their tags
router.include_router(chat_router, tags=["AI Chat"])
router.include_router(quotation_router, tags=["Quotations"])
router.include_router(session_router, tags=["Session Management"])
router.include_router(notification_router, tags=["Notifications"])
router.include_router(proactive_router, tags=["Proactive Suggestions"])
router.include_router(analytics_router, tags=["Analytics"])
router.include_router(feedback_router, tags=["Feedback"])
router.include_router(forecast_router, tags=["ML Forecasting"])
router.include_router(anomaly_router, tags=["Anomaly Detection"])
router.include_router(knowledge_router, tags=["Knowledge Base"])
router.include_router(graph_router, tags=["Knowledge Graph"])
router.include_router(dashboard_router, tags=["Dashboard"])

__all__ = ['router']