locals {
  suffix = "${var.app_name}-${var.environment}"

  # Public placeholder image — used on initial creation. After the
  # postprovision hook configures MI-based registry and azd deploy pushes
  # the real image, Terraform never touches the image again (ignore_changes).
  placeholder_image = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
}

# ── Log Analytics Workspace (required for Container Apps Environment) ─────────
resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${local.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

# ── Container Apps Environment ────────────────────────────────────────────────
resource "azurerm_container_app_environment" "main" {
  name                           = "cae-${local.suffix}"
  location                       = var.location
  resource_group_name            = var.resource_group_name
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id       = var.container_apps_subnet_id
  internal_load_balancer_enabled = false
  tags                           = var.tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }

  lifecycle {
    ignore_changes = [infrastructure_resource_group_name]
  }
}

# ── Backend Container App — internal ingress only ─────────────────────────────
# Registry and image are managed outside Terraform:
#   - postprovision hook: `az containerapp registry set --identity system`
#   - azd deploy: pushes ACR image and updates the container
resource "azurerm_container_app" "backend" {
  name                         = "ca-backend-${local.suffix}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = merge(var.tags, { "azd-service-name" = "backend" })

  identity {
    type = "SystemAssigned"
  }

  # No registry block — configured by postprovision hook via CLI.

  dynamic "secret" {
    for_each = nonsensitive(var.backend_secrets)
    content {
      name  = lower(replace(secret.key, "_", "-"))
      value = secret.value
    }
  }

  ingress {
    external_enabled = false
    target_port      = 8000
    transport        = "http"
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "backend"
      image  = local.placeholder_image
      cpu    = var.backend_cpu
      memory = var.backend_memory

      dynamic "env" {
        for_each = var.backend_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = nonsensitive(var.backend_secrets)
        content {
          name        = env.key
          secret_name = lower(replace(env.key, "_", "-"))
        }
      }

      liveness_probe {
        path      = "/health"
        port      = 8000
        transport = "HTTP"
        initial_delay           = 10
        interval_seconds        = 30
        failure_count_threshold = 3
      }
    }
  }

  lifecycle {
    # Registry is managed by postprovision hook; image is managed by azd deploy.
    ignore_changes = [registry, template[0].container[0].image]
  }
}

# ── Frontend Container App — external ingress ─────────────────────────────────
resource "azurerm_container_app" "frontend" {
  name                         = "ca-frontend-${local.suffix}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = merge(var.tags, { "azd-service-name" = "frontend" })

  identity {
    type = "SystemAssigned"
  }

  # No registry block — configured by postprovision hook via CLI.

  ingress {
    external_enabled = true
    target_port      = 8501
    transport        = "http"
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "frontend"
      image  = local.placeholder_image
      cpu    = var.frontend_cpu
      memory = var.frontend_memory

      env {
        name  = "BACKEND_URL"
        value = "https://${azurerm_container_app.backend.name}.internal.${azurerm_container_app_environment.main.default_domain}"
      }
      env {
        name  = "POLL_INTERVAL_SECONDS"
        value = "2"
      }
      env {
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = var.storage_account_url
      }
      env {
        name  = "AZURE_STORAGE_CONTAINER"
        value = var.audio_container_name
      }
    }
  }

  depends_on = [azurerm_container_app.backend]

  lifecycle {
    ignore_changes = [registry, template[0].container[0].image]
  }
}

# ── AcrPull role assignments ──────────────────────────────────────────────────
# Created during provision. The postprovision hook runs AFTER these exist,
# so `az containerapp registry set --identity system` always succeeds.
resource "azurerm_role_assignment" "backend_acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.backend.identity[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "frontend_acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.frontend.identity[0].principal_id
  principal_type       = "ServicePrincipal"
}
