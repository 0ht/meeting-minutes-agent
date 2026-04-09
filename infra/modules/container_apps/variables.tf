variable "resource_group_name"     { type = string }
variable "location"                 { type = string }
variable "app_name"                 { type = string }
variable "environment"              { type = string }
variable "container_apps_subnet_id" { type = string }
variable "acr_login_server"         { type = string }
variable "acr_username"             { type = string; sensitive = true }
variable "acr_password"             { type = string; sensitive = true }

# Backend image (e.g. myregistry.azurecr.io/backend:latest)
variable "backend_image"  { type = string }
# Frontend image (e.g. myregistry.azurecr.io/frontend:latest)
variable "frontend_image" { type = string }

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

variable "backend_cpu"      { type = number; default = 0.5 }
variable "backend_memory"   { type = string; default = "1Gi" }
variable "frontend_cpu"     { type = number; default = 0.5 }
variable "frontend_memory"  { type = string; default = "1Gi" }

variable "tags" { type = map(string) }
