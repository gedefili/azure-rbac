# ---------------------------------------------------------------------------
# User-Assigned Managed Identity
# Used by both the dashboard Container App and the graph builder job.
# ---------------------------------------------------------------------------

resource "azurerm_user_assigned_identity" "rbac" {
  name                = "id-rbac-${var.environment}"
  location            = azurerm_resource_group.rbac.location
  resource_group_name = azurerm_resource_group.rbac.name

  tags = var.tags
}

# ---------------------------------------------------------------------------
# RBAC role assignments for the managed identity
# ---------------------------------------------------------------------------

# Read secrets from Key Vault
resource "azurerm_role_assignment" "kv_secrets_user" {
  scope                = azurerm_key_vault.rbac.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.rbac.principal_id
}

# Read/write graph snapshots in Storage
resource "azurerm_role_assignment" "storage_blob_contributor" {
  scope                = azurerm_storage_account.rbac.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.rbac.principal_id
}

# Read Azure RBAC data across the subscription
# Note: For tenant-wide scanning, assign Reader at the management group or
# tenant root level outside of this module.
resource "azurerm_role_assignment" "subscription_reader" {
  scope                = "/subscriptions/${var.subscription_id}"
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.rbac.principal_id
}
