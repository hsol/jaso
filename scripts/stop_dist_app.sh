#!/bin/bash

# 빌드가 dist를 지우기 전에, 그 dist에서 돌고 있는 자소를 종료시킨다.
#
# rm -rf dist가 실행 중인 번들을 지우면 프로세스는 살아남는다. 번들이 사라진 자소는
# 폴더 선택창이 openPanel() == nil로 실패하고 사용자는 이유를 알 수 없다(0e6628e4).
# 이 앱은 "로그인 시 자동실행"에 지금 실행 중인 경로를 박으므로, dist에서 한 번 켜 두면
# 빌드마다 재현된다.
#
# 죽일 대상을 고르는 기준은 이 저장소의 dist 절대경로 접두사다. macOS는 번들 앱을
# Contents/MacOS/... 절대경로로 exec하므로 argv[0]에 그 경로가 그대로 들어 있고,
# /Applications/자소.app이나 다른 클론의 dist는 접두사가 달라 매칭되지 않는다.
#
# 패턴에 '자소'를 넣지 않는다 — 이 앱의 이름은 하필 정규화가 갈리는 한글이다. argv[0]의
# 번들 이름은 NFD(ㅈㅏㅅㅗ, e1 84 8c ...)로 들어오는데 이 파일에 적는 '자소'는 NFC(ec 9e 90 ...)라
# 바이트가 달라 pgrep이 영영 못 찾는다(실측: NFC 패턴 → 매칭 0, ASCII 접두사 → 매칭 1).
# dist 아래에서 도는 것은 이 앱뿐이므로 ASCII 접두사만으로 충분하다.

cd "$(dirname "$0")/.."

PIDS=$(pgrep -f "$PWD/dist/") || exit 0   # 없으면 조용히 빠진다

echo "🛑 dist에서 실행 중인 자소를 종료합니다 (pid: $PIDS)"
kill $PIDS 2>/dev/null

# 죽는 것을 보고 나서 돌려준다. 안 기다리면 rm이 살아 있는 프로세스의 번들을 지우는
# 바로 그 고장이 그대로 난다.
for _ in $(seq 20); do
    kill -0 $PIDS 2>/dev/null || exit 0
    sleep 0.1
done

# ponytail: 2초를 안 죽으면 SIGKILL. 자소는 저장할 상태가 없어 이걸로 잃을 게 없다.
kill -9 $PIDS 2>/dev/null || true
