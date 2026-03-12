output "account_ids" {
  description = "Map of subscription key → storage account ID"
  value = {
    for k, sa in azurerm_storage_account.accounts : k => sa.id
  }
}

output "account_names" {
  value = {
    for k, sa in azurerm_storage_account.accounts : k => sa.name
  }
}

output "access_model" {
  description = "Map of subscription key → access model (rbac|key)"
  value = {
    for k, v in local.storage_accounts : k => v.use_rbac ? "rbac" : "key"
  }
}
