# 자소

mac OSX 사용자들을 위한 한글 자소분리 방지 앱

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
poetry run python main.py
```

## 앱 빌드

```bash
./build.sh
```

## 앱 사용하기

### 1. 앱 실행

아직 앱을 패키징하지 못하여 코드를 다운로드 받아 빌드하여 사용하셔야 합니다.

![image](https://github.com/hsol/jaso/assets/1524891/8b587020-5d5e-4b37-a2e3-3a9a7c6c3127)

### 2. 자동변환 시작

자동변환 시작을 선택하여 자동으로 변환될 폴더 주소를 입력해줍니다.

![image](https://github.com/hsol/jaso/assets/1524891/b58a5c5a-e520-4448-9df8-684157ed2cde)

![image](https://github.com/hsol/jaso/assets/1524891/64df6bf3-d629-4e7b-8d5d-fa53a203b119)

### 3. 완료

이제 수정되거나, 이동하거나, 추가되는 폴더 및 파일명의 한글이 자소분리되지 않습니다!

![image](https://github.com/hsol/jaso/assets/1524891/e0fbc577-507d-44b6-a532-10e698dbd55a)

![image](https://github.com/hsol/jaso/assets/1524891/6a7a0b96-a263-44ea-82fa-54264aefa1cc)

https://github.com/hsol/jaso/assets/1524891/67e1994b-a43d-4c8d-bf66-05993ec9ef29
