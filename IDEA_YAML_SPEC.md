# IDEA_YAML_SPEC.md

## 1. Purpose

`idea.yaml`은 `repo B` 루트에 둘 수 있는 선택적 선언 파일이다.  
목적은 배포 플랫폼이 이 레포를 더 안정적으로 해석하도록 돕는 것이다.

이 파일은 아래를 위한 것이다.

- 레포 구조를 명시적으로 선언
- `docker-compose.yml`만으로 부족한 배포 정보를 보완
- 제한된 hook과 health 정보를 선언
- GitOps manifest 생성 시 필요한 안정적인 메타데이터 제공

중요한 점:

- `idea.yaml`은 canonical runtime source가 아니다
- 웹 UI에서 저장된 `Project State`가 항상 우선한다
- `idea.yaml`이 없어도 배포 등록은 가능해야 한다

이 파일은 아래를 위한 것이 아니다.

- 임의 shell 실행
- 운영 서버 SSH 제어
- Terraform/Ansible 대체
- Argo CD를 스크립트 실행기로 바꾸는 것

---

## 2. File Location

파일명은 반드시 아래와 같다.

```text
idea.yaml
```

위치는 `repo B` 루트다.

```text
repo-b/
  idea.yaml
  docker-compose.yml
  .env.example
  frontend/
  backend/
  db/
```

---

## 3. Design Principles

### Declarative Only
- 이 파일은 상태와 의도를 선언한다
- 플랫폼은 이 파일을 읽고 Kubernetes manifest를 생성한다
- 단, 같은 필드가 웹 UI `Project State`에 있으면 UI 값이 우선한다

### Restricted Hooks
- hook은 허용된 단계에서만 실행된다
- hook 실행은 host shell이 아니라 Kubernetes `Job` 또는 Argo CD hook manifest 기준이다

### Repo-Local Semantics
- 명령은 repo B 컨테이너 이미지 안에서 실행 가능한 형태여야 한다
- 플랫폼의 내부 파일 경로, 서버 경로, SSH 경로를 가정하면 안 된다

### Reproducible Delivery
- 새 image tag/digest가 꽂히면 같은 방식으로 재현 배포 가능해야 한다
- interactive command, 수동 승인 전제, TTY 입력 전제는 허용하지 않는다

---

## 4. Supported Use Cases

`idea.yaml`은 아래 용도로만 사용한다.

- 앱 타입 선언
- entry/backend/db 서비스 식별
- health check 경로 선언
- migration hook 선언
- smoke test hook 선언
- prod blue/green 호환 정보 선언
- compose 자동 추론보다 우선할 명시 정보 제공
- 또는 웹 UI 입력을 도와주는 import 힌트 제공

---

## 5. Unsupported Use Cases

아래는 `idea.yaml` 범위가 아니다.

- 임의 bash 스크립트 여러 줄 실행
- 서버 파일 복사/삭제
- 패키지 설치
- host network 조작
- systemd 제어
- Docker daemon 직접 제어
- kubectl 임의 명령 실행
- AWS credential 저장
- Argo CD destination의 canonical 정의
- prod hostname의 canonical 정의

---

## 6. Top-Level Schema

최상위 스키마는 아래를 사용한다.

```yaml
version: 1

app:
  type: frontend-backend-db
  name: my-service

routing:
  entry_service_name: frontend
  backend_service_name: backend
  backend_base_path: /api

services:
  frontend:
    port: 3000
    image_source: frontend
  backend:
    port: 8080
    image_source: backend
  db:
    port: 5432
    internal_only: true

healthchecks:
  frontend:
    path: /
  backend:
    path: /api/healthz
    readiness_path: /api/readyz

hooks:
  pre_sync:
    migrate:
      service: backend
      command: ["npm", "run", "migrate"]
      timeout_seconds: 300
  post_sync:
    smoke_test:
      service: backend
      command: ["npm", "run", "smoke"]
      timeout_seconds: 120

delivery:
  blue_green_compatible: true
```

---

## 7. Field Specification

### `version`
- required
- 현재 허용값은 `1`

### `app`
- required

#### `app.type`
- required
- 허용값:
  - `frontend-backend-db`
  - `single-web-db`

#### `app.name`
- required
- GitOps 리소스 이름 prefix 용도

### `routing`
- required

#### `routing.entry_service_name`
- optional
- 외부 `/` 요청을 받을 서비스 이름

#### `routing.backend_service_name`
- optional
- 외부 `/api` 요청을 받을 서비스 이름

#### `routing.backend_base_path`
- optional
- 기본값 `/api`

### `services`
- optional
- 각 서비스의 기본 포트와 이미지 소스를 지정한다

#### `services.<name>.port`
- required
- 컨테이너 내부 포트

#### `services.<name>.image_source`
- optional
- CI가 이미지 빌드 시 대응할 logical service name
- 기본값은 key 이름과 동일

#### `services.<name>.internal_only`
- optional boolean
- 기본값 `false`
- DB는 `true`를 권장

### `healthchecks`
- optional

#### `healthchecks.<name>.path`
- required if healthcheck declared
- liveness 또는 기본 응답 경로

#### `healthchecks.<name>.readiness_path`
- optional
- backend는 `/api/readyz` 권장

### `hooks`
- optional
- 지원 단계:
  - `pre_sync`
  - `post_sync`

#### `hooks.pre_sync.migrate`
- optional
- DB migration 같은 선행 작업

#### `hooks.post_sync.smoke_test`
- optional
- 배포 직후 검증

#### `hooks.<phase>.<name>.service`
- required
- 어떤 서비스 이미지 안에서 실행할지 지정

#### `hooks.<phase>.<name>.command`
- required
- 문자열 배열
- 예: `["npm", "run", "migrate"]`

#### `hooks.<phase>.<name>.timeout_seconds`
- optional
- 기본값 `300`

### `delivery`
- optional

#### `delivery.blue_green_compatible`
- optional boolean
- 기본값 `false`
- prod blue/green 호환 여부

---

## 8. Hook Execution Rules

hook은 자유 실행이 아니라 제한 실행이다.

### Required
- hook 명령은 컨테이너 안에서 비대화식으로 실행 가능해야 한다
- stdin 입력 없이 종료 가능해야 한다
- 같은 명령을 재실행해도 치명적 부작용이 없어야 한다

### Runtime Model
- `pre_sync` hook은 Argo CD `PreSync` 성격의 Kubernetes `Job`로 실행될 수 있다
- `post_sync` hook은 Argo CD `PostSync` 성격의 Kubernetes `Job`로 실행될 수 있다
- 플랫폼은 선언된 command를 바탕으로 `Job` manifest를 생성할 수 있다

### Forbidden
- `["bash", "-lc", "..."]` 형태의 광범위한 쉘 스크립트 의존
- 수동 확인 입력을 기다리는 명령
- 플랫폼 host에 설치된 도구를 전제하는 명령

권장 예시:

```yaml
hooks:
  pre_sync:
    migrate:
      service: backend
      command: ["pnpm", "prisma", "migrate", "deploy"]
      timeout_seconds: 300
```

비권장 예시:

```yaml
hooks:
  pre_sync:
    migrate:
      service: backend
      command: ["bash", "-lc", "apk add curl && ./scripts/do-anything.sh"]
```

---

## 9. Relationship With `docker-compose.yml`

`docker-compose.yml`이 있어도 `idea.yaml`은 여전히 유효하다.

우선순위는 아래처럼 둔다.

1. `idea.yaml`
2. `docker-compose.yml`
3. 플랫폼 기본 추론

즉 compose만으로 애매한 값은 `idea.yaml`이 보완할 수 있지만, 최종 우선순위는 웹 UI `Project State`다.

대표 예시:

- 실제 entry 서비스 이름
- backend 서비스 이름
- health check 경로
- migration 명령
- smoke test 명령

---

## 10. Minimal Required Example

가장 기본적인 `frontend + backend + db` 서비스용 예시는 아래다.

```yaml
version: 1

app:
  type: frontend-backend-db
  name: sample-app

routing:
  entry_service_name: frontend
  backend_service_name: backend
  backend_base_path: /api

services:
  frontend:
    port: 3000
  backend:
    port: 8080
  db:
    port: 5432
    internal_only: true

healthchecks:
  frontend:
    path: /
  backend:
    path: /api/healthz
    readiness_path: /api/readyz

delivery:
  blue_green_compatible: true
```

---

## 11. Example With Hooks

```yaml
version: 1

app:
  type: frontend-backend-db
  name: sample-app

routing:
  entry_service_name: frontend
  backend_service_name: backend
  backend_base_path: /api

services:
  frontend:
    port: 3000
    image_source: frontend
  backend:
    port: 8080
    image_source: backend
  db:
    port: 5432
    internal_only: true

healthchecks:
  frontend:
    path: /
  backend:
    path: /api/healthz
    readiness_path: /api/readyz

hooks:
  pre_sync:
    migrate:
      service: backend
      command: ["npm", "run", "migrate"]
      timeout_seconds: 300
  post_sync:
    smoke_test:
      service: backend
      command: ["npm", "run", "smoke"]
      timeout_seconds: 120

delivery:
  blue_green_compatible: true
```

---

## 12. Validation Rules

플랫폼은 최소한 아래를 검증해야 한다.

- `version`이 지원되는 값인지
- `app.type`이 허용된 값인지
- `routing.entry_service_name`이 실제 서비스 정의와 일치하는지
- `routing.backend_service_name`이 실제 서비스 정의와 일치하는지
- hook의 `service`가 실제 서비스 정의와 일치하는지
- hook의 `command`가 빈 배열이 아닌지
- `db` 같은 internal 서비스가 외부 entry로 잘못 지정되지 않았는지

---

## 13. Recommended Defaults

특별한 이유가 없으면 아래를 기본값으로 쓴다.

- `app.type=frontend-backend-db`
- `routing.entry_service_name=frontend`
- `routing.backend_service_name=backend`
- `routing.backend_base_path=/api`
- `healthchecks.backend.path=/api/healthz`
- `healthchecks.backend.readiness_path=/api/readyz`
- `delivery.blue_green_compatible=true`

---

## 14. Direct Instruction For Repo Authors

`repo B`를 구현할 때는 아래처럼 생각하면 된다.

1. `docker-compose.yml`은 로컬 실행과 구조 설명용으로 유지한다.
2. `idea.yaml`은 배포 플랫폼에 전달할 명시 계약으로 둔다.
3. entry 서비스, backend 서비스, health check, migration 명령을 이 파일에 선언한다.
4. hook은 컨테이너 안에서 비대화식으로 실행 가능한 명령만 적는다.
5. 플랫폼이 host shell을 실행해 줄 것이라고 가정하지 않는다.
6. 새 image tag/digest만 반영되면 바로 Argo CD 배포가 가능하도록 구조를 유지한다.

---

## 15. One-Sentence Summary

`idea.yaml`은 `repo B`가 배포 플랫폼에 구조, 라우팅, health check, 제한된 hook을 선택적으로 힌트로 전달하기 위한 파일이며, 임의 실행기가 아니라 `docker-compose`와 웹 UI `Project State` 기반 GitOps manifest 생성을 보완하는 보조 계약 파일이다.
