# Azure RBAC Permission Graph

A tool to visualize, analyze, and remediate Azure role-based access control (RBAC) at the
tenant level. It builds a graph of every principal, role, and resource in your Azure tenant,
surfaces security issues, suggests least-privilege personas, and provides AI-powered
remediation guidance via **Azure AI Foundry**.

---

## Features

| Capability | Description |
|---|---|
| **Tenant-wide graph** | Discovers every role assignment across all subscriptions and management groups |
| **Interactive dashboard** | D3.js force-directed graph with drill-down into subscriptions, resource groups, and individual resources |
| **Security analysis** | Detects over-privileged accounts, dormant identities, orphaned assignments, and missing group-based access |
| **Role/persona recommendations** | Groups principals by activity pattern and proposes consolidated custom roles |
| **AI-powered remediation** | Sends findings to Azure AI Foundry for natural-language remediation plans |
| **AWS phase 2 ready** | Pluggable client architecture allows adding an AWS IAM provider later |

---

## Quick Start

### Prerequisites

* Python 3.11+
* An Azure service principal with `Reader` access to all subscriptions and the `Directory Readers`
  Azure AD role (or equivalent Microsoft Graph permissions).
* (Optional) An Azure AI Foundry project endpoint and key for AI-powered recommendations.

### Installation

```bash
pip install -e ".[dev]"
```

### Configuration

Copy the sample environment file and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `AZURE_TENANT_ID` | Your Azure tenant ID |
| `AZURE_CLIENT_ID` | Service principal application (client) ID |
| `AZURE_CLIENT_SECRET` | Service principal secret (or use `AZURE_USE_MSI=true`) |
| `AZURE_USE_MSI` | Set to `true` to use Managed Identity instead of client secret |
| `AI_FOUNDRY_ENDPOINT` | Azure AI Foundry project endpoint URL |
| `AI_FOUNDRY_KEY` | API key for AI Foundry (or leave blank to use Azure AD auth) |
| `AI_FOUNDRY_DEPLOYMENT` | Deployment name inside AI Foundry (e.g. `gpt-4o`) |
| `AZURE_STORAGE_CONNECTION_STRING` | Storage account connection string for graph snapshots |
| `KEY_VAULT_URI` | Azure Key Vault URI used to retrieve secrets at runtime |

### Build the permission graph

```bash
python -m azure_rbac.graph_builder --output graph.json
```

### Run the dashboard

```bash
python -m azure_rbac.dashboard.app
# open http://localhost:5000
```

### Run security analysis

```bash
python -m azure_rbac.security_analyzer --graph graph.json --output findings.json
```

### Get AI recommendations

```bash
python -m azure_rbac.ai_advisor --findings findings.json
```

---

## Project Layout

```
azure-rbac/
├── docs/
│   ├── architecture.md          # System architecture
│   ├── ai-foundry-setup.md      # Azure AI Foundry setup guide
│   ├── ai-models.md             # AI model selection planning
│   ├── container-apps-plan.md   # Detailed Container Apps deployment plan
│   └── deployment-options.md    # Deployment, storage, and Key Vault options
├── terraform/                   # Infrastructure-as-code (Azure Container Apps)
│   ├── main.tf                  # Provider config, resource group
│   ├── variables.tf             # Input variables
│   ├── outputs.tf               # Output values
│   ├── container-apps.tf        # Container App Environment, dashboard, job
│   ├── acr.tf                   # Azure Container Registry
│   ├── storage.tf               # Storage Account + lifecycle policy
│   ├── keyvault.tf              # Key Vault (RBAC-based)
│   ├── identity.tf              # Managed Identity + role assignments
│   ├── log-analytics.tf         # Log Analytics workspace
│   └── terraform.tfvars.example # Example variable values
├── src/
│   └── azure_rbac/
│       ├── azure_client.py      # Azure Graph/ARM API client
│       ├── graph_builder.py     # Permission graph construction
│       ├── security_analyzer.py # Security findings engine
│       ├── ai_advisor.py        # AI Foundry integration
│       └── dashboard/
│           ├── app.py           # Flask REST API + server
│           ├── templates/
│           │   └── index.html   # Dashboard UI
│           └── static/
│               └── graph.js     # D3.js graph visualization
├── tests/
│   ├── test_azure_client.py
│   ├── test_graph_builder.py
│   └── test_security_analyzer.py
├── pyproject.toml
└── .env.example
```

---

## Documentation

| Document | Purpose |
|---|---|
| [Architecture](docs/architecture.md) | End-to-end system design |
| [AI Foundry Setup](docs/ai-foundry-setup.md) | How to provision AI Foundry and connect it to this tool |
| [AI Model Selection](docs/ai-models.md) | Which Azure AI Foundry models to use and why |
| [Container Apps Plan](docs/container-apps-plan.md) | Step-by-step Azure Container Apps deployment with Terraform |
| [Deployment Options](docs/deployment-options.md) | Container, App Service, AKS, and serverless options; storage and Key Vault guidance |

---

## Contributing

Pull requests are welcome. Please run `ruff check .` and `pytest` before submitting.

## License

See [LICENSE](LICENSE).
