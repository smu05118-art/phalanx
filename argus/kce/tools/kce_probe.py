#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_probe — 모집단 각 사의 정기보고서를 실제로 열어 **수록 가능 여부**를 관측한다.

업종만으로 고른 모집단에는 수주 표가 아예 없는 회사(실내건축·발전·게임 등)가 섞인다.
어느 회사를 어느 깊이로 수록할지는 **추정하지 않고 원문을 열어 재본다.**

등급(tier):
  · `site`     개별 현장 행이 파싱된다(착공일·완공예정일이 붙는다) → 현장 대시보드 가능
  · `segment`  수주표는 있으나 행이 '건축부문/토목부문'처럼 사업부문 묶음 → 집계만 가능
  · `agg`      수주 절은 있으나 인식되는 표가 없다 → 총계조차 못 뽑는다
  · `none`     정기보고서에 수주 절 자체가 없다 → 수록 대상 아님
  · `error`    접근 실패(보고서 없음·타임아웃 등) → 재시도 대상, 배제 아님

사용:
    python3 kce_probe.py --quarter 2026Q2 --out assets/probe_2026Q2.json
    python3 kce_probe.py --quarter 2026Q2 --only 009410,003070   # 일부만
"""
import argparse
import json
import re
import os
import sys
import time
import traceback

from kce_lib import atomic_write, latest_quarter, report_kind
from kce_fetch import (fetch_section, find_sections, parallel, pick_report,
                       search_reports, toc)
from kce_parse import parse_ii4, parse_p8, parse_tables
from kce_universe import load as load_universe

HERE = os.path.dirname(os.path.abspath(__file__))


# 공시 날짜 표기 방언. 4자리 연도+구분자만 보면 삼성E&A `201506`(YYYYMM)·
# 진흥기업 `24년12월`·HL D&I `25.12`를 전부 놓쳐 현장 표가 부문 표로 오분류된다.
_DATE = re.compile(r"(?:(?:19|20)\d{2}\s*[-./년]"          # 2019.12 / 2019-12-01 / 2019년
                   r"|(?:19|20)\d{4}"                       # 201506 (YYYYMM 붙임표기)
                   r"|\b\d{2}\s*[.\-년]\s*\d{1,2})")        # 25.12 / 24년12월


def grain_of(tables):
    """표가 **개별 현장** 단위인가 **사업부문 묶음**인가.

    같은 `수주상황` 표라도 회사에 따라 입도가 다르다 — SK이터닉스는 현장별
    EPC 계약을 적지만, 서한·CNT85는 '건축부문/토목부문/플랜트'처럼 부문 합계만 적는다.
    둘을 같은 등급으로 부르면 현장 대시보드가 3행짜리 막대가 된다.
    판별은 **날짜 유무**로 한다 — 부문 합계 행은 착공일·납기가 '-'로 비어 있다.

    표 단위로 보고 **가장 잘게 쪼개진 표**를 채택한다. 행을 한 덩어리로 합치면
    삼성E&A처럼 요약표(국내관급/민간/해외 3행)와 상세표(53행)를 같이 실은 회사가
    요약표에 희석돼 segment로 떨어진다.
    """
    for t in tables:
        rows = t["rows"]
        if len(rows) < 5:
            continue
        dated = sum(1 for r in rows
                    if _DATE.search((r.get("sd") or "") + " " + (r.get("ed") or "")))
        if dated >= 0.6 * len(rows):
            return "project"
    return "segment"


def report_window(quarter):
    """그 분기 정기보고서의 접수 검색 창(분기말 월 1일 ~ +3개월, 4Q는 +4개월)."""
    y, qn = int(quarter[:4]), int(quarter[5])
    start = "%d%02d01" % (y, qn * 3)
    endm = qn * 3 + (4 if qn == 4 else 3)
    ey = y + (1 if endm > 12 else 0)
    return start, "%d%02d28" % (ey, (endm - 1) % 12 + 1)


def probe_one(rec, quarter, keep_dir=None):
    """한 종목 관측. 예외를 밖으로 던지지 않고 tier='error'로 담는다."""
    out = {"slug": rec["slug"], "stock": rec["stock"], "name": rec["name"],
           "market": rec["market"], "industry": rec["industry"],
           "tier": "error", "note": "", "rcpNo": None, "title": None,
           "sections": [], "grain": None, "bal_sum": None,
           "cadence": "quarterly", "quarter": quarter,
           "ii4_rows": 0, "ii4_tables": 0,
           "unknown_headers": [], "p8_rows": 0}
    try:
        start, end = report_window(quarter)
        # 종목코드는 DART 검색에서 정확일치 키로 동작한다(동명이인 회사 혼선 없음).
        reports = search_reports(rec["stock"], start, end, report_kind(quarter))
        if not reports and int(quarter[5]) != 4:
            # 코넥스 법인은 분기·반기보고서 제출 의무가 없다 — 사업보고서만 낸다.
            # 이걸 error로 두면 실제로는 수록 가능한 회사(KC산업)가 배제된다.
            quarter = "%dQ4" % (int(quarter[:4]) - 1)
            start, end = report_window(quarter)
            reports = search_reports(rec["stock"], start, end, report_kind(quarter))
            if reports:
                out["cadence"], out["quarter"] = "annual", quarter
        if not reports:
            out["note"] = "그 분기 정기보고서 없음"
            return out
        for rcp, title in pick_report(reports, quarter)[:3]:
            nodes = toc(rcp)
            if not nodes:
                continue
            found = find_sections(nodes)
            out["rcpNo"], out["title"] = rcp, title
            out["sections"] = sorted(found)
            if not ("ii4" in found or "ii4x" in found):
                out["tier"], out["note"] = "none", "목차에 수주 절 없음"
                continue                      # 다음 후보(정정 전 원본 등)도 확인
            # ii4·ii4x **둘 다** 받아 행이 많은 쪽을 쓴다. 'XII. 상세표'는 대부분 회사에서
            # 증권발행 상세표라 수주와 무관하다 — 삼성물산만 여기에 건설수주 상세표를 둔다.
            # 한쪽만 보면 현대건설·GS건설처럼 II-4에 표가 있는 회사를 놓친다.
            best = None
            for key in ("ii4", "ii4x"):
                if key not in found:
                    continue
                html = fetch_section(found[key])
                if keep_dir:
                    os.makedirs(keep_dir, exist_ok=True)
                    with open(os.path.join(keep_dir, "%s_%s.html"
                                           % (rec["stock"], key)),
                              "w", encoding="utf-8") as f:
                        f.write(html)
                r = parse_ii4(html)
                n = sum(t["n"] for t in r["tables"])
                cand = (n, key, r, html)
                if best is None or n > best[0]:
                    best = cand
            n, key, r, html = best
            out["ii4_tables"] = len(r["tables"])
            out["ii4_rows"] = n
            out["ii4_key"] = key
            out["unknown_headers"] = [u["cols"] for u in r["unknown_headers"]][:4]
            out["sec_title"] = found[key].get("text", "")
            out["raw_tables"] = len(parse_tables(html))
            if "p8" in found:
                try:
                    p = parse_p8(fetch_section(found["p8"]))
                    out["p8_rows"] = sum(t["n"] for t in p["tables"])
                except Exception as e:
                    out["note"] = "p8 파싱 실패: %s" % e
            if out["ii4_rows"] > 0:
                allrows = [x for t in r["tables"] for x in t["rows"]]
                out["grain"] = grain_of(r["tables"])
                bals = [x["bal"] for x in allrows if x.get("bal") is not None]
                out["bal_sum"] = round(sum(bals)) if bals else None
                out["tier"] = "site" if out["grain"] == "project" else "segment"
            else:
                out["tier"] = "agg"
                out["note"] = ("수주 절은 있으나 사업장 행 0 "
                               "(표 %d개 중 인식 0)" % out["raw_tables"])
            return out
        if out["tier"] == "error":
            out["note"] = "열람 가능한 후보 보고서 없음"
        return out
    except Exception as e:
        out["tier"] = "error"
        out["note"] = "%s: %s" % (type(e).__name__, e)
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", help="기본: 오늘 기준 접수 완료된 최신 분기")
    ap.add_argument("--out", help="기본: assets/probe_<분기>.json")
    ap.add_argument("--only", help="종목코드 쉼표 구분 — 일부만 관측")
    ap.add_argument("--keep-html", help="받은 절 HTML 보관 디렉터리")
    ap.add_argument("--lanes", type=int, help="병렬 레인 수(기본 KCE_LANES 또는 6)")
    a = ap.parse_args()
    a.quarter = a.quarter or latest_quarter()
    a.out = a.out or os.path.join("assets", "probe_%s.json" % a.quarter)

    recs = load_universe()
    if not recs:
        sys.exit("universe.json 없음 — python3 kce_universe.py --write 먼저")
    if a.only:
        want = {s.strip() for s in a.only.split(",")}
        recs = [r for r in recs if r["stock"] in want]

    t0 = time.time()
    n_done = [0]

    def report(i, rec, res):
        n_done[0] += 1
        t = res["tier"] if isinstance(res, dict) else "error"
        note = (res.get("note") if isinstance(res, dict) else str(res))[:58]
        sys.stderr.write("[%2d/%d] %-6s %-18s %-8s %s\n"
                         % (n_done[0], len(recs), rec["stock"], rec["name"][:18], t, note))
        sys.stderr.flush()

    if a.lanes:
        import kce_fetch
        kce_fetch.LANES = max(1, a.lanes)
    rows = parallel(recs, lambda r: probe_one(r, a.quarter, a.keep_html),
                    on_done=report)
    # parallel은 예외를 그 자리에 담는다 — 등급 표에 빈 칸을 남기지 않는다
    rows = [r if isinstance(r, dict) else
            {"slug": rec["slug"], "stock": rec["stock"], "name": rec["name"],
             "market": rec["market"], "industry": rec["industry"], "tier": "error",
             "note": "%s: %s" % (type(r).__name__, r), "rcpNo": None, "title": None,
             "sections": [], "grain": None, "bal_sum": None, "cadence": "quarterly",
             "quarter": a.quarter, "ii4_rows": 0, "ii4_tables": 0,
             "unknown_headers": [], "p8_rows": 0}
            for rec, r in zip(recs, rows)]

    by = {}
    for r in rows:
        by[r["tier"]] = by.get(r["tier"], 0) + 1
    # **실행마다 달라지는 값을 산출물에 넣지 않는다.** 넣으면 내용이 같아도 매일
    # diff가 생겨 무의미한 커밋이 쌓인다(과거 __pycache__ 사건과 같은 유형).
    payload = {"quarter": a.quarter, "n": len(rows), "tally": by, "rows": rows}
    out = a.out if os.path.isabs(a.out) else os.path.join(HERE, a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    atomic_write(out, json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    sys.stderr.write("\n== %s: %s (%.0fs)\n" % (a.quarter, by, time.time() - t0))


if __name__ == "__main__":
    sys.exit(main())
