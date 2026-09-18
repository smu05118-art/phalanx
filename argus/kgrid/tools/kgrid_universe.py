#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_universe — 전력기기·전력망 모집단을 KIND 상장법인목록에서 확정한다.

스펙 §모집단의 네 겹을 그대로 만든다. 다만 ①업종만으로는 모집단이 서지 않는다 —
업종 4갈래 72종목의 절반 이상이 2차전지 장비·전기차 충전기·휴대폰 부품·교육용로봇이다
(FINDINGS §0 실측). 그래서 업종 안에서도 **주요제품 문구를 본다**.

  ① 업종 + 제품 — `전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업`·`기타 전기장비 제조업`·
                `절연선 및 케이블 제조업`·`전기 및 통신 공사업` 중 제품 문구가 전력망을 말하는 것
  ② 제품      — 업종 **밖**에서 제품 문구로 잡히는 것. 실체는 금구류·절연유·부스웨이·계량기다
                (제룡산업·보성파워텍·세명전기·미창석유공업·티에스넥스젠·옴니시스템, FINDINGS §1)
  ③ 지정      — 사유를 적은 지정. 스펙이 이름을 준 8사와, 업종이 엉뚱한 실제 제조사
  ④ 탐색      — `kgrid_scan.py` 가 정기보고서 II절 본문에서 찾아 승격한 종목

제외(스펙 ④):
  · `전기업` — 한국전력공사·SGC에너지·에이전트AI는 **발주처·발전사업자**다. 공급망이 아니다.
  · 이차전지 제조·건전지 — `ESS` 낱말이 겹친다(LG에너지솔루션·유니테크노·에이프로).
  · 지주회사 — 제품 문구에 자회사 제품이 다 적혀 이중계산된다(LS·효성·일진홀딩스).
    단 비츠로테크(042370)는 업종이 `기타 금융업`이면서 본인이 차단기를 만든다 — 지정으로 넣는다.

역할(role)은 **힌트**다. 진짜 근거는 수주표·계약 공시이며 `kgrid_reports`·`kgrid_contracts` 가
되돌려 준다 — 이름으로 단정하지 않는다.
  maker 전력기기 제조 · part 부품·소재·금구류 · cable 전선 · epc 전기공사·정비 · holding 지주

    python3 kgrid_universe.py            # 조회만
    python3 kgrid_universe.py --write    # assets/universe.json 갱신
"""
import argparse
import re
import sys
from collections import Counter

from kgrid_lib import KIND_URL, _get, load_asset, parse_kind, write_asset

# ① 업종 — FINDINGS §0 에서 KIND 실제 표기를 그대로 확인했다(가운뎃점 앞뒤 공백까지).
CORE_INDUSTRIES = (
    "전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업",
    "기타 전기장비 제조업",
    "절연선 및 케이블 제조업",
    "전기 및 통신 공사업",
)
# 발주처·발전사업자 — 스펙 ④ 제외. 업종째로 뺀다.
UTILITY_INDUSTRIES = ("전기업",)

# 전력망 어휘. 실측 오탐에서 배운 제약(FINDINGS §1):
#   · `GIS` 단독 금지 — AEGIS(넥스틴)·EGIS(제이에스링크)·Internet GIS(지어소프트)
#   · `ESS` 단독 금지 — ACESS FLOOR(세보엠이씨)·CESS(에이아이코리아), 그리고 이차전지 제조
#   · `초고압` 단독 금지 — 초고압용공구(일진디스플, 분말야금)
#   · `배전`·`송전`은 안전하다(실측 오탐 없음)
_GRID = re.compile(
    r"변압기|차단기|배전반|수배전|분전반|개폐기|개폐장치|전력기기|송전|배전|송배전|변전|"
    r"전력변환|계전기|전력설비|전력용|가스절연|스위치기어|부스덕트|부스웨이|busway|"
    r"전력량계|원격검침|피뢰기|부싱|절연유|권선|탭체인저|애자|금구류|"
    r"전력케이블|전력선|초고압케이블|초고압선|해저케이블|초전도선|"
    r"수배전설비|전력감시|배전자동화|원방감시|PCS\b|계통연계", re.I)
# `SCADA` 단독은 넣지 않았다 — 엠엑스온 347890 `스마트SCADA`는 스마트팩토리 솔루션이다.
# 전력계통 쪽은 `원방감시`·`배전자동화`·`전력감시` 라는 한국어 표기로 잡힌다(비츠로시스 054220).

# 어휘가 걸렸더라도 **이것이 본업이면** 전력망이 아니다(실측 오탐 방어).
_NOT_GRID = re.compile(
    r"2차전지|이차전지|리튬|배터리\s*셀|건전지|전기차\s*충전|충전기\(|휴대폰|"
    r"EV\s*Relay|차량용|자동차\s*부품|"
    r"반도체\s*(검사|전공정)|디스플레이|교육용|광섬유|광케이블(?!.*전력)", re.I)

# ② 경로에서 뺄 업종 — 전력기기의 **고객·유통·금융**이지 공급망이 아니다.
_NOT_SUPPLY = ("전기업", "상품 종합 도매업", "기타 전문 도매업",
               "기계장비 및 관련 물품 도매업", "기타 금융업",
               "일차전지 및 이차전지 제조업", "공공 행정, 국방 및 사회보장 행정")

# ③ 지정 — 사유를 적는다. 종목코드는 **KIND 조회로 확인**했다(기억으로 적지 않았다).
SEED = {
    # 스펙 §모집단 ②가 이름을 준 8사
    "267260": ("maker", "HD현대일렉트릭 — 변압기·고압차단기·회전기·배전반. 수주표 부문 합계 1행(FINDINGS §2)"),
    "010120": ("maker", "엘에스일렉트릭 — 고압/저압기기·변압기·배전반·인버터. 수주표 롤포워드 12열"),
    "298040": ("maker", "효성중공업 — KIND 주요제품이 `-`로 비어 있다(실측). 중공업(변압기·차단기)+건설 부문"),
    "103590": ("cable", "일진전기 — 전력선·변압기(중전기). 수주표 단위가 `천USD`(FINDINGS §2)"),
    "062040": ("maker", "산일전기 — 유입·몰드·주상·건식 변압기. 북미 수출 중심"),
    "033100": ("maker", "제룡전기 — 송배전용금구류·변압기"),
    "017040": ("maker", "광명전기 — 수배전반·가스절연개폐장치(GIS)·중앙감시반"),
    "189860": ("maker", "서전기전 — 수배전반·전력기기·전기공사"),
    # 업종이 엉뚱한 실제 제조사 — FINDINGS §1 에서 KIND 제품 문구로 확인했다.
    "042370": ("maker", "비츠로테크 — 업종이 `기타 금융업`이나 본인이 차단기·개폐기를 만든다"),
    "147830": ("part", "제룡산업 — 업종 `구조용 금속제품`. 송배전 금구류(≠제룡전기 033100)"),
    "006910": ("part", "보성파워텍 — 업종 `구조용 금속제품`. 송배전용 자재"),
    "017510": ("part", "세명전기 — 업종 `기타 금속 가공제품`. 154·345·765kV 송변전용 금구류"),
    "003650": ("part", "미창석유공업 — 업종 `석유 정제품`. 전기절연유(변압기 절연·냉각)"),
    "057540": ("part", "옴니시스템 — 업종 `측정,시험,항해,제어…`. 전자식전력량계·원격검침"),
    "043220": ("part", "티에스넥스젠 — 업종 `특수 목적용 기계`. 전력설비 Busway·발전설비 Damper"),
}

# 지주회사는 넣되 잔고 집계에서 뺀다(화면에 이유를 적는다).
HOLDING = {
    "006260": "LS — 지주. 전력용전선·통신케이블은 자회사(LS전선·엘에스일렉트릭) 제품이다",
    "004800": "효성 — 지주. 중전기(변압기·차단기)는 효성중공업 298040 것이다",
    "015860": "일진홀딩스 — 지주. 개폐기·차단기·배전반은 일진전기 103590 것이다",
}

MIN_ROWS = 2000
MIN_UNIVERSE = 20


def role_of(rec, seed_role=None, probe_role=None):
    """역할 힌트. 수주표·계약 공시가 확인하면 뒤 단계가 고쳐 준다."""
    if seed_role:
        return seed_role
    if probe_role:
        return probe_role
    p = rec.get("product") or ""
    ind = rec.get("industry") or ""
    if rec["stock"] in HOLDING or re.search(r"기타 금융업", ind):
        return "holding"
    if ind == "절연선 및 케이블 제조업" or re.search(r"전력선|전력케이블|해저케이블|초전도선", p):
        return "cable"
    # 공사·정비는 **제조를 말하지 않을 때만**이다. 선도전기 `수배전반,중전기기 제조,도매/전기공사`는
    # 제조사다 — 뒤에 붙은 `전기공사` 하나로 시공사로 옮기면 잔고의 뜻이 달라진다.
    if (ind == "전기 및 통신 공사업" or re.search(r"전기공사|정비\s*용역|발전설비\s*정비|유지보수", p)) \
            and not re.search(r"제조|생산", p):
        return "epc"
    # 금구류·절연유·계량기·부스웨이는 기기가 아니라 그 주변이다.
    if re.search(r"금구류|자재|절연유|부싱|권선|애자|탭체인저|busway|부스웨이|부스덕트|"
                 r"전력량계|원격검침|단말장치|보호계전", p, re.I):
        return "part"
    if _GRID.search(p):
        return "maker"
    return "part"


def _probe():
    try:
        return load_asset("universe_probe.json") or {}
    except Exception:
        return {}


def _probe_promoted():
    """kgrid_scan.py 가 정기보고서 본문으로 찾아 승격한 종목(없으면 빈 사전)."""
    return _probe().get("promoted") or {}


def _probe_rejected():
    """본문 근거로 **아니라고 판정된** 종목 → {종목코드: 이유}.

    어휘로는 걸리지만 II절 본문이 다른 산업을 말하는 회사가 있다(실측):
      · 파워넷 037030 `전력변환장치` — 본문은 SMPS·가전기기·배터리 팩이다
      · 대양전기공업 108380 `배전반류` — 본문은 선박용·잠수함·조선소다(방산 탭의 몫)
      · 제일일렉트릭 199820 `분전반` — 본문은 배선기구·건설사다(저압 배선기구)
      · 티엠씨 217590 `전력용케이블` — 본문은 해양플랜트·조선소·선박용이다
    **어휘로 들어온 종목만** 뺀다 — 지정(사유를 적은 것)·지주는 손대지 않는다.
    뺀 것은 `demoted` 로 남겨 커버리지 화면이 이유와 함께 보인다(지우지 않는다)."""
    out = {}
    for r in (_probe().get("rejected") or []):
        if isinstance(r, dict) and r.get("stock"):
            out[r["stock"]] = r.get("reason") or ""
    return out


def _grid_hit(product):
    """제품 문구가 전력망을 말하는가. 오탐 방어(_NOT_GRID)를 먼저 본다."""
    p = product or ""
    m = _GRID.search(p)
    if not m:
        return None
    # 어휘가 걸린 조각 주변이 오탐 문맥이면 버린다. 단 문구 전체가 아니라 **걸린 절**만 본다 —
    # '변압기, 전기차 충전기'처럼 둘 다 만드는 회사를 통째로 버리면 안 된다.
    for seg in re.split(r"[,·/]", p):
        if _GRID.search(seg) and not _NOT_GRID.search(seg):
            return _GRID.search(seg).group(0)
    return None


def select(recs):
    picked, seen, demoted = [], set(), []
    probe = _probe_promoted()
    rejected = _probe_rejected()
    for r in recs:
        stock, ind, prod = r["stock"], r["industry"], r.get("product") or ""
        seed = SEED.get(stock)
        pr = probe.get(stock)
        hit = _grid_hit(prod)
        src = None
        if seed:
            src = "지정"
        elif stock in HOLDING:
            src = "지주"
        elif ind in UTILITY_INDUSTRIES:
            continue                                  # 발주처 — 업종째로 제외
        elif ind in CORE_INDUSTRIES and hit:
            src = "업종"
        elif hit and ind not in _NOT_SUPPLY:
            src = "제품"
        elif pr:
            src = "탐색"
        if not src:
            continue
        if src in ("업종", "제품") and stock in rejected:
            demoted.append({"stock": stock, "name": r["name"], "industry": ind,
                            "product": prod[:90], "source": src,
                            "reason": rejected[stock]})
            continue
        d = dict(r)
        d["slug"] = stock
        d["source"] = src
        d["role"] = ("holding" if src == "지주" else
                     role_of(r, seed[0] if seed else None,
                             (pr or {}).get("role") if src == "탐색" else None))
        if seed:
            d["reason"] = seed[1]
        elif src == "지주":
            d["reason"] = HOLDING[stock]
        elif src == "탐색":
            d["reason"] = (pr or {}).get("reason", "")
        else:
            d["reason"] = "KIND 주요제품 문구에 `%s` — %s" % (hit, prod[:60])
        d["product_keys"] = []       # build_dicts 가 제품군으로 분류해 채운다
        d["bal_cur"] = None          # 수주표 통화 — kgrid_reports 가 채운다
        d["export_share"] = None     # 부문 매출(수출/내수)로 확인
        picked.append(d)
        seen.add(stock)
    missing = sorted(set(SEED) - seen)
    if missing:
        sys.stderr.write("[warn] 지정 종목이 상장법인목록에 없음(상장폐지·상호변경?): %s\n" % missing)
    if len(picked) < MIN_UNIVERSE:
        raise RuntimeError("모집단이 %d개뿐 — KIND 응답이 깨졌거나 업종명 체계가 바뀌었다" % len(picked))
    order = {"maker": 0, "cable": 1, "part": 2, "epc": 3, "holding": 4}
    picked.sort(key=lambda x: (order[x["role"]], x["stock"]))
    demoted.sort(key=lambda x: x["stock"])
    return picked, demoted


def fetch(write=False):
    recs = parse_kind(_get(KIND_URL))
    if len(recs) < MIN_ROWS:
        raise RuntimeError("KIND 목록이 %d행뿐" % len(recs))
    picked, demoted = select(recs)
    if write:
        write_asset("universe.json", {"source": KIND_URL, "n": len(picked), "rows": picked,
                                     "n_demoted": len(demoted), "demoted": demoted})
    return picked, demoted


def load():
    try:
        return load_asset("universe.json")["rows"]
    except FileNotFoundError:
        return []


def load_demoted():
    """어휘로는 걸렸지만 **본문 근거로 뺀** 종목. 커버리지 화면이 이유와 함께 보인다."""
    try:
        return load_asset("universe.json").get("demoted") or []
    except FileNotFoundError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    recs, demoted = fetch(write=a.write)
    for r in recs:
        print("%-7s %-7s %-4s %-16s %-4s %s"
              % (r["role"], r["stock"], r["source"][:2], r["name"][:16], r["market"][:4],
                 (r["reason"] or r["product"])[:76]))
    print("— %d종목 %s" % (len(recs), dict(Counter(r["role"] for r in recs))), file=sys.stderr)
    print("  출처 %s" % dict(Counter(r["source"] for r in recs)), file=sys.stderr)
    for d in demoted:
        print("[본문 근거로 뺐다] %s %s — %s" % (d["stock"], d["name"], d["reason"][:90]),
              file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
