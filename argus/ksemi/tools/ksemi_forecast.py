#!/usr/bin/env python3
"""Offline KSEMI ledger delivery proxy. Python 3.9+, standard library only.

Never imports the construction engine. All external evidence is in input/.
Continues the supplied round-2 engine. The supplied parser contract can establish
KRW-million normalization, but never verifies a source caption or accounting scope.
"""
import argparse
import calendar
import collections
import datetime as dt
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import statistics
import sys
sys.dont_write_bytecode = True

SCENARIOS = {'conservative': .25, 'base': .5, 'optimistic': .75}
MIN_FLOWS = 4
MONEY = 'KRW_million'
STAGES = ['포토', '식각', '증착', '이온주입', '열처리/RTP', 'CMP', '세정',
          '계측/검사', '이송/진공', '테스트', '패키징/후공정', '부품소재', '부품세정·재생']
STAGE_KEYS = ['photo', 'etch', 'depo', 'implant', 'thermal', 'cmp', 'clean',
              'metro', 'handling', 'test', 'pkg', 'parts', 'service']
STAGE_NAMES = dict(zip(STAGE_KEYS, STAGES))
REASONS = {
 'report_not_supplied': '후보 명단에만 존재: 보고서 원장·편입 판정 파일 미제공',
 'no_snapshot': '해당 분기 보고서/수주표 없음',
 'backlog_missing': '수주잔고 공란: 0으로 대체하지 않음',
 'unit_unknown': '금액 단위 캡션 미확인',
 'mixed_currency': '복수 통화·통화별 합계 혼재: 환율/행별 통화 없음',
 'normalized_scale_unverified': '원/천원 캡션과 변환된 JSON 숫자의 환산 계약 미제공',
 'aggregate_leaf_overlap': '합계행과 상세행의 중복 가능성',
 'duplicate_row_identity': '같은 이름·기간의 행을 구별할 부문/법인 키 없음',
 'table_reconciliation_failed': '합계행/상세행/수주-납품-잔고 정합성 실패',
 'future_order_in_snapshot': '분기말 이후 수주일이 원장에 포함됨',
 'delivery_period_unverified': '기납품액의 연누적/계약누적/분기 범위 미확인',
 'scope_changed': '인접 분기의 품목 범위 변경',
 'unit_changed': '인접 분기 단위 표기가 달라 환산 연속성 미확인',
 'negative_delivery_delta': '납품 누계 감소: 매출이나 0으로 교정하지 않음',
 'negative_net_order': '순수주 등가 음수: 취소/조정 원인 미확인',
 'insufficient_flow_samples': '적격 순수주·회전 관측 4개 미만',
 'recognition_unverified': '장비에 적용되는 매출인식 문구 미확정',
 'financial_revenue_unverified': '납품표 대용치: 회계매출/연결·별도 범위 미대조',
 'missing_dated_backlog': '금액과 잔고가 확인된 유효 미래 납기행 부족',
 'new_orders_unavailable': '신규수주 가정을 만들 표본 부족',
 'partial_existing_coverage': '일부 납기행만 계산: 잔고 전체 전망 아님',
 'fiscal_month_unknown': '결산월 미확인',
 'missing_observed_quarter': '연간 합산에 필요한 과거 분기 납품액 부족',
 'outside_forecast_horizon': '회계연도 일부가 T+10 범위 밖',
 'stage_tags_absent': '정본 13단계 배정 파일 미제공: 언급 단서만 표시',
 'sales_unit_raw_absent': '매출표 단위 원문/환산 계약 없어 회계매출 금액 미사용',
 'unit_caption_unavailable': '원문 캡션 미확인: 제공된 백만원 정규화 파서 계약에 의존',
 'sales_scope_unverified': '매출표 단위 계약은 있으나 중복·기간·연결/별도 범위 미대조',
 'needs_longer_ledger': '학습·장기/연간 백테스트에 더 긴 적격 원장이 필요함',
 'stage_unassigned': '정본 배정 파일에 회사는 있으나 단계 배정이 비어 있음',
 'source_semantics_required': '원장 길이 외 단위·기간·잔고·품목 범위·정합성 보완 필요',
 'unit_contract_inherited': '단위 근거 JSON 미제공: 2차 보고서의 정규화 설명을 조건부 승계',
}


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def qindex(q):
    if not re.fullmatch(r'\d{4}Q[1-4]', q):
        raise ValueError('invalid quarter: ' + q)
    return int(q[:4]) * 4 + int(q[-1]) - 1


def qadd(q, n):
    y, r = divmod(qindex(q) + n, 4)
    return '%04dQ%d' % (y, r + 1)


def qend(q):
    m = int(q[-1]) * 3
    return dt.date(int(q[:4]), m, calendar.monthrange(int(q[:4]), m)[1])


def date(s):
    m = re.fullmatch(r'\s*(\d{4})[-.](\d{1,2})[-.](\d{1,2})\.?\s*', s or '')
    if not m:
        return None
    try:
        return dt.date(*map(int, m.groups()))
    except ValueError:
        return None


def quantile(xs, p):
    if not xs:
        return None
    ys = sorted(xs)
    k = (len(ys)-1)*p
    a = int(k)
    return ys[a] + (ys[min(a+1, len(ys)-1)]-ys[a])*(k-a)


def sum_complete(xs):
    return sum(xs) if all(num(x) for x in xs) else None


def interval(lo=None, hi=None, method='observed_parameter_sensitivity'):
    return {'lower': lo, 'upper': hi, 'method': method,
            'nominal_level': None, 'calibrated': False}


def canonical(s):
    return re.sub(r'\s+', '', s or '')


def aggregate_name(s):
    return bool(re.search(r'합계|총계|소계|수주잔량계|^계$', canonical(s)))


def unit_audit(o, contract=None):
    raw = o.get('unit_raw')
    text = str(raw or '')
    if re.search(r'USD|K\$|US\$|CNY|RMB|EUR|JPY|달러|위안|엔화', text, re.I):
        code, currency = 'mixed_currency', None
    elif not o.get('unit_seen'):
        code, currency = 'unit_unknown', None
    elif contract and (not raw or re.sub(r'[\s,/]|개|대', '', text) in
                       ('십억원', '백만원', '억원', '천원', '만원', '원')):
        code, currency = None, 'KRW'
    elif not raw:
        code, currency = 'unit_unknown', None
    elif re.sub(r'[\s,/]|개|대', '', text) == '백만원':
        code, currency = None, 'KRW'
    elif '원' in text:
        code, currency = 'normalized_scale_unverified', 'KRW'
    else:
        code, currency = 'unit_unknown', None
    return {'raw_caption': raw, 'unit_seen': bool(o.get('unit_seen')),
            'verified': code is None, 'currency': currency,
            'money_unit': MONEY if code is None else None,
            'scale_from_input': 1 if code is None else None,
            'reason_code': code,
            'source_caption_verified': False,
            'status_codes': (['unit_caption_unavailable'] +
                (['unit_contract_inherited'] if contract.get('evidence_tier') == 'prior_report_statement' else []))
                if code is None and contract else [],
            'parser_contract': contract,
            'basis': ('normalization contract (see evidence tier); input already KRW million; scale 1, never rescale again'
                      if code is None and contract else
                      'parsed caption 백만원; raw and normalized million scale coincide' if code is None
                      else 'no rescaling of transformed JSON; no magnitude inference')}


def fiscal(c, origin):
    months = set()
    evidence = []
    for q, s in c.get('quarters', {}).items():
        if q > origin:
            continue
        t = s.get('title', '')
        if '사업보고서' in t:
            m = re.search(r'\((\d{4})\.(\d{2})\)', t)
            if m:
                months.add(int(m[2])); evidence.append({'quarter': q, 'title': t})
    month = next(iter(months)) if len(months) == 1 else None
    return {'month': month, 'basis': 'annual_report_title_month; fiscal year named by ending year',
            'evidence': evidence, 'assumption': '결산월이 전망 기간에 유지됨; 변경 공시 미제공'}


def recognition(c, origin):
    b = c.get('basis') or {}
    quotes = b.get('bases', []) if b.get('quarter', '9999Q4') <= origin else []
    accepted = []
    for v in quotes:
        t = v.get('quote', '')
        if (re.search(r'설치\s*완료|검수가 완료', t) and
                re.search(r'수익.*인식|인식.*수익', t) and '무상' not in t):
            accepted.append({'basis': '설치완료/SAT', 'quote': t})
        elif (re.search(r'인도.*시점.*수익.*인식|인도하는 시점에 수익', t) and
              not re.search(r'운송|기간에 걸쳐|5단계', t)):
            accepted.append({'basis': '인도', 'quote': t})
        elif '정밀세정 및 재생' in t and '기간에 걸쳐' in t:
            accepted.append({'basis': '진행기준(부품세정·재생 용역)', 'quote': t})
        elif '일부 계약' in t and '적용하였습니다' in t:
            accepted.append({'basis': '진행기준(일부 계약만)', 'quote': t})
    return {'source_primary': b.get('primary') if quotes else None,
            'source_rcp': b.get('rcpNo') if quotes else None,
            'source_quarter': b.get('quarter') if quotes else None,
            'source_quotes': quotes, 'accepted': accepted,
            'equipment_basis_verified': any(x['basis'] in ('설치완료/SAT', '인도') for x in accepted),
            'reason': None if accepted else '원문 인용이 없거나 일반 정책/운송·부품 용역/조건문/표 일부로 장비 인식을 확정 못 함',
            'timing_use': '설치/검수와 납기 사이 실측 시차 없음; 인식기준을 임의 분기 지연으로 변환하지 않음'}


def audit_snapshot(q, s, contract=None):
    o = s.get('orders') or {}; rows = o.get('items', [])
    unit = unit_audit(o, contract); reasons = []
    if not s or not s.get('rcpNo'):
        reasons.append('no_snapshot')
    if not num(o.get('backlog')):
        reasons.append('backlog_missing')
    if unit['reason_code']:
        reasons.append(unit['reason_code'])
    aggs = [i for i, row in enumerate(rows) if aggregate_name(row.get('nm'))]
    keys = [(canonical(i.get('nm')), i.get('sd'), i.get('ed')) for i in rows]
    duplicates = len(keys)-len(set(keys))
    if aggs:
        reasons.append('aggregate_leaf_overlap')
    if duplicates:
        reasons.append('duplicate_row_identity')
    discrepancies = {}
    for top, cell in [('order_amt', 'amt'), ('delivered', 'cmp'), ('backlog', 'bal')]:
        vals = [r.get(cell) for r in rows]
        present = [v for v in vals if num(v)]
        if num(o.get(top)):
            delta = sum(present)-o[top]
            discrepancies[top] = {'provided': o[top], 'sum_present': sum(present),
                                 'missing_cells': len(vals)-len(present), 'difference': delta}
            if len(present) == len(vals) and abs(delta) > max(2, abs(o[top])*1e-6):
                reasons.append('table_reconciliation_failed')
    a, d, b = (o.get(k) for k in ('order_amt', 'delivered', 'backlog'))
    identity = a-d-b if all(num(x) for x in (a, d, b)) else None
    if num(identity) and abs(identity) > max(2, abs(a)*1e-6):
        reasons.append('table_reconciliation_failed')
    if o.get('recon'):
        reasons.append('table_reconciliation_failed')
    future = [i for i, r in enumerate(rows) if date(r.get('sd')) and date(r['sd']) > qend(q)]
    if future:
        reasons.append('future_order_in_snapshot')
    current_dates = [date(r.get('ed')) for r in rows]
    sales = s.get('sales') or {}
    sales_rows = sales.get('items', [])
    sales_keys = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in sales_rows]
    sales_audit = {'row_count': len(sales_rows),
        'aggregate_rows': [i for i, r in enumerate(sales_rows) if any(aggregate_name(t) for t in r.get('labels', []))],
        'exact_duplicate_rows': len(sales_keys)-len(set(sales_keys)),
        'reported_total': sales.get('total'), 'period_label': sales.get('period_label'),
        'period_labels_in_rows': sorted(set(str(r.get('period')) for r in sales_rows)),
        'unit_seen': sales.get('unit_seen'), 'unit_raw': None, 'verified': False,
        'normalization_verified': bool(contract and sales.get('unit_seen')),
        'unit_status_codes': ['unit_caption_unavailable'] if contract and sales.get('unit_seen') else [],
        'parser_contract': contract,
        'upstream_recon': sales.get('recon'),
        'sum_policy': 'not summed: product subtotals, company totals and duplicate tables can overlap',
        'reason_code': 'sales_scope_unverified' if contract else 'sales_unit_raw_absent'}
    return {'quarter': q, 'rcpNo': s.get('rcpNo'), 'title': s.get('title'), 'node': s.get('node'),
            'order_row_count': len(rows), 'sales_row_count': len((s.get('sales') or {}).get('items', [])),
            'aggregate_rows': aggs, 'duplicate_rows': duplicates, 'grain': o.get('grain'),
            'valid_start_dates': sum(date(r.get('sd')) is not None for r in rows),
            'valid_end_dates': sum(d is not None for d in current_dates),
            'overdue_positive_backlog_rows': [i for i, d in enumerate(current_dates)
                if d and d <= qend(q) and num(rows[i].get('bal')) and rows[i]['bal'] > 0],
            'future_order_rows': future, 'unit': unit, 'reconciliation': discrepancies,
            'identity_A_minus_D_minus_B': identity, 'upstream_recon': o.get('recon'),
            'sales_unit_verified': False, 'sales_audit': sales_audit,
            'order_row_labels': [r.get('nm') for r in rows], 'reason_codes': sorted(set(reasons)),
            'raw_orders_summary': {k: o.get(k) for k in ('order_amt', 'delivered', 'backlog')},
            'progress_ratio': d/a if num(a) and a > 0 and num(d) and 0 <= d <= a and
                 unit['reason_code'] != 'mixed_currency' and not aggs and not duplicates and
                 num(identity) and abs(identity) <= max(2, abs(a)*1e-6) else None,
            'progress_ratio_basis': 'reported D/A within one snapshot; not physical process progress'}


def explicit_ytd(q, o):
    """Date labels, not numeric shape or comparison with an unverified sales table."""
    rows = o.get('items', [])
    y = q[:4]
    if not rows:
        return False
    for r in rows:
        sd, ed = canonical(r.get('sd')), canonical(r.get('ed'))
        suffix = {'1': '1분기', '2': '반기', '3': '3분기', '4': ''}[q[-1]]
        period = sd == y+'년'+suffix
        period |= bool(re.match(y+r'\.0?1\.0?1~', sd) and date(sd.split('~')[-1]) == qend(q))
        # A Jan-1 range in ed is a delivery deadline range, not proof of YTD.
        # Do not infer cumulative delivery periods from resets or sales magnitudes.
        if not period:
            return False
    return True


def scope_signature(o):
    return sorted(canonical(i.get('nm')) for i in o.get('items', []))


def flow_history(c, origin):
    snapshots = {q: s for q, s in c.get('quarters', {}).items() if q <= origin}
    audits = {q: audit_snapshot(q, s, c.get('_unit_contract')) for q, s in snapshots.items()}
    fy = fiscal(c, origin)['month']; actual = {}; flows = []; rejected = []
    for q in sorted(snapshots):
        s = snapshots[q]; o = s.get('orders') or {}; qa = audits[q]
        reasons = list(qa['reason_codes'])
        if fy != 12 or not explicit_ytd(q, o):
            reasons.append('delivery_period_unverified')
        prevq = qadd(q, -1); prev = snapshots.get(prevq, {}).get('orders') or {}
        d = None
        if num(o.get('delivered')):
            if q[-1] == '1':
                d = o['delivered']
            elif (num(prev.get('delivered')) and explicit_ytd(prevq, prev) and
                  not audits.get(prevq, {}).get('reason_codes') and
                  scope_signature(prev) == scope_signature(o)):
                d = o['delivered']-prev['delivered']
        if not num(d):
            reasons.append('delivery_period_unverified')
        elif d < 0:
            reasons.append('negative_delivery_delta')
        actual[q] = d if not reasons else None
        if not prev or not num(prev.get('backlog')):
            reasons.append('backlog_missing')
        elif audits[prevq]['reason_codes']:
            reasons.extend(audits[prevq]['reason_codes'])
        if prev and scope_signature(prev) != scope_signature(o):
            reasons.append('scope_changed')
        if (prev and canonical(prev.get('unit_raw')) != canonical(o.get('unit_raw')) and
                not (c.get('_unit_contract') and audits[prevq]['unit']['verified'] and qa['unit']['verified'])):
            reasons.append('unit_changed')
        new = o['backlog']-prev['backlog']+d if not reasons else None
        if num(new) and new < 0:
            reasons.append('negative_net_order')
        if not reasons and num(d) and d+o['backlog'] > 0:
            flows.append({'quarter': q, 'from': prevq, 'delivery': d,
                          'previous_backlog': prev['backlog'], 'backlog': o['backlog'],
                          'net_orders': new, 'hazard': d/(d+o['backlog']),
                          'turnover_D_over_previous_B': d/prev['backlog'] if prev['backlog'] > 0 else None,
                          'rcpNo': s.get('rcpNo')})
        else:
            rejected.append({'quarter': q, 'reason_codes': sorted(set(reasons)),
                             'raw_delivery_delta': d, 'raw_net_orders': new})
    return flows, actual, rejected


def project_pool(b, h, order, count=10):
    """Orders arrive at quarter start; equal within-quarter delivery hazard.
    h = D/(D+B_end), an effective pooled flow proxy, NOT measured order aging.
    """
    old, new_b = b, 0.0
    result = []
    for _ in range(count):
        e, n = old*h, (new_b+order)*h
        old -= e; new_b = new_b+order-n
        result.append({'value': e+n, 'existing_backlog_revenue': e,
                       'new_order_revenue': n, 'new_order_backlog': new_b,
                       'existing_backlog_remaining': old, 'new_orders': order})
    return result


def schedule(c, origin):
    s = c.get('quarters', {}).get(origin, {}); o = s.get('orders') or {}
    qa = audit_snapshot(origin, s, c.get('_unit_contract')); eligible = []; rejected = []
    fatal = {'aggregate_leaf_overlap', 'duplicate_row_identity', 'table_reconciliation_failed', 'mixed_currency'}
    if fatal.intersection(qa['reason_codes']):
        return {'rows': [], 'rejected': [], 'total': None, 'money': False,
                'reason_codes': sorted(fatal.intersection(qa['reason_codes']))}
    for i, r in enumerate(o.get('items', [])):
        sd, ed, b = date(r.get('sd')), date(r.get('ed')), r.get('bal')
        if num(b) and b == 0:
            continue
        why = []
        if not num(b) or b < 0: why.append('row_backlog_missing')
        if not ed: why.append('end_date_missing_or_range')
        elif ed <= qend(origin): why.append('overdue_not_assumed_completed')
        if sd and sd > qend(origin): why.append('post_origin_order')
        if why:
            rejected.append({'row': i, 'name': r.get('nm'), 'reasons': why})
        else:
            eligible.append({'row': i, 'name': r.get('nm'), 'backlog_input_scale': b,
                             'quarter': '%dQ%d' % (ed.year, (ed.month-1)//3+1), 'end': ed.isoformat()})
    return {'rows': eligible, 'rejected': rejected, 'total': o.get('backlog'),
            'money': qa['unit']['verified'],
            'ratio_currency_verified': qa['unit']['currency'] == 'KRW', 'reason_codes': []}


def fy_quarters(year, month):
    if month not in (3, 6, 9, 12):
        return []
    endq = '%dQ%d' % (year, month//3)
    return [qadd(endq, n) for n in (-3, -2, -1, 0)]


def annualize(rows, actual, origin, month, years):
    byq = {r['quarter']: r for r in rows}; result = []
    for year in years:
        qs = fy_quarters(year, month); oq = [q for q in qs if q <= origin]
        fq = [q for q in qs if q > origin]
        codes = []
        if not qs: codes.append('fiscal_month_unknown')
        if any(q not in byq for q in fq): codes.append('outside_forecast_horizon')
        observed = sum_complete([actual.get(q) for q in oq])
        if observed is None: codes.append('missing_observed_quarter')
        future = [byq.get(q, {}) for q in fq]
        total = sum_complete([observed]+[r.get('value') for r in future]) if qs else None
        if any(r.get('value') is None for r in future): codes.append('new_orders_unavailable')
        fields = {k: sum_complete([r.get(k) for r in future]) if qs else None for k in
                  ('existing_backlog_revenue', 'new_order_revenue', 'covered_sites_partial_revenue')}
        bounds = {}
        for key in ('interval', 'partial_existing_interval', 'new_order_interval', 'covered_sites_partial_interval'):
            lo = sum_complete([r.get(key, {}).get('lower') for r in future]) if qs else None
            hi = sum_complete([r.get(key, {}).get('upper') for r in future]) if qs else None
            if key == 'interval':
                lo = lo+observed if num(lo) and num(observed) and total is not None else None
                hi = hi+observed if num(hi) and num(observed) and total is not None else None
            bounds[key] = interval(lo, hi, 'sum_of_quarter_sensitivity_bounds')
        result.append(dict(fiscal_year=year, value=total, observed_revenue=observed if qs else None,
            observed_revenue_basis='YTD order-table delivery difference; not financial revenue',
            observed_quarters_available=sum(num(actual.get(q)) for q in oq),
            observed_quarters_required=len(oq), future_quarters=len(fq), complete=total is not None,
            quarters=qs, reason=';'.join(codes) or None, reason_codes=codes,
            component_scope='future_quarters_only; observed portion separate', **fields, **bounds))
    return result


def forecast_company(c, origin='2026Q2', count=10):
    flows, actual, rejected = flow_history(c, origin)
    current = audit_snapshot(origin, c.get('quarters', {}).get(origin, {}), c.get('_unit_contract'))
    f = fiscal(c, origin); b = current['raw_orders_summary']['backlog']
    current_orders = c.get('quarters', {}).get(origin, {}).get('orders') or {}
    current_scope = scope_signature(current_orders)
    comparable = []
    for flow in flows:
        historical_orders = c['quarters'][flow['quarter']].get('orders') or {}
        if (scope_signature(historical_orders) == current_scope and
                (c.get('_unit_contract') or
                 canonical(historical_orders.get('unit_raw')) == canonical(current_orders.get('unit_raw')))):
            comparable.append(flow)
        else:
            rejected.append({'quarter': flow['quarter'], 'reason_codes': ['scope_changed'],
                             'basis': 'training perimeter differs from current snapshot'})
    flows = comparable
    full = (len(flows) >= MIN_FLOWS and not current['reason_codes'] and num(b)
            and explicit_ytd(origin, current_orders) and f['month'] == 12)
    sched = schedule(c, origin); covered = sum(r['backlog_input_scale'] for r in sched['rows'])
    has_schedule = bool(sched['rows']) and sched.get('ratio_currency_verified', False) and num(sched['total']) and sched['total'] > 0 and covered <= sched['total']+2
    reasons = list(current['reason_codes'])
    if len(flows) < MIN_FLOWS: reasons.append('insufficient_flow_samples')
    if not explicit_ytd(origin, c.get('quarters', {}).get(origin, {}).get('orders') or {}):
        reasons.append('delivery_period_unverified')
    rb = recognition(c, origin)
    if not rb['equipment_basis_verified']: reasons.append('recognition_unverified')
    reasons += ['financial_revenue_unverified',
                'sales_scope_unverified' if c.get('_unit_contract') else 'sales_unit_raw_absent']
    reasons += current['unit']['status_codes']
    if not full:
        reasons.append('new_orders_unavailable')
        if not has_schedule: reasons.append('missing_dated_backlog')
        else: reasons.append('partial_existing_coverage')
    reasons = sorted(set(reasons))
    status = 'full' if full else 'partial' if has_schedule else 'unavailable'
    scenarios = {}; normalized = {}
    orders = [x['net_orders'] for x in flows]; hazards = [x['hazard'] for x in flows]
    h = quantile(hazards, .5) if full else None
    years = list(range(int(origin[:4]), int(origin[:4])+3))
    for name, p in SCENARIOS.items():
        order = quantile(orders, p) if full else None
        nominal = project_pool(b, h, order, count) if full else []
        alternatives = [project_pool(b, rate, amt, count) for rate, amt in itertools.product(
            sorted(set([quantile(hazards, .1), h, quantile(hazards, .9)])),
            sorted(set([quantile(orders, .1), order, quantile(orders, .9)])))] if full else []
        quarterly = []; normalized_rows = []
        for i in range(count):
            q = qadd(origin, i+1)
            part = sum(r['backlog_input_scale'] for r in sched['rows'] if r['quarter'] == q) if has_schedule else None
            n = nominal[i] if full else {'value': None, 'existing_backlog_revenue': None,
                'new_order_revenue': None, 'new_order_backlog': None, 'new_orders': None,
                'existing_backlog_remaining': None}
            row = dict(quarter=q, horizon=i+1, **n)
            row['covered_sites_partial_revenue'] = part if has_schedule and sched['money'] and not full else None
            for key, component in [('interval', 'value'), ('partial_existing_interval', 'existing_backlog_revenue'),
                                   ('new_order_interval', 'new_order_revenue')]:
                vals = [a[i][component] for a in alternatives]
                row[key] = interval(min(vals), max(vals)) if vals else interval()
            row['covered_sites_partial_interval'] = interval()  # No measured due-date/SAT error distribution.
            row.update(status=status, reason_codes=reasons,
                       existing_backlog_method='pooled_delivery_hazard' if full else 'contract_due_quarter_partial')
            quarterly.append(row)
            normalized_rows.append({'quarter': q, 'horizon': i+1,
                'covered_backlog_fraction_due': part/sched['total'] if has_schedule else None,
                'value': None, 'new_order_revenue': None, 'interval': interval(),
                'reason_codes': reasons})
        scenarios[name] = {'assumptions': {'new_orders_per_quarter_deseasonalized': order,
            'new_orders_per_quarter': order, 'seasonality_adjusted': False,
            'legacy_field_note': 'deseasonalized key retained for compatibility; no seasonal adjustment performed',
            'money_unit': MONEY if full else None, 'order_quantile': p,
            'delivery_hazard': h, 'timing_policy': 'same empirical hazard in all scenarios; new order quantile varies',
            'new_order_recognition': 'quarter-start pooled orders; delivery proxy, not SAT revenue',
            'missing_reasons': [] if full else reasons}, 'quarterly': quarterly,
            'annual': annualize(quarterly, actual, origin, f['month'], years)}
        normalized[name] = {'basis': 'origin disclosed backlog = 1; partial scheduled delivery share only',
            'money_unit': None, 'quarterly': normalized_rows,
            'annual': [{'fiscal_year': y, 'covered_future_backlog_fraction_due':
                        sum_complete([r['covered_backlog_fraction_due'] for r in normalized_rows
                            if r['quarter'] in fy_quarters(y, f['month'])]) if has_schedule and f['month'] else None,
                        'complete': False, 'calibrated': False} for y in years]}
    result = {'company_id': c['stock'], 'stock': c['stock'], 'company_name': c['name'],
        'audited_company_name': c['name'], 'source': c.get('source'), 'origin': origin,
        'panel_present': True, 'listed': True, 'status': status,
        'compatibility_status': {'full': 'full_ledger_estimate', 'partial': 'partial_amount_estimate',
                                 'unavailable': 'unavailable'}[status],
        'grade': 'conditional_delivery_proxy' if full else status,
        'audited_grade': status, 'audit_can': {'matrix': 'yes' if full else 'partial' if has_schedule else 'no',
                                             'trace': 'parsed_input_only', 'backtest': 'pending'},
        'audit_blockers': [REASONS.get(x, x) for x in reasons], 'reason_codes': reasons,
        'money_unit': MONEY if current['unit']['verified'] else None,
        'scope': 'provided order-table perimeter; may include display, solar, valves and parts',
        'financial_statement_revenue': False, 'fiscal_year_end_month': f['month'],
        'fiscal_basis': f['basis'], 'fiscal_evidence': f,
        'unit_audit': {'verified_at_origin': current['unit']['verified'],
                       'status_codes': current['unit']['status_codes'],
                       'quarters': {q: audit_snapshot(q, s, c.get('_unit_contract'))['unit'] for q, s in c.get('quarters', {}).items() if q <= origin}},
        'coverage': {'current_rows': current['order_row_count'], 'full_existing_coverage': full,
                     'origin_site_total_backlog': b if current['unit']['verified'] else None,
                     'modeled_site_backlog': b if full else covered if has_schedule and sched['money'] else None,
                     'covered_fraction': 1 if full else covered/sched['total'] if has_schedule else None,
                     'existing_backlog_method': 'pooled_delivery_hazard' if full else 'contract_due_quarter_partial'},
        'evidence': {'flows': flows, 'flow_rejections': rejected, 'order_basis': 'B_end - B_previous + quarterly delivery; net-order equivalent, cancellations/revisions included',
                     'flow_minimum': MIN_FLOWS, 'delivery_period_basis': 'explicit year/YTD date range in order rows only',
                     'seasonality': {'enabled': False, 'reason': 'no independently validated seasonal model; raw flow quantiles'},
                     'capex_link': {'enabled': False, 'reason': 'no customer CAPEX series or estimated elasticity in input'},
                     'schedule': sched, 'recognition': rb, 'horizon_validation': {'status':'backtest_not_run'}},
        'scenarios': scenarios, 'normalized_forecast': normalized, 'actual_revenue_proxy': actual,
        'aggregate_forecast': {'site_id': '__order_table__', 'site_name': 'provided order-table scope',
            'method': 'pooled_delivery_hazard' if full else None,
            'model': {'origin': origin, 'history_n': len(flows), 'burn_rate': h,
                       'reason': 'empirical pooled delivery intensity; no construction S curve'},
            'origin_backlog': b if current['unit']['verified'] else None,
            'origin_amount': current['raw_orders_summary']['order_amt'] if current['unit']['verified'] else None,
            'origin_progress': current['progress_ratio'],
            'quarterly': [{'quarter': r['quarter'], 'horizon': r['horizon'], 'progress': None,
                'revenue': r['existing_backlog_revenue'], 'revenue_interval': r['partial_existing_interval']}
                for r in scenarios['base']['quarterly']]}}
    return result


def metrics(rows):
    if not rows:
        return {'n': 0, 'mae': None, 'wape': None, 'bias': None, 'naive_mae': None,
                'sensitivity_coverage': None}
    n = len(rows); den = sum(abs(r['actual']) for r in rows)
    return {'n': n, 'mae': sum(abs(r['prediction']-r['actual']) for r in rows)/n,
            'wape': sum(abs(r['prediction']-r['actual']) for r in rows)/den if den else None,
            'bias': sum(r['prediction']-r['actual'] for r in rows)/n,
            'naive_mae': sum(abs(r['naive']-r['actual']) for r in rows)/n,
            'sensitivity_coverage': sum(r['lower'] <= r['actual'] <= r['upper'] for r in rows)/n}


def annual_metrics(rows):
    return dict(metrics(rows),
        unique_company_fiscal_years=len({(r['company_id'], r['fiscal_year']) for r in rows}),
        by_horizon_year={str(h): metrics([r for r in rows if r['horizon_year'] == h]) for h in (1, 2)},
        by_company={stock: metrics([r for r in rows if r['company_id'] == stock])
                    for stock in sorted({r['company_id'] for r in rows})},
        by_fiscal_year={str(y): metrics([r for r in rows if r['fiscal_year'] == y])
                        for y in sorted({r['fiscal_year'] for r in rows})})


def backtest(companies, quarters):
    scenario_rows = {name: [] for name in SCENARIOS}
    annual_rows = {name: [] for name in SCENARIOS}
    exclusions = collections.Counter()
    for c in companies:
        _, actual, _ = flow_history(c, quarters[-1])
        for origin in quarters[:-1]:
            truncated = dict(c, quarters={q: s for q, s in c.get('quarters', {}).items() if q <= origin})
            pred = forecast_company(truncated, origin)
            history = pred['evidence']['flows']
            for horizon in range(1, 11):
                q = qadd(origin, horizon)
                if q not in quarters:
                    exclusions['target_not_observed'] += 1; continue
                if pred['status'] != 'full':
                    exclusions['prediction_unavailable'] += 1; continue
                if not num(actual.get(q)):
                    exclusions['actual_delivery_unverified'] += 1; continue
                if scope_signature(c['quarters'][q].get('orders') or {}) != scope_signature(c['quarters'][origin].get('orders') or {}):
                    exclusions['target_scope_changed'] += 1; continue
                for name in SCENARIOS:
                    row = pred['scenarios'][name]['quarterly'][horizon-1]
                    scenario_rows[name].append({'company_id': c['stock'], 'origin': origin, 'quarter': q,
                        'horizon': horizon, 'prediction': row['value'], 'actual': actual[q],
                        'naive': history[-1]['delivery'], 'lower': row['interval']['lower'],
                        'upper': row['interval']['upper'], 'calibrated': False, 'nominal_level': None,
                        'training_quarters': [x['quarter'] for x in history]})
            if pred['status'] != 'full':
                continue
            for year in range(int(origin[:4]), int(origin[:4])+3):
                qs = fy_quarters(year, pred['fiscal_year_end_month'])
                if not qs or not all(q > origin and num(actual.get(q)) for q in qs):
                    continue
                scope = scope_signature(c['quarters'][origin].get('orders') or {})
                if any(scope_signature(c['quarters'][q].get('orders') or {}) != scope for q in qs):
                    continue
                for name in SCENARIOS:
                    byq = {r['quarter']: r for r in pred['scenarios'][name]['quarterly']}
                    if any(q not in byq for q in qs):
                        continue
                    annual_rows[name].append({'company_id': c['stock'], 'origin': origin,
                        'fiscal_year': year, 'horizon_year': year-int(origin[:4]), 'quarters': qs,
                        'prediction': sum(byq[q]['value'] for q in qs), 'actual': sum(actual[q] for q in qs),
                        'naive': 4*history[-1]['delivery'],
                        'lower': sum(byq[q]['interval']['lower'] for q in qs),
                        'upper': sum(byq[q]['interval']['upper'] for q in qs),
                        'training_quarters': [x['quarter'] for x in history],
                        'first_quarter_horizon': qindex(qs[0])-qindex(origin),
                        'last_quarter_horizon': qindex(qs[-1])-qindex(origin),
                        'calibrated': False, 'nominal_level': None})
    scored = scenario_rows['base']; annual = annual_rows['base']
    return {'scope': 'total order-table delivery proxy including new orders; not financial revenue',
            'money_unit': MONEY, 'calibrated': False, 'small_sample': True,
            'vintage': 'pseudo out-of-sample: revised current dataset, no historical publication vintages',
            'leakage_policy': 'predictor sees quarters <= origin; metadata does not fit parameters; not publication-date PIT',
            'unique_company_target_quarters': len({(r['company_id'], r['quarter']) for r in scored}),
            'scored_origins': sorted({r['origin'] for r in scored}),
            'independence_warning': 'overlapping horizons reuse actuals; scored rows are not independent samples',
            'overall': metrics(scored),
            't1_t8': metrics([r for r in scored if r['horizon'] <= 8]),
            'by_horizon': {str(h): metrics([r for r in scored if r['horizon'] == h]) for h in range(1, 11)},
            'annual': dict(annual_metrics(annual), reason=None if annual else 'no_eligible_fully_future_fiscal_year',
                scoring_policy='four fully future observed fiscal quarters; no synthetic annual actuals', rows=annual),
            'by_scenario': {name: {'overall': metrics(rows), 'rows': rows,
                'by_horizon': {str(h): metrics([r for r in rows if r['horizon'] == h]) for h in range(1, 11)},
                'annual': dict(annual_metrics(annual_rows[name]), rows=annual_rows[name])}
                for name, rows in scenario_rows.items()},
            'by_company': {c['stock']: metrics([r for r in scored if r['company_id'] == c['stock']]) for c in companies},
            'exclusions': dict(exclusions), 'rows': scored}


def stage_hints(u):
    # Lexical evidence, deliberately not a substitute for the missing authoritative tags.
    text = ' '.join([u.get('product', ''), str(u.get('why', {}).get('seed', ''))])
    words = {'포토': r'노광|포토|마스크', '식각': r'식각|에칭', '증착': r'증착|CVD|ALD',
             '이온주입': r'이온주입', '열처리/RTP': r'어닐링|열처리|RTP', 'CMP': r'CMP',
             '세정': r'세정|클리닝', '계측/검사': r'계측|검사|현미경', '이송/진공': r'이송|진공',
             '테스트': r'Test|테스트|테스터|Probe|프로브|Socket|소켓',
             '패키징/후공정': r'본더|Bonder|후공정|패키징|Reflow',
             '부품소재': r'부품|세라믹|정전척|전극|쿼츠', '부품세정·재생': r'부품 세정|정밀세정|재생'}
    return {'authoritative_tags': None, 'mention_hints': [s for s, p in words.items() if re.search(p, text, re.I)],
            'evidence_text': text, 'role': '공정서비스' if '공정 서비스' in text else '원문 제품 설명 참조',
            'reason': 'stage_tags_absent', 'used_for_model': False}


def contract_exposure(rows):
    superseded = {r.get('supersedes') for r in rows if isinstance(r.get('supersedes'), str)}
    seen = set(); active = []; duplicate = 0
    for r in rows:
        if r.get('rcp') in superseded or r.get('rcp') in seen:
            duplicate += 1; continue
        seen.add(r.get('rcp')); active.append(r)
    valid = []
    for r in active:
        a, n = r.get('amt_mkrw'), r.get('amt_native')
        if (r.get('currency') == 'KRW' and r.get('unit_seen') and r.get('amt_unit') == '원' and
                num(a) and num(n) and a >= 0 and abs(a-n/1e6) <= max(.001, abs(a)*1e-9) and r.get('event') != '해지'):
            valid.append(r)
    cn = lambda r: bool(re.search(r'중국|中國|China|PRC|시안|우시|청두|다롄', r.get('region', ''), re.I))
    total = sum(r['amt_mkrw'] for r in valid); ctotal = sum(r['amt_mkrw'] for r in valid if cn(r))
    return {'scope': 'supplied current-vintage cumulative disclosed contracts; not sales share or order intake',
        'not_used_for_forecast': True, 'rows': len(rows), 'after_rcp_dedup': len(active),
        'dropped_superseded_or_duplicate': duplicate, 'verified_amount_rows': len(valid),
        'china_region_rows': sum(cn(r) for r in active), 'unknown_amount_rows': len(active)-len(valid),
        'amount_mkrw': total if valid else None, 'china_amount_mkrw': ctotal if valid else None,
        'china_contract_amount_share': ctotal/total if total > 0 else None,
        'unknown_region_amount_mkrw': sum(r['amt_mkrw'] for r in valid if not r.get('region')),
        'named_customers': sorted(set(r.get('party') for r in active if r.get('party') and not r.get('party_anon'))),
        'anonymous_rows': sum(bool(r.get('party_anon')) for r in active),
        'evidence': [{'rcp': r.get('rcp'), 'filed': r.get('filed'), 'region': r.get('region'),
                      'region_cn': cn(r), 'amount_mkrw': r['amt_mkrw']} for r in valid]}


def customer_info(c):
    cus = c.get('customers') or {}; den = (c.get('segment_total') or {}).get('total')
    usable = cus.get('period') == '당기' and num(den) and den > 0
    rows = []
    for r in cus.get('rows', []):
        a = r.get('amount'); share = a/den if usable and num(a) and 0 <= a <= den else None
        label = r.get('label', '')
        anonymous = bool(r.get('anonymous')) or bool(re.search(r'^[A-Z](?:\s|사|업체|고객)', label))
        rows.append({'label': label, 'anonymous': anonymous, 'share': share})
    return {'quarter': cus.get('quarter'), 'rcpNo': cus.get('rcpNo'), 'period': cus.get('period'),
            'rows': rows, 'top_share': max([r['share'] for r in rows if r['share'] is not None], default=None),
            'basis': 'same current-year customer note / segment denominator in parsed input; no identity inference',
            'currency_amounts_not_republished': True, 'not_used_for_forecast': True}


def collect_tasks(c, audit, origin):
    """Local rerun manifest only. No collection or job execution."""
    tasks = []
    def add(q, code, priority, detail):
        tasks.append({'company_id': c['stock'], 'company_name': c['name'], 'quarter': q,
            'rcpNo': c.get('quarters', {}).get(q, {}).get('rcpNo'),
            'section': 'II-4 수주상황·매출실적 / III 주석', 'reason_code': code,
            'priority': priority, 'request': detail,
            'completion_rule': '실제 수집 원장의 단위·기간·범위·정정 이력을 확인; 미공시와 공란은 유지'})
    if not c.get('quarters'):
        add(origin, 'report_not_supplied', 'P1', '편입 판정 파일 확인 후 원장 필요 여부 결정')
        return tasks
    for qa in audit['quarters']:
        if qa['reason_codes'] or not qa['sales_audit']['verified']:
            add(qa['quarter'], 'source_semantics_required', 'P1',
                '금액 정규화 계약 수용 완료. 원문 캡션·기간·범위·행 중복 대조 필요: '+','.join(qa['reason_codes']))
    for q in [qadd('2021Q4', n) for n in range(19)]:
        if not c.get('quarters', {}).get(q, {}).get('rcpNo'):
            add(q, 'needs_longer_ledger', 'P2',
                '진행 중인 2021Q4~2026Q2 원장 확장 수신 후 재감사; 자동 추정 승격 금지')
    return tasks


def process_info(u, tag):
    hints = stage_hints(u)
    if tag is None:
        return hints
    keys = [x['key'] for x in tag['stages']]
    if any(k not in STAGE_NAMES for k in keys):
        raise ValueError('unknown authoritative stage key')
    return dict(hints, authoritative_tags=tag['stages'], stage_keys=keys,
        stage_names=[STAGE_NAMES[k] for k in keys], primary=tag.get('primary'),
        primary_name=STAGE_NAMES.get(tag.get('primary')), front_back=tag.get('front_back'),
        evidence_text=tag.get('evidence'), evidence_source=tag.get('evidence_source'),
        source_file='ksemi_stage_tags.json', reason=None if keys else 'stage_unassigned',
        limitation='정본 배정 그대로 표시; 산업 일반·겸업 문구 혼재. 품목 매출 비중·단계별 속도를 뜻하지 않음')


def memory_info(row):
    return {'source_file': 'ksemi_exposure.json', 'row': row,
        'verdict': row.get('verdict') if row else '미제공', 'revenue_share': None,
        'not_used_for_forecast': True,
        'basis': 'II-2·II-4 낱말; 미확인은 비노출이 아니며 매출 비중으로 변환하지 않음'}


def attach_peers(panels, peer_data):
    indexed = {p['company_id']: p for p in panels}
    edges = []; seen = set()
    for source in peer_data['rows']:
        for m in source['mentions']:
            key = (source['stock'], m['stock'], m['kind'])
            if key in seen: continue
            seen.add(key)
            edges.append(dict(m, source_stock=source['stock'], target_stock=m['stock'],
                              rcpNo=source.get('rcpNo')))
    family = collections.defaultdict(set)
    for e in edges:
        if e['kind'] == '계열':
            family[e['source_stock']].add(e['target_stock'])
            family[e['target_stock']].add(e['source_stock'])
    def affiliates(stock):
        found = set(); todo = list(family[stock])
        while todo:
            x = todo.pop()
            if x == stock or x in found: continue
            found.add(x); todo.extend(family[x]-found)
        return found
    for p in panels:
        stock = p['company_id']; aff = affiliates(stock)
        primary = p['industry_axes']['process'].get('primary')
        directed = [e for e in edges if stock in (e['source_stock'], e['target_stock'])]
        competitors = {e['target_stock'] if e['source_stock'] == stock else e['source_stock']
                       for e in directed if e['kind'] == '경쟁'}
        stage_peers = {x['company_id'] for x in panels if primary and x['in_report_population'] and
                       x['industry_axes']['process'].get('primary') == primary}
        ids = sorted((competitors | stage_peers)-aff-{stock}) if p['in_report_population'] else []
        comparisons = []
        for target in ids:
            x = indexed.get(target)
            if not x: continue
            comparisons.append({'company_id': target, 'company_name': x['company_name'],
                'comparison_basis': [label for yes, label in [(target in competitors, 'explicit_competitor_mention'),
                    (target in stage_peers, 'same_authoritative_primary_stage')] if yes],
                'status': x['status'], 'eligible_flow_n': len(x['evidence']['flows']),
                'delivery_hazard': x['scenarios']['base']['assumptions']['delivery_hazard'],
                'memory_verdict': x['industry_axes']['memory_foundry']['verdict']})
        p['industry_axes']['peers'] = {'source_file': 'ksemi_peers.json', 'mentions': directed,
            'comparisons': comparisons, 'known_affiliates_excluded': sorted(aff),
            'used_for_forecast': False, 'amount_aggregation': False,
            'limitation': '본문 이름 언급이며 계약 증거 아님. 같은 1차 단계 또는 경쟁 언급 비교만; 매출/잔고 합계 없음. 계열망 완전성 미확인'}
        if peer_data.get('not_supplied'):
            p['industry_axes']['peers'].update(status='not_supplied',
                limitation='계열·경쟁 언급 파일 미제공: 빈 배열은 계열 부재나 독립성의 증거가 아님; 회사 금액 합산 없음')
    return edges


def longer_ledger_need(p, c, bt):
    if not p['in_report_population']:
        return None
    qs = c.get('quarters', {})
    target = [qadd('2021Q4', n) for n in range(19)]
    current = audit_snapshot(p['origin'], qs.get(p['origin'], {}), c.get('_unit_contract'))
    period_ready = (not current['reason_codes'] and p['fiscal_year_end_month'] == 12 and
                    explicit_ytd(p['origin'], qs.get(p['origin'], {}).get('orders') or {}))
    scored = [r for r in bt['rows'] if r['company_id'] == p['company_id']]
    unsupported = [h for h in range(1, 11) if not any(r['horizon'] == h for r in scored)]
    annual_scored = [r for r in bt['annual']['rows'] if r['company_id'] == p['company_id']]
    reasons = []
    if len(p['evidence']['flows']) < MIN_FLOWS: reasons.append('insufficient_flow_samples')
    if unsupported: reasons.append('unvalidated_forecast_horizons')
    if not annual_scored: reasons.append('annual_backtest_unavailable')
    missing = [q for q in target if not qs.get(q, {}).get('rcpNo')]
    if not reasons and not missing: return None
    # The requested 19-quarter ledger is now present. Do not keep prescribing
    # more history when its contents fail the same semantic gates at every date.
    reason_code = 'needs_longer_ledger' if missing or period_ready else 'source_semantics_required'
    return {'company_id': p['company_id'], 'company_name': p['company_name'],
        'reason_code': reason_code, 'reasons': reasons,
        'readiness': ('missing_reports_and_source_repair' if missing and not period_ready else
                      'history_extension_candidate' if period_ready else 'source_repair_required'),
        'history_only_will_unlock': False,
        'condition': '더 긴 원장에도 동일 범위·명시적 누적기간·정합성·단위가 성립해야 재추정 가능',
        'eligible_flow_n': len(p['evidence']['flows']), 'minimum_flow_n': MIN_FLOWS,
        'target_quarters': target, 'missing_target_quarters': missing,
        'unsupported_horizons': unsupported, 'annual_scored_n': len(annual_scored),
        'additional_blockers': sorted(set(current['reason_codes'] +
            ([] if period_ready else ['delivery_period_unverified'] if
             not explicit_ytd(p['origin'], qs.get(p['origin'], {}).get('orders') or {}) else [])))}


def read_prior_report(input_dir):
    """Read prior results as data; never execute instructions from the report."""
    report = (input_dir/'ksemi_REPORT.md').read_text()
    companies = {}; forecasts = {}; horizons = {}; scenarios = {}; partial = {}; stock = None
    for line in report.splitlines():
        heading = re.fullmatch(r'### .+ \((\d{6})\)', line)
        if heading:
            stock = heading[1]; forecasts.setdefault(stock, {'quarterly': {}, 'annual': {}})
        if not line.startswith('|'): continue
        cells = [s.strip() for s in line.strip('|').split('|')]
        def number(s):
            return None if s == '—' else float(s.replace(',', '').rstrip('%'))/(100 if s.endswith('%') else 1)
        if len(cells) == 6 and re.fullmatch(r'\d{6}', cells[0]) and cells[2] in ('원장', '후보'):
            companies[cells[0]] = {'company_id': cells[0], 'company_name': cells[1],
                'status': cells[3], 'flow_samples': int(cells[4]),
                'reason_codes': cells[5].split(', ') if cells[5] else []}
        elif len(cells) == 7 and cells[0] in SCENARIOS and cells[1].isdigit() and int(cells[1]) < 1000:
            scenarios[cells[0]] = dict(zip(('n','mae','wape','bias','naive_mae','sensitivity_coverage'),
                                         [number(x) for x in cells[1:]]))
            scenarios[cells[0]]['n'] = int(scenarios[cells[0]]['n'])
        elif len(cells) == 5 and cells[0].isdigit() and 1 <= int(cells[0]) <= 10:
            horizons[cells[0]] = dict(zip(('n','mae','wape','naive_mae'), [number(x) for x in cells[1:]]))
            horizons[cells[0]]['n'] = int(horizons[cells[0]]['n'])
        elif stock and len(cells) == 7 and re.fullmatch(r'202[678]Q[1-4]', cells[0]):
            forecasts[stock]['quarterly'][cells[0]] = {'value':number(cells[2]),
                'existing_backlog_revenue':number(cells[4]), 'new_order_revenue':number(cells[5])}
        elif stock and len(cells) == 7 and cells[0] == 'base' and cells[1] in ('2026','2027','2028'):
            forecasts[stock]['annual'][cells[1]] = {'value':number(cells[2]),
                'observed_revenue':number(cells[3]), 'existing_backlog_revenue':number(cells[4]),
                'new_order_revenue':number(cells[5])}
        elif len(cells) == 4 and re.fullmatch(r'\d{6}',cells[0]) and re.fullmatch(r'\d{4}Q[1-4]',cells[2]):
            partial.setdefault(cells[0], {})[cells[2]] = number(cells[3])
    if len(companies) != 154 or set(horizons) != {str(h) for h in range(1,11)} or set(scenarios) != set(SCENARIOS):
        raise ValueError('prior report tables incomplete; do not fabricate a comparison baseline')
    annual = re.search(r'연간 독립 미래 4분기 검증 (\d+)건', report)
    unique = re.search(r'고유 회사×목표분기 (\d+)개', report)
    if not annual or not unique: raise ValueError('prior sample counts unavailable')
    return {'source_file': 'input/ksemi_REPORT.md', 'round': 2, 'reported_precision':
        'amounts rounded to .001 million KRW; WAPE rounded to .01 percentage point',
        'companies': list(companies.values()), 'forecasts_base': forecasts, 'partial_forecasts':partial,
        'backtest': {'overall': scenarios['base'], 'by_horizon': horizons,
                    'by_scenario': scenarios, 'annual': dict(metrics([]), n=int(annual[1])),
                    'unique_company_target_quarters': int(unique[1])},
        'population': {'input_companies': len(companies),
                       'status_counts': dict(collections.Counter(c['status'] for c in companies.values()))}}


def load_unit_contract(input_dir):
    evidence = input_dir/'ksemi_unit_evidence.json'
    if evidence.exists():
        statement = json.loads(evidence.read_text()).get('unit_contract')
        tier = 'supplied_parser_contract'; source = evidence.name
    else:
        report = (input_dir/'ksemi_REPORT.md').read_text()
        statements = [s for s in report.splitlines() if '저장 금액은 이미 백만원' in s and '_UNIT_SCALE' in s]
        if len(statements) != 1: return None
        statement = statements[0]; tier = 'prior_report_statement'; source = 'ksemi_REPORT.md'
    if not isinstance(statement, str) or not statement.strip(): return None
    return {'evidence_file': source, 'statement': statement, 'evidence_tier': tier,
        'code_reference': 'argus/kce/tools/kce_parse.py:197-207; applications 345,357,359 (reported, not inspected)',
        'source_code_inspected': False, 'source_caption_available': False,
        'normalization_assumption': 'expanded ledger retains the prior parser KRW-million convention; no rescaling',
        'missing_primary_evidence': [] if evidence.exists() else ['ksemi_unit_evidence.json', 'parser source', 'DART HTML']}


def reassess(p, c, previous):
    need = p['remediation']; qs = c['quarters']; target = [qadd('2021Q4', n) for n in range(19)]
    present = [q for q in target if qs.get(q, {}).get('rcpNo')]
    source_codes = {'no_snapshot','backlog_missing','unit_unknown','mixed_currency',
        'normalized_scale_unverified','aggregate_leaf_overlap','duplicate_row_identity',
        'table_reconciliation_failed','future_order_in_snapshot','delivery_period_unverified',
        'scope_changed','unit_changed','negative_delivery_delta','negative_net_order'}
    rejections = [r for r in p['evidence']['flow_rejections'] if r['quarter'] != target[0]]
    counts = dict(collections.Counter(code for r in rejections for code in r['reason_codes']))
    result = {'company_id':p['company_id'], 'company_name':p['company_name'],
        'previous_eligible_flow_n': previous['eligible_flow_n'], 'eligible_flow_n':len(p['evidence']['flows']),
        'flow_n_increase':len(p['evidence']['flows'])-previous['eligible_flow_n'],
        'minimum_flow_n':MIN_FLOWS, 'threshold_met':len(p['evidence']['flows']) >= MIN_FLOWS,
        'newly_threshold_met': previous['eligible_flow_n'] < MIN_FLOWS <= len(p['evidence']['flows']),
        'quarter_slots':len(qs), 'previous_receipted_quarter_n':19-len(previous['missing_target_quarters']),
        'receipted_quarter_n':len(present), 'adjacent_receipted_pair_n':sum(qadd(q,-1) in present for q in present),
        'maximum_flow_n':18, 'rejected_pair_n':18-len(p['evidence']['flows']),
        'rejection_reason_counts_nonexclusive':counts,
        'missing_target_quarters':[q for q in target if q not in present],
        'previous_reason_code':previous['reason_code'],
        'decision': 'resolved' if need is None else need['readiness'],
        'reason_code': None if need is None else need['reason_code'],
        'current_source_blockers': sorted(source_codes.intersection(p['reason_codes'])),
        'unsupported_horizons':p['backtest']['unvalidated_horizons'],
        'annual_scored_n':p['backtest']['annual']['n'],
        'history_only_will_unlock':False,
        'explanation': ('학습 4개 기준, T+1~T+10 및 연간 관측 검증 확보; 통계 보정/회계매출 검증을 뜻하지 않음'
                       if need is None else
                       '19개 슬롯 중 접수번호 없는 분기와 원문 의미 관문이 함께 남음; 추가 수집만으로 자동 승격 불가'
                       if len(present)<19 else
                       '19개 접수분기 확보 후에도 적격 흐름 부족; 기간·잔고·단위·정합성 검증이 필요하며 같은 형식 원장 추가만으로 해제 불가')}
    return result


def compare_backtests(previous, replay, current):
    key = lambda r: (r['company_id'], r['origin'], r['horizon'])
    keys = {key(r) for r in replay['rows']}
    paired = [r for r in current['rows'] if key(r) in keys]
    rows = []
    for h in range(1,11):
        old = previous['by_horizon'][str(h)]; new = current['by_horizon'][str(h)]
        rows.append({'horizon':h, 'previous':old, 'current':new, 'sample_increase':new['n']-old['n']})
    return {'published_round2':previous, 'horizon_comparison':rows,
        'annual_sample_increase':current['annual']['n']-previous['annual']['n'],
        'replay_basis':'current expanded snapshots restricted to round-2 available quarters from needs_longer_ledger.json; original round-2 ledger unavailable',
        'same_targets':{'n':len(paired), 'round2_window_replay':metrics(replay['rows']),
                        'expanded_history':metrics(paired), 'expanded_rows':paired},
        'round2_window_replay':{'overall':replay['overall'], 'rows':replay['rows'],
            'by_horizon':replay['by_horizon'], 'by_company':replay['by_company'], 'annual':replay['annual']},
        'warning':'Full-window score changes mix different targets and training lengths; same-target replay isolates the history effect only within current-vintage inputs.'}


def rounded(x):
    if isinstance(x, float):
        if not math.isfinite(x): raise ValueError('nonfinite output')
        return round(x, 9)
    if isinstance(x, dict): return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, list): return [rounded(v) for v in x]
    return x


def save(path, obj):
    path.write_text(json.dumps(rounded(obj), ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def build(input_dir, output_dir):
    reports = json.loads((input_dir/'ksemi_reports.json').read_text())
    universe = json.loads((input_dir/'ksemi_universe.json').read_text())
    contracts = json.loads((input_dir/'ksemi_contracts.json').read_text())
    def optional(name):
        path = input_dir/name
        return json.loads(path.read_text()) if path.exists() else {'rows': [], 'not_supplied': True}
    tags = optional('ksemi_stage_tags.json'); exposure = optional('ksemi_exposure.json')
    peers = optional('ksemi_peers.json')
    prior = read_prior_report(input_dir)
    prior_needs = json.loads((input_dir/'needs_longer_ledger.json').read_text())
    prior_needs_byid = {r['company_id']:r for r in prior_needs}
    contract = load_unit_contract(input_dir)
    tag_byid = {x['stock']: x for x in tags['rows']}
    exp_byid = {x['stock']: x for x in exposure['rows']}
    if len(tag_byid) != len(tags['rows']) or len(exp_byid) != len(exposure['rows']):
        raise ValueError('duplicate enrichment identity')
    for c in reports['rows']: c['_unit_contract'] = contract
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(input_dir.iterdir()) if p.is_file()}
    origin = max(reports['quarters']); byid = {c['stock']: c for c in reports['rows']}
    allrows = {c['stock']: c for c in universe['rows']}
    for c in reports['rows']: allrows.setdefault(c['stock'], c)
    if len(byid) != len(reports['rows']) or len(allrows) != len(universe['rows']):
        raise ValueError('population identities require explicit reconciliation')
    if ((not tags.get('not_supplied') and set(tag_byid) != set(allrows)) or
            (not exposure.get('not_supplied') and set(exp_byid) != set(byid))):
        raise ValueError('authoritative stage/exposure population mismatch')
    if set(prior_needs_byid) != set(byid):
        raise ValueError('round-2 retry manifest population mismatch')
    panels = []; audits = []; tasks = []
    grouped = collections.defaultdict(list)
    for r in contracts['rows']: grouped[r['stock']].append(r)
    for stock, u in sorted(allrows.items()):
        c = byid.get(stock, dict(u, quarters={}))
        panel = forecast_company(c, origin)
        panel['in_report_population'] = stock in byid
        panel['panel_present'] = stock in byid
        if stock not in byid:
            panel['reason_codes'] = sorted(set(panel['reason_codes']+['report_not_supplied']))
            panel['audit_blockers'].append(REASONS['report_not_supplied'])
            for scenario in panel['scenarios'].values():
                for row in scenario['quarterly']:
                    row['reason_codes'] = panel['reason_codes']
        process = process_info(u, tag_byid.get(stock))
        if process.get('reason'):
            panel['reason_codes'] = sorted(set(panel['reason_codes']+[process['reason']]))
        panel['industry_axes'] = {'process': process, 'recognition': panel['evidence']['recognition'],
            'customers': customer_info(c), 'china_contracts': contract_exposure(grouped[stock]),
            'memory_foundry': memory_info(exp_byid.get(stock)),
            'export_domestic': {'export_share': None, 'not_used_for_forecast': True,
                'source_quarter': origin, 'source_field': 'reports.quarters.sales',
                'reason_code': 'sales_scope_unverified' if stock in byid else 'report_not_supplied',
                'note': '수출/내수 파싱 값은 수집됐으나 총계·중복행·기간 범위 미대조; 검증 전 비중을 만들지 않음'},
            'schedule_table': panel['evidence']['schedule'],
            'system_and_unit_ids': {'status': 'not_supplied', 'note': '선표/계통/호기 식별자를 장비 원장에 임의 생성하지 않음'}}
        qs = [audit_snapshot(q, c.get('quarters', {}).get(q, {}), c.get('_unit_contract')) for q in sorted(reports['quarters'])]
        a = {'company_id': stock, 'company_name': c['name'], 'in_report_population': stock in byid,
             'membership': 'report_population' if stock in byid else 'candidate_without_supplied_scan_verdict',
             'status': panel['status'], 'reason_codes': panel['reason_codes'],
             'blockers': panel['audit_blockers'], 'quarter_slots': len(c.get('quarters', {})),
             'successful_report_quarters': sum(bool(q['rcpNo']) for q in qs),
             'order_rows': sum(q['order_row_count'] for q in qs), 'sales_rows': sum(q['sales_row_count'] for q in qs),
             'aggregate_rows': sum(len(q['aggregate_rows']) for q in qs),
             'sales_aggregate_rows': sum(len(q['sales_audit']['aggregate_rows']) for q in qs),
             'sales_exact_duplicate_rows': sum(q['sales_audit']['exact_duplicate_rows'] for q in qs),
             'unit_verified_quarters': sum(q['unit']['verified'] for q in qs),
             'fiscal': panel['fiscal_evidence'], 'recognition': panel['evidence']['recognition'],
             'flow_samples': len(panel['evidence']['flows']), 'quarters': qs,
             'process': panel['industry_axes']['process'],
             'scope': panel['scope'], 'current_snapshot_progress_only': qs[-1]['progress_ratio']}
        ctasks = collect_tasks(c, a, origin); a['collection_task_count'] = len(ctasks)
        tasks += ctasks; audits.append(a); panels.append(panel)
    edges = attach_peers(panels, peers)
    bt = backtest(reports['rows'], sorted(reports['quarters']))
    retry = []
    for p in panels:
        score = bt['by_company'].get(p['company_id'], metrics([]))
        p['backtest'] = dict(score, small_sample=True, calibrated=False,
            warning='검증 표본이 적음. 수정된 원장 기준 납품 대용치 채점; FY+2 회계매출 정확도 미검증.')
        company_scores = [r for r in bt['rows'] if r['company_id'] == p['company_id']]
        p['backtest']['by_horizon'] = {str(h): metrics([r for r in company_scores if r['horizon'] == h])
                                       for h in range(1, 11)}
        p['backtest']['unvalidated_horizons'] = [h for h in range(1, 11) if
            not p['backtest']['by_horizon'][str(h)]['n']]
        p['backtest']['annual'] = metrics([r for r in bt['annual']['rows'] if r['company_id'] == p['company_id']])
        p['evidence']['horizon_validation'] = {'unvalidated_horizons': p['backtest']['unvalidated_horizons'],
            'annual_score_n': p['backtest']['annual']['n'], 'financial_revenue_validated': False}
        p['audit_can']['backtest'] = 'yes_small_sample' if score['n'] else 'no'
        need = longer_ledger_need(p, byid.get(p['company_id'], {}), bt)
        p['remediation'] = need
        p['needs_longer_ledger'] = need if need and need['reason_code'] == 'needs_longer_ledger' else None
        if need:
            if need['reason_code'] == 'needs_longer_ledger': retry.append(need)
            p['reason_codes'] = sorted(set(p['reason_codes']+[need['reason_code']]))
        p['audit_blockers'] = [REASONS.get(x, x) for x in p['reason_codes']]
        p['warning_codes'] = [x for x in p['reason_codes'] if x in
            ('unit_caption_unavailable', 'financial_revenue_unverified', 'recognition_unverified',
             'sales_scope_unverified', 'needs_longer_ledger', 'stage_unassigned',
             'stage_tags_absent', 'unit_contract_inherited')]
        p['full_forecast_blockers'] = [] if p['status'] == 'full' else [x for x in p['reason_codes'] if x not in p['warning_codes']]
        for scenario in p['scenarios'].values():
            for row in scenario['quarterly']:
                row['reason_codes'] = p['reason_codes']
        a = next(a for a in audits if a['company_id'] == p['company_id'])
        a.update(reason_codes=p['reason_codes'], blockers=p['audit_blockers'],
                 needs_longer_ledger=p['needs_longer_ledger'], remediation=need)
        if p['company_id'] in byid:
            p['ledger_reassessment'] = reassess(p, byid[p['company_id']], prior_needs_byid[p['company_id']])
        else:
            p['ledger_reassessment'] = None
    counts = dict(collections.Counter(p['status'] for p in panels))
    rc = dict(collections.Counter(p['status'] for p in panels if p['in_report_population']))
    pop = {'input_entries': len(universe['rows']), 'input_companies': len(allrows),
        'report_companies': len(byid), 'candidate_only_companies': len(allrows)-len(byid),
        'status_counts': counts, 'report_status_counts': rc,
        'estimated_companies': sum(p['status'] != 'unavailable' for p in panels),
        'unestimated_companies': sum(p['status'] == 'unavailable' for p in panels),
        'full_forecast_companies': sum(p['status'] == 'full' for p in panels),
        'definition': 'estimated = full ledger delivery proxy or partial dated backlog amount; not accounting revenue'}
    stage_audit = []
    for s in STAGES:
        matches = [p for p in panels if p['in_report_population'] and s in p['industry_axes']['process'].get('stage_names', [])]
        fs = [p for p in matches if p['status'] == 'full']
        hs = [p['scenarios']['base']['assumptions']['delivery_hazard'] for p in fs]
        primary_matches = [p for p in matches if p['industry_axes']['process'].get('primary_name') == s]
        stage_audit.append({'stage': s, 'authoritative_tag_company_n': len(matches),
            'primary_company_n': len(primary_matches), 'flow_company_n': len(fs),
            'company_ids': [p['company_id'] for p in fs], 'descriptive_median_hazard': statistics.median(hs) if hs else None,
            'stage_speed_identified': False,
            'reason': '정본 태그 수용; 다중 단계·일반 산업·겸업 문구와 적은 적격 회사로 단계별 소진속도 차이 식별 불가'})
    if tags.get('not_supplied'):
        for row in stage_audit:
            row.update(authoritative_tag_company_n=None, primary_company_n=None, flow_company_n=None,
                       company_ids=None, reason='stage_tags_absent: supplied round-3 files contain no authoritative assignments')
    prior_byid = {x['company_id']: x for x in prior['companies']}
    delta = [{'company_id': p['company_id'], 'company_name': p['company_name'],
        'previous_status': prior_byid.get(p['company_id'], {}).get('status'), 'status': p['status'],
        'previous_flow_n': prior_byid.get(p['company_id'], {}).get('flow_samples'),
        'flow_n': len(p['evidence']['flows']),
        'resolved_reason_codes': sorted(set(prior_byid.get(p['company_id'], {}).get('reason_codes', []))-set(p['reason_codes'])),
        'added_reason_codes': sorted(set(p['reason_codes'])-set(prior_byid.get(p['company_id'], {}).get('reason_codes', [])))} for p in panels]
    for d, p in zip(delta, panels):
        old = prior['forecasts_base'].get(p['company_id'], {})
        changes = []
        for frequency, period_key in [('quarterly','quarter'),('annual','fiscal_year')]:
            for row in p['scenarios']['base'][frequency]:
                previous_row = old.get(frequency, {}).get(str(row[period_key]))
                if previous_row is None: continue
                before, after = previous_row['value'], row['value']
                changes.append({'frequency':frequency, 'period':row[period_key],
                    'previous_value':before, 'value':after,
                    'absolute_change':after-before if num(after) and num(before) else None,
                    'relative_change':after/before-1 if num(after) and num(before) and before else None,
                    'previous_components':previous_row,
                    'components':{k:row[k] for k in ('existing_backlog_revenue','new_order_revenue')},
                    'baseline_source':'published round-2 report, rounded amounts'})
        d['base_forecast_changes'] = changes
        d['partial_forecast_changes'] = [
            {'quarter':q,'previous_value':before,'value':next(r['covered_sites_partial_revenue']
                for r in p['scenarios']['base']['quarterly'] if r['quarter']==q),
             'baseline_source':'published round-2 report; rounded .001 million KRW'}
            for q,before in prior['partial_forecasts'].get(p['company_id'], {}).items()]
        d['large_change_threshold'] = .20
        d['large_value_change'] = any(num(r['relative_change']) and abs(r['relative_change']) >= .20 for r in changes)
        d['explanation'] = ('추가 적격 과거분기로 회사 내 h·순수주 분위수가 바뀜; 추정식·4개 기준 유지'
                            if d['flow_n'] > (d['previous_flow_n'] or 0) else
                            '적격 표본 증가 없음; 기간·잔고·단위·정합성 관문 유지' if p['in_report_population'] else
                            '보고서 원장 미제공 후보; 금액 추정 불가')
    replay_companies = []
    for c in reports['rows']:
        old = prior_needs_byid[c['stock']]
        allowed = set(old['target_quarters'])-set(old['missing_target_quarters'])
        replay_companies.append(dict(c, quarters={q:s for q,s in c['quarters'].items() if q in allowed}))
    replay_quarters = sorted({q for c in replay_companies for q in c['quarters']})
    replay = backtest(replay_companies, replay_quarters)
    for d in delta:
        d['previous_backtest_replay'] = replay['by_company'].get(d['company_id'],metrics([]))
    comparison = compare_backtests(prior['backtest'], replay, bt)
    reassessments = [p['ledger_reassessment'] for p in panels if p['ledger_reassessment']]
    continuation = {'base_engine': 'input/ksemi_forecast.py', 'base_renderer': 'input/forecast_section.py',
        'base_audit': None, 'base_audit_missing': True, 'baseline_source':'input/ksemi_REPORT.md',
        'previous_population': prior['population'], 'company_deltas': delta,
        'uncertainty':'round-2 panel/audit/original ledger absent; published report and retry manifest are the comparison evidence'}
    missing_inputs = [name for name in ('ksemi_stage_tags.json','ksemi_exposure.json','ksemi_peers.json',
        'ksemi_audit.json','ksemi_unit_evidence.json','forecast_panel.json') if not (input_dir/name).exists()]
    panel = {'schema_version': 'ksemi-r3-1', 'schema_family': 'kce-r4-1', 'assignment': 'ARGUS-ksemi',
        'origin': origin, 'money_unit': MONEY, 'unit_status_codes': ['unit_caption_unavailable'],
        'numeric_decimal_places': 9, 'input_sha256': hashes,
        'engine_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'adapter_basis': 'independent semiconductor order-table adapter; conservative unit/period gates',
        'fiscal_year_end_month': None, 'fiscal_basis': 'per-company observed annual report title month',
        'forecast_quarters': [qadd(origin, n) for n in range(1, 11)], 'population': pop,
        'unlisted_reference': [], 'backtest': bt, 'stage_audit': stage_audit,
        'backtest_comparison': comparison, 'ledger_reassessment':reassessments,
        'ledger_summary': {'quarters':reports['quarters'], 'slots':sum(len(c['quarters']) for c in reports['rows']),
            'receipted_snapshots':sum(r['receipted_quarter_n'] for r in reassessments),
            'previous_eligible_flow_n':sum(r['previous_eligible_flow_n'] for r in reassessments),
            'eligible_flow_n':sum(r['eligible_flow_n'] for r in reassessments),
            'decisions':dict(collections.Counter(r['decision'] for r in reassessments)),
            'newly_threshold_met':[r['company_id'] for r in reassessments if r['newly_threshold_met']]},
        'continuation': continuation, 'unit_contract': contract,
        'reason_dictionary': REASONS, 'needs_longer_ledger': retry,
        'source_repairs':[p['remediation'] for p in panels if p['remediation'] and
                          p['remediation']['reason_code'] == 'source_semantics_required'],
        'missing_input_files':missing_inputs,
        'aggregation_policy': 'No company, affiliate, peer or overlapping stage monetary totals',
        'enrichment_audit': {'stage_rows': len(tag_byid), 'empty_stage_rows': sum(not x['stages'] for x in tags['rows']),
            'memory_rows': len(exp_byid), 'memory_distribution': dict(collections.Counter(x['verdict'] for x in exposure['rows'])),
            'peer_edges':len(edges), 'missing_files':missing_inputs,
            'source_note':'Missing stage/exposure/peer JSON means unknown, not empty confirmed assignments or no affiliations'},
        'note': '민감도는 통계적 신뢰구간 아님. 금액은 2차 보고서 정규화 설명을 승계한 백만원 납품 대용치; unit_caption_unavailable, unit_contract_inherited.',
        'companies': panels}
    audit = {'schema_version': 'ksemi-audit-3', 'origin': origin, 'input_sha256': hashes, 'population': pop,
        'observed_errors': [{'company_id': c['stock'], 'errors': c.get('errors')} for c in reports['rows'] if c.get('errors')],
        'scope_limit': 'DART HTML/parser source/audit/enrichment absent; prior report normalization statement used conditionally',
        'missing_input_files':missing_inputs, 'ledger_reassessment':reassessments,
        'continuation': continuation, 'needs_longer_ledger': retry,
        'reason_dictionary': REASONS, 'stage_audit': stage_audit, 'companies': audits,
        'collection_queue': tasks, 'collection_task_count': len(tasks)}
    output_dir.mkdir(parents=True, exist_ok=True)
    save(output_dir/'forecast_panel.json', panel); save(output_dir/'ksemi_audit.json', audit)
    save(output_dir/'collection_queue.json', tasks)
    save(output_dir/'backtest.json', bt)
    save(output_dir/'needs_longer_ledger.json', retry)
    write_report(panel, audit, output_dir)
    print(json.dumps({'population': pop, 'backtest': bt['overall'], 'collection_tasks': len(tasks)}, ensure_ascii=False))
    return panel, audit


def write_report(panel, audit, out):
    pop = panel['population']; bt = panel['backtest']
    def f(v): return format(v, ',.3f') if num(v) else '—'
    def pct(v): return format(v*100, '.2f')+'%' if num(v) else '—'
    def table(headers, rows):
        return ['|'+'|'.join(headers)+'|', '|'+'|'.join(['---']*len(headers))+'|'] + [
            '|'+'|'.join(str(v).replace('|', '/') for v in row)+'|' for row in rows]
    full = [c for c in panel['companies'] if c['status'] == 'full']
    part = [c for c in panel['companies'] if c['status'] == 'partial']
    eligible = [r for r in panel['needs_longer_ledger'] if r['readiness'] == 'history_extension_candidate']
    text = ['# ARGUS-ksemi 3차 보고서', '',
        '2차 엔진·렌더러·회귀검사를 이어 수정했다. 추정식과 적격 흐름 4개 기준은 유지했다. 확장 원장과 2차 보고서·보류 목록만으로 재판정했으며 원문과 파서 소스는 확인하지 못했다.', '',
        '**새로 추정 가능해진 회사는 0사다.** 원익IPS와 티에스이의 needs_longer_ledger는 장기·연간 검증 확보로 해제했다. 나머지 81사는 적격 흐름 0개를 유지했다. 이 중 64사는 완전한 원장에서도 원문 의미·정합성 보완이 필요하고, 17사는 접수분기 누락도 남았다.',
        '기준 백테스트 T+1~T+8은 12→150건(WAPE 34.98%→34.56%), T+1~T+10은 12→171건(34.98%→35.15%), 연간은 0→20건(WAPE 18.35%)이다. 같은 목표 12건에서 WAPE는 34.98%→42.20%로 악화됐다. 표본 확대를 정확도 개선으로 간주하지 않았다.', '',
        f"입력 {pop['input_companies']}사 = 추정 {pop['estimated_companies']}사(전체 조건부 납품 대용치 {len(full)}사 + 일부 미래 납기 잔고 {len(part)}사) + 미추정 {pop['unestimated_companies']}사.",
        f"보고서 원장 {pop['report_companies']}사와 후보만 있는 {pop['candidate_only_companies']}사를 구분했다. 후보의 개별 편입·배제 판정 파일은 미제공이다.",
        '전 회사에 T+1~T+10(2026Q3~2028Q4), FY2026~FY2028, 보수·기준·낙관 슬롯을 유지하고 불가능한 값은 null로 남겼다.', '',
        '## 메워진 입력과 남은 불확실성', '',
        '- 이번 입력에는 `ksemi_stage_tags.json`, `ksemi_exposure.json`, `ksemi_peers.json`, `ksemi_audit.json`, `ksemi_unit_evidence.json`, 2차 `forecast_panel.json`이 없다. 과거 보고서에 존재했다는 설명을 실제 파일 수신으로 취급하지 않았다.',
        '- 공정 배정·메모리/파운드리·계열 간선은 미제공으로 남겼다. 계열망이 비어 있다고 독립 회사로 인정하거나 회사별 금액을 합산하지 않았다. 중국 노출은 제공 계약자료의 단위·중복 검사 후 설명용 비중만 유지했다.',
        '- 단위 근거는 2차 보고서의 `_UNIT_SCALE` 설명과 “저장 금액은 이미 백만원” 문장을 조건부 승계했다. `unit_contract.evidence_tier=prior_report_statement`; 확장본도 같은 정규화 규약이라는 가정이며 원문·파서 검증 완료를 뜻하지 않는다. 원익IPS·티에스이 적격 흐름은 백만원 캡션으로도 성립한다. 비백만원 캡션의 일부 납기 금액은 특히 승계 근거에 의존한다. 재환산하지 않았다.',
        '- 원문 캡션을 확인하지 못했으므로 금액 사용 회사에 `unit_caption_unavailable`을 기록했다. `unit_seen=false`, 혼합통화, 합계·상세 중복, 정합성 실패는 계약만으로 해제하지 않았다.',
        '- 매출표의 환산 계약 수용과 회계매출 확정은 다르다. 매출표 중복·연결/별도·수행의무 범위가 미대조여서 전 추정은 수주표 기납품액 대용치다.', '',
        '## 산업 축과 추정 방법', '',
        '1차의 수주잔고→납품 시차, 인도·설치검수(SAT)·진행기준, 공정 단계, 고객 집중, 전방 CAPEX, 메모리/파운드리, 수출·중국 계약, 장비·부품·서비스 범위를 이어 썼다. SAT 시차와 CAPEX 탄력성 관측이 없으므로 임의 계수를 넣지 않았다.',
        '수출·내수 축은 매출표의 총계·중복행·기간 범위 검증이 남아 비중을 null로 두었다. 중국 계약 비중으로 대신하지 않았다.',
        '명시적 연누적 기간, 12월 결산, 인접 분기 동일 품목 범위, 단위·정합성 검사를 통과한 표만 사용한다. 분기 납품 D는 연누적 차분(Q1은 누적 자체), 순수주 등가 N=B말−B전+D다. N은 취소·조정이 섞인 순액이며 공시된 신규 계약 총액과 같지 않다. 음수와 누락은 0으로 보정하지 않는다.',
        '적격 흐름 최소 4개. h=D/(D+B말)의 회사 내 중앙값을 고정하고 분기 N의 25·50·75% 분위수를 보수·기준·낙관 가정으로 쓴다. 계절조정은 하지 않는다. 각 분기초 신규수주가 유입된다고 가정해 기존 잔고 E의 납품=E×h, 신규 잔고 납품=(직전 신규잔고+N)×h로 분리한다. 금액 보존을 검사했다.',
        '민감도 구간은 h와 N의 10·90% 관측 분위수 및 시나리오 값을 조합한 범위다. 기존분·신규분 구간도 제공하며 `calibrated=false`, 신뢰수준은 null이다. 연간은 분기 민감도 경계의 합으로 보수적인 범위이며 확률구간이 아니다.',
        '납기형 일부 추정은 유효한 미래 납기행만 해당 분기에 배분한다. 신규분과 전체는 null이다. 세 시나리오는 같은 계약 납기를 보여 주며 근거 없는 시나리오 차이를 만들지 않는다. 납기/SAT 오차 분포가 없어 일부 잔고의 민감도 경계는 null이다.',
        'FY는 결산 종료 연도 기준이다. FY2026은 검증된 과거 관측분과 전망분을 구분한다. 3S는 3월 결산이며 부족한 과거 관측을 채우지 않는다. FY2028 전체 추정은 대부분 신규수주 지속 가정에 의존한다.', '',
        '## 추정 가능한 회사', '']
    text += table(['코드','회사','범위','적격 흐름','기준 h','기준 분기 N','기존 잔고 배분 비중'], [
        [c['company_id'],c['company_name'],c['status'],len(c['evidence']['flows']),
         pct(c['scenarios']['base']['assumptions']['delivery_hazard']),
         f(c['scenarios']['base']['assumptions']['new_orders_per_quarter']),pct(c['coverage']['covered_fraction'])]
        for c in full+part])
    text += ['', '금액 단위: 백만원. 조건부 납품 대용치이며 정규화 근거는 2차 보고서에서 승계했다.', '']
    for c in full:
        text += ['### '+c['company_name']+' ('+c['company_id']+')', '']
        text += table(['분기','보수 전체','기준 전체','낙관 전체','기준 잔고분','기준 신규분','기준 민감도'], [
            [r['quarter'],f(c['scenarios']['conservative']['quarterly'][i]['value']),f(r['value']),
             f(c['scenarios']['optimistic']['quarterly'][i]['value']),f(r['existing_backlog_revenue']),
             f(r['new_order_revenue']),f(r['interval']['lower'])+' ~ '+f(r['interval']['upper'])]
            for i,r in enumerate(c['scenarios']['base']['quarterly'])])
        text += ['']+table(['시나리오','FY','전체','관측분','미래 잔고분','미래 신규분','민감도'], [
            [name,r['fiscal_year'],f(r['value']),f(r['observed_revenue']),f(r['existing_backlog_revenue']),
             f(r['new_order_revenue']),f(r['interval']['lower'])+' ~ '+f(r['interval']['upper'])]
            for name,scenario in c['scenarios'].items() for r in scenario['annual']])+['']
    text += ['### 일부 미래 납기 잔고', '']+table(['코드','회사','분기','금액'], [
        [c['company_id'],c['company_name'],r['quarter'],f(r['covered_sites_partial_revenue'])]
        for c in part for r in c['scenarios']['base']['quarterly'] if (r['covered_sites_partial_revenue'] or 0)>0])
    text += ['', '## 백테스트', '',
        '예측 시점 이후 원장 값을 학습에 사용하지 않는 rolling-origin 검증이다. 단, 최초 공시일별 원장 빈티지가 없어 현재 정정본을 자른 pseudo out-of-sample이며 실제 당시 투자자가 알았던 정보의 검증은 아니다. 기준 naive는 마지막 적격 분기 납품액의 반복이다.',
        f"기준 시나리오 {bt['overall']['n']}건, 고유 회사×목표분기 {bt['unique_company_target_quarters']}개. 중첩 예측은 같은 실적을 재사용하므로 독립 표본 수가 아니다.",
        f"채점 가능한 기준분기는 {bt['scored_origins'][0]}~{bt['scored_origins'][-1]}의 {len(bt['scored_origins'])}개다. 매 기준분기까지의 적격 표본 전체를 사용하고 최소 4개 이전 예측은 채점하지 않았다. WAPE=절대오차 합/실측 절댓값 합, MAE=절대오차 평균, 편향=예측−실측 평균이다. 회사 금액 합계 전망은 만들지 않았으며 WAPE 분모의 집계는 오차 평가에만 사용했다.", '']
    text += table(['시나리오','n','MAE','WAPE','편향','naive MAE','민감도 포함률'], [
        [name,v['overall']['n'],f(v['overall']['mae']),pct(v['overall']['wape']),f(v['overall']['bias']),
         f(v['overall']['naive_mae']),pct(v['overall']['sensitivity_coverage'])] for name,v in bt['by_scenario'].items()])
    comparison = panel['backtest_comparison']; oldbt = comparison['published_round2']
    text += ['', '### 2차 대비 지평별 표본과 오차', '',
        '2차 값은 제공 보고서의 반올림 수치다. T+1~T+8을 기본 검증 범위로 집계하고 T+9~T+10도 추가 표시했다. 표본은 회사×기준분기×목표분기이며 회사 수가 아니다.', '']
    text += table(['지평','2차 n','3차 n','증가','2차 WAPE','3차 WAPE','3차 MAE','3차 naive MAE'], [
        ['T+'+str(r['horizon']),r['previous']['n'],r['current']['n'],r['sample_increase'],
         pct(r['previous']['wape']),pct(r['current']['wape']),f(r['current']['mae']),f(r['current']['naive_mae'])]
        for r in comparison['horizon_comparison']])
    text += ['']+table(['범위','2차 n','3차 n','증가','2차 WAPE','3차 WAPE'], [
        ['T+1~T+8',sum(oldbt['by_horizon'][str(h)]['n'] for h in range(1,9)),bt['t1_t8']['n'],
         bt['t1_t8']['n']-sum(oldbt['by_horizon'][str(h)]['n'] for h in range(1,9)),pct(oldbt['overall']['wape']),pct(bt['t1_t8']['wape'])],
        ['T+1~T+10',oldbt['overall']['n'],bt['overall']['n'],bt['overall']['n']-oldbt['overall']['n'],pct(oldbt['overall']['wape']),pct(bt['overall']['wape'])],
        ['연간',oldbt['annual']['n'],bt['annual']['n'],comparison['annual_sample_increase'],'—',pct(bt['annual']['wape'])]])
    paired = comparison['same_targets']
    text += ['', f"같은 목표 {paired['n']}건만 대조하면 짧은 원장 재현 WAPE {pct(paired['round2_window_replay']['wape'])} → 긴 학습 원장 {pct(paired['expanded_history']['wape'])}다. 전체 기간 WAPE와 함께 해석해야 한다. 짧은 원장 재현은 보류 목록의 당시 보유 분기로 현 정정본을 제한한 계산이며 최초 2차 JSON 자체가 아니다.", '',
        '### 회사별 검증', '']
    deltas = {r['company_id']:r for r in panel['continuation']['company_deltas']}
    text += table(['회사','2차 재현 n','2차 재현 WAPE','3차 n','3차 WAPE','3차 MAE','naive MAE'], [
        [c['company_name'],deltas[c['company_id']]['previous_backtest_replay']['n'],
         pct(deltas[c['company_id']]['previous_backtest_replay']['wape']),c['backtest']['n'],
         pct(c['backtest']['wape']),f(c['backtest']['mae']),f(c['backtest']['naive_mae'])] for c in full])
    text += ['', '### 연간 오차', '',
        '기준분기 이후의 미래 4분기 실측이 모두 있고 동일 품목 범위를 유지한 회계연도만 채점했다. 당해연도 기관측분을 더한 쉬운 문제와 섞지 않았다. 전망의 FY2026은 기관측+미래분이지만 여기의 연간 검증은 온전히 미래 4분기다.',
        f"연간 {bt['annual']['n']}건은 고유 회사×FY {bt['annual']['unique_company_fiscal_years']}개를 중복 사용한다. 서로 독립인 연도 표본 {bt['annual']['n']}개가 아니다.", '']
    text += table(['시나리오','n','MAE','WAPE','편향','naive MAE','민감도 포함률'], [
        [name,v['annual']['n'],f(v['annual']['mae']),pct(v['annual']['wape']),f(v['annual']['bias']),
         f(v['annual']['naive_mae']),pct(v['annual']['sensitivity_coverage'])] for name,v in bt['by_scenario'].items()])
    text += ['']+table(['연간 지평','n','MAE','WAPE','naive MAE'], [
        ['FY+'+h,m['n'],f(m['mae']),pct(m['wape']),f(m['naive_mae'])] for h,m in bt['annual']['by_horizon_year'].items()])
    text += ['']+table(['검증 대상 FY','n','MAE','WAPE','naive MAE'], [
        [y,m['n'],f(m['mae']),pct(m['wape']),f(m['naive_mae'])] for y,m in bt['annual']['by_fiscal_year'].items()])
    text += ['']+table(['회사','연간 n','MAE','WAPE','naive MAE'], [
        [next(c['company_name'] for c in full if c['company_id']==stock),m['n'],f(m['mae']),pct(m['wape']),f(m['naive_mae'])]
        for stock,m in bt['annual']['by_company'].items()])
    text += ['', '기준 시나리오의 전체 WAPE는 2차보다 소폭 악화됐다. 지평·시나리오·회사에 따라 naive보다 나쁜 오차도 그대로 남겼다. 이 점수는 납품 대용치 정확도이며 회계매출 정확도가 아니다. 기존분·신규분의 실측 정답이 없어 구성별 정확도는 검증하지 못했다.', '',
        '## 19분기 수신 후 보류 재판정', '']
    summary = panel['ledger_summary']; rr = panel['ledger_reassessment']
    text += [f"83사 × 19분기 = {summary['slots']}개 슬롯이지만 접수번호가 있는 원장은 {summary['receipted_snapshots']}개다. 적격 흐름은 {summary['previous_eligible_flow_n']}→{summary['eligible_flow_n']}개이며 새로 4개 문턱을 넘은 회사는 {len(summary['newly_threshold_met'])}사다.",
        '81사는 2차에도 흐름 0개였고 이번에도 0개다. 표본 1~3개에서 대기하던 회사가 다수였던 것은 아니다. 19개 슬롯을 18개 적격 인접쌍으로 간주할 수 없다.',
        '원익IPS 7→18개, 티에스이 7→16개는 T+1~T+10 및 연간 검증이 생겨 needs_longer_ledger를 해제했다. 티에스이 2024Q1 표 정합성 실패로 그 분기와 2024Q2 차분이 제외됐다. 2021Q4는 앞 분기가 없어 순수주 흐름으로 쓰지 않는다.',
        '완전한 19분기 수신 회사의 의미·정합성 차단은 source_semantics_required로 재분류했다. 접수번호 누락 회사는 needs_longer_ledger와 원문 보완 필요를 함께 남겼다. 과거 오류 횟수는 중복 집계이므로 합계가 제외 쌍 수와 같지 않다.', '']
    text += table(['재판정','회사 수'], [[k,v] for k,v in summary['decisions'].items()])
    text += ['']+table(['코드','회사','2차→3차 흐름','접수/인접쌍','재판정','현재 원문 차단','누락 분기'], [
        [r['company_id'],r['company_name'],str(r['previous_eligible_flow_n'])+'→'+str(r['eligible_flow_n']),
         str(r['receipted_quarter_n'])+'/'+str(r['adjacent_receipted_pair_n']),r['decision'],
         ', '.join(r['current_source_blockers']) or '없음',', '.join(r['missing_target_quarters']) or '없음'] for r in rr])
    text += ['', '## 2차 대비 회사별 추정 변화', '',
        '신규 추정 가능 회사는 없고 full 2사·partial 5사를 유지했다. 아래는 기준 시나리오의 제공 보고서 수치 대비 변화다. 절댓값 20% 이상을 큰 변화로 분류했다. 전체 154사 상태·사유 변화와 회사별 모든 분기·연간 수치 차이는 continuation.company_deltas에 저장했다.', '']
    text += table(['회사','기간','2차','3차','변화율','3차 잔고분','3차 신규분'], [
        [c['company_name'],str(r['period']),f(r['previous_value']),f(r['value']),pct(r['relative_change']),
         f(r['components']['existing_backlog_revenue']),f(r['components']['new_order_revenue'])]
        for c in full for r in deltas[c['company_id']]['base_forecast_changes'] if r['frequency']=='annual' or r['period']=='2026Q3'])
    text += ['', '원익IPS는 과거 저수주 구간이 들어와 기준 분기 순수주 N이 260,929→155,594.5백만원으로 낮아지고 h는 36.57%→42.97%로 높아졌다. 단기 잔고분 소진은 빨라졌지만 장기 신규분이 줄었다. 티에스이는 N이 62,857→43,449.5백만원, h는 50.55%→48.76%로 내려갔다. 최신 분기의 잔고를 바꾼 효과가 아니라 학습기간 구성 변화다. 과거 수주 국면을 동일 가중하는 중앙값이 최근 국면을 잘 대표하는지는 미검증이다.',
        '일부 납기형 5사의 양의 분기 금액은 2차 보고서와 0.001백만원 반올림 범위에서 동일하다. 신규분과 전체금액은 계속 null이다. 단계·노출·계열 정보의 미제공은 이번 전달 파일의 차이이며 회사 경제활동 변화로 해석하지 않는다.', '']
    text += ['', '## 정본 13단계 감사', '',
        '이번 단계 배정 파일은 미제공이다. 아래 —는 무배정이나 0개라는 판정이 아니다. 단계 속도·계열 금액 합계를 만들지 않았다.', '']
    text += table(['단계','정본 태그 회사','주단계 회사','적격 회사','기술통계 h 중앙값'], [
        [r['stage'],r['authoritative_tag_company_n'] if r['authoritative_tag_company_n'] is not None else '—',r['primary_company_n'] if r['primary_company_n'] is not None else '—',r['flow_company_n'] if r['flow_company_n'] is not None else '—',pct(r['descriptive_median_hazard'])] for r in panel['stage_audit']])
    text += ['', '## 전수 판정', '']+table(['코드','회사','입력 범위','상태','흐름 표본','사유 코드'], [
        [c['company_id'],c['company_name'],'원장' if c['in_report_population'] else '후보',c['status'],
         len(c['evidence']['flows']),', '.join(c['reason_codes'])] for c in panel['companies']])
    text += ['', '## 사유 코드', '']+['- `'+k+'`: '+v for k,v in REASONS.items()]
    text += ['', '## 재현과 인계', '',
        '```sh', 'python3 output/ksemi_forecast.py --input-dir input --output-dir output',
        'python3 output/forecast_section.py --panel output/forecast_panel.json --output-dir output',
        'python3 -B -m unittest discover -s output -p test_ksemi_forecast.py -v', '```', '',
        '검증 결과는 `validation.json`에 별도 기록한다. 입력 SHA-256 및 이어 쓴 코드·감사 경로는 패널에 보존했다. `sections/<종목코드>.html`은 가능한 회사만 생성하고 외부 스크립트·패키지·CDN을 쓰지 않는다.',
        'tracker 사전 확인은 `central_connection_failed`였다. 재시도·인계 강제 회수 없이 할당된 output/만 작성했다. 중앙 파일 claim 성공을 주장하지 않으며 로컬 작업 소유 범위는 task_claim.json에 기록했다. 정본 수정·네트워크 자료 수집·배포는 수행하지 않았다.']
    (out/'ksemi_REPORT.md').write_text('\n'.join(text)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=Path('input'))
    parser.add_argument('--output-dir', type=Path, default=Path('output'))
    args = parser.parse_args()
    build(args.input_dir, args.output_dir)


if __name__ == '__main__':
    main()
