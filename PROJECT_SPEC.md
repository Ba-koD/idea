# PROJECT_SPEC.md

## 1. Project Definition

`idea`는 On-Prem 환경에 설치되는 컨트롤 플레인이다.  
운영자는 웹 UI에서 실제 서비스 저장소를 등록하고, `test / stage / prod` 환경 배포를 통합 관리한다.  
배포 방식은 **GitOps 기반**이며, 실제 애플리케이션 배포는 **Argo CD가 담당**한다.

---

## 2. Core Architecture Summary

이 프로젝트는 아래 두 단계로 분리된다.

### A. idea 플랫폼 설치 단계
- 대상: On-Prem 인프라에 `idea` 플랫폼 자체를 설치
- 사용 도구: `GitHub Actions + Terraform + Ansible`
- 설치 대상:
  - Docker 또는 Container Runtime
  - kind
  - Argo CD
  - idea Backend / Frontend
  - 내부 DB / Secret Store
  - Monitoring Stack
  - Caddy
  - cloudflared 실행 기반

### B. 서비스 배포 및 운영 단계
- 대상: 운영자가 등록한 실제 서비스(레포 B)를 `test / stage / prod`에 배포
- 사용 도구: `idea UI + tmp 배포 계층 + Argo CD`
- 동작 방식:
  - 운영자가 웹 UI에서 레포 B, 환경별 `.env`, Cloudflare 정보, `test/stage` 허용 IP, 관리자 허용 IP, 배포 대상을 입력
  - 모든 입력값은 export/import 가능한 단일 `Project State`로 저장된다
  - `idea` 내부의 `tmp 배포 계층`이 GitOps 리소스와 Cloudflare desired state를 생성한다
  - Argo CD가 해당 리소스를 Kubernetes에 반영
  - `idea`의 Cloudflare reconciler가 Cloudflare API로 Tunnel, hostname, IP List, WAF rule을 반영한다
  - 외부 진입은 환경별 hostname을 `platform Caddy`에 연결하고, 기본 웹 경로는 앱 entry service로, `/api`는 backend service로 라우팅한다
  - prod는 `Caddy` 기반 blue-green 배포를 사용
  - 외부 공개는 `Cloudflare Tunnel`을 사용하되 `test/stage`는 허용 IP만 접근 가능하다

---

## 3. Fixed Terms

### idea
- On-Prem에 설치되는 컨트롤 플레인
- 웹 UI, API, 설정 저장, 비밀정보 암호화 저장, 배포 제어, 모니터링 기능 제공
- 모든 웹 설정의 export/import 기능을 제공

### 레포 A
- `idea` 플랫폼 자체의 소스코드 저장소
- GitHub Actions는 이 저장소를 기준으로 동작
- 설치/업데이트에 필요한 코드만 포함

### 레포 B
- 실제로 배포할 서비스의 GitHub 저장소
- 운영자가 idea UI에서 등록하는 대상
- 포함 가정:
  - 애플리케이션 코드
  - Dockerfile
  - 필요하면 `docker-compose.yml`
  - `.env.example` 정도의 예시 설정
- 실제 운영 secret은 저장하지 않음

### tmp 배포 계층
- 별도 제품이 아님
- idea 내부의 배포 오케스트레이션 로직
- 역할:
  - 레포 B와 저장된 환경값을 읽음
  - 레포 B에 `docker-compose.yml`이 있더라도 이를 직접 실행하지 않고 배포 입력 원본으로 해석함
  - 레포 B 변경 또는 배포 요청 시 웹 UI의 `Project State`와 repo 구조를 조합함
  - 런타임 웹 UI에서 입력된 build 경로, Argo CD 대상, env, target profile, hostname 라우팅을 canonical source로 사용함
  - GitOps 리소스를 생성함
  - Cloudflare desired state를 생성함
  - Argo CD가 반영할 선언형 산출물을 만듦
  - Cloudflare reconciler가 반영할 edge 산출물을 만듦
- 역할 아님:
  - Terraform 실행기 아님
  - Ansible 실행기 아님
  - `docker-compose up` 실행기 아님

### GitOps Desired State
- Argo CD가 감시하는 Git repository 또는 path
- Kubernetes manifest, Job, Caddy 설정 같은 선언형 산출물을 저장하는 위치
- 레포 B 애플리케이션 소스코드 저장소와는 분리된 배포 산출물 관점의 소스
- 레포 B 코드 변경만으로는 배포되지 않고, build 결과 이미지 정보와 manifest 변경이 이 경로에 기록되어야 Argo CD가 반영을 시작함

### Platform Caddy
- 외부 HTTP 진입점 역할을 담당하는 플랫폼 공용 프록시
- Cloudflare Tunnel의 내부 목적지
- 환경별 hostname을 내부 Kubernetes Service에 라우팅
- 기본 웹 경로는 앱 entry service로 연결하고, backend는 same-origin `/api` 경로로 연결
- prod에서는 blue/green active upstream 전환 지점 역할도 담당

### Runtime
- `test / stage / prod` 환경에서 실제로 실행되는 컨테이너
- prod는 `blue / green` 슬롯을 함께 운용

---

## 4. Non-Negotiable Rules

아래 규칙은 절대 바꾸지 않는다.

### Rule 1. Terraform / Ansible
- **idea 플랫폼 설치에만 사용**
- 실제 서비스의 `test / stage / prod` 앱 배포에는 사용하지 않음

### Rule 2. Argo CD
- **앱 배포를 담당하는 GitOps CD 컴포넌트**
- Git 저장소의 desired state를 Kubernetes에 sync
- 레포 B 소스코드를 직접 빌드하거나 `docker-compose`를 실행하지 않음
- `GitOps Desired State`의 manifest 변경을 감지해 sync함
- 실행 단계가 필요하면 Kubernetes `Job` 또는 Argo CD hook manifest로 선언된 것만 반영 대상이 됨
- Terraform을 대체하지 않음
- Terraform을 직접 실행하는 구조로 설계하지 않음

### Rule 3. tmp 배포 계층
- 레포 B와 저장된 설정을 바탕으로 배포 정의를 생성
- 다음 리소스를 생성 가능:
  - ConfigMap
  - Secret
  - Deployment
  - Service
  - Caddy 관련 설정
- Cloudflare reconciler가 반영할 edge desired state를 생성
- 레포 B의 `docker-compose.yml`은 직접 실행하지 않고 Kubernetes 리소스로 변환 가능한 입력 형식으로만 취급한다
- 레포 B 변경 시 tmp 또는 외부 CI가 생성한 이미지 tag 또는 digest를 GitOps 산출물에 반영할 수 있어야 한다
- build 경로, Argo CD 연결, env, target profile은 repo 내부 선언보다 웹 UI `Project State`가 우선한다
- migration이나 smoke test가 필요하면 선언형 `Job` 또는 hook manifest를 생성할 수 있다

### Rule 4. Cloudflare Edge Reconciliation
- Cloudflare edge 상태는 `idea`가 Cloudflare API로 reconcile한다
- Argo CD는 Kubernetes desired state만 sync한다
- Argo CD가 Cloudflare API를 직접 호출하는 구조로 설계하지 않는다
- `idea`는 배포 흐름에서 Tunnel, hostname, IP List, WAF rule을 자동 생성/수정한다
- 기본 흐름:
  - `test -> cloudflared -> platform Caddy -> test entry service`, 단 `test_allowed_source_ips`만 접근 가능
  - `stage -> cloudflared -> platform Caddy -> stage entry service`, 단 `stage_allowed_source_ips`만 접근 가능
  - `prod -> cloudflared -> platform Caddy -> active blue/green app`, public 공개
- `test/stage` allowlist가 비어 있으면 public 공개하지 않는다

### Rule 5. Prod Zero-Downtime
- prod는 단일 Deployment가 아님
- 기본 구성:
  - `prod-blue`
  - `prod-green`
  - `Caddy`
- 신규 배포는 inactive 슬롯에 먼저 배포
- health check 성공 후 Caddy가 active upstream 전환
- rollback 가능해야 함

### Rule 6. Canonical Project State
- 웹 UI에서 설정하는 모든 값은 versioned `Project State`로 정규화 저장한다
- export는 이 `Project State`를 그대로 직렬화한 결과여야 한다
- import는 동일한 `Project State`를 복원하고 같은 reconciliation 경로를 다시 실행해야 한다
- secret은 export bundle 안에서 암호화된 상태로 포함되며 import 시 대상 플랫폼 키로 재암호화된다
- import 완료 후 동일한 infra 조건이면 같은 GitOps 리소스와 같은 Cloudflare 정책이 재현되어야 한다

### Rule 7. Network and Routing Model
- 외부 공개 경로는 환경별 hostname 하나를 기준으로 한다
- 기본 웹 경로는 frontend 또는 app entry service가 담당한다
- backend는 같은 hostname 아래 `/api` 경로로 연결한다
- backend와 DB 같은 내부 컴포넌트는 `localhost`가 아니라 Kubernetes Service 이름으로 통신한다
- DB는 Cloudflare Tunnel, public hostname, external Caddy의 직접 노출 대상이 아니다
- 내부 프로젝트는 앱 전용 Caddy 없이도 배포 가능해야 하며, 외부 라우팅 책임은 기본적으로 platform Caddy가 가진다

---

## 5. High-Level Flow

### Step 1. idea 플랫폼 프로비저닝
1. 개발자가 레포 A에 push
2. GitHub Actions 실행
3. Terraform으로 On-Prem 호스트/기반 환경 준비
4. Ansible로 idea 플랫폼 구성요소 설치

### Step 2. 운영자 입력
운영자가 idea 웹 UI에서 아래를 입력한다.

- 프로젝트 생성
- 레포 B URL
- branch 또는 tag
- 레포 접근 secret
- build 정보
  - `frontend_build_context`
  - `frontend_dockerfile_path`
  - `backend_build_context`
  - `backend_dockerfile_path`
- Argo CD 연결 정보
  - `argo_project_name`
  - `argo_destination_name`
  - `argo_destination_server`
  - `gitops_repo_url`
  - `gitops_repo_branch`
  - `gitops_repo_path`
  - `gitops_repo_access_secret`
- Cloudflare API / Tunnel 정보
  - `base_domain`
  - `cloudflare_account_id`
  - `cloudflare_api_token`
  - `tunnel_name` 또는 `tunnel_id`
  - `test_hostname`
  - `stage_hostname`
  - `prod_hostname`
- 외부 라우팅 정보
  - `entry_service_name`
  - `backend_service_name`
  - `backend_base_path` 기본값 `/api`
- `test / stage / prod`용 `.env`
- `test_allowed_source_ips`
- `stage_allowed_source_ips`
- `admin_allowed_ips`
- 배포 대상 서버 또는 클러스터 선택
  - 환경별 `dev / stage / prod` target profile
  - 기본 provider `aws`
  - 기본 AWS target `eks`
  - `provider`
  - `cluster_type`
  - `namespace`
  - `service_port`
  - `build_source_strategy`
  - AWS:
    - `aws_region`
    - `aws_account_id`
    - `aws_auth_method`
    - `aws_access_key_id`
    - `aws_secret_access_key`
    - `aws_role_arn`
    - `aws_cluster_name`
    - `aws_cluster_endpoint`
  - On-Prem:
    - `argo_destination_name`
    - `kube_api_server`
    - `cluster_access_secret`
- prod blue-green 옵션
  - `prod_blue_green_enabled`
  - `healthcheck_path`
  - `healthcheck_timeout`
  - `switch_after_healthy`
  - `rollback_on_failure`

### Step 3. 설정 저장
- 프로젝트 메타데이터 저장
- versioned `Project State` 저장
- `.env` 파싱
- 일반값 / 민감값 분리
- 민감값 암호화 저장
- 레포 접근 secret 저장
- Cloudflare 관련 정보 저장
- Cloudflare 접근 정책 저장
- export/import 가능한 canonical schema로 저장

### Step 4. GitOps 리소스 생성
`tmp 배포 계층`이 환경별 선언형 리소스와 Cloudflare edge desired state를 생성한다.

- 레포 B 변경 또는 운영자 배포 요청이 발생하면 CI 또는 tmp가 배포 대상 이미지 tag/digest를 확정한다
- 확정된 이미지 정보와 `Project State`를 기준으로 environment별 manifest를 생성한다
- 생성된 산출물은 `GitOps Desired State` repository 또는 path에 기록된다

- test:
  - frontend 또는 app entry Deployment / Service
  - backend Deployment / Service
  - 내부 DB Deployment 또는 StatefulSet / Service
  - ConfigMap
  - Secret
  - 필요 시 migration / smoke test `Job`
  - `platform Caddy` 라우팅 설정
  - Tunnel hostname route
  - `test_allowed_source_ips` 기반 IP List / WAF rule
- stage:
  - frontend 또는 app entry Deployment / Service
  - backend Deployment / Service
  - 내부 DB Deployment 또는 StatefulSet / Service
  - ConfigMap
  - Secret
  - 필요 시 migration / smoke test `Job`
  - `platform Caddy` 라우팅 설정
  - Tunnel hostname route
  - `stage_allowed_source_ips` 기반 IP List / WAF rule
- prod:
  - `prod-blue`
  - `prod-green`
  - backend Service
  - 내부 DB Deployment 또는 StatefulSet / Service
  - 필요 시 migration / smoke test `Job`
  - `platform Caddy` 설정
  - public Tunnel hostname route
- admin:
  - `idea UI` / `Grafana`용 `admin_allowed_ips` 기반 IP List / WAF rule

### Step 5. Argo CD 반영
- Argo CD가 `GitOps Desired State` 변경을 감지
- 필요한 경우 `PreSync` migration `Job` 또는 hook 실행
- Kubernetes에 manifest 적용
- readiness / health check를 기준으로 배포 상태를 갱신
- 필요한 경우 `PostSync` smoke test `Job` 또는 hook 실행
- test / stage / prod 컨테이너 실행
- prod는 blue/green 슬롯 유지

### Step 6. Cloudflare API 반영 및 접근 제어
- `idea` Cloudflare reconciler가 Cloudflare API / Tunnel 설정 반영
- 외부 도메인 예시:
  - `test.<base_domain>`
  - `stage.<base_domain>`
  - `prod.<base_domain>`
- `test`는 `test_allowed_source_ips`에서만 접근 가능
- `stage`는 `stage_allowed_source_ips`에서만 접근 가능
- prod는 항상 Caddy를 경유
- `idea UI`와 `Grafana`는 `admin_allowed_ips`에서만 접근 가능

### Step 7. 모니터링
idea의 Monitoring 화면에서 아래를 확인한다.

- test 상태
- stage 상태
- prod active color
- 최근 배포 결과
- 로그
- 에러
- health status

---

## 6. Cloudflare Policy

### 6.1 Environment Exposure Model
각 환경은 Cloudflare Tunnel의 published application 방식으로 연결한다.  
하지만 공개 방식은 환경별로 다르게 고정한다.

예시:
- `test.example.com -> platform Caddy -> test entry service`, 단 `test_allowed_source_ips`만 허용
- `stage.example.com -> platform Caddy -> stage entry service`, 단 `stage_allowed_source_ips`만 허용
- `prod.example.com -> platform Caddy -> active prod slot`, public 공개

### 6.2 Automatic Cloudflare Reconciliation
Cloudflare 설정은 수동 콘솔 작업이 아니라 `idea`의 reconciliation 대상이다.

- 입력 원천은 idea 웹 UI다
- 저장 원천은 versioned `Project State`다
- 반영 원천은 `idea`의 Cloudflare reconciler다
- 반영 방식은 Cloudflare API다
- 관리 대상:
  - Tunnel
  - public hostname
  - IP List
  - WAF custom rule

### 6.3 Admin-Only Access Policy
아래 두 대상은 외부 공개가 가능하더라도 **admin IP allowlist만 허용**한다.

- `idea` 웹 UI
- `Grafana`

적용 호스트 예시:
- `idea.example.com`
- `grafana.example.com`

권장 방식:
- Cloudflare IP List 생성
  - 예: `allowed_admin_ips`
- WAF Custom Rule 적용
  - `ip.src not in $allowed_admin_ips` 이면 Block

### 6.4 Test/Stage Restricted Access Policy
`test`와 `stage`는 public-open 환경이 아니다.

- 웹 UI에서 환경별 허용 IP 목록을 받는다
- `test_allowed_source_ips`, `stage_allowed_source_ips`를 별도 저장한다
- Cloudflare API로 환경별 IP List와 WAF rule을 자동 생성한다
- 허용된 IP에서만 접근 가능하다
- allowlist가 비어 있으면 route를 비활성화하거나 deny-all로 유지한다

### 6.5 Separation Principle
- `prod` 앱은 공개 대상
- `test / stage` 앱은 제한 공개 대상
- `idea UI / Grafana`는 운영자 전용
- 따라서 세 정책을 절대 동일하게 취급하지 않음

### 6.6 Request Routing Principle
- 외부 브라우저는 환경별 hostname 하나만 진입점으로 사용한다
- 같은 hostname에서 `/`는 frontend 또는 app entry service로 연결한다
- 같은 hostname에서 `/api`는 backend service로 연결한다
- backend는 DB를 `localhost`가 아니라 내부 Service 이름으로 접근한다
- DB는 외부 hostname이나 Tunnel route 대상이 아니다

---

## 7. .env Storage Policy

### Core Principle
`.env`는 idea 내부에 저장한다.  
하지만 **평문 원문 전체 저장은 금지**하며, 반드시 구조화 저장 + 민감값 암호화를 사용한다.

### Required Processing
1. `.env` 입력
2. key-value 파싱
3. 일반값 / 민감값 분리
4. 일반값 저장
5. 민감값 암호화 저장
6. 배포 시점에만 복호화
7. Kubernetes `ConfigMap / Secret`으로 렌더링

### Forbidden
- `.env` 원문 전체를 레포 B에 저장하지 않음
- 민감값을 Git에 커밋하지 않음
- GitHub Secrets를 런타임 secret store처럼 read-back 하지 않음

---

## 8. Project State Export / Import Policy

### Core Principle
웹 UI에서 설정하는 모든 값은 별도 예외 없이 하나의 versioned `Project State`로 저장한다.  
export와 import는 이 `Project State`를 기준으로 동작한다.

### Included in Project State
- 프로젝트 메타데이터
- 레포 B URL / ref / access secret
- 환경별 `.env` 구조화 값
- 환경별 민감값
- 배포 대상 매핑
- Cloudflare account / tunnel / hostname 설정
- `entry_service_name`
- `backend_service_name`
- `backend_base_path`
- `build_source_strategy`
- `frontend_build_context`
- `frontend_dockerfile_path`
- `backend_build_context`
- `backend_dockerfile_path`
- `argo_project_name`
- `argo_destination_name`
- `argo_destination_server`
- `gitops_repo_url`
- `gitops_repo_branch`
- `gitops_repo_path`
- 환경별 target profile
- `namespace`
- `service_port`
- `test_allowed_source_ips`
- `stage_allowed_source_ips`
- `admin_allowed_ips`
- prod blue-green 정책
  - `prod_blue_green_enabled`
  - `healthcheck_path`
  - `healthcheck_timeout`
  - `switch_after_healthy`
  - `rollback_on_failure`
- 모니터링에 필요한 프로젝트 설정

### Export Behavior
- export 결과물은 versioned bundle이다
- 일반 설정과 민감값을 함께 포함한다
- 민감값은 export bundle 내부에서 암호화된 상태로 포함한다
- Cloudflare 접근 정책과 환경별 allowlist도 함께 포함한다
- import 시 재현에 필요하지 않은 일시적 runtime status는 포함하지 않는다

### Import Behavior
- import는 동일한 schema의 `Project State`를 복원한다
- 복원된 secret은 대상 `idea` 플랫폼 키로 재암호화된다
- 복원된 설정으로 GitOps 산출물을 다시 생성한다
- Cloudflare API reconciliation도 같은 정책으로 다시 수행한다
- 결과적으로 동일한 환경, 동일한 hostname, 동일한 접근 정책, 동일한 배포 동작이 재현되어야 한다

### Structural Requirement
- export/import는 부가 기능이 아니라 기본 저장 모델의 일부여야 한다
- 웹 UI 저장 경로와 import 경로가 다른 내부 스키마를 사용하면 안 된다
- 사용자가 웹에서 설정한 모든 필드는 export 가능해야 하며 import 후 누락 없이 동작해야 한다

---

## 9. Repo B Policy

### Repo B Meaning
- tmp가 배포할 실제 서비스 소스 저장소
- idea UI에서 등록하는 배포 대상
- `docker-compose.yml`이 있더라도 런타임 실행 파일이 아니라 배포 입력 원본으로 취급

### Required Input for Repo B Registration
- repo URL
- branch 또는 tag
- repo access secret
- `.env.example` 또는 필요한 key schema

### Compose Compatibility Policy
- `docker-compose.yml`이 있으면 tmp가 서비스, 포트, 환경변수, 의존관계를 읽을 수 있다
- repo 내부 선언 파일이 있더라도 런타임 웹 UI `Project State`가 우선한다
- `idea.yaml`은 선택적 힌트 또는 import 보조 입력으로만 취급할 수 있다
- compose 정의는 Kubernetes `Deployment / Service / ConfigMap / Secret` 생성의 입력으로만 사용한다
- compose 파일을 대상 서버에서 직접 실행하지 않는다
- 내부 통신 주소는 배포 시 `localhost`가 아니라 환경별 Service 이름으로 치환되어야 한다
- 앱 내부 Caddy가 없어도 배포 가능해야 하며, 외부 라우팅은 platform Caddy가 기본 담당한다

### Secret Handling
- GitHub repo access secret은 idea 내부 저장소에 저장
- 레포 A의 GitHub Secrets에 넣지 않음

### Delivery Trigger Policy
- 레포 B에 push만 했다고 바로 클러스터에 반영되지는 않는다
- 배포 대상 image tag 또는 digest가 `GitOps Desired State`에 기록되어야 Argo CD가 반영을 시작한다
- 따라서 실제 배포 트리거는 `repo B source 변경`이 아니라 `GitOps manifest 변경`이다

---

## 10. Required Features

### 10.1 idea 플랫폼 프로비저닝
- GitHub Actions
- Terraform
- Ansible
- kind / Argo CD / Caddy / Monitoring / idea 설치

### 10.2 통합 입력 UI
- 레포 B URL 등록
- repo access secret 등록
- Cloudflare API / Tunnel 정보 입력
- 환경별 hostname과 entry service 매핑 입력
- backend service 이름과 backend path 입력
- `test / stage / prod` `.env` 입력
- `test / stage` 허용 IP 입력
- `idea UI / Grafana`용 admin 허용 IP 입력
- 배포 대상 선택
- prod blue-green 옵션 설정

### 10.3 설정 저장 및 보안 처리
- 프로젝트 설정 저장
- versioned `Project State` 저장
- `.env` 암호화 저장
- repo access secret 저장
- Cloudflare secret 저장
- 환경별 allowlist 저장

### 10.4 Argo CD 기반 배포
- 환경별 GitOps 리소스 생성
- repo B 이미지 tag / digest를 반영한 GitOps manifest 갱신
- Argo CD 자동 반영
- 필요한 경우 migration / smoke test `Job` 또는 hook manifest 반영
- prod blue/green 리소스 생성
- same-origin `/api` 라우팅을 포함한 platform Caddy 설정 생성

### 10.5 Cloudflare API 기반 접근 제어
- 환경별 Tunnel 연결
- `test / stage` hostname 자동 연결
- `test / stage` IP List / WAF rule 자동 생성
- `idea UI / Grafana`는 admin IP만 허용
- Cloudflare edge 설정은 수동이 아니라 reconciliation으로 유지
- Cloudflare Tunnel의 내부 목적지는 환경별 entry service가 아니라 platform Caddy를 기본값으로 한다

### 10.6 prod blue-green
- inactive 슬롯 배포
- health check
- Caddy active upstream 전환
- rollback 지원

### 10.7 Monitoring
- test / stage / prod 상태 확인
- 현재 active prod color 확인
- 로그 및 health 상태 표시

### 10.8 설정 export / import
- 웹 설정 전체 export 지원
- encrypted secret 포함 export 지원
- import 후 동일 정책 / 동일 배포 구조 재현
- import 경로도 웹 저장과 같은 schema 사용

---

## 11. Explicit Non-Goals

아래는 구현하면 안 된다.

- `test / stage / prod` 앱 배포에 Terraform 사용
- `test / stage / prod` 앱 배포에 Ansible 사용
- Argo CD가 레포 B 소스코드를 직접 빌드
- Argo CD를 임의 shell 실행기처럼 사용
- 레포 B의 `docker-compose.yml`을 서버에서 직접 실행
- 레포 B의 실제 secret을 Git 저장소에 저장
- prod DNS를 blue/green 각각에 직접 붙여서 스위칭
- `idea` 웹뷰를 unrestricted public으로 노출
- `Grafana`를 unrestricted public으로 노출
- `test / stage`를 unrestricted public으로 노출
- DB를 public hostname 또는 Cloudflare Tunnel에 직접 연결
- GitHub Secrets를 런타임 secret store처럼 사용
- export/import 시 일부 웹 설정만 선택적으로 누락하는 구조

---

## 12. AI Guardrails

AI에게 요청할 때는 아래 전제를 항상 유지한다.

1. Terraform / Ansible은 **idea 설치용만 사용**
2. `test / stage / prod` 앱 배포는 **Argo CD가 담당**
3. `tmp`는 **배포 오케스트레이션 계층**
4. 레포 B는 **실제 배포 대상 서비스 저장소**
5. `.env`는 **idea가 암호화 저장**
6. 배포 시 `.env`는 **ConfigMap / Secret으로 변환**
7. prod는 **Caddy 기반 blue-green**
8. `prod`는 **Cloudflare Tunnel을 통해 public 공개**
9. `test / stage`는 **Cloudflare Tunnel + 환경별 IP allowlist로 제한 공개**
10. `idea UI`와 `Grafana`는 **admin IP allowlist만 허용**
11. Cloudflare 정책은 **IP List + WAF Custom Rule** 또는 동등한 allowlist 정책 사용
12. 외부 라우팅은 **platform Caddy**가 기본 담당하고 backend는 **same-origin `/api`**로 연결
13. 내부 서비스 간 통신은 **`localhost`가 아니라 Service 이름**을 사용
14. 레포 B의 `docker-compose.yml`은 **입력 원본이지 실행 대상이 아님**
15. Argo CD는 **레포 B source가 아니라 GitOps desired state**를 본다
16. 실행 단계가 필요하면 **Kubernetes `Job` 또는 hook**으로 선언한다
17. 모든 웹 설정은 **export/import 가능한 단일 Project State**로 저장
18. import 후에는 **동일 정책과 동일 배포 구조가 재현**되어야 함

---

## 13. Standard Prompt Examples

### Example 1
`위 PROJECT_SPEC.md를 기준으로 backend API 명세만 작성해줘. 아키텍처 전제는 바꾸지 마.`

### Example 2
`위 PROJECT_SPEC.md 기준으로 prod blue-green 전환 로직만 구체화해줘. Caddy를 active upstream 전환 지점으로 유지해.`

### Example 3
`위 PROJECT_SPEC.md 기준으로 Argo CD가 반영할 test/stage/prod 리소스 구조를 설명해줘. Terraform/Ansible은 idea 설치용으로만 유지해.`

### Example 4
`위 PROJECT_SPEC.md 기준으로 Cloudflare Tunnel과 admin_ip allowlist 정책까지 포함한 운영 절차를 정리해줘.`

---

## 14. Final Goal

이 프로젝트의 최종 목표는 아래와 같다.

- On-Prem에 설치되는 `idea` 플랫폼
- 웹 UI 기반 통합 입력
- 레포 B 기반 `test / stage / prod` 컨테이너 배포
- `.env` 암호화 저장
- Argo CD 기반 GitOps 반영
- platform Caddy 기반 hostname 및 `/api` 라우팅
- prod의 Cloudflare Tunnel 기반 public 공개
- test / stage의 Cloudflare IP allowlist 기반 제한 공개
- `idea UI / Grafana`는 admin IP만 허용
- 웹 설정 전체 export / import 지원
- prod의 Caddy 기반 blue-green 무중단 배포
- Monitoring 기반 상태 확인

---

## 15. One-Sentence Summary for AI

`idea`는 On-Prem에 설치되는 GitOps 기반 애플리케이션 배포 컨트롤 플레인이고, 플랫폼 설치는 `GitHub Actions + Terraform + Ansible`, 실제 서비스 배포는 `tmp 배포 계층 + Argo CD`, 레포 B의 compose 정의는 입력 원본으로만 사용되며 외부 라우팅은 `platform Caddy`가 hostname과 same-origin `/api`를 담당하고, Cloudflare edge 설정은 `idea`가 API로 reconcile하며, `prod`는 public 공개, `test/stage`는 환경별 IP allowlist 제한 공개, 관리자 화면은 `admin IP allowlist`, 모든 웹 설정은 export/import 가능한 단일 `Project State`로 관리한다.
