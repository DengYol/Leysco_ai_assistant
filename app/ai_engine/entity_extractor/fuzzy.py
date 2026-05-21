# app/ai_engine/entity_extractor/fuzzy.py

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
        self.customer_cache = []
        self.customer_names = []
        self.customer_dict = {}
        self.customer_codes = []
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
    
    def find_best_match(
        self, 
        query: str, 
        threshold: int = 65,
        max_results: int = 5
    ) -> List[Tuple[str, float, Dict]]:
        """Find the best matching customer name using multiple algorithms."""
        if not query or not self.customer_names:
            return []
        
        # Normalize the query
        normalized_query = self.normalize_text(query)
        if not normalized_query:
            return []
        
        # Try exact match first (fastest)
        for name in self.customer_names:
            if name.lower() == query.lower() or name.lower() == normalized_query:
                logger.info(f"Exact match found: '{query}' → '{name}'")
                return [(name, 100.0, self.customer_dict.get(name, {}))]
        
        # Check if query is a customer code
        if query.upper() in self.customer_codes or normalized_query.upper() in self.customer_codes:
            code_match = query.upper() if query.upper() in self.customer_codes else normalized_query.upper()
            for customer in self.customer_cache:
                if customer.get('CardCode') == code_match:
                    logger.info(f"Customer code match: '{query}' → '{customer.get('CardName')}'")
                    return [(customer.get('CardName'), 100.0, customer)]
        
        # Try direct lookup in dictionary
        if query in self.customer_dict:
            return [(query, 100.0, self.customer_dict[query])]
        
        if normalized_query in self.customer_dict:
            return [(normalized_query, 100.0, self.customer_dict[normalized_query])]
        
        # Generate query variations
        query_variations = self.get_name_variations(query)
        query_variations.append(normalized_query)
        query_variations = list(set(query_variations))
        
        # Simple similarity matching (avoid rapidfuzz dependency)
        results = []
        seen_names = set()
        
        for search_name in query_variations:
            for candidate_name in self.customer_names[:1000]:  # Limit for performance
                if candidate_name in seen_names:
                    continue
                seen_names.add(candidate_name)
                
                # Calculate simple similarity ratio
                ratio = self._similarity_ratio(search_name, candidate_name)
                
                if ratio >= threshold:
                    results.append((candidate_name, ratio, self.customer_dict.get(candidate_name, {})))
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        
        # Deduplicate by customer ID
        unique_results = []
        seen_customers = set()
        for name, score, customer in results:
            customer_id = customer.get('CardCode', name)
            if customer_id not in seen_customers:
                seen_customers.add(customer_id)
                unique_results.append((name, score, customer))
        
        top_results = unique_results[:max_results]
        
        if top_results:
            best_match = top_results[0]
            logger.info(f"Fuzzy match found: '{query}' → '{best_match[0]}' (score: {best_match[1]:.1f})")
            if len(top_results) > 1:
                logger.debug(f"Other matches: {[(r[0], f'{r[1]:.1f}') for r in top_results[1:]]}")
        
        return top_results
    
    def _similarity_ratio(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings."""
        if not a or not b:
            return 0.0
        
        # Simple SequenceMatcher for similarity
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100
    
    def get_closest_customer(self, query: str, threshold: int = 65) -> Optional[Dict]:
        """Get the closest matching customer."""
        matches = self.find_best_match(query, threshold)
        if matches:
            return matches[0][2]
        return None
    
    def suggest_correction(self, query: str, threshold: int = 60) -> Optional[str]:
        """Suggest a corrected customer name."""
        matches = self.find_best_match(query, threshold)
        if matches and matches[0][1] >= threshold:
            return matches[0][0]
        return None
    
    def get_customer_suggestions(self, query: str, limit: int = 3) -> List[Dict]:
        """Get customer suggestions for autocomplete."""
        matches = self.find_best_match(query, threshold=50, max_results=limit)
        return [
            {
                "name": match[0],
                "code": match[2].get('CardCode'),
                "score": round(match[1], 1)
            }
            for match in matches
        ]
    
    def correct_item_typo(self, item_name: str) -> str:
        """Correct item name typo (placeholder - implement if needed)."""
        # For now, just return the original
        return item_name
    
    def correct_customer_typo(self, customer_name: str) -> str:
        """Correct customer name typo."""
        corrected = self.suggest_correction(customer_name)
        return corrected if corrected else customer_name


# Singleton instance
fuzzy_matcher = FuzzyMatcher()