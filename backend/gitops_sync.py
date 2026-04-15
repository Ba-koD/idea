from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from time import monotonic, sleep
from typing import Any, Callable
from urllib.parse import quote, urlparse

import generator
from env_import import split_runtime_secrets
from provisioning import (
    DEFAULT_KUBECTL_EXECUTABLE,
    kube_api_request,
    normalize_secret_ref_name,
    reconcile_cloudflare_environment_access,
    resolve_secret_value,
    secret_env_var_name,
)

GITOPS_MANIFEST_FILE_NAMES = (
    "namespace.yaml",
    "runtime-configmap.yaml",
    "app-stack.yaml",
)
PLATFORM_CADDY_NAMESPACE = os.getenv("IDEA_PLATFORM_CADDY_NAMESPACE", "edge-system").strip() or "edge-system"
PLATFORM_CADDY_CONFIGMAP_NAME = os.getenv("IDEA_PLATFORM_CADDY_CONFIGMAP_NAME", "platform-caddy").strip() or "platform-caddy"
PLATFORM_CADDY_DEPLOYMENT_NAME = os.getenv("IDEA_PLATFORM_CADDY_DEPLOYMENT_NAME", "platform-caddy").strip() or "platform-caddy"
TOKEN_REDACTION_PATTERNS = (
    (re.compile(r"(https?://[^/\s:@]+:)[^@/\s]+(@)"), r"\1***\2"),
    (re.compile(r"github_pat_[A-Za-z0-9_]+"), "github_pat_***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]+\b"), "gh***"),
    (re.compile(r"\bcfut_[A-Za-z0-9]+\b", re.IGNORECASE), "cfut_***"),
    (re.compile(r"\bncp_iam_[A-Za-z0-9]+\b", re.IGNORECASE), "ncp_iam_***"),
)


def run_git_command(
    command: list[str],
    workdir: Path,
    env: dict[str, str],
    log_callback: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    def sanitize(text: str) -> str:
        sanitized = str(text or "")
        for pattern, replacement in TOKEN_REDACTION_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    process = subprocess.Popen(
        command,
        cwd=str(workdir),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output_lines: list[str] = []
    if log_callback is not None:
        log_callback(sanitize(f"$ {' '.join(command)}"))

    assert process.stdout is not None
    for line in process.stdout:
        output_lines.append(line)
        cleaned = sanitize(line.rstrip())
        if cleaned and log_callback is not None:
            log_callback(cleaned)

    returncode = process.wait()
    return subprocess.CompletedProcess(command, returncode, stdout=sanitize("".join(output_lines)), stderr="")


def git_authenticated_url(repo_url: str, token: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme in {"", "file"}:
        return repo_url
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported GitOps repo URL scheme: {parsed.scheme or '(empty)'}")
    if not parsed.netloc:
        raise ValueError("GitOps repo URL must include a hostname.")
    return f"{parsed.scheme}://x-access-token:{quote(token, safe='')}@{parsed.netloc}{parsed.path}"


def control_plane_env_secret_value(secret_ref: str) -> str:
    normalized_ref = normalize_secret_ref_name(secret_ref)
    env_names = [
        secret_env_var_name(secret_ref),
        normalized_ref.replace("-", "_").upper(),
    ]
    for env_name in env_names:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return ""


def build_git_token_candidates(
    project_state: dict[str, Any],
    primary_secret_ref: str,
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen_refs: set[str] = set()

    def add(secret_ref: str) -> None:
        normalized_ref = normalize_secret_ref_name(secret_ref)
        if not normalized_ref or normalized_ref in seen_refs:
            return
        seen_refs.add(normalized_ref)
        value = control_plane_env_secret_value(secret_ref)
        if value:
            candidates.append((normalized_ref, value))

    add(primary_secret_ref)
    add(project_state.get("project", {}).get("repo_access_secret_ref", ""))
    add(project_state.get("argo", {}).get("gitops_repo_access_secret_ref", ""))
    return candidates


def is_git_auth_error(output: str) -> bool:
    normalized = str(output or "")
    return (
        "requested url returned error: 403" in normalized.lower()
        or "permission to " in normalized.lower()
        or "authentication failed" in normalized.lower()
    )


def build_argocd_application_manifest(project_state: dict[str, Any], selected_env: str) -> dict[str, Any]:
    project = project_state["project"]
    argo = project_state["argo"]
    target = project_state["targets"][selected_env]

    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": f"{project['name']}-{selected_env}",
            "namespace": "argocd",
            "labels": {
                "idea.rnen.kr/project": project["name"],
                "idea.rnen.kr/environment": selected_env,
            },
            "annotations": {
                "argocd.argoproj.io/refresh": "hard",
            },
        },
        "spec": {
            "project": argo["project_name"],
            "destination": {
                "namespace": target["namespace"],
                "server": argo["destination_server"],
            },
            "source": {
                "repoURL": argo["gitops_repo_url"],
                "targetRevision": argo["gitops_repo_branch"],
                "path": f"{argo['gitops_repo_path']}/{selected_env}",
            },
            "syncPolicy": {
                "automated": {
                    "prune": True,
                    "selfHeal": True,
                },
                "syncOptions": [
                    "CreateNamespace=true",
                ],
            },
        },
    }


def apply_argocd_application_to_platform(project_state: dict[str, Any], selected_env: str) -> dict[str, Any]:
    manifest = build_argocd_application_manifest(project_state, selected_env)
    app_name = manifest["metadata"]["name"]
    app_path = f"/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/{quote(app_name, safe='')}"
    existing = kube_api_request(app_path, expected_statuses=(200, 404))

    if existing["status"] == 404:
        kube_api_request(
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications",
            method="POST",
            body=manifest,
            expected_statuses=(200, 201),
        )
        action = "created"
    else:
        kube_api_request(
            app_path,
            method="PATCH",
            body=manifest,
            expected_statuses=(200,),
            headers={"Content-Type": "application/merge-patch+json"},
        )
        action = "updated"

    return {
        "application_name": app_name,
        "action": action,
        "logs": [f"Argo CD application {app_name} {action} in the platform cluster."],
    }


def collect_gitops_source_manifests(output_dir: Path) -> list[Path]:
    manifests: list[Path] = []
    for file_name in GITOPS_MANIFEST_FILE_NAMES:
        candidate = output_dir / file_name
        if candidate.exists():
            manifests.append(candidate)
    return manifests


def uses_platform_cluster(project_state: dict[str, Any]) -> bool:
    destination_server = str(project_state.get("argo", {}).get("destination_server", "")).strip().rstrip("/")
    return destination_server in {"", "https://kubernetes.default.svc", "http://kubernetes.default.svc"}


def wait_for_platform_namespace(
    namespace: str,
    *,
    log_callback: Callable[[str], None] | None = None,
    timeout_seconds: int = 120,
) -> None:
    started_at = monotonic()
    while monotonic() - started_at < timeout_seconds:
        response = kube_api_request(f"/api/v1/namespaces/{quote(namespace, safe='')}", expected_statuses=(200, 404))
        if response["status"] == 200:
            return
        sleep(2)
    raise RuntimeError(f"Timed out waiting for namespace {namespace} to exist in the platform cluster.")


def apply_runtime_secret_to_platform_cluster(
    project_state: dict[str, Any],
    selected_env: str,
) -> list[str]:
    runtime_inline_secrets, _ = split_runtime_secrets(project_state["secrets"][selected_env])
    if not runtime_inline_secrets:
        return ["Skipped direct runtime secret apply because no inline runtime secrets were configured."]

    namespace = project_state["targets"][selected_env]["namespace"]
    project_name = project_state["project"]["name"]
    secret_name = f"{project_name}-{selected_env}-runtime-secrets"
    wait_for_platform_namespace(namespace)
    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
            "labels": {
                "idea.rnen.kr/project": project_name,
                "idea.rnen.kr/environment": selected_env,
            },
        },
        "type": "Opaque",
        "stringData": {
            key: str(value).lstrip("\r\n")
            for key, value in runtime_inline_secrets.items()
        },
    }
    secret_path = f"/api/v1/namespaces/{quote(namespace, safe='')}/secrets/{quote(secret_name, safe='')}"
    existing = kube_api_request(secret_path, expected_statuses=(200, 404))
    if existing["status"] == 404:
        kube_api_request(
            f"/api/v1/namespaces/{quote(namespace, safe='')}/secrets",
            method="POST",
            body=manifest,
            expected_statuses=(200, 201),
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
    return [f"{action.capitalize()} runtime secret {secret_name} directly in platform namespace {namespace}."]


def render_platform_caddy_env_route(project_state: dict[str, Any], selected_env: str) -> str:
    hostname = str(project_state["routing"].get(f"{selected_env}_hostname", "")).strip()
    if not hostname:
        raise ValueError(f"No routing hostname is configured for {selected_env}.")

    namespace = project_state["targets"][selected_env]["namespace"]
    backend_service_name = str(project_state["routing"].get("backend_service_name", "backend")).strip() or "backend"
    frontend_service_name = str(project_state["routing"].get("frontend_service_name", "frontend")).strip() or "frontend"
    route_id = re.sub(r"[^a-z0-9]+", "", f"{project_state['project']['name']}-{selected_env}".lower()) or selected_env
    start_marker = f"# BEGIN IDEA ENV {project_state['project']['name']} {selected_env}"
    end_marker = f"# END IDEA ENV {project_state['project']['name']} {selected_env}"
    return "\n".join(
        [
            f"  {start_marker}",
            f"  @{route_id} host {hostname}",
            f"  @{route_id}_api path /api*",
            f"  handle @{route_id} {{",
            f"    handle @{route_id}_api {{",
            f"      reverse_proxy http://{backend_service_name}.{namespace}.svc.cluster.local:8080",
            "    }",
            "",
            "    handle {",
            f"      reverse_proxy http://{frontend_service_name}.{namespace}.svc.cluster.local:80",
            "    }",
            "  }",
            f"  {end_marker}",
        ]
    )


def upsert_marked_block(text: str, block: str, start_marker: str, end_marker: str) -> str:
    pattern = re.compile(
        rf"(?ms)^[ \t]*{re.escape(start_marker)}.*?^[ \t]*{re.escape(end_marker)}\n?"
    )
    if pattern.search(text):
        return pattern.sub(f"{block}\n", text)

    default_handle = '  handle {\n    respond "Not Found" 404\n  }\n}'
    if default_handle in text:
        return text.replace(default_handle, f"{block}\n\n{default_handle}", 1)
    raise RuntimeError("platform-caddy ConfigMap did not contain the expected default Not Found handler.")


def reconcile_platform_caddy_environment_route(
    project_state: dict[str, Any],
    selected_env: str,
) -> list[str]:
    route_block = render_platform_caddy_env_route(project_state, selected_env)
    start_marker = f"# BEGIN IDEA ENV {project_state['project']['name']} {selected_env}"
    end_marker = f"# END IDEA ENV {project_state['project']['name']} {selected_env}"
    configmap_path = (
        f"/api/v1/namespaces/{quote(PLATFORM_CADDY_NAMESPACE, safe='')}/configmaps/"
        f"{quote(PLATFORM_CADDY_CONFIGMAP_NAME, safe='')}"
    )
    current = kube_api_request(configmap_path, expected_statuses=(200,))
    configmap = current["body"]
    current_caddyfile = str(configmap.get("data", {}).get("Caddyfile", "")).rstrip() + "\n"
    next_caddyfile = upsert_marked_block(current_caddyfile, route_block, start_marker, end_marker)
    if next_caddyfile == current_caddyfile:
        updated = False
    else:
        kube_api_request(
            configmap_path,
            method="PATCH",
            body={"data": {"Caddyfile": next_caddyfile}},
            expected_statuses=(200,),
            headers={"Content-Type": "application/merge-patch+json"},
        )
        restart_path = (
            f"/apis/apps/v1/namespaces/{quote(PLATFORM_CADDY_NAMESPACE, safe='')}/deployments/"
            f"{quote(PLATFORM_CADDY_DEPLOYMENT_NAME, safe='')}"
        )
        kube_api_request(
            restart_path,
            method="PATCH",
            body={
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "idea.rnen.kr/restarted-at": datetime.now(timezone.utc).isoformat()
                            }
                        }
                    }
                }
            },
            expected_statuses=(200,),
            headers={"Content-Type": "application/merge-patch+json"},
        )
        updated = True
    hostname = str(project_state["routing"].get(f"{selected_env}_hostname", "")).strip()
    return [
        (
            f"Updated platform-caddy route for {hostname} and restarted {PLATFORM_CADDY_DEPLOYMENT_NAME}."
            if updated
            else f"platform-caddy route for {hostname} was already up to date."
        )
    ]


def read_repo_text(repo_dir: Path, relative_path: str) -> str:
    candidate = repo_dir / relative_path
    if not candidate.exists():
        raise FileNotFoundError(f"Expected app repo file was missing: {relative_path}")
    return candidate.read_text(encoding="utf-8").rstrip("\n")


def repo_example_frontend_nginx_template(backend_service_name: str) -> str:
    return "\n".join(
        [
            "server {",
            "    listen 80;",
            "    server_name _;",
            "",
            "    root /usr/share/nginx/html;",
            "    index index.html;",
            "",
            "    location = /config.js {",
            '        add_header Cache-Control "no-store";',
            "        try_files $uri =404;",
            "    }",
            "",
            "    location /api/ {",
            f"        proxy_pass http://{backend_service_name}:8080;",
            "        proxy_http_version 1.1;",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "        proxy_set_header X-Forwarded-Proto $scheme;",
            "    }",
            "",
            "    location = /api {",
            f"        proxy_pass http://{backend_service_name}:8080;",
            "        proxy_http_version 1.1;",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "        proxy_set_header X-Forwarded-Proto $scheme;",
            "    }",
            "",
            "    location / {",
            "        try_files $uri /index.html;",
            "    }",
            "}",
        ]
    )


def render_repo_example_stack(output_dir: Path, project_state: dict[str, Any], selected_env: str, repo_dir: Path) -> Path:
    runtime_inline_secrets, _ = split_runtime_secrets(project_state["secrets"][selected_env])
    runtime_secret_keys = sorted(runtime_inline_secrets.keys())
    runtime_env = deepcopy(project_state["env"][selected_env])
    frontend_env = {
        key: value
        for key, value in runtime_env.items()
        if key in {"APP_ENV", "APP_DISPLAY_NAME", "PUBLIC_API_BASE_URL"}
    }
    frontend_env.setdefault("PUBLIC_API_BASE_URL", "/api")

    postgres_db = str(runtime_env.get("POSTGRES_DB", "idea")).strip() or "idea"
    postgres_user = str(runtime_env.get("POSTGRES_USER", "idea")).strip() or "idea"

    context = {
        "project": project_state["project"],
        "selected_env": selected_env,
        "target": project_state["targets"][selected_env],
        "runtime_env": runtime_env,
        "runtime_secret_keys": runtime_secret_keys,
        "frontend_env": frontend_env,
        "postgres_db": postgres_db,
        "postgres_user": postgres_user,
        "db_storage_size": "5Gi",
        "frontend_index_html": read_repo_text(repo_dir, "frontend/public/index.html"),
        "frontend_app_js": read_repo_text(repo_dir, "frontend/public/app.js"),
        "frontend_config_js_template": read_repo_text(repo_dir, "frontend/public/config.js.template"),
        "frontend_entrypoint_script": read_repo_text(repo_dir, "frontend/docker-entrypoint.d/30-render-config.sh"),
        "frontend_nginx_template": repo_example_frontend_nginx_template(
            str(project_state["routing"].get("backend_service_name", "backend")).strip() or "backend"
        ),
        "backend_package_json": read_repo_text(repo_dir, "backend/package.json"),
        "backend_db_js": read_repo_text(repo_dir, "backend/db.js"),
        "backend_server_js": read_repo_text(repo_dir, "backend/server.js"),
    }

    destination = output_dir / "app-stack.yaml"
    destination.write_text(generator.render_template("repo-example-stack.yaml.j2", context), encoding="utf-8")
    return destination


def target_runtime_dir(output_root: Path, project_name: str, selected_env: str) -> Path:
    return output_root / project_name / selected_env / "ncloud-runtime"


def target_kubeconfig_path(output_root: Path, project_name: str, selected_env: str) -> Path | None:
    runtime_dir = target_runtime_dir(output_root, project_name, selected_env)
    for file_name in ("ncloud-iam-kubeconfig.yaml", "kubeconfig.yaml"):
        candidate = runtime_dir / file_name
        if candidate.exists():
            return candidate
    return None


def run_target_kubectl(
    command: list[str],
    kubeconfig_path: Path,
    log_callback: Callable[[str], None] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "KUBECONFIG": str(kubeconfig_path),
    }
    process = subprocess.run(
        [DEFAULT_KUBECTL_EXECUTABLE, *command],
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
        env=env,
    )
    if log_callback is not None:
        log_callback(f"$ {DEFAULT_KUBECTL_EXECUTABLE} {' '.join(command)}")
        combined = (process.stdout or "") + (process.stderr or "")
        for line in combined.splitlines():
            if line.strip():
                log_callback(line.rstrip())
    return process


def apply_runtime_secret_to_target_cluster(
    project_state: dict[str, Any],
    selected_env: str,
    output_root: Path,
    log_callback: Callable[[str], None] | None = None,
) -> list[str]:
    project_name = project_state["project"]["name"]
    secret_manifest = output_root / project_name / selected_env / "runtime-secret.yaml"
    if not secret_manifest.exists():
        return ["Skipped direct runtime secret apply because no inline runtime secrets were configured."]

    kubeconfig_path = target_kubeconfig_path(output_root, project_name, selected_env)
    if kubeconfig_path is None:
        return ["Skipped direct runtime secret apply because no target kubeconfig was available yet."]

    apply_result = run_target_kubectl(["apply", "-f", "-"], kubeconfig_path, log_callback=log_callback, input_text=secret_manifest.read_text(encoding="utf-8"))
    if apply_result.returncode != 0:
        raise RuntimeError(f"kubectl apply failed for runtime-secret.yaml:\n{(apply_result.stderr or apply_result.stdout).strip()}")
    return [f"Applied runtime secret directly to {selected_env} target cluster from {secret_manifest.name}."]


def wait_for_frontend_service_url(
    project_state: dict[str, Any],
    selected_env: str,
    output_root: Path,
    log_callback: Callable[[str], None] | None = None,
    timeout_seconds: int = 600,
) -> str:
    project_name = project_state["project"]["name"]
    namespace = project_state["targets"][selected_env]["namespace"]
    kubeconfig_path = target_kubeconfig_path(output_root, project_name, selected_env)
    if kubeconfig_path is None:
        raise RuntimeError("No target kubeconfig was available while waiting for the frontend load balancer.")

    started_at = monotonic()
    while monotonic() - started_at < timeout_seconds:
        result = run_target_kubectl(["-n", namespace, "get", "service", "frontend", "-o", "json"], kubeconfig_path, log_callback=None)
        if result.returncode == 0 and result.stdout.strip():
            payload = json.loads(result.stdout)
            ingress = payload.get("status", {}).get("loadBalancer", {}).get("ingress", []) or []
            if ingress:
                endpoint = ingress[0].get("hostname") or ingress[0].get("ip") or ""
                if endpoint:
                    if log_callback is not None:
                        log_callback(f"Resolved frontend LoadBalancer endpoint for {selected_env}: {endpoint}")
                    return f"http://{endpoint}:80"
        sleep(5)

    raise RuntimeError(f"Timed out waiting for the frontend LoadBalancer endpoint in namespace {namespace}.")


def sync_gitops_repo(
    project_state: dict[str, Any],
    selected_env: str,
    output_root: Path,
    log_callback: Callable[[str], None] | None = None,
    apply_argocd: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = deepcopy(project_state)
    project = state["project"]
    argo = state["argo"]
    target = state["targets"][selected_env]

    gitops_repo_url = str(argo.get("gitops_repo_url", "")).strip()
    gitops_repo_branch = str(argo.get("gitops_repo_branch", "main")).strip() or "main"
    gitops_repo_path = str(argo.get("gitops_repo_path", "")).strip().strip("/")
    access_token_ref = str(argo.get("gitops_repo_access_secret_ref", "")).strip()
    access_token = resolve_secret_value(state, access_token_ref)
    fallback_token_candidates = [
        (ref, value)
        for ref, value in build_git_token_candidates(state, access_token_ref)
        if value and value != access_token
    ]

    if not gitops_repo_url:
        raise ValueError("argo.gitops_repo_url must be configured before GitOps sync can run.")
    if not gitops_repo_path:
        raise ValueError("argo.gitops_repo_path must be configured before GitOps sync can run.")
    if not access_token and urlparse(gitops_repo_url).scheme not in {"", "file"}:
        raise ValueError(
            f"GitOps repo access token for {access_token_ref!r} is missing. "
            "Import IDEA_GITOPS_REPO_ACCESS_TOKEN_VALUE before syncing GitOps."
        )
    if not str(target["ncloud"].get("cluster_uuid", "")).strip():
        raise ValueError("Provision the selected environment first so Argo CD has a target cluster to sync to.")

    logs: list[str] = []

    def emit(message: str) -> None:
        logs.append(message)
        if log_callback is not None:
            log_callback(message)

    output_dir = generator.generate_all(state, selected_env)

    emit(f"Generated manifests in {output_dir}.")
    emit(f"Preparing GitOps sync for {project['name']} {selected_env.upper()} using {gitops_repo_url}#{gitops_repo_branch}.")

    temp_dir = Path(mkdtemp(prefix=f"idea-gitops-{selected_env}-"))
    authenticated_repo_url = git_authenticated_url(gitops_repo_url, access_token)
    clone_env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
    }

    try:
        clone_result = run_git_command(
            ["git", "clone", "--depth", "1", "--branch", gitops_repo_branch, authenticated_repo_url, str(temp_dir / "repo")],
            temp_dir,
            clone_env,
            log_callback=log_callback,
        )
        if clone_result.returncode != 0:
            clone_error = clone_result.stdout.strip()
            if fallback_token_candidates and is_git_auth_error(clone_error):
                for fallback_secret_ref, fallback_token in fallback_token_candidates:
                    emit(
                        f"Primary GitOps token could not clone the repo. "
                        f"Retrying with platform control-plane fallback secret {fallback_secret_ref}."
                    )
                    fallback_repo_url = git_authenticated_url(gitops_repo_url, fallback_token)
                    clone_result = run_git_command(
                        ["git", "clone", "--depth", "1", "--branch", gitops_repo_branch, fallback_repo_url, str(temp_dir / "repo")],
                        temp_dir,
                        clone_env,
                        log_callback=log_callback,
                    )
                    if clone_result.returncode == 0:
                        authenticated_repo_url = fallback_repo_url
                        break
            if clone_result.returncode != 0:
                raise RuntimeError(f"git clone failed:\n{clone_result.stdout.strip()}")

        repo_dir = temp_dir / "repo"
        render_repo_example_stack(output_dir, state, selected_env, repo_dir)
        manifest_files = collect_gitops_source_manifests(output_dir)
        if not manifest_files:
            raise ValueError("No Kubernetes manifests were generated for GitOps sync.")

        target_dir = repo_dir / gitops_repo_path / selected_env
        target_dir.mkdir(parents=True, exist_ok=True)

        for child in target_dir.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

        copied_files: list[str] = []
        for manifest_file in manifest_files:
            destination = target_dir / manifest_file.name
            shutil.copy2(manifest_file, destination)
            copied_files.append(destination.name)

        emit(f"Updated GitOps source path {gitops_repo_path}/{selected_env} with {', '.join(sorted(copied_files))}.")

        run_git_command(
            ["git", "config", "user.name", "IDEA Platform"],
            repo_dir,
            clone_env,
            log_callback=log_callback,
        )
        run_git_command(
            ["git", "config", "user.email", "idea-platform@local"],
            repo_dir,
            clone_env,
            log_callback=log_callback,
        )

        status_result = run_git_command(["git", "status", "--porcelain"], repo_dir, clone_env, log_callback=None)
        changed = bool(status_result.stdout.strip())
        commit_sha = ""

        if changed:
            add_result = run_git_command(["git", "add", "."], repo_dir, clone_env, log_callback=log_callback)
            if add_result.returncode != 0:
                raise RuntimeError(f"git add failed:\n{add_result.stdout.strip()}")

            commit_message = f"gitops({project['name']}/{selected_env}): sync app manifests"
            commit_result = run_git_command(["git", "commit", "-m", commit_message], repo_dir, clone_env, log_callback=log_callback)
            if commit_result.returncode != 0:
                raise RuntimeError(f"git commit failed:\n{commit_result.stdout.strip()}")

            push_result = run_git_command(["git", "push", "origin", gitops_repo_branch], repo_dir, clone_env, log_callback=log_callback)
            if push_result.returncode != 0:
                push_error = push_result.stdout.strip()
                if fallback_token_candidates and is_git_auth_error(push_error):
                    for fallback_secret_ref, fallback_token in fallback_token_candidates:
                        emit(
                            f"Primary GitOps token could not push to the repo. "
                            f"Retrying with platform control-plane fallback secret {fallback_secret_ref}."
                        )
                        fallback_repo_url = git_authenticated_url(gitops_repo_url, fallback_token)
                        remote_result = run_git_command(
                            ["git", "remote", "set-url", "origin", fallback_repo_url],
                            repo_dir,
                            clone_env,
                            log_callback=log_callback,
                        )
                        if remote_result.returncode != 0:
                            raise RuntimeError(f"git remote set-url failed:\n{remote_result.stdout.strip()}")
                        push_result = run_git_command(["git", "push", "origin", gitops_repo_branch], repo_dir, clone_env, log_callback=log_callback)
                        if push_result.returncode == 0:
                            break
                if push_result.returncode != 0:
                    raise RuntimeError(f"git push failed:\n{push_result.stdout.strip()}")

            rev_result = run_git_command(["git", "rev-parse", "HEAD"], repo_dir, clone_env, log_callback=None)
            if rev_result.returncode == 0:
                commit_sha = rev_result.stdout.strip()
            emit(f"Pushed GitOps commit {commit_sha or '(unknown sha)'} to {gitops_repo_branch}.")
        else:
            emit("GitOps repo already matched the generated manifests. No commit was required.")

        integration_logs: list[str] = []
        integration_warnings: list[str] = []
        frontend_service_url = ""

        if apply_argocd:
            try:
                app_result = apply_argocd_application_to_platform(state, selected_env)
                integration_logs.extend(app_result["logs"])
            except Exception as exc:
                integration_warnings.append(f"Argo CD application apply did not complete: {exc}")

        if uses_platform_cluster(state):
            try:
                secret_apply_logs = apply_runtime_secret_to_platform_cluster(
                    state,
                    selected_env,
                )
                integration_logs.extend(secret_apply_logs)
            except Exception as exc:
                integration_warnings.append(f"Runtime secret apply did not complete: {exc}")

            try:
                caddy_logs = reconcile_platform_caddy_environment_route(
                    state,
                    selected_env,
                )
                integration_logs.extend(caddy_logs)
            except Exception as exc:
                integration_warnings.append(f"Platform edge routing did not complete: {exc}")
        else:
            try:
                secret_apply_logs = apply_runtime_secret_to_target_cluster(
                    state,
                    selected_env,
                    output_root,
                    log_callback=log_callback,
                )
                integration_logs.extend(secret_apply_logs)
            except Exception as exc:
                integration_warnings.append(f"Runtime secret apply did not complete: {exc}")

            try:
                frontend_service_url = wait_for_frontend_service_url(
                    state,
                    selected_env,
                    output_root,
                    log_callback=log_callback,
                )
            except Exception as exc:
                integration_warnings.append(f"Frontend LoadBalancer discovery did not complete: {exc}")

        try:
            cloudflare_result = reconcile_cloudflare_environment_access(
                state,
                selected_env,
                service_url=frontend_service_url or None,
            )
            integration_logs.extend(cloudflare_result.get("logs", []))
            integration_warnings.extend(cloudflare_result.get("warnings", []))
        except Exception as exc:
            integration_warnings.append(
                "Cloudflare environment routing did not complete. "
                f"Reason: {exc}"
            )

        for message in integration_logs:
            emit(message)
        for warning in integration_warnings:
            emit(f"WARNING: {warning}")

        next_result = state.setdefault("provisioning", {}).setdefault("last_results", {}).setdefault(selected_env, {})
        next_result["gitops_status"] = "synced"
        next_result["gitops_synced_at"] = datetime.now(timezone.utc).isoformat()
        next_result["gitops_repo_url"] = gitops_repo_url
        next_result["gitops_repo_branch"] = gitops_repo_branch
        next_result["gitops_repo_path"] = f"{gitops_repo_path}/{selected_env}"
        next_result["gitops_commit_sha"] = commit_sha
        next_result["gitops_application_name"] = f"{project['name']}-{selected_env}"
        next_result["logs_tail"] = logs[-80:]

        return state, {
            "applied": True,
            "logs": logs,
            "gitops_repo_path": f"{gitops_repo_path}/{selected_env}",
            "gitops_commit_sha": commit_sha,
            "gitops_application_name": f"{project['name']}-{selected_env}",
            "frontend_service_url": frontend_service_url,
            "warnings": integration_warnings,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
