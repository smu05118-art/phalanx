#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_reports — 정기보고서에서 이 탭의 축을 8분기분 모은다.

수집 대상(스펙 「데이터 원천」):

| 축 | 어디서 | 몇 분기 |
|---|---|---|
| 수주총액·기납품·잔고 | II-4 다. 수주상황 | 8분기(잔고 롤포워드) |
| 제품별 매출·수출/내수 | II-4 가. 매출실적 | 8분기 |
| 매출인식 기준(원문 인용) | III 주석 「고객과의 계약에서 생기는 수익」 | **사업보고서만** |
| 주요 고객·집중도 | III 주석 「영업부문 — 주요 고객」 | **사업보고서만** |

## 왜 인식기준·고객은 사업보고서만인가

원익IPS 2026 반기보고서(20260814001845)의 「중요한 회계정책」 절은 4.2KB로 축약돼 수익
문단이 통째로 없다. 같은 회사 2025 사업보고서(20260316001453)에는 주석 3-18에 다 있다.
반기에서 못 찾은 것을 '미공시'로 적으면 거짓이 된다 — 그래서 **연 1회 절만 따로** 받는다.

## 요청량 (DART는 공인 IP 단위로 막는다)

한 회사·한 분기당 3요청(검색·목차·절)이고 캐시가 있으면 0이다. 절 HTML은
`assets/cache/sec_<rcpNo>_<key>.html` 에 원문 그대로 남긴다(COMMON §0-4 — 파서가 자라면
재수집 없이 다시 뽑는다). 조회 결과(어느 rcpNo의 어느 노드였나)는
`assets/cache/reports_index.json` 에 남겨 재검색도 피한다. **실패는 캐시하지 않는다.**

사용:
    python3 ksemi_reports.py --write                      # 편입 전 종목 8분기
    python3 ksemi_reports.py --only 240810,042700 --write
    python3 ksemi_reports.py --quarters 8 --write
    python3 ksemi_reports.py --reparse --write            # 재수집 없이 캐시만 다시 파싱
"""
import argparse
import json
import os
import re
import sys
import time
import traceback

import ksemi_parse as P
from ksemi_lib import (atomic_write, latest_quarter, q_range, report_kind,
                       write_asset)
from ksemi_fetch import fetch_section, toc
from kce_fetch import parallel, pick_report, search_reports
from kce_probe import report_window
import ksemi_universe as U

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "assets", "cache")
INDEX = os.path.join(CACHE, "reports_index.json")

# 목차에서 찾을 절. 값은 `(제목 부분문자열 묶음들, 연결본 선호, 배제 낱말)`.
#
# 묶음은 **우선순위 순서**다. 회사마다 수익 주석의 제목이 다르다 —
#   · 원익IPS 2025 사업보고서: 「3. 중요한 회계정책」 안의 3-18 문단에 들어 있다
#   · 한미반도체 2025 사업보고서: 「25. 수익인식 - 연결」 이라는 **독립 주석**이 있고,
#     「2. 중요한 회계정책 - 연결」 에는 수익 문단이 아예 없다(수행의무·통제 0건).
# 그래서 한 절만 열어 보고 '미공시'라 적으면 거짓이 된다 — 후보를 순서대로 열어
# 근거가 나올 때까지 본다. `금융수익`·`기타영업외수익` 같은 동명이인 주석은 배제한다.
SECTION_SPECS = {
    "ii4": ([("매출 및 수주상황", "매출및수주상황"), ("수주상황", "수주현황"),
             ("매출실적",)], False, ()),
    "acc": ([("수익인식", "고객과의 계약에서 생기는 수익", "수익의 인식", "수익 인식"),
             ("수익",), ("중요한 회계정책", "회계정책")], True,
            ("금융수익", "영업외수익", "이자수익", "배당금수익", "수익성", "포괄손익")),
    "seg": ([("영업부문",), ("주요 고객", "주요고객")], True, ()),
}
TRY_LIMIT = 3                 # 한 절 키에 대해 열어 볼 후보 노드 수 상한(요청량 제한)
QUARTERLY = ("ii4",)          # 분기마다 받는 절
ANNUAL = ("acc", "seg")       # 사업보고서에서만 받는 절


def _cache_path(rcp, key):
    return os.path.join(CACHE, "sec_%s_%s.html" % (rcp, key))


def _load_index():
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_index(ix):
    os.makedirs(CACHE, exist_ok=True)
    atomic_write(INDEX, json.dumps(ix, ensure_ascii=False, indent=0,
                                   sort_keys=True) + "\n")


def pick_nodes(nodes, spec, limit=TRY_LIMIT):
    """목차에서 절 후보를 **우선순위 순서로** 돌려준다.

    주석은 연결·별도가 같은 제목으로 두 번 온다. 고객 집중도의 분모(부문 합계)는
    **연결 절에만** 있는 회사가 있다(원익IPS 별도 영업부문 절엔 부문 표가 없다).
    그래서 연결본을 앞에 두고, 별도본은 뒤에 남긴다(연결이 비면 별도로 떨어진다).
    """
    groups, prefer_conn, exclude = spec
    out, seen = [], set()
    for pats in groups:
        hits = [n for n in nodes
                if any(p in (n.get("text") or "") for p in pats)
                and not any(x in (n.get("text") or "") for x in exclude)]
        if prefer_conn:
            hits.sort(key=lambda n: 0 if "연결" in (n.get("text") or "") else 1)
        for n in hits:
            k = (n.get("rcpNo"), n.get("dcmNo"), n.get("eleId"), n.get("offset"))
            if k in seen:
                continue
            seen.add(k)
            out.append(n)
            if len(out) >= limit:
                return out
    return out


def _section_html(node, key, force=False):
    """절 HTML(캐시 우선). 실패는 캐시하지 않는다."""
    path = _cache_path(node["rcpNo"], key)
    if not force and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read(), True
    h = fetch_section(node)
    if not h or len(h) < 200:
        raise RuntimeError("절 HTML이 %d바이트 — 받지 못했다" % len(h or ""))
    os.makedirs(CACHE, exist_ok=True)
    atomic_write(path, h)
    return h, False


def _shrink_orders(o):
    """reports.json 에 담을 만큼으로 줄인다(원문은 캐시에 그대로 있다)."""
    return {
        "backlog": o["backlog"], "order_amt": o["order_amt"],
        "delivered": o["delivered"], "grain": o["grain"],
        "disclosed": o["disclosed"], "unit_seen": o["unit_seen"],
        "note": o["note"][:300], "recon": o["recon"],
        "unknown_headers": o["unknown_headers"][:3],
        "items": [{"nm": r["nm"], "sd": r["sd"], "ed": r["ed"], "amt": r["amt"],
                   "cmp": r["cmp"], "bal": r["bal"]}
                  for tb in o["tables"] for r in tb["rows"] if not r["total"]][:40],
        "unit_raw": (o["tables"][0]["unit"]["raw"] if o["tables"] else None),
    }


def _shrink_sales(s):
    """대표 수출/내수 + 품목별 당기 매출만 남긴다."""
    items = []
    for tb in s["tables"]:
        if not tb["periods"]:
            continue
        p = tb["periods"][0]
        for r in tb["rows"]:
            if r["total"] or r["channel"] in ("exp", "dom"):
                continue          # 총계·수출/내수 분해 행은 품목 목록이 아니다
            v = r["vals"].get(p)
            if v is None:
                continue
            items.append({"labels": r["labels"], "amt": v,
                          "channel": r["channel"], "period": p})
    return {"export": s["export"], "domestic": s["domestic"], "total": s["total"],
            "channel_kind": s["channel_kind"], "period_label": s["period_label"],
            "unit_seen": s["unit_seen"], "recon": s["recon"], "items": items[:40]}


def collect_one(rec, quarters, force=False, reparse=False, ix=None):
    """한 종목 수집. 예외를 밖으로 던지지 않고 `errors` 에 담는다."""
    out = {"stock": rec["stock"], "name": rec["name"], "market": rec["market"],
           "industry": rec["industry"], "product": rec.get("product", ""),
           "source": rec.get("source"), "quarters": {}, "basis": None,
           "customers": None, "segment_total": None, "annual_rcp": None,
           "errors": [], "cached": 0, "fetched": 0}
    ix = ix if ix is not None else {}
    for q in quarters:
        try:
            meta = _resolve(rec["stock"], q, ix, force=force, reparse=reparse)
            if not meta:
                out["quarters"][q] = {"missing": "정기보고서 없음"}
                continue
            qd = {"rcpNo": meta["rcpNo"], "title": meta["title"]}
            cands = _cands(meta, "ii4")
            if not cands:
                qd["missing"] = "II-4 절 없음"
                out["quarters"][q] = qd
                continue
            # 첫 후보(「4. 매출 및 수주상황」)가 표준이다. 수주표를 못 찾으면 다음
            # 후보(「수주상황」 단독 절·「매출실적」)까지 열어 본다 — 절 제목을
            # 회사가 쪼개 쓰는 경우가 있다.
            best = None
            for j, node in enumerate(cands):
                html, hit = _section_html(node, "ii4" if j == 0 else "ii4%d" % j,
                                          force=force and not reparse)
                out["cached" if hit else "fetched"] += 1
                o, s = P.orders(html), P.sales(html)
                cand = {"orders": _shrink_orders(o), "sales": _shrink_sales(s),
                        "node": node.get("text", "")}
                if best is None:
                    best = cand
                if o["disclosed"]:
                    best = cand
                    break
            qd.update(best)
            out["quarters"][q] = qd
        except Exception as e:                       # noqa: BLE001 — 종목별로 담는다
            out["errors"].append({"quarter": q, "error": "%s: %s"
                                  % (type(e).__name__, e)})
    # 사업보고서 전용 절 — 가장 최근 4분기 중 4Q(사업보고서)를 쓴다
    annual = [q for q in quarters if q.endswith("Q4")]
    for q in reversed(annual):
        try:
            meta = _resolve(rec["stock"], q, ix, force=force, reparse=reparse,
                            keys=ANNUAL)
            if not meta:
                continue
            out["annual_rcp"] = meta["rcpNo"]
            for j, node in enumerate(_cands(meta, "acc")):
                h, hit = _section_html(node, "acc" if j == 0 else "acc%d" % j,
                                       force=force and not reparse)
                out["cached" if hit else "fetched"] += 1
                b = P.revenue_basis(h)
                out["basis"] = {"primary": b["primary"], "found": b["found"],
                                "scoped": b["scoped"], "bases": b["bases"][:3],
                                "rcpNo": meta["rcpNo"], "quarter": q,
                                "node": node.get("text", "")}
                if b["found"]:
                    break
            for j, node in enumerate(_cands(meta, "seg")):
                h, hit = _section_html(node, "seg" if j == 0 else "seg%d" % j,
                                       force=force and not reparse)
                out["cached" if hit else "fetched"] += 1
                c = P.customers(h)
                st = P.segment_revenue(h)
                out["customers"] = {"rows": c["rows"], "period": c["period"],
                                    "anonymous": c["anonymous"], "found": c["found"],
                                    "skipped_prior": c["skipped_prior"],
                                    "rcpNo": meta["rcpNo"], "quarter": q,
                                    "node": node.get("text", "")}
                if st["total"] is not None and not (out["segment_total"] or {}).get("total"):
                    out["segment_total"] = st
                if c["found"]:
                    break
            if out["basis"] or out["customers"]:
                break
        except Exception as e:                       # noqa: BLE001
            out["errors"].append({"quarter": q + "(annual)",
                                  "error": "%s: %s" % (type(e).__name__, e)})
    out["kpi"] = kpi(out)
    return out


def _resolve(stock, q, ix, force=False, reparse=False, keys=QUARTERLY):
    """(종목,분기) → `{rcpNo,title,nodes:{key:node}}`. 검색·목차도 캐시한다."""
    ck = "%s|%s" % (stock, q)
    cur = ix.get(ck)
    if cur is not None and not force:
        if cur.get("none"):
            return None
        if all(k in cur["nodes"] or k in cur.get("absent", []) for k in keys):
            return {"rcpNo": cur["rcpNo"], "title": cur["title"],
                    "nodes": cur["nodes"]}
    if reparse:
        # 재파싱 모드에서는 새 요청을 내지 않는다(캐시에 없으면 건너뛴다).
        if cur and not cur.get("none"):
            return {"rcpNo": cur["rcpNo"], "title": cur["title"],
                    "nodes": cur["nodes"]}
        return None
    start, end = report_window(q)
    reps = pick_report(search_reports(stock, start, end, report_kind(q)), q)
    if not reps:
        ix[ck] = {"none": True}
        return None
    rcp, title = reps[0]
    nodes = toc(rcp)
    picked, absent = {}, []
    for key, spec in SECTION_SPECS.items():
        cands = pick_nodes(nodes, spec)
        if cands:
            picked[key] = cands
        else:
            absent.append(key)
    ix[ck] = {"rcpNo": rcp, "title": title, "nodes": picked, "absent": absent}
    return {"rcpNo": rcp, "title": title, "nodes": picked}


def _cands(meta, key):
    """조회 캐시의 노드 값 → 후보 목록. 옛 캐시는 노드 하나(dict)로 저장돼 있다."""
    v = (meta.get("nodes") or {}).get(key)
    if not v:
        return []
    return v if isinstance(v, list) else [v]


# ── KPI ────────────────────────────────────────────────────

def kpi(rec):
    """화면이 바로 쓰는 파생값. 원문이 없으면 None(추정하지 않는다).

    `bal_rev_x`(잔고/매출 배수)는 **연 매출 기준**으로 맞춘다 — 반기보고서의 매출실적
    첫 열은 반기 누계라 그대로 나누면 배수가 두 배로 뜬다. 연 매출은 가장 최근
    사업보고서(4Q) 분기의 합계를 쓰고, 없으면 배수를 계산하지 않는다.
    """
    qs = sorted(rec["quarters"])
    latest_bal = latest_q = None
    for q in reversed(qs):
        d = rec["quarters"][q]
        o = (d or {}).get("orders") or {}
        if o.get("backlog") is not None:
            latest_bal, latest_q = o["backlog"], q
            break
    annual_rev = None
    for q in reversed([x for x in qs if x.endswith("Q4")]):
        s = (rec["quarters"][q] or {}).get("sales") or {}
        if s.get("total"):
            annual_rev = s["total"]
            break
    exp_share = None
    for q in reversed(qs):
        s = (rec["quarters"][q] or {}).get("sales") or {}
        if s.get("export") is not None and s.get("total"):
            exp_share = round(100.0 * s["export"] / s["total"], 1)
            break
    top_share = top_label = None
    cu = rec.get("customers") or {}
    den = (rec.get("segment_total") or {}).get("total") or annual_rev
    if cu.get("rows") and den:
        top = max(cu["rows"], key=lambda r: r["amount"])
        top_share = round(100.0 * top["amount"] / den, 1)
        top_label = top["label"]
    return {
        "backlog": latest_bal, "backlog_quarter": latest_q,
        "annual_revenue": annual_rev,
        "bal_rev_x": (round(latest_bal / annual_rev, 2)
                      if latest_bal is not None and annual_rev else None),
        "export_share": exp_share,
        "top_customer": top_label, "top_customer_share": top_share,
        "basis": (rec.get("basis") or {}).get("primary"),
        "disclosed": any(((rec["quarters"][q] or {}).get("orders") or {})
                         .get("disclosed") for q in qs),
    }


# ── 실행 ───────────────────────────────────────────────────

def targets(only=None):
    """수집 대상. `scan.json` 이 있으면 지정 ∪ 편입, 없으면 지정만."""
    rows = U.load()
    if not rows:
        raise RuntimeError("assets/universe.json 이 없다 — ksemi_universe.py --write 먼저")
    by = {r["stock"]: r for r in rows}
    if only:
        return [by[s] for s in only if s in by]
    keep = {r["stock"] for r in rows if r.get("source") == "지정"}
    scan_path = os.path.join(HERE, "assets", "scan.json")
    if os.path.exists(scan_path):
        with open(scan_path, encoding="utf-8") as f:
            for r in json.load(f).get("rows", []):
                if r.get("verdict") == "편입":
                    keep.add(r["stock"])
    return [r for r in rows if r["stock"] in keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--only", help="종목코드 쉼표 구분")
    ap.add_argument("--quarters", type=int, default=8)
    ap.add_argument("--quarter", help="기준 분기(기본 최신)")
    ap.add_argument("--force", action="store_true", help="캐시 무시 재수집(범위를 좁혀라)")
    ap.add_argument("--reparse", action="store_true", help="요청 없이 캐시만 다시 파싱")
    a = ap.parse_args()

    q1 = a.quarter or latest_quarter()
    y, qn = int(q1[:4]), int(q1[5])
    back = a.quarters - 1
    y0, q0n = y - (back + (4 - qn)) // 4, ((qn - 1 - back) % 4) + 1
    quarters = q_range("%dQ%d" % (y0, q0n), q1)
    only = [s.strip() for s in a.only.split(",")] if a.only else None
    recs = targets(only)
    print("대상 %d종목 · %s~%s" % (len(recs), quarters[0], quarters[-1]),
          file=sys.stderr)

    ix = _load_index()
    rows, t0 = [], time.time()

    def one(r):
        try:
            return collect_one(r, quarters, force=a.force, reparse=a.reparse, ix=ix)
        except Exception:                            # noqa: BLE001
            traceback.print_exc()
            return {"stock": r["stock"], "name": r["name"],
                    "errors": [{"quarter": "*", "error": "collect 실패"}],
                    "quarters": {}, "kpi": {}}

    def done(i, item, r):
        if isinstance(r, Exception):
            print("  [%d] %s 예외 %s" % (i, item["stock"], r), file=sys.stderr)
            return
        print("  [%d/%d] %s %s 잔고=%s 오류=%d (%.0fs)"
              % (i + 1, len(recs), r["stock"], r["name"][:14],
                 (r.get("kpi") or {}).get("backlog"), len(r.get("errors") or []),
                 time.time() - t0), file=sys.stderr)

    # `ix`(조회 캐시)는 레인들이 같이 쓴다 — dict 항목 대입은 CPython에서 원자적이고
    # 키가 (종목,분기)로 겹치지 않으므로 락을 두지 않는다.
    rows = [r for r in parallel(recs, one, on_done=done)
            if not isinstance(r, Exception)]
    _save_index(ix)
    rows.sort(key=lambda r: -((r.get("kpi") or {}).get("backlog") or 0))
    data = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "quarters": quarters, "n": len(rows), "rows": rows}
    if a.write:
        write_asset("reports.json", data)
        print("→ assets/reports.json (%d종목)" % len(rows), file=sys.stderr)
    else:
        for r in rows:
            k = r.get("kpi") or {}
            print("%-7s %-16s 잔고 %-12s 배수 %-6s 수출 %-6s 최대고객 %-6s 인식 %s"
                  % (r["stock"], r["name"][:16], k.get("backlog"), k.get("bal_rev_x"),
                     k.get("export_share"), k.get("top_customer_share"),
                     k.get("basis")))
    n_bal = sum(1 for r in rows if (r.get("kpi") or {}).get("backlog") is not None)
    n_err = sum(len(r.get("errors") or []) for r in rows)
    print("— 잔고 수록 %d/%d · 오류 %d" % (n_bal, len(rows), n_err), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
