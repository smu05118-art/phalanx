# 주의: kaero_forecast_section.py 와 같은 이유로 탭 접두를 붙인다 (섹터 도구의 동명 모듈 충돌 방지).
#!/usr/bin/env python3
"""KAERO company order-detail fragments — Gantt · quarter roll-off schedule · client view.

Inline SVG only, standard library only, no package imports (self-contained).

Integration (same convention as kaero_forecast_section.render_forecast_section):
    render_orders_section({'stock': code, 'co': name, 'src': 'kaero_reports'}, contracts, forecast_entry=None)
    contracts : rows of kaero_contracts.json (단일판매·공급계약 공시 원장; any stock — filtered by panel stock), or
                ledger_rows(report_company_entry) — 정기보고서 수주상황(상세) 원장 rows converted to the same shape.
    forecast_entry : the company's entry from the Y+2 forecast panel (optional). Used only for the
                     side-by-side column of the schedule view; never adjusted to match.
Run: python3 -B output/kaero_orders_views.py --contracts input/kaero_contracts.json \
        --universe input/kaero_universe.json [--reports input/kaero_reports.json] --output-dir output/preview
"""
import argparse
import calendar
import datetime as dt
import html
import json
import math
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

sys.dont_write_bytecode = True

# ---------------------------------------------------------------- constants
BASE_QUARTER = "2026Q2"          # T0 of the page's Y+2 estimate
SCHEDULE_START, SCHEDULE_N = "2026Q3", 10   # T+1 .. T+10 = 2026Q3 .. 2028Q4

DOMAIN_KO = OrderedDict([("space", "우주"), ("mro", "MRO"), ("engine", "엔진"), ("struct", "기체구조물"),
                         ("defav", "방산항공"), ("other", "기타·미상")])   # LOGIC §5: narrower meaning wins
DOMAIN_COLOR = {"space": "#8b5cf6", "mro": "#0891b2", "engine": "#d97706", "struct": "#16a34a",
                "defav": "#dc2626", "other": "#64748b"}
NATURE_KO = {"RSP": "RSP", "PBL": "PBL", "DEV": "개발", "MRO": "정비", "LTA": "LTA", "BATCH": "양산·단발"}
AMOUNT_KIND_KO = {"contract_total": "공시 계약금액(총액)", "closing_backlog": "수주잔고(기말)"}
PARTY_KIND_KO = {"GOV": "정부", "G2G": "정부간", "PRIME": "체계업체", "OEM": "OEM·Tier-1", "FOREIGN": "해외",
                 "DOMESTIC": "국내", "ANON": "익명", "UNKNOWN": "미기재", "LEDGER": "수주표"}
TABLE_DECIMALS = 1               # display rounding only; sums use raw values

# explicit spelling aliases (LOGIC §6: dictionary-expanded names are grade C = 추정). Keys/values are party_norm() output.
ALIASES = {"스피릿 에어로시스템즈": "spirit aerosystems", "엘아이지넥스원": "lig넥스원",
           "엘아이지디펜스앤에어로스페이스": "lig디펜스앤에어로스페이스"}
ANON_SUFFIX = ("기관", "업체", "기업", "고객", "고객사", "거래처", "발주처")
ANON_RE = re.compile(r"^(?:[A-Z]사|고객\s*\d*|거래처\s*\d*|.*(?:비공개|미공개|익명).*)$")
_LEGAL = re.compile(r"(주식회사|㈜|社|\b(?:incorporated|inc|ltd|limited|llc|corp|corporation|co|gmbh|plc|pte|"
                    r"s\.a\.u|s\.a|l\.p|sp\.z o\.o)\b\.?)", re.I)


# ---------------------------------------------------------------- small helpers
def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def fmt(v, nd=6):
    return ("{:,.%df}" % nd).format(v).rstrip("0").rstrip(".") if number(v) else "—"


def fmt0(v):
    return "{:,.0f}".format(v) if number(v) else "—"


def fmt1(v):
    return fmt(v, TABLE_DECIMALS)


def pct(v):
    return "{:.1f}%".format(v * 100) if number(v) else "—"


def clip(s, n):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def unit_label(cur):
    return {"KRW": "백만원 (KRW)", "USD": "백만달러 (USD)"}.get(cur, str(cur) + " 백만 단위")


def table(headers, rows, caption):
    """Same markup convention as kaero_forecast_section.table; host `.wrap` provides overflow-x:auto."""
    return ('<div class="wrap" style="overflow-x:auto"><table><caption>' + esc(caption) + '</caption><thead><tr>' +
            ''.join('<th scope="col">' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' +
            ''.join('<tr>' + ''.join(('<th scope="row">' if i == 0 else '<td>') + cell +
                                     ('</th>' if i == 0 else '</td>') for i, cell in enumerate(row)) + '</tr>' for row in rows) +
            '</tbody></table></div>')


# ---------------------------------------------------------------- dates / quarters
_D_YMD = re.compile(r"^(\d{4})[-.](\d{1,2})[-.](\d{1,2})$")
_D_YY_MD = re.compile(r"^(\d{2})-(\d{2})-(\d{2})$")
_D_YM = re.compile(r"^(\d{4})[-.](\d{1,2})$")
_D_Y = re.compile(r"^~?\s*(\d{4})\s*년?$")
_D_YY = re.compile(r"^~\s*(\d{2})\s*년$")


def _mk(out, y, mo, d, precision, note=""):
    if not 1990 <= y <= 2100:
        out["note"] = "연도 범위 밖(" + str(y) + ") — 날짜로 읽지 않음"
        return out
    try:
        out["date"] = dt.date(y, mo, d)
    except ValueError:
        out["note"] = "유효하지 않은 날짜 '" + out["raw"] + "'"
        return out
    out["precision"], out["note"] = precision, note
    return out


def parse_date(text, role="end"):
    """Fail-closed date reader for disclosure/ledger strings.

    Accepts YYYY-MM-DD, YYYY.MM.DD, YY-MM-DD (→20YY, flagged), YYYY.MM / YYYY-MM (month), YYYY / YYYY년 / ~YYYY년 /
    ~YY년 (year), and ranges 'A~B' (end→B, start→A). Quantities such as '400대' and '-' give date=None.
    Month/year precision is placed at period end for role='end' and period start for role='start' (flagged in note).
    """
    raw = "" if text is None else str(text).strip()
    out = {"date": None, "precision": None, "raw": raw, "note": ""}
    if raw in ("", "-", "—"):
        out["note"] = "원문 없음" if raw == "" else "원문 '-'"
        return out
    if "~" in raw and not raw.startswith("~"):
        left, right = [p.strip() for p in raw.split("~", 1)]
        sub = parse_date(right if role == "end" else left, role)
        sub["raw"] = raw
        sub["note"] = ("기간 표기의 " + ("종료" if role == "end" else "시작") + "값" + ("; " + sub["note"] if sub["note"] else ""))
        return sub
    m = _D_YMD.match(raw)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return _mk(out, y, mo, d, "day")
    m = _D_YY_MD.match(raw)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return _mk(out, 2000 + y, mo, d, "day", "2자리 연도 → 20" + m.group(1) + "년으로 읽음")
    m = _D_YM.match(raw)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if not 1 <= mo <= 12:
            out["note"] = "월 값 오류 '" + raw + "'"
            return out
        d = calendar.monthrange(y, mo)[1] if role == "end" else 1
        return _mk(out, y, mo, d, "month", "월 단위 → " + ("말일" if role == "end" else "1일") + "로 둠")
    m = _D_Y.match(raw)
    if m:
        y = int(m.group(1))
        return _mk(out, y, 12 if role == "end" else 1, 31 if role == "end" else 1, "year",
                   "연 단위 → " + ("12-31" if role == "end" else "01-01") + "로 둠")
    m = _D_YY.match(raw)
    if m:
        y = 2000 + int(m.group(1))
        return _mk(out, y, 12 if role == "end" else 1, 31 if role == "end" else 1, "year",
                   "2자리 연도 → " + str(y) + "년, 연 단위 → " + ("12-31" if role == "end" else "01-01") + "로 둠")
    out["note"] = "날짜로 읽지 않음(원문 '" + raw + "')"
    return out


def quarter_of(d):
    return "%dQ%d" % (d.year, (d.month - 1) // 3 + 1)


def quarter_seq(start, n):
    y, q = int(start[:4]), int(start[5:])
    out = []
    for _ in range(n):
        out.append("%dQ%d" % (y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


QUARTERS = quarter_seq(SCHEDULE_START, SCHEDULE_N)


def _today(today):
    if today is None:
        return dt.date.today()
    if isinstance(today, dt.datetime):
        return today.date()
    if isinstance(today, dt.date):
        return today
    r = parse_date(str(today), "end")
    if r["date"] is None or r["precision"] != "day":
        raise ValueError("invalid today: " + str(today))
    return r["date"]


# ---------------------------------------------------------------- parties
def party_norm(p):
    """Transparent spelling normaliser for grouping (no semantic merging): drops parentheticals, legal-form tokens,
    a leading '대한민국', trailing punctuation; casefolds Latin."""
    s = "" if p is None else str(p)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"^\s*대한민국\s+", "", s)
    s = _LEGAL.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.·")
    return s.casefold()


def is_anonymous(party, party_kind=None, customers=None):
    """True when the counterparty is not a real name: withheld ('-'/blank), ANON/UNKNOWN kinds, or a generic
    descriptor such as '해외 정부기관', '미국 글로벌 우주항공 발사업체', 'A사'. A mapped customer overrides."""
    if customers:
        return False
    p = ("" if party is None else str(party)).strip()
    if not p or p in ("-", "—") or party_kind in ("ANON", "UNKNOWN"):
        return True
    if p.endswith(ANON_SUFFIX):
        return True
    return bool(ANON_RE.match(p))


def _anon_reason(party, party_kind, withheld):
    p = ("" if party is None else str(party)).strip()
    if not p or p in ("-", "—"):
        return "상대 미기재" + (" — 공시 유보: " + withheld if withheld else "")
    if party_kind == "ANON":
        return "익명 표기 '" + p + "'"
    return "일반 명칭 '" + p + "'" + (" — 공시 유보: " + clip(withheld, 40) if withheld else "")


# ---------------------------------------------------------------- normalisation
def normalize_contract(row, index=0, strict_units=False, self_stock=None, self_name=None):
    """One record shape for both sources. Idempotent on already-normalised rows."""
    if not isinstance(row, dict):
        raise ValueError("contract row must be a dict")
    if row.get("_norm"):
        return row
    if "closing" in row or ("label" in row and "rcp" not in row):
        return _from_ledger(row, index, self_stock, self_name)
    return _from_disclosure(row, index, strict_units)


def _from_disclosure(row, index, strict_units):
    title = str(row.get("title") or "")
    kind = "termination" if "해지" in title else "contract"
    name = str(row.get("name") or "").strip()
    if name in ("", "-"):
        name = "(계약명 미공시)"
    withheld = str(row.get("withheld") or "").strip()
    withheld = "" if withheld == "-" else withheld
    withheld_until = str(row.get("withheld_until") or "").strip()
    withheld_until = "" if withheld_until == "-" else withheld_until
    withheld_text = withheld + (" (유보기한 " + withheld_until + ")" if withheld and withheld_until else "")

    amount = float(row["amount"]) if number(row.get("amount")) else None
    cur = str(row.get("cur")).strip() if row.get("cur") else None
    label = str(row.get("amount_label") or "")
    amount_note = ""
    if amount is None:
        unit_status = "none"
        if kind == "termination":
            amount_note = "해지 공시 — 계약금액 없음"
        elif withheld:
            amount_note = "공시 유보: " + withheld_text
        else:
            amount_note = "공시 원문에 계약금액 없음"
    elif not cur:
        unit_status, amount, amount_note = "none", None, "통화 미확정 — 금액 제외 (" + label + ")"
    elif "통화 표기 없음" in label:
        if strict_units:
            unit_status, amount, cur, amount_note = "excluded", None, None, "통화 표기 없음 — 엄격 모드에서 금액 제외 (" + label + ")"
        else:
            unit_status, amount_note = "assumed", "통화 표기 없음 — 원으로 읽음 (" + label + ")"
    else:
        unit_status = "stated"

    start = parse_date(row.get("start"), "start")
    start_basis = "공시 시작일" if start["date"] else ""
    signed = str(row.get("signed") or "").strip()
    if start["date"] is None and signed not in ("", "-"):
        s2 = parse_date(signed, "start")
        if s2["date"]:
            start, start_basis = s2, "시작일 미기재 — 계약(체결)일로 대체"
    end = parse_date(row.get("end"), "end")
    end_raw = str(row.get("end_raw") if row.get("end_raw") is not None else (row.get("end") or "")).strip()
    end_reason = ""
    if end["date"] is None:
        note = str(row.get("note") or "")
        m = re.search(r"[^.。]*종료일[^.。]*", note)
        if withheld and end_raw in ("", "-"):
            end_reason = "공시 유보: " + withheld_text
        elif m:
            end_reason = "공시 주석: " + m.group(0).strip()
        elif end_raw == "":
            end_reason = "공시 원문에 종료일 없음"
        elif end_raw == "-":
            end_reason = "공시 원문 종료일 '-' (미정)"
        else:
            end_reason = end["note"]

    party = str(row.get("party") or "").strip()
    party_kind = row.get("party_kind") or ("UNKNOWN" if party in ("", "-") else "")
    customers = [c for c in (row.get("customers") or []) if isinstance(c, dict) and c.get("name")]
    anonymous = is_anonymous(party, party_kind, customers)
    return {
        "_norm": True, "source": "disclosure", "index": index,
        "id": str(row.get("rcp") or ("row%d" % index)), "stock": row.get("stock"), "name": name, "title": title, "kind": kind,
        "domain": row.get("domain") or "other", "nature": row.get("nature") or "",
        "cur": cur, "amount": amount, "amount_kind": "contract_total", "unit_status": unit_status, "amount_note": amount_note,
        "start": start["date"], "start_precision": start["precision"], "start_note": start["note"], "start_basis": start_basis,
        "end": end["date"], "end_precision": end["precision"], "end_note": end["note"], "end_raw": end_raw, "end_reason": end_reason,
        "party": party, "party_kind": party_kind, "party_tier": row.get("party_tier"), "customers": customers,
        "anonymous": anonymous, "anon_reason": _anon_reason(party, party_kind, withheld) if anonymous else "",
        "region": row.get("region") or "", "note": row.get("note") or "", "withheld": withheld, "withheld_until": withheld_until,
        "corrected": bool(row.get("corrected")), "supersedes": row.get("supersedes"), "signed": signed,
        "rev_ratio": row.get("rev_ratio"),
    }


def _from_ledger(row, index, self_stock=None, self_name=None):
    label = str(row.get("label") or "").strip() or "(품목 없음)"
    customers = [c for c in (row.get("customers") or []) if isinstance(c, dict) and c.get("name")]
    others = [c for c in customers if not (self_stock and c.get("stock") == self_stock) and not (self_name and c.get("name") == self_name)]
    party = str(others[0]["name"]) if others else ""
    due = str(row.get("due") if row.get("due") is not None else "").strip()
    order_date = str(row.get("order_date") if row.get("order_date") is not None else "").strip()
    end = parse_date(due, "end")
    start = parse_date(order_date, "start")
    start_basis = "수주표 수주일자" if start["date"] else ""
    if start["date"] is None and "~" in due and not due.startswith("~"):
        start = parse_date(due, "start")
        start_basis = "수주표 납기 기간 표기의 시작값" if start["date"] else ""
    amount = float(row["closing"]) if number(row.get("closing")) else None
    cur = str(row.get("cur")).strip() if row.get("cur") else None
    if amount is not None and not cur:
        amount = None
    return {
        "_norm": True, "source": "ledger", "index": index,
        "id": "ledger:%d" % index, "stock": self_stock, "name": label, "title": "정기보고서 수주상황(상세)", "kind": "contract",
        "domain": row.get("domain") or "other", "nature": row.get("nature") or "",
        "cur": cur, "amount": amount, "amount_kind": "closing_backlog",
        "unit_status": "stated" if amount is not None else "none",
        "amount_note": "" if amount is not None else "수주표에 잔고 없음",
        "start": start["date"], "start_precision": start["precision"], "start_note": start["note"], "start_basis": start_basis,
        "end": end["date"], "end_precision": end["precision"], "end_note": end["note"], "end_raw": due,
        "end_reason": "" if end["date"] else ("수주표 납기 '" + due + "' — " + end["note"]),
        "party": party, "party_kind": "LEDGER" if others else "UNKNOWN", "party_tier": others[0].get("tier") if others else None,
        "customers": others, "anonymous": not others, "anon_reason": "" if others else "수주표에 발주처 없음(품목 열만 있음)",
        "region": "", "note": "", "withheld": "", "withheld_until": "", "corrected": False, "supersedes": None, "signed": "",
        "rev_ratio": None, "seg": row.get("seg"), "tab": row.get("tab"), "gross": row.get("gross"), "delivered": row.get("delivered"),
    }


class LedgerRows(list):
    """list of normalised ledger rows with `.meta` (quarter, rcp, excluded_by_tab, ...)."""

    def __init__(self, rows, meta):
        super().__init__(rows)
        self.meta = meta


def ledger_rows(company_entry, quarter=None, tabs=("kaero", None)):
    """Convert kaero_reports.json company entry → contract rows (LOGIC §2: only this tab's segment rows)."""
    qs = company_entry.get("quarters") or {}
    if quarter is None:
        eligible = [q for q, v in qs.items() if isinstance(v, dict) and v.get("ok") and v.get("contracts")]
        quarter = max(eligible) if eligible else None
    if quarter is None or quarter not in qs:
        return LedgerRows([], {"quarter": None, "reason": "적격 분기(ok·contracts) 없음", "excluded_by_tab": {}})
    entry = qs[quarter]
    rows, excluded = [], Counter()
    for i, r in enumerate(entry.get("contracts") or []):
        if r.get("tab") not in tabs:
            excluded[str(r.get("tab"))] += 1
            continue
        rows.append(_from_ledger(r, i, company_entry.get("stock"), company_entry.get("name")))
    return LedgerRows(rows, {"quarter": quarter, "rcp": entry.get("rcp"), "title": entry.get("title"),
                             "excluded_by_tab": dict(excluded), "backlog": entry.get("backlog"), "shapes": entry.get("shapes")})


def prepare_contracts(contracts, stock=None, name=None, strict_units=False):
    """Filter to the company, drop superseded disclosures, normalise. Returns (rows, meta)."""
    meta = {"n_input": len(contracts), "dropped_other_stock": 0, "dropped_superseded": 0, "source": None}
    if isinstance(contracts, LedgerRows):
        meta["ledger"] = dict(contracts.meta)
    superseded = {r.get("supersedes") for r in contracts if isinstance(r, dict) and r.get("supersedes")}
    rows = []
    for i, r in enumerate(contracts):
        if not isinstance(r, dict):
            continue
        if stock and r.get("stock") not in (None, "", stock):
            meta["dropped_other_stock"] += 1
            continue
        if r.get("rcp") and r["rcp"] in superseded:
            meta["dropped_superseded"] += 1
            continue
        rows.append(normalize_contract(r, i, strict_units, stock, name))
    kinds = Counter(r["source"] for r in rows)
    meta["source"] = "ledger" if kinds.get("ledger") and not kinds.get("disclosure") else "disclosure" if kinds.get("disclosure") else None
    meta["amount_kinds"] = sorted(Counter(r["amount_kind"] for r in rows))
    return rows, meta


# ---------------------------------------------------------------- view 1: Gantt
def _status(c, today):
    if c["end"] and c["end"] < today:
        return "ended"
    if c["start"] and c["start"] > today:
        return "future"
    return "active"


def _tooltip(c):
    bits = [c["name"], "발주처 " + (c["party"] or "미기재") + (" (익명·미공개)" if c["anonymous"] else ""),
            "영역 " + DOMAIN_KO.get(c["domain"], c["domain"]) + " · 성격 " + NATURE_KO.get(c["nature"], c["nature"] or "미상"),
            "기간 " + (c["start"].isoformat() if c["start"] else "시작 미기재") + " ~ " + (c["end"].isoformat() if c["end"] else "종료 미기재")]
    if c["start_basis"] and c["start_basis"] != "공시 시작일":
        bits.append(c["start_basis"])
    if c["end_note"]:
        bits.append("종료일 " + c["end_note"])
    if number(c["amount"]):
        bits.append("금액 " + fmt1(c["amount"]) + " " + unit_label(c["cur"]) + " (" + AMOUNT_KIND_KO[c["amount_kind"]] + ")")
        if c["unit_status"] == "assumed":
            bits.append(c["amount_note"])
    else:
        bits.append("금액 — " + c["amount_note"])
    return " | ".join(bits)


def build_gantt(contracts, today=None, uid="kaero-gantt", strict_units=False, self_stock=None, self_name=None):
    """Bars for every contract with a readable end date, sorted by end; no-end and terminated rows kept aside."""
    today = _today(today)
    rows = [normalize_contract(r, i, strict_units, self_stock, self_name) for i, r in enumerate(contracts)]
    bars, no_end, excluded = [], [], []
    for c in rows:
        if c["kind"] != "contract":
            excluded.append(dict(c, exclude_reason="해지 공시 — 잔고가 아니므로 막대에서 제외"))
        elif c["end"]:
            bars.append(dict(c))
        else:
            no_end.append(dict(c))
    bars.sort(key=lambda c: (c["end"], c["start"] or c["end"], c["name"]))
    amax = {}
    for c in bars:
        if number(c["amount"]) and c["cur"]:
            amax[c["cur"]] = max(amax.get(c["cur"], 0.0), abs(c["amount"]))
    for c in bars:
        c["status"] = _status(c, today)
        if number(c["amount"]) and c["cur"] and amax.get(c["cur"]):
            c["height"] = 6.0 + 16.0 * math.sqrt(abs(c["amount"]) / amax[c["cur"]])
            c["amount_label"] = fmt0(c["amount"]) + ("*" if c["unit_status"] == "assumed" else "")
        else:
            c["height"] = 8.0
            c["amount_label"] = "— " + ("유보" if "유보" in c["amount_note"] else "없음")
        c["tooltip"] = _tooltip(c)
    axis = None
    if bars:
        first = min((c["start"] or c["end"]) for c in bars)
        last = max(c["end"] for c in bars)
        x0 = dt.date(min(first.year, today.year), 1, 1)
        x1 = dt.date(max(last.year, today.year) + 1, 1, 1)
        axis = {"x0": x0, "x1": x1}
    domains_present = [d for d in DOMAIN_KO if any(c["domain"] == d for c in bars)]
    if any(c["domain"] not in DOMAIN_KO for c in bars):
        domains_present.append("other") if "other" not in domains_present else None
    model = {"today": today, "bars": bars, "no_end": no_end, "excluded": excluded, "axis": axis,
             "amount_max_by_cur": amax, "domains_present": domains_present, "n_rows": len(rows), "uid": uid}
    model["desc"] = ("막대 %d건 · 종료일 없음 %d건 별도 · 제외 %d건" % (len(bars), len(no_end), len(excluded)) +
                     (" · 축 %s~%s · 오늘 %s" % (axis["x0"].isoformat(), axis["x1"].isoformat(), today.isoformat()) if axis else ""))
    model["svg"] = gantt_svg(model)
    return model


def gantt_svg(model):
    bars, axis, today, uid = model["bars"], model["axis"], model["today"], model["uid"]
    if not bars or not axis:
        return ""
    W, LW, RW, TOP, RH = 1000, 300, 118, 64, 22
    PX0, PX1 = LW + 8, W - RW
    H = TOP + RH * len(bars) + 14
    x0, x1 = axis["x0"], axis["x1"]
    span = max(1, (x1 - x0).days)

    def X(d):
        return PX0 + (d - x0).days / span * (PX1 - PX0)

    p = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" role="img" aria-labelledby="%s-title %s-desc" '
         'style="min-width:880px;width:100%%;height:auto;display:block">' % (W, H, uid, uid),
         '<title id="%s-title">수주 간트 — %d건, 종료일 순</title>' % (uid, len(bars)),
         '<desc id="%s-desc">%s</desc>' % (uid, esc(model["desc"]))]
    lx = PX0
    for dom in model["domains_present"]:
        label = DOMAIN_KO.get(dom, dom)
        p.append('<rect x="%d" y="8" width="12" height="12" rx="2" fill="%s"/><text x="%d" y="18" font-size="11" fill="currentColor">%s</text>'
                 % (lx, DOMAIN_COLOR.get(dom, DOMAIN_COLOR["other"]), lx + 16, esc(label)))
        lx += 16 + 11 * len(label) + 14
    years = list(range(x0.year, x1.year + 1))
    step = max(1, int(math.ceil(len(years) / 14.0)))
    for y in years[::step]:
        x = X(dt.date(y, 1, 1))
        p.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" style="stroke:var(--ln,#40546b)" stroke-width="1"/>' % (x, x, TOP - 6, H - 8))
        p.append('<text x="%.1f" y="%d" text-anchor="middle" font-size="10" fill="currentColor">%d</text>' % (x, TOP - 10, y))
    tx = X(today)
    p.append('<line data-today="%s" x1="%.1f" x2="%.1f" y1="%d" y2="%d" style="stroke:var(--a,#f59e0b)" stroke-width="1.5" stroke-dasharray="4 3"/>'
             % (today.isoformat(), tx, tx, TOP - 20, H - 8))
    p.append('<text x="%.1f" y="%d" text-anchor="middle" font-size="10" style="fill:var(--a,#f59e0b)">오늘 %s</text>' % (tx, TOP - 24, today.isoformat()))
    for i, b in enumerate(bars):
        cy = TOP + RH * i + RH / 2.0
        color = DOMAIN_COLOR.get(b["domain"], DOMAIN_COLOR["other"])
        xe = X(b["end"])
        xs = X(b["start"]) if b["start"] else xe - 3
        xs = max(PX0, min(xs, xe))
        w = max(2.0, xe - xs)
        h = b["height"]
        y = cy - h / 2.0
        has_amount = number(b["amount"])
        p.append('<g data-bar="1" data-id="%s" data-domain="%s" data-status="%s" opacity="%s"><title>%s</title>'
                 % (esc(b["id"]), esc(b["domain"]), b["status"], ".45" if b["status"] == "ended" else "1", esc(b["tooltip"])))
        p.append('<text x="4" y="%.1f" font-size="11" fill="currentColor">%s</text>' % (cy + 4, esc(clip(b["name"], 24))))
        p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" fill="%s" stroke="%s" stroke-width="1"%s/>'
                 % (xs, y, w, h, color if has_amount else "none", color, "" if has_amount else ' stroke-dasharray="3 2"'))
        if not b["start"]:
            p.append('<path d="M%.1f,%.1f l7,-5 v10 z" fill="%s"/>' % (xs - 7, cy, color))
        p.append('<text x="%d" y="%.1f" font-size="11" fill="currentColor">%s</text></g>' % (PX1 + 6, cy + 4, esc(b["amount_label"])))
    p.append("</svg>")
    return "".join(p)


def _row_cells(c, with_status=False):
    cells = [esc(c["name"]), esc((c["party"] or "미기재") + (" (익명·미공개)" if c["anonymous"] else "")),
             esc(DOMAIN_KO.get(c["domain"], c["domain"])), esc(NATURE_KO.get(c["nature"], c["nature"] or "미상")),
             esc(c["start"].isoformat() if c["start"] else "—") + (esc(" ※" + c["start_basis"]) if c["start_basis"] and c["start_basis"] not in ("공시 시작일", "수주표 수주일자") else ""),
             esc(c["end"].isoformat() if c["end"] else "—") + (esc(" ※" + c["end_note"]) if c["end"] and c["end_note"] else ""),
             (fmt1(c["amount"]) + (" *" if c["unit_status"] == "assumed" else "") + " " + esc(c["cur"])) if number(c["amount"]) else "— " + esc(c["amount_note"])]
    if with_status:
        cells.append({"ended": "종료일 경과", "future": "시작 전", "active": "진행 중"}[c["status"]])
    return cells


def gantt_html(model, uid):
    parts = ['<h3 id="%s-gantt-h">수주 간트</h3>' % uid,
             '<p>막대 = 시작~종료(예정)일, 정렬 = 종료일. 색 = 우주항공 영역(우주 › MRO › 엔진 › 기체구조물 › 방산항공 › 기타·미상, LOGIC §5). '
             '두께 = 통화별 최대 금액 대비 √척도, 오른쪽 라벨 = 금액(백만 단위, * 통화 표기 없음·원으로 읽음). '
             '세로 점선 = 오늘. 흐린 막대 = 종료일 경과. 점선 테두리 = 금액 미공개. ◁ = 시작일 미기재(종료일 위치에만 표시). 막대 위에 마우스를 올리면 상세가 보입니다.</p>']
    if model["bars"]:
        parts.append('<div class="wrap" style="overflow-x:auto">' + model["svg"] + '</div>')
        parts.append('<details><summary>간트 표 %d건</summary>' % len(model["bars"]) +
                     table(["계약", "발주처", "영역", "성격", "시작", "종료(예정)", "금액", "상태"],
                           [_row_cells(c, True) for c in model["bars"]], "간트 막대와 같은 순서(종료일 오름차순)") + '</details>')
    else:
        parts.append('<p data-gantt-status="empty">종료일을 읽을 수 있는 계약이 없어 간트를 그리지 않았습니다.</p>')
    if model["no_end"]:
        parts.append('<details open><summary>종료일 없는 계약 %d건 — 별도 묶음</summary>' % len(model["no_end"]) +
                     '<p>종료일이 없으면 막대 길이를 정할 수 없어 간트와 분기 스케줄에서 뺐습니다. 아래에 원문이 비어 있는 이유를 적었습니다.</p>' +
                     table(["계약", "발주처", "영역", "성격", "시작", "종료(예정)", "금액", "비어 있는 이유"],
                           [_row_cells(c)[:6] + [_row_cells(c)[6], esc(c["end_reason"] or c["end_note"] or "미상")] for c in model["no_end"]],
                           "종료일 없음 — 추정으로 메우지 않음") + '</details>')
    if model["excluded"]:
        parts.append('<details><summary>막대에서 제외 %d건</summary>' % len(model["excluded"]) +
                     table(["계약", "발주처", "영역", "성격", "시작", "종료(예정)", "금액", "제외 사유"],
                           [_row_cells(c)[:6] + [_row_cells(c)[6], esc(c["exclude_reason"])] for c in model["excluded"]], "해지 공시 등") + '</details>')
    return "".join(parts)


# ---------------------------------------------------------------- view 2: quarter roll-off schedule
def _shown(row):
    """Same display rule as kaero_forecast_section.shown: total → future-backlog-only → covered-subset."""
    if number(row.get("value")):
        return row["value"], row.get("interval") or {}, "전체 원장 추정"
    if number(row.get("existing_backlog_revenue")):
        return row["existing_backlog_revenue"], row.get("partial_existing_interval") or {}, "미래 잔고분만"
    if number(row.get("covered_sites_partial_revenue")):
        return row["covered_sites_partial_revenue"], row.get("covered_sites_partial_interval") or {}, "일부 잔고분만"
    return None, {}, "미추정"


def _forecast_for(forecast_entry, cur, quarters, scenario="base"):
    if forecast_entry is None:
        return {"status": "none", "reason": "추정 항목 없음(forecast_entry 미제공)", "scenario": scenario, "by_quarter": {}}
    panel = None
    for ch in forecast_entry.get("currency_panels") or []:
        if ch.get("currency") == cur:
            panel = ch
            break
    if panel is None:
        return {"status": "no_panel", "reason": "이 통화(%s)의 추정 패널 없음" % cur, "scenario": scenario, "by_quarter": {}}
    if panel.get("money_unit") != cur + "_million":
        return {"status": "unit_mismatch", "reason": "추정 단위 %s ≠ 계약 단위 %s_million — 비교 보류" % (panel.get("money_unit"), cur),
                "scenario": scenario, "by_quarter": {}}
    scen = (panel.get("scenarios") or {}).get(scenario)
    if not scen:
        return {"status": "no_scenario", "reason": "%s 시나리오 없음" % scenario, "scenario": scenario, "by_quarter": {}}
    byq = {}
    for r in scen.get("quarterly") or []:
        q = r.get("quarter")
        if q not in quarters:
            continue
        shown, bounds, basis = _shown(r)
        byq[q] = {"value": r.get("value") if number(r.get("value")) else None,
                  "existing": r.get("existing_backlog_revenue") if number(r.get("existing_backlog_revenue")) else None,
                  "partial": r.get("covered_sites_partial_revenue") if number(r.get("covered_sites_partial_revenue")) else None,
                  "shown": shown, "basis": basis,
                  "lower": bounds.get("lower") if number(bounds.get("lower")) else None,
                  "upper": bounds.get("upper") if number(bounds.get("upper")) else None}
    return {"status": "ok", "reason": "", "scenario": scenario, "by_quarter": byq,
            "estimate_status": panel.get("estimate_status"), "reported_backlog": (panel.get("coverage") or {}).get("reported_backlog")}


def build_schedule(contracts, forecast_entry=None, quarters=None, today=None, uid="kaero-schedule",
                   strict_units=False, self_stock=None, self_name=None):
    """End dates bucketed by quarter (window + before/after/no-end so totals reconcile), per currency, no conversion.
    The page's Y+2 estimate is placed beside each quarter and never adjusted."""
    today = _today(today)
    quarters = list(quarters or QUARTERS)
    rows = [normalize_contract(r, i, strict_units, self_stock, self_name) for i, r in enumerate(contracts)]
    terminated = [c for c in rows if c["kind"] != "contract"]
    rows = [c for c in rows if c["kind"] == "contract"]
    keys = ["before"] + quarters + ["after", "no_end"]
    buckets = OrderedDict((k, {"key": k, "n": 0, "n_no_amount": 0, "n_by_cur": {}, "sum": {}, "by_domain": {}, "items": []}) for k in keys)
    for c in rows:
        if c["end"] is None:
            k = "no_end"
        else:
            q = quarter_of(c["end"])
            k = "before" if q < quarters[0] else "after" if q > quarters[-1] else q
        b = buckets[k]
        b["n"] += 1
        b["items"].append(c["id"])
        if number(c["amount"]) and c["cur"]:
            cur = c["cur"]
            b["n_by_cur"][cur] = b["n_by_cur"].get(cur, 0) + 1
            b["sum"][cur] = b["sum"].get(cur, 0.0) + c["amount"]
            dom = c["domain"] if c["domain"] in DOMAIN_KO else "other"
            b["by_domain"].setdefault(cur, {})
            b["by_domain"][cur][dom] = b["by_domain"][cur].get(dom, 0.0) + c["amount"]
        else:
            b["n_no_amount"] += 1
    currencies = sorted({c["cur"] for c in rows if number(c["amount"]) and c["cur"]})
    totals = {cur: sum(b["sum"].get(cur, 0.0) for b in buckets.values()) for cur in currencies}
    counts = {cur: sum(b["n_by_cur"].get(cur, 0) for b in buckets.values()) for cur in currencies}
    window = {cur: sum(buckets[q]["sum"].get(cur, 0.0) for q in quarters) for cur in currencies}
    forecast = {cur: _forecast_for(forecast_entry, cur, quarters) for cur in currencies}
    if not currencies and forecast_entry is not None:
        forecast["__none__"] = {"status": "no_contract_amounts", "reason": "계약 금액이 없어 비교 대상 없음", "by_quarter": {}}
    comparison = {}
    for cur in currencies:
        fq = forecast[cur]["by_quarter"]
        comp = []
        for q in quarters:
            csum = buckets[q]["sum"].get(cur, 0.0)
            f = fq.get(q)
            fv = f["shown"] if f else None
            comp.append({"quarter": q, "n": buckets[q]["n_by_cur"].get(cur, 0), "n_no_amount": buckets[q]["n_no_amount"], "contract_sum": csum,
                         "forecast": fv, "basis": (f["basis"] if f else forecast[cur]["reason"] or "추정 없음"),
                         "lower": f["lower"] if f else None, "upper": f["upper"] if f else None,
                         "diff": (csum - fv) if number(fv) else None})
        comparison[cur] = comp
    model = {"today": today, "quarters": quarters, "buckets": buckets, "currencies": currencies, "totals": totals, "counts": counts,
             "window_sum": window, "forecast": forecast, "comparison": comparison, "n_rows": len(rows), "n_terminated": len(terminated),
             "n_no_amount": sum(b["n_no_amount"] for b in buckets.values()), "uid": uid,
             "amount_kinds": sorted(Counter(c["amount_kind"] for c in rows))}
    model["svg"] = {cur: schedule_svg(model, cur) for cur in currencies}
    return model


def schedule_svg(model, cur):
    quarters, buckets, uid = model["quarters"], model["buckets"], model["uid"] + "-" + cur
    fc = model["forecast"].get(cur) or {}
    fq = fc.get("by_quarter") or {}
    left, right, top, baseline = 95, 875, 40, 210
    vals = [buckets[q]["sum"].get(cur, 0.0) for q in quarters]
    fvals = [fq[q]["shown"] for q in quarters if q in fq and number(fq[q].get("shown"))]
    fups = [fq[q]["upper"] for q in quarters if q in fq and number(fq[q].get("upper"))]
    maxval = max([1.0] + vals + fvals + fups)
    step = (right - left) / float(len(quarters))
    bw = min(28.0, step * 0.3)

    def Y(v):
        return baseline - v / maxval * (baseline - top)

    descs = []
    for q in quarters:
        f = fq.get(q)
        descs.append("%s: 계약 %d건 합계 %s; 추정 %s(%s)" % (q, buckets[q]["n_by_cur"].get(cur, 0), fmt0(buckets[q]["sum"].get(cur, 0.0)),
                                                        fmt0(f["shown"]) if f else "—", f["basis"] if f else fc.get("reason", "없음")))
    p = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 262" role="img" aria-labelledby="%s-title %s-desc" '
         'style="min-width:720px;width:100%%;height:auto;display:block">' % (uid, uid),
         '<title id="%s-title">분기 전환 스케줄 · %s</title>' % (uid, esc(unit_label(cur))),
         '<desc id="%s-desc">%s. 왼쪽 색 막대 = 그 분기에 종료(예정)되는 계약의 %s 합계(영역별 누적), 오른쪽 점선 윤곽 막대 = 페이지 Y+2 추정(기준 시나리오 표시값)과 민감도 범위.</desc>'
         % (uid, esc(" / ".join(descs)), esc(AMOUNT_KIND_KO.get(model["amount_kinds"][0] if model["amount_kinds"] else "contract_total"))),
         '<line x1="%d" x2="%d" y1="%d" y2="%d" stroke="currentColor" opacity=".4"/>' % (left, right, baseline, baseline)]
    for v in (0.0, maxval / 2.0, maxval):
        p.append('<text x="88" y="%.1f" text-anchor="end" font-size="10" fill="currentColor">%s</text>' % (Y(v) + 4, fmt0(v)))
    for i, q in enumerate(quarters):
        b = buckets[q]
        x = left + (i + 0.5) * step
        cum = 0.0
        p.append('<g data-period="%s"><title>%s</title>' % (esc(q), esc(descs[i])))
        for dom in DOMAIN_KO:
            a = b["by_domain"].get(cur, {}).get(dom, 0.0)
            if a <= 0:
                continue
            p.append('<rect data-part="%s" x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>'
                     % (dom, x - bw - 2, Y(cum + a), bw, a / maxval * (baseline - top), DOMAIN_COLOR[dom]))
            cum += a
        p.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="10" fill="currentColor">%d건</text>'
                 % (x - bw / 2 - 2, min(Y(cum) - 4, baseline - 4), b["n_by_cur"].get(cur, 0)))
        f = fq.get(q)
        if f and number(f.get("shown")):
            p.append('<rect data-part="forecast" x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="currentColor" fill-opacity=".18" '
                     'stroke="currentColor" stroke-dasharray="3 2"/>' % (x + 2, Y(f["shown"]), bw, f["shown"] / maxval * (baseline - top)))
            if number(f.get("lower")) and number(f.get("upper")):
                cx = x + 2 + bw / 2
                lo, hi = Y(f["lower"]), Y(f["upper"])
                p.append('<path data-part="sensitivity" d="M%.1f,%.1fV%.1f M%.1f,%.1fH%.1f M%.1f,%.1fH%.1f" fill="none" stroke="currentColor"/>'
                         % (cx, lo, hi, cx - 4, lo, cx + 4, cx - 4, hi, cx + 4))
            if f["basis"] != "전체 원장 추정":
                p.append('<text x="%.1f" y="25" text-anchor="middle" font-size="10" fill="currentColor">부분</text>' % (x + 2 + bw / 2))
        elif fc.get("status") == "ok":
            p.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="10" fill="currentColor">미추정</text>' % (x + 2 + bw / 2, baseline - 6))
        p.append('<text x="%.1f" y="232" text-anchor="middle" font-size="11" fill="currentColor">%s</text></g>' % (x, esc(q)))
    p.append('<text x="%d" y="254" font-size="10" fill="currentColor">■ 계약 종료 합계(영역별 색)   ▭ Y+2 추정(기준 시나리오, 점선 윤곽)   ┼ 민감도 범위 — 통계적 신뢰구간 아님</text>' % left)
    p.append("</svg>")
    return "".join(p)


def schedule_html(model, uid):
    quarters = model["quarters"]
    parts = ['<h3 id="%s-schedule-h">분기 전환 스케줄 %s~%s</h3>' % (uid, quarters[0], quarters[-1]),
             '<p>종료(예정)일이 속한 분기에 계약을 쌓았습니다(색 = 영역). 오른쪽 점선 윤곽 막대는 페이지에 이미 실린 Y+2 추정(기준 시나리오 표시값)입니다. '
             '두 값은 정의가 다릅니다 — 왼쪽은 그 분기에 <em>끝나는</em> 계약의 %s 합계이고, 오른쪽은 그 분기에 <em>인식되는</em> 납품 추정입니다. '
             '어긋나는 것이 정상이며 맞추기 위한 조정을 하지 않았습니다. 창 밖(이전·이후)과 종료일 없음은 아래 표의 별도 행으로 두어 합계가 맞아떨어지게 했습니다.</p>'
             % esc(" / ".join(AMOUNT_KIND_KO.get(k, k) for k in model["amount_kinds"]) or "금액")]
    if not model["currencies"]:
        parts.append('<p data-schedule-status="counts_only">금액이 공시된 계약이 없어 건수만 집계합니다.</p>')
        rows = []
        for k, b in model["buckets"].items():
            label = {"before": quarters[0] + " 이전 종료", "after": quarters[-1] + " 이후 종료", "no_end": "종료일 없음"}.get(k, k)
            rows.append([esc(label), str(b["n"]), str(b["n_no_amount"])])
        parts.append(table(["분기", "종료 계약(건)", "이 중 금액 미공개(건)"], rows, "건수만 — 금액 미공시"))
        return "".join(parts)
    for cur in model["currencies"]:
        fc = model["forecast"][cur]
        parts.append('<h4>%s · %s</h4>' % (esc(cur), esc(unit_label(cur))))
        parts.append('<p>이 통화 계약 %d건 · 합계 %s · 창 안(%s~%s) 종료 합계 %s. %s</p>'
                     % (model["counts"][cur], fmt1(model["totals"][cur]), quarters[0], quarters[-1], fmt1(model["window_sum"][cur]),
                        esc("추정: " + (("기준 시나리오, 추정 상태 " + str(fc.get("estimate_status"))) if fc["status"] == "ok" else fc["reason"]))))
        parts.append('<div class="wrap" style="overflow-x:auto">' + model["svg"][cur] + '</div>')
        rows = []
        n_diff = 0
        for comp in model["comparison"][cur]:
            diff = comp["diff"]
            if number(diff) and abs(diff) > 1e-9:
                n_diff += 1
            rng = ("%s ~ %s" % (fmt1(comp["lower"]), fmt1(comp["upper"]))) if number(comp["lower"]) and number(comp["upper"]) else "—"
            rows.append([esc(comp["quarter"]), str(comp["n"]), str(comp["n_no_amount"]), fmt1(comp["contract_sum"]),
                         fmt1(comp["forecast"]), esc(comp["basis"]), rng, fmt1(diff) if number(diff) else "—"])
        for k in ("before", "after", "no_end"):
            b = model["buckets"][k]
            label = {"before": quarters[0] + " 이전 종료(경과·직전)", "after": quarters[-1] + " 이후 종료", "no_end": "종료일 없음(별도 묶음)"}[k]
            rows.append([esc(label), str(b["n_by_cur"].get(cur, 0)), str(b["n_no_amount"]), fmt1(b["sum"].get(cur, 0.0)), "—", "추정 창 밖", "—", "—"])
        rows.append(["<strong>합계</strong>", str(model["counts"][cur]), str(model["n_no_amount"]), fmt1(model["totals"][cur]), "—", "—", "—", "—"])
        parts.append(table(["분기", "종료 계약(건)", "금액 미공개(건, 통화 무관)", "계약 합계", "Y+2 추정(기준)", "추정 표시 근거", "민감도 범위", "차이 = 계약 − 추정"],
                           rows, "분기 전환 스케줄 · " + unit_label(cur) + " · 표시는 소수 %d자리 반올림, 합계는 반올림 전 값" % TABLE_DECIMALS))
        if fc["status"] == "ok":
            n_cmp = sum(1 for comp in model["comparison"][cur] if number(comp["forecast"]))
            parts.append('<p data-mismatch="%d">비교 가능한 %d개 분기 중 %d개에서 계약 종료 합계와 추정이 어긋납니다. 정의가 다르므로(총액 vs 분기 인식) 이는 오류가 아니며, 어느 쪽도 조정하지 않았습니다.</p>'
                         % (n_diff, n_cmp, n_diff))
        else:
            parts.append('<p data-forecast-status="%s">추정 열이 비어 있는 이유: %s</p>' % (esc(fc["status"]), esc(fc["reason"])))
    if model["n_no_amount"]:
        parts.append('<p>금액 미공개 %d건은 건수 열에만 있고 합계에는 들어가지 않습니다(사유는 간트 표·발주처 뷰 참조).</p>' % model["n_no_amount"])
    return "".join(parts)


# ---------------------------------------------------------------- view 3: clients
def _alias_map(rows):
    """Data-driven spelling → canonical customer map from rows that carry an upstream `customers` mapping."""
    amap = {}
    for c in rows:
        if c["customers"] and not c["anonymous"]:
            canon = str(c["customers"][0]["name"]).strip()
            grade, tier = str(c["customers"][0].get("grade") or ""), str(c["customers"][0].get("tier") or "")
            for k in (party_norm(c["party"]), party_norm(canon)):
                if k:
                    amap.setdefault(k, (canon, grade, tier))
    return amap


def _client_identity(c, amap):
    if c["anonymous"]:
        return "__anon__", "익명·미공개", "", "", False
    if c["customers"]:
        canon = str(c["customers"][0]["name"]).strip()
        return "c:" + party_norm(canon), canon, str(c["customers"][0].get("grade") or ""), str(c["customers"][0].get("tier") or ""), False
    key = party_norm(c["party"])
    via_alias = key in ALIASES
    key = ALIASES.get(key, key)
    if key in amap:
        canon, grade, tier = amap[key]
        return "c:" + party_norm(canon), canon, grade, tier, True
    return "p:" + key, c["party"].strip(), "", "", via_alias


def build_clients(contracts, top_n=10, strict_units=False, self_stock=None, self_name=None):
    """Per-currency counterparty aggregates: n, amount, share, longest end, concentration. Anonymous rows stay in one line."""
    rows = [normalize_contract(r, i, strict_units, self_stock, self_name) for i, r in enumerate(contracts)]
    n_terminated = sum(1 for c in rows if c["kind"] != "contract")
    rows = [c for c in rows if c["kind"] == "contract"]
    amap = _alias_map(rows)
    groups = OrderedDict()
    for c in rows:
        key, display, grade, tier, merged = _client_identity(c, amap)
        g = groups.setdefault(key, {"key": key, "display": display, "anonymous": key == "__anon__", "grade": grade, "tier": tier,
                                    "merged": False, "spellings": Counter(), "rows": []})
        g["rows"].append(c)
        g["spellings"][c["party"] or "-"] += 1
        g["merged"] = g["merged"] or merged
        if grade and (not g["grade"] or grade > g["grade"]):
            g["grade"] = grade
        if tier and not g["tier"]:
            g["tier"] = tier
    for g in groups.values():
        if not g["anonymous"] and not g["key"].startswith("c:"):
            g["display"] = g["spellings"].most_common(1)[0][0]
    currencies = sorted({c["cur"] for c in rows if number(c["amount"]) and c["cur"]})

    def entry_for(g, rs):
        ends = [c["end"] for c in rs if c["end"]]
        return {"key": g["key"], "display": g["display"], "anonymous": g["anonymous"], "grade": g["grade"], "tier": g["tier"],
                "merged": g["merged"], "n": len(rs), "sum": sum(c["amount"] for c in rs), "longest_end": max(ends) if ends else None,
                "n_no_end": len(rs) - len(ends), "domains": Counter(c["domain"] for c in rs), "natures": Counter(c["nature"] for c in rs),
                "spellings": Counter(c["party"] or "-" for c in rs), "anon_reasons": Counter(c["anon_reason"] for c in rs if c["anonymous"]),
                "n_assumed_unit": sum(1 for c in rs if c["unit_status"] == "assumed")}

    panels = []
    for cur in currencies:
        named, anon_rows = [], []
        for g in groups.values():
            rs = [c for c in g["rows"] if number(c["amount"]) and c["cur"] == cur]
            if not rs:
                continue
            if g["anonymous"]:
                anon_rows.extend(rs)
            else:
                named.append(entry_for(g, rs))
        anon = entry_for(groups["__anon__"], anon_rows) if anon_rows else None
        total = sum(e["sum"] for e in named) + (anon["sum"] if anon else 0.0)
        n_total = sum(e["n"] for e in named) + (anon["n"] if anon else 0)
        for e in named + ([anon] if anon else []):
            e["share"] = e["sum"] / total if total else None
        named.sort(key=lambda e: (-e["sum"], e["display"]))
        top, rest = named[:top_n], named[top_n:]
        rest_row = None
        if rest:
            ends = [e["longest_end"] for e in rest if e["longest_end"]]
            rest_row = {"display": "그 외 %d개사" % len(rest), "n": sum(e["n"] for e in rest), "sum": sum(e["sum"] for e in rest),
                        "share": (sum(e["sum"] for e in rest) / total) if total else None, "longest_end": max(ends) if ends else None,
                        "members": [e["display"] for e in rest], "n_assumed_unit": sum(e["n_assumed_unit"] for e in rest)}
        all_entries = named + ([anon] if anon else [])
        hhi = sum((e["share"] * 100.0) ** 2 for e in all_entries if number(e["share"])) if total else None
        panels.append({"cur": cur, "unit": unit_label(cur), "total": total, "n": n_total, "n_named_groups": len(named),
                       "top": top, "rest": rest_row, "anonymous": anon, "hhi": hhi,
                       "top1_share": top[0]["share"] if top else None,
                       "top3_share": sum(e["share"] for e in top[:3]) if top and total else None,
                       "max_end": max([e["longest_end"] for e in all_entries if e["longest_end"]] or [None]),
                       "n_assumed_unit": sum(e["n_assumed_unit"] for e in all_entries)})
    no_amount = []
    for g in groups.values():
        rs = [c for c in g["rows"] if not number(c["amount"])]
        if rs:
            ends = [c["end"] for c in rs if c["end"]]
            no_amount.append({"display": g["display"], "anonymous": g["anonymous"], "n": len(rs), "longest_end": max(ends) if ends else None,
                              "reasons": Counter(c["amount_note"] for c in rs), "spellings": Counter(c["party"] or "-" for c in rs)})
    no_amount.sort(key=lambda e: (e["anonymous"], -e["n"], e["display"]))
    return {"panels": panels, "no_amount": no_amount, "n_rows": len(rows), "n_terminated": n_terminated,
            "n_anonymous_rows": sum(1 for c in rows if c["anonymous"]), "n_groups": len([g for g in groups.values() if not g["anonymous"]]),
            "alias_map": {k: v[0] for k, v in amap.items()}, "top_n": top_n,
            "amount_kinds": sorted(Counter(c["amount_kind"] for c in rows))}


def _spell(counter, limit=4):
    items = counter.most_common()
    text = " · ".join("%s×%d" % (clip(k, 28), n) for k, n in items[:limit])
    return text + (" · 외 %d종" % (len(items) - limit) if len(items) > limit else "")


def clients_html(model, uid):
    kind = " / ".join(AMOUNT_KIND_KO.get(k, k) for k in model["amount_kinds"]) or "금액"
    parts = ['<h3 id="%s-clients-h">발주처(고객)별</h3>' % uid,
             '<p>상대별 건수·금액(%s)·최장 종료(예정)일·비중. 통화별로만 집계하며 환산·합산하지 않습니다. 비중과 집중도는 금액이 공시된 계약 합계 기준이며 잔고가 아닙니다. '
             '익명·미공개 표기(\'-\', \'해외 정부기관\' 같은 일반 명칭)는 실명과 섞지 않고 한 줄에 모았습니다. 표기가 다른 같은 상대는 괄호·법인격 토큰을 지운 뒤 '
             '원장의 고객 사전(customers)으로만 묶었고, 묶인 표기는 \'표기\' 열에 모두 남겼습니다(사전으로 편 이름은 등급 C=추정).</p>' % esc(kind)]
    if not model["panels"]:
        parts.append('<p data-clients-status="counts_only">금액이 공시된 계약이 없어 금액·비중을 만들지 않았습니다. 아래 금액 미공개 표에 상대별 건수만 있습니다.</p>')
    for pnl in model["panels"]:
        cur = pnl["cur"]
        parts.append('<h4>%s · %s</h4>' % (esc(cur), esc(pnl["unit"])))
        parts.append('<p>계약 %d건 · 합계 %s · 실명 발주처 %d곳%s. <strong>집중도</strong>: 상위 1개사 %s · 상위 3개사 %s · HHI %s(익명 묶음을 상대 하나로 계산, 0~10,000).%s</p>'
                     % (pnl["n"], fmt1(pnl["total"]), pnl["n_named_groups"],
                        (" · 익명·미공개 %d건" % pnl["anonymous"]["n"]) if pnl["anonymous"] else "",
                        pct(pnl["top1_share"]), pct(pnl["top3_share"]), fmt0(pnl["hhi"]),
                        (" * 통화 표기 없음(원으로 읽음) %d건 포함." % pnl["n_assumed_unit"]) if pnl["n_assumed_unit"] else ""))
        rows = []
        for e in pnl["top"]:
            tier = PARTY_KIND_KO.get(e["tier"].upper(), e["tier"]) if e["tier"] else ""
            grade = ("C(추정·표기 통합)" if e["merged"] else e["grade"]) if (e["grade"] or e["merged"]) else ""
            rows.append([esc(e["display"]), esc(" · ".join(x for x in (tier, grade) if x) or "—"), str(e["n"]),
                         fmt1(e["sum"]) + (" *" if e["n_assumed_unit"] else ""), pct(e["share"]),
                         esc(e["longest_end"].isoformat() if e["longest_end"] else "—") + (esc(" (종료일 없음 %d건)" % e["n_no_end"]) if e["n_no_end"] else ""),
                         esc(" · ".join(DOMAIN_KO.get(d, d) for d, _ in e["domains"].most_common())),
                         esc(_spell(e["spellings"]) if len(e["spellings"]) > 1 or e["merged"] else "")])
        if pnl["rest"]:
            r = pnl["rest"]
            rows.append([esc(r["display"]), "—", str(r["n"]), fmt1(r["sum"]) + (" *" if r["n_assumed_unit"] else ""), pct(r["share"]),
                         esc(r["longest_end"].isoformat() if r["longest_end"] else "—"), "—", esc(clip(" · ".join(r["members"]), 160))])
        if pnl["anonymous"]:
            a = pnl["anonymous"]
            rows.append(['<em>익명·미공개 (실명과 섞지 않음)</em>', "—", str(a["n"]), fmt1(a["sum"]) + (" *" if a["n_assumed_unit"] else ""), pct(a["share"]),
                         esc(a["longest_end"].isoformat() if a["longest_end"] else "—") + (esc(" (종료일 없음 %d건)" % a["n_no_end"]) if a["n_no_end"] else ""),
                         esc(" · ".join(DOMAIN_KO.get(d, d) for d, _ in a["domains"].most_common())), esc(_spell(a["spellings"], 6))])
        rows.append(["<strong>합계</strong>", "—", str(pnl["n"]), fmt1(pnl["total"]), "100%" if pnl["total"] else "—",
                     esc(pnl["max_end"].isoformat() if pnl["max_end"] else "—"), "—", "—"])
        parts.append(table(["발주처", "계층·등급", "건수", "금액", "비중", "최장 종료(예정)일", "영역", "표기"], rows,
                           "발주처별 · 상위 %d + 나머지 묶음 · %s" % (model["top_n"], pnl["unit"])))
    if model["no_amount"]:
        rows = [[(('<em>익명·미공개</em>') if e["anonymous"] else esc(e["display"])), str(e["n"]),
                 esc(e["longest_end"].isoformat() if e["longest_end"] else "—"),
                 esc(" · ".join("%s(%d)" % (clip(k, 60), n) for k, n in e["reasons"].most_common())),
                 esc(_spell(e["spellings"], 6) if e["anonymous"] or len(e["spellings"]) > 1 else "")] for e in model["no_amount"]]
        parts.append('<details><summary>금액 미공개 계약의 발주처 %d건</summary>' % sum(e["n"] for e in model["no_amount"]) +
                     '<p>금액이 없어 위 표의 합계·비중에 넣지 않았습니다. 빈 이유를 상대별로 적었습니다.</p>' +
                     table(["발주처", "건수", "최장 종료(예정)일", "금액이 비어 있는 이유", "표기"], rows, "금액 미공개 — 건수·기간만") + '</details>')
    if model["n_terminated"]:
        parts.append('<p>해지 공시 %d건은 발주처 집계에서 뺐습니다.</p>' % model["n_terminated"])
    return "".join(parts)


# ---------------------------------------------------------------- section
def build_views(panel_entry, contracts, forecast_entry=None, today=None, top_n=10, strict_units=False):
    """Everything render_orders_section needs, as data (used by selfcheck)."""
    stock = panel_entry.get("stock")
    name = panel_entry.get("co", panel_entry.get("name"))
    if not isinstance(stock, str) or not re.fullmatch(r"\d{6}", stock):
        raise ValueError("invalid company identifier")
    if forecast_entry is not None:
        c = forecast_entry
        if c.get("company_id") != stock or c.get("company_name") != name or c.get("stock") != stock or c.get("source") != panel_entry.get("src"):
            raise ValueError("company_identity_conflict")
    today = _today(today)
    rows, meta = prepare_contracts(contracts, stock, name, strict_units)
    uid = "kaero-orders-" + stock
    gantt = build_gantt(rows, today=today, uid=uid + "-gantt")
    schedule = build_schedule(rows, forecast_entry=forecast_entry, today=today, uid=uid + "-schedule")
    clients = build_clients(rows, top_n=top_n)
    return {"stock": stock, "name": name, "uid": uid, "today": today, "rows": rows, "meta": meta,
            "gantt": gantt, "schedule": schedule, "clients": clients}


def render_orders_section(panel_entry, contracts, forecast_entry=None, today=None, top_n=10, strict_units=False):
    """HTML fragment (a <section>) for the company page: Gantt · quarter roll-off schedule · client view."""
    v = build_views(panel_entry, contracts, forecast_entry, today, top_n, strict_units)
    name, uid, rows, meta = v["name"], v["uid"], v["rows"], v["meta"]
    if not rows:
        return ('<section class="kaero-orders" id="%s" data-orders-status="empty" aria-labelledby="%s-heading">'
                '<h2 id="%s-heading">%s 수주 상세 — 간트 · 분기 전환 · 발주처</h2><p>계약 원장 행 없음(입력 %d건, 다른 종목 %d건 제외).</p></section>'
                % (uid, uid, uid, esc(name), meta["n_input"], meta["dropped_other_stock"]))
    n_contract = sum(1 for c in rows if c["kind"] == "contract")
    n_term = len(rows) - n_contract
    n_end = sum(1 for c in rows if c["kind"] == "contract" and c["end"])
    n_amount = sum(1 for c in rows if c["kind"] == "contract" and number(c["amount"]))
    n_assumed = sum(1 for c in rows if c["kind"] == "contract" and c["unit_status"] == "assumed")
    n_excluded_unit = sum(1 for c in rows if c["kind"] == "contract" and c["unit_status"] == "excluded")
    n_anon = sum(1 for c in rows if c["kind"] == "contract" and c["anonymous"])
    status = "ok" if n_amount else "counts_only"
    if meta["source"] == "ledger":
        lm = meta.get("ledger", {})
        source = "정기보고서 수주상황(상세) 원장 %s (%s)" % (lm.get("quarter") or "?", lm.get("title") or "")
        if lm.get("excluded_by_tab"):
            source += " · 다른 탭 몫 제외 " + ", ".join("%s %d행" % (k, n) for k, n in sorted(lm["excluded_by_tab"].items()))
    else:
        source = "단일판매·공급계약 공시(정정 반영, 최신 정정본만)"
    kinds = " / ".join(AMOUNT_KIND_KO.get(k, k) for k in meta["amount_kinds"])
    parts = ['<section class="kaero-orders" id="%s" data-orders-status="%s" data-today="%s" aria-labelledby="%s-heading">' % (uid, status, v["today"].isoformat(), uid),
             '<h2 id="%s-heading">%s 수주 상세 — 간트 · 분기 전환 · 발주처</h2>' % (uid, esc(name)),
             '<p>기준일 %s · 원천: %s · 금액 성격: %s.</p>' % (v["today"].isoformat(), esc(source), esc(kinds)),
             '<p>계약 %d건(해지 공시 %d건 별도) · 종료일 있음 %d건 · 종료일 없음 %d건 · 금액 공시 %d건 · 금액 미공개 %d건 · 익명·미공개 상대 %d건%s.</p>'
             % (n_contract, n_term, n_end, n_contract - n_end, n_amount, n_contract - n_amount, n_anon,
                (" · 다른 종목 %d건·정정 전 공시 %d건 제외" % (meta["dropped_other_stock"], meta["dropped_superseded"])) if (meta["dropped_other_stock"] or meta["dropped_superseded"]) else ""),
             '<p data-unit-status="%s">금액은 제공된 kce_parse._UNIT_SCALE 정규화 계약에 따른 백만원(KRW)·통화별 백만 단위이며 통화별로만 집계하고 환산·합산하지 않습니다. '
             '%s%s—는 근거 부족이며 0이 아닙니다.</p>'
             % ("assumed_%d" % n_assumed if n_assumed else ("excluded_%d" % n_excluded_unit if n_excluded_unit else "stated"),
                ("통화 표기가 없어 원으로 읽은 금액 %d건이 포함되며 * 로 표시합니다(원문 amount_label 참조). " % n_assumed) if n_assumed else "",
                ("통화 표기가 없는 %d건은 엄격 모드로 금액에서 제외해 건수·기간만 보입니다. " % n_excluded_unit) if n_excluded_unit else "")]
    if meta["source"] != "ledger":
        parts.append('<p>공시 계약금액은 체결 시점 총액입니다. 기납품액을 빼지 않았으므로 정기보고서의 수주잔고와 다르며, 그 잔고에 더하지도 않았습니다. 종료일은 종료 예정일이며 정정공시로 바뀔 수 있습니다.</p>')
    else:
        parts.append('<p>수주표 잔고(기말)는 정기보고서 캡션 단위를 따르며, 납기는 월·연 단위 표기를 기간 말로 두었습니다(표에 ※로 표시).</p>')
    parts.append(gantt_html(v["gantt"], uid))
    parts.append(schedule_html(v["schedule"], uid))
    parts.append(clients_html(v["clients"], uid))
    parts.append('<p>세 뷰 모두 같은 %d건을 씁니다. 분기 스케줄의 금액은 그 분기에 종료(예정)되는 계약의 금액 합계이지 그 분기의 매출 인식액이 아닙니다. '
                 'Y+2 추정과 정의가 다르므로 두 값의 차이는 오류가 아니며 맞추기 위한 조정을 하지 않았습니다. 값이 빈 칸은 근거가 없어 비운 것이고 추정으로 메우지 않았습니다.</p></section>' % n_contract)
    return "".join(parts)


# ---------------------------------------------------------------- standalone preview
STYLE = """<style>
:root{color-scheme:dark;--bg:#0b1220;--pn:#121b2c;--ln:#2b3b54;--tx:#e6edf5;--a:#f5b642}
@media(prefers-color-scheme:light){:root{color-scheme:light;--bg:#f5f7fa;--pn:#fff;--ln:#cbd5e1;--tx:#182b3b;--a:#b45309}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.65 system-ui,sans-serif}
main{max-width:1280px;margin:auto;padding:24px}.kaero-orders{background:var(--pn);border:1px solid var(--ln);border-radius:12px;padding:24px;margin:24px 0}
h1,h2,h3,h4{line-height:1.3}h3{border-top:2px solid var(--ln);padding-top:20px}svg{display:block}
details{border:1px solid var(--ln);border-radius:8px;padding:12px;margin:12px 0}summary{cursor:pointer;font-weight:650}
.wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px;border-bottom:1px solid var(--ln);text-align:right;vertical-align:top}th:first-child,td:first-child{text-align:left}
caption{text-align:left;font-weight:650;padding:8px 0}a{color:inherit}@media(max-width:600px){main{padding:8px}.kaero-orders{padding:12px}}
</style>"""


def document(title, body):
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
            + esc(title) + '</title>' + STYLE + '</head><body><main>' + body + '</main></body></html>\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--reports", type=Path, default=None, help="optional kaero_reports.json → second section from the periodic-report ledger")
    parser.add_argument("--forecast-panel", type=Path, default=None, help="optional forecast_panel.json (companies[]) for the schedule comparison")
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "preview")
    parser.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    parser.add_argument("--strict-units", action="store_true", help="exclude amounts whose currency was not stated in the disclosure")
    args = parser.parse_args()
    contracts = json.loads(args.contracts.read_text(encoding="utf-8"))["rows"]
    universe = json.loads(args.universe.read_text(encoding="utf-8"))["rows"]
    reports = json.loads(args.reports.read_text(encoding="utf-8"))["companies"] if args.reports else {}
    forecasts = {}
    if args.forecast_panel:
        for c in json.loads(args.forecast_panel.read_text(encoding="utf-8")).get("companies", []):
            forecasts[c.get("company_id")] = c
    args.output_dir.mkdir(parents=True, exist_ok=True)
    links = []
    for u in universe:
        stock, name = u["stock"], u["name"]
        panel = {"stock": stock, "co": name, "src": "kaero_reports"}
        rows = [r for r in contracts if r.get("stock") == stock]
        fe = forecasts.get(stock)
        body = render_orders_section(panel, rows, fe, today=args.today, strict_units=args.strict_units)
        if stock in reports:
            lr = ledger_rows(reports[stock])
            if lr:
                body += render_orders_section(panel, lr, fe, today=args.today)
        (args.output_dir / (stock + ".html")).write_text(document(name + " 수주 상세", body), encoding="utf-8")
        links.append('<li><a href="%s.html">%s</a> — 공시 %d건</li>' % (stock, esc(name), len(rows)))
    (args.output_dir / "index.html").write_text(document("KAERO 수주 상세 미리보기", '<h1>한국우주항공 수주 상세 미리보기</h1><ul>' + "".join(links) + '</ul>'), encoding="utf-8")
    print("rendered %d company pages into %s (inline SVG only)" % (len(links), args.output_dir))


if __name__ == "__main__":
    main()
