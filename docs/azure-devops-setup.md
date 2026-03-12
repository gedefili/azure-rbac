# Azure DevOps CI/CD Setup Guide

This document walks through configuring the Azure DevOps pipeline for the Azure RBAC Permission Graph Tool.

---

## Table of Contents

1. [Authentication Strategy](#authentication-strategy)
2. [Prerequisites](#prerequisites)
3. [Step 1 – Create the Azure DevOps Project](#step-1--create-the-azure-devops-project)
4. [Step 2 – Configure Service Connections](#step-2--configure-service-connections)
5. [Step 3 – Create Variable Groups](#step-3--create-variable-groups)
6. [Step 4 – Create Environments with Approval Gates](#step-4--create-environments-with-approval-gates)
7. [Step 5 – Import the Pipeline](#step-5--import-the-pipeline)
8. [Step 6 – Terraform State Backend](#step-6--terraform-state-backend)
9. [Step 7 – First Run](#step-7--first-run)
10. [Pipeline Architecture](#pipeline-architecture)
11. [Branch Strategy](#branch-strategy)
12. [Troubleshooting](#troubleshooting)

---

## Authentication Strategy

### Recommended: Workload Identity Federation (OIDC)

The pipeline uses **Workload Identity Federation** via Azure DevOps service connections. This is the recommended enterprise approach because:

| Benefit | Detail |
|---|---|
| **No client secrets** | Uses OIDC tokens — nothing to rotate or leak |
| **Short-lived tokens** | Pipeline obtains a token per run, valid for minutes |
| **Auditable** | Every token issuance is logged in Azure AD sign-in logs |
| **No stored credentials** | Service connection has no password field |
| **Works with Conditional Access** | Compatible with Azure AD policies |

### Fallback: App Registration (Client Secret)

If your organisation requires an App Registration with a client secret:

1. Create an App Registration in Azure AD.
2. Generate a client secret (set expiry ≤ 6 months per corporate policy).
3. In Azure DevOps → Service connections → **New** → **Azure Resource Manager** → **Service principal (manual)**.
4. Enter the client ID, client secret, and tenant ID.
5. Name it identically to the WIF connection (e.g., `AzureRbac-Prd`).

> **Security note**: Client secrets must be rotated before expiry. The WIF approach eliminates this operational burden entirely.

### Why Not Managed Identity?

Azure DevOps hosted agents run on Microsoft-managed VMs and cannot use your tenant's managed identities directly. WIF provides equivalent security without requiring self-hosted agents.

---

## Prerequisites

| # | Requirement | Details |
|---|---|---|
| 1 | Azure DevOps organisation | With a project for this tool |
| 2 | Azure subscription | Owner or Contributor + User Access Admin |
| 3 | Terraform state storage | See [container-apps-plan.md](container-apps-plan.md#step-1--prepare-the-terraform-backend) |
| 4 | Azure AD permissions | Create App Registrations / manage service connections |
| 5 | Azure DevOps extensions | `Terraform` extension from HashiCorp (for `TerraformInstaller@1` task) |

### Install Required Extensions

In Azure DevOps → Organisation settings → Extensions → Browse marketplace:

- **Terraform** by HashiCorp
  - Provides the `TerraformInstaller@1` task
  - [Marketplace link](https://marketplace.visualstudio.com/items?itemName=HashiCorp.Terraform)

---

## Step 1 – Create the Azure DevOps Project

```
Azure DevOps → New project
  Name:        azure-rbac
  Visibility:  Private
  Version control: Git
  Work item:   Agile (or your org standard)
```

Push the existing repository:

```bash
# Add Azure DevOps as a remote
git remote add azdo https://dev.azure.com/<org>/azure-rbac/_git/azure-rbac

# Push all branches and tags
git push azdo --all
git push azdo --tags
```

---

## Step 2 – Configure Service Connections

Create one service connection per environment. In Azure DevOps:

```
Project settings → Service connections → New service connection
  → Azure Resource Manager
  → Workload Identity federation (automatic)      ← recommended
```

| Service Connection Name | Target Subscription | Target Resource Group |
|---|---|---|
| `AzureRbac-Dev` | Dev subscription | `rg-rbac-dev` |
| `AzureRbac-Stg` | Staging subscription | `rg-rbac-stg` |
| `AzureRbac-Prd` | Production subscription | `rg-rbac-prd` |

### Required Azure RBAC Roles for the Service Principal

Grant these roles to the service principal created by each service connection:

| Role | Scope | Purpose |
|---|---|---|
| `Contributor` | Resource Group `rg-rbac-{env}` | Create/update Azure resources |
| `AcrPush` | Container Registry `acrrbac{env}{suffix}` | Push container images |
| `User Access Administrator` | Resource Group `rg-rbac-{env}` | Terraform creates RBAC role assignments |

```bash
# Example: grant roles for the production service principal
SP_ID="<service-principal-object-id>"  # from the service connection

az role assignment create \
  --assignee "$SP_ID" \
  --role "Contributor" \
  --scope "/subscriptions/<sub-id>/resourceGroups/rg-rbac-prd"

az role assignment create \
  --assignee "$SP_ID" \
  --role "AcrPush" \
  --scope "/subscriptions/<sub-id>/resourceGroups/rg-rbac-prd/providers/Microsoft.ContainerRegistry/registries/acrrbacprd001"

az role assignment create \
  --assignee "$SP_ID" \
  --role "User Access Administrator" \
  --scope "/subscriptions/<sub-id>/resourceGroups/rg-rbac-prd"
```

> **Least privilege**: Scope roles to the resource group, not the subscription.

---

## Step 3 – Create Variable Groups

Create a variable group per environment in **Pipelines → Library → Variable groups**.

### Variable Group: `azure-rbac-dev`

| Variable | Value | Secret? |
|---|---|---|
| `subscriptionId` | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` | No |
| `acrName` | `acrrbacdev001` | No |
| `resourceGroup` | `rg-rbac-dev` | No |
| `dashboardApp` | `rbac-dashboard` | No |
| `graphBuilderJob` | `rbac-graph-builder` | No |
| `serviceConnection` | `AzureRbac-Dev` | No |
| `tfBackendStorageAccount` | `sttfstatedev001` | No |
| `tfBackendContainer` | `tfstate` | No |
| `tfBackendKey` | `azure-rbac-dev.tfstate` | No |
| `environment` | `dev` | No |
| `nameSuffix` | `001` | No |
| `aiFoundryEndpoint` | `https://hub-rbac-dev.openai.azure.com/` | No |
| `aiFoundryKey` | `<key>` | **Yes** |

Repeat for `azure-rbac-stg` and `azure-rbac-prd` with environment-specific values.

> **Secrets**: Mark `aiFoundryKey` as a secret variable. It is masked in logs and cannot be read back from the UI.

### Link to Key Vault (Optional – Recommended for Production)

Instead of storing secrets in variable groups, link the variable group to Azure Key Vault:

```
Variable groups → azure-rbac-prd → Link secrets from an Azure key vault
  → Service connection: AzureRbac-Prd
  → Key vault: kv-rbac-prd001
  → Authorize
  → Select secrets: AiFoundryKey, AiFoundryEndpoint
```

This pulls secrets directly from Key Vault at pipeline run time.

---

## Step 4 – Create Environments with Approval Gates

Environments control deployment approvals and track deployment history.

```
Pipelines → Environments → New environment
```

| Environment | Approvals | Checks |
|---|---|---|
| `azure-rbac-dev` | None (auto-deploy) | — |
| `azure-rbac-stg` | 1 approver (tech lead) | Branch: `main` or `release/*` |
| `azure-rbac-prd` | 2 approvers (tech lead + security) | Branch: `main` or `release/*` only |

### Configure Approval Gates (Production)

```
Environments → azure-rbac-prd → Approvals and checks
  → Approvals → Add
    → Approvers: <security-team-group>, <tech-lead>
    → Minimum approvals: 2
    → Allow approvers to approve their own runs: No

  → Branch control → Add
    → Allowed branches: refs/heads/main, refs/heads/release/*

  → Business hours → Add (optional)
    → Time zone: <your-tz>
    → Days: Monday–Thursday
    → Hours: 09:00–16:00
```

---

## Step 5 – Import the Pipeline

```
Pipelines → New pipeline → Azure Repos Git → azure-rbac
  → Select existing Azure Pipelines YAML file
  → Path: /azure-pipelines.yml
  → Run
```

The pipeline will appear in the Pipelines list. Rename it if desired:
```
Pipelines → ⋯ → Rename → "Azure RBAC – Build & Deploy"
```

---

## Step 6 – Terraform State Backend

The pipeline expects a remote Terraform backend. Create it once per environment:

```bash
# One-time setup (adjust names per environment)
az group create --name rg-terraform-state --location eastus

az storage account create \
  --name sttfstatedev001 \
  --resource-group rg-terraform-state \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --https-only true

az storage container create \
  --name tfstate \
  --account-name sttfstatedev001 \
  --auth-mode login

# Grant the pipeline service principal access
az role assignment create \
  --assignee "<pipeline-sp-object-id>" \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/<sub-id>/resourceGroups/rg-terraform-state/providers/Microsoft.Storage/storageAccounts/sttfstatedev001"
```

Then uncomment the `backend "azurerm"` block in `terraform/main.tf` — the pipeline passes the backend config values via `-backend-config` flags.

---

## Step 7 – First Run

### Initial Infrastructure Deployment

Run the pipeline with parameters:
- **environment**: `dev`
- **deployInfra**: `true` (checked)
- **forceImageBuild**: `true` (checked)

This will:
1. Run tests and lint
2. Build and push the container image to ACR
3. Run Trivy vulnerability scan
4. Run `terraform plan` and `terraform apply`
5. Deploy the image to the dashboard Container App and graph builder job
6. Verify the health check endpoint

### Subsequent Runs

For code-only changes (no infrastructure modifications):
- **deployInfra**: `false` (unchecked)

The pipeline automatically builds images on `main` and `release/*` pushes and deploys them.

---

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Azure DevOps Pipeline                        │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Stage 1: Build & Test                                      │    │
│  │  ┌─────────────────────┐  ┌──────────────────────────────┐  │    │
│  │  │  Job: TestAndLint   │  │  Job: BuildImage             │  │    │
│  │  │  • pip install      │→ │  • az acr login              │  │    │
│  │  │  • ruff check       │  │  • docker build (multi-stage)│  │    │
│  │  │  • mypy check       │  │  • docker push (SHA + latest)│  │    │
│  │  │  • pytest           │  │  • trivy scan (CRITICAL/HIGH)│  │    │
│  │  └─────────────────────┘  └──────────────────────────────┘  │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │  Stage 2: Infrastructure (optional)                          │    │
│  │  ┌──────────────────────────────────────────────────────┐   │    │
│  │  │  Deployment: TerraformApply                          │   │    │
│  │  │  • terraform init (remote backend)                   │   │    │
│  │  │  • terraform plan  → tfplan                          │   │    │
│  │  │  • terraform apply → create/update Azure resources   │   │    │
│  │  │  • Environment gate: approvals for stg/prd           │   │    │
│  │  └──────────────────────────────────────────────────────┘   │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │  Stage 3: Deploy                                             │    │
│  │  ┌──────────────────────────────────────────────────────┐   │    │
│  │  │  Deployment: DeployContainerApps                     │   │    │
│  │  │  • az containerapp update (dashboard)                │   │    │
│  │  │  • az containerapp job update (graph builder)        │   │    │
│  │  │  • Health check verification (10 retries)            │   │    │
│  │  │  • Environment gate: approvals for stg/prd           │   │    │
│  │  └──────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Image Tagging Strategy

Every build produces three tags:

| Tag | Example | Purpose |
|---|---|---|
| **Git SHA** | `acrrbacprd001.azurecr.io/azure-rbac:a1b2c3d` | Immutable, traceable to commit |
| **Build ID** | `acrrbacprd001.azurecr.io/azure-rbac:build-1234` | Traceable to pipeline run |
| **Latest** | `acrrbacprd001.azurecr.io/azure-rbac:latest` | Convenience for dev |

Container Apps are always updated with the **Git SHA** tag for full traceability.

---

## Branch Strategy

```
main ─────────────────────────────────────────────────────
  │           │                   │
  │  feature/RBAC-42        release/1.0
  │     │                        │
  │     └── PR → main            └── deploy to prd (gated)
  │           │
  │           ▼
  │     auto-deploy to dev
  │
```

| Branch | Triggers | Deploys To |
|---|---|---|
| `main` | Push (auto) | Dev (auto), Stg (approval), Prd (approval) |
| `release/*` | Push (auto) | Dev (auto), Stg (approval), Prd (approval) |
| `feature/*` | PR only | Tests run, no deployment |

---

## Troubleshooting

### "Terraform init failed – backend storage access denied"

The pipeline service principal needs `Storage Blob Data Contributor` on the Terraform state storage account. See [Step 6](#step-6--terraform-state-backend).

### "az containerapp update failed – image not found"

1. Verify the image was pushed: `az acr repository show-tags --name <acr> --repository azure-rbac`
2. Ensure the service connection has `AcrPush` on the registry.
3. Check that the managed identity on the Container App has `AcrPull`.

### "Trivy scan failed with exit code 1"

Trivy found CRITICAL or HIGH vulnerabilities in the image. Review the scan output, update base images or dependencies, and rebuild.

### "Health check failed after 10 attempts"

1. Check container app logs: `az containerapp logs show --name rbac-dashboard --resource-group <rg>`
2. Verify environment variables (Key Vault URI, storage account name).
3. Ensure the managed identity has the required RBAC roles.

### "Terraform apply failed – role assignment already exists"

This is common when roles were created manually before Terraform. Import the existing assignment:
```bash
terraform import azurerm_role_assignment.kv_secrets_user "<role-assignment-id>"
```

### "addSpnToEnvironment: Federated token error"

Ensure the service connection uses **Workload Identity federation**. If using an App Registration, set `addSpnToEnvironment: true` and replace `ARM_OIDC_TOKEN` / `ARM_USE_OIDC` with:
```bashazure-rbac dashboard --graph fauxterprise/graph.json
export ARM_CLIENT_SECRET="$servicePrincipalKey"
```
