#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xi1_sector — 수주 섹터 탭(kship·kdef·knuke·kgrid·kaero·ksemi)의 **계약별 진행 현황**.

원천: 반기·사업보고서 XI-1 「공시내용 진행 및 변경사항 › 나. 단일판매ㆍ공급계약 진행 현황」. 2024Q4 부터 Q2·Q4 에만
실린다(분기보고서엔 없다). 표 해석은 kce_xi1(6개 섹터 304사 2026Q2 실측 보강)을 그대로 쓰고, 이 모듈은 탭 공통 규칙만 둔다.

  1) collect — 탭 모집단 × 반기·연간 분기 → tools/assets/xi1/parsed/<stock>/<q>.json(커밋): 원문 표의 라벨·값
     문자열(raw — COMMON §0-4) + 해석 결과. 상태는 tools/assets/xi1/status.json. 원문 HTML 은 레포 규칙대로 커밋하지
     않고(.gitignore argus/*/tools/assets/xi1/_raw/) 로컬 gzip 으로만 둔다. 파서 판(kce_xi1.PARSER_REV)이 바뀌면 build 가
     로컬 HTML(있으면) 또는 보존 원문 표로 다시 해석한다 — 재수집이 필요 없다. 머리행 감지 규칙이 바뀐 경우만 HTML 이 필요하다.
  2) build — 해석 결과 → 원장 금액으로 단위 보정(kce_xi1.calibrate) → 분기 사이 같은 계약 잇기(thread)
     → 탭 원장(contracts.json, 단일판매ㆍ공급계약체결 공시) 연결(근거 등급) → 계약 지표 → 회사·섹터 집계
     → tools/assets/xi1/progress.json. 표마다 머리행 지도(hdrmap role 'xi')에 기록하고, 못 읽은 표는 탭 대기열로.

공통 원칙(각 탭 LOGIC 의 규칙을 그대로 따른다):
  · 통화를 섞지 않는다. 외화 계약금액을 우리가 환산하지 않는다. 원장(공시)에 회사가 적은 원화 계약금액이 연결된 경우에만
    그 값을 분모로 쓰고 basis='ledger_krw'(추정)로 표시한다. 그 밖의 외화 계약은 진행률 없음.
  · 연결은 fail-closed: 신고일자 = 원장 접수일(정정 전 원접수·계약일 포함) 에 금액·이름·상대방 근거가 붙을 때만.
    근거 없는 행은 'XI 전용'으로 남기고 억지로 붙이지 않는다.
  · 판매공급 누적은 매출·수주잔고(II-4)에 더하지 않는다 — 다른 축이다. 집계는 원화 계약만, 단위 의심 표는 빼고.
  · 결정적 출력: 실행 날짜를 쓰지 않는다. 기준일은 보고 기간 말일(Q2 → 6/30, Q4 → 12/31).
"""
import argparse
import datetime
import gzip
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import hdrmap                                   # noqa: E402
import kce_xi1 as X                             # noqa: E402
from kce_lib import atomic_write, latest_quarter  # noqa: E402

ARGUS = os.path.dirname(os.path.dirname(HERE))
TABS = ("kship", "kdef", "knuke", "kgrid", "kaero", "ksemi")
FIRST = "2024Q4"                                 # XI-1 진행 현황 표가 처음 실린 보고서
SECTION = [("xi1", ["공시내용 진행 및 변경사항"])]
RETRY = ("no_report", "no_section", "error")
SCHEMA = 1

# 탭 원장(contracts.json) 어댑터 — 금액은 전부 백만원(원화). 통화 열이 있는 탭은 원화가 아니면 금액을 쓰지 않는다.
LEDGER = {
    "kship": {"name": "name", "amt": "amt_krw_m"},
    "kdef": {"name": "name", "amt": "amt_krw_m"},
    "knuke": {"name": "name", "amt": "amt_krw_m"},
    "kgrid": {"name": "name", "amt": "amt_krw_m"},
    "kaero": {"name": "name", "amt": "amount", "cur": "cur"},
    "ksemi": {"name": "content", "amt": "amt_mkrw", "cur": "currency"},
}

# 지표 임계(LOGIC 에 적는다). 진행은 시간에 선형이 아니다 — 조선은 강재 절단 전 1~2년이 비고, 방산 양산은 인도 직전에 몰린다.
# 그래서 '경과 대비 진행'은 직선이 아니라 **탭 표준 곡선**(같은 탭 진행 계약들의 경과 구간별 진행률 중앙값, 단조 보정)과 비교한다.
#   lag     : 표준 곡선보다 20%p 이상 뒤처짐(경과 20~100% 구간에서만)
#   overdue : 계약 종료일이 기간 말보다 앞인데 공급 95% 미만
#   slip    : 최근 공급 속도(월)로 남은 금액을 채우면 종료일보다 6개월 이상 늦다
#   stalled : 직전 보고 이후 공급 증가 0 인데 잔여가 있다
LAG = -0.20
DONE = 0.95
OVER = 1.05
CURVE_BINS = [(i / 10, (i + 1) / 10) for i in range(10)] + [(1.0, 1.5)]
CURVE_MIN_N = 5


# ── 분기 · 경로 ─────────────────────────────────────────────────

def periods(latest, first=FIRST):
    """first 부터 latest 까지의 Q2·Q4(오름차순)."""
    y, q = int(first[:4]), int(first[5])
    ly, lq = int(latest[:4]), int(latest[5])
    out = []
    while (y, q) <= (ly, lq):
        if q in (2, 4):
            out.append("%dQ%d" % (y, q))
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)
    return out


def latest_xi(today=None):
    """정기보고서가 접수됐을 만한 최근 분기에서 가장 가까운 Q2·Q4(그 이전)."""
    lq = latest_quarter(today)
    y, q = int(lq[:4]), int(lq[5])
    if q in (2, 4):
        return lq
    return "%dQ2" % y if q == 3 else "%dQ4" % (y - 1)


def period_end(q):
    y = int(q[:4])
    return datetime.date(y, 6, 30) if q[5] == "2" else datetime.date(y, 12, 31)


def _window(q):
    """보고서 검색 기간·종류. 반기(A002)는 8월, 사업(A001)은 이듬해 3월 접수 — 정정까지 1년을 본다."""
    y = int(q[:4])
    if q[5] == "2":
        return "%d0701" % y, "%d0630" % (y + 1), "A002"
    return "%d0101" % (y + 1), "%d1231" % (y + 1), "A001"


_TITLE = re.compile(r"(사업|반기)보고서\s*\((\d{4})\.(\d{2})\)")


def xi_dir(tab, root=None):
    return os.path.join(root or ARGUS, tab, "tools", "assets", "xi1")


def raw_path(tab, st, q, root=None):
    return os.path.join(xi_dir(tab, root), "_raw", st, "%s.html.gz" % q)


def parsed_path(tab, st, q, root=None):
    return os.path.join(xi_dir(tab, root), "parsed", st, "%s.json" % q)


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def load_status(tab, root=None):
    p = os.path.join(xi_dir(tab, root), "status.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_status(tab, stat, root=None):
    p = os.path.join(xi_dir(tab, root), "status.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write(p, _dump(stat))


def write_raw(tab, st, q, html, root=None):
    """원문 gzip(mtime 0). 커밋하지 않는 로컬 사본 — 파서 판이 바뀌었을 때 DART 없이 다시 해석하려고."""
    p = raw_path(tab, st, q, root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        f.write(gzip.compress(html.encode("utf-8"), compresslevel=9, mtime=0))
    os.replace(tmp, p)
    return p


def read_raw(tab, st, q, root=None):
    p = raw_path(tab, st, q, root)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return gzip.decompress(f.read()).decode("utf-8")


_RAW_KEEP = ("lead", "cols", "ncols", "rows", "rspan", "n_raw")


def _raw_of(tables):
    """원문 표 보존본 — 판매공급·대금수령 문구가 있는 표만 본문 행까지, 나머지('가' 진행 표·사유 부표)는 머리만."""
    out = []
    for t in tables:
        d = {k: t[k] for k in _RAW_KEEP if k in t}
        d["lead"] = X.KP.lead_tail(t.get("lead"), 400)
        if not X._XI_HINT.search(" ".join(t.get("cols") or [])):
            d["rows"], d["rspan"] = [], []
        out.append(d)
    return out


def parse_doc(html, rcp=None, raw=None):
    """절 HTML(또는 보존된 원문 표 raw) → 커밋할 해석 결과. 결정적."""
    raw = raw if raw is not None else _raw_of(X.raw_tables(html))
    p = X.interpret([dict(t) for t in raw])
    keep = ("cols", "ncols", "fields", "n", "n_rec", "unit", "unit_fix", "unit_suspect", "rows")
    return {"rev": X.PARSER_REV, "rcp": rcp, "raw": raw,
            "tables": [dict({k: t[k] for k in keep if k in t}, lead=X.KP.lead_tail(t.get("lead"))) for t in p["tables"]],
            "rejected": [{"cols": r["cols"], "ncols": r["ncols"], "fields": r["fields"], "n": r["n"], "reason": r["reason"],
                          "lead": X.KP.lead_tail(r.get("lead")),
                          **({"rows": (r.get("rows") or [])[:3]} if r["reason"] == "near_miss" else {})}
                         for r in p.get("rejected") or []],
            "unknown": len(p["unknown_headers"])}


def write_parsed(tab, st, q, doc, root=None):
    p = parsed_path(tab, st, q, root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write(p, _dump(doc))
    return p


def read_parsed(tab, st, q, root=None):
    """해석 결과. 파서 판이 다르고 로컬 원문이 있으면 다시 해석해 덮어쓴다."""
    p = parsed_path(tab, st, q, root)
    doc = None
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    if doc is None or doc.get("rev") != X.PARSER_REV:
        html = read_raw(tab, st, q, root)
        if html is not None:
            doc = parse_doc(html, (doc or {}).get("rcp"))
            write_parsed(tab, st, q, doc, root)
        elif doc and doc.get("raw"):
            doc = parse_doc(None, doc.get("rcp"), raw=doc["raw"])       # CI: HTML 없이 보존 원문 표로 재해석
            write_parsed(tab, st, q, doc, root)
    return doc


def universe(tab, root=None):
    """[(stock, name)] — 탭 universe.json 행 순서 그대로."""
    p = os.path.join(root or ARGUS, tab, "tools", "assets", "universe.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    rows = d["rows"] if isinstance(d, dict) and "rows" in d else d
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    out, seen = [], set()
    for r in rows:
        st = r.get("stock")
        if st and st not in seen:
            seen.add(st)
            out.append((st, r.get("name") or st))
    return out


# ── 수집 ────────────────────────────────────────────────────────

def fetch_one(st, q, F):
    """(st, q) 의 XI-1 절 → (상태 dict, html|None). 제목 기준월이 맞는 보고서만, 첨부정정은 뒤로(kce_fetch.pick_report)."""
    s, e, kind = _window(q)
    want = "%s.%02d" % (q[:4], int(q[5]) * 3)
    cands = [c for c in F.pick_report(F.search_reports(st, s, e, kind), q)
             if (lambda m: bool(m) and "%s.%s" % (m.group(2), m.group(3)) == want)(_TITLE.search(c[1] or ""))]
    if not cands:
        return {"status": "no_report"}, None
    for rcp, title in cands[:3]:
        found = F.find_sections(F.toc(rcp), SECTION)
        if "xi1" in found:
            return {"status": "ok", "rcp": rcp, "title": title}, F.fetch_section(found["xi1"])
    return {"status": "no_section", "rcp": cands[0][0]}, None


def collect(tab, stocks=None, qs=None, root=None, force=False, recheck_all=False, lanes=1, fetch=None, log=None):
    """모자란 (종목, 분기)만 받는다. 상태가 RETRY 인 칸은 **최신 분기만** 매번 다시 본다(과거 분기는 --recheck-all).
    오류는 상태에 'error' 로 남지만 다음 실행이 다시 받는다. DART 는 IP 당 한 프로세스 — kce_fetch 전역 게이트가 묶는다."""
    if fetch is None:
        import kce_fetch as fetch
    log = log or (lambda m: sys.stderr.write(m + "\n"))
    stocks = stocks or [s for s, _ in universe(tab, root)]
    qs = qs or periods(latest_xi())
    stat = load_status(tab, root)
    todo = []
    for st in stocks:
        for q in qs:
            cur = stat.get("%s|%s" % (st, q))
            if force or cur is None:
                todo.append((st, q))
            elif cur.get("status") in RETRY and (q == qs[-1] or recheck_all or cur.get("status") == "error"):
                todo.append((st, q))
    log("xi1 %s: 수집 %d칸 (종목 %d × 분기 %s)" % (tab, len(todo), len(stocks), ",".join(qs)))

    def one(it):
        return fetch_one(it[0], it[1], fetch)

    def done(i, it, res):
        key = "%s|%s" % it
        if isinstance(res, Exception):
            stat[key] = {"status": "error", "error": ("%s: %s" % (type(res).__name__, res))[:160]}
        else:
            rec, html = res
            if html is not None:
                write_raw(tab, it[0], it[1], html, root)
                write_parsed(tab, it[0], it[1], parse_doc(html, rec.get("rcp")), root)
            stat[key] = rec
        save_status(tab, stat, root)
        log("  %s %s" % (key, stat[key]["status"]))

    fetch.parallel(todo, one, lanes=lanes, on_done=done)
    return stat


# ── 원장 ────────────────────────────────────────────────────────

_ISO = re.compile(r"((?:19|20)\d{2})[.\-/년\s]*(\d{1,2})[.\-/월\s]*(\d{1,2})")


def to_date(s):
    m = _ISO.search(s or "")
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def load_ledger(tab, root=None):
    p = os.path.join(root or ARGUS, tab, "tools", "assets", "contracts.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return ledger_rows(tab, d["rows"] if isinstance(d, dict) else d)


def ledger_rows(tab, rows):
    """탭 원장 행 → 공통 꼴 {rcp, stock, name, amt(원화 백만원|None), party, start, end, dates{YYYYMMDD}, rcps, term}."""
    spec = LEDGER[tab]
    out = []
    for r in rows:
        rcp = r.get("rcp")
        if not rcp:
            continue
        cur = (r.get(spec["cur"]) or "KRW") if spec.get("cur") else "KRW"
        amt = r.get(spec["amt"]) if cur in ("KRW", "원") else None
        sup = r.get("supersedes")
        sups = [s for s in (sup if isinstance(sup, list) else [sup]) if s]
        dates = {rcp[:8]} | {s[:8] for s in sups}
        sd = to_date(r.get("signed") or "")
        if sd:
            dates.add(sd.strftime("%Y%m%d"))
        term = bool(r.get("canceled")) or r.get("event") in ("해지", "철회") or "해지" in (r.get("title") or "")
        # ksemi 의 name 은 회사명이다(계약명은 content) — 다른 열로 메우지 않는다
        out.append({"rcp": rcp, "stock": r.get("stock"), "name": r.get(spec["name"]) or "",
                    "amt": amt if isinstance(amt, (int, float)) and amt > 0 else None,
                    "party": r.get("party") or "", "start": r.get("start") or "", "end": r.get("end") or "",
                    "dates": dates, "rcps": [rcp] + sups, "term": term,
                    "signed": [d for d in (sd, to_date(r.get("start") or "")) if d]})
    return out


def cell_sanity(r):
    """한 칸만 단위가 다른 행(한화에어로 2026Q2 IM3 발사대: 계약 388,180 · 수령 누적 121,938,492 — 천원).
    공급·수령 칸이 계약금액의 2배를 넘고 1,000·1,000,000 으로 나누면 1.2배 안에 들면 그 칸만 옮기고(cell_fix),
    그래도 안 맞으면 그 칸을 비운다(cell_drop). 계약 2배 넘게 공급·수령하는 계약은 없다."""
    amt = r.get("amt")
    if not amt or amt <= 0:
        return r
    for f in ("supCur", "supCum", "recvCur", "recvCum"):
        v = r.get(f)
        if v is None or abs(v) <= amt * 2:
            continue
        for k in (3, 6):
            if abs(v) / 10 ** k <= amt * 1.2:
                r[f] = round(v / 10 ** k, 6)
                r.setdefault("cell_fix", []).append(f)
                break
        else:
            r[f] = None
            r.setdefault("cell_drop", []).append(f)
    return r


def blank_zero(r, sup_any=True, recv_any=True):
    """열은 있는데 칸이 빈(`-`) 누적은 0 — kce 사업장 상세(xipDecomp)와 같은 규칙: 아직 공급·수령 전인 계약이다.
    열 자체가 없는 표(대금수령 열 없는 회사)는 None 으로 둔다 — 행 dict 에 키가 없으면 열이 없던 것.
    표의 행 절반 넘게 그 열을 비웠으면(sup_any/recv_any False) 회사가 진행을 적지 않은 것이라 0 으로 채우지 않는다."""
    if r.get("amt") is None:
        return r
    if sup_any and "supCum" in r and r["supCum"] is None:
        r["supCum"] = 0
    if recv_any and "recvCum" in r and r["recvCum"] is None and r.get("supCum") is not None:
        r["recvCum"] = 0
    return r


# ── 분기 사이 잇기 · 원장 연결 ─────────────────────────────────

def _dt8(dt):
    return (dt or "").replace(".", "")


def _near(a, b, tol):
    return a is not None and b is not None and b != 0 and abs(a - b) <= max(1.0, abs(b) * tol)


def _names(r):
    return [r.get("nm") or ""] + list(r.get("nm_more") or [])


def _same(r, prev):
    """두 분기 행이 같은 계약인가 → 점수(0 = 아님). 신고일자는 원접수일이라 분기마다 같다(변경계약은 날짜가 바뀐다)."""
    sim = max(X._sim(a, b) for a in _names(r) for b in _names(prev))
    same_key = X.nkey(r.get("nm")) == X.nkey(prev.get("nm")) and len(X.nkey(r.get("nm"))) >= 4
    amt = _near(r.get("amt"), prev.get("amt"), 0.02) or (r.get("amt_fx") and r.get("amt_fx") == prev.get("amt_fx"))
    # 같은 날 같은 이름·같은 금액의 쌍둥이 계약(스페코 조타기 2건: 종료일만 2027.12 / 2028.06)은 계약기간으로 가른다.
    per = 0.0
    if r.get("period") and prev.get("period"):
        per = 0.3 if re.sub(r"\s", "", r["period"]) == re.sub(r"\s", "", prev["period"]) else -0.3
    if r.get("dt") and r.get("dt") == prev.get("dt"):
        if same_key or sim >= 0.35 or amt:
            return 3 + sim + (0.5 if amt else 0) + per
        return 0
    if same_key and amt:
        return 2 + sim
    return 0


def thread(per_q):
    """[(q, rows)] 오름차순 → [{'hist': {q: row}, 'tab': {q: 표 메타}}]. 같은 분기 두 행이 한 실을 차지하지 않는다."""
    threads = []
    for q, rows in per_q:
        pairs = []
        for i, r in enumerate(rows):
            for j, t in enumerate(threads):
                last = t["hist"][max(t["hist"])]
                s = _same(r, last)
                if s:
                    pairs.append((-s, i, j))
        pairs.sort()
        ri, tj = set(), set()
        for s, i, j in pairs:
            if i in ri or j in tj:
                continue
            ri.add(i)
            tj.add(j)
            threads[j]["hist"][q] = rows[i]
        for i, r in enumerate(rows):
            if i not in ri:
                threads.append({"hist": {q: r}})
    return threads


def _cands(th, L):
    rows = [th["hist"][q] for q in sorted(th["hist"])]
    dts = {_dt8(r.get("dt")) for r in rows if r.get("dt")}
    xd = [d for d in (to_date(r.get("dt") or "") for r in rows) if d]
    key = max((len(X.nkey(r.get("nm"))) for r in rows), default=0)
    out = []
    for c in L:
        d = bool(dts & c["dates"])
        a = any(_near(r.get("amt"), c["amt"], 0.01) for r in rows)
        a15 = any(r.get("amt") and c["amt"] and abs(r["amt"] / c["amt"] - 1) <= 0.15 for r in rows)
        n = max(X._sim(a_, c["name"]) for r in rows for a_ in _names(r))
        p = max((X._sim(r.get("cl") or "", c["party"]) for r in rows if r.get("cl") and c["party"]), default=0)
        # 원장 계약일·시작일이 XI 신고일 ±45일 — 정정·변경 공시만 원장에 남은 오래된 계약(원접수가 원장 창 밖)을 잇는 근거.
        # `VLGC 2척`·`발전설비 공급계약` 같은 흔한 이름은 이 근거 없이 잇지 않는다(자매선이 같은 이름·같은 값으로 또 나온다).
        close = any(abs((x - y).days) <= 45 for x in xd for y in c["signed"])
        specific = key >= 10 and n >= 0.6
        if d and (a or n >= 0.3 or p >= 0.5):
            tier, score = "A", 3 + n + (1 if a else 0) + p / 2
            basis = "신고일+" + ("금액" if a else "이름" if n >= 0.3 else "상대방")
        elif d and (a15 or n >= 0.15):
            tier, score, basis = "B", 2 + n, "신고일+" + ("금액≈" if a15 else "이름≈")
        elif a and n >= 0.2 and (close or specific):
            tier, score, basis = "B", 1.5 + n + (0.3 if close else 0), "금액+이름" + ("+계약일" if close else "")
        elif a15 and n >= 0.5 and close:
            tier, score, basis = "B", 1 + n, "이름+금액≈+계약일"
        else:
            continue
        out.append((score, tier, basis, c))
    out.sort(key=lambda x: (-x[0], x[3]["rcp"]))
    return out


def link_all(threads, L):
    """실마다 최선 후보 하나. 1·2위 점수가 0.05 안이면 모호 → 연결 안 함. 원장 한 행을 두 실이 원하면 점수 높은 쪽."""
    want = []
    for k, th in enumerate(threads):
        cs = _cands(th, L)
        th["link"] = None
        th["cands"] = [(round(s, 3), c["rcp"], c["name"][:40]) for s, _t, _b, c in cs[:3]]
        if not cs:
            continue
        if len(cs) > 1 and cs[0][0] - cs[1][0] < 0.05 and cs[0][1] == cs[1][1]:
            th["ambiguous"] = True
            continue
        want.append((-cs[0][0], k, cs[0]))
    want.sort(key=lambda x: (x[0], x[1]))
    taken = set()
    for _s, k, (score, tier, basis, c) in want:
        if c["rcp"] in taken:
            threads[k]["ambiguous"] = True
            continue
        taken.add(c["rcp"])
        threads[k]["link"] = {"rcp": c["rcp"], "rcps": c["rcps"], "tier": tier, "basis": basis,
                              "score": round(score, 3), "_c": c}
    return threads


# ── 지표 ────────────────────────────────────────────────────────

def _months(a, b):
    return (b - a).days / 30.4375


def _add_months(d, m):
    return d + datetime.timedelta(days=round(m * 30.4375))


def _span(th, link):
    """계약기간(시작, 종료) — 원장이 있으면 원장, 없으면 XI 기간 칸."""
    c = (link or {}).get("_c")
    if c:
        s, e = to_date(c["start"]), to_date(c["end"])
        if s and e and e > s:
            return s, e, "원장"
    for q in sorted(th["hist"], reverse=True):
        per = th["hist"][q].get("period") or ""
        ds = [d for d in (to_date(x.group(0)) for x in _ISO.finditer(per)) if d]
        if len(ds) >= 2 and ds[-1] > ds[0]:
            return ds[0], ds[-1], "XI"
    return None, None, None


def _r(x, n=4):
    return None if x is None else round(x, n)


def metrics(th, latest_q, first_q):
    """실의 마지막 분기 값 기준 지표. 금액 백만원, 비율 0~1, 기간 개월."""
    qs = sorted(th["hist"])
    q = qs[-1]
    r = th["hist"][q]
    link = th.get("link")
    m = {"q": q}
    amt, basis = r.get("amt"), "xi"
    sup, recv = r.get("supCum"), r.get("recvCum")
    if amt is None and r.get("cur"):
        # 외화 계약. 공급·수령 열이 원화인지 그 외화인지는 표마다 다르다(풍산 USD 계약 + 원화 공급 / 진성이엔지 행 통화 USD 로
        # 공급·수령까지 USD). 원장 원화 금액 대비 공급이 1.5배 안이면 원화 공급으로 보고 원장 금액을 분모로(ledger_krw),
        # 아니면 공급·수령이 외화 계약금액 안에 들 때만 같은 외화로 보고 비율만 쓴다(fx_native — 원화 합계에서 뺀다).
        led = link["_c"]["amt"] if link else None
        if led and sup is not None and 0 <= sup <= led * 1.5:
            amt, basis = led, "ledger_krw"
        elif r.get("amt_fx") and (r.get("fx") or {}).get("supCum") is not None \
                and 0 <= r["fx"]["supCum"] <= r["amt_fx"] * 1.05 \
                and (r["fx"].get("recvCum") is None or r["fx"]["recvCum"] <= r["amt_fx"] * 1.05):
            amt, basis = r["amt_fx"], "fx_native"
            sup, recv = r["fx"]["supCum"], r["fx"].get("recvCum")
            m["unit"] = r["cur"]
    m["amt"], m["basis"] = amt, (basis if amt is not None else None)
    flags = []
    if th.get("suspect"):
        flags.append("unit_suspect")
    if r.get("cur"):
        flags.append("fx")
    if r.get("withheld"):
        flags.append("withheld")
    if r.get("cell_fix") or r.get("cell_drop"):
        flags.append("cell_fix")
    if amt and sup is not None:
        m["prog"] = _r(sup / amt)
        m["rem"] = max(amt - sup, 0)
        if sup / amt > OVER:
            flags.append("over")
    if sup is not None and recv is not None:
        m["ar"] = max(sup - recv, 0)          # 매출채권(순) — 공급했는데 아직 못 받은 돈
        m["adv"] = max(recv - sup, 0)         # 선수금(순) — 공급보다 먼저 받은 돈
        if sup:
            m["recv_ratio"] = _r(recv / sup)
    if amt and recv is not None:
        m["recv_prog"] = _r(recv / amt)       # 대금수령 진척(수령 ÷ 계약) — 조선처럼 선수금이 큰 계약도 0~100% 로 비교된다
    s, e, sb = _span(th, link)
    end_q = period_end(q)
    if s and e:
        m["start"], m["end"], m["span_src"] = s.isoformat(), e.isoformat(), sb
        m["elapsed"] = _r(min(max(_months(s, end_q) / _months(s, e), 0), 1.5))
        if m.get("prog") is not None:
            m["gap"] = _r(m["prog"] - m["elapsed"])
    # 공급 속도(월) — 직전 분기 값이 있으면 누적 차이, 없으면 당기(반기 6개월·사업 12개월)
    hv = lambda row, k: _hist_row(row, basis)[("amt", "supCur", "supCum", "recvCur", "recvCum").index(k)]  # noqa: E731
    prev = hv(th["hist"][qs[-2]], "supCum") if len(qs) >= 2 else None
    cur_sup = hv(r, "supCur")
    pace, pb = None, None
    if prev is not None and sup is not None:
        pace = (sup - prev) / _months(period_end(qs[-2]), end_q)
        pb = "Δ누적"
    elif cur_sup is not None:
        pace, pb = cur_sup / (6 if q[5] == "2" else 12), "당기"
    if pace is not None:
        m["pace"], m["pace_src"] = _r(pace, 3), pb
        if m.get("rem") and pace > 0:
            eta_m = m["rem"] / pace
            m["eta_m"] = _r(min(eta_m, 240), 1)
            if e and eta_m <= 240:
                m["slip_m"] = _r(_months(e, _add_months(end_q, eta_m)), 1)
    if prev is not None and sup is not None:
        if sup < prev * 0.99 - 1:
            flags.append("cum_drop")            # 누적이 줄었다 — 매출 취소·재분류 또는 원문 오기(원문 대조)
        elif abs(sup - prev) <= max(1, prev * 0.005) and m.get("rem") and 0.05 <= (m.get("prog") or 0) < DONE \
                and (m.get("elapsed") or 0) >= 0.3:
            flags.append("stalled")             # 이미 시작한 계약이 직전 보고 이후 공급 0
    if cur_sup is not None and cur_sup < 0:
        flags.append("reversal")                # 당기 판매ㆍ공급이 음수 — 매출 취소·계약 감액 신호
    # 계약금액 변동 — 분기 사이(XI)와 원장 공시 대비
    amts = [hv(th["hist"][x], "amt") for x in qs if hv(th["hist"][x], "amt")]
    if len(amts) >= 2 and not _near(amts[-1], amts[0], 0.01):
        m["chg_xi"] = _r(amts[-1] / amts[0] - 1)
    if link and basis == "xi" and amt and link["_c"]["amt"] and not _near(amt, link["_c"]["amt"], 0.01):
        m["chg_led"] = _r(amt / link["_c"]["amt"] - 1)
    if m.get("elapsed") is not None and m["elapsed"] >= 1 and m.get("prog") is not None and m["prog"] < DONE \
            and q == latest_q:
        flags.append("overdue")                 # 계약 종료일이 지났는데 공급 95% 미만(기간 말 기준)
    if (m.get("slip_m") or 0) >= 6 and (m.get("elapsed") or 0) >= 0.6:
        # 최근 공급 속도로는 종료일보다 6개월 이상 늦게 끝난다. 속도 외삽은 막바지에만 뜻이 있다 — 초기(경과 60% 전)는
        # 진행이 원래 느려(조선 표준 곡선: 경과 35%까지 진행 1% 미만) 늘 '지연'으로 나온다.
        flags.append("slip")
    # 상태 — 회사의 최신 분기 표에 있으면 진행, 빠졌으면 완료(직전 진행률 95% 이상)·이탈
    if q == latest_q:
        status = "new" if (len(qs) == 1 and q != first_q) else "active"
    else:
        status = "done" if (m.get("prog") or 0) >= DONE else "dropped"
    return m, flags, status


# ── build ───────────────────────────────────────────────────────

def _hdr(tab, st, name, q, parsed, rcp, root=None):
    """머리행 지도(role 'xi') — 실패해도 build 를 막지 않는다(hdrmap._guard)."""
    tables = [{"cols": t["cols"], "ncols": t["ncols"], "fields": t["fields"], "n": t["n"], "n_rec": t["n_rec"],
               "lead": t.get("lead") or "", "tag": "나"} for t in parsed["tables"]]
    rej = [{"cols": r["cols"], "ncols": r["ncols"], "fields": r["fields"], "n": r["n"],
            "lead": r.get("lead") or "", "reason": r["reason"]}
           for r in parsed.get("rejected") or [] if r["reason"] != "near_miss"]
    unk = [{"cols": r["cols"], "ncols": r["ncols"], "fields": r["fields"], "n": r["n"],
            "lead": r.get("lead") or "", "reason": "near_miss", "need": sorted(X.NEED), "rows": r.get("rows") or []}
           for r in parsed.get("rejected") or [] if r["reason"] == "near_miss"]
    hdrmap.record(tab, st, q, "xi", tables, picks=range(len(tables)), rejected=rej, unknown=unk,
                  meta={"name": name, "stock": st, "rcpNo": rcp}, root=root)


def build(tab, root=None, qs=None, ledger=None, hdr=True):
    """원문 캐시 → progress dict(쓰지는 않는다 — write_progress)."""
    names = dict(universe(tab, root))
    stat = load_status(tab, root)
    if qs is None:
        qs = sorted({k.split("|")[1] for k in stat}) or periods(latest_xi())
    L = load_ledger(tab, root) if ledger is None else ledger
    by_st = {}
    for c in L:
        by_st.setdefault(c["stock"], []).append(c)
    companies, contracts, review = {}, [], []
    for st, name in sorted(names.items()):
        cps, per_q = {}, []
        Ls = by_st.get(st, [])
        ref = [(c["name"], c["amt"]) for c in Ls if c["amt"]]
        for q in qs:
            rec = stat.get("%s|%s" % (st, q))
            if not rec:
                continue
            ent = {"status": rec.get("status")}
            if rec.get("rcp"):
                ent["rcp"] = rec["rcp"]
            doc = read_parsed(tab, st, q, root) if rec.get("status") == "ok" else None
            if doc is not None:
                parsed = {"tables": [dict(t, rows=[dict(r) for r in t["rows"]]) for t in doc["tables"]],
                          "rejected": doc["rejected"], "unknown_headers": [1] * doc.get("unknown", 0)}
                if ref:
                    X.calibrate(parsed, ref)
                if hdr:
                    _hdr(tab, st, name, q, parsed, rec.get("rcp"), root)
                rows = []
                for t in parsed["tables"]:
                    # 공급·수령 칸을 대부분 비운 표(LIG 전부, 한화시스템 방산 계약 — 보안상 진행 미기재, 민수 1건만 기재)는
                    # 빈칸이 0 이 아니라 '미기재'다. 행의 절반 이상이 그 열을 채운 표에서만 빈칸을 0 으로 본다.
                    nrow = len(t["rows"]) or 1
                    sup_any = sum(1 for r in t["rows"] if r.get("supCum") is not None) * 2 >= nrow
                    recv_any = sum(1 for r in t["rows"] if r.get("recvCum") is not None) * 2 >= nrow
                    if t["rows"] and not sup_any:
                        ent["sup_blank"] = True
                    for r in t["rows"]:
                        r = dict(r)
                        if t.get("unit_suspect"):
                            r["_suspect"] = True
                        cell_sanity(r)
                        blank_zero(r, sup_any, recv_any)
                        rows.append(r)
                fixes = sorted({t["unit_fix"] for t in parsed["tables"] if t.get("unit_fix")})
                ent.update(n=len(rows), tables=len(parsed["tables"]))
                if fixes:
                    ent["unit_fix"] = fixes
                if any(t.get("unit_suspect") for t in parsed["tables"]):
                    ent["unit_suspect"] = True
                if parsed["unknown_headers"]:
                    ent["status"] = "unknown_headers"
                elif not parsed["tables"]:
                    ent["status"] = "no_table"
                per_q.append((q, rows))
            cps[q] = ent
        if not cps:
            continue
        threads = link_all(thread(per_q), Ls)
        ok_qs = [q for q in qs if cps.get(q, {}).get("status") in ("ok", "unknown_headers")]
        latest = ok_qs[-1] if ok_qs else None
        first = ok_qs[0] if ok_qs else None
        items = []
        for k, th in enumerate(threads):
            th["suspect"] = any(r.get("_suspect") for r in th["hist"].values())
            m, flags, status = metrics(th, latest, first)
            last = th["hist"][max(th["hist"])]
            first_row = th["hist"][min(th["hist"])]
            item = {"id": "%s-%s-%02d" % (st, _dt8(first_row.get("dt")) or "nodate", k),
                    "stock": st, "nm": last.get("nm") or "", "cl": last.get("cl"), "dt": first_row.get("dt"),
                    "cur": last.get("cur"), "amt_fx": last.get("amt_fx"),
                    "hist": {q: _hist_row(r, m.get("basis")) for q, r in sorted(th["hist"].items())},
                    "m": m, "flags": flags, "status": status}
            if th.get("link"):
                lk = th["link"]
                item["link"] = {"rcp": lk["rcp"], "rcps": lk["rcps"], "tier": lk["tier"], "basis": lk["basis"]}
            else:
                review.append({"stock": st, "name": name, "id": item["id"], "nm": item["nm"], "dt": item["dt"],
                               "amt": m.get("amt"), "cands": th["cands"], "ambiguous": bool(th.get("ambiguous"))})
            items.append(item)
        contracts.extend(items)
        companies[st] = {"name": name, "periods": cps, "latest": latest, "_items": items, "_L": Ls}
    curve = sector_curve(contracts)
    for c in contracts:
        apply_curve(c, curve)
    for st, co in companies.items():
        items, Ls = co.pop("_items"), co.pop("_L")
        co["agg"] = company_agg(items, co["latest"], Ls)
        co["series"] = company_series(items, qs)
        co["flows"] = company_flows(items, qs, {q for q, p in co["periods"].items() if p["status"] == "ok"})
    prog = {"schema": SCHEMA, "tab": tab, "periods": qs, "asof": qs[-1] if qs else None, "curve": curve,
            "source": "반기·사업보고서 XI-1 「나. 단일판매ㆍ공급계약 진행 현황」(DART)",
            "rules": {"lag": LAG, "done": DONE, "over": OVER},
            "companies": companies, "contracts": contracts, "review": review}
    prog["sector"] = sector_agg(prog)
    prog["by_rcp"] = {r: c["id"] for c in contracts if c.get("link") for r in c["link"]["rcps"]}
    return prog


def sector_curve(contracts):
    """경과율 구간별 진행률 중앙값 → [{x, y, n}] (단조 비감소). 표본 5 미만 구간은 이웃 구간 사이 보간."""
    pts = [(c["m"]["elapsed"], c["m"]["prog"]) for c in contracts
           if c["status"] in ("active", "new") and c["m"].get("elapsed") is not None
           and c["m"].get("prog") is not None and not ({"unit_suspect", "over"} & set(c["flags"]))]
    raw = []
    for lo, hi in CURVE_BINS:
        ys = sorted(y for x, y in pts if lo <= x < hi or (hi == 1.5 and x >= hi))
        raw.append(((lo + hi) / 2, _median(ys) if len(ys) >= CURVE_MIN_N else None, len(ys)))
    known = [(x, y) for x, y, _n in raw if y is not None]
    if len(known) < 3:
        return []
    out, top = [], 0.0
    for x, y, n in raw:
        if y is None:
            lo = [k for k in known if k[0] < x]
            hi = [k for k in known if k[0] > x]
            if lo and hi:
                (x0, y0), (x1, y1) = lo[-1], hi[0]
                y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            else:
                y = (lo[-1] if lo else hi[0])[1]
        top = max(top, y)
        out.append({"x": round(x, 3), "y": round(top, 4), "n": n})
    return out


def _median(xs):
    if not xs:
        return None
    k = len(xs) // 2
    return xs[k] if len(xs) % 2 else (xs[k - 1] + xs[k]) / 2


def curve_at(curve, x):
    if not curve or x is None:
        return None
    pts = [(0.0, 0.0)] + [(p["x"], p["y"]) for p in curve]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 > x0 else y1
    return None


def apply_curve(c, curve):
    m = c["m"]
    exp = curve_at(curve, m.get("elapsed"))
    if exp is None or m.get("prog") is None:
        return
    m["exp"] = _r(exp)
    m["gap_c"] = _r(m["prog"] - exp)
    if c["status"] in ("active", "new") and m["gap_c"] <= LAG and 0.2 <= m["elapsed"] < 1.0 \
            and "unit_suspect" not in c["flags"]:
        c["flags"].append("lag")


def _hist_row(r, basis):
    """[계약, 공급 당기, 공급 누적, 수령 당기, 수령 누적] — fx_native 는 같은 외화 맨숫자(원화 합계에 안 쓴다)."""
    if basis == "fx_native":
        fx = r.get("fx") or {}
        return [r.get("amt_fx")] + [fx.get(f) for f in ("supCur", "supCum", "recvCur", "recvCum")]
    return [r.get(f) for f in ("amt", "supCur", "supCum", "recvCur", "recvCum")]


def _krw_ok(c):
    return c["m"].get("amt") and c["m"].get("basis") == "xi" and "unit_suspect" not in c["flags"]


_PARTY_NOISE = re.compile(r"^대한민국|\(주\)|주식회사|㈜|\s+|[.,·ㆍ]|\(.*?\)$")


def party_key(s):
    """계약상대 묶음 키 — `대한민국 방위사업청`=`방위사업청`, `(주)`·공백·끝 괄호 부연 무시. 익명(`… 지역 선주`)은 그대로."""
    return _PARTY_NOISE.sub("", s or "").lower()


def company_agg(items, latest, Ls):
    cur = [c for c in items if c["m"]["q"] == latest] if latest else []
    k = [c for c in cur if _krw_ok(c)]
    amt = sum(c["m"]["amt"] for c in k)
    sup = sum(c["hist"][latest][2] or 0 for c in k)
    rem = sum(c["m"].get("rem") or 0 for c in k)
    ar = sum(c["m"].get("ar") or 0 for c in k)
    adv = sum(c["m"].get("adv") or 0 for c in k)
    half = sum(c["hist"][latest][1] or 0 for c in k)
    fx = {}
    for c in cur:
        if c.get("cur") and not _krw_ok(c):
            fx[c["cur"]] = fx.get(c["cur"], 0) + 1
    big = sorted((c["m"]["amt"] for c in k), reverse=True)
    pace_y = sum(max(c["m"].get("pace") or 0, 0) for c in k) * 12
    parties = {}
    for c in k:
        raw = (c.get("cl") or "").strip()
        key = party_key(raw) or "(미기재)"
        cur_ = parties.setdefault(key, [raw or "(미기재)", 0.0])
        if raw and len(raw) < len(cur_[0]):
            cur_[0] = raw
        cur_[1] += c["m"].get("rem") or 0
    linked = [c for c in items if c.get("link")]
    # 원장 대응률: 원장 계약 중 진행 현황 기간(첫 보고 기간 시작 이후 종료) 안에 있는데 해지가 아닌 것 → 그중 XI 에 실린 비율
    w0 = datetime.date(2024, 1, 1)
    live = [c for c in Ls if not c["term"] and (to_date(c["end"]) or datetime.date(2100, 1, 1)) >= w0]
    got = {c["link"]["rcp"] for c in linked}
    return {"n": len(cur), "n_krw": len(k), "fx": fx, "amt": round(amt, 3), "sup": round(sup, 3),
            "rem": round(rem, 3), "ar": round(ar, 3), "adv": round(adv, 3), "sup_cur": round(half, 3),
            "prog_w": _r(sup / amt) if amt else None,
            "top3": _r(sum(big[:3]) / amt) if amt else None,
            # 연간 공급 속도(최근 월 속도 × 12)와 잔여 소진 기간 — 공시 계약만의 매출 가시성(II-4·매출 전체가 아니다)
            "pace_y": round(pace_y, 3), "burn_y": _r(rem / pace_y, 2) if pace_y > 0 else None,
            "parties": [[k_, d_, round(v, 3)] for k_, (d_, v) in sorted(parties.items(), key=lambda x: (-x[1][1], x[0]))[:5]],
            "lag": sum(1 for c in cur if "lag" in c["flags"]),
            "overdue": sum(1 for c in cur if "overdue" in c["flags"]),
            "stalled": sum(1 for c in cur if "stalled" in c["flags"]),
            "reversal": sum(1 for c in cur if "reversal" in c["flags"]),
            "cum_drop": sum(1 for c in cur if "cum_drop" in c["flags"]),
            "slip6": sum(1 for c in cur if "slip" in c["flags"]),
            "chg_up": sum(1 for c in cur if (c["m"].get("chg_xi") or c["m"].get("chg_led") or 0) > 0.01),
            "done": sum(1 for c in items if c["status"] == "done"),
            "dropped": sum(1 for c in items if c["status"] == "dropped"),
            "new": sum(1 for c in items if c["status"] == "new"),
            "linkA": sum(1 for c in linked if c["link"]["tier"] == "A"),
            "linkB": sum(1 for c in linked if c["link"]["tier"] == "B"),
            "xi_only": sum(1 for c in items if not c.get("link")),
            "ledger_live": len(live), "ledger_found": len(got & {c["rcp"] for c in live})}


def company_flows(items, qs, periods_ok):
    """보고 기간 사이 잔여 다리(원화 계약만): 시작 잔여 + 신규 + 금액 변동 − 공급 − 이탈 = 끝 잔여(+ 끝수 resid).
    두 기간 모두 표가 있는 경우만(한쪽이 비면 다리를 만들지 않는다 — 수집 공백을 '이탈'로 읽지 않게)."""
    out = {}
    ok = [q for q in qs if q in periods_ok]
    for p, q in zip(ok, ok[1:]):
        f = {"from": p, "start": 0.0, "new": 0.0, "new_n": 0, "chg": 0.0, "supplied": 0.0, "exit": 0.0, "exit_n": 0,
             "end": 0.0}
        for c in items:
            if c["m"].get("basis") != "xi" or "unit_suspect" in c["flags"]:
                continue
            a, b = c["hist"].get(p), c["hist"].get(q)
            a = a if a and a[0] and a[2] is not None else None        # 공급 미기재 행은 다리에서 뺀다(잔여를 모른다)
            b = b if b and b[0] and b[2] is not None else None
            ra = max(a[0] - a[2], 0) if a else None
            rb = max(b[0] - b[2], 0) if b else None
            if ra is not None:
                f["start"] += ra
            if rb is not None:
                f["end"] += rb
            if a and b:
                f["chg"] += b[0] - a[0]
                f["supplied"] += b[2] - a[2]
            elif b and q in c["hist"] and p not in c["hist"]:
                f["new"] += b[0]
                f["new_n"] += 1
                f["supplied"] += b[2]
            elif a and p in c["hist"] and q not in c["hist"]:
                f["exit"] += ra
                f["exit_n"] += 1
            elif a and not b:                                       # q 에서 공급 칸이 비었다 — 다리 밖으로
                f["start"] -= ra
            elif b and not a:                                       # p 에서 공급 칸이 비었다
                f["end"] -= rb
        f["resid"] = f["end"] - (f["start"] + f["new"] + f["chg"] - f["supplied"] - f["exit"])
        out[q] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()}
    return out


def company_series(items, qs):
    out = {}
    for q in qs:
        rows = [c for c in items if q in c["hist"] and c["hist"][q][0] and "unit_suspect" not in c["flags"]
                and c["m"].get("basis") != "fx_native"]
        if not rows:
            continue
        amt = sum(c["hist"][q][0] for c in rows)
        sup = sum(c["hist"][q][2] or 0 for c in rows)
        both = [c for c in rows if c["hist"][q][2] is not None and c["hist"][q][4] is not None]
        out[q] = {"n": len(rows), "amt": round(amt, 3), "sup": round(sup, 3),
                  "rem": round(sum(max(c["hist"][q][0] - (c["hist"][q][2] or 0), 0) for c in rows), 3),
                  "recv": round(sum(c["hist"][q][4] for c in both), 3),
                  "sup_both": round(sum(c["hist"][q][2] for c in both), 3),
                  "sup_cur": round(sum(c["hist"][q][1] or 0 for c in rows), 3)}
    return out


def sector_agg(prog):
    series = {}
    for q in prog["periods"]:
        cos = [co for co in prog["companies"].values() if q in co["series"]]
        if not cos:
            continue
        series[q] = {"cos": len(cos), **{k: round(sum(co["series"][q][k] for co in cos), 3)
                                         for k in ("n", "amt", "sup", "rem", "recv", "sup_cur", "sup_both")}}
    cos = prog["companies"].values()
    tot = lambda k: round(sum(co["agg"][k] or 0 for co in cos), 3)        # noqa: E731
    st = {}
    for co in cos:
        for p in co["periods"].values():
            st[p["status"]] = st.get(p["status"], 0) + 1
    amt, sup = tot("amt"), tot("sup")
    flows = {}
    for co in cos:
        for q, f in (co.get("flows") or {}).items():
            g = flows.setdefault(q, {"from": f["from"], "cos": 0})
            g["cos"] += 1
            for k_, v in f.items():
                if k_ not in ("from",):
                    g[k_] = round(g.get(k_, 0) + v, 3)
    parties = {}
    for co in cos:
        for k_, d_, v in co["agg"].get("parties") or []:
            if k_ != "(미기재)":
                cur_ = parties.setdefault(k_, [d_, 0.0, 0])
                if len(d_) < len(cur_[0]):
                    cur_[0] = d_
                cur_[1] += v
                cur_[2] += 1
    pace_y = tot("pace_y")
    return {"series": series, "status": st, "flows": flows,
            "parties": [[d_, round(v, 3), n_] for k_, (d_, v, n_) in sorted(parties.items(), key=lambda x: (-x[1][1], x[0]))[:15]],
            "pace_y": pace_y, "burn_y": _r(tot("rem") / pace_y, 2) if pace_y > 0 else None,
            "cos_with_rows": sum(1 for co in cos if co["agg"]["n"]),
            "n": tot("n"), "amt": amt, "sup": sup, "rem": tot("rem"), "ar": tot("ar"), "adv": tot("adv"),
            "prog_w": _r(sup / amt) if amt else None, "lag": tot("lag"), "overdue": tot("overdue"), "slip6": tot("slip6"),
            "stalled": tot("stalled"), "reversal": tot("reversal"), "cum_drop": tot("cum_drop"), "linkA": tot("linkA"), "linkB": tot("linkB"), "xi_only": tot("xi_only")}


def subset(prog, stocks):
    """탭 화면이 모집단 일부만 보여 줄 때(ksemi 편입 83사) — 그 종목만 남기고 섹터 집계를 다시 낸다. 곡선은 그대로(탭 표준)."""
    if not prog:
        return prog
    keep = set(stocks)
    out = dict(prog)
    out["companies"] = {st: co for st, co in prog["companies"].items() if st in keep}
    out["contracts"] = [c for c in prog["contracts"] if c["stock"] in keep]
    out["review"] = [r for r in prog.get("review") or [] if r["stock"] in keep]
    out["by_rcp"] = {r: i for r, i in (prog.get("by_rcp") or {}).items() if i.split("-")[0] in keep}
    out["sector"] = sector_agg(out)
    return out


def write_progress(tab, prog, root=None):
    d = xi_dir(tab, root)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "progress.json")
    atomic_write(p, _dump(prog))
    return p


def load_progress(tab=None, root=None, path=None):
    """페이지 생성기용 — 없으면 None(섹션을 만들지 않는다)."""
    p = path or os.path.join(xi_dir(tab, root), "progress.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tab", choices=TABS)
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--quarters", help="쉼표 목록(기본: 2024Q4 ~ 최신 Q2·Q4)")
    ap.add_argument("--only", help="종목코드 쉼표 목록")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--recheck-all", action="store_true")
    ap.add_argument("--lanes", type=int, default=1)
    ap.add_argument("--no-hdr", action="store_true")
    a = ap.parse_args(argv)
    qs = a.quarters.split(",") if a.quarters else periods(latest_xi())
    stocks = a.only.split(",") if a.only else None
    if a.collect:
        collect(a.tab, stocks, qs, force=a.force, recheck_all=a.recheck_all, lanes=a.lanes)
    if a.build:
        prog = build(a.tab, qs=qs, hdr=not a.no_hdr)
        if not a.no_hdr:
            hdrmap.write(a.tab)
        p = write_progress(a.tab, prog)
        s = prog["sector"]
        print("xi1 %s: 회사 %d(행 있음 %d) · 계약 %d · 연결 A%d/B%d · XI 전용 %d · 지연 의심 %d → %s"
              % (a.tab, len(prog["companies"]), s["cos_with_rows"], len(prog["contracts"]), s["linkA"], s["linkB"],
                 s["xi_only"], s["lag"], os.path.relpath(p, ARGUS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
