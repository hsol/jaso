from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'iconfile': 'icon.icns',
    'argv_emulation': False,
    'plist': {
        'LSUIElement': True,
        'CFBundleName': '자소',
        'CFBundleDisplayName': '자소',
        'CFBundleIdentifier': 'com.jaso.app',
        'CFBundleVersion': '0.0.1',
        'CFBundleShortVersionString': '0.0.1',
        'NSHighResolutionCapable': True,
    },
    'packages': ['rumps', 'watchdog'],
    'includes': ['os', 'unicodedata', 'subprocess', 'imp'],
    'excludes': ['tkinter', 'matplotlib', 'numpy', 'scipy'],
}

setup(
    app=APP,
    name="자소",
    description="OSX 자소분리 방지기(NFD->NFC)",
    version="0.0.1",
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
