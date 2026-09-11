#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scout_score — 관측(probe·contracts)을 산업별로 집계해 **수주기반 점수**를 낸다.

점수 공식(재현 가능해야 한다 — scout.md §3). 네 축, 100점 만점:

    점수 = 40·A + 30·min(B/2.0, 1) + 20·min(C/4.0, 1) + 10·D

  A 수주 공시율   = 수주표가 있는 회사 / **읽힌** 회사            (0~1)
      └ 못 읽은 회사(error)는 분모에서 뺀다. 추정으로 채우지 않는다.
  B 잔고/매출 배수 중앙값 (년)                                  2년이면 만점
      └ 잔고·매출 **둘 다 원문에서 파싱된** 회사만. 단위 캡션을 못 읽은 표는 뺀다.
  C 계약공시 빈도 중앙값 (건/년, 최근 2년 「단일판매ㆍ공급계약체결」)  연 4건이면 만점
  D 계약 단위 공시 비율 = 행이 개별 계약인 회사 / 수주표가 있는 회사  (0~1)

왜 이 가중치인가:
  · A가 가장 무겁다(40). 산업이 수주를 **공시하지 않으면** 탭이 설 자리가 없다 — 화면에 실을 것이 없다.
  · B(30)는 '몇 년치 일감인가' — 조선·건설이 2~3년이라 2년을 만점으로 뒀다.
  · C(20)는 계약 단위 원장(kship_contracts 형)을 만들 수 있는가.
  · D(10)는 원문 입도. 부문 합계뿐이면 회사 페이지가 3행짜리 막대가 된다(kce에서 실제로 겪었다).
보정 섹터(조선·건설)가 상단에 오지 않으면 **눈금이 틀린 것**이므로 그대로 보고한다.

    python3 scout_score.py            # 산업별 표
    python3 scout_score.py --write    # ../scout_evidence.json
"""
import argparse
import json
import os
import re
import sys

from scout_lib import ASSETS, SPECS, atomic_write, load_asset

PCACHE = os.path.join(ASSETS, "probe_cache")
CCACHE = os.path.join(ASSETS, "contracts_cache")

W_A, W_B, W_C, W_D = 40.0, 30.0, 20.0, 10.0
B_FULL, C_FULL = 2.0, 4.0            # 만점 기준: 잔고 2년치 · 계약공시 연 4건
FORMULA = ("점수 = %g·A(수주공시율) + %g·min(B(잔고/매출 중앙값)/%g,1) "
           "+ %g·min(C(계약공시 건/년 중앙값)/%g,1) + %g·D(계약단위 공시 비율)"
           % (W_A, W_B, B_FULL, W_C, C_FULL, W_D))


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2.0, 3)


def load_probe(stock, quarter="2025Q4"):
    for q in (quarter, "%dQ4" % (int(quarter[:4]) - 1)):
        p = os.path.join(PCACHE, "%s_%s.json" % (stock, q))
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return None


def load_contract(stock):
    if not os.path.isdir(CCACHE):
        return None
    for fn in sorted(os.listdir(CCACHE)):
        if fn.startswith(stock + "_"):
            with open(os.path.join(CCACHE, fn), encoding="utf-8") as f:
                return json.load(f)
    return None


def rows_for(sample, quarter):
    """표본 행 + 관측 결과를 합친 회사별 근거 행."""
    out = []
    for r in sample["rows"]:
        d = load_probe(r["stock"], quarter) or {}
        c = load_contract(r["stock"]) or {}
        # 잔고/매출 배수는 **단위를 읽은 표**에서만 믿는다(COMMON.md §2)
        mult = d.get("mult")
        unit_ok = all(o.get("unit_seen", True) for o in (d.get("orders") or []))
        out.append({
            "sector": r["sector"], "sector_label": r["sector_label"],
            "stock": r["stock"], "name": r["name"], "market": r["market"],
            "industry": r["industry"], "product": r["product"],
            "anchor": r["anchor"], "pick_reason": r["pick_reason"],
            "rcpNo": d.get("rcpNo"), "report": d.get("title"),
            "quarter": d.get("quarter"), "sec_title": d.get("sec_title"),
            "tier": d.get("tier", "미관측"), "note": d.get("note", ""),
            "bal_mw": d.get("bal"), "rev_mw": d.get("rev"),
            "mult": mult if unit_ok else None,
            "unit_seen": unit_ok,
            "bal_src": d.get("bal_src"), "grain": d.get("grain"),
            "n_rows": d.get("n_rows"), "has_client": d.get("has_client"),
            "has_date": d.get("has_date"), "anon_rows": d.get("anon_rows"),
            "top_share": d.get("top_share"),
            "clist_rows": d.get("clist_rows"), "clist_hidden": d.get("clist_hidden"),
            "contracts_2y": c.get("n_new"), "contracts_fix": c.get("n_fix"),
            "contracts_capped": c.get("capped"), "per_year": c.get("per_year"),
            "flags": d.get("flags") or {},
        })
    return out


def score(rows, sectors):
    out = []
    for s in sectors:
        rs = [r for r in rows if r["sector"] == s["id"]]
        readable = [r for r in rs if r["tier"] in ("proj", "seg", "no_table", "none_sec")]
        has = [r for r in readable if r["tier"] in ("proj", "seg")]
        A = (len(has) / len(readable)) if readable else None
        B = median([r["mult"] for r in has])
        C = median([r["per_year"] for r in rs if r["per_year"] is not None])
        D = (sum(1 for r in has if r["grain"] == "project") / len(has)) if has else None
        sc = None
        if A is not None:
            sc = (W_A * A
                  + (W_B * min((B or 0) / B_FULL, 1.0))
                  + (W_C * min((C or 0) / C_FULL, 1.0))
                  + (W_D * (D or 0)))
        # 산업 특성 축 후보 — 본문 낱말이 표본의 몇 %에서 보이는가
        flagpct = {}
        if readable:
            keys = set(k for r in readable for k in (r["flags"] or {}))
            for k in keys:
                flagpct[k] = round(100.0 * sum(1 for r in readable
                                               if (r["flags"] or {}).get(k)) / len(readable))
        out.append({
            "id": s["id"], "label": s["label"], "why": s["why"],
            "n_cand": s["n_cand"], "n_sample": len(rs),
            "n_readable": len(readable), "n_error": len(rs) - len(readable),
            "n_order": len(has), "n_proj": sum(1 for r in has if r["grain"] == "project"),
            "A_disclose": round(A, 3) if A is not None else None,
            "B_mult_med": B, "C_freq_med": C,
            "D_proj_ratio": round(D, 3) if D is not None else None,
            "score": round(sc, 1) if sc is not None else None,
            "flag_pct": flagpct,
            "top": sorted([{"stock": r["stock"], "name": r["name"], "mult": r["mult"],
                            "tier": r["tier"], "grain": r["grain"], "n_rows": r["n_rows"],
                            "per_year": r["per_year"]} for r in rs],
                          key=lambda x: -(x["mult"] or 0))[:4],
        })
    out.sort(key=lambda x: -(x["score"] or -1))
    return out


def md_table(secs, rows):
    """scout_report.md 의 섹터 표를 **그대로** 찍는다 — 손으로 옮겨 적다 틀리지 않게."""
    out = ["| 산업 | 후보 | 표본 | 읽힘 | 수주표 | A 공시율 | B 배수(년) | C 계약(건/년) | D 계약입도 | 점수 | 대표 종목(배수) |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for s in secs:
        top = ", ".join("%s(%s)" % (t["name"], "%.1f" % t["mult"] if t["mult"] else "—")
                        for t in s["top"][:3])
        out.append("| %s | %d | %d | %d | %d | %s | %s | %s | %s | **%s** | %s |" % (
            s["label"], s["n_cand"], s["n_sample"], s["n_readable"], s["n_order"],
            "%.0f%%" % (100 * s["A_disclose"]) if s["A_disclose"] is not None else "—",
            s["B_mult_med"] if s["B_mult_med"] is not None else "—",
            s["C_freq_med"] if s["C_freq_med"] is not None else "—",
            "%.0f%%" % (100 * s["D_proj_ratio"]) if s["D_proj_ratio"] is not None else "—",
            s["score"] if s["score"] is not None else "—", top))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", default="2025Q4")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--md", action="store_true", help="보고서용 마크다운 표만 찍는다")
    a = ap.parse_args()
    sample = load_asset("sample.json")
    rows = rows_for(sample, a.quarter)
    secs = score(rows, sample["sectors"])
    if a.md:
        print(md_table(secs, rows))
        return 0
    print(FORMULA + "\n")
    print("%-10s %-22s %5s %5s %5s %6s %6s %6s %6s" % (
        "id", "label", "표본", "읽힘", "수주", "A", "B(년)", "C(건/년)", "점수"))
    for s in secs:
        print("%-10s %-22s %5d %5d %5d %6s %6s %6s %6s" % (
            s["id"], s["label"], s["n_sample"], s["n_readable"], s["n_order"],
            s["A_disclose"], s["B_mult_med"], s["C_freq_med"], s["score"]))
    n_err = sum(s["n_error"] for s in secs)
    print("\n미확인(접근 실패·미관측) %d사 — 분모에서 제외" % n_err)
    if a.write:
        payload = {
            "generated_for": "argus/_specs/scout_report.md",
            "quarter": a.quarter,
            "formula": FORMULA,
            "formula_notes": {
                "A": "수주표가 있는 회사 / 읽힌 회사. 못 읽은 회사는 분모에서 제외",
                "B": "잔고/매출 배수의 중앙값(년). 잔고·매출 둘 다 원문 파싱 성공 + 단위 캡션 확인된 회사만",
                "C": "최근 2년 「단일판매ㆍ공급계약체결」 신규 건수 ÷ 2 의 중앙값",
                "D": "수주표 행이 개별 계약 단위인 회사 / 수주표가 있는 회사",
                "tier": {"proj": "계약(프로젝트) 단위 수주표", "seg": "부문 합계 수주표",
                         "no_table": "수주 절은 있으나 수주표 없음", "none_sec": "목차에 매출·수주 절 없음",
                         "error": "접근 실패 — 배제가 아니라 미확인"},
            },
            "sectors": secs, "companies": rows,
        }
        atomic_write(os.path.join(SPECS, "scout_evidence.json"),
                     json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
        print("→ argus/_specs/scout_evidence.json", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
