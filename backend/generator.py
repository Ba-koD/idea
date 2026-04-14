import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
env_loader = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def env_block(env_map: dict[str, str]) -> str:
    return "\n".join(f"{key}={value}" for key, value in sorted(env_map.items()))


def render_template(template_name: str, context: dict) -> str:
    template = env_loader.get_template(template_name)
    return template.render(**context).strip() + "\n"


def generate_all(project_state: dict, selected_env: str) -> Path:
    project = project_state["project"]
    argo = project_state["argo"]
    target = project_state["targets"][selected_env]
    cloudflare_env = project_state["cloudflare"]["environments"][selected_env]
    hostname = project_state["routing"][f"{selected_env}_hostname"]
    output_dir = Path("outputs") / project["name"] / selected_env
    output_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "project": project,
        "argo": argo,
        "target": target,
        "cloudflare": project_state["cloudflare"],
        "cloudflare_env": cloudflare_env,
        "routing": project_state["routing"],
        "access": project_state["access"],
        "delivery": project_state["delivery"],
        "selected_env": selected_env,
        "hostname": hostname,
        "runtime_env_block": env_block(project_state["env"][selected_env]),
        "runtime_secrets_block": env_block(project_state["secrets"][selected_env]),
        "project_state_json": json.dumps(project_state, indent=2, ensure_ascii=True),
    }

    rendered_files = {
        "namespace.yaml": render_template("namespace.yaml.j2", context),
        "argocd-application.yaml": render_template("argocd-application.yaml.j2", context),
        "runtime-configmap.yaml": render_template("runtime-configmap.yaml.j2", context),
        "deploy-summary.txt": render_template("deploy-summary.txt.j2", context),
        "runtime-project-input.json": context["project_state_json"] + "\n",
        "project-state.json": context["project_state_json"] + "\n",
    }

    for file_name, content in rendered_files.items():
        (output_dir / file_name).write_text(content, encoding="utf-8")

    return output_dir
