from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'iconfile': 'icon.icns',
    'argv_emulation': True,
    'plist': {
        'LSUIElement': True,
    },
    'packages': ['rumps'],
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
