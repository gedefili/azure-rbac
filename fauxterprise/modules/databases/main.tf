###############################################################################
# Databases – SQL, PostgreSQL Flexible, Cosmos DB
###############################################################################

variable "prefix" {
  type = string
}

variable "subscriptions" {
  type = any
}

variable "tags" {
  type = map(string)
}

# ---------------------------------------------------------------------------
# Azure SQL (Production App 1)
# ---------------------------------------------------------------------------
resource "azurerm_mssql_server" "prod_sql" {
  name                         = "${var.prefix}-prod-sql"
  resource_group_name          = var.subscriptions["prod_app1"].resource_groups["data"]
  location                     = var.subscriptions["prod_app1"].location
  version                      = "12.0"
  administrator_login          = "sqladmin"
  administrator_login_password = "FauxSQL-P@ss2024!"
  minimum_tls_version          = "1.2"
  tags                         = var.tags

  azuread_administrator {
    login_username = "AzureAD Admin"
    object_id      = data.azurerm_client_config.current.object_id
  }

  lifecycle {
    ignore_changes = [administrator_login_password]
  }
}

data "azurerm_client_config" "current" {}

resource "azurerm_mssql_database" "prod_db" {
  name      = "${var.prefix}-prod-appdb"
  server_id = azurerm_mssql_server.prod_sql.id
  sku_name  = "S0"
  tags      = var.tags
}

resource "azurerm_mssql_database" "prod_analytics" {
  name      = "${var.prefix}-prod-analyticsdb"
  server_id = azurerm_mssql_server.prod_sql.id
  sku_name  = "S0"
  tags      = var.tags
}

# ---------------------------------------------------------------------------
# PostgreSQL Flexible (Staging)
# ---------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "staging_pg" {
  name                          = "${var.prefix}-staging-pg"
  resource_group_name           = var.subscriptions["staging"].resource_groups["data"]
  location                      = var.subscriptions["staging"].location
  version                       = "15"
  administrator_login           = "pgadmin"
  administrator_password        = "FauxPG-P@ss2024!"
  storage_mb                    = 32768
  sku_name                      = "B_Standard_B1ms"
  zone                          = "1"
  tags                          = var.tags

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = true
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  lifecycle {
    ignore_changes = [administrator_password]
  }
}

resource "azurerm_postgresql_flexible_server_database" "staging_app" {
  name      = "staging_app"
  server_id = azurerm_postgresql_flexible_server.staging_pg.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# ---------------------------------------------------------------------------
# Cosmos DB (Production App 2 – ML metadata)
# ---------------------------------------------------------------------------
resource "azurerm_cosmosdb_account" "prod_cosmos" {
  name                = "${var.prefix}-prod-cosmos"
  resource_group_name = var.subscriptions["prod_app2"].resource_groups["data"]
  location            = var.subscriptions["prod_app2"].location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  tags                = var.tags

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.subscriptions["prod_app2"].location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "ml_metadata" {
  name                = "ml-metadata"
  resource_group_name = var.subscriptions["prod_app2"].resource_groups["data"]
  account_name        = azurerm_cosmosdb_account.prod_cosmos.name
  throughput          = 400
}

# ---------------------------------------------------------------------------
# Redis Cache (Staging – performance testing)
# ---------------------------------------------------------------------------
resource "azurerm_redis_cache" "staging_redis" {
  name                = "${var.prefix}-staging-redis"
  resource_group_name = var.subscriptions["staging_perf"].resource_groups["app"]
  location            = var.subscriptions["staging_perf"].location
  capacity            = 0
  family              = "C"
  sku_name            = "Basic"
  minimum_tls_version = "1.2"
  tags                = var.tags
}
