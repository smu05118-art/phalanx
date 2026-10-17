#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_run — 일일 수집 순서(워크플로가 부른다). 네트워크 단계만 모았다; 원장·모델·페이지는 각 모듈을 따로 부른다.

  --daily     KIND 모집단 → 후보 전수의 최신 분기 생산설비 절(캐시 있으면 요청 0) → 편입 회사의 이벤트 공시·재무제표(최신 2분기)
  --history   편입 회사의 과거 5개 분기 생산설비 절·재무제표 8분기도 수집(첫 실행·캐시 만료 때)
DART 는 kce_fetch 의 프로세스 간 게이트를 따르므로 이 스크립트 안에서도 전부 순차다. 한 회사 실패는 기록만 하고 계속한다.
"""
import argparse
import sys

from kcap_lib import latest_quarter, load_asset
import kcap_universe
import kcap_capacity
import kcap_events
import kcap_fin


def q_back(q, n):
    y, k = int(q[:4]), int(q[5])
    for _ in range(n):
        y, k = (y - 1, 4) if k == 1 else (y, k - 1)
    return "%dQ%d" % (y, k)


def promoted_stocks():
    """직전 모델에서 편입된 회사 + 톤 제품이 있는 회사(원장) — 첫 실행이면 후보 전부."""
    try:
        model = load_asset("model.json")
        prom = [st for st, c in model["companies"].items() if c.get("promoted")]
    except FileNotFoundError:
        prom = []
    try:
        led = load_asset("ledger.json")
        ton = [st for st, c in led["companies"].items() if c.get("n_ton_products")]
    except FileNotFoundError:
        ton = []
    out = sorted(set(prom) | set(ton))
    if not out:
        out = [r["stock"] for r in load_asset("universe.json")["rows"] if not r.get("excluded")]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--quarter", default="")
    a = ap.parse_args(argv)
    log = sys.stdout
    q = a.quarter or latest_quarter()
    log.write("[kcap_run] 기준 분기 %s\n" % q)
    uni = kcap_universe.fetch(write=True)
    log.write("[kcap_run] KIND %d → 후보 %d\n" % (uni["n_kind"], uni["n_candidates"]))
    names = {r["stock"]: r["name"] for r in uni["rows"]}
    cands = [r["stock"] for r in uni["rows"] if not r.get("excluded")]
    fails = []
    for st in cands:
        try:
            res = kcap_capacity.collect(st, names.get(st, st), q)
            if not res.get("ok"):
                fails.append((st, q, res.get("note")))
        except Exception as e:
            fails.append((st, q, "%s: %s" % (type(e).__name__, str(e)[:100])))
    log.write("[kcap_run] 생산설비 절 %s: %d사 중 실패 %d\n" % (q, len(cands), len(fails)))
    prom = promoted_stocks()
    if a.history:
        for st in prom:
            for qq in [q_back(q, i) for i in range(1, 6)]:
                try:
                    kcap_capacity.collect(st, names.get(st, st), qq)
                except Exception as e:
                    fails.append((st, qq, "%s: %s" % (type(e).__name__, str(e)[:100])))
        log.write("[kcap_run] 이력 5분기 수집 %d사\n" % len(prom))
    for st in prom:
        try:
            r = kcap_events.collect(st, names.get(st, st), since="20240101")
            if not r.get("ok"):
                fails.append((st, "events", "; ".join(str(x) for x in r.get("errors", []))[:100]))
        except Exception as e:
            fails.append((st, "events", "%s: %s" % (type(e).__name__, str(e)[:100])))
    fin_qs = [q_back(q, i) for i in range(7, -1, -1)] if a.history else [q_back(q, 1), q]
    for st in prom:
        try:
            kcap_fin.collect(st, names.get(st, st), fin_qs)
            kcap_fin.build(st, names.get(st, st))
        except Exception as e:
            fails.append((st, "fin", "%s: %s" % (type(e).__name__, str(e)[:100])))
    log.write("[kcap_run] 이벤트·재무 %d사 (재무 분기 %s)\n" % (len(prom), ",".join(fin_qs)))
    for f in fails:
        log.write("  ✗ %s %s %s\n" % f)
    log.write("[kcap_run] 끝 — 실패 %d\n" % len(fails))
    return 1 if len(fails) > max(3, len(cands) // 5) else 0     # 소수 실패는 캐시·다음 실행으로 흡수, 광범위 실패만 신호


if __name__ == "__main__":
    sys.exit(main())
