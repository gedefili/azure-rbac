# Security and Design Review Guide

This document provides a structured approach for reviewing the security posture and architecture of the Azure RBAC Permission Graph Tool. Use it as a companion to [SECURITY.md](../SECURITY.md) and [architecture.md](architecture.md).

---

## Quick Reference – File Map

| File | Purpose | Security-Relevant? |
|---|---|---|
| [Dockerfile](../Dockerfile) | Multi-stage container build | ✅ Image supply chain |
| [.dockerignore](../.dockerignore) | Excludes secrets from image context | ✅ Prevents data leaks |
| [terraform/main.tf](../terraform/main.tf) | Provider config, resource group | ✅ Provider version pinning |
| [terraform/identity.tf](../terraform/identity.tf) | Managed identity + RBAC roles | ✅ Least privilege |
| [terraform/keyvault.tf](../terraform/keyvault.tf) | Key Vault with network ACLs | ✅ Secrets storage |
| [terraform/storage.tf](../terraform/storage.tf) | Storage account (no shared key) | ✅ Data at rest |
| [terraform/acr.tf](../terraform/acr.tf) | Container registry (Premium) | ✅ Image integrity |
| [terraform/container-apps.tf](../terraform/container-apps.tf) | Dashboard + job with health probes | ✅ Runtime config |
| [terraform/variables.tf](../terraform/variables.tf) | Input variables with validation | ✅ Config boundaries |
| [src/azure_rbac/azure_client.py](../src/azure_rbac/azure_client.py) | Azure SDK wrapper | ✅ Auth chain |
| [src/azure_rbac/ai_advisor.py](../src/azure_rbac/ai_advisor.py) | AI Foundry integration | ✅ Data sent to LLM |
| [src/azure_rbac/dashboard/app.py](../src/azure_rbac/dashboard/app.py) | Flask REST API | ✅ Web attack surface |
| [src/azure_rbac/security_analyzer.py](../src/azure_rbac/security_analyzer.py) | RBAC rule engine | Analysis logic |
| [src/azure_rbac/graph_builder.py](../src/azure_rbac/graph_builder.py) | NetworkX graph construction | Data model |

---

## Review Area 1: Container Image Build Pipeline

### What to Check

1. **Dockerfile exists** at the project root and is used by CI/CD.
2. **Multi-stage build**: Build dependencies (gcc, pip) must not be in the final image.
3. **Non-root user**: The `USER` directive must set a non-root user.
4. **No secrets in build context**: `.dockerignore` must exclude `.env`, `*.tfvars`, `.terraform/`, `*.tfstate`.
5. **Base image**: Uses an official Python slim image with a pinned minor version.
6. **HEALTHCHECK**: Defined in Dockerfile for orchestrator integration.

### Key Finding (Pre-Hardening)

> **There was no Dockerfile or `.dockerignore` in the repository.** The Terraform configuration and docs referenced container images from ACR, but the image build pipeline was entirely missing. This has been resolved — see [Dockerfile](../Dockerfile) and [.dockerignore](../.dockerignore).

### CI/CD Image Build Flow

```
 Azure DevOps Pipeline (azure-pipelines.yml)
 ┌──────────────────────────────┐
 │ 1. Checkout code              │
 │ 2. pip install + pytest       │
 │ 3. ruff check + mypy          │
 │ 4. docker build (multi-stage) │──── Dockerfile
 │ 5. Trivy vulnerability scan   │──── Fail on CRITICAL / HIGH
 │ 6. docker push to ACR         │──── Tags: git SHA + build ID + latest
 │ 7. az containerapp update     │──── SHA-tagged image
 │ 8. Health check verification  │
 └──────────────────────────────┘
```

> **Authentication**: The pipeline uses **Workload Identity Federation (OIDC)** via Azure DevOps service connections — no client secrets to manage or rotate. See [azure-devops-setup.md](azure-devops-setup.md).

---

## Review Area 2: Authentication Chain

### Managed Identity (MSI) Flow

```
Container App / Job
    │
    │  AZURE_USE_MSI=true
    │  AZURE_CLIENT_ID=<mi-client-id>
    ▼
ManagedIdentityCredential
    │
    ├──► Key Vault  (Key Vault Secrets User)
    ├──► Storage    (Storage Blob Data Contributor)
    ├──► ACR        (AcrPull)
    └──► ARM API    (Reader on subscription)
```

### Authentication Priority in `azure_client.py`

```
1. AZURE_USE_MSI=true          → ManagedIdentityCredential
2. AZURE_CLIENT_ID +           → ClientSecretCredential
   AZURE_CLIENT_SECRET +          (requires AZURE_TENANT_ID)
   AZURE_TENANT_ID
3. Fallback                    → DefaultAzureCredential
```

### What to Verify

- [ ] In production, only option 1 (MSI) should be used.
- [ ] `AZURE_CLIENT_SECRET` must **never** be set as a plain environment variable in Container Apps — use Key Vault references.
- [ ] The managed identity principal ID matches the RBAC assignments in `identity.tf`.

---

## Review Area 3: Network Boundaries

### Current Network Configuration

```
Internet ──TLS──► Container Apps Ingress (external_enabled = true)
                   │
                   ├──► Key Vault      (network ACLs: deny + Azure bypass)
                   ├──► Storage        (RBAC-only, no shared key)
                   ├──► ACR            (public endpoint, RBAC-only)
                   └──► ARM/Graph API  (Azure backbone)
```

### Recommended Production Configuration

```
Internet ──TLS──► APIM / WAF ──► Container Apps (internal VNet)
                                   │
                                   ├──► Key Vault      (private endpoint)
                                   ├──► Storage        (private endpoint)
                                   ├──► ACR            (private endpoint)
                                   └──► ARM/Graph API  (Azure backbone)
```

### Action Items

| Priority | Action | Terraform File |
|---|---|---|
| HIGH | Deploy Container App Environment into a VNet | `container-apps.tf` |
| HIGH | Add private endpoint for Key Vault | `keyvault.tf` |
| MEDIUM | Add private endpoint for Storage | `storage.tf` |
| MEDIUM | Add private endpoint for ACR | `acr.tf` |
| LOW | Add Azure Front Door or API Management as a WAF | New file |

---

## Review Area 4: Data Flow and Sensitivity

### Graph Builder Data Flow

```
Azure ARM API                    Azure Graph API
    │                                │
    │ Role assignments,              │ Principal display names
    │ role definitions,              │ (users, groups, SPs)
    │ subscriptions, RGs             │
    ▼                                ▼
┌──────────────────────────────────────┐
│           GraphBuilder               │
│     (NetworkX DiGraph in memory)     │
│                                      │
│  Nodes: principals, roles, resources │
│  Edges: assigned, scoped_to, contains│
└──────────────┬───────────────────────┘
               │
     ┌─────────┴──────────┐
     ▼                     ▼
graph.json            SecurityAnalyzer
(blob storage)             │
                           ▼
                     findings.json
                     (blob storage)
                           │
                           ▼
                    AIAdvisor (optional)
                           │
                           ▼
                    Markdown report
                    (stdout / API)
```

### Sensitive Data in the Graph

| Node Type | Sensitive Fields | Risk if Exposed |
|---|---|---|
| `principal` (User) | `display_name`, `user_principal_name` | Identity enumeration |
| `principal` (ServicePrincipal) | `display_name`, `id` | Credential target |
| `role` (CustomRole) | `permissions` (actions, data_actions) | Permission mapping |
| `resource` (subscription) | `id`, `display_name` | Scope of access |
| Edge `assigned` | Links principal → role | Who has what |
| Edge `scoped_to` | Links role → resource | Where they have it |

> **Classification**: The graph is **Confidential**. Access must be restricted to security team members.

---

## Review Area 5: Dashboard API Security

### Endpoints and Risk Assessment

| Endpoint | Method | Auth Required | Risk | Notes |
|---|---|---|---|---|
| `/` | GET | Yes (Easy Auth) | LOW | Serves static HTML |
| `/api/graph` | GET | Yes (Easy Auth) | HIGH | Full RBAC graph disclosure |
| `/api/graph/node/<id>` | GET | Yes (Easy Auth) | MEDIUM | Single node + neighbours |
| `/api/findings` | GET | Yes (Easy Auth) | HIGH | Security vulnerabilities |
| `/api/findings/summary` | GET | Yes (Easy Auth) | LOW | Aggregate counts only |
| `/api/graph/reload` | POST | Yes + Token | MEDIUM | Cache flush (DoS vector) |
| `/api/health` | GET | No | LOW | Returns `{"status": "healthy"}` |

### Security Headers Applied

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), camera=(), microphone=()
Content-Security-Policy: default-src 'self'; script-src 'self' https://d3js.org; ...
Server: (removed)
```

### CORS Policy

When `CORS_ORIGINS` environment variable is set, only listed origins are allowed. When unset, no CORS headers are added (same-origin only).

---

## Review Area 6: AI Advisor Security

### Data Sent to AI Foundry

```json
{
  "findings": [
    {
      "id": "RBAC-001",
      "severity": "HIGH",
      "title": "Privileged role at subscription scope",
      "affected_nodes": ["<principal-id>", "<role-id>"],
      "remediation": "..."
    }
  ],
  "graph_summary": {
    "total_nodes": 150,
    "total_edges": 300,
    "subscriptions": ["Sub A", "Sub B"]
  }
}
```

### Risks

| Risk | Mitigation |
|---|---|
| Prompt injection via node labels | Node labels come from Azure AD (trusted source), not user input |
| LLM hallucination in remediation advice | Output is advisory only, never auto-applied; temperature = 0.3 |
| Data exfiltration to third-party model | Azure AI Foundry runs within the Azure boundary |
| Excessive token cost | `max_tokens=4096` cap per request |

---

## Review Area 7: Terraform State and IaC

### State Security

| Setting | Current | Recommended |
|---|---|---|
| Backend | Local (default) | Azure Storage with encryption |
| State encryption | N/A (local) | Azure SSE + HTTPS only |
| State access control | File system | Storage Account RBAC |
| Lock mechanism | None (local) | Azure Blob lease |
| Sensitive outputs | `acr_login_server`, `keyvault_uri` | Mark as `sensitive = true` where appropriate |

### Variable Validation

All variables in `variables.tf` have:
- Type constraints (`string`, `number`, `map`)
- Default values for non-sensitive fields
- Validation rules for enum-style values (`environment`, `storage_replication`, `acr_sku`)
- `sensitive = true` on `ai_foundry_key`

---

## Summary of Changes Made

### New Files Created

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage, non-root, production-hardened container build |
| `.dockerignore` | Prevents secrets, state, and dev files from entering the image |
| `SECURITY.md` | Threat model, STRIDE analysis, checklist, incident response |
| `azure-pipelines.yml` | Azure DevOps CI/CD pipeline (test, build, scan, deploy) |
| `docs/azure-devops-setup.md` | Azure DevOps setup guide with WIF service connections |
| `docs/security-review.md` | This document — structured security review guide |

### Files Modified

| File | Change | Security Impact |
|---|---|---|
| `pyproject.toml` | Added `gunicorn` dependency | Use production WSGI server |
| `terraform/acr.tf` | Parameterised SKU (default Premium), quarantine policy | Image integrity |
| `terraform/storage.tf` | `shared_access_key_enabled = false`, `https_traffic_only_enabled = true` | Prevent shared-key bypass |
| `terraform/keyvault.tf` | Added network ACLs (default deny + Azure bypass) | Restrict network access |
| `terraform/container-apps.tf` | Added liveness/readiness probes | Health monitoring, fast failure detection |
| `terraform/variables.tf` | Added `acr_sku` variable with validation | Configurable ACR tier |
| `src/azure_rbac/dashboard/app.py` | Restricted CORS, security headers, token-guarded reload, removed debug env var, localhost-only dev server | Web hardening |

### Remaining Action Items

| Priority | Action | Owner |
|---|---|---|
| **CRITICAL** | Configure Azure AD Easy Auth on the Container App | DevOps |
| **HIGH** | Deploy Container App Environment into a VNet | DevOps |
| **HIGH** | Add private endpoints for Key Vault, Storage, ACR | DevOps |
| **MEDIUM** | Enable Key Vault diagnostic logging to Log Analytics | DevOps |
| **LOW** | Add Azure Front Door / API Management as WAF | Architecture |
| **LOW** | Enable ACR geo-replication for DR | DevOps |
