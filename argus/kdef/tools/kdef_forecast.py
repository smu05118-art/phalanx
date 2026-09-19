#!/usr/bin/env python3
"""Offline KDEF round-3 continuation and conditional forecast. Python standard library only.

Report amounts never receive an inferred unit multiplier. Contract schedules are
partial, explicitly modelled disclosure cohorts, NOT observed remaining backlog.
No imports from the construction engine and no network or current-clock inputs.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import calendar
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ORIGIN = '2026Q2'
SCENARIOS = {'conservative': .25, 'base': .5, 'optimistic': .75}
TYPES = {
    'RND': ('체계개발', 'linear', '유형별 인식 속도 미확인; 공통 선형 가정'),
    'FIRST': ('최초양산', 'linear', '유형별 인식 속도 미확인; 공통 선형 가정'),
    'FOLLOW': ('후속양산', 'linear', '반복 생산 균등 가정; 실제 호기별 인도표 미확인'),
    'UPGRADE': ('성능개량', 'linear', '유형별 인식 속도 미확인; 공통 선형 가정'),
    'PBL': ('후속군수지원', 'linear', '지원 기간 균등 가정; 가동률·성과보수 미확인'),
    'SUPPLY': ('물품공급', 'linear', '유형별 인식 속도 미확인; 공통 선형 가정'),
}
REASONS = {
    'REPORT_SCALE_NOT_EXPORTED': '보고서 환산 배수·원문 단위 캡션 미제공',
    'REPORT_CURRENCY_UNKNOWN': '보고서 통화 미확인',
    'NO_ORIGIN_REPORT': '기준분기 보고서 없음 또는 읽기 실패',
    'NO_ORDER_TABLE': '수주표 미추출',
    'NO_ELIGIBLE_CONTRACT': '기준일에 유효한 유형·금액·기간 확인 계약 없음',
    'NO_ELIGIBLE_PROGRESS_ROW': '진행률·정확한 시작/종료일을 함께 확인한 행 없음',
    'COMPANY_TOTAL_UNIDENTIFIED': '회사 전체 잔고와 계약 공시 간 대사·범위 연결 없음',
    'UNOBSERVED_CONTRACT_PROGRESS': '계약 기인식액 미제공; 일정상 잔여분은 모형값',
    'NEW_ORDER_SAMPLE_LT4': '금액 확인 원계약 발생 분기 표본 4개 미만',
    'DISCLOSURE_ORDER_PROXY': '신규분은 수주공시 발생 분기의 조건부 가정; 회사 순수주 아님',
    'SHORT_HISTORY': '해당 회사의 유효 원장·동일 범위 표본 부족; 개별 재심사 참고',
    'NO_MONETARY_BACKTEST_TARGET': '보고서 단위 배수·분기 인식액 정답 미확인: 금액 채점 0건',
    'GROUP_OVERLAP': '계열사 중복 가능; 회사 간 합계 금지',
    'CIVIL_SCOPE_EXCLUDED': 'CIVIL/민수 행은 방산 추정에서 제외',
    'UNKNOWN_DEFENSE_SCOPE': '미분류 행·공시는 방산 여부 미확정',
    'MISSING_OBSERVED_H1': 'FY2026 관측 상반기 인식액 미확인',
    'CONTRACT_TYPE_UNKNOWN': '계약 유형 미확인: 유형별 금액 인식 보류',
    'CONTRACT_AFTER_ORIGIN': '기준분기 말 이후 공시: 전망에서 제외',
    'CONTRACT_DATE_INVALID': '정확한 계약 시작·종료일 미확인 또는 역전',
    'CONTRACT_MONEY_MISSING': '계약 백만원 금액 누락·비유한·비양수',
    'CONTRACT_EXPIRED': '기준일 전에 종료된 계약',
    'CONTRACT_CANCELLED': '해지·해제·취소 공시',
    'CONTRACT_SUPERSEDED': '기준일 당시 더 최신인 정정공시로 대체',
    'CONTRACT_ID_CONFLICT': '같은 접수번호의 내용 충돌',
    'CONTRACT_SIGNED_AFTER_ORIGIN': '수주일이 기준일 이후',
    'REPORT_LEDGER_IDENTITY_MISMATCH': '수주표 총액−기납품=잔고 대사 불일치',
    'REPORT_AGGREGATE_ROWS_PRESENT': '합계·소계 행 존재: 상세행과 중복 합산 금지',
    'REPORT_DUPLICATE_ROW_IDENTITY': '보고서 행 식별자가 중복되어 개별 이력 연결 불가',
    'REPORT_END_DATES_MISSING': '보고서 잔고 행의 정확한 종료일 일부 또는 전부 미확인',
}


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def qnum(q):
    if not re.fullmatch(r'\d{4}Q[1-4]', q):
        raise ValueError('invalid quarter: ' + str(q))
    return int(q[:4]) * 4 + int(q[-1]) - 1


def qadd(q, h):
    y, n = divmod(qnum(q) + h, 4)
    return f'{y}Q{n+1}'


def qend(q):
    month = int(q[-1]) * 3
    return date(int(q[:4]), month, calendar.monthrange(int(q[:4]), month)[1])


def date_quarter(d):
    return f'{d.year}Q{(d.month-1)//3+1}'


def parse_date(x):
    # Approximate month/year dates, "이후", ranges, and footnotes stay unknown.
    if not isinstance(x, str) or not re.fullmatch(r'\d{4}[-.]\d{2}[-.]\d{2}', x):
        return None
    try:
        return date.fromisoformat(x.replace('.', '-'))
    except ValueError:
        return None


def receipt_date(x):
    if not isinstance(x, str) or not re.fullmatch(r'\d{14}', x):
        return None
    return parse_date(x[:4] + '-' + x[4:6] + '-' + x[6:8])


def quantile(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    i = (len(xs)-1) * p
    a = int(i)
    return xs[a] + (xs[min(a+1, len(xs)-1)]-xs[a]) * (i-a)


def strict_sum(xs):
    xs = list(xs)
    return sum(xs) if all(number(x) for x in xs) else None


def interval(xs, method='finite_timing_sensitivity_0.8_1.0_1.2'):
    xs = list(xs)
    good = xs and all(number(x) for x in xs)
    return {'lower': min(xs) if good else None, 'upper': max(xs) if good else None,
            'method': method, 'nominal_level': None, 'calibrated': False}


def sum_intervals(rows, key):
    vals = [r[key] for r in rows]
    return {'lower': strict_sum(x['lower'] for x in vals),
            'upper': strict_sum(x['upper'] for x in vals),
            'method': 'sum_of_period_sensitivity_bounds_not_joint_probability',
            'nominal_level': None, 'calibrated': False}


def cdf(kind, x):
    # Round 2: no ledger-verified type-specific speeds. All retained schedules
    # use the same explicitly assumed linear curve, including SUPPLY.
    if kind not in TYPES and kind != 'LEDGER_LINEAR':
        raise ValueError('unknown contract type')
    return min(1., max(0., x))


def text_type(label):
    """Only literal stage words; export is not a contract type."""
    if '성능개량' in label:
        return 'UPGRADE'
    if re.search(r'PBL|후속군수지원|성과기반', label, re.I):
        return 'PBL'
    if re.search(r'체계개발|기술 개발|기술개발', label):
        return 'RND'
    if re.search(r'최초양산|초도양산|(?<!\d)1차\s*양산', label):
        return 'FIRST'
    if re.search(r'후속양산|(?<!\d)(?:[2-9]|[1-9]\d+)차\s*양산', label):
        return 'FOLLOW'
    return 'LEDGER_LINEAR'


def aggregate_row(r):
    label = re.sub(r'\s+', '', str(r.get('label', '')))
    return r.get('kind') == 'total' or label in ('합계', '총계', '계', '합계금액') or r.get('due') == '계'


def identity(r):
    # No fuzzy join or stable IDs invented from row order.
    return (re.sub(r'\s+', '', str(r.get('label', ''))), r.get('order_date') or '')


def report_unit(s):
    verified = s.get('_normalized_million') is True
    return {'currency': s.get('cur'), 'unit_seen': s.get('unit_seen'),
            'unit_from_prev': s.get('unit_from_prev'),
            'raw_unit_caption': s.get('_captions', []),
            'scale_from_input': 1 if verified else None,
            'money_unit': 'million_original_currency' if verified else None,
            'verified': verified,
            'ratio_eligible': verified and s.get('cur') in ('KRW', 'USD'),
            'reason': None if verified else 'REPORT_SCALE_NOT_EXPORTED',
            'basis': 'round-2 report documents parser contract; raw unit-evidence JSON absent; stored amounts not rescaled',
            'independently_verified': False}


def report_progress_rows(snapshot, quarter):
    """Dimensionless, single-row D/G only; never Δdelivered as quarterly sales."""
    if not snapshot.get('ok') or not report_unit(snapshot)['ratio_eligible']:
        return []
    if snapshot.get('shape') not in ('item', 'gross'):
        return []
    counts = Counter(identity(r) for r in snapshot.get('segments', []))
    valid = []
    for idx, r in enumerate(snapshot.get('segments', [])):
        if aggregate_row(r) or r.get('kind') == 'civil' or counts[identity(r)] != 1:
            continue
        g, d, b = r.get('gross'), r.get('delivered'), r.get('closing')
        if not (number(g) and g > 0 and number(d) and 0 <= d <= g):
            continue
        if number(b) and (b < 0 or abs(g-d-b) > max(2., abs(g)*1e-6)):
            continue
        start, end = parse_date(r.get('order_date')), parse_date(r.get('due'))
        if not (start and end and start < end and start <= qend(quarter)):
            continue
        valid.append({'row_index': idx, 'identity': list(identity(r)), 'label': r['label'],
                      'kind': r.get('kind'), 'currency': snapshot.get('cur'),
                      'start': start.isoformat(), 'end': end.isoformat(), 'gross_raw': g,
                      'delivered_raw': d, 'closing_raw': b, 'progress': d/g,
                      'type': text_type(r['label']), 'receipt': snapshot.get('rcp')})
    return valid


def project_progress(row, origin, target, stretch=1.):
    p0 = row['progress']
    end = parse_date(row['end'])
    if end <= qend(origin) and p0 < 1:
        return None  # overdue is not magically completed
    if p0 == 1:
        return 1.
    if qend(target) <= qend(origin):
        return p0
    days = (end-qend(origin)).days * stretch
    return p0 + (1-p0) * cdf(row['type'], (qend(target)-qend(origin)).days/days)


def contract_cohorts(rows, origin=ORIGIN):
    """Use filing-date vintage. A later correction cannot supply its old version."""
    cutoff = qend(origin)
    reasons = {}
    keyed = defaultdict(list)
    for i, c in enumerate(rows):
        keyed[c.get('rcp')].append(i)
    conflict = {i for ids in keyed.values() if len({json.dumps(rows[j], sort_keys=True) for j in ids}) > 1 for i in ids}
    preliminary = []
    for i, c in enumerate(rows):
        reason = None
        rd = receipt_date(c.get('rcp'))
        sd = parse_date(c.get('signed'))
        if c.get('civil') is True or c.get('domain') == 'CIVIL':
            reason = 'CIVIL_SCOPE_EXCLUDED'
        elif i in conflict:
            reason = 'CONTRACT_ID_CONFLICT'
        elif not rd or rd > cutoff:
            reason = 'CONTRACT_AFTER_ORIGIN'
        elif sd and sd > cutoff:
            reason = 'CONTRACT_SIGNED_AFTER_ORIGIN'
        if reason:
            reasons[i] = reason
        else:
            preliminary.append(i)
    superseded = {rows[i].get('supersedes') for i in preliminary if rows[i].get('supersedes')}
    latest = {}
    for i in preliminary:
        c = rows[i]
        # Same issuer, literal name, and signed/start date only; no amount matching.
        key = (c['stock'], c.get('name'), c.get('signed') or c.get('start') or c['rcp'])
        if key not in latest or rows[latest[key]]['rcp'] <= c['rcp']:
            latest[key] = i
    retained = []
    for i in preliminary:
        c = rows[i]
        key = (c['stock'], c.get('name'), c.get('signed') or c.get('start') or c['rcp'])
        if c['rcp'] in superseded or latest[key] != i:
            reasons[i] = 'CONTRACT_SUPERSEDED'
            continue
        if re.search('해지|해제|취소', (c.get('title') or '') + ' ' + (c.get('name') or '')):
            reasons[i] = 'CONTRACT_CANCELLED'
            continue
        if c.get('ctype') not in TYPES:
            reasons[i] = 'CONTRACT_TYPE_UNKNOWN'
            continue
        start, end = parse_date(c.get('start')), parse_date(c.get('end'))
        if not (start and end and start < end):
            reasons[i] = 'CONTRACT_DATE_INVALID'
            continue
        if not (number(c.get('amt_krw_m')) and c['amt_krw_m'] > 0):
            reasons[i] = 'CONTRACT_MONEY_MISSING'
            continue
        retained.append(dict(c, source_index=i))
        if end <= cutoff:
            reasons[i] = 'CONTRACT_EXPIRED'
    active = [c for c in retained if parse_date(c['end']) > cutoff]
    return active, retained, reasons


def scheduled_contract(c, origin, n=10, stretch=1.):
    """A*(F(t)-F(origin)); timing shocks keep the SAME origin modelled residual."""
    start, end, cut = parse_date(c['start']), parse_date(c['end']), qend(origin)
    amount = c['amt_krw_m']
    u0 = min(1., max(0., (cut-start).days/(end-start).days))
    f0 = cdf(c['ctype'], u0)
    anchor = max(cut, start)
    remaining_days = (end-anchor).days * stretch
    if remaining_days <= 0:
        return [0.] * n
    def cumulative(d):
        frac = min(1., max(0., (d-anchor).days/remaining_days))
        return amount * (cdf(c['ctype'], u0+(1-u0)*frac)-f0)
    previous = 0.
    result = []
    for h in range(1, n+1):
        now = cumulative(qend(qadd(origin, h)))
        result.append(now-previous)
        previous = now
    return result


def order_evidence(retained, stock, origin):
    first = qadd(origin, -7)
    samples = defaultdict(list)
    for c in retained:
        sd, start = parse_date(c.get('signed')), parse_date(c.get('start'))
        if c['stock'] != stock or c.get('corrected') or c.get('supersedes') or not sd or start < sd:
            continue
        q = date_quarter(sd)
        if first <= q <= origin:
            samples[q].append(c)
    amounts = {q: sum(c['amt_krw_m'] for c in cs) for q, cs in sorted(samples.items())}
    bytype = defaultdict(list)
    for cs in samples.values():
        for c in cs:
            bytype[c['ctype']].append(c)
    total = sum(amounts.values())
    timing = []
    for kind, cs in sorted(bytype.items()):
        timing.append({'ctype': kind, 'weight': sum(c['amt_krw_m'] for c in cs)/total,
                       'duration_quarters': statistics.median((parse_date(c['end'])-parse_date(c['start'])).days/91.310625 for c in cs),
                       'lag_quarters': statistics.median((parse_date(c['start'])-parse_date(c['signed'])).days/91.310625 for c in cs),
                       'sample_contracts': len(cs), 'receipts': [c['rcp'] for c in cs]})
    eligible = len(amounts) >= 4
    return {'available': eligible, 'sample_quarters': len(amounts), 'minimum_quarters': 4,
            'window': [qadd(first, h) for h in range(8)], 'observed_award_quarters': amounts,
            'unobserved_award_quarters': [qadd(first, h) for h in range(8) if qadd(first, h) not in amounts],
            'sample_receipts': [c['rcp'] for cs in samples.values() for c in cs],
            'domain_counts': dict(Counter(c.get('domain') or 'UNKNOWN' for cs in samples.values() for c in cs)),
            'quantiles': {k: quantile(list(amounts.values()), p) if eligible else None for k, p in SCENARIOS.items()},
            'P10': quantile(list(amounts.values()), .1) if eligible else None,
            'P90': quantile(list(amounts.values()), .9) if eligible else None,
            'timing': timing, 'seasonality': None,
            'basis': 'positive observed original-contract award quarters only; absent quarters remain missing',
            'cadence_assumption': 'one award-bearing cohort at every future quarter end; conditional selection-biased sensitivity, not company net orders',
            'scope': 'known_type_nonCIVIL_original_disclosures', 'calibrated': False}


def new_order_path(order, timing, n=10, stretch=1.):
    if order is None or not timing:
        return [None]*n, [None]*n
    revenues, balances = [], []
    recognized = 0.
    for h in range(1, n+1):
        revenue = 0.
        for j in range(1, h+1):
            for t in timing:
                duration = t['duration_quarters']*stretch
                now = (h-j-t['lag_quarters'])/duration
                prev = (h-1-j-t['lag_quarters'])/duration
                revenue += order*t['weight']*(cdf(t['ctype'], now)-cdf(t['ctype'], prev))
        recognized += revenue
        revenues.append(revenue)
        balances.append(h*order-recognized)
    return revenues, balances


def ledger_paths(company, origin):
    snapshot = company.get('quarters', {}).get(origin, {})
    rows = report_progress_rows(snapshot, origin)
    result = []
    for r in rows:
        if project_progress(r, origin, qadd(origin, 1)) is None:
            continue
        qs = []
        for h in range(1, 11):
            target = qadd(origin, h)
            now = project_progress(r, origin, target)
            prev = project_progress(r, origin, qadd(origin, h-1))
            qs.append({'quarter': target, 'horizon': h, 'progress': now,
                       'recognition_fraction_of_origin_gross': now-prev,
                       'progress_interval': interval([project_progress(r, origin, target, f) for f in (.8, 1., 1.2)])})
        annual = []
        for year in (2026, 2027, 2028):
            before = max(origin, f'{year-1}Q4')
            last = f'{year}Q4'
            fraction = project_progress(r, origin, last)-project_progress(r, origin, before)
            annual.append({'fiscal_year': year, 'progress_year_end': project_progress(r, origin, last),
                           'recognition_fraction': fraction if year > int(origin[:4]) else None,
                           'future_recognition_fraction': fraction,
                           'scope': 'same_report_row_progress_fraction_not_revenue',
                           'money_value': None, 'observed_H1_available': False})
        result.append(dict(r, monetary_forecast=None, method='observed_D_over_G_then_remaining_endpoint_curve',
                           scope='reported_row_only_defense_if_kind_def_otherwise_unclassified', quarterly=qs, annual=annual))
    return result


def annualize(qs, origin, years=(2026, 2027, 2028)):
    result = []
    for year in years:
        calendar_qs = [f'{year}Q{n}' for n in range(1, 5)]
        future = [r for r in qs if r['quarter'] in calendar_qs]
        needed = sum(q <= origin for q in calendar_qs)
        existing = strict_sum(r['covered_sites_partial_revenue'] for r in future)
        new = strict_sum(r['covered_new_order_revenue'] for r in future)
        complete_future = len(future) == 4-needed
        partial_total = strict_sum([existing, new]) if not needed and complete_future else None
        result.append({'fiscal_year': year, 'value': None, 'existing_backlog_revenue': None,
                       'covered_sites_partial_revenue': existing,
                       'new_order_revenue': None, 'covered_new_order_revenue': new,
                       'covered_total_partial_revenue': partial_total,
                       'observed_revenue': None if needed else 0.,
                       'observed_revenue_basis': 'unavailable_report_scale_and_quarterly_recognition',
                       'observed_quarters_available': 0, 'observed_quarters_required': needed,
                       'future_quarters': len(future), 'complete': False,
                       'partial_future_complete': complete_future, 'quarters': calendar_qs,
                       'reason': 'MISSING_OBSERVED_H1' if needed else 'COMPANY_TOTAL_UNIDENTIFIED',
                       'component_scope': 'future_quarters_only; modelled_disclosure_schedule_not_observed_backlog',
                       'interval': interval([]), 'partial_existing_interval': interval([]),
                       'covered_sites_partial_interval': sum_intervals(future, 'covered_sites_partial_interval'),
                       'covered_new_order_interval': sum_intervals(future, 'covered_new_order_interval'),
                       'covered_total_partial_interval': sum_intervals(future, 'covered_total_partial_interval') if not needed else interval([])})
    return result


def project_company(universe_row, report, active, retained, origin=ORIGIN):
    stock = universe_row['stock']
    cs = [c for c in active if c['stock'] == stock]
    s = report.get('quarters', {}).get(origin, {})
    ratio = ledger_paths(report, origin)
    evidence = order_evidence(retained, stock, origin)
    paths = {f: [scheduled_contract(c, origin, stretch=f) for c in cs] for f in (.8, 1., 1.2)}
    existing = {f: [sum(p[h] for p in paths[f]) for h in range(10)] if cs else [None]*10 for f in paths}
    reasons = ['REPORT_SCALE_NOT_EXPORTED', 'COMPANY_TOTAL_UNIDENTIFIED', 'SHORT_HISTORY', 'NO_MONETARY_BACKTEST_TARGET']
    if not s.get('ok'):
        reasons.append('NO_ORIGIN_REPORT')
    if not s.get('shape'):
        reasons.append('NO_ORDER_TABLE')
    if not cs:
        reasons.append('NO_ELIGIBLE_CONTRACT')
    else:
        reasons.append('UNOBSERVED_CONTRACT_PROGRESS')
    if not ratio:
        reasons.append('NO_ELIGIBLE_PROGRESS_ROW')
    reasons.append('DISCLOSURE_ORDER_PROXY' if evidence['available'] else 'NEW_ORDER_SAMPLE_LT4')
    if stock in ('012450', '042660', '272210', '099320', '000880'):
        reasons.append('GROUP_OVERLAP')
    if any(c.get('domain') is None for c in cs) or any(r['kind'] != 'def' for r in ratio) or 'UNKNOWN' in evidence['domain_counts']:
        reasons.append('UNKNOWN_DEFENSE_SCOPE')
    qa = audit_quarter(s, origin)
    reasons.extend(qa['issue_codes'])
    scenarios = {}
    new_extremes = [new_order_path(order, evidence['timing'], stretch=f)[0]
                    for order in (evidence['P10'], evidence['P90']) for f in (.8, 1., 1.2)]
    for name in SCENARIOS:
        order = evidence['quantiles'][name]
        new, new_bal = new_order_path(order, evidence['timing'])
        qs = []
        for h in range(10):
            e = existing[1.][h]
            ei = interval(existing[f][h] for f in (.8, 1., 1.2))
            ni = interval([p[h] for p in new_extremes]+[new[h]])
            pi = {'lower': strict_sum([ei['lower'], ni['lower']]),
                  'upper': strict_sum([ei['upper'], ni['upper']]),
                  'method': 'component_envelopes_over_explicit_parameter_grid',
                  'nominal_level': None, 'calibrated': False}
            qs.append({'quarter': qadd(origin, h+1), 'horizon': h+1,
                       'value': None, 'existing_backlog_revenue': None,
                       'covered_sites_partial_revenue': e,
                       'new_order_revenue': None, 'covered_new_order_revenue': new[h],
                       'covered_total_partial_revenue': strict_sum([e, new[h]]),
                       'new_order_backlog': new_bal[h], 'new_orders': order,
                       'interval': interval([]), 'partial_existing_interval': interval([]),
                       'covered_sites_partial_interval': ei, 'covered_new_order_interval': ni,
                       'covered_total_partial_interval': pi,
                       'existing_backlog_method': 'contract_type_schedule_modelled_residual_partial',
                       'status': 'partial' if cs or evidence['available'] else 'unavailable',
                       'reason_codes': reasons[:]})
        scenarios[name] = {'assumptions': {
            'new_orders_per_quarter_deseasonalized': order, 'duration_quarters': None,
            'lag_quarters': None, 'timing_by_type': evidence['timing'],
            'new_orders_scope': evidence['scope'], 'cadence_assumption': evidence['cadence_assumption'],
            'existing_schedule_same_across_scenarios': True,
            'scenario_axis': 'positive_disclosure_award_quarter_P25_P50_P75',
            'seasonality': 'not_estimated', 'calibrated': False},
            'quarterly': qs, 'annual': annualize(qs, origin)}
    active_evidence = []
    for c in cs:
        start, end = parse_date(c['start']), parse_date(c['end'])
        u = (qend(origin)-start).days/(end-start).days
        active_evidence.append({k: c.get(k) for k in ('source_index', 'rcp', 'stock', 'name', 'ctype', 'domain', 'party', 'party_kind', 'region', 'start', 'end', 'signed', 'corrected', 'supersedes', 'amt_krw_m', 'def_payrule')})
        active_evidence[-1].update(currency_original=None, money_unit='KRW_million',
                                  money_basis='explicit_amt_krw_m_field_not_independent_FX_verification',
                                  observed_progress=None, assumed_progress=cdf(c['ctype'], u),
                                  modelled_remaining_amount=c['amt_krw_m']*(1-cdf(c['ctype'], u)),
                                  delivery_units=None, production_stage_observed=None,
                                  route_fms='FMS' if 'FMS' in (c.get('name', '')+' '+c.get('note', '')) else None)
    status = 'partial' if cs or ratio or evidence['available'] else 'unavailable'
    return {'company_id': stock, 'company_name': universe_row['name'], 'audited_company_name': report.get('name'),
            'stock': stock, 'listed': True, 'source': 'kdef_reports+contracts', 'origin': origin,
            'panel_present': bool(report), 'grade': universe_row['role'], 'audited_grade': 'offline_input_only',
            'audit_can': {'matrix': 'partial' if cs or ratio else 'no', 'trace': 'partial', 'backtest': 'ratio_only'},
            'audit_blockers': [REASONS[x] for x in reasons], 'status': status,
            'integration_status': 'partial_amount_estimate' if status == 'partial' else 'unavailable',
            'reason_codes': reasons, 'money_unit': 'KRW_million',
            'scope': 'partial_nonCIVIL_known_type_contract_schedule; report_progress_separate',
            'financial_statement_revenue': False, 'fiscal_year_end_month': 12,
            'fiscal_basis': 'assumed_December_close_not_verified',
            'unit_audit': {'verified_at_origin': False, 'unit_declared_by_assignment': False,
                           'report_money_unit': None, 'contract_money_unit': 'KRW_million',
                           'contract_unit_basis': 'amt_krw_m explicit field; original currency and FX not exported',
                           'quarters': {q: report_unit(v) for q, v in sorted(report.get('quarters', {}).items())}},
            'coverage': {'current_rows': len(s.get('segments', [])), 'monetary_report_rows': 0,
                         'full_existing_coverage': False, 'active_contracts': len(cs),
                         'progress_rows': len(ratio), 'backlog_coverage_fraction': None,
                         'company_totals_additive': False},
            'evidence': {'new_orders': evidence, 'contracts': active_evidence},
            'scenarios': scenarios, 'ledger_progress': ratio, 'aggregate_forecast': None,
            'actual_revenue_proxy': {q: None for q in report.get('quarters', {})},
            'provenance': {'report_availability': 'quarter_end_information_set; reports published later',
                           'contract_cutoff': qend(origin).isoformat(), 'no_future_contracts': True,
                           'report_raw_captions_supplied': False, 'no_input_filling': True},
            'industry_axes': {'contract_types': dict(Counter(c['ctype'] for c in cs)),
                              'domains': dict(Counter(c.get('domain') or 'UNKNOWN' for c in cs)),
                              'counterparties': dict(Counter(c.get('party_kind') or 'UNKNOWN' for c in cs)),
                              'regions': dict(Counter(c.get('region') or 'UNKNOWN' for c in cs)),
                              'production_stage': None, 'delivery_units': None,
                              'lead_time_or_turnover': None, 'original_currency': None,
                              'operating_profit': None, 'margin': None}}


def metrics(rows, prediction='prediction', unit='percentage_points'):
    errors = [r[prediction]-r['actual'] for r in rows]
    denominator = sum(abs(r['actual']) for r in rows)
    return {'n': len(rows), 'unit': unit,
            'MAE': statistics.mean(abs(e) for e in errors) if errors else None,
            'MedAE': statistics.median(abs(e) for e in errors) if errors else None,
            'WAPE_pct': 100*sum(abs(e) for e in errors)/denominator if denominator else None,
            'Bias_pct': 100*sum(errors)/denominator if denominator else None}


def progress_backtest(reports):
    quarterly, annual = [], []
    skipped = Counter()
    for stock, company in reports['companies'].items():
        history = company.get('quarters', {})
        parsed = {q: {tuple(r['identity']): r for r in report_progress_rows(s, q)} for q, s in history.items()}
        for origin in sorted(history):
            for key, row in parsed[origin].items():
                if row['progress'] >= 1 or project_progress(row, origin, qadd(origin, 1)) is None:
                    skipped['not_active_or_overdue'] += 1
                    continue
                for h in range(1, 11):
                    target = qadd(origin, h)
                    truth = parsed.get(target, {}).get(key)
                    if not truth:
                        skipped['missing_or_invalid_target'] += 1
                        continue
                    quarterly.append({'stock': stock, 'origin': origin, 'target': target, 'horizon': h,
                                      'identity': list(key), 'origin_row': row['row_index'], 'target_row': truth['row_index'],
                                      'prediction': 100*project_progress(row, origin, target),
                                      'actual': 100*truth['progress'], 'persistence': 100*row['progress'],
                                      'origin_D': row['delivered_raw'], 'origin_G': row['gross_raw'],
                                      'target_D': truth['delivered_raw'], 'target_G': truth['gross_raw'],
                                      'origin_receipt': row['receipt'], 'target_receipt': truth['receipt'],
                                      'gross_changed': row['gross_raw'] != truth['gross_raw'],
                                      'due_changed': row['end'] != truth['end'], 'currency': row['currency']})
                for fyh in (1, 2):
                    year = int(origin[:4])+fyh
                    need = [f'{year-1}Q4'] + [f'{year}Q{q}' for q in range(1, 5)]
                    truths = [parsed.get(q, {}).get(key) for q in need]
                    if any(t is None for t in truths) or qnum(need[-1])-qnum(origin) > 10:
                        continue
                    predicted = project_progress(row, origin, need[-1])-project_progress(row, origin, need[0])
                    annual.append({'stock': stock, 'origin': origin, 'fiscal_year': year, 'fy_horizon': fyh,
                                   'identity': list(key), 'quarters': need,
                                   'prediction': 100*predicted, 'actual': 100*(truths[-1]['progress']-truths[0]['progress']),
                                   'persistence': 0., 'actual_progresses': [100*t['progress'] for t in truths],
                                   'target_rows': [t['row_index'] for t in truths],
                                   'negative_actual': truths[-1]['progress'] < truths[0]['progress']})
    summary = {'scope': 'reported_item_D_over_G_progress_only_not_contract_schedule_revenue',
               'availability_basis': 'quarter_end_snapshots_not_live_filing_date_backtest',
               'calibrated': False, 'max_input_quarters_per_company': max(len(c['quarters']) for c in reports['companies'].values()),
               'warning': '표본은 중첩 기준분기·생존 행이며 독립적이지 않음. 계약 금액 모형 성적 아님. 금액 표본 0; 장기 표본 부족.',
               'quarterly': [], 'annual': [], 'excluded': dict(skipped),
               'monetary': {'n': 0, 'MAE': None, 'WAPE_pct': None, 'Bias_pct': None,
                            'reason': 'NO_MONETARY_BACKTEST_TARGET'},
               'contract_schedule_and_new_orders': {'n': 0, 'reason': 'no_observed_contract_recognition_or_original_vintages'},
               'negative_annual_actuals': sum(r['negative_actual'] for r in annual)}
    for h in range(1, 11):
        rows = [r for r in quarterly if r['horizon'] == h]
        summary['quarterly'].append({'horizon': h, **metrics(rows), 'persistence': metrics(rows, 'persistence'),
                                     'gross_changed_n': sum(r['gross_changed'] for r in rows),
                                     'due_changed_n': sum(r['due_changed'] for r in rows)})
    for h in (1, 2):
        rows = [r for r in annual if r['fy_horizon'] == h]
        summary['annual'].append({'fy_horizon': h, **metrics(rows), 'persistence': metrics(rows, 'persistence')})
    return summary, {'quarterly': quarterly, 'annual': annual}


def audit_quarter(s, quarter):
    rows = s.get('segments', [])
    totals = [i for i, r in enumerate(rows) if aggregate_row(r)]
    identities = Counter(identity(r) for r in rows)
    leaves = [r for r in rows if not aggregate_row(r)]
    vals = [r.get('closing') for r in leaves]
    b = s.get('backlog')
    leafsum = strict_sum(vals) if leaves else None
    all_present_sum = sum(r['closing'] for r in rows if number(r.get('closing')))
    equation = (s.get('gross')-s.get('delivered')-b if s.get('shape') in ('item', 'gross')
                and all(number(s.get(k)) for k in ('gross', 'delivered', 'backlog')) else None)
    issues = []
    if number(equation) and abs(equation) > max(2., abs(s['gross'])*1e-6):
        issues.append('REPORT_LEDGER_IDENTITY_MISMATCH')
    if totals:
        issues.append('REPORT_AGGREGATE_ROWS_PRESENT')
    if any(n > 1 for n in identities.values()):
        issues.append('REPORT_DUPLICATE_ROW_IDENTITY')
    if any(parse_date(r.get('due')) is None for r in leaves):
        issues.append('REPORT_END_DATES_MISSING')
    if s and s.get('cur') not in ('KRW', 'USD'):
        issues.append('REPORT_CURRENCY_UNKNOWN')
    return {'present': bool(s), 'ok': s.get('ok'), 'receipt': s.get('rcp'),
            'receipt_date': receipt_date(s.get('rcp')).isoformat() if receipt_date(s.get('rcp')) else None,
            'shape': s.get('shape'), 'orders_scope': s.get('orders_scope'),
            'row_count': len(rows), 'aggregate_row_indices': totals, 'issue_codes': issues,
            'duplicate_identities': [list(k) for k, n in identities.items() if n > 1],
            'unit': report_unit(s), 'backlog_raw_unscaled': b,
            'raw_numeric_cells': sum(number(r.get(k)) for r in rows for k in ('closing', 'gross', 'delivered')),
            'raw_missing_cells': sum(r.get(k) is None for r in rows for k in ('closing', 'gross', 'delivered')),
            'row_kind_counts': dict(Counter(r.get('kind') or 'unknown' for r in rows)),
            'exact_start_dates': sum(parse_date(r.get('order_date')) is not None for r in rows),
            'exact_end_dates': sum(parse_date(r.get('due')) is not None for r in rows),
            'date_pairs': sum(bool(parse_date(r.get('due')) and parse_date(r.get('order_date'))) for r in rows),
            'progress_observations': len(report_progress_rows(s, quarter)),
            'reconciliation': {'scope': 'raw_input_units_only; diagnostics_not_repairs',
                               'sum_present_all_rows_closing': all_present_sum if rows else None,
                               'sum_complete_nonaggregate_closing': leafsum,
                               'provided_minus_nonaggregate': b-leafsum if number(b) and number(leafsum) else None,
                               'gross_minus_delivered_minus_backlog': equation},
            'revenue_fy_col': s.get('revenue_fy_col'), 'revenue_period_semantics_verified': False,
            'security_note': s.get('security_note'), 'note': s.get('note') or s.get('unit_note')}


# Round 2 extension. Above: round-1 date, cohort, progress, interval and audit
# primitives retained. Below: verified units, sales-table monetary model and
# rolling-vintage scoring. No external dependencies or network operations.
REASONS.update({
    'NO_CURRENT_SALES_TABLE': '현재 기간 회사 매출표 없음',
    'REVENUE_PERIOD_AMBIGUOUS': '현재 기간 열과 누계 해석을 확인할 수 없음',
    'REVENUE_COLUMN_ORDER_AMBIGUOUS': '현재 기간보다 과거 열이 먼저 나옴; 값의 열 연결 미확인',
    'REVENUE_CURRENCY_AMBIGUOUS': '매출 통화가 원화인지 확정할 수 없음',
    'REVENUE_TOTAL_AMBIGUOUS': '중복 또는 결측으로 회사 매출 합계 확정 불가',
    'REVENUE_DETAIL_MISMATCH': '매출 상세와 합계 불일치; 상세 축 전망 보류',
    'REVENUE_ROUTE_MISMATCH': '내수·수출 합계 대사 실패; 판로 축 전망 보류',
    'REVENUE_YTD_DECREASE': '매출 누계 감소; 분기 금액 보류',
    'REPORT_SCOPE_ASSUMED': '전망 범위는 제공된 매출표 전체; 연결/별도 일치 별도 검증 필요',
    'REVENUE_YTD_ASSUMED': '사업보고서 매출표의 현재 기간을 연초 누계로 해석; 독립 원문 검증 없음',
    'BACKLOG_SCOPE_UNMATCHED': '매출 범위와 잔고 범위 연결 불충분; 잔고/신규 완전 분해 불가',
    'BACKLOG_TURNOVER_SHORT_HISTORY': '같은 범위 잔고/매출 회전기간 관측 2개 미만',
    'BACKLOG_INCONSISTENT': '잔고 행 대사 실패 또는 음수·중복·결측',
    'NEW_ORDER_REPLENISHMENT_ASSUMED': '미래 신규수주를 최근 분기 매출 속도에 연동한 조건부 가정',
    'TYPE_SPEED_NOT_VERIFIED': '유형별 실측 인식 속도 미확인; 유형별 차등 곡선 사용 안 함',
    'UNALLOCATED_REVENUE': '잔고·신규로 나누지 못한 매출을 별도 표시',
    'CAPTION_NOT_EXPORTED': '회사·분기 원문 캡션 미포함; 전역 정규화 계약 적용',
    'MIXED_CURRENCY_CAPTION': '캡션에 외화 병기; 표별 통화 연결 필요',
    'SUSPICIOUS_SALES_BACKLOG_SCALE': '매출표와 수주표 금액 간 현저한 괴리; 환산 수정 없이 보류',
    'NO_MONETARY_BACKTEST_TARGET': '유효한 회사 분기 매출 정답 표본 없음',
    'ZERO_ORIGIN_SALES_RATE': '관측 매출은 0이나 양의 신규수주·매출 속도를 정할 근거 없음',
})
TOTAL_WORDS = {'합계', '총계', '총합계', '계', '합계금액'}
AXES = ('defense', 'civil', 'mixed', 'unknown')
FACTORS = {'conservative': .8, 'base': 1., 'optimistic': 1.2}


def compact(s):
    return re.sub(r'\s+', '', str(s or ''))


def close_money(a, b):
    # Roundoff allowance in STORED units, never an inferred multiplier.
    return number(a) and number(b) and abs(a-b) <= max(.002, abs(a)*.0001, abs(b)*.0001)


def total_sales_row(r):
    return compact(r.get('seg')) in TOTAL_WORDS


def category(kind):
    return {'def': 'defense', 'civil': 'civil', 'mixed': 'mixed'}.get(kind, 'unknown')


def period_evidence(s, quarter):
    cols = s.get('revenue_cols') or []
    headers = [str(x) for x in cols if re.search(r'20\d\d|제\d+기|당반기|당분기', str(x))]
    if not headers:
        return None, 'REVENUE_PERIOD_AMBIGUOUS'
    first = headers[0]
    year, q = int(quarter[:4]), int(quarter[-1])
    years = re.findall(r'20\d\d', first)
    if years and int(years[0]) != year:
        return first, 'REVENUE_COLUMN_ORDER_AMBIGUOUS'
    term = re.search(r'제(\d+)기', first)
    terms = [int(t) for c in headers for t in re.findall(r'제(\d+)기', c)]
    if term and terms and int(term[1]) < max(terms):
        return first, 'REVENUE_COLUMN_ORDER_AMBIGUOUS'
    if q == 4:
        valid = not re.search(r'분기|반기', first)
    elif q == 2:
        valid = bool(re.search(r'반기|2\s*분기|6\.30|6월', first))
    else:
        valid = bool(re.search(rf'{q}\s*분기', first))
    return first, None if valid else 'REVENUE_PERIOD_AMBIGUOUS'


def sales_observation(s, quarter):
    result = {'quarter': quarter, 'value': None, 'money_unit': 'KRW_million',
              'receipt': s.get('rcp'), 'source_field': 'revenue_segments[].val',
              'source_rows': [], 'reason_codes': [], 'axes': None, 'routes': None,
              'period': 'year_to_date_assumption', 'scope': 'entire_reported_sales_table',
              'raw_unit_captions': s.get('_captions', []), 'conversion_applied': False}
    rows = s.get('revenue_segments') or []
    if not s.get('ok') or not rows:
        result['reason_codes'].append('NO_CURRENT_SALES_TABLE')
        return result
    if not s.get('_normalized_million'):
        result['reason_codes'].append('REPORT_SCALE_NOT_EXPORTED')
        return result
    header, reason = period_evidence(s, quarter)
    result['current_header'] = header
    if reason:
        result['reason_codes'].append(reason)
        return result
    captions = s.get('_captions', [])
    if s.get('cur') == 'USD':
        result['reason_codes'].append('REVENUE_CURRENCY_AMBIGUOUS')
        return result
    if not captions:
        result['reason_codes'].append('CAPTION_NOT_EXPORTED')
    if any(re.search(r'USD|달러|\$', cap, re.I) for cap in captions):
        result['reason_codes'].append('MIXED_CURRENCY_CAPTION')
    totals = [(i, r) for i, r in enumerate(rows) if total_sales_row(r)]
    group_rows = defaultdict(list)
    for i, r in enumerate(rows):
        if not total_sales_row(r):
            group_rows[(compact(r.get('seg')), compact(r.get('item')))].append((i, r))
    groups = []
    for key, entries in group_rows.items():
        # Product subtotals can overlap leaf rows; retain only leaf item groups.
        if any(word in key[1] for word in ('소계', '합계', '총계')):
            continue
        bykind = defaultdict(list)
        for i, r in entries:
            bykind[r.get('kind')].append((i, r))
        if any(len(v) != 1 for v in bykind.values()):
            continue
        explicit = bykind.get('합계', [])
        selected = explicit or [x for kind in ('내수', '수출') for x in bykind.get(kind, [])]
        if not selected or not all(number(r.get('val')) and r['val'] >= 0 for _, r in selected):
            continue
        amount = sum(r['val'] for _, r in selected)
        kinds = {category(r.get('segkind')) for _, r in entries}
        cat = next(iter(kinds)) if len(kinds) == 1 else 'unknown'
        route = {k: bykind[k][0][1]['val'] if k in bykind else None for k in ('내수', '수출')}
        # Missing export/domestic is not zero. A route is known only if it
        # independently reconciles to this item total with BOTH sides present.
        routes_ok = all(number(v) and v >= 0 for v in route.values()) and close_money(sum(route.values()), amount)
        groups.append({'identity': list(key), 'value': amount, 'axis': cat,
                       'source_rows': [i for i, _ in selected], 'routes': route if routes_ok else None})
    whole = [(i, r) for i, r in totals if r.get('kind') == '합계']
    if len(whole) == 1 and number(whole[0][1].get('val')):
        amount, selected = whole[0][1]['val'], [whole[0][0]]
        result['total_basis'] = 'explicit_grand_total'
    elif not whole and totals:
        kinds = Counter(r.get('kind') for _, r in totals)
        if not all(k in ('내수', '수출') and n == 1 for k, n in kinds.items()):
            result['reason_codes'].append('REVENUE_TOTAL_AMBIGUOUS'); return result
        amount, selected = strict_sum(r.get('val') for _, r in totals), [i for i, _ in totals]
        result['total_basis'] = 'explicit_grand_total_route_rows'
    elif not totals and groups and len(groups) == len(group_rows):
        amount = sum(g['value'] for g in groups)
        selected = [i for g in groups for i in g['source_rows']]
        result['total_basis'] = 'nonoverlapping_table_items_scope_assumed'
    else:
        result['reason_codes'].append('REVENUE_TOTAL_AMBIGUOUS'); return result
    if not number(amount) or amount < 0:
        result['reason_codes'].append('REVENUE_TOTAL_AMBIGUOUS'); return result
    # Reject apparent cross-table scale corruption without repairing a value.
    delivered = s.get('delivered')
    if number(delivered) and delivered > amount*10000:
        result['reason_codes'].append('SUSPICIOUS_SALES_BACKLOG_SCALE'); return result
    result.update(value=amount, source_rows=selected)
    if groups and close_money(sum(g['value'] for g in groups), amount):
        # Any small report rounding residual is shown separately; not allocated.
        result['axes'] = {axis: sum(g['value'] for g in groups if g['axis'] == axis)
                          if any(g['axis'] == axis for g in groups) else None for axis in AXES}
        result['axes_rounding_residual'] = amount-sum(v for v in result['axes'].values() if number(v))
        result['axis_semantics'] = 'literal_parsed_classification; absent_category_is_null_not_economic_zero'
        result['groups'] = groups
    else:
        result['reason_codes'].append('REVENUE_DETAIL_MISMATCH')
    route_rows = {kind: [(i, r) for i, r in totals if r.get('kind') == kind] for kind in ('내수', '수출')}
    if all(len(v) == 1 for v in route_rows.values()):
        routes = {k: v[0][1].get('val') for k, v in route_rows.items()}
    elif groups and result['axes'] is not None and all(g['routes'] is not None for g in groups):
        routes = {k: sum(g['routes'][k] for g in groups) for k in ('내수', '수출')}
    elif selected and all(rows[i].get('kind') in ('내수', '수출') for i in selected) and {rows[i]['kind'] for i in selected} == {'내수', '수출'}:
        # Exhaustive selected leaf rows are themselves explicitly routed.
        # E.g. KAI domestic defense + exported aircraft/components. No null
        # cell is converted to zero and no subtotal is counted twice.
        routes = {k: sum(rows[i]['val'] for i in selected if rows[i]['kind'] == k) for k in ('내수', '수출')}
    else:
        routes = None
    if routes and all(number(v) and v >= 0 for v in routes.values()) and close_money(sum(routes.values()), amount):
        result['routes'] = routes
        result['route_rounding_residual'] = amount-sum(routes.values())
    else:
        result['reason_codes'].append('REVENUE_ROUTE_MISMATCH')
    return result


def sales_history(company, origin=None):
    return {q: sales_observation(s, q) for q, s in sorted(company.get('quarters', {}).items())
            if origin is None or q <= origin}


def observed_quarter(history, q, axis=None):
    current = history.get(q, {})
    def val(r):
        return r.get('value') if axis is None else (r.get('axes') or {}).get(axis)
    amount = val(current)
    if not number(amount):
        return None
    if q.endswith('Q1'):
        return amount
    previous = val(history.get(qadd(q, -1), {}))
    if not number(previous) or amount < previous:
        return None
    return amount-previous


def ledger_balance(s, axis):
    """No report totals are added to detail, subsidiaries or disclosures."""
    if not s.get('ok') or s.get('cur') != 'KRW':
        return None
    rows = s.get('segments', [])
    selected = [(i, r) for i, r in enumerate(rows) if not aggregate_row(r)
                and (axis == 'all' or category(r.get('kind')) == axis)]
    if not selected:
        return None
    # An all-company ledger cannot be established from unlabeled multi-row
    # tables. Only a single report-wide balance row is accepted for this case.
    if axis == 'all' and (len(selected) != 1 or s.get('shape') != 'balance'):
        return None
    if len({identity(r) for _, r in selected}) != len(selected):
        return None
    for _, r in selected:
        b, g, d = r.get('closing'), r.get('gross'), r.get('delivered')
        if not number(b) or b < 0:
            return None
        if number(g) and number(d) and not close_money(g-d, b):
            return None
    value = sum(r['closing'] for _, r in selected)
    if value <= 0:
        return None
    return {'value': value, 'source_rows': [i for i, _ in selected],
            'receipt': s.get('rcp'), 'axis': axis, 'scope_verified': False,
            'scope_basis': 'same_explicit_def_or_civil_tags' if axis != 'all' else 'single_report_wide_balance_row'}


def model_blocks_v2(company, origin, history):
    current = history[origin]
    qcount = int(origin[-1])
    categories = current['axes'] if current.get('axes') is not None else {'all': current['value']}
    # Rounding residual is preserved as an unallocated forecasting block.
    if current.get('axes_rounding_residual'):
        categories = dict(categories, rounding=current['axes_rounding_residual'])
    blocks = []
    for axis, ytd in categories.items():
        if not number(ytd) or ytd == 0:
            continue
        rate = ytd/qcount
        balance = ledger_balance(company['quarters'][origin], axis) if axis in ('defense', 'civil', 'all') else None
        # Blank/unclassified sales with one report-wide balance may be linked
        # only when this is the ONLY nonzero sales axis.
        if axis == 'unknown' and len([v for v in categories.values() if number(v) and v != 0]) == 1:
            balance = ledger_balance(company['quarters'][origin], 'all')
        samples = []
        if balance:
            for q, obs in history.items():
                ax = None if axis == 'all' else axis
                v = obs.get('value') if ax is None else (obs.get('axes') or {}).get(ax)
                b = ledger_balance(company['quarters'][q], balance['axis'])
                if b and number(v) and v > 0:
                    samples.append({'quarter': q, 'duration_quarters': b['value']/(v/int(q[-1])),
                                    'balance': b['value'], 'sales_ytd': v, 'receipt': obs['receipt']})
        eligible = bool(balance and len(samples) >= 2 and rate > 0)
        duration = statistics.median(x['duration_quarters'] for x in samples) if eligible else None
        blocks.append({'axis': axis, 'sales_ytd': ytd, 'quarterly_run_rate': rate,
                       'balance': balance, 'duration_samples': samples,
                       'duration_quarters': duration, 'backlog_model': eligible,
                       'new_orders_per_quarter_assumption': rate if eligible else None,
                       'method': 'reported_backlog_uniform_runoff_plus_new_cohorts' if eligible else 'sales_ytd_run_rate',
                       'reason': None if eligible else ('BACKLOG_TURNOVER_SHORT_HISTORY' if balance else 'BACKLOG_SCOPE_UNMATCHED')})
    return blocks


def block_path(block, factor=1., stretch=1., n=10):
    if not block['backlog_model']:
        return [{'existing': None, 'new': None, 'unallocated': block['quarterly_run_rate']*factor,
                 'value': block['quarterly_run_rate']*factor} for _ in range(n)]
    duration = block['duration_quarters']*stretch
    b = block['balance']['value']
    evidence = block.get('ledger_order_evidence', {})
    if evidence.get('available'):
        probability = {.6: .1, .8: .25, 1.: .5, 1.2: .75, 1.4: .9}[factor]
        order = quantile([r['order_proxy'] for r in evidence['samples']], probability)
    else:
        order = block.get('new_orders_per_quarter_assumption', block['quarterly_run_rate'])*factor
    timing = [{'ctype': 'FOLLOW', 'weight': 1., 'duration_quarters': duration, 'lag_quarters': 0.}]
    new, _ = new_order_path(order, timing, n)
    return [{'existing': b*(min(1., h/duration)-min(1., (h-1)/duration)),
             'new': new[h-1], 'unallocated': 0.,
             'value': b*(min(1., h/duration)-min(1., (h-1)/duration))+new[h-1]} for h in range(1, n+1)]


def monetary_projection(company, origin=ORIGIN, order_mode="ledger_pairs"):
    history = sales_history(company, origin)
    decision = receipt_date(history.get(origin, {}).get('receipt'))
    if decision:
        history = {q: s for q, s in history.items()
                   if receipt_date(s.get('receipt')) and receipt_date(s['receipt']) <= decision}
    obs = history.get(origin, {'value': None, 'reason_codes': ['NO_ORIGIN_REPORT']})
    result = {'available': number(obs.get('value')) and obs['value'] > 0, 'origin_observation': obs,
              'observed_sales_ytd': history, 'blocks': [], 'scenarios': {},
              'reason_codes': list(obs['reason_codes'])}
    if not result['available']:
        if obs.get('value') == 0:
            result['reason_codes'].append('ZERO_ORIGIN_SALES_RATE')
        return result
    blocks = model_blocks(company, origin, history, order_mode)
    result['blocks'] = blocks
    result['reason_codes'] += ['REPORT_SCOPE_ASSUMED', 'REVENUE_YTD_ASSUMED', 'TYPE_SPEED_NOT_VERIFIED']
    if any(b.get('ledger_order_evidence', {}).get('available') for b in blocks):
        result['reason_codes'].append('LEDGER_NET_ORDER_PROXY')
    if any(b['backlog_model'] and not b.get('ledger_order_evidence', {}).get('available') for b in blocks):
        result['reason_codes'].append('NEW_ORDER_REPLENISHMENT_ASSUMED')
    if not all(b['backlog_model'] for b in blocks):
        result['reason_codes'] += ['BACKLOG_SCOPE_UNMATCHED', 'UNALLOCATED_REVENUE']
    path_grid = {(factor, stretch): [block_path(b, factor, stretch) for b in blocks]
                 for factor in (.6, .8, 1., 1.2, 1.4) for stretch in (.8, 1., 1.2)}
    for scenario, factor in FACTORS.items():
        paths = path_grid[factor, 1.]
        qs = []
        for h in range(10):
            parts = [p[h] for p in paths]
            value = sum(p['value'] for p in parts)
            matched = [p for p in parts if p['existing'] is not None]
            existing = sum(p['existing'] for p in matched) if matched else None
            new = sum(p['new'] for p in matched) if matched else None
            unallocated = sum(p['unallocated'] for p in parts)
            axes = {axis: sum(p['value'] for b, p in zip(blocks, parts) if b['axis'] == axis)
                    if number((obs.get('axes') or {}).get(axis)) else None for axis in AXES}
            if any(b['axis'] == 'all' for b in blocks):
                axes = None
            routes = None
            if obs.get('routes'):
                routes = {k: value*v/obs['value'] for k, v in obs['routes'].items()}
            grid = [sum(p[h]['value'] for p in ps) for ps in path_grid.values()]
            component_bands = {}
            for key, field in [('existing', 'covered_existing_backlog_interval'),
                               ('new', 'covered_new_order_interval'),
                               ('unallocated', 'unallocated_interval')]:
                values = [[p[h][key] for p in ps if p[h][key] is not None] for ps in path_grid.values()]
                component_bands[field] = interval([sum(v) for v in values] if all(values) else [],
                                                   'explicit_order_and_duration_grid_component_envelope')
            qs.append({'quarter': qadd(origin, h+1), 'horizon': h+1, 'value': value,
                       'existing_backlog_revenue': existing if unallocated == 0 else None,
                       'new_order_revenue': new if unallocated == 0 else None,
                       'covered_existing_backlog_revenue': existing, 'covered_new_order_revenue': new,
                       'unallocated_revenue': unallocated, 'axes': axes, 'routes': routes, **component_bands,
                       'axes_rounding_residual': value-sum(v for v in axes.values() if number(v)) if axes else None,
                       'route_rounding_residual': value-sum(routes.values()) if routes else None,
                       'route_method': 'fixed_origin_sales_mix_assumption' if routes else None,
                       'interval': interval(grid, 'ledger_proxy_P10_to_P90_or_fallback_rate_x0.6_to1.4_duration_x0.8_to1.2'),
                       'decomposition_complete': unallocated == 0 and bool(matched),
                       'scope': 'entire_reported_company_sales_table_conditional'})
        annual = []
        for year in range(int(origin[:4]), int(origin[:4])+3):
            future = [r for r in qs if r['quarter'].startswith(str(year))]
            observed = obs['value'] if year == int(origin[:4]) else 0.
            complete = len(future) == (4-int(origin[-1]) if year == int(origin[:4]) else 4)
            components = {key: strict_sum(r[key] for r in future) for key in (
                'existing_backlog_revenue', 'new_order_revenue', 'covered_existing_backlog_revenue',
                'covered_new_order_revenue', 'unallocated_revenue')}
            band = sum_intervals(future, 'interval')
            for key in ('lower', 'upper'):
                if number(band[key]):
                    band[key] += observed
            future_axes = {axis: strict_sum(r['axes'][axis] for r in future) for axis in AXES} if all(r['axes'] is not None for r in future) else None
            axes = None
            if future_axes is not None and (year != int(origin[:4]) or obs.get('axes') is not None):
                axes = {axis: strict_sum([future_axes[axis], obs['axes'][axis] if year == int(origin[:4]) else 0.]) for axis in AXES}
            routes = None
            if all(r['routes'] is not None for r in future) and (year != int(origin[:4]) or obs.get('routes')):
                routes = {k: sum(r['routes'][k] for r in future)+(obs['routes'][k] if year == int(origin[:4]) else 0.) for k in ('내수', '수출')}
            annual.append({'fiscal_year': year, 'value': observed+sum(r['value'] for r in future) if complete else None,
                           'observed_revenue': observed, 'observed_quarters_required': int(origin[-1]) if year == int(origin[:4]) else 0,
                           'observed_revenue_basis': 'origin_sales_YTD_not_revenue_fy_not_delivered',
                           'future_quarters': len(future), 'complete': complete, **components,
                           'component_scope': 'future_only; observed_YTD_is_separate',
                           'axes': axes, 'routes': routes, 'interval': band,
                           **{key: sum_intervals(future, key) for key in (
                               'covered_existing_backlog_interval', 'covered_new_order_interval', 'unallocated_interval')},
                           'axes_rounding_residual': (observed+sum(r['value'] for r in future))-sum(v for v in axes.values() if number(v)) if axes else None,
                           'route_rounding_residual': (observed+sum(r['value'] for r in future))-sum(routes.values()) if routes else None,
                           'decomposition_complete': all(r['decomposition_complete'] for r in future),
                           'existing_share_of_modelled_future': components['covered_existing_backlog_revenue']/sum(r['value'] for r in future)
                           if number(components['covered_existing_backlog_revenue']) and sum(r['value'] for r in future) else None})
        result['scenarios'][scenario] = {'assumptions': {
            'calibrated': False, 'new_order_and_unallocated_run_rate_factor': factor,
            'new_order_proxy_quantile': SCENARIOS[scenario],
            'new_order_rule': 'eligible_pair_proxy_P25_P50_P75; otherwise_round2_rate_x0.8_1.0_1.2',
            'existing_schedule_same_across_scenarios': True,
            'new_award_timing': 'each_future_quarter_end; no_same_quarter_recognition',
            'duration': 'median_same_scope_backlog_divided_by_YTD_quarterly_sales_rate',
            'type_specific_speed_used': False, 'growth_compounding': False,
            'route_mix': 'fixed_origin_mix_if_reconciled; unknown_remains_unknown'}, 'quarterly': qs, 'annual': annual}
    return result


def normalized_inputs(reports, units):
    if not isinstance(units.get('unit_contract'), str) or '백만원' not in units['unit_contract']:
        raise ValueError('missing verified million-unit contract')
    # Attach metadata only; no monetary cell is modified.
    for stock, c in reports['companies'].items():
        for q, s in c['quarters'].items():
            s['_normalized_million'] = True
            s['_captions'] = units.get('companies', {}).get(stock, {}).get(q, [])
    return reports


def make_company_v2(u, report, active, retained, prior):
    # Carry forward round-1 cohort filters, report audit, ratio evidence and
    # schedule decomposition; keep that partial scope separate from totals.
    f = project_company(u, report, active, retained)
    legacy_scenarios = f.pop('scenarios')
    f['disclosure_only_scenarios'] = legacy_scenarios
    obsolete = {'REPORT_SCALE_NOT_EXPORTED', 'COMPANY_TOTAL_UNIDENTIFIED', 'NO_MONETARY_BACKTEST_TARGET'}
    f['reason_codes'] = [r for r in f['reason_codes'] if r not in obsolete]
    for scenario in legacy_scenarios.values():
        for row in scenario['quarterly']:
            row['reason_codes'] = [r for r in row['reason_codes'] if r not in obsolete]
        for row in scenario['annual']:
            row['observed_revenue_basis'] = 'disclosure_schedule_has_no_observed_company_revenue'
    money = monetary_projection(report)
    f['monetary_evidence'] = {k: v for k, v in money.items() if k != 'scenarios'}
    f['scenarios'] = money['scenarios'] if money['available'] else {
        key: {'assumptions': {'calibrated': False},
              'quarterly': [{'quarter': qadd(ORIGIN, h), 'horizon': h, 'value': None,
                             'existing_backlog_revenue': None, 'new_order_revenue': None,
                             'interval': interval([])} for h in range(1, 11)],
              'annual': [{'fiscal_year': y, 'value': None, 'complete': False, 'interval': interval([])} for y in (2026, 2027, 2028)]}
        for key in FACTORS}
    f['company_total_available'] = money['available']
    f['status'] = 'company_total_conditional' if money['available'] else f['status']
    f['integration_status'] = f['status']
    f['reason_codes'] = sorted(set(f['reason_codes']+money['reason_codes']+['TYPE_SPEED_NOT_VERIFIED']))
    f['audit_blockers'] = [REASONS[x] for x in f['reason_codes']]
    f['scope'] = 'entire_reported_sales_table_conditional' if money['available'] else 'partial_disclosures_only'
    f['unit_audit'].update(verified_at_origin=bool(report.get('quarters', {}).get(ORIGIN, {}).get('ok')), unit_declared_by_assignment=True,
                           report_money_unit='already_normalized_million; currency_is_separate', conversion_applied=False)
    f['provenance'].update(report_raw_captions_supplied=True, report_availability='origin_report_receipt_date; not origin_quarter_end')
    f['financial_statement_revenue'] = False
    f['coverage']['monetary_report_rows'] = sum(number(r.get('closing')) for r in report.get('quarters', {}).get(ORIGIN, {}).get('segments', []))
    f['coverage']['company_totals_additive'] = False
    f['coverage']['full_existing_coverage'] = bool(money['available'] and all(b['backlog_model'] for b in money['blocks']))
    f['prior_audit'] = {'status': prior.get('status'), 'reason_codes': prior.get('reason_codes', []),
                        'resolved_reason_codes': ['REPORT_SCALE_NOT_EXPORTED']}
    f['actual_revenue_proxy'] = {q: observed_quarter(money['observed_sales_ytd'], q) for q in money['observed_sales_ytd']}
    f['audit_can']['backtest'] = 'company_sales_snapshot_backtest_plus_progress'
    f['audit_can']['matrix'] = 'conditional' if money['available'] else 'partial'
    # Observed row balances, including CIVIL, now support separate monetary
    # runoff wherever an exact future endpoint exists; never add to totals.
    rows = report.get('quarters', {}).get(ORIGIN, {}).get('segments', [])
    counts = Counter(identity(r) for r in rows)
    ledger = []
    snapshot = report.get('quarters', {}).get(ORIGIN, {})
    if snapshot.get('cur') == 'KRW':
        for i, r in enumerate(rows):
            end, b = parse_date(r.get('due')), r.get('closing')
            if aggregate_row(r) or counts[identity(r)] != 1 or not end or end <= qend(ORIGIN) or not number(b) or b < 0:
                continue
            if number(r.get('gross')) and number(r.get('delivered')) and not close_money(r['gross']-r['delivered'], b):
                continue
            days = (end-qend(ORIGIN)).days
            path = [b*(min(1., (qend(qadd(ORIGIN,h))-qend(ORIGIN)).days/days)-min(1., (qend(qadd(ORIGIN,h-1))-qend(ORIGIN)).days/days)) for h in range(1,11)]
            ledger.append({'row_index': i, 'label': r['label'], 'axis': category(r.get('kind')),
                           'balance': b, 'end': end.isoformat(), 'quarterly': path,
                           'method': 'observed_remaining_balance_uniform_to_exact_due_date', 'calibrated': False})
    f['ledger_money_runoff'] = ledger
    if ledger and f['status'] == 'unavailable':
        f['status'] = f['integration_status'] = 'partial'
    return f


def money_backtest(reports, order_mode="ledger_pairs"):
    samples, annual, excluded = [], [], Counter()
    for stock, company in reports['companies'].items():
        history = sales_history(company)
        for origin in sorted(history):
            model = monetary_projection(company, origin, order_mode)
            if not model['available']:
                excluded['origin_sales_invalid'] += 1; continue
            decision = receipt_date(history[origin].get('receipt'))
            for row in model['scenarios']['base']['quarterly']:
                target = row['quarter']
                actual = observed_quarter(history, target)
                if not number(actual):
                    excluded['missing_invalid_or_negative_quarter_target'] += 1; continue
                target_date = receipt_date(history[target].get('receipt'))
                if not decision or not target_date or target_date <= decision:
                    excluded['filing_order_not_verifiable'] += 1; continue
                previous_truth = history.get(qadd(target, -1), {}) if not target.endswith('Q1') else None
                if previous_truth is not None and (not receipt_date(previous_truth.get('receipt')) or receipt_date(previous_truth['receipt']) > target_date):
                    excluded['target_previous_YTD_filed_later'] += 1; continue
                target_start = qend(qadd(target, -1))+timedelta(days=1)
                last = observed_quarter(model['observed_sales_ytd'], origin)
                # Origin rate is also a transparent baseline when the actual
                # preceding quarter is unavailable; never fill target truth.
                baseline = last if number(last) else history[origin]['value']/int(origin[-1])
                samples.append({'stock': stock, 'origin': origin, 'target': target, 'horizon': row['horizon'],
                                'prediction': row['value'], 'actual': actual, 'persistence': baseline,
                                'interval': row['interval'], 'origin_receipt': history[origin]['receipt'],
                                'target_receipt': history[target]['receipt'], 'decision_date': decision.isoformat(),
                                'forward_only': decision < target_start,
                                'target_source_rows': history[target]['source_rows'],
                                'origin_source_rows': history[origin]['source_rows'],
                                'target_sales_ytd': history[target]['value'],
                                'previous_target_sales_ytd': previous_truth.get('value') if previous_truth is not None else None,
                                'previous_target_receipt': history.get(qadd(target,-1), {}).get('receipt') if not target.endswith('Q1') else None,
                                'truth_basis': 'sales_table_YTD_difference; supplied_snapshot_not_original_vintage',
                                'backlog_blocks': sum(b['backlog_model'] for b in model['blocks'])})
            for fyh in (0, 1, 2):
                if fyh == 0 and origin.endswith('Q4'):
                    continue  # Already observed annual totals are not forecasts.
                year = int(origin[:4])+fyh
                qs = [f'{year}Q{i}' for i in range(1,5)]
                truth = [observed_quarter(history, q) for q in qs]
                predicted = next(r for r in model['scenarios']['base']['annual'] if r['fiscal_year'] == year)
                target_receipt = history.get(qs[-1], {}).get('receipt')
                if not all(number(x) for x in truth):
                    excluded['annual_truth_incomplete'] += 1
                    continue
                if not number(predicted['value']):
                    excluded['annual_forecast_beyond_ten_quarter_window'] += 1
                    continue
                if not decision or not receipt_date(target_receipt):
                    excluded['annual_filing_date_unverifiable'] += 1
                    continue
                if receipt_date(target_receipt) <= decision:
                    excluded['annual_target_not_after_decision'] += 1
                    continue
                receipts = [receipt_date(history.get(q, {}).get('receipt')) for q in qs]
                if any(d is None or d > receipt_date(target_receipt) for d in receipts):
                    excluded['annual_component_filed_after_year_end_target'] += 1
                    continue
                annual.append({'stock': stock, 'origin': origin, 'fiscal_year': year, 'fy_horizon': fyh,
                               'prediction': predicted['value'], 'actual': sum(truth),
                               'persistence': history[origin]['value']/int(origin[-1])*4,
                               'actual_quarters': dict(zip(qs, truth)),
                               'target_receipt': target_receipt, 'origin_receipt': history[origin]['receipt'],
                               'actual_quarter_receipts': {q: history[q]['receipt'] for q in qs},
                               'observed_revenue': predicted['observed_revenue'],
                               'future_quarters': predicted['future_quarters'],
                               'decision_date': decision.isoformat(), 'forward_only': decision < date(year,1,1)})
    summary = {'calibrated': False, 'money_unit': 'KRW_million',
               'scope': 'entire_reported_company_sales_table_conditional_model',
               'availability_basis': 'origin_filing_date; T+1 may be nowcast; forward_only subset separately scored',
               'limitations': ['same supplied snapshot; archived original vintages unavailable',
                              'YTD semantics follow current-period sales heading; not independently reread from raw filings',
                              'overlapping origins and affiliated companies are not independent samples',
                              'sensitivity envelope is not calibrated even when longer-horizon samples exist'],
               'monetary': metrics(samples, unit='KRW_million'),
               'forward_only': metrics([r for r in samples if r['forward_only']], unit='KRW_million'),
               'model_slices': {'with_backlog_blocks': metrics([r for r in samples if r['backlog_blocks']], unit='KRW_million'),
                                'sales_run_rate_only': metrics([r for r in samples if not r['backlog_blocks']], unit='KRW_million')},
               'quarterly': [], 'annual': [], 'excluded': dict(excluded),
               'rows': samples, 'annual_rows': annual}
    for h in range(1, 11):
        rows = [r for r in samples if r['horizon'] == h]
        summary['quarterly'].append({'horizon': h, **metrics(rows, unit='KRW_million'),
                                    'persistence': metrics(rows, 'persistence', 'KRW_million'),
                                    'forward_only': metrics([r for r in rows if r['forward_only']], unit='KRW_million'),
                                    'sensitivity_covered_n': sum(r['interval']['lower'] <= r['actual'] <= r['interval']['upper'] for r in rows),
                                    'calibrated': False})
    for h in (0,1,2):
        rows = [r for r in annual if r['fy_horizon'] == h]
        summary['annual'].append({'fy_horizon': h, **metrics(rows, unit='KRW_million'),
                                 'persistence': metrics(rows, 'persistence', 'KRW_million'),
                                 'forward_only': metrics([r for r in rows if r['forward_only']], unit='KRW_million')})
    return summary


def ledger_order_pairs(company, origin, history, axis, balance_axis):
    """Conditional net additions proxy, never gross awards or observed orders.

    Aggregated segment membership can change as contracts enter/leave. We do
    not join individual contract rows or count those rows as independent samples.
    Each eligible observation is exactly one adjacent calendar-quarter pair.
    """
    samples, rejected = [], []
    quarters = company.get('quarters', {})
    decision = receipt_date(history.get(origin, {}).get('receipt'))
    candidates = sorted(q for q in quarters if q <= origin and qadd(q, -1) in quarters)
    for q in candidates:
        previous = qadd(q, -1)
        s0, s1 = quarters[previous], quarters[q]
        record = {'previous_quarter': previous, 'quarter': q, 'axis': axis,
                  'balance_axis': balance_axis, 'previous_receipt': s0.get('rcp'),
                  'receipt': s1.get('rcp'), 'reason_codes': []}
        reasons = record['reason_codes']
        d0, d1 = receipt_date(s0.get('rcp')), receipt_date(s1.get('rcp'))
        if not decision or not d0 or not d1 or not d0 < d1 <= decision:
            reasons.append('PAIR_FILING_ORDER_OR_VINTAGE_INVALID')
        if previous not in history or q not in history:
            reasons.append('PAIR_SALES_UNAVAILABLE_AT_DECISION')
        if not s0.get('_normalized_million') or not s1.get('_normalized_million'):
            reasons.append('PAIR_UNIT_CONTRACT_MISSING')
        b0, b1 = ledger_balance(s0, balance_axis), ledger_balance(s1, balance_axis)
        if not b0 or not b1:
            reasons.append('PAIR_BALANCE_INVALID_OR_UNMATCHED')
        elif s0.get('shape') != s1.get('shape'):
            reasons.append('PAIR_LEDGER_SHAPE_CHANGED')
        # Unknown scope is not silently promoted to verified. A transition
        # between known/unknown scope is excluded too; no fuzzy scope repair.
        if s0.get('orders_scope') != s1.get('orders_scope'):
            reasons.append('PAIR_SCOPE_CHANGED')
        sales_axis = None if axis == 'all' else axis
        value = observed_quarter(history, q, sales_axis)
        if not number(value):
            reasons.append('PAIR_QUARTER_SALES_MISSING_OR_NEGATIVE')
        # Q1 resets YTD, but both endpoints still need the selected sales axis
        # to exist: an absent previous segment cannot establish continuity.
        previous_obs = history.get(previous, {})
        previous_sales = (previous_obs.get('value') if sales_axis is None else
                          (previous_obs.get('axes') or {}).get(sales_axis))
        if not number(previous_sales):
            reasons.append('PAIR_PREVIOUS_SALES_SCOPE_MISSING')
        if b0 and b1 and number(value):
            proxy = b1['value']-b0['value']+value
            record.update(previous_balance=b0['value'], balance=b1['value'],
                          sales_quarter=value, order_proxy=proxy,
                          previous_source_rows=b0['source_rows'], source_rows=b1['source_rows'],
                          sales_ytd=history.get(q, {}).get('value') if sales_axis is None else
                          (history.get(q, {}).get('axes') or {}).get(sales_axis),
                          previous_sales_ytd=previous_sales,
                          identity_set_changed={identity(s0['segments'][i]) for i in b0['source_rows']} !=
                          {identity(s1['segments'][i]) for i in b1['source_rows']})
            if proxy < 0:
                reasons.append('PAIR_NEGATIVE_NET_ADDITIONS')
        if reasons:
            rejected.append(record)
        else:
            samples.append(record)
    eligible = len(samples) >= 4
    return {'available': eligible, 'minimum_quarters': 4, 'sample_quarters': len(samples),
            'candidate_pairs': len(candidates), 'samples': samples, 'rejected_pairs': rejected,
            'rejection_counts': dict(Counter(code for r in rejected for code in r['reason_codes'])),
            'quantiles': {s: quantile([r['order_proxy'] for r in samples], p) if eligible else None
                          for s, p in SCENARIOS.items()},
            'P10': quantile([r['order_proxy'] for r in samples], .1) if eligible else None,
            'P90': quantile([r['order_proxy'] for r in samples], .9) if eligible else None,
            'reason': None if eligible else 'LEDGER_PAIR_SAMPLE_LT4', 'calibrated': False,
            'scope_verified': False, 'currency': 'KRW', 'money_unit': 'KRW_million',
            'basis': 'B_t - B_(t-1) + same_axis_quarter_sales; adjustments assumed absent',
            'limitations': ['not observed gross new orders; cancellations/FX/reclassifications are not isolated',
                           'negative net additions are retained as rejected evidence, never clipped to zero',
                           'nonnegative sample selection can bias the future-cohort assumption upward',
                           'same parsed segment tags/single company balance assumed scope-compatible; no raw-filing verification',
                           'aggregate contract membership may change; no individual-contract continuity is asserted']}


def model_blocks(company, origin, history, order_mode='ledger_pairs'):
    blocks = model_blocks_v2(company, origin, history)
    if order_mode == 'round2':
        return blocks
    if order_mode != 'ledger_pairs':
        raise ValueError('unknown order mode')
    for block in blocks:
        if block['balance']:
            evidence = ledger_order_pairs(company, origin, history, block['axis'], block['balance']['axis'])
            block['ledger_order_evidence'] = evidence
            if block['backlog_model'] and evidence['available']:
                block['new_orders_per_quarter_assumption'] = evidence['quantiles']['base']
                block['method'] = 'reported_backlog_runoff_plus_adjacent_pair_net_additions_proxy'
            block['new_order_estimation_status'] = ('eligible_conditional_proxy' if evidence['available']
                                                      else 'needs_qualified_pairs')
        else:
            block['new_order_estimation_status'] = 'scope_unmatched'
    return blocks


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n', encoding='utf-8')


def fmt(x):
    return f'{x:,.3f}' if number(x) else '—'


def write_report_v2(path, panel):
    pop, bt = panel['population'], panel['backtest']
    lines = ['# ARGUS-kdef 2차 — 회사 전체 조건부 매출 전망', '',
             f"71사 중 회사 전체 조건부 금액 {pop['company_total_forecast_companies']}사, 계약/행 부분 전망 {pop['status_counts'].get('partial',0)}사, 미추정 {pop['status_counts'].get('unavailable',0)}사. 금액은 백만원. 회사 간 합계는 만들지 않는다.", '',
             '## 단위와 범위', '',
             '제공된 `kdef_unit_evidence.json`의 파서 계약을 적용했다. `_UNIT_SCALE` 및 적용 행은 사용자 제공 증거이며 파서 정본을 직접 확인한 것은 아니다. 저장값의 적용 배수는 항상 1이다. 억원·천원·원 캡션을 보고 저장값을 다시 환산하지 않았다. 통화는 배수와 별개이며 USD 잔고는 KRW에 합치지 않는다.',
             f"원문 캡션은 {panel['unit_evidence']['company_count']}사 {panel['unit_evidence']['quarter_count']}분기. 캡션이 없는 분기에도 전역 정규화 계약은 적용하며 누락 사실은 보존한다.",
             '회사 전체란 제공된 매출표 전체의 조건부 금액이다. 연결재무제표 매출임을 보증하지 않는다. 12월 결산과 현재 매출 열의 연초 누계 해석은 가정이다. 매출표 합계가 있으면 그 행을 사용하고 상세·내수·수출을 중복 합산하지 않는다. `revenue_fy`, `sales_all`, `revenue_domestic/export`를 당기 누계의 대체값으로 쓰지 않는다.', '',
             '## 모형과 방산 축', '',
             '방산·CIVIL·혼합·미분류는 원장/매출표의 명시 태그를 유지한다. 미분류를 방산이나 민수로 채우지 않으며, 해당 분류 행이 없으면 0이 아니라 null이다. 원문의 특수선 등 혼합 가능 태그는 독립 검증되지 않았다. 상세와 전체가 대사되지 않으면 축별 전망을 보류한다. 내수/수출은 양쪽이 전체에 대사될 때만 기준분기 비중을 고정한 조건부 전망으로 낸다. 발주처 국적을 수출액으로 대입하지 않는다. 소액 반올림 차이는 axes/route_rounding_residual에 보존한다.',
             '동일 명시 방산/CIVIL 범위의 잔고가 유효하거나 하나의 회사 전체 잔고 행이 확인되면, 최소 2개 관측의 D=잔고/(연초누계매출/경과분기) 중앙값을 소진기간으로 가정한다. 이는 인도표나 실측 인식 속도가 아니다. 기존분 E_h=B0×[clip(h/D)-clip((h−1)/D)]. 신규 코호트는 각 미래 분기 말 발생하고 같은 D에 걸쳐 선형 인식한다. 신규수주 O는 최근 매출 속도×시나리오 계수라는 가정이며 실제 순수주를 추정한 값이 아니다.',
             '보수/기준/낙관은 신규수주·미분해 매출 속도 ×0.8/1.0/1.2. 기존 잔고는 시나리오 간 동일하다. 민감도는 속도 ×0.6~1.4, 기간 ×0.8/1.0/1.2의 유한 격자다. 모두 calibrated=false이며 확률·신뢰수준은 없다. 완전 분해가 안 되면 회사 전체 잔고분/신규분은 null이고 가용 잔고분·신규분·미분해분을 별도로 낸다. FY2026은 관측 H1 + 전망 Q3/Q4다.',
             '유형별 인식 속도는 이번 원장에서도 검증하지 못했다. 1차의 RND 곡선·초도 증속·공급 종료일 인식을 제거하고 모든 부분 계약에 공통 선형 가정을 적용했다. RND/FIRST/FOLLOW/PBL 등 유형·기간 정보는 보존하지만 차등 속도에는 사용하지 않는다. 계약 공시 부분 전망은 회사 매출 전망과 별개이며 더하지 않는다.',
             '한화에어로스페이스 원장에 한화오션·한화시스템·쎄트렉아이 행이 있다. 각각의 독립 회사 수치와 합치지 않는다. 모든 회사에 company_totals_additive=false이고 업종·그룹 합계는 null이다.', '',
             '## 회사별 FY2026~FY2028 — 기준 시나리오', '',
             '| 종목 | 회사 | FY2026 | FY2027 | FY2028 | FY2028 가용 잔고분/전체 | 상태 |',
             '|---|---|---:|---:|---:|---:|---|']
    for f in panel['companies']:
        annual = f['scenarios']['base']['annual']
        share = annual[-1].get('existing_share_of_modelled_future')
        lines.append('| '+ ' | '.join([f['stock'], f['company_name'], *[fmt(a['value']) for a in annual],
                                      f'{share:.1%}' if number(share) else '—', f['status']])+' |')
    lines += ['', '## 방산 잔고가 확인된 블록과 FY+2', '',
              '| 종목 | 범위 | 잔고 | 회전기간 D(분기) | FY2028 기존분 | FY2028 신규분 | 기존 비중 |',
              '|---|---|---:|---:|---:|---:|---:|']
    for f in panel['companies']:
        for b in f['monetary_evidence']['blocks']:
            if not b['backlog_model']: continue
            ps = block_path(b)
            existing, new = sum(x['existing'] for x in ps[6:10]), sum(x['new'] for x in ps[6:10])
            lines.append(f"| {f['stock']} | {b['axis']} | {fmt(b['balance']['value'])} | {b['duration_quarters']:.3f} | {fmt(existing)} | {fmt(new)} | {existing/(existing+new):.1%} |")
    lines += ['', 'Y+2 기존분 우세는 위 블록별 계산 결과로 확인하며 강제하지 않았다. 현대로템 원장의 확인 잔고는 CIVIL 철도행이므로 방산 잔고로 옮기지 않았다. 엠앤씨솔루션의 서로 다른 연도 잔고행은 기납품 대사를 만족하지 않아 소진 모형에서 제외했다.', '',
              '## 백테스트', '',
              f"금액 채점 {bt['monetary']['n']}건, 전체기간이 공시 후에 시작하는 forward-only {bt['forward_only']['n']}건. MAE {fmt(bt['monetary']['MAE'])} 백만원, WAPE {fmt(bt['monetary']['WAPE_pct'])}%. 아래는 기준 시나리오 회사 매출 평가다. 계약별 실제 인식액 채점과 잔고/신규 구성별 채점은 정답이 없어 0건이다.",
              f"잔고 연결 블록을 포함한 회사 매출 표본 {bt['model_slices']['with_backlog_blocks']['n']}건과 매출 속도만 사용한 표본 {bt['model_slices']['sales_run_rate_only']['n']}건을 JSON에서 별도로 집계했다. 이 평가는 잔고/신규 분해의 정확성을 검증하지 않는다.",
              '각 origin에 사용할 역사는 origin 이하로 제한했다. 판단일은 origin 보고서 접수일이다. T+1은 이미 시작된 분기의 nowcast일 수 있어 별도 표본 수로 구분했다. 현재 제공 스냅샷의 사후 정정 여부는 확인할 수 없어 엄밀한 실시간 vintage 백테스트는 아니다. 원장 기납품 차분을 회사 매출 정답으로 사용하지 않았다. 상세 채점 행과 기준/대상 접수번호는 JSON에 보존한다.', '',
              '| 지평 | n | forward n | MAE(백만원) | WAPE % | 지속모형 MAE |',
              '|---|---:|---:|---:|---:|---:|']
    for r in bt['quarterly']:
        lines.append(f"| T+{r['horizon']} | {r['n']} | {r['forward_only']['n']} | {fmt(r['MAE'])} | {fmt(r['WAPE_pct'])} | {fmt(r['persistence']['MAE'])} |")
    for r in bt['annual']:
        lines.append(f"| FY+{r['fy_horizon']} | {r['n']} | 별도 행 참고 | {fmt(r['MAE'])} | {fmt(r['WAPE_pct'])} | {fmt(r['persistence']['MAE'])} |")
    lines += ['', '표본이 없는 지평은 n=0, 오차=null이다. 짧은 자료의 중첩 표본과 계열 중복 때문에 독립 표본으로 볼 수 없으며 FY+2의 보정 성능을 주장하지 않는다.', '',
              '## 회사 전체 보류 사유', '', '| 종목 | 회사 | 사유 코드 |', '|---|---|---|']
    for f in panel['companies']:
        if not f['company_total_available']:
            lines.append(f"| {f['stock']} | {f['company_name']} | {', '.join(f['monetary_evidence']['reason_codes'])} |")
    lines += ['', '## 원문 캡션 차이 — 재환산 없음', '', '| 종목 | 회사 | 분기별 원문 캡션 |', '|---|---|---|']
    for f in panel['companies']:
        caps = f['unit_audit']['quarters']
        if any(any(x not in ('백만원', '') for x in c.get('raw_unit_caption', [])) for c in caps.values()):
            items = '; '.join(q+': '+', '.join(c['raw_unit_caption']) for q,c in caps.items() if c['raw_unit_caption'])
            lines.append(f"| {f['stock']} | {f['company_name']} | {items.replace('|','/')} |")
    lines += ['', '## 재현과 인계', '',
              '```sh', 'python3 output/kdef_forecast.py --input input --output output',
              'python3 -B -m unittest discover -s output -p test_kdef_forecast.py', '```', '',
              '1차 `kdef_forecast.py`의 기간·공시 필터·진행률·민감도·부분 코호트 함수를 이어 사용했고 `forecast_section.py`의 표·이스케이프·SVG 구조를 확장했다. 1차 audit 상태/사유와 입력 해시는 JSON에 보존한다. 모든 신규 파일은 output/에 있다. 생성 엔진은 네트워크를 사용하지 않으며 외부 데이터 수집·배포·정본 편집·외부 패키지·인증 변경은 하지 않았다. 사용자 지정 tracker preflight의 중앙 연결 시도는 central_connection_failed로 끝났으며 재시도·인계 강제 회수 없이 이 작업의 output/만 사용했다. 실행 검증 결과와 재현성은 `validation.json`에 기록한다.', '',
              '남은 검증: 표별 연결/별도 범위, 매출 열·누계 원문, 수주/매출의 동일 부문 대사, 유형별 실제 인식과 신규수주, 긴 시계열·원본 vintage. 이 정보가 없으면 미분해 항목은 null을 유지해야 한다.']
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')


# Round 3 adds evidence and evaluation to the supplied Round 2 implementation.
# The absent audit/unit/needs_longer_ledger JSON files are never fabricated.
REASONS.update({
    'LEDGER_NET_ORDER_PROXY': '동일 범위 인접쌍 잔고증감+분기매출 대용치; 취소·환율 등 조정 미분리',
    'LEDGER_PAIR_SAMPLE_LT4': '동일 범위·단위·접수순서 확인 인접 분기 표본 4개 미만',
    'PRIOR_UNIT_EVIDENCE_FILE_MISSING': '단위 증거 JSON 누락; 2차 보고서의 정규화 계약을 간접 근거로 계승',
    'PRIOR_AUDIT_FILE_MISSING': '2차 감사·needs_longer_ledger 원본 목록 누락; 코드와 보고서로 재심사 대상 재구성',
})


def round2_reference(text):
    """Read tables as data. Nothing from the report is evaluated as code."""
    companies, quarters, annual, captions, blocks = {}, [], [], {}, {}
    section = ''
    for line in text.splitlines():
        if line.startswith('## '):
            section = line
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if '회사별 FY2026' in section and len(cells) == 7 and re.fullmatch(r'\d{6}|\d{4}[A-Z]\d', cells[0]):
            def parsed(x):
                return float(x.replace(',', '')) if re.fullmatch(r'[\d,.]+', x) else None
            companies[cells[0]] = {'stock': cells[0], 'name': cells[1],
                                   'annual': {str(y): parsed(cells[i+2]) for i,y in enumerate((2026,2027,2028))},
                                   'status': cells[6]}
        if section == '## 백테스트' and re.fullmatch(r'T\+\d+|FY\+\d+', cells[0]):
            horizon = int(cells[0].split('+')[1])
            row = {'n': int(cells[1]), 'MAE': parsed(cells[3]), 'WAPE_pct': parsed(cells[4]),
                   'source': 'input/kdef_REPORT.md published rounded table; raw rows unavailable'}
            row['horizon' if cells[0].startswith('T') else 'fy_horizon'] = horizon
            (quarters if cells[0].startswith('T') else annual).append(row)
        if '방산 잔고가 확인된 블록' in section and len(cells) == 7 and re.fullmatch(r'\d{6}', cells[0]):
            blocks.setdefault(cells[0], {})[cells[1]] = {
                'balance': parsed(cells[2]), 'duration_quarters': parsed(cells[3]),
                'source': 'round-2 report block table, rounded'}
        if '원문 캡션 차이' in section and len(cells) == 3 and re.fullmatch(r'\d{6}|\d{4}[A-Z]\d', cells[0]):
            for q, cap in re.findall(r'(20\d\dQ[1-4]):\s*([^;]+)', cells[2]):
                captions.setdefault(cells[0], {})[q] = [s.strip() for s in cap.split(',') if s.strip()]
    if len(companies) != 71 or len(quarters) != 10 or len(annual) != 2:
        raise ValueError('round-2 report comparison tables incomplete')
    return {'companies': companies, 'quarterly': quarters, 'annual': annual, 'captions': captions,
            'backlog_blocks': blocks,
            'published_company_total_count': sum(c['status']=='company_total_conditional' for c in companies.values()),
            'published_backtest_n': sum(r['n'] for r in quarters), 'audit_list_supplied': False}


def inherited_units(reference, prior_text):
    required = ('저장값의 적용 배수는 항상 1', '금액은 백만원', '전역 정규화 계약')
    if not all(x in prior_text for x in required):
        raise ValueError('round-2 report does not document the stored-million unit contract')
    return {'unit_contract': '2차 보고서 기록: 저장 금액은 이미 백만원, 적용 배수 1; 동일 스키마 확장본에도 계승',
            'companies': reference['captions'],
            'evidence_source': 'input/kdef_REPORT.md 단위와 범위 및 원문 캡션 표',
            'original_unit_evidence_json_supplied': False, 'raw_parser_independently_verified': False,
            'extended_quarters_unit_contract_assumed_same': True,
            'new_quarters_raw_captions_available': False}


def shorten_company(company, first='2024Q3'):
    return dict(company, quarters={q: s for q,s in company['quarters'].items() if q >= first})


def annual_value(model, year=2028):
    if not model['available']:
        return None
    return next((r['value'] for r in model['scenarios']['base']['annual'] if r['fiscal_year']==year), None)


def candidate_pair_audits(company, origin=ORIGIN):
    history = sales_history(company, origin)
    decision = receipt_date(history.get(origin, {}).get('receipt'))
    if decision:
        history = {q: r for q,r in history.items()
                   if receipt_date(r.get('receipt')) and receipt_date(r['receipt']) <= decision}
    current = history.get(origin, {})
    snapshot = company['quarters'].get(origin, {})
    axes = current.get('axes')
    candidates = []
    for axis in ('defense', 'civil'):
        if ledger_balance(snapshot, axis):
            candidates.append((axis, axis))
    if ledger_balance(snapshot, 'all'):
        # Preserve v2's sole-unknown-axis linkage; do not infer company scope
        # from arbitrary multiple unknown rows.
        only_unknown = bool(axes and number(axes.get('unknown')) and
                            len([v for v in axes.values() if number(v) and v != 0]) == 1)
        if axes is None or only_unknown:
            candidates.append(('unknown' if only_unknown else 'all', 'all'))
    return [{'axis': axis, 'balance_axis': balance_axis,
             **ledger_order_pairs(company, origin, history, axis, balance_axis)} for axis,balance_axis in candidates]


def reassess_company(f, report, reference):
    short = shorten_company(report)
    short_audits = candidate_pair_audits(short)
    full_audits = candidate_pair_audits(report)
    short_byaxis = {a['axis']: a for a in short_audits}
    blocks = f['monetary_evidence']['blocks']
    modeled = {b['axis'] for b in blocks if b['backlog_model'] and b.get('ledger_order_evidence',{}).get('available')}
    for audit in full_audits:
        old = short_byaxis.get(audit['axis'], {})
        audit['short_window_sample_quarters'] = old.get('sample_quarters', 0)
        audit['threshold_crossed_in_long_window'] = audit['available'] and not old.get('available', False)
        audit['used_in_company_projection'] = audit['axis'] in modeled
    reasons = []
    if not f['company_total_available']:
        reasons.extend(f['monetary_evidence']['reason_codes'])
    for candidate in full_audits:
        if not candidate['available']:
            reasons.extend(candidate['rejection_counts'])
    if not full_audits:
        reasons.append('BACKLOG_SCOPE_UNMATCHED')
    elif not modeled:
        reasons.append('LEDGER_PAIR_SAMPLE_LT4' if not any(a['available'] for a in full_audits)
                       else 'CURRENT_SALES_OR_TURNOVER_UNAVAILABLE')
    fully = bool(blocks) and all(b['axis'] in modeled for b in blocks)
    status = ('eligible_conditional_proxy_full_decomposition' if fully else
              'eligible_conditional_proxy_partial_decomposition' if modeled else
              'eligible_history_but_current_forecast_blocked' if any(a['available'] for a in full_audits) else
              'needs_qualified_pairs' if any(a['sample_quarters']>0 for a in full_audits) else 'blocked_by_scope_or_target')
    new_order = f['evidence']['new_orders']
    prior_company = reference['companies'][f['stock']]
    return {'status': status, 'priority_recheck': prior_company['status'] != 'company_total_conditional' or not new_order['available'],
            'original_needs_longer_ledger_list_available': False,
            'priority_basis': 'prior reported total unavailable or rerun disclosed-award sample <4; not exact absent audit list',
            'reported_quarters': len(report['quarters']),
            'calendar_adjacent_pairs': sum(qadd(q,-1) in report['quarters'] for q in report['quarters']),
            'ledger_proxy_available': bool(modeled), 'full_proxy_decomposition': fully,
            'newly_crossed_4_pair_threshold': any(a['threshold_crossed_in_long_window'] and a['used_in_company_projection'] for a in full_audits),
            'short_window_is_exact_round2_ledger': False, 'short_window_start': '2024Q3',
            'short_window_note': 'controlled eight-quarter truncation of current input; original company-quarter ledger not supplied',
            'ledger_axes': full_audits, 'reason_codes': sorted(set(reasons)),
            'disclosure_orders': {'available': new_order['available'], 'sample_quarters': new_order['sample_quarters'],
                                  'changed_by_extended_report_ledger': False,
                                  'reason': None if new_order['available'] else 'NEW_ORDER_SAMPLE_LT4',
                                  'basis': 'round-2 original-contract award-quarter sampler unchanged; separate from ledger pairs'}}


def comparison_rows(current, previous, horizon_key):
    old = {r[horizon_key]: r for r in previous}
    return [{horizon_key: r[horizon_key], 'round2_n': old.get(r[horizon_key], {}).get('n'),
             'round3_n': r['n'], 'delta_n': r['n']-old[r[horizon_key]]['n'] if r[horizon_key] in old else None,
             'round2_WAPE_pct': old.get(r[horizon_key], {}).get('WAPE_pct'),
             'round3_WAPE_pct': r['WAPE_pct'], 'round3_MAE': r['MAE'],
             'round3_Bias_pct': r['Bias_pct'], 'forward_only': r.get('forward_only'),
             'persistence': r['persistence']} for r in current]


def summary_backtest(bt):
    return {k:v for k,v in bt.items() if k not in ('rows','annual_rows','progress_only')}


def build_panel(input_dir):
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(input_dir.iterdir()) if p.is_file()}
    def read(name): return json.loads((input_dir/name).read_text())
    prior_text = (input_dir/'kdef_REPORT.md').read_text()
    reference = round2_reference(prior_text)
    units = inherited_units(reference, prior_text)
    reports = normalized_inputs(read('kdef_reports.json'), units)
    universe, contracts = read('kdef_universe.json'), read('kdef_contracts.json')['rows']
    ids = [r['stock'] for r in universe['rows']]
    if len(set(ids)) != len(ids) or set(ids) != set(reports['companies']):
        raise ValueError('population mismatch')
    active, retained, excluded = contract_cohorts(contracts)
    forecasts = []
    for u in universe['rows']:
        report = reports['companies'][u['stock']]
        if report['name'] != u['name']:
            raise ValueError('company identity mismatch')
        f = make_company_v2(u, report, active, retained, reference['companies'][u['stock']])
        f['evidence']['contract_exclusions'] = dict(Counter(reason for i,reason in excluded.items() if contracts[i]['stock']==u['stock']))
        f['reason_codes'] = [r for r in f['reason_codes'] if r != 'SHORT_HISTORY']
        f['reason_codes'] += ['PRIOR_UNIT_EVIDENCE_FILE_MISSING', 'PRIOR_AUDIT_FILE_MISSING']
        f['unit_audit'].update(verified_at_origin=False, normalization_contract_inherited=True,
                               independently_verified=False, unit_declared_by_assignment=False,
                               evidence_source=units['evidence_source'])
        f['provenance'].update(report_raw_captions_supplied=False,
                               prior_report_caption_table_partially_available=True,
                               origin_report_filing_date=(receipt_date(report['quarters'].get(ORIGIN,{}).get('rcp')).isoformat()
                               if receipt_date(report['quarters'].get(ORIGIN,{}).get('rcp')) else None))
        f['prior_audit'] = {'status': reference['companies'][u['stock']]['status'], 'reason_codes': None,
                            'original_audit_json_available': False, 'source': 'round-2 report company table'}
        for scenario in f['disclosure_only_scenarios'].values():
            for row in scenario['quarterly']:
                row['reason_codes'] = [r for r in row['reason_codes'] if r != 'SHORT_HISTORY']
        audit = reassess_company(f, report, reference)
        f['needs_longer_ledger_reassessment'] = audit
        f['needs_longer_ledger'] = audit['status'] == 'needs_qualified_pairs'
        if f['needs_longer_ledger']:
            f['reason_codes'].append('LEDGER_PAIR_SAMPLE_LT4')
        f['audit_blockers'] = [REASONS.get(r,r) for r in f['reason_codes']]
        old = reference['companies'][u['stock']]
        new_value = f['scenarios']['base']['annual'][-1]['value']
        old_value = old['annual']['2028']
        long_legacy = monetary_projection(report, order_mode='round2')
        short_legacy = monetary_projection(shorten_company(report), order_mode='round2')
        long_value, short_value = annual_value(long_legacy), annual_value(short_legacy)
        delta = new_value-old_value if number(new_value) and number(old_value) else None
        relative = delta/abs(old_value)*100 if number(delta) and old_value else None
        reasons = []
        if long_value != short_value: reasons.append('extended_history_changes_median_backlog_turnover')
        if new_value != long_value: reasons.append('qualified_adjacent_pair_proxy_replaces_sales_rate_replenishment')
        if f['coverage']['full_existing_coverage'] is False: reasons.append('unmatched_sales_axes_remain_run_rate_only')
        if not f['company_total_available']: reasons.extend(f['monetary_evidence']['reason_codes'])
        f['round2_comparison'] = {
            'prior_status': old['status'], 'current_status': f['status'],
            'new_company_total_available': old['status']!='company_total_conditional' and f['company_total_available'],
            'prior_annual_base': old['annual'], 'current_annual_base': {str(r['fiscal_year']):r['value'] for r in f['scenarios']['base']['annual']},
            'FY2028_delta': delta, 'FY2028_delta_pct': relative,
            'large_change_threshold_pct': 20., 'large_change': number(relative) and abs(relative)>=20.,
            'controlled_short_window_round2_FY2028': short_value, 'controlled_long_window_round2_FY2028': long_value,
            'history_only_FY2028_delta': long_value-short_value if number(long_value) and number(short_value) else None,
            'extended_round2_model_vs_published_FY2028_delta': long_value-old_value if number(long_value) and number(old_value) else None,
            'proxy_rule_FY2028_delta': new_value-long_value if number(new_value) and number(long_value) else None,
            'blocks': [{'axis': b['axis'],
                        'prior_duration_quarters': reference['backlog_blocks'].get(u['stock'],{}).get(b['axis'],{}).get('duration_quarters'),
                        'current_duration_quarters': b['duration_quarters'],
                        'current_duration_observations': len(b['duration_samples']),
                        'round2_sales_rate_order_assumption_on_current_origin': b['quarterly_run_rate'],
                        'current_new_order_assumption': b['new_orders_per_quarter_assumption']}
                       for b in f['monetary_evidence']['blocks'] if b['backlog_model']],
            'reason_codes': reasons, 'exact_prior_reproduction_possible': False,
            'limitation': 'published values rounded to 0.001; original ledger/audit/unit evidence JSON absent'}
        forecasts.append(f)
    bt = money_backtest(reports)
    # Both controls use the same extraction and period rules; never tune them
    # after inspecting target outcomes. The full-ledger v2 control isolates the
    # new-order rule from the longer history. The eight-quarter control is NOT
    # asserted to reproduce the actual, incompletely supplied round-2 input.
    legacy_bt = money_backtest(reports, order_mode='round2')
    identity_keys = lambda rows: [(r['stock'], r['origin'], r.get('target'), r.get('fiscal_year')) for r in rows]
    same_control_samples = (identity_keys(bt['rows']) == identity_keys(legacy_bt['rows']) and
                            identity_keys(bt['annual_rows']) == identity_keys(legacy_bt['annual_rows']))
    if not same_control_samples:
        raise ValueError('model-control score samples differ')
    short_reports = dict(reports, companies={s:shorten_company(c) for s,c in reports['companies'].items()})
    short_bt = money_backtest(short_reports)
    progress, progress_rows = progress_backtest(reports)
    progress['warning'] = '행 진행률 전용·분기말 스냅샷 평가; 회사 매출/수주 대용치 채점과 별개'
    bt['progress_only'] = progress
    bt['contract_recognition'] = {'n':0, 'reason':'no_observed_contract_level_recognition_target'}
    bt['component_recognition'] = {'n':0, 'reason':'no_observed_existing_vs_new_sales_split'}
    bt['new_order_proxy_accuracy'] = {'n':0, 'reason':'no_observed_gross_awards_or_adjustment_reconciliation'}
    for f in forecasts:
        rows = [r for r in bt['rows'] if r['stock']==f['stock']]
        annual_rows = [r for r in bt['annual_rows'] if r['stock']==f['stock']]
        f['backtest'] = {'monetary': metrics(rows, unit='KRW_million'),
                         'forward_only': metrics([r for r in rows if r['forward_only']], unit='KRW_million'),
                         'annual': [{ 'fy_horizon':h, **metrics([r for r in annual_rows if r['fy_horizon']==h], unit='KRW_million')} for h in (0,1,2)],
                         'progress_samples': sum(r['stock']==f['stock'] for r in progress_rows['quarterly']),
                         'contract_recognition_n':0, 'calibrated':False}
    population = {'input_companies':len(ids), 'status_counts':dict(Counter(f['status'] for f in forecasts)),
                  'company_total_forecast_companies':sum(f['company_total_available'] for f in forecasts),
                  'full_decomposition_companies':sum(f['coverage']['full_existing_coverage'] for f in forecasts),
                  'historically_eligible_proxy_companies':sum(any(a['available'] for a in f['needs_longer_ledger_reassessment']['ledger_axes']) for f in forecasts),
                  'ledger_proxy_companies':sum(f['needs_longer_ledger_reassessment']['ledger_proxy_available'] for f in forecasts),
                  'newly_crossed_4_pair_companies':sum(f['needs_longer_ledger_reassessment']['newly_crossed_4_pair_threshold'] for f in forecasts),
                  'new_company_total_available':sum(f['round2_comparison']['new_company_total_available'] for f in forecasts)}
    return {'schema_version':'kdef-3.0', 'origin':ORIGIN, 'money_unit':'KRW_million',
            'input_sha256':hashes, 'engine_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'population':population,
            'ledger_coverage':{'quarters':reports['quarters'], 'calendar_quarter_count':len(reports['quarters']),
                               'company_quarters':sum(len(c['quarters']) for c in reports['companies'].values()),
                               'ok_company_quarters':sum(bool(s.get('ok')) for c in reports['companies'].values() for s in c['quarters'].values()),
                               'max_input_quarters_per_company':max(len(c['quarters']) for c in reports['companies'].values()),
                               'calendar_adjacent_pairs':sum(qadd(q,-1) in c['quarters'] for c in reports['companies'].values() for q in c['quarters'])},
            'unit_evidence':dict(units, company_count=len(units['companies']),
                                 quarter_count=sum(len(q) for q in units['companies'].values()),
                                 stored_value_multiplier_applied=1, no_rescaling=True,
                                 amounts_conditional_on_inherited_normalization_contract=True),
            'round2_reference':reference,
            'round2_comparison':{'quarterly':comparison_rows(bt['quarterly'],reference['quarterly'],'horizon'),
                                  'annual':comparison_rows(bt['annual'],reference['annual'],'fy_horizon'),
                                  'full_ledger_round2_model_control':summary_backtest(legacy_bt),
                                  'eight_quarter_round3_model_control':summary_backtest(short_bt),
                                  'full_ledger_controls_identical_sample_keys':same_control_samples,
                                  'exact_prior_inputs_supplied':False},
            'forecast_quarters':[qadd(ORIGIN,h) for h in range(1,11)], 'fiscal_years':[2026,2027,2028],
            'calibrated':False, 'aggregate_forecast':None, 'group_aggregation_allowed':False,
            'type_speed_evidence':{'verified':False,'type_specific_speed_used':False,
                                  'method':'inherited_common_linear_assumption; contract_types_metadata_only'},
            'reason_dictionary':REASONS, 'backtest':bt, 'companies':forecasts}


def write_report_v3(path, panel):
    pop, bt = panel['population'], panel['backtest']
    companies = panel['companies']
    ref = panel['round2_reference']
    old_n, new_n = ref['published_backtest_n'], bt['monetary']['n']
    crossed = [c['company_name'] for c in companies if c['needs_longer_ledger_reassessment']['newly_crossed_4_pair_threshold']]
    historical_only = [c['company_name'] for c in companies if c['needs_longer_ledger_reassessment']['status']=='eligible_history_but_current_forecast_blocked']
    lines = ['# ARGUS-kdef 3차 — 19분기 원장 재심사', '',
             f"원장은 71사·19개 달력분기(2021Q4~2026Q2), {panel['ledger_coverage']['company_quarters']:,}개 회사분기이며 읽기 성공은 {panel['ledger_coverage']['ok_company_quarters']:,}개다. 회사마다 19분기가 모두 있는 것은 아니다. 회사 전체 조건부 전망 {pop['company_total_forecast_companies']}사, 부분 전망 {pop['status_counts'].get('partial',0)}사, 미추정 {pop['status_counts'].get('unavailable',0)}사로, 2차 대비 새로 회사 전체를 추정하게 된 회사는 {pop['new_company_total_available']}사다.", '',
             f"동일 범위의 인접쌍 4개 기준을 충족하는 이력은 {pop['historically_eligible_proxy_companies']}사에서 확인했고, 현재 회사 전망에 사용할 수 있는 곳은 {pop['ledger_proxy_companies']}사다. 8분기 절단 대조군 대비 4개 기준을 새로 넘어 현재 전망에 반영한 회사는 {', '.join(crossed) or '없음'}이다. {', '.join(historical_only) or '해당 없음'}의 경우 과거 적격 표본을 확보했지만 기준분기 매출 열이 모호해 회사 전체 전망은 여전히 보류한다.", '',
             '## 먼저 확인한 입력 차이와 단위 근거', '',
             '제공 파일은 확장 원장·계약·유니버스 JSON, 2차 코드 3개, 2차 보고서다. 요청에 언급된 2차 감사 JSON·`needs_longer_ledger` 원본 목록·`kdef_unit_evidence.json`·2차 forecast_panel.json은 없다. 따라서 원래 보류 목록의 정확한 복원이나 2차 원장 전체 재현은 할 수 없다. 보고서의 회사별 상태와 기존 코드의 계약 공시 표본 부족 조건으로 우선 대상을 재구성했고 71사 전부를 재심사했다.',
             '제공 2차 코드의 4개 기준은 `order_evidence()`의 최근 8분기 중 원계약 공시 발생 분기 수에만 적용돼 있었다. 보고서 확장으로 계약 공시 표본이 늘었다고 처리하지 않았다. 이 공시 샘플러는 그대로 두고 `ledger_order_pairs()`를 추가해 원장의 인접 분기 대용치를 별도 판정했다. 원전 2차 성적은 이 입력의 KDEF 평가와 서로 다른 표본이므로 합치지 않았다.',
             '금액 단위는 백만원이며 저장값을 재환산하지 않는다. 2차 보고서가 기록한 전역 파서 정규화 계약(저장값 배수 1)을 동일 스키마 확장본에 계승했다. 원래 단위 증거 JSON과 과거 원문 캡션은 제공되지 않아 독립 검증은 불가능하다. 새 과거 분기도 같은 파서 계약을 따른다는 조건부 결과이며 `unit_evidence`에 이 가정을 표시했다. 2차 보고서의 캡션 표에서 실제 읽힌 캡션만 복원했고 빈 캡션은 만들어 넣지 않았다. 외화 잔고는 원화 금액과 합치지 않았다.', '',
             '## 인접쌍 재심사', '',
             '후보는 달력상 정확히 인접한 두 분기다. 양쪽 보고서의 접수순서·기준 보고서 접수일 이전 가용성, 동일 통화·정규화 계약·원장 형태·orders_scope, 같은 매출 축의 존재, 잔고 행 대사, 비음수 분기 매출을 확인했다. 연중 분기 매출은 당기 누계−직전 분기 누계, Q1은 당기 누계다. 분기 누락을 건너뛰거나 누락값을 0으로 채우지 않는다.',
             '`O_proxy(t)=B(t)−B(t−1)+Sales(t)`는 취소·환율·사업범위 이동 등이 없다는 가정 아래의 순증 대용치다. 실측 신규수주·총수주가 아니다. 음수 대용치는 탈락 근거에 원값을 보존하고 0으로 바꾸지 않는다. 비음수 표본 선택에 따른 상향 편향 가능성도 기록한다. 동일 태그의 부문 잔고 또는 단일 전체 잔고의 집계 범위를 가정하며 계약 행의 추가·종료는 허용하지만, 개별 계약을 같은 행으로 억지 연결하지 않는다. 부문 구성·범위의 원문 검증은 남아 있다.',
             '아래의 “8분기”는 현재 확장본을 2024Q3 이후로 자른 통제 비교다. 2차 당시 실제 회사별 원장 길이는 서로 달랐으며 원본이 없어 이 숫자를 당시 실측 표본으로 부르지 않는다. 회사 내 축별 관측 수도 서로 합치지 않는다.', '',
             '| 회사 | 축 | 달력 인접쌍 | 8분기 적격 | 확장 적격 | 현재 적용 | 남은 탈락 원인 |',
             '|---|---|---:|---:|---:|---|---|']
    for c in companies:
        a = c['needs_longer_ledger_reassessment']
        for x in a['ledger_axes']:
            exclusions = ', '.join(f'{k}:{v}' for k,v in x['rejection_counts'].items()) or '없음'
            lines.append(f"| {c['company_name']} ({c['stock']}) | {x['axis']} | {x['candidate_pairs']} | {x['short_window_sample_quarters']} | {x['sample_quarters']} | {'사용' if x['used_in_company_projection'] else '보류'} | {exclusions} |")
    lines += ['', '## 전망 방식과 분해', '',
              '2차의 분기 함수, 누계 매출 추출, 공시 필터, 선형 잔고 소진, 시나리오·민감도·HTML 구조를 이어 썼다. 매출·범위 판정 규칙을 바꿔 표본을 늘리지 않았다. 잔고 회전기간 D는 기준일까지의 같은 범위 잔고/(연초 누계 매출/경과 분기)의 중앙값으로 다시 계산한다. 실제 인도기간이나 유형별 인식 속도는 아니다.',
              '잔고분은 B0×[clip(h/D)−clip((h−1)/D)]. 적격 인접쌍이 4개 이상인 블록의 신규분은 대용치 P25/P50/P75를 각각 보수/기준/낙관 분기 말 코호트로 넣어 같은 D에 걸쳐 인식한다. 당분기 발생 코호트의 당분기 인식은 0이다. 적격 미달 블록은 2차의 매출 속도×0.8/1.0/1.2 가정으로 남기며, 실증 신규수주로 승격하지 않는다. 잔고 범위를 연결하지 못한 매출도 같은 계수의 미분해 매출로 분리한다.',
              '민감도는 대용치 P10/P90(대용치 미적격·미분해는 속도×0.6~1.4)와 D×0.8/1.0/1.2를 조합한 유한 격자다. JSON에 전체 및 가용 잔고·신규·미분해 구성별 범위를 저장했다. 모두 `calibrated=false`, `nominal_level=null`이다. 표본 수가 늘어도 신뢰구간으로 바꾸지 않았다.',
              '분기 2026Q3~2028Q4는 시나리오별 10개, FY2026~FY2028은 3개다. FY2026=관측 H1+미래 Q3/Q4이고 연간 잔고/신규 분해는 미래분만 가리킨다. 모든 축을 분해하지 못하면 회사 전체 잔고분·신규분은 null이며 가용 구성과 미분해를 별도 저장한다. 회사 전체 미추정 행에도 기간·시나리오·null을 보존한다. 공시 계약의 부분 전망과 정확한 납기 잔고의 별도 소진표를 회사 전체에 더하지 않는다.',
              '연결/별도 범위와 12월 결산·연초누계 해석은 조건부다. 미분류를 방산으로 바꾸지 않았다. 현대로템의 가용 원장은 CIVIL 철도행이고 방산 매출 축과 합쳐 방산 수주로 표현하지 않는다. 한화 계열 등을 포함한 모든 회사 간 합산은 금지되어 `aggregate_forecast=null`, `company_totals_additive=false`를 유지한다.', '',
              '## 2차 대비 회사별 변화', '',
              '| 회사 | 2차 FY2028 | 3차 FY2028 | 변동 % | 긴 원장+2차 모형 | 신규 대용치 규칙 효과 | 이유 |',
              '|---|---:|---:|---:|---:|---:|---|']
    changed = [c for c in companies if number(c['round2_comparison']['FY2028_delta']) and abs(c['round2_comparison']['FY2028_delta'])>.01]
    for c in sorted(changed, key=lambda c:abs(c['round2_comparison']['FY2028_delta_pct'] or 0), reverse=True):
        d = c['round2_comparison']
        lines.append(f"| {c['company_name']} | {fmt(d['prior_annual_base']['2028'])} | {fmt(d['current_annual_base']['2028'])} | {fmt(d['FY2028_delta_pct'])} | {fmt(d['controlled_long_window_round2_FY2028'])} | {fmt(d['proxy_rule_FY2028_delta'])} | 기간 중앙값 재계산·신규 대용치 반영 |")
    lines += ['', '| 회사·축 | 2차 기간 D | 3차 기간 D | 3차 기간 표본 | 종전 매출 속도 가정 | 3차 신규 대용치/가정 |',
              '|---|---:|---:|---:|---:|---:|']
    for c in companies:
        for b in c['round2_comparison']['blocks']:
            lines.append(f"| {c['company_name']} · {b['axis']} | {fmt(b['prior_duration_quarters'])} | {fmt(b['current_duration_quarters'])} | {b['current_duration_observations']} | {fmt(b['round2_sales_rate_order_assumption_on_current_origin'])} | {fmt(b['current_new_order_assumption'])} |")
    lines += ['', '큰 변화의 기준은 FY2028 절대 변동률 20%다. 퍼스텍은 이를 넘고, 한국항공우주도 약 19% 변동해 위에 함께 표시했다. “긴 원장+2차 모형”은 같은 현재 원장에서 신규수주를 예전의 매출 속도 가정으로 계산한 통제값이다. 이 값과 3차 차이는 신규 대용치 규칙 효과이고, 2차 발표값과 통제값 차이는 입력 이력 차이까지 포함한다. 원래 회사별 2차 원장이 없어 모든 차이를 순수한 모형 개선이라고 단정할 수 없다. 회사별 JSON에는 현재 8분기 절단 통제값도 저장했다.', '',
              '## 지평별·연간 백테스트와 표본 증가', '',
              f"분기 금액 채점은 {old_n:,}→{new_n:,}건(+{new_n-old_n:,}, {new_n/old_n:.2f}배)이다. 2차 발표 전체 WAPE 18.728%에 비해 이번 WAPE는 {bt['monetary']['WAPE_pct']:.3f}%로 나빠졌다. MAE는 {fmt(bt['monetary']['MAE'])}백만원, Bias는 {fmt(bt['monetary']['Bias_pct'])}%다. 표본 구성·지평·이력이 달라 전체 WAPE 차이를 같은 표본의 성능 변화라고 해석할 수 없다.",
              '기준은 원장 분기말이 아니라 기준 보고서 접수일이다. 매출표를 누계로 읽고 분기 차분으로 채점하며 기납품 차분을 정답으로 쓰지 않는다. 학습·회전기간·수주 표본은 기준분기 이하이면서 기준 접수일에 가용한 것만 사용한다. T+1은 이미 시작된 분기의 nowcast이므로 미래 분기 전체가 판단일 이후인 forward-only를 따로 집계한다. 원본 vintage가 없어 제공 스냅샷의 사후 정정은 통제하지 못한다.',
              '연간은 Q1~Q4의 유효 분기 정답과 접수순서를 모두 확인한다. FY+0은 보고서의 관측 누계에 남은 분기 전망을 더하되 Q4처럼 이미 끝난 연간은 채점하지 않는다. FY+1·FY+2는 완전한 미래 연도만 채점하며, 10분기 예측창에 해당 연도 4분기가 전부 들어오지 않으면 제외한다. FY+2의 Q1 기준점은 이 예측창을 넘는다. 제외 사유별 건수는 JSON에 보존한다. 계약별 인식·잔고/신규 구성·신규수주 자체의 정확도는 독립 정답이 없어 각각 0건이다.', '',
              '| 지평 | 2차 n | 3차 n | 증가 | 2차 WAPE % | 3차 WAPE % | 3차 MAE | Bias % | forward n | 지속모형 WAPE % |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for kind, key in [('quarterly','horizon'),('annual','fy_horizon')]:
        for r in panel['round2_comparison'][kind]:
            label = ('T+' if kind=='quarterly' else 'FY+')+str(r[key])
            old_count = str(r['round2_n']) if r['round2_n'] is not None else '미제공'
            delta = str(r['delta_n']) if r['delta_n'] is not None else '비교 불가'
            lines.append(f"| {label} | {old_count} | {r['round3_n']} | {delta} | {fmt(r['round2_WAPE_pct'])} | {fmt(r['round3_WAPE_pct'])} | {fmt(r['round3_MAE'])} | {fmt(r['round3_Bias_pct'])} | {r['forward_only']['n']} | {fmt(r['persistence']['WAPE_pct'])} |")
    legacy = panel['round2_comparison']['full_ledger_round2_model_control']['monetary']
    short = panel['round2_comparison']['eight_quarter_round3_model_control']['monetary']
    lines += ['', f"동일 긴 원장·동일 {legacy['n']:,}개 표본에서 2차 규칙의 WAPE는 {legacy['WAPE_pct']:.3f}%, 3차 규칙은 {bt['monetary']['WAPE_pct']:.3f}%다. 신규 대용치 규칙이 이 평가에서 개선됐다고 주장하지 않는다. 현재 입력을 8분기로 절단한 3차 통제군은 {short['n']:,}건·WAPE {short['WAPE_pct']:.3f}%이며, 2차 발표 표본을 정확히 재현한 결과는 아니다.",
              f"완전히 미래인 분기 표본은 {bt['forward_only']['n']:,}건, WAPE {fmt(bt['forward_only']['WAPE_pct'])}%다. 각 채점 행의 origin/target·접수번호·예측·정답·분기 누계 근거와 연간 구성은 forecast_panel.json에 있다. 겹치는 origin 및 계열 회사 표본은 독립이 아니다. WAPE의 오차 가중 집계는 업종·그룹 매출 합산 전망이 아니다. 작은 표본·낮은 실제 매출에서는 비율 오차가 커질 수 있다.", '',
              '| 회사별 높은 WAPE 사례 | n | MAE | WAPE % | Bias % |', '|---|---:|---:|---:|---:|']
    worst = sorted([c for c in companies if number(c['backtest']['monetary']['WAPE_pct'])],
                   key=lambda c:c['backtest']['monetary']['WAPE_pct'], reverse=True)[:10]
    for c in worst:
        r=c['backtest']['monetary']
        lines.append(f"| {c['company_name']} | {r['n']} | {fmt(r['MAE'])} | {fmt(r['WAPE_pct'])} | {fmt(r['Bias_pct'])} |")
    lines += ['', '## 71사 전수 결과 — 기준 시나리오', '',
              '| 종목 | 회사 | FY2026 | FY2027 | FY2028 | 상태 | 재심사 판정 | 잔여 사유 |',
              '|---|---|---:|---:|---:|---|---|---|']
    for c in companies:
        a=c['needs_longer_ledger_reassessment']
        reason='; '.join(a['reason_codes']) or ('일부 매출 축 잔고 미연결' if not a['full_proxy_decomposition'] else '표본 문턱 충족; 조정·범위 원문 미검증')
        lines.append('| '+' | '.join([c['stock'],c['company_name'],*[fmt(r['value']) for r in c['scenarios']['base']['annual']],c['status'],a['status'],reason])+' |')
    lines += ['', '## 재현·검증·남은 불확실성', '',
              '```sh', 'python3 -B output/kdef_forecast.py --input input --output output',
              'python3 -B -m unittest discover -s output -p test_kdef_forecast.py', '```', '',
              '산출물은 forecast_panel.json, kdef_REPORT.md, forecast_section.py, kdef_forecast.py, test_kdef_forecast.py다. forecast_section.py는 기존 HTML/SVG 렌더러를 이어 쓰며 원장 대용치 표본·남은 사유·회사 변화도 표시한다. 기본 실행은 개별 HTML 파일을 추가 생성하지 않는다. 입력 SHA-256과 엔진 해시를 패널에 저장하고 실행 테스트·입력 불변성·재생성 일치는 validation.json에 기록한다.',
              '남은 불확실성은 새 과거 분기의 원문 단위·매출 누계·동일 연결/별도 범위, 잔고 조정 항목, 공시 원본 vintage, 유형별 실제 인식·수주 정답이다. 회전기간과 신규수주 표본이 길어졌어도 이 항목들은 자동 해결되지 않는다. 누락값·미해결 축은 null 또는 명시한 미분해/조건부 가정으로 유지한다.',
              '작업은 배정된 output/에만 저장했다. 사용자 지정 tracker preflight는 central_connection_failed였으며 재시도·인계 강제 회수·정본 수정·외부 데이터 수집·배포·인증 변경을 하지 않았다. task_claim.json에 현재 세션의 산출물 범위를 기록했다.']
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Offline KDEF round-3 continuation; standard library only')
    parser.add_argument('--input', type=Path, default=Path(__file__).resolve().parents[1]/'input')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    if args.output.resolve()==args.input.resolve() or args.input.resolve() in args.output.resolve().parents:
        parser.error('output must not overwrite input')
    args.output.mkdir(parents=True,exist_ok=True)
    panel=build_panel(args.input)
    write_json(args.output/'forecast_panel.json',panel)
    write_report_v3(args.output/'kdef_REPORT.md',panel)
    print(json.dumps({'population':panel['population'],'monetary_backtest':panel['backtest']['monetary'],
                      'annual_backtest':[{'fy_horizon':r['fy_horizon'],'n':r['n'],'WAPE_pct':r['WAPE_pct']} for r in panel['backtest']['annual']]},ensure_ascii=False))


if __name__=='__main__':
    main()
