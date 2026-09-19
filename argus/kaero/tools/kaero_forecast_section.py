# 주의: 파일명을 `forecast_section.py` 로 두면 섹터 도구가 sys.path 에 얹는 argus/kce/tools 의
# 동명 모듈이 먼저 잡혀 건설 렌더러가 불린다. 탭 접두를 붙인다.
#!/usr/bin/env python3
"""KAERO company forecast fragments, inline SVG only, standard library.

Integration: render_forecast_section({'stock': code, 'co': name,
                                    'src': 'kaero_reports'}, forecast_entry)
Run: python3 -B output/forecast_section.py
"""
import argparse
import html
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from kaero_forecast import REASONS

LABELS = {"conservative": "보수", "base": "기준", "optimistic": "낙관"}
METHODS = {"program_empirical_burn": "RSP·LTA 최근 납품속도",
           "ledger_empirical_burn": "원장 최근 납품속도", "reported_aggregate_burn": "부문 집계 납품속도",
           "conditional_uniform_remaining_schedule": "잔여 납기 균등 분배 가정", "observed_zero_backlog": "관측 잔고 0"}


def esc(x):
    return html.escape(str(x), quote=True)


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def fmt(v):
    return f"{v:,.6f}".rstrip("0").rstrip(".") if number(v) else "—"


def reason(codes):
    return "; ".join(REASONS.get(x, x) for x in codes) or "추가 금액 차단 사유 없음"


def table(headers, rows, caption):
    return ('<div class="kaero-scroll"><table><caption>' + esc(caption) + '</caption><thead><tr>' +
            ''.join('<th scope="col">' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' +
            ''.join('<tr>' + ''.join(('<th scope="row">' if i == 0 else '<td>') + cell +
                                     ('</th>' if i == 0 else '</td>') for i, cell in enumerate(row)) + '</tr>' for row in rows) +
            '</tbody></table></div>')


def shown(row):
    """Select one disjoint display: total, full existing, or covered subset."""
    if number(row.get("value")):
        return row["value"], row.get("interval", {}), "전체 원장 추정"
    if number(row.get("existing_backlog_revenue")):
        return row["existing_backlog_revenue"], row.get("partial_existing_interval", {}), "미래 잔고분만"
    if number(row.get("covered_sites_partial_revenue")):
        return row["covered_sites_partial_revenue"], row.get("covered_sites_partial_interval", {}), "일부 잔고분만"
    return None, {}, "미추정"


def chart(rows, uid, unit, annual=False):
    maxval = max([1.] + [v for r in rows for v in (shown(r)[0], shown(r)[1].get("upper")) if number(v)])
    left, right, top, baseline = 95, 875, 40, 210
    width = right - left
    step = width / max(1, len(rows))
    def y(v):
        return baseline - v / maxval * (baseline - top)
    labels = [f"FY{r['fiscal_year']}" if annual else r["quarter"] for r in rows]
    descriptions = [f"{label}: 전체 {fmt(r.get('value'))}; 잔고분 {fmt(r.get('existing_backlog_revenue'))}; "
                    f"일부 잔고분 {fmt(r.get('covered_sites_partial_revenue'))}; 신규분 {fmt(r.get('new_order_revenue'))}; {shown(r)[2]}"
                    for label, r in zip(labels, rows)]
    title = "연간 추정·구성" if annual else "분기 추정·구성"
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 260" role="img" aria-labelledby="{uid}-title {uid}-desc">',
             f'<title id="{uid}-title">{esc(title)} ({esc(unit)})</title>',
             f'<desc id="{uid}-desc">{esc(" / ".join(descriptions))}. 민감도 구간; 통계적 신뢰구간 아님.</desc>',
             f'<line x1="{left}" x2="{right}" y1="{baseline}" y2="{baseline}" stroke="currentColor" opacity=".4"/>']
    for v in (0, maxval / 2, maxval):
        parts.append(f'<text x="88" y="{y(v)+4:.3f}" text-anchor="end" font-size="10" fill="currentColor">{v:,.2f}</text>')
    for i, (r, label) in enumerate(zip(rows, labels)):
        value, bounds, basis = shown(r)
        x = left + (i + .5) * step
        bar = min(42, step * .55)
        parts.append(f'<g data-period="{esc(label)}"><title>{esc(descriptions[i])}</title>')
        if number(value):
            chunks = []
            if number(r.get("value")):
                obs = r.get("observed_revenue", 0.) if annual else 0.
                chunks = [(obs, "#94a3b8", "observed"), (r["existing_backlog_revenue"], "#0891b2", "existing"),
                          (r["new_order_revenue"], "#d97706", "new")]
            else:
                chunks = [(value, "#0891b2", "partial-existing")]
            cumulative = 0.
            for amount, color, labelpart in chunks:
                if not number(amount):
                    continue
                parts.append(f'<rect data-part="{labelpart}" x="{x-bar/2:.3f}" y="{y(cumulative+amount):.3f}" width="{bar:.3f}" height="{amount/maxval*(baseline-top):.3f}" fill="{color}"/>')
                cumulative += amount
            if number(bounds.get("lower")) and number(bounds.get("upper")):
                lo, hi = y(bounds["lower"]), y(bounds["upper"])
                parts.append(f'<path data-part="sensitivity" d="M{x:.3f},{lo:.3f}V{hi:.3f} M{x-4:.3f},{lo:.3f}H{x+4:.3f} M{x-4:.3f},{hi:.3f}H{x+4:.3f}" fill="none" stroke="currentColor"/>')
            if not number(r.get("value")):
                parts.append(f'<text x="{x:.3f}" y="25" text-anchor="middle" font-size="10" fill="currentColor">부분</text>')
        else:
            parts.append(f'<text x="{x:.3f}" y="120" text-anchor="middle" font-size="11" fill="currentColor">미추정</text>')
        parts.append(f'<text x="{x:.3f}" y="232" text-anchor="middle" font-size="11" fill="currentColor">{esc(label)}</text></g>')
    parts.append('</svg>')
    return ''.join(parts)


def bounds_text(row):
    _, ci, basis = shown(row)
    if number(ci.get("lower")) and number(ci.get("upper")):
        return f"{fmt(ci['lower'])} ~ {fmt(ci['upper'])} ({basis})"
    return "—"


def render_forecast_section(panel_entry, forecast_entry):
    stock = panel_entry.get("stock")
    name = panel_entry.get("co", panel_entry.get("name"))
    if not isinstance(stock, str) or not re.fullmatch(r"\d{6}", stock):
        raise ValueError("invalid company identifier")
    if forecast_entry is None:
        return f'<section data-forecast-status="unavailable"><h2>{esc(name)} 추정</h2><p>추정 항목 없음.</p></section>'
    c = forecast_entry
    if c.get("company_id") != stock or c.get("company_name") != name or c.get("stock") != stock or c.get("source") != panel_entry.get("src"):
        raise ValueError("company_identity_conflict")
    uid = "kaero-forecast-" + stock
    parts = [f'<section class="kaero-forecast" id="{uid}" data-forecast-status="{esc(c["estimate_status"])}" aria-labelledby="{uid}-heading">',
             f'<h2 id="{uid}-heading">{esc(name)} Y+2 원장 추정</h2>',
             '<p>기준 2026Q2 · T+1~T+10 (2026Q3~2028Q4) · FY2026~FY2028. 12월 결산을 가정하며 결산월은 미확인입니다. 재무제표 매출 전망이 아닌, 항공·우주 원장 범위의 조건부 납품·잔고 소진 추정입니다.</p>',
             '<p data-unit-status="unit_caption_unavailable">금액은 제공된 kce_parse._UNIT_SCALE 정규화 계약에 따른 백만원(KRW), 통화별 백만 단위(USD)입니다. 원본 캡션은 미확인(unit_caption_unavailable)입니다. KRW·USD를 합산하거나 환산하지 않습니다. 환율 가정은 미설정이며 환헤지도 미확인입니다.</p>',
             '<p><strong>민감도 범위이며 통계적 신뢰구간이 아닙니다 (calibrated=false).</strong> —는 근거 부족이며 0이 아닙니다.</p>']
    if c["estimate_status"] != "full":
        parts.append('<p><strong>' + ("부분 추정" if c["estimate_status"] == "partial" else "미추정") + '</strong> · ' + esc(reason(c["reason_codes"])) + '</p>')
    else:
        parts.append('<p>full: 기존 잔고분과 신규수주 가정분을 모두 계산할 수 있습니다. 실제 전사 매출의 완전한 추정을 뜻하지 않습니다.</p>')
    axes = c.get("industry_axes", {})
    domain_labels = [x.get("ko", x.get("id")) for x in axes.get("domain_definitions", [])]
    nature_labels = [x.get("ko", x.get("id")) for x in axes.get("nature_definitions", [])]
    parts.append('<p>영역: ' + esc(' · '.join(domain_labels) or '미상') + ' / 계약 성격: ' +
                 esc(' · '.join(nature_labels) or '미상') + '. 제공 사전의 코드·표시명을 연결했으며 원문 의미 분류를 재확인한 것은 아닙니다.</p>')
    customers = axes.get("customer_hierarchy", [])
    if customers:
        parts.append('<details><summary>OEM·Tier-1·체계업체 고객 근거</summary>' + table(
            ['고객', '계층', '근거', '근거 등급'],
            [[esc(x.get('name')), esc(x.get('tier_label') or '미확인'), esc(x.get('basis')), esc(x.get('grade'))] for x in customers],
            '현재 공급망 입력; 고객별 금액 배분·수주 추정 계수로 사용하지 않음') + '</details>')
    if c.get("needs_longer_ledger"):
        parts.append('<p data-retry-reason="needs_longer_ledger">과거 원장 확장 후 재검증 항목 ' +
                     str(len(c['needs_longer_ledger'])) + '건. 목표 2021Q4~2026Q2 19분기. 적격 표본·동일 부문·계약 식별·단위가 확보돼야 하며 자동으로 추정이 가능해지는 것은 아닙니다.</p>')
    bt = c.get("backtest_summary", {})
    parts.append(f'<p>백테스트 표본이 적습니다: 이 회사 기존분 {bt.get("existing_n", 0)}건, 신규 포함 전체 {bt.get("total_n", 0)}건, 신규 인식이 양수인 전체 표본 {bt.get("nonzero_new_order_revenue_n", 0)}건, FY+2 연간 0건. 최대 6분기 원장이며 같은 계약의 중첩 기간도 포함합니다. 실제 매출·정정 전 공시 빈티지 검증은 아닙니다.</p>')
    for cur, score in bt.get('existing_scores_by_currency', {}).items():
        parts.append(f'<p>{esc(cur)} 기존분 백테스트 WAPE {fmt(score.get("wape") * 100 if number(score.get("wape")) else None)}%. 비교 가능한 {score.get("paired_naive_n", 0)}건의 모델/직전 납품속도 기준 WAPE: {fmt(score.get("paired_model_wape") * 100 if number(score.get("paired_model_wape")) else None)}% / {fmt(score.get("paired_naive_wape") * 100 if number(score.get("paired_naive_wape")) else None)}%.</p>')
    parts.append(table(["산업 축", "확인 범위"], [["선표에 해당하는 인도 일정", "공시 수주일·납기 / 실제 인도 선표 없음"],
                        ["계통·프로그램", "원장 품목·domain·RSP/LTA 문구"], ["공정단계·호기·shipset", "미확인"],
                        ["장납기·회전", "유효 원장 납품 차분 / 날짜 기반 균등 분배 가정"], ["통화·환율", "통화별 분리 / 환율 미설정"]], "우주항공 축과 데이터 한계"))
    if "group_overlap_no_industry_sum" in c.get("warnings", []):
        parts.append('<p><strong>계열 중복:</strong> 한화에어로 원장에 쎄트렉아이 사업이 포함됩니다. 두 회사 추정을 업종 합계로 더하지 않습니다.</p>')
    if "reported_fy_column_stale" in c.get("warnings", []):
        parts.append('<p>입력 매출 연도 열이 과거 연도로 표시돼 있습니다. 해당 연매출·잔고/매출 비율은 추정 계수에 쓰지 않았습니다.</p>')
    if c.get("multi_currency"):
        parts.append('<p>복수 통화 회사입니다. 회사 단일 금액은 미추정으로 유지하며 아래 통화별 패널만 사용합니다.</p>')
    for ch in c.get("currency_panels", []):
        cur = ch["currency"]
        if cur not in {"KRW", "USD"} or ch.get("money_unit") != cur + "_million":
            if ch.get("estimate_status") != "unavailable":
                raise ValueError("unit_currency_unresolved")
            parts.append('<p>단위·통화 미확정 — 금액 표시 보류.</p>')
            continue
        unit = "백만원 (KRW)" if cur == "KRW" else "백만달러 (USD)"
        cov = ch["coverage"]
        parts += [f'<h3>{esc(cur)} · {esc(unit)}</h3>',
                  f'<p>보고 잔고 {fmt(cov["reported_backlog"])} · 모델이 다루는 잔고 {fmt(cov["covered_backlog"])} · 적격 모델 {cov["covered_models"]}/{cov["models"]}. 반올림 전 상세합−보고 잔고 차이: {fmt(cov.get("row_sum_minus_reported_backlog"))}.</p>']
        parts.append('<p>' + esc(reason(ch["reason_codes"])) + '</p>')
        for key, label in LABELS.items():
            s = ch["scenarios"][key]
            a = s["assumptions"]
            parts.append(f'<details data-scenario="{key}" data-currency="{cur}"' + (' open' if key == "base" else '') + f'><summary>{label} 시나리오</summary>')
            parts.append('<p>청록: 기존 잔고분 · 황색: 신규수주 가정분 · 회색: 당해 관측분 · 선: 민감도 범위. 부분 막대는 미래 잔고분만 표시합니다.</p>')
            parts.append(chart(s["quarterly"], uid + '-' + cur + '-' + key + '-q', unit))
            qr = []
            for row in s["quarterly"]:
                e = row["existing_backlog_revenue"]
                text = fmt(e) if number(e) else fmt(row["covered_sites_partial_revenue"]) + " (일부)" if number(row["covered_sites_partial_revenue"]) else "—"
                qr.append([esc(row["quarter"]), fmt(row["value"]), esc(text), fmt(row["new_order_revenue"]), esc(bounds_text(row))])
            parts.append(table(["분기", "전체", "기존 잔고분", "신규분", "민감도 범위"], qr, label + " 분기 구성 · " + unit))
            parts.append(chart(s["annual"], uid + '-' + cur + '-' + key + '-y', unit, annual=True))
            ar = []
            for row in s["annual"]:
                e = row["existing_backlog_revenue"]
                e_text = fmt(e) if number(e) else fmt(row["covered_sites_partial_revenue"]) + " (일부)" if number(row["covered_sites_partial_revenue"]) else "—"
                ar.append([f"FY{row['fiscal_year']}", fmt(row["value"]), fmt(row["observed_revenue"]), esc(e_text),
                           fmt(row["new_order_revenue"]), esc(bounds_text(row)), esc(reason(row["reason_codes"]) if row["value"] is None else "")])
            parts.append(table(["연도", "전체", "관측 원장 Δ납품", "미래 잔고분", "미래 신규분", "민감도 범위", "미추정 사유"], ar, label + " 연간 구성 · " + unit))
            parts.append(f'<p>분기 순수주 가정 {fmt(a.get("new_orders_per_quarter"))} {esc(unit)} · 유효 표본 {a.get("order_samples", 0)}개 · 인식기간 {fmt(a.get("duration_quarters"))}분기. 적격 신규분에 한해 분기말 수주·추가 시차 0분기를 가정하므로 T+1 신규 인식은 0입니다. 신규분 미추정은 0으로 채우지 않습니다. 계절조정은 하지 않습니다.</p>')
            duration_basis = "공시 비RSP 계약기간 중앙값" if a.get("duration_basis", "").startswith("median_disclosed") else "집계 납품률 중앙값의 역수(인식기간 가정)"
            parts.append('<p>인식기간 근거: ' + duration_basis + '. 시나리오 간 기존분·기간·시차는 같고 순수주 P25/P50/P75만 달라집니다. 음수 순수주는 기록에 보존하며 미래 발주에만 0 하한을 적용합니다.</p></details>')
        rows = []
        for m in ch["row_forecasts"]:
            cls = m.get("classification", {})
            rows.append([esc("보고 부문 집계" if m["label"] == "__reported_aggregate__" else m["label"]),
                         esc((cls.get("domain") or {}).get("ko", m.get("domain") or "미상")),
                         esc((cls.get("nature") or {}).get("ko", m.get("nature") or "미상")),
                         esc(m.get("due_raw") or "—"), esc(METHODS.get(m.get("method"), "미추정")),
                         fmt(m["origin_backlog"]), str(len(m.get("samples", []))), esc(reason(m["reason_codes"]))])
        if rows:
            parts.append('<details><summary>품목·계통·장납기 원장과 추정 근거</summary>' +
                         table(["원장 품목", "영역", "계약 성격", "납기 원문", "방법", "잔고", "속도 표본", "사유"], rows, "상세 원장 · " + unit) + '</details>')
        if ch["excluded_rows"]:
            parts.append('<details><summary>부문·식별 문제로 제외한 행</summary>' + table(["행", "사유"],
                         [[esc(r["label"]), esc(REASONS.get(r["reason"], r["reason"]))] for r in ch["excluded_rows"]], "제외 근거") + '</details>')
    parts.append('<p>FY2026은 Q1·Q2 적격 원장 차분 + Q3·Q4 추정입니다. 관측분이 없으면 연간 전체는 미추정입니다. FY2027·FY2028은 네 미래 분기의 합입니다. RSP·LTA는 종료일까지 100% 소진을 강제하지 않습니다. 일정 분배는 공정곡선 실측이 아닙니다. 계약공시 금액은 정기보고서 잔고에 추가하지 않았습니다.</p></section>')
    return ''.join(parts)


STYLE = """<style>
:root{color-scheme:light dark;--bg:#f5f7fa;--fg:#182b3b;--panel:#fff;--line:#cbd5e1}
@media(prefers-color-scheme:dark){:root{--bg:#101a26;--fg:#e2e8f0;--panel:#172537;--line:#40546b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 system-ui,sans-serif}
main{max-width:1280px;margin:auto;padding:24px}.kaero-forecast{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px;margin:24px 0}
h1,h2,h3{line-height:1.3}h3{border-top:2px solid var(--line);padding-top:20px}svg{width:100%;height:auto;display:block}
details{border:1px solid var(--line);border-radius:8px;padding:12px;margin:12px 0}summary{cursor:pointer;font-weight:650}
.kaero-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}th:first-child,td:first-child{text-align:left}
caption{text-align:left;font-weight:650;padding:8px 0}a{color:inherit}@media(max-width:600px){main{padding:8px}.kaero-forecast{padding:12px}}
</style>"""


def document(title, body):
    return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(title) + '</title>' + STYLE + '</head><body><main>' + body + '</main></body></html>\n'


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=root / "forecast_panel.json")
    parser.add_argument("--output-dir", type=Path, default=root)
    args = parser.parse_args()
    panel = json.loads(args.panel.read_text())
    dest = args.output_dir / "sections"
    dest.mkdir(parents=True, exist_ok=True)
    links = []
    for c in panel["companies"]:
        if c["estimate_status"] == "unavailable":
            continue
        content = render_forecast_section({"stock": c["company_id"], "co": c["company_name"], "src": c["source"]}, c)
        (dest / (c["company_id"] + ".html")).write_text(document(c["company_name"] + " 원장 추정", content))
        links.append(f'<li><a href="sections/{c["company_id"]}.html">{esc(c["company_name"])} ({c["estimate_status"]})</a></li>')
    index = '<h1>한국우주항공 Y+2 추정 미리보기</h1><p>20사 전수 · 통화별 분리 · 민감도 범위, 통계적 신뢰구간 아님.</p><ul>' + ''.join(links) + '</ul>'
    (args.output_dir / "forecast_preview.html").write_text(document("KAERO 추정 미리보기", index))
    print(f"rendered {len(links)} estimable company pages; inline SVG only; forecast_preview.html")


if __name__ == "__main__":
    main()
