output "resource_group_name" {
  description = "Name of the deployed resource group"
  value       = azurerm_resource_group.main.name
}

output "frontend_url" {
  description = "Public URL of the Streamlit frontend (Container App)"
  value       = module.container_apps.frontend_url
}

output "backend_internal_url" {
  description = "Internal (private) URL of the FastAPI backend — only reachable inside the VNet"
  value       = module.container_apps.backend_internal_url
}

output "acr_login_server" {
  description = "Azure Container Registry login server"
  value       = module.container_registry.login_server
}

output "foundry_account_endpoint" {
  description = "Foundry (AI Services) account endpoint"
  value       = module.ai_services.foundry_account_endpoint
}

output "foundry_project_endpoint" {
  description = "Foundry project endpoint (used by AIProjectClient)"
  value       = module.ai_services.foundry_project_endpoint
}

output "speech_endpoint" {
  description = "Azure Speech (CognitiveServices) endpoint for Fast Transcription"
  value       = module.ai_services.speech_endpoint
}

output "storage_account_name" {
  description = "Azure Storage account name"
  value       = module.storage.account_name
}

output "audio_container_name" {
  description = "Blob container for audio files"
  value       = module.storage.audio_container_name
}

output "vnet_id" {
  description = "Virtual Network resource ID"
  value       = module.networking.vnet_id
}

