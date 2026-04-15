locals {
  install_summary = {
    environment_name                 = var.environment_name
    target_name                      = var.target_name
    target_host                      = var.target_host
    target_port                      = var.target_port
    target_user                      = var.target_user
    target_become                    = var.target_become
    idea_base_domain                 = var.idea_base_domain
    platform_container_runtime       = var.platform_container_runtime
    kind_cluster_name                = var.kind_cluster_name
    kind_node_image                  = var.kind_node_image
    kind_version                     = var.kind_version
    kubectl_version                  = var.kubectl_version
    helm_version                     = var.helm_version
    argocd_version                   = var.argocd_version
    enable_monitoring                = var.enable_monitoring
    enable_vault                     = var.enable_vault
    enable_cloudflared               = var.enable_cloudflared
    enable_cloudflare_reconciliation = var.enable_cloudflare_reconciliation
    cloudflare_public_subdomain      = var.cloudflare_public_subdomain
    cloudflare_argocd_subdomain      = var.cloudflare_argocd_subdomain
    cloudflare_tunnel_name           = var.cloudflare_tunnel_name
    platform_caddy_backend_path      = var.platform_caddy_backend_base_path
    namespaces = {
      idea       = var.idea_namespace
      edge       = var.edge_namespace
      monitoring = var.monitoring_namespace
      data       = var.data_namespace
      vault      = var.vault_namespace
    }
  }

  ansible_inventory_ini = templatefile("${path.module}/templates/inventory.ini.tftpl", {
    target_name   = var.target_name
    target_host   = var.target_host
    target_port   = var.target_port
    target_user   = var.target_user
    target_become = var.target_become
  })

  ansible_extra_vars = {
    platform_admin_user              = var.target_user
    platform_container_runtime       = var.platform_container_runtime
    idea_base_domain                 = var.idea_base_domain
    kind_cluster_name                = var.kind_cluster_name
    kind_node_image                  = var.kind_node_image
    kind_version                     = var.kind_version
    kubectl_version                  = var.kubectl_version
    helm_version                     = var.helm_version
    argocd_version                   = var.argocd_version
    enable_monitoring                = var.enable_monitoring
    enable_vault                     = var.enable_vault
    enable_cloudflared               = var.enable_cloudflared
    enable_cloudflare_reconciliation = var.enable_cloudflare_reconciliation
    cloudflared_tunnel_token         = var.cloudflared_tunnel_token
    cloudflare_api_token             = var.cloudflare_api_token
    cloudflare_account_id            = var.cloudflare_account_id
    cloudflare_zone_id               = var.cloudflare_zone_id
    cloudflare_public_subdomain      = var.cloudflare_public_subdomain
    cloudflare_argocd_subdomain      = var.cloudflare_argocd_subdomain
    cloudflare_tunnel_name           = var.cloudflare_tunnel_name
    cloudflare_admin_allowed_ips     = var.cloudflare_admin_allowed_ips
    platform_caddy_backend_base_path = var.platform_caddy_backend_base_path
    idea_namespace                   = var.idea_namespace
    edge_namespace                   = var.edge_namespace
    monitoring_namespace             = var.monitoring_namespace
    data_namespace                   = var.data_namespace
    vault_namespace                  = var.vault_namespace
    postgresql_password              = var.postgresql_password
    vault_dev_root_token             = var.vault_dev_root_token
    app_repo_token                   = var.app_repo_token
    gitops_repo_token                = var.gitops_repo_token
  }
}

resource "terraform_data" "platform_contract" {
  input = local.install_summary

  lifecycle {
    precondition {
      condition = (
        !var.enable_cloudflared ||
        var.enable_cloudflare_reconciliation ||
        trimspace(var.cloudflared_tunnel_token) != ""
      )
      error_message = "cloudflared_tunnel_token must be set when enable_cloudflared is true and Cloudflare API reconciliation is disabled."
    }

    precondition {
      condition = (
        !var.enable_cloudflare_reconciliation ||
        (
          var.enable_cloudflared &&
          trimspace(var.cloudflare_api_token) != "" &&
          trimspace(var.cloudflare_account_id) != "" &&
          trimspace(var.cloudflare_zone_id) != "" &&
          length(var.cloudflare_admin_allowed_ips) > 0
        )
      )
      error_message = "Cloudflare API reconciliation requires enable_cloudflared=true plus cloudflare_api_token, cloudflare_account_id, cloudflare_zone_id, and at least one cloudflare_admin_allowed_ips entry."
    }

    precondition {
      condition     = startswith(var.platform_caddy_backend_base_path, "/")
      error_message = "platform_caddy_backend_base_path must start with '/'."
    }
  }
}
