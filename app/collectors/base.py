"""수집기 공통 유틸.

핵심 원칙: 수집기 하나가 깨져도 나머지는 계속 돈다.
run() 은 예외를 밖으로 던지지 않고 collection_runs 에 기록한 뒤 결과만 반환한다.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

import requests

from ..config import HTTP_HEADERS, HTTP_TIMEOUT
from ..db import finish_run, start_run

log = logging.getLogger("collector")

_session = requests.Session()
_session.headers.update(HTTP_HEADERS)


@dataclass
class Result:
    collector: str
    status: str          # ok | skipped | error
    rows: int = 0
    message: str = ""

    def as_dict(self) -> dict:
        return dict(collector=self.collector, status=self.status,
                    rows=self.rows, message=self.message)


def http_get(url: str, *, params: dict | None = None, retries: int = 3,
             timeout: int | None = None) -> requests.Response:
    """지수 백오프 재시도가 붙은 GET."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=timeout or HTTP_TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001 - 재시도 후 마지막에 다시 던진다
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"GET 실패: {url} ({last})")


def run_collector(name: str, fn: Callable[[], Result]) -> Result:
    """수집기를 실행하고 실행 이력을 남긴다. 예외는 여기서 흡수한다."""
    run_id = start_run(name)
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001
        log.warning("[%s] 수집 실패: %s", name, exc)
        result = Result(name, "error", 0, str(exc))
    finish_run(run_id, result.status, result.rows, result.message)
    log.info("[%s] %s rows=%s %s", name, result.status, result.rows, result.message)
    return result
