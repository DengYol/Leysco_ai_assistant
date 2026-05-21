"""Warehouse extraction rules"""

import re
import logging
from ..constants import (
    WAREHOUSE_KEYWORDS,
    WAREHOUSE_STOP_WORDS,
    CHURN_HEALTH_KEYWORDS
)

logger = logging.getLogger(__name__)


class WarehouseRules:
    """Rules for warehouse name extraction"""
    
    @staticmethod
    def is_churn_health_query(text: str) -> bool:
        """Check if query is about churn risk or customer health."""
        text_lower = text.lower()
        for keyword in CHURN_HEALTH_KEYWORDS:
            if keyword in text_lower:
                return True
        return False
    
    @staticmethod
    def extract_warehouse(text: str) -> str:
        """Extract warehouse name with improved patterns including Swahili."""
        text_lower = text.lower()
        
        # Skip warehouse extraction for churn/health queries
        if WarehouseRules.is_churn_health_query(text):
            logger.info(f"Skipping warehouse extraction for churn/health query: {text[:50]}...")
            return None

        # Check for Swahili warehouse indicators
        if "ghala" in text_lower or "ny maghala" in text_lower:
            pattern_in = r'\b(?:katika|kwenye)\s+([a-zA-Z0-9\s\-]+)(?:\s+ghala|\s+hisa|\s+bidhaa)?'
            match = re.search(pattern_in, text_lower)
            if match:
                candidate = match.group(1).strip()
                if candidate and len(candidate) > 2:
                    logger.info(f"Extracted warehouse from Swahili pattern: '{candidate}'")
                    return candidate

        pattern_in = r'\b(?:in|from|at|katika|kwenye)\s+([a-zA-Z0-9\s\-]+)(?:\s+warehouse|\s+stock|\s+items?|\s+ghala|\s+hisa)?(?:\?|$)'
        match = re.search(pattern_in, text_lower)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(r'\b(warehouse|stock|items|item|the|a|an|ghala|hisa)\b', '', candidate).strip()
            if candidate and len(candidate) > 2 and candidate not in WAREHOUSE_STOP_WORDS:
                logger.info(f"Extracted warehouse from 'in/from/at' pattern: '{candidate}'")
                return candidate

        pattern_warehouse = r'\bwarehouse\s+([a-zA-Z0-9\s\-]+?)(?:\s+stock|\s+items?|\?|$)'
        match = re.search(pattern_warehouse, text_lower)
        if match:
            candidate = match.group(1).strip()
            if candidate and len(candidate) > 2 and candidate not in WAREHOUSE_STOP_WORDS:
                logger.info(f"Extracted warehouse from 'warehouse X' pattern: '{candidate}'")
                return candidate

        pattern_name_warehouse = r'([a-zA-Z0-9\s\-]+?)\s+warehouse(?:\s+stock|\s+items?|\?|$)'
        match = re.search(pattern_name_warehouse, text_lower)
        if match:
            candidate = match.group(1).strip()
            if candidate and len(candidate) > 2 and candidate not in WAREHOUSE_STOP_WORDS:
                logger.info(f"Extracted warehouse from 'X warehouse' pattern: '{candidate}'")
                return candidate

        cleaned_for_warehouse = re.sub(
            r'\b(show|list|get|find|tell|me|please|can|you|what|where|how|which|onyesha|taja|tafuta|pata)\b',
            '', text_lower
        )

        pattern1 = r'(?:in|at|from|katika|kwenye)\s+([a-zA-Z0-9]+(?:\s+[a-zA-Z0-9]+)?)\s+(?:warehouse|store|branch|depot|ghala)'
        match = re.search(pattern1, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            if all(w not in WAREHOUSE_STOP_WORDS for w in candidate.split()):
                return candidate

        pattern2 = r'([a-zA-Z0-9]+)\s+(?:warehouse|store|branch|depot|ghala)(?:\s|$)'
        match = re.search(pattern2, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            if candidate not in WAREHOUSE_STOP_WORDS:
                return candidate

        pattern3 = r'(?:warehouse|store|branch|depot|ghala)\s+([a-zA-Z0-9]+)'
        match = re.search(pattern3, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            if candidate not in WAREHOUSE_STOP_WORDS:
                return candidate

        for warehouse in ["main", "nairobi", "mombasa", "kisumu", "eldoret",
                          "central", "north", "south", "east", "west",
                          "dispatch", "shipping", "receiving", "quarantine"]:
            if warehouse in cleaned_for_warehouse:
                if warehouse == "west" and "lowest" in text_lower:
                    continue
                return warehouse

        return None