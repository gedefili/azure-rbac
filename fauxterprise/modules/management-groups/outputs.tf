output "group_ids" {
  description = "Map of management group logical names to their IDs"
  value = {
    root            = azurerm_management_group.root.id
    platform        = azurerm_management_group.platform.id
    connectivity    = azurerm_management_group.connectivity.id
    identity        = azurerm_management_group.identity_mg.id
    management      = azurerm_management_group.management.id
    landing_zones   = azurerm_management_group.landing_zones.id
    production      = azurerm_management_group.production.id
    staging         = azurerm_management_group.staging.id
    development     = azurerm_management_group.development.id
    sandbox         = azurerm_management_group.sandbox.id
    decommissioned  = azurerm_management_group.decommissioned.id
  }
}
