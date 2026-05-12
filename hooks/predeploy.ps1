#!/usr/bin/env pwsh
# predeploy hook — temporarily enable ACR public access for image push
# ACR is configured with public_network_access_enabled = false (private endpoints only).
# azd remoteBuild (az acr build) requires data-plane access to upload build context.
# After the build completes, postdeploy restores the closed-network posture.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$acrName = azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>$null
if (-not $acrName) {
    Write-Host "AZURE_CONTAINER_REGISTRY_NAME not set — skipping ACR public access toggle"
    exit 0
}

Write-Host "Enabling public network access on ACR '$acrName' for image push..."
az acr update --name $acrName --public-network-enabled true --default-action Allow --output none

# Wait for the change to propagate — ACR Tasks run on a remote agent that
# may still see the old firewall rules for up to ~30 s.
$maxRetries = 6
$delay = 10
for ($i = 1; $i -le $maxRetries; $i++) {
    try {
        $result = az acr login --name $acrName --expose-token --output json 2>&1 | ConvertFrom-Json
        if ($result.accessToken) {
            Write-Host "ACR public access confirmed (attempt $i/$maxRetries)."
            break
        }
    } catch {
        # ignore — retry
    }
    if ($i -eq $maxRetries) {
        Write-Host "WARNING: ACR access check did not succeed after $maxRetries attempts — proceeding anyway."
    } else {
        Write-Host "  Waiting for ACR access propagation ($i/$maxRetries)..."
        Start-Sleep -Seconds $delay
    }
}

Write-Host "ACR public access enabled (will be disabled in postdeploy)"
