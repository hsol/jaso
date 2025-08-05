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

<img width="236" height="114" alt="image" src="https://github.com/user-attachments/assets/dbdc053e-9f8c-402b-9ffa-f83ab66879fc" />


### 2. 대상 폴더 선택

자동변환을 원하는 폴더를 선택해줍니다.

<img width="116" height="101" alt="image" src="https://github.com/user-attachments/assets/76b2ab1a-1679-443d-b7b8-fcb3ad3be73f" />
<img width="809" height="461" alt="image" src="https://github.com/user-attachments/assets/31e7b6b9-952e-49c3-aa02-a0171f44a035" />

이제 수정되거나, 이동하거나, 추가되는 폴더 및 파일명의 한글이 자소분리되지 않습니다!

<img width="271" height="220" alt="image" src="https://github.com/user-attachments/assets/77d569a5-53eb-4ba8-802c-6c9a3148b99f" />

### 3. 한번에 변환

기본적으로 이전에 추가된 파일에 대해서는 변환을 진행하지 않습니다. 이 경우 "한번에 변환" 기능을 활용하여 변환할 수 있습니다.

### 4. 변환완료!

![image](https://github.com/hsol/jaso/assets/1524891/6a7a0b96-a263-44ea-82fa-54264aefa1cc)

### (deprecated)가이드 영상 업데이트필요

https://github.com/hsol/jaso/assets/1524891/67e1994b-a43d-4c8d-bf66-05993ec9ef29
