locals {
  suffix = "${var.app_name}-${var.environment}"
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
# Deployed inside the VNet for private networking.
# internal_load_balancer_enabled = false  → the environment has a public IP so
# that the frontend Container App can expose an external ingress endpoint.
# The backend Container App sets external_enabled = false to remain private.
resource "azurerm_container_app_environment" "main" {
  name                           = "cae-${local.suffix}"
  location                       = var.location
  resource_group_name            = var.resource_group_name
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id       = var.container_apps_subnet_id
  # false = external environment (required to allow the frontend to be public)
  internal_load_balancer_enabled = false
  tags                           = var.tags
}

# ── Backend Container App — internal ingress only ─────────────────────────────
resource "azurerm_container_app" "backend" {
  name                         = "ca-backend-${local.suffix}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  tags                         = var.tags

  registry {
    server               = var.acr_login_server
    username             = var.acr_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = var.acr_password
  }

  # Additional secrets (API keys, connection strings, …)
  dynamic "secret" {
    for_each = var.backend_secrets
    content {
      name  = replace(secret.key, "_", "-")
      value = secret.value
    }
  }

  ingress {
    # Internal only — not reachable from the public internet
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
      image  = var.backend_image
      cpu    = var.backend_cpu
      memory = var.backend_memory

      # Non-secret env vars
      dynamic "env" {
        for_each = var.backend_env
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secret env vars — reference by secret name
      dynamic "env" {
        for_each = var.backend_secrets
        content {
          name        = env.key
          secret_name = replace(env.key, "_", "-")
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
}

# ── Frontend Container App — external ingress ─────────────────────────────────
resource "azurerm_container_app" "frontend" {
  name                         = "ca-frontend-${local.suffix}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  tags                         = var.tags

  registry {
    server               = var.acr_login_server
    username             = var.acr_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = var.acr_password
  }

  ingress {
    # Public — accessible from the internet
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
      image  = var.frontend_image
      cpu    = var.frontend_cpu
      memory = var.frontend_memory

      # The frontend reaches the backend via the internal Container Apps URL.
      # Format: https://{app-name}.internal.{environment-default-domain}
      env {
        name  = "BACKEND_URL"
        value = "https://${azurerm_container_app.backend.name}.internal.${azurerm_container_app_environment.main.default_domain}"
      }
      env {
        name  = "POLL_INTERVAL_SECONDS"
        value = "2"
      }
    }
  }

  # Ensure the backend is created first so the BACKEND_URL is valid
  depends_on = [azurerm_container_app.backend]
}
