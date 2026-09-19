"""FastAPI 애플리케이션 — REST API + 대시보드 정적 파일 서빙."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import scheduler
from .collectors import COLLECTORS, run_all, run_one
from .config import ENABLE_SCHEDULER, STATIC_DIR
from .db import init_db
from .registry import sync_registry
from .services import calendar as cal_svc
from .services import indicators as ind_svc
from .services import brief as brief_svc
from .services import documents as doc_svc
from .services import forecasts as fc_svc
from .services import speeches as sp_svc
from .notify import telegram

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sync_registry()
    if ENABLE_SCHEDULER:
        scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="거시경제지표 대시보드", version="1.0", lifespan=lifespan)


# ------------------------------------------------------------------ 지표

@app.get("/api/summary")
def api_summary():
    return {"indicators": ind_svc.summary()}


@app.get("/api/indicators")
def api_indicators():
    return {"indicators": ind_svc.catalog()}


@app.get("/api/series")
def api_series(codes: str = Query(..., description="쉼표로 구분한 지표 코드"),
               range: str = Query("5Y", description="1Y|3Y|5Y|10Y|MAX")):
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:6]
    return ind_svc.series(code_list, range)


@app.get("/api/curve")
def api_curve():
    return ind_svc.curve()


@app.get("/api/forecasts")
def api_forecasts():
    """다음 발표 예상치 + 연도별 공식 전망."""
    return {"next": fc_svc.all_next(), "yearly": fc_svc.yearly_table()}


@app.get("/api/documents")
def api_documents(limit: int = 10, doc_type: str | None = None):
    """연준 회의록·성명 + 한글 요약."""
    from .services import translate as tr
    return {"documents": doc_svc.feed(limit, doc_type),
            "pending": doc_svc.pending_count(),
            "translator_ready": tr.available()}


@app.get("/api/documents/{uid:path}")
def api_document(uid: str):
    doc = doc_svc.get(uid)
    if not doc:
        return JSONResponse({"error": "문서를 찾을 수 없습니다"}, status_code=404)
    return doc


@app.post("/api/translate")
def api_translate(background: BackgroundTasks, limit: int = 3):
    """밀린 문서를 한글로 요약한다."""
    from .services import translate as tr
    if not tr.available():
        return JSONResponse(
            {"error": "ANTHROPIC_API_KEY 가 설정되지 않았습니다"}, status_code=400)
    background.add_task(tr.translate_pending, limit)
    return {"queued": limit}


# ---------------------------------------------------------------- 캘린더

@app.get("/api/calendar")
def api_calendar(start: str | None = None, end: str | None = None,
                 country: str | None = None, min_importance: int = 1):
    return {"events": cal_svc.events(start, end, country, min_importance),
            "upcoming": cal_svc.upcoming(7)}


@app.get("/api/calendar.ics")
def api_calendar_ics(country: str | None = None, min_importance: int = 2):
    items = cal_svc.events(country=country, min_importance=min_importance)
    return PlainTextResponse(
        cal_svc.to_ics(items),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="macro-calendar.ics"'},
    )


# ----------------------------------------------------------------- 발언

@app.get("/api/speeches")
def api_speeches(limit: int = 40, tone: str | None = None, org: str | None = None):
    return {"speeches": sp_svc.feed(limit, tone, org),
            "tone_stats": sp_svc.tone_stats(30)}


# ------------------------------------------------------------ 운영/상태

@app.get("/api/status")
def api_status():
    return {"runs": ind_svc.status(), "next_runs": scheduler.next_runs(),
            "scheduler_enabled": ENABLE_SCHEDULER}


@app.post("/api/refresh")
def api_refresh(background: BackgroundTasks,
                collector: str | None = None, backfill: bool = False):
    """수동 즉시 수집. collector 미지정 시 전체 실행."""
    if collector and collector not in COLLECTORS:
        return JSONResponse({"error": f"알 수 없는 수집기: {collector}"}, status_code=400)
    if collector:
        background.add_task(run_one, collector, backfill=backfill)
        return {"queued": [collector], "backfill": backfill}
    background.add_task(run_all, backfill=backfill)
    return {"queued": list(COLLECTORS), "backfill": backfill}


# ------------------------------------------------------------- 텔레그램

@app.get("/api/brief")
def api_brief():
    """발송될 브리핑 본문 미리보기."""
    return {"html": brief_svc.build(), "text": brief_svc.build_plain(),
            "telegram_configured": telegram.configured()}


@app.post("/api/telegram/send")
def api_telegram_send():
    """지금 즉시 브리핑을 봇으로 보낸다."""
    if not telegram.configured():
        return JSONResponse(
            {"error": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 설정되지 않았습니다"},
            status_code=400)
    try:
        results = telegram.send(brief_svc.build())
    except Exception as exc:  # noqa: BLE001 - 사용자에게 원인을 그대로 보여준다
        return JSONResponse({"error": str(exc)}, status_code=502)
    return {"sent": sum(1 for r in results if r["ok"]), "results": results}


@app.get("/api/telegram/chats")
def api_telegram_chats():
    """봇에게 온 메시지에서 chat_id 를 찾아준다 (최초 설정용)."""
    try:
        return {"chats": telegram.discover_chats()}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=502)


# --------------------------------------------------------------- 정적 파일

@app.middleware("http")
async def no_cache_static(request, call_next):
    """대시보드 자산은 캐시하지 않는다.

    JS/CSS 를 고쳤는데 브라우저가 옛 파일을 계속 쓰면 원인을 찾기 어렵다.
    로컬 단일 사용자용이라 캐시로 얻을 이득도 없다.
    """
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
