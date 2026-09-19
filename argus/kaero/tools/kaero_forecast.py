#!/usr/bin/env python3
"""Offline KAERO ledger forecast. Python standard library; never imports KCE.

Round 2 extends the supplied round-1 engine, audit and renderer.
Amounts require the supplied parser normalization contract and retain currency.
No raw captions, physical production schedules or accounting revenue are invented.
Run from the assignment root: python3 -B output/kaero_forecast.py
"""
import argparse
import calendar
import copy
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
ORIGIN = "2026Q2"
SCENARIOS = {"conservative": .25, "base": .5, "optimistic": .75}
CURRENCIES = {"KRW", "USD"}
LEDGER_TARGET_START = "2021Q4"
STATUS = {"full": "full_ledger_estimate", "partial": "partial_amount_estimate", "unavailable": "unavailable"}
REASONS = {
    "no_backlog": "항공·우주 잔고 금액 없음",
    "no_origin_snapshot": "기준분기 원장 없음",
    "unit_currency_unresolved": "단위·통화 미확정",
    "mixed_currency_caption": "USD·천원 혼합 캡션; 행별 단위 분리 필요",
    "scope_outside_aerospace": "행 문구가 항공·우주 밖 사업",
    "scope_ambiguous": "겸업사 행의 항공·우주 귀속 불명",
    "scope_restricted_rows": "입력 잔고에 비항공·미상 행이 있어 일부만 사용",
    "aggregate_scope_unresolved": "잔고와 납품·매출 부문 범위 미확정",
    "accounting_identity_conflict": "수주총액−기납품≠잔고; 단위·열·기간 재검증 필요",
    "row_total_mismatch": "상세 행 합계와 보고 잔고 불일치",
    "duplicate_row_identity": "같은 계약 식별자 중복",
    "negative_delivery_delta": "누계 납품 감소; 계약 탈락·재분류·기간 리셋 가능",
    "delivery_missing": "누계 납품 금액 없음",
    "gross_missing": "수주총액 없음",
    "nonconsecutive_quarter": "연속 분기 관측 아님",
    "insufficient_burn_samples": "유효 납품속도 표본 2개 미만",
    "insufficient_order_samples": "유효 순수주 표본 4개 미만",
    "missing_due_or_overdue": "유효 미래 납기 없음 또는 이미 경과",
    "rsp_lta_no_burn_samples": "RSP·LTA 납품속도 근거 부족; 종료일 강제 소진 금지",
    "missing_order_duration": "신규 수주 인식기간 근거 없음",
    "partial_existing_coverage": "기존 잔고 일부만 추정 가능",
    "missing_observed_calendar_quarter": "당해 연도 관측 원장 차분 누락",
    "multiple_currencies_no_scalar": "복수 통화는 currency_panels에 분리; 회사 합계 금지",
    "raw_unit_caption_not_supplied": "정규화 단위 계약은 확인; 원본 표 캡션 미제공",
    "calendar_year_assumption": "12월 결산 가정; 공시로 미확인",
    "not_financial_statement_revenue": "원장 납품·소진 대용치이며 재무제표 매출 아님",
    "short_backtest": "짧은 원장·선별된 검증 표본; 장기 예측·통계적 구간 검증 부족",
    "unit_caption_unavailable": "제공된 파서 정규화 계약으로 단위 사용; 원문 캡션 미확인",
    "needs_longer_ledger": "과거 원장 확장 후 재검증 필요; 적격 표본 확보·차단 해제를 보장하지 않음",
    "dictionary_reference_unresolved": "새 분류 사전에서 코드 또는 필수 성격을 확인하지 못함",
    "classification_semantics_unverified": "사전 코드의 존재는 검증; 원문 대비 의미 분류는 미검증",
    "unknown_customer_tier": "고객 계층 미확인; 임의 배정하지 않음",
    "group_overlap_no_industry_sum": "한화에어로 원장과 쎄트렉아이 중복 가능; 회사 간 합산 금지",
    "historical_gross_changed": "채점 기간 수주총액 변경; 기존 잔고분 정답 분리 불가",
    "report_vintage_unavailable": "원공시·정정 전 빈티지 없어 실제 공시시점 백테스트 아님",
    "reported_rounding_difference": "상세합과 보고 합계에 허용 반올림 차이; 원값 보존",
    "reported_fy_column_stale": "매출 연도 열이 직전 회계연도보다 과거; 커버리지 분모 검증 필요",
}


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def quantile(values, p):
    a = sorted(x for x in values if number(x))
    if not a:
        return None
    k = (len(a) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return a[lo] + (a[hi] - a[lo]) * (k - lo)


def qnum(q):
    if not re.fullmatch(r"\d{4}Q[1-4]", q):
        raise ValueError("invalid quarter")
    return int(q[:4]) * 4 + int(q[-1]) - 1


def qadd(q, h):
    y, n = divmod(qnum(q) + h, 4)
    return f"{y}Q{n + 1}"


def qend(q):
    m = int(q[-1]) * 3
    y = int(q[:4])
    return date(y, m, calendar.monthrange(y, m)[1])


def parse_date(value, end=False):
    """Strict precision-aware bounds. Counts ('400대') are never dates."""
    s = str(value or "").strip()
    if re.search(r"대|shipset|미정|상세", s, re.I):
        return None, "invalid_or_missing"
    s = s.lstrip("~ ")
    if "~" in s:
        parts = s.split("~")
        if len(parts) != 2 or not all(re.fullmatch(r"\s*\d{4}년?\s*", p) for p in parts):
            return None, "ambiguous_range"
        s = parts[-1 if end else 0].strip()
    match = re.fullmatch(r"(\d{4})(?:[-./년]\s*(\d{1,2}))?(?:[-./월]\s*(\d{1,2}))?[년월일.]?", s)
    if not match:
        return None, "invalid_or_missing"
    y, m, d = (int(v) if v else None for v in match.groups())
    precision = "day" if d else "month" if m else "year"
    m = m or (12 if end else 1)
    try:
        d = d or (calendar.monthrange(y, m)[1] if end else 1)
        return date(y, m, d), precision
    except ValueError:
        return None, "invalid_or_missing"


def tolerance(cur, n=1):
    # Reports mix integer-million and sub-million precision. Rounding tolerance
    # is fixed per row; never percentage-scaled to large backlog values.
    return (1.01 if cur == "KRW" else .000002) * max(1, n)


def identity_ok(row, cur):
    g, d, b = row.get("gross"), row.get("delivered"), row.get("closing")
    return (all(number(x) and x >= 0 for x in (g, d, b)) and
            abs(g - d - b) <= tolerance(cur))


def canonical_label(row):
    # Legal-prefix changes seen in the supplied Hanwha snapshots; no fuzzy join.
    s = row.get("label", "").replace("및해외생산법인", "및해외종속회사")
    s = re.sub(r"\s+", "", s)
    s = s.removesuffix("등")
    return s


def row_id(row):
    start, _ = parse_date(row.get("order_date"))
    return "|".join((str(row.get("cur")), canonical_label(row), str(start or row.get("order_date", ""))))


def scope_reason(stock, row):
    s = row.get("label", "")
    # Audit contradictions in the given ledger; narrower explicit context wins.
    aerospace = bool(re.search(r"항공|우주|위성|헬기|발사체", s))
    if not aerospace and re.search(r"한국수력원자력|원자력|증기발생기|전차|장갑차|대공포|포병|포수조준경|전방관측|신궁", s):
        return "scope_outside_aerospace"
    if row.get("tab") not in (None, "kaero"):
        return "scope_outside_aerospace"
    if stock in {"214430", "046120", "361390"} and not aerospace:
        if stock == "361390" and "EGSE" in s:
            return None
        return "scope_ambiguous"
    return None


def row_grain(row):
    label = row.get("label", "")
    if re.fullmatch(r"\s*(합\s*계|총\s*합\s*계|소\s*계)\s*", label):
        return "total"
    if label in {"조립", "부품", "위성사업", "위성시스템", "위성통신", "핵심부품 등", "항공전자 등", "EGSE/점검장비"}:
        return "segment"
    return "contract_or_program"  # Not asserted to be an individual airframe.


def native_currencies(table):
    return sorted(set(table.get("backlog", {})) | {r.get("cur") for r in table.get("contracts", []) if r.get("cur")})


def unit_confirmed(table, cur):
    return (table.get("_normalization_verified") is True and table.get("ok") is True and cur in CURRENCIES and cur in table.get("shapes", {}) and
            not any("통화가 둘 이상" in x for x in table.get("notes", [])))


def snapshot(co, quarter, cur):
    t = co.get("quarters", {}).get(quarter, {})
    rows = [r for r in t.get("contracts", []) if r.get("cur") == cur and row_grain(r) != "total"]
    counts = Counter(row_id(r) for r in rows)
    accepted, excluded = [], []
    for r in rows:
        reason = scope_reason(co["stock"], r)
        if r.get("_dictionary_invalid"):
            reason = "dictionary_reference_unresolved"
        if counts[row_id(r)] > 1:
            reason = "duplicate_row_identity"
        if reason:
            excluded.append({"row_id": row_id(r), "label": r["label"], "backlog": r.get("closing"), "reason": reason})
        else:
            accepted.append(r)
    b, g, d = (t.get(k, {}).get(cur) for k in ("backlog", "gross", "delivered"))
    reasons = []
    if not unit_confirmed(t, cur):
        reasons.append("unit_currency_unresolved")
    if excluded:
        reasons.append("scope_restricted_rows")
    if not rows and co["stock"] in {"047810", "003490", "484590", "487400"}:
        # KAI denominator omits complete-aircraft exports. KAL lacks matching sales.
        # KNS includes naval antennas and has no row-level sector separation.
        reasons.append("aggregate_scope_unresolved")
    sum_b = sum(r["closing"] for r in rows) if rows and all(number(r.get("closing")) for r in rows) else None
    if number(sum_b) and number(b) and abs(sum_b - b) > tolerance(cur, len(rows)):
        reasons.append("row_total_mismatch")
    amount_identity = None
    if all(number(x) for x in (g, d, b)):
        amount_identity = abs(g - d - b) <= tolerance(cur, len(rows)) and min(g, d, b) >= 0
        if not amount_identity:
            reasons.append("accounting_identity_conflict")
    return {"table": t, "rows": accepted, "all_rows": rows, "excluded": excluded,
            "backlog": b, "gross": g, "delivered": d, "sum_rows_backlog": sum_b,
            "amount_identity": amount_identity, "reasons": reasons,
            "scope_complete": not any(x in reasons for x in ("scope_restricted_rows", "aggregate_scope_unresolved", "row_total_mismatch")),
            "unit_confirmed": unit_confirmed(t, cur)}


def flow_pair(co, q0, q1, cur):
    a, b = snapshot(co, q0, cur), snapshot(co, q1, cur)
    reasons = []
    if qadd(q0, 1) != q1:
        reasons.append("nonconsecutive_quarter")
    if not a["unit_confirmed"] or not b["unit_confirmed"]:
        reasons.append("unit_currency_unresolved")
    if not a["scope_complete"] or not b["scope_complete"]:
        reasons.append("aggregate_scope_unresolved")
    if not number(a["delivered"]) or not number(b["delivered"]):
        reasons.append("delivery_missing")
    if a["amount_identity"] is not True or b["amount_identity"] is not True:
        reasons.append("accounting_identity_conflict")
    delta = b["delivered"] - a["delivered"] if number(a["delivered"]) and number(b["delivered"]) else None
    if number(delta) and delta < 0:
        reasons.append("negative_delivery_delta")
    order = b["backlog"] - a["backlog"] + delta if number(a["backlog"]) and number(b["backlog"]) and number(delta) else None
    return {"from": q0, "quarter": q1, "delivery_delta": delta, "net_orders": order,
            "burn_rate": delta / a["backlog"] if number(delta) and number(a["backlog"]) and a["backlog"] > 0 else None,
            "eligible": not reasons and number(order), "reason_codes": sorted(set(reasons))}


def evidence(co, origin, cur):
    qs = sorted(q for q in co.get("quarters", {}) if q <= origin)
    pairs = [flow_pair(co, a, b, cur) for a, b in zip(qs, qs[1:])]
    valid = [x for x in pairs if x["eligible"]]
    return {"pairs": pairs, "net_order_samples": [x["net_orders"] for x in valid],
            "burn_samples": [x["burn_rate"] for x in valid if 0 <= x["burn_rate"] <= 1],
            "negative_net_orders_retained": sum(x["net_orders"] < 0 for x in valid),
            "order_basis": "delta_native_currency_backlog_plus_delta_cumulative_delivered; net revisions, not gross bookings",
            "seasonality": {"applied": False, "reason": "no validated same-scope seasonal model; no automatic seasoning on ledger extension"}}


def row_rates(co, origin, row):
    qs = sorted(q for q in co.get("quarters", {}) if q <= origin)
    samples, rejects = [], []
    key, cur = row_id(row), row["cur"]
    for q0, q1 in zip(qs, qs[1:]):
        a = [r for r in snapshot(co, q0, cur)["rows"] if row_id(r) == key]
        b = [r for r in snapshot(co, q1, cur)["rows"] if row_id(r) == key]
        if len(a) != 1 or len(b) != 1 or qadd(q0, 1) != q1:
            continue
        if not (unit_confirmed(co["quarters"][q0], cur) and unit_confirmed(co["quarters"][q1], cur)):
            continue
        if not identity_ok(a[0], cur) or not identity_ok(b[0], cur):
            rejects.append({"quarter": q1, "reason": "accounting_identity_conflict"})
            continue
        delta = b[0]["delivered"] - a[0]["delivered"]
        if delta < 0:
            rejects.append({"quarter": q1, "reason": "negative_delivery_delta"})
        elif a[0]["closing"] > 0 and delta <= a[0]["closing"]:
            samples.append({"quarter": q1, "rate": delta / a[0]["closing"], "delivery_delta": delta})
    return samples, rejects


def interval(lower=None, upper=None, method="parameter_sensitivity_envelope"):
    return {"lower": lower, "upper": upper, "method": method, "nominal_level": None, "calibrated": False}


def burn_path(backlog, rate, n):
    return [backlog * rate * (1 - rate) ** h for h in range(n)]


def schedule_path(backlog, origin, start, due, n, shift_days=0):
    # Conditional uniform recognition in remaining calendar time, not a claimed
    # physical schedule, output rate, stage, shipset count or construction curve.
    from datetime import timedelta
    begin = max(qend(origin), start or qend(origin))
    finish = due + timedelta(days=shift_days)
    finish = max(finish, begin + timedelta(days=1))
    span = (finish - begin).days
    def cum(day):
        return max(0, min(1, (day - begin).days / span))
    return [backlog * (cum(qend(qadd(origin, h))) - cum(qend(qadd(origin, h - 1)))) for h in range(1, n + 1)]


def fit_row(co, origin, row, n=10):
    b, cur = row.get("closing"), row.get("cur")
    samples, rejects = row_rates(co, origin, row)
    start, sp = parse_date(row.get("order_date"))
    due, dp = parse_date(row.get("due"), end=True)
    reasons = []
    result = {"row_id": row_id(row), "label": row.get("label"), "currency": cur,
              "domain": row.get("domain"), "nature": row.get("nature"), "grain": row_grain(row),
              "classification": row.get("_classification", {}),
              "unit_status": "unit_caption_unavailable", "money_unit": cur + "_million" if cur in CURRENCIES else None,
              "origin_backlog": b, "gross": row.get("gross"), "delivered": row.get("delivered"),
              "order_date_raw": row.get("order_date"), "due_raw": row.get("due"),
              "start": start.isoformat() if start else None, "due": due.isoformat() if due else None,
              "start_precision": sp, "due_precision": dp,
              "progress": row["delivered"] / row["gross"] if identity_ok(row, cur) and row["gross"] > 0 else None,
              "samples": samples, "rejected_pairs": rejects, "method": None,
              "physical_stage": None, "airframe_number": None, "shipsets": None, "production_rate": None,
              "reason_codes": reasons}
    path, paths = None, []
    if not number(b) or b < 0 or cur not in CURRENCIES:
        reasons.append("unit_currency_unresolved")
    elif b == 0:
        path = [0.] * n
        paths = [path]
        result["method"] = "observed_zero_backlog"
    elif all(number(row.get(k)) for k in ("gross", "delivered", "closing")) and not identity_ok(row, cur):
        reasons.append("accounting_identity_conflict")
    elif len(samples) >= 2:
        rates = [s["rate"] for s in samples]
        r = quantile(rates, .5)
        path = burn_path(b, r, n)
        # Evaluate the continuous rate envelope: r(1-r)^(h-1) peaks at 1/h.
        lo, hi = min(rates), max(rates)
        paths = [burn_path(b, x, n) for x in sorted({lo, hi, r} | {1 / h for h in range(1, n + 1) if lo <= 1 / h <= hi})]
        result.update(method="program_empirical_burn" if row.get("nature") in {"RSP", "LTA"} else "ledger_empirical_burn", burn_rate=r)
    elif row.get("nature") in {"RSP", "LTA"}:
        reasons.append("rsp_lta_no_burn_samples")
    elif row_grain(row) == "segment":
        reasons.append("insufficient_burn_samples")
    elif due and due > qend(origin) and (not start or due > start):
        path = schedule_path(b, origin, start, due, n)
        # Explicit timing stress; year-only input carries a full-year span.
        stress = 365 if dp == "year" else 92
        paths = [schedule_path(b, origin, start, due, n, shift) for shift in (-stress, 0, stress)]
        result.update(method="conditional_uniform_remaining_schedule", timing_stress_days=stress)
    else:
        reasons.append("missing_due_or_overdue")
    result["quarterly"] = [{"quarter": qadd(origin, i + 1), "horizon": i + 1,
                            "revenue": path[i] if path else None,
                            "revenue_interval": interval(min(p[i] for p in paths), max(p[i] for p in paths)) if paths else interval()}
                           for i in range(n)]
    return result


def aggregate_model(co, origin, cur, ev, n):
    s = snapshot(co, origin, cur)
    row = {"cur": cur, "label": "__reported_aggregate__", "seg": "", "nature": "AGGREGATE",
           "gross": s["gross"], "delivered": s["delivered"], "closing": s["backlog"], "order_date": "-", "due": "-"}
    model = fit_row({"stock": co["stock"], "quarters": {}}, origin, row, n)
    rates = ev["burn_samples"]
    if s["scope_complete"] and s["amount_identity"] is True and len(rates) >= 2:
        rate = quantile(rates, .5)
        b = s["backlog"]
        low, high = min(rates), max(rates)
        paths = [burn_path(b, x, n) for x in sorted({low, high, rate} | {1 / h for h in range(1, n + 1) if low <= 1 / h <= high})]
        model.update(method="reported_aggregate_burn", burn_rate=rate, reason_codes=[], samples=[x for x in ev["pairs"] if x["eligible"]])
        model["quarterly"] = [{"quarter": qadd(origin, h), "horizon": h,
                              "revenue": burn_path(b, rate, n)[h - 1],
                              "revenue_interval": interval(min(p[h - 1] for p in paths), max(p[h - 1] for p in paths))}
                             for h in range(1, n + 1)]
    else:
        model["reason_codes"] = sorted(set(s["reasons"] + ["insufficient_burn_samples"]))
        model["samples"] = [x for x in ev["pairs"] if x["eligible"] and number(x["burn_rate"]) and 0 <= x["burn_rate"] <= 1]
    return model


def new_order_path(order, duration, n, lag=0):
    if order is None or duration is None or duration <= 0:
        return [None] * n, [None] * n
    # Orders placed at each quarter END. lag=0 still gives no delivery in T+1.
    def cum(age):
        return max(0., min(1., (age - lag) / duration))
    revenue, balances = [], []
    for h in range(1, n + 1):
        delivered = sum(order * (cum(h - issue) - cum(h - 1 - issue)) for issue in range(1, h + 1))
        revenue.append(delivered)
        balances.append(h * order - sum(revenue))
    return revenue, balances


def sum_if_known(values):
    return sum(values) if values and all(number(v) for v in values) else None


def annualize(rows, observed, origin, years=(2026, 2027, 2028)):
    result = []
    byq = {r["quarter"]: r for r in rows}
    for year in years:
        qs = [f"{year}Q{i}" for i in range(1, 5)]
        future = [byq[q] for q in qs if q > origin and q in byq]
        past = [q for q in qs if q <= origin]
        obs = sum_if_known([observed.get(q) for q in past]) if past else 0.
        all_future_present = len(future) == len(qs) - len(past)
        fields = ("existing_backlog_revenue", "covered_sites_partial_revenue", "new_order_revenue")
        parts = {key: sum_if_known([r[key] for r in future]) if all_future_present and future else None for key in fields}
        value = obs + parts["existing_backlog_revenue"] + parts["new_order_revenue"] if all(number(v) for v in (obs, parts["existing_backlog_revenue"], parts["new_order_revenue"])) else None
        bounds = {}
        for key in ("interval", "partial_existing_interval", "covered_sites_partial_interval", "new_order_interval"):
            lower = sum_if_known([r[key]["lower"] for r in future]) if all_future_present else None
            upper = sum_if_known([r[key]["upper"] for r in future]) if all_future_present else None
            if key == "interval":
                lower = lower + obs if number(lower) and number(obs) and number(value) else None
                upper = upper + obs if number(upper) and number(obs) and number(value) else None
            bounds[key] = interval(lower, upper, "sum_of_quarter_marginal_sensitivity_bounds")
        missing = [q for q in past if not number(observed.get(q))] + [q for q in qs if q > origin and q not in byq]
        reasons = sorted(set(code for r in future for code in r["reason_codes"]))
        if missing:
            reasons.append("missing_observed_calendar_quarter")
        result.append({"fiscal_year": year, "value": value, "observed_revenue": obs,
                       **parts, **bounds, "complete": value is not None, "quarters": qs,
                       "missing_quarters": missing, "reason_codes": sorted(set(reasons)),
                       "reason": ";".join(sorted(set(reasons))) if value is None else None})
    return result


def blank_scenarios(origin, n, reasons):
    scenarios = {}
    for name in SCENARIOS:
        rows = [{"quarter": qadd(origin, h), "horizon": h, "value": None,
                 "existing_backlog_revenue": None, "covered_sites_partial_revenue": None,
                 "new_order_revenue": None, "new_order_backlog": None, "new_orders": None,
                 "existing_backlog_method": None, "interval": interval(),
                 "new_order_interval": interval(),
                 "partial_existing_interval": interval(), "covered_sites_partial_interval": interval(),
                 "status": "unavailable", "reason_codes": reasons} for h in range(1, n + 1)]
        scenarios[name] = {"assumptions": {"missing_reasons": reasons}, "quarterly": rows,
                           "annual": annualize(rows, {}, origin)}
    return scenarios


def project_currency(co, origin, cur, n=10):
    s = snapshot(co, origin, cur)
    ev = evidence(co, origin, cur)
    reasons = list(s["reasons"])
    if s["unit_confirmed"]:
        reasons.append("unit_caption_unavailable")
    models = []
    if s["unit_confirmed"]:
        if len(s["rows"]) == 1 and row_grain(s["rows"][0]) == "segment" and s["scope_complete"]:
            # A single segment rollup is not a contract identity. In particular,
            # Satrec's 위성시스템 -> 위성사업 label is not fuzzily joined.
            models = [aggregate_model(co, origin, cur, ev, n)]
        elif s["rows"]:
            models = [fit_row(co, origin, r, n) for r in s["rows"]]
        elif number(s["backlog"]) and s["scope_complete"]:
            models = [aggregate_model(co, origin, cur, ev, n)]
    covered = [m for m in models if all(number(x["revenue"]) for x in m["quarterly"])]
    full_existing = bool(covered) and len(covered) == len(models) and s["scope_complete"] and number(s["backlog"])
    if not number(s["backlog"]):
        reasons.append("no_backlog")
    if not full_existing:
        reasons.append("partial_existing_coverage")
    reasons += [code for m in models for code in m["reason_codes"]]
    duration_samples = []
    for r in s["rows"]:
        start, _ = parse_date(r.get("order_date"))
        end, _ = parse_date(r.get("due"), end=True)
        if start and end and end > start and r.get("nature") != "RSP":
            duration_samples.append((end - start).days / (365.25 / 4))
    duration = quantile(duration_samples, .5)
    duration_basis = "median_disclosed_non_RSP_contract_duration_not_production_lead_time"
    if duration is None and len(ev["burn_samples"]) >= 2:
        rate = quantile(ev["burn_samples"], .5)
        duration = 1 / rate if rate > 0 else None
        duration_basis = "inverse_median_aggregate_burn_rate_assumption_not_disclosed_lead_time"
    eligible_orders = full_existing and len(ev["net_order_samples"]) >= 4 and duration is not None
    if len(ev["net_order_samples"]) < 4:
        reasons.append("insufficient_order_samples")
    if duration is None:
        reasons.append("missing_order_duration")
    status = "full" if full_existing and eligible_orders else "partial" if covered else "unavailable"
    # Fiscal actuals use only valid same-currency, same-ledger deltas. No revenue_fy / 4.
    observed = {x["quarter"]: x["delivery_delta"] for x in ev["pairs"] if x["eligible"]}
    scenarios = {}
    for name, p in SCENARIOS.items():
        raw_order = quantile(ev["net_order_samples"], p) if eligible_orders else None
        order = max(0., raw_order) if raw_order is not None else None
        new, new_b = new_order_path(order, duration, n)
        o_lo = max(0., quantile(ev["net_order_samples"], .1)) if eligible_orders else None
        o_hi = max(0., quantile(ev["net_order_samples"], .9)) if eligible_orders else None
        # New-order sensitivity includes explicit ±25% duration and 0..1 q lag.
        new_stresses = [new_order_path(o, duration * d, n, lag)[0]
                        for o in (o_lo, order, o_hi) for d in (.75, 1., 1.25) for lag in (0, 1)] if eligible_orders else []
        rows = []
        for i in range(n):
            partial = sum(m["quarterly"][i]["revenue"] for m in covered) if covered else None
            existing = partial if full_existing else None
            low = sum(m["quarterly"][i]["revenue_interval"]["lower"] for m in covered) if covered else None
            high = sum(m["quarterly"][i]["revenue_interval"]["upper"] for m in covered) if covered else None
            total = existing + new[i] if number(existing) and number(new[i]) else None
            bounds = interval(low + min(x[i] for x in new_stresses), high + max(x[i] for x in new_stresses)) if number(total) else interval()
            rows.append({"quarter": qadd(origin, i + 1), "horizon": i + 1, "value": total,
                         "existing_backlog_revenue": existing, "covered_sites_partial_revenue": partial,
                         "new_order_revenue": new[i], "new_order_backlog": new_b[i], "new_orders": order,
                         "new_order_interval": interval(min(x[i] for x in new_stresses), max(x[i] for x in new_stresses)) if new_stresses else interval(),
                         "interval": bounds, "partial_existing_interval": interval(low, high) if full_existing else interval(),
                         "covered_sites_partial_interval": interval(low, high),
                         "existing_backlog_method": "sum_of_disjoint_native_currency_ledger_models" if covered else None,
                         "status": STATUS[status], "reason_codes": sorted(set(reasons))})
        assumptions = {"new_orders_per_quarter": order,
                       "new_orders_per_quarter_deseasonalized": order,
                       "legacy_field_note": "deseasonalized is a retained r1 key; seasonality_applied=false",
                       "new_orders_raw_quantile": raw_order,
                       "money_unit": cur + "_million", "order_quantile": p, "order_samples": len(ev["net_order_samples"]),
                       "duration_quarters": duration, "duration_basis": duration_basis,
                       "duration_samples": duration_samples, "lag_quarters": 0,
                       "lag_basis": "explicit_quarter_end_award_assumption; no_empirical_start_lag",
                       "timing_policy": "identical_existing_path_and_new_duration_across_scenarios; only_order_quantile_varies",
                       "new_order_recognition": "quarter_end_native_currency_cohorts_uniform_duration",
                       "seasonality_applied": False, "missing_reasons": sorted(set(reasons)),
                       "fx_rate_assumption": None, "currency_conversion": False}
        scenarios[name] = {"assumptions": assumptions, "quarterly": rows, "annual": annualize(rows, observed, origin)}
    return {"currency": cur, "money_unit": cur + "_million" if cur in CURRENCIES else None,
            "unit_status": "unit_caption_unavailable" if s["unit_confirmed"] else "unit_currency_unresolved",
            "estimate_status": status, "status": STATUS[status], "reason_codes": sorted(set(reasons)),
            "scope": "supplied_aerospace_ledger_after_explicit_scope_audit", "financial_statement_revenue": False,
            "coverage": {"reported_backlog": s["backlog"], "covered_backlog": sum(m["origin_backlog"] for m in covered) if covered else None,
                         "row_sum_minus_reported_backlog": s["sum_rows_backlog"] - s["backlog"] if number(s["sum_rows_backlog"]) and number(s["backlog"]) else None,
                         "rounding_tolerance": tolerance(cur, len(s["all_rows"])),
                         "full_existing_backlog": full_existing, "models": len(models), "covered_models": len(covered),
                         "fraction": sum(m["origin_backlog"] for m in covered) / s["backlog"] if covered and number(s["backlog"]) and s["backlog"] > 0 else None},
            "evidence": ev, "excluded_rows": s["excluded"], "row_forecasts": models,
            "scenarios": scenarios, "actual_revenue_proxy": observed,
            "aggregate_forecast": {"origin_backlog": sum(m["origin_backlog"] for m in covered) if covered else None,
                                   "reported_backlog": s["backlog"], "method": "disjoint_rows" if s["rows"] else "aggregate_burn",
                                   "quarterly": [{"quarter": x["quarter"], "horizon": x["horizon"],
                                                  "revenue": x["existing_backlog_revenue"], "revenue_interval": x["partial_existing_interval"]}
                                                 for x in scenarios["base"]["quarterly"]]}}


def project_company(co, origin=ORIGIN, n=10):
    t = co.get("quarters", {}).get(origin, {})
    currencies = native_currencies(t)
    channels = [project_currency(co, origin, cur, n) for cur in currencies]
    status = "full" if channels and all(c["estimate_status"] == "full" for c in channels) else "partial" if any(c["estimate_status"] != "unavailable" for c in channels) else "unavailable"
    reasons = sorted(set(x for c in channels for x in c["reason_codes"]))
    if not channels:
        reasons += ["no_backlog"]
    if not t:
        reasons += ["no_origin_snapshot"]
    if any("통화가 둘 이상" in x for x in t.get("notes", [])):
        reasons += ["mixed_currency_caption", "unit_currency_unresolved"]
    if len(channels) > 1:
        reasons.append("multiple_currencies_no_scalar")
    one = channels[0] if len(channels) == 1 else None
    base = {"company_id": co["stock"], "company_name": co["name"], "audited_company_name": co["name"],
            "stock": co["stock"], "listed": True, "source": "kaero_reports", "origin": origin,
            "panel_present": bool(t), "grade": "offline_ledger_audit", "audited_grade": status,
            "estimate_status": status, "status": STATUS[status], "reason_codes": sorted(set(reasons)),
            "audit_can": {"forecast": status, "trace": "derived_report_rows_only", "backtest": "limited"},
            "audit_blockers": sorted(set(reasons)), "money_unit": one["money_unit"] if one else None,
            "scope": "kaero_ledger_proxy_not_company_consolidated_revenue", "financial_statement_revenue": False,
            "fiscal_year_end_month": 12, "fiscal_basis": "assumed_December_close_unverified",
            "currency_panels": channels, "multi_currency": len(channels) > 1,
            "unit_audit": {"normalized_unit_confirmed": bool(currencies) and all(unit_confirmed(t, c) for c in currencies),
                           "verified_at_origin": False, "raw_unit_caption_available": False,
                           "status": "unit_caption_unavailable",
                           "unit_basis": "input/kaero_unit_evidence.json: kce_parse._UNIT_SCALE normalizes KRW to million; kaero_LOGIC §1 native currency million; captions/code not independently checked",
                           "scale_from_input": 1, "currencies": currencies},
            "warnings": ["unit_caption_unavailable", "calendar_year_assumption", "not_financial_statement_revenue", "short_backtest", "report_vintage_unavailable", "classification_semantics_unverified"],
            "industry_axes": {"role": co.get("role"), "physical_delivery_schedule": None, "stage": None,
                              "airframe_or_shipset_count": None, "production_rate": None,
                              "schedule_basis": "disclosed_contract_dates_or_historical_delivery_burn_only",
                              "fx": {"conversion": False, "KRW_per_USD": None,
                                     "optional_formula_only": "USD_million * assumed_KRW_per_USD = KRW_million; no assumed FX inserted",
                                     "ten_won_shock_KRW_million_per_USD_million": 10, "hedge_data": None}}}
    for key in ("coverage", "evidence", "aggregate_forecast", "actual_revenue_proxy"):
        base[key] = one[key] if one else {} if key != "aggregate_forecast" else None
    base["scenarios"] = one["scenarios"] if one else blank_scenarios(origin, n, base["reason_codes"])
    for ch in channels:
        diff = ch["coverage"]["row_sum_minus_reported_backlog"]
        if number(diff) and 1e-9 < abs(diff) <= ch["coverage"]["rounding_tolerance"]:
            base["warnings"].append("reported_rounding_difference")
    fy_years = re.findall(r"20\d{2}", str(t.get("revenue_fy_col", "")))
    if fy_years and max(map(int, fy_years)) < int(origin[:4]) - 1:
        base["warnings"].append("reported_fy_column_stale")
    if co["stock"] in {"012450", "099320"}:
        base["warnings"].append("group_overlap_no_industry_sum")
    return base


def quarterly_audit(co, q):
    t = co["quarters"][q]
    rows = t.get("contracts", [])
    dates = Counter()
    for r in rows:
        for field, end in (("order_date", False), ("due", True)):
            d, p = parse_date(r.get(field), end)
            dates[field + ":" + p] += 1
            if field == "due" and d and d <= qend(q) and number(r.get("closing")) and r["closing"] > 0:
                dates["due:overdue_positive_backlog"] += 1
    money = {}
    for cur in native_currencies(t):
        s = snapshot(co, q, cur)
        money[cur] = {k: s[k] for k in ("unit_confirmed", "backlog", "gross", "delivered", "sum_rows_backlog", "amount_identity", "reasons", "excluded")}
        money[cur]["original_caption"] = None
        money[cur]["unit_status"] = "unit_caption_unavailable" if s["unit_confirmed"] else "unit_currency_unresolved"
    row_checks = []
    for i, r in enumerate(rows):
        g, d, b = (r.get(k) for k in ("gross", "delivered", "closing"))
        check = identity_ok(r, r.get("cur")) if all(number(x) for x in (g, d, b)) else None
        row_checks.append({"index": i, "row_id": row_id(r), "label": r.get("label"), "currency": r.get("cur"),
                           "source_pointer": f"/companies/{co['stock']}/quarters/{q}/contracts/{i}",
                           "gross": g, "delivered": d, "closing": b,
                           "grain": row_grain(r), "amount_identity": check,
                           "identity_difference": g - d - b if check is not None else None,
                           "scope_reason": scope_reason(co["stock"], r),
                           "order_date": r.get("order_date"), "due": r.get("due"),
                           "missing_amount_fields": [k for k in ("gross", "delivered", "closing") if not number(r.get(k))]})
    return {"quarter": q, "rcp": t.get("rcp"), "report_title": t.get("title"), "ok": t.get("ok"),
            "report_publication_date": str(t.get("rcp", ""))[:8] or None,
            "rows": len(rows), "grain_counts": dict(Counter(row_grain(r) for r in rows)),
            "aggregate_currency_tables": sum(x in {"openclose", "balance", "gross", "roll"} for x in t.get("shapes", {}).values()),
            "shapes": t.get("shapes", {}), "dates": dict(dates), "currency_unit_audit": money, "row_checks": row_checks,
            "notes": t.get("notes", []), "backlog_all": t.get("backlog_all"), "excluded_segments": t.get("dup_segments", []),
            "revenue_fy": t.get("revenue_fy"), "revenue_fy_col": t.get("revenue_fy_col"),
            "coverage_years_supplied": t.get("coverage_years"), "coverage_scope": t.get("coverage_scope"),
            "coverage_est_supplied": t.get("coverage_est"), "coverage_note": t.get("coverage_note")}


def collection_tasks(co, forecast, expected):
    tasks = []
    history = [qadd(LEDGER_TARGET_START, i) for i in range(qnum(ORIGIN) - qnum(LEDGER_TARGET_START) + 1)]
    for q in history:
        present = q in co.get("quarters", {})
        findings = quarterly_audit(co, q) if present else None
        fields = ["표 원문·직전 단위 캡션·통화·행별 단위·표 위치", "연결/별도·부문·내부거래 제거", "기초/신규/취소/납품/기말 잔고 연결표", "당분기와 누계 매출 구별·결산월"]
        blockers = list(forecast["reason_codes"])
        if co["stock"] == "274090":
            fields += ["USD와 천원 행의 $ 표식 및 행별 배수 분리; 혼합표 금액 산출 금지"]
        if co["stock"] in {"047810", "003490"}:
            fields += ["수주 범위와 같은 항공부문 매출; KAI 완제기수출 분리·KAL 총매출/연결조정/순매출 연결"]
        if co["stock"] in {"046120", "214430", "361390", "487400"}:
            fields += ["항공·우주와 원전/지상방산/해상용 사업 구분 및 누락 항공계약"]
        if co["stock"] in {"012450", "067390", "221840", "258610"}:
            fields += ["RSP/LTA 확정 발주와 프로그램 예상 총액 구분·콜오프·기종별 생산률·잔여 인도 일정"]
        if co["stock"] in {"288180", "451760", "488900", "484590"}:
            fields += ["II-4/XII 수주 상세·수주표 부재 여부; 항공부문 수주가 없다는 원문 확인"]
        fields += ["계약 식별자·호기/shipset·계통·공정단계·납기 변경 이력", "III 외화위험·환헤지 주석(환산 가정과 분리)"]
        row_targets = [r for r in findings["row_checks"]
                       if r["amount_identity"] is False or r["scope_reason"] or r["missing_amount_fields"] or
                       parse_date(r["due"], end=True)[0] is None or
                       (parse_date(r["due"], end=True)[0] <= qend(q) and number(r["closing"]) and r["closing"] > 0)] if findings else []
        observed_issues = sorted(set(code for v in findings["currency_unit_audit"].values() for code in v["reasons"])) if findings else ["report_not_in_input"]
        if row_targets:
            observed_issues.append("row_level_reextraction_targets")
        tasks.append({"company_id": co["stock"], "company_name": co["name"], "quarter": q,
                      "priority": "P0" if q == ORIGIN else "P1" if not present or q.startswith("2026") else "P2",
                      "action": "reextract_existing_report" if present else "collect_if_report_exists",
                      "existing_rcp": co.get("quarters", {}).get(q, {}).get("rcp"),
                      "report_sections": ["II-2", "II-4", "XII 수주상황 상세", "III 부문/수익/외화위험 주석"],
                      "fields": fields, "reason_codes": sorted(set(blockers)),
                      "observed_quarter_issues": observed_issues, "row_reextraction_targets": row_targets,
                      "acceptance_checks": ["원문 단위와 정규화 배수 일치", "같은 통화·범위의 G−C=B 및 행합 대조(오류를 강제 보정하지 않음)",
                                            "전분기와 식별자·부문·기간·단위 변화 확인", "추가 증거 없으면 null·사유 유지"],
                      "absence_policy": "상장 전·공시 의무 전 보고서 부재는 absent_not_zero로 기록; 후대 공시로 대체하지 않음"})
    return tasks


def make_audit(universe, reports, contracts, forecasts):
    out, tasks = [], []
    expected = reports["quarters"]
    fc = {c["company_id"]: c for c in forecasts}
    for u in universe["rows"]:
        co = reports["companies"].get(u["stock"], {"stock": u["stock"], "name": u["name"], "quarters": {}})
        qs = sorted(co["quarters"])
        f = fc[u["stock"]]
        quarters = [quarterly_audit(co, q) for q in qs]
        announcements = [r for r in contracts["rows"] if r.get("stock") == u["stock"]]
        item = {"company_id": u["stock"], "company_name": u["name"], "role": u.get("role"), "listed_date": u.get("listed"),
                "estimate_status": f["estimate_status"], "status": f["status"], "reason_codes": f["reason_codes"],
                "quarter_count": len(qs), "quarters_present": qs, "quarters_missing": [q for q in expected if q not in qs],
                "row_count": sum(x["rows"] for x in quarters), "latest_row_count": len(co.get("quarters", {}).get(ORIGIN, {}).get("contracts", [])),
                "aggregate_row_count": sum(x["grain_counts"].get("segment", 0) + x["grain_counts"].get("total", 0) for x in quarters),
                "aggregate_table_count": sum(x["aggregate_currency_tables"] for x in quarters),
                "unit_audit": f["unit_audit"], "warnings": f["warnings"], "quarters": quarters,
                "contract_announcements": {"rows": len(announcements), "corrected": sum(bool(r.get("corrected")) for r in announcements),
                                           "supersedes_links": sum(bool(r.get("supersedes")) for r in announcements),
                                           "basis": "cross_reference_only; no amounts added to periodic backlog; no reliable contract join/version history",
                                           "scope_warning": "issuer announcements can include non-aerospace contracts"}}
        out.append(item)
        tasks += collection_tasks(co, f, expected)
    coverage = [co["quarters"].get(ORIGIN, {}).get("coverage_years") for co in reports["companies"].values()]
    coverage = [v for v in coverage if number(v)]
    return {"schema_version": "kaero-audit-2", "origin": ORIGIN, "input_companies": len(universe["rows"]),
            "companies": out, "status_counts": dict(Counter(x["estimate_status"] for x in out)),
            "reason_dictionary": REASONS, "collection_tasks": tasks,
            "source_checks": {"report_records": sum(x["quarter_count"] for x in out),
                              "contract_ledger_rows_all_quarters": sum(x["row_count"] for x in out),
                              "contract_ledger_rows_origin": sum(x["latest_row_count"] for x in out),
                              "announcement_rows": len(contracts["rows"]),
                              "supplied_coverage_median_years": statistics.median(coverage) if coverage else None,
                              "supplied_coverage_samples": len(coverage), "claimed_3_8_year_median_reproduced": False,
                              "industry_backlog_total": None,
                              "not_industry_total_reason": "sector contamination and parent/subsidiary overlap; currencies cannot be added"},
            "audit_boundary": "provided normalized JSON and quoted text only; no original DART tables; no network",
            "tracker": {"preflight": "central_connection_failed", "claim_tool_in_workspace": False,
                        "ownership": "bounded isolated assignment output/ only; no handoff obtained or released"}}


def score_records(records):
    result = {}
    for cur in sorted({x["currency"] for x in records}):
        rs = [x for x in records if x["currency"] == cur]
        den = sum(abs(x["actual"]) for x in rs)
        paired = [x for x in rs if number(x.get("naive"))]
        pden = sum(abs(x["actual"]) for x in paired)
        result[cur] = {"n": len(rs), "company_count": len({x["company_id"] for x in rs}),
                       "mae": sum(abs(x["prediction"] - x["actual"]) for x in rs) / len(rs),
                       "wape": sum(abs(x["prediction"] - x["actual"]) for x in rs) / den if den else None,
                       "paired_naive_n": len(paired),
                       "paired_model_wape": sum(abs(x["prediction"] - x["actual"]) for x in paired) / pden if pden else None,
                       "paired_naive_wape": sum(abs(x["naive"] - x["actual"]) for x in paired) / pden if pden else None,
                       "money_unit": cur + "_million"}
    return result


def backtest(reports):
    existing, total, rejects = [], [], Counter()
    annual_existing, annual_total = [], []
    horizons = tuple(range(1, 11))
    for co in reports["companies"].values():
        qs = sorted(q for q in co["quarters"] if q <= ORIGIN)
        for origin in qs[:-1]:
            for cur in native_currencies(co["quarters"][origin]):
                # Prefix inputs: later report dates, rates and rows unavailable to fit.
                prefix = dict(co, quarters={q: co["quarters"][q] for q in qs if q <= origin})
                pred = project_currency(prefix, origin, cur, 10)
                for h in horizons:
                    target = qadd(origin, h)
                    if target not in qs:
                        continue
                    for model in pred["row_forecasts"]:
                        prediction = sum_if_known([x["revenue"] for x in model["quarterly"][:h]])
                        if prediction is None:
                            rejects["model_not_estimable_at_origin"] += 1
                            continue
                        key = model["row_id"]
                        actual_rows = []
                        for step in range(h + 1):
                            ss = snapshot(co, qadd(origin, step), cur)
                            if model["label"] == "__reported_aggregate__":
                                candidates = [{"gross": ss["gross"], "delivered": ss["delivered"], "closing": ss["backlog"]}] if ss["scope_complete"] and ss["unit_confirmed"] else []
                            else:
                                candidates = [x for x in ss["rows"] if row_id(x) == key] if ss["unit_confirmed"] else []
                            if len(candidates) != 1 or not identity_ok(candidates[0], cur):
                                actual_rows = []
                                break
                            actual_rows.append(candidates[0])
                        if not actual_rows:
                            rejects["target_missing_identity_or_unit"] += 1
                            continue
                        if any(abs(x["gross"] - actual_rows[0]["gross"]) > tolerance(cur) for x in actual_rows):
                            rejects["historical_gross_changed"] += 1
                            continue
                        deltas = [b["delivered"] - a["delivered"] for a, b in zip(actual_rows, actual_rows[1:])]
                        if any(x < 0 for x in deltas):
                            rejects["negative_delivery_delta"] += 1
                            continue
                        last_sample = model["samples"][-1] if model["samples"] else {}
                        naive_delta = last_sample.get("delivery_delta")
                        naive = min(model["origin_backlog"], h * naive_delta) if number(naive_delta) else None
                        existing.append({"company_id": co["stock"], "currency": cur, "origin": origin, "target": target,
                                         "horizon": h, "row_id": key, "method": model["method"], "prediction": prediction,
                                         "actual": sum(deltas), "naive": naive,
                                         "training_max_quarter": origin, "unit_status": "unit_caption_unavailable",
                                         "target_basis": "stable_gross_cumulative_delivery_delta"})
                        fiscal_year = int(origin[:4]) + 2
                        if target == f"{fiscal_year}Q4":
                            indices = [i for i in range(h) if int(qadd(origin, i + 1)[:4]) == fiscal_year]
                            if len(indices) == 4:
                                annual_existing.append({**existing[-1], "fiscal_year": fiscal_year,
                                    "prediction": sum(model["quarterly"][i]["revenue"] for i in indices),
                                    "actual": sum(deltas[i] for i in indices),
                                    "naive": min(max(0., model["origin_backlog"] - min(indices) * naive_delta), 4 * naive_delta) if number(naive_delta) else None,
                                    "target_basis": "FY_plus_2_four_quarters_stable_gross_delivery_delta"})
                    p = pred["scenarios"]["base"]["quarterly"]
                    predicted_total = sum_if_known([x["value"] for x in p[:h]])
                    if predicted_total is None:
                        rejects["total_not_estimable_at_origin"] += 1
                        continue
                    pairs = [flow_pair(co, qadd(origin, i), qadd(origin, i + 1), cur) for i in range(h)]
                    if not all(x["eligible"] for x in pairs):
                        rejects["total_target_unusable"] += 1
                        continue
                    hist = [x["delivery_delta"] for x in pred["evidence"]["pairs"] if x["eligible"]]
                    total.append({"company_id": co["stock"], "currency": cur, "origin": origin, "target": target,
                                  "horizon": h, "prediction": predicted_total, "actual": sum(x["delivery_delta"] for x in pairs),
                                  "predicted_new_order_revenue": sum(x["new_order_revenue"] for x in p[:h]),
                                  "naive": hist[-1] * h if hist else None,
                                  "training_max_quarter": origin, "unit_status": "unit_caption_unavailable",
                                  "target_basis": "aggregate_ledger_delivery_proxy_not_accounting_revenue"})
                    fiscal_year = int(origin[:4]) + 2
                    if target == f"{fiscal_year}Q4":
                        indices = [i for i in range(h) if int(qadd(origin, i + 1)[:4]) == fiscal_year]
                        if len(indices) == 4:
                            annual_total.append({**total[-1], "fiscal_year": fiscal_year,
                                "prediction": sum(p[i]["value"] for i in indices),
                                "actual": sum(pairs[i]["delivery_delta"] for i in indices),
                                "predicted_new_order_revenue": sum(p[i]["new_order_revenue"] for i in indices),
                                "naive": hist[-1] * 4 if hist else None,
                                "target_basis": "FY_plus_2_four_quarters_ledger_delivery_proxy"})
    return {"method": "rolling_quarter_prefix_no_future_rows_or_parameter_training", "calibrated": False,
            "small_sample": True, "quarter_origin_not_publication_time": True, "original_report_vintages_available": False,
            "unit_status": "unit_caption_unavailable",
            "warning": "적격 원장 차분만 채점. 기존분은 채점 구간 전체 수주총액 불변 표본에 한정. 실제 매출·정정 전 빈티지 정답 없음; 생존 계약 선택 편향 및 중첩 표본 존재.",
            "score_scope": "cumulative_horizon_errors; overlapping_origins_and_contracts_not_independent",
            "existing_backlog": {"scores_by_currency": score_records(existing), "records": existing},
            "total_with_new_orders": {"scores_by_currency": score_records(total), "records": total,
                                      "nonzero_new_order_revenue_n": sum(x["predicted_new_order_revenue"] > 0 for x in total)},
            "by_horizon": {str(h): {"existing": score_records([x for x in existing if x["horizon"] == h]),
                                    "total": score_records([x for x in total if x["horizon"] == h])} for h in horizons},
            "annual_FY_plus_2_n": len(annual_total), "annual_FY_plus_2_existing_n": len(annual_existing),
            "annual_FY_plus_2": {
                "existing_backlog": {"records": annual_existing, "scores_by_currency": score_records(annual_existing)},
                "total_with_new_orders": {"records": annual_total, "scores_by_currency": score_records(annual_total)}},
            "rejections": dict(rejects)}


def rounded(obj):
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError("nonfinite output")
        return round(obj, 9)
    if isinstance(obj, dict):
        return {k: rounded(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rounded(x) for x in obj]
    return obj


def audit_markdown(audit):
    lines = ["# KAERO 전수 감사", "", "입력 정규화 원장만 검사했다. 원본 DART 표·단위 캡션은 제공되지 않았다. 금액은 LOGIC §1의 통화별 백만 단위를 유지하며 환산하지 않는다.", "",
             f"{audit['input_companies']}사 · {audit['source_checks']['report_records']} 분기레코드 · 전 기간 계약행 {audit['source_checks']['contract_ledger_rows_all_quarters']}개 · 기준분기 {audit['source_checks']['contract_ledger_rows_origin']}개.", "",
             "|회사|분기|전체/최신 행|집계행/집계표|상태|막는 것|", "|---|---:|---:|---:|---|---|"]
    for c in audit["companies"]:
        reasons = "; ".join(REASONS.get(x, x) for x in c["reason_codes"]) or "조건부 원장 추정 가능"
        lines.append(f"|{c['company_id']} {c['company_name']}|{c['quarter_count']}|{c['row_count']}/{c['latest_row_count']}|{c['aggregate_row_count']}/{c['aggregate_table_count']}|{c['estimate_status']}|{reasons}|")
    lines += ["", "full은 잔고분·신규분의 조건부 원장 추정이 모두 있다는 뜻이다. 재무제표 매출·회사의 전체 사업 범위·납기/생산량 확정을 뜻하지 않는다.", "",
              "## 문서 요약과 입력의 차이", "",
              f"제공 coverage_years의 비결측 {audit['source_checks']['supplied_coverage_samples']}사 중앙값은 {audit['source_checks']['supplied_coverage_median_years']:.6f}년이다. 3.8년은 이 입력에서 재현되지 않는다. KAI 분모 불일치·제노코 연도 열 의심 때문에 이 값도 모델 공통 상수로 사용하지 않는다.",
              "수시공시는 238건(인수인계 237건). 오르비텍은 원전 용역 행이 잡혀 있고, 아이쓰리시스템에는 지상방산 행이 남았다. 입력은 고치지 않고 추정에서 배제했다. 한화에어로의 쎄트렉아이 포함분과 쎄트렉아이 자체 원장을 업종 합계로 더하지 않는다.", "",
              "## 분기별 날짜·단위·정합성", "", "JSON companies[].quarters에 분기·rcp·행수·날짜 정밀도·금액 등식·상세합계·제외행이 모두 있다.", "",
              "|회사|분기|행|날짜 인식|통화/정규화 단위 인식|등식·부문 문제|", "|---|---|---:|---|---|---|"]
    for c in audit["companies"]:
        for q in c["quarters"]:
            units = ", ".join(f"{k}:{'백만 단위 확인' if v['unit_confirmed'] else '미확정'}" for k, v in q["currency_unit_audit"].items()) or "없음"
            problems = sorted(set(x for v in q["currency_unit_audit"].values() for x in v["reasons"]))
            lines.append(f"|{c['company_id']}|{q['quarter']}|{q['rows']}|{json.dumps(q['dates'], ensure_ascii=False)}|{units}|{'; '.join(problems) or '추가 문제 검출 없음'}|")
    lines += ["", "## 맥미니 추가 수집 작업", "", "아래는 회사×분기별 실행 목록이다. 정확한 필드·섹션·기존 rcp는 kaero_audit.json collection_tasks를 사용한다. P0 기준분기 재검증 → P1 과거/누락 확보 → P2 원문 보강. 공시가 존재하지 않는 분기는 0으로 만들지 않는다.", "",
              "공통 필수: 단위 캡션/행별 통화, 연결·별도/부문, 기초+신규−취소−납품=기말 연결표, 분기/YTD 구분, 결산월, 계약 ID/호기/공정/납기 변경, 외화 주석. 원문에 없는 값은 unavailable로 수집 완료 처리한다.", "",
              "|회사|분기|우선순위|작업|추가 중점|", "|---|---|---|---|---|"]
    for t in audit["collection_tasks"]:
        focus = ("; ".join(t["fields"][4:-2]) or "단위·일정·수주 연결표") + f" / 재확인 행 {len(t['row_reextraction_targets'])}개"
        lines.append(f"|{t['company_id']} {t['company_name']}|{t['quarter']}|{t['priority']}|{t['action']}|{focus}|")
    return "\n".join(lines) + "\n"


def load_context(input_dir):
    """Read supplied data as data only. Definitions never supply model coefficients."""
    registry, metadata = {}, {}
    for key in ("tiers", "domains", "natures"):
        path = input_dir / f"kaero_{key}.json"
        data = json.loads(path.read_text())
        entries = data[key]
        ids = [x["id"] for x in entries]
        if len(ids) != len(set(ids)) or data["n"] != len(ids):
            raise ValueError("invalid dictionary: " + key)
        registry[key] = {x["id"]: x for x in entries}
        metadata[key] = {"source_file": path.name, "entries": entries,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    evidence_file = input_dir / "kaero_unit_evidence.json"
    evidence_data = json.loads(evidence_file.read_text()) if evidence_file.exists() else {}
    contract = evidence_data.get("unit_contract", "")
    # This verifies the supplied contract exists, not the unavailable source code/caption.
    normalization = isinstance(contract, str) and "_UNIT_SCALE" in contract and "백만원" in contract
    return {"registry": registry, "dictionaries": metadata,
            "unit": {"normalization_contract_available": normalization,
                     "supplied_contract": contract, "independently_verified_parser": False,
                     "raw_unit_caption_available": False, "status": "unit_caption_unavailable",
                     "scale_from_input": 1, "currency_conversion": False,
                     "native_units": {"KRW": "KRW_million", "USD": "USD_million"}}}


def prepare_reports(reports, context):
    result = copy.deepcopy(reports)
    reg = context["registry"]
    for co in result["companies"].values():
        for table in co["quarters"].values():
            table["_normalization_verified"] = context["unit"]["normalization_contract_available"]
            for row in table.get("contracts", []):
                domain, nature = row.get("domain"), row.get("nature")
                row["_dictionary_invalid"] = domain not in reg["domains"] or nature not in reg["natures"]
                row["_classification"] = {
                    "domain": reg["domains"].get(domain), "nature": reg["natures"].get(nature),
                    "customer_tiers": [{"name": x.get("name"), "tier": x.get("tier"),
                                        "tier_definition": reg["tiers"].get(x.get("tier")),
                                        "evidence_grade": x.get("grade"),
                                        "issuer_self_reference": x.get("stock") == co["stock"],
                                        "status": "reported_reference" if x.get("tier") in reg["tiers"] else "unknown_customer_tier"}
                                       for x in row.get("customers", [])],
                    "basis": "reported_codes_resolved_against_supplied_dictionaries",
                    "semantic_reclassification": False, "amounts_allocated_by_customer": False}
    return result


def dictionary_audit(input_dir, context):
    fields = {"domain": "domains", "nature": "natures", "tier": "tiers", "party_tier": "tiers"}
    counts, missing, invalid, examples = Counter(), Counter(), [], []
    def visit(obj, pointer, source):
        if isinstance(obj, dict):
            for field, kind in fields.items():
                if field not in obj:
                    continue
                value = obj[field]
                if value is None:
                    missing[field] += 1
                elif value not in context["registry"][kind]:
                    invalid.append({"source_file": source, "pointer": pointer + "/" + field, "value": value})
                else:
                    counts[field + ":" + value] += 1
            # Explicit example of a possible meaning mismatch, not an automatic relabel.
            name = obj.get("name", obj.get("label", ""))
            if obj.get("domain") == "space" and "KF-X" in name and "엔진" in name:
                examples.append({"source_file": source, "pointer": pointer,
                                 "label": name, "reported_domain": "space",
                                 "reason": "KF-X engine wording merits source review; valid code does not prove domain"})
            for key, value in obj.items():
                if key in {"domains", "natures"} and isinstance(value, dict):
                    for code in value:
                        if code not in context["registry"][key]:
                            invalid.append({"source_file": source, "pointer": pointer + "/" + key + "/" + code, "value": code})
                visit(value, pointer + "/" + str(key), source)
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                visit(value, pointer + "/" + str(i), source)
    for name in ("kaero_reports.json", "kaero_contracts.json", "kaero_suppliers.json"):
        visit(json.loads((input_dir / name).read_text()), "", name)
    return {"status": "references_valid" if not invalid else "dictionary_reference_unresolved",
            "known_reference_counts": dict(sorted(counts.items())), "null_reference_counts": dict(missing),
            "unknown_references": invalid, "semantic_review_examples": examples,
            "semantic_verification": "not_verified_without_original_tables",
            "coefficients_inferred_from_dictionary": False}


def attach_industry_axes(company, co, supplier, context):
    table = co["quarters"].get(ORIGIN, {})
    reg = context["registry"]
    axes = company["industry_axes"]
    axes.update({
        "domain_definitions": [reg["domains"].get(k, {"id": k, "status": "dictionary_reference_unresolved"})
                               for k in sorted(table.get("domains", {}))],
        "nature_definitions": [reg["natures"].get(k, {"id": k, "status": "dictionary_reference_unresolved"})
                               for k in sorted(table.get("natures", {}))],
        "domain_basis": table.get("domains_src"),
        "customer_hierarchy": [{"name": x.get("name"), "tier": x.get("tier"),
                                "tier_label": reg["tiers"].get(x.get("tier"), {}).get("ko"),
                                "basis": x.get("basis"), "grade": x.get("grade"),
                                "evidence": x.get("evidence"), "stock": x.get("stock"),
                                "amount_used_in_forecast": False}
                               for x in supplier.get("customers", [])],
        "customer_hierarchy_vintage": "current_supplied_supplier_summary_not_used_in_backtest",
        "parts_and_systems": supplier.get("cats", []),
        "nature_policy": {"RSP": "empirical_program_burn_only_no_forced_expiry",
                          "LTA": "empirical_program_burn_only_no_forced_expiry",
                          "PBL": "service_delivery_proxy_not_airframe_count",
                          "MRO": "service_delivery_proxy_not_airframe_count",
                          "DEV": "development_contract_not_mass_production",
                          "BATCH": "reported_residual_class_not_verified_physical_schedule"},
        "dictionary_validation": "code_membership_only; reported classifications retained",
        "group_aggregation": "disabled_all_companies",
        "company_role_is_customer_tier": False})


def retry_plan(companies, reports, bt):
    longer, structural = [], []
    period = [qadd(LEDGER_TARGET_START, i) for i in range(qnum(ORIGIN) - qnum(LEDGER_TARGET_START) + 1)]
    for c in companies:
        cid = c["company_id"]
        co = reports["companies"][cid]
        entries = []
        for ch in c["currency_panels"]:
            cur = ch["currency"]
            pairs = ch["evidence"]["pairs"]
            other = sorted(set(ch["reason_codes"]) - {
                "unit_caption_unavailable", "insufficient_order_samples", "insufficient_burn_samples",
                "rsp_lta_no_burn_samples", "partial_existing_coverage", "missing_order_duration"})
            rejected = dict(Counter(x for p in pairs for x in p["reason_codes"]))
            n = len(ch["evidence"]["net_order_samples"])
            if n < 4 and any(number(p["delivery_delta"]) for p in pairs):
                entries.append({"component": "new_orders", "currency": cur,
                                "current_eligible_samples": n, "required_eligible_samples": 4,
                                "release_condition": "4 consecutive-pair eligible net-order observations AND full existing coverage AND duration evidence",
                                "other_blockers": other, "rejected_pair_reasons": rejected})
            for model in ch["row_forecasts"]:
                if set(model["reason_codes"]) & {"insufficient_burn_samples", "rsp_lta_no_burn_samples"}:
                    entries.append({"component": "existing_backlog", "currency": cur, "row_id": model["row_id"],
                                    "label": model["label"], "current_eligible_samples": len(model["samples"]),
                                    "required_eligible_samples": 2,
                                    "release_condition": "2 same-identity, same-unit, same-scope nonnegative delivery-rate observations",
                                    "other_blockers": other, "rejected_pair_reasons": rejected})
            codes = sorted(set(ch["reason_codes"]) - {"unit_caption_unavailable", "partial_existing_coverage",
                           "insufficient_burn_samples", "rsp_lta_no_burn_samples", "insufficient_order_samples"})
            if all(p["delivery_delta"] is None for p in pairs):
                codes.append("delivery_missing")
            if codes:
                structural.append({"company_id": cid, "currency": cur, "reason_codes": sorted(set(codes)),
                                   "history_alone_sufficient": False})
        if not c["currency_panels"]:
            structural.append({"company_id": cid, "currency": None, "reason_codes": c["reason_codes"],
                               "history_alone_sufficient": False})
        c["needs_longer_ledger"] = []
        for item in entries:
            task = {"task_id": f"{cid}:{item['currency']}:{item['component']}:{len(c['needs_longer_ledger']) + 1}",
                    "company_id": cid, "company_name": c["company_name"], "reason_code": "needs_longer_ledger",
                    "target_start": LEDGER_TARGET_START, "target_end": ORIGIN, "target_quarter_count": len(period),
                    "quarters_present": sorted(q for q in co["quarters"] if q <= ORIGIN),
                    "quarters_missing": [q for q in period if q not in co["quarters"]],
                    "automatic_unblock": False, **item}
            longer.append(task)
            c["needs_longer_ledger"].append(task["task_id"])
        if entries:
            c["reason_codes"] = sorted(set(c["reason_codes"] + ["needs_longer_ledger"]))
            c["audit_blockers"] = list(c["reason_codes"])
            c["warnings"].append("needs_longer_ledger")
    return {"target_quarters": period, "needs_longer_ledger": longer,
            "structural_or_missing_fields": structural,
            "backtest_after_extension": {"reason_code": "needs_longer_ledger", "scope": "all_20_companies",
                                         "rerun": "rolling_origin_h1_to_h10_and_actual_FY_plus_2",
                                         "required": "eligible training prefixes and complete untouched targets; publication vintages still unavailable",
                                         "automatic_calibration": False},
            "absence_policy": "missing pre-listing reports and invalid pairs remain absent, never zero"}


def build(input_dir):
    universe = json.loads((input_dir / "kaero_universe.json").read_text())
    context = load_context(input_dir)
    reports = prepare_reports(json.loads((input_dir / "kaero_reports.json").read_text()), context)
    contracts = json.loads((input_dir / "kaero_contracts.json").read_text())
    ids = [u["stock"] for u in universe["rows"]]
    if len(set(ids)) != len(ids) or set(ids) != set(reports["companies"]):
        raise ValueError("universe/report company identity mismatch")
    companies = [project_company(reports["companies"][code]) for code in ids]
    bt = backtest(reports)
    suppliers = {c["stock"]: c for c in json.loads((input_dir / "kaero_suppliers.json").read_text())["cos"]}
    for c in companies:
        attach_industry_axes(c, reports["companies"][c["company_id"]], suppliers.get(c["company_id"], {}), context)
    retry = retry_plan(companies, reports, bt)
    audit = make_audit(universe, reports, contracts, companies)
    previous = json.loads((input_dir / "kaero_audit.json").read_text())
    prior = {c["company_id"]: c for c in previous["companies"]}
    audit["round1_comparison"] = [{"company_id": c["company_id"], "previous_status": prior[c["company_id"]]["estimate_status"],
                                  "current_status": c["estimate_status"],
                                  "resolved_reason_codes": sorted(set(prior[c["company_id"]]["reason_codes"]) - set(c["reason_codes"])),
                                  "added_reason_codes": sorted(set(c["reason_codes"]) - set(prior[c["company_id"]]["reason_codes"]))}
                                 for c in companies]
    audit["dictionary_audit"] = dictionary_audit(input_dir, context)
    audit["unit_contract"] = context["unit"]
    audit["retry_plan"] = retry
    for c in companies:
        cid = c["company_id"]
        c["backtest_summary"] = {"existing_n": sum(x["company_id"] == cid for x in bt["existing_backlog"]["records"]),
                                 "total_n": sum(x["company_id"] == cid for x in bt["total_with_new_orders"]["records"]),
                                 "nonzero_new_order_revenue_n": sum(x["company_id"] == cid and x["predicted_new_order_revenue"] > 0 for x in bt["total_with_new_orders"]["records"]),
                                 "existing_scores_by_currency": score_records([x for x in bt["existing_backlog"]["records"] if x["company_id"] == cid]),
                                 "annual_FY_plus_2_n": sum(x["company_id"] == cid for x in bt["annual_FY_plus_2"]["total_with_new_orders"]["records"]),
                                 "small_sample": True, "calibrated": False}
    counts = Counter(c["estimate_status"] for c in companies)
    panel = {"schema_version": "kaero-r2-kce-r4-compatible", "assignment": "ARGUS-kaero-round2", "origin": ORIGIN,
             "money_unit": "native_currency_million_no_cross_currency_scalar", "numeric_decimal_places": 9,
             "fiscal_year_end_month": 12, "fiscal_basis": "assumed_December_close_unverified",
             "forecast_quarters": [qadd(ORIGIN, h) for h in range(1, 11)], "companies": companies,
             "population": {"input_entries": len(ids), "input_companies": len(ids), "listed_companies": len(ids),
                            "estimated_companies": counts["full"] + counts["partial"], "unestimated_companies": counts["unavailable"],
                            "full_forecast_companies": counts["full"], "status_counts": dict(counts)},
             "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(input_dir.iterdir()) if p.is_file()},
             "engine_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "adapter_basis": "KCE company/scenarios/quarterly/annual skeleton retained; native currency_panels extension; no KCE import",
             "backtest": bt, "unlisted_reference": [], "reason_dictionary": REASONS,
             "unit_contract": context["unit"], "unit_status": "unit_caption_unavailable",
             "industry_dictionaries": context["dictionaries"], "dictionary_audit": audit["dictionary_audit"],
             "retry_plan": retry, "round1_comparison": audit["round1_comparison"],
             "note": "민감도 범위이며 통계적 신뢰구간 아님; 원장 대용치. 다통화 회사의 scalar는 null. 회사 간 업종 합계 없음."}
    return rounded(panel), rounded(audit)


def report_markdown(panel, audit):
    def fmt(value):
        return f"{value:,.6f}".rstrip("0").rstrip(".") if number(value) else "—"
    def pct(value):
        return f"{100 * value:.2f}%" if number(value) else "—"
    def safe(value):
        return str(value).replace("|", " / ").replace("\n", " ")
    pop, bt, retry = panel["population"], panel["backtest"], panel["retry_plan"]
    lines = ["# ARGUS-kaero 2차 감사·전수 추정", "",
        f"기준 2026Q2. **추정 {pop['estimated_companies']}사(전체 구성 {pop['full_forecast_companies']}사·부분 {pop['status_counts'].get('partial', 0)}사) + 미추정 {pop['unestimated_companies']}사 = 입력 {pop['input_companies']}사**.", "",
        "모든 회사에 T+1~T+10(2026Q3~2028Q4), FY2026~FY2028, 보수·기준·낙관 구조를 만들었다. 근거 없는 값은 null이다. 전체 구성(full)은 기존 잔고분과 신규분의 조건부 원장 추정이 모두 있다는 뜻이며, 재무제표 매출 또는 전사 사업 전체를 뜻하지 않는다.", "",
        "## 이번에 연결한 입력과 1차에서 이어 쓴 것", "",
        "`input/kaero_forecast.py`, `input/forecast_section.py`, `input/test_kaero_forecast.py`를 복사해 확장했다. 행 식별·부문 차단·RSP/LTA 소진·신규 코호트·불완전 연간·민감도 로직은 이어 썼다. `input/kaero_audit.json`과 회사별 판정을 직접 비교했다. 이전 감사는 현재 판정을 강제하는 정답으로 사용하지 않았다.", "",
        "새 사전은 계층 4개·영역 6개·성격 6개다. 정기보고서·수시계약·공급망의 코드 참조와 null 계층을 전수 검사하고, 행과 HTML의 표시명·근거에 연결했다. 사전에 없는 성격/영역은 해당 행 추정을 차단한다. 계층 이름으로 생산률·수주 성장률을 만들지 않는다.", "",
        f"사전에 없는 비결측 참조 {len(panel['dictionary_audit']['unknown_references'])}건. null 계층은 {json.dumps(panel['dictionary_audit']['null_reference_counts'], ensure_ascii=False)}이며 추정으로 메우지 않았다. 코드 존재는 원문 의미의 정확성을 보장하지 않는다. 예: 수시공시 `KF-X 체계개발 엔진(Engine)`의 입력 영역은 space다. 이를 의미 재검토 대상으로 남겼고 계약공시 금액을 전망에 넣지 않았다.", "",
        f"원장은 2025Q1~2026Q2 최대 6분기, 회사별 1~6분기, {audit['source_checks']['report_records']}개 분기 레코드다. 전 기간 계약행 {audit['source_checks']['contract_ledger_rows_all_quarters']}개, 기준분기 {audit['source_checks']['contract_ledger_rows_origin']}개, 수시공시 {audit['source_checks']['announcement_rows']}건. 19분기 자료는 이번 입력에 없으며 수집 중이라는 사용자 설명과 구분했다.", "",
        "1차 대비 full/partial/unavailable 회사 수와 회사별 판정은 동일하다. 사전 공백은 해소됐지만 적격 표본·단위 캡션·기간·부문·계약 연결의 공백은 남았다. 변경 비교는 `forecast_panel.json.round1_comparison`, 상세 재감사는 `kaero_audit.json`에 있다.", "",
        "## 단위·집계 경계", "",
        "금액 상태는 **unit_caption_unavailable**이다. 제공된 `kaero_unit_evidence.json`의 `kce_parse._UNIT_SCALE` 정규화 계약을 KRW 백만원의 근거로 사용했다. USD는 제공된 `kaero_LOGIC.md` §1의 통화별 백만 단위를 유지한다. 파서 실제 코드·원문 표·캡션은 이번에 확인하지 못했다. 입력 배수는 1이며 이미 정규화된 값에 다시 배수를 적용하지 않는다.", "",
        "KRW와 USD의 잔고·납품·추정을 환산하거나 합산하지 않았다. 복수통화 아스트의 회사 단일 금액은 null이다. 계열 중복을 막기 위해 회사 간 업종 금액 합계 자체를 만들지 않았다. 한화에어로 원장에 포함된 쎄트렉아이와 쎄트렉아이 자체 원장은 각각 회사 패널에만 남는다. 수시공시는 정기보고서 잔고에 더하지 않는다.", "",
        "## 산업 축과 계산", "",
        "- 영역: 민수 기체구조물·항공엔진·MRO·방산 항공·우주·기타/미상. 입력 문구의 분류를 유지하고 정의를 붙였다.",
        "- 성격: RSP·LTA는 최소 2개 유효 납품속도 표본으로만 소진한다. 종료일까지 전액 소진시키지 않는다. PBL/MRO는 서비스 대용치, DEV는 개발계약으로 표시한다.",
        "- 고객: OEM·Tier-1·국내 체계업체·정부 계층과 매출처/수주표/계약/본문 근거 등급을 보존한다. 현시점 공급망 요약은 과거 백테스트의 학습에 사용하지 않는다.",
        "- 기종·계통·장납기: 제공 부품 분류와 원장 문구, 수주일·납기의 정밀도를 표시한다. 호기·shipset·공정단계·물리적 생산률은 null이다. 원장 금액의 납품속도를 물리적 생산량으로 해석하지 않는다.",
        "- 환: 원통화를 분리하고 환율·환헤지 가정을 넣지 않는다.", "",
        "기존분은 유효 과거 납품 차분/직전 잔고 비율 r의 중앙값으로 B·r·(1−r)^(h−1)을 계산한다. 적격 속도가 부족한 일반 계약만 유효 미래 납기까지 잔여기간 균등 분배를 조건부 가정한다. 부문 집계·RSP·LTA에 납기 균등 분배를 강제하지 않는다.", "",
        "신규분 표본은 Δ잔고+Δ누계납품이다. 취소·정정·환영향·재분류가 섞일 수 있는 **순수주 대용치**이며 독립적인 신규 발주 실측이 아니다. 연속 분기, 통화·범위·금액 등식, 비음수 납품 차분을 통과한 표본이 4개 이상이고 기존분 전체 커버리지·인식기간 근거가 있어야 계산한다.", "",
        "|시나리오|순수주 가정|기존분·기간·시차|", "|---|---|---|",
        "|보수|유효 표본 P25, 미래 발주에만 0 하한|세 시나리오 동일|",
        "|기준|유효 표본 P50, 미래 발주에만 0 하한|세 시나리오 동일|",
        "|낙관|유효 표본 P75, 미래 발주에만 0 하한|세 시나리오 동일|", "",
        "음수 순수주 원관측은 삭제하지 않는다. 분기말 수주 코호트를 공시 비RSP 계약기간 중앙값(없으면 집계 납품률 역수라는 명시적 가정)에 걸쳐 균등 인식한다. 그래서 **적격 신규분의 T+1은 0**, 표본 부족 신규분의 T+1은 null이다. 계절조정은 적용하지 않는다. 시나리오가 같아지는 경우도 입력과 0 하한의 결과이며 인위적으로 벌리지 않는다.", "",
        "민감도는 모두 **calibrated=false**, nominal_level=null이다. 기존분 속도의 관측 최소~최대 연속 구간(내부 극값 포함), 날짜 ±92일 또는 연도 정밀도 ±365일, 신규 순수주 P10~P90·기간 ±25%·추가 지연 0~1분기를 사용한다. 임의 스트레스 폭이지 확률구간이 아니다. 연간 범위는 분기별 한계값 합으로 보수적인 외곽 구간이며 같은 경로에서 동시에 실현된다는 뜻이 아니다.", "",
        "FY2026은 유효 Q1·Q2 원장 차분 + Q3·Q4 추정이다. 관측분을 연율화하지 않는다. 쎄트렉아이의 2026Q1 누계 납품 감소는 제외하므로 분기 full이어도 FY2026 전체는 null이다. FY2027·FY2028은 미래 4분기의 합이다. 결산월은 12월 가정이며 원공시로 미확인이다.", "",
        "## 20사 전수 결과", "",
        "아래 금액은 기준 시나리오 2026Q3의 잔고분이다. ‘일부’는 전체 잔고·회사 매출이 아니다. KRW=백만원, USD=백만달러, 공통 unit_caption_unavailable. 상세 10개 분기와 3개 연도·세 시나리오는 JSON 및 가능한 회사의 `sections/<종목>.html`에 있다.", "",
        "|회사|판정|통화: T+1 잔고분|적격 순수주 표본|주요 사유 코드|", "|---|---|---|---|---|"]
    for c in panel["companies"]:
        values, samples = [], []
        for ch in c["currency_panels"]:
            row = ch["scenarios"]["base"]["quarterly"][0]
            value = row["existing_backlog_revenue"]
            part = not number(value)
            if part:
                value = row["covered_sites_partial_revenue"]
            values.append(ch["currency"] + ": " + fmt(value) + (" 일부" if part and number(value) else ""))
            samples.append(ch["currency"] + ": " + str(len(ch["evidence"]["net_order_samples"])))
        codes = [x for x in c["reason_codes"] if x != "unit_caption_unavailable"]
        lines.append(f"|{c['company_id']} {c['company_name']}|{c['estimate_status']}|{'; '.join(values) or '—'}|{'; '.join(samples) or '—'}|{'; '.join(codes) or '조건부 전체 구성 가능'}|")
    lines += ["", "## 전체 구성 가능 회사의 연간 시나리오", "",
              "모두 KRW 백만원, unit_caption_unavailable. —는 미추정이다. 연간 잔고분·신규분·관측분의 개별 값과 민감도 범위는 JSON에 있다.", "",
              "|회사|시나리오|FY2026|FY2027|FY2028|분기 순수주 가정|", "|---|---|---:|---:|---:|---:|"]
    for c in panel["companies"]:
        if c["estimate_status"] != "full":
            continue
        for name, sc in c["scenarios"].items():
            values = '|'.join(fmt(x['value']) for x in sc['annual'])
            lines.append(f"|{c['company_name']}|{name}|{values}|{fmt(sc['assumptions']['new_orders_per_quarter'])}|")
    lines += ["", "## 백테스트: 계산 가능 범위와 한계", "",
              "각 원점에서 그 분기 이하 입력만 잘라 다시 적합했다. h=1~10의 **누적 납품** 오차를 채점하며 통화를 분리한다. 기존 잔고분 정답은 원점부터 목표까지 계약 식별자·단위·등식이 유효하고 총계약액이 불변인 행의 누계 납품 차분이다. 신규분 포함 총액은 적격 집계 차분을 정답으로 삼는다. 실제 재무제표 매출을 채점하지 않았다.", "",
              "원공시·정정 전 빈티지가 없으므로 공시시점 투자전략 백테스트가 아니다. 채점 가능 계약만 남기는 선택 편향, 중첩 원점·기간, 적은 회사 수가 있다. 수주총액이 바뀐 행 등은 점수를 조작해 맞추지 않고 제외 사유를 집계했다.", "",
              "|대상·통화|표본|회사 수|MAE(해당 통화 백만)|WAPE|동일 비교 표본|모델 WAPE|직전 납품 유지 WAPE|", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for group, label in (("existing_backlog", "기존 잔고분"), ("total_with_new_orders", "신규분 포함 총액")):
        for cur, score in bt[group]["scores_by_currency"].items():
            lines.append(f"|{label} {cur}|{score['n']}|{score['company_count']}|{fmt(score['mae'])}|{pct(score['wape'])}|{score['paired_naive_n']}|{pct(score['paired_model_wape'])}|{pct(score['paired_naive_wape'])}|")
    lines += ["", "WAPE는 Σ|예측−실제|/Σ|실제|다. 서로 다른 길이의 누적 오차를 모은 위 집계는 참고용이며, 기간별 수치는 다음 표와 `backtest.by_horizon`으로 분리했다. **기존 잔고분 모델은 KRW·USD 모두 동일 표본의 단순 기준보다 나빴다.** 검증 우위를 주장하지 않는다.", "",
              f"신규분 포함 총액 표본은 {len(bt['total_with_new_orders']['records'])}개이며 예측 신규분이 0보다 큰 표본은 {bt['total_with_new_orders']['nonzero_new_order_revenue_n']}개다. 이 점수로 신규수주 모델의 예측력을 검증했다고 말할 수 없다. FY+2 총액 표본 {bt['annual_FY_plus_2_n']}개, 기존분 표본 {bt['annual_FY_plus_2_existing_n']}개. 합성 테스트 표본은 이 점수에 들어가지 않는다.", "",
              "|누적 기간|기존분 KRW n / WAPE|기존분 USD n / WAPE|총액 n|", "|---|---|---|---:|"]
    for h, group in bt["by_horizon"].items():
        cols = [f"{group['existing'].get(cur, {}).get('n', 0)} / {pct(group['existing'].get(cur, {}).get('wape'))}" for cur in ("KRW", "USD")]
        lines.append(f"|T+{h}|{cols[0]}|{cols[1]}|{sum(s['n'] for s in group['total'].values())}|")
    lines += ["", "제외·계산불가 횟수(서로 다른 단위의 시도이므로 표본과 직접 합산하지 않음): `" + json.dumps(bt['rejections'], ensure_ascii=False) + "`.", "",
              "## needs_longer_ledger — 확장 원장 도착 후 재실행", "",
              f"목표는 **2021Q4~2026Q2 19분기**다. `forecast_panel.json.retry_plan.needs_longer_ledger`에 회사·통화·구성요소·행 식별자별 {len(retry['needs_longer_ledger'])}건을 저장했다. 달력상의 분기 수가 아니라 적격 관측 개수로 다시 판정한다. 목록의 `other_blockers`와 `rejected_pair_reasons`도 확인해야 한다.", "",
              "|회사|통화|구성요소·행|현재 적격 표본/필요|추가 차단 사유|", "|---|---|---|---:|---|"]
    for t in retry['needs_longer_ledger']:
        lines.append(f"|{t['company_id']} {t['company_name']}|{t['currency']}|{safe(t['component'] + ': ' + t.get('label', ''))}|{t['current_eligible_samples']}/{t['required_eligible_samples']}|{safe('; '.join(t['other_blockers']) or '적격 추가 관측 필요')}|")
    lines += ["", "백테스트는 20사 전체에 대해 확장 입력으로 재실행한다. 이번 코드가 T+1~T+10과 실제 FY+2 목표연도의 네 분기만 채점하므로 19분기가 들어와도 결과를 0으로 고정하지 않는다. 다만 적격 원점·표적 부족, 신규수주 인식 0, 원공시 빈티지 부재는 계속 남을 수 있다. 원장이 늘어도 자동으로 calibrated=true가 되지 않는다.", "",
              "## 분기 확장만으로 해소되지 않는 항목", "",
              "- 켄코아: 혼합 USD·천원 행별 단위가 필요하다. 정규화 계약만으로 혼합통화를 분리하지 않는다.",
              "- KAI·대한항공·케이앤에스아이앤씨 등: 항공 범위와 일치하는 잔고·납품 연결, 부문 분해가 필요하다.",
              "- 나라스페이스: 현재 4분기이며 집계 누계납품이 null이다. 과거 분기 수만 늘려서는 신규수주를 해제할 수 없다. 같은 범위의 납품·수주 연결표가 추가돼야 한다.",
              "- 수주표/금액 없는 케이피항공산업·컨텍·비츠로넥스텍·삼양컴텍: 부재를 0으로 바꾸지 않는다.",
              "- 아스트 USD 등식·행합 오류, 루미르 등식 불일치, 스피어 중복 식별자, 제노코·아이쓰리시스템·오르비텍 부문 혼입: 원문·계약 ID·범위의 재검증이 필요하다. 원장은 수정하지 않았다.",
              "- 이노스페이스 상세합은 보고 잔고보다 1백만원 크고 케일럼은 1백만원 작다. 1차의 행당 고정 반올림 허용오차 범위로 보존했으므로 커버리지 비율이 미세하게 100%를 넘을 수 있다. 숫자를 억지로 맞추지 않았다.",
              "- 모든 회사의 원문 단위 캡션, 결산월, 확정 콜오프/프로그램 예상 총액 구분, 물리적 일정·수량·생산률·헤지·정정 전 빈티지는 미확인이다.", "",
              "구조적·필드 공백은 `retry_plan.structural_or_missing_fields`, 회사×19분기 수집표는 `kaero_audit.json.collection_tasks` 380건에 별도로 기록했다. 이는 수집 요청 데이터이며 이 작업에서 실행하지 않았다. 상장 전·공시 의무 전 부재도 absent_not_zero로 남겨야 한다.", "",
              "## 재현·검증·통합", "",
              "Python 표준 라이브러리만 사용한다. 입력 JSON/문서는 명령으로 실행하지 않으며 HTML은 inline SVG와 기본 details만 사용한다. 외부 패키지·CDN이 없다.", "",
              "```sh\npython3 -B output/kaero_forecast.py\npython3 -B output/forecast_section.py\npython3 -B -m unittest discover -s output -p 'test_kaero_forecast.py' -v\n```", "",
              "시험은 분해 합계·잔고 보존·단위와 혼합통화 차단·시나리오 순서·미래정보 차단·원시 관측에서 백테스트 점수 재계산·사전/정규화 계약 누락 차단·19분기 합성 경로에서 실제 FY+2 채점·HTML 외부 자산/식별자·입력 해시 불변을 검사한다. 실제 실행 결과는 `validation.json`과 `test_results.txt`에 남긴다.", "",
              "렌더러 통합 함수는 `render_forecast_section({'stock': code, 'co': name, 'src': 'kaero_reports'}, forecast_entry)`다. 회사 식별자·이름·출처가 어긋나면 차단한다. 가능한 10사만 `sections/`에 저장하고 미추정 회사도 JSON 전수 목록에는 남긴다.", "",
              "입력별 SHA-256은 forecast_panel.json과 input_manifest.json에 있다. 변경은 output/로 제한했다. 추적 preflight는 제공된 AGENTS 절차에 따라 한 번 실행했으나 central_connection_failed였다. 중앙 연결 성공·claim 확보를 주장하지 않으며 재시도하지 않았다. 로컬 task_claim.json에 고립된 작업 범위를 기록했다. 시장/DART 네트워크 조회, 원본 수정, 배포, 메시지 전송, 인증·자격증명 접근, 하위 fleet 실행은 하지 않았다.", ""]
    return '\n'.join(lines)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=root / "input")
    parser.add_argument("--output-dir", type=Path, default=root / "output")
    args = parser.parse_args()
    if args.input_dir.resolve() == args.output_dir.resolve() or args.input_dir.resolve() in args.output_dir.resolve().parents:
        raise ValueError("outputs must not modify input/")
    panel, audit = build(args.input_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("forecast_panel.json", panel), ("kaero_audit.json", audit)):
        (args.output_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (args.output_dir / "kaero_AUDIT.md").write_text(audit_markdown(audit))
    (args.output_dir / "kaero_REPORT.md").write_text(report_markdown(panel, audit))
    print(json.dumps({"population": panel["population"], "source_checks": audit["source_checks"],
                      "backtest_existing": panel["backtest"]["existing_backlog"]["scores_by_currency"],
                      "backtest_total": panel["backtest"]["total_with_new_orders"]["scores_by_currency"],
                      "collection_tasks": len(audit["collection_tasks"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
