# 주의: 탭 접두(kship_)를 유지한다. 접두 없는 이름은 sys.path 에 얹힌 다른 탭의 동명 모듈과 충돌한다.
#!/usr/bin/env python3
"""KSHIP order-detail views: Gantt · quarterly delivery schedule · client breakdown.

Inline SVG only. Standard library only. No network, packages, JavaScript or CDN.

Integration (same shape as kship_forecast_section.render_forecast_section):
    render_orders_section({'stock': code, 'co': name, 'src': 'kship_universe'},
                          contracts, forecast_entry=None, today=None) -> str

`contracts` is the kship_contracts.json payload ({'n': .., 'rows': [..]}) or its row list.
Rows are filtered to the panel stock inside this module — never pre-summed across companies.
`forecast_entry` is the per-company object render_forecast_section receives (or None).
`today` is an ISO date or datetime.date; None means datetime.date.today().

Each build_* returns {'html': fragment, ...computed data} so a checker can assert on the
numbers that produced the picture instead of re-parsing HTML.
"""
import argparse
import collections
import datetime
import html
import json
import math
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True

MONEY_UNIT = 'KRW_million'        # ledger field amt_krw_m — 공시 원화 금액, 백만원. 다른 단위는 그리지 않는다.
MONEY_LABEL = '백만원'
WINDOW = ('2026Q3', '2028Q4')
TOP_N = 10

# LOGIC §6: 슬롯→선종 고정 (CONT 1, LNGC 2, VLCC·PC 3, VLGC 4, OFFSH 5, NAVAL 6, BULK 7, PCTC 8).
# 여기 hex 값은 다크 표면용 대체값이다. 프로젝트의 검증된 8슬롯 팔레트가 따로 있으면 PALETTE 만 바꾼다.
SLOT = {'CONT': 1, 'LNGC': 2, 'VLCC': 3, 'PC': 3, 'VLGC': 4, 'OFFSH': 5, 'NAVAL': 6, 'BULK': 7, 'PCTC': 8}
PALETTE = {1: '#5b9cf5', 2: '#f2c14e', 3: '#62c48a', 4: '#e07b9a', 5: '#9b7bf0', 6: '#e8734a', 7: '#8fb8c9', 8: '#c9b458'}
OTHER_COLOR, NONE_COLOR = '#8a94a6', '#5c6470'
TYPE_ORDER = ['CONT', 'LNGC', 'VLCC', 'PC', 'VLGC', 'OFFSH', 'NAVAL', 'BULK', 'PCTC', 'OTHER', None]
TYPE_LABEL = {'CONT': '컨테이너선', 'LNGC': 'LNG선·FSRU', 'VLCC': '유조선·셔틀탱커', 'PC': 'P/C선',
              'VLGC': '가스선(LPG·암모니아·에탄)', 'OFFSH': '해양설비', 'NAVAL': '함정·특수선', 'BULK': '벌크선',
              'PCTC': '자동차운반선', 'OTHER': '선박 외(공사·설비·기자재)', None: '미분류(원문에서 못 정함)'}

_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
_Q_A = re.compile(r'(\d{4})\s*[-./]?\s*Q\s*([1-4])', re.I)
_Q_B = re.compile(r'Q\s*([1-4])\s*[-./]?\s*(\d{4})', re.I)


# ---------------------------------------------------------------- small helpers (same flavour as the forecast renderer)
def esc(value):
    return html.escape(str(value), quote=True)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fmt(value):
    return f"{value:,.3f}" if number(value) else "—"


def fmt0(value):
    return f"{value:,.0f}" if number(value) else "—"


def pct(value):
    return f"{value:.1f}%" if number(value) else "—"


def shorten(text, n):
    text = str(text)
    return text if len(text) <= n else text[:max(1, n - 1)] + '…'


def parse_date(value):
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str) and _DATE.fullmatch(value.strip()):
        try:
            return datetime.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def quarter_of(day):
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def norm_quarter(value):
    if not isinstance(value, str):
        return None
    m = _Q_A.search(value)
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    m = _Q_B.search(value)
    if m:
        return f"{m.group(2)}Q{m.group(1)}"
    return None


def quarter_range(first, last):
    ya, qa, yb, qb = int(first[:4]), int(first[5]), int(last[:4]), int(last[5])
    out = []
    while (ya, qa) <= (yb, qb):
        out.append(f"{ya}Q{qa}")
        qa += 1
        if qa == 5:
            ya, qa = ya + 1, 1
    return out


def type_label(t):
    return TYPE_LABEL[t] if t in TYPE_LABEL else str(t)


def color_of(t):
    if t in SLOT:
        return PALETTE[SLOT[t]]
    return OTHER_COLOR if t == 'OTHER' else NONE_COLOR


def type_sorted(types):
    known = {t: i for i, t in enumerate(TYPE_ORDER)}
    return sorted(set(types), key=lambda t: (known.get(t, len(known) - 2), str(t)))


def table(headers, rows, caption, row_attrs=None):
    """Same markup as the forecast renderer's table(); row_attrs adds data-* per row for checkers."""
    row_attrs = list(row_attrs or [])
    row_attrs += [''] * (len(rows) - len(row_attrs))   # never let zip() drop a data row
    return ('<div class="wrap" style="overflow-x:auto"><table style="border-collapse:collapse;width:100%">'
            '<caption style="text-align:left;padding:.6rem 0">' + esc(caption) + '</caption><thead><tr>'
            + ''.join('<th scope="col" style="text-align:left;padding:.35rem">' + esc(h) + '</th>' for h in headers)
            + '</tr></thead><tbody>'
            + ''.join('<tr' + (' ' + attrs if attrs else '') + '>'
                      + ''.join(('<th scope="row"' if i == 0 else '<td')
                                + ' style="text-align:left;padding:.35rem;border-top:1px solid var(--ln,#667085)">'
                                + esc(v) + ('</th>' if i == 0 else '</td>')
                                for i, v in enumerate(row)) + '</tr>' for row, attrs in zip(rows, row_attrs))
            + '</tbody></table></div>')


def swatch(color, dashed=False):
    border = 'border:1px dashed currentColor;' if dashed else 'border:1px solid var(--ln,#667085);'
    return (f'<span style="display:inline-block;width:.9em;height:.9em;vertical-align:-.1em;'
            f'background:{color};{border}"></span>')


# ---------------------------------------------------------------- ledger access and normalisation
def ledger_rows(contracts):
    rows = contracts.get('rows') if isinstance(contracts, dict) else contracts
    if not isinstance(rows, list):
        raise ValueError('contracts must be the ledger dict with rows or a list of rows')
    return rows


def select_company(contracts, stock):
    return [r for r in ledger_rows(contracts) if isinstance(r, dict) and r.get('stock') == stock]


def normalize(row):
    """One ledger row -> plain dict with parsed dates and typed numbers. Nothing is estimated."""
    title = str(row.get('title') or '')
    start, signed, end = parse_date(row.get('start')), parse_date(row.get('signed')), parse_date(row.get('end'))
    amt = float(row['amt_krw_m']) if number(row.get('amt_krw_m')) else None
    ships = int(row['ships']) if number(row.get('ships')) else None
    t = row.get('type')
    t = t if isinstance(t, str) and t else None
    return {'rcp': str(row.get('rcp') or ''), 'stock': str(row.get('stock') or ''), 'title': title,
            'name': str(row.get('name') or ''), 'type': t, 'ships': ships, 'amt': amt,
            'rev_ratio': row['rev_ratio'] if number(row.get('rev_ratio')) else None,
            'party': str(row.get('party') or '').strip(), 'party_anon': bool(row.get('party_anon')),
            'region': str(row.get('region') or ''),
            'start': start or signed, 'start_src': 'start' if start else ('signed' if signed else None),
            'end': end, 'signed': signed, 'end_raw': row.get('end'), 'start_raw': row.get('start'),
            'terminated': '해지' in title, 'subsidiary': '자회사' in title,
            'corrected': bool(row.get('corrected')), 'note': str(row.get('note') or ''),
            'supersedes': row.get('supersedes')}


def party_key(c):
    return c['party'] or '(상대 미기재)'


def missing_end_reason(c):
    if c['terminated']:
        return '계약해지 공시 — 원문에 금액·종료일 없음(잔고 아님)'
    raw = c['end_raw']
    reason = "원문 종료일 '-'(미정)" if raw in (None, '', '-') else f"종료일 형식 인식 불가({raw})"
    hints = []
    if '미정' in c['note']:
        hints.append('비고: 종료일 미정')
    if '착공' in c['note']:
        hints.append('비고: 기간이 착공일 기준')
    if '미발효' in c['note']:
        hints.append('비고: 계약 미발효')
    if c['start'] is None:
        hints.append('시작일도 미상')
    elif c['start_src'] == 'signed':
        hints.append('시작일은 수주일로 대신 표기')
    return reason + ('; ' + '; '.join(hints) if hints else '')


def _today(today):
    if today is None:
        return datetime.date.today()
    day = parse_date(today)
    if day is None:
        raise ValueError('invalid today')
    return day


# ---------------------------------------------------------------- view 1: Gantt
GW, NAME_X, PARTY_X, CX0, CX1, TOP, RH, BOT = 1100, 4, 262, 404, 1086, 40, 18, 14


def build_gantt(rows, uid, today=None):
    """Bars = non-terminated contracts with a parsable end date, sorted by end. Others go to `separate`."""
    today = _today(today)
    bars = sorted((c for c in rows if not c['terminated'] and c['end']),
                  key=lambda c: (c['end'], c['start'] or c['end'], c['rcp']))
    separate = [c for c in rows if c['terminated'] or not c['end']]
    max_amt = max([c['amt'] for c in bars if c['amt']] + [0.0])
    past_due = [c for c in bars if c['end'] < today]
    chunks = ['<div data-view="gantt">']
    axis = None
    if not bars:
        chunks.append('<p data-gantt-status="empty">간트 막대 없음: 종료일이 있는 유효 계약이 없습니다.</p>')
    else:
        first = min(min(c['start'] or c['end'] for c in bars), today)
        last = max(max(c['end'] for c in bars), today)
        lo, hi = datetime.date(today.year - 10, 1, 1), datetime.date(today.year + 10, 12, 31)
        a0 = datetime.date(max(first, lo).year, 1, 1)
        a1 = datetime.date(min(last, hi).year + 1, 1, 1)
        axis = (a0, a1)
        span = max(1, (a1 - a0).days)

        def x(day):
            day = min(max(day, a0), a1)
            return CX0 + (day - a0).days / span * (CX1 - CX0)

        height = TOP + len(bars) * RH + BOT
        desc = (f"계약 {len(bars)}건, 종료일 오름차순. 축 {a0}~{a1}. 오늘 {today}. "
                f"막대 굵기 = 금액(최대 대비 제곱근), 라벨 = 금액 {MONEY_LABEL}.")
        chunks.append(f'<div class="wrap" style="overflow-x:auto">'
                      f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GW} {height}" role="img" '
                      f'aria-labelledby="{uid}-title {uid}-desc" style="min-width:900px;width:100%;height:auto;display:block">'
                      f'<title id="{uid}-title">수주 간트 · 종료일 순 · 금액 {MONEY_LABEL}</title>'
                      f'<desc id="{uid}-desc">{esc(desc)}</desc>'
                      f'<text x="{NAME_X}" y="14" font-size="10" fill="currentColor">계약명</text>'
                      f'<text x="{PARTY_X}" y="14" font-size="10" fill="currentColor">상대(익명은 기울임)</text>')
        step = 1 if a1.year - a0.year <= 14 else 2
        for yr in range(a0.year, a1.year + 1, step):
            xx = x(datetime.date(yr, 1, 1))
            chunks.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{TOP - 8}" y2="{height - BOT}" '
                          f'stroke="var(--ln,#667085)" stroke-width=".6"/>'
                          f'<text x="{xx + 2:.1f}" y="14" font-size="10" fill="currentColor">{yr}</text>')
        xt = x(today)
        chunks.append(f'<line data-today="{today}" x1="{xt:.1f}" x2="{xt:.1f}" y1="{TOP - 8}" y2="{height - BOT}" '
                      f'stroke="var(--a,#4b96ed)" stroke-width="1.5" stroke-dasharray="4 3"/>'
                      f'<text x="{xt + 3:.1f}" y="{TOP - 12}" font-size="10" fill="var(--a,#4b96ed)">오늘 {today}</text>')
        for i, c in enumerate(bars):
            y0 = TOP + i * RH
            cy = y0 + RH / 2
            start = c['start'] or c['end']
            xs, xe = x(start), x(c['end'])
            if xe - xs < 2:                      # zero-length or sub-pixel bar: keep a 2px sliver inside the axis
                xs = xe - 2
                if xs < CX0:
                    xs, xe = CX0, CX0 + 2
            h = 6 + 8 * math.sqrt(c['amt'] / max_amt) if (c['amt'] and max_amt) else 6
            color = color_of(c['type'])
            ships = c['ships'] if c['ships'] is not None else '—'
            period = (f"{start}" if c['start'] else '시작일 미상') + (' (수주일 기준)' if c['start_src'] == 'signed' else '')
            parts = [c['name'], '선종 ' + type_label(c['type']), f"척/기 {ships}",
                     '상대 ' + party_key(c) + (' [익명 표기]' if c['party_anon'] else ''),
                     f"기간 {period} ~ {c['end']}", f"금액 {fmt(c['amt'])} {MONEY_LABEL}",
                     '매출 대비 ' + pct(c['rev_ratio'])]
            if c['end'] < today:
                parts.append('종료일 경과(인도·완료 여부 원문 미확인)')
            if c['corrected']:
                parts.append('정정공시 반영')
            if c['subsidiary']:
                parts.append('자회사 주요경영사항 공시')
            title = ' · '.join(parts)
            rect = (f'<rect x="{xs:.1f}" y="{cy - h / 2:.1f}" width="{xe - xs:.1f}" height="{h:.1f}" fill="{color}"/>'
                    if c['amt'] is not None else
                    f'<rect x="{xs:.1f}" y="{cy - 3:.1f}" width="{xe - xs:.1f}" height="6" fill="none" '
                    f'stroke="{color}" stroke-dasharray="3 2"/>')
            label = fmt0(c['amt']) if c['amt'] is not None else '금액 미상'
            if xe + 64 <= CX1:
                lx, anchor = xe + 4, 'start'
            elif xs - 68 >= CX0:
                lx, anchor = xs - 4, 'end'
            else:
                lx, anchor = xe - 4, 'end'
            italic = ' font-style="italic"' if c['party_anon'] else ''
            chunks.append(f'<g data-bar="1" data-rcp="{esc(c["rcp"])}" data-type="{esc(c["type"] or "")}" '
                          f'data-end="{c["end"]}"><title>{esc(title)}</title>'
                          f'<text x="{NAME_X}" y="{cy + 3.5:.1f}" font-size="10" fill="currentColor">{esc(shorten(c["name"], 24))}</text>'
                          f'<text x="{PARTY_X}" y="{cy + 3.5:.1f}" font-size="10" fill="currentColor"{italic}>'
                          f'{esc(shorten(party_key(c), 13))}</text>{rect}'
                          f'<text x="{lx:.1f}" y="{cy + 3.2:.1f}" font-size="9.5" text-anchor="{anchor}" fill="currentColor">{esc(label)}</text>')
            if start < a0:
                chunks.append(f'<text x="{CX0 + 1}" y="{cy + 3.5:.1f}" font-size="9" fill="currentColor">◀</text>')
            if c['end'] > a1:
                chunks.append(f'<text x="{CX1 - 9}" y="{cy + 3.5:.1f}" font-size="9" fill="currentColor">▶</text>')
            chunks.append('</g>')
        chunks.append('</svg></div>')
        counts = collections.Counter(c['type'] for c in bars)
        chunks.append('<p>' + ' '.join(
            f'<span style="display:inline-block;margin:0 .8rem .3rem 0">{swatch(color_of(t), t not in SLOT and t != "OTHER")} '
            f'{esc(type_label(t))} {counts[t]}건</span>' for t in type_sorted(counts)) + '</p>')
        chunks.append(f'<p>축 {a0} ~ {a1}(오늘 ±10년으로 자름; 잘린 구간은 ◀▶). 막대 굵기는 금액의 제곱근 비례, 라벨은 금액({MONEY_LABEL}, 정수 반올림). '
                      f'시작일이 없으면 수주일을 대신 쓰고 제목에 표시합니다. 종료일이 오늘 이전인 계약 {len(past_due)}건 — '
                      f'인도·완료 여부는 원문(수시공시)에 없어 확인하지 못했습니다.</p>')
    if separate:
        chunks.append(table(['계약명', '상대', '선종', '시작일', f'금액({MONEY_LABEL})', '간트 제외 사유'],
                            [[c['name'], party_key(c) + (' [익명]' if c['party_anon'] else ''), type_label(c['type']),
                              str(c['start']) if c['start'] else '—', fmt(c['amt']), missing_end_reason(c)] for c in separate],
                            f'종료일 없는 건 · 간트·분기 스케줄에서 제외 · {len(separate)}건(해지 공시 {sum(1 for c in separate if c["terminated"])}건 포함)',
                            ['data-sep="1" data-rcp="' + esc(c['rcp']) + '"' for c in separate]))
    else:
        chunks.append('<p>종료일 없는 건: 없음.</p>')
    chunks.append('</div>')
    return {'html': ''.join(chunks), 'bars': bars, 'separate': separate, 'axis': axis, 'today': today,
            'past_due': past_due, 'max_amt': max_amt}


# ---------------------------------------------------------------- view 2: quarterly delivery schedule
def forecast_join(forecast_entry, scenario='base'):
    """Read the page's Y+2 estimate (per quarter) and its 선표 rows. Never modifies either side."""
    if not isinstance(forecast_entry, dict):
        return {}, {}, None
    fq = {}
    for r in ((forecast_entry.get('scenarios') or {}).get(scenario) or {}).get('quarterly') or []:
        q = norm_quarter(r.get('quarter'))
        if not q:
            continue
        iv = r.get('covered_scope_interval') or {}
        fq[q] = {'value': r['value'] if number(r.get('value')) else None,
                 'covered': r['covered_scope_value'] if number(r.get('covered_scope_value')) else None,
                 'lower': iv['lower'] if number(iv.get('lower')) else None,
                 'upper': iv['upper'] if number(iv.get('upper')) else None}
    fs = {}
    for r in (forecast_entry.get('industry_axes') or {}).get('schedule') or []:
        q = norm_quarter(r.get('quarter'))
        if not q:
            continue
        d = fs.setdefault(q, {'n': 0, 'units': 0})
        d['n'] += 1
        if number(r.get('units')):
            d['units'] += r['units']
    meta = {'scenario': scenario, 'origin': forecast_entry.get('origin'), 'status': forecast_entry.get('status'),
            'has_quarterly': bool(fq), 'has_schedule': bool(fs)}
    return fq, fs, meta


def _bucket():
    return {'n': 0, 'amt': 0.0, 'amt_n': 0, 'amt_missing': 0, 'ships': 0, 'by_type': collections.Counter(), 'rows': []}


def build_schedule(rows, uid, forecast_entry=None, window=WINDOW):
    """Contract end dates bucketed by quarter; window quarters plus 'before'/'after' so totals reconcile."""
    quarters = quarter_range(window[0], window[1])
    keys = ['before'] + quarters + ['after']
    pop = [c for c in rows if not c['terminated'] and c['end']]
    no_end = [c for c in rows if not c['terminated'] and not c['end']]
    b = collections.OrderedDict((k, _bucket()) for k in keys)
    for c in pop:
        q = quarter_of(c['end'])
        k = q if q in b else ('before' if q < quarters[0] else 'after')
        d = b[k]
        d['n'] += 1
        d['rows'].append(c)
        if c['amt'] is not None:
            d['amt'] += c['amt']
            d['amt_n'] += 1
            d['by_type'][c['type']] += c['amt']
        else:
            d['amt_missing'] += 1
        if c['ships']:
            d['ships'] += c['ships']
    fq, fs, meta = forecast_join(forecast_entry)
    scen_label = {'conservative': '보수', 'base': '기준', 'optimistic': '낙관'}.get(meta['scenario'], meta['scenario']) if meta else '기준'

    # ---- chart
    upper = max([1.0] + [d['amt'] for d in b.values()]
                + [v for q in quarters for v in ((fq.get(q) or {}).get('value'), (fq.get(q) or {}).get('covered')) if number(v)])

    def y(v):
        return 200 - v / upper * 160

    step = 750 / len(keys)
    label_of = {'before': quarters[0] + ' 이전', 'after': quarters[-1] + ' 이후'}
    desc = ' / '.join(f"{label_of.get(k, k)}: {d['n']}건 {fmt(d['amt'])}" for k, d in b.items())
    chunks = ['<div data-view="schedule">',
              f'<div class="wrap" style="overflow-x:auto"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 250" role="img" '
              f'aria-labelledby="{uid}-title {uid}-desc" style="min-width:640px;width:100%;height:auto;display:block">',
              f'<title id="{uid}-title">분기별 계약 종료(마지막 호선 인도 예정) 합계 · {MONEY_LABEL}</title>',
              f'<desc id="{uid}-desc">{esc(desc)}</desc>',
              f'<line x1="65" x2="820" y1="{y(0):.2f}" y2="{y(0):.2f}" stroke="currentColor"/>']
    for i, k in enumerate(keys):
        d = b[k]
        xc = 65 + (i + .5) * step
        edge = k in ('before', 'after')
        opacity = ' opacity=".55"' if edge else ''
        chunks.append(f'<g data-q="{k}" data-n="{d["n"]}"{opacity}>'
                      f'<title>{esc(label_of.get(k, k))}: {d["n"]}건 · {fmt(d["amt"])} {MONEY_LABEL}</title>')
        offset = 0.0
        for t in type_sorted(d['by_type']):
            v = d['by_type'][t]
            if v <= 0:
                continue
            a, bb = y(offset), y(offset + v)
            chunks.append(f'<rect data-type="{esc(t or "")}" x="{xc - 17:.2f}" y="{bb:.2f}" width="34" '
                          f'height="{a - bb:.2f}" fill="{color_of(t)}"/>')
            offset += v
        if d['n']:
            chunks.append(f'<text x="{xc:.2f}" y="{y(offset) - 4:.2f}" text-anchor="middle" font-size="9" fill="currentColor">{d["n"]}건</text>')
        f = fq.get(k) if not edge else None
        if f:
            if number(f['value']):
                yy = y(f['value'])
                chunks.append(f'<path data-forecast="value" d="M{xc:.2f},{yy - 5:.2f}l5,5l-5,5l-5,-5z M{xc - 14:.2f},{yy:.2f}H{xc + 14:.2f}" '
                              f'stroke="currentColor" fill="var(--pn,#f7fafc)" stroke-width="1.2"/>')
            if number(f['covered']):
                yy = y(f['covered'])
                chunks.append(f'<circle data-forecast="covered" cx="{xc:.2f}" cy="{yy:.2f}" r="4" stroke="currentColor" fill="none"/>')
            if not number(f['value']) and not number(f['covered']):
                chunks.append(f'<text x="{xc:.2f}" y="60" text-anchor="middle" font-size="9" fill="currentColor">추정 —</text>')
        chunks.append(f'<text x="{xc:.2f}" y="216" text-anchor="middle" font-size="9" fill="currentColor">'
                      f'{esc("이전" if k == "before" else "이후" if k == "after" else k)}</text></g>')
    chunks.append(f'<text x="65" y="240" font-size="9" fill="currentColor">막대 = 이 분기에 종료(인도 예정)되는 계약의 공시 금액 합, 선종별 누적. '
                  f'◇ = 페이지 추정({scen_label}) 원장 전범위 합, ○ = 계산 범위 합. 양끝 흐린 막대 = 창 밖.</text></svg></div>')

    # ---- side-by-side table
    if meta is None:
        chunks.append('<p data-forecast-join="none">페이지 추정 미제공: 이 렌더에는 forecast_entry 가 전달되지 않아 추정 열을 비웠습니다(—). '
                      '분기 계약 합계는 그 자체로 유효합니다.</p>')
    else:
        chunks.append(f'<p data-forecast-join="{esc(meta["status"] or "")}">페이지 추정: 기준 {esc(meta["origin"] or "—")} · 상태 {esc(meta["status"] or "—")} · '
                      f'{scen_label} 시나리오 분기값을 그대로 옮겼습니다. 추정은 진행기준 매출 대용치이고 계약 합계는 인도 시점의 계약 총액이라 '
                      '<strong>같은 분기라도 같을 이유가 없습니다</strong>. 차이는 기록만 하고 조정하지 않았습니다.</p>')
    mismatches = []
    trows, attrs = [], []
    for k in keys:
        d = b[k]
        f = fq.get(k)
        s = fs.get(k)
        memo = []
        amt_txt = fmt(d['amt']) if d['amt_n'] else '—'
        if k in ('before', 'after'):
            memo.append('창 밖 — 합계 대조용')
            if k == 'before' and d['n']:
                memo.append('종료일 경과분 포함(인도 여부 원문 미확인)')
        elif meta is None:
            memo.append('추정 미제공')
        else:
            if f is None:
                memo.append('추정 원장에 이 분기 없음')
            else:
                v, tag = (f['value'], '전범위') if f['value'] is not None else (f['covered'], '계산범위')
                if v is None:
                    memo.append(f'이 분기에 끝나는 계약 {d["n"]}건·합계 {amt_txt} vs 추정 미추정(—)')
                else:
                    diff = fmt(d['amt'] - v) if d['amt_n'] else '—(계약 합계 없음)'
                    memo.append(f'이 분기에 끝나는 계약 {d["n"]}건·합계 {amt_txt} vs 추정({tag}) {fmt(v)} — 차이 {diff}, 조정 안 함')
            if meta['has_schedule']:
                sn = s['n'] if s else 0
                if sn != d['n']:
                    memo.append(f'페이지 선표 {sn}건 ≠ 계약 {d["n"]}건 — 불일치 기록(조정 안 함)')
                    mismatches.append({'quarter': k, 'page_schedule_n': sn, 'contracts_n': d['n']})
                else:
                    memo.append(f'페이지 선표 {sn}건 일치')
        if d['amt_missing']:
            memo.append(f'금액 미상 {d["amt_missing"]}건은 합계에서 빠짐')
        trows.append([label_of.get(k, k), d['n'], d['ships'] if d['ships'] else '—', amt_txt,
                      fmt(f['value']) if f else '—', fmt(f['covered']) if f else '—',
                      (f"{fmt(f['lower'])} ~ {fmt(f['upper'])}" if f and f['lower'] is not None and f['upper'] is not None else '—'),
                      (s['n'] if s else (0 if (meta and meta['has_schedule'] and k in quarters) else '—')),
                      '; '.join(memo)])
        attrs.append(f'data-q="{k}"')
    tot_n = sum(d['n'] for d in b.values())
    tot_amt = sum(d['amt'] for d in b.values())
    tot_ships = sum(d['ships'] for d in b.values())
    trows.append(['합계(창 안+밖)', tot_n, tot_ships if tot_ships else '—', fmt(tot_amt), '—', '—', '—', '—',
                  f'종료일 없는 유효 계약 {len(no_end)}건은 별도(간트 아래 표) · 해지 공시 제외'])
    attrs.append('data-q="total"')
    chunks.append(table(['분기(종료일 기준)', '종료 계약 건수', '척/기', f'종료 계약 합계({MONEY_LABEL})',
                         f'페이지 추정({scen_label}) 전범위 합', f'페이지 추정({scen_label}) 계산범위 합', '페이지 추정 민감도',
                         '페이지 선표 건수', '메모'], trows,
                        f'{window[0]}~{window[1]} 분기 전환 스케줄 · 계약 종료일 = 마지막 호선 인도 예정 · 추정과 나란히(조정 없음)', attrs))
    if mismatches:
        chunks.append('<p data-schedule-mismatch="' + str(len(mismatches)) + '">페이지 선표 건수와 원장 계약 건수가 어긋난 분기: '
                      + esc(', '.join(f"{m['quarter']}(선표 {m['page_schedule_n']} vs 계약 {m['contracts_n']})" for m in mismatches))
                      + '. 원장 스냅샷·정정 반영 시점 차이일 수 있으며 여기서는 맞추지 않았습니다.</p>')
    chunks.append('</div>')
    return {'html': ''.join(chunks), 'buckets': b, 'keys': keys, 'quarters': quarters, 'pop': pop, 'no_end': no_end,
            'forecast': fq, 'page_schedule': fs, 'meta': meta, 'mismatches': mismatches,
            'total_n': tot_n, 'total_amt': tot_amt}


# ---------------------------------------------------------------- view 3: clients
def _agg_new():
    return {'n': 0, 'amt': 0.0, 'amt_n': 0, 'amt_missing': 0, 'ships': 0, 'max_end': None, 'no_end': 0,
            'types': collections.Counter(), 'labels': collections.Counter()}


def _agg_add(d, c):
    d['n'] += 1
    if c['amt'] is not None:
        d['amt'] += c['amt']
        d['amt_n'] += 1
    else:
        d['amt_missing'] += 1
    if c['ships']:
        d['ships'] += c['ships']
    if c['end']:
        d['max_end'] = c['end'] if d['max_end'] is None or c['end'] > d['max_end'] else d['max_end']
    else:
        d['no_end'] += 1
    d['types'][c['type']] += 1
    d['labels'][party_key(c)] += 1


def _types_text(counter):
    return ' · '.join(f"{t or '미분류'} {n}" for t, n in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0]))))


def build_clients(rows, uid, top_n=TOP_N):
    """Named parties ranked by amount; anonymous rows kept as one separate line; remainder pooled."""
    pop = [c for c in rows if not c['terminated']]
    named = collections.OrderedDict()
    anon = _agg_new()
    for c in pop:
        if c['party_anon']:
            _agg_add(anon, c)
        else:
            _agg_add(named.setdefault(party_key(c), _agg_new()), c)
    total_n = len(pop)
    total_amt = sum(c['amt'] for c in pop if c['amt'] is not None)
    amt_missing = sum(1 for c in pop if c['amt'] is None)
    ranking = sorted(named.items(), key=lambda kv: (-kv[1]['amt'], -kv[1]['n'], kv[0]))
    top, rest = ranking[:top_n], ranking[top_n:]
    others = _agg_new()
    for _, d in rest:
        for key in ('n', 'amt', 'amt_n', 'amt_missing', 'ships', 'no_end'):
            others[key] += d[key]
        others['types'].update(d['types'])
        others['labels'].update(d['labels'])
        if d['max_end'] and (others['max_end'] is None or d['max_end'] > others['max_end']):
            others['max_end'] = d['max_end']

    def share(d):
        return d['amt'] / total_amt * 100 if total_amt > 0 and d['amt_n'] else None

    cr1 = share(top[0][1]) if top else None
    cr3 = sum(share(d) or 0 for _, d in top[:3]) if top else None
    anon_share = share(anon) if anon['n'] else None

    def row(label, d, extra=''):
        return [label, d['n'], d['ships'] if d['ships'] else '—', fmt(d['amt']) if d['amt_n'] else '—', pct(share(d)),
                str(d['max_end']) if d['max_end'] else '—',
                ('종료일 미정 ' + str(d['no_end']) + '건' if d['no_end'] else '') + (' · ' if d['no_end'] and d['amt_missing'] else '')
                + ('금액 미상 ' + str(d['amt_missing']) + '건' if d['amt_missing'] else '') or '—',
                _types_text(d['types']) + (' · ' + extra if extra else '')]

    trows, attrs = [], []
    for i, (name, d) in enumerate(top, 1):
        trows.append(row(f'{i}. {name}', d))
        attrs.append('data-client="named" data-party="' + esc(name) + '"')
    if rest:
        trows.append(row(f'그 외 실명 발주처 {len(rest)}곳', others, '상위 ' + str(top_n) + ' 밖'))
        attrs.append(f'data-client="other" data-members="{len(rest)}"')
    if anon['n']:
        trows.append(row('익명 표기(○○ 소재/지역 선주·선사 등) — 실명과 섞지 않음', anon,
                         '표기 종류 ' + str(len(anon['labels'])) + '개'))
        attrs.append(f'data-client="anon" data-members="{len(anon["labels"])}"')
    total = _agg_new()
    for c in pop:
        _agg_add(total, c)
    trows.append(row('합계(유효 계약 전체)', total))
    attrs.append('data-client="total"')
    chunks = ['<div data-view="clients">']

    # ---- share bars (SVG)
    bars = [(shorten(n, 18), share(d), d['n']) for n, d in top]
    if rest:
        bars.append((f'그 외 실명 {len(rest)}곳', share(others), others['n']))
    if anon['n']:
        bars.append(('익명 표기(합)', anon_share, anon['n']))
    if bars:
        hgt = 24 + 22 * len(bars)
        desc = ' / '.join(f"{n}: {pct(s)} {k}건" for n, s, k in bars)
        chunks.append(f'<div class="wrap" style="overflow-x:auto"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 {hgt}" role="img" '
                      f'aria-labelledby="{uid}-title {uid}-desc" style="min-width:560px;width:100%;height:auto;display:block">'
                      f'<title id="{uid}-title">발주처별 공시 계약 금액 비중</title><desc id="{uid}-desc">{esc(desc)}</desc>')
        for i, (n, s, k) in enumerate(bars):
            yy = 16 + 22 * i
            w = (s or 0) / 100 * 480
            fill = 'var(--a,#4b96ed)' if i < len(top) else ('var(--ln,#667085)' if n.startswith('그 외') else 'var(--tx,#84adad)')
            chunks.append(f'<g data-share-row="{i}"><title>{esc(n)}: {pct(s)} · {k}건</title>'
                          f'<text x="4" y="{yy + 4}" font-size="10" fill="currentColor">{esc(n)}</text>'
                          f'<rect x="250" y="{yy - 6}" width="{w:.1f}" height="12" fill="{fill}"/>'
                          f'<text x="{254 + w:.1f}" y="{yy + 4}" font-size="10" fill="currentColor">{pct(s)} · {k}건</text></g>')
        chunks.append('</svg></div>')
    chunks.append(table(['발주처', '건수', '척/기', f'금액 합계({MONEY_LABEL})', '비중(공시 계약 합 대비)', '최장 종료일', '빈 값 사유', '선종 구성'],
                        trows, f'발주처별 · 상위 {top_n} 실명 + 나머지 묶음 + 익명 한 줄 · 비중 분모 = 금액이 있는 유효 계약 합 {fmt(total_amt)} {MONEY_LABEL}', attrs))
    conc = []
    if top:
        conc.append(f'최대 실명 발주처 {esc(top[0][0])} {pct(cr1)}(CR1)')
        conc.append(f'상위 {min(3, len(top))} 실명 합 {pct(cr3)}(CR3)')
    if anon['n']:
        conc.append(f'익명 표기 합계 {pct(anon_share)} — 익명 안에 특정 선주가 몰려 있어도 원문이 밝히지 않아 알 수 없습니다')
    if amt_missing:
        conc.append(f'금액 미상 {amt_missing}건은 분모·비중에서 빠졌습니다')
    chunks.append('<p data-concentration="1">집중도: ' + ' · '.join(conc) + '. 비중은 <strong>공시 계약 단순 합</strong> 대비이며 '
                  '회사 보고 수주잔고(기납품 차감·미공시 계약 포함) 대비가 아닙니다. 발주처 이름은 원문 표기 그대로이며 '
                  '표기가 다른 같은 기관(예: 괄호 표기 차이)은 합치지 않았습니다.</p>')
    if anon['labels']:
        chunks.append('<details><summary>익명 표기 내역(원문 표기 그대로, 실명과 별도)</summary>'
                      + table(['표기', '건수'], [[k, v] for k, v in anon['labels'].most_common()], '익명 표기별 건수 · 금액은 한 줄 합계만')
                      + '</details>')
    chunks.append('</div>')
    return {'html': ''.join(chunks), 'pop': pop, 'ranking': ranking, 'top': top, 'rest': rest, 'others': others,
            'anon': anon, 'total': total, 'total_n': total_n, 'total_amt': total_amt, 'amt_missing': amt_missing,
            'cr1': cr1, 'cr3': cr3, 'anon_share': anon_share}


# ---------------------------------------------------------------- section
def prepare_company(panel_entry, contracts, forecast_entry=None):
    stock = panel_entry.get('stock')
    name = panel_entry.get('co', panel_entry.get('name'))
    if not isinstance(stock, str) or not re.fullmatch(r'\d{6}', stock):
        raise ValueError('invalid stock identifier')
    if forecast_entry is not None:
        c = forecast_entry
        if c.get('stock') != stock or c.get('company_id') != stock or c.get('company_name') != name:
            raise ValueError('company_identity_conflict')
        if 'src' in panel_entry and panel_entry['src'] != c.get('source'):
            raise ValueError('company_identity_conflict')
        if c.get('money_unit') != MONEY_UNIT:
            raise ValueError('unexpected output unit')
    return stock, (name if isinstance(name, str) and name else stock), [normalize(r) for r in select_company(contracts, stock)]


def render_orders_section(panel_entry, contracts, forecast_entry=None, today=None):
    stock, name, rows = prepare_company(panel_entry, contracts, forecast_entry)
    if not rows:
        return f'<p data-orders-status="unavailable">수주 상세 미제공: 원장에 {esc(stock)} 계약 공시가 없습니다.</p>'
    uid = 'kship-orders-' + stock
    g = build_gantt(rows, uid + '-gantt', today=today)
    s = build_schedule(rows, uid + '-schedule', forecast_entry)
    k = build_clients(rows, uid + '-clients')
    live = [c for c in rows if not c['terminated']]
    terminated = [c for c in rows if c['terminated']]
    status = 'full' if all(c['end'] and c['amt'] is not None for c in live) else 'partial'
    subs = sum(1 for c in rows if c['subsidiary'])
    corrected = sum(1 for c in rows if c['corrected'])
    chunks = [f'<section id="{uid}" data-orders-status="{status}" data-orders-n="{len(rows)}" lang="ko" '
              'style="font:15px/1.65 system-ui,sans-serif;color:var(--tx,#17212b);background:var(--pn,#f7fafc);padding:1rem;max-width:1280px;margin:auto">',
              f'<h2>{esc(name)} · 수주 상세 — 간트 · 분기 전환 · 발주처</h2>',
              f'<p>원장: 거래소 「단일판매ㆍ공급계약체결」 공시 {len(rows)}건(정정은 최신 접수분만, 정정 반영 {corrected}건, 해지 공시 {len(terminated)}건 포함). '
              f'금액은 공시 원화 금액 {MONEY_LABEL} — 지분·부가세·환산 조건은 각 공시 비고 그대로이며 재환산하지 않았습니다. —는 미상이며 0이 아닙니다.</p>',
              '<p><strong>종료일 = 계약기간 종료일(마지막 호선 인도 예정). 진행기준 인식이므로 인도 분기 ≠ 매출 분기.</strong> '
              '아래 합계는 공시 계약의 단순 합이며 회사 보고 수주잔고(기납품 차감·공시 기준 미달 계약 포함)가 아닙니다. 지주·자회사, 회사 간 합산은 금지합니다.</p>']
    if subs:
        chunks.append(f'<p>자회사 주요경영사항 공시 {subs}건 포함 — 지주 자체 계약이 아니며 해당 자회사 페이지의 같은 계약과 중복될 수 있습니다.</p>')
    chunks.append(f'<p>기준일(오늘 선) {g["today"]} · 유효 계약 {len(live)}건 중 종료일 있음 {len(g["bars"])}건, 없음 {len(live) - len(g["bars"])}건.</p>')
    chunks.append('<h3>1. 수주 간트 — 종료일 순, 색 = 선종</h3>' + g['html'])
    chunks.append(f'<h3>2. 분기 전환 스케줄 {WINDOW[0]}–{WINDOW[1]} — 페이지 추정과 나란히</h3>' + s['html'])
    chunks.append('<h3>3. 발주처별 — 실명 상위 · 나머지 · 익명 한 줄 · 집중도</h3>' + k['html'])
    chunks.append('<p><small>선종·척수는 계약명에서 파이프라인이 다시 뽑은 값이고 못 정한 건은 미분류입니다. 발주처 익명 표기(소재·지역·선주·선사)는 원문이 실명을 밝히지 않은 것이라 '
                  '실명 표와 섞지 않았습니다. 이 화면은 추정·보간을 하지 않으며 빈 칸의 사유를 각 표에 적었습니다.</small></p></section>')
    return ''.join(chunks)


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contracts', type=Path, default=root.parent / 'input' / 'kship_contracts.json')
    parser.add_argument('--universe', type=Path, default=root.parent / 'input' / 'kship_universe.json')
    parser.add_argument('--forecast-panel', type=Path, default=None, help='forecast_panel.json (optional)')
    parser.add_argument('--today', default=None, help='ISO date for the today line (default: system date)')
    parser.add_argument('--output', type=Path, default=root / 'sections_orders')
    args = parser.parse_args()
    ledger = json.loads(args.contracts.read_text(encoding='utf-8'))
    names = {}
    if args.universe.exists():
        names = {r['stock']: r['name'] for r in json.loads(args.universe.read_text(encoding='utf-8'))['rows']}
    panel = {}
    if args.forecast_panel:
        panel = {c['stock']: c for c in json.loads(args.forecast_panel.read_text(encoding='utf-8'))['companies']}
    args.output.mkdir(parents=True, exist_ok=True)
    count = 0
    for stock in sorted({r.get('stock') for r in ledger_rows(ledger) if isinstance(r, dict)}):
        entry = panel.get(stock)
        fragment = render_orders_section({'stock': stock, 'co': names.get(stock, entry['company_name'] if entry else stock)},
                                         ledger, entry, today=args.today)
        (args.output / (stock + '.html')).write_text(fragment + '\n', encoding='utf-8')
        count += 1
    print(f'Rendered {count} company order sections; inline SVG/table; offline.')


if __name__ == '__main__':
    main()
