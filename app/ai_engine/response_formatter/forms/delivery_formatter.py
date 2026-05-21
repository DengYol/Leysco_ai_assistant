"""Delivery formatting for outstanding deliveries"""

from typing import Union, List, Dict
from ..base import BaseFormatter


class DeliveryFormatter(BaseFormatter):
    """Formatter for delivery-related responses"""
    
    @classmethod
    def format_outstanding_deliveries(cls, data: Union[dict, list], language: str = "en") -> dict:
        """Format outstanding deliveries with customer grouping."""
        if isinstance(data, dict):
            deliveries = data.get('deliveries') or data.get('data') or data.get('items') or []
        elif isinstance(data, list):
            deliveries = data
        else:
            deliveries = []

        if not deliveries:
            msg = cls._get_no_results_message("GET_OUTSTANDING_DELIVERIES", language)
            return {"message": msg, "data": []}

        sample = deliveries[0] if deliveries else {}

        doc_id_fields = ['doc_num', 'document_number', 'doc_id', 'id', 'DocNum']
        customer_fields = ['customer_name', 'customer', 'CardName', 'customer_name_display', 'CustomerName']
        item_fields = ['item_code', 'ItemCode', 'product_code', 'item_name', 'ItemName']
        quantity_fields = ['pending_quantity', 'quantity', 'open_quantity', 'qty', 'PendingQuantity']
        value_fields = ['total_value', 'value', 'amount', 'DocTotal', 'TotalValue']

        doc_field = next((f for f in doc_id_fields if f in sample), 'doc_num')
        cust_field = next((f for f in customer_fields if f in sample), 'customer_name')
        item_field = next((f for f in item_fields if f in sample), 'item_code')
        qty_field = next((f for f in quantity_fields if f in sample), 'pending_quantity')
        val_field = next((f for f in value_fields if f in sample), 'total_value')

        by_document = {}
        by_customer = {}

        for item in deliveries:
            doc_id = str(item.get(doc_field, 'Unknown'))
            customer = item.get(cust_field, 'Unknown')

            if doc_id not in by_document:
                by_document[doc_id] = {
                    'customer': customer,
                    'items': [],
                    'total_value': 0,
                    'doc_date': item.get('doc_date', item.get('DocDate', '')),
                    'status': item.get('status', 'Outstanding')
                }
            by_document[doc_id]['items'].append(item)
            by_document[doc_id]['total_value'] += float(item.get(val_field, 0))

            if customer not in by_customer:
                by_customer[customer] = {
                    'documents': set(),
                    'items': [],
                    'total_value': 0
                }
            by_customer[customer]['documents'].add(doc_id)
            by_customer[customer]['items'].append(item)
            by_customer[customer]['total_value'] += float(item.get(val_field, 0))

        for customer in by_customer:
            by_customer[customer]['document_count'] = len(by_customer[customer]['documents'])
            del by_customer[customer]['documents']

        total_docs = len(by_document)
        total_items = len(deliveries)
        total_value = sum(float(d.get(val_field, 0)) for d in deliveries)
        overdue_count = sum(1 for d in deliveries if d.get('is_overdue', False))

        opener = cls._get_opener("GET_OUTSTANDING_DELIVERIES", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📦 **Muhtasari wa Usafirishaji Uliobaki: Hati {total_docs}**")
            lines.append(f"• Bidhaa {total_items} kwa jumla")
            lines.append(f"• Thamani jumla: KES {total_value:,.2f}")
            lines.append("")
            if overdue_count > 0:
                lines.append(f"⚠️ Tahadhari: {overdue_count} ya bidhaa zimechelewa kusafirishwa!")
                lines.append("")
            lines.append("**Maelezo kwa Wateja:**")
            lines.append("")
            for idx, (customer, cust_data) in enumerate(list(by_customer.items())[:5], 1):
                lines.append(f"{idx}. **{customer}**")
                doc_word = "hati" if cust_data['document_count'] == 1 else "hati"
                lines.append(f"   📄 {cust_data['document_count']} {doc_word}")
                lines.append(f"   💰 KES {cust_data['total_value']:,.2f}")
                for item in cust_data['items'][:3]:
                    item_code = item.get(item_field, 'N/A')
                    qty = item.get(qty_field, 0)
                    lines.append(f"   • {item_code}: {qty:,.0f} vitengo")
                if len(cust_data['items']) > 3:
                    lines.append(f"   • ... na {len(cust_data['items']) - 3} bidhaa nyingine")
                lines.append("")
            if len(by_customer) > 5:
                remaining = len(by_customer) - 5
                lines.append(f"📋 Na wateja wengine {remaining} wenye usafirishaji uliobaki.")
                lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            doc_word = "document" if total_docs == 1 else "documents"
            lines.append(f"📦 **Outstanding Deliveries Summary: {total_docs} {doc_word}**")
            lines.append(f"• {total_items} line items total")
            lines.append(f"• Total value: KES {total_value:,.2f}")
            lines.append("")
            if overdue_count > 0:
                lines.append(f"⚠️ Alert: {overdue_count} item(s) are overdue for delivery!")
                lines.append("")
            lines.append("**Details by Customer:**")
            lines.append("")
            for idx, (customer, cust_data) in enumerate(list(by_customer.items())[:5], 1):
                lines.append(f"{idx}. **{customer}**")
                doc_word = "document" if cust_data['document_count'] == 1 else "documents"
                lines.append(f"   📄 {cust_data['document_count']} {doc_word}")
                lines.append(f"   💰 KES {cust_data['total_value']:,.2f}")
                for item in cust_data['items'][:3]:
                    item_code = item.get(item_field, 'N/A')
                    qty = item.get(qty_field, 0)
                    lines.append(f"   • {item_code}: {qty:,.0f} units")
                if len(cust_data['items']) > 3:
                    lines.append(f"   • ... and {len(cust_data['items']) - 3} more items")
                lines.append("")
            if len(by_customer) > 5:
                remaining = len(by_customer) - 5
                lines.append(f"📋 Plus {remaining} more customer(s) with outstanding deliveries.")
                lines.append("")

        lines.append(cls._get_tip("GET_OUTSTANDING_DELIVERIES", language))
        lines.append(cls._get_closer(language))

        return {
            "message": "\n".join(lines),
            "data": deliveries,
            "summary": {
                "total_documents": total_docs,
                "total_items": total_items,
                "total_value": total_value,
                "customers_affected": len(by_customer),
                "overdue_count": overdue_count
            }
        }