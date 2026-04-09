output "vnet_id" {
  description = "Virtual network resource ID"
  value       = azurerm_virtual_network.main.id
}

output "container_apps_subnet_id" {
  description = "Subnet ID for the Container Apps Environment"
  value       = azurerm_subnet.container_apps.id
}
