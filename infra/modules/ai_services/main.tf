locals {
  suffix = "${var.app_name}-${var.environment}"
}

# ── Azure AI Foundry account (multi-service AI Services / Cognitive Services) ──
# kind = "AIServices" makes this a Foundry-compatible account that can host
# Foundry Projects, OpenAI model deployments, and other Azure AI capabilities.
resource "azurerm_cognitive_account" "foundry" {
  name                          = "aif-${local.suffix}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  kind                          = "AIServices"
  sku_name                      = var.openai_sku
  local_auth_enabled            = false
  custom_subdomain_name         = "aif-${local.suffix}"
  project_management_enabled    = true
  public_network_access_enabled = false

  network_acls {
    default_action = "Deny"
  }

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

# ── Private Endpoint for AI Services ──────────────────────────────────────────
resource "azurerm_private_dns_zone" "cognitive" {
  name                = "privatelink.cognitiveservices.azure.com"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "cognitive" {
  name                  = "vnet-link-cognitive"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.cognitive.name
  virtual_network_id    = var.vnet_id
}

resource "azurerm_private_dns_zone" "openai" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "openai" {
  name                  = "vnet-link-openai"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.openai.name
  virtual_network_id    = var.vnet_id
}

resource "azurerm_private_endpoint" "cognitive" {
  name                = "pe-cognitive-aif-${local.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-cognitive"
    private_connection_resource_id = azurerm_cognitive_account.foundry.id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name = "cognitive-dns"
    private_dns_zone_ids = [
      azurerm_private_dns_zone.cognitive.id,
      azurerm_private_dns_zone.openai.id,
    ]
  }
}

# ── Speech (Fast Transcription) ────────────────────────────────────────────────
# The AIServices (Foundry) account above also exposes the Speech endpoint, so a
# separate CognitiveServices account is no longer needed.  The standalone
# "aicu-*" resource has been consolidated into the Foundry account.
