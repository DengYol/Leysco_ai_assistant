"""Price lookup and prioritization logic"""

import re
import logging
from typing import List, Dict, Optional
from .base import BaseTransformer
from ..utils import extract_size_from_item_name, normalize_size_for_comparison
from ..constants import SIZE_PATTERNS

logger = logging.getLogger(__name__)


class PriceTransformer(BaseTransformer):
    """Handles price lookup with intelligent item prioritization"""
    
    @classmethod
    def calculate_item_priority_score(
        cls,
        item: Dict,
        search_term: str,
        required_size: Optional[str] = None,
        exact_size_required: bool = False
    ) -> int:
        """
        Calculate priority score for an item based on multiple factors.
        Higher score = more relevant.
        
        Scoring weights:
        - Exact size match: +500 points
        - Sellable item (Y): +200 points
        - Chemical item group (ItmsGrpCod=4): +150 points
        - Exact name/code match: +100 points
        - Size match (any): +80 points
        - Search term in name: +50 points
        - Size priority: +priority score
        """
        name = item.get("ItemName", "").upper()
        code = item.get("ItemCode", "").upper()
        search_upper = search_term.upper()
        
        score = 0
        
        # 1. Exact size match (highest priority)
        if required_size:
            item_size = extract_size_from_item_name(name)
            if item_size and required_size == item_size:
                score += 500
                logger.debug(f"   Exact size match: {item_size} for {name}")
            elif exact_size_required and not (item_size and required_size == item_size):
                score -= 1000
                logger.debug(f"   Size mismatch: {item_size} vs {required_size} for {name}")
        
        # 2. Sellable items
        sell_item = item.get("SellItem", "")
        if sell_item == "Y":
            score += 200
        elif sell_item == "N":
            score -= 100
        
        # 3. Item group preference
        itms_grp_cod = item.get("ItmsGrpCod")
        if itms_grp_cod == 4:  # Chemical
            score += 150
        elif itms_grp_cod == 3:  # Packaging
            score -= 50
        
        # 4. Exact name/code match
        if name == search_upper or code == search_upper:
            score += 100
        elif search_upper in name or search_upper in code:
            score += 50
        
        # 5. Size-based priority
        for size_pattern, priority in SIZE_PATTERNS.items():
            if size_pattern.upper() in name:
                score += priority
                break
        
        # 6. Penalize label items
        if "LABEL-" in name or "LABEL " in name:
            score -= 300
        
        # 7. Numeric size detection
        numbers = re.findall(r'\b(\d+)\b', name)
        if numbers:
            score += 20
        
        return score
    
    @classmethod
    def prioritize_items(cls, items: List[Dict], search_term: str,
                         required_size: Optional[str] = None,
                         exact_size_required: bool = False) -> List[Dict]:
        """Prioritize items by relevance score"""
        if not items:
            return []
        
        scored_items = []
        for item in items:
            score = cls.calculate_item_priority_score(
                item, search_term, required_size, exact_size_required
            )
            scored_items.append((score, item))
        
        scored_items.sort(key=lambda x: x[0], reverse=True)
        
        logger.info(f"   Top prioritized items:")
        for i, (score, item) in enumerate(scored_items[:5]):
            name = item.get("ItemName", "Unknown")
            sell = item.get("SellItem", "?")
            grp = item.get("ItmsGrpCod", "?")
            logger.info(f"      {i+1}. Score {score}: {name} (SellItem={sell}, Grp={grp})")
        
        return [item for score, item in scored_items[:10]]
    
    @classmethod
    def filter_exact_size_matches(cls, results: List[Dict], required_size: str) -> List[Dict]:
        """Filter results to only exact size matches"""
        if not required_size:
            return results
        
        exact_matches = [
            r for r in results 
            if extract_size_from_item_name(r.get("ItemName", "")) == required_size
        ]
        
        if exact_matches:
            logger.info(f"   Filtered to {len(exact_matches)} exact size matches")
            return exact_matches
        
        logger.warning(f"   No exact size match for {required_size}, using {len(results)} priced items")
        return results