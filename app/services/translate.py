"""연준 문서 한글 요약.

Claude API 로 FOMC 회의록·성명을 읽고 한글 핵심 요약을 만든다.
회의록은 6천 단어 안팎이라 전문을 그대로 옮기면 읽히지 않는다.
정책 결정 · 물가 · 고용 · 향후 지침 네 축으로 압축하고, 매파/비둘기파 판단을
근거와 함께 붙인다.

ANTHROPIC_API_KEY 가 없으면 아무 것도 하지 않는다 — 원문은 이미 저장돼 있으므로
나중에 키를 넣으면 그때 밀린 문서까지 소급해서 요약한다.
"""
from __future__ import annotations

import json
import logging

from ..config import ANTHROPIC_API_KEY, TRANSLATE_MODEL
from ..db import query, save_translation

log = logging.getLogger("translate")

SYSTEM = """당신은 한국 기관투자자를 위해 연준 문서를 정리하는 거시경제 애널리스트입니다.

원칙:
- 원문에 있는 내용만 씁니다. 원문에 없는 수치·전망을 만들어내지 않습니다.
- 통화정책 용어는 아래 표기를 그대로 씁니다.
  · maintain/hold the target range → 금리 **동결** ("동점" 은 오역입니다)
  · unanimous → 만장일치,  dissent → 반대표/소수의견
  · dot plot → 점도표,  balance sheet runoff → 대차대조표 축소
  · accommodative → 완화적,  restrictive → 긴축적
  · basis points → bp,  target range → 목표범위
  · easing bias → 완화 편향,  forward guidance → 선제 지침
- 위원들의 의견이 갈린 대목은 갈렸다는 사실 자체가 중요하므로 반드시 남깁니다.
- 단정적 해석 대신 원문이 말한 강도를 그대로 옮깁니다
  ("several" 은 '몇몇', "most" 는 '대다수' 로 구분).

반드시 아래 JSON 스키마로만 답합니다. 다른 텍스트를 덧붙이지 마세요.
{
  "headline": "한 문장 요약 (60자 이내)",
  "policy": "정책 결정과 금리 관련 논의 (3~5문장)",
  "inflation": "물가 관련 논의 (2~4문장)",
  "labor": "고용·경기 관련 논의 (2~4문장)",
  "guidance": "향후 정책 방향에 대한 시사점 (2~4문장)",
  "dissent": "이견·소수의견이 있었다면 그 내용, 없으면 빈 문자열",
  "tone": "hawkish | dovish | neutral 중 하나",
  "tone_reason": "그렇게 판단한 근거 (1~2문장)"
}"""


def available() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def summarize(title: str, body: str) -> dict:
    """문서 하나를 한글 요약한다. 실패하면 예외를 올린다."""
    client = _client()
    prompt = (f"다음은 연준이 공개한 문서 원문입니다.\n\n"
              f"제목: {title}\n\n"
              f"---- 원문 시작 ----\n{body}\n---- 원문 끝 ----\n\n"
              f"위 스키마에 맞춰 한글로 정리해 주세요.")

    # 입력이 길어 스트리밍으로 받는다 (비스트리밍은 HTTP 타임아웃에 걸릴 수 있다)
    with client.messages.stream(
        model=TRANSLATE_MODEL,
        max_tokens=8000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError(f"모델이 요약을 거부했습니다: {message.stop_details}")

    text = "".join(b.text for b in message.content if b.type == "text").strip()
    # 모델이 코드펜스를 붙이는 경우가 있어 벗겨낸다
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def render_ko(data: dict) -> str:
    """요약 JSON → 사람이 읽는 한글 본문."""
    blocks = [
        ("정책 결정", data.get("policy")),
        ("물가", data.get("inflation")),
        ("고용·경기", data.get("labor")),
        ("향후 방향", data.get("guidance")),
        ("이견", data.get("dissent")),
    ]
    parts = [data.get("headline", "").strip()]
    for label, text in blocks:
        if text and text.strip():
            parts.append(f"[{label}]\n{text.strip()}")
    return "\n\n".join(p for p in parts if p)


def translate_pending(limit: int = 3) -> tuple[int, list[str]]:
    """아직 요약되지 않은 문서를 처리한다. (성공 건수, 실패 메시지)"""
    if not available():
        return 0, ["ANTHROPIC_API_KEY 미설정"]

    rows = query(
        """SELECT uid, title, body FROM documents
           WHERE summary_ko IS NULL AND body IS NOT NULL AND length(body) > 500
           ORDER BY meeting_date DESC LIMIT ?""",
        (limit,),
    )
    done, failed = 0, []
    for row in rows:
        try:
            data = summarize(row["title"], row["body"])
            save_translation(row["uid"], render_ko(data),
                             data.get("tone", "neutral"),
                             data.get("tone_reason", ""), TRANSLATE_MODEL)
            done += 1
            log.info("요약 완료: %s", row["title"][:50])
        except Exception as exc:  # noqa: BLE001 - 문서 단위로 격리
            failed.append(f"{row['title'][:30]}({type(exc).__name__})")
            log.warning("요약 실패 %s: %s", row["title"][:40], exc)
    return done, failed
