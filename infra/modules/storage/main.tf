locals {
  # Storage account names: 3-24 lowercase alphanumeric chars, no hyphens
  sa_name = lower(replace("st${var.app_name}${var.environment}", "-", ""))
}

resource "azurerm_storage_account" "main" {
  name                     = substr(local.sa_name, 0, 24)
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = var.storage_account_tier
  account_replication_type = var.storage_replication_type
  shared_access_key_enabled = false
  tags                     = var.tags

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  # Restrict public blob access
  allow_nested_items_to_be_public = false
}

resource "azurerm_storage_container" "audio" {
  name                  = "audio-files"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# Container holding the terminology dictionary (terminology.json) consumed by
# the Foundry agents via the lookup_terminology tool.
resource "azurerm_storage_container" "terms" {
  name                  = "terms"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# Container persisting meeting-minutes generation history
# (input file + job.json with results) for later retrieval/download.
resource "azurerm_storage_container" "history" {
  name                  = "history"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}
