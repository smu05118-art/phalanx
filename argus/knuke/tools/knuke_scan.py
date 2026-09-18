#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""knuke_scan — 모집단 ③ 겹. KIND 제품 문구가 원전·발전을 말하지 않는 상장사를 **정기보고서
II절 본문**으로 찾아 승격한다(스펙 §모집단 ③, kship_scan 방식).

발전기자재는 매출의 일부가 원전·발전인 회사가 많아(`열교환기`·`밸브`·`특수강`·`계측기`)
KIND 한 줄로는 안 보인다. II절에서 **발주처(한국수력원자력·한국전력)**·원전·발전소 언급을
세어 공급망으로 본다.

  1) 후보 풀 — KIND 제품 문구가 발전 부품 어휘에 걸리고, 무관한 업종(금융·의약·식품·유통…)이
     아닌 회사. 이미 모집단이면 제외. 발전 **사업자**(전기·가스공급업)도 제외.
  2) 증거 — II절(사업의 개요·주요 제품·매출 및 수주상황) 본문에서 `hits` 원전·발전 낱말 횟수 ·
     `koreanuke` 한국수력원자력 언급 · `gov` 한전·발전사 언급.
  3) 승격(fail-closed) — 본문을 못 읽었으면(ok=False) 승격하지 않는다.

    python3 knuke_scan.py --scan [--quarter 2026Q2] [--limit 120]   # → assets/universe_probe.json
그 뒤 `knuke_universe.py --write` 가 승격분을 '탐색' 출처로 모집단에 넣는다.
"""
import argparse
import re
import sys
import time

from knuke_lib import (KIND_URL, _get, fetch_section, find_sections, latest_quarter,
                       parse_kind, pick_report, report_kind, report_window, search_reports, toc,
                       write_asset)
from knuke_universe import IND, PROD, _NOT_SUPPLY, EXCLUDE_STOCK
from knuke_universe import load as load_universe

SECTIONS = [
    ("overview", ["사업의 개요"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품"]),
    ("sales", ["매출 및 수주상황", "수주상황", "매출실적"]),
]

# 후보 풀 — 발전 부품이 될 수 있는 제품 어휘. 넓게 잡되 읽을 수 있는 규모로 줄인다.
POOL = re.compile(
    r"열교환기|압력용기|저장탱크|탱크|보일러|터빈|터어빈|밸브|피팅|배관|펌프|송풍기|블로워|"
    r"주단조|단조|주조|주강|특수강|합금강|봉강|판재|플랜지|"
    r"계측|계장|센서|검출기|제어반|배전반|수배전|변압기|개폐기|차단기|케이블|전선|"
    r"복수기|탈기기|급수가열기|응축기|탈황|탈질|집진|스크러버|"
    r"발전설비|발전용|발전기자재|플랜트|산업설비|압력배관|비파괴|방사선|엔지니어링|정비", re.I)
# 업종 화이트리스트 — 모집단이 실제로 흩어져 있는 업종 + 인접 제조업.
POOL_IND = re.compile(
    r"기계 제조업|구조용 금속제품|탱크|1차 철강|1차 비철금속|금속 가공|측정, 시험|전기장비|"
    r"전동기, 발전기|절연선|기타 과학기술|엔지니어링|기술 서비스|특수 목적용 기계|"
    r"일반 목적용 기계|기타 금속 가공제품|금속 주조업|전기 및 통신 공사업|기타 기계|"
    r"기초 화학물질|정밀기기")
# 발전일 수 없는 업종(고객·금융·소비재·발전사업자).
EXCL = re.compile(r"금융|보험|증권|은행|부동산|임대|음식|식료|음료|주류|담배|의복|가죽|신발|화장품|"
                  r"농업|어업|임업|광업|숙박|교육|오락|게임|스포츠|광고|출판|영화|방송프로그램|"
                  r"여행|운송업|창고|도매업|소매업|의약|의료용|사회복지|협회|하수|폐기물|"
                  r"전기업|가스업|증기.*공급|발전업|전기, 가스")

# 원전·발전 낱말 — 본문에서 세는 것.
NUKE_WORDS = re.compile(
    r"한국수력원자력|한수원|원자력발전|원자력\s*발전소|원자력|원전|원자로|핵연료|방사선|"
    r"신한울|신고리|새울|한빛|한울|월성|고리|APR1400|SMR|사용후핵연료|계속운전|"
    r"화력발전|복합화력|복합발전|석탄화력|열병합|발전설비|발전소|발전용|발전플랜트|"
    r"증기발생기|증기터빈|가스터빈|보일러|HRSG|두코바니|바라카", re.I)
# 발주처 강신호 — 한국수력원자력·한국전력·발전 5사(발주처 실명이 곧 발전기자재사의 증거).
KHNP = re.compile(r"한국수력원자력|한수원")
KEPCO = re.compile(r"한국전력공사|한국전력|한전(?!KPS)|남동발전|중부발전|서부발전|남부발전|동서발전|"
                   r"한국전력기술|발전공기업|발전자회사")

PROMOTE_HITS = 8              # 본문에서 원전·발전을 이만큼 말하면 공급망으로 본다
PROMOTE_HITS_WITH_CLIENT = 4  # 한수원·한전 언급이 있으면서 낱말 이만큼
RULE = ("원전·발전 낱말 ≥ %d, 또는 한국수력원자력·한국전력·발전 5사 언급이 있으면서 낱말 ≥ %d. "
        "II절을 못 읽은 회사는 승격하지 않는다(fail-closed)."
        % (PROMOTE_HITS, PROMOTE_HITS_WITH_CLIENT))


def judge(row):
    if not row.get("ok"):
        return False
    hits = row.get("hits", 0)
    client = row.get("khnp", 0) + row.get("kepco", 0)
    return hits >= PROMOTE_HITS or (client >= 1 and hits >= PROMOTE_HITS_WITH_CLIENT)


def role_for(row):
    ind = row.get("industry") or ""
    p = row.get("product") or ""
    if re.search(r"엔지니어링|기술 서비스|과학기술", ind) or re.search(r"설계|엔지니어링|감리", p):
        return "eng"
    if re.search(r"정비|유지보수|방사선안전|비파괴|검사", p):
        return "om"
    if re.search(r"1차 철강|1차 비철금속|금속 주조|기초 화학", ind) or re.search(r"주단조|단조|특수강|합금", p):
        return "material"
    return "part"


def pool(recs, universe):
    uni = {r["stock"] for r in universe}
    out = []
    for r in recs:
        st = r["stock"]
        if st in uni or st in EXCLUDE_STOCK:
            continue
        ind, prod = r.get("industry") or "", r.get("product") or ""
        if EXCL.search(ind) or _NOT_SUPPLY.search(ind) or not POOL_IND.search(ind):
            continue
        if IND.search(ind) and PROD.search(prod):
            continue          # 이미 ① KIND 경로가 잡는다
        if POOL.search(prod):
            out.append(r)
    return out


def probe_one(rec, quarter):
    st = rec["stock"]
    out = {"stock": st, "name": rec["name"], "market": rec["market"],
           "industry": rec["industry"], "product": rec["product"],
           "ok": False, "hits": 0, "khnp": 0, "kepco": 0, "terms": {}, "note": ""}
    start, end = report_window(quarter)
    try:
        reports = pick_report(search_reports(st, start, end, report_kind(quarter)), quarter)
    except Exception as e:
        out["note"] = "검색 실패: %s" % e
        return out
    if not reports:
        out["note"] = "정기보고서 없음"
        return out
    rcp = reports[0][0]
    out["rcp"] = rcp
    try:
        found = find_sections(toc(rcp), SECTIONS)
        text = ""
        for key in ("overview", "products", "sales"):
            if key in found:
                text += re.sub(r"<[^>]+>", " ", fetch_section(found[key]))
    except Exception as e:
        out["note"] = "본문 읽기 실패: %s" % e
        return out
    if not text.strip():
        out["note"] = "II절 없음"
        return out
    text = re.sub(r"[\s　]+", " ", text)
    terms = {}
    for m in NUKE_WORDS.finditer(text):
        t = m.group(0)
        terms[t] = terms.get(t, 0) + 1
    out["terms"] = dict(sorted(terms.items(), key=lambda kv: -kv[1])[:12])
    out["hits"] = sum(terms.values())
    out["khnp"] = len(KHNP.findall(text))
    out["kepco"] = len(KEPCO.findall(text))
    out["ok"] = True
    m = NUKE_WORDS.search(text)
    out["quote"] = text[max(0, m.start() - 60):m.start() + 120].strip() if m else ""
    return out


def scan(quarter, limit=None, log=sys.stderr):
    recs = parse_kind(_get(KIND_URL))
    universe = load_universe()
    cands = pool(recs, universe)
    if limit:
        cands = cands[:limit]
    log.write("후보 %d사 (모집단 %d 제외)\n" % (len(cands), len(universe)))
    promoted, rejected, failed = {}, [], []
    for i, r in enumerate(cands, 1):
        row = probe_one(r, quarter)
        if not row["ok"]:
            failed.append(row)
        elif judge(row):
            client = row["khnp"] + row["kepco"]
            promoted[r["stock"]] = {
                "role": role_for(row), "hits": row["hits"], "khnp": row["khnp"],
                "kepco": row["kepco"], "terms": row["terms"],
                "reason": "정기보고서 II절에서 원전·발전 낱말 %d회%s — \"%s\""
                          % (row["hits"],
                             (", 한수원·한전 등 발주처 %d회" % client) if client else "",
                             (row.get("quote") or "")[:120])}
            log.write("  [승격] %s %s hits=%d 한수원=%d 한전=%d\n"
                      % (r["stock"], r["name"][:14], row["hits"], row["khnp"], row["kepco"]))
        else:
            rejected.append({k: row[k] for k in
                             ("stock", "name", "industry", "product", "hits", "khnp", "kepco", "terms")})
        if i % 20 == 0:
            log.write("  … %d/%d (승격 %d)\n" % (i, len(cands), len(promoted)))
            log.flush()
    out = {"quarter": quarter, "rule": RULE, "n_cand": len(cands),
           "promoted": promoted, "rejected": rejected, "failed": failed,
           "scanned_at": time.strftime("%Y-%m-%d")}
    write_asset("universe_probe.json", out)
    log.write("승격 %d · 제외 %d · 실패 %d\n" % (len(promoted), len(rejected), len(failed)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--quarter", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pool-only", action="store_true")
    a = ap.parse_args()
    if a.pool_only:
        recs = parse_kind(_get(KIND_URL))
        cands = pool(recs, load_universe())
        print("후보 %d사" % len(cands))
        for r in cands[:60]:
            print("  %s %-16s %-22s %s" % (r["stock"], r["name"][:16], (r["industry"] or "")[:22],
                                           (r["product"] or "")[:44]))
        return
    if a.scan:
        scan(a.quarter or latest_quarter(), a.limit)


if __name__ == "__main__":
    sys.exit(main())
