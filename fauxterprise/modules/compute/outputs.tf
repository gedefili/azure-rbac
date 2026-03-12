output "aks_cluster_id" {
  value = azurerm_kubernetes_cluster.prod_aks.id
}

output "acr_id" {
  value = azurerm_container_registry.acr.id
}

output "law_id" {
  value = azurerm_log_analytics_workspace.central.id
}

output "vm_identities" {
  description = "System-assigned managed identity principal IDs"
  value = merge(
    { for idx, vm in azurerm_linux_virtual_machine.prod_web : "prod-web-${idx}" => vm.identity[0].principal_id },
    { for idx, vm in azurerm_windows_virtual_machine.dc : "dc-${idx}" => vm.identity[0].principal_id },
    { jumpbox = azurerm_linux_virtual_machine.jumpbox.identity[0].principal_id },
  )
}
