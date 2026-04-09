locals {
  suffix = "${var.app_name}-${var.environment}"
}

# ── Azure OpenAI ─────────────────────────────────────────────────────────────
resource "azurerm_cognitive_account" "openai" {
  name                = "oai-${local.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  kind                = "OpenAI"
  sku_name            = var.openai_sku
  tags                = var.tags

  # Required for Azure OpenAI
  custom_subdomain_name = "oai-${local.suffix}"
}

resource "azurerm_cognitive_deployment" "gpt" {
  name                 = var.openai_model_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.openai_model_name
    version = var.openai_model_version
  }

  scale {
    type     = "Standard"
    capacity = var.openai_deployment_capacity
  }
}

# ── Azure AI Content Understanding ────────────────────────────────────────────
# Content Understanding is part of Azure AI Services (multi-service account).
resource "azurerm_cognitive_account" "content_understanding" {
  name                = "aicu-${local.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  # "AIServices" exposes Content Understanding endpoints.
  kind                = "AIServices"
  sku_name            = var.content_understanding_sku
  tags                = var.tags

  custom_subdomain_name = "aicu-${local.suffix}"
}
