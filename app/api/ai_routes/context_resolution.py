"""Context resolution for conversation references"""

from typing import Dict, Tuple
import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FIX: GET_ITEMS context item_name bleed-over
#
# Listing/browse queries ("show me 10 items", "list all products") must NOT
# inherit item_name from the previous turn — the user wants a fresh browse,
# not a filter by whatever was discussed before.
# ---------------------------------------------------------------------------

_LISTING_CONTEXT_BLOCK_RE = re.compile(
    r"(?:show(?:\s+me)?|list|get(?:\s+me)?|display|browse|view)\s+(?:\d+|all|every)?\s*"
    r"(?:items?|products?|inventory|bidhaa|vitu)"
    r"|(?:onyesha|orodhesha|pata)\s+(?:\d+\s+)?(?:bidhaa|vitu)",
    re.IGNORECASE,
)

# Intents whose handlers show ALL records — inheriting item_name from context
# would silently turn a "show all" into a filtered search.
_NO_CONTEXT_ITEM_INTENTS = {
    "GET_ITEMS",
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "GET_WAREHOUSES",
    "GET_CUSTOMERS",
    "GET_CUSTOMER_HEALTH",
    "GET_OUTSTANDING_DELIVERIES",
    "GET_LOW_STOCK_ALERTS",
    "GET_SALES_ANALYTICS",
    "GET_REORDER_REPORT",
}


def resolve_reference_from_context(
    message: str,
    context: Dict,
    entities: Dict
) -> Tuple[Dict, bool]:
    """
    Resolve references like "the first one", "its price", "that customer"
    using conversation context.

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

    # ------------------------------------------------------------------
    # FIX: Suppress item_name context fill for listing / browse queries.
    # "show me 10 items" wants ALL items, not a filter by last item.
    # ------------------------------------------------------------------
    _current_intent = entities.get("_intent") or context.get("last_intent", "")
    _skip_item_from_context = (
        bool(_LISTING_CONTEXT_BLOCK_RE.search(message))
        or _current_intent in _NO_CONTEXT_ITEM_INTENTS
        or bool(entities.get("_is_listing"))
    )
    if _skip_item_from_context:
        logger.debug(
            f"Context item fill suppressed for listing/browse query: '{message[:60]}'"
        )
    # ------------------------------------------------------------------

    # Check for ordinal references (first, second, third, 1st, 2nd, etc.)
    ordinals = {
        "first": 0, "1st": 0, "one": 0,
        "second": 1, "2nd": 1, "two": 1,
        "third": 2, "3rd": 2, "three": 2,
        "fourth": 3, "4th": 3, "four": 3,
        "fifth": 4, "5th": 4, "five": 4
    }

    # Check for item references
    if not resolved_entities.get("item_name") and not _skip_item_from_context:
        for word, index in ordinals.items():
            if word in message_lower:
                if index < len(last_results):
                    item = last_results[index]
                    resolved_entities["item_name"] = (
                        item.get("ItemName") or item.get("name")
                    )
                    resolved_entities["_resolved_from_context"] = True
                    context_used = True
                    logger.info(
                        f"Resolved '{word}' to item: {resolved_entities['item_name']}"
                    )
                    break

        if not context_used and any(
            word in message_lower for word in ["it", "this", "that", "the item"]
        ):
            if referenced_items:
                resolved_entities["item_name"] = referenced_items[0].get("name")
                resolved_entities["_resolved_from_context"] = True
                context_used = True
                logger.info(
                    f"Resolved reference to item: {resolved_entities['item_name']}"
                )

        if not context_used and "price" in message_lower:
            if referenced_items:
                resolved_entities["_price_query"] = True
                resolved_entities["item_name"] = referenced_items[0].get("name")
                context_used = True
                logger.info(
                    f"Resolved price reference for: {resolved_entities['item_name']}"
                )

    # Check for customer references (not suppressed — customer context is
    # still valid even on item-browse queries)
    if not resolved_entities.get("customer_name"):
        for word, index in ordinals.items():
            if word in message_lower:
                if index < len(referenced_customers):
                    customer = referenced_customers[index]
                    resolved_entities["customer_name"] = customer.get("name")
                    resolved_entities["_resolved_from_context"] = True
                    context_used = True
                    logger.info(
                        f"Resolved '{word}' to customer: {resolved_entities['customer_name']}"
                    )
                    break

        if not context_used and any(
            word in message_lower
            for word in ["customer", "them", "they", "that company"]
        ):
            if referenced_customers:
                resolved_entities["customer_name"] = referenced_customers[0].get("name")
                resolved_entities["_resolved_from_context"] = True
                context_used = True
                logger.info(
                    f"Resolved customer reference: {resolved_entities['customer_name']}"
                )

    return resolved_entities, context_used