# posting_auto

## UI 실행 방법

`ui.py`는 Streamlit 앱입니다. 아래 순서대로 실행하세요.

### 1. 가상환경 생성 (최초 1회)

```bash
python3 -m venv .venv
```

### 2. 의존성 설치 (최초 1회)

```bash
.venv/bin/pip install -r requirements-ui.txt
```

### 3. UI 실행

```bash
.venv/bin/streamlit run ui.py
```

### 4. 접속

실행 후 브라우저에서 다음 주소로 접속합니다.

- **로컬:** http://localhost:8501
- **네트워크:** 터미널에 표시되는 Network URL 사용

### 요약 (가상환경이 이미 있는 경우)

```bash
.venv/bin/streamlit run ui.py
```
