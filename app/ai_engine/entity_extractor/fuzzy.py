# app/ai_engine/entity_extractor/fuzzy.py
# FIXED: P1.1 - Item typo-correction now properly implemented with fuzzy matching

import re
import logging
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class FuzzyMatcher:
    """Enhanced fuzzy matching for customer names and items."""
    
    def __init__(self, api_service=None):
        """
        Initialize FuzzyMatcher.
        
        Args:
            api_service: Optional API service for fetching data (not used directly)
        """
        # Customer-related caches
        self.customer_cache = []
        self.customer_names = []
        self.customer_dict = {}
        self.customer_codes = []
        
        # Item-related caches (NEW - P1.1)
        self.item_cache = []
        self.item_names = []
        self.item_dict = {}
        self.item_codes = []
        
        self._last_refresh = None
        self.api_service = api_service
        logger.info("FuzzyMatcher initialized")
        
    def normalize_text(self, text: str) -> str:
        """Normalize text for better matching."""
        if not text:
            return text
        
        # Convert to lowercase
        text = text.lower().strip()
        
        # Remove common suffixes
        suffixes = [
            'ltd', 'limited', 'inc', 'corporation', 'corp', 'llc', 'co', 
            'supplies', 'supply', 'agrovet', 'agri', 'vet', 'enterprises', 
            'enterprise', 'traders', 'services', 'solutions', 'group',
            'store', 'shop', 'center', 'centre', 'company'
        ]
        for suffix in suffixes:
            text = re.sub(rf'\s+{suffix}\s*$', '', text)
            text = re.sub(rf'^{suffix}\s+', '', text)
        
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Remove common filler words
        filler_words = ['and', 'the', 'of', 'for', 'to', 'by', 'with', 'a', 'an']
        for word in filler_words:
            text = re.sub(rf'\b{word}\b', '', text)
            text = ' '.join(text.split())
        
        return text
    
    def get_name_variations(self, name: str) -> List[str]:
        """Generate common variations of a name."""
        variations = [name]
        
        # Remove common parts
        patterns_to_remove = [
            r'\s+supplies$', r'\s+supply$', r'\s+agrovet$', r'\s+agri$',
            r'\s+limited$', r'\s+ltd$', r'\s+inc$', r'\s+corp$', r'\s+co$',
            r'\s+enterprises$', r'\s+enterprise$', r'\s+traders$',
            r'\s+services$', r'\s+solutions$', r'\s+group$',
            r'\s+store$', r'\s+shop$', r'\s+center$', r'\s+centre$'
        ]
        
        for pattern in patterns_to_remove:
            variant = re.sub(pattern, '', name, flags=re.IGNORECASE)
            if variant != name and variant.strip():
                variations.append(variant.strip())
        
        # Split by spaces and take first N words
        words = name.split()
        if len(words) > 3:
            variations.append(' '.join(words[:3]))
        if len(words) > 2:
            variations.append(' '.join(words[:2]))
        if len(words) > 1:
            variations.append(words[0])
        
        # Remove duplicates while preserving order
        seen = set()
        variations = [v for v in variations if not (v in seen or seen.add(v))]
        
        return variations
    
    def refresh_customer_cache(self, customers: List[Dict]):
        """Refresh the customer name cache."""
        self.customer_cache = customers
        self.customer_names = []
        self.customer_dict = {}
        self.customer_codes = []
        
        for customer in customers:
            # Get the main name fields
            card_name = customer.get('CardName', '')
            card_code = customer.get('CardCode', '')
            
            # Store original
            self.customer_dict[card_name] = customer
            self.customer_dict[card_code] = customer
            self.customer_names.append(card_name)
            self.customer_codes.append(card_code)
            
            # Add normalized version
            normalized = self.normalize_text(card_name)
            if normalized and normalized != card_name:
                self.customer_names.append(normalized)
                self.customer_dict[normalized] = customer
            
            # Add code as searchable name
            if card_code and card_code != card_name:
                self.customer_names.append(card_code)
            
            # Add variations
            variations = self.get_name_variations(card_name)
            for variant in variations:
                if variant and variant != card_name:
                    self.customer_names.append(variant)
                    self.customer_dict[variant] = customer
        
        # Remove duplicates
        seen = set()
        unique_names = []
        for name in self.customer_names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)
        self.customer_names = unique_names
        
        logger.info(f"Customer cache refreshed with {len(customers)} customers → {len(self.customer_names)} searchable names")
    
    # NEW: P1.1 - Item cache refresh method
    def refresh_item_cache(self, items: List[Dict]):
        """
        Refresh the item name cache.
        
        This enables typo correction for item names by building a searchable
        cache of all available items and their variations.
        
        Args:
            items: List of item dictionaries from ERP
                   Expected fields: ItemCode, ItemName (or similar)
        """
        self.item_cache = items
        self.item_names = []
        self.item_dict = {}
        self.item_codes = []
        
        for item in items:
            # Get the main name and code fields
            item_name = item.get('ItemName') or item.get('name') or ''
            item_code = item.get('ItemCode') or item.get('code') or ''
            
            if not item_name:
                continue
            
            # Store original name and code
            self.item_dict[item_name] = item
            self.item_dict[item_code] = item
            self.item_names.append(item_name)
            self.item_codes.append(item_code)
            
            # Add normalized version
            normalized = self.normalize_text(item_name)
            if normalized and normalized != item_name:
                self.item_names.append(normalized)
                self.item_dict[normalized] = item
            
            # Add code as searchable name
            if item_code and item_code != item_name:
                self.item_names.append(item_code)
            
            # Add variations (first N words, etc.)
            variations = self.get_name_variations(item_name)
            for variant in variations:
                if variant and variant != item_name:
                    self.item_names.append(variant)
                    self.item_dict[variant] = item
        
        # Remove duplicates
        seen = set()
        unique_names = []
        for name in self.item_names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)
        self.item_names = unique_names
        
        logger.info(f"Item cache refreshed with {len(items)} items → {len(self.item_names)} searchable names")
    
    def find_best_match(
        self, 
        query: str, 
        threshold: int = 65,
        max_results: int = 5,
        search_type: str = 'customer'
    ) -> List[Tuple[str, float, Dict]]:
        """
        Find the best matching name using multiple algorithms.
        
        Args:
            query: Search query (name to match)
            threshold: Minimum similarity score (0-100)
            max_results: Maximum number of results to return
            search_type: 'customer' or 'item' to specify which cache to search
        
        Returns:
            List of tuples: (matched_name, score, full_record)
        """
        # Select appropriate cache based on search_type
        if search_type == 'item':
            names = self.item_names
            codes = self.item_codes
            cache_dict = self.item_dict
        else:
            names = self.customer_names
            codes = self.customer_codes
            cache_dict = self.customer_dict
        
        if not query or not names:
            return []
        
        # Normalize the query
        normalized_query = self.normalize_text(query)
        if not normalized_query:
            return []
        
        # Try exact match first (fastest)
        for name in names:
            if name.lower() == query.lower() or name.lower() == normalized_query:
                logger.info(f"Exact match found: '{query}' → '{name}'")
                return [(name, 100.0, cache_dict.get(name, {}))]
        
        # Check if query is a code
        if query.upper() in codes or normalized_query.upper() in codes:
            code_match = query.upper() if query.upper() in codes else normalized_query.upper()
            for item in (self.item_cache if search_type == 'item' else self.customer_cache):
                code_field = 'ItemCode' if search_type == 'item' else 'CardCode'
                name_field = 'ItemName' if search_type == 'item' else 'CardName'
                if item.get(code_field) == code_match:
                    logger.info(f"Code match: '{query}' → '{item.get(name_field)}'")
                    return [(item.get(name_field), 100.0, item)]
        
        # Try direct lookup in dictionary
        if query in cache_dict:
            return [(query, 100.0, cache_dict[query])]
        
        if normalized_query in cache_dict:
            return [(normalized_query, 100.0, cache_dict[normalized_query])]
        
        # Generate query variations
        query_variations = self.get_name_variations(query)
        query_variations.append(normalized_query)
        query_variations = list(set(query_variations))
        
        # Simple similarity matching (avoid rapidfuzz dependency)
        results = []
        seen_names = set()
        
        for search_name in query_variations:
            for candidate_name in names[:1000]:  # Limit for performance
                if candidate_name in seen_names:
                    continue
                seen_names.add(candidate_name)
                
                # Calculate simple similarity ratio
                ratio = self._similarity_ratio(search_name, candidate_name)
                
                if ratio >= threshold:
                    results.append((candidate_name, ratio, cache_dict.get(candidate_name, {})))
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        
        # Deduplicate by ID
        unique_results = []
        seen_ids = set()
        for name, score, record in results:
            record_id = record.get('ItemCode') or record.get('CardCode') or name
            if record_id not in seen_ids:
                seen_ids.add(record_id)
                unique_results.append((name, score, record))
        
        top_results = unique_results[:max_results]
        
        if top_results:
            best_match = top_results[0]
            logger.info(f"Fuzzy match found: '{query}' → '{best_match[0]}' (score: {best_match[1]:.1f})")
            if len(top_results) > 1:
                logger.debug(f"Other matches: {[(r[0], f'{r[1]:.1f}') for r in top_results[1:]]}")
        
        return top_results
    
    def _similarity_ratio(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings (0-100)."""
        if not a or not b:
            return 0.0
        
        # Simple SequenceMatcher for similarity
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100
    
    def get_closest_customer(self, query: str, threshold: int = 65) -> Optional[Dict]:
        """Get the closest matching customer."""
        matches = self.find_best_match(query, threshold, search_type='customer')
        if matches:
            return matches[0][2]
        return None
    
    # NEW: P1.1 - Get closest matching item
    def get_closest_item(self, query: str, threshold: int = 80) -> Optional[Dict]:
        """
        Get the closest matching item by name/code.
        
        Args:
            query: Item name or code to match
            threshold: Minimum similarity score (default 80%)
        
        Returns:
            Item dictionary if match found above threshold, else None
        """
        matches = self.find_best_match(query, threshold, search_type='item')
        if matches:
            score = matches[0][1]
            item = matches[0][2]
            logger.info(f"Item match: '{query}' → '{matches[0][0]}' (score: {score:.1f}%)")
            return item
        logger.warning(f"No item match found for '{query}' with threshold {threshold}%")
        return None
    
    def suggest_correction(self, query: str, threshold: int = 60) -> Optional[str]:
        """Suggest a corrected customer name."""
        matches = self.find_best_match(query, threshold, search_type='customer')
        if matches and matches[0][1] >= threshold:
            return matches[0][0]
        return None
    
    # NEW: P1.1 - Suggest item correction
    def suggest_item_correction(self, query: str, threshold: int = 80) -> Optional[str]:
        """
        Suggest a corrected item name.
        
        Args:
            query: Misspelled item name
            threshold: Minimum score for auto-correction (default 80%)
        
        Returns:
            Corrected item name if confident match found, else None
        """
        matches = self.find_best_match(query, threshold, search_type='item')
        if matches and matches[0][1] >= threshold:
            corrected = matches[0][0]
            score = matches[0][1]
            logger.info(f"Item typo corrected: '{query}' → '{corrected}' (confidence: {score:.1f}%)")
            return corrected
        return None
    
    def get_customer_suggestions(self, query: str, limit: int = 3) -> List[Dict]:
        """Get customer suggestions for autocomplete."""
        matches = self.find_best_match(query, threshold=50, max_results=limit, search_type='customer')
        return [
            {
                "name": match[0],
                "code": match[2].get('CardCode'),
                "score": round(match[1], 1)
            }
            for match in matches
        ]
    
    # NEW: P1.1 - Get item suggestions
    def get_item_suggestions(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Get item suggestions for autocomplete or typo correction.
        
        Args:
            query: Partial item name or code
            limit: Maximum suggestions to return
        
        Returns:
            List of item suggestions with names, codes, and match scores
        """
        matches = self.find_best_match(query, threshold=60, max_results=limit, search_type='item')
        return [
            {
                "name": match[0],
                "code": match[2].get('ItemCode'),
                "score": round(match[1], 1)
            }
            for match in matches
        ]
    
    # FIXED: P1.1 - Item typo correction now fully implemented
    def correct_item_typo(self, item_name: str, confidence_threshold: int = 85) -> Tuple[str, bool]:
        """
        Correct item name typos using fuzzy matching.
        
        This replaces the placeholder that just returned the input unchanged.
        Now it attempts to find a matching item in the catalog.
        
        Args:
            item_name: Potentially misspelled item name
            confidence_threshold: Minimum confidence for auto-correction (0-100)
                                 Default 85% means we only auto-correct high-confidence matches
        
        Returns:
            Tuple of (corrected_name, was_corrected)
            - corrected_name: Original or corrected item name
            - was_corrected: Boolean indicating if correction was applied
        
        Examples:
            >>> correct_item_typo("CRR F")
            ("CRR F PAN HD TAP SCREW ST", True)  # Found and corrected
            
            >>> correct_item_typo("UNKNOWN ITEM")
            ("UNKNOWN ITEM", False)  # No match, returned original
            
            >>> correct_item_typo("CRR F Pan")  # Slight variation
            ("CRR F PAN HD TAP SCREW ST", True)  # Corrected with high confidence
        """
        if not item_name or not item_name.strip():
            return item_name, False
        
        item_name = item_name.strip()
        
        # Try to find best match
        matches = self.find_best_match(
            item_name,
            threshold=70,  # Start with 70% to find candidates
            max_results=3,
            search_type='item'
        )
        
        if not matches:
            # No fuzzy matches found
            logger.debug(f"No item match found for '{item_name}'")
            return item_name, False
        
        best_match = matches[0]
        matched_name, score, item_record = best_match
        
        # Only auto-correct if confidence is high enough
        if score >= confidence_threshold:
            logger.info(f"Item typo corrected: '{item_name}' → '{matched_name}' (confidence: {score:.1f}%)")
            return matched_name, True
        
        # If confidence is moderate (70-85%), log it but don't auto-correct
        # The caller can decide whether to present as suggestion
        if score >= 70:
            logger.info(f"Potential item match: '{item_name}' ≈ '{matched_name}' (confidence: {score:.1f}%) - not auto-correcting")
            return item_name, False
        
        # Low confidence, return original
        logger.debug(f"Low confidence match for '{item_name}': best was '{matched_name}' ({score:.1f}%)")
        return item_name, False
    
    def correct_customer_typo(self, customer_name: str) -> str:
        """Correct customer name typo."""
        corrected = self.suggest_correction(customer_name)
        return corrected if corrected else customer_name


# Singleton instance
fuzzy_matcher = FuzzyMatcher()