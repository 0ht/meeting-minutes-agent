locals {
  # ACR names: 5-50 alphanumeric, no hyphens
  acr_name = lower(replace("acr${var.app_name}${var.environment}", "-", ""))
}

resource "azurerm_container_registry" "main" {
  name                = substr(local.acr_name, 0, 50)
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.acr_sku
  # Admin credentials are required for Container Apps to pull images
  admin_enabled       = true
  tags                = var.tags
}
