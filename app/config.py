"""애플리케이션 설정. .env 파일 또는 환경변수에서 API 키를 읽는다."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = DATA_DIR / "macro.db"

DATA_DIR.mkdir(exist_ok=True)


def _load_dotenv() -> None:
    """의존성 없이 .env 를 읽어 os.environ 에 채운다 (기존 값은 유지)."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

# --- API 키 (없어도 동작한다. 없는 소스는 건너뛴다) ---
FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
ECOS_API_KEY = os.environ.get("ECOS_API_KEY", "").strip()

# --- 네트워크 ---
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "30"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
HTTP_HEADERS = {"User-Agent": USER_AGENT, "Accept": "*/*"}

# --- 연준 문서 한글 요약 (선택) ---
# https://console.anthropic.com 에서 발급. 없으면 원문만 수집한다.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
TRANSLATE_MODEL = os.environ.get("TRANSLATE_MODEL", "claude-opus-5").strip()

# --- 텔레그램 봇 (선택) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
# 쉼표로 여러 곳에 동시 발송 (개인 + 그룹방 등)
TELEGRAM_CHAT_IDS = [c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()]
# 아침 브리핑 발송 시각 (Asia/Seoul, HH:MM)
BRIEF_TIME = os.environ.get("BRIEF_TIME", "07:30").strip()
# 로컬 서버의 아침 브리핑 / 발표 알림 스위치.
# 클라우드(GitHub Actions)가 발송을 맡은 뒤로는 로컬에서 끄지 않으면
# 같은 메시지가 두 번 간다. 로컬 .env 에서 0 으로 둔다.
ENABLE_TELEGRAM = os.environ.get("ENABLE_TELEGRAM", "1") != "0"
ENABLE_ALERTS = os.environ.get("ENABLE_ALERTS", "1") != "0"

# --- 서버 ---
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))


def _lan_ip() -> str:
    """이 PC 의 LAN IP. 텔레그램 링크를 휴대폰에서 열려면 127.0.0.1 로는 안 된다.

    실제로 패킷을 보내지 않는 UDP connect 로 라우팅 테이블이 고르는
    출발지 주소를 확인한다. 실패하면 루프백으로 되돌린다.
    """
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


# 브리핑에 넣을 대시보드 주소. 비워두면 LAN IP 로 자동 구성한다.
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "").strip().rstrip("/")
if not DASHBOARD_URL:
    DASHBOARD_URL = f"http://{_lan_ip()}:{PORT}"

# 외부에서 열리는 공유용 스냅샷 주소 (선택)
SNAPSHOT_URL = os.environ.get("SNAPSHOT_URL", "").strip()

# --- 스케줄 (초 단위) ---
SCHEDULE_SECONDS = {
    "treasury": 60 * 60,        # 1시간
    "fred": 60 * 60 * 6,        # 6시간
    "ecos": 60 * 60 * 6,        # 6시간
    "yahoo": 60 * 30,           # 30분 (시장 시세라 자주 본다)
    "releases": 60 * 30,        # 30분 (발표 직후 알림)
    "speeches": 60 * 60,        # 1시간
    "calendar": 60 * 60 * 12,   # 12시간
    "forecast": 60 * 60 * 6,    # 6시간 (나우캐스팅은 매 영업일 갱신)
    "minutes": 60 * 60 * 6,     # 6시간 (회의록은 회의 3주 뒤 공개)
    "publish": 60 * 60 * 6,     # 6시간 (브리핑 직전에도 한 번 더 올린다)
    "market": 60 * 60 * 6,      # 6시간
}

# 스케줄러 자동 실행 여부
ENABLE_SCHEDULER = os.environ.get("ENABLE_SCHEDULER", "1") != "0"
