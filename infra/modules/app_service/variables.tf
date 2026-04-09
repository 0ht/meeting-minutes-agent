variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "app_name"            { type = string }
variable "environment"         { type = string }
variable "app_service_sku"     { type = string }
variable "docker_image"        { type = string }
variable "tags"                { type = map(string) }
variable "app_settings"        { type = map(string) }
