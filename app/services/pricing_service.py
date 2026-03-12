"""
pricing_service.py
==================
SAP B1-style pricing for Leysco.

Pricing hierarchy (highest → lowest priority):
  1. Customer's assigned price list  (octg.ListNum)
  2. Base price list chain           (BASE_NUM walking)
  3. Default price list              (ListNum = 1)

Key behaviours mirrored from SAP B1:
  - Price list chaining via BASE_NUM
  - Price = 0 means "not priced on this list" → fall back
  - isGrossPrc = "Y" → price already includes VAT
  - UomEntry reported alongside price
  - API id ≠ SAP ListNum — we maintain a map at startup
"""

import logging
from typing import Dict, List, Optional, Tuple

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
DEFAULT_SAP_LIST_NUM = 1          # fallback if customer has no list assigned
MAX_CHAIN_DEPTH      = 10         # safety limit for BASE_NUM walking

# Non-EA price lists (api_ids 23-34) all return 500.
# Map each broken SAP ListNum to its working EA equivalent.
# e.g. customer on ListNum=1 'Price List 01' → try ListNum=26 'Price List 01 - EA'
NON_EA_TO_EA_FALLBACK = {
    1:  26,   # Price List 01       → Price List 01 - EA
    2:  18,   # RETAIL PRICELIST    → RETAIL PRICELIST - EA
    3:  19,   # DISTRIBUTOR         → DISTRIBUTOR - EA
    4:  20,   # INTERCOMPANY        → INTERCOMPANY - EA
    5:  21,   # WHOLESALE           → WHOLESALE - EA
    6:  22,   # MD PRICE            → MD PRICE - EA
    10: 17,   # Price List 10       → Price List 10 - EA
}
PRICE_LIST_SEARCH_TIMEOUT = 20    # seconds


# ---------------------------------------------------------------------------
# PricingService
# ---------------------------------------------------------------------------
class PricingService:
    """
    Resolves item prices following the SAP B1 pricing hierarchy.

    Usage:
        svc   = PricingService()
        result = svc.get_price(item_code="FGHY0478", sap_list_num=17)
        result = svc.get_price_for_customer(item_code="FGHY0478",
                                             customer=customer_dict)
    """

    def __init__(self):
        self.base_url = settings.LEYSCO_API_BASE_URL.rstrip("/")
        self.session  = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {settings.LEYSCO_API_TOKEN}",
            "Content-Type":  "application/json",
        })

        # Built once per service lifetime — refreshed by calling _build_maps()
        # sap_list_num (int) → price list dict (contains id, BASE_NUM, isGrossPrc …)
        self._list_by_sap_num: Dict[int, Dict] = {}
        # api_id (int) → price list dict
        self._list_by_api_id:  Dict[int, Dict] = {}

        self._build_maps()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def get_price_for_customer(
        self,
        item_code: str,
        customer: Dict,
    ) -> Dict:
        """
        Resolve the price of item_code for a given customer dict.

        The customer dict must contain either:
          - customer["PriceListNum"]   (direct field, often null)
          - customer["octg"]["ListNum"] (from payment group — more reliable)

        Returns a result dict — never raises.
        """
        sap_list_num = self._customer_list_num(customer)
        return self.get_price(item_code=item_code, sap_list_num=sap_list_num)

    def get_price(
        self,
        item_code: str,
        sap_list_num: int = DEFAULT_SAP_LIST_NUM,
    ) -> Dict:
        """
        Walk the price list chain starting at sap_list_num until a
        non-zero price is found, then return a rich result dict.

        Result dict keys:
          item_code        str
          price            float | None
          currency         str   ("KES")
          uom_entry        int | None
          is_gross_price   bool  (True = VAT included)
          price_list_id    int   (API id used)
          price_list_name  str
          sap_list_num     int   (SAP ListNum used)
          chain_walked     list  (SAP ListNums tried, in order)
          found            bool
          note             str
        """
        chain_walked: List[int] = []
        current_sap_num         = sap_list_num
        depth                   = 0

        while depth < MAX_CHAIN_DEPTH:
            depth        += 1
            price_list = self._list_by_sap_num.get(current_sap_num)

            # If this SAP ListNum maps to a broken non-EA list,
            # silently redirect to the EA equivalent before fetching
            if price_list:
                api_id = self._to_int(price_list.get('id'))
                ea_sap_num = NON_EA_TO_EA_FALLBACK.get(current_sap_num)
                if ea_sap_num and api_id and api_id >= 23:
                    ea_list = self._list_by_sap_num.get(ea_sap_num)
                    if ea_list:
                        logger.info(
                            f'  Redirecting SAP {current_sap_num} '
                            f'(api_id={api_id}, broken) '
                            f'→ EA equivalent SAP {ea_sap_num} '
                            f'({ea_list.get("ListName")})'
                        )
                        price_list      = ea_list
                        current_sap_num = ea_sap_num

            if not price_list:
                note = (
                    f"SAP list {current_sap_num} not found in price list map. "
                    f"Chain: {chain_walked}"
                )
                logger.warning(note)
                break

            chain_walked.append(current_sap_num)
            api_id = price_list["id"]

            price, uom_entry = self._fetch_price(api_id, item_code)

            if price is not None and price > 0:
                return {
                    "item_code":       item_code,
                    "price":           price,
                    "currency":        "KES",
                    "uom_entry":       uom_entry,
                    "is_gross_price":  price_list.get("isGrossPrc") == "Y",
                    "price_list_id":   api_id,
                    "price_list_name": price_list.get("ListName", ""),
                    "sap_list_num":    current_sap_num,
                    "chain_walked":    chain_walked,
                    "found":           True,
                    "note":            f"Found on list '{price_list.get('ListName')}' "
                                       f"(SAP {current_sap_num})",
                }

            # price = 0 or None → try base list
            base_sap_num = price_list.get("BASE_NUM")

            if not base_sap_num or base_sap_num <= 0 or base_sap_num == current_sap_num:
                # No further chaining possible (also guards against BASE_NUM=-1)
                break

            logger.info(
                f"  {item_code}: price=0 on SAP list {current_sap_num} "
                f"→ following chain to SAP list {base_sap_num}"
            )
            current_sap_num = base_sap_num

        # Nothing found after walking the full chain
        note = (
            f"No price found for {item_code}. "
            f"Lists tried (SAP ListNum): {chain_walked}"
        )
        logger.warning(note)
        return {
            "item_code":       item_code,
            "price":           None,
            "currency":        "KES",
            "uom_entry":       None,
            "is_gross_price":  False,
            "price_list_id":   None,
            "price_list_name": "",
            "sap_list_num":    sap_list_num,
            "chain_walked":    chain_walked,
            "found":           False,
            "note":            note,
        }


    def get_price_any_list(
        self,
        item_code: str,
    ) -> Dict:
        """
        Try all known price lists and return the first non-zero price found.

        - Price > 0 on any list  → return it immediately
        - Price = 0 on any list  → item registered but unpriced; note it and continue
        - Item absent from list  → try next list
        Avoids recursive get_price() calls — uses _fetch_price directly.
        """
        registered_on: Optional[str] = None

        for sap_num in sorted(self._list_by_sap_num.keys()):
            pl     = self._list_by_sap_num[sap_num]
            api_id = self._to_int(pl.get('id'))
            if not api_id:
                continue

            # Skip broken non-EA lists (api_ids 23-34 all return 500)
            # Their EA equivalents are covered by the EA list entries
            if api_id >= 23:
                continue

            price, uom_entry = self._fetch_price(api_id, item_code)

            if price is None:
                continue  # item absent from this list

            if price > 0:
                return {
                    "item_code":       item_code,
                    "price":           price,
                    "currency":        "KES",
                    "uom_entry":       uom_entry,
                    "is_gross_price":  pl.get("isGrossPrc") == "Y",
                    "price_list_id":   api_id,
                    "price_list_name": pl.get("ListName", ""),
                    "sap_list_num":    sap_num,
                    "chain_walked":    [sap_num],
                    "found":           True,
                    "note":            f"Found on list {sap_num}: {pl.get('ListName', '')}",
                }

            # price == 0: item is registered but unpriced on this list
            if registered_on is None:
                registered_on = pl.get('ListName', f'SAP {sap_num}')
                logger.info(
                    f'  get_price_any_list: {item_code} registered but '
                    f'price=0 on {registered_on!r}'
                )

        if registered_on:
            note = (
                f'{item_code} exists in the system but has no price set '
                f'(likely an internal or inactive item).'
            )
        else:
            note = (
                f'No price data found for {item_code} on any of the '
                f'{len(self._list_by_sap_num)} price lists.'
            )

        logger.warning(f'  get_price_any_list: {note}')
        return {
            "item_code":       item_code,
            "price":           None,
            "currency":        "KES",
            "uom_entry":       None,
            "is_gross_price":  False,
            "price_list_id":   None,
            "price_list_name": registered_on or "",
            "sap_list_num":    0,
            "chain_walked":    [],
            "found":           False,
            "note":            note,
        }

    def get_all_price_lists(self) -> List[Dict]:
        """Return the cached list of all price lists (sorted by SAP ListNum)."""
        return sorted(self._list_by_sap_num.values(), key=lambda x: x["id"])

    def refresh(self):
        """Force a reload of the price list map from the API."""
        self._build_maps()

    # ------------------------------------------------------------------
    # INTERNAL — PRICE LIST MAP
    # ------------------------------------------------------------------

    def _build_maps(self):
        """
        Fetch all price lists and build two lookup dicts:
          sap_list_num → price_list_dict
          api_id       → price_list_dict
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/price_lists",
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()

            records = raw.get("ResponseData") or raw.get("responseData") or []
            if isinstance(records, dict):
                records = records.get("data", [])

            self._list_by_sap_num = {}
            self._list_by_api_id  = {}

            for pl in records:
                # ListNum is stored as a string in the API ("17", "18" …)
                sap_num = self._to_int(pl.get("ListNum"))
                api_id  = self._to_int(pl.get("id"))

                if sap_num is not None:
                    self._list_by_sap_num[sap_num] = pl
                if api_id is not None:
                    self._list_by_api_id[api_id] = pl

            # Log full map so we can debug ListNum→api_id mismatches
            mapping = {
                sap_num: pl.get('id')
                for sap_num, pl in self._list_by_sap_num.items()
            }
            logger.info(
                f"PricingService: loaded {len(self._list_by_sap_num)} price lists. "
                f"SAP ListNum→API id map: {mapping}"
            )

        except Exception as e:
            logger.error(f"PricingService: failed to build price list map: {e}")

    # ------------------------------------------------------------------
    # INTERNAL — PRICE FETCH
    # ------------------------------------------------------------------

    def _fetch_price(
        self,
        api_price_list_id: int,
        item_code: str,
    ) -> Tuple[Optional[float], Optional[int]]:
        """
        Fetch the price of item_code from a price list (by API id).

        Returns (price, uom_entry) or (None, None) on failure.

        Uses ?search=item_code — confirmed to work server-side.
        Falls back to None if the record exists but Price is missing.
        Treats Price=0 as "not priced" (caller walks the chain).
        """
        try:
            url    = f"{self.base_url}/item/base-prices/price-list/{api_price_list_id}"
            params = {"search": item_code, "per_page": 50}

            resp = self.session.get(url, params=params, timeout=PRICE_LIST_SEARCH_TIMEOUT)

            # 500 on certain price list IDs means the list exists in metadata
            # but has no usable data endpoint — skip it gracefully
            if resp.status_code == 500:
                logger.warning(
                    f"  _fetch_price: api_list={api_price_list_id} returned 500 "
                    f"(list may be empty or unsupported) — skipping"
                )
                return None, None

            resp.raise_for_status()
            raw = resp.json()

            records = raw.get("ResponseData") or raw.get("responseData") or []
            if isinstance(records, dict):
                records = records.get("data", [])

            for rec in records:
                if rec.get("ItemCode") == item_code:
                    price     = self._extract_price(rec)
                    uom_entry = rec.get("UomEntry")
                    logger.info(
                        f"  _fetch_price: {item_code} | api_list={api_price_list_id} "
                        f"| price={price} | uom_entry={uom_entry}"
                    )
                    return price, uom_entry

            # Item not in this list at all
            logger.info(
                f"  _fetch_price: {item_code} not found in api_list={api_price_list_id}"
            )
            return None, None

        except Exception as e:
            logger.error(
                f"  _fetch_price error: list={api_price_list_id} item={item_code}: {e}"
            )
            return None, None

    # ------------------------------------------------------------------
    # INTERNAL — HELPERS
    # ------------------------------------------------------------------

    def _customer_list_num(self, customer: Dict) -> int:
        """
        Extract the SAP price list number from a customer dict.

        Priority:
          1. customer["PriceListNum"]      (direct, often null)
          2. customer["octg"]["ListNum"]   (from payment group — reliable)
          3. DEFAULT_SAP_LIST_NUM
        """
        direct = self._to_int(customer.get("PriceListNum"))
        if direct:
            return direct

        octg = customer.get("octg") or {}
        from_octg = self._to_int(octg.get("ListNum"))
        if from_octg:
            return from_octg

        logger.info(
            f"Customer '{customer.get('CardName')}' has no price list — "
            f"using default SAP list {DEFAULT_SAP_LIST_NUM}"
        )
        return DEFAULT_SAP_LIST_NUM

    @staticmethod
    def _extract_price(record: Dict) -> Optional[float]:
        """
        Extract a numeric price from a record, checking known field names.
        Returns None only if ALL price fields are absent (not set in DB).
        Returns 0.0 if the field exists but is zero (caller interprets as unpriced).
        """
        for field in ("Price", "BasePrice", "UnitPrice", "ItemPrice"):
            val = record.get(field)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _to_int(value) -> Optional[int]:
        """Safely coerce a value to int (handles string "17", float 1.0, None)."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None