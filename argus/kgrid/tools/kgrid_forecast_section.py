# 주의: 파일명을 `forecast_section.py` 로 두면 섹터 도구가 sys.path 에 얹는 argus/kce/tools 의
# 동명 모듈이 먼저 잡혀 건설 렌더러가 불린다. 탭 접두를 붙인다.
#!/usr/bin/env python3
"""KGRID company forecast fragment, stdlib + inline SVG, no external assets.

API: render_forecast_section(panel_entry, forecast_entry) -> str
CLI: python3 -B output/forecast_section.py
"""
import sys
sys.dont_write_bytecode = True
import html
import json
import math
import re
from pathlib import Path
from kgrid_forecast import REASONS

LABELS = {'conservative': '보수', 'base': '기준', 'optimistic': '낙관'}


def esc(x):
    return html.escape(str(x), quote=True)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def fmt(v, ratio=False):
    if not number(v):
        return '—'
    return f'{v*100:,.3f}%' if ratio else f'{v:,.3f}'


def reasons(codes):
    return '; '.join(REASONS.get(x, x) for x in codes) or '추정 범위 밖'


def table(headers, rows, caption):
    return ('<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse"><caption style="text-align:left">'+esc(caption)+
            '</caption><thead><tr>'+''.join('<th scope="col">'+esc(h)+'</th>' for h in headers)+
            '</tr></thead><tbody>'+''.join('<tr>'+''.join(('<th scope="row">' if i == 0 else '<td>')+esc(v)+
            ('</th>' if i == 0 else '</td>') for i, v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table></div>')


def shown(row):
    if number(row.get('value')):
        return row['value'], 'interval', '범위 전체'
    if number(row.get('existing_backlog_revenue')):
        return row['existing_backlog_revenue'], 'partial_existing_interval', '기존 잔고분만'
    if number(row.get('covered_sites_partial_revenue')):
        return row['covered_sites_partial_revenue'], 'covered_sites_partial_interval', '일부 행 잔고분만'
    return None, 'interval', '미추정'


def chart(rows, uid, ratio=False, annual=False):
    values = [shown(r) for r in rows]
    top = max([1e-9] + [v for v, _, _ in values if number(v)] +
              [r.get(k, {}).get('upper', 0) or 0 for r, (_, k, _) in zip(rows, values)])
    unit = '기준 잔고 대비 %' if ratio else '백만원 · 검증 원장 범위'
    title = ('연간' if annual else '분기')+' 기존 잔고·신규수주 추정 · '+unit
    descriptions = []
    for r, (v, key, kind) in zip(rows, values):
        period = 'FY'+str(r['fiscal_year']) if annual else r['quarter']
        bounds = r.get(key, {})
        descriptions.append(f"{period}: {kind} {fmt(v, ratio)}; 전체 {fmt(r.get('value'),ratio)}; "
                            f"잔고분 {fmt(r.get('existing_backlog_revenue'),ratio)}; 신규분 {fmt(r.get('new_order_revenue'),ratio)}; "
                            f"민감도 {fmt(bounds.get('lower'),ratio)}~{fmt(bounds.get('upper'),ratio)}")
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 242" role="img" aria-labelledby="{uid}-title {uid}-desc" style="display:block;width:100%;height:auto">',
              f'<title id="{uid}-title">{esc(title)}</title>',
              f'<desc id="{uid}-desc">{esc(" / ".join(descriptions))} 민감도 범위는 통계적 신뢰구간이 아닙니다.</desc>',
              '<line x1="92" y1="192" x2="884" y2="192" stroke="var(--ln,#6b7280)"/>',
              f'<text x="88" y="28" text-anchor="end" font-size="11" fill="currentColor">{esc(fmt(top,ratio))}</text>',
              '<text x="88" y="196" text-anchor="end" font-size="11" fill="currentColor">0</text>']
    width = 780/max(1, len(rows))
    def y(v):
        return 192-v/top*162
    for i, (r, (v, key, kind)) in enumerate(zip(rows, values)):
        x = 94+(i+.5)*width
        label = 'FY'+str(r['fiscal_year']) if annual else r['quarter']
        chunks.append(f'<g data-period="{esc(label)}"><title>{esc(descriptions[i])}</title>')
        if number(v):
            if number(r.get('value')):
                parts = [('existing', r['existing_backlog_revenue'], '#219ebc'),
                         ('new', r['new_order_revenue'], '#f4a261')]
                if annual:
                    parts.insert(0, ('observed', r.get('observed_revenue', 0), '#8d99ae'))
            else:
                parts = [('partial', v, '#219ebc')]
            offset = 0
            for name, height, color in parts:
                if not number(height):
                    continue
                chunks.append(f'<rect data-part="{name}" x="{x-17:.3f}" y="{y(offset+height):.3f}" width="34" height="{height/top*162:.3f}" fill="{color}"/>')
                offset += height
            b = r.get(key, {})
            if number(b.get('lower')) and number(b.get('upper')):
                chunks.append(f'<path data-part="sensitivity" d="M{x:.3f},{y(b["lower"]):.3f}V{y(b["upper"]):.3f} M{x-5:.3f},{y(b["lower"]):.3f}H{x+5:.3f} M{x-5:.3f},{y(b["upper"]):.3f}H{x+5:.3f}" stroke="currentColor" fill="none"/>')
            if kind != '범위 전체':
                chunks.append(f'<text x="{x:.3f}" y="20" text-anchor="middle" font-size="10" fill="currentColor">부분</text>')
        else:
            chunks.append(f'<text x="{x:.3f}" y="112" text-anchor="middle" font-size="11" fill="currentColor">미추정</text>')
        chunks.append(f'<text x="{x:.3f}" y="212" text-anchor="middle" font-size="10" fill="currentColor">{esc(label)}</text></g>')
    chunks.append('</svg>')
    return ''.join(chunks)


def period_table(rows, ratio=False, annual=False):
    rendered = []
    for r in rows:
        v, key, kind = shown(r)
        b = r.get(key, {})
        existing = fmt(r.get('existing_backlog_revenue'), ratio)
        if not number(r.get('existing_backlog_revenue')) and number(r.get('covered_sites_partial_revenue')):
            existing = fmt(r['covered_sites_partial_revenue'], ratio)+' (일부 행)'
        row = [('FY'+str(r['fiscal_year'])) if annual else r['quarter'], fmt(r.get('value'), ratio)]
        if annual:
            row.append(fmt(r.get('observed_revenue'), ratio))
        row.extend([existing, fmt(r.get('new_order_revenue'), ratio),
                    fmt(b.get('lower'), ratio)+' ~ '+fmt(b.get('upper'), ratio)+' ('+kind+')'])
        if not number(r.get('value')):
            row[1] += ' · '+reasons(r.get('reason_codes') or ['new_order_history_short'])
        rendered.append(row)
    heads = ['연도' if annual else '분기', '범위 전체']
    if annual:
        heads.append('이미 관측한 흐름')
    heads += ['미래 잔고분', '미래 신규분', '민감도 범위']
    return table(heads, rendered, ('연간 구성' if annual else '분기 구성')+' · '+('기준 잔고 대비 %' if ratio else '백만원 · 검증 원장 범위'))


def render_forecast_section(panel_entry, forecast_entry):
    stock = panel_entry.get('stock')
    name = panel_entry.get('co') or panel_entry.get('name') or '회사'
    if not isinstance(stock, str) or not re.fullmatch(r'\d{6}', stock):
        raise ValueError('invalid stock identifier')
    if forecast_entry is None:
        return f'<p class="wrap" data-forecast-status="unavailable">{esc(name)} — 미추정: 원장 항목 없음.</p>'
    f = forecast_entry
    if f.get('stock') != stock or f.get('company_id') != stock or f.get('company_name') != name:
        raise ValueError('company_identity_conflict')
    if 'src' in panel_entry and panel_entry['src'] != f.get('source'):
        raise ValueError('company_source_conflict')
    if f.get('money_unit') not in (None, 'KRW_million'):
        raise ValueError('unrecognized amount unit')
    has_money = any(number(r.get(k)) for s in f['scenarios'].values() for r in s['quarterly']
                    for k in ('value', 'existing_backlog_revenue', 'covered_sites_partial_revenue', 'new_order_revenue'))
    if has_money and f.get('money_unit') != 'KRW_million':
        raise ValueError('unverified monetary value')
    uid = 'kgrid-forecast-'+stock
    axes = f.get('industry_axes', {})
    branch = {'long_lead': '장납기', 'turnover': '회전'}.get(f['evidence']['branch'], '미상')
    bt = f.get('backtest_summary', {})
    cm = bt.get('company', {})
    overall = bt.get('all_companies', {})
    chunks = [f'<section class="wrap" id="{uid}" data-forecast-status="{esc(f["status"])}" aria-labelledby="{uid}-heading" style="color:var(--tx,#202936);background:var(--pn,#fff);border:1px solid var(--ln,#aaa);padding:1rem">',
              f'<h2 id="{uid}-heading">{esc(name)} · Y+2 조건부 추정</h2>',
              f'<p>기준 {esc(f["origin"])} · 2026Q3~2028Q4 · FY2026~FY2028 · 12월 결산 가정(미검증). '
              f'원장 범위: {esc(f["scope"])} · 장납기/회전: <strong>{branch}</strong> · 원장 통화 {esc(f.get("currency") or "미상")}.</p>',
              '<p><strong>선택 원장 범위의 조건부 납품 대용치입니다.</strong> 재무제표 매출과 같다고 단정할 수 없습니다. '
              '금액은 제공된 정규화 계약과 회사·분기 캡션으로 검증한 백만원입니다. 비율 100%는 선택한 기준 잔고와 같은 크기입니다. '
              '회사별 금액·비율을 산업 합계로 더하지 않습니다.</p>',
              '<p>막대: 기존 잔고분(청색) + 신규수주 가정분(주황색), 이미 관측한 흐름(회색). '
              '<strong>구간은 민감도 범위이며 통계적 신뢰구간이 아닙니다(calibrated=false).</strong> —는 근거 부족입니다.</p>',
              f'<p><strong>백테스트 표본이 적습니다.</strong> 이 회사 {cm.get("n",0)}개 · 전체 {overall.get("n",0)}개 · '
              f'완전 연간 {bt.get("annual_n",0)}개 · 금액 {bt.get("money_n",0)}개. '
              f'회사 비율 WAPE {esc(fmt(cm.get("wape_pct")))}%. T+2~T+10/완전 연간 성능은 미검증이며 최신 수정 원장의 사후 검증입니다.</p>',
              '<p>미추정/부분 사유: '+esc(reasons(f.get('reason_codes', [])))+'</p>',
              '<details><summary>전력계통·선표·공정·호기 근거</summary>',
              '<p>계통/제품: '+esc(' / '.join(axes.get('grid_products', [])) or '자료 없음')+'</p>',
              '<p>선표: 선적·납품·검수 마일스톤 자료 없음. 공정단계: 설계·조달·제조·시험의 실측 진행률 없음. '
              '호기: 개별 기기/호기별 잔고 식별자 없음. 공시 납기를 실제 검수·수익인식일로 단정하지 않습니다.</p>',
              '<p>선택 범위: '+esc(' / '.join(f.get('scope_labels', [])) or '미확정')+'</p>']
    customers = axes.get('utility_customers', [])
    chunks.append(table(['실명 매출처 문구', '비중 %', '귀속', '부문'],
                        [[r.get('name') or '—', fmt(r.get('share_pct')), r.get('entity') or '본체 표/세부 귀속 미확정', r.get('seg') or '—']
                         for r in customers], '보고서 본체 첫 표의 실명 근거 · 합산/미래 배분하지 않음'))
    chunks.append('<p>'+esc(axes.get('customer_note', '실명 고객 자료 없음'))+'</p>')
    for t in axes.get('demand_quotes', []):
        chunks.append('<blockquote>'+esc(t)+'</blockquote>')
    for t in (axes.get('probe_evidence', {}).get('evidence') or []):
        chunks.append('<blockquote>프로브 원문: '+esc(t)+'</blockquote>')
    retry = f.get('retry_plan', {})
    if retry.get('rerun_on_ledger_extension'):
        chunks.append('<p>needs_longer_ledger · 19분기 확장 후 재검증: '+esc(retry.get('group'))+'. '+esc(retry.get('condition'))+'</p>')
    chunks.append('</details>')
    if f['status'] == 'unavailable':
        chunks.append('<p><strong>미추정.</strong> 잔고·매출·단위·범위·일정 중 막힌 근거를 먼저 복원해야 합니다.</p></section>')
        return ''.join(chunks)
    normalized = f['normalized_forecast']['scenarios']
    for key, label in LABELS.items():
        s = normalized[key]; a = s['assumptions']
        chunks.append(f'<details data-scenario="{key}"'+(' open' if key == 'base' else '')+f'><summary>{label} 시나리오</summary>')
        if has_money:
            ms = f['scenarios'][key]
            chunks.append('<h3>검증된 원장 범위 · 백만원</h3><p>전체 값이 —이면 잔고 전체 또는 일부 행의 소진분만 추정한 것입니다. '
                          '미상 신규수주를 0으로 채우지 않았습니다.</p>')
            chunks.append(chart(ms['quarterly'], uid+'-'+key+'-mq'))
            chunks.append(period_table(ms['quarterly']))
            chunks.append(chart(ms['annual'], uid+'-'+key+'-my', annual=True))
            chunks.append(period_table(ms['annual'], annual=True))
        chunks.append('<details><summary>기준 잔고 대비 비율과 모델 가정</summary>')
        chunks.append(chart(s['quarterly'], uid+'-'+key+'-q', ratio=True))
        chunks.append(period_table(s['quarterly'], ratio=True))
        chunks.append(chart(s['annual'], uid+'-'+key+'-y', ratio=True, annual=True))
        chunks.append(period_table(s['annual'], ratio=True, annual=True))
        chunks.append('<p>신규수주 가정/분기: 기준 잔고의 '+esc(fmt(a['new_orders_per_quarter_deseasonalized'], True))+
                      '; 소진기간 대용치 '+esc(fmt(a['duration_quarters']))+'분기. '
                      '보수/기준/낙관은 적격 순수주 대용치의 P25/P50/P75이며 통계적 미래 확률이 아닙니다. '
                      '소진기간은 실제 생산 lead time이 아닙니다. 장납기는 다음 분기, 회전은 같은 분기부터 신규수주를 인식하는 가정입니다.</p>')
        chunks.append('</details>')
        chunks.append('</details>')
    chunks.append('<p><small>FY2026=확인된 H1 흐름+Q3/Q4 추정, FY2027/2028=네 분기 합. '
                  '입력 6분기로 계절조정·장기 오차 보정을 하지 않았습니다. 신규수주 대용치는 취소·환율·범위 변경을 포함할 수 있습니다. '
                  '공시 계약 금액은 잔고에 더하지 않았습니다. 지주·계열 재공시와 다른 통화/부문의 금액은 합산하지 않습니다.</small></p></section>')
    return ''.join(chunks)


def write_sections(root, panel):
    out = root/'sections'
    out.mkdir(exist_ok=True)
    for f in panel['companies']:
        if f['status'] == 'unavailable':
            continue
        fragment = render_forecast_section({'stock': f['stock'], 'name': f['company_name']}, f)
        page = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>'+esc(f['company_name'])+' KGRID 추정</title></head><body style="max-width:1160px;margin:2rem auto;font:15px/1.65 system-ui;padding:0 1rem">'+fragment+'</body></html>\n')
        (out/(f['stock']+'.html')).write_text(page)


def main():
    root = Path(__file__).resolve().parent
    panel = json.loads((root/'forecast_panel.json').read_text())
    write_sections(root, panel)


if __name__ == '__main__':
    main()
