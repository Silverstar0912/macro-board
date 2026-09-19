"""텔레그램 봇 발송.

봇 토큰과 채팅 ID 가 없으면 발송을 시도하지 않고 skipped 로 남긴다.
대시보드 본체는 텔레그램 설정 여부와 무관하게 동작해야 한다.
"""
from __future__ import annotations

import logging

import requests

from ..config import (HTTP_TIMEOUT, TELEGRAM_BOT_TOKEN,
                      TELEGRAM_CHAT_ID, TELEGRAM_CHAT_IDS)

log = logging.getLogger("telegram")

API = "https://api.telegram.org/bot{token}/{method}"
# 텔레그램 메시지 상한은 4096자. 여유를 두고 자른다.
MAX_LEN = 3900


def configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS)


def _call(method: str, payload: dict | None = None, token: str | None = None) -> dict:
    token = token or TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다")
    resp = requests.post(API.format(token=token, method=method),
                         json=payload or {}, timeout=HTTP_TIMEOUT)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"텔레그램 {method} 실패: "
                           f"{data.get('error_code')} {data.get('description')}")
    return data["result"]


def send_one(text: str, chat_id: str) -> dict:
    """HTML 포맷 메시지를 한 곳에 발송."""
    if len(text) > MAX_LEN:
        text = text[:MAX_LEN] + "\n…(생략)"
    return _call("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })


def send(text: str, chat_id: str | None = None) -> list[dict]:
    """설정된 모든 대상에 발송한다.

    한 곳이 실패해도 나머지는 계속 보낸다 — 그룹방에서 봇이 쫓겨났다고
    개인 브리핑까지 끊기면 안 된다. 성공/실패를 함께 담아 돌려준다.
    """
    targets = [chat_id] if chat_id else TELEGRAM_CHAT_IDS
    if not targets:
        raise RuntimeError("TELEGRAM_CHAT_ID 가 설정되지 않았습니다")

    results = []
    for target in targets:
        try:
            res = send_one(text, target)
            results.append({"chat_id": target, "ok": True,
                            "message_id": res.get("message_id")})
        except Exception as exc:  # noqa: BLE001 - 대상 단위로 격리
            log.warning("[%s] 발송 실패: %s", target, exc)
            results.append({"chat_id": target, "ok": False, "error": str(exc)})
    return results


def me(token: str | None = None) -> dict:
    """봇 토큰 확인용 — 봇 이름/username 을 돌려준다."""
    return _call("getMe", token=token)


def discover_chats(token: str | None = None) -> list[dict]:
    """봇에게 온 메시지에서 chat_id 를 찾아낸다.

    사용자가 봇과의 대화창에 아무 메시지나 한 번 보낸 뒤 호출하면
    그 채팅의 id 가 나온다. (봇은 먼저 말을 걸 수 없다)
    """
    updates = _call("getUpdates", {"limit": 20}, token=token)
    seen: dict[str, dict] = {}
    for upd in updates:
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat")
        if not chat:
            continue
        seen[str(chat["id"])] = {
            "chat_id": str(chat["id"]),
            "type": chat.get("type"),
            "title": chat.get("title") or chat.get("username")
                     or " ".join(filter(None, [chat.get("first_name"),
                                               chat.get("last_name")])),
        }
    return list(seen.values())
