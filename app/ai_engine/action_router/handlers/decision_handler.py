"""Decision support intent handlers"""

from typing import Dict, Any
import logging
from ..base_handler import BaseHandler

logger = logging.getLogger(__name__)


class DecisionHandler(BaseHandler):
    """Handler for decision support intents (inventory health, reorder decisions, etc.)"""
    
    def analyze_inventory_health(self, entities: dict, language: str) -> dict:
        """Analyze inventory health with proper conversational formatting."""
        warehouse = entities.get("warehouse") or entities.get("warehouse_name")
        
        # Check cache first (10 minute TTL)
        cache_key = f"inventory_health:{warehouse or 'all'}"
        cached = self.cache.get_simple(cache_key)
        if cached:
            logger.info(f"Using cached inventory health data for {warehouse or 'all'}")
            return cached
        
        try:
            analysis = self.router.decision_support.analyze_inventory_health(warehouse)
            
            if "error" in analysis:
                return {"message": analysis["error"], "data": []}
            
            # IMPORTANT: health_score is at the root level, not in summary
            health_score = analysis.get("health_score", 0)
            summary = analysis.get("summary", {})
            
            # Get counts from summary
            total_items = summary.get("total_items", 0)
            critical_count = summary.get("critical_items_count", 0)
            low_count = summary.get("low_items_count", 0)
            healthy_count = summary.get("healthy_items_count", 0)
            overstock_count = summary.get("overstock_items_count", 0)
            out_of_stock_count = summary.get("out_of_stock_count", 0)
            total_value = summary.get("total_inventory_value", 0)
            
            # Get items from analysis (these are lists)
            critical_items = analysis.get("critical_items", [])
            low_items = analysis.get("risk_items", [])
            overstock_items = analysis.get("overstock_items", [])
            
            # Build conversational response
            if language == "sw":
                # Health score with emoji
                if health_score >= 80:
                    health_emoji = "🟢"
                    health_desc = "Bora"
                elif health_score >= 60:
                    health_emoji = "🟡"
                    health_desc = "Nzuri"
                elif health_score >= 40:
                    health_emoji = "🟠"
                    health_desc = "Wastani"
                else:
                    health_emoji = "🔴"
                    health_desc = "Inahitaji Uangalizi"
                
                text = f"{health_emoji} **Afya ya Hisa: {health_score}/100** ({health_desc})\n\n"
                text += f"📊 **Muhtasari wa Hisa**\n"
                text += f"• Jumla ya Bidhaa: **{total_items:,}**\n"
                text += f"• Thamani Jumla: **KES {total_value:,.2f}**\n\n"
                
                text += f"📦 **Hali ya Hisa:**\n"
                text += f"• ❌ Zimeisha: {out_of_stock_count}\n"
                text += f"• 🔴 Muhimu: {critical_count}\n"
                text += f"• 🟡 Chache: {low_count}\n"
                text += f"• ✅ Nzuri: {healthy_count}\n"
                text += f"• 📦 Zaidi: {overstock_count}\n\n"
                
                # Add critical items if any
                if critical_items:
                    text += f"🔴 **Bidhaa Muhimu Zinazohitaji Kuagizwa Mara Moja**\n"
                    for item in critical_items[:5]:
                        name = item.get('name', 'Unknown')
                        available = item.get('available', 0)
                        text += f"• {name} - Zimesalia: {available:,.0f} tu\n"
                    text += "\n"
                
                # Add low stock items if any
                if low_items:
                    text += f"🟡 **Bidhaa Zenye Hisa Chache**\n"
                    for item in low_items[:5]:
                        name = item.get('name', 'Unknown')
                        available = item.get('available', 0)
                        text += f"• {name} - Zimesalia: {available:,.0f}\n"
                    text += "\n"
                
                # Recommendations
                recommendations = []
                if out_of_stock_count > 0:
                    recommendations.append(f"Agiza bidhaa {out_of_stock_count} zilizoisha mara moja")
                if critical_count > 0:
                    recommendations.append(f"Agiza bidhaa {critical_count} muhimu ndani ya saa 24")
                if low_count > 0:
                    recommendations.append(f"Panga kuagiza bidhaa {low_count} chache wiki hii")
                if overstock_count > 0:
                    recommendations.append(f"Fanya promo kwa bidhaa {overstock_count} zilizozaidi")
                
                if recommendations:
                    text += f"💡 **Mapendekezo:**\n"
                    for rec in recommendations[:3]:
                        text += f"• {rec}\n"
                    text += "\n"
                else:
                    text += f"✅ Hisa zako ziko sawa! Endelea kufuatilia.\n\n"
                
                text += f"💡 **Kidokezo:** Uliza 'onyesha hisa chache' kuona orodha kamili."
                
            else:
                # English version
                if health_score >= 80:
                    health_emoji = "🟢"
                    health_desc = "Excellent"
                elif health_score >= 60:
                    health_emoji = "🟡"
                    health_desc = "Good"
                elif health_score >= 40:
                    health_emoji = "🟠"
                    health_desc = "Fair"
                else:
                    health_emoji = "🔴"
                    health_desc = "Needs Attention"
                
                text = f"{health_emoji} **Inventory Health: {health_score}/100** ({health_desc})\n\n"
                text += f"📊 **Inventory Summary**\n"
                text += f"• Total Items: **{total_items:,}**\n"
                text += f"• Total Value: **KES {total_value:,.2f}**\n\n"
                
                text += f"📦 **Stock Status:**\n"
                text += f"• ❌ Out of Stock: {out_of_stock_count}\n"
                text += f"• 🔴 Critical: {critical_count}\n"
                text += f"• 🟡 Low Stock: {low_count}\n"
                text += f"• ✅ Healthy: {healthy_count}\n"
                text += f"• 📦 Overstock: {overstock_count}\n\n"
                
                # Add critical items
                if critical_items:
                    text += f"🔴 **Critical Items - Order Immediately**\n"
                    for item in critical_items[:5]:
                        name = item.get('name', 'Unknown')
                        available = item.get('available', 0)
                        text += f"• {name} - Only {available:,.0f} left\n"
                    text += "\n"
                
                # Add low stock items
                if low_items:
                    text += f"🟡 **Low Stock Items**\n"
                    for item in low_items[:5]:
                        name = item.get('name', 'Unknown')
                        available = item.get('available', 0)
                        text += f"• {name} - Only {available:,.0f} left\n"
                    text += "\n"
                
                # Recommendations
                recommendations = []
                if out_of_stock_count > 0:
                    recommendations.append(f"Order {out_of_stock_count} out-of-stock items immediately")
                if critical_count > 0:
                    recommendations.append(f"Order {critical_count} critical items within 24 hours")
                if low_count > 0:
                    recommendations.append(f"Schedule orders for {low_count} low stock items this week")
                if overstock_count > 0:
                    recommendations.append(f"Run promotions on {overstock_count} overstocked items")
                
                if recommendations:
                    text += f"💡 **Recommendations:**\n"
                    for rec in recommendations[:3]:
                        text += f"• {rec}\n"
                    text += "\n"
                else:
                    text += f"✅ Your inventory is healthy! Keep monitoring.\n\n"
                
                text += f"💡 **Tip:** Ask 'show low stock items' to see the full list."
            
            result = {"message": text, "data": [analysis]}
            
            # Cache the result (10 minutes)
            self.cache.set_simple(cache_key, result, ttl=600)
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing inventory health: {e}", exc_info=True)
            
            # Return a friendly error message
            if language == "sw":
                return {
                    "message": "⏰ Samahani, uchambuzi wa afya ya hisa unachukua muda mrefu. Tafadhali jaribu tena baadaye.\n\n💡 Unaweza pia kuuliza maswali maalum zaidi kama:\n• 'onyesha hisa chache'\n• 'bidhaa muhimu'\n• 'mapendekezo ya kuagiza'",
                    "data": []
                }
            else:
                return {
                    "message": "⏰ Sorry, the inventory health analysis is taking too long. Please try again in a moment.\n\n💡 You can also ask more specific questions like:\n• 'show low stock items'\n• 'critical stock items'\n• 'reorder recommendations'",
                    "data": []
                }
    
    def get_reorder_decisions(self, entities: dict, language: str) -> dict:
        """Get reorder decisions."""
        item_name = entities.get("item_name")
        
        # Check cache
        cache_key = f"reorder_decisions:{item_name or 'all'}"
        cached = self.cache.get_simple(cache_key)
        if cached:
            logger.info(f"Using cached reorder decisions")
            return cached
        
        decisions = self.router.decision_support.get_reorder_decisions(item_name)
        
        if language == "sw":
            text = "📋 **Maamuzi ya Kuagiza Tena**\n\n"
            if decisions.get("immediate_orders"):
                text += "🔄 **Maagizo ya Haraka Yanahitajika:**\n\n"
                for i, order in enumerate(decisions["immediate_orders"][:5], 1):
                    text += f"{i}. **{order['name']}**\n"
                    text += f"   • Agiza: {order['recommended_qty']:,.0f} vitengo\n"
                    text += f"   • Kadirio la Gharama: KES {order['estimated_cost']:,.0f}\n\n"
            else:
                text += "✅ Hakuna maagizo ya haraka yanayohitajika.\n"
        else:
            text = "📋 **Reorder Decisions**\n\n"
            if decisions.get("immediate_orders"):
                text += "🔄 **Immediate Orders Required:**\n\n"
                for i, order in enumerate(decisions["immediate_orders"][:5], 1):
                    text += f"{i}. **{order['name']}**\n"
                    text += f"   • Order: {order['recommended_qty']:,.0f} units\n"
                    text += f"   • Estimated Cost: KES {order['estimated_cost']:,.0f}\n\n"
            else:
                text += "✅ No immediate reorders needed.\n"
        
        result = {"message": text, "data": [decisions]}
        
        # Cache for 5 minutes
        self.cache.set_simple(cache_key, result, ttl=300)
        
        return result
    
    def analyze_pricing_opportunities(self, entities: dict, language: str) -> dict:
        """Analyze pricing opportunities."""
        customer_name = entities.get("customer_name")
        opportunities = self.router.decision_support.analyze_pricing_opportunities(customer_name)
        
        if language == "sw":
            text = "💰 **Fursa za Bei na Uchambuzi**\n\n"
            sections = [
                ("price_drops", "📉 Kushuka kwa Bei - NUNUA SASA!", "Price Drops - BUY NOW!"),
                ("price_hikes", "📈 Kupanda kwa Bei", "Price Hikes - Consider Alternatives"),
                ("best_value", "⭐ Bidhaa za Thamani Bora", "Best Value Items"),
            ]
        else:
            text = "💰 **Pricing Opportunities & Insights**\n\n"
            sections = [
                ("price_drops", "📉 Price Drops - BUY NOW!", "Price Drops - BUY NOW!"),
                ("price_hikes", "📈 Price Hikes - Consider Alternatives", "Price Hikes - Consider Alternatives"),
                ("best_value", "⭐ Best Value Items", "Best Value Items"),
            ]
        
        has_items = False
        for key, sw_label, en_label in sections:
            items = opportunities.get(key, [])
            if items:
                has_items = True
                label = sw_label if language == "sw" else en_label
                text += f"{label}\n"
                for opp in items[:5]:
                    price = opp.get('current', opp.get('price', 0))
                    text += f"• **{opp['name']}**: KES {price:,.0f}\n"
                text += "\n"
        
        if not has_items:
            if language == "sw":
                text += "Hakuna fursa za bei zilizopatikana kwa sasa.\n\n"
            else:
                text += "No pricing opportunities found at this time.\n\n"
        
        return {"message": text, "data": [opportunities]}
    
    def analyze_customer_behavior(self, customer_name: str, language: str) -> dict:
        """Analyze customer behavior."""
        if not customer_name:
            if language == "sw":
                return {"message": "ℹ️ Tafadhali taja jina la mteja.\n\n💡 Mfano: 'onyesha tabia ya mteja Magomano'", "data": []}
            return {"message": "ℹ️ Please specify a customer name.\n\n💡 Example: 'show customer behavior for Magomano'", "data": []}
        
        analysis = self.router.decision_support.analyze_customer_behavior(customer_name)
        
        if "error" in analysis:
            return {"message": analysis["error"], "data": []}
        
        cname = analysis['customer']['name']
        patterns = analysis.get("purchase_patterns", {})
        
        if language == "sw":
            text = f"👤 **Uchambuzi wa Mteja: {cname}**\n\n"
            if patterns:
                text += "📊 **Mifumo ya Ununuzi**\n"
                text += f"• Jumla ya Oda: {patterns.get('total_orders', 0):,}\n"
                text += f"• Jumla ya Matumizi: KES {patterns.get('total_spent', 0):,.2f}\n"
                text += f"• Wastani wa Oda: KES {patterns.get('avg_order_value', 0):,.2f}\n\n"
        else:
            text = f"👤 **Customer Insights: {cname}**\n\n"
            if patterns:
                text += "📊 **Purchase Patterns**\n"
                text += f"• Total Orders: {patterns.get('total_orders', 0):,}\n"
                text += f"• Total Spent: KES {patterns.get('total_spent', 0):,.2f}\n"
                text += f"• Avg Order Value: KES {patterns.get('avg_order_value', 0):,.2f}\n\n"
        
        sections = [
            ("recommendations", "💡 Mapendekezo", "💡 Recommendations"),
            ("upsell_opportunities", "📈 Fursa za Kuuza Zaidi", "📈 Upsell Opportunities"),
            ("risk_factors", "⚠️ Sababu za Hatari", "⚠️ Risk Factors"),
        ]
        
        for key, sw_label, en_label in sections:
            items = analysis.get(key, [])
            if items:
                label = sw_label if language == "sw" else en_label
                text += f"{label}\n"
                for item in items[:5]:
                    text += f"• {item}\n"
                text += "\n"
        
        return {"message": text, "data": [analysis]}
    
    def forecast_demand(self, item_name: str, days: int, language: str) -> dict:
        """Forecast demand for an item."""
        if not item_name:
            if language == "sw":
                return {"message": "ℹ️ Tafadhali taja jina la bidhaa.\n\n💡 Mfano: 'utabiri wa mahitaji ya vegimax'", "data": []}
            return {"message": "ℹ️ Please specify an item name.\n\n💡 Example: 'forecast demand for vegimax'", "data": []}
        
        forecast = self.router.decision_support.forecast_demand(item_name, days or 30)
        
        if "error" in forecast:
            return {"message": forecast["error"], "data": []}
        
        if language == "sw":
            text = f"📈 **Utabiri wa Mahitaji: {forecast['item_name']}**\n\n"
            text += f"📦 Hisa ya Sasa: {forecast['current_stock']:,.0f} vitengo\n"
            text += f"📊 Wastani wa Kila Siku: {forecast['daily_avg']:,.1f} vitengo\n\n"
            text += f"💡 **Mapendekezo:** {forecast['recommendation']}"
        else:
            text = f"📈 **Demand Forecast: {forecast['item_name']}**\n\n"
            text += f"📦 Current Stock: {forecast['current_stock']:,.0f} units\n"
            text += f"📊 Daily Average: {forecast['daily_avg']:,.1f} units\n\n"
            text += f"💡 **Recommendation:** {forecast['recommendation']}"
        
        return {"message": text, "data": [forecast]}