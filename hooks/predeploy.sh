#!/bin/sh
# predeploy hook — temporarily enable ACR public access for image push
# ACR is configured with public_network_access_enabled = false (private endpoints only).
# azd remoteBuild (az acr build) requires data-plane access to upload build context.

set -eu

acr_name=$(azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>/dev/null || true)
if [ -z "$acr_name" ]; then
    echo "AZURE_CONTAINER_REGISTRY_NAME not set — skipping ACR public access toggle"
    exit 0
fi

echo "Enabling public network access on ACR '$acr_name' for image push..."
az acr update --name "$acr_name" --public-network-enabled true --output none
echo "ACR public access enabled (will be disabled in postdeploy)"
