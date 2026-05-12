#!/usr/bin/env pwsh
# predeploy hook — temporarily enable ACR public access for image push
# ACR is configured with public_network_access_enabled = false (private endpoints only).
# azd remoteBuild (az acr build) requires data-plane access to upload build context.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$acrName = azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>$null
if (-not $acrName) {
    Write-Host "AZURE_CONTAINER_REGISTRY_NAME not set — skipping ACR public access toggle"
    exit 0
}

Write-Host "Enabling public network access on ACR '$acrName' for image push..."
az acr update --name $acrName --public-network-enabled true --output none
Write-Host "ACR public access enabled (will be disabled in postdeploy)"
