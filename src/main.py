import os
import plistlib
import sys
import unicodedata
import webbrowser
# macOS 경고 메시지 숨기기
os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

# py2app 번들의 stdout/stderr 기본 인코딩은 ASCII다. 이 앱의 로그와 경로는 대부분 한글이라
# 그대로 두면 print 한 줄이 UnicodeEncodeError를 던진다. 여기서 한 번 UTF-8로 맞춰둔다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors='replace')

import rumps
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# 번들에서는 cwd가 Contents/Resources, 개발 실행에서는 저장소 assets/
ICON_PATH = ('icon.icns' if os.path.exists('icon.icns')
             else os.path.join(os.path.dirname(__file__), '..', 'assets', 'icon.icns'))

AUTOSTART_LABEL = 'tech.proofer.jaso'
AUTOSTART_PLIST = os.path.expanduser(f'~/Library/LaunchAgents/{AUTOSTART_LABEL}.plist')

# Application Support/자소/ 안에 저장되는 감시 폴더 목록 파일 (rumps.App.open 이 위치를 잡아준다)
WATCHED_DIRECTORY_FILE = 'watched_directory'


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
    # __file__ 이 <앱>.app/Contents/Resources/main.py 라는 점을 이용해 .app 경로를 되짚고 open 으로 띄운다.
    if getattr(sys, 'frozen', None) == 'macosx_app':
        bundle = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        return ['/usr/bin/open', bundle]
    return [sys.executable, os.path.abspath(__file__)]


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
    # Observer 하나에 여러 폴더를 걸 수 있으므로 폴더가 늘어도 스레드와 타이머는 하나뿐이다.
    observer: Observer | None = None
    timer: rumps.Timer | None = None

    def watch(self, directory_to_watch):
        # 이미 도는 Observer에 경로를 하나 더 건다 — 기존 폴더의 감시는 끊기지 않는다.
        if self.observer is None:
            self.observer = Observer()
            self.observer.start()

            def _maintainer(timer: rumps.Timer):
                if self.observer.is_alive():
                    self.observer.join(1)

            self.timer = rumps.Timer(_maintainer, 1)
            self.timer.start()

        self.observer.schedule(Handler(), directory_to_watch, recursive=True)

    def stop(self):
        # 걸어둔 경로가 몇 개든 Observer가 하나라 한 번의 stop으로 감시 스레드가 전부 정지한다.
        try:
            self.observer.stop()
            self.observer.join()
        except:
            pass
        finally:
            self.timer and self.timer.stop()
            self.observer = None
            self.timer = None


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

    def _start_watching(self, directory_path):
        # 폴더 선택과 시작 시 자동 복원이 공유하는 경로. 목록에 하나를 더한다.
        _failed_paths.clear()  # 새 감시 시작이면 지난 실패 기록은 무효
        self.watched_directories.append(directory_path)
        self.menu["대상 폴더 선택"].title = f"폴더 추가 ({len(self.watched_directories)}곳 감시 중)"

        # 한번에 변환 메뉴 추가
        if self.convert_menu_item is None:
            self.convert_menu_item = rumps.MenuItem("한번에 변환", callback=self._convert_once)
            self.menu.insert_before("로그인 시 자동실행", self.convert_menu_item)

        self.watcher.watch(directory_path)

    @rumps.clicked("대상 폴더 선택")
    def _select_directory(self, _):
        try:
            # AppKit 초기화 및 권한 확인
            if not NSApplication.sharedApplication():
                NSApplication.sharedApplication()
            
            # rumps를 통해 AppKit에 접근하여 네이티브 폴더 선택 다이얼로그 사용
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseFiles_(False)
            panel.setCanChooseDirectories_(True)
            panel.setAllowsMultipleSelection_(False)
            panel.setTitle_("폴더 선택")
            panel.setMessage_("한글 자소분리를 방지할 폴더를 선택해주세요.")
            
            # 다이얼로그를 최상위로 설정
            panel.setLevel_(NSModalPanelWindowLevel)
            
            # 메인 스레드에서 실행되도록 보장
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
                    rumps.alert("유효하지 않은 폴더입니다.", icon_path=self.icon_path)
                elif os.path.normpath(directory_path) in map(os.path.normpath, self.watched_directories):
                    rumps.alert("이미 감시 중인 폴더입니다.", icon_path=self.icon_path)
                else:
                    self._start_watching(directory_path)
                    self._save_watched_directories()
                    rumps.alert(f"폴더가 추가되었습니다. 이제 {len(self.watched_directories)}곳에서 자동으로 한글의 자소분리가 방지됩니다.", icon_path=self.icon_path)
            else:
                rumps.alert("폴더를 선택하지 않았습니다.", icon_path=self.icon_path)
        except Exception as e:
            rumps.alert(f"오류: {str(e)}")

    def _convert_once(self, _):
        try:
            if not self.watched_directories:
                rumps.alert("먼저 대상 폴더를 선택해주세요.", icon_path=self.icon_path)
                return

            # 수동 실행은 재시도 기회다 — 권한을 고쳤을 수 있으니 실패 기록을 비우고 다시 훑는다
            _failed_paths.clear()

            # 등록된 모든 폴더의 파일과 폴더명을 한번에 변환 (폴더별 건수를 알림에 그대로 보여준다)
            lines = []
            for directory in self.watched_directories:
                folder_name = os.path.basename(directory)
                if not os.path.isdir(directory):
                    lines.append(f"{folder_name}: 폴더를 찾을 수 없음")
                    continue
                lines.append(f"{folder_name}: {normalize_filenames_in_directory(directory)}개")

            failed_note = f"\n건너뛴 항목: {len(_failed_paths)}개 (권한 등으로 이름 변경 실패)" if _failed_paths else ""
            rumps.alert("변환 완료!\n\n" + "\n".join(lines) + f"{failed_note}\n\n모든 파일과 폴더명이 NFD에서 NFC로 변환되었습니다.", icon_path=self.icon_path)
        except Exception as e:
            rumps.alert(f"오류: {str(e)}")

    @rumps.events.before_start
    def _restore_state(self):
        # 메뉴는 run() 시점에 만들어지므로 __init__ 이 아니라 여기서 상태를 맞춘다.
        self.menu["로그인 시 자동실행"].state = autostart_enabled()

        # 시작 시 복원은 조용히 — 로그인 자동실행 때 알림창이 뜨면 곤란하다.
        for directory in self._load_watched_directories():
            self._start_watching(directory)

    @rumps.clicked("로그인 시 자동실행")
    def _toggle_autostart(self, sender):
        try:
            sender.state = 0 if sender.state else 1
            set_autostart(bool(sender.state))
        except Exception as e:
            sender.state = autostart_enabled()
            rumps.alert(f"자동실행 설정 실패: {e}", icon_path=self.icon_path)

    @rumps.clicked("도움말", "개발자 정보")
    def _developer_info(self, _):
        if not rumps.alert("개발자 정보", "임한솔\nmolmoty@gmail.com\nhttps://hsol.info",
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
    print('OK:', launch_arguments())


if __name__ == "__main__":
    if '--selfcheck' in sys.argv:
        _selfcheck()
        raise SystemExit

    from AppKit import NSOpenPanel, NSOKButton, NSApplication, NSModalPanelWindowLevel
    app = JasoRumpsApp()
    app.run()
