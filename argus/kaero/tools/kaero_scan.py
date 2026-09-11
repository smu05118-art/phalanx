#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero_scan — 모집단 ④ 겹. KIND 제품 문구가 항공·우주를 말하지 않는 상장사를
**정기보고서 II절 본문**으로 찾아 승격한다(스펙 §모집단 ③ — Tier-2 부품사 확장).

이 산업은 kdef 보다 증거가 **선명하다**. 고객이 세계에 몇 안 되는 기체 제작사·엔진 제작사라
본문에 **실명으로** 나온다(FINDINGS §2·§3):

    아스트 수주표 품목 열   SPIRIT · EMBRAER · BOMBARDIER · IAI · RUAG
    하이즈항공 매출처 각주   BOE(Boeing Commercial Airplanes)
    한화에어로 판매전략      "GE, P&W, 롤스로이스 등과의 엔진부품공급 계약"

그런데 문구만 세면 틀린다(실측). 반도체 회사 본문의 "항공기 관련 LiDAR" 한 줄과 다른 맥락의
`Lockheed` 언급이 겹쳐 나노씨엠에스가 승격됐고, 정작 **대한항공은 떨어졌다** — 운송 낱말이
99회라 문구 규칙을 통과하지 못한다. 그러나 대한항공 II-4 매출표에는 `2. 항공우주사업` 부문이
있고 수주표 품목은 `항공기체 · 군용기MRO · 무인기` 다.

그래서 승격 1순위는 **II-4 표의 부문·품목 이름**(등급 A)이고, 문구는 보조(등급 B)다.

  1) 후보 풀 — 제조 업종이면서 제품 문구가 가공·소재·전장 어휘에 걸리는 회사(모집단 제외).
     항공 **운송** 업종도 후보에 넣는다 — 대한항공 항공우주사업본부처럼 운송사 안에 제조가 있다.
  2) 증거 — II-4 표의 부문·품목 이름(`seg_aero`)과, II절 본문의
     `oem` OEM·Tier-1 실명 · `prime` 국내 체계업체 언급 · `hits` 항공·우주 낱말 · `struct` 기체구조물 낱말
  3) 승격(fail-closed) — 본문을 못 읽었으면(ok=False) **절대 승격하지 않는다**.

    python3 kaero_scan.py --pool-only
    python3 kaero_scan.py --scan [--quarter 2026Q2] [--limit 40]   # → assets/universe_probe.json
그 뒤 `kaero_universe.py --write` 가 승격분을 '탐색' 출처로 모집단에 넣는다.
"""
import argparse
import re
import sys
import time

from kaero_lib import (KIND_URL, _get, fetch_section, latest_quarter, open_sections,
                       parse_kind, parse_tables, text_of, write_asset)
from kaero_universe import _AERO, _NOT_AERO
from kaero_universe import load as load_universe

SECTIONS = [
    ("overview", ["사업의 개요"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품"]),
    ("sales", ["매출 및 수주상황", "수주상황", "매출실적"]),
]

# ── 고객 실명 ──────────────────────────────────────────────
# OEM(기체·엔진 제작사)과 Tier-1. 한글·영문 표기가 섞여 온다.
# `AIRBUS`·`BOEING`은 대소문자 섞임이 흔해 re.I 로 본다. `GE`·`PW`는 너무 짧아 넣지 않는다
# (GE는 GE헬스케어·GE파워와 겹치고, PW는 임의의 약칭과 겹친다) — 대신 긴 꼴만 쓴다.
OEM = {
    "Boeing": r"Boeing|보잉|BOE\s*\(",
    "Airbus": r"Airbus|에어버스",
    "Embraer": r"Embraer|엠브라에르",
    "Bombardier": r"Bombardier|봄바디어",
    "Lockheed": r"Lockheed|록히드",
    "Gulfstream": r"Gulfstream|걸프스트림",
    "Spirit": r"Spirit\s*Aero|SPIRIT\b|스피릿에어로",
    "GE Aerospace": r"GE\s*Aerospace|GE\s*Aviation|제너럴\s*일렉트릭|GEnx|GE90|LEAP",
    "Pratt & Whitney": r"Pratt\s*&?\s*Whitney|프랫\s*앤\s*휘트니|P&W|PW\d{4}|GTF",
    "Rolls-Royce": r"Rolls[\s\-]?Royce|롤스로이스",
    "Safran": r"Safran|사프란",
    "Honeywell": r"Honeywell|허니웰",
    "Collins": r"Collins\s*Aero|콜린스",
    "Leonardo": r"Leonardo\s*S|레오나르도",
    "IAI": r"\bIAI\b|이스라엘항공우주",
    "TAI": r"\bTAI\b|터키항공우주",
    "RUAG": r"\bRUAG\b",
    "Mitsubishi Heavy": r"Mitsubishi\s*Heavy|미쓰비시중공업",
    "SAMC": r"\bSAMC\b|上海飛機|COMAC|코맥",
}
# 국내 체계업체 — 부품사→체계업체 연결의 근거.
PRIME = {
    "047810": r"한국항공우주(산업)?|KAI\b|카이\(주\)",
    "012450": r"한화에어로스페이스|한화테크윈",
    "003490": r"대한항공\s*항공우주|대한항공",
    "272210": r"한화시스템",
    "079550": r"LIG\s*넥스원|LIG디펜스",
    "099320": r"쎄트렉아이",
    "한국항공우주연구원": r"한국항공우주연구원|항우연|KARI\b",
}

# 항공·우주 낱말(본문에서 세는 것)
AERO_WORDS = re.compile(
    r"항공기|항공\s*부품|항공우주|우주항공|기체\s*구조|기체\s*부품|동체|주익|날개\s*구조|"
    r"벌크헤드|스트링거|나셀|파일런|랜딩기어|착륙장치|항공\s*엔진|가스터빈|엔진\s*부품|"
    r"발사체|로켓|누리호|인공위성|위성\s*체|위성\s*본체|탑재체|지상국|우주\s*발사|"
    r"감항|형식증명|AS9100|NADCAP|Nadcap|MRO|창정비|PBL|RSP|"
    r"Boeing|Airbus|Embraer|보잉|에어버스", re.I)
# 기체구조물을 직접 말하는 낱말 — 승격 보조 근거
STRUCT_WORDS = re.compile(r"기체\s*구조|기체\s*부품|동체|주익|날개\s*구조|벌크헤드|스트링거|"
                          r"나셀|파일런|SECTION\s*\d|shipset|쉽셋", re.I)
# 항공 **운송**만 말하는 문서를 막는다 — 여객·화물 낱말이 압도적이면 제조사가 아니다.
TRANSPORT_WORDS = re.compile(r"여객|화물\s*운송|운항|노선|탑승|마일리지|기내식|공항\s*이용", re.I)

# 후보 풀 — 항공 부품이 될 수 있는 제품 어휘. **넓히기만 하면 DART를 수천 건 긁는다**
# (COMMON §2). `소재`·`검사`·`시험`·`센서` 같은 일반어를 넣으면 후보가 274사가 되고 그 대부분이
# 이차전지·반도체·바이오다(실측). 항공 공급망에 실제로 쓰이는 공정·품목어만 남긴다.
POOL = re.compile(
    r"단조|주조|주물|주강|정밀\s*가공|절삭|기계\s*가공|가공품|판금|열처리|표면처리|"
    r"복합재|탄소섬유|프리프레그|티타늄|특수강|초내열|인코넬|알루미늄\s*압출|"
    r"유압|공압|액추에이터|감속기|베어링|"
    r"적외선|짐벌|자이로|관성|항법|안테나|레이돔|"
    r"전장품|하네스|시뮬레이|드론|무인기|무인\s*항공|구조물|"
    r"터빈|추진|엔진\s*부품|정밀\s*부품|정밀기기", re.I)
# 제품 문구가 다른 산업을 말하면 후보에서 뺀다 — 이차전지·반도체·바이오·화장품·건설.
POOL_NOT = re.compile(r"이차전지|2차전지|배터리|전기차|반도체|디스플레이|웨이퍼|포토레지스트|"
                      r"바이오|의약|진단|화장품|식품|해상풍력|건축|토목|정수기|가전", re.I)
POOL_IND = re.compile(
    r"항공기,우주선|항공 여객 운송업|무기 및 총포탄|기타 금속 가공제품|구조용 금속제품|"
    r"자동차 신품 부품|전자부품|통신 및 방송 장비|측정, 시험, 항해, 제어|특수 목적용 기계|"
    r"일반 목적용 기계|기타 기계|금속 주조업|1차 철강|1차 비철금속|기타 화학제품|플라스틱제품|"
    r"전기장비|그외 기타 운송장비|컴퓨터|자연과학 및 공학 연구개발|소프트웨어|"
    r"기타 과학기술 서비스|반도체 제조업|절연선 및 케이블|사진장비 및 광학기기|선박 및 보트")
EXCL = re.compile(r"금융|보험|증권|은행|부동산|임대업|음식|식료|음료|주류|담배|의복|가죽|신발|"
                  r"화장품|농업|어업|임업|광업|숙박|교육|오락|게임|스포츠|광고|출판|영화|"
                  r"방송프로그램|여행|창고|도매업|소매업|의약|의료용|사회복지|협회|수도|하수")

# ── 승격 규칙 ──────────────────────────────────────────────
# **표 근거가 문구 근거를 이긴다.** 문구 세기만으로 판정하면 반도체 회사 본문의
# "항공기 관련 LiDAR" 한 줄과 다른 맥락의 `Lockheed` 언급이 겹쳐 승격된다(실측: 나노씨엠에스).
# 반대로 대한항공은 운송 낱말이 99회라 문구 규칙에서는 떨어지는데, 매출표에 `2. 항공우주사업`
# 부문이 있고 수주표 품목이 `항공기체·군용기MRO·무인기` 다 — 이쪽이 훨씬 강한 근거다.
#
# 그래서 1순위는 **II-4 표의 부문·품목 이름**(등급 A)이고, 문구는 보조다.
SEG_AERO = re.compile(r"항공우주|항공기체|기체\s*구조|기체\s*부품|항공기\s*부품|항공\s*부품|"
                      r"군용기|무인기|완제기|발사체|인공위성|위성\s*본체|위성\s*체|탑재체", re.I)
PROMOTE_SEG = 1            # 표의 부문·품목 이름이 항공·우주를 말하면 그것으로 충분하다
PROMOTE_OEM_HITS = 12      # 표 근거가 없으면 OEM 실명 + 낱말이 넉넉하고 + 기체구조물 낱말이 있어야
PROMOTE_OEM_STRUCT = 2
PROMOTE_HITS = 25          # 실명도 없으면 낱말이 아주 많고 기체구조물 낱말이 확실해야 한다
PROMOTE_HITS_STRUCT = 3
RULE = ("① II-4 매출·수주표의 부문·품목 이름이 항공·우주를 말하면 승격(등급 A). "
        "② 표 근거가 없으면 OEM·Tier-1 실명이 있고 항공·우주 낱말 ≥ %d, 기체구조물 낱말 ≥ %d. "
        "③ 실명도 없으면 낱말 ≥ %d, 기체구조물 낱말 ≥ %d. "
        "②③ 에는 운송 낱말이 더 많으면 승격하지 않는다(항공사 본문이 제조로 오인된다). "
        "II절을 못 읽은 회사는 승격하지 않는다(fail-closed)."
        % (PROMOTE_OEM_HITS, PROMOTE_OEM_STRUCT, PROMOTE_HITS, PROMOTE_HITS_STRUCT))


def judge(row):
    if not row.get("ok"):
        return False
    if len(row.get("seg_aero") or []) >= PROMOTE_SEG:
        return True                     # ① 표 근거 — 운송 낱말과 무관하게 이긴다
    hits, struct = row.get("hits", 0), row.get("struct", 0)
    n_oem = len(row.get("oem") or {})
    if row.get("transport", 0) > hits:
        return False
    return ((n_oem >= 1 and hits >= PROMOTE_OEM_HITS and struct >= PROMOTE_OEM_STRUCT)
            or (hits >= PROMOTE_HITS and struct >= PROMOTE_HITS_STRUCT))


def role_for(row):
    p = (row.get("product") or "") + " " + (row.get("industry") or "")
    if row.get("struct", 0) >= 3:
        return "struct"
    if re.search(r"발사체|로켓|위성|지상국", p, re.I):
        return "space"
    if re.search(r"티타늄|합금|소재|복합재|탄소섬유", p) and not re.search(r"부품|조립|장비", p):
        return "material"
    if re.search(r"정비|MRO|시험|인증|용역", p) and not re.search(r"제조|부품|가공", p):
        return "service"
    return "part"


def pool(recs, universe):
    uni = {r["stock"] for r in universe}
    out = []
    for r in recs:
        if r["stock"] in uni:
            continue
        ind, prod = r.get("industry") or "", r.get("product") or ""
        if EXCL.search(ind) or not POOL_IND.search(ind):
            continue
        # 항공 **운송** 업종은 ② 제품 경로에서 통째로 빠진다(스펙 ④). 그러나 운송사 안에
        # 제조·정비 사업부가 있는 회사가 있다(대한항공 항공우주사업본부) — 제품 문구가
        # `제조`·`정비`를 말하면 후보로 올려 **본문이 판정하게** 한다. 이름으로 넣지 않는다.
        if "항공" in ind and "운송" in ind:
            if re.search(r"제조|정비|생산", prod):
                out.append(r)
            continue
        if _AERO.search(prod) and not _NOT_AERO.search(prod):
            continue          # 이미 ② 제품 경로가 잡는다
        if POOL.search(prod) and not POOL_NOT.search(prod):
            out.append(r)
    return out


def _aero_segments(sales_html):
    """II-4 절의 표에서 항공·우주를 말하는 **부문·품목 이름**을 모은다(등급 A 근거).

    이름 열만 본다 — 숫자 셀이나 비고를 읽으면 아무 표나 걸린다. 표의 머리행에 있는
    `사업부문`·`품목` 같은 일반어는 잡히지 않는다(SEG_AERO 가 구체어만 본다)."""
    from kaero_reports import _carry_units, _headered      # 표 복구는 한 벌만 쓴다
    names = set()
    for t in _headered(_carry_units(parse_tables(sales_html))):
        for r in t["rows"]:
            for c in r[:3]:
                c = (c or "").strip()
                if c and SEG_AERO.search(c):
                    names.add(c[:40])
    return names


def probe_one(rec, quarter):
    """II절 본문 → 고객 실명·낱말 수. 실패는 ok=False 로 남긴다(캐시하지 않는다)."""
    st = rec["stock"]
    out = {"stock": st, "name": rec["name"], "market": rec["market"],
           "industry": rec["industry"], "product": rec["product"],
           "ok": False, "hits": 0, "struct": 0, "transport": 0,
           "oem": {}, "prime": {}, "terms": {}, "seg_aero": [], "note": ""}
    try:
        rcp, title, found, tried = open_sections(st, quarter, SECTIONS, "overview")
        if not rcp:
            rcp, title, found, tried = open_sections(st, quarter, SECTIONS, "sales")
    except Exception as e:
        out["note"] = "검색 실패: %s" % e
        return out
    if not rcp:
        out["note"] = "정기보고서 II절 없음" + (" (후보 %d건 시도)" % len(tried) if tried else "")
        return out
    out["rcp"], out["title"] = rcp, title
    try:
        text, sales_html = "", ""
        for key in ("overview", "products", "sales"):
            if key in found:
                h = fetch_section(found[key])
                if key == "sales":
                    sales_html = h
                text += text_of(h)
    except Exception as e:
        out["note"] = "본문 읽기 실패: %s" % e
        return out
    # ① 표 근거 — II-4 표의 **부문·품목 이름**. 이름 열(숫자가 아닌 앞쪽 셀)만 본다.
    if sales_html:
        try:
            out["seg_aero"] = sorted(_aero_segments(sales_html))[:12]
        except Exception as e:
            out["note"] = "표 읽기 실패: %s" % e
    if not text.strip():
        out["note"] = "II절 본문이 빔"
        return out
    text = re.sub(r"[\s　]+", " ", text)
    terms = {}
    for m in AERO_WORDS.finditer(text):
        t = m.group(0)
        terms[t] = terms.get(t, 0) + 1
    out["terms"] = dict(sorted(terms.items(), key=lambda kv: -kv[1])[:12])
    out["hits"] = sum(terms.values())
    out["struct"] = len(STRUCT_WORDS.findall(text))
    out["transport"] = len(TRANSPORT_WORDS.findall(text))
    out["oem"] = {k: len(re.findall(p, text, re.I)) for k, p in OEM.items()
                  if re.search(p, text, re.I)}
    out["prime"] = {k: len(re.findall(p, text, re.I)) for k, p in PRIME.items()
                    if re.search(p, text, re.I)}
    out["ok"] = True
    m = STRUCT_WORDS.search(text) or AERO_WORDS.search(text)
    out["quote"] = text[max(0, m.start() - 70):m.start() + 130].strip() if m else ""
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
            seg = row.get("seg_aero") or []
            promoted[r["stock"]] = {
                "role": role_for(row), "hits": row["hits"], "struct": row["struct"],
                "oem": row["oem"], "prime": row["prime"], "terms": row["terms"],
                "seg_aero": seg, "grade": "A" if seg else "B",
                "reason": ("II-4 표의 부문·품목 이름 %s — 항공·우주 사업이 표로 구분돼 있다"
                           % (seg[:6],)) if seg else
                          ("정기보고서 II절에서 항공·우주 낱말 %d회(기체구조물 %d회)%s%s — \"%s\""
                           % (row["hits"], row["struct"],
                              (", OEM·Tier-1 실명 %s" % list(row["oem"])) if row["oem"] else "",
                              (", 체계업체 언급 %s" % list(row["prime"])) if row["prime"] else "",
                              (row.get("quote") or "")[:130]))}
            log.write("  [승격] %s %-14s %s hits=%d struct=%d seg=%s oem=%s\n"
                      % (r["stock"], r["name"][:14], promoted[r["stock"]]["grade"],
                         row["hits"], row["struct"], seg[:3], list(row["oem"])))
        else:
            rejected.append({k: row[k] for k in
                             ("stock", "name", "industry", "product", "hits", "struct",
                              "transport", "oem", "prime", "terms", "seg_aero")})
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
        cands = pool(parse_kind(_get(KIND_URL)), load_universe())
        print("후보 %d사" % len(cands))
        for r in cands:
            print("  %s %-16s %-24s %s" % (r["stock"], r["name"][:16], r["industry"][:24],
                                           (r["product"] or "")[:44]))
        return
    if a.scan:
        scan(a.quarter or latest_quarter(), a.limit)


if __name__ == "__main__":
    sys.exit(main())
