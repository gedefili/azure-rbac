output "sql_server_id" {
  value = azurerm_mssql_server.prod_sql.id
}

output "cosmos_id" {
  value = azurerm_cosmosdb_account.prod_cosmos.id
}

output "postgresql_id" {
  value = azurerm_postgresql_flexible_server.staging_pg.id
}

output "redis_id" {
  value = azurerm_redis_cache.staging_redis.id
}
