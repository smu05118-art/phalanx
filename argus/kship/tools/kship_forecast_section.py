# 주의: 파일명을 `forecast_section.py` 로 두면 섹터 도구가 sys.path 에 얹는 argus/kce/tools 의
# 동명 모듈이 먼저 잡혀 건설 렌더러가 불린다(kdef 통합에서 실제로 conflict 가 났다). 탭 접두를 붙인다.
#!/usr/bin/env python3
"""KSHIP company section. Inline SVG, no network, packages, JavaScript or CDN.

Integration: render_forecast_section({'stock': code, 'co': name,
                                    'src': 'kship_universe'}, forecast_entry).
Also accepts the supplied universe row (stock/name) without a src field.
"""
import argparse
import collections
import html
import json
import math
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
from kship_forecast import REASONS, SCENARIOS

LABELS = {"conservative": "보수", "base": "기준", "optimistic": "낙관"}


def esc(value):
    return html.escape(str(value), quote=True)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fmt(value):
    return f"{value:,.3f}" if number(value) else "—"


def reasons(codes):
    return "; ".join(REASONS.get(c, c) for c in codes) or "없음"


def bounds(row):
    b = row.get("interval", {})
    return f"{fmt(b.get('lower'))} ~ {fmt(b.get('upper'))}" if number(b.get("lower")) and number(b.get("upper")) else "—"


def table(headers, rows, caption):
    return ('<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%">'
            '<caption style="text-align:left;padding:.6rem 0">' + esc(caption) + '</caption><thead><tr>'
            + ''.join('<th scope="col" style="text-align:left;padding:.35rem">' + esc(h) + '</th>' for h in headers)
            + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(('<th scope="row"' if i == 0 else '<td')
                                      + ' style="text-align:left;padding:.35rem;border-top:1px solid var(--ln,#667085)">'
                                      + esc(v) + ('</th>' if i == 0 else '</td>')
                                      for i, v in enumerate(row)) + '</tr>' for row in rows)
            + '</tbody></table></div>')


def chart(rows, uid, annual=False):
    """No zero-height bars for null. Only complete company totals are stacked."""
    def label(r):
        return 'FY' + str(r['fiscal_year']) if annual else r['quarter']
    vals = [r.get("value") for r in rows]
    upper = max([1.0] + [v for v in vals if number(v)]
                + [r["interval"]["upper"] for r in rows if number(r.get("interval", {}).get("upper"))])
    lower = min([0.0] + [v for v in vals if number(v)]
                + [r["interval"]["lower"] for r in rows if number(r.get("interval", {}).get("lower"))])
    def y(v):
        return 170 - (v - lower) / (upper - lower) * 135
    desc = ' / '.join(f"{label(r)} 전체 {fmt(r.get('value'))}; 잔고 {fmt(r.get('existing_backlog_revenue'))}; "
                      f"신규 {fmt(r.get('new_order_revenue'))}; 민감도 {bounds(r)}" for r in rows)
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 220" role="img" '
              f'aria-labelledby="{uid}-title {uid}-desc" style="width:100%;height:auto">',
              f'<title id="{uid}-title">원장 매출 대용치 · 백만원</title>',
              f'<desc id="{uid}-desc">{esc(desc)}</desc>',
              f'<line x1="65" x2="820" y1="{y(0):.2f}" y2="{y(0):.2f}" stroke="currentColor"/>']
    step = 750 / max(1, len(rows))
    for i, r in enumerate(rows):
        x, v = 65 + (i + .5) * step, r.get("value")
        chunks.append(f'<g data-period="{esc(label(r))}"><title>{esc(label(r))}: {esc(fmt(v))}</title>')
        if not number(v):
            chunks.append(f'<text x="{x:.2f}" y="108" text-anchor="middle" fill="currentColor" font-size="12">미추정</text>')
        else:
            if annual:
                parts = [("annual", v, 0, "var(--a,#4b96ed)")]
            else:
                e, n = r.get("existing_backlog_revenue"), r.get("new_order_revenue")
                if not number(e) or not number(n):
                    raise ValueError("total exists with missing component")
                parts = [("existing", e, 0, "var(--a,#4b96ed)"),
                         ("new", n, e, "var(--tx,#84adad)")]
            for key, value, offset, color in parts:
                a, b = y(offset), y(offset + value)
                chunks.append(f'<rect data-part="{key}" x="{x-17:.2f}" y="{min(a,b):.2f}" width="34" '
                              f'height="{abs(a-b):.2f}" fill="{color}"/>')
            ci = r.get("interval", {})
            if number(ci.get("lower")) and number(ci.get("upper")):
                a, b = y(ci["lower"]), y(ci["upper"])
                chunks.append(f'<path data-part="sensitivity" d="M{x:.2f},{a:.2f}V{b:.2f} '
                              f'M{x-4:.2f},{a:.2f}H{x+4:.2f} M{x-4:.2f},{b:.2f}H{x+4:.2f}" '
                              'stroke="currentColor" fill="none"/>')
        chunks.append(f'<text x="{x:.2f}" y="197" text-anchor="middle" fill="currentColor" font-size="10">'
                      f'{esc(label(r))}</text></g>')
    chunks.append('</svg>')
    return ''.join(chunks)


def render_forecast_section(panel_entry, forecast_entry):
    stock=panel_entry.get('stock'); name=panel_entry.get('co',panel_entry.get('name'))
    if not isinstance(stock,str) or not re.fullmatch(r'\d{6}',stock): raise ValueError('invalid stock identifier')
    if forecast_entry is None: return '<p data-forecast-status="unavailable">미추정: 원장 없음.</p>'
    c=forecast_entry
    if c.get('stock')!=stock or c.get('company_id')!=stock or c.get('company_name')!=name:
        raise ValueError('company_identity_conflict')
    if 'src' in panel_entry and panel_entry['src']!=c['source']: raise ValueError('company_identity_conflict')
    if c.get('money_unit')!='KRW_million': raise ValueError('unexpected output unit')
    if c.get('status') not in ('full','partial','unavailable'): raise ValueError('unknown status')
    uid='kship-forecast-'+stock; cov=c['coverage']; axes=c['industry_axes']; fx=axes['fx']
    chunks=[f'<section id="{uid}" data-forecast-status="{esc(c["status"])}" lang="ko" style="font:15px/1.65 system-ui,sans-serif;color:var(--tx,#17212b);background:var(--pn,#f7fafc);padding:1rem;max-width:1280px;margin:auto">',
      f'<h2>{esc(name)} · 2026Q3–2028Q4 추정</h2>',
      '<p><strong>진행기준이므로 인도 분기 ≠ 매출 분기.</strong> 선표 종료일은 계약의 마지막 호선 인도 예정입니다. '
      '아래 수치는 보고된 원화 장부액 기준 인식 대용치이며, 회사 회계매출 전망으로 인증한 값이 아닙니다.</p>',
      f'<p>기준 {esc(c["origin"])} · 금액 백만원 · 상태 {esc(c["status"])}. '
      '민감도 구간은 <strong>통계적 신뢰구간이 아닙니다 (calibrated=false)</strong>. —는 미상이며 0이 아닙니다.</p>',
      f'<p>계산 부문: {esc(", ".join(cov["modeled_segments"]) or "없음")} / 제외 부문: '
      f'{esc(", ".join(cov["excluded_segments"]) or "없음")}. '
      f'현재 원장 부문 잔고 {fmt(cov["reported_backlog"])} / 계산 범위 잔고 {fmt(cov["modeled_backlog"])}.</p>',
      '<p>회사전체/조선부문·연결제거 범위가 확인되지 않았습니다. 지주와 자회사 또는 회사간 합산은 금지합니다.</p>',
      f'<p>한계: {esc(reasons(c["reason_codes"]))}</p>',
      f'<p><strong>분기 백테스트 {c["backtest"]["quarterly_n"]}개.</strong> {esc(c["backtest"]["sample_warning"])}</p>',
      '<h3>환 · 헤지</h3>',
      '<p>수주의 USD 경제노출과 KRW 매출은 구분합니다. 미래 환율은 미상이며 이미 보고된 KRW 장부액을 재환산하지 않습니다. '
      'FX 시나리오·환위험 구간은 산출하지 않았습니다. USD 매도 명목액은 헤지비율이 아니며 약정환율은 미래 현물환율이 아닙니다.</p>',
      table(['입력 USD 매도 명목액(백만USD)','입력 USD 매입 명목액(백만USD)','공시 약정환율(원/USD)','환 표 통화','미래 환율 / 유효 헤지비율'],
            [[fmt(fx['usd_sell_m_reported']),fmt(fx['usd_buy_m_reported']),fmt(fx['hedge_avg_rate_reported_krw_per_usd']),fx['fx_table_currency'] or '—','— / —']],
            '입력 집계를 그대로 보존; 당기/전기·목적별 중복 합계는 원문에서 독립 검증하지 못함'),
      f'<p>{esc(fx.get("fx_parse_warning",fx["warning"]))}</p>',
      table(['USD열 항목','원화 표시액(백만원)'],
            [[label,fmt(value)] for label,value in fx['usd_exposure_column_krw_million'].items()],
            'fx 표의 USD 경제노출 열 · USD 명목액이나 환율이 아님 · 빈 표는 확인 불가'),
      '<h3>원장 · 선표 근거</h3>']
    hist=[]
    for s in c['audit']['snapshots']:
        totals={r['field']:r for r in s['reconciliations']}
        hist.append([s['quarter'],s['raw_unit_caption'],fmt(totals['closing']['reported_total']),fmt(totals['closing']['leaf_sum']),
                     fmt(totals['delivered']['leaf_sum']),fmt(s['revenue_audit']['reported_grand_ytd']),
                     '; '.join(r['segment_id']+': '+fmt(r['rollforward_residual']) for r in s['rows'])])
    chunks.append(table(['분기','원문 단위(재환산 안 함)','입력 기말 합계','부문 기말합','부문 누적 기납품','별도 보고 매출 YTD','기초+신규−기납품−기말'],hist,
                        '금액 백만원 · 누적 기납품과 매출은 별개 · 회사 원문 합계를 덮어쓰지 않음'))
    grouped=collections.defaultdict(lambda:[0,0])
    for r in axes['schedule']:
        k=(r['quarter'],r['type']); grouped[k][0]+=1;grouped[k][1]+=r['units']
    chunks.append(table(['마지막 인도 예정 분기','선종','계약 건수','계약 척/기 수'],
                        [[q,t,*v] for (q,t),v in sorted(grouped.items())],
                        '기준분기말까지 접수된 유효 미인도 계약 · 모든 호선이 마지막 분기에 인도된다는 뜻 아님'))
    chunks.append('<p>선표는 금액이 아닌 척수로 가중합니다. 선종→부문 매핑과 공정곡선은 추정이며 금액 커버리지는 미상입니다. '
                  '관측 소진율과 선표 곡선을 50:50으로 혼합하고, 선표가 없는 부문은 관측 소진율만 씁니다.</p>')
    for key,label in LABELS.items():
        s=c['scenarios'][key];a=s['assumptions']
        chunks.append(f'<details data-scenario="{key}"'+(' open' if key=='base' else '')+f'><summary>{label} 시나리오</summary>')
        chunks.append(f'<p>순유입 Q{a["order_quantile"]*100:g}의 양수 부분으로 신규 코호트를 가정합니다. '
                      '순유입은 취소·환산 등이 미분리된 대용치로 달러 신규수주가 아닙니다. '
                      '분기말 신규 유입은 다음 분기부터 인식하므로 T+1 신규분 0은 모델 구조입니다. 미래 환율은 가정하지 않습니다.</p>')
        # The chart always has a clear covered-scope label; null scope total stays null in data/table.
        visual=[{**r,'value':r['covered_scope_value'],'existing_backlog_revenue':r['covered_sites_partial_revenue'],
                 'new_order_revenue':r['covered_scope_new_revenue'],'interval':r['covered_scope_interval']} for r in s['quarterly']]
        chunks.append('<p>그림: 계산 가능한 부문의 잔고분(파랑) + 신규분(보조색), 검은 선은 민감도 범위. 제외 부문은 포함하지 않습니다.</p>')
        chunks.append(chart(visual,uid+'-'+key))
        chunks.append(table(['분기','원장 전범위 합','계산 범위 잔고분','계산 범위 신규분','계산 범위 합','계산 범위 민감도','남은 기존잔고'],
                            [[r['quarter'],fmt(r['value']),fmt(r['covered_sites_partial_revenue']),fmt(r['covered_scope_new_revenue']),
                              fmt(r['covered_scope_value']),bounds({'interval':r['covered_scope_interval']}),fmt(r['remaining_existing_backlog'])]
                             for r in s['quarterly']],label+' 분기 · 백만원'))
        chunks.append(table(['연도','원장 전범위 합','과거 관측 대용치','미래 잔고분(전범위)','미래 신규분(전범위)','계산 범위 미래합','전범위 민감도','계산 범위 미래합 민감도'],
                            [['FY'+str(r['fiscal_year']),fmt(r['value']),fmt(r['observed_revenue']),fmt(r['existing_backlog_revenue']),
                              fmt(r['new_order_revenue']),fmt(r['covered_future_value']),bounds(r),bounds({'interval':r['covered_future_interval']})] for r in s['annual']],
                            label+' 연간 · 백만원 · 미래합은 과거 관측을 포함하지 않음'))
        chunks.append('</details>')
    chunks.append('<p><small>FY2026는 Q1·Q2 관측 대용치와 Q3·Q4 추정, FY2027·FY2028은 네 분기 추정 합입니다. '
                  '과거 관측이나 부문 하나라도 빠지면 전범위 합은 —입니다. 미래연도 관측 0은 필요한 과거 분기가 없다는 뜻입니다. '
                  '135개 민감도 경로는 공정·소진·신규 순유입 가정의 범위이며 환율·누락 부문·연결제거 위험을 포괄하지 않습니다.</small></p></section>')
    return ''.join(chunks)


def main():
    root=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel',type=Path,default=root/'forecast_panel.json')
    parser.add_argument('--output',type=Path,default=root/'sections')
    args=parser.parse_args();panel=json.loads(args.panel.read_text());args.output.mkdir(parents=True,exist_ok=True)
    count=0
    for c in panel['companies']:
        if c['status']=='unavailable':continue
        fragment=render_forecast_section({'stock':c['stock'],'co':c['company_name'],'src':c['source']},c)
        (args.output/(c['stock']+'.html')).write_text(fragment+'\n');count+=1
    print(f'Rendered {count} eligible company sections; reused R1 inline SVG/table; offline.')

if __name__=='__main__':main()
