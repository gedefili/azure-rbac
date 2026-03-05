# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "resource_group_name" {
  description = "Name of the resource group."
  value       = azurerm_resource_group.rbac.name
}

output "container_app_environment_name" {
  description = "Name of the Container App Environment."
  value       = azurerm_container_app_environment.rbac.name
}

output "dashboard_fqdn" {
  description = "FQDN of the dashboard Container App (HTTPS)."
  value       = azurerm_container_app.dashboard.ingress[0].fqdn
}

output "dashboard_url" {
  description = "Full URL of the dashboard."
  value       = "https://${azurerm_container_app.dashboard.ingress[0].fqdn}"
}

output "acr_login_server" {
  description = "Login server of the Azure Container Registry."
  value       = azurerm_container_registry.rbac.login_server
}

output "storage_account_name" {
  description = "Name of the storage account."
  value       = azurerm_storage_account.rbac.name
}

output "keyvault_uri" {
  description = "URI of the Key Vault."
  value       = azurerm_key_vault.rbac.vault_uri
}

output "managed_identity_client_id" {
  description = "Client ID of the user-assigned managed identity."
  value       = azurerm_user_assigned_identity.rbac.client_id
}

output "managed_identity_principal_id" {
  description = "Principal (object) ID of the user-assigned managed identity."
  value       = azurerm_user_assigned_identity.rbac.principal_id
}

output "log_analytics_workspace_id" {
  description = "Resource ID of the Log Analytics workspace."
  value       = azurerm_log_analytics_workspace.rbac.id
}
