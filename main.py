import os
import unicodedata
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
    # 주어진 폴더와 그 하위 폴더에 있는 모든 파일의 이름을 NFC로 정규화합니다.
    processed_count = 0
    
    # 모든 경로를 먼저 수집하여 상위 폴더 변경의 영향을 받지 않도록 함
    all_paths = []

    # 일단 선택된 폴더부터 정규화
    normalize_path(directory)
    
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
        try:
            normalize_path(str(path))
            processed_count += 1
        except Exception as e:
            print(f"{path_type} 처리 중 오류 발생: {path}, 오류: {e}")
    
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
        self.convert_menu_item = None

    @rumps.clicked("대상 폴더 선택")
    def _select_directory(self, _):
        try:
            if self.watcher:
                self.watcher.stop()
                self.watched_directory = None
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
                    # 버튼 텍스트 업데이트
                    self.watched_directory = directory_path
                    folder_name = os.path.basename(directory_path)
                    self.menu["대상 폴더 선택"].title = f"다시선택 ({folder_name}에서 변환 중)"
                    
                    # 한번에 변환 메뉴 추가
                    if self.convert_menu_item is None:
                        self.convert_menu_item = rumps.MenuItem("한번에 변환", callback=self._convert_once)
                        self.menu.insert_before("종료", self.convert_menu_item)
                    
                    rumps.alert("폴더가 설정되었습니다. 이제부터 해당 폴더에서 자동으로 한글의 자소분리가 방지됩니다.", icon_path=self.icon_path)
                    self.watcher = Watcher(directory_path)
                    self.watcher.run()
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

    @rumps.clicked("종료")
    def _quit(self, _):
        if self.watcher:
            self.watcher.stop()
            self.watched_directory = None
        
        rumps.quit_application()


if __name__ == "__main__":
    from AppKit import NSOpenPanel, NSOKButton, NSApplication, NSModalPanelWindowLevel
    app = JasoRumpsApp()
    app.run()
