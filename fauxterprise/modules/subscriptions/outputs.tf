output "subscription_map" {
  description = "Map of subscription key → metadata (display_name, location, mg, rg_names)"
  value = {
    for sub_key, sub in local.subscriptions : sub_key => {
      display_name = sub.display_name
      location     = sub.location
      mg           = sub.mg
      resource_groups = {
        for rg in sub.resource_groups :
        rg => azurerm_resource_group.rgs["${sub_key}-${rg}"].name
      }
      resource_group_ids = {
        for rg in sub.resource_groups :
        rg => azurerm_resource_group.rgs["${sub_key}-${rg}"].id
      }
    }
  }
}
