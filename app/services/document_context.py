
"""
app/services/document_context.py
==================================
Active Document Context Manager

Tracks the "current document" across conversation turns so the AI can
resolve pronouns like "it", "that order", "the same customer", "convert it".

Every time a handler returns a document (quotation, order, invoice, etc.)
it should call DocumentContextManager.set_active_document().
Every time the AI needs to resolve "it" or "that", it calls
DocumentContextManager.get_active_document().

Stored inside the existing ConversationMemory cache so no new infrastructure
is needed — it piggybacks on the existing session TTL.
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Any

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# SAP B1 Object Type → human label mapping
SAP_DOC_LABELS = {
    23:  "Quotation",
    17:  "Sales Order",
    15:  "Delivery",
    13:  "A/R Invoice",
    24:  "A/R Credit Memo",
    22:  "Purchase Order",
    20:  "Goods Receipt PO",
    18:  "A/P Invoice",
    19:  "A/P Credit Memo",
    59:  "Goods Receipt",
    60:  "Goods Issue",
    67:  "Inventory Transfer",
}

# Valid lifecycle transitions between document types
DOCUMENT_TRANSITIONS = {
    "quotation":        ["sales_order", "cancelled"],
    "sales_order":      ["delivery", "ar_invoice", "cancelled"],
    "delivery":         ["ar_invoice", "ar_credit_memo"],
    "purchase_order":   ["goods_receipt_po", "cancelled"],
    "goods_receipt_po": ["ap_invoice"],
}

# Intent → document type slug mapping
INTENT_TO_DOC_TYPE = {
    "CREATE_QUOTATION":         "quotation",
    "GET_QUOTATIONS":           "quotation",
    "GET_CUSTOMER_ORDERS":      "sales_order",
    "GET_AR_INVOICES":          "ar_invoice",
    "GET_AP_INVOICES":          "ap_invoice",
    "GET_OUTSTANDING_DELIVERIES": "delivery",
    "CREATE_PURCHASE_ORDER":    "purchase_order",
    "GET_PURCHASE_ORDERS":      "purchase_order",
    "GET_GOODS_RECEIPT":        "goods_receipt_po",
    "CREATE_STOCK_TRANSFER":    "inventory_transfer",
    "CREATE_GOODS_ISSUE":       "goods_issue",
    "CREATE_GOODS_RECEIPT":     "goods_receipt",
}


class DocumentContextManager:
    """
    Manages the 'active document' for a conversation session.
    Enables pronoun resolution: "it", "that", "the same customer", "convert it".
    """

    def __init__(self):
        self.cache = get_cache_service()

    def _key(self, session_id: str) -> str:
        return f"doc_context:{session_id}"

    # ------------------------------------------------------------------
    # Set / Get active document
    # ------------------------------------------------------------------

    def set_active_document(
        self,
        session_id: str,
        doc_type: str,
        doc_num: Optional[str],
        card_code: Optional[str],
        card_name: Optional[str] = None,
        extra: Optional[Dict] = None,
    ) -> None:
        """
        Store the most recently touched document so follow-up queries can
        reference it without repeating all details.

        Args:
            session_id:  Conversation session ID
            doc_type:    Slug like "quotation", "sales_order", "ar_invoice"
            doc_num:     SAP DocNum (may be None for drafts)
            card_code:   Customer/Vendor CardCode
            card_name:   Display name
            extra:       Any additional fields to store (items, total, etc.)
        """
        if not session_id:
            return

        doc = {
            "doc_type":   doc_type,
            "doc_num":    doc_num,
            "card_code":  card_code,
            "card_name":  card_name,
            "set_at":     datetime.now().isoformat(),
            **(extra or {}),
        }
        self.cache.set_simple(self._key(session_id), doc, ttl=1800)
        logger.info(
            f"📄 Active document set: {doc_type} #{doc_num} "
            f"| Customer: {card_code} | Session: {session_id}"
        )

    def get_active_document(self, session_id: str) -> Optional[Dict]:
        """Return the active document dict or None."""
        if not session_id:
            return None
        return self.cache.get_simple(self._key(session_id))

    def clear_active_document(self, session_id: str) -> None:
        """Clear active document (e.g. on new chat)."""
        if session_id:
            self.cache.delete_simple(self._key(session_id))

    # ------------------------------------------------------------------
    # Pronoun / reference resolution
    # ------------------------------------------------------------------

    def resolve_document_reference(
        self,
        session_id: str,
        message: str,
        entities: Dict,
    ) -> Dict:
        """
        Enrich entities by resolving document references in the message.

        Handles:
          "convert it to a sales order"    → doc_type transition
          "show that invoice"              → retrieve active doc
          "for the same customer"          → fill customer_name from active doc
          "what's the total on that order" → retrieve active doc num
        """
        if not session_id:
            return entities

        active = self.get_active_document(session_id)
        if not active:
            return entities

        msg = message.lower()

        # Resolve "it", "that", "this" referring to a document
        doc_pronouns = {"it", "that", "this", "the same", "that one", "this one"}
        has_pronoun = any(p in msg for p in doc_pronouns)

        # Fill missing customer from active document
        if not entities.get("customer_name") and not entities.get("_customer_code"):
            if "same customer" in msg or "that customer" in msg or has_pronoun:
                if active.get("card_name"):
                    entities["customer_name"] = active["card_name"]
                    entities["_customer_code"] = active.get("card_code")
                    logger.info(
                        f"🔁 Resolved customer from active doc: {active['card_name']}"
                    )

        # Fill missing doc_num from active document
        if not entities.get("doc_num") and has_pronoun:
            if active.get("doc_num"):
                entities["doc_num"] = active["doc_num"]
                entities["_active_doc_type"] = active["doc_type"]
                logger.info(
                    f"🔁 Resolved doc_num from active doc: {active['doc_num']}"
                )

        # Detect document lifecycle transition intent
        transition_phrases = {
            "convert":       True,
            "turn into":     True,
            "make it a":     True,
            "create order":  True,
            "post":          True,
            "approve":       True,
        }
        for phrase in transition_phrases:
            if phrase in msg:
                entities["_doc_transition_from"] = active.get("doc_type")
                entities["_doc_num_from"] = active.get("doc_num")
                entities["_card_code_from"] = active.get("card_code")
                logger.info(
                    f"🔁 Document transition detected: "
                    f"{active['doc_type']} → (user wants to convert)"
                )
                break

        return entities

    def get_allowed_transitions(self, doc_type: str) -> list:
        """Return valid next document types from the given type."""
        return DOCUMENT_TRANSITIONS.get(doc_type, [])

    def doc_label(self, doc_type: str) -> str:
        """Return a human-readable label for a doc type slug."""
        labels = {v: k for k, v in {
            "quotation":          "Quotation",
            "sales_order":        "Sales Order",
            "delivery":           "Delivery",
            "ar_invoice":         "A/R Invoice",
            "ar_credit_memo":     "A/R Credit Memo",
            "purchase_order":     "Purchase Order",
            "goods_receipt_po":   "Goods Receipt PO",
            "ap_invoice":         "A/P Invoice",
            "inventory_transfer": "Inventory Transfer",
            "goods_issue":        "Goods Issue",
            "goods_receipt":      "Goods Receipt",
        }.items()}
        return labels.get(doc_type, doc_type.replace("_", " ").title())


# Singleton
_doc_ctx: Optional[DocumentContextManager] = None


def get_document_context() -> DocumentContextManager:
    global _doc_ctx
    if _doc_ctx is None:
        _doc_ctx = DocumentContextManager()
    return _doc_ctx
