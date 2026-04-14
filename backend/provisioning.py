from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

SUPPORTED_NCLOUD_CLUSTER_VERSIONS: tuple[str, ...] = ("1.33.4", "1.34.3", "1.32.8")
DEFAULT_NCLOUD_CLUSTER_VERSION = "1.33.4"
DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV: dict[str, str] = {
    "dev": "s2-g3a",
    "stage": "s2-g3a",
    "prod": "s4-g3a",
}
DEFAULT_PLATFORM_CADDY_SERVICE_URL = os.getenv(
    "IDEA_PLATFORM_CADDY_SERVICE_URL",
    "http://platform-caddy.edge-system.svc.cluster.local:80",
)
DEFAULT_CLOUDFLARE_API_BASE_URL = "https://api.cloudflare.com/client/v4"

TERRAFORM_VERSIONS_TF = dedent(
    """
    terraform {
      required_version = ">= 1.6.0"

      required_providers {
        ncloud = {
          source = "NaverCloudPlatform/ncloud"
        }
      }
    }
    """
).strip() + "\n"


TERRAFORM_VARIABLES_TF = dedent(
    """
    variable "site" { type = string }
    variable "region" { type = string }
    variable "zone" { type = string }
    variable "project_name" { type = string }
    variable "environment_name" { type = string }

    variable "cluster_name" { type = string }
    variable "existing_cluster_uuid" { type = string }
    variable "cluster_version" { type = string }
    variable "cluster_type_code" { type = string }
    variable "hypervisor_code" { type = string }
    variable "login_key_name" { type = string }

    variable "existing_vpc_no" { type = string }
    variable "existing_node_subnet_no" { type = string }
    variable "existing_lb_private_subnet_no" { type = string }
    variable "existing_lb_public_subnet_no" { type = string }
    variable "existing_node_pool_id" { type = string }

    variable "vpc_name" { type = string }
    variable "vpc_cidr" { type = string }
    variable "node_subnet_name" { type = string }
    variable "node_subnet_cidr" { type = string }
    variable "lb_private_subnet_name" { type = string }
    variable "lb_private_subnet_cidr" { type = string }
    variable "lb_public_subnet_name" { type = string }
    variable "lb_public_subnet_cidr" { type = string }

    variable "node_pool_name" { type = string }
    variable "node_count" { type = number }
    variable "node_server_spec_code" { type = string }
    variable "node_image_label" { type = string }
    variable "node_storage_size_gb" { type = number }
    variable "autoscale_enabled" { type = bool }
    variable "autoscale_min" { type = number }
    variable "autoscale_max" { type = number }
    """
).strip() + "\n"


TERRAFORM_MAIN_TF = dedent(
    """
    provider "ncloud" {
      region      = var.region
      site        = var.site
      support_vpc = true
    }

    locals {
      use_existing_cluster           = trimspace(var.existing_cluster_uuid) != ""
      use_existing_vpc               = !local.use_existing_cluster && trimspace(var.existing_vpc_no) != "" && can(regex("^[0-9]+$", var.existing_vpc_no))
      use_existing_node_subnet       = !local.use_existing_cluster && trimspace(var.existing_node_subnet_no) != "" && can(regex("^[0-9]+$", var.existing_node_subnet_no))
      use_existing_lb_private_subnet = !local.use_existing_cluster && trimspace(var.existing_lb_private_subnet_no) != "" && can(regex("^[0-9]+$", var.existing_lb_private_subnet_no))
      use_existing_lb_public_subnet  = !local.use_existing_cluster && trimspace(var.existing_lb_public_subnet_no) != "" && can(regex("^[0-9]+$", var.existing_lb_public_subnet_no))
      use_existing_node_pool         = trimspace(var.existing_node_pool_id) != ""
      has_existing_login_key         = try(length(data.ncloud_login_key.existing.login_key_list), 0) > 0
      create_login_key               = !local.use_existing_cluster && !local.has_existing_login_key
    }

    data "ncloud_login_key" "existing" {
      filter {
        name   = "key_name"
        values = [var.login_key_name]
      }
    }

    resource "ncloud_login_key" "managed" {
      count    = local.create_login_key ? 1 : 0
      key_name = var.login_key_name
    }

    resource "terraform_data" "preflight" {
      lifecycle {
        precondition {
          condition     = trimspace(var.login_key_name) != ""
          error_message = "login_key_name must be non-empty before cluster provisioning can run."
        }
      }
    }

    data "ncloud_vpc" "existing" {
      count = local.use_existing_vpc ? 1 : 0
      id    = var.existing_vpc_no
    }

    resource "ncloud_vpc" "managed" {
      count           = local.use_existing_cluster || local.use_existing_vpc ? 0 : 1
      name            = var.vpc_name
      ipv4_cidr_block = var.vpc_cidr
    }

    locals {
      vpc_no         = local.use_existing_cluster ? data.ncloud_nks_cluster.existing[0].vpc_no : (local.use_existing_vpc ? data.ncloud_vpc.existing[0].id : ncloud_vpc.managed[0].id)
      network_acl_no = local.use_existing_cluster ? "" : (local.use_existing_vpc ? data.ncloud_vpc.existing[0].default_network_acl_no : ncloud_vpc.managed[0].default_network_acl_no)
    }

    data "ncloud_subnet" "existing_node" {
      count = local.use_existing_node_subnet ? 1 : 0
      id    = var.existing_node_subnet_no
    }

    resource "ncloud_subnet" "node" {
      count          = local.use_existing_cluster || local.use_existing_node_subnet ? 0 : 1
      vpc_no         = local.vpc_no
      subnet         = var.node_subnet_cidr
      zone           = var.zone
      network_acl_no = local.network_acl_no
      subnet_type    = "PRIVATE"
      name           = var.node_subnet_name
      usage_type     = "GEN"
    }

    data "ncloud_subnet" "existing_lb_private" {
      count = local.use_existing_lb_private_subnet ? 1 : 0
      id    = var.existing_lb_private_subnet_no
    }

    resource "ncloud_subnet" "lb_private" {
      count          = local.use_existing_cluster || local.use_existing_lb_private_subnet ? 0 : 1
      vpc_no         = local.vpc_no
      subnet         = var.lb_private_subnet_cidr
      zone           = var.zone
      network_acl_no = local.network_acl_no
      subnet_type    = "PRIVATE"
      name           = var.lb_private_subnet_name
      usage_type     = "LOADB"
    }

    data "ncloud_subnet" "existing_lb_public" {
      count = local.use_existing_lb_public_subnet ? 1 : 0
      id    = var.existing_lb_public_subnet_no
    }

    resource "ncloud_subnet" "lb_public" {
      count          = local.use_existing_cluster || local.use_existing_lb_public_subnet ? 0 : 1
      vpc_no         = local.vpc_no
      subnet         = var.lb_public_subnet_cidr
      zone           = var.zone
      network_acl_no = local.network_acl_no
      subnet_type    = "PUBLIC"
      name           = var.lb_public_subnet_name
      usage_type     = "LOADB"
    }

    locals {
      node_subnet_no       = local.use_existing_cluster ? try(data.ncloud_nks_cluster.existing[0].subnet_no_list[0], "") : (local.use_existing_node_subnet ? data.ncloud_subnet.existing_node[0].id : ncloud_subnet.node[0].id)
      lb_private_subnet_no = local.use_existing_cluster ? data.ncloud_nks_cluster.existing[0].lb_private_subnet_no : (local.use_existing_lb_private_subnet ? data.ncloud_subnet.existing_lb_private[0].id : ncloud_subnet.lb_private[0].id)
      lb_public_subnet_no  = local.use_existing_cluster ? try(data.ncloud_nks_cluster.existing[0].lb_public_subnet_no, "") : (local.use_existing_lb_public_subnet ? data.ncloud_subnet.existing_lb_public[0].id : ncloud_subnet.lb_public[0].id)
      effective_login_key_name = local.use_existing_cluster ? "" : (local.create_login_key ? ncloud_login_key.managed[0].key_name : var.login_key_name)
    }

    data "ncloud_nks_versions" "cluster_version" {
      hypervisor_code = var.hypervisor_code

      filter {
        name   = "value"
        values = [var.cluster_version]
        regex  = true
      }
    }

    data "ncloud_nks_server_images" "node_image" {
      hypervisor_code = var.hypervisor_code

      filter {
        name   = "label"
        values = [var.node_image_label]
        regex  = true
      }
    }

    data "ncloud_nks_cluster" "existing" {
      count = local.use_existing_cluster ? 1 : 0
      uuid  = var.existing_cluster_uuid
    }

    resource "ncloud_nks_cluster" "cluster" {
      count                 = local.use_existing_cluster ? 0 : 1
      name                  = var.cluster_name
      hypervisor_code       = var.hypervisor_code
      cluster_type          = var.cluster_type_code
      k8s_version           = data.ncloud_nks_versions.cluster_version.versions[0].value
      login_key_name        = local.effective_login_key_name
      zone                  = var.zone
      vpc_no                = local.vpc_no
      subnet_no_list        = [local.node_subnet_no]
      lb_private_subnet_no  = local.lb_private_subnet_no
      lb_public_subnet_no   = local.lb_public_subnet_no != "" ? local.lb_public_subnet_no : null
      kube_network_plugin   = "cilium"
      public_network        = false
      return_protection     = false

      depends_on = [terraform_data.preflight, ncloud_login_key.managed]
    }

    locals {
      cluster_uuid     = local.use_existing_cluster ? data.ncloud_nks_cluster.existing[0].uuid : ncloud_nks_cluster.cluster[0].uuid
      cluster_endpoint = local.use_existing_cluster ? data.ncloud_nks_cluster.existing[0].endpoint : ncloud_nks_cluster.cluster[0].endpoint
    }

    resource "ncloud_nks_node_pool" "node_pool" {
      count            = local.use_existing_node_pool ? 0 : 1
      cluster_uuid     = local.cluster_uuid
      node_pool_name   = var.node_pool_name
      node_count       = var.node_count
      software_code    = data.ncloud_nks_server_images.node_image.images[0].value
      server_spec_code = var.node_server_spec_code
      storage_size     = var.node_storage_size_gb
      subnet_no_list   = [local.node_subnet_no]

      autoscale {
        enabled = var.autoscale_enabled
        min     = var.autoscale_min
        max     = var.autoscale_max
      }
    }

    data "ncloud_nks_kube_config" "cluster" {
      cluster_uuid = local.cluster_uuid
    }
    """
).strip() + "\n"


TERRAFORM_OUTPUTS_TF = dedent(
    """
    output "vpc_no" {
      value = local.vpc_no
    }

    output "node_subnet_no" {
      value = local.node_subnet_no
    }

    output "lb_private_subnet_no" {
      value = local.lb_private_subnet_no
    }

    output "lb_public_subnet_no" {
      value = local.lb_public_subnet_no
    }

    output "cluster_uuid" {
      value = local.cluster_uuid
    }

    output "cluster_endpoint" {
      value = local.cluster_endpoint
    }

    output "node_pool_id" {
      value = local.use_existing_node_pool ? var.existing_node_pool_id : try(ncloud_nks_node_pool.node_pool[0].id, "")
    }

    output "managed_login_private_key" {
      sensitive = true
      value = try(ncloud_login_key.managed[0].private_key, "")
    }

    output "kubeconfig" {
      sensitive = true
      value = {
        host                   = data.ncloud_nks_kube_config.cluster.host
        client_certificate     = data.ncloud_nks_kube_config.cluster.client_certificate
        client_key             = data.ncloud_nks_kube_config.cluster.client_key
        cluster_ca_certificate = data.ncloud_nks_kube_config.cluster.cluster_ca_certificate
      }
    }
    """
).strip() + "\n"


def normalize_secret_ref_name(name: str) -> str:
    lowered = str(name or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered)
    return normalized.strip("-")


def secret_env_var_name(secret_ref: str) -> str:
    normalized = normalize_secret_ref_name(secret_ref).replace("-", "_").upper()
    return f"IDEA_SECRET_{normalized}"


def looks_like_resource_id(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9]+", str(value or "").strip()))


def looks_like_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return not text or text.startswith("replace-me") or text in {"changeme", "change-me", "placeholder", "todo"}


def normalize_resource_name(value: Any, fallback: str, max_length: int) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raw = fallback.strip().lower()
    normalized = re.sub(r"[^a-z0-9-]+", "-", raw)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if len(normalized) > max_length:
        normalized = normalized[:max_length].rstrip("-")
    return normalized or fallback[:max_length].strip("-")


def normalize_node_server_spec_code(value: Any, selected_env: str) -> str:
    default = DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV.get(selected_env, "s2-g3a")
    text = str(value or "").strip()
    if looks_like_placeholder(text):
        return default
    if text.upper().startswith("SVR."):
        return default
    return text


class ProvisioningPartialFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        next_state: dict[str, Any],
        runtime_dir: str,
        logs: list[str],
        partial_outputs: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.next_state = next_state
        self.runtime_dir = runtime_dir
        self.logs = logs
        self.partial_outputs = partial_outputs or {}
        self.warnings = warnings or []


def run_command(
    command: list[str],
    workdir: Path,
    env: dict[str, str],
    log_callback: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    if log_callback is None:
        return subprocess.run(
            command,
            cwd=str(workdir),
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )

    process = subprocess.Popen(
        command,
        cwd=str(workdir),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output_lines: list[str] = []
    log_callback(f"$ {' '.join(command)}")

    assert process.stdout is not None
    for line in process.stdout:
        cleaned = line.rstrip()
        output_lines.append(line)
        if cleaned:
            log_callback(cleaned)

    returncode = process.wait()
    return subprocess.CompletedProcess(command, returncode, stdout="".join(output_lines), stderr="")


def resolve_secret_value(project_state: dict[str, Any], secret_ref: str) -> str:
    normalized_ref = normalize_secret_ref_name(secret_ref)
    secret_values = project_state.get("provisioning", {}).get("secret_values", {})
    if normalized_ref in secret_values and str(secret_values[normalized_ref]).strip():
        return str(secret_values[normalized_ref]).strip()

    env_name = secret_env_var_name(secret_ref)
    if os.getenv(env_name):
        return os.environ[env_name].strip()

    fallback_env_name = normalize_secret_ref_name(secret_ref).replace("-", "_").upper()
    if os.getenv(fallback_env_name):
        return os.environ[fallback_env_name].strip()

    return ""


def render_kubeconfig(cluster_name: str, kubeconfig: dict[str, str]) -> str:
    return dedent(
        f"""
        apiVersion: v1
        kind: Config
        clusters:
          - cluster:
              server: {kubeconfig['host']}
              certificate-authority-data: {kubeconfig['cluster_ca_certificate']}
            name: {cluster_name}
        contexts:
          - context:
              cluster: {cluster_name}
              user: {cluster_name}
            name: {cluster_name}
        current-context: {cluster_name}
        users:
          - name: {cluster_name}
            user:
              client-certificate-data: {kubeconfig['client_certificate']}
              client-key-data: {kubeconfig['client_key']}
        """
    ).strip() + "\n"


def render_argocd_cluster_secret(cluster_name: str, cluster_endpoint: str, kubeconfig: dict[str, str], selected_env: str) -> str:
    config = {
        "tlsClientConfig": {
            "insecure": False,
            "caData": kubeconfig["cluster_ca_certificate"],
            "certData": kubeconfig["client_certificate"],
            "keyData": kubeconfig["client_key"],
        }
    }
    return dedent(
        f"""
        apiVersion: v1
        kind: Secret
        metadata:
          name: argocd-cluster-{selected_env}-{cluster_name}
          namespace: argocd
          labels:
            argocd.argoproj.io/secret-type: cluster
        type: Opaque
        stringData:
          name: {cluster_name}
          server: {cluster_endpoint}
          config: |
        """
    ).strip() + "\n" + "\n".join(f"            {line}" for line in json.dumps(config, indent=2).splitlines()) + "\n"


def preferred_base_domain(project_state: dict[str, Any]) -> str:
    environments = project_state.get("cloudflare", {}).get("environments", {})
    for env_name in ("prod", "stage", "dev"):
        base_domain = str(environments.get(env_name, {}).get("base_domain", "")).strip().lower()
        if base_domain:
            return base_domain
    return ""


def normalize_argocd_access_hint(project_state: dict[str, Any]) -> str:
    base_domain = preferred_base_domain(project_state) or "rnen.kr"
    desired_hint = f"https://argo.{base_domain}"
    raw_hint = str(project_state.get("argo", {}).get("access_hint", "")).strip()

    if not raw_hint:
        return desired_hint

    parsed = urlparse(raw_hint if "://" in raw_hint else f"https://{raw_hint}")
    if parsed.hostname:
        return f"{parsed.scheme or 'https'}://{parsed.hostname}"

    return desired_hint


def argocd_hostname(project_state: dict[str, Any]) -> str:
    parsed = urlparse(normalize_argocd_access_hint(project_state))
    return parsed.hostname or ""


def http_json_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}

    if body is not None and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"

    request = Request(url, data=payload, headers=request_headers, method=method)

    try:
        with urlopen(request, context=ssl_context) as response:
            raw_body = response.read()
            status = response.status
    except HTTPError as exc:
        raw_body = exc.read()
        status = exc.code
        if status not in expected_statuses:
            detail = raw_body.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{method} {url} failed with {status}: {detail}") from exc

    parsed_body: Any = None
    if raw_body:
        text = raw_body.decode("utf-8", errors="replace")
        try:
            parsed_body = json.loads(text)
        except json.JSONDecodeError:
            parsed_body = text

    if status not in expected_statuses:
        raise RuntimeError(f"{method} {url} returned unexpected status {status}.")

    return {"status": status, "body": parsed_body}


def load_incluster_platform_context() -> tuple[str, dict[str, str], ssl.SSLContext]:
    token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    ca_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
    host = os.getenv("KUBERNETES_SERVICE_HOST", "").strip()
    port = os.getenv("KUBERNETES_SERVICE_PORT", "443").strip()

    if not token_path.exists() or not host:
        raise RuntimeError("Backend is not running with in-cluster Kubernetes credentials.")

    ssl_context = ssl.create_default_context(cafile=str(ca_path)) if ca_path.exists() else ssl.create_default_context()
    return (
        f"https://{host}:{port}",
        {"Authorization": f"Bearer {token_path.read_text(encoding='utf-8').strip()}"},
        ssl_context,
    )


def kube_api_request(
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    api_server, api_headers, ssl_context = load_incluster_platform_context()
    return http_json_request(
        f"{api_server}{path}",
        method=method,
        headers={**api_headers, **(headers or {})},
        body=body,
        expected_statuses=expected_statuses,
        ssl_context=ssl_context,
    )


def build_argocd_cluster_secret_manifest(
    cluster_name: str,
    cluster_endpoint: str,
    kubeconfig: dict[str, str],
    selected_env: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": f"argocd-cluster-{selected_env}-{cluster_name}",
            "namespace": "argocd",
            "labels": {
                "argocd.argoproj.io/secret-type": "cluster",
                "app.kubernetes.io/managed-by": "idea-platform",
            },
        },
        "type": "Opaque",
        "stringData": {
            "name": cluster_name,
            "server": cluster_endpoint,
            "config": json.dumps(
                {
                    "tlsClientConfig": {
                        "insecure": False,
                        "caData": kubeconfig["cluster_ca_certificate"],
                        "certData": kubeconfig["client_certificate"],
                        "keyData": kubeconfig["client_key"],
                    }
                },
                indent=2,
            ),
        },
    }


def apply_argocd_cluster_secret_to_platform(
    cluster_name: str,
    cluster_endpoint: str,
    kubeconfig: dict[str, str],
    selected_env: str,
) -> dict[str, Any]:
    manifest = build_argocd_cluster_secret_manifest(cluster_name, cluster_endpoint, kubeconfig, selected_env)
    secret_name = manifest["metadata"]["name"]
    secret_path = f"/api/v1/namespaces/argocd/secrets/{quote(secret_name, safe='')}"
    existing = kube_api_request(secret_path, expected_statuses=(200, 404))

    if existing["status"] == 404:
        kube_api_request(
            "/api/v1/namespaces/argocd/secrets",
            method="POST",
            body=manifest,
            expected_statuses=(201,),
        )
        action = "created"
    else:
        kube_api_request(
            secret_path,
            method="PATCH",
            body=manifest,
            expected_statuses=(200,),
            headers={"Content-Type": "application/merge-patch+json"},
        )
        action = "updated"

    return {
        "applied": True,
        "secret_name": secret_name,
        "action": action,
        "logs": [f"Argo CD cluster secret {secret_name} {action} in the platform cluster."],
    }


def cloudflare_api_request(
    api_token: str,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
) -> dict[str, Any]:
    response = http_json_request(
        f"{DEFAULT_CLOUDFLARE_API_BASE_URL}{path}",
        method=method,
        headers={"Authorization": f"Bearer {api_token}"},
        body=body,
        expected_statuses=expected_statuses,
    )
    payload = response["body"]
    if isinstance(payload, dict) and payload.get("success") is False:
        errors = payload.get("errors") or []
        error_text = "; ".join(str(item.get("message") or item) for item in errors) or "Cloudflare API request failed."
        raise RuntimeError(error_text)
    return response


def upsert_cloudflare_dns_record(api_token: str, zone_id: str, hostname: str, tunnel_id: str) -> list[str]:
    logs: list[str] = []
    target = f"{tunnel_id}.cfargotunnel.com"
    lookup = cloudflare_api_request(
        api_token,
        f"/zones/{zone_id}/dns_records?type=CNAME&name={quote(hostname, safe='')}",
    )
    existing_record = ((lookup["body"] or {}).get("result") or [{}])[0]

    if not existing_record or not existing_record.get("id"):
        cloudflare_api_request(
            api_token,
            f"/zones/{zone_id}/dns_records",
            method="POST",
            body={
                "type": "CNAME",
                "proxied": True,
                "name": hostname,
                "content": target,
            },
        )
        logs.append(f"Created Cloudflare DNS record for {hostname}.")
        return logs

    if existing_record.get("content") != target or not bool(existing_record.get("proxied")):
        cloudflare_api_request(
            api_token,
            f"/zones/{zone_id}/dns_records/{existing_record['id']}",
            method="PUT",
            body={
                "type": "CNAME",
                "proxied": True,
                "name": hostname,
                "content": target,
            },
        )
        logs.append(f"Updated Cloudflare DNS record for {hostname}.")
        return logs

    logs.append(f"Cloudflare DNS record for {hostname} already matched the active tunnel.")
    return logs


def reconcile_cloudflare_waf_allowlist(api_token: str, zone_id: str, hostname: str, allowed_ips: list[str]) -> list[str]:
    if not allowed_ips:
        return ["Skipped Cloudflare WAF reconciliation because no admin allowlist IPs were configured."]

    logs: list[str] = []
    expression = f'(http.host eq "{hostname}") and not ip.src in {{ {" ".join(allowed_ips)} }}'
    ref = "idea-platform-argocd-admin-allowlist"
    description = "Managed by idea platform for Argo CD admin IP restriction"

    entrypoint = cloudflare_api_request(
        api_token,
        f"/zones/{zone_id}/rulesets/phases/http_request_firewall_custom/entrypoint",
        expected_statuses=(200, 404),
    )

    if entrypoint["status"] == 404:
        cloudflare_api_request(
            api_token,
            f"/zones/{zone_id}/rulesets",
            method="POST",
            body={
                "name": "Zone-level phase entry point",
                "description": "Managed by idea platform for admin IP restriction",
                "kind": "zone",
                "phase": "http_request_firewall_custom",
                "rules": [
                    {
                        "ref": ref,
                        "description": description,
                        "expression": expression,
                        "action": "block",
                        "enabled": True,
                    }
                ],
            },
        )
        logs.append(f"Created Cloudflare WAF entrypoint with admin allowlist rule for {hostname}.")
        return logs

    result = (entrypoint["body"] or {}).get("result") or {}
    ruleset_id = result.get("id", "")
    existing_rule = next((rule for rule in result.get("rules", []) if rule.get("ref") == ref), None)

    if not existing_rule:
        cloudflare_api_request(
            api_token,
            f"/zones/{zone_id}/rulesets/{ruleset_id}/rules",
            method="POST",
            body={
                "ref": ref,
                "description": description,
                "expression": expression,
                "action": "block",
                "enabled": True,
            },
        )
        logs.append(f"Created Cloudflare WAF admin allowlist rule for {hostname}.")
        return logs

    needs_update = (
        existing_rule.get("expression") != expression
        or existing_rule.get("action") != "block"
        or not bool(existing_rule.get("enabled", True))
    )
    if needs_update:
        cloudflare_api_request(
            api_token,
            f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{existing_rule['id']}",
            method="PATCH",
            body={
                "ref": ref,
                "description": description,
                "expression": expression,
                "action": "block",
                "enabled": True,
            },
        )
        logs.append(f"Updated Cloudflare WAF admin allowlist rule for {hostname}.")
        return logs

    logs.append(f"Cloudflare WAF admin allowlist already matched {hostname}.")
    return logs


def reconcile_cloudflare_argocd_access(project_state: dict[str, Any]) -> dict[str, Any]:
    cloudflare = project_state.get("cloudflare", {})
    if not cloudflare.get("enabled", True):
        return {"applied": False, "warnings": ["Skipped Cloudflare reconciliation because Cloudflare is disabled."], "logs": []}

    api_token = resolve_secret_value(project_state, cloudflare.get("api_token_secret_ref", ""))
    account_id = str(cloudflare.get("account_id", "")).strip()
    zone_id = str(cloudflare.get("zone_id", "")).strip()
    tunnel_name = str(cloudflare.get("tunnel_name", "")).strip()
    hostname = argocd_hostname(project_state)

    missing = []
    if looks_like_placeholder(api_token):
        missing.append("IDEA_CLOUDFLARE_API_TOKEN_VALUE")
    if not account_id:
        missing.append("IDEA_CLOUDFLARE_ACCOUNT_ID")
    if not zone_id:
        missing.append("IDEA_CLOUDFLARE_ZONE_ID")
    if not tunnel_name:
        missing.append("IDEA_CLOUDFLARE_TUNNEL_NAME")
    if not hostname:
        missing.append("IDEA_ARGO_ACCESS_HINT")
    if missing:
        return {
            "applied": False,
            "warnings": ["Skipped Cloudflare reconciliation because required values were missing: " + ", ".join(missing)],
            "logs": [],
        }

    tunnels_response = cloudflare_api_request(api_token, f"/accounts/{account_id}/cfd_tunnel")
    tunnel = next(
        (item for item in (tunnels_response["body"] or {}).get("result", []) if item.get("name") == tunnel_name),
        None,
    )
    if not tunnel:
        return {
            "applied": False,
            "warnings": [
                f"Skipped Cloudflare reconciliation because tunnel {tunnel_name!r} was not found. "
                "Import a real IDEA_CLOUDFLARE_TUNNEL_NAME or keep the platform tunnel name."
            ],
            "logs": [],
        }

    tunnel_id = str(tunnel.get("id", "")).strip()
    if not tunnel_id:
        return {"applied": False, "warnings": [f"Tunnel {tunnel_name!r} did not return a tunnel id."], "logs": []}

    config_response = cloudflare_api_request(
        api_token,
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
        expected_statuses=(200, 404),
    )
    result_payload = (config_response["body"] or {}).get("result") or {}
    existing_config = result_payload.get("config") or result_payload or {}
    existing_ingress = existing_config.get("ingress") or []
    hostname_rules = [rule for rule in existing_ingress if isinstance(rule, dict) and rule.get("hostname")]
    fallback_rule = next(
        (rule for rule in existing_ingress if isinstance(rule, dict) and rule.get("service") and not rule.get("hostname")),
        {"service": "http_status:404"},
    )

    updated_rules: list[dict[str, Any]] = []
    hostname_present = False
    for rule in hostname_rules:
        if rule.get("hostname") == hostname:
            hostname_present = True
            updated_rules.append(
                {
                    "hostname": hostname,
                    "service": DEFAULT_PLATFORM_CADDY_SERVICE_URL,
                    "originRequest": rule.get("originRequest", {}),
                }
            )
        else:
            updated_rules.append(rule)

    if not hostname_present:
        updated_rules.append(
            {
                "hostname": hostname,
                "service": DEFAULT_PLATFORM_CADDY_SERVICE_URL,
                "originRequest": {},
            }
        )

    updated_config = {key: value for key, value in existing_config.items() if key != "ingress"}
    updated_config["ingress"] = updated_rules + [fallback_rule]
    cloudflare_api_request(
        api_token,
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
        method="PUT",
        body={"config": updated_config},
    )

    logs = [f"Cloudflare tunnel {tunnel_name} now routes {hostname} to {DEFAULT_PLATFORM_CADDY_SERVICE_URL}."]
    logs.extend(upsert_cloudflare_dns_record(api_token, zone_id, hostname, tunnel_id))
    logs.extend(
        reconcile_cloudflare_waf_allowlist(
            api_token,
            zone_id,
            hostname,
            [item.strip() for item in project_state.get("access", {}).get("admin_allowed_source_ips", []) if str(item).strip()],
        )
    )
    return {
        "applied": True,
        "warnings": [],
        "logs": logs,
        "hostname": hostname,
        "tunnel_id": tunnel_id,
    }


def extract_terraform_output(raw_output: str) -> dict[str, Any]:
    payload = json.loads(raw_output)
    return {key: value.get("value") for key, value in payload.items()}


def state_output_value(state_payload: dict[str, Any], output_name: str) -> Any:
    output = state_payload.get("outputs", {}).get(output_name)
    if isinstance(output, dict):
        return output.get("value")
    return None


def read_terraform_state(runtime_dir: Path) -> dict[str, Any]:
    state_path = runtime_dir / "terraform.tfstate"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def runtime_state_has_managed_resources(runtime_dir: Path) -> bool:
    state_payload = read_terraform_state(runtime_dir)
    destroyable_resource_types = {
        "ncloud_vpc",
        "ncloud_subnet",
        "ncloud_nks_cluster",
        "ncloud_nks_node_pool",
        "ncloud_login_key",
    }
    for resource in state_payload.get("resources", []):
        if resource.get("mode", "managed") != "managed":
            continue
        if resource.get("type") not in destroyable_resource_types:
            continue
        if resource.get("instances"):
            return True
    return False


def first_resource_attributes(state_payload: dict[str, Any], resource_type: str, resource_name: str) -> dict[str, Any]:
    for resource in state_payload.get("resources", []):
        if resource.get("type") != resource_type or resource.get("name") != resource_name:
            continue
        for instance in resource.get("instances", []):
            attributes = instance.get("attributes") or {}
            if attributes:
                return attributes
    return {}


def extract_partial_runtime_outputs(runtime_dir: Path) -> dict[str, Any]:
    state_payload = read_terraform_state(runtime_dir)
    cluster_attrs = first_resource_attributes(state_payload, "ncloud_nks_cluster", "cluster")
    vpc_attrs = first_resource_attributes(state_payload, "ncloud_vpc", "managed")
    node_attrs = first_resource_attributes(state_payload, "ncloud_subnet", "node")
    lb_private_attrs = first_resource_attributes(state_payload, "ncloud_subnet", "lb_private")
    lb_public_attrs = first_resource_attributes(state_payload, "ncloud_subnet", "lb_public")
    node_pool_attrs = first_resource_attributes(state_payload, "ncloud_nks_node_pool", "node_pool")
    login_key_attrs = first_resource_attributes(state_payload, "ncloud_login_key", "managed")
    kubeconfig_attrs = first_resource_attributes(state_payload, "ncloud_nks_kube_config", "cluster")

    partial_outputs: dict[str, Any] = {}
    cluster_uuid = state_output_value(state_payload, "cluster_uuid") or cluster_attrs.get("uuid")
    cluster_endpoint = state_output_value(state_payload, "cluster_endpoint") or cluster_attrs.get("endpoint", "")
    vpc_no = state_output_value(state_payload, "vpc_no") or cluster_attrs.get("vpc_no") or vpc_attrs.get("id") or vpc_attrs.get("vpc_no") or ""
    node_subnet_no = (
        state_output_value(state_payload, "node_subnet_no")
        or (cluster_attrs.get("subnet_no_list") or [""])[0]
        or node_attrs.get("id")
        or node_attrs.get("subnet_no")
        or ""
    )
    lb_private_subnet_no = (
        state_output_value(state_payload, "lb_private_subnet_no")
        or cluster_attrs.get("lb_private_subnet_no")
        or lb_private_attrs.get("id")
        or lb_private_attrs.get("subnet_no")
        or ""
    )
    lb_public_subnet_no = (
        state_output_value(state_payload, "lb_public_subnet_no")
        or cluster_attrs.get("lb_public_subnet_no")
        or lb_public_attrs.get("id")
        or lb_public_attrs.get("subnet_no")
        or ""
    )
    node_pool_id = state_output_value(state_payload, "node_pool_id") or node_pool_attrs.get("id") or ""

    if cluster_uuid:
        partial_outputs["cluster_uuid"] = cluster_uuid
    if cluster_endpoint:
        partial_outputs["cluster_endpoint"] = cluster_endpoint
    if vpc_no:
        partial_outputs["vpc_no"] = vpc_no
    if node_subnet_no:
        partial_outputs["node_subnet_no"] = node_subnet_no
    if lb_private_subnet_no:
        partial_outputs["lb_private_subnet_no"] = lb_private_subnet_no
    if lb_public_subnet_no:
        partial_outputs["lb_public_subnet_no"] = lb_public_subnet_no
    if node_pool_id:
        partial_outputs["node_pool_id"] = node_pool_id

    kubeconfig_output = state_output_value(state_payload, "kubeconfig")
    if isinstance(kubeconfig_output, dict) and kubeconfig_output.get("host"):
        partial_outputs["kubeconfig"] = kubeconfig_output
    elif kubeconfig_attrs.get("host"):
        partial_outputs["kubeconfig"] = {
            "host": kubeconfig_attrs.get("host", ""),
            "client_certificate": kubeconfig_attrs.get("client_certificate", ""),
            "client_key": kubeconfig_attrs.get("client_key", ""),
            "cluster_ca_certificate": kubeconfig_attrs.get("cluster_ca_certificate", ""),
        }

    if login_key_attrs.get("private_key"):
        partial_outputs["managed_login_private_key"] = login_key_attrs.get("private_key", "")

    return partial_outputs


def write_runtime_artifacts_from_outputs(
    runtime_dir: Path,
    cluster_name: str,
    login_key_name: str,
    selected_env: str,
    outputs: dict[str, Any],
) -> None:
    kubeconfig = outputs.get("kubeconfig")
    if isinstance(kubeconfig, dict) and kubeconfig.get("host"):
        (runtime_dir / "kubeconfig.yaml").write_text(
            render_kubeconfig(cluster_name, kubeconfig),
            encoding="utf-8",
        )
        cluster_endpoint = str(outputs.get("cluster_endpoint", "") or "").strip()
        if cluster_endpoint:
            (runtime_dir / "argocd-cluster-secret.yaml").write_text(
                render_argocd_cluster_secret(cluster_name, cluster_endpoint, kubeconfig, selected_env),
                encoding="utf-8",
            )

    managed_login_private_key = str(outputs.get("managed_login_private_key", "") or "").strip()
    if managed_login_private_key:
        managed_login_key_path = runtime_dir / f"{login_key_name}.pem"
        managed_login_key_path.write_text(managed_login_private_key.rstrip() + "\n", encoding="utf-8")
        managed_login_key_path.chmod(0o600)


def apply_partial_outputs_to_state(state: dict[str, Any], selected_env: str, partial_outputs: dict[str, Any]) -> None:
    ncloud = state["targets"][selected_env]["ncloud"]
    if partial_outputs.get("cluster_uuid"):
        ncloud["cluster_uuid"] = partial_outputs.get("cluster_uuid", "")
    if partial_outputs.get("cluster_endpoint"):
        ncloud["cluster_endpoint"] = partial_outputs.get("cluster_endpoint", "")
    if partial_outputs.get("vpc_no"):
        ncloud["vpc_no"] = partial_outputs.get("vpc_no", "")
    if partial_outputs.get("node_subnet_no"):
        ncloud["subnet_no"] = partial_outputs.get("node_subnet_no", "")
    if partial_outputs.get("lb_private_subnet_no"):
        ncloud["lb_subnet_no"] = partial_outputs.get("lb_private_subnet_no", "")
    if partial_outputs.get("lb_public_subnet_no"):
        ncloud["lb_public_subnet_no"] = partial_outputs.get("lb_public_subnet_no", "")
    if partial_outputs.get("node_pool_id"):
        ncloud["node_pool_id"] = partial_outputs.get("node_pool_id", "")


def read_runtime_tfvars(runtime_dir: Path) -> dict[str, Any]:
    tfvars_path = runtime_dir / "terraform.tfvars.json"
    if not tfvars_path.exists():
        return {}
    try:
        return json.loads(tfvars_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def recover_state_from_runtime_artifacts(
    state: dict[str, Any],
    selected_env: str,
    output_root: Path,
    log_callback: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime_dir = ensure_runtime_dir(output_root, state["project"]["name"], selected_env)
    saved_tfvars = read_runtime_tfvars(runtime_dir)
    desired_cluster_name = str(state["targets"][selected_env]["ncloud"].get("cluster_name") or "").strip()

    if saved_tfvars and desired_cluster_name and saved_tfvars.get("cluster_name") != desired_cluster_name:
        return state, {}

    recovered = extract_partial_runtime_outputs(runtime_dir)
    if not recovered:
        return state, {}

    ncloud = state["targets"][selected_env]["ncloud"]
    changed = False

    if recovered.get("cluster_uuid") and not looks_like_uuid(ncloud.get("cluster_uuid")):
        changed = True
    if recovered.get("vpc_no") and not looks_like_resource_id(ncloud.get("vpc_no")):
        changed = True
    if recovered.get("node_subnet_no") and not looks_like_resource_id(ncloud.get("subnet_no")):
        changed = True
    if recovered.get("lb_private_subnet_no") and not looks_like_resource_id(ncloud.get("lb_subnet_no")):
        changed = True
    if recovered.get("lb_public_subnet_no") and not looks_like_resource_id(ncloud.get("lb_public_subnet_no")):
        changed = True
    if recovered.get("node_pool_id") and looks_like_placeholder(ncloud.get("node_pool_id")):
        changed = True
    if recovered.get("cluster_endpoint") and looks_like_placeholder(ncloud.get("cluster_endpoint")):
        changed = True

    if not changed:
        return state, recovered

    apply_partial_outputs_to_state(state, selected_env, recovered)
    if recovered.get("cluster_endpoint"):
        state["argo"]["destination_server"] = recovered.get("cluster_endpoint", "")
    if log_callback is not None:
        log_callback(
            "Recovered existing Ncloud runtime ids from the saved terraform state before apply. "
            f"cluster_uuid={recovered.get('cluster_uuid', '') or '(unknown)'}"
        )
    return state, recovered


def build_runtime_tfvars(project_state: dict[str, Any], selected_env: str) -> dict[str, Any]:
    project = project_state["project"]
    target = project_state["targets"][selected_env]
    ncloud = target["ncloud"]
    cluster_name = ncloud.get("cluster_name") or f"{project['name']}-{selected_env}"
    node_server_spec_code = normalize_node_server_spec_code(
        ncloud.get("node_server_spec_code") or ncloud.get("node_product_code"),
        selected_env,
    )

    return {
        "site": project_state.get("provisioning", {}).get("site", "public"),
        "region": ncloud.get("region_code", "KR"),
        "zone": ncloud.get("zone_code", "KR-2"),
        "project_name": project["name"],
        "environment_name": selected_env,
        "cluster_name": cluster_name,
        "existing_cluster_uuid": ncloud.get("cluster_uuid") if looks_like_uuid(ncloud.get("cluster_uuid")) else "",
        "cluster_version": ncloud.get("cluster_version", DEFAULT_NCLOUD_CLUSTER_VERSION),
        "cluster_type_code": ncloud.get("cluster_type_code", "SVR.VNKS.STAND.C004.M016.G003"),
        "hypervisor_code": ncloud.get("hypervisor_code", "KVM"),
        "login_key_name": ncloud.get("login_key_name", "idea-runtime-login"),
        "existing_vpc_no": ncloud.get("vpc_no") if looks_like_resource_id(ncloud.get("vpc_no")) else "",
        "existing_node_subnet_no": ncloud.get("subnet_no") if looks_like_resource_id(ncloud.get("subnet_no")) else "",
        "existing_lb_private_subnet_no": ncloud.get("lb_subnet_no") if looks_like_resource_id(ncloud.get("lb_subnet_no")) else "",
        "existing_lb_public_subnet_no": ncloud.get("lb_public_subnet_no") if looks_like_resource_id(ncloud.get("lb_public_subnet_no")) else "",
        "existing_node_pool_id": ncloud.get("node_pool_id") if not looks_like_placeholder(ncloud.get("node_pool_id")) else "",
        "vpc_name": normalize_resource_name(ncloud.get("vpc_name"), f"{cluster_name}-vpc", 30),
        "vpc_cidr": ncloud.get("vpc_cidr", "10.10.0.0/16"),
        "node_subnet_name": normalize_resource_name(ncloud.get("node_subnet_name"), f"{cluster_name}-node", 30),
        "node_subnet_cidr": ncloud.get("node_subnet_cidr", "10.10.1.0/24"),
        "lb_private_subnet_name": normalize_resource_name(ncloud.get("lb_private_subnet_name"), f"{cluster_name}-lbpri", 30),
        "lb_private_subnet_cidr": ncloud.get("lb_private_subnet_cidr", "10.10.10.0/24"),
        "lb_public_subnet_name": normalize_resource_name(ncloud.get("lb_public_subnet_name"), f"{cluster_name}-lbpub", 30),
        "lb_public_subnet_cidr": ncloud.get("lb_public_subnet_cidr", "10.10.11.0/24"),
        "node_pool_name": normalize_resource_name(ncloud.get("node_pool_name"), f"{cluster_name}-pool", 20),
        "node_count": int(ncloud.get("node_count", 2)),
        "node_server_spec_code": node_server_spec_code,
        "node_image_label": ncloud.get("node_image_label", "ubuntu-22.04"),
        "node_storage_size_gb": int(ncloud.get("block_storage_size_gb", 50)),
        "autoscale_enabled": bool(ncloud.get("autoscale_enabled", True)),
        "autoscale_min": int(ncloud.get("autoscale_min_node_count", 1)),
        "autoscale_max": int(ncloud.get("autoscale_max_node_count", max(int(ncloud.get("node_count", 2)), 1))),
}


def looks_like_uuid(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F-]{36}", str(value or "").strip()))


def validate_ncloud_preflight(
    tfvars: dict[str, Any],
    access_key_ref: str,
    access_key: str,
    secret_key_ref: str,
    secret_key: str,
) -> None:
    errors: list[str] = []

    if tfvars["cluster_version"] not in SUPPORTED_NCLOUD_CLUSTER_VERSIONS:
        errors.append(
            "cluster_version must be one of "
            + ", ".join(SUPPORTED_NCLOUD_CLUSTER_VERSIONS)
            + f" (got {tfvars['cluster_version']!r})."
        )

    if looks_like_placeholder(tfvars["login_key_name"]):
        errors.append("login_key_name must be non-empty before provisioning can run.")

    if looks_like_placeholder(access_key):
        errors.append(
            f"Ncloud access key value for {access_key_ref!r} is missing or still a placeholder. "
            "Fill IDEA_NCLOUD_ACCESS_KEY_VALUE before provisioning."
        )

    if looks_like_placeholder(secret_key):
        errors.append(
            f"Ncloud secret key value for {secret_key_ref!r} is missing or still a placeholder. "
            "Fill IDEA_NCLOUD_SECRET_KEY_VALUE before provisioning."
        )

    if errors:
        raise ValueError("Ncloud provisioning preflight failed:\n- " + "\n- ".join(errors))


def ensure_runtime_dir(output_root: Path, project_name: str, selected_env: str) -> Path:
    runtime_dir = output_root / project_name / selected_env / "ncloud-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def ensure_clean_runtime_dir(output_root: Path, project_name: str, selected_env: str, directory_name: str) -> Path:
    runtime_dir = output_root / project_name / selected_env / directory_name
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def write_runtime_terraform_files(runtime_dir: Path, tfvars: dict[str, Any]) -> None:
    (runtime_dir / "versions.tf").write_text(TERRAFORM_VERSIONS_TF, encoding="utf-8")
    (runtime_dir / "variables.tf").write_text(TERRAFORM_VARIABLES_TF, encoding="utf-8")
    (runtime_dir / "main.tf").write_text(TERRAFORM_MAIN_TF, encoding="utf-8")
    (runtime_dir / "outputs.tf").write_text(TERRAFORM_OUTPUTS_TF, encoding="utf-8")
    (runtime_dir / "terraform.tfvars.json").write_text(
        json.dumps(tfvars, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def reset_ncloud_target_runtime_state(state: dict[str, Any], selected_env: str) -> None:
    ncloud = state["targets"][selected_env]["ncloud"]
    ncloud["cluster_uuid"] = ""
    ncloud["cluster_endpoint"] = ""
    ncloud["vpc_no"] = f"vpc-{selected_env}"
    ncloud["subnet_no"] = f"subnet-{selected_env}"
    ncloud["lb_subnet_no"] = f"lb-subnet-{selected_env}"
    ncloud["lb_public_subnet_no"] = ""
    ncloud["node_pool_id"] = ""
    state["argo"]["destination_server"] = "https://kubernetes.default.svc"


def remove_runtime_artifacts(runtime_dir: Path, login_key_name: str) -> None:
    for file_name in ("kubeconfig.yaml", "argocd-cluster-secret.yaml", "terraform.tfplan"):
        target = runtime_dir / file_name
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass
    login_key_path = runtime_dir / f"{login_key_name}.pem"
    if login_key_path.exists():
        try:
            login_key_path.unlink()
        except OSError:
            pass


def remove_runtime_state_files(runtime_dir: Path) -> None:
    for file_name in ("terraform.tfstate", "terraform.tfstate.backup"):
        target = runtime_dir / file_name
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass

    terraform_dir = runtime_dir / ".terraform"
    if terraform_dir.exists():
        shutil.rmtree(terraform_dir, ignore_errors=True)


def build_destroy_import_tfvars(project_state: dict[str, Any], selected_env: str) -> dict[str, Any]:
    tfvars = build_runtime_tfvars(project_state, selected_env)
    tfvars["existing_cluster_uuid"] = ""
    tfvars["existing_vpc_no"] = ""
    tfvars["existing_node_subnet_no"] = ""
    tfvars["existing_lb_private_subnet_no"] = ""
    tfvars["existing_lb_public_subnet_no"] = ""
    tfvars["existing_node_pool_id"] = ""
    return tfvars


def build_destroy_import_targets(project_state: dict[str, Any], selected_env: str) -> list[tuple[str, str]]:
    ncloud = project_state["targets"][selected_env]["ncloud"]
    targets: list[tuple[str, str]] = []

    vpc_no = str(ncloud.get("vpc_no", "")).strip()
    if looks_like_resource_id(vpc_no):
        targets.append(("ncloud_vpc.managed[0]", vpc_no))

    node_subnet_no = str(ncloud.get("subnet_no", "")).strip()
    if looks_like_resource_id(node_subnet_no):
        targets.append(("ncloud_subnet.node[0]", node_subnet_no))

    lb_private_subnet_no = str(ncloud.get("lb_subnet_no", "")).strip()
    if looks_like_resource_id(lb_private_subnet_no):
        targets.append(("ncloud_subnet.lb_private[0]", lb_private_subnet_no))

    lb_public_subnet_no = str(ncloud.get("lb_public_subnet_no", "")).strip()
    if looks_like_resource_id(lb_public_subnet_no):
        targets.append(("ncloud_subnet.lb_public[0]", lb_public_subnet_no))

    cluster_uuid = str(ncloud.get("cluster_uuid", "")).strip()
    if looks_like_uuid(cluster_uuid):
        targets.append(("ncloud_nks_cluster.cluster[0]", cluster_uuid))

    node_pool_id = str(ncloud.get("node_pool_id", "")).strip()
    if node_pool_id and not looks_like_placeholder(node_pool_id):
        targets.append(("ncloud_nks_node_pool.node_pool[0]", node_pool_id))

    return targets


def validate_destroy_import_targets(project_state: dict[str, Any], selected_env: str) -> list[tuple[str, str]]:
    ncloud = project_state["targets"][selected_env]["ncloud"]
    required_fields = {
        "cluster_uuid": looks_like_uuid(ncloud.get("cluster_uuid")),
        "vpc_no": looks_like_resource_id(ncloud.get("vpc_no")),
        "subnet_no": looks_like_resource_id(ncloud.get("subnet_no")),
        "lb_subnet_no": looks_like_resource_id(ncloud.get("lb_subnet_no")),
        "node_pool_id": bool(str(ncloud.get("node_pool_id", "")).strip() and not looks_like_placeholder(ncloud.get("node_pool_id"))),
    }
    missing = [field_name for field_name, is_present in required_fields.items() if not is_present]
    if missing:
        raise ValueError(
            "Destroy needs the current Ncloud target ids so it can import the live resources into a temporary "
            "Terraform state before deletion. Fill these fields first or re-run provision successfully: "
            + ", ".join(missing)
        )
    return build_destroy_import_targets(project_state, selected_env)


def import_existing_destroy_targets(
    runtime_dir: Path,
    terraform_bin: str,
    command_env: dict[str, str],
    import_targets: list[tuple[str, str]],
    log_callback: Callable[[str], None] | None = None,
) -> None:
    for resource_address, resource_id in import_targets:
        result = run_command(
            [terraform_bin, "import", resource_address, resource_id],
            runtime_dir,
            command_env,
            log_callback=log_callback,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"terraform import failed for {resource_address} ({resource_id}):\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )


def delete_argocd_cluster_secret_from_platform(cluster_name: str, selected_env: str) -> dict[str, Any]:
    secret_name = f"argocd-cluster-{selected_env}-{cluster_name}"
    secret_path = f"/api/v1/namespaces/argocd/secrets/{quote(secret_name, safe='')}"
    existing = kube_api_request(secret_path, expected_statuses=(200, 404))

    if existing["status"] == 404:
        return {
            "applied": False,
            "secret_name": secret_name,
            "action": "noop",
            "logs": [f"Argo CD cluster secret {secret_name} was already absent from the platform cluster."],
        }

    kube_api_request(secret_path, method="DELETE", expected_statuses=(200, 202))
    return {
        "applied": True,
        "secret_name": secret_name,
        "action": "deleted",
        "logs": [f"Argo CD cluster secret {secret_name} deleted from the platform cluster."],
    }


def provision_ncloud_target(
    project_state: dict[str, Any],
    selected_env: str,
    output_root: Path,
    apply: bool = True,
    log_callback: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = deepcopy(project_state)
    project = state["project"]
    target = state["targets"][selected_env]
    if target.get("provider") != "ncloud" or target.get("cluster_type") != "nks":
        raise ValueError("Only provider=ncloud and cluster_type=nks are supported by runtime provisioning.")

    ncloud = target["ncloud"]
    access_key_ref = ncloud.get("access_key_secret_ref", "")
    secret_key_ref = ncloud.get("secret_key_secret_ref", "")
    access_key = resolve_secret_value(state, access_key_ref)
    secret_key = resolve_secret_value(state, secret_key_ref)
    missing_refs: list[dict[str, str]] = []

    if not access_key:
        missing_refs.append({"ref": access_key_ref, "env": secret_env_var_name(access_key_ref)})
    if not secret_key:
        missing_refs.append({"ref": secret_key_ref, "env": secret_env_var_name(secret_key_ref)})

    if missing_refs:
        raise ValueError(
            "Missing provisioning secret values for: "
            + ", ".join(f"{item['ref']} (env {item['env']})" for item in missing_refs)
        )

    logs: list[str] = []

    def emit(message: str) -> None:
        logs.append(message)
        if log_callback is not None:
            log_callback(message)

    state, recovered_runtime_outputs = recover_state_from_runtime_artifacts(state, selected_env, output_root, log_callback=emit)
    tfvars = build_runtime_tfvars(state, selected_env)
    validate_ncloud_preflight(tfvars, access_key_ref, access_key, secret_key_ref, secret_key)
    runtime_dir = ensure_runtime_dir(output_root, project["name"], selected_env)
    write_runtime_terraform_files(runtime_dir, tfvars)
    state["targets"][selected_env]["ncloud"]["node_product_code"] = tfvars["node_server_spec_code"]

    terraform_bin = state.get("provisioning", {}).get("terraform_executable", "terraform")
    command_env = {
        **os.environ,
        "NCLOUD_ACCESS_KEY": access_key,
        "NCLOUD_SECRET_KEY": secret_key,
        "NCLOUD_REGION": tfvars["region"],
        "TF_IN_AUTOMATION": "1",
    }

    emit(f"Prepared Terraform runtime in {runtime_dir}.")
    if recovered_runtime_outputs:
        emit(
            "Provisioning reused runtime artifacts from the previous successful state. "
            f"node_pool_id={recovered_runtime_outputs.get('node_pool_id', '') or '(create new)'}."
        )
    emit(f"Ncloud target cluster_name={tfvars['cluster_name']} zone={tfvars['zone']} region={tfvars['region']}.")
    emit(f"Existing cluster_uuid={tfvars['existing_cluster_uuid'] or '(create new)'} vpc_no={tfvars['existing_vpc_no'] or '(create new)'}.")
    emit(f"Ncloud node server spec={tfvars['node_server_spec_code']} node_count={tfvars['node_count']}.")
    emit("Running terraform init.")

    init_result = run_command([terraform_bin, "init", "-backend=false"], runtime_dir, command_env, log_callback=log_callback)
    if init_result.returncode != 0:
        raise RuntimeError(f"terraform init failed:\n{init_result.stderr.strip() or init_result.stdout.strip()}")
    emit("terraform init completed.")

    emit("Running terraform validate.")
    validate_result = run_command([terraform_bin, "validate"], runtime_dir, command_env, log_callback=log_callback)
    if validate_result.returncode != 0:
        raise RuntimeError(f"terraform validate failed:\n{validate_result.stderr.strip() or validate_result.stdout.strip()}")
    emit("terraform validate completed.")

    if not apply:
        return state, {
            "applied": False,
            "runtime_dir": str(runtime_dir),
            "logs": logs,
            "tfvars": tfvars,
        }

    emit("Running terraform apply.")
    apply_result = run_command([terraform_bin, "apply", "-auto-approve"], runtime_dir, command_env, log_callback=log_callback)
    if apply_result.returncode != 0:
        partial_outputs = extract_partial_runtime_outputs(runtime_dir)
        if partial_outputs.get("cluster_uuid"):
            apply_partial_outputs_to_state(state, selected_env, partial_outputs)
            write_runtime_artifacts_from_outputs(
                runtime_dir,
                tfvars["cluster_name"],
                tfvars["login_key_name"],
                selected_env,
                partial_outputs,
            )
            emit(
                "Terraform apply failed after partial resource creation. "
                f"Recovered cluster_uuid={partial_outputs.get('cluster_uuid')} for retry."
            )
            raise ProvisioningPartialFailure(
                "terraform apply failed after partial resource creation. "
                f"Recovered cluster_uuid={partial_outputs.get('cluster_uuid')} and saved it to project state. "
                "Fix the node server spec and retry provisioning.",
                next_state=state,
                runtime_dir=str(runtime_dir),
                logs=logs,
                partial_outputs=partial_outputs,
                warnings=["Partial Ncloud resources were created and saved to project state for retry."],
            )
        raise RuntimeError(f"terraform apply failed:\n{apply_result.stderr.strip() or apply_result.stdout.strip()}")
    emit("terraform apply completed.")

    emit("Collecting terraform outputs.")
    output_result = run_command([terraform_bin, "output", "-json"], runtime_dir, command_env, log_callback=log_callback)
    if output_result.returncode != 0:
        raise RuntimeError(f"terraform output failed:\n{output_result.stderr.strip() or output_result.stdout.strip()}")

    outputs = extract_terraform_output(output_result.stdout)
    kubeconfig = outputs["kubeconfig"]
    write_runtime_artifacts_from_outputs(
        runtime_dir,
        tfvars["cluster_name"],
        tfvars["login_key_name"],
        selected_env,
        outputs,
    )
    kubeconfig_path = runtime_dir / "kubeconfig.yaml"
    argocd_cluster_secret_path = runtime_dir / "argocd-cluster-secret.yaml"
    managed_login_private_key = str(outputs.get("managed_login_private_key", "") or "").strip()
    managed_login_key_path = runtime_dir / f"{tfvars['login_key_name']}.pem"

    integration_logs: list[str] = []
    integration_warnings: list[str] = []

    try:
        platform_argocd_result = apply_argocd_cluster_secret_to_platform(
            tfvars["cluster_name"],
            outputs["cluster_endpoint"],
            kubeconfig,
            selected_env,
        )
        integration_logs.extend(platform_argocd_result["logs"])
    except Exception as exc:
        integration_warnings.append(
            "Automatic Argo CD cluster registration did not complete. "
            f"Reason: {exc}"
        )

    try:
        cloudflare_result = reconcile_cloudflare_argocd_access(state)
        integration_logs.extend(cloudflare_result.get("logs", []))
        integration_warnings.extend(cloudflare_result.get("warnings", []))
    except Exception as exc:
        integration_warnings.append(
            "Automatic Cloudflare Argo CD routing did not complete. "
            f"Reason: {exc}"
        )

    next_ncloud = state["targets"][selected_env]["ncloud"]
    next_ncloud["cluster_uuid"] = outputs["cluster_uuid"]
    next_ncloud["cluster_endpoint"] = outputs["cluster_endpoint"]
    next_ncloud["vpc_no"] = outputs["vpc_no"]
    next_ncloud["subnet_no"] = outputs["node_subnet_no"]
    next_ncloud["lb_subnet_no"] = outputs["lb_private_subnet_no"]
    next_ncloud["lb_public_subnet_no"] = outputs["lb_public_subnet_no"]
    next_ncloud["node_pool_id"] = outputs["node_pool_id"]
    next_ncloud["login_key_name"] = tfvars["login_key_name"]
    state["argo"]["destination_name"] = ""
    state["argo"]["destination_server"] = outputs["cluster_endpoint"]
    state["argo"]["access_hint"] = normalize_argocd_access_hint(state)
    state.setdefault("provisioning", {}).setdefault("last_results", {})[selected_env] = {
        "status": "provisioned",
        "operation": "apply",
        "provisioned": True,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "runtime_dir": str(runtime_dir),
        "kubeconfig_path": str(kubeconfig_path),
        "argocd_cluster_secret_path": str(argocd_cluster_secret_path),
        "managed_login_key_path": str(managed_login_key_path) if managed_login_private_key else "",
        "cluster_uuid": outputs["cluster_uuid"],
        "cluster_endpoint": outputs["cluster_endpoint"],
        "integration_logs": integration_logs,
        "integration_warnings": integration_warnings,
        "logs_tail": logs[-80:],
    }

    emit(f"Wrote kubeconfig to {kubeconfig_path}.")
    if managed_login_private_key:
        emit(f"Wrote generated Ncloud login key to {managed_login_key_path}.")
    emit(f"Wrote Argo CD cluster secret manifest to {argocd_cluster_secret_path}.")
    for message in integration_logs:
        emit(message)
    for warning in integration_warnings:
        emit(f"WARNING: {warning}")

    return state, {
        "applied": True,
        "runtime_dir": str(runtime_dir),
        "kubeconfig_path": str(kubeconfig_path),
        "argocd_cluster_secret_path": str(argocd_cluster_secret_path),
        "managed_login_key_path": str(managed_login_key_path) if managed_login_private_key else "",
        "logs": logs,
        "outputs": outputs,
        "warnings": integration_warnings,
    }


def destroy_ncloud_target(
    project_state: dict[str, Any],
    selected_env: str,
    output_root: Path,
    apply: bool = True,
    log_callback: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = deepcopy(project_state)
    project = state["project"]
    target = state["targets"][selected_env]
    if target.get("provider") != "ncloud" or target.get("cluster_type") != "nks":
        raise ValueError("Only provider=ncloud and cluster_type=nks are supported by runtime destroy.")

    runtime_dir = ensure_runtime_dir(output_root, project["name"], selected_env)
    state, _ = recover_state_from_runtime_artifacts(state, selected_env, output_root, log_callback=log_callback)

    ncloud = state["targets"][selected_env]["ncloud"]
    access_key_ref = ncloud.get("access_key_secret_ref", "")
    secret_key_ref = ncloud.get("secret_key_secret_ref", "")
    access_key = resolve_secret_value(state, access_key_ref)
    secret_key = resolve_secret_value(state, secret_key_ref)
    missing_refs: list[dict[str, str]] = []

    if not access_key:
        missing_refs.append({"ref": access_key_ref, "env": secret_env_var_name(access_key_ref)})
    if not secret_key:
        missing_refs.append({"ref": secret_key_ref, "env": secret_env_var_name(secret_key_ref)})
    if missing_refs:
        raise ValueError(
            "Missing provisioning secret values for: "
            + ", ".join(f"{item['ref']} (env {item['env']})" for item in missing_refs)
        )

    import_targets: list[tuple[str, str]] = []
    destroy_runtime_dir = runtime_dir
    using_import_destroy_state = False
    if runtime_state_has_managed_resources(runtime_dir):
        tfvars = build_runtime_tfvars(state, selected_env)
    else:
        import_targets = validate_destroy_import_targets(state, selected_env)
        tfvars = build_destroy_import_tfvars(state, selected_env)
        destroy_runtime_dir = ensure_clean_runtime_dir(output_root, project["name"], selected_env, "ncloud-destroy-runtime")
        using_import_destroy_state = True
    validate_ncloud_preflight(tfvars, access_key_ref, access_key, secret_key_ref, secret_key)
    write_runtime_terraform_files(destroy_runtime_dir, tfvars)

    command_env = {
        **os.environ,
        "NCLOUD_ACCESS_KEY": access_key,
        "NCLOUD_SECRET_KEY": secret_key,
        "NCLOUD_REGION": tfvars["region"],
        "TF_IN_AUTOMATION": "1",
    }
    terraform_bin = state.get("provisioning", {}).get("terraform_executable", "terraform")
    logs: list[str] = []

    def emit(message: str) -> None:
        logs.append(message)
        if log_callback is not None:
            log_callback(message)

    emit(f"Prepared Terraform runtime in {destroy_runtime_dir}.")
    emit(
        f"Destroying Ncloud target cluster_name={tfvars['cluster_name']} "
        f"cluster_uuid={tfvars['existing_cluster_uuid'] or '(tracked state)'}."
    )
    emit("Running terraform init.")
    init_result = run_command([terraform_bin, "init", "-backend=false"], destroy_runtime_dir, command_env, log_callback=log_callback)
    if init_result.returncode != 0:
        raise RuntimeError(f"terraform init failed:\n{init_result.stderr.strip() or init_result.stdout.strip()}")
    emit("terraform init completed.")

    emit("Running terraform validate.")
    validate_result = run_command([terraform_bin, "validate"], destroy_runtime_dir, command_env, log_callback=log_callback)
    if validate_result.returncode != 0:
        raise RuntimeError(f"terraform validate failed:\n{validate_result.stderr.strip() or validate_result.stdout.strip()}")
    emit("terraform validate completed.")

    if using_import_destroy_state:
        emit("Importing the current Ncloud resources into a temporary Terraform state for safe destroy.")
        import_existing_destroy_targets(
            destroy_runtime_dir,
            terraform_bin,
            command_env,
            import_targets,
            log_callback=log_callback,
        )
        emit("terraform import completed for the existing target resources.")

    if not apply:
        emit("Running terraform plan -destroy.")
        plan_result = run_command(
            [terraform_bin, "plan", "-destroy"],
            destroy_runtime_dir,
            command_env,
            log_callback=log_callback,
        )
        if plan_result.returncode != 0:
            raise RuntimeError(f"terraform plan -destroy failed:\n{plan_result.stderr.strip() or plan_result.stdout.strip()}")
        emit("terraform plan -destroy completed.")
        if using_import_destroy_state:
            shutil.rmtree(destroy_runtime_dir, ignore_errors=True)
        return state, {
            "applied": False,
            "destroyed": False,
            "runtime_dir": str(destroy_runtime_dir),
            "logs": logs,
            "warnings": [],
        }

    integration_logs: list[str] = []
    integration_warnings: list[str] = []
    emit("Running terraform destroy.")
    destroy_result = run_command(
        [terraform_bin, "destroy", "-auto-approve"],
        destroy_runtime_dir,
        command_env,
        log_callback=log_callback,
    )
    if destroy_result.returncode != 0:
        raise RuntimeError(f"terraform destroy failed:\n{destroy_result.stderr.strip() or destroy_result.stdout.strip()}")
    emit("terraform destroy completed.")

    try:
        platform_argocd_result = delete_argocd_cluster_secret_from_platform(
            tfvars["cluster_name"],
            selected_env,
        )
        integration_logs.extend(platform_argocd_result["logs"])
    except Exception as exc:
        integration_warnings.append(
            "Automatic Argo CD cluster deregistration did not complete. "
            f"Reason: {exc}"
        )

    remove_runtime_artifacts(runtime_dir, tfvars["login_key_name"])
    remove_runtime_state_files(runtime_dir)
    if using_import_destroy_state:
        shutil.rmtree(destroy_runtime_dir, ignore_errors=True)
    reset_ncloud_target_runtime_state(state, selected_env)
    state.setdefault("provisioning", {}).setdefault("last_results", {})[selected_env] = {
        "status": "destroyed",
        "operation": "destroy",
        "provisioned": False,
        "destroyed_at": datetime.now(timezone.utc).isoformat(),
        "runtime_dir": str(destroy_runtime_dir),
        "cluster_uuid": "",
        "cluster_endpoint": "",
        "integration_logs": integration_logs,
        "integration_warnings": integration_warnings,
        "logs_tail": logs[-80:],
    }
    for message in integration_logs:
        emit(message)
    for warning in integration_warnings:
        emit(f"WARNING: {warning}")

    return state, {
        "applied": True,
        "destroyed": True,
        "runtime_dir": str(destroy_runtime_dir),
        "logs": logs,
        "warnings": integration_warnings,
        "outputs": {
            "cluster_uuid": "",
            "cluster_endpoint": "",
        },
    }
