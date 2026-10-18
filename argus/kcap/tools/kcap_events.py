#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_events — 캐파 변동 이벤트 원장(거래소 수시공시 I001).

제목으로 고르는 공시(`classify`): 신규시설투자등(자율공시 포함)·생산중단·생산재개·영업정지·유형자산 양도/취득결정·영업양도/양수.
접미 `(자회사의 주요경영사항)`·`(종속회사의주요경영사항)` → `subsidiary`, 접두 `[기재정정]`·`[첨부정정]` → `corrected`.

본문(viewer.do 노드 하나)은 거래소 xforms 격자 — (항목 | 세부항목 | 값) 이고 값 칸은 colspan 으로 두 번 전개된다.
`parse_tables` 가 전개한 행을 kship_contracts._kv 방식으로 평탄화한다: 마지막 칸이 값, 그 앞의 서로 다른 칸을 이어 붙인 것이
**원문 라벨**이며 `kv` 에 전부 남긴다('2. 생산중단내역 생산중단 분야의 매출액(원)' → '2,828,725,728,648').
정정 공시는 앞에 `정정신고(보고)` 표(정정항목 | 정정전 | 정정후)가 붙는다 — 그 본문은 `correction` 에, 정정사유·정정관련
공시서류제출일은 `kv` 에 둔다. `fields` 는 정규화 키(amount_krw·pct·purpose·reason·scope·period_start/end·halt_date·restart_date·
decided·capa_text)이고 **못 읽으면 null — 추정하지 않는다**. capa_text 는 `N만톤|N천톤|N톤/년|capa` 주변 40자를 뽑기만 한다.

`supersede`: 같은 (type, scope|purpose 정규화, period_start|decided) 의 뒤 접수가 앞을 덮는다(kship `supersedes`). 정정 공시가 적은
'정정관련 공시서류제출일' 과 같은 날 접수된 같은 type 의 앞 공시가 있으면 그 연결을 먼저 쓴다(이사회결의일이 정정으로 바뀌어도 이어진다).
덮인 이벤트도 원장에 남긴다(`superseded_by`) — 이력 보존.

캐시: assets/cache/<stock>/ev_<rcpNo>.html(+ .meta.json) · 산출: assets/events/<stock>.json. 실패는 fail-closed — 예외를 밖으로
던지지 않고 `errors[]` 에 적으며, 검색 창 하나라도 실패하면 산출 파일을 건드리지 않는다(캐시는 남아 재실행이 싸다).

    python3 kcap_events.py --stocks 006650,011170 [--since 20240101] [--until YYYYMMDD] [--force]
    python3 kcap_events.py --stocks 006650 --rebuild                      # 캐시만으로 재파싱(요청 0)
    python3 kcap_events.py --fixture tests/fixtures/ev_006650_생산중단_20261006800696.html --title 생산중단
"""
import argparse
import datetime
import html as _html
import json
import os
import re
import sys

from kcap_lib import (CACHE, fetch_section, load_asset, parse_tables, read_cache, search_reports,  # noqa: F401
                      to_float, toc, write_asset, write_cache)

MAX_RESULTS = 100           # kce_fetch.search_reports 의 maxResults — 이만큼 오면 잘린 것으로 보고 창을 쪼갠다
MIN_WINDOW_DAYS = 28        # 이보다 짧은 창이 그래도 100건이면 errors 에 적고 받은 것만 쓴다
_WS = re.compile(r"[\s\xa0　]+")

# ── 제목 분류 ──────────────────────────────────────────────────────────────
# (type, 정규화 제목에 들어 있어야 할 낱말) — 위에서부터 첫 적중
TYPES = [
    ("invest", "신규시설투자"),          # 신규 시설투자 등(자율공시)
    ("restart", "생산재개"),
    ("halt", "생산중단"),
    ("suspend", "영업정지"),
    ("asset_sale", "유형자산양도"),      # 유형자산 양도결정 — 설비 매각
    ("asset_buy", "유형자산취득"),       # 유형자산 취득결정 — 설비 매입
    ("biz_sale", "영업양도"),
    ("biz_buy", "영업양수"),
]
TYPE_LABEL = {"invest": "신규시설투자", "restart": "생산재개", "halt": "생산중단", "suspend": "영업정지",
              "asset_sale": "유형자산 양도", "asset_buy": "유형자산 취득", "biz_sale": "영업양도", "biz_buy": "영업양수"}
_CORRECTED = re.compile(r"\[(기재정정|첨부정정)\]")
_SUBSIDIARY = re.compile(r"\((자회사|종속회사)의\s*주요경영사항\)")


def _title_core(title):
    """배지([기재정정]·[첨부추가]…)·공백·가운뎃점을 뗀 제목."""
    t = re.sub(r"\[[^\]]*\]", "", title or "")
    return re.sub(r"[\s\xa0　ㆍ·]", "", t)


def classify(title):
    """공시 제목 → 이벤트 type, 해당 없으면 None."""
    core = _title_core(title)
    for etype, needle in TYPES:
        if needle in core:
            return etype
    return None


def title_flags(title):
    t = title or ""
    return {"corrected": bool(_CORRECTED.search(t)), "subsidiary": bool(_SUBSIDIARY.search(t))}


# ── 본문 평탄화 ────────────────────────────────────────────────────────────
_CORR_HEAD = ("정정항목", "정정전", "정정후")


def _clean(c):
    return _WS.sub(" ", _html.unescape(c or "")).strip()


def _put(d, key, val):
    """같은 라벨이 다시 나오면 ' #2' 접미로 둘 다 남긴다(원문 보존)."""
    k, i = key, 1
    while k in d:
        i += 1
        k = "%s #%d" % (key, i)
    d[k] = val


def flatten(html):
    """본문 표 → (kv{원문 라벨: 값}, correction{정정항목: {before, after}}, 종속회사명|None, 표 수).

    행 규칙(거래소 xforms 격자 전개 결과 기준):
      · `정정항목|정정전|정정후` 머리 뒤의 행은 정정 표 — (항목, 정정전, 정정후)
      · `종속회사인 | X | 의 주요경영사항 신고` → kv['종속회사인'] = X
      · 네 칸이 서로 다르면 (라벨, 값, 라벨, 값) — '종속회사명 | X | 영문 | Y'
      · 그 밖은 마지막 칸이 값, 앞의 서로 다른 칸들이 라벨(rowspan 부모 + 세부항목). '※ 관련공시' 는 10항 rowspan 에
        끼어 있어도 제 라벨로 둔다.
    """
    kv, corr, sub_name = {}, {}, None
    tables = parse_tables(html)
    for t in tables:
        rows = ([list(t["cols"])] if t.get("cols") else []) + [list(r) for r in t["rows"]]
        mode = "kv"
        for r in rows:
            cells = [_clean(c) for c in r]
            if not any(cells):
                continue
            if tuple(re.sub(r"\s", "", c) for c in cells[:3]) == _CORR_HEAD:
                mode = "corr"
                continue
            if mode == "corr":
                if len(cells) >= 3:
                    _put(corr, cells[0], {"before": cells[1], "after": cells[-1]})
                    continue
                mode = "kv"                                   # 3열 미만 — 정정 표가 끝났다
            if len(cells) >= 3 and cells[0].endswith("회사인") and "주요경영사항" in cells[-1]:
                _put(kv, cells[0], cells[1])
                sub_name = sub_name or cells[1]
                continue
            if len(cells) == 4 and all(cells) and cells[0] != cells[1] and cells[1] != cells[2] and cells[2] != cells[3]:
                _put(kv, cells[0], cells[1])
                _put(kv, cells[0] + " " + cells[2], cells[3])
                continue
            if len(cells) < 2:
                continue
            val = cells[-1]
            labels = list(dict.fromkeys(c for c in cells[:-1] if c and c != val))
            if not labels:
                continue
            if any(lab.startswith("※") for lab in labels):
                labels = [lab for lab in labels if lab.startswith("※")]
            _put(kv, " ".join(labels), val)
    return kv, corr, sub_name, len(tables)


def _body_text(html):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html or "")
    t = re.sub(r"(?i)<br\s*/?>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return _WS.sub(" ", _html.unescape(t)).strip()


# N만톤 · N천톤 · N톤/년 · capa/Capa/CAPA — 추출만 한다(수치 해석 없음)
_CAPA = re.compile(r"\d[\d,.]*\s*(?:만\s*톤|천\s*톤|톤\s*/\s*년)|capa|Capa|CAPA")


def capa_text(text):
    """본문 어디든 캐파 표현이 있으면 그 주변 40자, 없으면 None."""
    m = _CAPA.search(text or "")
    if not m:
        return None
    s, e = max(0, m.start() - 40), min(len(text), m.end() + 40)
    return text[s:e].strip()


# ── 라벨 → 정규화 필드 ─────────────────────────────────────────────────────
FIELDS = ("amount_krw", "pct", "purpose", "reason", "scope", "period_start", "period_end",
          "halt_date", "restart_date", "decided", "capa_text")

# (field, 적용 type 들 | '*', 정규화 라벨에 전부 들어야 할 낱말, 들어 있으면 안 될 낱말) — 위에서부터 첫 적중.
# 유형자산·영업양수도 서식의 라벨은 실측 fixture 가 없어 거래소 서식명 기준 후보만 둔다 — 못 찾으면 null.
_FIELD_RULES = [
    ("amount_krw", ("invest",), ("투자금액",), ()),
    ("amount_krw", ("halt", "restart"), ("분야의매출액",), ("최근",)),
    ("amount_krw", ("suspend",), ("영업정지금액",), ()),
    ("amount_krw", ("asset_sale", "biz_sale"), ("양도금액",), ()),
    ("amount_krw", ("asset_sale", "biz_sale"), ("양도가액",), ()),
    ("amount_krw", ("asset_buy",), ("취득금액",), ()),
    ("amount_krw", ("asset_buy",), ("취득가액",), ()),
    ("amount_krw", ("biz_buy",), ("양수금액",), ()),
    ("amount_krw", ("biz_buy",), ("양수가액",), ()),
    ("pct", ("invest",), ("자기자본대비",), ()),
    ("pct", ("halt", "restart", "suspend", "biz_sale", "biz_buy"), ("매출액대비",), ()),
    ("pct", ("asset_sale", "asset_buy"), ("자산총액대비",), ()),
    ("pct", "*", ("자기자본대비",), ()),
    ("pct", "*", ("매출액대비",), ()),
    ("pct", "*", ("자산총액대비",), ()),
    ("purpose", ("invest",), ("투자목적",), ()),
    ("purpose", ("halt",), ("생산중단내용",), ()),
    ("purpose", ("restart",), ("생산재개내용",), ()),
    ("purpose", ("suspend",), ("영업정지내용",), ()),
    ("purpose", ("asset_sale", "biz_sale"), ("양도목적",), ()),
    ("purpose", ("asset_buy",), ("취득목적",), ()),
    ("purpose", ("biz_buy",), ("양수목적",), ()),
    ("reason", ("halt",), ("생산중단사유",), ()),
    ("reason", ("restart",), ("생산재개사유",), ()),
    ("reason", ("suspend",), ("영업정지사유",), ()),
    ("reason", "*", ("사유",), ("정정",)),
    ("scope", ("halt",), ("생산중단분야",), ()),
    ("scope", ("restart",), ("생산재개분야",), ()),
    ("scope", ("suspend",), ("영업정지분야",), ()),
    ("scope", ("invest",), ("투자대상",), ()),
    ("scope", ("asset_sale", "asset_buy"), ("자산명",), ()),
    ("scope", ("asset_sale", "asset_buy"), ("자산구분",), ()),
    ("scope", ("biz_sale",), ("양도대상",), ()),
    ("scope", ("biz_buy",), ("양수대상",), ()),
    ("period_start", ("invest",), ("투자기간시작",), ()),
    ("period_start", "*", ("시작일",), ()),
    ("period_end", ("invest",), ("투자기간종료",), ()),
    ("period_end", "*", ("종료일",), ()),
    ("halt_date", ("halt", "restart"), ("생산중단일자",), ()),
    ("halt_date", ("suspend",), ("영업정지일자",), ()),
    ("restart_date", ("halt", "restart"), ("생산재개예정일자",), ()),
    ("restart_date", ("halt", "restart"), ("생산재개일자",), ()),
    ("decided", "*", ("이사회결의일",), ()),
]
_DATE = re.compile(r"(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})")


def _norm(label):
    """라벨 정규화 — 번호('2. ')·머리 '-'·공백·가운뎃점 제거. '2. 투자내역 - 투자금액(원)' → '투자내역투자금액(원)'."""
    return re.sub(r"^\s*\d+\.\s*|^\s*-\s*|[\s\xa0　ㆍ·]|\s-\s", "", label or "")


def _find(kv, needles, exclude=()):
    """needle 을 전부 품고 exclude 를 하나도 안 품은 정규화 라벨 중 **가장 짧은** 라벨의 값(kship_contracts._find)."""
    hits = []
    for i, (k, v) in enumerate(kv.items()):
        nk = _norm(k)
        if all(n in nk for n in needles) and not any(x in nk for x in exclude):
            hits.append((len(nk), i, v))
    return min(hits)[2] if hits else None


def _date(s):
    m = _DATE.search(s or "")
    return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))) if m else None


def _period(s):
    """'2021-05-20 ~ 2027-12-31' → (시작, 종료). 물결이 없으면 (None, None)."""
    parts = re.split(r"[~∼〜]", s or "")
    if len(parts) >= 2:
        return _date(parts[0]), _date(parts[1])
    return None, None


def _won(s):
    v = to_float(s)
    if v is None:
        return None
    return int(v) if float(v).is_integer() else v


def _text(s):
    s = _WS.sub(" ", s or "").strip()
    return None if s in ("", "-", "—", "–", "해당없음", "해당 없음") else s


_CONV = {"amount_krw": _won, "pct": to_float, "period_start": _date, "period_end": _date,
         "halt_date": _date, "restart_date": _date, "decided": _date}


def _conv(field, raw):
    return _CONV.get(field, _text)(raw)


def _rules_for(etype):
    return [r for r in _FIELD_RULES if r[1] == "*" or etype in r[1]]


def fields_from_kv(kv, etype):
    """kv → 정규화 필드. 라벨을 찾은 첫 규칙이 이긴다(값이 '-' 라 null 이어도 다음 규칙으로 넘어가지 않는다)."""
    out = dict.fromkeys(FIELDS)
    hit = set()
    for field, _types, needles, exclude in _rules_for(etype):
        if field in hit:
            continue
        raw = _find(kv, needles, exclude)
        if raw is not None:
            hit.add(field)
            out[field] = _conv(field, raw)
    return out


def apply_correction(fields, corr, etype):
    """정정 표의 **정정후** 값을 fields 에 덮어쓴다. 본표도 정정후 값이지만 본표가 없거나 라벨이 다른 문서를 대비한다.
    '4. 투자기간' 한 줄('A ~ B')은 시작·종료로 가른다."""
    rules = _rules_for(etype)
    for item, ba in corr.items():
        nk = _norm(item)
        after = ba.get("after") or ""
        if "투자기간" in nk and "시작" not in nk and "종료" not in nk:
            s, e = _period(after)
            if s or e or _text(after) is None:
                fields["period_start"], fields["period_end"] = s, e
                continue
        for field, _types, needles, exclude in rules:
            if all(n in nk for n in needles) and not any(x in nk for x in exclude):
                fields[field] = _conv(field, after)
                break
    return fields


def _filed(rcp):
    return "%s-%s-%s" % (rcp[:4], rcp[4:6], rcp[6:8]) if re.match(r"^\d{14}$", rcp or "") else None


def parse_event(html, rcp, title, stock=None):
    """본문 HTML → 이벤트 레코드. 원문 라벨은 kv 에 전부, 정규화 값은 fields 에(못 읽으면 null)."""
    kv, corr, sub_name, n_tables = flatten(html)
    etype = classify(title)
    fl = title_flags(title)
    fields = fields_from_kv(kv, etype)
    if corr:
        apply_correction(fields, corr, etype)
    fields["capa_text"] = capa_text(_body_text(html))
    if not sub_name and fl["subsidiary"]:
        sub_name = _text(_find(kv, ("종속회사명",)) or _find(kv, ("자회사명",)))
    corrected = fl["corrected"] or bool(corr)
    return {
        "rcp": rcp, "stock": stock, "filed": _filed(rcp), "title": title, "type": etype,
        "corrected": corrected, "subsidiary": fl["subsidiary"] or bool(sub_name), "subsidiary_name": sub_name,
        "kv": kv, "fields": fields, "n_tables": n_tables,
        "correction": corr or None,
        "correction_reason": _text(_find(kv, ("정정사유",))) if corrected else None,
        "corrects_filed": _date(_find(kv, ("정정관련공시서류제출일",))) if corrected else None,
    }


# ── 정정 덮어쓰기(이력 보존) ────────────────────────────────────────────────

def _norm_scope(s):
    return re.sub(r"[\s\xa0　]|\(주\)|㈜|주식회사", "", s or "").lower()


def _skey(e):
    f = e.get("fields") or {}
    anchor = f.get("scope") or f.get("purpose")
    when = f.get("period_start") or f.get("decided")
    if not anchor or not when:
        return None
    return (e.get("type"), _norm_scope(anchor), when)


def supersede(events):
    """접수번호 순으로 보며 뒤 접수가 앞을 덮는다. 모든 이벤트를 돌려주되 `supersedes`(덮은 앞 rcp)·`superseded_by`(덮은 뒤 rcp)
    를 적는다 — 덮인 것도 원장에 남는다. 연결 순서: ① 정정 공시의 '정정관련 공시서류제출일' == 앞 공시 filed(같은 type; 여럿이면
    scope 가 같은 것, 그래도 모호하면 포기) ② (type, scope|purpose 정규화, period_start|decided) 키."""
    out = [dict(e) for e in sorted(events, key=lambda e: e.get("rcp") or "")]
    by_key, by_filed = {}, {}
    for e in out:
        e.setdefault("supersedes", None)
        e.setdefault("superseded_by", None)
        prev = None
        cf = e.get("corrects_filed")
        if e.get("corrected") and cf:
            cands = [c for c in by_filed.get((e.get("type"), cf), []) if c is not e]
            if len(cands) > 1:
                sk = _skey(e)
                cands = [c for c in cands if sk and _skey(c) and _skey(c)[1] == sk[1]]
            if len(cands) == 1:
                prev = cands[0]
        k = _skey(e)
        if prev is None and k is not None:
            prev = by_key.get(k)
        if prev is not None and prev is not e:
            e["supersedes"] = prev["rcp"]
            prev["superseded_by"] = e["rcp"]
            pk = _skey(prev)
            if pk is not None:
                by_key[pk] = e                        # 옛 키로 오는 다음 정정도 최신 판에 붙는다
        if k is not None:
            by_key[k] = e
        if e.get("filed"):
            by_filed.setdefault((e.get("type"), e["filed"]), []).append(e)
    return out


def active_events(events):
    return [e for e in events if not e.get("superseded_by")]


# ── 수집 ────────────────────────────────────────────────────────────────────

def _d(s):
    return datetime.datetime.strptime(s, "%Y%m%d").date()


def _s(d):
    return d.strftime("%Y%m%d")


def _today():
    return _s(datetime.date.today())


def year_windows(since, until):
    """[since, until] 을 연도 단위 창으로 — [('20240101','20241231'), ('20250101','20251231'), ('20260101','20261017')]."""
    s, u = _d(since), _d(until)
    out = []
    while s <= u:
        e = min(datetime.date(s.year, 12, 31), u)
        out.append((_s(s), _s(e)))
        s = e + datetime.timedelta(days=1)
    return out


def _search_window(stock, start, end, errors, depth=0):
    """한 창의 I001 검색. 실패하면 errors 에 적고 None. MAX_RESULTS 건이면 잘린 것이라 반으로 쪼개 다시 묻는다."""
    try:
        rows = search_reports(stock, start, end, "I001")
    except Exception as e:                                    # 네트워크·파싱 — 창 단위로 fail-closed
        errors.append({"stage": "search", "window": [start, end], "error": "%s: %s" % (type(e).__name__, e)})
        return None
    if len(rows) < MAX_RESULTS:
        return rows
    d0, d1 = _d(start), _d(end)
    if (d1 - d0).days < MIN_WINDOW_DAYS or depth >= 6:
        errors.append({"stage": "search", "window": [start, end],
                       "error": "결과 %d건 — maxResults 상한에서 잘렸을 수 있음" % len(rows)})
        return rows
    mid = d0 + datetime.timedelta(days=(d1 - d0).days // 2)
    a = _search_window(stock, start, _s(mid), errors, depth + 1)
    b = _search_window(stock, _s(mid + datetime.timedelta(days=1)), end, errors, depth + 1)
    if a is None or b is None:
        return None
    return a + b


def _meta_name(rcp):
    return "ev_%s.meta.json" % rcp


def _fetch_body(rcp):
    nodes = toc(rcp)
    if not nodes:
        raise RuntimeError("목차 없음")
    html = fetch_section(nodes[0])                             # 수시공시는 '본문' 노드 하나
    if not html or "<table" not in html.lower():
        raise RuntimeError("본문에 표 없음")                     # 실패는 캐시하지 않는다
    return html


def _merge_and_write(stock, name, events, errors, since, until, replace=False):
    old = load_asset("events/%s.json" % stock, default={})
    by = {} if replace else {e["rcp"]: e for e in (old.get("events") or []) if e.get("rcp")}
    for e in events:
        by[e["rcp"]] = e                                       # 새 파싱이 옛 레코드를 덮는다 — 파서가 자라면 재수집 없이 갱신
    allev = supersede(list(by.values()))
    data = {"stock": stock, "name": name, "since": since, "until": until, "n": len(allev),
            "n_active": len(active_events(allev)), "events": allev, "errors": errors}
    write_asset("events/%s.json" % stock, data)
    return data


def collect(stock, name, since="20240101", until=None, force=False, log=None):
    """I001 검색(연도 창) → classify 된 것만 본문 수집(캐시 있으면 요청 0) → 파싱 → events/<stock>.json 병합 저장.
    반환 {'ok','stock','n','fetched','errors','written'} — 예외는 전파하지 않는다."""
    until = until or _today()
    log = log or sys.stderr
    errors, found, seen = [], [], set()
    search_failed = False
    for start, end in year_windows(since, until):
        rows = _search_window(stock, start, end, errors)
        if rows is None:
            search_failed = True
            continue
        for rcp, title in rows:
            if rcp in seen:
                continue
            seen.add(rcp)
            if classify(title):
                found.append((rcp, title))
    events, fetched = [], 0
    for rcp, title in sorted(found):
        cname = "ev_%s.html" % rcp
        html = None if force else read_cache(stock, cname)
        if html is None:
            try:
                html = _fetch_body(rcp)
            except Exception as e:
                errors.append({"stage": "fetch", "rcp": rcp, "title": title, "error": "%s: %s" % (type(e).__name__, e)})
                continue
            write_cache(stock, cname, html)
            write_cache(stock, _meta_name(rcp), json.dumps({"rcp": rcp, "title": title, "stock": stock}, ensure_ascii=False))
            fetched += 1
        elif read_cache(stock, _meta_name(rcp)) is None:
            write_cache(stock, _meta_name(rcp), json.dumps({"rcp": rcp, "title": title, "stock": stock}, ensure_ascii=False))
        try:
            events.append(parse_event(html, rcp, title, stock))
        except Exception as e:
            errors.append({"stage": "parse", "rcp": rcp, "title": title, "error": "%s: %s" % (type(e).__name__, e)})
    if search_failed:
        log.write("[kcap_events] %s 검색 창 실패 — 산출 파일을 건드리지 않음(%d건 파싱은 버림, 캐시 %d건 보존)\n"
                  % (stock, len(events), fetched))
        return {"ok": False, "stock": stock, "n": len(events), "fetched": fetched, "errors": errors, "written": False}
    data = _merge_and_write(stock, name, events, errors, since, until)
    log.write("[kcap_events] %s %s 후보 %d · 파싱 %d · 새 수집 %d · 원장 %d(유효 %d) · 오류 %d\n"
              % (stock, name, len(found), len(events), fetched, data["n"], data["n_active"], len(errors)))
    return {"ok": not errors, "stock": stock, "n": data["n"], "fetched": fetched, "errors": errors, "written": True}


_TITLE_TAG = re.compile(r"<title>([^<]*)</title>", re.I)


def _title_from_html(html):
    """캐시 본문의 <title> '대한유화/생산중단/(2026.10.06)생산중단' → '생산중단'(배지는 들어 있지 않다 — corrected 는 정정 표로 판정)."""
    m = _TITLE_TAG.search(html or "")
    if not m:
        return ""
    last = _html.unescape(m.group(1)).split("/")[-1].strip()
    return re.sub(r"^\(\d{4}\.\d{2}\.\d{2}\)", "", last).strip()


def rebuild(stock, name, log=None):
    """캐시만으로 재파싱(요청 0). 캐시가 비었는데 기존 원장이 있으면 덮지 않는다."""
    log = log or sys.stderr
    folder = os.path.join(CACHE, stock)
    errors, events = [], []
    files = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    for f in files:
        m = re.match(r"^ev_(\d{14})\.html$", f)
        if not m:
            continue
        rcp = m.group(1)
        html = read_cache(stock, f)
        raw = read_cache(stock, _meta_name(rcp))
        try:
            meta = json.loads(raw) if raw else {}
        except ValueError:
            meta = {}
        title = meta.get("title") or _title_from_html(html)
        try:
            events.append(parse_event(html, rcp, title, stock))
        except Exception as e:
            errors.append({"stage": "parse", "rcp": rcp, "title": title, "error": "%s: %s" % (type(e).__name__, e)})
    if not events:
        old = load_asset("events/%s.json" % stock, default={})
        if old.get("events"):
            errors.append({"stage": "rebuild", "error": "캐시에 이벤트가 없어 기존 원장(%d건)을 유지" % len(old["events"])})
            return {"ok": False, "stock": stock, "n": len(old["events"]), "fetched": 0, "errors": errors, "written": False}
    old = load_asset("events/%s.json" % stock, default={})
    data = _merge_and_write(stock, name, events, errors, old.get("since") or "", old.get("until") or "", replace=True)
    log.write("[kcap_events] %s %s 캐시 재파싱 %d · 원장 %d(유효 %d) · 오류 %d\n"
              % (stock, name, len(events), data["n"], data["n_active"], len(errors)))
    return {"ok": not errors, "stock": stock, "n": data["n"], "fetched": 0, "errors": errors, "written": True}


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description="캐파 변동 이벤트 원장 — 거래소 수시공시 수집·파싱")
    ap.add_argument("--stocks", default="", help="종목코드, 쉼표 구분")
    ap.add_argument("--since", default="20240101")
    ap.add_argument("--until", default=None)
    ap.add_argument("--force", action="store_true", help="캐시가 있어도 다시 받는다")
    ap.add_argument("--rebuild", action="store_true", help="캐시만으로 재파싱(요청 0)")
    ap.add_argument("--fixture", default="", help="본문 HTML 파일 하나를 파싱해 JSON 출력(요청 0)")
    ap.add_argument("--title", default="")
    ap.add_argument("--rcp", default="")
    a = ap.parse_args(argv)
    if a.fixture:
        with open(a.fixture, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r"(\d{14})", os.path.basename(a.fixture))
        rcp = a.rcp or (m.group(1) if m else "")
        rec = parse_event(html, rcp, a.title or _title_from_html(html))
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        return 0
    stocks = [s for s in a.stocks.split(",") if s]
    if not stocks:
        ap.error("--stocks 가 필요하다")
    names = {r["stock"]: r["name"] for r in load_asset("universe.json", default={"rows": []}).get("rows", [])}
    bad = 0
    for st in stocks:
        if a.rebuild:
            res = rebuild(st, names.get(st, st))
        else:
            res = collect(st, names.get(st, st), since=a.since, until=a.until, force=a.force)
        print("%s %s ok=%s events=%s fetched=%s errors=%d written=%s"
              % (st, names.get(st, ""), res["ok"], res["n"], res["fetched"], len(res["errors"]), res["written"]))
        for err in res["errors"]:
            print("   ", json.dumps(err, ensure_ascii=False))
        bad += 0 if res["ok"] else 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
