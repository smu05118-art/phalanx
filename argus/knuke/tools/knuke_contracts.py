#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""knuke_contracts — 사업 단위 원장을 수시공시 「단일판매ㆍ공급계약체결」(I001)에서 만든다.

정기보고서 II-4 수주표가 부문 합계뿐인 회사도 계약 공시에는 **발주처·계약명·계약기간**이
개별로 나온다(스펙 §데이터 원천). 원전·발전기자재의 특징:

  · **발주처가 관급이 많다** — 한국수력원자력·한국전력·발전 5사가 실명으로 나온다(GOV).
    조선의 '○○ 소재 선사' 익명 문제가 여기엔 없다.
  · **계약기간이 초장기다**(5~10년, 신한울 2033년까지). 종료일이 인도/완공 시점이라
    조선의 '선표'에 해당하는 납기 스케줄의 대용이 된다. 날짜로 파싱 안 되면 만들지 않는다(fail-closed).
  · 계약상대 네 갈래 — `GOV`(한수원·한전·발전사·조달청 등 관급) · `PRIME`(주기기·설계 대형사
    하도급) · `FOREIGN`(해외 발전사·EPC) · `DOMESTIC`(국내 기업).

캐시: assets/contracts/<종목>/<rcpNo>.json — 원문 (라벨,값) 전부 보존(`kv`).
분류는 **빌드 때 캐시에서 다시** 한다(사전이 자라도 재수집 불필요, COMMON §0-4).

    python3 knuke_contracts.py --collect --from 20200101
    python3 knuke_contracts.py --build
"""
import argparse
import json
import os
import re
import sys
import time

from knuke_lib import (ASSETS, atomic_write, fetch_section, has_asset, load_asset,
                       num_of, parse_tables, search_reports, toc, write_asset)
from knuke_universe import load as load_universe

CACHE = os.path.join(ASSETS, "contracts")

# ── 계약상대 갈래 ───────────────────────────────────────────
# 관급(발주처) — 한수원·한전·발전 5사·공공기관. 영문 병기가 붙으므로 부분일치.
_GOV = re.compile(r"한국수력원자력|한수원|KHNP|한국전력공사|한국전력(?!기술)|KEPCO|한전(?!KPS|기술)|"
                  r"남동발전|중부발전|서부발전|남부발전|동서발전|한국지역난방|지역난방공사|"
                  r"한국가스공사|KOGAS|조달청|한국원자력|원자력환경공단|한국에너지|발전소\s*본부|"
                  r"수력원자력|Korea Hydro")
# 국내 주기기·설계·정비 대형사(하도급 상대). 부품사 → 이 회사로 연결을 되짚는다.
PRIME_NAMES = {
    "034020": r"두산에너빌리티|두산중공업|Doosan\s*Enerbility|Doosan\s*Heavy",
    "052690": r"한전기술|한국전력기술|KEPCO\s*E&C|KOPEC",
    "051600": r"한전KPS|한전\s*KPS|KEPCO\s*KPS|KPS\b",
}
# 해외 발전사·EPC — 라틴 문자 4자 이상이거나 나라 이름.
_LATIN = re.compile(r"[A-Za-z]{4,}")
_FOREIGN_HINT = re.compile(r"체코|루마니아|폴란드|사우디|UAE|이집트|미국|프랑스|영국|불가리아|"
                           r"두코바니|바라카|체르나보다|웨스팅하우스|Westinghouse|EDF|해외")
# 익명 표기 — 발전기자재는 드물지만(보안·경영상 비밀) 남긴다.
_ANON = re.compile(r"비공개|공시유보|유보|익명|영업비밀|소재\s*업체|소재\s*법인|"
                   r"해외\s*[^,()]{0,8}(?:업체|고객|법인|바이어)")


def party_kind(party):
    """계약상대 문자열 → (갈래, 대형사 종목코드 or None). 못 읽으면 ('UNKNOWN', None)."""
    p = (party or "").strip()
    if not p or p in ("-", "—"):
        return "UNKNOWN", None
    if _ANON.search(p):
        return "ANON", None
    for stock, pat in PRIME_NAMES.items():
        if re.search(pat, p, re.I):
            return "PRIME", stock
    if _GOV.search(p):
        return "GOV", None
    if _FOREIGN_HINT.search(p) or (_LATIN.search(p) and not re.search(r"주식회사|\(주\)|㈜", p)):
        return "FOREIGN", None
    return "DOMESTIC", None


# ── 발전원(domain)·공급 계층(tier) ──────────────────────────

def _domains():
    pairs = []
    for d in load_asset("domains.json")["domains"]:
        for k in d["keywords"]:
            pairs.append((k["kw"].lower().replace(" ", ""), d["id"], k["prio"]))
    pairs.sort(key=lambda p: (-p[2], -len(p[0])))
    return [(kw, did) for kw, did, _ in pairs]


_DOM_PAIRS = None


def domain_of(name):
    """계약명·사업명 → 발전원 id. 못 찾으면 None(추정하지 않는다)."""
    global _DOM_PAIRS
    if _DOM_PAIRS is None:
        _DOM_PAIRS = _domains()
    t = (name or "").lower().replace(" ", "")
    for kw, did in _DOM_PAIRS:
        if kw and kw in t:
            return did
    return None


def _ctypes():
    # 수출 계약명은 영문이다(`Gas Turbine`·`FGD`) — 대소문자를 가리지 않는다.
    return [(re.compile(c["pattern"], re.I), c["id"])
            for c in load_asset("contract_types.json")["types"]]


_CT = None


def ctype_of(name):
    """계약명 → 공급 계층 id. 못 읽으면 'UNKNOWN'."""
    global _CT
    if _CT is None:
        _CT = _ctypes()
    n = name or ""
    for rx, cid in _CT:
        if rx.search(n):
            return cid
    return "UNKNOWN"


# 공시 첫 칸 「1. 판매ㆍ공급계약 구분」 — 실측 분포 공사수주·용역제공·기타 판매ㆍ공급계약.
# 계약명으로 계층을 못 읽었을 때만 이 **원문 칸**을 근거로 쓴다(추정이 아니라 공시 구분의 직역).
# '용역제공'은 설계·정비·검사를 한데 묶은 말이라 계층을 가르지 못하므로 승격시키지 않는다.
_KIND_TIER = {"공사수주": "EPC"}


def tier_from_kind(kind_raw):
    return _KIND_TIER.get(re.sub(r"[\s　]", "", kind_raw or ""))


_DATE = re.compile(r"(\d{4})[-.\s/]*(\d{1,2})[-.\s/]*(\d{1,2})")


def _date(s):
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
    hits = [(len(k), i, v) for i, (k, v) in enumerate(kv.items()) if all(n in k for n in needles)]
    return min(hits)[2] if hits else None


# SMR 은 별도 축으로 세우지 않고 계약명 문자열 태그로만 남긴다(스펙 §왜수주기반 5).
_SMR = re.compile(r"SMR|소형모듈원자로|i-SMR|혁신형\s*소형")


def _fields_from_kv(kv):
    # 유가증권 「- 체결계약명」 · 코스닥 「1. 판매ㆍ공급계약 내용」 두 양식.
    name = (_find(kv, "체결계약명") or _find(kv, "계약명")
            or _find(kv, "판매", "공급계약", "내용") or _find(kv, "공급계약 내용") or "")
    if not name and _find(kv, "판매공급계약구분"):
        name = _find(kv, "세부내용") or ""
    amt_krw = num_of(_find(kv, "계약금액 총액(원)") or _find(kv, "계약금액(원)")
                     or _find(kv, "확정 계약금액") or _find(kv, "계약금액") or "")
    party = _find(kv, "계약상대") or ""
    kind, prime = party_kind(party)
    kind_raw = _find(kv, "판매공급계약구분") or ""
    tier, tier_basis = ctype_of(name), "name"
    if tier == "UNKNOWN":
        t2 = tier_from_kind(kind_raw)
        tier, tier_basis = (t2, "kind") if t2 else ("UNKNOWN", "")
    start = _date(_find(kv, "계약기간", "시작") or _find(kv, "시작일") or "")
    end = _date(_find(kv, "계약기간", "종료") or _find(kv, "종료일") or "")
    dom = domain_of(name)
    return {
        "name": name,
        "domain": dom,
        "tier": tier,
        "tier_basis": tier_basis,      # 'name'(계약명) | 'kind'(공시 「판매ㆍ공급계약 구분」) | ''
        "kind_raw": kind_raw,
        "smr": bool(_SMR.search(name or "")),
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
        "note": _find(kv, "기타", "중요") or _find(kv, "기타") or "",
        "withheld": _find(kv, "공시유보", "유보사유") or _find(kv, "유보사유") or "",
        "withheld_until": _find(kv, "공시유보", "유보기한") or _find(kv, "유보기한") or "",
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
            except Exception as e:
                log.write("[warn] %s %s %s\n" % (st, rcp, e))
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            atomic_write(path, json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
            got += 1
        log.write("%s 계약 공시 %d건 중 캐시 %d건\n" % (st, len(cons), got))
        log.flush()


def build(stocks=None):
    """캐시 → contracts.json. 정정공시는 같은 (회사, 계약명, 수주일)의 원본을 덮는다."""
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
        for r in sorted(recs, key=lambda r: r["rcp"]):
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
        print("계약 %d건 · 발전원 %s" % (len(rows), dict(Counter(r["domain"] for r in rows))))
        print("  공급계층 %s" % dict(Counter(r["tier"] for r in rows)))
        print("  상대 %s" % dict(Counter(r["party_kind"] for r in rows)))
        for r in rows[-6:]:
            print("  ", r["stock"], r["signed"], r["domain"], r["tier"], r["party_kind"],
                  (r["name"] or "")[:34], r["amt_krw_m"], r["years"])


if __name__ == "__main__":
    sys.exit(main())
