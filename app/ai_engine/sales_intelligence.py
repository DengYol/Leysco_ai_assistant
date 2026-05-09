"""
app/ai_engine/sales_intelligence.py
====================================
Sales Intelligence Engine - Identifies revenue opportunities
Proactively detects churn risk, upsell opportunities, cross-sell potential,
reorder patterns, and seasonal opportunities.

This is the CORE of the sales-focused AI.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict
import asyncio

from app.services.leysco_api_service import LeyscoAPIService
from app.services.pricing_service import PricingService

logger = logging.getLogger(__name__)


@dataclass
class SalesOpportunity:
    """Data class for a sales opportunity"""
    type: str  # CHURN_RISK, UPSELL, CROSS_SELL, REORDER, SEASONAL, LOW_STOCK, PRICE_DROP
    customer_code: Optional[str]
    customer_name: Optional[str]
    item_code: Optional[str]
    item_name: Optional[str]
    severity: str  # HIGH, MEDIUM, LOW
    score: int  # 0-100, higher = more urgent
    potential_value: float  # Estimated revenue potential in KES
    days_since: Optional[int]
    current_quantity: Optional[float]
    target_quantity: Optional[float]
    typical_quantity: Optional[float]
    stock_level: Optional[float]
    season: Optional[str]
    action: str  # Action to take
    recommendation: str  # Human-readable recommendation
    message_en: str  # English message for user
    message_sw: str  # Swahili message for user
    data: Dict[str, Any]  # Raw data for reference


class SalesIntelligence:
    """
    Sales-focused AI that proactively identifies opportunities.
    This is the brain of the sales assistant.
    """
    
    def __init__(self, api_service: LeyscoAPIService, pricing_service: PricingService):
        self.api = api_service
        self.pricing = pricing_service
        self._cache = {}  # Simple cache for computed results
        
        # Configuration thresholds (adjust based on Leysco's data)
        self.CHURN_DAYS_MULTIPLIER = 2.0  # 2x average gap = churn risk
        self.CHURN_SCORE_HIGH = 80
        self.CHURN_SCORE_MEDIUM = 60
        
        self.UPSELL_THRESHOLD = 50  # Units - suggest bulk if buying less
        self.UPSELL_TARGET = 100  # Target bulk quantity
        
        self.LOW_STOCK_THRESHOLD = 50  # Units - alert if below
        self.REORDER_SAFETY_STOCK = 100  # Recommended reorder quantity
        
        # Seasonal patterns (customize for Leysco's business)
        self.SEASONAL_PATTERNS = {
            1: {  # January
                "keywords": ["new year", "resolution", "fresh start"],
                "discount": 5,
                "message_en": "New Year, New Savings! Start the year right",
                "message_sw": "Mwaka Mpya, Akiba Mpya! Anza mwaka vizuri"
            },
            2: {  # February
                "keywords": ["valentine", "love", "gift"],
                "discount": 10,
                "message_en": "Spread the love with special Valentine offers",
                "message_sw": "Engeza upendo kwa ofa maalum za Valentines"
            },
            3: {  # March - Planting season
                "keywords": ["seed", "fertilizer", "plant", "sowing", "crop"],
                "discount": 15,
                "message_en": "Planting Season! Stock up on seeds and fertilizer",
                "message_sw": "Msimu wa Kupanda! Nunua mbegu na mbolea"
            },
            4: {  # April
                "keywords": ["rain", "water", "irrigation"],
                "discount": 10,
                "message_en": "Prepare for the rains with irrigation solutions",
                "message_sw": "Jiandae kwa mvua na suluhisho la umwagiliaji"
            },
            5: {  # May
                "keywords": ["growth", "pest", "weed"],
                "discount": 10,
                "message_en": "Protect your crops from pests and weeds",
                "message_sw": "Linda mazao yako dhidi ya wadudu na magugu"
            },
            6: {  # June
                "keywords": ["pesticide", "herbicide", "fungicide"],
                "discount": 15,
                "message_en": "Peak growing season! Pest control solutions",
                "message_sw": "Msimu wa ukuaji! Suluhisho za kudhibiti wadudu"
            },
            7: {  # July
                "keywords": ["mid year", "sale", "clearance"],
                "discount": 20,
                "message_en": "Mid-Year Clearance! Up to 20% off",
                "message_sw": "Uuzaji wa Katikati ya Mwaka! Punguzo hadi 20%"
            },
            8: {  # August
                "keywords": ["pre harvest", "nutrition"],
                "discount": 10,
                "message_en": "Pre-harvest nutrition for better yields",
                "message_sw": "Lishe kabla ya mavuno kwa mazao bora"
            },
            9: {  # September
                "keywords": ["harvest", "ready", "ripe"],
                "discount": 10,
                "message_en": "Harvest season! Harvesting equipment on sale",
                "message_sw": "Msimu wa Mavuno! Vifaa vya kuvuna kwa bei nafuu"
            },
            10: {  # October
                "keywords": ["storage", "silo", "warehouse"],
                "discount": 15,
                "message_en": "Store your harvest safely with our storage solutions",
                "message_sw": "Hifadhi mavuno yako kwa usalama na suluhisho zetu"
            },
            11: {  # November
                "keywords": ["black friday", "cyber", "deal"],
                "discount": 25,
                "message_en": "Black Friday Deals! Biggest discounts of the year",
                "message_sw": "Ofa za Black Friday! Punguzo kubwa zaidi mwaka"
            },
            12: {  # December
                "keywords": ["christmas", "holiday", "gift", "festive"],
                "discount": 15,
                "message_en": "Holiday Specials! Christmas promotions now",
                "message_sw": "Ofa za Sikukuu! Promo za Krismasi sasa"
            }
        }
    
    async def identify_opportunities(self, limit: int = 20) -> Dict[str, Any]:
        """
        Scan for sales opportunities across multiple dimensions.
        Returns ranked opportunities with actionable recommendations.
        """
        start_time = datetime.now()
        
        opportunities = []
        
        # Run all detectors in parallel for performance
        tasks = [
            self._detect_churn_risk(),
            self._detect_upsell_opportunities(),
            self._detect_cross_sell_opportunities(),
            self._detect_reorder_opportunities(),
            self._detect_seasonal_opportunities(),
            self._detect_low_stock_opportunities(),
        ]
        
        results = await asyncio.gather(*tasks)
        
        for result in results:
            opportunities.extend(result)
        
        # Rank by score (higher = more urgent/valuable)
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        # Calculate total potential value
        total_potential = sum(o.potential_value for o in opportunities)
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(f"📊 Sales Intelligence: Found {len(opportunities)} opportunities "
                   f"worth KES {total_potential:,.2f} in {processing_time:.0f}ms")
        
        return {
            "total_opportunities": len(opportunities),
            "total_potential_value": total_potential,
            "high_priority_count": len([o for o in opportunities if o.severity == "HIGH"]),
            "opportunities": [asdict(o) for o in opportunities[:limit]],
            "processing_time_ms": processing_time
        }
    
    async def _detect_churn_risk(self) -> List[SalesOpportunity]:
        """Find customers at risk of leaving."""
        opportunities = []
        
        try:
            customers = self.api.get_customers(limit=200)
            
            if not customers:
                logger.warning("No customers found for churn detection")
                return []
            
            for customer in customers:
                customer_code = customer.get('CardCode')
                customer_name = customer.get('CardName', 'Unknown')
                
                # Skip customers with no email/phone (likely test data)
                if not customer_code:
                    continue
                
                # Get order history
                orders = self.api.get_customer_orders(
                    customer_code=customer_code, 
                    limit=50
                )
                
                if not orders:
                    # Customer with no orders - lead not converted
                    opportunities.append(SalesOpportunity(
                        type="LEAD_NOT_CONVERTED",
                        customer_code=customer_code,
                        customer_name=customer_name,
                        item_code=None,
                        item_name=None,
                        severity="HIGH",
                        score=85,
                        potential_value=50000,
                        days_since=None,
                        current_quantity=None,
                        target_quantity=None,
                        typical_quantity=None,
                        stock_level=None,
                        season=None,
                        action="Convert lead to customer",
                        recommendation=f"{customer_name} has never placed an order. Send a welcome offer.",
                        message_en=f"🎯 **Lead Opportunity:** {customer_name} hasn't ordered yet. Send a 15% welcome discount!",
                        message_sw=f"🎯 **Fursa ya Mteja:** {customer_name} hajaagiza bado. Tuma punguzo la 15% la kukaribisha!",
                        data={"customer": customer, "order_count": 0}
                    ))
                    continue
                
                # Calculate churn risk based on recency and frequency
                valid_dates = []
                order_dates = []
                order_values = []
                
                for order in orders:
                    doc_date = order.get('DocDate', '')
                    doc_total = order.get('DocTotal', 0)
                    
                    if doc_date:
                        try:
                            date_obj = datetime.strptime(doc_date, "%Y-%m-%d")
                            valid_dates.append(date_obj)
                            order_dates.append(date_obj)
                            order_values.append(float(doc_total))
                        except:
                            pass
                
                if not valid_dates:
                    continue
                
                last_date = max(valid_dates)
                days_since = (datetime.now() - last_date).days
                
                # Calculate average gap between orders
                if len(order_dates) >= 2:
                    sorted_dates = sorted(order_dates, reverse=True)
                    gaps = [(sorted_dates[i-1] - sorted_dates[i]).days 
                           for i in range(1, len(sorted_dates))]
                    avg_gap = sum(gaps) / len(gaps) if gaps else 30
                    
                    # If days since last order > threshold * average gap, churn risk
                    if days_since > avg_gap * self.CHURN_DAYS_MULTIPLIER:
                        risk_score = min(100, int((days_since / avg_gap) * 25))
                        
                        if risk_score >= self.CHURN_SCORE_MEDIUM:
                            avg_order_value = sum(order_values) / len(order_values) if order_values else 10000
                            severity = "HIGH" if risk_score >= self.CHURN_SCORE_HIGH else "MEDIUM"
                            
                            discount = 10 if risk_score >= 80 else 5
                            
                            opportunities.append(SalesOpportunity(
                                type="CHURN_RISK",
                                customer_code=customer_code,
                                customer_name=customer_name,
                                item_code=None,
                                item_name=None,
                                severity=severity,
                                score=risk_score,
                                potential_value=avg_order_value,
                                days_since=days_since,
                                current_quantity=None,
                                target_quantity=None,
                                typical_quantity=None,
                                stock_level=None,
                                season=None,
                                action="Win back customer",
                                recommendation=f"{customer_name} hasn't ordered in {days_since} days (normally every {avg_gap:.0f} days). Offer {discount}% discount.",
                                message_en=f"⚠️ **Churn Risk:** {customer_name} hasn't ordered in {days_since} days. Normally every {avg_gap:.0f} days. Offer {discount}% win-back discount!",
                                message_sw=f"⚠️ **Hatari ya Kuondoka:** {customer_name} hajaagiza kwa siku {days_since}. Kawaida kila siku {avg_gap:.0f}. Toa punguzo la {discount}% kuwarudisha!",
                                data={
                                    "customer": customer,
                                    "days_since": days_since,
                                    "avg_gap": avg_gap,
                                    "order_count": len(orders),
                                    "risk_score": risk_score
                                }
                            ))
            
            logger.info(f"✅ Detected {len(opportunities)} churn risk opportunities")
            
        except Exception as e:
            logger.error(f"Error detecting churn risk: {e}", exc_info=True)
        
        return opportunities
    
    async def _detect_upsell_opportunities(self) -> List[SalesOpportunity]:
        """Find opportunities to sell more to existing customers."""
        opportunities = []
        
        try:
            # Get top-selling items
            top_items = self.api.get_top_selling_items(limit=20)
            
            if not top_items:
                logger.warning("No top items found for upsell detection")
                return []
            
            for item in top_items[:10]:
                item_code = item.get('ItemCode')
                item_name = item.get('ItemName', 'Unknown')
                
                if not item_code:
                    continue
                
                # Get all orders to find customer purchase patterns
                orders = self.api.get_customer_orders(limit=500)
                
                # Track customer purchases for this item
                customer_purchases = defaultdict(lambda: {
                    'name': '',
                    'total_quantity': 0,
                    'avg_quantity': 0,
                    'last_purchase': None,
                    'purchase_count': 0
                })
                
                for order in orders:
                    for line in order.get('Items', []):
                        if line.get('ItemCode') == item_code:
                            cust_code = order.get('CardCode')
                            cust_name = order.get('CardName', 'Unknown')
                            qty = line.get('Quantity', 0)
                            
                            customer_purchases[cust_code]['name'] = cust_name
                            customer_purchases[cust_code]['total_quantity'] += qty
                            customer_purchases[cust_code]['purchase_count'] += 1
                            
                            # Track last purchase date
                            doc_date = order.get('DocDate', '')
                            if doc_date and (not customer_purchases[cust_code]['last_purchase'] or 
                                           doc_date > customer_purchases[cust_code]['last_purchase']):
                                customer_purchases[cust_code]['last_purchase'] = doc_date
                
                # Calculate average quantities
                for cust_code, data in customer_purchases.items():
                    if data['purchase_count'] > 0:
                        data['avg_quantity'] = data['total_quantity'] / data['purchase_count']
                
                # Identify upsell opportunities
                for cust_code, data in customer_purchases.items():
                    if data['avg_quantity'] < self.UPSELL_THRESHOLD and data['avg_quantity'] > 0:
                        potential_increase = self.UPSELL_TARGET - data['avg_quantity']
                        potential_value = potential_increase * 1000  # Estimate price per unit
                        
                        opportunities.append(SalesOpportunity(
                            type="UPSELL",
                            customer_code=cust_code,
                            customer_name=data['name'],
                            item_code=item_code,
                            item_name=item_name,
                            severity="MEDIUM",
                            score=70,
                            potential_value=potential_value,
                            days_since=None,
                            current_quantity=data['avg_quantity'],
                            target_quantity=self.UPSELL_TARGET,
                            typical_quantity=None,
                            stock_level=None,
                            season=None,
                            action="Suggest bulk purchase",
                            recommendation=f"{data['name']} buys {data['avg_quantity']:.0f} units of {item_name}. Suggest bulk purchase of {self.UPSELL_TARGET} units for 10% discount.",
                            message_en=f"📈 **Upsell Opportunity:** {data['name']} buys {data['avg_quantity']:.0f} units of {item_name}. Suggest bulk purchase ({self.UPSELL_TARGET} units) for 10% discount!",
                            message_sw=f"📈 **Fursa ya Kuuza Zaidi:** {data['name']} ananunua vitengo {data['avg_quantity']:.0f} vya {item_name}. Pendekeza ununuzi wa wingi (vitengo {self.UPSELL_TARGET}) kwa punguzo la 10%!",
                            data={
                                "customer_code": cust_code,
                                "item_code": item_code,
                                "current_avg_quantity": data['avg_quantity'],
                                "target_quantity": self.UPSELL_TARGET,
                                "purchase_count": data['purchase_count']
                            }
                        ))
            
            logger.info(f"✅ Detected {len(opportunities)} upsell opportunities")
            
        except Exception as e:
            logger.error(f"Error detecting upsell opportunities: {e}", exc_info=True)
        
        return opportunities
    
    async def _detect_cross_sell_opportunities(self) -> List[SalesOpportunity]:
        """Find complementary products to suggest."""
        opportunities = []
        
        try:
            # Get items that have cross-sell data
            items = self.api.get_items(limit=50)
            
            for item in items[:20]:
                item_code = item.get('ItemCode')
                item_name = item.get('ItemName', 'Unknown')
                
                if not item_code:
                    continue
                
                # Get cross-sell recommendations from pricing service
                try:
                    cross_sell = self.pricing.get_cross_sell_recommendations(item_code)
                except Exception as e:
                    logger.debug(f"Could not get cross-sell for {item_code}: {e}")
                    continue
                
                if cross_sell and cross_sell.get('recommendations'):
                    rec = cross_sell['recommendations'][0]
                    rec_item_name = rec.get('ItemName', 'another product')
                    confidence = rec.get('confidence', 70)
                    
                    opportunities.append(SalesOpportunity(
                        type="CROSS_SELL",
                        customer_code=None,  # General recommendation
                        customer_name=None,
                        item_code=item_code,
                        item_name=item_name,
                        severity="MEDIUM",
                        score=confidence,
                        potential_value=cross_sell.get('potential_value', 2000),
                        days_since=None,
                        current_quantity=None,
                        target_quantity=None,
                        typical_quantity=None,
                        stock_level=None,
                        season=None,
                        action="Suggest bundle",
                        recommendation=f"Customers who buy {item_name} also buy {rec_item_name}. Offer bundle discount.",
                        message_en=f"🛒 **Cross-sell Opportunity:** Customers who buy {item_name} also buy {rec_item_name}. Bundle them for 10% off!",
                        message_sw=f"🛒 **Fursa ya Kuuza Pamoja:** Wateja wanaonunua {item_name} pia hununua {rec_item_name}. Fungasha pamoja kwa punguzo la 10%!",
                        data={
                            "item_code": item_code,
                            "item_name": item_name,
                            "recommendations": cross_sell['recommendations'][:3],
                            "confidence": confidence
                        }
                    ))
            
            logger.info(f"✅ Detected {len(opportunities)} cross-sell opportunities")
            
        except Exception as e:
            logger.error(f"Error detecting cross-sell opportunities: {e}", exc_info=True)
        
        return opportunities
    
    async def _detect_reorder_opportunities(self) -> List[SalesOpportunity]:
        """Find customers due for reorder based on historical patterns."""
        opportunities = []
        
        try:
            customers = self.api.get_customers(limit=100)
            
            for customer in customers:
                customer_code = customer.get('CardCode')
                customer_name = customer.get('CardName', 'Unknown')
                
                if not customer_code:
                    continue
                
                orders = self.api.get_customer_orders(customer_code=customer_code, limit=30)
                
                if len(orders) < 2:
                    continue
                
                # Analyze reorder patterns for each item
                item_patterns = defaultdict(lambda: {
                    'name': '',
                    'quantities': [],
                    'last_order': None,
                    'avg_interval': None
                })
                
                order_dates = []
                
                for order in orders:
                    doc_date = order.get('DocDate', '')
                    if doc_date:
                        try:
                            order_dates.append(datetime.strptime(doc_date, "%Y-%m-%d"))
                        except:
                            pass
                    
                    for item in order.get('Items', []):
                        item_code = item.get('ItemCode')
                        if item_code:
                            item_patterns[item_code]['name'] = item.get('ItemName', 'Unknown')
                            item_patterns[item_code]['quantities'].append(item.get('Quantity', 0))
                
                # Sort dates to calculate intervals
                if len(order_dates) >= 2:
                    sorted_dates = sorted(order_dates, reverse=True)
                    intervals = [(sorted_dates[i-1] - sorted_dates[i]).days 
                               for i in range(1, len(sorted_dates))]
                    avg_interval = sum(intervals) / len(intervals) if intervals else 30
                    
                    # Check if due for reorder based on last order date
                    last_order_date = max(order_dates) if order_dates else None
                    if last_order_date:
                        days_since = (datetime.now() - last_order_date).days
                        
                        # If approaching average interval, suggest reorder
                        if days_since >= avg_interval * 0.8:  # 80% of average interval
                            for item_code, pattern in item_patterns.items():
                                if pattern['quantities']:
                                    avg_qty = sum(pattern['quantities']) / len(pattern['quantities'])
                                    
                                    opportunities.append(SalesOpportunity(
                                        type="REORDER",
                                        customer_code=customer_code,
                                        customer_name=customer_name,
                                        item_code=item_code,
                                        item_name=pattern['name'],
                                        severity="MEDIUM",
                                        score=65,
                                        potential_value=avg_qty * 1000,  # Estimate
                                        days_since=days_since,
                                        current_quantity=None,
                                        target_quantity=None,
                                        typical_quantity=avg_qty,
                                        stock_level=None,
                                        season=None,
                                        action="Suggest reorder",
                                        recommendation=f"{customer_name} typically orders {avg_qty:.0f} units of {pattern['name']}. They may be due for reorder.",
                                        message_en=f"🔄 **Reorder Opportunity:** {customer_name} typically orders {avg_qty:.0f} units of {pattern['name']}. Would you like to prepare a quotation?",
                                        message_sw=f"🔄 **Fursa ya Kuagiza Tena:** {customer_name} kwa kawaida huagiza vitengo {avg_qty:.0f} vya {pattern['name']}. Je, ungependa kuandaa nukuu?",
                                        data={
                                            "customer_code": customer_code,
                                            "item_code": item_code,
                                            "typical_quantity": avg_qty,
                                            "days_since_last_order": days_since,
                                            "avg_interval_days": avg_interval
                                        }
                                    ))
            
            logger.info(f"✅ Detected {len(opportunities)} reorder opportunities")
            
        except Exception as e:
            logger.error(f"Error detecting reorder opportunities: {e}", exc_info=True)
        
        return opportunities
    
    async def _detect_seasonal_opportunities(self) -> List[SalesOpportunity]:
        """Find seasonal sales opportunities."""
        opportunities = []
        
        try:
            current_month = datetime.now().month
            season_config = self.SEASONAL_PATTERNS.get(current_month)
            
            if not season_config:
                return []
            
            # Get items that match seasonal keywords
            items = self.api.get_items(limit=200)
            
            for item in items:
                item_name = item.get('ItemName', '').lower()
                item_code = item.get('ItemCode')
                
                # Check if item matches seasonal keywords
                for keyword in season_config['keywords']:
                    if keyword in item_name:
                        # Check stock level
                        inventory = self.api.get_inventory_report(search=item_code, limit=1)
                        stock = inventory[0].get('CurrentOnHand', 0) if inventory else 0
                        
                        opportunities.append(SalesOpportunity(
                            type="SEASONAL",
                            customer_code=None,
                            customer_name=None,
                            item_code=item_code,
                            item_name=item.get('ItemName'),
                            severity="HIGH",
                            score=85,
                            potential_value=50000,
                            days_since=None,
                            current_quantity=None,
                            target_quantity=None,
                            typical_quantity=None,
                            stock_level=stock,
                            season=datetime.now().strftime("%B"),
                            action="Run seasonal promotion",
                            recommendation=f"{item.get('ItemName')} is in high demand this season. Run a {season_config['discount']}% promotion.",
                            message_en=f"🌱 **Seasonal Opportunity:** {item.get('ItemName')} is in high demand for {datetime.now().strftime('%B')}. Run a {season_config['discount']}% promotion!",
                            message_sw=f"🌱 **Fursa ya Msimu:** {item.get('ItemName')} inahitajika sana mwezi wa {datetime.now().strftime('%B')}. Fanya promo ya {season_config['discount']}%!",
                            data={
                                "item_code": item_code,
                                "item_name": item.get('ItemName'),
                                "season": datetime.now().strftime("%B"),
                                "discount": season_config['discount'],
                                "current_stock": stock
                            }
                        ))
                        break  # Only add once per item
            
            logger.info(f"✅ Detected {len(opportunities)} seasonal opportunities")
            
        except Exception as e:
            logger.error(f"Error detecting seasonal opportunities: {e}", exc_info=True)
        
        return opportunities
    
    async def _detect_low_stock_opportunities(self) -> List[SalesOpportunity]:
        """Find items with low stock that need reordering."""
        opportunities = []
        
        try:
            inventory = self.api.get_inventory_report(limit=500)
            
            for item in inventory:
                item_code = item.get('ItemCode')
                item_name = item.get('ItemName', 'Unknown')
                on_hand = float(item.get('CurrentOnHand', 0))
                committed = float(item.get('CurrentIsCommited', 0))
                
                # Calculate available stock
                available = on_hand - committed
                
                if available < self.LOW_STOCK_THRESHOLD and available > 0:
                    # Check if this is a popular item
                    top_items = self.api.get_top_selling_items(limit=20)
                    is_popular = any(t.get('ItemCode') == item_code for t in top_items)
                    
                    score = 80 if is_popular else 60
                    severity = "HIGH" if is_popular else "MEDIUM"
                    reorder_qty = self.REORDER_SAFETY_STOCK * 2 if is_popular else self.REORDER_SAFETY_STOCK
                    
                    opportunities.append(SalesOpportunity(
                        type="LOW_STOCK",
                        customer_code=None,
                        customer_name=None,
                        item_code=item_code,
                        item_name=item_name,
                        severity=severity,
                        score=score,
                        potential_value=reorder_qty * 1000,  # Estimate
                        days_since=None,
                        current_quantity=None,
                        target_quantity=None,
                        typical_quantity=None,
                        stock_level=available,
                        season=None,
                        action="Reorder stock",
                        recommendation=f"{item_name} stock is low ({available:.0f} units left). Reorder {reorder_qty:.0f} units.",
                        message_en=f"📦 **Low Stock Alert:** {item_name} has only {available:.0f} units left. Reorder {reorder_qty:.0f} units now!",
                        message_sw=f"📦 **Tahadhari ya Hisa Chache:** {item_name} imesalia vitengo {available:.0f} tu. Agiza vitengo {reorder_qty:.0f} sasa!",
                        data={
                            "item_code": item_code,
                            "item_name": item_name,
                            "current_stock": available,
                            "committed": committed,
                            "on_hand": on_hand,
                            "recommended_reorder": reorder_qty,
                            "is_popular": is_popular
                        }
                    ))
            
            logger.info(f"✅ Detected {len(opportunities)} low stock opportunities")
            
        except Exception as e:
            logger.error(f"Error detecting low stock opportunities: {e}", exc_info=True)
        
        return opportunities
    
    def clear_cache(self):
        """Clear the intelligence cache."""
        self._cache.clear()
        logger.info("Sales intelligence cache cleared")


# =========================================================
# Factory function to create SalesIntelligence instance
# =========================================================

def create_sales_intelligence(
    api_service: LeyscoAPIService,
    pricing_service: PricingService
) -> SalesIntelligence:
    """Create a SalesIntelligence instance with the given services."""
    return SalesIntelligence(api_service, pricing_service)