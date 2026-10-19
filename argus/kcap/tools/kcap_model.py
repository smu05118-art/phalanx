#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_model — 제품→스프레드 매핑, 분기 스프레드 마진 프록시, 보고 영업이익 보정, 다음 분기 추정.

  마진 프록시(억원, 분기) = Σ_제품 [ 연간 생산능력(톤)/4 × 가동률 × Σ_구성 share × 스프레드 분기평균(USD/MT) ] × 환율(원/달러, 분기평균) ÷ 1e8

  · 스프레드는 argus/kchem 레지스트리(원장 역산)에서 제품 토큰·지역(한국 우선)으로 고른다 — 원장은 2026-08-24 이후 멈춰 있으므로
    그 뒤 분기는 마지막 13주 평균을 '가정' 으로 쓰고 정지 주수를 표시한다.
  · 가동률은 보고서의 누적 생산실적을 분기별로 차분해 쓰고, 없으면 보고된 기간 가동률 → 사업장 집계 가동률 → 회사 중앙값(추정) → 80% 가정.
  · 보정: 보고 영업이익(연결, 억원) = a + b × 프록시, 분기 4개 이상에서 최소제곱. R²·잔차 σ 를 그대로 보인다.
  · 추정: 다음 분기(마지막 보고 분기 + 1·+2)의 프록시에 a·b 를 적용, 범위는 ±1.64σ. 보정이 안 되면 프록시만.
전부 '추정' 이다 — 원문이 지지하지 않는 수치(바스켓 구성비·가동률 가정·계수)는 화면에 '추정' 으로 표시하고 근거를 남긴다.
출력: assets/model.json
"""
import datetime
import json
import os
import re
import sys

from kcap_lib import ARGUS, ASSETS, load_asset, write_asset

KCHEM_REG = os.path.join(ARGUS, "kchem", "tools", "assets", "registry.json")
KCHEM_DATA = os.path.join(ARGUS, "kchem", "data", "kchem_data.js")
FX_PATH = os.path.join(ARGUS, "kship", "tools", "assets", "fx.json")
MIN_FIT_N = 4
DEFAULT_UTIL = 80.0          # 아무 근거도 없을 때의 가동률 가정 — 화면에 '추정(80% 가정)'
MIN_R2 = 0.3                 # 보정 추정을 화면 수치로 내보내는 최소 설명력
MIN_COVERAGE = 30.0          # 매핑 캐파 비중(비화학 제외)이 이보다 작으면 보정이 회사 손익을 대표하지 못한다
MIN_SCALE = 0.2              # 프록시 평균 / |영업이익| 평균 — 이보다 작으면 다른 사업(정유·지주)이 손익을 지배한다
NON_PRODUCT_RX = re.compile(r"증기|스팀|전기|전력|용수|순수|소금|가스|드라이아이스|소스|식품|설탕|건자재|리조트|하역|운송|부산물|스크랩|폐|자동차|태양광|모듈|셀|전지박|동박|필름|부직포|타이어|섬유|원사|직물|의약|백신|화장품")


# ── 외부 입력 ─────────────────────────────────────────────

def _json_after(text, what):
    i, j = text.find("{"), text.rfind("}")
    if i < 0:
        raise ValueError("%s: JSON 없음" % what)
    return json.loads(text[i:j + 1])


def load_kchem():
    with open(KCHEM_REG, encoding="utf-8") as f:
        reg = json.load(f)
    with open(KCHEM_DATA, encoding="utf-8") as f:
        data = _json_after(f.read(), "kchem_data.js")
    return reg, data


def load_fx():
    with open(FX_PATH, encoding="utf-8") as f:
        fx = json.load(f)
    return {q: v.get("USDKRW_avg") for q, v in fx["quarters"].items() if v.get("USDKRW_avg")}, fx.get("as_of")


# ── 분기 ──────────────────────────────────────────────────

def q_of_date(d):
    y, m = int(d[:4]), int(d[5:7])
    return "%dQ%d" % (y, (m - 1) // 3 + 1)


def q_next(q, n=1):
    y, k = int(q[:4]), int(q[5])
    for _ in range(n):
        y, k = (y + 1, 1) if k == 4 else (y, k + 1)
    return "%dQ%d" % (y, k)


def q_range(a, b):
    out, q = [], a
    while q <= b:
        out.append(q)
        q = q_next(q)
        if len(out) > 60:
            break
    return out


# ── 제품 매핑 ───────────────────────────────────────────────

def _norm_label(raw):
    s = re.sub(r"[\s　]+", "", raw or "").lower()
    s = re.sub(r"\(주\d*\)|\(\*\)|\(단위[^)]*\)", "", s)
    return s


def map_product(raw, pmap):
    """품목 표기 → [{'token','share','rule'}] (없으면 [])."""
    cands = []
    base = _norm_label(raw)
    cands.append(base)
    stripped = re.sub(r"(등|외|류|레진|제품|수지|계열)+$", "", base)
    if stripped and stripped != base:
        cands.append(stripped)
    stripped2 = re.sub(r"\([^)]*\)", "", stripped or base)
    if stripped2 and stripped2 not in cands:
        cands.append(stripped2)
    rules = pmap["rules"]
    for c in cands:
        for rule in rules:
            if re.fullmatch(rule["match"], c):
                return [dict(p, rule=rule["match"], note=rule.get("note")) for p in rule["products"]]
    # 복합 표기 '카본블랙,TAR, PA' · 'EO/EG' 는 규칙에 있으면 위에서 잡힌다; 아니면 부분별로
    parts = [x for x in re.split(r"[,/·+&、]", base) if x]
    if len(parts) >= 2:
        found = []
        for part in parts:
            p2 = re.sub(r"(등|외|류|레진|제품|수지|계열)+$", "", part)
            for rule in rules:
                if re.fullmatch(rule["match"], p2 or part):
                    found.extend(dict(p, rule=rule["match"], note=rule.get("note"), part=part) for p in rule["products"])
                    break
        if found:
            # 부분이 n개면 각 부분은 1/n — 매핑 안 된 부분('과산화수소, TDI' 의 과산화수소)은 그 몫만큼 빠진다(과대계상 금지)
            w = 1.0 / len(parts)
            return [dict(f, share=round(f["share"] * w, 4), partial=True) for f in found]
    return []


def company_override(stock, raw, pmap):
    ov = (pmap.get("company_overrides") or {}).get(stock) or {}
    for k, v in ov.items():
        if _norm_label(k) == _norm_label(raw):
            return [dict(x, rule="운영자 입력", note=x.get("source", "운영자 입력(추정)")) for x in v]
    return None


def spread_candidates(token, reg, pmap):
    """제품 토큰 → [(sid, weight, row)] — 복합 토큰은 구성원으로 펼친다. 없으면 []."""
    comp = pmap["composites"].get(token)
    members = comp["members"] if comp else [token]
    region_order = pmap["spread_region_order"]
    layer_order = pmap["layer_order"]
    rows = [r for r in reg["rows"] if r.get("kind") == "spread" and r.get("product")] + \
           [r for r in reg.get("derived", []) if r.get("values") is not None]
    out = []
    for m in members:
        cands = [r for r in rows if r.get("product") == m and (r.get("region") or "") in region_order]
        if not cands:
            continue
        cands.sort(key=lambda r: (region_order.index(r.get("region")), layer_order.index(r.get("layer")) if r.get("layer") in layer_order else 9,
                                  0 if r.get("reproduced") else 1, r["sid"]))
        out.append((cands[0]["sid"], 1.0 / len(members), cands[0]))
    return out


# ── 시계열 ─────────────────────────────────────────────────

def quarter_means(data, sid):
    s = data["series"].get(sid)
    if not s:
        return {}, None
    dates = data["axes"][s["axis"]] if s.get("axis") else s.get("dates") or []
    acc = {}
    last = None
    for d, v in zip(dates, s["v"]):
        if v is None:
            continue
        acc.setdefault(q_of_date(d), []).append(float(v))
        last = d
    return {q: (sum(v) / len(v), len(v)) for q, v in acc.items()}, last


def recent_mean(data, sid, weeks=13):
    s = data["series"].get(sid)
    if not s:
        return None
    vals = [float(v) for v in s["v"] if v is not None][-weeks:]
    return sum(vals) / len(vals) if vals else None


def output_ton(rep):
    """보고서 한 건의 누적 생산실적(톤). 원장은 원문 단위 값(output_period)과 톤 환산(output_ton_period)을 같이 두며,
    톤 환산이 없으면 ton_mul 로 바꾼다 — 생산능력(톤)과 같은 단위로만 나눈다(GS '천톤' 527 ÷ 1,338,000 톤 같은 단위 착오 금지)."""
    if not rep:
        return None
    if rep.get("output_ton_period") is not None:
        return rep["output_ton_period"]
    if rep.get("output_period") is not None and rep.get("ton_mul"):
        return rep["output_period"] * rep["ton_mul"]
    return None


def util_series(product, quarters):
    """제품의 분기별 가동률(%) — 누적 생산실적 차분 → 보고 가동률 → None. 돌려줌 {q: (util, src)}."""
    br = product.get("by_report") or {}
    out = {}
    for q in quarters:
        y, k = int(q[:4]), int(q[5])
        rep = br.get(q)
        cap = (rep or {}).get("capacity_ton_annual")
        val = None
        if rep and output_ton(rep) is not None and cap:
            # 누적 차분: Q1 = 1Q, Qn = n분기 누적 − (n−1) 누적, Q4 = 연간 − 9M
            prev_q = "%dQ%d" % (y, k - 1) if k > 1 else None
            prev = br.get(prev_q) if prev_q else None
            out_q = output_ton(rep) - (output_ton(prev) if output_ton(prev) is not None else 0.0) if k > 1 else output_ton(rep)
            if k == 1 or output_ton(prev) is not None:
                val = (100.0 * out_q / (cap / 4.0), "누적차분")
                if val[0] < 0:
                    # 뒤 보고서의 누적이 앞 보고서보다 작다(한화솔루션 LDPE 2026 반기) — 원문 불일치이므로 차분을 버리고 보고 가동률로
                    val = (rep["util_pct"], "보고 기간 가동률(%d개월)·누적차분 불일치" % rep["months"]) if rep.get("util_pct") is not None else None
            elif rep.get("util_pct") is not None:
                val = (rep["util_pct"], "보고 기간 가동률(%d개월)" % rep["months"])
        elif rep and rep.get("util_pct") is not None:
            val = (rep["util_pct"], "보고 기간 가동률(%d개월)" % rep["months"])
        if val is None:
            # 분기 보고서가 없는 분기: 같은 해의 가장 가까운 뒤 보고서의 기간 가동률
            later = [br[qq] for qq in sorted(br) if qq[:4] == q[:4] and qq > q and br[qq].get("util_pct") is not None]
            if later:
                val = (later[0]["util_pct"], "같은 해 뒤 보고서 기간 가동률")
        if val is not None and val[0] is not None and val[0] > 200:
            val = None     # 단위 착오로 보이는 값은 쓰지 않는다
        out[q] = val
    return out


# ── 보정 ───────────────────────────────────────────────────

def ols(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    ss_res = sum(r * r for r in resid)
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else None
    sigma = (ss_res / (n - 2)) ** 0.5 if n > 2 else None
    return {"a": a, "b": b, "r2": r2, "sigma": sigma, "n": n}


# ── 모델 ───────────────────────────────────────────────────

def build_company(stock, co, reg, data, fx, fxq_asof, pmap, fin, eval_date):
    quarters_all = q_range("2023Q1", "2027Q4")
    spread_cache = {}
    mapped, unmapped = [], []
    for p in co["products"]:
        if not (p["is_ton"] and p.get("latest") and p["latest"].get("capacity_ton_annual")):
            continue
        if p.get("aggregate"):
            continue
        m = company_override(stock, p["product_raw"], pmap) or map_product(p["product_raw"], pmap)
        if not m:
            unmapped.append({"product_raw": p["product_raw"], "entity": p["entity"], "capacity_ton_annual": p["latest"]["capacity_ton_annual"],
                             "non_product": bool(NON_PRODUCT_RX.search(p["product_raw"] + " " + (p.get("segment") or "")))})
            continue
        comps = []
        for mm in m:
            sc = spread_candidates(mm["token"], reg, pmap)
            if not sc:
                comps.append({"token": mm["token"], "share": mm["share"], "spreads": [], "note": mm.get("note"), "no_spread": True})
                continue
            comps.append({"token": mm["token"], "share": mm["share"], "note": mm.get("note"),
                          "spreads": [{"sid": sid, "w": w, "name": row["name"], "region": row.get("region"), "layer": row.get("layer"),
                                       "reproduced": row.get("reproduced"), "kind": row.get("kind")} for sid, w, row in sc]})
            for sid, _, _ in sc:
                if sid not in spread_cache:
                    spread_cache[sid] = quarter_means(data, sid) + (recent_mean(data, sid),)
        if all(c.get("no_spread") for c in comps):
            unmapped.append({"product_raw": p["product_raw"], "entity": p["entity"], "capacity_ton_annual": p["latest"]["capacity_ton_annual"],
                             "note": "토큰은 있으나 스프레드 시리즈 없음(%s)" % ", ".join(c["token"] for c in comps)})
            continue
        mapped.append({"key": p["key"], "product_raw": p["product_raw"], "entity": p["entity"], "site": p["site"],
                       "capacity_ton_annual": p["latest"]["capacity_ton_annual"], "capacity_quarter": p["latest"]["quarter"],
                       "basis": p["latest"]["basis"], "nameplate_ton": p["latest"].get("nameplate_ton"),
                       "components": comps, "util": util_series(p, quarters_all), "latest_util": p["latest"].get("util_pct")})
    if not mapped:
        return {"stock": stock, "name": co["name"], "promoted": False, "mapped": [], "unmapped": unmapped,
                "why": "스프레드에 매핑되는 톤 단위 제품 없음" if not unmapped else "매핑 가능한 제품 없음(%d개 미매핑)" % len(unmapped)}
    # 사업장 집계 가동률(대한유화 '기초유분 및모노머'·'폴리머' 처럼 품목이 아니라 공장 단위로만 가동률을 적는 회사) — 생산실적 가중 평균
    agg_util = {}
    for q in quarters_all:
        acc = []
        for p in co["products"]:
            if not p.get("aggregate"):
                continue
            u = util_series(p, [q]).get(q)
            if u and u[0] is not None:
                acc.append((u[0], output_ton((p.get("by_report") or {}).get(q)) or 1.0))
        if acc:
            agg_util[q] = round(sum(u * w for u, w in acc) / sum(w for _, w in acc), 1)
    # 회사 가동률 중앙값(폴백)
    utils_known = [v[0] for mp in mapped for v in mp["util"].values() if v] or list(agg_util.values())
    median_util = sorted(utils_known)[len(utils_known) // 2] if utils_known else None
    # 스프레드 신선도
    last_dates = [spread_cache[s][1] for s in spread_cache if spread_cache[s][1]]
    spread_last = max(last_dates) if last_dates else None
    stale_weeks = ((datetime.date.fromisoformat(eval_date) - datetime.date.fromisoformat(spread_last)).days // 7) if spread_last else None
    # 분기 프록시
    fin_q = (fin.get("series") or fin.get("quarters") or []) if fin else []     # kcap_fin: series = 분기 시계열 목록
    if isinstance(fin_q, dict):
        fin_q = []
    op_by_q = {x["q"]: x for x in fin_q if x.get("op_q") is not None}
    last_fin_q = max(op_by_q) if op_by_q else None
    first_q = "2023Q1"
    last_q = q_next(last_fin_q, 2) if last_fin_q else q_of_date(spread_last or eval_date)
    rows = []
    for q in q_range(first_q, last_q):
        total = 0.0
        detail = []
        assumed = []
        for mp in mapped:
            u = mp["util"].get(q)
            if u:
                util, usrc = u
            elif q in agg_util:
                util, usrc = agg_util[q], "사업장 집계 가동률(추정)"
                assumed.append("가동률")
            elif median_util is not None:
                util, usrc = median_util, "회사 중앙값(추정)"
                assumed.append("가동률")
            else:
                util, usrc = DEFAULT_UTIL, "80% 가정(추정)"
                assumed.append("가동률")
            sp_val = 0.0
            sp_src = []
            for c in mp["components"]:
                if c.get("no_spread"):
                    continue
                for s in c["spreads"]:
                    qm, lastd, rec = spread_cache[s["sid"]]
                    if q in qm:
                        v, nw = qm[q]
                        src = "분기평균 %d주" % nw
                        if nw < 10:
                            src += "(부분)"
                            assumed.append("스프레드 부분분기")
                    elif rec is not None:
                        v, src = rec, "최근 13주 평균 가정"
                        assumed.append("스프레드 가정")
                    else:
                        continue
                    sp_val += c["share"] * s["w"] * v
                    sp_src.append("%s=%.0f(%s)" % (s["sid"], v, src))
            fxv = fx.get(q)
            if fxv is None:
                fxv = fx[max(fx)]
                assumed.append("환율 가정")
            contrib = mp["capacity_ton_annual"] / 4.0 * (util / 100.0) * sp_val * fxv / 1e8
            total += contrib
            detail.append({"product_raw": mp["product_raw"], "entity": mp["entity"], "util": round(util, 1), "util_src": usrc,
                           "spread_usd": round(sp_val, 1), "spread_src": sp_src, "fx": fxv, "contrib_eok": round(contrib, 1)})
        op = op_by_q.get(q)
        rows.append({"q": q, "proxy_eok": round(total, 1), "op_eok": (op["op_q"] / 100.0 if op else None), "rev_eok": (op["rev_q"] / 100.0 if op and op.get("rev_q") is not None else None),
                     "op_basis": (op or {}).get("basis"), "assumed": sorted(set(assumed)), "detail": detail,
                     "status": ("보고" if op else ("추정" if last_fin_q and q > last_fin_q else "프록시만"))})
    # 보정
    pairs = [(r["proxy_eok"], r["op_eok"]) for r in rows if r["op_eok"] is not None and r["proxy_eok"] is not None]
    fit = ols([x for x, _ in pairs], [y for _, y in pairs]) if len(pairs) >= MIN_FIT_N else None
    for r in rows:
        if fit:
            r["op_fit_eok"] = round(fit["a"] + fit["b"] * r["proxy_eok"], 1)
            if fit["sigma"] is not None:
                r["op_fit_lo"] = round(r["op_fit_eok"] - 1.64 * fit["sigma"], 1)
                r["op_fit_hi"] = round(r["op_fit_eok"] + 1.64 * fit["sigma"], 1)
    estimates = [r for r in rows if r["status"] == "추정"]
    caveats = []
    if fit is not None and fit.get("r2") is not None and fit["r2"] < MIN_R2:
        pass
    if stale_weeks:
        caveats.append("스프레드 원장 마지막 관측 %s(평가일 기준 %d주 정지) — 그 뒤 분기는 최근 13주 평균 가정" % (spread_last, stale_weeks))
    if fit is None:
        caveats.append("보고 영업이익과 프록시의 분기 쌍이 %d개(최소 %d) — 보정 없음, 프록시 방향만" % (len(pairs), MIN_FIT_N))
    if unmapped:
        caveats.append("미매핑 톤 제품 %d개(%s) 는 프록시에 없음" % (len(unmapped), ", ".join(u["product_raw"][:10] for u in unmapped[:5])))
    if any("가동률" in r["assumed"] for r in rows if r["status"] == "추정"):
        caveats.append("추정 분기의 가동률은 회사 중앙값 또는 80% 가정")
    mapped_cap = sum(mp["capacity_ton_annual"] for mp in mapped)
    unmapped_chem = [u for u in unmapped if not u.get("non_product")]
    unmapped_cap = sum(u["capacity_ton_annual"] for u in unmapped_chem)
    coverage = round(100.0 * mapped_cap / (mapped_cap + unmapped_cap), 1) if (mapped_cap + unmapped_cap) else None
    # 보정이 회사 손익을 대표하는가 — 설명력·커버리지·규모 세 문턱을 모두 넘어야 '보정 추정' 수치를 화면에 낸다
    fit_ok, fit_why = False, []
    if fit:
        ops = [abs(r["op_eok"]) for r in rows if r["op_eok"] is not None]
        prx = [r["proxy_eok"] for r in rows if r["op_eok"] is not None]
        scale = (sum(prx) / len(prx)) / (sum(ops) / len(ops)) if ops and sum(ops) > 0 else None
        if fit["r2"] is None or fit["r2"] < MIN_R2:
            fit_why.append("설명력 낮음(R²=%s)" % (round(fit["r2"], 2) if fit["r2"] is not None else "-"))
        if coverage is None or coverage < MIN_COVERAGE:
            fit_why.append("매핑 커버리지 %s%% < %d%%" % (coverage, MIN_COVERAGE))
        if scale is not None and scale < MIN_SCALE:
            fit_why.append("프록시가 영업이익 대비 작음(%.2f) — 비매핑 사업(정유·지주 등)이 손익을 지배" % scale)
        if mapped_cap < 50000:
            fit_why.append("매핑 캐파 %.0f kt 미만" % 50)
        fit_ok = not fit_why
        fit["scale"] = round(scale, 3) if scale is not None else None
        fit["ok"] = fit_ok
        fit["why"] = fit_why
        if not fit_ok:
            caveats.append("보정 추정은 참고만: " + "; ".join(fit_why))
    return {"stock": stock, "name": co["name"], "promoted": True, "mapped": mapped, "unmapped": unmapped,
            "mapped_capacity_ton": mapped_cap, "unmapped_capacity_ton": unmapped_cap,
            "unmapped_nonproduct_ton": sum(u["capacity_ton_annual"] for u in unmapped if u.get("non_product")),
            "coverage_pct": coverage, "fit_ok": fit_ok,
            "median_util": median_util, "spread_last": spread_last, "stale_weeks": stale_weeks,
            "quarters": rows, "fit": fit, "last_fin_q": last_fin_q, "estimates": estimates, "caveats": caveats,
            "fin_basis": (fin_q[-1].get("basis") if fin_q else None)}


def build_all(write=True):
    reg, data = load_kchem()
    fx, fx_asof = load_fx()
    pmap = load_asset("product_map.json")
    ledger = load_asset("ledger.json")
    eval_date = reg.get("argus_asof") or datetime.date.today().isoformat()
    out = {"eval_date": eval_date, "kchem_fingerprint": reg.get("fingerprint"), "fx_asof": fx_asof,
           "rules": {"proxy": "Σ 캐파/4 × 가동률 × Σ share×스프레드(USD/MT) × 환율 ÷ 1e8 (억원)", "fit": "OP = a + b×proxy (OLS, n≥%d)" % MIN_FIT_N,
                     "range": "±1.64σ", "default_util": DEFAULT_UTIL, "spread_fallback": "최근 13주 평균"},
           "companies": {}, "summary": {}}
    for stock, meta in ledger["companies"].items():
        co = load_asset("capacity/%s.json" % stock)
        fin = load_asset("fin/%s.json" % stock, default={}) if os.path.isfile(os.path.join(ASSETS, "fin", "%s.json" % stock)) else {}
        out["companies"][stock] = build_company(stock, co, reg, data, fx, fx_asof, pmap, fin if isinstance(fin, dict) else {}, eval_date)
    cos = out["companies"].values()
    out["summary"] = {"companies": len(out["companies"]), "promoted": sum(1 for c in cos if c["promoted"]),
                      "with_fit": sum(1 for c in cos if c.get("fit")), "with_fit_ok": sum(1 for c in cos if c.get("fit_ok")),
                      "with_estimate": sum(1 for c in cos if c.get("estimates")),
                      "mapped_capacity_ton": sum(c.get("mapped_capacity_ton", 0) for c in cos),
                      "unmapped_capacity_ton": sum(c.get("unmapped_capacity_ton", 0) for c in cos)}
    if write:
        write_asset("model.json", out)
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    m = build_all(write="--dry-run" not in argv)
    s = m["summary"]
    print("companies %d · promoted %d · with fit %d · with estimate %d · mapped cap %.0f kt · unmapped %.0f kt" % (
        s["companies"], s["promoted"], s["with_fit"], s["with_estimate"], s["mapped_capacity_ton"] / 1000, s["unmapped_capacity_ton"] / 1000))
    if "--list" in argv:
        for st, c in sorted(m["companies"].items(), key=lambda x: -(x[1].get("mapped_capacity_ton") or 0)):
            if not c["promoted"]:
                continue
            est = c["estimates"][0] if c["estimates"] else None
            print("  %s %-10s cov %5s%% fit %s est %s" % (st, c["name"][:10], c.get("coverage_pct"),
                  ("n=%d R²=%s" % (c["fit"]["n"], round(c["fit"]["r2"], 2) if c["fit"]["r2"] is not None else "-")) if c["fit"] else "-",
                  ("%s proxy %.0f → OP %s" % (est["q"], est["proxy_eok"], est.get("op_fit_eok"))) if est else "-"))
            for mp in c["mapped"]:
                print("      %-18s %10.0f t/yr → %s" % (mp["product_raw"][:18], mp["capacity_ton_annual"], ", ".join("%s×%s[%s]" % (cc["token"], cc["share"], "/".join(s["sid"][:22] for s in cc["spreads"]) or "없음") for cc in mp["components"])))
            for u in c["unmapped"]:
                print("      ✗ %-18s %10.0f t/yr 미매핑 %s" % (u["product_raw"][:18], u["capacity_ton_annual"], u.get("note", "")))


if __name__ == "__main__":
    main()
