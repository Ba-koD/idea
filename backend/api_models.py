from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

ENVIRONMENTS: tuple[str, ...] = ("dev", "stage", "prod")
SUPPORTED_NCLOUD_CLUSTER_VERSIONS: tuple[str, ...] = ("1.33.4", "1.34.3", "1.32.8")
DEFAULT_NCLOUD_CLUSTER_VERSION = "1.33.4"
DEFAULT_PLATFORM_TUNNEL_NAME = "idea-platform"
DEFAULT_ARGOCD_SUBDOMAIN = "argo"
DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV: Dict[str, str] = {
    "dev": "s2-g3a",
    "stage": "s2-g3a",
    "prod": "s4-g3a",
}


def build_hostname(subdomain: str, base_domain: str) -> str:
    normalized_base = (base_domain or "").strip().lower()
    normalized_subdomain = (subdomain or "").strip().lower()

    if not normalized_base:
        return ""

    if normalized_subdomain in {"", "@", "*"}:
        return normalized_base

    return f"{normalized_subdomain}.{normalized_base}"


def preferred_base_domain(state: Dict[str, Any]) -> str:
    environments = state.get("cloudflare", {}).get("environments", {})
    for env_name in ("prod", "stage", "dev"):
        base_domain = str(environments.get(env_name, {}).get("base_domain", "")).strip().lower()
        if base_domain:
            return base_domain
    return ""


def desired_argocd_access_hint(state: Dict[str, Any]) -> str:
    base_domain = preferred_base_domain(state) or "rnen.kr"
    return f"https://{DEFAULT_ARGOCD_SUBDOMAIN}.{base_domain}"


def normalize_argocd_access_hint(raw_hint: Any, state: Dict[str, Any]) -> str:
    hint = str(raw_hint or "").strip()
    desired_hint = desired_argocd_access_hint(state)

    if not hint:
        return desired_hint

    parsed = urlparse(hint if "://" in hint else f"https://{hint}")
    if parsed.hostname:
        return f"{parsed.scheme or 'https'}://{parsed.hostname}"

    return desired_hint


def normalize_ncloud_node_product_code(raw_value: Any, env_name: str) -> str:
    default_value = DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV.get(env_name, "s2-g3a")
    text = str(raw_value or "").strip()
    if not text:
        return default_value
    if text.upper().startswith("SVR."):
        return default_value
    return text


def default_targets() -> Dict[str, Dict[str, Any]]:
    return {
        "dev": {
            "provider": "ncloud",
            "cluster_type": "nks",
            "namespace": "repo-example-dev",
            "service_port": 80,
            "ncloud": {
                "region_code": "KR",
                "cluster_name": "idea-dev",
                "cluster_uuid": "",
                "cluster_version": DEFAULT_NCLOUD_CLUSTER_VERSION,
                "cluster_type_code": "SVR.VNKS.STAND.C004.M016.G003",
                "hypervisor_code": "KVM",
                "auth_method": "access_key",
                "access_key_secret_ref": "ncloud-dev-access-key",
                "secret_key_secret_ref": "ncloud-dev-secret-key",
                "zone_code": "KR-2",
                "vpc_no": "vpc-dev",
                "subnet_no": "subnet-dev",
                "lb_subnet_no": "lb-subnet-dev",
                "lb_public_subnet_no": "",
                "node_pool_id": "",
                "login_key_name": "idea-runtime-login",
                "node_pool_name": "repo-example-dev-pool",
                "node_count": 2,
                "node_product_code": DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV["dev"],
                "node_image_label": "ubuntu-22.04",
                "block_storage_size_gb": 50,
                "autoscale_enabled": True,
                "autoscale_min_node_count": 2,
                "autoscale_max_node_count": 4,
                "vpc_cidr": "10.10.0.0/16",
                "node_subnet_cidr": "10.10.1.0/24",
                "lb_private_subnet_cidr": "10.10.10.0/24",
                "lb_public_subnet_cidr": "10.10.11.0/24",
            },
        },
        "stage": {
            "provider": "ncloud",
            "cluster_type": "nks",
            "namespace": "repo-example-stage",
            "service_port": 80,
            "ncloud": {
                "region_code": "KR",
                "cluster_name": "idea-stage",
                "cluster_uuid": "",
                "cluster_version": DEFAULT_NCLOUD_CLUSTER_VERSION,
                "cluster_type_code": "SVR.VNKS.STAND.C004.M016.G003",
                "hypervisor_code": "KVM",
                "auth_method": "access_key",
                "access_key_secret_ref": "ncloud-stage-access-key",
                "secret_key_secret_ref": "ncloud-stage-secret-key",
                "zone_code": "KR-2",
                "vpc_no": "vpc-stage",
                "subnet_no": "subnet-stage",
                "lb_subnet_no": "lb-subnet-stage",
                "lb_public_subnet_no": "",
                "node_pool_id": "",
                "login_key_name": "idea-runtime-login",
                "node_pool_name": "repo-example-stage-pool",
                "node_count": 2,
                "node_product_code": DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV["stage"],
                "node_image_label": "ubuntu-22.04",
                "block_storage_size_gb": 50,
                "autoscale_enabled": True,
                "autoscale_min_node_count": 2,
                "autoscale_max_node_count": 4,
                "vpc_cidr": "10.20.0.0/16",
                "node_subnet_cidr": "10.20.1.0/24",
                "lb_private_subnet_cidr": "10.20.10.0/24",
                "lb_public_subnet_cidr": "10.20.11.0/24",
            },
        },
        "prod": {
            "provider": "ncloud",
            "cluster_type": "nks",
            "namespace": "repo-example-prod",
            "service_port": 80,
            "ncloud": {
                "region_code": "KR",
                "cluster_name": "idea-prod",
                "cluster_uuid": "",
                "cluster_version": DEFAULT_NCLOUD_CLUSTER_VERSION,
                "cluster_type_code": "SVR.VNKS.STAND.C004.M016.G003",
                "hypervisor_code": "KVM",
                "auth_method": "access_key",
                "access_key_secret_ref": "ncloud-prod-access-key",
                "secret_key_secret_ref": "ncloud-prod-secret-key",
                "zone_code": "KR-2",
                "vpc_no": "vpc-prod",
                "subnet_no": "subnet-prod",
                "lb_subnet_no": "lb-subnet-prod",
                "lb_public_subnet_no": "",
                "node_pool_id": "",
                "login_key_name": "idea-runtime-login",
                "node_pool_name": "repo-example-prod-pool",
                "node_count": 3,
                "node_product_code": DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV["prod"],
                "node_image_label": "ubuntu-22.04",
                "block_storage_size_gb": 100,
                "autoscale_enabled": True,
                "autoscale_min_node_count": 3,
                "autoscale_max_node_count": 6,
                "vpc_cidr": "10.30.0.0/16",
                "node_subnet_cidr": "10.30.1.0/24",
                "lb_private_subnet_cidr": "10.30.10.0/24",
                "lb_public_subnet_cidr": "10.30.11.0/24",
            },
        },
    }


def default_env_map() -> Dict[str, Dict[str, str]]:
    return {
        "dev": {
            "APP_ENV": "dev",
            "APP_DISPLAY_NAME": "Repo Example Dev",
            "PUBLIC_API_BASE_URL": "/api",
        },
        "stage": {
            "APP_ENV": "stage",
            "APP_DISPLAY_NAME": "Repo Example Stage",
            "PUBLIC_API_BASE_URL": "/api",
        },
        "prod": {
            "APP_ENV": "prod",
            "APP_DISPLAY_NAME": "Repo Example Prod",
            "PUBLIC_API_BASE_URL": "/api",
            "NODE_ENV": "production",
        },
    }


def default_secrets() -> Dict[str, Dict[str, str]]:
    return {
        "dev": {},
        "stage": {},
        "prod": {},
    }


def prune_legacy_example_secrets(secret_map: Dict[str, str], env_name: str) -> Dict[str, str]:
    legacy_example_value = f"secret://repo-example/{env_name}/example-api-token"
    return {
        key: value
        for key, value in (secret_map or {}).items()
        if not (key == "EXAMPLE_API_TOKEN" and value == legacy_example_value)
    }


def default_provisioning() -> Dict[str, Any]:
    return {
        "terraform_executable": "terraform",
        "site": "public",
        "secret_values": {},
        "last_results": {},
    }


DEFAULT_PROJECT_STATE: Dict[str, Any] = {
    "project": {
        "name": "repo-example",
        "app_repo_url": "https://github.com/Ba-koD/repo_example",
        "git_ref": "main",
        "repo_access_secret_ref": "github-repo-example-token",
    },
    "build": {
        "source_strategy": "platform_build_runner",
        "frontend_context": "frontend",
        "frontend_dockerfile_path": "frontend/Dockerfile",
        "backend_context": "backend",
        "backend_dockerfile_path": "backend/Dockerfile",
    },
    "argo": {
        "project_name": "default",
        "destination_name": "",
        "destination_server": "https://kubernetes.default.svc",
        "gitops_repo_url": "https://github.com/Ba-koD/idea.git",
        "gitops_repo_branch": "main",
        "gitops_repo_path": "gitops/apps",
        "gitops_repo_access_secret_ref": "gitops-repo-token",
        "admin_password_secret_ref": "argocd-admin-password",
        "admin_password_last_applied_at": "",
        "access_hint": "https://argo.rnen.kr",
    },
    "cloudflare": {
        "enabled": True,
        "account_id": "2052eb94f7b555bd3bf9db83c1f4edbf",
        "zone_id": "aaafd11f9c6912ba37c1d52a69b78398",
        "api_token_secret_ref": "cloudflare-api-token",
        "tunnel_name": DEFAULT_PLATFORM_TUNNEL_NAME,
        "route_mode": "platform_caddy",
        "environments": {
            "dev": {
                "subdomain": "dev",
                "base_domain": "rnen.kr",
            },
            "stage": {
                "subdomain": "stage",
                "base_domain": "rnen.kr",
            },
            "prod": {
                "subdomain": "prod",
                "base_domain": "rnen.kr",
            },
        },
    },
    "targets": default_targets(),
    "routing": {
        "entry_service_name": "frontend",
        "backend_service_name": "backend",
        "backend_base_path": "/api",
        "dev_hostname": "dev.rnen.kr",
        "stage_hostname": "stage.rnen.kr",
        "prod_hostname": "prod.rnen.kr",
    },
    "provisioning": default_provisioning(),
    "env": default_env_map(),
    "secrets": default_secrets(),
    "access": {
        "admin_allowed_source_ips": ["58.123.221.76/32"],
        "dev_allowed_source_ips": ["58.123.221.76/32"],
        "stage_allowed_source_ips": ["58.123.221.76/32"],
        "prod_allowed_source_ips": [],
    },
    "delivery": {
        "prod_blue_green_enabled": True,
        "healthcheck_path": "/api/healthz",
        "healthcheck_timeout_seconds": 30,
        "rollback_on_failure": True,
    },
}


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = deepcopy(base)
        for key, value in override.items():
            merged[key] = deep_merge(merged.get(key), value) if key in merged else deepcopy(value)
        return merged

    return deepcopy(override if override is not None else base)


def make_default_project_state() -> Dict[str, Any]:
    return deepcopy(DEFAULT_PROJECT_STATE)


def normalize_project_state(raw_state: Any) -> Dict[str, Any]:
    incoming = raw_state.model_dump() if isinstance(raw_state, BaseModel) else deepcopy(raw_state or {})
    state = deep_merge(make_default_project_state(), incoming)

    cloudflare = state.setdefault("cloudflare", {})
    argo = state.setdefault("argo", {})
    routing = state.setdefault("routing", {})
    delivery = state.setdefault("delivery", {})
    access = state.setdefault("access", {})
    legacy_base_domain = cloudflare.get("base_domain", "")
    legacy_prefix = cloudflare.get("public_subdomain_prefix", "")
    environments = cloudflare.setdefault("environments", {})

    if not str(cloudflare.get("tunnel_name", "")).strip():
        cloudflare["tunnel_name"] = DEFAULT_PLATFORM_TUNNEL_NAME

    for env_name in ENVIRONMENTS:
        env_cloudflare = environments.setdefault(env_name, {})
        env_cloudflare.setdefault("base_domain", legacy_base_domain)

        if not env_cloudflare.get("subdomain"):
            if legacy_prefix:
                suffix = {"dev": "-dev", "stage": "-stage", "prod": ""}[env_name]
                env_cloudflare["subdomain"] = f"{legacy_prefix}{suffix}"
            else:
                env_cloudflare["subdomain"] = DEFAULT_PROJECT_STATE["cloudflare"]["environments"][env_name]["subdomain"]

        routing[f"{env_name}_hostname"] = build_hostname(
            env_cloudflare.get("subdomain", ""),
            env_cloudflare.get("base_domain", ""),
        )

        incoming_env_map = incoming.get("env", {}).get(env_name)
        if incoming_env_map is not None:
            state.setdefault("env", {})[env_name] = deepcopy(incoming_env_map)
        else:
            env_values = state.setdefault("env", {}).setdefault(env_name, {})
            env_values.setdefault("APP_ENV", env_name)
            env_values.setdefault("APP_DISPLAY_NAME", f"Repo Example {env_name.title()}")
            env_values.setdefault("PUBLIC_API_BASE_URL", routing.get("backend_base_path", "/api"))

        incoming_secret_map = incoming.get("secrets", {}).get(env_name)
        if incoming_secret_map is not None:
            state.setdefault("secrets", {})[env_name] = prune_legacy_example_secrets(
                deepcopy(incoming_secret_map),
                env_name,
            )
        else:
            state.setdefault("secrets", {}).setdefault(env_name, {})
            state["secrets"][env_name] = prune_legacy_example_secrets(state["secrets"][env_name], env_name)
        state.setdefault("targets", {}).setdefault(env_name, deepcopy(DEFAULT_PROJECT_STATE["targets"][env_name]))
        state["targets"][env_name]["ncloud"]["node_product_code"] = normalize_ncloud_node_product_code(
            state["targets"][env_name]["ncloud"].get("node_product_code"),
            env_name,
        )
        access.setdefault(f"{env_name}_allowed_source_ips", [])

    delivery.setdefault("healthcheck_path", f"{routing.get('backend_base_path', '/api').rstrip('/')}/healthz")
    state.setdefault("provisioning", deepcopy(DEFAULT_PROJECT_STATE["provisioning"]))
    argo["access_hint"] = normalize_argocd_access_hint(argo.get("access_hint", ""), state)

    return state


class ProjectConfig(BaseModel):
    name: str = "repo-example"
    app_repo_url: str = "https://github.com/Ba-koD/repo_example"
    git_ref: str = "main"
    repo_access_secret_ref: str = "github-repo-example-token"


class BuildConfig(BaseModel):
    source_strategy: str = "platform_build_runner"
    frontend_context: str = "frontend"
    frontend_dockerfile_path: str = "frontend/Dockerfile"
    backend_context: str = "backend"
    backend_dockerfile_path: str = "backend/Dockerfile"


class ArgoConfig(BaseModel):
    project_name: str = "default"
    destination_name: str = ""
    destination_server: str = "https://kubernetes.default.svc"
    gitops_repo_url: str = "https://github.com/Ba-koD/idea.git"
    gitops_repo_branch: str = "main"
    gitops_repo_path: str = "gitops/apps"
    gitops_repo_access_secret_ref: str = "gitops-repo-token"
    admin_password_secret_ref: str = "argocd-admin-password"
    admin_password_last_applied_at: str = ""
    access_hint: str = "https://argo.rnen.kr"


class CloudflareEnvConfig(BaseModel):
    subdomain: str = ""
    base_domain: str = ""


class CloudflareConfig(BaseModel):
    enabled: bool = True
    account_id: str = "2052eb94f7b555bd3bf9db83c1f4edbf"
    zone_id: str = "aaafd11f9c6912ba37c1d52a69b78398"
    api_token_secret_ref: str = "cloudflare-api-token"
    tunnel_name: str = DEFAULT_PLATFORM_TUNNEL_NAME
    route_mode: str = "platform_caddy"
    environments: Dict[str, CloudflareEnvConfig] = Field(
        default_factory=lambda: {
            env_name: CloudflareEnvConfig(**DEFAULT_PROJECT_STATE["cloudflare"]["environments"][env_name])
            for env_name in ENVIRONMENTS
        }
    )


class TargetConfig(BaseModel):
    provider: str = "ncloud"
    cluster_type: str = "nks"
    namespace: str = ""
    service_port: int = 80
    ncloud: Dict[str, Any] = Field(default_factory=dict)


class RoutingConfig(BaseModel):
    entry_service_name: str = "frontend"
    backend_service_name: str = "backend"
    backend_base_path: str = "/api"
    dev_hostname: str = ""
    stage_hostname: str = ""
    prod_hostname: str = ""


class ProvisioningConfig(BaseModel):
    terraform_executable: str = "terraform"
    site: str = "public"
    secret_values: Dict[str, str] = Field(default_factory=dict)
    last_results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class AccessConfig(BaseModel):
    admin_allowed_source_ips: List[str] = Field(
        default_factory=lambda: deepcopy(DEFAULT_PROJECT_STATE["access"]["admin_allowed_source_ips"])
    )
    dev_allowed_source_ips: List[str] = Field(
        default_factory=lambda: deepcopy(DEFAULT_PROJECT_STATE["access"]["dev_allowed_source_ips"])
    )
    stage_allowed_source_ips: List[str] = Field(
        default_factory=lambda: deepcopy(DEFAULT_PROJECT_STATE["access"]["stage_allowed_source_ips"])
    )
    prod_allowed_source_ips: List[str] = Field(
        default_factory=lambda: deepcopy(DEFAULT_PROJECT_STATE["access"]["prod_allowed_source_ips"])
    )


class DeliveryConfig(BaseModel):
    prod_blue_green_enabled: bool = True
    healthcheck_path: str = "/api/healthz"
    healthcheck_timeout_seconds: int = 30
    rollback_on_failure: bool = True


class ProjectState(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    build: BuildConfig = Field(default_factory=BuildConfig)
    argo: ArgoConfig = Field(default_factory=ArgoConfig)
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    targets: Dict[str, TargetConfig] = Field(
        default_factory=lambda: {
            env_name: TargetConfig(**default_targets()[env_name])
            for env_name in ENVIRONMENTS
        }
    )
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    provisioning: ProvisioningConfig = Field(default_factory=ProvisioningConfig)
    env: Dict[str, Dict[str, str]] = Field(default_factory=default_env_map)
    secrets: Dict[str, Dict[str, str]] = Field(default_factory=default_secrets)
    access: AccessConfig = Field(default_factory=AccessConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)


class DeployRequest(BaseModel):
    selected_env: Literal["dev", "stage", "prod"]
    project_state: ProjectState


class EnvExchangeRequest(BaseModel):
    selected_env: Literal["dev", "stage", "prod"]
    project_state: ProjectState | None = None


class ProvisionRequest(BaseModel):
    selected_env: Literal["dev", "stage", "prod"]
    project_state: ProjectState
    apply: bool = True
    operation: Literal["apply", "destroy"] = "apply"
