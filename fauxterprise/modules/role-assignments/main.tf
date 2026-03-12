###############################################################################
# Role Assignments – spread users and groups across resources
#
# This creates a realistic tangle of RBAC:
#   • Group-level assignments at subscription / RG scope
#   • Individual user assignments (some intentionally over-privileged)
#   • Storage data-plane roles vs management-plane roles
#   • Key Vault RBAC roles for vaults using that model
#   • A mix of built-in roles at different scopes
###############################################################################

variable "users" {
  description = "Map of user key → object ID"
  type        = map(string)
}

variable "groups" {
  description = "Map of group name → object ID"
  type        = map(string)
}

variable "subscriptions" {
  description = "Subscription metadata map"
  type        = any
}

variable "keyvaults" {
  description = "Map of subscription key → Key Vault ID"
  type        = map(string)
}

variable "storage" {
  description = "Map of subscription key → Storage Account ID"
  type        = map(string)
}

variable "tags" {
  type = map(string)
}

# ---------------------------------------------------------------------------
# Built-in role definition IDs (well-known)
# ---------------------------------------------------------------------------
locals {
  roles = {
    owner                          = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
    contributor                    = "b24988ac-6180-42a0-ab88-20f7382dd24c"
    reader                         = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
    user_access_admin              = "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9"
    storage_blob_data_contributor  = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
    storage_blob_data_reader       = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
    keyvault_admin                 = "00482a5a-887f-4fb3-b363-3b7fe8e74483"
    keyvault_secrets_user          = "4633458b-17de-408a-b874-0445c86b69e6"
    keyvault_reader                = "21090545-7ca7-4776-b22c-e363652d74d2"
    network_contributor            = "4d97b98b-1d4f-4787-a291-c67834d212e7"
    monitoring_contributor         = "749f88d5-cbae-40b8-bcfc-e573ddc772fa"
    monitoring_reader              = "43d0d8ad-25c7-4714-9337-8ba259a9fe05"
    sql_db_contributor             = "9b7fa17d-e63e-47b0-bb0a-15c516ac86ec"
    cosmos_db_operator             = "230815da-be43-4aae-9cb4-875f7bd000aa"
    aks_cluster_admin              = "0ab0b1a8-8aac-4efd-b8c2-3ee1fb270be8"
    acr_push                       = "8311e382-0749-4cb8-b61a-304f252e45ec"
    log_analytics_contributor      = "92aaf0da-9dab-42b6-94a3-d43ce8d16293"
    website_contributor            = "de139f84-1756-47ae-9be6-808fbbe84772"
  }

  # Sort user keys for stable indexing
  user_keys = sort(keys(var.users))
}

# ═══════════════════════════════════════════════════════════════════════════
# GROUP-LEVEL ASSIGNMENTS (management-plane)
# ═══════════════════════════════════════════════════════════════════════════

# Platform admins → Owner on all platform RGs
resource "azurerm_role_assignment" "platform_admins_connectivity" {
  for_each = var.subscriptions["connectivity"].resource_group_ids

  scope                = each.value
  role_definition_name = "Owner"
  principal_id         = var.groups["platform-admins"]
}

resource "azurerm_role_assignment" "platform_admins_management" {
  for_each = var.subscriptions["management_sub"].resource_group_ids

  scope                = each.value
  role_definition_name = "Owner"
  principal_id         = var.groups["platform-admins"]
}

# Security team → Reader everywhere + Security Admin on prod
resource "azurerm_role_assignment" "security_reader_prod1" {
  for_each = var.subscriptions["prod_app1"].resource_group_ids

  scope                = each.value
  role_definition_name = "Reader"
  principal_id         = var.groups["security-team"]
}

resource "azurerm_role_assignment" "security_reader_prod2" {
  for_each = var.subscriptions["prod_app2"].resource_group_ids

  scope                = each.value
  role_definition_name = "Reader"
  principal_id         = var.groups["security-team"]
}

# DevOps → Contributor on staging & dev
resource "azurerm_role_assignment" "devops_staging" {
  for_each = var.subscriptions["staging"].resource_group_ids

  scope                = each.value
  role_definition_name = "Contributor"
  principal_id         = var.groups["devops-team"]
}

resource "azurerm_role_assignment" "devops_dev" {
  for_each = var.subscriptions["dev"].resource_group_ids

  scope                = each.value
  role_definition_name = "Contributor"
  principal_id         = var.groups["devops-team"]
}

# App developers → Contributor on dev, Reader on staging
resource "azurerm_role_assignment" "appdev_dev" {
  for_each = var.subscriptions["dev"].resource_group_ids

  scope                = each.value
  role_definition_name = "Contributor"
  principal_id         = var.groups["app-developers"]
}

resource "azurerm_role_assignment" "appdev_staging_reader" {
  for_each = var.subscriptions["staging"].resource_group_ids

  scope                = each.value
  role_definition_name = "Reader"
  principal_id         = var.groups["app-developers"]
}

# Network ops → Network Contributor on connectivity
resource "azurerm_role_assignment" "netops_connectivity" {
  for_each = var.subscriptions["connectivity"].resource_group_ids

  scope                = each.value
  role_definition_name = "Network Contributor"
  principal_id         = var.groups["network-ops"]
}

# Data engineers → Contributor on prod data RGs
resource "azurerm_role_assignment" "data_eng_prod1" {
  scope                = var.subscriptions["prod_app1"].resource_group_ids["data"]
  role_definition_name = "Contributor"
  principal_id         = var.groups["data-engineers"]
}

resource "azurerm_role_assignment" "data_eng_prod2" {
  scope                = var.subscriptions["prod_app2"].resource_group_ids["data"]
  role_definition_name = "Contributor"
  principal_id         = var.groups["data-engineers"]
}

# ML team → Contributor on prod_app2 ml RG
resource "azurerm_role_assignment" "ml_team_prod2" {
  scope                = var.subscriptions["prod_app2"].resource_group_ids["ml"]
  role_definition_name = "Contributor"
  principal_id         = var.groups["ml-team"]
}

# IT Ops → Monitoring Contributor on management
resource "azurerm_role_assignment" "itops_monitoring" {
  for_each = var.subscriptions["management_sub"].resource_group_ids

  scope                = each.value
  role_definition_name = "Monitoring Contributor"
  principal_id         = var.groups["it-ops"]
}

# Auditors → Reader on everything (prod subscriptions)
resource "azurerm_role_assignment" "auditors_prod1" {
  for_each = var.subscriptions["prod_app1"].resource_group_ids

  scope                = each.value
  role_definition_name = "Reader"
  principal_id         = var.groups["read-only-auditors"]
}

resource "azurerm_role_assignment" "auditors_prod2" {
  for_each = var.subscriptions["prod_app2"].resource_group_ids

  scope                = each.value
  role_definition_name = "Reader"
  principal_id         = var.groups["read-only-auditors"]
}

# Contributor leads → Contributor on landing-zone RGs
resource "azurerm_role_assignment" "leads_staging" {
  for_each = var.subscriptions["staging"].resource_group_ids

  scope                = each.value
  role_definition_name = "Contributor"
  principal_id         = var.groups["contributor-leads"]
}

# Sandbox users → Contributor on sandbox
resource "azurerm_role_assignment" "sandbox_users" {
  for_each = var.subscriptions["sandbox"].resource_group_ids

  scope                = each.value
  role_definition_name = "Contributor"
  principal_id         = var.groups["sandbox-users"]
}

# Identity admins → Owner on identity sub
resource "azurerm_role_assignment" "identity_admins" {
  for_each = var.subscriptions["identity"].resource_group_ids

  scope                = each.value
  role_definition_name = "Owner"
  principal_id         = var.groups["identity-admins"]
}

# ═══════════════════════════════════════════════════════════════════════════
# STORAGE DATA-PLANE ROLES
# ═══════════════════════════════════════════════════════════════════════════

# Storage blob contributors group → data contributor on storage accounts
resource "azurerm_role_assignment" "storage_blob_group" {
  for_each = var.storage

  scope                = each.value
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.groups["storage-blob-contributors"]
}

# ═══════════════════════════════════════════════════════════════════════════
# KEY VAULT RBAC ROLES (only for vaults using RBAC model)
# ═══════════════════════════════════════════════════════════════════════════

# Key Vault admins group → Key Vault Administrator on all vaults
resource "azurerm_role_assignment" "kv_admin_group" {
  for_each = var.keyvaults

  scope                = each.value
  role_definition_name = "Key Vault Administrator"
  principal_id         = var.groups["keyvault-admins"]
}

# Security team → Key Vault Reader on all vaults
resource "azurerm_role_assignment" "kv_reader_security" {
  for_each = var.keyvaults

  scope                = each.value
  role_definition_name = "Key Vault Reader"
  principal_id         = var.groups["security-team"]
}

# ═══════════════════════════════════════════════════════════════════════════
# INDIVIDUAL USER ASSIGNMENTS (some intentionally messy)
# ═══════════════════════════════════════════════════════════════════════════

# User 0 – "Break glass" account with Owner on prod (over-privileged)
resource "azurerm_role_assignment" "break_glass_prod1" {
  for_each = var.subscriptions["prod_app1"].resource_group_ids

  scope                = each.value
  role_definition_name = "Owner"
  principal_id         = var.users[local.user_keys[0]]
}

# User 1 – Owner on connectivity (network lead)
resource "azurerm_role_assignment" "net_lead" {
  for_each = var.subscriptions["connectivity"].resource_group_ids

  scope                = each.value
  role_definition_name = "Owner"
  principal_id         = var.users[local.user_keys[1]]
}

# User 2 – User Access Administrator on staging (can grant access)
resource "azurerm_role_assignment" "staging_uaa" {
  for_each = var.subscriptions["staging"].resource_group_ids

  scope                = each.value
  role_definition_name = "User Access Administrator"
  principal_id         = var.users[local.user_keys[2]]
}

# Users 10-14 – individual Contributor on prod_app1 app RG
resource "azurerm_role_assignment" "individual_contrib" {
  for_each = {
    for i in range(10, 15) : local.user_keys[i] => var.users[local.user_keys[i]]
  }

  scope                = var.subscriptions["prod_app1"].resource_group_ids["app"]
  role_definition_name = "Contributor"
  principal_id         = each.value
}

# Users 20-24 – Storage Blob Data Reader on prod storage
resource "azurerm_role_assignment" "individual_blob_reader" {
  for_each = {
    for i in range(20, 25) : local.user_keys[i] => var.users[local.user_keys[i]]
  }

  scope                = var.storage["prod_app1"]
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = each.value
}

# Users 30-34 – Key Vault Secrets User on staging vault
resource "azurerm_role_assignment" "individual_kv_secrets" {
  for_each = {
    for i in range(30, 35) : local.user_keys[i] => var.users[local.user_keys[i]]
  }

  scope                = var.keyvaults["staging"]
  role_definition_name = "Key Vault Secrets User"
  principal_id         = each.value
}

# User 50 – Reader on decommissioned (forgot to remove)
resource "azurerm_role_assignment" "stale_decomm" {
  scope                = values(var.subscriptions["decommissioned"].resource_group_ids)[0]
  role_definition_name = "Reader"
  principal_id         = var.users[local.user_keys[50]]
}

# Users 60-64 – Monitoring Reader on management
resource "azurerm_role_assignment" "individual_monitoring" {
  for_each = {
    for i in range(60, 65) : local.user_keys[i] => var.users[local.user_keys[i]]
  }

  scope                = values(var.subscriptions["management_sub"].resource_group_ids)[0]
  role_definition_name = "Monitoring Reader"
  principal_id         = each.value
}

# Users 70-74 – Website Contributor on staging app
resource "azurerm_role_assignment" "individual_web_staging" {
  for_each = {
    for i in range(70, 75) : local.user_keys[i] => var.users[local.user_keys[i]]
  }

  scope                = var.subscriptions["staging"].resource_group_ids["app"]
  role_definition_name = "Website Contributor"
  principal_id         = each.value
}

# Users 80-84 – Contributor on sandbox (personal experiments)
resource "azurerm_role_assignment" "individual_sandbox" {
  for_each = {
    for i in range(80, 85) : local.user_keys[i] => var.users[local.user_keys[i]]
  }

  scope                = values(var.subscriptions["sandbox"].resource_group_ids)[0]
  role_definition_name = "Contributor"
  principal_id         = each.value
}

# User 99 – Owner on multiple scopes (over-privileged shadow admin)
resource "azurerm_role_assignment" "shadow_admin_prod2" {
  for_each = var.subscriptions["prod_app2"].resource_group_ids

  scope                = each.value
  role_definition_name = "Owner"
  principal_id         = var.users[local.user_keys[99]]
}

resource "azurerm_role_assignment" "shadow_admin_staging" {
  for_each = var.subscriptions["staging"].resource_group_ids

  scope                = each.value
  role_definition_name = "Owner"
  principal_id         = var.users[local.user_keys[99]]
}
