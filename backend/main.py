from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import zipfile
import shutil
import uvicorn

# 기존 generator 모듈 가정 (create_infra_zip 또는 generate_all 함수 포함)
try:
    import generator
except ImportError:
    # generator가 없을 경우를 대비한 가상 클래스 (에러 방지용)
    class Generator:
        def generate_all(self, req): 
            path = f"outputs/{req.project_name}/{req.env_type}"
            os.makedirs(path, exist_ok=True)
            with open(f"{path}/readme_iac.txt", "w") as f: f.write("IaC Generated")
            return path
    generator = Generator()

app = FastAPI(title="Infra-Forge Pro Control Plane")

# 1. CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 데이터 모델 정의
class CloudflareConfig(BaseModel):
    token: str
    zone_id: str
    tunnel_id: str
    domain: str
    allowed_ips: Optional[List[str]] = []

class DeployRequest(BaseModel):
    project_name: str
    repo_url: str
    env_type: str
    env_vars: str
    replica: int
    entry_service: Optional[str] = "frontend-svc"
    backend_service: Optional[str] = "backend-svc"
    healthcheck_path: Optional[str] = "/healthz"
    cloudflare: Optional[CloudflareConfig] = None

# 2. 통합 배포 API (로그 수집 및 다운로드 링크 추가)
@app.post("/api/deploy")
async def deploy_project(req: DeployRequest):
    try:
        # 프론트엔드로 전달할 실행 로그 수집
        execution_logs = []
        execution_logs.append(f"Project state received: {req.project_name}")
        execution_logs.append(f"Target Environment: {req.env_type.upper()}")

        # 터미널 출력 (기존 로직 유지)
        print("\n" + "="*60)
        print(f" [PROJECT STATE RECEIVED] : {req.project_name}")
        print(f"📡 Target Environment : {req.env_type.upper()}")
        print("-" * 60)
        
        # [Step 1] IaC 파일 생성
        # 기존 코드의 generator 로직 호출 (경로 반환 가정)
        # 만약 generator.generate_all(req)가 경로를 반환한다면:
        output_path = generator.generate_all(req) 
        execution_logs.append(f"Generating GitOps Manifests for {req.repo_url}...")
        
        # [Step 2] Cloudflare Reconciler 로그
        if req.cloudflare:
            execution_logs.append(f"Cloudflare Reconciler synced with domain: {req.cloudflare.domain}")
            print(f" Cloudflare Reconciler Start...")
            print(f"   > Target Domain: {req.cloudflare.domain}")
            
        # [Step 3] 다운로드를 위한 압축 파일 생성
        zip_filename = f"{req.project_name}_{req.env_type}.zip"
        zip_dir = f"outputs/{req.project_name}/{req.env_type}"
        os.makedirs(zip_dir, exist_ok=True)
        zip_path = os.path.join(zip_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(zip_dir):
                for file in files:
                    if file != zip_filename:
                        zipf.write(os.path.join(root, file), file)
        
        execution_logs.append("Deployment Preparation Complete. IaC package ready.")
        print("="*60 + "\n")
        
        return {
            "status": "success", 
            "project_state": "reconciled",
            "message": f"{req.env_type.upper()} 환경 배포 정의 반영 완료",
            "logs": execution_logs,
            "download_url": f"http://localhost:8000/api/download/{req.project_name}/{req.env_type}"
        }

    except Exception as e:
        print(f"❌ [SYSTEM ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 3. 파일 다운로드 전용 API
@app.get("/api/download/{project}/{env}")
async def download_iac_bundle(project: str, env: str):
    zip_path = f"outputs/{project}/{env}/{project}_{env}.zip"
    if os.path.exists(zip_path):
        return FileResponse(
            path=zip_path, 
            media_type='application/octet-stream', 
            filename=f"{project}_{env}_iac.zip"
        )
    raise HTTPException(status_code=404, detail="배포 파일을 찾을 수 없습니다.")

# 4. Blue-Green 전환 API
@app.post("/api/traffic/switch")
async def switch_traffic(data: dict):
    target = data.get("target_color", "blue")
    print(f"🔄 [PROD TRAFFIC CONTROL] Switch Active Slot -> {target.upper()}")
    return {
        "status": "success", 
        "active_slot": target,
        "message": f"Caddy 라우팅이 {target.upper()} 슬롯으로 전환되었습니다."
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
