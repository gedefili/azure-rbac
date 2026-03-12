# Fauxterprise Scenarios

This document describes the security and RBAC scenarios modeled by the
Fauxterprise Terraform environment.  Each scenario is defined in
[scenarios.json](scenarios.json) with structured metadata; this file provides
the human-readable overlay.

---

## Critical

### S01 – Over-privileged break-glass account

**User 0** has **Owner** on every resource group in `prod_app1`.  This
simulates a break-glass account whose broad scope was never reduced after the
initial deployment.

- **Terraform**: `modules/role-assignments/main.tf` → `break_glass_prod1`
- **Expected finding**: Owner assigned directly to an individual user in production

### S02 – Shadow admin with cross-environment Owner

**User 99** has **Owner** on all RGs in both `prod_app2` _and_ `staging`.
This models an unchecked shadow admin who accumulated privileges across
environments without periodic access review.

- **Terraform**: `modules/role-assignments/main.tf` → `shadow_admin_prod2`, `shadow_admin_staging`
- **Expected finding**: Owner across multiple environments on a single user

---

## High

### S03 – User Access Administrator on staging

**User 2** has **User Access Administrator** on every staging RG, granting the
ability to assign roles to others — effectively privilege escalation.

- **Terraform**: `modules/role-assignments/main.tf` → `staging_uaa`
- **Expected finding**: UAA assigned to individual user

### S04 – Stale access on decommissioned subscription

**User 50** retains **Reader** on the `decommissioned` subscription.  The
workload is retired, but the access was never revoked.

- **Terraform**: `modules/role-assignments/main.tf` → `stale_decomm`
- **Expected finding**: Role assignment on decommissioned resource

### S08 – Broad platform group with Owner

The **platform-admins** group holds **Owner** on all RGs across both
`connectivity` and `management_sub`.  The blast radius spans core
infrastructure.

- **Terraform**: `modules/role-assignments/main.tf` → `platform_admins_connectivity`, `platform_admins_management`
- **Expected finding**: Group Owner on multiple infrastructure subscriptions

---

## Medium

### S03 – User Access Administrator on staging

_(see High section above)_

### S05 – Direct user assignments instead of groups

**Users 10–14** each have individual **Contributor** on `prod_app1/app` RG.
Group-based assignment is preferred for auditability and lifecycle management.

- **Terraform**: `modules/role-assignments/main.tf` → `individual_contrib`
- **Expected finding**: Direct user role assignments on production

### S06 – Mixed storage access models

Storage accounts alternate between RBAC (`shared_access_key_enabled=false`)
and key-based (`shared_access_key_enabled=true`) access.  Key-based accounts
bypass RBAC, making access invisible to role assignment audits.

- **Terraform**: `modules/storage/main.tf` → `azurerm_storage_account.accounts`
- **Pattern**: Even-indexed subs → RBAC; odd-indexed → key

### S07 – Mixed Key Vault access models

Key Vaults alternate between RBAC authorization and classic access-policy
(opposite of storage).  Access-policy vaults require a separate audit path.

- **Terraform**: `modules/keyvault/main.tf` → `azurerm_key_vault.vaults`
- **Pattern**: Odd-indexed subs → RBAC; even-indexed → access-policy

### S10 – Individual Key Vault secrets access

**Users 30–34** have **Key Vault Secrets User** on the staging vault.

- **Terraform**: `modules/role-assignments/main.tf` → `individual_kv_secrets`

### S13 – Network lead with full infrastructure Owner

**User 1** has **Owner** on all connectivity RGs as an individual assignment,
overlapping with the platform-admins group.

- **Terraform**: `modules/role-assignments/main.tf` → `net_lead`

---

## Low

### S09 – Individual storage blob data readers

**Users 20–24** have **Storage Blob Data Reader** on `prod_app1` storage.

- **Terraform**: `modules/role-assignments/main.tf` → `individual_blob_reader`

### S11 – Monitoring role sprawl

**Users 60–64** have individual **Monitoring Reader** on `management_sub`,
overlapping with the it-ops group's Monitoring Contributor.

- **Terraform**: `modules/role-assignments/main.tf` → `individual_monitoring`

### S12 – Sandbox with overly broad Contributor

**Users 80–84** have individual **Contributor** on sandbox in addition to the
`sandbox-users` group assignment.

- **Terraform**: `modules/role-assignments/main.tf` → `individual_sandbox`

### S14 – Website Contributor on staging

**Users 70–74** have **Website Contributor** on the staging app RG.

- **Terraform**: `modules/role-assignments/main.tf` → `individual_web_staging`

### S16 – Overlapping auditor and department memberships

Every 3rd user is added to `read-only-auditors` in addition to their
department group.  The cross-cutting membership may accumulate unintended
access through future role assignments on the auditor group.

- **Terraform**: `modules/identity/main.tf` → `azuread_group_member.auditors`

---

## Informational

### S15 – CAF-lite management group hierarchy

The hierarchy follows a reduced Cloud Adoption Framework pattern:

```
Fauxterprise (root)
├── Platform
│   ├── Connectivity
│   ├── Identity
│   └── Management
├── Landing Zones
│   ├── Production
│   ├── Staging
│   └── Development
├── Sandbox
└── Decommissioned
```

Role inheritance flows down this tree.  11 management groups across 3 levels.

### S17 – Incomplete ExpressRoute peering

The hub/spoke network includes an ExpressRoute circuit, but peering to staging
is intentionally incomplete — simulating a real-world misconfiguration.

- **Terraform**: `modules/networking/main.tf`

### S18 – Service principal proliferation

Five SPs are created: `deploy-pipeline`, `monitoring-agent`, `backup-service`,
`data-pipeline`, `ml-inference`.  Each should be reviewed for least-privilege
and credential rotation.

- **Terraform**: `modules/identity/main.tf` → `azuread_application.apps`
