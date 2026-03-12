variable "prefix" {
  description = "Short prefix for all resource names (e.g. 'faux')"
  type        = string
  default     = "faux"
}

variable "domain" {
  description = "Azure AD verified domain used for user UPNs (e.g. contoso.onmicrosoft.com)"
  type        = string
  default     = "fauxterprise.onmicrosoft.com"
}

variable "primary_location" {
  description = "Primary Azure region"
  type        = string
  default     = "eastus2"
}

variable "secondary_location" {
  description = "Secondary Azure region for DR / multi-region resources"
  type        = string
  default     = "westus2"
}

variable "express_route_location" {
  description = "Peering location for the Express Route circuit"
  type        = string
  default     = "Washington DC"
}
