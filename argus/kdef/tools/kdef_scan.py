#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_scan — 모집단 ④ 겹. KIND 제품 문구가 방산을 말하지 않는 상장사를 **정기보고서 II절
본문**으로 찾아 승격한다(스펙 §모집단 ④, kship_scan 방식).

방산은 조선보다 이 겹이 더 중요하다. KIND 주요제품은 한 줄이고 방산은 매출의 일부인 회사가
많아(`단조품`·`자동차부품`·`특수 목적용 기계`) 제품 문구만으로는 안 보인다. 실제로 스펙이
지정으로 부른 한일단조·SNT다이내믹스·스페코가 전부 그런 회사였다.

  1) 후보 풀 — KIND 제품 문구가 **부품 어휘**(단조·주조·밸브·유압·안테나·광학·센서·전원…)에
     걸리고, 방산과 무관한 업종(금융·의약·식품·유통·오락…)이 아닌 회사. 이미 모집단이면 제외.
     고객 업종(정부·공공기관)은 애초에 상장사가 아니다.
  2) 증거 — II절(사업의 개요·주요 제품·매출 및 수주상황) 본문에서
     `hits` 방산 낱말 횟수 · `mentions` 체계업체 언급(회사별) · `gov` 방위사업청·국방과학연구소 언급.
  3) 승격(fail-closed) — 본문을 못 읽었으면(ok=False) **절대 승격하지 않는다**.
     규칙은 RULE 에 적고 커버리지 페이지에 그대로 싣는다. 제외도 근거와 함께 남긴다.

    python3 kdef_scan.py --scan [--quarter 2026Q2] [--limit 80]   # → assets/universe_probe.json
그 뒤 `kdef_universe.py --write` 가 승격분을 '탐색' 출처로 모집단에 넣는다.
"""
import argparse
import re
import sys
import time

from kdef_lib import (KIND_URL, _get, fetch_section, find_sections, latest_quarter, load_asset,
                      parse_kind, pick_report, report_kind, report_window, search_reports, toc,
                      write_asset)
from kdef_universe import _DEF, _NOT_SUPPLY
from kdef_universe import load as load_universe
from kdef_contracts import PRIME_NAMES

SECTIONS = [
    ("overview", ["사업의 개요"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품"]),
    ("sales", ["매출 및 수주상황", "수주상황", "매출실적"]),
]

# 후보 풀 — 방산 부품이 될 수 있는 제품 어휘. 넓게 잡되 **읽을 수 있는 규모**로 줄인다.
# 어휘만 넓히면 후보가 410사(≈1,200 요청)가 되어 한 웨이브가 DART를 수천 건 긁는다
# (COMMON §2 가 금한 것). 업종 화이트리스트와 함께 걸어 224사로 맞췄다.
POOL = re.compile(
    r"단조|주조|주물|주강|정밀가공|절삭|기계가공|밸브|피팅|유압|공압|실린더|액추에이터|감속기|기어|"
    r"변속기|베어링|전원|축전지|이차전지|연료전지|배전반|제어반|케이블|커넥터|안테나|레이돔|증폭기|"
    r"RF|마이크로파|센서|검출기|적외선|광학|렌즈|짐벌|자이로|관성|항법|위성|무선|암호|임베디드|"
    r"시뮬레이|복합재|탄소섬유|유리섬유|특수강|합금|티타늄|열처리|표면처리|추진|로켓|엔진|터빈|"
    r"열교환|신관|헬멧|철구조|판금|용접|계측|계장|드론|무인|구조물|전장품|통신장비|전자장비|"
    r"정밀기기|사출|가공품", re.I)
# 업종 화이트리스트 — 우리 모집단 44사가 실제로 흩어져 있는 업종 + 인접 제조업.
# **자동차 신품 부품은 반드시 포함**한다(SNT다이내믹스·한일단조·상신브레이크가 그 업종이다).
POOL_IND = re.compile(
    r"항공기,우주선|무기 및 총포탄|기타 금속 가공제품|자동차 신품 부품|전자부품|통신 및 방송 장비|"
    r"측정, 시험, 항해, 제어|특수 목적용 기계|일반 목적용 기계|컴퓨터 및 주변장치|구조용 금속제품|"
    r"절연선 및 케이블|전동기, 발전기|사진장비 및 광학기기|1차 철강|1차 비철금속|기타 화학제품|"
    r"기초 화학물질|반도체 제조업|그외 기타 운송장비|선박 및 보트|전기장비|기타 기계|금속 주조업|"
    r"정밀기기|플라스틱제품|직물|섬유|일차전지|소프트웨어")
# 방산일 수 없는 업종(고객·금융·소비재).
EXCL = re.compile(r"금융|보험|증권|은행|부동산|임대|음식|식료|음료|주류|담배|의복|가죽|신발|화장품|"
                  r"농업|어업|임업|광업|숙박|교육|오락|게임|스포츠|광고|출판|영화|방송프로그램|"
                  r"여행|운송업|창고|도매업|소매업|의약|의료용|사회복지|협회|수도|하수")

# 방산 낱말 — 본문에서 세는 것. 모집단 ②의 어휘에 본문에서만 나오는 말을 더한다.
DEF_WORDS = re.compile(
    r"방위사업청|국방과학연구소|국방기술진흥연구소|방위산업|방산|군수|군납|국방|군용|무기체계|"
    r"방위력\s*개선|유도무기|유도탄|탄약|전차|자주포|장갑차|함정|잠수함|전투기|훈련기|헬기|"
    r"전투체계|레이다|레이더|전자전|피아식별|야시|열영상|창정비|군수지원|방산업체|방산물자|"
    r"방위산업체|군수품|K9|K2전차|천궁|현무|수리온|KF-21|T-50", re.I)
GOV_WORDS = re.compile(r"방위사업청|국방과학연구소|국방기술진흥연구소|방위사업법|방산물자|방위산업체")

PROMOTE_MENTIONS = 2       # 체계업체 언급 합
PROMOTE_HITS = 8           # 본문에서 방산을 이만큼 말하면 공급망으로 본다
PROMOTE_HITS_WITH_MENTIONS = 4
RULE = ("방산 낱말 ≥ %d, 또는 체계업체 언급 ≥ %d 이면서 방산 낱말 ≥ %d, "
        "또는 방위사업청·국방과학연구소·방산물자 지정 언급이 있으면서 방산 낱말 ≥ %d. "
        "II절을 못 읽은 회사는 승격하지 않는다(fail-closed)."
        % (PROMOTE_HITS, PROMOTE_MENTIONS, PROMOTE_HITS_WITH_MENTIONS, PROMOTE_HITS_WITH_MENTIONS))


def judge(row):
    if not row.get("ok"):
        return False
    hits = row.get("hits", 0)
    ment = sum((row.get("mentions") or {}).values())
    gov = row.get("gov", 0)
    return (hits >= PROMOTE_HITS
            or (ment >= PROMOTE_MENTIONS and hits >= PROMOTE_HITS_WITH_MENTIONS)
            or (gov >= 1 and hits >= PROMOTE_HITS_WITH_MENTIONS))


def role_for(row):
    """승격 종목의 역할 힌트 — 본문 낱말로 갈라 둔다(계약 공시가 확인하면 바뀐다)."""
    ind = row.get("industry") or ""
    p = (row.get("product") or "")
    if re.search(r"1차 철강|1차 비철금속|기초 화학물질", ind) or re.search(r"화약|특수강|합금|소재", p):
        return "material"
    if re.search(r"정비|용역|시뮬레이|군수지원", p) and not re.search(r"제조|부품|장비", p):
        return "service"
    return "part"


def pool(recs, universe):
    uni = {r["stock"] for r in universe}
    out = []
    for r in recs:
        if r["stock"] in uni:
            continue
        ind, prod = r.get("industry") or "", r.get("product") or ""
        if EXCL.search(ind) or ind in _NOT_SUPPLY or not POOL_IND.search(ind):
            continue
        if _DEF.search(prod):
            continue          # 이미 ② 제품 경로가 잡는다
        if POOL.search(prod):
            out.append(r)
    return out


def probe_one(rec, quarter):
    """II절 본문 → 방산 낱말 횟수·체계업체 언급. 실패는 ok=False 로 남긴다(캐시하지 않는다)."""
    st = rec["stock"]
    out = {"stock": st, "name": rec["name"], "market": rec["market"],
           "industry": rec["industry"], "product": rec["product"],
           "ok": False, "hits": 0, "gov": 0, "mentions": {}, "terms": {}, "note": ""}
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
    for m in DEF_WORDS.finditer(text):
        t = m.group(0)
        terms[t] = terms.get(t, 0) + 1
    out["terms"] = dict(sorted(terms.items(), key=lambda kv: -kv[1])[:12])
    out["hits"] = sum(terms.values())
    out["gov"] = len(GOV_WORDS.findall(text))
    ment = {}
    for stock, pat in PRIME_NAMES.items():
        n = len(re.findall(pat, text, re.I))
        if n:
            ment[stock] = n
    out["mentions"] = ment
    out["ok"] = True
    # 근거 문장 — 방산 낱말 주변 한 토막을 그대로 남긴다(사람이 확인할 수 있게)
    m = DEF_WORDS.search(text)
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
            promoted[r["stock"]] = {
                "role": role_for(row), "hits": row["hits"], "gov": row["gov"],
                "mentions": row["mentions"], "terms": row["terms"],
                "reason": "정기보고서 II절에서 방산 낱말 %d회%s%s — \"%s\""
                          % (row["hits"],
                             (", 방위사업청·국방과학연구소 등 %d회" % row["gov"]) if row["gov"] else "",
                             (", 체계업체 언급 %s" % row["mentions"]) if row["mentions"] else "",
                             (row.get("quote") or "")[:120])}
            log.write("  [승격] %s %s hits=%d gov=%d %s\n"
                      % (r["stock"], r["name"][:14], row["hits"], row["gov"], row["mentions"]))
        else:
            rejected.append({k: row[k] for k in
                             ("stock", "name", "industry", "product", "hits", "gov", "mentions", "terms")})
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
        for r in cands[:40]:
            print("  %s %-16s %-22s %s" % (r["stock"], r["name"][:16], r["industry"][:22],
                                           (r["product"] or "")[:44]))
        return
    if a.scan:
        scan(a.quarter or latest_quarter(), a.limit)


if __name__ == "__main__":
    sys.exit(main())
