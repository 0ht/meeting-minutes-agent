locals {
  suffix = "${var.app_name}-${var.environment}"
}

resource "azurerm_service_plan" "main" {
  name                = "asp-${local.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  os_type             = "Linux"
  sku_name            = var.app_service_sku
  tags                = var.tags
}

resource "azurerm_linux_web_app" "main" {
  name                = "app-${local.suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  service_plan_id     = azurerm_service_plan.main.id
  tags                = var.tags

  https_only = true

  site_config {
    always_on = true

    dynamic "application_stack" {
      for_each = var.docker_image != "" ? [1] : []
      content {
        docker_image_name = var.docker_image
      }
    }

    # If no Docker image is specified, run Python directly via startup command
    dynamic "application_stack" {
      for_each = var.docker_image == "" ? [1] : []
      content {
        python_version = "3.12"
      }
    }
  }

  app_settings = merge(var.app_settings, {
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
  })

  lifecycle {
    ignore_changes = [
      # Ignore changes to the docker image tag so Terraform doesn't override CI/CD
      site_config[0].application_stack,
    ]
  }
}
