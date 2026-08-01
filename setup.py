import tomllib
from pathlib import Path

from setuptools import setup

# 버전의 유일한 출처는 pyproject.toml. 여기서 읽어 앱 번들·배포 파일명이 항상 같은 값을 쓴다.
VERSION = tomllib.loads(
    (Path(__file__).parent / 'pyproject.toml').read_text(encoding='utf-8')
)['tool']['poetry']['version']

APP = ['src/main.py']
DATA_FILES = ['assets/icon.icns']  # 번들 Contents/Resources/icon.icns 로 복사됨 (메뉴바 아이콘용)
OPTIONS = {
    'iconfile': 'assets/icon.icns',
    'argv_emulation': False,
    'plist': {
        'LSUIElement': True,
        'CFBundleName': '자소',
        'CFBundleDisplayName': '자소',
        'CFBundleIdentifier': 'tech.proofer.jaso',
        'CFBundleVersion': '1',
        'CFBundleShortVersionString': VERSION,
        'NSHighResolutionCapable': True,
        # 실행 하한. 이걸 빼면 낮은 OS에서 macOS의 안내 대신 dyld 로드 실패로 그냥 죽는다.
        # 값의 근거: 릴리스는 CI에서만 만들고(release.yml), 거기 Python은 python.org의
        # macos11 universal2 빌드라 번들되는 dylib이 전부 minos 11.0이다(실측: 티켓 6ad582ef).
        # 이 숫자와 번들의 실제 minos가 어긋나면 build_dmg.sh가 빌드를 세운다 — 함께 고칠 것.
        'LSMinimumSystemVersion': '11.0',
    },
    'packages': ['rumps', 'watchdog', 'AppKit', 'Foundation', 'objc'],
    'includes': ['os', 'unicodedata', 'subprocess', 'imp'],
    'excludes': ['matplotlib', 'numpy', 'scipy'],
}

setup(
    app=APP,
    name="자소",
    description="OSX 자소분리 방지기(NFD->NFC)",
    version=VERSION,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
)
