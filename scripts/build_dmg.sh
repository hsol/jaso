#!/bin/bash

# 자소 앱 DMG 설치 파일 생성 스크립트

set -e  # 오류 발생 시 스크립트 중단
cd "$(dirname "$0")/.."  # 어디서 실행해도 저장소 루트에서 동작

echo "🚀 자소 앱 DMG 설치 파일 생성을 시작합니다..."

# 변수 설정
APP_NAME="자소"
# 버전의 유일한 출처는 pyproject.toml (setup.py도 같은 값을 읽는다)
VERSION=$(poetry run python -c 'import tomllib,pathlib;print(tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))["tool"]["poetry"]["version"])')
# 파일명만 ASCII. 볼륨명·앱 이름은 한글 그대로 — 브라우저·CI가 한글 파일명을 깨뜨린다
DMG_NAME="jaso-${VERSION}.dmg"
VOLUME_NAME="${APP_NAME}"

# 서명 identity는 접두 매칭으로 잡는다 — 해시를 박으면 CI의 임시 키체인에서 안 맞는다.
# 인증서가 없는 기계(로컬 기여자)에서는 경고만 남기고 미서명으로 계속 빌드한다.
# 릴리스에서 "secret 없으면 실패"시키는 건 워크플로 쪽 몫이다.
SIGN_ID="Developer ID Application"
if [ "$(security find-identity -v -p codesigning | grep -c "$SIGN_ID")" -eq 0 ]; then
    echo "⚠️  '${SIGN_ID}' 인증서가 없습니다 — 미서명으로 계속합니다(배포용으로는 쓸 수 없습니다)."
    SIGN_ID=""
fi

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

# 실행 하한 검증 — 스텁 하나만 보면 안 된다.
# py2app 스텁은 늘 11.0이지만 앱이 실제로 로드하는 건 Contents/Frameworks의 dylib이고,
# 그건 빌드에 쓴 Python이 링크한 것을 그대로 복사한 것이다. Homebrew Python으로 빌드하면
# libssl/libcrypto가 그 맥의 OS 버전으로 박힌다(실측: macOS 26 머신에서 minos 26.0).
# 그러면 Info.plist가 약속한 하한이 조용히 거짓이 되므로, 여기서 세운다.
echo "🔍 번들의 실제 실행 하한을 확인합니다..."
APP_DIR="dist/${APP_NAME}.app"
DECLARED=$(plutil -extract LSMinimumSystemVersion raw "${APP_DIR}/Contents/Info.plist")
MINOS_LIST=$(find "${APP_DIR}/Contents" -type f \
    \( -name '*.so' -o -name '*.dylib' -o -path '*/MacOS/*' \) | while read -r f; do
        V=$(otool -l "$f" 2>/dev/null | awk '/minos/ {print $2; exit}')
        [ -n "$V" ] && printf '%s %s\n' "$V" "$f"
    done | sort -V)
ACTUAL=$(printf '%s\n' "$MINOS_LIST" | tail -1 | awk '{print $1}')
if [ -z "$ACTUAL" ]; then
    echo "❌ 번들에서 Mach-O 바이너리를 하나도 못 읽었습니다 — 검사가 통째로 무력해진 상태라 세웁니다."
    exit 1
fi

if [ "$(printf '%s\n%s\n' "$DECLARED" "$ACTUAL" | sort -V | tail -1)" != "$DECLARED" ]; then
    echo "❌ 번들의 실제 하한(${ACTUAL})이 Info.plist의 LSMinimumSystemVersion(${DECLARED})보다 높습니다."
    echo "   이 DMG는 macOS ${DECLARED} 사용자에게서 dyld 로드 실패로 죽습니다. 원인 파일:"
    printf '%s\n' "$MINOS_LIST" | awk -v v="$ACTUAL" '$1 == v {print "     " $0}'
    echo "   릴리스 DMG는 CI(.github/workflows/release.yml)에서만 만드세요 — 그쪽 Python은"
    echo "   python.org의 macos11 빌드라 번들 전체가 11.0으로 고정입니다."
    echo "   하한을 정말 올리려면 setup.py의 LSMinimumSystemVersion과 README의 숫자를 같이 고치세요."
    exit 1
fi
echo "✅ 실제 하한 ${ACTUAL} ≤ 선언한 하한 ${DECLARED} (검사한 바이너리 $(printf '%s\n' "$MINOS_LIST" | wc -l | tr -d ' ')개)"

# 실행파일 이름을 ASCII로 바꾼다. 취향이 아니라 codesign 때문이다.
# CFBundleExecutable이 한글이면 codesign이 그 파일을 "번들의 메인 실행파일"로 알아보지 못하고
# Contents/MacOS/ 안의 nested code로 취급해 CodeResources에 cdhash를 봉인해버린다. 그런데 메인
# 실행파일은 봉인 뒤에 서명이 박히므로 cdhash가 곧바로 어긋나고, 검증이 이렇게 실패한다:
#   codesign -vvv --strict dist/자소.app  → "a sealed resource is missing or invalid"
# (ASCII 이름으로 바꾸면 같은 번들이 "valid on disk"로 통과한다. 실측으로 확인했다.)
# 번들 이름(자소.app)·CFBundleName·CFBundleDisplayName은 그대로라 Finder에는 여전히 '자소'로 보인다.
echo "🔤 실행파일 이름을 ASCII로 바꿉니다 (codesign 요구사항)..."
mv "dist/${APP_NAME}.app/Contents/MacOS/${APP_NAME}" "dist/${APP_NAME}.app/Contents/MacOS/jaso"
plutil -replace CFBundleExecutable -string jaso "dist/${APP_NAME}.app/Contents/Info.plist"

# 앱 서명 — hdiutil 앞에서. DMG 안에 들어가는 앱이 이미 서명돼 있어야 한다.
# 안쪽(.so/.dylib/보조 실행파일)부터 서명하고 마지막에 .app 을 서명한다.
# codesign --deep 은 애플이 권장하지 않고 공증에서 자주 반려되므로 쓰지 않는다.
if [ -n "$SIGN_ID" ]; then
    echo "🔏 번들 내부 바이너리를 서명합니다..."
    find "dist/${APP_NAME}.app/Contents" \
        \( -name '*.so' -o -name '*.dylib' -o -path '*/MacOS/python' \) \
        -exec codesign --force --options runtime --timestamp -s "$SIGN_ID" {} +

    # assets/jaso.entitlements 는 disable-library-validation 하나만 담는다. 실측 결과다
    # (ad-hoc + --options runtime 으로 서명해 앱을 띄우고 NFD 파일을 떨궈 정규화까지 확인):
    #   없음 / allow-unsigned-executable-memory 만 → libpython3.11.dylib dlopen 실패
    #     ("mapping process and mapped file (non-platform) have different Team IDs"), 정규화 안 됨
    #   disable-library-validation 만              → 정상 기동 + 정규화 성공. 이걸 남긴다
    # py2app 번들은 Contents/Frameworks의 libpython·libssl 을 실행 중에 dlopen 하므로 이게 필요하다.
    # 주의: entitlements plist에 XML 주석을 넣으면 codesign이 파싱에 실패한다("AMFIUnserializeXML:
    # syntax error"). 그래서 설명이 파일이 아니라 여기 있다.
    echo "🔏 앱을 서명합니다..."
    codesign --force --options runtime --timestamp \
        --entitlements assets/jaso.entitlements -s "$SIGN_ID" "dist/${APP_NAME}.app"

    codesign -vvv --strict "dist/${APP_NAME}.app"
else
    # 미서명 경로에서도 봉인은 맞춰 둔다. 위에서 Info.plist를 고쳤기 때문에 py2app이 붙여 둔
    # ad-hoc 서명이 깨진 상태다(codesign --verify → "invalid Info.plist"). 지금은 그래도 실행되지만
    # 깨진 서명을 남길 이유가 없다. ad-hoc으로 다시 봉인한다.
    codesign --force -s - "dist/${APP_NAME}.app"
    codesign --verify "dist/${APP_NAME}.app"
fi

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

# DMG 서명 — hdiutil 뒤에서. DMG는 실행 코드가 아니라 --options runtime / entitlements 를 붙이지 않는다.
if [ -n "$SIGN_ID" ]; then
    echo "🔏 DMG를 서명합니다..."
    codesign --force --timestamp -s "$SIGN_ID" "${DMG_NAME}"
    codesign -vvv "${DMG_NAME}"
fi

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