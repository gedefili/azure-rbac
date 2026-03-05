# ---------------------------------------------------------------------------
# Azure Container Registry
# Stores the Docker image for the dashboard and graph builder.
# ---------------------------------------------------------------------------

resource "azurerm_container_registry" "rbac" {
  name                = "acrrbac${var.environment}${var.name_suffix}"
  resource_group_name = azurerm_resource_group.rbac.name
  location            = azurerm_resource_group.rbac.location
  sku                 = "Basic"
  admin_enabled       = false

  tags = var.tags
}

# Allow the managed identity to pull images from ACR
resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.rbac.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.rbac.principal_id
}
