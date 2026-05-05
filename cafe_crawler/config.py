import os
from pathlib import Path

# posting_auto/cafe_crawler/config.py → BASE_DIR = posting_auto/
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "cafe.db"
KNOWLEDGE_DB_PATH = DATA_DIR / "knowledge.db"

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")

NAVER_DISPLAY = 100
NAVER_MAX_PAGES = 10
KAKAO_SIZE = 50
KAKAO_MAX_PAGES = 10

REQUEST_TIMEOUT = 10


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def require_naver_keys() -> None:
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise RuntimeError(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 .env 에 설정되어야 합니다."
        )


def require_kakao_key() -> None:
    if not KAKAO_REST_API_KEY:
        raise RuntimeError("KAKAO_REST_API_KEY 가 .env 에 설정되어야 합니다.")


def _read_env_at_runtime():
    """env 변수는 모듈 import 후 .env 가 로드되는 케이스도 있으므로 호출 시점에 재조회."""
    return (
        os.getenv("NAVER_CLIENT_ID", "") or NAVER_CLIENT_ID,
        os.getenv("NAVER_CLIENT_SECRET", "") or NAVER_CLIENT_SECRET,
        os.getenv("KAKAO_REST_API_KEY", "") or KAKAO_REST_API_KEY,
    )
