"""
Inventory Movement Handler - Stock transfers, goods receipt/issue
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.sap_document_service import (
    SAPDocumentService, 
    create_sap_document_service
)
from app.services.business_rules import (
    BusinessRulesEngine,
    create_business_rules_engine
)

logger = logging.getLogger(__name__)


class InventoryMovementHandler:
    """
    Handles all inventory movement intents:
    - CREATE_GOODS_ISSUE
    - CREATE_GOODS_RECEIPT
    - CREATE_STOCK_TRANSFER
    - GET_INVENTORY_VALUATION
    - GET_REORDER_REPORT
    - GET_LOW_STOCK_ALERTS
    - ALLOCATE_STOCK
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
    
    def handle_create_stock_transfer(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Create stock transfer between warehouses
        """
        from_warehouse = entities.get("from_warehouse") or entities.get("source_warehouse")
        to_warehouse = entities.get("to_warehouse") or entities.get("destination_warehouse")
        items = entities.get("items", [])
        
        # Extract from message if not in entities
        if not items and entities.get("item_name"):
            quantity = entities.get("quantity", 1)
            items = [{
                "ItemCode": entities.get("item_code") or entities.get("item_name"),
                "ItemName": entities.get("item_name"),
                "Quantity": quantity
            }]
        
        if not from_warehouse:
            if language == "sw":
                return {"message": "Tafadhali taja ghala la chanzo. Kwa mfano: 'hamisha hisa kutoka NRB01 hadi NAK01'", "data": []}
            return {"message": "Please specify source warehouse. Example: 'transfer stock from NRB01 to NAK01'", "data": []}
        
        if not to_warehouse:
            if language == "sw":
                return {"message": "Tafadhali taja ghala lengwa.", "data": []}
            return {"message": "Please specify destination warehouse.", "data": []}
        
        if not items:
            if language == "sw":
                return {"message": "Tafadhali taja bidhaa za kuhamisha.", "data": []}
            return {"message": "Please specify items to transfer.", "data": []}
        
        # Check stock availability at source
        stock_check = self.rules.check_stock_availability(items, from_warehouse)
        blocking_issues = [r for r in stock_check if not r.passed and r.severity == "blocking"]
        
        if blocking_issues:
            issues_msg = "\n".join([r.message for r in blocking_issues])
            return {
                "message": f"❌ Stock transfer cannot proceed:\n{issues_msg}",
                "data": [],
                "success": False
            }
        
        # Create stock transfer
        transfer_doc_lines = []
        for item in items:
            transfer_doc_lines.append({
                "ItemCode": item.get("ItemCode"),
                "ItemName": item.get("ItemName", item.get("ItemCode")),
                "Quantity": float(item.get("Quantity", 1)),
                "FromWarehouse": from_warehouse,
                "ToWarehouse": to_warehouse
            })
        
        result = self.sap_docs.create_stock_transfer(
            from_warehouse=from_warehouse,
            to_warehouse=to_warehouse,
            items=transfer_doc_lines        )
        
        if result.get("success"):
            if language == "sw":
                msg = f"✅ **Uhamisho wa Hisa Umeundwa!**\n\nKutoka: {from_warehouse}\nKwenda: {to_warehouse}\nBidhaa: {len(items)}\n\nUhamisho umehifadhiwa kwenye mfumo."
            else:
                msg = f"✅ **Stock Transfer Created!**\n\nFrom: {from_warehouse}\nTo: {to_warehouse}\nItems: {len(items)}\n\nThe transfer has been saved to the system."
            
            return {
                "message": msg,
                "data": [{"from_warehouse": from_warehouse, "to_warehouse": to_warehouse, "items": items}],
                "success": True,
                "ui_hint": "stock_transfer_card",
                "actions": [
                    {"label": "View Transfer", "intent": "GET_STOCK_TRANSFER", "variant": "primary"},
                    {"label": "Complete Transfer", "intent": "COMPLETE_STOCK_TRANSFER", "variant": "secondary"}
                ]
            }
        else:
            return {"message": f"Failed to create stock transfer: {result.get('error')}", "data": [], "success": False}
    
    def handle_create_goods_receipt(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Create goods receipt (stock in)
        """
        po_num = entities.get("po_num") or entities.get("purchase_order")
        warehouse = entities.get("warehouse", "MAIN")
        items = entities.get("items", [])
        
        if po_num:
            # Create goods receipt from purchase order
            result = self.sap_docs.create_goods_receipt(po_num)
            
            if result.get("success"):
                if language == "sw":
                    msg = f"✅ **Upokaji wa Bidhaa Umeundwa!**\n\nKutoka kwa Agizo la Ununuzi: {po_num}\nGhala: {warehouse}\n\nBidhaa zimepokewa kwenye mfumo."
                else:
                    msg = f"✅ **Goods Receipt Created!**\n\nFrom Purchase Order: {po_num}\nWarehouse: {warehouse}\n\nGoods have been received into the system."
                
                return {
                    "message": msg,
                    "data": [{"po_num": po_num, "warehouse": warehouse}],
                    "success": True,
                    "ui_hint": "goods_receipt_card"
                }
            else:
                return {"message": f"Failed to create goods receipt: {result.get('error')}", "data": [], "success": False}
        
        elif items:
            # Create direct goods receipt
            result = self.sap_docs.create_goods_receipt(
                warehouse=warehouse,
                items=items
            )
            
            if result.get("success"):
                if language == "sw":
                    msg = f"✅ **Upokaji wa Bidhaa Umeundwa!**\n\nGhala: {warehouse}\nBidhaa: {len(items)}\n\nBidhaa zimepokewa kwenye mfumo."
                else:
                    msg = f"✅ **Goods Receipt Created!**\n\nWarehouse: {warehouse}\nItems: {len(items)}\n\nGoods have been received into the system."
                
                return {
                    "message": msg,
                    "data": [{"warehouse": warehouse, "items": items}],
                    "success": True,
                    "ui_hint": "goods_receipt_card"
                }
            else:
                return {"message": f"Failed to create goods receipt: {result.get('error')}", "data": [], "success": False}
        else:
            if language == "sw":
                return {"message": "Tafadhali taja namba ya agizo la ununuzi au bidhaa za kupokea.", "data": []}
            return {"message": "Please specify a purchase order number or items to receive.", "data": []}
    
    def handle_create_goods_issue(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Create goods issue (stock out)
        """
        warehouse = entities.get("warehouse", "MAIN")
        items = entities.get("items", [])
        reason = entities.get("reason", "")
        
        # Extract from message if not in entities
        if not items and entities.get("item_name"):
            quantity = entities.get("quantity", 1)
            items = [{
                "ItemCode": entities.get("item_code") or entities.get("item_name"),
                "ItemName": entities.get("item_name"),
                "Quantity": quantity
            }]
        
        if not items:
            if language == "sw":
                return {"message": "Tafadhali taja bidhaa za kutoa kutoka ghala.", "data": []}
            return {"message": "Please specify items to issue from stock.", "data": []}
        
        # Check stock availability
        stock_check = self.rules.check_stock_availability(items, warehouse)
        blocking_issues = [r for r in stock_check if not r.passed and r.severity == "blocking"]
        
        if blocking_issues:
            issues_msg = "\n".join([r.message for r in blocking_issues])
            return {
                "message": f"❌ Goods issue cannot proceed:\n{issues_msg}",
                "data": [],
                "success": False
            }
        
        # Create goods issue
        result = self.sap_docs.create_goods_issue(
            warehouse=warehouse,
            items=items,
            reason=reason
        )
        
        if result.get("success"):
            if language == "sw":
                msg = f"✅ **Utoaji wa Bidhaa Umeundwa!**\n\nGhala: {warehouse}\nBidhaa: {len(items)}\nSababu: {reason or 'Hakuna'}\n\nBidhaa zimetolewa kutoka kwenye mfumo."
            else:
                msg = f"✅ **Goods Issue Created!**\n\nWarehouse: {warehouse}\nItems: {len(items)}\nReason: {reason or 'None'}\n\nGoods have been issued from the system."
            
            return {
                "message": msg,
                "data": [{"warehouse": warehouse, "items": items, "reason": reason}],
                "success": True,
                "ui_hint": "goods_issue_card"
            }
        else:
            return {"message": f"Failed to create goods issue: {result.get('error')}", "data": [], "success": False}
    
    def handle_get_reorder_report(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Get report of items that need reordering (below reorder point)
        """
        warehouse = entities.get("warehouse")
        limit = entities.get("quantity", 20)
        
        # Get inventory report
        inventory = self.router.api.get_inventory_report(limit=100)
        
        reorder_items = []
        for item in inventory:
            on_hand = float(item.get("CurrentOnHand", 0))
            min_stock = float(item.get("MinStock", 0)) or 10  # Default if not set
            
            if 0 < on_hand <= min_stock:
                reorder_items.append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName"),
                    "OnHand": on_hand,
                    "ReorderPoint": min_stock,
                    "Shortfall": min_stock - on_hand,
                    "Warehouse": item.get("WhsCode")
                })
        
        # Filter by warehouse if specified
        if warehouse:
            reorder_items = [i for i in reorder_items if i.get("Warehouse") == warehouse]
        
        reorder_items = sorted(reorder_items, key=lambda x: x["Shortfall"], reverse=True)[:limit]
        
        if not reorder_items:
            if language == "sw":
                return {"message": "Hakuna bidhaa zinazohitaji kuagizwa upya. Hisa zote ziko katika kiwango kinachokubalika.", "data": []}
            return {"message": "No items need reordering. All stock levels are acceptable.", "data": []}
        
        if language == "sw":
            lines = [f"📊 **Ripoti ya Kuagiza Upya**"]
            lines.append(f"Bidhaa zinazohitaji kuagizwa: {len(reorder_items)}")
            lines.append("")
            lines.append("**Orodha ya Bidhaa:**")
            
            for item in reorder_items[:10]:
                lines.append(f"⚠️ **{item['ItemName']}**")
                lines.append(f"   Hisa iliyopo: {item['OnHand']:.0f}")
                lines.append(f"   Kiwango cha kuagiza: {item['ReorderPoint']:.0f}")
                lines.append(f"   Upungufu: {item['Shortfall']:.0f}")
        else:
            lines = [f"📊 **Reorder Report**"]
            lines.append(f"Items needing reorder: {len(reorder_items)}")
            lines.append("")
            lines.append("**Items to Reorder:**")
            
            for item in reorder_items[:10]:
                lines.append(f"⚠️ **{item['ItemName']}**")
                lines.append(f"   Current Stock: {item['OnHand']:.0f}")
                lines.append(f"   Reorder Point: {item['ReorderPoint']:.0f}")
                lines.append(f"   Shortfall: {item['Shortfall']:.0f}")
        
        return {
            "message": "\n".join(lines),
            "data": reorder_items,
            "count": len(reorder_items),
            "ui_hint": "reorder_report",
            "actions": [
                {"label": "Create Purchase Order", "intent": "CREATE_PURCHASE_ORDER", "variant": "primary"},
                {"label": "Export Report", "intent": "EXPORT_REORDER_REPORT", "variant": "secondary"}
            ]
        }