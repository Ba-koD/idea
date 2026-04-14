from __future__ import annotations

import json
import os
import re
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Any

SUPPORTED_NCLOUD_CLUSTER_VERSIONS: tuple[str, ...] = ("1.33.4", "1.34.3", "1.32.8")
DEFAULT_NCLOUD_CLUSTER_VERSION = "1.33.4"

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
      has_existing_login_key         = length(data.ncloud_login_key.existing.login_key_list) > 0
    }

    data "ncloud_login_key" "existing" {
      filter {
        name   = "key_name"
        values = [var.login_key_name]
      }
    }

    resource "terraform_data" "preflight" {
      lifecycle {
        precondition {
          condition     = local.use_existing_cluster || local.has_existing_login_key
          error_message = "login_key_name must point to an existing Ncloud login key before cluster provisioning can run."
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
      login_key_name        = var.login_key_name
      zone                  = var.zone
      vpc_no                = local.vpc_no
      subnet_no_list        = [local.node_subnet_no]
      lb_private_subnet_no  = local.lb_private_subnet_no
      lb_public_subnet_no   = local.lb_public_subnet_no != "" ? local.lb_public_subnet_no : null
      kube_network_plugin   = "cilium"
      public_network        = false
      return_protection     = false

      depends_on = [terraform_data.preflight]
    }

    locals {
      cluster_uuid     = local.use_existing_cluster ? data.ncloud_nks_cluster.existing[0].uuid : ncloud_nks_cluster.cluster[0].uuid
      cluster_endpoint = local.use_existing_cluster ? data.ncloud_nks_cluster.existing[0].endpoint : ncloud_nks_cluster.cluster[0].endpoint
    }

    resource "ncloud_nks_node_pool" "node_pool" {
      count            = local.use_existing_cluster ? 0 : 1
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
      value = try(ncloud_nks_node_pool.node_pool[0].id, "")
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


def run_command(command: list[str], workdir: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(workdir),
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


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


def extract_terraform_output(raw_output: str) -> dict[str, Any]:
    payload = json.loads(raw_output)
    return {key: value.get("value") for key, value in payload.items()}


def build_runtime_tfvars(project_state: dict[str, Any], selected_env: str) -> dict[str, Any]:
    project = project_state["project"]
    target = project_state["targets"][selected_env]
    ncloud = target["ncloud"]

    return {
        "site": project_state.get("provisioning", {}).get("site", "public"),
        "region": ncloud.get("region_code", "KR"),
        "zone": ncloud.get("zone_code", "KR-2"),
        "project_name": project["name"],
        "environment_name": selected_env,
        "cluster_name": ncloud.get("cluster_name") or f"{project['name']}-{selected_env}",
        "existing_cluster_uuid": ncloud.get("cluster_uuid") if looks_like_uuid(ncloud.get("cluster_uuid")) else "",
        "cluster_version": ncloud.get("cluster_version", DEFAULT_NCLOUD_CLUSTER_VERSION),
        "cluster_type_code": ncloud.get("cluster_type_code", "SVR.VNKS.STAND.C004.M016.G003"),
        "hypervisor_code": ncloud.get("hypervisor_code", "KVM"),
        "login_key_name": ncloud.get("login_key_name", "idea-runtime-login"),
        "existing_vpc_no": ncloud.get("vpc_no") if looks_like_resource_id(ncloud.get("vpc_no")) else "",
        "existing_node_subnet_no": ncloud.get("subnet_no") if looks_like_resource_id(ncloud.get("subnet_no")) else "",
        "existing_lb_private_subnet_no": ncloud.get("lb_subnet_no") if looks_like_resource_id(ncloud.get("lb_subnet_no")) else "",
        "existing_lb_public_subnet_no": ncloud.get("lb_public_subnet_no") if looks_like_resource_id(ncloud.get("lb_public_subnet_no")) else "",
        "vpc_name": f"{project['name']}-{selected_env}-vpc",
        "vpc_cidr": ncloud.get("vpc_cidr", "10.10.0.0/16"),
        "node_subnet_name": f"{project['name']}-{selected_env}-node",
        "node_subnet_cidr": ncloud.get("node_subnet_cidr", "10.10.1.0/24"),
        "lb_private_subnet_name": f"{project['name']}-{selected_env}-lb-private",
        "lb_private_subnet_cidr": ncloud.get("lb_private_subnet_cidr", "10.10.10.0/24"),
        "lb_public_subnet_name": f"{project['name']}-{selected_env}-lb-public",
        "lb_public_subnet_cidr": ncloud.get("lb_public_subnet_cidr", "10.10.11.0/24"),
        "node_pool_name": ncloud.get("node_pool_name", f"{project['name']}-{selected_env}-pool"),
        "node_count": int(ncloud.get("node_count", 2)),
        "node_server_spec_code": ncloud.get("node_server_spec_code") or ncloud.get("node_product_code"),
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
        errors.append("login_key_name must be set to an existing Ncloud login key name.")

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


def write_runtime_terraform_files(runtime_dir: Path, tfvars: dict[str, Any]) -> None:
    (runtime_dir / "versions.tf").write_text(TERRAFORM_VERSIONS_TF, encoding="utf-8")
    (runtime_dir / "variables.tf").write_text(TERRAFORM_VARIABLES_TF, encoding="utf-8")
    (runtime_dir / "main.tf").write_text(TERRAFORM_MAIN_TF, encoding="utf-8")
    (runtime_dir / "outputs.tf").write_text(TERRAFORM_OUTPUTS_TF, encoding="utf-8")
    (runtime_dir / "terraform.tfvars.json").write_text(
        json.dumps(tfvars, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def provision_ncloud_target(project_state: dict[str, Any], selected_env: str, output_root: Path, apply: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
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

    tfvars = build_runtime_tfvars(state, selected_env)
    validate_ncloud_preflight(tfvars, access_key_ref, access_key, secret_key_ref, secret_key)
    runtime_dir = ensure_runtime_dir(output_root, project["name"], selected_env)
    write_runtime_terraform_files(runtime_dir, tfvars)

    terraform_bin = state.get("provisioning", {}).get("terraform_executable", "terraform")
    command_env = {
        **os.environ,
        "NCLOUD_ACCESS_KEY": access_key,
        "NCLOUD_SECRET_KEY": secret_key,
        "NCLOUD_REGION": tfvars["region"],
        "TF_IN_AUTOMATION": "1",
    }

    logs = [
        f"Prepared Terraform runtime in {runtime_dir}.",
        f"Ncloud target cluster_name={tfvars['cluster_name']} zone={tfvars['zone']} region={tfvars['region']}.",
        f"Existing cluster_uuid={tfvars['existing_cluster_uuid'] or '(create new)'} vpc_no={tfvars['existing_vpc_no'] or '(create new)'}.",
    ]

    init_result = run_command([terraform_bin, "init", "-backend=false"], runtime_dir, command_env)
    if init_result.returncode != 0:
        raise RuntimeError(f"terraform init failed:\n{init_result.stderr.strip() or init_result.stdout.strip()}")
    logs.append("terraform init completed.")

    validate_result = run_command([terraform_bin, "validate"], runtime_dir, command_env)
    if validate_result.returncode != 0:
        raise RuntimeError(f"terraform validate failed:\n{validate_result.stderr.strip() or validate_result.stdout.strip()}")
    logs.append("terraform validate completed.")

    if not apply:
        return state, {
            "applied": False,
            "runtime_dir": str(runtime_dir),
            "logs": logs,
            "tfvars": tfvars,
        }

    apply_result = run_command([terraform_bin, "apply", "-auto-approve"], runtime_dir, command_env)
    if apply_result.returncode != 0:
        raise RuntimeError(f"terraform apply failed:\n{apply_result.stderr.strip() or apply_result.stdout.strip()}")
    logs.append("terraform apply completed.")

    output_result = run_command([terraform_bin, "output", "-json"], runtime_dir, command_env)
    if output_result.returncode != 0:
        raise RuntimeError(f"terraform output failed:\n{output_result.stderr.strip() or output_result.stdout.strip()}")

    outputs = extract_terraform_output(output_result.stdout)
    kubeconfig = outputs["kubeconfig"]
    kubeconfig_path = runtime_dir / "kubeconfig.yaml"
    kubeconfig_path.write_text(render_kubeconfig(tfvars["cluster_name"], kubeconfig), encoding="utf-8")

    argocd_cluster_secret_path = runtime_dir / "argocd-cluster-secret.yaml"
    argocd_cluster_secret_path.write_text(
        render_argocd_cluster_secret(tfvars["cluster_name"], outputs["cluster_endpoint"], kubeconfig, selected_env),
        encoding="utf-8",
    )

    next_ncloud = state["targets"][selected_env]["ncloud"]
    next_ncloud["cluster_uuid"] = outputs["cluster_uuid"]
    next_ncloud["cluster_endpoint"] = outputs["cluster_endpoint"]
    next_ncloud["vpc_no"] = outputs["vpc_no"]
    next_ncloud["subnet_no"] = outputs["node_subnet_no"]
    next_ncloud["lb_subnet_no"] = outputs["lb_private_subnet_no"]
    next_ncloud["lb_public_subnet_no"] = outputs["lb_public_subnet_no"]
    next_ncloud["login_key_name"] = tfvars["login_key_name"]
    state["argo"]["destination_name"] = ""
    state["argo"]["destination_server"] = outputs["cluster_endpoint"]
    state.setdefault("provisioning", {}).setdefault("last_results", {})[selected_env] = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "runtime_dir": str(runtime_dir),
        "kubeconfig_path": str(kubeconfig_path),
        "argocd_cluster_secret_path": str(argocd_cluster_secret_path),
        "cluster_uuid": outputs["cluster_uuid"],
        "cluster_endpoint": outputs["cluster_endpoint"],
    }

    logs.append(f"Wrote kubeconfig to {kubeconfig_path}.")
    logs.append(f"Wrote Argo CD cluster secret manifest to {argocd_cluster_secret_path}.")

    return state, {
        "applied": True,
        "runtime_dir": str(runtime_dir),
        "kubeconfig_path": str(kubeconfig_path),
        "argocd_cluster_secret_path": str(argocd_cluster_secret_path),
        "logs": logs,
        "outputs": outputs,
    }
