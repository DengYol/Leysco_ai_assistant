"""
Swahili Language Support Module - V2 (Production Ready)

Upgrades:
- Improved language detection
- Intent classification with confidence scoring
- Smarter entity extraction (noise removal)
- Better code-switching handling
- Safe translation (no broken sentences)
- Backward compatible with your existing system
- ADDED: Strong Swahili word detection for phrases like "nionyeshe", "viwango"
- ADDED: Direct mapping of Swahili queries to intents
- FIXED: Removed premature logging that caused false UNKNOWN entries
"""

import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class SwahiliSupport:

    # -----------------------------------------------------------------------
    # CONFIG DATA
    # -----------------------------------------------------------------------

    COMMON_SWAHILI_WORDS = {
        "na", "ni", "ya", "za", "kwa", "katika", "kwenye",
        "tafuta", "taka", "ona", "uliza", "leta",
        "bei", "pesa", "gharama", "hisa",
        "mteja", "wateja", "bidhaa", "vitu",
        "leo", "jana", "kesho"
    }

    # Strong Swahili indicators (words that are uniquely Swahili)
    STRONG_SWAHILI_WORDS = {
        "nionyeshe", "onyesha", "taja", "orodhesha", "hesabu", "hesabia",
        "tafuta", "pata", "angalia", "soma", "andika", "sema", "uliza",
        "jibu", "sawasawa", "pole", "asante", "karibu", "samahani",
        "viwango", "idadi", "zilizopo", "hifadhi", "stoko",
        "ghala", "maghala", "ny maghala",
        "nukuu", "nukta", "maagizo", "agizo",
        "msambazaji", "wasambazaji", "kampuni", "makampuni",
    }

    GREETINGS = ["habari", "jambo", "mambo", "vipi", "poa", "sema", "sasa", "freshi", "nzuri"]

    ADJECTIVES = ["kubwa", "ndogo", "nzuri", "mbaya", "mpya", "zamani"]

    # Direct intent mapping for Swahili phrases
    INTENT_MAPPING = {
        # Stock queries
        "hisa": "GET_STOCK_LEVELS",
        "viwango vya hisa": "GET_STOCK_LEVELS",
        "idadi ya hisa": "GET_STOCK_LEVELS",
        "zilizopo": "GET_STOCK_LEVELS",
        "stoko": "GET_STOCK_LEVELS",
        
        # Price queries
        "bei": "GET_ITEM_PRICE",
        "gharama": "GET_ITEM_PRICE",
        "thamani": "GET_ITEM_PRICE",
        "pesa": "GET_ITEM_PRICE",
        "ngapi": "GET_ITEM_PRICE",
        
        # Items queries
        "bidhaa": "GET_ITEMS",
        "vitu": "GET_ITEMS",
        "mazao": "GET_ITEMS",
        "orodha ya bidhaa": "GET_ITEMS",
        
        # Customer queries
        "mteja": "GET_CUSTOMERS",
        "wateja": "GET_CUSTOMERS",
        "msambazaji": "GET_CUSTOMERS",
        
        # Quotation queries
        "nukuu": "CREATE_QUOTATION",
        "tengeneza nukuu": "CREATE_QUOTATION",
        "unda nukuu": "CREATE_QUOTATION",
        
        # Delivery queries
        "usafirishaji": "GET_OUTSTANDING_DELIVERIES",
        "maagizo": "GET_OUTSTANDING_DELIVERIES",
        
        # Warehouse queries
        "ghala": "GET_WAREHOUSES",
        "maghala": "GET_WAREHOUSES",
        "ny maghala": "GET_WAREHOUSES",
    }

    PRICE_PATTERNS = [
        r'bei\s+ya\s+([a-zA-Z0-9\s\-]+)',
        r'([a-zA-Z0-9\s\-]+?)\s+bei\s+gani',
        r'([a-zA-Z0-9\s\-]+?)\s+ni\s+pesa\s+ngapi',
        r'([a-zA-Z0-9\s\-]+?)\s+ngapi',
        r'gharama\s+ya\s+([a-zA-Z0-9\s\-]+)'
    ]

    STOCK_PATTERNS = [
        r'viwango\s+vya\s+hisa',
        r'angalia\s+hisa',
        r'hisa\s+za\s+([a-zA-Z0-9\s\-]+)',
        r'idadi\s+ya\s+([a-zA-Z0-9\s\-]+)',
        r'nionyeshe\s+hisa',
    ]

    # Swahili request prefixes to remove
    PREFIXES_TO_REMOVE = [
        r'^nionyeshe\s+',   # "show me"
        r'^onyesha\s+',      # "show"
        r'^taja\s+',         # "list"
        r'^orodhesha\s+',    # "list"
        r'^hesabu\s+',       # "calculate"
        r'^tafuta\s+',       # "search"
        r'^pata\s+',         # "get"
        r'^angalia\s+',      # "check"
        r'^soma\s+',         # "read"
        r'^tengeneza\s+',    # "create"
        r'^unda\s+',         # "create"
    ]

    # -----------------------------------------------------------------------
    # INIT
    # -----------------------------------------------------------------------

    def __init__(self):
        self.detected_language = "en"
        logger.info("✅ Swahili Support V2 Initialized")

    # -----------------------------------------------------------------------
    # LANGUAGE DETECTION (IMPROVED with strong indicators)
    # -----------------------------------------------------------------------

    def detect_language(self, text: str) -> str:
        words = text.lower().split()

        if not words:
            return "en"

        # Check for strong Swahili indicators first
        strong_sw_count = sum(
            1 for w in words
            if w in self.STRONG_SWAHILI_WORDS
        )
        
        # Check for strong Swahili phrases (multiple words)
        text_lower = text.lower()
        strong_phrase_count = 0
        for phrase in ["viwango vya hisa", "tengeneza nukuu", "unda nukuu", "nionyeshe hisa"]:
            if phrase in text_lower:
                strong_phrase_count += 1

        # If any strong Swahili indicator found, default to Swahili
        if strong_sw_count > 0 or strong_phrase_count > 0:
            lang = "sw"
            percent = 100.0
        else:
            sw_count = sum(
                1 for w in words
                if w in self.COMMON_SWAHILI_WORDS or w in self.GREETINGS
            )
            percent = (sw_count / len(words)) * 100

            if percent >= 60:
                lang = "sw"
            elif percent >= 30:
                lang = "mixed"
            else:
                lang = "en"

        self.detected_language = lang
        logger.debug(f"🌍 Language detected: {lang} ({percent:.1f}%)")  # Changed to DEBUG

        return lang

    # -----------------------------------------------------------------------
    # INTENT CLASSIFICATION (WITH CONFIDENCE)
    # -----------------------------------------------------------------------

    def classify_swahili_intent(self, text: str) -> str:
        """
        Backward-compatible method (returns only intent)
        """
        return self._classify_intent_internal(text)["intent"]

    def _classify_intent_internal(self, text: str) -> Dict:
        text_lower = text.lower()

        # First, check direct mapping for Swahili phrases
        for phrase, intent in self.INTENT_MAPPING.items():
            if phrase in text_lower:
                logger.debug(f"🎯 Direct mapping: '{phrase}' -> {intent}")  # Changed to DEBUG
                return {"intent": intent, "confidence": 0.85}

        scores = {
            "GET_ITEM_PRICE": 0,
            "GET_STOCK_LEVELS": 0,
            "GET_ITEMS": 0,
            "GET_CUSTOMERS": 0,
            "CREATE_QUOTATION": 0,
            "GET_OUTSTANDING_DELIVERIES": 0,
            "GET_WAREHOUSES": 0,
            "GREETING": 0
        }

        # Stock level patterns (highest priority)
        for pattern in self.STOCK_PATTERNS:
            if re.search(pattern, text_lower):
                scores["GET_STOCK_LEVELS"] += 5
                logger.debug(f"📊 Stock pattern matched: {pattern}")  # Changed to DEBUG

        # Stock keywords
        if any(word in text_lower for word in ["hisa", "viwango", "idadi", "zilizopo", "stoko"]):
            scores["GET_STOCK_LEVELS"] += 3

        # Price patterns
        if any(re.search(p, text_lower) for p in self.PRICE_PATTERNS):
            scores["GET_ITEM_PRICE"] += 4

        # Price keywords
        if any(word in text_lower for word in ["bei", "pesa", "gharama", "thamani"]):
            scores["GET_ITEM_PRICE"] += 2

        if "ngapi" in text_lower:
            scores["GET_ITEM_PRICE"] += 1

        # Items keywords
        if any(word in text_lower for word in ["bidhaa", "mazao", "vitu", "orodha"]):
            scores["GET_ITEMS"] += 3

        # Customer keywords
        if any(word in text_lower for word in ["mteja", "wateja", "msambazaji"]):
            scores["GET_CUSTOMERS"] += 2

        # Quotation keywords
        if any(word in text_lower for word in ["nukuu", "tengeneza", "unda"]):
            scores["CREATE_QUOTATION"] += 3

        # Delivery keywords
        if any(word in text_lower for word in ["usafirishaji", "maagizo", "delivery"]):
            scores["GET_OUTSTANDING_DELIVERIES"] += 3

        # Warehouse keywords
        if any(word in text_lower for word in ["ghala", "maghala"]):
            scores["GET_WAREHOUSES"] += 3

        # Greeting
        if any(g in text_lower for g in self.GREETINGS):
            scores["GREETING"] += 3

        # Select best
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        if best_score == 0:
            return {"intent": "UNKNOWN", "confidence": 0.0}

        confidence = min(1.0, round(best_score / 5, 2))

        logger.debug(f"🎯 Intent scores: {scores}")  # Changed to DEBUG
        logger.debug(f"🎯 Selected intent: {best_intent} (confidence: {confidence})")  # Changed to DEBUG

        return {
            "intent": best_intent,
            "confidence": confidence
        }

    # -----------------------------------------------------------------------
    # ENTITY EXTRACTION (IMPROVED)
    # -----------------------------------------------------------------------

    def extract_entities_swahili(self, text: str) -> Dict:
        text_lower = text.lower()

        entities = {
            "item_name": None,
            "customer_name": None,
            "quantity": None,
            "warehouse": None,
            "date": None,
            "detail_mode": False
        }

        # Quantity (digits)
        num_match = re.search(r'\b\d+\b', text)
        if num_match:
            entities["quantity"] = int(num_match.group())

        # Extract item from stock query
        stock_match = re.search(r'hisa\s+(?:ya|za)\s+(.+)', text_lower)
        if stock_match:
            candidate = stock_match.group(1).strip()
            # Remove trailing words
            candidate = re.sub(r'\s+(?:ni|na|ya|za|kwa|katika)$', '', candidate)
            if len(candidate) > 2:
                entities["item_name"] = candidate
                logger.debug(f"📦 Item extracted from stock query: {candidate}")  # Changed to DEBUG

        # Extract item from price query
        for pattern in self.PRICE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                candidate = match.group(1).strip()
                # Remove adjectives
                for adj in self.ADJECTIVES:
                    candidate = candidate.replace(adj, "").strip()
                # Clean trailing noise
                candidate = re.sub(r'\s+(ya|za|na)$', '', candidate).strip()
                if len(candidate) > 2:
                    entities["item_name"] = candidate
                    logger.debug(f"📦 Item extracted from price query: {candidate}")  # Changed to DEBUG
                    break

        # Extract item from general query
        if not entities["item_name"]:
            # Look for patterns like "angalia X" or "nionyeshe X"
            general_match = re.search(r'(?:angalia|nionyeshe|onyesha|taja|orodhesha)\s+([a-zA-Z0-9\s\-]+)', text_lower)
            if general_match:
                candidate = general_match.group(1).strip()
                # Remove common suffixes
                candidate = re.sub(r'\s+(?:na|ya|za)$', '', candidate)
                if len(candidate) > 2 and len(candidate) < 50:
                    entities["item_name"] = candidate
                    logger.debug(f"📦 Item extracted from general query: {candidate}")  # Changed to DEBUG

        # Customer extraction
        customer_match = re.search(r'mteja\s+([a-zA-Z0-9\s\-]+)', text_lower)
        if customer_match:
            entities["customer_name"] = customer_match.group(1).strip()

        # Alternative customer pattern
        customer_match2 = re.search(r'kwa\s+([a-zA-Z0-9\s\-]+?)(?:\s+na|\s+ya|$)', text_lower)
        if customer_match2 and not entities["customer_name"]:
            candidate = customer_match2.group(1).strip()
            if len(candidate) > 2:
                entities["customer_name"] = candidate

        # Date keywords
        if "leo" in text_lower:
            entities["date"] = "today"
        elif "jana" in text_lower:
            entities["date"] = "yesterday"
        elif "kesho" in text_lower:
            entities["date"] = "tomorrow"

        return entities

    # -----------------------------------------------------------------------
    # NORMALIZE TEXT (Remove Swahili prefixes)
    # -----------------------------------------------------------------------

    def normalize_swahili_text(self, text: str) -> str:
        """Remove Swahili request prefixes to get the core query."""
        text_lower = text.lower()
        normalized = text_lower
        
        for prefix in self.PREFIXES_TO_REMOVE:
            normalized = re.sub(prefix, '', normalized, flags=re.IGNORECASE)
        
        # Translate common Swahili query patterns to English
        if "hisa" in normalized:
            normalized = re.sub(r'hisa\s+(?:ya|za)\s+', 'stock levels of ', normalized)
            normalized = normalized.replace("viwango vya hisa", "stock levels")
            normalized = normalized.replace("angalia hisa", "check stock")
        
        if "bei" in normalized:
            normalized = re.sub(r'bei\s+ya\s+', 'price of ', normalized)
        
        return normalized.strip()

    # -----------------------------------------------------------------------
    # CODE SWITCHING
    # -----------------------------------------------------------------------

    def normalize_code_switching(self, text: str) -> Tuple[str, str]:
        text_lower = text.lower()

        replacements = {
            "natafuta": "search",
            "nataka": "want",
            "bei ya": "price of",
            "ngapi": "how much",
            "nionyeshe": "show me",
            "onyesha": "show",
            "taja": "list",
            "orodhesha": "list",
            "angalia": "check",
            "hisa": "stock",
            "viwango vya hisa": "stock levels",
            "idadi ya": "quantity of",
            "mteja": "customer",
            "wateja": "customers",
            "bidhaa": "items",
            "nukuu": "quotation",
            "tengeneza nukuu": "create quotation",
            "unda nukuu": "create quotation",
            "ghala": "warehouse",
            "maghala": "warehouses",
        }

        normalized = text_lower
        for k, v in replacements.items():
            normalized = normalized.replace(k, v)

        return normalized, "mixed"

    # -----------------------------------------------------------------------
    # SAFE TRANSLATION
    # -----------------------------------------------------------------------

    def translate_response(self, text: str, target_lang: str = "sw") -> str:
        if target_lang != "sw":
            return text

        # More comprehensive translation dictionary
        dictionary = {
            "price": "bei",
            "prices": "bei",
            "stock": "hisa",
            "stocks": "hisa",
            "customer": "mteja",
            "customers": "wateja",
            "available": "inapatikana",
            "unavailable": "haipatikani",
            "total": "jumla",
            "item": "bidhaa",
            "items": "bidhaa",
            "quantity": "idadi",
            "warehouse": "ghala",
            "warehouses": "maghala",
            "quotation": "nukuu",
            "quotations": "nukuu",
            "create": "unda",
            "created": "imeundwa",
            "successfully": "kikamilifu",
            "failed": "imeshindwa",
            "error": "hitilafu",
            "please": "tafadhali",
            "try again": "jaribu tena",
            "found": "imepatikana",
            "not found": "haijapatikana",
            "show": "onyesha",
            "show me": "nionyeshe",
            "check": "angalia",
            "list": "orodhesha",
        }

        words = text.split()
        translated_words = []
        for word in words:
            # Remove punctuation for lookup
            clean_word = word.lower().rstrip('.,!?;:')
            if clean_word in dictionary:
                # Preserve original case pattern
                if word[0].isupper():
                    translated_words.append(dictionary[clean_word].capitalize())
                else:
                    translated_words.append(dictionary[clean_word])
            else:
                translated_words.append(word)

        return " ".join(translated_words)

    # -----------------------------------------------------------------------
    # MAIN ENTRY POINT (BACKWARD COMPATIBLE)
    # -----------------------------------------------------------------------

    def process_swahili_query(self, user_message: str) -> Dict:
        """
        Process Swahili query - returns preliminary result without logging.
        The caller (intent_classifier) will log the final result after all processing.
        """
        lang = self.detect_language(user_message)

        normalized = user_message
        if lang == "mixed":
            normalized, _ = self.normalize_code_switching(user_message)
        elif lang == "sw":
            # Also normalize pure Swahili to help with intent detection
            normalized = self.normalize_swahili_text(user_message)

        intent_data = self._classify_intent_internal(user_message)
        entities = self.extract_entities_swahili(user_message)

        result = {
            "original_text": user_message,
            "detected_language": lang,
            "normalized_text": normalized,
            "intent": intent_data["intent"],
            "confidence": intent_data["confidence"],
            "entities": entities
        }

        # Only log at DEBUG level - final logging is done by intent_classifier
        logger.debug(f"🇰🇪 Swahili processing result: intent={result['intent']}, confidence={result['confidence']}")
        
        return result