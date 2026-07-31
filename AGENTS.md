# AGENTS.md

## 프로젝트

macOS 메뉴바 앱 "자소". 선택한 폴더를 감시하며 파일/폴더명 유니코드를 NFD → NFC로 정규화해 한글 자소분리를 막는다. Python 3.11 + rumps(메뉴바) + watchdog(파일감시), py2app으로 `.app` 빌드.

전체 로직은 `src/main.py` 한 파일(약 200줄)에 있다. 모듈 분리 계획 없음 — 새 기능도 여기에 넣는다.

## 구조

```
src/main.py           전부. 정규화 함수 + Watcher + Handler + JasoRumpsApp(메뉴바 UI)
assets/icon.icns      메뉴바/번들 아이콘
scripts/build.sh      py2app 빌드 → dist/자소.app
scripts/build_dmg.sh  앱 빌드 + hdiutil로 DMG 생성
setup.py              py2app 번들 설정 (plist, LSUIElement: True = Dock 아이콘 없음)
pyproject.toml        Poetry 의존성 (package-mode = false)
                      런타임: rumps, watchdog / dev: py2app, setuptools (빌드 전용)
```

`setup.py`·`pyproject.toml`·`poetry.lock`은 툴 관례상 루트 고정. 빌드 산출물(`build/`, `dist/`, `*.dmg`)도 루트에 생긴다.

## 명령어

```bash
poetry install                   # 최초 1회
poetry run python src/main.py    # 개발 실행 (메뉴바에 아이콘 등장)
./scripts/build.sh               # 앱 빌드
./scripts/build_dmg.sh           # 배포용 DMG
```

빌드 스크립트는 첫 줄에서 저장소 루트로 `cd`하므로 어디서 실행해도 된다.

```bash
poetry run python src/main.py --selfcheck                    # 자동실행 plist 왕복 검증 (개발)
PYTHONIOENCODING=utf-8 "dist/자소.app/Contents/MacOS/자소" --selfcheck   # 번들 경로 분기 검증
```

테스트 프레임워크 없음. 검증은 실제 실행 + 폴더에 NFD 이름 파일을 넣어 확인.

## main.py 흐름

1. `normalize_path(path)` — 이름만 NFC 정규화 후 `os.rename`. **길이 비교로 변경 필요 여부 판단** (NFD는 조합문자로 더 길다). 길이가 같으면 no-op.
2. `normalize_filenames_in_directory(dir)` — `os.walk(topdown=False)`로 전 경로 수집 후 **역순(깊은 것부터) 처리**. 상위 폴더 rename이 하위 경로를 무효화하는 문제를 피하기 위한 것이니 순서를 바꾸지 말 것.
3. `Handler.on_any_event` — created/modified/moved 이벤트마다 해당 경로를 정규화.
4. `Watcher.run` — `Observer` 시작 + `rumps.Timer`로 1초마다 `observer.join(1)`. rumps 이벤트 루프와 watchdog 스레드를 공존시키기 위한 장치.
5. 로그인 시 자동실행 — `~/Library/LaunchAgents/tech.proofer.jaso.plist`의 **존재 여부**가 곧 on/off. `launchctl load/unload`는 쓰지 않는다(로그인 시 실행만 필요).
6. 감시 폴더 기억 — `Application Support/자소/watched_directory`에 경로 한 줄. `rumps.App.open()`이 위치를 잡아주므로 별도 경로 계산 없음. **바이너리 + utf-8 명시** 필수(아래 ASCII 함정).
7. `@rumps.events.before_start` 훅(`_restore_state`)에서 체크 상태와 감시 폴더를 모두 복원한다 — rumps는 `run()` 시점에 메뉴를 만들기 때문에 `__init__`에서는 `self.menu[...]`가 아직 없다. 복원은 알림창 없이 조용히 한다(로그인 자동실행 때 팝업이 뜨면 안 되므로).

폴더 선택과 시작 시 복원은 `_start_watching()` 하나를 공유한다. 감시 시작 로직을 고칠 때는 여기만 고치면 된다.

## 번들 런타임의 함정 (실측)

py2app 번들 안에서 값들이 개발 실행과 다르다. 추측하지 말고 확인할 것:

- `sys.executable` = `<앱>.app/Contents/MacOS/python` — **앱 실행파일이 아니다.** 앱을 다시 띄우려면 `__file__`(`Contents/Resources/main.py`)에서 `../..`로 `.app` 경로를 되짚어 `/usr/bin/open <bundle>`을 쓴다 (`launch_arguments()`).
- `sys.frozen == 'macosx_app'`, `os.getcwd()` = `Contents/Resources`.
- **기본 인코딩이 ASCII다.** 한글이 든 텍스트를 기본 인코딩으로 쓰면 `UnicodeEncodeError`. 파일은 `'wb'` + `plistlib`(UTF-8 XML)로 쓰거나 `encoding='utf-8'`을 명시할 것. `print`는 모듈 최상단에서 stdout/stderr를 UTF-8로 `reconfigure` 해 두었으니 그냥 써도 된다 — **그 블록을 지우지 말 것.**
- 번들 디버깅은 `open`이 아니라 실행파일을 직접 돌려 stderr를 본다: `"dist/자소.app/Contents/MacOS/자소"`.

## 주의사항

- **AppKit import는 `if __name__ == "__main__":` 블록 안에서** 한다 (`src/main.py` 끝). 모듈 상단으로 올리면 py2app 번들에서 초기화 순서 문제가 난다. `NSOpenPanel` 등은 `_select_directory`에서 그 전역 이름을 참조한다.
- `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`를 rumps import 전에 설정한다 (`src/main.py:4`). 순서 유지.
- `ICON_PATH`는 두 실행 환경을 모두 커버한다: 번들에서는 cwd가 `Contents/Resources`라 `icon.icns`가 그대로 잡히고, 개발 실행에서는 `assets/icon.icns`로 폴백한다. 아이콘 위치를 옮기면 `setup.py`의 `iconfile`·`DATA_FILES`와 함께 고쳐야 한다.
- 메뉴 항목 제목이 곧 키다 (`self.menu["대상 폴더 선택"]`). 한글 문자열을 바꾸면 조회 코드도 같이 고쳐야 한다.
- 버전이 세 곳에 흩어져 있다: `pyproject.toml`(0.1.0), `setup.py`의 `version`(0.0.1)과 `CFBundleShortVersionString`(0.1.0), `build_dmg.sh`의 `VERSION`. 릴리스 시 전부 맞출 것.
- 파일명 조작 코드다. rename 실패는 `normalize_quietly()`가 삼켜 로그만 남긴다 — 한 경로의 실패가 전체 순회를 멈추지 않게 하는 의도이니 유지.
- `Handler.on_any_event`의 `try/except`도 유지. watchdog 감시 스레드로 예외가 새어나가면 스레드가 죽고 감시가 **조용히** 멈춘다(알림도 없다). 이 핸들러가 그 경계다.

### 알려진 문제: rename이 계속 실패하는 경로가 있으면 감시가 폭주한다

읽기 전용 하위 폴더처럼 rename이 **영구적으로** 실패하는 NFD 파일이 감시 트리에 있으면, 실패한 rename이 다시 이벤트를 유발해 초당 150여 회 순회가 반복된다(실측 CPU 12%, 로그 폭증). 정상 폴더에서는 유휴 CPU 0%로 재현되지 않는다.

원인은 "실패한 경로를 무한히 재시도한다"는 것. 실패한 경로를 기억해 건너뛰는 식의 가드가 필요하다. 미수정.

## 코드 스타일

- 주석·UI 문자열·커밋 메시지 모두 한국어.
- 타입 힌트는 가벼운 수준(`Observer | None`)으로만.
- 의존성 추가는 최소화. 현재 표준 라이브러리 + rumps + watchdog + py2app 계열이 전부다.
