#!/usr/bin/env python3
"""Offline KNUKE ledger forecasts, audit and rolling-origin validation.

Only Python's standard library. Does not import or execute input code.
Round 2 extends the supplied round-1 engine. Amounts require the supplied
company-quarter captions and normalization contract; no second scaling or FX.
Caption-to-table locations and DART HTML are not independently verified.
"""
import argparse
import calendar
import copy
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
SCENARIOS = {"conservative": .25, "base": .50, "optimistic": .75}
MONEY = "KRW_million"
ORIGIN = "2026Q2"
MIN_RATES = 2
MIN_ORDERS = 4
INFORMATIONAL_REASONS = {"ledger_not_company_revenue", "raw_caption_absent", "scope_unknown", "ytd_inferred",
                         "power_scope_unidentified", "regional_leadtime_unidentified", "date_range_recovered",
                         "caption_table_mapping_unverified", "unit_recovered_from_supplied_evidence"}
REASONS = {
    "needs_longer_ledger": "기존 범위·행ID를 유지한 원장 확장 후 적격 표본 재검사 필요; 자동 해제 보장 아님",
    "caption_table_mapping_unverified": "회사·분기 캡션과 정규화 계약 제공; 개별 표 위치·HTML 대응은 미검증",
    "unit_recovered_from_supplied_evidence": "같은 회사·분기의 단일 원화 단위 캡션과 정규화 계약으로 금액 조건부 허용",
    "new_order_driver_unidentified": "날짜 계약·O&M·배분 불가 행은 신규수주 전환모형 추가 근거 필요",
    "missing_origin": "기준분기 원장 없음",
    "unit_unverified": "해당 표 단위 미확인: 금액 차단",
    "foreign_currency": "외화 원장: 원화 환산 금지, 외화 배율 원문 재수집 필요",
    "no_order_rows": "수주 원장 행 없음",
    "aggregate_excluded": "합계·소계는 대조용이며 개별행 합산에서 제외",
    "duplicate_identity": "동일 이름·상대·계약일 중복: 임의 순번 연결 금지",
    "grouped_contracts": "여러 계약 묶음: 대표 시작·종료일을 단일 호기 일정으로 사용 불가",
    "identity_conflict": "계약총액−누계납품−잔고 불일치",
    "dates_missing": "개별 계약의 정확한 시작·종료일 없음",
    "date_range_recovered": "입력 기간 문자열의 두 날짜에서 실제 서비스 기간 복원",
    "date_precision_year_only": "연도만 있는 날짜: 임의 월일 배분 금지",
    "date_raw_conflict": "정규화 날짜와 원시 날짜 불일치",
    "expired_positive_backlog": "종료일 경과 후 양의 잔고: 전액 인식·자동 연장 금지",
    "insufficient_burn_samples": "동일 행·범위의 적격 분기 소진율 2개 미만",
    "insufficient_order_samples": "행 구성이 같은 적격 신규수주 표본 4개 미만",
    "new_order_model_unavailable": "신규수주 금액·전환 근거 부족: 0으로 대입하지 않음",
    "partial_backlog_coverage": "미배분 잔고가 있어 원장 전체 잔고분은 미추정",
    "scope_unknown": "별도·연결 범위 미확인: 제공 수주 원장 범위만 해석",
    "scope_transition": "기간 간 별도·연결 범위 표기 변경: 경계를 넘는 차분 제외",
    "raw_caption_absent": "단위 캡션 원문 미제공: unit_seen과 정규화 계약에 조건부 의존",
    "ledger_not_company_revenue": "수주 원장 대용치이며 회사 전체 회계매출이 아님",
    "power_scope_unidentified": "비발전·미분류 사업 혼재: 원전 순수 매출로 합산 불가",
    "missing_operating_unit_driver": "가동호기·계속운전·정비주기 자료 없음: O&M 갱신수주 미추정",
    "missing_observed_calendar_quarter": "연간 합산에 필요한 과거 분기 원장 납품액 없음",
    "backlog_reconciliation": "원장 잔고 합계와 보존행 합계 대조 실패",
    "reported_backlog_total_missing": "보고서 총잔고 값 없음: 행 합계로 빈 총잔고를 대체하지 않음",
    "negative_delivery_revision": "누계 납품 감소를 수정·퇴출 가능성으로 보존, 적합에서 제외",
    "ytd_inferred": "연초 리셋과 연중 단조 증가로 누적 기준 추론: 원문 열 제목 재확인 필요",
    "regional_leadtime_unidentified": "지역별 잔고·납품 연결 없음: 국내외 공기를 가중 혼합하지 않음",
}


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def quantile(xs, p):
    xs = sorted(x for x in xs if number(x))
    if not xs:
        return None
    pos = (len(xs) - 1) * p
    lo = int(pos)
    return xs[lo] + (xs[min(lo + 1, len(xs) - 1)] - xs[lo]) * (pos - lo)


def qnum(q):
    if not re.fullmatch(r"\d{4}Q[1-4]", q):
        raise ValueError("invalid quarter: " + q)
    return int(q[:4]) * 4 + int(q[-1]) - 1


def qadd(q, h):
    n = qnum(q) + h
    return f"{n // 4}Q{n % 4 + 1}"


def qend(q):
    y, m = int(q[:4]), int(q[-1]) * 3
    return date(y, m, calendar.monthrange(y, m)[1])


def parse_date(x):
    if not isinstance(x, str) or not re.fullmatch(r"\d{4}[-.]\d{2}[-.]\d{2}", x.strip()):
        return None
    try:
        return date.fromisoformat(x.strip().replace(".", "-"))
    except ValueError:
        return None


def compact(x):
    return re.sub(r"\s+", "", x or "")


def aggregate(r):
    return compact(r.get("label") or r.get("name")) in {"합계", "총계", "소계", "계", "합계(총계)"}


def row_key(r):
    # No fuzzy name matching, no row-number identity, no cross-company joins.
    fields = [r.get("name") or r.get("label"), r.get("client"), r.get("start_raw") or r.get("start")]
    return "|".join(compact(x) for x in fields)


RAW_KRW_SCALES = {"십억원": 1000, "백만원": 1, "억원": 100, "천원": .001,
                  "만원": .01, "원": .000001}


def unit_decision(s):
    context = s.get("_unit_context", {})
    captions = context.get("raw_unit_captions", [])
    tokens = {compact(t) for caption in captions for t in re.split(r"[,;()/：:]", caption)}
    units = sorted(tokens & RAW_KRW_SCALES.keys())
    foreign = any(re.search(r"USD|달러|\$|EUR|유로|JPY|엔화|CNY|위안", c, re.I) for c in captions)
    codes = []
    if not context.get("normalization_contract_supported"):
        codes.append("normalization_contract_missing")
    if not units:
        codes.append("monetary_caption_missing")
    if foreign:
        codes.append("foreign_or_mixed_caption")
    if s.get("cur") != "KRW":
        codes.append("currency_not_krw")
    if s.get("ok") is not True:
        codes.append("report_not_ok")
    if s.get("unit_from_prev"):
        codes.append("unit_borrowed_from_previous")
    # A missing parser flag may be recovered only from a unique same-quarter
    # monetary unit. An empty caption is preserved, never treated as evidence.
    if s.get("unit_seen") is not True and len(units) != 1:
        codes.append("unrecognized_flag_with_ambiguous_captions")
    allowed = not codes
    return {"money_allowed": allowed, "raw_unit_captions": captions,
            "recognized_krw_units": units, "raw_scales_context_only": {u: RAW_KRW_SCALES[u] for u in units},
            "scale_from_input": 1 if allowed else None,
            "normalization_contract_supported": bool(context.get("normalization_contract_supported")),
            "caption_source": context.get("source"), "table_mapping_verified": False,
            "raw_html_verified": False, "empty_caption_count": captions.count(""),
            "recovered_parser_flag": allowed and s.get("unit_seen") is not True,
            "reason_codes": codes}


def apply_unit_evidence(reports, evidence):
    """Attach data provenance to a copy; never mutate inputs or multiply values."""
    result = copy.deepcopy(reports)
    contract = evidence.get("unit_contract", "")
    supported = all(t in contract for t in ("백만원", "정규화", "_UNIT_SCALE"))
    for stock, company in result["companies"].items():
        for quarter, snapshot in company.get("quarters", {}).items():
            captions = evidence.get("companies", {}).get(stock, {}).get(quarter, [])
            if not isinstance(captions, list) or not all(isinstance(x, str) for x in captions):
                raise ValueError(f"invalid unit captions: {stock}/{quarter}")
            snapshot["_unit_context"] = {"raw_unit_captions": captions,
                "normalization_contract_supported": supported,
                "source": f"knuke_unit_evidence.json#/companies/{stock}/{quarter}"}
    return result


def money_ok(s):
    return unit_decision(s)["money_allowed"]


def region_of(r):
    t = " ".join(str(r.get(k) or "") for k in ("region", "name", "label"))
    if re.search(r"해외|국외|체코|루마니아|UAE|BNPP|요르단|인도\b|사우디|베트남|카타르|미국|OMAN|Oman|쿠웨이트", t, re.I):
        return "export"
    if re.search(r"국내|대한민국|신한울|새울|한울|한빛|월성|고리|당진|신서천|음성|삼척|신호남|신일산|고성|광양|완도|신안|왕신|포항|충청|충남|경상|전남|부산|경남", t):
        return "domestic"
    return "unknown"


def axes(r, role):
    name = r.get("name") or r.get("label") or ""
    if re.search(r"O/H|주기교체", name, re.I) and re.search(r"구매|계측|ICI", name, re.I):
        driver = "operating_fleet_replacement_equipment"
    elif re.search(r"정비|O&M|운영|운전|유지관리|방사선관리|주기적|교정", name, re.I):
        driver = "operating_fleet_service_or_replacement"
    elif re.search(r"설계|인허가|기술용역|문서개발", compact(name)):
        driver = "engineering_contract_schedule"
    elif re.search(r"해체|폐기물|방폐물", name):
        driver = "decommissioning_service_schedule"
    elif role == "main" or re.search(r"NSSS|원자로|터빈|열교환기|HRSG|ICI|계측|케이블|Turbine|Seal|VANE", name, re.I):
        driver = "equipment_delivery_or_newbuild"
    else:
        driver = "reported_segment_turnover"
    systems = [s for s in ("NSSS", "MMIS", "ICI", "CVAP", "HRSG", "EPC", "MACST") if s in name.upper()]
    unit = re.findall(r"(?:신한울|새울|한울|한빛|월성|고리|Dukovany)\s*#?\s*\d+(?:[,·~]\d+)?(?:호기)?", name, re.I)
    return {"driver": driver, "region": region_of(r), "system_tags": systems,
            "unit_mentions": unit, "actual_process_stage": None,
            "stage_basis": "계약명은 업무 유형만 식별; 실제 공정단계·가동호기수 미제공",
            "supplied_domain": r.get("domain"),
            "domain_text_conflict": r.get("domain") == "IND" and bool(re.search(r"UAE.*원전|BNPP", name, re.I))}


def dates(r):
    reasons = []
    a, b = parse_date(r.get("start")), parse_date(r.get("end"))
    raw_a, raw_b = str(r.get("start_raw") or "").strip(), str(r.get("end_raw") or "").strip()
    grouped = bool(re.search(r"등\s*\d+\s*건", r.get("name") or "") or "등" in raw_a or "등" in raw_b)
    if grouped:
        return None, None, ["grouped_contracts"]
    # Explicit two-date service period; a contract signing date can precede service.
    span = re.fullmatch(r"(\d{4}[.-]\d{2}[.-]\d{2})\s*[~～]\s*(\d{4}[.-]\d{2}[.-]\d{2})", raw_b)
    if span:
        x, y = parse_date(span[1]), parse_date(span[2])
        if x and y and x < y and (a is None or a <= x):
            return x, y, ["date_range_recovered"]
        return None, None, ["date_raw_conflict"]
    for raw, normalized in ((raw_a, a), (raw_b, b)):
        exact = parse_date(raw)
        if exact and normalized and exact != normalized:
            return None, None, ["date_raw_conflict"]
        if raw and not exact and raw not in {"-", "—"}:
            reasons.append("date_precision_year_only" if re.fullmatch(r"\d{4}년", raw) else "date_raw_conflict")
    if reasons or a is None or b is None or a >= b:
        return None, None, sorted(set(reasons + ["dates_missing"]))
    return a, b, []


def semantics(history):
    """Classify flow columns only using snapshots available at the origin."""
    snaps = sorted(history.items())
    if snaps and snaps[-1][1].get("shape") == "roll":
        return "ytd_roll", "shape_roll_year_to_date_assumption"
    if snaps and snaps[-1][1].get("shape") == "item":
        rows = [s.get("segments", []) for _, s in snaps]
        dated = any(r.get("start") or r.get("end") for rs in rows for r in rs)
        resets, decreases = 0, 0
        for (pq, p), (q, s) in zip(snaps, snaps[1:]):
            if qadd(pq, 1) != q or not number(p.get("delivered")) or not number(s.get("delivered")):
                continue
            if set(row_key(r) for r in p.get("segments", [])) != set(row_key(r) for r in s.get("segments", [])):
                continue
            if s["delivered"] < p["delivered"]:
                if q.endswith("Q1"):
                    resets += 1
                else:
                    decreases += 1
        if not dated and resets >= 1 and decreases == 0:
            return "ytd_inferred", "annual_reset_plus_monotone_within_year_not_raw_header"
    return "contract_cumulative", "award_or_A_equals_C_plus_B_contract_ledger_proxy"


def normalize_snapshot(s, q, role, sem):
    raw_rows = s.get("segments", [])
    keys = Counter(row_key(r) for r in raw_rows if not aggregate(r))
    result = []
    for i, r in enumerate(raw_rows):
        codes = []
        if aggregate(r):
            codes.append("aggregate_excluded")
        if keys[row_key(r)] > 1:
            codes.append("duplicate_identity")
        a, c, b = (r.get(k) for k in ("gross", "delivered", "closing"))
        derived = []
        conflict = False
        if sem == "contract_cumulative":
            if sum(number(x) for x in (a, c, b)) == 2:
                if not number(a):
                    a = c + b; derived.append("gross")
                elif not number(c):
                    c = a - b; derived.append("delivered")
                else:
                    b = a - c; derived.append("closing")
            if all(number(x) for x in (a, c, b)):
                conflict = min(a, c, b) < 0 or abs(a - c - b) > max(1.01, abs(a) * 1e-6)
                if conflict:
                    codes.append("identity_conflict")
        start, end, date_codes = dates(r)
        codes.extend(date_codes)
        if end and end <= qend(q) and number(b) and b > 0:
            codes.append("expired_positive_backlog")
        if not money_ok(s):
            codes.append("foreign_currency" if s.get("cur") not in (None, "KRW") else "unit_unverified")
        progress = c / a if number(c) and number(a) and a > 0 and not conflict and sem == "contract_cumulative" else None
        result.append({"row_id": hashlib.sha256(row_key(r).encode()).hexdigest()[:16], "key": row_key(r),
                       "row_index": i, "label": r.get("label"), "name": r.get("name"),
                       "client": r.get("client"), "axes": axes(r, role),
                       "is_aggregate": aggregate(r), "grouped": "grouped_contracts" in codes,
                       "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
                       "reported_start": r.get("start"), "reported_end": r.get("end"),
                       "start_raw": r.get("start_raw"), "end_raw": r.get("end_raw"),
                       "gross": a if money_ok(s) else None, "delivered": c if money_ok(s) else None,
                       "backlog": b if money_ok(s) else None, "raw_delivered_present": number(r.get("delivered")),
                       "derived_fields": derived, "progress": progress,
                       "unit_ratio_basis": "same_table_dimensionless_only; no_fx_conversion",
                       "reason_codes": sorted(set(codes))})
    return result


def normalized_history(company, origin):
    history = {q: s for q, s in company.get("quarters", {}).items() if qnum(q) <= qnum(origin)}
    sem, basis = semantics(history)
    norm = {q: normalize_snapshot(s, q, company.get("role"), sem) for q, s in history.items()}
    return history, norm, sem, basis


def eligible_row(r):
    return not any(c in r["reason_codes"] for c in
                   ("aggregate_excluded", "duplicate_identity", "grouped_contracts", "identity_conflict", "unit_unverified", "foreign_currency"))


def matched_deltas(history, norm, sem):
    pairs, excluded = [], Counter()
    for q in sorted(history):
        pq = qadd(q, -1)
        if pq not in history:
            excluded["nonadjacent_or_missing_previous"] += 1; continue
        p, s = history[pq], history[q]
        if not money_ok(p) or not money_ok(s):
            excluded["unit_currency"] += 1; continue
        if p.get("orders_scope") != s.get("orders_scope"):
            excluded["scope_transition"] += 1; continue
        pr = {r["key"]: r for r in norm[pq] if eligible_row(r)}
        cr = {r["key"]: r for r in norm[q] if eligible_row(r)}
        ds = {}
        for key in pr.keys() & cr.keys():
            old, cur = pr[key], cr[key]
            if not old["raw_delivered_present"] or not cur["raw_delivered_present"]:
                excluded["derived_or_missing_delivery"] += 1; continue
            if not number(old["backlog"]) or not number(cur["backlog"]):
                excluded["missing_backlog"] += 1; continue
            delta = cur["delivered"] if sem.startswith("ytd") and q.endswith("Q1") else cur["delivered"] - old["delivered"]
            rate = delta / old["backlog"] if old["backlog"] > 0 else None
            ds[key] = {"quarter": q, "delivery": delta, "rate": rate,
                       "orders": cur["backlog"] - old["backlog"] + delta,
                       "previous_backlog": old["backlog"], "current_backlog": cur["backlog"]}
            if delta < 0:
                excluded["negative_delivery_revision"] += 1
        # All supplied leaf identities must match, not merely the eligible subset.
        pk = [r["key"] for r in norm[pq] if not r["is_aggregate"]]
        ck = [r["key"] for r in norm[q] if not r["is_aggregate"]]
        complete = bool(pk) and len(pk) == len(set(pk)) and set(pk) == set(ck) == set(ds)
        if not complete:
            excluded["incomplete_or_changed_row_set"] += 1
        pairs.append({"quarter": q, "scope": s.get("orders_scope"), "rows": ds, "complete": complete,
                      "delivery": sum(x["delivery"] for x in ds.values()) if complete else None})
    return pairs, dict(excluded)


def term_fraction(start, end, at, gamma=1.):
    return max(0., min(1., (at - start).days / (end - start).days)) ** gamma


def row_path(model, origin, horizons=10, parameter=None):
    b = model["backlog"]
    if model["method"] == "zero_backlog_identity":
        return [0.] * horizons
    if model["method"] == "observed_segment_burn":
        r = model["rate"] if parameter is None else parameter
        return [b * r * (1 - r) ** (h - 1) for h in range(1, horizons + 1)]
    if model["method"] in {"service_term", "engineering_term", "equipment_term", "contract_term"}:
        a, e = parse_date(model["start"]), parse_date(model["end"])
        gamma = 1. if parameter is None else parameter
        f0 = term_fraction(a, e, qend(origin), gamma)
        if f0 >= 1:
            return None
        path = []
        for h in range(1, horizons + 1):
            p = term_fraction(a, e, qend(qadd(origin, h - 1)), gamma)
            v = term_fraction(a, e, qend(qadd(origin, h)), gamma)
            path.append(b * max(0., v - p) / (1. - f0))
        return path
    return None


def build_models(company, origin):
    hist, norm, sem, basis = normalized_history(company, origin)
    pairs, exclusions = matched_deltas(hist, norm, sem)
    current = norm.get(origin, [])
    models = []
    for r in current:
        if r["is_aggregate"]:
            continue
        m = dict(r)
        m["method"] = "unavailable"
        samples = [p["rows"][r["key"]] for p in pairs if r["key"] in p["rows"]
                   and p["scope"] == hist.get(origin, {}).get("orders_scope")]
        rates = [v["rate"] for v in samples if number(v["rate"]) and 0 <= v["rate"] <= 1][-8:]
        m["rate_samples"] = samples
        m["eligible_rate_sample_count"] = len(rates)
        m["rate"] = quantile(rates, .5) if len(rates) >= MIN_RATES else None
        m["rate_range"] = [min(rates), max(rates)] if len(rates) >= MIN_RATES else [None, None]
        if eligible_row(r) and number(r["backlog"]) and r["backlog"] >= 0:
            if r["backlog"] == 0:
                m["method"] = "zero_backlog_identity"
            elif r["start"] and r["end"] and "expired_positive_backlog" not in r["reason_codes"]:
                driver = r["axes"]["driver"]
                m["method"] = ("service_term" if "service" in driver else "engineering_term" if "engineering" in driver
                               else "equipment_term" if "equipment" in driver else "contract_term")
            elif "expired_positive_backlog" not in r["reason_codes"] and number(m["rate"]):
                # O&M bundled rows never reach this route; individual services need a service term.
                if "service" not in r["axes"]["driver"] and company.get("stock") != "051600":
                    m["method"] = "observed_segment_burn"
            if m["method"] == "unavailable":
                code = "insufficient_burn_samples" if len(rates) < MIN_RATES else "new_order_driver_unidentified"
                m["reason_codes"] = sorted(set(m["reason_codes"] + [code]))
        models.append(m)
    return hist, norm, sem, basis, pairs, exclusions, models


def interval(lo=None, hi=None, method="parameter_sensitivity_not_confidence_interval"):
    return {"lower": lo, "upper": hi, "method": method, "nominal_level": None, "calibrated": False}


def sum_known(xs):
    return sum(xs) if xs and all(number(x) for x in xs) else None


def sum_intervals(rows, key):
    return interval(sum_known([(x.get(key) or {}).get("lower") for x in rows]),
                    sum_known([(x.get(key) or {}).get("upper") for x in rows]),
                    "sum_of_quarter_sensitivity_bounds_not_joint_probability")


def timing_evidence(contracts, stock, origin):
    """Context only. Contract amounts are never added to report backlog or O."""
    cutoff = qend(origin)
    available, excluded = [], Counter()
    for c in contracts:
        if c.get("stock") != stock:
            continue
        rcp = c.get("rcp") or ""
        published = parse_date(f"{rcp[:4]}-{rcp[4:6]}-{rcp[6:8]}") if len(rcp) >= 8 else None
        if not published or published > cutoff:
            excluded["publication_after_origin_or_invalid"] += 1; continue
        a, b = parse_date(c.get("start")), parse_date(c.get("end"))
        if not a or not b or b <= a:
            excluded["invalid_period"] += 1; continue
        signed = parse_date(c.get("signed"))
        available.append({"rcp": rcp, "published": published.isoformat(), "name": c.get("name"),
                          "party": c.get("party"), "tier": c.get("tier"), "region": region_of(c),
                          "start": a.isoformat(), "end": b.isoformat(),
                          "duration_quarters": (b - a).days / 91.3125,
                          "signed_to_start_quarters": (a - signed).days / 91.3125 if signed and a >= signed else None,
                          "corrected": bool(c.get("corrected")), "supersedes": c.get("supersedes"),
                          "not_added_to_backlog": True})
    superseded = {r["supersedes"] for r in available if r["supersedes"]}
    available = [r for r in available if r["rcp"] not in superseded]
    buckets = defaultdict(list)
    for r in available:
        buckets[f"{r['tier']}:{r['region']}"].append(r["duration_quarters"])
    return {"purpose": "context_only_no_allocation_without_ledger_join", "publication_cutoff": cutoff.isoformat(),
            "rows": available, "excluded": dict(excluded),
            "by_tier_region": {k: {"n": len(v), "median_quarters": quantile(v, .5),
                                   "min_quarters": min(v), "max_quarters": max(v)} for k, v in sorted(buckets.items())},
            "limitation": "최신 정정본만 남은 계약은 과거 버전 복원 불가. 계약기간은 발주→착공 지연이 아님. 모집단 대표성 없음."}


def annualize(qs, actual, origin, years):
    result = []
    for year in years:
        quarters = [f"{year}Q{i}" for i in range(1, 5)]
        future = [r for r in qs if r["quarter"] in quarters]
        past = [q for q in quarters if qnum(q) <= qnum(origin)]
        observed = sum_known([actual.get(q) for q in past]) if past else 0.
        fv = sum_known([r["value"] for r in future])
        ci = sum_intervals(future, "interval")
        if number(observed) and number(ci["lower"]):
            ci["lower"] += observed; ci["upper"] += observed
        else:
            ci = interval()
        value = observed + fv if number(observed) and number(fv) and len(future) + len(past) == 4 else None
        reasons = sorted(set(c for r in future for c in r["reason_codes"]))
        if not number(observed):
            reasons.append("missing_observed_calendar_quarter")
        result.append({"fiscal_year": year, "value": value,
                       "existing_backlog_revenue": sum_known([r["existing_backlog_revenue"] for r in future]),
                       "covered_sites_partial_revenue": sum_known([r["covered_sites_partial_revenue"] for r in future]),
                       "new_order_revenue": sum_known([r["new_order_revenue"] for r in future]),
                       "observed_revenue": observed, "observed_revenue_basis": "same_ledger_quarter_delivery_proxy_not_financial_statements",
                       "observed_quarters_available": sum(number(actual.get(q)) for q in past),
                       "observed_quarters_required": len(past), "future_quarters": len(future),
                       "complete": number(value), "quarters": quarters,
                       "reason": ";".join(reasons) if reasons else None, "reason_codes": reasons,
                       "component_scope": "future_quarters_only; observed_H1_separate",
                       "interval": ci, "partial_existing_interval": sum_intervals(future, "partial_existing_interval"),
                       "covered_sites_partial_interval": sum_intervals(future, "covered_sites_partial_interval")})
    return result


def forecast_company(meta, company, contracts, origin=ORIGIN, horizons=10):
    stock = meta["stock"]
    company = {**company, "stock": stock, "role": meta.get("role")}
    hist, norm, sem, sem_basis, pairs, exclusions, models = build_models(company, origin)
    s = hist.get(origin, {})
    unit = unit_decision(s)
    reason = ["ledger_not_company_revenue"]
    reason.append("caption_table_mapping_unverified" if unit["raw_unit_captions"] else "raw_caption_absent")
    if unit["recovered_parser_flag"]:
        reason.append("unit_recovered_from_supplied_evidence")
    if not s:
        reason.append("missing_origin")
    if s.get("orders_scope") in (None, "unknown"):
        reason.append("scope_unknown")
    if exclusions.get("scope_transition"):
        reason.append("scope_transition")
    if not money_ok(s):
        reason.append("foreign_currency" if s.get("cur") not in (None, "KRW") else "unit_unverified")
    if not s and hist and hist[max(hist)].get("cur") not in (None, "KRW"):
        reason.append("foreign_currency")
    if not models:
        reason.append("no_order_rows")
    if sem == "ytd_inferred":
        reason.append("ytd_inferred")
    if any(m["axes"]["supplied_domain"] not in {"NUKE", "THERMAL", "RENEW"} for m in models):
        reason.append("power_scope_unidentified")
    if meta.get("role") == "om" or stock == "130660":
        reason.append("missing_operating_unit_driver")
    if models and any(m["axes"]["region"] == "unknown" for m in models):
        reason.append("regional_leadtime_unidentified")
    paths = {m["row_id"]: row_path(m, origin, horizons) for m in models}
    good = [m for m in models if paths[m["row_id"]] is not None]
    leaf_sum = sum_known([m["backlog"] for m in models])
    total = s.get("backlog") if money_ok(s) else None
    reconciliation = number(leaf_sum) and number(total) and abs(leaf_sum - total) <= max(1.01, abs(total) * 1e-6)
    existing_full = bool(models) and len(good) == len(models) and reconciliation
    if not reconciliation and models:
        reason.append("reported_backlog_total_missing" if money_ok(s) and not number(total) else "backlog_reconciliation")
    if not existing_full:
        reason.append("partial_backlog_coverage")
    for m in models:
        if m["method"] == "unavailable":
            reason.extend(m["reason_codes"])
    # New cohorts only for stable product/segment ledgers, with observed own turnover.
    order_pairs = [p for p in pairs if p["complete"] and p["scope"] == s.get("orders_scope")
                   and all(x["delivery"] >= 0 for x in p["rows"].values())][-8:]
    current_keys = {m["key"] for m in models}
    order_pairs = [p for p in order_pairs if set(p["rows"]) == current_keys]
    allow_orders = (existing_full and len(order_pairs) >= MIN_ORDERS
                    and all(m["method"] in {"observed_segment_burn", "zero_backlog_identity"} and number(m["rate"]) for m in models)
                    and meta.get("role") != "om" and stock not in {"051600", "130660"})
    if len(order_pairs) < MIN_ORDERS:
        reason.append("insufficient_order_samples")
    if not allow_orders:
        reason.append("new_order_model_unavailable")
    burn_retry = [m for m in models if m["method"] == "unavailable" and eligible_row(m)
                  and number(m["backlog"]) and m["backlog"] > 0
                  and "expired_positive_backlog" not in m["reason_codes"]
                  and "service" not in m["axes"]["driver"] and stock != "051600"
                  and m["eligible_rate_sample_count"] < MIN_RATES]
    supported_new_driver = bool(models) and all(eligible_row(m) and (
        m["method"] in {"observed_segment_burn", "zero_backlog_identity"} or m in burn_retry)
        for m in models) and meta.get("role") != "om" and stock not in {"051600", "130660"}
    order_retry = supported_new_driver and len(order_pairs) < MIN_ORDERS
    needs_longer = bool(burn_retry or order_retry)
    if needs_longer:
        reason.append("needs_longer_ledger")
    if not allow_orders and models and not supported_new_driver:
        reason.append("new_order_driver_unidentified")
    retry = {"needs_longer_ledger": needs_longer, "target_start": "2021Q4", "target_end": ORIGIN,
             "target_quarter_count": 19, "observed_quarter_count": len(hist),
             "eligible_new_order_sample_count": len(order_pairs), "minimum_new_order_samples": MIN_ORDERS,
             "order_sample_retry": order_retry,
             "burn_rows": [{"row_id": m["row_id"], "name": m["name"],
                            "eligible_samples": m["eligible_rate_sample_count"], "minimum_samples": MIN_RATES}
                           for m in burn_retry],
             "new_order_driver_supported": supported_new_driver,
             "non_length_prerequisites": sorted(set(reason) & {
                 "scope_transition", "reported_backlog_total_missing", "backlog_reconciliation",
                 "new_order_driver_unidentified", "missing_operating_unit_driver", "duplicate_identity",
                 "grouped_contracts", "identity_conflict", "expired_positive_backlog"}),
             "acceptance": "실측만. 동일 회사·연속 분기·같은 행ID·회계범위·확인 단위의 적격 표본. 과거 기간 추가만으로 현재 범위 표본 증가를 보장하지 않음."}
    existing = [sum(paths[m["row_id"]][h] for m in good) for h in range(horizons)] if good else [None] * horizons
    sensitivity_paths = {}
    for m in good:
        if m["method"] == "observed_segment_burn":
            lo, hi = m["rate_range"]
            grid = sorted(set([lo, hi, m["rate"]] + [1 / h for h in range(1, horizons + 1) if lo <= 1 / h <= hi]))
        elif m["method"] == "zero_backlog_identity":
            grid = [None]
        else:
            grid = [.75, 1., 1.25]
        sensitivity_paths[m["row_id"]] = [row_path(m, origin, horizons, p) for p in grid]
        m["sensitivity_parameters"] = grid
    ebounds = [interval(sum(min(p[h] for p in sensitivity_paths[m["row_id"]]) for m in good),
                        sum(max(p[h] for p in sensitivity_paths[m["row_id"]]) for m in good)) if good else interval() for h in range(horizons)]
    actual = {q: None for q in hist}
    for p in pairs:
        if p["complete"]:
            actual[p["quarter"]] = p["delivery"]
    # Roll/YTD Q1 delivery is directly available; requires current unit and all leaf sums.
    if sem.startswith("ytd"):
        for q, snap in hist.items():
            if q.endswith("Q1") and money_ok(snap) and norm[q] and all(eligible_row(r) and r["raw_delivered_present"] for r in norm[q]):
                actual[q] = sum(r["delivered"] for r in norm[q])
    scenarios = {}
    for scenario, percentile in SCENARIOS.items():
        order_models = []
        if allow_orders:
            for m in models:
                signed = [p["rows"][m["key"]]["orders"] for p in order_pairs]
                values = [max(0., x) for x in signed]
                order_models.append({"row_id": m["row_id"], "orders": quantile(values, percentile),
                                     "p10": quantile(values, .1), "p90": quantile(values, .9),
                                     "rate": m["rate"], "rate_range": m["rate_range"],
                                     "negative_order_n": sum(x < 0 for x in signed)})
        quarterly = []
        new_cumulative = 0.
        for h in range(1, horizons + 1):
            new_orders = sum(m["orders"] for m in order_models) if allow_orders else None
            # Quarter-end arrival, own segment geometric turnover from next quarter.
            new_revenue = sum(m["orders"] * (1 - (1 - m["rate"]) ** (h - 1)) for m in order_models) if allow_orders else None
            new_bounds = (sum(m["p10"] * (1 - (1 - m["rate_range"][0]) ** (h - 1)) for m in order_models),
                          sum(m["p90"] * (1 - (1 - m["rate_range"][1]) ** (h - 1)) for m in order_models)) if allow_orders else (None, None)
            if number(new_revenue):
                new_cumulative += new_revenue
            covered = existing[h - 1]
            full_e = covered if existing_full else None
            value = full_e + new_revenue if number(full_e) and number(new_revenue) else None
            full_bounds = interval(ebounds[h - 1]["lower"] + new_bounds[0], ebounds[h - 1]["upper"] + new_bounds[1]) if number(value) else interval()
            block = [] if number(value) else sorted(set(reason))
            quarterly.append({"quarter": qadd(origin, h), "horizon": h, "value": value,
                              "existing_backlog_revenue": full_e, "covered_sites_partial_revenue": covered,
                              "new_order_revenue": new_revenue, "new_orders": new_orders,
                              "new_order_backlog": h * new_orders - new_cumulative if number(new_orders) else None,
                              "existing_remaining_backlog": total - sum(existing[:h]) if existing_full else None,
                              "interval": full_bounds,
                              "partial_existing_interval": ebounds[h - 1] if existing_full else interval(),
                              "covered_sites_partial_interval": ebounds[h - 1],
                              "existing_backlog_method": "sum_of_disjoint_ledger_rows",
                              "status": "conditional_full_ledger_proxy" if number(value) else "partial" if number(covered) else "unavailable",
                              "reason_codes": block})
        scenarios[scenario] = {"assumptions": {
            "new_orders_per_quarter_deseasonalized": sum(m["orders"] for m in order_models) if allow_orders else None,
            "new_orders_per_quarter": sum(m["orders"] for m in order_models) if allow_orders else None,
            "order_level_basis": "unadjusted_empirical_quantile; legacy_deseasonalized_field_is_compatibility_alias_only",
            "money_unit": MONEY if money_ok(s) else None, "order_quantile": percentile,
            "duration_quarters": None, "lag_quarters": None,
            "timing_policy": "same own-segment rates in all scenarios; contract term curves fixed; only order quantiles vary",
            "new_order_recognition": "quarter_end_cohorts_geometric_own_segment_turnover; no_report_contract_amount_addition",
            "unknown_contract_lag": True, "cohort_arrival_convention": "next_quarter_recognition_is_assumption_not_observed_start_lag",
            "seasonality": {"enabled": False, "reason": "fewer_than_two_complete_years_of_eligible_flows"},
            "order_models": order_models,
            "missing_reasons": [] if allow_orders else ["new_order_model_unavailable"]},
            "quarterly": quarterly,
            "annual": annualize(quarterly, actual, origin, [2026, 2027, 2028])}
    has_amount = bool(good)
    status = "full" if allow_orders and existing_full else "partial" if has_amount else "unavailable"
    coverage = {"current_rows": len(models), "monetary_rows": sum(number(m["backlog"]) for m in models),
                "modeled_rows": len(good), "full_existing_coverage": existing_full,
                "full_individual_site_coverage": existing_full and all("term" in m["method"] or m["backlog"] == 0 for m in good),
                "origin_site_total_backlog": total, "modeled_site_backlog": sum(m["backlog"] for m in good) if good else None,
                "unmodeled_site_ids": [m["row_id"] for m in models if m not in good],
                "modeled_backlog_share": sum(m["backlog"] for m in good) / total if good and number(total) and total > 0 else None,
                "leaf_sum": leaf_sum, "backlog_reconciles": reconciliation}
    for m in models:
        m["quarterly"] = [{"quarter": qadd(origin, h), "horizon": h,
                           "revenue": paths[m["row_id"]][h - 1] if paths[m["row_id"]] is not None else None,
                           "remaining_backlog_fraction": 1 - sum(paths[m["row_id"]][:h]) / m["backlog"]
                           if paths[m["row_id"]] is not None and m["backlog"] > 0 else None}
                          for h in range(1, horizons + 1)]
    return {"company_id": stock, "stock": stock, "company_name": meta["name"], "audited_company_name": meta["name"],
            "listed": True, "source": "knuke_reports:" + stock, "origin": origin, "panel_present": bool(s),
            "grade": "supplied_report_ledger", "audited_grade": "conditional_supplied_captions_no_table_html",
            "status": status, "compatibility_status": {"full": "full_ledger_estimate", "partial": "partial_amount_estimate", "unavailable": "unavailable"}[status],
            "reason_codes": sorted(set(reason)),
            "amount_blocking_reason_codes": [c for c in sorted(set(reason)) if c not in INFORMATIONAL_REASONS],
            "audit_blockers": [REASONS.get(c, c) for c in sorted(set(reason)) if c not in INFORMATIONAL_REASONS],
            "limitations": [REASONS.get(c, c) for c in sorted(set(reason)) if c in INFORMATIONAL_REASONS],
            "audit_can": {"matrix": "yes" if has_amount else "no", "trace": "normalized_input_only", "backtest": "proxy_only"},
            "money_unit": MONEY if money_ok(s) else None,
            "scope": "supplied_disjoint_order_ledger; " + str(s.get("orders_scope") or "unknown"),
            "financial_statement_revenue": False, "fiscal_year_end_month": 12, "fiscal_basis": "assumed_December_close_unverified",
            "retry": retry,
            "unit_audit": {**unit, "verified_at_origin": money_ok(s), "raw_verified_at_origin": False,
                           "verification_level": "supplied_company_quarter_captions_and_normalization_contract",
                           "money_unit": MONEY if money_ok(s) else None, "scale_from_input": 1 if money_ok(s) else None,
                           "raw_unit_caption_available": bool(unit["raw_unit_captions"]), "currency": s.get("cur"),
                           "latest_available_currency": hist[max(hist)].get("cur") if hist else None,
                           "unit_basis": "knuke_unit_evidence.json 회사·분기 캡션 + 백만원 정규화 계약; 입력 값 재배율 없음"},
            "coverage": coverage, "evidence": {"delivery_semantics": sem, "delivery_basis": sem_basis,
                "pairs": pairs, "pair_exclusions": exclusions,
                "orders": [{"quarter": p["quarter"], "value": sum(x["orders"] for x in p["rows"].values())} for p in order_pairs],
                "negative_order_proxy_n": sum(x["orders"] < 0 for p in order_pairs for x in p["rows"].values()),
                "order_basis": "B_current-B_previous+quarter_delivery; includes_revisions; negative_retained_then_clipped_only_for_future_cohorts",
                "timing": timing_evidence(contracts, stock, origin)},
            "scenarios": scenarios, "aggregate_forecast": {"site_id": "__ledger_total__", "site_name": "제공 수주 원장",
                "method": "sum_of_disjoint_ledger_rows", "origin_backlog": total,
                "quarterly": [{"quarter": r["quarter"], "horizon": r["horizon"], "progress": None,
                               "revenue": r["existing_backlog_revenue"], "revenue_interval": r["partial_existing_interval"]}
                              for r in scenarios["base"]["quarterly"]]},
            "actual_revenue_proxy": actual, "row_forecasts": models,
            "provenance": {"raw_html_available": False, "historical_revision_versions_available": False,
                           "future_snapshots_excluded": True, "contracts_not_added_to_reports": True}}


def metrics(rows):
    if not rows:
        return {"n": 0, "mae": None, "median_absolute_error": None, "wape_pct": None, "bias_pct": None, "negative_actual_n": 0}
    errs = [r["prediction"] - r["actual"] for r in rows]
    den = sum(abs(r["actual"]) for r in rows)
    return {"n": len(rows), "mae": sum(abs(x) for x in errs) / len(errs),
            "median_absolute_error": statistics.median(abs(x) for x in errs),
            "wape_pct": 100 * sum(abs(x) for x in errs) / den if den else None,
            "bias_pct": 100 * sum(errs) / den if den else None,
            "negative_actual_n": sum(r["actual"] < 0 for r in rows)}


def backtest(universe, reports, contracts):
    rows, full_rows, excluded = [], [], Counter()
    allq = sorted(reports["quarters"])
    for meta in universe:
        c = reports["companies"].get(meta["stock"], {})
        for origin in allq[:-1]:
            if origin not in c.get("quarters", {}):
                excluded["origin_missing"] += 1; continue
            fc = forecast_company(meta, c, contracts, origin)
            for h in range(1, 11):
                target = qadd(origin, h)
                if target not in c.get("quarters", {}):
                    excluded["future_target_unobserved"] += 1; continue
                # Target normalization cannot retroactively change origin parameters.
                th, tn, ts, _ = normalized_history({**c, "role": meta.get("role")}, target)
                tp, _ = matched_deltas(th, tn, ts)
                pair = next((p for p in tp if p["quarter"] == target), None)
                if pair is None:
                    excluded["target_pair_unavailable"] += 1; continue
                target_by_key = {r["key"]: r for r in tn[target] if eligible_row(r)}
                origin_scope = c["quarters"][origin].get("orders_scope")
                target_scope = th[target].get("orders_scope")
                if origin_scope != target_scope:
                    excluded["target_scope_changed"] += 1; continue
                for m in fc["row_forecasts"]:
                    pred = m["quarterly"][h - 1]["revenue"]
                    tr = target_by_key.get(m["key"])
                    if not number(pred):
                        excluded["row_prediction_unavailable"] += 1; continue
                    if tr is None or m["key"] not in pair["rows"]:
                        excluded["row_target_missing_or_identity_changed"] += 1; continue
                    # Existing-only score requires unchanged lifetime contract amount;
                    # delivery including newly awarded work is not its target.
                    if not ("term" in m["method"] and ts == "contract_cumulative"
                            and number(m["gross"]) and number(tr["gross"])
                            and abs(m["gross"] - tr["gross"]) <= max(1.01, abs(m["gross"]) * 1e-6)):
                        excluded["existing_target_scope_changed_or_new_orders_mixed"] += 1; continue
                    rows.append({"company_id": meta["stock"], "origin": origin, "target": target, "horizon": h,
                                 "row_id": m["row_id"], "prediction": pred, "actual": pair["rows"][m["key"]]["delivery"],
                                 "target_basis": "unchanged_gross_matched_contract_quarter_delivery_proxy"})
                pred = fc["scenarios"]["base"]["quarterly"][h - 1]["value"]
                same = {m["key"] for m in fc["row_forecasts"]} == set(pair["rows"])
                if number(pred) and pair["complete"] and same and ts == fc["evidence"]["delivery_semantics"]:
                    full_rows.append({"company_id": meta["stock"], "origin": origin, "target": target,
                                      "horizon": h, "prediction": pred, "actual": pair["delivery"],
                                      "target_basis": "same_segment_ledger_total_quarter_delivery_including_new_orders"})
                else:
                    excluded["total_prediction_or_target_unavailable"] += 1
    bycompany = {}
    for meta in universe:
        s = meta["stock"]
        bycompany[s] = {"existing_contract": metrics([r for r in rows if r["company_id"] == s]),
                        "total_ledger": metrics([r for r in full_rows if r["company_id"] == s])}
    return {"scope": "rolling_report_quarter_origin; delivery_proxy_not_audited_sales",
            "origins": allq[:-1], "money_unit": MONEY, "filled_cells_scored": 0,
            "existing_contract": metrics(rows), "total_ledger": metrics(full_rows),
            "by_horizon": {str(h): {"existing_contract": metrics([r for r in rows if r["horizon"] == h]),
                                   "total_ledger": metrics([r for r in full_rows if r["horizon"] == h])} for h in range(1, 11)},
            "by_company": bycompany, "exclusions": dict(excluded), "calibrated": False,
            "small_sample_warning": f"입력 달력 {len(allq)}분기이며 장기 지평·회사별 표본 희소. 최신 정정 원장, 공시시차를 완전히 복원한 실제 거래시점 검증이 아님. FY2027·FY2028 실측 성적 없음.",
            "publication_policy": "origin report snapshots released after quarter-end; no later-quarter inputs; contracts rcp date <= origin quarter-end; report revision vintages absent",
            "samples": rows, "total_samples": full_rows}


def audit_data(universe, reports, contracts, forecasts):
    result, tasks = [], []
    fcs = {c["company_id"]: c for c in forecasts}
    expected = reports["quarters"]
    for meta in universe:
        stock = meta["stock"]; c = reports["companies"].get(stock, {})
        fc = fcs[stock]
        hist, norm, sem, _ = normalized_history({**c, "role": meta.get("role")}, ORIGIN)
        snapshots = []
        for q in expected:
            s = hist.get(q, {}); rs = norm.get(q, [])
            flags = sorted(set(code for r in rs for code in r["reason_codes"]))
            item = {"quarter": q, "present": q in hist, "ok": s.get("ok"), "rcp": s.get("rcp"),
                    "shape": s.get("shape"), "orders_scope": s.get("orders_scope"), "reported_n_orders": s.get("n_orders"),
                    "rows": len(rs), "aggregate_rows": sum(r["is_aggregate"] for r in rs),
                    "grouped_rows": sum(r["grouped"] for r in rs),
                    "duplicate_rows": sum("duplicate_identity" in r["reason_codes"] for r in rs),
                    "reported_timeline_rows": len(s.get("timeline", [])),
                    "named_client_rows": sum(bool(r.get("client")) for r in rs),
                    "valid_individual_period_rows": sum(bool(r["start"] and r["end"]) for r in rs),
                    "unit_seen": s.get("unit_seen"), "unit_from_prev": s.get("unit_from_prev"),
                    "currency": s.get("cur"), "money_allowed": money_ok(s), "raw_caption_verified": False,
                    "unit_evidence": unit_decision(s),
                    "reported_backlog": s.get("backlog") if money_ok(s) else None,
                    "leaf_backlog_sum": sum_known([r["backlog"] for r in rs if not r["is_aggregate"]]),
                    "revenue_rows": len(s.get("revenue_segments", [])),
                    "revenue_aggregate_rows": sum(compact(r.get("seg")) in {"합계", "총계", "소계"} for r in s.get("revenue_segments", [])),
                    "reason_codes": flags, "row_audit": rs}
            snapshots.append(item)
            need = ["제공 캡션의 수주표 위치·HTML 연결", "A/C/B 열 제목·누적기간·별도/연결/계열 범위", "원문 전체 합계와 보존행 대조"]
            if not s:
                need.append("정기보고서 제출 여부부터 확인; 미제출이면 미제출 근거 기록")
            if not rs:
                need.append("수주표 미공시/보안/추출실패 구분 및 명시적 없음 근거")
            if "duplicate_identity" in flags:
                need.append("병합셀·지역·품목·계약ID 복원: 순번으로 연결하지 말 것")
            if "grouped_contracts" in flags:
                need.append("등 N건의 개별 계약·호기·발주처·기간·잔고; 가동호기·계속운전·정비주기·갱신단가")
            if any(x in flags for x in ("date_range_recovered", "date_raw_conflict", "dates_missing", "expired_positive_backlog", "date_precision_year_only")):
                need.append("계약일/역무시작일/종료일 구분·원시 기간 문자열·변경계약·현재 공정단계·납기")
            if s.get("cur") == "USD":
                need.append("천달러 캡션과 원통화 수주/납품/잔고 원시값; 임의 KRW 환산 금지")
            if stock == "034020":
                need.append("주기기/위탁운영/보증 분리, 국내·체코 등 수출별 수주·납품·공정단계; 2026 parent→unknown 범위 확인")
            if q == "2025Q4":
                need.append("정관/보고서의 회계연도·결산월 확인")
            tasks.append({"stock": stock, "company_name": meta["name"], "quarter": q, "rcp": s.get("rcp"),
                          "priority": "P0" if q == ORIGIN or not s or not money_ok(s) or "grouped_contracts" in flags else "P1",
                          "action": "recollect_or_verify", "required": need,
                          "acceptance": "원문 경로·rcp·절/표·캡션·단위 배율·통화·회계범위·행ID·변경이력 보존; 수정 전후 A=C+B 및 잔고합 대조"})
        for q in [qadd("2021Q4", h) for h in range(19) if qadd("2021Q4", h) not in expected]:
            tasks.append({"stock": stock, "company_name": meta["name"], "quarter": q, "rcp": None,
                          "priority": "P2", "action": "extend_history_if_filed",
                          "required": ["당시 공시 버전의 II-4 수주/납품/부문매출 원문", "동일 범위·단위·계약ID·정정이력", "미제출이면 그 근거"],
                          "reason_code": "needs_longer_ledger" if fc["retry"]["needs_longer_ledger"] else "long_horizon_backtest_history",
                          "acceptance": "실측만, 보간 없음; 기존 원장 접속·범위·단위·적격 표본 수 증가 검증"})
        result.append({"stock": stock, "company_name": meta["name"], "role": meta.get("role"),
                       "status": fc["status"], "reason_codes": fc["reason_codes"], "blockers": fc["audit_blockers"],
                       "amount_blocking_reason_codes": fc["amount_blocking_reason_codes"], "limitations": fc["limitations"],
                       "quarter_count": len(hist), "expected_quarter_count": len(expected),
                       "missing_quarters": [q for q in expected if q not in hist],
                       "row_count": sum(x["rows"] for x in snapshots), "aggregate_rows": sum(x["aggregate_rows"] for x in snapshots),
                       "grouped_rows": sum(x["grouped_rows"] for x in snapshots),
                       "unit_recognized_quarters": sum(x["money_allowed"] for x in snapshots),
                       "retry": fc["retry"],
                       "delivery_semantics": sem, "coverage": fc["coverage"], "quarters": snapshots,
                       "contracts_count": sum(x.get("stock") == stock for x in contracts)})
    univ = {c["stock"] for c in universe}
    orphan = Counter(x.get("stock") for x in contracts if x.get("stock") not in univ)
    return {"schema_version": "knuke-audit-2", "origin": ORIGIN, "input_companies": len(universe),
            "report_companies": len(reports["companies"]), "report_quarters": sum(c["quarter_count"] for c in result),
            "order_rows": sum(c["row_count"] for c in result), "companies": result,
            "population_discrepancies": {"HANDOFF_claimed_companies": 25, "actual_universe_companies": len(universe),
                "HANDOFF_claimed_report_records": 193, "actual_report_records": sum(c["quarter_count"] for c in result),
                "HANDOFF_claimed_contracts": 317, "actual_contracts": len(contracts),
                "contracts_outside_universe": dict(sorted(orphan.items())),
                "contracts_outside_universe_n": sum(orphan.values()), "outside_universe_not_promoted": True},
            "collection_tasks": tasks, "collection_task_count": len(tasks),
            "source_limit": "제공 JSON·회사분기 캡션·정규화 계약으로 재감사. DART 원문 HTML·표 위치 미제공. 과거 완료 주장은 검증 증거가 아님."}


def rounded(x):
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError("non-finite output")
        return round(x, 6)  # Preserve row/component sums within 1e-4 million KRW.
    if isinstance(x, dict):
        return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, list):
        return [rounded(v) for v in x]
    return x


def write_json(path, data):
    path.write_text(json.dumps(rounded(data), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build(input_dir):
    load = lambda name: json.loads((input_dir / name).read_text(encoding="utf-8"))
    u, r, contracts = load("knuke_universe.json"), load("knuke_reports.json"), load("knuke_contracts.json")
    units, prior = load("knuke_unit_evidence.json"), load("knuke_audit.json")
    r = apply_unit_evidence(r, units)
    universe = u["rows"]
    ids = [m["stock"] for m in universe]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate universe stock")
    if set(r["companies"]) - set(ids):
        raise ValueError("report company outside universe requires explicit reconciliation")
    companies = [forecast_company(m, r["companies"].get(m["stock"], {}), contracts["rows"]) for m in universe]
    bt = backtest(universe, r, contracts["rows"])
    for c in companies:
        c["backtest"] = {**bt["by_company"][c["stock"]], "warning": bt["small_sample_warning"], "calibrated": False,
            "by_horizon": {str(h): {key: metrics([r for r in bt[samples] if r["company_id"] == c["stock"] and r["horizon"] == h])
                for key, samples in (("existing_contract", "samples"), ("total_ledger", "total_samples"))} for h in range(1, 11)}}
    counts = dict(Counter(c["status"] for c in companies))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(input_dir.iterdir()) if p.is_file()}
    prior_by_id = {c["stock"]: c for c in prior["companies"]}
    changes = [{"stock": c["stock"], "company_name": c["company_name"],
                "prior_status": prior_by_id.get(c["stock"], {}).get("status"), "status": c["status"],
                "removed_reason_codes": sorted(set(prior_by_id.get(c["stock"], {}).get("reason_codes", [])) - set(c["reason_codes"])),
                "added_reason_codes": sorted(set(c["reason_codes"]) - set(prior_by_id.get(c["stock"], {}).get("reason_codes", []))),
                "unit_recovered": c["unit_audit"]["recovered_parser_flag"]} for c in companies]
    evidence_only = sorted(set(units["companies"]) - set(ids))
    retry_list = [{"stock": c["stock"], "company_name": c["company_name"], "status": c["status"],
                   **c["retry"], "current_blockers": c["amount_blocking_reason_codes"]}
                  for c in companies if c["retry"]["needs_longer_ledger"]]
    panel = {"schema_version": "knuke-r2-1", "compatible_skeleton": "kce-r4-1", "assignment": "ARGUS-knuke round 2",
             "origin": ORIGIN, "money_unit": MONEY, "numeric_decimal_places": 6,
             "input_sha256": hashes, "engine_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "fiscal_year_end_month": 12, "fiscal_basis": "assumed_December_close_unverified",
             "forecast_quarters": [qadd(ORIGIN, h) for h in range(1, 11)],
             "population": {"input_entries": len(universe), "input_companies": len(universe), "listed_companies": len(universe),
                            "unlisted_companies": 0, "status_counts": counts,
                            "estimated_companies": sum(c["status"] != "unavailable" for c in companies),
                            "unestimated_companies": sum(c["status"] == "unavailable" for c in companies),
                            "full_forecast_companies": counts.get("full", 0),
                            "estimated_definition": "at_least_one_monetary_ledger_component; progress_only_counts_as_unestimated",
                            "unit_evidence_companies": len(units["companies"]),
                            "unit_evidence_quarters": sum(len(v) for v in units["companies"].values()),
                            "evidence_only_stocks_not_promoted": evidence_only},
             "reaudit": {"prior_audit_schema": prior.get("schema_version"), "changes": changes,
                         "input_ledger_quarters": sum(len(c.get("quarters", {})) for c in r["companies"].values()),
                         "unit_contract": units["unit_contract"], "input_amount_scale": 1,
                         "evidence_only_company_reason": "unit captions alone do not supply a company ledger or universe membership"},
             "needs_longer_ledger": retry_list,
             "unlisted_reference": [], "backtest": bt, "reason_dictionary": REASONS,
             "note": "민감도 범위이며 calibrated=false. 원청·하청 중복을 제거할 자료가 없어 회사 합을 산업 시장규모로 합산하지 않는다.",
             "companies": companies}
    audit = audit_data(universe, r, contracts["rows"], companies)
    audit["reaudit"] = panel["reaudit"]
    audit["needs_longer_ledger"] = retry_list
    return panel, audit


def report_markdown(panel, audit):
    """Reproducible review report using actual output counts and metrics."""
    p, bt = panel["population"], panel["backtest"]
    fmt = lambda x: f"{x:,.3f}" if number(x) else "—"
    status = {"full": "전체 원장 조건부 추정", "partial": "일부 구성 추정", "unavailable": "금액 미추정"}
    lines = ["# ARGUS-knuke 2차 재감사·추정", "",
        f"기준 {ORIGIN}. 실제 모집단 **{p['input_companies']}사 = 금액 구성 추정 {p['estimated_companies']}사 + 미추정 {p['unestimated_companies']}사**. "
        f"추정 중 전체 원장 {p['full_forecast_companies']}사, 일부 구성 {p['status_counts'].get('partial', 0)}사. "
        "추정 대상은 수주 원장의 납품·역무 인식 대용치이며 회사 전체 회계매출 또는 순수 원전 매출이 아니다.", "",
        "1차 `knuke_forecast.py`, `forecast_section.py`, 테스트를 복사해 수정했고 `knuke_audit.json`의 판정과 비교했다. "
        "입력 파일은 읽기 전용으로 취급했다. 금액·단위·범위·원장 공백을 추정치로 메우지 않았다.", "",
        "## 입력과 단위 재감사", "",
        f"`knuke_universe.json`·`knuke_reports.json`은 {p['input_companies']}사·{audit['report_quarters']}분기·{audit['order_rows']}행이다. "
        f"새 캡션은 {p['unit_evidence_companies']}사·{p['unit_evidence_quarters']}분기다. "
        "25사·193분기는 단위 근거 파일의 크기이며 현재 수주 원장의 크기가 아니다. 원장에 없는 회사는 캡션만으로 편입하지 않았다.", "",
        "캡션만 있는 10종목: " + ", ".join(p["evidence_only_stocks_not_promoted"]) + ". "
        "계약공시의 모집단 밖 종목도 자동 편입하거나 금액에 합산하지 않았다.", "",
        "금액은 이미 **백만원**으로 정규화됐다는 새 입력 계약을 사용한다. 억원·천원 원문 캡션은 추적 근거로 보존하며 입력 금액에 다시 100 또는 0.001을 곱하지 않는다. "
        "같은 회사·분기의 원화 캡션, 정상 보고서, KRW 통화, 정규화 계약이 필요하다. 과거 분기 단위를 빌리지 않는다. "
        "파서의 단위 표식이 없으면 원화 금액 단위가 하나로 식별될 때만 조건부 복구한다. 외화·혼합통화·수량만 있는 캡션은 차단한다.", "",
        "제공 파일은 회사·분기별 캡션 목록이다. 표 위치·셀·공시번호 연결과 DART HTML은 없으므로 `raw_verified_at_origin=false`, "
        "`table_mapping_verified=false`를 유지한다. 이는 제공 정규화 계약에 의존한 조건부 허용이며 원문 독립검증 완료가 아니다.", "",
        "| 1차 단위 차단 회사 | 2차 결과 | 남은 조건 |", "|---|---|---|",
        "| 한텍 098070 | 기준분기 ['', '백만원'] 중 단일 원화 금액 단위로 복구, 일부 잔고분 추정 | 빈 캡션은 근거에서 제외. 보고서 총잔고는 null, 적격 신규수주 표본 2개. 개별행 잔고 176,966백만원을 총잔고로 채우지 않음 |",
        "| 부스타 008470 | 미추정 | 수주 행·표 통화 없음. 매출·혼합통화 캡션으로 수주 원장 생성 불가 |",
        "| 티에스넥스젠 043220 | 미추정 | 천원 캡션은 있으나 수주 행·표 통화 없음 |",
        "| 이성씨엔아이 379390 | 미추정 | 2026Q2 원장 없음. 과거 표 USD·혼합 캡션, 환산 없음 |", "",
        "모든 단위 판단·분기 행 감사는 `knuke_audit.json`, 1차 대비 변경은 `forecast_panel.json.reaudit.changes`에 있다. "
        "한텍의 2026Q2 누계납품 감소 -4,803백만원은 수정 가능성으로 남기며 소진율·신규수주 적합에서 제외한다.", "",
        "## 산업 축과 모델", "",
        "1차의 업무 축을 유지한다: ① 주기기·기자재와 신규 착공·납기 ② 설계·인허가 역무기간 ③ 가동호기·계속운전·정비에 의존하는 O&M "
        "④ 가동호기 교체 기자재 ⑤ 해체·폐기물 용역 ⑥ 제공 부문 납품·회전. 발전원 태그, 공급계층별 계약기간, NSSS/MMIS/ICI/CVAP/HRSG/EPC/MACST, "
        "호기 문자열, 국내·수출·미상을 보존한다. SMR을 독립 매출축으로 만들지 않는다. 실제 공정단계·착공일·가동호기수는 미확인이다.", "",
        "- 정확한 개별 서비스·설계·납기 기간이 있으면 기준분기 이후 잔여 계약기간에 잔고를 균등 배분한다. 이것은 실제 공정 S곡선이나 상업운전일 예측이 아니다.",
        "- 기간이 없고 같은 행·범위의 적격 납품 소진율이 2개 이상이면 중앙값 r로 잔고 B를 `B × r × (1-r)^(h-1)`로 인식한다. 개별 서비스·묶음 O&M에 이 회전율을 강제로 적용하지 않는다.",
        "- 신규분은 안정된 품목·부문 원장의 `O = B현재 − B이전 + 분기납품` 적격 표본 4개 이상과 전체 잔고 대조·자체 소진율이 모두 필요하다. 최근 최대 8개 표본의 P25/P50/P75로 보수/기준/낙관을 설정한다. O에는 정정·취소가 섞일 수 있어 실제 총신규수주와 동일하지 않다.",
        "- 음의 과거 신규수주 대용치는 증거에 보존한다. 미래 코호트 규모에만 max(0, O)를 적용한다. 분기말 수주 유입·다음 분기부터 자체 소진율 인식을 가정하며 실제 착공시차로 주장하지 않는다.",
        "- 세 시나리오의 기존 잔고 인식 경로는 같다. 신규분이 미추정이면 세 시나리오에 같은 확인 잔고분만 있고, 신규분은 null이다. 계절성 보정은 하지 않는다.",
        "- A=C+B, 합계·소계 제외, 행ID 중복, 묶음 계약, 종료 후 양의 잔고, 별도·연결 범위 변경을 검사한다. 원청·하청·계열·계약공시 금액을 더하지 않으며 산업 총액을 만들지 않는다.", "",
        "민감도는 `calibrated=false`, 명목 신뢰수준 null이다. 기간 배분 지수 0.75/1/1.25, 관측 소진율 최소~최대와 분기별 내부 극값, "
        "신규수주 P10~P90을 사용한다. 연간 범위는 분기별 경계의 합이며 공동확률 구간이 아니다. 백테스트 성적을 보고 범위를 맞추지 않았다.", "",
        "T+1~T+10은 2026Q3~2028Q4다. FY2026은 원장 기준 Q1·Q2 관측과 Q3·Q4 추정의 합, FY2027·FY2028은 각 네 분기 추정의 합이다. "
        "관측분이나 신규분이 없으면 전체 연간 값은 null이다. 12월 결산은 미검증 가정이다. 과거 매출표 값을 다른 범위의 원장에 붙이지 않는다.", "",
        "## 전수 판정", "", "| 종목 | 회사 | 판정 | 적격 신규수주 n | 금액 차단 사유 코드 |", "|---|---|---|---:|---|"]
    for c in panel["companies"]:
        lines.append(f"| {c['stock']} | {c['company_name']} | {status[c['status']]} | {c['retry']['eligible_new_order_sample_count']} | "
                     + ", ".join(c["amount_blocking_reason_codes"]) + " |")
    lines += ["", "9사의 HTML은 `sections/<종목>.html`에 있고 미추정 6사는 JSON과 위 표에 이유를 남긴다. "
              "분기·연간·시나리오·분해·구간은 모든 회사 JSON에 동일 구조로 존재하며, 낼 수 없는 칸은 null이다.", "",
              "## 전체 원장 추정 연간값", "", "단위: 백만원. 원전 순수 매출이나 회사 전체 회계매출로 읽지 않는다.", "",
              "| 회사 | 시나리오 | FY2026 | FY2027 | FY2028 |", "|---|---|---:|---:|---:|"]
    for c in panel["companies"]:
        if c["status"] == "full":
            for key, label in (("conservative", "보수"), ("base", "기준"), ("optimistic", "낙관")):
                lines.append(f"| {c['company_name']} | {label} | " + " | ".join(fmt(a["value"]) for a in c["scenarios"][key]["annual"]) + " |")
    lines += ["", "## 일부 추정의 잔고분", "", "단위: 백만원. 배분 가능한 행의 **미래 잔고분만** 합산했다. FY2026 열은 Q3·Q4분만이다. "
              "전사 연간 매출이 아니며 신규분과 과거 관측분을 포함하지 않는다.", "",
              "| 회사 | 2026 하반기 | 2027 잔고분 | 2028 잔고분 |", "|---|---:|---:|---:|"]
    for c in panel["companies"]:
        if c["status"] == "partial":
            lines.append(f"| {c['company_name']} | " + " | ".join(fmt(a["covered_sites_partial_revenue"]) for a in c["scenarios"]["base"]["annual"]) + " |")
    lines += ["", "## 원장 확장 후 재실행: needs_longer_ledger", "",
              "`forecast_panel.json.needs_longer_ledger`의 종목만 다음 금액 게이트 재검사 대상으로 뽑을 수 있다. "
              "목표는 2021Q4~2026Q2의 19분기다. 단순 분기 개수보다 같은 범위·행ID·단위·비음수 납품의 적격 표본 증가가 필요하다. "
              "확장만으로 자동 해제된다는 뜻이 아니다.", "",
              "| 회사 | 신규수주 n/4 | 원장 확장으로 재검사할 항목 | 추가 선결조건 |", "|---|---:|---|---|"]
    for c in panel["needs_longer_ledger"]:
        targets = (["신규수주 표본"] if c["order_sample_retry"] else []) + [f"{m['name']} 소진율 {m['eligible_samples']}/2" for m in c["burn_rows"]]
        lines.append(f"| {c['company_name']} {c['stock']} | {c['eligible_new_order_sample_count']}/4 | "
                     + "; ".join(targets) + " | " + (", ".join(c["non_length_prerequisites"]) or "적격 표본 증가 확인") + " |")
    lines += ["", "두산에너빌리티는 2026년 parent→unknown 경계를 넘지 않으므로 과거 parent 원장을 늘려도 현재 unknown 범위의 1개 표본은 그대로일 수 있다. "
              "한전기술의 한 행은 과거에 같은 행이 없으면 길이를 늘려도 복구되지 않는다. 한텍은 총잔고 누락도 별도 해결해야 한다.", "",
              "길이만으로 풀리지 않는 항목: 한전산업·강원에너지의 중복 행ID, 한전KPS의 묶음 계약·회계 항등식, 우진의 종료일 경과 잔고, "
              "O&M의 가동호기·계속운전·정비주기·갱신 단가, 날짜 계약의 신규수주 전환모형, 수주 행 부재·외화·기준분기 부재. "
              "이들은 `needs_longer_ledger`만으로 처리하지 않는다. 장기 백테스트 표본 확보는 전체 회사에 별도로 필요하다.", "",
              "## 백테스트", "", "| 대상 | n | MAE 백만원 | WAPE % | Bias % | 음의 실측 n |", "|---|---:|---:|---:|---:|---:|"]
    for key, label in (("existing_contract", "동일 계약 잔고분"), ("total_ledger", "신규분 포함 전체 원장")):
        m = bt[key]
        lines.append(f"| {label} | {m['n']} | {fmt(m['mae'])} | {fmt(m['wape_pct'])} | {fmt(m['bias_pct'])} | {m['negative_actual_n']} |")
    lines += ["", "잔고분 오차는 크다. 균등 기간 배분을 실제 공정 인식으로 해석할 수 없으며 장기 정확성을 입증하지 못한다. "
              "회사·원점·행·지평이 중첩되는 표본은 독립 표본이 아니다. 전체 원장 표본도 두 회사의 짧은 지평에 국한된다.", "",
              "| 지평 | 잔고분 n | 잔고분 WAPE % | 전체 원장 n | 전체 WAPE % |", "|---|---:|---:|---:|---:|"]
    for h, m in bt["by_horizon"].items():
        lines.append(f"| T+{h} | {m['existing_contract']['n']} | {fmt(m['existing_contract']['wape_pct'])} | {m['total_ledger']['n']} | {fmt(m['total_ledger']['wape_pct'])} |")
    lines += ["", "각 원점까지의 원장만으로 모델을 다시 만든다. 정규화·누적 기준도 해당 원점 정보에서 판정한다. "
              "잔고분은 계약총액이 변하지 않은 같은 계약의 분기 납품 차분과 비교하고, 전체는 같은 부문 구성의 납품 차분과 비교한다. "
              "수정으로 음수가 된 실측도 점수에서 제거하지 않았다. 채워 넣은 실측 표본은 0이다. 모든 점수의 표본은 JSON에 공개한다.", "",
              bt["small_sample_warning"], "",
              "보고서는 분기말 이후 공시됐으며 정정 전 빈티지·정확한 당시 정보집합은 제공되지 않았다. "
              "따라서 분기 원장 순서의 회고 검증이며 분기말 실시간 투자 백테스트가 아니다. 계약기간 참고는 공시번호 날짜가 원점 분기말 이전인 것만 사용한다. "
              "FY2027·FY2028의 실제 성적이나 95% 적중률은 제시하지 않는다.", "",
              "## 재현·검증·인계", "", "작업 루트에서 표준 라이브러리 Python으로 실행한다. 네트워크·외부 패키지·CDN은 필요 없다.", "",
              "```sh", "python3 -B output/knuke_forecast.py", "python3 -B output/forecast_section.py",
              "python3 -B -m unittest discover -s output -p 'test_knuke_forecast.py' -v", "```", "",
              "테스트는 모집단 보존, 단위 복구와 누락·외화 차단, 재배율 방지, 분기·연간 분해 보존, 범위 경계, 누락값, "
              "미래 입력 누출, 실제 백테스트 표본 재계산, 오프라인 HTML/SVG와 입력 SHA-256을 확인한다. 실행 결과는 `test_results.txt`에 별도로 남긴다.", "",
              "tracker 사전 확인은 central_connection_failed였다. 연결 재시도·원격 인계·정본 수정은 하지 않았고 지정 worker 공간의 output/에만 썼다. "
              "배포·외부 메시지·인증 변경·중첩 fleet 작업은 없다. 정본 통합은 coordinator가 수행한다.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--input-dir", type=Path, default=root / "input")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    panel, audit = build(args.input_dir)
    write_json(args.output_dir / "forecast_panel.json", panel)
    write_json(args.output_dir / "knuke_audit.json", audit)
    (args.output_dir / "knuke_REPORT.md").write_text(report_markdown(panel, audit), encoding="utf-8")
    print(json.dumps({"population": panel["population"], "report_records": audit["report_quarters"],
                      "order_rows": audit["order_rows"], "collection_tasks": audit["collection_task_count"],
                      "backtest_existing": panel["backtest"]["existing_contract"],
                      "backtest_total": panel["backtest"]["total_ledger"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
