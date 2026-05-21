"""Quotation related intent handlers"""

from typing import Dict, Any
import logging
import re
from datetime import datetime, timedelta
from ..base_handler import BaseHandler
from ..utils.helpers import extract_quantity_and_item, clean_item_search_term
from ..constants import SKIP_GROUPS, SKIP_PREFIXES
from app.ai_engine.multi_turn_quotation import handle_create_quotation

logger = logging.getLogger(__name__)


class QuotationHandler(BaseHandler):
    """Handler for quotation related intents"""

    def create_quotation(self, entities: dict, message: str, language: str) -> dict:
        """
        Create a new quotation.

        FIX: The query rewriter rewrites
            'create quotation for Magomano with 3 vegimax 30ml'
        to
            'create quotation for Magomano?'
        stripping the item list.  We recover the full original text from
        entities['_original_query'] and pass that to handle_create_quotation
        so the item parser always sees the complete message.
        """
        sid = entities.get("_session_id", "")

        # Prefer the unmodified original query stored by chat.py.
        # Fall back to the (possibly rewritten) message only if unavailable.
        original_query = (entities.get("_original_query") or "").strip()
        effective_message = original_query if original_query else message

        if effective_message != message:
            logger.info(
                f"QuotationHandler: using original query for item extraction: "
                f"'{effective_message}' (rewritten was: '{message}')"
            )

        result = handle_create_quotation(
            message=effective_message,
            entities=entities,
            session_id=sid,
            action_router_self=self.router,
            language=language,
        )

        # Ensure the result has the required fields for Flutter
        if result and isinstance(result, dict):
            if "intent" not in result:
                result["intent"] = "CREATE_QUOTATION"

            if not result.get("quotation_id") and result.get("data"):
                data = result.get("data", [])
                if data and isinstance(data, list) and len(data) > 0:
                    first_item = data[0]
                    if isinstance(first_item, dict):
                        result["quotation_id"] = (
                            str(first_item.get("DocNum"))
                            or str(first_item.get("quotation_id"))
                            or str(first_item.get("id"))
                            or ""
                        )

            if result.get("quotation_id"):
                result["success"] = True
            elif "error" not in result:
                result["success"] = True

        return result

    def get_quotations(self, customer_name: str, limit: int, language: str) -> dict:
        """Get quotations for a customer."""
        if not customer_name:
            return self._missing("a customer name", language)

        customer, search_name = self.router._resolve_customer(customer_name)
        if not customer:
            return self._not_found("Customer", search_name, language)

        quotes = self.api.get_customer_quotations(
            customer_name=customer.get("CardName"),
            limit=limit or 10,
        )

        if not quotes:
            if language == "sw":
                return {
                    "message": (
                        f"Hakuna nukuu zilizopatikana kwa {customer.get('CardName')}\n\n"
                        f"Unda moja: 'unda nukuu kwa {customer_name} na 5 vegimax'"
                    ),
                    "data": [],
                }
            return {
                "message": (
                    f"No quotations found for {customer.get('CardName')}\n\n"
                    f"Create one: 'create quotation for {customer_name} with 5 vegimax'"
                ),
                "data": [],
            }

        if language == "sw":
            text = f"Nukuu za {customer.get('CardName')} ({len(quotes)} kwa jumla)\n\n"
            for i, q in enumerate(quotes, 1):
                valid = (q.get("DocDueDate") or "")[:10]
                text += (
                    f"{i}. Nukuu {q.get('DocNum')} — "
                    f"KES {float(q.get('DocTotal', 0)):,.2f}"
                    + (f" (tarehe ya mwisho {valid})" if valid else "") + "\n"
                )
        else:
            text = f"Quotations for {customer.get('CardName')} ({len(quotes)} total)\n\n"
            for i, q in enumerate(quotes, 1):
                valid = (q.get("DocDueDate") or "")[:10]
                text += (
                    f"{i}. Quote {q.get('DocNum')} — "
                    f"KES {float(q.get('DocTotal', 0)):,.2f}"
                    + (f" (valid until {valid})" if valid else "") + "\n"
                )

        return {"message": text, "data": quotes}

    def follow_up_quotations(self, entities: dict, language: str) -> dict:
        """Handle follow-up quotations using QuotationIntelligence."""
        customer_name = (entities.get("customer_name") or "").strip()

        if not self.router.user_token:
            if language == "sw":
                return {
                    "message": "Samahani, siwezi kuona taarifa za nukuu bila kuwa umeingia. Tafadhali ingia tena.",
                    "data": [],
                }
            return {
                "message": "Sorry, I cannot fetch quotation intelligence without authentication. Please log in again.",
                "data": [],
            }

        try:
            report = self.router.quotation_intelligence.get_follow_up_report(
                customer_name=customer_name if customer_name else None,
                language=language,
            )
            message = self.router.quotation_intelligence.format_report_message(report, language)
            return {"message": message, "data": report}

        except Exception as e:
            logger.error(f"Error in FOLLOW_UP_QUOTATIONS handler: {e}")
            if language == "sw":
                return {
                    "message": "Samahani, nimekosa kuleta ripoti ya nukuu. Tafadhali jaribu tena.",
                    "data": [],
                }
            return {
                "message": "Sorry, I failed to fetch the quotation follow-up report. Please try again.",
                "data": [],
            }

    def _extract_quotation_items(self, message: str, customer: dict) -> tuple:
        """Extract multiple items from a quotation message."""
        items_to_quote = []
        skipped_items = []
        logger.info(f"Extracting items from: {message}")

        items_part = message
        customer_name = customer.get("CardName", "") if customer else ""
        if customer_name:
            items_part = re.sub(re.escape(customer_name), "", message, flags=re.IGNORECASE)
            items_part = re.sub(r"^.*?(?:with|for)\s+", "", items_part, flags=re.IGNORECASE)

        prefixes_to_remove = [
            r"^create\s+(?:a\s+)?quotation\s+for\s+",
            r"^make\s+(?:a\s+)?quotation\s+for\s+",
            r"^new\s+quotation\s+for\s+",
            r"^quotation\s+for\s+",
            r"^quote\s+for\s+",
        ]
        for prefix in prefixes_to_remove:
            items_part = re.sub(prefix, "", items_part, flags=re.IGNORECASE)

        items_part = items_part.strip()
        logger.info(f"Items part after cleaning: {items_part}")

        all_matches = extract_quantity_and_item(items_part)

        for qty, item_search in all_matches:
            try:
                item_search = clean_item_search_term(item_search)
                logger.info(f"Searching for item: '{item_search}' (qty: {qty})")

                items = self.api.get_items(search=item_search, limit=10)
                if items:
                    item = None
                    for candidate in items:
                        candidate_name = candidate.get("ItemName", "").lower()
                        candidate_code = candidate.get("ItemCode", "").lower()
                        search_lower = item_search.lower()

                        if search_lower == candidate_name or search_lower == candidate_code:
                            item = candidate
                            break
                        if search_lower in candidate_name or search_lower in candidate_code:
                            if not item:
                                item = candidate
                            elif len(candidate_name) < len(item.get("ItemName", "").lower()):
                                item = candidate

                    if not item:
                        item = items[0]

                    item_code  = item.get("ItemCode")
                    item_name  = item.get("ItemName")
                    item_group = (item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                    is_sellable = item.get("SellItem") == "Y"
                    is_packing  = item_group in SKIP_GROUPS or any(
                        item_code.startswith(p) for p in SKIP_PREFIXES
                    )

                    if not is_sellable or is_packing:
                        skipped_items.append({
                            "name":   item_name,
                            "code":   item_code,
                            "reason": f"Non-sellable item (Group: {item_group})",
                        })
                        continue

                    price_result = self.pricing.get_price_for_customer(
                        item_code=item_code, customer=customer
                    )
                    price = price_result.get("price", 0) if price_result.get("found") else 0

                    if price <= 0:
                        skipped_items.append({
                            "name":   item_name,
                            "code":   item_code,
                            "reason": "No price set for this customer",
                        })
                        continue

                    items_to_quote.append({
                        "ItemCode":   item_code,
                        "ItemName":   item_name,
                        "Quantity":   qty,
                        "Price":      price,
                        "ItemGroup":  item_group,
                    })
                    logger.info(f"Added item: {item_name} x{qty} @ KES {price}")
                else:
                    skipped_items.append({
                        "name":   item_search,
                        "reason": "Item not found in system",
                    })
            except Exception as e:
                logger.error(f"Failed to parse item: {item_search} - {e}")
                continue

        logger.info(
            f"Total items to quote: {len(items_to_quote)}, Skipped: {len(skipped_items)}"
        )
        return items_to_quote, skipped_items