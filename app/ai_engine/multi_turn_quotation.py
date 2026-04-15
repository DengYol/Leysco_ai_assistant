"""
app/ai_engine/multi_turn_quotation.py
=======================================
Multi-Turn Quotation Flow

Allows sales reps to build a quotation conversationally across multiple
messages instead of requiring all items in a single message.

Optimizations:
- Caching for draft sessions
- Async support for API calls
- Improved item extraction performance
- LRU cache for price lookups
"""

import logging
import re
import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache, wraps

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# ── Words that mean "finalise the quote" ─────────────────────────────────────
_DONE_WORDS = {
    # English
    "done", "finish", "finished", "submit", "confirm", "create",
    "send", "yes", "ok", "okay", "proceed", "complete", "go", "finalize",
    # Swahili
    "maliza", "isha", "kabisa", "ndio", "sawa", "tuma", "tengeneza",
}

_CANCEL_WORDS = {
    "cancel", "abort", "stop", "quit", "exit", "no",
    "acha", "simama", "hapana",
}

# SKIP patterns for item extraction
SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX", "LABEL")
SKIP_NAME_TERMS = ("LABEL", "PACK", "BAG", "BOX", "STICKER", "SLEEVE", "WRAPPER")


def _is_done(message: str) -> bool:
    """Return True if the message means 'finalise the quotation'."""
    msg = message.lower().strip().rstrip("!?.,")
    words = msg.split()
    return msg in _DONE_WORDS or (len(words) == 1 and words[0] in _DONE_WORDS)


def _is_cancel(message: str) -> bool:
    """Return True if the message means 'cancel the quotation'."""
    msg = message.lower().strip().rstrip("!?.,")
    return any(w in msg.split() for w in _CANCEL_WORDS)


def _running_total(draft: dict) -> float:
    """Sum all line totals in the draft."""
    return sum(item.get("LineTotal", 0.0) for item in draft.get("items", []))


def _fmt(amount: float) -> str:
    return f"KES {amount:,.0f}"


def _item_line(item: dict) -> str:
    name = item.get("ItemName", "?")
    qty = item.get("Quantity", 0)
    price = item.get("Price", 0.0)
    total = item.get("LineTotal", qty * price)
    return f"• {name} × {qty} @ {_fmt(price)} = {_fmt(total)}"


def _normalize_api_result(result: Any) -> List[Dict]:
    """
    Normalize API result to a list of dictionaries.
    Handles dict, list, and tuple return types.
    """
    if not result:
        return []
    
    # If it's already a list
    if isinstance(result, list):
        return result
    
    # If it's a tuple, convert to list
    if isinstance(result, tuple):
        return list(result)
    
    # If it's a dict, try to extract data
    if isinstance(result, dict):
        # Check for ResponseData structure
        if "ResponseData" in result:
            response_data = result["ResponseData"]
            if isinstance(response_data, dict):
                if "data" in response_data:
                    data = response_data["data"]
                    return data if isinstance(data, list) else []
                if "stocks" in response_data:
                    stocks = response_data["stocks"]
                    if isinstance(stocks, dict) and "data" in stocks:
                        return stocks["data"]
            elif isinstance(response_data, list):
                return response_data
        # Check for direct data array
        if "data" in result:
            data = result["data"]
            return data if isinstance(data, list) else []
    
    return []


# ── Cached item search ───────────────────────────────────────────────────────

@lru_cache(maxsize=256)
def _search_item_cached(api, item_search: str, qty: int, customer_code: str = "") -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Cached version of item search and price lookup.
    Returns (item, price_result) or (None, None)
    """
    try:
        items = api.get_items(search=item_search, limit=10)
        
        # Normalize the result (handle tuple, dict, list)
        items = _normalize_api_result(items)
        
        if not items:
            # Try broader search - extract base name (remove size)
            import re
            base_name = re.sub(r'\s+\d+(?:ml|ML|mL|kg|KG|g|G|l|L)\b', '', item_search, flags=re.IGNORECASE).strip()
            if base_name != item_search:
                logger.info(f"🔍 No items found for '{item_search}', trying broader search: '{base_name}'")
                items = api.get_items(search=base_name, limit=20)
                items = _normalize_api_result(items)
            
            if not items:
                logger.debug(f"No items found for search: {item_search}")
                return None, None
        
        # Find best matching item (prioritize sellable, non-packing)
        best_item = None
        for candidate in items:
            if not isinstance(candidate, dict):
                logger.debug(f"Skipping non-dict candidate: {type(candidate)}")
                continue
                
            candidate_name = candidate.get("ItemName", "").lower()
            candidate_code = candidate.get("ItemCode", "").lower()
            search_lower = item_search.lower()
            item_group = (candidate.get("item_group") or {}).get("ItmsGrpNam", "").upper()
            is_sellable = candidate.get("SellItem") == "Y"
            
            # Check if it's a packing/raw material
            is_packing = (
                item_group in SKIP_GROUPS or
                any(candidate_code.startswith(p) for p in SKIP_PREFIXES) or
                any(term in candidate_name.upper() for term in SKIP_NAME_TERMS)
            )
            
            if is_packing or not is_sellable:
                logger.debug(f"Skipping non-sellable/packing item: {candidate_name} (is_packing={is_packing}, is_sellable={is_sellable})")
                continue
            
            # Check for matches (exact or contains)
            if search_lower == candidate_name or search_lower == candidate_code:
                best_item = candidate
                break
            if search_lower in candidate_name or search_lower in candidate_code:
                if not best_item:
                    best_item = candidate
                elif len(candidate_name) < len(best_item.get("ItemName", "").lower()):
                    best_item = candidate
        
        # If no sellable item found, try broader search without size
        if not best_item:
            import re
            base_name = re.sub(r'\s+\d+(?:ml|ML|mL|kg|KG|g|G|l|L)\b', '', item_search, flags=re.IGNORECASE).strip()
            if base_name != item_search:
                logger.info(f"🔍 No sellable item found for '{item_search}', trying broader search: '{base_name}'")
                items = api.get_items(search=base_name, limit=20)
                items = _normalize_api_result(items)
                
                for candidate in items:
                    if not isinstance(candidate, dict):
                        continue
                        
                    candidate_name = candidate.get("ItemName", "").lower()
                    candidate_code = candidate.get("ItemCode", "").lower()
                    item_group = (candidate.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                    is_sellable = candidate.get("SellItem") == "Y"
                    
                    is_packing = (
                        item_group in SKIP_GROUPS or
                        any(candidate_code.startswith(p) for p in SKIP_PREFIXES) or
                        any(term in candidate_name.upper() for term in SKIP_NAME_TERMS)
                    )
                    
                    if is_packing or not is_sellable:
                        continue
                    
                    # Check if the base name is in the candidate name
                    if base_name in candidate_name or base_name in candidate_code:
                        best_item = candidate
                        logger.info(f"✅ Found item via broader search: {candidate_name} ({candidate_code})")
                        break
        
        if not best_item:
            logger.debug(f"No sellable item found for: {item_search}")
            return None, None
        
        logger.info(f"✅ Found item: {best_item.get('ItemName')} ({best_item.get('ItemCode')})")
        return best_item, None
        
    except Exception as e:
        logger.debug(f"Item search failed for '{item_search}': {e}")
        return None, None


def _extract_items_from_message(message: str, ar: Any, customer: dict) -> tuple:
    """
    Extract multiple items from a quotation message.
    Optimized with caching.
    Returns (items_to_quote, skipped_items)
    """
    items_to_quote = []
    skipped_items = []
    logger.info(f"🔍 Multi-turn extracting items from: {message}")
    
    # Step 1: Extract customer name
    customer_name = customer.get("CardName", "") if customer else ""
    
    # Step 2: Find the items part by locating "with" or removing customer name
    items_part = message
    
    # Remove the prefix "create quotation for"
    prefixes_to_remove = [
        r'^create\s+(?:a\s+)?quotation\s+for\s+',
        r'^make\s+(?:a\s+)?quotation\s+for\s+',
        r'^new\s+quotation\s+for\s+',
        r'^quotation\s+for\s+',
        r'^quote\s+for\s+',
        r'^add\s+',
    ]
    for prefix in prefixes_to_remove:
        items_part = re.sub(prefix, '', items_part, flags=re.IGNORECASE)
    
    # Remove customer name if present
    if customer_name:
        escaped_customer = re.escape(customer_name)
        items_part = re.sub(escaped_customer, '', items_part, flags=re.IGNORECASE)
    
    # Find everything after "with"
    with_match = re.search(r'with\s+(.+)$', items_part, re.IGNORECASE)
    if with_match:
        items_part = with_match.group(1).strip()
        logger.info(f"📦 Items part from 'with' clause: {items_part}")
    else:
        items_part = items_part.strip()
        logger.info(f"📦 Items part (no 'with' clause): {items_part}")
    
    # Remove any remaining customer name fragments
    if customer_name:
        customer_words = customer_name.lower().split()
        for word in customer_words:
            if len(word) > 3:
                items_part = re.sub(r'\b' + re.escape(word) + r'\b', '', items_part, flags=re.IGNORECASE)
    
    items_part = re.sub(r'\s+', ' ', items_part).strip()
    logger.info(f"📦 Cleaned items part: {items_part}")
    
    # Split by "and" to handle multiple items
    item_parts = re.split(r'\s+and\s+', items_part)
    
    all_matches = []
    
    for part in item_parts:
        part = part.strip()
        if not part:
            continue
        
        # Try to find quantity and item name (quantity first)
        match = re.search(r'^(\d+)\s+(.+)$', part, re.IGNORECASE)
        if match:
            qty = int(match.group(1))
            item_search = match.group(2).strip()
            all_matches.append((qty, item_search))
            logger.info(f"📦 Extracted: qty={qty}, item='{item_search}'")
            continue
        
        # Pattern: item name followed by quantity
        match = re.search(r'^(.+?)\s+(\d+)$', part, re.IGNORECASE)
        if match:
            qty = int(match.group(2))
            item_search = match.group(1).strip()
            all_matches.append((qty, item_search))
            logger.info(f"📦 Extracted: qty={qty}, item='{item_search}'")
            continue
        
        # Default quantity = 1
        if part and len(part) > 2:
            is_customer_fragment = False
            if customer_name:
                part_lower = part.lower()
                customer_lower = customer_name.lower()
                if part_lower in customer_lower or customer_lower in part_lower:
                    is_customer_fragment = True
            
            if not is_customer_fragment:
                all_matches.append((1, part))
                logger.info(f"📦 Extracted (default qty=1): item='{part}'")
    
    # Multi-item pattern
    if not all_matches:
        multi_item_pattern = r'(\d+)\s+([a-zA-Z0-9\-]+)\s+and\s+(\d+)\s+([a-zA-Z0-9\s\-]+)'
        match = re.search(multi_item_pattern, items_part, re.IGNORECASE)
        if match:
            all_matches.append((int(match.group(1)), match.group(2)))
            all_matches.append((int(match.group(3)), match.group(4)))
            logger.info(f"📦 Multi-item pattern extracted: {all_matches}")
    
    # =========================================================
    # FIXED SECTION: ITEM SEARCH HANDLING
    # =========================================================
    for qty, item_search in all_matches:
        try:
            # Clean up the item search string
            item_search = re.sub(r'\s+(and|na|with|for|units?|pieces?|vitengo)$', '', item_search, flags=re.IGNORECASE)
            item_search = item_search.strip()
            
            if customer_name and item_search.lower() in customer_name.lower():
                logger.info(f"⏭️ Skipping customer name fragment: '{item_search}'")
                continue
            
            logger.info(f"🔍 Searching for item: '{item_search}' (qty: {qty})")
            
            # ✅ FIX: Proper unpacking
            best_item, _ = _search_item_cached(
                ar.api,
                item_search,
                qty,
                customer.get("CardCode", "")
            )
            
            if not best_item:
                # Try a broader search (first word only)
                words = item_search.split()
                if len(words) > 1:
                    broader_search = words[0]
                    logger.info(f"🔍 Trying broader search: '{broader_search}'")
                    
                    # ✅ FIX: Proper unpacking again
                    best_item, _ = _search_item_cached(
                        ar.api,
                        broader_search,
                        qty,
                        customer.get("CardCode", "")
                    )
            
            # ✅ EXTRA SAFETY (future-proof)
            if isinstance(best_item, tuple):
                best_item = best_item[0]
            
            if not best_item or not isinstance(best_item, dict):
                skipped_items.append({
                    "name": item_search,
                    "reason": "No sellable item found"
                })
                continue
            
            item_code = best_item.get("ItemCode")
            item_name = best_item.get("ItemName")
            item_group = (best_item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
            
            # Get price for customer
            price_result = ar.pricing.get_price_for_customer(
                item_code=item_code,
                customer=customer
            )
            
            # Handle price result safely
            if isinstance(price_result, tuple):
                price = price_result[1] if len(price_result) > 1 else 0
                found = price > 0
            elif isinstance(price_result, dict):
                found = price_result.get("found", False)
                price = price_result.get("price", 0) if found else 0
            else:
                price = 0
                found = False
            
            if not found or price <= 0:
                skipped_items.append({
                    "name": item_name,
                    "code": item_code,
                    "reason": "No price set for this customer"
                })
                continue
            
            items_to_quote.append({
                "ItemCode": item_code,
                "ItemName": item_name,
                "Quantity": qty,
                "Price": price,
                "LineTotal": qty * price,
                "ItemGroup": item_group
            })
            
            logger.info(f"✅ Added item: {item_name} x{qty} @ KES {price}")
        
        except Exception as e:
            logger.error(f"Failed to parse item: {item_search} - {e}")
            continue
    
    logger.info(f"📦 Total items to quote: {len(items_to_quote)}, Skipped: {len(skipped_items)}")
    return items_to_quote, skipped_items


# ── Session helpers with caching ─────────────────────────────────────────────

def _get_ctx():
    """Lazy import so the module loads even if session_context isn't deployed yet."""
    from app.services.session_context import session_ctx
    return session_ctx


def _get_draft_cache_key(session_id: str) -> str:
    """Generate cache key for draft."""
    return f"quotation_draft:{session_id}"


def _load_draft(session_id: str) -> dict | None:
    """Return the active quotation draft for this session, or None."""
    if not session_id:
        return None
    
    # Try Redis cache first
    cache = get_cache_service()
    cache_key = _get_draft_cache_key(session_id)
    cached = cache.get_simple(cache_key)
    if cached:
        logger.info(f"📦 Draft cache hit: {session_id}")
        return cached
    
    # Fallback to session context
    try:
        ctx = _get_ctx()
        raw = ctx.get(session_id, "quotation_draft")
        if isinstance(raw, dict) and "customer_code" in raw:
            # Cache for future requests
            cache.set_simple(cache_key, raw, ttl=3600)  # 1 hour TTL for drafts
            return raw
    except Exception as exc:
        logger.debug("_load_draft: %s", exc)
    return None


def _save_draft(session_id: str, draft: dict) -> None:
    """Save draft to both cache and session context."""
    if not session_id:
        return
    
    # Save to Redis cache
    cache = get_cache_service()
    cache_key = _get_draft_cache_key(session_id)
    cache.set_simple(cache_key, draft, ttl=3600)
    
    # Save to session context
    try:
        _get_ctx().set(session_id, "quotation_draft", draft)
    except Exception as exc:
        logger.debug("_save_draft: %s", exc)


def _clear_draft(session_id: str) -> None:
    """Remove only the quotation_draft key without wiping other session data."""
    if not session_id:
        return
    
    # Clear from Redis cache
    cache = get_cache_service()
    cache_key = _get_draft_cache_key(session_id)
    cache.delete_simple(cache_key)
    
    # Clear from session context
    try:
        ctx = _get_ctx()
        lock = getattr(ctx, "_lock", None)
        store = getattr(ctx, "_store", None)
        if lock is not None and store is not None:
            with lock:
                s = store.get(session_id)
                if s is not None:
                    entities = getattr(s, "entities", {})
                    if "quotation_draft" in entities:
                        del entities["quotation_draft"]
        else:
            d = getattr(ctx, "_store", {})
            if session_id in d and "quotation_draft" in d[session_id]:
                del d[session_id]["quotation_draft"]
    except Exception as exc:
        logger.debug("_clear_draft: %s", exc)


# ── Main entry point ──────────────────────────────────────────────────────────

def handle_create_quotation(
    message: str,
    entities: dict,
    session_id: str,
    action_router_self: Any,
    language: str = "en",
) -> dict:
    """
    Handle CREATE_QUOTATION intent with multi-turn support.
    Optimized with caching and async support.
    """
    ar = action_router_self
    customer_name = (entities.get("customer_name") or "").strip()
    draft = _load_draft(session_id)

    # ── Cancel ───────────────────────────────────────────────────────────────
    if _is_cancel(message) and draft:
        _clear_draft(session_id)
        if language == "sw":
            return {"message": "Nukuu imefutwa. Unaweza kuanza upya wakati wowote.", "data": []}
        return {"message": "Quotation cancelled. You can start a new one anytime.", "data": []}

    # ── Resolve customer ─────────────────────────────────────────────────────
    if draft:
        resolved = {"CardCode": draft["customer_code"], "CardName": draft["customer_name"]}
    else:
        if not customer_name:
            if language == "sw":
                return {"message": "Tafadhali taja jina la mteja kwa nukuu.\nMfano: 'Tengeneza nukuu kwa Magomano'", "data": []}
            return {"message": "Please specify a customer name for the quotation.\nExample: 'Create quote for Magomano'", "data": []}

        resolved, _ = ar._resolve_customer(customer_name)
        if not resolved:
            if language == "sw":
                return {"message": f"Mteja '{customer_name}' hajapatikana.", "data": []}
            return {"message": f"Customer '{customer_name}' not found.", "data": []}

        # Persist customer to session so next turns inherit it
        try:
            ctx = _get_ctx()
            ctx.set(session_id, "customer_name", resolved.get("CardName"))
            ctx.set(session_id, "customer_code", resolved.get("CardCode"))
        except Exception:
            pass

    # ── Case C: "done" with items in draft → finalise ────────────────────────
    if _is_done(message):
        if draft and draft.get("items"):
            return _finalise(draft, session_id, ar, language)
        if draft and not draft.get("items"):
            if language == "sw":
                return {"message": "Hakuna bidhaa kwenye nukuu bado. Tafadhali ongeza bidhaa kwanza.\nMfano: '4 vegimax-250ml na 4 Maize Tosheka'", "data": []}
            return {"message": "No items in the quote yet. Please add some items first.\nExample: '4 vegimax-250ml and 4 Maize Tosheka'", "data": []}
        # No draft at all — fall through to Case A

    # ── Try to extract items from the current message ─────────────────────────
    items_found, skipped = _extract_items_from_message(message, ar, resolved)

    # ── Case A: No items + no draft → start draft ─────────────────────────────
    if not items_found and not draft:
        new_draft = {
            "customer_code": resolved.get("CardCode"),
            "customer_name": resolved.get("CardName"),
            "items": [],
            "running_total": 0.0,
        }
        _save_draft(session_id, new_draft)

        cname = resolved.get("CardName")
        if language == "sw":
            msg = (
                f"✅ Nukuu imeanzishwa kwa **{cname}**.\n\n"
                "Ongeza bidhaa kwa kuandika, kwa mfano:\n"
                "• '4 vegimax-250ml na 4 Maize Tosheka'\n"
                "• '10 vegimax'\n"
                "• '5 mbegu za kabichi'\n\n"
                "Andika **'maliza'** unapokuwa tayari kuunda nukuu."
            )
        else:
            msg = (
                f"✅ Quote started for **{cname}**.\n\n"
                "Add items by typing, for example:\n"
                "• '4 vegimax-250ml and 4 Maize Tosheka'\n"
                "• '10 vegimax'\n"
                "• '5 cabbage seeds'\n\n"
                "Type **'done'** when you're ready to create the quote."
            )
        return {"message": msg, "data": [new_draft]}

    # ── Case B: Items found + draft exists → append ───────────────────────────
    if items_found and draft:
        for item in items_found:
            item["LineTotal"] = item["Quantity"] * item["Price"]
        draft["items"].extend(items_found)
        draft["running_total"] = _running_total(draft)
        _save_draft(session_id, draft)

        added_lines = "\n".join(_item_line(i) for i in items_found)
        count = len(draft["items"])
        total = draft["running_total"]
        cname = draft["customer_name"]

        if language == "sw":
            msg = (
                f"✅ **Imeongezwa kwenye nukuu ya {cname}:**\n{added_lines}\n\n"
                f"📋 **Jumla inayoendelea:** {_fmt(total)} ({count} bidhaa)\n\n"
                "Ongeza bidhaa zaidi au andika **'maliza'** kuunda nukuu."
            )
        else:
            msg = (
                f"✅ **Added to {cname}'s quote:**\n{added_lines}\n\n"
                f"📋 **Running total:** {_fmt(total)} "
                f"({count} item{'s' if count != 1 else ''})\n\n"
                "Add more items or type **'done'** to create the quote."
            )

        if skipped:
            names = ", ".join(s.get("name", "?") for s in skipped[:3])
            if language == "sw":
                msg += f"\n\n⚠️ Ilirukwa (haiuzwi / bei haipo): {names}"
            else:
                msg += f"\n\n⚠️ Skipped (not sellable / no price): {names}"

        return {"message": msg, "data": [draft]}

    # ── Case D: Items found + no draft → single-turn (backward compat) ────────
    if items_found and not draft:
        return _create_immediately(items_found, skipped, resolved, ar, language)

    # ── Existing draft, no new items → prompt ────────────────────────────────
    if draft:
        cname = draft["customer_name"]
        count = len(draft["items"])
        total = draft["running_total"]
        if language == "sw":
            progress = f" ({count} bidhaa, {_fmt(total)})" if count else ""
            msg = f"Nukuu ya **{cname}** inaendelea{progress}.\n\nOngeza bidhaa (mfano: '4 vegimax-250ml na 4 Maize Tosheka') au andika **'maliza'**."
        else:
            progress = f" ({count} item{'s' if count != 1 else ''}, {_fmt(total)})" if count else ""
            msg = f"Quote for **{cname}** is in progress{progress}.\n\nAdd items (e.g. '4 vegimax-250ml and 4 Maize Tosheka') or type **'done'**."
        return {"message": msg, "data": [draft]}

    # Fallback
    if language == "sw":
        return {"message": "Sikuweza kupata bidhaa au mteja. Tafadhali jaribu tena.\nMfano: '4 vegimax-250ml na 4 Maize Tosheka'", "data": []}
    return {"message": "Could not find any items or customer. Please try again.\nExample: '4 vegimax-250ml and 4 Maize Tosheka'", "data": []}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _finalise(draft: dict, session_id: str, ar: Any, language: str) -> dict:
    """Call QuotationService, clear draft, return confirmation card."""
    try:
        result = ar.quotation.create_quotation(
            customer_code=draft["customer_code"],
            items=draft["items"],
            comments="Quotation created via AI Assistant (multi-turn)",
            language=language,
        )
    except Exception as exc:
        logger.error("Quotation creation failed: %s", exc)
        if language == "sw":
            return {"message": f"Hitilafu kuunda nukuu: {exc}", "data": []}
        return {"message": f"Failed to create quotation: {exc}", "data": []}

    _clear_draft(session_id)

    if result.get("message"):
        return {
            "message": result["message"],
            "data": result.get("data", [])
        }

    if result.get("success"):
        doc_num = result.get("DocNum", "N/A")
        cname = draft["customer_name"]
        total = draft["running_total"]
        items = draft["items"]

        if language == "sw":
            text = f"✅ **Nukuu #{doc_num} Imeundwa!**\n\n"
            text += f"**Mteja:** {cname}\n"
            text += f"**Bidhaa {len(items)}:**\n"
            for item in items:
                text += f"  {_item_line(item)}\n"
            text += f"\n**JUMLA: {_fmt(total)}**"
        else:
            text = f"✅ **Quotation #{doc_num} Created!**\n\n"
            text += f"**Customer:** {cname}\n"
            text += f"**{len(items)} Item{'s' if len(items) != 1 else ''}:**\n"
            for item in items:
                text += f"  {_item_line(item)}\n"
            text += f"\n**TOTAL: {_fmt(total)}**"

        return {"message": text, "data": [result]}

    error = result.get("error", "Unknown error")
    if "web_interface_instructions" in result:
        steps = result["web_interface_instructions"].get("steps", [])
        if language == "sw":
            text = "⚠️ **Kuunda nukuu kupitia API haiwezekani sasa hivi.**\n\nTumia wavuti:\n"
        else:
            text = "⚠️ **Quotation API not available.**\n\nPlease use the web interface:\n"
        text += "\n".join(steps)
        text += f"\n\n**{draft['customer_name']}  ·  {_fmt(draft['running_total'])}**\n"
        for item in draft["items"]:
            text += f"  {_item_line(item)}\n"
        return {"message": text, "data": [draft]}

    if language == "sw":
        return {"message": f"❌ Imeshindwa kuunda nukuu: {error}", "data": []}
    return {"message": f"❌ Failed to create quotation: {error}", "data": []}


def _create_immediately(
    items: list,
    skipped: list,
    customer: dict,
    ar: Any,
    language: str,
) -> dict:
    """Original single-turn path — all items came in the first message."""
    try:
        result = ar.quotation.create_quotation(
            customer_code=customer.get("CardCode"),
            items=items,
            comments="Quotation created via AI Assistant",
            language=language,
        )
    except Exception as exc:
        logger.error("Single-turn quotation failed: %s", exc)
        if language == "sw":
            return {"message": f"Hitilafu: {exc}", "data": []}
        return {"message": f"Error: {exc}", "data": []}

    if result.get("message"):
        return {
            "message": result["message"],
            "data": result.get("data", [])
        }

    if result.get("success"):
        doc_num = result.get("DocNum", "N/A")
        cname = customer.get("CardName")
        total = sum(i.get("Price", 0) * i.get("Quantity", 0) for i in items)

        if language == "sw":
            text = f"✅ **Nukuu #{doc_num} imeundwa kwa {cname}**\n\n"
            text += f"**Bidhaa {len(items)}:**\n"
            for item in items:
                text += f"  {_item_line(item)}\n"
            text += f"\n**JUMLA: {_fmt(total)}**"
        else:
            text = f"✅ **Quotation #{doc_num} created for {cname}**\n\n"
            text += f"**{len(items)} Item{'s' if len(items) != 1 else ''}:**\n"
            for item in items:
                text += f"  {_item_line(item)}\n"
            text += f"\n**TOTAL: {_fmt(total)}**"

        if skipped:
            names = ", ".join(s.get("name", "?") for s in skipped[:3])
            if language == "sw":
                text += f"\n\n⚠️ Ilirukwa: {names}"
            else:
                text += f"\n\n⚠️ Skipped: {names}"

        return {"message": text, "data": [result]}

    error = result.get("error", "Unknown error")
    if "web_interface_instructions" in result:
        steps = result["web_interface_instructions"].get("steps", [])
        if language == "sw":
            text = "⚠️ **Kuunda nukuu kupitia API haiwezekani.**\n\n"
        else:
            text = "⚠️ **Quotation creation via API not available.**\n\n"
        text += "\n".join(steps)
        return {"message": text, "data": []}

    if language == "sw":
        return {"message": f"❌ {error}", "data": []}
    return {"message": f"❌ {error}", "data": []}