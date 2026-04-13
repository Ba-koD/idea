# idea

`idea`는 On-Prem 환경에 설치되는 GitOps 기반 애플리케이션 배포 컨트롤 플레인입니다.  
운영자는 웹 UI에서 실제 서비스 저장소를 등록하고, `test / stage / prod` 환경 배포와 접근 정책을 통합 관리합니다.

상세 설계와 고정 아키텍처 원칙은 [PROJECT_SPEC.md](/mnt/c/Users/rudgh/idea/PROJECT_SPEC.md)를 기준으로 합니다.

## Overview

`idea`는 애플리케이션 자체가 아니라, 애플리케이션을 배포하고 운영하기 위한 플랫폼입니다.

이 프로젝트가 해결하려는 문제는 단순합니다.

- On-Prem 환경에 배포 기반을 일관되게 설치하고
- 서비스별 설정과 secret을 웹에서 안전하게 관리하고
- GitOps 방식으로 `test / stage / prod` 배포를 자동화하고
- prod는 blue-green으로 무중단 전환하고
- Cloudflare 기반 접근 정책까지 한 곳에서 관리하는 것

## What idea Does

`idea`는 다음 역할을 담당합니다.

- On-Prem 환경에 `idea`, `kind`, `Argo CD`, `Caddy`, `Monitoring`, `cloudflared` 실행 기반을 설치합니다.
- 운영자가 웹 UI에서 서비스 저장소, 환경별 `.env`, 배포 대상, Cloudflare 설정을 입력할 수 있게 합니다.
- 입력된 설정과 secret을 구조화 저장하고 민감값은 암호화합니다.
- 내부 `tmp 배포 계층`이 GitOps 리소스와 Cloudflare desired state를 생성합니다.
- Argo CD가 Kubernetes 리소스를 반영합니다.
- `idea`의 Cloudflare reconciler가 Cloudflare API를 통해 Tunnel, hostname, IP allowlist, WAF rule을 반영합니다.
- 플랫폼 `Caddy`가 환경별 hostname과 same-origin `/api` 라우팅을 담당합니다.
- Monitoring 화면에서 배포 상태, active color, 로그, health 상태를 보여줍니다.

## How It Works

전체 흐름은 아래처럼 나뉩니다.

### 1. Platform Install

레포 A 기준으로 `GitHub Actions + Terraform + Ansible`을 사용해 `idea` 플랫폼 자체를 설치합니다.

이 단계에서 설치되는 대상:

- Docker 또는 Container Runtime
- kind
- Argo CD
- idea Backend / Frontend
- 내부 DB / Secret Store
- Monitoring Stack
- Caddy
- cloudflared 실행 기반

### 2. Service Registration

운영자는 웹 UI에서 배포할 실제 서비스(레포 B)를 등록합니다.

입력하는 주요 값:

- 저장소 URL
- branch 또는 tag
- 저장소 접근 secret
- 환경별 hostname
- entry service와 backend service 연결 정보
- `test / stage / prod`용 `.env`
- Cloudflare 계정 및 Tunnel 정보
- `test`, `stage`, `admin` 접근 허용 IP
- 배포 대상 클러스터 또는 서버
- prod blue-green 설정

### 3. Reconciliation

설정이 저장되면 `idea`는 이를 단일 `Project State`로 관리합니다.

그 다음 내부적으로 두 경로가 함께 움직입니다.

- Argo CD 경로:
  GitOps repo/path에 기록된 Kubernetes 리소스를 반영합니다.
- Cloudflare 경로:
  Cloudflare API로 hostname, IP List, WAF rule을 반영합니다.

중요한 점:
Argo CD는 Kubernetes 리소스만 sync합니다.  
Cloudflare API 호출은 `idea`의 reconciler가 담당합니다.

## GitOps Delivery Flow

실제 배포는 보통 아래 순서로 진행됩니다.

1. `repo B`에 코드 변경이 push되거나, 운영자가 웹 UI에서 배포를 요청합니다.
2. 운영자가 웹 UI에서 저장한 `Project State`에는 repo URL, build 경로, Argo CD 대상, 배포 환경별 값, routing 규칙이 포함됩니다.
3. `tmp 배포 계층`이 `Project State + repo B 구조`를 읽고, 필요한 경우 이미지를 build/push한 뒤 GitOps manifest를 생성하거나 갱신합니다.
4. 이 변경이 Argo CD가 감시하는 GitOps repo/path에 기록됩니다.
5. Argo CD가 diff를 감지하고 Kubernetes에 sync합니다.
6. 필요한 경우 migration이나 smoke test는 `Job` 또는 hook manifest로 실행됩니다.
7. Cloudflare 관련 변경은 별도 reconciler가 API로 반영합니다.

중요한 점:

- `repo B` 코드가 바뀌는 것만으로는 바로 배포되지 않습니다.
- 실제 배포 트리거는 GitOps manifest 변경입니다.
- Argo CD는 `docker-compose`나 임의 host shell을 실행하지 않습니다.
- app repo 등록, build 입력, Argo CD 연결, target 서버/클러스터 정보는 런타임 웹 UI 입력이 canonical source입니다.

## Runtime Routing Model

기본 외부 진입 구조는 아래와 같습니다.

- `test.example.com -> cloudflared -> platform Caddy -> test entry service`
- `stage.example.com -> cloudflared -> platform Caddy -> stage entry service`
- `prod.example.com -> cloudflared -> platform Caddy -> active prod slot`

같은 hostname 내부에서는 경로를 고정합니다.

- `/`는 frontend 또는 app entry service
- `/api`는 backend service

중요한 점:

- backend와 DB는 `localhost`로 통신하지 않습니다.
- backend는 `db`, `redis` 같은 Kubernetes Service 이름으로 내부 의존성에 붙습니다.
- DB는 Cloudflare Tunnel이나 public hostname에 직접 연결하지 않습니다.
- 내부 프로젝트는 앱 전용 `Caddy` 없이도 배포 가능해야 하며, 외부 라우팅은 플랫폼 `Caddy`가 맡는 것을 기본값으로 합니다.

## Environment Model

환경별 공개 정책은 처음부터 다르게 설계됩니다.

| 환경 | 공개 방식 |
| --- | --- |
| `prod` | public 공개 |
| `stage` | `stage_allowed_source_ips`에서만 접근 가능 |
| `test` | `test_allowed_source_ips`에서만 접근 가능 |
| `idea UI` | `admin_allowed_ips`에서만 접근 가능 |
| `Grafana` | `admin_allowed_ips`에서만 접근 가능 |

즉, `test`와 `stage`는 Tunnel에 연결되더라도 기본적으로 public-open 환경이 아닙니다.

## Prod Deployment

prod는 단일 배포가 아니라 `blue / green + Caddy` 구조로 운영합니다.

기본 방식:

- 신규 버전은 inactive 슬롯에 먼저 배포
- health check 성공 후 Caddy가 active upstream 전환
- 전환 실패 시 rollback 가능

이 구조 때문에 prod DNS를 blue/green에 직접 붙여서 전환하지 않습니다.

## Repo B Compatibility

레포 B는 일반 애플리케이션 저장소를 의미합니다.

포함 가능 예시:

- 애플리케이션 코드
- Dockerfile
- 필요하면 `docker-compose.yml`
- `.env.example`

중요한 점:

- `docker-compose.yml`이 있어도 이를 서버에서 직접 실행하지 않습니다.
- compose는 서비스, 포트, 환경변수, 의존관계를 읽기 위한 입력 원본으로만 사용합니다.
- 최종 배포 산출물은 Kubernetes `Deployment / Service / ConfigMap / Secret`입니다.
- build 경로, routing, target cluster/server, hostname 연결 같은 배포 입력은 repo에 박아두지 않고 웹 UI `Project State`로 관리하는 것이 기본입니다.

## What Users Configure in the UI

운영자가 웹 UI에서 관리하는 값은 크게 아래 범주로 나뉩니다.

### Repository

- `project_name`
- `repo_url`
- `git_ref`
- `repo_access_secret`
- `frontend_build_context`
- `frontend_dockerfile_path`
- `backend_build_context`
- `backend_dockerfile_path`
- `gitops_repo_path`
- `.env.example` 또는 key schema

### Argo CD Integration

- `argo_project_name`
- `argo_destination_name`
- `argo_destination_server`
- `gitops_repo_url`
- `gitops_repo_branch`
- `gitops_repo_path`
- `gitops_repo_access_secret`

### Environment Variables

환경별로 `test / stage / prod` 값을 각각 입력합니다.

대표 예시:

```env
APP_NAME=my-service
APP_PORT=8080
LOG_LEVEL=info
DATABASE_URL=postgres://user:password@db:5432/app
REDIS_URL=redis://:password@redis:6379/0
JWT_SECRET=replace-me
SESSION_SECRET=replace-me
THIRD_PARTY_API_KEY=replace-me
```

`idea`는 이를 구조화 저장하고, 배포 시 `ConfigMap / Secret`으로 렌더링합니다.

배포 시에는 개발용 주소를 그대로 쓰지 않습니다.

- frontend의 API 호출은 가능하면 같은 hostname의 `/api`를 사용합니다.
- backend의 DB 주소는 `localhost:5432`가 아니라 `db` 같은 내부 Service 이름을 사용합니다.

### Cloudflare

- `base_domain`
- `cloudflare_account_id`
- `cloudflare_api_token`
- `tunnel_name` 또는 `tunnel_id`
- `test_hostname`
- `stage_hostname`
- `prod_hostname`
- `test_allowed_source_ips`
- `stage_allowed_source_ips`
- `admin_allowed_ips`

### Routing

- `entry_service_name`
- `backend_service_name`
- `backend_base_path` 기본값 `/api`

### Deployment Target

- 환경별 `dev / stage / prod` target profile
- 기본 provider:
  - `aws`
- 기본 AWS target:
  - `eks`
- 공통 입력:
  - `provider`
  - `cluster_type`
  - `namespace`
  - `service_port`
  - `build_source_strategy`
    - `repo_b_ci`
    - `platform_build_runner`
- AWS 입력:
  - `aws_region`
  - `aws_account_id`
  - `aws_auth_method`
    - `access_key`
    - `assume_role`
  - `aws_access_key_id`
  - `aws_secret_access_key`
  - `aws_role_arn`
  - `aws_cluster_name`
  - `aws_cluster_endpoint` 선택
- On-Prem 입력:
  - `argo_destination_name`
  - 또는 `kube_api_server`
  - `cluster_access_secret`

### Prod Blue-Green

- `prod_blue_green_enabled`
- `healthcheck_path`
- `healthcheck_timeout`
- `switch_after_healthy`
- `rollback_on_failure`

## Security Defaults

이 프로젝트의 기본 보안 전제는 아래와 같습니다.

- `.env` 원문 전체를 Git에 저장하지 않습니다.
- 민감값은 `idea` 내부 저장소에 암호화 저장합니다.
- 레포 B의 secret을 Git 저장소에 커밋하지 않습니다.
- GitHub Secrets를 런타임 secret store처럼 사용하지 않습니다.
- `test / stage`는 unrestricted public으로 열지 않습니다.
- `idea UI`와 `Grafana`는 admin allowlist만 허용합니다.
- DB는 외부 hostname 또는 Cloudflare Tunnel에 직접 노출하지 않습니다.
- 외부 라우팅은 플랫폼 `Caddy`가 담당하고, 앱 내부 `Caddy`는 기본 필수요건이 아닙니다.

## Export / Import

웹에서 설정한 값은 모두 versioned `Project State`로 저장됩니다.  
그래서 export/import는 부가 기능이 아니라 기본 저장 구조의 일부입니다.

이 의미는 다음과 같습니다.

- 웹에서 설정한 값 전체를 export할 수 있습니다.
- secret은 암호화된 상태로 bundle에 포함됩니다.
- import는 같은 schema를 복원합니다.
- import 후 같은 reconciliation 경로가 다시 실행됩니다.
- 결과적으로 동일한 GitOps 리소스와 동일한 Cloudflare 정책이 재현되어야 합니다.

## Repository Roles

- 레포 A:
  `idea` 플랫폼 자체의 소스코드 저장소
- 레포 B:
  실제 배포할 서비스 저장소
- `tmp 배포 계층`:
  `idea` 내부의 배포 오케스트레이션 로직

중요한 점:
사용자가 실제로 쓰는 서비스는 레포 B의 애플리케이션입니다.  
`tmp`는 별도 사용자 서비스가 아니라, 그 서비스를 배포하기 위한 내부 계층입니다.

## Non-Goals

이 프로젝트는 아래 방식으로 구현하지 않습니다.

- `test / stage / prod` 앱 배포에 Terraform 사용
- `test / stage / prod` 앱 배포에 Ansible 사용
- Argo CD가 레포 B 소스코드를 직접 빌드
- Argo CD를 임의 shell 실행기처럼 사용
- 레포 B의 `docker-compose.yml`을 서버에서 직접 실행
- prod DNS를 blue/green 각각에 직접 붙여서 전환
- `test / stage`를 unrestricted public으로 노출
- `idea UI` 또는 `Grafana`를 unrestricted public으로 노출
- DB를 public hostname 또는 Cloudflare Tunnel에 직접 연결
- GitHub Secrets를 런타임 secret store처럼 사용

## Documentation

더 자세한 아키텍처와 고정 규칙은 아래 문서를 참고하면 됩니다.

- [PROJECT_SPEC.md](/mnt/c/Users/rudgh/idea/PROJECT_SPEC.md)
- [RUNTIME_PROJECT_STATE_SPEC.md](/mnt/c/Users/rudgh/idea/RUNTIME_PROJECT_STATE_SPEC.md)

## Summary

`idea`는 On-Prem에 설치되는 배포 관리 플랫폼이며, 운영자는 웹 UI에서 서비스 저장소, 환경별 `.env`, hostname 및 내부 서비스 라우팅, Cloudflare 설정, 접근 정책, 배포 대상, prod blue-green 정책을 입력하고, 시스템은 이를 `Argo CD + platform Caddy + Cloudflare API reconciliation`으로 일관되게 실행합니다.
