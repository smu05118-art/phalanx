#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_build — 캐시된 정기보고서 절들을 회사별 **캐파 원장**으로 엮는다.

보고서 한 건은 당기(반기·분기·연간)와 직전 연간 1~2개의 생산능력 열을 가진다. 여러 분기의 보고서를 겹치면
연도별 연간 생산능력 시계열(2022~)과 분기별 가동률이 나온다. 연간 생산능력이 보고서 사이에서 5% 이상 달라지면
`changes` 에 증설·축소·신설·중단으로 남긴다(원문 두 값을 그대로 적는다 — 해석은 화면에서 '추정' 표시).

출력: assets/capacity/<stock>.json (회사별 원장), assets/ledger.json (전체 요약).
"""
import datetime
import json
import os
import re
import sys

from kcap_lib import ASSETS, CACHE, dump_json, load_asset, quarter_months, read_cache, write_asset
import kcap_capacity as C

CHANGE_PCT = 5.0
ANNUAL_RX = re.compile(r"보고서 연간 열\(")      # 연간 열 출처 판정 — 근거 문구('직전 연간 열 없음')의 부분 문자열에 속지 않게 접두 고정


def cross_report_annualize(r, months, prev_annual):
    """보고서 안에 직전 연간 열이 없을 때(국도화학 '미상' 기간 표) 원장의 직전 연도 값으로 파서와 같은 연환산 규칙을 적용한다.
    (기간값 < 직전 연도 × PRORATED_MAX 면 기간비례, 아니면 명판 그대로). 근거가 없으면 파서 값 그대로."""
    cap_t = r["capacity_ton_annual"]
    if not (r.get("basis") or "").startswith("연환산 근거 없음") or not months or months >= 12 or not prev_annual:
        return cap_t, r.get("basis")
    period_t = r["capacity_period"] * r["ton_mul"] if (r.get("capacity_period") is not None and r.get("ton_mul")) else cap_t
    ratio = period_t / prev_annual
    if ratio < C.PRORATED_MAX:
        return period_t * 12.0 / months, "기간비례(%d개월)→연환산(원장 직전 연도 기준)" % months
    return period_t, "연간 명판 그대로(원장 직전 연도와 %d%%)" % round(100 * ratio)


def changes_of(annual, annual_src):
    """연도별 생산능력 → (변동 목록, 최신 연환산 vs 마지막 연간 열). 변동은 **연간 열끼리**만 비교한다 —
    당기 연환산(기간비례 추정)과 연간 열을 비교하면 분기 보고서의 일수 비례 때문에 가짜 ±15% 가 생긴다."""
    annual_only = {y: v for y, v in annual.items() if ANNUAL_RX.search(annual_src.get(y) or "")}
    ys = sorted(annual_only, key=int)
    changes = []
    for a, b in zip(ys, ys[1:]):
        va, vb = annual_only[a], annual_only[b]
        if va and vb:
            pct = 100.0 * (vb - va) / va
            if abs(pct) >= CHANGE_PCT:
                changes.append({"from_year": a, "to_year": b, "from": va, "to": vb, "pct": round(pct, 1),
                                "kind": "증설" if pct > 0 else "축소", "src": [annual_src.get(a), annual_src.get(b)]})
        elif va and not vb:
            changes.append({"from_year": a, "to_year": b, "from": va, "to": 0.0, "pct": -100.0, "kind": "중단(0)", "src": [annual_src.get(a), annual_src.get(b)]})
    # 최신 연환산 vs 마지막 연간 열 — 낮은 신뢰(기간비례 추정)지만 올해 증설 징후는 여기서만 보인다
    est_years = sorted((y for y in annual if y not in annual_only), key=int)
    latest_vs_annual = None
    if est_years and ys:
        y, ya = est_years[-1], ys[-1]
        va, vb = annual_only[ya], annual[y]
        if va and vb and abs(100.0 * (vb - va) / va) >= CHANGE_PCT:
            latest_vs_annual = {"annual_year": ya, "annual": va, "est_year": y, "est": vb, "pct": round(100.0 * (vb - va) / va, 1),
                                "note": "당기 연환산(추정) 대비 — 분기 보고서의 일수 비례·정기보수 반영 가능성, 사업보고서로 확인 전까지 참고"}
    return changes, latest_vs_annual


def _norm(s):
    return re.sub(r"[\s　]+", "", s or "")


def product_key(r):
    return "%s|%s|%s" % (_norm(r["product_raw"]), _norm(r["entity"]), _norm(r["site"]))


def period_years(parsed_periods, quarter):
    """보고서의 기간 라벨 목록 → {라벨: (연도, 개월)}. 당기 = 분기의 연도·개월, 나머지는 라벨의 연도 또는 내림차순으로 연-1, 연-2."""
    qy = int(quarter[:4])
    out = {}
    order = 0
    for lab, cur in parsed_periods:
        if cur:
            out[lab] = (qy, quarter_months(quarter))
            continue
        m = re.search(r"(20\d{2})", lab)
        if m:
            y = int(m.group(1))
            out[lab] = (y, 12 if not re.search(r"반기|분기|상반기", lab) else quarter_months(quarter))
        else:
            order += 1
            out[lab] = (qy - order, 12 if not re.search(r"반기|분기|상반기", lab) else quarter_months(quarter))
    return out


def cached_quarters(stock):
    d = os.path.join(CACHE, stock)
    if not os.path.isdir(d):
        return []
    qs = sorted(f[:6] for f in os.listdir(d) if f.endswith("_cap.html"))
    return qs


def build_company(stock, name):
    prods = {}
    reports = {}
    for q in cached_quarters(stock):
        html = read_cache(stock, "%s_cap.html" % q)
        meta_raw = read_cache(stock, "%s_cap.meta.json" % q)
        meta = json.loads(meta_raw) if meta_raw else {}
        try:
            parsed = C.parse_section(html, q)
        except Exception as e:           # 한 분기 파싱 실패가 회사 전체를 지우지 않게
            reports[q] = {"rcp": meta.get("rcp"), "title": meta.get("title"), "error": "%s: %s" % (type(e).__name__, str(e)[:120])}
            continue
        reports[q] = {"rcp": meta.get("rcp"), "title": meta.get("title"), "node": meta.get("node"), "tables": parsed["tables"],
                      "n_products": len(parsed["products"]), "n_ton": sum(1 for r in parsed["products"] if r["is_ton"] and r["capacity_ton_annual"]),
                      "unparsed": len(parsed["unparsed"])}
        for r in parsed["products"]:
            k = product_key(r)
            p = prods.setdefault(k, {"key": k, "product_raw": r["product_raw"], "family": r["family"], "segment": r["segment"],
                                     "site": r["site"], "entity": r["entity"], "unit_raw": r["unit_raw"], "is_ton": r["is_ton"],
                                     "aggregate": r.get("aggregate", False), "by_report": {}, "annual": {}, "annual_src": {}})
            if r["is_ton"] and not p["is_ton"]:
                p["is_ton"], p["unit_raw"] = True, r["unit_raw"]
            p["by_report"][q] = {"capacity_period": r["capacity_period"], "capacity_ton_annual": r["capacity_ton_annual"],
                                 "output_period": r["output_period"], "output_ton_period": r.get("output_ton_period"), "ton_mul": r["ton_mul"],
                                 "util_pct": r["util_pct"], "util_src": r.get("util_src"),
                                 "months": r["months"], "basis": r["basis"], "nameplate_ton": r.get("nameplate_ton"),
                                 "cur_period": r["cur_period"]}
            # 연도별 연간 생산능력 — 당기(연환산)와 직전 연간 열들
            labels = [(pk, pk == r["cur_period"]) for pk in r["history"]]
            years = period_years(labels, q)
            for pk, vals in r["history"].items():
                cap = vals.get("capacity")
                if cap is None or cap < 0 or not r["ton_mul"]:
                    continue                      # 음수는 증감 열 누수(WISCOM) — 생산능력이 아니다
                if pk == "미상" and pk != r["cur_period"]:
                    continue                      # 기간 없는 열은 그 표의 당기일 때만(국도화학 단일 열) — 다른 표(산출근거)에서 섞여 온 '미상' 은 연도를 받지 않는다
                y, months = years.get(pk, (None, None))
                if y is None:
                    continue
                if months == 12:
                    val, src = cap * r["ton_mul"], "%s 보고서 연간 열(%s)" % (q, pk)
                elif pk == r["cur_period"] and r["capacity_ton_annual"]:
                    val, basis = cross_report_annualize(r, months, p["annual"].get(str(int(y) - 1)))
                    if basis != r["basis"]:
                        p["by_report"][q]["capacity_ton_annual"], p["by_report"][q]["basis"] = val, basis
                    src = "%s 보고서 당기 연환산(%s)" % (q, basis)
                else:
                    continue
                key = str(y)
                # 같은 연도 값이 여러 보고서에서 오면 최신 보고서의 연간 열 > 연환산 순으로 우선
                prev = p["annual_src"].get(key)
                rank = (1 if months == 12 else 0, q)
                if prev is None or rank > prev["rank"]:
                    p["annual"][key] = val
                    p["annual_src"][key] = {"rank": rank, "src": src}
    # 최신 상태·변동
    for p in prods.values():
        qs = sorted(p["by_report"])
        latest_q = qs[-1] if qs else None
        p["latest"] = dict(p["by_report"][latest_q], quarter=latest_q) if latest_q else None
        p["annual_src"] = {y: v["src"] for y, v in p["annual_src"].items()}
        p["changes"], p["latest_vs_annual"] = changes_of(p["annual"], p["annual_src"])
        p["util_history"] = [{"q": q, "util_pct": v["util_pct"], "months": v["months"], "src": v.get("util_src")} for q, v in sorted(p["by_report"].items()) if v["util_pct"] is not None]
    # 같은 품목이 사업소 표기만 바뀌어 두 키로 갈라진 경우(OCI 카본블랙 '포항,광양,산동' → '포항,광양') 같은 변동이 두 번 나온다 — 한 번만
    seen = set()
    for p in sorted(prods.values(), key=lambda p: (p["product_raw"], p["entity"], p["key"])):
        kept = []
        for ch in p["changes"]:
            sig = (p["product_raw"], p["entity"], ch["from_year"], ch["to_year"], ch["from"], ch["to"])
            if sig not in seen:
                seen.add(sig)
                kept.append(ch)
        p["changes"] = kept
    out = {"stock": stock, "name": name, "reports": reports, "products": sorted(prods.values(), key=lambda p: (not p["is_ton"], p["entity"], p["product_raw"])),
           "n_products": len(prods), "n_ton_products": sum(1 for p in prods.values() if p["is_ton"] and p["latest"] and p["latest"]["capacity_ton_annual"]),
           "n_changes": sum(len(p["changes"]) for p in prods.values()), "quarters": cached_quarters(stock)}
    return out


def build_all(write=True):
    uni = load_asset("universe.json")["rows"]
    ledger = {"companies": {}, "n_companies": 0, "n_products": 0, "n_ton_products": 0, "n_changes": 0}
    for r in uni:
        if r.get("excluded"):
            continue
        if not cached_quarters(r["stock"]):
            continue
        co = build_company(r["stock"], r["name"])
        if write:
            write_asset("capacity/%s.json" % r["stock"], co)
        ledger["companies"][r["stock"]] = {"name": r["name"], "quarters": co["quarters"], "n_products": co["n_products"],
                                           "n_ton_products": co["n_ton_products"], "n_changes": co["n_changes"],
                                           "errors": [q for q, v in co["reports"].items() if v.get("error")]}
        ledger["n_companies"] += 1
        ledger["n_products"] += co["n_products"]
        ledger["n_ton_products"] += co["n_ton_products"]
        ledger["n_changes"] += co["n_changes"]
    if write:
        write_asset("ledger.json", ledger)
    return ledger


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    led = build_all(write="--dry-run" not in argv)
    print("companies %d · products %d · ton products %d · changes %d" % (led["n_companies"], led["n_products"], led["n_ton_products"], led["n_changes"]))
    if "--changes" in argv:
        for st, c in led["companies"].items():
            if c["n_changes"]:
                co = json.load(open(os.path.join(ASSETS, "capacity", "%s.json" % st), encoding="utf-8"))
                for p in co["products"]:
                    for ch in p["changes"]:
                        print("  %s %s | %s (%s) %s→%s: %.0f→%.0f (%+.1f%%) %s" % (st, c["name"], p["product_raw"][:18], p["entity"][:12], ch["from_year"], ch["to_year"], ch["from"], ch["to"], ch["pct"], ch["kind"]))


if __name__ == "__main__":
    main()
