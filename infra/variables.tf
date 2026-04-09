variable "resource_group_name" {
  description = "Name of the Azure resource group"
  type        = string
  default     = "rg-meeting-minutes-agent"
}

variable "location" {
  description = "Azure region to deploy resources"
  type        = string
  default     = "japaneast"
}

variable "environment" {
  description = "Deployment environment (dev / staging / prod)"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod"
  }
}

variable "app_name" {
  description = "Base name used to derive resource names"
  type        = string
  default     = "mtgminutes"
}

# ── Azure OpenAI ─────────────────────────────────────────────────────────────
variable "openai_sku" {
  description = "SKU for the Azure OpenAI resource"
  type        = string
  default     = "S0"
}

variable "openai_model_name" {
  description = "Azure OpenAI model to deploy (e.g. gpt-4o)"
  type        = string
  default     = "gpt-4o"
}

variable "openai_model_version" {
  description = "Version of the Azure OpenAI model"
  type        = string
  default     = "2024-05-13"
}

variable "openai_deployment_capacity" {
  description = "Tokens-per-minute capacity (in thousands) for the OpenAI deployment"
  type        = number
  default     = 30
}

# ── Azure AI Content Understanding ──────────────────────────────────────────
variable "content_understanding_sku" {
  description = "SKU for the Azure AI Content Understanding (Cognitive Services) resource"
  type        = string
  default     = "S0"
}

# ── Storage ───────────────────────────────────────────────────────────────────
variable "storage_account_tier" {
  description = "Storage account tier"
  type        = string
  default     = "Standard"
}

variable "storage_replication_type" {
  description = "Storage account replication type"
  type        = string
  default     = "LRS"
}

# ── App Service ───────────────────────────────────────────────────────────────
variable "app_service_sku" {
  description = "App Service plan SKU"
  type        = string
  default     = "B2"
}

variable "docker_image" {
  description = "Docker image for the backend (e.g. myregistry.azurecr.io/meeting-minutes-agent:latest)"
  type        = string
  default     = ""
}
