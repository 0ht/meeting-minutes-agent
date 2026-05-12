#!/usr/bin/env pwsh
# postdeploy hook — runs after azd deploy completes.
#
# 1. Re-disable ACR public access (restore closed-network posture)
# 2. Register/update Foundry Prompt Agents (idempotent)
# 3. Upload terminology dictionary to Blob Storage (idempotent)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── 1. ACR public access teardown ────────────────────────────────────────────
$acrName = azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>$null
if ($acrName) {
    Write-Host "Disabling public network access on ACR '$acrName'..."
    az acr update --name $acrName --public-network-enabled false --default-action Deny --output none
    Write-Host "ACR public access disabled — private endpoints only"
} else {
    Write-Host "AZURE_CONTAINER_REGISTRY_NAME not set — skipping ACR toggle"
}

# ── 2. Foundry Prompt Agent registration ─────────────────────────────────────
$foundryEndpoint = azd env get-value FOUNDRY_PROJECT_ENDPOINT 2>$null
if (-not $foundryEndpoint) {
    $foundryEndpoint = azd env get-value foundry_project_endpoint 2>$null
}
if ($foundryEndpoint) {
    Write-Host "Registering Foundry Prompt Agents..."
    $env:FOUNDRY_PROJECT_ENDPOINT = $foundryEndpoint
    python backend/scripts/register_foundry_agents.py
    Write-Host "Foundry agents registered."
} else {
    Write-Host "FOUNDRY_PROJECT_ENDPOINT not set — skipping Foundry agent registration"
}

# ── 3. Terminology dictionary upload ─────────────────────────────────────────
$storageAccountName = azd env get-value AZURE_STORAGE_ACCOUNT_NAME 2>$null
if (-not $storageAccountName) {
    $storageAccountName = azd env get-value storage_account_name 2>$null
}
$termsFile = "backend/app/data/terminology.json"
if ($storageAccountName -and (Test-Path $termsFile)) {
    Write-Host "Uploading terminology dictionary to Blob Storage..."
    az storage blob upload `
        --account-name $storageAccountName `
        --container-name terms `
        --name terminology.json `
        --file $termsFile `
        --auth-mode login `
        --overwrite `
        --output none 2>&1
    Write-Host "Terminology dictionary uploaded."
} else {
    Write-Host "Storage account not set or terminology file missing — skipping upload"
}
