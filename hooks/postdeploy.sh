#!/bin/sh
# postdeploy hook — runs after azd deploy completes.
#
# 1. Re-disable ACR public access (restore closed-network posture)
# 2. Register/update Foundry Prompt Agents (idempotent)
# 3. Upload terminology dictionary to Blob Storage (idempotent)

set -eu

# ── 1. ACR public access teardown ────────────────────────────────────────────
acr_name=$(azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>/dev/null || true)
if [ -n "$acr_name" ]; then
    echo "Disabling public network access on ACR '$acr_name'..."
    az acr update --name "$acr_name" --public-network-enabled false --default-action Deny --output none
    echo "ACR public access disabled — private endpoints only"
else
    echo "AZURE_CONTAINER_REGISTRY_NAME not set — skipping ACR toggle"
fi

# ── 2. Foundry Prompt Agent registration ─────────────────────────────────────
foundry_endpoint=$(azd env get-value FOUNDRY_PROJECT_ENDPOINT 2>/dev/null || true)
if [ -z "$foundry_endpoint" ]; then
    foundry_endpoint=$(azd env get-value foundry_project_endpoint 2>/dev/null || true)
fi
if [ -n "$foundry_endpoint" ]; then
    echo "Registering Foundry Prompt Agents..."
    export FOUNDRY_PROJECT_ENDPOINT="$foundry_endpoint"
    python backend/scripts/register_foundry_agents.py
    echo "Foundry agents registered."
else
    echo "FOUNDRY_PROJECT_ENDPOINT not set — skipping Foundry agent registration"
fi

# ── 3. Terminology dictionary upload ─────────────────────────────────────────
storage_account_name=$(azd env get-value AZURE_STORAGE_ACCOUNT_NAME 2>/dev/null || true)
if [ -z "$storage_account_name" ]; then
    storage_account_name=$(azd env get-value storage_account_name 2>/dev/null || true)
fi
terms_file="backend/app/data/terminology.json"
if [ -n "$storage_account_name" ] && [ -f "$terms_file" ]; then
    echo "Uploading terminology dictionary to Blob Storage..."
    az storage blob upload \
        --account-name "$storage_account_name" \
        --container-name terms \
        --name terminology.json \
        --file "$terms_file" \
        --auth-mode login \
        --overwrite \
        --output none 2>&1
    echo "Terminology dictionary uploaded."
else
    echo "Storage account not set or terminology file missing — skipping upload"
fi
