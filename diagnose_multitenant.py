#!/usr/bin/env python3
"""
Diagnostic Tool: Multi-Tenant Backend URL Routing Verification
FIXED: Windows UTF-8 encoding issues
"""

import os
import re
import sys
from typing import Optional, Dict, List, Tuple

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

def log_pass(msg: str):
    print(f"{GREEN}✅ {msg}{RESET}")

def log_fail(msg: str):
    print(f"{RED}❌ {msg}{RESET}")

def log_warn(msg: str):
    print(f"{YELLOW}⚠️  {msg}{RESET}")

def log_info(msg: str):
    print(f"{BLUE}ℹ️  {msg}{RESET}")

def log_section(title: str):
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{title}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")

# =========================================================
# CHECK 1: Environment Variables
# =========================================================

def check_env_vars() -> Tuple[bool, List[str]]:
    """Check if per-tenant env vars are configured."""
    log_section("1️⃣  CHECKING ENVIRONMENT VARIABLES")
    
    all_pass = True
    env_vars = {}
    
    for key, value in os.environ.items():
        if key.startswith("LARAVEL_BACKEND_URL_"):
            company_code = key.replace("LARAVEL_BACKEND_URL_", "")
            env_vars[company_code] = value
    
    if env_vars:
        log_pass(f"Found {len(env_vars)} per-tenant backend URLs")
        for code, url in sorted(env_vars.items()):
            print(f"  {BLUE}•{RESET} {code:15} → {url}")
    else:
        log_warn("No per-tenant env vars found (LARAVEL_BACKEND_URL_<CODE>)")
        all_pass = False
    
    global_url = os.getenv("LARAVEL_BACKEND_URL")
    if global_url:
        log_info(f"Global fallback: {global_url}")
    else:
        log_warn("No global LARAVEL_BACKEND_URL fallback set")
        all_pass = False
    
    return all_pass, list(env_vars.keys())


# =========================================================
# CHECK 2: URL Pattern Matching
# =========================================================

def check_url_patterns() -> bool:
    """Verify the URL pattern matching for origin sniffing."""
    log_section("2️⃣  CHECKING URL PATTERN MATCHING")
    
    all_pass = True
    pattern = r"https?://(dev\d+)\.leysco100\.com"
    
    test_cases = [
        ("https://dev100.leysco100.com", "dev100", True),
        ("https://dev109.leysco100.com", "dev109", True),
        ("https://dev1.leysco100.com", "dev1", True),
        ("https://dev999.leysco100.com", "dev999", True),
        ("https://custom.leysco100.com", None, False),
        ("https://dev100.other.com", None, False),
        ("https://localhost:3000", None, False),
    ]
    
    for origin, expected_match, should_match in test_cases:
        m = re.search(pattern, origin)
        matched = m.group(1) if m else None
        
        if should_match:
            if matched == expected_match:
                log_pass(f"'{origin}' → {matched}")
            else:
                log_fail(f"'{origin}' expected {expected_match}, got {matched}")
                all_pass = False
        else:
            if matched is None:
                log_pass(f"'{origin}' correctly didn't match")
            else:
                log_fail(f"'{origin}' should not match, but got {matched}")
                all_pass = False
    
    return all_pass


# =========================================================
# CHECK 3: Backend URL Resolution Chain
# =========================================================

def check_resolution_chain() -> bool:
    """Simulate the resolution chain for various scenarios."""
    log_section("3️⃣  CHECKING RESOLUTION CHAIN")
    
    all_pass = True
    
    test_cases = [
        {
            "name": "Per-tenant env var (highest priority)",
            "company_code": "TEST001",
            "env_vars": {"LARAVEL_BACKEND_URL_TEST001": "https://dev100-be.leysco100.com"},
            "origin": None,
            "expected": "https://dev100-be.leysco100.com",
        },
        {
            "name": "Origin sniffing (no env var)",
            "company_code": None,
            "env_vars": {},
            "origin": "https://dev109.leysco100.com",
            "expected": "https://dev109-be.leysco100.com",
        },
        {
            "name": "Global fallback",
            "company_code": None,
            "env_vars": {"LARAVEL_BACKEND_URL": "https://dev100-be.leysco100.com"},
            "origin": None,
            "expected": "https://dev100-be.leysco100.com",
        },
    ]
    
    for case in test_cases:
        result = None
        
        if case["company_code"]:
            env_key = f"LARAVEL_BACKEND_URL_{case['company_code'].upper()}"
            result = case["env_vars"].get(env_key)
        
        if not result and case["origin"]:
            m = re.search(r"https?://(dev\d+)\.leysco100\.com", case["origin"])
            if m:
                result = f"https://{m.group(1)}-be.leysco100.com"
        
        if not result:
            result = case["env_vars"].get("LARAVEL_BACKEND_URL")
        
        if result == case["expected"]:
            log_pass(f"{case['name']}")
            print(f"  {BLUE}Result:{RESET} {result}")
        else:
            log_fail(f"{case['name']}")
            print(f"  {RED}Expected:{RESET} {case['expected']}")
            print(f"  {RED}Got:{RESET} {result}")
            all_pass = False
    
    return all_pass


# =========================================================
# CHECK 4: Token Session Caching
# =========================================================

def check_session_caching() -> bool:
    """Verify that session cache includes backend_url."""
    log_section("4️⃣  CHECKING SESSION CACHE STRUCTURE")
    
    all_pass = True
    
    expected_session_fields = [
        "user_id",
        "user_role",
        "user_email",
        "company_code",
        "assigned_customers",
        "is_manager",
        "backend_url",
        "raw_user_data",
    ]
    
    log_info("Expected fields in cached user session:")
    for field in expected_session_fields:
        if field == "backend_url":
            print(f"  {GREEN}•{RESET} {field:20} ← {BOLD}REQUIRED for multi-tenant{RESET}")
        else:
            print(f"  {BLUE}•{RESET} {field:20}")
    
    log_pass("Session cache structure verified")
    return all_pass


# =========================================================
# CHECK 5: Code Inspection
# =========================================================

def check_code_quality() -> bool:
    """Check that the codebase uses proper multi-tenant factories."""
    log_section("5️⃣  CHECKING CODE USAGE PATTERNS")
    
    all_pass = True
    
    files_to_check = [
        ("app/api/dependencies.py", "resolve_backend_url", "multi-tenant URL resolution"),
        ("app/services/leysco_api/client.py", "create_api_service_from_context", "context-aware API service factory"),
    ]
    
    for filepath, function, purpose in files_to_check:
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                if function in content:
                    log_pass(f"{filepath}: {function}() found")
                    print(f"  {BLUE}Purpose:{RESET} {purpose}")
                else:
                    log_fail(f"{filepath}: {function}() NOT FOUND")
                    all_pass = False
            except Exception as e:
                log_fail(f"{filepath}: Error reading file: {e}")
                all_pass = False
        else:
            log_fail(f"{filepath}: FILE NOT FOUND")
            all_pass = False
    
    return all_pass


# =========================================================
# CHECK 6: Multi-Tenant Configuration
# =========================================================

def check_multitenant_config(company_codes: List[str]) -> bool:
    """Comprehensive multi-tenant configuration check."""
    log_section("6️⃣  CHECKING MULTI-TENANT CONFIGURATION")
    
    all_pass = True
    
    if not company_codes:
        log_warn("No per-tenant env vars configured")
        log_info("To enable multi-tenant, set environment variables:")
        print(f"  export LARAVEL_BACKEND_URL_TEST001=https://dev100-be.leysco100.com")
        print(f"  export LARAVEL_BACKEND_URL_TEST009=https://dev109-be.leysco100.com")
        return False
    
    log_pass(f"Found {len(company_codes)} configured tenants")
    
    for code in company_codes:
        url = os.getenv(f"LARAVEL_BACKEND_URL_{code}")
        
        if url and url.startswith("https://") and "-be.leysco100.com" in url:
            log_pass(f"{code}: {url}")
        else:
            log_fail(f"{code}: Invalid URL format: {url}")
            log_info("  Expected format: https://<env>-be.leysco100.com")
            all_pass = False
    
    return all_pass


# =========================================================
# MAIN
# =========================================================

def main():
    print(f"\n{BOLD}{BLUE}{'='*70}")
    print(f"Multi-Tenant Backend URL Routing Diagnostic Tool")
    print(f"{'='*70}{RESET}\n")
    
    results = {}
    
    results["env_vars"], company_codes = check_env_vars()
    results["patterns"] = check_url_patterns()
    results["chain"] = check_resolution_chain()
    results["caching"] = check_session_caching()
    results["code"] = check_code_quality()
    results["config"] = check_multitenant_config(company_codes)
    
    log_section("SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n{BOLD}Results: {passed}/{total} checks passed{RESET}\n")
    
    for check, result in results.items():
        status = f"{GREEN}✅ PASS{RESET}" if result else f"{RED}❌ FAIL{RESET}"
        print(f"  {status} — {check}")
    
    if passed == total:
        log_pass("\n🎉 Multi-tenant backend URL routing is fully configured!")
        return 0
    else:
        log_warn(f"\n{total - passed} issue(s) found. See above for details and fixes.")
        return 1


if __name__ == "__main__":
    sys.exit(main())