#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero_universe — 우주·항공부품 모집단을 KIND 상장법인목록에서 확정한다.

스펙 `_specs/kaero.md` §모집단 의 네 겹이다. 이름으로 넣지 않는다 — 근거를 `reason` 에 남긴다.

  ① 업종  `항공기,우주선 및 부품 제조업` 전 종목(현재 11). 이 업종만이 이 산업을 바로 말한다.
  ② 제품  다른 업종이되 KIND 주요제품 문구가 항공·우주를 말하는 종목.
          **짧은 낱말이 사고를 만든다**(실측):
            · `위성` 하나면 위성방송(케이티스카이라이프)·위성DMB 중계기(CS·쏠리드)가 들어온다
            · `기체` 하나면 **기체분리막**(에어레인 — 기체=gas)이 들어온다
            · `엔진부품` 하나면 자동차·선박·디젤 엔진부품 7사가 들어온다
            · `MRO` 하나면 소모성 자재 구매대행(MDS스피어)·선박 MRO(에스엔시스)가 들어온다
              — 스펙의 어휘 목록에 있지만 **단독으로는 쓰지 않았다**. 항공 MRO 회사
              (케일럼 `항공기MRO`)는 `항공기` 로 이미 걸린다.
          → 강한 어휘만 쓰고 부정 어휘로 막는다. 애매한 것은 ②로 넣지 말고 ④가 원문으로 판정한다.
  ③ 지정  스펙이 이름으로 지정한 8사. 전부 ①에 이미 있지만 **사유를 적어** 남긴다.
  ④ 탐색  `kaero_scan.py` 가 정기보고서 II절 본문에서 Boeing·Airbus·Embraer·기체구조물·KAI
          언급을 확인해 승격한 종목(assets/universe_probe.json).

제외(스펙 ④): 항공 **운송**(여객·화물)·여행업은 ②에서 자동으로 뺀다. 다만 대한항공처럼
운송 업종이면서 **항공우주사업부문**이 따로 있는 회사는 ④ 탐색이 원문으로 확인해 올린다 —
이름으로 넣지도, 업종으로 버리지도 않는다.

kdef·kship 과 겹치는 회사는 제외하지 않는다. 부문 단위로 나눠 싣고 화면에 중복임을 적는다.

    python3 kaero_universe.py            # 조회만
    python3 kaero_universe.py --write    # assets/universe.json 갱신
"""
import argparse
import re
import sys
from collections import Counter

from kaero_lib import KIND_URL, _get, load_asset, parse_kind, write_asset

# ① 업종 — KIND 실제 표기 그대로(쉼표 뒤 공백 없음).
AERO_INDUSTRIES = ("항공기,우주선 및 부품 제조업",)

# ② 강한 제품 어휘. `항공기MRO`·`항공부품제조`처럼 붙여 쓰는 회사가 있어 공백은 선택이다.
_AERO = re.compile(
    r"항공기|항공\s*부품|항공\s*정밀|항공우주|우주\s*항공|우주\s*방산|"
    r"항공.{0,4}구조물|기체\s*구조|기체\s*부품|기체\s*조립|동체|"
    r"발사체|로켓|누리호|추진기관|"
    r"인공위성|위성\s*체|위성\s*시스템|위성\s*탑재체|위성\s*부분품|위성\s*지상국|위성\s*운용국|"
    r"위성\s*영상|지상국|항공\s*전자|항공\s*엔진", re.I)

# ② 부정 어휘 — 실측 오탐. `위성방송`·`위성DMB`는 방송이고, `기체분리막`의 기체는 gas 다.
_NOT_AERO = re.compile(r"위성\s*방송|위성DMB|위성\s*서비스|위성방송수신|기체\s*분리막|"
                       r"여행|항공권|택배", re.I)

# ② 경로에서 뺄 업종 — 항공의 **고객·운송**이지 제조 공급망이 아니다(스펙 ④).
#    ④ 탐색은 이 업종도 본다(대한항공 항공우주사업본부).
_TRANSPORT = ("항공 여객 운송업", "항공 화물 운송업", "기타 운송관련 서비스업",
              "여행사 및 기타 여행보조 서비스업")

# ③ 지정 — 스펙이 이름으로 든 8사. 종목코드는 KIND 목록 조회로 확인했다(기억으로 적지 않았다).
SEED = {
    "047810": ("prime", "한국항공우주 — 완제기·기체부품. 잔고배수 7.5년으로 이 산업 최장(FINDINGS)"),
    "012450": ("prime", "한화에어로스페이스 — 항공엔진·RSP. 「4. 수주상황(상세)」에 RSP 계약 원장(FINDINGS §3)"),
    "067390": ("struct", "아스트 — 동체(Section48)·벌크헤드. 국외수주 USD 표·국내수주 원 표 분리(FINDINGS §1)"),
    "221840": ("struct", "하이즈항공 — B787 날개구조물. 매출처 각주에 `BOE(Boeing Commercial Airplanes)`"),
    "274090": ("struct", "켄코아에어로스페이스 — 항공가공품·조립품. 표 안에 통화가 섞인다(FINDINGS §6)"),
    "462350": ("space", "이노스페이스 — 소형발사체·로켓추진기관"),
    "474170": ("space", "루미르 — 인공위성 시스템·전장품"),
    "288180": ("struct", "케이피항공산업 — 항공·우주 방산 구조물. 수주표가 없고 매출처 표만 있다(FINDINGS §2)"),
}

MIN_ROWS = 2000
MIN_UNIVERSE = 8

_ROLE_LABEL = {"prime": "체계업체", "struct": "기체구조물", "engine": "엔진·부품",
               "space": "우주", "part": "부품", "service": "정비·용역", "material": "소재"}


def role_of(rec, seed_role=None, probe_role=None):
    """역할 힌트. **판정의 근거가 아니라 정렬용**이다 — 진짜 축은 원문에서 읽는 영역(domain)이고
    `kaero_reports` 가 수주·매출표에서 확인해 채운다."""
    if seed_role:
        return seed_role
    if probe_role:
        return probe_role
    p = rec.get("product") or ""
    if re.search(r"발사체|로켓|인공위성|위성\s*체|위성\s*탑재체|위성\s*영상|지상국|누리호", p, re.I):
        return "space"
    if re.search(r"기체\s*구조|기체\s*부품|동체|날개|구조물|조립품", p, re.I):
        return "struct"
    if re.search(r"항공\s*엔진|엔진부품|추진기관|가스터빈", p, re.I):
        return "engine"
    if re.search(r"MRO|정비|창정비|용역|서비스", p, re.I) and not re.search(r"제조|부품|조립", p):
        return "service"
    if re.search(r"티타늄|합금|소재|원소재|복합재", p, re.I) and not re.search(r"부품|조립", p):
        return "material"
    return "part"


def _probe_promoted():
    """kaero_scan.py 가 정기보고서 본문으로 찾아 승격한 종목(없으면 빈 사전)."""
    try:
        return load_asset("universe_probe.json").get("promoted") or {}
    except Exception:
        return {}


def select(recs):
    picked, seen = [], set()
    probe = _probe_promoted()
    for r in recs:
        src = None
        seed = SEED.get(r["stock"])
        pr = probe.get(r["stock"])
        prod = r.get("product") or ""
        if r["industry"] in AERO_INDUSTRIES:
            src = "업종"
        elif seed:
            src = "지정"
        elif pr:
            src = "탐색"
        elif (_AERO.search(prod) and not _NOT_AERO.search(prod)
              and r["industry"] not in _TRANSPORT):
            src = "제품"
        if not src:
            continue
        d = dict(r)
        d["slug"] = r["stock"]
        d["source"] = src
        d["role"] = role_of(r, seed[0] if seed else None,
                            (pr or {}).get("role") if src == "탐색" else None)
        if seed:
            d["reason"] = seed[1]
        elif src == "탐색":
            d["reason"] = (pr or {}).get("reason", "")
        elif src == "제품":
            m = _AERO.search(prod)
            d["reason"] = "KIND 주요제품 문구에 `%s` — %s" % (m.group(0), prod[:60])
        else:
            d["reason"] = "KIND 업종 `%s`" % r["industry"]
        # 아래 셋은 **원문이 채운다**. 여기서 추정하지 않는다.
        d["domains"] = []          # kaero_reports — 수주·매출표 품목 문구에서
        d["dup_tabs"] = []         # kaero_reports — 부문 필터에서 빠진 부문(kdef·kship)
        d["oem"] = []              # kaero_reports — 매출처·수주표에서 읽은 OEM
        picked.append(d)
        seen.add(r["stock"])
    missing = sorted(set(SEED) - seen)
    if missing:
        sys.stderr.write("[warn] 지정 종목이 상장법인목록에 없음(상장폐지·상호변경?): %s\n" % missing)
    if len(picked) < MIN_UNIVERSE:
        raise RuntimeError("모집단이 %d개뿐 — KIND 응답이 깨졌거나 업종명 체계가 바뀌었다" % len(picked))
    order = {"prime": 0, "struct": 1, "engine": 2, "space": 3, "part": 4,
             "service": 5, "material": 6}
    picked.sort(key=lambda r: (order[r["role"]], r["stock"]))
    return picked


def fetch(write=False):
    recs = parse_kind(_get(KIND_URL))
    if len(recs) < MIN_ROWS:
        raise RuntimeError("KIND 목록이 %d행뿐" % len(recs))
    picked = select(recs)
    if write:
        write_asset("universe.json", {"source": KIND_URL, "n": len(picked), "rows": picked})
    return picked


def load():
    try:
        return load_asset("universe.json")["rows"]
    except FileNotFoundError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    recs = fetch(write=a.write)
    for r in recs:
        print("%-6s %-7s %-3s %-18s %-4s %s"
              % (_ROLE_LABEL[r["role"]], r["stock"], r["source"][:2], r["name"][:18],
                 r["market"][:4], (r["reason"] or r["product"])[:64]))
    print("— %d종목 %s" % (len(recs), dict(Counter(r["role"] for r in recs))), file=sys.stderr)
    print("  출처 %s" % dict(Counter(r["source"] for r in recs)), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
