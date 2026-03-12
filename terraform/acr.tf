# ---------------------------------------------------------------------------
# Azure Container Registry
# Stores the Docker image for the dashboard and graph builder.
#
# Security notes:
#   - Admin account is disabled (only managed identity / RBAC pulls).
#   - Premium SKU enables content trust, private endpoints, and
#     geo-replication for production.
#   - For dev/stg, override with var.acr_sku = "Basic".
# ---------------------------------------------------------------------------

resource "azurerm_container_registry" "rbac" {
  name                = "acrrbac${var.environment}${var.name_suffix}"
  resource_group_name = azurerm_resource_group.rbac.name
  location            = azurerm_resource_group.rbac.location
  sku                 = var.acr_sku
  admin_enabled       = false

  # Quarantine policy – holds pushed images for scanning before promotion
  quarantine_policy_enabled = var.acr_sku == "Premium" ? true : null

  tags = var.tags
}

# Allow the managed identity to pull images from ACR
resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.rbac.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.rbac.principal_id
}
