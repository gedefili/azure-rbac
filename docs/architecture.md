# System Architecture – Azure RBAC Permission Graph Tool

## Overview

This tool collects every role assignment in an Azure tenant, builds a directed permission graph, surfaces security issues, and provides AI-powered remediation guidance via **Azure AI Foundry**.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Azure Tenant                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐  │
│  │ Mgmt     │  │ Sub A    │  │ Sub B    │  │  Azure AD / Entra  │  │
│  │ Groups   │  │ RGs/Res  │  │ RGs/Res  │  │  Users/Groups/SPs  │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬───────────┘  │
│       │              │              │                  │              │
│       └──────────────┴──────────────┴──────────────────┘             │
│                            Azure ARM / Graph API                      │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │
                           ┌─────────▼──────────┐
                           │   AzureClient       │
                           │ (azure_client.py)   │
                           └─────────┬──────────┘
                                     │
                           ┌─────────▼──────────┐
                           │   GraphBuilder      │
                           │ (graph_builder.py)  │
                           │  NetworkX DiGraph   │
                           └──────┬──────┬──────┘
                                  │      │
               ┌──────────────────┘      └──────────────────┐
               │                                             │
    ┌──────────▼──────────┐                    ┌────────────▼──────────┐
    │  SecurityAnalyzer   │                    │   Dashboard (Flask)    │
    │ (security_analyzer) │                    │      app.py            │
    │                     │                    │   index.html + D3.js   │
    │  Findings (JSON)    │                    └───────────────────────┘
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │     AIAdvisor       │
    │   (ai_advisor.py)   │
    │  Azure AI Foundry   │
    │  GPT-4o / Phi-3     │
    └─────────────────────┘
```

---

## Components

### 1. AzureClient (`azure_client.py`)

**Responsibility**: Authenticate to Azure and retrieve raw RBAC data.

| Method | Azure API | Purpose |
|---|---|---|
| `list_subscriptions()` | ARM – Subscriptions | Enumerate all subscriptions |
| `list_management_groups()` | Management Groups API | Enumerate MG hierarchy |
| `list_role_assignments(sub_id)` | ARM – Authorization | All assignments per subscription |
| `list_role_definitions(sub_id)` | ARM – Authorization | All role definitions |
| `list_resource_groups(sub_id)` | ARM – Resource | Resource group list |

**Authentication** (priority order):
1. Managed Identity (when `AZURE_USE_MSI=true`)
2. Service Principal client secret (`AZURE_CLIENT_ID` + `AZURE_CLIENT_SECRET`)
3. `DefaultAzureCredential` (environment, workload identity, Azure CLI)

**Required Azure RBAC permissions**:
- `Reader` on all subscriptions (or at Management Group level)
- `Microsoft.Authorization/roleAssignments/read`
- `Microsoft.Authorization/roleDefinitions/read`
- `Directory.Read.All` on Microsoft Graph (for principal display names)

---

### 2. GraphBuilder (`graph_builder.py`)

**Responsibility**: Build a NetworkX `DiGraph` representing the tenant permission structure.

#### Node types

| `node_type` | `sub_type` values | Represents |
|---|---|---|
| `principal` | `User`, `Group`, `ServicePrincipal` | Azure AD identities |
| `resource` | `subscription`, `management_group`, `resource_group`, `resource` | Azure scopes |
| `role` | `BuiltInRole`, `CustomRole` | Role definitions |

#### Edge types

| `edge_type` | From → To | Meaning |
|---|---|---|
| `assigned` | principal → role | This principal has been assigned this role |
| `scoped_to` | role (instance) → resource | This role assignment is scoped to this resource |
| `contains` | subscription → resource_group | Containment relationship |

#### Graph invariants

- Every role assignment produces exactly one `assigned` and one `scoped_to` edge.
- The same role definition node is reused across multiple assignments.
- Scope resolution maps ARM scope strings to the correct node type (sub/rg/resource).

---

### 3. SecurityAnalyzer (`security_analyzer.py`)

**Responsibility**: Inspect the graph and emit structured `Finding` objects.

#### Rules

| Rule ID | Severity | Check |
|---|---|---|
| RBAC-001 | HIGH | Privileged role (Owner/Contributor/UAA) at subscription scope |
| RBAC-002 | MEDIUM | Direct user assignment instead of group |
| RBAC-003 | MEDIUM | Orphaned assignment (principal not found in Azure AD) |
| RBAC-004 | CRITICAL | Service principal assigned Owner role |
| RBAC-005 | HIGH | Custom role with wildcard (`*`) actions |
| RBAC-006 | LOW | Low group-based access adoption (<20%) |

Each `Finding` contains:
- `id`, `severity`, `title`, `description`
- `affected_nodes` (list of graph node IDs) – used by the dashboard to highlight nodes
- `remediation` – step-by-step fix guidance
- `references` – links to Microsoft documentation

After analysis, the analyzer annotates affected graph nodes with `security_flags` (used for visual highlighting in the dashboard).

---

### 4. AIAdvisor (`ai_advisor.py`)

**Responsibility**: Send findings and graph metadata to **Azure AI Foundry** for AI-powered recommendations.

#### Inputs

- Full list of `Finding` objects (serialised to JSON)
- Graph summary statistics (node/edge counts, subscription names)
- Optional free-text context (tenant name, compliance requirements)

#### Outputs

- **Remediation report** – Markdown document with prioritised action plan
- **Persona suggestions** – Proposed job-function groups to replace individual assignments

#### How it connects to AI Foundry

```python
from openai import AzureOpenAI

client = AzureOpenAI(
    azure_endpoint="https://<hub>.openai.azure.com/",
    api_key="<key>",                  # or azure_ad_token_provider=…
    api_version="2024-02-01",
)
response = client.chat.completions.create(
    model="gpt-4o",                   # deployment name in AI Foundry
    messages=[{"role": "user", "content": prompt}],
)
```

---

### 5. Dashboard (`dashboard/`)

**Responsibility**: Serve an interactive web UI for graph exploration.

#### REST API

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Single-page HTML dashboard |
| `/api/graph` | GET | Full graph JSON (`?node_type=principal` to filter) |
| `/api/graph/node/<id>` | GET | Node detail + neighbours |
| `/api/findings` | GET | All findings (`?severity=critical` to filter) |
| `/api/findings/summary` | GET | Finding counts by severity |
| `/api/graph/reload` | POST | Invalidate in-memory cache |
| `/api/health` | GET | Health check |

#### Front-end

- **D3.js v7** force-directed graph
- Nodes coloured by type; security-flagged nodes pulse in red
- Click-to-drill: shows node metadata, security flags, and neighbours in a side panel
- Filter toolbar: All / Principals / Roles / Resources / ⚠ Flagged
- Live search across node labels

---

## Data Flow

```
1. azure-rbac build
   └─ AzureClient → list subscriptions, MGs, role assignments, role definitions
   └─ GraphBuilder.build() → NetworkX DiGraph
   └─ GraphBuilder.save("graph.json")

2. azure-rbac analyze --graph graph.json --output findings.json
   └─ GraphBuilder.load("graph.json")
   └─ SecurityAnalyzer.analyze() → list[Finding]
   └─ findings.json

3. azure-rbac advise --findings findings.json
   └─ AIAdvisor.generate_remediation_report() → Markdown report
   └─ (optional) AIAdvisor.suggest_personas()

4. azure-rbac dashboard --graph graph.json
   └─ Flask app reads graph.json + findings.json
   └─ Serves http://localhost:5000
```

---

## Storage Architecture

Graph snapshots and findings are persisted to **Azure Blob Storage** for historical analysis and audit trails. See [deployment-options.md](deployment-options.md) for storage account configuration.

```
Storage Account: rbacgraph<env>
└── Container: graph-snapshots/
    ├── 2026-03-01T00:00:00Z/graph.json
    ├── 2026-03-01T00:00:00Z/findings.json
    └── latest/
        ├── graph.json
        └── findings.json
```

---

## Security Considerations

- The service principal used by this tool only needs **read** permissions.
- API keys and connection strings are loaded from **Azure Key Vault** at runtime (never stored in environment files in production).
- The dashboard runs behind your organisation's authentication proxy (Azure AD App Service authentication or API Management).
- Graph data and findings may contain sensitive permission information – restrict access accordingly.

---

## AWS Phase 2 Extension Point

The `AzureClient` is the only Azure-specific component. Phase 2 adds an `AwsClient` with the same interface:

```python
class AwsClient:
    def list_subscriptions(self) -> list[Subscription]:   # → AWS accounts
    def list_role_assignments(self, account_id: str) -> list[RoleAssignment]:
    def list_role_definitions(self, account_id: str) -> list[RoleDefinition]:
    def list_resource_groups(self, account_id: str) -> list[dict]:
```

`GraphBuilder`, `SecurityAnalyzer`, and the dashboard are cloud-agnostic and will work unchanged with the AWS client.
