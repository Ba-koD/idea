import os
import shutil
import tempfile
from jinja2 import Environment, FileSystemLoader

# 템플릿 폴더 위치 설정
env_loader = Environment(loader=FileSystemLoader("templates"))

def generate_all(data):
    """
    설계도의 Step 3: GitOps 리소스(K8s YAML) 생성 로직
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. 생성할 K8s 매니페스트 목록 (테라폼 대신 YAML)
        templates = ["deployment.yaml.j2", "service.yaml.j2"]
        
        # 2. Jinja2 렌더링
        for t_name in templates:
            try:
                template = env_loader.get_template(t_name)
                # UI에서 받은 데이터를 주입
                output_content = template.render(data.model_dump())
                
                output_file_name = t_name.replace(".j2", "")
                with open(os.path.join(tmp_dir, output_file_name), "w") as f:
                    f.write(output_content)
            except Exception as e:
                print(f"Template Error ({t_name}): {str(e)}")
        
        # 3. 결과물 저장 경로 (설계도 상의 GitOps repo/path 구조 준비)
        output_base_dir = os.path.join("outputs", data.project_name, data.env_type)
        if not os.path.exists(output_base_dir):
            os.makedirs(output_base_dir, exist_ok=True)
            
        # 4. 파일 복사
        for file_name in os.listdir(tmp_dir):
            shutil.copy(os.path.join(tmp_dir, file_name), os.path.join(output_base_dir, file_name))
        
        return output_base_dir
