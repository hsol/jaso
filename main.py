import os
import unicodedata
import subprocess

# macOS 경고 메시지 숨기기
os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

import rumps
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def normalize_path(path: str):
    # 주어진 파일 경로의 이름을 NFC 유니코드 형식으로 정규화하고 파일명을 변경합니다.
    directory, name = os.path.split(path)
    normalized_name = unicodedata.normalize('NFC', name)
    if len(name) == len(normalized_name):
        return

    normalized_path = os.path.join(directory, normalized_name)
    os.rename(path, normalized_path)


def normalize_filenames_in_directory(directory):
    # 주어진 디렉토리와 그 하위 폴더에 있는 모든 파일의 이름을 NFC로 정규화합니다.
    for dir_path, child_dir_names, filenames in os.walk(directory):
        for filename in filenames:
            file_path = os.path.join(dir_path, filename)
            normalize_path(str(file_path))
        for dir_name in child_dir_names:
            child_dir_path = os.path.join(dir_path, dir_name)
            normalize_path(str(child_dir_path))
        break


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
        if event.event_type == 'created':
            normalize_filenames_in_directory(event.src_path)
        elif event.event_type == 'modified':
            normalize_filenames_in_directory(event.src_path)
        elif event.event_type == 'moved':
            normalize_filenames_in_directory(event.dest_path)


class JasoRumpsApp(rumps.App):
    # macOS 메뉴바 앱을 위한 클래스입니다.

    def __init__(self, *args, **kwargs):
        icon_path = "icon.icns"
        super().__init__(name="자소", icon=icon_path, quit_button=None)

        self.watcher: Watcher | None = None
        self.icon_path = icon_path
        self.watched_directory = None

    @rumps.clicked("자동변환 시작")
    def _start(self, _):
        try:
            if self.watcher:
                self.watcher.stop()
                self.watched_directory = None
                self.menu["자동변환 시작"].title = "자동변환 시작"
                rumps.alert(message="이미 실행 중이던 작업을 중단했습니다.", icon_path=self.icon_path)
            
            # rumps를 통해 AppKit에 접근하여 네이티브 폴더 선택 다이얼로그 사용
            import objc
            from Foundation import NSURL
            from AppKit import NSOpenPanel, NSOKButton
            
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseFiles_(False)
            panel.setCanChooseDirectories_(True)
            panel.setAllowsMultipleSelection_(False)
            panel.setTitle_("폴더 선택")
            panel.setMessage_("한글 자소분리를 방지할 폴더를 선택해주세요.")
            
            if panel.runModal() == NSOKButton:
                directory_path = panel.URLs()[0].path()
            else:
                directory_path = ""
            
            if directory_path:
                if not os.path.isdir(directory_path):
                    rumps.alert("유효하지 않은 폴더입니다.", icon_path=self.icon_path)
                else:
                    # 버튼 텍스트 업데이트
                    self.watched_directory = directory_path
                    folder_name = os.path.basename(directory_path)
                    self.menu["자동변환 시작"].title = f"새로시작 ({folder_name}에서 변환 중)"
                    
                    rumps.alert("폴더가 설정되었습니다. 이제부터 해당 폴더에서 자동으로 한글의 자소분리가 방지됩니다.", icon_path=self.icon_path)
                    self.watcher = Watcher(directory_path)
                    self.watcher.run()
            else:
                rumps.alert("폴더를 선택하지 않았습니다.", icon_path=self.icon_path)
        except Exception as e:
            rumps.alert(f"오류: {str(e)}")

    @rumps.clicked("종료")
    def _quit(self, _):
        if self.watcher:
            self.watcher.stop()
            self.watched_directory = None
        rumps.quit_application()


if __name__ == "__main__":
    app = JasoRumpsApp()
    app.run()
