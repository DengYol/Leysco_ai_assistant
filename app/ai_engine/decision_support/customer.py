"""Customer behavior and segmentation analysis"""

import logging
from typing import Dict, Any, Optional, List
from collections import Counter
from datetime import datetime, timedelta

from .constants import THRESHOLDS, CACHE_TTL
from .utils import mean, get_rfm_segment
from .cache import cached

logger = logging.getLogger(__name__)


class CustomerAnalyzer:
    """Handles customer behavior analysis and segmentation"""
    
    def __init__(self, parent):
        self.parent = parent
        self.api = parent.api
        self.recommender = parent.recommender
    
    @cached("customer_behavior")
    def analyze_customer_behavior(self, customer_name: str) -> Dict[str, Any]:
        """Deep dive into a customer's purchasing patterns."""
        
        try:
            customers = self.api.get_customers(search=customer_name, limit=1)
            if not customers:
                return {
                    "error": f"Customer '{customer_name}' not found",
                    "message": "Please check the spelling or try a different customer name",
                    "suggestions": ["List all customers", "Search by partial name"]
                }

            customer = customers[0]
            orders = self.api.get_customer_orders(
                customer_name=customer.get("CardName"), limit=100
            )

            analysis = {
                "customer": {
                    "name": customer.get("CardName"),
                    "code": customer.get("CardCode"),
                    "since": customer.get("CreateDate", "Unknown"),
                    "city": customer.get("City", "Unknown"),
                    "phone": customer.get("Phone1", "Unknown"),
                    "email": customer.get("EmailAddress", "Unknown"),
                },
                "purchase_patterns": {},
                "recommendations": [],
                "upsell_opportunities": [],
                "risk_factors": [],
                "rfm_score": {},
                "next_best_actions": [],
            }

            if not orders:
                analysis["risk_factors"].append("No order history found")
                analysis["recommendations"].append("Send welcome offer and product catalog")
                analysis["next_best_actions"] = [
                    {"action": "Send introductory email", "priority": "HIGH"},
                    {"action": "Offer first-purchase discount", "priority": "HIGH"},
                ]
                return analysis

            # Process orders
            dates = []
            amounts = []
            items_bought = Counter()
            categories = Counter()

            for order in orders:
                date_str = order.get("DocDate") or order.get("doc_date", "")
                if date_str:
                    dates.append(date_str[:10])

                amount = float(order.get("DocTotal") or order.get("doc_total") or 0)
                amounts.append(amount)

                lines = order.get("DocumentLines") or order.get("document_lines") or []
                for line in lines:
                    code = line.get("ItemCode")
                    if code:
                        items_bought[code] += 1
                        
                        item_details = self.api.get_items(search=code, limit=1)
                        if item_details and len(item_details) > 0:
                            category = item_details[0].get("item_group", {}).get("ItmsGrpNam", "Unknown")
                            categories[category] += 1

            # Parse dates
            date_objs = []
            for d in dates:
                try:
                    date_objs.append(datetime.strptime(d, "%Y-%m-%d"))
                except ValueError:
                    pass

            date_objs.sort()

            total_orders = len(orders)
            total_spent = sum(amounts)
            avg_order = total_spent / total_orders if total_orders > 0 else 0
            
            if len(date_objs) > 1:
                intervals = [(date_objs[i+1] - date_objs[i]).days for i in range(len(date_objs)-1)]
                avg_interval = mean(intervals)
                purchase_frequency = 30 / avg_interval if avg_interval > 0 else 0
            else:
                avg_interval = 0
                purchase_frequency = 0

            if date_objs:
                days_since_last = (datetime.now() - date_objs[-1]).days
                is_active = days_since_last < 30
                is_churn_risk = days_since_last > THRESHOLDS["churn_risk_days"]
            else:
                days_since_last = 999
                is_active = False
                is_churn_risk = True

            # RFM scoring
            recency_score = self._calculate_recency_score(days_since_last)
            frequency_score = self._calculate_frequency_score(purchase_frequency)
            monetary_score = self._calculate_monetary_score(avg_order)
            rfm_total = recency_score + frequency_score + monetary_score

            analysis["purchase_patterns"] = {
                "total_orders": total_orders,
                "total_spent": round(total_spent, 2),
                "avg_order_value": round(avg_order, 2),
                "purchase_frequency": round(purchase_frequency, 1),
                "avg_days_between_orders": round(avg_interval, 1) if avg_interval else "N/A",
                "estimated_monthly_spend": round(purchase_frequency * avg_order, 2) if purchase_frequency else 0,
                "last_purchase_days_ago": days_since_last,
                "is_active": is_active,
                "top_items": [
                    {"code": code, "count": count}
                    for code, count in items_bought.most_common(5)
                ],
                "top_categories": [
                    {"category": cat, "count": count}
                    for cat, count in categories.most_common(3)
                ],
            }

            analysis["rfm_score"] = {
                "recency": recency_score,
                "frequency": frequency_score,
                "monetary": monetary_score,
                "total": rfm_total,
                "segment": get_rfm_segment(rfm_total),
            }

            if is_churn_risk:
                analysis["risk_factors"].append(
                    f"⚠️ Churn Risk: No purchase in {days_since_last} days"
                )
                analysis["recommendations"].append(
                    "Send re-engagement offer with special discount"
                )
                analysis["next_best_actions"].append({
                    "action": "Send re-engagement email with 15% discount",
                    "priority": "HIGH"
                })

            return analysis
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in analyze_customer_behavior: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Customer analysis failed: {str(e)}"
            }
    
    @cached("customer_segmentation")
    async def find_customers_by_item(self, item_name: str, limit: int = 10) -> Dict[str, Any]:
        """Find customers who would buy or have bought a specific item."""
        logger.info(f"🎯 Finding customers for item: {item_name}")
        
        try:
            # First, get the item code
            items = self.api.get_items(search=item_name, limit=5)
            if not items:
                return {
                    "error": True,
                    "message": f"No item found matching '{item_name}'",
                    "suggestions": ["Check spelling", "Try a different product name"]
                }
            
            # Find the best matching item
            matched_item = items[0]
            item_code = matched_item.get("ItemCode")
            item_full_name = matched_item.get("ItemName")
            
            logger.info(f"🎯 Matched item: {item_full_name} ({item_code})")
            
            # Get customers from recommendation service
            customers = []
            if self.recommender:
                try:
                    customers = self.recommender.get_customers_for_item(
                        item_code=item_code,
                        limit=limit
                    )
                    logger.info(f"Found {len(customers)} customers from recommendation service")
                except Exception as e:
                    logger.warning(f"Recommendation service failed: {e}")
            
            if not customers:
                customers = await self._find_customers_from_orders(item_code, limit)
            
            if not customers:
                return {
                    "item_name": item_full_name,
                    "item_code": item_code,
                    "customers_found": 0,
                    "customers": [],
                    "message": f"No customers found for '{item_full_name}'",
                }
            
            # Add summary statistics
            total_purchase_volume = sum(c.get("PurchaseQuantity", 0) for c in customers)
            
            result = {
                "item_name": item_full_name,
                "item_code": item_code,
                "customers_found": len(customers),
                "customers": customers[:limit],
                "summary": {
                    "total_customers": len(customers),
                    "total_purchase_volume": round(total_purchase_volume, 0),
                    "average_purchase_volume": round(total_purchase_volume / len(customers), 1) if customers else 0,
                    "top_customers": [
                        {"name": c.get("CardName"), "quantity": c.get("PurchaseQuantity", 0)}
                        for c in customers[:3]
                    ]
                },
                "timestamp": datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in find_customers_by_item: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Failed to find customers for {item_name}: {str(e)}"
            }
    
    async def _find_customers_from_orders(self, item_code: str, limit: int = 10) -> List[Dict]:
        """Fallback method to find customers from order history."""
        customers_with_purchases = []
        
        try:
            all_customers = self.api.get_all_customers(limit=500)
            
            for customer in all_customers[:100]:
                customer_code = customer.get("CardCode")
                if not customer_code:
                    continue
                
                try:
                    orders_result = self.api.get_orders(customer_code=customer_code, limit=20)
                    orders = orders_result if isinstance(orders_result, list) else []
                    
                    total_quantity = 0
                    for order in orders:
                        lines = order.get("DocumentLines", [])
                        for line in lines:
                            if line.get("ItemCode") == item_code:
                                total_quantity += float(line.get("Quantity", 0))
                    
                    if total_quantity > 0:
                        customers_with_purchases.append({
                            "CardCode": customer_code,
                            "CardName": customer.get("CardName"),
                            "PurchaseQuantity": total_quantity,
                            "Source": "order_history",
                            "RecommendationReason": "✓ Previous buyer of this product"
                        })
                        
                        if len(customers_with_purchases) >= limit:
                            break
                            
                except Exception:
                    continue
                    
        except Exception as e:
            logger.error(f"Error in _find_customers_from_orders: {e}")
        
        return customers_with_purchases
    
    def _calculate_recency_score(self, days_since_last: int) -> int:
        """Calculate recency score (5 = best)."""
        if days_since_last <= 7:
            return 5
        elif days_since_last <= 30:
            return 4
        elif days_since_last <= 60:
            return 3
        elif days_since_last <= 90:
            return 2
        else:
            return 1
    
    def _calculate_frequency_score(self, purchase_frequency: float) -> int:
        """Calculate frequency score (5 = best)."""
        if purchase_frequency >= 4:
            return 5
        elif purchase_frequency >= 2:
            return 4
        elif purchase_frequency >= 1:
            return 3
        elif purchase_frequency >= 0.5:
            return 2
        else:
            return 1
    
    def _calculate_monetary_score(self, avg_order: float) -> int:
        """Calculate monetary score (5 = best)."""
        if avg_order >= 100000:
            return 5
        elif avg_order >= 50000:
            return 4
        elif avg_order >= 25000:
            return 3
        elif avg_order >= 10000:
            return 2
        else:
            return 1