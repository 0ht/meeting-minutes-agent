#!/usr/bin/env pwsh
# postdeploy hook — re-disable ACR public access after image push
# Restores the closed-network posture defined in Terraform.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$acrName = azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>$null
if (-not $acrName) {
    Write-Host "AZURE_CONTAINER_REGISTRY_NAME not set — skipping ACR public access toggle"
    exit 0
}

Write-Host "Disabling public network access on ACR '$acrName'..."
az acr update --name $acrName --public-network-enabled false --output none
Write-Host "ACR public access disabled — private endpoints only"
