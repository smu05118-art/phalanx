#!/usr/bin/env python3
"""Drop-in KCE forecast HTML; standard library, existing theme tokens, no JS/CSS assets.
Run: python3 -B output/forecast_section.py (writes three sample fragments).
"""
import sys
sys.dont_write_bytecode = True
import html
import json
import math
import re
from pathlib import Path

LABELS = {'conservative':'보수', 'base':'기준', 'optimistic':'낙관'}
REASONS = {
 'duration':'유효 공기 근거 부족', 'start_lag':'착공 시차 근거 부족',
 'new_order_samples_minimum_4':'최근 순수주 적격 표본 4개 미만',
 'full_existing_backlog_coverage':'기존 잔고 전체를 추정할 근거 부족',
 'grade_audit_prohibits_estimation':'감사표의 추정 보류 판정',
 'company_absent_from_grade_audit':'제공 감사표에 회사 항목 없음',
 'no_observation_at_origin':'2026Q2 관측 없음',
 'company_identity_conflict':'회사 식별 충돌',
 'duplicate_site_identity':'중복 현장 식별자',
 'unlisted_excluded_from_listed_universe':'비상장 계열사로 상장사 추정에서 제외',
 'missing_observed_calendar_quarter':'FY2026 상반기 원장 차분 누락',
}
NEGATIVE_WARNING = '⚠ 음수 원장 대용치: 현장 교체·제외 영향, 실제 매출로 해석 불가'

def esc(x):
    return html.escape(str(x), quote=True)

def number(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def fmt(v):
    return f'{v:,.3f}' if number(v) else '—'

def reason(codes):
    codes = codes or ['근거 부족']
    return '; '.join(REASONS.get(x,x) for x in codes)

def value_cell(v):
    return esc(fmt(v)) + (f'<br><strong>{NEGATIVE_WARNING}</strong>' if number(v) and v<0 else '')

def bounds(row,partial=False,covered=False):
    b=row.get('covered_sites_partial_interval' if covered else 'partial_existing_interval' if partial else 'interval') or {}
    if number(b.get('lower')) and number(b.get('upper')):
        return f"{fmt(b['lower'])} ~ {fmt(b['upper'])}"
    return '— (구간 근거 없음)'

def chart(rows,uid,annual=False):
    """Signed annual values; quarterly stacks retain null component semantics."""
    values=[]; descriptions=[]
    for r in rows:
        total=r.get('value'); part=r.get('existing_backlog_revenue')
        partial=False
        if not annual and not number(part):
            part=r.get('covered_sites_partial_revenue'); partial=number(part)
        shown=total if number(total) else part if not annual else None
        values.append(shown)
        label=f"FY{r['fiscal_year']}" if annual else r['quarter']
        descriptions.append(f"{label}: 전체 {fmt(total)}; 잔고분 {fmt(part)}{' (일부 현장)' if partial else ''}; 신규분 {fmt(r.get('new_order_revenue'))}; 구간 {bounds(r)}" + ('; '+NEGATIVE_WARNING if number(total) and total<0 else ''))
    lo=min([0]+[v for v in values if number(v)]); hi=max([0]+[v for v in values if number(v)])
    for r in rows:
        for key in ('interval','partial_existing_interval','covered_sites_partial_interval') if not annual else ('interval',):
            b=r.get(key) or {}
            if number(b.get('lower')): lo=min(lo,b['lower'])
            if number(b.get('upper')): hi=max(hi,b['upper'])
    spread=hi-lo or 1
    top,bottom,left,width=28,170,84,720
    def y(v): return top+(hi-v)/spread*(bottom-top)
    baseline=y(0); step=width/max(1,len(rows)); bar=min(38,step*.54)
    title='연간 전체 추정' if annual else '분기 추정: 잔고분·신규분'
    chunks=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 222" role="img" aria-labelledby="{uid}-title {uid}-desc" style="width:100%;height:auto;display:block;color:var(--tx)">',
        f'<title id="{uid}-title">{title} (백만원)</title>',f'<desc id="{uid}-desc">{esc(" / ".join(descriptions))}</desc>',
        f'<line x1="{left}" x2="812" y1="{baseline:.3f}" y2="{baseline:.3f}" stroke="var(--ln)"/>']
    for v in sorted(set((lo,0,hi))):
        chunks.append(f'<text x="78" y="{y(v)+4:.3f}" text-anchor="end" fill="var(--tx)" font-size="10">{v:,.0f}</text>')
    for i,(r,v) in enumerate(zip(rows,values)):
        x=left+(i+.5)*step; label=f"FY{r['fiscal_year']}" if annual else r['quarter']
        chunks.append(f'<g data-period="{esc(label)}" data-value="{esc(fmt(r.get("value")))}"><title>{esc(descriptions[i])}</title>')
        if number(v):
            if not annual and number(r.get('value')):
                e=r['existing_backlog_revenue']; n=r['new_order_revenue']
                parts=[('existing',e,0,'var(--a)',1),('new',n,e,'var(--tx)',.55)]
            else:
                parts=[('annual' if annual else 'partial',v,0,'var(--a)',1)]
            for key,height,offset,fill,opacity in parts:
                ya,yb=y(offset),y(offset+height)
                chunks.append(f'<rect data-part="{key}" x="{x-bar/2:.3f}" y="{min(ya,yb):.3f}" width="{bar:.3f}" height="{abs(ya-yb):.3f}" fill="{fill}" fill-opacity="{opacity}"/>')
            ci=r.get('interval') if number(r.get('value')) else r.get('partial_existing_interval') if number(r.get('existing_backlog_revenue')) else r.get('covered_sites_partial_interval')
            if ci and number(ci.get('lower')) and number(ci.get('upper')):
                yl,yu=y(ci['lower']),y(ci['upper'])
                chunks.append(f'<path data-part="interval" d="M{x:.3f},{yl:.3f}V{yu:.3f} M{x-4:.3f},{yl:.3f}H{x+4:.3f} M{x-4:.3f},{yu:.3f}H{x+4:.3f}" fill="none" stroke="var(--tx)" stroke-width="1.2"/>')
            if not number(r.get('value')):
                chunks.append(f'<text x="{x:.3f}" y="20" text-anchor="middle" fill="var(--tx)" font-size="10">부분</text>')
            if v<0:
                chunks.append(f'<text x="{x:.3f}" y="204" text-anchor="middle" fill="var(--tx)" font-size="11">⚠ 음수 대용치</text>')
        else:
            chunks.append(f'<text x="{x:.3f}" y="100" text-anchor="middle" fill="var(--tx)" font-size="12">미추정</text>')
        chunks.append(f'<text x="{x:.3f}" y="189" text-anchor="middle" fill="var(--tx)" font-size="10">{esc(label)}</text></g>')
    chunks.append('</svg>')
    return ''.join(chunks)

def table_html(headers,rows,caption):
    return ('<div style="overflow-x:auto"><table style="width:100%"><caption style="text-align:left">'+esc(caption)+
        '</caption><thead><tr>'+''.join('<th scope="col">'+esc(h)+'</th>' for h in headers)+
        '</tr></thead><tbody>'+''.join('<tr>'+''.join(('<th scope="row">' if i==0 else '<td>')+v+('</th>' if i==0 else '</td>') for i,v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table></div>')

def render_forecast_section(panel_entry, forecast_entry) -> str:
    """Render one company, rejecting mismatched joins before rendering any amounts."""
    stock=panel_entry.get('stock'); name=panel_entry.get('co') or '회사'
    if stock is None:
        return f'<p class="wrap" data-forecast-status="excluded_unlisted">{esc(name)} — 비상장 계열사: 상장사 추정에서 제외.</p>'
    if not isinstance(stock,str) or not re.fullmatch(r'[0-9]{6}',stock):
        raise ValueError('invalid listed stock identifier')
    if forecast_entry is None:
        return f'<p class="wrap" data-forecast-status="unavailable">{esc(name)} — 미추정: 제공된 추정 항목 없음.</p>'
    if (forecast_entry.get('company_id')!=stock or forecast_entry.get('company_name')!=name
        or forecast_entry.get('stock',stock)!=stock or forecast_entry.get('listed',True) is not True
        or forecast_entry.get('source')!=panel_entry.get('src')):
        raise ValueError('company_identity_conflict: panel and forecast must match')
    if forecast_entry.get('money_unit')!='KRW_million':
        raise ValueError('money_unit must be KRW_million')
    scenarios=forecast_entry.get('scenarios') or {}
    has_values=any(number(r.get(f)) for s in scenarios.values() for r in s.get('quarterly',[])
                   for f in ('value','existing_backlog_revenue','covered_sites_partial_revenue','new_order_revenue'))
    if not has_values:
        return f'<p class="wrap" data-forecast-status="unavailable">{esc(name)} — 미추정: {esc(reason(forecast_entry.get("reason_codes")))}.</p>'
    uid='forecast-'+stock
    chunks=[f'<section class="wrap" id="{uid}" data-forecast-status="{esc(forecast_entry["status"])}" aria-labelledby="{uid}-heading" style="color:var(--tx);background:var(--pn);border:1px solid var(--ln);padding:1rem">',
        f'<h2 id="{uid}-heading">{esc(name)} Y+2 원장 매출 <span style="color:var(--a);border:1px solid var(--ln);padding:.1em .4em">추정</span></h2>',
        '<p>기준 2026Q2 · 백만원 · 2026Q3~2028Q4 · 12월 결산 가정. 현장 원장 범위의 조건부 대용치이며 연결 매출 전망으로 해석하지 않습니다.</p>',
        '<p>시나리오 칩을 펼쳐 비교하세요. 막대: 잔고분(강조색) + 신규분(본문색). 세로선: 민감도 구간이며 통계적 신뢰구간이 아닙니다.</p>']
    if forecast_entry['status']!='full_ledger_estimate':
        chunks.append('<p><strong>부분 추정 — 전체 금액은 미추정.</strong> '+esc(reason(forecast_entry.get('reason_codes')))+'; 없는 구성은 0으로 대입하지 않습니다.</p>')
    for key,label in LABELS.items():
        s=scenarios[key]; qs=s['quarterly']; annual=s['annual']; a=s['assumptions']
        chunks.append(f'<details data-scenario="{key}"'+(' open' if key=='base' else '')+' style="margin:.75rem 0">'+
            f'<summary style="display:list-item;cursor:pointer"><span style="display:inline-block;background:var(--bg);border:1px solid var(--ln);border-radius:1rem;padding:.25rem .75rem;color:var(--a)">{label} 시나리오 · P{ {"conservative":25,"base":50,"optimistic":75}[key]}</span></summary>')
        chunks.append(chart(qs,uid+'-'+key+'-q'))
        quarter_rows=[]
        for r in qs:
            existing=r.get('existing_backlog_revenue'); covered=r.get('covered_sites_partial_revenue')
            existing_display=value_cell(existing) if number(existing) else (value_cell(covered)+' (일부 현장만)' if number(covered) else '—')
            part=not number(r.get('value')) and number(existing)
            covered_only=not number(r.get('value')) and not part and number(covered)
            shown_bounds=bounds(r,partial=part,covered=covered_only)
            quarter_rows.append([esc(r['quarter']),value_cell(r.get('value')),existing_display,
                                 value_cell(r.get('new_order_revenue')),esc(shown_bounds)+(' (잔고분만)' if part else ' (일부 현장만)' if covered_only else '')])
        chunks.append(table_html(['분기','전체 추정','잔고분','신규분','민감도 구간'],quarter_rows,label+' 시나리오 · 분기 구성 (백만원)'))
        chunks.append(chart(annual,uid+'-'+key+'-y',annual=True))
        annual_rows=[]
        for r in annual:
            total=value_cell(r.get('value'))
            if not number(r.get('value')):
                total+=' · '+esc(reason((r.get('reason') or ';'.join(forecast_entry.get('reason_codes',[]))).split(';')))
            existing_value=value_cell(r.get('existing_backlog_revenue'))
            if not number(r.get('existing_backlog_revenue')) and number(r.get('covered_sites_partial_revenue')):
                existing_value=value_cell(r['covered_sites_partial_revenue'])+' (일부 현장만)'
            annual_rows.append([f"FY{r['fiscal_year']}",total,value_cell(r.get('observed_revenue')),
                existing_value,value_cell(r.get('new_order_revenue')),esc(bounds(r))])
        chunks.append(table_html(['연도','전체 추정','관측 원장 차분','미래 잔고분','미래 신규분','전체 민감도 구간'],annual_rows,label+' 시나리오 · 연간 구성 (백만원)'))
        chunks.append('<p><small>가정: 계절조정 분기 순수주 '+esc(fmt(a.get('new_orders_per_quarter_deseasonalized')))+'백만원; 공기 '+esc(fmt(a.get('duration_quarters')))+'분기; 착공 시차 '+esc(fmt(a.get('lag_quarters')))+'분기. 보수/기준/낙관은 수주 P25/P50/P75이며 공기·시차는 같은 중앙값입니다.</small></p></details>')
    chunks.append('<p><small>가정·한계: FY2026 = Q1·Q2 관측 원장 ΔC + Q3·Q4 추정; FY2027·FY2028 = 네 분기 추정 합. 잔고분·신규분은 미래 분기만 포함합니다. O=Δ잔고+Δ기성의 최근 8분기 적격 4개 이상 표본을 사용하며 음수 O는 원장에 보존하고 미래 양의 수주 코호트에만 max(O,0)를 적용합니다. 현재 일정의 공기·착공 시차를 사용하며 분기말 수주를 공기 동안 균등 인식합니다. 구간은 속도 범위와 수주 P10~P90의 민감도이며 보정되지 않았습니다. 현장 교체·계약 변경·가공 표식 누락(sFilled) 영향이 있고, 신규수주 포함 전체 예측의 과거 검증은 불가합니다. 원본 미래 예측은 적합·채점에 쓰지 않았습니다. —는 근거 부족이며 0이 아닙니다.</small></p></section>')
    return ''.join(chunks)

def write_samples():
    root=Path(__file__).resolve().parents[1]
    panel=json.loads((root/'input/kce_panel_v4.json').read_text())
    forecasts={c['company_id']:c for c in json.loads((root/'output/forecast_panel.json').read_text())['companies']}
    out=root/'output/samples'; out.mkdir(exist_ok=True)
    for filename,code in [('full_028050.html','028050'),('partial_014790.html','014790'),('unavailable_001880.html','001880')]:
        (out/filename).write_text(render_forecast_section(panel[code],forecasts[code])+'\n')

if __name__=='__main__':
    write_samples()
