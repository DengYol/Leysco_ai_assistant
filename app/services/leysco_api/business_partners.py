"""Business partner (customer, vendor, lead) operations"""

import logging
from typing import List, Dict, Optional

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
    
    def get_business_partner_type(self, business_partner: Dict) -> str:
        """
        Determine business partner type from the data.
        Checks multiple possible fields and values.
        """
        card_type = business_partner.get("CardType") or business_partner.get("card_type") or business_partner.get("Type") or business_partner.get("type")
        card_name = business_partner.get("CardName", "").lower()
        
        if any(word in card_name for word in ["vendor", "supplier"]):
            return "V"
        if any(word in card_name for word in ["lead", "prospect"]):
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
        return self.get_business_partner_type(business_partner) == "C"
    
    def is_vendor(self, business_partner: Dict) -> bool:
        return self.get_business_partner_type(business_partner) == "V"
    
    def is_lead(self, business_partner: Dict) -> bool:
        return self.get_business_partner_type(business_partner) == "L"
    
    def filter_by_bp_type(self, business_partners: List[Dict], bp_type: str) -> List[Dict]:
        if not business_partners or bp_type is None:
            return business_partners
        
        filtered = []
        for bp in business_partners:
            if bp_type == "C" and self.is_customer(bp):
                filtered.append(bp)
            elif bp_type == "V" and self.is_vendor(bp):
                filtered.append(bp)
            elif bp_type == "L" and self.is_lead(bp):
                filtered.append(bp)
        
        logger.info(f"Filtered {len(filtered)}/{len(business_partners)} business partners for type {bp_type}")
        return filtered
    
    def get_customers(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get customers only (excludes vendors and leads)"""
        return self._fetch_business_partners(search, limit, bp_type="C")
    
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
                
                logger.info(f"📄 Fetching business partners page {page}")
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
                
                # Apply BP type filter
                if bp_type is not None:
                    partners = self.filter_by_bp_type(partners, bp_type)
                
                all_partners.extend(partners)
                logger.info(f"Page {page}: Found {len(partners)} (total: {len(all_partners)})")
                
                # Check pagination
                if len(partners) < per_page:
                    break
                page += 1
                
                if limit and len(all_partners) >= limit:
                    all_partners = all_partners[:limit]
                    break
            
            all_partners.sort(key=lambda x: x.get("CardName", ""))
            logger.info(f"✅ Retrieved {len(all_partners)} total business partners")
            return all_partners
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch business partners: {e}", exc_info=True)
            return []
    
    def resolve_customer(self, name: str) -> Optional[Dict]:
        """
        Resolve customer by name - returns the best matching customer.
        Tries exact match first, then fuzzy match.
        """
        if not name:
            return None
        
        # Try exact match first
        customers = self.get_customers(search=name, limit=10)
        if customers:
            name_lower = name.lower()
            for customer in customers:
                customer_name = customer.get("CardName", "").lower()
                if customer_name == name_lower:
                    logger.info(f"✅ Exact match found for customer: {customer.get('CardName')}")
                    return customer
            
            # Return first match if no exact match
            logger.info(f"✅ Returning first match for customer: {customers[0].get('CardName')}")
            return customers[0]
        
        # Try with cleaned search term
        cleaned = clean_customer_search_term(name)
        if cleaned != name:
            customers = self.get_customers(search=cleaned, limit=5)
            if customers:
                logger.info(f"✅ Found customer using cleaned term '{cleaned}': {customers[0].get('CardName')}")
                return customers[0]
        
        logger.warning(f"❌ No customer found for: {name}")
        return None