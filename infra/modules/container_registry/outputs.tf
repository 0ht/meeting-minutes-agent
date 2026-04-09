output "login_server" {
  description = "ACR login server (e.g. myregistry.azurecr.io)"
  value       = azurerm_container_registry.main.login_server
}

output "admin_username" {
  description = "ACR admin username"
  value       = azurerm_container_registry.main.admin_username
  sensitive   = true
}

output "admin_password" {
  description = "ACR admin password"
  value       = azurerm_container_registry.main.admin_password
  sensitive   = true
}

output "acr_name" {
  description = "ACR resource name"
  value       = azurerm_container_registry.main.name
}
