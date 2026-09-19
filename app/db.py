"""SQLite 스키마와 접근 헬퍼.

observations 는 (indicator_code, obs_date) 복합 PK 를 써서 UPSERT 로 멱등하게 적재한다.
같은 수집을 몇 번 돌려도 행이 늘어나지 않고 값만 갱신된다.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from .config import DB_PATH

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS indicators (
    code          TEXT PRIMARY KEY,
    name_ko       TEXT NOT NULL,
    name_en       TEXT,
    country       TEXT NOT NULL,
    category      TEXT NOT NULL,
    unit          TEXT,
    source        TEXT,
    source_id     TEXT,
    frequency     TEXT,
    transform     TEXT,
    decimals      INTEGER DEFAULT 2,
    display_order INTEGER DEFAULT 999,
    featured      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS observations (
    indicator_code TEXT NOT NULL,
    obs_date       TEXT NOT NULL,
    value          REAL NOT NULL,
    PRIMARY KEY (indicator_code, obs_date)
);
CREATE INDEX IF NOT EXISTS idx_obs_date ON observations(obs_date);

CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    uid            TEXT UNIQUE,
    event_date     TEXT NOT NULL,
    event_time     TEXT,
    country        TEXT,
    title          TEXT NOT NULL,
    importance     INTEGER DEFAULT 2,
    indicator_code TEXT,
    actual         TEXT,
    forecast       TEXT,
    previous       TEXT,
    source         TEXT,
    url            TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);

CREATE TABLE IF NOT EXISTS speeches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uid          TEXT UNIQUE,
    published_at TEXT NOT NULL,
    speaker      TEXT,
    role         TEXT,
    org          TEXT,
    title        TEXT NOT NULL,
    url          TEXT,
    summary      TEXT,
    tone         TEXT,
    tone_score   REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_speeches_pub ON speeches(published_at DESC);

CREATE TABLE IF NOT EXISTS forecasts (
    indicator_code TEXT NOT NULL,
    target_period  TEXT NOT NULL,   -- 예측 대상 기간 (YYYY-MM-01 / YYYY-01-01)
    horizon        TEXT NOT NULL,   -- month | year
    value          REAL NOT NULL,
    source         TEXT NOT NULL,
    as_of          TEXT,            -- 전망 발표 시점
    note           TEXT,
    PRIMARY KEY (indicator_code, target_period, horizon, source)
);
CREATE INDEX IF NOT EXISTS idx_fc_code ON forecasts(indicator_code, target_period);

CREATE TABLE IF NOT EXISTS documents (
    uid           TEXT PRIMARY KEY,
    doc_type      TEXT NOT NULL,      -- minutes | statement
    meeting_date  TEXT,
    published_at  TEXT,
    title         TEXT NOT NULL,
    url           TEXT,
    body          TEXT,               -- 원문
    summary_ko    TEXT,               -- 한글 핵심 요약
    tone          TEXT,               -- hawkish | dovish | neutral
    tone_reason   TEXT,
    translated_at TEXT,
    model         TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_date ON documents(meeting_date DESC);

CREATE TABLE IF NOT EXISTS collection_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    collector   TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT,
    rows        INTEGER DEFAULT 0,
    message     TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_collector ON collection_runs(collector, id DESC);
"""


def get_conn() -> sqlite3.Connection:
    """스레드별 커넥션. 스케줄러 스레드와 요청 스레드가 따로 쓴다."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


@contextmanager
def tx():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


def query(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return get_conn().execute(sql, params).fetchall()


def query_one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return get_conn().execute(sql, params).fetchone()


# ---------------------------------------------------------------- upserts

def upsert_indicator(ind: dict) -> None:
    with tx() as conn:
        conn.execute(
            """
            INSERT INTO indicators (code, name_ko, name_en, country, category, unit,
                                    source, source_id, frequency, transform,
                                    decimals, display_order, featured)
            VALUES (:code, :name_ko, :name_en, :country, :category, :unit,
                    :source, :source_id, :frequency, :transform,
                    :decimals, :display_order, :featured)
            ON CONFLICT(code) DO UPDATE SET
                name_ko=excluded.name_ko, name_en=excluded.name_en,
                country=excluded.country, category=excluded.category,
                unit=excluded.unit, source=excluded.source,
                source_id=excluded.source_id, frequency=excluded.frequency,
                transform=excluded.transform, decimals=excluded.decimals,
                display_order=excluded.display_order, featured=excluded.featured
            """,
            ind,
        )


def upsert_observations(code: str, points: Iterable[tuple[str, float]]) -> int:
    """(날짜, 값) 목록을 멱등 적재하고 반영된 행 수를 반환한다."""
    rows = [(code, d, float(v)) for d, v in points if v is not None and d]
    if not rows:
        return 0
    with tx() as conn:
        conn.executemany(
            """
            INSERT INTO observations (indicator_code, obs_date, value)
            VALUES (?, ?, ?)
            ON CONFLICT(indicator_code, obs_date) DO UPDATE SET value=excluded.value
            """,
            rows,
        )
    return len(rows)


def upsert_event(ev: dict) -> None:
    with tx() as conn:
        conn.execute(
            """
            INSERT INTO events (uid, event_date, event_time, country, title,
                                importance, indicator_code, actual, forecast,
                                previous, source, url)
            VALUES (:uid, :event_date, :event_time, :country, :title,
                    :importance, :indicator_code, :actual, :forecast,
                    :previous, :source, :url)
            ON CONFLICT(uid) DO UPDATE SET
                event_date=excluded.event_date, event_time=excluded.event_time,
                title=excluded.title, importance=excluded.importance,
                indicator_code=excluded.indicator_code, source=excluded.source,
                url=excluded.url
            """,
            ev,
        )


def upsert_speech(sp: dict) -> None:
    with tx() as conn:
        conn.execute(
            """
            INSERT INTO speeches (uid, published_at, speaker, role, org, title,
                                  url, summary, tone, tone_score)
            VALUES (:uid, :published_at, :speaker, :role, :org, :title,
                    :url, :summary, :tone, :tone_score)
            ON CONFLICT(uid) DO UPDATE SET
                published_at=excluded.published_at, speaker=excluded.speaker,
                role=excluded.role, org=excluded.org, title=excluded.title,
                url=excluded.url, summary=excluded.summary,
                tone=excluded.tone, tone_score=excluded.tone_score
            """,
            sp,
        )


def upsert_forecast(fc: dict) -> None:
    with tx() as conn:
        conn.execute(
            """
            INSERT INTO forecasts (indicator_code, target_period, horizon,
                                   value, source, as_of, note)
            VALUES (:indicator_code, :target_period, :horizon,
                    :value, :source, :as_of, :note)
            ON CONFLICT(indicator_code, target_period, horizon, source)
            DO UPDATE SET value=excluded.value, as_of=excluded.as_of,
                          note=excluded.note
            """,
            fc,
        )


def upsert_document(doc: dict) -> bool:
    """새로 추가됐으면 True. 이미 있으면 원문만 갱신하고 False."""
    existing = query_one("SELECT uid FROM documents WHERE uid = ?", (doc["uid"],))
    with tx() as conn:
        conn.execute(
            """
            INSERT INTO documents (uid, doc_type, meeting_date, published_at,
                                   title, url, body)
            VALUES (:uid, :doc_type, :meeting_date, :published_at,
                    :title, :url, :body)
            ON CONFLICT(uid) DO UPDATE SET
                title=excluded.title, url=excluded.url, body=excluded.body,
                published_at=excluded.published_at
            """,
            doc,
        )
    return existing is None


def save_translation(uid: str, summary_ko: str, tone: str,
                     tone_reason: str, model: str) -> None:
    with tx() as conn:
        conn.execute(
            """UPDATE documents SET summary_ko=?, tone=?, tone_reason=?,
                                    translated_at=?, model=? WHERE uid=?""",
            (summary_ko, tone, tone_reason, _now(), model, uid),
        )


# ------------------------------------------------------------ run tracking

def start_run(collector: str) -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO collection_runs (collector, started_at, status) VALUES (?, ?, 'running')",
            (collector, _now()),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, status: str, rows: int = 0, message: str = "") -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE collection_runs SET finished_at=?, status=?, rows=?, message=? WHERE id=?",
            (_now(), status, rows, message[:500], run_id),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
