# Deployment Options, Storage, and Key Vault

This document describes the supported deployment targets for the Azure RBAC Permission Graph tool and the required supporting infrastructure (Storage Account and Key Vault).

---

## Supporting Infrastructure (Required for All Deployments)

### Storage Account

The storage account persists graph snapshots and security findings for historical trending and audit.

#### Naming and SKU recommendations

| Environment | Storage Account Name | SKU | Replication |
|---|---|---|---|
| Development | `strbacdev<suffix>` | Standard | LRS |
| Staging | `strbacstg<suffix>` | Standard | ZRS |
| Production | `strbacprd<suffix>` | Standard | GRS |

#### Container layout

```
strbacprd<suffix>
└── graph-snapshots/
    ├── YYYY-MM-DDTHH:MM:SSZ/
    │   ├── graph.json          # Full permission graph
    │   └── findings.json       # Security findings
    └── latest/
        ├── graph.json
        └── findings.json
```

#### Provisioning

```bash
az storage account create \
  --name strbacprd001 \
  --resource-group rg-rbac \
  --location eastus \
  --sku Standard_GRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --https-only true

az storage container create \
  --name graph-snapshots \
  --account-name strbacprd001 \
  --auth-mode login
```

#### Lifecycle policy (auto-delete old snapshots)

```bash
az storage account management-policy create \
  --account-name strbacprd001 \
  --resource-group rg-rbac \
  --policy '{
    "rules": [{
      "name": "delete-old-snapshots",
      "type": "Lifecycle",
      "definition": {
        "filters": {"blobTypes": ["blockBlob"], "prefixMatch": ["graph-snapshots/20"]},
        "actions": {"baseBlob": {"delete": {"daysAfterModificationGreaterThan": 90}}}
      }
    }]
  }'
```

#### RBAC permissions

| Identity | Role | Scope |
|---|---|---|
| Tool's managed identity | `Storage Blob Data Contributor` | Storage account |
| Dashboard app identity | `Storage Blob Data Reader` | Storage account |
| Developers | `Storage Blob Data Reader` | Storage account |

---

### Azure Key Vault

Key Vault stores all secrets used by the tool (AI Foundry key, storage connection string, Azure AD client secret if used).

#### Naming

| Environment | Key Vault Name |
|---|---|
| Development | `kv-rbac-dev` |
| Staging | `kv-rbac-stg` |
| Production | `kv-rbac-prd` |

#### Provisioning

```bash
az keyvault create \
  --name kv-rbac-prd \
  --resource-group rg-rbac \
  --location eastus \
  --sku standard \
  --enable-rbac-authorization true \
  --enable-soft-delete true \
  --retention-days 90 \
  --public-network-access Disabled   # Private endpoint only in prod
```

#### Secrets to store

| Secret Name | Description |
|---|---|
| `AzureTenantId` | Tenant ID for RBAC data collection |
| `AzureClientId` | Service principal app ID |
| `AzureClientSecret` | Service principal secret (if not using MSI) |
| `AiFoundryEndpoint` | Azure AI Foundry project endpoint URL |
| `AiFoundryKey` | AI Foundry API key |
| `StorageConnectionString` | Storage account connection string |

```bash
az keyvault secret set --vault-name kv-rbac-prd --name AiFoundryEndpoint --value "https://…"
az keyvault secret set --vault-name kv-rbac-prd --name AiFoundryKey --value "<key>"
```

#### Access policy (RBAC model)

```bash
# Grant tool's managed identity read access to secrets
az role assignment create \
  --assignee <managed-identity-object-id> \
  --role "Key Vault Secrets User" \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-rbac/providers/Microsoft.KeyVault/vaults/kv-rbac-prd

# Grant admins full access
az role assignment create \
  --assignee <admin-group-object-id> \
  --role "Key Vault Administrator" \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-rbac/providers/Microsoft.KeyVault/vaults/kv-rbac-prd
```

#### Private endpoint (production)

```bash
az network private-endpoint create \
  --name pe-kv-rbac-prd \
  --resource-group rg-rbac \
  --vnet-name vnet-rbac \
  --subnet snet-private-endpoints \
  --private-connection-resource-id /subscriptions/<sub-id>/resourceGroups/rg-rbac/providers/Microsoft.KeyVault/vaults/kv-rbac-prd \
  --group-id vault \
  --connection-name conn-kv-rbac-prd
```

---

## Deployment Options

### Option A: Azure Container Apps (Recommended) ✅

**Best for**: Production, auto-scaling, minimal ops overhead

> **Terraform templates included.** See [`terraform/`](../terraform/) for the complete infrastructure-as-code deployment and [`docs/container-apps-plan.md`](container-apps-plan.md) for the detailed deployment plan.

#### Architecture

```
Internet → HTTPS → Container App Environment
                   ├── rbac-dashboard      (web app, HTTP ingress, 1–5 replicas)
                   └── rbac-graph-builder  (cron job, nightly at 02:00 UTC)
                         │
                   ┌─────┴─────┐
                   │ Key Vault │  Storage Account  │  ACR  │  Log Analytics
```

#### Quick Start with Terraform

```bash
cd terraform/
cp terraform.tfvars.example terraform.tfvars   # edit with your values
terraform init
terraform plan
terraform apply
```

This creates the Container App Environment, dashboard, scheduled graph builder job, ACR, Storage Account, Key Vault, Log Analytics workspace, managed identity, and all RBAC role assignments. See the [Container Apps Plan](container-apps-plan.md) for the full step-by-step walkthrough.

#### Manual Provisioning (Azure CLI)

```bash
# Create Container App Environment
az containerapp env create \
  --name cae-rbac-prd \
  --resource-group rg-rbac \
  --location eastus \
  --enable-workload-profiles

# Deploy dashboard
az containerapp create \
  --name rbac-dashboard \
  --resource-group rg-rbac \
  --environment cae-rbac-prd \
  --image <acr-name>.azurecr.io/azure-rbac:latest \
  --target-port 5000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5 \
  --cpu 0.5 --memory 1.0Gi \
  --system-assigned \
  --env-vars \
      KEY_VAULT_URI=https://kv-rbac-prd.vault.azure.net/ \
      AZURE_USE_MSI=true

# Deploy nightly graph builder as a job
az containerapp job create \
  --name rbac-graph-builder \
  --resource-group rg-rbac \
  --environment cae-rbac-prd \
  --image <acr-name>.azurecr.io/azure-rbac:latest \
  --trigger-type Schedule \
  --cron-expression "0 2 * * *" \
  --replica-timeout 3600 \
  --command "azure-rbac build --output /mnt/graph.json"
```

#### Pros / Cons

| Pros | Cons |
|---|---|
| Serverless, scales to zero | Limited to containerised workloads |
| Managed TLS, custom domain | Cold start latency |
| Built-in Dapr support | |
| KEDA-based auto-scaling | |
| **Terraform templates provided** | |

---

### Option B: Azure App Service

**Best for**: Teams already using App Service, simple web app deployment

```bash
az appservice plan create \
  --name asp-rbac-prd \
  --resource-group rg-rbac \
  --sku P1V3 \
  --is-linux

az webapp create \
  --name rbac-dashboard-prd \
  --resource-group rg-rbac \
  --plan asp-rbac-prd \
  --runtime "PYTHON:3.12"

# Enable managed identity
az webapp identity assign \
  --name rbac-dashboard-prd \
  --resource-group rg-rbac

# Configure app settings (from Key Vault references)
az webapp config appsettings set \
  --name rbac-dashboard-prd \
  --resource-group rg-rbac \
  --settings \
    AZURE_USE_MSI=true \
    KEY_VAULT_URI=https://kv-rbac-prd.vault.azure.net/ \
    WEBSITES_PORT=5000
```

**Nightly scan**: Use an **Azure Logic App** or **Azure Functions** timer trigger to run the `azure-rbac build` command via the App Service REST API or a separate Azure Function.

---

### Option C: Azure Kubernetes Service (AKS)

**Best for**: Organisations already running AKS, need full control over networking

#### Workload Identity setup

```yaml
# serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: rbac-tool-sa
  namespace: rbac
  annotations:
    azure.workload.identity/client-id: <managed-identity-client-id>
```

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rbac-dashboard
  namespace: rbac
spec:
  replicas: 2
  selector:
    matchLabels:
      app: rbac-dashboard
  template:
    metadata:
      labels:
        app: rbac-dashboard
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: rbac-tool-sa
      containers:
      - name: dashboard
        image: <acr-name>.azurecr.io/azure-rbac:latest
        command: ["azure-rbac", "dashboard", "--graph", "/data/graph.json"]
        ports:
        - containerPort: 5000
        env:
        - name: AZURE_USE_MSI
          value: "true"
        - name: KEY_VAULT_URI
          value: "https://kv-rbac-prd.vault.azure.net/"
        volumeMounts:
        - name: graph-data
          mountPath: /data
      volumes:
      - name: graph-data
        persistentVolumeClaim:
          claimName: rbac-graph-pvc
---
# CronJob for nightly graph rebuild
apiVersion: batch/v1
kind: CronJob
metadata:
  name: rbac-graph-builder
  namespace: rbac
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: rbac-tool-sa
          restartPolicy: OnFailure
          containers:
          - name: builder
            image: <acr-name>.azurecr.io/azure-rbac:latest
            command: ["azure-rbac", "build", "--output", "/data/graph.json"]
            volumeMounts:
            - name: graph-data
              mountPath: /data
          volumes:
          - name: graph-data
            persistentVolumeClaim:
              claimName: rbac-graph-pvc
```

---

### Option D: Azure Functions (Serverless, Scan Only)

**Best for**: Running the graph builder and analyzer on a schedule without a persistent server

```python
# function_app.py
import azure.functions as func
from azure_rbac.azure_client import AzureClient
from azure_rbac.graph_builder import GraphBuilder
from azure_rbac.security_analyzer import SecurityAnalyzer

app = func.FunctionApp()

@app.timer_trigger(schedule="0 0 2 * * *", arg_name="timer")
def nightly_scan(timer: func.TimerRequest) -> None:
    client = AzureClient()
    builder = GraphBuilder(client)
    builder.build()
    builder.save("/tmp/graph.json")

    import networkx as nx
    analyzer = SecurityAnalyzer(builder.graph)
    findings = analyzer.analyze()
    # Upload to blob storage…
```

---

### Option E: Local / Developer Workstation

For development and ad-hoc analysis:

```bash
# Authenticate with Azure CLI
az login
az account set --subscription <sub-id>

# Build graph
azure-rbac build --output /tmp/graph.json

# Analyse
azure-rbac analyze --graph /tmp/graph.json --output /tmp/findings.json

# Get AI recommendations
azure-rbac advise --findings /tmp/findings.json

# Launch dashboard
azure-rbac dashboard --graph /tmp/graph.json
# open http://localhost:5000
```

---

## Docker Image

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .

EXPOSE 5000
CMD ["azure-rbac", "dashboard", "--graph", "/data/graph.json"]
```

```bash
# Build and push
docker build -t <acr-name>.azurecr.io/azure-rbac:latest .
az acr login --name <acr-name>
docker push <acr-name>.azurecr.io/azure-rbac:latest
```

---

## CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4

    - name: Run tests
      run: |
        pip install -e ".[dev]"
        pytest

    - name: Login to ACR
      uses: azure/docker-login@v1
      with:
        login-server: ${{ secrets.ACR_LOGIN_SERVER }}
        username: ${{ secrets.ACR_USERNAME }}
        password: ${{ secrets.ACR_PASSWORD }}

    - name: Build and push image
      run: |
        docker build -t ${{ secrets.ACR_LOGIN_SERVER }}/azure-rbac:${{ github.sha }} .
        docker push ${{ secrets.ACR_LOGIN_SERVER }}/azure-rbac:${{ github.sha }}

    - name: Deploy to Container Apps
      uses: azure/container-apps-deploy-action@v1
      with:
        appSourcePath: ${{ github.workspace }}
        acrName: ${{ secrets.ACR_NAME }}
        containerAppName: rbac-dashboard
        resourceGroup: rg-rbac
        imageToDeploy: ${{ secrets.ACR_LOGIN_SERVER }}/azure-rbac:${{ github.sha }}
```

---

## Deployment Comparison

| Criteria | Container Apps | App Service | AKS | Functions |
|---|---|---|---|---|
| Complexity | Low | Low | High | Low |
| Ops overhead | Very low | Low | High | Very low |
| Cost (idle) | Near zero | ~$50/mo (P1V3) | ~$100+/mo | Near zero |
| Custom networking | Yes (managed VNet) | Yes | Yes | Yes |
| Scale to zero | Yes | No (Basic+) | No | Yes |
| Persistent storage | Volumes (preview) | App Service mount | PVC | Blob only |
| Best for | Recommended | Existing App Svc | Enterprise K8s | Batch jobs only |

---

## References

- [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/)
- [AKS Workload Identity](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview)
- [Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/)
- [Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/)
- [Azure Blob Storage lifecycle management](https://learn.microsoft.com/en-us/azure/storage/blobs/lifecycle-management-overview)
