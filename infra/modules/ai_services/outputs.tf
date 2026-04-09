output "openai_endpoint" {
  description = "Azure OpenAI endpoint"
  value       = azurerm_cognitive_account.openai.endpoint
}

output "openai_key" {
  description = "Azure OpenAI primary access key"
  value       = azurerm_cognitive_account.openai.primary_access_key
  sensitive   = true
}

output "content_understanding_endpoint" {
  description = "Azure AI Content Understanding endpoint"
  value       = azurerm_cognitive_account.content_understanding.endpoint
}

output "content_understanding_key" {
  description = "Azure AI Content Understanding primary access key"
  value       = azurerm_cognitive_account.content_understanding.primary_access_key
  sensitive   = true
}
