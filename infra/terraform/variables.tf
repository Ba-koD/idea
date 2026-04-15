variable "environment_name" {
  description = "Logical name for this platform installation target."
  type        = string
  default     = "platform"
}

variable "target_name" {
  description = "Inventory alias for the target host."
  type        = string
  default     = "idea-platform-host"

  validation {
    condition     = can(regex("^[0-9A-Za-z._-]+$", var.target_name))
    error_message = "target_name may contain only letters, digits, dot, underscore, and hyphen."
  }
}

variable "target_host" {
  description = "Public IP or DNS name for the On-Prem install target."
  type        = string

  validation {
    condition     = trimspace(var.target_host) != ""
    error_message = "target_host must not be empty."
  }
}

variable "target_port" {
  description = "SSH port for the target host."
  type        = number
  default     = 22

  validation {
    condition     = var.target_port > 0 && var.target_port < 65536
    error_message = "target_port must be a valid TCP port."
  }
}

variable "target_user" {
  description = "SSH user used by Ansible."
  type        = string
  default     = "ubuntu"
}

variable "target_become" {
  description = "Whether Ansible should request privilege escalation for the target host."
  type        = bool
  default     = true
}

variable "platform_container_runtime" {
  description = "Container runtime to install. MVP currently supports Docker."
  type        = string
  default     = "docker"

  validation {
    condition     = contains(["docker"], var.platform_container_runtime)
    error_message = "MVP currently supports only docker."
  }
}

variable "idea_base_domain" {
  description = "Base domain reserved for the platform and future app routing."
  type        = string
  default     = "idea.local"
}

variable "kind_cluster_name" {
  description = "Kind cluster name."
  type        = string
  default     = "idea"
}

variable "kind_node_image" {
  description = "Kind node image."
  type        = string
  default     = "kindest/node:v1.33.4"
}

variable "kind_version" {
  description = "Kind binary version."
  type        = string
  default     = "v0.23.0"
}

variable "kubectl_version" {
  description = "kubectl binary version."
  type        = string
  default     = "v1.33.4"
}

variable "helm_version" {
  description = "Helm binary version."
  type        = string
  default     = "v3.15.4"
}

variable "argocd_version" {
  description = "Argo CD version tag used for manifest install."
  type        = string
  default     = "v2.11.7"
}

variable "enable_monitoring" {
  description = "Whether to install kube-prometheus-stack."
  type        = bool
  default     = true
}

variable "enable_vault" {
  description = "Whether to install Vault dev mode as the MVP secret store."
  type        = bool
  default     = true
}

variable "enable_cloudflared" {
  description = "Whether to install the cloudflared execution base."
  type        = bool
  default     = false
}

variable "enable_cloudflare_reconciliation" {
  description = "Whether to create and reconcile Cloudflare Tunnel, DNS, and WAF policy via the Cloudflare API."
  type        = bool
  default     = false
}

variable "cloudflared_tunnel_token" {
  description = "Cloudflare tunnel token for manual tunnel mode. Required only when enable_cloudflared is true and API reconciliation is disabled."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "Scoped Cloudflare API token used for tunnel, DNS, and WAF reconciliation."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID used for tunnel reconciliation."
  type        = string
  default     = ""
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID used for DNS and WAF reconciliation."
  type        = string
  default     = ""
}

variable "cloudflare_public_subdomain" {
  description = "Public hostname prefix published through Cloudflare Tunnel."
  type        = string
  default     = "idea"
}

variable "cloudflare_argocd_subdomain" {
  description = "Public hostname prefix used for the Argo CD UI through Cloudflare Tunnel."
  type        = string
  default     = "argo"
}

variable "cloudflare_tunnel_name" {
  description = "Human-readable Cloudflare Tunnel name."
  type        = string
  default     = "idea-platform"
}

variable "cloudflare_admin_allowed_ips" {
  description = "List of administrator source IPs or CIDRs that may access the public idea hostname."
  type        = list(string)
  default     = []
}

variable "platform_caddy_backend_base_path" {
  description = "Base path routed to the idea backend through platform Caddy."
  type        = string
  default     = "/api"
}

variable "idea_namespace" {
  description = "Namespace for the idea platform workloads."
  type        = string
  default     = "idea-system"
}

variable "edge_namespace" {
  description = "Namespace for platform edge workloads."
  type        = string
  default     = "edge-system"
}

variable "monitoring_namespace" {
  description = "Namespace for monitoring workloads."
  type        = string
  default     = "monitoring"
}

variable "data_namespace" {
  description = "Namespace for internal data services."
  type        = string
  default     = "idea-data"
}

variable "vault_namespace" {
  description = "Namespace for Vault."
  type        = string
  default     = "vault"
}

variable "postgresql_password" {
  description = "Password for the internal PostgreSQL instance."
  type        = string
  default     = "change-me-postgres"
  sensitive   = true
}

variable "vault_dev_root_token" {
  description = "Root token for Vault dev mode."
  type        = string
  default     = "change-me-root"
  sensitive   = true
}

variable "app_repo_token" {
  description = "Platform control-plane fallback token for the app repository."
  type        = string
  default     = ""
  sensitive   = true
}

variable "gitops_repo_token" {
  description = "Platform control-plane fallback token for the GitOps repository."
  type        = string
  default     = ""
  sensitive   = true
}
