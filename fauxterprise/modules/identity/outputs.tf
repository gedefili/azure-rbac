output "user_principal_ids" {
  description = "Map of user key → object ID"
  value = {
    for k, u in azuread_user.users : k => u.id
  }
}

output "user_upns" {
  description = "Map of user key → UPN"
  value = {
    for k, u in azuread_user.users : k => u.user_principal_name
  }
}

output "group_ids" {
  description = "Map of group name → object ID"
  value = {
    for k, g in azuread_group.groups : k => g.id
  }
}

output "service_principal_ids" {
  description = "Map of SP name → object ID"
  value = {
    for k, sp in azuread_service_principal.sps : k => sp.id
  }
}
