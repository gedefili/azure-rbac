###############################################################################
# Compute resources – VMs, VMSS, Container Instances, AKS
###############################################################################

variable "prefix" {
  type = string
}

variable "subscriptions" {
  type = any
}

variable "networking" {
  description = "Map of vnet-subnet key → subnet ID"
  type        = map(string)
}

variable "tags" {
  type = map(string)
}

# ---------------------------------------------------------------------------
# Log Analytics (shared workspace for diagnostics)
# ---------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "central" {
  name                = "${var.prefix}-central-law"
  resource_group_name = var.subscriptions["management_sub"].resource_groups["monitoring"]
  location            = var.subscriptions["management_sub"].location
  sku                 = "PerGB2018"
  retention_in_days   = 90
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Network Interfaces for VMs
# ---------------------------------------------------------------------------
resource "azurerm_network_interface" "prod_app1_web" {
  count               = 2
  name                = "${var.prefix}-prod-app1-web-nic-${count.index}"
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["app"]
  location            = var.subscriptions["prod_app1"].location
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.networking["prod_app1-AppSubnet"]
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_network_interface" "identity_dc" {
  count               = 2
  name                = "${var.prefix}-identity-dc-nic-${count.index}"
  resource_group_name = var.subscriptions["identity"].resource_groups["adds"]
  location            = var.subscriptions["identity"].location
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.networking["identity-DomainControllers"]
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_network_interface" "mgmt_jumpbox" {
  name                = "${var.prefix}-mgmt-jumpbox-nic"
  resource_group_name = var.subscriptions["management_sub"].resource_groups["automation"]
  location            = var.subscriptions["management_sub"].location
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.networking["mgmt-Automation"]
    private_ip_address_allocation = "Dynamic"
  }
}

# ---------------------------------------------------------------------------
# Virtual Machines
# ---------------------------------------------------------------------------

# Production web servers
resource "azurerm_linux_virtual_machine" "prod_web" {
  count               = 2
  name                = "${var.prefix}-prod-web-${count.index}"
  resource_group_name = var.subscriptions["prod_app1"].resource_groups["app"]
  location            = var.subscriptions["prod_app1"].location
  size                = "Standard_B2s"
  admin_username      = "azureadmin"
  tags                = merge(var.tags, { role = "webserver" })

  network_interface_ids = [azurerm_network_interface.prod_app1_web[count.index].id]

  admin_ssh_key {
    username   = "azureadmin"
    public_key = tls_private_key.ssh.public_key_openssh
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }
}

# Domain controllers
resource "azurerm_windows_virtual_machine" "dc" {
  count               = 2
  name                = "${var.prefix}-dc-${count.index}"
  resource_group_name = var.subscriptions["identity"].resource_groups["adds"]
  location            = var.subscriptions["identity"].location
  size                = "Standard_B2s"
  admin_username      = "azureadmin"
  admin_password      = "FauxDC-P@ss2024!"
  tags                = merge(var.tags, { role = "domain-controller" })

  network_interface_ids = [azurerm_network_interface.identity_dc[count.index].id]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2022-datacenter-g2"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }

  lifecycle {
    ignore_changes = [admin_password]
  }
}

# Management jumpbox
resource "azurerm_linux_virtual_machine" "jumpbox" {
  name                = "${var.prefix}-mgmt-jumpbox"
  resource_group_name = var.subscriptions["management_sub"].resource_groups["automation"]
  location            = var.subscriptions["management_sub"].location
  size                = "Standard_B1s"
  admin_username      = "azureadmin"
  tags                = merge(var.tags, { role = "jumpbox" })

  network_interface_ids = [azurerm_network_interface.mgmt_jumpbox.id]

  admin_ssh_key {
    username   = "azureadmin"
    public_key = tls_private_key.ssh.public_key_openssh
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }
}

# ---------------------------------------------------------------------------
# SSH key (shared, for demo only)
# ---------------------------------------------------------------------------
resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# ---------------------------------------------------------------------------
# AKS Cluster (Production App 2 – ML workloads)
# ---------------------------------------------------------------------------
resource "azurerm_kubernetes_cluster" "prod_aks" {
  name                = "${var.prefix}-prod-aks"
  resource_group_name = var.subscriptions["prod_app2"].resource_groups["app"]
  location            = var.subscriptions["prod_app2"].location
  dns_prefix          = "${var.prefix}-prod-aks"
  tags                = merge(var.tags, { workload = "ml-inference" })

  default_node_pool {
    name           = "system"
    node_count     = 2
    vm_size        = "Standard_B2s"
    vnet_subnet_id = var.networking["prod_app2-AppSubnet"]
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
    service_cidr   = "10.200.0.0/16"
    dns_service_ip = "10.200.0.10"
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.central.id
  }
}

# ---------------------------------------------------------------------------
# Container Instances (Dev quick-deploy)
# ---------------------------------------------------------------------------
resource "azurerm_container_group" "dev_api" {
  name                = "${var.prefix}-dev-api"
  resource_group_name = var.subscriptions["dev"].resource_groups["app"]
  location            = var.subscriptions["dev"].location
  os_type             = "Linux"
  ip_address_type     = "Private"
  subnet_ids          = [var.networking["dev-AppSubnet"]]
  tags                = var.tags

  container {
    name   = "api"
    image  = "mcr.microsoft.com/azuredocs/aci-helloworld:latest"
    cpu    = "0.5"
    memory = "0.5"

    ports {
      port     = 80
      protocol = "TCP"
    }
  }
}

# ---------------------------------------------------------------------------
# Container Registry (shared, in management sub)
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "acr" {
  name                = "${var.prefix}enterpriseacr"
  resource_group_name = var.subscriptions["management_sub"].resource_groups["automation"]
  location            = var.subscriptions["management_sub"].location
  sku                 = "Standard"
  admin_enabled       = false
  tags                = var.tags
}
