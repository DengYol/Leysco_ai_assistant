"""Delivery tracking intent handlers"""

from typing import Dict, Any
import logging
from ..base_handler import BaseHandler

logger = logging.getLogger(__name__)


class DeliveryHandler(BaseHandler):
    """Handler for delivery related intents"""
    
    def get_outstanding_deliveries(self, customer_name: str, limit: int, language: str) -> dict:
        """Get outstanding deliveries for a customer."""
        if not customer_name:
            return self._missing("a customer name", language)
        
        customer, search_name = self.router._resolve_customer(customer_name)
        if not customer:
            return self._not_found("Customer", search_name, language)
        
        deliveries = self.delivery.get_outstanding_deliveries(
            customer_code=customer.get("CardCode"), 
            limit=limit or 10
        )
        
        if not deliveries:
            if language == "sw":
                return {"message": f"Hakuna usafirishaji uliobaki kwa {customer.get('CardName')}.", "data": []}
            return {"message": f"No outstanding deliveries for {customer.get('CardName')}.", "data": []}
        
        if language == "sw":
            text = f"Usafirishaji Uliobaki: {customer.get('CardName')}\n\n"
            for i, d in enumerate(deliveries, 1):
                text += f"{i}. Usafirishaji #{d.get('DocNum')} — Hali: {d.get('Status')} | Tarehe: {d.get('ETA')}\n"
        else:
            text = f"Outstanding Deliveries: {customer.get('CardName')}\n\n"
            for i, d in enumerate(deliveries, 1):
                text += f"{i}. Delivery #{d.get('DocNum')} — Status: {d.get('Status')} | ETA: {d.get('ETA')}\n"
        
        return {"message": text, "data": deliveries}
    
    def track_delivery(self, delivery_number: str, language: str) -> dict:
        """Track a specific delivery."""
        if not delivery_number:
            if language == "sw":
                return {"message": "Tafadhali toa namba ya usafirishaji kwa mfano 'fuatilia 10045'", "data": []}
            return {"message": "Please provide a delivery number to track.", "data": []}
        
        tracking = self.delivery.track_delivery(delivery_number)
        
        if "error" in tracking:
            if language == "sw":
                return {"message": f"Usafirishaji #{delivery_number} haukupatikana.", "data": []}
            return {"message": tracking["error"], "data": []}
        
        if language == "sw":
            text = f"Kufuatilia Usafirishaji #{tracking['DocNum']}\n\n"
            text += f"Hali: {tracking['Status']}\n"
            text += f"Tarehe: {tracking['ETA']}\n"
            text += f"Mteja: {tracking['Customer']}\n\n"
            text += "Ratiba:\n"
            for event in tracking.get('Timeline', []):
                icon = '✅' if event['status'] == 'completed' else '⏳'
                text += f"{icon} {event['event']} - {event['date'][:10]}\n"
        else:
            text = f"Tracking Delivery #{tracking['DocNum']}\n\n"
            text += f"Status: {tracking['Status']}\n"
            text += f"ETA: {tracking['ETA']}\n"
            text += f"Customer: {tracking['Customer']}\n\n"
            text += "Timeline:\n"
            for event in tracking.get('Timeline', []):
                icon = '✅' if event['status'] == 'completed' else '⏳'
                text += f"{icon} {event['event']} - {event['date'][:10]}\n"
        
        return {"message": text, "data": [tracking]}
    
    def get_delivery_history(self, customer_name: str, limit: int, language: str) -> dict:
        """Get delivery history for a customer."""
        if not customer_name:
            return self._missing("a customer name", language)
        
        customer, search_name = self.router._resolve_customer(customer_name)
        if not customer:
            return self._not_found("Customer", search_name, language)
        
        history = self.delivery.get_delivery_history(
            customer_code=customer.get("CardCode"), 
            days=30, 
            limit=limit or 10
        )
        
        if not history:
            if language == "sw":
                return {"message": f"Hakuna historia ya usafirishaji kwa {customer.get('CardName')} katika siku 30 zilizopita.", "data": []}
            return {"message": f"No delivery history for {customer.get('CardName')} in the past 30 days.", "data": []}
        
        if language == "sw":
            text = f"Historia ya Usafirishaji: {customer.get('CardName')} (Siku 30 zilizopita)\n\n"
            for i, d in enumerate(history, 1):
                text += f"{i}. Usafirishaji #{d.get('DocNum')} - {(d.get('DocDate') or '')[:10]} — KES {float(d.get('TotalValue', 0)):,.2f}\n"
        else:
            text = f"Delivery History: {customer.get('CardName')} (Last 30 days)\n\n"
            for i, d in enumerate(history, 1):
                text += f"{i}. Delivery #{d.get('DocNum')} - {(d.get('DocDate') or '')[:10]} — KES {float(d.get('TotalValue', 0)):,.2f}\n"
        
        return {"message": text, "data": history}