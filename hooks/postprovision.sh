#!/bin/sh
# postprovision hook — configure MI-based ACR registry on Container Apps.
set -eu

rg_name=$(azd env get-value AZURE_RESOURCE_GROUP 2>/dev/null || true)
acr_endpoint=$(azd env get-value AZURE_CONTAINER_REGISTRY_ENDPOINT 2>/dev/null || true)
backend_name=$(azd env get-value SERVICE_BACKEND_RESOURCE_NAME 2>/dev/null || true)
frontend_name=$(azd env get-value SERVICE_FRONTEND_RESOURCE_NAME 2>/dev/null || true)

if [ -z "$rg_name" ] || [ -z "$acr_endpoint" ]; then
    echo "Resource group or ACR not set — skipping registry configuration"
    exit 0
fi

for app_name in $backend_name $frontend_name; do
    [ -z "$app_name" ] && continue
    echo "Configuring MI-based registry on '$app_name'..."
    az containerapp registry set \
        --name "$app_name" \
        --resource-group "$rg_name" \
        --server "$acr_endpoint" \
        --identity system \
        --output none 2>&1
    echo "  Done: $app_name"
done

echo "MI-based ACR registry configured on all Container Apps."
