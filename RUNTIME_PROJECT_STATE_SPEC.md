# RUNTIME_PROJECT_STATE_SPEC.md

## 1. Purpose

이 문서는 `idea` 웹 UI와 CLI가 동일하게 사용하는 런타임 배포 입력 schema를 정의한다.

- app repo에 배포 설정을 박아두지 않는다
- `tmp` 서비스는 웹 UI 또는 CLI로 받은 `Project State`를 canonical source로 사용한다
- `tmp`는 `Project State + repo 구조`를 읽고 GitOps 산출물을 생성한다
- Argo CD는 그 GitOps 산출물만 sync한다

즉 같은 값이 repo와 UI 양쪽에 있으면 항상 UI `Project State`가 우선한다.

중요한 점:

- app repo는 독립적인 웹 서비스 소스 저장소다
- IP allowlist, Cloudflare, Ncloud target, 실제 운영 secret, env별 hostname은 app repo가 아니라 `tmp`가 소유한다
- 같은 app repo를 `dev / stage / prod`에 재사용하는 것은 `tmp`가 환경별 `Project State`를 다르게 적용해서 구현한다

---

## 2. Canonical Principle

- 런타임 배포 입력은 모두 versioned `Project State`에 저장한다.
- 웹 UI와 CLI import는 동일한 schema를 사용한다.
- `tmp`는 `Project State + repo 구조`를 읽고 build/push, manifest 생성, Cloudflare desired state 생성을 수행한다.
- repo 내부 `docker-compose.yml`과 optional metadata는 참고 입력일 뿐이다.
- 같은 정보가 UI와 repo 양쪽에 있으면 UI가 우선한다.

---

## 3. Top-Level Shape

```yaml
project:
  name: repo-example
  app_repo_url: https://github.com/Ba-koD/repo_example
  git_ref: main
  repo_access_secret_ref: github-repo-example-token

build:
  source_strategy: platform_build_runner
  frontend_context: frontend
  frontend_dockerfile_path: frontend/Dockerfile
  backend_context: backend
  backend_dockerfile_path: backend/Dockerfile

argo:
  project_name: default
  destination_name: ""
  destination_server: https://kubernetes.default.svc
  gitops_repo_url: https://github.com/Ba-koD/idea.git
  gitops_repo_branch: main
  gitops_repo_path: gitops/apps
  gitops_repo_access_secret_ref: gitops-repo-token
  access_hint: https://argo.rnen.kr

cloudflare:
  enabled: true
  account_id: 2052eb94f7b555bd3bf9db83c1f4edbf
  zone_id: aaafd11f9c6912ba37c1d52a69b78398
  api_token_secret_ref: cloudflare-api-token
  tunnel_name: idea-platform
  route_mode: platform_caddy
  environments:
    dev:
      subdomain: repo-example-dev
      base_domain: rnen.kr
    stage:
      subdomain: repo-example-stage
      base_domain: rnen.kr
    prod:
      subdomain: repo-example
      base_domain: rnen.kr

targets:
  dev:
    provider: ncloud
    cluster_type: nks
    namespace: repo-example-dev
    service_port: 80
    ncloud:
      region_code: KR
      cluster_name: idea-dev
      auth_method: access_key
      access_key_secret_ref: ncloud-dev-access-key
      secret_key_secret_ref: ncloud-dev-secret-key
  stage:
    provider: ncloud
    cluster_type: nks
    namespace: repo-example-stage
    service_port: 80
    ncloud:
      region_code: KR
      cluster_name: idea-stage
      auth_method: access_key
      access_key_secret_ref: ncloud-stage-access-key
      secret_key_secret_ref: ncloud-stage-secret-key
  prod:
    provider: ncloud
    cluster_type: nks
    namespace: repo-example-prod
    service_port: 80
    ncloud:
      region_code: KR
      cluster_name: idea-prod
      auth_method: access_key
      access_key_secret_ref: ncloud-prod-access-key
      secret_key_secret_ref: ncloud-prod-secret-key

routing:
  dev_hostname: repo-example-dev.rnen.kr
  stage_hostname: repo-example-stage.rnen.kr
  prod_hostname: repo-example.rnen.kr
  entry_service_name: frontend
  backend_service_name: backend
  backend_base_path: /api

env:
  dev:
    APP_ENV: dev
    APP_DISPLAY_NAME: Repo Example Dev
    PUBLIC_API_BASE_URL: /api
  stage:
    APP_ENV: stage
    APP_DISPLAY_NAME: Repo Example Stage
    PUBLIC_API_BASE_URL: /api
  prod:
    APP_ENV: prod
    APP_DISPLAY_NAME: Repo Example Prod
    PUBLIC_API_BASE_URL: /api
    NODE_ENV: production

secrets:
  dev: {}
  stage: {}
  prod: {}

access:
  admin_allowed_source_ips:
    - 58.123.221.76/32
  dev_allowed_source_ips:
    - 58.123.221.76/32
  stage_allowed_source_ips:
    - 58.123.221.76/32
  prod_allowed_source_ips: []

delivery:
  prod_blue_green_enabled: true
  healthcheck_path: /api/healthz
  healthcheck_timeout_seconds: 30
  rollback_on_failure: true
```

---

## 4. Required Runtime UI Sections

## 3.1 .env Import / Export Contract

UI와 API는 `.env` text import와 file import를 모두 지원한다.

- `POST /api/project-state/import-env`
  - `env_file` 또는 `env_text`
  - `selected_env`
- `POST /api/project-state/export-env`
  - 현재 `selected_env` 기준 `.env` 생성
- `POST /api/provision-target`
  - `selected_env`
  - `project_state`
  - `apply`
  - Terraform 기반 Ncloud target provisioning 또는 dry-run

Ncloud provisioning 기본값:

- 기본 Kubernetes version: `1.33.4`
- 현재 지원 선택지: `1.33.4`, `1.34.3`, `1.32.8`
- `login_key_name`은 실제 Ncloud에 이미 존재하는 key 이름이어야 한다.

규칙:

- `IDEA_*` 키는 `Project State` 필드에 매핑된다.
- `IDEA_*_VALUE` 키는 control-plane secret value로 저장된다.
- prefix 없는 키는 runtime env 또는 runtime secret으로 들어간다.
- `SECRET`, `TOKEN`, `PASSWORD`, `JWT`, `DATABASE_URL` 류 key는 secret으로 분리된다.
- `IDEA_IMPORT_MODE=replace`면 현재 환경값을 덮어쓴다.
- `IDEA_SELECTED_ENV`가 있으면 해당 env가 우선한다.

로컬 import 테스트 파일:

- [`.env`](/mnt/c/Users/rudgh/idea/.env)
- [`.env.stage`](/mnt/c/Users/rudgh/idea/.env.stage)
- [`.env.prod`](/mnt/c/Users/rudgh/idea/.env.prod)

### Repository

- `project.name`
- `project.app_repo_url`
- `project.git_ref`
- `project.repo_access_secret_ref`

Important:

- `project.app_repo_url`은 전역 입력이고 `dev / stage / prod`에 공통 적용한다.
- 별도 `image_tag` 필드는 canonical `Project State`에 포함하지 않는다.
- 배포용 image tag 또는 digest는 build 결과 또는 GitOps 산출물에서 결정한다.

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

### Cloudflare

- `cloudflare.enabled`
- `cloudflare.account_id`
- `cloudflare.zone_id`
- `cloudflare.api_token_secret_ref`
- `cloudflare.tunnel_name`
- `cloudflare.route_mode`
- `cloudflare.environments.dev.subdomain`
- `cloudflare.environments.dev.base_domain`
- `cloudflare.environments.stage.subdomain`
- `cloudflare.environments.stage.base_domain`
- `cloudflare.environments.prod.subdomain`
- `cloudflare.environments.prod.base_domain`

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

UI note:

- env별 hostname preview는 Cloudflare의 `subdomain + base_domain` 조합으로 계산한다.
- `subdomain`이 `@` 또는 `*`면 bare `base_domain`을 hostname으로 사용한다.

### Environment Variables

- `env.dev`
- `env.stage`
- `env.prod`

### Runtime Secrets

- `secrets.dev`
- `secrets.stage`
- `secrets.prod`

### Access Policy

- `access.admin_allowed_source_ips`
- `access.dev_allowed_source_ips`
- `access.stage_allowed_source_ips`
- `access.prod_allowed_source_ips`

### Delivery Policy

- `delivery.prod_blue_green_enabled`

Important:

- 현재 schema와 UI는 `prod_blue_green_enabled`를 지원한다.
- 하지만 현재 GitOps generator는 아직 실제 `blue`/`green` workload 두 벌을 만들지 않는다.
- 즉 현재는 정책 플래그와 UI 상태까지만 구현돼 있다.
- Ncloud runtime provisioning은 구현돼 있지만, Cloudflare env reconcile은 아직 별도 단계다.
- `delivery.healthcheck_path`
- `delivery.healthcheck_timeout_seconds`
- `delivery.rollback_on_failure`

---

## 5. Secret Input Drawer Contract

UI는 일반 입력 폼과 별도로 `Secret Input` 영역 또는 modal/drawer를 가져야 한다.

이 영역에서 운영자가 값을 입력하면, UI는 평문을 직접 저장하지 않고 secret store reference로 치환해 `Project State`에 저장한다.

### Required Secret Inputs

- `project.repo_access_secret_ref`
- `argo.gitops_repo_access_secret_ref`
- `cloudflare.api_token_secret_ref`
- `targets.dev.ncloud.access_key_secret_ref`
- `targets.dev.ncloud.secret_key_secret_ref`
- `targets.stage.ncloud.access_key_secret_ref`
- `targets.stage.ncloud.secret_key_secret_ref`
- `targets.prod.ncloud.access_key_secret_ref`
- `targets.prod.ncloud.secret_key_secret_ref`
- `secrets.dev.*`
- `secrets.stage.*`
- `secrets.prod.*`

### Optional Secret Inputs

- `targets.<env>.cluster_access_secret_ref`
- `build.registry_push_secret_ref`
- `delivery.rollback_guard_secret_ref`

### UI Behavior

- 사용자는 secret key 이름과 실제 값을 입력한다.
- 저장 후 UI는 secret ref만 다시 보여준다.
- 이후 편집 화면에서는 기존 secret 평문을 재노출하지 않는다.
- CLI import도 같은 secret ref naming rule을 사용한다.
- `Cloudflare Apply` 또는 `Save and Reconcile` 동작 시 hostname, tunnel, allowlist 변경이 Cloudflare API 대상 desired state로 전달된다.

---

## 6. Ncloud Default Target Model

기본 provider는 `ncloud`, 기본 cluster type은 `nks`다.

### Required Ncloud Fields

- `ncloud.region_code`
- `ncloud.cluster_name`
- `ncloud.auth_method`

### Supported Auth Methods

#### `access_key`

- `ncloud.access_key_secret_ref`
- `ncloud.secret_key_secret_ref`

### Optional Ncloud Fields

- `ncloud.cluster_uuid`
- `ncloud.vpc_no`
- `ncloud.subnet_no`
- `ncloud.api_endpoint`
- `cluster_access_secret_ref`

### Runtime Meaning

- `tmp`는 이 정보를 사용해 대상 NKS cluster를 식별하고 Argo CD destination 또는 cluster registration에 필요한 값을 해석한다.
- Ncloud 자격증명은 UI에 평문 저장하지 않고 secret store reference로만 연결한다.
- `cluster_access_secret_ref`가 있으면 kubeconfig 기반 연결을 우선할 수 있다.

---

## 7. Secondary Target Models

Ncloud 이외의 target도 허용한다.

### AWS

- `provider: aws`
- `cluster_type: eks`
- `aws.region`
- `aws.cluster_name`
- `aws.access_key_secret_ref`
- `aws.secret_key_secret_ref`

### On-Prem

- `provider: onprem`
- `cluster_type: kubernetes`
- `namespace`
- `argo.destination_name` 또는 `argo.destination_server`
- `cluster_access_secret_ref`

---

## 8. Routing and Caddy Contract

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

Hostname derivation:

- `cloudflare.environments.dev.subdomain + base_domain -> routing.dev_hostname`
- `cloudflare.environments.stage.subdomain + base_domain -> routing.stage_hostname`
- `cloudflare.environments.prod.subdomain + base_domain -> routing.prod_hostname`
- `@` 또는 `*`는 bare domain을 의미한다.

### Important

- DB는 UI에서 hostname 연결 대상으로 선택할 수 없어야 한다.
- backend는 같은 hostname 아래 `/api`로만 외부 노출하는 것을 기본값으로 한다.
- frontend는 내부 `localhost`가 아니라 외부 same-origin `/api`를 사용해야 한다.

---

## 9. CLI Parity

웹 UI가 없어도 같은 `Project State`를 파일로 만들어 CLI에서 import할 수 있어야 한다.

### Example

```bash
python3 scripts/project_state_dry_run.py \
  examples/repo_example.ncloud.project-state.json
```

### Meaning

- UI가 저장하는 값과 CLI 파일은 같은 schema를 쓴다.
- dry-run은 repo 접근, build path, routing, target, secret ref 누락 여부를 검증한다.
- 실제 배포 구현이 들어가면 같은 파일이 `tmp` API 또는 worker 입력으로 그대로 사용된다.

---

## 10. Runtime Precedence

우선순위는 아래와 같다.

1. 웹 UI 또는 CLI `Project State`
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

## 11. Non-Goals

- app repo에 Ncloud credential을 커밋
- app repo에 Argo CD destination을 고정
- app repo에 prod hostname을 고정
- app repo에 운영용 dev/stage/prod secret 저장
- Argo CD를 임의 shell 실행기로 사용
- Terraform/Ansible로 dev/stage/prod 앱 배포를 직접 수행
