# 개발 문서

`Python 3.11`

## 앱 초기설정

### poetry(python 패키지 매니저) 설치

```
pip install poetry
```

또는 Brew 로 설치

```
brew install poetry
```

### 패키지 설치

```
eval $(poetry env activate)
poetry install
```

## 앱 개발

```
poetry run python src/main.py
```

## 앱 빌드

### 기본 앱 빌드

```bash
./scripts/build.sh
```

### 설치 파일(DMG) 생성

```bash
./scripts/build_dmg.sh
```

생성된 DMG 파일을 더블클릭하여 마운트한 후, `자소.app`을 `Applications` 폴더로 드래그 앤 드롭하여 설치할 수 있습니다.

## 릴리스

`main`에 푸시하면 GitHub Actions가 DMG를 빌드해 릴리스를 올립니다.
릴리스할 때 사람이 하는 일은 `pyproject.toml`의 `version` 한 줄을 올리는 것뿐입니다.
같은 버전으로 다시 푸시하면 이미 그 릴리스가 있으므로 빌드 없이 건너뜁니다.

### 필요한 GitHub Secrets

릴리스는 서명된 DMG만 올립니다. 아래 값은 저장소 **Settings → Secrets and variables → Actions**에
넣어 두어야 하고, **하나라도 비어 있으면 릴리스 워크플로가 빌드 전에 실패합니다**
(미서명 DMG가 릴리스에 올라가는 일을 막기 위해서입니다).

| 이름 | 무엇이고 어디서 나오나 |
|---|---|
| `CERT_P12_BASE64` | Developer ID Application 인증서를 키체인 접근에서 `.p12`로 내보낸 뒤 `base64 -i cert.p12 \| pbcopy` 한 값 |
| `CERT_PASSWORD` | 위 `.p12`를 내보낼 때 지정한 비밀번호 |
| `TEAM_ID` | Apple Developer 계정의 10자리 팀 ID (developer.apple.com → Membership) |
| `AC_KEY_ID` | 공증용. App Store Connect → 사용자 및 액세스 → 통합 → App Store Connect API 키의 Key ID |
| `AC_ISSUER_ID` | 공증용. 같은 화면 위쪽에 있는 Issuer ID (팀 하나에 하나) |
| `AC_KEY_P8_BASE64` | 공증용. API 키를 만들 때 한 번만 받는 `.p8` 파일을 base64로 인코딩한 값 |
