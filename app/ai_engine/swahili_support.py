"""
Swahili Language Support Module - V2 (Production Ready)

Upgrades:
- Improved language detection
- Intent classification with confidence scoring
- Smarter entity extraction (noise removal)
- Better code-switching handling
- Safe translation (no broken sentences)
- Backward compatible with your existing system
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

    GREETINGS = ["habari", "jambo", "mambo", "vipi", "poa"]

    ADJECTIVES = ["kubwa", "ndogo", "nzuri", "mbaya", "mpya", "zamani"]

    PRICE_PATTERNS = [
        r'bei\s+ya\s+([a-zA-Z0-9\s\-]+)',
        r'([a-zA-Z0-9\s\-]+?)\s+bei\s+gani',
        r'([a-zA-Z0-9\s\-]+?)\s+ni\s+pesa\s+ngapi',
        r'([a-zA-Z0-9\s\-]+?)\s+ngapi',
        r'gharama\s+ya\s+([a-zA-Z0-9\s\-]+)'
    ]

    # -----------------------------------------------------------------------
    # INIT
    # -----------------------------------------------------------------------

    def __init__(self):
        self.detected_language = "en"
        logger.info("✅ Swahili Support V2 Initialized")

    # -----------------------------------------------------------------------
    # LANGUAGE DETECTION (IMPROVED)
    # -----------------------------------------------------------------------

    def detect_language(self, text: str) -> str:
        words = text.lower().split()

        if not words:
            return "en"

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
        logger.info(f"🌍 Language detected: {lang} ({percent:.1f}%)")

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

        scores = {
            "GET_ITEM_PRICE": 0,
            "GET_STOCK_LEVELS": 0,
            "GET_CUSTOMERS": 0,
            "GREETING": 0
        }

        # Price (highest priority)
        if any(re.search(p, text_lower) for p in self.PRICE_PATTERNS):
            scores["GET_ITEM_PRICE"] += 4

        if "bei" in text_lower or "pesa" in text_lower:
            scores["GET_ITEM_PRICE"] += 2

        if "ngapi" in text_lower:
            scores["GET_ITEM_PRICE"] += 1

        # Stock
        if "hisa" in text_lower or "stock" in text_lower:
            scores["GET_STOCK_LEVELS"] += 3

        # Customer
        if "mteja" in text_lower or "wateja" in text_lower:
            scores["GET_CUSTOMERS"] += 2

        # Greeting
        if any(g in text_lower for g in self.GREETINGS):
            scores["GREETING"] += 3

        # Select best
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        if best_score == 0:
            return {"intent": "UNKNOWN", "confidence": 0.0}

        confidence = min(1.0, round(best_score / 5, 2))

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

        # Extract item using patterns
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
                    logger.info(f"📦 Item extracted: {candidate}")
                    break

        # Customer extraction
        customer_match = re.search(r'mteja\s+([a-zA-Z0-9\s\-]+)', text_lower)
        if customer_match:
            entities["customer_name"] = customer_match.group(1).strip()

        # Date keywords
        if "leo" in text_lower:
            entities["date"] = "today"
        elif "jana" in text_lower:
            entities["date"] = "yesterday"
        elif "kesho" in text_lower:
            entities["date"] = "tomorrow"

        return entities

    # -----------------------------------------------------------------------
    # CODE SWITCHING
    # -----------------------------------------------------------------------

    def normalize_code_switching(self, text: str) -> Tuple[str, str]:
        text_lower = text.lower()

        replacements = {
            "natafuta": "search",
            "nataka": "want",
            "bei ya": "price of",
            "ngapi": "how much"
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

        dictionary = {
            "price": "bei",
            "stock": "hisa",
            "customer": "mteja",
            "available": "inapatikana"
        }

        words = text.split()
        translated = [dictionary.get(w.lower(), w) for w in words]

        return " ".join(translated)

    # -----------------------------------------------------------------------
    # MAIN ENTRY POINT (BACKWARD COMPATIBLE)
    # -----------------------------------------------------------------------

    def process_swahili_query(self, user_message: str) -> Dict:
        lang = self.detect_language(user_message)

        normalized = user_message
        if lang == "mixed":
            normalized, _ = self.normalize_code_switching(user_message)

        intent_data = self._classify_intent_internal(user_message)
        entities = self.extract_entities_swahili(user_message)

        result = {
            "original_text": user_message,
            "detected_language": lang,
            "normalized_text": normalized,
            "intent": intent_data["intent"],
            "confidence": intent_data["confidence"],  # 🆕 added
            "entities": entities
        }

        logger.info(f"🇰🇪 Final Result: {result}")
        return result