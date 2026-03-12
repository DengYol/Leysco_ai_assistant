"""
system_test.py
==============
Comprehensive test suite for ActionRouter.
Tests every intent/capability documented in the system.

Place this file anywhere inside your  app/  folder and run from project root:

    python app/system_test.py                    # run all tests
    python app/system_test.py -v                 # verbose output
    python app/system_test.py --category items   # one category
    python app/system_test.py --intent GET_ITEMS # one intent

Install optional deps for coloured output and tables:
    pip install colorama tabulate
"""

import sys
import os
import time
import importlib
import importlib.util
import argparse
import traceback
from datetime import datetime
from typing import Optional

# ── Locate action_router.py by walking up from this file ─────────────────────
_THIS_FILE = os.path.abspath(__file__)
_APP_DIR   = os.path.dirname(_THIS_FILE)
_ROOT_DIR  = os.path.dirname(_APP_DIR)

_AI_ENGINE_DIR = os.path.join(_APP_DIR, "ai_engine")

for _p in (_ROOT_DIR, _APP_DIR, _AI_ENGINE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Optional pretty-print deps ────────────────────────────────────────────────
try:
    from colorama import Fore, Style, init as colorama_init  # type: ignore[import]
    colorama_init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class Fore:  # type: ignore[no-redef]
        GREEN = RED = YELLOW = CYAN = MAGENTA = WHITE = RESET = ""
    class Style:  # type: ignore[no-redef]
        BRIGHT = DIM = RESET_ALL = ""

try:
    from tabulate import tabulate  # type: ignore[import]
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# ── Load ActionRouter ─────────────────────────────────────────────────────────
#
#   Strategy (tried in order):
#   1. Direct file load  - finds action_router.py on disk, no __init__.py needed
#   2. app.action_router - standard package import
#   3. action_router     - bare module import from _APP_DIR

IMPORT_OK    = False
IMPORT_ERROR = ""
ActionRouter = None  # type: ignore[assignment]

# 1. Direct file load
_ar_path = os.path.join(_APP_DIR, "ai_engine", "action_router.py")
if os.path.isfile(_ar_path):
    try:
        _spec = importlib.util.spec_from_file_location("action_router", _ar_path)
        _mod  = importlib.util.module_from_spec(_spec)          # type: ignore[arg-type]
        sys.modules["action_router"] = _mod
        _spec.loader.exec_module(_mod)                          # type: ignore[union-attr]
        ActionRouter = getattr(_mod, "ActionRouter", None)
        if ActionRouter is not None:
            IMPORT_OK = True
        else:
            IMPORT_ERROR = f"action_router.py found but has no ActionRouter class"
    except Exception:
        IMPORT_ERROR = traceback.format_exc()

# 2 & 3. Package / bare imports as fallback
if not IMPORT_OK:
    for _mod_name in ("app.action_router", "action_router"):
        try:
            _m = importlib.import_module(_mod_name)
            ActionRouter = getattr(_m, "ActionRouter", None)
            if ActionRouter is not None:
                IMPORT_OK = True
                IMPORT_ERROR = ""
                break
        except Exception:
            IMPORT_ERROR = traceback.format_exc()

if not IMPORT_OK:
    IMPORT_ERROR = (
        f"{IMPORT_ERROR}\n"
        f"  Looked for: {_ar_path}\n"
        f"  File exists: {os.path.isfile(_ar_path)}\n\n"
        f"  app/ .py files:\n" +
        "\n".join(f"    {f}" for f in sorted(os.listdir(_APP_DIR)) if f.endswith(".py"))
    )

# =============================================================================
# TEST DEFINITIONS
# Each entry: (category, intent, entities, message, language, description)
# =============================================================================
TEST_CASES = [

    # ──────────────────────────────────────────────
    # 💬 CONVERSATIONAL
    # ──────────────────────────────────────────────
    ("conversational", "GREETING",    {}, "Hello",          "en", "English greeting"),
    ("conversational", "GREETING",    {}, "Habari",          "sw", "Swahili greeting"),
    ("conversational", "THANKS",      {}, "Thank you",       "en", "English thanks"),
    ("conversational", "THANKS",      {}, "Asante",          "sw", "Swahili thanks"),
    ("conversational", "SMALL_TALK",  {}, "Goodbye",         "en", "Small talk / goodbye"),
    ("conversational", "FAQ",         {"item_name": "how do I order?"}, "how do I order?", "en", "FAQ question"),

    # ──────────────────────────────────────────────
    # 🏢 COMPANY KNOWLEDGE
    # ──────────────────────────────────────────────
    ("knowledge", "COMPANY_INFO",     {}, "Tell me about Leysco",              "en", "Company info EN"),
    ("knowledge", "COMPANY_INFO",     {}, "Niambie kuhusu Leysco",             "sw", "Company info SW"),
    ("knowledge", "PRODUCT_INFO",     {}, "What products do you have?",        "en", "Product catalogue"),
    ("knowledge", "HOW_TO_ORDER",     {}, "How do I place an order?",          "en", "Ordering process"),
    ("knowledge", "PAYMENT_METHODS",  {}, "What payment methods do you accept?","en", "Payment methods"),
    ("knowledge", "CONTACT_INFO",     {}, "How can I contact Leysco?",         "en", "Contact info"),
    ("knowledge", "POLICY_QUESTION",  {}, "What is your return policy?",       "en", "Return policy"),

    # ──────────────────────────────────────────────
    # 📦 ITEMS
    # ──────────────────────────────────────────────
    ("items", "GET_ITEMS",            {"quantity": 5},                       "show me items",                "en", "List items (no filter)"),
    ("items", "GET_ITEMS",            {"item_name": "vegimax", "quantity": 5}, "show vegimax items",         "en", "Search item by name"),
    ("items", "GET_ITEMS",            {"quantity": 5},                       "nionyeshe bidhaa",             "sw", "List items SW"),
    ("items", "GET_SELLABLE_ITEMS",   {"quantity": 5},                       "show sellable items",          "en", "Sellable items"),
    ("items", "GET_PURCHASABLE_ITEMS",{"quantity": 5},                       "show purchasable items",       "en", "Purchasable items"),
    ("items", "GET_INVENTORY_ITEMS",  {"quantity": 5},                       "show inventory items",         "en", "Inventory items"),
    ("items", "GET_ITEMS_ADVANCED",   {"quantity": 5},                       "show inventory report",        "en", "Advanced inventory report"),
    ("items", "GET_ITEM_DETAILS",     {"item_name": "vegimax"},              "show details for vegimax",     "en", "Item details (found)"),
    ("items", "GET_ITEM_DETAILS",     {},                                    "show item details",             "en", "Item details (missing name)"),
    ("items", "GET_ITEM_DETAILS",     {"item_name": "xyznotexist999"},       "details for xyznotexist999",   "en", "Item details (not found)"),

    # ──────────────────────────────────────────────
    # 💰 PRICING
    # ──────────────────────────────────────────────
    ("pricing", "GET_ITEM_PRICE",     {"item_name": "vegimax"},              "price of vegimax",             "en", "Item price"),
    ("pricing", "GET_ITEM_PRICE",     {},                                    "what is the price?",            "en", "Item price (missing name)"),
    ("pricing", "GET_CUSTOMER_PRICE", {"item_name": "vegimax", "customer_name": "Magomano"}, "price for Magomano", "en", "Customer-specific price"),
    ("pricing", "GET_CUSTOMER_PRICE", {"customer_name": "Magomano"},         "price for Magomano",           "en", "Customer price (missing item)"),
    ("pricing", "GET_CUSTOMER_PRICE", {"item_name": "vegimax"},              "price of vegimax",             "en", "Customer price (missing customer)"),

    # ──────────────────────────────────────────────
    # 👥 CUSTOMERS
    # ──────────────────────────────────────────────
    ("customers", "GET_CUSTOMERS",        {"quantity": 5},                   "list customers",               "en", "List customers"),
    ("customers", "GET_CUSTOMERS",        {"customer_name": "Magomano", "quantity": 3}, "find Magomano",    "en", "Search customer by name"),
    ("customers", "GET_CUSTOMERS",        {"quantity": 3},                   "orodhesha wateja",             "sw", "List customers SW"),
    ("customers", "GET_CUSTOMER_DETAILS", {"customer_name": "Magomano"},     "details for Magomano",         "en", "Customer details (found)"),
    ("customers", "GET_CUSTOMER_DETAILS", {},                                "show customer details",         "en", "Customer details (missing)"),
    ("customers", "GET_CUSTOMER_DETAILS", {"customer_name": "xyzfakeXYZ"},   "details for xyzfakeXYZ",       "en", "Customer details (not found)"),

    # ──────────────────────────────────────────────
    # 🏭 WAREHOUSES
    # ──────────────────────────────────────────────
    ("warehouses", "GET_WAREHOUSES",      {},                                "show warehouses",              "en", "List all warehouses"),
    ("warehouses", "GET_WAREHOUSES",      {"warehouse": "Nairobi"},          "show Nairobi warehouse",       "en", "Warehouse by name"),
    ("warehouses", "GET_WAREHOUSE_STOCK", {"warehouse": "Nairobi"},          "stock in Nairobi",             "en", "Warehouse stock"),
    ("warehouses", "GET_WAREHOUSE_STOCK", {},                                "show warehouse stock",         "en", "Warehouse stock (missing name)"),
    ("warehouses", "GET_LOW_STOCK_ALERTS",{},                                "show low stock alerts",        "en", "Low stock alerts (all)"),
    ("warehouses", "GET_LOW_STOCK_ALERTS",{"warehouse": "Nairobi"},          "low stock in Nairobi",         "en", "Low stock alerts (warehouse)"),

    # ──────────────────────────────────────────────
    # 📋 ORDERS, INVOICES, QUOTATIONS
    # ──────────────────────────────────────────────
    ("orders", "GET_CUSTOMER_ORDERS",     {"customer_name": "Magomano", "quantity": 5}, "orders for Magomano", "en", "Customer orders"),
    ("orders", "GET_CUSTOMER_ORDERS",     {},                                "show orders",                  "en", "Orders (missing customer)"),
    ("orders", "GET_CUSTOMER_INVOICES",   {"customer_name": "Magomano", "quantity": 5}, "invoices for Magomano","en","Customer invoices"),
    ("orders", "GET_OUTSTANDING_INVOICES",{"customer_name": "Magomano"},     "outstanding invoices",         "en", "Outstanding invoices"),
    ("orders", "GET_QUOTATIONS",          {"customer_name": "Magomano", "quantity": 5}, "quotations for Magomano","en","Customer quotations"),
    ("orders", "GET_QUOTATIONS",          {},                                "show quotations",              "en", "Quotations (missing customer)"),
    ("orders", "CREATE_QUOTATION",
        {"customer_name": "Magomano"},
        "create quotation for Magomano with 5 vegimax",
        "en", "Create quotation"),
    ("orders", "CREATE_QUOTATION",        {},                                "create quotation",             "en", "Create quotation (missing customer)"),
    ("orders", "GET_OUTSTANDING_DELIVERIES", {"customer_name": "Magomano", "quantity": 5}, "outstanding deliveries", "en", "Outstanding deliveries"),
    ("orders", "TRACK_DELIVERY",          {"item_name": "12345"},            "track delivery 12345",         "en", "Track delivery"),
    ("orders", "TRACK_DELIVERY",          {},                                "track delivery",               "en", "Track delivery (missing number)"),
    ("orders", "GET_DELIVERY_HISTORY",    {"customer_name": "Magomano", "quantity": 5}, "delivery history for Magomano","en","Delivery history"),

    # ──────────────────────────────────────────────
    # 🎯 RECOMMENDATIONS
    # ──────────────────────────────────────────────
    ("recommendations", "RECOMMEND_ITEMS",    {"quantity": 5},                   "recommend items",            "en", "Recommend items (general)"),
    ("recommendations", "RECOMMEND_ITEMS",    {"item_name": "vegimax", "quantity": 5}, "items like vegimax",   "en", "Recommend items (by item)"),
    ("recommendations", "RECOMMEND_ITEMS",    {"customer_name": "Magomano", "quantity": 5}, "items for Magomano","en","Recommend items (by customer)"),
    ("recommendations", "RECOMMEND_CUSTOMERS",{"quantity": 5},                   "recommend customers",        "en", "Recommend customers (general)"),
    ("recommendations", "RECOMMEND_CUSTOMERS",{"item_name": "vegimax", "quantity": 5}, "customers for vegimax","en","Recommend customers (by item)"),
    ("recommendations", "GET_CROSS_SELL",     {"item_name": "vegimax", "quantity": 5}, "cross sell for vegimax","en","Cross-sell suggestions"),
    ("recommendations", "GET_CROSS_SELL",     {},                                "cross sell",                 "en", "Cross-sell (missing item)"),
    ("recommendations", "GET_UPSELL",         {"item_name": "vegimax", "quantity": 3}, "upsell vegimax",        "en", "Upsell suggestions"),
    ("recommendations", "GET_SEASONAL_RECOMMENDATIONS", {"quantity": 5},         "seasonal picks",             "en", "Seasonal recommendations"),
    ("recommendations", "GET_TRENDING_PRODUCTS", {"quantity": 5},                "trending products",          "en", "Trending products"),

    # ──────────────────────────────────────────────
    # 📊 DECISION SUPPORT
    # ──────────────────────────────────────────────
    ("decision_support", "ANALYZE_INVENTORY_HEALTH", {},                          "analyze inventory health",  "en", "Inventory health (all)"),
    ("decision_support", "ANALYZE_INVENTORY_HEALTH", {"warehouse": "Nairobi"},    "inventory health Nairobi",  "en", "Inventory health (warehouse)"),
    ("decision_support", "GET_REORDER_DECISIONS",    {},                          "reorder decisions",         "en", "Reorder decisions"),
    ("decision_support", "ANALYZE_PRICING_OPPORTUNITIES", {},                     "pricing opportunities",     "en", "Pricing opportunities"),
    ("decision_support", "ANALYZE_CUSTOMER_BEHAVIOR", {"customer_name": "Magomano"}, "customer behaviour",    "en", "Customer behaviour analysis"),
    ("decision_support", "ANALYZE_CUSTOMER_BEHAVIOR", {},                         "analyze customer",          "en", "Customer behaviour (missing name)"),
    ("decision_support", "FORECAST_DEMAND",          {"item_name": "vegimax", "quantity": 30}, "forecast vegimax","en","Demand forecast"),
    ("decision_support", "FORECAST_DEMAND",          {},                           "forecast demand",          "en", "Demand forecast (missing item)"),

    # ──────────────────────────────────────────────
    # 🎓 TRAINING
    # ──────────────────────────────────────────────
    ("training", "TRAINING_ONBOARDING", {},                                    "start onboarding",            "en", "Onboarding welcome"),
    ("training", "TRAINING_MODULE",     {"item_name": "pricing"},              "training module pricing",     "en", "Training module"),
    ("training", "TRAINING_VIDEO",      {},                                    "show training videos",         "en", "Training videos"),
    ("training", "TRAINING_GUIDE",      {},                                    "show training guides",         "en", "Training guides"),
    ("training", "TRAINING_FAQ",        {},                                    "training FAQ",                 "en", "Training FAQ"),
    ("training", "TRAINING_GLOSSARY",   {},                                    "show glossary",                "en", "Training glossary"),
    ("training", "TRAINING_WEBINAR",    {},                                    "show webinars",                "en", "Training webinars"),

    # ──────────────────────────────────────────────
    # ❓ FALLBACK
    # ──────────────────────────────────────────────
    ("fallback", "UNKNOWN_INTENT_XYZ",  {},                                    "do something weird",          "en", "Unsupported intent (fallback)"),
]


# =============================================================================
# RESULT TRACKING
# =============================================================================
class TestResult:
    def __init__(self):
        self.passed   = 0
        self.failed   = 0
        self.errors   = 0
        self.skipped  = 0
        self.records  = []   # (status, category, intent, desc, duration, detail)

    @property
    def total(self):
        return self.passed + self.failed + self.errors + self.skipped

    def add(self, status, category, intent, desc, duration, detail=""):
        self.records.append((status, category, intent, desc, f"{duration:.3f}s", detail))
        if   status == "PASS":  self.passed  += 1
        elif status == "FAIL":  self.failed  += 1
        elif status == "ERROR": self.errors  += 1
        elif status == "SKIP":  self.skipped += 1


# =============================================================================
# VALIDATION HELPERS
# =============================================================================
def validate_result(result, intent: str, entities: dict) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    A result is valid when:
      - It is a dict
      - It has 'message' key (string, non-empty)  OR  has 'error' key for unsupported intents
    """
    if not isinstance(result, dict):
        return False, f"Expected dict, got {type(result).__name__}"

    # Fallback intents return {"error": ...}
    if "error" in result:
        return True, "Unsupported intent returned error key (expected)"

    if "message" not in result:
        return False, "Result missing 'message' key"

    msg = result["message"]
    if not isinstance(msg, str):
        return False, f"'message' is not a string (got {type(msg).__name__})"

    if not msg.strip():
        return False, "'message' is empty string"

    # 'data' key should exist (can be empty list or None for knowledge intents)
    if "data" not in result:
        return False, "Result missing 'data' key"

    return True, "OK"


def colour(text: str, colour_code: str) -> str:
    if HAS_COLOR:
        return f"{colour_code}{text}{Style.RESET_ALL}"
    return text


def status_label(status: str) -> str:
    mapping = {
        "PASS":  colour("✓ PASS",  Fore.GREEN),
        "FAIL":  colour("✗ FAIL",  Fore.RED),
        "ERROR": colour("⚡ ERROR", Fore.YELLOW),
        "SKIP":  colour("– SKIP",  Fore.CYAN),
    }
    return mapping.get(status, status)


# =============================================================================
# RUNNER
# =============================================================================
def run_tests(
    router: "ActionRouter",
    category_filter: Optional[str] = None,
    intent_filter:   Optional[str] = None,
    verbose: bool = False,
) -> TestResult:

    results = TestResult()
    total   = len(TEST_CASES)

    print(colour(f"\n{'='*70}", Style.BRIGHT))
    print(colour("  Leysco ActionRouter — System Test Suite", Style.BRIGHT))
    print(colour(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  {total} test cases", Style.DIM))
    print(colour(f"{'='*70}\n", Style.BRIGHT))

    for idx, (category, intent, entities, message, language, description) in enumerate(TEST_CASES, 1):

        # Apply filters
        if category_filter and category.lower() != category_filter.lower():
            results.add("SKIP", category, intent, description, 0, "Filtered out")
            continue
        if intent_filter and intent.upper() != intent_filter.upper():
            results.add("SKIP", category, intent, description, 0, "Filtered out")
            continue

        prefix = f"[{idx:>3}/{total}]"
        label  = f"{colour(category.upper(), Fore.CYAN)} › {colour(intent, Fore.MAGENTA)}"
        print(f"{colour(prefix, Style.DIM)} {label}")
        if verbose:
            print(f"         {colour('Desc:', Style.DIM)} {description}")
            print(f"         {colour('Msg :', Style.DIM)} {message!r}")
            print(f"         {colour('Ent :', Style.DIM)} {entities}")
            print(f"         {colour('Lang:', Style.DIM)} {language}")

        t0 = time.perf_counter()
        try:
            result   = router.route(intent, entities, message, language)
            duration = time.perf_counter() - t0

            ok, reason = validate_result(result, intent, entities)

            if ok:
                results.add("PASS", category, intent, description, duration)
                print(f"         {status_label('PASS')} ({duration:.3f}s)")
                if verbose and result.get("message"):
                    preview = result["message"][:200].replace("\n", " ")
                    print(f"         {colour('→', Style.DIM)} {preview}{'…' if len(result['message']) > 200 else ''}")
            else:
                results.add("FAIL", category, intent, description, duration, reason)
                print(f"         {status_label('FAIL')} ({duration:.3f}s) — {colour(reason, Fore.RED)}")

        except Exception as exc:
            duration = time.perf_counter() - t0
            tb = traceback.format_exc()
            short_err = str(exc)[:120]
            results.add("ERROR", category, intent, description, duration, short_err)
            print(f"         {status_label('ERROR')} ({duration:.3f}s) — {colour(short_err, Fore.YELLOW)}")
            if verbose:
                print(colour(tb, Fore.YELLOW))

        print()

    return results


# =============================================================================
# SUMMARY REPORT
# =============================================================================
def print_summary(results: TestResult):
    print(colour(f"{'='*70}", Style.BRIGHT))
    print(colour("  SUMMARY", Style.BRIGHT))
    print(colour(f"{'='*70}", Style.BRIGHT))

    pass_rate = (results.passed / results.total * 100) if results.total else 0

    print(f"  Total   : {results.total}")
    print(f"  {colour('Passed', Fore.GREEN)}  : {results.passed}")
    print(f"  {colour('Failed', Fore.RED)}  : {results.failed}")
    print(f"  {colour('Errors', Fore.YELLOW)}  : {results.errors}")
    print(f"  {colour('Skipped', Fore.CYAN)} : {results.skipped}")
    print(f"  Pass rate: {colour(f'{pass_rate:.1f}%', Fore.GREEN if pass_rate >= 80 else Fore.RED)}")
    print()

    # Per-category breakdown
    category_stats: dict[str, dict] = {}
    for status, cat, intent, desc, dur, detail in results.records:
        if cat not in category_stats:
            category_stats[cat] = {"pass": 0, "fail": 0, "error": 0, "skip": 0}
        category_stats[cat][status.lower()] += 1

    print(colour("  Category Breakdown:", Style.BRIGHT))
    headers = ["Category", "Pass", "Fail", "Error", "Skip"]
    rows = [
        [
            colour(cat, Fore.CYAN),
            colour(str(s["pass"]),  Fore.GREEN),
            colour(str(s["fail"]),  Fore.RED   if s["fail"]  else Style.DIM),
            colour(str(s["error"]), Fore.YELLOW if s["error"] else Style.DIM),
            colour(str(s["skip"]),  Fore.CYAN   if s["skip"]  else Style.DIM),
        ]
        for cat, s in sorted(category_stats.items())
    ]
    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="simple"))
    else:
        print(f"  {'Category':<25} {'Pass':>5} {'Fail':>5} {'Error':>6} {'Skip':>5}")
        for cat, s in sorted(category_stats.items()):
            print(f"  {cat:<25} {s['pass']:>5} {s['fail']:>5} {s['error']:>6} {s['skip']:>5}")

    # Show failures / errors
    failures = [(s, cat, intent, desc, dur, d) for s, cat, intent, desc, dur, d in results.records
                if s in ("FAIL", "ERROR")]
    if failures:
        print()
        print(colour("  Failed / Errored Tests:", Fore.RED))
        for status, cat, intent, desc, dur, detail in failures:
            icon = "✗" if status == "FAIL" else "⚡"
            print(f"  {colour(icon, Fore.RED if status == 'FAIL' else Fore.YELLOW)} "
                  f"{cat} › {intent} — {desc}")
            if detail:
                print(f"    {colour(detail, Style.DIM)}")

    print(colour(f"\n{'='*70}\n", Style.BRIGHT))
    return pass_rate >= 80   # exit 0 when pass rate ≥ 80 %


# =============================================================================
# ENTRY POINT
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Leysco ActionRouter System Tests")
    parser.add_argument("-v", "--verbose",   action="store_true", help="Show detailed output per test")
    parser.add_argument("--category",        help="Only run tests in this category")
    parser.add_argument("--intent",          help="Only run tests for this specific intent")
    parser.add_argument("--list-categories", action="store_true", help="List available categories and exit")
    args = parser.parse_args()

    if args.list_categories:
        cats = sorted(set(c for c, *_ in TEST_CASES))
        print("Available categories:")
        for c in cats:
            count = sum(1 for tc in TEST_CASES if tc[0] == c)
            print(f"  {c:<25} ({count} tests)")
        sys.exit(0)

    if not IMPORT_OK:
        print(colour(f"\n❌  Cannot import ActionRouter: {IMPORT_ERROR}", Fore.RED))
        print(colour("    Make sure you run this from the project root directory.", Style.DIM))
        print(colour("    e.g.  python system_test.py", Style.DIM))
        sys.exit(1)

    print(colour("\n⚙  Initialising ActionRouter …", Style.DIM))
    try:
        router = ActionRouter()
        print(colour("✓  ActionRouter ready.\n", Fore.GREEN))
    except Exception as e:
        print(colour(f"\n❌  Failed to instantiate ActionRouter: {e}", Fore.RED))
        traceback.print_exc()
        sys.exit(1)

    results = run_tests(
        router,
        category_filter=args.category,
        intent_filter=args.intent,
        verbose=args.verbose,
    )

    all_ok = print_summary(results)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()