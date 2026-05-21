"""Constants for Entity Extractor - Patterns, word lists, and configuration"""

import re

# ============================================================================
# NUMBER WORD MAPPINGS
# ============================================================================

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "couple": 2, "few": 3, "some": 5,
}

SWAHILI_NUMBER_WORDS = {
    "moja": 1, "mbili": 2, "tatu": 3, "nne": 4, "tano": 5,
    "sita": 6, "saba": 7, "nane": 8, "tisa": 9, "kumi": 10,
}

# ============================================================================
# CUSTOMER DETECTION WORDS
# ============================================================================

CUSTOMER_SUFFIX_WORDS = {
    "suppliers", "supplier", "vendor", "vendors", "traders", "trader",
    "enterprises", "enterprise", "solutions", "company", "co", "ltd",
    "limited", "inc", "group", "associates", "agency", "agencies",
    "industries", "industry", "international", "brothers", "bros",
    "holdings", "services", "distributors", "distributor",
    "technologies", "tech", "systems", "solutions", "consulting",
    "logistics", "transport", "shipping", "trading", "imports", "exports",
    "corporation", "corp", "llc", "l.l.c", "global", "worldwide",
    "partners", "ventures", "enterprise", "business", "firm", "shop",
    "store", "retail", "wholesale", "distributor", "dealer", "agency",
    "agrovet", "farm", "farms", "agro", "agri", "agriculture",
    "mteja", "wateja", "msambazaji", "wasambazaji", "kampuni", "makampuni",
}

STRIP_FROM_SEARCH = {
    "suppliers", "supplier", "vendor", "vendors", "traders", "trader",
    "enterprises", "enterprise", "company", "ltd", "limited",
    "inc", "group", "associates", "agency", "agencies",
    "industries", "industry", "international", "brothers", "bros",
    "holdings", "services", "distributors", "distributor",
    "mteja", "wateja", "kampuni", "makampuni",
}

# ============================================================================
# PRODUCT INDICATORS
# ============================================================================

PRODUCT_INDICATORS = {
    "vegimax", "cabbage", "tomato", "seed", "seeds", "fertilizer",
    "pesticide", "herbicide", "fungicide", "chemical", "insecticide",
    "maize", "wheat", "rice", "beans", "peas", "onion", "potato",
    "carrot", "kale", "spinach", "capsicum", "chili", "pepper",
    "cucumber", "pumpkin", "squash", "melon", "watermelon",
    "strawberry", "raspberry", "blueberry", "blackberry",
    "apple", "orange", "mango", "banana", "pineapple", "avocado",
    "grape", "lemon", "lime", "grapefruit", "herb", "spice",
    "easeed", "agriscope", "tosheka", "kh500", "mh401", "snowball",
    "yolo wonder", "blockies", "lumarx", "smd", "cti",
    "takii", "takii logo", "rmst0512", "takii seed", "takii seeds",
    "bidhaa", "mazao", "vitu", "mbegu", "mbolea", "dawa", "sumu",
}

# ============================================================================
# WAREHOUSE KEYWORDS
# ============================================================================

WAREHOUSE_KEYWORDS = {
    "warehouse", "store", "branch", "depot", "facility", "storage",
    "dispatch", "shipping", "receiving", "main", "nairobi", "mombasa",
    "kisumu", "eldoret", "central", "north", "south", "east", "west",
    "inactive", "active", "quarantine", "quarntine", "bonded", "free",
    "ghala", "ny maghala", "hifadhi", "stoko",
}

WAREHOUSE_STOP_WORDS = {
    "is", "in", "at", "from", "the", "a", "an", "and", "or", "but",
    "show", "list", "get", "find", "tell", "me", "please", "can", "you",
    "what", "where", "how", "which", "when", "why",
    "nionyeshe", "onyesha", "angalia", "tafuta", "pata", "taja",
    "churn", "risk", "churn risk", "at risk", "healthy", "unhealthy",
    "health", "score", "grade", "signal", "recommendation",
    "customer health", "health check", "churn prediction",
}

# ============================================================================
# QUERY TYPE INDICATORS
# ============================================================================

INFO_QUERY_INDICATORS = {
    "tell me about", "what is", "about ", "information on", "info on",
    "details about", "learn about", "explain", "describe",
    "niambie kuhusu", "maelezo kuhusu", "taarifa kuhusu",
}

FORECAST_INDICATORS = {
    "forecast", "predict", "projection", "future", "demand", "sales trend",
    "will sell", "expected", "anticipate", "estimate", "outlook",
    "how much will", "how many will", "predict demand", "forecast demand",
    "utabiri", "makadirio", "mahitaji",
}

COMPETITOR_PRICING_INDICATORS = {
    "competitor price", "market price", "compare price", "price comparison",
    "market intelligence", "price alert", "best price", "cheapest",
    "lowest price", "who sells", "where to buy", "best deal",
    "bei ya ushindani", "bei ya soko", "linganisha bei", "bei bora",
}

RECOMMENDATION_INDICATORS = {
    "customers who bought", "also bought", "frequently bought",
    "people also buy", "others bought", "similar customers bought",
    "what else do customers buy with", "commonly bought with",
    "bundle with", "frequently purchased together", "who bougth",
    "who bought", "customers who buy", "people who buy",
    "recommend items", "suggest items", "recommend products",
    "suggest products", "what to sell", "items to sell",
    "cross sell", "cross-sell", "upsell", "up-sell",
    "also buys what", "buys what", "also purchases",
    "wateja walionunua", "alinunua pia", "nunua pamoja", "pendekeza bidhaa",
}

SEASONAL_INDICATORS = {
    "seasonal", "what to plant", "best for this season", "what grows in",
    "planting guide", "seasonal picks", "this month", "current month",
    "in season", "spring", "summer", "fall", "autumn", "winter",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "msimu", "panda katika msimu", "mazao ya msimu",
}

LISTING_INDICATORS = {
    "all", "list", "show", "display", "view", "get", "find",
    "zote", "ote", "orodhesha", "onyesha",
}

CHURN_HEALTH_KEYWORDS = {
    "churn", "churn risk", "customer health", "health score", "at risk",
    "churning", "health check", "customer wellbeing", "risk level",
    "likely to leave", "likely to churn", "unhealthy customer",
}

# ============================================================================
# CONTEXT AND PRONOUN WORDS
# ============================================================================

PRONOUN_WORDS = {
    "their", "them", "they", "him", "her", "it", "that", "this", "these", "those",
    "his", "hers", "its", "our", "your", "my",
    "wake", "wake", "yake", "yetu", "yako", "yangu",
}

FOLLOWUP_INDICATORS = {
    "what about", "how about", "tell me more", "more info", "details on",
    "what is its", "how much is it", "its price", "its stock", "its status",
    "vipi kuhusu", "niambie zaidi", "maelezo zaidi", "bei yake", "hisa zake",
}

# ============================================================================
# SWAHILI PATTERNS
# ============================================================================

SWAHILI_PREFIXES = [
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
    r'^sema\s+',         # "tell"
]

SWAHILI_MONTHS = {
    "januari": "january", "februari": "february", "machi": "march",
    "april": "april", "mei": "may", "juni": "june",
    "julai": "july", "agosti": "august", "septemba": "september",
    "oktoba": "october", "novemba": "november", "desemba": "december",
}

# ============================================================================
# SIZE PATTERNS
# ============================================================================

SIZE_PATTERNS = [
    r'(\d+(?:\.\d+)?)\s*(ml|ML|mL|kg|KG|g|G|l|L|lt|LT)',
    r'(ml|ML|mL|kg|KG|g|G|l|L|lt|LT)\s*(\d+(?:\.\d+)?)',
    r'(\d+)\s*(?:ml|ML|mL|kg|KG|g|G|l|L|lt|LT)',
    r'(\d+(?:\.\d+)?)\s*(mililita|ml|millilita)',
    r'(\d+(?:\.\d+)?)\s*(kilogramu|kg|kilo)',
    r'(\d+(?:\.\d+)?)\s*(gramu|g|gram)',
    r'(\d+(?:\.\d+)?)\s*(lita|l|litre)',
]

COMMON_SIZES = {
    "10ml": 100, "10 ml": 100, "10ml": 100,
    "30ml": 90, "30 ml": 90, "30ml": 90,
    "125ml": 70, "125 ml": 70, "125ml": 70,
    "250ml": 60, "250 ml": 60, "250ml": 60,
    "500ml": 50, "500 ml": 50, "500ml": 50,
    "1kg": 100, "1 kg": 100, "1kg": 100,
    "2kg": 90, "2 kg": 90, "2kg": 90,
    "5kg": 70, "5 kg": 70, "5kg": 70,
    "10kg": 60, "10 kg": 60, "10kg": 60,
    "25kg": 50, "25 kg": 50, "25kg": 50,
    "50kg": 40, "50 kg": 40, "50kg": 40,
}

# ============================================================================
# FUZZY MATCHING CONFIGURATION
# ============================================================================

ITEM_FUZZY_CUTOFF = 0.70
ITEM_FUZZY_N = 1
ITEM_CACHE_TTL = 300

# ============================================================================
# MONTHS
# ============================================================================

MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]

# ============================================================================
# REGEX PATTERNS
# ============================================================================

CUSTOMER_NAME_NOISE = re.compile(
    r"^\s*(?:"
    r"orders?\s+for|"
    r"customer\s+orders?\s+for|"
    r"client\s+orders?\s+for|"
    r"details?\s+for|"
    r"invoices?\s+for|"
    r"info\s+(?:for|on)|"
    r"information\s+(?:for|on)|"
    r"quotations?\s+for|"
    r"show\s+(?:me\s+)?|"
    r"nionyeshe\s+|"
    r"onyesha\s+|"
    r"angalia\s+|"
    r"tafuta\s+|"
    r"pata\s+"
    r")\s*",
    re.IGNORECASE,
)

COMMAND_VERBS = r"\b(show|list|get|find|search|display|tell|give|look|create|make|generate|onyesha|taja|tafuta|pata|unda|tengeneza)\b"