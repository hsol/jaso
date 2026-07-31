from setuptools import setup

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
        'CFBundleShortVersionString': '0.1.0',
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
    version="0.0.1",
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
)
