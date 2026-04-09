variable "resource_group_name"      { type = string }
variable "location"                  { type = string }
variable "app_name"                  { type = string }
variable "environment"               { type = string }
variable "storage_account_tier"      { type = string }
variable "storage_replication_type"  { type = string }
variable "tags"                      { type = map(string) }
