# 거시경제지표 대시보드

채권금리 · CPI · 기준금리 등 거시지표를 자동 수집해 한 화면에서 보여주는 대시보드.
과거 시계열, 발표일정 캘린더, 연준·미 재무부 주요 인사 발언까지 함께 다룬다.

기획 내용은 [기획서.md](기획서.md) 참고.

---

## 빠른 시작

```bash
pip install -r requirements.txt
python run.py
```

브라우저에서 http://127.0.0.1:8500 접속. 서버가 뜨면 스케줄러가 즉시 1회 수집한다.

`HOST=0.0.0.0` 으로 띄우므로 같은 Wi-Fi 의 휴대폰·태블릿에서도 열린다
(`http://<이 PC의 LAN IP>:8500`). 이 PC 에서만 쓰려면 `.env` 의 `HOST` 를
`127.0.0.1` 로 바꾼다. 포트는 8000 이 다른 용도로 쓰이고 있어 8500 을 기본으로 한다.

### 과거 이력 백필 (최초 1회 권장)

```bash
python run.py --backfill
```

미 국채 수익률곡선 15년치(약 4.6만 관측치)를 적재한다. 2~3분 걸린다.

### 수집만 1회 실행

```bash
python run.py --collect
```

---

## API 키 설정 (선택)

키가 없어도 **미 국채금리 · 수익률곡선 · FOMC 일정 · 연준/재무부 발언**은 정상 동작한다.
키를 넣으면 CPI·기준금리·한국 지표·미국 발표일정이 추가로 활성화된다.

`.env.example` 를 `.env` 로 복사한 뒤 값을 채운다.

| 키 | 발급처 | 활성화되는 항목 |
|----|--------|----------------|
| `FRED_API_KEY` | https://fredaccount.stlouisfed.org/apikeys | 미국 기준금리(EFFR), CPI, 근원 CPI, 근원 PCE, 기대인플레, 실업률, 비농업고용, S&P500, WTI, 달러지수, 원/달러, **미국 지표 발표일정** |
| `ECOS_API_KEY` | https://ecos.bok.or.kr/api/#/AuthKeyApply | 한국 기준금리, 국고채 3Y·10Y, 소비자물가 |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 @BotFather | 아침 브리핑 텔레그램 발송 |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com | FOMC 회의록·성명 한글 요약 |

키가 없는 지표는 KPI 카드에 "API 키 필요"로 표시되며, 수집기 배지는 `건너뜀` 상태가 된다.

---

## 클라우드 자동 실행 (GitHub Actions)

수집·발표 알림·아침 브리핑·공유 보드 발행은 **GitHub Actions 에서 돈다.**
PC 가 꺼져 있어도 동작하고 비용은 들지 않는다 (공개 저장소는 Actions 무료).

`.github/workflows/macro.yml` 이 30분마다(매시 25분·55분) 한 번 틱을 돈다.

| 틱마다 하는 일 | |
|---|---|
| 주기가 된 수집기 실행 | 수집기별 주기(`SCHEDULE_SECONDS`)는 DB 의 실행 기록으로 지킨다 |
| 새 지표 발표 알림 | 새 기간이 생기면 텔레그램으로 즉시 |
| 아침 브리핑 | 07:25 이후 그날 첫 틱이 보낸다 |
| 공유 보드 배포 | GitHub Pages 에 새로 올린다 |

**아침 브리핑을 별도 예약으로 나누지 않은 이유** — 같은 실행 그룹에서 대기 중인
실행은 새 실행이 오면 취소된다. 브리핑 실행이 틱에 밀려 취소되지 않도록 모든 실행을
같은 틱으로 만들고, "브리핑 시각이 지났고 오늘 아직 안 보냈으면 보낸다" 로 판단한다.
어느 틱이 밀리거나 취소돼도 다음 틱이 이어받는다.

**DB 는 저장소에 올리지 않는다.** 매 실행이 끝나면 Actions 캐시에 저장하고 다음
실행이 이어받는다. 캐시가 없으면(최초 실행·장기 미사용) 전체 이력부터 다시 받으며,
이때 알림 기준선도 새로 세워 과거 발표가 무더기로 날아가지 않게 한다.

### 최초 설정 (1회)

1. **비밀값 등록** — 저장소 Settings → Secrets and variables → Actions 에
   `FRED_API_KEY`, `ECOS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
   `ANTHROPIC_API_KEY` 를 넣는다. 코드에는 키가 없다.
2. **Pages 소스** — Settings → Pages → Source 를 **GitHub Actions** 로 바꾼다.
3. Actions 탭 → 거시 대시보드 → Run workflow 로 한 번 돌려 확인한다.

### 알아둘 것

- GitHub 예약 실행은 몇 분씩 늦게 뜬다. 브리핑은 대체로 07:25~07:45 사이에 온다.
- 공개 저장소의 예약 실행은 60일간 활동이 없으면 GitHub 이 끈다. 워크플로가
  달마다 `.github/heartbeat` 를 커밋해 이를 막는다.
- 아침 브리핑이 한 곳에도 못 가면 실행이 실패로 표시되고 GitHub 이 메일로 알린다.
  30분 틱의 일시적 수집 오류는 실패로 치지 않는다 (메일 폭주 방지). 대신
  갱신이 멈춘 지표는 보드와 브리핑에 ⚠ 로 드러난다.

### 로컬 서버

`python run.py` 는 이제 **실시간 대시보드를 볼 때만** 띄우면 된다. 클라우드가 발송을
맡으므로 로컬 `.env` 에서 `ENABLE_TELEGRAM=0`, `ENABLE_ALERTS=0` 으로 두어야
같은 메시지가 두 번 가지 않는다. 로컬 DB 와 클라우드 DB 는 따로 논다.

---

## 지표 발표 즉시 알림

CPI·PPI·고용처럼 장을 움직이는 지표는 발표 직후에 알아야 의미가 있다.
30분마다 감시 대상의 최근 관측치만 가볍게 확인하고, 새 기간이 생기면 알린다.

감시 대상: 미국 CPI·근원 CPI·PPI·근원 PPI·근원 PCE·실업률·비농업고용·기준금리,
한국 소비자물가·기준금리 (`app/collectors/releases.py` 의 `WATCHED`).

알림에는 이전 값 대비 변화와, 예상치가 있으면 상회/하회 판정이 함께 실린다.

```
🔔 미국 소비자물가(CPI) 발표
· 2026.08  3.45%  (▲ 이전 3.30%)
· 예상 3.38% → 상회 (+0.07)
예상치 출처: 클리블랜드 연은 나우캐스팅
```

첫 실행은 기준선만 세우고 알리지 않는다 — 이미 나와 있던 값이 새 발표처럼
무더기로 날아가지 않도록. 기준선을 다시 세우려면 `python run.py --watch-init`.

미국 정책금리는 일별 계열이라 매일 값이 바뀌므로, 0.10%p 이상 움직였을 때만
발표로 본다.

---

## 텔레그램 아침 브리핑

매일 아침(기본 07:30 KST) 주요 KPI와 향후 7일 발표일정을 텔레그램으로 보낸다.

### 봇 만들기

1. 텔레그램에서 **@BotFather** 를 열고 `/newbot` 전송
2. 봇 이름과 `_bot` 으로 끝나는 username 을 입력하면 토큰이 나온다
3. 토큰을 `.env` 의 `TELEGRAM_BOT_TOKEN` 에 넣는다
4. 방금 만든 봇과의 대화창에 아무 메시지나 한 번 보낸다 (봇은 먼저 말을 걸 수 없다)
5. 아래 명령으로 `chat_id` 를 찾아 `.env` 의 `TELEGRAM_CHAT_ID` 에 넣는다

```bash
python run.py --telegram-setup
```

### 확인

```bash
python run.py --brief    # 발송 없이 본문만 미리보기
python run.py --send     # 지금 즉시 발송
```

서버를 띄워두면 매일 `BRIEF_TIME` 에 자동 발송된다.
`ENABLE_TELEGRAM=0` 이면 발송하지 않는다.

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `TELEGRAM_BOT_TOKEN` | — | BotFather 발급 토큰 |
| `TELEGRAM_CHAT_ID` | — | 받을 채팅 ID (개인/그룹/채널) |
| `BRIEF_TIME` | `07:30` | 발송 시각 (Asia/Seoul) |
| `ENABLE_TELEGRAM` | `1` | `0` 이면 발송 중단 |
| `DASHBOARD_URL` | 자동 | 브리핑에 넣을 대시보드 주소. 비우면 LAN IP 로 자동 구성 |

브리핑 맨 아래에 대시보드 바로가기 링크가 붙는다. 서버가 루프백에만 바인딩돼 있으면
휴대폰에서 열리지 않으므로, 그 경우 링크 아래에 안내 문구가 함께 나간다.

---

## 공유용 보드 (GitHub Pages)

로컬 대시보드는 LAN 안에서만 열린다. 스터디 그룹처럼 밖에 있는 사람과 나누려면
서버가 필요 없는 한 장짜리 HTML 을 GitHub Pages 에 올린다.
클로드 아티팩트는 열람자에게도 로그인을 요구하지만, GitHub Pages 는 누구나 열 수 있다.

주소: https://Silverstar0912.github.io/macro-board/ — 텔레그램 브리핑 링크도 이곳을 가리킨다.

클라우드 워크플로가 30분마다 새로 만들어 배포한다. 따로 할 일은 없다.
페이지는 생성 시점의 값을 담은 정적 스냅샷이므로 상단에 기준 시각을 표시한다.

손으로 만들어 보려면 `python run.py --snapshot 경로.html` (배포는 하지 않는다).

---

## 화면 구성

| 탭 | 내용 |
|----|------|
| **지표 현황** | 카테고리별 KPI 카드 — 최신값, 전일/전기 대비(bp), 1년 전 대비 |
| **과거 추이** | 지표 최대 4개 오버레이, 기간 토글 1Y/3Y/5Y/10Y/MAX, 단위가 다르면 우측 축 분리 |
| **수익률곡선** | 미 국채 곡선 최신 vs 1개월 전 vs 1년 전 비교 |
| **발표일정** | 다가오는 7일 리스트 + 월간 캘린더, 국가·중요도 필터, iCal 내보내기 |
| **주요 발언** | 연준·재무부 인사 발언 피드, 매파/비둘기파 톤 배지 및 30일 분포 |
| **연준 회의록** | FOMC 회의록·성명 한글 요약 (정책·물가·고용·향후 방향 + 이견) |

상단 우측 배지는 수집기별 최근 실행 상태(정상/실패/건너뜀)이며, `지금 갱신` 으로 즉시 수집한다.

---

## 데이터 소스

| 소스 | 수집 대상 | 키 |
|------|----------|----|
| U.S. Treasury Daily Yield Curve | 국채 1M~30Y 일별 금리 | 불필요 |
| Yahoo Finance | 환율·지수·유가·금·은·구리 시장 시세 | 불필요 |
| Federal Reserve `speeches.xml` / `press_all.xml` | 연준 인사 연설·보도자료 | 불필요 |
| Federal Reserve FOMC Calendar | FOMC 회의 일정, 회의록·성명 원문 | 불필요 |
| 클리블랜드 연은 인플레이션 나우캐스팅 | 다음 CPI/PCE 발표 예상치 | 불필요 |
| 한국은행 통화정책방향 결정회의 | 금통위 일정 (연 8회) | 불필요 |
| home.treasury.gov 보도자료 | 재무장관 발언·성명 | 불필요 |
| FRED API | 물가·고용·정책금리·시장지표, 미국 발표일정 | 필요 |
| 한국은행 ECOS API | 한국 기준금리·국고채·소비자물가 | 필요 |

> BLS 사이트는 자동 접근을 403 으로 차단하므로 미국 지표 발표일은 FRED 릴리스 캘린더로 받는다.
> 일정을 임의로 추정해 채우지 않는다.

---

## 자동 수집 주기

`app/config.py` 의 `SCHEDULE_SECONDS` 에서 조정한다.

| 수집기 | 기본 주기 |
|--------|----------|
| treasury | 1시간 |
| speeches | 1시간 |
| fred / ecos | 6시간 |
| calendar | 12시간 |
| yahoo | 30분 |
| forecast | 6시간 |
| minutes | 6시간 |

`ENABLE_SCHEDULER=0` 을 주면 자동 수집 없이 수동(`지금 갱신`, `/api/refresh`)으로만 동작한다.

---

## FOMC 회의록 한글 요약

FOMC 회의록은 회의 3주 뒤, 성명은 회의 당일 공개된다. 캘린더를 6시간마다 훑어
새 문서가 올라오면 원문을 저장하고 Claude API 로 한글 요약을 만든다.

**원문 수집과 번역은 분리돼 있다.** `ANTHROPIC_API_KEY` 가 없어도 원문은 계속 쌓이고,
나중에 키를 넣으면 밀린 문서까지 소급해서 요약한다.

```bash
python run.py --translate    # 밀린 문서를 한글로 요약
```

요약은 원문(5~7천 단어)을 **정책 결정 / 물가 / 고용·경기 / 향후 방향** 네 축으로
압축하고, 이견(소수의견)과 매파·비둘기파 판단을 근거와 함께 붙인다.

프롬프트에 세 가지 제약을 걸어 두었다.

- 원문에 없는 수치·전망을 만들어내지 않는다
- 통화정책 용어는 국내 시장 표기를 쓴다 (동결·점도표·대차대조표 축소·완화 편향 …)
- 강도를 그대로 옮긴다 — `several` 은 '몇몇', `most` 는 '대다수'

세 번째가 핵심이다. 회의록은 위원 몇 명이 어느 쪽이었는지가 정보이므로,
뭉뚱그리면 회의록을 읽는 의미가 없어진다.

비용은 회의록 1건당 약 160원(Claude Opus 5 기준, 입력 1.3만 / 출력 2천 토큰).
연 8회 회의이므로 연간 2천 원 수준이다. `TRANSLATE_MODEL` 로 모델을 바꿀 수 있다.

새 회의록이 공개되면 이후 열흘간 텔레그램 브리핑에도 헤드라인이 실린다.

---

## 직접 관리하는 일정 추가

FOMC·금통위·미국 지표 발표일은 자동 수집된다. 그 밖에 직접 챙기고 싶은 일정은
`data/seed_events.json` 에 넣으면 캘린더에 함께 표시된다.
(`data/seed_events.json.example` 참고)

```json
[
  {
    "date": "2026-10-15",
    "time": "09:00 KST",
    "country": "KR",
    "title": "금통위 통화정책방향 결정",
    "importance": 3,
    "indicator_code": "KR_POLICY"
  }
]
```

---

## 지표 추가하기

`app/registry.py` 의 `INDICATORS` 목록에 한 줄 추가하면 끝이다.
DB 스키마, KPI 카드, 시계열 차트, 지표 선택 칩이 모두 자동으로 따라온다.

```python
dict(code="US_PPI", name_ko="미국 생산자물가(전년비)", name_en="US PPI YoY",
     country="US", category="물가", unit="%", source="fred",
     source_id="PPIACO", frequency="M", transform="yoy", decimals=2,
     display_order=24, featured=0),
```

`transform` 은 `level`(원계열) / `yoy`(전년동월비 %) / `diff`(전기차) / `spread`(파생) 중 하나다.

---

## API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/summary` | 전 지표 최신값 + 변화량 |
| GET | `/api/indicators` | 지표 카탈로그 |
| GET | `/api/series?codes=US10Y,US2Y&range=5Y` | 시계열 |
| GET | `/api/curve` | 수익률곡선 비교 |
| GET | `/api/calendar?start=&end=&country=&min_importance=` | 발표일정 |
| GET | `/api/calendar.ics` | iCal 구독 |
| GET | `/api/speeches?limit=40&tone=hawkish` | 발언 피드 |
| GET | `/api/status` | 수집기 실행 상태 |
| POST | `/api/refresh?collector=treasury&backfill=false` | 수동 수집 |
| GET | `/api/brief` | 브리핑 본문 미리보기 |
| POST | `/api/telegram/send` | 브리핑 즉시 발송 |
| GET | `/api/telegram/chats` | chat_id 찾기 |
| GET | `/api/forecasts` | 다음 발표 예상치 + 연도별 공식 전망 |
| GET | `/api/documents` | FOMC 회의록·성명 한글 요약 |
| POST | `/api/translate` | 밀린 문서 요약 실행 |

FastAPI 자동 문서: http://127.0.0.1:8500/docs

---

## 구조

```
app/
├── config.py       설정·API 키
├── db.py           SQLite 스키마·UPSERT 헬퍼
├── registry.py     지표 카탈로그 (여기만 고치면 지표가 늘어난다)
├── scheduler.py    인프로세스 수집 스케줄러
├── main.py         FastAPI 라우트
├── collectors/     treasury · fred · ecos · calendar_src · speeches
│                  forecast · minutes
├── notify/         telegram 발송
└── services/       indicators · calendar · speeches · brief
                   forecasts · documents · translate · snapshot
static/             대시보드 UI (Vanilla JS + ECharts)
data/macro.db       SQLite (자동 생성)
```

수집기는 서로 격리돼 있다. 한 소스가 죽어도 나머지는 계속 수집하고,
실패는 `collection_runs` 테이블과 상단 배지에 남는다.

---

## 알려진 제약

- 톤(매파/비둘기파) 태깅은 원문 키워드 휴리스틱이다. 해석 보조용이며 원문 확인을 대체하지 않는다.
- 미 재무부 목록 페이지는 최근 항목만 노출하므로 발언 이력은 수집을 반복하며 쌓인다.
- 금통위 일정은 한국은행이 공표한 연도만 들어온다. 내년 일정이 아직 없으면 0건이고,
  공표되는 시점부터 자동으로 채워진다.
- 미 국채 CSV 는 2012년 이후를 제공한다. 그 이전 이력은 FRED 키로 받는다.
- **FRED 의 시장 시리즈는 공표 일정을 따라 며칠씩 밀린다** (유가 8일, 환율 5일 관측).
  그래서 거래되는 자산(환율·지수·에너지·금속)은 Yahoo 시세를 쓴다. 정의가 다르므로
  (선물 vs 현물 고시가) 한 계열에 섞지 않고 지표별로 소스를 하나만 쓴다.
- 알루미늄·원자재 종합지수는 IMF 월별 통계라 두 달 이상 밀린다. 일별 대체 소스가
  무료로 없어 그대로 두되, 카드에 기준일과 지연 경고가 표시된다.
- 일별 지표가 4일 넘게 멈추면 카드 날짜가 주황색 ⚠ 로 바뀌고 브리핑에도 경고가 실린다.
- 시장 컨센서스(블룸버그·로이터 서베이)는 유료 데이터라 쓸 수 없다. 예상치는
  클리블랜드 연은 나우캐스팅과 FOMC 경제전망(SEP)이며, 화면에 출처를 함께 표시한다.
- 회의록 한글 요약은 기계 요약이다. 판단이 필요한 대목은 함께 실린 원문 링크를 확인한다.
- 공유용 보드의 JS 는 파이썬 문자열 안에 들어 있다. 이스케이프가 한 겹 벗겨지면
  스크립트 전체가 죽고 정적 HTML 만 남아 '빈 페이지' 처럼 보인다. 이를 막기 위해
  `snapshot._check()` 가 생성 직후 문법을 검사하고, 걸리면 파일을 쓰지 않는다.

## 면책

공개 데이터를 취합·표시하는 정보 도구이며 투자 자문이 아니다.
표시 수치는 원 출처와 다를 수 있으므로 의사결정 전 원문을 확인해야 한다.
