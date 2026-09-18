# 주의: 파일명을 `forecast_section.py` 로 두면 섹터 도구가 sys.path 에 얹는 argus/kce/tools 의
# 동명 모듈이 먼저 잡혀 건설 렌더러가 불린다(kdef 통합에서 실제로 conflict). 탭 접두를 붙인다.
#!/usr/bin/env python3
"""KNUKE drop-in HTML renderer. Inline SVG/CSS only; no external assets or JS.

API compatible with KCE: render_forecast_section(panel_entry, forecast_entry).
CLI writes output/sections/<stock>.html for companies with monetary estimates.
"""
import argparse
from datetime import date
import html
import json
import math
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True

LABELS = {"conservative": "보수", "base": "기준", "optimistic": "낙관"}
DRIVERS = {
    "equipment_delivery_or_newbuild": "주기기·기자재 / 신규 착공·납기",
    "engineering_contract_schedule": "설계·인허가 / 계약 역무기간",
    "operating_fleet_service_or_replacement": "O&M / 가동호기·계속운전·정비",
    "operating_fleet_replacement_equipment": "교체 기자재 / 가동호기·정비주기",
    "decommissioning_service_schedule": "해체·폐기물 / 개별 용역기간",
    "reported_segment_turnover": "부문 원장 / 관측 납품·회전",
}
METHODS = {"observed_segment_burn": "관측 납품 소진율", "service_term": "서비스 계약기간 균등배분",
           "engineering_term": "설계 역무기간 균등배분", "equipment_term": "납기기간 균등배분 가정",
           "contract_term": "계약기간 균등배분 가정", "zero_backlog_identity": "확인 잔고 0", "unavailable": "미추정"}
CSS = """
.knuke-forecast{--tx:#e6edf5;--pn:#132233;--ln:#38506a;--bg:#091522;--a:#62dbc9;color:var(--tx);background:var(--pn);border:1px solid var(--ln);border-radius:12px;padding:20px;margin:20px auto;font:15px/1.6 system-ui,sans-serif;max-width:1200px}
.knuke-forecast h2,.knuke-forecast h3{line-height:1.3}.knuke-forecast a{color:var(--a)}
.knuke-forecast table{border-collapse:collapse;width:100%;font-size:13px}.knuke-forecast th,.knuke-forecast td{border-bottom:1px solid var(--ln);padding:7px;text-align:left;vertical-align:top}.knuke-forecast caption{text-align:left;padding:10px 0;font-weight:700}
.knuke-forecast .scroll{overflow-x:auto}.knuke-forecast .warning{border-left:4px solid #f1ba72;padding:10px;background:var(--bg)}
.knuke-forecast details{padding:10px 0;border-top:1px solid var(--ln)}.knuke-forecast summary{cursor:pointer;font-weight:700}
.knuke-forecast .badge{border:1px solid var(--a);padding:2px 8px;border-radius:12px;color:var(--a);font-size:12px}
.knuke-forecast small{color:#b3c5d7}.knuke-forecast svg{width:100%;height:auto;min-width:620px;display:block}
@media(prefers-color-scheme:light){.knuke-forecast{--tx:#132233;--pn:#fff;--ln:#bbc9d7;--bg:#eef4f7;--a:#00665b}.knuke-forecast small{color:#435b72}}
"""


def esc(x):
    return html.escape(str(x), quote=True)


def number(x):
    return isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)


def fmt(x):
    return f"{x:,.3f}" if number(x) else "—"


def table(headers, rows, caption):
    return ("<div class='scroll'><table><caption>" + esc(caption) + "</caption><thead><tr>"
            + "".join("<th scope='col'>" + esc(x) + "</th>" for x in headers) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join("<td>" + esc(v) + "</td>" for v in row) + "</tr>" for row in rows)
            + "</tbody></table></div>")


def shown(r):
    if number(r.get("value")):
        return r["value"], r["interval"], "원장 전체 조건부 추정"
    if number(r.get("existing_backlog_revenue")):
        return r["existing_backlog_revenue"], r["partial_existing_interval"], "미래 잔고분만"
    return r.get("covered_sites_partial_revenue"), r.get("covered_sites_partial_interval") or {}, "수록 일부 잔고분만"


def chart(rows, uid, annual=False):
    data = [shown(r) for r in rows]
    mx = max([1.] + [v for v, _, _ in data if number(v)] + [ci["upper"] for _, ci, _ in data if number(ci.get("upper"))])
    left, bottom, height, width = 72, 182, 144, 730
    step = width / max(1, len(rows))
    y = lambda v: bottom - v / mx * height
    chunks = [f"<div class='scroll'><svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 840 226' role='img' aria-labelledby='{uid}-title'>",
              f"<title id='{uid}-title'>분기별 잔고분과 신규분{' 연간 합산' if annual else ''}; 백만원; 미추정은 빈칸</title>",
              f"<line x1='{left}' x2='816' y1='{bottom}' y2='{bottom}' stroke='var(--ln)'/>",
              f"<text x='66' y='42' text-anchor='end' fill='var(--tx)' font-size='11'>{mx:,.0f}</text>",
              f"<text x='66' y='{bottom}' text-anchor='end' fill='var(--tx)' font-size='11'>0</text>"]
    for i, (r, (v, ci, scope)) in enumerate(zip(rows, data)):
        x = left + (i + .5) * step
        label = f"FY{r['fiscal_year']}" if annual else r["quarter"]
        text = f"{label}: 전체 {fmt(r.get('value'))}; 잔고분 {fmt(r.get('existing_backlog_revenue'))}; 일부 잔고분 {fmt(r.get('covered_sites_partial_revenue'))}; 신규분 {fmt(r.get('new_order_revenue'))}; {scope}; 민감도 {fmt(ci.get('lower'))}~{fmt(ci.get('upper'))}"
        chunks.append(f"<g><title>{esc(text)}</title>")
        if number(v):
            parts = [(v, "var(--a)", 1.)]
            if number(r.get("value")):
                parts = [(r["existing_backlog_revenue"], "var(--a)", 1.), (r["new_order_revenue"], "var(--tx)", .5)]
                if annual:
                    parts.insert(0, (r.get("observed_revenue", 0), "#86a7dc", .7))
            offset = 0
            for amount, color, opacity in parts:
                if not number(amount):
                    continue
                chunks.append(f"<rect x='{x-17:.3f}' y='{y(offset+amount):.3f}' width='34' height='{amount/mx*height:.3f}' fill='{color}' fill-opacity='{opacity}'/>")
                offset += amount
            if number(ci.get("lower")) and number(ci.get("upper")):
                chunks.append(f"<path d='M{x:.3f},{y(ci['lower']):.3f}V{y(ci['upper']):.3f} M{x-4:.3f},{y(ci['lower']):.3f}H{x+4:.3f} M{x-4:.3f},{y(ci['upper']):.3f}H{x+4:.3f}' stroke='var(--tx)' fill='none'/>")
            if not number(r.get("value")):
                chunks.append(f"<text x='{x:.3f}' y='21' text-anchor='middle' fill='var(--tx)' font-size='10'>잔고분만</text>")
        else:
            chunks.append(f"<text x='{x:.3f}' y='106' text-anchor='middle' fill='var(--tx)' font-size='11'>미추정</text>")
        chunks.append(f"<text x='{x:.3f}' y='205' text-anchor='middle' fill='var(--tx)' font-size='10'>{esc(label)}</text></g>")
    return "".join(chunks) + "</svg></div>"


def timeline(rows, uid):
    valid = [r for r in rows if r.get("start") and r.get("end") and not r.get("grouped")]
    if not valid:
        return "<p>개별 계약·호기 선표를 그릴 정확한 기간이 없습니다. 묶음 대표기간은 아래 원장 표에 별도로 남겼습니다.</p>"
    start = min(date.fromisoformat(r["start"]) for r in valid)
    end = max(date.fromisoformat(r["end"]) for r in valid)
    span = max(1, (end - start).days)
    x = lambda d: 310 + 670 * (d - start).days / span
    h = 75 + len(valid) * 26
    chunks = [f"<div class='scroll'><svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1010 {h}' role='img' aria-labelledby='{uid}-title'>",
              f"<title id='{uid}-title'>개별 계약 역무·납기 선표. 상업운전일·실제 공정률 선표가 아닙니다.</title>"]
    for yr in range(start.year, end.year + 1):
        pos = x(max(start, date(yr, 1, 1)))
        chunks.append(f"<line x1='{pos:.2f}' x2='{pos:.2f}' y1='30' y2='{h-18}' stroke='var(--ln)'/><text x='{pos:.2f}' y='20' font-size='10' fill='var(--tx)'>{yr}</text>")
    for i, r in enumerate(valid):
        label = r.get("name") or r.get("label") or "행"
        yy = 44 + i * 26
        a, b = date.fromisoformat(r["start"]), date.fromisoformat(r["end"])
        title = f"{label} / {r.get('client') or '발주처 미상'} / {a}~{b} / {METHODS.get(r['method'], r['method'])}"
        chunks.append(f"<g><title>{esc(title)}</title><text x='4' y='{yy+4}' font-size='10' fill='var(--tx)'>{esc(label[:28])}</text><rect x='{x(a):.3f}' y='{yy-6}' width='{max(1, x(b)-x(a)):.3f}' height='12' rx='3' fill='var(--a)'/></g>")
    return "".join(chunks) + "</svg></div>"


def render_forecast_section(panel_entry, forecast_entry):
    stock = panel_entry.get("stock")
    name = panel_entry.get("co") or panel_entry.get("name") or "회사"
    if not isinstance(stock, str) or not re.fullmatch(r"\d{6}", stock):
        raise ValueError("invalid stock identity")
    if forecast_entry is None:
        return f"<p>{esc(name)} — 추정 항목 없음.</p>"
    c = forecast_entry
    if c.get("stock") != stock or c.get("company_id") != stock or c.get("company_name") != name:
        raise ValueError("company_identity_conflict")
    source = panel_entry.get("src") or panel_entry.get("source")
    if source is not None and source != c.get("source"):
        raise ValueError("source_identity_conflict")
    if c.get("money_unit") not in (None, "KRW_million"):
        raise ValueError("unsupported money unit")
    if c.get("money_unit") is None:
        for s in c["scenarios"].values():
            for row in s["quarterly"] + s["annual"]:
                if any(number(row.get(k)) for k in ("value", "existing_backlog_revenue", "covered_sites_partial_revenue", "new_order_revenue")):
                    raise ValueError("unverified_money_in_panel")
    uid = "knuke-forecast-" + stock
    status = {"full": "원장 전체 조건부 추정", "partial": "원장 일부 구성 추정", "unavailable": "금액 미추정"}[c["status"]]
    chunks = ["<style>" + CSS + "</style>", f"<section class='knuke-forecast' id='{uid}' data-forecast-status='{c['status']}'>",
              f"<h2>{esc(name)} Y+2 추정 <span class='badge'>{status}</span></h2>",
              f"<p>기준 {esc(c['origin'])} · T+1~T+10 · FY2026~FY2028 · 12월 결산 가정(미검증). 금액 표시 단위: 백만원. 표 통화: {esc(c['unit_audit'].get('currency') or c['unit_audit'].get('latest_available_currency') or '미확인')}.</p>",
              "<p class='warning'>제공 수주 원장 범위의 납품·역무 인식 대용치입니다. 회사 전체 회계매출 또는 순수 원전 매출과 같지 않습니다. —는 미추정이며 0이 아닙니다. 민감도 범위는 통계적 신뢰구간이 아니며 calibrated=false입니다.</p>",
              f"<p>원장 범위: {esc(c['scope'])}. 배분 가능 행 {c['coverage']['modeled_rows']}/{c['coverage']['current_rows']}. 회사·분기 캡션: {esc(' / '.join(c['unit_audit'].get('raw_unit_captions', [])) or '없음')}. 제공 캡션과 백만원 정규화 계약에 조건부 의존합니다. 표 위치·HTML 대응은 미검증이며 입력 금액을 재배율하지 않습니다.</p>",
              "<details open><summary>판정 이유·막는 것</summary><ul>" + "".join("<li>" + esc(x) + "</li>" for x in c["audit_blockers"]) + "</ul><p>해석 한계</p><ul>" + "".join("<li>" + esc(x) + "</li>" for x in c.get("limitations", [])) + "</ul></details>"]
    bt = c.get("backtest", {})
    chunks.append(table(["대상", "금액 표본 n", "MAE 백만원", "WAPE %"],
                        [[label, bt.get(key, {}).get("n", 0), fmt(bt.get(key, {}).get("mae")), fmt(bt.get(key, {}).get("wape_pct"))]
                         for key, label in (("existing_contract", "동일 계약 잔고분"), ("total_ledger", "신규분 포함 원장 전체"))], "백테스트: 이 회사의 실측 대용치 표본"))
    empty_horizons = ["T+" + h for h, v in bt.get("by_horizon", {}).items()
                      if not v["existing_contract"]["n"] and not v["total_ledger"]["n"]]
    chunks.append("<p class='warning'>" + esc(bt.get("warning") or "백테스트 자료 없음")
                  + " 금액 검증 표본 0인 지평: " + esc(", ".join(empty_horizons) or "없음")
                  + ". 적은 표본을 장기 정확도로 해석하지 않습니다.</p>")
    retry = c.get("retry", {})
    if retry.get("needs_longer_ledger"):
        chunks.append("<p class='warning'>needs_longer_ledger: 적격 신규수주 표본 "
                      + esc(retry.get("eligible_new_order_sample_count")) + "/4. 2021Q4~2026Q2 원장 확장 후 재검사. "
                      + esc(retry.get("acceptance")) + " 추가 조건: "
                      + esc(", ".join(retry.get("non_length_prerequisites", [])) or "적격 표본 확보") + "</p>")
    for key, label in LABELS.items():
        s = c["scenarios"][key]
        premise = (f"신규수주 표본 P{int({'conservative':.25,'base':.5,'optimistic':.75}[key]*100)} 가정"
                   if s["assumptions"]["order_models"] else "신규분 미추정 · 잔고분 공통 경로")
        chunks.append(f"<details data-scenario='{key}'{' open' if key == 'base' else ''}><summary>{label} · {premise}</summary>")
        chunks.append("<p>청록: 미래 잔고분 · 회색: 신규수주 가정분 · 파랑: 과거 관측분 · 세로선: 민감도 범위. 전체가 미추정이면 알려진 잔고분만 표시합니다.</p>")
        chunks.append(chart(s["quarterly"], uid + "-" + key + "-q"))
        rows = []
        for r in s["quarterly"]:
            _, ci, scope = shown(r)
            rows.append([r["quarter"], fmt(r["value"]), fmt(r["existing_backlog_revenue"]),
                         fmt(r["covered_sites_partial_revenue"]), fmt(r["new_order_revenue"]),
                         f"{fmt(ci.get('lower'))}~{fmt(ci.get('upper'))} ({scope})"])
        chunks.append(table(["분기", "원장 전체", "전체 잔고분", "배분 가능 잔고분", "신규분", "민감도 범위"], rows, label + " 분기 구성 · 백만원"))
        chunks.append(chart(s["annual"], uid + "-" + key + "-y", True))
        rows = []
        for r in s["annual"]:
            _, ci, scope = shown(r)
            rows.append([f"FY{r['fiscal_year']}", fmt(r["value"]), fmt(r["observed_revenue"]),
                         fmt(r["existing_backlog_revenue"]), fmt(r["covered_sites_partial_revenue"]),
                         fmt(r["new_order_revenue"]), f"{fmt(ci.get('lower'))}~{fmt(ci.get('upper'))}",
                         "완비" if r["complete"] else "미추정: " + (r.get("reason") or scope)])
        chunks.append(table(["연도", "원장 전체", "관측분", "미래 전체 잔고분", "미래 배분 가능분", "신규분", "민감도", "완비 여부·사유"], rows, label + " 연간 구성 · 백만원"))
        chunks.append("<p><small>분기 신규수주 가정 " + fmt(s["assumptions"].get("new_orders_per_quarter_deseasonalized"))
                      + "백만원. 안정된 품목·부문 원장만 O=ΔB+R의 분위수를 사용합니다. 실제 착공시차·공기 미식별 시 임의 값을 채우지 않습니다. 수주 분기말 유입, 다음 분기부터 같은 부문 관측 소진율로 전환한다는 조건부 가정입니다. 날짜 계약은 잔여기간 균등배분, 민감도 지수 0.75/1/1.25. 세 시나리오의 인식 속도는 동일합니다.</small></p></details>")
    chunks.append("<h3>호기·계통·역무 선표</h3><p>계약명에서 확인되는 업무·호기만 표시합니다. 실제 공정단계와 가동 호기 수, 계속운전 승인·정비주기는 입력에 없어 미확인입니다. 계약기간은 실제 착공일·상업운전일과 다를 수 있습니다.</p>")
    chunks.append(timeline(c["row_forecasts"], uid + "-timeline"))
    rows = []
    for r in c["row_forecasts"]:
        ax = r["axes"]
        rows.append([r.get("name") or r.get("label") or "—", r.get("client") or "—",
                     DRIVERS.get(ax["driver"], ax["driver"]), ", ".join(ax["system_tags"] + ax["unit_mentions"]) or "미확인",
                     {"export": "수출", "domestic": "국내", "unknown": "미상"}[ax["region"]],
                     ("묶음 대표기간: " if r["grouped"] else "") + str(r.get("start_raw") or "—") + " → " + str(r.get("end_raw") or "—"),
                     (r.get("start") or "—") + " → " + (r.get("end") or "—"),
                     fmt(r.get("backlog")), fmt(100*r["progress"]) + "%" if number(r.get("progress")) else "—",
                     METHODS[r["method"]], "; ".join(r["reason_codes"]) or "—"])
    chunks.append(table(["사업·품목", "발주처", "수요 축", "계통·호기", "지역", "원시 기간", "배분 기간", "잔고 백만원", "현재 누계/A", "추정법", "행 판정 코드"], rows, "보존행 전수: 현재 비율은 미래 예측과 구분"))
    timing = c["evidence"]["timing"]
    chunks.append(table(["공급계층:지역", "n", "계약기간 중앙값(분기)", "최소~최대"],
                        [[k, v["n"], fmt(v["median_quarters"]), f"{fmt(v['min_quarters'])}~{fmt(v['max_quarters'])}"] for k, v in timing["by_tier_region"].items()],
                        "장납기·회전 참고: 당시 공시가 확인되는 계약만, 잔고·신규수주에 더하지 않음"))
    chunks.append("<p><small>" + esc(timing["limitation"]) + " 국내·수출은 별도 표시하며, 연결할 지역별 원장이 없으면 계약 건수로 가중 배분하지 않습니다. FY2026은 Q1·Q2 관측 + Q3·Q4 추정, FY2027·FY2028은 네 분기 추정 합입니다. 신규분 또는 관측분이 없으면 연간 전체도 —입니다. 원청·하청 중복을 제거할 수 없어 회사 합을 산업 규모로 합산하지 않습니다.</small></p></section>")
    return "".join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent
    parser.add_argument("--panel", type=Path, default=root / "forecast_panel.json")
    parser.add_argument("--output-dir", type=Path, default=root / "sections")
    args = parser.parse_args()
    panel = json.loads(args.panel.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    links = []
    for c in panel["companies"]:
        if c["status"] == "unavailable":
            (args.output_dir / (c["stock"] + ".html")).unlink(missing_ok=True)
            continue
        body = render_forecast_section({"stock": c["stock"], "co": c["company_name"], "src": c["source"]}, c)
        page = "<!doctype html><html lang='ko'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>" + esc(c["company_name"]) + " 원장 추정</title><body style='margin:0;background:#091522'>" + body + "</body></html>"
        (args.output_dir / (c["stock"] + ".html")).write_text(page, encoding="utf-8")
        links.append(f"<li><a href='{c['stock']}.html'>{esc(c['company_name'])} · {c['status']}</a></li>")
    print(f"Rendered {len(links)} estimated company pages: {args.output_dir}")


if __name__ == "__main__":
    main()
