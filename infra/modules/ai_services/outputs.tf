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
  description = "Azure Speech (CognitiveServices) endpoint for Fast Transcription"
  value       = azurerm_cognitive_account.speech.endpoint
}

output "speech_id" {
  description = "Azure Speech (CognitiveServices) resource ID"
  value       = azurerm_cognitive_account.speech.id
}

output "speech_key" {
  description = "Azure Speech (CognitiveServices) primary access key"
  value       = azurerm_cognitive_account.speech.primary_access_key
  sensitive   = true
}
