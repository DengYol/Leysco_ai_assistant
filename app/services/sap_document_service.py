"""
SAP Document Service - Unified API for all SAP B1 document types
Covers Sales, Purchase, Inventory, and Financial documents
"""

import logging
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime

from app.services.leysco_api.client import LeyscoAPIService, create_api_service

logger = logging.getLogger(__name__)


class SAPDocType(int, Enum):
    """SAP B1 Document Type IDs"""
    # Sales Cycle
    QUOTATION = 23
    SALES_ORDER = 17
    DELIVERY = 15
    AR_INVOICE = 13
    AR_CREDIT_MEMO = 14
    INCOMING_PAYMENT = 24
    
    # Purchase Cycle
    PURCHASE_REQUEST = 1470000113
    PURCHASE_ORDER = 22
    GOODS_RECEIPT_PO = 20
    AP_INVOICE = 18
    AP_CREDIT_MEMO = 19
    OUTGOING_PAYMENT = 25
    
    # Inventory
    GOODS_RECEIPT = 59
    GOODS_ISSUE = 60
    INVENTORY_TRANSFER = 67
    INVENTORY_COUNTING = 68
    
    # Financial
    JOURNAL_ENTRY = 30
    
    # Business Partners
    CUSTOMER = 2
    VENDOR = 4


class DocumentStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    DRAFT = "draft"


class SAPDocumentService:
    """
    Unified service for all SAP B1 document operations
    Provides consistent interface for all document types
    """
    
    def __init__(self, user_token: str = None, company_code: str = None):
        self.user_token = user_token
        self.company_code = company_code
        self.api = create_api_service(
            user_token=user_token, 
            company_code=company_code
        )
    
    # =========================================================
    # SALES CYCLE DOCUMENTS
    # =========================================================
    
    def get_quotation(self, doc_num: str) -> Optional[Dict]:
        """Get quotation by document number"""
        return self._get_document(SAPDocType.QUOTATION, doc_num)
    
    def get_quotations(self, customer_code: str = None, status: str = None, limit: int = 50) -> List[Dict]:
        """Get quotations with filters"""
        return self._search_documents(
            doc_type=SAPDocType.QUOTATION,
            customer_code=customer_code,
            status=status,
            limit=limit
        )
    
    def create_quotation(self, data: Dict) -> Dict:
        """Create new quotation"""
        return self._create_document(SAPDocType.QUOTATION, data)
    
    def convert_quotation_to_order(self, quotation_num: str) -> Dict:
        """
        Convert quotation to sales order
        Copies quotation data and creates new sales order
        """
        quote = self.get_quotation(quotation_num)
        if not quote:
            return {"success": False, "error": f"Quotation {quotation_num} not found"}
        
        # Prepare order data from quotation
        order_data = {
            "CardCode": quote.get("CardCode"),
            "CardName": quote.get("CardName"),
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocDueDate": quote.get("DocDueDate"),
            "DocumentLines": quote.get("DocumentLines", []),
            "Comments": f"Converted from Quotation {quotation_num}"
        }
        
        return self.create_sales_order(order_data)
    
    def get_sales_order(self, doc_num: str) -> Optional[Dict]:
        """Get sales order by document number"""
        return self._get_document(SAPDocType.SALES_ORDER, doc_num)
    
    def get_sales_orders(self, customer_code: str = None, status: str = None, limit: int = 50) -> List[Dict]:
        """Get sales orders with filters"""
        return self._search_documents(
            doc_type=SAPDocType.SALES_ORDER,
            customer_code=customer_code,
            status=status,
            limit=limit
        )
    
    def create_sales_order(self, data: Dict) -> Dict:
        """Create new sales order"""
        return self._create_document(SAPDocType.SALES_ORDER, data)
    
    def get_delivery(self, doc_num: str) -> Optional[Dict]:
        """Get delivery document"""
        return self._get_document(SAPDocType.DELIVERY, doc_num)
    
    def get_outstanding_deliveries(self, customer_code: str = None, limit: int = 100) -> List[Dict]:
        """Get deliveries not yet invoiced"""
        return self._search_documents(
            doc_type=SAPDocType.DELIVERY,
            customer_code=customer_code,
            status="open",
            limit=limit
        )
    
    def create_delivery(self, order_num: str, data: Dict = None) -> Dict:
        """Create delivery from sales order"""
        order = self.get_sales_order(order_num)
        if not order:
            return {"success": False, "error": f"Sales Order {order_num} not found"}
        
        delivery_data = data or {
            "CardCode": order.get("CardCode"),
            "CardName": order.get("CardName"),
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocumentLines": order.get("DocumentLines", []),
            "Comments": f"Delivery for Sales Order {order_num}"
        }
        
        return self._create_document(SAPDocType.DELIVERY, delivery_data)
    
    def convert_delivery_to_invoice(self, delivery_num: str) -> Dict:
        """Convert delivery to A/R invoice"""
        delivery = self.get_delivery(delivery_num)
        if not delivery:
            return {"success": False, "error": f"Delivery {delivery_num} not found"}
        
        invoice_data = {
            "CardCode": delivery.get("CardCode"),
            "CardName": delivery.get("CardName"),
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocDueDate": delivery.get("DocDueDate"),
            "DocumentLines": delivery.get("DocumentLines", []),
            "Comments": f"Invoice for Delivery {delivery_num}"
        }
        
        return self.create_ar_invoice(invoice_data)
    
    def get_ar_invoice(self, doc_num: str) -> Optional[Dict]:
        """Get A/R invoice by document number"""
        return self._get_document(SAPDocType.AR_INVOICE, doc_num)
    
    def get_ar_invoices(self, customer_code: str = None, status: str = None, limit: int = 50) -> List[Dict]:
        """Get A/R invoices with filters"""
        return self._search_documents(
            doc_type=SAPDocType.AR_INVOICE,
            customer_code=customer_code,
            status=status,
            limit=limit
        )
    
    def get_overdue_invoices(self, customer_code: str = None, days_overdue: int = 0) -> List[Dict]:
        """Get overdue A/R invoices"""
        invoices = self.get_ar_invoices(customer_code=customer_code, status="open")
        
        overdue = []
        today = datetime.now().date()
        
        for inv in invoices:
            due_date_str = inv.get("DocDueDate", "")
            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str[:10], "%Y-%m-%d").date()
                    days = (today - due_date).days
                    if days >= days_overdue:
                        inv["days_overdue"] = days
                        overdue.append(inv)
                except:
                    pass
        
        return sorted(overdue, key=lambda x: x.get("days_overdue", 0), reverse=True)
    
    def create_ar_invoice(self, data: Dict) -> Dict:
        """Create A/R invoice"""
        return self._create_document(SAPDocType.AR_INVOICE, data)
    
    def get_customer_balance(self, customer_code: str) -> Dict:
        """Get customer balance (open invoices total)"""
        invoices = self.get_ar_invoices(customer_code=customer_code, status="open")
        total_balance = sum(float(inv.get("DocTotal", 0)) for inv in invoices)
        
        return {
            "customer_code": customer_code,
            "open_invoice_count": len(invoices),
            "total_balance": total_balance,
            "currency": "KES"
        }
    
    # =========================================================
    # PURCHASE CYCLE DOCUMENTS
    # =========================================================
    
    def get_purchase_order(self, doc_num: str) -> Optional[Dict]:
        """Get purchase order by document number"""
        return self._get_document(SAPDocType.PURCHASE_ORDER, doc_num)
    
    def get_purchase_orders(self, vendor_code: str = None, status: str = None, limit: int = 50) -> List[Dict]:
        """Get purchase orders with filters"""
        return self._search_documents(
            doc_type=SAPDocType.PURCHASE_ORDER,
            customer_code=vendor_code,  # Reuse customer_code as vendor_code
            status=status,
            limit=limit
        )
    
    def create_purchase_order(self, data: Dict) -> Dict:
        """Create purchase order"""
        return self._create_document(SAPDocType.PURCHASE_ORDER, data)
    
    def get_goods_receipt_po(self, doc_num: str) -> Optional[Dict]:
        """Get goods receipt PO"""
        return self._get_document(SAPDocType.GOODS_RECEIPT_PO, doc_num)
    
    def create_goods_receipt(self, po_num: str, data: Dict = None) -> Dict:
        """Create goods receipt from purchase order"""
        po = self.get_purchase_order(po_num)
        if not po:
            return {"success": False, "error": f"Purchase Order {po_num} not found"}
        
        receipt_data = data or {
            "CardCode": po.get("CardCode"),
            "CardName": po.get("CardName"),
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocumentLines": po.get("DocumentLines", []),
            "Comments": f"Goods Receipt for PO {po_num}"
        }
        
        return self._create_document(SAPDocType.GOODS_RECEIPT_PO, receipt_data)
    
    def get_ap_invoice(self, doc_num: str) -> Optional[Dict]:
        """Get A/P invoice"""
        return self._get_document(SAPDocType.AP_INVOICE, doc_num)
    
    def get_ap_invoices(self, vendor_code: str = None, status: str = None, limit: int = 50) -> List[Dict]:
        """Get A/P invoices with filters"""
        return self._search_documents(
            doc_type=SAPDocType.AP_INVOICE,
            customer_code=vendor_code,
            status=status,
            limit=limit
        )
    
    def create_ap_invoice(self, data: Dict) -> Dict:
        """Create A/P invoice"""
        return self._create_document(SAPDocType.AP_INVOICE, data)
    
    # =========================================================
    # INVENTORY MOVEMENTS
    # =========================================================
    
    def get_stock_transfer(self, doc_num: str) -> Optional[Dict]:
        """Get inventory transfer document"""
        return self._get_document(SAPDocType.INVENTORY_TRANSFER, doc_num)
    
    def create_stock_transfer(self, from_warehouse: str, to_warehouse: str, items: List[Dict]) -> Dict:
        """Create inventory transfer between warehouses"""
        transfer_data = {
            "FromWarehouse": from_warehouse,
            "ToWarehouse": to_warehouse,
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocumentLines": items,
            "Comments": f"Transfer from {from_warehouse} to {to_warehouse}"
        }
        return self._create_document(SAPDocType.INVENTORY_TRANSFER, transfer_data)
    
    def get_goods_issue(self, doc_num: str) -> Optional[Dict]:
        """Get goods issue document"""
        return self._get_document(SAPDocType.GOODS_ISSUE, doc_num)
    
    def create_goods_issue(self, warehouse: str, items: List[Dict], reason: str = "") -> Dict:
        """Create goods issue (stock out)"""
        issue_data = {
            "Warehouse": warehouse,
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocumentLines": items,
            "Comments": reason or "Goods Issue"
        }
        return self._create_document(SAPDocType.GOODS_ISSUE, issue_data)
    
    def get_goods_receipt(self, doc_num: str) -> Optional[Dict]:
        """Get goods receipt document"""
        return self._get_document(SAPDocType.GOODS_RECEIPT, doc_num)
    
    def create_goods_receipt(self, warehouse: str, items: List[Dict], po_num: str = None) -> Dict:
        """Create goods receipt (stock in)"""
        receipt_data = {
            "Warehouse": warehouse,
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocumentLines": items,
            "Comments": f"Goods Receipt" + (f" for PO {po_num}" if po_num else "")
        }
        return self._create_document(SAPDocType.GOODS_RECEIPT, receipt_data)
    
    # =========================================================
    # DOCUMENT LIFECYCLE
    # =========================================================
    
    def cancel_document(self, doc_type: SAPDocType, doc_num: str, reason: str = "") -> Dict:
        """Cancel a document"""
        # SAP B1 typically uses -1 for cancellation
        return self._update_document_status(doc_type, doc_num, "C", reason)
    
    def close_document(self, doc_type: SAPDocType, doc_num: str) -> Dict:
        """Close a document"""
        return self._update_document_status(doc_type, doc_num, "CL")
    
    def reverse_document(self, doc_type: SAPDocType, doc_num: str, reason: str = "") -> Dict:
        """Reverse a document (creates negative document)"""
        return self._update_document_status(doc_type, doc_num, "R", reason)
    
    # =========================================================
    # PRIVATE METHODS
    # =========================================================
    
    def _get_document(self, doc_type: SAPDocType, doc_num: str) -> Optional[Dict]:
        """Generic document getter"""
        try:
            result = self.api.get(f"/marketing/docs/{doc_type.value}/{doc_num}")
            if result.get("success"):
                return result.get("data")
            return None
        except Exception as e:
            logger.error(f"Failed to get document {doc_type.value}/{doc_num}: {e}")
            return None
    
    def _search_documents(
        self, 
        doc_type: SAPDocType, 
        customer_code: str = None, 
        status: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """Generic document search"""
        try:
            params = {"per_page": limit}
            if customer_code:
                params["card_code"] = customer_code
            if status:
                params["status"] = status
            
            result = self.api.get(f"/marketing/docs/{doc_type.value}", params=params)
            if result.get("success"):
                data = result.get("data", [])
                if isinstance(data, dict):
                    data = data.get("data", [])
                return data
            return []
        except Exception as e:
            logger.error(f"Failed to search documents: {e}")
            return []
    
    def _create_document(self, doc_type: SAPDocType, data: Dict) -> Dict:
        """Generic document creator"""
        try:
            result = self.api.post(f"/marketing/docs/{doc_type.value}", json=data)
            if result.get("success"):
                return {"success": True, "data": result.get("data")}
            return {"success": False, "error": result.get("error", "Creation failed")}
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            return {"success": False, "error": str(e)}
    
    def _update_document_status(self, doc_type: SAPDocType, doc_num: str, status: str, reason: str = "") -> Dict:
        """Generic document status updater"""
        try:
            data = {"DocStatus": status}
            if reason:
                data["Comments"] = reason
            
            result = self.api.patch(f"/marketing/docs/{doc_type.value}/{doc_num}", json=data)
            if result.get("success"):
                return {"success": True, "message": f"Document {doc_num} updated to status {status}"}
            return {"success": False, "error": result.get("error", "Update failed")}
        except Exception as e:
            logger.error(f"Failed to update document: {e}")
            return {"success": False, "error": str(e)}


def create_sap_document_service(user_token: str = None, company_code: str = None) -> SAPDocumentService:
    """Factory function for SAPDocumentService"""
    return SAPDocumentService(user_token=user_token, company_code=company_code)