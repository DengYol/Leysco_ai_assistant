"""
Swahili Language Support Module
Handles Swahili queries, translations, and bilingual responses
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SwahiliSupport:
    """
    Provides Swahili language support for:
    - Intent classification
    - Entity extraction
    - Response translation
    - Code-switching (Camp/Eng)
    """
    
    # Common Swahili greetings and conversational phrases
    GREETINGS = {
        "hello": ["habari", "jambo", "hujambo", "sijambo", "mambo", "vipi"],
        "good morning": ["habari za asubuhi", "subuhi"],
        "good afternoon": ["habari za mchana", "mchana"],
        "good evening": ["habari za jioni", "jioni"],
        "how are you": ["habari yako", "uko poa", "poa", "mzima"],
        "thank you": ["asante", "shukrani", "nashukuru"],
        "welcome": ["karibu"],
        "goodbye": ["kwaheri", "baadaye", "tutaonana"],
        "yes": ["ndiyo", "ndio", "ehe"],
        "no": ["hapana", "sio", "siyo"],
        "okay": ["sawa", "poa", "tz"],
    }
    
    # Business terms in Swahili
    BUSINESS_TERMS = {
        # Products
        "product": ["bidhaa", "produkti"],
        "item": ["kitu", "vitu"],
        "price": ["bei", "gharama"],
        "cost": ["gharama"],
        "stock": ["hisa", "akiba"],
        "inventory": ["orodha", "hisa"],
        
        # Customers
        "customer": ["mteja", "wateja"],
        "client": ["mteja", "mlengwa"],
        "company": ["kampuni"],
        "business": ["biashara"],
        
        # Orders
        "order": ["oda", "agizo"],
        "orders": ["oda", "maagizo"],
        "quotation": ["nukuu", "bei"],
        "quote": ["nukuu"],
        "delivery": ["usafirishaji", "wasilisho"],
        "invoice": ["ankra", "risiti"],
        
        # Warehouse
        "warehouse": ["ghala", "bohari"],
        "store": ["duka", "shopo"],
        
        # Actions
        "show": ["onyesha", "nionyeshe"],
        "list": ["orodhesha"],
        "find": ["tafuta"],
        "search": ["tafuta"],
        "create": ["unda", "tengeneza"],
        "make": ["tengeneza"],
        "check": ["angalia"],
        "view": ["tazama"],
        
        # Questions
        "how many": ["ngapi"],
        "how much": ["bei gani", "gharama gani"],
        "what": ["nini"],
        "where": ["wapi"],
        "when": ["lini"],
        "which": ["ipi"],
        "who": ["nani"],
        
        # Time
        "today": ["leo"],
        "yesterday": ["jana"],
        "tomorrow": ["kesho"],
        "now": ["sasa"],
        "recent": ["karibuni", "za hivi karibuni"],
        
        # Quantities
        "few": ["chache"],
        "many": ["nyingi"],
        "all": ["zote"],
        "some": ["baadhi"],
        
        # Status
        "available": ["inapatikana", "ipo"],
        "out of stock": ["imeisha"],
        "low": ["chini"],
        "critical": ["muhimu"],
        "pending": ["inasubiri"],
        "completed": ["imekamilika"],
    }
    
    # Product names (usually remain in English)
    PRODUCT_NAMES = [
        "vegimax", "easeed", "agriscope", "tosheka", "kh500", "mh401",
        "cabbage", "tomato", "maize", "mahindi", "nyanya", "kabeji",
        "karoti", "vitunguu", "mbegu", "mbolea", "dawa"
    ]
    
    # Common Swahili stop words to ignore in entity extraction
    STOP_WORDS = {
        "na", "kwa", "ya", "za", "la", "cha", "vya", "mwa",
        "katika", "kwenye", "kutoka", "hadi", "mpaka", 
        "ni", "si", "ndio", "hapana", "sawa",
        "hii", "hizo", "huo", "hicho", "yule", "wale",
        "angu", "ako", "ake", "etu", "enu", "ao",
        "nini", "nani", "lini", "wapi", "vipi", "gani",
        "sana", "kabisa", "pia", "tena", "bado",
        "tu", "basi", "kisha", "ndipo", "ndiyo"
    }
    
    # Price query patterns in Swahili
    PRICE_PATTERNS = [
        r'bei\s+ya\s+([a-zA-Z0-9\s\-]+)',           # bei ya [product]
        r'([a-zA-Z0-9\s\-]+?)\s+bei\s+gani',        # [product] bei gani
        r'([a-zA-Z0-9\s\-]+?)\s+ni\s+pesa\s+ngapi', # [product] ni pesa ngapi
        r'([a-zA-Z0-9\s\-]+?)\s+ngapi',              # [product] ngapi
        r'gharama\s+ya\s+([a-zA-Z0-9\s\-]+)',       # gharama ya [product]
        r'([a-zA-Z0-9\s\-]+?)\s+gharama\s+gani',    # [product] gharama gani
    ]
    
    def __init__(self):
        self.detected_language = "en"  # Default to English
        logger.info("✅ Swahili support initialized")
    
    # -----------------------------------------------------------------------
    # LANGUAGE DETECTION
    # -----------------------------------------------------------------------
    
    def detect_language(self, text: str) -> str:
        """
        Detect if text is Swahili, English, or mixed (code-switching)
        """
        text_lower = text.lower()
        words = text_lower.split()
        
        # Count Swahili words
        swahili_count = 0
        swahili_words = []
        
        # Check each word against our Swahili vocabulary
        for word in words:
            # Check greetings
            for eng, swa_list in self.GREETINGS.items():
                if word in swa_list:
                    swahili_count += 1
                    swahili_words.append(word)
                    break
            
            # Check business terms
            for eng, swa_list in self.BUSINESS_TERMS.items():
                if word in swa_list:
                    swahili_count += 1
                    swahili_words.append(word)
                    break
        
        # Calculate percentage of Swahili words
        if len(words) == 0:
            self.detected_language = "en"
        else:
            swahili_percent = (swahili_count / len(words)) * 100
            
            if swahili_percent >= 70:
                self.detected_language = "sw"
            elif swahili_percent >= 30:
                self.detected_language = "mixed"
            else:
                self.detected_language = "en"
        
        logger.info(f"🌍 Detected language: {self.detected_language} ({swahili_count}/{len(words)} Swahili words)")
        logger.info(f"   Swahili words: {swahili_words}")
        
        return self.detected_language
    
    # -----------------------------------------------------------------------
    # SWAHILI INTENT CLASSIFICATION
    # -----------------------------------------------------------------------
    
    def classify_swahili_intent(self, text: str) -> str:
        """
        Classify intent from Swahili text
        Enhanced with better price query detection
        """
        text_lower = text.lower()
        
        # 🆕 Check for price queries first (most common)
        is_price_query = any(re.search(pattern, text_lower) for pattern in self.PRICE_PATTERNS)
        
        if is_price_query:
            logger.info(f"💰 Detected price query in Swahili")
            # Check if it's asking about customer price
            if any(word in text_lower for word in ["mteja", "wateja", "customer"]):
                return "GET_CUSTOMER_PRICE"
            else:
                return "GET_ITEM_PRICE"
        
        # Greetings
        for eng, swa_list in self.GREETINGS.items():
            if any(greeting in text_lower for greeting in swa_list):
                if eng in ["hello", "good morning", "good afternoon", "good evening"]:
                    return "GREETING"
                elif eng == "thank you":
                    return "THANKS"
                elif eng == "goodbye":
                    return "SMALL_TALK"
        
        # Product/Item queries
        if any(word in text_lower for word in ["bidhaa", "vitu", "kitu", "produkti"]):
            if any(word in text_lower for word in ["bei", "gharama"]):
                return "GET_ITEM_PRICE"
            elif any(word in text_lower for word in ["hisa", "akiba", "orodha"]):
                return "GET_STOCK_LEVELS"
            else:
                return "GET_ITEMS"
        
        # Price queries (second pass for other patterns)
        if any(word in text_lower for word in ["bei", "gharama"]):
            if "mteja" in text_lower or "wateja" in text_lower:
                return "GET_CUSTOMER_PRICE"
            else:
                return "GET_ITEM_PRICE"
        
        # Stock queries
        if any(word in text_lower for word in ["hisa", "akiba", "orodha"]):
            if any(word in text_lower for word in ["chini", "imeisha"]):
                return "GET_LOW_STOCK_ALERTS"
            else:
                return "GET_STOCK_LEVELS"
        
        # Customer queries
        if any(word in text_lower for word in ["mteja", "wateja"]):
            if "bei" in text_lower:
                return "GET_CUSTOMER_PRICE"
            elif "oda" in text_lower:
                return "GET_CUSTOMER_ORDERS"
            else:
                return "GET_CUSTOMERS"
        
        # Order/quotation queries
        if any(word in text_lower for word in ["oda", "agizo", "maagizo"]):
            return "GET_CUSTOMER_ORDERS"
        
        if any(word in text_lower for word in ["nukuu", "bei"]):
            if any(word in text_lower for word in ["unda", "tengeneza", "fanya"]):
                return "CREATE_QUOTATION"
            else:
                return "GET_QUOTATIONS"
        
        # Warehouse queries
        if any(word in text_lower for word in ["ghala", "bohari", "duka"]):
            return "GET_WAREHOUSES"
        
        # Delivery queries
        if any(word in text_lower for word in ["usafirishaji", "wasilisho"]):
            return "TRACK_DELIVERY"
        
        # Training/help queries
        if any(word in text_lower for word in ["jinsi", "namna", "mafunzo", "saidia"]):
            return "TRAINING_MODULE"
        
        # If no match, return UNKNOWN
        return "UNKNOWN"
    
    # -----------------------------------------------------------------------
    # SWAHILI ENTITY EXTRACTION
    # -----------------------------------------------------------------------
    
    def extract_entities_swahili(self, text: str) -> Dict:
        """
        Extract entities from Swahili text
        Enhanced for price queries like "Vegimax ni pesa ngapi?"
        """
        text_lower = text.lower()
        entities = {
            "item_name": None,
            "customer_name": None,
            "quantity": None,
            "warehouse": None,
            "date": None,
            "detail_mode": False
        }
        
        # Extract quantity (numbers)
        digit_match = re.search(r"\b(\d+)\b", text)
        if digit_match:
            entities["quantity"] = int(digit_match.group(1))
        
        # Extract quantity words in Swahili
        swahili_numbers = {
            "moja": 1, "mbili": 2, "tatu": 3, "nne": 4, "tano": 5,
            "sita": 6, "saba": 7, "nane": 8, "tisa": 9, "kumi": 10,
            "ishirini": 20, "thelathini": 30, "arobaini": 40, "hamsini": 50,
            "sitini": 60, "sabini": 70, "themanini": 80, "tisini": 90, "mia": 100,
            "elfu": 1000, "milioni": 1000000
        }
        
        for num_word, num_value in swahili_numbers.items():
            if num_word in text_lower:
                entities["quantity"] = num_value
                break
        
        # 🆕 IMPROVED: Extract product name for price queries using patterns
        for pattern in self.PRICE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                candidate = match.group(1).strip()
                # Clean up candidate
                for stop in self.STOP_WORDS:
                    candidate = candidate.replace(f" {stop}", "")
                # Remove common suffixes
                candidate = re.sub(r'\s+(na|ya|za|la)$', '', candidate).strip()
                
                if candidate and len(candidate) > 2:
                    entities["item_name"] = candidate
                    logger.info(f"📦 Extracted item from price pattern: '{candidate}'")
                    # Continue to extract other entities but return early with item
                    break
        
        # If item still not found, try product indicators
        if not entities["item_name"]:
            product_indicators = ["bidhaa", "kitu", "produkti", "vitu"]
            for indicator in product_indicators:
                if indicator in text_lower:
                    # Try to find what comes after the indicator
                    pattern = rf"{indicator}\s+([a-zA-Z0-9\s\-]+)"
                    match = re.search(pattern, text_lower)
                    if match:
                        candidate = match.group(1).strip()
                        # Clean up candidate
                        for stop in self.STOP_WORDS:
                            candidate = candidate.replace(f" {stop}", "")
                        if candidate and len(candidate) > 2:
                            entities["item_name"] = candidate
                            logger.info(f"📦 Extracted item from indicator: '{candidate}'")
                            break
        
        # If still not found, try known product names
        if not entities["item_name"]:
            for product in self.PRODUCT_NAMES:
                if product in text_lower:
                    entities["item_name"] = product
                    logger.info(f"📦 Extracted known product: '{product}'")
                    break
        
        # Extract customer name
        customer_indicators = ["mteja", "wateja", "kampuni", "biashara", "kwa"]
        for indicator in customer_indicators:
            if indicator in text_lower:
                # Try to find what comes after the indicator
                pattern = rf"{indicator}\s+([a-zA-Z0-9\s\-]+)"
                match = re.search(pattern, text_lower)
                if match:
                    candidate = match.group(1).strip()
                    # Clean up candidate
                    for stop in self.STOP_WORDS:
                        candidate = candidate.replace(f" {stop}", "")
                    # Remove common suffixes
                    candidate = re.sub(r'\s+(na|ya|za|la)$', '', candidate).strip()
                    
                    if candidate and len(candidate) > 2:
                        # Check if it's actually a product name
                        if candidate.lower() in self.PRODUCT_NAMES:
                            entities["item_name"] = candidate
                        else:
                            entities["customer_name"] = candidate
                            logger.info(f"👥 Extracted customer: '{candidate}'")
                        break
        
        # Extract warehouse
        warehouse_indicators = ["ghala", "bohari", "duka", "shopo", "kwenye"]
        for indicator in warehouse_indicators:
            if indicator in text_lower:
                pattern = rf"{indicator}\s+([a-zA-Z0-9\s\-]+)"
                match = re.search(pattern, text_lower)
                if match:
                    candidate = match.group(1).strip()
                    if candidate and len(candidate) > 2:
                        entities["warehouse"] = candidate
                        logger.info(f"🏭 Extracted warehouse: '{candidate}'")
                        break
        
        # Extract date
        date_keywords = {
            "leo": "today",
            "jana": "yesterday",
            "kesho": "tomorrow",
            "wiki": "week",
            "mwezi": "month",
            "mwaka": "year"
        }
        for sw, eng in date_keywords.items():
            if sw in text_lower:
                entities["date"] = eng
                logger.info(f"📅 Extracted date: '{eng}'")
                break
        
        # Detail mode
        if any(word in text_lower for word in ["maelezo", "undani", "kamili", "zaidi"]):
            entities["detail_mode"] = True
            logger.info(f"🔍 Detail mode enabled")
        
        logger.info(f"🇰🇪 Swahili entities extracted: {entities}")
        return entities
    
    # -----------------------------------------------------------------------
    # RESPONSE TRANSLATION
    # -----------------------------------------------------------------------
    
    def translate_response(self, response: str, target_lang: str = "sw") -> str:
        """
        Simple translation of common response phrases
        For complex responses, would integrate with translation API
        """
        if target_lang != "sw":
            return response
        
        # Common response translations
        translations = {
            # Greetings
            "Hello": "Habari",
            "Hi": "Mambo",
            "Good morning": "Habari za asubuhi",
            "Good afternoon": "Habari za mchana",
            "Good evening": "Habari za jioni",
            "Welcome": "Karibu",
            "Thank you": "Asante",
            "Thanks": "Asante",
            "You're welcome": "Karibu tena",
            "Goodbye": "Kwaheri",
            
            # Common phrases
            "Here are": "Hizi ndizo",
            "I found": "Nimepata",
            "Found": "Nimepata",
            "Showing": "Inaonyesha",
            "Items": "Bidhaa",
            "Products": "Bidhaa",
            "Customers": "Wateja",
            "Customer": "Mteja",
            "Price": "Bei",
            "Prices": "Bei",
            "Stock": "Hisa",
            "Available": "Inapatikana",
            "Out of stock": "Imeisha",
            "Low stock": "Hisa chache",
            "Critical": "Muhimu",
            "Order": "Oda",
            "Orders": "Oda",
            "Quotation": "Nukuu",
            "Quotations": "Nukuu",
            "Warehouse": "Ghala",
            "Warehouses": "Maghala",
            "Delivery": "Usafirishaji",
            "Deliveries": "Usafirishaji",
            
            # Actions
            "Please specify": "Tafadhali taja",
            "Try asking": "Jaribu kuuliza",
            "For example": "Kwa mfano",
            "Tip": "Kidokezo",
            "Note": "Kumbuka",
            
            # Questions
            "What would you like to know?": "Ungependa kujua nini?",
            "How can I help you?": "Nikusaidiye vipi?",
            "Anything else?": "Kitu kingine?",
            
            # Errors
            "not found": "haipatikani",
            "No results": "Hakuna matokeo",
            "Error": "Hitilafu",
            "Please try again": "Tafadhali jaribu tena",
        }
        
        # Simple word-by-word translation (for demo)
        # In production, use a proper translation API like Google Translate
        translated = response
        for eng, sw in translations.items():
            translated = translated.replace(eng, sw)
            translated = translated.replace(eng.lower(), sw.lower())
        
        return translated
    
    def get_bilingual_response(self, swahili_response: str, english_response: str) -> str:
        """
        Return response in both languages for mixed queries
        """
        return f"🇰🇪 **Kiswahili:**\n{swahili_response}\n\n🇬🇧 **English:**\n{english_response}"
    
    # -----------------------------------------------------------------------
    # CODE-SWITCHING SUPPORT
    # -----------------------------------------------------------------------
    
    def normalize_code_switching(self, text: str) -> Tuple[str, str]:
        """
        Normalize code-switched text (Camp/Eng) to standard forms
        Returns (normalized_text, detected_pattern)
        """
        text_lower = text.lower()
        
        # Common code-switching patterns
        patterns = {
            "camp": [
                (r'ni ([a-z]+)', r'it is \1'),
                (r'iko ([a-z]+)', r'it is \1'),
                (r'ziko ([a-z]+)', r'they are \1'),
                (r'na ([a-z]+)', r'and \1'),
                (r'lakini', r'but'),
                (r'kwa sababu', r'because'),
                (r'kama', r'if'),
                (r'basi', r'then'),
            ],
            "swahili_verbs": [
                (r'natafuta ([a-z]+)', r'search for \1'),
                (r'nataka ([a-z]+)', r'want \1'),
                (r'naona ([a-z]+)', r'see \1'),
                (r'nauliza ([a-z]+)', r'ask about \1'),
            ]
        }
        
        normalized = text
        detected = "mixed"
        
        # Apply camp normalization
        for pattern, replacement in patterns["camp"]:
            normalized = re.sub(pattern, replacement, normalized)
        
        return normalized, detected
    
    # -----------------------------------------------------------------------
    # UTILITY METHODS
    # -----------------------------------------------------------------------
    
    def get_price_query_examples(self) -> List[str]:
        """Return examples of price queries in Swahili"""
        return [
            "bei ya vegimax",
            "vegimax bei gani",
            "vegimax ni pesa ngapi",
            "cabbage ngapi",
            "gharama ya tomato",
            "tomato bei gani"
        ]
    
    def get_greeting_examples(self) -> List[str]:
        """Return examples of greetings in Swahili"""
        return [
            "habari",
            "jambo",
            "mambo",
            "habari za asubuhi",
            "asante"
        ]
    
    # -----------------------------------------------------------------------
    # MAIN ENTRY POINT
    # -----------------------------------------------------------------------
    
    def process_swahili_query(self, user_message: str) -> Dict:
        """
        Main entry point for processing Swahili queries
        Returns dict with intent, entities, and language info
        """
        # Detect language
        lang = self.detect_language(user_message)
        
        result = {
            "original_text": user_message,
            "detected_language": lang,
            "normalized_text": user_message,
            "intent": None,
            "entities": {}
        }
        
        # Handle code-switching
        if lang == "mixed":
            normalized, _ = self.normalize_code_switching(user_message)
            result["normalized_text"] = normalized
            logger.info(f"🔄 Normalized code-switched text: {normalized}")
        
        # Classify intent in Swahili
        result["intent"] = self.classify_swahili_intent(user_message)
        
        # Extract entities
        result["entities"] = self.extract_entities_swahili(user_message)
        
        logger.info(f"🇰🇪 Processed Swahili query: intent={result['intent']}, entities={result['entities']}")
        return result