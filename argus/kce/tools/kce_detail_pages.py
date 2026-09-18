#!/usr/bin/env python3
"""Offline KCE detail candidates. Python standard library only.

Public builders return HTML or None (denied / insufficient evidence). They never
write. build_all writes pages, status.html and manifest.json under output/ only.
Audit is mandatory: pass audit=the loaded grade_audit.json, or use the sibling
../input/grade_audit.json. No network, input imports, credentials or interpolation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import html
import json
import math
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
INPUT = ROOT.parent / "input"
PAGES = {"matrix": "분기매출 후보", "trace": "원문 배치 추적", "backtest": "성적표 후보"}
E = html.escape

# Values copied from kce_page.CSS, sct_matrix and sct_trace. No vendor required.
CSS = """
:root{--bg:#0f1116;--pn:#171a21;--pn2:#1e222b;--ln:#2a2f3a;--tx:#e6e8ec;--tx2:#98a1b0;
--tx3:#5d6675;--a:#60a5fa;--up:#4ade80;--dn:#f87171;--wn:#fbbf24;
--sep:#22c55e;--pr:#f59e0b;--fc:#f472b6;--mn:#22d3ee;--fe:#c084fc;--cmp:#3b82f6;--xi:#8b5cf6;
--c2:#60a5fa;--c3:#10b981;--c3b:#0c8a62;--c11:#8b5cf6;--empty:#252a34}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font:13px/1.6 -apple-system,"Segoe UI","Malgun Gothic",sans-serif;padding-bottom:40px}
a{color:var(--a)}header{padding:12px clamp(12px,3vw,28px);border-bottom:1px solid var(--ln);background:var(--pn)}
.hd{display:flex;gap:12px;align-items:center;flex-wrap:wrap}h1{font-size:17px;font-weight:600;letter-spacing:-.3px}
.tag,.cid{font-size:11px;color:var(--tx2)}nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
nav a,button{border:1px solid var(--ln);border-radius:6px;padding:3px 9px;background:var(--pn2);color:var(--a);font:inherit}
nav a{text-decoration:none}main{max-width:1600px;margin:auto;padding:18px clamp(12px,3vw,28px)}
section{margin-top:18px;background:var(--pn);border:1px solid var(--ln);border-radius:10px;padding:14px 16px;min-width:0}
h2{font-size:13px;color:var(--tx2);margin-bottom:10px}p{margin:6px 0}.note{color:var(--wn);font-size:12px;background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.25);border-radius:7px;padding:8px 11px;margin:12px 0}
.mut,.na{color:var(--tx3)}.footnote{color:var(--tx2);font-size:12px;margin-top:10px}.dn{color:var(--dn)}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi div{background:var(--pn);border:1px solid var(--ln);border-radius:9px;padding:12px 14px}.kpi b{display:block;font-size:19px;font-weight:600}.kpi span{font-size:11px;color:var(--tx2)}
.wrap{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}.wide{width:max-content;min-width:100%}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:12px;font-variant-numeric:tabular-nums}
th,td{padding:5px 8px;border-bottom:1px solid var(--ln);text-align:right;white-space:nowrap}
th{color:var(--tx2);font-weight:500;font-size:11px;position:sticky;top:0;background:var(--pn);z-index:2}
.lbl,.l{text-align:left}.lbl{min-width:235px;max-width:330px;white-space:normal;position:sticky;left:0;background:var(--pn);z-index:1}
thead .lbl{z-index:3}td:not(.lbl){min-width:78px}.grp td{background:var(--pn2);color:var(--tx);font-weight:600}.agg .lbl{color:var(--wn)}
.yb{border-left:1px solid var(--ln)}tbody tr:hover td{background:var(--pn2)}
td.fl{outline:1px dashed var(--sep);outline-offset:-2px}td.fli{outline:1px dashed var(--pr);outline-offset:-2px}
td.flx{outline:1px dashed var(--xi);outline-offset:-2px}td.ffc{outline:1px dashed var(--fc);outline-offset:-2px}
td.fm{outline:1px solid var(--mn);outline-offset:-2px}td.fe{outline:1px dashed var(--fe);outline-offset:-2px;background:rgba(192,132,252,.10)}
.ctl{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:10px 0}.ctl input,.ctl select{background:var(--pn2);border:1px solid var(--ln);border-radius:6px;color:var(--tx);font:inherit;padding:4px 8px}
.ctl input[type=search]{min-width:190px}.ctl label{color:var(--tx2)}:focus-visible{outline:2px solid var(--a);outline-offset:3px}
.strip{display:flex;gap:2px}.strip span,.strip a{display:inline-block;min-width:30px;text-align:center;border:1px solid var(--ln);border-radius:3px;text-decoration:none}
.strip .obs{color:var(--c2)}.strip .filled{color:var(--pr);border-style:dashed}.strip .empty{color:var(--tx3);background:var(--empty)}
.caption{white-space:normal;min-width:220px;max-width:420px;text-align:left}details{margin:12px 0}summary{cursor:pointer;color:var(--tx2)}
.chart{width:100%;height:210px}.chart .actual{stroke:var(--a)}.chart .predicted{stroke:var(--pr)}.chart polyline{fill:none;stroke-width:2}
@media(min-width:768px){.wrap{max-height:70vh;overflow-y:auto}}@media(max-width:600px){section{padding:10px}.lbl{min-width:200px;max-width:220px}}
[hidden]{display:none!important}
"""


def json_html(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def at(seq, k):
    return seq[k] if isinstance(seq, list) and 0 <= k < len(seq) else None


def money(site, key, k):
    value = at(site.get(key), k)
    return value if number(value) else None


def delta(a, b):
    # Preserve the normalized decimal precision in data-v and manual checks.
    return float(Decimal(str(a)) - Decimal(str(b)))


def total(values):
    values = [v for v in values if v is not None]
    return float(sum((Decimal(str(v)) for v in values), Decimal(0))) if values else None


def fmt(value, scale=1000, digits=1):
    return "–" if value is None else f"{value / scale:,.{digits}f}"


def quarter_ord(q):
    if not re.fullmatch(r"\d{4}Q[1-4]", q):
        raise ValueError(f"Invalid quarter: {q!r}")
    return int(q[:4]) * 4 + int(q[-1]) - 1


def company(panel, stock):
    if not re.fullmatch(r"\d{6}", stock):
        raise ValueError("stock must be a six digit code")
    data = panel.get(stock)
    if data is None:
        return None
    fq = data.get("fq", [])
    ords = [quarter_ord(q) for q in fq]
    if not fq or ords != sorted(set(ords)):
        raise ValueError(f"{stock}: quarters must be nonempty, unique and increasing")
    ids = [s.get("id") for s in data.get("sites", [])]
    if not all(isinstance(i, str) and i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"{stock}: missing or duplicate site id")
    for site in data.get("sites", []):
        for key in ("amt", "cmp", "bal"):
            if not isinstance(site.get(key), list) or len(site[key]) != len(fq):
                raise ValueError(f"{site['id']}: {key} length does not match fq")
            if any(v is not None and not number(v) for v in site[key]):
                raise ValueError(f"{site['id']}: nonnumeric {key}")
    return data


def load_audit(audit=None):
    if audit is None:
        audit = json.loads((INPUT / "grade_audit.json").read_text(encoding="utf-8"))
    companies = audit.get("companies", [])
    if isinstance(companies, dict):
        return companies
    return {c["stock"]: c for c in companies}


def decision(panel, stock, page, audit=None):
    record = load_audit(audit).get(stock, {})
    raw = record.get("can", {}).get(page)
    # Never bool('no') / bool('false'). Unknown and absent fail closed.
    allowed = raw is True or raw in ("true", "yes", "conditional", "partial")
    blockers = " / ".join(record.get("blocker", []))
    if not allowed:
        return False, f"판정 {raw if raw is not None else '미제공'}: {blockers or '생성 허가 근거 없음'}"
    if stock not in panel:
        return False, "현재 input에 정규화 원장 없음"
    return True, f"판정 {raw}: {blockers or '제공된 관측 범위만 사용'}"


def normalize(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).casefold()


def aggregate(site):
    name = normalize(site.get("nm"))
    return bool(site.get("agg")) or name in {"합계", "총계", "총합계", "소계", "계", "기타"} or "기타현장" in name


def identity(site):
    return tuple(normalize(site.get(key)) for key in ("nm", "cl", "sd"))


def identity_counts(data):
    return [Counter(identity(s) for s in data["sites"] if not aggregate(s)
                    and any(money(s, key, k) is not None for key in ("amt", "cmp", "bal")))
            for k in range(len(data["fq"]))]


def filled(site, key, k, fq):
    """Conservative provenance reader; unknown nonempty shapes remain processed.

    Supports quarter arrays, metric arrays/maps, quarter/index maps and scalar
    markers. A present marker on either endpoint marks the difference as processed.
    No current input site has a non-null sFilled; supported shapes are tested.
    """
    def pick(value):
        if isinstance(value, list):
            return pick(at(value, k))
        if isinstance(value, dict):
            if any(metric in value for metric in ("amt", "cmp", "bal")):
                return pick(value.get(key))
            for index in (fq[k], str(k), k):
                if index in value:
                    return pick(value[index])
            if any(re.fullmatch(r"\d{4}Q[1-4]|\d+", str(x)) for x in value):
                return None
            return "unknown" if value else None
        return str(value) if value not in (None, False, "", 0) else None
    return pick(site.get("sFilled"))


FILL_CLASSES = {"p8": "fl", "interp": "fli", "xi1": "flx", "fcst": "ffc", "bcst": "ffc",
                "manual": "fm", "manualE": "fe"}


def series(data, site, counts=None):
    counts = counts if counts is not None else identity_counts(data)
    fq = data["fq"]
    values, markers, reasons = [], [], []
    for k, q in enumerate(fq):
        v, marker = None, None
        if aggregate(site):
            reason = "집계·기타현장: 구성 변화와 중복 위험으로 분기차분 제외"
        elif k == 0:
            reason = "직전 분기 원장 없음: 첫 누계를 분기매출로 간주하지 않음"
        elif quarter_ord(q) != quarter_ord(fq[k - 1]) + 1:
            reason = "비연속 분기: 여러 분기의 차이를 한 분기 값으로 만들지 않음"
        elif any(money(site, "cmp", j) is None for j in (k - 1, k)):
            reason = "당기 또는 직전 분기 cmp 누계 미제공"
        elif not identity(site)[0] or any(counts[j][identity(site)] != 1 for j in (k - 1, k)):
            reason = "동일 nm/cl/sd 식별 중복 또는 이름 없음: 연결 보류"
        else:
            v = delta(money(site, "cmp", k), money(site, "cmp", k - 1))
            marker = filled(site, "cmp", k, fq) or filled(site, "cmp", k - 1, fq)
            reason = (f"sFilled={marker}: 가공 입력을 포함한 차분" if marker else "관측 입력의 누계 차분; 회계 매출 확정 아님")
            if v < 0:
                reason += "; 음수 유지: 정정·범위변경·초기화 가능"
        values.append(v)
        markers.append(marker)
        reasons.append(reason)
    return {"values": values, "markers": markers, "reasons": reasons}


def cell(value, reason="", cls="", q=""):
    classes = [cls, "na" if value is None else "", "dn" if value is not None and value < 0 else "",
               "yb" if q.endswith("Q1") else ""]
    return f'<td class="{E(" ".join(classes).strip())}" title="{E(reason)}">{fmt(value)}</td>'


def qhead(fq, label):
    return '<thead><tr><th class="lbl" scope="col">' + E(label) + '</th>' + ''.join(
        f'<th scope="col" class="{"yb" if q.endswith("Q1") else ""}">{E(q)}</th>' for q in fq) + '</tr></thead>'


def audit_note(panel, stock, page, audit):
    record = load_audit(audit).get(stock, {})
    _, why = decision(panel, stock, page, audit)
    n = len(panel[stock]["fq"])
    return (f'<p class="note">{E(why)}</p><p class="footnote">판정 원장 {record.get("quarters", "미상")}시점 · '
            f'현재 원장 {n}시점. 입력이 늘어도 등급·생성 금지 판정을 자동 승격하지 않습니다. '
            '단위는 기존 생성기의 백만원 원장 규약을 따르며 원문 환산 정확성은 재검증하지 못했습니다.</p>')


def shell(data, stock, title, body, script=""):
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{E(data.get("co", stock))} · {E(title)}</title><style>{CSS}</style></head><body>'
            f'<header><div class="hd"><h1>{E(data.get("co", stock))} · {E(title)}</h1>'
            f'<span class="tag">{E(stock)} · 제공 원장 {len(data.get("fq", []))}시점</span></div>'
            '<nav aria-label="상세 페이지"><a href="status.html">페이지·판정 안내</a></nav></header>'
            f'<main>{body}</main><script>{script}</script></body></html>\n')


MATRIX_JS = r"""
const rows=[...document.querySelectorAll('#tb tr[data-q]')];
const groups=[...document.querySelectorAll('#tb tr.grp[data-gid]')];
const n=document.querySelectorAll('#matrix thead th').length-1;
const fmt=v=>v===null?'–':(v/1000).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1});
function update(){
 const query=document.getElementById('search').value.toLowerCase();
 const group=document.getElementById('group').value;
 const processed=document.getElementById('processed').checked;
 const sums=Array(n).fill(null), per={}, counts=Array(n).fill(0);let shown=0;
 rows.forEach(r=>{
  const visible=r.dataset.q.includes(query)&&(!group||r.dataset.gid===group);
  r.hidden=!visible;if(!visible)return;shown++;
  const gid=r.dataset.gid;if(!per[gid])per[gid]=Array(n).fill(null);
  const flags=r.dataset.fill.split(',');
  r.dataset.v.split(',').forEach((x,k)=>{
   if(x===''||(!processed&&flags[k]==='1'))return;
   const v=Number(x);if(!Number.isFinite(v))return;
   sums[k]=(sums[k]===null?0:sums[k])+v;
   per[gid][k]=(per[gid][k]===null?0:per[gid][k])+v;counts[k]++;
  });
 });
 function set(row,vals){[...row.querySelectorAll('td')].slice(1).forEach((td,k)=>td.textContent=fmt(vals[k]));}
 set(document.getElementById('total'),sums);
 groups.forEach(g=>{g.hidden=!per[g.dataset.gid];set(g,per[g.dataset.gid]||Array(n).fill(null));});
 document.getElementById('count').textContent=shown+'행 표시 · 합산 '+(processed?'가공 포함':'관측 입력만')+' · 회사 총매출 아님';
 document.getElementById('total').querySelector('td').textContent='선택 현장 부분합 ('+(processed?'가공 포함':'관측 입력')+')';
 document.getElementById('coverage').textContent=FQ.map((q,k)=>q+': '+counts[k]+'건').join(' / ');
}
document.getElementById('search').addEventListener('input',update);
document.getElementById('group').addEventListener('change',update);
document.getElementById('processed').addEventListener('change',update);update();
"""


def build_matrix(panel, stock, *, audit=None):
    if not decision(panel, stock, "matrix", audit)[0]:
        return None
    data = company(panel, stock)
    fq, sites = data["fq"], data["sites"]
    counts = identity_counts(data)
    by_id = {s["id"]: series(data, s, counts) for s in sites}
    groups = defaultdict(list)
    for s in sites:
        key = "집계·기타현장 (차분 제외)" if aggregate(s) else f'{s.get("reg") or "미상"} · {s.get("seg") or "미상"}'
        groups[key].append(s)

    def sum_cells(members):
        return ''.join(cell(total(by_id[s["id"]]["values"][k] for s in members
                                 if not by_id[s["id"]]["markers"][k]), q=q) for k, q in enumerate(fq))

    rows = ['<tr class="grp tot" id="total"><td class="lbl">선택 현장 부분합 (관측 입력)</td>' + sum_cells(sites) + '</tr>']
    for gid, (name, members) in enumerate(groups.items()):
        rows.append(f'<tr class="grp" data-gid="{gid}"><td class="lbl">{E(name)} ({len(members)})</td>{sum_cells(members)}</tr>')
        for s in members:
            rev = by_id[s["id"]]
            values = ','.join('' if v is None else str(v) for v in rev["values"])
            flags = ','.join('1' if m else '0' for m in rev["markers"])
            search = ' '.join(str(s.get(key) or '') for key in ("id", "nm", "cl", "reg", "seg")).lower()
            label = f'<span class="cid">{E(s["id"])}</span><br>{E(s.get("nm") or "이름 미제공")}'
            if aggregate(s):
                label += ' <span class="tag">집계 · 합산 제외</span>'
            cells = ''.join(cell(v, rev["reasons"][k], FILL_CLASSES.get(rev["markers"][k], "fe") if rev["markers"][k] else "", fq[k])
                            for k, v in enumerate(rev["values"]))
            rows.append(f'<tr class="{"agg" if aggregate(s) else "site"}" data-gid="{gid}" data-q="{E(search)}" '
                        f'data-id="{E(s["id"])}" data-v="{E(values)}" data-has="???" data-fill="{flags}">'
                        f'<td class="lbl">{label}</td>{cells}</tr>')
    groups_html = ''.join(f'<option value="{i}">{E(name)}</option>' for i, name in enumerate(groups))
    body = audit_note(panel, stock, "matrix", audit)
    body += ('<p>분기매출 후보 = 동일 현장의 인접 관측 cmp 누계 차분. <b>확정 매출·회사 총매출이 아닙니다.</b> '
             '금액: 십억원 (백만원 원장 ÷ 1,000). 음수와 0을 그대로 표시합니다.</p>'
             '<p class="footnote">관측 입력 차분: 일반 셀 · 가공 포함: 점선/실선 셀 (툴팁에 sFilled). '
             '초록=p8, 주황=interp, 보라=xi1, 분홍=fcst/bcst, 청록=manual, 연보라=기타 가공. '
             '가공 셀은 표시하되 기본 부분합에서 제외합니다.</p>'
             '<section><h2>현장별 분기차분</h2><div class="ctl">'
             '<label>검색 <input id="search" type="search" placeholder="현장·발주처·코드"></label>'
             f'<label>그룹 <select id="group"><option value="">전체</option>{groups_html}</select></label>'
             '<label><input id="processed" type="checkbox"> 부분합에 가공값 포함</label>'
             '<span id="count" aria-live="polite"></span></div>'
             f'<div class="wrap" tabindex="0" aria-label="분기매출 후보 표 가로 스크롤"><table class="wide" id="matrix">{qhead(fq, "현장 / 단위: 십억원")}'
             f'<tbody id="tb">{"".join(rows)}</tbody></table></div>'
             '<p class="footnote" id="coverage" aria-live="polite"></p></section>')
    # Independently reported totals are context, never additive to site differences.
    raw_rows = []
    for label, values in [("공시 잔고 declared (비가산)", data.get("declared", [])),
                          ("원장 summary.bal (비가산)", data.get("summary", {}).get("bal", []))]:
        raw_rows.append(f'<tr><td class="lbl">{E(label)}</td>' + ''.join(cell(at(values, k), q=q) for k, q in enumerate(fq)) + '</tr>')
    for s in sites:
        if aggregate(s):
            raw_rows.append(f'<tr class="agg"><td class="lbl">{E(s["nm"])} · 원장 잔고 (비가산)</td>'
                            + ''.join(cell(money(s, "bal", k), q=q,
                                           cls="fe" if filled(s, "bal", k, fq) else "",
                                           reason="가공값" if filled(s, "bal", k, fq) else "관측 잔고") for k, q in enumerate(fq)) + '</tr>')
    body += (f'<section><h2>잔고 대조 · 분기차분 합계에 더하지 않는 참고값</h2><div class="wrap" tabindex="0"><table class="wide">'
             f'{qhead(fq, "공시·집계 원장 / 십억원")}<tbody>{"".join(raw_rows)}</tbody></table></div></section>'
             '<section><h2>빈칸과 합산 범위</h2><p class="footnote">–는 첫 분기·비연속 분기·누계 결측·중복 식별·집계행입니다. '
             '셀 툴팁에 개별 이유를 남겼습니다. 결측을 0으로 채우거나 첫 관측 누계를 전액 매출로 넣지 않습니다. '
             'agg=true, 기타현장, 합 계/소계/총계는 현장 부분합에서 항상 제외합니다. '
             'sFilled가 어느 한쪽 누계에 있으면 차분도 가공값입니다. '
             '분기별 합산 현장 구성이 다르므로 부분합 증감을 성장률로 해석하지 마세요. '
             'II-4/III-8/XI-1의 현장별 출처 플래그는 미제공이므로 data-has는 ???입니다.</p></section>')
    return shell(data, stock, PAGES["matrix"], body, 'const FQ=' + json_html(fq) + ';\n' + MATRIX_JS)


def valid_positions(positions, stock, fq):
    out = {}
    for q in fq:
        record = positions.get(stock, {}).get(q, {})
        receipt = str(record.get("rcpNo") or "")
        tables = [t for t in record.get("tables", []) if isinstance(t.get("i"), int)
                  and not isinstance(t["i"], bool) and t["i"] >= 0]
        if re.fullmatch(r"\d{14}", receipt) and tables:
            out[q] = {"rcpNo": receipt, "tables": tables}
    return out


TRACE_JS = r"""
const traceRows=[...document.querySelectorAll('#trace-body tr')];
function traceFilter(){const q=document.getElementById('trace-search').value.toLowerCase();
 let n=0;traceRows.forEach((r,i)=>{r.hidden=!String(SITES[i][0]+' '+SITES[i][1]).toLowerCase().includes(q);if(!r.hidden)n++;});
 document.getElementById('trace-count').textContent=n+'행';}
document.getElementById('trace-search').addEventListener('input',traceFilter);traceFilter();
"""


def build_trace(panel, positions, stock, *, audit=None):
    if not decision(panel, stock, "trace", audit)[0]:
        return None
    data = company(panel, stock)
    fq = data["fq"]
    loc = valid_positions(positions, stock, fq)
    if not loc:
        return None
    # A company-quarter table cannot establish a particular site's row location.
    # The strip describes panel presence and links to a separately labeled locator.
    slim, rows = [], []
    for s in data["sites"]:
        marks = []
        for k, q in enumerate(fq):
            keys = [key for key in ("amt", "cmp", "bal") if money(s, key, k) is not None]
            marks.append(None if not keys else ("가" if any(filled(s, key, k, fq) for key in keys) else "O"))
        slim.append([s["id"], s.get("nm", ""), marks, int(aggregate(s))])
        cells = []
        for q, mark in zip(fq, marks):
            reason = "원장 수치 없음" if mark is None else ("가공 포함; 원문 관측으로 간주하지 않음" if mark == "가" else "원장 수치 존재; 현장↔표 연결 미확정")
            content = E(mark or "–")
            if mark and q in loc:
                content = f'<a href="#source-{q}" title="{E(reason)} · 회사 분기 표 후보 보기">{content}</a>'
            cells.append(f'<td class="{"fli" if mark == "가" else ""}" title="{E(reason)}">{content}</td>')
        rows.append(f'<tr class="{"agg" if aggregate(s) else "site"}"><td class="lbl"><span class="cid">{E(s["id"])}</span><br>'
                    f'{E(s.get("nm", ""))}{" · 집계" if aggregate(s) else ""}</td>{"".join(cells)}</tr>')
    source_rows = []
    for q in fq:
        record = loc.get(q)
        if not record:
            source_rows.append(f'<tr id="source-{q}"><td>{q}</td><td colspan="5" class="l">접수번호 또는 표 위치 없음</td></tr>')
            continue
        for j, table in enumerate(record["tables"]):
            href = "https://dart.fss.or.kr/dsaf001/main.do?" + urlencode({"rcpNo": record["rcpNo"]})
            anchor = f' id="source-{q}"' if j == 0 else ''
            source_rows.append(f'<tr{anchor}><td>{q}</td>'
                              f'<td><a href="{E(href)}" target="_blank" rel="noopener noreferrer">{record["rcpNo"]} · DART</a></td>'
                              f'<td>i={table["i"]} (0기반)</td><td>{E(str(table.get("unit") or "단위 미제공"))}</td>'
                              f'<td>{E(str(table.get("n") if table.get("n") is not None else "미제공"))}</td>'
                              f'<td class="caption">{E(str(table.get("lead") or "캡션 미제공"))}</td></tr>')
    body = audit_note(panel, stock, "trace", audit)
    body += (f'<p>회사·분기 표 위치 {len(loc)}/{len(fq)}시점. 아래 O는 <b>정규화 원장 수치 존재</b>입니다. '
             '원문 공사명이나 개별 행 위치를 확인했다는 뜻이 아닙니다.</p>'
             '<p class="note">입력 위치는 회사·분기별 추출 표 번호 i와 캡션입니다. '
             'DART의 dcmNo/offset 및 현장↔표 대응은 없습니다. DART 링크는 보고서를 열며 특정 표로 바로 이동하지 않습니다.</p>'
             '<section><h2>원장 관측 스트립 · O 관측 입력 / 가 가공 포함 / – 미제공</h2>'
             '<div class="ctl"><label>검색 <input type="search" id="trace-search" placeholder="현장·코드"></label>'
             '<span id="trace-count" aria-live="polite"></span></div>'
             f'<div class="wrap" tabindex="0" aria-label="추적 표 가로 스크롤"><table class="wide">{qhead(fq, "현장 / 원장 존재")}'
             f'<tbody id="trace-body">{"".join(rows)}</tbody></table></div>'
             '<p class="footnote">O/가를 누르면 그 분기의 회사 표 후보로 이동합니다. 여러 표가 있으면 모두 후보로 제시하며 '
             '특정 현장의 원표로 임의 배정하지 않습니다. 가공값에 대한 원문 관측을 주장하지 않습니다.</p></section>'
             '<section><h2>원문 배치 · kce_table_positions.json</h2><div class="wrap" tabindex="0"><table>'
             '<thead><tr><th>분기</th><th>접수번호 / 보고서 링크</th><th>추출 표 위치</th><th>원문 단위</th><th>기록 행수 n</th><th>단위·위치 캡션</th></tr></thead>'
             f'<tbody>{"".join(source_rows)}</tbody></table></div></section>'
             '<section><h2>출처별 빈칸</h2><p class="footnote">II-4 현장별 원문명·행번호, III-8 별도/연결의 현장별 원자료, XI-1 계약명은 '
             '이 정규화 원장과 위치 파일에 없습니다. 원본의 네 출처 스트립을 임의 복원하지 않습니다. '
             'grade_audit의 III-8 일부 가능 판정은 증거 요약이며 19분기의 행별 원문 자료를 대신하지 않습니다. '
             '이 페이지는 partial 판정을 유지하는 회사 표 위치·원장 존재 지도입니다.</p></section>')
    return shell(data, stock, PAGES["trace"], body,
                 'const FQ=' + json_html(fq) + ',SITES=' + json_html(slim) + ';\n' + TRACE_JS)


def backtest_data(data):
    """Fixed one-quarter persistence; all three cmp endpoints must be observed.

    No latest dates, future schedules, interpolation or fit on holdouts. Signed
    revisions are kept in the provisional score; they remain unverified targets.
    """
    fq = data["fq"]
    counts = identity_counts(data)
    revs = {s["id"]: series(data, s, counts) for s in data["sites"]}
    folds, omitted = [], []
    for k in range(1, len(fq) - 1):
        examples = []
        exclusions = Counter()
        for s in data["sites"]:
            if aggregate(s):
                exclusions["집계행"] += 1
                continue
            rev = revs[s["id"]]
            pred, actual = rev["values"][k], rev["values"][k + 1]
            if pred is None or actual is None:
                exclusions["인접 관측 3개/고유 식별 부족"] += 1
                continue
            if rev["markers"][k] or rev["markers"][k + 1]:
                exclusions["sFilled 포함"] += 1
                continue
            examples.append({"id": s["id"], "name": s.get("nm", ""),
                             "cmp": [money(s, "cmp", j) for j in (k - 1, k, k + 1)],
                             "predicted": pred, "actual": actual, "error": delta(pred, actual)})
        if not examples:
            omitted.append({"origin": fq[k], "reason": "평가 가능한 비집계·비가공 인접 3관측 현장 없음"})
            continue
        errors = [abs(e["error"]) for e in examples]
        denom = total(abs(e["actual"]) for e in examples)
        folds.append({"train_from": fq[k - 1], "origin": fq[k], "holdout": fq[k + 1],
                      "n": len(examples), "predicted": total(e["predicted"] for e in examples),
                      "actual": total(e["actual"] for e in examples), "mae": total(errors) / len(errors),
                      "wape": total(errors) / denom * 100 if denom else None,
                      "negative_train": sum(e["predicted"] < 0 for e in examples),
                      "negative_actual": sum(e["actual"] < 0 for e in examples),
                      "exclusions": dict(exclusions), "examples": examples})
    examples = [e for fold in folds for e in fold["examples"]]
    errors = [abs(e["error"]) for e in examples]
    denom = total(abs(e["actual"]) for e in examples)
    return {"folds": folds, "omitted": omitted, "n": len(examples),
            "sites": len({e["id"] for e in examples}),
            "mae": total(errors) / len(errors) if errors else None,
            "wape": total(errors) / denom * 100 if denom else None}


def fold_chart(folds):
    values = [f[key] for f in folds for key in ("predicted", "actual")]
    lo, hi = min(values + [0]), max(values + [0])
    span = hi - lo or 1
    def points(key):
        return ' '.join(f'{35 + i * 720 / max(1, len(folds) - 1):.2f},{170 - (f[key] - lo) / span * 140:.2f}' for i, f in enumerate(folds))
    return ('<svg class="chart" viewBox="0 0 800 210" role="img" aria-labelledby="chart-title">'
            '<title id="chart-title">평가 현장 부분합 · 주황 예측, 파랑 실제 차분. 분기별 현장 구성이 다름.</title>'
            f'<polyline class="predicted" points="{points("predicted")}"/><polyline class="actual" points="{points("actual")}"/>'
            f'<text x="35" y="200" fill="var(--tx2)" font-size="12">{folds[0]["origin"]} → {folds[-1]["origin"]} · 주황 예측 / 파랑 실제 차분</text></svg>')


def build_backtest(panel, stock, *, audit=None):
    if not decision(panel, stock, "backtest", audit)[0]:
        return None
    data = company(panel, stock)
    bt = backtest_data(data)
    if not bt["folds"]:
        return None
    rows, details = [], []
    for fold in bt["folds"]:
        wape = '–' if fold["wape"] is None else f'{fold["wape"]:.1f}%'
        rows.append(f'<tr><td>{fold["train_from"]} → {fold["origin"]}</td><td>{fold["holdout"]}</td><td>{fold["n"]}</td>'
                    f'<td>{fmt(fold["predicted"])}</td><td>{fmt(fold["actual"])}</td><td>{fmt(fold["mae"])}</td><td>{wape}</td>'
                    f'<td>{fold["negative_train"]} / {fold["negative_actual"]}</td></tr>')
        erows = []
        for e in fold["examples"]:
            erows.append(f'<tr><td class="l">{E(e["id"])} · {E(e["name"])}</td>'
                         + ''.join(f'<td>{fmt(v, 1, 3)}</td>' for v in e["cmp"])
                         + ''.join(f'<td>{fmt(e[key], 1, 3)}</td>' for key in ("predicted", "actual", "error")) + '</tr>')
        exclusions = ' / '.join(f'{key} {value}행' for key, value in fold["exclusions"].items())
        details.append(f'<details><summary>기준 {fold["origin"]} · {fold["n"]}건의 계산 원장 (백만원)</summary><p class="footnote">제외: {E(exclusions or "없음")}</p>'
                       '<div class="wrap" tabindex="0"><table><thead><tr><th class="l">현장</th><th>C[t-1]</th><th>C[t]</th><th>C[t+1]</th>'
                       '<th>예측</th><th>실제 차분</th><th>오차 (예측−실제)</th></tr></thead>'
                       f'<tbody>{"".join(erows)}</tbody></table></div></details>')
    small = len(bt["folds"]) < 8 or bt["sites"] < 20 or any(f["n"] < 10 for f in bt["folds"])
    warning = ('표본이 적습니다: ' if small else '표본 범위 제한: ') + (
        f'{len(bt["folds"])}개 기준분기, {bt["n"]}개 현장×기준분기, 고유 {bt["sites"]}현장. '
        '같은 현장이 반복되므로 독립 표본 수가 아닙니다. 원본 S-curve 성적표와 비교할 수 없습니다.')
    body = audit_note(panel, stock, "backtest", audit)
    body += ('<p><b>고정 1분기 지속모형의 조건부 성적표.</b> 기준 t의 예측 = C[t]−C[t−1], '
             '평가 타깃 = C[t+1]−C[t]. 인접한 세 관측만 사용하고 가공·집계행은 제외합니다. '
             '평가 타깃은 검증된 재무제표 매출이 아닌 누계 차분입니다.</p>'
             f'<p class="note">{E(warning)}</p><div class="kpi">'
             f'<div><b>{len(bt["folds"])}</b><span>평가 가능한 기준분기</span></div><div><b>{bt["n"]}</b><span>현장×기준분기</span></div>'
             f'<div><b>{fmt(bt["mae"])}</b><span>MAE · 십억원</span></div>'
             f'<div><b>{"–" if bt["wape"] is None else format(bt["wape"], ".1f") + "%"}</b><span>전체 WAPE</span></div></div>'
             '<section><h2>평가 현장 부분합 · 분기별 현장 구성 다름</h2>' + fold_chart(bt["folds"]) + '</section>'
             '<section><h2>기준분기별 성적 · 금액 십억원</h2><div class="wrap" tabindex="0"><table><thead><tr>'
             '<th>학습 / 기준 t</th><th>평가 t+1</th><th>현장 수</th><th>예측 부분합</th><th>실제 차분 부분합</th><th>MAE</th><th>WAPE</th><th>음수 학습 / 평가</th>'
             f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>'
             f'<section><h2>손으로 재계산할 수 있는 현장별 기록</h2>{"".join(details)}</section>'
             '<section><h2>평가 범위와 빈칸</h2><p class="footnote">MAE = Σ|예측−실제| / 평가건수. '
             'WAPE = Σ|예측−실제| / Σ|실제| × 100; 분모 0이면 –입니다. 전체 지표는 모든 현장×기준분기로 계산하며 '
             '분기 WAPE의 단순평균을 쓰지 않습니다. 음수 정정은 별도 건수로 표시하고 점수에서 숨기지 않습니다. '
             '관측 3개가 없는 현장, 비연속 분기, 중복 식별, sFilled 포함, 집계행은 제외합니다. '
             '맨 처음 분기는 학습 이전 값이 없고 맨 마지막 분기는 다음 평가값이 없어서 기준분기로 쓰지 않습니다. '
             '종료일·최신 잔고·사후 모델 재적합을 예측에 사용하지 않습니다. 최신 정규화 원장의 생존·정정 편향, '
             '시점별 식별/연결 검증 한계는 남아 있습니다.</p>'
             '<p class="footnote">표본 부족 표시 규칙: 기준분기 8개 미만 또는 고유현장 20개 미만 또는 '
             '어느 기준분기든 10현장 미만. 이는 설명용 기준이며 통계적 유의성 판정이 아닙니다.</p>'
             '<p class="footnote">후보에서 제외된 기준분기: '
             + E(' / '.join(f'{x["origin"]}: {x["reason"]}' for x in bt["omitted"]) or '없음') + '</p></section>')
    return shell(data, stock, PAGES["backtest"], body)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".detail-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def build_all(panel, positions, output_dir=None, stocks=None, *, audit=None):
    """Build only permitted pages; status.html explains every omission.

    Destinations must be inside this generator's output directory. Denied pages
    are not written. A preexisting denied page aborts to prevent stale-page leaks;
    the caller must choose a fresh destination (no implicit destructive cleanup).
    """
    dest = Path(output_dir) if output_dir is not None else ROOT / "samples"
    dest = dest.resolve()
    if not dest.is_relative_to(ROOT):
        raise ValueError("deliverables must stay under output/ (generator directory)")
    audit = audit if audit is not None else json.loads((INPUT / "grade_audit.json").read_text(encoding="utf-8"))
    stocks = list(stocks) if stocks is not None else sorted(panel)
    manifest, staged = {}, {}
    for stock in stocks:
        data = company(panel, stock)
        record = load_audit(audit).get(stock, {})
        pages = {"matrix": build_matrix(panel, stock, audit=audit),
                 "trace": build_trace(panel, positions, stock, audit=audit),
                 "backtest": build_backtest(panel, stock, audit=audit)}
        status = {}
        links = []
        for page, content in pages.items():
            allowed, reason = decision(panel, stock, page, audit)
            if allowed and content is None:
                reason = "접수번호·표 위치 없음" if page == "trace" else "평가 가능한 비집계·비가공 인접 3관측 현장 없음"
            path = dest / stock / f"{page}.html"
            if not path.resolve().is_relative_to(ROOT):
                raise ValueError("destination symlink escapes output/")
            if content is None and path.exists():
                raise FileExistsError(f"Denied page already exists; choose a fresh output directory: {path}")
            status[page] = {"generated": content is not None, "reason": reason}
            if content is not None:
                staged[path] = content
                links.append(f'<p><a href="{page}.html">{E(PAGES[page])}</a> · {E(reason)}</p>')
            else:
                links.append(f'<p class="note">{E(PAGES[page])} 미생성 — {E(reason)}</p>')
        manifest[stock] = {"name": data.get("co", stock) if data else record.get("name", stock),
                           "grade": record.get("now", "미상"), "quarters": len(data["fq"]) if data else 0,
                           "audit_quarters": record.get("quarters"), "pages": status}
        body = (f'<p>기존 등급: {E(str(record.get("now", "미상")))}. 판정 우선으로 생성 여부를 결정했습니다.</p>'
                + ''.join(links) + '<p class="footnote">기존 index는 제공 입력이며 이 표본에서 재작성하지 않습니다. '
                '원본의 index·matrix·trace·backtest 네 페이지를 모두 사용할 수 있는 등급으로 자동 승격하지 않습니다.</p>')
        staged[dest / stock / "status.html"] = shell(data or {"co": record.get("name", stock)}, stock, "페이지·판정 안내", body)
    for path, content in staged.items():
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError("destination symlink escapes output/")
    for path, content in staged.items():
        atomic_write(path, content)
    manifest_path = dest / "manifest.json"
    if not manifest_path.resolve().is_relative_to(ROOT):
        raise ValueError("manifest symlink escapes output/")
    atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=INPUT)
    parser.add_argument("--out", type=Path, default=ROOT / "samples")
    parser.add_argument("--stocks", nargs="+", default=["001260", "011370"], help="default: two different audit grades")
    parser.add_argument("--all", action="store_true", help="build all panel companies")
    args = parser.parse_args()
    def read(name):
        return json.loads((args.input_dir / name).read_text(encoding="utf-8"))
    panel, positions, audit = (read(name) for name in ("kce_panel_data.json", "kce_table_positions.json", "grade_audit.json"))
    result = build_all(panel, positions, args.out, None if args.all else args.stocks, audit=audit)
    for stock, item in result.items():
        rendered = ','.join(page for page, state in item["pages"].items() if state["generated"]) or 'none'
        denied = ','.join(page for page, state in item["pages"].items() if not state["generated"]) or 'none'
        print(f'{stock} {item["name"]} grade={item["grade"]} quarters={item["quarters"]} generated={rendered} omitted={denied}')
    print(f'companies={len(result)} pages={sum(s["generated"] for x in result.values() for s in x["pages"].values())} status={len(result)}')


if __name__ == "__main__":
    main()
