import json
import os
import socket
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import generator
from api_models import DeployRequest, EnvExchangeRequest, ProjectState, ProvisionRequest, normalize_project_state
from env_import import apply_env_import, export_env_text, write_export_env_file
from provisioning import ProvisioningPartialFailure, provision_ncloud_target
from state_store import load_or_initialize_state, save_state as save_encrypted_state

app = FastAPI(title="idea Control Plane API")
OUTPUT_ROOT = Path("outputs")
LEGACY_PROJECT_STATE_PATH = OUTPUT_ROOT / "project-state.json"
PROVISION_TASKS: dict[str, dict] = {}
PROVISION_TASKS_LOCK = threading.Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def runtime_payload(status: str = "ok"):
    return {
        "status": status,
        "service": "idea-control-plane",
        "environment": os.getenv("APP_ENV", "platform"),
        "serverTime": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
    }


def ensure_project_state_file() -> dict:
    return load_or_initialize_state(
        OUTPUT_ROOT,
        LEGACY_PROJECT_STATE_PATH,
        normalize_project_state,
    )


def load_project_state() -> dict:
    return ensure_project_state_file()


def save_project_state(payload: ProjectState | dict) -> dict:
    return save_encrypted_state(OUTPUT_ROOT, payload, normalize_project_state)


def create_provision_task(selected_env: str) -> dict:
    task = {
        "task_id": uuid4().hex,
        "selected_env": selected_env,
        "status": "queued",
        "logs": [f"Queued {selected_env.upper()} provisioning task."],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
        "error": "",
    }
    with PROVISION_TASKS_LOCK:
        PROVISION_TASKS[task["task_id"]] = task
    return task


def append_provision_log(task_id: str, message: str) -> None:
    with PROVISION_TASKS_LOCK:
        task = PROVISION_TASKS.get(task_id)
        if not task:
            return
        task["logs"].append(message)
        task["updated_at"] = datetime.now(timezone.utc).isoformat()


def update_provision_task(task_id: str, **updates: object) -> None:
    with PROVISION_TASKS_LOCK:
        task = PROVISION_TASKS.get(task_id)
        if not task:
            return
        task.update(updates)
        task["updated_at"] = datetime.now(timezone.utc).isoformat()


def get_provision_task(task_id: str) -> dict | None:
    with PROVISION_TASKS_LOCK:
        task = PROVISION_TASKS.get(task_id)
        return json.loads(json.dumps(task)) if task else None


def build_gitops_bundle(state: dict, selected_env: str) -> dict:
    project = state["project"]
    target = state["targets"][selected_env]
    runtime_env = state["env"][selected_env]
    cloudflare_env = state["cloudflare"]["environments"][selected_env]
    hostname = state["routing"][f"{selected_env}_hostname"]

    execution_logs = [
        f"Loaded project state for {project['name']}.",
        f"Selected environment: {selected_env.upper()}.",
        f"App repository: {project['app_repo_url']} @ {project['git_ref']}.",
        f"NKS target: {target['ncloud']['cluster_name']} / namespace {target['namespace']}.",
        f"Cloudflare route: {hostname or '(base domain missing)'} via tunnel {state['cloudflare']['tunnel_name']}.",
        "Argo CD will watch "
        f"{state['argo']['gitops_repo_url']}#{state['argo']['gitops_repo_branch']} "
        f"at {state['argo']['gitops_repo_path']}/{selected_env}.",
        f"Runtime APP_ENV={runtime_env.get('APP_ENV', selected_env)} "
        f"PUBLIC_API_BASE_URL={runtime_env.get('PUBLIC_API_BASE_URL', '/api')}.",
    ]

    output_path = generator.generate_all(state, selected_env)
    zip_filename = f"{project['name']}_{selected_env}_manifests.zip"
    zip_path = output_path / zip_filename

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w") as zipf:
        for root, _, files in os.walk(output_path):
            for file in files:
                if file == zip_filename or not file.endswith((".yaml", ".yml", ".json", ".txt")):
                    continue
                zipf.write(os.path.join(root, file), arcname=file)

    execution_logs.append(
        "Bundle generated with namespace, Argo CD application, runtime ConfigMap, and redacted project-state payload."
    )
    if any(not str(value).startswith("secret://") for value in state["secrets"][selected_env].values()):
        execution_logs.append("Inline runtime secrets were materialized into a Kubernetes Secret manifest for Argo CD.")
    elif state["secrets"][selected_env]:
        execution_logs.append("Runtime secret refs were kept as refs only. No inline Kubernetes Secret manifest was generated.")
    execution_logs.append(f"Argo CD access hint: {state['argo']['access_hint']}")

    return {
        "logs": execution_logs,
        "download_url": f"/api/download/{project['name']}/{selected_env}",
        "hostname": hostname,
        "cloudflare": {
            "subdomain": cloudflare_env.get("subdomain", ""),
            "base_domain": cloudflare_env.get("base_domain", ""),
        },
    }


@app.on_event("startup")
async def startup_event():
    ensure_project_state_file()


@app.get("/api/project-state")
async def get_project_state():
    return load_project_state()


@app.put("/api/project-state")
async def put_project_state(project_state: ProjectState):
    return save_project_state(project_state)


@app.post("/api/project-state/import-env")
async def import_project_env(
    selected_env: str = Form(...),
    env_file: UploadFile | None = File(None),
    env_text: str = Form(""),
    project_state: str = Form(""),
):
    if selected_env not in {"dev", "stage", "prod"}:
        raise HTTPException(status_code=400, detail="selected_env must be one of dev, stage, prod.")

    try:
        payload = normalize_project_state(json.loads(project_state)) if project_state else load_project_state()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid project_state payload: {exc}") from exc

    if env_file is None and not env_text.strip():
        raise HTTPException(status_code=400, detail="either env_file or env_text must be provided.")

    if env_file is not None:
        try:
            env_payload_text = (await env_file.read()).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="env file must be UTF-8 encoded text.") from exc
        file_name = env_file.filename or ".env"
    else:
        env_payload_text = env_text
        file_name = "pasted.env"

    next_state, summary = apply_env_import(payload, selected_env, env_payload_text)
    saved_state = save_project_state(next_state)

    return {
        "status": "success",
        "message": f"{summary['selected_env'].upper()} .env imported into Project State",
        "project_state": saved_state,
        "summary": {
            **summary,
            "file_name": file_name,
        },
    }


@app.post("/api/project-state/export-env")
async def export_project_env(req: EnvExchangeRequest):
    try:
        selected_env = req.selected_env
        state = save_project_state(req.project_state) if req.project_state else load_project_state()
        env_text = export_env_text(state, selected_env)
        env_path = write_export_env_file(OUTPUT_ROOT, state["project"]["name"], selected_env, env_text)

        return {
            "status": "success",
            "message": f"{selected_env.upper()} .env export generated",
            "selected_env": selected_env,
            "file_name": env_path.name,
            "env_text": env_text,
            "download_url": f"/api/download-env/{state['project']['name']}/{selected_env}",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/deploy")
async def deploy_project(req: DeployRequest):
    try:
        selected_env = req.selected_env
        state = save_project_state(req.project_state)
        bundle = build_gitops_bundle(state, selected_env)

        return {
            "status": "success",
            "project_state": "reconciled",
            "message": f"{selected_env.upper()} 환경 GitOps 입력값 정리 완료",
            "logs": bundle["logs"],
            "download_url": bundle["download_url"],
            "hostname": bundle["hostname"],
            "cloudflare": bundle["cloudflare"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/provision-target")
async def provision_target(req: ProvisionRequest):
    try:
        selected_env = req.selected_env
        state = save_project_state(req.project_state)
        next_state, result = provision_ncloud_target(state, selected_env, OUTPUT_ROOT, apply=req.apply)
        saved_state = save_project_state(next_state)

        payload = {
            "status": "success",
            "selected_env": selected_env,
            "message": (
                f"{selected_env.upper()} Ncloud target provisioned."
                if result["applied"]
                else f"{selected_env.upper()} Ncloud provisioning dry-run generated."
            ),
            "project_state": saved_state,
            "logs": result["logs"],
            "runtime_dir": result["runtime_dir"],
            "applied": result["applied"],
        }

        if result["applied"]:
            bundle = build_gitops_bundle(saved_state, selected_env)
            result["logs"].extend(bundle["logs"])
            payload.update(
                {
                    "cluster_uuid": result["outputs"]["cluster_uuid"],
                    "cluster_endpoint": result["outputs"]["cluster_endpoint"],
                    "kubeconfig_download_url": f"/api/download-provision/{saved_state['project']['name']}/{selected_env}/kubeconfig",
                    "argocd_cluster_secret_download_url": (
                        f"/api/download-provision/{saved_state['project']['name']}/{selected_env}/argocd-cluster-secret"
                    ),
                    "logs": result["logs"],
                    "message": f"{selected_env.upper()} Ncloud target provisioned and GitOps artifacts refreshed.",
                }
            )
        if result.get("warnings"):
            payload["warnings"] = result["warnings"]

        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProvisioningPartialFailure as exc:
        save_project_state(exc.next_state)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/provision-target/start")
async def start_provision_target(req: ProvisionRequest):
    task = create_provision_task(req.selected_env)
    payload = req.model_dump()

    def run_task() -> None:
        try:
            update_provision_task(task["task_id"], status="running")
            append_provision_log(task["task_id"], "Saving project state to backend.")
            state = save_project_state(payload["project_state"])
            append_provision_log(task["task_id"], "Project state saved. Starting provisioning pipeline.")
            next_state, result = provision_ncloud_target(
                state,
                payload["selected_env"],
                OUTPUT_ROOT,
                apply=payload["apply"],
                log_callback=lambda message: append_provision_log(task["task_id"], message),
            )
            saved_state = save_project_state(next_state)

            result_payload = {
                "status": "success",
                "selected_env": payload["selected_env"],
                "message": (
                    f"{payload['selected_env'].upper()} Ncloud target provisioned."
                    if result["applied"]
                    else f"{payload['selected_env'].upper()} Ncloud provisioning dry-run generated."
                ),
                "project_state": saved_state,
                "logs": result["logs"],
                "runtime_dir": result["runtime_dir"],
                "applied": result["applied"],
            }

            if result["applied"]:
                bundle = build_gitops_bundle(saved_state, payload["selected_env"])
                result["logs"].extend(bundle["logs"])
                result_payload.update(
                    {
                        "cluster_uuid": result["outputs"]["cluster_uuid"],
                        "cluster_endpoint": result["outputs"]["cluster_endpoint"],
                        "kubeconfig_download_url": f"/api/download-provision/{saved_state['project']['name']}/{payload['selected_env']}/kubeconfig",
                        "argocd_cluster_secret_download_url": (
                            f"/api/download-provision/{saved_state['project']['name']}/{payload['selected_env']}/argocd-cluster-secret"
                        ),
                        "logs": result["logs"],
                        "message": f"{payload['selected_env'].upper()} Ncloud target provisioned and GitOps artifacts refreshed.",
                    }
                )
            if result.get("warnings"):
                result_payload["warnings"] = result["warnings"]

            update_provision_task(
                task["task_id"],
                status="completed",
                result=result_payload,
            )
        except ProvisioningPartialFailure as exc:
            saved_state = save_project_state(exc.next_state)
            append_provision_log(task["task_id"], str(exc))
            update_provision_task(
                task["task_id"],
                status="failed",
                error=str(exc),
                result={
                    "project_state": saved_state,
                    "runtime_dir": exc.runtime_dir,
                    "logs": exc.logs,
                    "warnings": exc.warnings,
                    "partial_outputs": exc.partial_outputs,
                },
            )
        except Exception as exc:
            append_provision_log(task["task_id"], f"Provisioning failed: {exc}")
            update_provision_task(
                task["task_id"],
                status="failed",
                error=str(exc),
            )

    threading.Thread(target=run_task, daemon=True).start()

    return {
        "status": "accepted",
        "task_id": task["task_id"],
        "selected_env": req.selected_env,
        "message": f"{req.selected_env.upper()} provisioning started.",
        "logs": task["logs"],
    }


@app.get("/api/provision-target/status/{task_id}")
async def get_provision_target_status(task_id: str):
    task = get_provision_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="provision task not found")
    return task


@app.get("/api/healthz")
async def healthz():
    return runtime_payload()


@app.get("/api/readyz")
async def readyz():
    return runtime_payload("ready")


@app.get("/api/time")
async def time():
    return runtime_payload()


@app.get("/api/download/{project}/{env}")
async def download_iac_bundle(project: str, env: str):
    zip_path = OUTPUT_ROOT / project / env / f"{project}_{env}_manifests.zip"
    if zip_path.exists():
        return FileResponse(
            path=zip_path,
            media_type="application/octet-stream",
            filename=f"{project}_{env}_gitops_bundle.zip",
        )
    raise HTTPException(status_code=404, detail="배포 파일을 찾을 수 없습니다.")


@app.get("/api/download-env/{project}/{env}")
async def download_runtime_env(project: str, env: str):
    env_path = OUTPUT_ROOT / project / env / f"{project}_{env}.runtime.env"
    if env_path.exists():
        return FileResponse(
            path=env_path,
            media_type="text/plain; charset=utf-8",
            filename=f"{project}_{env}.runtime.env",
        )
    raise HTTPException(status_code=404, detail="env export file not found.")


@app.get("/api/download-provision/{project}/{env}/{artifact}")
async def download_provision_artifact(project: str, env: str, artifact: str):
    runtime_dir = OUTPUT_ROOT / project / env / "ncloud-runtime"
    artifact_map = {
        "kubeconfig": runtime_dir / "kubeconfig.yaml",
        "argocd-cluster-secret": runtime_dir / "argocd-cluster-secret.yaml",
    }
    target = artifact_map.get(artifact)
    if target and target.exists():
        return FileResponse(
            path=target,
            media_type="text/plain; charset=utf-8",
            filename=target.name,
        )
    raise HTTPException(status_code=404, detail="provisioning artifact not found.")


@app.post("/api/traffic/switch")
async def switch_traffic(data: dict):
    target = data.get("target_color", "blue")
    return {
        "status": "success",
        "active_slot": target,
        "message": f"Caddy 라우팅이 {target.upper()} 슬롯으로 전환되었습니다.",
    }


@app.get("/")
async def root():
    return {
        **runtime_payload(),
        "message": "Use /api/project-state, /api/project-state/import-env, /api/project-state/export-env, /api/provision-target/start, or /api/healthz.",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
