###############################################################################
# Subscriptions & Resource Groups
#
# We simulate 10 subscriptions spread across the management group tree.
# Each subscription gets several resource groups representing typical
# workload patterns (networking, data, compute, shared, security, etc.).
#
# NOTE: In a real tenant you would use azurerm_subscription or import
# existing ones. Here we use azurerm_resource_group within the current
# subscription and tag them to *represent* the logical subscription.
# For a demo / plan-only environment this keeps things self-contained.
###############################################################################

variable "prefix" {
  type = string
}

variable "management_groups" {
  description = "Map of management group logical names → IDs"
  type        = map(string)
}

variable "tags" {
  type = map(string)
}

# ---------------------------------------------------------------------------
# Subscription definitions – each maps to a management group placement
# ---------------------------------------------------------------------------
locals {
  subscriptions = {
    # ── Platform ──
    connectivity = {
      display_name     = "${var.prefix}-connectivity-sub"
      mg               = "connectivity"
      location         = "eastus2"
      resource_groups  = ["networking", "expressroute", "dns", "firewall"]
    }
    identity = {
      display_name     = "${var.prefix}-identity-sub"
      mg               = "identity"
      location         = "eastus2"
      resource_groups  = ["adds", "entra-connect", "security"]
    }
    management_sub = {
      display_name     = "${var.prefix}-management-sub"
      mg               = "management"
      location         = "eastus2"
      resource_groups  = ["logging", "monitoring", "automation", "backup"]
    }

    # ── Landing Zones – Production ──
    prod_app1 = {
      display_name     = "${var.prefix}-prod-app1-sub"
      mg               = "production"
      location         = "eastus2"
      resource_groups  = ["app", "data", "networking", "shared", "security"]
    }
    prod_app2 = {
      display_name     = "${var.prefix}-prod-app2-sub"
      mg               = "production"
      location         = "westus2"
      resource_groups  = ["app", "data", "networking", "shared", "ml"]
    }

    # ── Landing Zones – Staging ──
    staging = {
      display_name     = "${var.prefix}-staging-sub"
      mg               = "staging"
      location         = "eastus2"
      resource_groups  = ["app", "data", "networking", "shared", "testing"]
    }
    staging_perf = {
      display_name     = "${var.prefix}-staging-perf-sub"
      mg               = "staging"
      location         = "westus2"
      resource_groups  = ["app", "data", "networking", "loadtest"]
    }

    # ── Landing Zones – Development ──
    dev = {
      display_name     = "${var.prefix}-dev-sub"
      mg               = "development"
      location         = "eastus2"
      resource_groups  = ["app", "data", "networking", "shared", "experiments"]
    }

    # ── Sandbox ──
    sandbox = {
      display_name     = "${var.prefix}-sandbox-sub"
      mg               = "sandbox"
      location         = "centralus"
      resource_groups  = ["playground", "prototypes", "ml-experiments"]
    }

    # ── Decommissioned ──
    decommissioned = {
      display_name     = "${var.prefix}-decommissioned-sub"
      mg               = "decommissioned"
      location         = "eastus"
      resource_groups  = ["legacy-app", "archive"]
    }
  }

  # Flatten subscription×resource_group into a flat map for for_each
  rg_flat = merge([
    for sub_key, sub in local.subscriptions : {
      for rg in sub.resource_groups :
      "${sub_key}-${rg}" => {
        sub_key  = sub_key
        rg_name  = "${var.prefix}-${sub_key}-${rg}-rg"
        location = sub.location
        tags     = merge(var.tags, {
          subscription = sub.display_name
          mg_placement = sub.mg
        })
      }
    }
  ]...)
}

# ---------------------------------------------------------------------------
# Resource Groups
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "rgs" {
  for_each = local.rg_flat

  name     = each.value.rg_name
  location = each.value.location
  tags     = each.value.tags
}

# ---------------------------------------------------------------------------
# Management Group ↔ Subscription associations
# (Simulated – in a real environment these would use
#  azurerm_management_group_subscription_association)
# ---------------------------------------------------------------------------
# In a demo we just tag the RGs; the association is conceptual.
