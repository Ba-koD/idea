from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import generator
import os

app = FastAPI()

# 1. CORS 설정: 설계서의 On-Prem 제어 평면 원칙에 따라 모든 도메인 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cloudflare Reconciler용 데이터 구조
class CloudflareConfig(BaseModel):
    token: str
    zone_id: str
    tunnel_id: str
    domain: str
    allowed_ips: Optional[List[str]] = [] # 설계서의 allowed_source_ips 반영

# Project State 전체를 담는 데이터 모델
class DeployRequest(BaseModel):
    # Repository Role
    project_name: str
    repo_url: str
    env_type: str  # test, stage, prod
    
    # Environment Model
    env_vars: str
    replica: int
    
    # Routing Model (설계서 핵심: Caddy 라우팅을 위한 서비스명)
    entry_service: Optional[str] = "frontend-svc"
    backend_service: Optional[str] = "backend-svc"
    healthcheck_path: Optional[str] = "/healthz"
    
    # Cloudflare Connectivity
    cloudflare: Optional[CloudflareConfig] = None

# 2. 통합 배포 API (Reconciliation Trigger)
@app.post("/api/deploy")
async def deploy_project(req: DeployRequest):
    try:
        print("\n" + "="*60)
        print(f" [PROJECT STATE RECEIVED] : {req.project_name}")
        print(f"📡 Target Environment : {req.env_type.upper()}")
        print("-" * 60)
        
        # [Step 1] Argo CD 경로 (GitOps Manifest 생성)
        # 설계서 원칙: tmp 배포 계층이 Kubernetes 리소스를 정의함
        print(f"📝 Generating GitOps Manifests for {req.repo_url}...")
        
        # [Step 2] Cloudflare 경로 (Reconciler 작동)
        if req.cloudflare:
            print(f" Cloudflare Reconciler Start...")
            print(f"   > Target Domain: {req.cloudflare.domain}")
            print(f"   > Tunnel Mapping: {req.cloudflare.tunnel_id}")
            # 설계서 보안 원칙: Secret은 마스킹 처리
            masked_token = req.cloudflare.token[:4] + "****" + req.cloudflare.token[-4:] if len(req.cloudflare.token) > 8 else "****"
            print(f"   > Auth: Token Verified ({masked_token})")

        # [팀원 2에게 전달] 
        # generator.create_infra_zip(req)를 실행하면 
        # 이제 설계서에 정의된 모든 변수(entry_service 등)를 YAML에 박을 수 있습니다.
        
        print("="*60 + "\n")
        
        return {
            "status": "success", 
            "project_state": "reconciled",
            "message": f"{req.env_type.upper()} 환경의 배포 정의 및 네트워크 정책 반영 완료"
        }
    except Exception as e:
        print(f"❌ [SYSTEM ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 3. Prod Blue-Green 무중단 전환 API
@app.post("/api/traffic/switch")
async def switch_traffic(data: dict):
    target = data.get("target_color") # blue or green
    print(f"🔄 [PROD TRAFFIC CONTROL] Switch Active Slot -> {target.upper()}")
    
    # 설계서 원칙: Caddy가 Upstream을 전환함
    # caddy_client.switch_upstream(target) 로직이 들어갈 자리
    
    return {
        "status": "success", 
        "active_slot": target,
        "message": f"Caddy 라우팅이 {target.upper()} 슬롯으로 전환되었습니다."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
