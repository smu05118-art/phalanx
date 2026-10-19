#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_fin — 분기 매출액·영업이익·당기순이익(연결 우선, 없으면 별도). 캐파 탭의 분기 마진 프록시 입력.

정기보고서 목차에서 `n. 연결재무제표` 절(없으면 `n. 재무제표` = 별도, basis 'sep')을 받아 kship_fin.parse_fin_section 으로
읽는다 — 값은 **백만원**으로 정규화돼 있다(단위 캡션을 못 읽으면 `unit_assumed`). IS 열 태그는 `cur_q`(3개월)·`cur_ytd`(누적)·
`cur_full`(연간 또는 기간 표기 없음). 계정명은 kship_fin ACCOUNT_MAP 의 FnGuide 이름(`매출액(수익)`·`영업이익`·`당기순이익`)이고
여기서는 `매출액`·`영업이익`·`당기순이익` 키로 옮긴다.

분기화(build_series): 3개월 열이 있으면 그 값(src '3m_column'), 없으면 누적차분(src 'ytd_diff') — Q1 = 누적, Qn = 누적 − 같은 해
직전 분기 누적, Q4 = 연간 − 3Q 누적. 직전 누적이 없으면 null + `no_prior_ytd` flag(추정하지 않는다). 3개월 열이 있어도 누적차분을
만들어 1백만원 넘게 다르면 `ytd_diff_mismatch` flag(후속 보고서의 전기 재작성 흔적 — kship_fin `restated` 와 같은 뜻).

수집은 **순차**(DART 는 공인 IP 단위로 막는다 — 병렬 금지). 캐시 assets/cache/<stock>/<q>_fin.html(+ _fin.meta.json),
산출 assets/fin/<stock>.json({stock, name, quarters:{q: parse_quarter}, series:[build_series], errors}). 실패는 errors 에 적고
기존 분기는 유지한다(fail-closed).

    python3 kcap_fin.py --stocks 006650 --quarters 2024Q3..2026Q2 [--force]
    python3 kcap_fin.py --stocks 006650 --build                       # 캐시만으로(요청 0)
    python3 kcap_fin.py --fixture tests/fixtures/fin_006650_2026Q2_cons.html --quarter 2026Q2
"""
import argparse
import datetime
import json
import os
import re
import sys
import unicodedata

from kcap_lib import (CACHE, fetch_section, load_asset, pick_report, q_prev, q_range, read_cache,  # noqa: F401
                      report_kind, search_reports, search_window, toc, write_asset, write_cache)
import kship_fin                                              # kcap_lib 가 kship/tools·kce/tools 를 sys.path 에 넣은 뒤

KEYS = {"매출액": "매출액(수익)", "영업이익": "영업이익", "당기순이익": "당기순이익"}   # 우리 키 → kship_fin 계정명
UNIT = "백만원"
TOL = 1.0                                                     # 백만원 — 3개월 열 vs 누적차분 대조 허용 오차
MAX_CANDIDATES = 3                                            # pick_report 후보를 몇 개까지 열어 보나(첫 후보가 정정신고일 수 있다)
_CONS = re.compile(r"^\s*\d+\.\s*연결\s*재무제표\s*$")
_SEP = re.compile(r"^\s*\d+\.\s*재무제표\s*$")
_REPORT_TITLE = re.compile(r"(사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)")


# ── 목차 ────────────────────────────────────────────────────────────────────

def fin_node(nodes):
    """목차 → (노드, basis). `n. 연결재무제표` → 'cons', 없으면 `n. 재무제표` → 'sep'. `… 주석` 절은 정규식 끝 고정으로 걸리지 않는다."""
    for rx, basis in ((_CONS, "cons"), (_SEP, "sep")):
        for n in nodes or []:
            t = unicodedata.normalize("NFKC", n.get("text") or "")
            if rx.match(t):
                return n, basis
    return None, None


def _title_ok(title, quarter):
    """정기보고서 제목의 기준월이 분기말과 맞는가 — 안 맞는 문서(다른 분기·정정신고)는 열지 않는다."""
    m = _REPORT_TITLE.search(title or "")
    return bool(m) and (m.group(2), m.group(3)) == (quarter[:4], "%02d" % (int(quarter[5]) * 3))


# ── 절 하나 → 분기 레코드 ───────────────────────────────────────────────────

def _pick(d):
    if d is None:
        return None
    return {k: d.get(src) for k, src in KEYS.items()}


def parse_quarter(html, quarter, basis=None, rcp=None):
    """절 HTML → {q, basis, rcp, unit, unit_assumed, found, tags_seen, cur{매출액,영업이익,당기순이익}, cur_ytd{…}, flags}.
    cur 는 3개월 열(없으면 None), cur_ytd 는 누적 열(없으면 연간/단일 열 cur_full). 값은 백만원."""
    p = kship_fin.parse_fin_section(html)
    isd = p.get("is") or {}
    flags = []
    for f in p.get("flags") or []:                            # kship_fin 은 (code, msg) 튜플
        flags.append("%s: %s" % (f[0], f[1]) if isinstance(f, (list, tuple)) and len(f) >= 2 else str(f))
    # 손실 분기: face 가 '영업손실'·'분기순손실' 라벨을 쓰면 kship_fin ACCOUNT_MAP 에 안 걸려 영업이익이 비는다(롯데케미칼 2024Q3~2025Q4 실측).
    # 같은 표를 다시 읽어 손실 라벨 행을 음수로 채운다 — 라벨이 '손실' 이면 부호는 항상 음수(괄호 유무와 무관).
    _recover_loss_labels(html, isd, flags)
    cur_q = isd.get("cur_q")
    ytd = isd.get("cur_ytd")
    if ytd is None and isd.get("cur_full") is not None:
        ytd = isd["cur_full"]
        if int(quarter[5]) != 4:
            flags.append("ytd_from_unlabeled_column")          # 3개월/누적 표기 없는 단일 열 — 누적으로 본다
    if not isd:
        flags.append("no_income_statement")
    elif cur_q is None:
        flags.append("no_3m_column")
    if p.get("unit_assumed"):
        flags.append("unit_assumed")
    return {"q": quarter, "basis": basis, "rcp": rcp, "unit": UNIT, "unit_assumed": bool(p.get("unit_assumed")),
            "found": list(p.get("found") or []), "tags_seen": sorted(isd), "cur": _pick(cur_q), "cur_ytd": _pick(ytd),
            "flags": flags}


# ── 분기 시계열 ─────────────────────────────────────────────────────────────

_LOSS_RX = [
    (re.compile(r"^영업(손실|이익\(손실\)|손익)$"), "영업이익"),
    (re.compile(r"^(연결)?(당기|분기|반기)?순손실$"), "당기순이익"),
]


def _recover_loss_labels(html, isd, flags):
    """face 손익계산서(없으면 포괄손익계산서)에서 '영업손실'·'분기순손실' 행을 찾아 비어 있는 계정을 −|값| 으로 채운다."""
    need = [k for k in ("영업이익", "당기순이익") if not any((isd.get(t) or {}).get(k) is not None for t in isd)]
    if not need:
        return
    try:
        st = kship_fin.statements_of(html)
    except Exception:
        return
    src = st.get("is") or st.get("cis")
    if not src:
        return
    tags = src.get("tags") or []
    for row in src.get("rows") or []:
        label = kship_fin.norm_label(row[0])
        for rx, acct in _LOSS_RX:
            if acct in need and rx.match(label):
                for tg, v in zip(tags, row[1:]):
                    if v is None or tg not in isd:
                        continue
                    if isd[tg].get(acct) is None:
                        isd[tg][acct] = -abs(float(v))
                        if tg.startswith("cur") and ("loss_label:%s" % acct) not in flags:
                            flags.append("loss_label:%s" % acct)


def _sub(a, b):
    if a is None or b is None:
        return None
    return round(a - b, 2)


def build_series(per_q):
    """{q: parse_quarter 결과} → {'quarters': [{q, basis, rcp, rev_q, op_q, ni_q, rev_ytd, op_ytd, ni_ytd, src, how, unit, flags}]}.
    src '3m_column'(3개월 열) | 'ytd_diff'(누적차분: Q1 = 누적, Qn = 누적 − 직전 분기 누적, Q4 = 연간 − 3Q 누적) | None."""
    out = []
    for q in sorted(per_q):
        p = per_q[q] or {}
        n = int(q[5])
        flags = list(p.get("flags") or [])
        cur, ytd = p.get("cur"), p.get("cur_ytd")
        rec = {"q": q, "basis": p.get("basis"), "rcp": p.get("rcp"), "unit": UNIT,
               "rev_q": None, "op_q": None, "ni_q": None,
               "rev_ytd": (ytd or {}).get("매출액"), "op_ytd": (ytd or {}).get("영업이익"), "ni_ytd": (ytd or {}).get("당기순이익"),
               "src": None, "how": None, "flags": flags}
        diff, how, missing = None, None, None
        if ytd:
            if n == 1:
                diff, how = dict(ytd), "ytd_as_3m(Q1)"
            else:
                pq = q_prev(q)                                # Q2→Q1 · Q3→Q2 · Q4→Q3 — 같은 회계연도
                prev = (per_q.get(pq) or {}).get("cur_ytd")
                if prev:
                    diff = {k: _sub(ytd.get(k), prev.get(k)) for k in KEYS}
                    how = "annual_minus_9M" if n == 4 else "ytd_minus_prev_ytd"
                else:
                    missing = pq
        has_cur = bool(cur) and any(v is not None for v in cur.values())
        if has_cur:
            vals, src = cur, "3m_column"
            if diff:
                for k in KEYS:
                    a, b = diff.get(k), cur.get(k)
                    if a is not None and b is not None and abs(a - b) > TOL:
                        flags.append("ytd_diff_mismatch:%s:%s" % (k, round(a - b, 2)))
        elif diff:
            vals, src = diff, "ytd_diff"
            rec["how"] = how
        else:
            vals, src = {}, None
            flags.append("no_prior_ytd:%s" % missing if missing else "no_income_data")
        rec.update({"rev_q": vals.get("매출액"), "op_q": vals.get("영업이익"), "ni_q": vals.get("당기순이익"), "src": src})
        out.append(rec)
    return {"quarters": out}


# ── 수집 ────────────────────────────────────────────────────────────────────

def _today():
    return datetime.date.today().strftime("%Y-%m-%d")


def _meta_name(q):
    return "%s_fin.meta.json" % q


def _read_meta(stock, q):
    raw = read_cache(stock, _meta_name(q))
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def _fetch_quarter(stock, q):
    """검색 → 후보(기준월이 맞는 것만, 최대 MAX_CANDIDATES) → 목차 → 재무제표 절. 반환 (html, meta) 또는 (None, 사유)."""
    start, end = search_window(q)
    reps = pick_report(search_reports(stock, start, end, report_kind(q)), q)
    if not reps:
        return None, "정기보고서 없음(%s~%s)" % (start, end)
    tried = []
    for rcp, title in reps[:MAX_CANDIDATES]:
        if not _title_ok(title, q):
            tried.append((rcp, "기준월 불일치: %s" % title))
            continue
        node, basis = fin_node(toc(rcp))
        if node is None:
            tried.append((rcp, "재무제표 절 없음"))
            continue
        html = fetch_section(node)
        if not html or "<table" not in html.lower():
            tried.append((rcp, "절 본문에 표 없음"))              # 실패는 캐시하지 않는다
            continue
        return html, {"rcp": rcp, "title": title, "basis": basis, "node": node.get("text"), "q": q}
    return None, "후보 %d건 모두 실패: %s" % (len(reps[:MAX_CANDIDATES]), tried)


def _merge_and_write(stock, name, per_q, errors):
    old = load_asset("fin/%s.json" % stock, default={})
    quarters = dict(old.get("quarters") or {})
    quarters.update(per_q)                                    # 새 파싱이 옛 분기를 덮는다 — 기존 분기는 유지(fail-closed)
    series = build_series(quarters)["quarters"]
    data = {"stock": stock, "name": name, "unit": UNIT, "quarters": quarters, "series": series,
            "errors": errors}
    write_asset("fin/%s.json" % stock, data)
    return data


def collect(stock, name, quarters, force=False, log=None):
    """분기마다 (캐시 없으면) 검색·목차·절 요청을 **순차**로 하고 파싱해 fin/<stock>.json 에 병합 저장.
    반환 {'ok','stock','n_quarters','errors','written'} — 예외는 전파하지 않는다."""
    log = log or sys.stderr
    errors, per_q = [], {}
    for q in quarters:
        cname = "%s_fin.html" % q
        html = None if force else read_cache(stock, cname)
        meta = _read_meta(stock, q) if html is not None else {}
        if html is None:
            try:
                html, meta = _fetch_quarter(stock, q)
            except Exception as e:                            # 네트워크·목차 파싱 — 분기 단위로 fail-closed
                errors.append({"q": q, "stage": "fetch", "error": "%s: %s" % (type(e).__name__, e)})
                continue
            if html is None:
                errors.append({"q": q, "stage": "search", "error": meta})
                continue
            write_cache(stock, cname, html)
            write_cache(stock, _meta_name(q), json.dumps(meta, ensure_ascii=False))
        try:
            rec = parse_quarter(html, q, basis=meta.get("basis"), rcp=meta.get("rcp"))
            rec["title"] = meta.get("title")
            per_q[q] = rec
        except Exception as e:
            errors.append({"q": q, "stage": "parse", "error": "%s: %s" % (type(e).__name__, e)})
    if not per_q:
        log.write("[kcap_fin] %s %s 파싱된 분기 없음 — 산출 파일을 건드리지 않음(오류 %d)\n" % (stock, name, len(errors)))
        return {"ok": False, "stock": stock, "n_quarters": 0, "errors": errors, "written": False}
    data = _merge_and_write(stock, name, per_q, errors)
    log.write("[kcap_fin] %s %s 분기 %d(이번 %d) · 오류 %d\n" % (stock, name, len(data["quarters"]), len(per_q), len(errors)))
    return {"ok": not errors, "stock": stock, "n_quarters": len(data["quarters"]), "errors": errors, "written": True}


def build(stock, name=None, log=None):
    """캐시된 분기들로 분기 손익 시계열을 만든다(요청 0). 반환 build_series 결과; 캐시가 있으면 fin/<stock>.json 도 갱신."""
    log = log or sys.stderr
    folder = os.path.join(CACHE, stock)
    per_q, errors = {}, []
    files = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    for f in files:
        m = re.match(r"^(\d{4}Q[1-4])_fin\.html$", f)
        if not m:
            continue
        q = m.group(1)
        meta = _read_meta(stock, q)
        try:
            rec = parse_quarter(read_cache(stock, f), q, basis=meta.get("basis"), rcp=meta.get("rcp"))
            rec["title"] = meta.get("title")
            per_q[q] = rec
        except Exception as e:
            errors.append({"q": q, "stage": "parse", "error": "%s: %s" % (type(e).__name__, e)})
    if not per_q:
        log.write("[kcap_fin] %s 캐시 없음 — 시계열 비움\n" % stock)
        return {"quarters": [], "errors": errors}
    old = load_asset("fin/%s.json" % stock, default={})
    data = _merge_and_write(stock, name or old.get("name") or stock, per_q, errors)
    return {"quarters": data["series"], "errors": errors}


# ── CLI ─────────────────────────────────────────────────────────────────────

def parse_quarters(spec):
    """'2024Q3..2026Q2' → 범위, '2026Q1,2026Q2' → 목록."""
    out = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ".." in part:
            a, b = part.split("..", 1)
            out.extend(q_range(a.strip(), b.strip()))
        else:
            out.append(part)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="분기 매출액·영업이익(연결 우선) — 정기보고서 재무제표 절")
    ap.add_argument("--stocks", default="", help="종목코드, 쉼표 구분")
    ap.add_argument("--quarters", default="", help="예: 2024Q3..2026Q2")
    ap.add_argument("--build", action="store_true", help="캐시만으로 시계열(요청 0)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fixture", default="", help="절 HTML 파일 하나를 파싱해 출력(요청 0)")
    ap.add_argument("--quarter", default="2026Q2")
    a = ap.parse_args(argv)
    if a.fixture:
        with open(a.fixture, encoding="utf-8") as f:
            html = f.read()
        rec = parse_quarter(html, a.quarter)
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        return 0
    stocks = [s for s in a.stocks.split(",") if s]
    if not stocks:
        ap.error("--stocks 가 필요하다")
    names = {r["stock"]: r["name"] for r in load_asset("universe.json", default={"rows": []}).get("rows", [])}
    bad = 0
    for st in stocks:
        if a.build:
            res = build(st, names.get(st))
            print("%s %s 분기 %d · 오류 %d" % (st, names.get(st, ""), len(res["quarters"]), len(res["errors"])))
            for r in res["quarters"]:
                print("   %s %s rev_q %s op_q %s (%s) %s" % (r["q"], r["basis"], r["rev_q"], r["op_q"], r["src"], ",".join(r["flags"])))
            bad += 1 if res["errors"] else 0
            continue
        qs = parse_quarters(a.quarters)
        if not qs:
            ap.error("--quarters 가 필요하다(예: 2024Q3..2026Q2)")
        res = collect(st, names.get(st, st), qs, force=a.force)
        print("%s %s ok=%s quarters=%s errors=%d written=%s" % (st, names.get(st, ""), res["ok"], res["n_quarters"], len(res["errors"]), res["written"]))
        for err in res["errors"]:
            print("   ", json.dumps(err, ensure_ascii=False))
        bad += 0 if res["ok"] else 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
