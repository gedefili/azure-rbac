# Azure AI Foundry Setup Guide

This document walks you through provisioning **Azure AI Foundry** and connecting it to the Azure RBAC Permission Graph tool.

---

## What is Azure AI Foundry?

Azure AI Foundry (formerly Azure AI Studio) is Microsoft's unified platform for building, deploying, and managing AI applications. It provides:

- A **Model Catalog** with hundreds of models (OpenAI GPT-4o, Phi-4, Llama, Mistral, etc.)
- **Managed endpoints** for model inference
- **Azure AI Projects** for organising prompts, evaluations, and connections
- Built-in integration with Azure Key Vault, Storage, and Monitor

---

## Prerequisites

| Requirement | Details |
|---|---|
| Azure subscription | Owner or Contributor at subscription level |
| Resource group | Dedicate one to AI Foundry resources (e.g. `rg-rbac-ai`) |
| Azure region | Choose a region that supports GPT-4o: East US, West Europe, Sweden Central |
| Quota | Request GPT-4o quota in the chosen region via Azure portal |

---

## Step 1: Create an AI Foundry Hub

An **AI Foundry Hub** is the top-level resource that groups multiple AI projects and shared connections.

### Portal

1. Go to [https://ai.azure.com](https://ai.azure.com)
2. Click **+ New hub**
3. Fill in:
   - **Name**: `hub-rbac-<env>` (e.g. `hub-rbac-prod`)
   - **Subscription**: your Azure subscription
   - **Resource group**: `rg-rbac-ai`
   - **Region**: East US (or your preferred GPT-4o region)
   - **Storage account**: create new or select existing `strbacai<env>`
   - **Key Vault**: create new or select existing `kv-rbac-<env>`
   - **Application Insights**: create new for telemetry
4. Click **Review + Create**

### Azure CLI

```bash
# Create resource group
az group create --name rg-rbac-ai --location eastus

# Create AI Hub (requires azure-ai-ml extension)
az extension add --name azure-ai-ml

az ml workspace create \
  --kind hub \
  --name hub-rbac-prod \
  --resource-group rg-rbac-ai \
  --location eastus \
  --storage-account /subscriptions/<sub-id>/resourceGroups/rg-rbac-ai/providers/Microsoft.Storage/storageAccounts/strbacaiprod \
  --key-vault /subscriptions/<sub-id>/resourceGroups/rg-rbac-ai/providers/Microsoft.KeyVault/vaults/kv-rbac-prod
```

---

## Step 2: Create an AI Foundry Project

A **Project** is a child of the Hub and is the unit of work for your application.

### Portal

1. Inside your Hub, click **+ New project**
2. Fill in:
   - **Name**: `proj-rbac-analyzer`
   - **Hub**: `hub-rbac-prod`
3. Click **Create**

### CLI

```bash
az ml workspace create \
  --kind project \
  --name proj-rbac-analyzer \
  --resource-group rg-rbac-ai \
  --hub-id /subscriptions/<sub-id>/resourceGroups/rg-rbac-ai/providers/Microsoft.MachineLearningServices/workspaces/hub-rbac-prod
```

---

## Step 3: Deploy a Model

### Deploy GPT-4o (recommended)

1. In your Project, go to **Model Catalog** → search for **gpt-4o**
2. Click **Deploy** → **Serverless API** (pay-per-token) or **Standard** (provisioned)
3. Set:
   - **Deployment name**: `gpt-4o` (this is what goes in `AI_FOUNDRY_DEPLOYMENT`)
   - **Tokens per minute (TPM)**: 10 000 (increase as needed)
   - **Content filter**: Default (Microsoft Responsible AI policy)
4. After deployment, copy the **Target URI** (endpoint) and **Key**

### Deploy GPT-4o-mini (optional, for interactive Q&A)

Repeat the above with model **gpt-4o-mini** and deployment name `gpt-4o-mini`.

### Deploy Phi-4 (optional, for private/air-gapped deployments)

1. Search for **Phi-4** in Model Catalog
2. Click **Deploy** → **Managed compute**
3. Choose VM SKU: `Standard_NC24ads_A100_v4` (recommended for Phi-4)
4. Deployment takes ~10 minutes

---

## Step 4: Retrieve the Endpoint and Key

### Portal

1. Go to your Project → **Deployments**
2. Click your deployment (e.g. `gpt-4o`)
3. Copy:
   - **Target URI** → set as `AI_FOUNDRY_ENDPOINT` in your `.env` or Key Vault
   - **Key 1** → set as `AI_FOUNDRY_KEY`

### CLI

```bash
az cognitiveservices account keys list \
  --name <openai-resource-name> \
  --resource-group rg-rbac-ai \
  --query key1 -o tsv
```

---

## Step 5: Store Credentials in Key Vault

Never store the AI Foundry key in a `.env` file in production. Use **Azure Key Vault**:

```bash
# Store endpoint
az keyvault secret set \
  --vault-name kv-rbac-prod \
  --name "AiFoundryEndpoint" \
  --value "https://hub-rbac-prod.openai.azure.com/"

# Store key
az keyvault secret set \
  --vault-name kv-rbac-prod \
  --name "AiFoundryKey" \
  --value "<your-key>"
```

In the application, retrieve secrets via the `azure-keyvault-secrets` SDK:

```python
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

vault_uri = "https://kv-rbac-prod.vault.azure.net/"
client = SecretClient(vault_url=vault_uri, credential=DefaultAzureCredential())

endpoint = client.get_secret("AiFoundryEndpoint").value
key = client.get_secret("AiFoundryKey").value
```

---

## Step 6: Assign RBAC Permissions

The service principal or managed identity running the tool needs:

| Resource | Role | Purpose |
|---|---|---|
| AI Foundry Hub | `Azure AI Developer` | Submit inference requests |
| Key Vault | `Key Vault Secrets User` | Read secrets at runtime |
| Storage Account | `Storage Blob Data Contributor` | Write graph snapshots |
| All Subscriptions | `Reader` | Read RBAC data |

```bash
# Assign AI Developer role to the tool's managed identity
az role assignment create \
  --assignee <managed-identity-object-id> \
  --role "Azure AI Developer" \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-rbac-ai/providers/Microsoft.MachineLearningServices/workspaces/hub-rbac-prod

# Key Vault Secrets User
az role assignment create \
  --assignee <managed-identity-object-id> \
  --role "Key Vault Secrets User" \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-rbac-ai/providers/Microsoft.KeyVault/vaults/kv-rbac-prod
```

---

## Step 7: Configure the Tool

Set the following in `.env` (dev) or Key Vault (production):

```ini
AI_FOUNDRY_ENDPOINT=https://hub-rbac-prod.openai.azure.com/
AI_FOUNDRY_DEPLOYMENT=gpt-4o
# Leave AI_FOUNDRY_KEY blank to use DefaultAzureCredential (recommended for prod)
AI_FOUNDRY_KEY=
```

---

## Monitoring and Cost Management

### Enable diagnostic logging

```bash
az monitor diagnostic-settings create \
  --name "rbac-ai-diag" \
  --resource /subscriptions/<sub-id>/resourceGroups/rg-rbac-ai/providers/Microsoft.CognitiveServices/accounts/<openai-resource> \
  --logs '[{"category":"Audit","enabled":true},{"category":"RequestResponse","enabled":true}]' \
  --workspace /subscriptions/<sub-id>/resourceGroups/rg-rbac-ai/providers/Microsoft.OperationalInsights/workspaces/log-rbac
```

### Set spending limit alerts

```bash
az consumption budget create \
  --budget-name rbac-ai-budget \
  --amount 100 \
  --time-grain Monthly \
  --category Cost \
  --resource-group rg-rbac-ai \
  --notification-operator GreaterThan \
  --notification-threshold 80 \
  --contact-emails security-team@contoso.com
```

---

## Networking (Private Deployment)

For production deployments with strict network controls:

1. **Enable managed virtual network** on the AI Foundry Hub
2. **Create private endpoints** for:
   - Azure OpenAI resource
   - Key Vault
   - Storage Account
3. **Disable public network access** on all resources
4. Deploy the tool on an Azure VM or AKS pod inside the same VNet

```bash
# Enable Hub managed VNet
az ml workspace update \
  --name hub-rbac-prod \
  --resource-group rg-rbac-ai \
  --managed-network allow_internet_outbound

# Create private endpoint for OpenAI
az network private-endpoint create \
  --name pe-openai-rbac \
  --resource-group rg-rbac-ai \
  --vnet-name vnet-rbac \
  --subnet snet-private-endpoints \
  --private-connection-resource-id /subscriptions/<sub-id>/resourceGroups/rg-rbac-ai/providers/Microsoft.CognitiveServices/accounts/<openai-resource> \
  --group-id account \
  --connection-name conn-openai-rbac
```

---

## References

- [Azure AI Foundry documentation](https://learn.microsoft.com/en-us/azure/ai-studio/)
- [Deploy OpenAI models in Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-studio/how-to/deploy-models-openai)
- [Azure AI Foundry pricing](https://azure.microsoft.com/en-us/pricing/details/ai-studio/)
- [AI Foundry networking](https://learn.microsoft.com/en-us/azure/ai-studio/how-to/configure-managed-network)
- [Azure OpenAI quotas](https://learn.microsoft.com/en-us/azure/ai-services/openai/quotas-limits)
