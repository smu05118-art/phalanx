#!/usr/bin/env python3
"""Offline KSHIP reference engine. Standard library; never imports the KCE engine.

Round 3 extends the supplied R2 adapter, runoff, cohort, audit and rendering contract.
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
VERSION = "kship-r3-1"
ORIGIN = "2026Q2"
AS_OF = "2026-09-18"
SCENARIOS = {"conservative": (0.25, 0.95), "base": (0.50, 1.0),
             "optimistic": (0.75, 1.05)}
EXPECTED_HISTORY = [f"{y}Q{q}" for y in range(2021, 2027) for q in range(1, 5)
                    if "2021Q4" <= f"{y}Q{q}" <= ORIGIN]
MIN_BURN_SAMPLES = 2
MIN_ORDER_SAMPLES = 4
BACKTEST_HORIZON = 8
REASONS = {
    "missing_reports_file": "입력에 kship_reports.json 없음; 문서의 수집 완료는 원장이 아님",
    "unsupported_reports_schema": "원본 원장 구조 미검증; 명시적 중간 스키마 어댑터 필요",
    "company_reports_absent": "해당 회사 정기보고서 원장 없음",
    "origin_snapshot_absent": "기준분기 적격 원장 없음",
    "holding_overlap": "지주 발행인 계약과 자회사 운영 범위·계열 중복 미분리",
    "unknown_unit_or_currency": "표 단위·통화·unit_seen 근거 불충분",
    "insufficient_burn_history": "동일 범위 인접분기 소진율 표본 2개 미만",
    "insufficient_order_history": "동일 부문 유효 신규 순유입 대용치 표본 4개 미만 (환효과 미분리)",
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
    "insufficient_segment_history": "동일 부문 유효 소진율 2개 또는 순유입 4개 기준 미달",
    "scope_mismatch": "입력 수주표가 해당 시기 조선부문 범위와 불일치; 다른 범위로 보존",
    "segment_scope_changed": "부문 명칭·범위 변경; 근거 없이 과거 부문과 연결하지 않음",
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
            # R3 embeds the normalization contract in the ledger. A raw caption
            # alone is insufficient; the stored numbers must be declared normalized.
            embedded = raw.get("unit_contract") == "값은 kce_parse._UNIT_SCALE 로 표마다 백만원 정규화 후 저장. raw_unit_caption 은 원문 캡션."
            external = (bool(evidence.get("unit_contract")) and caption in
                        evidence.get("companies", {}).get(stock, {}).get(quarter, []))
            unit_ok = (source.get("unit_seen") is True and source.get("cur") == "KRW"
                       and caption in {"억원", "백만원", "척, 백만원"} and (embedded or external))
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
            hj_marine = {"방산", "신조선", "기타(수리선)", "특수선", "상선", "수리"}
            if stock == "097230" and not set(ids).issubset(hj_marine):
                issues.append("scope_mismatch")
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
                              "unit_basis": "embedded_normalization_contract" if embedded else "external_unit_evidence",
                              "unit_independently_verified": False,
                              "normalization_applied_here": 1, "reconciliations": comparisons,
                              "revenue_audit": ra, "fx": source.get("fx"), "hedge": source.get("hedge"),
                              "scope": ("unverified_non_marine_table" if "scope_mismatch" in issues else "marine_segment") if stock == "097230" else "reported_segment_sum_uneliminated"})
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
        failures = []
        if not number(row["backlog"]) or row["backlog"] < 0: failures.append("invalid_snapshot")
        if len(burns) < MIN_BURN_SAMPLES: failures.append("insufficient_burn_history")
        if len(orders) < MIN_ORDER_SAMPLES: failures.append("insufficient_order_history")
        eligible = not failures
        fits.append({"segment_id": seg, "backlog": row["backlog"], "eligible": eligible,
                     "burn_samples": burns, "net_inflow_samples": orders, "excluded_samples": excluded,
                     "schedule": sched, "duration_basis": "median_observed_contract_period" if sched else "inverse_median_burn_proxy",
                     "recognition_basis": row["recognition_basis"], "source_rollforward_residual": row["rollforward_residual"],
                     "sample_counts": {"burn": len(burns), "net_inflow": len(orders)},
                     "minimum_samples": {"burn": MIN_BURN_SAMPLES, "net_inflow": MIN_ORDER_SAMPLES},
                     "clean_new_order_samples": None,
                     "reason_codes": failures})
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
    reasons.extend(code for s in snapshots if s["quarter"] == origin for code in s["issues"])
    if company["role"] == "holding":
        reasons.append("holding_overlap")
        current = None
    fits = fit_native(company["stock"], valid, current, schedule) if current else []
    eligible = [f for f in fits if f["eligible"]]
    if fits:
        reasons.extend(["book_value_only", "scope_unverified"])
        if len(eligible) != len(fits): reasons.append("insufficient_segment_history")
        reasons.extend(code for f in fits for code in f["reason_codes"] if code not in reasons)
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
           "scale_applied": 1, "basis": "supplied_normalization_contract; already_normalized_millions",
           "independently_verified_from_original": False},
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
            complete_year = len(historical)+len(indices)==4
            bounds = interval(obs+min(sensitivity), obs+max(sensitivity)) if sensitivity and number(obs) and full and complete_year else interval()
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
            "minimum_history_samples": {"burn": MIN_BURN_SAMPLES, "net_inflow": MIN_ORDER_SAMPLES}, "new_order_arrival": "quarter_end; first_recognition_next_quarter",
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
                if not 1 <= h <= BACKTEST_HORIZON: continue
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
                        "actual": complete_sum(scored[q]["actual"] for q in qs),
                        "quarters": qs, "horizons": [scored[q]["horizon"] for q in qs],
                        "information_cutoff": s["available_on"],
                        "target_basis": "four_observed_same_scope_quarters; all_forecast_at_origin"})
    return {"quarterly": metric(records), "annual": metric(annual_records),
            "by_horizon": {str(h):metric([r for r in records if r["horizon"]==h]) for h in range(1,BACKTEST_HORIZON+1)},
            "by_company": {c["stock"]: {"quarterly": metric([r for r in records if r["company_id"]==c["stock"]]),
                            "annual": metric([r for r in annual_records if r["company_id"]==c["stock"]])} for c in universe},
            "annual_by_year": {str(y):metric([r for r in annual_records if r["fiscal_year"]==y])
                               for y in sorted({r["fiscal_year"] for r in annual_records})},
            "annual_by_terminal_horizon": {str(h):metric([r for r in annual_records if max(r["horizons"])==h])
                                           for h in range(4,BACKTEST_HORIZON+1)},
            "records": records, "annual_records": annual_records, "exclusions": dict(exclusions),
            "calibrated": False, "filled_cells_scored": 0,
            "method": "rolling_origin_retrospective_reported_scope_proxy; base_same_engine",
            "vintage_policy": "quarter_and_report_date_gated; latest_contract_snapshot_survivorship_and_revision_bias_unresolved",
            "strict_real_time": False, "independent_holdout": False,
            "schema_policy_basis": "developed_after_auditing_full_supplied_input; not_independent_holdout",
            "origin_range": {"first": min((r["origin"] for r in records),default=None),
                             "last": max((r["origin"] for r in records),default=None)},
            "unique_origins": len({(r["company_id"],r["origin"]) for r in records}),
            "unique_targets": len({(r["company_id"],r["quarter"]) for r in records}),
            "sample_warning": "최대19분기·회사별 길이 상이. 중첩 예측이며 독립 표본 아님; 공시일이 목표분기 중간일 수 있는 사후 재생. 구간 미보정."}


def summarize_projection(f):
    return {"status": f["status"], "coverage": f["coverage"],
            "base_annual": f["scenarios"]["base"]["annual"],
            "segments": [{"segment_id": x["segment_id"], "eligible": x["eligible"],
                          "burn_n": len(x["burn_samples"]), "net_inflow_n": len(x["net_inflow_samples"]),
                          "median_burn": quantile([r["value"] for r in x["burn_samples"]], .5),
                          "median_net_inflow": quantile([r["value"] for r in x["net_inflow_samples"]], .5)}
                         for x in f["evidence"]["segments"]]}


def read_round2_report(path):
    """Read the actual supplied report; never manufacture the missing R2 audit/panel."""
    text = path.read_text()
    horizons = {}
    annual = collections.defaultdict(list)
    for line in text.splitlines():
        cells = line.strip("|").split("|")
        if re.fullmatch(r"T\+\d+", cells[0]):
            horizons[cells[0][2:]] = {"n": int(cells[1]), "wape_pct": None if cells[2]=="None" else float(cells[2])}
        if len(cells)==7 and re.fullmatch(r"FY\d{4}", cells[1]):
            annual[cells[0]].append({"fiscal_year": int(cells[1][2:]),
                **{key: None if val=="None" else float(val) for key,val in zip(
                    ("value","observed_revenue","existing_backlog_revenue","new_order_revenue","covered_future_value"),cells[2:])}})
    pattern = r"분기 채점 \*\*(\d+)개\*\*, 연간 \*\*(\d+)개\*\*. 분기 MAE ([\d.]+)백만원, WAPE ([\d.]+)%, bias (-?[\d.]+)%"
    match = re.search(pattern,text)
    if not match: raise ValueError("supplied R2 report metrics not found")
    n,an,mae,wape,bias = match.groups()
    return {"source": path.name, "quarterly": {"n":int(n),"mae":float(mae),"wape_pct":float(wape),"bias_pct":float(bias)},
            "annual": {"n":int(an)}, "by_horizon":horizons,"base_annual_by_name":dict(annual)}


def comparison(input_dir, universe, reports, contracts, companies, bt):
    # Execute the reviewed supplied module under a non-main name, without modifying it.
    import runpy
    from types import SimpleNamespace
    prior = SimpleNamespace(**runpy.run_path(str(input_dir/'kship_forecast.py'),run_name='kship_round2_reference'))
    short = {stock:[s for s in ss if s['quarter'] >= '2024Q3'] for stock,ss in reports.items()}
    old_bt = prior.backtest_native(universe,short,contracts)
    short_bt = backtest_native(universe,short,contracts)
    reported = read_round2_report(input_dir/'kship_REPORT.md')
    changes = []
    for company,current in zip(universe,companies):
        stock=company['stock']; snaps=short.get(stock,[])
        rows=[r for r in contracts if r['stock']==stock]
        old=prior.project_native(company,snaps,rows)
        same=project_native(company,snaps,rows)
        before, short4, now = map(summarize_projection,(old,same,current))
        segold={f['segment_id']:f for f in short4['segments']}
        segments=[]
        for f in now['segments']:
            p=segold.get(f['segment_id'])
            segments.append({"segment_id":f['segment_id'],"short_ledger_same_rule":p,"extended_ledger":f,
                             "newly_eligible":bool(f['eligible'] and p and not p['eligible'])})
        value_changes=[]
        previous={a['fiscal_year']:a for a in before['base_annual']}
        for a in now['base_annual']:
            b=previous[a['fiscal_year']]
            comparable=before['coverage']['modeled_segments']==now['coverage']['modeled_segments']
            delta=(a['covered_future_value']-b['covered_future_value']) if all(number(x) for x in (a['covered_future_value'],b['covered_future_value'])) else None
            pct=100*delta/abs(b['covered_future_value']) if number(delta) and b['covered_future_value'] else None
            value_changes.append({"fiscal_year":a['fiscal_year'],"round2_covered_future_value":b['covered_future_value'],
                 "round3_covered_future_value":a['covered_future_value'],"same_modeled_scope":comparable,
                 "difference":rounded(delta),"difference_pct":rounded(pct),
                 "large_change_ge_10pct":bool(number(pct) and abs(pct)>=10),
                 "interpretation":"same_scope_value_change" if comparable else "scope_changed_do_not_interpret_as_like_for_like"})
        changes.append({"company_id":stock,"company_name":company['name'],"round2_replay":before,
                        "short_ledger_four_sample_rule":short4,"round3":now,"segments":segments,
                        "annual_changes":value_changes,
                        "newly_estimable_under_same_four_sample_rule":same['status']=='unavailable' and current['status']!='unavailable'})
    key=lambda r:(r['company_id'],r['origin'],r['quarter'])
    old_records={key(r):r for r in old_bt['records']};new_records={key(r):r for r in bt['records']}
    paired=sorted(old_records.keys() & new_records.keys())
    metrics_match=all(reported['quarterly'][k]==old_bt['quarterly'][k] for k in ('n','mae','wape_pct','bias_pct'))
    annual_checks=[]
    for change in changes:
        supplied=reported['base_annual_by_name'].get(change['company_name'],[])
        for a in supplied:
            replay=next(x for x in change['round2_replay']['base_annual'] if x['fiscal_year']==a['fiscal_year'])
            annual_checks.append(all(replay[k]==v for k,v in a.items()))
    return {"reported_round2":reported,"round2_code_minimum_order_samples":2,"round3_minimum_order_samples":MIN_ORDER_SAMPLES,
            "round2_replay_matches_reported_metrics":metrics_match,
            "round2_replay_matches_reported_annual_values":bool(annual_checks) and all(annual_checks),
            "round2_ledger_reconstruction":"2024Q3..2026Q2 slice of supplied R3 ledger; separate R2 raw ledger absent",
            "round2_snapshot_count":sum(map(len,short.values())),"round3_snapshot_count":sum(map(len,reports.values())),
            "round2_replay_backtest":old_bt,"short_ledger_four_sample_backtest":short_bt,
            "paired_records":{"n":len(paired),"round2":metric([old_records[k] for k in paired]),"round3":metric([new_records[k] for k in paired])},
            "companies":changes}


def reassess(company,change):
    current=company['evidence']['segments'];old={x['segment_id']:x for x in change['short_ledger_four_sample_rule']['segments']}
    resolved=[];pending=[]
    for f in current:
        p=old.get(f['segment_id'],{})
        if f['eligible'] and p.get('eligible') is False: resolved.append(f['segment_id'])
        if f['eligible']: continue
        causes=list(f['reason_codes'])
        if company['stock']=='042660' and f['segment_id']=='EP및특수선':
            causes.append('segment_scope_changed')
            detail='2026Q1에 새 부문명이 시작. 이전 해양및특수선/플랜트/E&I와 범위 일치 근거가 없어 연결하지 않음.'
        elif company['stock']=='097230' and f['segment_id']=='수리':
            detail='현행 수리는 2025Q1부터. 유효 순유입 2개; Q1 누적 기납품과 누락 2024Q4·2025Q4를 채우지 않음. 2022 기타(수리선)과 연결 근거 없음.'
        else: detail='동일 부문·인접 분기·유효 흐름으로 표본을 제한한 뒤 최소 표본 미달.'
        pending.append({"segment_id":f['segment_id'],"sample_counts":f['sample_counts'],"reason_codes":causes,
                        "detail":detail,"next_evidence":"동일 범위 추가 분기 또는 원문에 근거한 과거 범위 대조"})
    return {"source":"missing needs_longer_ledger/audit file; reassessed all supplied companies against explicit four-sample rule",
            "resolved_segments":resolved,"pending_segments":pending,
            "needs_longer_ledger":bool(pending),
            "newly_estimable_under_four_sample_rule":change['newly_estimable_under_same_four_sample_rule'],
            "disposition":"ledger_absent" if not current else "partially_resolved" if resolved and pending else "still_blocked" if pending else "sample_gate_satisfied",
            "clean_gross_USD_orders_verified":False}


def report_text(panel):
    pop,bt,cmp=panel['population'],panel['backtest'],panel['round2_comparison']
    old=cmp['reported_round2']; short=cmp['short_ledger_four_sample_backtest']
    def fmt(x): return f"{x:,.3f}" if number(x) else '—'
    lines=['# ARGUS-kship 3차 — 확장 원장 재판정', '',
      f"기준 {ORIGIN}, 입력 사용 가능일 {AS_OF}. 41사 전수, 원장 5사·79개 회사분기(2차 35개 대비 +44). 계산 가능한 범위 {pop['estimated_companies']}사, 미추정 {pop['unestimated_companies']}사.",
      '**핵심 판정:** 같은 신규 순유입 4개 기준을 양쪽에 적용하면 HJ 특수선·상선이 각각 3→5개로 적격 전환된다. HJ 수리(2개), 한화 EP및특수선(1개)은 여전히 미달이다. 삼성·한화 상선/기타·HD·대한은 짧은 원장에서도 이미 4개를 충족했다. 19분기라는 달력 길이를 모든 부문의 18개 적격 표본으로 간주할 수 없다.',
      '제공된 2차 실행 코드는 순유입 최소 **2개**를 사용해 이미 5사를 partial로 계산했다. 이번 요청의 **4개**와 다르다. 따라서 2차 발표 대비 새로 계산 가능한 회사 수는 0; 같은 4개 규칙의 짧은 원장 대비로는 HJ 1사가 부분 계산 가능해졌다. 기준 완화로 해제한 결과가 아니다.',
      '금액은 **백만원(KRW_million)**. 신규분은 환산·취소가 섞인 장부 순유입 대용치이다. 깨끗한 USD 신규수주 4건 확보를 뜻하지 않는다. 회사 회계매출 인증·회사간 합산을 하지 않으며 전사 상태는 partial 또는 unavailable로 유지한다.', '',
      '## 입력 및 재사용', '',
      '- 2차 코드의 원장 어댑터·분기 차분·잔고 소진·smoothstep 신규 코호트·선표·환/헤지 처리·민감도·HTML 표/SVG와 기존 테스트를 이어 사용했다. 변경은 내장 단위계약 인식, 4개 표본 기준, 19분기 감사, 범위 예외, 지평 8개/연간 검증 및 비교 출력이다.',
      '- 실제 입력은 7개 파일이다. 언급된 kship_audit.json, needs_longer_ledger, kship_unit_evidence.json, 이전 forecast_panel.json은 없다. 누락 산출물을 복원한 척하지 않고 제공 보고서 수치와 2차 코드를 직접 비교했다.',
      '- 원장 최상위 unit_contract는 kce_parse._UNIT_SCALE로 표마다 백만원 정규화했다고 명시한다. unit_seen=true·KRW·알려진 단위 캡션을 함께 확인하고 배율 1을 적용한다. 원문/파서가 없어 독립 검증은 못 했다. 단위 근거 없는 셀은 계산하지 않는다.',
      f"- 2024Q3 이후 35개를 잘라 2차 코드로 재생했다. 보고서와 분기 지표 일치: {cmp['round2_replay_matches_reported_metrics']}, 기준 연간 값 일치: {cmp['round2_replay_matches_reported_annual_values']}. 별도 2차 원장이 없어 과거 파일 동일성 자체는 확인할 수 없다.", '',
      '## 표본 부족 재판정', '',
      '|회사|원장 분기 수|현재 부문|순유입 2차 창→확장|소진율 2차 창→확장|4개 규칙 판정|',
      '|---|---:|---|---:|---:|---|']
    for change in cmp['companies']:
        c=next(c for c in panel['companies'] if c['stock']==change['company_id'])
        for r in change['segments']:
            a,b=r['short_ledger_same_rule'],r['extended_ledger']
            state='신규 적격' if r['newly_eligible'] else '적격 유지' if b['eligible'] else '보류'
            lines.append(f"|{c['company_name']}|{c['audit']['quarter_count']}|{r['segment_id']}|{a['net_inflow_n']}→{b['net_inflow_n']}|{a['burn_n']}→{b['burn_n']}|{state}|")
    lines += ['', '- 삼성·한화·HD 각 19분기, HJ 17분기, 대한 5분기다. 대한은 확장되지 않았지만 유효 순유입 4개로 경계값을 충족한다.',
      '- 한화 EP및특수선은 2026Q1부터 새 범위로 등장한다. 이전 해양및특수선·플랜트·E&I를 임의 병합하지 않았다. 추가 과거 분기를 받아도 현행 부문의 순유입 1개·소진율 1개는 늘지 않았다.',
      '- HJ 현행 특수선·상선은 2024Q1 이후 같은 이름의 이력만 사용한다. 2022~2023 방산·신조선과 연결하지 않는다. 수리는 유효 순유입이 2025Q3·2026Q2의 2개다. 2025Q1 기납품이 null이므로 2025Q2 차분도 만들 수 없다. 과거 기타(수리선) 연결은 근거 미상이다.',
      '- HJ 2021Q4 수주표는 조선부문이 아닌 건설 프로젝트 목록이다. 원문 값을 보존하되 scope_mismatch로 학습·채점에서 제외했다. HJ 2024Q4·2025Q4는 없으며 Q1 프로젝트 누계를 분기매출로 채우지 않았다.',
      '- 원장 없는 나머지 36사는 계속 unavailable이다. HD한국조선해양은 holding_overlap도 유지한다. 회사별 재판정은 JSON ledger_reassessment 및 최상위 needs_longer_ledger에 기록했다.', '',
      '## 2차 대비 회사별 값 변화', '',
      '기준 시나리오의 계산 가능 미래분 합을 비교한다. ±10% 이상을 큰 변화로 표시한다. HJ는 수리가 제외되어 비교 범위 자체가 바뀌었으므로 단순 성장률로 해석할 수 없다.', '',
      '|회사|FY|2차 미래분|3차 미래분|차이 %|같은 범위|10% 이상|', '|---|---|---:|---:|---:|---|---|']
    for c in cmp['companies']:
        if not c['segments']: continue
        for a in c['annual_changes']:
            lines.append(f"|{c['company_name']}|{a['fiscal_year']}|{fmt(a['round2_covered_future_value'])}|{fmt(a['round3_covered_future_value'])}|{fmt(a['difference_pct'])}|{a['same_modeled_scope']}|{a['large_change_ge_10pct']}|")
    lines += ['',
      '- 삼성: 과거 조선해양의 낮은 소진율·순유입이 추가되면서 FY2027 −10.2%, FY2028 −15.2%. 토건의 순유입 중앙값은 오르지만 규모가 큰 조선해양 하락을 상쇄하지 못한다.',
      '- 한화: 상선 소진율·순유입 중앙값 하락으로 FY2026 미래분 −12.7%, FY2027 −7.6%. EP및특수선의 보류 범위는 그대로다.',
      '- HJ: 같은 4개 기준에서 특수선·상선이 새로 적격이다. 2차 발표 대비로는 수리가 제외되고, 상선 순유입 중앙값이 267,700→10,700으로 낮아져 FY2028 계산 범위 합이 −70.8% 변한다. 범위 축소와 가정 변경이 섞인 수치이다.',
      '- HD: 조선·기타의 과거 낮은 순유입과 조선 소진율이 반영되어 FY2028 −15.4%. 모든 현행 부문은 계속 적격이다.',
      '- 대한: 원장 5분기와 적격 표본 4개가 그대로라 3개 연도 값이 모두 같다. 최소 표본을 충족하지만 독립적인 정확도 근거는 아직 없다.', '',
      '긴 원장의 효과는 경험적 소진율·순유입 분위수가 과거 구간까지 포함하도록 바뀌는 것이다. 기준잔고·현재 선표는 동일하다. 아래 중앙값으로 변화 방향을 확인할 수 있다. 외삽 성장률이나 환율 배수는 추가하지 않았다.', '',
      '|회사·부문|소진율 중앙값 2차→3차|분기 순유입 중앙값 2차→3차 (백만원)|', '|---|---:|---:|']
    for c in cmp['companies']:
        pri={r['segment_id']:r for r in c['round2_replay']['segments']}
        for r in c['round3']['segments']:
            p=pri[r['segment_id']]
            lines.append(f"|{c['company_name']}·{r['segment_id']}|{fmt(p['median_burn'])}→{fmt(r['median_burn'])}|{fmt(p['median_net_inflow'])}→{fmt(r['median_net_inflow'])}|")
    lines += ['', '## 백테스트: 표본과 오차', '',
      f"분기 T+1~T+8 **{bt['quarterly']['n']}개**, 완전한 미래 4분기의 연간 **{bt['annual']['n']}개**. 기준분기 {bt['origin_range']['first']}~{bt['origin_range']['last']}; 고유 회사·기준분기 {bt['unique_origins']}개, 고유 회사·목표분기 {bt['unique_targets']}개. 같은 목표를 여러 기준분기에서 예측하므로 독립 표본 수가 아니다.",
      f"분기 MAE {fmt(bt['quarterly']['mae'])}, WAPE **{fmt(bt['quarterly']['wape_pct'])}%**, bias {fmt(bt['quarterly']['bias_pct'])}%. 연간 MAE {fmt(bt['annual']['mae'])}, WAPE **{fmt(bt['annual']['wape_pct'])}%**, bias {fmt(bt['annual']['bias_pct'])}%.",
      '2차는 2개 문턱, 3차는 4개 문턱이다. 가운데 열은 같은 4개 문턱으로 짧은 원장을 재계산한 통제 비교이다. 표본 증가와 문턱 변경을 섞어 정확도 개선으로 주장하지 않는다.', '',
      '|지평|2차 발표 n|짧은 원장·4개 기준 n|3차 n|발표 대비 증가|같은 기준 대비 증가|2차 WAPE %|3차 WAPE %|3차 MAE|3차 bias %|',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for h,m in bt['by_horizon'].items():
        p=old['by_horizon'][h];sh=short['by_horizon'][h]
        lines.append(f"|T+{h}|{p['n']}|{sh['n']}|{m['n']}|{m['n']-p['n']}|{m['n']-sh['n']}|{fmt(p['wape_pct'])}|{fmt(m['wape_pct'])}|{fmt(m['mae'])}|{fmt(m['bias_pct'])}|")
    for label,key in [('분기 합계','quarterly'),('연간','annual')]:
        p=old[key];m=bt[key];sh=short[key]
        lines.append(f"|{label}|{p['n']}|{sh['n']}|{m['n']}|{m['n']-p['n']}|{m['n']-sh['n']}|{fmt(p.get('wape_pct'))}|{fmt(m['wape_pct'])}|{fmt(m['mae'])}|{fmt(m['bias_pct'])}|")
    paired=cmp['paired_records']
    lines += ['', f"동일 회사·기준분기·목표분기로 겹치는 {paired['n']}건만 비교하면 WAPE는 2차 {fmt(paired['round2']['wape_pct'])}% → 3차 {fmt(paired['round3']['wape_pct'])}%이다. 전체 성적과 같은 표본 비교를 모두 남겼다.", '',
      '|회사|2차 분기 n|3차 분기 n|분기 MAE|분기 WAPE %|분기 bias %|연간 n|연간 MAE|연간 WAPE %|연간 bias %|',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in panel['companies']:
        if not c['audit']['quarter_count']: continue
        m=c['backtest'];qr=m['metrics'];a=m['annual_metrics']
        pn=sum(r['company_id']==c['stock'] for r in cmp['round2_replay_backtest']['records'])
        lines.append(f"|{c['company_name']}|{pn}|{qr['n']}|{fmt(qr['mae'])}|{fmt(qr['wape_pct'])}|{fmt(qr['bias_pct'])}|{a['n']}|{fmt(a['mae'])}|{fmt(a['wape_pct'])}|{fmt(a['bias_pct'])}|")
    lines += ['', '|연간 목표|n|MAE|WAPE %|bias %|', '|---|---:|---:|---:|---:|']
    for y,m in bt['annual_by_year'].items():
        lines.append(f"|FY{y}|{m['n']}|{fmt(m['mae'])}|{fmt(m['wape_pct'])}|{fmt(m['bias_pct'])}|")
    lines += ['', 'MAE = 평균 절대오차(백만원), WAPE = Σ|예측−관측|/Σ|관측|×100, bias = Σ(예측−관측)/Σ|관측|×100. 음수 조정 관측은 보존한다. 회사별 금액규모가 달라 전체 WAPE는 큰 회사의 영향을 많이 받는다.',
      '각 기준분기 보고서 공시일까지 알려진 origin 이하 원장만 학습하고, 계약은 더 보수적으로 기준분기말까지 공시·서명된 것만 쓴다. 현재 정정본만 있는 이력의 수정·생존편향은 해소하지 못했다. 공시가 다음 분기 중간에 이뤄지므로 엄격한 분기말 실시간 성적이 아니다. 전부 같은 장부 대용치로 채점하며 독립 holdout 검증이 아니다.',
      '연간은 원점 이후 Q1~Q4 네 분기 모두 같은 부문 범위·실제 관측을 갖고 T+8 안에 들어오는 경우만 합산했다. 현재 연도 관측분을 끼워 오차를 낮추지 않았다. 삼성은 모든 부문의 최초 적격 원점이 2024Q1이며 그 뒤 완결 가능한 FY2025에 2025Q2 소계 오류와 Q3 차분 불가가 있어 연간 채점이 없다. HJ는 Q1 프로젝트 누계로 분기 인식을 알 수 없어 연간 채점이 없고, 대한은 최소 표본 충족 시점이 최신 분기라 이후 실제값이 없어 채점이 없다.',
      f"제외 건수(단위가 회사/기준분기/목표분기로 서로 다름): {json.dumps(bt['exclusions'],ensure_ascii=False)}. 모든 예측·실제·공시 컷오프·학습 분기·선표 접수번호는 JSON records/annual_records에 보존한다.", '',
      '## 추정 구조와 민감도', '',
      '- 신규 유입은 균형이 맞는 표의 YTD 차분 또는 Δ잔고+인식액. 소진율은 양수이고 1 이하인 인식/직전 잔고 표본만 사용한다. 삼성은 부문 매출 YTD, HJ는 동일 연도 프로젝트 누계 차분, HD·한화·대한은 기납품 YTD 대용치이다.',
      '- 보수/기준/낙관은 순유입 Q25/Q50/Q75의 양수 부분. 음수 관측을 삭제하지 않고 투입 코호트에만 max(0,Qp)를 적용한다. 분기말 유입으로 T+1 신규분 0은 모델 구조다.',
      '- 기존잔고는 관측 기하 소진과 계약 척수 가중 smoothstep 선표를 50:50으로 혼합한다. 선표가 없으면 소진율만 쓴다. 신규 기간은 선표 계약기간 중앙값 또는 소진율 역수. **진행기준이므로 인도 분기 ≠ 매출 분기**이며 계약 마지막 인도일을 전체 매출일로 쓰지 않는다.',
      '- 소진 Q10/Q50/Q90 × 순유입 Q10/Q25/Q50/Q75/Q90 × 선표가중 0/0.5/1 × 기간 0.8/1/1.2 = 135개 경로. 분기는 경로별 min/max, 연간은 각 경로를 먼저 연간 합산한 뒤 min/max. 통계적 신뢰구간이 아니며 모든 구간 calibrated=false이다.',
      '- 과거 관측·부문이 부족하면 전범위 value와 interval은 null. 계산 가능한 부문의 잔고분·신규분·covered_scope_interval 및 covered_future_interval은 별도 제공한다. FY2026=Q1/Q2 관측+Q3/Q4 추정, FY2027/2028=네 추정분기 합이다.',
      '- 환율·헤지 배수는 미상으로 남긴다. 보고된 KRW 장부액을 재환산하지 않으며 USD 명목액/KRW 잔고로 헤지비율을 만들지 않는다. 계약 금액은 예측에 사용하지 않고 지주 계약을 자회사에 복제하지 않는다.', '',
      '## 기준 시나리오 연간 분해', '',
      '|회사|FY|전범위 값|관측 대용치|계산 가능 미래 잔고분|계산 가능 미래 신규분|계산 가능 미래합|미래합 민감도 하한~상한|',
      '|---|---|---:|---:|---:|---:|---:|---|']
    for c in panel['companies']:
        if c['status']=='unavailable': continue
        for a in c['scenarios']['base']['annual']:
            ci=a['covered_future_interval']
            lines.append(f"|{c['company_name']}|{a['fiscal_year']}|{fmt(a['value'])}|{fmt(a['observed_revenue'])}|{fmt(a['covered_future_existing'])}|{fmt(a['covered_future_new'])}|{fmt(a['covered_future_value'])}|{fmt(ci['lower'])} ~ {fmt(ci['upper'])}|")
    lines += ['', '세 시나리오의 2026Q3~2028Q4 10분기와 FY2026~FY2028 전체 결과는 forecast_panel.json에 있다(41사×3×10=1,230 분기행, 41사×3×3=369 연간행). null은 0이 아니다.', '',
      '## 원장 감사와 전수 범위', '',
      '|회사|분기|상태|계산 부문|제외 부문 / 미추정 사유|', '|---|---:|---|---|---|']
    for c in panel['companies']:
        cov=c['coverage']
        lines.append(f"|{c['company_name']} ({c['stock']})|{c['audit']['quarter_count']}|{c['status']}|{', '.join(cov['modeled_segments']) or '—'}|{', '.join(cov['excluded_segments']) or (', '.join(c['reason_codes']) if c['status']=='unavailable' else '—')}|")
    lines += ['', '원문 합계와 부문합 차이·흐름 잔차는 보존하며 임의 정정하지 않는다. 2백만원 이내는 기존 반올림 허용치다. 잔차 초과 흐름은 표본에서 제외한다. 다음은 계산에 영향을 주는 발견 사항이다.', '']
    for c in panel['companies']:
        for s in c['audit']['snapshots']:
            if s['issues']: lines.append(f"- {c['company_name']} {s['quarter']}: {', '.join(s['issues'])}.")
            for r in s['reconciliations']:
                if number(r['difference']) and abs(r['difference'])>2:
                    lines.append(f"- {c['company_name']} {s['quarter']} {r['field']}: 원문합계 {r['reported_total']}, 부문합 {r['leaf_sum']}, 차이 {r['difference']}.")
            for r in s['rows']:
                for field in ('rollforward_residual','gross_residual'):
                    if number(r[field]) and abs(r[field])>2:
                        lines.append(f"- {c['company_name']} {s['quarter']} {r['segment_id']} {field}={r[field]}: 흐름 표본 제외.")
            for issue in s['revenue_audit']['issues']:
                lines.append(f"- {c['company_name']} {s['quarter']} 매출 감사: {json.dumps(issue,ensure_ascii=False)}.")
    lines += ['', '## 재현·검증·남은 일', '', '```sh',
      'python3 -B output/kship_forecast.py --input input --output output',
      'python3 -B -m unittest discover -s output -p test_kship_forecast.py -v',
      '# 선택: 기존 화면에 붙일 회사 섹션 생성',
      'python3 -B output/forecast_section.py --panel output/forecast_panel.json --output output/sections', '```', '',
      '입력 SHA-256 및 재사용 코드 해시는 JSON에 기록한다. 단위 실패 차단, 4개 경계값, 범위 분리, 미래정보 변조 불변성, 잔고/신규 보존, 분기·연간 합산, 백테스트 전건 재생 및 입력불변/재현성을 테스트한다.',
      '남은 일: 한화 현행 EP및특수선·HJ 수리의 추가 적격 표본/범위 근거, HJ 누락 연말과 Q1 인식, 원장 없는 36사, 원문 단위·연결제거 및 환조정 검증. 성적이 나쁜 표본을 제거하거나 창을 성적에 맞춰 선택하지 않았다. 민감도는 보정하지 않았다.',
      '작업은 output/에만 저장하며 정본 수정·배포·외부 패키지·외부 메시지·인증 작업을 하지 않았다. 시작 시 tracker preflight는 central_connection_failed로 실패했고 재시도/인계 취득 없이 로컬 output 소유권 기록을 남겼다. 원장 계산·검증은 네트워크 없이 수행한다.']
    return '\n'.join(lines)+'\n'


def build(input_dir, output_dir):
    if input_dir.resolve()==output_dir.resolve() or input_dir.resolve() in output_dir.resolve().parents:
        raise ValueError('output must not overwrite input')
    before=hashes(input_dir)
    universe=json.loads((input_dir/'kship_universe.json').read_text())['rows']
    if len({c['stock'] for c in universe}) != len(universe): raise ValueError('duplicate company')
    contracts=json.loads((input_dir/'kship_contracts.json').read_text())['rows']
    reports,issues=load_reports(input_dir/'kship_reports.json')
    bt=backtest_native(universe,reports,contracts)
    companies=[]
    for c in universe:
        stock=c['stock'];snaps=reports.get(stock,[])
        rows=[r for r in contracts if r['stock']==stock]
        f=project_native(c,snaps,rows)
        scores=bt['by_company'][stock]
        f['backtest']={'quarterly_n':scores['quarterly']['n'],'metrics':scores['quarterly'],
                       'annual_n':scores['annual']['n'],'annual_metrics':scores['annual'],'sample_warning':bt['sample_warning']}
        ca=contract_audit(rows);ca['unfiltered_reference_schedule']=ca.pop('schedule')
        ca['used_for_revenue_forecast']=f['industry_axes']['schedule_used_for_runoff']
        ca['use_semantics']='dates_and_unit_counts_only_for_book_runoff_timing; contract_amounts_unused'
        ca['used_schedule_rcps']=sorted({r['rcp'] for fit in f['evidence']['segments'] if fit['eligible'] for r in fit['schedule']})
        f['audit']={'quarter_count':len(snaps),'usable_quarter_count':len(usable(snaps,ORIGIN)),
                    'missing_quarters':[q for q in EXPECTED_HISTORY if not any(s['quarter']==q for s in snaps)],
                    'snapshots':snaps,'prior_audit_available':False,'contract_audit':ca}
        companies.append(f)
    cmp=comparison(input_dir,universe,reports,contracts,companies,bt)
    for c,ch in zip(companies,cmp['companies']):
        c['ledger_reassessment']=reassess(c,ch)
        c['round2_comparison']=ch
    counts=collections.Counter(c['status'] for c in companies)
    pop={'input_companies':len(universe),'ledger_companies':len(reports),
         'status_counts':{s:counts[s] for s in ('full','partial','unavailable')},
         'estimated_companies':counts['full']+counts['partial'],'unestimated_companies':counts['unavailable']}
    panel={'schema_version':VERSION,'assignment':'ARGUS-kship round3','origin':ORIGIN,'as_of':AS_OF,
           'money_unit':'KRW_million','forecast_quarters':[qadd(ORIGIN,h) for h in range(1,11)],
           'input_sha256':before,'engine_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'round2_reuse':{name:before[name] for name in ('kship_forecast.py','forecast_section.py','test_kship_forecast.py','kship_REPORT.md')},
           'population':pop,'backtest':bt,'round2_comparison':cmp,'calibrated':False,'company_aggregation_permitted':False,
           'needs_longer_ledger':[{'company_id':c['stock'],'company_name':c['company_name'],**c['ledger_reassessment']}
                                  for c in companies if c['ledger_reassessment']['needs_longer_ledger']],
           'limitations':['book_value_proxy_not_future_nominal_KRW_revenue','net_inflow_not_clean_USD_orders',
                          'holding_overlap_no_group_sum','uncalibrated_overlapping_retrospective_backtest','prior_audit_and_needs_file_absent'],
           'audit':{'global_issues':issues,'ledger_company_ids':sorted(reports),'actual_snapshot_count':sum(map(len,reports.values())),
                    'calendar_quarters':EXPECTED_HISTORY,'expected_yard_snapshot_count':len(reports)*len(EXPECTED_HISTORY),
                    'missing_yard_company_quarters':sum(len(c['audit']['missing_quarters']) for c in companies if c['stock'] in reports),
                    'missing_inputs':['kship_audit.json','needs_longer_ledger','kship_unit_evidence.json','round2 forecast_panel.json']},
           'companies':companies}
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/'forecast_panel.json').write_text(json.dumps(panel,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (output_dir/'kship_REPORT.md').write_text(report_text(panel))
    if hashes(input_dir)!=before: raise RuntimeError('input mutated')
    return {'population':pop,'backtest_n':bt['quarterly']['n'],'annual_backtest_n':bt['annual']['n'],
            'input_unchanged':True,'round2_reproduced':cmp['round2_replay_matches_reported_metrics'],
            'quarterly_rows':len(universe)*30,'annual_rows':len(universe)*9}


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
