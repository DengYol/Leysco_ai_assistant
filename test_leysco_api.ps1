# ============================================================
# Leysco API Service Tester
# Tests all endpoints used by the LeyscoAPIService class
# ============================================================

param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Token = "",
    [string]$Username = "",
    [string]$Password = ""
)

# Colors for output
$Green = "Green"
$Red = "Red"
$Yellow = "Yellow"
$Cyan = "Cyan"
$White = "White"

function Write-Success { Write-Host "✅ $($args[0])" -ForegroundColor $Green }
function Write-Error { Write-Host "❌ $($args[0])" -ForegroundColor $Red }
function Write-Info { Write-Host "📌 $($args[0])" -ForegroundColor $Cyan }
function Write-Warning { Write-Host "⚠️ $($args[0])" -ForegroundColor $Yellow }
function Write-Test { Write-Host "`n🧪 TEST: $($args[0])" -ForegroundColor $White -BackgroundColor DarkBlue }
function Write-Separator { Write-Host ("=" * 60) -ForegroundColor $Gray }
function Write-Result { 
    if ($args[0]) { 
        Write-Host "   ✓ $($args[0])" -ForegroundColor $Green 
    } else {
        Write-Host "   ✗ $($args[1])" -ForegroundColor $Red
    }
}

# ============================================================
# Helper Functions
# ============================================================

function Get-AuthHeader {
    if ($Token) {
        return @{ "Authorization" = "Bearer $Token" }
    }
    return @{}
}

function Invoke-Test {
    param(
        [string]$Name,
        [string]$Method = "GET",
        [string]$Endpoint,
        [object]$Body = $null,
        [int]$ExpectedStatus = 200,
        [switch]$NoOutput
    )
    
    $url = "$BaseUrl$Endpoint"
    $headers = Get-AuthHeader
    $headers["Content-Type"] = "application/json"
    
    Write-Host ""
    Write-Host "🔹 $Name" -ForegroundColor $Cyan
    Write-Host "   $Method $url" -ForegroundColor $DarkGray
    
    try {
        $params = @{
            Uri = $url
            Method = $Method
            Headers = $headers
            ContentType = "application/json"
            TimeoutSec = 30
        }
        
        if ($Body -and ($Method -eq "POST" -or $Method -eq "PUT")) {
            $params["Body"] = ($Body | ConvertTo-Json -Depth 10)
            Write-Host "   Body: $($params["Body"])" -ForegroundColor $DarkGray
        }
        
        $response = Invoke-RestMethod @params -ErrorAction Stop
        
        if (-not $NoOutput) {
            $responseJson = $response | ConvertTo-Json -Depth 5
            if ($responseJson.Length -gt 500) {
                Write-Host "   Response: $($responseJson.Substring(0, 500))..." -ForegroundColor $DarkGray
            } else {
                Write-Host "   Response: $responseJson" -ForegroundColor $DarkGray
            }
        }
        
        Write-Success "$Name completed successfully"
        return $response
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        Write-Error "$Name failed: HTTP $statusCode - $($_.Exception.Message)"
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $reader.BaseStream.Position = 0
            $reader.DiscardBufferedData()
            $errorBody = $reader.ReadToEnd()
            Write-Host "   Error Body: $errorBody" -ForegroundColor $Red
        }
        return $null
    }
}

# ============================================================
# Authentication Setup
# ============================================================

Clear-Host
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor $Cyan
Write-Host "║                 LEYSCO API SERVICE TESTER                     ║" -ForegroundColor $Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor $Cyan
Write-Host ""
Write-Info "Base URL: $BaseUrl"

# Try to get token if not provided
if (-not $Token -and $Username -and $Password) {
    Write-Test "Authentication - Login"
    $loginResult = Invoke-Test -Name "Login" -Method "POST" -Endpoint "/api/v1/login" -Body @{
        username = $Username
        password = $Password
    }
    
    if ($loginResult -and $loginResult.token) {
        $Token = $loginResult.token
        Write-Success "Authentication successful, token obtained"
    } else {
        Write-Warning "Could not authenticate. Tests will run without token (may fail for protected endpoints)"
    }
} elseif (-not $Token) {
    Write-Warning "No token provided. Some endpoints may return 401 Unauthorized"
}

# ============================================================
# Health Check Tests
# ============================================================

Write-Test "1. Health Check"
$health = Invoke-Test -Name "Health Check" -Endpoint "/health" -ExpectedStatus 200
if ($health) { Write-Result "Service is healthy" }

# ============================================================
# AI Module Tests
# ============================================================

Write-Test "2. AI Chat Module"

# 2.1 Send a chat message
$chatMessage = "Hello, I need help with pricing"
Write-Info "Sending chat message: '$chatMessage'"
$chatResponse = Invoke-Test -Name "AI Chat" -Method "POST" -Endpoint "/api/ai/chat" -Body @{
    message = $chatMessage
    session_id = "test_session_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    stream = $false
}

if ($chatResponse) {
    Write-Result "Response received" "Message: $($chatResponse.result)"
    $sessionId = $chatResponse.session_id
}

# 2.2 Get chat history
$history = Invoke-Test -Name "Get Chat History" -Endpoint "/api/ai/session/history?limit=10"
if ($history -and $history.history) {
    Write-Result "Retrieved $($history.history.Count) messages"
}

# 2.3 Get session summary
$sessionSummary = Invoke-Test -Name "Get Session Summary" -Endpoint "/api/ai/session/summary"
if ($sessionSummary) {
    Write-Result "Session found" "Messages: $($sessionSummary.message_count), Intent: $($sessionSummary.last_intent)"
}

# 2.4 Clear session
Invoke-Test -Name "Clear Session" -Method "POST" -Endpoint "/api/ai/session/clear" -Body @{
    session_id = $sessionId
} -NoOutput

# ============================================================
# Notification Tests
# ============================================================

Write-Test "3. Notifications Module"

# 3.1 Get notifications
$notifications = Invoke-Test -Name "Get Notifications" -Endpoint "/api/ai/notifications?unread_only=true"
if ($notifications -and $notifications.notifications) {
    Write-Result "Found $($notifications.notifications.Count) notifications" "Unread count: $($notifications.unread_count)"
}

# 3.2 Get unread count
$unreadCount = Invoke-Test -Name "Get Unread Count" -Endpoint "/api/ai/notifications/unread-count"
if ($unreadCount) {
    Write-Result "Unread notifications: $($unreadCount.unread_count)"
}

# 3.3 Mark notification read (if any)
if ($notifications -and $notifications.notifications -and $notifications.notifications.Count -gt 0) {
    $firstNotifId = $notifications.notifications[0].id
    Invoke-Test -Name "Mark Notification Read" -Method "POST" -Endpoint "/api/ai/notifications/$firstNotifId/read" -NoOutput
    Write-Result "Marked notification $firstNotifId as read"
}

# 3.4 Scan for notifications
$scanResult = Invoke-Test -Name "Scan Notifications" -Method "POST" -Endpoint "/api/ai/notifications/scan" -Body @{} -NoOutput
if ($scanResult) { Write-Result "Notification scan triggered" }

# ============================================================
# Proactive Suggestions
# ============================================================

Write-Test "4. Proactive Suggestions"
$proactive = Invoke-Test -Name "Get Proactive Suggestions" -Endpoint "/api/ai/proactive"
if ($proactive -and $proactive.suggestions) {
    Write-Result "Found $($proactive.suggestions.Count) suggestions"
}

# ============================================================
# Analytics Tests
# ============================================================

Write-Test "5. Analytics Module"

# 5.1 Analytics summary
$analytics = Invoke-Test -Name "Get Analytics Summary" -Endpoint "/api/ai/analytics/summary?period=week"
if ($analytics) {
    Write-Result "Total queries: $($analytics.total_queries)" "Success rate: $($analytics.success_rate)%"
}

# 5.2 Intent analytics
$intentAnalytics = Invoke-Test -Name "Get Intent Analytics" -Endpoint "/api/ai/analytics/intents?days=7"
if ($intentAnalytics) {
    Write-Result "Intent analytics retrieved"
}

# 5.3 User analytics (if manager)
$userAnalytics = Invoke-Test -Name "Get User Analytics" -Endpoint "/api/ai/analytics/users?days=7"
if ($userAnalytics) {
    Write-Result "User analytics retrieved"
}

# 5.4 Performance stats
$performance = Invoke-Test -Name "Get Performance Stats" -Endpoint "/api/ai/performance/stats"
if ($performance) {
    Write-Result "Performance stats retrieved"
}

# ============================================================
# Forecasting Tests
# ============================================================

Write-Test "6. Forecasting Module"

# 6.1 ML Forecast
$mlForecast = Invoke-Test -Name "ML Forecast" -Method "POST" -Endpoint "/api/ai/forecast/ml" -Body @{
    item_code = "TEST001"
    periods = 30
}
if ($mlForecast) {
    Write-Result "ML forecast generated"
}

# 6.2 Seasonal forecast
$seasonal = Invoke-Test -Name "Seasonal Forecast" -Endpoint "/api/ai/forecast/seasonal?item_code=TEST001"
if ($seasonal) {
    Write-Result "Seasonal forecast retrieved"
}

# ============================================================
# Anomaly Detection Tests
# ============================================================

Write-Test "7. Anomaly Detection"

# 7.1 Scan anomalies
$scanAnomalies = Invoke-Test -Name "Scan Anomalies" -Method "POST" -Endpoint "/api/ai/anomalies/scan" -Body @{
    scan_type = "full"
}
if ($scanAnomalies) { Write-Result "Anomaly scan triggered" }

# 7.2 Sales anomalies
$salesAnomalies = Invoke-Test -Name "Get Sales Anomalies" -Endpoint "/api/ai/anomalies/sales?days=30"
if ($salesAnomalies) {
    Write-Result "Sales anomalies retrieved"
}

# 7.3 Stock anomalies
$stockAnomalies = Invoke-Test -Name "Get Stock Anomalies" -Endpoint "/api/ai/anomalies/stock"
if ($stockAnomalies) {
    Write-Result "Stock anomalies retrieved"
}

# 7.4 Pricing anomalies
$pricingAnomalies = Invoke-Test -Name "Get Pricing Anomalies" -Endpoint "/api/ai/anomalies/pricing"
if ($pricingAnomalies) {
    Write-Result "Pricing anomalies retrieved"
}

# ============================================================
# Knowledge Base Tests
# ============================================================

Write-Test "8. Knowledge Base"

# 8.1 Search knowledge base
$searchResults = Invoke-Test -Name "Search Knowledge Base" -Endpoint "/api/ai/knowledge/search?query=pricing&limit=5"
if ($searchResults -and $searchResults.results) {
    Write-Result "Found $($searchResults.results.Count) results"
}

# 8.2 Get knowledge stats
$knowledgeStats = Invoke-Test -Name "Get Knowledge Stats" -Endpoint "/api/ai/knowledge/stats"
if ($knowledgeStats) {
    Write-Result "Documents: $($knowledgeStats.total_documents), Vectors: $($knowledgeStats.total_vectors)"
}

# ============================================================
# Knowledge Graph Tests
# ============================================================

Write-Test "9. Knowledge Graph"

# 9.1 Build graph
$buildGraph = Invoke-Test -Name "Build Knowledge Graph" -Method "POST" -Endpoint "/api/ai/graph/build" -Body @{
    force_rebuild = $true
} -NoOutput
if ($buildGraph) { Write-Result "Knowledge graph built" }

# 9.2 Cross-sell recommendations
$crossSell = Invoke-Test -Name "Cross-sell Recommendations" -Endpoint "/api/ai/graph/recommendations/cross-sell/TEST001?limit=5"
if ($crossSell -and $crossSell.recommendations) {
    Write-Result "Found $($crossSell.recommendations.Count) cross-sell recommendations"
}

# 9.3 Upsell recommendations
$upsell = Invoke-Test -Name "Upsell Recommendations" -Endpoint "/api/ai/graph/recommendations/upsell/TEST001?limit=5"
if ($upsell -and $upsell.recommendations) {
    Write-Result "Found $($upsell.recommendations.Count) upsell recommendations"
}

# 9.4 Customer graph
$customerGraph = Invoke-Test -Name "Get Customer Graph" -Endpoint "/api/ai/graph/customer/CUST001"
if ($customerGraph) {
    Write-Result "Customer graph retrieved"
}

# 9.5 Substitutes
$substitutes = Invoke-Test -Name "Get Substitutes" -Endpoint "/api/ai/graph/substitutes/TEST001?limit=5"
if ($substitutes -and $substitutes.products) {
    Write-Result "Found $($substitutes.products.Count) substitutes"
}

# 9.6 Complements
$complements = Invoke-Test -Name "Get Complements" -Endpoint "/api/ai/graph/complements/TEST001?limit=5"
if ($complements -and $complements.products) {
    Write-Result "Found $($complements.products.Count) complements"
}

# 9.7 Graph stats
$graphStats = Invoke-Test -Name "Get Graph Stats" -Endpoint "/api/ai/graph/stats"
if ($graphStats) {
    Write-Result "Nodes: $($graphStats.node_count), Edges: $($graphStats.edge_count)"
}

# ============================================================
# Cache Tests
# ============================================================

Write-Test "10. Cache Management"

# 10.1 Get cache stats
$cacheStats = Invoke-Test -Name "Get Cache Stats" -Endpoint "/api/ai/cache/stats"
if ($cacheStats) {
    Write-Result "Hits: $($cacheStats.hits), Misses: $($cacheStats.misses), Hit rate: $($cacheStats.hit_rate)%"
}

# 10.2 Clear cache
Invoke-Test -Name "Clear Cache" -Method "POST" -Endpoint "/api/ai/cache/clear" -Body @{} -NoOutput
Write-Result "Cache cleared"

# ============================================================
# Feedback Tests
# ============================================================

Write-Test "11. Feedback Tracking"

# 11.1 Track suggestion click
$feedback = Invoke-Test -Name "Track Suggestion Click" -Method "POST" -Endpoint "/api/ai/feedback/suggestion-clicked" -Body @{
    suggestion = "Check price of vegimax"
    intent = "GET_ITEM_PRICE"
    session_id = "test_session"
} -NoOutput
if ($feedback) { Write-Result "Suggestion click tracked" }

# 11.2 Get feedback performance
$feedbackPerf = Invoke-Test -Name "Get Feedback Performance" -Endpoint "/api/ai/feedback/performance?days=7"
if ($feedbackPerf) {
    Write-Result "Click rate: $($feedbackPerf.click_rate)%"
}

# ============================================================
# Dashboard Tests
# ============================================================

Write-Test "12. Dashboard"
$dashboard = Invoke-Test -Name "Get Dashboard Data" -Endpoint "/api/ai/dashboard"
if ($dashboard) {
    Write-Result "Dashboard data retrieved"
}

# ============================================================
# API Info Tests
# ============================================================

Write-Test "13. API Information"
$apiInfo = Invoke-Test -Name "Get API Info" -Endpoint "/api/info"
if ($apiInfo) {
    Write-Result "Version: $($apiInfo.version)" "Service: $($apiInfo.name)"
}

# ============================================================
# Business Partner Tests (if token available)
# ============================================================

if ($Token) {
    Write-Test "14. Business Partners (requires auth)"
    
    # 14.1 Get customers
    $customers = Invoke-Test -Name "Get Customers" -Endpoint "/api/v1/TEST001/customers?limit=5"
    if ($customers -and $customers.data) {
        Write-Result "Found $($customers.data.Count) customers"
    }
    
    # 14.2 Get customer by code
    $customerDetail = Invoke-Test -Name "Get Customer Detail" -Endpoint "/api/v1/TEST001/customers/CUST001"
    if ($customerDetail) {
        Write-Result "Customer details retrieved"
    }
    
    # 14.3 Get items
    $items = Invoke-Test -Name "Get Items" -Endpoint "/api/v1/TEST001/items?limit=5"
    if ($items -and $items.data) {
        Write-Result "Found $($items.data.Count) items"
    }
    
    # 14.4 Get inventory
    $inventory = Invoke-Test -Name "Get Inventory" -Endpoint "/api/v1/TEST001/inventory/?limit=5"
    if ($inventory -and $inventory.data) {
        Write-Result "Found $($inventory.data.Count) inventory items"
    }
    
    # 14.5 Get price
    $price = Invoke-Test -Name "Get Price" -Endpoint "/api/v1/TEST001/price?item_code=ITEM001"
    if ($price) {
        Write-Result "Price: $($price.price) $($price.currency)"
    }
    
    # 14.6 Get orders
    $orders = Invoke-Test -Name "Get Orders" -Endpoint "/api/v1/TEST001/orders?limit=5"
    if ($orders -and $orders.data) {
        Write-Result "Found $($orders.data.Count) orders"
    }
    
    # 14.7 Get outstanding deliveries
    $deliveries = Invoke-Test -Name "Get Outstanding Deliveries" -Endpoint "/api/v1/TEST001/deliveries/outstanding?limit=5"
    if ($deliveries -and $deliveries.data) {
        Write-Result "Found $($deliveries.data.Count) outstanding deliveries"
    }
    
    # 14.8 Get expenses
    $expenses = Invoke-Test -Name "Get Expenses" -Endpoint "/api/v1/TEST001/expenses?limit=5"
    if ($expenses -and $expenses.data) {
        Write-Result "Found $($expenses.data.Count) expenses"
    }
}

# ============================================================
# Debug Routes Tests
# ============================================================

Write-Test "15. Debug Routes"

# 15.1 Get price debug
$debugPrice = Invoke-Test -Name "Debug Price" -Endpoint "/debug/price/ITEM001"
if ($debugPrice) { Write-Result "Price debug info retrieved" }

# 15.2 Get price lists
$priceLists = Invoke-Test -Name "Debug Price Lists" -Endpoint "/debug/price-lists"
if ($priceLists) { Write-Result "Found $($priceLists.Count) price lists" }

# 15.3 Get warehouses
$warehouses = Invoke-Test -Name "Debug Warehouses" -Endpoint "/debug/warehouses"
if ($warehouses) { Write-Result "Found $($warehouses.Count) warehouses" }

# 15.4 Probe special prices
$specialPrices = Invoke-Test -Name "Probe Special Prices" -Endpoint "/debug/probe-special-prices?item=ITEM001"
if ($specialPrices) { Write-Result "Special prices probed" }

# ============================================================
# Summary Report
# ============================================================

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor $Green
Write-Host "║                      TEST SUMMARY                            ║" -ForegroundColor $Green
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor $Green
Write-Host ""
Write-Info "Base URL: $BaseUrl"
if ($Token) { 
    Write-Success "Authentication: Valid token provided"
} else {
    Write-Warning "Authentication: No token - some tests may have failed with 401"
}
Write-Host ""
Write-Info "Tests Completed:"
Write-Host "   • AI Chat Module (4 tests)" -ForegroundColor $Cyan
Write-Host "   • Notifications (4 tests)" -ForegroundColor $Cyan
Write-Host "   • Proactive Suggestions (1 test)" -ForegroundColor $Cyan
Write-Host "   • Analytics (4 tests)" -ForegroundColor $Cyan
Write-Host "   • Forecasting (2 tests)" -ForegroundColor $Cyan
Write-Host "   • Anomaly Detection (4 tests)" -ForegroundColor $Cyan
Write-Host "   • Knowledge Base (2 tests)" -ForegroundColor $Cyan
Write-Host "   • Knowledge Graph (8 tests)" -ForegroundColor $Cyan
Write-Host "   • Cache (2 tests)" -ForegroundColor $Cyan
Write-Host "   • Feedback (2 tests)" -ForegroundColor $Cyan
Write-Host "   • Dashboard (1 test)" -ForegroundColor $Cyan
Write-Host "   • API Info (1 test)" -ForegroundColor $Cyan
if ($Token) {
    Write-Host "   • Business Partners (8 tests)" -ForegroundColor $Cyan
}
Write-Host "   • Debug Routes (4 tests)" -ForegroundColor $Cyan
Write-Host ""
Write-Success "Testing complete!"

# Optional: Save results to file
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$resultFile = "leysco_api_test_results_$timestamp.json"
$resultsObject = @{
    timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    base_url = $BaseUrl
    authenticated = [bool]$Token
    tests = @{}
}

Write-Info "Results saved to: $resultFile"