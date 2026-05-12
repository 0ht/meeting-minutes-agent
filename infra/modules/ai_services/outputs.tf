output "foundry_account_endpoint" {
  description = "Foundry (AI Services) account endpoint — OpenAI-compatible base URL"
  value       = azurerm_cognitive_account.foundry.endpoint
}

output "foundry_account_id" {
  description = "Foundry (AI Services) account resource ID"
  value       = azurerm_cognitive_account.foundry.id
}

output "foundry_account_name" {
  description = "Foundry (AI Services) account name"
  value       = azurerm_cognitive_account.foundry.name
}

output "foundry_project_id" {
  description = "Foundry project resource ID"
  value       = azapi_resource.foundry_project.id
}

output "foundry_project_name" {
  description = "Foundry project name"
  value       = azapi_resource.foundry_project.name
}

# Foundry project endpoint — used by azure-ai-projects SDK (AIProjectClient).
# Format: https://<account>.services.ai.azure.com/api/projects/<project>
output "foundry_project_endpoint" {
  description = "Foundry project endpoint for AIProjectClient"
  value       = "https://${azurerm_cognitive_account.foundry.custom_subdomain_name}.services.ai.azure.com/api/projects/${azapi_resource.foundry_project.name}"
}

output "gpt_deployment_name" {
  description = "GPT model deployment name on the Foundry account"
  value       = azurerm_cognitive_deployment.gpt.name
}

output "speech_endpoint" {
  description = "Speech endpoint — served by the Foundry (AIServices) account"
  value       = azurerm_cognitive_account.foundry.endpoint
}

output "speech_id" {
  description = "Resource ID used for Speech RBAC — same as the Foundry account"
  value       = azurerm_cognitive_account.foundry.id
}

output "foundry_principal_id" {
  description = "System-assigned Managed Identity principal ID of the Foundry account"
  value       = azurerm_cognitive_account.foundry.identity[0].principal_id
}
