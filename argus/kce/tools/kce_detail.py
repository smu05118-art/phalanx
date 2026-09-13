#!/usr/bin/env python3
"""신규 편입사 원문 보강. II-4 원장과 별도로 III-8/계약 주석의 관측을 보존한다.

연결/별도를 추정하거나 III-8 금액을 II-4 잔고에 더하지 않는다. 실패한 원문은
기존 캐시를 덮지 않는다. 웹 수집 원문은 --raw-dir에만 저장한다(공개 Git 제외).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse

from kce_fetch import toc, find_sections, fetch_section, parallel
from kce_lib import atomic_write, CORP, num_of
from kce_parse import parse_tables, _records, _basis_of, _UNIT_RE, _UNIT_SCALE, unit_scale

HERE = Path(__file__).resolve().parent
CACHE = HERE / 'assets' / 'detail_cache'
VERSION = 4
MONEY = ('amt', 'ub', 'ubimp', 'rc', 'allw', 'contract_liability')


def write_changed(path, obj):
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + '\n'
    path = Path(path)
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(str(path), text)
    return True


def viewer_url(node):
    keys = ('rcpNo', 'dcmNo', 'eleId', 'offset', 'length', 'dtd')
    return 'https://dart.fss.or.kr/report/viewer.do?' + urllib.parse.urlencode(
        {k: node.get(k, '0' if k != 'dtd' else 'dart4.xsd') for k in keys})


def unit_of(lead, cols):
    labels = _UNIT_RE.findall(lead or '') or _UNIT_RE.findall(' '.join(cols))
    if not labels:
        return None
    label = labels[-1].replace(' ', '')
    if re.search(r'USD|EUR|JPY|달러|유로|엔화|외화', label, re.I):
        return None
    return next((name for name, _ in _UNIT_SCALE if name in label), None)


def parse_source(text, node, kind):
    if '<table' not in text.lower() and '<html' not in text.lower():
        raise ValueError('DART 본문 형식 미확인')
    # 여러 중견사는 수주총액을 생략하고 진행률/미청구/미수금만 공시한다.
    # 이 경우 금액을 만들어 넣지 않고 있는 열을 모두 보존한다.
    parsed = {'tables': [], 'unknown_headers': []}
    aliases = {'계약자산': 'ub', '미청구공사': 'ub', '매출채권': 'rc', '공사미수금': 'rc',
               '미청구공사손실충당금': 'ubimp', '계약부채': 'contract_liability'}
    for table_index, table in enumerate(parse_tables(text)):
        table['fields'] = [field or aliases.get(col) for field, col in zip(table['fields'],table['ncols'])]
        table['table_index'] = table_index+1
        rows = _records(table, {'nm', 'pr', 'ub', 'rc'})
        if rows is not None:
            for row in rows:
                if 'contract_liability' in row:
                    v = num_of(row['contract_liability'])
                    row['contract_liability'] = round(v*unit_scale(table['lead'],table['cols']),6) if v is not None else None
                if not row.get('p8_dl') and row.get('ed'):
                    row['p8_dl'] = row['ed']
                # 삼일기업공사처럼 '회사명' 열에 현장명을 적고 품목은 '-'인 원문.
                # 원래 회사명 셀은 보존하고 어떤 열을 이름으로 사용했는지 남긴다.
                if (row.get('nm') or '').strip() in ('', '-', '—') and row.get('p8_ent'):
                    row['nm'] = row['p8_ent']
                    row['name_field'] = '회사명 열(품목 공란)'
            parsed['tables'].append(dict(table, rows=rows))
        elif 'pr' in table['fields'] and len(table['rows']) > 0:
            parsed['unknown_headers'].append({'cols': table['cols'], 'n': len(table['rows'])})
    tables = []
    for ti, t in enumerate(parsed['tables']):
        # parse_p8의 등장순서 추정은 신규 경로에 적용하지 않는다.
        basis = _basis_of(t['lead'])
        if basis is None and kind == 'note':
            title = node.get('text', '')
            if '(연결)' in title:
                basis = '연결'
            elif '(별도)' in title:
                basis = '별도'
        unit = unit_of(t['lead'], t['cols'])
        rows = []
        for row in t['rows']:
            row = dict(row)
            if unit is None:
                for key in MONEY:
                    row[key] = None
            rows.append(row)
        tables.append({'id': '%s-%d' % (node['eleId'], t['table_index']),
                       'basis': basis or '미확인', 'basis_method': 'source_label' if basis else 'unknown',
                       'source_unit': unit, 'unit': '백만원' if unit else None,
                       'lead': t['lead'], 'cols': t['cols'], 'rows': rows})
    return {'kind': kind, 'title': node['text'], 'url': viewer_url(node),
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'bytes_utf8': len(text.encode('utf-8')), 'tables': tables,
            'status': 'tables_found' if tables else 'no_recognized_progress_table',
            'unknown_headers': parsed['unknown_headers']}


def collect_one(item, raw_dir=None, force=False):
    stock, quarter, base = item
    rcp = base['rcpNo']
    path = CACHE / stock / (quarter + '.json')
    if path.exists() and not force:
        old = json.loads(path.read_text(encoding='utf-8'))
        if old.get('version') == VERSION and old.get('rcpNo') == rcp:
            return {'stock': stock, 'quarter': quarter, 'status': 'cached'}
        if old.get('rcpNo') == rcp and raw_dir:
            reparsed = []
            for source in old['sources']:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(source['url']).query)
                node = {key: values[0] for key, values in query.items()}
                node['text'] = source['title']
                raw = Path(raw_dir) / stock / quarter / (node['eleId'] + '.html')
                if not raw.exists():
                    break
                text = raw.read_text(encoding='utf-8')
                if hashlib.sha256(text.encode()).hexdigest() != source['sha256']:
                    # text 모드 newline 변환 방지: 원문 해시와 정확히 같아야 재파싱한다.
                    with raw.open(encoding='utf-8', newline='') as stream:
                        text = stream.read()
                if hashlib.sha256(text.encode()).hexdigest() != source['sha256']:
                    raise ValueError('보존 원문 해시 불일치')
                reparsed.append(parse_source(text, node, source['kind']))
            if len(reparsed) == len(old['sources']):
                old.update(version=VERSION, sources=reparsed)
                write_changed(path, old)
                return {'stock': stock, 'quarter': quarter, 'status': 'reparsed',
                        'rows': sum(len(t['rows']) for s in reparsed for t in s['tables'])}
    nodes = toc(rcp)
    if not nodes:
        raise ValueError('%s %s 목차 없음' % (stock, quarter))
    found = find_sections(nodes)
    selected = []
    if 'p8' in found:
        selected.append(('p8', found['p8']))
    # 개별 계약 주석을 추가로 확인한다. 포괄적인 재무제표 전체를 반복 수집하지 않는다.
    for node in nodes:
        if re.search(r'건설계약|공사계약|수주계약', node['text']) and not re.search(r'회계정책|수주상황', node['text']):
            if node['eleId'] not in {n['eleId'] for _, n in selected}:
                selected.append(('note', node))
    sources = []
    for kind, node in selected:
        text = fetch_section(node)
        source = parse_source(text, node, kind)
        if raw_dir:
            raw = Path(raw_dir) / stock / quarter
            raw.mkdir(parents=True, exist_ok=True)
            atomic_write(str(raw / (node['eleId'] + '.html')), text)
        sources.append(source)
    out = {'version': VERSION, 'stock': stock, 'quarter': quarter, 'rcpNo': rcp,
           'report_url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + rcp,
           'sources': sources,
           'ii4_url': viewer_url(found['ii4']) if 'ii4' in found else None,
           'status': 'checked' if selected else 'section_not_found'}
    changed = write_changed(path, out)
    return {'stock': stock, 'quarter': quarter, 'status': 'updated' if changed else 'unchanged',
            'sources': len(sources), 'rows': sum(len(t['rows']) for s in sources for t in s['tables'])}


def _money_close(a, b):
    return a is not None and b is not None and abs(a-b) <= max(1.0, abs(a)*0.001)


def match_row(row, sites, k, company=None):
    """같은 분기 이름 + 발주처/날짜/금액 중 하나가 일치할 때만 1:1 후보를 반환."""
    from kce_series import nm_key, _norm_date, _norm_day
    key = nm_key(row.get('nm'))
    if not key:
        return None, 'name_missing'
    candidates, alternate = [], []
    def client_key(value):
        return nm_key(re.sub(r'주식회사|㈜|\(주\)', '', value or ''))
    for s in sites:
        if s.get('agg') or not s.get('observations', [])[k]:
            continue
        obs = s['observations'][k]
        same_name = nm_key(obs.get('nm')) == key
        client = bool(row.get('cl')) and client_key(row['cl']) == client_key(obs.get('cl'))
        day_a, day_b = _norm_day(row.get('sd')), _norm_day(obs.get('sd'))
        dates = bool(day_a and day_b and day_a == day_b)
        amount = _money_close(row.get('amt'), s['s']['amt'][k])
        if same_name and (client or dates or amount):
            candidates.append(s)
        # 정식 현장명/약칭이 달라도 발주처·계약일·도급액이 모두 같으면 연결 가능.
        month_a, month_b = _norm_date(row.get('sd')), _norm_date(obs.get('sd'))
        month = bool(month_a and month_b and month_a == month_b)
        if amount and client and (dates or month):
            alternate.append(s)
    if len(candidates) == 1:
        return candidates[0], 'exact_name_and_identity'
    if len(candidates) > 1:
        return None, 'ambiguous'
    if len(alternate) == 1:
        return alternate[0], 'client_date_amount'
    return None, 'ambiguous' if alternate else 'no_exact_match'


def enrich(D, cache=None):
    """출처별 III-8 관측과 보수적인 현장 연결. 원래 잔고/진행률은 수정하지 않는다."""
    cache = Path(cache or CACHE)
    for site in D['sites']:
        site.pop('detail', None)
    ledger, observations, unresolved = [], [], []
    for k, q in enumerate(D['fq']):
        p = cache / D['stock'] / (q + '.json')
        if not p.exists():
            ledger.append({'quarter': q, 'status': 'not_collected', 'rows': 0, 'matched': 0})
            continue
        doc = json.loads(p.read_text(encoding='utf-8'))
        if doc.get('rcpNo') != D['src'].get(q):
            ledger.append({'quarter': q, 'status': 'report_changed', 'rows': 0, 'matched': 0})
            continue
        entry = {'quarter': q, 'status': doc['status'], 'rcpNo': doc['rcpNo'],
                 'report_url': doc['report_url'], 'ii4_url': doc.get('ii4_url'),
                 'sources': [{key: s[key] for key in ('title', 'url', 'sha256', 'status')} for s in doc['sources']],
                 'rows': 0, 'matched': 0, 'unmatched': 0, 'unknown_unit': 0, 'unknown_basis': 0}
        seen = set()
        for source in doc['sources']:
            for table in source['tables']:
                for ri, row in enumerate(table['rows']):
                    from kce_series import is_total_row, is_agg_row
                    if is_total_row(row) or is_agg_row(row):
                        continue
                    identity = (table['basis'], json.dumps(row, sort_keys=True, ensure_ascii=False))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    entry['rows'] += 1
                    site, method = match_row(row, D['sites'], k, D['co'])
                    item = dict(row, quarter=q, basis=table['basis'], source_unit=table['source_unit'],
                                url=source['url'], source_title=source['title'],
                                source_hash=source['sha256'], table_id=table['id'],
                                source_row=ri+1, match=method, site_id=site['id'] if site else None)
                    observations.append(item)
                    if table['source_unit'] is None:
                        entry['unknown_unit'] += 1
                    if table['basis'] == '미확인':
                        entry['unknown_basis'] += 1
                    if site:
                        entry['matched'] += 1
                        site.setdefault('detail', []).append(len(observations)-1)
                    else:
                        entry['unmatched'] += 1
                        unresolved.append(len(observations)-1)
        ledger.append(entry)
    # II-4 미연결 관측도 별도 탐색 가능. 기존 잔고/현장 집계에는 절대 편입하지 않는다.
    from kce_series import nm_key, _norm_day, _norm_date
    disclosure = {}
    for i in unresolved:
        row = observations[i]
        key = '|'.join((nm_key(row.get('p8_ent')), nm_key(row.get('nm')),
                        nm_key(row.get('cl')), _norm_day(row.get('sd')) or _norm_date(row.get('sd')) or ''))
        sid = 'p8-' + hashlib.sha256(key.encode()).hexdigest()[:14]
        if sid not in disclosure:
            disclosure[sid] = {'id': sid, 'nm': row.get('nm') or '명칭 미기재', 'cl': row.get('cl') or '',
                               'seg': '공시 계약', 'reg': '미분류', 'sd': row.get('sd'), 'ed': row.get('p8_dl'),
                               'source_only': True, 'detail': [], 'observations': [None]*len(D['fq']),
                               's': {f: [None]*len(D['fq']) for f in ('amt','cmp','bal','pr')}}
        disclosure[sid]['detail'].append(i)
        disclosure[sid]['nm'] = row.get('nm') or disclosure[sid]['nm']
        disclosure[sid]['ed'] = row.get('p8_dl') or disclosure[sid]['ed']
        row['disclosure_id'] = sid
    D['detail'] = {'version': VERSION, 'ledger': ledger, 'observations': observations,
                   'unmatched': unresolved,
                   'disclosure_sites': list(disclosure.values()),
                   'note': '연결·별도 원문 관측을 각각 보존. III-8 표는 중요 계약 일부일 수 있어 회사 총계로 합산하지 않음.'}
    return D


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only')
    ap.add_argument('--raw-dir')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    legacy = {v['stock'] for v in CORP.values()}
    only = set(args.only.split(',')) if args.only else None
    items = []
    for path in sorted((HERE / 'assets' / 'series_cache').glob('*/*.json')):
        stock, quarter = path.parent.name, path.stem
        if stock in legacy or (only and stock not in only):
            continue
        base = json.loads(path.read_text(encoding='utf-8'))
        if base.get('ok') and re.fullmatch(r'\d{14}', base.get('rcpNo') or ''):
            items.append((stock, quarter, base))
    failures = []
    def run(item):
        try:
            return collect_one(item, args.raw_dir, args.force)
        except Exception as exc:
            return {'stock': item[0], 'quarter': item[1], 'status': 'error',
                    'error': '%s: %s' % (type(exc).__name__, str(exc)[:180])}
    def done(index, item, result):
        if isinstance(result, Exception):
            result = {'stock': item[0], 'quarter': item[1], 'status': 'error', 'error': str(result)[:180]}
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result['status'] == 'error':
            failures.append(result)
    parallel(items, run, on_done=done)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
