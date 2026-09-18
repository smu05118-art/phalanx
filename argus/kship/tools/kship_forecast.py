#!/usr/bin/env python3
"""Offline KSHIP reference engine. Standard library; never imports the KCE engine.

Round 2 extends the supplied R1 quarter, curve, metric, audit and collection helpers.
Native normalized ledger adapter; all amounts are reported-book-value proxies.
No network, packages, invented exchange rates or input mutations.
"""
import argparse
import calendar
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
VERSION = "kship-r2-1"
ORIGIN = "2026Q2"
AS_OF = "2026-09-18"
SCENARIOS = {"conservative": (0.25, 0.95), "base": (0.50, 1.0),
             "optimistic": (0.75, 1.05)}
EXPECTED_HISTORY = ["2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3",
                    "2025Q4", "2026Q1", "2026Q2"]
REASONS = {
    "missing_reports_file": "입력에 kship_reports.json 없음; 문서의 수집 완료는 원장이 아님",
    "unsupported_reports_schema": "원본 원장 구조 미검증; 명시적 중간 스키마 어댑터 필요",
    "company_reports_absent": "해당 회사 정기보고서 원장 없음",
    "origin_snapshot_absent": "기준분기 적격 원장 없음",
    "holding_overlap": "지주 발행인 계약과 자회사 운영 범위·계열 중복 미분리",
    "unknown_unit_or_currency": "표 단위·통화·unit_seen 근거 불충분",
    "insufficient_burn_history": "동일 범위 인접분기 소진율 표본 2개 미만",
    "insufficient_order_history": "환효과를 분리한 신규수주 분기 표본 4개 미만",
    "fx_basis_missing": "USD 환산율 또는 원화잔고의 USD 노출비중 근거 없음",
    "recognition_basis_missing": "진행기준/인도기준 수익인식 주석 근거 없음",
    "scope_incomplete": "전체 부문 포괄성 미확인; 부분만 계산 가능",
    "missing_observed_calendar_quarter": "연간 합산에 필요한 과거 분기 관측 누락",
    "future_component_unavailable": "미래 분기 잔고분 또는 신규분 근거 부족",
    "non_december_fiscal_unsupported": "12월 외 결산은 이 YTD 어댑터에서 미지원",
    "duplicate_snapshot": "동일 회사·분기 복수 원장; 임의 선택 금지",
    "invalid_snapshot": "날짜·부문키·보고범위 등 원장 계약 위반",
}


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def rounded(x):
    return round(x, 3) if number(x) else None


def qnum(q):
    if not isinstance(q, str) or not re.fullmatch(r"\d{4}Q[1-4]", q):
        raise ValueError("invalid quarter: " + str(q))
    return int(q[:4]) * 4 + int(q[-1]) - 1


def qadd(q, n):
    y, k = divmod(qnum(q) + n, 4)
    return f"{y:04d}Q{k + 1}"


def date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def qend(q):
    qnum(q)
    y, m = int(q[:4]), int(q[-1]) * 3
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def date_quarter(d):
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def quantile(values, p):
    values = sorted(v for v in values if number(v))
    if not values:
        return None
    at = (len(values) - 1) * p
    low, high = math.floor(at), math.ceil(at)
    return values[low] + (values[high] - values[low]) * (at - low)


def complete_sum(values):
    values = list(values)
    return rounded(sum(values)) if all(number(x) for x in values) else None


def interval(lo=None, hi=None, method="parameter_sensitivity_envelope"):
    return {"lower": rounded(lo), "upper": rounded(hi), "method": method,
            "nominal_level": None, "calibrated": False}



def curve(x, recognition):
    x = min(1.0, max(0.0, x))
    if recognition == "progress":
        return x * x * (3 - 2 * x)  # Explicit smoothstep prior, not fitted vessel progress.
    if recognition == "delivery":
        return 1.0 if x >= 1 else 0.0
    raise ValueError("unsupported recognition basis")


def cohort_path(order, duration, recognition, n=10):
    if not number(order) or not number(duration) or duration <= 0:
        return [(None, None)] * n
    if order < 0:
        raise ValueError("negative new cohort")
    out = []
    for h in range(1, n + 1):
        revenue = sum(order * (curve((h - issued) / duration, recognition)
                               - curve((h - issued - 1) / duration, recognition))
                      for issued in range(1, h + 1))
        backlog = sum(order * (1 - curve((h - issued) / duration, recognition))
                      for issued in range(1, h + 1))
        out.append((revenue, backlog))
    return out



def metric(records):
    if not records:
        return {"n": 0, "mae": None, "wape_pct": None, "bias_pct": None,
                "negative_actual_n": 0, "sample_warning": "실제 채점 표본 0; 정확도 평가 불가"}
    den = sum(abs(r["actual"]) for r in records)
    err = [r["prediction"] - r["actual"] for r in records]
    return {"n": len(records), "mae": rounded(statistics.mean(abs(e) for e in err)),
            "wape_pct": rounded(100 * sum(abs(e) for e in err) / den) if den else None,
            "bias_pct": rounded(100 * sum(err) / den) if den else None,
            "negative_actual_n": sum(r["actual"] < 0 for r in records),
            "sample_warning": "표본 20 미만; 성적 불안정" if len(records) < 20 else "중첩 표본; 독립 표본 아님"}



def contract_audit(rows, origin=ORIGIN):
    invalid, post_origin, valid_intervals, schedule = [], [], [], []
    all_rcps = {r.get("rcp") for r in rows}
    superseded = {r.get("supersedes") for r in rows if r.get("supersedes") in all_rcps}
    for row in rows:
        sd, ed, signed = date(row.get("start")), date(row.get("end")), date(row.get("signed"))
        rcp = str(row.get("rcp", ""))
        receipt = date(rcp[:4] + "-" + rcp[4:6] + "-" + rcp[6:8]) if len(rcp) >= 8 else None
        issue = [k for k, v in (("start", sd), ("end", ed), ("signed", signed), ("rcp_date", receipt)) if v is None]
        if sd and ed and ed < sd:
            issue.append("end_before_start")
        if issue:
            invalid.append({"rcp": rcp, "fields": issue,
                            "raw": {k: row.get(k) for k in ("start", "end", "signed")}})
        if receipt and receipt > qend(origin):
            post_origin.append(rcp)
        if sd and ed and ed >= sd:
            valid_intervals.append((ed - sd).days / 91.3125)
        if ed and row.get("type") not in (None, "OTHER") and rcp not in superseded:
            schedule.append({"rcp": rcp, "quarter": date_quarter(ed), "last_delivery_date": str(ed),
                             "type": row.get("type"), "units": row.get("ships"),
                             "unit_count_semantics": "contract_units_not_per_vessel_delivery_dates",
                             "published_after_origin": bool(receipt and receipt > qend(origin)),
                             "revenue": None})
    date_ranges = {}
    for key in ("start", "end", "signed"):
        dates = [date(r.get(key)) for r in rows if date(r.get(key))]
        date_ranges[key] = {"valid_rows": len(dates), "min": str(min(dates)) if dates else None,
                            "max": str(max(dates)) if dates else None}
    return {"rows": len(rows), "date_ranges": date_ranges,
            "aggregate_rows": 0, "aggregate_rows_basis": "contract_records_not_report_totals",
            "corrected_rows": sum(r.get("corrected") is True for r in rows),
            "supersedes_links": sum(bool(r.get("supersedes")) for r in rows),
            "superseded_rows_still_present": sorted(superseded),
            "post_origin_receipt_rows": len(post_origin), "post_origin_receipts": post_origin,
            "invalid_date_rows": invalid, "valid_contract_interval_rows": len(valid_intervals),
            "contract_period_not_build_duration": True,
            "declared_money_unit": "KRW_million via amt_krw_m field only",
            "amount_cells_present": sum(number(r.get("amt_krw_m")) for r in rows),
            "raw_caption_verified_rows": 0, "usd_contract_amount_rows": 0,
            "unit_verified_for_forecast": False,
            "schedule": schedule, "used_for_revenue_forecast": False,
            "schedule_warning": "종료일은 마지막 호선 인도; 개별 인도·진행률·잔여금액 없음",
            "series": {"status": "unavailable", "estimated": True,
                       "reason": "익명 상대 병합 위험; 옵션·동형 힌트는 사실상 시리즈 확인 아님",
                       "option_hint_rows": sum(r.get("option_hint") is True for r in rows)}}


def collection_tasks(company, snapshots, reason_codes):
    existing = {s.get("quarter") for s in snapshots if not s.get("issues")}
    tasks = []
    role = company["role"]
    for q in EXPECTED_HISTORY:
        tasks.append({"stock": company["stock"], "company_name": company["name"], "quarter": q,
                      "priority": "P0" if role == "yard" else "P1",
                      "action": "verify_and_complete" if q in existing else "collect_or_document_unavailable",
                      "report_type": "사업보고서" if q.endswith("Q4") else "반기보고서" if q.endswith("Q2") else "분기보고서",
                      "required_sections": ["II-4 수주상황/매출", "주석 수익", "II-5 위험관리 및 파생금융상품 주석", "연결·별도/부문 및 결산월"],
                      "required_fields": ["원문 표 위치·접수번호·공시일", "원문 단위 캡션·통화·unit_seen",
                                          "부문 ID·합계/소계·포괄범위", "연초잔고·YTD 신규·YTD 기납품·기말잔고",
                                          "실제 매출 YTD·진행률 수익인식 정책", "신규수주 내 환산·취소·변경 분리",
                                          "USD 계약명목·기준/인식 환율·환노출", "USD 매도 헤지명목·평균약정환율·만기·목적·합계/전기말 구분"],
                      "role_specific": {"yard": "개별 호선 인도/건조단계; 계약→부문 매핑; 마지막 호선만 있는 경우 그대로 표시",
                                        "holding": "발행인→실제 건조 자회사 매핑·연결 제거; 조선사 합계와 중복 금지",
                                        "engine": "엔진 호기·시운전/인도·매칭 선박·장납기 및 수익인식 시점",
                                        "equip": "선박 계통·제품별 조선 매출/잔고·장납기/회전·인도/검수 시점",
                                        "steel": "후판/형강 등 제품별 조선 노출·회전·단가/물량·수익인식 시점"}[role],
                      "special_check": "HJ 수주 절 제목 변형 대응" if company["stock"] == "097230" and q.endswith("Q4") else
                                       "삼성 합계 셀과 부문합 별도 대조" if company["stock"] == "010140" and q in ("2024Q4", "2025Q1") else None,
                      "availability_caution": "상장/보고서/공시의무가 없으면 해당 없음 근거 보존; 특히 대한조선 2025Q2 이전",
                      "acceptance": "같은 범위·단위로 YTD 차분/연초잔고 대조; 정정·합계·전기말 이중합산 금지",
                      "blocked_by": reason_codes})
    return tasks



def hashes(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.iterdir()) if p.is_file()}


# R2 native ledger adapter. Source fields are preserved; derived fields never fill them.
SCENARIOS = {"conservative": (.25, 1.0), "base": (.50, 1.0), "optimistic": (.75, 1.0)}
REASONS.update({
    "insufficient_segment_history": "동일 부문 유효 소진율 또는 순유입 표본 2개 미만",
    "book_value_only": "보고 장부환산액 기준 조건부 대용치; 미래 원화 회계매출 아님",
    "scope_unverified": "연결제거·부문 포괄성 또는 회사 회계매출 일치 미확인",
    "negative_net_inflow": "음수 순유입은 취소·환산 등을 포함; 신규 코호트는 분위수의 양수 부분만 가정",
})
COMMERCIAL = {"CONT", "LNGC", "VLCC", "PC", "VLGC", "BULK", "PCTC", "LPG", "LNG", "TANKER"}

def canonical(s):
    return re.sub(r"\s+", "", s or "")


def residual(a, b, c, d):
    return rounded(a + b - c - d) if all(number(x) for x in (a, b, c, d)) else None


def revenue_audit(raw):
    """Use first current-year column only; never sum subtotals and their children."""
    rev = raw.get("revenue", {})
    rows = rev.get("rows", [])
    groups = collections.defaultdict(list)
    for r in rows:
        groups[canonical(r.get("seg"))].append(r)
    values, issues = {}, []
    for seg, rs in groups.items():
        totals = [r for r in rs if r.get("kind") == "합계"]
        if len(totals) == 1 and totals[0].get("vals") and number(totals[0]["vals"][0]):
            v = totals[0]["vals"][0]
            children = [r["vals"][0] for r in rs if r.get("kind") != "합계" and r.get("vals")]
            # Null child is not zero. A reported total can stand independently.
            valid = True
            if children and all(number(x) for x in children) and abs(sum(children) - v) > 2:
                issues.append({"code": "revenue_subtotal_conflict", "segment": seg,
                               "reported": v, "children_sum": rounded(sum(children))})
                valid = False
            if valid and rev.get("cur") == "KRW":
                values[seg] = v
    grand = values.get("합계")
    leaves = [v for k, v in values.items() if k != "합계"]
    difference = rounded(sum(leaves) - grand) if leaves and number(grand) else None
    return {"values": values, "issues": issues, "reported_grand_ytd": grand,
            "leaf_minus_grand": difference, "period_cols": rev.get("period_cols", []),
            "basis": "first_current_period_column_YTD; no_previous_year_columns"}


def load_reports(path, evidence_path=None):
    if not path.exists():
        return {}, ["missing_reports_file"]
    raw = json.loads(path.read_text())
    evidence_path = evidence_path or path.with_name("kship_unit_evidence.json")
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    if not isinstance(raw.get("companies"), dict):
        return {}, ["unsupported_reports_schema"]
    out = {}
    for stock, company in raw["companies"].items():
        snapshots = []
        if stock != company.get("stock"):
            raise ValueError("company identity mismatch")
        for quarter, source in sorted(company.get("quarters", {}).items()):
            qnum(quarter)
            caption = source.get("raw_unit_caption")
            unit_ok = (bool(evidence.get("unit_contract")) and source.get("unit_seen") is True
                       and source.get("cur") == "KRW" and caption in
                       evidence.get("companies", {}).get(stock, {}).get(quarter, []))
            available = date(str(source.get("rcp", ""))[:4] + "-" + str(source.get("rcp", ""))[4:6]
                             + "-" + str(source.get("rcp", ""))[6:8])
            issues = []
            if not unit_ok:
                issues.append("unknown_unit_or_currency")
            if not available or available < qend(quarter) or source.get("ok") is not True:
                issues.append("invalid_snapshot")
            ra = revenue_audit(source)
            rows = []
            for r in source.get("segments", []):
                seg = canonical(r.get("seg"))
                n = {"segment_id": seg, "source_label": r.get("seg"), "source_fields": dict(r),
                     "unit_verified": unit_ok, "money_unit": "KRW_million",
                     "backlog": r.get("closing") if unit_ok and number(r.get("closing")) else None}
                roll = residual(r.get("opening"), r.get("new"), r.get("delivered"), r.get("closing"))
                gross = rounded(r["gross"] - r["delivered"] - r["closing"]) if all(number(r.get(k)) for k in ("gross", "delivered", "closing")) else None
                n.update(rollforward_residual=roll, gross_residual=gross,
                         flow_valid=unit_ok and (roll is None or abs(roll) <= 2) and (gross is None or abs(gross) <= 2))
                if stock == "010140":
                    n.update(recognition_basis="revenue_leaf_YTD", recognition_ytd=ra["values"].get(seg))
                elif stock == "097230":
                    n.update(recognition_basis="delivered_project_cumulative_same_year_difference_only",
                             recognition_ytd=None)
                else:
                    n.update(recognition_basis="delivered_YTD_proxy", recognition_ytd=r.get("delivered"))
                if not unit_ok:
                    n["recognition_ytd"] = None
                rows.append(n)
            ids = [r["segment_id"] for r in rows]
            if len(ids) != len(set(ids)) or not all(ids):
                issues.append("invalid_snapshot")
            comparisons = []
            for f, top in [("opening", "opening"), ("new", "new"), ("delivered", "delivered"), ("closing", "backlog"), ("gross", "gross")]:
                leaf = complete_sum(r["source_fields"].get(f) for r in rows) if rows and unit_ok else None
                total = source.get(top)
                comparisons.append({"field": f, "reported_total": total, "leaf_sum": leaf,
                                    "difference": rounded(leaf-total) if number(leaf) and number(total) else None,
                                    "selected_basis": "verified_leaves; reported_total_never_overwritten"})
            snapshots.append({"quarter": quarter, "available_on": str(available) if available else None,
                              "rcp": source.get("rcp"), "issues": issues, "rows": rows,
                              "raw_unit_caption": caption, "unit_verified": unit_ok,
                              "normalization_applied_here": 1, "reconciliations": comparisons,
                              "revenue_audit": ra, "fx": source.get("fx"), "hedge": source.get("hedge"),
                              "scope": "marine_segment" if stock == "097230" else "reported_segment_sum_uneliminated"})
        out[stock] = snapshots
    return out, []


def usable(snapshots, origin, as_of=AS_OF):
    return [s for s in snapshots if not s["issues"] and qnum(s["quarter"]) <= qnum(origin)
            and date(s["available_on"]) <= date(as_of)]


def recognition(history, q):
    row = history.get(q)
    if not row or not row["flow_valid"]:
        return None
    prev = history.get(qadd(q, -1))
    if row["recognition_basis"].startswith("delivered_project"):
        if q.endswith("Q1") or not prev or not prev["flow_valid"]:
            return None  # Never treat project-to-date recognized sums as YTD.
        a, b = row["source_fields"].get("delivered"), prev["source_fields"].get("delivered")
    else:
        a = row.get("recognition_ytd")
        if q.endswith("Q1"):
            return a if number(a) and a >= 0 else None
        b = prev.get("recognition_ytd") if prev and prev["flow_valid"] else None
    return a - b if number(a) and number(b) else None


def ledger_observations(snapshots):
    histories = collections.defaultdict(dict)
    for s in snapshots:
        for r in s["rows"]:
            histories[r["segment_id"]][s["quarter"]] = r
    result = {}
    for s in snapshots:
        result[s["quarter"]] = complete_sum(recognition(histories[r["segment_id"]], s["quarter"])
                                             for r in s["rows"]) if s["rows"] else None
    return result


def receipt_date(rcp):
    s = str(rcp)
    return date(s[:4] + "-" + s[4:6] + "-" + s[6:8])


def delivery_schedule(rows, origin):
    """Only snapshot records already filed at origin; missing prior corrections stay absent."""
    cut = qend(origin)
    candidates = [r for r in rows if receipt_date(r.get("rcp")) and receipt_date(r["rcp"]) <= cut]
    superseded = {r.get("supersedes") for r in candidates}
    schedule, rejected = [], collections.Counter()
    for r in rows:
        rd, start, end, signed = receipt_date(r.get("rcp")), date(r.get("start")), date(r.get("end")), date(r.get("signed"))
        why = None
        if not rd or rd > cut: why = "not_known_at_origin"
        elif r.get("rcp") in superseded: why = "superseded"
        elif not all((start, end, signed)) or end <= start: why = "invalid_dates"
        elif signed > cut: why = "signed_after_origin"
        elif end <= cut: why = "already_due"
        elif r.get("type") in (None, "OTHER"): why = "non_vessel_or_unknown_type"
        elif not number(r.get("ships")) or r["ships"] <= 0: why = "unknown_unit_count"
        if why:
            rejected[why] += 1
            continue
        schedule.append({"rcp": r["rcp"], "type": r["type"], "units": r["ships"],
                         "start": str(start), "end": str(end), "quarter": date_quarter(end),
                         "duration_quarters": (end-start).days/91.3125,
                         "weight_basis": "reported_contract_unit_count; not_value_or_individual_hull_dates",
                         "amount_used": False})
    return schedule, dict(rejected)


def match_segment(stock, seg, item):
    t = item["type"]
    if seg in {"조선해양", "선박"}: return True
    if seg == "상선": return t in COMMERCIAL
    if seg == "조선": return t in COMMERCIAL | {"NAVAL"}
    if seg == "특수선": return t == "NAVAL"
    if seg in {"해양및특수선", "EP및특수선"}: return t in {"OFFSH", "NAVAL"}
    if seg == "해양플랜트": return t == "OFFSH"
    return False


def fit_native(stock, snapshots, current, schedule):
    fits = []
    for row in current["rows"]:
        seg = row["segment_id"]
        hist = {s["quarter"]: r for s in snapshots for r in s["rows"] if r["segment_id"] == seg}
        burns, orders, excluded = [], [], []
        for q, r in hist.items():
            prev = hist.get(qadd(q, -1))
            recognized = recognition(hist, q)
            if prev and number(prev["backlog"]) and prev["backlog"] > 0 and number(recognized):
                rate = recognized/prev["backlog"]
                if 0 < rate <= 1:
                    burns.append({"quarter": q, "value": rate, "recognized": recognized,
                                  "opening_previous_quarter": prev["backlog"]})
                else:
                    excluded.append({"quarter": q, "reason": "burn_outside_0_1", "value": rate})
            sf = r["source_fields"]
            # Reported new is preferred when the YTD rollforward actually balances.
            oq = None
            if r["flow_valid"] and number(sf.get("new")):
                if q.endswith("Q1"):
                    oq = sf["new"]
                elif prev and prev["flow_valid"] and number(prev["source_fields"].get("new")):
                    oq = sf["new"]-prev["source_fields"]["new"]
                basis = "reported_new_YTD_difference_including_unseparated_adjustments"
            else:
                basis = "derived_delta_backlog_plus_recognition; not_gross_USD_orders"
                if r["flow_valid"] and prev and prev["flow_valid"] and all(number(x) for x in (r["backlog"], prev["backlog"], recognized)):
                    oq = r["backlog"]-prev["backlog"]+recognized
            if number(oq): orders.append({"quarter": q, "value": oq, "basis": basis})
        sched = [x for x in schedule if match_segment(stock, seg, x)]
        eligible = number(row["backlog"]) and row["backlog"] >= 0 and len(burns) >= 2 and len(orders) >= 2
        fits.append({"segment_id": seg, "backlog": row["backlog"], "eligible": eligible,
                     "burn_samples": burns, "net_inflow_samples": orders, "excluded_samples": excluded,
                     "schedule": sched, "duration_basis": "median_observed_contract_period" if sched else "inverse_median_burn_proxy",
                     "recognition_basis": row["recognition_basis"], "source_rollforward_residual": row["rollforward_residual"],
                     "reason_codes": [] if eligible else ["insufficient_segment_history"]})
    return fits


def schedule_fraction(schedule, origin, horizon):
    numer, denom = 0.0, 0.0
    for s in schedule:
        start, end = date(s["start"]), date(s["end"])
        days = (end-start).days
        at0 = curve((qend(origin)-start).days/days, "progress")
        at1 = curve((qend(qadd(origin, horizon))-start).days/days, "progress")
        denom += s["units"] * (1-at0)
        numer += s["units"] * (at1-at0)
    return numer/denom if denom > 0 else None


def native_path(fit, origin, order_p, burn_p=.5, schedule_weight=.5, duration_scale=1.0):
    if not fit["eligible"]:
        return None
    rate = quantile([x["value"] for x in fit["burn_samples"]], burn_p)
    raw_order = quantile([x["value"] for x in fit["net_inflow_samples"]], order_p)
    order = max(0.0, raw_order)  # Explicit scenario floor, never an observed zero or missing-data fill.
    duration = quantile([x["duration_quarters"] for x in fit["schedule"]], .5) if fit["schedule"] else 1/rate
    duration = max(1.0, duration * duration_scale)
    cohort = cohort_path(order, duration, "progress", 10)
    path, previous = [], 0.0
    for h in range(1, 11):
        empirical = 1-(1-rate)**h
        scheduled = schedule_fraction(fit["schedule"], origin, h)
        cumulative = empirical if scheduled is None else (1-schedule_weight)*empirical+schedule_weight*scheduled
        existing = fit["backlog"]*(cumulative-previous)
        previous = cumulative
        path.append({"quarter": qadd(origin, h), "existing": existing, "new": cohort[h-1][0],
                     "new_backlog": cohort[h-1][1], "orders": order,
                     "remaining_existing": fit["backlog"]*(1-cumulative), "burn_fraction": cumulative})
    return path


def aggregate_path(fits, origin, order_p, burn_p=.5, weight=.5, duration_scale=1.0):
    paths = [native_path(f, origin, order_p, burn_p, weight, duration_scale) for f in fits if f["eligible"]]
    if not paths:
        return None
    return [{k: sum(path[i][k] for path in paths) for k in
             ("existing", "new", "new_backlog", "orders", "remaining_existing")} for i in range(10)]


def fx_evidence(current):
    h = (current or {}).get("hedge") or {}
    fx = (current or {}).get("fx") or {}
    usd_column = {}
    columns = fx.get("cols", [])
    usd_indices = [i-1 for i, c in enumerate(columns) if re.search(r"\bUSD\b", c)]
    if fx.get("cur") == "KRW" and len(usd_indices) == 1 and usd_indices[0] >= 0:
        for r in fx.get("rows", []):
            vals = r.get("vals", [])
            if len(vals) == len(columns)-1 and number(vals[usd_indices[0]]):
                usd_column[canonical(r.get("label"))] = vals[usd_indices[0]]
    # Preserve supplied nominal aggregate; never re-sum items, purposes or vintages.
    evidence = {"usd_sell_m_reported": h.get("usd_sell_m"), "usd_buy_m_reported": h.get("usd_buy_m"),
                "nominal_money_unit": "USD_million", "aggregate_verified_from_original": False,
                "hedge_shape": h.get("shape"), "hedge_avg_rate_reported_krw_per_usd": h.get("avg_rate"),
                "hedge_avg_rate_is_spot": False, "hedge_ratio": None, "future_fx_rate": None,
                "fx_table_currency": fx.get("cur"), "fx_columns": fx.get("cols", []),
                "fx_table_rows": fx.get("rows", []), "fx_table_used_to_derive_rate": False,
                "usd_exposure_column_krw_million": usd_column,
                "usd_exposure_column_is_usd_nominal": False,
                "model_fx_policy": "reported_KRW_book_basis_no_retranslation; no_assumed_spot_or_forward_rate",
                "warning": "USD 수주와 KRW 매출의 기간·노출·헤지 만기 대응 없음. 명목액은 헤지비율이 아니며 약정환율은 현물환율이 아님."}
    if fx.get("cur") == "USD" and any("평균약정환율" in x for x in fx.get("cols", [])):
        evidence["fx_parse_warning"] = "mixed_rate_and_amount_columns; cell_scaling_and_column_alignment_unverified; not_usable_as_exchange_rates"
    return evidence


def project_native(company, snapshots, contracts, origin=ORIGIN, as_of=AS_OF):
    valid = usable(snapshots, origin, as_of)
    current = next((s for s in valid if s["quarter"] == origin), None)
    schedule, schedule_exclusions = delivery_schedule(contracts, origin)
    reasons = []
    if not snapshots: reasons.append("company_reports_absent")
    if not current: reasons.append("origin_snapshot_absent")
    if company["role"] == "holding":
        reasons.append("holding_overlap")
        current = None
    fits = fit_native(company["stock"], valid, current, schedule) if current else []
    eligible = [f for f in fits if f["eligible"]]
    if fits:
        reasons.extend(["book_value_only", "scope_unverified"])
        if len(eligible) != len(fits): reasons.append("insufficient_segment_history")
        if any(x["value"] < 0 for f in fits for x in f["net_inflow_samples"]): reasons.append("negative_net_inflow")
    observations = ledger_observations(valid)
    full = bool(fits) and len(eligible) == len(fits)
    out = {"stock": company["stock"], "company_id": company["stock"], "company_name": company["name"],
           "role": company["role"], "source": "kship_universe", "origin": origin,
           "status": "partial" if eligible else "unavailable", "reason_codes": reasons,
           "money_unit": "KRW_million", "financial_statement_revenue": False,
           "value_semantics": "uneliminated_reported_scope_book_value_recognition_proxy",
           "modeled_flow_scope": "new_orders_new_backlog_remaining_existing_and_covered_fields_are_eligible_segments_only",
           "fiscal_year_end_month": 12, "fiscal_basis": "calendar_FY_requested; December_close_not_independently_verified",
           "scope": current["scope"] if current else "unknown", "unit_audit": {"verified_at_origin": bool(current and current["unit_verified"]),
           "scale_applied": 1, "basis": "supplied_kship_unit_evidence; already_normalized_millions"},
           "coverage": {"group_additive": False, "full_reported_scope_model": full,
                        "modeled_segments": [f["segment_id"] for f in eligible],
                        "excluded_segments": [f["segment_id"] for f in fits if not f["eligible"]],
                        "reported_backlog": complete_sum(f["backlog"] for f in fits) if fits else None,
                        "modeled_backlog": complete_sum(f["backlog"] for f in eligible) if eligible else None},
           "evidence": {"segments": fits}, "observed_ledger_proxy": observations,
           "reported_revenue_reference_ytd": {s["quarter"]: s["revenue_audit"]["reported_grand_ytd"] for s in valid},
           "industry_axes": {"schedule": schedule, "schedule_exclusions": schedule_exclusions,
                             "schedule_used_for_runoff": any(f["schedule"] for f in eligible),
                             "schedule_coverage_value_ratio": None, "schedule_mapping_is_assumption": True,
                             "schedule_warning": "계약 종료일은 마지막 호선 인도 예정. 진행기준 매출 분기와 다름. 척수 가중은 금액 비중 아님.",
                             "fx": fx_evidence(current), "hedge_ratio": None}, "scenarios": {}}
    variants = []
    if eligible:
        for bp in (.1, .5, .9):
            for op in (.1, .25, .5, .75, .9):
                for w in (0.0, .5, 1.0):
                    for ds in (.8, 1.0, 1.2):
                        variants.append(aggregate_path(fits, origin, op, bp, w, ds))
    for key, (p, _) in SCENARIOS.items():
        path = aggregate_path(fits, origin, p)
        qs = []
        for i in range(10):
            a = path[i] if path else {}
            e, n = rounded(a.get("existing")), rounded(a.get("new"))
            val = complete_sum([e, n])
            bounds = interval(min(v[i]["existing"]+v[i]["new"] for v in variants),
                              max(v[i]["existing"]+v[i]["new"] for v in variants)) if variants else interval()
            qs.append({"quarter": qadd(origin, i+1), "horizon": i+1,
                       "value": val if full else None, "existing_backlog_revenue": e if full else None,
                       "new_order_revenue": n if full else None,
                       "covered_scope_value": val, "covered_sites_partial_revenue": e,
                       "covered_scope_new_revenue": n, "covered_scope_interval": bounds,
                       "interval": bounds if full else interval(),
                       "new_orders": rounded(a.get("orders")), "new_order_backlog": rounded(a.get("new_backlog")),
                       "remaining_existing_backlog": rounded(a.get("remaining_existing")),
                       "reason_codes": reasons, "status": "conditional_book_proxy" if val is not None else "unavailable"})
        annual = []
        for year in range(int(origin[:4]), int(origin[:4])+3):
            historical = [f"{year}Q{k}" for k in range(1,5) if qnum(f"{year}Q{k}") <= qnum(origin)]
            indices = [i for i,r in enumerate(qs) if r["quarter"].startswith(str(year))]
            obs = complete_sum(observations.get(q) for q in historical)
            es = complete_sum(qs[i]["existing_backlog_revenue"] for i in indices)
            ns = complete_sum(qs[i]["new_order_revenue"] for i in indices)
            covered_e = complete_sum(qs[i]["covered_sites_partial_revenue"] for i in indices)
            covered_n = complete_sum(qs[i]["covered_scope_new_revenue"] for i in indices)
            value = complete_sum([obs, es, ns]) if len(historical)+len(indices)==4 else None
            sensitivity = [sum(v[i]["existing"]+v[i]["new"] for i in indices) for v in variants]
            bounds = interval(obs+min(sensitivity), obs+max(sensitivity)) if sensitivity and number(obs) and full else interval()
            annual.append({"fiscal_year": year, "value": value, "observed_revenue": obs,
                           "observed_basis": "same_model_ledger_proxy; not_financial_statement_revenue",
                           "existing_backlog_revenue": es, "new_order_revenue": ns,
                           "covered_future_existing": covered_e, "covered_future_new": covered_n,
                           "covered_future_value": complete_sum([covered_e,covered_n]),
                           "covered_future_interval": interval(min(sensitivity),max(sensitivity)) if sensitivity else interval(),
                           "interval": bounds, "reason_codes": [] if value is not None else ["missing_observed_calendar_quarter" if obs is None else "future_component_unavailable"]})
        out["scenarios"][key] = {"assumptions": {"order_quantile": p, "fx_multiplier": None,
            "fx_rate": None, "fx_policy": "reported_KRW_book_basis; future_FX_effect_unestimated",
            "order_basis": "positive_part_of_empirical_net_replenishment; includes_unseparated_FX_cancellations",
            "zero_floor_is_model_assumption": True, "schedule_blend": .5,
            "schedule_blend_basis": "explicit_unfitted_prior; sensitivity_0_0.5_1",
            "minimum_history_samples": 2, "new_order_arrival": "quarter_end; first_recognition_next_quarter",
            "progress_curve": "R1_smoothstep_unfitted; contract_period_not_actual_build_stage",
            "sensitivity_grid": {"burn_quantiles": [.1,.5,.9], "order_quantiles": [.1,.25,.5,.75,.9],
                                 "schedule_weights": [0,.5,1], "duration_scales": [.8,1,1.2]},
            "calibrated": False}, "quarterly": qs, "annual": annual}
    return out

def backtest_native(universe, reports, contracts):
    records, annual_records, exclusions = [], [], collections.Counter()
    for company in universe:
        stock = company["stock"]
        snapshots = usable(reports.get(stock, []), ORIGIN)
        if not snapshots or company["role"] == "holding":
            exclusions["company_without_eligible_ledger"] += 1
            continue
        target_actuals = ledger_observations(snapshots)
        for s in snapshots[:-1]:
            origin = s["quarter"]
            train = usable(snapshots, origin, s["available_on"])
            schedule, _ = delivery_schedule([r for r in contracts if r["stock"] == stock], origin)
            fits = fit_native(stock, train, s, schedule)
            if not fits or not all(f["eligible"] for f in fits):
                exclusions["training_scope_incomplete"] += 1
                continue
            pred = aggregate_path(fits, origin, .5)
            scored = {}
            for target in snapshots:
                h = qnum(target["quarter"]) - qnum(origin)
                if not 1 <= h <= 10: continue
                if sorted(r["segment_id"] for r in target["rows"]) != sorted(f["segment_id"] for f in fits):
                    exclusions["target_segment_scope_changed"] += 1
                    continue
                actual = target_actuals.get(target["quarter"])
                if not number(actual):
                    exclusions["unobserved_or_invalid_target"] += 1
                    continue
                value = rounded(pred[h-1]["existing"]+pred[h-1]["new"])
                r = {"company_id": stock, "origin": origin, "information_cutoff": s["available_on"],
                     "contract_cutoff": str(qend(origin)), "quarter": target["quarter"], "horizon": h,
                     "prediction": value, "actual": actual, "target_basis": "observed_ledger_proxy",
                     "training_quarters": [v["quarter"] for v in train], "schedule_rcps": [v["rcp"] for v in schedule]}
                records.append(r)
                scored[target["quarter"]] = r
            for year in range(int(origin[:4])+1, int(ORIGIN[:4])+1):
                qs = [f"{year}Q{k}" for k in range(1,5)]
                if all(q in scored for q in qs):
                    annual_records.append({"company_id": stock, "origin": origin, "fiscal_year": year,
                        "prediction": complete_sum(scored[q]["prediction"] for q in qs),
                        "actual": complete_sum(scored[q]["actual"] for q in qs)})
    return {"quarterly": metric(records), "annual": metric(annual_records),
            "by_horizon": {str(h):metric([r for r in records if r["horizon"]==h]) for h in range(1,11)},
            "records": records, "annual_records": annual_records, "exclusions": dict(exclusions),
            "calibrated": False, "filled_cells_scored": 0,
            "method": "rolling_origin_retrospective_reported_scope_proxy; base_same_engine",
            "vintage_policy": "quarter_and_report_date_gated; latest_contract_snapshot_survivorship_and_revision_bias_unresolved",
            "strict_real_time": False, "independent_holdout": False,
            "schema_policy_basis": "developed_after_auditing_full_supplied_input; not_independent_holdout",
            "sample_warning": "최대 8분기뿐인 소표본·중첩 예측. 보정·모델선택·장기 정확도 검증 불가. 공시일이 다음 분기 중간일 수 있음."}


def report_text(panel):
    pop, bt = panel['population'], panel['backtest']
    lines = ['# ARGUS-kship 2차 전수 추정', '',
      f"기준 {ORIGIN}; 41사 전수 감사. 원장 5사 **35개 회사·분기**, 추정 가능한 범위 {pop['estimated_companies']}사, 미추정 {pop['unestimated_companies']}사.",
      '수치는 **백만원**. 결과는 검증 가능한 부문의 보고 장부액 소진 및 순유입 조건부 대용치다. 회사 회계매출 전망으로 인증하지 않는다. `partial`은 범위·회계연결 한계가 남았다는 뜻이며, `value`는 모든 현재 원장 부문이 계산될 때만 제공한다.', '',
      '## 계산 기준', '',
      '- 1차 엔진의 분기 연산·smoothstep 코호트·지표·계약 감사 및 HTML 표/SVG를 이어 사용하고, 새 원장 어댑터를 추가했다. 1차 감사 328개 수집 항목은 재생성하지 않고 JSON에서 원본 항목에 2차 상태를 붙였다.',
      '- `kship_unit_evidence.json`의 정규화 계약을 적용했다. 근거로 제공된 kce_parse.py:197–207, 345·357·359행은 이 작업에 원문 코드가 없으므로 독립 검증하지 않았다. 이미 백만원이므로 배율은 항상 1이다. 원문 캡션을 다시 곱하지 않는다.',
      '- 부문 기초+신규−기납품−기말과 gross−기납품−기말을 대조한다. 2백만원 이하 차이는 정수 표의 반올림 허용치다. 초과 잔차는 남기고 해당 흐름 표본을 제외한다. 원문 합계는 덮어쓰지 않는다.',
      '- 삼성은 누적 프로젝트 기납품을 YTD로 오인하지 않고 검증된 부문 매출 YTD를 차분한다. HJ는 같은 해 인접 분기의 기납품 차분만 사용하고 Q1·누락 연말은 채우지 않는다. 다른 세 회사는 롤포워드 기납품 YTD 대용치를 차분한다. 부문명은 공백만 정규화하며 재편 부문을 임의 연결하지 않는다.',
      '- 신규가 있으면 균형이 맞는 표의 YTD 차분, 없으면 Δ기말잔고+인식액을 **순유입 대용치**로 계산한다. 환산·취소·범위변동을 분리한 달러 신규수주가 아니다. 음수 관측도 표본에 보존하고, 시나리오의 신규 코호트 투입은 분위수의 양수 부분(max(0,Qp))으로 가정한다. 이는 신규 순유입의 조건부 가정이며 취소 위험을 별도로 예측한 값이 아니다.',
      '- 선표: 계약 접수일·서명일이 기준분기말 이전이고 유효한 시작·종료일·척수가 있는 미인도 계약만 사용한다. 계약 금액은 단위/환산을 별도 인증하지 못해 사용하지 않는다. 지주 계약을 자회사에 붙이지 않는다. 최신 정정본만 남은 자료의 생존편향은 해소하지 못했다.',
      '- **진행기준이므로 인도 분기 ≠ 매출 분기.** 계약 종료일은 마지막 호선 인도 예정이며 개별 호선 인도일이 아니다. 잔고 배분은 관측 소진율의 기하 소진 50% + 척수 가중 smoothstep 잔여 공정곡선 50%의 미보정 가정이다. 선표가 없는 부문은 관측 소진율만 사용한다. 선종→부문 매핑, 계약기간→공정기간, 척수→잔고 비중은 모두 가정이며 선표의 금액 커버리지는 미상이다.',
      '- 신규 코호트는 분기말 유입, 다음 분기부터 smoothstep 인식. 기간은 해당 선표 계약기간 중앙값, 선표가 없으면 소진율 역수 대용치다. 보수/기준/낙관은 순유입 Q25/Q50/Q75이며 성장률·환율을 추가하지 않는다.',
      '- 민감도는 소진율 Q10/Q50/Q90 × 순유입 Q10/Q25/Q50/Q75/Q90 × 선표 가중 0/0.5/1 × 기간 0.8/1/1.2의 135개 경로 범위다. 연간 범위는 각 경로를 먼저 합친 뒤 min/max를 구한다. 통계적 신뢰구간이 아니며 **calibrated=false**. 환위험·누락 부문·연결제거·취소 전반을 포괄하는 구간은 아니다.',
      '- FY2026 = Q1·Q2의 같은 범위 관측 대용치 + Q3·Q4 추정. FY2027·FY2028은 각 4분기 추정 합. 관측 분기가 빠지면 전체는 null, 확인 가능한 미래 구성분은 따로 제공한다. HJ FY2026 Q1은 누적 기납품에서 알 수 없어 null이다.',
      '- HD한국조선해양(009540)은 `holding_overlap`으로 미추정. 모든 회사에 group_additive=false를 두고 회사간·그룹 합계는 만들지 않았다.', '',
      '## 환과 헤지', '',
      '수주의 달러 경제노출과 원화 매출은 구분한다. 모델은 이미 보고된 KRW 장부환산액을 재환산하지 않는 조건부 기준이다. 미래 현물환율·선도환율·환민감도 배수는 null이며, 미래 원화 회계매출에 대한 환 조정은 계산하지 않는다. USD 매도 명목액을 원화 잔고로 나누어 헤지비율을 만들지 않는다. 만기·헤지대상·기간별 회계배분이 없어서 명목액과 약정환율만으로도 유효 헤지비율을 알 수 없다.',
      '한화의 fx 표는 평균약정환율과 금액이 섞여 셀 배율·열 대응을 검증할 수 없으므로 환율 원천으로 사용할 수 없다. hedge.avg_rate만 공시 약정환율 참고로 표시하며 미래 환율로 사용하지 않는다. HD/대한의 fx 표는 원화 표시 외화자산·부채 표이지 USD/KRW 환율 표가 아니다. hedge의 전기/당기 및 목적별 합산을 독립 검증하지 못해 제공된 집계값을 그대로 참고로 보존한다.', '',
      '|회사|USD 매도 명목액(백만USD, 입력 집계)|공시 약정환율(원/USD)|환 테이블|USD열 순노출(원화 백만원)|', '|---|---:|---:|---|---:|']
    for c in panel['companies']:
        if c['stock'] in panel['audit']['ledger_company_ids']:
            f=c['industry_axes']['fx']
            lines.append(f"|{c['company_name']}|{f['usd_sell_m_reported']}|{f['hedge_avg_rate_reported_krw_per_usd']}|{f['fx_table_currency']}|{f['usd_exposure_column_krw_million'].get('순노출')}|")
    lines += ['', '## 재감사와 범위', '', '|회사|분기 수|상태|계산 부문 / 제외 부문|기준 잔고(부문합)|', '|---|---:|---|---|---:|']
    for c in panel['companies']:
        a=c['audit']; cov=c['coverage']
        lines.append(f"|{c['company_name']} ({c['stock']})|{a['quarter_count']}|{c['status']}|{', '.join(cov['modeled_segments']) or '—'} / {', '.join(cov['excluded_segments']) or '—'}|{cov['reported_backlog']}|")
    lines += ['', '주요 원장 불일치(입력 값을 보존; 모든 분기 감사는 JSON audit.snapshots):', '']
    for c in panel['companies']:
        for s in c['audit']['snapshots']:
            for r in s['reconciliations']:
                if number(r['difference']) and abs(r['difference'])>2:
                    lines.append(f"- {c['company_name']} {s['quarter']} {r['field']}: 원문합계 {r['reported_total']}, 부문합 {r['leaf_sum']}, 차이 {r['difference']}.")
            for r in s['rows']:
                for field in ('rollforward_residual','gross_residual'):
                    if number(r[field]) and abs(r[field])>2:
                        lines.append(f"- {c['company_name']} {s['quarter']} {r['segment_id']} {field}: {r[field]} (흐름 표본 제외).")
            for issue in s['revenue_audit']['issues']:
                lines.append(f"- {c['company_name']} {s['quarter']} 매출 소계 불일치: {json.dumps(issue,ensure_ascii=False)}.")
    lines += ['', '삼성 매출 부문합과 회사 합계 차이는 연결제거/파싱/범위 차이를 구분할 수 없어 회사 합계로 승격하지 않는다. 한화 EP 및 특수선은 과거 해양·플랜트 부문과 임의 병합하지 않는다. HJ 원장은 조선부문만이며 회사전체가 아니다. 대한조선은 상위 금액이 비어 있어도 균형이 맞는 원문 부문값은 계산 가능하다.', '',
      '## 과거 검증', '',
      f"분기 채점 **{bt['quarterly']['n']}개**, 연간 **{bt['annual']['n']}개**. 분기 MAE {bt['quarterly']['mae']}백만원, WAPE {bt['quarterly']['wape_pct']}%, bias {bt['quarterly']['bias_pct']}%. 최대 8분기 이력의 적은 중첩 표본이므로 장기 정확도나 신뢰구간 보정 근거가 아니다.",
      '학습에는 origin 이하·해당 보고서 공시일 이하 자료만 넣었다. 원장 부문 집합이 달라진 목표·오류/누락 목표는 제외했다. 채점 대상은 실제 입력으로 계산한 같은 범위 인식 대용치이며 신규+잔고 총모델을 채점했다. 관측 매출이 없는 기간을 0으로 만들지 않았다. 현재 보존된 과거 원장과 계약 정정본을 사용하므로 엄격한 실시간 투자 백테스트는 아니다. 스키마·부문 처리 규칙은 전체 입력 감사 후 정했으므로 독립 holdout 검증도 아니다.', '',
      '|horizon|분기 n|WAPE %|', '|---|---:|---:|']
    for h,m in bt['by_horizon'].items(): lines.append(f"|T+{h}|{m['n']}|{m['wape_pct']}|")
    lines += ['', '## 기준 시나리오 연간 결과', '', '|회사|연도|전체 대용치|관측 대용치|미래 잔고분|미래 신규분|미래 계산 가능 범위 합|', '|---|---|---:|---:|---:|---:|---:|']
    for c in panel['companies']:
        if c['status']=='unavailable': continue
        for a in c['scenarios']['base']['annual']:
            lines.append(f"|{c['company_name']}|FY{a['fiscal_year']}|{a['value']}|{a['observed_revenue']}|{a['existing_backlog_revenue']}|{a['new_order_revenue']}|{a['covered_future_value']}|")
    lines += ['', 'null/None는 미상이며 0이 아니다. 한화의 계산 가능 범위 합은 제외 부문을 포함하지 않는다. 3종 시나리오의 T+1~T+10 전체 수치·잔고/신규 분해·민감도는 forecast_panel.json과 회사 HTML에 수록했다.', '',
      '## 재현과 남은 확인', '', '```sh', 'python3 -B output/kship_forecast.py --input input --output output',
      'python3 -B output/forecast_section.py --panel output/forecast_panel.json --output output/sections',
      'python3 -B -m unittest discover -s output -p test_kship_forecast.py -v', '```', '',
      '남은 확인은 누락 5개 회사·분기와 원장 없는 36사, 원장 부문 재편·대규모 잔차, 삼성 소계·연결제거, 달러 신규수주와 환조정 분리, 개별 호선 진행률 및 헤지 만기/회계배분이다. 입력 파일·정본은 수정하지 않았고 네트워크·외부 패키지·배포를 사용하지 않았다. tracker는 SSH 방식이므로 이번 네트워크 금지 범위에서 실행하지 않았다.']
    return '\n'.join(lines)+'\n'


def build(input_dir, output_dir):
    before = hashes(input_dir)
    universe = json.loads((input_dir/'kship_universe.json').read_text())['rows']
    if len({c['stock'] for c in universe}) != len(universe): raise ValueError('duplicate company')
    contracts = json.loads((input_dir/'kship_contracts.json').read_text())['rows']
    reports, issues = load_reports(input_dir/'kship_reports.json')
    prior = json.loads((input_dir/'kship_audit.json').read_text())
    prior_companies = {c['company_id']: c for c in prior['companies']}
    companies=[]
    bt=backtest_native(universe,reports,contracts)
    for c in universe:
        stock=c['stock']; snaps=reports.get(stock,[])
        f=project_native(c,snaps,[r for r in contracts if r['stock']==stock])
        company_scores=[r for r in bt['records'] if r['company_id']==stock]
        f['backtest']={'quarterly_n':len(company_scores), 'metrics':metric(company_scores), 'sample_warning':bt['sample_warning']}
        old=prior_companies[stock]
        tasks=[]
        for task in old['collection_tasks']:
            tasks.append({**task,'round2_disposition':'provided_verify_remaining_fields' if any(s['quarter']==task['quarter'] for s in snaps) else 'still_missing; do_not_fill'})
        ca=contract_audit([r for r in contracts if r['stock']==stock])
        ca['unfiltered_reference_schedule']=ca.pop('schedule')
        ca['used_for_revenue_forecast']=f['industry_axes']['schedule_used_for_runoff']
        ca['use_semantics']='dates_and_unit_counts_only_for_book_runoff_timing; contract_amounts_unused'
        ca['used_schedule_rcps']=sorted({r['rcp'] for fit in f['evidence']['segments'] if fit['eligible'] for r in fit['schedule']})
        f['audit']={'quarter_count':len(snaps),'missing_quarters':[q for q in EXPECTED_HISTORY if not any(s['quarter']==q for s in snaps)],
                    'snapshots':snaps,'prior_reason_codes':old['reason_codes'], 'collection_tasks':tasks,
                    'contract_audit':ca}
        companies.append(f)
    counts=collections.Counter(c['status'] for c in companies)
    population={'input_companies':len(universe),'ledger_companies':len(reports),
                'status_counts':{s:counts[s] for s in ('full','partial','unavailable')},
                'estimated_companies':counts['full']+counts['partial'],'unestimated_companies':counts['unavailable']}
    panel={'schema_version':VERSION,'assignment':'ARGUS-kship round2','origin':ORIGIN,'as_of':AS_OF,
           'money_unit':'KRW_million','forecast_quarters':[qadd(ORIGIN,h) for h in range(1,11)],
           'input_sha256':before,'engine_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'round1_reuse':{'engine':before['kship_forecast.py'],'section':before['forecast_section.py'],'audit':before['kship_audit.json']},
           'population':population,'backtest':bt,'calibrated':False,'company_aggregation_permitted':False,
           'limitations':['진행기준: 인도 분기 ≠ 매출 분기','book_value_proxy_not_future_nominal_KRW_revenue',
                          'net_inflow_not_clean_USD_orders','holding_overlap_no_group_sum','small_sample_uncalibrated'],
           'audit':{'global_issues':issues,'ledger_company_ids':sorted(reports),'actual_snapshot_count':sum(map(len,reports.values())),
                    'expected_yard_snapshot_count':40,'prior_collection_task_count':prior['collection_task_count'],
                    'missing_company_quarters':sum(len(c['audit']['missing_quarters']) for c in companies)},'companies':companies}
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/'forecast_panel.json').write_text(json.dumps(panel,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (output_dir/'kship_REPORT.md').write_text(report_text(panel))
    if hashes(input_dir)!=before: raise RuntimeError('input mutated')
    return {'population':population,'backtest_n':bt['quarterly']['n'],'annual_backtest_n':bt['annual']['n'],
            'input_unchanged':True,'quarterly_rows':len(universe)*30,'annual_rows':len(universe)*9}


def main():
    root=Path(__file__).resolve().parent.parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=root/'input')
    parser.add_argument('--output',type=Path,default=root/'output')
    args=parser.parse_args()
    if args.input.resolve()==args.output.resolve() or args.input.resolve() in args.output.resolve().parents:
        parser.error('output must not overwrite input')
    print(json.dumps(build(args.input,args.output),ensure_ascii=False,indent=2))

if __name__=='__main__': main()
