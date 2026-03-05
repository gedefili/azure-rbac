# ---------------------------------------------------------------------------
# Azure RBAC Permission Graph – Azure Container Apps Deployment
# ---------------------------------------------------------------------------
# This Terraform configuration deploys the full infrastructure for running
# the Azure RBAC Permission Graph tool on Azure Container Apps:
#
#   • Resource Group
#   • Log Analytics Workspace
#   • Azure Container Registry (ACR)
#   • Storage Account with lifecycle policy
#   • Key Vault (RBAC-based access)
#   • User-Assigned Managed Identity with RBAC assignments
#   • Container App Environment
#   • Container App (dashboard web app)
#   • Container App Job (nightly graph builder)
#
# Usage:
#   cp terraform.tfvars.example terraform.tfvars   # edit with your values
#   terraform init
#   terraform plan
#   terraform apply
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Uncomment to use a remote backend (recommended for teams):
  # backend "azurerm" {
  #   resource_group_name  = "rg-terraform-state"
  #   storage_account_name = "sttfstate<suffix>"
  #   container_name       = "tfstate"
  #   key                  = "azure-rbac.tfstate"
  # }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }

  subscription_id = var.subscription_id
}

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

data "azurerm_client_config" "current" {}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "rbac" {
  name     = "rg-rbac-${var.environment}"
  location = var.location

  tags = var.tags
}
