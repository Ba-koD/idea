# PROVISIONING_GUIDELINES.md

## 1. Goal

이 문서는 `idea`가 app repo를 어떻게 프로비저닝해야 하는지에 대한 구현 가이드라인이다.

기본 원칙은 단순하다.

- app repo는 애플리케이션 코드와 build 입력만 가진다
- 런타임 배포 입력은 `Project State`가 가진다
- `tmp`는 `Project State + repo 구조`를 읽어 build, GitOps, Argo CD, Cloudflare를 연결한다

즉 app repo는 독립적인 웹 서비스 소스 저장소일 뿐이고, 배포 정책의 owner는 아니다.

---

## 1.1 Ownership Boundary

### App Repo Owns

- frontend / backend 소스 코드
- Dockerfile
- 로컬 실행용 `.env.example`
- optional `docker-compose.yml`
- health check와 runtime env를 읽는 애플리케이션 코드

### tmp Owns

- dev / stage / prod 실제 env 값
- 운영용 secret 값
- Ncloud target 선택
- Argo CD destination
- GitOps manifest 생성
- Cloudflare Tunnel / hostname / IP allowlist / WAF 적용
- 배포 실행과 rollback 정책

### Important

- app repo는 IP 접속 차단을 구현하지 않는다
- app repo는 Cloudflare API를 직접 호출하지 않는다
- app repo는 배포 환경을 선택하지 않는다
- 같은 repo를 dev / stage / prod에 재사용하는 것은 `tmp`가 env를 다르게 주입해서 구현한다

---

## 2. Frontend Guideline

### Required

- frontend는 외부 same-origin을 기준으로 backend를 호출해야 한다.
- backend API 경로는 기본적으로 `/api`를 사용한다.
- frontend는 내부 `localhost:8080` 같은 값을 가정하면 안 된다.
- 내부 reverse proxy가 꼭 필요하지 않으면 앱 내부 Caddy/Nginx에서 `/api` 라우팅을 하지 않는다.

### Recommended

- 정적 파일은 단순 웹 서버로 서빙한다.
- runtime config가 필요하면 `config.js`나 HTML template 치환 방식을 사용한다.
- health check는 `/` 또는 정적 asset 응답으로 충분하다.

### Avoid

- frontend 코드에 cluster host나 internal DNS를 박아두기
- prod hostname을 repo에 하드코딩하기
- 배포 환경별 `.env.dev/.env.stage/.env.prod`를 canonical source로 사용하기

---

## 3. Backend Guideline

### Required

- backend는 `/api/healthz`와 `/api/readyz`를 제공해야 한다.
- backend는 `0.0.0.0`으로 바인딩해야 한다.
- 내부 의존성은 `localhost`가 아니라 Kubernetes Service 이름을 사용해야 한다.
- backend는 stateless 기본값을 따라야 한다.

### Recommended

- 기본 포트는 `8080`
- JSON 응답 기본
- migration은 별도 Job 또는 hook command로 분리
- DB, cache, queue 주소는 env로 주입

### Avoid

- backend가 외부 hostname을 직접 프록시 대상으로 가정하는 것
- compose 전용 네트워크 이름에 강하게 결합하는 것
- 실행 시 interactive setup이 필요한 것

---

## 4. Repo Contract

`tmp`가 기대하는 최소 repo 구조는 아래다.

```text
repo/
  frontend/
    Dockerfile
  backend/
    Dockerfile
  docker-compose.yml        # optional but recommended
  .env.example             # optional but recommended
```

### Required Inputs From Project State

- repo URL / git ref
- frontend context / Dockerfile path
- backend context / Dockerfile path
- Argo CD destination
- dev / stage / prod target
- env별 `subdomain + base_domain` 조합으로 계산한 hostname / `/api` routing
- env / secret

Important:

- `App Repository URL`은 전역 입력이고 `dev / stage / prod` 전체에 공통 적용한다.
- 별도 `image tag` UI 입력은 두지 않고, build 결과의 image tag/digest를 GitOps 산출물에 반영한다.

---

## 5. Provisioning Flow

1. 운영자가 UI 또는 CLI로 `Project State`를 제출한다.
2. `tmp`가 repo를 clone하고 build path를 검증한다.
3. `tmp`가 frontend/backend 이미지를 build한다.
4. `tmp`가 registry에 이미지를 push한다.
5. `tmp`가 env별 GitOps manifest를 생성한다.
6. `tmp`가 platform Caddy routing과 Cloudflare desired state를 생성한다.
7. Argo CD가 GitOps repo 변경을 sync한다.

중요한 점:

- Argo CD는 app source repo를 직접 build하지 않는다.
- app repo 변경만으로는 배포되지 않는다.
- GitOps manifest가 바뀌어야 Argo CD가 움직인다.

현재 구현 상태:

- `.env` file import / text import는 구현돼 있다.
- `Project State -> GitOps bundle` 생성도 구현돼 있다.
- `POST /api/provision-target` 경로로 Ncloud VPC/Subnet/NKS runtime provisioning 1차 경로도 구현돼 있다.
- provisioning 결과로 `cluster_uuid`, subnet id, endpoint, kubeconfig, Argo CD cluster secret manifest가 나온다.
- prod blue-green도 현재는 state/UI 플래그만 있고, 실제 manifest 2벌 생성은 아직 없다.

---

## 6. Ncloud Default Model

기본 타깃은 `Ncloud + NKS`로 둔다.

### UI Required Fields

- `provider = ncloud`
- `cluster_type = nks`
- `region_code`
- `cluster_name`
- `namespace`
- `service_port`

### UI Secret Drawer Fields

- `repo_access_secret`
- `gitops_repo_access_secret`
- `ncloud_access_key`
- `ncloud_secret_key`
- env별 runtime secret들

### Notes

- UI는 secret 값을 저장하지 않고 secret ref만 `Project State`에 남긴다.
- Ncloud access key/secret key는 target별로 분리 가능해야 한다.
- `cluster_access_secret`가 있으면 kubeconfig 기반 연결도 허용한다.
- 실제 Ncloud provisioning 구현에는 최소 `region_code`, `zone_code`, `cluster_name`, `vpc_no`, `subnet_no`, `lb_subnet_no`, `node_pool_name`, `node_count`, `node_product_code`, `block_storage_size_gb`, `access_key_secret_ref`, `secret_key_secret_ref`가 필요하다.
- 실제 apply 전 수동 확인이 필요한 값:
  - 지원되는 Kubernetes version인지 확인
    - `1.33.4`
    - `1.34.3`
    - `1.32.8`
  - Ncloud login key name
  - 실제 access key / secret key 값
  - 기존 리소스를 재사용하려면 `cluster_uuid`, `vpc_no`, `subnet_no`, `lb_subnet_no`
  - 신규 리소스를 만들면 placeholder `vpc-*` / `subnet-*` 값은 backend가 실제 id로 대체한다

---

## 7. CLI Dry-Run

UI 구현 전에는 같은 schema를 파일로 만들어 dry-run할 수 있다.

```bash
python3 scripts/project_state_dry_run.py \
  examples/repo_example.ncloud.project-state.json
```

이 명령은:

- repo clone
- frontend/backend Dockerfile path 검증
- compose 존재 여부 확인
- target/routing/secret ref 요약

을 수행한다.

---

## 8. UI Guidance

UI는 최소 아래 탭 또는 섹션을 가져야 한다.

- Repository
- Build
- Argo CD
- Targets
- Routing
- Environment
- Secrets
- Access
- Delivery

Cloudflare 입력은 환경별 `subdomain`과 `base_domain`을 따로 받아야 하며, `subdomain`이 `@` 또는 `*`면 bare domain으로 해석한다.

### Secrets Tab

이 탭에서는 아래를 입력한다.

- repo access token
- GitOps repo access token
- provider credential secret
- env별 runtime secret

저장 후에는 plaintext 대신 secret ref 이름만 보여준다.
