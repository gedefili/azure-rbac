# ---------------------------------------------------------------------------
# Storage Account
# Persists graph snapshots and security findings for audit trails.
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "rbac" {
  name                     = "strbac${var.environment}${var.name_suffix}"
  resource_group_name      = azurerm_resource_group.rbac.name
  location                 = azurerm_resource_group.rbac.location
  account_tier             = "Standard"
  account_replication_type = var.storage_replication
  account_kind             = "StorageV2"
  min_tls_version          = "TLS1_2"

  allow_nested_items_to_be_public = false

  tags = var.tags
}

# Blob container for graph snapshots
resource "azurerm_storage_container" "snapshots" {
  name                  = "graph-snapshots"
  storage_account_id    = azurerm_storage_account.rbac.id
  container_access_type = "private"
}

# Lifecycle policy – auto-delete old snapshots
resource "azurerm_storage_management_policy" "snapshots_lifecycle" {
  storage_account_id = azurerm_storage_account.rbac.id

  rule {
    name    = "delete-old-snapshots"
    enabled = true

    filters {
      prefix_match = ["graph-snapshots/20"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.snapshot_retention_days
      }
    }
  }
}
