output "vault_ids" {
  description = "Map of subscription key → Key Vault ID"
  value = {
    for k, kv in azurerm_key_vault.vaults : k => kv.id
  }
}

output "vault_uris" {
  value = {
    for k, kv in azurerm_key_vault.vaults : k => kv.vault_uri
  }
}

output "access_model" {
  description = "Map of subscription key → access model (rbac|access-policy)"
  value = {
    for k, v in local.keyvaults : k => v.use_rbac ? "rbac" : "access-policy"
  }
}
