output "subnet_ids" {
  description = "Map of vnet-subnet key → subnet ID"
  value = {
    for k, s in azurerm_subnet.subnets : k => s.id
  }
}

output "vnet_ids" {
  description = "Map of vnet key → VNet ID"
  value = {
    for k, v in azurerm_virtual_network.vnets : k => v.id
  }
}

output "firewall_private_ip" {
  value = azurerm_firewall.hub.ip_configuration[0].private_ip_address
}

output "express_route_circuit_id" {
  value = azurerm_express_route_circuit.er.id
}
