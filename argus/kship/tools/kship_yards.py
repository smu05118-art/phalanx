#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_yards — 조선사 정기보고서에서 분기 지표 4종을 읽는다(2026 반기 3사 실측 구조).

  ① 수주 롤포워드   II. 4. 매출 및 수주상황 → 수주상황 표. 사업부문별(조선/해양/기타 …)
                   기초수주잔액 + 신규증감 − 기납품액 = 기말수주잔고 (HD현대중공업형) 또는
                   수주총액/기납품액/수주잔고 (표준형: 삼성중공업 억원, 한화오션 백만원).
                   **선종·척수는 여기 없다** — 척당 계약 공시(kship_contracts)가 그 축을 맡는다.
  ② 매출실적       같은 절, 사업부문 × 수출/내수/합계.
  ③ 환노출         II. 5. 위험관리 및 파생거래 → '환위험' 통화별 표(USD·EUR·CNY·JPY·기타).
                   계약자산·매출채권·현금 등 자산계와 부채계. 헤지 전 노출이다.
  ④ 헤지 명목액     III. 주석 'N. 파생금융상품 (연결)' → 미결제약정 내역. 통화선도 매도 USD(천),
                   평균만기, 계약건수. 주석 번호는 회사마다 다르므로 제목으로 찾는다.

모두 원문 표를 raw 로 함께 보존한다(판정이 아니라 원문이 원장이다). 단위는 표마다 읽어
백만원으로 정규화하고, 달러 표기는 USD 백만으로 둔다(환산은 화면이 분기말 환율로).
fail-closed: 수주표를 못 찾으면 그 분기를 쓰지 않는다.

    python3 kship_yards.py --collect --quarter 2026Q2 [--only 329180]
    python3 kship_yards.py --build
"""
import argparse
import json
import os
import re
import sys

from kship_lib import (ASSETS, atomic_write, fetch_section, find_sections, latest_quarter,
                       load_asset, num_of, parse_tables, pick_report, report_kind,
                       search_reports, toc, write_asset)
from kship_parse import unit_of, is_total
from kship_universe import load as load_universe
from kce_probe import report_window                      # noqa: E402

CACHE = os.path.join(ASSETS, "yards_cache")

SECTIONS = [
    ("orders", ["매출 및 수주상황", "수주상황"]),
    ("risk", ["위험관리 및 파생거래", "위험관리"]),
]


def _clean(s):
    return re.sub(r"[\s　]+", "", s or "")


def _scaled(v, mul):
    x = num_of(v)
    if x is None:
        return None
    x = x * mul
    return int(x) if float(x).is_integer() else round(x, 3)


def parse_orders_table(t):
    """수주표 한 장 → {unit, cur, rows:[{seg, opening, new, delivered, closing}]}."""
    cols = [_clean(c) for c in t["cols"]]
    cur, mul, seen = unit_of(t.get("lead"), t.get("cols"))

    def col(*keys):
        for i, c in enumerate(cols):
            if all(k in c for k in keys):
                return i
        return None
    i_open = col("기초", "금액") if col("기초", "금액") is not None else col("기초")
    i_new = col("신규", "금액") if col("신규", "금액") is not None else col("신규")
    i_done = col("기납품", "금액") if col("기납품", "금액") is not None else col("기납품")
    i_close = col("기말", "금액") if col("기말", "금액") is not None else (col("수주잔고", "금액") if col("수주잔고", "금액") is not None else col("수주잔고"))
    i_total = col("수주총액", "금액") if col("수주총액", "금액") is not None else col("수주총액")
    if i_close is None or (i_open is None and i_total is None):
        return None
    rows = []
    for r in t["rows"]:
        seg = (r[0] if r else "").strip()
        if not seg:
            continue
        rec = {"seg": _clean(seg) if is_total(seg) else seg,
               "total": is_total(seg),
               "opening": _scaled(r[i_open], mul) if i_open is not None and i_open < len(r) else None,
               "gross": _scaled(r[i_total], mul) if i_total is not None and i_total < len(r) else None,
               "new": _scaled(r[i_new], mul) if i_new is not None and i_new < len(r) else None,
               "delivered": _scaled(r[i_done], mul) if i_done is not None and i_done < len(r) else None,
               "closing": _scaled(r[i_close], mul) if i_close < len(r) else None}
        if rec["closing"] is None and rec["gross"] is None and rec["opening"] is None:
            continue
        # 한화오션·HD현대중공업은 기납품액을 (음수)로 적는다 — 부호를 정규화한다
        if rec["delivered"] is not None and rec["delivered"] < 0:
            rec["delivered"] = -rec["delivered"]
        rows.append(rec)
    return {"cur": cur, "unit_seen": seen, "rows": rows, "cols": t["cols"], "lead": (t.get("lead") or "")[-120:]}


def parse_revenue_table(t):
    cols = [_clean(c) for c in t["cols"]]
    if not ("사업부문" in cols and any("매출유형" in c for c in cols)):
        return None
    cur, mul, _ = unit_of(t.get("lead"), t.get("cols"))
    rows = []
    for r in t["rows"]:
        if len(r) < 5:
            continue
        seg, kind = r[0].strip(), (r[3] if len(r) > 3 else "").strip()
        kind = _clean(kind)
        if kind not in ("수출", "국내", "내수", "합계", "기타"):
            continue
        vals = [_scaled(v, mul) for v in r[4:]]
        rows.append({"seg": seg or None, "kind": "국내" if kind in ("국내", "내수") else kind, "vals": vals})
    return {"cur": cur, "period_cols": t["cols"][4:], "rows": rows} if rows else None


def parse_fx_table(t):
    cols = [_clean(c) for c in t["cols"]]
    if not any("USD" in c for c in cols):
        return None
    cur, mul, _ = unit_of(t.get("lead"), t.get("cols"))
    out = {"cur": cur, "cols": t["cols"], "rows": []}
    for r in t["rows"]:
        lab = _clean(r[0]) if r else ""
        if not lab:
            continue
        out["rows"].append({"label": r[0].strip(), "vals": [_scaled(v, mul) for v in r[1:]]})
    keys = {_clean(x["label"]): x for x in out["rows"]}
    for k, v in keys.items():
        if "계약자산" in k:
            out["contract_asset"] = v["vals"]
        if k in ("자산계", "자산합계"):
            out["assets"] = v["vals"]
        if k in ("부채계", "부채합계"):
            out["liabilities"] = v["vals"]
    return out if out["rows"] else None


def parse_hedge_tables(html):
    """주석 '파생금융상품' → 통화선도 명목액(매도/매입, USD 천 단위 등), 평균만기, 건수."""
    out = {"forwards": [], "raw": []}
    for t in parse_tables(html):
        head = " ".join(t["cols"])
        if "미결제약정" not in (t.get("lead") or "") and "미결제" not in head:
            continue
        out["raw"].append({"lead": (t.get("lead") or "")[-100:], "cols": t["cols"], "rows": t["rows"][:20]})
        for r in t["rows"]:
            lab = r[0] if r else ""
            m = re.search(r"(매도|매입)금액.*?([A-Z]{3})\s*\[[A-Z]{3},\s*(천|백만)\]", lab)
            if not m:
                continue
            side, ccy, unit = m.group(1), m.group(2), m.group(3)
            mul = 0.001 if unit == "천" else 1.0            # → 백만 통화단위
            for i, v in enumerate(r[1:]):
                x = num_of(v)
                if x is None:
                    continue
                kind = t["cols"][i + 1] if i + 1 < len(t["cols"]) else ""
                out["forwards"].append({"side": side, "ccy": ccy, "amt_m": round(x * mul, 3),
                                        "hedge": ("현금흐름" if "현금흐름" in kind else "공정가치" if "공정가치" in kind else ""),
                                        "instr": ("스왑" if "스왑" in kind else "선도")})
        for r in t["rows"]:
            lab = r[0] if r else ""
            if "평균만기" in lab:
                out["avg_maturity"] = [v for v in r[1:] if v]
            if "계약건수" in lab:
                out["contracts"] = [num_of(v) for v in r[1:]]
    return out


_CCY = re.compile(r"\b(USD|EUR|CNY|JPY|GBP|KRW|SGD|NOK|DKK|CHF)\b")


def parse_hedge_any(html, where):
    """세 회사 세 모양의 통화선도 표를 하나의 결과로 — {'usd_sell_m','avg_rate','items','shape'}.

      · HD현대중공업(주석): 행 라벨 '매도금액, 파생상품, USD [USD, 천]' → 천 단위
      · 삼성중공업(위험관리 절): [매도통화, 매도금액, 매입통화, 매입금액, …] 행, 단위 '외화:천'
      · 한화오션(위험관리 절): ['USD 매도', 평균약정환율, 'USD', 금액(백만USD), 'KRW', 금액(백만원), …]
    금액은 전부 **백만 통화단위**로 맞춘다. 못 읽으면 items 가 비고 shape 가 None — 추정하지 않는다.
    """
    out = {"items": [], "shape": None, "where": where}
    for t in parse_tables(html):
        head = " ".join(t["cols"]); lead = (t.get("lead") or "")[-160:]
        unit_txt = (head + " " + lead)
        k = 1e-3 if re.search(r"외화\s*:\s*천|\[USD,\s*천\]|\(단위\s*:\s*천", unit_txt) else 1.0
        if "백만USD" in unit_txt or "백만 USD" in unit_txt:
            k = 1.0
        for r in t["rows"]:
            if not r:
                continue
            lab = r[0]
            # (1) HHI 주석형
            m = re.search(r"(매도|매입)금액.*?([A-Z]{3})\s*\[[A-Z]{3},\s*(천|백만)\]", lab)
            if m:
                mul = 1e-3 if m.group(3) == "천" else 1.0
                for i, v in enumerate(r[1:]):
                    x = num_of(v)
                    if x is None:
                        continue
                    col = t["cols"][i + 1] if i + 1 < len(t["cols"]) else ""
                    out["items"].append({"side": m.group(1), "ccy": m.group(2), "amt_m": round(x * mul, 3),
                                         "hedge": "현금흐름" if "현금흐름" in col else ("공정가치" if "공정가치" in col else ""),
                                         "instr": "스왑" if "스왑" in col else "선도"})
                out["shape"] = out["shape"] or "note-label"
                continue
            # (3) 한화오션형: 'USD 매도' … 'USD', 금액, 'KRW', 금액
            if re.match(r"\s*(USD|EUR|JPY|CNY)\s*(매도|매입)", lab):
                ccy, side = re.match(r"\s*([A-Z]{3})\s*(매도|매입)", lab).groups()
                amt = None; rate = None
                for i, c in enumerate(r[1:], 1):
                    if c.strip() == ccy and i + 1 < len(r):
                        amt = num_of(r[i + 1]); break
                if len(r) > 1:
                    rate = num_of(r[1])
                if amt is not None:
                    out["items"].append({"side": side, "ccy": ccy, "amt_m": round(amt * k, 3), "hedge": "공정가치", "instr": "선도"})
                    if rate and rate > 100:
                        out["avg_rate"] = rate
                out["shape"] = out["shape"] or "row-ccy"
                continue
            # (2) 삼성중공업형: [매도통화, 매도금액, 매입통화, 매입금액, …]
            if len(r) >= 4 and _CCY.fullmatch(r[0].strip() or "") and _CCY.fullmatch(r[2].strip() or ""):
                sell_ccy, sell_amt, buy_ccy, buy_amt = r[0].strip(), num_of(r[1]), r[2].strip(), num_of(r[3])
                if sell_amt is not None:
                    out["items"].append({"side": "매도", "ccy": sell_ccy, "amt_m": round(sell_amt * k, 3), "hedge": "", "instr": "선도"})
                if buy_amt is not None:
                    out["items"].append({"side": "매입", "ccy": buy_ccy, "amt_m": round(buy_amt * k, 3), "hedge": "", "instr": "선도"})
                out["shape"] = out["shape"] or "pair-cols"
                continue
            if "평균만기" in lab:
                out["avg_maturity"] = [v for v in r[1:] if v]
            if "계약건수" in lab:
                out["contracts"] = [num_of(v) for v in r[1:]]
    out["usd_sell_m"] = round(sum(i["amt_m"] for i in out["items"] if i["side"] == "매도" and i["ccy"] == "USD"), 3)
    out["usd_buy_m"] = round(sum(i["amt_m"] for i in out["items"] if i["side"] == "매입" and i["ccy"] == "USD"), 3)
    return out


def collect_one(rec, quarter, force=False):
    st = rec["stock"]
    path = os.path.join(CACHE, st, quarter + ".json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    start, end = report_window(quarter)
    reports = pick_report(search_reports(st, start, end, report_kind(quarter)), quarter)
    if not reports:
        return {"stock": st, "quarter": quarter, "ok": False, "note": "정기보고서 없음"}
    rcp, title = reports[0]
    nodes = toc(rcp)
    found = find_sections(nodes, SECTIONS)
    out = {"stock": st, "quarter": quarter, "rcp": rcp, "title": title, "ok": False, "note": ""}
    if "orders" not in found:
        out["note"] = "수주 절 없음"
        return out
    html = fetch_section(found["orders"])
    tables = parse_tables(html)
    orders = [x for x in (parse_orders_table(t) for t in tables if t["cols"]) if x and x["rows"]]
    revenue = [x for x in (parse_revenue_table(t) for t in tables if t["cols"]) if x]
    if not orders:
        out["note"] = "수주표 인식 실패 — 머리행: %s" % [t["cols"] for t in tables if t["cols"]][:3]
        return out
    out["orders"] = max(orders, key=lambda o: len(o["rows"]))
    out["revenue"] = revenue[0] if revenue else None
    hedges = []
    if "risk" in found:
        rhtml = fetch_section(found["risk"])
        fx = [x for x in (parse_fx_table(t) for t in parse_tables(rhtml) if t["cols"]) if x]
        out["fx"] = fx[0] if fx else None            # 첫 표 = 당반기
        hedges.append(parse_hedge_any(rhtml, "risk"))
    # 헤지 주석: 제목에 '파생금융상품'이 들어간 연결 주석(없는 회사도 있다 — 한화오션은 절에만)
    hn = [n for n in nodes if "파생금융상품" in n["text"] and "연결" in n["text"]] or \
         [n for n in nodes if "파생금융상품" in n["text"]]
    if hn:
        hedges.append(parse_hedge_any(fetch_section(hn[0]), "note"))
    # 절과 주석이 같은 계약을 둘 다 적는 회사가 있다 — USD 매도 명목액이 큰 쪽 하나를 채택한다
    hedges = [h for h in hedges if h["items"]]
    out["hedge"] = max(hedges, key=lambda h: h["usd_sell_m"]) if hedges else None
    out["ok"] = True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--quarter", default=None)
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    q = a.quarter or latest_quarter()
    yards = [r for r in load_universe() if r["role"] == "yard"]
    if a.only:
        sel = set(a.only.split(","))
        yards = [r for r in yards if r["stock"] in sel]
    if a.collect:
        for r in yards:
            try:
                d = collect_one(r, q, a.force)
            except Exception as e:
                print("%s %s 실패: %s" % (r["stock"], r["name"], e), file=sys.stderr)
                continue
            if not d.get("ok"):
                print("%s %-10s ✗ %s" % (r["stock"], r["name"], d.get("note")))
                continue
            o = d["orders"]
            tot = [x for x in o["rows"] if x["total"]]
            close = tot[0]["closing"] if tot else sum((x["closing"] or 0) for x in o["rows"])
            fwd = (d.get("hedge") or {}).get("usd_sell_m") or 0
            ca = (d.get("fx") or {}).get("contract_asset")
            print("%s %-10s ✓ 잔고 %s %s · 부문 %d · 헤지매도 USD %sM · 계약자산USD %s" % (
                r["stock"], r["name"], format(round(close or 0), ","), o["cur"],
                sum(1 for x in o["rows"] if not x["total"]), format(round(fwd), ","),
                (format(ca[0], ",") if ca else "—")))


if __name__ == "__main__":
    sys.exit(main())
