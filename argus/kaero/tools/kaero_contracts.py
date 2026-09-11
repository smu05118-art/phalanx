#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero_contracts — 수시공시 「단일판매ㆍ공급계약체결」(I001) 원장.

**이 탭에서는 보조 원장이다.** scout 실측으로 우주항공 표본 8사의 계약 공시는 중앙값
**연 0.75건**뿐이다(조선·방산과 다른 점). 이유가 원문에 있다 — 아스트 II-4 는 이렇게 적는다:

> 현재의 수주계약은 항공산업의 특성상 대부분 장기 공급 계약으로 통상 해당 기종이 단종될
> 때까지 자동 연장되는 관행이 있습니다.

한 번 계약하면 수십 년 가는 LTA 라 **새 공시가 드물다**. 그래서 이 탭의 1차 원장은
정기보고서 II-4(그리고 상세표)의 계약 줄이고(`kaero_reports._contract_rows`),
이 파일은 '최근에 새로 딴 일감'을 보태는 얇은 원장이다 — 스펙 §데이터원천 그대로.

이 산업 특유의 처리:
  · **계약금액이 외화**로 오는 건이 있다(`계약금액 총액(USD)`). 원화로 환산하지 않고
    통화를 같이 싣는다(FINDINGS §1 와 같은 규칙).
  · 계약상대가 Boeing·Airbus·Spirit 처럼 **OEM·Tier-1 실명**이다 — 고객 계층으로 갈라 둔다.

캐시: assets/contracts/<종목>/<rcpNo>.json — 원문 (라벨,값) 전부 보존(`kv`).
분류는 **빌드 때 캐시에서 다시** 한다(사전이 자라도 재수집이 필요 없게, COMMON §0-4).

    python3 kaero_contracts.py --collect --from 20200101
    python3 kaero_contracts.py --build
"""
import argparse
import json
import os
import re
import sys
import time

from kaero_lib import (ASSETS, atomic_write, fetch_section, load_asset, num_of,
                       parse_tables, search_reports, toc, write_asset)
from kaero_reports import customers_in, domain_of, nature_of
from kaero_universe import load as load_universe

CACHE = os.path.join(ASSETS, "contracts")

# ── 계약상대 갈래 ───────────────────────────────────────────
_GOV = re.compile(r"방위사업청|국방과학연구소|국방기술진흥연구소|한국항공우주연구원|한국천문연구원|"
                  r"과학기술정보통신부|산업통상자원부|우주항공청|조달청|국토교통부|기상청|"
                  r"항공안전기술원|한국연구재단|Korea Aerospace Research")
_G2G = re.compile(r"국방부|국방물자청|국방조달|군비청|방위성|Ministry of Defen[cs]e|NASA|ESA\b|"
                  r"European Space Agency")
_KR = re.compile(r"대한민국|Republic of Korea")
_ANON = re.compile(r"비공개|공시유보|유보|익명|영업비밀|소재\s*업체|소재\s*법인|"
                   r"해외\s*[^,()]{0,8}(?:업체|고객|법인|바이어)|국내\s*[^,()]{0,8}업체")
_LATIN = re.compile(r"[A-Za-z]{4,}")


def party_kind(party):
    """계약상대 → (갈래, 고객 계층). 못 읽으면 ('UNKNOWN', None).

    이 산업은 상대가 **OEM·Tier-1 실명**인 것이 특징이라 계층을 함께 돌려준다."""
    p = (party or "").strip()
    if not p or p in ("-", "—"):
        return "UNKNOWN", None
    if _ANON.search(p):
        return "ANON", None
    hits = customers_in(p)
    if hits:
        return ("PRIME" if hits[0]["tier"] == "prime" else "OEM"), hits[0]["tier"]
    if _G2G.search(p) and not _KR.search(p):
        return "G2G", "gov"
    if _GOV.search(p):
        return "GOV", "gov"
    if _LATIN.search(p):
        return "FOREIGN", None
    return "DOMESTIC", None


# ── 금액·통화 ───────────────────────────────────────────────
# 라벨에 통화가 적혀 온다 — `계약금액 총액(원)` · `계약금액 총액(USD)`.
_CUR_LABEL = [("USD", re.compile(r"USD|달러|\$")), ("EUR", re.compile(r"EUR|유로|€")),
              ("JPY", re.compile(r"JPY|엔화")), ("KRW", re.compile(r"원\)|원$|KRW"))]
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
    """needle 을 모두 품은 라벨 중 **가장 짧은** 라벨의 값 — 정정 표(긴 라벨)보다 본표가 이긴다."""
    hits = [(len(k), i, v) for i, (k, v) in enumerate(kv.items()) if all(n in k for n in needles)]
    return min(hits)[2] if hits else None


def _amount(kv):
    """계약금액 → (값(백만, 그 통화), 통화, 원문 라벨). 통화를 못 읽으면 KRW로 두지 않고 None."""
    cands = [(k, v) for k, v in kv.items() if "계약금액" in k and "비율" not in k and "대비" not in k]
    if not cands:
        cands = [(k, v) for k, v in kv.items() if "공급계약금액" in k]
    for k, v in sorted(cands, key=lambda kv2: len(kv2[0])):
        n = num_of(v)
        if n is None:
            continue
        for cur, pat in _CUR_LABEL:
            if pat.search(k):
                return round(n / 1e6, 6), cur, k
        # 통화 표기가 없는 양식(코스닥 「1. 판매ㆍ공급계약 내용」)은 원화다 — 다만 그렇게 적는다.
        return round(n / 1e6, 6), "KRW", k + "(통화 표기 없음 — 원으로 읽음)"
    return None, None, ""


def _fields_from_kv(kv):
    name = (_find(kv, "체결계약명") or _find(kv, "계약명")
            or _find(kv, "판매", "공급계약", "내용") or _find(kv, "공급계약 내용") or "")
    if not name and _find(kv, "판매공급계약구분"):
        name = _find(kv, "세부내용") or ""
    amt, cur, amt_label = _amount(kv)
    party = _find(kv, "계약상대") or ""
    kind, tier = party_kind(party)
    start = _date(_find(kv, "계약기간", "시작") or _find(kv, "시작일") or "")
    end = _date(_find(kv, "계약기간", "종료") or _find(kv, "종료일") or "")
    blob = name + " " + party
    return {
        "name": name,
        "domain": domain_of(blob),
        "nature": nature_of(blob, start or "", end or ""),
        "amount": amt, "cur": cur, "amount_label": amt_label,
        "rev_ratio": num_of(_find(kv, "매출액대비") or ""),
        "party": party, "party_kind": kind, "party_tier": tier,
        "customers": customers_in(party) or customers_in(name),
        "region": _find(kv, "판매", "지역") or _find(kv, "공급지역") or "",
        "start": start or "", "end": end or "", "years": _years(start, end),
        "end_raw": (_find(kv, "계약기간", "종료") or _find(kv, "종료일") or ""),
        "signed": _date(_find(kv, "수주", "일자") or _find(kv, "계약(수주)일자")
                        or _find(kv, "계약(수주)일") or "") or "",
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
    """캐시 → contracts.json. 정정공시는 같은 (회사, 계약명, 수주일)의 원본을 덮는다."""
    out = []
    stocks = stocks or (sorted(os.listdir(CACHE)) if os.path.isdir(CACHE) else [])
    for st in stocks:
        d = os.path.join(CACHE, st)
        if not os.path.isdir(d):
            continue
        recs = []
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
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
        rows = build()
        from collections import Counter
        print("계약 %d건 · 영역 %s" % (len(rows), dict(Counter(r["domain"] for r in rows))))
        print("  성격 %s" % dict(Counter(r["nature"] for r in rows)))
        print("  상대 %s · 통화 %s" % (dict(Counter(r["party_kind"] for r in rows)),
                                    dict(Counter(r["cur"] for r in rows))))
        for r in rows[-6:]:
            print("  ", r["stock"], r["signed"], r["domain"], r["nature"], r["party_kind"],
                  (r["name"] or "")[:34], r["amount"], r["cur"])


if __name__ == "__main__":
    sys.exit(main())
