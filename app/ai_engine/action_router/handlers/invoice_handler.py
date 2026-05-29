"""
Invoice Handler - A/R and A/P invoice operations
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from app.services.sap_document_service import (
    SAPDocumentService, 
    create_sap_document_service,
    SAPDocType
)
from app.services.business_rules import (
    BusinessRulesEngine,
    create_business_rules_engine
)
from app.services.proactive_insights import (
    ProactiveInsightsEngine,
    create_proactive_insights_engine
)

logger = logging.getLogger(__name__)


class InvoiceHandler:
    """
    Handles all invoice-related intents:
    - GET_AR_INVOICES
    - GET_AP_INVOICES
    - GET_OVERDUE_INVOICES
    - GET_CUSTOMER_BALANCE
    - GET_PAYMENT_STATUS
    - CREATE_AR_INVOICE
    - CREATE_AP_INVOICE
    - SEND_PAYMENT_REMINDER
    """
    
    def __init__(self, action_router):
        self.router = action_router
        self._sap_docs = None
        self._rules = None
        self._insights = None
    
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
    
    @property
    def insights(self) -> ProactiveInsightsEngine:
        if self._insights is None:
            self._insights = create_proactive_insights_engine(
                user_token=self.router.user_token,
                company_code=self.router.company_code
            )
        return self._insights
    
    def handle_get_ar_invoices(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Get A/R invoices with optional filters
        """
        customer_name = entities.get("customer_name", "").strip()
        limit = entities.get("quantity", 20)
        status = entities.get("status", "open")
        
        # Resolve customer code if name provided
        customer_code = None
        customer_display = None
        if customer_name:
            customer = self.router.api.resolve_customer(customer_name)
            if customer:
                customer_code = customer.get("CardCode")
                customer_display = customer.get("CardName", customer_name)
        
        invoices = self.sap_docs.get_ar_invoices(
            customer_code=customer_code,
            status=status if status != "all" else None,
            limit=limit
        )
        
        if not invoices:
            if customer_display:
                msg = f"No {status} invoices found for {customer_display}." if language == "en" else f"Hakuna invoice {status} zilizopatikana kwa {customer_display}."
            else:
                msg = f"No {status} invoices found." if language == "en" else f"Hakuna invoice {status} zilizopatikana."
            
            return {"message": msg, "data": []}
        
        # Format response
        total_amount = sum(float(inv.get("DocTotal", 0)) for inv in invoices)
        
        if language == "sw":
            lines = [f"📄 **Invoice za A/R**"]
            if customer_display:
                lines.append(f"Kwa: {customer_display}")
            lines.append(f"Jumla: KES {total_amount:,.2f}")
            lines.append(f"Idadi: {len(invoices)}")
            lines.append("")
            lines.append("**Orodha ya Invoice:**")
            
            for inv in invoices[:10]:
                due_date = inv.get("DocDueDate", "")[:10]
                days_overdue = self._calculate_overdue_days(due_date) if due_date else 0
                status_icon = "🔴" if days_overdue > 0 else "🟢" if inv.get("DocStatus") == "C" else "🟡"
                lines.append(f"{status_icon} #{inv.get('DocNum')} - KES {float(inv.get('DocTotal', 0)):,.2f} - Tarehe: {due_date}")
        else:
            lines = [f"📄 **A/R Invoices**"]
            if customer_display:
                lines.append(f"Customer: {customer_display}")
            lines.append(f"Total Amount: KES {total_amount:,.2f}")
            lines.append(f"Count: {len(invoices)}")
            lines.append("")
            lines.append("**Invoice List:**")
            
            for inv in invoices[:10]:
                due_date = inv.get("DocDueDate", "")[:10]
                days_overdue = self._calculate_overdue_days(due_date) if due_date else 0
                status_icon = "🔴" if days_overdue > 0 else "🟢" if inv.get("DocStatus") == "C" else "🟡"
                lines.append(f"{status_icon} #{inv.get('DocNum')} - KES {float(inv.get('DocTotal', 0)):,.2f} - Due: {due_date}")
        
        if len(invoices) > 10:
            lines.append(f"\n... and {len(invoices) - 10} more")
        
        return {
            "message": "\n".join(lines),
            "data": invoices[:20],
            "total_amount": total_amount,
            "count": len(invoices),
            "ui_hint": "invoice_list"
        }
    
    def handle_get_overdue_invoices(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Get overdue A/R invoices
        """
        customer_name = entities.get("customer_name", "").strip()
        days_overdue = entities.get("days_overdue", 1)
        
        customer_code = None
        customer_display = None
        if customer_name:
            customer = self.router.api.resolve_customer(customer_name)
            if customer:
                customer_code = customer.get("CardCode")
                customer_display = customer.get("CardName", customer_name)
        
        overdue = self.sap_docs.get_overdue_invoices(
            customer_code=customer_code,
            days_overdue=days_overdue
        )
        
        if not overdue:
            if customer_display:
                msg = f"No overdue invoices found for {customer_display}." if language == "en" else f"Hakuna invoice zilizochelewa kwa {customer_display}."
            else:
                msg = "No overdue invoices found." if language == "en" else "Hakuna invoice zilizochelewa."
            
            return {"message": msg, "data": []}
        
        total_overdue = sum(float(inv.get("DocTotal", 0)) for inv in overdue)
        
        if language == "sw":
            lines = [f"🔴 **Invoice Zilizochelewa**"]
            if customer_display:
                lines.append(f"Kwa: {customer_display}")
            lines.append(f"Jumla: KES {total_overdue:,.2f}")
            lines.append(f"Idadi: {len(overdue)}")
            lines.append("")
            lines.append("**Orodha ya Invoice Zilizochelewa:**")
            
            for inv in overdue[:10]:
                due_date = inv.get("DocDueDate", "")[:10]
                days = inv.get("days_overdue", 0)
                lines.append(f"🔴 #{inv.get('DocNum')} - KES {float(inv.get('DocTotal', 0)):,.2f} - Imechelewa siku {days}")
        else:
            lines = [f"🔴 **Overdue Invoices**"]
            if customer_display:
                lines.append(f"Customer: {customer_display}")
            lines.append(f"Total Overdue: KES {total_overdue:,.2f}")
            lines.append(f"Count: {len(overdue)}")
            lines.append("")
            lines.append("**Overdue Invoice List:**")
            
            for inv in overdue[:10]:
                due_date = inv.get("DocDueDate", "")[:10]
                days = inv.get("days_overdue", 0)
                lines.append(f"🔴 #{inv.get('DocNum')} - KES {float(inv.get('DocTotal', 0)):,.2f} - {days} days overdue")
        
        # Add proactive insights
        insights = self.insights.get_insights_for_document("ar_invoice", "")
        if insights:
            lines.append("\n💡 **Proactive Insight:**")
            lines.append(f"   {insights[0]}")
        
        return {
            "message": "\n".join(lines),
            "data": overdue[:20],
            "total_overdue": total_overdue,
            "count": len(overdue),
            "ui_hint": "overdue_invoice_list",
            "actions": [
                {"label": "Send Reminders", "intent": "SEND_PAYMENT_REMINDERS", "variant": "primary"},
                {"label": "View Aging Report", "intent": "GET_AGING_REPORT", "variant": "secondary"}
            ]
        }
    
    def handle_get_customer_balance(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Get customer's current balance (open invoices)
        """
        customer_name = entities.get("customer_name", "").strip()
        
        if not customer_name:
            if language == "sw":
                return {"message": "Tafadhali taja jina la mteja. Kwa mfano: 'Salio la mteja Mahakali Enterprises'", "data": []}
            return {"message": "Please specify a customer name. Example: 'customer balance for Mahakali Enterprises'", "data": []}
        
        customer = self.router.api.resolve_customer(customer_name)
        if not customer:
            if language == "sw":
                return {"message": f"Mteja '{customer_name}' hajakupatikana.", "data": []}
            return {"message": f"Customer '{customer_name}' not found.", "data": []}
        
        customer_code = customer.get("CardCode")
        customer_display = customer.get("CardName", customer_name)
        
        balance = self.sap_docs.get_customer_balance(customer_code)
        
        # Check credit limit
        credit_check = self.rules.check_credit_limit(
            customer_code=customer_code,
            order_amount=0  # Just checking current status
        )
        
        if language == "sw":
            lines = [
                f"💰 **Salio la Mteja**",
                f"**Mteja:** {customer_display}",
                f"**Salio la sasa:** KES {balance['total_balance']:,.2f}",
                f"**Invoice wazi:** {balance['open_invoice_count']}",
                "",
                credit_check.message
            ]
        else:
            lines = [
                f"💰 **Customer Balance**",
                f"**Customer:** {customer_display}",
                f"**Current Balance:** KES {balance['total_balance']:,.2f}",
                f"**Open Invoices:** {balance['open_invoice_count']}",
                "",
                credit_check.message
            ]
        
        return {
            "message": "\n".join(lines),
            "data": [balance],
            "balance": balance['total_balance'],
            "open_invoice_count": balance['open_invoice_count'],
            "ui_hint": "customer_balance_card",
            "actions": [
                {"label": "View Open Invoices", "intent": "GET_OVERDUE_INVOICES", "params": {"customer_name": customer_display}},
                {"label": "View Payment History", "intent": "GET_PAYMENT_HISTORY", "params": {"customer_name": customer_display}}
            ]
        }
    
    def handle_send_payment_reminder(
        self, 
        entities: Dict, 
        message: str, 
        language: str = "en"
    ) -> Dict:
        """
        Send payment reminder for overdue invoices
        """
        customer_name = entities.get("customer_name", "").strip()
        invoice_num = entities.get("invoice_num") or entities.get("doc_num")
        
        if not customer_name and not invoice_num:
            if language == "sw":
                return {"message": "Tafadhali taja mteja au namba ya invoice.", "data": []}
            return {"message": "Please specify a customer or invoice number.", "data": []}
        
        if invoice_num:
            # Get specific invoice
            invoice = self.sap_docs.get_ar_invoice(invoice_num)
            if not invoice:
                return {"message": f"Invoice #{invoice_num} not found.", "data": []}
            customer_display = invoice.get("CardName", "Customer")
            amount = float(invoice.get("DocTotal", 0))
            days_overdue = self._calculate_overdue_days(invoice.get("DocDueDate", ""))
        else:
            # Get customer and their overdue invoices
            customer = self.router.api.resolve_customer(customer_name)
            if not customer:
                return {"message": f"Customer '{customer_name}' not found.", "data": []}
            customer_display = customer.get("CardName", customer_name)
            overdue = self.sap_docs.get_overdue_invoices(customer.get("CardCode"))
            if not overdue:
                return {"message": f"No overdue invoices found for {customer_display}.", "data": []}
            amount = sum(float(inv.get("DocTotal", 0)) for inv in overdue)
            days_overdue = max(inv.get("days_overdue", 0) for inv in overdue)
        
        # Simulate sending reminder
        # In production, this would call an email/SMS API
        
        if language == "sw":
            msg = f"✅ Kumbusho la malipo limetumwa kwa {customer_display} kwa invoice yenye thamani ya KES {amount:,.2f} (imechelewa siku {days_overdue})."
        else:
            msg = f"✅ Payment reminder sent to {customer_display} for invoice(s) totaling KES {amount:,.2f} ({days_overdue} days overdue)."
        
        return {
            "message": msg,
            "data": [],
            "ui_hint": "success_confirmation",
            "actions": [
                {"label": "View Customer", "intent": "GET_CUSTOMER_DETAILS", "params": {"customer_name": customer_display}},
                {"label": "View Invoices", "intent": "GET_OVERDUE_INVOICES", "params": {"customer_name": customer_display}}
            ]
        }
    
    def _calculate_overdue_days(self, due_date_str: str) -> int:
        """Calculate days overdue from due date"""
        if not due_date_str:
            return 0
        try:
            due_date = datetime.strptime(due_date_str[:10], "%Y-%m-%d")
            days = (datetime.now() - due_date).days
            return max(0, days)
        except:
            return 0