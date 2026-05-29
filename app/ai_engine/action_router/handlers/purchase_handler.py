"""
Purchase Handler - Purchase order and procurement operations
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.sap_document_service import (
    SAPDocumentService, 
    create_sap_document_service,
    SAPDocType
)
from app.services.business_rules import (
    BusinessRulesEngine,
    create_business_rules_engine
)

logger = logging.getLogger(__name__)


class PurchaseHandler:
    """
    Handles all purchase-related intents:
    - GET_PURCHASE_ORDERS
    - CREATE_PURCHASE_ORDER
    - GET_PURCHASE_REQUESTS
    - GET_GOODS_RECEIPT
    - GET_AP_INVOICES
    - APPROVE_PURCHASE_ORDER
    """
    
    def __init__(self, action_router):
        self.router = action_router
        self._sap_docs = None
        self._rules = None
    
    @property
    def sap_docs(self) -> SAPDocumentService:
        if self._sap_docs is None:
            self._sap_docs = create_sap_document_service(
                user_token=self.router.user_token,
                company_code=self.router.company_code
            )
        return self._sap_docs
    
    @property
    def rules(self) -> BusinessRulesEngine:
        if self._rules is None:
            self._rules = create_business_rules_engine(
                user_token=self.router.user_token,
                company_code=self.router.company_code
            )
        return self._rules
    
    def handle_get_purchase_orders(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Get purchase orders with optional filters
        """
        vendor_name = entities.get("vendor_name") or entities.get("customer_name", "").strip()
        status = entities.get("status", "open")
        limit = entities.get("quantity", 20)
        
        # Resolve vendor code if name provided
        vendor_code = None
        vendor_display = None
        if vendor_name:
            # Search for vendor (business partner with CardType='S')
            vendors = self.router.api.get_vendors(search=vendor_name, limit=5)
            if vendors:
                vendor_code = vendors[0].get("CardCode")
                vendor_display = vendors[0].get("CardName", vendor_name)
        
        purchase_orders = self.sap_docs.get_purchase_orders(
            vendor_code=vendor_code,
            status=status if status != "all" else None,
            limit=limit
        )
        
        if not purchase_orders:
            if vendor_display:
                msg = f"No purchase orders found for {vendor_display}." if language == "en" else f"Hakuna maagizo ya ununuzi yaliyopatikana kwa {vendor_display}."
            else:
                msg = f"No purchase orders found." if language == "en" else "Hakuna maagizo ya ununuzi yaliyopatikana."
            
            return {"message": msg, "data": []}
        
        # Format response
        total_amount = sum(float(po.get("DocTotal", 0)) for po in purchase_orders)
        
        if language == "sw":
            lines = [f"📦 **Maagizo ya Ununuzi**"]
            if vendor_display:
                lines.append(f"Muuzaji: {vendor_display}")
            lines.append(f"Jumla: KES {total_amount:,.2f}")
            lines.append(f"Idadi: {len(purchase_orders)}")
            lines.append("")
            lines.append("**Orodha ya Maagizo:**")
            
            for po in purchase_orders[:10]:
                doc_date = po.get("DocDate", "")[:10]
                status_icon = "🟢" if po.get("DocStatus") == "C" else "🟡"
                lines.append(f"{status_icon} PO#{po.get('DocNum')} - KES {float(po.get('DocTotal', 0)):,.2f} - Tarehe: {doc_date}")
        else:
            lines = [f"📦 **Purchase Orders**"]
            if vendor_display:
                lines.append(f"Vendor: {vendor_display}")
            lines.append(f"Total: KES {total_amount:,.2f}")
            lines.append(f"Count: {len(purchase_orders)}")
            lines.append("")
            lines.append("**Purchase Order List:**")
            
            for po in purchase_orders[:10]:
                doc_date = po.get("DocDate", "")[:10]
                status_icon = "🟢" if po.get("DocStatus") == "C" else "🟡"
                lines.append(f"{status_icon} PO#{po.get('DocNum')} - KES {float(po.get('DocTotal', 0)):,.2f} - Date: {doc_date}")
        
        if len(purchase_orders) > 10:
            lines.append(f"\n... and {len(purchase_orders) - 10} more")
        
        return {
            "message": "\n".join(lines),
            "data": purchase_orders[:20],
            "total_amount": total_amount,
            "count": len(purchase_orders),
            "ui_hint": "purchase_order_list"
        }
    
    def handle_create_purchase_order(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Create a purchase order
        """
        vendor_name = entities.get("vendor_name") or entities.get("customer_name", "").strip()
        items = entities.get("items", [])
        
        # Extract items from message if not in entities
        if not items and entities.get("item_name"):
            quantity = entities.get("quantity", 1)
            items = [{
                "ItemCode": entities.get("item_code") or entities.get("item_name"),
                "ItemName": entities.get("item_name"),
                "Quantity": quantity
            }]
        
        if not vendor_name:
            if language == "sw":
                return {"message": "Tafadhali taja muuzaji. Kwa mfano: 'unda agizo la ununuzi kwa ABC Suppliers'", "data": []}
            return {"message": "Please specify a vendor. Example: 'create purchase order for ABC Suppliers'", "data": []}
        
        if not items:
            if language == "sw":
                return {"message": "Tafadhali taja bidhaa unazotaka kununua.", "data": []}
            return {"message": "Please specify the items to purchase.", "data": []}
        
        # Resolve vendor
        vendors = self.router.api.get_vendors(search=vendor_name, limit=5)
        if not vendors:
            return {"message": f"Vendor '{vendor_name}' not found.", "data": []}
        
        vendor = vendors[0]
        vendor_code = vendor.get("CardCode")
        vendor_display = vendor.get("CardName", vendor_name)
        
        # Build purchase order data
        document_lines = []
        for item in items:
            # Get item details
            item_code = item.get("ItemCode") or item.get("name")
            item_name = item.get("ItemName") or item.get("name")
            quantity = float(item.get("Quantity", 1))
            
            # Get item price (vendor price if available, else standard)
            # This would call a vendor pricing service in production
            price = item.get("Price", 0)
            
            document_lines.append({
                "ItemCode": item_code,
                "ItemName": item_name,
                "Quantity": quantity,
                "Price": price,
                "LineTotal": quantity * price,
                "WarehouseCode": entities.get("warehouse", "")
            })
        
        po_data = {
            "CardCode": vendor_code,
            "CardName": vendor_display,
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocDueDate": (datetime.now().replace(day=datetime.now().day + 30)).strftime("%Y-%m-%d"),
            "DocumentLines": document_lines,
            "Comments": f"PO created via AI Assistant"
        }
        
        # Check approval requirements
        total_amount = sum(line["LineTotal"] for line in document_lines)
        approval_check = self.rules.check_approval_required(
            doc_type="purchase_order",
            amount=total_amount,
            user_role=self.router.user_role
        )
        
        if not approval_check.passed:
            # Request approval instead of creating
            return {
                "message": f"⚠️ {approval_check.message}\n\nWould you like to request approval?",
                "data": [],
                "requires_approval": True,
                "approval_amount": total_amount,
                "actions": [
                    {"label": "Request Approval", "intent": "REQUEST_PO_APPROVAL", "variant": "primary"},
                    {"label": "Cancel", "intent": "CANCEL", "variant": "secondary"}
                ]
            }
        
        # Create purchase order
        result = self.sap_docs.create_purchase_order(po_data)
        
        if result.get("success"):
            po_num = result.get("data", {}).get("DocNum", "created")
            
            if language == "sw":
                msg = f"✅ **Agizo la Ununuzi Limeundwa!**\n\n**Muuzaji:** {vendor_display}\n**Jumla:** KES {total_amount:,.2f}\n**Namba ya PO:** {po_num}\n\nAgizo limehifadhiwa kwenye mfumo."
            else:
                msg = f"✅ **Purchase Order Created!**\n\n**Vendor:** {vendor_display}\n**Total:** KES {total_amount:,.2f}\n**PO Number:** {po_num}\n\nThe purchase order has been saved to the system."
            
            return {
                "message": msg,
                "data": [{"po_num": po_num, "vendor": vendor_display, "total_amount": total_amount, "items": document_lines}],
                "success": True,
                "ui_hint": "purchase_order_card",
                "actions": [
                    {"label": "View PO", "intent": "GET_PURCHASE_ORDER", "params": {"doc_num": po_num}},
                    {"label": "Create Goods Receipt", "intent": "CREATE_GOODS_RECEIPT", "params": {"po_num": po_num}},
                    {"label": "Print PO", "intent": "PRINT_PURCHASE_ORDER", "params": {"doc_num": po_num}}
                ]
            }
        else:
            error_msg = result.get("error", "Unknown error")
            return {"message": f"Failed to create purchase order: {error_msg}", "data": [], "success": False}
    
    def handle_get_purchase_requests(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Get purchase requests (PRs)
        """
        limit = entities.get("quantity", 20)
        
        # Get purchase requests from API
        try:
            result = self.router.api.get("/purchase_requests", params={"limit": limit})
            prs = result.get("data", []) if result.get("success") else []
        except:
            prs = []
        
        if not prs:
            if language == "sw":
                return {"message": "Hakuna maombi ya ununuzi yaliyopatikana.", "data": []}
            return {"message": "No purchase requests found.", "data": []}
        
        if language == "sw":
            lines = [f"📋 **Maombi ya Ununuzi**"]
            lines.append(f"Idadi: {len(prs)}")
            lines.append("")
            lines.append("**Orodha ya Maombi:**")
            
            for pr in prs[:10]:
                status_icon = "🟢" if pr.get("status") == "approved" else "🟡" if pr.get("status") == "pending" else "⚪"
                lines.append(f"{status_icon} PR#{pr.get('pr_num')} - {pr.get('requested_by')} - {pr.get('department')}")
        else:
            lines = [f"📋 **Purchase Requests**"]
            lines.append(f"Count: {len(prs)}")
            lines.append("")
            lines.append("**Purchase Request List:**")
            
            for pr in prs[:10]:
                status_icon = "🟢" if pr.get("status") == "approved" else "🟡" if pr.get("status") == "pending" else "⚪"
                lines.append(f"{status_icon} PR#{pr.get('pr_num')} - {pr.get('requested_by')} - {pr.get('department')}")
        
        return {
            "message": "\n".join(lines),
            "data": prs[:20],
            "count": len(prs),
            "ui_hint": "purchase_request_list"
        }
    
    def handle_approve_purchase_order(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Approve a purchase order (manager only)
        """
        po_num = entities.get("doc_num") or entities.get("po_num")
        
        if not po_num:
            if language == "sw":
                return {"message": "Tafadhali taja namba ya agizo la ununuzi.", "data": []}
            return {"message": "Please specify the purchase order number.", "data": []}
        
        # Check if user is manager
        if self.router.user_role != "manager":
            if language == "sw":
                return {"message": "Samahani, uidhinishaji wa agizo la ununuzi unahitaji daraja la meneja.", "data": []}
            return {"message": "Sorry, purchase order approval requires manager role.", "data": []}
        
        # Approve the PO
        result = self.sap_docs.close_document(SAPDocType.PURCHASE_ORDER, po_num)
        
        if result.get("success"):
            if language == "sw":
                msg = f"✅ Agizo la Ununuzi #{po_num} limeidhinishwa."
            else:
                msg = f"✅ Purchase Order #{po_num} has been approved."
            
            return {
                "message": msg,
                "data": [{"po_num": po_num, "status": "approved"}],
                "ui_hint": "success_confirmation"
            }
        else:
            return {"message": f"Failed to approve PO #{po_num}: {result.get('error')}", "data": []}