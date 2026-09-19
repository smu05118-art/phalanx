# 주의: 파일명을 `forecast_section.py` 로 두면 섹터 도구가 sys.path 에 얹는 argus/kce/tools 의
# 동명 모듈이 먼저 잡혀 건설 렌더러가 불린다. 탭 접두를 붙인다.
#!/usr/bin/env python3
"""KSEMI company section. Inline SVG/CSS only; no scripts, network, packages.
Compatibility entry: render_forecast_section(panel_entry, forecast_entry=None).
"""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from ksemi_forecast import REASONS, SCENARIOS

LABELS = {'conservative': '보수', 'base': '기준', 'optimistic': '낙관'}
STATUS = {'full': '조건부 전체 납품 대용치', 'partial': '일부 미래 납기 잔고만 추정', 'unavailable': '미추정'}


def esc(x):
    return html.escape(str(x), quote=True)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def fmt(v):
    return f'{v:,.3f}' if number(v) else '—'


def pct(v):
    return f'{v*100:,.2f}%' if number(v) else '—'


def bounds(r):
    b = r.get('interval', {})
    return f"{fmt(b.get('lower'))} ~ {fmt(b.get('upper'))}" if number(b.get('lower')) else '—'


def table(headers, rows, caption):
    return ('<div class="ks-scroll"><table><caption>'+esc(caption)+'</caption><thead><tr>'+
            ''.join('<th scope="col">'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+
            ''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+
            '</tbody></table></div>')


def chart(rows, uid, annual=False, ratio=False):
    label = '일부 잔고의 납기 배분 비율' if ratio else '연간 납품 대용치' if annual else '분기 잔고분·신규수주 가정분'
    groups = []
    for r in rows:
        if ratio:
            parts = [r.get('covered_backlog_fraction_due')]; v = parts[0]; high = v
        else:
            v = r.get('value')
            if number(v):
                parts = ([r.get('observed_revenue', 0)] if annual else []) + [r.get('existing_backlog_revenue'), r.get('new_order_revenue')]
            elif number(r.get('covered_sites_partial_revenue')):
                parts = [r['covered_sites_partial_revenue']]; v = parts[0]
            else:
                parts = []; v = None
            high = (r.get('interval') or {}).get('upper')
        groups.append((r, parts, v, high))
    ymax = max([1e-9]+[x for _, _, v, hi in groups for x in (v, hi) if number(x)])
    step = 740/max(1, len(rows)); colors = ['#64748b', '#2563eb', '#d97706'] if annual else ['#2563eb', '#d97706']
    if ratio: colors = ['#7c3aed']
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 245" role="img" aria-labelledby="{uid}-title {uid}-desc">',
        f'<title id="{uid}-title">{esc(label)}</title><desc id="{uid}-desc">빈칸은 미추정. 파랑은 잔고, 주황은 신규수주 가정, 회색은 관측. 구간은 통계적 신뢰구간이 아닙니다.</desc>',
        '<line x1="75" y1="185" x2="815" y2="185" stroke="currentColor"/>',
        f'<text x="70" y="32" text-anchor="end">{esc(pct(ymax) if ratio else fmt(ymax))}</text>',
        '<text x="65" y="187" text-anchor="end">0</text>']
    for i, (r, parts, v, high) in enumerate(groups):
        x = 75+step*(i+.5); w = min(42, step*.58)
        period = f"FY{r['fiscal_year']}" if annual else r['quarter']
        text = f"{period}: {pct(v) if ratio else fmt(v)}; 민감도 {bounds(r)}"
        chunks.append('<g><title>'+esc(text)+'</title>')
        if not number(v):
            chunks.append(f'<text x="{x}" y="175" text-anchor="middle">—</text>')
        else:
            bottom = 185
            for j, part in enumerate(parts):
                if not number(part): continue
                height = part/ymax*145
                color = colors[j % len(colors)]
                if r.get('value') is None and not ratio: color = '#7c3aed'
                chunks.append(f'<rect x="{x-w/2:.2f}" y="{bottom-height:.2f}" width="{w}" height="{max(0,height):.2f}" fill="{color}"/>')
                bottom -= height
            b = r.get('interval') or {}
            if number(b.get('lower')) and number(b.get('upper')):
                lowy, highy = 185-b['lower']/ymax*145, 185-b['upper']/ymax*145
                chunks.append(f'<path d="M{x},{lowy} V{highy} M{x-5},{lowy} H{x+5} M{x-5},{highy} H{x+5}" stroke="currentColor" fill="none"/>')
        chunks.append(f'<text x="{x}" y="208" text-anchor="middle">{esc(period)}</text></g>')
    chunks.append('</svg>')
    return ''.join(chunks)


CSS = '''<style>
.ks-panel{color:var(--tx,#172033);background:var(--bg,#fff);font:14px/1.65 system-ui,sans-serif;max-width:1200px;margin:24px auto;padding:24px;border:1px solid #94a3b8;border-radius:16px}
.ks-panel h2{margin:0;font-size:24px}.ks-panel h3{font-size:18px;margin-top:24px}.ks-panel p{margin:10px 0}.ks-panel .ks-note{padding:12px;border-left:4px solid #d97706;background:var(--panel,#fffbeb)}
.ks-panel .ks-muted{color:var(--muted,#64748b)}.ks-panel .ks-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.ks-panel .ks-card{border:1px solid #94a3b8;border-radius:9px;padding:12px}
.ks-panel .ks-scroll{overflow:auto}.ks-panel table{border-collapse:collapse;min-width:640px;width:100%;margin:12px 0}.ks-panel caption{text-align:left;font-weight:600}.ks-panel th,.ks-panel td{border-bottom:1px solid #cbd5e1;padding:7px;text-align:right;white-space:nowrap}.ks-panel td:first-child,.ks-panel th:first-child{text-align:left}.ks-panel summary{cursor:pointer;font-weight:600;padding:9px}.ks-panel svg{width:100%;height:auto;min-width:580px}.ks-panel svg text{fill:currentColor;font-size:11px}.ks-panel blockquote{border-left:3px solid #64748b;margin:10px 0;padding:8px 14px}.ks-panel .ks-chip{display:inline-block;padding:2px 8px;border:1px solid #94a3b8;border-radius:12px;margin:3px}
@media(prefers-color-scheme:dark){.ks-panel{--tx:#e2e8f0;--bg:#111827;--panel:#292524;--muted:#94a3b8}}
@media(max-width:600px){.ks-panel{margin:8px;padding:12px}.ks-panel h2{font-size:21px}}
</style>'''


def render_forecast_section(panel_entry, forecast_entry=None):
    c = forecast_entry if forecast_entry is not None else panel_entry
    uid = 'ks-'+hashlib.sha256((str(c['company_id'])+str(c['origin'])).encode()).hexdigest()[:12]
    axes = c['industry_axes']; rec = axes['recognition']; bt = c['backtest']; proc = axes['process']
    unit = '백만원(KRW)' if c.get('money_unit') else '금액 단위 미확정 · 비율만 가능'
    pieces = [CSS, f'<section class="ks-panel" id="{uid}" aria-labelledby="{uid}-heading">',
        f'<h2 id="{uid}-heading">{esc(c["company_name"])} · 분기·연간 전망</h2>',
        f'<p><span class="ks-chip">{esc(STATUS[c["status"]])}</span> 기준 {esc(c["origin"])} · {esc(unit)} · 결산월 {esc(c.get("fiscal_year_end_month") or "미확인")}</p>',
        '<p class="ks-note">수주표 납품액의 조건부 대용치입니다. 회계매출과 연결·별도 범위는 미대조입니다. 전체 추정에는 신규수주 가정이 포함됩니다. 민감도 범위는 <strong>통계적 신뢰구간이 아닙니다(calibrated=false)</strong>. —는 미추정입니다.</p>']
    if c.get('money_unit'):
        pieces.append('<p class="ks-note">백만원 정규화 근거는 2차 보고서 설명에서 승계했습니다. 단위 근거 JSON·원문·파서 소스는 이번 입력에 없습니다(unit_caption_unavailable, unit_contract_inherited). 추가 환산은 하지 않았습니다.</p>')
    review = c.get('ledger_reassessment')
    if review:
        pieces.append('<p class="ks-note">19분기 재판정: 적격 흐름 '+
            str(review['previous_eligible_flow_n'])+' → '+str(review['eligible_flow_n'])+'개 · '+
            esc(review['explanation'])+'</p>')
    shares = [x['basis'] for x in rec['accepted']]
    pieces.append('<div class="ks-grid">')
    h = c['scenarios']['base']['assumptions']['delivery_hazard']
    for title, value in [
        ('인도·설치검수·진행기준', ', '.join(shares) or '적용 기준 미확인'),
        ('정본 공정 단계', ', '.join(proc.get('stage_names', [])) or '배정 파일 미제공'),
        ('전·후공정 / 주단계', (proc.get('front_back') or '미확인')+' / '+(proc.get('primary_name') or '미확인')),
        ('메모리·파운드리 원문 낱말', axes['memory_foundry']['verdict']+' · 매출 비중 아님'),
        ('회전 강도 h / 관측 수', f'{pct(h)} / {len(c["evidence"]["flows"])}개; 실제 리드타임 아님'),
        ('동일 주석 최대 고객 비중', pct(axes['customers']['top_share'])),
        ('수출·내수 매출 비중', '범위·중복 대조 전 미산출'),
        ('중국향 공시 계약 금액 비중', pct(axes['china_contracts']['china_contract_amount_share']))]:
        pieces.append('<div class="ks-card"><strong>'+esc(title)+'</strong><br>'+esc(value)+'</div>')
    pieces.append('</div><p class="ks-muted">단계·메모리 노출·계열 파일은 이번 입력에 없어 판정을 복원하지 않았습니다. 중국 비중은 제공된 누적 계약 기준이며 매출 비중이 아닙니다. 익명 고객 실명과 CAPEX 연동 계수는 추정하지 않습니다.</p>')
    pieces.append('<details><summary>단계·메모리·동종 비교 근거</summary><p>'+esc(proc.get('evidence_text') or '—')+'</p>')
    memory = axes['memory_foundry'].get('row') or {}
    pieces.append('<p>노출 근거 접수번호 '+esc(memory.get('rcpNo') or '—')+' · '+esc(axes['memory_foundry']['basis'])+'</p>')
    for key in ('mem', 'fnd'):
        for quote in memory.get(key, {}).get('quotes', []):
            pieces.append('<blockquote>'+esc(quote)+'</blockquote>')
    peers = axes['peers']
    pieces.append(table(['회사','비교 근거','상태','흐름 표본','h','메모리 판정'], [
        [x['company_name'], ', '.join(x['comparison_basis']), STATUS[x['status']],x['eligible_flow_n'],
         pct(x['delivery_hazard']),x['memory_verdict']] for x in peers['comparisons']],
        '같은 정본 주단계·경쟁 언급 비교; 다른 회사 추정치를 채워 넣지 않음'))
    pieces.append('<p>'+esc(peers['limitation'])+' · 제외 계열 코드: '+esc(', '.join(peers['known_affiliates_excluded']) or '제공 관계 없음')+'</p>')
    for edge in peers['mentions']:
        pieces.append('<blockquote>'+esc(edge['source_stock']+' → '+edge['target_stock']+' ['+edge['kind']+'] '+edge.get('quote',''))+'</blockquote>')
    pieces.append('</details>')
    pieces.append('<details><summary>인식기준 인용과 판정</summary>')
    for v in rec['source_quotes']:
        pieces.append('<blockquote>'+esc(v['quote'])+'</blockquote>')
    pieces.append('<p>'+esc(rec.get('reason') or '수행의무별 인용 확인; 모든 품목에 확대 적용하지 않음')+
                  ' · 접수번호 '+esc(rec.get('source_rcp') or '—')+'</p><p>'+esc(rec['timing_use'])+'</p></details>')
    pieces.append(f'<p class="ks-note">백테스트 표본 {bt["n"]}개: '+
        ('MAE '+fmt(bt['mae'])+' 백만원, WAPE '+pct(bt['wape'])+'. ' if bt['n'] else '채점 가능한 표본이 없습니다. ')+
        '현재 정정본으로 재현한 납품 대용치 점수입니다. 미검증 지평: '+
        esc(', '.join('T+'+str(h) for h in bt['unvalidated_horizons']) or '없음')+
        ' · 연간 검증 '+str(bt['annual']['n'])+'건, WAPE '+pct(bt['annual']['wape'])+'. 중첩 목표는 독립 표본이 아닙니다.</p>')
    pieces.append(table(['지평','n','MAE','WAPE','naive MAE'],
        [['T+'+str(h),str(bt['by_horizon'][str(h)]['n']),fmt(bt['by_horizon'][str(h)]['mae']),
          pct(bt['by_horizon'][str(h)]['wape']),fmt(bt['by_horizon'][str(h)]['naive_mae'])]
         for h in range(1,9)], '기준 시나리오 T+1~T+8 · 백만원 · 현재 정정본을 자른 검증'))
    for name in SCENARIOS:
        s = c['scenarios'][name]; qs = s['quarterly']; annual = s['annual']
        pieces.append('<details'+(' open' if name == 'base' else '')+'><summary>'+LABELS[name]+' 시나리오</summary>')
        pieces.append('<p>분기 순수주 등가 가정 '+fmt(s['assumptions']['new_orders_per_quarter'])+
                      ' 백만원 · 고정 회전 강도 '+pct(s['assumptions']['delivery_hazard'])+'</p>')
        if c['status'] == 'partial':
            pieces.append('<p class="ks-note">유효한 미래 납기행의 잔고만 배분합니다. 신규수주·전체 전망과 납기 오차 구간은 미추정이며 세 시나리오의 납기 배분은 같습니다.</p>')
        pieces.append('<div class="ks-scroll">'+chart(qs, uid+'-'+name)+'</div>')
        pieces.append('<p class="ks-muted">파랑: 기존 잔고분 · 주황: 신규수주 가정분 · 보라: 일부 납기행만 · 회색: 과거 관측분</p>')
        pieces.append(table(['분기','전체','잔고분','신규분','일부 납기분','민감도 범위'],
            [[r['quarter'],fmt(r['value']),fmt(r['existing_backlog_revenue']),fmt(r['new_order_revenue']),
              fmt(r['covered_sites_partial_revenue']),bounds(r)] for r in qs], 'T+1~T+10 · 백만원; 일부 납기분은 전체와 합산하지 않음'))
        pieces.append('<div class="ks-scroll">'+chart(annual, uid+'-'+name+'-annual', annual=True)+'</div>')
        pieces.append(table(['회계연도','전체','과거 관측','미래 잔고분','미래 신규분','일부 납기분','민감도 범위'],
            [[f'FY{r["fiscal_year"]}',fmt(r['value']),fmt(r['observed_revenue']),fmt(r['existing_backlog_revenue']),
              fmt(r['new_order_revenue']),fmt(r['covered_sites_partial_revenue']),bounds(r)] for r in annual],
            'FY2026~FY2028 · 결산 종료 연도로 표기; 과거 관측과 미래 구성 별도'))
        if c['status'] == 'partial':
            ratios = c['normalized_forecast'][name]['quarterly']
            pieces.append('<div class="ks-scroll">'+chart(ratios, uid+'-'+name+'-ratio', ratio=True)+'</div>')
            pieces.append(table(['분기','기준 잔고 대비 일부 납기 배분'],
                [[r['quarter'],pct(r['covered_backlog_fraction_due'])] for r in ratios],
                '통화 환산 없는 비율; 신규수주·SAT·전체 매출을 뜻하지 않음'))
        pieces.append('</details>')
    sched = axes['schedule_table']; schedule_rows = sched.get('rows', [])
    pieces.append('<details><summary>납기표·계통·공정·호기와 장납기 확인 범위</summary>')
    pieces.append('<p>'+esc(axes['system_and_unit_ids']['note'])+
        '. 납기 날짜는 납품 배분에만 쓰며 장비 검수일로 바꾸지 않습니다. 소진이 빠르다는 산업 가정을 모든 회사에 강제하지 않습니다.</p>')
    pieces.append(table(['품목','기재 납기','달력분기'], [[r['name'],r['end'],r['quarter']] for r in schedule_rows],
                         '유효 미래 납기행; 누락·기한 경과·복수 통화 행은 배분 제외'))
    pieces.append('<p>배분 가능 잔고 비중 '+pct(c['coverage']['covered_fraction'])+
        ' · 배분 제외 행 '+str(len(sched.get('rejected', [])))+'개. 전사·부문·통화·계열 간 합계는 만들지 않습니다.</p></details>')
    pieces.append('<details><summary>미추정 사유·범위·회계연도</summary><ul>')
    pieces.extend('<li>'+esc(REASONS.get(code, code))+'</li>' for code in c['reason_codes'])
    pieces.append('</ul><p>'+esc(c['scope'])+'</p><p>'+esc(c['fiscal_evidence']['assumption'])+'</p></details></section>')
    return ''.join(pieces)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', type=Path, default=Path('output/forecast_panel.json'))
    parser.add_argument('--output-dir', type=Path, default=Path('output'))
    parser.add_argument('--all', action='store_true', help='Compatibility flag; render all estimated companies')
    args = parser.parse_args(); panel = json.loads(args.panel.read_text())
    selected = [c for c in panel['companies'] if c['status'] != 'unavailable']
    directory = args.output_dir/'sections'
    directory.mkdir(parents=True, exist_ok=True)
    allowed = {c['company_id']+'.html' for c in selected}
    for stale in directory.glob('*.html'):
        if stale.name not in allowed and stale.stem.isdigit(): stale.unlink()
    for c in selected:
        (directory/(c['company_id']+'.html')).write_text('<!doctype html><html lang="ko"><head><meta charset="utf-8">'+
            '<meta name="viewport" content="width=device-width, initial-scale=1"><title>'+esc(c['company_name'])+
            ' 전망</title></head><body>'+render_forecast_section(c)+'</body></html>')
    (args.output_dir/'forecast_preview.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8">'+
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>KSEMI 전망 검토</title><body>'+
        ''.join(render_forecast_section(c) for c in selected)+'</body></html>')
    print('Rendered %d company sections; inline SVG/CSS; no external assets.' % len(selected))


if __name__ == '__main__':
    main()
