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
