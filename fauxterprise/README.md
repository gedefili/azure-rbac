# Fauxterprise – Simulated Enterprise Azure Environment

A Terraform project that provisions a realistic, "messy" enterprise Azure tenant for use as a demo environment with the **azure-rbac** analyzer. It covers a wide range of patterns you'd find in a real Cloud Adoption Framework (CAF) landing zone deployment.

## What's Inside

### 1. Management Group Hierarchy (CAF-lite)

```
Tenant Root
 └─ faux-enterprise
      ├─ Platform
      │    ├─ Connectivity      (hub networking, ExpressRoute)
      │    ├─ Identity           (AD DS, Entra Connect)
      │    └─ Management         (logging, monitoring, automation)
      ├─ Landing Zones
      │    ├─ Production         (2 subscriptions)
      │    ├─ Staging            (2 subscriptions)
      │    └─ Development        (1 subscription)
      ├─ Sandbox                 (1 subscription)
      └─ Decommissioned          (1 subscription)
```

### 2. Subscriptions (10 total)

| Subscription | Management Group | Location | Purpose |
|---|---|---|---|
| connectivity-sub | Connectivity | eastus2 | Hub networking, ExpressRoute, DNS, Firewall |
| identity-sub | Identity | eastus2 | AD DS, Entra Connect |
| management-sub | Management | eastus2 | Logging, monitoring, automation, backup |
| prod-app1-sub | Production | eastus2 | Production workload #1 (web app + SQL) |
| prod-app2-sub | Production | westus2 | Production workload #2 (AKS + Cosmos DB + ML) |
| staging-sub | Staging | eastus2 | Staging environment |
| staging-perf-sub | Staging | westus2 | Performance / load testing |
| dev-sub | Development | eastus2 | Development environment |
| sandbox-sub | Sandbox | centralus | Experimentation |
| decommissioned-sub | Decommissioned | eastus | Retired workloads |

### 3. Networking

- **Hub/spoke** topology with VNet peering from every spoke to the hub
- **Azure Firewall** in the hub VNet
- **ExpressRoute circuit** + VPN Gateway (partially configured)
  - Private peering configured on the circuit
  - Gateway connection established on the hub side
  - Staging VNet intentionally **not** using remote gateways (gap for the analyzer to find)
- **Private DNS zones** for blob, vault, database, and app services
- **NSGs** on every spoke VNet

### 4. 100 Azure AD Users

First names from famous **computer scientists**, last names from famous **AI scientists**:

> Ada Turing, Alan McCarthy, Grace Minsky, Donald Hinton, Edsger Bengio, John LeCun, Claude Ng, Barbara Russell, Dennis Norvig, Linus Pearl, …

Users are assigned to **15 security groups** based on department:

| Group | Purpose |
|---|---|
| platform-admins | Owner on platform subscriptions |
| security-team | Reader + KV Reader across prod |
| app-developers | Contributor on dev, Reader on staging |
| data-engineers | Contributor on data RGs |
| devops-team | Contributor on staging & dev |
| identity-admins | Owner on identity subscription |
| network-ops | Network Contributor on connectivity |
| ml-team | Contributor on ML resource groups |
| qa-team | QA assignments |
| it-ops | Monitoring Contributor on management |
| read-only-auditors | Reader on production (every 3rd user) |
| contributor-leads | Contributor on landing zones (every 7th user) |
| sandbox-users | Contributor on sandbox (every 5th user) |
| keyvault-admins | Key Vault Administrator on all vaults |
| storage-blob-contributors | Storage Blob Data Contributor |

### 5. Storage Accounts (1 per subscription)

Access model **alternates** between subscriptions:
- Even-indexed → **RBAC** (shared access key disabled)
- Odd-indexed → **Key-based** (shared access key enabled)

Each includes blob containers (`data`, `logs`, `backups`), with tables and queues for select subscriptions.

### 6. Key Vaults (1 per subscription)

Access model **alternates** (opposite of storage):
- Even-indexed → **Access Policy**
- Odd-indexed → **RBAC**

Each vault is seeded with demo secrets (`db-connection-password`, `api-key`, `storage-account-key`).

### 7. Additional Resources

| Category | Resources |
|---|---|
| **Compute** | 2× Linux web VMs, 2× Windows DCs, 1× jumpbox, AKS cluster, Container Instance, Container Registry |
| **Databases** | Azure SQL (prod), PostgreSQL Flexible (staging), Cosmos DB (prod ML), Redis Cache (perf) |
| **App Services** | 4× Linux Web Apps, 2× Function Apps, 3× App Service Plans |
| **Messaging** | Event Hub namespace, Service Bus + queues |
| **Monitoring** | Log Analytics workspace, 2× App Insights |
| **Identity** | 5× service principals (deploy, monitoring, backup, data-pipeline, ml-inference) |

### 8. Role Assignments (intentionally messy)

- Group-level assignments at RG scope (standard CAF pattern)
- **Over-privileged individuals**: User 0 is Owner on prod, User 99 is Owner on prod + staging
- **Stale assignments**: User 50 has Reader on decommissioned
- **User Access Administrator** grants on staging
- Individual blob/secret/monitoring role assignments
- ~200+ total role assignment resources

## Usage

There are three ways to test against this environment, from simplest to most realistic:

### Option 1: Local Fixture (No Azure Needed)

Generate a JSON fixture that matches what the Azure SDK would return, then run
the full tool pipeline locally. **This is the fastest way to get started.**

```bash
# Generate the fixture from Terraform definitions
python fauxterprise/generate_fixture.py

# Build the RBAC graph using the fixture (no Azure credentials required)
azure-rbac build --fixture fauxterprise/fixture.json -o graph.json

# Run security analysis
azure-rbac analyze -g graph.json

# Launch the dashboard
azure-rbac dashboard -g graph.json
```

### Option 2: Docker Compose (Virtual Server)

Run the entire pipeline in Docker containers:

```bash
cd fauxterprise

# Full pipeline: generate fixture → build graph → analyze → start dashboard
docker compose up pipeline
# → Open http://localhost:5000

# Or run individual steps:
docker compose run --rm generate-fixture
docker compose run --rm build-graph
docker compose run --rm analyze
docker compose up dashboard
```

### Option 3: Real Azure Deployment (Lab Subscription)

Deploy to an actual Azure subscription using the included deploy script:

```bash
cd fauxterprise
cp terraform.tfvars.example terraform.tfvars   # customise as needed

# Initialise Terraform
./deploy.sh init

# Preview what will be created
./deploy.sh plan

# Deploy (requires confirmation — costs ~$150–$300/month)
./deploy.sh apply

# After testing, tear down everything
./deploy.sh destroy
```

**Prerequisites for real deployment:**
- Terraform >= 1.5
- Azure CLI logged in (`az login`)
- Owner or Contributor + User Access Admin on the target subscription
- Application Administrator in Azure AD

### Variables

| Variable | Default | Description |
|---|---|---|
| `prefix` | `faux` | Short prefix for all resource names |
| `domain` | `fauxterprise.onmicrosoft.com` | Azure AD domain for user UPNs |
| `primary_location` | `eastus2` | Primary Azure region |
| `secondary_location` | `westus2` | Secondary region |
| `express_route_location` | `Washington DC` | ExpressRoute peering location |

## What the azure-rbac Analyzer Will Find

This environment is designed to surface realistic findings:

- **Over-privileged users** (Owner on prod, shadow admins)
- **Stale access** on decommissioned resources
- **Mixed access models** (RBAC vs key-based storage, RBAC vs access-policy vaults)
- **Incomplete network peering** (staging not using ExpressRoute gateway)
- **Broad group permissions** vs **individual direct assignments**
- **Service principal proliferation**
- **User Access Administrator** grants (privilege escalation risk)
- **Cross-environment access** (same user with access to prod + staging)
