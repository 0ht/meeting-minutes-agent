output "login_server" {
  description = "ACR login server (e.g. myregistry.azurecr.io)"
  value       = azurerm_container_registry.main.login_server
}

output "acr_id" {
  description = "ACR resource ID (for RBAC role assignments)"
  value       = azurerm_container_registry.main.id
}

output "acr_name" {
  description = "ACR resource name"
  value       = azurerm_container_registry.main.name
}
