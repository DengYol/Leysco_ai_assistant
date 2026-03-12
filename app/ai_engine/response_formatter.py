import logging

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """
    Converts raw system responses into natural, conversational text
    AND preserves structured list data for the mobile app UI.
    """

    MAX_RESULTS = 5

    # -------------------------------------------------
    @staticmethod
    def _extract_list(data):
        if isinstance(data, dict):

            if "error" in data:
                return "error", data["error"]

            response = data.get("ResponseData")

            if isinstance(response, list):
                return "list", response

            if isinstance(response, dict) and "data" in response:
                return "list", response["data"]

            return "list", []

        if isinstance(data, list):
            return "list", data

        return "error", "Invalid data format"

    # -------------------------------------------------
    @staticmethod
    def _format_price(value):
        try:
            return f"{float(value):,.2f}"
        except Exception:
            return value or "0.00"

    # -------------------------------------------------
    @staticmethod
    def _not_available(msg="That information is not available in Leysco right now."):
        return {"message": msg, "data": []}

    # =================================================
    # 🔥 FIX FOR SERVER CRASH (alias method added)
    # =================================================
    @staticmethod
    def format_prices(data: dict) -> dict:
        """Alias to prevent crash from old router call"""
        return ResponseFormatter.format_item_price(data)

    # =================================================
    # ITEM PRICE
    # =================================================
    @staticmethod
    def format_item_price(data: dict) -> dict:
        if not data or "item" not in data:
            return ResponseFormatter._not_available("I couldn’t find that item in Leysco.")

        item = data.get("item", {})
        prices = data.get("prices", [])
        uom = data.get("uom", "Unit")

        item_name = item.get("ItemName") or item.get("full_name") or "Unknown Item"
        item_code = item.get("ItemCode", "")

        if not prices:
            return {
                "message": f"I found {item_name} ({item_code}) but no price list data is available.",
                "data": []
            }

        lines = []
        structured = []

        for p in prices[:ResponseFormatter.MAX_RESULTS]:
            list_name = p.get("ListName", "Price List")
            price = ResponseFormatter._format_price(p.get("Price"))
            currency = p.get("Currency", "KES")

            lines.append(f"{list_name}: {price} {currency} per {uom}")

            structured.append({
                "price_list": list_name,
                "price": price,
                "currency": currency,
                "uom": uom
            })

        return {
            "message": f"Here are the prices for {item_name} ({item_code}):\n" + "\n".join(lines),
            "data": structured
        }
    
    

    # -------------------------------------------------
    @staticmethod
    def format_customer(data) -> dict:
        status, payload = ResponseFormatter._extract_list(data)

        if status == "error":
            return ResponseFormatter._not_available(payload)

        if not payload:
            return ResponseFormatter._not_available("I couldn’t find that customer.")

        customers = payload[:ResponseFormatter.MAX_RESULTS]

        lines = [
            f"{c.get('CardName', 'N/A')} (Code: {c.get('CardCode', 'N/A')})"
            for c in customers if isinstance(c, dict)
        ]

        return {
            "message": "Here are the matching customers:\n" + "\n".join(lines),
            "data": customers
        }

    # -------------------------------------------------
    @staticmethod
    def format_stock(data: dict) -> dict:
        if "error" in data or data.get("stock") is None:
            return ResponseFormatter._not_available()

        return {
            "message": f"We currently have {data.get('stock')} units of {data.get('item_name')} available.",
            "data": []
        }

    # -------------------------------------------------
    @staticmethod
    def format_list(title: str, data) -> dict:
        status, payload = ResponseFormatter._extract_list(data)

        if status == "error":
            return ResponseFormatter._not_available(payload)

        if not payload:
            return ResponseFormatter._not_available(f"I couldn’t find any {title}.")

        limited = payload[:ResponseFormatter.MAX_RESULTS]

        if title == "items":
            lines = [
                f"{i.get('ItemName', 'N/A')} ({i.get('ItemCode', 'N/A')}) — Stock: {i.get('OnHand', 'N/A')}"
                for i in limited if isinstance(i, dict)
            ]
            return {"message": "Here are the matching items:\n" + "\n".join(lines), "data": limited}

        if title == "customers":
            return ResponseFormatter.format_customer(data)

        return {"message": f"I found some {title}.", "data": limited}

    # -------------------------------------------------
    @staticmethod
    def format_sales_orders(data: list) -> dict:
        if not data:
            return {"message": "No sales orders found.", "data": []}

        lines = []
        structured = []

        for idx, item in enumerate(data[:ResponseFormatter.MAX_RESULTS], 1):
            if isinstance(item, dict):
                name = item.get("name") or item.get("ItemName") or "N/A"
                warehouse = item.get("warehouse") or item.get("Warehouse") or "N/A"
            else:
                name = str(item)
                warehouse = "N/A"

            lines.append(f"{idx}. {name} (Warehouse: {warehouse})")
            structured.append({"name": name, "warehouse": warehouse})

        return {
            "message": f"Found {len(data)} recent sales orders:\n" + "\n".join(lines),
            "data": structured
        }
    
    @staticmethod
    def format_customer_activity(summary: dict, engagement: str) -> dict:
     """
     Formats customer activity when no orders are found.
     Shows engagement level and document counts.
     """

     invoices = summary.get("invoices", [])
     deliveries = summary.get("deliveries", [])
     quotations = summary.get("quotations", [])

     message_lines = [
         "No recent sales orders found.",
         "",
         f"📊 Engagement Level: {engagement}",
         "",
         "📈 Customer Activity Summary",
         f"🧾 Invoices: {len(invoices)}",
         f"🚚 Deliveries: {len(deliveries)}",
         f"📝 Quotations: {len(quotations)}",
     ]

     return {
         "message": "\n".join(message_lines),
         "data": summary
     }


    # -------------------------------------------------
    @staticmethod
    def format_recommended_items(data: list) -> str:
        """Format recommended items for frontend or API response."""
        if not data:
            return "No item recommendations available."

        formatted_text = f"Top {min(len(data), ResponseFormatter.MAX_RESULTS)} recommended items:\n"
        for idx, item in enumerate(data[:ResponseFormatter.MAX_RESULTS], 1):
            if isinstance(item, dict):
                name = item.get("ItemName") or item.get("name") or "N/A"
                code = item.get("ItemCode") or item.get("code") or "N/A"
            else:
                name = str(item)
                code = "N/A"

            formatted_text += f"{idx}. {name} (Code: {code})\n"

        return formatted_text

    # -------------------------------------------------
    @staticmethod
    def format_recommended_customers(data: list) -> str:
        """Format recommended customers for frontend or API response."""
        if not data:
            return "No customer recommendations available."

        formatted_text = f"Top {min(len(data), ResponseFormatter.MAX_RESULTS)} recommended customers:\n"
        for idx, cust in enumerate(data[:ResponseFormatter.MAX_RESULTS], 1):
            if isinstance(cust, dict):
                name = cust.get("CardName") or cust.get("name") or "N/A"
                code = cust.get("CardCode") or cust.get("code") or "N/A"
            else:
                name = str(cust)
                code = "N/A"

            formatted_text += f"{idx}. {name} (Code: {code})\n"

        return formatted_text
    
   

    @staticmethod
    def format_quotations(quotations, customer_name: str | None = None) -> dict:
        """
        Formats quotation data into readable text.
        Optionally filters by customer.
        """

        # 🔹 Case 1: None or empty
        if not quotations:
            return {"message": "No quotations found.", "data": []}

        # 🔹 Case 2: API returned error string
        if isinstance(quotations, str):
            return {"message": quotations, "data": []}

        # 🔹 Case 3: SAP wrapper
        if isinstance(quotations, dict):
            quotations = quotations.get("value") or quotations.get("data") or []

        # 🔹 Case 4: list contains strings
        if isinstance(quotations, list) and quotations and isinstance(quotations[0], str):
            return {"message": "\n".join(quotations), "data": quotations}

        if not quotations:
            return {"message": "No quotations found.", "data": []}

        # ✅ FILTER BY CUSTOMER (if provided)
        if customer_name:
            quotations = [
                q for q in quotations
                if customer_name.lower() in str(q.get("CardName", "")).lower()
            ]

            if not quotations:
                return {
                    "message": f"No quotations found for {customer_name}.",
                    "data": []
                }

        text = f"📄 Quotations ({len(quotations)} found):\n\n"

        grand_total = 0

        for i, q in enumerate(quotations, start=1):
            total = float(q.get("DocTotal", 0))
            grand_total += total

            text += (
                f"{i}. Quotation No: {q.get('DocNum', 'N/A')}\n"
                f"   Date: {q.get('DocDate', 'N/A')}\n"
                f"   Customer: {q.get('CardName', 'N/A')}\n"
                f"   Total: {total:,.2f} KES\n"
                f"   Status: {q.get('DocStatus', 'N/A')}\n\n"
            )

        text += f"💰 Grand Total: {grand_total:,.2f} KES"

        return {
            "message": text,
            "data": quotations
        }

    # =================================================
    # UPDATED: CROSS-SELL FORMATTER (handles both naming conventions)
    # =================================================
    @staticmethod
    def format_cross_sell(data: dict) -> dict:
        """
        Format cross-sell recommendations.
        Expected data structure from recommendation_service:
        {
            "item_name": "Syova Watermelon Sukari F1",
            "recommendations": [
                {
                    "ItemName": "SACK - FERTILIZER BAGS 2kg PRINTED",
                    "ItemCode": "RMSA0009",
                    "Reason": "Commonly purchased with syova watermelon sukari f1",
                    "Price": null,
                    "StockStatus": "✅ In Stock"
                },
                ...
            ]
        }
        Also handles lowercase field names as fallback.
        """
        if not data or not isinstance(data, dict):
            return ResponseFormatter._not_available("I couldn't find any cross-sell recommendations.")
        
        item_name = data.get("item_name", "this item")
        recommendations = data.get("recommendations", [])
        
        if not recommendations:
            return {
                "message": f"I couldn't find any items commonly purchased with {item_name}.",
                "data": []
            }
        
        # Build the message
        lines = [f"**Customers who bought {item_name} also bought:**"]
        
        for idx, item in enumerate(recommendations[:ResponseFormatter.MAX_RESULTS], 1):
            # Handle both uppercase and lowercase field names
            name = (item.get("ItemName") or item.get("name") or "Unknown Item")
            item_code = (item.get("ItemCode") or item.get("item_code") or "")
            price = item.get("Price") or item.get("price")
            reason = item.get("Reason") or item.get("reason") or ""
            stock_status = item.get("StockStatus") or item.get("stock_status") or ""
            stock = item.get("stock", 0)
            
            # Format display name with code if available
            display_name = name
            if item_code:
                display_name = f"{name} ({item_code})"
            
            lines.append(f"{idx}. **{display_name}**")
            
            # Add price info if available
            if price:
                if isinstance(price, (int, float)) and price > 0:
                    lines.append(f"   💰 Price: {ResponseFormatter._format_price(price)} KES")
                else:
                    lines.append(f"   ⚠️ Price: Bei haijulikani")
            else:
                lines.append(f"   ⚠️ Price: Bei haijulikani")
            
            # Add reason if available
            if reason:
                lines.append(f"   💡 Reason: {reason}")
            
            # Add stock status - use StockStatus first, then calculate from stock
            if stock_status:
                lines.append(f"   {stock_status}")
            elif stock <= 0:
                lines.append(f"   ⚠️ Status: ⚠️ Out of Stock")
            elif stock > 0:
                lines.append(f"   ✅ Status: In Stock ({stock} units)")
            
            lines.append("")  # Empty line between items
        
        # Add tip if there are recommendations
        if recommendations:
            lines.append("💡 **Tip:** Bundle these items together and save 10%! Let me know if you need help!")
        
        return {
            "message": "\n".join(lines).strip(),
            "data": recommendations
        }


    # -------------------------------------------------
    @staticmethod
    def format_generic_error(data: dict) -> dict:
        return ResponseFormatter._not_available(data.get('error', 'Something went wrong while checking the system.'))