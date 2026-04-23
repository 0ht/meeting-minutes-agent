output "account_name" {
  description = "Storage account name"
  value       = azurerm_storage_account.main.name
}

output "account_id" {
  description = "Storage account resource ID"
  value       = azurerm_storage_account.main.id
}

output "primary_blob_endpoint" {
  description = "Primary blob endpoint URL"
  value       = azurerm_storage_account.main.primary_blob_endpoint
}

output "audio_container_name" {
  description = "Name of the audio-files blob container"
  value       = azurerm_storage_container.audio.name
}

output "terms_container_name" {
  description = "Name of the terminology blob container"
  value       = azurerm_storage_container.terms.name
}

output "history_container_name" {
  description = "Name of the history blob container"
  value       = azurerm_storage_container.history.name
}
