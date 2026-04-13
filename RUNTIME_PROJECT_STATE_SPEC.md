# RUNTIME_PROJECT_STATE_SPEC.md

## 1. Purpose

이 문서는 `idea` 웹 UI가 런타임에 받아야 하는 배포 입력의 canonical schema를 정의한다.  
핵심 원칙은 하나다.

- app repo에 배포 설정을 박아두지 않고, `tmp` 서비스가 웹 UI의 `Project State`를 기준으로 Argo CD용 GitOps 산출물을 자동 생성한다

즉 다음 값들은 repo 내부 파일보다 웹 UI 입력이 우선한다.

- app repo URL / ref
- build context / Dockerfile path
- Argo CD 연결 정보
- dev / stage / prod target profile
- Caddy hostname 및 `/api` 라우팅
- Cloudflare 정책
- 환경별 env / secret

---

## 2. Canonical Principle

- 런타임 배포 입력은 모두 versioned `Project State`에 저장한다.
- `tmp`는 `Project State + repo B 구조`를 읽고 GitOps manifest를 생성한다.
- Argo CD는 그 manifest만 sync한다.
- repo 내부 `docker-compose.yml`과 선택적 선언 파일은 참고 입력일 뿐이다.
- 같은 정보가 UI와 repo 양쪽에 있으면 UI가 우선한다.

---

## 3. Top-Level Shape

```yaml
project:
  name: my-service
  app_repo_url: https://github.com/acme/my-service.git
  git_ref: main
  repo_access_secret_ref: github-app-token

build:
  source_strategy: platform_build_runner
  frontend_context: frontend
  frontend_dockerfile_path: frontend/Dockerfile
  backend_context: backend
  backend_dockerfile_path: backend/Dockerfile

argo:
  project_name: default
  destination_name: aws-eks-dev
  destination_server: https://kubernetes.default.svc
  gitops_repo_url: https://github.com/acme/idea-gitops.git
  gitops_repo_branch: main
  gitops_repo_path: workloads/my-service
  gitops_repo_access_secret_ref: gitops-repo-token

targets:
  dev:
    provider: aws
    cluster_type: eks
    namespace: my-service-dev
    service_port: 80
    aws:
      region: ap-northeast-2
      account_id: "123456789012"
      auth_method: access_key
      access_key_secret_ref: aws-dev-key
      secret_key_secret_ref: aws-dev-secret
      cluster_name: idea-dev
  stage:
    provider: aws
    cluster_type: eks
    namespace: my-service-stage
    service_port: 80
    aws:
      region: ap-northeast-2
      account_id: "123456789012"
      auth_method: assume_role
      role_arn: arn:aws:iam::123456789012:role/idea-stage-deployer
      cluster_name: idea-stage
  prod:
    provider: aws
    cluster_type: eks
    namespace: my-service-prod
    service_port: 80
    aws:
      region: ap-northeast-2
      account_id: "123456789012"
      auth_method: assume_role
      role_arn: arn:aws:iam::123456789012:role/idea-prod-deployer
      cluster_name: idea-prod

routing:
  dev_hostname: dev.example.com
  stage_hostname: stage.example.com
  prod_hostname: prod.example.com
  entry_service_name: frontend
  backend_service_name: backend
  backend_base_path: /api

env:
  dev:
    APP_ENV: dev
    PUBLIC_API_BASE_PATH: /api
  stage:
    APP_ENV: stage
    PUBLIC_API_BASE_PATH: /api
  prod:
    APP_ENV: prod
    PUBLIC_API_BASE_PATH: /api

secrets:
  dev:
    DATABASE_URL: secret://db-dev-url
  stage:
    DATABASE_URL: secret://db-stage-url
  prod:
    DATABASE_URL: secret://db-prod-url

access:
  admin_allowed_source_ips:
    - 58.123.221.76/32
  dev_allowed_source_ips:
    - 58.123.221.76/32
  stage_allowed_source_ips:
    - 58.123.221.76/32

delivery:
  prod_blue_green_enabled: true
  healthcheck_path: /api/healthz
  healthcheck_timeout_seconds: 30
  rollback_on_failure: true
```

---

## 4. Required Runtime UI Sections

### Repository

- `project.name`
- `project.app_repo_url`
- `project.git_ref`
- `project.repo_access_secret_ref`

### Build

- `build.source_strategy`
  - `platform_build_runner`
  - `repo_b_ci`
- `build.frontend_context`
- `build.frontend_dockerfile_path`
- `build.backend_context`
- `build.backend_dockerfile_path`

### Argo CD

- `argo.project_name`
- `argo.destination_name`
- `argo.destination_server`
- `argo.gitops_repo_url`
- `argo.gitops_repo_branch`
- `argo.gitops_repo_path`
- `argo.gitops_repo_access_secret_ref`

### Deployment Targets

환경별로 따로 관리한다.

- `targets.dev`
- `targets.stage`
- `targets.prod`

각 target은 아래 공통 필드를 가진다.

- `provider`
- `cluster_type`
- `namespace`
- `service_port`

### Routing / Caddy

- `routing.dev_hostname`
- `routing.stage_hostname`
- `routing.prod_hostname`
- `routing.entry_service_name`
- `routing.backend_service_name`
- `routing.backend_base_path`

### Environment Variables

- `env.dev`
- `env.stage`
- `env.prod`

### Secrets

- `secrets.dev`
- `secrets.stage`
- `secrets.prod`

### Access Policy

- `access.admin_allowed_source_ips`
- `access.dev_allowed_source_ips`
- `access.stage_allowed_source_ips`

### Delivery Policy

- `delivery.prod_blue_green_enabled`
- `delivery.healthcheck_path`
- `delivery.healthcheck_timeout_seconds`
- `delivery.rollback_on_failure`

---

## 5. AWS Default Target Model

기본 provider는 `aws`, 기본 cluster type은 `eks`다.

### Required AWS Fields

- `aws.region`
- `aws.account_id`
- `aws.auth_method`
- `aws.cluster_name`

### Supported Auth Methods

#### `access_key`

- `aws.access_key_secret_ref`
- `aws.secret_key_secret_ref`

#### `assume_role`

- `aws.role_arn`

### Optional AWS Fields

- `aws.cluster_endpoint`
- `aws.external_id`

### Runtime Meaning

- `tmp`는 이 정보를 사용해 대상 EKS cluster를 식별하고 Argo CD destination 또는 cluster registration에 필요한 값을 해석한다.
- AWS 자격증명은 UI에 평문 저장하지 않고 secret store reference로만 연결한다.

---

## 6. On-Prem Target Model

AWS 이외의 self-managed target도 허용한다.

### Required On-Prem Fields

- `provider: onprem`
- `cluster_type: kubernetes`
- `namespace`
- `argo.destination_name` 또는 `argo.destination_server`
- `cluster_access_secret_ref`

### Runtime Meaning

- `tmp`는 저장된 kube access secret 또는 Argo CD destination mapping을 통해 target에 연결한다.

---

## 7. Routing and Caddy Contract

모든 hostname과 내부 라우팅은 웹 UI에서 설정 가능해야 한다.

### Required

- `entry_service_name`
- `backend_service_name`
- `backend_base_path`
- env별 hostname

### Default Flow

- `dev.<domain> -> cloudflared -> platform Caddy -> frontend`
- `dev.<domain>/api -> platform Caddy -> backend`
- `stage.<domain> -> cloudflared -> platform Caddy -> frontend`
- `stage.<domain>/api -> platform Caddy -> backend`
- `prod.<domain> -> cloudflared -> platform Caddy -> active prod slot`
- `prod.<domain>/api -> platform Caddy -> active prod backend`

### Important

- DB는 UI에서 hostname 연결 대상으로 선택할 수 없어야 한다.
- backend는 같은 hostname 아래 `/api`로만 외부 노출하는 것을 기본값으로 한다.

---

## 8. Runtime Precedence

우선순위는 아래와 같다.

1. 웹 UI `Project State`
2. repo B의 optional metadata
3. compose 추론값

즉 다음 값은 repo 내부에서 읽히더라도 UI가 덮어쓴다.

- build 경로
- entry service
- backend service
- backend path
- healthcheck
- target profile
- env / secret
- hostname

---

## 9. Non-Goals

- app repo에 AWS credential을 커밋
- app repo에 Argo CD destination을 고정
- app repo에 prod hostname을 고정
- app repo에 운영용 dev/stage/prod secret 저장
- Argo CD를 임의 shell 실행기로 사용
- Terraform/Ansible로 dev/stage/prod 앱 배포를 수행

