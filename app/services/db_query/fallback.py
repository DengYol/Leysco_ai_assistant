"""Fallback data generators for when API calls fail"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_fallback_inventory_report() -> list:
    """Generate fallback inventory data when API times out"""
    logger.info("Using fallback inventory report data")
    return [
        {"ItemCode": "SAMPLE001", "ItemName": "Sample Product A", "CurrentOnHand": 150, "CurrentIsCommited": 25, "WhsCode": "MAIN"},
        {"ItemCode": "SAMPLE002", "ItemName": "Sample Product B", "CurrentOnHand": 45, "CurrentIsCommited": 10, "WhsCode": "MAIN"},
        {"ItemCode": "SAMPLE003", "ItemName": "Sample Product C", "CurrentOnHand": 8, "CurrentIsCommited": 2, "WhsCode": "MAIN"}
    ]


def get_fallback_warehouses() -> list:
    """Generate fallback warehouse data when API fails"""
    logger.info("Using fallback warehouse data")
    return [
        {"WhsCode": "WH001", "WhsName": "Nairobi Main Warehouse", "City": "Nairobi", "County": "Nairobi", "Country": "Kenya", "Status": "Active"},
        {"WhsCode": "WH002", "WhsName": "Mombasa Distribution Center", "City": "Mombasa", "County": "Mombasa", "Country": "Kenya", "Status": "Active"},
        {"WhsCode": "WH003", "WhsName": "Kisumu Regional Hub", "City": "Kisumu", "County": "Kisumu", "Country": "Kenya", "Status": "Active"},
        {"WhsCode": "WH004", "WhsName": "Eldoret Store", "City": "Eldoret", "County": "Uasin Gishu", "Country": "Kenya", "Status": "Active"},
        {"WhsCode": "WH005", "WhsName": "Nakuru Warehouse", "City": "Nakuru", "County": "Nakuru", "Country": "Kenya", "Status": "Active"},
    ]


def get_fallback_sales_analytics() -> list:
    """Generate fallback sales analytics data when API fails"""
    logger.info("Using fallback sales analytics data")
    return [
        {
            "analysis_type": "sales_analytics",
            "period": "last_30_days",
            "summary": {
                "total_revenue": 1250000,
                "total_transactions": 342,
                "average_order_value": 3654.97,
                "unique_customers": 156,
                "total_items_sold": 1250
            },
            "trends": {
                "revenue_change": "+12.5%",
                "transactions_change": "+8.2%",
                "customers_change": "+5.6%"
            },
            "top_products": [
                {"name": "Vegimax 250ml", "quantity": 245, "revenue": 73500},
                {"name": "Easeed 1kg", "quantity": 180, "revenue": 54000},
                {"name": "Tosheka 500ml", "quantity": 156, "revenue": 46800}
            ],
            "is_fallback": True,
            "message": "Sales analytics data (sample data - API connection in progress)"
        }
    ]


def get_fallback_deliveries() -> list:
    """Generate fallback deliveries data when API fails"""
    logger.info("Using fallback deliveries data")
    return [
        {
            "DocNum": "DEL001",
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocDueDate": (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"),
            "CardCode": "CUST001",
            "CardName": "Sample Customer",
            "Status": "Pending",
            "IsOverdue": False,
            "CompletionPercentage": 0,
            "Items": [
                {
                    "ItemCode": "ITEM001",
                    "ItemName": "Sample Product",
                    "Quantity": 100,
                    "OpenQty": 100,
                    "DeliveredQty": 0,
                    "Price": 500,
                    "Value": 50000
                }
            ],
            "TotalOutstanding": 50000,
            "ItemCount": 1,
            "is_fallback": True,
            "message": "Sample delivery data - real API connection in progress"
        }
    ]


def get_fallback_turnover_data() -> list:
    """Generate fallback turnover data when API times out"""
    logger.info("Using fallback turnover data")
    return [
        {"ItemCode": "SAMPLE001", "TurnoverRate": 4.5},
        {"ItemCode": "SAMPLE002", "TurnoverRate": 2.3},
        {"ItemCode": "SAMPLE003", "TurnoverRate": 1.2}
    ]


def get_fallback_slow_products() -> list:
    """Generate fallback slow products data when API times out"""
    logger.info("Using fallback slow products data")
    return [
        {"ItemCode": "SLOW001", "ItemName": "Slow Moving Item X", "TurnoverRate": 0.3},
        {"ItemCode": "SLOW002", "ItemName": "Slow Moving Item Y", "TurnoverRate": 0.5}
    ]