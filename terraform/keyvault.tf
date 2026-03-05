# ---------------------------------------------------------------------------
# Azure Key Vault
# Stores secrets used by the RBAC tool (AI Foundry key, etc.).
# Uses RBAC-based access control (no access policies).
# ---------------------------------------------------------------------------

resource "azurerm_key_vault" "rbac" {
  name                       = "kv-rbac-${var.environment}${var.name_suffix}"
  location                   = azurerm_resource_group.rbac.location
  resource_group_name        = azurerm_resource_group.rbac.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = var.keyvault_soft_delete_retention_days
  purge_protection_enabled   = true

  tags = var.tags
}

# Grant the Terraform deployer admin access to manage secrets during apply.
# In production, consider scoping this to a CI/CD service principal and
# removing manual admin access after initial provisioning.
resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.rbac.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Store AI Foundry endpoint (if provided)
resource "azurerm_key_vault_secret" "ai_foundry_endpoint" {
  count        = var.ai_foundry_endpoint != "" ? 1 : 0
  name         = "AiFoundryEndpoint"
  value        = var.ai_foundry_endpoint
  key_vault_id = azurerm_key_vault.rbac.id

  depends_on = [azurerm_role_assignment.kv_admin]
}

# Store AI Foundry key (if provided)
resource "azurerm_key_vault_secret" "ai_foundry_key" {
  count        = var.ai_foundry_key != "" ? 1 : 0
  name         = "AiFoundryKey"
  value        = var.ai_foundry_key
  key_vault_id = azurerm_key_vault.rbac.id

  depends_on = [azurerm_role_assignment.kv_admin]
}
