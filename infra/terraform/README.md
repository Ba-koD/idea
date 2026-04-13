# Terraform Contract

이 디렉터리의 Terraform은 provider-specific 인프라 생성을 대신하는 단일 호스트 설치 계약을 정규화한다.

현재 MVP 범위:

- On-Prem 단일 호스트 대상 입력 검증
- Ansible inventory 렌더링
- Ansible extra vars 렌더링
- Argo CD GitOps repo 연결 계약 전달
- 설치 계약 출력

현재 범위 밖:

- VM 생성
- vSphere / Proxmox / libvirt 연동
- 네트워크 장비 변경

기본 사용 순서:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init -backend=false
terraform apply -auto-approve
terraform output -raw ansible_inventory_ini
terraform output -json ansible_extra_vars
```
