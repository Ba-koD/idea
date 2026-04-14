# TMP_UI_PANEL_SPEC.md

## 1. Goal

이 문서는 `tmp` 서비스가 가져야 하는 런타임 배포 UI 패널 구성을 정의한다.

핵심은 아래 두 가지다.

- 같은 app repo를 `dev / stage / prod`로 나눠 각각 다른 env, target, access policy로 배포할 수 있어야 한다
- provider 기본값은 `Ncloud + NKS`이고, Cloudflare API reconcile까지 같은 화면 흐름에서 이어져야 한다

추가 원칙:

- app repo는 독립적인 서비스 소스 저장소로 취급한다
- IP 차단, Cloudflare hostname, Tunnel, Ncloud target, secret 저장은 모두 `tmp` 패널에서 결정한다
- 즉 배포 정책은 repo가 아니라 `tmp` UI가 owner다

---

## 2. Top-Level Panels

필수 패널은 아래 순서를 권장한다.

1. Repository
2. Build
3. Argo CD
4. Targets
5. Routing
6. Environment
7. Secrets
8. Access
9. Delivery
10. Review / Apply

---

## 3. Repository Panel

### Fields

- `project.name`
- `project.app_repo_url`
- `project.git_ref`
- `project.repo_access_secret_ref`

### Behavior

- private repo면 secret drawer에서 token을 등록한다
- repo clone test 버튼을 둔다
- 성공 시 frontend/backend path 자동 추론을 시도한다

---

## 4. Build Panel

### Fields

- `build.source_strategy`
- `build.frontend_context`
- `build.frontend_dockerfile_path`
- `build.backend_context`
- `build.backend_dockerfile_path`

### Behavior

- `docker-compose.yml`이 있으면 context 후보를 자동 제안한다
- 사용자는 최종값을 직접 수정할 수 있다
- UI 값이 항상 repo 추론값보다 우선한다

---

## 5. Argo CD Panel

### Fields

- `argo.project_name`
- `argo.destination_name`
- `argo.destination_server`
- `argo.gitops_repo_url`
- `argo.gitops_repo_branch`
- `argo.gitops_repo_path`
- `argo.gitops_repo_access_secret_ref`

### Behavior

- destination 연결 테스트 버튼
- GitOps repo write 가능 여부 검증 버튼
- 실제 적용은 `tmp`가 generated manifest를 커밋하는 방식

---

## 6. Targets Panel

`dev`, `stage`, `prod` 각각 별도 카드 또는 탭으로 분리한다.

### Common Fields Per Environment

- `provider`
- `cluster_type`
- `namespace`
- `service_port`

### Default

- `provider = ncloud`
- `cluster_type = nks`

### Ncloud Required Fields Per Environment

- `region_code`
- `cluster_name`
- `cluster_version`
- `zone_code`
- `vpc_no`
- `subnet_no`
- `lb_subnet_no`
- `node_pool_name`
- `node_count`
- `node_product_code`
- `block_storage_size_gb`
- `auth_method`
- `access_key_secret_ref`
- `secret_key_secret_ref`

### Ncloud Optional Fields

- `cluster_uuid`
- `autoscale_enabled`
- `autoscale_min_node_count`
- `autoscale_max_node_count`
- `kubelet_args`
- `node_labels`
- `node_taints`
- `cluster_access_secret_ref`

### Why These Are Needed

- `node_count`, `node_product_code`, `block_storage_size_gb`는 서버 할당량과 용량을 결정한다
- `vpc_no`, `subnet_no`, `lb_subnet_no`는 네트워크 위치를 결정한다
- `node_pool_name`, `cluster_version`은 NKS worker pool 구성의 핵심 식별자다

### Panel Behavior

- `dev`, `stage`, `prod`는 같은 repo를 쓰더라도 target 값은 독립적으로 저장한다
- `dev`는 소형 node count를 기본 제안할 수 있다
- `prod`는 더 큰 instance type, 더 큰 node count, blue-green 요구값을 기본 제안할 수 있다

---

## 7. Routing Panel

### Fields

- `routing.dev_hostname`
- `routing.stage_hostname`
- `routing.prod_hostname`
- `routing.entry_service_name`
- `routing.backend_service_name`
- `routing.backend_base_path`

### Default

- `/` -> frontend
- `/api` -> backend

### Behavior

- DB는 선택 대상에 보여주지 않는다
- backend는 기본적으로 `/api`로만 외부 노출한다

---

## 8. Environment Panel

`dev`, `stage`, `prod` 각각 별도 env editor를 둔다.

### Required

- `env.dev`
- `env.stage`
- `env.prod`

### Recommended Defaults

- `APP_ENV`
- `APP_DISPLAY_NAME`
- `PUBLIC_API_BASE_URL`

### Example

- dev:
  - `APP_ENV=dev`
  - `APP_DISPLAY_NAME=Repo Example Dev`
- stage:
  - `APP_ENV=stage`
  - `APP_DISPLAY_NAME=Repo Example Stage`
- prod:
  - `APP_ENV=prod`
  - `APP_DISPLAY_NAME=Repo Example Prod`

### Behavior

- 같은 repo라도 env 값이 다르면 프론트는 각 환경 이름을 다르게 렌더링해야 한다
- 예: `APP_ENV=dev`면 메인 화면에 `dev environment` 텍스트가 떠야 한다

---

## 9. Secrets Panel

이 패널은 일반 env와 별도로 분리한다.

### Secret Drawer Required Inputs

- repo access token
- GitOps repo access token
- Ncloud access key
- Ncloud secret key
- Cloudflare API token
- env별 app secret

### Behavior

- plaintext는 입력 직후 마스킹하고 다시 보여주지 않는다
- UI에는 secret ref 이름만 남긴다
- `Project State`에는 secret ref만 저장한다

---

## 10. Access Panel

### Fields

- `access.admin_allowed_source_ips`
- `access.dev_allowed_source_ips`
- `access.stage_allowed_source_ips`

### Default Policy

- `prod`는 public
- `dev`, `stage`는 allowlist
- `idea UI`는 admin allowlist

---

## 11. Delivery Panel

### Fields

- `delivery.prod_blue_green_enabled`
- `delivery.healthcheck_path`
- `delivery.healthcheck_timeout_seconds`
- `delivery.rollback_on_failure`

### Behavior

- `prod` 카드에서만 blue-green 옵션을 강조한다
- `dev`, `stage`는 단일 slot 배포를 기본값으로 한다

---

## 12. Cloudflare Apply Behavior

Cloudflare는 별도 패널이 아니라 `Routing + Access + Review/Apply`에서 함께 정리해도 된다.

### Required Inputs

- `cloudflare.enabled`
- `cloudflare.account_id`
- `cloudflare.zone_id`
- `cloudflare.base_domain`
- `cloudflare.public_subdomain_prefix`
- `cloudflare.api_token_secret_ref`
- `cloudflare.tunnel_name`
- `cloudflare.route_mode`

### On Apply

`Apply` 또는 `Save and Reconcile`를 누르면 `tmp`는 아래를 수행해야 한다.

1. tunnel 존재 여부 확인
2. 필요 시 tunnel 생성 또는 재사용
3. env별 hostname desired state 계산
4. allowlist / WAF desired state 계산
5. GitOps manifest 생성
6. Cloudflare API reconcile 실행
7. Argo CD가 GitOps repo 변경을 sync

즉 Cloudflare API와 Argo CD는 분리된 실행 경로지만, UI에서는 하나의 apply 흐름으로 보여야 한다.

---

## 13. CLI Parity

웹 UI가 아직 없어도 아래와 같은 상태 파일로 같은 흐름을 재현할 수 있어야 한다.

```bash
python3 scripts/project_state_dry_run.py \
  examples/repo_example.ncloud.project-state.json
```

이 dry-run은 최소한 아래를 확인해야 한다.

- repo clone 가능
- build path 존재
- env / secret ref 구조 유효
- Ncloud target 필수 필드 존재
- Cloudflare 필수 필드 존재
