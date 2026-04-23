# ============================================================
# BACKEND-FIRST SaaS TESTING SCRIPT (curl.exe based, fixed JSON)
# Tests all API endpoints via HTTP calls only
# ============================================================

$BASE = "https://mme-backend-ibrd.onrender.com"
$PASS = 0
$FAIL = 0
$RESULTS = @()
$TIMEOUT = 60

function Test-API {
    param (
        [string]$Name,
        [string]$Method,
        [string]$Url,
        [string]$Token = "",
        [string]$Body = "",
        [string]$ContentType = "application/json",
        [int]$ExpectedStatus = 200,
        [string]$ExpectedContains = "",
        [string]$Description = ""
    )

    $fullUrl = "$BASE$Url"
    Write-Host "`n--- TEST: $Name ---" -ForegroundColor Cyan
    Write-Host "  $Method $Url" -ForegroundColor DarkGray
    if ($Description) { Write-Host "  DESC: $Description" -ForegroundColor DarkGray }

    $curlArgs = @("-s", "--max-time", "$TIMEOUT", "-X", $Method, "-w", "`n%{http_code}", $fullUrl)
    
    if ($Token) {
        $curlArgs += @("-H", "Authorization: Bearer $Token")
    }
    
    if ($Body -and $Method -ne "GET") {
        $curlArgs += @("-H", "Content-Type: $ContentType", "-d", $Body)
    }

    $rawOutput = & curl.exe @curlArgs 2>&1
    $outputStr = $rawOutput -join "`n"
    $lines = $outputStr.Trim() -split "`n"
    $statusCode = 0
    try { $statusCode = [int]($lines[-1].Trim()) } catch { $statusCode = 0 }
    $responseBody = if ($lines.Length -gt 1) { ($lines[0..($lines.Length - 2)] -join "`n").Trim() } else { "" }

    $passed = $true
    $reason = ""

    if ($statusCode -ne $ExpectedStatus) {
        $passed = $false
        $reason = "Expected $ExpectedStatus, got $statusCode"
    }

    if ($ExpectedContains -and $responseBody -notlike "*$ExpectedContains*") {
        $passed = $false
        if ($reason) { $reason += " | " }
        $reason += "Missing '$ExpectedContains'"
    }

    if ($passed) {
        Write-Host "  PASS (HTTP $statusCode)" -ForegroundColor Green
        $script:PASS++
    } else {
        Write-Host "  FAIL: $reason" -ForegroundColor Red
        $truncated = if ($responseBody.Length -gt 250) { $responseBody.Substring(0,250) + "..." } else { $responseBody }
        Write-Host "  Body: $truncated" -ForegroundColor Yellow
        $script:FAIL++
    }

    $script:RESULTS += [PSCustomObject]@{
        Test = $Name
        Result = if ($passed) { "PASS" } else { "FAIL" }
        HTTP = $statusCode
        Detail = if ($passed) { "" } else { $reason }
    }

    return @{ StatusCode = $statusCode; Content = $responseBody; Passed = $passed }
}

Write-Host "============================================" -ForegroundColor Magenta
Write-Host " BACKEND-FIRST SaaS SYSTEM TEST" -ForegroundColor Magenta
Write-Host " Target: $BASE" -ForegroundColor Magenta
Write-Host " $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta


# ============================================================
# PHASE 1: HEALTH
# ============================================================
Write-Host "`n=== PHASE 1: HEALTH ===" -ForegroundColor Yellow

Test-API -Name "Health Check" -Method "GET" -Url "/health" `
    -ExpectedContains "ok" -Description "Server alive"


# ============================================================
# PHASE 2: AUTHENTICATION
# ============================================================
Write-Host "`n=== PHASE 2: AUTHENTICATION ===" -ForegroundColor Yellow

Test-API -Name "Login - Bad Creds" -Method "POST" -Url "/api/v1/login" `
    -Body "username=wrong@email.com&password=badpass" -ContentType "application/x-www-form-urlencoded" `
    -ExpectedStatus 401 -ExpectedContains "Incorrect credentials" `
    -Description "Reject bad credentials"

$loginResult = Test-API -Name "Login - Good Creds" -Method "POST" -Url "/api/v1/login" `
    -Body "username=test@gmail.com&password=123456" -ContentType "application/x-www-form-urlencoded" `
    -ExpectedContains "access_token" -Description "Return JWT tokens"

$TOKEN = ""
$REFRESH = ""
if ($loginResult.Passed) {
    $data = $loginResult.Content | ConvertFrom-Json
    $TOKEN = $data.access_token
    $REFRESH = $data.refresh_token
    Write-Host "  Tokens acquired" -ForegroundColor DarkGreen
}

Test-API -Name "Validate Token /me" -Method "GET" -Url "/api/v1/me" `
    -Token $TOKEN -ExpectedContains "test@gmail.com" `
    -Description "Return user info from JWT"

Test-API -Name "No Auth - /me" -Method "GET" -Url "/api/v1/me" `
    -ExpectedStatus 401 -Description "Reject unauthenticated"

Test-API -Name "Bad Token - /me" -Method "GET" -Url "/api/v1/me" `
    -Token "fake_invalid_token_xyz" -ExpectedStatus 401 `
    -Description "Reject forged JWT"

# Write refresh body to temp file to avoid escaping issues
$refreshBody = '{"refresh_token": "' + $REFRESH + '"}'
$refreshTmp = "e:\NME-project\_tmp_refresh.json"
[System.IO.File]::WriteAllText($refreshTmp, $refreshBody)

$refreshResult = Test-API -Name "Token Refresh" -Method "POST" -Url "/api/v1/refresh" `
    -Body "@$refreshTmp" `
    -ExpectedContains "access_token" -Description "Rotate tokens"

if ($refreshResult.Passed) {
    $rData = $refreshResult.Content | ConvertFrom-Json
    $TOKEN = $rData.access_token
    $REFRESH = $rData.refresh_token
    Write-Host "  Tokens rotated" -ForegroundColor DarkGreen
}

# Old refresh token test
$oldRefreshBody = '{"refresh_token": "expired_fake_token"}'
$oldRefreshTmp = "e:\NME-project\_tmp_old_refresh.json"
[System.IO.File]::WriteAllText($oldRefreshTmp, $oldRefreshBody)

Test-API -Name "Old Refresh Rejected" -Method "POST" -Url "/api/v1/refresh" `
    -Body "@$oldRefreshTmp" `
    -ExpectedStatus 401 -Description "Old refresh token rejected"


# ============================================================
# PHASE 3: PRODUCTS
# ============================================================
Write-Host "`n=== PHASE 3: PRODUCTS ===" -ForegroundColor Yellow

$productsResult = Test-API -Name "List Products" -Method "GET" -Url "/api/v1/products/" `
    -Token $TOKEN -Description "Org-scoped product list"

$ts = Get-Date -Format "HHmmss"
$createProdJson = '{"name":"TestProd' + $ts + '","sku":"TST-' + $ts + '","category":"Testing","cost_price":10.5,"selling_price":25.0,"lead_time_days":5}'
$createTmp = "e:\NME-project\_tmp_create_prod.json"
[System.IO.File]::WriteAllText($createTmp, $createProdJson)

$createResult = Test-API -Name "Create Product" -Method "POST" -Url "/api/v1/products/" `
    -Token $TOKEN -Body "@$createTmp" -ExpectedContains "id" `
    -Description "Create product (plan-limited)"

$PRODUCT_ID = $null
if ($createResult.Passed) {
    $pData = $createResult.Content | ConvertFrom-Json
    $PRODUCT_ID = $pData.id
    Write-Host "  Product ID: $PRODUCT_ID" -ForegroundColor DarkGreen
}

if ($PRODUCT_ID) {
    # Duplicate SKU
    Test-API -Name "Duplicate SKU Reject" -Method "POST" -Url "/api/v1/products/" `
        -Token $TOKEN -Body "@$createTmp" -ExpectedStatus 400 `
        -ExpectedContains "SKU already exists" -Description "Reject duplicate SKU"

    # Update product
    $updateJson = '{"name":"Updated' + $ts + '","sku":"TST-' + $ts + '","category":"Updated","cost_price":12.0,"selling_price":30.0,"lead_time_days":7}'
    $updateTmp = "e:\NME-project\_tmp_update_prod.json"
    [System.IO.File]::WriteAllText($updateTmp, $updateJson)

    Test-API -Name "Update Product" -Method "PUT" -Url "/api/v1/products/$PRODUCT_ID" `
        -Token $TOKEN -Body "@$updateTmp" -ExpectedContains "Updated" `
        -Description "Update product fields"
}


# ============================================================
# PHASE 4: INVENTORY
# ============================================================
Write-Host "`n=== PHASE 4: INVENTORY ===" -ForegroundColor Yellow

Test-API -Name "Inventory Summary" -Method "GET" -Url "/api/v1/inventory/summary" `
    -Token $TOKEN -Description "Org-scoped inventory"

if ($PRODUCT_ID) {
    $addStockJson = '{"product_id":' + $PRODUCT_ID + ',"quantity":50}'
    $addStockTmp = "e:\NME-project\_tmp_add_stock.json"
    [System.IO.File]::WriteAllText($addStockTmp, $addStockJson)

    Test-API -Name "Add Stock" -Method "POST" -Url "/api/v1/inventory/add-stock" `
        -Token $TOKEN -Body "@$addStockTmp" `
        -ExpectedContains "quantity_on_hand" -Description "Add stock to product"

    Test-API -Name "Get Inventory" -Method "GET" -Url "/api/v1/inventory/$PRODUCT_ID" `
        -Token $TOKEN -ExpectedContains "quantity_on_hand" `
        -Description "Get product inventory"
}


# ============================================================
# PHASE 5: SALES
# ============================================================
Write-Host "`n=== PHASE 5: SALES ===" -ForegroundColor Yellow

if ($PRODUCT_ID) {
    $saleJson = '{"product_id":' + $PRODUCT_ID + ',"quantity_sold":5}'
    $saleTmp = "e:\NME-project\_tmp_sale.json"
    [System.IO.File]::WriteAllText($saleTmp, $saleJson)

    Test-API -Name "Record Sale" -Method "POST" -Url "/api/v1/sales/" `
        -Token $TOKEN -Body "@$saleTmp" `
        -ExpectedContains "Sale recorded" -Description "Atomic sale + inv deduction"

    $oversellJson = '{"product_id":' + $PRODUCT_ID + ',"quantity_sold":99999}'
    $oversellTmp = "e:\NME-project\_tmp_oversell.json"
    [System.IO.File]::WriteAllText($oversellTmp, $oversellJson)

    Test-API -Name "Oversell Reject" -Method "POST" -Url "/api/v1/sales/" `
        -Token $TOKEN -Body "@$oversellTmp" `
        -ExpectedStatus 400 -ExpectedContains "Not enough stock" `
        -Description "Reject sale exceeding stock"

    Test-API -Name "Sales History" -Method "GET" -Url "/api/v1/sales/history/$PRODUCT_ID" `
        -Token $TOKEN -Description "7-day sales history"
}


# ============================================================
# PHASE 6: ORDERS & CONTACTS
# ============================================================
Write-Host "`n=== PHASE 6: ORDERS & CONTACTS ===" -ForegroundColor Yellow

Test-API -Name "List Contacts" -Method "GET" -Url "/api/v1/contacts" `
    -Token $TOKEN -Description "Org-scoped contacts"

$contactJson = '{"name":"TestSupplier' + $ts + '","phone":"555' + $ts + '","type":"supplier"}'
$contactTmp = "e:\NME-project\_tmp_contact.json"
[System.IO.File]::WriteAllText($contactTmp, $contactJson)

$contactResult = Test-API -Name "Create Contact" -Method "POST" -Url "/api/v1/contacts" `
    -Token $TOKEN -Body "@$contactTmp" -ExpectedContains "id" `
    -Description "Create supplier contact"

$CONTACT_ID = $null
if ($contactResult.Passed) {
    $cData = $contactResult.Content | ConvertFrom-Json
    $CONTACT_ID = $cData.id
    Write-Host "  Contact ID: $CONTACT_ID" -ForegroundColor DarkGreen
}

$ORDER_ID = $null
if ($CONTACT_ID -and $PRODUCT_ID) {
    $orderJson = '{"contact_id":' + $CONTACT_ID + ',"items":[{"product_id":' + $PRODUCT_ID + ',"quantity":2}]}'
    $orderTmp = "e:\NME-project\_tmp_order.json"
    [System.IO.File]::WriteAllText($orderTmp, $orderJson)

    $orderResult = Test-API -Name "Create Order" -Method "POST" -Url "/api/v1/orders" `
        -Token $TOKEN -Body "@$orderTmp" -ExpectedContains "id" `
        -Description "Server-computed total"

    if ($orderResult.Passed) {
        $oData = $orderResult.Content | ConvertFrom-Json
        $ORDER_ID = $oData.id
        Write-Host "  Order ID: $ORDER_ID, Total: $($oData.total_amount)" -ForegroundColor DarkGreen
    }

    if ($ORDER_ID) {
        Test-API -Name "Get Order" -Method "GET" -Url "/api/v1/orders/$ORDER_ID" `
            -Token $TOKEN -ExpectedContains "total_amount" `
            -Description "Fetch order (org-scoped)"

        $statusTmp = "e:\NME-project\_tmp_status.json"
        [System.IO.File]::WriteAllText($statusTmp, '{"status":"confirmed"}')

        Test-API -Name "Status: pending->confirmed" -Method "PATCH" -Url "/api/v1/orders/$ORDER_ID/status" `
            -Token $TOKEN -Body "@$statusTmp" `
            -ExpectedContains "confirmed" -Description "Valid transition"

        $badStatusTmp = "e:\NME-project\_tmp_bad_status.json"
        [System.IO.File]::WriteAllText($badStatusTmp, '{"status":"delivered"}')

        Test-API -Name "Invalid Transition" -Method "PATCH" -Url "/api/v1/orders/$ORDER_ID/status" `
            -Token $TOKEN -Body "@$badStatusTmp" `
            -ExpectedStatus 400 -ExpectedContains "Invalid transition" `
            -Description "Reject invalid state change"
    }

    Test-API -Name "List Orders" -Method "GET" -Url "/api/v1/orders" `
        -Token $TOKEN -Description "All org orders"

    if ($CONTACT_ID) {
        Test-API -Name "Contact Stats" -Method "GET" -Url "/api/v1/contacts/$CONTACT_ID/stats" `
            -Token $TOKEN -ExpectedContains "total_orders" `
            -Description "Aggregated contact stats"
    }
}


# ============================================================
# PHASE 7: BILLING
# ============================================================
Write-Host "`n=== PHASE 7: BILLING ===" -ForegroundColor Yellow

Test-API -Name "Billing Status" -Method "GET" -Url "/api/v1/billing/status" `
    -Token $TOKEN -ExpectedContains "plan" `
    -Description "Plan, limits, usage"

$upgradeTmp = "e:\NME-project\_tmp_upgrade.json"
[System.IO.File]::WriteAllText($upgradeTmp, '{"plan":"pro"}')

Test-API -Name "Upgrade to Pro" -Method "POST" -Url "/api/v1/billing/upgrade" `
    -Token $TOKEN -Body "@$upgradeTmp" `
    -Description "Simulated pro upgrade"

$billingCheck = Test-API -Name "Verify Pro Plan" -Method "GET" -Url "/api/v1/billing/status" `
    -Token $TOKEN -ExpectedContains "pro" `
    -Description "Confirm plan is pro"

Test-API -Name "Downgrade to Free" -Method "POST" -Url "/api/v1/billing/downgrade" `
    -Token $TOKEN -ExpectedContains "free" `
    -Description "Downgrade to free"

Test-API -Name "Double Downgrade Reject" -Method "POST" -Url "/api/v1/billing/downgrade" `
    -Token $TOKEN -ExpectedStatus 400 -ExpectedContains "Already on the free plan" `
    -Description "Reject redundant downgrade"


# ============================================================
# PHASE 8: PREDICTIONS
# ============================================================
Write-Host "`n=== PHASE 8: PREDICTIONS ===" -ForegroundColor Yellow

if ($PRODUCT_ID) {
    Test-API -Name "Get Prediction" -Method "GET" -Url "/api/v1/predictions/$PRODUCT_ID" `
        -Token $TOKEN -Description "AI prediction (subscription-gated)"
}


# ============================================================
# PHASE 9: NOTIFICATIONS
# ============================================================
Write-Host "`n=== PHASE 9: NOTIFICATIONS ===" -ForegroundColor Yellow

Test-API -Name "Notifications" -Method "GET" -Url "/api/v1/notifications" `
    -Token $TOKEN -Description "Org-scoped notifications"


# ============================================================
# PHASE 10: AUDIT LOGS
# ============================================================
Write-Host "`n=== PHASE 10: AUDIT LOGS ===" -ForegroundColor Yellow

Test-API -Name "Audit Logs" -Method "GET" -Url "/api/v1/audit-logs" `
    -Token $TOKEN -ExpectedContains "data" `
    -Description "Admin-only audit trail"


# ============================================================
# PHASE 11: SECURITY (unauthenticated access)
# ============================================================
Write-Host "`n=== PHASE 11: SECURITY ===" -ForegroundColor Yellow

Test-API -Name "Products No Auth" -Method "GET" -Url "/api/v1/products/" `
    -ExpectedStatus 401 -Description "Must require auth"

Test-API -Name "Orders No Auth" -Method "GET" -Url "/api/v1/orders" `
    -ExpectedStatus 401 -Description "Must require auth"

Test-API -Name "Billing No Auth" -Method "GET" -Url "/api/v1/billing/status" `
    -ExpectedStatus 401 -Description "Must require auth"

Test-API -Name "Notifications No Auth" -Method "GET" -Url "/api/v1/notifications" `
    -ExpectedStatus 401 -Description "Must require auth"

Test-API -Name "Audit No Auth" -Method "GET" -Url "/api/v1/audit-logs" `
    -ExpectedStatus 401 -Description "Must require auth"


# ============================================================
# PHASE 12: CLEANUP
# ============================================================
Write-Host "`n=== PHASE 12: CLEANUP ===" -ForegroundColor Yellow

if ($PRODUCT_ID) {
    Test-API -Name "Soft Delete Product" -Method "DELETE" -Url "/api/v1/products/$PRODUCT_ID" `
        -Token $TOKEN -ExpectedContains "deleted" `
        -Description "Soft-delete (admin RBAC)"

    $afterDel = Test-API -Name "Verify Soft Delete" -Method "GET" -Url "/api/v1/products/" `
        -Token $TOKEN -Description "Deleted product excluded"

    if ($afterDel.Passed) {
        $remaining = $afterDel.Content | ConvertFrom-Json
        $found = $remaining | Where-Object { $_.id -eq $PRODUCT_ID }
        if (-not $found) {
            Write-Host "  VERIFIED: Soft-deleted product excluded" -ForegroundColor DarkGreen
        }
    }
}

if ($CONTACT_ID) {
    Test-API -Name "Delete Contact" -Method "DELETE" -Url "/api/v1/contacts/$CONTACT_ID" `
        -Token $TOKEN -ExpectedContains "deleted" -Description "Soft-delete contact"
}


# ============================================================
# PHASE 13: LOGOUT & SESSION KILL
# ============================================================
Write-Host "`n=== PHASE 13: LOGOUT ===" -ForegroundColor Yellow

Test-API -Name "Logout" -Method "POST" -Url "/api/v1/logout" `
    -Token $TOKEN -ExpectedContains "Logged out" `
    -Description "Kill session, invalidate tokens"

Test-API -Name "Token Dead After Logout" -Method "GET" -Url "/api/v1/me" `
    -Token $TOKEN -ExpectedStatus 401 `
    -Description "Token rejected after logout"


# ============================================================
# CLEANUP TEMP FILES
# ============================================================
Get-ChildItem "e:\NME-project\_tmp_*.json" -ErrorAction SilentlyContinue | Remove-Item -Force


# ============================================================
# FINAL REPORT
# ============================================================
Write-Host "`n============================================" -ForegroundColor Magenta
Write-Host " TEST RESULTS SUMMARY" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta
Write-Host " Total: $($PASS + $FAIL)" -ForegroundColor White
Write-Host " Passed: $PASS" -ForegroundColor Green
Write-Host " Failed: $FAIL" -ForegroundColor $(if ($FAIL -gt 0) { "Red" } else { "Green" })
Write-Host "============================================" -ForegroundColor Magenta

$RESULTS | Format-Table -Property Test, Result, HTTP, Detail -AutoSize

if ($FAIL -eq 0) {
    Write-Host "`n ALL TESTS PASSED - Secure SaaS Architecture Verified!" -ForegroundColor Green
} else {
    Write-Host "`n $FAIL test(s) FAILED - Review above!" -ForegroundColor Red
}
