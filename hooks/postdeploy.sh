#!/bin/sh
# postdeploy hook — re-disable ACR public access after image push
# Restores the closed-network posture defined in Terraform.

set -eu

acr_name=$(azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>/dev/null || true)
if [ -z "$acr_name" ]; then
    echo "AZURE_CONTAINER_REGISTRY_NAME not set — skipping ACR public access toggle"
    exit 0
fi

echo "Disabling public network access on ACR '$acr_name'..."
az acr update --name "$acr_name" --public-network-enabled false --output none
echo "ACR public access disabled — private endpoints only"
