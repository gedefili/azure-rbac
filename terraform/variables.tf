# ---------------------------------------------------------------------------
# Input variables
# ---------------------------------------------------------------------------

variable "subscription_id" {
  description = "Azure subscription ID where resources will be created."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, stg, prd). Used in resource naming."
  type        = string
  default     = "prd"

  validation {
    condition     = contains(["dev", "stg", "prd"], var.environment)
    error_message = "environment must be one of: dev, stg, prd."
  }
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project    = "azure-rbac"
    managed_by = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Naming suffix (ensures globally unique names)
# ---------------------------------------------------------------------------

variable "name_suffix" {
  description = "Short alphanumeric suffix appended to globally unique names (storage, ACR, Key Vault). Example: '001'."
  type        = string
  default     = "001"
}

# ---------------------------------------------------------------------------
# Container image
# ---------------------------------------------------------------------------

variable "container_image_name" {
  description = "Name of the container image (without the registry prefix or tag)."
  type        = string
  default     = "azure-rbac"
}

variable "container_image_tag" {
  description = "Tag for the container image."
  type        = string
  default     = "latest"
}

# ---------------------------------------------------------------------------
# Dashboard Container App
# ---------------------------------------------------------------------------

variable "dashboard_min_replicas" {
  description = "Minimum number of dashboard replicas (set to 0 to scale to zero)."
  type        = number
  default     = 1
}

variable "dashboard_max_replicas" {
  description = "Maximum number of dashboard replicas."
  type        = number
  default     = 5
}

variable "dashboard_cpu" {
  description = "CPU cores allocated to each dashboard replica."
  type        = number
  default     = 0.5
}

variable "dashboard_memory" {
  description = "Memory (in Gi) allocated to each dashboard replica."
  type        = string
  default     = "1Gi"
}

# ---------------------------------------------------------------------------
# Graph builder job
# ---------------------------------------------------------------------------

variable "graph_builder_cron" {
  description = "Cron expression for the nightly graph builder job (UTC)."
  type        = string
  default     = "0 2 * * *"
}

variable "graph_builder_timeout" {
  description = "Maximum execution time (seconds) for a single graph builder run."
  type        = number
  default     = 3600
}

variable "graph_builder_cpu" {
  description = "CPU cores allocated to the graph builder job."
  type        = number
  default     = 1.0
}

variable "graph_builder_memory" {
  description = "Memory (in Gi) allocated to the graph builder job."
  type        = string
  default     = "2Gi"
}

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

variable "storage_replication" {
  description = "Storage account replication type."
  type        = string
  default     = "GRS"

  validation {
    condition     = contains(["LRS", "ZRS", "GRS", "RAGRS", "GZRS", "RAGZRS"], var.storage_replication)
    error_message = "storage_replication must be one of: LRS, ZRS, GRS, RAGRS, GZRS, RAGZRS."
  }
}

variable "snapshot_retention_days" {
  description = "Number of days to retain graph snapshots before automatic deletion."
  type        = number
  default     = 90
}

# ---------------------------------------------------------------------------
# Key Vault
# ---------------------------------------------------------------------------

variable "keyvault_soft_delete_retention_days" {
  description = "Number of days to retain soft-deleted Key Vault items."
  type        = number
  default     = 90
}

# ---------------------------------------------------------------------------
# Log Analytics
# ---------------------------------------------------------------------------

variable "log_retention_days" {
  description = "Number of days to retain logs in Log Analytics."
  type        = number
  default     = 30
}

# ---------------------------------------------------------------------------
# AI Foundry (optional – stored in Key Vault)
# ---------------------------------------------------------------------------

variable "ai_foundry_endpoint" {
  description = "Azure AI Foundry endpoint URL. Leave empty to skip."
  type        = string
  default     = ""
}

variable "ai_foundry_key" {
  description = "Azure AI Foundry API key. Leave empty to skip."
  type        = string
  default     = ""
  sensitive   = true
}

variable "ai_foundry_deployment" {
  description = "Model deployment name inside AI Foundry (e.g. gpt-4o)."
  type        = string
  default     = "gpt-4o"
}
