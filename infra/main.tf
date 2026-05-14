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
  tags                       = local.tags

  # Private Endpoint — allows Container Apps to reach AI Services inside the VNet
  vnet_id                    = module.networking.vnet_id
  private_endpoint_subnet_id = module.networking.private_endpoints_subnet_id
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

  # Private Endpoint — allows Container Apps to reach blob storage inside the VNet
  vnet_id                    = module.networking.vnet_id
  private_endpoint_subnet_id = module.networking.private_endpoints_subnet_id
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

  # Private Endpoint — allows Container Apps to pull images inside the VNet
  vnet_id                    = module.networking.vnet_id
  private_endpoint_subnet_id = module.networking.private_endpoints_subnet_id
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
  acr_id                  = module.container_registry.acr_id
  tags                    = local.tags

  # Storage info for frontend direct upload
  storage_account_url  = module.storage.primary_blob_endpoint
  audio_container_name = module.storage.audio_container_name

  # Non-secret backend env vars
  backend_env = {
    AZURE_OPENAI_DEPLOYMENT     = module.ai_services.gpt_deployment_name
    AZURE_OPENAI_API_VERSION    = "2025-04-01-preview"
    AZURE_STORAGE_CONTAINER     = module.storage.audio_container_name
    AZURE_STORAGE_ACCOUNT_URL   = module.storage.primary_blob_endpoint
    AZURE_TERMS_CONTAINER       = module.storage.terms_container_name
    AZURE_TERMS_BLOB            = "terminology.json"
    AZURE_HISTORY_CONTAINER     = module.storage.history_container_name
    AZURE_SPEECH_ENDPOINT        = module.ai_services.speech_endpoint
    FOUNDRY_PROJECT_ENDPOINT    = module.ai_services.foundry_project_endpoint
    FOUNDRY_MODEL_DEPLOYMENT    = module.ai_services.gpt_deployment_name
    MAX_AUDIO_SIZE_MB           = "500"
    SPEECH_POLL_TIMEOUT_SECONDS = "3600"
    SPEECH_POLL_INTERVAL_SECONDS = "5"
    # CORS — restrict to the frontend Container App's public FQDN.
    CORS_ALLOWED_ORIGINS        = "https://ca-frontend-${var.app_name}-${var.environment}.${module.container_apps.environment_default_domain}"
  }

  # No more API key secrets needed — authentication via Managed Identity
  backend_secrets = {}
}

# ── RBAC: Backend Managed Identity → Storage Blob Data Contributor ────────────
resource "azurerm_role_assignment" "backend_blob_contributor" {
  scope                = module.storage.account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.container_apps.backend_principal_id
  principal_type       = "ServicePrincipal"
}

# ── RBAC: Frontend Managed Identity → Storage Blob Data Contributor ───────────
# Frontend uploads audio files directly to Blob Storage.
resource "azurerm_role_assignment" "frontend_blob_contributor" {
  scope                = module.storage.account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.container_apps.frontend_principal_id
  principal_type       = "ServicePrincipal"
}

# ── RBAC: Backend Managed Identity → Foundry account ─────────────────────────
# "Azure AI Developer" grants data-plane access to the Foundry project + model
# deployments (chat completions, agents, etc.) via DefaultAzureCredential.
resource "azurerm_role_assignment" "backend_foundry_ai_user" {
  scope                = module.ai_services.foundry_account_id
  role_definition_name = "Azure AI Developer"
  principal_id         = module.container_apps.backend_principal_id
  principal_type       = "ServicePrincipal"
}

# Cognitive Services User — required for Speech Fast Transcription on the
# Foundry (AIServices) account.  Replaces the old per-speech-resource assignment.
resource "azurerm_role_assignment" "backend_speech_user" {
  scope                = module.ai_services.foundry_account_id
  role_definition_name = "Cognitive Services User"
  principal_id         = module.container_apps.backend_principal_id
  principal_type       = "ServicePrincipal"
}

# Cognitive Services OpenAI User — required for OpenAI model inference calls
# made through the project's get_openai_client() (chat.completions endpoint).
resource "azurerm_role_assignment" "backend_openai_user" {
  scope                = module.ai_services.foundry_account_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = module.container_apps.backend_principal_id
  principal_type       = "ServicePrincipal"
}

# ── RBAC: AI Services Managed Identity → Storage Blob Data Reader ────────────
# Batch Transcription reads audio files from Blob Storage using the Foundry
# (AI Services) account's system-assigned Managed Identity.  The storage
# account allows trusted Azure services via network_rules bypass.
resource "azurerm_role_assignment" "foundry_blob_reader" {
  scope                = module.storage.account_id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = module.ai_services.foundry_principal_id
  principal_type       = "ServicePrincipal"
}
