"""Customer handler for customer-related operations"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from app.services.customer_health_service import create_customer_health_service

logger = logging.getLogger(__name__)


class CustomerHandler:
    """Handles customer-related operations including health and churn risk"""

    def __init__(self, api, pricing_service, warehouse_service):
        self.api = api
        self.pricing = pricing_service
        self.warehouse = warehouse_service
        self.router = None
        self._health_service = None

    @property
    def health_service(self):
        """Lazy load health service — always source token from self.api first."""
        if self._health_service is None:
            # self.api is a LeyscoAPIService instance and already holds the
            # resolved user token.  Fall back to self.router only if needed.
            token = (
                getattr(self.api, "user_token", None)
                or (getattr(self.router, "user_token", None) if self.router else None)
            )
            company_code = (
                getattr(self.api, "company_code", None)
                or (getattr(self.router, "company_code", None) if self.router else None)
            )
            self._health_service = create_customer_health_service(
                user_token=token,
                company_code=company_code,
            )
        return self._health_service

    # ------------------------------------------------------------------
    # Public handlers
    # ------------------------------------------------------------------

    def handle_get_customers(self, entities: Dict, message: str, language: str = "en") -> Dict:
        """Get list of customers"""
        try:
            customers = self._fetch_customers()

            if not customers:
                return {
                    "message": (
                        "No customers found."
                        if language == "en"
                        else "Hakuna wateja waliopatikana."
                    ),
                    "data": [],
                }

            customer_name = entities.get("customer_name")
            if customer_name:
                customers = [
                    c for c in customers
                    if customer_name.lower() in c.get("CardName", "").lower()
                ]

            limit = entities.get("quantity", 10)
            customers = customers[:limit]

            if language == "sw":
                message_text = f"Wateja {len(customers)} wamepatikana."
            else:
                message_text = f"Found {len(customers)} customers."

            if customers:
                message_text += "\n\n"
                for i, customer in enumerate(customers[:10], 1):
                    card_name = customer.get("CardName", "Unknown")
                    card_code = customer.get("CardCode", "N/A")
                    message_text += f"{i}. {card_name} (ID: {card_code})\n"

            return {"message": message_text, "data": customers}

        except Exception as e:
            logger.error(f"Error fetching customers: {e}", exc_info=True)
            return {
                "message": "Failed to fetch customers. Please try again.",
                "data": [],
            }

    def handle_get_customer_health(self, entities: Dict, message: str, language: str = "en") -> Dict:
        """Get customer health and churn risk analysis using CustomerHealthService"""
        try:
            logger.info("=" * 60)
            logger.info("CUSTOMER HEALTH ANALYSIS START")
            logger.info(f"Entities: {entities}")
            logger.info(f"Message: {message}")

            customers = self._fetch_customers()
            logger.info(f"Fetched {len(customers) if customers else 0} customers")

            if not customers:
                logger.warning("No customers found - check API connection")
                return {
                    "message": (
                        "No customers found for health analysis."
                        if language == "en"
                        else "Hakuna wateja wa uchambuzi wa afya."
                    ),
                    "data": [],
                }

            for i, customer in enumerate(customers[:3]):
                logger.info(
                    f"Customer {i + 1}: {customer.get('CardCode')} - {customer.get('CardName')}"
                )

            # ====================================================================
            # FIX: Determine how many customers we need to analyze
            # ====================================================================
            # Get limit from entities with proper default
            limit = entities.get("quantity")
            
            # Ensure limit is an integer with default
            if limit is None:
                limit = 10
                logger.info("No limit provided, using default: 10")
            else:
                try:
                    limit = int(limit)
                    logger.info(f"Using provided limit: {limit}")
                except (ValueError, TypeError):
                    limit = 10
                    logger.info(f"Invalid limit value, using default: 10")
            
            # Check if this is a risk/churn query
            is_risk_query = any(keyword in message.lower() for keyword in [
                "risk", "churn", "at risk", "churning", "leaving", 
                "unhealthy", "health", "danger", "warning"
            ])
            
            # Determine how many customers to analyze
            # For risk queries, analyze more to find at-risk ones
            if is_risk_query:
                analyze_count = min(len(customers), max(30, limit * 3))
            else:
                analyze_count = min(len(customers), limit)
            
            # Hard safety cap to prevent timeout
            analyze_count = min(analyze_count, 50)
            
            logger.info(
                f"Analyzing {analyze_count} of {len(customers)} customers "
                f"(limit={limit}, risk_query={is_risk_query})"
            )

            customer_health = []
            for customer in customers[:analyze_count]:
                card_code = customer.get("CardCode")
                card_name = customer.get("CardName", "Unknown")

                if not card_code:
                    continue

                try:
                    logger.info(f"Analyzing customer: {card_code} - {card_name}")

                    health_data = self.health_service.score(
                        customer_code=card_code,
                        customer_name=card_name,
                    )

                    logger.info(
                        f"Health data for {card_code}: "
                        f"score={health_data.get('score')}, grade={health_data.get('grade')}"
                    )

                    if health_data and not health_data.get("error"):
                        grade = health_data.get("grade", "Unknown")
                        risk_score = health_data.get("score", 0)

                        if grade == "Critical":
                            risk_level = "Critical"
                        elif grade == "At Risk":
                            risk_level = "High"
                        elif grade == "Fair":
                            risk_level = "Medium"
                        elif grade in ("Good", "Excellent"):
                            risk_level = "Low"
                        else:
                            risk_level = "Healthy"

                        signals = health_data.get("signals", {})
                        recency = signals.get("recency", {})
                        frequency = signals.get("frequency", {})

                        customer_health.append(
                            {
                                "customer_id": card_code,
                                "customer_name": card_name,
                                "risk_score": risk_score,
                                "risk_level": risk_level,
                                "grade": grade,
                                "emoji": health_data.get("emoji", "🟢"),
                                "days_since_last_order": recency.get("days_since_order"),
                                "total_orders": frequency.get("orders_90d", 0),
                                "total_spent": 0,
                                "recommendations": health_data.get("recommendations", []),
                                "signals": signals,
                            }
                        )
                    else:
                        logger.warning(f"Health service failed for {card_code}")
                        customer_health.append(
                            self._calculate_customer_health_fallback(customer, {})
                        )

                except Exception as e:
                    logger.error(f"Error analyzing customer {card_code}: {e}")
                    customer_health.append(
                        self._calculate_customer_health_fallback(customer, {})
                    )

            # ====================================================================
            # Filter to at-risk customers when query is about churn / risk
            # ====================================================================
            if is_risk_query:
                customer_health = [
                    c for c in customer_health
                    if c["risk_level"] in ("Critical", "High", "Medium")
                ]
                
                # Sort by risk score (highest risk first)
                customer_health.sort(key=lambda x: x["risk_score"], reverse=True)
                
                # Limit results
                customer_health = customer_health[:limit]

            logger.info(f"Found {len(customer_health)} at-risk customers")

            if not customer_health:
                if is_risk_query:
                    return {
                        "message": (
                            "✅ No customers are currently at risk of churning. All customers are in good health!"
                            if language == "en"
                            else "✅ Hakuna wateja walio katika hatari ya kuondoka. Wateja wote wako katika hali nzuri!"
                        ),
                        "data": [],
                    }
                else:
                    return {
                        "message": (
                            "No customers at risk found."
                            if language == "en"
                            else "Hakuna wateja walio katika hatari waliopatikana."
                        ),
                        "data": [],
                    }

            formatted_message = self._format_customer_health_response(customer_health, language)

            logger.info("CUSTOMER HEALTH ANALYSIS COMPLETE")
            logger.info("=" * 60)

            return {"message": formatted_message, "data": customer_health}

        except Exception as e:
            logger.error(f"Error in customer health analysis: {e}", exc_info=True)
            return {
                "message": "Failed to analyze customer health. Please try again.",
                "data": [],
            }

    def handle_get_customer_details(self, entities: Dict, message: str, language: str = "en") -> Dict:
        """Get detailed customer information"""
        try:
            customer_name = entities.get("customer_name")
            if not customer_name:
                return {
                    "message": (
                        "Please specify a customer name."
                        if language == "en"
                        else "Tafadhali taja jina la mteja."
                    ),
                    "data": [],
                }

            # Use BusinessPartnerHandler's resolve_customer for best match
            matching = self.api.resolve_customer(customer_name)

            if not matching:
                return {
                    "message": (
                        f"Customer '{customer_name}' not found."
                        if language == "en"
                        else f"Mteja '{customer_name}' hakupatikana."
                    ),
                    "data": [],
                }

            health_data = self.health_service.score(
                customer_code=matching.get("CardCode"),
                customer_name=matching.get("CardName"),
            )

            orders = self._fetch_customer_orders(matching.get("CardCode"))

            total_orders = len(orders)
            total_spent = sum(o.get("DocTotal", 0) for o in orders)
            avg_order_value = total_spent / total_orders if total_orders > 0 else 0

            customer_detail = {
                "CardCode": matching.get("CardCode"),
                "CardName": matching.get("CardName"),
                "PhoneNumber": matching.get("PhoneNumber", "N/A"),
                "EmailAddress": matching.get("EmailAddress", "N/A"),
                "TotalOrders": total_orders,
                "TotalSpent": total_spent,
                "AverageOrderValue": avg_order_value,
                "LastOrderDate": orders[0].get("DocDate") if orders else "Never",
                "HealthScore": health_data.get("score", 0) if health_data else 0,
                "HealthGrade": health_data.get("grade", "Unknown") if health_data else "Unknown",
                "RecentOrders": orders[:5],
            }

            if language == "sw":
                message_text = f"Taarifa za mteja: {customer_detail['CardName']}\n\n"
                message_text += f"Kodi: {customer_detail['CardCode']}\n"
                message_text += f"Simu: {customer_detail['PhoneNumber']}\n"
                message_text += f"Barua pepe: {customer_detail['EmailAddress']}\n"
                message_text += f"Jumla ya oda: {customer_detail['TotalOrders']}\n"
                message_text += f"Jumla ya kiasi: KES {customer_detail['TotalSpent']:,.2f}\n"
                message_text += f"Wastani wa oda: KES {customer_detail['AverageOrderValue']:,.2f}\n"
                message_text += f"Oda ya mwisho: {customer_detail['LastOrderDate']}\n"
                message_text += f"Alama ya afya: {customer_detail['HealthScore']:.1f}/100 ({customer_detail['HealthGrade']})"
            else:
                message_text = f"Customer details for: {customer_detail['CardName']}\n\n"
                message_text += f"Code: {customer_detail['CardCode']}\n"
                message_text += f"Phone: {customer_detail['PhoneNumber']}\n"
                message_text += f"Email: {customer_detail['EmailAddress']}\n"
                message_text += f"Total Orders: {customer_detail['TotalOrders']}\n"
                message_text += f"Total Spent: KES {customer_detail['TotalSpent']:,.2f}\n"
                message_text += f"Average Order Value: KES {customer_detail['AverageOrderValue']:,.2f}\n"
                message_text += f"Last Order: {customer_detail['LastOrderDate']}\n"
                message_text += f"Health Score: {customer_detail['HealthScore']:.1f}/100 ({customer_detail['HealthGrade']})"

            return {"message": message_text, "data": customer_detail}

        except Exception as e:
            logger.error(f"Error fetching customer details: {e}", exc_info=True)
            return {"message": "Failed to fetch customer details.", "data": []}

    def get_customer_orders(
        self, customer_name: str = "", limit: int = 10, language: str = "en"
    ) -> Dict:
        """Get customer orders"""
        try:
            if not customer_name:
                return {
                    "message": (
                        "Please specify a customer name."
                        if language == "en"
                        else "Tafadhali taja jina la mteja."
                    ),
                    "data": [],
                }

            customer = self.api.resolve_customer(customer_name)

            if not customer:
                return {
                    "message": (
                        f"Customer '{customer_name}' not found."
                        if language == "en"
                        else f"Mteja '{customer_name}' hakupatikana."
                    ),
                    "data": [],
                }

            orders = self._fetch_customer_orders(customer.get("CardCode"))
            orders = orders[:limit]

            if language == "sw":
                message_text = f"Oda {len(orders)} za {customer.get('CardName')} zimepatikana."
                if orders:
                    message_text += "\n\n"
                    for i, order in enumerate(orders[:10], 1):
                        doc_num = order.get("DocNum", "N/A")
                        doc_date = order.get("DocDate", "N/A")
                        doc_total = order.get("DocTotal", 0)
                        message_text += f"{i}. Oda #{doc_num} - {doc_date} - KES {doc_total:,.2f}\n"
            else:
                message_text = f"Found {len(orders)} orders for {customer.get('CardName')}."
                if orders:
                    message_text += "\n\n"
                    for i, order in enumerate(orders[:10], 1):
                        doc_num = order.get("DocNum", "N/A")
                        doc_date = order.get("DocDate", "N/A")
                        doc_total = order.get("DocTotal", 0)
                        message_text += f"{i}. Order #{doc_num} - {doc_date} - KES {doc_total:,.2f}\n"

            return {"message": message_text, "data": orders}

        except Exception as e:
            logger.error(f"Error fetching customer orders: {e}", exc_info=True)
            return {"message": "Failed to fetch customer orders.", "data": []}

    def get_customer_invoices(
        self, customer_name: str = "", limit: int = 10, language: str = "en"
    ) -> Dict:
        """Get customer invoices"""
        try:
            if not customer_name:
                return {
                    "message": (
                        "Please specify a customer name."
                        if language == "en"
                        else "Tafadhali taja jina la mteja."
                    ),
                    "data": [],
                }

            customer = self.api.resolve_customer(customer_name)

            if not customer:
                return {
                    "message": (
                        f"Customer '{customer_name}' not found."
                        if language == "en"
                        else f"Mteja '{customer_name}' hakupatikana."
                    ),
                    "data": [],
                }

            invoices = self._fetch_customer_invoices(customer.get("CardCode"))
            invoices = invoices[:limit]

            if language == "sw":
                message_text = f"Ankara {len(invoices)} za {customer.get('CardName')} zimepatikana."
                if invoices:
                    message_text += "\n\n"
                    for i, invoice in enumerate(invoices[:10], 1):
                        doc_num = invoice.get("DocNum", "N/A")
                        doc_date = invoice.get("DocDate", "N/A")
                        doc_total = invoice.get("DocTotal", 0)
                        message_text += f"{i}. Ankara #{doc_num} - {doc_date} - KES {doc_total:,.2f}\n"
            else:
                message_text = f"Found {len(invoices)} invoices for {customer.get('CardName')}."
                if invoices:
                    message_text += "\n\n"
                    for i, invoice in enumerate(invoices[:10], 1):
                        doc_num = invoice.get("DocNum", "N/A")
                        doc_date = invoice.get("DocDate", "N/A")
                        doc_total = invoice.get("DocTotal", 0)
                        message_text += f"{i}. Invoice #{doc_num} - {doc_date} - KES {doc_total:,.2f}\n"

            return {"message": message_text, "data": invoices}

        except Exception as e:
            logger.error(f"Error fetching customer invoices: {e}", exc_info=True)
            return {"message": "Failed to fetch customer invoices.", "data": []}

    # ------------------------------------------------------------------
    # Private data-fetch helpers — all delegate to LeyscoAPIService
    # ------------------------------------------------------------------

    def _fetch_customers(self) -> List[Dict]:
        """
        Fetch customers via LeyscoAPIService.business_partners.
        Uses the correct /bp_masterdata endpoint with auth + pagination.
        Previously this method made raw HTTP calls to hardcoded endpoints
        that all returned 404; now it delegates to the handler that already
        works for every other feature.
        """
        try:
            customers = self.api.get_customers()
            if customers:
                logger.info(f"✅ Fetched {len(customers)} customers via BusinessPartnerHandler")
                return customers

            logger.warning("BusinessPartnerHandler returned 0 customers")
            return []

        except Exception as e:
            logger.error(f"Failed to fetch customers: {e}", exc_info=True)
            return []

    def _fetch_customer_orders(self, card_code: str) -> List[Dict]:
        """Fetch orders for a specific customer via LeyscoAPIService."""
        try:
            orders = self.api.get_customer_orders(customer_code=card_code)
            logger.info(f"Fetched {len(orders)} orders for {card_code}")
            return orders
        except Exception as e:
            logger.error(f"Failed to fetch customer orders for {card_code}: {e}")
            return []

    def _fetch_customer_invoices(self, card_code: str) -> List[Dict]:
        """
        Fetch invoices for a specific customer.
        LeyscoAPIService has no invoice alias yet, so we use the Leysco
        doc-type endpoint directly (doc type 13 = A/R Invoice in SAP B1).
        """
        try:
            url = f"{self.api.base_url}/marketing/docs/13"
            params = {"CardCode": card_code, "page": 1, "per_page": 50}

            resp = self.api.session.get(url, params=params, timeout=30)
            logger.info(f"Invoice fetch status for {card_code}: {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                if data.get("ResultState") and data.get("ResponseData"):
                    response_data = data["ResponseData"]
                    if isinstance(response_data, dict):
                        return response_data.get("data", [])
                    if isinstance(response_data, list):
                        return response_data
            else:
                logger.warning(
                    f"Invoice endpoint returned {resp.status_code} for {card_code}: "
                    f"{resp.text[:300]}"
                )
            return []

        except Exception as e:
            logger.error(f"Failed to fetch customer invoices for {card_code}: {e}")
            return []

    # ------------------------------------------------------------------
    # Fallback health calculation (used when health service errors)
    # ------------------------------------------------------------------

    def _calculate_customer_health_fallback(self, customer: Dict, sales_data: Dict) -> Dict:
        """Fallback: return a neutral health record when the health service fails."""
        return {
            "customer_id": customer.get("CardCode"),
            "customer_name": customer.get("CardName", "Unknown"),
            "risk_score": 50,
            "risk_level": "Medium",
            "grade": "Unknown",
            "emoji": "🟡",
            "days_since_last_order": None,
            "total_orders": 0,
            "total_spent": 0,
            "recommendations": ["Unable to fetch full health data. Using basic analysis."],
            "signals": {},
        }

    # ------------------------------------------------------------------
    # Response formatter
    # ------------------------------------------------------------------

    def _format_customer_health_response(self, customers: List[Dict], language: str = "en") -> str:
        """Format customer health response"""
        if not customers:
            return (
                "Hakuna wateja walio katika hatari waliopatikana."
                if language == "sw"
                else "No customers at risk found."
            )

        lines = ["🏥 Customer Health & Churn Risk Analysis", ""]

        critical = [c for c in customers if c.get("risk_level") == "Critical"]
        high = [c for c in customers if c.get("risk_level") == "High"]
        medium = [c for c in customers if c.get("risk_level") == "Medium"]

        if critical:
            lines.append("🔴 **Critical Risk - Immediate Action Required**")
            lines.append("")
            for customer in critical:
                emoji = customer.get("emoji", "🔴")
                lines.append(f"{emoji} • **{customer['customer_name']}**")
                lines.append(f"  Risk Score: {customer['risk_score']}/100")
                if customer.get("days_since_last_order"):
                    lines.append(f"  Last order: {customer['days_since_last_order']} days ago")
                lines.append(f"  Total orders: {customer['total_orders']}")
                for rec in customer.get("recommendations", [])[:2]:
                    lines.append(f"  💡 {rec}")
                lines.append("")

        if high:
            lines.append("🟠 **High Risk - Needs Attention**")
            lines.append("")
            for customer in high:
                emoji = customer.get("emoji", "🟠")
                lines.append(f"{emoji} • **{customer['customer_name']}**")
                lines.append(f"  Risk Score: {customer['risk_score']}/100")
                if customer.get("days_since_last_order"):
                    lines.append(f"  Last order: {customer['days_since_last_order']} days ago")
                lines.append("")

        if medium:
            lines.append("🟡 **Medium Risk - Monitor Closely**")
            lines.append("")
            for customer in medium:
                emoji = customer.get("emoji", "🟡")
                lines.append(f"{emoji} • **{customer['customer_name']}**")
                lines.append(f"  Risk Score: {customer['risk_score']}/100")
                lines.append("")

        lines.append("")
        lines.append("💡 **Recommendations:**")
        lines.append("• Reach out to critical/high risk customers with special offers")
        lines.append("• Review order history to identify drop-off patterns")
        lines.append("• Consider loyalty programs for medium risk customers")

        return "\n".join(lines)