#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh – Deploy or tear-down the Fauxterprise environment
#
# This script wraps Terraform to provision the simulated enterprise tenant
# in a real Azure subscription.  It adds safety checks, cost warnings, and
# handles the common lifecycle commands.
#
# Prerequisites:
#   • Terraform >= 1.5 on PATH
#   • Azure CLI logged in (az login) with sufficient privileges:
#       – Owner or Contributor + User Access Admin on the target subscription
#       – Application Administrator in Azure AD
#   • A terraform.tfvars file (copy terraform.tfvars.example to start)
#
# Usage:
#   ./deploy.sh init          Initialise Terraform and download providers
#   ./deploy.sh plan          Preview what will be created
#   ./deploy.sh apply         Apply the configuration (requires confirmation)
#   ./deploy.sh destroy       Tear down all resources (requires confirmation)
#   ./deploy.sh output        Show Terraform outputs
#   ./deploy.sh fixture       Generate fixture.json from live Terraform state
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colour helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERR]${NC}   $*" >&2; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
check_prereqs() {
    local missing=0
    for cmd in terraform az; do
        if ! command -v "$cmd" &>/dev/null; then
            error "$cmd is not installed or not on PATH"
            missing=1
        fi
    done
    if [[ $missing -ne 0 ]]; then
        exit 1
    fi

    # Verify Azure CLI is logged in
    if ! az account show &>/dev/null; then
        error "Azure CLI is not logged in.  Run: az login"
        exit 1
    fi

    info "Azure account: $(az account show --query '{name:name, id:id}' -o tsv)"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_init() {
    info "Initialising Terraform…"
    terraform init -upgrade
    ok "Terraform initialised"
}

cmd_plan() {
    check_prereqs
    if [[ ! -f terraform.tfvars ]]; then
        warn "No terraform.tfvars found – using defaults."
        warn "Copy terraform.tfvars.example and customise if needed."
    fi
    info "Running terraform plan…"
    terraform plan -out=tfplan
    ok "Plan saved to tfplan"
}

cmd_apply() {
    check_prereqs
    echo ""
    warn "═══════════════════════════════════════════════════════════════"
    warn "  This will create real Azure resources in your subscription."
    warn ""
    warn "  Resources include:"
    warn "    • 11 management groups"
    warn "    • 100 Azure AD users + 15 groups + 5 service principals"
    warn "    • ~30 resource groups across 10 logical subscriptions"
    warn "    • VNets, NSGs, storage accounts, Key Vaults, VMs, AKS…"
    warn "    • 200+ role assignments"
    warn ""
    warn "  Estimated monthly cost: \$150–\$300 (varies by region/SKU)"
    warn "  Run 'destroy' when done to avoid ongoing charges."
    warn "═══════════════════════════════════════════════════════════════"
    echo ""
    read -rp "Type 'yes' to proceed: " confirm
    if [[ "$confirm" != "yes" ]]; then
        info "Aborted."
        exit 0
    fi

    if [[ -f tfplan ]]; then
        info "Applying saved plan…"
        terraform apply tfplan
    else
        info "Running terraform apply…"
        terraform apply
    fi
    ok "Fauxterprise environment deployed"
    echo ""
    info "Next steps:"
    info "  1. Run:  azure-rbac build -o fauxterprise-graph.json"
    info "  2. Run:  azure-rbac analyze -g fauxterprise-graph.json"
    info "  3. When done:  ./deploy.sh destroy"
}

cmd_destroy() {
    check_prereqs
    echo ""
    warn "This will DESTROY all Fauxterprise resources."
    read -rp "Type 'yes' to confirm: " confirm
    if [[ "$confirm" != "yes" ]]; then
        info "Aborted."
        exit 0
    fi
    terraform destroy
    ok "All resources destroyed"
}

cmd_output() {
    terraform output -json
}

cmd_fixture() {
    info "Generating fixture.json from Terraform definitions…"
    python3 "$SCRIPT_DIR/generate_fixture.py" -o "$SCRIPT_DIR/fixture.json"
    ok "Fixture written to $SCRIPT_DIR/fixture.json"
    echo ""
    info "Test locally with:"
    info "  azure-rbac build --fixture fauxterprise/fixture.json -o graph.json"
    info "  azure-rbac analyze -g graph.json"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 {init|plan|apply|destroy|output|fixture}"
    exit 1
fi

case "$1" in
    init)    cmd_init ;;
    plan)    cmd_plan ;;
    apply)   cmd_apply ;;
    destroy) cmd_destroy ;;
    output)  cmd_output ;;
    fixture) cmd_fixture ;;
    *)
        error "Unknown command: $1"
        echo "Usage: $0 {init|plan|apply|destroy|output|fixture}"
        exit 1
        ;;
esac
