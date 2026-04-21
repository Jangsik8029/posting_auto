"""공용 HTTP 세션 + 타임아웃 상수.

외부 API를 호출하는 클라이언트는 이 모듈의 세션을 사용해
TCP 커넥션 풀을 재사용하고 일관된 User-Agent를 전송한다.
"""
from __future__ import annotations

import logging
import threading

import requests

logger = logging.getLogger(__name__)

TIMEOUT_DEFAULT = 30
TIMEOUT_LONG = 120
TIMEOUT_SHORT = 10

DEFAULT_USER_AGENT = "posting-auto/0.1 (+https://github.com/)"

_session_lock = threading.Lock()
_session: requests.Session | None = None


def get_shared_session() -> requests.Session:
    """프로세스 당 하나의 requests.Session 을 반환한다."""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                s = requests.Session()
                s.headers.update({"User-Agent": DEFAULT_USER_AGENT})
                _session = s
    return _session


def reset_shared_session() -> None:
    """테스트용 세션 리셋."""
    global _session
    with _session_lock:
        if _session is not None:
            try:
                _session.close()
            except Exception as exc:
                logger.debug("Session close ignored: %s", exc)
        _session = None
