#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scout_contracts — 표본 각 사의 수시공시 「단일판매ㆍ공급계약체결」 건수를 센다(최근 2년).

수주기반 산업인지 가리는 세 번째 축이다(scout.md §2). 정기보고서의 수주표가 부문 합계뿐이어도
계약공시가 잦으면 **계약 단위 원장**을 만들 수 있다(kship_contracts 가 그렇게 만들어졌다).

세는 규칙:
  · 제목이 `단일판매ㆍ공급계약`(가운뎃점 방언 포함)인 거래소 수시공시(publicType I001)
  · `[기재정정]`은 원공시의 정정이므로 **따로** 센다 — 본 건수에 넣으면 부풀려진다
  · `해지`는 계약 소멸이므로 따로 센다
  · 검색 상한(maxResults=100)에 닿으면 `capped=true` — '100건 이상'으로만 말한다(fail-closed)

    python3 scout_contracts.py --end 20260911            # assets/contracts.json
    python3 scout_contracts.py --only 034020 --dump
"""
import argparse
import json
import os
import re
import sys
import time

from scout_lib import ASSETS, atomic_write, load_asset, search_reports, write_asset

CACHE = os.path.join(ASSETS, "contracts_cache")

# 가운뎃점은 `ㆍ`(U+318D)·`·`(U+00B7)·`,`·공백 등으로 흔들린다 — 낱말만 본다.
_SUPPLY = re.compile(r"단일\s*판매.{0,3}공급\s*계약")
_FIX = re.compile(r"\[기재정정\]|\[첨부정정\]|정정신고")
_CANCEL = re.compile(r"해지|해제|취소")


def count_one(stock, start, end, force=False):
    path = os.path.join(CACHE, "%s_%s_%s.json" % (stock, start, end))
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    out = {"stock": stock, "start": start, "end": end, "ok": False}
    try:
        reports = search_reports(stock, start, end, "I001")
    except Exception as e:
        out["note"] = "%s: %s" % (type(e).__name__, str(e)[:80])
        return out                       # 실패는 캐시하지 않는다
    new, fix, cancel, titles = 0, 0, 0, []
    for rcp, title in reports:
        if not _SUPPLY.search(title or ""):
            continue
        if _CANCEL.search(title):
            cancel += 1
        elif _FIX.search(title):
            fix += 1
        else:
            new += 1
            if len(titles) < 5:
                titles.append({"rcp": rcp, "title": title[:70]})
    out.update(ok=True, n_all=len(reports), n_new=new, n_fix=fix, n_cancel=cancel,
               capped=len(reports) >= 100, sample=titles,
               per_year=round(new / 2.0, 1))
    os.makedirs(CACHE, exist_ok=True)
    atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="20260911", help="검색 종료일(YYYYMMDD) — 기록에 남는다")
    ap.add_argument("--only")
    ap.add_argument("--sector")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dump", action="store_true")
    a = ap.parse_args()
    start = "%d%s" % (int(a.end[:4]) - 2, a.end[4:])

    if a.only:
        recs = [{"stock": s.strip(), "name": s.strip(), "sector": "-"}
                for s in a.only.split(",")]
    else:
        d = load_asset("sample.json")
        seen, recs = set(), []
        for r in d["rows"]:
            if a.sector and r["sector"] != a.sector:
                continue
            if r["stock"] in seen:
                continue
            seen.add(r["stock"])
            recs.append(r)
    rows = []
    t0 = time.time()
    for i, r in enumerate(recs, 1):
        c = count_one(r["stock"], start, a.end, a.force)
        c["name"], c["sector"] = r.get("name"), r.get("sector")
        rows.append(c)
        sys.stderr.write("[%3d/%d] %-6s %-16s 신규 %-4s 정정 %-4s 해지 %-3s %s\n" % (
            i, len(recs), r["stock"], (r.get("name") or "")[:16], c.get("n_new"),
            c.get("n_fix"), c.get("n_cancel"),
            ("상한 도달(100건 이상)" if c.get("capped") else c.get("note", ""))))
        sys.stderr.flush()
        if a.dump:
            print(json.dumps(c, ensure_ascii=False, indent=1))
    if not a.only and not a.sector:
        write_asset("contracts.json", {"start": start, "end": a.end, "n": len(rows), "rows": rows})
    sys.stderr.write("== %d사 %.0fs\n" % (len(rows), time.time() - t0))


if __name__ == "__main__":
    sys.exit(main())
