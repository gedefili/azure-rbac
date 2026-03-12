###############################################################################
# Identity – 100 Azure AD users, groups, and service principals
#
# First names  → famous computer scientists
# Last names   → famous artificial intelligence scientists
# Users are placed into team-based security groups.
###############################################################################

variable "prefix" {
  type = string
}

variable "domain" {
  type = string
}

variable "tags" {
  type = map(string)
}

# ---------------------------------------------------------------------------
# Name pools
# ---------------------------------------------------------------------------
locals {
  # 20 famous computer scientists (first names)
  first_names = [
    "Ada",        # Lovelace
    "Alan",       # Turing
    "Grace",      # Hopper
    "Donald",     # Knuth
    "Edsger",     # Dijkstra
    "John",       # von Neumann
    "Claude",     # Shannon
    "Barbara",    # Liskov
    "Dennis",     # Ritchie
    "Linus",      # Torvalds
    "Vint",       # Cerf
    "Tim",        # Berners-Lee
    "Margaret",   # Hamilton
    "Hedy",       # Lamarr
    "Niklaus",    # Wirth
    "Ken",        # Thompson
    "Tony",       # Hoare
    "Leslie",     # Lamport
    "Frances",    # Allen
    "Shafi",      # Goldwasser
  ]

  # 20 famous AI scientists (last names)
  last_names = [
    "Turing",       # Alan Turing
    "McCarthy",     # John McCarthy
    "Minsky",       # Marvin Minsky
    "Hinton",       # Geoffrey Hinton
    "Bengio",       # Yoshua Bengio
    "LeCun",        # Yann LeCun
    "Ng",           # Andrew Ng
    "Russell",      # Stuart Russell
    "Norvig",       # Peter Norvig
    "Pearl",        # Judea Pearl
    "Sutton",       # Richard Sutton
    "Goodfellow",   # Ian Goodfellow
    "Schmidhuber",  # Jürgen Schmidhuber
    "Hochreiter",   # Sepp Hochreiter
    "Thrun",        # Sebastian Thrun
    "Kaplan",       # Jerry Kaplan
    "Hassabis",     # Demis Hassabis
    "Amodei",       # Dario Amodei
    "Li",           # Fei-Fei Li
    "Altman",       # Sam Altman (AI industry leader)
  ]

  # Generate 100 users by cycling through first × last names
  # Index i: first = i % 20, last = floor(i / 20) + offset to avoid repeats
  users = [
    for i in range(100) : {
      index      = i
      first_name = local.first_names[i % 20]
      last_name  = local.last_names[(floor(i / 20) + i % 20) % 20]
      department = local.departments[i % length(local.departments)]
      job_title  = local.job_titles[i % length(local.job_titles)]
    }
  ]

  # Create a unique display-name → UPN mapping
  user_map = {
    for u in local.users :
    "user-${u.index}" => {
      display_name = "${u.first_name} ${u.last_name}"
      first_name   = u.first_name
      last_name    = u.last_name
      upn          = lower("${u.first_name}.${u.last_name}.${u.index}@${var.domain}")
      department   = u.department
      job_title    = u.job_title
    }
  }

  departments = [
    "Platform Engineering",
    "Cloud Security",
    "Application Development",
    "Data Engineering",
    "DevOps",
    "Identity & Access",
    "Network Operations",
    "AI / ML",
    "QA / Testing",
    "IT Operations",
  ]

  job_titles = [
    "Cloud Engineer",
    "Security Analyst",
    "Software Developer",
    "Data Engineer",
    "DevOps Engineer",
    "IAM Specialist",
    "Network Engineer",
    "ML Engineer",
    "QA Engineer",
    "IT Administrator",
    "Solutions Architect",
    "SRE",
    "Tech Lead",
    "Engineering Manager",
    "Principal Engineer",
    "Staff Developer",
    "Security Architect",
    "Platform Lead",
    "Data Scientist",
    "Infrastructure Engineer",
  ]

  # ---------------------------------------------------------------------------
  # Group definitions – users assigned round-robin by department
  # ---------------------------------------------------------------------------
  groups = {
    "platform-admins"   = { description = "Platform engineering team with elevated access" }
    "security-team"     = { description = "Cloud security analysts and architects" }
    "app-developers"    = { description = "Application development team" }
    "data-engineers"    = { description = "Data engineering and analytics team" }
    "devops-team"       = { description = "DevOps and SRE team" }
    "identity-admins"   = { description = "Identity and access management" }
    "network-ops"       = { description = "Network operations team" }
    "ml-team"           = { description = "Machine learning engineers" }
    "qa-team"           = { description = "Quality assurance and testing" }
    "it-ops"            = { description = "General IT operations" }
    "read-only-auditors"       = { description = "Read-only auditors for compliance" }
    "contributor-leads"        = { description = "Tech leads with Contributor at LZ scope" }
    "sandbox-users"            = { description = "Users who can experiment in sandbox" }
    "keyvault-admins"          = { description = "Key Vault administrators" }
    "storage-blob-contributors" = { description = "Users with blob data contributor" }
  }

  # Map departments → primary group
  dept_to_group = {
    "Platform Engineering"     = "platform-admins"
    "Cloud Security"           = "security-team"
    "Application Development"  = "app-developers"
    "Data Engineering"         = "data-engineers"
    "DevOps"                   = "devops-team"
    "Identity & Access"        = "identity-admins"
    "Network Operations"       = "network-ops"
    "AI / ML"                  = "ml-team"
    "QA / Testing"             = "qa-team"
    "IT Operations"            = "it-ops"
  }
}

# ---------------------------------------------------------------------------
# Azure AD Users
# ---------------------------------------------------------------------------
resource "azuread_user" "users" {
  for_each = local.user_map

  display_name        = each.value.display_name
  user_principal_name = each.value.upn
  mail_nickname       = replace(lower("${each.value.first_name}.${each.value.last_name}.${split("-", each.key)[1]}"), " ", "")
  password            = "FauxP@ss${each.value.first_name}${split("-", each.key)[1]}!"
  department          = each.value.department
  job_title           = each.value.job_title

  lifecycle {
    ignore_changes = [password]
  }
}

# ---------------------------------------------------------------------------
# Azure AD Groups
# ---------------------------------------------------------------------------
resource "azuread_group" "groups" {
  for_each = local.groups

  display_name     = "${var.prefix}-${each.key}"
  description      = each.value.description
  security_enabled = true
}

# ---------------------------------------------------------------------------
# Group memberships – primary group based on department
# ---------------------------------------------------------------------------
resource "azuread_group_member" "primary" {
  for_each = local.user_map

  group_object_id  = azuread_group.groups[local.dept_to_group[each.value.department]].id
  member_object_id = azuread_user.users[each.key].id
}

# Every 3rd user also gets read-only-auditors
resource "azuread_group_member" "auditors" {
  for_each = {
    for k, v in local.user_map : k => v
    if tonumber(split("-", k)[1]) % 3 == 0
  }

  group_object_id  = azuread_group.groups["read-only-auditors"].id
  member_object_id = azuread_user.users[each.key].id
}

# Every 5th user gets sandbox access
resource "azuread_group_member" "sandbox" {
  for_each = {
    for k, v in local.user_map : k => v
    if tonumber(split("-", k)[1]) % 5 == 0
  }

  group_object_id  = azuread_group.groups["sandbox-users"].id
  member_object_id = azuread_user.users[each.key].id
}

# Every 7th user is a contributor-lead
resource "azuread_group_member" "leads" {
  for_each = {
    for k, v in local.user_map : k => v
    if tonumber(split("-", k)[1]) % 7 == 0
  }

  group_object_id  = azuread_group.groups["contributor-leads"].id
  member_object_id = azuread_user.users[each.key].id
}

# Even-indexed users get keyvault-admins or storage blob contributor (alternating)
resource "azuread_group_member" "keyvault" {
  for_each = {
    for k, v in local.user_map : k => v
    if tonumber(split("-", k)[1]) % 4 == 0
  }

  group_object_id  = azuread_group.groups["keyvault-admins"].id
  member_object_id = azuread_user.users[each.key].id
}

resource "azuread_group_member" "storage_blob" {
  for_each = {
    for k, v in local.user_map : k => v
    if tonumber(split("-", k)[1]) % 4 == 2
  }

  group_object_id  = azuread_group.groups["storage-blob-contributors"].id
  member_object_id = azuread_user.users[each.key].id
}

# ---------------------------------------------------------------------------
# Service Principals for workload identity
# ---------------------------------------------------------------------------
resource "azuread_application" "apps" {
  for_each = toset(["deploy-pipeline", "monitoring-agent", "backup-service", "data-pipeline", "ml-inference"])

  display_name = "${var.prefix}-sp-${each.key}"
}

resource "azuread_service_principal" "sps" {
  for_each = azuread_application.apps

  client_id = each.value.client_id
}
