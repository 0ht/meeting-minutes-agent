locals {
  # Storage account names: 3-24 lowercase alphanumeric chars, no hyphens
  sa_name = lower(replace("st${var.app_name}${var.environment}", "-", ""))
}

resource "azurerm_storage_account" "main" {
  name                          = substr(local.sa_name, 0, 24)
  resource_group_name           = var.resource_group_name
  location                      = var.location
  account_tier                  = var.storage_account_tier
  account_replication_type      = var.storage_replication_type
  shared_access_key_enabled     = false
  # Public access is denied by default via network_rules.default_action = "Deny".
  # bypass = ["AzureServices"] allows trusted Azure services (e.g. Cognitive
  # Services / Batch Transcription) to read blobs using their managed identity.
  public_network_access_enabled = true
  tags                          = var.tags

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
  }

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  # Restrict public blob access
  allow_nested_items_to_be_public = false
}

resource "azurerm_storage_container" "audio" {
  name               = "audio-files"
  storage_account_id = azurerm_storage_account.main.id
}

# Container holding the terminology dictionary (terminology.json) consumed by
# the Foundry agents via the lookup_terminology tool.
resource "azurerm_storage_container" "terms" {
  name               = "terms"
  storage_account_id = azurerm_storage_account.main.id
}

# Container persisting meeting-minutes generation history
# (input file + job.json with results) for later retrieval/download.
resource "azurerm_storage_container" "history" {
  name               = "history"
  storage_account_id = azurerm_storage_account.main.id
}

# ── Private Endpoint for Blob Storage ─────────────────────────────────────────
# Allows Container Apps (inside the VNet) to reach blob storage privately even
# when public network access is disabled on the storage account.

resource "azurerm_private_dns_zone" "blob" {
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "blob" {
  name                  = "vnet-link-blob"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.blob.name
  virtual_network_id    = var.vnet_id
}

resource "azurerm_private_endpoint" "blob" {
  name                = "pe-blob-${substr(local.sa_name, 0, 24)}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "psc-blob"
    private_connection_resource_id = azurerm_storage_account.main.id
    is_manual_connection           = false
    subresource_names              = ["blob"]
  }

  private_dns_zone_group {
    name                 = "blob-dns"
    private_dns_zone_ids = [azurerm_private_dns_zone.blob.id]
  }
}
