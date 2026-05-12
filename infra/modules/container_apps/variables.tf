variable "resource_group_name"     { type = string }
variable "location"                 { type = string }
variable "app_name"                 { type = string }
variable "environment"              { type = string }
variable "container_apps_subnet_id" { type = string }
variable "acr_login_server"         { type = string }
variable "acr_id" {
  description = "ACR resource ID for AcrPull role assignment"
  type        = string
}

# Backend environment variables (secrets are passed separately)
variable "backend_env" {
  description = "Non-secret env vars for the backend container"
  type        = map(string)
  default     = {}
}
variable "backend_secrets" {
  description = "Secret env vars for the backend container"
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "backend_cpu" {
  type    = number
  default = 0.5
}
variable "backend_memory" {
  type    = string
  default = "1Gi"
}
variable "frontend_cpu" {
  type    = number
  default = 0.5
}
variable "frontend_memory" {
  type    = string
  default = "1Gi"
}

variable "storage_account_url" {
  description = "Primary blob endpoint URL for frontend direct upload"
  type        = string
}

variable "audio_container_name" {
  description = "Blob container name for audio files"
  type        = string
}

variable "tags" { type = map(string) }
