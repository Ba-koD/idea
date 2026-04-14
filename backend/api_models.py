from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

ENVIRONMENTS: tuple[str, ...] = ("dev", "stage", "prod")


def build_hostname(subdomain: str, base_domain: str) -> str:
    normalized_base = (base_domain or "").strip().lower()
    normalized_subdomain = (subdomain or "").strip().lower()

    if not normalized_base:
        return ""

    if normalized_subdomain in {"", "@", "*"}:
        return normalized_base

    return f"{normalized_subdomain}.{normalized_base}"


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
                "cluster_version": "1.30",
                "auth_method": "access_key",
                "access_key_secret_ref": "ncloud-dev-access-key",
                "secret_key_secret_ref": "ncloud-dev-secret-key",
                "zone_code": "KR-2",
                "vpc_no": "vpc-dev",
                "subnet_no": "subnet-dev",
                "lb_subnet_no": "lb-subnet-dev",
                "node_pool_name": "repo-example-dev-pool",
                "node_count": 2,
                "node_product_code": "SVR.VSVR.STAND.C002.M004.NET.SSD.B050.G002",
                "block_storage_size_gb": 50,
                "autoscale_enabled": True,
                "autoscale_min_node_count": 2,
                "autoscale_max_node_count": 4,
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
                "cluster_version": "1.30",
                "auth_method": "access_key",
                "access_key_secret_ref": "ncloud-stage-access-key",
                "secret_key_secret_ref": "ncloud-stage-secret-key",
                "zone_code": "KR-2",
                "vpc_no": "vpc-stage",
                "subnet_no": "subnet-stage",
                "lb_subnet_no": "lb-subnet-stage",
                "node_pool_name": "repo-example-stage-pool",
                "node_count": 2,
                "node_product_code": "SVR.VSVR.STAND.C002.M004.NET.SSD.B050.G002",
                "block_storage_size_gb": 50,
                "autoscale_enabled": True,
                "autoscale_min_node_count": 2,
                "autoscale_max_node_count": 4,
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
                "cluster_version": "1.30",
                "auth_method": "access_key",
                "access_key_secret_ref": "ncloud-prod-access-key",
                "secret_key_secret_ref": "ncloud-prod-secret-key",
                "zone_code": "KR-2",
                "vpc_no": "vpc-prod",
                "subnet_no": "subnet-prod",
                "lb_subnet_no": "lb-subnet-prod",
                "node_pool_name": "repo-example-prod-pool",
                "node_count": 3,
                "node_product_code": "SVR.VSVR.STAND.C004.M008.NET.SSD.B100.G002",
                "block_storage_size_gb": 100,
                "autoscale_enabled": True,
                "autoscale_min_node_count": 3,
                "autoscale_max_node_count": 6,
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
        "dev": {
            "EXAMPLE_API_TOKEN": "secret://repo-example/dev/example-api-token",
        },
        "stage": {
            "EXAMPLE_API_TOKEN": "secret://repo-example/stage/example-api-token",
        },
        "prod": {
            "EXAMPLE_API_TOKEN": "secret://repo-example/prod/example-api-token",
        },
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
        "destination_name": "ncloud-nks-dev",
        "destination_server": "https://kubernetes.default.svc",
        "gitops_repo_url": "https://github.com/Ba-koD/idea.git",
        "gitops_repo_branch": "main",
        "gitops_repo_path": "gitops/generated/repo-example",
        "gitops_repo_access_secret_ref": "gitops-repo-token",
        "access_hint": "ssh MacMini && kubectl -n argocd port-forward svc/argocd-server 8081:80",
    },
    "cloudflare": {
        "enabled": True,
        "account_id": "2052eb94f7b555bd3bf9db83c1f4edbf",
        "zone_id": "aaafd11f9c6912ba37c1d52a69b78398",
        "api_token_secret_ref": "cloudflare-api-token",
        "tunnel_name": "repo-example-platform",
        "route_mode": "platform_caddy",
        "environments": {
            "dev": {
                "subdomain": "repo-example-dev",
                "base_domain": "rnen.kr",
            },
            "stage": {
                "subdomain": "repo-example-stage",
                "base_domain": "rnen.kr",
            },
            "prod": {
                "subdomain": "repo-example",
                "base_domain": "rnen.kr",
            },
        },
    },
    "targets": default_targets(),
    "routing": {
        "entry_service_name": "frontend",
        "backend_service_name": "backend",
        "backend_base_path": "/api",
        "dev_hostname": "repo-example-dev.rnen.kr",
        "stage_hostname": "repo-example-stage.rnen.kr",
        "prod_hostname": "repo-example.rnen.kr",
    },
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
    state = raw_state.model_dump() if isinstance(raw_state, BaseModel) else deepcopy(raw_state or {})
    state = deep_merge(make_default_project_state(), state)

    cloudflare = state.setdefault("cloudflare", {})
    routing = state.setdefault("routing", {})
    delivery = state.setdefault("delivery", {})
    access = state.setdefault("access", {})
    legacy_base_domain = cloudflare.get("base_domain", "")
    legacy_prefix = cloudflare.get("public_subdomain_prefix", "")
    environments = cloudflare.setdefault("environments", {})

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

        env_values = state.setdefault("env", {}).setdefault(env_name, {})
        env_values.setdefault("APP_ENV", env_name)
        env_values.setdefault("APP_DISPLAY_NAME", f"Repo Example {env_name.title()}")
        env_values.setdefault("PUBLIC_API_BASE_URL", routing.get("backend_base_path", "/api"))

        state.setdefault("secrets", {}).setdefault(env_name, {})
        state.setdefault("targets", {}).setdefault(env_name, deepcopy(DEFAULT_PROJECT_STATE["targets"][env_name]))
        access.setdefault(f"{env_name}_allowed_source_ips", [])

    delivery.setdefault("healthcheck_path", f"{routing.get('backend_base_path', '/api').rstrip('/')}/healthz")

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
    destination_name: str = "ncloud-nks-dev"
    destination_server: str = "https://kubernetes.default.svc"
    gitops_repo_url: str = "https://github.com/Ba-koD/idea.git"
    gitops_repo_branch: str = "main"
    gitops_repo_path: str = "gitops/generated/repo-example"
    gitops_repo_access_secret_ref: str = "gitops-repo-token"
    access_hint: str = "ssh MacMini && kubectl -n argocd port-forward svc/argocd-server 8081:80"


class CloudflareEnvConfig(BaseModel):
    subdomain: str = ""
    base_domain: str = ""


class CloudflareConfig(BaseModel):
    enabled: bool = True
    account_id: str = ""
    zone_id: str = ""
    api_token_secret_ref: str = "cloudflare-api-token"
    tunnel_name: str = "repo-example-platform"
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


class AccessConfig(BaseModel):
    admin_allowed_source_ips: List[str] = Field(default_factory=list)
    dev_allowed_source_ips: List[str] = Field(default_factory=list)
    stage_allowed_source_ips: List[str] = Field(default_factory=list)
    prod_allowed_source_ips: List[str] = Field(default_factory=list)


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
    env: Dict[str, Dict[str, str]] = Field(default_factory=default_env_map)
    secrets: Dict[str, Dict[str, str]] = Field(default_factory=default_secrets)
    access: AccessConfig = Field(default_factory=AccessConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)


class DeployRequest(BaseModel):
    selected_env: Literal["dev", "stage", "prod"]
    project_state: ProjectState

