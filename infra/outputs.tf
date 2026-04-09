output "resource_group_name" {
  description = "Name of the deployed resource group"
  value       = azurerm_resource_group.main.name
}

output "backend_url" {
  description = "URL of the backend App Service"
  value       = module.app_service.url
}

output "openai_endpoint" {
  description = "Azure OpenAI endpoint"
  value       = module.ai_services.openai_endpoint
}

output "content_understanding_endpoint" {
  description = "Azure AI Content Understanding endpoint"
  value       = module.ai_services.content_understanding_endpoint
}

output "storage_account_name" {
  description = "Azure Storage account name"
  value       = module.storage.account_name
}

output "audio_container_name" {
  description = "Blob container for audio files"
  value       = module.storage.audio_container_name
}
