"""실행 엔트리포인트.

    python run.py                   # 서버 실행 (http://127.0.0.1:8000)
    python run.py --backfill        # 과거 이력 일괄 적재 후 종료
    python run.py --collect         # 1회 수집 후 종료
    python run.py --brief           # 브리핑 본문 미리보기 (발송 안 함)
    python run.py --send            # 브리핑을 텔레그램으로 즉시 발송
    python run.py --telegram-setup  # 봇 확인 + chat_id 찾기
    python run.py --translate       # 밀린 연준 문서를 한글로 요약
    python run.py --snapshot        # 공유용 HTML 생성
    python run.py --daily           # 전체 수집 + 브리핑 발송 (클라우드 아침 작업)
    python run.py --tick            # 주기가 된 수집기만 실행 (클라우드 30분 작업)
    python run.py --watch           # 새 지표 발표 확인 후 알림
    python run.py --watch-init      # 알림 기준선만 세우기 (첫 설정용)
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _prepare():
    from app.db import init_db
    from app.registry import sync_registry
    init_db()
    sync_registry()


def _telegram_setup() -> int:
    from app.config import TELEGRAM_CHAT_ID
    from app.notify import telegram

    info = telegram.me()
    print()
    print(f"  봇 확인 완료: {info.get('first_name')} (@{info.get('username')})")

    chats = telegram.discover_chats()
    if not chats:
        print()
        print("  chat_id 를 찾지 못했습니다.")
        print(f"  텔레그램에서 @{info.get('username')} 를 열고 아무 메시지나 한 번 보낸 뒤")
        print("  이 명령을 다시 실행하세요. (봇은 먼저 말을 걸 수 없습니다)")
        print()
        return 1

    print()
    print("  찾은 채팅:")
    for c in chats:
        mark = "   ← 현재 설정됨" if c["chat_id"] == TELEGRAM_CHAT_ID else ""
        print(f"    TELEGRAM_CHAT_ID={c['chat_id']}  ({c['type']}: {c['title']}){mark}")
    print()
    print("  위 값을 .env 의 TELEGRAM_CHAT_ID 에 넣으세요.")
    print()
    return 0


def main() -> int:
    args = set(sys.argv[1:])

    if "--watch" in args or "--watch-init" in args:
        _prepare()
        from app.collectors import run_one
        res = run_one("releases", backfill="--watch-init" in args)
        print()
        print(f"  {res.status}  알림 {res.rows}건  {res.message}")
        print()
        return 0

    if "--tick" in args:
        # 클라우드 30분 작업. 매번 새 머신이 뜨므로 수집기별 주기는 DB 기록으로 지킨다.
        _prepare()
        from app import scheduler
        from app.collectors import run_all, run_due
        from app.config import ENABLE_TELEGRAM

        if ENABLE_TELEGRAM and scheduler.brief_due():
            # 오늘 첫 브리핑 차례 — 전체를 새로 받은 뒤 보낸다
            print()
            print("=== 아침 브리핑 차례: 전체 수집 ===")
            for res in run_all():
                print(f"  {res.collector:10s} {res.status:8s} rows={res.rows:<8} {res.message}")
            scheduler._send_brief_only()
            from app.db import query
            row = query("""SELECT status, rows, message FROM collection_runs
                           WHERE collector = 'brief' ORDER BY id DESC LIMIT 1""")[0]
            print(f"  브리핑 {row['status']}  {row['rows']}곳 발송  {row['message'] or ''}")
            print()
            return 0 if row["status"] in ("ok", "skipped") else 1

        results = run_due()
        print()
        print(f"=== 주기 도래 수집기 {len(results)}개 ===")
        for res in results:
            print(f"  {res.collector:10s} {res.status:8s} rows={res.rows:<8} {res.message}")
        print()
        # 틱은 항상 성공으로 끝낸다. 30분마다 도는 작업을 일시적 네트워크 오류로
        # 실패 처리하면 GitHub 실패 메일이 쏟아진다. 개별 실패는 collection_runs 와
        # 보드의 지연 경고(⚠)로 드러난다.
        return 0

    if "--daily" in args:
        # 아침 작업: 전체 수집 후 브리핑 발송. 보드 발행은 클라우드 워크플로가 한다.
        _prepare()
        from app.collectors import run_all
        from app import scheduler

        print()
        print("=== 수집 ===")
        for res in run_all():
            print(f"  {res.collector:10s} {res.status:8s} rows={res.rows:<8} {res.message}")

        print()
        print("=== 브리핑 발송 ===")
        scheduler._send_brief_only()

        from app.db import query
        row = query("""SELECT status, rows, message FROM collection_runs
                       WHERE collector = 'brief' ORDER BY id DESC LIMIT 1""")[0]
        print(f"  {row['status']}  {row['rows']}곳 발송  {row['message'] or ''}")
        print()
        # 브리핑이 한 곳에도 못 갔으면 워크플로를 실패로 표시해 메일 알림을 받게 한다
        return 0 if row["status"] in ("ok", "skipped") else 1

    if "--telegram-setup" in args:
        _prepare()
        return _telegram_setup()

    if "--snapshot" in args:
        _prepare()
        from app.services import snapshot
        rest = [a for a in sys.argv[1:] if not a.startswith("--")]
        path = rest[0] if rest else "data/snapshot.html"
        out = snapshot.write(path)
        size = __import__("pathlib").Path(out).stat().st_size
        print()
        print(f"  생성 완료: {out}  ({size / 1024:.0f} KB)")
        print("  서버 없이 열리는 자체 완결형 HTML 입니다.")
        print()
        return 0

    if "--translate" in args:
        _prepare()
        from app.services import documents, translate
        if not translate.available():
            print()
            print("  ANTHROPIC_API_KEY 가 .env 에 설정되지 않았습니다.")
            print("  https://console.anthropic.com 에서 발급 후 넣어주세요.")
            print(f"  요약 대기 중인 문서: {documents.pending_count()}건")
            print()
            return 1
        print()
        print(f"  요약 대기: {documents.pending_count()}건")
        done, failed = translate.translate_pending(limit=20)
        print(f"  요약 완료: {done}건")
        for f in failed:
            print(f"  실패: {f}")
        print()
        return 0

    if "--brief" in args:
        _prepare()
        from app.services import brief
        print()
        print(brief.build_plain())
        print()
        return 0

    if "--send" in args:
        _prepare()
        from app.notify import telegram
        from app.services import brief
        if not telegram.configured():
            print()
            print("  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 .env 에 설정되지 않았습니다.")
            print("  python run.py --telegram-setup 으로 먼저 설정하세요.")
            print()
            return 1
        results = telegram.send(brief.build())
        print()
        for res in results:
            if res["ok"]:
                print(f"  발송 완료  chat={res['chat_id']}  (message_id={res['message_id']})")
            else:
                print(f"  발송 실패  chat={res['chat_id']}  {res['error']}")
        print()
        return 0 if all(r["ok"] for r in results) else 1

    if {"--backfill", "--collect"} & args:
        _prepare()
        from app.collectors import run_all
        results = run_all(backfill="--backfill" in args)
        print()
        print("=== 수집 결과 ===")
        for r in results:
            print(f"  {r.collector:10s} {r.status:8s} rows={r.rows:<8} {r.message}")
        if "--backfill" in args:
            from app import scheduler
            if scheduler.skip_brief_if_late():
                print("  브리핑   오늘은 건너뜀 (새로 시작했는데 브리핑 시각이 이미 지남)")
        return 0

    import uvicorn
    from app.config import HOST, PORT
    print()
    print(f"  대시보드: http://{HOST}:{PORT}")
    print()
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload="--reload" in args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
