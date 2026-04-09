locals {
  tags = {
    project     = "meeting-minutes-agent"
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ── Resource group ────────────────────────────────────────────────────────────
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}

# ── AI Services (Content Understanding + OpenAI) ──────────────────────────────
module "ai_services" {
  source = "./modules/ai_services"

  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  app_name                   = var.app_name
  environment                = var.environment
  openai_sku                 = var.openai_sku
  openai_model_name          = var.openai_model_name
  openai_model_version       = var.openai_model_version
  openai_deployment_capacity = var.openai_deployment_capacity
  content_understanding_sku  = var.content_understanding_sku
  tags                       = local.tags
}

# ── Storage ───────────────────────────────────────────────────────────────────
module "storage" {
  source = "./modules/storage"

  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  app_name                 = var.app_name
  environment              = var.environment
  storage_account_tier     = var.storage_account_tier
  storage_replication_type = var.storage_replication_type
  tags                     = local.tags
}

# ── Networking (VNet + Container Apps subnet) ─────────────────────────────────
module "networking" {
  source = "./modules/networking"

  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  app_name                   = var.app_name
  environment                = var.environment
  vnet_address_space         = var.vnet_address_space
  container_apps_subnet_cidr = var.container_apps_subnet_cidr
  tags                       = local.tags
}

# ── Container Registry ────────────────────────────────────────────────────────
module "container_registry" {
  source = "./modules/container_registry"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  app_name            = var.app_name
  environment         = var.environment
  acr_sku             = var.acr_sku
  tags                = local.tags
}

# ── Container Apps (Streamlit frontend + FastAPI backend) ──────────────────────
module "container_apps" {
  source = "./modules/container_apps"

  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_resource_group.main.location
  app_name                = var.app_name
  environment             = var.environment
  container_apps_subnet_id = module.networking.container_apps_subnet_id
  acr_login_server        = module.container_registry.login_server
  acr_username            = module.container_registry.admin_username
  acr_password            = module.container_registry.admin_password
  backend_image           = "${module.container_registry.login_server}/backend:latest"
  frontend_image          = "${module.container_registry.login_server}/frontend:latest"
  tags                    = local.tags

  # Non-secret backend env vars
  backend_env = {
    AZURE_CU_ANALYZER_ID        = "prebuilt-audioAnalyzer"
    AZURE_OPENAI_DEPLOYMENT     = var.openai_model_name
    AZURE_OPENAI_API_VERSION    = "2024-02-01"
    AZURE_STORAGE_CONTAINER     = module.storage.audio_container_name
    MAX_AUDIO_SIZE_MB           = "100"
    CU_POLL_TIMEOUT_SECONDS     = "300"
    CU_POLL_INTERVAL_SECONDS    = "5"
  }

  # Secrets (API keys, connection strings)
  backend_secrets = {
    AZURE_CU_ENDPOINT                = module.ai_services.content_understanding_endpoint
    AZURE_CU_KEY                     = module.ai_services.content_understanding_key
    AZURE_OPENAI_ENDPOINT            = module.ai_services.openai_endpoint
    AZURE_OPENAI_KEY                 = module.ai_services.openai_key
    AZURE_STORAGE_CONNECTION_STRING  = module.storage.connection_string
  }
}
