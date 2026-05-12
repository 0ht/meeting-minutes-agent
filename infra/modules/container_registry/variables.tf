variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "app_name"            { type = string }
variable "environment"         { type = string }
variable "acr_sku" {
  type    = string
  default = "Premium"
}
variable "tags"                { type = map(string) }

variable "vnet_id" {
  description = "VNet ID for Private DNS Zone link"
  type        = string
}

variable "private_endpoint_subnet_id" {
  description = "Subnet ID for the ACR Private Endpoint"
  type        = string
}
