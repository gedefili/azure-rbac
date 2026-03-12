###############################################################################
# Storage Accounts – one per subscription, alternating RBAC / key access
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

locals {
  # Pick the first RG in each subscription for storage placement
  storage_accounts = {
    for idx, sub_key in sort(keys(var.subscriptions)) : sub_key => {
      # Alternate: even index → RBAC (shared_access_key disabled),
      #            odd index  → key-based (shared_access_key enabled)
      use_rbac     = idx % 2 == 0
      rg_name      = values(var.subscriptions[sub_key].resource_groups)[0]
      location     = var.subscriptions[sub_key].location
      display_name = var.subscriptions[sub_key].display_name
    }
  }
}

resource "azurerm_storage_account" "accounts" {
  for_each = local.storage_accounts

  name                            = replace("${var.prefix}${each.key}sa", "-", "")
  resource_group_name             = each.value.rg_name
  location                        = each.value.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  shared_access_key_enabled       = !each.value.use_rbac
  allow_nested_items_to_be_public = false
  min_tls_version                 = "TLS1_2"

  tags = merge(var.tags, {
    access_model = each.value.use_rbac ? "rbac" : "key"
    subscription = each.value.display_name
  })
}

# Blob containers
resource "azurerm_storage_container" "data" {
  for_each = local.storage_accounts

  name                  = "data"
  storage_account_id    = azurerm_storage_account.accounts[each.key].id
  container_access_type = "private"
}

resource "azurerm_storage_container" "logs" {
  for_each = local.storage_accounts

  name                  = "logs"
  storage_account_id    = azurerm_storage_account.accounts[each.key].id
  container_access_type = "private"
}

resource "azurerm_storage_container" "backups" {
  for_each = {
    for k, v in local.storage_accounts : k => v
    if contains(["prod_app1", "prod_app2", "management_sub"], k)
  }

  name                  = "backups"
  storage_account_id    = azurerm_storage_account.accounts[each.key].id
  container_access_type = "private"
}

# Table storage for some subscriptions
resource "azurerm_storage_table" "audit" {
  for_each = {
    for k, v in local.storage_accounts : k => v
    if contains(["management_sub", "prod_app1", "staging"], k)
  }

  name                 = "auditlog"
  storage_account_id   = azurerm_storage_account.accounts[each.key].id
}

# Queue for event-driven workloads
resource "azurerm_storage_queue" "events" {
  for_each = {
    for k, v in local.storage_accounts : k => v
    if contains(["prod_app1", "prod_app2", "staging", "dev"], k)
  }

  name                 = "events"
  storage_account_id   = azurerm_storage_account.accounts[each.key].id
}
