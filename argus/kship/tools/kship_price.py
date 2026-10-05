#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_price — 모집단 57사(회사 폴더 56 + 지주 HD한국조선해양 009540)의 시세를 모아 prices.json 을 만든다.

원천 둘, 전부 키 없음.
  ① aikstockdata.com 공개 JSON(`/data/public/s/<code>.json`) — 상장주식수·시가총액·DART 기반 PER(TTM)·PBR·최신 정기보고서
     주요계정. **출처 표기·비영리** 조건이라 응답의 license·citation 문구를 그대로 보존하고 페이지 각주가 이것을 인용한다.
  ② 네이버 금융 일봉(`fchart.stock.naver.com/siseJson.nhn`, 정규장·수정주가) — **종가 정본**과 5년 분기 시세(`history_quarterly`).
     한 요청에 5년치(약 1,300행)가 오므로 종목당 1요청이다(2026-10-05 실측 57/57, 49초).
종목마다 0.5초 간격으로 읽고, 실패한 종목은 rows 에 `error` 로 남긴다(전체를 실패시키지 않는다).

## 종가 정본 규칙 (2026-09-30 오너 결정 + 2026-10-05 검증, prices.json `close_rule` 에도 같은 문장)
  1. `close` = **네이버 정규장 종가(KRX, 수정주가)**, `close_source = naver_regular_close`. 시총 = close × 상장주식수.
  2. `as_of` = 네이버 일봉의 **최신 거래일**. aik 는 T+1 저녁에 전 거래일을 싣고 주말·휴일에는 갱신하지 않아 월요일 러너(10:40 KST)
     기준 목요일 종가가 온다(10/4 실측: aik as_of 10/1, 네이버 10/2). 네이버가 더 최신이면 `as_of` 를 그 날로 전진하고
     `as_of_source = naver_latest`, aik 기준일·종가·시총·시고저·거래량은 `aik_as_of`·`aik_close`·`market_cap_krw_aik`·`aik_quote` 에 보존.
  3. aik `close` 는 대조용(`naver_check`)으로만 쓴다. 실측: 같은 기준일에 시가·저가·거래량은 네이버와 같은데 고가·종가가 다른 종목이 있다
     (현대리바트 10/1 aik 고가 5,600·종가 5,560 vs 네이버 5,800·5,750, 거래량 6,396 동일) — 장 마감 전 스냅숏으로 보이며 '확정 종가'
     표기와 어긋난다(원인은 미확인, 숫자만 기록).
  4. 토스 일봉은 쓰지 않는다. 2025-03 넥스트레이드(NXT) 개장 뒤 토스 일봉은 KRX+NXT 합산(거래량 1.3~3.0배, 종가·고저 상이 —
     삼성重 2025-03-24·KCC 2025-03-17 부터)이고, 거래정지일을 거래일처럼 넣는다(삼영이엔씨 764원 × 62일). 2022~2024 는 네이버와 동일.
  5. 네이버 일봉의 **무거래일**(거래량 0 — 시고저 0 자리표시 행, 또는 전일 종가 복사 행)은 분기 집계에서 뺀다(`history_meta.no_trade_dropped`).
     거래정지 분기는 비게 두고(가짜 평균가를 만들지 않음), 마지막 거래일이 분기말 전이면 그 값이 기말이다.

`history_quarterly` = 분기 기말/고/저/평균 종가(subQ 의 PER 4종·TP 밴드·xlsx `1b. 종가`·레퍼런스 패치 시가총액 4계정용). 창은 5년 전이 속한
분기의 첫날부터(분기 경계 정렬). 네이버를 받지 못한 행은 기존 prices.json 의 이력을 이어 붙인다(`history_meta.carried_from`, --no-carry 로 끔).
universe.json 의 `listed`(현 시장 상장·이전일)가 이력 안에 있으면 그 전 분기 목록을 `history_meta.pre_listed_quarters` 에 적는다
(삼미금속 코넥스 구간 2023Q2~2025Q4 · SK오션플랜트 코스닥 구간) — 자르지 않고 표기만.

    python3 kship_price.py                       # 57사 시세 + 5년 분기 시세 + 네이버 종가 규칙
    python3 kship_price.py --no-history          # aik + 네이버 2주 창만(이력은 기존 파일에서 이어 붙임)
    python3 kship_price.py --no-naver            # 네이버 생략 — close 는 aik 값(close_source=aik_close)
    python3 kship_price.py --only 010140,075580
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from kship_lib import ASSETS, KSHIP, load_asset, write_asset
from kship_universe import load as load_universe

AIK = "https://aikstockdata.com/data/public/s/%s.json"
# 네이버 일봉(정규장·수정주가) — 응답은 JSON 이 아니라 JS 배열 리터럴(작은따옴표 헤더)이다.
NAVER_DAILY = "https://fchart.stock.naver.com/siseJson.nhn?symbol=%s&requestType=1&startTime=%s&endTime=%s&timeframe=day"
NAVER_LOOKBACK_DAYS = 14                              # --no-history 때 기준일 앞 2주(연휴 포함)만 받는다
OUT = "prices.json"
HOLDING = "009540"                                    # 폴더 없는 지주 — 스펙 1 모집단 규약
UA = "phalanx-argus-kship/0.1 (non-commercial, source attribution)"
HISTORY_YEARS = 5
HISTORY_SOURCE = "네이버 금융 일봉(fchart siseJson, KRX 정규장·수정주가)"

CLOSE_RULE = {
    "close": "네이버 정규장 종가(KRX, 수정주가) — close_source=naver_regular_close. 네이버가 없으면 aik close(close_source=aik_close(…))",
    "as_of": "네이버 일봉 최신 거래일(YYYYMMDD). aik 기준일보다 최신이면 전진(as_of_source=naver_latest), 같으면 aik_same_day. "
             "aik 는 T+1 저녁 갱신·주말 미갱신이라 월요일 오전에는 목요일 종가다(2026-10-04 실측 aik 10/1 vs 네이버 10/2)",
    "market_cap_krw": "close × shares_outstanding(aik 상장주식수). aik 원값은 market_cap_krw_aik",
    "aik": "대조용(naver_check). 같은 기준일에 시가·저가·거래량은 네이버와 같고 고가·종가가 다른 종목이 있다(현대리바트 2026-10-01 aik 5,600/5,560 "
           "vs 네이버 5,800/5,750, 거래량 6,396 동일) — '확정 종가' 표기와 어긋나며 원인은 미확인. aik 기준일·종가·시고저·거래량은 aik_as_of·aik_close·aik_quote 에 보존",
    "history_quarterly": "네이버 일봉 5년(분기 경계 정렬) 집계. 무거래일(거래량 0)은 뺀다. 토스 일봉은 2025-03 NXT 개장 뒤 KRX+NXT 합산"
                         "(거래량 1.3~3.0배·종가 상이)이고 거래정지일을 거래일처럼 넣어 쓰지 않는다(2026-10-05 검증, 2022~2024 는 네이버와 동일)",
    "decided": "2026-09-30 오너(정본=네이버 정규장 종가) · 2026-10-05 V2 검증(as_of 전진 · 토스 제거 · 무거래일 제외)",
}


# ── 모집단 ──────────────────────────────────────────────────

def roster():
    """universe.json(41) ∪ 회사 폴더(56, 승격 16 포함) ∪ 009540 → {stock: {name, market, role, listed, src}}."""
    out = {}
    for r in load_universe():
        out[r["stock"]] = {"name": r["name"], "market": r.get("market"), "role": r.get("role"),
                           "listed": r.get("listed"), "src": "universe"}
    for d in sorted(os.listdir(KSHIP)):
        if not (len(d) == 6 and d.isdigit()) or not os.path.isdir(os.path.join(KSHIP, d)):
            continue
        if d in out:
            out[d]["src"] = "universe+folder"
            continue
        name = None
        p = os.path.join(KSHIP, d, "index.html")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                m = re.search(r"<title>(.*?)</title>", f.read(4000))
            if m:
                name = m.group(1).split(" — ")[0].strip()
        out[d] = {"name": name, "market": None, "role": "equip", "listed": None, "src": "folder"}
    if HOLDING not in out:
        out[HOLDING] = {"name": "HD한국조선해양", "market": "유가", "role": "holding", "listed": None, "src": "spec"}
    return dict(sorted(out.items()))


# ── aikstockdata ────────────────────────────────────────────

def _get(url, tries=2, timeout=30):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        if i < tries - 1:
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("GET 실패 %s: %s" % (url, last))


def fetch_aik(stock):
    return json.loads(_get(AIK % stock).decode("utf-8"))


def _fin_block(f):
    """financials → {period, basis, revenue/operating_income/net_income 당기·전년·YoY}."""
    if not isinstance(f, dict):
        return None
    out = {"period": f.get("period"), "period_ko": f.get("period_ko"), "basis": f.get("basis"),
           "unit": f.get("unit"), "source": f.get("source")}
    for k in ("revenue", "operating_income", "net_income"):
        v = f.get(k) or {}
        out[k] = v.get("current")
        out[k + "_prior_year"] = v.get("prior_year")
        out[k + "_yoy_pct"] = v.get("yoy_pct")
    return out


def row_of(d, meta):
    """aikstockdata 응답 → prices.json 한 행(스펙 2-3). 시세가 없으면 quote_absent 를 그대로 둔다."""
    q = d.get("quote") or {}
    v = d.get("valuation") or {}
    return {
        "name": d.get("name_ko") or meta.get("name"),
        "market": d.get("market") or meta.get("market"),
        "role": meta.get("role"),
        "close": q.get("close"),
        "as_of": q.get("as_of") or d.get("as_of"),
        "open": q.get("open"), "high": q.get("high"), "low": q.get("low"),
        "volume": q.get("volume"),
        "shares_outstanding": q.get("shares_outstanding"),
        "market_cap_krw": q.get("market_cap_krw"),
        "trading_status": q.get("trading_status"),
        "quote_absent": d.get("quote_absent"),
        "pe_ttm": v.get("pe_ttm"),
        "pb": v.get("pb"),
        "ttm_net_income_krw": v.get("ttm_net_income_krw"),
        "equity_krw": v.get("equity_krw"),
        "valuation_basis": v.get("basis"),
        "pe_note": v.get("pe_note"), "pb_note": v.get("pb_note"),
        "financials_ref": _fin_block(d.get("financials")),
        "snapshot_id": d.get("snapshot_id"),
        "generated_kst": d.get("generated_kst"),
        "page_url": d.get("page_url"),
    }


# ── 시세 이력(일봉 → 분기) ──────────────────────────────────

def quarter_of(date):
    return "%sQ%d" % (date[:4], (int(date[5:7]) - 1) // 3 + 1)


def quarter_start(q):
    """'2021Q3' → '2021-07-01'."""
    return "%s-%02d-01" % (q[:4], (int(q[5]) - 1) * 3 + 1)


def history_since(today, years=HISTORY_YEARS):
    """이력 창의 시작일 — `years`년 전이 속한 **분기의 첫날**. 날짜 그대로 자르면 첫 분기가 사흘짜리(2021Q3 3일)로
    남아 고/저/평균이 분기 전체를 대표하지 못하는데 days 만 보고는 상장 분기와 구별이 안 된다(검증에서 잡음)."""
    try:
        back = today.replace(year=today.year - years)                  # 달력 기준 N년 전(365일×N 은 윤일에 하루씩 밀린다)
    except ValueError:                                                 # 2/29 → 2/28
        back = today.replace(year=today.year - years, day=28)
    return quarter_start(quarter_of(back.isoformat()))


TRUNCATED_GRACE_DAYS = 10                              # 분기 첫 거래일 지연 허용(연초 1/2·추석 연휴 최대 +9일 실측)


def aggregate_candles(candles, today, years=HISTORY_YEARS):
    """일봉 [{timestamp, closePrice, highPrice, lowPrice}] → {'2024Q3': {close_end, high, low, avg, days, end_date, partial}}.

    최근 `years`년(분기 경계 정렬, history_since) 안의 분기만. 진행 중 분기(오늘이 분기말 전)는 partial.
    첫 거래일이 분기 시작 +10일보다 늦은 분기(상장·자료 시작·거래정지)는 `truncated: true` — 고/저/평균이 분기 전체를 덮지 않는다.
    값은 원 단위 정수(평균은 소수 1자리). 무거래일 제외는 호출자(naver_candles)가 한다."""
    since = history_since(today, years)
    groups = {}
    for c in candles:
        d = str(c.get("timestamp", ""))[:10]
        if len(d) != 10 or d < since:
            continue
        try:
            rec = (float(c["closePrice"]), float(c["highPrice"]), float(c["lowPrice"]))
        except (KeyError, TypeError, ValueError):
            continue
        groups.setdefault(quarter_of(d), {})[d] = rec
    cur_q = quarter_of(today.isoformat())
    out = {}
    for q in sorted(groups):
        g = groups[q]
        dates = sorted(g)
        closes = [g[d][0] for d in dates]
        out[q] = {"close_end": _int(g[dates[-1]][0]),
                  "high": _int(max(g[d][1] for d in dates)),
                  "low": _int(min(g[d][2] for d in dates)),
                  "avg": round(sum(closes) / len(closes), 1),
                  "days": len(dates), "end_date": dates[-1],
                  "partial": q == cur_q}
        qs = datetime.date.fromisoformat(quarter_start(q))
        if datetime.date.fromisoformat(dates[0]) > qs + datetime.timedelta(days=TRUNCATED_GRACE_DAYS):
            out[q]["truncated"] = True
            out[q]["start_date"] = dates[0]
    return out


def _int(x):
    return int(x) if float(x).is_integer() else x


# ── 네이버 일봉 ─────────────────────────────────────────────

def parse_naver_rows(text):
    """siseJson 응답 → [{date(YYYYMMDD), open, high, low, close, volume}] 날짜순.
    헤더 행(['날짜','시가','고가','저가','종가','거래량','외국인소진율'])은 작은따옴표라 JSON 이 아니다.
    무거래일은 두 모양으로 온다 — 시고저 0·거래량 0(거래정지, 종가는 전일 복사) 또는 시고저종 전부 전일 종가·거래량 0. 여기서는 거르지 않는다."""
    body = text.strip().replace("'", '"')
    rows = json.loads(body) if body else []
    out = []
    for r in rows[1:] if rows and isinstance(rows[0], list) and rows[0] and rows[0][0] == "날짜" else rows:
        if not (isinstance(r, list) and len(r) >= 5 and isinstance(r[0], str) and len(r[0]) == 8 and r[0].isdigit()):
            continue
        if not all(isinstance(x, (int, float)) for x in r[1:5]):
            continue
        out.append({"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4],
                    "volume": r[5] if len(r) > 5 and isinstance(r[5], (int, float)) else None})
    out.sort(key=lambda x: x["date"])
    return out


def parse_naver_daily(text):
    """siseJson 응답 → {YYYYMMDD: 종가}(무거래일 포함 — 그날의 종가는 전일 종가 복사이고 aik 도 같은 값을 싣는다)."""
    return {r["date"]: r["close"] for r in parse_naver_rows(text)}


def _yyyymmdd(d):
    return d.strftime("%Y%m%d") if isinstance(d, datetime.date) else str(d).replace("-", "")[:8]


def fetch_naver_daily(stock, as_of, lookback=NAVER_LOOKBACK_DAYS, end=None):
    """기준일(YYYYMMDD) 앞 lookback 일 ~ end(기본 기준일)의 네이버 일봉 종가 {YYYYMMDD: close}."""
    d = datetime.date(int(as_of[:4]), int(as_of[4:6]), int(as_of[6:]))
    start = (d - datetime.timedelta(days=lookback)).strftime("%Y%m%d")
    return parse_naver_daily(_get(NAVER_DAILY % (stock, start, _yyyymmdd(end) if end else as_of)).decode("utf-8"))


def fetch_naver_history(stock, today, years=HISTORY_YEARS):
    """5년(분기 경계 정렬) ~ 오늘의 네이버 일봉 행 — 한 요청(2026-10-05 실측 57/57, 종목당 ≤1,300행·75KB)."""
    start = _yyyymmdd(history_since(today, years))
    return parse_naver_rows(_get(NAVER_DAILY % (stock, start, _yyyymmdd(today))).decode("utf-8"))


def is_no_trade(r):
    """무거래일 — 거래량 0 또는 고가/저가 0(거래정지 자리표시 행). 거래량이 없는 응답(None)은 시고저로만 판정."""
    if r.get("volume") is not None and not r["volume"]:
        return True
    return not r.get("high") or not r.get("low")


def naver_candles(rows):
    """네이버 행 → aggregate_candles 입력. 무거래일을 뺀다(가짜 평균가·고저 방지). (candles, dropped_n)."""
    cands, dropped = [], 0
    for r in rows:
        if is_no_trade(r):
            dropped += 1
            continue
        d = r["date"]
        cands.append({"timestamp": "%s-%s-%s" % (d[:4], d[4:6], d[6:]), "closePrice": r["close"],
                      "highPrice": r["high"], "lowPrice": r["low"]})
    return cands, dropped


def history_from_rows(rows, today, listed=None, years=HISTORY_YEARS):
    """네이버 일봉 행 → (history_quarterly, history_meta). 행이 없으면 (None, meta[error])."""
    cands, dropped = naver_candles(rows)
    meta = {"source": HISTORY_SOURCE, "rows": len(rows), "no_trade_dropped": dropped,
            "from": rows[0]["date"] if rows else None, "to": rows[-1]["date"] if rows else None,
            "window_from": history_since(today, years)}
    if not cands:
        meta["error"] = "거래일 0건(전부 무거래)" if rows else "일봉 0건"
        return None, meta
    hist = aggregate_candles(cands, today, years)
    if listed and len(str(listed)) >= 10:
        lq = quarter_of(str(listed)[:10])
        pre = [q for q in hist if q < lq]
        if pre:
            meta["listed"] = str(listed)[:10]
            meta["pre_listed_quarters"] = pre
            meta["pre_listed_note"] = "universe `listed`(현 시장 상장·이전일) 전 구간 — 이전 시장(코넥스·코스닥 등) 시세, 자르지 않고 표기만"
    return hist, meta


# ── 종가 규칙 ───────────────────────────────────────────────

KST = datetime.timezone(datetime.timedelta(hours=9))
SESSION_SETTLED = datetime.time(15, 40)                # KRX 정규장 15:30 마감 + 여유 — 이 전에는 오늘 행을 종가로 쓰지 않는다


def include_today_closes(today, now=None):
    """오늘 날짜의 일봉 행을 종가로 인정할지 — 과거 날짜(--today)는 항상, 오늘은 KST 15:40 이후에만.
    러너는 10:40 KST(장중)에 돌므로 네이버가 진행 중인 날의 행을 싣더라도 그 값을 종가·기말로 쓰지 않는다(전 거래일 종가가 정본).
    2026-10-05(휴장) 09:41 KST 실측에서는 당일 행이 없었지만 장중 노출 여부는 확인하지 못해 가드를 둔다."""
    now = now or datetime.datetime.now(KST)
    if today < now.date():
        return True
    return now.time() >= SESSION_SETTLED


def drop_in_progress_day(rows, today, include_today):
    """today 보다 뒤의 행은 항상, today 행은 include_today 가 아니면 뺀다(이력·종가 규칙 둘 다 이 행을 쓴다)."""
    cut = _yyyymmdd(today)
    return [r for r in (rows or []) if r["date"] < cut or (include_today and r["date"] == cut)]


def naver_check_row(close, as_of, naver):
    """aik close vs 같은 기준일 네이버 종가. 기준일 행이 없으면 None(휴장·미제공)."""
    nv = (naver or {}).get(as_of)
    if nv is None or close is None or not close:
        return {"date": as_of, "aik": close, "naver_close": nv, "diff_pct": None,
                "note": "네이버 기준일 종가 없음" if nv is None else "aik close 없음"}
    return {"date": as_of, "aik": close, "naver_close": _int(nv), "diff_pct": round(100.0 * (close - nv) / nv, 3)}


def apply_close_rule(row, naver_rows, today):
    """종가 정본 규칙(모듈 머리말) 적용 — row 를 제자리에서 고치고 돌려준다.

    naver_rows: parse_naver_rows 결과(날짜순) 또는 None. 네이버 최신 거래일(≤ today)의 종가를 close 로, 그 날을 as_of 로.
    aik 기준일 종가와의 대조는 naver_check(같은 날), aik 원값은 aik_* 에 보존."""
    aik_as_of = row.get("as_of")
    by_date = {r["date"]: r for r in (naver_rows or [])}
    row["naver_check"] = naver_check_row(row.get("close"), aik_as_of, {d: r["close"] for d, r in by_date.items()}) \
        if aik_as_of and len(str(aik_as_of)) == 8 else {"date": aik_as_of, "aik": row.get("close"), "naver_close": None,
                                                        "diff_pct": None, "note": "aik 기준일 없음"}
    cutoff = _yyyymmdd(today)
    dates = sorted(d for d in by_date if d <= cutoff and (not aik_as_of or d >= str(aik_as_of)))
    if not dates or by_date[dates[-1]].get("close") in (None, 0):
        row["close_source"] = "aik_close(네이버 기준일 종가 없음)"
        row["as_of_source"] = "aik"
        return row
    latest = dates[-1]
    nr = by_date[latest]
    row["aik_as_of"] = aik_as_of
    row["aik_close"] = row.get("close")
    row["close"] = _int(nr["close"])
    row["close_source"] = "naver_regular_close"
    if row.get("shares_outstanding"):
        row["market_cap_krw_aik"] = row.get("market_cap_krw")
        row["market_cap_krw"] = int(round(row["close"] * row["shares_outstanding"]))
    if latest == str(aik_as_of):
        row["as_of_source"] = "aik_same_day"
    else:
        advanced = sum(1 for d in dates if d > str(aik_as_of)) if aik_as_of else None
        row["aik_quote"] = {"as_of": aik_as_of, "close": row["aik_close"], "open": row.get("open"), "high": row.get("high"),
                            "low": row.get("low"), "volume": row.get("volume"), "trading_status": row.get("trading_status")}
        row["as_of"] = latest
        row["as_of_source"] = "naver_latest(aik 기준일 %s 보다 %s거래일 최신)" % (aik_as_of, advanced if advanced is not None else "?")
        row["open"], row["high"], row["low"], row["volume"] = (_int(nr["open"]) if nr.get("open") else None,
                                                               _int(nr["high"]) if nr.get("high") else None,
                                                               _int(nr["low"]) if nr.get("low") else None, nr.get("volume"))
        if nr.get("volume") is not None:
            row["trading_status"] = "no_trade" if is_no_trade(nr) else "traded"
    return row


def naver_summary(rows):
    """행별 naver_check → 상단 요약(대조 수·일치 수·|차이|>1% 수·최대 |차이|와 그 종목·as_of 전진 수)."""
    checks = [(s, r["naver_check"]) for s, r in rows.items() if isinstance(r.get("naver_check"), dict) and r["naver_check"].get("diff_pct") is not None]
    out = {"source": "fchart.stock.naver.com siseJson 일봉 종가(정규장) — aik 기준일 같은 날 대조",
           "checked_n": len(checks), "equal_n": sum(1 for _, c in checks if c["diff_pct"] == 0),
           "abs_gt_1pct_n": sum(1 for _, c in checks if abs(c["diff_pct"]) > 1.0),
           "max_abs": None,
           "close_source_n": {}, "as_of_advanced_n": 0, "as_of_n": {},
           "note": "close 는 네이버 정규장 종가(close_source), aik 원값은 aik_close — 차이는 행마다 naver_check. aik `close` 는 금융위 T+1 "
                   "확정 종가로 표기되지만 같은 기준일에 시가·저가·거래량은 같고 고가·종가가 다른 종목이 있다(2026-10-01 현대리바트 5,560 vs 5,750). "
                   "어느 쪽이 '확정'인지 이 파일은 판정하지 않고 네이버를 정본으로 쓴다(close_rule)."}
    for s, r in rows.items():
        if "error" in r:
            continue
        cs = r.get("close_source") or "?"
        out["close_source_n"][cs] = out["close_source_n"].get(cs, 0) + 1
        if str(r.get("as_of_source") or "").startswith("naver_latest"):
            out["as_of_advanced_n"] += 1
        ao = str(r.get("as_of"))
        out["as_of_n"][ao] = out["as_of_n"].get(ao, 0) + 1
    if checks:
        s, c = max(checks, key=lambda x: abs(x[1]["diff_pct"]))
        out["max_abs"] = {"stock": s, "diff_pct": c["diff_pct"], "aik": c.get("aik"), "naver_close": c.get("naver_close")}
    return out


# ── 조립 ────────────────────────────────────────────────────

def collect(codes, meta, today, with_history=True, sleep=0.5, log=print, naver=True, include_today=None):
    rows, license_, citation = {}, None, None
    hist_ok = hist_fail = 0
    if include_today is None:
        include_today = include_today_closes(today)
    for i, s in enumerate(codes):
        m = meta.get(s, {})
        try:
            d = fetch_aik(s)
        except Exception as e:                            # noqa: BLE001 — 종목 하나의 실패는 행으로 남긴다
            rows[s] = {"name": m.get("name"), "role": m.get("role"), "error": "%s: %s" % (type(e).__name__, str(e)[:200])}
            log("%s %-12s ✗ %s" % (s, (m.get("name") or "")[:12], rows[s]["error"][:80]))
            time.sleep(sleep)
            continue
        if license_ is None and isinstance(d.get("license"), dict):
            license_ = d["license"]
            citation = d.get("citation")
        row = row_of(d, m)
        nrows = None
        if naver:
            try:
                if with_history:
                    nrows = drop_in_progress_day(fetch_naver_history(s, today), today, include_today)
                    hist, hmeta = history_from_rows(nrows, today, listed=m.get("listed"))
                    if hist:
                        row["history_quarterly"], row["history_meta"] = hist, hmeta
                        hist_ok += 1
                    else:
                        row["history_unavailable"], row["history_error"] = True, hmeta.get("error")
                        hist_fail += 1
                elif row.get("as_of") and len(str(row["as_of"])) == 8:
                    nrows = drop_in_progress_day([{"date": k, "close": v, "open": None, "high": None, "low": None, "volume": None}
                                                  for k, v in sorted(fetch_naver_daily(s, row["as_of"], end=today).items())],
                                                 today, include_today)
            except Exception as e:                        # noqa: BLE001 — 네이버 실패는 행에 남기고 aik 값으로 간다
                row["naver_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
                if with_history:
                    row["history_unavailable"], row["history_error"] = True, row["naver_error"]
                    hist_fail += 1
            time.sleep(0.3)
        elif with_history:
            row["history_unavailable"], row["history_error"] = True, "--no-naver"
        apply_close_rule(row, nrows, today)
        rows[s] = row
        nc = row.get("naver_check") or {}
        log("%s %-12s ✓ %s원 (%s%s) 시총 %s억 PER %s PBR %s%s%s" % (
            s, (row["name"] or "")[:12], format(row["close"], ",") if row["close"] is not None else "—",
            row["as_of"], " ←aik %s" % row["aik_as_of"] if row.get("aik_as_of") and row["aik_as_of"] != row["as_of"] else "",
            format(round((row["market_cap_krw"] or 0) / 1e8), ","), row["pe_ttm"], row["pb"],
            (" · 이력 %d분기" % len(row["history_quarterly"])) if row.get("history_quarterly") else "",
            (" · aik %s (%+.3f%%)" % (format(nc["aik"], ","), nc["diff_pct"])) if nc.get("diff_pct") is not None else ""))
        if i < len(codes) - 1:
            time.sleep(sleep)
    out = {
        "as_of": today.isoformat(),
        "source": "aikstockdata.com(상장주식수·PER/PBR·주요계정, 출처표기·비영리) + 네이버 금융 일봉(정규장 종가·분기 시세)",
        "citation": citation,
        "license": license_,
        "close_rule": CLOSE_RULE,
        "run": {"today": today.isoformat(), "include_today_closes": bool(include_today),
                "note": "오늘 날짜 일봉 행은 KST 15:40 이후(또는 --today 가 과거)일 때만 종가·이력에 넣는다 — 장중 러너(10:40 KST)는 전 거래일까지"},
        "fields": {"close": "종가(원) — 네이버 정규장 종가(close_source=naver_regular_close); 네이버가 없으면 aik close. aik 원값은 aik_close, 차이는 naver_check",
                   "as_of": "시세 기준일 YYYYMMDD — 네이버 최신 거래일(as_of_source=naver_latest… 이면 aik 기준일 aik_as_of 보다 최신)",
                   "as_of_source": "aik_same_day | naver_latest(…) | aik",
                   "aik_close": "aikstockdata quote.close 원값('금융위 T+1 확정' 표기) — 정규장 종가와 다른 종목이 많아 대조용으로만 보존",
                   "aik_as_of": "aik 시세 기준일(as_of 를 네이버로 전진했을 때만 다름)",
                   "aik_quote": "as_of 를 전진했을 때 aik 기준일의 종가·시고저·거래량 원값",
                   "close_source": "close 의 출처(naver_regular_close | aik_close(…))",
                   "market_cap_krw_aik": "aik 시총 원값(market_cap_krw 는 close × 발행주식수로 다시 잰 값)",
                   "shares_outstanding": "상장주식수(aik)",
                   "market_cap_krw": "시가총액(원) = close × shares_outstanding", "pe_ttm": "PER(TTM, DART 순이익 기준·aik 기계 산정)",
                   "pb": "PBR(최신 정기보고서 자본총계, aik)",
                   "financials_ref": "최신 정기보고서 누적 주요계정(원) — fin 대조용",
                   "history_quarterly": "분기 기말/고/저/평균 종가(원, 네이버 일봉 수정주가·무거래일 제외). truncated=분기 첫 거래일이 늦음(상장·자료 시작·거래정지)",
                   "history_meta": "source·rows·no_trade_dropped·from·to·window_from(+pre_listed_quarters: universe listed 전 구간 표기, carried_from: 이어붙임)",
                   "naver_check": "aik 기준일(aik_as_of)의 네이버 종가와 aik close 의 차이 %"},
        "roster_n": len(codes), "ok_n": 0, "error_n": 0, "errors": [],
        "naver_check": {"skipped": True},
        "history": {"attempted": bool(naver and with_history), "available_n": hist_ok, "failed_n": hist_fail,
                    "reason": None if (naver and with_history) else ("--no-naver" if not naver else "--no-history"),
                    "source": HISTORY_SOURCE if (naver and with_history) else None,
                    "years": HISTORY_YEARS, "window_from": history_since(today), "truncated_grace_days": TRUNCATED_GRACE_DAYS,
                    "note": "history_quarterly 는 네이버 일봉(정규장·수정주가) 집계, 창은 5년 전이 속한 분기의 첫날부터(분기 경계 정렬), "
                            "무거래일(거래량 0)은 제외. 토스 일봉은 2025-03 NXT 개장 뒤 KRX+NXT 합산이라 쓰지 않는다(close_rule)."},
        "rows": rows,
    }
    refresh_counts(out, naver)
    return out


def refresh_counts(out, naver=True):
    """rows 로부터 ok/error 수와 naver_check 요약을 다시 센다(--only 병합 뒤에도 같은 함수)."""
    rows = out.get("rows") or {}
    ok = sorted(s for s, r in rows.items() if "error" not in r)
    err = sorted(s for s, r in rows.items() if "error" in r)
    out["roster_n"] = len(rows)
    out["ok_n"], out["error_n"], out["errors"] = len(ok), len(err), err
    out["naver_check"] = naver_summary(rows) if naver else {"skipped": True}
    return out


def carry_history(out, prev):
    """네이버 이력을 새로 만들지 못한 행에 기존 prices.json(prev)의 history_quarterly 를 이어 붙인다.

    워크플로(update-kship.yml)의 이어붙임과 같은 규칙: 이력이 없고 error 도 없는 행만, prev 행에 이력이 있을 때만.
    history_meta 는 prev 것을 옮기고 `carried_from`(prev.as_of, 이미 있으면 유지)을 남긴다. 붙인 수를 돌려준다."""
    n = 0
    prow = (prev or {}).get("rows") or {}
    for code, row in (out.get("rows") or {}).items():
        if row.get("history_quarterly") or "error" in row:
            continue
        old = prow.get(code) or {}
        if not old.get("history_quarterly"):
            continue
        row["history_quarterly"] = old["history_quarterly"]
        meta = dict(old.get("history_meta") or {})
        meta["carried_from"] = meta.get("carried_from") or prev.get("as_of")
        row["history_meta"] = meta
        row.pop("history_unavailable", None)
        row["history_carried"] = True
        n += 1
    if n:
        h = out.setdefault("history", {})
        h["carried_n"] = n
        h["carried_note"] = ("일봉을 새로 받지 못해 기존 prices.json(%s 기준)의 history_quarterly 를 이어 붙였다 — "
                             "history_meta.carried_from 참조(출처는 그 행의 history_meta.source)" % prev.get("as_of"))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="종목코드 콤마 목록")
    ap.add_argument("--no-history", action="store_true", help="5년 일봉 생략(네이버 2주 창으로 종가 규칙만)")
    ap.add_argument("--no-naver", action="store_true", help="네이버 생략 — close 는 aik 값")
    ap.add_argument("--no-carry", action="store_true", help="이력을 못 만든 행에 기존 파일 이력을 이어 붙이지 않음")
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--today", default=None)
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    meta = roster()
    codes = sorted(meta)
    if a.only:
        sel = set(a.only.split(","))
        codes = [c for c in codes if c in sel]
    print("모집단 %d사 (universe %d · 폴더 전용 %d · 지주 %s)" % (
        len(meta), sum(1 for m in meta.values() if m["src"].startswith("universe")),
        sum(1 for m in meta.values() if m["src"] == "folder"), HOLDING))
    out = collect(codes, meta, today, with_history=not a.no_history, sleep=a.sleep, naver=not a.no_naver)
    p = os.path.join(ASSETS, OUT)
    prev = load_asset(OUT) if os.path.exists(p) else None
    if prev and not a.no_carry:
        n = carry_history(out, prev)
        if n:
            print("이력 이어붙임: %d 종목 (기존 %s 기준)" % (n, prev.get("as_of")))
    if a.only and prev:
        # 부분 실행은 기존 파일의 다른 행을 보존한다 — 요약도 병합된 전체로 다시 센다
        merged = dict(prev.get("rows", {}))
        merged.update(out["rows"])
        out["rows"] = dict(sorted(merged.items()))
        refresh_counts(out, not a.no_naver)
    write_asset(OUT, out)
    h = out["history"]
    print("prices.json: 성공 %d · 실패 %d%s · 이력 %s(가용 %d·실패 %d·이어붙임 %d%s)" % (
        out["ok_n"], out["error_n"], (" " + ",".join(out["errors"])) if out["errors"] else "",
        "시도" if h["attempted"] else "미시도", h["available_n"], h["failed_n"], h.get("carried_n", 0),
        (" · " + h["reason"]) if h["reason"] else ""))
    nc = out.get("naver_check") or {}
    if not nc.get("skipped"):
        print("종가 규칙: close_source %s · as_of %s · 전진 %d종목 | aik 대조 %d종목 · 일치 %d · |차이|>1%% %d · 최대 %s" % (
            json.dumps(nc.get("close_source_n"), ensure_ascii=False), json.dumps(nc.get("as_of_n")),
            nc.get("as_of_advanced_n", 0), nc.get("checked_n", 0), nc.get("equal_n", 0), nc.get("abs_gt_1pct_n", 0),
            json.dumps(nc.get("max_abs"), ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
