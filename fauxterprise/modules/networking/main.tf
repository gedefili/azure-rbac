###############################################################################
# Networking – Hub / Spoke VNets, NSGs, and partial ExpressRoute peering
#
# Hub VNet lives in the connectivity subscription.
# Spoke VNets in each workload subscription peer to the hub.
# An ExpressRoute circuit is created but only *partially* connected
# (gateway exists, but peering to staging is incomplete).
###############################################################################

variable "prefix" {
  type = string
}

variable "subscriptions" {
  type = any
}

variable "tags" {
  type = map(string)
}

# ---------------------------------------------------------------------------
# Address space plan
# ---------------------------------------------------------------------------
locals {
  vnets = {
    # ── Hub (Connectivity) ──────────────────────────────────────────────────
    hub = {
      rg_name       = var.subscriptions["connectivity"].resource_groups["networking"]
      location      = var.subscriptions["connectivity"].location
      address_space = ["10.0.0.0/16"]
      subnets = {
        GatewaySubnet       = "10.0.0.0/24"
        AzureFirewallSubnet = "10.0.1.0/24"
        SharedServices      = "10.0.2.0/24"
        Management          = "10.0.3.0/24"
        DnsResolver         = "10.0.4.0/24"
      }
    }

    # ── Identity ────────────────────────────────────────────────────────────
    identity = {
      rg_name       = var.subscriptions["identity"].resource_groups["adds"]
      location      = var.subscriptions["identity"].location
      address_space = ["10.1.0.0/16"]
      subnets = {
        DomainControllers = "10.1.0.0/24"
        EntraConnect      = "10.1.1.0/24"
      }
    }

    # ── Management ──────────────────────────────────────────────────────────
    mgmt = {
      rg_name       = var.subscriptions["management_sub"].resource_groups["logging"]
      location      = var.subscriptions["management_sub"].location
      address_space = ["10.2.0.0/16"]
      subnets = {
        Monitoring  = "10.2.0.0/24"
        Automation  = "10.2.1.0/24"
      }
    }

    # ── Prod App 1 ──────────────────────────────────────────────────────────
    prod_app1 = {
      rg_name       = var.subscriptions["prod_app1"].resource_groups["networking"]
      location      = var.subscriptions["prod_app1"].location
      address_space = ["10.10.0.0/16"]
      subnets = {
        AppSubnet      = "10.10.0.0/24"
        DataSubnet     = "10.10.1.0/24"
        PrivateEndpoints = "10.10.2.0/24"
        AppGateway     = "10.10.3.0/24"
      }
    }

    # ── Prod App 2 ──────────────────────────────────────────────────────────
    prod_app2 = {
      rg_name       = var.subscriptions["prod_app2"].resource_groups["networking"]
      location      = var.subscriptions["prod_app2"].location
      address_space = ["10.11.0.0/16"]
      subnets = {
        AppSubnet      = "10.11.0.0/24"
        DataSubnet     = "10.11.1.0/24"
        MLSubnet       = "10.11.2.0/24"
      }
    }

    # ── Staging ─────────────────────────────────────────────────────────────
    staging = {
      rg_name       = var.subscriptions["staging"].resource_groups["networking"]
      location      = var.subscriptions["staging"].location
      address_space = ["10.20.0.0/16"]
      subnets = {
        AppSubnet      = "10.20.0.0/24"
        DataSubnet     = "10.20.1.0/24"
        TestSubnet     = "10.20.2.0/24"
      }
    }

    # ── Staging Perf ────────────────────────────────────────────────────────
    staging_perf = {
      rg_name       = var.subscriptions["staging_perf"].resource_groups["networking"]
      location      = var.subscriptions["staging_perf"].location
      address_space = ["10.21.0.0/16"]
      subnets = {
        LoadTestAgents = "10.21.0.0/24"
        AppSubnet      = "10.21.1.0/24"
      }
    }

    # ── Dev ─────────────────────────────────────────────────────────────────
    dev = {
      rg_name       = var.subscriptions["dev"].resource_groups["networking"]
      location      = var.subscriptions["dev"].location
      address_space = ["10.30.0.0/16"]
      subnets = {
        AppSubnet      = "10.30.0.0/24"
        DataSubnet     = "10.30.1.0/24"
        Experiments    = "10.30.2.0/24"
      }
    }

    # ── Sandbox ─────────────────────────────────────────────────────────────
    sandbox = {
      rg_name       = var.subscriptions["sandbox"].resource_groups["playground"]
      location      = var.subscriptions["sandbox"].location
      address_space = ["10.40.0.0/16"]
      subnets = {
        General = "10.40.0.0/24"
      }
    }
  }

  # Spokes to peer with hub (everything except hub itself)
  spoke_keys = [for k in keys(local.vnets) : k if k != "hub"]
}

# ---------------------------------------------------------------------------
# Virtual Networks
# ---------------------------------------------------------------------------
resource "azurerm_virtual_network" "vnets" {
  for_each = local.vnets

  name                = "${var.prefix}-${each.key}-vnet"
  resource_group_name = each.value.rg_name
  location            = each.value.location
  address_space       = each.value.address_space
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------
locals {
  subnet_flat = merge([
    for vnet_key, vnet in local.vnets : {
      for snet_name, cidr in vnet.subnets :
      "${vnet_key}-${snet_name}" => {
        vnet_key            = vnet_key
        subnet_name         = snet_name
        resource_group_name = vnet.rg_name
        vnet_name           = azurerm_virtual_network.vnets[vnet_key].name
        address_prefixes    = [cidr]
      }
    }
  ]...)
}

resource "azurerm_subnet" "subnets" {
  for_each = local.subnet_flat

  name                 = each.value.subnet_name
  resource_group_name  = each.value.resource_group_name
  virtual_network_name = each.value.vnet_name
  address_prefixes     = each.value.address_prefixes
}

# ---------------------------------------------------------------------------
# NSGs – one per spoke VNet (hub has Azure Firewall instead)
# ---------------------------------------------------------------------------
resource "azurerm_network_security_group" "spoke_nsgs" {
  for_each = {
    for k in local.spoke_keys : k => local.vnets[k]
  }

  name                = "${var.prefix}-${each.key}-nsg"
  resource_group_name = each.value.rg_name
  location            = each.value.location
  tags                = var.tags

  # Default rule – allow intra-vnet, deny internet inbound
  security_rule {
    name                       = "AllowVNetInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "VirtualNetwork"
  }

  security_rule {
    name                       = "DenyInternetInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

# ---------------------------------------------------------------------------
# Hub ↔ Spoke Peerings
# ---------------------------------------------------------------------------
resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  for_each = toset(local.spoke_keys)

  name                         = "hub-to-${each.key}"
  resource_group_name          = local.vnets["hub"].rg_name
  virtual_network_name         = azurerm_virtual_network.vnets["hub"].name
  remote_virtual_network_id    = azurerm_virtual_network.vnets[each.key].id
  allow_forwarded_traffic      = true
  allow_gateway_transit        = true
  allow_virtual_network_access = true
}

resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  for_each = toset(local.spoke_keys)

  name                         = "${each.key}-to-hub"
  resource_group_name          = local.vnets[each.key].rg_name
  virtual_network_name         = azurerm_virtual_network.vnets[each.key].name
  remote_virtual_network_id    = azurerm_virtual_network.vnets["hub"].id
  allow_forwarded_traffic      = true
  use_remote_gateways          = false # would be true once ER gateway is active
  allow_virtual_network_access = true
}

# ---------------------------------------------------------------------------
# Azure Firewall in Hub
# ---------------------------------------------------------------------------
resource "azurerm_public_ip" "firewall_pip" {
  name                = "${var.prefix}-hub-fw-pip"
  resource_group_name = local.vnets["hub"].rg_name
  location            = local.vnets["hub"].location
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_firewall" "hub" {
  name                = "${var.prefix}-hub-firewall"
  resource_group_name = local.vnets["hub"].rg_name
  location            = local.vnets["hub"].location
  sku_name            = "AZFW_VNet"
  sku_tier            = "Standard"
  tags                = var.tags

  ip_configuration {
    name                 = "fw-ipconfig"
    subnet_id            = azurerm_subnet.subnets["hub-AzureFirewallSubnet"].id
    public_ip_address_id = azurerm_public_ip.firewall_pip.id
  }
}

# ---------------------------------------------------------------------------
# ExpressRoute – Circuit + Gateway (partially configured)
# ---------------------------------------------------------------------------
resource "azurerm_public_ip" "er_gw_pip" {
  name                = "${var.prefix}-er-gw-pip"
  resource_group_name = var.subscriptions["connectivity"].resource_groups["expressroute"]
  location            = var.subscriptions["connectivity"].location
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_express_route_circuit" "er" {
  name                  = "${var.prefix}-expressroute"
  resource_group_name   = var.subscriptions["connectivity"].resource_groups["expressroute"]
  location              = var.subscriptions["connectivity"].location
  service_provider_name = "Equinix"
  peering_location      = "Washington DC"
  bandwidth_in_mbps     = 200
  tags                  = var.tags

  sku {
    tier   = "Standard"
    family = "MeteredData"
  }
}

resource "azurerm_virtual_network_gateway" "er_gateway" {
  name                = "${var.prefix}-er-gateway"
  resource_group_name = local.vnets["hub"].rg_name
  location            = local.vnets["hub"].location
  type                = "ExpressRoute"
  sku                 = "Standard"
  tags                = var.tags

  ip_configuration {
    name                          = "er-gw-ipconfig"
    public_ip_address_id          = azurerm_public_ip.er_gw_pip.id
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.subnets["hub-GatewaySubnet"].id
  }
}

# Private peering – configured on the circuit but NOT connected to staging
# This represents the "partially setup" state requested.
resource "azurerm_express_route_circuit_peering" "private" {
  peering_type                  = "AzurePrivatePeering"
  express_route_circuit_name    = azurerm_express_route_circuit.er.name
  resource_group_name           = var.subscriptions["connectivity"].resource_groups["expressroute"]
  primary_peer_address_prefix   = "172.16.0.0/30"
  secondary_peer_address_prefix = "172.16.0.4/30"
  vlan_id                       = 100
  peer_asn                      = 65001
}

# The gateway-connection to the ER circuit IS created (hub side)…
resource "azurerm_virtual_network_gateway_connection" "hub_er" {
  name                       = "${var.prefix}-hub-er-connection"
  resource_group_name        = local.vnets["hub"].rg_name
  location                   = local.vnets["hub"].location
  type                       = "ExpressRoute"
  virtual_network_gateway_id = azurerm_virtual_network_gateway.er_gateway.id
  express_route_circuit_id   = azurerm_express_route_circuit.er.id
  tags                       = var.tags
}

# …but the staging VNet does NOT have use_remote_gateways = true,
# and there is no dedicated gateway or connection for staging_perf.
# This is the intentional "partial setup" gap.

# ---------------------------------------------------------------------------
# Private DNS Zones (hub-linked)
# ---------------------------------------------------------------------------
resource "azurerm_private_dns_zone" "zones" {
  for_each = toset([
    "privatelink.blob.core.windows.net",
    "privatelink.vaultcore.azure.net",
    "privatelink.database.windows.net",
    "privatelink.azurewebsites.net",
  ])

  name                = each.key
  resource_group_name = var.subscriptions["connectivity"].resource_groups["dns"]
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "hub_links" {
  for_each = azurerm_private_dns_zone.zones

  name                  = "${var.prefix}-hub-link-${replace(each.key, ".", "-")}"
  resource_group_name   = var.subscriptions["connectivity"].resource_groups["dns"]
  private_dns_zone_name = each.value.name
  virtual_network_id    = azurerm_virtual_network.vnets["hub"].id
  registration_enabled  = false
  tags                  = var.tags
}
