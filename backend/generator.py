import os
import shutil
import tempfile
from jinja2 import Environment, FileSystemLoader

# 템플릿 폴더 위치 설정
env_loader = Environment(loader=FileSystemLoader("templates"))

def generate_all(data): # 함수 이름을 main.py와 맞춤
    # 1. 임시 작업 폴더 생성
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 생성할 기본 파일 목록
        templates = ["provider.tf.j2", "vpc.tf.j2", "ec2.tf.j2", "rds.tf.j2"]
        
        # 2. Jinja2를 이용해 템플릿 렌더링
        for t_name in templates:
            try:
                template = env_loader.get_template(t_name)
                # Pydantic 모델(data)을 딕셔너리로 변환하여 템플릿에 주입
                output_content = template.render(data.model_dump())
                
                # .j2 확장자를 제거하고 실제 .tf 파일로 저장
                output_file_name = t_name.replace(".j2", "")
                with open(os.path.join(tmp_dir, output_file_name), "w") as f:
                    f.write(output_content)
            except Exception as e:
                print(f"Template rendering skip or error: {t_name} -> {str(e)}")
        
        # 3. 결과물 저장 경로 설정 (outputs/[프로젝트명]/[환경])
        output_base_dir = os.path.join("outputs", data.project_name, data.env_type)
        if not os.path.exists(output_base_dir):
            os.makedirs(output_base_dir)
            
        # 파일을 임시 폴더에서 실제 outputs 폴더로 복사
        for file_name in os.listdir(tmp_dir):
            shutil.copy(os.path.join(tmp_dir, file_name), os.path.join(output_base_dir, file_name))
        
        # main.py에서 ZIP을 만들 수 있도록 경로 반환
        return output_base_dir
