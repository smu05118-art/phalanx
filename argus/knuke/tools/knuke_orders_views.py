# 주의: knuke_forecast_section.py 와 같은 이유로 탭 접두(knuke_)를 유지한다. 다른 탭의 동명 모듈과 섞이지 않게.
#!/usr/bin/env python3
"""KNUKE 수주 상세 뷰 3종 — 간트 · 분기 전환 스케줄 · 발주처별. 회사 페이지에 끼우는 HTML 조각.

API (knuke_forecast_section.render_forecast_section 과 같은 관례):
    render_orders_section(panel_entry, contracts, forecast_entry=None, today=None) -> str
    build_gantt(contracts, today=None) -> dict
    build_schedule(contracts, forecast_entry=None, window=("2026Q3", "2028Q4"), today=None) -> dict
    build_clients(contracts, today=None, top_n=8) -> dict

- 표준 라이브러리만. 인라인 SVG/CSS 만, 외부 자산·JS 없음.
- `contracts` 는 contracts.json 의 rows 목록(또는 {"rows": [...]} 전체) — 계약공시 원장.
  행마다 name·party·party_kind·domain·tier·start·end·amt_krw_m 을 읽는다. 정기보고서 수주표 행
  (client·closing)도 같은 자리에서 읽히도록 별칭을 두었지만 금액 뜻(계약총액 vs 잔고)이 다르므로
  amount_source 로 구분해 표시한다.
- 금액은 `amt_krw_m`(백만원)을 그대로 읽고 절대 재배율하지 않는다. 값이 없으면 —(0 아님).
- 오늘(today)은 인자 → panel_entry['asof'] → date.today() 순.
"""
import argparse
from collections import Counter, OrderedDict
from datetime import date, datetime, timedelta
import html
import json
import math
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True

DEFAULT_WINDOW = ("2026Q3", "2028Q4")
DOMAIN_ORDER = ["NUKE", "THERMAL", "RENEW", "GRID", "IND", "NONE"]
DOMAINS = {
    "NUKE": ("원자력", "var(--a)"),
    "THERMAL": ("화력·가스", "#f1ba72"),
    "RENEW": ("신재생·수력·ESS", "#8fd18f"),
    "GRID": ("송배전·전력망", "#86a7dc"),
    "IND": ("산업·플랜트", "#c9a0dc"),
    "NONE": ("발전원 미판정", "#8a9bb0"),
}
TIERS = OrderedDict([
    ("DECOM", "해체·폐기물"), ("INSP", "검사"), ("OM", "정비·O&M"), ("ENG", "설계"),
    ("EPC", "EPC·건설·설치"), ("INC", "계측제어"), ("IC", "계측제어"), ("MAIN", "주기기"),
    ("AUX", "보조기기"), ("SUPPLY", "기자재"), ("UNKNOWN", "미분류"),
])
SERVICE_TIERS = {"DECOM", "INSP", "OM"}
KINDS = {"GOV": "관급(한수원·한전·발전사·조달청)", "PRIME": "원청 하도급", "FOREIGN": "해외",
         "DOMESTIC": "국내 민간", "ANON": "공시유보", "UNKNOWN": "미상"}
ANON_KEY = "__anon__"
ANON_TOKENS = {"", "-", "—", "–", "미공개", "비공개", "공시유보", "비밀유지"}
SCENARIOS = OrderedDict([("conservative", "보수"), ("base", "기준"), ("optimistic", "낙관")])
CSS = """
.knuke-orders{--tx:#e6edf5;--pn:#132233;--ln:#38506a;--bg:#091522;--a:#62dbc9;color:var(--tx);background:var(--pn);border:1px solid var(--ln);border-radius:12px;padding:20px;margin:20px auto;font:15px/1.6 system-ui,sans-serif;max-width:1200px}
.knuke-orders h2,.knuke-orders h3{line-height:1.3}.knuke-orders a{color:var(--a)}
.knuke-orders table{border-collapse:collapse;width:100%;font-size:13px}.knuke-orders th,.knuke-orders td{border-bottom:1px solid var(--ln);padding:7px;text-align:left;vertical-align:top}.knuke-orders th.num,.knuke-orders td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.knuke-orders caption{text-align:left;padding:10px 0;font-weight:700}
.knuke-orders .scroll{overflow-x:auto}.knuke-orders .warning{border-left:4px solid #f1ba72;padding:10px;background:var(--bg)}
.knuke-orders details{padding:10px 0;border-top:1px solid var(--ln)}.knuke-orders summary{cursor:pointer;font-weight:700}
.knuke-orders .badge{border:1px solid var(--a);padding:2px 8px;border-radius:12px;color:var(--a);font-size:12px}
.knuke-orders small{color:#b3c5d7}.knuke-orders svg .sub{fill:#b3c5d7}.knuke-orders svg{width:100%;height:auto;min-width:620px;display:block}
.knuke-orders .legend span{display:inline-block;margin:0 12px 4px 0;font-size:13px}.knuke-orders .sw{display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-2px;margin-right:4px;border:1px solid var(--ln)}
@media(prefers-color-scheme:light){.knuke-orders{--tx:#132233;--pn:#fff;--ln:#bbc9d7;--bg:#eef4f7;--a:#00665b}.knuke-orders small{color:#435b72}.knuke-orders svg .sub{fill:#435b72}}
"""


# ---------- 공통 도우미 ----------

def esc(x):
    return html.escape(str(x), quote=True)


def number(x):
    return isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)


def fmt(x):
    """표용: 백만원 소수 3자리(기존 섹션과 같은 표기)."""
    return f"{x:,.3f}" if number(x) else "—"


def fmt0(x):
    """그림 라벨용: 정수 자리만."""
    return f"{x:,.0f}" if number(x) else "—"


def pct(v, t):
    return (v / t * 100.0) if (number(v) and number(t) and t > 0) else None


def fmt_pct(p):
    return f"{p:.1f}%" if number(p) else "—"


def parse_date(x):
    """'YYYY-MM-DD' · 'YYYY.MM.DD' · 'YYYY/MM/DD' · 'YYYYMMDD' → date. 못 읽으면 None(추정하지 않음)."""
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    s = str(x).strip()
    if not s or s in ("-", "—", "–"):
        return None
    m = re.match(r"^(\d{4})[.\-/]?(\d{1,2})[.\-/]?(\d{1,2})", s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _today(x=None):
    if x is None:
        return date.today()
    d = parse_date(x)
    if d is None:
        raise ValueError("today must be a date or YYYY-MM-DD string")
    return d


def qparse(key):
    m = re.fullmatch(r"(\d{4})Q([1-4])", str(key).strip())
    if not m:
        raise ValueError("quarter key must look like 2026Q3: " + str(key))
    return int(m.group(1)), int(m.group(2))


def qkey(yq):
    return f"{yq[0]}Q{yq[1]}"


def quarter_of(d):
    return d.year, (d.month - 1) // 3 + 1


def quarter_range(q0, q1):
    out = []
    y, q = q0
    while (y, q) <= q1:
        out.append((y, q))
        q += 1
        if q > 4:
            y, q = y + 1, 1
    return out


def domain_key(d):
    return d if d in DOMAINS and d != "NONE" else "NONE"


def domain_label(d):
    return DOMAINS[domain_key(d)][0]


def domain_color(d):
    return DOMAINS[domain_key(d)][1]


def tier_label(t):
    return TIERS.get(t or "UNKNOWN", "미분류" if not t else str(t))


_CORP = re.compile(r"(주식회사|\(주\)|㈜|\(유\)|유한회사|\(재\)|재단법인)")
_ALIAS = re.compile(r"\((?=[A-Za-z])[A-Za-z0-9&.,'\-/ ]*\)\s*$")
_SITE = re.compile(r"\s+\S+(본부|지사|사업소)$")


def client_key(name):
    """발주처 묶음 키: 법인 접미(㈜·주식회사) · 끝의 영문 별칭 괄호 · 공백·구두점을 걷어낸 소문자.
    원문 표기는 지우지 않고 raw_variants 로 같이 띄운다. 사명 변경(두산중공업↔두산에너빌리티)은 합치지 않는다."""
    s = str(name or "").strip()
    s = _ALIAS.sub("", s)
    s = _CORP.sub("", s)
    s = _SITE.sub("", s.strip())
    s = re.sub(r"[\s.,·ㆍ'\"()\[\]]+", "", s)
    return s.lower()


def is_anonymous(client, party_kind=None):
    c = re.sub(r"\s+", "", str(client or ""))
    if party_kind == "ANON":
        return True
    if c in ANON_TOKENS:
        return True
    return any(t in c for t in ("공시유보", "비밀유지", "미공개", "비공개"))


# ---------- 원장 행 정규화 ----------

def normalize_contracts(contracts, stock=None):
    """contracts.json rows(또는 {'rows': [...]}) → 뷰 공통 행. 이미 정규화된 행은 그대로 복사.
    stock 이 주어지면: dict 입력은 그 종목만 거르고, list 입력은 다른 종목 행이 섞이면 fail-closed."""
    if isinstance(contracts, dict):
        rows = contracts.get("rows") or contracts.get("contracts") or []
        if stock is not None:
            rows = [r for r in rows if r.get("stock") in (None, stock)]
    else:
        rows = list(contracts or [])
    out = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise ValueError("contract row must be a dict")
        if stock is not None and r.get("stock") not in (None, stock):
            raise ValueError("contract_identity_conflict")
        if r.get("_normalized"):
            out.append(dict(r))
            continue
        title = str(r.get("title") or "")
        if "amt_krw_m" in r:
            amt, src = r.get("amt_krw_m"), "계약금액(공시, 백만원)"
        elif "closing" in r:
            amt, src = r.get("closing"), "수주잔고(보고서, 백만원)"
        else:
            amt, src = r.get("amount"), "금액(백만원)"
        amount = float(amt) if number(amt) else None
        client = r.get("party") if "party" in r else r.get("client")
        client = str(client or "").strip()
        party_kind = str(r.get("party_kind") or "").strip() or None
        anonymous = is_anonymous(client, party_kind) or client_key(client) == ""
        note = str(r.get("note") or "").strip()
        withheld = str(r.get("withheld") or "").strip()
        out.append({
            "_normalized": True,
            "id": str(r.get("rcp") or r.get("id") or f"row{i}"),
            "stock": r.get("stock"),
            "name": str(r.get("name") or r.get("label") or "—").strip() or "—",
            "title": title,
            "client": client,
            "client_display": ("익명(공시유보)" if anonymous else client) or "발주처 미기재",
            "party_kind": party_kind,
            "anonymous": anonymous,
            "domain": r.get("domain") if r.get("domain") in DOMAINS else None,
            "tier": str(r.get("tier") or "UNKNOWN"),
            "smr": bool(r.get("smr")),
            "region": str(r.get("region") or "").strip(),
            "start": parse_date(r.get("start")),
            "start_raw": str(r.get("start_raw") if r.get("start_raw") not in (None, "") else (r.get("start") or "")),
            "end": parse_date(r.get("end")),
            "end_raw": str(r.get("end_raw") if r.get("end_raw") not in (None, "") else (r.get("end") or "")),
            "signed": parse_date(r.get("signed")),
            "amount": amount,
            "amount_source": src,
            "terminated": "해지" in title,
            "note": note,
            "withheld": "" if withheld in ("-", "—") else withheld,
        })
    return out


def _excerpt(note, keywords, width=80):
    if not note:
        return ""
    idx = -1
    for k in keywords:
        j = note.find(k)
        if j >= 0 and (idx < 0 or j < idx):
            idx = j
    if idx < 0:
        return ""
    a = max(0, idx - 25)
    b = min(len(note), a + width)
    return ("…" if a > 0 else "") + note[a:b].strip() + ("…" if b < len(note) else "")


def no_end_reason(r):
    """종료일이 없는 이유 — 원문(제목·비고)에서만 끌어온다."""
    if r["terminated"]:
        return "계약 해지 공시 — 원문에 계약기간·금액이 없음"
    note = r.get("note") or ""
    ex = _excerpt(note, ("종료일", "미정", "협의"))
    if "미정" in note:
        base = "원문에 종료일 '미정'"
    elif "협의" in note:
        base = "원문에 종료일 변경 협의 중"
    else:
        base = "공시 계약기간 종료일 칸이 비어 있음(end_raw=" + (r.get("end_raw") or "-") + ")"
    return base + (" — " + ex if ex else "")


# ---------- 뷰 1: 간트 ----------

def build_gantt(contracts, today=None):
    today = _today(today)
    rows = normalize_contracts(contracts)
    bars, no_end = [], []
    for r in rows:
        if r["end"] is None:
            n = dict(r)
            n["reason"] = no_end_reason(r)
            no_end.append(n)
        else:
            b = dict(r)
            b["ended"] = r["end"] < today
            b["start_missing"] = r["start"] is None
            bars.append(b)
    bars.sort(key=lambda b: (b["end"], b["start"] or b["end"], b["name"]))
    amounts = [b["amount"] for b in bars if number(b["amount"])]
    starts = [b["start"] for b in bars if b["start"] is not None]
    return {
        "today": today.isoformat(),
        "bars": bars,
        "no_end": no_end,
        "n_bars": len(bars),
        "n_no_end": len(no_end),
        "n_ended": sum(1 for b in bars if b["ended"]),
        "n_start_missing": sum(1 for b in bars if b["start_missing"]),
        "n_no_amount": sum(1 for b in bars if not number(b["amount"])),
        "amount_max": max(amounts) if amounts else None,
        "amount_sum": sum(amounts),
        "span": ((min(starts + [b["end"] for b in bars]).isoformat(), max(b["end"] for b in bars).isoformat()) if bars else None),
    }


def _bar_title(b, money_ok):
    period = (b["start"].isoformat() if b["start"] else "시작일 미기재") + " → " + b["end"].isoformat()
    status = "종료 경과" if b["ended"] else "진행 중(종료일 미도래)"
    amt = (fmt(b["amount"]) + " 백만원 · " + b["amount_source"]) if (money_ok and number(b["amount"])) else "금액 원문 없음"
    if b.get("withheld"):
        amt += " (" + b["withheld"] + ")"
    return " / ".join([b["name"], b["client_display"], period, domain_label(b["domain"]) + " · " + tier_label(b["tier"]), amt, status])


def gantt_svg(g, uid, money_ok=True):
    bars = g["bars"]
    if not bars:
        return "<p>종료일이 확인되는 계약이 없어 간트를 그리지 않습니다.</p>"
    today = date.fromisoformat(g["today"])
    d0 = min([b["start"] or b["end"] for b in bars] + [today])
    d1 = max([b["end"] for b in bars] + [today])
    pad = max(7, int((d1 - d0).days * 0.02))
    d0, d1 = d0 - timedelta(days=pad), d1 + timedelta(days=pad)
    span = max(1, (d1 - d0).days)
    x = lambda d: 310 + 670 * (d - d0).days / span
    n = len(bars)
    top, pitch = 44, 26
    h = top + n * pitch + 16
    amax = g["amount_max"] or 0
    chunks = [f"<div class='scroll'><svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1010 {h}' role='img' aria-labelledby='{uid}-title'>",
              f"<title id='{uid}-title'>계약공시 기준 수주 간트. 종료일 오름차순, 색=발전원, 두께=계약금액, 점선 세로선=오늘 {g['today']}. 상업운전일·공정률 선표가 아닙니다.</title>"]
    years = d1.year - d0.year
    step = 1 if years <= 14 else (2 if years <= 28 else 5)
    for yr in range(d0.year, d1.year + 1):
        d = date(yr, 1, 1)
        if d < d0 or d > d1:
            continue
        pos = x(d)
        chunks.append(f"<line x1='{pos:.2f}' x2='{pos:.2f}' y1='30' y2='{h - 14}' stroke='var(--ln)'/>")
        if yr % step == 0:
            chunks.append(f"<text x='{pos:.2f}' y='20' font-size='10' fill='var(--tx)'>{yr}</text>")
    tx = x(today)
    chunks.append(f"<line x1='{tx:.2f}' x2='{tx:.2f}' y1='26' y2='{h - 14}' stroke='var(--tx)' stroke-dasharray='4 3'/>")
    chunks.append(f"<text x='{tx + 3:.2f}' y='{h - 4}' font-size='10' fill='var(--tx)'>오늘 {g['today']}</text>")
    for i, b in enumerate(bars):
        yy = top + i * pitch
        color = domain_color(b["domain"])
        service = b["tier"] in SERVICE_TIERS
        has_amt = bool(money_ok and number(b["amount"]) and amax > 0)
        bh = (6 + 14 * math.sqrt(b["amount"] / amax)) if has_amt else 6.0
        op = 0.35 if b["ended"] else 1.0
        if service:
            op *= 0.55
        xb = x(b["end"])
        xa = x(b["start"]) if b["start"] is not None else None
        name_op = " fill-opacity='.6'" if b["ended"] else ""
        sub = b["client_display"] + " · " + tier_label(b["tier"]) + (" · SMR" if b["smr"] else "")
        chunks.append("<g class='gbar'><title>" + esc(_bar_title(b, money_ok)) + "</title>")
        chunks.append(f"<text x='4' y='{yy - 1}' font-size='10' fill='var(--tx)'{name_op}>" + esc(b["name"][:30]) + "</text>")
        chunks.append(f"<text x='4' y='{yy + 9}' font-size='9' class='sub'>" + esc(sub[:40]) + "</text>")
        if xa is None:
            # 시작일 미기재: 왼쪽 점선 리더 + 종료일 눈금만. 시작일을 추정해 채우지 않는다.
            chunks.append(f"<line x1='310' x2='{xb:.3f}' y1='{yy}' y2='{yy}' stroke='{color}' stroke-dasharray='3 3' stroke-opacity='{op:.2f}'/>")
            chunks.append(f"<rect x='{xb - 2:.3f}' y='{yy - bh / 2:.3f}' width='4' height='{bh:.3f}' fill='{color}' fill-opacity='{op:.2f}'/>")
        else:
            w = max(1.5, xb - xa)
            if has_amt:
                extra = f" stroke='{color}' stroke-width='1.5'" if service else ""
                chunks.append(f"<rect x='{xa:.3f}' y='{yy - bh / 2:.3f}' width='{w:.3f}' height='{bh:.3f}' rx='2' fill='{color}' fill-opacity='{op:.2f}'{extra}/>")
            else:
                chunks.append(f"<rect x='{xa:.3f}' y='{yy - bh / 2:.3f}' width='{w:.3f}' height='{bh:.3f}' rx='2' fill='none' stroke='{color}' stroke-dasharray='3 2' stroke-opacity='{op:.2f}'/>")
        if money_ok:
            lab = fmt0(b["amount"]) if has_amt else "금액 미공시"
            tw = 6.2 * len(lab) + 4
            if xb + tw <= 1006:
                lx, anchor, fill = xb + 4, "start", "var(--tx)"
            elif xa is not None and (xb - xa) >= tw + 6 and has_amt and op >= 0.6:
                lx, anchor, fill = (xa + xb) / 2, "middle", "var(--bg)"
            else:
                lx, anchor, fill = (xa if xa is not None else 310) - 4, "end", "var(--tx)"
            chunks.append(f"<text x='{lx:.2f}' y='{yy + 4}' font-size='10' text-anchor='{anchor}' fill='{fill}'>" + esc(lab) + "</text>")
        chunks.append("</g>")
    return "".join(chunks) + "</svg></div>"


def gantt_legend(g, money_ok):
    sw = []
    for k in DOMAIN_ORDER:
        label, color = DOMAINS[k]
        sw.append(f"<span><i class='sw' style='background:{color}'></i>{esc(label)}</span>")
    notes = ["채움=기자재·주기기·보조기기·계측제어·설계·EPC", "반투명+테두리=정비·검사·해체(서비스)",
             "점선 테두리=금액 원문 없음", "흐림=종료 경과", "왼쪽 점선=시작일 미기재(종료일 눈금만)"]
    if money_ok:
        notes.insert(0, "막대 두께=계약금액(√비례, 최대 " + fmt0(g["amount_max"]) + " 백만원) · 라벨=계약금액 백만원")
    else:
        notes.insert(0, "금액 단위 미확인 — 두께·라벨 없음(기간만)")
    return "<p class='legend'>" + "".join(sw) + "</p><p><small>" + " · ".join(esc(n) for n in notes) + "</small></p>"


# ---------- 뷰 2: 분기 전환 스케줄 ----------

def _shown(r):
    if number(r.get("value")):
        return r["value"], r.get("interval") or {}, "원장 전체 조건부 추정"
    if number(r.get("existing_backlog_revenue")):
        return r["existing_backlog_revenue"], r.get("partial_existing_interval") or {}, "미래 잔고분만"
    return r.get("covered_sites_partial_revenue"), r.get("covered_sites_partial_interval") or {}, "수록 일부 잔고분만"


def _estimates(forecast_entry, qkeys):
    """페이지에 이미 실린 Y+2 추정(분기)을 창 분기별로 꺼낸다. 없으면 왜 없는지 남긴다."""
    if forecast_entry is None:
        return {"usable": False, "reason": "이 회사의 Y+2 추정 항목이 없음(forecast_entry=None)", "scenarios": {}, "n_base_quarters": 0}
    mu = forecast_entry.get("money_unit")
    if mu not in (None, "KRW_million"):
        return {"usable": False, "reason": f"추정 금액 단위가 백만원으로 확인되지 않음(money_unit={mu})", "scenarios": {}, "n_base_quarters": 0}
    scen = forecast_entry.get("scenarios") or {}
    out = {}
    for key in SCENARIOS:
        s = scen.get(key) or {}
        qmap = {}
        for row in s.get("quarterly") or []:
            q = str(row.get("quarter") or "").strip()
            if q not in qkeys:
                continue
            v, ci, scope = _shown(row)
            qmap[q] = {"value": v if number(v) else None,
                       "lower": ci.get("lower") if number(ci.get("lower")) else None,
                       "upper": ci.get("upper") if number(ci.get("upper")) else None,
                       "scope": scope}
        out[key] = qmap
    base = out.get("base", {})
    n_base = sum(1 for q in qkeys if base.get(q, {}).get("value") is not None)
    return {"usable": True, "reason": "", "scenarios": out, "status": forecast_entry.get("status"),
            "origin": forecast_entry.get("origin"), "n_base_quarters": n_base}


def build_schedule(contracts, forecast_entry=None, window=DEFAULT_WINDOW, today=None):
    rows = normalize_contracts(contracts)
    today = _today(today)
    q0, q1 = qparse(window[0]), qparse(window[1])
    if q1 < q0:
        raise ValueError("window end before start")
    quarters = quarter_range(q0, q1)
    window_keys = [qkey(yq) for yq in quarters]

    def bucket(key, label, kind):
        return {"key": key, "label": label, "kind": kind, "n": 0, "amount": 0.0, "n_no_amount": 0,
                "by_domain": {}, "n_by_domain": {}, "items": []}

    buckets = OrderedDict()
    buckets["before"] = bucket("before", window[0] + " 이전 종료", "before")
    for k in window_keys:
        buckets[k] = bucket(k, k, "window")
    buckets["after"] = bucket("after", window[1] + " 이후 종료", "after")
    buckets["no_end"] = bucket("no_end", "종료일 없음", "no_end")
    for r in rows:
        if r["end"] is None:
            b = buckets["no_end"]
        else:
            yq = quarter_of(r["end"])
            if yq < q0:
                b = buckets["before"]
            elif yq > q1:
                b = buckets["after"]
            else:
                b = buckets[qkey(yq)]
        b["n"] += 1
        dk = domain_key(r["domain"])
        b["n_by_domain"][dk] = b["n_by_domain"].get(dk, 0) + 1
        if number(r["amount"]):
            b["amount"] += r["amount"]
            b["by_domain"][dk] = b["by_domain"].get(dk, 0.0) + r["amount"]
        else:
            b["n_no_amount"] += 1
        b["items"].append(r["id"])
    est = _estimates(forecast_entry, window_keys)
    win = [buckets[k] for k in window_keys]
    est_sum, est_q = {}, {}
    for key in SCENARIOS:
        qmap = est["scenarios"].get(key, {})
        vals = [qmap[q]["value"] for q in window_keys if qmap.get(q, {}).get("value") is not None]
        est_sum[key] = sum(vals) if vals else None
        est_q[key] = len(vals)
    amount_window = sum(b["amount"] for b in win)
    return {
        "today": today.isoformat(),
        "window": (window[0], window[1]),
        "window_keys": window_keys,
        "buckets": buckets,
        "estimates": est,
        "summary": {
            "n_total": len(rows),
            "amount_total": sum(b["amount"] for b in buckets.values()),
            "n_window": sum(b["n"] for b in win),
            "amount_window": amount_window,
            "n_no_amount_window": sum(b["n_no_amount"] for b in win),
            "estimate_window_sum": est_sum,
            "estimate_window_quarters": est_q,
            "gap_base": (amount_window - est_sum["base"]) if est_sum.get("base") is not None else None,
        },
    }


def schedule_svg(s, uid, money_ok=True):
    keys = s["window_keys"]
    buckets = s["buckets"]
    est = s["estimates"]
    base = est["scenarios"].get("base", {}) if est.get("usable") else {}
    unit = "백만원" if money_ok else "건"
    vals = [(buckets[q]["amount"] if money_ok else buckets[q]["n"]) for q in keys]
    ests = [base.get(q, {}).get("value") for q in keys] if money_ok else [None] * len(keys)
    ups = [base.get(q, {}).get("upper") for q in keys] if money_ok else [None] * len(keys)
    mx = max([1.0] + [v for v in vals if number(v)] + [v for v in ests if number(v)] + [v for v in ups if number(v)])
    left, bottom, height, width = 72, 182, 144, 730
    step = width / max(1, len(keys))
    y = lambda v: bottom - v / mx * height
    chunks = [f"<div class='scroll'><svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 840 226' role='img' aria-labelledby='{uid}-title'>",
              f"<title id='{uid}-title'>분기별 종료 계약 합계({unit}, 발전원별 누적)와 페이지의 Y+2 기준 추정(빈 막대). 창 {keys[0]}~{keys[-1]}.</title>",
              f"<line x1='{left}' x2='816' y1='{bottom}' y2='{bottom}' stroke='var(--ln)'/>",
              f"<text x='66' y='42' text-anchor='end' fill='var(--tx)' font-size='11'>{mx:,.0f}</text>",
              f"<text x='66' y='{bottom}' text-anchor='end' fill='var(--tx)' font-size='11'>0</text>"]
    for i, q in enumerate(keys):
        b = buckets[q]
        xc = left + (i + .5) * step
        parts = b["by_domain"] if money_ok else b["n_by_domain"]
        comp = ", ".join(domain_label(k) + " " + str(b["n_by_domain"][k]) + "건" for k in DOMAIN_ORDER if b["n_by_domain"].get(k))
        text = f"{q}: 끝나는 계약 {b['n']}건"
        if money_ok:
            text += f" · 합계 {fmt(b['amount'])} 백만원 · 금액 원문 없음 {b['n_no_amount']}건"
        text += " · " + (comp or "구성 없음")
        e = base.get(q) if est.get("usable") else None
        if e is not None:
            text += f" · 기준 추정 {fmt(e['value'])} ({e['scope']}; 민감도 {fmt(e['lower'])}~{fmt(e['upper'])})"
        elif est.get("usable"):
            text += " · 기준 추정 없음(해당 분기 행 없음)"
        else:
            text += " · 추정 없음: " + est.get("reason", "")
        chunks.append("<g><title>" + esc(text) + "</title>")
        offset = 0.0
        for k in DOMAIN_ORDER:
            v = parts.get(k)
            if not v:
                continue
            chunks.append(f"<rect x='{xc - 19:.3f}' y='{y(offset + v):.3f}' width='17' height='{v / mx * height:.3f}' fill='{domain_color(k)}'/>")
            offset += v
        chunks.append(f"<text x='{xc - 10.5:.3f}' y='{y(offset) - 3:.3f}' text-anchor='middle' fill='var(--tx)' font-size='9'>{b['n']}건</text>")
        if e is not None and number(e["value"]):
            chunks.append(f"<rect x='{xc + 2:.3f}' y='{y(e['value']):.3f}' width='17' height='{e['value'] / mx * height:.3f}' fill='none' stroke='var(--tx)' stroke-width='1.2'/>")
            if number(e["lower"]) and number(e["upper"]):
                cx = xc + 10.5
                chunks.append(f"<path d='M{cx:.3f},{y(e['lower']):.3f}V{y(e['upper']):.3f} M{cx - 4:.3f},{y(e['lower']):.3f}H{cx + 4:.3f} M{cx - 4:.3f},{y(e['upper']):.3f}H{cx + 4:.3f}' stroke='var(--tx)' fill='none'/>")
        elif money_ok and est.get("usable"):
            chunks.append(f"<text x='{xc + 10.5:.3f}' y='{bottom - 4}' text-anchor='middle' fill='var(--tx)' font-size='8'>추정 —</text>")
        chunks.append(f"<text x='{xc:.3f}' y='205' text-anchor='middle' fill='var(--tx)' font-size='10'>{esc(q)}</text></g>")
    return "".join(chunks) + "</svg></div>"


# ---------- 뷰 3: 발주처별 ----------

def _display_name(counter):
    if not counter:
        return "—"
    best = max(counter.items(), key=lambda kv: (kv[1], -len(kv[0])))
    return best[0]


def _kind_label(counter):
    if not counter:
        return "—"
    return " / ".join(KINDS.get(k, k) for k, _ in counter.most_common())


def build_clients(contracts, today=None, top_n=8):
    rows = normalize_contracts(contracts)
    today = _today(today)
    groups = OrderedDict()

    def get(key):
        if key not in groups:
            groups[key] = {"key": key, "raw_names": Counter(), "kinds": Counter(), "withheld": Counter(),
                           "n": 0, "amount": 0.0, "n_no_amount": 0, "n_active": 0, "amount_active": 0.0,
                           "n_no_end": 0, "latest_end": None, "anonymous": key == ANON_KEY, "ids": [], "members": 1}
        return groups[key]

    for r in rows:
        active = (not r["terminated"]) and (r["end"] is None or r["end"] >= today)
        key = ANON_KEY if r["anonymous"] else (client_key(r["client"]) or ANON_KEY)
        g = get(key)
        g["raw_names"][r["client"] or "-"] += 1
        g["kinds"][r["party_kind"] or "UNKNOWN"] += 1
        if r["withheld"]:
            g["withheld"][r["withheld"]] += 1
        g["n"] += 1
        g["ids"].append(r["id"])
        if number(r["amount"]):
            g["amount"] += r["amount"]
        else:
            g["n_no_amount"] += 1
        if r["end"] is None:
            g["n_no_end"] += 1
        elif g["latest_end"] is None or r["end"] > g["latest_end"]:
            g["latest_end"] = r["end"]
        if active:
            g["n_active"] += 1
            if number(r["amount"]):
                g["amount_active"] += r["amount"]
    anon = groups.get(ANON_KEY)
    named = [g for k, g in groups.items() if k != ANON_KEY]
    named.sort(key=lambda g: (-g["amount_active"], -g["amount"], -g["n"], g["key"]))
    totals = {
        "n": len(rows),
        "amount": sum(g["amount"] for g in groups.values()),
        "n_no_amount": sum(g["n_no_amount"] for g in groups.values()),
        "n_active": sum(g["n_active"] for g in groups.values()),
        "amount_active": sum(g["amount_active"] for g in groups.values()),
        "n_no_end": sum(g["n_no_end"] for g in groups.values()),
    }

    def merge(gs, label):
        m = {"key": "__rest__", "raw_names": Counter(), "kinds": Counter(), "withheld": Counter(), "n": 0,
             "amount": 0.0, "n_no_amount": 0, "n_active": 0, "amount_active": 0.0, "n_no_end": 0,
             "latest_end": None, "anonymous": False, "ids": [], "members": len(gs), "label": label}
        for g in gs:
            m["raw_names"].update(g["raw_names"])
            m["kinds"].update(g["kinds"])
            m["withheld"].update(g["withheld"])
            for f in ("n", "amount", "n_no_amount", "n_active", "amount_active", "n_no_end"):
                m[f] += g[f]
            m["ids"].extend(g["ids"])
            if g["latest_end"] is not None and (m["latest_end"] is None or g["latest_end"] > m["latest_end"]):
                m["latest_end"] = g["latest_end"]
        return m

    def finish(g, group, label=None):
        return {
            "name": label or g.get("label") or _display_name(g["raw_names"]),
            "group": group,
            "members": g["members"],
            "raw_variants": sorted(g["raw_names"]),
            "kind": _kind_label(g["kinds"]),
            "withheld_reasons": dict(g["withheld"]),
            "n": g["n"], "n_active": g["n_active"], "n_no_amount": g["n_no_amount"], "n_no_end": g["n_no_end"],
            "amount": g["amount"], "amount_active": g["amount_active"],
            "latest_end": g["latest_end"].isoformat() if g["latest_end"] else None,
            "share_active": pct(g["amount_active"], totals["amount_active"]),
            "share_all": pct(g["amount"], totals["amount"]),
            "anonymous": g["anonymous"],
            "ids": list(g["ids"]),
        }

    out_rows = [finish(g, "top") for g in named[:top_n]]
    rest = named[top_n:]
    if rest:
        out_rows.append(finish(merge(rest, f"그 밖의 {len(rest)}개 발주처"), "rest"))
    if anon:
        out_rows.append(finish(anon, "anon", "익명·공시유보(원문 표기 그대로)"))
    T = totals["amount_active"]
    named_shares = [pct(g["amount_active"], T) for g in named] if T > 0 else []
    conc = {
        "basis": "미종료(종료일 미도래 또는 미기재, 해지 제외) 계약금액 합계 대비",
        "named_count": len(named),
        "top1_name": out_rows[0]["name"] if named else None,
        "top1_share_active": out_rows[0]["share_active"] if named else None,
        "top3_share_active": (sum(x for x in [r["share_active"] for r in out_rows[:3] if r["group"] == "top"] if number(x)) if (named and T > 0) else None),
        "hhi_active_named": (sum(p * p for p in named_shares if number(p)) if named_shares else None),
        "anon_n": anon["n"] if anon else 0,
        "anon_amount_active": anon["amount_active"] if anon else 0.0,
        "anon_share_active": pct(anon["amount_active"], T) if anon else None,
    }
    return {"today": today.isoformat(), "top_n": top_n, "rows": out_rows, "totals": totals, "concentration": conc}


def clients_svg(c, uid, money_ok=True):
    rows = c["rows"]
    total = c["totals"]["amount_active"] if money_ok else c["totals"]["n"]
    if not rows or not total:
        return "<p>미종료 계약금액이 없어 집중도 막대를 그리지 않습니다(전부 종료 경과이거나 금액 원문 없음).</p>"
    basis = "미종료 계약금액" if money_ok else "계약 건수"
    chunks = [f"<div class='scroll'><svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 840 70' role='img' aria-labelledby='{uid}-title'>",
              f"<title id='{uid}-title'>발주처 집중도: {basis} 100% 누적 막대. 익명 묶음은 회색 점선.</title>",
              "<text x='8' y='12' font-size='10' fill='var(--tx)'>0%</text><text x='832' y='12' font-size='10' text-anchor='end' fill='var(--tx)'>100%</text>"]
    x0 = 8.0
    W = 824.0
    ni = 0
    for r in rows:
        v = r["amount_active"] if money_ok else r["n"]
        w = W * v / total if v else 0.0
        if w <= 0:
            continue
        share = pct(v, total)
        if r["group"] == "anon":
            style = "fill='#8a9bb0' fill-opacity='.5' stroke='#8a9bb0' stroke-dasharray='4 2'"
        elif r["group"] == "rest":
            style = "fill='#8a9bb0' fill-opacity='.8'"
        else:
            style = f"fill='var(--a)' fill-opacity='{max(0.25, 1.0 - 0.11 * ni):.2f}'"
            ni += 1
        title = f"{r['name']}: {fmt_pct(share)} · {r['n_active']}건 미종료 / {r['n']}건 전체"
        if money_ok:
            title += f" · 미종료 {fmt(r['amount_active'])} 백만원"
        chunks.append(f"<g><title>{esc(title)}</title><rect x='{x0:.2f}' y='18' width='{w:.2f}' height='28' {style}/>")
        if w >= 56:
            chunks.append(f"<text x='{x0 + w / 2:.2f}' y='36' font-size='10' text-anchor='middle' fill='var(--bg)'>{esc(r['name'][:8])} {fmt_pct(share)}</text>")
        chunks.append("</g>")
        x0 += w
    return "".join(chunks) + "</svg></div>"


# ---------- HTML 조립 ----------

def table(headers, rows, caption, num_cols=()):
    num = set(num_cols)
    head = "".join("<th scope='col'" + (" class='num'" if i in num else "") + ">" + esc(h) + "</th>" for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join("<td" + (" class='num'" if i in num else "") + ">" + esc(v) + "</td>" for i, v in enumerate(row)) + "</tr>" for row in rows)
    return "<div class='scroll'><table><caption>" + esc(caption) + "</caption><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table></div>"


def _money_status(panel_entry, rows):
    unit = panel_entry.get("money_unit", "KRW_million")
    if unit not in (None, "KRW_million"):
        return False, f"금액 단위 미확인(money_unit={unit}) — 건수·기간만 표시"
    if panel_entry.get("unit_seen") is False:
        return False, "표 단위 캡션 미확인(unit_seen=false) — 건수·기간만 표시"
    if rows and not any(number(r["amount"]) for r in rows):
        return False, "금액이 확인되는 계약이 없음 — 건수·기간만 표시"
    return True, "계약공시 계약금액 백만원(amt_krw_m) 그대로, 재배율 없음"


def render_orders_section(panel_entry, contracts, forecast_entry=None, today=None):
    stock = panel_entry.get("stock")
    name = panel_entry.get("co") or panel_entry.get("name") or "회사"
    if not isinstance(stock, str) or not re.fullmatch(r"\d{6}", stock):
        raise ValueError("invalid stock identity")
    if forecast_entry is not None:
        c = forecast_entry
        if c.get("stock") != stock or c.get("company_id") != stock or c.get("company_name") != name:
            raise ValueError("company_identity_conflict")
        source = panel_entry.get("src") or panel_entry.get("source")
        if source is not None and source != c.get("source"):
            raise ValueError("source_identity_conflict")
    today = _today(today if today is not None else (panel_entry.get("asof") or panel_entry.get("today")))
    rows = normalize_contracts(contracts, stock)
    money_ok, money_reason = _money_status(panel_entry, rows)
    g = build_gantt(rows, today)
    s = build_schedule(rows, forecast_entry, today=today)
    c = build_clients(rows, today)
    uid = "knuke-orders-" + stock
    money_attr = "KRW_million" if money_ok else "count_only"
    chunks = ["<style>" + CSS + "</style>",
              f"<section class='knuke-orders' id='{uid}' data-contracts='{len(rows)}' data-gantt-bars='{g['n_bars']}' data-gantt-noend='{g['n_no_end']}' data-money='{money_attr}' data-est-quarters='{s['estimates'].get('n_base_quarters', 0)}'>",
              f"<h2>{esc(name)} 수주 상세 <span class='badge'>계약공시 {len(rows)}건</span></h2>",
              f"<p>기준일 {today.isoformat()} · 원장: 단일판매ㆍ공급계약 공시 {len(rows)}건(입력 원장 기준) · 종료일 있음 {g['n_bars']}건 / 없음 {g['n_no_end']}건 / 종료 경과 {g['n_ended']}건 / 시작일 미기재 {g['n_start_missing']}건. 금액: {esc(money_reason)}.</p>",
              "<p class='warning'>계약기간은 공시상 납기·역무기간이며 상업운전일·실제 공정률과 다를 수 있습니다. 금액은 공시 계약금액(총액)이고 잔여 잔고가 아닙니다. —는 원문에 값이 없는 것이며 0이 아닙니다. 정기보고서 수주표와 범위가 달라 그 합계와 맞지 않을 수 있으며, 여기서 맞추지 않습니다.</p>"]
    if not rows:
        chunks.append("<p>이 회사의 계약공시 행이 없어 세 뷰를 그리지 않습니다.</p></section>")
        return "".join(chunks)

    # 1. 간트
    chunks.append("<h3>1. 수주 간트 — 계약별 시작~종료</h3>")
    chunks.append(gantt_legend(g, money_ok))
    chunks.append(gantt_svg(g, uid + "-gantt", money_ok))
    if g["no_end"]:
        rows_ = []
        for r in g["no_end"]:
            rows_.append([r["name"], r["client_display"], r["start"].isoformat() if r["start"] else "—",
                          r["signed"].isoformat() if r["signed"] else "—",
                          fmt(r["amount"]) if money_ok else "—", domain_label(r["domain"]) + " · " + tier_label(r["tier"]), r["reason"]])
        chunks.append(table(["사업·계약명", "발주처", "시작일", "공시일", "계약금액 백만원", "발전원 · 단계", "종료일이 없는 이유(원문 근거)"],
                            rows_, f"별도 묶음: 종료일이 없어 막대를 그리지 않은 계약 {len(g['no_end'])}건", num_cols=(4,)))
    else:
        chunks.append("<p><small>종료일이 없는 계약 없음.</small></p>")
    chunks.append(f"<p><small>막대 {g['n_bars']}개 = 종료일 있는 계약 {g['n_bars']}건. 종료 경과 {g['n_ended']}건은 흐리게 두어 연간 정비계약 같은 갱신 주기를 보이게 했습니다. 금액 원문 없음 {g['n_no_amount']}건은 점선 테두리.</small></p>")

    # 2. 분기 전환 스케줄
    keys = s["window_keys"]
    est = s["estimates"]
    sm = s["summary"]
    chunks.append(f"<h3>2. 분기 전환 스케줄 — 종료일 기준 {keys[0]}~{keys[-1]}</h3>")
    if est.get("usable"):
        chunks.append(f"<p>채운 막대: 그 분기에 끝나는 계약의 계약금액 합계(발전원별 누적). 빈 막대: 페이지에 실린 Y+2 <b>기준</b> 추정(원점 {esc(est.get('origin') or '미상')}, 상태 {esc(est.get('status') or '미상')}), 세로선은 민감도 범위. 두 값은 정의가 다릅니다(계약 총액의 종료 분기 귀속 vs 분기 매출 인식 추정치). 어긋나면 그대로 둡니다.</p>")
    else:
        chunks.append("<p>채운 막대: 그 분기에 끝나는 계약의 계약금액 합계(발전원별 누적). 추정 열은 비어 있음 — " + esc(est.get("reason", "")) + ".</p>")
    chunks.append(schedule_svg(s, uid + "-sched", money_ok))
    rows_ = []
    for q in keys:
        b = s["buckets"][q]
        comp = ", ".join(domain_label(k) + " " + str(b["n_by_domain"][k]) for k in DOMAIN_ORDER if b["n_by_domain"].get(k)) or "—"
        row = [q, b["n"], fmt(b["amount"]) if money_ok else "—", b["n_no_amount"], comp]
        for key in SCENARIOS:
            e = est["scenarios"].get(key, {}).get(q) if est.get("usable") else None
            row.append(fmt(e["value"]) if e else "—")
        eb = est["scenarios"].get("base", {}).get(q) if est.get("usable") else None
        row.append((fmt(eb["lower"]) + "~" + fmt(eb["upper"]) + " (" + eb["scope"] + ")") if eb else "—")
        row.append(fmt(b["amount"] - eb["value"]) if (money_ok and eb and number(eb["value"])) else "—")
        rows_.append(row)
    chunks.append(table(["분기", "끝나는 계약", "계약 합계 백만원", "금액 원문 없음", "발전원 구성(건)", "보수 추정", "기준 추정", "낙관 추정", "기준 민감도 범위(범위 뜻)", "계약 합계 − 기준 추정"],
                        rows_, "분기 전환 스케줄: 추정치 옆에 '이 분기에 끝나는 계약 N건·합계 M' · 백만원", num_cols=(1, 2, 3, 5, 6, 7, 9)))
    outside = []
    for k in ("before", "after", "no_end"):
        b = s["buckets"][k]
        outside.append(f"{b['label']} {b['n']}건" + (f"·합계 {fmt(b['amount'])}" if money_ok else ""))
    chunks.append("<p><small>창 밖: " + esc(" / ".join(outside)) + f". 창 안 {sm['n_window']}건 + 창 밖 {sm['n_total'] - sm['n_window']}건 = 전체 {sm['n_total']}건.</small></p>")
    if est.get("usable") and money_ok:
        eq = sm["estimate_window_quarters"]["base"]
        if sm["estimate_window_sum"]["base"] is not None:
            gap = sm["gap_base"]
            verdict = ("계약 합계가 추정보다 큼" if gap > 0 else ("계약 합계가 추정보다 작음" if gap < 0 else "일치"))
            chunks.append(f"<p class='warning'>창 합계 대조(기준 시나리오, 추정 있는 {eq}/{len(keys)}분기 기준): 끝나는 계약 합계 {fmt(sm['amount_window'])} vs 추정 합 {fmt(sm['estimate_window_sum']['base'])} → 차이 {fmt(gap)} 백만원 ({verdict}). 두 수는 같은 것을 재지 않으므로 어긋남을 조정하지 않았습니다. 창 안 금액 원문 없음 {sm['n_no_amount_window']}건은 계약 합계에서 빠져 있습니다.</p>")
        else:
            chunks.append("<p class='warning'>창 안 분기에 기준 추정값이 하나도 없어 대조하지 못했습니다(미추정은 0이 아님).</p>")
    elif est.get("usable") and not money_ok:
        chunks.append("<p class='warning'>계약 금액 단위가 확인되지 않아 추정치와 금액을 대조하지 않았습니다(건수만 표시).</p>")

    # 3. 발주처별
    conc = c["concentration"]
    chunks.append("<h3>3. 발주처(고객)별 — 건수·금액·최장 종료일·비중</h3>")
    chunks.append(f"<p>상위 {c['top_n']}개 발주처 + 나머지 묶음 + 익명 한 줄. 묶음 키는 법인 접미(㈜·주식회사)·영문 별칭 괄호·공백만 걷어낸 표기이며 원문 표기를 오른쪽에 그대로 둡니다. 사명 변경 전후(두산중공업↔두산에너빌리티)는 합치지 않았습니다. 비중 분모: {esc(conc['basis'])}.</p>")
    chunks.append(clients_svg(c, uid + "-clients", money_ok))
    rows_ = []
    for r in c["rows"]:
        raw = "; ".join(r["raw_variants"])
        if r["group"] == "anon" and r["withheld_reasons"]:
            raw += " · 사유: " + ", ".join(f"{k} ×{v}" for k, v in sorted(r["withheld_reasons"].items()))
        rows_.append([r["name"], r["kind"], r["n"], r["n_active"], fmt(r["amount"]) if money_ok else "—",
                      fmt(r["amount_active"]) if money_ok else "—", r["n_no_amount"],
                      (r["latest_end"] or "—") + (f" (종료일 없음 {r['n_no_end']}건)" if r["n_no_end"] else ""),
                      fmt_pct(r["share_active"]) if money_ok else "—", fmt_pct(r["share_all"]) if money_ok else "—", raw])
    t = c["totals"]
    rows_.append(["합계", "—", t["n"], t["n_active"], fmt(t["amount"]) if money_ok else "—", fmt(t["amount_active"]) if money_ok else "—",
                  t["n_no_amount"], "—", "100.0%" if (money_ok and t["amount_active"] > 0) else "—", "100.0%" if (money_ok and t["amount"] > 0) else "—", "—"])
    chunks.append(table(["발주처", "구분", "건수", "미종료 건수", "계약금액 합계 백만원", "미종료 계약금액 백만원", "금액 원문 없음", "최장 종료일", "미종료 금액 비중", "전체 금액 비중", "원문 표기"],
                        rows_, f"발주처별 집계 · 실명 {conc['named_count']}곳 · 익명 {conc['anon_n']}건", num_cols=(2, 3, 4, 5, 6, 8, 9)))
    if money_ok and t["amount_active"] > 0 and conc["named_count"]:
        hhi = conc["hhi_active_named"]
        chunks.append(f"<p>집중도(미종료 계약금액 기준): 1위 {esc(conc['top1_name'])} {fmt_pct(conc['top1_share_active'])} · 상위 3 {fmt_pct(conc['top3_share_active'])} · 실명 발주처 HHI {hhi:,.0f}(10,000 만점, 익명 {conc['anon_n']}건은 정체를 알 수 없어 HHI 에서 제외하고 분모에는 포함). 미종료 = 종료일 미도래 또는 미기재(해지 제외)이며 계약 총액 기준이라 잔여 잔고 비중과 다를 수 있습니다.</p>")
    elif money_ok:
        chunks.append("<p>미종료 계약금액이 0이어서 비중·집중도를 계산하지 않았습니다(전부 종료 경과이거나 금액 원문 없음).</p>")
    else:
        chunks.append("<p>금액 단위가 확인되지 않아 비중·집중도는 비워 두었습니다(건수만).</p>")
    chunks.append("</section>")
    return "".join(chunks)


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent
    parser.add_argument("--contracts", type=Path, default=root.parent / "input" / "knuke_contracts.json")
    parser.add_argument("--universe", type=Path, default=root.parent / "input" / "knuke_universe.json")
    parser.add_argument("--forecast-panel", type=Path, default=None, help="forecast_panel.json (companies[] with stock) — 있으면 나란히 표시")
    parser.add_argument("--output-dir", type=Path, default=root / "sections_orders")
    parser.add_argument("--today", default=None, help="YYYY-MM-DD (기본: 실행일)")
    parser.add_argument("--stock", default=None, help="한 종목만")
    args = parser.parse_args()
    data = json.loads(args.contracts.read_text(encoding="utf-8"))
    rows = data["rows"] if isinstance(data, dict) else data
    names = {}
    if args.universe and args.universe.exists():
        u = json.loads(args.universe.read_text(encoding="utf-8"))
        for r in u.get("rows", []):
            names[r["stock"]] = r.get("name")
    forecasts = {}
    if args.forecast_panel and args.forecast_panel.exists():
        p = json.loads(args.forecast_panel.read_text(encoding="utf-8"))
        for cpy in p.get("companies", []):
            forecasts[cpy["stock"]] = cpy
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stocks = sorted({r["stock"] for r in rows if r.get("stock")})
    if args.stock:
        stocks = [s for s in stocks if s == args.stock]
    n = 0
    for stock in stocks:
        mine = [r for r in rows if r.get("stock") == stock]
        fe = forecasts.get(stock)
        name = names.get(stock) or (fe or {}).get("company_name") or ("종목 " + stock)
        panel = {"stock": stock, "co": name}
        if fe is not None and fe.get("source") is not None:
            panel["src"] = fe.get("source")
        body = render_orders_section(panel, mine, fe, today=args.today)
        page = ("<!doctype html><html lang='ko'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>"
                + esc(name) + " 수주 상세</title><body style='margin:0;background:#091522'>" + body + "</body></html>")
        (args.output_dir / (stock + ".html")).write_text(page, encoding="utf-8")
        n += 1
    print(f"Rendered {n} company order-view pages: {args.output_dir}")


if __name__ == "__main__":
    main()
