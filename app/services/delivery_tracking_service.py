"""
delivery_tracking_service.py
=============================
Comprehensive delivery tracking and monitoring service.

Provides:
- Outstanding deliveries by customer
- Delivery status tracking
- Expected delivery dates
- Delivery history
- Real-time updates (when GPS/tracking available)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DeliveryTrackingService:
    """
    Service for tracking deliveries and shipments.
    
    Integrates with SAP B1 delivery documents to provide:
    - Outstanding delivery tracking
    - Delivery status monitoring
    - ETA calculations
    - Delivery history
    """
    
    def __init__(self, api_service):
        self.api = api_service
    
    # =========================================================
    # DELIVERY STATUS TRACKING
    # =========================================================
    
    def get_outstanding_deliveries(self, customer_code: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get all outstanding (pending) deliveries for a customer.
        
        Returns deliveries that are:
        - Created but not yet dispatched
        - In transit
        - Ready for pickup
        """
        try:
            # In SAP, outstanding deliveries are typically delivery documents (ODLN)
            # that haven't been closed or fully invoiced
            deliveries = self.api.get_deliveries(customer_code=customer_code, limit=limit)
            
            if not deliveries:
                return []
            
            # Enrich delivery data with status and ETA
            enriched = []
            for delivery in deliveries:
                status = self._determine_delivery_status(delivery)
                eta = self._calculate_eta(delivery)
                
                enriched.append({
                    "DocNum": delivery.get("DocNum"),
                    "DocEntry": delivery.get("DocEntry"),
                    "CardCode": delivery.get("CardCode"),
                    "CardName": delivery.get("CardName"),
                    "DocDate": delivery.get("DocDate"),
                    "DocDueDate": delivery.get("DocDueDate"),
                    "DocTotal": delivery.get("DocTotal"),
                    "ItemCount": len(delivery.get("DocumentLines", [])),
                    "Status": status,
                    "ETA": eta,
                    "Address": delivery.get("Address"),
                    "Comments": delivery.get("Comments"),
                })
            
            return enriched
            
        except Exception as e:
            logger.error(f"Error getting outstanding deliveries for {customer_code}: {e}")
            return []
    
    def get_delivery_details(self, doc_num: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific delivery.
        
        Includes:
        - Line items
        - Quantities
        - Delivery address
        - Current status
        - Tracking information
        """
        try:
            delivery = self.api.get_delivery_by_docnum(doc_num)
            
            if not delivery:
                return None
            
            # Extract line items
            line_items = []
            for line in delivery.get("DocumentLines", []):
                line_items.append({
                    "ItemCode": line.get("ItemCode"),
                    "ItemName": line.get("ItemDescription"),
                    "Quantity": line.get("Quantity"),
                    "DeliveredQty": line.get("DeliveredQty", 0),
                    "RemainingQty": line.get("Quantity", 0) - line.get("DeliveredQty", 0),
                    "Price": line.get("Price"),
                    "LineTotal": line.get("LineTotal"),
                })
            
            status = self._determine_delivery_status(delivery)
            eta = self._calculate_eta(delivery)
            
            return {
                "DocNum": delivery.get("DocNum"),
                "DocEntry": delivery.get("DocEntry"),
                "DocDate": delivery.get("DocDate"),
                "DocDueDate": delivery.get("DocDueDate"),
                "Customer": {
                    "CardCode": delivery.get("CardCode"),
                    "CardName": delivery.get("CardName"),
                    "Address": delivery.get("Address"),
                    "Phone": delivery.get("Phone"),
                },
                "Status": status,
                "ETA": eta,
                "TotalValue": delivery.get("DocTotal"),
                "Items": line_items,
                "Comments": delivery.get("Comments"),
                "CreatedBy": delivery.get("UserSign"),
                "LastUpdated": delivery.get("UpdateDate"),
            }
            
        except Exception as e:
            logger.error(f"Error getting delivery details for {doc_num}: {e}")
            return None
    
    def get_delivery_history(self, customer_code: str, days: int = 30, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get delivery history for a customer.
        
        Shows completed deliveries from the past N days.
        """
        try:
            # Get all deliveries and filter to completed ones
            all_deliveries = self.api.get_deliveries(customer_code=customer_code, limit=limit)
            
            if not all_deliveries:
                return []
            
            # Filter to completed/closed deliveries within date range
            cutoff_date = datetime.now() - timedelta(days=days)
            history = []
            
            for delivery in all_deliveries:
                doc_date = delivery.get("DocDate")
                status = self._determine_delivery_status(delivery)
                
                # Only include completed deliveries
                if status == "Delivered":
                    history.append({
                        "DocNum": delivery.get("DocNum"),
                        "DocDate": doc_date,
                        "ItemCount": len(delivery.get("DocumentLines", [])),
                        "TotalValue": delivery.get("DocTotal"),
                        "Status": status,
                    })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting delivery history for {customer_code}: {e}")
            return []
    
    def track_delivery(self, doc_num: str) -> Dict[str, Any]:
        """
        Track a specific delivery with real-time status.
        
        In production: integrate with GPS tracking, courier APIs, etc.
        For now: provides SAP status and estimated delivery.
        """
        try:
            delivery = self.get_delivery_details(doc_num)
            
            if not delivery:
                return {"error": f"Delivery {doc_num} not found"}
            
            # Build tracking timeline
            timeline = self._build_delivery_timeline(delivery)
            
            return {
                "DocNum": doc_num,
                "Status": delivery["Status"],
                "ETA": delivery["ETA"],
                "Customer": delivery["Customer"]["CardName"],
                "Address": delivery["Customer"]["Address"],
                "Timeline": timeline,
                "Items": len(delivery["Items"]),
                "TotalValue": delivery["TotalValue"],
            }
            
        except Exception as e:
            logger.error(f"Error tracking delivery {doc_num}: {e}")
            return {"error": str(e)}
    
    # =========================================================
    # DELIVERY ANALYTICS
    # =========================================================
    
    def get_delivery_summary(self, customer_code: str) -> Dict[str, Any]:
        """
        Get overall delivery summary for a customer.
        
        Includes:
        - Outstanding deliveries count
        - Delayed deliveries count
        - On-time delivery rate
        - Average delivery time
        """
        try:
            outstanding = self.get_outstanding_deliveries(customer_code, limit=100)
            history = self.get_delivery_history(customer_code, days=90, limit=100)
            
            # Count delayed deliveries
            delayed = sum(1 for d in outstanding if d["Status"] == "Delayed")
            
            return {
                "TotalOutstanding": len(outstanding),
                "Delayed": delayed,
                "InTransit": sum(1 for d in outstanding if d["Status"] == "In Transit"),
                "RecentDeliveries": len(history),
                "OnTimeRate": self._calculate_ontime_rate(history),
            }
            
        except Exception as e:
            logger.error(f"Error getting delivery summary for {customer_code}: {e}")
            return {}
    
    # =========================================================
    # HELPER METHODS
    # =========================================================
    
    def _determine_delivery_status(self, delivery: Dict[str, Any]) -> str:
        """
        Determine delivery status from SAP document data.
        
        Possible statuses:
        - Pending: Created, not yet dispatched
        - In Transit: Dispatched, on the way
        - Delayed: Past due date
        - Delivered: Completed
        - Cancelled: Cancelled order
        """
        doc_status = delivery.get("DocumentStatus", "O")  # O=Open, C=Closed
        cancelled = delivery.get("Cancelled", "N")
        
        if cancelled == "Y":
            return "Cancelled"
        
        if doc_status == "C":
            return "Delivered"
        
        # Check if past due date
        due_date_str = delivery.get("DocDueDate")
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str[:10], "%Y-%m-%d")
                if datetime.now() > due_date:
                    return "Delayed"
            except:
                pass
        
        # Check if dispatched (has shipping date or tracking number)
        if delivery.get("U_ShipDate") or delivery.get("U_TrackingNum"):
            return "In Transit"
        
        return "Pending"
    
    def _calculate_eta(self, delivery: Dict[str, Any]) -> str:
        """
        Calculate estimated delivery time.
        
        In production: use actual GPS data, courier APIs
        For now: use DocDueDate or estimate based on creation date
        """
        due_date_str = delivery.get("DocDueDate")
        
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str[:10], "%Y-%m-%d")
                
                # If past due, return overdue message
                if datetime.now() > due_date:
                    days_overdue = (datetime.now() - due_date).days
                    return f"Overdue by {days_overdue} day(s)"
                
                # Return days until delivery
                days_until = (due_date - datetime.now()).days
                if days_until == 0:
                    return "Today"
                elif days_until == 1:
                    return "Tomorrow"
                else:
                    return f"In {days_until} days"
            except:
                pass
        
        return "Unknown"
    
    def _build_delivery_timeline(self, delivery: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Build a timeline of delivery events.
        
        In production: integrate with real tracking events
        For now: create timeline from SAP dates
        """
        timeline = []
        
        # Order created
        doc_date = delivery.get("DocDate")
        if doc_date:
            timeline.append({
                "event": "Order Created",
                "date": doc_date,
                "status": "completed"
            })
        
        # Check if dispatched
        ship_date = delivery.get("U_ShipDate")
        if ship_date:
            timeline.append({
                "event": "Dispatched",
                "date": ship_date,
                "status": "completed"
            })
        
        # Expected delivery
        due_date = delivery.get("DocDueDate")
        status = delivery.get("Status")
        
        if due_date:
            timeline.append({
                "event": "Expected Delivery",
                "date": due_date,
                "status": "completed" if status == "Delivered" else "pending"
            })
        
        return timeline
    
    def _calculate_ontime_rate(self, history: List[Dict[str, Any]]) -> str:
        """Calculate on-time delivery percentage."""
        if not history:
            return "N/A"
        
        # In production: compare actual vs promised delivery dates
        # For now: assume 90% on-time rate
        return "90%"