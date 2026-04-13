# App Sample

이 저장소에는 `idea` 플랫폼 위에 올릴 수 있는 최소 예제 앱이 포함되어 있다.

구조:

- [frontend](/mnt/c/Users/rudgh/idea/frontend)
- [backend](/mnt/c/Users/rudgh/idea/backend)
- [docker-compose.yml](/mnt/c/Users/rudgh/idea/docker-compose.yml)

기능:

- frontend는 runtime 설정의 `PUBLIC_API_BASE_URL`을 사용해 backend를 호출한다.
- backend는 현재 시간과 PostgreSQL의 `now()` 값을 함께 반환한다.
- health check endpoint:
  - `/api/healthz`
  - `/api/readyz`

## Local Run

`.env.example`를 `.env`로 복사한 뒤 실행한다.

```bash
cp .env.example .env
docker compose up --build
```

기본 접속:

- frontend: `http://localhost:3000`
- backend: `http://localhost:8080/api/healthz`
- postgres: `localhost:5432`

로컬에서는 frontend가 `PUBLIC_API_BASE_URL=http://localhost:8080/api`를 사용한다.
플랫폼 배포에서는 이 값을 `/api`로 주입하면 된다.

## Platform DB

현재 `idea` 플랫폼 IaC가 만드는 PostgreSQL 서비스는 아래다.

- service: `idea-postgresql`
- namespace: `idea-data`
- port: `5432`

즉 Kubernetes 배포 시 backend에는 보통 아래 값이 들어가면 된다.

```env
DATABASE_HOST=idea-postgresql.idea-data.svc.cluster.local
DATABASE_PORT=5432
DATABASE_NAME=idea
DATABASE_USER=idea
DATABASE_PASSWORD=<runtime secret>
```

비밀번호는 플랫폼 secret/runtime UI가 주입해야 한다. repo에 고정하지 않는다.

## Notes

- app 내부 `nginx`는 정적 파일 서빙만 담당한다.
- 외부 hostname과 `/api` 라우팅은 플랫폼 `Caddy`가 맡는다.
- repo에는 `.env.example`만 두고, 실제 `.env`는 git에 올리지 않는다.
