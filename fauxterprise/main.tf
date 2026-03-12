###############################################################################
# Fauxterprise – A simulated enterprise Azure environment
#
# This Terraform project provisions a realistic multi-subscription, multi-
# management-group Azure tenant modelled after the Cloud Adoption Framework
# (CAF) Enterprise-Scale landing zone architecture.  It is intentionally
# "messy" – mixing RBAC and key-based access, partially-configured peering,
# and a wide variety of resource types – so that the azure-rbac analyser has
# plenty of real-world patterns to discover.
###############################################################################

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.47"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

provider "azuread" {}

data "azurerm_client_config" "current" {}

# ---------------------------------------------------------------------------
# Locals – central place for subscription & naming metadata
# ---------------------------------------------------------------------------
locals {
  tenant_id = data.azurerm_client_config.current.tenant_id
  prefix    = var.prefix
  tags = {
    environment = "fauxterprise"
    managed_by  = "terraform"
    purpose     = "azure-rbac-demo"
  }
}

# ---------------------------------------------------------------------------
# 1. Management Group hierarchy (CAF-lite)
# ---------------------------------------------------------------------------
module "management_groups" {
  source    = "./modules/management-groups"
  prefix    = local.prefix
  tenant_id = local.tenant_id
}

# ---------------------------------------------------------------------------
# 2. Azure AD users (100 famous CS × AI scientists)
# ---------------------------------------------------------------------------
module "identity" {
  source = "./modules/identity"
  prefix = local.prefix
  domain = var.domain
  tags   = local.tags
}

# ---------------------------------------------------------------------------
# 3. Subscriptions & resource groups
# ---------------------------------------------------------------------------
module "subscriptions" {
  source            = "./modules/subscriptions"
  prefix            = local.prefix
  management_groups = module.management_groups.group_ids
  tags              = local.tags
}

# ---------------------------------------------------------------------------
# 4. Networking – Hub/spoke + partial ExpressRoute peering
# ---------------------------------------------------------------------------
module "networking" {
  source        = "./modules/networking"
  prefix        = local.prefix
  subscriptions = module.subscriptions.subscription_map
  tags          = local.tags
}

# ---------------------------------------------------------------------------
# 5. Storage accounts (alternating RBAC / key access)
# ---------------------------------------------------------------------------
module "storage" {
  source        = "./modules/storage"
  prefix        = local.prefix
  subscriptions = module.subscriptions.subscription_map
  tags          = local.tags
}

# ---------------------------------------------------------------------------
# 6. Key Vaults (alternating RBAC / access-policy)
# ---------------------------------------------------------------------------
module "keyvault" {
  source        = "./modules/keyvault"
  prefix        = local.prefix
  subscriptions = module.subscriptions.subscription_map
  tenant_id     = local.tenant_id
  tags          = local.tags
}

# ---------------------------------------------------------------------------
# 7. Compute, databases, app services & other resources
# ---------------------------------------------------------------------------
module "compute" {
  source        = "./modules/compute"
  prefix        = local.prefix
  subscriptions = module.subscriptions.subscription_map
  networking    = module.networking.subnet_ids
  tags          = local.tags
}

module "databases" {
  source        = "./modules/databases"
  prefix        = local.prefix
  subscriptions = module.subscriptions.subscription_map
  tags          = local.tags
}

module "app_services" {
  source        = "./modules/app-services"
  prefix        = local.prefix
  subscriptions = module.subscriptions.subscription_map
  networking    = module.networking.subnet_ids
  tags          = local.tags
}

# ---------------------------------------------------------------------------
# 8. Role assignments – spread users across resources
# ---------------------------------------------------------------------------
module "role_assignments" {
  source = "./modules/role-assignments"

  users         = module.identity.user_principal_ids
  groups        = module.identity.group_ids
  subscriptions = module.subscriptions.subscription_map
  keyvaults     = module.keyvault.vault_ids
  storage       = module.storage.account_ids
  tags          = local.tags
}
