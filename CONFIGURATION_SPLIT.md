# CONFIGURATION_SPLIT.md

## 1. Current Runtime Model

현재 이 저장소의 구조는 아래처럼 두 층으로 나뉜다.

- `idea` 플랫폼 설치
  - GitHub Actions + Terraform + Ansible
  - 대상: `idea` 웹, backend API, kind, Argo CD, Caddy, cloudflared, monitoring
- `tmp` 서비스 배포 입력
  - `idea` 웹 UI 또는 `.env` file/text import
  - 대상: app repo URL, `dev / stage / prod` env, secret, Cloudflare, Ncloud target, allowlist

런타임 배포 흐름은 이렇다.

1. 운영자가 `idea` 웹에서 `.env` 파일 업로드 또는 텍스트 붙여넣기를 한다.
2. `tmp` backend가 `IDEA_*` 키를 `Project State`로 저장한다.
3. prefix 없는 일반 키는 runtime env 또는 runtime secret으로 저장한다.
4. `tmp`가 GitOps bundle을 생성한다.
5. 필요하면 `tmp`가 Ncloud NKS target provisioning을 수행한다.
6. Argo CD가 Kubernetes에 sync한다.

중요한 점:

- `App Repository URL`은 전역값이다.
- `dev / stage / prod`는 같은 repo를 공유하고, env와 target만 달라진다.
- `dev / stage / prod` hostname은 Cloudflare `subdomain + base_domain`에서 계산된다.
- `prod_blue_green_enabled`는 state와 UI에는 반영돼 있지만, 현재 GitOps manifest는 아직 실제 blue/green workload 2벌을 생성하지 않는다.
- Ncloud provisioning은 `POST /api/provision-target` 경로로 실행된다.

## 2. IDEA Platform GitHub Actions Inputs

플랫폼 설치에 필요한 값은 GitHub `Settings -> Secrets and variables -> Actions`에 둔다.

### Required Secrets

- `PLATFORM_SSH_PRIVATE_KEY`
- `PLATFORM_TARGET_HOST`
- `PLATFORM_TARGET_USER`
- `PLATFORM_POSTGRESQL_PASSWORD`
- `PLATFORM_VAULT_DEV_ROOT_TOKEN`

### Optional Secrets

- `PLATFORM_CLOUDFLARE_API_TOKEN`
- `PLATFORM_CLOUDFLARED_TUNNEL_TOKEN`

### Common Variables

- `PLATFORM_TARGET_PORT`
- `PLATFORM_TARGET_BECOME`
- `PLATFORM_IDEA_BASE_DOMAIN`
- `PLATFORM_ENABLE_MONITORING`
- `PLATFORM_ENABLE_VAULT`
- `PLATFORM_ENABLE_CLOUDFLARED`
- `PLATFORM_ENABLE_CLOUDFLARE_RECONCILIATION`
- `PLATFORM_CLOUDFLARE_ACCOUNT_ID`
- `PLATFORM_CLOUDFLARE_ZONE_ID`
- `PLATFORM_CLOUDFLARE_PUBLIC_SUBDOMAIN`
- `PLATFORM_CLOUDFLARE_TUNNEL_NAME`
- `PLATFORM_CLOUDFLARE_ADMIN_ALLOWED_IPS`

이 값들은 `idea` 플랫폼 자체를 띄우는 데만 쓴다. app repo URL, app runtime env, env별 hostname, Ncloud target 같은 값은 여기에 두지 않는다.

## 3. tmp Provisioning .env Inputs

`tmp`는 `.env` file import와 text import를 둘 다 지원한다.

- file import: UI의 `IMPORT FILE`
- text import: UI의 `IMPORT TEXT`
- export: UI의 `EXPORT .ENV`

### Prefix Rule

- `IDEA_*`
  - `Project State` 갱신
  - 예: repo URL, Argo CD, Cloudflare, Ncloud, allowlist, delivery
- `IDEA_*_VALUE`
  - control-plane secret value 입력
  - 현재 지원: repo token, gitops token, Cloudflare API token, Ncloud access/secret key
- prefix 없는 키
  - runtime env 또는 runtime secret
  - key 이름이 `SECRET`, `TOKEN`, `PASSWORD`, `JWT`, `DATABASE_URL` 류면 secret으로 분리됨

### Core IDEA Keys

- `IDEA_SELECTED_ENV`
- `IDEA_IMPORT_MODE`
- `IDEA_PROJECT_NAME`
- `IDEA_APP_REPOSITORY_URL`
- `IDEA_GIT_REF`
- `IDEA_REPO_ACCESS_SECRET_REF`
- `IDEA_GITOPS_REPO_URL`
- `IDEA_GITOPS_REPO_BRANCH`
- `IDEA_GITOPS_REPO_PATH`
- `IDEA_GITOPS_REPO_ACCESS_SECRET_REF`
- `IDEA_ARGO_DESTINATION_SERVER`
- `IDEA_CLOUDFLARE_ACCOUNT_ID`
- `IDEA_CLOUDFLARE_ZONE_ID`
- `IDEA_CLOUDFLARE_API_TOKEN_SECRET_REF`
- `IDEA_CLOUDFLARE_TUNNEL_NAME`
- `IDEA_CLOUDFLARE_SUBDOMAIN`
- `IDEA_CLOUDFLARE_BASE_DOMAIN`
- `IDEA_NAMESPACE`
- `IDEA_NCLOUD_REGION_CODE`
- `IDEA_NCLOUD_CLUSTER_NAME`
- `IDEA_NCLOUD_ZONE_CODE`
- `IDEA_NCLOUD_VPC_NO`
- `IDEA_NCLOUD_SUBNET_NO`
- `IDEA_NCLOUD_LB_SUBNET_NO`
- `IDEA_NCLOUD_ACCESS_KEY_SECRET_REF`
- `IDEA_NCLOUD_SECRET_KEY_SECRET_REF`
- `IDEA_ADMIN_ALLOWED_SOURCE_IPS`
- `IDEA_ENV_ALLOWED_SOURCE_IPS`
- `IDEA_PROD_BLUE_GREEN_ENABLED`
- `IDEA_HEALTHCHECK_PATH`

### Control-Plane Secret Value Keys

- `IDEA_REPO_ACCESS_TOKEN_VALUE`
- `IDEA_GITOPS_REPO_ACCESS_TOKEN_VALUE`
- `IDEA_CLOUDFLARE_API_TOKEN_VALUE`
- `IDEA_NCLOUD_ACCESS_KEY_VALUE`
- `IDEA_NCLOUD_SECRET_KEY_VALUE`

위 키는 현재 env의 실제 secret ref 이름에 자동 매핑된다. ref 이름이 `ncloud-dev-access-key`든 `ncp_iam_...`이든 상관없이 현재 state 기준 ref에 연결된다.

중요한 구분:

- `*_SECRET_REF`
  - Project State 안에 저장되는 논리 이름
  - 예: `IDEA_NCLOUD_ACCESS_KEY_SECRET_REF=ncloud-dev-access-key`
- `*_VALUE`
  - tmp provisioning에 실제로 쓰이는 자격증명 원문
  - 예: `IDEA_NCLOUD_ACCESS_KEY_VALUE=<real-access-key>`

즉 `REF = 이름`, `VALUE = 실제 값`이다.

### Runtime Keys Example

- `APP_ENV`
- `APP_DISPLAY_NAME`
- `PUBLIC_API_BASE_URL`
- `PUBLIC_API_BASE_PATH`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `JWT_SECRET` if the app actually signs or verifies JWTs

루트 import 테스트 파일:

- [`.env`](/mnt/c/Users/rudgh/idea/.env)
- [`.env.stage`](/mnt/c/Users/rudgh/idea/.env.stage)
- [`.env.prod`](/mnt/c/Users/rudgh/idea/.env.prod)

이 세 파일은 의도적으로 slim import 예시다.

- platform install용 `PLATFORM_*` 값은 넣지 않는다
- 기본값으로 충분한 필드는 생략했다
- 실제로 자주 바꾸는 app repo / app env / target / control-plane credential 값만 남겼다

## 4. Auto-Resolved vs Manual Values

### Auto-Resolved Today

- `routing.dev_hostname`, `routing.stage_hostname`, `routing.prod_hostname`
- runtime ConfigMap payload
- inline runtime Secret manifest
- Argo CD Application manifest
- env export file path

### Still Manual Today

- 실제 `IDEA_NCLOUD_ACCESS_KEY_VALUE`
- 실제 `IDEA_NCLOUD_SECRET_KEY_VALUE`
- 실제 `IDEA_NCLOUD_LOGIN_KEY_NAME`
- private repo라면 실제 `IDEA_REPO_ACCESS_TOKEN_VALUE`
- GitOps repo가 private라면 실제 `IDEA_GITOPS_REPO_ACCESS_TOKEN_VALUE`
- Cloudflare apply까지 돌릴 거라면 실제 `IDEA_CLOUDFLARE_API_TOKEN_VALUE`

기존 infra를 재사용할 때만 수동으로 필요한 값:

- 기존 `cluster_uuid`
- 기존 `vpc_no`
- 기존 `subnet_no`
- 기존 `lb_subnet_no`

즉 현재는 Ncloud target을 state에 저장하는 수준을 넘어서, backend가 Terraform으로 Ncloud VPC/Subnet/NKS target을 실제 provision할 수 있다. 신규 리소스를 만들 경우 `vpc_no/subnet_no/lb_subnet_no`는 placeholder여도 괜찮고, provider credential과 login key만 실제 값이어야 한다.

## 5. Ncloud Provisioning Gap

현재 저장소는 `Ncloud + NKS`를 기본 target model로 다루고, 실제 API 기반 provisioning 1차 경로가 구현돼 있다.

실제 구현에 필요한 핵심 값:

- `IDEA_NCLOUD_REGION_CODE`
- `IDEA_NCLOUD_ZONE_CODE`
- `IDEA_NCLOUD_CLUSTER_NAME`
- `IDEA_NCLOUD_CLUSTER_VERSION`
- `IDEA_NCLOUD_VPC_NO`
- `IDEA_NCLOUD_SUBNET_NO`
- `IDEA_NCLOUD_LB_SUBNET_NO`
- `IDEA_NCLOUD_NODE_POOL_NAME`
- `IDEA_NCLOUD_NODE_COUNT`
- `IDEA_NCLOUD_NODE_PRODUCT_CODE`
  NKS node `serverSpecCode` 값이다. 예: `s2-g3a`, `s4-g3a`
- `IDEA_NCLOUD_BLOCK_STORAGE_SIZE_GB`
- `IDEA_NCLOUD_ACCESS_KEY_SECRET_REF`
- `IDEA_NCLOUD_SECRET_KEY_SECRET_REF`

현재 provisioning 경로는 아래를 수행한다.

- 기존 cluster UUID가 있으면 existing cluster fetch
- 없으면 VPC / node subnet / LB subnet / NKS cluster / node pool 생성
- kubeconfig 생성
- Argo CD cluster Secret manifest 생성
- 생성된 `cluster_uuid`, subnet id, endpoint를 Project State에 다시 저장

현재도 수동으로 필요한 값:

- 지원되는 Kubernetes version 중 하나
  - `1.33.4`
  - `1.34.3`
  - `1.32.8`
- 실제 Ncloud login key name
- 실제 Ncloud access key / secret key
- 기존 리소스를 재사용할 때만 `vpc_no`, `subnet_no`, `lb_subnet_no`, `cluster_uuid`

## 6. Current Implementation Status

### Implemented

- `.env` file import
- `.env` text import
- `.env` export
- `IDEA_*` -> `Project State` 매핑
- `IDEA_*_VALUE` -> control-plane secret value 매핑
- runtime env / runtime secret 분리
- Argo CD bundle generation
- env별 Cloudflare hostname state 저장
- env별 allowlist state 저장
- `POST /api/provision-target` Ncloud runtime provisioning
- kubeconfig / Argo CD cluster secret artifact 생성
- provisioning 후 platform Argo CD cluster secret 자동 적용 시도
- provisioning 후 `argo.rnen.kr` Cloudflare tunnel/DNS/WAF 자동 reconcile 시도

### Not Implemented Yet

- prod blue/green workload 두 벌 생성과 실제 무중단 전환

즉 현재 구조는 `idea provisioning`과 `tmp provisioning input`의 경계는 정리됐고, import/export와 Ncloud runtime provisioning도 동작한다. 남은 큰 작업은 env별 app runtime Cloudflare reconcile과 real blue/green rollout이다.
