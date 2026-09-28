# 파일명에 탭 접두 `kgrid_` 를 붙였다 — kgrid_forecast_section.py 머리말과 같은 이유(섹터 도구의 동명 모듈 충돌 회피).
#!/usr/bin/env python3
"""KGRID 수주 상세 뷰 3종 — 간트 · 분기 전환 스케줄 · 발주처별. stdlib + inline SVG, 외부 자산 없음.

API (kgrid_forecast_section.render_forecast_section 과 같은 결):
  build_gantt(rows, uid, today=None) -> dict(html, bars, no_end, canceled, recs)
  build_schedule(rows, uid, today=None, forecast_entry=None, scenario='base', window=None) -> dict(html, buckets, ...)
  build_clients(rows, uid, today=None, top_n=8) -> dict(html, top, rest, anon, total_count, total_amount, ...)
  render_orders_section(panel_entry, contracts, forecast_entry=None, today=None) -> str
CLI: python3 -B output/kgrid_orders_views.py [stock ...]   → output/orders_sections/<stock>.html

원칙: 원문이 지지하는 것만 싣는다. 금액은 공시 원문 금액×공시 환율을 백만원으로 다시 계산해 환산값과 맞을 때만 쓴다.
값이 없으면 칸을 비우고 이유를 적는다. 추정으로 메우지 않는다.
"""
import sys
sys.dont_write_bytecode = True
import datetime
import html
import json
import math
import re
from collections import Counter, OrderedDict
from pathlib import Path

DEFAULT_WINDOW = ((2026, 3), (2028, 4))          # Y+2 창 (2026Q3~2028Q4) — forecast_entry 가 있으면 그 분기 목록을 따른다
BRANCH_LABEL = {'long_lead': '장납기', 'turnover': '회전', 'unknown': '미상'}
BRANCH_COLOR = {'long_lead': '#219ebc', 'turnover': '#f4a261', 'unknown': '#8d99ae'}
BRANCH_ORDER = ('long_lead', 'turnover', 'unknown')
FORECAST_COLOR = '#2a9d8f'
PRODUCT_LABEL = {'ehv': '초고압', 'cable': '전력선·케이블', 'converter': '변환·ESS', 'switchgear': '수배전반',
                 'breaker': '차단기', 'dist_tr': '배전변압기', 'fitting': '금구류'}
TURNOVER_TAGS = ('switchgear', 'breaker', 'dist_tr', 'fitting')
DURATION_TAGS = ('cable', 'converter')
ANON_LABELS = {'', '-', '—', '–', '개인', '비공개', '미공개', '미정', '해당없음', '해당사항없음', '익명', '없음', 'n/a', 'N/A'}
AFFIL_REL = ('계열회사', '자회사', '관계회사', '모회사', '최대주주', '종속회사')
CORP_TOKENS = ('주식회사', '유한회사', '(주)', '㈜', '(유)')
SUFFIX_TOKENS = {'co', 'ltd', 'limited', 'inc', 'incorporated', 'corp', 'corporation', 'company', 'llc', 'pte', 'pty',
                 'gmbh', 'plc', 'sa', 'nv', 'sf', 'ag', 'spa', 'bv', 'llp', 'lp'}
KV_RE = re.compile(r'(\d{2,3})(?=\s*(?:/\s*\d{2,3}\s*)?[kK][vV])')
EHV_WORDS = ('초고압', 'HVDC', 'EHV')
EXPECT_RE = re.compile(r'예상되는\s*계약\s*기간\s*종료일은\s*(\d{4})\s*년도?\s*(\d)\s*분기')
AMOUNT_TOL = 0.01                                 # 원문 금액×환율 대 환산값 허용 오차(억원 반올림 흡수)
CANCEL_AMT_TOL = 0.005


# ---------------------------------------------------------------- 공용 소도구
def esc(x):
    return html.escape('' if x is None else str(x), quote=True)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def fmt(v):
    return f'{v:,.3f}' if number(v) else '—'


def fmt0(v):
    return f'{v:,.0f}' if number(v) else '—'


def pct(v):
    return f'{v:.1f}%' if number(v) else '—'


def trunc(s, n):
    s = '' if s is None else str(s)
    return s if len(s) <= n else s[:max(1, n - 1)] + '…'


def parse_date(s):
    if not isinstance(s, str):
        return None
    m = re.fullmatch(r'\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*', s)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def as_date(x):
    if x is None:
        return datetime.date.today()
    if isinstance(x, datetime.datetime):
        return x.date()
    if isinstance(x, datetime.date):
        return x
    if isinstance(x, str):
        d = parse_date(x)
        if d:
            return d
    raise ValueError('today must be a date or YYYY-MM-DD')


def shift_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:              # 2월 29일
        return d.replace(year=d.year + n, day=28)


def q_of(d):
    return (d.year, (d.month - 1) // 3 + 1)


def q_label(q):
    return f'{q[0]}Q{q[1]}'


def q_parse(s):
    m = re.search(r'(\d{4})\D{0,2}Q([1-4])', str(s or ''))
    return (int(m.group(1)), int(m.group(2))) if m else None


def q_range(a, b):
    out = []
    y, q = a
    while (y, q) <= tuple(b):
        out.append((y, q))
        q += 1
        if q > 4:
            q, y = 1, y + 1
    return out


def svg_text(x, y, s, anchor='start', size=10, fill='currentColor', extra=''):
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" fill="{fill}"{extra}>{esc(s)}</text>'


def scroll_box(svg):
    return '<div style="overflow-x:auto">' + svg + '</div>'


def table(headers, rows, caption, row_attrs=None, table_attr=''):
    body = []
    for i, row in enumerate(rows):
        a = ''
        if row_attrs and i < len(row_attrs) and row_attrs[i]:
            a = ' ' + row_attrs[i]
        cells = ''.join(('<th scope="row">' if j == 0 else '<td>') + esc(v) + ('</th>' if j == 0 else '</td>')
                        for j, v in enumerate(row))
        body.append('<tr' + a + '>' + cells + '</tr>')
    ta = (' ' + table_attr) if table_attr else ''
    return ('<div style="overflow-x:auto"><table' + ta + ' style="width:100%;border-collapse:collapse"><caption style="text-align:left">' +
            esc(caption) + '</caption><thead><tr>' + ''.join('<th scope="col">' + esc(h) + '</th>' for h in headers) +
            '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>')


# ---------------------------------------------------------------- 행 정규화
def party_key(p):
    """표기 차이(법인 접미사·구두점·대소문자·공백)만 접는다. 괄호 안 별칭은 남긴다 — 다른 이름을 같은 상대로 합치지 않기 위해."""
    s = str(p or '').lower()
    for t in CORP_TOKENS:
        s = s.replace(t, ' ')
    s = re.sub(r'[^0-9a-z가-힣]+', ' ', s)
    toks = [t for t in s.split() if t not in SUFFIX_TOKENS]
    return ''.join(toks)


def anon_label(row):
    p = str(row.get('party') or '').strip()
    if p in ANON_LABELS or '비밀유지' in p or '비공개' in p:
        return p or '(미기재)'
    return None


def branch_of(name, product, years):
    """장납기/회전 판정. 1) 이름의 전압 계급(≥154kV)·초고압·HVDC·EHV 2) 품목 태그 3) cable/converter 는 계약기간 1.0년 문턱 4) 그 외 미상."""
    text = name or ''
    kvs = [int(k) for k in KV_RE.findall(text)]
    if any(k >= 154 for k in kvs) or any(w in text for w in EHV_WORDS):
        return 'long_lead', '계약명의 전압 계급/초고압/HVDC'
    if product == 'ehv':
        return 'long_lead', '품목 태그 ehv'
    if product in TURNOVER_TAGS:
        return 'turnover', '품목 태그 ' + product
    if product in DURATION_TAGS:
        if number(years):
            return ('long_lead' if years >= 1.0 else 'turnover'), f'품목 태그 {product} + 계약기간 {years:.1f}년(문턱 1.0년)'
        return 'unknown', f'품목 태그 {product} · 계약기간 없음'
    return 'unknown', '품목 태그 없음'


def verified_amount(row):
    """amt_krw_m 을 그대로 믿지 않는다. 원문 금액(amt)×공시 환율(fx)/1e6 이 환산값과 1% 안에서 맞을 때만 금액으로 쓴다."""
    v = row.get('amt_krw_m')
    if not number(v):
        return None, '공시 금액 없음(원화 환산값 미기재)'
    amt, cur, fx = row.get('amt'), row.get('cur'), row.get('fx')
    if not number(amt):
        return None, '원문 금액 없음 — 환산값을 검증할 수 없어 미표시'
    if cur == 'KRW':
        calc = amt / 1e6
    elif isinstance(cur, str) and cur and number(fx):
        calc = amt * fx / 1e6
    elif isinstance(cur, str) and cur:
        return None, f'외화({cur}) 공시 환율 없음 — 원화 환산 미검증'
    else:
        return None, '통화 미상 — 원화 환산 미검증'
    if v <= 0 or abs(calc - v) > AMOUNT_TOL * abs(v):
        return None, '원문 금액×환율이 환산값과 1% 넘게 어긋남 — 미표시'
    return float(v), ''


def end_reason(r):
    parts = []
    period = r['period']
    if r['raw'].get('end') not in (None, '') and r['end'] is None:
        parts.append('종료일 문구 “' + str(r['raw'].get('end')) + '”를 날짜로 읽지 못함')
    elif period.endswith('~'):
        parts.append('공시 계약기간의 종료일이 비어 있음(“' + period + '”)')
    elif not period:
        parts.append('공시에 계약기간 항목 없음')
    else:
        parts.append('공시 계약기간 “' + period + '”에서 종료일을 읽지 못함')
    m = EXPECT_RE.search(r['note'])
    if m:
        parts.append(f'주석 인용: {m.group(1)}년 {m.group(2)}분기 종료 예상 — 스케줄에는 넣지 않음')
    return ' · '.join(parts)


def prepare(rows, today):
    """원장 행 → 뷰용 레코드. 해지 공시 행과 원 계약 행을 짝지어 status(active/ended/canceled)를 정한다."""
    recs = []
    for idx, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get('name') or '').strip() or '(계약명 없음)'
        party = str(row.get('party') or '').strip()
        product = row.get('product') if isinstance(row.get('product'), str) and row.get('product') else None
        start, end = parse_date(row.get('start')), parse_date(row.get('end'))
        signed = parse_date(row.get('signed')) or parse_date(row.get('date'))
        notes = []
        if start and end and start > end:
            notes.append(f'시작일 {start.isoformat()} 이 종료일 {end.isoformat()} 뒤 — 시작일 무시')
            start = None
        years = row.get('years') if number(row.get('years')) else None
        if years is None and start and end:
            years = round((end - start).days / 365.25, 1)
        amount, amount_note = verified_amount(row)
        branch, branch_why = branch_of(name, product, years)
        bar_start, bar_kind = start, 'full'
        if end and not start:
            if signed:
                bar_start, bar_kind = signed, 'start_from_signed'
            else:
                bar_kind = 'end_only'
        party_rel = str(row.get('party_rel') or '').strip()
        recs.append({
            'idx': idx, 'rcp': str(row.get('rcp') or ''), 'raw': row,
            'name': name, 'name_key': re.sub(r'\s+', '', name).lower(),
            'party': party, 'party_key': party_key(party), 'anon': anon_label(row),
            'party_rel': party_rel,
            'affiliate': bool(row.get('affiliate')) or party_rel in AFFIL_REL,
            'utility': bool(row.get('utility')),
            'withheld': bool(row.get('withheld')), 'withheld_why': str(row.get('withheld_why') or '').strip(),
            'withheld_until': str(row.get('withheld_until') or '').strip(),
            'product': product, 'branch': branch, 'branch_why': branch_why,
            'start': start, 'end': end, 'signed': signed, 'years': years,
            'bar_start': bar_start, 'bar_kind': bar_kind,
            'amount': amount, 'amount_note': amount_note,
            'canceled': bool(row.get('canceled')), 'cancel_why': str(row.get('cancel_why') or '').strip(),
            'canceled_by': None, 'matched_original': None, 'cancel_match_note': '',
            'kind_raw': str(row.get('kind_raw') or '').strip(), 'region_raw': str(row.get('region_raw') or '').strip(),
            'region': str(row.get('region') or ''),
            'subsidiary': bool(row.get('subsidiary')), 'sub_name': str(row.get('sub_name') or '').strip(),
            'period': str(row.get('period') or '').strip(), 'note': str(row.get('note') or ''),
            'doc_title': str(row.get('doc_title') or '').strip(), 'notes': notes,
            'end_note': '', 'status': '',
        })
    # 해지 공시 ↔ 원 계약 짝짓기: 같은 계약명(공백 무시)·같은 상대. 후보가 여럿이면 금액이 같은 것, 그래도 여럿이면 특정하지 않는다.
    originals = {}
    for r in recs:
        if not r['canceled']:
            originals.setdefault((r['name_key'], r['party_key']), []).append(r)
    for c in recs:
        if not c['canceled']:
            continue
        cands = [o for o in originals.get((c['name_key'], c['party_key']), []) if o['canceled_by'] is None]
        if not cands:
            c['cancel_match_note'] = '원 계약 행 없음(원장 창 밖이거나 이름·상대 표기가 다름) — 해지 행만 표시'
            continue
        exact = [o for o in cands if number(o['amount']) and number(c['amount'])
                 and abs(o['amount'] - c['amount']) <= CANCEL_AMT_TOL * max(abs(o['amount']), 1e-9)]
        pool = exact if exact else cands
        pick = None
        if len(pool) == 1:
            pick = pool[0]
        elif exact:
            pick = max(exact, key=lambda o: (o['signed'] or datetime.date.min, o['idx']))
        if pick is None:
            c['cancel_match_note'] = f'원 계약 후보 {len(cands)}건 — 특정하지 못해 해지 행만 표시(원 계약 행은 잔고에 남음)'
            continue
        pick['canceled_by'] = c
        c['matched_original'] = pick
        c['cancel_match_note'] = ('원 계약 행(' + (pick['signed'].isoformat() if pick['signed'] else '계약일 미상') +
                                  ' 체결)을 잔고에서 제외' + ('' if exact else ' · 해지 금액≠원 계약 금액(부분 해지로 봄)'))
    for r in recs:
        if r['canceled'] or r['canceled_by'] is not None:
            r['status'] = 'canceled'
        elif r['end'] is not None and r['end'] < today:
            r['status'] = 'ended'
        else:
            r['status'] = 'active'
        if r['end'] is None:
            r['end_note'] = end_reason(r)
    return recs


def select_rows(contracts, stock):
    if isinstance(contracts, dict):
        rows = contracts.get('rows') or []
    else:
        rows = list(contracts or [])
    return [r for r in rows if isinstance(r, dict) and str(r.get('stock') or '') == stock]


def party_text(r):
    if r['anon'] is not None:
        return r['anon'] + (' (' + r['withheld_why'] + ')' if r['withheld_why'] else '')
    return r['party'] or '상대 미기재'


def tooltip(r):
    bits = [r['name'],
            '상대: ' + party_text(r) + (f" [{r['party_rel']}]" if r['party_rel'] and r['party_rel'] != '-' else ''),
            '기간: ' + (r['start'].isoformat() if r['start'] else
                      (('계약일 ' + r['signed'].isoformat() + '부터 표시') if r['bar_kind'] == 'start_from_signed' and r['signed']
                       else '시작일 없음')) + ' ~ ' + (r['end'].isoformat() if r['end'] else '종료일 없음'),
            '금액: ' + (fmt(r['amount']) + ' 백만원' if number(r['amount']) else '미표시(' + r['amount_note'] + ')'),
            '분류: ' + BRANCH_LABEL[r['branch']] + ' — ' + r['branch_why'] +
            (' · 품목 ' + PRODUCT_LABEL.get(r['product'], r['product']) if r['product'] else ''),
            ('유형: ' + r['kind_raw']) if r['kind_raw'] else '',
            ('지역: ' + r['region_raw']) if r['region_raw'] else '',
            ('공시: ' + r['doc_title']) if r['doc_title'] else '',
            ('재공시: 자회사 ' + r['sub_name']) if r['subsidiary'] and r['sub_name'] else '']
    bits.extend(r['notes'])
    return ' · '.join(b for b in bits if b)


# ---------------------------------------------------------------- 1. 수주 간트
def gantt_svg(bars, uid, today):
    W, LEFT, RIGHT, ROW, TOP, BOTTOM = 1000, 330, 150, 24, 48, 14
    PLOT = W - LEFT - RIGHT
    H = TOP + ROW * len(bars) + BOTTOM
    starts = [r['bar_start'] for r in bars if r['bar_start'] is not None]
    ends = [r['end'] for r in bars]
    lo = min(starts + ends + [today])
    hi = max(ends + [today])
    lo = max(lo, shift_years(today, -6))
    hi = min(hi, shift_years(today, 8))
    lo = min(lo, today - datetime.timedelta(days=90))
    hi = max(hi, today + datetime.timedelta(days=90))
    span = max(1, (hi - lo).days)

    def x(d):
        return LEFT + max(0.0, min(1.0, (d - lo).days / span)) * PLOT

    max_amt = max([r['amount'] for r in bars if number(r['amount'])] + [0.0])
    n_ended = sum(1 for r in bars if r['status'] == 'ended')
    title = f'수주 간트 · 계약 {len(bars)}건 · 종료일순 · 오늘 {today.isoformat()}'
    desc = (f'가로축 {lo.isoformat()}~{hi.isoformat()}(축 밖은 ◀▶ 표시). 막대 두께는 검증 금액(백만원)에 비례, 색은 장납기/회전/미상. '
            f'오늘 이전에 끝난 {n_ended}건은 흐리게. 시작일이 없어 계약일부터 그린 막대는 점선 테두리.')
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{uid}-title {uid}-desc" '
              f'style="display:block;width:100%;min-width:720px;height:auto" data-gantt-bars="{len(bars)}">',
              f'<title id="{uid}-title">{esc(title)}</title><desc id="{uid}-desc">{esc(desc)}</desc>']
    for y in range(lo.year, hi.year + 2):
        d = datetime.date(y, 1, 1)
        if d < lo or d > hi:
            continue
        xx = x(d)
        chunks.append(f'<line x1="{xx:.1f}" y1="{TOP - 8}" x2="{xx:.1f}" y2="{H - BOTTOM}" stroke="var(--ln,#6b7280)" stroke-opacity=".45"/>')
        chunks.append(svg_text(xx, TOP - 12, str(y), 'middle', 10))
    for i in range(len(bars) + 1):
        yy = TOP + i * ROW
        chunks.append(f'<line x1="{LEFT}" y1="{yy}" x2="{LEFT + PLOT}" y2="{yy}" stroke="var(--ln,#6b7280)" stroke-opacity=".15"/>')
    xt = x(today)
    chunks.append(f'<line x1="{xt:.1f}" y1="{TOP - 26}" x2="{xt:.1f}" y2="{H - BOTTOM}" stroke="var(--a,#e63946)" stroke-width="1.5" stroke-dasharray="4 3" data-today="{today.isoformat()}"/>')
    chunks.append(svg_text(xt, TOP - 30, '오늘 ' + today.isoformat(), 'middle', 10, 'var(--a,#e63946)'))
    for i, r in enumerate(bars):
        yc = TOP + i * ROW + ROW / 2
        color = BRANCH_COLOR[r['branch']]
        amt = r['amount']
        th = (6 + 12 * (amt / max_amt)) if (number(amt) and max_amt > 0) else 5.0
        x1 = x(r['end'])
        ident = r['rcp'] or ('row' + str(r['idx']))
        chunks.append(f'<g data-bar="{esc(ident)}" data-kind="{r["bar_kind"]}" data-branch="{r["branch"]}" data-status="{r["status"]}">'
                      f'<title>{esc(tooltip(r))}</title>')
        op = ' opacity=".45"' if r['status'] == 'ended' else ''
        if r['bar_kind'] == 'end_only':
            chunks.append(f'<path d="M{x1:.1f},{yc - 6:.1f} l6,6 l-6,6 l-6,-6 z" fill="{color}"{op}/>')
        else:
            x0 = x(r['bar_start'])
            w = max(2.0, x1 - x0)
            style = ''
            if not number(amt):
                style = ' fill-opacity=".35" stroke="currentColor" stroke-dasharray="1 2"'
            elif r['bar_kind'] == 'start_from_signed':
                style = ' fill-opacity=".6" stroke="currentColor" stroke-dasharray="3 2"'
            chunks.append(f'<rect x="{x0:.1f}" y="{yc - th / 2:.1f}" width="{w:.1f}" height="{th:.1f}" fill="{color}"{style}{op}/>')
            if r['bar_start'] < lo:
                chunks.append(f'<path d="M{LEFT + 7},{yc - 5:.1f} L{LEFT + 1},{yc:.1f} L{LEFT + 7},{yc + 5:.1f} Z" fill="currentColor"/>')
        if r['end'] > hi:
            chunks.append(f'<path d="M{LEFT + PLOT - 7},{yc - 5:.1f} L{LEFT + PLOT - 1},{yc:.1f} L{LEFT + PLOT - 7},{yc + 5:.1f} Z" fill="currentColor"/>')
        left = trunc(r['name'], 24) + ' · ' + trunc(party_text(r), 12)
        chunks.append(svg_text(LEFT - 8, yc + 4, left, 'end', 11))
        right = r['end'].isoformat() + ' · ' + (fmt0(amt) if number(amt) else '금액 미표시')
        chunks.append(svg_text(LEFT + PLOT + 8, yc + 4, right, 'start', 10))
        chunks.append('</g>')
    chunks.append('</svg>')
    return ''.join(chunks)


def legend_html():
    sw = ''.join(f'<span style="display:inline-block;width:.9em;height:.9em;background:{BRANCH_COLOR[b]};vertical-align:middle;margin-right:.25em"></span>{BRANCH_LABEL[b]} '
                 for b in BRANCH_ORDER)
    return ('<p>' + sw + ' · 두께=검증 금액(백만원) · 흐림=오늘 이전 종료 · 점선 테두리=시작일 미기재(계약일부터) · '
            '◆=시작일·계약일 모두 없음(종료일만) · ◀▶=축 범위 밖 · 붉은 점선=오늘. 장납기=초고압·HVDC, 회전=배전(수배전반·차단기·배전변압기·금구), 미상=근거 없음.</p>')


def build_gantt(rows, uid, today=None):
    today = as_date(today)
    recs = prepare(rows, today)
    bars = [r for r in recs if r['status'] != 'canceled' and r['end'] is not None]
    bars.sort(key=lambda r: (r['end'], r['bar_start'] or r['end'], r['name']))
    no_end = [r for r in recs if r['status'] != 'canceled' and r['end'] is None]
    no_end.sort(key=lambda r: (r['signed'] or datetime.date.min, r['idx']))
    canceled = [r for r in recs if r['status'] == 'canceled']
    canceled.sort(key=lambda r: (r['signed'] or datetime.date.min, r['idx']))
    chunks = [legend_html()]
    if bars:
        chunks.append(scroll_box(gantt_svg(bars, uid, today)))
    else:
        chunks.append('<p data-gantt-empty="1">종료일이 있는 계약이 없어 간트 막대를 그리지 않았습니다.</p>')
    n_sub = sum(1 for r in bars if r['bar_kind'] == 'start_from_signed')
    n_unamt = sum(1 for r in bars if not number(r['amount']))
    bits = [f'막대 {len(bars)}건 = 취소되지 않은 계약 중 종료일이 있는 건.']
    if n_sub:
        bits.append(f'{n_sub}건은 시작일이 없어 계약일부터 점선으로 그렸습니다(추정 아님, 공시 계약일).')
    if n_unamt:
        bits.append(f'{n_unamt}건은 금액을 검증하지 못해 얇은 점선 막대이며 금액 라벨을 비웠습니다.')
    chunks.append('<p>' + ' '.join(bits) + '</p>')
    if no_end:
        rows_ = [[r['name'], party_text(r), r['signed'].isoformat() if r['signed'] else '—',
                  r['start'].isoformat() if r['start'] else '—',
                  fmt(r['amount']) if number(r['amount']) else '— ' + r['amount_note'],
                  BRANCH_LABEL[r['branch']] + (' · ' + PRODUCT_LABEL.get(r['product'], r['product']) if r['product'] else ''),
                  r['end_note'] + (' · ' + ' · '.join(r['notes']) if r['notes'] else '')] for r in no_end]
        chunks.append(table(['계약명', '상대', '계약일', '시작일', '금액(백만원)', '분류', '종료일이 없는 이유'], rows_,
                            f'별도 묶음 · 종료일 없는 계약 {len(no_end)}건 — 간트·분기 스케줄에 넣지 않음(발주처 집계에는 포함)',
                            [f'data-no-end="{esc(r["rcp"] or r["idx"])}"' for r in no_end], 'data-gantt-no-end="1"'))
    else:
        chunks.append('<p data-gantt-no-end="0">종료일 없는 계약: 없음.</p>')
    if canceled:
        rows_ = []
        for r in canceled:
            if r['canceled']:
                rows_.append([r['name'], party_text(r), '해지 공시', r['signed'].isoformat() if r['signed'] else '—',
                              fmt(r['amount']) if number(r['amount']) else '— ' + r['amount_note'],
                              r['cancel_why'] or '사유 미기재', r['cancel_match_note']])
            else:
                c = r['canceled_by']
                rows_.append([r['name'], party_text(r), '원 계약(해지됨)', r['signed'].isoformat() if r['signed'] else '—',
                              fmt(r['amount']) if number(r['amount']) else '— ' + r['amount_note'],
                              (c['cancel_why'] or '사유 미기재') if c else '',
                              '해지 공시 ' + ((c['signed'].isoformat() if c and c['signed'] else '일자 미상')) + ' 에 의해 제외'])
        chunks.append(table(['계약명', '상대', '행 종류', '일자', '금액(백만원)', '해지 사유', '처리'], rows_,
                            f'해지 · {len(canceled)}행(해지 공시 {sum(1 for r in canceled if r["canceled"])}건 + 짝지어진 원 계약 {sum(1 for r in canceled if not r["canceled"])}건) — 모든 뷰에서 제외',
                            [f'data-canceled="{esc(r["rcp"] or r["idx"])}"' for r in canceled], 'data-gantt-canceled="1"'))
    return {'html': ''.join(chunks), 'bars': bars, 'no_end': no_end, 'canceled': canceled, 'recs': recs, 'today': today}


# ---------------------------------------------------------------- 2. 분기 전환 스케줄
def shown(row):
    """kgrid_forecast_section.shown 과 같은 규칙 — 전체값 → 기존 잔고분 → 일부 행 잔고분 순으로 보여줄 값을 고른다."""
    if number(row.get('value')):
        return row['value'], 'interval', '범위 전체'
    if number(row.get('existing_backlog_revenue')):
        return row['existing_backlog_revenue'], 'partial_existing_interval', '기존 잔고분만'
    if number(row.get('covered_sites_partial_revenue')):
        return row['covered_sites_partial_revenue'], 'covered_sites_partial_interval', '일부 행 잔고분만'
    return None, 'interval', '미추정'


def forecast_quarters(forecast_entry, scenario='base'):
    if not isinstance(forecast_entry, dict):
        return {}, 'Y+2 추정 항목 없음(forecast_entry 미제공) — 추정 칸을 비움'
    if forecast_entry.get('status') == 'unavailable':
        return {}, '페이지의 Y+2 추정이 미추정(unavailable) 상태 — 추정 칸을 비움'
    if forecast_entry.get('money_unit') not in (None, 'KRW_million'):
        return {}, '추정 금액 단위 미확인(money_unit=' + str(forecast_entry.get('money_unit')) + ') — 금액 비교 안 함'
    sc = (forecast_entry.get('scenarios') or {}).get(scenario) or {}
    out = {}
    for r in sc.get('quarterly') or []:
        if not isinstance(r, dict):
            continue
        q = q_parse(r.get('quarter'))
        if not q:
            continue
        v, key, kind = shown(r)
        b = r.get(key) or {}
        out[q] = {'value': v, 'kind': kind, 'lower': b.get('lower'), 'upper': b.get('upper'),
                  'existing': r.get('existing_backlog_revenue'), 'new': r.get('new_order_revenue'),
                  'reasons': list(r.get('reason_codes') or [])}
    if not out:
        return {}, f'추정({scenario}) 분기 행 없음 — 추정 칸을 비움'
    if forecast_entry.get('money_unit') != 'KRW_million' and any(number(x['value']) for x in out.values()):
        return {}, '추정에 금액이 있으나 money_unit 이 KRW_million 이 아님 — 금액 비교 안 함'
    return out, ''


def new_bucket(label, kind):
    return {'label': label, 'kind': kind, 'count': 0, 'amount': 0.0, 'unknown': 0,
            'by_branch': {b: 0.0 for b in BRANCH_ORDER}, 'count_branch': {b: 0 for b in BRANCH_ORDER}, 'items': []}


def bucket_add(b, r):
    b['count'] += 1
    b['count_branch'][r['branch']] += 1
    if number(r['amount']):
        b['amount'] += r['amount']
        b['by_branch'][r['branch']] += r['amount']
    else:
        b['unknown'] += 1
    b['items'].append(r)


def schedule_svg(buckets, fq, uid, f_note):
    labels = list(buckets.keys())
    n = max(1, len(labels))
    W, H, LEFT, RIGHT, TOP, BASE = 960, 262, 96, 16, 40, 200
    PLOT = W - LEFT - RIGHT
    slot = PLOT / n
    tops = [b['amount'] for b in buckets.values()] + [fq[q]['value'] for q in fq if number(fq[q]['value'])]
    top = max([1e-9] + tops)

    def y(v):
        return BASE - v / top * (BASE - TOP)

    title = '분기 전환 스케줄 · 종료일 기준 계약 합계(장납기/회전/미상 누적) 옆에 Y+2 기준 추정 · 백만원'
    descs = []
    for lab, b in buckets.items():
        f = fq.get(q_parse(lab))
        descs.append(f"{lab}: 끝나는 계약 {b['count']}건 합계 {fmt(b['amount'])}" +
                     (f", 추정 {fmt(f['value'])}({f['kind']})" if f else ', 추정 없음'))
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{uid}-title {uid}-desc" '
              f'style="display:block;width:100%;min-width:640px;height:auto">',
              f'<title id="{uid}-title">{esc(title)}</title><desc id="{uid}-desc">{esc(" / ".join(descs))} {esc(f_note)}</desc>',
              f'<line x1="{LEFT}" y1="{BASE}" x2="{W - RIGHT}" y2="{BASE}" stroke="var(--ln,#6b7280)"/>',
              svg_text(LEFT - 6, TOP + 4, fmt0(top), 'end', 10), svg_text(LEFT - 6, BASE + 4, '0', 'end', 10)]
    for i, lab in enumerate(labels):
        b = buckets[lab]
        xc = LEFT + (i + .5) * slot
        chunks.append(f'<g data-quarter="{esc(lab)}" data-count="{b["count"]}" data-amount="{b["amount"]:.3f}"><title>{esc(descs[i])}</title>')
        off = 0.0
        for br in BRANCH_ORDER:
            h = b['by_branch'][br]
            if h > 0:
                chunks.append(f'<rect data-part="{br}" x="{xc - 26:.1f}" y="{y(off + h):.1f}" width="24" height="{h / top * (BASE - TOP):.3f}" fill="{BRANCH_COLOR[br]}"/>')
                off += h
        if b['count']:
            chunks.append(svg_text(xc - 14, y(off) - 4, f"{b['count']}건" + (f"(미표시 {b['unknown']})" if b['unknown'] else ''), 'middle', 9))
        f = fq.get(q_parse(lab))
        if f and number(f['value']):
            chunks.append(f'<rect data-part="forecast" x="{xc + 2:.1f}" y="{y(f["value"]):.1f}" width="16" height="{f["value"] / top * (BASE - TOP):.3f}" fill="{FORECAST_COLOR}"/>')
            if number(f['lower']) and number(f['upper']):
                fx = xc + 10
                chunks.append(f'<path data-part="sensitivity" d="M{fx:.1f},{y(f["lower"]):.1f}V{y(f["upper"]):.1f} M{fx - 4:.1f},{y(f["lower"]):.1f}H{fx + 4:.1f} M{fx - 4:.1f},{y(f["upper"]):.1f}H{fx + 4:.1f}" stroke="currentColor" fill="none"/>')
            if f['kind'] != '범위 전체':
                chunks.append(svg_text(xc + 10, TOP - 8, '부분', 'middle', 9))
        elif f:
            chunks.append(svg_text(xc + 10, BASE - 8, '미추정', 'middle', 9))
        chunks.append(svg_text(xc, BASE + 14, lab, 'middle', 10))
        chunks.append('</g>')
    lx = LEFT
    for br in BRANCH_ORDER:
        chunks.append(f'<rect x="{lx}" y="{H - 16}" width="10" height="10" fill="{BRANCH_COLOR[br]}"/>')
        chunks.append(svg_text(lx + 13, H - 7, '계약 종료 · ' + BRANCH_LABEL[br], 'start', 9))
        lx += 110
    chunks.append(f'<rect x="{lx}" y="{H - 16}" width="10" height="10" fill="{FORECAST_COLOR}"/>')
    chunks.append(svg_text(lx + 13, H - 7, 'Y+2 기준 추정(페이지 값 그대로)', 'start', 9))
    chunks.append('</svg>')
    return ''.join(chunks)


def build_schedule(rows, uid, today=None, forecast_entry=None, scenario='base', window=None):
    today = as_date(today)
    recs = prepare(rows, today)
    fq, f_note = forecast_quarters(forecast_entry, scenario)
    if window is not None:
        qs = q_range(window[0], window[1])
    elif fq:
        qs = q_range(min(fq), max(fq))
    else:
        qs = q_range(DEFAULT_WINDOW[0], DEFAULT_WINDOW[1])
    first, last = qs[0], qs[-1]
    live = [r for r in recs if r['status'] != 'canceled']
    buckets = OrderedDict((q_label(q), new_bucket(q_label(q), 'in')) for q in qs)
    before = new_bucket(q_label(first) + ' 이전 종료', 'before')
    after = new_bucket(q_label(last) + ' 이후 종료', 'after')
    none = new_bucket('종료일 없음', 'none')
    for r in live:
        if r['end'] is None:
            b = none
        else:
            q = q_of(r['end'])
            b = before if q < first else after if q > last else buckets[q_label(q)]
        bucket_add(b, r)
    all_buckets = list(buckets.values()) + [before, after, none]
    total_count = sum(b['count'] for b in all_buckets)
    total_amount = sum(b['amount'] for b in all_buckets)
    total_unknown = sum(b['unknown'] for b in all_buckets)
    chunks = [scroll_box(schedule_svg(buckets, fq, uid, f_note))]
    rows_, attrs = [], []
    mismatches = []
    for lab, b in buckets.items():
        f = fq.get(q_parse(lab))
        bl = '/'.join(str(b['count_branch'][x]) for x in BRANCH_ORDER)
        if f is None:
            fv, frange, diff, note = '—', '—', '—', f_note
        elif number(f['value']):
            fv = fmt(f['value']) + ('' if f['kind'] == '범위 전체' else ' (' + f['kind'] + ')')
            frange = fmt(f['lower']) + ' ~ ' + fmt(f['upper']) if number(f['lower']) and number(f['upper']) else '—'
            d = f['value'] - b['amount']
            diff = fmt(d)
            if b['count'] == 0:
                note = '이 분기에 끝나는 계약 없음 — 추정은 잔고 소진·신규수주 가정분이라 계약 합계와 직접 비교 불가'
            else:
                note = '추정이 계약 종료 합계보다 ' + ('큼' if d > 0 else '작음' if d < 0 else '같음') + ' — 어긋남을 그대로 둠(조정 안 함)'
            if b['unknown']:
                note += f' · 금액 미표시 {b["unknown"]}건은 합계에서 빠짐'
            mismatches.append((lab, b['count'], b['amount'], f['value'], d))
        else:
            fv, frange, diff = '미추정', '—', '—'
            note = '추정 없음' + (': ' + ', '.join(f['reasons']) if f['reasons'] else '')
        rows_.append([lab, f"{b['count']}건", fmt(b['amount']) if b['count'] - b['unknown'] > 0 else ('—' if b['count'] == 0 else '— 금액 미표시'),
                      str(b['unknown']), bl, fv, frange, diff, note])
        attrs.append(f'data-sched-row="{esc(lab)}" data-count="{b["count"]}"')
    for b, why in ((before, '창 이전(이미 종료) — 스케줄 막대에 넣지 않음'), (after, '창 이후 — 스케줄 막대에 넣지 않음'),
                   (none, '종료일 없음 — 어느 분기에도 넣지 않음(간트 별도 묶음 참조)')):
        bl = '/'.join(str(b['count_branch'][x]) for x in BRANCH_ORDER)
        rows_.append([b['label'], f"{b['count']}건", fmt(b['amount']) if b['count'] - b['unknown'] > 0 else ('—' if b['count'] == 0 else '— 금액 미표시'),
                      str(b['unknown']), bl, '—', '—', '—', why])
        attrs.append(f'data-sched-row="{esc(b["kind"])}" data-count="{b["count"]}"')
    rows_.append(['합계(취소 제외 전체)', f'{total_count}건', fmt(total_amount), str(total_unknown),
                  '/'.join(str(sum(b['count_branch'][x] for b in all_buckets)) for x in BRANCH_ORDER), '—', '—', '—',
                  '분기·창 밖·종료일 없음을 더하면 취소 제외 계약 전체와 같아야 함'])
    attrs.append(f'data-sched-row="total" data-count="{total_count}"')
    chunks.append(table(['분기', '끝나는 계약', '계약 합계(백만원)', '금액 미표시', '장납기/회전/미상(건)', 'Y+2 추정(기준)', '추정 민감도 범위', '추정 − 계약', '비고'],
                        rows_, '분기 전환 스케줄 · 종료일 분기 기준 · 백만원(검증 금액만) · 추정은 페이지의 Y+2 기준 시나리오 값을 옮긴 것',
                        attrs, 'data-schedule="1"'))
    note = ('<p>계약 합계는 <strong>계약 총액을 종료 분기에 한꺼번에 놓은 것</strong>이고, Y+2 추정은 분기별 납품 대용치(잔고 소진분+신규수주 가정분)입니다. '
            '두 수는 개념이 달라 어긋나는 것이 정상이며, 어긋남을 맞추려고 어느 쪽도 조정하지 않았습니다. 추정이 없는 칸은 이유를 비고에 적었습니다.</p>')
    if f_note and not fq:
        note += '<p data-forecast-note="1">' + esc(f_note) + '</p>'
    chunks.append(note)
    return {'html': ''.join(chunks), 'buckets': buckets, 'before': before, 'after': after, 'none': none,
            'all_buckets': all_buckets, 'total_count': total_count, 'total_amount': total_amount, 'total_unknown': total_unknown,
            'forecast': fq, 'forecast_note': f_note, 'mismatches': mismatches, 'quarters': qs, 'recs': recs, 'today': today}


# ---------------------------------------------------------------- 3. 발주처(고객)별
def new_group(label, anonymous):
    return {'label': label, 'anonymous': anonymous, 'count': 0, 'amount': 0.0, 'unknown': 0, 'max_end': None, 'no_end': 0,
            'variants': Counter(), 'rels': set(), 'utility': False, 'affiliate': False, 'withheld': set(), 'regions': set(),
            'branches': Counter(), 'items': []}


def group_add(g, r):
    g['count'] += 1
    if number(r['amount']):
        g['amount'] += r['amount']
    else:
        g['unknown'] += 1
    if r['end'] is None:
        g['no_end'] += 1
    elif g['max_end'] is None or r['end'] > g['max_end']:
        g['max_end'] = r['end']
    g['variants'][r['party'] or r['anon'] or '(미기재)'] += 1
    if r['party_rel'] and r['party_rel'] != '-':
        g['rels'].add(r['party_rel'])
    g['utility'] = g['utility'] or r['utility']
    g['affiliate'] = g['affiliate'] or r['affiliate']
    if r['withheld_why']:
        g['withheld'].add(r['withheld_why'])
    if r['region']:
        g['regions'].add(r['region'])
    g['branches'][r['branch']] += 1
    g['items'].append(r)


def group_label(g):
    if not g['variants']:
        return g['label']
    main = g['variants'].most_common(1)[0][0]
    others = [v for v, _ in g['variants'].most_common() if v != main]
    return main + (' (표기 변형: ' + ', '.join(others) + ')' if others else '')


def clients_svg(items, uid):
    """items: (label, share or None, color, sub)."""
    n = max(1, len(items))
    W, LEFT, RIGHT, ROW = 960, 320, 90, 20
    PLOT = W - LEFT - RIGHT
    H = 8 + n * ROW + 6
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{uid}-title" '
              f'style="display:block;width:100%;min-width:640px;height:auto">',
              f'<title id="{uid}-title">발주처별 비중 · 활성 계약 검증 금액 기준</title>']
    for i, (label, share, color, sub) in enumerate(items):
        yy = 8 + i * ROW
        chunks.append(f'<g data-client-bar="{esc(sub)}">')
        chunks.append(svg_text(LEFT - 8, yy + 14, trunc(label, 34), 'end', 11))
        if number(share):
            w = max(1.0, share / 100.0 * PLOT)
            chunks.append(f'<rect x="{LEFT}" y="{yy + 3}" width="{w:.1f}" height="14" fill="{color}"/>')
            chunks.append(svg_text(LEFT + w + 6, yy + 14, pct(share), 'start', 10))
        else:
            chunks.append(svg_text(LEFT + 4, yy + 14, '금액 미표시 — 비중 없음', 'start', 10))
        chunks.append('</g>')
    chunks.append('</svg>')
    return ''.join(chunks)


def build_clients(rows, uid, today=None, top_n=8):
    today = as_date(today)
    recs = prepare(rows, today)
    basis = [r for r in recs if r['status'] == 'active']
    n_ended = sum(1 for r in recs if r['status'] == 'ended')
    n_canceled = sum(1 for r in recs if r['status'] == 'canceled')
    named, anon = OrderedDict(), OrderedDict()
    for r in basis:
        if r['anon'] is not None:
            g = anon.setdefault(r['anon'], new_group(r['anon'], True))
        else:
            g = named.setdefault(r['party_key'], new_group(r['party'], False))
        group_add(g, r)
    named_list = sorted(named.values(), key=lambda g: (-g['amount'], -g['count'], g['label']))
    top = named_list[:top_n]
    rest_list = named_list[top_n:]
    anon_list = sorted(anon.values(), key=lambda g: (-g['amount'], -g['count'], g['label']))
    total_count = len(basis)
    total_amount = sum(r['amount'] for r in basis if number(r['amount']))
    unknown_count = sum(1 for r in basis if not number(r['amount']))
    rest = new_group(f'나머지 {len(rest_list)}개 발주처', False)
    for g in rest_list:
        for r in g['items']:
            group_add(rest, r)
    rest['label'] = f'나머지 {len(rest_list)}개 발주처'

    def share(g):
        return (g['amount'] / total_amount * 100.0) if (total_amount > 0 and g['count'] - g['unknown'] > 0) else None

    rows_, attrs, bars = [], [], []
    cum = 0.0
    for g in top:
        s = share(g)
        if number(s):
            cum += s
        rel = ', '.join(sorted(g['rels'])) if g['rels'] else '—'
        flags = ('관계회사 ' if g['affiliate'] else '') + ('유틸리티' if g['utility'] else '')
        rows_.append([group_label(g), rel, flags.strip() or '—', f"{g['count']}건", fmt(g['amount']) if g['count'] - g['unknown'] > 0 else '—',
                      str(g['unknown']), (g['max_end'].isoformat() if g['max_end'] else '—') + (f' · 종료일 없음 {g["no_end"]}건' if g['no_end'] else ''),
                      pct(s), pct(cum) if number(s) else '—',
                      ('일부 비공개: ' + ', '.join(sorted(g['withheld']))) if g['withheld'] else ''])
        attrs.append(f'data-client="named" data-count="{g["count"]}"')
        bars.append((group_label(g), s, BRANCH_COLOR['long_lead'] if not g['affiliate'] else '#8ecae6', 'named'))
    for g in anon_list:
        s = share(g)
        rows_.append(['익명 표기 “' + g['label'] + '”' + (' (' + ', '.join(sorted(g['withheld'])) + ')' if g['withheld'] else ''),
                      '—', '익명', f"{g['count']}건", fmt(g['amount']) if g['count'] - g['unknown'] > 0 else '—',
                      str(g['unknown']), (g['max_end'].isoformat() if g['max_end'] else '—') + (f' · 종료일 없음 {g["no_end"]}건' if g['no_end'] else ''),
                      pct(s), '—', '누구인지 알 수 없어 한 상대로 세지 않음 — 상위·집중도 계산에서 제외'])
        attrs.append(f'data-client="anon" data-count="{g["count"]}"')
        bars.append(('익명 “' + g['label'] + '”', s, BRANCH_COLOR['unknown'], 'anon'))
    if rest_list:
        s = share(rest)
        rows_.append([rest['label'], '—', '—', f"{rest['count']}건", fmt(rest['amount']) if rest['count'] - rest['unknown'] > 0 else '—',
                      str(rest['unknown']), (rest['max_end'].isoformat() if rest['max_end'] else '—') + (f' · 종료일 없음 {rest["no_end"]}건' if rest['no_end'] else ''),
                      pct(s), '—', ', '.join(trunc(group_label(g), 20) for g in rest_list[:6]) + (' …' if len(rest_list) > 6 else '')])
        attrs.append(f'data-client="rest" data-count="{rest["count"]}"')
        bars.append((rest['label'], s, '#cbd5e1', 'rest'))
    rows_.append(['합계(활성 계약)', '—', '—', f'{total_count}건', fmt(total_amount) if total_count - unknown_count > 0 else '—', str(unknown_count),
                  '—', '100.0%' if total_amount > 0 else '—', '—', f'종료 {n_ended}건·해지 {n_canceled}행은 제외'])
    attrs.append(f'data-client="total" data-count="{total_count}"')
    top1 = share(top[0]) if top else None
    top3 = sum(share(g) or 0.0 for g in top[:3]) if top else None
    chunks = []
    if total_count == 0:
        chunks.append('<p data-clients-empty="1">활성(미종료·미취소) 계약이 없어 발주처 집계를 만들지 않았습니다.</p>')
    else:
        chunks.append(scroll_box(clients_svg(bars, uid)))
    chunks.append(table(['발주처(공시 표기)', '관계(원문)', '구분', '건수', '금액 합계(백만원)', '금액 미표시', '최장 종료일', '비중', '누적', '비고'],
                        rows_, f'발주처별 · 활성 계약(종료일 ≥ 오늘 또는 종료일 없음, 해지 제외) · 상위 {len(top)} + 익명 + 나머지 · 비중은 검증 금액 합계 대비',
                        attrs, 'data-clients="1"'))
    conc = []
    if top and number(top1):
        conc.append(f'최대 발주처 “{trunc(group_label(top[0]), 40)}” 비중 {pct(top1)}' + (' (관계회사 — 최종 수요처가 아님)' if top[0]['affiliate'] else ''))
    if top and number(top3):
        conc.append(f'상위 {min(3, len(top))}개 합계 {pct(top3)}')
    if anon_list:
        conc.append(f'익명 표기 {sum(g["count"] for g in anon_list)}건·{fmt(sum(g["amount"] for g in anon_list))} 백만원은 집중도 계산에서 제외')
    if unknown_count:
        conc.append(f'금액 미표시 {unknown_count}건은 건수에만 포함')
    chunks.append('<p data-concentration="1">' + esc(' · '.join(conc) if conc else '집중도: 계산할 활성 계약 금액 없음') +
                  '. 비중의 분모는 <strong>공시 계약금액 합계</strong>이며 정기보고서 수주잔고가 아닙니다(기납품·진행률을 알 수 없음).</p>')
    return {'html': ''.join(chunks), 'top': top, 'rest': rest, 'rest_list': rest_list, 'anon': anon_list,
            'total_count': total_count, 'total_amount': total_amount, 'unknown_count': unknown_count,
            'basis': basis, 'ended_count': n_ended, 'canceled_count': n_canceled, 'top1_share': top1, 'top3_share': top3,
            'recs': recs, 'today': today}


# ---------------------------------------------------------------- 회사 페이지 조각
def render_orders_section(panel_entry, contracts, forecast_entry=None, today=None):
    stock = panel_entry.get('stock')
    name = panel_entry.get('co') or panel_entry.get('name') or '회사'
    if not isinstance(stock, str) or not re.fullmatch(r'\d{6}', stock):
        raise ValueError('invalid stock identifier')
    today = as_date(today)
    if forecast_entry is not None:
        f = forecast_entry
        if f.get('stock') != stock or f.get('company_id') != stock or f.get('company_name') != name:
            raise ValueError('company_identity_conflict')
        if 'src' in panel_entry and panel_entry['src'] != f.get('source'):
            raise ValueError('company_source_conflict')
    uid = 'kgrid-orders-' + stock
    rows = select_rows(contracts, stock)
    if not rows:
        return (f'<p class="wrap" id="{uid}" data-orders-status="unavailable">{esc(name)} — 수주 상세 뷰 없음: '
                '이 종목의 단일판매·공급계약 공시 행이 원장에 없습니다(정기보고서 수주표만 있는 회사는 합계·목록 탭을 보십시오).</p>')
    g = build_gantt(rows, uid + '-gantt', today)
    s = build_schedule(rows, uid + '-sched', today, forecast_entry)
    c = build_clients(rows, uid + '-clients', today)
    recs = g['recs']
    n_cancel = sum(1 for r in recs if r['canceled'])
    n_matched = sum(1 for r in recs if r['canceled_by'] is not None)
    n_active = sum(1 for r in recs if r['status'] == 'active')
    n_ended = sum(1 for r in recs if r['status'] == 'ended')
    n_unamt = sum(1 for r in recs if r['status'] != 'canceled' and not number(r['amount']))
    n_corr = sum(1 for r in recs if r['raw'].get('corrected'))
    subs = sorted({r['sub_name'] for r in recs if r['subsidiary'] and r['sub_name']})
    n_sub = sum(1 for r in recs if r['subsidiary'])
    branch_counts = Counter(r['branch'] for r in recs if r['status'] != 'canceled')
    chunks = [f'<section class="wrap" id="{uid}" data-orders-status="ok" data-rows="{len(recs)}" aria-labelledby="{uid}-heading" '
              'style="color:var(--tx,#202936);background:var(--pn,#fff);border:1px solid var(--ln,#aaa);padding:1rem">',
              f'<h2 id="{uid}-heading">{esc(name)} · 수주 상세 — 간트 · 분기 전환 · 발주처</h2>',
              f'<p>원장: 단일판매·공급계약 공시 {len(recs)}행(정정은 최신본만 · 정정 {n_corr}건 · 해지 공시 {n_cancel}건, 그중 원 계약 행과 짝지은 {n_matched}건) · '
              f'활성 {n_active}건 · 종료 {n_ended}건 · 오늘 기준 {today.isoformat()}. '
              f'금액은 공시 원문 금액×공시 환율을 백만원으로 다시 계산해 환산값과 1% 안에서 맞는 것만 씁니다(미검증 {n_unamt}건은 비움). '
              '공시 계약금액은 정기보고서 수주잔고에 더하지 않으며, 기납품·진행률은 공시에 없어 잔여액을 만들지 않았습니다.</p>',
              '<p>장납기/회전(색): 계약명의 전압 계급(154kV 이상)·초고압·HVDC → 장납기; 품목 태그 ehv → 장납기, 수배전반·차단기·배전변압기·금구 → 회전; '
              f'전력선·변환은 계약기간 1.0년 문턱; 근거 없으면 미상. 이 회사: 장납기 {branch_counts.get("long_lead", 0)}건 · 회전 {branch_counts.get("turnover", 0)}건 · 미상 {branch_counts.get("unknown", 0)}건.</p>']
    if n_sub:
        chunks.append(f'<p><strong>지주 재공시 {n_sub}건</strong>(자회사 {esc(", ".join(subs) or "미상")}의 주요경영사항). '
                      '자회사 페이지의 같은 계약과 별개 행이며 자사 잔고 집계에 더하지 않습니다.</p>')
    if forecast_entry is not None:
        br = {'long_lead': '장납기', 'turnover': '회전'}.get(((forecast_entry.get('evidence') or {}).get('branch')), '미상')
        chunks.append(f'<p>Y+2 추정(페이지 값): 기준 {esc(forecast_entry.get("origin") or "미상")} · 회사 단위 장납기/회전 판정 <strong>{br}</strong> · '
                      f'상태 {esc(forecast_entry.get("status") or "미상")}. 계약 단위 색은 위 규칙으로 따로 정했습니다.</p>')
    else:
        chunks.append('<p data-forecast-note="none">Y+2 추정 항목이 전달되지 않아 분기 스케줄의 추정 칸을 비웠습니다.</p>')
    chunks.append(f'<h3 id="{uid}-gantt-h">1. 수주 간트 · 종료일순</h3>')
    chunks.append(g['html'])
    chunks.append(f'<h3 id="{uid}-sched-h">2. 분기 전환 스케줄 · {esc(q_label(s["quarters"][0]))}~{esc(q_label(s["quarters"][-1]))}</h3>')
    chunks.append(s['html'])
    chunks.append(f'<h3 id="{uid}-clients-h">3. 발주처별 · 활성 계약</h3>')
    chunks.append(c['html'])
    chunks.append('<details><summary>방법과 한계</summary>'
                  '<p>행 단위: 원장은 정정 공시를 최신본으로 접은 상태로 받습니다. 해지 공시는 별도 행이므로 같은 계약명(공백 무시)·같은 상대의 원 계약 행과 짝지어 둘 다 뺍니다. '
                  '후보가 여럿이면 금액이 같은 행을, 그래도 여럿이면 특정하지 않고 해지 행만 뺍니다(원 계약 행은 남고 그 사실을 표에 적습니다).</p>'
                  '<p>날짜: 시작일이 없고 종료일만 있으면 공시 계약일부터 점선으로 그립니다. 둘 다 없으면 종료일 표식만 둡니다. 종료일이 없으면 별도 묶음이며 주석의 예상 분기는 인용만 하고 스케줄에 넣지 않습니다.</p>'
                  '<p>상대: 법인 접미사·구두점·대소문자·공백 차이만 접어 같은 상대로 묶고 표기 변형을 함께 적습니다. 괄호 안 별칭이 다른 이름은 합치지 않습니다. '
                  '“-”·“개인” 같은 익명 표기는 익명 줄에 그대로 두고 실명과 섞지 않습니다. 관계회사(계열·자회사) 표시는 공시의 관계 열을 그대로 옮긴 것입니다.</p>'
                  '<p>금액: 통화가 다른 계약은 공시가 밝힌 환율로만 환산된 값을 쓰며, 환율이 없거나 원문 금액이 없으면 금액을 비웁니다. 비율·집중도의 분모는 활성 계약의 검증 금액 합계입니다.</p>'
                  '<p>못 싣는 것: 기납품·잔여액(공시에 없음), 정기보고서 수주잔고와의 대사(단위·범위가 다름), 5% 미만 매출처, 비밀유지로 가린 상대.</p>'
                  '</details></section>')
    return ''.join(chunks)


# ---------------------------------------------------------------- CLI
def load_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def main(argv):
    here = Path(__file__).resolve().parent
    cands = [here.parent / 'input' / 'kgrid_contracts.json', here / 'kgrid_contracts.json', here.parent / 'kgrid_contracts.json']
    src = next((p for p in cands if p.exists()), None)
    if src is None:
        raise SystemExit('kgrid_contracts.json not found next to input/ or output/')
    contracts = load_json(src)
    names = {}
    for p in (src.parent / 'kgrid_universe.json', here / 'kgrid_universe.json'):
        if p.exists():
            names = {r['stock']: r['name'] for r in load_json(p).get('rows', []) if isinstance(r, dict) and r.get('stock')}
            break
    out = here / 'orders_sections'
    out.mkdir(exist_ok=True)
    stocks = argv or sorted({str(r.get('stock')) for r in contracts.get('rows', []) if isinstance(r, dict) and r.get('stock')})
    for stock in stocks:
        name = names.get(stock, stock)
        fragment = render_orders_section({'stock': stock, 'name': name}, contracts, None)
        page = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>' + esc(name) + ' KGRID 수주 상세</title></head><body style="max-width:1160px;margin:2rem auto;font:15px/1.65 system-ui;padding:0 1rem">' +
                fragment + '</body></html>\n')
        (out / (stock + '.html')).write_text(page, encoding='utf-8')
        print(stock, name, 'ok')


if __name__ == '__main__':
    main(sys.argv[1:])
