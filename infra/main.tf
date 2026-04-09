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

# ── App Service (backend) ─────────────────────────────────────────────────────
module "app_service" {
  source = "./modules/app_service"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  app_name            = var.app_name
  environment         = var.environment
  app_service_sku     = var.app_service_sku
  docker_image        = var.docker_image
  tags                = local.tags

  # Pass secrets as app settings (from Key Vault references in production)
  app_settings = {
    AZURE_CU_ENDPOINT                = module.ai_services.content_understanding_endpoint
    AZURE_CU_KEY                     = module.ai_services.content_understanding_key
    AZURE_CU_ANALYZER_ID             = "prebuilt-audioAnalyzer"
    AZURE_OPENAI_ENDPOINT            = module.ai_services.openai_endpoint
    AZURE_OPENAI_KEY                 = module.ai_services.openai_key
    AZURE_OPENAI_DEPLOYMENT          = var.openai_model_name
    AZURE_OPENAI_API_VERSION         = "2024-02-01"
    AZURE_STORAGE_CONNECTION_STRING  = module.storage.connection_string
    AZURE_STORAGE_CONTAINER          = module.storage.audio_container_name
    MAX_AUDIO_SIZE_MB                = "100"
    WEBSITES_PORT                    = "8000"
  }
}
