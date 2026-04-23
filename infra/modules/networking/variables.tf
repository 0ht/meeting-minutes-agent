variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "app_name"            { type = string }
variable "environment"         { type = string }
variable "vnet_address_space" {
  type    = string
  default = "10.0.0.0/16"
}
# Container Apps requires a /23 subnet (512 addresses) minimum
variable "container_apps_subnet_cidr" {
  type    = string
  default = "10.0.0.0/23"
}
variable "tags"                { type = map(string) }
