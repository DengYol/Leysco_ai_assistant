"""Customer name extraction rules"""

import re
import logging
from ..constants import (
    CUSTOMER_SUFFIX_WORDS,
    PRODUCT_INDICATORS,
    LISTING_INDICATORS,
    CUSTOMER_NAME_NOISE,
    STRIP_FROM_SEARCH
)

logger = logging.getLogger(__name__)


def clean_customer_search_term(name: str) -> str:
    """
    Strip generic business suffix words from a customer name before
    passing it to the API search, so 'magomano suppliers' → 'magomano'.
    """
    if not name:
        return name
    tokens = name.lower().split()
    cleaned = [t for t in tokens if t not in STRIP_FROM_SEARCH]
    return " ".join(cleaned).strip() or name


def clean_customer_name(raw: str) -> str:
    """
    Strip leading noise phrases from a raw extracted customer name.
    E.g. 'orders for Maa's Agrovet' → 'Maa's Agrovet'
    """
    if not raw:
        return raw
    
    # Remove common prefixes
    prefixes_to_remove = [
        r'^details\s+of\s+',
        r'^info(?:rmation)?\s+(?:for|about|of)\s+',
        r'^(?:show|get|find|check)\s+me\s+',
        r'^(?:customer|client|mteja)\s+(?:details|info|information)\s+(?:for|of|about)\s+',
        r'^(?:orders?|purchases)\s+(?:for|of|from)\s+',
        r'^what\s+(?:are|is)\s+the\s+(?:details|info)\s+(?:for|of|about)\s+',
        r'^tell\s+me\s+about\s+',
        r'^analyse\s+',  # Add for behavior analysis
        r'^analyze\s+',  # Add for behavior analysis
        r'^customer\s+behaviour\s+for\s+',  # Add for behavior analysis
        r'^customer\s+behavior\s+for\s+',  # Add for behavior analysis
        r'^how\s+is\s+',  # Add for performance queries
    ]
    
    cleaned = raw
    for prefix in prefixes_to_remove:
        cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
    
    # Remove trailing "behaviour" or "behavior"
    cleaned = re.sub(r'\s+behaviour$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+behavior$', '', cleaned, flags=re.IGNORECASE)
    
    # Also use the existing noise pattern
    cleaned = CUSTOMER_NAME_NOISE.sub("", cleaned).strip()
    
    return cleaned if cleaned else raw


# ---------------------------------------------------------------------------
# Boundary patterns — these mark where a customer name ENDS.
# Order matters: more specific patterns first.
# Pattern groups:
#   "with <number>"         → "with 2 vegimax"
#   "x <number>"            → "x 5 items"
#   standalone qty+item     → "2 vegimax", "3kg sugar"
#   conjunctions            → "and", "na" (Swahili)
#   SAP order keywords      → "quantity", "qty", "order"
# ---------------------------------------------------------------------------
_CUSTOMER_BOUNDARY = re.compile(
    r"""
    \s+
    (?:
        with\s+\d+              # "with 2"
      | x\s*\d+                 # "x2" / "x 2"
      | \d+\s*(?:x\b|pcs?\b|units?\b|pieces?\b)  # "2x", "2pcs"
      | \b\d+\s+[a-zA-Z]        # bare "2 vegimax"
      | \d+\s*(?:kg|g|ml|l|lt)\b  # "500ml", "2kg"
      | \b(?:and|na)\b\s+\d+    # "and 3" / "na 3"
      | \bquantity\b
      | \bqty\b
      | \border\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


class CustomerRules:
    """Rules for customer name extraction"""
    
    @staticmethod
    def looks_like_company(text: str) -> bool:
        """Check if text looks like a company/customer name."""
        if not text or len(text) < 3:
            return False

        text_lower = text.lower()

        for suffix in CUSTOMER_SUFFIX_WORDS:
            if suffix in text_lower:
                return True

        original_words = text.split()
        capitalized_count = sum(1 for w in original_words if w and w[0].isupper())
        if len(original_words) >= 2 and capitalized_count >= len(original_words) - 1:
            for product in PRODUCT_INDICATORS:
                if product in text_lower:
                    return False
            return True

        company_patterns = [
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$',
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Ltd|Limited|Inc|Corp|LLC|Co)$',
            r'^(?:The\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Company|Corporation)$',
            r'^[A-Z]{2,}(?:\s+[A-Z]{2,})*$',
            r'^[A-Z][A-Z\s\']+(?:\s+-\s+[A-Z]+)?$',
        ]

        for pattern in company_patterns:
            if re.match(pattern, text):
                return True

        return False
    
    @staticmethod
    def is_customer_code(text: str) -> bool:
        """Check if text looks like a customer code (e.g., CL01243, V50000)."""
        return bool(re.match(r'^[A-Z]{2,3}\d{4,8}$', text.upper()))
    
    @staticmethod
    def is_listing_query(text: str) -> bool:
        """Check if query is asking to list customers (not a specific one)."""
        text_lower = text.lower()

        if CustomerRules.is_customer_code(text_lower):
            return False

        if re.search(r'[A-Z][A-Za-z\s\']+\s*-\s*[A-Z]+', text):
            return False

        listing_patterns = [
            r'\b(?:all|list|show|display|view|orodhesha|onyesha)\s+(?:customers|clients|companies|wateja)\b',
            r'\b(?:customers|clients|companies|wateja)\s+(?:list|all|wote)\b',
            r'^show\s+me\s+(?:customers|clients|wateja)$',
            r'^list\s+(?:customers|clients|wateja)$',
            r'^get\s+(?:customers|clients|wateja)$',
            r'^all\s+(?:customers|clients|wateja)$',
            r'^customers\s*$',
            r'^wateja\s*$',
        ]

        for pattern in listing_patterns:
            if re.search(pattern, text_lower):
                return True

        if re.search(r'\b\d+\s+(?:customers|clients|wateja)\b', text_lower) and not re.search(r'[A-Z][A-Za-z\s\']+', text):
            return True

        return False

    @staticmethod
    def _trim_at_boundary(candidate: str) -> str:
        """
        Truncate a raw customer candidate at the first quantity/item boundary.

        Examples:
            "magomano supplies with 2 vegimax 30ml" → "magomano supplies"
            "abc traders and 3 items"               → "abc traders"
            "xyz ltd x2 cartons"                    → "xyz ltd"
            "jane agrovet 500ml sugar"              → "jane agrovet"
        """
        boundary_match = _CUSTOMER_BOUNDARY.search(candidate)
        if boundary_match:
            trimmed = candidate[: boundary_match.start()].strip()
            if trimmed:
                logger.debug(
                    f"_trim_at_boundary: '{candidate}' → '{trimmed}' "
                    f"(boundary at pos {boundary_match.start()})"
                )
                return trimmed
        return candidate
    
    @staticmethod
    def _is_price_query(text: str) -> bool:
        """
        Check if the query is asking for a price.
        
        This helps us avoid extracting item names as customer names
        in price queries like "what is the price of X?"
        """
        text_lower = text.lower()
        price_keywords = [
            "price", "cost", "how much", "what's", "what is", "charge",
            "rate", "bei", "gharama", "thamani", "ngapi", "expensive",
            "cheapest", "best price"
        ]
        return any(keyword in text_lower for keyword in price_keywords)

    @staticmethod
    def _is_behavior_query(text: str) -> bool:
        """
        Check if the query is asking for customer behavior analysis.
        
        This helps us extract customer names from patterns like:
        "Analyse Mahakali Enterprises behaviour"
        """
        text_lower = text.lower()
        behavior_keywords = [
            "behaviour", "behavior", "analyse", "analyze", 
            "performance", "performing", "trend", "pattern"
        ]
        return any(keyword in text_lower for keyword in behavior_keywords)

    @staticmethod
    def _extract_customer_from_behavior_query(text: str) -> str:
        """
        Extract customer name from behavior analysis queries.
        
        Examples:
            "Analyse Mahakali Enterprises behaviour" → "Mahakali Enterprises"
            "analyse customer behaviour for Mahakali Enterprises" → "Mahakali Enterprises"
            "analyze customer behavior for ABC Traders" → "ABC Traders"
            "how is XYZ Ltd performing" → "XYZ Ltd"
        """
        text_lower = text.lower()
        
        # Pattern 1: "analyse X behaviour" or "analyze X behavior"
        # Use word boundaries and ensure we don't capture "customer" as the name
        match = re.search(r'\b(?:analyse|analyze)\s+([A-Za-z][\w\s&]+?)\s+(?:behaviour|behavior)\b', text, re.IGNORECASE)
        
        # Pattern 2: "analyse behaviour of X" or "analyze behavior of X"
        if not match:
            match = re.search(r'\b(?:analyse|analyze)\s+(?:behaviour|behavior)\s+of\s+([A-Za-z][\w\s&]+)', text, re.IGNORECASE)
        
        # Pattern 3: "customer behaviour for X" or "customer behavior for X" (MOST IMPORTANT)
        # Fixed: Now captures the text AFTER "for" instead of before
        if not match:
            match = re.search(r'customer\s+(?:behaviour|behavior)\s+for\s+([A-Za-z][\w\s&]+)', text, re.IGNORECASE)
        
        # Pattern 4: "how is X performing"
        if not match:
            match = re.search(r'how\s+is\s+([A-Za-z][\w\s&]+?)\s+performing', text, re.IGNORECASE)
        
        # Pattern 5: "performance of X"
        if not match:
            match = re.search(r'performance\s+of\s+([A-Za-z][\w\s&]+)', text, re.IGNORECASE)
        
        if match:
            customer_name = match.group(1).strip()
            # Remove trailing punctuation
            customer_name = re.sub(r'[?.,!]$', '', customer_name)
            # Filter out common stop words that might have been captured
            invalid_names = ['customer', 'behaviour', 'behavior', 'for', 'of', 'the', 'a', 'an']
            if customer_name and len(customer_name) > 2 and customer_name.lower() not in invalid_names:
                logger.info(f"Extracted customer name from behavior query: '{customer_name}'")
                return customer_name
            else:
                logger.debug(f"Filtered out invalid customer name: '{customer_name}'")
        
        return None

    @staticmethod
    def extract_customer_name(text: str, is_listing: bool = False, is_competitor_pricing: bool = False) -> str:
        """Extract customer name from text."""
        text_lower = text.lower()
        customer_name = None
        
        # =====================================================================
        # FIX: Check if this is a price query FIRST
        # =====================================================================
        # In price queries like "what is the price of Punched Washer?",
        # we should NOT extract "Punched Washer" as a customer name.
        # This prevents the issue where item_name and customer_name both get set.
        # =====================================================================
        is_price_query = CustomerRules._is_price_query(text)
        
        # =====================================================================
        # NEW: Check if this is a behavior query - extract customer name
        # =====================================================================
        is_behavior_query = CustomerRules._is_behavior_query(text)
        
        if is_behavior_query and not is_listing:
            behavior_customer = CustomerRules._extract_customer_from_behavior_query(text)
            if behavior_customer:
                logger.info(f"Extracted customer name from behavior analysis: '{behavior_customer}'")
                return behavior_customer
        
        # Check for pronoun queries
        pronoun_patterns = [
            r'\b(?:their|them|they|his|her|its|wake|yake|yetu|yako)\s+(?:orders?|details?|info|quotation|delivery|invoices?)\b',
            r'(?:show|get|find|check|onyesha|tafuta|angalia)\s+(?:their|his|her|its|wake|yake|yetu|yako)\s+(?:orders?|details?)\b',
            r'\b(?:their|them|they|wake|yake|yetu|yako)\b',
        ]
        is_pronoun_query = any(re.search(pattern, text_lower) for pattern in pronoun_patterns)

        if is_pronoun_query:
            logger.info(f"Pronoun query detected: '{text}'")
            return None
        
        if not is_listing and not is_competitor_pricing:
            # Step 1: Customer code pattern
            customer_code_patterns = [
                r'\b([A-Z]{2,3}\d{4,8})\b',
                r'\b(customer\s+code\s+([A-Z0-9]+))\b',
                r'\b(code\s+([A-Z0-9]+))\b',
            ]

            for pattern in customer_code_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    code = match.group(1) if match.group(1) else (match.group(2) if len(match.groups()) > 1 else None)
                    if code and re.match(r'^[A-Z]{2,3}\d{4,8}$', code.upper()):
                        customer_name = code.upper()
                        logger.info(f"Extracted customer code: '{customer_name}'")
                        return customer_name

            # Step 2: "details of <Name>" pattern
            details_of_match = re.search(
                r'(?:customer|client|mteja)?\s*(?:details|info|information)\s+of\s+([A-Z][A-Za-z0-9\s\'\-&]{2,})',
                text,
                re.IGNORECASE,
            )
            if details_of_match:
                candidate = details_of_match.group(1).strip()
                candidate = clean_customer_name(candidate)
                candidate = CustomerRules._trim_at_boundary(candidate)
                if candidate and len(candidate) > 2:
                    customer_name = candidate
                    logger.info(f"Extracted customer name (details-of-pattern): '{customer_name}'")
                    return customer_name

            # ================================================================
            # Step 3: "for/kwa <Name>" pattern - CONTEXT AWARE
            # ================================================================
            # FIX: Don't extract customer name from price queries using "of" pattern
            # Example: "what is the price of Punched Washer?" should NOT extract customer
            if not is_price_query:
                for_match = re.search(
                    r'\b(?:for|kwa)\s+([A-Z][A-Za-z0-9\s\'\-&]{2,})',
                    text,
                    re.IGNORECASE,
                )
                if for_match:
                    candidate = for_match.group(1).strip()
                    candidate = clean_customer_name(candidate)
                    candidate = CustomerRules._trim_at_boundary(candidate)
                    if candidate.lower() not in {
                        "all", "customers", "customer", "list", "show",
                        "wateja", "mteja", "orodha", "onyesha"
                    }:
                        customer_name = candidate
                        logger.info(f"Extracted customer name (for/kwa-pattern): '{customer_name}'")
                        return customer_name
                else:
                    logger.debug(f"Skipped for/kwa-pattern extraction (price query detected)")
            else:
                logger.debug(f"Skipped for/kwa-pattern extraction (price query detected)")

            # Step 4: "of <Name>" pattern (for "details of X") - CONTEXT AWARE
            # ================================================================
            # FIX: Don't extract customer name from price queries using "of" pattern
            # Example: "price of X" should NOT extract customer
            if not is_price_query:
                of_match = re.search(
                    r'\bof\s+([A-Z][A-Za-z0-9\s\'\-&]{2,})',
                    text,
                    re.IGNORECASE,
                )
                if of_match:
                    candidate = of_match.group(1).strip()
                    candidate = clean_customer_name(candidate)
                    candidate = CustomerRules._trim_at_boundary(candidate)
                    # Don't capture if it's a product or common word
                    if candidate.lower() not in {"items", "products", "stock", "inventory", "orders", "all"}:
                        customer_name = candidate
                        logger.info(f"Extracted customer name (of-pattern): '{customer_name}'")
                        return customer_name
                else:
                    logger.debug(f"Skipped of-pattern extraction (price query detected)")
            else:
                logger.debug(f"Skipped of-pattern extraction (price query detected)")

            # Step 5: "customer/client <Name>" pattern
            name_match = re.search(
                r'(?:customer|client|mteja)\s+([A-Z][A-Za-z0-9\s\'\-&]{2,})',
                text,
                re.IGNORECASE,
            )
            if name_match:
                candidate = name_match.group(1).strip()
                candidate = clean_customer_name(candidate)
                candidate = CustomerRules._trim_at_boundary(candidate)
                if candidate.lower() not in {
                    "all", "customers", "customer", "list", "show",
                    "wateja", "mteja", "orodha", "onyesha"
                }:
                    customer_name = candidate
                    logger.info(f"Extracted customer name (customer-pattern): '{customer_name}'")
                    return customer_name
            
            # ===================================================================
            # Step 6: Direct name extraction (assuming the query starts with customer name)
            # ===================================================================
            # FIXED: Skip if this is a price query or behavior query (already handled)
            # Prevents "Price of X" from being extracted as customer name
            # ===================================================================
            if not customer_name and not is_price_query and not is_behavior_query and not re.search(
                r'^(show|list|get|find|check|what|how|tell|onyesha|orodhesha|tafuta|angalia|analyse|analyze)', 
                text_lower
            ):
                words = text.split()
                if len(words) >= 2:
                    potential_name = " ".join(words[:min(4, len(words))])
                    if re.search(r'[A-Z]', potential_name) and not re.search(r'\d', potential_name):
                        candidate = clean_customer_name(potential_name)
                        if candidate and len(candidate) > 3:
                            customer_name = candidate
                            logger.info(f"Extracted customer name (direct pattern): '{customer_name}'")
                            return customer_name
        
        return customer_name


# Export the class and functions
__all__ = ['CustomerRules', 'clean_customer_name', 'clean_customer_search_term']