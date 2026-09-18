#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""knuke_universe — 원전·발전기자재 모집단을 KIND 상장법인목록에서 확정한다(스펙 §모집단).

네 겹이다:
  ① KIND  업종이 기계·금속·측정·전기장비·엔지니어링 계열이면서 **주요제품**에 원전·발전 어휘
          (원자력·원전·원자로·핵연료·방사선·발전설비·발전용·보일러·터빈·주단조·압력용기·열교환기)
  ② 지정  사유를 적은 지정 — 두산에너빌리티·한전기술·한전KPS·비에이치아이·우진·오르비텍.
          **종목코드는 scout 표본(sample.json)에서 확인**했다(이름으로 단정하지 않는다).
  ③ 탐색  `knuke_scan.py` 가 정기보고서 II절 본문에서 '한국수력원자력'·'원전'·'발전소'를 세어 승격
          (assets/universe_probe.json).
  ④ 제외  리츠·부동산·금융·소프트웨어·의약·화장품·식품 · 발전 **사업자**(한전·발전 5사·SK E&S 등 —
          발주처이지 기자재사가 아니다).

역할(role)은 **힌트**다 — main 주기기 · eng 설계·엔지니어링 · om 정비/O&M ·
part 기자재·부품 · material 소재·주단조 · holding 지주. 화면 카드는 이름이 아니라 원문 지표
(수주잔고·계약 건수)로 고른다.

    python3 knuke_universe.py            # 조회만
    python3 knuke_universe.py --write    # assets/universe.json 갱신
"""
import argparse
import re
import sys
from collections import Counter

from knuke_lib import KIND_URL, _get, load_asset, parse_kind, write_asset

# ① 업종 — 스펙 §모집단 ①. KIND 표기는 쉼표 뒤 공백이 없다(측정, 시험…).
IND = re.compile(r"기계 제조업|구조용 금속제품|1차 철강|금속 가공|측정, 시험|전기장비|"
                 r"기타 과학기술|엔지니어링")
# ① 주요제품 원전·발전 어휘. `발전기` 단독은 `발전기자재`·자동차 발전기와 겹치므로 붙은 꼴만.
PROD = re.compile(r"원자력|원전|원자로|핵연료|방사선|발전설비|발전용|발전기자재|보일러|터빈|터어빈|"
                  r"주단조|압력용기|열교환기|증기발생기|복수기")

# ④ 제외 — 업종·제품 어디에 걸려도 뺀다. 발전 **사업자**는 발주처이지 기자재사가 아니다.
_NOT_SUPPLY = re.compile(r"리츠|부동산|금융|보험|은행|증권|소프트웨어 개발|의약|화장품|식품|"
                         r"전기업|가스업|증기.*공급|발전업|전기, 가스")
# ④ 발전 사업자·발주처 이름(상장) — 명시 제외.
EXCLUDE_STOCK = {
    "015760": "한국전력 — 발주처(전력망 사업자)",
    "052690_x": "",  # placeholder
}
EXCLUDE_STOCK.pop("052690_x", None)

# ② 지정 — scout 표본에서 종목코드를 확인했다(sample.json npp 8사 중 6사 + 발전기자재 대표).
SEED = {
    "034020": ("main", "두산에너빌리티 — 원자로·터빈 주기기(잔고 25.5조·배수 1.5년). 체코 두코바니 수주"),
    "052690": ("eng", "한전기술 — 원전 종합설계·엔지니어링. II-4 수주표에 발주처(한수원) 실명 23행"),
    "051600": ("om", "한전KPS — 발전설비 경상·예방정비(O&M). 요르단 IPP3 O&M 등 해외 정비"),
    "083650": ("part", "비에이치아이 — 보일러·열교환기 등 발전 보조기기. 계약공시 잦음(2년 24건)"),
    "105840": ("part", "우진 — 원전용 계측기(노내핵계측·온도센서)"),
    "046120": ("om", "오르비텍 — 방사선안전관리·비파괴검사, 항공기 정밀부품 겸업"),
    "015590": ("part", "DKME(대경기계기술) — 열교환기·압력용기·산업용보일러"),
    "008470": ("part", "부스타 — 관류·진공온수·무압온수 보일러"),
}

MIN_ROWS = 2000
MIN_UNIVERSE = 8


def role_of(rec, seed_role=None, probe_role=None):
    if seed_role:
        return seed_role
    if probe_role:
        return probe_role
    p = rec.get("product") or ""
    ind = rec.get("industry") or ""
    if re.search(r"엔지니어링|기술 서비스|과학기술", ind) or re.search(r"설계|엔지니어링|감리", p):
        return "eng"
    if re.search(r"정비|O\s*&\s*M|유지보수|방사선안전|검사", p):
        return "om"
    if re.search(r"1차 철강|금속 가공|구조용 금속", ind) and re.search(r"주단조|단조|주조|특수강|봉강", p):
        return "material"
    if re.search(r"지주|투자회사", ind + p):
        return "holding"
    return "part"


def _probe_promoted():
    try:
        return load_asset("universe_probe.json").get("promoted") or {}
    except Exception:
        return {}


def select(recs):
    picked, seen = [], set()
    probe = _probe_promoted()
    for r in recs:
        if r["stock"] in EXCLUDE_STOCK:
            continue
        src = None
        seed = SEED.get(r["stock"])
        pr = probe.get(r["stock"])
        ind, prod = r.get("industry") or "", r.get("product") or ""
        if seed:
            src = "지정"
        elif IND.search(ind) and PROD.search(prod) and not _NOT_SUPPLY.search(ind):
            src = "KIND"
        elif pr:
            src = "탐색"
        if not src:
            continue
        if _NOT_SUPPLY.search(ind) and not seed:
            continue
        d = dict(r)
        d["slug"] = r["stock"]
        d["source"] = src
        d["role"] = role_of(r, seed[0] if seed else None,
                            (pr or {}).get("role") if src == "탐색" else None)
        if seed:
            d["reason"] = seed[1]
        elif src == "KIND":
            m = PROD.search(prod)
            d["reason"] = "KIND 주요제품 문구에 `%s` — %s" % (m.group(0), prod[:60])
        elif src == "탐색":
            d["reason"] = (pr or {}).get("reason", "")
        else:
            d["reason"] = ""
        d["client_conc"] = None      # 발주처 집중도(한수원 비중) — 정기보고서 수주표로 확인
        d["export_share"] = None     # 수출 비중 — 부문 매출로 확인
        picked.append(d)
        seen.add(r["stock"])
    missing = sorted(set(SEED) - seen)
    if missing:
        sys.stderr.write("[warn] 지정 종목이 상장법인목록에 없음(상장폐지·상호변경?): %s\n" % missing)
    if len(picked) < MIN_UNIVERSE:
        raise RuntimeError("모집단이 %d개뿐 — KIND 응답이 깨졌거나 업종명 체계가 바뀌었다" % len(picked))
    order = {"main": 0, "eng": 1, "om": 2, "part": 3, "material": 4, "holding": 5}
    picked.sort(key=lambda r: (order.get(r["role"], 9), r["stock"]))
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
        print("%-8s %-7s %-3s %-18s %-4s %-24s %s"
              % (r["role"], r["stock"], r["source"][:2], r["name"][:18], (r["market"] or "")[:4],
                 (r["industry"] or "")[:24], (r["reason"] or r["product"] or "")[:56]))
    print("— %d종목 %s" % (len(recs), dict(Counter(r["role"] for r in recs))), file=sys.stderr)
    print("  출처 %s" % dict(Counter(r["source"] for r in recs)), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
