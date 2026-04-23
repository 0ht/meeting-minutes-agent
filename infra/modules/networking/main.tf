locals {
  suffix = "${var.app_name}-${var.environment}"
}

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${local.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.vnet_address_space]
  tags                = var.tags
}

# Subnet for Container Apps — must be at least /23 and delegated
resource "azurerm_subnet" "container_apps" {
  name                            = "snet-container-apps"
  resource_group_name             = var.resource_group_name
  virtual_network_name            = azurerm_virtual_network.main.name
  address_prefixes                = [var.container_apps_subnet_cidr]
  default_outbound_access_enabled = true

  delegation {
    name = "Microsoft.App.environments"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}
