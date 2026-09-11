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
                  r"국군|조달청|Defense Acquisition Program|DAPA")
# 해외 국방부 — `크로아티아 국방부 (The Ministry of Defence…)`. 우리 국방부와 섞이지 않게
# `대한민국`이 함께 적힌 건은 GOV 로 보낸다.
_G2G = re.compile(r"국방부|Ministry of Defen[cs]e|Ministry of National Defen[cs]e|Defence Ministry")
_KR = re.compile(r"대한민국|Republic of Korea")
# 익명 표기 — 실측 19건 중 1건(KAI `해외 완제기 업체`). 이름이 없으면 없다고 적는다.
_ANON = re.compile(r"비공개|공시유보|유보|익명|영업비밀|소재\s*업체|소재\s*법인|"
                   r"해외\s*[^,()]{0,8}(?:업체|고객|법인|바이어)|국내\s*[^,()]{0,8}업체")
_LATIN = re.compile(r"[A-Za-z]{4,}")
# 체계업체 이름(정식·약칭·구명) → 종목코드. 하도급 계약의 상대를 여기서 되짚는다.
PRIME_NAMES = {
    "012450": r"한화에어로스페이스|한화\s*에어로|Hanwha\s*Aerospace",
    "047810": r"한국항공우주산업|한국항공우주|KAI\b|Korea Aerospace",
    "079550": r"LIG디펜스앤에어로스페이스|LIG넥스원|LIG\s*Nex1|엘아이지넥스원",
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
    if _G2G.search(p) and not _KR.search(p):
        return "G2G", None       # 해외 국방부. FMS 인지 직수출인지는 공시에 없다(FINDINGS §9)
    if _GOV.search(p):
        return "GOV", None
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


def domain_of(name):
    """체결계약명 → 계통 id. 못 찾으면 None(추정하지 않는다)."""
    global _DOM_PAIRS
    if _DOM_PAIRS is None:
        _DOM_PAIRS = _domains()
    t = (name or "").lower().replace(" ", "")
    for kw, did in _DOM_PAIRS:
        if kw and kw in t:
            return did
    return None


def _ctypes():
    return [(re.compile(c["pattern"]), c["id"]) for c in load_asset("contract_types.json")["types"]]


_CT = None


def ctype_of(name):
    """체결계약명 → 계약유형 id(FINDINGS §3: 계약명에 그대로 적힌다). 못 읽으면 'UNKNOWN'."""
    global _CT
    if _CT is None:
        _CT = _ctypes()
    n = name or ""
    for rx, cid in _CT:
        if rx.search(n):
            return cid
    return "UNKNOWN"


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
    본표(짧은 라벨)가 이긴다."""
    hits = [(len(k), i, v) for i, (k, v) in enumerate(kv.items()) if all(n in k for n in needles)]
    return min(hits)[2] if hits else None


# 국내 방산 계약의 대금 성격 — 원문 문구 그대로(FINDINGS §4). 이익률 수치는 공시에 없다.
_DEF_PAY = re.compile(r"방위산업에\s*관한\s*착수금\s*및\s*중도금\s*지급규칙|착수금\s*및\s*중도금")


def _fields_from_kv(kv):
    name = _find(kv, "체결계약명") or _find(kv, "계약명") or ""
    if not name and _find(kv, "판매공급계약구분"):
        name = _find(kv, "세부내용") or ""
    amt_krw = num_of(_find(kv, "계약금액(원)") or _find(kv, "계약금액") or "")
    party = _find(kv, "계약상대") or ""
    kind, prime = party_kind(party)
    start = _date(_find(kv, "계약기간", "시작") or _find(kv, "시작일") or "")
    end = _date(_find(kv, "계약기간", "종료") or _find(kv, "종료일") or "")
    payterm = _find(kv, "대금지급") or ""
    dom = domain_of(name)
    return {
        "name": name,
        "domain": dom,
        "ctype": ctype_of(name),
        "civil": dom == "CIVIL",
        "amt_krw_m": (round(amt_krw / 1e6, 3) if amt_krw is not None else None),   # 백만원
        "rev_ratio": num_of(_find(kv, "매출액대비") or ""),
        "party": party,
        "party_kind": kind,
        "party_prime": prime,
        "region": _find(kv, "판매", "지역") or _find(kv, "공급지역") or "",
        "start": start or "",
        "end": end or "",
        "years": _years(start, end),
        "end_raw": (_find(kv, "계약기간", "종료") or _find(kv, "종료일") or ""),
        "signed": _date(_find(kv, "수주", "일자") or _find(kv, "계약(수주)일자")
                        or _find(kv, "계약(수주)일") or "") or "",
        "advance": _find(kv, "선급금") or "",
        "payterm": payterm,
        "def_payrule": bool(_DEF_PAY.search(payterm or "")),
        "withheld": _find(kv, "공시유보") or "",
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
        for r in rows[-6:]:
            print("  ", r["stock"], r["signed"], r["domain"], r["ctype"], r["party_kind"],
                  (r["name"] or "")[:34], r["amt_krw_m"], r["years"])


if __name__ == "__main__":
    sys.exit(main())
