# IaC MVP

이 디렉터리는 `idea` 플랫폼 설치용 IaC MVP를 담는다.

구성:

- `terraform/`
  단일 On-Prem 호스트 설치 계약을 정규화하고 Ansible 입력을 렌더링한다.
- `ansible/`
  Ubuntu 또는 macOS 단일 호스트에 Docker, kind, Argo CD, PostgreSQL, Vault dev mode, monitoring, platform Caddy, cloudflared 실행 기반과 GitOps 배포 경로를 설치한다.

현재 가정:

- 대상 OS는 Ubuntu 또는 macOS
- 단일 호스트
- container runtime은 Docker
- kind 위에 플랫폼 컴포넌트를 올린다

로컬 검증:

```bash
terraform fmt -check -recursive infra/terraform
cd infra/terraform && terraform init -backend=false && terraform validate
cd ../ansible && ANSIBLE_CONFIG=$PWD/ansible.cfg ansible-playbook --syntax-check -i inventory/hosts.ini.example site.yml
```

GitHub Actions 설정:

- 필수 repository secrets
  - `PLATFORM_SSH_PRIVATE_KEY`
  - `PLATFORM_TARGET_HOST`
  - `PLATFORM_TARGET_USER`
  - `PLATFORM_POSTGRESQL_PASSWORD`
  - `PLATFORM_VAULT_DEV_ROOT_TOKEN`
- private GitOps repo access에서 추가 필수 repository secret
  - `PLATFORM_GITOPS_REPO_TOKEN`
- Cloudflare API 자동화 모드에서 추가 필수 repository secrets
  - `PLATFORM_CLOUDFLARE_API_TOKEN`
- 수동 tunnel token 모드에서만 필요한 선택 repository secret
  - `PLATFORM_CLOUDFLARED_TUNNEL_TOKEN`
- 자주 쓰는 repository variables
  - `PLATFORM_TARGET_PORT=22`
  - `PLATFORM_TARGET_BECOME=false` for macOS targets, `true` for Linux targets
  - `PLATFORM_IDEA_BASE_DOMAIN=rnen.kr`
  - `PLATFORM_ENABLE_MONITORING=true`
  - `PLATFORM_ENABLE_VAULT=true`
  - `PLATFORM_ENABLE_CLOUDFLARED=true`
  - `PLATFORM_ENABLE_CLOUDFLARE_RECONCILIATION=true`
  - `PLATFORM_GITOPS_REPO_PATH=gitops/idea-platform/workloads`
  - `PLATFORM_GITOPS_REPO_USERNAME=x-access-token`
  - `PLATFORM_CLOUDFLARE_ACCOUNT_ID=<account-id>`
  - `PLATFORM_CLOUDFLARE_ZONE_ID=<zone-id>`
  - `PLATFORM_CLOUDFLARE_PUBLIC_SUBDOMAIN=idea`
  - `PLATFORM_CLOUDFLARE_TUNNEL_NAME=idea-platform`
  - `PLATFORM_CLOUDFLARE_ADMIN_ALLOWED_IPS=203.0.113.10/32`

주요 GitHub Actions 설정 의미:

- `PLATFORM_SSH_PRIVATE_KEY`
  - `PLATFORM_TARGET_HOST`와 `PLATFORM_TARGET_USER`로 SSH 접속할 수 있는 private key 원문
- `PLATFORM_TARGET_HOST`
  - 배포 제어 대상 호스트. 현재 구조에서는 보통 `ssh.rnen.kr`
- `PLATFORM_TARGET_USER`
  - 해당 호스트에 접속할 SSH 사용자. 현재 구조에서는 예: `rudgh`
- `PLATFORM_GITOPS_REPO_TOKEN`
  - Argo CD가 GitOps repo를 읽기 위한 GitHub token
  - 현재 repo가 private이면 필수
  - 최소 권한은 대상 repo `Contents: Read`
- `PLATFORM_GITOPS_REPO_PATH`
  - 현재 repo 안에서 Argo CD가 감시할 manifest 경로
- `PLATFORM_CLOUDFLARE_ACCOUNT_ID`
  - Tunnel API에 쓰는 Cloudflare account ID
- `PLATFORM_CLOUDFLARE_ZONE_ID`
  - DNS/WAF에 쓰는 `rnen.kr` zone ID
- `PLATFORM_CLOUDFLARE_ADMIN_ALLOWED_IPS`
  - `idea.<base_domain>` 접근을 허용할 관리자 공인 IP/CIDR 목록

Cloudflare 모드 선택 규칙:

- `PLATFORM_ENABLE_CLOUDFLARED=true` 이고 `PLATFORM_CLOUDFLARE_API_TOKEN`이 있으면
  - `PLATFORM_ENABLE_CLOUDFLARE_RECONCILIATION`를 따로 넣지 않아도 자동으로 Cloudflare API 자동화 모드로 동작한다
- `PLATFORM_ENABLE_CLOUDFLARED=true` 이고 `PLATFORM_CLOUDFLARED_TUNNEL_TOKEN`만 있으면
  - 수동 tunnel token 모드로 동작한다
- 두 모드를 모두 명시하고 싶으면 `PLATFORM_ENABLE_CLOUDFLARE_RECONCILIATION=true|false`로 강제할 수 있다

Cloudflare API token 권한:

- Account permission:
  - `Cloudflare Tunnel` `Edit`
- Zone permissions:
  - `DNS` `Edit`
  - `WAF` `Edit`
- Resource scope:
  - 대상 account 1개
  - 대상 zone 1개만 선택

권한 생성 참고:

- https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
- https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel-api/
- https://developers.cloudflare.com/waf/custom-rules/create-api/

중요한 경계:

- 이 IaC workflow는 `idea` 플랫폼 설치만 담당한다.
- 사용자 서비스 app repo 등록, build 정보, env, 배포 대상, Argo CD 연결, Caddy hostname 라우팅은 런타임 `idea UI`와 `tmp` 서비스가 관리한다.
- 즉 `PLATFORM_APP_REPO_URL` 같은 값은 더 이상 platform install workflow 입력이 아니다.

Cloudflare API 자동화 결과:

- `idea.<PLATFORM_IDEA_BASE_DOMAIN>` hostname용 tunnel ingress 생성
- `idea.<PLATFORM_IDEA_BASE_DOMAIN> -> <tunnel-id>.cfargotunnel.com` CNAME 생성
- `idea.<PLATFORM_IDEA_BASE_DOMAIN>`에 대해 `ADMIN_IP` 이외 요청을 block하는 WAF custom rule 생성
- Kubernetes `cloudflared` Deployment는 Cloudflare API에서 확보한 tunnel token으로 실행

실제 배포:

1. GitHub repository `Settings -> Secrets and variables -> Actions`에서 위 secrets와 variables를 등록한다.
2. self-hosted runner가 `self-hosted`, `macOS` 라벨로 온라인 상태인지 확인한다.
3. GitHub Actions `Deploy Platform MVP` workflow를 실행한다.

로컬 수동 배포가 필요하면 `infra/terraform/terraform.tfvars.example`를 참고해 별도 `tfvars` 파일을 만들어도 된다.
