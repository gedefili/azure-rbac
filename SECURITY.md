# Security Model and Threat Analysis

This document describes the security architecture, threat model, and hardening measures for the Azure RBAC Permission Graph Tool.

---

## Table of Contents

1. [Trust Boundaries](#trust-boundaries)
2. [Threat Model (STRIDE)](#threat-model-stride)
3. [Authentication and Authorisation](#authentication-and-authorisation)
4. [Secrets Management](#secrets-management)
5. [Network Security](#network-security)
6. [Container Image Security](#container-image-security)
7. [Data Classification](#data-classification)
8. [Security Checklist](#security-checklist)
9. [Incident Response](#incident-response)
10. [Responsible AI](#responsible-ai)

---

## Trust Boundaries

```
                                ┌──────────────────────────────────────────────────┐
                                │              Azure Subscription                  │
   Internet                     │                                                  │
   (untrusted)                  │  ┌────────────────────────────────────────────┐  │
        │                       │  │      Container App Environment (VNet)      │  │
        │   TLS 1.2+            │  │                                            │  │
        ├───────────────────────┤  │  ┌──────────────┐  ┌───────────────────┐   │  │
        │   Trust boundary 1    │  │  │   Dashboard   │  │  Graph Builder    │   │  │
        │   (ingress)           │  │  │  (Flask API)  │  │  (Cron Job)       │   │  │
        │                       │  │  └──────┬───────┘  └────────┬──────────┘   │  │
        │                       │  │         │ MSI                │ MSI          │  │
        │                       │  └─────────┼────────────────────┼─────────────┘  │
        │                       │            │ Trust boundary 2   │                │
        │                       │  ┌─────────▼────────┐ ┌────────▼───────────┐    │
        │                       │  │   Key Vault      │ │ Storage Account    │    │
        │                       │  │   (secrets)      │ │ (graph data)       │    │
        │                       │  └──────────────────┘ └────────────────────┘    │
        │                       │                                                  │
        │                       │  ┌──────────────────┐  ┌───────────────────┐    │
        │                       │  │   ACR (images)   │  │  Log Analytics    │    │
        │                       │  └──────────────────┘  └───────────────────┘    │
        │                       └──────────────────────────────────────────────────┘
        │                                    │
        │                       Trust boundary 3 (external service)
        │                                    │
        │                       ┌────────────▼───────────────┐
        │                       │ Azure ARM / Graph API      │
        │                       │ Azure AI Foundry (GPT-4o)  │
        │                       └────────────────────────────┘
```

**Trust boundary 1 – Internet → Dashboard**: Ingress traffic from the internet reaches the dashboard via TLS-terminated Container Apps ingress. Authentication should be enforced here (Azure AD Easy Auth or an API gateway).

**Trust boundary 2 – Workload → Azure Services**: Both the dashboard and graph builder authenticate to Key Vault, Storage, ACR, and Azure APIs via a user-assigned managed identity. Secrets are never stored in environment variables in production.

**Trust boundary 3 – Azure APIs / AI Foundry**: The graph builder calls Azure ARM and Graph APIs with Reader permissions. The AI advisor sends RBAC finding data (potentially sensitive permission structures) to Azure AI Foundry.

---

## Threat Model (STRIDE)

### Spoofing (Identity)

| Threat | Mitigation | Status |
|---|---|---|
| Attacker impersonates the dashboard to users | TLS certificate on Container Apps ingress (auto-managed) | ✅ Implemented |
| Attacker uses stolen API keys to call AI Foundry | API key stored in Key Vault, accessed via MSI only | ✅ Implemented |
| Unauthenticated access to dashboard | **Requires** Azure AD Easy Auth or API Management in front | ⚠️ Action needed |
| Managed identity spoofing | User-assigned MI bound to specific Container Apps only | ✅ Implemented |

### Tampering

| Threat | Mitigation | Status |
|---|---|---|
| Modified container images | ACR Premium with content trust / quarantine policy | ✅ Implemented |
| Graph data tampered in storage | Storage RBAC (no shared key), immutable snapshots via lifecycle policy | ✅ Implemented |
| Terraform state tampering | Remote backend with encryption and access control | ⚠️ Backend config commented out |

### Repudiation

| Threat | Mitigation | Status |
|---|---|---|
| Untracked changes to RBAC assignments | Graph builder runs nightly, snapshots are versioned by timestamp | ✅ Implemented |
| No audit trail for dashboard access | Log Analytics captures container logs | ✅ Implemented |
| No audit trail for Key Vault access | Key Vault diagnostic logs (add to Log Analytics) | ⚠️ Enhancement |

### Information Disclosure

| Threat | Mitigation | Status |
|---|---|---|
| RBAC graph data exposed to unauthorised users | Dashboard requires authentication (see Spoofing) | ⚠️ Action needed |
| Graph data contains permission mappings for the entire tenant | Storage account: public access disabled, shared key disabled, TLS 1.2+ | ✅ Implemented |
| AI Foundry receives sensitive RBAC structure | Data sent to Azure-hosted model (not third-party); stays within tenant boundary | ✅ Acceptable |
| Container image leaks source code or secrets | `.dockerignore` excludes `.env`, Terraform state, tests, docs | ✅ Implemented |
| Server fingerprinting | `Server` header removed from responses | ✅ Implemented |

### Denial of Service

| Threat | Mitigation | Status |
|---|---|---|
| Dashboard overloaded with requests | Container Apps auto-scaling (1–5 replicas) | ✅ Implemented |
| Cache flush abuse (`/api/graph/reload`) | Token-protected reload endpoint (`RELOAD_TOKEN` env var) | ✅ Implemented |
| Large graph exhausts memory | Max replicas limit, memory/CPU quotas on containers | ✅ Implemented |

### Elevation of Privilege

| Threat | Mitigation | Status |
|---|---|---|
| Managed identity over-privileged | MI has Reader (not Contributor), scoped to specific resources | ✅ Implemented |
| Container escapes to host | Runs as non-root (`USER appuser`), Container Apps sandboxed | ✅ Implemented |
| Dashboard API allows arbitrary actions | Read-only API; `reload` is token-gated | ✅ Implemented |
| AI advisor prompt injection | System prompt is hardcoded; user content is serialised JSON, not free-text | ✅ Mitigated |

---

## Authentication and Authorisation

### Managed Identity Permissions

| Role | Scope | Purpose |
|---|---|---|
| `AcrPull` | Container Registry | Pull container images |
| `Key Vault Secrets User` | Key Vault | Read AI Foundry credentials |
| `Storage Blob Data Contributor` | Storage Account | Read/write graph snapshots |
| `Reader` | Subscription | Enumerate role assignments and resources |

**Principle of least privilege**: The MI has **no write permissions** on Azure RBAC. It can only *read* assignments, not modify them.

### Dashboard Authentication

The dashboard Flask app does **not** implement its own authentication. In production, authentication must be provided by one of:

| Method | Recommended For | How |
|---|---|---|
| **Azure AD Easy Auth** | Container Apps | Enable via `az containerapp auth update` |
| **API Management** | Enterprise | Deploy APIM in front with Azure AD OAuth |
| **Reverse proxy** | Self-hosted | Nginx/Caddy with OIDC middleware |

> **Action required**: Configure one of the above before exposing the dashboard to the internet.

---

## Secrets Management

| Secret | Storage | Access |
|---|---|---|
| AI Foundry API key | Key Vault (`AiFoundryKey`) | MSI → Key Vault Secrets User |
| AI Foundry endpoint | Key Vault (`AiFoundryEndpoint`) | MSI → Key Vault Secrets User |
| Azure AD client secret | Key Vault (if using SP auth) | MSI → Key Vault Secrets User |
| Storage connection details | Constructed from account name + MSI | No secret needed |
| Terraform state encryption | Azure Storage (remote backend) | Deployer RBAC |

**Key Vault hardening applied**:
- RBAC-based access (no legacy access policies)
- Purge protection enabled
- Soft-delete retention: 90 days
- Network ACLs: default deny, bypass for Azure services

---

## Network Security

### Current State

| Component | Network Access |
|---|---|
| Dashboard Container App | External ingress (internet-routable via TLS) |
| Graph Builder Job | Outbound-only (no ingress) |
| Key Vault | Default deny + Azure service bypass |
| Storage Account | Public endpoint (RBAC-protected, no shared key) |
| ACR | Public endpoint (RBAC-protected, no admin) |
| Log Analytics | Azure-managed endpoint |

### Production Recommendations

For maximum isolation, deploy the Container App Environment into a custom VNet:

```hcl
resource "azurerm_container_app_environment" "rbac" {
  name                           = "cae-rbac-${var.environment}"
  location                       = azurerm_resource_group.rbac.location
  resource_group_name            = azurerm_resource_group.rbac.name
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.rbac.id
  infrastructure_subnet_id       = azurerm_subnet.container_apps.id
}
```

Add private endpoints for:
- Key Vault (`Microsoft.KeyVault/vaults`)
- Storage Account (`Microsoft.Storage/storageAccounts`, sub-resource `blob`)
- ACR (`Microsoft.ContainerRegistry/registries`)

---

## Container Image Security

### Build Pipeline

1. **Multi-stage Dockerfile** – Build dependencies isolated from runtime image.
2. **Non-root user** – Container runs as `appuser` (UID 1000).
3. **Minimal base image** – `python:3.12-slim` (Debian slim, ~150 MB).
4. **No secrets in image** – `.dockerignore` excludes `.env`, Terraform state, test data.
5. **Dependency pinning** – `pyproject.toml` specifies minimum versions.
6. **Health check** – `HEALTHCHECK` instruction for orchestrator liveness.

### Image Scanning

The Azure DevOps pipeline ([`azure-pipelines.yml`](azure-pipelines.yml)) runs a **Trivy vulnerability scan** on every image build, failing the pipeline on CRITICAL or HIGH findings.

For additional defence-in-depth, enable ACR's built-in scanning:

```bash
# ACR built-in scanning (Premium SKU)
az acr task create \
  --name scan-on-push \
  --registry acrrbacprd001 \
  --cmd "mcr.microsoft.com/acr/acr-cli:latest" \
  --context /dev/null
```

---

## Data Classification

| Data | Classification | Storage | Encryption |
|---|---|---|---|
| RBAC graph (role assignments, principals, scopes) | **Confidential** – reveals who has access to what | Blob Storage | Encrypted at rest (Azure SSE) |
| Security findings | **Confidential** – reveals security gaps | Blob Storage | Encrypted at rest |
| AI Foundry API key | **Secret** | Key Vault | Encrypted at rest (HSM-backed) |
| AI remediation reports | **Internal** – contains security advice | Returned in API response | In-transit TLS |
| Container logs | **Internal** | Log Analytics | Encrypted at rest |
| Terraform state | **Secret** – contains resource IDs and config | Remote backend | Encrypted at rest |

---

## Security Checklist

Use this checklist before any production deployment:

### Infrastructure
- [ ] Terraform remote backend configured with encryption
- [ ] ACR SKU set to Premium (content trust, private endpoints)
- [ ] Key Vault network ACLs set to default deny
- [ ] Storage account shared key access disabled
- [ ] Storage account HTTPS-only enabled
- [ ] Container App Environment deployed into a custom VNet
- [ ] Private endpoints for Key Vault, Storage, and ACR
- [ ] Log Analytics retention set appropriately (≥ 30 days)
- [ ] Key Vault diagnostic logs enabled

### Application
- [ ] Dashboard authentication configured (Azure AD Easy Auth)
- [ ] CORS origins restricted (not wildcard)
- [ ] Security headers applied (CSP, X-Frame-Options, etc.)
- [ ] Reload endpoint protected with `RELOAD_TOKEN`
- [ ] Flask debug mode disabled
- [ ] Gunicorn used as WSGI server (not Flask dev server)
- [ ] Container runs as non-root user

### CI/CD
- [ ] Azure DevOps pipeline imported from `azure-pipelines.yml`
- [ ] Service connections use Workload Identity Federation (no client secrets)
- [ ] Container image scanned for vulnerabilities (Trivy) on every build
- [ ] Image tags use Git SHA (not just `latest`)
- [ ] Terraform plan reviewed before apply (environment approval gates)
- [ ] Secrets stored in variable groups linked to Key Vault
- [ ] Environment approval gates on staging and production
- [ ] Branch protection rules on `main`

### Permissions
- [ ] Managed identity has Reader only (no write on RBAC)
- [ ] Key Vault admin role removed after initial setup
- [ ] `Directory.Read.All` Graph API permission granted (for principal names)
- [ ] Storage Blob Data Contributor scoped to the RBAC storage account only

---

## Incident Response

### Compromised Managed Identity

1. Revoke role assignments immediately:
   ```bash
   az role assignment delete --assignee <principal-id> --all
   ```
2. Rotate Key Vault secrets (AI Foundry key).
3. Check Storage Account access logs for exfiltration.
4. Review ACR audit logs for unauthorized image pushes.
5. Redeploy with a new managed identity.

### Compromised Container Image

1. Quarantine the image in ACR:
   ```bash
   az acr repository update --name <acr> --image azure-rbac:<tag> --write-enabled false
   ```
2. Roll back to the last known-good image tag.
3. Investigate the CI/CD pipeline for supply chain attack vectors.
4. Scan all image layers with Trivy or Defender for Containers.

### Data Breach (Graph Data Exposed)

1. Assess which graph snapshots were accessed (Storage Account logs).
2. Notify affected teams – the graph reveals who has privileged access.
3. Trigger an out-of-band RBAC review for all principals in the graph.
4. Consider revoking and re-issuing role assignments if tampering is suspected.

---

## Responsible AI

The AI Advisor component sends RBAC findings to Azure AI Foundry. Key safeguards:

- **Data stays in Azure**: AI Foundry models run within the Azure boundary.
- **System prompt is hardcoded**: Cannot be overridden by user input.
- **No PII in prompts**: Findings contain principal IDs and role names, not personal data.
- **Output is advisory only**: AI recommendations are never applied automatically.
- **Temperature = 0.3**: Low creativity reduces hallucination risk.
- **Token limit = 4096**: Prevents runaway cost on a single request.

See [ai-models.md](ai-models.md) for model selection criteria and cost estimates.
