output "url" {
  description = "Default hostname URL of the App Service"
  value       = "https://${azurerm_linux_web_app.main.default_hostname}"
}

output "app_service_name" {
  description = "Name of the App Service"
  value       = azurerm_linux_web_app.main.name
}

output "principal_id" {
  description = "Managed identity principal ID (if assigned)"
  value       = azurerm_linux_web_app.main.identity[*].principal_id
}
