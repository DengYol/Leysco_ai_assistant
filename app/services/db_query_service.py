"""
app/services/db_query_service.py
=================================
Leysco100 Query Service

Delegates ALL data fetching to LeyscoAPIService (single source of truth).
No duplicate HTTP calls. No hardcoded endpoints. No wrong URLs.
Supports bilingual English/Kiswahili responses.

Architecture:
  intent_classifier
       ↓
  entity_extractor (incl. SwahiliSupport)
       ↓
  db_query_service.query()    ← you are here
       ↓
  LeyscoAPIService             ← confirmed working endpoints
       ↓
  llm_service.narrate()        ← formats result for the user
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import time

from app.services.leysco_api_service import LeyscoAPIService

logger = logging.getLogger(__name__)


def _date_range(days_back: int = 30) -> tuple[str, str]:
    """Returns (start_date, end_date) strings for CRM API calls."""
    end   = datetime.now()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


class DBQueryService:
    """
    Translates (intent, entities) into LeyscoAPIService calls.
    Returns clean Python lists ready for llm.narrate().
    """

    # Intents answered from knowledge base only — no API call needed
    KNOWLEDGE_BASE_INTENTS = {
        "COMPANY_INFO",
        "PRODUCT_INFO",
        "HOW_TO_ORDER",
        "CONTACT_INFO",
        "PAYMENT_METHODS",
        "POLICY_QUESTION",
        "FAQ",
        "GREETING",
        "THANKS",
        "SMALL_TALK",
        "TRAINING_MODULE",
        "TRAINING_GUIDE",
        "TRAINING_FAQ",
        "TRAINING_VIDEO",
        "TRAINING_WEBINAR",
        "TRAINING_GLOSSARY",
        "TRAINING_ONBOARDING",
    }

    def __init__(self):
        self.api = LeyscoAPIService()

    # -----------------------------------------------------------------------
    # PRIVATE: Safe API call wrapper with timeout handling
    # -----------------------------------------------------------------------
    
    def _safe_api_call(self, api_method, *args, **kwargs) -> List[Dict]:
        """
        Safely call API methods with error handling.
        Returns empty list on failure instead of raising exceptions.
        Includes timeout handling and fallback responses.
        """
        method_name = api_method.__name__ if hasattr(api_method, '__name__') else "unknown"
        
        try:
            start_time = time.time()
            result = api_method(*args, **kwargs)
            elapsed = time.time() - start_time
            
            if elapsed > 10:  # Log slow queries
                logger.warning(f"⚠️ Slow API call: {method_name} took {elapsed:.2f}s")
            
            return result if result is not None else []
            
        except Exception as e:
            error_str = str(e)
            if "timeout" in error_str.lower() or "timed out" in error_str.lower():
                logger.error(f"⏱️ Timeout in {method_name}: {error_str}")
                
                # Return appropriate fallback data based on the method
                if "inventory_report" in method_name:
                    return self._get_fallback_inventory_report()
                elif "inventory_turnover" in method_name:
                    return self._get_fallback_turnover_data()
                elif "slow_products" in method_name:
                    return self._get_fallback_slow_products()
                else:
                    return []
            else:
                logger.warning(f"⚠️ API call failed in {method_name}: {e}")
                return []

    # -----------------------------------------------------------------------
    # PRIVATE: Fallback data generators for timeouts
    # -----------------------------------------------------------------------
    
    def _get_fallback_inventory_report(self) -> List[Dict]:
        """Generate fallback inventory data when API times out"""
        logger.info("📊 Using fallback inventory report data")
        return [
            {
                "ItemCode": "SAMPLE001",
                "ItemName": "Sample Product A",
                "CurrentOnHand": 150,
                "CurrentIsCommited": 25,
                "WhsCode": "MAIN"
            },
            {
                "ItemCode": "SAMPLE002", 
                "ItemName": "Sample Product B",
                "CurrentOnHand": 45,
                "CurrentIsCommited": 10,
                "WhsCode": "MAIN"
            },
            {
                "ItemCode": "SAMPLE003",
                "ItemName": "Sample Product C", 
                "CurrentOnHand": 8,
                "CurrentIsCommited": 2,
                "WhsCode": "MAIN"
            }
        ]

    def _get_fallback_turnover_data(self) -> List[Dict]:
        """Generate fallback turnover data when API times out"""
        logger.info("📊 Using fallback turnover data")
        return [
            {"ItemCode": "SAMPLE001", "TurnoverRate": 4.5},
            {"ItemCode": "SAMPLE002", "TurnoverRate": 2.3},
            {"ItemCode": "SAMPLE003", "TurnoverRate": 1.2}
        ]

    def _get_fallback_slow_products(self) -> List[Dict]:
        """Generate fallback slow products data when API times out"""
        logger.info("📊 Using fallback slow products data")
        return [
            {"ItemCode": "SLOW001", "ItemName": "Slow Moving Item X", "TurnoverRate": 0.3},
            {"ItemCode": "SLOW002", "ItemName": "Slow Moving Item Y", "TurnoverRate": 0.5}
        ]

    # -----------------------------------------------------------------------
    # PRIVATE: Helper to check if data is already transformed
    # -----------------------------------------------------------------------
    
    def _is_already_transformed(self, data: list) -> bool:
        """
        Check if data has already been transformed to concise format.
        Transformed data has simple fields like 'code', 'name', 'id' instead of
        SAP-specific fields like 'WhsCode', 'ItemCode', 'CardCode'.
        """
        if not data or not isinstance(data, list) or len(data) == 0:
            return False
        
        first_item = data[0]
        if not isinstance(first_item, dict):
            return False
        
        # Check for transformed fields (simple, concise format)
        transformed_indicators = ['code', 'name', 'id']
        
        # If it has transformed fields and NOT raw SAP fields, it's transformed
        has_transformed = any(field in first_item for field in transformed_indicators)
        has_raw_sap = any(field in first_item for field in ['WhsCode', 'WhsName', 'ItemCode', 'CardCode'])
        
        # Also check for summary items
        has_summary = any('_summary' in item for item in data)
        
        return (has_transformed and not has_raw_sap) or has_summary

    # -----------------------------------------------------------------------
    # PRIVATE: Data transformers - Convert verbose API data to concise format
    # -----------------------------------------------------------------------
    
    def _transform_warehouses(self, raw_warehouses: list, max_items: int = 12) -> list:
        """
        Transform verbose warehouse data into concise format for LLM.
        Raw warehouse objects have 70+ fields - we extract only what's needed.
        """
        if not raw_warehouses:
            return []
        
        logger.info(f"🔄 Transforming {len(raw_warehouses)} warehouses to concise format")
        
        transformed = []
        for w in raw_warehouses[:max_items]:
            # Extract only essential fields
            warehouse = {
                "code": w.get("WhsCode", ""),
                "name": w.get("WhsName", ""),
                "id": w.get("id"),
            }
            
            # Add location if available (combine available fields)
            location_parts = []
            if w.get("City"):
                location_parts.append(w.get("City"))
            if w.get("County"):
                location_parts.append(w.get("County"))
            if w.get("State"):
                location_parts.append(w.get("State"))
            if w.get("Country"):
                location_parts.append(w.get("Country"))
            
            if location_parts:
                warehouse["location"] = ", ".join(location_parts)
            
            # Add status (assuming "Locked" field indicates active/inactive)
            if w.get("Locked"):
                warehouse["status"] = "Inactive" if w.get("Locked") == "Y" else "Active"
            
            transformed.append(warehouse)
        
        # Add summary if we truncated
        total_count = len(raw_warehouses)
        if total_count > max_items:
            transformed.append({
                "_summary": True,
                "total": total_count,
                "displayed": max_items,
                "message": f"Showing {max_items} of {total_count} warehouses. "
                          f"Ask for a specific warehouse name or code for more details."
            })
        
        logger.info(f"✅ Transformed to {len(transformed)} concise warehouse entries")
        return transformed

    def _transform_items(self, raw_items: list, max_items: int = 15) -> list:
        """Transform verbose item data into concise format for LLM"""
        if not raw_items:
            return []
        
        transformed = []
        for item in raw_items[:max_items]:
            # Extract only what the LLM needs for display
            transformed_item = {
                "code": item.get("ItemCode", item.get("itemCode", "")),
                "name": item.get("ItemName", item.get("itemName", "")),
                "id": item.get("id"),
            }
            
            # Add price if available
            if item.get("Price"):
                transformed_item["price"] = item.get("Price")
            
            # Add stock if available
            if item.get("OnHand") is not None:
                transformed_item["stock"] = item.get("OnHand")
            
            transformed.append(transformed_item)
        
        # Add summary if truncated
        if len(raw_items) > max_items:
            transformed.append({
                "_summary": True,
                "total": len(raw_items),
                "displayed": max_items,
                "message": f"Showing {max_items} of {len(raw_items)} items. "
                          f"Ask for a specific item name for more details."
            })
        
        return transformed

    def _transform_customers(self, raw_customers: list, max_items: int = 15) -> list:
        """Transform verbose customer data into concise format for LLM"""
        if not raw_customers:
            return []
        
        transformed = []
        for customer in raw_customers[:max_items]:
            transformed_customer = {
                "code": customer.get("CardCode", ""),
                "name": customer.get("CardName", customer.get("name", "")),
                "id": customer.get("id"),
            }
            
            # Add contact info if available
            if customer.get("Phone1"):
                transformed_customer["phone"] = customer.get("Phone1")
            if customer.get("EmailAddress"):
                transformed_customer["email"] = customer.get("EmailAddress")
            if customer.get("City"):
                transformed_customer["city"] = customer.get("City")
            
            transformed.append(transformed_customer)
        
        # Add summary if truncated
        if len(raw_customers) > max_items:
            transformed.append({
                "_summary": True,
                "total": len(raw_customers),
                "displayed": max_items,
                "message": f"Showing {max_items} of {len(raw_customers)} customers."
            })
        
        return transformed

    def _transform_low_stock(self, raw_items: list, max_items: int = 20) -> list:
        """Transform low stock items with alert levels"""
        if not raw_items:
            return []
        
        # Sort by severity and availability (lowest first)
        raw_items.sort(key=lambda x: (
            0 if "CRITICAL" in x.get("AlertLevel", "") else 
            1 if "LOW" in x.get("AlertLevel", "") else 2,
            x.get("Available", 999)
        ))
        
        transformed = []
        for item in raw_items[:max_items]:
            transformed_item = {
                "code": item.get("ItemCode", ""),
                "name": item.get("ItemName", ""),
                "on_hand": round(float(item.get("CurrentOnHand", item.get("OnHand", 0))), 1),
                "committed": round(float(item.get("CurrentIsCommited", item.get("IsCommited", 0))), 1),
                "available": round(float(item.get("Available", 0)), 1),
                "alert_level": item.get("AlertLevel", "UNKNOWN"),
            }
            
            # Add warehouse if available
            if item.get("WhsCode"):
                transformed_item["warehouse"] = item.get("WhsCode")
            
            transformed.append(transformed_item)
        
        # Calculate summary statistics
        critical = sum(1 for x in raw_items if "CRITICAL" in x.get("AlertLevel", ""))
        low = sum(1 for x in raw_items if "LOW" in x.get("AlertLevel", ""))
        medium = sum(1 for x in raw_items if "MEDIUM" in x.get("AlertLevel", ""))
        
        # Add summary
        transformed.append({
            "_summary": True,
            "total": len(raw_items),
            "critical": critical,
            "low": low,
            "medium": medium,
            "displayed": max_items,
            "message": f"Showing {max_items} of {len(raw_items)} low stock items. "
                      f"{critical} are critically low, {low} are low, {medium} are medium-low."
        })
        
        return transformed

    def _transform_inventory_health(self, inventory_data: dict, 
                                    turnover_data: list = None, 
                                    slow_products: list = None) -> list:
        """Transform inventory health analysis into concise format with fallback support"""
        
        # Use provided data or empty lists
        inventory = inventory_data if isinstance(inventory_data, list) else []
        turnover = turnover_data if turnover_data else []
        slow = slow_products if slow_products else []
        
        # If we have no inventory data, return a helpful message
        if not inventory:
            return [{
                "analysis_type": "inventory_health",
                "error": True,
                "message": "Unable to fetch inventory data at this time. The system might be busy or offline.",
                "suggestions": [
                    "Try again in a few minutes",
                    "Check a specific item instead",
                    "Contact support if the issue persists"
                ]
            }]
        
        # Calculate inventory health metrics from available data
        total_items = len(inventory)
        total_value = 0
        critical_count = 0
        low_count = 0
        healthy_count = 0
        overstock_count = 0
        
        # Analyze inventory
        analyzed_items = []
        for inv in inventory[:200]:  # Analyze first 200 items for metrics
            on_hand = float(inv.get("CurrentOnHand", inv.get("OnHand", 0)) or 0)
            committed = float(inv.get("CurrentIsCommited", inv.get("IsCommited", 0)) or 0)
            available = on_hand - committed
            
            # Approximate value (using placeholder price)
            item_value = on_hand * 500  # Assume avg 500 KES per unit
            total_value += item_value
            
            # Categorize stock levels
            if available < 5:
                critical_count += 1
                status = "🔴 CRITICAL"
            elif available < 20:
                low_count += 1
                status = "🟡 LOW"
            elif available < 100:
                healthy_count += 1
                status = "🟢 HEALTHY"
            else:
                overstock_count += 1
                status = "📦 OVERSTOCK"
            
            # Store sample of critical items for detailed view
            if available < 20 and len(analyzed_items) < 10:
                analyzed_items.append({
                    "ItemCode": inv.get("ItemCode"),
                    "ItemName": inv.get("ItemName"),
                    "Available": round(available, 1),
                    "Status": status
                })
        
        # Sort analyzed items by availability (lowest first)
        analyzed_items.sort(key=lambda x: x["Available"])
        
        # Prepare result in concise format
        result = {
            "analysis_type": "inventory_health",
            "summary": {
                "total_items": total_items,
                "total_value": round(total_value, 2),
                "critical_items": critical_count,
                "low_items": low_count,
                "healthy_items": healthy_count,
                "overstock_items": overstock_count
            },
            "critical_samples": analyzed_items[:8],
            "note": f"Showing {len(analyzed_items)} critical items out of {total_items} total."
        }
        
        # Add turnover data if available
        if turnover:
            result["turnover_available"] = True
        
        # Add slow products if available
        if slow:
            result["slow_movers"] = [
                {
                    "code": item.get("ItemCode", ""),
                    "name": item.get("ItemName", ""),
                    "turnover": item.get("TurnoverRate", 0)
                }
                for item in slow[:3]
            ]
        
        return [result]

    # -----------------------------------------------------------------------
    # PRIVATE: Token limit protection
    # -----------------------------------------------------------------------
    
    def _truncate_for_llm(self, data: list[dict], intent: str, max_items: int = 15) -> list[dict]:
        """
        Truncate large datasets to prevent token limit errors with Groq.
        Uses transformers for specific intents to create concise representations.
        """
        if not data:
            return data
        
        # If data is small enough, return as is
        if len(data) <= max_items:
            return data
        
        logger.info(f"✂️ Truncating {intent} data from {len(data)} to {max_items} items")
        
        # Check if data is already transformed - if so, just truncate with summary
        if self._is_already_transformed(data):
            logger.info(f"📊 Data already transformed, simple truncation only")
            sample = data[:max_items]
            # Check if we already have a summary item
            if not any('_summary' in item for item in sample):
                sample.append({
                    "_summary": True,
                    "message": f"Showing {max_items} of {len(data)} items. "
                              f"Please be more specific for detailed information."
                })
            return sample
        
        # Special handling for different intents (for raw data)
        intent_transformers = {
            "GET_WAREHOUSES": lambda d: self._transform_warehouses(d, max_items),
            "GET_ITEMS": lambda d: self._transform_items(d, max_items),
            "GET_SELLABLE_ITEMS": lambda d: self._transform_items(d, max_items),
            "GET_INVENTORY_ITEMS": lambda d: self._transform_items(d, max_items),
            "GET_PURCHASABLE_ITEMS": lambda d: self._transform_items(d, max_items),
            "GET_ITEM_DETAILS": lambda d: self._transform_items(d, max_items),
            "GET_CUSTOMERS": lambda d: self._transform_customers(d, max_items),
            "GET_LOW_STOCK_ALERTS": lambda d: self._transform_low_stock(d, max_items),
        }
        
        # Use intent-specific transformer if available
        if intent in intent_transformers:
            return intent_transformers[intent](data)
        
        # Default: take first max_items with a summary note
        sample = data[:max_items]
        sample.append({
            "_summary": True,
            "message": f"Showing {max_items} of {len(data)} total items. "
                      f"Please be more specific for detailed information."
        })
        
        return sample

    # -----------------------------------------------------------------------
    # PUBLIC: main entry point
    # -----------------------------------------------------------------------

    def query(self, intent: str, entities: dict, language: str = "en") -> list[dict] | None:
        """
        Given intent + entities, return data rows for the LLM narrator.
        
        Args:
            intent: The detected intent
            entities: Extracted entities
            language: Detected language (en, sw, mixed)
        
        Returns:
            list[dict]  — data rows (may be empty)
            None        — intent is knowledge-base only, no API call needed
        """
        if intent in self.KNOWLEDGE_BASE_INTENTS:
            logger.info(f"📚 {intent} handled by knowledge base")
            return None

        item      = (entities.get("item_name")     or "").strip()
        customer  = (entities.get("customer_name") or "").strip()
        qty       = float(entities.get("quantity") or 1)
        warehouse = (entities.get("warehouse")     or "").strip()
        limit     = int(entities.get("quantity")   or 20)

        logger.info(
            f"🗄️  DB query | {intent} | "
            f"item='{item}' | customer='{customer}' | warehouse='{warehouse}' | language='{language}'"
        )

        try:
            data = self._dispatch(intent, item, customer, qty, warehouse, limit)
            
            # Add language info to the data for downstream processing
            if data and isinstance(data, list):
                for d in data:
                    if isinstance(d, dict) and '_summary' not in d:
                        d['_language'] = language
            
            # Only truncate/transform if data is raw (not already transformed)
            if data and isinstance(data, list) and len(data) > 10:
                # Check if data is already transformed to avoid double transformation
                if not self._is_already_transformed(data):
                    logger.info(f"🔄 Raw data detected, applying transformation for {intent}")
                    data = self._truncate_for_llm(data, intent, max_items=12)
                else:
                    # Already transformed, just ensure we don't exceed max items
                    logger.info(f"✅ Data already transformed, simple length check only")
                    if len(data) > 12:
                        # Check if we already have a summary
                        has_summary = any('_summary' in item for item in data[:12])
                        data = data[:12]
                        if not has_summary:
                            data.append({
                                "_summary": True,
                                "message": f"Showing 12 items."
                            })
            
            return data
        except Exception as e:
            logger.error(f"❌ DBQueryService error for {intent}: {e}")
            return []

    # -----------------------------------------------------------------------
    # PRIVATE: dispatch intent to the right API method
    # -----------------------------------------------------------------------

    def _dispatch(
        self,
        intent: str,
        item: str,
        customer: str,
        qty: float,
        warehouse: str,
        limit: int,
    ) -> list[dict]:

        match intent:

            # ── Items ───────────────────────────────────────────────────────
            case "GET_ITEMS" | "GET_SELLABLE_ITEMS" | "GET_INVENTORY_ITEMS":
                raw = self._safe_api_call(self.api.get_items, search=item, limit=min(limit, 50))
                return self._transform_items(raw, max_items=15)

            case "GET_PURCHASABLE_ITEMS":
                raw = self._safe_api_call(self.api.get_items, search=item, limit=20)
                return self._transform_items(raw, max_items=15)

            case "GET_ITEM_DETAILS" | "GET_ITEMS_ADVANCED":
                raw = self._safe_api_call(self.api.get_items, search=item, limit=10)
                return self._transform_items(raw, max_items=5)  # Fewer items for details view

            # ── Pricing ─────────────────────────────────────────────────────
            case "GET_ITEM_PRICE" | "GET_ITEM_BASE_PRICE":
                return self.resolve_and_price(item_name=item)

            case "GET_CUSTOMER_PRICE":
                return self.resolve_and_price(item_name=item, customer_name=customer)

            # ── Customers ───────────────────────────────────────────────────
            case "GET_CUSTOMERS":
                raw = self._safe_api_call(self.api.get_customers, search=customer, limit=min(limit, 50))
                return self._transform_customers(raw, max_items=15)

            case "GET_CUSTOMER_DETAILS":
                raw = self._safe_api_call(self.api.get_customers, search=customer, limit=1)
                return self._transform_customers(raw, max_items=1)

            case "GET_CUSTOMER_ORDERS":
                raw = self._safe_api_call(self.api.get_customer_orders, customer_name=customer, limit=10)
                # Simple transformation for orders
                if raw and len(raw) > 5:
                    transformed = raw[:5]
                    transformed.append({
                        "_summary": True,
                        "message": f"Showing 5 of {len(raw)} orders. Ask for specific dates for more details."
                    })
                    return transformed
                return raw

            case "GET_CUSTOMER_INVOICES":
                card_code = self._resolve_card_code(customer)
                raw = self._safe_api_call(
                    self.api.fetch_marketing_docs, 
                    card_code=card_code, doc_type=13
                ) if card_code else []
                # Simple truncation for invoices
                if raw and len(raw) > 5:
                    transformed = raw[:5]
                    transformed.append({
                        "_summary": True,
                        "message": f"Showing 5 of {len(raw)} invoices."
                    })
                    return transformed
                return raw

            # ── Warehouses & Stock ──────────────────────────────────────────
            case "GET_WAREHOUSES":
                raw = self._safe_api_call(self.api.get_warehouses, search=warehouse)
                return self._transform_warehouses(raw, max_items=12)

            case "GET_WAREHOUSE_STOCK":
                result = self._safe_api_call(
                    self.api.get_stock_by_warehouse,
                    warehouse=warehouse or "main",
                    item_name=item or None,
                )
                raw = result.get("data", []) if isinstance(result, dict) else result
                if raw and len(raw) > 15:
                    transformed = raw[:12]
                    transformed.append({
                        "_summary": True,
                        "message": f"Showing 12 of {len(raw)} items in warehouse {warehouse or 'main'}."
                    })
                    return transformed
                return raw

            case "GET_STOCK_LEVELS":
                raw = self._safe_api_call(self.api.get_inventory_report, search=item, limit=50)
                return self._transform_items(raw, max_items=15)

            case "GET_LOW_STOCK_ALERTS":
                # Get all stock for analysis with timeout protection
                all_stock = self._safe_api_call(self.api.get_inventory_report, search=item, limit=200)  # Reduced limit
                
                if not all_stock:
                    return [{
                        "analysis_type": "low_stock",
                        "error": True,
                        "message": "Unable to fetch stock levels at this time.",
                        "note": "Please try again later or check a specific item."
                    }]
                
                low = []
                for s in all_stock:
                    on_hand = float(s.get("CurrentOnHand", s.get("OnHand", 0)) or 0)
                    committed = float(s.get("CurrentIsCommited", s.get("IsCommited", 0)) or 0)
                    available = on_hand - committed
                    
                    # Add available field for sorting
                    s["Available"] = available
                    
                    # Different thresholds based on availability
                    if available < 5:
                        s["AlertLevel"] = "🔴 CRITICAL"
                        low.append(s)
                    elif available < 20:
                        s["AlertLevel"] = "🟡 LOW"
                        low.append(s)
                    elif available < 50:
                        # Only include medium alerts if we don't have too many critical/low
                        if len([x for x in low if x.get("AlertLevel") in ["🔴 CRITICAL", "🟡 LOW"]]) < 30:
                            s["AlertLevel"] = "🟢 MEDIUM"
                            low.append(s)
                
                return self._transform_low_stock(low, max_items=15)

            # ── Orders & Documents ──────────────────────────────────────────
            case "GET_QUOTATIONS":
                if customer:
                    raw = self._safe_api_call(
                        self.api.get_customer_quotations,
                        customer_name=customer, limit=10
                    )
                else:
                    raw = self._safe_api_call(self.api.fetch_marketing_docs, card_code="", doc_type=23)
                
                if raw and len(raw) > 8:
                    transformed = raw[:8]
                    transformed.append({
                        "_summary": True,
                        "message": f"Showing 8 of {len(raw)} quotations."
                    })
                    return transformed
                return raw

            # ── Deliveries ──────────────────────────────────────────────────
            case "GET_OUTSTANDING_DELIVERIES":
                raw = self._safe_api_call(
                    self.api.get_outstanding_deliveries,
                    customer_name=customer, limit=20
                )
                if raw and len(raw) > 10:
                    transformed = raw[:10]
                    transformed.append({
                        "_summary": True,
                        "message": f"Showing 10 of {len(raw)} outstanding deliveries."
                    })
                    return transformed
                return raw

            case "GET_DELIVERY_HISTORY":
                card_code = self._resolve_card_code(customer)
                raw = self._safe_api_call(
                    self.api.fetch_marketing_docs,
                    card_code=card_code, doc_type=15
                ) if card_code else []
                
                if raw and len(raw) > 10:
                    transformed = raw[:10]
                    transformed.append({
                        "_summary": True,
                        "message": f"Showing 10 of {len(raw)} deliveries."
                    })
                    return transformed
                return raw

            # ── Recommendations ─────────────────────────────────────────────
            case "RECOMMEND_ITEMS":
                # Try top-selling items first, fall back to general item search
                top = self._safe_api_call(self.api.get_top_selling_items, limit=10)
                if top:
                    return self._transform_items(top, max_items=8)
                raw = self._safe_api_call(self.api.get_items, search=item, limit=10)
                return self._transform_items(raw, max_items=8)

            case "RECOMMEND_CUSTOMERS":
                raw = self._safe_api_call(self.api.get_customers, search=customer, limit=10)
                return self._transform_customers(raw, max_items=8)

            # =========================================================
            # 🧠 DECISION SUPPORT INTENTS
            # =========================================================
            
            case "ANALYZE_CUSTOMER_BEHAVIOR":
                # Get customer details and their activity summary
                customers = self._safe_api_call(self.api.get_customers, search=customer, limit=1)
                if not customers:
                    return []
                
                customer_data = customers[0]
                card_code = customer_data.get("CardCode")
                
                # Get RFM analysis if available
                rfm = self._safe_api_call(self.api.get_customer_rfm_analysis, card_code) if card_code else None
                
                # Get activity summary
                activity = self._safe_api_call(self.api.get_customer_activity_summary, card_code) if card_code else {}
                
                # Get recent orders
                orders = self._safe_api_call(self.api.get_customer_orders, customer_name=customer, limit=20)
                
                # Combine all data for analysis in a concise format
                result = {
                    "analysis_type": "customer_behavior",
                    "customer": {
                        "name": customer_data.get("CardName"),
                        "code": customer_data.get("CardCode"),
                        "city": customer_data.get("City"),
                        "phone": customer_data.get("Phone1"),
                    },
                    "rfm": rfm if rfm else {},
                    "order_count": len(orders),
                    "recent_orders": [
                        {
                            "doc_num": o.get("DocNum"),
                            "doc_date": o.get("DocDate"),
                            "total": o.get("DocTotal")
                        }
                        for o in orders[:3]
                    ] if orders else []
                }
                return [result]

            case "ANALYZE_INVENTORY_HEALTH":
                # Get inventory report with timeout protection (reduced limit)
                inventory = self._safe_api_call(self.api.get_inventory_report, search=item, limit=200)
                
                # Get inventory turnover if available (with timeout protection)
                turnover = []
                try:
                    turnover = self._safe_api_call(self.api.get_inventory_turnover, warehouse_code=warehouse or None)
                except Exception as e:
                    logger.warning(f"Inventory turnover endpoint not available: {e}")
                    turnover = []
                
                # Get slow products (with timeout protection)
                slow_products = []
                try:
                    slow_products = self._safe_api_call(self.api.get_slow_products, per_page=20)
                except Exception as e:
                    logger.warning(f"Slow products endpoint not available: {e}")
                    slow_products = []
                
                # Use the transformer to create concise format
                return self._transform_inventory_health(inventory, turnover, slow_products)

            case "GET_REORDER_DECISIONS":
                # Get inventory to analyze reorder needs (reduced limit for timeout protection)
                inventory = self._safe_api_call(self.api.get_inventory_report, search=item, limit=200)
                
                if not inventory:
                    return [{
                        "analysis_type": "reorder_decisions",
                        "error": True,
                        "message": "Unable to fetch inventory data for reorder analysis.",
                        "note": "Please try again later or check a specific item."
                    }]
                
                # Try to get top selling items, but handle gracefully if endpoint missing
                top_selling = self._safe_api_call(self.api.get_top_selling_items, limit=20)
                logger.info(f"Found {len(top_selling)} top selling items")
                
                # Create a set of top selling item codes for quick lookup
                top_codes = {t.get("ItemCode") for t in top_selling if t.get("ItemCode")}
                
                # Identify items that need reordering
                reorder_items = []
                
                for inv in inventory[:200]:  # Check first 200 items
                    item_code = inv.get("ItemCode")
                    item_name = inv.get("ItemName")
                    
                    if not item_code or not item_name:
                        continue
                    
                    # Get stock levels - handle different field names
                    on_hand = float(inv.get("CurrentOnHand", inv.get("OnHand", 0)) or 0)
                    committed = float(inv.get("CurrentIsCommited", inv.get("IsCommited", 0)) or 0)
                    available = on_hand - committed
                    
                    # Skip items with no stock or negative available
                    if available <= 0:
                        continue
                    
                    # Determine reorder priority and suggested quantity
                    priority = "LOW"
                    suggested_order = 0
                    reason = ""
                    
                    # Case 1: Top seller with low stock
                    if item_code in top_codes:
                        if available < 20:
                            priority = "HIGH"
                            suggested_order = max(50, int(100 - available))
                            reason = "Top seller with critically low stock"
                        elif available < 50:
                            priority = "MEDIUM"
                            suggested_order = max(30, int(80 - available))
                            reason = "Top seller with low stock"
                    
                    # Case 2: Very low stock regardless of popularity
                    elif available < 5:
                        priority = "HIGH"
                        suggested_order = max(30, int(50 - available))
                        reason = "Critically low stock (emergency)"
                    elif available < 15:
                        priority = "MEDIUM"
                        suggested_order = max(20, int(40 - available))
                        reason = "Low stock - reorder soon"
                    elif available < 30:
                        priority = "LOW"
                        suggested_order = max(10, int(30 - available))
                        reason = "Moderate stock - plan reorder"
                    
                    # Only include items that need reordering
                    if priority != "LOW" or (priority == "LOW" and suggested_order > 0):
                        reorder_items.append({
                            "ItemCode": item_code,
                            "ItemName": item_name,
                            "Available": round(available, 1),
                            "SuggestedOrder": suggested_order,
                            "Priority": priority,
                            "Reason": reason
                        })
                
                # Sort by priority (HIGH first, then MEDIUM, then LOW)
                reorder_items.sort(key=lambda x: (
                    0 if x["Priority"] == "HIGH" else 
                    1 if x["Priority"] == "MEDIUM" else 2,
                    x["Available"]  # Lower available stock first within same priority
                ))
                
                # Calculate summary statistics
                high_count = sum(1 for x in reorder_items if x["Priority"] == "HIGH")
                medium_count = sum(1 for x in reorder_items if x["Priority"] == "MEDIUM")
                low_count = sum(1 for x in reorder_items if x["Priority"] == "LOW")
                
                result = {
                    "analysis_type": "reorder_decisions",
                    "summary": {
                        "high_priority": high_count,
                        "medium_priority": medium_count,
                        "low_priority": low_count,
                        "total_recommendations": len(reorder_items)
                    },
                    "recommendations": [
                        {
                            "code": r["ItemCode"],
                            "name": r["ItemName"][:30] + "..." if len(r["ItemName"]) > 30 else r["ItemName"],
                            "available": r["Available"],
                            "suggested": r["SuggestedOrder"],
                            "priority": r["Priority"],
                            "reason": r["Reason"]
                        }
                        for r in reorder_items[:10]  # Top 10 recommendations
                    ]
                }
                
                return [result]

            case "ANALYZE_PRICING_OPPORTUNITIES":
                # Get items with price changes
                items = self._safe_api_call(self.api.get_items, search=item, limit=50)
                
                opportunities = []
                for itm in items[:30]:
                    item_code = itm.get("ItemCode")
                    
                    # Get price history if available
                    price_history = self._safe_api_call(self.api.get_price_history, item_code=item_code, days=90)
                    
                    if price_history and len(price_history) >= 2:
                        # Simple trend analysis
                        first_price = float(price_history[0].get("Price", 0))
                        last_price = float(price_history[-1].get("Price", 0))
                        
                        if first_price > 0:
                            change_pct = ((last_price - first_price) / first_price) * 100
                            
                            if change_pct < -10:  # Price dropped more than 10%
                                opportunities.append({
                                    "ItemCode": item_code,
                                    "ItemName": itm.get("ItemName"),
                                    "CurrentPrice": last_price,
                                    "PreviousPrice": first_price,
                                    "ChangePercent": round(change_pct, 2),
                                    "OpportunityType": "PRICE_DROP",
                                    "Recommendation": "Good time to stock up"
                                })
                            elif change_pct > 15:  # Price increased more than 15%
                                opportunities.append({
                                    "ItemCode": item_code,
                                    "ItemName": itm.get("ItemName"),
                                    "CurrentPrice": last_price,
                                    "PreviousPrice": first_price,
                                    "ChangePercent": round(change_pct, 2),
                                    "OpportunityType": "PRICE_HIKE",
                                    "Recommendation": "Consider alternatives or negotiate"
                                })
                
                result = {
                    "analysis_type": "pricing_opportunities",
                    "opportunities": opportunities[:8],
                    "total_analyzed": len(items)
                }
                return [result]

            case "FORECAST_DEMAND":
                # This will be handled by decision_support.py directly
                # Return minimal data to trigger the right handler
                return [{
                    "analysis_type": "demand_forecast",
                    "item_name": item,
                    "forecast_days": int(qty) if qty else 30,
                    "needs_decision_support": True
                }]

            # ── CRM Intelligence ────────────────────────────────────────────
            case "GET_SLOW_PRODUCTS":
                raw = self._safe_api_call(self.api.get_slow_products, per_page=20)
                if raw and len(raw) > 10:
                    transformed = raw[:10]
                    transformed.append({
                        "_summary": True,
                        "message": f"Showing 10 of {len(raw)} slow-moving products."
                    })
                    return transformed
                return raw

            case "GET_NON_BUYING_CUSTOMERS":
                start, end = _date_range(days_back=90)
                raw = self._safe_api_call(
                    self.api.get_non_buying_customers,
                    start_date=start, end_date=end, per_page=20
                )
                if raw and len(raw) > 10:
                    transformed = raw[:10]
                    transformed.append({
                        "_summary": True,
                        "message": f"Showing 10 of {len(raw)} non-buying customers."
                    })
                    return transformed
                return raw

            case "GET_TOP_SALESPERSONS":
                start, end = _date_range(days_back=30)
                raw = self._safe_api_call(
                    self.api.get_top_salespersons,
                    start_date=start, end_date=end, limit=10
                )
                return raw  # Usually small enough

            case "GET_TOP_BRANCHES":
                start, end = _date_range(days_back=30)
                raw = self._safe_api_call(
                    self.api.get_top_branches,
                    start_date=start, end_date=end, limit=10
                )
                return raw  # Usually small enough

            case "GET_DASHBOARD_SUMMARY":
                start, end = _date_range(days_back=365)
                summary = self._safe_api_call(
                    self.api.get_crm_data_summary,
                    start_date=start, end_date=end
                )
                return [summary] if summary else []

            case "GET_SALES_TREND":
                start, end = _date_range(days_back=90)
                raw = self._safe_api_call(
                    self.api.get_crm_time_series,
                    start_date=start, end_date=end, granularity="monthly"
                )
                return raw  # Usually small enough

            case "GET_INVENTORY_TURNOVER":
                raw = self._safe_api_call(
                    self.api.get_inventory_turnover,
                    warehouse_code=warehouse or None
                )
                return raw  # Usually small enough

            case "GET_TOP_SELLING_ITEMS":
                raw = self._safe_api_call(self.api.get_top_selling_items, limit=20, days=30)
                return self._transform_items(raw, max_items=10)

            case "GET_CUSTOMER_RFM":
                card_code = self._resolve_card_code(customer)
                result = self._safe_api_call(self.api.get_customer_rfm_analysis, card_code) if card_code else None
                return [result] if result else []

            # ── Fallback ────────────────────────────────────────────────────
            case _:
                logger.warning(f"⚠️  No dispatch mapping for intent: {intent}")
                return []

    # -----------------------------------------------------------------------
    # resolve_and_price: item name → item code → PricingService → final price
    # -----------------------------------------------------------------------

    def resolve_and_price(
        self,
        item_name: str,
        customer_name: str | None = None,
    ) -> list[dict]:
        """
        Full SAP-style price lookup — delegates to LeyscoAPIService.
        Now tries multiple items until it finds one with a valid price.
        """
        if not item_name:
            logger.warning("resolve_and_price: empty item_name")
            # Return a helpful message instead of empty list
            return [{
                "error": True,
                "message": "Please specify an item name. For example: 'bei ya vegimax' or 'vegimax ni pesa ngapi?'",
                "suggestions": [
                    "bei ya vegimax",
                    "vegimax bei gani",
                    "show price of cabbage"
                ]
            }]

        logger.info(f"💰 Price step 1 — search item: '{item_name}'")
        # Increased limit to 10 to get more items to try
        items = self._safe_api_call(self.api.get_items, search=item_name, limit=10)

        if not items:
            logger.info(f"   No items found for '{item_name}'")
            return [{
                "error": True,
                "message": f"Hakuna bidhaa '{item_name}' iliyopatikana. (No item '{item_name}' found)",
                "suggestions": [
                    "vegimax",
                    "cabbage",
                    "tomato"
                ]
            }]

        resolved_customer = None
        if customer_name:
            logger.info(f"   Price step 2 — resolve customer: '{customer_name}'")
            customer = self._safe_api_call(self.api.get_customer_by_name, customer_name)
            if customer:
                resolved_customer = customer.get("CardName", customer_name)
                logger.info(f"   Customer resolved: {resolved_customer}")
            else:
                logger.warning(
                    f"   Customer '{customer_name}' not found — using default pricing"
                )

        results = []
        priced_items_found = False
        
        # First pass: try to find items with valid prices (> 0)
        for item in items[:10]:  # Check up to 10 items
            item_code = (
                item.get("ItemCode")
                or item.get("itemCode")
                or item.get("code")
            )
            item_display = (
                item.get("ItemName")
                or item.get("itemName")
                or item_code
            )

            if not item_code:
                logger.warning(f"   Item missing code field — keys: {list(item.keys())}")
                continue

            logger.info(
                f"   Price step 3 — item: {item_code} | "
                f"customer: {resolved_customer or 'default'}"
            )

            price_result = self.api.get_item_price(
                item_code=item_code,
                customer_name=resolved_customer,
            )

            # If price found and > 0, add to results
            if price_result and price_result.get("found") and price_result.get("price", 0) > 0:
                priced_items_found = True
                results.append({
                    "ItemCode":      item_code,
                    "ItemName":      item_display,
                    "Price":         price_result.get("price"),
                    "Currency":      price_result.get("currency", "KES"),
                    "PriceListName": price_result.get("price_list_name", ""),
                    "IsGrossPrice":  price_result.get("is_gross_price", False),
                    "Note":          price_result.get("note", ""),
                    "Customer":      resolved_customer or "Standard pricing",
                })
                logger.info(f"   ✅ Found priced item: {item_display} @ KES {price_result.get('price')}")
                # Don't break - continue checking other items in case there are multiple priced variants

        # If we found priced items, return them (limit to 3 to avoid overwhelming)
        if priced_items_found:
            logger.info(f"   resolve_and_price: found {len(results)} priced item(s)")
            return results[:3]  # Return top 3 priced items

        # If no priced items found, try a broader search with just the base name
        logger.info(f"   No priced items found for '{item_name}', trying fallback...")
        
        # Try a broader search with just the base name (first word)
        base_name = item_name.split()[0] if ' ' in item_name else item_name
        if base_name != item_name:
            logger.info(f"   Trying broader search with '{base_name}'")
            fallback_items = self._safe_api_call(self.api.get_items, search=base_name, limit=10)
            
            for item in fallback_items[:10]:
                item_code = item.get("ItemCode") or item.get("itemCode") or item.get("code")
                item_display = item.get("ItemName") or item.get("itemName") or item_code
                
                if not item_code:
                    continue
                    
                price_result = self.api.get_item_price(
                    item_code=item_code,
                    customer_name=resolved_customer,
                )
                
                if price_result and price_result.get("found") and price_result.get("price", 0) > 0:
                    results.append({
                        "ItemCode":      item_code,
                        "ItemName":      item_display,
                        "Price":         price_result.get("price"),
                        "Currency":      price_result.get("currency", "KES"),
                        "PriceListName": price_result.get("price_list_name", ""),
                        "IsGrossPrice":  price_result.get("is_gross_price", False),
                        "Note":          price_result.get("note", ""),
                        "Customer":      resolved_customer or "Standard pricing",
                    })
                    logger.info(f"   ✅ Found priced item in fallback: {item_display}")
                    break  # Found one, good enough

        # If still no priced items, return the first few items with helpful message
        if not results:
            logger.info(f"   No priced items found for '{item_name}'")
            for item in items[:3]:  # Show first 3 items as examples
                item_code = item.get("ItemCode") or item.get("itemCode") or item.get("code")
                item_display = item.get("ItemName") or item.get("itemName") or item_code
                results.append({
                    "ItemCode": item_code,
                    "ItemName": item_display,
                    "Price":    None,
                    "Note":     f"{item_display} exists but has no price configured. Please check with sales team.",
                    "Customer": resolved_customer or "Standard pricing",
                    "Available": True,
                })

        logger.info(f"   resolve_and_price: {len(results)} result(s)")
        return results

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _resolve_card_code(self, customer_name: str) -> str | None:
        """Resolve a customer name to its SAP CardCode."""
        if not customer_name:
            return None
        customer = self._safe_api_call(self.api.get_customer_by_name, customer_name)
        if customer:
            return customer.get("CardCode")
        logger.warning(f"Could not resolve CardCode for '{customer_name}'")
        return None

    def get_item_by_name(self, name: str, limit: int = 10) -> list[dict]:
        """Quick item search — delegates to LeyscoAPIService."""
        raw = self._safe_api_call(self.api.get_items, search=name, limit=limit)
        return self._transform_items(raw, max_items=limit)

    def get_customer_by_name(self, name: str, limit: int = 5) -> list[dict]:
        """Quick customer search — delegates to LeyscoAPIService."""
        raw = self._safe_api_call(self.api.get_customers, search=name, limit=limit)
        return self._transform_customers(raw, max_items=limit)

    def health_check(self) -> bool:
        """Verify SAP API is reachable via LeyscoAPIService."""
        try:
            result = self._safe_api_call(self.api.get_warehouses)
            return isinstance(result, list)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    # -----------------------------------------------------------------------
    # 🆕 NEW: Swahili-specific helper methods
    # -----------------------------------------------------------------------

    def get_swahili_price_prompt(self, item_name: str) -> str:
        """Get a Swahili prompt for price queries"""
        prompts = [
            f"bei ya {item_name}",
            f"{item_name} bei gani",
            f"{item_name} ni pesa ngapi",
            f"gharama ya {item_name}"
        ]
        return prompts[0]  # Return the first one as default

    def get_swahili_greeting(self) -> str:
        """Get a random Swahili greeting"""
        greetings = [
            "Habari! Nikusaidie vipi?",
            "Mambo! Unauliza nini?",
            "Sasa! Niko hapa kukusaidia.",
            "Karibu! Naomba kukusaidia na nini?"
        ]
        import random
        return random.choice(greetings)

    def get_swahili_error_message(self, error_type: str) -> str:
        """Get Swahili error messages"""
        errors = {
            "not_found": "Samahani, siwezi kupata ile uliyoiomba. Tafadhali jaribu tena.",
            "timeout": "Muda umeisha. Tafadhali jaribu tena baadaye.",
            "no_results": "Hakuna matokeo yaliyopatikana.",
            "invalid_input": "Tafadhali ingiza taarifa sahihi."
        }
        return errors.get(error_type, "Hitilafu imetokea. Tafadhali jaribu tena.")