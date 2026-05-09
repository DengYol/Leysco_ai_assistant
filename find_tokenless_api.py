#!/usr/bin/env python3
"""
Script to find all places where LeyscoAPIService is created without a user token.
Run: python find_tokenless_api.py
"""

import os
import re
import ast
from pathlib import Path

def find_leysco_api_instantiations(directory="."):
    """Find all LeyscoAPIService instantiations and check if they pass a token."""
    
    results = []
    
    for root, dirs, files in os.walk(directory):
        # Skip virtual environments and cache directories
        if any(skip in root for skip in ['venv', '__pycache__', 'env', '.git', 'node_modules']):
            continue
        
        for file in files:
            if not file.endswith('.py'):
                continue
            
            filepath = os.path.join(root, file)
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Look for LeyscoAPIService() without token
                lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    # Check for LeyscoAPIService() without token parameter
                    if 'LeyscoAPIService(' in line:
                        # Check if token is passed
                        if 'LeyscoAPIService()' in line or 'LeyscoAPIService( )' in line:
                            results.append({
                                'file': filepath,
                                'line': i,
                                'code': line.strip(),
                                'issue': 'No token parameter at all'
                            })
                        elif 'user_token=' not in line and 'token=' not in line:
                            # Has parameters but no user_token
                            results.append({
                                'file': filepath,
                                'line': i,
                                'code': line.strip(),
                                'issue': 'Has parameters but missing user_token'
                            })
                    
                    # Also check for create_api_service() without token
                    if 'create_api_service(' in line and 'create_api_service()' in line:
                        results.append({
                            'file': filepath,
                            'line': i,
                            'code': line.strip(),
                            'issue': 'create_api_service called without token'
                        })
                    
                    # Check for get_pricing_service() with token (should use create_pricing_service)
                    if 'get_pricing_service(user_token=' in line:
                        results.append({
                            'file': filepath,
                            'line': i,
                            'code': line.strip(),
                            'issue': 'Using get_pricing_service with token - should use create_pricing_service'
                        })
                    
                    # Check for PricingService() without token
                    if 'PricingService()' in line and 'PricingService()' in line:
                        results.append({
                            'file': filepath,
                            'line': i,
                            'code': line.strip(),
                            'issue': 'PricingService created without token'
                        })
                    
                    # Check for WarehouseService() without token
                    if 'WarehouseService()' in line:
                        results.append({
                            'file': filepath,
                            'line': i,
                            'code': line.strip(),
                            'issue': 'WarehouseService created without token'
                        })
                        
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
    
    return results

def main():
    print("=" * 80)
    print("🔍 Finding LeyscoAPIService instantiations without user token...")
    print("=" * 80)
    
    # Start from the app directory
    app_dir = "app"
    if not os.path.exists(app_dir):
        app_dir = "."
    
    results = find_leysco_api_instantiations(app_dir)
    
    if not results:
        print("\n✅ No issues found! All API services appear to be created with tokens.")
    else:
        print(f"\n❌ Found {len(results)} potential issues:\n")
        
        for r in results:
            print(f"📁 File: {r['file']}")
            print(f"📍 Line: {r['line']}")
            print(f"⚠️  Issue: {r['issue']}")
            print(f"📝 Code: {r['code']}")
            print("-" * 80)
        
        print("\n💡 Suggested fixes:")
        print("  1. Replace 'LeyscoAPIService()' with 'create_api_service(user_token=token)'")
        print("  2. Replace 'PricingService()' with 'create_pricing_service(user_token=token)'")
        print("  3. Replace 'WarehouseService()' with 'create_warehouse_service(user_token=token)'")
        print("  4. Replace 'get_pricing_service(user_token=...)' with 'create_pricing_service(user_token=...)'")
        print("  5. Make sure the service receives user_token in its __init__")

if __name__ == "__main__":
    main()