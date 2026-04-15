FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git unzip \
    && curl -fsSL -o /tmp/terraform.zip https://releases.hashicorp.com/terraform/1.14.4/terraform_1.14.4_linux_amd64.zip \
    && unzip -q /tmp/terraform.zip -d /usr/local/bin \
    && rm -rf /var/lib/apt/lists/* /tmp/terraform.zip

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api_models.py env_import.py generator.py gitops_sync.py main.py provisioning.py state_store.py ./
COPY templates ./templates

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
