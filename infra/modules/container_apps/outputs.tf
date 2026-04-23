output "environment_default_domain" {
  description = "Default domain of the Container Apps Environment"
  value       = azurerm_container_app_environment.main.default_domain
}

output "backend_internal_url" {
  description = "Internal URL of the backend Container App (private network)"
  value       = "https://${azurerm_container_app.backend.name}.internal.${azurerm_container_app_environment.main.default_domain}"
}

output "frontend_url" {
  description = "Public URL of the Streamlit frontend"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "backend_app_name" {
  description = "Backend Container App name"
  value       = azurerm_container_app.backend.name
}

output "frontend_app_name" {
  description = "Frontend Container App name"
  value       = azurerm_container_app.frontend.name
}

output "log_analytics_workspace_id" {
  description = "Log Analytics Workspace resource ID"
  value       = azurerm_log_analytics_workspace.main.id
}

output "backend_principal_id" {
  description = "System-assigned Managed Identity principal ID of the backend Container App"
  value       = azurerm_container_app.backend.identity[0].principal_id
}
