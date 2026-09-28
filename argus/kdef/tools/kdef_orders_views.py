# 주의: 파일명에 탭 접두(kdef_)를 붙인다 — 섹터 도구가 sys.path 에 얹는 동명 모듈과의 충돌을 피한다
# (input/kdef_forecast_section.py 머리말과 같은 이유).
#!/usr/bin/env python3
"""KDEF 수주 상세 뷰 3종: 간트 · 분기 전환 스케줄 · 발주처별 집계.

회사 페이지에 끼우는 HTML 조각을 만든다. 인라인 SVG만 쓰고 외부 자산·스크립트는 없다.
표준 라이브러리만 사용하며 탭 패키지(kdef_forecast 등)를 import 하지 않는다.

공개 함수
  normalize_contracts(contracts, today=None, stock=None, universe=None) -> list[dict]
  build_gantt(contracts, uid, today=None, money=True, stock=None, universe=None) -> dict
  build_schedule(contracts, uid, today=None, forecast_entry=None, money=True, quarters=None,
                 stock=None, universe=None) -> dict
  build_clients(contracts, uid, today=None, money=True, top_n=8, stock=None, universe=None) -> dict
  render_orders_section(panel_entry, contracts, forecast_entry=None, today=None, universe=None,
                        reported_backlog=None) -> str

원칙: 원문(원장 행)이 지지하는 것만 싣는다. 값이 없으면 칸을 비우고 이유를 적는다. 추정으로 메우지 않는다.
"""
import sys
sys.dont_write_bytecode = True
import html
import math
import re
from collections import OrderedDict
from datetime import date, timedelta

MONEY_UNIT = 'KRW_million'
QUARTERS = ['2026Q3', '2026Q4', '2027Q1', '2027Q2', '2027Q3', '2027Q4',
            '2028Q1', '2028Q2', '2028Q3', '2028Q4']

# 방산 계통(domain) — 이 산업의 분류축. 색은 다크 배경에서 서로 구분되도록 고정 색을 쓴다.
DOMAINS = OrderedDict([
    ('MISSILE', ('유도무기', '#d9534f')),
    ('AIR', ('항공', '#4f8fd6')),
    ('NAVAL', ('함정', '#2aa198')),
    ('GROUND', ('지상', '#b58900')),
    ('FIRE', ('화력·탄약', '#e07b2e')),
    ('ISR', ('감시정찰', '#8e6bd0')),
    ('C4I', ('지휘통신', '#3fa34d')),
    ('SUPPORT', ('군수지원', '#9aa5b1')),
    ('CIVIL', ('민수', '#5f6f7f')),
])
UNCLASSIFIED = ('미분류', '#7d8491')
CTYPES = {'UPGRADE': '성능개량', 'PBL': 'PBL', 'RND': '체계개발', 'FIRST': '최초양산',
          'FOLLOW': '후속양산', 'SUPPLY': '물품구매·공급', 'UNKNOWN': '미상'}
PARTY_KINDS = {'GOV': '정부', 'PRIME': '체계업체', 'G2G': '해외정부', 'FOREIGN': '해외기업',
               'DOMESTIC': '국내기업', 'ANON': '익명', 'UNKNOWN': '미기재'}
# 발주처 통합 표기. 입력이 지지하는 것만: LIG넥스원→LIG디펜스앤에어로스페이스(kdef_universe.json "구 LIG넥스원"),
# 한화방산은 원문 표기 자체가 "한화에어로스페이스(주)와 합병"이라고 적는다.
ALIASES = {'LIG넥스원': 'LIG디펜스앤에어로스페이스', 'LIG D&A': 'LIG디펜스앤에어로스페이스',
           '한화방산(한화에어로스페이스와 합병)': '한화에어로스페이스'}
STATUS_LABEL = {'open': '진행중', 'ended': '종료 경과', 'nodate': '기간 미상', 'terminated': '해지',
                'termination': '해지 공시', 'other': '기타 공시'}


# ---------------------------------------------------------------- 공통 도우미 (기존 렌더러와 같은 결)
def esc(x):
    return html.escape(str(x), quote=True)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def fmt(x):
    return f'{x:,.3f}' if number(x) else '—'


def fmt0(x):
    return f'{x:,.0f}' if number(x) else '—'


def pct(x):
    return f'{100*x:.1f}%' if number(x) else '—'


def parse_date(s):
    if not isinstance(s, str):
        return None
    m = re.fullmatch(r'\s*(\d{4})[-./](\d{1,2})[-./](\d{1,2})\s*', s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def quarter_of(d):
    return f'{d.year}Q{(d.month-1)//3+1}'


def table(headers, rows, caption):
    return ('<div class="wrap" style="overflow-x:auto"><table><caption>'+esc(caption)+'</caption><thead><tr>'+
            ''.join('<th scope="col">'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+
            ''.join('<tr>'+''.join(('<th scope="row">' if i == 0 else '<td>')+esc(v)+
                                    ('</th>' if i == 0 else '</td>') for i, v in enumerate(row))+'</tr>' for row in rows)+
            '</tbody></table></div>')


def _svg_open(uid, title, desc, width, height, min_width=720):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
            f'aria-labelledby="{uid}-title {uid}-desc" style="width:100%;height:auto;min-width:{min_width}px">'
            f'<title id="{uid}-title">{esc(title)}</title><desc id="{uid}-desc">{esc(desc)}</desc>')


def _domain_of(r):
    return DOMAINS.get(r['domain'], UNCLASSIFIED) if r['domain'] else UNCLASSIFIED


def _canonical(raw):
    s = (raw or '').strip()
    s = re.sub(r'\([^()]*[A-Za-z][^()]*\)', ' ', s)          # 괄호 안 로마자 별칭 제거
    s = re.sub(r'\(주\)|㈜|주식회사|\(유\)|유한회사', '', s)      # 법인 형태 표기 제거(공백 없이 이어 붙임)
    s = re.sub(r'^\s*대한민국\s*', '', s)                      # 정부기관 앞의 국호
    s = re.sub(r'\s+', ' ', s).strip(' ·,')
    return ALIASES.get(s, s)


def _party(n, universe):
    """발주처 그룹 키와 표시 이름. 익명·미기재는 실명과 절대 섞지 않는다."""
    kind = n['party_kind']
    raw = n['party_raw'].strip()
    if kind == 'ANON':
        return ('ANON', raw), '익명 표기: ' + (raw or '(표기 없음)')
    if kind == 'UNKNOWN' or raw in ('', '-'):
        return ('UNKNOWN', ''), '상대 미기재'
    canon = _canonical(raw) or raw
    code = str(n['party_prime']) if n['party_prime'] else None
    names = universe or {}
    if not code:
        for k, v in names.items():                            # 종목명과 정확히 같으면 같은 체계업체
            if v == canon:
                code = k
                break
    if code:
        return ('PRIME', code), names.get(code) or canon
    return ('NAME', canon), canon


# ---------------------------------------------------------------- 정규화
def normalize_contracts(contracts, today=None, stock=None, universe=None):
    """원장 행 → 상태가 붙은 정규화 행. 상태: open/ended/nodate/terminated/termination/other.

    - stock 이 주어지면 다른 종목 행은 버린다(건수는 결과 행의 '_dropped' 에 기록).
    - 다른 행의 supersedes 에 적힌 rcp 는 정정으로 덮인 원본이므로 버린다(원장은 이미 적용돼 있어 보통 0건).
    - 「계약해지」 공시는 (계약명, 시작일)로 원본을 찾아 원본을 terminated 로 표시한다. 시작일이 없는 해지 공시는
      같은 이름의 계약이 정확히 하나일 때만 이름으로 맞춘다.
    """
    today = today or date.today()
    superseded = {r.get('supersedes') for r in contracts if isinstance(r, dict) and r.get('supersedes')}
    dropped = {'other_stock': 0, 'superseded': 0}
    base, terms, out = [], [], []
    for r in contracts:
        if not isinstance(r, dict):
            continue
        if stock and r.get('stock') != stock:
            dropped['other_stock'] += 1
            continue
        if r.get('rcp') in superseded:
            dropped['superseded'] += 1
            continue
        title = str(r.get('title') or '')
        name = str(r.get('name') or '').strip()
        amt = r.get('amt_krw_m')
        withheld = str(r.get('withheld') or '').strip()
        domain_raw = r.get('domain')
        domain = domain_raw if domain_raw in DOMAINS else None
        if r.get('civil') is True:
            domain = 'CIVIL'
        n = {'_norm': True, 'rcp': str(r.get('rcp') or ''), 'stock': str(r.get('stock') or ''), 'title': title,
             'corrected': bool(r.get('corrected')), 'name': '' if name == '-' else name,
             'domain': domain, 'domain_raw': domain_raw, 'ctype': r.get('ctype') or 'UNKNOWN',
             'civil': bool(r.get('civil')), 'amt': amt if number(amt) else None, 'amt_raw': amt,
             'party_raw': str(r.get('party') or ''), 'party_kind': r.get('party_kind') or 'UNKNOWN',
             'party_prime': r.get('party_prime'), 'region': str(r.get('region') or ''),
             'start_raw': str(r.get('start') or ''), 'end_raw': str(r.get('end') or ''),
             'end_text': str(r.get('end_raw') or ''), 'signed': str(r.get('signed') or ''),
             'withheld': '' if withheld in ('', '-') else withheld,
             'withheld_until': str(r.get('withheld_until') or ''), 'def_payrule': bool(r.get('def_payrule')),
             'years': r.get('years'), 'status': None, 'reason': '', 'matched': False, '_dropped': dropped}
        n['start'] = parse_date(n['start_raw'])
        n['end'] = parse_date(n['end_raw'])
        n['party_key'], n['party_label'] = _party(n, universe)
        if '해지' in title:
            n['status'] = 'termination'
            n['reason'] = '해지 공시(계약이 아님)'
            terms.append(n)
        elif '계약체결' in title:
            base.append(n)
        else:
            n['status'] = 'other'
            n['reason'] = '계약체결 공시가 아님: ' + (title or '제목 없음')
            out.append(n)
    by_name_start = {}
    by_name = {}
    for t in terms:
        if t['name']:
            by_name_start.setdefault((t['name'], t['start_raw']), []).append(t)
            by_name.setdefault(t['name'], []).append(t)
    same_name_count = {}
    for n in base:
        same_name_count[n['name']] = same_name_count.get(n['name'], 0) + 1
    for n in base:
        t = None
        by_start = False
        cands = by_name_start.get((n['name'], n['start_raw'])) if n['name'] else None
        if cands:
            t = cands.pop(0)
            by_start = True
        elif n['name'] and same_name_count.get(n['name']) == 1:
            for c in by_name.get(n['name'], []):
                if not c['matched'] and not c['start_raw']:
                    t = c
                    break
        if t is not None:
            t['matched'] = True
            t['matched_rcp'] = n['rcp']
            n['status'] = 'terminated'
            n['reason'] = '해지 공시 ' + t['rcp'] + ('' if by_start else '(계약명 일치)')
            out.append(n)
            continue
        if n['end'] is None and n['start'] is None:
            n['status'] = 'nodate'
            n['reason'] = '시작·종료일 미기재'
        elif n['end'] is None:
            n['status'] = 'nodate'
            n['reason'] = ('종료일 미기재' if n['end_raw'] in ('', '-') else '종료일 해석 불가: "' + n['end_raw'] + '"')
        elif n['start'] is None:
            n['status'] = 'nodate'
            n['reason'] = ('시작일 미기재' if n['start_raw'] in ('', '-') else '시작일 해석 불가: "' + n['start_raw'] + '"')
        elif n['start'] > n['end']:
            n['status'] = 'nodate'
            n['reason'] = '기간 역전(시작일이 종료일보다 늦음)'
        else:
            n['status'] = 'open' if n['end'] >= today else 'ended'
        if n['status'] == 'nodate' and n['end_text'] not in ('', '-') and n['end_text'] != n['end_raw']:
            n['reason'] += ' · 원문 종료란 "' + n['end_text'] + '"'
        out.append(n)
    out.extend(terms)
    return out


def _ensure_norm(contracts, today, stock, universe):
    rows = list(contracts or [])
    if rows and all(isinstance(r, dict) and r.get('_norm') for r in rows):
        return rows
    return normalize_contracts(rows, today, stock, universe)


def _label_name(r):
    if r['name']:
        return r['name']
    return '(계약명 유보)' if r['withheld'] else '(계약명 미기재)'


def _tooltip(r, money):
    d = _domain_of(r)[0]
    amt = (fmt(r['amt']) + ' 백만원' if r['amt'] is not None else '금액 미기재') if money else '금액 비표시'
    return (f"{_label_name(r)} · {r['party_label']} · {r['start_raw'] or '?'}~{r['end_raw'] or '?'} · "
            f"{CTYPES.get(r['ctype'], r['ctype'])} · {d} · {amt} · 공시 {r['rcp']}"
            + (' · 정정' if r['corrected'] else '') + (' · 유보: ' + r['withheld'] if r['withheld'] else ''))


def _cut(s, n):
    return s if len(s) <= n else s[:n-1] + '…'


# ---------------------------------------------------------------- 1. 간트
def _gantt_svg(rows, uid, today, money, title, t0, t1, desc_extra=''):
    W, L, R, ROW, TOP, BOT = 980, 300, 890, 18, 48, 28
    H = TOP + ROW*len(rows) + BOT
    span = max((t1 - t0).days, 1)

    def x(d):
        return L + (R-L) * max(0, min(span, (d - t0).days)) / span

    amts = [r['amt'] for r in rows if r['amt'] is not None]
    amax = max(amts) if amts else 0.
    present = []
    for r in rows:
        key = r['domain'] or '_'
        if key not in present:
            present.append(key)
    desc = (f'{len(rows)}건. 가로축 {t0.isoformat()}~{t1.isoformat()}, 종료일 순. '
            + ('막대 두께는 계약금액(백만원)의 제곱근에 비례, 라벨은 정수 반올림. ' if money else '금액 비표시(건수·기간만). ')
            + '점선 테두리는 금액 미기재. ' + desc_extra)
    parts = [_svg_open(uid, title, desc, W, H)]
    lx = 4
    for key in present:
        lab, col = DOMAINS[key] if key in DOMAINS else UNCLASSIFIED
        parts.append(f'<rect x="{lx}" y="6" width="10" height="10" fill="{col}"/>'
                     f'<text x="{lx+13}" y="15" font-size="10" fill="currentColor">{esc(lab)}</text>')
        lx += 13 + 11*len(lab) + 10
    parts.append(f'<path d="M{L},{TOP-4}V{H-BOT+4}M{R},{TOP-4}V{H-BOT+4}" stroke="var(--ln,#bbc4ce)" fill="none"/>')
    years = list(range(t0.year, t1.year + 2))
    step = 1 if (t1.year - t0.year) <= 9 else 2
    for y in years:
        if step == 2 and y % 2:
            continue
        d = date(y, 1, 1)
        if d < t0 or d > t1:
            continue
        xx = x(d)
        parts.append(f'<path d="M{xx:.1f},{TOP-4}V{H-BOT+4}" stroke="var(--ln,#bbc4ce)" stroke-opacity=".5" fill="none"/>'
                     f'<text x="{xx:.1f}" y="{TOP-8}" text-anchor="middle" font-size="10" fill="currentColor">{y}</text>')
    if t0 <= today <= t1:
        xt = x(today)
        parts.append(f'<path data-part="today" d="M{xt:.1f},{TOP-4}V{H-BOT+4}" stroke="currentColor" stroke-dasharray="4 3" fill="none"/>'
                     f'<text x="{xt:.1f}" y="{TOP-20}" text-anchor="middle" font-size="10" fill="currentColor">오늘 {today.isoformat()}</text>')
    for i, r in enumerate(rows):
        y = TOP + ROW*i
        col = _domain_of(r)[1]
        xs, xe = x(r['start']), x(r['end'])
        if xe - xs < 2:
            xe = xs + 2
        parts.append('<g><title>' + esc(_tooltip(r, money)) + '</title>')
        parts.append(f'<text x="4" y="{y+13}" font-size="10" fill="currentColor">{esc(_cut(_label_name(r), 19))}</text>'
                     f'<text x="206" y="{y+13}" font-size="9" fill="currentColor" opacity=".75">{esc(_cut(r["party_label"], 9))}</text>')
        if money and r['amt'] is not None:
            h = 5 + 11*math.sqrt(max(r['amt'], 0.)/amax) if amax > 0 else 10
            parts.append(f'<rect data-part="bar" x="{xs:.1f}" y="{y+9-h/2:.1f}" width="{xe-xs:.1f}" height="{h:.1f}" rx="2" fill="{col}"/>')
            label = fmt0(r['amt'])
        else:
            parts.append(f'<rect data-part="bar" x="{xs:.1f}" y="{y+6}" width="{xe-xs:.1f}" height="6" rx="2" fill="none" stroke="{col}" stroke-dasharray="3 2"/>')
            label = '금액 미기재' if money else ''
        if r['start'] < t0:
            parts.append(f'<path d="M{L-9},{y+9}l6,-4v8z" fill="{col}"/>')
        if label:
            parts.append(f'<text x="{min(xe, R)+4:.1f}" y="{y+13}" font-size="9" fill="currentColor">{label}</text>')
        parts.append('</g>')
    parts.append(f'<text x="4" y="{H-8}" font-size="10" fill="currentColor">'
                 + esc(('막대 두께 ∝ √금액(백만원) · 라벨 정수 반올림 · ' if money else '금액 비표시 · ')
                       + '점선 테두리: 금액 미기재 · ◀: 창 이전에 시작 · 세로 점선: 오늘') + '</text></svg>')
    return ''.join(parts)


def build_gantt(contracts, uid, today=None, money=True, stock=None, universe=None):
    """계약마다 시작~종료 막대. 종료일 순, 색은 방산 계통, 두께·라벨은 금액, 오늘 기준선.
    종료일이 없는 건·해지 건·계약이 아닌 공시는 막대 없이 별도 묶음으로 뺀다."""
    today = today or date.today()
    rows = _ensure_norm(contracts, today, stock, universe)
    key = lambda r: (r['end'], r['start'], r['rcp'])
    open_rows = sorted([r for r in rows if r['status'] == 'open'], key=key)
    ended_rows = sorted([r for r in rows if r['status'] == 'ended'], key=key)
    nodate = [r for r in rows if r['status'] == 'nodate']
    terminated = [r for r in rows if r['status'] == 'terminated']
    terms = [r for r in rows if r['status'] == 'termination']
    other = [r for r in rows if r['status'] == 'other']
    parts = [f'<h3 id="{uid}-h">수주 간트</h3>']
    parts.append(f'<p>진행중 {len(open_rows)}건 · 종료 경과 {len(ended_rows)}건 · 기간 미상 {len(nodate)}건 · '
                 f'해지 {len(terminated)}건(해지 공시 {len(terms)}건) · 기타 공시 {len(other)}건. '
                 '막대는 공시된 계약기간(시작~종료)이며 실제 인도·인식 시점이 아니다.</p>')
    if open_rows:
        t0 = min(r['start'] for r in open_rows)
        t0 = max(t0, today - timedelta(days=730))
        t0 = min(t0, today - timedelta(days=90))
        t1 = max(r['end'] for r in open_rows) + timedelta(days=60)
        parts.append('<div class="wrap" style="overflow-x:auto">'
                     + _gantt_svg(open_rows, uid + '-open', today, money, '진행중 계약 간트', t0, t1,
                                  '오늘보다 2년 이전 시작분은 창 왼쪽에서 잘라 ◀로 표시.') + '</div>')
    else:
        parts.append('<p>진행중(종료일이 오늘 이후) 계약 없음.</p>')
    if ended_rows:
        t0 = min(r['start'] for r in ended_rows)
        t1 = max(max(r['end'] for r in ended_rows), today)
        parts.append(f'<details><summary>종료일 경과 계약 {len(ended_rows)}건(막대 별도)</summary>'
                     '<p>공시 종료일이 오늘 이전인 계약. 실제 완료·정산 여부는 원문에 없다.</p>'
                     '<div class="wrap" style="overflow-x:auto">'
                     + _gantt_svg(ended_rows, uid + '-ended', today, money, '종료일 경과 계약 간트', t0, t1) + '</div></details>')
    if nodate:
        parts.append(f'<details open><summary>종료일 없는 계약 {len(nodate)}건 — 막대 없음</summary>'
                     + table(['계약명', '발주처', '시작', '원문 종료란', '금액(백만원)' if money else '금액', '비어 있는 이유'],
                             [[_label_name(r), r['party_label'], r['start_raw'] or '—', r['end_text'] or r['end_raw'] or '—',
                               (fmt(r['amt']) if money else '비표시'), r['reason'] + (' · 유보: ' + r['withheld'] if r['withheld'] else '')]
                              for r in nodate], '간트·분기 스케줄에서 제외; 발주처 집계에는 건수·금액으로 포함') + '</details>')
    if terminated or terms:
        rows_t = [[_label_name(r), r['party_label'], r['start_raw'] or '—', r['end_raw'] or '—',
                   (fmt(r['amt']) if money else '비표시'), STATUS_LABEL[r['status']] + ' · ' + r['reason']]
                  for r in terminated + [t for t in terms if not t['matched']]]
        parts.append(f'<details><summary>해지 관련 {len(rows_t)}건 — 집계 제외</summary>'
                     + table(['계약명', '발주처', '시작', '종료', '금액(백만원)' if money else '금액', '상태'], rows_t,
                             '원본이 원장에 없는 해지 공시는 공시 자체를 적는다(해지 금액은 원문 주석에만 있어 싣지 않음)') + '</details>')
    if other:
        parts.append(f'<details><summary>계약체결 공시가 아닌 행 {len(other)}건 — 집계 제외</summary>'
                     + table(['제목', '공시번호', '이유'], [[r['title'], r['rcp'], r['reason']] for r in other], '필드가 비어 있어 막대·금액 없음')
                     + '</details>')
    return {'html': ''.join(parts), 'n_bars': len(open_rows) + len(ended_rows), 'n_bars_open': len(open_rows),
            'n_bars_ended': len(ended_rows), 'open': open_rows, 'ended': ended_rows, 'nodate': nodate,
            'terminated': terminated, 'terminations': terms, 'other': other, 'rows': rows}


# ---------------------------------------------------------------- 2. 분기 전환 스케줄
def _forecast_quarters(f):
    out = {}
    if not isinstance(f, dict):
        return out
    base = (f.get('scenarios') or {}).get('base') or {}
    for r in base.get('quarterly') or []:
        q = r.get('quarter')
        if q:
            o = out.setdefault(q, {})
            o['value'] = r.get('value')
            o['backlog'] = r.get('covered_existing_backlog_revenue')
            o['interval'] = r.get('interval') or {}
    dbase = (f.get('disclosure_only_scenarios') or {}).get('base') or {}
    for r in dbase.get('quarterly') or []:
        q = r.get('quarter')
        if q:
            out.setdefault(q, {})['sites_partial'] = r.get('covered_sites_partial_revenue')
    return out


def _forecast_annual(f):
    out = {}
    if not isinstance(f, dict):
        return out
    base = (f.get('scenarios') or {}).get('base') or {}
    for r in base.get('annual') or []:
        if r.get('fiscal_year') is not None:
            out[str(r['fiscal_year'])] = r
    return out


def _schedule_svg(buckets, fq, uid, money):
    qs = list(buckets.keys())
    left, width, height, baseline = 72, 740, 138, 174
    step = width / max(len(qs), 1)
    ceilings = [1.]
    for q in qs:
        ceilings.append(buckets[q]['sum'] if money else float(buckets[q]['n']))
        v = (fq.get(q) or {}).get('value')
        if money and number(v):
            ceilings.append(v)
    top = max(ceilings)
    parts = [_svg_open(uid, '분기별 종료 계약과 기준 추정 · ' + ('백만원' if money else '건수'),
                       '왼쪽 채움 막대는 그 분기에 종료일이 있는 계약의 ' + ('총액을 계통별로 쌓은 것' if money else '건수')
                       + ', 오른쪽 테두리 막대는 기준 시나리오의 회사 전체 분기 추정(진한 부분은 가용 잔고분). '
                       '개념이 달라(총액 vs 선형 인식) 어긋남이 정상이며 맞추지 않았다.', 840, 236)]
    parts.append(f'<path d="M{left},34V{baseline}H816" fill="none" stroke="var(--ln,#bbc4ce)"/>'
                 f'<text x="66" y="32" text-anchor="end" fill="currentColor" font-size="10">{top:,.0f}</text>'
                 f'<text x="66" y="178" text-anchor="end" fill="currentColor" font-size="10">0</text>')
    for i, q in enumerate(qs):
        b = buckets[q]
        x = left + (i+.5)*step
        parts.append(f'<g><title>{esc(q)}: 종료 {b["n"]}건' + (f' · 합계 {fmt(b["sum"])} 백만원 · 금액 미기재 {b["n_noamt"]}건' if money else '') + '</title>')
        offset = 0.
        if money:
            for key, val in b['by_domain'].items():
                if val <= 0:
                    continue
                col = DOMAINS[key][1] if key in DOMAINS else UNCLASSIFIED[1]
                hgt = height*val/top
                parts.append(f'<rect data-part="contracts" x="{x-22:.1f}" y="{baseline-height*(offset+val)/top:.1f}" width="24" height="{hgt:.1f}" fill="{col}"/>')
                offset += val
        elif b['n']:
            parts.append(f'<rect data-part="contracts" x="{x-22:.1f}" y="{baseline-height*b["n"]/top:.1f}" width="24" height="{height*b["n"]/top:.1f}" fill="var(--a,#176b9b)"/>')
        parts.append(f'<text x="{x-10:.1f}" y="{baseline-height*(b["sum"] if money else b["n"])/top-3:.1f}" text-anchor="middle" font-size="9" fill="currentColor">{b["n"]}건</text>')
        f = fq.get(q) or {}
        if money and number(f.get('value')):
            hv = height*f['value']/top
            parts.append(f'<rect data-part="forecast" x="{x+6:.1f}" y="{baseline-hv:.1f}" width="14" height="{hv:.1f}" fill="none" stroke="var(--a,#176b9b)"/>')
            if number(f.get('backlog')) and f['backlog'] >= 0:
                hb = height*min(f['backlog'], f['value'])/top
                parts.append(f'<rect data-part="forecast-backlog" x="{x+6:.1f}" y="{baseline-hb:.1f}" width="14" height="{hb:.1f}" fill="var(--a,#176b9b)" fill-opacity=".55"/>')
        parts.append(f'<text x="{x:.1f}" y="194" text-anchor="middle" fill="currentColor" font-size="10">{esc(q)}</text></g>')
    parts.append('<text x="72" y="222" fill="currentColor" font-size="10">'
                 + esc(('채움: 이 분기 종료 계약 총액(계통색) · 테두리: 기준 추정 회사 전체(진한 부분 가용 잔고분) · ' if money
                        else '채움: 이 분기 종료 계약 건수 · ') + '추정 미제공이면 테두리 막대 없음') + '</text></svg>')
    return ''.join(parts)


def build_schedule(contracts, uid, today=None, forecast_entry=None, money=True, quarters=None, stock=None, universe=None):
    """종료일을 분기로 묶어 창(기본 2026Q3~2028Q4)에 쌓고, 페이지의 기준 추정을 옆에 둔다.
    창 밖(이전·이후)과 종료일 없는 건은 따로 세어 합계가 계약 합계와 맞도록 한다."""
    today = today or date.today()
    qs = list(quarters or QUARTERS)
    rows = _ensure_norm(contracts, today, stock, universe)
    dated = [r for r in rows if r['status'] in ('open', 'ended')]
    nodate = [r for r in rows if r['status'] == 'nodate']

    def bucket():
        return {'n': 0, 'sum': 0., 'n_noamt': 0, 'n_past': 0, 'by_domain': OrderedDict(), 'rows': []}
    buckets = OrderedDict((q, bucket()) for q in qs)
    before, after = bucket(), bucket()
    for r in dated:
        q = quarter_of(r['end'])
        if q in buckets:
            b = buckets[q]
        elif q < qs[0]:
            b = before
        else:
            b = after
        b['n'] += 1
        b['rows'].append(r)
        if r['end'] < today:
            b['n_past'] += 1
        if r['amt'] is not None:
            b['sum'] += r['amt']
            key = r['domain'] or '_'
            b['by_domain'][key] = b['by_domain'].get(key, 0.) + r['amt']
        else:
            b['n_noamt'] += 1
    total_n = sum(b['n'] for b in buckets.values()) + before['n'] + after['n']
    total_sum = sum(b['sum'] for b in buckets.values()) + before['sum'] + after['sum']
    window_n = sum(b['n'] for b in buckets.values())
    window_sum = sum(b['sum'] for b in buckets.values())
    fq = _forecast_quarters(forecast_entry)
    fa = _forecast_annual(forecast_entry)
    has_forecast = any(number((fq.get(q) or {}).get('value')) for q in qs)
    mismatches = []
    data = []
    for q in qs:
        b = buckets[q]
        f = fq.get(q) or {}
        v, bl, sp = f.get('value'), f.get('backlog'), f.get('sites_partial')
        diff = (v - b['sum']) if (money and number(v)) else None
        note = ''
        if not forecast_entry:
            note = '추정 미제공'
        elif not number(v):
            note = '이 분기 추정 없음'
        elif money and b['sum'] > v:
            note = '종료 계약 총액이 추정 회사 전체를 초과 — 총액은 종료 분기에 몰리고 추정은 선형 인식이라 어긋남; 조정하지 않음'
            mismatches.append(q)
        elif money and b['n'] == 0:
            note = '이 분기 종료 계약 없음(추정은 잔고 선형 인식·신규 가정)'
        if b['n_past']:
            note = (note + ' · ' if note else '') + f'오늘 이전 종료 {b["n_past"]}건 포함'
        if money:
            data.append([q, b['n'], fmt(b['sum']) if b['n'] else '—', b['n_noamt'] or '—',
                         fmt(v), fmt(bl), fmt(sp), fmt(diff), note])
        else:
            data.append([q, b['n'], b['n_noamt'] or '—', note or '금액 비표시'])
    parts = [f'<h3 id="{uid}-h">분기 전환 스케줄 {qs[0]}~{qs[-1]}</h3>']
    parts.append('<p>종료일 기준으로 분기에 묶은 계약 총액이다. 기인식분을 차감하지 않았으므로 잔고나 매출이 아니다. '
                 '옆의 추정은 페이지에 실린 기준 시나리오(회사 전체 분기 추정·가용 잔고분·공시 계약 부분)이며 두 값을 맞추지 않았다. '
                 + ('추정 항목이 제공되지 않아 추정 열은 비어 있다.' if not forecast_entry else
                    ('추정과 어긋나는 분기: ' + ', '.join(mismatches) if mismatches else '종료 총액이 추정을 넘는 분기는 없다.')) + '</p>')
    parts.append('<div class="wrap" style="overflow-x:auto">' + _schedule_svg(buckets, fq, uid + '-svg', money) + '</div>')
    if money:
        parts.append(table(['분기', '종료 계약', '종료 총액', '금액 미기재', '추정 회사 전체(기준)', '추정 가용 잔고분', '공시 계약 부분(선형)', '추정−종료 총액', '대조'],
                           data, '백만원 · 추정 열은 forecast_entry 의 base 시나리오 저장값 그대로'))
    else:
        parts.append(table(['분기', '종료 계약', '금액 미기재', '대조'], data, '건수만 표시(금액 단위 미확인)'))
    outside = [['창 이전(' + qs[0] + ' 전) 종료', before['n'], fmt(before['sum']) if money else '비표시', before['n_noamt'] or '—'],
               ['창 이후(' + qs[-1] + ' 후) 종료', after['n'], fmt(after['sum']) if money else '비표시', after['n_noamt'] or '—'],
               ['창 안 소계', window_n, fmt(window_sum) if money else '비표시', sum(b['n_noamt'] for b in buckets.values()) or '—'],
               ['종료일 있는 계약 합계', total_n, fmt(total_sum) if money else '비표시', before['n_noamt'] + after['n_noamt'] + sum(b['n_noamt'] for b in buckets.values()) or '—'],
               ['종료일 없음(제외)', len(nodate), fmt(sum(r['amt'] for r in nodate if r['amt'] is not None)) if money else '비표시', sum(1 for r in nodate if r['amt'] is None) or '—']]
    parts.append(table(['구간', '건수', '총액(백만원)' if money else '총액', '금액 미기재'], outside, '창 밖 구간까지 더하면 종료일 있는 계약 전체와 같다'))
    if money and forecast_entry:
        roll = []
        for label, group, fy in [('2026 하반기(Q3~Q4)', [q for q in qs if q.startswith('2026')], '2026'),
                                 ('FY2027', [q for q in qs if q.startswith('2027')], '2027'),
                                 ('FY2028(Y+2)', [q for q in qs if q.startswith('2028')], '2028')]:
            if not group:
                continue
            csum = sum(buckets[q]['sum'] for q in group)
            cn = sum(buckets[q]['n'] for q in group)
            vals = [(fq.get(q) or {}).get('value') for q in group]
            qsum = sum(vals) if all(number(v) for v in vals) else None
            annual = (fa.get(fy) or {}).get('value')
            roll.append([label, cn, fmt(csum), fmt(qsum), fmt(annual) + (' (관측 H1 포함)' if fy == '2026' and number(annual) else ''),
                         fmt(qsum - csum) if number(qsum) else '—'])
        parts.append(table(['기간', '종료 계약', '종료 총액', '분기 추정 합(기준)', '연간 추정(기준)', '분기 추정 합−종료 총액'], roll,
                           'Y+2 대조 · 백만원 · 연간 추정은 저장값, 분기 합은 분기 저장값의 단순 합'))
    return {'html': ''.join(parts), 'buckets': buckets, 'before': before, 'after': after, 'nodate': nodate,
            'total_n': total_n, 'total_sum': total_sum, 'window_n': window_n, 'window_sum': window_sum,
            'forecast_quarters': fq, 'has_forecast': has_forecast, 'mismatches': mismatches, 'quarters': qs, 'rows': rows}


# ---------------------------------------------------------------- 3. 발주처별
def _new_group(key, label):
    return {'key': key, 'label': label, 'kinds': [], 'n': 0, 'sum': 0., 'n_amt': 0, 'n_noamt': 0, 'n_open': 0,
            'sum_open': 0., 'n_open_noamt': 0, 'n_nodate': 0, 'max_end': None, 'variants': OrderedDict(), 'members': 0}


def _add(g, r):
    if r['party_kind'] not in g['kinds']:
        g['kinds'].append(r['party_kind'])
    g['n'] += 1
    raw = r['party_raw'].strip() or '(빈칸)'
    g['variants'][raw] = g['variants'].get(raw, 0) + 1
    if r['amt'] is not None:
        g['sum'] += r['amt']
        g['n_amt'] += 1
    else:
        g['n_noamt'] += 1
    if r['status'] == 'open':
        g['n_open'] += 1
        if r['amt'] is not None:
            g['sum_open'] += r['amt']
        else:
            g['n_open_noamt'] += 1
    if r['status'] == 'nodate':
        g['n_nodate'] += 1
    if r['end'] and (g['max_end'] is None or r['end'] > g['max_end']):
        g['max_end'] = r['end']


def _merge(dst, g):
    for k in g['kinds']:
        if k not in dst['kinds']:
            dst['kinds'].append(k)
    for k in ('n', 'sum', 'n_amt', 'n_noamt', 'n_open', 'sum_open', 'n_open_noamt', 'n_nodate'):
        dst[k] += g[k]
    if g['max_end'] and (dst['max_end'] is None or g['max_end'] > dst['max_end']):
        dst['max_end'] = g['max_end']
    dst['variants'][g['label']] = g['n']
    dst['members'] += 1


def _clients_svg(items, uid, money, total):
    ROW, L, R = 20, 300, 900
    H = 30 + ROW*len(items) + 24
    parts = [_svg_open(uid, '발주처 비중 · ' + ('진행중 계약 총액' if money else '진행중 건수'),
                       '막대 길이는 진행중(종료일이 오늘 이후) 계약의 ' + ('총액' if money else '건수') + ' 비중. 익명·미기재는 실명과 섞지 않고 따로 한 줄.', 980, H)]
    parts.append(f'<path d="M{L},22V{H-20}" stroke="var(--ln,#bbc4ce)" fill="none"/>')
    for i, g in enumerate(items):
        y = 30 + ROW*i
        share = g.get('share_open')
        w = (R-L)*share if number(share) else 0
        special = g['key'][0] in ('ANON', 'UNKNOWN', 'REST')
        fill = 'var(--ln,#bbc4ce)' if special else 'var(--a,#176b9b)'
        parts.append(f'<g><title>{esc(g["label"])}: 진행중 {g["n_open"]}건' + (f' · {fmt(g["sum_open"])} 백만원' if money else '') + f' · 전체 {g["n"]}건</title>'
                     f'<text x="4" y="{y+13}" font-size="10" fill="currentColor">{esc(_cut(g["label"], 26))}</text>'
                     f'<rect data-part="share" x="{L}" y="{y+3}" width="{w:.1f}" height="13" fill="{fill}"' + (' fill-opacity=".6"' if special else '') + '/>'
                     f'<text x="{L+w+4:.1f}" y="{y+13}" font-size="9" fill="currentColor">{esc(pct(share))}' + (f' · {g["n_open"]}건' if g['n_open'] else ' · 진행중 없음') + '</text></g>')
    parts.append(f'<text x="4" y="{H-6}" font-size="10" fill="currentColor">' + esc('분모: 진행중 계약 ' + (f'총액 {fmt(total)} 백만원' if money else f'{total}건') + ' · 회색: 나머지 묶음·익명·미기재') + '</text></svg>')
    return ''.join(parts)


def build_clients(contracts, uid, today=None, money=True, top_n=8, stock=None, universe=None):
    """상대별 집계(건수·금액·최장 종료일·비중). 익명·미기재는 각각 한 줄로 실명과 분리. 상위 N + 나머지 묶음 + 집중도."""
    today = today or date.today()
    rows = _ensure_norm(contracts, today, stock, universe)
    scope = [r for r in rows if r['status'] in ('open', 'ended', 'nodate')]
    groups = OrderedDict()
    for r in scope:
        g = groups.get(r['party_key'])
        if g is None:
            g = groups[r['party_key']] = _new_group(r['party_key'], r['party_label'])
        _add(g, r)
    for g in groups.values():
        if g['key'][0] == 'PRIME' and universe and universe.get(g['key'][1]):
            g['label'] = universe[g['key'][1]]
    total_all = sum(g['sum'] for g in groups.values())
    total_open = sum(g['sum_open'] for g in groups.values())
    n_all = sum(g['n'] for g in groups.values())
    n_open = sum(g['n_open'] for g in groups.values())
    named = [g for g in groups.values() if g['key'][0] not in ('ANON', 'UNKNOWN')]
    special = [g for g in groups.values() if g['key'][0] in ('ANON', 'UNKNOWN')]
    if money:
        named.sort(key=lambda g: (-g['sum_open'], -g['sum'], -g['n_open'], -g['n'], g['label']))
    else:
        named.sort(key=lambda g: (-g['n_open'], -g['n'], g['label']))
    top, rest = named[:top_n], named[top_n:]
    rest_group = None
    if rest:
        rest_group = _new_group(('REST', ''), f'나머지 {len(rest)}개 발주처')
        for g in rest:
            _merge(rest_group, g)
    items = top + ([rest_group] if rest_group else []) + special
    denom_open = total_open if money else n_open
    denom_all = total_all if money else n_all
    for g in items:
        num_open = g['sum_open'] if money else g['n_open']
        num_all = g['sum'] if money else g['n']
        g['share_open'] = num_open/denom_open if denom_open > 0 else None
        g['share_all'] = num_all/denom_all if denom_all > 0 else None
    top1 = top[0]['share_open'] if top else None
    top3 = sum(g['share_open'] for g in top[:3] if number(g['share_open'])) if top and number(top[0]['share_open']) else None
    parts = [f'<h3 id="{uid}-h">발주처별</h3>']
    parts.append('<p>' + esc(f'실명 발주처 {len(named)}곳' + (f' · 익명·미기재 {len(special)}줄' if special else '') +
                             f' · 대상 {n_all}건(진행중 {n_open}건). ') +
                 ('비중의 분모는 진행중(종료일이 오늘 이후) 계약의 총액 합계이며 기인식분을 차감하지 않은 계약 총액이다. ' if money
                  else '금액 단위가 확인되지 않아 건수 비중만 보인다. ') +
                 esc(f'집중도: 최대 발주처 {pct(top1)} · 상위 3곳 {pct(top3)}.' if top else '집계 대상 없음.') +
                 ' 종목명으로 되짚은 체계업체는 종목코드로 묶고, 그 밖은 법인 형태·로마자 별칭·국호를 뗀 이름으로 묶었다(원문 표기 열 참조).</p>')
    if items:
        parts.append('<div class="wrap" style="overflow-x:auto">' + _clients_svg(items, uid + '-svg', money, denom_open) + '</div>')
        if money:
            hdr = ['발주처', '갈래', '건수', '총액', '금액 미기재', '진행중 건수', '진행중 총액', '진행중 비중', '전체 비중', '최장 종료일', '원문 표기']
            data = [[g['label'], '/'.join(PARTY_KINDS.get(k, k) for k in g['kinds']), g['n'], fmt(g['sum']) if g['n_amt'] else '—',
                     g['n_noamt'] or '—', g['n_open'], fmt(g['sum_open']) if g['n_open'] - g['n_open_noamt'] else '—',
                     pct(g['share_open']) if g['n_open'] else '—', pct(g['share_all']),
                     g['max_end'].isoformat() if g['max_end'] else '—(종료일 없음)',
                     ' · '.join(f'{k}×{v}' if v > 1 else k for k, v in g['variants'].items())] for g in items]
            cap = '백만원 · 총액은 공시 계약금액 합, 잔고 아님 · 상위 ' + str(min(top_n, len(named))) + '곳 + 나머지 + 익명·미기재'
        else:
            hdr = ['발주처', '갈래', '건수', '진행중 건수', '진행중 건수 비중', '전체 건수 비중', '최장 종료일', '원문 표기']
            data = [[g['label'], '/'.join(PARTY_KINDS.get(k, k) for k in g['kinds']), g['n'], g['n_open'],
                     pct(g['share_open']) if g['n_open'] else '—', pct(g['share_all']),
                     g['max_end'].isoformat() if g['max_end'] else '—(종료일 없음)',
                     ' · '.join(f'{k}×{v}' if v > 1 else k for k, v in g['variants'].items())] for g in items]
            cap = '건수만 · 상위 ' + str(min(top_n, len(named))) + '곳 + 나머지 + 익명·미기재'
        parts.append(table(hdr, data, cap))
    return {'html': ''.join(parts), 'groups': groups, 'top': top, 'rest': rest, 'rest_group': rest_group, 'special': special,
            'items': items, 'total_all': total_all, 'total_open': total_open, 'n_all': n_all, 'n_open': n_open,
            'top1_share': top1, 'top3_share': top3, 'n_named': len(named), 'rows': rows}


# ---------------------------------------------------------------- 섹션
def render_orders_section(panel_entry, contracts, forecast_entry=None, today=None, universe=None, reported_backlog=None):
    """회사 페이지에 끼울 수주 상세 조각. 기존 render_forecast_section 과 같은 검사 관례(종목코드·회사 동일성·단위)를 따른다.

    panel_entry: {'stock','co'|'name','src'?}  contracts: 원장 행(list[dict]; 다른 종목 행은 걸러 냄)
    forecast_entry: 페이지의 회사 전망 항목(없으면 추정 열 비움)  today: 기준일(기본 오늘)
    universe: {종목코드: 종목명}  reported_backlog: {'quarter','value','unit_seen','cur'} 참고용 공시 잔고
    """
    today = today or date.today()
    stock = panel_entry.get('stock')
    name = panel_entry.get('co') or panel_entry.get('name') or '회사'
    if not isinstance(stock, str) or not re.fullmatch(r'[0-9A-Z]{6}', stock):
        raise ValueError('invalid stock identifier')
    f = forecast_entry
    money = True
    unit_note = ''
    if f is not None:
        if (f.get('stock') not in (None, stock)) or (f.get('company_id') not in (None, stock)):
            raise ValueError('company_identity_conflict')
        if f.get('company_name') not in (None, name):
            raise ValueError('company_identity_conflict')
        if panel_entry.get('src') is not None and f.get('source') is not None and panel_entry['src'] != f['source']:
            raise ValueError('company_source_conflict')
        if f.get('money_unit') not in (None, MONEY_UNIT):
            money = False
            unit_note = f'전망 항목의 금액 단위가 {f.get("money_unit")} 로 백만원과 다르므로 금액을 싣지 않고 건수·기간만 보인다.'
    if panel_entry.get('money_unit') not in (None, MONEY_UNIT):
        money = False
        unit_note = f'패널의 금액 단위가 {panel_entry.get("money_unit")} 로 확인되지 않아 금액을 싣지 않고 건수·기간만 보인다.'
    uid = 'kdef-orders-' + stock
    rows = normalize_contracts(contracts, today, stock, universe)
    dropped = rows[0]['_dropped'] if rows else {'other_stock': 0, 'superseded': 0}
    g = build_gantt(rows, uid + '-gantt', today, money)
    s = build_schedule(rows, uid + '-schedule', today, f, money)
    c = build_clients(rows, uid + '-clients', today, money)
    counts = {k: sum(1 for r in rows if r['status'] == k) for k in STATUS_LABEL}
    civil = [r for r in rows if r['domain'] == 'CIVIL' and r['status'] in ('open', 'ended', 'nodate')]
    amt_all = sum(r['amt'] for r in rows if r['amt'] is not None and r['status'] in ('open', 'ended', 'nodate'))
    parts = [f'<section id="{uid}" class="wrap" data-orders-status="{"money" if money else "count_only"}" '
             f'data-orders-rows="{len(rows)}" data-orders-bars="{g["n_bars"]}" data-orders-open="{g["n_bars_open"]}">',
             f'<h2>{esc(name)} · 수주 상세 — 간트 · 분기 전환 · 발주처</h2>',
             f'<p>기준일 {today.isoformat()} · 원천: 단일판매ㆍ공급계약 공시 원장 {len(rows)}행'
             + (f'(다른 종목 {dropped["other_stock"]}행 제외)' if dropped['other_stock'] else '')
             + (f'(정정으로 덮인 원본 {dropped["superseded"]}행 제외)' if dropped['superseded'] else '')
             + ' · ' + ' · '.join(f'{STATUS_LABEL[k]} {v}건' for k, v in counts.items() if v)
             + (f' · 이 중 민수(CIVIL) {len(civil)}건' if civil else '') + '.</p>']
    if money:
        parts.append(f'<p>금액은 공시 계약금액(백만원, 저장값 재환산 없음; 외화 계약은 공시 시점 환산액). 계약 총액이며 기인식분을 차감하지 않았으므로 '
                     f'수주잔고·매출이 아니다. 집계 대상(진행중·종료 경과·기간 미상) 총액 {fmt(amt_all)} 백만원. 계열 회사 간 합산 금지.</p>')
    else:
        parts.append('<p><strong>금액 비표시</strong>: ' + esc(unit_note) + '</p>')
    if isinstance(reported_backlog, dict) and number(reported_backlog.get('value')):
        if reported_backlog.get('unit_seen') and reported_backlog.get('cur', 'KRW') == 'KRW' and money:
            parts.append(f'<p>참고: 정기보고서 수주잔고 {esc(reported_backlog.get("quarter", ""))} {fmt(reported_backlog["value"])} 백만원. '
                         '수시공시 대상(일정 규모 이상)만 담긴 계약 총액과 범위·차감 방식이 달라 직접 비교하지 않는다.</p>')
        else:
            parts.append('<p>참고: 정기보고서 수주잔고는 단위 미확인 또는 외화라 싣지 않는다.</p>')
    parts.append(g['html'])
    parts.append(s['html'])
    parts.append(c['html'])
    parts.append('<details><summary>이 조각의 규칙</summary><ul>'
                 '<li>상태: 종료일 ≥ 기준일이면 진행중, 아니면 종료 경과. 시작·종료일이 없거나 해석 불가·역전이면 기간 미상(막대·분기 제외, 발주처 집계 포함).</li>'
                 '<li>해지 공시는 (계약명, 시작일)로 원본을 찾아 둘 다 집계에서 뺀다. 원본이 없으면 공시만 적는다.</li>'
                 '<li>계통 색: ' + esc(' · '.join(f'{v[0]}({k})' for k, v in DOMAINS.items())) + ' · 미분류는 회색. 민수(CIVIL) 계약은 민수 색으로 포함한다.</li>'
                 '<li>발주처: 익명 표기·상대 미기재는 실명과 합치지 않고 각각 한 줄. 종목명으로 되짚은 체계업체는 종목코드로, 그 밖은 법인 형태·로마자 별칭·국호를 뗀 표기로 묶는다. '
                 '통합 표기 ' + esc(', '.join(f'{k}→{v}' for k, v in ALIASES.items())) + '.</li>'
                 '<li>추정 열은 forecast_entry(base) 저장값 그대로이며, 종료 총액과 어긋나도 조정하지 않는다.</li></ul></details></section>')
    return ''.join(parts)


if __name__ == '__main__':
    print('이 모듈은 라이브러리다. 검증은 output/selfcheck_kdef.py 를 실행한다.')
