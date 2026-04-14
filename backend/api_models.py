from pydantic import BaseModel
from typing import Optional

# 1. Cloudflare 설정을 담기 위한 하위 모델
class CloudflareConfig(BaseModel):
    token: str
    zone_id: str
    tunnel_id: str
    domain: str

# 2. 프론트엔드 App.js의 payload와 일치하는 메인 요청 모델
class InfraRequest(BaseModel):
    # 기본 프로젝트 정보
    project_name: str
    repo_url: str
    env_type: str  # dev, stage, prod
    
    # 인프라 설정 정보
    env_vars: str
    replica: int
    
    # Cloudflare 설정 (선택 사항으로 두어 유연성 확보)
    cloudflare: Optional[CloudflareConfig] = None
    
    # 필요 시 확장할 필드들 (기본값 설정)
    region: Optional[str] = "ap-northeast-2"

# 3. (선택) 트래픽 스위치용 모델도 미리 정의해두면 깔끔합니다
class TrafficSwitchRequest(BaseModel):
    target_color: str  # blue or green
