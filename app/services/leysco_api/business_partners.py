"""Business partner (customer, vendor, lead) operations"""

import logging
from typing import List, Dict, Optional
from difflib import get_close_matches

from .constants import BP_TYPES
from .utils import clean_customer_search_term, apply_limit, normalize_response

logger = logging.getLogger(__name__)


class BusinessPartnerHandler:
    """Handles customer, vendor, and lead operations"""
    
    def __init__(self, parent):
        self.parent = parent
        self.session = parent.session
        self.base_url = parent.base_url
        self.auth_handler = parent.auth_handler
        self.cache_manager = parent.cache_manager
        self._cached_customers = None  # Cache for all customers
    
    def get_business_partner_type(self, business_partner: Dict) -> str:
        """
        Determine business partner type from the data.
        Checks multiple possible fields and values.
        """
        # Handle None or empty input
        if not business_partner or not isinstance(business_partner, dict):
            return "C"
        
        card_type = business_partner.get("CardType") or business_partner.get("card_type") or business_partner.get("Type") or business_partner.get("type")
        card_name = business_partner.get("CardName", "")
        
        # Handle None card_name
        if card_name is None:
            card_name = ""
        
        card_name_lower = card_name.lower()
        
        if any(word in card_name_lower for word in ["vendor", "supplier"]):
            return "V"
        if any(word in card_name_lower for word in ["lead", "prospect"]):
            return "L"
        
        if card_type:
            card_type_str = str(card_type).upper()
            if card_type_str in ["C", "CUSTOMER"]:
                return "C"
            elif card_type_str in ["V", "VENDOR", "SUPPLIER"]:
                return "V"
            elif card_type_str in ["L", "LEAD"]:
                return "L"
        
        group_code = business_partner.get("GroupCode") or business_partner.get("group_code")
        if group_code:
            try:
                gc = int(group_code)
                if 1 <= gc <= 100:
                    return "C"
                elif 101 <= gc <= 200:
                    return "V"
                elif 201 <= gc <= 300:
                    return "L"
            except:
                pass
        
        return "C"
    
    def is_customer(self, business_partner: Dict) -> bool:
        if not business_partner or not isinstance(business_partner, dict):
            return False
        return self.get_business_partner_type(business_partner) == "C"
    
    def is_vendor(self, business_partner: Dict) -> bool:
        if not business_partner or not isinstance(business_partner, dict):
            return False
        return self.get_business_partner_type(business_partner) == "V"
    
    def is_lead(self, business_partner: Dict) -> bool:
        if not business_partner or not isinstance(business_partner, dict):
            return False
        return self.get_business_partner_type(business_partner) == "L"
    
    def filter_by_bp_type(self, business_partners: List[Dict], bp_type: str) -> List[Dict]:
        if not business_partners or bp_type is None:
            return business_partners or []
        
        filtered = []
        for bp in business_partners:
            # Skip None entries
            if bp is None or not isinstance(bp, dict):
                continue
            if bp_type == "C" and self.is_customer(bp):
                filtered.append(bp)
            elif bp_type == "V" and self.is_vendor(bp):
                filtered.append(bp)
            elif bp_type == "L" and self.is_lead(bp):
                filtered.append(bp)
        
        logger.info(f"Filtered {len(filtered)}/{len(business_partners) if business_partners else 0} business partners for type {bp_type}")
        return filtered
    
    def get_customers(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get customers only (excludes vendors and leads)"""
        # For customer searches with a term, use local filtering for better partial matching
        if search and search.lower() not in ["all", "all customers", "customers", "customer", "show", "list", "display"]:
            return self._get_customers_with_local_filter(search, limit)
        return self._fetch_business_partners(search, limit, bp_type="C")
    
    def _get_customers_with_local_filter(self, search: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Get customers with local filtering for better partial matching.
        This handles cases where the API doesn't support partial word matching.
        """
        # Fetch all customers once and cache them
        all_customers = self._fetch_all_customers()
        
        if not all_customers:
            return []
        
        search_lower = search.lower().strip()
        search_terms = search_lower.split()
        
        matching_customers = []
        
        for customer in all_customers:
            if customer is None or not isinstance(customer, dict):
                continue
                
            customer_name = customer.get("CardName", "")
            if customer_name is None:
                customer_name = ""
            customer_name_lower = customer_name.lower()
            
            card_code = customer.get("CardCode", "")
            if card_code is None:
                card_code = ""
            card_code_lower = card_code.lower()
            
            # Check if all search terms appear in either name or code
            all_terms_match = all(
                term in customer_name_lower or term in card_code_lower 
                for term in search_terms
            )
            
            if all_terms_match:
                # Calculate relevance score
                # Exact match on full name gets highest score
                if customer_name_lower == search_lower:
                    score = 100
                elif customer_name_lower.startswith(search_lower):
                    score = 90
                elif search_lower in customer_name_lower:
                    # Count how many terms match
                    matched_terms = sum(1 for term in search_terms if term in customer_name_lower)
                    score = 80 + (matched_terms / len(search_terms)) * 10
                else:
                    score = 70
                
                matching_customers.append((score, customer))
        
        if matching_customers:
            # Sort by score (highest first)
            matching_customers.sort(key=lambda x: x[0], reverse=True)
            results = [customer for score, customer in matching_customers]
            
            if limit:
                results = results[:limit]
            
            logger.info(f"✅ Found {len(results)} customers matching '{search}' via local filter")
            return results
        
        # Fallback: try to find any customer containing the search string
        for customer in all_customers:
            if customer is None or not isinstance(customer, dict):
                continue
            customer_name = customer.get("CardName", "")
            if customer_name is None:
                customer_name = ""
            if search_lower in customer_name.lower():
                matching_customers.append(customer)
        
        if matching_customers:
            logger.info(f"✅ Found {len(matching_customers)} customers containing '{search}'")
            if limit:
                return matching_customers[:limit]
            return matching_customers
        
        logger.warning(f"❌ No customers found matching '{search}'")
        return []
    
    def _fetch_all_customers(self) -> List[Dict]:
        """Fetch all customers once and cache them for local filtering."""
        # Return cached customers if available
        if self._cached_customers is not None:
            logger.info("📦 Using cached customers for local filtering")
            return self._cached_customers
        
        try:
            if not self.auth_handler.ensure_auth():
                return []
            
            all_customers = []
            page = 1
            per_page = 200
            
            while True:
                url = f"{self.base_url}/bp_masterdata"
                params = {"page": page, "per_page": per_page}
                
                logger.info(f"📄 Fetching all customers page {page} (no search filter)")
                resp = self.session.get(url, params=params, timeout=30)
                
                if not self.auth_handler.check_auth(resp):
                    logger.warning("Authentication failed, stopping fetch")
                    break
                
                if resp.status_code != 200:
                    logger.error(f"Failed to fetch page {page}: {resp.status_code}")
                    break
                
                try:
                    data = resp.json()
                except Exception as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    break
                
                partners = normalize_response(data)
                
                if not partners:
                    break
                
                # Filter to customers only, skipping None entries
                customers = []
                for partner in partners:
                    if partner is not None and isinstance(partner, dict):
                        if self.is_customer(partner):
                            customers.append(partner)
                
                all_customers.extend(customers)
                logger.info(f"Page {page}: Found {len(customers)} customers (total: {len(all_customers)})")
                
                # Check pagination
                if len(partners) < per_page:
                    break
                page += 1
            
            all_customers.sort(key=lambda x: x.get("CardName", "") if x.get("CardName") else "")
            logger.info(f"✅ Cached {len(all_customers)} total customers")
            
            # Cache for future use
            self._cached_customers = all_customers
            return all_customers
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch all customers: {e}", exc_info=True)
            return []
    
    def get_all_customers(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Alias for get_customers"""
        return self.get_customers(search, limit)
    
    def get_vendors(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get vendors only"""
        return self._fetch_business_partners(search, limit, bp_type="V")
    
    def get_leads(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get leads only"""
        return self._fetch_business_partners(search, limit, bp_type="L")
    
    def get_all_business_partners(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get all business partners (customers, vendors, leads)"""
        return self._fetch_business_partners(search, limit, bp_type=None)
    
    def _fetch_business_partners(self, search: str = "", limit: Optional[int] = None, bp_type: Optional[str] = None) -> List[Dict]:
        """Internal method to fetch business partners with pagination"""
        try:
            if not self.auth_handler.ensure_auth():
                return []
            
            # Handle "show all" search terms
            if search and search.lower() in ["all", "all customers", "customers", "customer", "show", "list", "display"]:
                search = ""
            
            cleaned_search = clean_customer_search_term(search) if search and bp_type == "C" else search
            
            all_partners = []
            page = 1
            per_page = 200
            
            while True:
                url = f"{self.base_url}/bp_masterdata"
                params = {"page": page, "per_page": per_page}
                if cleaned_search:
                    params["search"] = cleaned_search
                
                logger.info(f"📄 Fetching business partners page {page} with search: '{cleaned_search}'")
                self.parent._record_api_call()
                resp = self.session.get(url, params=params, timeout=30)
                
                if not self.auth_handler.check_auth(resp):
                    logger.warning("Authentication failed, stopping fetch")
                    break
                
                if resp.status_code != 200:
                    logger.error(f"Failed to fetch page {page}: {resp.status_code}")
                    break
                
                try:
                    data = resp.json()
                except Exception as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    break
                
                partners = normalize_response(data)
                
                if not partners:
                    break
                
                # Apply BP type filter, skipping None entries
                if bp_type is not None:
                    filtered_partners = []
                    for partner in partners:
                        if partner is not None and isinstance(partner, dict):
                            if bp_type == "C" and self.is_customer(partner):
                                filtered_partners.append(partner)
                            elif bp_type == "V" and self.is_vendor(partner):
                                filtered_partners.append(partner)
                            elif bp_type == "L" and self.is_lead(partner):
                                filtered_partners.append(partner)
                    partners = filtered_partners
                
                all_partners.extend(partners)
                logger.info(f"Page {page}: Found {len(partners)} (total: {len(all_partners)})")
                
                # Check pagination
                if len(partners) < per_page:
                    break
                page += 1
                
                if limit and len(all_partners) >= limit:
                    all_partners = all_partners[:limit]
                    break
            
            all_partners.sort(key=lambda x: x.get("CardName", "") if x.get("CardName") else "")
            logger.info(f"✅ Retrieved {len(all_partners)} total business partners")
            return all_partners
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch business partners: {e}", exc_info=True)
            return []
    
    def resolve_customer(self, name: str) -> Optional[Dict]:
        """
        Resolve customer by name - returns the best matching customer.
        Tries exact match first, then partial match, then fuzzy match.
        """
        if not name:
            return None
        
        name_lower = name.lower().strip()
        
        # Fetch all customers using local filtering for best results
        all_customers = self._fetch_all_customers()
        
        if not all_customers:
            logger.warning("No customers available to search")
            return None
        
        # ================================================================
        # STEP 1: Exact match (case-insensitive)
        # ================================================================
        for customer in all_customers:
            if customer is None or not isinstance(customer, dict):
                continue
            customer_name = customer.get("CardName", "")
            if customer_name is None:
                continue
            if customer_name.lower() == name_lower:
                logger.info(f"✅ Exact match found for customer: {customer.get('CardName')}")
                return customer
        
        # ================================================================
        # STEP 2: Partial match - all search terms appear in customer name
        # Example: "cash sale" matches "CASH SALE - TRADING"
        # ================================================================
        search_terms = name_lower.split()
        best_matches = []
        
        for customer in all_customers:
            if customer is None or not isinstance(customer, dict):
                continue
            customer_name = customer.get("CardName", "")
            if customer_name is None:
                continue
            customer_name_lower = customer_name.lower()
            
            # Check if all search terms are present in the customer name
            all_terms_found = all(term in customer_name_lower for term in search_terms)
            if all_terms_found:
                # Calculate match score
                term_coverage = sum(1 for term in search_terms if term in customer_name_lower) / len(search_terms)
                # Exact match of full name gets boost
                exact_boost = 1.0 if customer_name_lower == name_lower else 0
                # Shorter names get slight boost
                name_boost = 1.0 / (len(customer_name_lower) / 20)
                score = term_coverage + exact_boost + name_boost
                best_matches.append((score, customer))
        
        if best_matches:
            # Sort by score (highest first) and return best match
            best_matches.sort(key=lambda x: x[0], reverse=True)
            best_match = best_matches[0][1]
            logger.info(f"✅ Partial match found: '{name}' → '{best_match.get('CardName')}'")
            return best_match
        
        # ================================================================
        # STEP 3: Try matching by CardCode
        # ================================================================
        for customer in all_customers:
            if customer is None or not isinstance(customer, dict):
                continue
            card_code = customer.get("CardCode", "")
            if card_code is None:
                continue
            if card_code.lower() == name_lower or name_lower in card_code.lower():
                logger.info(f"✅ Match by CardCode: '{name}' → '{customer.get('CardName')}'")
                return customer
        
        # ================================================================
        # STEP 4: Fuzzy match using difflib for close matches
        # ================================================================
        customer_names = [c.get("CardName", "") for c in all_customers if c and c.get("CardName")]
        fuzzy_matches = get_close_matches(name, customer_names, n=3, cutoff=0.6)
        
        if fuzzy_matches:
            for match_name in fuzzy_matches:
                for customer in all_customers:
                    if customer and customer.get("CardName") == match_name:
                        logger.info(f"✅ Fuzzy match found: '{name}' → '{match_name}'")
                        return customer
        
        # ================================================================
        # STEP 5: Try with cleaned search term (remove suffixes)
        # ================================================================
        cleaned = clean_customer_search_term(name)
        if cleaned != name and len(cleaned) > 2:
            for customer in all_customers:
                if customer is None or not isinstance(customer, dict):
                    continue
                customer_name = customer.get("CardName", "")
                if customer_name is None:
                    continue
                if cleaned.lower() in customer_name.lower() or customer_name.lower().startswith(cleaned.lower()):
                    logger.info(f"✅ Match using cleaned term '{cleaned}': {customer.get('CardName')}")
                    return customer
        
        # ================================================================
        # STEP 6: Try single word match (first or last word of search)
        # ================================================================
        if len(search_terms) > 1:
            for term in search_terms:
                if len(term) > 2:
                    for customer in all_customers:
                        if customer is None or not isinstance(customer, dict):
                            continue
                        customer_name = customer.get("CardName", "")
                        if customer_name is None:
                            continue
                        if term in customer_name.lower():
                            logger.info(f"✅ Single term match: '{term}' in '{customer.get('CardName')}'")
                            return customer
        
        logger.warning(f"❌ No customer found for: '{name}'")
        return None
    
    def search_customers_by_term(self, search_term: str, limit: int = 10) -> List[Dict]:
        """
        Search customers by term - returns all matching customers.
        Useful for autocomplete or showing multiple matches.
        """
        if not search_term:
            return self.get_customers(limit=limit)
        
        # Use local filtering for better results
        return self._get_customers_with_local_filter(search_term, limit)
    
    def clear_customer_cache(self):
        """Clear the cached customers list."""
        self._cached_customers = None
        logger.info("Customer cache cleared")