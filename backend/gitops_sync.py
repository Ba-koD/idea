from __future__ import annotations

import os
import shutil
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, Callable
from urllib.parse import quote, urlparse

import generator
from provisioning import kube_api_request, resolve_secret_value

GITOPS_MANIFEST_FILE_NAMES = (
    "namespace.yaml",
    "runtime-configmap.yaml",
    "runtime-secret.yaml",
)


def run_git_command(
    command: list[str],
    workdir: Path,
    env: dict[str, str],
    log_callback: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
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
        log_callback(f"$ {' '.join(command)}")

    assert process.stdout is not None
    for line in process.stdout:
        output_lines.append(line)
        cleaned = line.rstrip()
        if cleaned and log_callback is not None:
            log_callback(cleaned)

    returncode = process.wait()
    return subprocess.CompletedProcess(command, returncode, stdout="".join(output_lines), stderr="")


def git_authenticated_url(repo_url: str, token: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme in {"", "file"}:
        return repo_url
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported GitOps repo URL scheme: {parsed.scheme or '(empty)'}")
    if not parsed.netloc:
        raise ValueError("GitOps repo URL must include a hostname.")
    return f"{parsed.scheme}://x-access-token:{quote(token, safe='')}@{parsed.netloc}{parsed.path}"


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
    manifest_files = collect_gitops_source_manifests(output_dir)
    if not manifest_files:
        raise ValueError("No Kubernetes manifests were generated for GitOps sync.")

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
            raise RuntimeError(f"git clone failed:\n{clone_result.stdout.strip()}")

        repo_dir = temp_dir / "repo"
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

            commit_message = f"gitops({project['name']}/{selected_env}): sync runtime manifests"
            commit_result = run_git_command(["git", "commit", "-m", commit_message], repo_dir, clone_env, log_callback=log_callback)
            if commit_result.returncode != 0:
                raise RuntimeError(f"git commit failed:\n{commit_result.stdout.strip()}")

            push_result = run_git_command(["git", "push", "origin", gitops_repo_branch], repo_dir, clone_env, log_callback=log_callback)
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

        if apply_argocd:
            try:
                app_result = apply_argocd_application_to_platform(state, selected_env)
                integration_logs.extend(app_result["logs"])
            except Exception as exc:
                integration_warnings.append(f"Argo CD application apply did not complete: {exc}")

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
            "warnings": integration_warnings,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
