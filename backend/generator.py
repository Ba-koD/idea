import os
import shutil
import tempfile
from jinja2 import Environment, FileSystemLoader

# 템플릿 폴더 위치 설정
env_loader = Environment(loader=FileSystemLoader("templates"))

def create_infra_zip(data: object):
    # 1. 임시 작업 폴더 생성 (파일을 잠시 굽는 곳)
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 생성할 파일 목록 정의
        templates = ["provider.tf.j2", "vpc.tf.j2", "ec2.tf.j2"]
        if data.db_enabled:
            templates.append("rds.tf.j2")
        
        # 2. Jinja2를 이용해 템플릿 렌더링
        for t_name in templates:
            template = env_loader.get_template(t_name)
            # 데이터를 딕셔너리 형태로 변환하여 템플릿에 주입
            output_content = template.render(data.model_dump())
            
            # .j2 확장자를 제거하고 실제 .tf 파일로 저장
            output_file_name = t_name.replace(".j2", "")
            with open(os.path.join(tmp_dir, output_file_name), "w") as f:
                f.write(output_content)
        
        # 3. 결과물 압축 (outputs 폴더에 저장)
        if not os.path.exists("outputs"):
            os.makedirs("outputs")
            
        zip_base_name = os.path.join("outputs", f"{data.project_name}_{data.env}")
        zip_file_path = shutil.make_archive(zip_base_name, 'zip', tmp_dir)
        
        return zip_file_path
