"""Core routing logic for AI intent handling

This module contains the main _route_async function which implements
the 5-tier routing system:
- Tier 1: Fast conversational responses (greeting, thanks, small talk)
- Tier 1: Knowledge base responses
- Tier 2: Delivery tracking
- Tier 3: Decision support (analytics, forecasting, recommendations)
- Tier 4: Database queries with LLM narration
- Tier 5: Action router (business operations)
"""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import logging

from .schemas import AIResponse
from .suggestion_handlers import get_suggestions_with_feedback, legacy_format, format_delivery_response
from .utils import create_summary_from_analysis, ensure_utf8_string
from .constants import (
    KNOWLEDGE_BASE_INTENTS,
    DELIVERY_INTENTS,
    DECISION_SUPPORT_INTENTS,
    ACTION_ROUTER_INTENTS,
    PRICE_INTENTS,
    RECOMMENDATION_INTENTS,
    MANAGER_ONLY_INTENTS
)
from .rag_handlers import enhance_with_rag

from app.ai_engine.action_router import create_action_router
from app.ai_engine.decision_support import DecisionSupport
from app.ai_engine.response_formatter import ResponseFormatter
from app.services.db_query import create_db_query_service
from app.services.pricing_service import create_pricing_service
from app.services.conversation_memory import get_conversation_memory

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTION TO ENSURE DATA IS ALWAYS A LIST
# ============================================================================

def _ensure_list(data: Any) -> List[Any]:
    """
    Ensure data is a list (wrap dict in list, convert None to empty list).
    
    This prevents the ValidationError that occurs when AIResponse expects
    a list but receives a dict or None.
    
    Args:
        data: Input data (could be dict, list, None, or other)
        
    Returns:
        List version of the data
    """
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    # For other types (str, int, etc.), wrap in list
    return [data] if data else []


# ============================================================================
# CUSTOMER BEHAVIOR RESPONSE FORMATTER
# ============================================================================

def _format_customer_behavior_response(data: dict, language: str) -> str:
    """Format customer behavior analysis response in a user-friendly way."""
    
    customer = data.get("customer", {})
    customer_name = customer.get("name", "Customer")
    
    # Build the response
    lines = []
    
    # Header
    if language == "sw":
        lines.append(f"📊 **Uchambuzi wa Tabia za Mteja: {customer_name}**\n")
    else:
        lines.append(f"📊 **Customer Behavior Analysis: {customer_name}**\n")
    
    # Customer Info
    lines.append("**Customer Information:**")
    lines.append(f"• Name: {customer_name}")
    if customer.get("code"):
        lines.append(f"• Code: {customer.get('code')}")
    if customer.get("phone") and customer.get("phone") != "Unknown" and customer.get("phone") != "N/A":
        lines.append(f"• Phone: {customer.get('phone')}")
    if customer.get("city") and customer.get("city") != "Unknown":
        lines.append(f"• City: {customer.get('city')}")
    if customer.get("since") and customer.get("since") != "Unknown":
        lines.append(f"• Customer Since: {customer.get('since')}")
    if customer.get("email") and customer.get("email") != "Unknown" and customer.get("email") != "N/A":
        lines.append(f"• Email: {customer.get('email')}")
    
    # Purchase Patterns
    purchase_patterns = data.get("purchase_patterns", {})
    if purchase_patterns and any(purchase_patterns.values()):
        lines.append("\n**🛒 Purchase Patterns:**")
        
        # Average order value
        avg_order = purchase_patterns.get("average_order_value")
        if avg_order and avg_order > 0:
            lines.append(f"• Average Order Value: KES {avg_order:,.2f}")
        
        # Order frequency
        frequency = purchase_patterns.get("order_frequency_days")
        if frequency and frequency > 0:
            lines.append(f"• Order Frequency: Every {frequency} days")
        
        # Last order
        last_order = purchase_patterns.get("last_order_date")
        if last_order and last_order != "Never":
            lines.append(f"• Last Order: {last_order}")
        
        # Total orders
        total_orders = purchase_patterns.get("total_orders")
        if total_orders and total_orders > 0:
            lines.append(f"• Total Orders: {total_orders}")
    
    # RFM Score
    rfm = data.get("rfm_score", {})
    if rfm and any(rfm.values()):
        lines.append("\n**⭐ RFM Score Analysis:**")
        if rfm.get("recency"):
            lines.append(f"• Recency: {rfm.get('recency')}/5")
        if rfm.get("frequency"):
            lines.append(f"• Frequency: {rfm.get('frequency')}/5")
        if rfm.get("monetary"):
            lines.append(f"• Monetary: {rfm.get('monetary')}/5")
        if rfm.get("overall"):
            lines.append(f"• Overall Score: {rfm.get('overall')}/15 ({rfm.get('segment', 'N/A')})")
    
    # Risk Factors
    risk_factors = data.get("risk_factors", [])
    if risk_factors:
        lines.append("\n**⚠️ Risk Factors:**")
        for risk in risk_factors:
            lines.append(f"• {risk}")
    
    # Recommendations
    recommendations = data.get("recommendations", [])
    if recommendations:
        lines.append("\n**💡 Recommendations:**")
        for rec in recommendations[:5]:  # Top 5
            lines.append(f"• {rec}")
    
    # Upsell Opportunities
    upsell = data.get("upsell_opportunities", [])
    if upsell:
        lines.append("\n**📈 Upsell Opportunities:**")
        for opp in upsell[:3]:  # Top 3
            lines.append(f"• {opp}")
    
    # Next Best Actions
    next_actions = data.get("next_best_actions", [])
    if next_actions:
        lines.append("\n**🎯 Next Best Actions:**")
        for action in next_actions[:3]:
            priority = action.get("priority", "MEDIUM")
            action_text = action.get("action", "")
            priority_icon = "🔴" if priority == "HIGH" else "🟡" if priority == "MEDIUM" else "🟢"
            lines.append(f"• {priority_icon} [{priority}] {action_text}")
    
    # Footer
    lines.append("\n---")
    lines.append("💬 Need more details? Just ask!")
    
    return "\n".join(lines)


async def route_async(
    intent: str,
    entities: dict,
    message: str,
    language: str,
    session_id: str,
    user_token: str,
    llm,
    formatter: ResponseFormatter,
    context: Dict = None,
    assigned_customers: List[str] = None,
    user_role: str = "sales_rep",
    company_code: str = None
) -> AIResponse:
    """Async routing with proper await, user token, context awareness, and permissions.
    
    Implements 5-tier routing system:
    1. Fast conversational responses
    2. Knowledge base with RAG
    3. Delivery tracking
    4. Decision support (manager-only for some)
    5. Database queries with LLM narration
    6. Action router for business operations
    
    Args:
        intent: Detected intent
        entities: Extracted entities
        message: Original user message
        language: Detected language (en/sw)
        session_id: Current session ID
        user_token: Authenticated user's Bearer token
        llm: LLM service instance
        formatter: Response formatter
        context: Conversation context
        assigned_customers: List of customers assigned to sales rep
        user_role: User's role (manager/sales_rep)
        company_code: Company code for multi-tenant URL resolution
    """
    
    # Add assigned customers filter for sales reps
    if user_role == "sales_rep" and assigned_customers:
        entities["_assigned_customers"] = assigned_customers
        logger.info(f"Applying assigned customers filter for sales rep: {len(assigned_customers)} customers")
    
    # Create per-request services with user token and company code
    action_router = create_action_router(
        user_token=user_token,
        company_code=company_code
    )
    pricing_service = create_pricing_service(
        user_token=user_token,
        company_code=company_code
    )
    db = create_db_query_service(
        user_token=user_token,
        company_code=company_code
    )
    
    decision_support = DecisionSupport(
        api=action_router.api,
        pricing=pricing_service,
        warehouse=action_router.warehouse,
        recommender=action_router.recommender,
    )
    
    memory = get_conversation_memory()
    
    # ========================================================================
    # TIER 1: Fast conversational responses
    # ========================================================================
    
    if intent == "GREETING":
        return _handle_greeting(language, intent, entities, context, session_id)
    
    if intent == "THANKS":
        return _handle_thanks(language, intent, entities, context, session_id)
    
    if intent == "SMALL_TALK":
        return await _handle_small_talk(message, language, intent, entities, context, session_id, llm)
    
    # ========================================================================
    # TIER 1: Knowledge base with RAG
    # ========================================================================
    
    if intent in KNOWLEDGE_BASE_INTENTS:
        logger.info(f"Tier 1 — Knowledge base: {intent}")
        return await _handle_knowledge_base(
            message, intent, language, entities, context, session_id, llm
        )
    
    # ========================================================================
    # TIER 2: Delivery tracking
    # ========================================================================
    
    if intent in DELIVERY_INTENTS:
        logger.info(f"Tier 2 — Delivery tracking: {intent}")
        return await _handle_delivery_tracking(
            intent, entities, message, language, db, formatter, context, session_id, llm
        )
    
    # ========================================================================
    # TIER 3: Decision support (Manager-only for some intents)
    # ========================================================================
    
    if intent in DECISION_SUPPORT_INTENTS:
        logger.info(f"Tier 3 — Decision support: {intent}")
        return await _handle_decision_support(
            intent, entities, message, language, user_role, 
            decision_support, formatter, context, session_id, llm
        )
    
    # ========================================================================
    # TIER 4: Database query with LLM narration
    # ========================================================================
    
    if intent not in ACTION_ROUTER_INTENTS:
        logger.info(f"Tier 4 — DB query + narrate: {intent}")
        return await _handle_db_query(
            intent, entities, message, language, db, formatter, context, session_id, llm
        )
    
    # ========================================================================
    # TIER 5: Action router (business operations)
    # ========================================================================
    
    logger.info(f"Tier 5 — Action router: {intent}")
    return await _handle_action_router(
        intent, entities, message, language, action_router, formatter, context, session_id
    )


# ============================================================================
# TIER 1 HANDLERS
# ============================================================================

def _handle_greeting(language: str, intent: str, entities: dict, context: Dict, session_id: str) -> AIResponse:
    """Handle greeting intent."""
    if language == "sw":
        msg = "Habari! Mimi ni Msaidizi wa AI wa Leysco. Ninaweza kukusaidia na bei za bidhaa, hisa, wateja, maagizo, na zaidi. Unahitaji nini?"
    else:
        msg = "Hello! I'm the Leysco AI Assistant. I can help you with items, pricing, stock levels, customers, orders, and more. What would you like to know?"
    
    return AIResponse(
        intent=intent,
        entities=entities,
        result=msg,
        data=[],
        suggestions=[],
        session_id=session_id,
    )


def _handle_thanks(language: str, intent: str, entities: dict, context: Dict, session_id: str) -> AIResponse:
    """Handle thanks intent."""
    if language == "sw":
        msg = "Karibu sana! Niambie kama una swali lingine lolote."
    else:
        msg = "You're welcome! Let me know if there's anything else I can help you with."
    
    return AIResponse(
        intent=intent,
        entities=entities,
        result=msg,
        data=[],
        suggestions=[],
        session_id=session_id,
    )


async def _handle_small_talk(
    message: str, language: str, intent: str, entities: dict, 
    context: Dict, session_id: str, llm
) -> AIResponse:
    """Handle small talk intent with LLM."""
    answer = await llm.generate_async(
        f"The user sent a short conversational message: \"{message}\"\n"
        f"Reply naturally and briefly as the Leysco AI Assistant.",
        intent="GENERAL",
        max_tokens=80,
        language=language,
    )
    
    return AIResponse(
        intent=intent,
        entities=entities,
        result=answer,
        data=[],
        suggestions=[],
        session_id=session_id,
    )


async def _handle_knowledge_base(
    message: str, intent: str, language: str, entities: dict,
    context: Dict, session_id: str, llm
) -> AIResponse:
    """Handle knowledge base intent with RAG enhancement."""
    # Try RAG enhancement
    rag_context = await enhance_with_rag(message, None)
    
    if rag_context:
        prompt = f"""You are the Leysco AI Assistant. Use the following information to answer the user's question.
        
RELEVANT INFORMATION:
{rag_context}

USER QUESTION: {message}

Answer based on the information above. If the information doesn't contain the answer, say so politely.
"""
    else:
        prompt = f"User asked: {message}"
    
    answer = await llm.generate_async(
        prompt,
        intent=intent,
        language=language,
        max_tokens=500,
    )
    
    return AIResponse(
        intent=intent,
        entities=entities,
        result=answer,
        data=[],
        suggestions=[],
        session_id=session_id,
    )


# ============================================================================
# TIER 2 HANDLERS
# ============================================================================

async def _handle_delivery_tracking(
    intent: str, entities: dict, message: str, language: str,
    db, formatter: ResponseFormatter, context: Dict, session_id: str, llm
) -> AIResponse:
    """Handle delivery tracking intents."""
    # Validate delivery number for TRACK_DELIVERY
    if intent == "TRACK_DELIVERY":
        delivery_number = entities.get("delivery_number") or entities.get("doc_num")
        if not delivery_number:
            if language == "sw":
                msg = "Tafadhali toa namba ya usafirishaji. Kwa mfano: 'fuatilia delivery #10045'"
            else:
                msg = "Please provide a delivery number. For example: 'track delivery #10045'"
            return AIResponse(
                intent=intent,
                entities=entities,
                result=msg,
                data=[],
                suggestions=["track delivery 10045", "check order status"],
                session_id=session_id,
            )
    
    # Query the database
    rows = db.query(intent=intent, entities=entities, language=language)
    
    if rows is None or not rows:
        answer = await llm.generate_async(
            f"User asked about deliveries: {message}",
            intent=intent,
            language=language,
            max_tokens=300,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=[],
            session_id=session_id,
        )
    
    # Use formatter for outstanding deliveries
    if intent == "GET_OUTSTANDING_DELIVERIES":
        formatted = formatter.format_outstanding_deliveries(rows, language)
        return AIResponse(
            intent=intent,
            entities=entities,
            result=formatted.get("message", ""),
            data=_ensure_list(formatted.get("data", rows)),
            suggestions=[],
            session_id=session_id,
        )
    
    # For other delivery intents
    if isinstance(rows, list) and len(rows) > 0:
        result_message = format_delivery_response(rows[0] if len(rows) == 1 else rows, intent, language, formatter)
        return AIResponse(
            intent=intent,
            entities=entities,
            result=result_message,
            data=_ensure_list(rows),
            suggestions=[],
            session_id=session_id,
        )
    
    answer = await llm.narrate_async(
        question=message,
        db_rows=rows,
        intent=intent,
        language=language,
        max_tokens=400,
    )
    return AIResponse(
        intent=intent,
        entities=entities,
        result=answer,
        data=_ensure_list(rows),
        suggestions=[],
        session_id=session_id,
    )


# ============================================================================
# TIER 3 HANDLERS
# ============================================================================

async def _handle_decision_support(
    intent: str, entities: dict, message: str, language: str, user_role: str,
    decision_support, formatter: ResponseFormatter, context: Dict, session_id: str, llm
) -> AIResponse:
    """Handle decision support intents (analytics, forecasting, recommendations)."""
    
    # Check manager-only permissions
    if intent in MANAGER_ONLY_INTENTS and user_role != "manager":
        return AIResponse(
            intent=intent,
            entities=entities,
            result="This feature is only available for managers. Please contact your manager for inventory and pricing decisions.",
            data=[],
            suggestions=[],
            session_id=session_id,
        )
    
    try:
        result_data = await decision_support.analyze(intent, entities)
        
        if result_data and isinstance(result_data, dict):
            # GET_TOP_SELLING_ITEMS - use formatter
            if intent == "GET_TOP_SELLING_ITEMS":
                items = result_data.get("items", [])
                days = entities.get("days")
                if days is None or not isinstance(days, int):
                    days = 30
                limit = entities.get("quantity")
                if limit is None or not isinstance(limit, int):
                    limit = 10
                limit = min(limit, len(items)) if items else limit
                formatted = formatter.format_top_selling_items(
                    items=items,
                    limit=limit,
                    days=days,
                    language=language
                )
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=formatted.get("message", ""),
                    data=_ensure_list(items),
                    suggestions=[],
                    session_id=session_id,
                )
            
            # GET_SLOW_MOVING_ITEMS - use formatter
            elif intent == "GET_SLOW_MOVING_ITEMS":
                items = result_data.get("items", [])
                days = entities.get("days")
                if days is None or not isinstance(days, int):
                    days = 90
                limit = entities.get("quantity")
                if limit is None or not isinstance(limit, int):
                    limit = 10
                limit = min(limit, len(items)) if items else limit
                formatted = formatter.format_slow_moving_items(
                    items=items,
                    limit=limit,
                    days=days,
                    language=language
                )
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=formatted.get("message", ""),
                    data=_ensure_list(items),
                    suggestions=[],
                    session_id=session_id,
                )
            
            # GET_SALES_ANALYTICS - wrap result_data in a list
            elif intent == "GET_SALES_ANALYTICS":
                formatted = formatter.format_sales_analytics(result_data, language)
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=formatted.get("message", ""),
                    data=_ensure_list(result_data),
                    suggestions=[],
                    session_id=session_id,
                )
            
            # ANALYZE_CUSTOMER_BEHAVIOR - Format nicely for users
            elif intent == "ANALYZE_CUSTOMER_BEHAVIOR":
                formatted_message = _format_customer_behavior_response(result_data, language)
                
                # Generate suggestions based on next best actions
                suggestions = []
                next_best_actions = result_data.get("next_best_actions", [])
                for action in next_best_actions[:3]:  # Top 3 actions
                    action_text = action.get("action", "")
                    if action_text:
                        suggestions.append(action_text)
                
                # Add default suggestions if none found
                if not suggestions:
                    customer_name = result_data.get("customer", {}).get("name", "")
                    suggestions = [
                        f"Create quote for {customer_name}",
                        f"View orders for {customer_name}",
                        f"Recommend items for {customer_name}",
                        f"Track delivery for {customer_name}"
                    ]
                
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=formatted_message,
                    data=_ensure_list(result_data),
                    suggestions=suggestions,
                    session_id=session_id,
                )
            
            # Other decision support intents - use summary
            else:
                summary = create_summary_from_analysis(intent, result_data)
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=summary,
                    data=_ensure_list(result_data),
                    suggestions=[],
                    session_id=session_id,
                )
        
        # No data available
        answer = await llm.generate_async(
            f"No data available for {intent.lower().replace('_', ' ')}.",
            intent=intent,
            language=language,
            max_tokens=200,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=[],
            session_id=session_id,
        )
        
    except Exception as e:
        logger.error(f"Error in decision support: {e}", exc_info=True)
        answer = await llm.generate_async(
            f"There was an error processing your request for {intent.lower().replace('_', ' ')}.",
            intent=intent,
            language=language,
            max_tokens=200,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=[],
            session_id=session_id,
        )


# ============================================================================
# TIER 4 HANDLERS
# ============================================================================

async def _handle_db_query(
    intent: str, entities: dict, message: str, language: str,
    db, formatter: ResponseFormatter, context: Dict, session_id: str, llm
) -> AIResponse:
    """Handle database queries with LLM narration."""
    
    # Execute query
    if intent in PRICE_INTENTS:
        rows = db.resolve_and_price(
            item_name=entities.get("item_name") or "",
            customer_name=entities.get("customer_name") or "" if intent == "GET_CUSTOMER_PRICE" else None,
        )
    else:
        rows = db.query(intent=intent, entities=entities, language=language)
    
    # Handle no results
    if rows is None:
        answer = await llm.generate_async(
            f"User asked: {message}",
            intent=intent,
            language=language,
            max_tokens=300,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=[],
            session_id=session_id,
        )
    
    if not rows:
        logger.info(f"No data returned for {intent}")
        answer = await llm.narrate_async(
            question=message,
            db_rows=[],
            intent=intent,
            language=language,
            max_tokens=300,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=[],
            session_id=session_id,
        )
    
    # Use formatter for outstanding deliveries
    if intent == "GET_OUTSTANDING_DELIVERIES":
        formatted = formatter.format_outstanding_deliveries(rows, language)
        return AIResponse(
            intent=intent,
            entities=entities,
            result=formatted.get("message", ""),
            data=_ensure_list(formatted.get("data", rows)),
            suggestions=[],
            session_id=session_id,
        )
    
    # Narrate the results
    if isinstance(rows, list) and len(rows) > 20:
        truncated_rows = rows[:20]
        answer = await llm.narrate_async(
            question=message,
            db_rows=truncated_rows,
            intent=intent,
            language=language,
            max_tokens=600,
        )
        answer += f"\n\n(Showing first 20 of {len(rows)} results)"
    else:
        answer = await llm.narrate_async(
            question=message,
            db_rows=rows,
            intent=intent,
            language=language,
            max_tokens=600,
        )
    
    return AIResponse(
        intent=intent,
        entities=entities,
        result=answer,
        data=_ensure_list(rows),
        suggestions=[],
        session_id=session_id,
    )


# ============================================================================
# TIER 5 HANDLERS
# ============================================================================

async def _handle_action_router(
    intent: str, entities: dict, message: str, language: str,
    action_router, formatter: ResponseFormatter, context: Dict, session_id: str
) -> AIResponse:
    """Handle action router intents (business operations)."""
    
    api_result = action_router.route(intent, entities, message, language=language)
    logger.info(f"API Result type: {type(api_result)}")
    
    # Special handling for CREATE_QUOTATION
    if intent == "CREATE_QUOTATION":
        return await _handle_quotation_creation(api_result, entities, language, formatter, context, session_id)
    
    # Handle recommendation intents
    if intent in RECOMMENDATION_INTENTS:
        return _handle_recommendations(intent, entities, api_result, formatter, context, session_id)
    
    # Handle simple message responses
    if isinstance(api_result, dict) and "message" in api_result and "ResponseData" not in api_result:
        return AIResponse(
            intent=intent,
            entities=entities,
            result=api_result["message"],
            data=_ensure_list(api_result.get("data")),
            suggestions=[],
            session_id=session_id,
        )
    
    # Handle case where api_result is a dict with ResponseData
    if isinstance(api_result, dict) and "ResponseData" in api_result:
        response_data = api_result.get("ResponseData", [])
        return AIResponse(
            intent=intent,
            entities=entities,
            result=api_result.get("message", "Operation completed successfully."),
            data=_ensure_list(response_data),
            suggestions=[],
            session_id=session_id,
        )
    
    # Default legacy formatting
    formatted = legacy_format(intent, api_result, formatter)
    
    return AIResponse(
        intent=intent,
        entities=entities,
        result=formatted.get("message", "I couldn't process your request."),
        data=_ensure_list(formatted.get("data")),
        suggestions=[],
        session_id=session_id,
    )


async def _handle_quotation_creation(
    api_result: dict, entities: dict, language: str,
    formatter: ResponseFormatter, context: Dict, session_id: str
) -> AIResponse:
    """Handle quotation creation with proper formatting."""
    
    if api_result.get("success") or api_result.get("quotation_id"):
        quotation_id = api_result.get("quotation_id")
        data = api_result.get("data", [{}])[0] if api_result.get("data") else {}
        
        customer_name = data.get("customer_name") or entities.get("customer_name", "")
        items = data.get("items", [])
        total_amount = data.get("total_amount", 0)
        
        # Calculate total from items if needed
        if total_amount == 0 and items:
            for item in items:
                price = item.get("price", 0)
                quantity = item.get("quantity", 1)
                total_amount += float(price) * float(quantity)
        
        valid_until = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        formatted = formatter.format_quotation_creation_success(
            customer_name=customer_name,
            items=items,
            total_amount=total_amount,
            valid_until=valid_until,
            doc_num=quotation_id,
            language=language
        )
        
        message_text = ensure_utf8_string(formatted["message"])
        
        return AIResponse(
            intent="CREATE_QUOTATION",
            entities=entities,
            result=message_text,
            data=_ensure_list(formatted.get("data")),
            suggestions=[],
            session_id=session_id,
        )
    else:
        error_msg = api_result.get("message", "Failed to create quotation")
        invalid_items = api_result.get("invalid_items", [])
        
        formatted = formatter.format_quotation_creation_error(
            error_message=error_msg,
            invalid_items=invalid_items,
            language=language
        )
        
        return AIResponse(
            intent="CREATE_QUOTATION",
            entities=entities,
            result=formatted["message"],
            data=_ensure_list(formatted.get("data")),
            suggestions=[],
            session_id=session_id,
        )


def _handle_recommendations(
    intent: str, entities: dict, api_result, 
    formatter: ResponseFormatter, context: Dict, session_id: str
) -> AIResponse:
    """Handle recommendation intents."""
    
    # If api_result is already a dict with message and data, use it directly
    if isinstance(api_result, dict) and "message" in api_result:
        logger.info(f"Using pre-formatted recommendation response")
        return AIResponse(
            intent=intent,
            entities=entities,
            result=api_result["message"],
            data=_ensure_list(api_result.get("data")),
            suggestions=["Get seasonal recommendations", "Show trending products"],
            session_id=session_id,
        )
    
    # Fallback to legacy formatting
    if isinstance(api_result, dict):
        formatted = legacy_format(intent, api_result, formatter)
        result_message = formatted.get("message", "")
        if not result_message:
            result_message = f"I couldn't find any recommendations for {entities.get('item_name', 'this item')}."
    else:
        formatted = legacy_format(
            intent,
            {"recommendations": api_result if api_result else []},
            formatter,
        )
        result_message = formatted.get("message", "No recommendations found.")
    
    return AIResponse(
        intent=intent,
        entities=entities,
        result=result_message,
        data=_ensure_list(formatted.get("data")),
        suggestions=["Get seasonal recommendations", "Show trending products"],
        session_id=session_id,
    )