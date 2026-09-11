#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scout_peek — 원문을 **사람 눈으로** 확인하는 도구. 가설을 코드로 굳히기 전에 쓴다.

    python3 scout_peek.py 034020 --quarter 2025Q4            # 목차만
    python3 scout_peek.py 034020 --quarter 2025Q4 --sec 수주  # 그 절의 표를 덤프
    python3 scout_peek.py 034020 --contracts                  # 단일판매·공급계약 공시 목록
"""
import argparse
import re
import sys

from scout_lib import (fetch_section, parse_tables, pick_report, report_kind,
                       report_window, search_reports, toc, unit_scale)

CACHE = {}


def reports_for(stock, quarter):
    start, end = report_window(quarter)
    return pick_report(search_reports(stock, start, end, report_kind(quarter)), quarter)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stock")
    ap.add_argument("--quarter", default="2025Q4")
    ap.add_argument("--sec", help="목차 제목 부분 문자열")
    ap.add_argument("--contracts", action="store_true")
    ap.add_argument("--rows", type=int, default=14)
    a = ap.parse_args()

    if a.contracts:
        y = int(a.quarter[:4])
        for rcp, title in search_reports(a.stock, "%d0101" % (y - 1), "%d1231" % (y + 1), "I001"):
            print(rcp, title)
        return

    reps = reports_for(a.stock, a.quarter)
    if not reps:
        sys.exit("정기보고서 없음")
    rcp, title = reps[0]
    print("== %s %s" % (rcp, title))
    nodes = toc(rcp)
    for n in nodes:
        print("   ", n.get("text"))
    if not a.sec:
        return
    hit = [n for n in nodes if a.sec in (n.get("text") or "")]
    if not hit:
        sys.exit("그 절 없음")
    for n in hit:
        html = fetch_section(n)
        print("\n#### 절: %s (%d bytes)" % (n["text"], len(html)))
        for i, t in enumerate(parse_tables(html)):
            print("\n-- 표%d lead=%r unit_scale=%s" % (i, (t.get("lead") or "")[-140:],
                                                      unit_scale(t.get("lead"), t.get("cols"))))
            print("   cols:", t["cols"])
            for r in t["rows"][:a.rows]:
                print("   ", [c[:22] for c in r])
            if len(t["rows"]) > a.rows:
                print("    ... %d행 더" % (len(t["rows"]) - a.rows))


if __name__ == "__main__":
    sys.exit(main())
