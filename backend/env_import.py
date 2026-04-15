from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from api_models import default_env_map

SECRET_KEY_MARKERS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASS",
    "PRIVATE",
    "API_KEY",
    "ACCESS_KEY",
    "SECRET_KEY",
    "CLIENT_SECRET",
    "JWT",
    "COOKIE",
    "SESSION",
    "DATABASE_URL",
    "REDIS_URL",
    "MONGO_URL",
    "POSTGRES_URL",
)

ENV_NAMES = ("dev", "stage", "prod")


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


def stringify_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(item) for item in value if item is not None)
    return str(value)


def normalize_secret_ref_name(name: str) -> str:
    normalized = str(name or "").strip().replace("__", "/").replace("_", "-").lower()
    return "-".join(part for part in normalized.split("-") if part)


def set_path(mapping: Dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    target = mapping
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value


def get_path(mapping: Dict[str, Any], path: tuple[str, ...], default: Any = "") -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def make_platform_key_map(selected_env: str) -> Dict[str, tuple[tuple[str, ...], Callable[[str], Any]]]:
    env_path = ("cloudflare", "environments", selected_env)
    target_path = ("targets", selected_env)
    ncloud_path = ("targets", selected_env, "ncloud")
    access_key = f"{selected_env}_allowed_source_ips"

    return {
        "IDEA_SELECTED_ENV": (("meta", "selected_env"), str),
        "IDEA_IMPORT_MODE": (("meta", "import_mode"), str),
        "IDEA_PROJECT_NAME": (("project", "name"), str),
        "IDEA_APP_REPOSITORY_URL": (("project", "app_repo_url"), str),
        "IDEA_GIT_REF": (("project", "git_ref"), str),
        "IDEA_REPO_ACCESS_SECRET_REF": (("project", "repo_access_secret_ref"), str),
        "IDEA_BUILD_SOURCE_STRATEGY": (("build", "source_strategy"), str),
        "IDEA_FRONTEND_CONTEXT": (("build", "frontend_context"), str),
        "IDEA_FRONTEND_DOCKERFILE": (("build", "frontend_dockerfile_path"), str),
        "IDEA_BACKEND_CONTEXT": (("build", "backend_context"), str),
        "IDEA_BACKEND_DOCKERFILE": (("build", "backend_dockerfile_path"), str),
        "IDEA_ARGO_PROJECT_NAME": (("argo", "project_name"), str),
        "IDEA_ARGO_DESTINATION_NAME": (("argo", "destination_name"), str),
        "IDEA_ARGO_DESTINATION_SERVER": (("argo", "destination_server"), str),
        "IDEA_GITOPS_REPO_URL": (("argo", "gitops_repo_url"), str),
        "IDEA_GITOPS_REPO_BRANCH": (("argo", "gitops_repo_branch"), str),
        "IDEA_GITOPS_REPO_PATH": (("argo", "gitops_repo_path"), str),
        "IDEA_GITOPS_REPO_ACCESS_SECRET_REF": (("argo", "gitops_repo_access_secret_ref"), str),
        "IDEA_ARGO_ADMIN_PASSWORD_SECRET_REF": (("argo", "admin_password_secret_ref"), str),
        "IDEA_ARGO_ADMIN_PASSWORD_LAST_APPLIED_AT": (("argo", "admin_password_last_applied_at"), str),
        "IDEA_ARGO_ACCESS_HINT": (("argo", "access_hint"), str),
        "IDEA_CLOUDFLARE_ENABLED": (("cloudflare", "enabled"), parse_bool),
        "IDEA_CLOUDFLARE_ACCOUNT_ID": (("cloudflare", "account_id"), str),
        "IDEA_CLOUDFLARE_ZONE_ID": (("cloudflare", "zone_id"), str),
        "IDEA_CLOUDFLARE_API_TOKEN_SECRET_REF": (("cloudflare", "api_token_secret_ref"), str),
        "IDEA_CLOUDFLARE_TUNNEL_NAME": (("cloudflare", "tunnel_name"), str),
        "IDEA_CLOUDFLARE_ROUTE_MODE": (("cloudflare", "route_mode"), str),
        "IDEA_CLOUDFLARE_SUBDOMAIN": (env_path + ("subdomain",), str),
        "IDEA_CLOUDFLARE_BASE_DOMAIN": (env_path + ("base_domain",), str),
        "IDEA_PROVIDER": (target_path + ("provider",), str),
        "IDEA_CLUSTER_TYPE": (target_path + ("cluster_type",), str),
        "IDEA_NAMESPACE": (target_path + ("namespace",), str),
        "IDEA_SERVICE_PORT": (target_path + ("service_port",), parse_int),
        "IDEA_NCLOUD_REGION_CODE": (ncloud_path + ("region_code",), str),
        "IDEA_NCLOUD_CLUSTER_NAME": (ncloud_path + ("cluster_name",), str),
        "IDEA_NCLOUD_CLUSTER_UUID": (ncloud_path + ("cluster_uuid",), str),
        "IDEA_NCLOUD_CLUSTER_VERSION": (ncloud_path + ("cluster_version",), str),
        "IDEA_NCLOUD_CLUSTER_TYPE_CODE": (ncloud_path + ("cluster_type_code",), str),
        "IDEA_NCLOUD_HYPERVISOR_CODE": (ncloud_path + ("hypervisor_code",), str),
        "IDEA_NCLOUD_AUTH_METHOD": (ncloud_path + ("auth_method",), str),
        "IDEA_NCLOUD_ACCESS_KEY_SECRET_REF": (ncloud_path + ("access_key_secret_ref",), str),
        "IDEA_NCLOUD_SECRET_KEY_SECRET_REF": (ncloud_path + ("secret_key_secret_ref",), str),
        "IDEA_NCLOUD_ZONE_CODE": (ncloud_path + ("zone_code",), str),
        "IDEA_NCLOUD_VPC_NO": (ncloud_path + ("vpc_no",), str),
        "IDEA_NCLOUD_SUBNET_NO": (ncloud_path + ("subnet_no",), str),
        "IDEA_NCLOUD_LB_SUBNET_NO": (ncloud_path + ("lb_subnet_no",), str),
        "IDEA_NCLOUD_LB_PUBLIC_SUBNET_NO": (ncloud_path + ("lb_public_subnet_no",), str),
        "IDEA_NCLOUD_NODE_POOL_ID": (ncloud_path + ("node_pool_id",), str),
        "IDEA_NCLOUD_LOGIN_KEY_NAME": (ncloud_path + ("login_key_name",), str),
        "IDEA_NCLOUD_NODE_POOL_NAME": (ncloud_path + ("node_pool_name",), str),
        "IDEA_NCLOUD_NODE_COUNT": (ncloud_path + ("node_count",), parse_int),
        "IDEA_NCLOUD_NODE_PRODUCT_CODE": (ncloud_path + ("node_product_code",), str),
        "IDEA_NCLOUD_NODE_IMAGE_LABEL": (ncloud_path + ("node_image_label",), str),
        "IDEA_NCLOUD_BLOCK_STORAGE_SIZE_GB": (ncloud_path + ("block_storage_size_gb",), parse_int),
        "IDEA_NCLOUD_AUTOSCALE_ENABLED": (ncloud_path + ("autoscale_enabled",), parse_bool),
        "IDEA_NCLOUD_AUTOSCALE_MIN_NODE_COUNT": (ncloud_path + ("autoscale_min_node_count",), parse_int),
        "IDEA_NCLOUD_AUTOSCALE_MAX_NODE_COUNT": (ncloud_path + ("autoscale_max_node_count",), parse_int),
        "IDEA_NCLOUD_VPC_CIDR": (ncloud_path + ("vpc_cidr",), str),
        "IDEA_NCLOUD_NODE_SUBNET_CIDR": (ncloud_path + ("node_subnet_cidr",), str),
        "IDEA_NCLOUD_LB_PRIVATE_SUBNET_CIDR": (ncloud_path + ("lb_private_subnet_cidr",), str),
        "IDEA_NCLOUD_LB_PUBLIC_SUBNET_CIDR": (ncloud_path + ("lb_public_subnet_cidr",), str),
        "IDEA_ENTRY_SERVICE_NAME": (("routing", "entry_service_name"), str),
        "IDEA_BACKEND_SERVICE_NAME": (("routing", "backend_service_name"), str),
        "IDEA_BACKEND_BASE_PATH": (("routing", "backend_base_path"), str),
        "IDEA_ADMIN_ALLOWED_SOURCE_IPS": (("access", "admin_allowed_source_ips"), parse_csv_list),
        "IDEA_ENV_ALLOWED_SOURCE_IPS": (("access", access_key), parse_csv_list),
        "IDEA_PROD_BLUE_GREEN_ENABLED": (("delivery", "prod_blue_green_enabled"), parse_bool),
        "IDEA_HEALTHCHECK_PATH": (("delivery", "healthcheck_path"), str),
        "IDEA_HEALTHCHECK_TIMEOUT_SECONDS": (("delivery", "healthcheck_timeout_seconds"), parse_int),
        "IDEA_ROLLBACK_ON_FAILURE": (("delivery", "rollback_on_failure"), parse_bool),
        "IDEA_TERRAFORM_EXECUTABLE": (("provisioning", "terraform_executable"), str),
        "IDEA_PROVISION_SITE": (("provisioning", "site"), str),
    }


def make_control_plane_secret_value_map(selected_env: str) -> Dict[str, tuple[str, ...]]:
    ncloud_path = ("targets", selected_env, "ncloud")
    return {
        "IDEA_REPO_ACCESS_TOKEN_VALUE": ("project", "repo_access_secret_ref"),
        "IDEA_GITOPS_REPO_ACCESS_TOKEN_VALUE": ("argo", "gitops_repo_access_secret_ref"),
        "IDEA_ARGO_ADMIN_PASSWORD_VALUE": ("argo", "admin_password_secret_ref"),
        "IDEA_CLOUDFLARE_API_TOKEN_VALUE": ("cloudflare", "api_token_secret_ref"),
        "IDEA_NCLOUD_ACCESS_KEY_VALUE": ncloud_path + ("access_key_secret_ref",),
        "IDEA_NCLOUD_SECRET_KEY_VALUE": ncloud_path + ("secret_key_secret_ref",),
    }


def parse_env_text(env_text: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}

    for raw_line in env_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        parsed[key] = value

    return parsed


def looks_like_secret(key: str, value: str) -> bool:
    upper_key = key.upper()

    if any(marker in upper_key for marker in SECRET_KEY_MARKERS):
        return True

    if upper_key.endswith(("_URL", "_URI", "_DSN")) and "://" in value and "@" in value:
        return True

    return False


def apply_env_import(project_state: Dict[str, Any], selected_env: str, env_text: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    imported = parse_env_text(env_text)
    hinted_env = str(imported.get("IDEA_SELECTED_ENV", selected_env)).strip().lower()
    effective_env = hinted_env if hinted_env in ENV_NAMES else selected_env
    import_mode = str(imported.get("IDEA_IMPORT_MODE", "merge")).strip().lower()
    platform_key_map = make_platform_key_map(effective_env)
    control_plane_secret_value_map = make_control_plane_secret_value_map(effective_env)
    base_env = deepcopy(default_env_map()[effective_env])
    current_env = deepcopy(project_state.get("env", {}).get(effective_env, {}))
    current_secrets = deepcopy(project_state.get("secrets", {}).get(effective_env, {}))
    runtime_env = base_env if import_mode == "replace" else {**base_env, **current_env}
    runtime_secrets: Dict[str, str] = {} if import_mode == "replace" else current_secrets
    imported_env_keys: list[str] = []
    imported_secret_keys: list[str] = []
    platform_keys: list[str] = []
    control_plane_secret_refs: list[str] = []

    next_state = deepcopy(project_state)
    for key, value in imported.items():
        if key in platform_key_map:
            path, caster = platform_key_map[key]
            if path[0] != "meta":
                set_path(next_state, path, caster(value))
                platform_keys.append(key)

    for key, value in imported.items():
        if key in control_plane_secret_value_map:
            secret_ref_path = control_plane_secret_value_map[key]
            secret_ref = normalize_secret_ref_name(get_path(next_state, secret_ref_path))
            if secret_ref:
                next_state.setdefault("provisioning", {}).setdefault("secret_values", {})[secret_ref] = value
                control_plane_secret_refs.append(secret_ref)
            continue

        if key.startswith("IDEA_SECRET_VALUE_"):
            secret_ref = normalize_secret_ref_name(key.removeprefix("IDEA_SECRET_VALUE_"))
            next_state.setdefault("provisioning", {}).setdefault("secret_values", {})[secret_ref] = value
            control_plane_secret_refs.append(secret_ref)
            continue

    for key, value in imported.items():
        if key in platform_key_map or key in control_plane_secret_value_map or key.startswith("IDEA_SECRET_VALUE_"):
            continue

        if looks_like_secret(key, value):
            runtime_secrets[key] = value
            imported_secret_keys.append(key)
        else:
            runtime_env[key] = value
            imported_env_keys.append(key)

    next_state.setdefault("env", {})[effective_env] = runtime_env
    next_state.setdefault("secrets", {})[effective_env] = runtime_secrets

    return next_state, {
        "selected_env": effective_env,
        "import_mode": import_mode,
        "total_count": len(imported),
        "env_count": len(imported_env_keys),
        "secret_count": len(imported_secret_keys),
        "platform_count": len(platform_keys),
        "control_plane_secret_count": len(control_plane_secret_refs),
        "env_keys": sorted(imported_env_keys),
        "secret_keys": sorted(imported_secret_keys),
        "platform_keys": sorted(platform_keys),
        "control_plane_secret_refs": sorted(control_plane_secret_refs),
    }


def split_runtime_secrets(secret_map: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    inline_secrets: Dict[str, str] = {}
    secret_refs: Dict[str, str] = {}

    for key, value in (secret_map or {}).items():
        if isinstance(value, str) and value.startswith("secret://"):
            secret_refs[key] = value
        elif value is not None:
            inline_secrets[key] = str(value)

    return inline_secrets, secret_refs


def redact_project_state(project_state: Dict[str, Any]) -> Dict[str, Any]:
    redacted = deepcopy(project_state)

    for env_name, secret_map in redacted.get("secrets", {}).items():
        inline_secrets, secret_refs = split_runtime_secrets(secret_map)
        next_secret_map: Dict[str, str] = {}
        for key in sorted(secret_refs):
            next_secret_map[key] = secret_refs[key]
        for key in sorted(inline_secrets):
            next_secret_map[key] = "<redacted>"
        redacted["secrets"][env_name] = next_secret_map

    provisioning = redacted.setdefault("provisioning", {})
    provisioning["secret_values"] = {}
    provisioning["last_results"] = {}

    return redacted


def export_env_text(project_state: Dict[str, Any], selected_env: str) -> str:
    state = deepcopy(project_state)
    env_name = selected_env
    target = state["targets"][env_name]
    ncloud = target.get("ncloud", {})
    cloudflare_env = state["cloudflare"]["environments"][env_name]
    lines = [
        "# IDEA Project State import/export",
        "IDEA_IMPORT_MODE=replace",
        f"IDEA_SELECTED_ENV={env_name}",
        "",
        "# Project",
        f"IDEA_PROJECT_NAME={stringify_env_value(get_path(state, ('project', 'name')))}",
        f"IDEA_APP_REPOSITORY_URL={stringify_env_value(get_path(state, ('project', 'app_repo_url')))}",
        f"IDEA_GIT_REF={stringify_env_value(get_path(state, ('project', 'git_ref')))}",
        f"IDEA_REPO_ACCESS_SECRET_REF={stringify_env_value(get_path(state, ('project', 'repo_access_secret_ref')))}",
        "",
        "# Build",
        f"IDEA_BUILD_SOURCE_STRATEGY={stringify_env_value(get_path(state, ('build', 'source_strategy')))}",
        f"IDEA_FRONTEND_CONTEXT={stringify_env_value(get_path(state, ('build', 'frontend_context')))}",
        f"IDEA_FRONTEND_DOCKERFILE={stringify_env_value(get_path(state, ('build', 'frontend_dockerfile_path')))}",
        f"IDEA_BACKEND_CONTEXT={stringify_env_value(get_path(state, ('build', 'backend_context')))}",
        f"IDEA_BACKEND_DOCKERFILE={stringify_env_value(get_path(state, ('build', 'backend_dockerfile_path')))}",
        "",
        "# Argo CD",
        f"IDEA_ARGO_PROJECT_NAME={stringify_env_value(get_path(state, ('argo', 'project_name')))}",
        f"IDEA_ARGO_DESTINATION_NAME={stringify_env_value(get_path(state, ('argo', 'destination_name')))}",
        f"IDEA_ARGO_DESTINATION_SERVER={stringify_env_value(get_path(state, ('argo', 'destination_server')))}",
        f"IDEA_GITOPS_REPO_URL={stringify_env_value(get_path(state, ('argo', 'gitops_repo_url')))}",
        f"IDEA_GITOPS_REPO_BRANCH={stringify_env_value(get_path(state, ('argo', 'gitops_repo_branch')))}",
        f"IDEA_GITOPS_REPO_PATH={stringify_env_value(get_path(state, ('argo', 'gitops_repo_path')))}",
        f"IDEA_GITOPS_REPO_ACCESS_SECRET_REF={stringify_env_value(get_path(state, ('argo', 'gitops_repo_access_secret_ref')))}",
        f"IDEA_ARGO_ADMIN_PASSWORD_SECRET_REF={stringify_env_value(get_path(state, ('argo', 'admin_password_secret_ref')))}",
        f"IDEA_ARGO_ADMIN_PASSWORD_LAST_APPLIED_AT={stringify_env_value(get_path(state, ('argo', 'admin_password_last_applied_at')))}",
        f"IDEA_ARGO_ACCESS_HINT={stringify_env_value(get_path(state, ('argo', 'access_hint')))}",
        "",
        "# Cloudflare",
        f"IDEA_CLOUDFLARE_ENABLED={stringify_env_value(get_path(state, ('cloudflare', 'enabled')))}",
        f"IDEA_CLOUDFLARE_ACCOUNT_ID={stringify_env_value(get_path(state, ('cloudflare', 'account_id')))}",
        f"IDEA_CLOUDFLARE_ZONE_ID={stringify_env_value(get_path(state, ('cloudflare', 'zone_id')))}",
        f"IDEA_CLOUDFLARE_API_TOKEN_SECRET_REF={stringify_env_value(get_path(state, ('cloudflare', 'api_token_secret_ref')))}",
        f"IDEA_CLOUDFLARE_TUNNEL_NAME={stringify_env_value(get_path(state, ('cloudflare', 'tunnel_name')))}",
        f"IDEA_CLOUDFLARE_ROUTE_MODE={stringify_env_value(get_path(state, ('cloudflare', 'route_mode')))}",
        f"IDEA_CLOUDFLARE_SUBDOMAIN={stringify_env_value(cloudflare_env.get('subdomain'))}",
        f"IDEA_CLOUDFLARE_BASE_DOMAIN={stringify_env_value(cloudflare_env.get('base_domain'))}",
        "",
        "# Target",
        f"IDEA_PROVIDER={stringify_env_value(target.get('provider'))}",
        f"IDEA_CLUSTER_TYPE={stringify_env_value(target.get('cluster_type'))}",
        f"IDEA_NAMESPACE={stringify_env_value(target.get('namespace'))}",
        f"IDEA_SERVICE_PORT={stringify_env_value(target.get('service_port'))}",
        f"IDEA_NCLOUD_REGION_CODE={stringify_env_value(ncloud.get('region_code'))}",
        f"IDEA_NCLOUD_CLUSTER_NAME={stringify_env_value(ncloud.get('cluster_name'))}",
        f"IDEA_NCLOUD_CLUSTER_UUID={stringify_env_value(ncloud.get('cluster_uuid'))}",
        f"IDEA_NCLOUD_CLUSTER_VERSION={stringify_env_value(ncloud.get('cluster_version'))}",
        f"IDEA_NCLOUD_CLUSTER_TYPE_CODE={stringify_env_value(ncloud.get('cluster_type_code'))}",
        f"IDEA_NCLOUD_HYPERVISOR_CODE={stringify_env_value(ncloud.get('hypervisor_code'))}",
        f"IDEA_NCLOUD_AUTH_METHOD={stringify_env_value(ncloud.get('auth_method'))}",
        f"IDEA_NCLOUD_ACCESS_KEY_SECRET_REF={stringify_env_value(ncloud.get('access_key_secret_ref'))}",
        f"IDEA_NCLOUD_SECRET_KEY_SECRET_REF={stringify_env_value(ncloud.get('secret_key_secret_ref'))}",
        f"IDEA_NCLOUD_ZONE_CODE={stringify_env_value(ncloud.get('zone_code'))}",
        f"IDEA_NCLOUD_VPC_NO={stringify_env_value(ncloud.get('vpc_no'))}",
        f"IDEA_NCLOUD_SUBNET_NO={stringify_env_value(ncloud.get('subnet_no'))}",
        f"IDEA_NCLOUD_LB_SUBNET_NO={stringify_env_value(ncloud.get('lb_subnet_no'))}",
        f"IDEA_NCLOUD_LB_PUBLIC_SUBNET_NO={stringify_env_value(ncloud.get('lb_public_subnet_no'))}",
        f"IDEA_NCLOUD_NODE_POOL_ID={stringify_env_value(ncloud.get('node_pool_id'))}",
        f"IDEA_NCLOUD_LOGIN_KEY_NAME={stringify_env_value(ncloud.get('login_key_name'))}",
        f"IDEA_NCLOUD_NODE_POOL_NAME={stringify_env_value(ncloud.get('node_pool_name'))}",
        f"IDEA_NCLOUD_NODE_COUNT={stringify_env_value(ncloud.get('node_count'))}",
        f"IDEA_NCLOUD_NODE_PRODUCT_CODE={stringify_env_value(ncloud.get('node_product_code'))}",
        f"IDEA_NCLOUD_NODE_IMAGE_LABEL={stringify_env_value(ncloud.get('node_image_label'))}",
        f"IDEA_NCLOUD_BLOCK_STORAGE_SIZE_GB={stringify_env_value(ncloud.get('block_storage_size_gb'))}",
        f"IDEA_NCLOUD_AUTOSCALE_ENABLED={stringify_env_value(ncloud.get('autoscale_enabled'))}",
        f"IDEA_NCLOUD_AUTOSCALE_MIN_NODE_COUNT={stringify_env_value(ncloud.get('autoscale_min_node_count'))}",
        f"IDEA_NCLOUD_AUTOSCALE_MAX_NODE_COUNT={stringify_env_value(ncloud.get('autoscale_max_node_count'))}",
        f"IDEA_NCLOUD_VPC_CIDR={stringify_env_value(ncloud.get('vpc_cidr'))}",
        f"IDEA_NCLOUD_NODE_SUBNET_CIDR={stringify_env_value(ncloud.get('node_subnet_cidr'))}",
        f"IDEA_NCLOUD_LB_PRIVATE_SUBNET_CIDR={stringify_env_value(ncloud.get('lb_private_subnet_cidr'))}",
        f"IDEA_NCLOUD_LB_PUBLIC_SUBNET_CIDR={stringify_env_value(ncloud.get('lb_public_subnet_cidr'))}",
        "",
        "# Routing and delivery",
        f"IDEA_ENTRY_SERVICE_NAME={stringify_env_value(get_path(state, ('routing', 'entry_service_name')))}",
        f"IDEA_BACKEND_SERVICE_NAME={stringify_env_value(get_path(state, ('routing', 'backend_service_name')))}",
        f"IDEA_BACKEND_BASE_PATH={stringify_env_value(get_path(state, ('routing', 'backend_base_path')))}",
        f"IDEA_ADMIN_ALLOWED_SOURCE_IPS={stringify_env_value(get_path(state, ('access', 'admin_allowed_source_ips'), []))}",
        f"IDEA_ENV_ALLOWED_SOURCE_IPS={stringify_env_value(get_path(state, ('access', f'{env_name}_allowed_source_ips'), []))}",
        f"IDEA_PROD_BLUE_GREEN_ENABLED={stringify_env_value(get_path(state, ('delivery', 'prod_blue_green_enabled')))}",
        f"IDEA_HEALTHCHECK_PATH={stringify_env_value(get_path(state, ('delivery', 'healthcheck_path')))}",
        f"IDEA_HEALTHCHECK_TIMEOUT_SECONDS={stringify_env_value(get_path(state, ('delivery', 'healthcheck_timeout_seconds')))}",
        f"IDEA_ROLLBACK_ON_FAILURE={stringify_env_value(get_path(state, ('delivery', 'rollback_on_failure')))}",
        "",
        "# Provisioning",
        f"IDEA_TERRAFORM_EXECUTABLE={stringify_env_value(get_path(state, ('provisioning', 'terraform_executable')))}",
        f"IDEA_PROVISION_SITE={stringify_env_value(get_path(state, ('provisioning', 'site')))}",
        "",
        "# Runtime variables",
    ]

    for key, value in sorted((state.get("env", {}).get(env_name) or {}).items()):
        lines.append(f"{key}={stringify_env_value(value)}")

    lines.extend(["", "# Runtime secrets"])
    for key, value in sorted((state.get("secrets", {}).get(env_name) or {}).items()):
        lines.append(f"{key}={stringify_env_value(value)}")

    return "\n".join(lines).strip() + "\n"


def write_export_env_file(output_root: Path, project_name: str, selected_env: str, env_text: str) -> Path:
    output_dir = output_root / project_name / selected_env
    output_dir.mkdir(parents=True, exist_ok=True)
    env_path = output_dir / f"{project_name}_{selected_env}.runtime.env"
    env_path.write_text(env_text, encoding="utf-8")
    return env_path
