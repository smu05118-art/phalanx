#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_contracts — 사업 단위 원장을 수시공시 「단일판매ㆍ공급계약체결」(I001)에서 만든다.

**이 탭의 1차 원장이다.** 정기보고서 II-4 수주표는 보안 때문에 품목이 안 나오고 잔액 한 줄인
회사도 있다(FINDINGS §5). 무기체계·계약유형·계약상대·계약기간은 오직 이 공시에만 있다.

조선 탭과 결정적으로 다른 점(FINDINGS §1 실측 19건):
  · **계약상대가 공개다.** 익명은 19건 중 1건뿐(조선은 81%가 '○○ 소재 선사').
    상대는 네 갈래 — `GOV`(방위사업청·국방과학연구소·국방기술진흥연구소) ·
    `PRIME`(국내 체계업체 하도급) · `G2G`(해외 국방부) · `FOREIGN`(해외 업체).
    → 부품사→체계업체 연결이 **추정이 아니라 공시로** 잡힌다.
  · **계약기간이 다년도다**(3~10년). 종료일이 인도 예정 시점이라 '선표'의 대용이 된다.
    다만 종료일 칸에 `계약종료일 변경(연장)` 같은 **문구**가 들어온 정정공시가 있다
    (LIG 20260423800410) — 날짜로 파싱되지 않으면 기간을 만들지 않는다(fail-closed).
  · **계약명에 유형이 적힌다** — 체계개발/최초양산/후속양산/성능개량/PBL(FINDINGS §3).

방산업체도 민수 계약을 공시한다(현대로템 `모로코 철도청`, KAI `Vertical Aerospace`).
계통이 민수로 잡히면 `civil=True` 로 남겨 방산 집계에서 뺀다 — 버리지 않는다(커버리지에 보인다).

캐시: assets/contracts/<종목>/<rcpNo>.json — 원문 (라벨,값) 전부 보존(`kv`).
분류는 **빌드 때 캐시에서 다시** 한다(사전이 자라도 재수집이 필요 없게, COMMON §0-4).

    python3 kdef_contracts.py --collect --from 20200101      # 모집단 전부
    python3 kdef_contracts.py --build                        # 캐시 → assets/contracts.json
"""
import argparse
import json
import os
import re
import sys
import time

from kdef_lib import (ASSETS, atomic_write, fetch_section, has_asset, load_asset,
                      num_of, parse_tables, search_reports, toc, write_asset)
from kdef_universe import load as load_universe

CACHE = os.path.join(ASSETS, "contracts")

# ── 계약상대 갈래 ───────────────────────────────────────────
# 원문 실례는 FINDINGS §1. `대한민국 방위사업청`·`방위사업청(Defense Acquisition…)` 처럼
# 영문 병기가 붙으므로 부분일치로 본다.
_GOV = re.compile(r"방위사업청|국방과학연구소|국방기술진흥연구소|대한민국\s*국방부|육군|해군|공군|해병대|"
                  r"국군|조달청|경찰청|해양경찰|산림청|소방청|관세청|한국수력원자력|한국전력|"
                  r"대한무역투자진흥공사|KOTRA|한국항공우주연구원|한국원자력|국가정보원|"
                  r"정부출연|출연연구기관|대한민국\s*정부|한국\s*정부|Defense Acquisition Program|DAPA|"
                  r"Korea Aerospace Research|KARI\b|"   # 한국항공우주연구원 영문(KAI 가 아니다)
                  # 국내 정부 시설·기관 — `정부통합데이터센터`·`행정안전부 정부청사관리본부`·`정부세종청사`.
                  # `정부`가 앞에 붙은 합성어는 국내 기관이다(해외 정부는 `○○ 정부`로 뒤에 온다).
                  r"정부(?:통합|청사|세종|대전|과천|전산|합동|기관|부처)")
# 국방 조달기관(방위사업청·국과연·국방부·각군) — 민수 계약을 내지 않는 발주처. 계약명이 민수
# 어휘(발전기세트)로 읽혀도 이 상대면 민수가 아니다(휴니드 `발전기세트(제어장치 포함)` 실측).
_DEF_BUYER = re.compile(r"방위사업청|국방과학연구소|국방기술진흥연구소|국방부|육군|해군|공군|해병대|"
                        r"국군|DAPA|Ministry of (National )?Defen[cs]e|국방물자청|군비청")
# 해외 국방부 — `크로아티아 국방부 (The Ministry of Defence…)`. 우리 국방부와 섞이지 않게
# `대한민국`이 함께 적힌 건은 GOV 로 보낸다.
# 해외 국방 조달기관은 이름이 나라마다 다르다 — `노르웨이 국방물자청(NDMA)`·`폴란드 군비청`.
# 기업으로 분류하면 방산 수출(G2G)이 통째로 '해외 기업'이 된다(실측).
# `폴란드 정부`·`이라크 정부`·`말레이시아 정부`·`해외 정부기관`은 낱말이 `정부`뿐이라 국내 기업
# (DOMESTIC)으로 떨어져 있었다(실측 4건 2,770억 — 해궁·KUH 수출이 내수로 셈). `정부`를 더하되
# **맨 `정부`는 fail-open 이다** — 앞으로 들어올 국내 상대 `정부통합데이터센터`·`정부세종청사`가
# 해외 정부(수출)로 셈해진다(규약: 모르면 내수). 그래서 두 꼴만 본다 —
#   ① `해외|외국|국외 정부(기관)` ② `○○ 정부(기관)`가 **이름 끝**(괄호 영문 병기 허용)에 오는 꼴.
# `정부출연연구기관`(국내, 국과연 익명 표기)·`정부○○센터`는 _GOV 로, `시정부`(에드먼턴·타이중 트램
# 발주)·`지방정부`는 국방 조달이 아니라 FOREIGN/DOMESTIC 으로 남긴다.
_G2G = re.compile(r"국방부|국방물자청|국방조달|군비청|방위성|방위장비청|국방획득|국방부처|"
                  r"(?:해외|외국|국외)\s*정부(?:기관)?|[가-힣A-Za-z]{2,}\s*정부(?:기관)?\s*(?:\([^)]*\))?\s*$|"
                  r"Government|"
                  r"Ministry of Defen[cs]e|Ministry of National Defen[cs]e|Defence Ministry|"
                  r"Defen[cs]e Materiel|Armament Agency|Defen[cs]e Acquisition(?! Program Admin)")
_G2G_CITY = re.compile(r"시\s*정부|주\s*정부|지방\s*정부|지자체|City|Municipal|시청|도청|군청")
_KR = re.compile(r"대한민국|Republic of Korea|한국\s*정부|우리\s*정부|우리나라")
# 익명 표기 — 실측 19건 중 1건(KAI `해외 완제기 업체`). 이름이 없으면 없다고 적는다.
_ANON = re.compile(r"비공개|공시유보|유보|익명|영업비밀|소재\s*업체|소재\s*법인|"
                   r"해외\s*[^,()]{0,8}(?:업체|고객|법인|바이어)|국내\s*[^,()]{0,8}업체")
_LATIN = re.compile(r"[A-Za-z]{4,}")
# 국내 법인 표기 — `현대위아(주) (HYUNDAI WIA CORP)`·`기아 주식회사(KIA CORPORATION)`·`에이치디현대중공업(주)
# (HD HYUNDAI HEAVY INDUSTRIES…)`는 영문 병기 때문에 FOREIGN(직수출)으로 셈해졌다(실측). 국내 법인 접미가
# 있고 라틴 문자가 **괄호 안에만** 있으면 국내 기업이다. 괄호 밖에 영문이 있는 외국 법인(`Larsen & Toubro
# Limited (L&T)`)·국호를 한글로 적은 외국 발주처(`터키 이스탄불 市 (Istanbul…)`, 접미 없음)는 그대로 FOREIGN.
_KO_CORP = re.compile(r"\(주\)|㈜|주식회사|\(유\)|유한회사|유한책임회사")
_PAREN = re.compile(r"\([^)]*\)?")
# 체계업체 이름(정식·약칭·구명) → 종목코드. 하도급 계약의 상대를 여기서 되짚는다.
PRIME_NAMES = {
    # 한화디펜스(2022-11 한화에어로스페이스에 합병)·한화방산도 012450 — 합병 전 공시의 상대다(실측 K56·30mm).
    "012450": r"한화에어로스페이스|한화\s*에어로|Hanwha\s*Aerospace|한화디펜스|Hanwha\s*Defense|한화방산",
    # `한국항공우주연구원`(KARI, 정부출연연)은 KAI 가 아니다 — `한국항공우주` 부분일치가 연구원을 체계업체로
    # 읽어 누리호·정지궤도 위성 계약(비츠로넥스텍·제노코)이 KAI 하도급으로 묶였다(실측 8건).
    "047810": r"한국항공우주산업|한국항공우주(?!\s*연구원)|KAI\b|Korea Aerospace(?!\s*Research)",
    # LIG넥스원은 2026년 LIG디펜스앤에어로스페이스(LIG D&A)로 이름을 바꿨다 — 한글 풀이표기와 약칭도 받는다.
    "079550": r"LIG디펜스앤에어로스페이스|엘아이지디펜스앤에어로스페이스|LIG\s*D&A|LIG디앤에이|LIG넥스원|LIG\s*Nex1|엘아이지넥스원",
    "064350": r"현대로템|Hyundai\s*Rotem",
    "272210": r"한화시스템|Hanwha\s*Systems",
    "042660": r"한화오션|대우조선해양|Hanwha\s*Ocean",
    "103140": r"풍산|Poongsan",
    "000880": r"\(주\)한화(?!에어로|시스템|오션)|주식회사 한화(?!에어로|시스템|오션)",
}


def party_kind(party):
    """계약상대 문자열 → (갈래, 체계업체 종목코드 or None). 못 읽으면 ('UNKNOWN', None)."""
    p = (party or "").strip()
    if not p or p in ("-", "—"):
        return "UNKNOWN", None
    if _ANON.search(p):
        return "ANON", None
    for stock, pat in PRIME_NAMES.items():
        if re.search(pat, p, re.I):
            return "PRIME", stock
    if _G2G.search(p) and not _KR.search(p) and not _G2G_CITY.search(p):
        return "G2G", None       # 해외 국방부. FMS 인지 직수출인지는 공시에 없다(FINDINGS §9)
    if _GOV.search(p):
        return "GOV", None
    if _KO_CORP.search(p) and not _LATIN.search(_PAREN.sub(" ", p)):
        return "DOMESTIC", None  # 국내 법인 + 괄호 영문 병기
    if _LATIN.search(p):
        return "FOREIGN", None
    return "DOMESTIC", None


# ── 계통(domain)·계약유형 ───────────────────────────────────

def _domains():
    """assets/domains.json → (키워드, domain id) 목록. **우선순위 → 길이** 순.

    길이만으로 고르면 `천궁Ⅱ 다기능레이다 수출`이 ISR 로 간다. 이 계약이 속한 무기체계는
    천궁(유도무기)이므로 체계 이름(prio 90)이 일반 어휘(prio 50)를 이겨야 한다."""
    pairs = []
    for d in load_asset("domains.json")["domains"]:
        for k in d["keywords"]:
            pairs.append((k["kw"].lower().replace(" ", ""), d["id"], k["prio"]))
    pairs.sort(key=lambda p: (-p[2], -len(p[0])))
    return [(kw, did) for kw, did, _ in pairs]


_DOM_PAIRS = None

# 민수 판정을 **되짚는** 조건 — 민수 어휘가 맞아도 계약명에 군 용도가 적혔거나(`발전기세트
# (디젤엔진식)[TICN용]`·`해군함정용 조타기`) 상대가 국방 조달기관이면 민수가 아니다. 그때는
# 민수 어휘를 건너뛰고 다음 계통 어휘를 찾는다(없으면 None — 방산 미상).
_CIVIL_NEG = re.compile(r"TICN|해군|함정|군용|군수용|방산용|방위사업|국방|육군|공군|해경|경비정", re.I)
# 민수로 **단정할 수 없는** 그룹 내 설비 계약 — 한화에어로스페이스(체계업체)가 발주한 `MCS Plant 구축
# 공사`(한화오션 4,245억)·`MCS Plant 지능화 물류 시스템 구축`(한화시스템 967억). 공시 본문(kv)에 용도가
# 없고, MCS 는 한화의 155mm 모듈화장약(Modular Charge System) 약어일 수 있어 방산 생산설비일 가능성이
# 있다. 일반 낱말 `Plant`·`시스템 구축` 하나로 5,212억을 방산 합계에서 빼지 않는다 — 민수 어휘를 건너뛰어
# '계통 미상'(방산 집계 안)에 두고 사람 판정 큐 후보로 남긴다(HANDOFF ③). 같은 이유로 build_dicts 의
# CIVIL 어휘는 `Plant` 홀로가 아니라 `H2 Plant`·`LNG Plant` 구절만 쓴다.
_CIVIL_HOLD = re.compile(r"MCS\s*Plant", re.I)


def domain_of(name, party=None):
    """체결계약명 → 계통 id. 못 찾으면 None(추정하지 않는다).

    party 를 주면 민수 되짚기에 쓴다(국방 조달기관이 발주한 계약은 민수로 두지 않는다)."""
    global _DOM_PAIRS
    if _DOM_PAIRS is None:
        _DOM_PAIRS = _domains()
    t = (name or "").lower().replace(" ", "")
    skip_civil = (bool(_CIVIL_NEG.search(name or "")) or bool(_CIVIL_HOLD.search(name or ""))
                  or bool(_DEF_BUYER.search(party or "")))
    for kw, did in _DOM_PAIRS:
        if kw and kw in t:
            if did == "CIVIL" and skip_civil:
                continue
            return did
    return None


# 계통을 못 읽은 계약 가운데 **부품 이름**이 적힌 것 — 무기체계 이름이 없어 계통을 지어내지
# 않는 편이 맞고(HANDOFF ③), 대신 '부품(계통 미상)'이라고 적어 '미상'과 가른다.
# 어휘는 부품 사전(parts_taxonomy.kw) + 부품 계약명에 흔한 일반 낱말.
_PART_WORDS = re.compile(r"부품|조립체|구성품|모듈|장치|유닛|키트|kit|chip|칩|connector|커넥터|cable|"
                         r"케이블|센서|안테나|소재|자재|증폭기|조준경|엔진|변속기|측정기|측정장치|필터|"
                         r"하네스|어셈블리|assy|프로브|probe|밸브|피팅|fitting|베어링|기어|감속기|"
                         r"단말|송신기|수신기|처리기|탐색기|신관|포신|탄체|날개|동체|구동기|작동기", re.I)
_PART_KW = None


def part_hint(name):
    """계통 미상 계약명이 부품 이름을 품었는가 → 'PART' | None."""
    global _PART_KW
    if _PART_KW is None:
        try:
            _PART_KW = sorted({w.lower().replace(" ", "")
                               for c in load_asset("parts_taxonomy.json")["cats"]
                               for w in c["kw"] if len(w) >= 3})
        except FileNotFoundError:
            _PART_KW = []
    n = name or ""
    if _PART_WORDS.search(n):
        return "PART"
    t = n.lower().replace(" ", "")
    return "PART" if any(k in t for k in _PART_KW) else None


def _ctypes():
    return [(re.compile(c["pattern"]), c["id"]) for c in load_asset("contract_types.json")["types"]]


_CT = None
# 수출사업 **이행계약**임을 적는 낱말 — `수출사업`·`수출계약`은 판로 낱말이라 이것과 가른다.
_EXEC_WORDS = re.compile(r"실행\s*계약|이행\s*약정|이행\s*계약")


def _ctypes_for(party_kind):
    """상대 갈래에 맞춘 판정 순서. G2G 는 EXPORT_EXEC 를 SUPPLY **앞**에 둔다."""
    if party_kind != "G2G":
        return _CT
    ee = [x for x in _CT if x[1] == "EXPORT_EXEC"]
    rest = [x for x in _CT if x[1] != "EXPORT_EXEC"]
    i = next((k for k, x in enumerate(rest) if x[1] == "SUPPLY"), len(rest))
    return rest[:i] + ee + rest[i:]


def ctype_of(name, party_kind=None):
    """체결계약명 → 계약유형 id(FINDINGS §3: 계약명에 그대로 적힌다). 못 읽으면 'UNKNOWN'.

    유형 축은 **계약의 성격**, 판로 축(export_of)은 **수출 여부**다 — 둘을 여기서 코드로 가른다.
    party_kind 가 있으면 EXPORT_EXEC 판정만 상대에 따라 달라진다:
      · G2G(해외 정부): 이름이 EXPORT_EXEC 패턴에 맞으면 SUPPLY 보다 **먼저** EXPORT_EXEC —
        `폴란드 FA-50 항공기 공급 사업 실행계약`(4.21조)은 해외 정부의 물품구매가 아니라 정부 간 수출사업의
        실행계약이다(해외 정부가 부품 물품구매를 공시 상대로 나오는 일은 없다). 양산·개량·개발·PBL 낱말이
        있으면 여전히 그쪽. 유형 낱말이 전혀 없는 G2G(`잠수함 3척`·`필리핀 FA-50 추가 사업`)도 EXPORT_EXEC
        — 유형 미상 222건 가운데 금액이 가장 큰 묶음(G2G 6건 16.8조)이 이렇게 풀린다(실측).
      · PRIME(국내 체계업체 상대): EXPORT_EXEC 금지 — `T-50 수출사업용 엔진`·`사우디 MSAM-Ⅱ MFR 수출사업
        … 조립체 외 3건 계약`은 부품사의 공급계약이고 판로는 export_kind=indirect 가 이미 표시한다.
        공급 낱말이 없으면 UNKNOWN(지어내지 않는다).
      · DOMESTIC(국내 기업): `수출사업|수출계약`만으로는 EXPORT_EXEC 가 아니다(판로 낱말). `실행계약·
        이행약정·이행계약`이 적혀야 한다. GOV(KOTRA `방산수출 이행약정`)·FOREIGN·ANON 은 이름대로."""
    global _CT
    if _CT is None:
        _CT = _ctypes()
    n = name or ""
    has_exec = any(cid == "EXPORT_EXEC" for _, cid in _CT)
    for rx, cid in _ctypes_for(party_kind):
        if not rx.search(n):
            continue
        if cid == "EXPORT_EXEC":
            if party_kind == "PRIME":
                continue
            if party_kind == "DOMESTIC" and not _EXEC_WORDS.search(n):
                continue
        return cid
    if party_kind == "G2G" and has_exec:
        return "EXPORT_EXEC"
    return "UNKNOWN"


# ── 수출 판정(판로) ─────────────────────────────────────────
# 수출은 유형이 아니라 **판로**다. 공시에 있는 세 근거를 모두 쓴다 —
#   ① 계약상대가 해외 정부(G2G)·해외 기업(FOREIGN)·`해외 ○○ 업체`(ANON)          → 직수출
#   ② 「판매ㆍ공급지역」이 국내가 아님(`미국`·`아랍에미레이트`·`폴란드`…)             → 직수출
#   ③ 상대가 국내 체계업체(PRIME)인데 계약명에 `수출`이 적힘(`T-50 수출사업용 엔진`) → 간접수출
# 상대만 보면 107건 31.5조, 지역·간접수출까지 보면 ≈160건 43조가 수출이다(2026-10 실측).
# 지역 열은 납품처 이름(`한화시스템 구미사업장`)·주소(`충청남도 보령시`)·`지정 우주궤도`로
# 오염돼 있어 **국내 화이트리스트**에 걸리지 않는 값만 해외로 본다(fail-closed: 모르면 내수).
#   `발주자 지정납품장소`·`"원사업자"의 지정 장소`·`충남 계룡시`·`충남 논산 계룡대 국방통합데이터센터`
#   도 국내다(실측 6건) — '지정'·'납품장소'·도 약칭·국방 시설을 화이트리스트에 둔다.
_REGION_DOMESTIC = re.compile(
    r"대한민국|국내|한국|^-$|^$|사업장|㈜|\(주\)|주식회사|납품처|본사|공장|지정|납품장소|도착도|구매자|주소|궤도|"
    r"특별시|광역시|특별자치|[가-힣]{2}(남|북)도|경기도|강원도|제주|중공업|조선|산업$|"
    r"충남|충북|전남|전북|경남|경북|경기|강원|서울|부산|대구|인천|광주|대전|울산|세종|계룡|국방|"
    r"[가-힣]+(시|군|구)\s+[가-힣]+(시|군|구|읍|면|동)|[가-힣]{2,}(시|군)$")
_ANON_ABROAD = re.compile(r"해외|국외|외국")


def region_is_foreign(region):
    """「판매ㆍ공급지역」이 해외인가 — 국내 화이트리스트에 하나도 안 걸릴 때만 True.

    `대한민국외 해외지점`·`국외지점`처럼 '해외·국외'를 적은 값은 국호가 함께 있어도 해외다(실측 3건)."""
    r = re.sub(r"\s+", " ", (region or "")).strip()
    if not r:
        return False
    if _ANON_ABROAD.search(r):
        return True
    return not _REGION_DOMESTIC.search(r)


def export_of(party_kind, party, region, name):
    """→ (export: bool, kind: 'direct'|'indirect'|'', basis: 'party'|'region'|'name'|'')."""
    if party_kind in ("G2G", "FOREIGN"):
        return True, "direct", "party"
    if party_kind == "ANON" and _ANON_ABROAD.search(party or ""):
        return True, "direct", "party"
    foreign = region_is_foreign(region)
    if party_kind == "PRIME":
        if foreign:
            return True, "indirect", "region"
        if "수출" in (name or ""):
            return True, "indirect", "name"
        return False, "", ""
    if foreign:
        return True, "direct", "region"
    return False, "", ""


_DATE = re.compile(r"(\d{4})[-.\s/]*(\d{1,2})[-.\s/]*(\d{1,2})")


def _date(s):
    """`2026-07-24` 꼴만 날짜로 본다. `계약종료일 변경(연장)` 같은 문구는 None(fail-closed)."""
    m = _DATE.search(s or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if not (1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def _years(start, end):
    if not start or not end or end <= start:
        return None
    import datetime
    a = datetime.date(*(int(x) for x in start.split("-")))
    b = datetime.date(*(int(x) for x in end.split("-")))
    return round((b - a).days / 365.25, 1)


# ── 공시 본문 → 필드 ───────────────────────────────────────

def _norm_key(key):
    return re.sub(r"^\s*[\d]+\.\s*|^\s*-\s*|[\s　ㆍ·]", "", key)


def _kv(html):
    """(항목, 세부항목, 값) 표 → (정규화 사전, 원문 (라벨,값) 목록)."""
    kv, raw = {}, []
    for t in parse_tables(html):
        for row in t["rows"]:
            cells = [c.strip() for c in row]
            if len(cells) < 2:
                continue
            val = cells[-1]
            labels = [c for c in cells[:-1] if c and c != val]
            key = " ".join(dict.fromkeys(labels))
            if not key:
                continue
            raw.append((key, val))
            kv.setdefault(_norm_key(key), val)
    return kv, raw


def _kv_from_raw(raw):
    kv = {}
    for k, v in raw:
        kv.setdefault(_norm_key(k), v)
    return kv


def _find(kv, *needles):
    """needle 을 모두 품은 라벨 중 **가장 짧은** 라벨의 값 — 정정공시의 정정 표(긴 라벨)보다
    본표(짧은 라벨)가 이긴다. 라벨은 공백이 지워진 상태이므로 needle 도 지워서 본다
    (`"계약금액 총액(원)"` 을 그대로 찾으면 영영 못 찾는다 — 실측 버그)."""
    needles = [_norm_key(n) for n in needles]
    hits = [(len(k), i, v) for i, (k, v) in enumerate(kv.items()) if all(n in k for n in needles)]
    return min(hits)[2] if hits else None


# 국내 방산 계약의 대금 성격 — 원문 문구 그대로(FINDINGS §4). 이익률 수치는 공시에 없다.
_DEF_PAY = re.compile(r"방위산업에\s*관한\s*착수금\s*및\s*중도금\s*지급규칙|착수금\s*및\s*중도금")


_NUMTOK = re.compile(r"-?[\d,]*\d")


def _num1(v):
    """값에 숫자 토큰이 **하나뿐일 때만** 숫자로 읽는다(뭉쳐 온 정정행 방어, fail-closed)."""
    if v is None:
        return None
    toks = [t for t in _NUMTOK.findall(str(v)) if any(c.isdigit() for c in t)]
    return num_of(v) if len(toks) == 1 else None


def _fields_from_kv(kv):
    # 양식이 두 갈래다 — 유가증권 「- 체결계약명」, 코스닥 「1. 판매ㆍ공급계약 내용」.
    # 코스닥 양식을 안 보면 계약명이 통째로 빈칸이 된다(실측 57건: 스페코·한일단조 등).
    name = (_find(kv, "체결계약명") or _find(kv, "계약명")
            or _find(kv, "판매", "공급계약", "내용") or _find(kv, "공급계약 내용") or "")
    if not name and _find(kv, "판매공급계약구분"):
        name = _find(kv, "세부내용") or ""
    # 정정공시에는 라벨과 값이 **뭉쳐 온** 행이 있다(`…계약금액 총액(원) - 매출액 대비(%) …` /
    # 값 `86,764,475,454 86,764,475,454 188.08`). 그대로 num_of 하면 숫자가 이어 붙어
    # 8.7×10^24 원짜리 계약이 된다(실측 5건) — 숫자 토큰이 둘 이상인 값은 쓰지 않는다.
    amt_krw = _num1(_find(kv, "계약금액총액(원)") or _find(kv, "계약금액(원)")
                    or _find(kv, "확정계약금액") or _find(kv, "계약금액") or "")
    party = _find(kv, "계약상대") or ""
    kind, prime = party_kind(party)
    start = _date(_find(kv, "계약기간", "시작") or _find(kv, "시작일") or "")
    end = _date(_find(kv, "계약기간", "종료") or _find(kv, "종료일") or "")
    payterm = _find(kv, "대금지급") or ""
    dom = domain_of(name, party)
    region = _find(kv, "판매", "지역") or _find(kv, "공급지역") or ""
    exp, exp_kind, exp_basis = export_of(kind, party, region, name)
    return {
        "name": name,
        "domain": dom,
        "domain_hint": (part_hint(name) if dom is None else None),
        "ctype": ctype_of(name, kind),
        "civil": dom == "CIVIL",
        "amt_krw_m": (round(amt_krw / 1e6, 3) if amt_krw is not None else None),   # 백만원
        "rev_ratio": num_of(_find(kv, "매출액대비") or ""),
        "party": party,
        "party_kind": kind,
        "party_prime": prime,
        "region": region,
        "export": exp,
        "export_kind": exp_kind,
        "export_basis": exp_basis,
        "start": start or "",
        "end": end or "",
        "years": _years(start, end),
        "end_raw": (_find(kv, "계약기간", "종료") or _find(kv, "종료일") or ""),
        "signed": _date(_find(kv, "수주", "일자") or _find(kv, "계약(수주)일자")
                        or _find(kv, "계약(수주)일") or "") or "",
        "advance": _find(kv, "선급금") or "",
        "payterm": payterm,
        "def_payrule": bool(_DEF_PAY.search(payterm or "")),
        # 공시유보 — 방산에서 드물지 않다(경영상 비밀유지). 계약명·금액이 '-' 인 이유가 이것이므로
        # 사유와 기한을 따로 남겨 화면에 '빈칸'이 아니라 '유보'라고 적는다.
        "withheld": _find(kv, "공시유보", "유보사유") or _find(kv, "유보사유") or "",
        "withheld_until": _find(kv, "공시유보", "유보기한") or _find(kv, "유보기한") or "",
        "note": _find(kv, "기타", "중요") or _find(kv, "기타") or "",
    }


def parse_contract(html, rcp, title, stock):
    kv, raw = _kv(html)
    rec = {"rcp": rcp, "stock": stock, "title": title, "corrected": "정정" in (title or "")}
    rec.update(_fields_from_kv(kv))
    rec["kv"] = raw
    return rec


def collect(stocks, start, end, force=False, log=sys.stderr):
    for st in stocks:
        try:
            lst = search_reports(st, start, end, "I001")
        except Exception as e:
            log.write("[warn] %s 검색 실패 %s\n" % (st, e))
            continue
        cons = [(r, t) for r, t in lst if "단일판매" in t or "공급계약" in t]
        got = 0
        for rcp, title in cons:
            path = os.path.join(CACHE, st, rcp + ".json")
            if os.path.exists(path) and not force:
                got += 1
                continue
            try:
                nodes = toc(rcp)
                if not nodes:
                    continue
                rec = parse_contract(fetch_section(nodes[0]), rcp, title, st)
            except Exception as e:                          # 일시 실패는 캐시하지 않는다
                log.write("[warn] %s %s %s\n" % (st, rcp, e))
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            atomic_write(path, json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
            got += 1
        log.write("%s 계약 공시 %d건 중 캐시 %d건\n" % (st, len(cons), got))
        log.flush()


def build(stocks=None):
    """캐시 → contracts.json. 정정공시는 같은 (회사, 계약명, 수주일)의 원본을 덮는다(supersedes)."""
    out = []
    stocks = stocks or (sorted(os.listdir(CACHE)) if os.path.isdir(CACHE) else [])
    for st in stocks:
        d = os.path.join(CACHE, st)
        if not os.path.isdir(d):
            continue
        recs = []
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                recs.append(json.load(fh))
        by = {}
        for r in sorted(recs, key=lambda r: r["rcp"]):      # rcp 오름차순 → 뒤(정정)가 덮는다
            if r.get("kv"):
                r.update(_fields_from_kv(_kv_from_raw(r["kv"])))
            key = (r["stock"], re.sub(r"\s+", "", r["name"] or ""), r["signed"] or r["start"])
            if key in by:
                r["supersedes"] = by[key]["rcp"]
            by[key] = r
        out.extend(by.values())
    out.sort(key=lambda r: (r["stock"], r["signed"] or r["start"], r["rcp"]))
    for r in out:
        r.pop("kv", None)
    write_asset("contracts.json", {"n": len(out), "rows": out})
    return out


def load():
    try:
        return load_asset("contracts.json")["rows"]
    except FileNotFoundError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--from", dest="start", default="20200101")
    ap.add_argument("--to", dest="end", default=time.strftime("%Y%m%d"))
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    stocks = [r["stock"] for r in load_universe()]
    if a.only:
        stocks = a.only.split(",")
    if a.collect:
        collect(stocks, a.start, a.end, a.force)
    if a.build:
        if not has_asset("domains.json"):
            raise SystemExit("assets/domains.json 이 없다 — 먼저 `python3 build_dicts.py --write`")
        rows = build()
        from collections import Counter
        print("계약 %d건 · 계통 %s" % (len(rows), dict(Counter(r["domain"] for r in rows))))
        print("  유형 %s" % dict(Counter(r["ctype"] for r in rows)))
        print("  상대 %s" % dict(Counter(r["party_kind"] for r in rows)))
        defc = [r for r in rows if not r["civil"]]
        print("  방산 %d건 · 계통 미상 %d(부품 %d) · 수출 %d(직 %d·간접 %d) %.1f조"
              % (len(defc), sum(1 for r in defc if not r["domain"]),
                 sum(1 for r in defc if not r["domain"] and r.get("domain_hint") == "PART"),
                 sum(1 for r in defc if r["export"]),
                 sum(1 for r in defc if r["export_kind"] == "direct"),
                 sum(1 for r in defc if r["export_kind"] == "indirect"),
                 sum(r["amt_krw_m"] or 0 for r in defc if r["export"]) / 1e6))
        for r in rows[-6:]:
            print("  ", r["stock"], r["signed"], r["domain"], r["ctype"], r["party_kind"],
                  (r["name"] or "")[:34], r["amt_krw_m"], r["years"])


if __name__ == "__main__":
    sys.exit(main())
