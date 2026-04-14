# 🏗️ Infra-Forge Pro

> **GitOps 기반의 온프레미스 배포 및 인프라 관리 플랫폼** > Infra-Forge Pro는 운영자의 선언적 설정(Declarative Configuration)을 통해 인프라 프로비저닝부터 Kubernetes 리소스 생성, Cloudflare 네트워크 자동화까지 일관되게 실행하는 통합 제어 플랫폼입니다.

---

## ✨ 주요 기능 (Key Features)

* **통합 컨트롤 플레인 (Integrated Control Plane)**: React 기반 웹 UI를 통해 서비스 저장소, 환경 변수(.env), 복제본 수(Replicas) 등을 한곳에서 관리합니다.
* **IaC 자동화 엔진 (IaC Automation Engine)**: Jinja2 템플릿 엔진을 활용하여 프로젝트 설정에 맞는 Kubernetes Manifest(Deployment, Service) 및 인프라 코드를 동적으로 생성합니다.
* **Cloudflare Reconciler**: Cloudflare API와 연동하여 Tunnel 생성 및 DNS 레코드를 자동으로 동기화하고 보안 정책(IP Allowlist)을 적용합니다.
* **실시간 인프라 가시화**: Mermaid.js를 사용하여 현재 설정된 인프라 토폴로지를 실시간 다이어그램으로 시각화합니다.
* **무중단 배포 (Blue-Green Deployment)**: 운영(Prod) 환경에서 트래픽을 Blue/Green 슬롯으로 즉시 전환할 수 있는 런타임 라우팅 제어 기능을 제공합니다.

---

## 🏗️ 시스템 아키텍처 (System Architecture)

1.  **사용자 선언 (User Declaration)**: 운영자가 UI에서 환경별(Dev, Stage, Prod) 인프라 상태를 정의합니다.
2.  **상태 모델링 (State Modeling)**: FastAPI 백엔드가 요청을 수신하여 Pydantic 모델을 통해 데이터를 검증하고 정규화합니다.
3.  **템플릿 렌더링 (Template Rendering)**: `generator.py`가 Jinja2를 사용하여 사전 정의된 설계도를 바탕으로 K8s YAML 파일을 생성합니다.
4.  **리소스 배포 및 동기화**: 생성된 GitOps 번들을 통해 Kubernetes 클러스터(kind)에 반영하며, Cloudflare 설정을 동기화합니다.

---

## 🛠️ 기술 스택 (Tech Stack)

### **Frontend**
* **React.js**: 상태 중심의 인프라 관리 인터페이스
* **Mermaid.js**: 동적 인프라 토폴로지 시각화
* **Axios**: 백엔드 API 통신 및 번들 다운로드

### **Backend**
* **FastAPI (Python)**: 고성능 비동기 API 서버
* **Jinja2**: 동적 IaC/K8s 매니페스트 템플릿 엔진
* **Pydantic**: 데이터 검증 및 API 스키마 관리

### **Infrastructure Layer**
* **Kubernetes**: 컨테이너 오케스트레이션 (Deployment/Service 관리)
* **Cloudflare**: Zero Trust 보안 터널 및 도메인 관리
* **Argo CD / GitOps**: 선언적 배포 상태 유지

---

## 📂 프로젝트 구조 (Project Structure)

```text
.
├── backend/
│   ├── templates/          # K8s Jinja2 템플릿 (deployment, service)
│   ├── outputs/            # 생성된 프로젝트별 GitOps 번들 저장소
│   ├── api_models.py       # Pydantic 기반 인프라 데이터 모델
│   ├── generator.py        # 리소스 생성 엔진 (Jinja2 기반)
│   └── main.py             # FastAPI 엔드포인트 및 비즈니스 로직
└── frontend/
    ├── src/
    │   ├── components/     # Mermaid 뷰어 등 UI 컴포넌트
    │   ├── App.js          # 통합 제어 인터페이스 메인 로직
    │   └── api.js          # API 호출 유틸리티
    └── package.json        # 프론트엔드 의존성 관리
🚀 시작하기 (Getting Started)
Backend 설정
Bash
cd backend
python -m venv venv
# Linux/macOS
source venv/bin/activate  
# Windows
venv\Scripts\activate

pip install -r requirements.txt
python main.py
Frontend 설정
Bash
cd frontend
npm install
npm start