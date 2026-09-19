#!/usr/bin/env python3
"""Offline KNUKE ledger forecasts, audit and rolling-origin validation.

Only Python's standard library. Does not import or execute input code.
Round 3 extends the supplied round-2 engine. Amounts require the supplied
normalization contract and same-quarter captions or explicit parser unit flags.
No second scaling or FX. Parser-only evidence is conditional, not raw verification.
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
BACKTEST_HORIZONS = 8
INFORMATIONAL_REASONS = {"ledger_not_company_revenue", "raw_caption_absent", "scope_unknown", "ytd_inferred",
                         "parser_unit_flag_only",
                         "power_scope_unidentified", "regional_leadtime_unidentified", "date_range_recovered",
                         "caption_table_mapping_unverified", "unit_recovered_from_supplied_evidence"}
REASONS = {
    "parser_unit_flag_only": "같은 분기 KRW·unit_seen 표식과 제공 백만원 정규화 계약에 조건부 의존; 원문 캡션 미제공",
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
    parser_only = (not captions and context.get("allow_parser_flag") is True
                   and s.get("unit_seen") is True)
    if not units and not parser_only:
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
            "evidence_level": "parser_flag_and_supplied_contract" if parser_only else "supplied_caption_and_contract",
            "parser_only": parser_only, "normalization_code_independently_verified": False,
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
                "allow_parser_flag": evidence.get("allow_parser_flag", False),
                "source": evidence.get("sources", {}).get(stock, {}).get(quarter,
                    f"knuke_unit_evidence.json#/companies/{stock}/{quarter}")}
    return result


def unit_evidence_from_audit(reports, prior, allow_parser_flag=True):
    """Reuse only exact company/quarter/filing captions; never carry units in time.

    The standalone round-2 caption file is absent in round 3. Its contract and
    113 quarter audit records survive in the supplied audit. Expanded records
    with unit_seen=True rely explicitly on the same supplied parser contract.
    This weaker evidence tier is exposed and tested against captions-only mode.
    """
    evidence = {"unit_contract": prior.get("reaudit", {}).get("unit_contract", ""),
                "companies": {}, "sources": {}, "allow_parser_flag": allow_parser_flag}
    previous = {c["stock"]: c for c in prior["companies"]}
    for stock, company in reports["companies"].items():
        old = {q["quarter"]: q for q in previous.get(stock, {}).get("quarters", []) if q.get("present")}
        evidence["companies"][stock], evidence["sources"][stock] = {}, {}
        for q, s in company.get("quarters", {}).items():
            a = old.get(q, {})
            same = bool(a.get("rcp")) and a["rcp"] == s.get("rcp") and a.get("currency") == s.get("cur")
            captions = a.get("unit_evidence", {}).get("raw_unit_captions", []) if same else []
            evidence["companies"][stock][q] = captions
            evidence["sources"][stock][q] = (f"knuke_audit.json#/companies/{stock}/quarters/{q}/unit_evidence"
                if captions else f"knuke_reports.json#/companies/{stock}/quarters/{q}:unit_seen,cur,ok")
    return evidence


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
        for key in sorted(pr.keys() & cr.keys()):
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


def order_pair_diagnostics(history, norm, pairs, origin):
    """One audit record for every possible adjacent calendar pair, including holes."""
    current_keys = {r["key"] for r in norm.get(origin, []) if not r["is_aggregate"]}
    current_scope = history.get(origin, {}).get("orders_scope")
    lookup = {p["quarter"]: p for p in pairs}
    if not history:
        return []
    result = []
    for n in range(qnum(min(history)) + 1, qnum(origin) + 1):
        q = f"{n // 4}Q{n % 4 + 1}"
        pq = qadd(q, -1)
        p, s = history.get(pq), history.get(q)
        codes = []
        if p is None or s is None:
            codes.append("missing_adjacent_snapshot")
        else:
            if not money_ok(p) or not money_ok(s):
                codes.append("unit_currency")
            if p.get("orders_scope") != s.get("orders_scope"):
                codes.append("scope_transition")
            if s.get("orders_scope") != current_scope:
                codes.append("not_current_scope")
            old = [r for r in norm[pq] if not r["is_aggregate"]]
            now = [r for r in norm[q] if not r["is_aggregate"]]
            if not old or not now:
                codes.append("no_order_rows")
            for r in old + now:
                codes.extend(c for c in r["reason_codes"] if c in {
                    "duplicate_identity", "grouped_contracts", "identity_conflict"})
                if not r["raw_delivered_present"]:
                    codes.append("missing_raw_delivery")
            if {r["key"] for r in old} != {r["key"] for r in now}:
                codes.append("changed_row_set")
            if {r["key"] for r in old} != current_keys or {r["key"] for r in now} != current_keys:
                codes.append("not_current_row_set")
        pair = lookup.get(q)
        if pair:
            if not pair["complete"]:
                codes.append("incomplete_pair")
            if any(v["delivery"] < 0 for v in pair["rows"].values()):
                codes.append("negative_delivery_revision")
        elif p is not None and s is not None and not codes:
            codes.append("pair_unavailable")
        result.append({"previous_quarter": pq, "quarter": q,
                       "eligible": not codes and bool(pair), "reason_codes": sorted(set(codes))})
    return result


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
        all_rates = [v["rate"] for v in samples if number(v["rate"]) and 0 <= v["rate"] <= 1]
        rates = all_rates[-8:]
        m["rate_samples"] = samples
        m["eligible_rate_sample_count"] = len(all_rates)
        m["rate_fit_sample_count"] = len(rates)
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
    if unit["parser_only"]:
        reason.append("parser_unit_flag_only")
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
    current_keys = {m["key"] for m in models}
    order_pairs_all = [p for p in pairs if p["complete"] and p["scope"] == s.get("orders_scope")
                      and all(x["delivery"] >= 0 for x in p["rows"].values())
                      and set(p["rows"]) == current_keys]
    order_pairs = order_pairs_all[-8:]
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
             "eligible_new_order_sample_count": len(order_pairs_all), "minimum_new_order_samples": MIN_ORDERS,
             "fit_new_order_sample_count": len(order_pairs),
             "eligible_new_order_quarters": [p["quarter"] for p in order_pairs_all],
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
    diagnostics = order_pair_diagnostics(hist, norm, pairs, origin)
    retry["calendar_extension_complete"] = len(hist) == qnum(origin) - qnum("2021Q4") + 1
    retry["remaining_pair_blockers"] = dict(Counter(code for p in diagnostics for code in p["reason_codes"]))
    retry["next_action"] = ("repair_or_verify_existing_pair_evidence; calendar_length_alone_is_not_the_gate"
                            if needs_longer else "no_length_retry; inspect_other_model_prerequisites")
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
            "seasonality": {"enabled": False, "reason": "round_2_policy_retained_without_backtest_tuning"},
            "order_models": order_models,
            "missing_reasons": [] if allow_orders else ["new_order_model_unavailable"]},
            "quarterly": quarterly,
            "annual": annualize(quarterly, actual, origin,
                                range(int(origin[:4]), int(qadd(origin, horizons)[:4]) + 1))}
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
                           "verification_level": unit["evidence_level"],
                           "money_unit": MONEY if money_ok(s) else None, "scale_from_input": 1 if money_ok(s) else None,
                           "raw_unit_caption_available": bool(unit["raw_unit_captions"]), "currency": s.get("cur"),
                           "latest_available_currency": hist[max(hist)].get("cur") if hist else None,
                           "unit_basis": "2차 감사의 동일 공시 캡션 또는 이번 원장의 같은 분기 unit_seen=true·KRW + 제공 백만원 정규화 계약; 재배율 없음"},
            "coverage": coverage, "evidence": {"delivery_semantics": sem, "delivery_basis": sem_basis,
                "pairs": pairs, "pair_exclusions": exclusions,
                "order_pair_diagnostics": diagnostics,
                "orders": [{"quarter": p["quarter"], "value": sum(x["orders"] for x in p["rows"].values())} for p in order_pairs],
                "all_eligible_orders": [{"quarter": p["quarter"], "value": sum(x["orders"] for x in p["rows"].values())} for p in order_pairs_all],
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


def annual_backtest_samples(quarterly_rows, existing=False):
    """Full calendar FY at prior Q4 (FY+1) or two Q4s before (FY+2).

    Require all four individually eligible actuals. No partial-year annualization,
    overlapping year-to-date labels or zero-filling of missing observations.
    """
    groups = defaultdict(list)
    for r in quarterly_rows:
        if not r["origin"].endswith("Q4"):
            continue
        year = int(r["target"][:4])
        lead = year - int(r["origin"][:4])
        if lead not in (1, 2):
            continue
        groups[(r["company_id"], r["origin"], year, r.get("row_id"))].append(r)
    result = []
    for (stock, origin, year, row_id), values in sorted(groups.items()):
        values = sorted(values, key=lambda r: r["target"])
        if [r["target"] for r in values] != [f"{year}Q{i}" for i in range(1, 5)]:
            continue
        row = {"company_id": stock, "origin": origin, "fiscal_year": year,
               "lead_years": year - int(origin[:4]), "quarters": [r["target"] for r in values],
               "horizons": [r["horizon"] for r in values],
               "prediction": sum(r["prediction"] for r in values),
               "actual": sum(r["actual"] for r in values),
               "quarter_predictions": [r["prediction"] for r in values],
               "quarter_actuals": [r["actual"] for r in values],
               "target_basis": "four_complete_same_contract_quarters" if existing else "four_complete_same_segment_ledger_quarters"}
        if existing:
            row["row_id"] = row_id
        result.append(row)
    return result


def backtest(universe, reports, contracts):
    rows, full_rows, excluded = [], [], Counter()
    allq = sorted(reports["quarters"])
    for meta in universe:
        c = reports["companies"].get(meta["stock"], {})
        target_cache = {}
        for origin in allq[:-1]:
            if origin not in c.get("quarters", {}):
                excluded["origin_missing"] += 1; continue
            fc = forecast_company(meta, c, contracts, origin)
            for h in range(1, BACKTEST_HORIZONS + 1):
                target = qadd(origin, h)
                if target not in c.get("quarters", {}):
                    excluded["future_target_unobserved"] += 1; continue
                # Target normalization cannot retroactively change origin parameters.
                if target not in target_cache:
                    th, tn, ts, _ = normalized_history({**c, "role": meta.get("role")}, target)
                    tp, _ = matched_deltas(th, tn, ts)
                    target_cache[target] = th, tn, ts, tp
                th, tn, ts, tp = target_cache[target]
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
    annual_rows = annual_backtest_samples(rows, existing=True)
    annual_full_rows = annual_backtest_samples(full_rows)
    annual = {"scope": "Q4_origin_full_calendar_year; FY+1_h1_to_h4; FY+2_h5_to_h8",
              "fiscal_basis": "assumed_December_close_unverified", "filled_cells_scored": 0,
              "existing_contract": metrics(annual_rows), "total_ledger": metrics(annual_full_rows),
              "by_lead_year": {str(y): {"existing_contract": metrics([r for r in annual_rows if r["lead_years"] == y]),
                                      "total_ledger": metrics([r for r in annual_full_rows if r["lead_years"] == y])} for y in (1, 2)},
              "samples": annual_rows, "total_samples": annual_full_rows}
    bycompany = {}
    for meta in universe:
        s = meta["stock"]
        bycompany[s] = {"existing_contract": metrics([r for r in rows if r["company_id"] == s]),
                        "total_ledger": metrics([r for r in full_rows if r["company_id"] == s]),
                        "annual": {"existing_contract": metrics([r for r in annual_rows if r["company_id"] == s]),
                                   "total_ledger": metrics([r for r in annual_full_rows if r["company_id"] == s])}}
    return {"scope": "rolling_report_quarter_origin; delivery_proxy_not_audited_sales",
            "origins": allq[:-1], "money_unit": MONEY, "filled_cells_scored": 0,
            "existing_contract": metrics(rows), "total_ledger": metrics(full_rows),
            "by_horizon": {str(h): {"existing_contract": metrics([r for r in rows if r["horizon"] == h]),
                                   "total_ledger": metrics([r for r in full_rows if r["horizon"] == h])} for h in range(1, BACKTEST_HORIZONS + 1)},
            "by_company": bycompany, "annual": annual, "exclusions": dict(excluded), "calibrated": False,
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
    return {"schema_version": "knuke-audit-3", "origin": ORIGIN, "input_companies": len(universe),
            "report_companies": len(reports["companies"]), "report_quarters": sum(c["quarter_count"] for c in result),
            "order_rows": sum(c["row_count"] for c in result), "companies": result,
            "population_discrepancies": {"assignment_claimed_companies": 25, "actual_universe_companies": len(universe),
                "assignment_claimed_report_records": 434, "actual_report_records": sum(c["quarter_count"] for c in result),
                "actual_contracts": len(contracts),
                "contracts_outside_universe": dict(sorted(orphan.items())),
                "contracts_outside_universe_n": sum(orphan.values()), "outside_universe_not_promoted": True},
            "collection_tasks": tasks, "collection_task_count": len(tasks),
            "source_limit": "제공 JSON·2차 감사 캡션·정규화 계약 및 같은 분기 unit_seen=true·KRW 표식에 조건부 의존. DART 원문 HTML·표 위치·파서 코드 미제공."}


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


def reconstruct_round2(universe, reports, prior):
    """Restrict to audited round-2 company/quarter cells; check surviving values.

    Original round-2 forecast_panel is not supplied. This reconstruction is
    independently checked against its audit and the rounded published report.
    """
    old_ids = {c["stock"] for c in prior["companies"]}
    u = [m for m in universe if m["stock"] in old_ids]
    r = {"n": len(u), "quarters": [], "companies": {}}
    checks, mismatches = 0, []
    fields = ("key", "gross", "delivered", "backlog", "start_raw", "end_raw", "reason_codes")
    for old in prior["companies"]:
        stock = old["stock"]
        qs = [q["quarter"] for q in old["quarters"] if q.get("present")]
        c = reports["companies"][stock]
        subset = {q: c["quarters"][q] for q in qs if q in c["quarters"]}
        r["companies"][stock] = {**c, "quarters": subset}
        sem, _ = semantics(subset)
        for a in old["quarters"]:
            if not a.get("present"):
                continue
            s = subset.get(a["quarter"], {})
            normalized = normalize_snapshot(s, a["quarter"], old.get("role"), sem)
            checks += 1
            expected = [{k: row.get(k) for k in fields} for row in a["row_audit"]]
            actual = [{k: row.get(k) for k in fields} for row in normalized]
            if (expected != actual or a.get("rcp") != s.get("rcp")
                    or a.get("orders_scope") != s.get("orders_scope")
                    or a.get("reported_backlog") != (s.get("backlog") if money_ok(s) else None)):
                mismatches.append({"stock": stock, "quarter": a["quarter"]})
    r["quarters"] = sorted({q for c in r["companies"].values() for q in c["quarters"]})
    if mismatches:
        raise ValueError("round-2 reconstruction input mismatch: " + str(mismatches))
    return u, r, {"source": "input/knuke_audit.json; old company/quarter mask on unchanged overlap",
                  "checked_company_quarters": checks, "overlap_mismatches": mismatches,
                  "original_forecast_panel_supplied": False}


def published_round2_metrics(text):
    result = {}
    for key, label in (("existing_contract", "동일 계약 잔고분"), ("total_ledger", "신규분 포함 전체 원장")):
        match = re.search(r"^\| " + re.escape(label) + r" \| ([\d,]+) \| ([\d,.]+) \| ([\d,.]+) \|", text, re.M)
        if not match:
            raise ValueError("published round-2 metric table missing: " + label)
        result[key] = {"n": int(match[1].replace(",", "")), "mae": float(match[2].replace(",", "")),
                       "wape_pct": float(match[3].replace(",", ""))}
    return result


def company_changes(companies, old_companies, prior):
    old_fc = {c["stock"]: c for c in old_companies}
    old_audit = {c["stock"]: c for c in prior["companies"]}
    result = []
    for c in companies:
        stock = c["stock"]
        old = old_fc.get(stock)
        values = []
        if old:
            for scenario in SCENARIOS:
                for a, b in zip(old["scenarios"][scenario]["annual"], c["scenarios"][scenario]["annual"]):
                    for key in ("value", "covered_sites_partial_revenue", "existing_backlog_revenue", "new_order_revenue"):
                        x, y = a[key], b[key]
                        pct = 100 * (y - x) / abs(x) if number(x) and number(y) and x != 0 else None
                        values.append({"scenario": scenario, "fiscal_year": b["fiscal_year"], "component": key,
                                       "round2": x, "round3": y, "change_pct": pct,
                                       "large_change": abs(pct) >= 20 if number(pct) else number(y) and x is None})
        old_retry = old_audit.get(stock, {}).get("retry", {})
        changed_rates = []
        if old:
            bykey = {r["key"]: r for r in old["row_forecasts"]}
            for r in c["row_forecasts"]:
                previous = bykey.get(r["key"], {})
                if previous.get("rate") != r.get("rate"):
                    changed_rates.append({"row_id": r["row_id"], "name": r["name"] or r["label"],
                                          "round2_rate": previous.get("rate"), "round3_rate": r.get("rate"),
                                          "round2_fit_n": previous.get("rate_fit_sample_count"),
                                          "round3_fit_n": r.get("rate_fit_sample_count")})
        result.append({"stock": stock, "company_name": c["company_name"],
                       "prior_status": old_audit.get(stock, {}).get("status"), "status": c["status"],
                       "prior_company_present": old is not None,
                       "prior_needs_longer_ledger": old_retry.get("needs_longer_ledger", False),
                       "prior_eligible_new_order_samples": old_retry.get("eligible_new_order_sample_count"),
                       "eligible_new_order_samples": c["retry"]["eligible_new_order_sample_count"],
                       "prior_quarter_count": old_audit.get(stock, {}).get("quarter_count"),
                       "quarter_count": c["retry"]["observed_quarter_count"],
                       "length_gate_resolved": old_retry.get("needs_longer_ledger", False) and not c["retry"]["needs_longer_ledger"],
                       "removed_reason_codes": sorted(set(old_audit.get(stock, {}).get("reason_codes", [])) - set(c["reason_codes"])),
                       "added_reason_codes": sorted(set(c["reason_codes"]) - set(old_audit.get(stock, {}).get("reason_codes", []))),
                       "unit_recovered": c["unit_audit"]["recovered_parser_flag"],
                       "changed_burn_rates": changed_rates, "annual_changes": values,
                       "new_order_assumption_base": c["scenarios"]["base"]["assumptions"]["new_orders_per_quarter"],
                       "prior_new_order_assumption_base": old["scenarios"]["base"]["assumptions"]["new_orders_per_quarter"] if old else None,
                       "pair_blockers": c["retry"]["remaining_pair_blockers"],
                       "remaining_blockers": c["amount_blocking_reason_codes"]})
    return result


def backtest_subset(bt, ids):
    rows = [r for r in bt["samples"] if r["company_id"] in ids]
    full = [r for r in bt["total_samples"] if r["company_id"] in ids]
    arows = [r for r in bt["annual"]["samples"] if r["company_id"] in ids]
    afull = [r for r in bt["annual"]["total_samples"] if r["company_id"] in ids]
    return {"existing_contract": metrics(rows), "total_ledger": metrics(full),
            "by_horizon": {str(h): {"existing_contract": metrics([r for r in rows if r["horizon"] == h]),
                                   "total_ledger": metrics([r for r in full if r["horizon"] == h])} for h in range(1, BACKTEST_HORIZONS + 1)},
            "annual": {"existing_contract": metrics(arows), "total_ledger": metrics(afull)}}


def build(input_dir):
    load = lambda name: json.loads((input_dir / name).read_text(encoding="utf-8"))
    u, r, contracts = load("knuke_universe.json"), load("knuke_reports.json"), load("knuke_contracts.json")
    prior = load("knuke_audit.json")
    units = unit_evidence_from_audit(r, prior)
    strict_reports = apply_unit_evidence(r, unit_evidence_from_audit(r, prior, allow_parser_flag=False))
    r = apply_unit_evidence(r, units)
    universe = u["rows"]
    ids = [m["stock"] for m in universe]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate universe stock")
    if set(r["companies"]) - set(ids):
        raise ValueError("report company outside universe requires explicit reconciliation")
    companies = [forecast_company(m, r["companies"].get(m["stock"], {}), contracts["rows"]) for m in universe]
    bt = backtest(universe, r, contracts["rows"])
    old_u, old_r, reconstruction = reconstruct_round2(universe, r, prior)
    old_companies = [forecast_company(m, old_r["companies"][m["stock"]], contracts["rows"]) for m in old_u]
    old_bt = backtest(old_u, old_r, contracts["rows"])
    published = published_round2_metrics((input_dir / "knuke_REPORT.md").read_text(encoding="utf-8"))
    for key, expected in published.items():
        for field, value in expected.items():
            if round(old_bt[key][field], 3) != value:
                raise ValueError(f"round-2 metric reproduction mismatch: {key}/{field}")
    reconstruction["published_metrics_reproduced_to_3dp"] = True
    reconstruction["published_metrics"] = published
    reconstruction["annual_metrics_previously_published"] = False
    # Isolate universe expansion from additional history. This uses the same
    # round-3 policy and all 19 quarters for the original 15 companies.
    original_ids = {m["stock"] for m in old_u}
    original_bt = backtest_subset(bt, original_ids)
    strict_companies = [forecast_company(m, strict_reports["companies"][m["stock"]], contracts["rows"]) for m in universe]
    for c in companies:
        c["round2_backtest"] = old_bt["by_company"].get(c["stock"])
        c["backtest"] = {**bt["by_company"][c["stock"]], "warning": bt["small_sample_warning"], "calibrated": False,
            "by_horizon": {str(h): {key: metrics([r for r in bt[samples] if r["company_id"] == c["stock"] and r["horizon"] == h])
                for key, samples in (("existing_contract", "samples"), ("total_ledger", "total_samples"))} for h in range(1, BACKTEST_HORIZONS + 1)}}
    counts = dict(Counter(c["status"] for c in companies))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(input_dir.iterdir()) if p.is_file()}
    changes = company_changes(companies, old_companies, prior)
    evidence_only = sorted(set(units["companies"]) - set(ids))
    retry_list = [{"stock": c["stock"], "company_name": c["company_name"], "status": c["status"],
                   **c["retry"], "current_blockers": c["amount_blocking_reason_codes"]}
                  for c in companies if c["retry"]["needs_longer_ledger"]]
    panel = {"schema_version": "knuke-r3-1", "compatible_skeleton": "kce-r4-1", "assignment": "ARGUS-knuke round 3",
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
                            "unit_evidence_quarters": sum(money_ok(s) for c in r["companies"].values() for s in c["quarters"].values()),
                            "caption_backed_quarters": sum(money_ok(s) and not unit_decision(s)["parser_only"] for c in r["companies"].values() for s in c["quarters"].values()),
                            "parser_only_quarters": sum(money_ok(s) and unit_decision(s)["parser_only"] for c in r["companies"].values() for s in c["quarters"].values()),
                            "evidence_only_stocks_not_promoted": evidence_only},
             "reaudit": {"prior_audit_schema": prior.get("schema_version"), "changes": changes,
                         "input_ledger_quarters": sum(len(c.get("quarters", {})) for c in r["companies"].values()),
                         "unit_contract": units["unit_contract"], "input_amount_scale": 1,
                         "unit_contract_source": "input/knuke_audit.json#/reaudit/unit_contract",
                         "expanded_unit_contract_application": "same named expanded report ledger; supplied parser contract assumed applicable; collector code and HTML not supplied",
                         "evidence_only_company_reason": "unit captions alone do not supply a company ledger or universe membership"},
             "needs_longer_ledger": retry_list,
             "reassessment": {"prior_priority_stocks": [c["stock"] for c in prior["companies"]
                    if c.get("retry", {}).get("needs_longer_ledger") or "insufficient_order_samples" in c.get("reason_codes", [])],
                 "prior_length_gate_count": len(prior.get("needs_longer_ledger", [])),
                 "resolved_length_gate_stocks": [c["stock"] for c in changes if c["length_gate_resolved"]],
                 "newly_estimated_prior_stocks": [c["stock"] for c in changes if c["prior_status"] == "unavailable" and c["status"] != "unavailable"],
                 "added_estimated_stocks": [c["stock"] for c in changes if not c["prior_company_present"] and c["status"] != "unavailable"],
                 "large_change_threshold_pct": 20},
             "round2_comparison": {"reconstruction": reconstruction, "baseline_backtest": old_bt,
                 "expanded_original_universe_backtest": original_bt,
                 "quarter_growth": {"round2": prior["report_quarters"],
                     "round3_original_companies": sum(len(r["companies"][s]["quarters"]) for s in original_ids),
                     "round3_all_companies": sum(len(c["quarters"]) for c in r["companies"].values())},
                 "method_changes": ["unit parser-only evidence tier explicitly enabled for new cells; captions-only diagnostic supplied",
                     "same-current-row-set eligibility filter precedes last-8 fit window; full eligible count separate from fit count",
                     "annual full-FY scoring added at Q4 origins; four observed quarters required",
                     "round-2 seasonality/rate/order quantile assumptions retained; no error-based parameter tuning"]},
             "captions_only_sensitivity": {"purpose": "effect of refusing supplied parser flags without raw captions; not calibrated uncertainty",
                 "status_counts": dict(Counter(c["status"] for c in strict_companies)),
                 "companies": [{"stock": c["stock"], "status": c["status"],
                     "eligible_new_order_samples": c["retry"]["eligible_new_order_sample_count"],
                     "base_annual": c["scenarios"]["base"]["annual"]} for c in strict_companies]},
             "unlisted_reference": [], "backtest": bt, "reason_dictionary": REASONS,
             "note": "민감도 범위이며 calibrated=false. 원청·하청 중복을 제거할 자료가 없어 회사 합을 산업 시장규모로 합산하지 않는다.",
             "companies": companies}
    audit = audit_data(universe, r, contracts["rows"], companies)
    audit["reaudit"] = panel["reaudit"]
    audit["needs_longer_ledger"] = retry_list
    return panel, audit


def report_markdown(panel, audit):
    """Reproducible round-3 report; no hand-edited performance claims."""
    p, bt = panel["population"], panel["backtest"]
    comp = panel["round2_comparison"]
    old, expanded = comp["baseline_backtest"], comp["expanded_original_universe_backtest"]
    changes = {c["stock"]: c for c in panel["reaudit"]["changes"]}
    cos = {c["stock"]: c for c in panel["companies"]}
    fmt = lambda x: f"{x:,.3f}" if number(x) else "—"
    status = {"full": "전체 원장 조건부", "partial": "일부 구성", "unavailable": "미추정", None: "2차 모집단 밖"}
    def table(headers, values):
        return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] + [
            "| " + " | ".join(str(v).replace("|", "/") for v in row) + " |" for row in values]
    lines = ["# ARGUS-knuke 3차 — 19분기 재판정·추정·백테스트", "",
        f"기준 **2026Q2**, 2021Q4~2026Q2 달력 **19분기·25사·{audit['report_quarters']} 회사분기·{audit['order_rows']:,}행**. "
        f"추정 가능 구성은 **{p['estimated_companies']}사**(전체 원장 {p['full_forecast_companies']}사, 일부 {p['status_counts'].get('partial', 0)}사), 미추정 {p['unestimated_companies']}사다. "
        "회사 전체 회계매출·원전 순수 매출이 아니라 제공 수주 원장의 납품·역무 인식 대용치다.", "",
        f"**기존 needs_longer_ledger 5사 중 해제 {len(panel['reassessment']['resolved_length_gate_stocks'])}사.** "
        "원장이 길어졌지만 현재와 같은 행ID·범위·확인 단위·비음수 납품을 만족하는 쌍은 늘지 않았다. "
        "4개 기준을 낮추거나 누락·중복 행을 순서로 연결하지 않았다. 기존 15사의 판정은 유지되고, 새로 편입된 10사 중 우진엔텍·일진파워·금양그린파워·지투파워의 일부 잔고분을 처음 제시한다.", "",
        "2차 엔진·렌더러·테스트를 복사해 확장했다. 2차의 최근 최대 8개 적격 표본, 신규수주 최소 4개, 소진율 최소 2개 기준을 유지했다. "
        "총 적격 표본 수와 실제 적합에 쓰는 최근 8개를 별도로 공개한다. 현재 행 구성 필터를 먼저 적용한 뒤 최근 8개를 선택하도록 순서를 바로잡았다. "
        "2차 패널 원본은 입력에 없으므로 2차 감사에 있는 회사·분기 마스크로 복원했다. 113개 겹치는 분기의 공시번호·범위·행별 금액/날짜/판정에 불일치가 없고, "
        "2차 보고서의 표본 수·MAE·WAPE를 소수 셋째 자리까지 재현했다.", "",
        "## 표본 부족 보류 우선 재판정", ""]
    reasons = {
        "034020": "2026 parent→unknown 경계와 행명 변경. 현재 범위·행 구성의 쌍은 2026Q2 1개뿐. 주기기·보증 소진율도 각 1/2, 운영서비스 동인 미확인.",
        "052690": "왕신 연료전지 행 소진율 0/2. 전체 계약 집합은 18개 쌍 모두 변경. 날짜 기반 설계 계약의 신규수주 전환 동인도 별도 필요.",
        "083650": "2021Q4~2025Q1 두 행의 이름·라벨·상대가 비어 동일 ID가 중복됨. 2025Q2부터 국내/해외 식별, 2025Q4 두 행의 납품 차분이 음수. 적격은 2025Q3·2026Q1·2026Q2뿐.",
        "098070": "실제 파일은 여전히 7분기이며 앞 3분기 수주 행 없음. 적격은 2025Q4·2026Q1뿐. 2026Q2 납품 차분 -4,803, 보고서 총잔고 null. 행 잔고 176,966으로 총잔고를 메우지 않음.",
        "258610": "과거 15→13→12개 행 구성 변경, 2025Q3/Q4 MTU Seal 2차 납품 누락·LEAP VANE 항등식 불일치. 현재 12행과 맞는 적격은 2025Q2·2026Q2뿐. 2022Q1 휴대폰 품목 등 범위 변화도 원문 확인 필요.",
        "288620": "새 편입 회사. start_raw가 ~공시일 형태로 매 분기 달라져 18개 쌍 모두 행ID 변경. 이를 계약일로 정정하거나 날짜를 지워 연결할 근거 없음."
    }
    priority = [c for c in panel["reaudit"]["changes"] if c["prior_needs_longer_ledger"]]
    lines += table(["회사", "분기 2차→3차", "적격 신규수주 n 2차→3차", "새로 확인한 탈락 사유"], [
        [f"{c['company_name']} {c['stock']}", f"{c['prior_quarter_count']}→{c['quarter_count']}",
         f"{c['prior_eligible_new_order_samples']}→{c['eligible_new_order_samples']}", reasons[c['stock']]] for c in priority])
    lines += ["", "`needs_longer_ledger`는 호환용 재검사 표식으로 남겼다. 새 `calendar_extension_complete`, `remaining_pair_blockers`, "
        "`next_action`은 달력 확장 완료와 행 근거 보완을 구분한다. `evidence.order_pair_diagnostics`에는 가능한 각 분기 쌍의 적격 여부와 탈락 사유가 있다. "
        "새 보류 에스프리즘(288620)은 " + reasons["288620"], "",
        "기타 기존 표본 부족 회사도 전수 재검사했다. 한전산업의 중복 행, 한전KPS의 묶음·항등식, 오르비텍의 O&M 신규 동인, "
        "우진의 종료일 경과 잔고, 강원에너지의 중복 행, 부스타·티에스넥스젠의 수주 행 부재, 이성씨엔아이의 기준분기 부재·외화는 길이만으로 해소되지 않는다.", "",
        "## 단위 근거와 불확실성", "",
        "이번 입력에는 `knuke_unit_evidence.json`과 DART HTML·파서 코드가 없다. 2차 감사의 `reaudit.unit_contract`에 백만원 정규화 계약이 보존되어 있고, "
        "동일 회사·분기·공시번호·통화가 일치하는 과거 감사 캡션만 재사용했다. 추가 원장에는 같은 분기 `ok=true`, `cur=KRW`, `unit_seen=true`, "
        "`unit_from_prev=false`가 있을 때 **제공 파서 계약에 조건부 의존**한다. 확장 파일도 같은 정규화 계약을 따른다는 입력 연속성 가정이며, 원문 단위 검증 완료가 아니다.", "",
        f"금액 허용 {p['unit_evidence_quarters']} 회사분기 = 캡션 근거 {p['caption_backed_quarters']} + 파서 표식만 있는 {p['parser_only_quarters']}. "
        "캡션이 있는데 수량만 있거나 혼합통화이면 파서 표식으로 우회하지 않는다. 파서 표식이 거짓·누락이면 동일 공시의 단일 원화 단위 캡션 없이는 차단한다. "
        "한텍의 현재 단위만 이전 감사의 단일 백만원 캡션으로 복구했다. 과거 분기 단위를 빌리지 않았고 입력 금액을 재배율·환산하지 않았다.", "",
        f"더 엄격한 캡션 전용 진단에서는 {panel['captions_only_sensitivity']['status_counts']}이다. "
        "새 4사의 부분 추정은 파서 표식 근거에 의존한다. `captions_only_sensitivity`에 회사별 판정·적격 n·기준 연간값을 함께 실었다. "
        "모든 `raw_verified_at_origin`, `table_mapping_verified`, `normalization_code_independently_verified`는 false다. 단위 표식 자체의 오류 가능성은 민감도 범위가 보장하지 않는다.", "",
        "## 모델·전수 판정", "",
        "개별 날짜 계약은 기준분기 이후 잔여기간에 잔고를 균등 배분한다. 날짜 없는 적격 품목 행은 최근 최대 8개 관측 소진율의 중앙값 r로 "
        "`B×r×(1-r)^(h-1)`를 계산한다. 서비스·묶음·종료 후 양의 잔고에 회전율을 강제로 적용하지 않는다. "
        "신규수주 대용치는 `O=ΔB+분기납품`, 현재 행 구성과 같은 적격 쌍 최소 4개·현재 잔고 대조·자체 소진율이 필요하다. "
        "분기말 코호트 유입·다음 분기 인식 가정 아래 P25/P50/P75로 보수/기준/낙관을 나눈다. 음의 관측 O는 보존하고 미래 코호트 크기에만 0 하한을 적용한다.", "",
        "합계·소계는 제외하며 A=C+B, 중복 ID, 묶음, 별도/연결 경계, 누계 감소를 검사한다. 기존 엔진의 A=C+B 대수적 유도는 derived_fields에 남기고 "
        "유도한 납품을 실측 차분 표본에 쓰지 않는다. 보고서 총잔고·없는 분기·신규분·계약일·관측 납품의 빈칸을 추정치나 0으로 메우지 않는다. "
        "원청·하청·계열 간 금액 및 계약공시 금액을 합산하지 않으며 산업 총액을 만들지 않는다.", ""]
    lines += table(["종목·회사", "분기 수", "2차→3차 판정", "적격 n / 적합 n", "미충족 사유"], [
        [f"{c['stock']} {c['company_name']}", c['retry']['observed_quarter_count'],
         status[changes[c['stock']]['prior_status']] + "→" + status[c['status']],
         f"{c['retry']['eligible_new_order_sample_count']} / {c['retry']['fit_new_order_sample_count']}",
         ", ".join(c['amount_blocking_reason_codes']) or "없음(조건부 원장 모형)"] for c in panel['companies']])
    lines += ["", "## 분기·연간 추정과 민감도", "",
        "모든 25사에 T+1~T+10(2026Q3~2028Q4), FY2026~FY2028, 세 시나리오와 잔고분·신규분·민감도를 동일 JSON 구조로 제공한다. "
        "FY2026은 원장 Q1·Q2 관측 + Q3·Q4 추정, 2027·2028은 네 분기 추정 합이다. 12월 결산은 미검증 가정이다. "
        "날짜계약 기간 지수 0.75/1/1.25, 관측 소진율 최소~최대와 내부 극값, 신규수주 P10~P90의 민감도다. "
        "`calibrated=false`, `nominal_level=null`; 연간은 분기별 경계의 합이며 공동확률 구간이 아니다. 백테스트 결과로 범위·계절성·파라미터를 맞추지 않았다.", "",
        "전체 원장 조건부 연간값(백만원):", ""]
    lines += table(["회사", "시나리오", "FY2026", "FY2027", "FY2028"], [
        [c['company_name'], scenario, *[fmt(a['value']) for a in c['scenarios'][scenario]['annual']]]
        for c in panel['companies'] if c['status'] == 'full' for scenario in SCENARIOS])
    lines += ["", "일부 추정의 배분 가능한 **미래 잔고분만**(백만원). 첫 열은 2026 하반기이며 신규분·과거 관측분을 포함하지 않는다. "
        "신규분 미추정 회사는 세 시나리오의 알려진 잔고분이 동일하고 신규분은 null이다.", ""]
    lines += table(["회사", "2026 하반기", "2027 잔고분", "2028 잔고분"], [
        [c['company_name'], *[fmt(a['covered_sites_partial_revenue']) for a in c['scenarios']['base']['annual']]]
        for c in panel['companies'] if c['status'] == 'partial'])
    lines += ["", "## 2차 대비 회사별 값 변화", "",
        "큰 변화는 같은 회사·시나리오·연도·구성의 절대 변화율 20% 이상으로 정의했다(검증 성적과 무관하게 고정). "
        "기준 시나리오의 대표 큰 변화는 아래와 같으며 모든 시나리오·구성의 비교는 `reaudit.changes[].annual_changes`에 있다.", ""]
    large = []
    for c in panel['reaudit']['changes']:
        for a in c['annual_changes']:
            if a['scenario'] == 'base' and a['large_change'] and a['component'] == ('value' if c['status'] == 'full' else 'covered_sites_partial_revenue'):
                large.append([c['company_name'], f"FY{a['fiscal_year']}", a['component'], fmt(a['round2']), fmt(a['round3']), fmt(a['change_pct'])])
    lines += table(["회사", "연도", "비교 구성", "2차", "3차", "변화 %"], large)
    dk, st = changes['015590'], changes['077970']
    lines += ["", f"DKME: 신규수주 적격 n은 7→13, 적합은 7→8. 신규수주 중앙값 {fmt(dk['prior_new_order_assumption_base'])}→{fmt(dk['new_order_assumption_base'])}백만원/분기, "
        "소진율 중앙값 0.347044→0.332048로 바뀌었다. 2024Q3 표본이 최근 8개에 추가되며 신규분이 커진 결과다. "
        f"STX엔진은 적격 7→18, 적합 7→8, 신규수주 가정 {fmt(st['prior_new_order_assumption_base'])}→{fmt(st['new_order_assumption_base'])}; 부문별 소진율 변경도 반영됐다.", "",
        "강원에너지는 배분 가능한 2차전지 한 행의 소진율 표본이 4→5, 중앙값 0.699391→0.603723으로 내려가 잔고 인식이 뒤로 이동했다. "
        "2028 증가율은 작은 기저에서 발생하며 회사 전체 매출 변화가 아니다. 케일럼도 행별 최근 8개 소진율이 바뀌어 일부 잔고분이 줄었다. "
        "한전기술의 일부 소진율 참고치는 달라졌지만 추정 가능한 행은 날짜계약이므로 실제 잔고 인식 경로는 같다. 비에이치아이·한텍의 경로는 바뀌지 않았다.", "",
        "## 백테스트 표본과 오차", "",
        f"회사분기: 2차 113 → 기존 15사 확장 {comp['quarter_growth']['round3_original_companies']} → 25사 전체 {comp['quarter_growth']['round3_all_companies']}. "
        "원점은 2021Q4~2026Q1 중 해당 회사 원장이 있는 분기다. 각 원점까지 자료만으로 누적 의미·적합·모형을 다시 판정한다. "
        "T+1~T+8을 점수화하며 예측은 모두 기준 시나리오다. 잔고분의 표본 단위는 회사·원점·계약행·목표분기, 전체 원장은 회사·원점·목표분기다.", ""]
    lines += table(["대상", "2차 n", "기존15사 확장 n", "전체25사 n", "n 증가", "2차 WAPE %", "기존15사 확장 WAPE %", "전체 WAPE %", "전체 MAE 백만원"], [
        [label, old[key]['n'], expanded[key]['n'], bt[key]['n'], bt[key]['n']-old[key]['n'],
         fmt(old[key]['wape_pct']), fmt(expanded[key]['wape_pct']), fmt(bt[key]['wape_pct']), fmt(bt[key]['mae'])]
        for key, label in (("existing_contract", "동일 계약 잔고분"), ("total_ledger", "신규 포함 전체 원장"))])
    lines += ["", "지평별 표본 증가와 오차:", ""]
    lines += table(["지평", "잔고 n 2차→3차", "잔고 WAPE 2차→3차 %", "전체 n 2차→3차", "전체 WAPE 2차→3차 %", "3차 MAE 잔고 / 전체"], [
        [f"T+{h}", f"{old['by_horizon'][h]['existing_contract']['n']}→{v['existing_contract']['n']}",
         f"{fmt(old['by_horizon'][h]['existing_contract']['wape_pct'])}→{fmt(v['existing_contract']['wape_pct'])}",
         f"{old['by_horizon'][h]['total_ledger']['n']}→{v['total_ledger']['n']}",
         f"{fmt(old['by_horizon'][h]['total_ledger']['wape_pct'])}→{fmt(v['total_ledger']['wape_pct'])}",
         f"{fmt(v['existing_contract']['mae'])} / {fmt(v['total_ledger']['mae'])}"] for h, v in bt['by_horizon'].items()])
    lines += ["", f"잔고분 WAPE는 2차 {fmt(old['existing_contract']['wape_pct'])}% → 3차 {fmt(bt['existing_contract']['wape_pct'])}%, 전체 원장은 {fmt(old['total_ledger']['wape_pct'])}% → {fmt(bt['total_ledger']['wape_pct'])}%.",
        "정확도가 개선됐다고 주장하지 않는다. 표본 구성·원점이 달라진 비교이며, 표본 수 증가 자체가 성능 개선은 아니다. "
        f"음의 실측 잔고분 {bt['existing_contract']['negative_actual_n']}개도 제외하지 않았다. 빈 관측값을 채워 점수화한 표본은 0개다.", "",
        "## 연간 백테스트", "",
        "연말 Q4 원점의 FY+1(T+1~4)·FY+2(T+5~8) **네 분기 실측이 모두 있는 동일 범위**만 합산했다. "
        "이미 관측된 상반기를 섞는 당해연도 업데이트 오차와 구분한다. 잔고분 연간 표본도 동일 계약행 기준이며 회사 전체 매출이 아니다. "
        "2차 보고서에는 연간 오차가 없었다. 아래 ‘2차 재구성’은 기존 원장·동일 연간 채점 규칙으로 이번에 계산한 비교치다.", ""]
    lines += table(["대상", "2차 재구성 n", "기존15사 확장 n", "3차 n", "2차 재구성 WAPE %", "3차 WAPE %", "3차 MAE", "3차 Bias %"], [
        [label, old['annual'][key]['n'], expanded['annual'][key]['n'], bt['annual'][key]['n'],
         fmt(old['annual'][key]['wape_pct']), fmt(bt['annual'][key]['wape_pct']), fmt(bt['annual'][key]['mae']), fmt(bt['annual'][key]['bias_pct'])]
        for key, label in (("existing_contract", "동일 계약 연간 잔고분"), ("total_ledger", "연간 전체 원장"))])
    lines += [""] + table(["연간 지평", "잔고 n", "잔고 WAPE %", "전체 n", "전체 WAPE %"], [
        [f"FY+{y}", v['existing_contract']['n'], fmt(v['existing_contract']['wape_pct']), v['total_ledger']['n'], fmt(v['total_ledger']['wape_pct'])]
        for y, v in bt['annual']['by_lead_year'].items()])
    lines += ["", "회사별 분기·연간 검증 범위:", ""]
    lines += table(["회사", "분기 잔고 n / WAPE %", "분기 전체 n / WAPE %", "연간 잔고 n / WAPE %", "연간 전체 n / WAPE %"], [
        [c['company_name'], *[f"{b[key]['n']} / {fmt(b[key]['wape_pct'])}" for b in (c['backtest'], c['backtest']['annual']) for key in ('existing_contract', 'total_ledger')]]
        for c in panel['companies']])
    lines += ["", "WAPE=Σ|예측−실측|/Σ|실측|×100, MAE=Σ|예측−실측|/n.",
        "오차 집계는 성능 통계이며 기업 금액을 산업 매출로 합산한 것이 아니다. 회사·원점·행·지평이 겹쳐 표본은 독립적이지 않다. "
        "원장 열 제목·정정 전 빈티지와 정확한 당시 정보집합을 확인할 수 없어 분기 원장 순서의 회고 검증이다. 보고서는 분기말 후 공시되므로 "
        "분기말 실시간 투자 백테스트가 아니다. 최신 정정 원장 영향과 파서 표식 기반 단위 불확실성이 남는다. "
        "연간 전체 원장 검증은 여전히 소수 회사에 한정되며 FY2027·FY2028 실측 성적은 없다. 모든 채점 표본·제외 사유·분기 합산 내역은 JSON에 공개했다.", "",
        "## 재현·검증·인계", "",
        "```sh", "python3 -B output/knuke_forecast.py", "python3 -B output/forecast_section.py",
        "python3 -B -m unittest discover -s output -p 'test_knuke_forecast.py' -v", "```", "",
        "출력: forecast_panel.json·knuke_REPORT.md·forecast_section.py·knuke_forecast.py·test_knuke_forecast.py. "
        "보조 감사는 knuke_audit.json, 추정 회사 HTML은 sections/, 실행한 검증 결과는 test_results.txt에 있다. "
        "테스트는 기존 회귀검증을 유지하면서 19분기 게이트·단위 근거 등급·2차 복원·미래 데이터 비누출·연간 네 분기 완비·실제 점수 재계산을 확인한다. "
        "입력 SHA-256과 엔진 SHA-256을 패널에 기록했다.", "",
        "tracker preflight는 central_connection_failed로 소유권을 중앙에서 확인하지 못했다. 재시도·강제 인계 없이 지정 worker의 output/만 사용했다. "
        "정본·인증·자격증명 저장소는 변경하지 않았으며 자료 수집 네트워크·배포·외부 메시지·중첩 fleet 작업을 하지 않았다. coordinator가 통합한다.", ""]
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
