locals {
  suffix = "${var.app_name}-${var.environment}"
}

# ── Azure AI Foundry account (multi-service AI Services / Cognitive Services) ──
# kind = "AIServices" makes this a Foundry-compatible account that can host
# Foundry Projects, OpenAI model deployments, and other Azure AI capabilities.
resource "azurerm_cognitive_account" "foundry" {
  name                       = "aif-${local.suffix}"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  kind                       = "AIServices"
  sku_name                   = var.openai_sku
  local_auth_enabled         = false
  custom_subdomain_name      = "aif-${local.suffix}"
  project_management_enabled = true

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# ── Foundry Project (sub-resource of the AI Services account) ────────────────
# Uses azapi because this resource type is not yet exposed by azurerm.
resource "azapi_resource" "foundry_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview"
  name      = "proj-${local.suffix}"
  parent_id = azurerm_cognitive_account.foundry.id
  location  = var.location

  identity {
    type = "SystemAssigned"
  }

  body = jsonencode({
    properties = {
      displayName = "Meeting Minutes Agent (${var.environment})"
      description = "Foundry project hosting the meeting minutes agent pipeline (script / minutes / terminology)."
    }
  })

  tags = {
    Environment = "Hybrid"
  }

  response_export_values = ["properties.endpoints", "identity"]

  schema_validation_enabled = false
}

# ── GPT model deployment on the Foundry account ───────────────────────────────
resource "azurerm_cognitive_deployment" "gpt" {
  name                 = var.openai_model_name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.openai_model_name
    version = var.openai_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.openai_deployment_capacity
  }
}

# ── Azure Speech (Fast Transcription) ──────────────────────────────────────────
# CognitiveServices multi-service account exposes Speech endpoints for transcription.
resource "azurerm_cognitive_account" "speech" {
  name                = "aicu-${local.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  kind                = "CognitiveServices"
  sku_name            = var.speech_sku  # local_auth (account keys) is enabled to match the deployed environment.
  # Backend prefers Managed Identity but key-based auth is left available
  # as a fallback for diagnostics / local testing.  local_auth_enabled  = true
  tags                = var.tags

  custom_subdomain_name = "aicu-${local.suffix}"
}

# Renamed from "content_understanding" to "speech" — tell Terraform this is the
# same resource so it won't destroy and recreate it.
moved {
  from = azurerm_cognitive_account.content_understanding
  to   = azurerm_cognitive_account.speech
}
