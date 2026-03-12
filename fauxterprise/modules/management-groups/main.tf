###############################################################################
# Management Group hierarchy – Cloud Adoption Framework (reduced)
#
# Tenant Root
#  └─ Fauxterprise (root)
#       ├─ Platform
#       │    ├─ Connectivity      (hub networking, ExpressRoute)
#       │    ├─ Identity           (AD DS, identity services)
#       │    └─ Management         (logging, monitoring)
#       ├─ Landing Zones
#       │    ├─ Production
#       │    ├─ Staging
#       │    └─ Development
#       ├─ Sandbox                 (experimentation)
#       └─ Decommissioned          (retired workloads)
###############################################################################

variable "prefix" {
  type = string
}

variable "tenant_id" {
  type = string
}

# ── Root ────────────────────────────────────────────────────────────────────
resource "azurerm_management_group" "root" {
  display_name               = "${var.prefix}-enterprise"
  name                       = "${var.prefix}-enterprise"
}

# ── Platform ────────────────────────────────────────────────────────────────
resource "azurerm_management_group" "platform" {
  display_name               = "${var.prefix}-platform"
  name                       = "${var.prefix}-platform"
  parent_management_group_id = azurerm_management_group.root.id
}

resource "azurerm_management_group" "connectivity" {
  display_name               = "${var.prefix}-connectivity"
  name                       = "${var.prefix}-connectivity"
  parent_management_group_id = azurerm_management_group.platform.id
}

resource "azurerm_management_group" "identity_mg" {
  display_name               = "${var.prefix}-identity"
  name                       = "${var.prefix}-identity"
  parent_management_group_id = azurerm_management_group.platform.id
}

resource "azurerm_management_group" "management" {
  display_name               = "${var.prefix}-management"
  name                       = "${var.prefix}-management"
  parent_management_group_id = azurerm_management_group.platform.id
}

# ── Landing Zones ───────────────────────────────────────────────────────────
resource "azurerm_management_group" "landing_zones" {
  display_name               = "${var.prefix}-landing-zones"
  name                       = "${var.prefix}-landing-zones"
  parent_management_group_id = azurerm_management_group.root.id
}

resource "azurerm_management_group" "production" {
  display_name               = "${var.prefix}-production"
  name                       = "${var.prefix}-production"
  parent_management_group_id = azurerm_management_group.landing_zones.id
}

resource "azurerm_management_group" "staging" {
  display_name               = "${var.prefix}-staging"
  name                       = "${var.prefix}-staging"
  parent_management_group_id = azurerm_management_group.landing_zones.id
}

resource "azurerm_management_group" "development" {
  display_name               = "${var.prefix}-development"
  name                       = "${var.prefix}-development"
  parent_management_group_id = azurerm_management_group.landing_zones.id
}

# ── Sandbox ─────────────────────────────────────────────────────────────────
resource "azurerm_management_group" "sandbox" {
  display_name               = "${var.prefix}-sandbox"
  name                       = "${var.prefix}-sandbox"
  parent_management_group_id = azurerm_management_group.root.id
}

# ── Decommissioned ──────────────────────────────────────────────────────────
resource "azurerm_management_group" "decommissioned" {
  display_name               = "${var.prefix}-decommissioned"
  name                       = "${var.prefix}-decommissioned"
  parent_management_group_id = azurerm_management_group.root.id
}
