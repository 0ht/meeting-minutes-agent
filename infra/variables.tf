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
  description = "Azure OpenAI model to deploy (e.g. gpt-5.4)"
  type        = string
  default     = "gpt-5.4"
}

variable "openai_model_version" {
  description = "Version of the Azure OpenAI model"
  type        = string
  default     = "2026-03-05"
}

variable "openai_deployment_capacity" {
  description = "Tokens-per-minute capacity (in thousands) for the OpenAI deployment"
  type        = number
  default     = 30
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

# ── Networking ────────────────────────────────────────────────────────────────
variable "vnet_address_space" {
  description = "CIDR block for the Virtual Network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "container_apps_subnet_cidr" {
  description = "CIDR block for the Container Apps subnet (minimum /23)"
  type        = string
  default     = "10.0.0.0/23"
}

# ── Container Registry ────────────────────────────────────────────────────────
variable "acr_sku" {
  description = "SKU for Azure Container Registry (Premium required for Private Endpoints)"
  type        = string
  default     = "Premium"
  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "acr_sku must be Basic, Standard, or Premium"
  }
}

# ── Container Apps ────────────────────────────────────────────────────────────
variable "backend_cpu" {
  description = "CPU allocation for the backend Container App (vCPU)"
  type        = number
  default     = 0.5
}

variable "backend_memory" {
  description = "Memory allocation for the backend Container App"
  type        = string
  default     = "1Gi"
}

variable "frontend_cpu" {
  description = "CPU allocation for the frontend (Streamlit) Container App (vCPU)"
  type        = number
  default     = 0.5
}

variable "frontend_memory" {
  description = "Memory allocation for the frontend Container App"
  type        = string
  default     = "1Gi"
}
