#!/usr/bin/env pwsh
# postprovision hook — configure MI-based ACR registry on Container Apps.
#
# This runs AFTER Terraform has created the Container Apps (with placeholder
# images) and the AcrPull role assignments. It configures the MI-based
# registry via CLI, which is idempotent — safe to run on every provision.
#
# Flow:
#   terraform apply → Container Apps with placeholder + AcrPull roles
#   postprovision   → az containerapp registry set --identity system (this hook)
#   azd deploy      → push ACR images + update container apps

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$rgName      = azd env get-value AZURE_RESOURCE_GROUP 2>$null
$acrEndpoint = azd env get-value AZURE_CONTAINER_REGISTRY_ENDPOINT 2>$null
$backendName = azd env get-value SERVICE_BACKEND_RESOURCE_NAME 2>$null
$frontendName = azd env get-value SERVICE_FRONTEND_RESOURCE_NAME 2>$null

if (-not $rgName -or -not $acrEndpoint) {
    Write-Host "Resource group or ACR not set — skipping registry configuration"
    exit 0
}

foreach ($appName in @($backendName, $frontendName)) {
    if (-not $appName) { continue }
    Write-Host "Configuring MI-based registry on '$appName'..."
    az containerapp registry set `
        --name $appName `
        --resource-group $rgName `
        --server $acrEndpoint `
        --identity system `
        --output none 2>&1
    Write-Host "  Done: $appName"
}

Write-Host "MI-based ACR registry configured on all Container Apps."
