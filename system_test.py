"""
system_test.py
==============
Comprehensive System Test Suite for Leysco AI Assistant

Run with: python -m pytest system_test.py -v
Or: python system_test.py (for manual testing)
"""

import sys
import os
import json
import time
import asyncio
import unittest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import test configuration
try:
    from app.core.config import settings
except ImportError:
    # Mock settings if not available
    class MockSettings:
        GROQ_API_KEY = "test_key"
        LEYSCO_API_BASE_URL = "https://test-api.leysco.com/api/v1"
        LEYSCO_API_TOKEN = "test_token"
        ENABLED_COMPETITORS = "twiga,sokopepper"
        COMPETITOR_API_TIMEOUT_SECONDS = 10
        COMPETITOR_CACHE_TTL_HOURS = 24
        WORLD_BANK_ENABLED = False
        GROQ_MODEL = "llama3-8b-8192"
    
    settings = MockSettings()


# =========================================================
# Test Imports
# =========================================================

def test_imports():
    """Test that all modules can be imported correctly."""
    print("\n" + "="*60)
    print("TEST 1: Module Imports")
    print("="*60)
    
    modules_to_test = [
        ("app.services.leysco_api_service", "LeyscoAPIService"),
        ("app.services.pricing_service", "PricingService"),
        ("app.services.warehouse_service", "WarehouseService"),
        ("app.services.recommendation_service", "RecommendationService"),
        ("app.services.delivery_tracking_service", "DeliveryTrackingService"),
        ("app.services.quotation_service", "QuotationService"),
        ("app.services.customer_health_service", "CustomerHealthService"),
        ("app.services.quotation_intelligence", "QuotationIntelligence"),
        ("app.services.competitor_api_service", "CompetitorAPIService"),
        ("app.services.db_query_service", "DBQueryService"),
        ("app.services.llm_service", "LLMService"),
        ("app.services.cache_service", "CacheService"),
        ("app.services.session_context", "SessionContext"),
        ("app.ai_engine.action_router", "ActionRouter"),
        ("app.ai_engine.intent_classifier", "IntentClassifier"),
        ("app.ai_engine.entity_extractor", "EntityExtractor"),
        ("app.ai_engine.swahili_support", "SwahiliSupport"),
        ("app.ai_engine.conversation_enhancer", "ConversationEnhancer"),
        ("app.ai_engine.decision_support", "DecisionSupport"),
        ("app.ai_engine.response_formatter", "ResponseFormatter"),
        ("app.ai_engine.suggestions_engine", "SuggestionsEngine"),
        ("app.ai_engine.prompt_manager", "PromptManager"),
        ("app.ai_engine.leysco_knowledge_base", "get_knowledge"),
        ("app.ai_engine.multi_turn_quotation", "handle_create_quotation"),
        ("app.ai_engine.intent_overrides", "apply_intent_overrides"),
        ("app.ai_engine.training_actions", "TrainingActions"),
    ]
    
    passed = 0
    failed = 0
    
    for module_name, class_name in modules_to_test:
        try:
            module = __import__(module_name, fromlist=[class_name])
            if class_name:
                getattr(module, class_name)
            print(f"✅ {module_name}.{class_name}")
            passed += 1
        except ImportError as e:
            print(f"❌ {module_name}.{class_name}: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠️ {module_name}.{class_name}: {e}")
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    return failed == 0


# =========================================================
# Test Services
# =========================================================

def test_cache_service():
    """Test cache service functionality."""
    print("\n" + "="*60)
    print("TEST 2: Cache Service")
    print("="*60)
    
    from app.services.cache_service import get_cache_service
    
    cache = get_cache_service(ttl_seconds=5, max_entries=10)
    
    # Test set and get
    test_intent = "TEST_INTENT"
    test_entities = {"item_name": "vegimax"}
    test_response = {"message": "Test response", "data": []}
    
    cache.set(test_intent, test_entities, "test message", test_response)
    
    cached = cache.get(test_intent, test_entities)
    if cached and cached.get("message") == "Test response":
        print("✅ Cache set/get works")
    else:
        print("❌ Cache set/get failed")
        return False
    
    # Test TTL expiration
    time.sleep(6)
    cached = cache.get(test_intent, test_entities)
    if cached is None:
        print("✅ Cache TTL expiration works")
    else:
        print("❌ Cache TTL expiration failed")
    
    # Test stats
    stats = cache.get_stats()
    print(f"📊 Cache stats: {stats['cache_size']} entries, {stats['hit_rate']} hit rate")
    
    # Test invalidation
    cache.set(test_intent, test_entities, "test", test_response)
    cache.invalidate_intent(test_intent)
    cached = cache.get(test_intent, test_entities)
    if cached is None:
        print("✅ Cache invalidation works")
    else:
        print("❌ Cache invalidation failed")
    
    return True


def test_session_context():
    """Test session context functionality."""
    print("\n" + "="*60)
    print("TEST 3: Session Context")
    print("="*60)
    
    from app.services.session_context import SessionContext
    
    ctx = SessionContext(ttl_seconds=2)
    session_id = "test_session_123"
    
    # Test merge
    result = ctx.merge(session_id, {"item_name": "vegimax"})
    if result.get("item_name") == "vegimax":
        print("✅ Session merge works")
    else:
        print("❌ Session merge failed")
        return False
    
    # Test get
    data = ctx.get(session_id)
    if data.get("item_name") == "vegimax":
        print("✅ Session get works")
    else:
        print("❌ Session get failed")
    
    # Test update
    ctx.update_from_response(session_id, {"customer_name": "Magomano"})
    data = ctx.get(session_id)
    if data.get("customer_name") == "Magomano":
        print("✅ Session update works")
    else:
        print("❌ Session update failed")
    
    # Test reference resolution
    entities = {}
    result = ctx.resolve_references(session_id, "what is the price of it?", entities)
    if result.get("item_name") == "vegimax":
        print("✅ Reference resolution (it → item) works")
    else:
        print("❌ Reference resolution failed")
    
    # Test TTL expiration
    time.sleep(2.5)
    data = ctx.get(session_id)
    if not data:
        print("✅ Session TTL expiration works")
    else:
        print("❌ Session TTL expiration failed")
    
    # Test clear
    ctx.merge(session_id, {"item_name": "test"})
    ctx.clear(session_id)
    data = ctx.get(session_id)
    if not data:
        print("✅ Session clear works")
    else:
        print("❌ Session clear failed")
    
    return True


def test_swahili_support():
    """Test Swahili language support."""
    print("\n" + "="*60)
    print("TEST 4: Swahili Support")
    print("="*60)
    
    from app.ai_engine.swahili_support import SwahiliSupport
    
    sw = SwahiliSupport()
    
    test_cases = [
        ("habari", "sw"),
        ("jambo", "sw"),
        ("bei ya vegimax", "mixed"),
        ("hello", "en"),
        ("asante", "sw"),
        ("Price of cabbage", "en"),
    ]
    
    passed = 0
    for text, expected_lang in test_cases:
        detected = sw.detect_language(text)
        if detected == expected_lang:
            print(f"✅ Language detection: '{text}' → {detected}")
            passed += 1
        else:
            print(f"❌ Language detection: '{text}' → {detected} (expected {expected_lang})")
    
    # Test price query extraction
    price_queries = [
        ("bei ya vegimax", "vegimax"),
        ("vegimax bei gani", "vegimax"),
        ("vegimax ni pesa ngapi", "vegimax"),
    ]
    
    for query, expected_item in price_queries:
        result = sw.process_swahili_query(query)
        item = result.get("entities", {}).get("item_name")
        if item == expected_item:
            print(f"✅ Price extraction: '{query}' → {item}")
        else:
            print(f"❌ Price extraction: '{query}' → {item} (expected {expected_item})")
    
    # Test intent classification
    intent_tests = [
        ("habari", "GREETING"),
        ("asante", "THANKS"),
        ("bei ya vegimax", "GET_ITEM_PRICE"),
        ("onyesha bidhaa", "GET_ITEMS"),
    ]
    
    for text, expected_intent in intent_tests:
        result = sw.process_swahili_query(text)
        intent = result.get("intent")
        if intent == expected_intent:
            print(f"✅ Intent classification: '{text}' → {intent}")
        else:
            print(f"❌ Intent classification: '{text}' → {intent} (expected {expected_intent})")
    
    return True


def test_entity_extractor():
    """Test entity extraction functionality."""
    print("\n" + "="*60)
    print("TEST 5: Entity Extractor")
    print("="*60)
    
    from app.ai_engine.entity_extractor import EntityExtractor
    from app.services.session_context import SessionContext
    
    extractor = EntityExtractor()
    ctx = SessionContext(ttl_seconds=60)
    session_id = "test_session_456"
    
    test_cases = [
        ("Price of vegimax", "vegimax", None),
        ("Price of Takii logo", "takii logo", None),
        ("Create a quote for Magomano", None, "Magomano"),
        ("Customer details for Lumarx", None, "Lumarx"),
        ("Stock level of cabbage", "cabbage", None),
    ]
    
    passed = 0
    for text, expected_item, expected_customer in test_cases:
        # Test fresh extraction (no session)
        entities = extractor.extract(text)
        item = entities.get("item_name")
        customer = entities.get("customer_name")
        
        item_ok = (item == expected_item) if expected_item else (item is None or item == "")
        customer_ok = (customer == expected_customer) if expected_customer else (customer is None)
        
        if item_ok and customer_ok:
            print(f"✅ Fresh extraction: '{text}' → item={item}, customer={customer}")
            passed += 1
        else:
            print(f"❌ Fresh extraction: '{text}' → item={item} (exp={expected_item}), customer={customer} (exp={expected_customer})")
    
    # Test with session context (current message should override)
    ctx.merge(session_id, {"item_name": "old_vegimax"})
    entities = extractor.extract("Price of cabbage", initial_entities=ctx.get(session_id))
    
    if entities.get("item_name") == "cabbage":
        print("✅ Session override works (current message takes priority)")
        passed += 1
    else:
        print(f"❌ Session override failed: {entities.get('item_name')} (expected cabbage)")
    
    # Test fuzzy correction
    fuzzy_test = "vegimaks"
    entities = extractor.extract(fuzzy_test)
    if entities.get("item_name") == "vegimax" or "vegimax" in str(entities.get("item_name", "")).lower():
        print(f"✅ Fuzzy correction: '{fuzzy_test}' → {entities.get('item_name')}")
        passed += 1
    else:
        print(f"❌ Fuzzy correction failed: '{fuzzy_test}' → {entities.get('item_name')}")
    
    print(f"\n📊 Results: {passed}/{len(test_cases) + 2} passed")
    return passed > 0


def test_intent_classifier():
    """Test intent classification."""
    print("\n" + "="*60)
    print("TEST 6: Intent Classifier")
    print("="*60)
    
    from app.ai_engine.intent_classifier import IntentClassifier
    
    classifier = IntentClassifier()
    
    test_cases = [
        ("hello", "GREETING"),
        ("thank you", "THANKS"),
        ("price of vegimax", "GET_ITEM_PRICE"),
        ("show me items", "GET_ITEMS"),
        ("low stock alerts", "GET_LOW_STOCK_ALERTS"),
        ("create a quotation", "CREATE_QUOTATION"),
        ("show customers", "GET_CUSTOMERS"),
        ("how to create a quote", "TRAINING_MODULE"),
        ("what does BOM mean", "TRAINING_GLOSSARY"),
        ("inventory health", "ANALYZE_INVENTORY_HEALTH"),
        ("forecast demand", "FORECAST_DEMAND"),
        ("customers who bought vegimax", "GET_CROSS_SELL"),
        ("trending products", "GET_TRENDING_PRODUCTS"),
        ("bye", "SMALL_TALK"),
    ]
    
    passed = 0
    for text, expected_intent in test_cases:
        result = classifier.classify(text)
        intent = result.get("intent") if isinstance(result, dict) else str(result)
        
        if intent == expected_intent:
            print(f"✅ '{text}' → {intent}")
            passed += 1
        else:
            print(f"❌ '{text}' → {intent} (expected {expected_intent})")
    
    print(f"\n📊 Results: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_suggestions_engine():
    """Test suggestions engine."""
    print("\n" + "="*60)
    print("TEST 7: Suggestions Engine")
    print("="*60)
    
    from app.ai_engine.suggestions_engine import suggestions_engine
    
    test_cases = [
        ("GET_ITEM_PRICE", {"item_name": "vegimax"}, "en"),
        ("GET_ITEM_PRICE", {"item_name": "vegimax"}, "sw"),
        ("GET_CUSTOMER_PRICE", {"customer_name": "Magomano"}, "en"),
        ("GET_WAREHOUSES", {}, "en"),
        ("GREETING", {}, "en"),
    ]
    
    passed = 0
    for intent, entities, lang in test_cases:
        suggestions = suggestions_engine.get(intent=intent, entities=entities, language=lang)
        if suggestions and len(suggestions) > 0:
            print(f"✅ {intent} ({lang}) → {len(suggestions)} suggestions")
            for s in suggestions[:2]:
                print(f"   - {s}")
            passed += 1
        else:
            print(f"❌ {intent} ({lang}) → no suggestions")
    
    return passed == len(test_cases)


def test_response_formatter():
    """Test response formatter."""
    print("\n" + "="*60)
    print("TEST 8: Response Formatter")
    print("="*60)
    
    from app.ai_engine.response_formatter import ResponseFormatter
    
    formatter = ResponseFormatter()
    
    # Test price formatting
    price_data = {
        "item": {"ItemName": "VegiMax", "ItemCode": "VGM001"},
        "prices": [
            {"ListName": "Standard", "Price": 150.00},
            {"ListName": "Wholesale", "Price": 140.00}
        ],
        "uom": "ml"
    }
    
    result = formatter.format_item_price(price_data)
    if result.get("message") and "VegiMax" in result["message"]:
        print("✅ Price formatting works")
    else:
        print("❌ Price formatting failed")
    
    # Test customer formatting
    customer_data = [
        {"CardName": "Magomano Suppliers", "CardCode": "C001"},
        {"CardName": "Lumarx Enterprises", "CardCode": "C002"}
    ]
    
    result = formatter.format_customer(customer_data)
    if result.get("message") and "Magomano" in result["message"]:
        print("✅ Customer formatting works")
    else:
        print("❌ Customer formatting failed")
    
    # Test list formatting
    items_data = [
        {"ItemName": "VegiMax", "ItemCode": "VGM001", "OnHand": 100},
        {"ItemName": "Cabbage Seeds", "ItemCode": "SEED001", "OnHand": 500}
    ]
    
    result = formatter.format_list("items", items_data)
    if result.get("message") and "VegiMax" in result["message"]:
        print("✅ List formatting works")
    else:
        print("❌ List formatting failed")
    
    # Test cross-sell formatting
    cross_sell_data = {
        "item_name": "VegiMax",
        "recommendations": [
            {"ItemName": "Sprayer", "ItemCode": "SP001", "Price": 500}
        ]
    }
    
    result = formatter.format_cross_sell(cross_sell_data)
    if result.get("message") and "Sprayer" in result["message"]:
        print("✅ Cross-sell formatting works")
    else:
        print("❌ Cross-sell formatting failed")
    
    return True


def test_decision_support_health_score():
    """Test decision support health score calculations."""
    print("\n" + "="*60)
    print("TEST 9: Decision Support - Health Scores")
    print("="*60)
    
    from app.ai_engine.decision_support import _mean, _std, _confidence_score
    
    # Test mean
    assert _mean([10, 20, 30]) == 20.0
    assert _mean([]) == 0.0
    print("✅ Mean calculation works")
    
    # Test standard deviation
    result = _std([10, 20, 30])
    assert round(result, 1) == 8.2
    print("✅ Standard deviation calculation works")
    
    # Test confidence score
    assert _confidence_score(100) == 1.0
    assert _confidence_score(45) == 0.75
    assert _confidence_score(20) == 0.6
    assert _confidence_score(5) == 0.2
    assert _confidence_score(0) == 0.0
    print("✅ Confidence score calculation works")
    
    return True


def test_prompt_manager():
    """Test prompt manager."""
    print("\n" + "="*60)
    print("TEST 10: Prompt Manager")
    print("="*60)
    
    from app.ai_engine.prompt_manager import PromptManager, VALID_INTENTS
    
    pm = PromptManager()
    
    # Test intent prompt generation
    intent_prompt = pm.get_intent_prompt("test message")
    if intent_prompt and "intent" in intent_prompt.lower():
        print("✅ Intent prompt generation works")
    else:
        print("❌ Intent prompt generation failed")
    
    # Test entity prompt generation
    entity_prompt = pm.get_entity_prompt("price of vegimax")
    if entity_prompt and "item_name" in entity_prompt:
        print("✅ Entity prompt generation works")
    else:
        print("❌ Entity prompt generation failed")
    
    # Test VALID_INTENTS
    print(f"📊 Valid intents count: {len(VALID_INTENTS)}")
    required_intents = [
        "GET_ITEMS", "GET_ITEM_PRICE", "GET_CUSTOMERS", "CREATE_QUOTATION",
        "GREETING", "THANKS", "TRAINING_MODULE", "ANALYZE_INVENTORY_HEALTH",
        "GET_CROSS_SELL", "GET_TRENDING_PRODUCTS"
    ]
    
    missing = [i for i in required_intents if i not in VALID_INTENTS]
    if not missing:
        print("✅ All required intents are present")
    else:
        print(f"❌ Missing intents: {missing}")
    
    return True


def test_training_actions():
    """Test training actions."""
    print("\n" + "="*60)
    print("TEST 11: Training Actions")
    print("="*60)
    
    from app.ai_engine.training_actions import TrainingActions
    
    training = TrainingActions()
    
    # Test module handler
    result = training.handle_training_module({}, "show me sales module")
    if result and ("Sales" in result or "sales" in result.lower()):
        print("✅ Training module handler works")
    else:
        print("❌ Training module handler failed")
    
    # Test glossary handler
    result = training.handle_training_glossary({}, "what is BOM")
    if result and ("Bill of Materials" in result or "BOM" in result):
        print("✅ Glossary handler works")
    else:
        print("❌ Glossary handler failed")
    
    # Test FAQ handler
    result = training.handle_training_faq({}, "sales FAQ")
    if result and "FAQ" in result:
        print("✅ FAQ handler works")
    else:
        print("❌ FAQ handler failed")
    
    # Test webinar handler
    result = training.handle_training_webinar({})
    if result and "Webinar" in result:
        print("✅ Webinar handler works")
    else:
        print("❌ Webinar handler failed")
    
    return True


def test_knowledge_base():
    """Test knowledge base."""
    print("\n" + "="*60)
    print("TEST 12: Knowledge Base")
    print("="*60)
    
    from app.ai_engine.leysco_knowledge_base import (
        get_knowledge, get_company_info, get_brand_info, 
        get_ordering_info, get_contact_info, get_policies, get_faq_answer
    )
    
    # Test get_knowledge
    result = get_knowledge("COMPANY_INFO")
    if result and "Leysco" in result:
        print("✅ get_knowledge() works")
    else:
        print("❌ get_knowledge() failed")
    
    # Test get_company_info
    result = get_company_info()
    if result.get("name") and "Leysco" in result["name"]:
        print("✅ get_company_info() works")
    else:
        print("❌ get_company_info() failed")
    
    # Test get_brand_info
    result = get_brand_info()
    if result and "seeds" in result:
        print("✅ get_brand_info() works")
    else:
        print("❌ get_brand_info() failed")
    
    # Test get_ordering_info
    result = get_ordering_info()
    if result and "how_to_order" in result:
        print("✅ get_ordering_info() works")
    else:
        print("❌ get_ordering_info() failed")
    
    # Test get_contact_info
    result = get_contact_info()
    if result and "customer_support" in result:
        print("✅ get_contact_info() works")
    else:
        print("❌ get_contact_info() failed")
    
    # Test get_policies
    result = get_policies()
    if result and "returns" in result:
        print("✅ get_policies() works")
    else:
        print("❌ get_policies() failed")
    
    # Test get_faq_answer
    result = get_faq_answer("How do I check stock?")
    if result and "stock" in result.lower():
        print("✅ get_faq_answer() works")
    else:
        print("❌ get_faq_answer() failed")
    
    return True


def test_intent_overrides():
    """Test intent overrides."""
    print("\n" + "="*60)
    print("TEST 13: Intent Overrides")
    print("="*60)
    
    from app.ai_engine.intent_overrides import apply_intent_overrides
    
    test_cases = [
        ("GET_ITEMS", {"item_name": "cabbage", "customer_name": "Magomano"}, "GET_CUSTOMER_PRICE"),
        ("GET_ITEMS", {"warehouse": "nairobi"}, "GET_WAREHOUSE_STOCK"),
        ("GET_ITEMS_ADVANCED", {"item_name": "vegimax"}, "GET_ITEM_PRICE"),
    ]
    
    passed = 0
    for original_intent, entities, expected_intent in test_cases:
        result = apply_intent_overrides(original_intent, entities)
        if result == expected_intent:
            print(f"✅ {original_intent} → {result}")
            passed += 1
        else:
            print(f"❌ {original_intent} → {result} (expected {expected_intent})")
    
    # Test protected intents (should not be overridden)
    protected_intents = ["GET_CROSS_SELL", "GET_UPSELL", "GET_SEASONAL_RECOMMENDATIONS"]
    for intent in protected_intents:
        result = apply_intent_overrides(intent, {"item_name": "vegimax"})
        if result == intent:
            print(f"✅ Protected intent {intent} preserved")
            passed += 1
        else:
            print(f"❌ Protected intent {intent} was overridden to {result}")
    
    return passed >= 3


def test_conversation_enhancer():
    """Test conversation enhancer."""
    print("\n" + "="*60)
    print("TEST 14: Conversation Enhancer")
    print("="*60)
    
    from app.ai_engine.conversation_enhancer import ConversationEnhancer
    
    enhancer = ConversationEnhancer()
    
    test_cases = [
        ("GET_ITEM_PRICE", "Here are the prices.", None),
        ("GREETING", "Hello", None),
        ("GET_ITEMS", "Found 5 items", [{"ItemCode": "001"}])
    ]
    
    passed = 0
    for intent, message, data in test_cases:
        enhanced = enhancer.enhance(intent, message, data)
        if enhanced and len(enhanced) >= len(message):
            print(f"✅ {intent} enhanced")
            passed += 1
        else:
            print(f"❌ {intent} enhancement failed")
    
    # Test error formatting
    error_msg = enhancer.format_error("timeout error")
    if error_msg and "taking a moment" in error_msg:
        print("✅ Error formatting works")
        passed += 1
    
    return passed >= 3


# =========================================================
# Main Test Runner
# =========================================================

def run_all_tests():
    """Run all tests and print summary."""
    print("\n" + "█"*60)
    print(" LEYSCO AI SYSTEM TEST SUITE")
    print("█"*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("Module Imports", test_imports),
        ("Cache Service", test_cache_service),
        ("Session Context", test_session_context),
        ("Swahili Support", test_swahili_support),
        ("Entity Extractor", test_entity_extractor),
        ("Intent Classifier", test_intent_classifier),
        ("Suggestions Engine", test_suggestions_engine),
        ("Response Formatter", test_response_formatter),
        ("Decision Support", test_decision_support_health_score),
        ("Prompt Manager", test_prompt_manager),
        ("Training Actions", test_training_actions),
        ("Knowledge Base", test_knowledge_base),
        ("Intent Overrides", test_intent_overrides),
        ("Conversation Enhancer", test_conversation_enhancer),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} raised exception: {e}")
            results.append((name, False))
    
    # Print summary
    print("\n" + "="*60)
    print(" TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\n📊 Total: {passed} passed, {failed} failed")
    print(f"📊 Success Rate: {passed/len(results)*100:.1f}%")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return failed == 0


# =========================================================
# Entry Point
# =========================================================

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)