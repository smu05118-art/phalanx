#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_products — 정기보고서 「II-2 주요 제품 및 서비스」 본문을 받아 둔다(부품 분류의 근거).

부품 분류를 KIND 한 줄 문구와 ④ 탐색이 남긴 인용문만으로 하면 오탐이 남는다
(인공지능 회사가 인용문 속 '동체' 때문에 항공구조물이 된다). 회사가 **자기 제품을 적은 절**을
읽으면 그 문제가 줄어든다 — 이 스크립트는 그 절의 글자만 뽑아 캐시한다.

분기별로 바뀌는 값이 아니므로 **회사당 한 번**(가장 최근 보고서)만 받는다.
표도 셀을 이어 붙여 함께 남긴다(제품 표만 있고 문장이 없는 회사가 있다).

    python3 kdef_products.py --collect [--only 012450] [--force]
"""
import argparse
import json
import os
import re
import sys

from kdef_lib import (ASSETS, atomic_write, fetch_section, find_sections, latest_quarter,
                      parse_tables, pick_report, report_window, search_reports, toc)
from kdef_universe import load as load_universe
import kdef_reports

CACHE = os.path.join(ASSETS, "products")
SECTIONS = [("products", ["주요 제품 및 서비스", "주요 제품", "주요제품", "제품 및 서비스"])]
LIMIT = 6000                     # 회사당 저장 글자 수 — 분류에 쓰는 만큼만


def _text(html):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ")
    return re.sub(r"[ \t　]+", " ", t)


def _cached_rcp(st):
    """이미 받아 둔 정기보고서 캐시에서 **가장 최근 분기의 접수번호**를 쓴다.
    검색을 다시 하지 않으므로 회사당 DART 요청이 둘(목차·절)로 줄어든다."""
    d = os.path.join(kdef_reports.CACHE, st)
    if not os.path.isdir(d):
        return None
    for f in sorted(os.listdir(d), reverse=True):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            x = json.load(fh)
        if x.get("rcp"):
            return x["rcp"]
    return None


def collect_one(rec, quarter, force=False, log=sys.stderr):
    st = rec["stock"]
    path = os.path.join(CACHE, st + ".json")
    if os.path.exists(path) and not force:
        return None
    rcp = _cached_rcp(st)
    if not rcp:
        start, end = report_window(quarter)
        try:
            lst = pick_report(search_reports(st, start, end, "A003"), quarter) or []
        except Exception as e:
            log.write("[warn] %s 검색 실패 %s\n" % (st, e))
            return None
        rcp = lst[0][0] if lst else None
    if not rcp:
        log.write("%s 정기보고서 없음\n" % st)
        return None
    found = find_sections(toc(rcp), SECTIONS)
    if "products" not in found:
        atomic_write(path, json.dumps({"stock": st, "name": rec.get("name", ""), "rcp": rcp,
                                       "ok": False, "note": "주요 제품 절을 못 찾음", "text": ""},
                                      ensure_ascii=False, indent=1) + "\n")
        log.write("%s 제품 절 없음 (rcp %s)\n" % (st, rcp))
        return None
    html = fetch_section(found["products"])
    cells = []
    for t in parse_tables(html):
        cells.extend(t["cols"])
        for r in t["rows"]:
            cells.extend(c for c in r if c and not re.fullmatch(r"[\d,.\s%-]*", c))
    body = _text(html)
    text = (body + " " + " ".join(cells))[:LIMIT]
    os.makedirs(CACHE, exist_ok=True)
    atomic_write(path, json.dumps({"stock": st, "name": rec.get("name", ""), "rcp": rcp,
                                   "ok": bool(text.strip()), "note": "", "text": text},
                                  ensure_ascii=False, indent=1) + "\n")
    log.write("%s %s 제품 절 %d자\n" % (st, rec.get("name", "")[:12], len(text)))
    return text


def load():
    out = {}
    if not os.path.isdir(CACHE):
        return out
    for f in sorted(os.listdir(CACHE)):
        if f.endswith(".json"):
            with open(os.path.join(CACHE, f), encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("text"):
                out[d["stock"]] = d["text"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--quarter", default=None)
    a = ap.parse_args()
    rows = load_universe()
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["stock"] in want]
    q = a.quarter or latest_quarter()
    if a.collect:
        for r in rows:
            collect_one(r, q, a.force)
    got = load()
    print("제품 절 캐시 %d사 (평균 %d자)"
          % (len(got), (sum(len(t) for t in got.values()) // max(1, len(got)))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
