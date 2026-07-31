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

# Application Support/자소/ 안에 저장되는 감시 폴더 경로 파일 (rumps.App.open 이 위치를 잡아준다)
WATCHED_DIRECTORY_FILE = 'watched_directory'


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
    directory, name = os.path.split(path)
    normalized_name = unicodedata.normalize('NFC', name)
    if len(name) == len(normalized_name):
        return

    normalized_path = os.path.join(directory, normalized_name)
    os.rename(path, normalized_path)


def normalize_quietly(path_type: str, path: str) -> bool:
    # 한 경로의 실패가 나머지 순회를 멈추지 않도록, 오류는 로그만 남기고 삼킨다.
    try:
        normalize_path(path)
        return True
    except Exception as e:
        print(f"{path_type} 처리 중 오류 발생: {path}, 오류: {e}")
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
    observer: Observer | None = None
    timer: rumps.Timer | None = None

    def __init__(self, directory_to_watch):
        self.directory_to_watch = directory_to_watch

    def run(self):
        event_handler = Handler()

        self.observer and self.observer.stop()
        self.observer = Observer()
        self.observer.schedule(event_handler, self.directory_to_watch, recursive=True)
        self.observer.start()

        def _maintainer(timer: rumps.Timer):
            if self.observer.is_alive():
                self.observer.join(1)

        self.timer = rumps.Timer(_maintainer, 1)
        self.timer.start()

    def stop(self):
        try:
            self.observer.stop()
            self.observer.join()
        except:
            pass
        finally:
            self.timer and self.timer.stop()


class Handler(FileSystemEventHandler):
    # 파일 시스템 이벤트에 반응하여 적절한 조치를 취하는 이벤트 핸들러 클래스입니다.
    @staticmethod
    def on_any_event(event):
        # watchdog 감시 스레드로 예외가 빠져나가면 스레드가 죽어 감시가 조용히 멈춘다.
        # 이벤트 처리 중 무슨 일이 나든 여기서 막는다.
        try:
            if event.event_type in ('created', 'modified'):
                normalize_filenames_in_directory(event.src_path)
            elif event.event_type == 'moved':
                normalize_filenames_in_directory(event.dest_path)
        except Exception as e:
            print(f"이벤트 처리 중 오류 발생: {event.event_type} {event.src_path}, 오류: {e}")


class JasoRumpsApp(rumps.App):
    # macOS 메뉴바 앱을 위한 클래스입니다.

    def __init__(self, *args, **kwargs):
        super().__init__(name="자소", icon=ICON_PATH, quit_button=None)

        self.watcher: Watcher | None = None
        self.icon_path = ICON_PATH
        self.watched_directory = None
        self.convert_menu_item = None

    # 감시 폴더 기억: rumps가 만들어주는 Application Support 폴더에 경로 한 줄만 저장한다.
    # 번들의 기본 인코딩이 ASCII라 한글 경로가 깨지므로 반드시 바이너리 + utf-8 로 다룬다.
    def _load_watched_directory(self):
        try:
            with self.open(WATCHED_DIRECTORY_FILE, 'rb') as f:
                directory = f.read().decode('utf-8')
        except (OSError, UnicodeDecodeError):
            return None
        return directory if os.path.isdir(directory) else None

    def _save_watched_directory(self, directory):
        try:
            with self.open(WATCHED_DIRECTORY_FILE, 'wb') as f:
                f.write((directory or '').encode('utf-8'))
        except OSError as e:
            print('감시 폴더 저장 실패:', e)

    def _start_watching(self, directory_path):
        # 폴더 선택과 시작 시 자동 복원이 공유하는 경로
        self.watched_directory = directory_path
        folder_name = os.path.basename(directory_path)
        self.menu["대상 폴더 선택"].title = f"다시선택 ({folder_name}에서 변환 중)"

        # 한번에 변환 메뉴 추가
        if self.convert_menu_item is None:
            self.convert_menu_item = rumps.MenuItem("한번에 변환", callback=self._convert_once)
            self.menu.insert_before("로그인 시 자동실행", self.convert_menu_item)

        self.watcher = Watcher(directory_path)
        self.watcher.run()

    @rumps.clicked("대상 폴더 선택")
    def _select_directory(self, _):
        try:
            if self.watcher:
                self.watcher.stop()
                self.watched_directory = None
                self._save_watched_directory('')
                self.menu["대상 폴더 선택"].title = "대상 폴더 선택"

                # 한번에 변환 메뉴 제거
                if self.convert_menu_item:
                    self.menu.pop(self.convert_menu_item.title)
                    self.convert_menu_item = None
                
                rumps.alert(message="이미 실행 중이던 작업을 중단했습니다.", icon_path=self.icon_path)
            
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
                else:
                    self._start_watching(directory_path)
                    self._save_watched_directory(directory_path)
                    rumps.alert("폴더가 설정되었습니다. 이제부터 해당 폴더에서 자동으로 한글의 자소분리가 방지됩니다.", icon_path=self.icon_path)
            else:
                rumps.alert("폴더를 선택하지 않았습니다.", icon_path=self.icon_path)
        except Exception as e:
            rumps.alert(f"오류: {str(e)}")

    def _convert_once(self, _):
        try:
            if not self.watched_directory:
                rumps.alert("먼저 대상 폴더를 선택해주세요.", icon_path=self.icon_path)
                return
            
            if not os.path.isdir(self.watched_directory):
                rumps.alert("선택된 폴더가 더 이상 유효하지 않습니다.", icon_path=self.icon_path)
                return
            
            # 선택된 폴더 내 모든 파일과 폴더명을 한번에 변환
            processed_count = normalize_filenames_in_directory(self.watched_directory)
            folder_name = os.path.basename(self.watched_directory)
            rumps.alert(f"변환 완료!\n\n폴더: {folder_name}\n처리된 항목 수: {processed_count}개\n\n모든 파일과 폴더명이 NFD에서 NFC로 변환되었습니다.", icon_path=self.icon_path)
        except Exception as e:
            rumps.alert(f"오류: {str(e)}")

    @rumps.events.before_start
    def _restore_state(self):
        # 메뉴는 run() 시점에 만들어지므로 __init__ 이 아니라 여기서 상태를 맞춘다.
        self.menu["로그인 시 자동실행"].state = autostart_enabled()

        directory = self._load_watched_directory()
        if directory:
            # 시작 시 복원은 조용히 — 로그인 자동실행 때 알림창이 뜨면 곤란하다.
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
        if self.watcher:
            self.watcher.stop()
            self.watched_directory = None
        
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
    print('OK:', launch_arguments())


if __name__ == "__main__":
    if '--selfcheck' in sys.argv:
        _selfcheck()
        raise SystemExit

    from AppKit import NSOpenPanel, NSOKButton, NSApplication, NSModalPanelWindowLevel
    app = JasoRumpsApp()
    app.run()
