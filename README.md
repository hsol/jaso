# 자소

맥에서 만든 파일·폴더 이름의 한글이 윈도우에서 깨지는 것(자소분리)을 자동으로 막아주는 맥 앱입니다.
감시할 폴더를 지정해두면 — 여러 곳을 걸어둬도 됩니다 — 그 안에서 새로 생기거나 이름이 바뀌는
파일을 알아서 NFC로 되돌립니다.

### [⬇︎ 최신 버전 내려받기 (.dmg)](https://github.com/hsol/jaso/releases/latest)

<!-- 이 숫자는 setup.py의 LSMinimumSystemVersion과 같은 값이어야 하고, 번들의 실제 minos가
     그보다 높으면 scripts/build_dmg.sh가 빌드를 세운다(티켓 6ad582ef). 손으로 맞출 필요는 없고,
     빌드가 서면 그때 세 곳(setup.py·여기·아래 문장)을 함께 올린다.
     아래 서명·공증 문장은 v0.1.1 DMG로 실측 확인했다(티켓 a6743b18):
       spctl -a -t open  → accepted / source=Notarized Developer ID
       xcrun stapler validate → The validate action worked!
     릴리스가 미서명으로 도로 나가면 이 문장부터 거짓이 되니 함께 고칠 것. -->
**Apple Silicon(M1 이상) 맥 전용, macOS 11 이상**이 필요합니다. 인텔 맥에서는 실행되지 않습니다.
Apple Developer ID로 서명·공증했으므로 "확인되지 않은 개발자" 경고 없이 바로 실행됩니다.

## 무슨 문제인가요

맥(APFS/HFS+)은 파일명 한글을 **NFD**로 저장합니다. `각`을 `ㄱ + ㅏ + ㄱ`처럼 자모로 쪼개서 씁니다.
반면 윈도우와 대부분의 소프트웨어는 **NFC**를 씁니다. `각`을 글자 하나로 씁니다.

그래서 맥에서 `이렇게 됩니다.txt`로 저장한 파일을 구글 드라이브·원드라이브·웹하드로 공유하면
윈도우 쪽에서는 이렇게 보입니다.

```
ㅇㅣㄹㅓㅎㄱㅔㄷㅗㅣㅂㄴㅣㄷㅏ.txt
```

10년 넘게 고쳐지지 않은 문제라서, 맥과 윈도우를 오가며 협업하면 계속 마주치게 됩니다.

## 기존 방식과 뭐가 다른가요

지금까지는 `Contact`나 `반디네이머` 같은 도구로 그때그때 일괄 변환하거나,
`convmv -r -f utf-8 -t utf-8 --nfc .` 같은 명령을 직접 돌려서 해결했습니다.
문제는 **한 번 고쳐도 끝이 아니라는 것**입니다. 맥에서 파일을 하나 더 만들거나 이름만 바꿔도
그 파일은 다시 NFD가 되고, 윈도우 쪽 동료는 또 깨진 이름을 봅니다.

자소는 그 반복을 없앱니다. 폴더를 한 번 지정해두면 — 작업 폴더, 공유 폴더, 다운로드 폴더처럼
여러 곳을 함께 걸어둘 수 있습니다 — 이후로는 감시하다가 자동으로 NFC를 유지하므로,
변환을 "실행하는" 일 자체가 사라집니다.

## 앱 사용하기

### 1. 앱 실행

DMG 파일을 통해 설치한 후 Applications 폴더에서 `자소` 앱을 실행하거나, 개발 중이라면 다음 명령어로 실행할 수 있습니다:

```bash
poetry run python src/main.py
```

<img width="236" height="114" alt="image" src="https://github.com/user-attachments/assets/dbdc053e-9f8c-402b-9ffa-f83ab66879fc" />

### 2. 대상 폴더 선택

자동변환을 원하는 폴더를 선택해줍니다.

<img width="116" height="101" alt="image" src="https://github.com/user-attachments/assets/76b2ab1a-1679-443d-b7b8-fcb3ad3be73f" />
<img width="809" height="461" alt="image" src="https://github.com/user-attachments/assets/31e7b6b9-952e-49c3-aa02-a0171f44a035" />

이제 수정되거나, 이동하거나, 추가되는 폴더 및 파일명의 한글이 자소분리되지 않습니다!

폴더가 하나라도 걸리면 메뉴 맨 위에 "감시 중인 폴더" 아래로 감시 중인 폴더들이 걸어둔 순서대로
늘어서고, 구분선 아래가 명령입니다.

```
감시 중인 폴더
사진
문서
──────────
폴더 추가
한번에 변환
로그인 시 자동실행
도움말
종료
```

**폴더를 더 걸려면** "폴더 추가"를 누릅니다 (아직 한 곳도 없을 때는 "대상 폴더 선택"입니다).
누를 때마다 목록에 한 줄씩 늘어납니다.

**한 폴더만 빼려면** 목록의 그 폴더 이름 위에 마우스를 올려 "감시 해제"를 누릅니다.
나머지 폴더는 그대로 감시가 이어집니다. (이름이 같은 폴더를 둘 걸었다면 서브메뉴 첫 줄의
전체 경로로 구분할 수 있습니다.)

걸어둔 폴더는 기억되므로, 앱을 다시 켜면 바로 이어서 감시합니다. 감시를 해제한 폴더는 기억에서도
지워져 다시 켜도 돌아오지 않습니다.

<img width="271" height="220" alt="image" src="https://github.com/user-attachments/assets/77d569a5-53eb-4ba8-802c-6c9a3148b99f" />

### 3. 로그인 시 자동실행

메뉴에서 "로그인 시 자동실행"을 클릭하면 체크 표시가 켜지고, 다음 로그인부터 앱이 자동으로 실행됩니다. 다시 클릭하면 해제됩니다.

내부적으로는 `~/Library/LaunchAgents/tech.proofer.jaso.plist`를 만들거나 지우는 방식이며, 앱을 다른 위치로 옮겼다면 체크를 껐다 다시 켜주세요.

### 4. 한번에 변환

기본적으로 이전에 추가된 파일에 대해서는 변환을 진행하지 않습니다. 이 경우 "한번에 변환" 기능을 활용하여 변환할 수 있습니다.
등록된 폴더를 모두 훑고, 폴더별로 몇 개를 바꿨는지 알려줍니다.
<img width="216" height="114" alt="image" src="https://github.com/user-attachments/assets/e3faa353-efcf-44e6-9183-d7a489c1ef31" />
<img width="269" height="282" alt="image" src="https://github.com/user-attachments/assets/c703cc64-956a-4559-a08f-c009537d6d2d" />

### 5. 변환완료!

![image](https://github.com/hsol/jaso/assets/1524891/6a7a0b96-a263-44ea-82fa-54264aefa1cc)

## 개발자라면

빌드·릴리스·서명 설정은 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)에 있습니다.
