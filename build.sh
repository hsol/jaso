#!/bin/bash

# Poetry를 사용한 자소 앱 빌드 스크립트

set -e  # 오류 발생 시 스크립트 중단

echo "🚀 Poetry를 사용한 자소 앱 빌드를 시작합니다..."

# 기존 빌드 파일 정리
echo "🧹 기존 빌드 파일을 정리합니다..."
rm -rf build dist

# Poetry 환경에서 py2app로 빌드
echo "📦 Poetry 환경에서 py2app로 앱을 빌드합니다..."
poetry run python setup.py py2app

echo "✅ 빌드가 완료되었습니다!"
echo "�� 앱 위치: dist/자소.app" 