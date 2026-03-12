import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PricingEngine:
    """
    SAP-style Pricing Intelligence Engine for Leysco100.

    Works with the real PricingService methods:
      - pricing_service.get_price_for_customer(item_code, customer_dict)
      - pricing_service.get_price(item_code, sap_list_num)
      - pricing_service.get_price_any_list(item_code)
      - api_service.get_customer(card_code)

    Price hierarchy (highest → lowest priority):
      1. Customer price list (via PricingService chain walking)
      2. Promotional price   (if pricing_service supports it)
      3. Any available list  (get_price_any_list fallback)
      4. Volume discount applied on top
      5. Manual discount applied on top
    """

    def __init__(self, pricing_service, api_service):
        self.pricing = pricing_service
        self.api     = api_service

    # =========================================================
    # MAIN PRICE CALCULATION
    # =========================================================

    def calculate_price(
        self,
        card_code: Optional[str],
        item_code: str,
        qty: float = 1,
        manual_discount: float = 0,
    ) -> Dict:
        """
        Calculate the final price for an item, optionally for a customer.

        Args:
            card_code:       SAP customer CardCode (e.g. "C001"). None = default pricing.
            item_code:       SAP item code (e.g. "VGM-001").
            qty:             Quantity — used for volume discount calculation.
            manual_discount: Additional manual discount % (0-100).

        Returns:
            dict with keys: item_code, card_code, quantity, currency,
                            price_source, base_price, volume_discount,
                            manual_discount, final_price, line_total, reason
            OR: {"error": "..."} if no price found.
        """

        price_source = "Unknown"
        reason       = []
        currency     = "KES"
        base_price   = None
        price_result = None

        # =====================================================
        # 1. CUSTOMER PRICE LIST (with full chain walking)
        # =====================================================
        if card_code:
            try:
                customer = self.api.get_customer(card_code)

                if customer:
                    price_result = self.pricing.get_price_for_customer(
                        item_code=item_code,
                        customer=customer,
                    )

                    if price_result and price_result.get("found") and price_result.get("price"):
                        base_price   = float(price_result["price"])
                        price_source = f"Customer Price List ({price_result.get('price_list_name', '')})"
                        reason.append(
                            f"Customer price list applied "
                            f"(SAP list {price_result.get('sap_list_num')}: "
                            f"{price_result.get('price_list_name', '')})."
                        )
                        logger.info(f"✅ Customer price found: {base_price} for {card_code}/{item_code}")
                    else:
                        logger.info(f"   Customer {card_code} has no price for {item_code} — trying fallback")

            except Exception as e:
                logger.warning(f"Customer price lookup failed for {card_code}: {e}")

        # =====================================================
        # 2. PROMOTIONAL PRICE
        # =====================================================
        if hasattr(self.pricing, "get_promo_price"):
            try:
                promo = self.pricing.get_promo_price(item_code)

                if promo and promo.get("PromoPrice") is not None:
                    promo_price = float(promo["PromoPrice"])

                    if base_price is None or promo_price < base_price:
                        base_price   = promo_price
                        price_source = "Promotional Price"
                        reason.append("Promotional pricing applied.")
                        logger.info(f"   Promo price applied: {promo_price}")

            except Exception as e:
                logger.warning(f"Promo pricing skipped: {e}")

        # =====================================================
        # 3. ANY AVAILABLE PRICE LIST (fallback)
        # =====================================================
        if base_price is None:
            try:
                fallback = self.pricing.get_price_any_list(item_code)

                if fallback and fallback.get("found") and fallback.get("price"):
                    base_price   = float(fallback["price"])
                    price_source = f"Default Price List ({fallback.get('price_list_name', '')})"
                    reason.append(
                        f"Default price list used "
                        f"({fallback.get('price_list_name', 'Standard')})."
                    )
                    logger.info(f"   Fallback price found: {base_price} from {fallback.get('price_list_name')}")

            except Exception as e:
                logger.warning(f"Fallback price lookup failed for {item_code}: {e}")

        # No price found anywhere
        if base_price is None:
            logger.warning(f"❌ No price found for {item_code} (customer: {card_code})")
            return {"error": f"No price found for item {item_code}."}

        logger.info(f"Base price resolved: {base_price} KES ({price_source})")

        # =====================================================
        # 4. VOLUME DISCOUNT
        # =====================================================
        volume_discount = 0
        if hasattr(self.pricing, "get_volume_discount"):
            try:
                volume_discount = self.pricing.get_volume_discount(item_code, qty) or 0
                if volume_discount > 0:
                    reason.append(f"{volume_discount}% volume discount applied (qty={qty}).")
            except Exception as e:
                logger.warning(f"Volume discount skipped: {e}")

        # =====================================================
        # 5. MANUAL DISCOUNT
        # =====================================================
        if manual_discount > 0:
            reason.append(f"{manual_discount}% manual discount applied.")

        # =====================================================
        # FINAL PRICE CALCULATION
        # =====================================================
        final_price = base_price

        if volume_discount > 0:
            final_price *= (1 - volume_discount / 100)

        if manual_discount > 0:
            final_price *= (1 - manual_discount / 100)

        final_price = round(final_price, 2)
        total       = round(final_price * qty, 2)

        # VAT note
        is_gross = price_result.get("is_gross_price", False) if price_result else False
        if is_gross:
            reason.append("Price includes VAT.")

        return {
            "item_code":        item_code,
            "card_code":        card_code,
            "quantity":         qty,
            "currency":         currency,
            "price_source":     price_source,
            "base_price":       round(base_price, 2),
            "volume_discount":  volume_discount,
            "manual_discount":  manual_discount,
            "final_price":      final_price,
            "line_total":       total,
            "is_gross_price":   is_gross,
            "reason":           " | ".join(reason) if reason else "Standard pricing applied.",
        }