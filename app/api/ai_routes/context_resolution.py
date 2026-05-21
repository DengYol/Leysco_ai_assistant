"""Context resolution for conversation references"""

from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


def resolve_reference_from_context(
    message: str, 
    context: Dict, 
    entities: Dict
) -> Tuple[Dict, bool]:
    """
    Resolve references like "the first one", "its price", "that customer" using conversation context.
    
    Returns:
        Tuple of (resolved_entities, context_used_flag)
    """
    resolved_entities = entities.copy()
    context_used = False
    
    if not context:
        return resolved_entities, False
    
    last_results = context.get("last_results", [])
    referenced_items = context.get("referenced_items", [])
    referenced_customers = context.get("referenced_customers", [])
    
    message_lower = message.lower()
    
    # Check for ordinal references (first, second, third, 1st, 2nd, etc.)
    ordinals = {
        "first": 0, "1st": 0, "one": 0,
        "second": 1, "2nd": 1, "two": 1,
        "third": 2, "3rd": 2, "three": 2,
        "fourth": 3, "4th": 3, "four": 3,
        "fifth": 4, "5th": 4, "five": 4
    }
    
    # Check for item references
    if not resolved_entities.get("item_name"):
        for word, index in ordinals.items():
            if word in message_lower:
                if index < len(last_results):
                    item = last_results[index]
                    resolved_entities["item_name"] = item.get("ItemName") or item.get("name")
                    resolved_entities["_resolved_from_context"] = True
                    context_used = True
                    logger.info(f"Resolved '{word}' to item: {resolved_entities['item_name']}")
                    break
        
        if not context_used and any(word in message_lower for word in ["it", "this", "that", "the item"]):
            if referenced_items and len(referenced_items) > 0:
                resolved_entities["item_name"] = referenced_items[0].get("name")
                resolved_entities["_resolved_from_context"] = True
                context_used = True
                logger.info(f"Resolved reference to item: {resolved_entities['item_name']}")
        
        if not context_used and "price" in message_lower:
            if referenced_items and len(referenced_items) > 0:
                resolved_entities["_price_query"] = True
                resolved_entities["item_name"] = referenced_items[0].get("name")
                context_used = True
                logger.info(f"Resolved price reference for: {resolved_entities['item_name']}")
    
    # Check for customer references
    if not resolved_entities.get("customer_name"):
        for word, index in ordinals.items():
            if word in message_lower:
                if index < len(referenced_customers):
                    customer = referenced_customers[index]
                    resolved_entities["customer_name"] = customer.get("name")
                    resolved_entities["_resolved_from_context"] = True
                    context_used = True
                    logger.info(f"Resolved '{word}' to customer: {resolved_entities['customer_name']}")
                    break
        
        if not context_used and any(word in message_lower for word in ["customer", "them", "they", "that company"]):
            if referenced_customers and len(referenced_customers) > 0:
                resolved_entities["customer_name"] = referenced_customers[0].get("name")
                resolved_entities["_resolved_from_context"] = True
                context_used = True
                logger.info(f"Resolved customer reference: {resolved_entities['customer_name']}")
    
    return resolved_entities, context_used