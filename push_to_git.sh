#!/bin/bash

# 1. 모든 변경사항 스테이징
git add .

# 2. 커밋 메시지 입력 받기
read -p "커밋 메시지를 입력하세요 (기본값: 'update infra-forge-pro'): " msg
if [ -z "$msg" ]; then
    msg="update infra-forge-pro"
fi

# 3. 커밋 실행
git commit -m "$msg"

# 4. 깃허브로 푸시
echo "----------------------------------------"
echo "GitHub 업로드를 시작합니다..."
echo "----------------------------------------"

git push origin main

echo ""
echo "업로드가 완료되었습니다."
