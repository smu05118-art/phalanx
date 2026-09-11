#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_scan — 모집단 ③ 겹(부품사 확장). KIND 주요제품 한 줄로는 안 보이는 전력망 부품사를
**정기보고서「II. 사업의 내용」본문**에서 찾아 승격하고, 이름만으로 들어와 있던 종목을 다시 본다.

왜 이 겹이 필요한가 — 원문에서 확인한 것:
  · FINDINGS §1 이 KIND 문구로 잡아낸 부품사는 금구류·절연유·부스웨이·계량기뿐이고,
    **부싱·탭체인저는 KIND 문구에서 아예 잡히지 않았다.** 그 낱말들은 II-2「주요 제품 및 서비스」
    본문에만 있다.
  · 반대로 KIND 문구만으로 들어온 종목 중에 전력망이 아닌 것이 있었다(아래 --rejudge 실측).
    - 파워넷 037030 : 본문 II-1 "주력 제품인 SMPS는 … IT, OA, 가전, 산업용 등 다양한 분야에
      적용되는 핵심부품", II-2 "TV, Monitor 등 Display용 SMPS를 주력 제품으로" → 가전 전원장치다.
    - 대양전기공업 108380 : II-2 제품표 제품설명이 "선박용 배전반 외"·"철도차량용 배전반 외",
      판매경로가 "당사 -> 국내시공사(조선소, 철도차량제작사) -> 최종수요자" → 선박·철도다.
    - 제일일렉트릭 199820 : II-2 "배선기구 — 세대내 배선에서 전기 기구와 접속하거나",
      "주택용 분전반 — 세대 간선으로부터 각 분기회로로 갈라지는 곳에 설치" → 세대 저압 배선기구다.

세 갈래로 나눠 돈다(DART 를 두드리는 것은 --probe/--rejudge 뿐이다):

    python3 kgrid_scan.py --probe [--limit 60]   후보의 II절 본문을 읽어 assets/probe_rows.json 에 쌓는다
    python3 kgrid_scan.py --rejudge [--limit 40] 이미 모집단인 회사도 같은 방식으로 읽어 쌓는다
    python3 kgrid_scan.py --build                쌓인 증거만으로 판정 → assets/universe_probe.json

--probe 는 **아직 안 읽은 종목만** 읽는다(이어 돌리기). 실패는 저장하지 않는다 — 다시 돌리면
빠진 것만 받는다(COMMON §2). 판정 기준을 고칠 때는 --build 만 다시 돌리면 되고 DART 를 건드리지
않는다. 승격은 **본문 인용문이 있을 때만** 한다(COMMON §0-1).
"""
import argparse
import os
import re
import sys
import time

from kgrid_lib import (ASSETS, KIND_URL, _get, fetch_section, find_sections, has_asset,
                       latest_quarter, load_asset, parse_kind, pick_report, report_kind,
                       report_window, search_reports, toc, write_asset)
from kgrid_universe import CORE_INDUSTRIES, HOLDING, UTILITY_INDUSTRIES
from kgrid_universe import load as load_universe

# 「II. 사업의 내용」에서 읽는 절. 부싱·탭체인저 같은 부품 낱말은 II-2 에 있고(스펙 ③),
# 발주처·계통 낱말은 II-1·II-4 에 있다(FINDINGS §4).
SECTIONS = [
    ("overview", ["사업의 개요"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품"]),
    ("sales", ["매출 및 수주상황", "수주상황", "매출실적"]),
]

RAW = os.path.join(ASSETS, "_raw", "probe")     # 원문 본문 캐시(.gitignore — 커밋하지 않는다)
ROWS = "probe_rows.json"                        # 파싱 결과 캐시(원문 인용문을 담는다 — 커밋한다)

# ── 후보 풀 ─────────────────────────────────────────────────
# 두 갈래를 합친다.
#  (a) 업종 4갈래(FINDINGS §0 의 KIND 실제 표기) 안에 있는데 모집단에 못 든 51사 — 제품 문구가
#      짧아 놓친 것이 여기 섞인다(대원전선 006340 `전선,통신케이블…`이 그렇다).
#  (b) 업종 밖이지만 **전력기기 부품이 될 수 있는 소재·부품 어휘**를 제품 문구에 가진 회사.
#      업종 화이트리스트를 같이 걸어 2,759사가 수백 건으로 줄도록 했다(COMMON §2 — 한 웨이브가
#      DART 를 수천 건 긁지 않는다).
POOL = re.compile(
    r"부싱|탭체인저|절연유|절연물|절연재|절연지|절연|권선|코일|애자|부스덕트|부스웨이|"
    r"변성기|계기용|리액터|콘덴서|커패시터|피뢰기|퓨즈|단자|함체|판넬|패널|"
    r"에폭시|수지|몰드|규소강판|전기강판|방향성|전기동|동선|동박|압연|주물|주조|단조|"
    r"프레스|금형|도금|열처리|스위치|계전|차단|개폐|배전|송전|변압|전력|전기설비|"
    r"전선|케이블|전력량계|검침|세라믹|변압기|철심|코어|탱크|용접|판금|"
    r"윤활유|기유|유압|변류기|계측|제어반|배전반|모터|전동기|발전기|감시|SCADA|"
    r"적산계기|계기|동판|동대|동봉|황동|신동", re.I)
POOL_IND = re.compile(
    r"전자부품|특수 목적용 기계|일반 목적용 기계|1차 철강|1차 비철금속|기초 화학물질|"
    r"기타 화학제품|전동기, 발전기|기타 전기장비|절연선 및 케이블|기타 금속 가공제품|"
    r"구조용 금속제품|측정, 시험, 항해, 제어|플라스틱제품|금속 주조업|고무제품|"
    r"석유 정제품|비금속 광물|도자기|유리|시멘트|내화|합성고무|펄프, 종이|"
    r"전기 및 통신 공사업|통신 및 방송 장비|기타 기계|산업용 기계|자동차 신품 부품")
# 전력기기의 **고객·금융·소비재**이지 공급망이 아닌 업종.
EXCL_IND = re.compile(
    r"금융|보험|증권|은행|부동산|임대업|음식|식료|음료|주류|담배|의복|가죽|신발|화장품|"
    r"농업|어업|임업|광업|숙박|교육|오락|게임|스포츠|광고|출판|영화|방송업|방송프로그램|"
    r"여행|운송|창고|도매|소매|의약|의료|사회복지|협회|수도|하수|소프트웨어|"
    r"컴퓨터 프로그래밍|연구개발업|기술 서비스업")
# 제품 문구가 이 말만 하면 후보에서 뺀다(FINDINGS §1 의 어휘 함정 — 이차전지·충전기·가전).
# 단 전력망 낱말을 같이 말하면 남긴다('변압기, 전기차 충전기'를 통째로 버리지 않는다).
POOL_NOT = re.compile(
    r"2차전지|이차전지|리튬|배터리|건전지|전기차\s*충전|충전기|휴대폰|교육용|"
    r"태양광\s*모듈|태양전지|연료전지|광섬유|프로브|probe|반도체\s*및\s*디스플레이", re.I)
POOL_KEEP = re.compile(r"변압기|배전|송전|수배전|개폐|차단기|전력망|전력계통|금구류|절연유|적산계기|검침")

# 본문을 꼭 봐야 할 지정 후보 — 제품 문구·업종으로는 못 잡지만 전력망 부품일 수 있는 회사.
# 이름으로 넣는 것이 아니라 **본문을 읽을 후보에 넣는 것**이다. 승격은 인용문이 결정한다.
EXTRA = {
    "006340": "대원전선 — 업종은 절연선·케이블인데 제품 문구가 `전선,통신케이블`뿐이다(전력선?)",
    "027040": "서울전자통신 — 제품 문구 `전자변성기, 트랜스포머자재`(전력용 변성기인가 전자용 트랜스인가)",
    "025540": "한국단자공업 — `정밀압착단자`. 전력용 압착단자·접속재일 수 있다",
    "040160": "누리플렉스 — `지능형검침인프라(AMI)`. 업종이 소프트웨어라 풀에서 빠진다",
    "130660": "한전산업 — `발전설비 운전·정비, 전기검침`. 업종이 엔지니어링 서비스업이라 빠진다",
    "103140": "풍산 — KIND 주요제품 문구가 비어 있다(신동·방산). 변압기 권선용 동대인가",
}

# ── 본문 어휘 ───────────────────────────────────────────────
# STRONG = **전력망에서만 쓰는 말**. 이것이 곧 승격 근거이고, 인용문도 이 낱말 주변에서 뽑는다.
# FINDINGS §1 의 함정을 그대로 지켰다:
#   · `GIS` 단독 금지 → `가스절연`·`GIS차단기`·`GIS개폐장치` 처럼 문맥이 붙은 꼴만
#   · `ESS` 단독 금지 → 아예 넣지 않았다(이차전지 제조가 이 낱말로 들어온다)
#   · `초고압` 단독 금지 → `초고압 변압기`·`초고압 케이블` 처럼 뒷말이 붙은 꼴만
STRONG = re.compile(
    r"부싱|탭\s?체인저|탭\s?절환|부하시\s?탭|OLTC|"
    r"절연유|애자|피뢰기|변류기|계기용\s?변성기|계기용\s?변압기|계기용\s?변류기|"
    r"부스\s?덕트|버스\s?덕트|부스\s?웨이|bus\s?duct|busway|"
    r"전력량계|원격\s?검침|배전\s?자동화|"
    r"송전\s?선로|배전\s?선로|송배전|변전소|변전\s?설비|변전\s?소용|"
    r"전력\s?계통|계통\s?연계|전력망|송변전|"
    r"초고압\s?변압기|초고압\s?케이블|초고압\s?전력|주상\s?변압기|몰드\s?변압기|"
    r"유입\s?변압기|건식\s?변압기|전력용\s?변압기|배전용\s?변압기|특고압\s?변압기|"
    r"가스\s?절연|GIS\s?차단기|GIS\s?개폐장치|GIS\s?개폐기|가스절연개폐장치|"
    r"방향성\s?전기강판|무방향성\s?전기강판|규소\s?강판|전기\s?강판|"
    r"해저\s?전력\s?케이블|지중\s?케이블|지중\s?선로|"
    r"고온\s?초전도|초전도\s?선재|전력용\s?초전도|초전도\s?한류기|초전도\s?케이블|"
    r"송배전용|전력\s?기자재|전력\s?설비용|수배전\s?설비|"
    r"154\s?kV|345\s?kV|765\s?kV|22\.9\s?kV|66\s?kV|25\.8\s?kV|170\s?kV|362\s?kV|800\s?kV",
    re.I)
# MID = 전력망을 말할 수도, 아닐 수도 있는 말. 혼자서는 승격 못 한다(선박용 배전반이 이 무리다).
MID = re.compile(
    r"변압기|차단기|개폐기|배전반|수배전|스위치기어|전력기기|전력설비|계전기|보호계전|"
    r"전력용|권선|철심|절연물|몰드\s?성형|배전|송전|변전|"
    r"전력\s?케이블|전력선|해저\s?케이블|초전도", re.I)
# NEG = 같은 낱말을 쓰지만 **전력망이 아닌 곳**. 세는 이유는 판정이 아니라 견제다
# (대양전기공업의 `배전반`은 선박·철도용이었다 — §--rejudge 실측).
NEG = re.compile(
    r"선박용|함정|잠수함|조선소|선주|해양플랜트|박용|"
    r"철도\s?차량|철도차량용|전동차|객차|"
    r"세대\s?내|세대\s?간선|주택용|아파트|모델하우스|건설사|배선기구|"
    r"자동차용|차량용|전기차|이차전지|2차전지|배터리\s?팩|"
    r"반도체\s?장비|디스플레이|휴대폰|스마트폰|가전기기|생활가전|SMPS|Adaptor|어댑터", re.I)
# 발주처 — 한국전력공사는 **고객**이다(모집단에는 안 넣지만, 언급은 전력망이라는 증거다).
KEPCO = re.compile(r"한국전력공사|한국전력거래소|KEPCO|한전\s?KDN|한국전력", re.I)
# GEN = 전력을 **파는** 쪽의 말(스펙 ④ 제외 대상 — 발전사업자·발주처). 전력기기 공급망이 아니다.
# 실측: 금양그린파워 282720 은 `발전매출`·`발전사업 허가`·`SMP+REC` 가 14회인데 전력망 고유 낱말은
# 2회다 — 신재생 발전소를 개발·시공하고 전기를 파는 회사다. 반면 한전KPS 051600 은 gen 1회 ·
# 고유 낱말 26회(송전선로 유지·HVDC 설비점검)로 정비 **공급자**다. 그래서 절대수가 아니라
# gen 과 고유 낱말의 **크기 비교**로 가른다.
GEN = re.compile(r"발전매출|발전사업\s?허가|SMP\s?\+?\s?REC|전력\s?판매|전력거래소|발전사업자|"
                 r"REC\s?판매", re.I)
# 모집단 체계업체 언급 — 이들에게 납품한다면 전력기기 공급망이다.
PRIME_NAMES = {
    "267260": r"HD\s?현대일렉트릭|현대일렉트릭",
    "010120": r"LS\s?ELECTRIC|엘에스일렉트릭|LS일렉트릭|LS산전",
    "298040": r"효성중공업",
    "103590": r"일진전기",
    "062040": r"산일전기",
    "033100": r"제룡전기",
    "017040": r"광명전기",
    "189860": r"서전기전",
    "001440": r"대한전선",
    "000500": r"가온전선",
    "LS전선": r"LS전선|엘에스전선",
}

# ── 판정선은 모집단 29사의 실측값으로 맞췄다(`--rejudge` 로 본문을 다 읽어 세어 본 것) ──
# 전력망 고유 낱말(s)만으로는 선이 서지 않는다 — HD현대일렉트릭 s=1(`전력기자재` 1회)·
# 엘에스일렉트릭 s=2 다. 이 회사들은 본문에서 `변압기`·`차단기`라고만 쓴다. 반대로
# 파워넷·대양전기공업·제일일렉트릭·이지트로닉스는 **s=0** 이었다(고유 낱말이 한 번도 안 나온다).
# 그래서 두 신호를 함께 본다: s 는 **문지기**(0이면 무조건 제외), 점수는 s*3 + mid 로 센다.
#
#   실측 점수(2026Q2 반기보고서, `--rejudge` 29사):
#     ○ 피앤씨테크 577 · 산일전기 286 · 서전기전 204 · 서남 193 · 지투파워 125 · 보성파워텍 69 ·
#       티에스넥스젠 48 · 효성중공업 47 · 티씨머티리얼즈 47 · 세명전기 44 · 엘에스일렉트릭 42 ·
#       HD현대일렉트릭 40 · LS마린솔루션 40 · 옴니시스템 37 · 비츠로테크 37 · 일진전기 32 ·
#       대한전선 32 · 가온전선 27 · 광명전기 23 · 미창석유공업 17 · 비츠로시스 17 ·
#       제룡전기 16 · 선도전기 16 · 제룡산업 15   ← 모집단 하한
#     ✕ 대양전기공업 6(선박·철도 배전반) · 이지트로닉스 5(전기차·방산 전력변환) ·
#       티엠씨 3(선박·해양 케이블) · 파워넷 0(가전 SMPS) · 제일일렉트릭 41이지만 **s=0**
#   → 하한 15 와 상한 6 사이가 비어 있다. s=0 을 문지기로 세우고 승격선을 그 빈 띠에 둔다.
#
#   후보 191사 쪽에서도 같은 빈 띠가 나왔다: 대원전선 10(제품표 용도가 `전력송배전`인 전력선 회사) ·
#   그 아래는 지엔씨에너지 5 · 한국쉘석유 4 · POSCO홀딩스 4 처럼 부수 언급뿐이다.
#   그래서 승격선은 **10**(5와 15 사이의 빈 띠)로 둔다. 보고서가 짧으면 낱말 수도 적어진다 —
#   대원전선 본문은 6.3KB뿐인데 내용은 명백하다(밀도가 아니라 빈 띠로 선을 긋는 이유다).
STRONG_WEIGHT = 3
PROMOTE_SCORE = 10           # s*3 + mid. 모집단 하한 15와 오탐 상한 5 사이의 빈 띠
PROMOTE_SCORE_WITH_REF = 6   # 한전·체계업체 언급이 받쳐 주면 이만큼으로 충분하다
PROMOTE_REF = 2              # 받쳐 주는 언급의 최소 합(한국전력공사 + 전력기기 체계업체)
PROMOTE_MID = 1              # 전력기기 낱말이 한 번도 없으면 그 고유 낱말은 남의 산업 이야기다
NEG_RATIO = 2.0              # 비전력망 문맥이 점수의 이 배를 넘으면 승격하지 않는다
RULE = ("II절 본문에서 **전력망 고유 낱말** s(부싱·탭체인저·절연유·애자·변류기·부스덕트·전력량계·"
        "송배전·변전소·전력계통·154/345/765kV·가스절연·지중케이블·전기강판 …)와 **전력기기 낱말** "
        "mid(변압기·차단기·개폐기·배전반·배전·송전·전력선 …)를 센다. 점수 = s×%d + mid. "
        "s ≥ 1 · mid ≥ %d 이면서 점수 ≥ %d, 또는 한국전력공사·전력기기 체계업체 언급 ≥ %d 이면서 "
        "점수 ≥ %d 이면 승격. 다음이면 승격하지 않는다 — ① 고유 낱말이 하나도 없다(s=0) "
        "② 비전력망 문맥(선박·함정·철도차량·세대배선·자동차·가전) 낱말이 점수의 %.0f배를 넘는다 "
        "③ 전력을 **파는** 쪽 낱말(발전매출·발전사업 허가·SMP+REC)이 고유 낱말보다 많다(스펙 ④ "
        "발주처·발전사업자) ④ II절을 못 읽었거나 인용문을 못 뽑았다(fail-closed). "
        "`GIS`·`ESS`·`초고압` 단독은 어휘에 넣지 않았다(FINDINGS §1 실측 오탐)."
        % (STRONG_WEIGHT, PROMOTE_MID, PROMOTE_SCORE, PROMOTE_REF, PROMOTE_SCORE_WITH_REF,
           NEG_RATIO))


# ── 후보 뽑기 ───────────────────────────────────────────────

def pool(recs, universe):
    uni = {r["stock"] for r in universe}
    out = []
    for r in recs:
        st = r["stock"]
        if st in uni or st in HOLDING:
            continue
        ind, prod = r.get("industry") or "", r.get("product") or ""
        if ind in UTILITY_INDUSTRIES:
            continue                                   # 발주처·발전사업자(스펙 ④)
        if st in EXTRA:
            out.append(r)
            continue
        if EXCL_IND.search(ind):
            continue
        core = ind in CORE_INDUSTRIES
        if not (core or (POOL_IND.search(ind) and POOL.search(prod))):
            continue
        if POOL_NOT.search(prod) and not POOL_KEEP.search(prod):
            continue
        out.append(r)
    return out


# ── 본문 읽기 ───────────────────────────────────────────────

def _raw_path(quarter, stock):
    return os.path.join(RAW, quarter, stock + ".txt")


def body_text(stock, quarter):
    """II절 본문(개요·주요제품·매출수주)을 태그를 벗겨 한 덩어리로. 성공만 캐시한다.

    반환: (text, rcp, title). 못 읽으면 예외가 아니라 (None, rcp, note) 로 알린다.
    """
    p = _raw_path(quarter, stock)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            head = f.readline().rstrip("\n")
            rcp, _, title = head.partition("\t")
            return f.read(), rcp, title
    start, end = report_window(quarter)
    reports = pick_report(search_reports(stock, start, end, report_kind(quarter)), quarter)
    if not reports:
        return None, "", "정기보고서 없음"
    rcp, title = reports[0]
    found = find_sections(toc(rcp), SECTIONS)
    if not found:
        return None, rcp, "II절 목차 없음"
    text = ""
    for key in ("overview", "products", "sales"):
        if key in found:
            text += " " + re.sub(r"<[^>]+>", " ", fetch_section(found[key]))
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"[\s　]+", " ", text).strip()
    if not text:
        return None, rcp, "II절 본문 비어 있음"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:                 # 성공만 캐시(COMMON §2)
        f.write("%s\t%s\n" % (rcp, title))
        f.write(text)
    return text, rcp, title


def _counts(pat, text):
    c = {}
    for m in pat.finditer(text):
        t = re.sub(r"\s+", " ", m.group(0))
        c[t] = c.get(t, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def quotes(text, limit=3, width=90):
    """승격 근거로 남길 **원문 인용문**. STRONG 낱말 주변을 그대로 잘라 낸다(추정 금지).

    같은 낱말이 반복되면 서로 다른 낱말이 걸린 토막을 우선해 다양한 근거를 남긴다.
    """
    out, used = [], set()
    for m in STRONG.finditer(text):
        key = re.sub(r"\s+", "", m.group(0)).lower()
        if key in used:
            continue
        used.add(key)
        s = max(0, m.start() - width // 2)
        out.append(text[s:m.end() + width].strip())
        if len(out) >= limit:
            break
    return out


def probe_one(rec, quarter):
    """한 회사의 II절 본문 → 낱말 횟수·인용문. 실패는 ok=False 로 남기고 캐시하지 않는다."""
    row = {"stock": rec["stock"], "name": rec["name"], "market": rec.get("market", ""),
           "industry": rec.get("industry", ""), "product": rec.get("product", ""),
           "quarter": quarter, "ok": False, "strong": 0, "mid": 0, "neg": 0, "kepco": 0,
           "terms": {}, "neg_terms": {}, "mentions": {}, "evidence": [], "note": "",
           "rcp": "", "title": ""}
    try:
        text, rcp, title = body_text(rec["stock"], quarter)
    except Exception as e:                                    # 일시 실패 — 캐시하지 않는다
        row["note"] = "본문 읽기 실패: %s" % str(e)[:90]
        return row
    row["rcp"] = rcp
    if text is None:
        row["note"] = title
        return row
    row["title"] = title
    measure(row, text)
    return row


def measure(row, text):
    """본문 한 덩어리 → 낱말 횟수·인용문. 어휘를 고치면 원문 캐시로 **다시 셀 수 있게** 떼어 뒀다."""
    strong = _counts(STRONG, text)
    row["terms"] = dict(list(strong.items())[:12])
    row["strong"] = sum(strong.values())
    row["mid"] = sum(_counts(MID, text).values())
    neg = _counts(NEG, text)
    row["neg_terms"] = dict(list(neg.items())[:8])
    row["neg"] = sum(neg.values())
    row["kepco"] = len(KEPCO.findall(text))
    gen = _counts(GEN, text)
    row["gen_terms"] = dict(list(gen.items())[:6])
    row["gen"] = sum(gen.values())
    row["mentions"] = {k: len(re.findall(p, text, re.I))
                       for k, p in PRIME_NAMES.items() if re.search(p, text, re.I)}
    row["evidence"] = quotes(text)
    row["ok"] = True
    return row


def remeasure(rows, quarter, log=sys.stderr):
    """원문 캐시(assets/_raw/probe/<분기>/<종목>.txt)가 있으면 **어휘로 다시 센다**.

    낱말을 고쳤을 때 DART 를 다시 두드리지 않기 위한 것이다(COMMON §0-4 — 원문을 남겨 두면
    파서가 자라도 재수집이 필요 없다). 캐시가 없는 행은 그대로 둔다.
    """
    n = 0
    for st, row in rows.items():
        p = _raw_path(row.get("quarter") or quarter, st)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            head = f.readline().rstrip("\n")
            text = f.read()
        row["rcp"], _, row["title"] = head.partition("\t")
        measure(row, text)
        n += 1
    if n:
        log.write("원문 캐시로 다시 센 회사 %d사\n" % n)
    return rows


# ── 판정 ────────────────────────────────────────────────────

def score_of(row):
    return STRONG_WEIGHT * row.get("strong", 0) + row.get("mid", 0)


def judge(row):
    """승격 여부와 사유. 본문을 못 읽었으면 절대 승격하지 않는다(fail-closed)."""
    if not row.get("ok"):
        return False, "II절 본문을 읽지 못했다(%s) — 근거 없이 넣지 않는다" % (row.get("note") or "사유 미상")
    s, mid, neg = row.get("strong", 0), row.get("mid", 0), row.get("neg", 0)
    sc = score_of(row)
    ref = row.get("kepco", 0) + sum((row.get("mentions") or {}).values())
    negs = ", ".join(list(row.get("neg_terms") or {})[:4])
    if s == 0:
        return False, ("II절 본문에 전력망 고유 낱말이 하나도 없다(전력망 관련 낱말은 %d회, "
                       "비전력망 문맥 %d회%s) — 같은 낱말을 다른 산업에서 쓴다"
                       % (mid, neg, (": " + negs) if negs else ""))
    if not row.get("evidence"):
        return False, "인용문을 뽑지 못했다 — 증거 없는 승격은 하지 않는다"
    if neg > sc * NEG_RATIO:
        return False, ("점수 %d(고유 %d·관련 %d)보다 비전력망 문맥(%s)이 %d회로 압도한다 — "
                       "같은 낱말을 다른 산업에서 쓴다" % (sc, s, mid, negs, neg))
    if row.get("gen", 0) > s:
        return False, ("본문이 전력을 **파는** 쪽을 말한다(%s 등 %d회 > 전력망 고유 낱말 %d회) — "
                       "발전사업자·발주처는 공급망이 아니다(스펙 ④)"
                       % (", ".join(list(row.get("gen_terms") or {})[:3]), row["gen"], s))
    if mid < PROMOTE_MID:
        return False, ("전력망 고유 낱말은 %d회 나오는데(%s) 전력기기 낱말(변압기·차단기·배전…)이 "
                       "한 번도 없다 — 자기 제품이 아니라 남의 산업을 말하는 것이다"
                       % (s, ", ".join(list(row.get("terms") or {})[:3])))
    top = ", ".join("%s %d" % kv for kv in list((row.get("terms") or {}).items())[:4])
    if sc >= PROMOTE_SCORE:
        return True, "점수 %d(고유 낱말 %d회: %s · 관련 낱말 %d회)" % (sc, s, top, mid)
    if ref >= PROMOTE_REF and sc >= PROMOTE_SCORE_WITH_REF:
        return True, "점수 %d(고유 낱말 %d회: %s) + 한전·전력기기 체계업체 언급 %d회(%s)" % (
            sc, s, top, ref, ", ".join(sorted((row.get("mentions") or {}).keys())) or "한국전력공사")
    return False, ("점수가 %d뿐이다(고유 낱말 %d회·관련 낱말 %d회, 승격선 %d, 한전·체계업체 언급이 "
                   "받치면 %d) — 부수 언급으로 본다"
                   % (sc, s, mid, PROMOTE_SCORE, PROMOTE_SCORE_WITH_REF))


def role_for(row):
    """역할 힌트. 진짜 근거는 수주표·계약 공시다(kgrid_universe 머리말 그대로)."""
    ind, prod = row.get("industry") or "", row.get("product") or ""
    terms = " ".join((row.get("terms") or {}).keys())
    if ind == "절연선 및 케이블 제조업" or re.search(r"전력선|전력케이블|해저케이블|초고압\s?케이블", prod + terms):
        return "cable"
    if (ind == "전기 및 통신 공사업"
            or re.search(r"전기공사|정비\s*용역|발전설비\s*정비|유지보수", prod)) \
            and not re.search(r"제조|생산", prod):
        return "epc"
    if re.search(r"변압기|차단기|개폐기|배전반|수배전|스위치기어|인버터|PCS|전력변환", prod, re.I):
        return "maker"
    # KIND 문구는 소재인데 **본문에서 기기를 만든다**고 말하는 경우가 있다 — KBI메탈 024840 은
    # 제품 문구가 `동ROD, 모터코어`인데 본문에 "변압기 사업부인 KBI일렉트릭(주)은 … 몰드변압기
    # 제조를 목적으로 설립된 회사"가 나온다(2026.04 지분 100% 취득).
    # `주상변압기`는 여기서 빼 뒀다 — 금구류 회사가 **설치 대상**으로 부르는 말이다
    # (보성파워텍 006910 본문에 2회. 그 회사는 기기가 아니라 자재를 만든다).
    n = sum(v for k, v in (row.get("terms") or {}).items()
            if re.match(r"몰드\s?변압기|유입\s?변압기|건식\s?변압기|전력용\s?변압기|"
                        r"배전용\s?변압기|특고압\s?변압기|초고압\s?변압기|GIS\s?차단기|"
                        r"GIS\s?개폐장치|가스절연개폐장치", k, re.I))
    if n >= 2:
        return "maker"
    return "part"                       # 본문으로 들어온 것은 대개 부품·소재다(스펙 ③)


# ── 행 저장소 ───────────────────────────────────────────────

def load_rows():
    if not has_asset(ROWS):
        return {}
    return load_asset(ROWS).get("rows") or {}


def load_failed():
    if not has_asset(ROWS):
        return {}
    return load_asset(ROWS).get("failed") or {}


def save_rows(rows, quarter, failed=None):
    d = {"quarter": quarter, "n": len(rows), "scanned_at": time.strftime("%Y-%m-%d"),
         "rows": {k: rows[k] for k in sorted(rows)}}
    # 못 읽은 회사도 남긴다 — 조용히 사라지면 커버리지가 거짓말을 한다(COMMON §0-2).
    # 다만 **행은 캐시하지 않으므로** 다시 --probe 하면 이들만 재시도한다.
    d["failed"] = {k: failed[k] for k in sorted(failed)} if failed else (load_failed() or {})
    write_asset(ROWS, d)


def _run(cands, quarter, rows, tag, log):
    """후보를 순차로 읽는다. DART 는 프로세스 하나로만 두드린다(COMMON §2)."""
    done = ok = 0
    failed = dict(load_failed())
    for r in cands:
        failed.pop(r["stock"], None)
        row = probe_one(r, quarter)
        if r["stock"] in EXTRA:
            row["extra"] = EXTRA[r["stock"]]
        if row["ok"]:
            ok += 1
            rows[r["stock"]] = row
        else:
            failed[r["stock"]] = {"stock": r["stock"], "name": r["name"],
                                  "industry": r.get("industry", ""),
                                  "product": r.get("product", ""), "note": row["note"]}
            log.write("  [warn] %s %s — %s\n" % (r["stock"], r["name"][:14], row["note"]))
        done += 1
        if done % 10 == 0:
            save_rows(rows, quarter, failed)          # 중간 저장 — 끊겨도 이어서 돈다
            log.write("  … %s %d/%d (읽음 %d)\n" % (tag, done, len(cands), ok))
            log.flush()
    save_rows(rows, quarter, failed)
    log.write("%s 완료: %d사 시도 · %d사 본문 확보 · %d사 못 읽음\n"
              % (tag, done, ok, len(failed)))
    return rows


def probe(quarter, limit=None, log=sys.stderr):
    recs = parse_kind(_get(KIND_URL))
    universe = load_universe()
    cands = pool(recs, universe)
    rows = load_rows()
    todo = [r for r in cands if r["stock"] not in rows]
    log.write("후보 %d사(모집단 %d 제외) · 이미 읽은 것 %d · 이번에 읽을 것 %d\n"
              % (len(cands), len(universe), len(cands) - len(todo), len(todo)))
    if limit:
        todo = todo[:limit]
    return _run(todo, quarter, rows, "probe", log)


def rejudge(quarter, limit=None, log=sys.stderr):
    """이미 모집단에 있는 회사도 본문으로 다시 본다.

    KIND 주요제품 한 줄만 보고 넣은 종목이 실제로 전력망인지 원문이 말하게 한다. 여기서 나온
    '제외 권고'는 모집단을 **지우지 않고** rejected 에 인용문과 함께 남긴다 — 커버리지 페이지가
    "왜 빠졌는지"를 보여야 하기 때문이다(스펙 §화면).
    """
    universe = load_universe()
    rows = load_rows()
    todo = [r for r in universe
            if r.get("role") != "holding" and rows.get(r["stock"], {}).get("scope") != "universe"]
    log.write("모집단 %d사 중 재판정 대상 %d사\n" % (len(universe), len(todo)))
    if limit:
        todo = todo[:limit]
    for r in todo:
        rows.pop(r["stock"], None)
    rows = _run(todo, quarter, rows, "rejudge", log)
    for r in todo:
        if r["stock"] in rows:
            rows[r["stock"]]["scope"] = "universe"
            rows[r["stock"]]["universe_source"] = r.get("source", "")
            rows[r["stock"]]["universe_reason"] = r.get("reason", "")
    save_rows(rows, quarter)
    return rows


# ── 산출 ────────────────────────────────────────────────────

def build(log=sys.stderr):
    """쌓인 증거만으로 판정한다 — DART 를 두드리지 않는다.

    universe_probe.json 의 promoted 는 kgrid_universe._probe_promoted() 가 읽는 모양이다:
      {"promoted": {"<종목코드>": {"role","reason","evidence",...}}, "rejected":[...], "candidates":N}
    """
    d = load_asset(ROWS)
    rows, quarter = d.get("rows") or {}, d.get("quarter") or ""
    remeasure(rows, quarter, log)
    save_rows(rows, quarter)
    promoted, rejected, kept = {}, [], []
    for st in sorted(rows):
        row = rows[st]
        ok, why = judge(row)
        in_uni = row.get("scope") == "universe"
        base = {"stock": st, "name": row["name"], "industry": row.get("industry", ""),
                "product": row.get("product", ""), "strong": row.get("strong", 0),
                "mid": row.get("mid", 0), "neg": row.get("neg", 0),
                "gen": row.get("gen", 0), "gen_terms": row.get("gen_terms") or {},
                "kepco": row.get("kepco", 0), "mentions": row.get("mentions") or {},
                "terms": row.get("terms") or {}, "neg_terms": row.get("neg_terms") or {},
                "rcp": row.get("rcp", ""), "title": row.get("title", ""),
                "score": score_of(row), "evidence": row.get("evidence") or []}
        if row.get("extra"):
            base["extra"] = row["extra"]
        if ok and not in_uni:
            promoted[st] = dict(base, role=role_for(row),
                                reason="탐색 — %s %s%s" % (row.get("title") or "정기보고서", why,
                                                         " · " + row["extra"] if row.get("extra") else ""))
            continue
        if ok and in_uni:
            kept.append(dict(base, verdict="유지", reason=why,
                             universe_source=row.get("universe_source", "")))
            continue
        rejected.append(dict(base, verdict=("제외 권고" if in_uni else "제외"), reason=why,
                             scope=("universe" if in_uni else "candidate"),
                             universe_source=row.get("universe_source", ""),
                             universe_reason=row.get("universe_reason", "")))
    rejected.sort(key=lambda x: (x["scope"] != "universe", -x["strong"], x["stock"]))
    failed = [d.get("failed", {})[k] for k in sorted(d.get("failed") or {})]
    out = {"quarter": quarter, "rule": RULE, "candidates": len(rows),
           "built_at": time.strftime("%Y-%m-%d"),
           "promoted": promoted, "rejected": rejected, "kept": kept, "failed": failed}
    write_asset("universe_probe.json", out)
    log.write("후보(본문 확보) %d · 승격 %d · 제외 %d · 모집단 유지 %d · 못 읽음 %d "
              "→ assets/universe_probe.json\n"
              % (len(rows), len(promoted), len(rejected), len(kept), len(failed)))
    for st, p in sorted(promoted.items()):
        log.write("  [승격] %s %-14s %-5s s=%-3d %s\n"
                  % (st, p["name"][:14], p["role"], p["strong"], p["reason"][:80]))
    for r in rejected:
        if r["scope"] == "universe":
            log.write("  [제외권고] %s %-14s s=%-3d neg=%-3d %s\n"
                      % (r["stock"], r["name"][:14], r["strong"], r["neg"], r["reason"][:80]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="후보 II절 본문 수집(이어 돌리기)")
    ap.add_argument("--rejudge", action="store_true", help="모집단 회사도 본문으로 다시 본다")
    ap.add_argument("--build", action="store_true", help="쌓인 증거로 판정 → universe_probe.json")
    ap.add_argument("--pool-only", action="store_true")
    ap.add_argument("--quarter", default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    q = a.quarter or latest_quarter()
    if a.pool_only:
        cands = pool(parse_kind(_get(KIND_URL)), load_universe())
        print("후보 %d사" % len(cands))
        for r in cands:
            print("  %s %-16s %-24s %s" % (r["stock"], r["name"][:16], (r["industry"] or "")[:24],
                                           (r["product"] or "")[:46]))
        return
    if a.rejudge:
        rejudge(q, a.limit)
    if a.probe:
        probe(q, a.limit)
    if a.build or ((a.probe or a.rejudge) and not a.limit):
        build()
    if not (a.probe or a.rejudge or a.build):
        ap.error("--probe · --rejudge · --build 중 하나를 고르시오")


if __name__ == "__main__":
    sys.exit(main())
