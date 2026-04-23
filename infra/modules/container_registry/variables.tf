variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "app_name"            { type = string }
variable "environment"         { type = string }
variable "acr_sku" {
  type    = string
  default = "Basic"
}
variable "tags"                { type = map(string) }
