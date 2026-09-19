"""지표 카탈로그.

여기에 정의된 항목이 곧 DB의 indicators 테이블이고, 수집기는 source/source_id 를
보고 무엇을 가져올지 결정한다. 지표를 추가하려면 이 목록에 한 줄만 넣으면 된다.
"""
from __future__ import annotations

from .db import upsert_indicator

# transform: level(원계열) | yoy(전년동월대비 %) | diff(전기차) | spread(파생)
INDICATORS: list[dict] = [
    # ------------------------------------------------ 미국 금리 (키 불필요)
    dict(code="US3M", name_ko="미국 국채 3개월", name_en="US 3M Treasury",
         country="US", category="금리", unit="%", source="treasury",
         source_id="3 Mo", frequency="D", transform="level", decimals=2,
         display_order=10, featured=0),
    dict(code="US2Y", name_ko="미국 국채 2년", name_en="US 2Y Treasury",
         country="US", category="금리", unit="%", source="treasury",
         source_id="2 Yr", frequency="D", transform="level", decimals=2,
         display_order=11, featured=1),
    dict(code="US5Y", name_ko="미국 국채 5년", name_en="US 5Y Treasury",
         country="US", category="금리", unit="%", source="treasury",
         source_id="5 Yr", frequency="D", transform="level", decimals=2,
         display_order=12, featured=0),
    dict(code="US10Y", name_ko="미국 국채 10년", name_en="US 10Y Treasury",
         country="US", category="금리", unit="%", source="treasury",
         source_id="10 Yr", frequency="D", transform="level", decimals=2,
         display_order=13, featured=1),
    dict(code="US30Y", name_ko="미국 국채 30년", name_en="US 30Y Treasury",
         country="US", category="금리", unit="%", source="treasury",
         source_id="30 Yr", frequency="D", transform="level", decimals=2,
         display_order=14, featured=0),
    dict(code="US10Y2Y", name_ko="미 장단기 스프레드(10Y-2Y)",
         name_en="10Y-2Y Spread", country="US", category="금리", unit="%p",
         source="derived", source_id="US10Y-US2Y", frequency="D",
         transform="spread", decimals=2, display_order=15, featured=1),

    # ------------------------------------------------ 미국 정책/물가/고용 (FRED 키 필요)
    dict(code="US_POLICY", name_ko="미국 기준금리(EFFR)", name_en="Fed Funds Rate",
         country="US", category="정책금리", unit="%", source="fred",
         source_id="DFF", frequency="D", transform="level", decimals=2,
         display_order=1, featured=1),
    dict(code="US_CPI", name_ko="미국 CPI(전년비)", name_en="US CPI YoY",
         country="US", category="물가", unit="%", source="fred",
         source_id="CPIAUCSL", frequency="M", transform="yoy", decimals=2,
         display_order=20, featured=1),
    dict(code="US_CORECPI", name_ko="미국 근원 CPI(전년비)", name_en="US Core CPI YoY",
         country="US", category="물가", unit="%", source="fred",
         source_id="CPILFESL", frequency="M", transform="yoy", decimals=2,
         display_order=21, featured=1),
    dict(code="US_COREPCE", name_ko="미국 근원 PCE(전년비)", name_en="US Core PCE YoY",
         country="US", category="물가", unit="%", source="fred",
         source_id="PCEPILFE", frequency="M", transform="yoy", decimals=2,
         display_order=22, featured=0),
    dict(code="US_PCE", name_ko="미국 PCE(전년비)", name_en="US PCE YoY",
         country="US", category="물가", unit="%", source="fred",
         source_id="PCEPI", frequency="M", transform="yoy", decimals=2,
         display_order=23, featured=0),
    dict(code="US_PPI", name_ko="미국 PPI(전년비)", name_en="US PPI Final Demand YoY",
         country="US", category="물가", unit="%", source="fred",
         source_id="PPIFIS", frequency="M", transform="yoy", decimals=2,
         display_order=24, featured=1),
    dict(code="US_COREPPI", name_ko="미국 근원 PPI(전년비)",
         name_en="US Core PPI YoY", country="US", category="물가", unit="%",
         source="fred", source_id="PPIFES", frequency="M", transform="yoy",
         decimals=2, display_order=25, featured=0),
    dict(code="US_BEI10", name_ko="미국 기대인플레(10Y BEI)", name_en="10Y Breakeven",
         country="US", category="물가", unit="%", source="fred",
         source_id="T10YIE", frequency="D", transform="level", decimals=2,
         display_order=23, featured=0),
    dict(code="US_UNRATE", name_ko="미국 실업률", name_en="US Unemployment Rate",
         country="US", category="고용", unit="%", source="fred",
         source_id="UNRATE", frequency="M", transform="level", decimals=1,
         display_order=30, featured=1),
    dict(code="US_PAYEMS", name_ko="미국 비농업고용(전월차)", name_en="Nonfarm Payrolls MoM",
         country="US", category="고용", unit="천명", source="fred",
         source_id="PAYEMS", frequency="M", transform="diff", decimals=0,
         display_order=31, featured=0),

    # ------------------------------------------------ 한국 (ECOS 키 필요)
    dict(code="KR_POLICY", name_ko="한국 기준금리", name_en="BOK Base Rate",
         country="KR", category="정책금리", unit="%", source="ecos",
         source_id="722Y001/M/0101000", frequency="M", transform="level",
         decimals=2, display_order=2, featured=1),
    dict(code="KR3Y", name_ko="국고채 3년", name_en="KTB 3Y",
         country="KR", category="금리", unit="%", source="ecos",
         source_id="817Y002/D/010200000", frequency="D", transform="level",
         decimals=2, display_order=40, featured=1),
    dict(code="KR10Y", name_ko="국고채 10년", name_en="KTB 10Y",
         country="KR", category="금리", unit="%", source="ecos",
         source_id="817Y002/D/010210000", frequency="D", transform="level",
         decimals=2, display_order=41, featured=1),
    dict(code="KR_CPI", name_ko="한국 소비자물가(전년비)", name_en="KR CPI YoY",
         country="KR", category="물가", unit="%", source="ecos",
         source_id="901Y009/M/0", frequency="M", transform="yoy", decimals=2,
         display_order=42, featured=1),

    # ------------------------------------------------ 시장 (FRED 키 필요)
    # stooq 는 봇 차단(JS 챌린지)으로 사용 불가하여 FRED 시리즈로 대체
    dict(code="SPX", name_ko="S&P 500", name_en="S&P 500", country="US",
         category="시장", unit="pt", source="yahoo", source_id="^GSPC",
         frequency="D", transform="level", decimals=2, display_order=50, featured=0),
    # 뉴스에서 인용되는 달러지수는 ICE DXY 다. FRED 의 광의 달러지수(2006=100)는
    # 값의 자릿수부터 달라 비교가 안 되므로 시장이 쓰는 쪽으로 맞춘다.
    dict(code="DXY", name_ko="달러지수(DXY)", name_en="ICE Dollar Index",
         country="US", category="시장", unit="idx", source="yahoo",
         source_id="DX-Y.NYB", frequency="D", transform="level", decimals=2,
         display_order=52, featured=0),
    dict(code="USDKRW", name_ko="원/달러 환율", name_en="USD/KRW", country="KR",
         category="시장", unit="원", source="yahoo", source_id="KRW=X",
         frequency="D", transform="level", decimals=2, display_order=53, featured=1),

    # ------------------------------------------------ 원자재
    # 에너지는 FRED 일별, 귀금속은 LBMA 일별, 산업금속은 IMF 월별(FRED 경유)
    dict(code="WTI", name_ko="WTI 유가", name_en="WTI Crude", country="US",
         category="원자재", unit="USD/bbl", source="yahoo", source_id="CL=F",
         frequency="D", transform="level", decimals=2, display_order=60, featured=1),
    dict(code="BRENT", name_ko="브렌트유", name_en="Brent Crude", country="US",
         category="원자재", unit="USD/bbl", source="yahoo", source_id="BZ=F",
         frequency="D", transform="level", decimals=2, display_order=61, featured=0),
    dict(code="NGAS", name_ko="천연가스(헨리허브)", name_en="Henry Hub Natural Gas",
         country="US", category="원자재", unit="USD/MMBtu", source="yahoo",
         source_id="NG=F", frequency="D", transform="level", decimals=2,
         display_order=62, featured=0),
    dict(code="GOLD", name_ko="금", name_en="Gold Futures", country="US",
         category="원자재", unit="USD/oz", source="yahoo", source_id="GC=F",
         frequency="D", transform="level", decimals=2, display_order=63, featured=1),
    dict(code="SILVER", name_ko="은", name_en="Silver Futures", country="US",
         category="원자재", unit="USD/oz", source="yahoo", source_id="SI=F",
         frequency="D", transform="level", decimals=3, display_order=64, featured=1),
    dict(code="COPPER", name_ko="구리", name_en="Copper Futures", country="US",
         category="원자재", unit="USD/lb", source="yahoo", source_id="HG=F",
         frequency="D", transform="level", decimals=3, display_order=65, featured=1),
    dict(code="ALUM", name_ko="알루미늄", name_en="Aluminum (Global Price)",
         country="US", category="원자재", unit="USD/t", source="fred",
         source_id="PALUMUSDM", frequency="M", transform="level", decimals=2,
         display_order=66, featured=0),
    dict(code="CMDTY", name_ko="원자재 종합지수", name_en="All Commodities Index",
         country="US", category="원자재", unit="idx", source="fred",
         source_id="PALLFNFINDEXM", frequency="M", transform="level", decimals=2,
         display_order=67, featured=0),
]

BY_CODE = {i["code"]: i for i in INDICATORS}


def indicators_for(source: str) -> list[dict]:
    return [i for i in INDICATORS if i["source"] == source]


def sync_registry() -> None:
    """카탈로그를 DB에 반영한다 (앱 시작 시 호출)."""
    for ind in INDICATORS:
        upsert_indicator(ind)
