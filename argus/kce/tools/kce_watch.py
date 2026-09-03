#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_watch — 새 정기보고서가 나왔는지 감지해 7사를 자동 갱신한다.

각 회사의 `fq[-1]` 다음 분기 보고서가 DART에 올라왔는지 확인하고, 있으면
수집 → 빌드 → (파생 페이지 재생성)까지 수행한다. 회사마다 독립으로 처리하므로
한 회사가 실패해도 나머지는 진행한다.

fail-closed: 파싱 실패·미지 헤더·대량 소실은 `kce_build`가 예외로 막는다.
여기서는 그 예외를 회사 단위로 잡아 리포트에 남기고 **그 회사만** 건너뛴다.

사용:
    python3 kce_watch.py                 # 감지만(dry-run). 무엇이 갱신될지 보고
    python3 kce_watch.py --apply         # 실제 갱신
    python3 kce_watch.py --co sct --apply
    python3 kce_watch.py --quarter 2026Q3 --apply   # 분기 강제(정정 재적재 등)
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import traceback

from kce_lib import CORP, extract_data, q_next, report_kind
from kce_fetch import fetch_quarter, pick_report, search_reports
import kce_build

HERE = os.path.dirname(os.path.abspath(__file__))
KCE = os.path.dirname(HERE)


def next_quarter(co):
    """그 회사가 다음에 채워야 할 분기."""
    D = extract_data(os.path.join(KCE, co, "index.html"))
    return q_next(D["fq"][-1])


def _window(quarter):
    """그 분기 보고서의 접수 검색 창(분기말 월 1일 ~ +3개월, 4Q는 +4개월)."""
    y, qn = int(quarter[:4]), int(quarter[5])
    start = "%d%02d01" % (y, qn * 3)
    endm = qn * 3 + (4 if qn == 4 else 3)
    ey = y + (1 if endm > 12 else 0)
    return start, "%d%02d28" % (ey, (endm - 1) % 12 + 1)


def is_published(co, quarter):
    """그 분기 정기보고서가 DART에 올라왔는가. (있음?, rcpNo, 제목)"""
    start, end = _window(quarter)
    reports = search_reports(CORP[co]["name"], start, end, report_kind(quarter))
    ranked = pick_report(reports, quarter)
    if not ranked:
        return False, None, None
    rcp, title = ranked[0]
    return True, rcp, title


def run(companies, apply=False, quarter=None, raw_dir=None):
    out = {"checked": [], "updated": [], "skipped": [], "failed": []}
    tmp = raw_dir or tempfile.mkdtemp(prefix="kce_raw_")
    made_tmp = raw_dir is None
    try:
        for co in companies:
            q = quarter or next_quarter(co)
            try:
                found, rcp, title = is_published(co, q)
            except Exception as e:
                out["failed"].append({"co": co, "quarter": q,
                                      "stage": "search", "error": str(e)})
                continue
            out["checked"].append({"co": co, "quarter": q, "published": found,
                                   "rcpNo": rcp, "title": title})
            if not found:
                out["skipped"].append({"co": co, "quarter": q,
                                       "reason": "보고서 미공시"})
                continue
            if not apply:
                out["updated"].append({"co": co, "quarter": q, "rcpNo": rcp,
                                       "dry_run": True})
                continue
            try:
                fetch_quarter(co, q, tmp)
                rep = kce_build.update_quarter(co, q, tmp, apply=True)
                out["updated"].append({
                    "co": co, "quarter": q, "rcpNo": rcp,
                    "created": len(rep["created"]),
                    "disappeared": len(rep["disappeared"]),
                    "backfilled": len(rep.get("backfilled") or []),
                    "events": rep["events"],
                    "p8_unmatched": len(rep["p8_unmatched"]),
                })
            except Exception as e:
                out["failed"].append({"co": co, "quarter": q, "stage": "build",
                                      "error": "%s: %s" % (type(e).__name__, e),
                                      "trace": traceback.format_exc()[-800:]})
    finally:
        if made_tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--co", action="append", choices=sorted(CORP),
                    help="특정 회사만(반복 가능). 기본은 7사 전부")
    ap.add_argument("--quarter", help="분기 강제 지정(예: 2026Q3)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--raw", help="원문 저장 디렉토리(기본: 임시 디렉토리)")
    a = ap.parse_args()
    res = run(a.co or list(CORP), apply=a.apply, quarter=a.quarter, raw_dir=a.raw)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    # 실패가 있으면 비정상 종료 — Action이 빨갛게 뜬다
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
