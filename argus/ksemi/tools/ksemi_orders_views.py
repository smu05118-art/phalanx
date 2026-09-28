#!/usr/bin/env python3
"""KSEMI 수주 상세 뷰 3종 — 간트 · 분기 전환 스케줄 · 발주처별.

Inline SVG/CSS only; standard library only; no network, no scripts, no packages.
같은 결의 기존 렌더러: ksemi_forecast_section.render_forecast_section(panel_entry, forecast_entry=None).

Entry
    render_orders_section(panel_entry, contracts, forecast_entry=None,
                          today=None, report_entry=None, standalone=False) -> str
Building blocks (all pure functions over the parsed ledger)
    prepare(contracts, company_id=None)                 -> dict  원장 행 정규화·활성/제외 분류
    build_gantt(items, today, money_ok=True, uid='ko')  -> dict  종료일 있는 계약 = 막대 1개
    build_schedule(items, forecast_rows=None, ...)      -> dict  종료 분기별 묶음 + 추정 나란히
    build_clients(items, today, top_n=8, money_ok=True) -> dict  발주처별 집계·집중도

원칙
  * 원장(단일판매ㆍ공급계약체결 공시 파싱 결과)에 있는 값만 쓴다. 금액은 파서가 백만원으로 정규화한
    amt_mkrw 이며 unit_seen=True 인 행만 금액으로 인정한다. 그 외는 '금액 미확인'으로 건수만 센다.
  * 비어 있는 칸은 비워 두고 사유를 적는다. 추정으로 채우지 않는다.
  * 종료일 없는 계약은 간트·분기 스케줄에서 별도 묶음으로 뺀다.
  * 익명 상대는 한 줄로 모으고 실명 순위와 섞지 않는다.
"""
import argparse
import datetime as _dt
import hashlib
import html
import json
import math
import re
from collections import Counter
from pathlib import Path

Q_FROM, Q_TO = '2026Q3', '2028Q4'
TOP_N = 8
ANON_KEY = '__anon__'
GENERIC = '반도체 장비(단계 미상)'
NONE = '원문 낱말 없음'


# ----------------------------------------------------------------------------- basics
def esc(x):
    return html.escape('' if x is None else str(x), quote=True)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def fmt(v):
    return f'{v:,.3f}' if number(v) else '—'


def pct(v):
    return f'{v*100:,.2f}%' if number(v) else '—'


DATE_RE = re.compile(r'^\s*(\d{4})[-./](\d{1,2})[-./](\d{1,2})\s*$')


def parse_date(s):
    """'YYYY-MM-DD' -> date; anything else -> None (never guessed)."""
    if isinstance(s, _dt.datetime):
        return s.date()
    if isinstance(s, _dt.date):
        return s
    if not isinstance(s, str):
        return None
    m = DATE_RE.match(s)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def quarter_of(d):
    return f'{d.year}Q{(d.month - 1) // 3 + 1}'


def quarter_span(q_from, q_to):
    """['2026Q3', ..., '2028Q4'] inclusive; string order works because the width is fixed."""
    y, q = int(q_from[:4]), int(q_from[-1])
    out = []
    while len(out) < 400:
        cur = f'{y}Q{q}'
        out.append(cur)
        if cur >= q_to:
            break
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def clip(text, max_em=26.0):
    """Cut a label by estimated width (CJK = 1em, Latin = 0.55em) so SVG labels stay in their column."""
    out, width = [], 0.0
    for ch in str(text):
        w = 1.0 if ord(ch) > 0x2E7F else 0.55
        if width + w > max_em:
            return ''.join(out).rstrip() + '…'
        out.append(ch)
        width += w
    return ''.join(out)


# ----------------------------------------------------------------------------- counterparty
LEGAL_KO = re.compile(r'(주식회사|\(주\)|㈜|\(株\)|유한회사)')
LEGAL_LATIN = re.compile(r'\b(co|corp|corporation|inc|ltd|limited|llc|gmbh|pte|sdn|bhd|plc|company)\b\.?', re.I)
STRIP = re.compile(r'[\s\.,、·ㆍ\-_/\'’"“”]+')
# 표기 변형만 묶는다(음역·법인 표시). 자회사·현지법인은 별도 상대로 남긴다(중국 노출 축이 거기 걸려 있다).
PARTY_ALIASES = [
    (re.compile(r'^(sk|에스케이)하이닉스(\(skhynix\))?$|^skhynix$'), 'sk하이닉스'),
    (re.compile(r'^skhynixsemiconductor\(china\)(\(skhycl\))?$'), 'skhynixsemiconductor(china)'),
    (re.compile(r'^삼성전자(\(samsungelectronics\))?$|^samsungelectronics$'), '삼성전자'),
    (re.compile(r'^samsung\(china\)semiconductor(\(scs\))?$'), 'samsung(china)semiconductor'),
    (re.compile(r'^(lg|엘지)디스플레이$|^lgdisplay$'), 'lg디스플레이'),
    (re.compile(r'^(lg|엘지)에너지솔루션$'), 'lg에너지솔루션'),
]


def party_key(raw):
    s = LEGAL_KO.sub(' ', raw or '')
    s = LEGAL_LATIN.sub(' ', s)
    s = s.replace('[', '(').replace(']', ')').replace('（', '(').replace('）', ')')
    s = STRIP.sub('', s).lower()
    s = re.sub(r'\(\s*\)', '', s)          # 법인 표시를 지워 빈 괄호가 된 것
    # 법인 표시가 괄호 안에 있으면('(SK Hynix Inc.)') 닫는 괄호만 남아 짝이 깨진다.
    # 짝을 맞춘 뒤, **전체를 감싼** 괄호일 때만 벗긴다 — '(china)' 같은 의미 있는 괄호를 지우면
    # 별칭 대조가 통째로 어긋난다(자체 검증 3건이 여기서 실패했다).
    op, cl = s.count('('), s.count(')')
    if op > cl:
        s += ')' * (op - cl)
    elif cl > op:
        s = '(' * (cl - op) + s
    while len(s) > 1 and s[0] == '(' and s[-1] == ')':
        depth = 0
        for i, ch in enumerate(s):
            depth += (ch == '(') - (ch == ')')
            if depth == 0 and i < len(s) - 1:
                break
        else:
            s = s[1:-1]
            continue
        break
    for pattern, canon in PARTY_ALIASES:
        if pattern.match(s):
            return canon
    return s


ANON_LITERALS = {'', '-', '비공개', '공시유보', '미공개', '유보', '비공개(공시유보)'}
ANON_SUFFIX = re.compile(r'(업체|기업|제조사|제조회사|유통회사|제조업|장비사|공급기업|고객사)\s*(\([^)]*\))?\s*$')
LEGAL_ANY = re.compile(r'(주식회사|\(주\)|㈜|유한회사|\b(co|corp|inc|ltd|llc|gmbh|pte|plc)\b)', re.I)


def is_anonymous(row):
    """parser flag first; then literal placeholders; then descriptive labels like '국내 IT기업' (no legal form)."""
    if row.get('party_anon'):
        return True
    p = str(row.get('party') or '').strip()
    if p in ANON_LITERALS:
        return True
    if LEGAL_ANY.search(p):
        return False
    return bool(ANON_SUFFIX.search(p))


# ----------------------------------------------------------------------------- process stage (colour axis)
STAGES = ['포토', '식각', '증착', '이온주입', '열처리/RTP', 'CMP', '세정', '테스트', '패키징/후공정',
          '계측/검사', '이송/진공', '부품소재', '부품세정·재생']
# 임시 배정표. 정본은 ksemi_universe.EQUIP_WORDS + stages.json 인데 이번 입력에 없다.
# 계약 공시 본문에서 파서가 잡은 content_words 만 본다(본문을 새로 해석하지 않는다). 앞 단계가 우선.
STAGE_WORDS = {
    '포토': {'포토', '트랙', '코터', '코팅', '노광', '스테퍼', '스캐너'},
    '식각': {'식각', '에칭', 'etch', 'etcher'},
    '증착': {'증착', 'cvd', 'ald', 'pvd', '스퍼터', 'sputter'},
    '이온주입': {'이온주입', '임플란트', 'implant'},
    '열처리/RTP': {'열처리', 'rtp', '산화', '확산', '퍼니스', 'furnace', '어닐'},
    'CMP': {'cmp', '연마'},
    '세정': {'세정', 'cleaner', '클리너', 'cleaning'},
    '테스트': {'테스트', '테스터', 'burn-in', '번인', '소켓', 'probe', '프로브', '프로브카드', '핸들러', 'handler'},
    '패키징/후공정': {'후공정', 'tc bonder', '본더', 'bonder', '패키지', '패키징', '다이싱', '몰딩'},
    '계측/검사': {'검사', '계측', 'inspection', '현미경', 'defect', '계측기'},
    '이송/진공': {'이송', '반송', '진공', 'foup', '로봇', 'efem'},
    '부품소재': {'펌프', '밸브', '챔버', '세라믹', 'rf', '전극', '링', '가스', '쿼츠', '히터', '정전척', '샤워헤드'},
    '부품세정·재생': {'재생', '부품세정'},
}
GENERIC_WORDS = {'반도체 제조 장비', '반도체 제조용', '반도체제조용', '반도체 장비', '반도체장비', 'wafer', '웨이퍼', '전공정'}
NOT_WORDS = {'트랙': ('트랙터',), '마스크': ('마스크팩',), '링': ('링크', '필링', '링거')}
_SLOTS = ['#2563eb', '#d97706', '#7c3aed', '#059669', '#dc2626', '#0891b2', '#ca8a04', '#db2777']
STAGE_COLORS = {s: _SLOTS[i % len(_SLOTS)] for i, s in enumerate(STAGES)}
STAGE_COLORS[GENERIC] = '#64748b'
STAGE_COLORS[NONE] = '#94a3b8'


def stage_of(row):
    words = [str(w).strip().lower() for w in (row.get('content_words') or []) if str(w).strip()]
    content = str(row.get('content') or '').lower()
    hits = {}
    for stage, vocab in STAGE_WORDS.items():
        for w in words:
            if w in vocab and not any(nw in content for nw in NOT_WORDS.get(w, ())):
                hits.setdefault(stage, []).append(w)
    if hits:
        stage = next(iter(hits))
        return stage, hits[stage]
    generic = [w for w in words if w in GENERIC_WORDS]
    if generic:
        return GENERIC, generic
    return NONE, words


def stage_color(stage):
    return STAGE_COLORS.get(stage, '#94a3b8')


# ----------------------------------------------------------------------------- ledger -> items
def make_item(r):
    start, end, signed = parse_date(r.get('start')), parse_date(r.get('end')), parse_date(r.get('signed'))
    amt, unit_seen = r.get('amt_mkrw'), bool(r.get('unit_seen'))
    if number(amt) and unit_seen:
        amount, amount_reason = float(amt), None
    elif number(amt):
        amount, amount_reason = None, '금액 단위 미확인(unit_seen=false)'
    else:
        amount, amount_reason = None, str(r.get('amt_note') or '계약금액 칸을 원문에서 못 읽음')
    anon = is_anonymous(r)
    party = str(r.get('party') or '').strip()
    party_raw = str(r.get('party_raw') or '').strip()
    if anon:
        key = ANON_KEY
        label = party or party_raw or '(상대 미기재)'
    else:
        key = party_key(party)
        label = party
    raw_end = str(r.get('end') or '').strip()
    if end is None:
        end_reason = '종료일 칸 비어 있음' if not raw_end else '종료일 형식 미확인: ' + raw_end
    else:
        end_reason = None
    start_note = None
    raw_start = str(r.get('start') or '').strip()
    if start is None:
        start_note = '시작일 칸 비어 있음' if not raw_start else '시작일 형식 미확인: ' + raw_start
    elif end is not None and start > end:
        start_note = '시작일이 종료일보다 늦음(원문 확인 필요)'
    stage, words = stage_of(r)
    amendments = r.get('amendments') or []
    return {
        'rcp': str(r.get('rcp') or ''), 'stock': str(r.get('stock') or ''), 'company': str(r.get('name') or ''),
        'filed': str(r.get('filed') or ''), 'event': str(r.get('event') or ''),
        'content': str(r.get('content') or '').strip() or '(계약내용 미기재)',
        'party_label': label, 'party_key': key, 'party_raw': party_raw, 'anon': anon,
        'start': start, 'end': end, 'signed': signed, 'start_note': start_note, 'end_reason': end_reason,
        'amount': amount, 'amount_reason': amount_reason,
        'stage': stage, 'stage_words': words,
        'region': str(r.get('region') or '').strip(), 'region_cn': bool(r.get('region_cn')),
        'corrected': bool(r.get('corrected')), 'amend_reason': str(r.get('amend_reason') or ''),
        'amendments': amendments, 'withheld': str(r.get('withheld') or ''),
    }


def prepare(contracts, company_id=None):
    """Normalise the ledger (dict with 'rows' or list) for one company; split active / excluded rows."""
    rows = contracts.get('rows') if isinstance(contracts, dict) else contracts
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    if company_id is not None:
        cid = str(company_id)
        rows = [r for r in rows if r.get('stock') is None or str(r.get('stock')) == cid]
    superseded = set()
    for r in rows:
        for s in (r.get('supersedes') or []):
            superseded.add(str(s))
    seen, active, excluded = set(), [], []
    for r in rows:
        item = make_item(r)
        rcp = item['rcp']
        if rcp and rcp in seen:
            excluded.append((item, '같은 접수번호 중복 행'))
            continue
        if rcp:
            seen.add(rcp)
        if rcp and rcp in superseded:
            excluded.append((item, '뒤 정정공시가 대체함(supersedes)'))
            continue
        ev = item['event'].strip()
        if ev and ev != '체결':
            excluded.append((item, ev + ' 공시 — 원 계약 행과 잇는 키가 원문에 없어 원 계약 행은 그대로 둠'))
            continue
        active.append(item)
    names = Counter(str(r.get('name')) for r in rows if r.get('name'))
    return {'rows': rows, 'active': active, 'excluded': excluded,
            'company_name': names.most_common(1)[0][0] if names else None}


# ----------------------------------------------------------------------------- 1. Gantt
def build_gantt(items, today, money_ok=True, uid='ko'):
    bars = sorted([i for i in items if i['end'] is not None],
                  key=lambda i: (i['end'], i['start'] or i['end'], i['rcp']))
    unscheduled = [i for i in items if i['end'] is None]
    stages = []
    for b in bars:
        if b['stage'] not in stages:
            stages.append(b['stage'])
    svg = gantt_svg(bars, today, money_ok, uid) if bars else ''
    return {'bars': bars, 'unscheduled': unscheduled, 'svg': svg, 'stages': stages}


def bar_tip(b):
    span = (b['start'].isoformat() if b['start'] else '시작일 없음') + ' ~ ' + (b['end'].isoformat() if b['end'] else '종료일 없음')
    money = fmt(b['amount']) + ' 백만원' if b['amount'] is not None else '금액 미확인: ' + str(b['amount_reason'])
    parts = [b['party_label'] + (' [익명]' if b['anon'] else ''), b['content'], span, money,
             '단계 ' + b['stage'] + (' (' + ', '.join(b['stage_words']) + ')' if b['stage_words'] else ''),
             '지역 ' + (b['region'] or '미기재') + (' · 중국향' if b['region_cn'] else ''), '접수번호 ' + b['rcp']]
    if b['start_note']:
        parts.append(b['start_note'])
    if b['corrected']:
        parts.append('정정: ' + (b['amend_reason'] or '사유 미기재'))
    return ' · '.join(parts)


def gantt_svg(bars, today, money_ok, uid):
    W, LX, X0, X1, TOP, RH, BOTTOM = 1000, 292, 302, 930, 46, 24, 28
    H = TOP + RH * len(bars) + BOTTOM
    dates = [today] + [b['end'] for b in bars] + [b['start'] for b in bars if b['start'] is not None and b['start'] <= b['end']]
    dmin, dmax = min(dates), max(dates)
    pad = max(20, int((dmax - dmin).days * 0.03))
    dmin, dmax = dmin - _dt.timedelta(days=pad), dmax + _dt.timedelta(days=pad)
    span = max(1, (dmax - dmin).days)

    def x(d):
        return X0 + (d - dmin).days / span * (X1 - X0)

    amax = max([b['amount'] for b in bars if b['amount'] is not None] or [0.0])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{uid}-gt {uid}-gd">',
           f'<title id="{uid}-gt">수주 간트 — 계약별 시작~종료</title>',
           f'<desc id="{uid}-gd">막대 {len(bars)}개. 종료일 오름차순. 색은 공정단계(원문 낱말 근거), 두께는 계약금액(백만원, 제곱근 비례), '
           '점선 테두리는 금액 미확인, 마름모는 시작일 없이 종료일만 있는 계약. 세로 점선은 기준일. 흐린 막대는 기준일 이전에 끝난 계약.</desc>']
    for y in range(dmin.year, dmax.year + 2):
        d = _dt.date(y, 1, 1)
        if dmin <= d <= dmax:
            xx = x(d)
            out.append(f'<line x1="{xx:.1f}" y1="{TOP - 14}" x2="{xx:.1f}" y2="{H - BOTTOM + 4}" stroke="currentColor" stroke-opacity=".18"/>')
            out.append(f'<text x="{xx + 3:.1f}" y="{TOP - 18}">{y}</text>')
    out.append(f'<line x1="{X0}" y1="{TOP - 12}" x2="{X1}" y2="{TOP - 12}" stroke="currentColor" stroke-opacity=".5"/>')
    for k, b in enumerate(bars):
        yc = TOP + RH * k + RH / 2
        color = stage_color(b['stage'])
        ended = b['end'] < today
        label = clip(b['party_label'] + ' · ' + b['content'], 25)
        out.append(f'<g class="ko-bar" opacity="{"0.45" if ended else "1"}"><title>{esc(bar_tip(b))}</title>')
        out.append(f'<text x="{LX}" y="{yc + 4:.1f}" text-anchor="end">{esc(label)}</text>')
        xe = x(b['end'])
        has_start = b['start'] is not None and b['start'] <= b['end']
        xs = x(b['start']) if has_start else xe
        if has_start:
            width = max(2.0, xe - xs)
            if b['amount'] is not None and money_ok and amax > 0:
                h = 6 + 14 * math.sqrt(max(0.0, b['amount'] / amax))
                out.append(f'<rect x="{xs:.1f}" y="{yc - h / 2:.1f}" width="{width:.1f}" height="{h:.1f}" rx="2" fill="{color}"/>')
            else:
                out.append(f'<rect x="{xs:.1f}" y="{yc - 5:.1f}" width="{width:.1f}" height="10" rx="2" fill="none" stroke="{color}" stroke-dasharray="4 3"/>')
        else:
            out.append(f'<path d="M{xe:.1f},{yc - 7:.1f} l7,7 l-7,7 l-7,-7 z" fill="{color}"/>')
        if money_ok:
            text = fmt(b['amount']) if b['amount'] is not None else '금액 미확인'
            est = len(text) * 6.5
            if xe + 8 + est <= X1 + 62:
                out.append(f'<text x="{xe + 6:.1f}" y="{yc + 4:.1f}">{esc(text)}</text>')
            else:
                out.append(f'<text x="{xs - 6:.1f}" y="{yc + 4:.1f}" text-anchor="end">{esc(text)}</text>')
        out.append('</g>')
    xt = x(today)
    out.append(f'<line x1="{xt:.1f}" y1="{TOP - 14}" x2="{xt:.1f}" y2="{H - BOTTOM + 4}" style="stroke:var(--a,#dc2626)" stroke-width="1.5" stroke-dasharray="5 3"/>')
    out.append(f'<text x="{xt + 4:.1f}" y="{H - 8}" style="fill:var(--a,#dc2626)">기준일 {today.isoformat()}</text>')
    out.append('</svg>')
    return ''.join(out)


# ----------------------------------------------------------------------------- 2. quarterly schedule
def forecast_rows_of(entry):
    """(rows, reason) from a forecast/panel entry; rows only when the base scenario exists."""
    if not entry:
        return [], '추정 패널 미제공(forecast_entry=None)'
    if not entry.get('scenarios'):
        return [], '추정 패널에 시나리오가 없음(이 회사 추정 미제공)'
    rows = ((entry.get('scenarios') or {}).get('base') or {}).get('quarterly') or []
    if not rows:
        return [], '기준 시나리오 분기 행 없음(status=' + str(entry.get('status') or '미확인') + ')'
    if not entry.get('money_unit'):
        return rows, '추정 금액 단위 미확정(money_unit 없음) — 추정 금액 비표시'
    return rows, None


def _bucket():
    return {'n': 0, 'amount': 0.0, 'unknown': 0, 'items': []}


def build_schedule(items, forecast_rows=None, q_from=Q_FROM, q_to=Q_TO, money_ok=True, forecast_ok=True):
    quarters = quarter_span(q_from, q_to)
    fmap = {}
    for r in (forecast_rows or []):
        q = str(r.get('quarter') or '').strip()
        if q:
            fmap[q] = r
    buckets = {q: _bucket() for q in quarters}
    before, after, no_end = _bucket(), _bucket(), []
    for i in items:
        if i['end'] is None:
            no_end.append(i)
            continue
        q = quarter_of(i['end'])
        b = buckets.get(q)
        if b is None:
            b = before if q < q_from else after
        b['n'] += 1
        b['items'].append(i)
        if i['amount'] is None:
            b['unknown'] += 1
        else:
            b['amount'] += i['amount']
    rows = []
    for q in quarters:
        b, f = buckets[q], (fmap.get(q) or {})
        fv = f.get('value') if forecast_ok else None
        fb = f.get('existing_backlog_revenue') if forecast_ok else None
        fp = f.get('covered_sites_partial_revenue') if forecast_ok else None
        amount = b['amount'] if money_ok else None
        rows.append({'quarter': q, 'n': b['n'], 'unknown': b['unknown'], 'amount': amount,
                     'forecast_present': bool(f),
                     'forecast_value': fv if number(fv) else None,
                     'forecast_backlog': fb if number(fb) else None,
                     'forecast_partial': fp if number(fp) else None,
                     'diff': (amount - fv) if (amount is not None and number(fv)) else None})
    compared = [r for r in rows if r['diff'] is not None]
    summary = {
        'contract_n_in_range': sum(b['n'] for b in buckets.values()),
        'contract_unknown_in_range': sum(b['unknown'] for b in buckets.values()),
        'contract_amount_in_range': sum(b['amount'] for b in buckets.values()),
        'n_compared': len(compared),
        'contract_sum_compared': sum(r['amount'] for r in compared),
        'forecast_sum_compared': sum(r['forecast_value'] for r in compared),
    }
    summary['diff'] = summary['contract_sum_compared'] - summary['forecast_sum_compared'] if compared else None
    return {'quarters': quarters, 'rows': rows, 'buckets': buckets, 'before': before, 'after': after,
            'no_end': no_end, 'summary': summary, 'q_from': q_from, 'q_to': q_to}


def schedule_svg(sched, uid, money_ok, has_forecast):
    rows = sched['rows']
    W, H, X0, X1, BASE, PLOT = 840, 250, 75, 815, 190, 140
    if money_ok:
        vals = [r['amount'] for r in rows] + [r['forecast_value'] for r in rows if r['forecast_value'] is not None]
    else:
        vals = [float(r['n']) for r in rows]
    ymax = max([1e-9] + [v for v in vals if number(v)])
    step = (X1 - X0) / max(1, len(rows))
    w = min(30.0, step * 0.34)
    unit = '백만원' if money_ok else '건'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{uid}-st {uid}-sd">',
           f'<title id="{uid}-st">분기 전환 스케줄 — 종료 분기별 계약 합계와 기준 추정</title>',
           f'<desc id="{uid}-sd">파랑은 그 분기에 끝나는 공시 계약의 총액 합계({unit}), 주황 테두리는 기존 페이지의 기준 시나리오 추정 전체. 숫자는 건수. 둘은 정의가 달라 같을 이유가 없고 조정하지 않았다.</desc>',
           f'<line x1="{X0}" y1="{BASE}" x2="{X1}" y2="{BASE}" stroke="currentColor"/>',
           f'<text x="{X0 - 5}" y="32" text-anchor="end">{esc(fmt(ymax) if money_ok else str(int(ymax)))}</text>',
           f'<text x="{X0 - 10}" y="{BASE + 2}" text-anchor="end">0</text>']
    for i, r in enumerate(rows):
        cx = X0 + step * (i + 0.5)
        v = r['amount'] if money_ok else float(r['n'])
        tip = f"{r['quarter']}: 종료 계약 {r['n']}건" + (f", 금액 미확인 {r['unknown']}건" if r['unknown'] else '')
        if money_ok:
            tip += f", 합계 {fmt(r['amount'])} 백만원"
        if r['forecast_value'] is not None:
            tip += f"; 기준 추정 전체 {fmt(r['forecast_value'])}"
        out.append(f'<g><title>{esc(tip)}</title>')
        if number(v) and v > 0:
            h = v / ymax * PLOT
            bx = cx - w - 1 if has_forecast else cx - w / 2
            out.append(f'<rect x="{bx:.1f}" y="{BASE - h:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#2563eb"/>')
        if has_forecast and r['forecast_value'] is not None and money_ok:
            h = r['forecast_value'] / ymax * PLOT
            out.append(f'<rect x="{cx + 1:.1f}" y="{BASE - h:.1f}" width="{w:.1f}" height="{max(0.0, h):.1f}" fill="none" stroke="#d97706" stroke-width="1.5"/>')
        elif has_forecast and money_ok:
            out.append(f'<text x="{cx + 1 + w / 2:.1f}" y="{BASE - 6}" text-anchor="middle">—</text>')
        count = f"{r['n']}건" + (f"+{r['unknown']}미확인" if r['unknown'] else '')
        top_y = BASE - (v / ymax * PLOT if number(v) else 0) - 6
        out.append(f'<text x="{cx:.1f}" y="{max(44.0, top_y):.1f}" text-anchor="middle">{esc(count)}</text>')
        out.append(f'<text x="{cx:.1f}" y="{BASE + 18}" text-anchor="middle">{esc(r["quarter"])}</text></g>')
    out.append('</svg>')
    return ''.join(out)


# ----------------------------------------------------------------------------- 3. clients
def _group(key, anon):
    return {'key': key, 'anon': anon, 'labels': Counter(), 'n': 0, 'amount': 0.0, 'unknown': 0,
            'open_n': 0, 'open_amount': 0.0, 'open_unknown': 0, 'noend_n': 0, 'ended_n': 0,
            'max_end': None, 'cn_n': 0, 'rcps': []}


def _add(g, i, today):
    g['labels'][i['party_label']] += 1
    g['n'] += 1
    g['rcps'].append(i['rcp'])
    if i['amount'] is None:
        g['unknown'] += 1
    else:
        g['amount'] += i['amount']
    if i['region_cn']:
        g['cn_n'] += 1
    if i['end'] is None:
        g['noend_n'] += 1
    elif i['end'] >= today:
        g['open_n'] += 1
        if i['amount'] is None:
            g['open_unknown'] += 1
        else:
            g['open_amount'] += i['amount']
    else:
        g['ended_n'] += 1
    if i['end'] is not None and (g['max_end'] is None or i['end'] > g['max_end']):
        g['max_end'] = i['end']


def _pick_label(labels):
    return sorted(labels.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]


def build_clients(items, today, top_n=TOP_N, money_ok=True):
    groups = {}
    for i in items:
        k = ANON_KEY if i['anon'] else i['party_key']
        if k not in groups:
            groups[k] = _group(k, i['anon'])
        _add(groups[k], i, today)
    total = _group('__total__', False)
    for i in items:
        _add(total, i, today)
    total['label'] = '합계'
    total['variants'] = []
    total['share_all'] = 1.0 if (money_ok and total['amount'] > 0) else None
    total['share_open'] = 1.0 if (money_ok and total['open_amount'] > 0) else None
    for g in groups.values():
        g['label'] = _pick_label(g['labels']) if not g['anon'] else '익명·비공개 상대'
        g['variants'] = sorted(g['labels'])
        g['share_all'] = g['amount'] / total['amount'] if (money_ok and total['amount'] > 0) else None
        g['share_open'] = g['open_amount'] / total['open_amount'] if (money_ok and total['open_amount'] > 0) else None
    named = sorted((g for g in groups.values() if not g['anon']),
                   key=lambda g: (-(g['amount'] if money_ok else 0.0), -g['n'], g['label']))
    top, rest = named[:top_n], named[top_n:]
    rest_row = None
    if rest:
        rest_row = _group('__rest__', False)
        rest_keys = {g['key'] for g in rest}
        for i in items:
            if (not i['anon']) and i['party_key'] in rest_keys:
                _add(rest_row, i, today)
        rest_row['label'] = f'그 외 {len(rest)}개 발주처'
        rest_row['variants'] = [g['label'] for g in rest]
        rest_row['share_all'] = rest_row['amount'] / total['amount'] if (money_ok and total['amount'] > 0) else None
        rest_row['share_open'] = rest_row['open_amount'] / total['open_amount'] if (money_ok and total['open_amount'] > 0) else None
    anon = groups.get(ANON_KEY)
    top3 = [g['share_open'] for g in top[:3]]
    conc = {
        'top1_label': top[0]['label'] if top else None,
        'top1_open': top[0]['share_open'] if top else None,
        'top1_all': top[0]['share_all'] if top else None,
        'top3_open': sum(top3) if top3 and all(number(s) for s in top3) else None,
        'named_count': len(named),
        'anon_n': anon['n'] if anon else 0,
        'anon_open_share': anon['share_open'] if anon else None,
        'open_amount': total['open_amount'], 'open_n': total['open_n'], 'open_unknown': total['open_unknown'],
        'noend_n': total['noend_n'],
    }
    return {'groups': groups, 'named': named, 'top': top, 'rest': rest, 'rest_row': rest_row,
            'anon': anon, 'total': total, 'concentration': conc}


# ----------------------------------------------------------------------------- HTML
CSS = '''<style>
.ko-panel{color:var(--tx,#172033);background:var(--bg,#fff);font:14px/1.65 system-ui,sans-serif;max-width:1200px;margin:24px auto;padding:24px;border:1px solid var(--ln,#94a3b8);border-radius:16px}
.ko-panel h2{margin:0;font-size:24px}.ko-panel h3{font-size:18px;margin:24px 0 8px}.ko-panel h4{font-size:15px;margin:16px 0 6px}.ko-panel p{margin:10px 0}
.ko-panel .ko-note{padding:12px;border-left:4px solid var(--a,#d97706);background:var(--pn,#fffbeb)}
.ko-panel .ko-muted{color:var(--muted,#64748b)}
.ko-panel .ko-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.ko-panel .ko-card{border:1px solid var(--ln,#94a3b8);border-radius:9px;padding:12px;background:var(--pn,transparent)}
.ko-panel .wrap{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
.ko-panel table{border-collapse:collapse;min-width:640px;width:100%;margin:12px 0}
.ko-panel caption{text-align:left;font-weight:600}
.ko-panel th,.ko-panel td{border-bottom:1px solid var(--ln,#cbd5e1);padding:6px 7px;text-align:right;white-space:nowrap}
.ko-panel td:first-child,.ko-panel th:first-child{text-align:left}
.ko-panel tr.ko-sum td{font-weight:600;border-top:2px solid var(--ln,#94a3b8)}
.ko-panel tr.ko-anon td{font-style:italic}
.ko-panel summary{cursor:pointer;font-weight:600;padding:9px}
.ko-panel svg{width:100%;height:auto;min-width:720px;display:block}.ko-panel svg text{fill:currentColor;font-size:11px}
.ko-panel .ko-chip{display:inline-block;padding:2px 8px;border:1px solid var(--ln,#94a3b8);border-radius:12px;margin:3px}
.ko-panel .ko-sw{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.ko-panel.ko-standalone{--tx:#172033;--bg:#fff;--pn:#fffbeb;--ln:#94a3b8;--a:#d97706;--muted:#64748b}
@media(prefers-color-scheme:dark){.ko-panel.ko-standalone{--tx:#e2e8f0;--bg:#111827;--pn:#292524;--ln:#475569;--a:#f59e0b;--muted:#94a3b8}}
@media(max-width:600px){.ko-panel{margin:8px;padding:12px}.ko-panel h2{font-size:21px}}
</style>'''


def table(headers, rows, caption, row_classes=None):
    row_classes = list(row_classes or [])
    body = []
    for k, row in enumerate(rows):
        cls = row_classes[k] if k < len(row_classes) else ''
        body.append('<tr' + (f' class="{esc(cls)}"' if cls else '') + '>' +
                    ''.join('<td>' + esc(x) + '</td>' for x in row) + '</tr>')
    return ('<div class="wrap"><table><caption>' + esc(caption) + '</caption><thead><tr>' +
            ''.join('<th scope="col">' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' +
            ''.join(body) + '</tbody></table></div>')


def _d(d):
    return d.isoformat() if d else ''


def _money(v, money_ok):
    return fmt(v) if (money_ok and v is not None) else '—'


def _gantt_rows(bars, money_ok):
    rows, classes = [], []
    for b in bars:
        rows.append([
            b['party_label'] + (' [익명]' if b['anon'] else ''), b['content'],
            b['stage'] + (' (' + ', '.join(b['stage_words']) + ')' if b['stage_words'] else ''),
            _d(b['start']) or (b['start_note'] or ''), _d(b['end']),
            _money(b['amount'], money_ok) if b['amount'] is not None else ('미확인: ' + str(b['amount_reason']) if money_ok else '—'),
            (b['region'] or '미기재') + (' · 中' if b['region_cn'] else ''),
            b['rcp'] + (' 정정' if b['corrected'] else ''),
        ])
        classes.append('ko-anon' if b['anon'] else '')
    return rows, classes


def render_orders_section(panel_entry, contracts, forecast_entry=None, today=None, report_entry=None,
                          standalone=False, top_n=TOP_N, q_from=Q_FROM, q_to=Q_TO):
    panel_entry = panel_entry or {}
    today = parse_date(today) if today is not None else _dt.date.today()
    if today is None:
        raise ValueError('today must be a date or YYYY-MM-DD')
    cid = panel_entry.get('company_id')
    prep = prepare(contracts, company_id=cid)
    items, excluded = prep['active'], prep['excluded']
    name = panel_entry.get('company_name') or prep['company_name'] or (str(cid) if cid is not None else '회사')
    uid = 'ko-' + hashlib.sha256((str(cid) + '|' + str(panel_entry.get('origin')) + '|' + today.isoformat()).encode()).hexdigest()[:12]
    money_ok = any(i['amount'] is not None for i in items)
    n_unknown = sum(1 for i in items if i['amount'] is None)
    fentry = forecast_entry if forecast_entry is not None else panel_entry
    frows, freason = forecast_rows_of(fentry)
    forecast_ok = bool(frows) and freason is None
    gantt = build_gantt(items, today, money_ok, uid)
    sched = build_schedule(items, frows, q_from, q_to, money_ok, forecast_ok)
    clients = build_clients(items, today, top_n, money_ok)

    P = [CSS, f'<section class="ko-panel{" ko-standalone" if standalone else ""}" id="{uid}" aria-labelledby="{uid}-h">',
         f'<h2 id="{uid}-h">{esc(name)} · 수주 상세 — 간트 · 분기 전환 · 발주처</h2>',
         '<p><span class="ko-chip">기준일 ' + esc(today.isoformat()) + '</span>'
         f'<span class="ko-chip">원장 {len(prep["rows"])}행 · 활성 {len(items)}건 · 제외 {len(excluded)}건</span>'
         + ('<span class="ko-chip">금액 백만원(KRW) · 계약별 단위 확인분만</span>' if money_ok else '<span class="ko-chip">금액 단위 확인된 계약 없음 → 건수·기간만</span>')
         + (f'<span class="ko-chip">금액 미확인 {n_unknown}건</span>' if n_unknown else '') + '</p>',
         '<p class="ko-note">「단일판매ㆍ공급계약체결」 공시 원장만 씁니다. 정기보고서 II-4 수주잔고와는 범위·시점이 달라 대조하지 않습니다. '
         '계약금액은 공시 총액이며 기납품분을 빼지 않았습니다. 상대 실명은 공시 표기 그대로이고 익명은 실명으로 추정하지 않습니다. '
         '값이 없는 칸은 비워 두고 사유를 적었습니다.</p>']
    if not items:
        P.append('<p class="ko-note">이 회사의 활성 공시 계약이 없습니다' + (f' (제외 {len(excluded)}건)' if excluded else '') + '. 세 뷰를 그리지 않습니다.</p>')

    # ---- 1. Gantt
    P.append('<h3>1. 수주 간트 — 계약별 시작~종료</h3>')
    if gantt['bars']:
        P.append('<p class="ko-muted">종료일 오름차순 · 색 = 공정단계(계약 본문 낱말) · 두께 = 계약금액(제곱근 비례) · 점선 = 금액 미확인 · 마름모 = 시작일 없음 · 흐림 = 기준일 이전 종료</p>')
        P.append('<p>' + ''.join(f'<span class="ko-chip"><span class="ko-sw" style="background:{stage_color(s)}"></span>{esc(s)}</span>' for s in gantt['stages']) + '</p>')
        P.append('<div class="wrap">' + gantt['svg'] + '</div>')
        rows, classes = _gantt_rows(gantt['bars'], money_ok)
        P.append(table(['상대', '계약내용', '단계(낱말)', '시작', '종료', '금액(백만원)', '지역', '접수번호'], rows,
                       f'막대 {len(gantt["bars"])}개 = 종료일 있는 활성 계약 수', classes))
    else:
        P.append('<p class="ko-muted">종료일 있는 활성 계약이 없어 간트를 그리지 않습니다.</p>')
    if gantt['unscheduled']:
        rows = [[b['party_label'] + (' [익명]' if b['anon'] else ''), b['content'], _d(b['start']) or (b['start_note'] or ''),
                 _money(b['amount'], money_ok) if b['amount'] is not None else ('미확인' if money_ok else '—'),
                 b['end_reason'] or '', b['rcp']] for b in gantt['unscheduled']]
        P.append('<h4>별도 묶음 — 종료일 없는 계약 ' + str(len(gantt['unscheduled'])) + '건</h4>')
        P.append('<p class="ko-muted">종료일 칸이 비어 있거나 형식을 못 읽은 계약입니다. 간트 막대와 분기 스케줄에서 뺐고, 발주처 집계에는 건수·금액만 들어갑니다(미종료 여부 판정 불가).</p>')
        P.append(table(['상대', '계약내용', '시작', '금액(백만원)', '사유', '접수번호'], rows, '종료일 없음 — 기간 추정하지 않음',
                       ['ko-anon' if b['anon'] else '' for b in gantt['unscheduled']]))
    P.append('<p class="ko-muted">공정단계 배정은 계약 공시 본문에서 파서가 잡은 낱말(content_words)만 씁니다. 정본 단계 사전(stages.json)은 이번 입력에 없어 모듈 안 임시 배정표를 썼고, 낱말이 없으면 「원문 낱말 없음」입니다.</p>')

    # ---- 2. schedule
    P.append(f'<h3>2. 분기 전환 스케줄 — 종료 분기별 {esc(q_from)}~{esc(q_to)}</h3>')
    has_forecast = forecast_ok and any(r['forecast_value'] is not None for r in sched['rows'])
    if items:
        P.append('<div class="wrap">' + schedule_svg(sched, uid, money_ok, has_forecast) + '</div>')
        P.append('<p class="ko-muted">파랑: 그 분기에 끝나는 활성 계약 총액 합계' + ('' if money_ok else '(금액 없음 → 건수)') + ' · 주황 테두리: 기존 페이지 기준 시나리오 추정 전체(있을 때) · 라벨: 종료 건수</p>')
    srows = []
    for r in sched['rows']:
        srows.append([r['quarter'], r['n'], r['unknown'] or '', _money(r['amount'], money_ok),
                      fmt(r['forecast_value']) if r['forecast_value'] is not None else ('—' if r['forecast_present'] else ''),
                      fmt(r['forecast_backlog']) if r['forecast_backlog'] is not None else '',
                      fmt(r['forecast_partial']) if r['forecast_partial'] is not None else '',
                      fmt(r['diff']) if r['diff'] is not None else ''])
    s = sched['summary']
    srows.append(['합계', s['contract_n_in_range'], s['contract_unknown_in_range'] or '', _money(s['contract_amount_in_range'], money_ok),
                  fmt(s['forecast_sum_compared']) if s['n_compared'] else '', '', '', fmt(s['diff']) if s['diff'] is not None else ''])
    P.append(table(['분기', '종료 계약 건수', '금액 미확인', '종료 계약 합계(백만원)', '기준 추정 전체', '기준 추정 잔고분', '일부 납기분', '계약합계−추정'],
                   srows, '추정치 옆에 「이 분기에 끝나는 계약 N건·합계 M」 · 백만원', [''] * (len(srows) - 1) + ['ko-sum']))
    if not forecast_ok:
        P.append('<p class="ko-note">추정 열이 빈 이유: ' + esc(freason or '기준 시나리오에 값이 없음') + '. 비교를 만들지 않았습니다.</p>')
    elif s['n_compared']:
        ratio = (s['contract_sum_compared'] / s['forecast_sum_compared']) if s['forecast_sum_compared'] else None
        P.append('<p class="ko-note">추정이 있는 ' + str(s['n_compared']) + '개 분기: 계약 종료 합계 ' + fmt(s['contract_sum_compared']) +
                 ' vs 기준 추정 전체 ' + fmt(s['forecast_sum_compared']) + ' → 차이 ' + fmt(s['diff']) + ' 백만원' +
                 (' (계약/추정 = ' + f'{ratio:,.2f}' + '배)' if ratio is not None else '') +
                 '. 어긋남을 조정하지 않았습니다 — 계약 합계는 공시 총액을 종료 분기에 통째로 둔 값이고 추정은 납품 대용치라 정의가 다릅니다.</p>')
    else:
        P.append('<p class="ko-note">추정 행은 있으나 이 구간에서 값이 있는 분기가 없어 비교하지 못했습니다.</p>')
    extra = [['구간 이전 종료(' + q_from + ' 이전)', sched['before']['n'], sched['before']['unknown'] or '', _money(sched['before']['amount'], money_ok), '이미 종료된 활성 행 · 기납품 여부는 원장에 없음'],
             ['구간 이후 종료(' + q_to + ' 이후)', sched['after']['n'], sched['after']['unknown'] or '', _money(sched['after']['amount'], money_ok), '최장 ' + (_d(max((i['end'] for i in sched['after']['items']), default=None)) or '—')],
             ['종료일 없음', len(sched['no_end']), sum(1 for i in sched['no_end'] if i['amount'] is None) or '', _money(sum(i['amount'] for i in sched['no_end'] if i['amount'] is not None), money_ok), '위 별도 묶음']]
    P.append(table(['구간 밖', '건수', '금액 미확인', '합계(백만원)', '비고'], extra, '분기 구간에 들어가지 않은 활성 계약'))

    # ---- 3. clients
    P.append('<h3>3. 발주처별 — 건수·금액·최장 종료일·비중</h3>')
    c = clients['concentration']
    cards = [
        ('최대 발주처 · 미종료 잔고 비중', (esc(c['top1_label']) + ' ' + pct(c['top1_open'])) if c['top1_open'] is not None else
         ('산출 불가: 미종료 계약 금액 없음' if items else '계약 없음')),
        ('상위 3개 발주처 · 미종료 잔고 비중', pct(c['top3_open']) if c['top3_open'] is not None else '산출 불가'),
        ('최대 발주처 · 전체 계약 비중', (esc(c['top1_label']) + ' ' + pct(c['top1_all'])) if c['top1_all'] is not None else '산출 불가'),
        ('미종료 잔고 합계(백만원)', _money(c['open_amount'], money_ok) + f' · {c["open_n"]}건' + (f' · 금액 미확인 {c["open_unknown"]}건' if c['open_unknown'] else '')),
        ('실명 발주처 수 / 익명 건수', f'{c["named_count"]} / {c["anon_n"]}' + (f' (익명 잔고 비중 {pct(c["anon_open_share"])})' if c['anon_open_share'] is not None else '')),
        ('종료일 없는 계약', f'{c["noend_n"]}건 · 미종료 여부 판정 불가'),
    ]
    P.append('<div class="ko-grid">' + ''.join('<div class="ko-card"><strong>' + esc(t) + '</strong><br>' + v + '</div>' for t, v in cards) + '</div>')
    P.append('<p class="ko-muted">「미종료 잔고」= 종료일이 기준일 이후인 활성 계약의 공시 총액 합계(금액 확인분). 기납품분을 빼지 않았고 정기보고서 수주잔고가 아닙니다. 상대 표기는 공백·법인 표시·음역 변형만 묶었고(변형 열에 표시) 자회사·현지법인은 따로 둡니다.</p>')
    if report_entry:
        kpi = report_entry.get('kpi') or {}
        bq = kpi.get('backlog_quarter')
        qorders = (((report_entry.get('quarters') or {}).get(bq) or {}).get('orders') or {}) if bq else {}
        if kpi.get('disclosed') and number(kpi.get('backlog')) and qorders.get('unit_seen'):
            P.append('<p class="ko-muted">참고 — 정기보고서 II-4 수주잔고 ' + esc(bq) + ': ' + fmt(kpi['backlog']) + ' (' + esc(qorders.get('unit_raw') or '단위 표기') + '). 범위가 달라 위 합계와 대조하지 않습니다.</p>')
        elif kpi.get('disclosed') and number(kpi.get('backlog')):
            P.append('<p class="ko-muted">참고 — 정기보고서 수주잔고는 단위 미확인(unit_seen=false)이라 숫자를 싣지 않습니다.</p>')
        else:
            P.append('<p class="ko-muted">참고 — 정기보고서 수주잔고 미공시.</p>')

    def crow(g):
        return [g['label'], g['n'], g['unknown'] or '', _money(g['amount'], money_ok), pct(g['share_all']),
                g['open_n'], _money(g['open_amount'], money_ok), pct(g['share_open']),
                _d(g['max_end']) or (f'종료일 없음({g["noend_n"]}건)' if g['noend_n'] else '—'),
                g['cn_n'] or '', ', '.join(g['variants']) if len(g['variants']) > 1 else '']

    crows, ccls = [], []
    for g in clients['top']:
        crows.append(crow(g)); ccls.append('')
    if clients['rest_row']:
        crows.append(crow(clients['rest_row'])); ccls.append('')
    if clients['anon']:
        a = clients['anon']
        row = crow(a)
        row[0] = '익명·비공개 상대 (' + str(a['n']) + '건)'
        row[-1] = ', '.join(a['variants'])
        crows.append(row); ccls.append('ko-anon')
    if items:
        crows.append(crow(clients['total'])); ccls.append('ko-sum')
    P.append(table(['발주처', '건수', '금액 미확인', '금액 합계(백만원)', '비중(전체)', '미종료 건수', '미종료 금액', '비중(잔고)', '최장 종료일', '중국향', '표기 변형'],
                   crows, f'상위 {min(top_n, len(clients["top"]))}개 실명 발주처 + 나머지 묶음 · 익명은 한 줄 · 비중 분모 = 금액 확인분', ccls))
    if not money_ok and items:
        P.append('<p class="ko-note">금액 열이 —인 이유: 이 회사의 계약 공시에서 금액 단위를 확인한 행이 없습니다. 비중도 만들지 않았습니다.</p>')

    # ---- exclusions
    P.append('<details><summary>제외 행 ' + str(len(excluded)) + '건 · 사유</summary>')
    if excluded:
        P.append(table(['접수번호', '공시일', '구분', '상대', '사유'],
                       [[i['rcp'], i['filed'], i['event'] or '—', i['party_label'], why] for i, why in excluded], '활성 원장에서 뺀 행'))
    else:
        P.append('<p class="ko-muted">제외한 행이 없습니다.</p>')
    P.append('<p class="ko-muted">해지·철회 공시는 원 계약 행과 잇는 키가 원장에 없어 원 계약을 지우지 않았습니다. 정정공시(supersedes)는 원 행을 대체합니다.</p></details>')
    P.append('</section>')
    return ''.join(P)


# ----------------------------------------------------------------------------- CLI (parity with the forecast renderer)
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contracts', type=Path, default=Path('input/ksemi_contracts.json'))
    parser.add_argument('--reports', type=Path, default=Path('input/ksemi_reports.json'))
    parser.add_argument('--panel', type=Path, default=None, help='forecast_panel.json (optional)')
    parser.add_argument('--today', default=None)
    parser.add_argument('--output-dir', type=Path, default=Path('output'))
    args = parser.parse_args()
    ledger = json.loads(args.contracts.read_text(encoding='utf-8'))
    rows = ledger['rows'] if isinstance(ledger, dict) else ledger
    reports = {}
    if args.reports and args.reports.exists():
        for r in json.loads(args.reports.read_text(encoding='utf-8')).get('rows', []):
            reports[str(r.get('stock'))] = r
    panel = {}
    if args.panel and args.panel.exists():
        for c in json.loads(args.panel.read_text(encoding='utf-8')).get('companies', []):
            panel[str(c.get('company_id'))] = c
    stocks = sorted({str(r.get('stock')) for r in rows if r.get('stock') is not None})
    directory = args.output_dir / 'orders_sections'
    directory.mkdir(parents=True, exist_ok=True)
    for stock in stocks:
        rep = reports.get(stock)
        pe = panel.get(stock) or {'company_id': stock, 'company_name': (rep or {}).get('name'), 'origin': '2026Q2'}
        htm = render_orders_section(pe, ledger, forecast_entry=panel.get(stock), today=args.today, report_entry=rep, standalone=True)
        (directory / (stock + '.html')).write_text('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                                                   '<meta name="viewport" content="width=device-width, initial-scale=1"><title>' +
                                                   esc(pe.get('company_name') or stock) + ' 수주 상세</title></head><body>' + htm + '</body></html>', encoding='utf-8')
    print('Rendered %d order sections; inline SVG/CSS; no external assets.' % len(stocks))


if __name__ == '__main__':
    main()
