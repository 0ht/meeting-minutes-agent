output "account_name" {
  description = "Storage account name"
  value       = azurerm_storage_account.main.name
}

output "connection_string" {
  description = "Primary connection string for the storage account"
  value       = azurerm_storage_account.main.primary_connection_string
  sensitive   = true
}

output "audio_container_name" {
  description = "Name of the audio-files blob container"
  value       = azurerm_storage_container.audio.name
}
