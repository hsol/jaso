import json
import os
import plistlib
import ssl
import sys
import threading
import time
import traceback
import unicodedata
import urllib.request
import uuid
import webbrowser
# macOS 경고 메시지 숨기기
os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

# py2app 번들의 stdout/stderr 기본 인코딩은 ASCII다. 이 앱의 로그와 경로는 대부분 한글이라
# 그대로 두면 print 한 줄이 UnicodeEncodeError를 던진다. 여기서 한 번 UTF-8로 맞춰둔다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors='replace')

import rumps
from AppKit import NSApplication, NSModalPanelWindowLevel, NSOKButton, NSOpenPanel
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

APP_NAME = '자소'

# 번들에서는 cwd가 Contents/Resources, 개발 실행에서는 저장소 assets/
ICON_PATH = ('icon.icns' if os.path.exists('icon.icns')
             else os.path.join(os.path.dirname(__file__), '..', 'assets', 'icon.icns'))


def bundle_path():
    # 번들 실행일 때만 .app 경로를 준다. __file__ 이 <앱>.app/Contents/Resources/main.py 라는 점을 되짚는다.
    # 개발 실행에서는 .app 자체가 없으므로 None.
    if getattr(sys, 'frozen', None) != 'macosx_app':
        return None
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def support_path(name):
    # Application Support/자소/<name>. rumps가 폴더까지 만들어준다.
    return os.path.join(rumps.application_support(APP_NAME), name)


def start_logging():
    # 번들에서는 stdout/stderr가 갈 데가 없다 — print도 traceback도 그대로 사라진다.
    # (0e6628e4: 사용자가 오류를 만났는데 남은 증거가 알림창 스크린샷 한 장뿐이었다.)
    # 이 앱의 except는 전부 print/traceback을 쓰므로 문 하나만 파일로 돌리면 전부 남는다.
    # ponytail: 회전 없음 — 1MB 넘으면 통째로 버린다. 쌓여봐야 이벤트 처리 실패 로그다
    path = support_path(f'{APP_NAME}.log')
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        os.remove(path)
    if bundle_path() is not None:  # 개발 실행은 터미널로 보는 게 낫다
        sys.stdout = sys.stderr = open(path, 'a', encoding='utf-8', buffering=1)
    print(f"\n--- {APP_NAME} 시작 {time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} ---")
    return path


def activate():
    # 이 앱은 Dock 없는 accessory(LSUIElement)라 메뉴 항목을 눌러도 활성 앱이 되지 않는다.
    # 그대로 모달을 띄우면 패널이 키 포커스를 못 받고(번들) 아예 화면에 올라오지도 않는데(개발 실행),
    # runModal()은 계속 블록된다. 모달 세션이 사는 동안 AppKit이 메뉴 항목을 전부 비활성화하므로
    # 사용자는 종료조차 못 누른다 — 강제 종료 말고는 길이 없다(81e3dfb8).
    # 그래서 모달을 띄우기 전에 반드시 앱을 앞으로 올린다.
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


def alert(*args, **kwargs):
    # rumps.alert도 NSAlert 모달이라 같은 함정을 밟는다. 이 앱의 알림은 전부 이 문을 지난다.
    activate()
    # 번들이 통째로 사라지면 icon.icns도 같이 사라진다. rumps.alert는 아이콘 파일이 없으면
    # FileNotFoundError를 던지므로, 하필 그 상황을 알리려던 알림이 조용히 죽는다(실측).
    # 아이콘은 있으면 좋은 것이지 알림이 뜨는 조건이 아니다.
    if not os.path.exists(kwargs.get('icon_path') or ''):
        kwargs.pop('icon_path', None)
    return rumps.alert(*args, **kwargs)


LOG_PATH = start_logging()


# ---- 사용 통계 (GA4 Measurement Protocol) ----
# 브라우저가 없는 앱이라 gtag.js 대신 서버용 엔드포인트로 직접 쏜다.
# 나가는 값은 "무엇을 몇 번 했는가"뿐이다 — 폴더 경로·파일명은 절대 싣지 않는다(_selfcheck가 지킨다).
# api_secret은 이 값이 노출돼도 읽기 권한은 없고 쓰기만 되는 키다. 클라이언트 앱이라 어차피 번들에 들어간다.
GA_URL = ('https://www.google-analytics.com/{path}'
          '?measurement_id=G-JXPBH4TWPD&api_secret=J41bqcEITaaGz7KPJL863Q')
ANALYTICS_OFF_FILE = 'analytics_off'  # 이 파일이 있으면 한 건도 보내지 않는다
_session_id = str(int(time.time()))
_client_id = None


def analytics_enabled(path: str = None) -> bool:
    return not os.path.exists(path or support_path(ANALYTICS_OFF_FILE))


def set_analytics(enabled: bool, path: str = None):
    # 자동실행과 같은 방식 — 파일 하나의 존재 여부가 곧 on/off.
    path = path or support_path(ANALYTICS_OFF_FILE)
    if enabled:
        if os.path.exists(path):
            os.remove(path)
    else:
        open(path, 'w').close()


def app_version():
    # 버전별 사용을 보려면 번들의 Info.plist가 유일한 출처다. 개발 실행은 'dev'.
    bundle = bundle_path()
    if bundle is None:
        return 'dev'
    try:
        with open(os.path.join(bundle, 'Contents', 'Info.plist'), 'rb') as f:
            return plistlib.load(f).get('CFBundleShortVersionString', '?')
    except Exception:
        return '?'


def client_id():
    # 설치마다 고정된 임의 번호. 사람을 식별하지 않는다 — GA가 재방문을 셀 수 있을 정도만이다.
    # 저장에 실패하면 다음 실행에 새 번호가 생긴다(통계가 조금 틀어질 뿐, 앱은 멀쩡하다).
    global _client_id
    if _client_id is None:
        try:
            with open(support_path('client_id')) as f:
                _client_id = f.read().strip()
        except OSError:
            _client_id = ''
        if not _client_id:
            _client_id = f'{uuid.uuid4().int % 10 ** 10}.{int(time.time())}'
            try:
                with open(support_path('client_id'), 'w') as f:
                    f.write(_client_id)
            except OSError as e:
                print('client_id 저장 실패:', e)
    return _client_id


def ga_payload(name, params):
    # session_id와 engagement_time_msec이 없으면 GA4는 실시간 화면 말고 어디에도 이 이벤트를 세지 않는다.
    return {'client_id': client_id(),
            'events': [{'name': name,
                        'params': {'session_id': _session_id,
                                   'engagement_time_msec': 1,
                                   'app_version': app_version(),
                                   **params}}]}


def _post_event(name, params, debug=False):
    request = urllib.request.Request(
        GA_URL.format(path='debug/mp/collect' if debug else 'mp/collect'),
        json.dumps(ga_payload(name, params)).encode('utf-8'),
        {'Content-Type': 'application/json'})
    # py2app 번들의 ssl은 python.org 빌드의 CA 경로를 물려받는데 사용자 맥에는 그 경로가 없다.
    # macOS가 늘 갖고 있는 루트 번들을 직접 쥐여준다(없으면 기본값).
    cafile = '/etc/ssl/cert.pem'
    context = ssl.create_default_context(cafile=cafile if os.path.exists(cafile) else None)
    try:
        with urllib.request.urlopen(request, timeout=5, context=context) as response:
            return response.status, response.read().decode('utf-8', 'replace')
    except Exception as e:
        print('사용 통계 전송 실패:', e)  # 통계는 실패해도 앱이 하는 일과 무관하다
        return None, str(e)


def track(name, **params):
    # 네트워크가 앱을 멈춰 세우지 않도록 데몬 스레드에서 보낸다. 실패는 로그 한 줄로 끝난다.
    # ponytail: 큐·재시도·배치 없음 — 잃어도 되는 데이터고, 이벤트가 사용자 조작당 한 건이다
    if not analytics_enabled():
        return
    threading.Thread(target=_post_event, args=(name, params), daemon=True).start()


def report_error(e, icon_path=None, what='오류'):
    # 예외는 사용자에게 한 줄, 로그에 전부. 번들에서 사후에 읽을 수 있는 유일한 자국이다.
    traceback.print_exc()
    # 통계에는 예외 종류만 — 메시지에는 폴더 경로가 섞여 나갈 수 있다.
    track('error', what=what, kind=type(e).__name__)
    alert(f'{what}: {e}\n\n자세한 기록:\n{LOG_PATH}', icon_path=icon_path)


AUTOSTART_LABEL = 'tech.proofer.jaso'
AUTOSTART_PLIST = os.path.expanduser(f'~/Library/LaunchAgents/{AUTOSTART_LABEL}.plist')

# Application Support/자소/ 안에 저장되는 감시 폴더 목록 파일 (rumps.App.open 이 위치를 잡아준다)
WATCHED_DIRECTORY_FILE = 'watched_directory'

# 감시 폴더 목록 위에 세우는 비활성 헤더. 제목이 곧 rumps 메뉴 키라서 개수를 넣지 않는다
# (넣으면 폴더가 늘 때마다 키가 바뀐다). 바로 아래에 줄이 그만큼 보이므로 숫자는 중복이기도 하다.
WATCH_HEADER = '감시 중인 폴더'


def parse_watched_directories(text: str) -> list[str]:
    # 저장 형식은 "한 줄에 폴더 하나". 예전의 한 줄짜리 파일이 그대로 1개 목록으로 읽히므로
    # 마이그레이션 코드가 필요 없다. 반대 방향은 '\n'.join(dirs) 한 줄이라 함수로 만들지 않는다.
    # 지워진 폴더와 중복은 여기서 조용히 빠진다.
    directories: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and line not in directories and os.path.isdir(line):
            directories.append(line)
    return directories


def launch_arguments():
    # 번들에서 sys.executable 은 Contents/MacOS/python (앱 실행파일이 아님) 이므로 쓸 수 없다.
    bundle = bundle_path()
    if bundle is not None:
        return ['/usr/bin/open', bundle]
    return [sys.executable, os.path.abspath(__file__)]


def panel_failure_message(bundle):
    # openPanel()이 nil일 때 사용자에게 할 말. 프로세스 안에서 되살릴 방법이 없으므로
    # "무엇을 하면 되는지"만 말한다. bundle이 None이면 개발 실행(또는 판단 근거 없음).
    if bundle is not None and not os.path.exists(bundle):
        why = (f'실행 중인 {APP_NAME} 앱 파일이 사라졌습니다.\n'
               '(앱을 옮기거나 지우거나 새 버전으로 덮어썼을 때 생깁니다.)\n\n'
               f'{APP_NAME}를 종료하고 앱을 다시 실행해 주세요.')
    else:
        why = f'{APP_NAME}를 종료한 뒤 다시 실행해 주세요.'
    return f'폴더 선택창을 열 수 없습니다.\n\n{why}\n\n자세한 기록:\n{LOG_PATH}'


def autostart_enabled(plist_path: str = AUTOSTART_PLIST) -> bool:
    return os.path.exists(plist_path)


def set_autostart(enabled: bool, plist_path: str = AUTOSTART_PLIST):
    # launchd가 로그인 시 ~/Library/LaunchAgents를 읽으므로 plist 존재 여부만 관리하면 된다.
    # ponytail: launchctl load/unload 생략 — "로그인 시 실행"만 필요하고 즉시 기동은 필요 없음
    if not enabled:
        if os.path.exists(plist_path):
            os.remove(plist_path)
        return

    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    with open(plist_path, 'wb') as f:
        plistlib.dump({
            'Label': AUTOSTART_LABEL,
            'ProgramArguments': launch_arguments(),
            'RunAtLoad': True,
        }, f)


def normalize_path(path: str):
    # 주어진 파일 경로의 이름을 NFC 유니코드 형식으로 정규화하고 파일명을 변경합니다.
    # 길이 비교가 아니라 문자열 비교를 쓴다 — 길이가 같은데 코드포인트가 다른 정규화도 있다.
    directory, name = os.path.split(path)
    normalized_name = unicodedata.normalize('NFC', name)
    if name == normalized_name:
        return

    normalized_path = os.path.join(directory, normalized_name)
    os.rename(path, normalized_path)


def resolve_stored_path(path: str):
    # FSEvents(watchdog)가 넘겨주는 경로의 이름은 항상 NFD다. 디스크에 이미 NFC로 저장돼
    # 있어도 NFD 문자열이 오므로, 그 문자열만 믿으면 같은 파일을 끝없이 rename 하게 된다.
    # (실측: 초당 230여 건의 no-op rename → 이벤트 → rename 무한 루프)
    # 그래서 부모 폴더를 훑어 실제로 저장된 이름을 찾아 돌려준다.
    directory, name = os.path.split(path)
    wanted = unicodedata.normalize('NFC', name)
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if unicodedata.normalize('NFC', entry.name) == wanted:
                    return os.path.join(directory, entry.name)
    except OSError:
        return None
    return None  # 이미 지워졌거나 옮겨진 경로


# rename이 영구적으로 실패하는 경로(읽기 전용 폴더 안의 NFD 파일 등)를 계속 재시도하면
# 실패한 rename이 다시 이벤트를 유발해 순회가 무한 반복된다. 한 번 실패한 경로는 건너뛴다.
# 권한을 고친 뒤에는 "한번에 변환"이 이 목록을 비우므로 다시 시도할 수 있다.
# ponytail: 락 없음 — 멤버십 검사/추가/clear 뿐이라 GIL 아래에서 충분하다
_failed_paths: set[str] = set()


def normalize_quietly(path_type: str, path: str) -> bool:
    # 한 경로의 실패가 나머지 순회를 멈추지 않도록, 오류는 로그만 남기고 삼킨다.
    if path in _failed_paths:
        return False
    try:
        normalize_path(path)
        return True
    except Exception as e:
        _failed_paths.add(path)
        print(f"{path_type} 처리 중 오류 발생(이후 건너뜀): {path}, 오류: {e}")
        traceback.print_exc()
        return False


def normalize_filenames_in_directory(directory):
    # 주어진 폴더와 그 하위 폴더에 있는 모든 파일의 이름을 NFC로 정규화합니다.
    processed_count = 0

    # 모든 경로를 먼저 수집하여 상위 폴더 변경의 영향을 받지 않도록 함
    all_paths = []

    # 일단 선택된 폴더부터 정규화 (실패해도 하위 순회는 계속한다)
    normalize_quietly('dir', directory)

    # 깊이 우선으로 모든 경로를 수집 (가장 깊은 것부터 처리)
    for root, dirs, files in os.walk(directory, topdown=False):
        # 파일들을 먼저 수집
        for filename in files:
            file_path = os.path.join(root, filename)
            all_paths.append(('file', file_path))
        
        # 폴더들을 수집
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            all_paths.append(('dir', dir_path))
    
    # 수집된 경로들을 역순으로 처리 (가장 깊은 것부터)
    for path_type, path in reversed(all_paths):
        if normalize_quietly(path_type, str(path)):
            processed_count += 1

    return processed_count


class Watcher:
    # 파일 시스템의 변경을 감시하는 watchdog 클래스입니다.
    # Observer 하나에 여러 폴더를 걸 수 있으므로 폴더가 늘어도 감시 스레드는 하나뿐이다.
    observer: Observer | None = None

    def __init__(self):
        # 폴더 경로 -> watchdog 핸들. 폴더 하나만 떼어내려면 schedule()이 준 핸들이 필요하다.
        self.watches: dict[str, object] = {}

    def watch(self, directory_to_watch):
        # 이미 도는 Observer에 경로를 하나 더 건다 — 기존 폴더의 감시는 끊기지 않는다.
        # Observer는 데몬 스레드라 스스로 돈다 — 메인 스레드가 join으로 붙들 이유가 없다.
        # (붙들면 rumps.Timer가 메인 런루프에서 매초 1초씩 앱을 멈춰 세운다)
        if self.observer is None:
            self.observer = Observer()
            self.observer.start()

        self.watches[directory_to_watch] = self.observer.schedule(Handler(), directory_to_watch, recursive=True)

    def unwatch(self, directory_to_watch):
        # 이 경로만 뗀다 — 같은 Observer에 걸린 나머지 폴더의 감시는 그대로다.
        watch = self.watches.pop(directory_to_watch, None)
        if watch is not None and self.observer is not None:
            self.observer.unschedule(watch)
        if not self.watches:
            self.stop()  # 마지막 폴더가 빠지면 스레드도 접는다. watch()가 다시 살린다

    def stop(self):
        # 걸어둔 경로가 몇 개든 Observer가 하나라 한 번의 stop으로 감시 스레드가 전부 정지한다.
        try:
            if self.observer is not None:  # 이미 멈춘 뒤 또 불러도 정상 (종료 경로가 무조건 부른다)
                self.observer.stop()
                self.observer.join()
        except Exception:
            traceback.print_exc()
        finally:
            self.observer = None
            self.watches.clear()


class Handler(FileSystemEventHandler):
    # 파일 시스템 이벤트에 반응하여 적절한 조치를 취하는 이벤트 핸들러 클래스입니다.
    @staticmethod
    def on_any_event(event):
        # watchdog 감시 스레드로 예외가 빠져나가면 스레드가 죽어 감시가 조용히 멈춘다.
        # 이벤트 처리 중 무슨 일이 나든 여기서 막는다.
        try:
            if event.event_type == 'moved':
                path = event.dest_path
            elif event.event_type in ('created', 'modified'):
                path = event.src_path
            else:
                return

            # 이벤트가 준 NFD 경로를 실제 저장된 이름으로 되돌린 뒤에 처리한다.
            path = resolve_stored_path(path)
            if path is not None:
                normalize_filenames_in_directory(path)
        except Exception as e:
            print(f"이벤트 처리 중 오류 발생: {event.event_type} {event.src_path}, 오류: {e}")
            traceback.print_exc()


class JasoRumpsApp(rumps.App):
    # macOS 메뉴바 앱을 위한 클래스입니다.

    def __init__(self, *args, **kwargs):
        super().__init__(name="자소", icon=ICON_PATH, quit_button=None)

        self.watcher = Watcher()
        self.icon_path = ICON_PATH
        self.watched_directories: list[str] = []
        self.convert_menu_item = None

    # 감시 폴더 기억: rumps가 만들어주는 Application Support 폴더에 한 줄에 하나씩 저장한다.
    # 번들의 기본 인코딩이 ASCII라 한글 경로가 깨지므로 반드시 바이너리 + utf-8 로 다룬다.
    def _load_watched_directories(self) -> list[str]:
        try:
            with self.open(WATCHED_DIRECTORY_FILE, 'rb') as f:
                return parse_watched_directories(f.read().decode('utf-8'))
        except (OSError, UnicodeDecodeError):
            return []

    def _save_watched_directories(self):
        try:
            with self.open(WATCHED_DIRECTORY_FILE, 'wb') as f:
                f.write('\n'.join(self.watched_directories).encode('utf-8'))
        except OSError as e:
            print('감시 폴더 저장 실패:', e)

    def _update_add_title(self):
        self.menu["대상 폴더 선택"].title = "폴더 추가" if self.watched_directories else "대상 폴더 선택"

    def _start_watching(self, directory_path):
        # 폴더 선택과 시작 시 자동 복원이 공유하는 경로. 목록에 하나를 더한다.
        _failed_paths.clear()  # 새 감시 시작이면 지난 실패 기록은 무효
        self.watched_directories.append(directory_path)

        # 감시 목록은 명령 위에 둔다 — 메뉴를 여는 이유가 대개 "지금 뭘 감시하나"라서 답이 첫 줄에
        # 있어야 한다. 헤더(콜백이 없어 비활성)와 구분선이 목록의 시작과 끝을 표시한다.
        if WATCH_HEADER not in self.menu:
            self.menu.insert_before("대상 폴더 선택", rumps.MenuItem(WATCH_HEADER))
            self.menu.insert_before("대상 폴더 선택", rumps.separator)

        # "한번에 변환"을 먼저 세우고 폴더 항목을 그 앞에 끼운다. 기준선이 늘 아래에 있으니
        # 폴더가 몇 개 늘고 줄어도 자동실행·도움말·종료는 순서 그대로 남는다.
        if self.convert_menu_item is None:
            self.convert_menu_item = rumps.MenuItem("한번에 변환", callback=self._convert_once)
            self.menu.insert_before("로그인 시 자동실행", self.convert_menu_item)

        # 메뉴 키는 전체 경로다 — 이름이 같은 폴더 둘을 걸어도 서로를 덮어쓰지 않는다.
        # 넣을 때의 title이 그대로 키가 되므로(rumps), 끼운 뒤에 보이는 이름만 폴더명으로 바꾼다.
        item = rumps.MenuItem(directory_path)
        item.add(rumps.MenuItem(directory_path))  # 서브메뉴 머리글: 콜백이 없어 비활성 = 전체 경로 표시용
        item.add(rumps.MenuItem("감시 해제", callback=lambda _, p=directory_path: self._stop_watching(p)))
        # 직전 폴더 뒤에 꽂아 걸어둔 순서를 유지한다. 첫 폴더는 헤더 바로 뒤.
        anchor = self.watched_directories[-2] if len(self.watched_directories) > 1 else WATCH_HEADER
        self.menu.insert_after(anchor, item)
        item.title = os.path.basename(directory_path) or directory_path  # '/'처럼 basename이 빈 경로

        self._update_add_title()
        self.watcher.watch(directory_path)

    def _stop_watching(self, directory_path):
        # "감시 해제" 콜백. 메뉴 키가 전체 경로라 이름이 같은 다른 폴더는 건드리지 않는다.
        if directory_path not in self.watched_directories:
            return
        self.watched_directories.remove(directory_path)
        self.watcher.unwatch(directory_path)
        del self.menu[directory_path]
        track('folder_remove', watched_count=len(self.watched_directories))

        if not self.watched_directories:
            # 폴더가 없으면 목록도 변환할 것도 없다 — 초기 상태로 되돌린다.
            # 구분선 키는 rumps가 붙이는 카운터('SeparatorMenuItem_1')고 지워도 줄지 않는다.
            # 다시 걸면 _2가 되므로 상수로 박지 말고 그때그때 목록에서 찾는다.
            del self.menu[WATCH_HEADER]
            del self.menu[next(k for k in self.menu if k.startswith('SeparatorMenuItem'))]
            del self.menu["한번에 변환"]
            self.convert_menu_item = None

        self._update_add_title()
        self._save_watched_directories()

    @rumps.clicked("대상 폴더 선택")
    def _select_directory(self, _):
        try:
            # 네이티브 폴더 선택 다이얼로그
            panel = NSOpenPanel.openPanel()
            if panel is None:
                # AppKit은 이 패널을 별도 XPC 서비스(openAndSavePanelService)에 그린다. 그 서비스가
                # 뜰 때 SecCodeCopyGuestWithAttributes로 호출한 앱의 서명을 확인하는데, 실행 중에
                # 앱 번들이 디스크에서 사라졌으면 확인이 실패해 서비스가 즉시 죽고 nil이 돌아온다
                # (0e6628e4 실측: ViewBridge FAULT ... error 100002 → "Connection interrupted").
                # 프로세스 안에서 되돌릴 방법이 없다 — 사용자에게 나갈 길을 알려주고 끝낸다.
                bundle = bundle_path()
                print(f'openPanel()이 nil을 반환했다. bundle={bundle} '
                      f'exists={bundle is not None and os.path.exists(bundle)}')
                alert(panel_failure_message(bundle), icon_path=self.icon_path)
                return
            panel.setCanChooseFiles_(False)
            panel.setCanChooseDirectories_(True)
            panel.setAllowsMultipleSelection_(False)
            panel.setTitle_("폴더 선택")
            panel.setMessage_("한글 자소분리를 방지할 폴더를 선택해주세요.")
            
            # 다이얼로그를 최상위로 설정
            panel.setLevel_(NSModalPanelWindowLevel)

            activate()
            result = panel.runModal()
            
            if result == NSOKButton:
                urls = panel.URLs()
                if urls and len(urls) > 0:
                    directory_path = urls[0].path()
                else:
                    directory_path = ""
            else:
                directory_path = ""
            
            if directory_path:
                if not os.path.isdir(directory_path):
                    alert("유효하지 않은 폴더입니다.", icon_path=self.icon_path)
                elif os.path.normpath(directory_path) in map(os.path.normpath, self.watched_directories):
                    alert("이미 감시 중인 폴더입니다.", icon_path=self.icon_path)
                else:
                    self._start_watching(directory_path)
                    self._save_watched_directories()
                    track('folder_add', watched_count=len(self.watched_directories))
                    alert(f"폴더가 추가되었습니다. 이제 {len(self.watched_directories)}곳에서 자동으로 한글의 자소분리가 방지됩니다.", icon_path=self.icon_path)
            else:
                alert("폴더를 선택하지 않았습니다.", icon_path=self.icon_path)
        except Exception as e:
            report_error(e, self.icon_path)

    def _convert_once(self, _):
        try:
            if not self.watched_directories:
                alert("먼저 대상 폴더를 선택해주세요.", icon_path=self.icon_path)
                return

            # 수동 실행은 재시도 기회다 — 권한을 고쳤을 수 있으니 실패 기록을 비우고 다시 훑는다
            _failed_paths.clear()

            # 등록된 모든 폴더의 파일과 폴더명을 한번에 변환 (폴더별 건수를 알림에 그대로 보여준다)
            lines = []
            processed = 0
            for directory in self.watched_directories:
                folder_name = os.path.basename(directory)
                if not os.path.isdir(directory):
                    lines.append(f"{folder_name}: 폴더를 찾을 수 없음")
                    continue
                count = normalize_filenames_in_directory(directory)
                processed += count
                lines.append(f"{folder_name}: {count}개")

            track('convert_once', watched_count=len(self.watched_directories),
                  processed=processed, skipped=len(_failed_paths))

            failed_note = f"\n건너뛴 항목: {len(_failed_paths)}개 (권한 등으로 이름 변경 실패)" if _failed_paths else ""
            alert("변환 완료!\n\n" + "\n".join(lines) + f"{failed_note}\n\n모든 파일과 폴더명이 NFD에서 NFC로 변환되었습니다.", icon_path=self.icon_path)
        except Exception as e:
            report_error(e, self.icon_path)

    @rumps.events.before_start
    def _restore_state(self):
        # 메뉴는 run() 시점에 만들어지므로 __init__ 이 아니라 여기서 상태를 맞춘다.
        self.menu["로그인 시 자동실행"].state = autostart_enabled()
        self.menu["사용 통계 보내기"].state = analytics_enabled()

        # 시작 시 복원은 조용히 — 로그인 자동실행 때 알림창이 뜨면 곤란하다.
        for directory in self._load_watched_directories():
            self._start_watching(directory)

        track('app_start', watched_count=len(self.watched_directories),
              autostart=autostart_enabled())

    @rumps.clicked("로그인 시 자동실행")
    def _toggle_autostart(self, sender):
        try:
            sender.state = 0 if sender.state else 1
            set_autostart(bool(sender.state))
            track('autostart', enabled=bool(sender.state))
        except Exception as e:
            sender.state = autostart_enabled()
            report_error(e, self.icon_path, '자동실행 설정 실패')

    @rumps.clicked("사용 통계 보내기")
    def _toggle_analytics(self, sender):
        try:
            sender.state = 0 if sender.state else 1
            set_analytics(bool(sender.state))
            track('analytics_on')  # 끄는 쪽은 보내지 않는다 — 껐는데 한 건 나가면 그게 배신이다
        except Exception as e:
            sender.state = analytics_enabled()
            report_error(e, self.icon_path, '사용 통계 설정 실패')

    @rumps.clicked("도움말", "개발자 정보")
    def _developer_info(self, _):
        track('help')
        if not alert("개발자 정보", "임한솔\nmolmoty@gmail.com\nhttps://hsol.info",
                           ok="확인", cancel="홈페이지 열기"):
            webbrowser.open("https://hsol.info")

    @rumps.clicked("종료")
    def _quit(self, _):
        self.watcher.stop()
        self.watched_directories = []
        rumps.quit_application()


def _selfcheck():
    # 자동실행 plist 쓰기/읽기/삭제 왕복 검증: poetry run python src/main.py --selfcheck
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        plist = os.path.join(tmp, 'LaunchAgents', f'{AUTOSTART_LABEL}.plist')
        assert not autostart_enabled(plist)

        set_autostart(True, plist)
        assert autostart_enabled(plist)
        with open(plist, 'rb') as f:
            data = plistlib.load(f)
        assert data['Label'] == AUTOSTART_LABEL
        assert data['RunAtLoad'] is True
        for arg in data['ProgramArguments']:
            assert os.path.exists(arg), data['ProgramArguments']

        set_autostart(False, plist)
        assert not autostart_enabled(plist)
        set_autostart(False, plist)  # 두 번 꺼도 예외 없음

    # 감시 폴더 목록: 저장 문자열 ↔ 목록 왕복 검증
    with tempfile.TemporaryDirectory() as tmp:
        a, b = os.path.join(tmp, '가나'), os.path.join(tmp, 'b')
        os.makedirs(a)
        os.makedirs(b)
        missing = os.path.join(tmp, '없는폴더')

        assert parse_watched_directories(a) == [a], '한 줄짜리 옛 파일'
        assert parse_watched_directories(f'{a}\n{b}') == [a, b], '여러 줄'
        assert parse_watched_directories(f'\n{a}\n\n  \n{b}\n') == [a, b], '빈 줄 무시'
        assert parse_watched_directories(f'{a}\n{missing}\n{b}') == [a, b], '없는 경로 제외'
        assert parse_watched_directories(f'{a}\n{a}') == [a], '중복 제거'
        assert parse_watched_directories('') == [], '빈 파일'
        assert parse_watched_directories('\n'.join([a, b])) == [a, b], '왕복'

    # openPanel()이 nil일 때 사용자에게 나가는 문구: 원인별로 갈리고, 파이썬 예외 문구가 새지 않는다
    with tempfile.TemporaryDirectory() as tmp:
        gone = panel_failure_message(os.path.join(tmp, '없는앱.app'))
        assert '사라졌습니다' in gone and '다시 실행' in gone, gone
        here = panel_failure_message(tmp)  # 번들이 멀쩡한데 nil이면 원인을 단정하지 않는다
        assert '사라졌습니다' not in here and '다시 실행' in here, here
        for message in (gone, here, panel_failure_message(None)):
            assert 'NoneType' not in message and LOG_PATH in message, message

    # 아이콘 파일이 없어도 알림은 떠야 한다. 번들이 사라진 상황에서 실제로 이것 때문에
    # "폴더 선택창을 열 수 없습니다" 알림이 통째로 죽었다(FileNotFoundError: icon.icns).
    passed, real_alert = {}, rumps.alert
    rumps.alert = lambda *a, **k: passed.update(k)
    try:
        alert('아이콘 없음', icon_path='/없는/경로/icon.icns')
        assert 'icon_path' not in passed, passed
        alert('아이콘 있음', icon_path=ICON_PATH)
        assert passed.get('icon_path') == ICON_PATH, passed
    finally:
        rumps.alert = real_alert

    # 사용 통계: 파일 하나로 켜고 끈다 (자동실행과 같은 방식)
    with tempfile.TemporaryDirectory() as tmp:
        off = os.path.join(tmp, ANALYTICS_OFF_FILE)
        assert analytics_enabled(off), '기본값은 켜짐'
        set_analytics(False, off)
        assert not analytics_enabled(off)
        set_analytics(True, off)
        assert analytics_enabled(off)
        set_analytics(True, off)  # 두 번 켜도 예외 없음

    # 나가는 값에 개인 정보가 없어야 한다. 폴더 경로·파일명·사용자 이름이 새면 이 앱은 감시자가 된다.
    body = json.dumps(ga_payload('folder_add', {'watched_count': 2}), ensure_ascii=False)
    assert '"name": "folder_add"' in body and 'session_id' in body, body
    assert os.path.expanduser('~') not in body, body
    assert 'watched_count' in body and body.count('/') == 0, body

    _selfcheck_menu()
    print('OK:', launch_arguments())
    print('로그:', LOG_PATH)


def _selfcheck_menu():
    # 메뉴 조립 검증: 폴더 항목이 순서대로 들어가고, 하나만 빼도 나머지가 남는다.
    import tempfile
    app = JasoRumpsApp()
    fixed = ['대상 폴더 선택', '로그인 시 자동실행', '사용 통계 보내기', '도움말', '종료']
    for title in fixed:  # run()이 데코레이터에서 만들어주는 고정 항목을 손으로 세운다
        app.menu.add(rumps.MenuItem(title))

    def keys():
        # 구분선 키는 rumps가 붙이는 카운터라 재삽입하면 값이 바뀐다 — 개수와 자리만 본다.
        return ['SEP' if k.startswith('SeparatorMenuItem') else k for k in app.menu]

    def watching(*paths):  # 감시 폴더가 1곳 이상일 때의 기대 메뉴
        return [WATCH_HEADER, *paths, 'SEP'] + fixed[:1] + ['한번에 변환'] + fixed[1:]

    with tempfile.TemporaryDirectory() as tmp:
        app._application_support = tmp  # 진짜 설정 파일을 건드리지 않는다
        a, b = os.path.join(tmp, '사진'), os.path.join(tmp, '하위', '사진')  # 이름이 같은 폴더 둘
        os.makedirs(a)
        os.makedirs(b)

        app._start_watching(a)
        app._start_watching(b)
        # rumps.Timer는 NSDefaultRunLoopMode에 걸린다 — 콜백이 붙드는 동안 앱 전체가 멎는다.
        # 감시는 데몬 스레드가 알아서 돈다. 메인 런루프에 타이머를 거는 순간이 회귀다(81e3dfb8).
        assert rumps.timers() == [], rumps.timers()
        app._save_watched_directories()
        assert keys() == watching(a, b), keys()
        assert app.menu[WATCH_HEADER].callback is None, '헤더는 비활성 (클릭 불가)'
        assert [app.menu[a].title, app.menu[b].title] == ['사진', '사진'], '보이는 건 폴더 이름'
        assert list(app.menu[a]) == [a, '감시 해제'], '서브메뉴에 전체 경로'
        assert app.menu['대상 폴더 선택'].title == '폴더 추가'

        unwatch_a = app.menu[a]['감시 해제']
        unwatch_a.callback(unwatch_a)  # 메뉴를 클릭했을 때 rumps가 하는 것과 같은 호출
        assert app.watched_directories == [b], '나머지 폴더는 유지'
        assert list(app.watcher.watches) == [b], '나머지 폴더의 감시도 유지'
        assert keys() == watching(b), keys()
        assert app._load_watched_directories() == [b], '해제가 저장 파일에 즉시 반영'

        app._stop_watching(b)
        assert list(app.menu) == fixed, '전부 해제하면 초기 상태 (헤더·구분선·한번에 변환 사라짐)'
        assert app.watcher.observer is None, '감시 스레드도 정리'
        assert app.menu['대상 폴더 선택'].title == '대상 폴더 선택'
        assert app._load_watched_directories() == []
        app._stop_watching(b)  # 두 번 해제해도 예외 없음

        # 다시 걸어도 헤더·구분선이 정확히 1개씩. 구분선 키는 이때 _2로 바뀐다(카운터가 안 줄어든다).
        app._start_watching(a)
        assert keys() == watching(a), keys()
        app._stop_watching(a)
        assert list(app.menu) == fixed, list(app.menu)


if __name__ == "__main__":
    if '--selfcheck' in sys.argv:
        _selfcheck()
        raise SystemExit

    if '--ga-test' in sys.argv:
        # GA 디버그 엔드포인트로 한 건 보내고 검증 메시지를 그대로 보여준다.
        # validationMessages가 비어 있으면 측정 ID·시크릿·페이로드가 모두 맞다는 뜻이다.
        print(_post_event('app_start', {'watched_count': 0}, debug=True))
        raise SystemExit

    app = JasoRumpsApp()
    app.run()
