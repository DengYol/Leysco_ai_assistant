"""Item name extraction rules"""

import re
import logging
import difflib
from ..constants import PRODUCT_INDICATORS, SIZE_PATTERNS

logger = logging.getLogger(__name__)


class ItemRules:
    """Rules for item name extraction"""
    
    # ====================================================================
    # FIX: Conversational terms that should NOT be extracted as items
    # ====================================================================
    CONVERSATIONAL_TERMS = [
        'yourself', 'about you', 'who are you', 'what are you',
        'tell me about', 'introduce yourself', 'your name',
        'who made you', 'who created you', 'what do you do',
        'how can you help', 'what are your capabilities', 'your features',
        'about yourself', 'tell me about yourself'
    ]
    
    @staticmethod
    def is_product_name(text: str) -> bool:
        """Check if text is likely a product name."""
        if not text:
            return False

        text_lower = text.lower()
        
        # Skip conversational terms
        for term in ItemRules.CONVERSATIONAL_TERMS:
            if term in text_lower:
                return False

        for product in PRODUCT_INDICATORS:
            if product in text_lower:
                return True

        words = text_lower.split()
        if len(words) == 1 and not words[0][0].isupper():
            return True

        return False
    
    @staticmethod
    def validate_sellable_item(item_name: str, api_service, required_size: str = None) -> str:
        """
        Validate that the item is sellable, find a sellable alternative if not.
        This prevents returning packing materials, raw materials, etc.
        
        Args:
            item_name: The item name to validate
            api_service: API service for searching items
            required_size: Optional required size (e.g., "250ml")
        
        Returns:
            Best matching sellable item name, or original if no size specified
        """
        if not item_name or not api_service:
            return item_name
        
        # ====================================================================
        # FIX: Skip validation for conversational terms
        # ====================================================================
        for term in ItemRules.CONVERSATIONAL_TERMS:
            if term in item_name.lower():
                logger.info(f"🔍 Skipping validation for conversational term: '{item_name}'")
                return item_name
        
        # ====================================================================
        # FIX: If no size is specified, return the original item name
        # This allows the pricing handler to search for ALL matching items
        # ====================================================================
        if not required_size:
            logger.info(f"🔍 No size specified for '{item_name}', returning original for multi-item search")
            return item_name
        
        # Search for the item with the required size
        items = api_service.get_items(search=item_name, limit=50)
        if not items:
            return item_name
        
        item_name_lower = item_name.lower()
        normalized_required = ItemRules.normalize_size(required_size)
        logger.info(f"🔍 Searching for items with size: {normalized_required}")
        
        # First, find sellable items that match the size
        size_matches = []
        for item in items:
            if item.get("SellItem") == "Y":
                item_display = item.get("ItemName", "")
                item_size = ItemRules.normalize_size(item_display)
                if item_size and item_size == normalized_required:
                    size_matches.append({
                        "name": item_display,
                        "code": item.get("ItemCode"),
                        "score": difflib.SequenceMatcher(None, item_name_lower, item_display.lower()).ratio()
                    })
        
        if size_matches:
            # Sort by score and return the best match
            size_matches.sort(key=lambda x: x["score"], reverse=True)
            best_match = size_matches[0]
            logger.info(f"✅ Found sellable item with exact size match: '{best_match['name']}' (size: {required_size})")
            return best_match["name"]
        
        # If no sellable with exact size, look for any item with matching size
        size_matches_any = []
        for item in items:
            item_display = item.get("ItemName", "")
            item_size = ItemRules.normalize_size(item_display)
            if item_size and item_size == normalized_required:
                group_cod = item.get("ItmsGrpCod")
                if group_cod != 3:  # Exclude packing material
                    size_matches_any.append({
                        "name": item_display,
                        "score": difflib.SequenceMatcher(None, item_name_lower, item_display.lower()).ratio()
                    })
        
        if size_matches_any:
            size_matches_any.sort(key=lambda x: x["score"], reverse=True)
            best_match = size_matches_any[0]
            logger.warning(f"⚠️ No sellable item with size {required_size}, using non-sellable: '{best_match['name']}'")
            return best_match["name"]
        
        # If no size match found, return the original item name
        logger.info(f"ℹ️ No items found with size {required_size}, returning original: '{item_name}'")
        return item_name

    @staticmethod
    def extract_quotation_items(text: str, customer_name: str, api_service) -> tuple:
        """
        Extract items and quantities from a quotation message.

        Parsing strategy (most-to-least specific):

        Pass 1 — "with QTY NAME SIZE" after the customer name boundary.
            Handles: "... with 2 vegimax 30ml"

        Pass 2 — "with QTY NAME" (no size unit).
            Handles: "... with 3 cartons sugar"

        Pass 3 — Search the full text for "QTY NAME SIZE" anywhere
            (fallback when customer_name split doesn't land us past the items).

        Pass 4 — Plain "QTY NAME" anywhere in full text (last resort).

        In every pass we skip stop-words (with, and, for, quotation, …) so
        we don't accidentally capture structural words as item names.
        """
        items_list = []
        item_name = None
        detected_size = None
        exact_size_match_required = False

        STOP_WORDS = {
            'with', 'and', 'for', 'quotation', 'create', 'make',
            'na', 'kwa', 'a', 'an', 'the', 'of', 'in', 'on',
        }

        # ------------------------------------------------------------------
        # Determine the search region.
        # Prefer the text that comes AFTER the resolved customer name so we
        # don't accidentally re-parse the company name as an item.
        # Fall back to the full text if the customer name isn't present.
        # ------------------------------------------------------------------
        if customer_name and customer_name.lower() in text.lower():
            # Case-insensitive split at the first occurrence of customer_name
            idx = text.lower().find(customer_name.lower())
            search_region = text[idx + len(customer_name):]
        else:
            search_region = text

        # ------------------------------------------------------------------
        # Pass 1: "with QTY NAME SIZE"  e.g. "with 2 vegimax 30ml"
        # ------------------------------------------------------------------
        SIZE_UNIT = r'(?:ml|ML|mL|kg|KG|g(?!ram)|G|l(?!t)|L|lt|LT|pcs?|pieces?|units?|cartons?|bags?|boxes?|crates?)'
        p1 = re.findall(
            r'(?:with\s+)?(\d+)\s+([a-zA-Z][a-zA-Z0-9\-]*)\s+(\d+(?:\.\d+)?\s*' + SIZE_UNIT + r')',
            search_region,
            re.IGNORECASE,
        )
        for qty, name, size in p1:
            if name.lower() in STOP_WORDS:
                continue
            full_name = f"{name} {size}".strip()
            items_list.append({
                "name": full_name,
                "quantity": int(qty),
                "size": size,
            })
            if not item_name:
                item_name = full_name
                detected_size = ItemRules.normalize_size(size)
                exact_size_match_required = True
            logger.info(f"Pass-1 item: qty={qty}, name='{full_name}', size='{size}'")

        # ------------------------------------------------------------------
        # Pass 2: "with QTY NAME" (no size)  e.g. "with 3 sugar"
        # ------------------------------------------------------------------
        if not items_list:
            p2 = re.findall(
                r'(?:with\s+)(\d+)\s+([a-zA-Z][a-zA-Z0-9\-]*)',
                search_region,
                re.IGNORECASE,
            )
            for qty, name in p2:
                if name.lower() in STOP_WORDS:
                    continue
                items_list.append({
                    "name": name,
                    "quantity": int(qty),
                    "size": None,
                })
                if not item_name:
                    item_name = name
                logger.info(f"Pass-2 item (no size): qty={qty}, name='{name}'")

        # ------------------------------------------------------------------
        # Pass 3: Any "QTY NAME SIZE" in the full text (region-independent)
        # ------------------------------------------------------------------
        if not items_list:
            p3 = re.findall(
                r'(\d+)\s+([a-zA-Z][a-zA-Z0-9\-]*)\s+(\d+(?:\.\d+)?\s*' + SIZE_UNIT + r')',
                text,
                re.IGNORECASE,
            )
            for qty, name, size in p3:
                if name.lower() in STOP_WORDS:
                    continue
                full_name = f"{name} {size}".strip()
                items_list.append({
                    "name": full_name,
                    "quantity": int(qty),
                    "size": size,
                })
                if not item_name:
                    item_name = full_name
                    detected_size = ItemRules.normalize_size(size)
                    exact_size_match_required = True
                logger.info(f"Pass-3 item: qty={qty}, name='{full_name}', size='{size}'")

        # ------------------------------------------------------------------
        # Pass 4: Any "QTY NAME" in the full text (last resort)
        # ------------------------------------------------------------------
        if not items_list:
            p4 = re.findall(
                r'(\d+)\s+([a-zA-Z][a-zA-Z0-9\-]*)',
                text,
                re.IGNORECASE,
            )
            for qty, name in p4:
                if name.lower() in STOP_WORDS:
                    continue
                items_list.append({
                    "name": name,
                    "quantity": int(qty),
                    "size": None,
                })
                if not item_name:
                    item_name = name
                logger.info(f"Pass-4 item (no size): qty={qty}, name='{name}'")

        return item_name, items_list, detected_size, exact_size_match_required
    
    @staticmethod
    def extract_item_name(text_lower: str, cleaned_text: str, is_recommendation: bool, api_service) -> tuple:
        """Extract item name from text with sellable item validation."""
        item_name = None
        detected_size = None
        exact_size_match_required = False
        
        # ====================================================================
        # FIX: Skip item extraction for conversational queries
        # ====================================================================
        for term in ItemRules.CONVERSATIONAL_TERMS:
            if term in text_lower:
                logger.info(f"🔍 Conversational query detected, skipping item extraction: '{text_lower[:50]}'")
                return None, detected_size, exact_size_match_required
        
        # ====================================================================
        # Extract size FIRST and store it
        # ====================================================================
        for pattern in SIZE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                if len(match.groups()) == 2:
                    if match.group(1).isdigit() or (match.group(1) and match.group(1).replace('.', '').isdigit()):
                        size_num = match.group(1)
                        size_unit = match.group(2)
                        detected_size = f"{size_num}{size_unit}".lower()
                    elif match.group(2).isdigit() or (match.group(2) and match.group(2).replace('.', '').isdigit()):
                        size_num = match.group(2)
                        size_unit = match.group(1)
                        detected_size = f"{size_num}{size_unit}".lower()
                else:
                    detected_size = match.group(0).lower()

                detected_size = ItemRules.normalize_size(detected_size)
                exact_size_match_required = True
                logger.info(f"✅ Detected size: {detected_size} (exact match required: {exact_size_match_required})")
                break
        
        # Sell out patterns
        sell_out_patterns = [
            r'sell\s+out\s+([a-zA-Z0-9\-\(\)\s]+)',
            r'who\s+would\s+buy\s+([a-zA-Z0-9\-\(\)\s]+)',
            r'which\s+customers?\s+buy\s+([a-zA-Z0-9\-\(\)\s]+)',
        ]

        for pattern in sell_out_patterns:
            match = re.search(pattern, text_lower)
            if match:
                item_name = match.group(1).strip()
                break
        
        # Recommendation patterns
        if is_recommendation and not item_name:
            cross_sell_patterns = [
                r'customers who bought\s+([a-zA-Z0-9\-\(\)\s]+?)\s+also',
                r'also bought with\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'what else do customers buy with\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'wateja walionunua\s+([a-zA-Z0-9\-\(\)\s]+?)\s+pia',
            ]
            for pattern in cross_sell_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    candidate = match.group(1).strip()
                    if candidate and len(candidate) > 1:
                        for prod in PRODUCT_INDICATORS:
                            if prod in candidate.lower():
                                item_name = prod
                                break
                        if not item_name and not ItemRules._looks_like_company(candidate):
                            item_name = candidate
                        break
        
        # Price patterns
        has_price_word = bool(re.search(
            r"\b(price|cost|how\s+much|what'?s?\s*(the)?\s*price|pricing|how\s+expensive|charge|rate|bei|gharama|thamani|ngapi)\b",
            text_lower, re.IGNORECASE
        ))

        if not item_name and has_price_word:
            price_patterns = [
                r'price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'cost\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'how\s+much\s+is\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'what\s+is\s+the\s+price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'what\s+does\s+([a-zA-Z0-9\-\(\)\s]+)\s+cost',
                r'price\s+for\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'best price for\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'cheapest\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'who sells\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'([a-zA-Z0-9\-]+)\s+(\d+(?:ml|ML|mL|kg|KG|g|G|l|L))\s+(?:price|cost)',
                r'([a-zA-Z0-9\-]+)\s+(?:price|cost)\s+(\d+(?:ml|ML|mL|kg|KG|g|G|l|L))',
                r'bei\s+ya\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'gharama\s+ya\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'ngapi\s+([a-zA-Z0-9\-\(\)\s]+)',
            ]
            for pattern in price_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    candidate = match.group(1).strip()
                    if len(match.groups()) > 1 and match.group(2):
                        size_candidate = match.group(2).strip()
                        if detected_size is None:
                            detected_size = ItemRules.normalize_size(size_candidate)
                            exact_size_match_required = True
                            logger.info(f"✅ Detected size from price pattern: {detected_size}")
                    candidate = re.sub(r'\b(price|of|the|a|an|for|in|at|to|is|are|was|were|bei|ya)\b', '', candidate, flags=re.IGNORECASE)
                    candidate = candidate.strip()
                    if candidate and len(candidate) > 1:
                        if any(prod in candidate.lower() for prod in PRODUCT_INDICATORS) or not ItemRules._looks_like_company(candidate):
                            item_name = candidate
                            logger.info(f"Extracted item from price pattern: '{item_name}'")
                            break
        
        # Stock patterns
        if not item_name:
            stock_patterns = [
                r'stock\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'stock\s+levels?\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'inventory\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'hisa\s+za\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'viwango\s+vya\s+hisa\s+za\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'idadi\s+ya\s+([a-zA-Z0-9\-\(\)\s]+)',
            ]
            for pattern in stock_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    candidate = match.group(1).strip()
                    if candidate and len(candidate) > 1:
                        item_name = candidate
                        logger.info(f"Extracted item from stock pattern: '{item_name}'")
                        break
        
        # ====================================================================
        # Validate and correct item name with size awareness
        # If no size is specified, keep the original name for multi-item search
        # ====================================================================
        if item_name and api_service:
            original_item_name = item_name
            logger.info(f"🔍 Validating item '{original_item_name}' with required_size: {detected_size}")
            # Pass detected_size to validate_sellable_item for size-aware matching
            item_name = ItemRules.validate_sellable_item(
                item_name, 
                api_service, 
                required_size=detected_size
            )
            if original_item_name != item_name:
                logger.info(f"✅ Item name corrected from '{original_item_name}' to '{item_name}' (size: {detected_size})")
            else:
                logger.info(f"✅ Item name unchanged: '{item_name}' (size: {detected_size})")
        
        return item_name, detected_size, exact_size_match_required
    
    @staticmethod
    def normalize_size(size_str: str) -> str:
        """Normalize size string to a standard format for comparison."""
        if not size_str:
            return ""
        # Remove whitespace and normalize
        normalized = re.sub(r'\s+', '', size_str.lower())
        # Convert common variations
        normalized = re.sub(r'^(\d+)ml$', r'\1ml', normalized)
        normalized = re.sub(r'^(\d+)kg$', r'\1kg', normalized)
        normalized = re.sub(r'^(\d+)g$', r'\1g', normalized)
        normalized = re.sub(r'^(\d+)l$', r'\1l', normalized)
        return normalized
    
    @staticmethod
    def _looks_like_company(text: str) -> bool:
        """
        Quick check if text looks like a company name.
        
        DYNAMIC: This method uses only universal patterns that apply to ANY
        company across ANY industry, not hardcoded product/industry indicators.
        This ensures it works for agrovets, retailers, manufacturers, etc.
        """
        if not text or len(text) < 3:
            return False
        
        text_lower = text.lower()
        
        # UNIVERSAL COMPANY SUFFIXES (industry-agnostic)
        # These are typical business entity types, not product categories
        universal_suffixes = [
            "suppliers", "supplier", "vendor", "traders", "enterprises", 
            "company", "ltd", "limited", "inc", "group", "associates",
            "agency", "industries", "international", "brothers", "holdings",
            "services", "distributors", "distributor", "corporation", "corp", "llc",
            "global", "partners", "ventures", "enterprise", "business",
            "incorporation", "pty", "co", "plc", "nv", "gmbh", "sarl",
            "s.a.r.l", "pvt", "bv", "kft", "ood", "ehf"
        ]
        
        # UNIVERSAL LEGAL/FORMAL INDICATORS (not product-related)
        formal_indicators = [
            "and co", "and company", "& co", "& company",
            "the company", "the group", "the firm", "the house",
        ]
        
        # Check suffixes
        for suffix in universal_suffixes:
            if text_lower.endswith(suffix):
                return True
            if f" {suffix}" in text_lower:
                return True
        
        # Check formal indicators
        for indicator in formal_indicators:
            if indicator in text_lower:
                return True
        
        # Check if it contains multiple capitalized words (trademark pattern)
        # Examples: "John & Sons", "Mary's Farm", "ABC Traders"
        words = text.split()
        capitalized_count = sum(1 for word in words if word and word[0].isupper())
        if len(words) >= 2 and capitalized_count >= 2:
            # Multiple proper nouns suggest company name
            return True
        
        return False