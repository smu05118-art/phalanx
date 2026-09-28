#!/usr/bin/env python3
"""Drop-in KCE orders detail views: Gantt / quarterly roll-off schedule / clients.
Standard library only, existing theme tokens (--bg/--pn/--ln/--tx/--a), inline SVG, no JS/CSS assets.
Run: python3 -B output/kce_orders_views.py [--today YYYY-MM-DD] (writes sample fragments to output/samples/).
Check: python3 -B output/selfcheck_kce.py --samples (assertions over the whole panel; see kce_ORDERS_SPEC.md).

Ledger semantics (input/kce_panel.json, one entry per company):
  fq[]      observed quarters; k = len(fq)-1 is the reference quarter (2026Q2 for most companies, older for some 신규 ledgers)
  fqF[]     fq + 4 forecast quarters for the '정밀' pipeline; null for the '신규' pipeline
  sites[]   II-4 site rows: id, nm, cl(발주처), reg, seg/seg2(공종), agg, sd/ed(착공/완공예정), amt/cmp/bal[] aligned to fqF or fq
  agg       {ids,names} = representative row that duplicates listed component sites (excluded);
            true = residual '기타' bundle of unlisted small sites (real backlog, no dates/client — kept, flagged)
Amount shown everywhere is the site's 계약잔액 (bal) at the reference quarter. 도급액 (amt) is carried for tooltips/tables only.
Amounts are rendered only for the '정밀' pipeline (백만원 verified in LOGIC.md §5); '신규' ledgers show counts and periods only.
"""
import sys
sys.dont_write_bytecode = True
import datetime
import html
import json
import math
import re
from pathlib import Path

UNIT_VERIFIED_SRC_PREFIX = '정밀'   # LOGIC.md §5: 백만원 단위가 연간 매출 공시와 대조된 파이프라인. 유일한 금액 표시 근거.
HORIZON_START, HORIZON_END = '2026Q3', '2028Q4'
TOP_N_CLIENTS = 10
GANTT_YEARS_BEFORE = 12   # time axis clipping around the reference quarter (clipped bars get ◂ / ▸ markers)
GANTT_YEARS_AFTER = 12

PALETTE = ['#4cc9f0', '#f4a261', '#a3e635', '#e879a0', '#c084fc', '#facc15', '#34d399', '#fb923c', '#60a5fa', '#f472b6', '#94a3b8', '#e5e7eb']
CATEGORY_COLORS = {   # fixed hues for labels seen in the panel; a label keeps its hue unless a heavier synonym already took it
    '건축': '#4cc9f0', '건축주택': '#4cc9f0', '일반건축': '#4cc9f0', 'Home Solution': '#4cc9f0',
    '주택': '#60a5fa', '외주주택': '#60a5fa', '자체공사': '#c084fc',
    '토목': '#a3e635', '인프라': '#a3e635',
    '플랜트': '#f4a261', '플랜트인프라': '#f4a261', '화공': '#f4a261',
    '플랜트전력': '#fb923c', '비화공': '#facc15', '환경': '#34d399',
    '기타': '#94a3b8', '미분류': '#6b7280',
}

ANON_EXACT = {'-', '—', '–', '.', '기타', '기타등', '기타 등', '개인', '개인등', '개인 등', '익명', '비공개', '미상', '미정', '민간', '다수',
              '해당없음', '없음', 'n/a', 'na', '수분양자', '수분양자등', '수분양자 등', '조합원', '입주자'}
ANON_PATTERNS = [re.compile(p) for p in (
    r'^[A-Za-z]\s*(사|社|회사|건설|법인)$',                        # A사, B 사
    r'\*',                                                       # 서*수 — masked personal name
    r'^[○◯〇●ㅇ]{1,4}',                                           # ○○건설 (Korean circle masks; any label starting with them)
    r'^[OoXx]{2,4}(\s*(사|社|회사|건설|법인|주식회사|개발))?$',       # OO건설 / xx사 — whole label must be the mask (OPWP, Orsted, X Energy stay named)
    r'^(개인|기타|익명|민간)\s*[\d()\[\]]*$',
    r'^수분양자',
)]
SELF_PREFIXES = ('자체', '자사', '직영')       # own-development rows: named, but not an external client
RESIDUAL_LABEL = '소액 현장 묶음'              # display label for agg:true residual bundles inside the anonymous client line

REASONS = {
    'blank': '완공예정일 미기재(빈 칸)', 'null': '완공예정일 없음(null)', 'invalid': '완공예정일 형식 불명',
    'residual': '소액 현장 묶음(agg) — 개별 현장 미공시라 발주처·기간 없음',
    'aggregate': '대표 합산행(agg{ids}) — 구성 현장이 따로 있어 이중계산 방지', 'inactive': '기준 분기 원장에 잔액 없음(완료·제외·미보고)',
    'zero': '기준 분기 잔액 0', 'negative': '기준 분기 잔액 음수(원장 이상치)',
}
CLIENT_CLASS_LABEL = {'blank': '미기재', 'generic': '총칭', 'masked': '가명·마스킹', 'residual': '소액 묶음', 'self': '자체사업', 'named': '실명',
                      'anonymous': '익명', 'rest': '실명'}
NEGATIVE_WARNING = '⚠ 음수 원장 대용치: 실제 매출로 해석 불가'


# ----------------------------------------------------------------------------- basic helpers (same vocabulary as forecast renderer)
def esc(x):
    return html.escape(str(x), quote=True)


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def fmt(v):
    """Ledger balances are integer 백만원; the forecast renderer prints 3 decimals because its values are model outputs."""
    return f'{v:,.0f}' if number(v) else '—'


def pct(v):
    return f'{v * 100:.1f}%' if number(v) else '—'


def _em(s):
    """Rough rendered width in em: CJK/full-width glyphs ≈ 1em, everything else ≈ 0.55em."""
    return sum(1.0 if ord(ch) > 0x2E7F else 0.55 for ch in s)


def _fit(s, max_em):
    """Truncate to an estimated width budget (em) with an ellipsis."""
    s = '' if s is None else str(s)
    if _em(s) <= max_em:
        return s
    out = ''
    for ch in s:
        if _em(out + ch) > max_em - 1.0:
            break
        out += ch
    return out + '…'


def table_html(headers, rows, caption):
    return ('<div style="overflow-x:auto"><table style="width:100%"><caption style="text-align:left">' + esc(caption) +
            '</caption><thead><tr>' + ''.join('<th scope="col">' + esc(h) + '</th>' for h in headers) +
            '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(('<th scope="row">' if i == 0 else '<td>') + v + ('</th>' if i == 0 else '</td>')
                                                              for i, v in enumerate(row)) + '</tr>' for row in rows) + '</tbody></table></div>')


# ----------------------------------------------------------------------------- dates and quarters
def _last_day(y, m):
    if m == 12:
        return datetime.date(y, 12, 31)
    return datetime.date(y, m + 1, 1) - datetime.timedelta(days=1)


def parse_date(raw, role='end'):
    """Return (date|None, precision|reason). Month/year precision is rounded to the first day (role='start') or last day (role='end')."""
    if raw is None:
        return None, 'null'
    if isinstance(raw, datetime.datetime):
        return raw.date(), 'day'
    if isinstance(raw, datetime.date):
        return raw, 'day'
    if not isinstance(raw, str):
        return None, 'invalid'
    t = raw.strip().replace('.', '-').replace('/', '-').rstrip('-')
    if not t:
        return None, 'blank'
    try:
        m = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})', t)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), 'day'
        m = re.fullmatch(r'(\d{4})-(\d{1,2})', t)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            return (datetime.date(y, mo, 1) if role == 'start' else _last_day(y, mo)), 'month'
        m = re.fullmatch(r'(\d{4})', t)
        if m:
            y = int(m.group(1))
            return (datetime.date(y, 1, 1) if role == 'start' else datetime.date(y, 12, 31)), 'year'
    except ValueError:
        return None, 'invalid'
    return None, 'invalid'


def _as_date(v):
    if v is None:
        return datetime.date.today()
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    d, _ = parse_date(str(v), 'start')
    if d is None:
        raise ValueError(f'unparseable date {v!r}')
    return d


def quarter_of(d):
    return f'{d.year}Q{(d.month - 1) // 3 + 1}'


def quarter_index(q):
    m = re.fullmatch(r'(\d{4})Q([1-4])', str(q or ''))
    if not m:
        raise ValueError(f'bad quarter label {q!r}')
    return int(m.group(1)) * 4 + int(m.group(2)) - 1


def quarter_label(i):
    return f'{i // 4}Q{i % 4 + 1}'


def quarter_range(a, b):
    return [quarter_label(i) for i in range(quarter_index(a), quarter_index(b) + 1)]


def quarter_start(q):
    i = quarter_index(q)
    return datetime.date(i // 4, (i % 4) * 3 + 1, 1)


def quarter_end(q):
    i = quarter_index(q)
    return _last_day(i // 4, (i % 4) * 3 + 3)


# ----------------------------------------------------------------------------- client labels
def client_class(raw):
    """'named' | 'self' | 'blank' | 'generic' | 'masked'. Anything but 'named'/'self' is pooled into the anonymous line."""
    t = raw.strip() if isinstance(raw, str) else ''
    if not t:
        return 'blank'
    if t in ('-', '—', '–', '.'):
        return 'blank'
    if t.startswith(SELF_PREFIXES):
        return 'self'
    squashed = re.sub(r'\s+', '', t)
    if squashed in ANON_EXACT or t.lower() in ANON_EXACT or squashed.lower() in ANON_EXACT:
        return 'generic'
    for p in ANON_PATTERNS:
        if p.search(t):
            return 'masked'
    return 'named'


def money_unit_verified(panel_entry, forecast_entry=None):
    """(bool, reason). Amounts are rendered only when True; otherwise views show counts and periods.
    The only accepted evidence is the ledger pipeline itself (src '정밀…'). A forecast entry's own money_unit says nothing about
    this ledger's cells, so it is deliberately NOT used (forecast_entry is accepted for signature symmetry only)."""
    src = panel_entry.get('src') or ''
    if isinstance(src, str) and src.startswith(UNIT_VERIFIED_SRC_PREFIX):
        return True, '정밀 파이프라인 — 백만원 단위가 연간 매출 공시와 대조됨(LOGIC.md §5)'
    return False, "'신규' 파이프라인 — 금액 단위가 원문과 대조되지 않아 건수·기간만 표시"


# ----------------------------------------------------------------------------- ledger → contracts
def _cell(arr, k):
    if isinstance(arr, list) and 0 <= k < len(arr) and number(arr[k]):
        return arr[k]
    return None


def _first_seen(site, axis):
    for i, q in enumerate(axis):
        for key in ('bal', 'amt', 'cmp'):
            if _cell(site.get(key), i) is not None:
                return q
    return None


def contracts_from_panel(panel_entry, sites=None):
    """Normalize II-4 site rows of one company into contract dicts (reference quarter = last observed quarter)."""
    fq = list(panel_entry.get('fq') or [])
    axis = list(panel_entry.get('fqF') or fq)
    k = len(fq) - 1
    origin = fq[k] if k >= 0 else None
    if sites is None:
        sites = panel_entry.get('sites') or []
    out = []
    for s in sites:
        if not isinstance(s, dict):
            continue
        bal, amt, cmp_ = _cell(s.get('bal'), k), _cell(s.get('amt'), k), _cell(s.get('cmp'), k)
        mark = None
        filled = s.get('sFilled')
        if isinstance(filled, list) and 0 <= k < len(filled):
            mark = filled[k]
        elif isinstance(filled, dict):
            mark = filled.get(str(k), filled.get(k))
        agg = s.get('agg')
        is_agg = isinstance(agg, dict)      # representative row whose components are listed separately → exclude
        is_residual = agg is True           # residual bundle of unlisted small sites → real backlog without dates/client
        start, sprec = parse_date(s.get('sd'), 'start')
        end, eprec = parse_date(s.get('ed'), 'end')
        cat = s.get('seg2') or s.get('seg') or '미분류'
        cat = cat.strip() if isinstance(cat, str) and cat.strip() else '미분류'
        client_raw = s.get('cl') if isinstance(s.get('cl'), str) else ''
        client = client_raw.strip()
        if is_agg:
            status = 'aggregate'
        elif bal is None:
            status = 'inactive'
        elif bal == 0:
            status = 'zero'
        elif bal < 0:
            status = 'negative'
        else:
            status = 'active'
        measured = mark in (None, '')
        amount = bal if (status == 'active' and measured) else None
        amount_reason = None if (status != 'active' or measured) else f'보전값(sFilled={mark}) — 실측 아님'
        out.append({
            'id': str(s.get('id') or ''), 'name': str(s.get('nm') or ''), 'client': client,
            'client_class': 'residual' if is_residual else client_class(client),
            'region': s.get('reg') if isinstance(s.get('reg'), str) else '', 'category': cat,
            'start': start, 'start_precision': sprec if start else None, 'start_reason': None if start else sprec,
            'end': end, 'end_precision': eprec if end else None, 'end_reason': None if end else eprec,
            'balance': bal, 'contract_amount': amt, 'completed': cmp_, 'filled_mark': mark,
            'amount': amount, 'amount_reason': amount_reason,
            'status': status, 'is_agg': is_agg, 'residual': is_residual, 'agg_info': agg if isinstance(agg, dict) else None,
            'origin': origin, 'first_seen': _first_seen(s, axis),
            'date_order_error': bool(start and end and start > end),
        })
    return out


def _looks_raw(contracts):
    return bool(contracts) and isinstance(contracts[0], dict) and 'status' not in contracts[0] and ('amt' in contracts[0] or 'bal' in contracts[0])


def status_counts(contracts):
    out = {'total': len(contracts), 'active': 0, 'active_with_end': 0, 'active_no_end': 0, 'zero': 0, 'negative': 0, 'inactive': 0, 'aggregate': 0,
           'amount_missing': 0, 'residual': 0, 'residual_amount': 0.0}
    for c in contracts:
        out[c['status']] += 1
        if c['status'] == 'active':
            out['active_with_end' if c['end'] else 'active_no_end'] += 1
            if c['amount'] is None:
                out['amount_missing'] += 1
            if c['residual']:
                out['residual'] += 1
                if number(c['amount']):
                    out['residual_amount'] += c['amount']
    return out


def category_colors(contracts, money_ok=True):
    weight = {}
    for c in contracts:
        w = c['amount'] if (money_ok and number(c['amount'])) else 1
        weight[c['category']] = weight.get(c['category'], 0) + w
    order = sorted(weight, key=lambda key: (-weight[key], key))
    colors, used = {}, set()
    for cat in order:                       # pass 1: fixed hues for known labels (heaviest synonym wins a shared hue)
        col = CATEGORY_COLORS.get(cat)
        if col is not None and col not in used:
            colors[cat] = col
            used.add(col)
    for cat in order:                       # pass 2: everything else from unused palette entries, then generated hues
        if cat in colors:
            continue
        col = next((p for p in PALETTE if p not in used), None)
        if col is None:
            col = f'hsl({(len(colors) * 47) % 360},65%,62%)'
        colors[cat] = col
        used.add(col)
    return colors


def _origin_of(contracts):
    return next((c['origin'] for c in contracts if c.get('origin')), None)


# ----------------------------------------------------------------------------- view 1: Gantt
def build_gantt(contracts, today=None, money_ok=True, uid='orders-gantt', max_rows=None, colors=None):
    """One bar per active contract with an end date, sorted by end date; contracts without end date are listed separately."""
    today = _as_date(today)
    active = [c for c in contracts if c['status'] == 'active']
    rows = sorted((c for c in active if c['end'] is not None),
                  key=lambda c: (c['end'], -(c['amount'] if number(c['amount']) else 0), c['id']))
    no_end = [c for c in active if c['end'] is None]
    truncated = 0
    if max_rows is not None and len(rows) > max_rows:
        truncated = len(rows) - max_rows
        rows = rows[:max_rows]
    colors = colors or category_colors(active, money_ok)
    origin = _origin_of(contracts)
    origin_end = quarter_end(origin) if origin else None
    anchor = origin_end or today
    snapshot = origin_end or today          # balances are as of this date; 'overdue' is judged against it, not against today

    def bar_start(c):
        if c['start'] is not None:
            return c['start'], 'start'
        if c['first_seen']:
            return quarter_start(c['first_seen']), 'first_seen'
        return c['end'], 'end'

    starts = [bar_start(c)[0] for c in rows]
    ends = [c['end'] for c in rows]
    lo = min(starts + [anchor, today])
    hi = max(ends + [anchor, today])
    tmin = max(lo, datetime.date(anchor.year - GANTT_YEARS_BEFORE, 1, 1))
    tmax = min(hi, datetime.date(anchor.year + GANTT_YEARS_AFTER, 12, 31))
    tmin, tmax = min(tmin, today, anchor), max(tmax, today, anchor)     # reference lines are always inside the axis
    if tmax <= tmin:
        tmax = tmin + datetime.timedelta(days=366)
    span = (tmax - tmin).days
    W, LEFT, RIGHT = 1100, 420, 96
    x0, x1 = LEFT + 6, W - RIGHT
    NAME_X, NAME_EM, CLIENT_X, CLIENT_EM = 6, 24, 254, 16      # name at 10px → 240px; client at 9px → 144px; both end before x0

    def x(d):
        if d < tmin:
            d = tmin
        if d > tmax:
            d = tmax
        return x0 + (d - tmin).days / span * (x1 - x0)

    PITCH, HEAD, FOOT = 16, 46, 22
    n = len(rows)
    H = HEAD + PITCH * max(n, 1) + FOOT
    max_amt = max([c['amount'] for c in rows if number(c['amount'])] or [0])
    desc = (f'{n}건 계약 막대, 종료일 순, 색=공종, 두께=기준 분기 잔액(백만원)' if money_ok
            else f'{n}건 계약 막대, 종료일 순, 색=공종, 금액 단위 미확인이라 두께 일정·금액 미표시')
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
           f'aria-labelledby="{uid}-title {uid}-desc" style="display:block;min-width:{W}px;color:var(--tx)">',
           f'<title id="{uid}-title">수주 간트 — 계약별 착공~완공예정 (오늘 {today.isoformat()})</title>',
           f'<desc id="{uid}-desc">{esc(desc)}</desc>',
           f'<rect x="{x0}" y="{HEAD}" width="{x1 - x0:.1f}" height="{PITCH * max(n, 1)}" fill="var(--bg)" fill-opacity=".35"/>']
    year_step = 2 if (tmax.year - tmin.year) > 15 else 1
    for yr in range(tmin.year, tmax.year + 1):
        d = datetime.date(yr, 1, 1)
        if tmin <= d <= tmax:
            xx = x(d)
            out.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{HEAD - 14}" y2="{H - FOOT}" stroke="var(--ln)"/>')
            if yr % year_step == 0:
                out.append(f'<text x="{xx + 3:.1f}" y="{HEAD - 17}" fill="var(--tx)" font-size="10">{yr}</text>')
                out.append(f'<text x="{xx + 3:.1f}" y="{H - FOOT + 12}" fill="var(--tx)" font-size="10">{yr}</text>')
        for mth in (4, 7, 10):
            q = datetime.date(yr, mth, 1)
            if tmin <= q <= tmax:
                xq = x(q)
                out.append(f'<line x1="{xq:.1f}" x2="{xq:.1f}" y1="{HEAD - 6}" y2="{H - FOOT}" stroke="var(--ln)" stroke-opacity=".35"/>')
    if origin_end:
        xo = x(origin_end)
        out.append(f'<line data-part="origin" x1="{xo:.1f}" x2="{xo:.1f}" y1="{HEAD - 34}" y2="{H - FOOT}" stroke="var(--tx)" stroke-dasharray="4 3"/>')
        out.append(f'<text x="{xo - 3:.1f}" y="{HEAD - 36}" text-anchor="end" fill="var(--tx)" font-size="10">기준 {esc(origin)}</text>')
    xt = x(today)
    out.append(f'<line data-part="today" x1="{xt:.1f}" x2="{xt:.1f}" y1="{HEAD - 34}" y2="{H - FOOT}" stroke="var(--a)" stroke-width="1.5"/>')
    out.append(f'<text x="{xt + 3:.1f}" y="{HEAD - 36}" fill="var(--a)" font-size="10">오늘 {today.isoformat()}</text>')
    amount_head = '잔액(백만원)' if money_ok else '잔액 미표시'
    out.append(f'<text x="{NAME_X}" y="{HEAD - 6}" fill="var(--tx)" font-size="10">현장</text>')
    out.append(f'<text x="{CLIENT_X}" y="{HEAD - 6}" fill="var(--tx)" font-size="10">발주처</text>')
    out.append(f'<text x="{W - 6}" y="{HEAD - 6}" text-anchor="end" fill="var(--tx)" font-size="10">{amount_head}</text>')
    stats = {'overdue': 0, 'overdue_dashed': 0, 'stale': 0, 'start_unknown': 0, 'clipped': 0, 'amount_missing': 0, 'order_error': 0, 'coarse_precision': 0}
    for i, c in enumerate(rows):
        yc = HEAD + i * PITCH + PITCH / 2
        s, s_kind = bar_start(c)
        e = c['end']
        if c['date_order_error']:
            stats['order_error'] += 1
        xs, xe = x(s), x(e)
        if xe < xs:
            xs, xe = xe, xs
        w = max(2.0, xe - xs)
        if s < tmin or e > tmax:
            stats['clipped'] += 1
        if s_kind != 'start':
            stats['start_unknown'] += 1
        overdue = e < snapshot                                   # planned end before the ledger snapshot, balance still there
        stale = (not overdue) and e < today                      # ended after the snapshot but before today: balance not refreshed
        if overdue:
            stats['overdue'] += 1
            if s_kind != 'start':
                stats['overdue_dashed'] += 1
        if stale:
            stats['stale'] += 1
        if c['end_precision'] in ('month', 'year') or c['start_precision'] in ('month', 'year'):
            stats['coarse_precision'] += 1
        amt = c['amount']
        if amt is None:
            stats['amount_missing'] += 1
        h = 4 + 9 * math.sqrt(amt / max_amt) if (money_ok and number(amt) and max_amt > 0) else 8.0
        color = colors.get(c['category'], PALETTE[-1])
        money_txt = fmt(amt) if money_ok else '단위 미확인'
        prec = {'month': ' (월 단위)', 'year': ' (연 단위)'}.get(c['end_precision'], '')
        tip_parts = [c['id'], c['name'], '발주처 ' + (c['client'] or '(미기재)'), '공종 ' + c['category'], '지역 ' + (c['region'] or '-'),
                     '착공 ' + (c['start'].isoformat() if c['start'] else '미기재'), '완공예정 ' + e.isoformat() + prec,
                     '잔액 ' + money_txt, '도급액 ' + (fmt(c['contract_amount']) if money_ok else '단위 미확인')]
        if overdue:
            tip_parts.append(f'지연: 완공예정일이 기준 분기말({snapshot.isoformat()}) 이전인데 잔액 보유')
        if stale:
            tip_parts.append(f'완공예정일이 기준 분기말 이후·오늘 이전 — 잔액은 기준 분기({origin}) 값(갱신 전)')
        if s_kind == 'first_seen':
            tip_parts.append('착공일 미기재 — 막대 시작은 원장 최초 관측 분기')
        if c['date_order_error']:
            tip_parts.append('착공일이 완공예정일보다 늦음(원장 오류)')
        if c['amount_reason']:
            tip_parts.append(c['amount_reason'])
        amount_attr = fmt(amt) if (money_ok and number(amt)) else ''
        ov_attr = ' data-overdue="1"' if overdue else (' data-stale="1"' if stale else '')
        out.append(f'<g data-id="{esc(c["id"])}" data-end="{e.isoformat()}" data-category="{esc(c["category"])}" data-amount="{esc(amount_attr)}"{ov_attr}>'
                   f'<title>{esc(" · ".join(tip_parts))}</title>')
        out.append(f'<text x="{NAME_X}" y="{yc + 3.5:.1f}" fill="var(--tx)" font-size="10">{esc(_fit(c["name"], NAME_EM))}</text>')
        out.append(f'<text x="{CLIENT_X}" y="{yc + 3.5:.1f}" fill="var(--tx)" fill-opacity=".7" font-size="9">{esc(_fit(c["client"] or "(미기재)", CLIENT_EM))}</text>')
        style = ''
        if s_kind != 'start':
            style = ' stroke="var(--tx)" stroke-dasharray="3 2" fill-opacity=".35"' + (' stroke-width="1.6"' if overdue else '')
        elif overdue:
            style = ' stroke="var(--tx)" stroke-width="1.2"'
        if amt is None and s_kind == 'start':
            style += ' fill-opacity=".25"'
        out.append(f'<rect data-part="bar" x="{xs:.1f}" y="{yc - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{color}"{style}/>')
        if s < tmin:
            out.append(f'<text x="{x0 - 2}" y="{yc + 3.5:.1f}" text-anchor="end" fill="var(--tx)" font-size="9">◂</text>')
        if e > tmax:
            out.append(f'<text x="{x1 + 2}" y="{yc + 3.5:.1f}" fill="var(--tx)" font-size="9">▸</text>')
        label = fmt(amt) if money_ok else ''
        out.append(f'<text x="{W - 6}" y="{yc + 3.5:.1f}" text-anchor="end" fill="var(--tx)" font-size="9">{esc(label)}</text></g>')
    if not rows:
        out.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{HEAD + PITCH / 2 + 4:.1f}" text-anchor="middle" fill="var(--tx)" font-size="12">종료일 있는 활성 계약 없음</text>')
    out.append('</svg>')
    svg = ''.join(out)

    # legend + notes + no-end table
    cat_stat = {}
    for c in rows:
        st = cat_stat.setdefault(c['category'], [0, 0.0])
        st[0] += 1
        if number(c['amount']):
            st[1] += c['amount']
    legend = ''.join(
        f'<span style="display:inline-block;margin:.1rem .6rem .1rem 0"><span style="display:inline-block;width:.8em;height:.8em;background:{colors.get(cat, PALETTE[-1])};'
        f'vertical-align:middle;margin-right:.3em"></span>{esc(cat)} {st[0]}건' + (f' · {fmt(st[1])}' if money_ok else '') + '</span>'
        for cat, st in sorted(cat_stat.items(), key=lambda kv: (-kv[1][1] if money_ok else -kv[1][0], kv[0])))
    notes = [f'막대 {n}건 = 기준 분기 잔액 보유 계약 중 완공예정일이 있는 건. 정렬 종료일 오름차순. 색 = 공종(seg2, 없으면 seg). '
             + ('두께 = 잔액 제곱근 비례, 우측 숫자 = 잔액(백만원).' if money_ok else '금액 단위 미확인 — 두께 일정, 금액 미표시.')]
    if stats['overdue']:
        notes.append(f'테두리 강조 {stats["overdue"]}건: 완공예정일이 기준 분기말({snapshot.isoformat()}) 이전인데 잔액이 남아 있음(지연 또는 완공예정일 미갱신)'
                     + (f'; 그중 착공일 미기재 {stats["overdue_dashed"]}건은 점선 테두리.' if stats['overdue_dashed'] else '.'))
    if stats['stale']:
        notes.append(f'{stats["stale"]}건은 완공예정일이 기준 분기말 이후·오늘 이전 — 잔액은 기준 분기 값이며 그 뒤 갱신되지 않은 상태(지연 여부 판단 불가).')
    if stats['start_unknown']:
        notes.append(f'점선 막대 {stats["start_unknown"]}건: 착공일 미기재 — 막대 시작을 원장 최초 관측 분기로 표시(착공일 대용이 아님).')
    if stats['amount_missing']:
        notes.append(f'연한 막대 {stats["amount_missing"]}건: 기준 분기 값이 보전값(sFilled)이라 금액 미표시.')
    if stats['coarse_precision']:
        notes.append(f'{stats["coarse_precision"]}건은 착공·완공예정일이 월/연 단위 표기(월초·연초 / 월말·연말로 배치).')
    if stats['clipped']:
        notes.append(f'{stats["clipped"]}건은 시간축(기준 분기 ±{GANTT_YEARS_BEFORE}년) 밖으로 잘림 — ◂/▸ 표시, 툴팁에 실제 날짜.')
    if stats['order_error']:
        notes.append(f'{stats["order_error"]}건은 착공일이 완공예정일보다 늦음(원장 오류) — 두 날짜 사이를 그대로 표시.')
    if truncated:
        notes.append(f'⚠ 표시 제한으로 {truncated}건이 잘렸습니다(max_rows). 합계 검증은 잘리지 않은 전체 집합 기준.')
    no_end_rows = []
    for c in sorted(no_end, key=lambda c: (-(c['amount'] if number(c['amount']) else 0), c['id'])):
        reason = REASONS['residual'] if c['residual'] else REASONS.get(c['end_reason'], c['end_reason'] or '완공예정일 없음')
        no_end_rows.append([esc(_trunc(c['name'], 40)), esc(c['client'] or '(미기재)'), esc(c['category']),
                            esc(c['start'].isoformat() if c['start'] else '— (착공일 없음)'),
                            esc(fmt(c['amount']) if money_ok else '단위 미확인'),
                            esc(fmt(c['contract_amount']) if money_ok else '단위 미확인'), esc(reason)])
    no_end_sum = sum(c['amount'] for c in no_end if number(c['amount']))
    n_residual = sum(1 for c in no_end if c['residual'])
    if no_end:
        no_end_html = (f'<p><strong>종료일 없는 활성 계약 {len(no_end)}건</strong>' + (f' · 잔액 합계 {fmt(no_end_sum)}' if money_ok else '')
                       + (f' · 소액 현장 묶음 {n_residual}건 포함' if n_residual else '')
                       + ' — 간트에서 제외하고 아래에 따로 둡니다. 사유는 행마다 표기.</p>'
                       + table_html(['현장', '발주처', '공종', '착공', '잔액', '도급액', '종료일 없는 사유'], no_end_rows, '종료일 없는 활성 계약'))
    else:
        no_end_html = '<p>종료일 없는 활성 계약: 없음.</p>'
    html_out = (f'<div style="overflow:auto;max-height:75vh;border:1px solid var(--ln)">{svg}</div>'
                + f'<p style="margin:.4rem 0">{legend}</p>' + '<p><small>' + esc(' '.join(notes)) + '</small></p>' + no_end_html)
    return {'html': html_out, 'svg': svg, 'rows': rows, 'no_end': no_end, 'bars': n, 'truncated': truncated, 'colors': colors,
            'stats': stats, 'axis': {'tmin': tmin, 'tmax': tmax, 'today': today, 'origin': origin, 'origin_end': origin_end},
            'no_end_amount': no_end_sum}


def _trunc(s, n):
    s = '' if s is None else str(s)
    return s if len(s) <= n else s[:max(1, n - 1)] + '…'


# ----------------------------------------------------------------------------- view 2: quarterly roll-off schedule
def _estimate_row(est, q):
    """(existing-backlog estimate, kind) for a quarter from the base scenario; kind ∈ existing|covered|unestimated|no_row."""
    r = est.get(q)
    if not r:
        return None, 'no_row'
    if number(r.get('existing_backlog_revenue')):
        return r['existing_backlog_revenue'], 'existing'
    if number(r.get('covered_sites_partial_revenue')):
        return r['covered_sites_partial_revenue'], 'covered'
    return None, 'unestimated'


def build_schedule(contracts, forecast_entry=None, money_ok=True, horizon=(HORIZON_START, HORIZON_END), uid='orders-schedule', colors=None,
                   no_forecast_reason=None):
    """Bucket active contracts by end quarter (before-horizon / each horizon quarter / after-horizon / no end date) and set
    each horizon quarter next to the page's Y+2 base-scenario 잔고분 estimate. Nothing is adjusted to reconcile the two."""
    active = [c for c in contracts if c['status'] == 'active']
    colors = colors or category_colors(active, money_ok)
    origin = _origin_of(contracts)
    hq = quarter_range(horizon[0], horizon[1])
    h0, h1 = quarter_index(horizon[0]), quarter_index(horizon[1])

    def bucket(key, label, kind):
        return {'key': key, 'label': label, 'kind': kind, 'count': 0, 'amount': 0.0, 'amount_missing': 0, 'by_category': {}}

    buckets = ([bucket('before', f'~{quarter_label(h0 - 1)} (지평 전)', 'before')] + [bucket(q, q, 'quarter') for q in hq]
               + [bucket('after', f'{quarter_label(h1 + 1)}~ (지평 후)', 'after'), bucket('no_end', '종료일 없음', 'no_end')])
    index = {b['key']: b for b in buckets}
    for c in active:
        if c['end'] is None:
            key = 'no_end'
        else:
            qi = quarter_index(quarter_of(c['end']))
            key = 'before' if qi < h0 else ('after' if qi > h1 else quarter_label(qi))
        b = index[key]
        b['count'] += 1
        if number(c['amount']):
            b['amount'] += c['amount']
            b['by_category'][c['category']] = b['by_category'].get(c['category'], 0.0) + c['amount']
        else:
            b['amount_missing'] += 1
    total_amount = sum(c['amount'] for c in active if number(c['amount']))
    total_count = len(active)
    est, est_status = {}, None
    if forecast_entry is not None:
        base = (forecast_entry.get('scenarios') or {}).get('base') or {}
        for r in base.get('quarterly') or []:
            if isinstance(r, dict) and r.get('quarter'):
                est[r['quarter']] = r
        est_status = forecast_entry.get('status')
    absent = no_forecast_reason or 'Y+2 추정 항목이 전달되지 않음(추정 없음이 아니라 미전달)'

    # chart
    short = {'before': '지평 전', 'after': '지평 후', 'no_end': '무종료'}
    n = len(buckets)
    vals = [b['amount'] if money_ok else float(b['count']) for b in buckets]
    est_ex, est_kind, est_tot = [], [], []
    for b in buckets:
        if money_ok and b['kind'] == 'quarter':
            v, kind = _estimate_row(est, b['key'])
            r = est.get(b['key']) or {}
            est_ex.append(v)
            est_kind.append(kind)
            est_tot.append(r.get('value') if number(r.get('value')) else None)
        else:
            est_ex.append(None)
            est_kind.append(None)
            est_tot.append(None)
    hi = max([0.0] + vals + [v for v in est_ex if number(v) and v > 0] + [v for v in est_tot if number(v) and v > 0])
    if hi <= 0:
        hi = 1.0
    top, bottom, left, width = 30, 186, 84, 730

    def y(v):
        return top + (hi - v) / hi * (bottom - top)

    step = width / n
    bar = min(28.0, step * .46)
    ebar = min(9.0, step * .16)
    unit = '백만원' if money_ok else '건'
    title = '분기 전환 스케줄: 종료 분기별 계약 ' + ('잔액' if money_ok else '건수') + ' vs 기준 시나리오 잔고분 추정'
    descs = []
    for i, b in enumerate(buckets):
        d = f'{b["label"]}: 이 분기에 끝나는 계약 {b["count"]}건'
        if money_ok:
            d += f'·합계 {fmt(b["amount"])}'
            if number(est_ex[i]):
                d += f'; 추정 잔고분 {fmt(est_ex[i])}' + (' (일부 현장)' if est_kind[i] == 'covered' else '') + (' ' + NEGATIVE_WARNING if est_ex[i] < 0 else '')
            if number(est_tot[i]):
                d += f'; 추정 전체 {fmt(est_tot[i])}' + (' ' + NEGATIVE_WARNING if est_tot[i] < 0 else '')
        descs.append(d)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 222" role="img" aria-labelledby="{uid}-title {uid}-desc" '
           f'style="width:100%;height:auto;display:block;color:var(--tx)">',
           f'<title id="{uid}-title">{esc(title)} ({unit})</title>', f'<desc id="{uid}-desc">{esc(" / ".join(descs))}</desc>',
           f'<line x1="{left}" x2="{left + width}" y1="{bottom}" y2="{bottom}" stroke="var(--ln)"/>',
           f'<text x="{left - 6}" y="{bottom + 4}" text-anchor="end" fill="var(--tx)" font-size="10">0</text>',
           f'<text x="{left - 6}" y="{top + 4}" text-anchor="end" fill="var(--tx)" font-size="10">{hi:,.0f}</text>']
    for i, b in enumerate(buckets):
        xc = left + (i + .5) * step
        dim = ' opacity=".55"' if b['kind'] != 'quarter' else ''
        out.append(f'<g data-bucket="{esc(b["key"])}" data-count="{b["count"]}" data-amount="{fmt(b["amount"]) if money_ok else ""}"{dim}><title>{esc(descs[i])}</title>')
        if money_ok:
            offset = 0.0
            for cat, a in sorted(b['by_category'].items(), key=lambda kv: (-kv[1], kv[0])):
                ya, yb = y(offset), y(offset + a)
                out.append(f'<rect data-part="contract" data-category="{esc(cat)}" x="{xc - bar / 2:.1f}" y="{min(ya, yb):.1f}" width="{bar:.1f}" '
                           f'height="{abs(ya - yb):.1f}" fill="{colors.get(cat, PALETTE[-1])}"/>')
                offset += a
        elif b['count'] > 0:
            yb = y(float(b['count']))
            out.append(f'<rect data-part="contract" x="{xc - bar / 2:.1f}" y="{yb:.1f}" width="{bar:.1f}" height="{bottom - yb:.1f}" fill="var(--a)"/>')
        if number(est_ex[i]):
            if est_ex[i] >= 0:
                ye = y(est_ex[i])
                dash = ' stroke-dasharray="3 2"' if est_kind[i] == 'covered' else ''
                out.append(f'<rect data-part="estimate" x="{xc + bar / 2 + 2:.1f}" y="{ye:.1f}" width="{ebar:.1f}" height="{bottom - ye:.1f}" '
                           f'fill="none" stroke="var(--a)" stroke-width="1.4"{dash}/>')
            else:
                out.append(f'<text data-part="estimate-negative" x="{xc + bar / 2 + 2:.1f}" y="{bottom - 4}" fill="var(--a)" font-size="9">⚠음수</text>')
        if number(est_tot[i]) and est_tot[i] >= 0:
            yt = y(est_tot[i])
            out.append(f'<path data-part="estimate-total" d="M{xc + bar / 2 + 1:.1f},{yt:.1f}H{xc + bar / 2 + 3 + ebar:.1f}" stroke="var(--tx)" stroke-width="1.2"/>')
        if b['count'] > 0:
            ytop = y(vals[i]) - 3
            out.append(f'<text x="{xc:.1f}" y="{max(top - 2, ytop):.1f}" text-anchor="middle" fill="var(--tx)" font-size="9">{b["count"]}건</text>')
        lab = short.get(b['kind'], b['label'])
        out.append(f'<text x="{xc:.1f}" y="{bottom + 15}" text-anchor="middle" fill="var(--tx)" font-size="9">{esc(lab)}</text></g>')
    legend_txt = ('채움 막대 = 이 분기에 끝나는 계약 잔액(색=공종); 테두리 막대 = 기준 시나리오 잔고분 추정; 가로 눈금 = 추정 전체(잔고분+신규분)' if money_ok
                  else '채움 막대 = 이 분기에 끝나는 계약 건수(금액 단위 미확인)')
    out.append(f'<text x="{left}" y="216" fill="var(--tx)" font-size="9">{esc(legend_txt)}</text>')
    out.append('</svg>')
    svg = ''.join(out)

    # table
    if money_ok:
        headers = ['분기', '이 분기에 끝나는 계약 건수', '이 분기에 끝나는 계약 잔액 합계', '누적 종료 잔액(지평 내)', '추정 잔고분(기준)', '누적 추정 잔고분(지평 내)',
                   '추정 전체(기준)', '차이 (종료 잔액 − 추정 잔고분)']
    else:
        headers = ['분기', '이 분기에 끝나는 계약 건수', '이 분기에 끝나는 계약 잔액 합계', '추정 잔고분(기준)', '추정 전체(기준)']
    trows = []
    cum_c = cum_e = 0.0
    for b in buckets:
        is_q = b['kind'] == 'quarter'
        amt_cell = fmt(b['amount']) if money_ok else '단위 미확인'
        if money_ok and b['amount_missing']:
            amt_cell += f' (+{b["amount_missing"]}건 보전값 제외)'
        if is_q:
            ex, kind = _estimate_row(est, b['key'])
            r = est.get(b['key']) or {}
            if not money_ok:
                est_cell = tot_cell = '— (금액 미표시)'
            elif forecast_entry is None:
                est_cell = tot_cell = '— (' + absent + ')'
            else:
                if kind == 'no_row':
                    est_cell = '— (추정 행 없음)'
                elif kind == 'unestimated':
                    est_cell = '— (미추정)'
                else:
                    est_cell = fmt(ex) + (' (일부 현장)' if kind == 'covered' else '') + (' ' + NEGATIVE_WARNING if ex < 0 else '')
                tot_cell = (fmt(r.get('value')) + (' ' + NEGATIVE_WARNING if r['value'] < 0 else '')) if number(r.get('value')) else '— (전체 미추정)'
            if money_ok:
                cum_c += b['amount']
                diff_cell = '— (추정 없음)'
                if number(ex):
                    cum_e += ex
                    diff_cell = f'{b["amount"] - ex:,.0f}'
                trows.append([esc(b['label']), str(b['count']), esc(amt_cell), fmt(cum_c), esc(est_cell), fmt(cum_e), esc(tot_cell), esc(diff_cell)])
            else:
                trows.append([esc(b['label']), str(b['count']), esc(amt_cell), esc(est_cell), esc(tot_cell)])
        else:
            outside = '— (지평 밖)'
            if money_ok:
                trows.append([esc(b['label']), str(b['count']), esc(amt_cell), outside, outside, outside, outside, outside])
            else:
                trows.append([esc(b['label']), str(b['count']), esc(amt_cell), outside, outside])
    na = '해당 없음'
    if money_ok:
        trows.append(['<strong>합계(활성 전체)</strong>', f'<strong>{total_count}</strong>', f'<strong>{fmt(total_amount)}</strong>', na, na, na, na, na])
    else:
        trows.append(['<strong>합계(활성 전체)</strong>', f'<strong>{total_count}</strong>', '단위 미확인', na, na])
    table = table_html(headers, trows, f'종료 분기별 계약 vs Y+2 추정 ({unit}; 지평 {hq[0]}~{hq[-1]}; 기준 분기 {origin or "불명"})')

    # factual notes on agreement/disagreement — no reconciliation
    notes = ['종료 계약 잔액 = 완공예정일이 그 분기에 속하는 활성 계약의 기준 분기 잔액을 종료 분기에 일괄 귀속한 값. '
             '추정 잔고분 = 기존 잔고를 공기 동안 균등 인식한 분기 매출 대용치(기준 시나리오; 잔고분은 시나리오 간 동일). 정의가 달라 분기별로 어긋나는 것이 정상입니다.']
    h_contract = sum(index[q]['amount'] for q in hq)
    h_count = sum(index[q]['count'] for q in hq)
    est_vals = [(q, _estimate_row(est, q)[0]) for q in hq]
    n_est = sum(1 for _, v in est_vals if number(v))
    h_est = sum(v for _, v in est_vals if number(v))
    comparison = {'horizon_contract_amount': h_contract if money_ok else None, 'horizon_contract_count': h_count,
                  'horizon_estimate_existing': h_est if n_est else None, 'estimated_quarters': n_est, 'total_active_amount': total_amount if money_ok else None}
    if forecast_entry is None:
        notes.append('추정치 열이 비어 있는 이유: ' + absent + '.')
    elif n_est == 0:
        notes.append('추정 항목에 잔고분 수치가 없어(상태 ' + str(est_status) + ') 금액 비교를 하지 않습니다.')
    elif not money_ok:
        notes.append('금액 단위 미확인으로 계약 합계를 표시하지 않으므로 추정치와의 금액 비교도 하지 않습니다. 건수만 참고하세요.')
    else:
        notes.append(f'지평 {hq[0]}~{hq[-1]}: 종료 계약 {h_count}건·잔액 합계 {fmt(h_contract)} vs 기준 시나리오 잔고분 추정 합계 {fmt(h_est)}({n_est}개 분기 추정). '
                     f'차이(종료 잔액 − 추정 잔고분) = {h_contract - h_est:,.0f}. 어느 쪽도 조정하지 않았습니다.')
        if h_est > total_amount:
            notes.append(f'⚠ 추정 잔고분 합계({fmt(h_est)})가 기준 분기 활성 잔액 합계({fmt(total_amount)})보다 큽니다 — 추정이 원장 잔액을 초과합니다.')
        for q, v in est_vals:
            b = index[q]
            if number(v) and b['count'] == 0:
                notes.append(f'{q}: 추정 잔고분 {fmt(v)} 있으나 이 분기에 끝나는 계약은 없음.')
            elif b['count'] > 0 and not number(v):
                notes.append(f'{q}: 계약 {b["count"]}건 종료 예정이나 추정 잔고분 없음(미추정).')
    if index['no_end']['count']:
        notes.append(f'종료일 없는 활성 계약 {index["no_end"]["count"]}건' + (f'(잔액 {fmt(index["no_end"]["amount"])})' if money_ok else '')
                     + '은 어느 분기에도 배치하지 않았습니다.')
    if index['after']['count']:
        notes.append(f'{index["after"]["label"]} 종료 {index["after"]["count"]}건' + (f'(잔액 {fmt(index["after"]["amount"])})' if money_ok else '') + '은 지평 밖입니다.')
    if index['before']['count']:
        notes.append(f'{index["before"]["label"]} {index["before"]["count"]}건' + (f'(잔액 {fmt(index["before"]["amount"])})' if money_ok else '')
                     + f': 완공예정일이 지평 시작 전인 계약(잔액은 기준 분기 {origin or "불명"} 값).')
        if origin:
            gap = (h0 - 1) - quarter_index(origin)
            if gap > 0:
                notes.append(f'기준 분기({origin})가 지평 시작 직전 분기보다 {gap}분기 앞서 있어, 그 사이에 끝난 계약의 잔액은 갱신되지 않은 값입니다.')
    html_out = svg + table + '<p><small>' + esc(' '.join(notes)) + '</small></p>'
    return {'html': html_out, 'svg': svg, 'buckets': buckets, 'index': index, 'total_amount': total_amount, 'total_count': total_count,
            'horizon': hq, 'estimates': est, 'comparison': comparison, 'notes': notes}


# ----------------------------------------------------------------------------- view 3: clients
def build_clients(contracts, money_ok=True, top_n=TOP_N_CLIENTS, uid='orders-clients'):
    """Aggregate active contracts by 발주처 label (verbatim, whitespace-trimmed). Anonymous/blank/generic/masked labels and residual
    bundles are pooled into ONE line and never ranked with named clients. Own-development rows ('자체…') stay named but are excluded
    from concentration metrics."""
    active = [c for c in contracts if c['status'] == 'active']
    groups = {}
    for c in active:
        cls = c['client_class']
        anon = cls in ('blank', 'generic', 'masked', 'residual')
        key = '__anon__' if anon else c['client']
        g = groups.get(key)
        if g is None:
            g = groups[key] = {'label': '익명·미기재 발주처' if anon else c['client'], 'class': 'anonymous' if anon else cls, 'count': 0, 'amount': 0.0,
                               'amount_missing': 0, 'max_end': None, 'no_end_count': 0, 'ids': [], 'labels': {}, 'members': 0}
        g['count'] += 1
        g['ids'].append(c['id'])
        if number(c['amount']):
            g['amount'] += c['amount']
        else:
            g['amount_missing'] += 1
        if c['end'] is None:
            g['no_end_count'] += 1
        elif g['max_end'] is None or c['end'] > g['max_end']:
            g['max_end'] = c['end']
        lab = RESIDUAL_LABEL if c['residual'] else (c['client'] if c['client'] else '(빈 칸)')
        g['labels'][lab] = g['labels'].get(lab, 0) + 1
    anon = groups.pop('__anon__', None)
    named = list(groups.values())
    for g in named:
        g['members'] = 1
    metric = (lambda g: g['amount']) if money_ok else (lambda g: float(g['count']))
    named.sort(key=lambda g: (-metric(g), -g['count'], g['label']))
    top = named[:top_n]
    rest = named[top_n:]
    rest_group = None
    if rest:
        rest_group = {'label': f'기타 실명 발주처 {len(rest)}개', 'class': 'rest', 'count': sum(g['count'] for g in rest), 'amount': sum(g['amount'] for g in rest),
                      'amount_missing': sum(g['amount_missing'] for g in rest), 'max_end': max((g['max_end'] for g in rest if g['max_end']), default=None),
                      'no_end_count': sum(g['no_end_count'] for g in rest), 'ids': [i for g in rest for i in g['ids']], 'labels': {}, 'members': len(rest)}
    total_amount = sum(c['amount'] for c in active if number(c['amount']))
    total_count = len(active)
    denom = total_amount if money_ok else float(total_count)

    def share(g):
        return (metric(g) / denom) if denom else None

    listed = top + ([rest_group] if rest_group else []) + ([anon] if anon else [])
    # concentration over identified external clients (excludes anonymous pool and own-development rows)
    ext = [g for g in named if g['class'] != 'self']
    ext_total = sum(metric(g) for g in ext)
    conc = {'top1': sum(metric(g) for g in ext[:1]) / denom if denom else None,
            'top3': sum(metric(g) for g in ext[:3]) / denom if denom else None,
            'top5': sum(metric(g) for g in ext[:5]) / denom if denom else None,
            'hhi_external': (sum((metric(g) / ext_total) ** 2 for g in ext) * 10000) if ext_total else None,
            'anonymous_share': (metric(anon) / denom) if (anon and denom) else (0.0 if denom else None),
            'self_share': (sum(metric(g) for g in named if g['class'] == 'self') / denom) if denom else None,
            'external_named_share': (ext_total / denom) if denom else None,
            'external_named_clients': len(ext), 'basis': '잔액' if money_ok else '건수'}

    # table
    unit_h = '잔액 합계(백만원)' if money_ok else '잔액 합계'
    headers = ['발주처', '구분', '건수', unit_h, '최장 완공예정일', '비중', '누적 비중']
    trows = []
    cum = 0.0
    for g in listed:
        sh = share(g)
        if sh is not None and g is not anon:
            cum += sh
        cum_cell = pct(cum) if (sh is not None and g is not anon) else ('— (분모 없음)' if sh is None else '(별도)')
        if g['class'] == 'anonymous':
            comp = ', '.join(f'{esc(k)} ×{v}' for k, v in sorted(g['labels'].items(), key=lambda kv: (-kv[1], kv[0])))
            name_cell = f'<strong>{esc(g["label"])}</strong><br><small>구성: {comp}</small>'
        else:
            name_cell = esc(g['label']) if g['class'] != 'rest' else f'<em>{esc(g["label"])}</em>'
        amt_cell = (fmt(g['amount']) + (f' (+{g["amount_missing"]}건 보전값 제외)' if g['amount_missing'] else '')) if money_ok else '단위 미확인'
        end_cell = g['max_end'].isoformat() if g['max_end'] else '— (종료일 없음)'
        if g['max_end'] and g['no_end_count']:
            end_cell += f' (종료일 없는 {g["no_end_count"]}건 제외)'
        trows.append([name_cell, esc(CLIENT_CLASS_LABEL.get(g['class'], '실명')), str(g['count']), esc(amt_cell), esc(end_cell), esc(pct(sh)), esc(cum_cell)])
    trows.append(['<strong>합계(활성 전체)</strong>', '해당 없음', f'<strong>{total_count}</strong>', f'<strong>{fmt(total_amount) if money_ok else "단위 미확인"}</strong>',
                  '해당 없음', '100.0%' if denom else '— (분모 없음)', '해당 없음'])
    table = table_html(headers, trows, f'발주처별 집계 (상위 {min(top_n, len(named))}개 + 나머지 묶음 + 익명 줄; 비중 기준 {conc["basis"]})')
    conc_rows = [['상위 1개 실명 외부 발주처', esc(pct(conc['top1']))], ['상위 3개', esc(pct(conc['top3']))], ['상위 5개', esc(pct(conc['top5']))],
                 ['HHI(실명 외부 발주처 내부, 0~10,000)', esc(f'{conc["hhi_external"]:,.0f}') if number(conc['hhi_external']) else '— (실명 외부 발주처 없음)'],
                 ['익명·미기재 비중', esc(pct(conc['anonymous_share']))], ['자체사업 비중', esc(pct(conc['self_share']))],
                 ['실명 외부 발주처 비중 (개수)', esc(pct(conc['external_named_share'])) + f' ({conc["external_named_clients"]}개)']]
    conc_table = table_html(['집중도 지표', '값'], conc_rows, f'발주처 집중도 (분모 = 활성 계약 {conc["basis"]} 전체)')

    # chart
    n = len(listed)
    H = 26 + n * 20 + 6
    maxv = max([metric(g) for g in listed] or [1.0]) or 1.0
    BAR_X, BAR_W, LABEL_EM = 270, 400, 25
    chart_desc = ' / '.join(g['label'] + ': ' + str(g['count']) + '건' for g in listed)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 {H}" role="img" aria-labelledby="{uid}-title {uid}-desc" style="width:100%;height:auto;display:block;color:var(--tx)">',
           f'<title id="{uid}-title">발주처별 {conc["basis"]} 비중</title>',
           f'<desc id="{uid}-desc">{esc(chart_desc)}</desc>']
    for i, g in enumerate(listed):
        yc = 20 + i * 20 + 10
        v = metric(g)
        w = BAR_W * v / maxv
        fill = 'var(--tx)' if g['class'] == 'anonymous' else 'var(--a)'
        op = '.45' if g['class'] in ('anonymous', 'rest') else ('.7' if g['class'] == 'self' else '1')
        val = fmt(v) if money_ok else f'{int(v)}건'
        out.append(f'<g data-client-class="{esc(g["class"])}" data-count="{g["count"]}"><title>{esc(g["label"])}: {g["count"]}건 · {esc(val)} · {esc(pct(share(g)))}</title>'
                   f'<text x="4" y="{yc + 3.5}" fill="var(--tx)" font-size="10">{esc(_fit(g["label"], LABEL_EM))}</text>'
                   f'<rect data-part="client" x="{BAR_X}" y="{yc - 7}" width="{w:.1f}" height="14" fill="{fill}" fill-opacity="{op}"/>'
                   f'<text x="{BAR_X + 4 + w:.1f}" y="{yc + 3.5}" fill="var(--tx)" font-size="9">{esc(val)} · {esc(pct(share(g)))}</text></g>')
    out.append('</svg>')
    svg = ''.join(out)
    notes = ['발주처 라벨은 원문 그대로(공백만 정리)이며 표기 변형(예: ㈜ 유무)을 합치지 않았습니다. '
             '익명·미기재(빈 칸, "-", 기타, 개인, A사, 마스킹 이름, 수분양자, 소액 현장 묶음 등)는 한 줄로만 모으고 실명과 섞지 않았으며 구성 라벨을 함께 적었습니다. '
             '"자체…" 라벨은 자체사업으로 표시하고 집중도 지표에서 제외했습니다. 최장 완공예정일은 종료일 있는 계약만의 최댓값입니다.']
    if not money_ok:
        notes.append('금액 단위 미확인 — 비중·집중도는 건수 기준.')
    html_out = table + svg + conc_table + '<p><small>' + esc(' '.join(notes)) + '</small></p>'
    return {'html': html_out, 'svg': svg, 'rows': listed, 'named': named, 'top': top, 'rest': rest_group, 'anonymous': anon,
            'total_amount': total_amount, 'total_count': total_count, 'concentration': conc}


# ----------------------------------------------------------------------------- section renderer
def render_orders_section(panel_entry, contracts, forecast_entry=None, today=None) -> str:
    """Render the three views for one company. `contracts` may be normalized dicts (contracts_from_panel), raw site rows, or None."""
    stock = panel_entry.get('stock')
    name = panel_entry.get('co') or '회사'
    if stock is not None and (not isinstance(stock, str) or not re.fullmatch(r'[0-9]{6}', stock)):
        raise ValueError('invalid listed stock identifier')
    unlisted = stock is None
    no_forecast_reason = None
    if unlisted:
        if forecast_entry is not None:
            no_forecast_reason = '비상장 계열사 — 상장사 Y+2 추정 대상이 아니므로 전달된 추정 항목을 쓰지 않음'
        else:
            no_forecast_reason = '비상장 계열사 — 상장사 Y+2 추정 대상이 아님'
        forecast_entry = None
    elif forecast_entry is not None:
        if (forecast_entry.get('company_id') != stock or forecast_entry.get('company_name') != name
                or forecast_entry.get('stock', stock) != stock or forecast_entry.get('listed', True) is not True
                or forecast_entry.get('source') != panel_entry.get('src')):
            raise ValueError('company_identity_conflict: panel and forecast must match')
        if forecast_entry.get('money_unit') != 'KRW_million':
            raise ValueError('money_unit must be KRW_million')
    key = stock or ('unlisted-' + re.sub(r'[^0-9A-Za-z]+', '-', str(panel_entry.get('src') or name)).strip('-'))
    uid = 'orders-' + key
    sites = panel_entry.get('sites') or []
    if panel_entry.get('grain') == 'segment':
        return (f'<p class="wrap" id="{uid}" data-orders-status="segment_grain">{esc(name)} — 부문 단위 원장(grain=segment): 현장·계약 단위 행이 없어 '
                f'간트·분기 전환·발주처 뷰를 만들 수 없습니다(부문 행 {len(sites)}개, 발주처·기간 정보 없음).</p>')
    if contracts is None:
        contracts = contracts_from_panel(panel_entry)
    elif _looks_raw(contracts):
        contracts = contracts_from_panel(panel_entry, sites=contracts)
    if not contracts:
        return f'<p class="wrap" id="{uid}" data-orders-status="no_sites">{esc(name)} — 원장에 현장 행이 없어 수주 상세 뷰를 만들 수 없습니다.</p>'
    today = _as_date(today)
    money_ok, money_note = money_unit_verified(panel_entry, forecast_entry)
    counts = status_counts(contracts)
    origin = _origin_of(contracts) or '기준 분기 불명'
    active = [c for c in contracts if c['status'] == 'active']
    colors = category_colors(active, money_ok)
    gantt = build_gantt(contracts, today=today, money_ok=money_ok, uid=uid + '-gantt', colors=colors)
    schedule = build_schedule(contracts, forecast_entry=forecast_entry, money_ok=money_ok, uid=uid + '-schedule', colors=colors,
                              no_forecast_reason=no_forecast_reason)
    clients = build_clients(contracts, money_ok=money_ok, uid=uid + '-clients')
    status = 'ok' if active else 'no_active'
    total_amount = schedule['total_amount']
    chunks = [f'<section class="wrap" id="{uid}" data-orders-status="{status}" data-money="{"verified" if money_ok else "unverified"}" '
              f'data-origin="{esc(origin)}" aria-labelledby="{uid}-heading" style="color:var(--tx);background:var(--pn);border:1px solid var(--ln);padding:1rem">',
              f'<h2 id="{uid}-heading">{esc(name)} 수주 상세 — 간트 · 분기 전환 · 발주처 <span style="color:var(--a);border:1px solid var(--ln);padding:.1em .4em">원장</span></h2>',
              f'<p>기준 {esc(origin)} · II-4 현장 원장(착공·완공예정일·도급액·계약잔액) · 금액 = 기준 분기 계약잔액' + (' · 백만원' if money_ok else ' · <strong>금액 미표시</strong>') + f' · 오늘 {today.isoformat()}. '
              + esc(money_note) + '.</p>',
              f'<p>원장 현장 {counts["total"]}건 → 기준 분기 잔액 보유(활성) <strong>{counts["active"]}건</strong>'
              + (f' · 잔액 합계 <strong>{fmt(total_amount)}</strong>' if money_ok else '')
              + f' (완공예정일 있음 {counts["active_with_end"]} / 없음 {counts["active_no_end"]}'
              + (f'; 소액 현장 묶음 {counts["residual"]}건' + (f'·잔액 {fmt(counts["residual_amount"])}' if money_ok else '') + ' 포함' if counts['residual'] else '')
              + f'); 제외: 잔액 0 {counts["zero"]}건, 기준 분기 미수록 {counts["inactive"]}건, 대표 합산행 {counts["aggregate"]}건, 음수 잔액 {counts["negative"]}건'
              + (f', 보전값이라 금액 미표시 {counts["amount_missing"]}건' if counts['amount_missing'] else '') + '.</p>']
    if unlisted:
        chunks.append('<p><small>' + esc(no_forecast_reason) + ' — 분기 전환 스케줄의 추정치 열은 비어 있습니다.</small></p>')
    if not active:
        chunks.append('<p><strong>기준 분기에 잔액을 보유한 계약이 없어 세 뷰 모두 비어 있습니다.</strong></p>')
    chip = 'display:inline-block;background:var(--bg);border:1px solid var(--ln);border-radius:1rem;padding:.25rem .75rem;color:var(--a)'
    for view_key, label, body in (('gantt', '1 · 수주 간트', gantt['html']), ('schedule', '2 · 분기 전환 스케줄 vs Y+2 추정', schedule['html']),
                                  ('clients', '3 · 발주처별', clients['html'])):
        chunks.append(f'<details data-view="{view_key}" open style="margin:.75rem 0"><summary style="display:list-item;cursor:pointer"><span style="{chip}">{esc(label)}</span></summary>{body}</details>')
    chunks.append('<p><small>가정·한계: 금액은 기준 분기 II-4 계약잔액이며 매출·현금흐름이 아닙니다. 완공예정일은 공시 시점 계획이라 개정될 수 있고 지연 현장은 종료일이 지나도 잔액이 남습니다. '
                  '값이 없는 칸은 근거가 없는 것이지 0이 아닙니다. 발주처·공종 라벨은 회사별 원문 어휘를 그대로 씁니다. 추정치와 계약 합계는 정의가 달라 맞추지 않았습니다. 인라인 SVG만 사용하며 스크립트가 없습니다.</small></p></section>')
    return ''.join(chunks)


# ----------------------------------------------------------------------------- samples
def write_samples(codes=('028050', '000720', '001260', '011370', '112190', 'unlisted:hen'), today=None, panel_path=None, forecasts=None):
    root = Path(__file__).resolve().parents[1]
    panel_path = Path(panel_path) if panel_path else root / 'input/kce_panel.json'
    panel = json.loads(panel_path.read_text(encoding='utf-8'))
    if forecasts is None:
        forecasts = {}
        fp = root / 'output/forecast_panel.json'
        if fp.exists():
            try:
                forecasts = {c['company_id']: c for c in json.loads(fp.read_text(encoding='utf-8')).get('companies', []) if c.get('company_id')}
            except (ValueError, KeyError, TypeError):
                forecasts = {}
    out = root / 'output/samples'
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for code in codes:
        entry = panel.get(code)
        if entry is None:
            continue
        html_text = render_orders_section(entry, contracts_from_panel(entry), forecasts.get(entry.get('stock')), today=today)
        path = out / ('orders_' + re.sub(r'[^0-9A-Za-z]+', '-', code) + '.html')
        path.write_text(html_text + '\n', encoding='utf-8')
        written.append(path)
    return written


if __name__ == '__main__':
    _today = None
    if '--today' in sys.argv and sys.argv.index('--today') + 1 < len(sys.argv):
        _today = _as_date(sys.argv[sys.argv.index('--today') + 1])
    for p in write_samples(today=_today):
        print(p)
