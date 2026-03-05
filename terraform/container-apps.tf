# ---------------------------------------------------------------------------
# Container App Environment
# ---------------------------------------------------------------------------

resource "azurerm_container_app_environment" "rbac" {
  name                       = "cae-rbac-${var.environment}"
  location                   = azurerm_resource_group.rbac.location
  resource_group_name        = azurerm_resource_group.rbac.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.rbac.id

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Container App – Dashboard (web app with HTTP ingress)
# ---------------------------------------------------------------------------

resource "azurerm_container_app" "dashboard" {
  name                         = "rbac-dashboard"
  container_app_environment_id = azurerm_container_app_environment.rbac.id
  resource_group_name          = azurerm_resource_group.rbac.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.rbac.id]
  }

  registry {
    server   = azurerm_container_registry.rbac.login_server
    identity = azurerm_user_assigned_identity.rbac.id
  }

  ingress {
    external_enabled = true
    target_port      = 5000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.dashboard_min_replicas
    max_replicas = var.dashboard_max_replicas

    container {
      name   = "dashboard"
      image  = "${azurerm_container_registry.rbac.login_server}/${var.container_image_name}:${var.container_image_tag}"
      cpu    = var.dashboard_cpu
      memory = var.dashboard_memory

      env {
        name  = "AZURE_USE_MSI"
        value = "true"
      }

      env {
        name  = "KEY_VAULT_URI"
        value = azurerm_key_vault.rbac.vault_uri
      }

      env {
        name  = "AZURE_STORAGE_ACCOUNT_NAME"
        value = azurerm_storage_account.rbac.name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.rbac.client_id
      }

      env {
        name  = "DASHBOARD_PORT"
        value = "5000"
      }
    }
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Container App Job – Graph Builder (scheduled nightly)
# ---------------------------------------------------------------------------

resource "azurerm_container_app_job" "graph_builder" {
  name                         = "rbac-graph-builder"
  location                     = azurerm_resource_group.rbac.location
  container_app_environment_id = azurerm_container_app_environment.rbac.id
  resource_group_name          = azurerm_resource_group.rbac.name
  replica_timeout_in_seconds   = var.graph_builder_timeout

  schedule_trigger_config {
    cron_expression          = var.graph_builder_cron
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.rbac.id]
  }

  registry {
    server   = azurerm_container_registry.rbac.login_server
    identity = azurerm_user_assigned_identity.rbac.id
  }

  template {
    container {
      name   = "graph-builder"
      image  = "${azurerm_container_registry.rbac.login_server}/${var.container_image_name}:${var.container_image_tag}"
      cpu    = var.graph_builder_cpu
      memory = var.graph_builder_memory

      command = ["azure-rbac", "build", "--output", "/tmp/graph.json"]

      env {
        name  = "AZURE_USE_MSI"
        value = "true"
      }

      env {
        name  = "KEY_VAULT_URI"
        value = azurerm_key_vault.rbac.vault_uri
      }

      env {
        name  = "AZURE_STORAGE_ACCOUNT_NAME"
        value = azurerm_storage_account.rbac.name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.rbac.client_id
      }
    }
  }

  tags = var.tags
}
