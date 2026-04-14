#!/usr/bin/env python3

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_TOP_LEVEL = [
    "project",
    "build",
    "argo",
    "cloudflare",
    "targets",
    "routing",
    "env",
    "secrets",
    "access",
    "delivery",
]


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_state(path: Path) -> dict:
    try:
      return json.loads(path.read_text())
    except FileNotFoundError:
      fail(f"state file not found: {path}")
    except json.JSONDecodeError as exc:
      fail(f"invalid json in {path}: {exc}")


def require_keys(obj: dict, keys: list[str], prefix: str) -> None:
    for key in keys:
        if key not in obj:
            fail(f"missing required field: {prefix}{key}")


def build_hostname(subdomain: str, base_domain: str) -> str:
    normalized_base = (base_domain or "").strip().lower()
    normalized_subdomain = (subdomain or "").strip().lower()

    if not normalized_base:
        return ""

    if normalized_subdomain in {"", "@", "*"}:
        return normalized_base

    return f"{normalized_subdomain}.{normalized_base}"


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def clone_repo(repo_url: str, git_ref: str, dest: Path) -> Path:
    run(["git", "clone", "--depth", "1", "--branch", git_ref, repo_url, str(dest)])
    return dest


def collect_secret_refs(state: dict) -> list[str]:
    refs: set[str] = set()

    for path in [
        ("project", "repo_access_secret_ref"),
        ("argo", "gitops_repo_access_secret_ref"),
        ("cloudflare", "api_token_secret_ref"),
    ]:
        value = state.get(path[0], {}).get(path[1])
        if value:
            refs.add(value)

    for target in state.get("targets", {}).values():
        provider = target.get("provider")
        if provider == "ncloud":
            for key in ["access_key_secret_ref", "secret_key_secret_ref"]:
                value = target.get("ncloud", {}).get(key)
                if value:
                    refs.add(value)
        cluster_access = target.get("cluster_access_secret_ref")
        if cluster_access:
            refs.add(cluster_access)

    for secret_map in state.get("secrets", {}).values():
        for value in secret_map.values():
            if isinstance(value, str):
                refs.add(value)

    return sorted(refs)


def normalized_cloudflare_environments(cloudflare: dict) -> dict[str, dict]:
    environments = dict(cloudflare.get("environments") or {})

    if environments:
      for env_name in ["dev", "stage", "prod"]:
          environments.setdefault(env_name, {})
      return environments

    base_domain = cloudflare.get("base_domain", "")
    prefix = cloudflare.get("public_subdomain_prefix", "")
    legacy_suffix = {"dev": "-dev", "stage": "-stage", "prod": ""}

    return {
        env_name: {
            "subdomain": f"{prefix}{legacy_suffix[env_name]}" if prefix else "",
            "base_domain": base_domain,
        }
        for env_name in ["dev", "stage", "prod"]
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run validator for idea runtime Project State."
    )
    parser.add_argument("state_path", help="Path to Project State JSON file.")
    args = parser.parse_args()

    state_path = Path(args.state_path).resolve()
    state = load_state(state_path)
    require_keys(state, REQUIRED_TOP_LEVEL, "")

    project = state["project"]
    build = state["build"]
    argo = state["argo"]
    cloudflare = state["cloudflare"]
    routing = state["routing"]

    require_keys(project, ["name", "app_repo_url", "git_ref"], "project.")
    require_keys(
        build,
        [
            "source_strategy",
            "frontend_context",
            "frontend_dockerfile_path",
            "backend_context",
            "backend_dockerfile_path",
        ],
        "build.",
    )
    require_keys(
        argo,
        [
            "project_name",
            "destination_name",
            "gitops_repo_url",
            "gitops_repo_branch",
            "gitops_repo_path",
        ],
        "argo.",
    )
    require_keys(
        cloudflare,
        [
            "enabled",
            "account_id",
            "zone_id",
            "api_token_secret_ref",
            "tunnel_name",
            "route_mode",
        ],
        "cloudflare.",
    )
    require_keys(
        routing,
        [
            "dev_hostname",
            "stage_hostname",
            "prod_hostname",
            "entry_service_name",
            "backend_service_name",
            "backend_base_path",
        ],
        "routing.",
    )

    cloudflare_environments = normalized_cloudflare_environments(cloudflare)
    require_keys(cloudflare_environments, ["dev", "stage", "prod"], "cloudflare.environments.")

    for env_name in ["dev", "stage", "prod"]:
        require_keys(
            cloudflare_environments[env_name],
            ["subdomain", "base_domain"],
            f"cloudflare.environments.{env_name}.",
        )
        expected_hostname = build_hostname(
            cloudflare_environments[env_name]["subdomain"],
            cloudflare_environments[env_name]["base_domain"],
        )
        if routing.get(f"{env_name}_hostname") != expected_hostname:
            fail(
                f"routing.{env_name}_hostname does not match cloudflare.environments.{env_name}: "
                f"{routing.get(f'{env_name}_hostname')} != {expected_hostname}"
            )

    for env_name in ["dev", "stage", "prod"]:
        if env_name not in state["targets"]:
            fail(f"missing required field: targets.{env_name}")
        target = state["targets"][env_name]
        require_keys(target, ["provider", "cluster_type", "namespace", "service_port"], f"targets.{env_name}.")
        if target["provider"] == "ncloud":
            require_keys(
                target.get("ncloud", {}),
                ["region_code", "cluster_name", "auth_method"],
                f"targets.{env_name}.ncloud.",
            )

    workdir = Path(tempfile.mkdtemp(prefix="idea-project-state-"))
    repo_dir = workdir / "repo"
    try:
        clone_repo(project["app_repo_url"], project["git_ref"], repo_dir)

        frontend_context = repo_dir / build["frontend_context"]
        backend_context = repo_dir / build["backend_context"]
        frontend_dockerfile = repo_dir / build["frontend_dockerfile_path"]
        backend_dockerfile = repo_dir / build["backend_dockerfile_path"]
        compose_file = repo_dir / "docker-compose.yml"

        for path, label in [
            (frontend_context, "frontend context"),
            (backend_context, "backend context"),
            (frontend_dockerfile, "frontend Dockerfile"),
            (backend_dockerfile, "backend Dockerfile"),
        ]:
            if not path.exists():
                fail(f"{label} not found: {path.relative_to(repo_dir)}")

        summary = {
            "project": project["name"],
            "repo_url": project["app_repo_url"],
            "git_ref": project["git_ref"],
            "repo_root": str(repo_dir),
            "compose_present": compose_file.exists(),
            "checked_paths": {
                "frontend_context": build["frontend_context"],
                "frontend_dockerfile_path": build["frontend_dockerfile_path"],
                "backend_context": build["backend_context"],
                "backend_dockerfile_path": build["backend_dockerfile_path"],
            },
            "routing": {
                "dev_hostname": routing["dev_hostname"],
                "stage_hostname": routing["stage_hostname"],
                "prod_hostname": routing["prod_hostname"],
                "entry_service_name": routing["entry_service_name"],
                "backend_service_name": routing["backend_service_name"],
                "backend_base_path": routing["backend_base_path"],
            },
            "targets": state["targets"],
            "required_secret_refs": collect_secret_refs(state),
            "gitops": {
                "repo_url": argo["gitops_repo_url"],
                "branch": argo["gitops_repo_branch"],
                "path": argo["gitops_repo_path"],
                "destination_name": argo["destination_name"],
            },
            "cloudflare": {
                "enabled": cloudflare["enabled"],
                "environments": cloudflare_environments,
                "tunnel_name": cloudflare["tunnel_name"],
                "route_mode": cloudflare["route_mode"],
            },
        }

        print(json.dumps(summary, indent=2, ensure_ascii=True))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
