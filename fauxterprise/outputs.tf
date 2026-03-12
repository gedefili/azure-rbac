output "management_groups" {
  description = "Management group hierarchy IDs"
  value       = module.management_groups.group_ids
}

output "subscriptions" {
  description = "Subscription metadata map"
  value       = module.subscriptions.subscription_map
}

output "user_count" {
  description = "Number of Azure AD users created"
  value       = length(module.identity.user_principal_ids)
}

output "group_ids" {
  description = "Security group object IDs"
  value       = module.identity.group_ids
}

output "storage_access_models" {
  description = "Storage access model per subscription (rbac vs key)"
  value       = module.storage.access_model
}

output "keyvault_access_models" {
  description = "Key Vault access model per subscription (rbac vs access-policy)"
  value       = module.keyvault.access_model
}

output "express_route_circuit_id" {
  description = "ExpressRoute circuit ID (partially configured)"
  value       = module.networking.express_route_circuit_id
}
