"""연준·미 재무부 주요 인사 발언 수집기 (API 키 불필요).

소스
  - 연준 speeches.xml   : 의장/부의장/이사/지역 연은 총재 연설
  - 연준 press_all.xml  : FOMC 성명, 증언, 보도자료
  - 미 재무부 보도자료 페이지 : 장관 발언·성명 (RSS 가 막혀 있어 HTML 파싱)

톤 태깅은 키워드 휴리스틱이다. 해석 보조용이며 원문 확인을 대체하지 않는다.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from ..db import query_one, upsert_speech
from .base import Result, http_get

FED_SPEECHES = "https://www.federalreserve.gov/feeds/speeches.xml"
FED_PRESS = "https://www.federalreserve.gov/feeds/press_all.xml"
TREASURY_PRESS = "https://home.treasury.gov/news/press-releases"

# 연준 주요 인사 → 직책 (소문자 성씨 기준)
FED_ROLES = {
    "powell": "연준 의장",
    "jefferson": "연준 부의장",
    "bowman": "연준 감독담당 부의장",
    "barr": "연준 이사",
    "waller": "연준 이사",
    "cook": "연준 이사",
    "kugler": "연준 이사",
    "miran": "연준 이사",
    "williams": "뉴욕 연은 총재",
    "goolsbee": "시카고 연은 총재",
    "bostic": "애틀랜타 연은 총재",
    "daly": "샌프란시스코 연은 총재",
    "logan": "댈러스 연은 총재",
    "kashkari": "미니애폴리스 연은 총재",
    "schmid": "캔자스시티 연은 총재",
    "musalem": "세인트루이스 연은 총재",
    "hammack": "클리블랜드 연은 총재",
    "collins": "보스턴 연은 총재",
    "harker": "필라델피아 연은 총재",
    "barkin": "리치먼드 연은 총재",
    "warsh": "연준 의장",
}

HAWKISH = [
    "tighten", "tightening", "restrictive", "inflation risk", "upside risk",
    "higher for longer", "vigilant", "premature", "overheat", "persistent inflation",
    "price pressures", "hike", "raise rates", "patient on cuts",
]
DOVISH = [
    "cut", "cutting", "accommodative", "easing", "ease policy", "downside risk",
    "softening", "moderating", "cooling", "disinflation", "slack",
    "labor market weakness", "normalize", "lower rates",
]


def _uid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:20]


def _tone(text: str) -> tuple[str, float]:
    low = text.lower()
    h = sum(low.count(k) for k in HAWKISH)
    d = sum(low.count(k) for k in DOVISH)
    if h == d:
        return "neutral", 0.0
    score = (h - d) / max(h + d, 1)
    return ("hawkish" if score > 0 else "dovish"), round(score, 2)


def _parse_pubdate(raw: str) -> str:
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001 - 포맷이 어긋나면 현재 시각으로 대체
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _split_speaker(title: str) -> tuple[str, str]:
    """'Waller, The Economic Outlook' → ('Waller', 'The Economic Outlook')

    연준 연설 RSS 는 항상 '성씨, 제목' 형태다. 알려진 인물이 아니어도
    앞부분이 1~2 단어의 고유명사면 발언자로 본다 (신임 인사 대응).
    """
    if "," not in title:
        return "", title.strip()
    head, _, rest = title.partition(",")
    head, rest = head.strip(), rest.strip()
    if not rest:
        return "", title.strip()
    if head.lower() in FED_ROLES:
        return head, rest
    words = head.split()
    if 1 <= len(words) <= 2 and all(w[:1].isupper() for w in words):
        return head, rest
    return "", title.strip()


def _speech_body(url: str) -> str:
    """연설 원문 본문. 톤 태깅 정확도를 위해 제목만이 아니라 본문을 본다."""
    soup = BeautifulSoup(http_get(url, retries=2).text, "lxml")
    node = soup.select_one("#article, div.col-xs-12.col-sm-8.col-md-8") or soup.body
    return node.get_text(" ", strip=True) if node else ""


def _fetch_rss(url: str, org: str, default_role: str, *, read_body: bool = False) -> int:
    soup = BeautifulSoup(http_get(url).content, "xml")
    count = 0
    for item in soup.find_all("item"):
        title = (item.title.get_text(strip=True) if item.title else "").strip()
        if not title:
            continue
        link = item.link.get_text(strip=True) if item.link else ""
        desc = item.description.get_text(strip=True) if item.description else ""
        pub = _parse_pubdate(item.pubDate.get_text(strip=True) if item.pubDate else "")
        speaker, clean_title = _split_speaker(title)
        role = FED_ROLES.get(speaker.lower(), default_role) if speaker else default_role

        uid = _uid(org, link or title)
        existing = query_one("SELECT tone, tone_score FROM speeches WHERE uid = ?", (uid,))

        body = ""
        # 본문은 신규 항목만 1회 받아온다 (이미 저장된 건 재요청하지 않는다)
        if read_body and link and existing is None:
            try:
                body = _speech_body(link)
            except Exception:  # noqa: BLE001 - 본문 실패해도 제목 기반으로 저장
                body = ""

        if existing is not None and read_body and not body:
            # 본문 없이 다시 태깅하면 이미 계산해 둔 톤이 제목 기준으로 덮어써진다.
            # 재수집이 정보를 잃지 않도록 기존 값을 그대로 유지한다.
            tone, score = existing["tone"], existing["tone_score"]
        else:
            tone, score = _tone(f"{clean_title} {desc} {body}")
        upsert_speech(dict(
            uid=uid,
            published_at=pub, speaker=speaker or org, role=role, org=org,
            title=clean_title, url=link, summary=desc[:600],
            tone=tone, tone_score=score,
        ))
        count += 1
    return count


_SLUG_RE = re.compile(r"^/news/press-releases/[a-z0-9\-]+/?$")
TREASURY_PAGES = [
    (TREASURY_PRESS + "/statements-remarks", "재무장관 발언·성명"),
    (TREASURY_PRESS, "재무부 보도자료"),
]


def _fetch_treasury() -> int:
    """재무부 목록 페이지 파싱.

    각 항목은 h3.featured-stories__headline > a 가 제목·링크이고,
    같은 블록의 <time datetime> 이 발표일이다.
    """
    count = 0
    for url, role in TREASURY_PAGES:
        soup = BeautifulSoup(http_get(url).text, "lxml")
        for headline in soup.select("h3.featured-stories__headline a[href]"):
            href = headline["href"].split("?")[0]
            if not _SLUG_RE.match(href):
                continue
            title = headline.get_text(" ", strip=True)
            if len(title) < 15:
                continue
            block = headline.find_parent("div")
            pub = datetime.now(timezone.utc).isoformat(timespec="seconds")
            time_el = block.select_one("time[datetime]") if block else None
            if time_el:
                try:
                    pub = datetime.fromisoformat(
                        time_el["datetime"].replace("Z", "+00:00")
                    ).isoformat(timespec="seconds")
                except ValueError:
                    pass
            speaker = "美 재무장관" if "secretary" in title.lower() else "美 재무부"
            tone, score = _tone(title)
            upsert_speech(dict(
                uid=_uid("treasury", href.rstrip("/")),
                published_at=pub, speaker=speaker, role=role,
                org="U.S. Treasury", title=title,
                url="https://home.treasury.gov" + href, summary="",
                tone=tone, tone_score=score,
            ))
            count += 1
    return count


def collect() -> Result:
    total = 0
    failed: list[str] = []
    tasks = [
        ("fed-speeches", lambda: _fetch_rss(FED_SPEECHES, "Federal Reserve",
                                            "연준 인사", read_body=True)),
        ("fed-press", lambda: _fetch_rss(FED_PRESS, "Federal Reserve", "연준 보도자료")),
        ("treasury", _fetch_treasury),
    ]
    for name, fn in tasks:
        try:
            total += fn()
        except Exception as exc:  # noqa: BLE001 - 소스 단위 격리
            failed.append(f"{name}({type(exc).__name__})")

    if total == 0:
        return Result("speeches", "error", 0, "전량 실패: " + ", ".join(failed))
    return Result("speeches", "ok", total, f"실패: {', '.join(failed)}" if failed else "")


def backfill() -> Result:
    return collect()
