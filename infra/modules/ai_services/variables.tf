variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "app_name"            { type = string }
variable "environment"         { type = string }
variable "openai_sku"          { type = string }
variable "openai_model_name"   { type = string }
variable "openai_model_version"{ type = string }
variable "openai_deployment_capacity" { type = number }
variable "tags"                { type = map(string) }

variable "vnet_id" {
  description = "VNet ID for Private DNS Zone link"
  type        = string
}

variable "private_endpoint_subnet_id" {
  description = "Subnet ID for the AI Services Private Endpoint"
  type        = string
}
