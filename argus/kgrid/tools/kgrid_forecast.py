#!/usr/bin/env python3
"""Offline KGRID ledger audit/forecast. Python standard library only.

python3 -B output/kgrid_forecast.py --input-dir input --output-dir output
Amounts fail closed unless the supplied text proves the table's normalization.
Dimensionless forecasts are an explicit, separate extension to the KCE skeleton.
No construction-engine import, network, credential or canonical-file writes.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import calendar
import copy
import hashlib
import html
import json
import math
import re
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

SCENARIOS = {'conservative': .25, 'base': .50, 'optimistic': .75}
YEARS = (2026, 2027, 2028)
REASONS = {
    'needs_longer_ledger': '원장 기간/적격 표본 부족: 19분기 원장 도착 후 재실행',
    'unit_history_unverified': '적합에 쓰는 과거 분기의 단위 계약/캡션 연결이 없음',
    'negative_order_quantile': '음수 순수주 분위는 신규 코호트 모형에서 지원하지 않음',
    'holding_excluded': '지주·자회사 재공시: 독립 합산·추정 제외',
    'missing_origin': '기준 분기의 원장 없음',
    'missing_backlog': '본체 수주잔고 없음',
    'unit_unrecognized': '수주표 금액 단위 인식 실패',
    'scale_unverified': '본체 수주표의 원단위→저장값 배율 근거 미제공: 금액 미추정',
    'currency_mismatch': '잔고·연매출 통화 불일치: 환산·배수·모델 분기 보류',
    'coverage_unknown': '유효한 직전 연매출 대비 잔고배수 없음: 장납기/회전 미상',
    'aggregate_contamination': '날짜/라벨 칸의 합계행이 낱행에 혼입됨',
    'declared_total_mismatch': '입력이 총계 불일치를 표시함',
    'scope_non_grid': '수주표가 연소기·엔진프레임·PVD 등 비전력기기 범위임',
    'delivery_basis_unknown': '기납품액의 당기누계/계약누계 구분 근거 부족',
    'flow_history_short': '같은 범위의 적격 분기 소진 표본 2개 미만',
    'new_order_history_short': '신규수주/순수주 적격 표본 4개 미만',
    'schedule_partial': '일부 납기만 유효: 전체 잔고 소진분 미추정',
    'schedule_unknown': '납기가 없거나 주석·연간단가·열린 기간·복수계약 대표일임',
    'overdue_positive_backlog': '양수 잔고의 납기가 기준일 이전/당일: 자동 이연 금지',
    'scope_changed': '표 주체 또는 부문 집합 변경: 차분 제외',
    'negative_delivery_delta': '음수 기납품 차분: 원장에 보존하고 적합·정답에서 제외',
    'missing_observed_calendar_quarter': '연간 합계에 필요한 과거 분기 원장 흐름 없음',
    'ratio_only': '금액 대신 기준 잔고 대비 비율만 추정',
    'no_model_evidence': '금액·비율 추정을 지지할 흐름/일정 근거 없음',
}


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def total(xs):
    xs = list(xs)
    return sum(xs) if all(number(x) for x in xs) else None


def quantile(xs, p):
    xs = sorted(x for x in xs if number(x))
    if not xs:
        return None
    i = (len(xs) - 1) * p
    lo, hi = math.floor(i), math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def qnum(q):
    if not re.fullmatch(r'\d{4}Q[1-4]', q):
        raise ValueError('invalid quarter: ' + str(q))
    return int(q[:4]) * 4 + int(q[-1]) - 1


def qadd(q, n):
    y, k = divmod(qnum(q) + n, 4)
    return f'{y}Q{k+1}'


def qend(q):
    m = int(q[-1]) * 3
    y = int(q[:4])
    return date(y, m, calendar.monthrange(y, m)[1])


def clean(s):
    return re.sub(r'\s+', '', html.unescape(str(s or '')))


def is_total(s):
    return clean(s).strip('|·') in {'계', '소계', '합계', '총계', '총합계', '단순합계'}


def aggregate_row(row):
    # The input parser examined labels only. Kwangmyung stores its total in dates.
    return any(is_total(row.get(k)) for k in ('label', 'seg', 'item', 'order_date', 'due'))


def due_date(s):
    """An exact date or closed range's last date. No '등', footnotes, ditto, open ranges."""
    s = html.unescape(str(s or '')).strip()
    if not s or any(t in s for t in ('등', '단가', '단간', '주)', '(*', '분납', '"')):
        return None
    if s.endswith(('~', '부터')):
        return None
    found = re.findall(r"(?<!\d)(\d{4}|\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})(?:일)?", s)
    if not found:
        return None
    y, m, d = map(int, found[-1])
    if y < 100:
        y += 2000
    try:
        return date(y, m, d)
    except ValueError:
        return None


def quotes(snapshot):
    return sorted(set(html.unescape(t) for d in snapshot.get('demand', {}).values()
                      for t in d.get('quotes', [])))


def scale_proof(snapshot):
    """Accept a same-row G/D/B triplet in an explicit KRW caption, never another entity.

    This can prove a single row's scale, not all monetary columns in the report.
    The present input proves Jeryong Industrial's HVDC row in three quarters.
    A subsidiary caption and a customer-sales caption cannot prove the main backlog.
    """
    proofs = []
    if snapshot.get('unit_seen') is not True or snapshot.get('cur') != 'KRW':
        return proofs
    units = [('천원', .001), ('백만원', 1.0), ('억원', 100.0), ('원', .000001)]
    for text in quotes(snapshot):
        if '수주현황' not in text or '수주총액' not in text or '기납품액' not in text or '수주잔고' not in text:
            continue
        caption = re.search(r'단위\s*:\s*(천원|백만원|억원|원)\s*\)', text)
        if not caption:
            continue
        raw_unit = caption.group(1)
        to_million = dict(units)[raw_unit]
        for i, row in enumerate(snapshot.get('segments', [])):
            if aggregate_row(row) or not all(number(row.get(k)) for k in ('gross', 'delivered', 'closing')):
                continue
            # Match label before the three numbers; don't infer scale from magnitudes.
            label = row.get('label', '')
            if not label or clean(label) not in clean(text):
                continue
            a, b, c = [row[k] / to_million for k in ('gross', 'delivered', 'closing')]
            tokens = [f'{v:,.0f}' if math.isclose(v, round(v), abs_tol=.001) else '' for v in (a, b, c)]
            if all(tokens) and re.search(r'\s*-?\s*'.join(map(re.escape, tokens)), text):
                proofs.append({'row_index': i, 'label': label, 'money_unit': 'KRW_million',
                               'raw_unit': raw_unit, 'scale_from_input': 1,
                               'raw_to_million': to_million, 'quote': text,
                               'basis': 'same_row_caption_and_gross_delivered_closing_triplet'})
    return proofs


def unit_proof(snapshot):
    """A supplied normalization contract is evidence, not executable instructions.

    Captions are report-level candidates, not an independently reconstructed table
    mapping. Accept the explicit parser contract plus the original unit_seen flag;
    never multiply already-normalized values a second time or convert FX to KRW.
    """
    attached = snapshot.get('_unit_evidence', {})
    cur = snapshot.get('cur')
    recognized = []
    for caption in attached.get('captions', []):
        if not isinstance(caption, str):
            continue
        if cur == 'KRW' and re.search(r'십억원|백만원|억원|천원|만원|(?<![가-힣])원(?![가-힣])', caption):
            recognized.append(caption)
        elif cur in ('USD', 'EUR') and cur in caption:
            recognized.append(caption)
    verified = bool(attached.get('contract_valid') and recognized and snapshot.get('unit_seen') is True)
    return {'verified': verified, 'normalization_contract_received': attached.get('contract_valid') is True,
            'basis': 'supplied_parser_normalization_contract_and_quarter_caption_candidates',
            'currency': cur, 'money_unit': cur+'_million' if verified else None,
            'scale_from_stored_value': 1 if verified else None,
            'caption_candidates': attached.get('captions', []), 'recognized_candidates': recognized,
            'json_pointer': attached.get('json_pointer'), 'contract': attached.get('contract'),
            'caption_to_primary_table_independently_reconstructed': False,
            'raw_tables_available': False, 'normalizer_source_available': False}


def attach_evidence(reports, units, probes):
    reports = copy.deepcopy(reports)
    contract = units.get('unit_contract', '')
    valid = all(t in contract for t in ('백만원', '_UNIT_SCALE', '0.001', '1e-6'))
    for code, co in reports['companies'].items():
        for q, x in co['quarters'].items():
            x['_unit_evidence'] = {'contract_valid': valid, 'contract': contract,
                'captions': units.get('companies', {}).get(code, {}).get(q, []),
                'json_pointer': '/companies/'+code+'/'+q}
        probe = probes.get('rows', {}).get(code)
        if probe and probe.get('stock') == code and probe.get('name') == co['name']:
            co['_probe'] = copy.deepcopy(probe)
    return reports


def table_snapshot(co, q):
    x = co.get('quarters', {}).get(q)
    if not x or x.get('ok') is not True:
        return {'quarter': q, 'valid': False, 'reasons': ['missing_origin']}
    rows = x.get('segments', [])
    issues = []
    if any(aggregate_row(r) for r in rows):
        issues.append('aggregate_contamination')
    if x.get('total_mismatch'):
        issues.append('declared_total_mismatch')
    if not number(x.get('backlog')):
        issues.append('missing_backlog')
    if x.get('unit_seen') is not True or x.get('cur') not in ('KRW', 'USD', 'EUR'):
        issues.append('unit_unrecognized')
    if '_unit_evidence' in x and x.get('unit_seen') is True and not unit_proof(x)['verified']:
        issues.append('unit_history_unverified')
    nongrid = any(re.search(r'연소기|엔진프레임|PVD', r.get('label', ''), re.I) for r in rows)
    if nongrid:
        issues.append('scope_non_grid')
    selected = [r for r in rows if r.get('kind') == 'grid'] if x.get('shape') == 'roll' else rows
    subset = x.get('shape') == 'roll' and len(selected) != len(rows)
    if subset and not selected:
        issues.append('scope_non_grid')
    out = {'quarter': q, 'valid': not issues, 'reasons': sorted(set(issues)), 'raw': x,
           'B': total(r.get('closing') for r in selected) if subset else x.get('backlog'),
           'D': total(r.get('delivered') for r in selected) if subset else x.get('delivered'),
           'O': total(r.get('new') for r in selected) if subset else x.get('new'),
           'opening': total(r.get('opening') for r in selected) if subset else x.get('opening'),
           'cur': x.get('cur'), 'shape': x.get('shape'), 'subset': subset,
           'scope': 'grid_segments_in_primary_table' if subset else 'primary_orders_table',
           'selected_labels': [r.get('label') for r in selected], 'rows': selected}
    # Broad segment names stay stable when item wording changes. Project grids aren't flow-fit.
    out['scope_key'] = (out['cur'], x.get('entity', ''), out['scope'],
                        tuple(sorted(set(clean(r.get('seg')) for r in selected))))
    return out


def current_revenue(x):
    totals = [r.get('val') for r in x.get('revenue_segments', [])
              if is_total(r.get('seg')) and is_total(r.get('kind'))]
    if totals:
        return totals[-1]
    rs = x.get('revenue_segments', [])
    # Single department aggregate is unambiguous; never add domestic/export plus totals.
    combined = [r.get('val') for r in rs if is_total(r.get('kind'))]
    if len(combined) == 1:
        return combined[0]
    return None


def evidence(co, origin):
    history = {q: table_snapshot(co, q) for q in sorted(co.get('quarters', {}), key=qnum)
               if qnum(q) <= qnum(origin)}
    current = history.get(origin, {'valid': False, 'reasons': ['missing_origin']})
    # Corroboration uses only information available by this origin and within the year.
    ytd_years = set()
    ytd_proofs = []
    for q, s in history.items():
        if not s['valid'] or s['subset']:
            continue
        rev = current_revenue(s['raw'])
        if (number(rev) and rev > 0 and number(s['D']) and
                s['cur'] == s['raw'].get('revenue_cur') and abs(s['D']-rev) <= max(1, rev*.015)):
            ytd_years.add(q[:4])
            ytd_proofs.append({'quarter': q, 'delivered': s['D'], 'current_revenue': rev,
                               'relative_difference': (s['D']-rev)/rev,
                               'basis': 'parsed_current_sales_corroboration_not_raw_header_verification'})
    flow, orders, rates, rejected = [], [], [], []
    for q, s in history.items():
        if not s['valid'] or not number(s.get('D')):
            continue
        is_ytd = s['shape'] == 'roll' or (not s['subset'] and q[:4] in ytd_years)
        if not is_ytd:
            continue
        prev = history.get(qadd(q, -1))
        same = prev and prev['valid'] and prev.get('scope_key') == s['scope_key']
        if q.endswith('Q1'):
            d, o = s['D'], s.get('O')
        elif same and number(prev.get('D')):
            d = s['D'] - prev['D']
            o = s['O'] - prev['O'] if number(s.get('O')) and number(prev.get('O')) else None
        else:
            rejected.append({'quarter': q, 'reason': 'scope_changed' if prev else 'missing_previous_quarter'})
            continue
        if d < 0:
            rejected.append({'quarter': q, 'value': d, 'reason': 'negative_delivery_delta'})
            continue
        flow.append({'quarter': q, 'value': d, 'basis': 'YTD_reset_Q1_else_same_year_difference',
                     'scope_key': s['scope_key']})
        if same and number(prev.get('B')) and prev['B'] > 0:
            rates.append({'quarter': q, 'B_previous': prev['B'], 'delivery': d,
                          'ratio': d/prev['B'], 'scope_key': s['scope_key']})
            if number(o):
                order = o
                route = 'reported_YTD_new_order_difference'
            else:
                order = s['B'] - prev['B'] + d
                route = 'backlog_delta_plus_YTD_delivery_proxy'
            orders.append({'quarter': q, 'value': order, 'route': route,
                           'backlog_delta': s['B']-prev['B'], 'delivery': d,
                           'reconciliation_residual': s['B']-prev['B']-order+d,
                           'scope_key': s['scope_key']})
        elif number(o) and s['shape'] == 'roll':
            orders.append({'quarter': q, 'value': o, 'route': 'reported_YTD_new_order_Q1',
                           'reconciliation_residual': s['B']-s['opening']-o+d
                           if number(s.get('opening')) else None, 'scope_key': s['scope_key']})
    if current.get('scope_key'):
        rates = [r for r in rates if r['scope_key'] == current['scope_key']][-8:]
        orders = [r for r in orders if r['scope_key'] == current['scope_key']][-8:]
        flow = [r for r in flow if r['scope_key'] == current['scope_key']]
    raw = current.get('raw', {})
    coverage = raw.get('coverage_years')
    coverage_basis = 'provided_backlog_div_previous_fiscal_revenue'
    if current.get('subset'):
        prior = history.get(str(int(origin[:4])-1)+'Q4')
        if (prior and prior['valid'] and prior.get('scope_key') == current.get('scope_key')
                and number(prior.get('D')) and prior['D'] > 0):
            coverage = current['B']/prior['D']
            coverage_basis = 'selected_grid_backlog_div_selected_previous_FY_delivery_proxy'
        else:
            coverage = None
            coverage_basis = 'selected_grid_previous_FY_delivery_missing'
    if not current.get('subset') and raw.get('cur') != raw.get('revenue_cur'):
        coverage = None
    branch = ('long_lead' if coverage >= 1 else 'turnover') if number(coverage) and coverage > 0 else None
    durs = [1/r['ratio'] for r in rates if r['ratio'] > 0]
    duration = quantile(durs, .5) if len(durs) >= 2 else None
    # Stock/delivery turnover is an empirical intensity proxy, never a factory lead-time claim.
    if number(duration):
        duration = max(1.0, duration)
    return {'history': history, 'current': current, 'orders': orders, 'flows': flow,
            'rates': rates, 'rejected': rejected, 'ytd_proofs': ytd_proofs,
            'coverage_years': coverage, 'coverage_basis': coverage_basis, 'branch': branch,
            'duration': duration, 'raw_scale_basis': 'same_normalized_scale_within_supplied_series_assumed',
            'negative_order_n': sum(r['value'] < 0 for r in orders)}


def interval(lo=None, hi=None, method='explicit_parameter_grid_sensitivity'):
    return {'lower': lo, 'upper': hi, 'method': method, 'nominal_level': None, 'calibrated': False}


def cdf(t, duration):
    return min(1.0, max(0.0, t/duration))


def model_path(branch, duration, order, n=10):
    """Origin backlog = 1. Long lead: geometric pool + next-quarter uniform cohorts.
    Turnover: finite stock liquidation + same-quarter uniform order cohorts.
    Unknown orders propagate null, including the first long-lead quarter.
    """
    rows = []
    for h in range(1, n+1):
        if branch == 'long_lead':
            r = min(1.0, 1/duration)
            e = r*(1-r)**(h-1)
            remaining = (1-r)**h
            offset = 0
        else:
            e = cdf(h, duration)-cdf(h-1, duration)
            remaining = 1-cdf(h, duration)
            offset = 1
        if number(order):
            new = sum(order*(cdf(h-j+offset, duration)-cdf(h-j-1+offset, duration))
                      for j in range(1, h+1))
            new_backlog = sum(order*(1-cdf(h-j+offset, duration)) for j in range(1, h+1))
        else:
            new = new_backlog = None
        rows.append({'existing_backlog_revenue': e, 'new_order_revenue': new,
                     'value': total((e, new)), 'new_orders': order,
                     'new_order_backlog': new_backlog, 'remaining_existing_backlog': remaining})
    return rows


def annualize(qs, observed, origin, reason_codes):
    lookup = {r['quarter']: r for r in qs}
    result = []
    for year in YEARS:
        allqs = [f'{year}Q{k}' for k in range(1, 5)]
        past = [q for q in allqs if qnum(q) <= qnum(origin)]
        future = [q for q in allqs if qnum(q) > qnum(origin)]
        rows = [lookup.get(q, {}) for q in future]
        obs = total(observed.get(q) for q in past)
        v = total([obs]+[r.get('value') for r in rows])
        y = {'fiscal_year': year, 'value': v,
             'existing_backlog_revenue': total(r.get('existing_backlog_revenue') for r in rows),
             'covered_sites_partial_revenue': total(r.get('covered_sites_partial_revenue') for r in rows),
             'new_order_revenue': total(r.get('new_order_revenue') for r in rows),
             'observed_revenue': obs, 'observed_revenue_basis': 'same_scope_YTD_delivery_proxy',
             'observed_quarters_available': sum(number(observed.get(q)) for q in past),
             'observed_quarters_required': len(past), 'future_quarters': len(future),
             'complete': number(v), 'quarters': allqs,
             'component_scope': 'future_quarters_only; observed_current_year_separate',
             'reason': None if number(v) else ';'.join(sorted(set(reason_codes +
                 (['missing_observed_calendar_quarter'] if obs is None else [])))),
             'reason_codes': [] if number(v) else sorted(set(reason_codes +
                 (['missing_observed_calendar_quarter'] if obs is None else [])))}
        for k in ('interval', 'partial_existing_interval', 'covered_sites_partial_interval'):
            lo = total(r.get(k, {}).get('lower') for r in rows)
            hi = total(r.get(k, {}).get('upper') for r in rows)
            if k == 'interval':
                lo, hi = total((obs, lo)), total((obs, hi))
            y[k] = interval(lo, hi, 'sum_of_quarter_sensitivity_bounds')
        result.append(y)
    return result


def scheduled_path(ev, n=10, monetary=False):
    current = ev['current']
    raw = current.get('raw', {})
    if not current.get('valid') or not ev['branch'] or not number(current.get('B')) or current['B'] <= 0:
        return None
    proof_ids = {p['row_index'] for p in scale_proof(raw)}
    if unit_proof(raw)['verified'] and raw.get('cur') == 'KRW':
        proof_ids = set(range(len(raw.get('segments', []))))
    eligible, excluded = [], []
    origin = current['quarter']
    for idx, row in enumerate(raw.get('segments', [])):
        if monetary and idx not in proof_ids:
            excluded.append({'row_index': idx, 'reason': 'scale_unverified'})
            continue
        b = row.get('closing')
        due = due_date(row.get('due'))
        if not number(b) or b < 0:
            excluded.append({'row_index': idx, 'reason': 'missing_backlog'})
        elif b == 0:
            eligible.append((idx, row, 0, 1))
        elif not due:
            excluded.append({'row_index': idx, 'reason': 'schedule_unknown'})
        elif due <= qend(origin):
            excluded.append({'row_index': idx, 'reason': 'overdue_positive_backlog'})
        else:
            # Quarter-level scenario, not a project progress curve or point-in-time sale.
            dq = due.year*4+(due.month-1)//3
            eligible.append((idx, row, b, dq-qnum(origin)))
    if not eligible or not any(b > 0 for _, _, b, _ in eligible):
        return None
    denom = 1 if monetary else current['B']
    coverage_complete = (not excluded and math.isclose(sum(b for _, _, b, _ in eligible), current['B'], abs_tol=1e-6))
    out = []
    for h in range(1, n+1):
        e = sum(b/denom*(cdf(h, d)-cdf(h-1, d)) for _, _, b, d in eligible)
        # Discrete +/- one-quarter rescheduling sensitivity, no presumed statistical level.
        candidates = [sum(b/denom*(cdf(h, max(1, d+shift))-cdf(h-1, max(1, d+shift)))
                          for _, _, b, d in eligible) for shift in (-1, 0, 1)]
        out.append({'existing_backlog_revenue': e if coverage_complete else None,
                    'covered_sites_partial_revenue': e,
                    'partial_existing_interval': interval(min(candidates), max(candidates)) if coverage_complete else interval(),
                    'covered_sites_partial_interval': interval(min(candidates), max(candidates))})
    return {'path': out, 'excluded': excluded, 'coverage_complete': coverage_complete,
            'rows': [{'row_index': i, 'label': r['label'], 'backlog_source_value': b,
                      'due_raw': r.get('due'), 'remaining_quarters': d} for i, r, b, d in eligible]}


def quarter_template(q, h, codes):
    return {'quarter': q, 'horizon': h, 'value': None, 'existing_backlog_revenue': None,
            'covered_sites_partial_revenue': None, 'new_order_revenue': None,
            'new_order_backlog': None, 'new_orders': None, 'remaining_existing_backlog': None,
            'interval': interval(), 'partial_existing_interval': interval(),
            'covered_sites_partial_interval': interval(), 'existing_backlog_method': None,
            'status': 'unavailable', 'reason_codes': list(codes)}


def scale_forecast_row(row, factor):
    result = copy.deepcopy(row)
    for key in ('value', 'existing_backlog_revenue', 'covered_sites_partial_revenue',
                'new_order_revenue', 'new_order_backlog', 'new_orders', 'remaining_existing_backlog'):
        if number(result.get(key)):
            result[key] *= factor
    for key in ('interval', 'partial_existing_interval', 'covered_sites_partial_interval'):
        for bound in ('lower', 'upper'):
            if number(result[key][bound]):
                result[key][bound] *= factor
    return result


def forecast_company(co, origin, n=10, with_context=True):
    ev = evidence(co, origin)
    cur = ev['current']; raw = cur.get('raw', {})
    reasons = list(cur.get('reasons', []))
    if co.get('role') == 'holding':
        reasons.append('holding_excluded')
    if not ev['branch']:
        reasons.append('coverage_unknown')
    if raw.get('cur') and raw.get('revenue_cur') and raw['cur'] != raw['revenue_cur']:
        reasons.append('currency_mismatch')
    proofs = scale_proof(raw)
    table_proof = unit_proof(raw)
    money_scale_ok = table_proof['verified'] and raw.get('cur') == 'KRW'
    if not table_proof['verified'] and not proofs and (number(cur.get('B')) or raw.get('unit_seen') is True):
        reasons.append('scale_unverified')
    if not ev['flows']:
        reasons.append('delivery_basis_unknown')
    if ev['duration'] is None:
        reasons.append('flow_history_short')
    if len(ev['orders']) < 4:
        reasons.append('new_order_history_short')
    allowed = (co.get('role') != 'holding' and cur.get('valid') and ev['branch'] is not None
               and number(cur.get('B')) and cur['B'] > 0)
    empirical = allowed and number(ev['duration'])
    schedule = scheduled_path(ev, n) if allowed and not empirical else None
    money_schedule = scheduled_path(ev, n, monetary=True) if allowed else None
    if schedule or money_schedule:
        if any(not s['coverage_complete'] for s in (schedule, money_schedule) if s):
            reasons.append('schedule_partial')
    normalized = {}
    monetary = {}
    new_ok = empirical and len(ev['orders']) >= 4
    ovs = [r['value']/cur['B'] for r in ev['orders']] if new_ok else []
    if ovs and quantile(ovs, .1) < 0:
        reasons.append('negative_order_quantile')
        ovs = []  # Preserve negative observations; do not replace cancellations with zero.
    all_missing_codes = sorted(set(reasons))
    path_reasons = [x for x in all_missing_codes if x != 'scale_unverified']
    for scenario, p in SCENARIOS.items():
        a = {'money_unit': None, 'value_unit': 'origin_backlog_fraction',
             'order_quantile': p, 'new_orders_per_quarter_deseasonalized': quantile(ovs, p),
             'duration_quarters': ev['duration'] if empirical else None,
             'lag_quarters': 1 if ev['branch'] == 'long_lead' else 0 if ev['branch'] == 'turnover' else None,
             'seasonality': {'enabled': False, 'reason': 'fixed_nonseasonal_round1_model; requires_separate_validation'},
             'timing_policy': 'fixed_observed_stock_flow_duration_in_all_scenarios',
             'duration_basis': 'median_previous_backlog_div_quarter_delivery; minimum_1_quarter',
             'new_order_recognition': 'next_quarter_uniform_cohorts' if ev['branch'] == 'long_lead' else 'same_quarter_turnover_cohorts',
             'sensitivity_duration_multipliers': [.75, 1, 1.25],
             'sensitivity_order_quantiles': [.10, .50, .90],
             'missing_reasons': path_reasons}
        paths = model_path(ev['branch'], ev['duration'], quantile(ovs, p), n) if empirical else None
        grid = [model_path(ev['branch'], max(1, ev['duration']*factor), quantile(ovs, op), n)
                for factor in (.75, 1, 1.25) for op in (.1, .5, .9)] if empirical else []
        qs, mqs = [], []
        for h in range(1, n+1):
            q = qadd(origin, h)
            r = quarter_template(q, h, path_reasons)
            if paths:
                r.update(paths[h-1])
                es = [g[h-1]['existing_backlog_revenue'] for g in grid]
                r['partial_existing_interval'] = interval(min(es), max(es))
                vs = [g[h-1]['value'] for g in grid if number(g[h-1]['value'])]
                if vs:
                    r['interval'] = interval(min(vs), max(vs))
                r['existing_backlog_method'] = 'long_lead_geometric_pool' if ev['branch'] == 'long_lead' else 'turnover_finite_liquidation'
                r['status'] = 'conditional_full_ledger_proxy' if number(r['value']) else 'partial_existing_only'
            elif schedule:
                r.update(schedule['path'][h-1])
                r['existing_backlog_method'] = 'disclosed_due_uniform_remaining_quarters'
                r['status'] = 'partial_existing_only'
            qs.append(r)
            mr = quarter_template(q, h, all_missing_codes)
            if money_scale_ok and (paths or schedule):
                mr = scale_forecast_row(r, cur['B'])
            elif money_schedule:
                mr.update(money_schedule['path'][h-1])
                mr['existing_backlog_method'] = 'verified_row_disclosed_due_uniform_remaining_quarters'
                mr['status'] = 'partial_existing_only'
            mqs.append(mr)
        observed = {r['quarter']: r['value']/cur['B'] for r in ev['flows']} if allowed else {}
        normalized[scenario] = {'assumptions': a, 'quarterly': qs,
                                'annual': annualize(qs, observed, origin, path_reasons)}
        ma = dict(a, money_unit='KRW_million' if money_schedule else None,
                  value_unit='KRW_million' if money_schedule else None,
                  new_orders_per_quarter_deseasonalized=None, duration_quarters=None,
                  lag_quarters=None, missing_reasons=all_missing_codes,
                  duration_basis='only_caption_verified_rows_with_valid_due_dates')
        if money_scale_ok and (empirical or schedule):
            ma = dict(a, money_unit='KRW_million', value_unit='KRW_million',
                      new_orders_per_quarter_deseasonalized=quantile(ovs, p)*cur['B'] if ovs else None,
                      missing_reasons=all_missing_codes,
                      amount_basis='stored_million_KRW_contract; scale_from_stored_value=1')
        money_observed = {r['quarter']: r['value'] for r in ev['flows']} if money_scale_ok and allowed else {}
        monetary[scenario] = {'assumptions': ma, 'quarterly': mqs,
                             'annual': annualize(mqs, money_observed, origin, all_missing_codes)}
    has_ratio = any(number(r.get(k)) for r in normalized['base']['quarterly']
                    for k in ('value', 'existing_backlog_revenue', 'covered_sites_partial_revenue'))
    has_money = any(number(r.get(k)) for r in monetary['base']['quarterly']
                    for k in ('value', 'existing_backlog_revenue', 'covered_sites_partial_revenue'))
    if has_ratio and not has_money:
        reasons.append('ratio_only')
    if not has_ratio and not has_money:
        reasons.append('no_model_evidence')
    complete_money = all(number(r['value']) for r in monetary['base']['quarterly'] + monetary['base']['annual'])
    status = 'conditional_full_ledger_proxy' if complete_money else 'partial_amount_estimate' if has_money or has_ratio else 'unavailable'
    evout = {k: v for k, v in ev.items() if k not in ('history', 'current')}
    evout['origin_backlog_source_value'] = cur.get('B')
    evout['origin_backlog_value_is_not_a_verified_currency_amount'] = not table_proof['verified']
    evout['raw_scale_basis'] = 'provided_company_quarter_normalization_contract' if table_proof['verified'] else ev['raw_scale_basis']
    evout['schedule'] = schedule
    evout['monetary_schedule'] = money_schedule
    entry = {'company_id': co['stock'], 'stock': co['stock'], 'company_name': co['name'],
             'audited_company_name': co['name'], 'source': 'kgrid_reports', 'origin': origin,
             'listed': True, 'role': co['role'], 'panel_present': True,
             'grade': 'conditional' if complete_money else 'partial' if status != 'unavailable' else 'unavailable',
             'audited_grade': 'offline_parsed_ledger_with_supplied_unit_contract',
             'status': status, 'availability': 'conditional_full' if complete_money else 'partial' if status != 'unavailable' else 'unavailable',
             'estimate_kind': 'verified_ledger_amount_and_ratio' if has_money and money_scale_ok else 'verified_row_amount_and_ratio' if has_money else 'ratio_only' if has_ratio else 'none',
             'reason_codes': sorted(set(reasons)), 'money_unit': 'KRW_million' if has_money else None,
             'currency': raw.get('cur'), 'scope': cur.get('scope', 'primary_orders_table'),
             'scope_labels': cur.get('selected_labels', []),
             'financial_statement_revenue': False, 'fiscal_year_end_month': 12,
             'fiscal_basis': 'assumed_December_close_not_verified_from_company_fiscal_metadata',
             'unit_audit': {'parser_recognized_at_origin': raw.get('unit_seen') is True,
                            'verified_at_origin': table_proof['verified'] or bool(proofs),
                            'verified_scope': 'parser_contract_primary_table' if table_proof['verified'] else 'matched_rows_only',
                            'proofs': proofs, 'main_table_scale_verified': table_proof['verified'],
                            'contract_evidence': table_proof,
                            'raw_tables_available': False, 'money_unit': table_proof['money_unit']},
             'audit_can': {'amount': 'conditional_full' if complete_money else 'partial' if has_money else 'no', 'ratio': 'yes' if has_ratio else 'no',
                           'backtest': 'rolling_origin_proxy_only'},
             'audit_blockers': [REASONS.get(x, x) for x in sorted(set(reasons))],
             'coverage': {'current_rows': len(raw.get('segments', [])),
                          'monetary_rows': len(cur.get('rows', [])) if money_scale_ok else len(proofs),
                          'full_existing_coverage': bool(allowed and (empirical or (schedule and schedule['coverage_complete']))),
                          'full_individual_site_coverage': False,
                          'model_branch': ev['branch'], 'model_coverage_years': ev['coverage_years']},
             'evidence': evout, 'scenarios': monetary,
             'normalized_forecast': {'value_unit': 'origin_backlog_fraction', 'denominator': 'selected_scope_origin_backlog',
                                     'money_unit': None, 'scenarios': normalized,
                                     'note': '1 = 기준 잔고; 다른 회사끼리 더하지 않음. 동일 정규화 배율의 시계열이라는 조건부 비율.'},
             'aggregate_forecast': {'site_id': '__primary_orders_table__', 'site_name': cur.get('scope'),
                                    'method': normalized['base']['quarterly'][0]['existing_backlog_method'],
                                    'model': {'origin': origin, 'branch': ev['branch'], 'duration_quarters': ev['duration']},
                                     'origin_backlog': cur.get('B') if money_scale_ok and allowed else None,
                                     'quarterly': monetary['base']['quarterly']},
             'actual_revenue_proxy': [{'quarter': q, 'value': v, 'money_unit': 'KRW_million'} for q, v in money_observed.items()],
             'provenance': {'file': 'input/kgrid_reports.json', 'json_pointer': '/companies/'+co['stock'],
                            'origin_receipt': raw.get('rcp'), 'contracts_added_to_backlog': False,
                            'point_in_time_filing_vintages_available': False}}
    if with_context:
        entry['industry_axes'] = industry_axes(co, origin)
    return entry


def industry_axes(co, origin):
    x = co.get('quarters', {}).get(origin, {})
    text = ' '.join(quotes(x))
    usable = [t for t in quotes(x) if '단위' not in t and len(re.findall(r'\d[\d,.]*', t)) < 5]
    probe = co.get('_probe', {})
    if probe.get('quarter') != origin or probe.get('rcp') != x.get('rcp'):
        probe = {}  # Do not attach current-quarter prose to a historical forecast origin.
    return {'grid_products': [r.get('label') for r in x.get('segments', [])],
            'probe_evidence': {k: probe.get(k) for k in ('quarter', 'rcp', 'product', 'terms', 'evidence', 'neg_evidence')},
            'probe_basis': 'matching_company_quarter_receipt; qualitative_product_support_only',
            'branch_policy': 'long_lead_if_same_currency_coverage_ge_1_year_else_turnover; no_keyword_duration_inference',
            'utility_customers': [{k: r.get(k) for k in ('name', 'share_pct', 'seg', 'entity', 'tbl', 'evidence')}
                                  for r in x.get('customers', []) if r.get('tbl') == 0 and r.get('evidence') == 'named'],
            'customer_note': '실명은 전력회사 판정과 다름. 본체 tbl=0만 표시; entity가 종속회사이면 회사 대표 비중 아님. 합산·수주 배분 안 함.',
            'demand_quotes': usable[:5], 'demand_scope': 'supplied_origin_text_only',
            'hvdc_text_present': 'HVDC' in text,
            'shipping_schedule': {'observed': False, 'reason': '선적·납품·검수 마일스톤별 표 미제공'},
            'production_stage': {'observed': False, 'reason': '설계/조달/권선/조립/시험/검수 실측 공정률 없음'},
            'unit_machine': {'observed': False, 'reason': '개별 변압기·호기 식별자와 분할 인도금액 없음'},
            'model_does_not_allocate_by_customer_product_grid_stage_or_unit': True}


def contract_audit(contracts, universe):
    roles = {r['stock']: r['role'] for r in universe['rows']}
    counts = Counter(); rows = []
    for i, r in enumerate(contracts['rows']):
        if r['stock'] not in roles:
            bucket = 'outside_universe'
        elif r.get('subsidiary') or roles[r['stock']] == 'holding':
            bucket = 'subsidiary_or_holding_reannouncement'
        else:
            bucket = 'own_disclosure'
        counts[bucket] += 1
        rows.append({'input_row': i, 'stock': r['stock'], 'rcp': r.get('rcp'),
                     'bucket': bucket, 'canceled': bool(r.get('canceled')),
                     'corrected': bool(r.get('corrected')), 'withheld': bool(r.get('withheld')),
                     'date': r.get('date'), 'start': r.get('start'), 'end': r.get('end'),
                     'party': r.get('party'), 'utility_flag': r.get('utility'),
                     'used_for_order_or_backlog_amount': False})
    active = Counter(r['bucket'] for r in rows if not r['canceled'])
    return {'raw_rows': len(rows), 'partition_counts': dict(counts), 'noncanceled_counts': dict(active),
            'corrected_rows': sum(r['corrected'] for r in rows), 'canceled_rows': sum(r['canceled'] for r in rows),
            'all_subsidiary_flag_rows': sum(bool(r.get('subsidiary')) for r in contracts['rows']),
            'duplicate_receipt_rows': len(rows)-len({r['rcp'] for r in rows}),
            'documentation_counts': {'own': 176, 'reannouncement': 76},
            'documentation_matches_current_input': False,
            'policy': 'No contract amounts summed. No durable amendment-chain/original-contract key is supplied; corrected rows may repeat a contract. Contract periods are not remaining order backlog.',
            'rows': rows}


def audit_company(co, fc, quarters, contracts):
    qs = {}
    jobs = []
    for q in quarters:
        x = co.get('quarters', {}).get(q, {})
        rows = x.get('segments', [])
        agg = [i for i, r in enumerate(rows) if aggregate_row(r)]
        atomic = [r for r in rows if not aggregate_row(r)]
        provided = x.get('backlog')
        atomic_sum = total(r.get('closing') for r in atomic)
        present_sum = sum(r['closing'] for r in atomic if number(r.get('closing')))
        raw_sum = sum(r['closing'] for r in rows if number(r.get('closing')))
        snap = table_snapshot(co, q)
        proof = scale_proof(x)
        contract_proof = unit_proof(x)
        dates = [{'row_index': i, 'label': r.get('label'), 'order_date_raw': r.get('order_date'),
                  'due_raw': r.get('due'), 'parsed_due': due_date(r.get('due')).isoformat() if due_date(r.get('due')) else None,
                  'overdue_with_positive_backlog': bool(due_date(r.get('due')) and due_date(r.get('due')) <= qend(q)
                                                       and number(r.get('closing')) and r['closing'] > 0)} for i, r in enumerate(rows)]
        qa = {'present': bool(x), 'ok': x.get('ok'), 'receipt': x.get('rcp'),
              'shape': x.get('shape'), 'entity': x.get('entity'), 'grain': x.get('grain'),
              'rows': len(rows), 'aggregate_rows': len(agg), 'aggregate_row_indices': agg,
              'atomic_rows': len(atomic), 'missing_closing_cells': sum(not number(r.get('closing')) for r in atomic),
              'other_table_count': len(x.get('orders_other', [])), 'other_tables_excluded': x.get('orders_other', []),
              'unit_parser_recognized': x.get('unit_seen') is True, 'currency': x.get('cur'),
              'unit_note': x.get('unit_note'), 'unit_from_prev': x.get('unit_from_prev'),
              'raw_unit_caption_for_primary_table': None, 'scale_verified_rows': proof,
              'unit_contract_evidence': contract_proof,
              'main_table_scale_verified': contract_proof['verified'], 'revenue_currency': x.get('revenue_cur'),
              'revenue_basis': x.get('revenue_basis'), 'revenue_fy_col': x.get('revenue_fy_col'),
              'provided_coverage_years': x.get('coverage_years'),
              'source_values': {'unit_verified': contract_proof['verified'], 'backlog': provided, 'row_sum_present': raw_sum if rows else None,
                 'atomic_sum_complete': atomic_sum if atomic else None, 'atomic_sum_present': present_sum if atomic else None,
                 'provided_minus_atomic_present': provided-present_sum if number(provided) and atomic else None},
              'provided_total_mismatch': x.get('total_mismatch'), 'dates': dates,
              'blocking_codes': snap['reasons']}
        qs[q] = qa
        if co['role'] != 'holding':
            needs = ['II-4 수주상황 원표 cols/rows/lead, 앞 단위 캡션, 정규화 배율·통화, 표 주체, 연결/별도',
                     '기납품액·신규수주 열의 당기누계/계약누계 구분과 주석; 같은 범위 분기 매출 및 기초/기말 조정']
            why = [] if contract_proof['verified'] else ['unit_unrecognized' if not x.get('unit_seen') else 'scale_unverified']
            if contract_proof['verified']:
                needs[0] = 'II-4 원표 cols/rows/lead·주체·연결/별도: 단위 정규화 계약은 확보, 원표 귀속 독립 대조는 미완'
            if not rows:
                needs.append('수주표 미공시 문구 또는 누락 표; 계약공시로 잔고를 대신 합산하지 말 것')
                why.append('missing_backlog')
            if agg:
                needs.append('날짜 칸 합계행 및 rowspan 원표; 낱행·소계·총계 구분 재추출')
                why.append('aggregate_contamination')
            if not x.get('coverage_years'):
                needs.append('직전 사업연도 같은 주체·통화의 12개월 매출; 외화 잔고는 동일 통화 매출 또는 공시 환율')
                why.append('coverage_unknown')
            if any(not d['parsed_due'] or d['overdue_with_positive_backlog'] for d in dates):
                needs.append('납기 각주·변경 사유, 선적/납품/시험/검수 일정, 호기/기기별 잔고와 인식 조건')
            if 'scope_non_grid' in snap['reasons']:
                needs.append('II-2/II-4 전력망 사업부 수주표; 현재 비전력 표의 대체 가능 여부')
                why.append('scope_non_grid')
            jobs.append({'stock': co['stock'], 'company_name': co['name'], 'quarter': q,
                         'existing_receipt': x.get('rcp'), 'priority': 'P0',
                         'action': 'recover_raw_cache_then_targeted_DART_if_absent',
                         'reason_codes': why, 'collect': needs})
    if co['role'] != 'holding':
        for q in (qadd('2021Q4', i) for i in range(19)):
            if q in co.get('quarters', {}):
                continue
            jobs.append({'stock': co['stock'], 'company_name': co['name'], 'quarter': q,
                         'existing_receipt': None, 'priority': 'P1', 'action': 'collect_missing_history',
                         'reason_codes': ['needs_longer_ledger'],
                         'collect': ['II-4 수주/매출 원표·단위·범위·누계 구분·접수일 및 원본/정정 이력',
                                     '사업연도·결산월; 분기 신규수주·취소·환율/연결범위 조정; 선표·공정·호기 공시 여부']})
    return {'stock': co['stock'], 'company_name': co['name'], 'role': co['role'],
            'status': fc['availability'], 'panel_status': fc['status'], 'estimate_kind': fc['estimate_kind'],
            'reason_codes': fc['reason_codes'], 'blockers': fc['audit_blockers'],
            'quarter_count': len(co.get('quarters', {})), 'successful_quarter_count': sum(bool(v.get('ok')) for v in qs.values()),
            'row_count': sum(v['rows'] for v in qs.values()), 'aggregate_rows': sum(v['aggregate_rows'] for v in qs.values()),
            'quarters': qs, 'contracts': [r for r in contracts['rows'] if r['stock'] == co['stock']],
            'collection_tasks': jobs}


def metrics(rows):
    errs = [r['predicted']-r['actual'] for r in rows]
    denominator = sum(abs(r['actual']) for r in rows)
    return {'n': len(rows), 'company_count': len({r['stock'] for r in rows}),
            'mae_origin_backlog_fraction': statistics.mean(map(abs, errs)) if errs else None,
            'median_absolute_error': statistics.median(map(abs, errs)) if errs else None,
            'wape_pct': sum(map(abs, errs))/denominator*100 if denominator else None,
            'bias_pct': sum(errs)/denominator*100 if denominator else None,
            'interval_hit_rate_pct': sum(r['lower'] <= r['actual'] <= r['upper'] for r in rows)/len(rows)*100 if rows else None,
            'small_sample': len(rows) < 20, 'calibrated': False}


def backtest(reports):
    rows = []; money_rows = []; excluded = Counter()
    quarters = sorted(reports['quarters'], key=qnum)
    # Recompute every origin from truncated report snapshots. No latest dates/customer text.
    for co in reports['companies'].values():
        if co['role'] == 'holding':
            excluded['holding_companies'] += 1
            continue
        for origin in quarters[:-1]:
            fc = forecast_company(co, origin, 10, with_context=False)
            ev = evidence(co, origin)
            b = ev['current'].get('B')
            for r in fc['normalized_forecast']['scenarios']['base']['quarterly']:
                target = r['quarter']
                if target not in quarters:
                    excluded['target_after_input'] += 1
                    continue
                if not number(r['value']):
                    excluded['prediction_unavailable'] += 1
                    continue
                te = evidence(co, target)
                actual = next((x['value'] for x in te['flows'] if x['quarter'] == target), None)
                if te['current'].get('scope_key') != ev['current'].get('scope_key') or not number(actual) or not b:
                    excluded['missing_or_scope_changed_target'] += 1
                    continue
                rows.append({'stock': co['stock'], 'company_name': co['name'], 'origin': origin,
                             'target': target, 'horizon': r['horizon'], 'branch': ev['branch'],
                             'value_unit': 'origin_backlog_fraction', 'origin_backlog_source_value': b,
                             'actual_delivery_source_value': actual, 'actual': actual/b,
                             'predicted': r['value'], 'lower': r['interval']['lower'], 'upper': r['interval']['upper'],
                             'origin_receipt': co['quarters'][origin]['rcp'], 'target_receipt': co['quarters'][target]['rcp'],
                             'target_is_financial_statement_revenue': False})
                mr = fc['scenarios']['base']['quarterly'][r['horizon']-1]
                if number(mr['value']) and unit_proof(te['current']['raw'])['verified']:
                    money_rows.append(dict(rows[-1], value_unit='KRW_million', actual=actual,
                        predicted=mr['value'], lower=mr['interval']['lower'], upper=mr['interval']['upper']))
    annual = []
    grouped = {}
    for r in rows:
        grouped.setdefault((r['stock'], r['origin'], int(r['target'][:4])), []).append(r)
    for (stock, origin, year), rs in grouped.items():
        if {r['target'] for r in rs} == {f'{year}Q{k}' for k in range(1, 5)}:
            annual.append({'stock': stock, 'origin': origin, 'target_year': year,
                           **{k: sum(r[k] for r in rs) for k in ('predicted', 'actual', 'lower', 'upper')}})
    return {'scope': 'rolling_origin_total_delivery_proxy_including_new_order_assumptions',
            'money_observations': len(money_rows), 'money_rows': money_rows,
            'money_metrics': money_metrics(money_rows), 'value_unit': 'origin_backlog_fraction',
            'point_in_time': 'snapshot_cutoff_only; receipt/revision vintages absent; not real-time investable validation',
            'origins': quarters[:-1], 'rows': rows, 'metrics': metrics(rows),
            'by_horizon': {str(h): metrics([r for r in rows if r['horizon'] == h]) for h in range(1, 11)},
            'by_branch': {b: metrics([r for r in rows if r['branch'] == b]) for b in ('long_lead', 'turnover')},
            'by_company': {c: metrics([r for r in rows if r['stock'] == c]) for c in reports['companies']},
            'annual_rows': annual, 'annual_metrics': metrics(annual), 'exclusions': dict(excluded),
            'warning': '현재 원장 6분기; 유효 백테스트는 T+1만 존재. T+2~T+10·완전 연간 미검증. 겹치는 origin/target은 독립 표본이 아님. 민감도 포함률은 보정 성능이 아님.',
            'retry_reason_codes': ['needs_longer_ledger'],
            'uncalibrated_interval_policy': 'parameter_sensitivity_only; never fitted to heldout targets',
            'excluded_targets_preserved': True}


def money_metrics(rows):
    result = metrics(rows)
    result['mae_KRW_million'] = result.pop('mae_origin_backlog_fraction')
    result['value_unit'] = 'KRW_million'
    result['pooling_policy'] = 'error_metrics_only; not an_industry_revenue_aggregate'
    return result


def retry_plan(fc, co):
    if co['role'] == 'holding':
        return {'group': 'holding_excluded', 'reason_codes': ['holding_excluded'], 'rerun_on_ledger_extension': False}
    missing = [qadd('2021Q4', i) for i in range(19) if qadd('2021Q4', i) not in co['quarters']]
    blockers = [c for c in fc['reason_codes'] if c not in ('flow_history_short', 'new_order_history_short',
                                                        'ratio_only', 'no_model_evidence')]
    if fc['status'] == 'conditional_full_ledger_proxy':
        group = 'validation_only'
    elif fc['evidence']['duration'] is not None and not blockers:
        group = 'forecast_sample_short'
    else:
        group = 'history_plus_other_evidence'
    return {'group': group, 'reason_codes': ['needs_longer_ledger'] if missing else [],
            'rerun_on_ledger_extension': bool(missing), 'target_quarters': '2021Q4..2026Q2',
            'target_quarter_count': 19, 'available_quarter_count': len(co['quarters']),
            'missing_quarters': missing, 'eligible_order_samples': len(fc['evidence']['orders']),
            'required_order_samples': 4, 'eligible_delivery_rates': len(fc['evidence']['rates']),
            'required_delivery_rates': 2, 'other_evidence_reason_codes': blockers,
            'longer_ledger_alone_guarantees_forecast': False,
            'condition': '동일 주체·범위·통화·검증 단위·당기누계가 확인된 분기만 적격. 범위 변경 이전 분기는 자동 편입하지 않음.'}


def manual_checks(panel):
    """Independent FY2027 cohort arithmetic, without calling model_path/cdf."""
    traces = []
    for stock in ('267260', '033100'):
        f = next(c for c in panel['companies'] if c['stock'] == stock)
        a = f['normalized_forecast']['scenarios']['base']['assumptions']
        d = a['duration_quarters']; o = a['new_orders_per_quarter_deseasonalized']
        qs = []
        for h in range(3, 7):
            existing = (1/d)*(1-1/d)**(h-1) if a['lag_quarters'] == 1 else max(0, min(h,d)-min(h-1,d))/d
            lag = a['lag_quarters']
            cohorts = [o*max(0, min(h-j+1-lag,d)-max(0,min(h-j-lag,d)))/d for j in range(1,h+1)]
            qs.append({'quarter': qadd('2026Q2',h), 'existing': existing, 'cohorts': cohorts})
        value = sum(r['existing']+sum(r['cohorts']) for r in qs)
        b = f['evidence']['origin_backlog_source_value']
        target = f['normalized_forecast']['scenarios']['base']['annual'][1]['value']
        traces.append({'stock':stock, 'duration':d, 'orders_per_quarter_ratio':o, 'quarters':qs,
                       'FY2027':value, 'FY2027_KRW_million':value*b, 'difference':value-target})
    return traces


def write_documents(out, panel, audit, reports):
    from forecast_section import write_sections
    write_sections(out, panel)
    traces = manual_checks(panel)
    write_json(out/'fy2027_manual_checks.json', traces)
    pop = panel['population']; bt = panel['backtest']; us = panel['round1_comparison']['unit_evidence']
    def fmt(v):
        return f'{v:,.3f}' if number(v) else '—'
    lines = ['# ARGUS-kgrid 2차 재감사', '',
        f"기준 2026Q2. 모집단 **{pop['input_companies']}사 = 추정 {pop['estimated_companies']}사 + 미추정 {pop['unestimated_companies']}사**. "
        f"선택 원장 범위의 분기·연간 전체 금액 추정 {pop['full_forecast_companies']}사, 잔고분 부분 추정 {pop['estimated_companies']-pop['full_forecast_companies']}사. 지주 3사는 미추정에 포함한다.", '',
        '## 1차를 이어 변경한 것', '',
        '제공된 kgrid_forecast.py·forecast_section.py를 복사해 단위 연결, 금액 경로, 재실행 목록, 금액 백테스트를 추가했다. '
        '기존 model_path의 장납기·회전 수식과 적격 표본 기준을 유지했다. 입력 kgrid_audit.json의 회사별 사유·모집단과 실제 비교를 남겼다. '
        '1차 10사 추정(대부분 비율, 금액은 제룡산업 일부 행)에서 이번에는 10사 모두 검증 단위의 금액을 제시한다.', '',
        f"단위 파일은 **{us['evidence_companies']}사·{us['evidence_company_quarters']}회사분기**, 원장/모집단은 **34사·{us['report_company_quarters']}회사분기**다. "
        f"모집단 회사분기 캡션 연결 {us['covered_universe_company_quarters']}개, 기준분기 본체 표 정규화 계약 검증 {us['verified_primary_tables_at_origin']}사다. "
        '추정 모집단은 kgrid_universe.rows와 kgrid_reports.companies가 일치하는 34사를 사용한다. '
        '191개 프로브는 탐색 후보이며 모집단이 아니다. 단위 파일에만 있는 7개 ID는 '+', '.join(us['outside_universe_unit_evidence_ids'])+'이다.', '',
        '모집단 안에서 캡션 목록이 없는 한 쌍은 선도전기(007610) 2025Q3이며 원장에 본체 잔고도 없다. '
        '1차의 scale_unverified는 해소했다. 기준분기 수주표가 없는 10사는 missing_backlog/unit_unrecognized로 남기며 단위 계약 자체가 미제공됐다고 다시 분류하지 않는다.', '',
        '정규화 근거: '+us['normalization_contract'], '',
        '**이미 저장된 백만원에 추가 배율을 곱하지 않는다.** 원문 캡션은 회사·분기별 후보 목록이며 개별 표와의 직접 대응표는 아니다. '
        '이번 판정은 제공된 파서 정규화 계약과 원장의 unit_seen·통화를 함께 신뢰한 검증이다. 파서 소스 및 원표 전체는 제공되지 않아 독립 재파싱은 못 했다. '
        '일진전기·일진홀딩스의 USD는 KRW로 환산하지 않는다. 단위 계약은 누락 수주표·중복 합계행·다른 부문 문제를 해결하지 않는다.', '',
        '## 산업 축과 모델', '',
        '1차의 전력계통/제품군, 전력회사 고객, 선적·납품·검수 선표, 설계·조달·제조·시험 공정, 기기·호기 축을 유지한다. '
        '프로브 원행은 회사명·종목·분기·접수번호가 맞을 때 제품·계통 인용 근거로 연결한다. 키워드 점수로 납기나 금액을 만들지 않는다. '
        '개별 선적·검수 마일스톤, 실측 공정률, 호기별 금액이 없어 그 축의 미래 배분은 미추정이다.', '',
        '장납기/회전은 같은 통화의 기준 잔고÷직전 연매출 ≥1년/＜1년을 따른다. LS·효성중공업은 본체 표의 전력/중공업 선택 행만 사용하고 건설·자동화·다른 수주표를 더하지 않는다. '
        '그 외 회사는 본체 수주표 범위이며, 포함된 통신·태양광 등 혼합 제품을 전력망 순수 매출로 재명명하지 않는다. '
        '연간 결산월은 12월 가정이며 회사별 결산 메타데이터로 확인하지 못했다.', '',
        '분기 소진 대용치는 당기누계가 확인된 기납품액의 Q1 리셋/전분기 차분이다. roll 이외에는 같은 연도 매출 표와 1.5% 이내 일치하는 파싱값이 보강 근거이며 원문 열 머리 검증은 아니다. '
        '신규수주는 직접 공시 당기수주 차분 또는 Δ잔고+분기 기납품 대용치다. 취소·환율·범위 조정이 섞일 수 있다. '
        '계약누계인지 모르는 기납품액은 분기 매출로 바꾸지 않는다. 동일 범위 소진률 2개, 신규수주 4개가 최소 기준이다.', '',
        'd=max(1, median(직전 잔고/분기 기납품)), 기준잔고 B0. 장납기 잔고분=B0×(1/d)×(1−1/d)^(h−1), '
        '회전 잔고분=B0×[min(1,h/d)−min(1,(h−1)/d)]. 신규분은 매분기 일정 주문 코호트를 d분기에 걸쳐 균등 인식한다. '
        '장납기는 다음 분기, 회전은 같은 분기부터 인식한다. 실제 공장 납기를 측정한 값이 아니다.', '',
        '보수/기준/낙관은 적격 순수주 대용치 P25/P50/P75이며 세 경우 모두 같은 소진기간을 사용한다. '
        '음수 순수주를 0으로 바꾸지 않으며 지원되지 않는 음수 분위가 생기면 신규분을 비운다. '
        '민감도는 기간×[0.75,1,1.25], 주문 P10/P50/P90의 격자이며 모든 구간 calibrated=false, nominal_level=null이다. '
        '납기 기반 부분 추정은 남은 분기 균등 배분·±1분기 민감도다. 구간은 통계적 신뢰구간이 아니다.', '',
        'FY2026=확인된 2026Q1/Q2 흐름+Q3/Q4 예측, FY2027/2028=각 4분기 합이다. '
        '잔고분·신규분은 미래분만, 이미 관측한 H1은 별도 필드다. 구성요소 하나라도 미상인 전체 값은 null이다. '
        '일부 행 잔고분은 covered_sites_partial_revenue이며 기존 잔고 전체와 중복 합산하면 안 된다.', '',
        '## 전수 판정', '',
        '| 종목 | 회사 | 판정 | 모델 | 단위 계약 | 주문 표본 | 사유 코드 |',
        '|---|---|---|---|---|---:|---|']
    for f in panel['companies']:
        label = '전체 조건부' if f['status']=='conditional_full_ledger_proxy' else '부분 잔고' if f['status']!='unavailable' else '미추정'
        lines.append(f"| {f['stock']} | {f['company_name']} | {label} | {f['evidence']['branch'] or '미상'} | {'검증' if f['unit_audit']['main_table_scale_verified'] else '표 미확인'} | {len(f['evidence']['orders'])} | {', '.join(f['reason_codes']) or '—'} |")
    lines += ['', '## 연간 전체 금액 추정 · 백만원', '',
              '조건부 전체 추정 6사의 선택 원장 납품 대용치다. 회사 전체 재무제표 매출 또는 산업 합계로 해석하지 않는다. 분기 10개·3시나리오·구성요소·민감도는 JSON과 회사별 HTML에 모두 포함한다.', '',
              '| 회사 | 시나리오 | FY2026 | FY2027 | FY2028 |', '|---|---|---:|---:|---:|']
    for f in panel['companies']:
        if f['status']=='conditional_full_ledger_proxy':
            for key,s in f['scenarios'].items():
                lines.append('| '+f['company_name']+' | '+key+' | '+' | '.join(fmt(r['value']) for r in s['annual'])+' |')
    lines += ['', '## 원장 확장 후 재실행 목록', '',
        '모든 목록은 forecast_panel.json 및 kgrid_audit.json의 retry_queue에 종목·누락 분기·사유·적격 표본 수로 저장했다. '
        '`reason_codes`에 `needs_longer_ledger`가 있는 항목만 선택해 재실행할 수 있다. 입력은 실제로 2025Q1~2026Q2 **6분기**이며 19분기 목표까지 회사당 13분기가 빠져 있다. '
        '과거 분기가 늘어도 같은 범위 적격 표본이 늘어난다는 보장은 없다.', '',
        '| 그룹 | 회사 | 다음 검증 |', '|---|---|---|']
    for group,desc in [('forecast_sample_short','신규수주 적격 표본 4개 확보 시 전체 추정 재평가. 가온전선은 2025Q3 범위 변경이 있어 그 이전 자료를 자동 차분 연결할 수 없음'),
                       ('validation_only','현재 추정 유지, 시점별 재적합으로 T+2~T+10·연간 검증 표본 확보'),
                       ('history_plus_other_evidence','원장 확장과 함께 각 회사 other_evidence_reason_codes의 누계·납기·범위·단위/표 누락 해소 필요')]:
        names=[r['company_name'] for r in panel['retry_queue'] if r['group']==group]
        lines.append('| '+group+' | '+', '.join(names)+' | '+desc+' |')
    lines += ['', '지주 3사는 원장 길이와 무관하게 독립 추정/합산 제외한다. 단위 근거 확보만으로 광명전기의 합계행 혼입을 자동 제거하지 않았다. '
        '서전기전·LS마린솔루션 등의 계약누계 의심, 세명전기·누리플렉스의 같은 범위 직전 연매출 부재, 비츠로테크·삼영·서남의 비전력 표 범위 문제는 별도 근거가 필요하다.', '',
        '## 백테스트', '',
        f"현재 실측 비교 **{bt['metrics']['n']}개·{bt['metrics']['company_count']}사**, 모두 T+1. 금액 비교 {bt['money_observations']}개, 완전 연간 {bt['annual_metrics']['n']}개. "
        f"기준잔고 비율 WAPE {fmt(bt['metrics']['wape_pct'])}%, bias {fmt(bt['metrics']['bias_pct'])}%. "
        f"금액 WAPE {fmt(bt['money_metrics']['wape_pct'])}%, bias {fmt(bt['money_metrics']['bias_pct'])}%, MAE {fmt(bt['money_metrics']['mae_KRW_million'])}백만원. "
        f"민감도 포함률 {fmt(bt['metrics']['interval_hit_rate_pct'])}%는 신뢰수준 추정이 아니다.", '',
        '각 origin 이하 분기만으로 다시 적합하고 실제 target 기납품 차분과 비교했다. 신규분·잔고분의 실측 분해는 없으므로 총 납품 대용치만 평가한다. '
        '회사별 비율 WAPE와 금액 합산 오차의 가중치가 달라 지표가 다르다. 금액 오차를 합산하는 것은 산업 매출 집계가 아니다. '
        '정정 전 원본·공시 시점별 빈티지가 없어 실시간 투자 가능 성능이 아닌 최신 수정 원장의 사후 검증이다. '
        'T+2~T+10 및 완전 연간 지표는 n=0/null로 남겼다. 실측값과 예측값을 재사용해 표본을 늘리지 않았다.', '',
        '| 회사 | origin → target | 예측 백만원 | 실측 백만원 |', '|---|---|---:|---:|']
    for r in bt['money_rows']:
        lines.append(f"| {r['company_name']} | {r['origin']} → {r['target']} | {fmt(r['predicted'])} | {fmt(r['actual'])} |")
    residuals=[r for f in panel['companies'] if f['role']!='holding' for r in f['evidence']['orders'] if abs(r.get('reconciliation_residual') or 0)>1000]
    lines += ['', '효성중공업의 공시 신규수주와 잔고 롤포워드에는 큰 잔차가 남는다. 신규수주 자체는 직접 공시값으로 사용하되 잔차를 evidence.orders에 그대로 보존했다. '
        f'1,000백만원 초과 잔차 {len(residuals)}개를 취소/환율 등으로 임의 분해하지 않았다.', '',
        '## FY2027 독립 산식 검산 2사', '',
        'HD현대일렉트릭(장납기)·제룡전기(회전)의 기준 잔고=1 비율 및 주문 코호트를 model_path/cdf 호출 없이 별도 계산했다. fy2027_manual_checks.json에 분기별 항과 금액 변환을 남겼다.', '']
    for t in traces:
        lines.append(f"- {t['stock']}: FY2027 {fmt(t['FY2027_KRW_million'])}백만원, 비율 {t['FY2027']:.9f}, 엔진 차이 {t['difference']:.12g}.")
    lines += ['', '## 사유 코드', '']
    for code in sorted({c for f in panel['companies'] for c in f['reason_codes']}|{'needs_longer_ledger'}):
        lines.append('- `'+code+'`: '+REASONS[code])
    lines += ['', '## 실행과 검증', '',
        '`python3 -B output/kgrid_forecast.py --input-dir input --output-dir output`', '',
        '`python3 -B -m unittest discover -s output -p test_kgrid_forecast.py -v`', '',
        '테스트는 입력 불변 해시, 모집단 보존, 단위 연결 제거 시 차단, 통화/지주 차단, 미래 원장 오염 독립성, 잔고 질량보존, 분기/연간 분해, '
        '민감도 포함, 실제 백테스트 정답 재계산, 사유별 재실행 목록, HTML/SVG 균형·이스케이프를 검사한다. '
        '표준 라이브러리와 인라인 SVG만 사용한다. 정본 편집·배포·외부 패키지·네트워크 수집은 실행하지 않았다. '
        'tracker preflight는 central_connection_failed를 반환해 세션 전역 상태 확인은 못 했다. 배정된 output/만 편집했다.', '']
    (out/'kgrid_REPORT.md').write_text('\n'.join(lines))


def rounded(x):
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError('nonfinite output')
        return round(x, 9)
    if isinstance(x, dict):
        return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rounded(v) for v in x]
    return x


def build(input_dir):
    root = Path(input_dir)
    reports = json.loads((root/'kgrid_reports.json').read_text())
    contracts = json.loads((root/'kgrid_contracts.json').read_text())
    universe = json.loads((root/'kgrid_universe.json').read_text())
    units = json.loads((root/'kgrid_unit_evidence.json').read_text())
    probes = json.loads((root/'kgrid_probe_rows.json').read_text())
    previous_audit = json.loads((root/'kgrid_audit.json').read_text())
    reports = attach_evidence(reports, units, probes)
    ids = [r['stock'] for r in universe['rows']]
    if len(ids) != len(set(ids)) or set(ids) != set(reports['companies']):
        raise ValueError('universe/report identity mismatch: cannot invent or silently drop companies')
    if reports['n'] != len(ids) or universe['n'] != len(ids):
        raise ValueError('population count mismatch')
    for u in universe['rows']:
        c = reports['companies'][u['stock']]
        if c['stock'] != u['stock'] or c['name'] != u['name'] or c['role'] != u['role']:
            raise ValueError('company_identity_conflict')
    origin = max(reports['quarters'], key=qnum)
    if origin != '2026Q2':
        raise ValueError('bounded FY2026-FY2028 assignment requires 2026Q2 origin')
    forecasts = [forecast_company(reports['companies'][code], origin) for code in ids]
    ca = contract_audit(contracts, universe)
    audits = [audit_company(reports['companies'][f['stock']], f, reports['quarters'], ca) for f in forecasts]
    status_counts = Counter(f['status'] for f in forecasts)
    estimated = sum(f['status'] != 'unavailable' for f in forecasts)
    population = {'input_entries': len(ids), 'input_companies': len(ids), 'listed_companies': len(ids),
                  'unlisted_companies': 0, 'holding_companies': sum(c['role'] == 'holding' for c in forecasts),
                  'status_counts': dict(status_counts),
                  'availability_counts': dict(Counter(f['availability'] for f in forecasts)),
                  'estimated_companies': estimated, 'unestimated_companies': len(ids)-estimated,
                  'full_forecast_companies': sum(f['status'] == 'conditional_full_ledger_proxy' for f in forecasts),
                  'amount_estimated_companies': sum(f['money_unit'] == 'KRW_million' for f in forecasts),
                  'ratio_estimated_companies': sum(f['estimate_kind'] != 'none' for f in forecasts),
                  'note': 'full_forecast means the selected ledger scope, conditional model, not consolidated financial statement revenue; partial estimates counted separately'}
    ratios = [c['quarters'][origin]['coverage_years'] for c in reports['companies'].values()
              if c['role'] != 'holding' and number(c['quarters'][origin].get('coverage_years'))]
    doc_check = {'documentation': {'long_lead': 9, 'turnover': 8, 'median_years': 1.11},
                 'current_input_nonholding': {'n': len(ratios), 'long_lead': sum(v >= 1 for v in ratios),
                    'turnover': sum(v < 1 for v in ratios), 'median_years': statistics.median(ratios)},
                 'warning': '文書와 현재 입력의 모집단/시점 차이 원인 미확정. 제공 배수는 본체/비전력 범위 및 광명 합계 오류를 포함; 경제적 전수 분류로 단정하지 않음.'}
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir()) if p.is_file()}
    bt = backtest(reports)
    for f in forecasts:
        f['backtest_summary'] = {'company': bt['by_company'][f['stock']], 'all_companies': bt['metrics'],
                                 'annual_n': bt['annual_metrics']['n'], 'money_n': bt['money_observations'],
                                 'company_money': money_metrics([r for r in bt['money_rows'] if r['stock'] == f['stock']]),
                                 'warning': bt['warning']}
        f['retry_plan'] = retry_plan(f, reports['companies'][f['stock']])
    unit_summary = {'evidence_companies': len(units['companies']),
        'evidence_company_quarters': sum(len(qs) for qs in units['companies'].values()),
        'forecast_universe_companies': len(ids), 'report_company_quarters': sum(len(c['quarters']) for c in reports['companies'].values()),
        'outside_universe_unit_evidence_ids': sorted(set(units['companies'])-set(ids)),
        'covered_universe_company_quarters': sum(q in units['companies'].get(code, {}) for code, co in reports['companies'].items() for q in co['quarters']),
        'missing_caption_pairs': [{'stock': code, 'quarter': q} for code, co in reports['companies'].items()
                                  for q in co['quarters'] if q not in units['companies'].get(code, {})],
        'verified_primary_tables_at_origin': sum(f['unit_audit']['main_table_scale_verified'] for f in forecasts),
        'normalization_contract': units['unit_contract'], 'independent_raw_table_reconstruction': False}
    previous_by_id = {c['stock']: c for c in previous_audit['companies']}
    comparison = {'previous_population': previous_audit['population'], 'unit_evidence': unit_summary,
        'companies': [{'stock': f['stock'], 'previous_estimate_kind': previous_by_id.get(f['stock'], {}).get('estimate_kind'),
          'current_estimate_kind': f['estimate_kind'],
          'resolved_reason_codes': sorted(set(previous_by_id.get(f['stock'], {}).get('reason_codes', []))-set(f['reason_codes'])),
          'remaining_reason_codes': f['reason_codes']} for f in forecasts]}
    retries = [dict(stock=f['stock'], company_name=f['company_name'], **f['retry_plan']) for f in forecasts]
    panel = {'schema_version': 'kgrid-2-unit-evidence', 'assignment': 'ARGUS-kgrid-round2', 'origin': origin,
             'money_unit': 'KRW_million', 'money_unit_policy': 'selected_scope_only; contract_verified; no_FX_conversion; no_company_aggregation',
             'numeric_decimal_places': 9, 'input_sha256': hashes,
             'engine_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'adapter_basis': 'continued_supplied_round1_kgrid_forecast_and_forecast_section; no_model_replacement',
             'fiscal_year_end_month': 12, 'fiscal_basis': 'assumed_December_close',
             'forecast_quarters': [qadd(origin, h) for h in range(1, 11)], 'population': population,
             'unlisted_reference': [], 'backtest': bt, 'companies': forecasts,
             'round1_comparison': comparison, 'retry_queue': retries,
             'aggregation': {'industry_total': None, 'reason': 'holdings/reannouncements excluded; residual cross_company_transactions not reconciled'},
             'note': '금액은 검증된 선택 원장 범위의 조건부 납품 대용치. 재무제표 매출 아님. 구간은 민감도 범위, calibrated=false.'}
    audit = {'schema_version': 'kgrid-audit-2', 'origin': origin, 'population': population,
             'input_sha256': hashes, 'documentation_reconciliation': doc_check, 'contracts': ca,
             'round1_comparison': comparison, 'retry_queue': retries,
             'companies': audits, 'collection_tasks': [t for c in audits for t in c['collection_tasks']],
             'collection_policy': '회사×분기 명시; P0 원문 캐시 우선, 없으면 DART 수집. 이 작업은 수집을 실행하지 않음. 미공시이면 부재 문구 보존.',
             'limit': 'Unit contract and quarter caption candidates supplied; table-to-caption mapping and parser source not independently reconstructed. Missing headers/dates remain unknown.'}
    return panel, audit, reports


def write_json(path, data):
    path.write_text(json.dumps(rounded(data), ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', default=str(Path(__file__).resolve().parents[1]/'input'))
    parser.add_argument('--output-dir', default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    out = Path(args.output_dir)
    if out.resolve() == Path(args.input_dir).resolve() or out.name != 'output':
        raise ValueError('new deliverables must be placed in an output/ directory')
    out.mkdir(parents=True, exist_ok=True)
    panel, audit, reports = build(args.input_dir)
    write_json(out/'forecast_panel.json', panel)
    write_json(out/'kgrid_audit.json', audit)
    write_documents(out, panel, audit, reports)
    print(json.dumps({'population': panel['population'], 'backtest': panel['backtest']['metrics'],
                      'annual_backtest_n': panel['backtest']['annual_metrics']['n'],
                      'collection_tasks': len(audit['collection_tasks'])}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
