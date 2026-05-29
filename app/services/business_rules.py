"""
Business Rules Engine - SAP B1 business logic enforcement
Handles credit limits, stock checks, approvals, and pricing validation
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from app.services.leysco_api.client import LeyscoAPIService, create_api_service
from app.services.pricing_service import PricingService, create_pricing_service

logger = logging.getLogger(__name__)


class RuleSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


@dataclass
class RuleResult:
    """Result of a business rule check"""
    passed: bool
    message: str
    severity: RuleSeverity
    data: Dict[str, Any] = None
    suggested_action: str = None


class BusinessRulesEngine:
    """
    Enforces SAP B1 business rules:
    - Credit limit validation
    - Stock availability checks
    - Approval thresholds
    - Price list validation
    - Tax configuration
    """
    
    def __init__(self, user_token: str = None, company_code: str = None):
        self.user_token = user_token
        self.company_code = company_code
        self.api = create_api_service(user_token=user_token, company_code=company_code)
        self.pricing = create_pricing_service(user_token=user_token, company_code=company_code)
    
    # =========================================================
    # CREDIT LIMIT RULES
    # =========================================================
    
    def check_credit_limit(
        self, 
        customer_code: str, 
        order_amount: float,
        currency: str = "KES"
    ) -> RuleResult:
        """
        Check if order exceeds customer's credit limit
        """
        try:
            # Get customer details
            customers = self.api.get_customers(search=customer_code, limit=1)
            if not customers:
                return RuleResult(
                    passed=False,
                    message=f"Customer {customer_code} not found",
                    severity=RuleSeverity.ERROR
                )
            
            customer = customers[0]
            credit_limit = float(customer.get("CreditLimit", 0))
            current_balance = self._get_customer_balance(customer_code)
            
            # Calculate available credit
            available_credit = credit_limit - current_balance
            would_exceed = order_amount > available_credit
            
            if credit_limit <= 0:
                return RuleResult(
                    passed=True,
                    message=f"No credit limit set for this customer. Current balance: KES {current_balance:,.2f}",
                    severity=RuleSeverity.INFO,
                    data={
                        "credit_limit": credit_limit,
                        "current_balance": current_balance,
                        "available": available_credit,
                        "order_amount": order_amount
                    }
                )
            
            if would_exceed:
                return RuleResult(
                    passed=False,
                    message=f"Order would exceed credit limit. Limit: KES {credit_limit:,.2f}, "
                           f"Current balance: KES {current_balance:,.2f}, "
                           f"Available: KES {available_credit:,.2f}, "
                           f"Order total: KES {order_amount:,.2f}",
                    severity=RuleSeverity.BLOCKING,
                    data={
                        "credit_limit": credit_limit,
                        "current_balance": current_balance,
                        "available": available_credit,
                        "order_amount": order_amount,
                        "excess_amount": order_amount - available_credit
                    },
                    suggested_action="Consider partial order or request credit limit increase"
                )
            
            # Warn if using more than 80% of credit
            utilization = (current_balance + order_amount) / credit_limit
            if utilization > 0.8:
                return RuleResult(
                    passed=True,
                    message=f"⚠️ Credit utilization will be {utilization:.1%} after this order "
                           f"(KES {current_balance + order_amount:,.2f} of {credit_limit:,.2f})",
                    severity=RuleSeverity.WARNING,
                    data={
                        "credit_limit": credit_limit,
                        "current_balance": current_balance,
                        "order_amount": order_amount,
                        "utilization": utilization
                    }
                )
            
            return RuleResult(
                passed=True,
                message=f"✓ Credit check passed. Available: KES {available_credit:,.2f}",
                severity=RuleSeverity.INFO,
                data={
                    "credit_limit": credit_limit,
                    "current_balance": current_balance,
                    "available": available_credit,
                    "order_amount": order_amount
                }
            )
            
        except Exception as e:
            logger.error(f"Credit check failed: {e}")
            return RuleResult(
                passed=True,  # Fail open for safety
                message=f"Credit check unavailable: {str(e)}",
                severity=RuleSeverity.WARNING
            )
    
    def _get_customer_balance(self, customer_code: str) -> float:
        """Get customer's open invoice balance"""
        try:
            invoices = self.api.get_customer_orders(
                customer_code=customer_code, 
                doc_type="Invoice",
                limit=100
            )
            open_invoices = [inv for inv in invoices if inv.get("DocStatus") != "C"]
            total = sum(float(inv.get("DocTotal", 0)) for inv in open_invoices)
            return total
        except:
            return 0.0
    
    # =========================================================
    # STOCK AVAILABILITY RULES
    # =========================================================
    
    def check_stock_availability(
        self,
        items: List[Dict],
        warehouse: str = None
    ) -> List[RuleResult]:
        """
        Check if items are available in stock
        """
        results = []
        
        for item in items:
            item_code = item.get("ItemCode")
            quantity = float(item.get("Quantity", 1))
            
            # Get stock from inventory report
            stock_info = self._get_item_stock(item_code, warehouse)
            
            if stock_info.get("available", 0) >= quantity:
                results.append(RuleResult(
                    passed=True,
                    message=f"✓ {item_code}: {quantity} available (Stock: {stock_info.get('on_hand', 0)})",
                    severity=RuleSeverity.INFO,
                    data=stock_info
                ))
            else:
                available = stock_info.get("available", 0)
                shortfall = quantity - available
                
                results.append(RuleResult(
                    passed=False,
                    message=f"❌ {item_code}: Insufficient stock. Requested: {quantity}, "
                           f"Available: {available}, Shortfall: {shortfall}",
                    severity=RuleSeverity.BLOCKING if shortfall > 0 else RuleSeverity.WARNING,
                    data={
                        **stock_info,
                        "requested": quantity,
                        "shortfall": shortfall
                    },
                    suggested_action=f"Consider ordering {shortfall} less or check alternative warehouse"
                ))
        
        return results
    
    def _get_item_stock(self, item_code: str, warehouse: str = None) -> Dict:
        """Get stock information for an item"""
        try:
            inventory = self.api.get_inventory_report(search=item_code, limit=1)
            if not inventory:
                return {"on_hand": 0, "available": 0, "warehouse": warehouse}
            
            item = inventory[0]
            
            # Filter by warehouse if specified
            if warehouse:
                # This assumes inventory report includes warehouse filter
                pass
            
            on_hand = float(item.get("CurrentOnHand", 0))
            committed = float(item.get("CurrentIsCommited", 0))
            
            return {
                "on_hand": on_hand,
                "committed": committed,
                "available": on_hand - committed,
                "warehouse": warehouse or item.get("WhsCode", "Unknown")
            }
        except:
            return {"on_hand": 0, "available": 0, "warehouse": warehouse}
    
    # =========================================================
    # APPROVAL THRESHOLD RULES
    # =========================================================
    
    def check_approval_required(
        self,
        doc_type: str,
        amount: float,
        user_role: str
    ) -> RuleResult:
        """
        Check if document requires manager approval
        """
        # Define thresholds per document type and role
        thresholds = {
            "quotation": {"sales_rep": 100000, "manager": 500000},
            "sales_order": {"sales_rep": 100000, "manager": 500000},
            "purchase_order": {"sales_rep": 200000, "manager": 1000000},
            "invoice_discount": {"sales_rep": 10000, "manager": 50000},
        }
        
        doc_thresholds = thresholds.get(doc_type, {"sales_rep": 50000, "manager": 250000})
        user_threshold = doc_thresholds.get(user_role, doc_thresholds["sales_rep"])
        
        if amount > user_threshold:
            return RuleResult(
                passed=False,
                message=f"This {doc_type} exceeds your approval limit of KES {user_threshold:,.2f}. "
                       f"Total: KES {amount:,.2f}. Manager approval required.",
                severity=RuleSeverity.BLOCKING,
                data={"amount": amount, "threshold": user_threshold, "required_role": "manager"},
                suggested_action="Request manager approval or split into smaller documents"
            )
        
        return RuleResult(
            passed=True,
            message=f"✓ Approval not required (within KES {user_threshold:,.2f} limit)",
            severity=RuleSeverity.INFO
        )
    
    # =========================================================
    # PRICE VALIDATION RULES
    # =========================================================
    
    def validate_item_prices(
        self,
        items: List[Dict],
        customer_code: str
    ) -> List[RuleResult]:
        """
        Validate that items have valid prices for the customer
        """
        results = []
        
        for item in items:
            item_code = item.get("ItemCode")
            requested_price = item.get("Price", 0)
            
            # Get correct price from pricing service
            price_result = self.pricing.get_price_for_customer(
                item_code=item_code,
                customer={"CardCode": customer_code}
            )
            
            correct_price = price_result.get("price", 0) if price_result.get("found") else 0
            
            if correct_price <= 0:
                results.append(RuleResult(
                    passed=False,
                    message=f"❌ {item_code}: No price configured for this customer",
                    severity=RuleSeverity.BLOCKING,
                    data={"item_code": item_code}
                ))
            elif abs(requested_price - correct_price) > 0.01:
                # Price mismatch warning
                results.append(RuleResult(
                    passed=True,
                    message=f"⚠️ {item_code}: Price mismatch. Your price: KES {requested_price:,.2f}, "
                           f"System price: KES {correct_price:,.2f}",
                    severity=RuleSeverity.WARNING,
                    data={"requested": requested_price, "correct": correct_price},
                    suggested_action="Use system price or override with approval"
                ))
            else:
                results.append(RuleResult(
                    passed=True,
                    message=f"✓ {item_code}: Price validated (KES {correct_price:,.2f})",
                    severity=RuleSeverity.INFO
                ))
        
        return results


def create_business_rules_engine(user_token: str = None, company_code: str = None) -> BusinessRulesEngine:
    """Factory function for BusinessRulesEngine"""
    return BusinessRulesEngine(user_token=user_token, company_code=company_code)