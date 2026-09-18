# 주의: 파일명을 `forecast_section.py` 로 두면 섹터 도구가 sys.path 에 얹는 argus/kce/tools 의
# 같은 이름 모듈이 먼저 잡힌다 — 탭 접두를 붙여 구분한다.
#!/usr/bin/env python3
"""KDEF company fragment: inline SVG, HTML tables/details, no external assets."""
import sys
sys.dont_write_bytecode = True
import html
import json
import math
import re
from pathlib import Path
from kdef_forecast import REASONS, TYPES

LABELS = {'conservative': '보수', 'base': '기준', 'optimistic': '낙관'}


def esc(x):
    return html.escape(str(x), quote=True)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def fmt(x):
    return f'{x:,.3f}' if number(x) else '—'


def reasons(codes):
    return '; '.join(REASONS.get(x, x) for x in codes)


def bounds(r, field):
    b = r.get(field, {})
    return f"{fmt(b.get('lower'))} ~ {fmt(b.get('upper'))}" if number(b.get('lower')) else '—'


def table(headers, rows, caption):
    return ('<div style="overflow-x:auto"><table><caption>'+esc(caption)+'</caption><thead><tr>'+
            ''.join('<th scope="col">'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+
            ''.join('<tr>'+''.join(('<th scope="row">' if i == 0 else '<td>')+esc(v)+
                                    ('</th>' if i == 0 else '</td>') for i, v in enumerate(row))+'</tr>' for row in rows)+
            '</tbody></table></div>')


def chart(rows, uid, annual=False):
    """Components remain visibly partial even when one component is unavailable."""
    def shown_band(r):
        e, n = r.get('covered_sites_partial_revenue'), r.get('covered_new_order_revenue')
        if number(e) and number(n):
            if annual and r.get('observed_quarters_required'):
                # FY2026 has no annual total: the graphic shows future components only.
                eb, nb = r['covered_sites_partial_interval'], r['covered_new_order_interval']
                return {key: eb[key]+nb[key] if number(eb[key]) and number(nb[key]) else None
                        for key in ('lower', 'upper')}
            return r['covered_total_partial_interval']
        return r.get('covered_sites_partial_interval' if number(e) else 'covered_new_order_interval', {})
    description = []
    ceilings = []
    for r in rows:
        label = f"FY{r['fiscal_year']}" if annual else r['quarter']
        e, n = r.get('covered_sites_partial_revenue'), r.get('covered_new_order_revenue')
        description.append(f"{label}: 회사 전체 미추정; 일정 잔여 부분 {fmt(e)}, 신규 가정 부분 {fmt(n)} 백만원")
        ceilings.append((e if number(e) else 0)+(n if number(n) else 0))
        b = shown_band(r)
        if number(b.get('upper')):
            ceilings.append(b['upper'])
        for key in ('covered_total_partial_interval', 'covered_sites_partial_interval', 'covered_new_order_interval'):
            b = r.get(key, {})
            if number(b.get('upper')):
                ceilings.append(b['upper'])
    top = max(ceilings+[1.])
    left, width, height, baseline = 72, 740, 138, 174
    step = width/max(len(rows), 1)
    bar = min(36, .5*step)
    result = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 228" role="img" aria-labelledby="{uid}-title {uid}-desc" style="width:100%;height:auto">',
              f'<title id="{uid}-title">알려진 계약의 부분 인식 모형, 백만원</title>',
              f'<desc id="{uid}-desc">{esc(" / ".join(description))}. 민감도 범위이며 신뢰구간이 아닙니다.</desc>',
              f'<path d="M{left},34V{baseline}H816" fill="none" stroke="var(--ln,#bbc4ce)"/>',
              f'<text x="66" y="32" text-anchor="end" fill="currentColor" font-size="10">{top:,.0f}</text>',
              f'<text x="66" y="178" text-anchor="end" fill="currentColor" font-size="10">0</text>']
    for i, r in enumerate(rows):
        x = left+(i+.5)*step
        e, n = r.get('covered_sites_partial_revenue'), r.get('covered_new_order_revenue')
        label = f"FY{r['fiscal_year']}" if annual else r['quarter']
        result.append('<g><title>'+esc(description[i])+'</title>')
        offset = 0.
        for kind, value, color in [('existing', e, 'var(--a,#176b9b)'), ('new', n, '#b97432')]:
            if number(value):
                y = baseline-height*(offset+value)/top
                result.append(f'<rect data-part="{kind}" x="{x-bar/2:.3f}" y="{y:.3f}" width="{bar:.3f}" height="{height*value/top:.3f}" fill="{color}"/>')
                offset += value
        if not number(e) and not number(n):
            marker = '미추정'
        elif annual and r.get('observed_quarters_required'):
            marker = '미래분만'
        elif not number(e) or not number(n):
            marker = '일부 구성'
        else:
            marker = '부분합'
        result.append(f'<text x="{x:.3f}" y="24" text-anchor="middle" fill="currentColor" font-size="10">{marker}</text>')
        b = shown_band(r)
        if number(b.get('lower')) and number(b.get('upper')):
            yl, yu = baseline-height*b['lower']/top, baseline-height*b['upper']/top
            result.append(f'<path data-part="interval" d="M{x:.3f},{yl:.3f}V{yu:.3f}M{x-4:.3f},{yl:.3f}H{x+4:.3f}M{x-4:.3f},{yu:.3f}H{x+4:.3f}" stroke="currentColor" fill="none"/>')
        result.append(f'<text x="{x:.3f}" y="194" text-anchor="middle" fill="currentColor" font-size="10">{esc(label)}</text></g>')
    result.append('<text x="72" y="219" fill="currentColor" font-size="10">파랑: 일정 잔여 부분 · 갈색: 신규 가정 부분 · —: 근거 부족 · 회사 전체 매출 미추정</text></svg>')
    return ''.join(result)


def schedule_svg(contracts, uid):
    from kdef_forecast import parse_date
    from datetime import date
    cut, end = date(2026, 6, 30), date(2028, 12, 31)
    shown = contracts[:16]
    height = 60+26*len(shown)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 {height}" role="img" aria-labelledby="{uid}-title {uid}-desc" style="width:100%;height:auto">',
             f'<title id="{uid}-title">계약별 기간표</title>',
             f'<desc id="{uid}-desc">기준 2026년 6월 말부터 2028년 말까지의 계약 기간. 실제 선표·공정단계·호기별 인도 일정은 미확인. 최대 16건의 기간만 표시하고 전체 계약은 표로 제공합니다.</desc>']
    for year, d in [('2026Q2', cut), ('2027', date(2027, 1, 1)), ('2028', date(2028, 1, 1)), ('2028Q4', end)]:
        x = 270+530*(d-cut).days/(end-cut).days
        parts.append(f'<text x="{x:.3f}" y="16" text-anchor="middle" fill="currentColor" font-size="10">{year}</text>')
    for i, c in enumerate(shown):
        s, e = parse_date(c['start']), parse_date(c['end'])
        lo, hi = max(cut, s), min(end, e)
        x1 = 270+530*max(0, (lo-cut).days)/(end-cut).days
        x2 = 270+530*max(0, (hi-cut).days)/(end-cut).days
        y = 28+26*i
        name = c['name']
        parts.append(f'<g><title>{esc(name)} · {esc(c["start"])}~{esc(c["end"])} · {esc(TYPES[c["ctype"]][0])}</title>')
        parts.append(f'<text x="4" y="{y+12}" fill="currentColor" font-size="11">{esc(name[:22])}</text>')
        if x2 > x1 and lo <= end:
            parts.append(f'<rect x="{x1:.3f}" y="{y}" width="{x2-x1:.3f}" height="15" rx="3" fill="var(--a,#176b9b)"/>')
        parts.append('</g>')
    parts.append('</svg>')
    return ''.join(parts)


# Round-2 renderer extends the original escaping, table and schedule helpers.
def company_chart(rows, uid, annual=False):
    values = [r.get('value') for r in rows]
    top = max([r['interval']['upper'] for r in rows if number(r['interval']['upper'])]+[1.])
    baseline, height, left, width = 185, 150, 76, 732
    step = width/max(1,len(rows))
    label = lambda r: f"FY{r['fiscal_year']}" if annual else r['quarter']
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 244" role="img" aria-labelledby="{uid}-title {uid}-desc">',
             f'<title id="{uid}-title">회사 매출표 전체 조건부 전망 · 백만원</title>',
             f'<desc id="{uid}-desc">'+esc('; '.join(label(r)+': '+fmt(r.get('value')) for r in rows))+'. 구간은 보정되지 않은 민감도입니다.</desc>',
             f'<path d="M{left},25V{baseline}H816" fill="none" stroke="currentColor"/>',
             f'<text x="70" y="30" text-anchor="end" fill="currentColor" font-size="10">{top:,.0f}</text>']
    colors = ['#7d8491','#287da6','#c37e33','#8a65b1']
    for i,r in enumerate(rows):
        x=left+(i+.5)*step; offset=0
        components=[r.get('observed_revenue',0),r.get('covered_existing_backlog_revenue'),r.get('covered_new_order_revenue'),r.get('unallocated_revenue')]
        for v,color in zip(components,colors):
            if not number(v) or v < 0:continue
            parts.append(f'<rect x="{x-13:.3f}" y="{baseline-height*(offset+v)/top:.3f}" width="26" height="{height*v/top:.3f}" fill="{color}"/>')
            offset+=v
        band=r['interval']
        if number(band['lower']) and number(band['upper']):
            lo,hi=baseline-height*band['lower']/top,baseline-height*band['upper']/top
            parts.append(f'<path d="M{x:.3f},{lo:.3f}V{hi:.3f}M{x-4:.3f},{lo:.3f}H{x+4:.3f}M{x-4:.3f},{hi:.3f}H{x+4:.3f}" stroke="currentColor" fill="none"/>')
        parts.append(f'<text x="{x:.3f}" y="205" text-anchor="middle" font-size="10" fill="currentColor">{esc(label(r))}</text>')
    parts.append('<text x="76" y="232" font-size="10" fill="currentColor">회색 관측누계 · 파랑 가용 잔고분 · 갈색 가용 신규분 · 보라 미분해 매출</text></svg>')
    return ''.join(parts)


def render_forecast_section(panel_entry, forecast_entry):
    stock=panel_entry.get('stock'); name=panel_entry.get('co') or panel_entry.get('name') or '회사'
    if not isinstance(stock,str) or not re.fullmatch(r'[0-9A-Z]{6}',stock):raise ValueError('invalid stock identifier')
    f=forecast_entry
    if f is None:return '<section><p>미추정: 회사 항목 없음</p></section>'
    if f.get('stock')!=stock or f.get('company_id')!=stock or f.get('company_name')!=name:raise ValueError('company_identity_conflict')
    if panel_entry.get('src') is not None and panel_entry['src']!=f['source']:raise ValueError('company_source_conflict')
    if f['money_unit']!='KRW_million':raise ValueError('unsupported monetary unit')
    uid='kdef-forecast-'+stock
    parts=[f'<section id="{uid}" data-forecast-status="{esc(f["status"])}"><h1>{esc(name)} · FY2026~FY2028</h1>',
           '<p>2026Q2 보고서 기준 · 분기 T+1~T+10 · 백만원 · 저장값 재환산 없음</p>',
           '<p>회사 전체는 제공된 매출표 전체의 조건부 전망입니다. 연결/별도 범위와 12월 결산·매출 누계 해석은 독립 검증되지 않았습니다. <strong>calibrated=false</strong>: 구간은 민감도이며 통계적 신뢰구간이 아닙니다. —는 미확인입니다.</p>',
           '<p>계열 회사 간 합산 금지. 계약 공시 부분 전망은 아래 회사 전체 금액에 추가하지 않습니다.</p>']
    bt=f['backtest']
    parts.append(f'<p>이 회사 매출 금액 채점 {bt["monetary"]["n"]}건 · 전 기간 공시 이후인 표본 {bt["forward_only_n"]}건 · MAE {fmt(bt["monetary"]["MAE"])} 백만원. 계약별 실제 인식 채점 0건. 짧은 중첩 표본으로 장기 정확도를 보증하지 않습니다.</p>')
    if f['company_total_available']:
        parts.append('<p>기존 잔고는 시나리오 간 동일합니다. 보수/기준/낙관은 신규수주와 미분해 매출 속도 ×0.8/1.0/1.2입니다. 관측 H1과 미래분을 구분하고, 나누지 못한 잔고·신규 구성은 미분해 매출로 표시합니다.</p>')
        for key,label in LABELS.items():
            s=f['scenarios'][key]
            parts.append(f'<details data-scenario="{key}"'+(' open' if key=='base' else '')+f'><summary>{label}</summary>')
            for annual,rs in [(True,s['annual']),(False,s['quarterly'])]:
                parts.append(company_chart(rs,uid+'-'+key+('-a' if annual else '-q'),annual))
                data=[]
                for r in rs:
                    data.append([f'FY{r["fiscal_year"]}' if annual else r['quarter'],fmt(r['value']),fmt(r.get('observed_revenue')) if annual else '해당 없음',fmt(r.get('covered_existing_backlog_revenue')),fmt(r.get('covered_new_order_revenue')),fmt(r.get('unallocated_revenue')),bounds(r,'interval')])
                parts.append(table(['기간','회사 전체','관측 누계','가용 잔고분','가용 신규분','미분해 매출','민감도'],data,label+' · 백만원; 잔고·신규·미분해는 미래분'))
            parts.append(table(['연도','방산','CIVIL','혼합','미분류','내수','수출'],[[f'FY{r["fiscal_year"]}',*[fmt((r.get('axes') or {}).get(k)) for k in ('defense','civil','mixed','unknown')],*[fmt((r.get('routes') or {}).get(k)) for k in ('내수','수출')]] for r in s['annual']], '금액 축; 내수/수출은 대사된 기준분기 구성비 고정 가정'))
            parts.append('</details>')
        parts.append('<details><summary>잔고 연결과 인식 가정</summary>'+table(['범위','누계 매출','연결 잔고','기간 D(분기)','모형'],[[b['axis'],fmt(b['sales_ytd']),fmt((b.get('balance') or {}).get('value')),fmt(b['duration_quarters']),b['method']] for b in f['monetary_evidence']['blocks']], 'D는 관측 잔고/매출 회전비율의 중앙값; 실측 인도기간 아님')+'<p>유형별 속도 차이는 검증되지 않아 사용하지 않았습니다. 신규는 미래 분기 말 코호트 발생 가정입니다.</p></details>')
    else:
        parts.append('<p><strong>회사 전체 금액 보류</strong>: '+esc(reasons(f['monetary_evidence']['reason_codes']))+'</p>')
    if f['evidence']['contracts'] or f['evidence']['new_orders']['available']:
        parts.append('<details><summary>별도 공시 계약의 부분 전망</summary><p>기인식액을 모르는 공시 코호트의 공통 선형 일정 가정입니다. 실제 회사 잔고나 회사 전체 매출이 아닙니다. CIVIL 공시는 제외했습니다.</p>')
        for key,label in LABELS.items():
            rs=f['disclosure_only_scenarios'][key]['quarterly']
            parts.append(table(['분기','기존 일정 부분','공시 신규 가정 부분'],[[r['quarter'],fmt(r['covered_sites_partial_revenue']),fmt(r['covered_new_order_revenue'])] for r in rs],label+' 공시 부분 · 백만원'))
        if f['evidence']['contracts']:
            parts.append(schedule_svg(f['evidence']['contracts'],uid+'-contracts'))
        parts.append('</details>')
    if f['ledger_money_runoff']:
        parts.append('<details><summary>정확한 납기가 있는 원장 잔고의 별도 소진표</summary>'+table(['행','범위','잔고','납기']+[f'T+{h}' for h in range(1,11)],[[r['label'],r['axis'],fmt(r['balance']),r['end'],*[fmt(x) for x in r['quarterly']]] for r in f['ledger_money_runoff']], '공통 선형 가정; 회사 전체 전망에 추가하지 않음')+'</details>')
    parts.append('<details><summary>단위 근거·보류 사유</summary><p>'+esc(reasons(f['reason_codes']))+'</p>'+table(['분기','원문 캡션','저장 배수'],[[q,', '.join(v['raw_unit_caption']) or '캡션 미제공',1] for q,v in f['unit_audit']['quarters'].items()], '저장 금액은 이미 백만원; 외화 잔고는 합산 제외')+'</details></section>')
    return ''.join(parts)


def write_sections(panel, directory):
    directory.mkdir(parents=True,exist_ok=True)
    style=':root{color-scheme:light dark}body{font:15px/1.65 system-ui,sans-serif;max-width:1160px;margin:auto;padding:24px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #8993a2;padding:8px;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}caption{text-align:left;font-weight:600}summary{padding:12px;cursor:pointer;font-weight:650}svg{width:100%;height:auto}details{margin-block:12px}'
    count=0
    for c in panel['companies']:
        if c['status']=='unavailable':
            owned=directory/(c['stock']+'.html')
            if owned.exists():owned.unlink()
            continue
        fragment=render_forecast_section({'stock':c['stock'],'co':c['company_name'],'src':c['source']},c)
        page='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(c['company_name'])+' 전망</title><style>'+style+'</style></head><body>'+fragment+'</body></html>'
        (directory/(c['stock']+'.html')).write_text(page+'\n',encoding='utf-8');count+=1
    return count


if __name__=='__main__':
    out=Path(__file__).resolve().parent
    print(write_sections(json.loads((out/'forecast_panel.json').read_text()),out/'sections'))
