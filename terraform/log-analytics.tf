# ---------------------------------------------------------------------------
# Log Analytics Workspace
# Required by the Container App Environment for logging and monitoring.
# ---------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "rbac" {
  name                = "log-rbac-${var.environment}"
  location            = azurerm_resource_group.rbac.location
  resource_group_name = azurerm_resource_group.rbac.name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days

  tags = var.tags
}
