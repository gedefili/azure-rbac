# Azure Container Apps – Detailed Deployment Plan

This document provides a comprehensive, step-by-step plan for deploying the Azure RBAC Permission Graph tool on **Azure Container Apps** using the included **Terraform templates**.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Resource Inventory](#resource-inventory)
4. [Step 1 – Prepare the Terraform Backend](#step-1--prepare-the-terraform-backend)
5. [Step 2 – Configure Variables](#step-2--configure-variables)
6. [Step 3 – Deploy Infrastructure with Terraform](#step-3--deploy-infrastructure-with-terraform)
7. [Step 4 – Build and Push the Container Image](#step-4--build-and-push-the-container-image)
8. [Step 5 – Verify the Deployment](#step-5--verify-the-deployment)
9. [Step 6 – Configure AI Foundry (Optional)](#step-6--configure-ai-foundry-optional)
10. [Step 7 – Set Up CI/CD](#step-7--set-up-cicd)
11. [Networking and Security](#networking-and-security)
12. [Monitoring and Observability](#monitoring-and-observability)
13. [Cost Management](#cost-management)
14. [Scaling and Performance](#scaling-and-performance)
15. [Disaster Recovery](#disaster-recovery)
16. [Day-2 Operations Runbook](#day-2-operations-runbook)
17. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                      Azure Subscription                     │
                    │                                                             │
                    │  ┌─────────────────────────────────────────────────────┐    │
                    │  │              Resource Group: rg-rbac-prd            │    │
                    │  │                                                     │    │
  Internet          │  │  ┌───────────────────────────────────────────────┐  │    │
     │              │  │  │    Container App Environment: cae-rbac-prd    │  │    │
     │   HTTPS      │  │  │                                               │  │    │
     ├──────────────┤  │  │  ┌─────────────────┐  ┌───────────────────┐  │  │    │
     │              │  │  │  │  rbac-dashboard  │  │ rbac-graph-builder│  │  │    │
     │              │  │  │  │  (Container App) │  │ (Container App    │  │  │    │
     │              │  │  │  │                  │  │  Job – cron)      │  │  │    │
     │              │  │  │  │  Flask :5000     │  │  "0 2 * * *"     │  │  │    │
     │              │  │  │  │  1–5 replicas    │  │  1 CPU / 2 Gi    │  │  │    │
     │              │  │  │  └───────┬──────────┘  └────────┬──────────┘  │  │    │
     │              │  │  │          │ User-Assigned         │             │  │    │
     │              │  │  │          │ Managed Identity      │             │  │    │
     │              │  │  └──────────┼──────────────────────┼─────────────┘  │    │
     │              │  │             │                       │                │    │
     │              │  │     ┌───────▼───────┐  ┌───────────▼──────────┐     │    │
     │              │  │     │   Key Vault   │  │  Storage Account     │     │    │
     │              │  │     │ (secrets)     │  │  graph-snapshots/    │     │    │
     │              │  │     └───────────────┘  └──────────────────────┘     │    │
     │              │  │                                                     │    │
     │              │  │     ┌───────────────┐  ┌──────────────────────┐     │    │
     │              │  │     │      ACR      │  │  Log Analytics       │     │    │
     │              │  │     │ (images)      │  │  (logs & metrics)    │     │    │
     │              │  │     └───────────────┘  └──────────────────────┘     │    │
     │              │  └─────────────────────────────────────────────────────┘    │
     │              └─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Type | Purpose |
|---|---|---|
| **rbac-dashboard** | Container App (web) | Serves the Flask dashboard UI + REST API on port 5000 |
| **rbac-graph-builder** | Container App Job (cron) | Runs `azure-rbac build` nightly at 02:00 UTC to refresh the permission graph |
| **Key Vault** | Azure Key Vault | Stores AI Foundry credentials, tenant ID, and any other secrets |
| **Storage Account** | Blob Storage | Persists `graph.json` and `findings.json` snapshots in `graph-snapshots/` |
| **ACR** | Container Registry | Hosts the Docker image used by both the dashboard and the builder |
| **Log Analytics** | Monitoring | Collects container logs, metrics, and enables alerting |
| **Managed Identity** | User-Assigned MI | Authenticates both workloads to Key Vault, Storage, ACR, and Azure RBAC APIs |

### Data Flow

```
1. Graph Builder Job (02:00 UTC daily)
   ├── Authenticates via Managed Identity
   ├── Reads Key Vault secrets (tenant config, AI Foundry creds)
   ├── Calls Azure ARM + Graph APIs to discover role assignments
   ├── Builds NetworkX permission graph
   ├── Runs SecurityAnalyzer to produce findings
   ├── (Optional) Calls AI Foundry for remediation advice
   └── Uploads graph.json + findings.json to Blob Storage

2. Dashboard (always running)
   ├── Authenticates via Managed Identity
   ├── Reads latest graph.json + findings.json from Blob Storage
   ├── Serves interactive D3.js visualization on port 5000
   └── Exposes REST API: /api/graph, /api/findings, /api/health
```

---

## Prerequisites

| # | Requirement | Details |
|---|---|---|
| 1 | **Azure subscription** | Owner or Contributor role on the target subscription |
| 2 | **Azure CLI** | Version 2.60+ (`az --version`) |
| 3 | **Terraform** | Version 1.5+ (`terraform --version`) |
| 4 | **Docker** | For building the container image locally |
| 5 | **Azure AD permissions** | The deployer needs `Microsoft.Authorization/roleAssignments/write` to create RBAC assignments |
| 6 | **Service principal / MSI** | The tool's managed identity needs `Reader` on all subscriptions to scan and `Directory.Read.All` on Microsoft Graph |
| 7 | **(Optional) AI Foundry** | An Azure AI Foundry project with a deployed GPT-4o model. See [ai-foundry-setup.md](ai-foundry-setup.md) |

### Required CLI extensions

```bash
az extension add --name containerapp
az extension add --name log-analytics
```

---

## Resource Inventory

The Terraform templates in [`terraform/`](../terraform/) create the following resources:

| Resource | Terraform File | Naming Convention |
|---|---|---|
| Resource Group | `main.tf` | `rg-rbac-{env}` |
| Log Analytics Workspace | `log-analytics.tf` | `log-rbac-{env}` |
| Azure Container Registry | `acr.tf` | `acrrbac{env}{suffix}` |
| Storage Account | `storage.tf` | `strbac{env}{suffix}` |
| Blob Container | `storage.tf` | `graph-snapshots` |
| Lifecycle Policy | `storage.tf` | auto-delete after 90 days |
| Key Vault | `keyvault.tf` | `kv-rbac-{env}{suffix}` |
| User-Assigned Managed Identity | `identity.tf` | `id-rbac-{env}` |
| Container App Environment | `container-apps.tf` | `cae-rbac-{env}` |
| Dashboard Container App | `container-apps.tf` | `rbac-dashboard` |
| Graph Builder Job | `container-apps.tf` | `rbac-graph-builder` |
| RBAC Role Assignments (5) | `identity.tf`, `acr.tf`, `keyvault.tf` | Various |

---

## Step 1 – Prepare the Terraform Backend

For team use, store Terraform state in a remote backend. Create a dedicated storage account:

```bash
# Create a resource group for Terraform state (one-time setup)
az group create --name rg-terraform-state --location eastus

# Create storage account for state files
az storage account create \
  --name sttfstate<your-suffix> \
  --resource-group rg-terraform-state \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2

# Create container for state files
az storage container create \
  --name tfstate \
  --account-name sttfstate<your-suffix> \
  --auth-mode login
```

Then uncomment the `backend "azurerm"` block in `terraform/main.tf` and fill in the values.

> **For individual use**: Skip this step. Terraform will use a local state file by default.

---

## Step 2 – Configure Variables

```bash
cd terraform/
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

```hcl
# Required
subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
environment     = "prd"          # dev, stg, or prd
location        = "eastus"
name_suffix     = "001"          # ensures globally unique names

# Optional – AI Foundry
ai_foundry_endpoint   = "https://hub-rbac-prod.openai.azure.com/"
ai_foundry_key        = "<your-key>"
ai_foundry_deployment = "gpt-4o"
```

### Key Variables Reference

| Variable | Default | Description |
|---|---|---|
| `subscription_id` | *(required)* | Azure subscription for all resources |
| `environment` | `prd` | Controls naming and defaults |
| `location` | `eastus` | Azure region |
| `name_suffix` | `001` | Uniqueness suffix for globally unique names |
| `dashboard_min_replicas` | `1` | Minimum replicas (set to `0` to scale to zero) |
| `dashboard_max_replicas` | `5` | Maximum replicas for auto-scaling |
| `graph_builder_cron` | `0 2 * * *` | Cron schedule for graph rebuild (UTC) |
| `storage_replication` | `GRS` | Use `LRS` for dev, `GRS` for production |
| `snapshot_retention_days` | `90` | Days before old snapshots are deleted |

---

## Step 3 – Deploy Infrastructure with Terraform

```bash
cd terraform/

# Authenticate to Azure
az login
az account set --subscription <your-subscription-id>

# Initialize Terraform (downloads providers)
terraform init

# Preview the changes
terraform plan -out=tfplan

# Apply the changes
terraform apply tfplan
```

### Expected Output

After `terraform apply`, you will see outputs like:

```
dashboard_url             = "https://rbac-dashboard.delightfulbay-xxxxxxxx.eastus.azurecontainerapps.io"
acr_login_server          = "acrrbacprd001.azurecr.io"
keyvault_uri              = "https://kv-rbac-prd001.vault.azure.net/"
managed_identity_client_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

> **Note**: The dashboard will show an error until the container image is pushed (next step).

---

## Step 4 – Build and Push the Container Image

```bash
# Navigate to the project root
cd ..

# Authenticate to ACR (use the output from terraform)
az acr login --name acrrbacprd001

# Build the Docker image
docker build -t acrrbacprd001.azurecr.io/azure-rbac:latest .

# Push to ACR
docker push acrrbacprd001.azurecr.io/azure-rbac:latest
```

### Verify the image

```bash
az acr repository show-tags --name acrrbacprd001 --repository azure-rbac
```

### Update the Container App (if image already existed)

After pushing a new image, the Container App will automatically pull the `:latest` tag on the next revision. To force an immediate update:

```bash
az containerapp update \
  --name rbac-dashboard \
  --resource-group rg-rbac-prd \
  --image acrrbacprd001.azurecr.io/azure-rbac:latest
```

---

## Step 5 – Verify the Deployment

### 5.1 Check the dashboard

Open the `dashboard_url` from the Terraform output in your browser:

```bash
# Get the URL
terraform -chdir=terraform output dashboard_url

# Quick health check
curl -s https://<dashboard-fqdn>/api/health
```

### 5.2 Trigger a manual graph build

```bash
az containerapp job start \
  --name rbac-graph-builder \
  --resource-group rg-rbac-prd
```

Monitor the job execution:

```bash
az containerapp job execution list \
  --name rbac-graph-builder \
  --resource-group rg-rbac-prd \
  --output table
```

### 5.3 Check logs

```bash
# Dashboard logs
az containerapp logs show \
  --name rbac-dashboard \
  --resource-group rg-rbac-prd \
  --follow

# Graph builder job logs
az containerapp job logs show \
  --name rbac-graph-builder \
  --resource-group rg-rbac-prd
```

### 5.4 Verify RBAC permissions

The managed identity should have:

```bash
PRINCIPAL_ID=$(terraform -chdir=terraform output -raw managed_identity_principal_id)

az role assignment list \
  --assignee "$PRINCIPAL_ID" \
  --all \
  --output table
```

Expected roles:

| Role | Scope |
|---|---|
| `AcrPull` | Container Registry |
| `Key Vault Secrets User` | Key Vault |
| `Storage Blob Data Contributor` | Storage Account |
| `Reader` | Subscription |

---

## Step 6 – Configure AI Foundry (Optional)

If you did not provide `ai_foundry_endpoint` and `ai_foundry_key` during the initial deployment:

1. Follow the [AI Foundry Setup Guide](ai-foundry-setup.md) to create a hub, project, and deploy a model.

2. Store the credentials in Key Vault:

```bash
az keyvault secret set \
  --vault-name kv-rbac-prd001 \
  --name AiFoundryEndpoint \
  --value "https://hub-rbac-prod.openai.azure.com/"

az keyvault secret set \
  --vault-name kv-rbac-prd001 \
  --name AiFoundryKey \
  --value "<your-key>"
```

3. Or update via Terraform:

```bash
# Edit terraform.tfvars
ai_foundry_endpoint = "https://hub-rbac-prod.openai.azure.com/"
ai_foundry_key      = "<your-key>"

terraform plan -out=tfplan && terraform apply tfplan
```

---

## Step 7 – Set Up CI/CD

### GitHub Actions Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Build and Deploy to Container Apps

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  ACR_NAME: acrrbacprd001
  RESOURCE_GROUP: rg-rbac-prd
  DASHBOARD_APP: rbac-dashboard
  IMAGE_NAME: azure-rbac

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest
      - run: ruff check .

  build-and-deploy:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      id-token: write    # Required for OIDC login
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login (OIDC)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Login to ACR
        run: az acr login --name ${{ env.ACR_NAME }}

      - name: Build and push image
        run: |
          IMAGE_TAG="${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }}"
          docker build -t "$IMAGE_TAG" .
          docker push "$IMAGE_TAG"

      - name: Deploy to Container Apps
        run: |
          az containerapp update \
            --name ${{ env.DASHBOARD_APP }} \
            --resource-group ${{ env.RESOURCE_GROUP }} \
            --image "${{ env.ACR_NAME }}.azurecr.io/${{ env.IMAGE_NAME }}:${{ github.sha }}"
```

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `AZURE_CLIENT_ID` | Service principal or managed identity client ID for OIDC login |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target subscription ID |

### Terraform in CI/CD

For infrastructure changes, add a separate workflow:

```yaml
name: Terraform Plan & Apply

on:
  pull_request:
    paths: ["terraform/**"]
  push:
    branches: [main]
    paths: ["terraform/**"]

jobs:
  terraform:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
      pull-requests: write
    defaults:
      run:
        working-directory: terraform
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3

      - name: Azure Login
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - run: terraform init
      - run: terraform plan -no-color
        if: github.event_name == 'pull_request'
      - run: terraform apply -auto-approve
        if: github.ref == 'refs/heads/main'
```

---

## Networking and Security

### Default Configuration (public ingress)

The default Terraform configuration deploys with public HTTPS ingress on the dashboard. This is suitable for:
- Development and staging environments
- Proof-of-concept deployments
- Teams that will add authentication at the application layer

### Production Hardening Checklist

| # | Action | How |
|---|---|---|
| 1 | **Enable Azure AD authentication** | Add [EasyAuth](https://learn.microsoft.com/en-us/azure/container-apps/authentication) to the dashboard Container App |
| 2 | **Restrict ingress to corporate IP ranges** | Configure IP restrictions on the Container App ingress |
| 3 | **Deploy into a VNet** | Create a VNet and configure `infrastructure_subnet_id` on the Container App Environment |
| 4 | **Enable private endpoints** | Add private endpoints for Key Vault, Storage, and ACR |
| 5 | **Disable public access on Key Vault** | Set `public_network_access_enabled = false` in `keyvault.tf` |
| 6 | **Enable TLS 1.3** | Configured by default on Container Apps |
| 7 | **Enable Defender for Containers** | `az security pricing create --name Containers --tier Standard` |

### VNet Integration Example

To deploy into a VNet, add the following to your Terraform configuration:

```hcl
resource "azurerm_virtual_network" "rbac" {
  name                = "vnet-rbac-${var.environment}"
  location            = azurerm_resource_group.rbac.location
  resource_group_name = azurerm_resource_group.rbac.name
  address_space       = ["10.0.0.0/16"]
}

resource "azurerm_subnet" "container_apps" {
  name                 = "snet-container-apps"
  resource_group_name  = azurerm_resource_group.rbac.name
  virtual_network_name = azurerm_virtual_network.rbac.name
  address_prefixes     = ["10.0.0.0/23"]

  delegation {
    name = "container-apps"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Then update the Container App Environment:
# infrastructure_subnet_id = azurerm_subnet.container_apps.id
```

---

## Monitoring and Observability

### Built-in Monitoring

Container Apps automatically sends logs to the Log Analytics workspace configured in the Terraform templates.

### Useful KQL Queries

**Dashboard request latency (P95)**:

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "rbac-dashboard"
| where Log_s contains "request"
| summarize percentile(todouble(extract("(\\d+)ms", 1, Log_s)), 95) by bin(TimeGenerated, 5m)
| render timechart
```

**Graph builder job failures**:

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "rbac-graph-builder"
| where Log_s contains "error" or Log_s contains "ERROR"
| project TimeGenerated, Log_s
| order by TimeGenerated desc
```

**Container restart count**:

```kql
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "rbac-dashboard"
| where Reason_s == "ContainerRestarted"
| summarize count() by bin(TimeGenerated, 1h)
```

### Alerts

Set up Azure Monitor alerts for critical scenarios:

```bash
# Alert on graph builder job failure
az monitor metrics alert create \
  --name "rbac-graph-builder-failure" \
  --resource-group rg-rbac-prd \
  --scopes "/subscriptions/<sub-id>/resourceGroups/rg-rbac-prd/providers/Microsoft.App/jobs/rbac-graph-builder" \
  --condition "count FailedExecutions > 0" \
  --action-group <action-group-id> \
  --description "Graph builder job failed"
```

---

## Cost Management

### Estimated Monthly Cost (Production)

| Resource | SKU | Estimated Cost |
|---|---|---|
| Container App Environment | Consumption | $0 (no base cost) |
| Dashboard (1 replica, 0.5 CPU / 1 Gi) | Consumption | ~$15/mo |
| Graph Builder Job (1 run/day, ~10 min) | Consumption | ~$1/mo |
| Storage Account (GRS, <1 GB) | Standard | ~$1/mo |
| Key Vault | Standard | ~$0.03/secret/mo |
| Log Analytics (< 5 GB/mo ingestion) | Free tier | $0 |
| ACR (Basic) | Basic | ~$5/mo |
| **Total** | | **~$22/mo** |

### Cost Optimization Tips

1. **Scale to zero**: Set `dashboard_min_replicas = 0` in non-production environments
2. **Use LRS storage** for dev/staging: `storage_replication = "LRS"`
3. **Reduce log retention**: `log_retention_days = 7` for development
4. **Use spot instances**: Not yet available for Container Apps, but monitor Azure updates
5. **Right-size the builder**: If scans complete quickly, reduce `graph_builder_cpu` and `graph_builder_memory`

---

## Scaling and Performance

### Horizontal Scaling

The dashboard auto-scales between `dashboard_min_replicas` and `dashboard_max_replicas` based on concurrent HTTP requests:

| Metric | Scale Rule |
|---|---|
| HTTP concurrent requests | Default: 10 concurrent requests per replica |
| CPU utilization | Add custom rule at 70% threshold |

To add a custom scaling rule, modify the dashboard template in `container-apps.tf`:

```hcl
# Inside the template block of azurerm_container_app.dashboard
http_scale_rule {
  name                = "http-scaling"
  concurrent_requests = "20"
}
```

### Performance Recommendations

| Area | Recommendation |
|---|---|
| **Cold start** | Set `dashboard_min_replicas = 1` to avoid cold starts in production |
| **Graph build time** | Large tenants (>10k assignments) may need `graph_builder_cpu = 2.0` and `graph_builder_memory = 4Gi` |
| **Dashboard memory** | Large graphs may need `dashboard_memory = 2Gi` |
| **API response time** | The dashboard caches the graph in memory; first request after restart loads from Blob Storage |

---

## Disaster Recovery

### Backup Strategy

| Component | Backup Method | RPO |
|---|---|---|
| **Graph snapshots** | GRS replication (automatic) | 0 (synchronous) |
| **Key Vault secrets** | Soft delete + purge protection (90 days) | 0 |
| **Terraform state** | Remote backend with versioning | Per commit |
| **Container image** | ACR geo-replication (Premium SKU) | Near-zero |
| **Configuration** | Git (this repository) | Per commit |

### Recovery Procedures

**Scenario: Dashboard is down**

```bash
# Check Container App status
az containerapp show --name rbac-dashboard --resource-group rg-rbac-prd --query "properties.runningStatus"

# Force a new revision
az containerapp update --name rbac-dashboard --resource-group rg-rbac-prd --image <same-image>

# Or redeploy from Terraform
terraform apply
```

**Scenario: Graph builder job consistently fails**

```bash
# Check recent executions
az containerapp job execution list --name rbac-graph-builder --resource-group rg-rbac-prd --output table

# View logs from the last failed execution
az containerapp job logs show --name rbac-graph-builder --resource-group rg-rbac-prd

# Manually trigger a run to test
az containerapp job start --name rbac-graph-builder --resource-group rg-rbac-prd
```

**Scenario: Full environment rebuild**

```bash
# Terraform recreates everything from state
terraform destroy   # only if needed
terraform apply
# Then push the container image to the new ACR
```

---

## Day-2 Operations Runbook

### Rotate AI Foundry Key

```bash
# Generate a new key in the Azure portal, then update Key Vault
az keyvault secret set --vault-name kv-rbac-prd001 --name AiFoundryKey --value "<new-key>"

# The app picks up the new secret on next Key Vault read (no restart needed
# if using lazy loading; otherwise restart the dashboard)
az containerapp revision restart --name rbac-dashboard --resource-group rg-rbac-prd --revision <revision-name>
```

### Update the Container Image

```bash
# Build and push new image
docker build -t acrrbacprd001.azurecr.io/azure-rbac:v1.2.0 .
docker push acrrbacprd001.azurecr.io/azure-rbac:v1.2.0

# Update Terraform variable
# container_image_tag = "v1.2.0"
terraform apply

# Or update directly
az containerapp update --name rbac-dashboard --resource-group rg-rbac-prd \
  --image acrrbacprd001.azurecr.io/azure-rbac:v1.2.0
```

### Change the Graph Builder Schedule

```bash
# Edit terraform.tfvars
graph_builder_cron = "0 3 * * *"   # Change to 03:00 UTC
terraform apply
```

### Add a New Subscription to Scan

The managed identity needs `Reader` on the new subscription:

```bash
PRINCIPAL_ID=$(terraform -chdir=terraform output -raw managed_identity_principal_id)

az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Reader" \
  --scope "/subscriptions/<new-subscription-id>"
```

---

## Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Dashboard shows "No graph data" | Graph builder has not run yet | Trigger a manual run: `az containerapp job start ...` |
| Dashboard returns 502 | Container is crashing | Check logs: `az containerapp logs show ...` |
| Graph builder job timeout | Large tenant, insufficient resources | Increase `graph_builder_cpu` and `graph_builder_memory` |
| "Forbidden" accessing Key Vault | Missing RBAC assignment | Verify managed identity has `Key Vault Secrets User` role |
| "Forbidden" accessing Blob Storage | Missing RBAC assignment | Verify managed identity has `Storage Blob Data Contributor` role |
| ACR pull fails | Missing `AcrPull` role | Verify `az role assignment list --assignee <principal-id>` |
| Terraform state lock error | Another apply in progress | Wait or break the lock: `terraform force-unlock <lock-id>` |

---

## References

- [Azure Container Apps documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Container Apps jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- [Terraform azurerm provider – Container Apps](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/container_app)
- [Managed identities in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [Container Apps networking](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Container Apps monitoring](https://learn.microsoft.com/en-us/azure/container-apps/observability)
