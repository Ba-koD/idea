import json
import os
import socket
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import generator
from api_models import DeployRequest, ProjectState, normalize_project_state

app = FastAPI(title="idea Control Plane API")
OUTPUT_ROOT = Path("outputs")
PROJECT_STATE_PATH = OUTPUT_ROOT / "project-state.json"

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


def load_project_state() -> dict:
    if not PROJECT_STATE_PATH.exists():
        return normalize_project_state({})

    try:
        payload = json.loads(PROJECT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return normalize_project_state({})

    return normalize_project_state(payload)


def save_project_state(payload: ProjectState | dict) -> dict:
    normalized = normalize_project_state(payload)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECT_STATE_PATH.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return normalized


@app.get("/api/project-state")
async def get_project_state():
    return load_project_state()


@app.put("/api/project-state")
async def put_project_state(project_state: ProjectState):
    return save_project_state(project_state)


@app.post("/api/deploy")
async def deploy_project(req: DeployRequest):
    try:
        selected_env = req.selected_env
        state = save_project_state(req.project_state)
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
            "Bundle generated with namespace, Argo CD application, runtime ConfigMap, and project-state JSON."
        )
        execution_logs.append(f"Argo CD access hint: {state['argo']['access_hint']}")

        return {
            "status": "success",
            "project_state": "reconciled",
            "message": f"{selected_env.upper()} 환경 GitOps 입력값 정리 완료",
            "logs": execution_logs,
            "download_url": f"/api/download/{project['name']}/{selected_env}",
            "hostname": hostname,
            "cloudflare": {
                "subdomain": cloudflare_env.get("subdomain", ""),
                "base_domain": cloudflare_env.get("base_domain", ""),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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
        "message": "Use /api/project-state, /api/deploy, /api/download, or /api/healthz.",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
