#!/bin/sh
# predeploy hook — temporarily enable ACR public access for image push
# ACR is configured with public_network_access_enabled = false (private endpoints only).
# azd remoteBuild (az acr build) requires data-plane access to upload build context.
# After the build completes, postdeploy restores the closed-network posture.

set -eu

acr_name=$(azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>/dev/null || true)
if [ -z "$acr_name" ]; then
    echo "AZURE_CONTAINER_REGISTRY_NAME not set — skipping ACR public access toggle"
    exit 0
fi

echo "Enabling public network access on ACR '$acr_name' for image push..."
az acr update --name "$acr_name" --public-network-enabled true --default-action Allow --output none

# Wait for the change to propagate — ACR Tasks run on a remote agent that
# may still see the old firewall rules for up to ~30 s.
max_retries=6
delay=10
for i in $(seq 1 $max_retries); do
    if az acr login --name "$acr_name" --expose-token --output none 2>/dev/null; then
        echo "ACR public access confirmed (attempt $i/$max_retries)."
        break
    fi
    if [ "$i" -eq "$max_retries" ]; then
        echo "WARNING: ACR access check did not succeed after $max_retries attempts — proceeding anyway."
    else
        echo "  Waiting for ACR access propagation ($i/$max_retries)..."
        sleep $delay
    fi
done

echo "ACR public access enabled (will be disabled in postdeploy)"
