"""
app/services/invoice_service.py
================================
Service for managing customer invoices (Document Type 13)
"""

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class InvoiceService:
    """
    Service for managing customer invoices.
    Provides methods to fetch, analyze, and manage customer invoices.
    """

    DOC_TYPE_INVOICE = 13
    
    STATUS_MAP = {
        1: {"en": "Open", "sw": "Funguliwa"},
        2: {"en": "Closed", "sw": "Imefungwa"},
        3: {"en": "Cancelled", "sw": "Imeghairiwa"},
    }

    def __init__(self, api):
        self.api = api

    def get_customer_invoices(
        self,
        customer_name: str,
        limit: int = 20,
        doc_status: str = "all",
        include_details: bool = False
    ) -> List[Dict]:
        """
        Get invoices for a specific customer.
        
        Args:
            customer_name: Name of the customer
            limit: Maximum number of invoices to return
            doc_status: Invoice status ('open', 'closed', 'all')
            include_details: Whether to include line items
        
        Returns:
            List of invoices with details
        """
        try:
            logger.info(f"📋 Fetching invoices for customer: {customer_name}")
            
            # Resolve customer
            customer = self.api.resolve_customer(customer_name)
            if not customer:
                logger.warning(f"⚠️ Customer '{customer_name}' not found")
                return []
            
            customer_code = customer.get("CardCode")
            customer_name_resolved = customer.get("CardName", customer_name)
            
            # Determine status value
            status_value = None
            if doc_status.lower() == "open":
                status_value = 1
            elif doc_status.lower() == "closed":
                status_value = 2
            
            # Fetch invoices (Document Type 13 = Invoices)
            params = {
                "isDoc": 1,
                "page": 1,
                "per_page": min(limit, 100),
                "CardCode": customer_code
            }
            if status_value is not None:
                params["DocStatus"] = status_value
            
            url = f"{self.api.base_url}/marketing/docs/{self.DOC_TYPE_INVOICE}"
            resp = self.api.session.get(url, params=params, timeout=20)
            self.api._debug_response("CUSTOMER INVOICES", resp)
            
            if resp.status_code != 200:
                logger.error(f"Failed to fetch invoices: {resp.status_code}")
                return []
            
            invoices = self.api._normalize(resp.json())
            
            # Enhance invoices with additional info
            enhanced_invoices = []
            for invoice in invoices[:limit]:
                enhanced_invoice = self._enhance_invoice(invoice, customer)
                enhanced_invoices.append(enhanced_invoice)
            
            logger.info(f"✅ Found {len(enhanced_invoices)} invoices for {customer_name_resolved}")
            return enhanced_invoices
            
        except Exception as e:
            logger.error(f"❌ Error fetching customer invoices: {e}")
            return []

    def get_invoice_details(self, invoice_number: str) -> Optional[Dict]:
        """
        Get detailed information for a specific invoice.
        
        Args:
            invoice_number: The invoice document number
        
        Returns:
            Invoice details or None if not found
        """
        try:
            logger.info(f"🔍 Fetching invoice #{invoice_number}")
            url = f"{self.api.base_url}/marketing/docs/{self.DOC_TYPE_INVOICE}/{invoice_number}"
            params = {"isDoc": 1}
            resp = self.api.session.get(url, params=params, timeout=20)
            self.api._debug_response("INVOICE DETAILS", resp)
            
            if resp.status_code == 200:
                data = resp.json()
                normalized = self.api._normalize(data)
                if normalized and len(normalized) > 0:
                    invoice = normalized[0]
                    
                    # Get customer info
                    customer_code = invoice.get("CardCode")
                    if customer_code:
                        customer = self.api.get_customer_by_code(customer_code)
                        if customer:
                            invoice["CustomerName"] = customer.get("CardName")
                    
                    return self._enhance_invoice(invoice, {})
            
            logger.warning(f"⚠️ Invoice #{invoice_number} not found")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error fetching invoice details: {e}")
            return None

    def get_recent_invoices(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """
        Get recent invoices across all customers.
        
        Args:
            days: Number of days to look back
            limit: Maximum number of invoices to return
        
        Returns:
            List of recent invoices
        """
        try:
            logger.info(f"📋 Fetching recent invoices from last {days} days")
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            params = {
                "isDoc": 1,
                "page": 1,
                "per_page": limit,
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d")
            }
            
            url = f"{self.api.base_url}/marketing/docs/{self.DOC_TYPE_INVOICE}"
            resp = self.api.session.get(url, params=params, timeout=20)
            self.api._debug_response("RECENT INVOICES", resp)
            
            if resp.status_code != 200:
                logger.error(f"Failed to fetch recent invoices: {resp.status_code}")
                return []
            
            invoices = self.api._normalize(resp.json())
            
            # Enhance each invoice
            enhanced_invoices = []
            for invoice in invoices[:limit]:
                # Get customer info
                customer_code = invoice.get("CardCode")
                if customer_code:
                    customer = self.api.get_customer_by_code(customer_code)
                    if customer:
                        invoice["CustomerName"] = customer.get("CardName")
                
                enhanced_invoices.append(self._enhance_invoice(invoice, {}))
            
            logger.info(f"✅ Found {len(enhanced_invoices)} recent invoices")
            return enhanced_invoices
            
        except Exception as e:
            logger.error(f"❌ Error fetching recent invoices: {e}")
            return []

    def get_invoice_summary(self, customer_name: str) -> Dict[str, Any]:
        """
        Get invoice summary statistics for a customer.
        
        Args:
            customer_name: Name of the customer
        
        Returns:
            Dictionary with invoice statistics
        """
        try:
            invoices = self.get_customer_invoices(customer_name, limit=100, doc_status="all")
            
            if not invoices:
                return {
                    "customer": customer_name,
                    "total_invoices": 0,
                    "total_amount": 0,
                    "average_amount": 0,
                    "open_invoices": 0,
                    "closed_invoices": 0,
                    "overdue_invoices": 0,
                    "recent_invoices": []
                }
            
            total_amount = sum(float(inv.get("DocTotal", 0)) for inv in invoices)
            open_invoices = sum(1 for inv in invoices if inv.get("StatusText") == "Open")
            closed_invoices = sum(1 for inv in invoices if inv.get("StatusText") == "Closed")
            
            # Calculate overdue invoices (due date passed and not paid)
            today = datetime.now().date()
            overdue_invoices = 0
            for inv in invoices:
                due_date = inv.get("DocDueDate")
                if due_date and inv.get("StatusText") != "Closed":
                    try:
                        due = datetime.strptime(due_date[:10], "%Y-%m-%d").date()
                        if due < today:
                            overdue_invoices += 1
                    except:
                        pass
            
            # Get recent invoices (last 5)
            recent = sorted(invoices, key=lambda x: x.get("DocDate", ""), reverse=True)[:5]
            
            return {
                "customer": customer_name,
                "total_invoices": len(invoices),
                "total_amount": total_amount,
                "average_amount": total_amount / len(invoices) if invoices else 0,
                "open_invoices": open_invoices,
                "closed_invoices": closed_invoices,
                "overdue_invoices": overdue_invoices,
                "recent_invoices": [
                    {
                        "invoice_number": inv.get("DocNum"),
                        "date": inv.get("DocDate"),
                        "due_date": inv.get("DocDueDate"),
                        "total": inv.get("DocTotal"),
                        "status": inv.get("StatusText")
                    }
                    for inv in recent
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculating invoice summary: {e}")
            return {"error": str(e), "customer": customer_name}

    def _enhance_invoice(self, invoice: Dict, customer: Dict) -> Dict:
        """Enhance invoice with additional calculated fields."""
        enhanced = invoice.copy()
        
        # Add customer info if available
        if customer:
            enhanced["CustomerName"] = customer.get("CardName")
            enhanced["CustomerCode"] = customer.get("CardCode")
        
        # Add status text
        doc_status = invoice.get("DocStatus")
        if doc_status in self.STATUS_MAP:
            enhanced["StatusText"] = self.STATUS_MAP[doc_status]["en"]
        elif doc_status in [1, "1", "bost_Open"]:
            enhanced["StatusText"] = "Open"
        elif doc_status in [2, "2", "bost_Close"]:
            enhanced["StatusText"] = "Closed"
        elif doc_status in [3, "3"]:
            enhanced["StatusText"] = "Cancelled"
        else:
            enhanced["StatusText"] = str(doc_status) if doc_status else "Unknown"
        
        # Format total
        total = invoice.get("DocTotal", 0)
        enhanced["TotalFormatted"] = f"KES {float(total):,.2f}"
        
        # Calculate days overdue if applicable
        if enhanced["StatusText"] != "Closed":
            due_date = invoice.get("DocDueDate")
            if due_date:
                try:
                    due = datetime.strptime(due_date[:10], "%Y-%m-%d").date()
                    today = datetime.now().date()
                    if due < today:
                        enhanced["DaysOverdue"] = (today - due).days
                except:
                    pass
        
        return enhanced