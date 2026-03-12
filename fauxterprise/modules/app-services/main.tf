###############################################################################
# App Services, Function Apps, and related PaaS resources
###############################################################################

variable "prefix" {
  type = string
}

variable "subscriptions" {
  type = any
}

variable "networking" {
  description = "Map of vnet-subnet key → subnet ID"
  type        = map(string)
}

variable "tags" {
  type = map(string)
}

# ---------------------------------------------------------------------------
# App Service Plans
# ---------------------------------------------------------------------------
resource "azurerm_service_plan" "prod_plan" {
  name                = "${var.prefix}-prod-asp"
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["app"]
  location            = var.subscriptions["prod_app1"].location
  os_type             = "Linux"
  sku_name            = "P1v3"
  tags                = var.tags
}

resource "azurerm_service_plan" "staging_plan" {
  name                = "${var.prefix}-staging-asp"
  resource_group_name = var.subscriptions["staging"].resource_groups["app"]
  location            = var.subscriptions["staging"].location
  os_type             = "Linux"
  sku_name            = "S1"
  tags                = var.tags
}

resource "azurerm_service_plan" "dev_plan" {
  name                = "${var.prefix}-dev-asp"
  resource_group_name = var.subscriptions["dev"].resource_groups["app"]
  location            = var.subscriptions["dev"].location
  os_type             = "Linux"
  sku_name            = "B1"
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Web Apps
# ---------------------------------------------------------------------------
resource "azurerm_linux_web_app" "prod_api" {
  name                = "${var.prefix}-prod-api"
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["app"]
  location            = var.subscriptions["prod_app1"].location
  service_plan_id     = azurerm_service_plan.prod_plan.id
  tags                = merge(var.tags, { workload = "api" })

  site_config {
    always_on = true
    application_stack {
      python_version = "3.11"
    }
    vnet_route_all_enabled = true
  }

  identity {
    type = "SystemAssigned"
  }

  app_settings = {
    "WEBSITE_RUN_FROM_PACKAGE" = "1"
    "SCM_DO_BUILD_DURING_DEPLOYMENT" = "true"
  }
}

resource "azurerm_linux_web_app" "prod_frontend" {
  name                = "${var.prefix}-prod-frontend"
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["app"]
  location            = var.subscriptions["prod_app1"].location
  service_plan_id     = azurerm_service_plan.prod_plan.id
  tags                = merge(var.tags, { workload = "frontend" })

  site_config {
    always_on = true
    application_stack {
      node_version = "18-lts"
    }
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_linux_web_app" "staging_api" {
  name                = "${var.prefix}-staging-api"
  resource_group_name = var.subscriptions["staging"].resource_groups["app"]
  location            = var.subscriptions["staging"].location
  service_plan_id     = azurerm_service_plan.staging_plan.id
  tags                = merge(var.tags, { workload = "api", environment = "staging" })

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_linux_web_app" "dev_api" {
  name                = "${var.prefix}-dev-api-app"
  resource_group_name = var.subscriptions["dev"].resource_groups["app"]
  location            = var.subscriptions["dev"].location
  service_plan_id     = azurerm_service_plan.dev_plan.id
  tags                = merge(var.tags, { workload = "api", environment = "dev" })

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  identity {
    type = "SystemAssigned"
  }
}

# ---------------------------------------------------------------------------
# Function Apps
# ---------------------------------------------------------------------------
resource "azurerm_service_plan" "func_plan" {
  name                = "${var.prefix}-func-asp"
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["shared"]
  location            = var.subscriptions["prod_app1"].location
  os_type             = "Linux"
  sku_name            = "Y1"
  tags                = var.tags
}

resource "azurerm_storage_account" "func_storage" {
  name                     = "${var.prefix}funcsa"
  resource_group_name      = var.subscriptions["prod_app1"].resource_groups["shared"]
  location                 = var.subscriptions["prod_app1"].location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = var.tags
}

resource "azurerm_linux_function_app" "event_processor" {
  name                       = "${var.prefix}-event-processor"
  resource_group_name        = var.subscriptions["prod_app1"].resource_groups["shared"]
  location                   = var.subscriptions["prod_app1"].location
  service_plan_id            = azurerm_service_plan.func_plan.id
  storage_account_name       = azurerm_storage_account.func_storage.name
  storage_account_access_key = azurerm_storage_account.func_storage.primary_access_key
  tags                       = merge(var.tags, { workload = "event-processing" })

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_linux_function_app" "data_pipeline" {
  name                       = "${var.prefix}-data-pipeline"
  resource_group_name        = var.subscriptions["prod_app2"].resource_groups["app"]
  location                   = var.subscriptions["prod_app2"].location
  service_plan_id            = azurerm_service_plan.func_plan.id
  storage_account_name       = azurerm_storage_account.func_storage.name
  storage_account_access_key = azurerm_storage_account.func_storage.primary_access_key
  tags                       = merge(var.tags, { workload = "data-pipeline" })

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  identity {
    type = "SystemAssigned"
  }
}

# ---------------------------------------------------------------------------
# Application Insights
# ---------------------------------------------------------------------------
resource "azurerm_application_insights" "prod" {
  name                = "${var.prefix}-prod-appinsights"
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["shared"]
  location            = var.subscriptions["prod_app1"].location
  application_type    = "web"
  tags                = var.tags
}

resource "azurerm_application_insights" "staging" {
  name                = "${var.prefix}-staging-appinsights"
  resource_group_name = var.subscriptions["staging"].resource_groups["shared"]
  location            = var.subscriptions["staging"].location
  application_type    = "web"
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Event Hub Namespace (for event streaming)
# ---------------------------------------------------------------------------
resource "azurerm_eventhub_namespace" "prod_events" {
  name                = "${var.prefix}-prod-eventhub"
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["shared"]
  location            = var.subscriptions["prod_app1"].location
  sku                 = "Basic"
  capacity            = 1
  tags                = var.tags
}

resource "azurerm_eventhub" "telemetry" {
  name                = "telemetry"
  namespace_name      = azurerm_eventhub_namespace.prod_events.name
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["shared"]
  partition_count     = 2
  message_retention   = 1
}

# ---------------------------------------------------------------------------
# Service Bus (Staging – message-driven)
# ---------------------------------------------------------------------------
resource "azurerm_servicebus_namespace" "staging_bus" {
  name                = "${var.prefix}-staging-servicebus"
  resource_group_name = var.subscriptions["staging"].resource_groups["shared"]
  location            = var.subscriptions["staging"].location
  sku                 = "Basic"
  tags                = var.tags
}

resource "azurerm_servicebus_queue" "orders" {
  name         = "orders"
  namespace_id = azurerm_servicebus_namespace.staging_bus.id
}

resource "azurerm_servicebus_queue" "notifications" {
  name         = "notifications"
  namespace_id = azurerm_servicebus_namespace.staging_bus.id
}
