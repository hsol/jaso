#!/bin/bash

# 자소 앱 DMG 설치 파일 생성 스크립트

set -e  # 오류 발생 시 스크립트 중단

echo "🚀 자소 앱 DMG 설치 파일 생성을 시작합니다..."

# 변수 설정
APP_NAME="자소"
VERSION="0.1.0"
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
VOLUME_NAME="${APP_NAME}"

# 기존 빌드 파일 정리
echo "🧹 기존 빌드 파일을 정리합니다..."
rm -rf build dist *.dmg

# 먼저 앱 빌드
echo "📦 앱을 빌드합니다..."
poetry run python setup.py py2app

# 앱이 성공적으로 빌드되었는지 확인
if [ ! -d "dist/${APP_NAME}.app" ]; then
    echo "❌ 앱 빌드에 실패했습니다."
    exit 1
fi

echo "✅ 앱 빌드가 완료되었습니다."

# 임시 디렉토리 생성
echo "📦 임시 디렉토리를 생성합니다..."
TEMP_DIR=$(mktemp -d)
mkdir -p "${TEMP_DIR}"

# 앱을 임시 디렉토리로 복사
echo "📦 앱을 임시 디렉토리로 복사합니다..."
cp -R "dist/${APP_NAME}.app" "${TEMP_DIR}/"

# Applications 폴더 링크 생성
echo "📦 Applications 폴더 링크를 생성합니다..."
ln -s /Applications "${TEMP_DIR}/Applications"

# DMG 파일 생성
echo "📦 DMG 파일을 생성합니다..."
hdiutil create -volname "${VOLUME_NAME}" -srcfolder "${TEMP_DIR}" -ov -format UDZO "${DMG_NAME}"

# 임시 디렉토리 정리
echo "🧹 임시 디렉토리를 정리합니다..."
rm -rf "${TEMP_DIR}"

echo "✅ DMG 파일 생성이 완료되었습니다!"
echo "📦 생성된 파일: ${DMG_NAME}"
echo "📁 앱 위치: dist/${APP_NAME}.app"
echo ""
echo "📋 사용 방법:"
echo "1. ${DMG_NAME} 파일을 더블클릭하여 마운트"
echo "2. '자소.app'을 'Applications' 폴더로 드래그 앤 드롭"
echo "3. 설치 완료!" 