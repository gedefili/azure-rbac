###############################################################################
# Key Vaults – one per subscription, alternating RBAC / access-policy
###############################################################################

variable "prefix" {
  type = string
}

variable "subscriptions" {
  type = any
}

variable "tenant_id" {
  type = string
}

variable "tags" {
  type = map(string)
}

data "azurerm_client_config" "current" {}

locals {
  keyvaults = {
    for idx, sub_key in sort(keys(var.subscriptions)) : sub_key => {
      # Alternate: even index → access-policy model,
      #            odd index  → RBAC model
      # (Opposite of storage, so we get both patterns in each sub)
      use_rbac     = idx % 2 == 1
      rg_name      = values(var.subscriptions[sub_key].resource_groups)[0]
      location     = var.subscriptions[sub_key].location
      display_name = var.subscriptions[sub_key].display_name
    }
  }
}

resource "azurerm_key_vault" "vaults" {
  for_each = local.keyvaults

  name                        = "${var.prefix}-${each.key}-kv"
  resource_group_name         = each.value.rg_name
  location                    = each.value.location
  tenant_id                   = var.tenant_id
  sku_name                    = "standard"
  soft_delete_retention_days  = 7
  purge_protection_enabled    = false
  enable_rbac_authorization   = each.value.use_rbac
  enabled_for_disk_encryption = true

  tags = merge(var.tags, {
    access_model = each.value.use_rbac ? "rbac" : "access-policy"
    subscription = each.value.display_name
  })

  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }
}

# Access policies for vaults using the access-policy model
# Give the current deployer full access
resource "azurerm_key_vault_access_policy" "deployer" {
  for_each = {
    for k, v in local.keyvaults : k => v if !v.use_rbac
  }

  key_vault_id = azurerm_key_vault.vaults[each.key].id
  tenant_id    = var.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = [
    "Get", "List", "Set", "Delete", "Purge", "Recover",
  ]
  key_permissions = [
    "Get", "List", "Create", "Delete", "Purge", "Recover",
    "WrapKey", "UnwrapKey",
  ]
  certificate_permissions = [
    "Get", "List", "Create", "Delete", "Purge",
  ]
}

# Seed each vault with a couple of demo secrets
resource "azurerm_key_vault_secret" "db_password" {
  for_each = azurerm_key_vault.vaults

  name         = "db-connection-password"
  value        = "P@ssw0rd-${each.key}-demo"  # intentionally weak for demo
  key_vault_id = each.value.id

  depends_on = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "api_key" {
  for_each = azurerm_key_vault.vaults

  name         = "api-key"
  value        = "ak-${each.key}-${substr(sha256(each.key), 0, 16)}"
  key_vault_id = each.value.id

  depends_on = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "storage_key" {
  for_each = {
    for k, v in local.keyvaults : k => v
    if contains(["prod_app1", "prod_app2", "staging", "management_sub"], k)
  }

  name         = "storage-account-key"
  value        = "demo-storage-key-${each.key}"
  key_vault_id = azurerm_key_vault.vaults[each.key].id

  depends_on = [azurerm_key_vault_access_policy.deployer]
}
