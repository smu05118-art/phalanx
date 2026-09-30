#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_price — 모집단 57사(회사 폴더 56 + 지주 HD한국조선해양 009540)의 시세를 모아 prices.json 을 만든다.

원천은 aikstockdata.com 공개 JSON(`/data/public/s/<code>.json`) — 금융위 확정 종가(T+1),
상장주식수·시가총액, DART 기반 PER(TTM)·PBR, 최신 정기보고서 주요계정. **출처 표기·비영리**
조건이라 응답의 license·citation 문구를 그대로 보존하고 페이지 각주가 이것을 인용한다.
종목마다 0.5초 간격으로 읽고, 실패한 종목은 rows 에 `error` 로 남긴다(전체를 실패시키지 않는다).

`history_quarterly`(분기 기말/고/저/평균 종가 — subQ 의 PER 4종·TP 밴드용)는 **시도만** 한다:
~/phalanx/toss_api.py 의 candles_history 가 있고 토큰 캐시 파일(~/phalanx/jem_data/.toss_token.json)이
**존재하는지만** 확인해 import 해서 5년(분기 경계에 맞춘 창) 일봉을 집계한다. 비밀 파일은 열지도 출력하지도 않는다.
안 되면 `history_unavailable: true` 와 `history_error` 를 남기고, 기존 prices.json 에 이력이 있으면
그 행의 `history_quarterly` 를 이어 붙인다(`history_meta.carried_from`, --no-carry 로 끔) — 러너(토스 없음)와
맥미니 실행이 날마다 뒤집히지 않게 하기 위해서다(워크플로의 이어붙임과 같은 규칙).

종가 대조(`naver_check`): 같은 기준일의 네이버 일봉 종가(정규장)를 받아 aik `close` 와의 차이 % 를 행마다
남기고 전체 요약을 상단에 둔다. 검증(2026-09-30)에서 aik `close` 는 시가·고가·저가·거래량은 네이버와 같은데
**종가만** 48/57 종목에서 달랐고(삼성重 9/28 20,100 vs 네이버·토스 20,150, 화인베스틸 974 vs 1,017 = 4.4%),
토스 일봉 종가는 표본 4종목 전부 네이버와 같았다. 그래서 `close` 는 계약대로 aik 값을 두되(라이선스·T+1 확정 원천
표기) "정규장 종가" 라고 단정하지 않고 대조 기록을 함께 싣는다 — 소비자는 `naver_check.diff_pct` 로 판단한다.

    python3 kship_price.py                       # 57사 시세 + 가능하면 5년 분기 시세 + 네이버 종가 대조
    python3 kship_price.py --no-history          # aikstockdata 만(이력은 기존 파일에서 이어 붙임)
    python3 kship_price.py --no-naver            # 네이버 대조 생략
    python3 kship_price.py --only 010140,075580
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

from kship_lib import ASSETS, KSHIP, load_asset, write_asset
from kship_universe import load as load_universe

AIK = "https://aikstockdata.com/data/public/s/%s.json"
# 네이버 일봉(정규장 종가) — aik `close` 대조용. 응답은 JSON 이 아니라 JS 배열 리터럴(작은따옴표 헤더)이다.
NAVER_DAILY = "https://fchart.stock.naver.com/siseJson.nhn?symbol=%s&requestType=1&startTime=%s&endTime=%s&timeframe=day"
NAVER_LOOKBACK_DAYS = 14                              # 기준일 앞 2주(연휴 포함)만 받는다
OUT = "prices.json"
HOLDING = "009540"                                    # 폴더 없는 지주 — 스펙 1 모집단 규약
UA = "phalanx-argus-kship/0.1 (non-commercial, source attribution)"
TOSS_DIR = os.path.expanduser("~/phalanx")
TOSS_TOKEN = os.path.join(TOSS_DIR, "jem_data", ".toss_token.json")
HISTORY_YEARS = 5
HISTORY_PAGES = 7                                     # 200봉 × 7 ≈ 5.6년 거래일


# ── 모집단 ──────────────────────────────────────────────────

def roster():
    """universe.json(41) ∪ 회사 폴더(56, 승격 16 포함) ∪ 009540 → {stock: {name, market, role, src}}."""
    out = {}
    for r in load_universe():
        out[r["stock"]] = {"name": r["name"], "market": r.get("market"), "role": r.get("role"), "src": "universe"}
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
        out[d] = {"name": name, "market": None, "role": "equip", "src": "folder"}
    if HOLDING not in out:
        out[HOLDING] = {"name": "HD한국조선해양", "market": "유가", "role": "holding", "src": "spec"}
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


# ── 시세 이력(토스 일봉 → 분기) ─────────────────────────────

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
    첫 거래일이 분기 시작 +10일보다 늦은 분기(상장·자료 시작)는 `truncated: true` — 고/저/평균이 분기 전체를 덮지 않는다.
    값은 원 단위 정수(평균은 소수 1자리)."""
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


def toss_module():
    """토스 클라이언트를 쓸 수 있는지 — 파일 존재 여부만 본다(토큰·시크릿 내용은 읽지 않는다).
    돌려주는 것: (module 또는 None, 불가 사유)."""
    mod_path = os.path.join(TOSS_DIR, "toss_api.py")
    if not os.path.exists(mod_path):
        return None, "toss_api.py 없음(%s)" % mod_path
    if not os.path.exists(TOSS_TOKEN):
        return None, "토큰 캐시 파일 없음(%s) — 인증된 적 없음" % TOSS_TOKEN
    if TOSS_DIR not in sys.path:
        sys.path.insert(0, TOSS_DIR)
    try:
        import toss_api                                   # noqa: E402
    except Exception as e:                                # noqa: BLE001
        return None, "toss_api import 실패: %s" % e
    if not hasattr(toss_api, "candles_history"):
        return None, "toss_api.candles_history 없음"
    # toss_api.TOKEN_CACHE 는 **상대경로**(jem_data/.toss_token.json) — cwd 가 ~/phalanx 가 아니면
    # 토큰 캐시를 못 찾고 새 토큰을 받아 **이 레포 안에** 캐시 파일을 만든다. 절대경로로 바꿔 둔다.
    toss_api.TOKEN_CACHE = pathlib.Path(TOSS_TOKEN)
    return toss_api, None


def fetch_history(toss, stock, today, pages=HISTORY_PAGES):
    """5년 일봉(수정주가) → 분기 집계. 실패는 예외로 올린다(호출자가 error 필드에 적는다).
    toss_api._creds() 는 자격이 없으면 sys.exit 를 부르므로 SystemExit 도 잡아 올린다."""
    try:
        candles = toss.candles_history(stock, "1d", pages=pages, adjusted=True, strict=True)
    except SystemExit as e:
        raise RuntimeError("toss_api 종료: %s" % e)
    if not candles:
        raise RuntimeError("일봉 0건")
    return aggregate_candles(candles, today), candles


# ── 종가 대조(네이버 일봉) ──────────────────────────────────

def parse_naver_daily(text):
    """siseJson 응답 → {YYYYMMDD: 종가}. 헤더 행(['날짜','시가','고가','저가','종가',…])은 작은따옴표라 JSON 이 아니다."""
    body = text.strip().replace("'", '"')
    rows = json.loads(body) if body else []
    out = {}
    for r in rows[1:] if rows and isinstance(rows[0], list) and rows[0] and rows[0][0] == "날짜" else rows:
        if isinstance(r, list) and len(r) >= 5 and isinstance(r[0], str) and len(r[0]) == 8 and isinstance(r[4], (int, float)):
            out[r[0]] = r[4]
    return out


def fetch_naver_daily(stock, as_of, lookback=NAVER_LOOKBACK_DAYS):
    """기준일(YYYYMMDD) 앞 lookback 일 ~ 기준일의 네이버 일봉 종가 {YYYYMMDD: close}."""
    d = datetime.date(int(as_of[:4]), int(as_of[4:6]), int(as_of[6:]))
    start = (d - datetime.timedelta(days=lookback)).strftime("%Y%m%d")
    return parse_naver_daily(_get(NAVER_DAILY % (stock, start, as_of)).decode("utf-8"))


def naver_check_row(close, as_of, naver):
    """aik close vs 같은 기준일 네이버 종가. 기준일 행이 없으면 None(휴장·미제공)."""
    nv = (naver or {}).get(as_of)
    if nv is None or close is None or not close:
        return {"date": as_of, "aik": close, "naver_close": nv, "diff_pct": None,
                "note": "네이버 기준일 종가 없음" if nv is None else "aik close 없음"}
    return {"date": as_of, "aik": close, "naver_close": _int(nv), "diff_pct": round(100.0 * (close - nv) / nv, 3)}


def naver_summary(rows):
    """행별 naver_check → 상단 요약(대조 수·일치 수·|차이|>1% 수·최대 |차이|와 그 종목)."""
    checks = [(s, r["naver_check"]) for s, r in rows.items() if isinstance(r.get("naver_check"), dict) and r["naver_check"].get("diff_pct") is not None]
    out = {"source": "fchart.stock.naver.com siseJson 일봉 종가(정규장) — 기준일 as_of 같은 날",
           "checked_n": len(checks), "equal_n": sum(1 for _, c in checks if c["diff_pct"] == 0),
           "abs_gt_1pct_n": sum(1 for _, c in checks if abs(c["diff_pct"]) > 1.0),
           "max_abs": None,
           "note": "aik `close` 는 금융위 T+1 확정 종가로 표기되지만 네이버·토스의 정규장 종가와 다를 수 있다(2026-09-30 검증: "
                   "시가·고가·저가·거래량은 같고 종가만 48/57 상이, 최대 4.4%). 어느 쪽이 '확정'인지는 이 파일이 판정하지 않는다 — "
                   "2026-09-30 부터 close 는 네이버 정규장 종가(close_source), aik 원값은 aik_close — 차이는 여기 기록."}
    if checks:
        s, c = max(checks, key=lambda x: abs(x[1]["diff_pct"]))
        out["max_abs"] = {"stock": s, "diff_pct": c["diff_pct"], "aik": c["aik"], "naver_close": c["naver_close"]}
    return out


# ── 조립 ────────────────────────────────────────────────────

def collect(codes, meta, today, with_history=True, sleep=0.5, pages=HISTORY_PAGES, log=print, naver=True):
    rows, license_, citation = {}, None, None
    toss, why = (toss_module() if with_history else (None, "--no-history"))
    hist_ok = hist_fail = 0
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
        if toss is not None:
            try:
                hist, candles = fetch_history(toss, s, today, pages)
                row["history_quarterly"] = hist
                row["history_meta"] = {"source": "토스증권 오픈API 일봉(adjusted=true)", "candles": len(candles),
                                       "from": str(candles[0].get("timestamp", ""))[:10],
                                       "to": str(candles[-1].get("timestamp", ""))[:10]}
                # 같은 날짜의 토스 종가 vs aik close 대조. 실측(9/28 삼성重 aik 20,100 vs 토스 20,150 — 네이버도
                # 20,150): 어긋나는 쪽은 aik 였다(시가·고가·저가·거래량은 세 원천이 같고 종가만 다름). 이력은 분기
                # 밴드(고/저/평균)용이라 차이 % 만 기록하고, close 는 계약(스펙 2-3)대로 aik 값을 둔다.
                ao = row.get("as_of")
                if ao and len(ao) == 8:
                    iso = "%s-%s-%s" % (ao[:4], ao[4:6], ao[6:])
                    same = [c for c in candles if str(c.get("timestamp", ""))[:10] == iso]
                    if same and row.get("close"):
                        tc = float(same[-1]["closePrice"])
                        row["history_meta"]["close_check"] = {"date": iso, "aik": row["close"], "toss": _int(tc),
                                                              "diff_pct": round(100.0 * (tc - row["close"]) / row["close"], 3)}
                hist_ok += 1
            except Exception as e:                        # noqa: BLE001
                row["history_unavailable"] = True
                row["history_error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
                hist_fail += 1
        else:
            row["history_unavailable"] = True
            row["history_error"] = why
        if naver and row.get("as_of") and len(str(row["as_of"])) == 8:
            try:
                row["naver_check"] = naver_check_row(row.get("close"), row["as_of"], fetch_naver_daily(s, row["as_of"]))
            except Exception as e:                        # noqa: BLE001 — 대조는 선택, 본체는 계속
                row["naver_check"] = {"date": row["as_of"], "aik": row.get("close"), "naver_close": None, "diff_pct": None,
                                      "error": "%s: %s" % (type(e).__name__, str(e)[:160])}
            time.sleep(0.3)
        # 종가 정본(2026-09-30 오너 결정): 같은 기준일 네이버 정규장 종가가 있으면 그것을 `close` 로 쓴다.
        # 실측 — 9/28·9/29 57종목 중 48~49종목에서 aik `close` 가 네이버·토스 정규장 종가와 달랐고(최대 4.4%,
        # 시가·고가·저가·거래량은 세 원천이 같음) 어긋난 쪽은 aik 였다. aik 값은 aik_close 로 보존하고
        # 시총은 정규장 종가 × 발행주식수로 다시 잰다(둘이 같으면 표기만 바뀐다).
        nc0 = row.get("naver_check") or {}
        if nc0.get("naver_close") is not None:
            row["aik_close"] = row.get("close")
            row["close"] = nc0["naver_close"]
            row["close_source"] = "naver_regular_close"
            if row.get("shares_outstanding"):
                row["market_cap_krw_aik"] = row.get("market_cap_krw")
                row["market_cap_krw"] = int(row["close"] * row["shares_outstanding"])
        else:
            row["close_source"] = "aik_close(네이버 기준일 종가 없음)"
        rows[s] = row
        nc = row.get("naver_check") or {}
        log("%s %-12s ✓ %s원 (%s) 시총 %s억 PER %s PBR %s%s%s" % (
            s, (row["name"] or "")[:12], format(row["close"], ",") if row["close"] is not None else "—",
            row["as_of"], format(round((row["market_cap_krw"] or 0) / 1e8), ","), row["pe_ttm"], row["pb"],
            (" · 이력 %d분기" % len(row["history_quarterly"])) if row.get("history_quarterly") else "",
            (" · 네이버 %s (%+.3f%%)" % (format(nc["naver_close"], ","), nc["diff_pct"])) if nc.get("diff_pct") is not None else ""))
        if i < len(codes) - 1:
            time.sleep(sleep)
    ok = sorted(s for s, r in rows.items() if "error" not in r)
    err = sorted(s for s, r in rows.items() if "error" in r)
    out = {
        "as_of": today.isoformat(),
        "source": "aikstockdata.com(금융위 확정종가 T+1) — 출처표기·비영리",
        "citation": citation,
        "license": license_,
        "fields": {"close": "종가(원) — 같은 기준일 네이버 정규장 종가(close_source=naver_regular_close); 없으면 aik close. aik 원값은 aik_close, 차이는 naver_check",
                   "aik_close": "aikstockdata quote.close 원값('금융위 T+1 확정' 표기) — 정규장 종가와 다른 종목이 많아 대조용으로만 보존",
                   "close_source": "close 의 출처(naver_regular_close | aik_close(…))",
                   "market_cap_krw_aik": "aik 시총 원값(close 를 네이버로 바꾼 경우 market_cap_krw 는 네이버 종가 × 발행주식수)",
                   "as_of": "시세 기준일 YYYYMMDD", "shares_outstanding": "상장주식수",
                   "market_cap_krw": "시가총액(원) = close × shares_outstanding(aik 산정)", "pe_ttm": "PER(TTM, DART 순이익 기준·기계 산정)",
                   "pb": "PBR(최신 정기보고서 자본총계)",
                   "financials_ref": "최신 정기보고서 누적 주요계정(원) — fin 대조용",
                   "history_quarterly": "분기 기말/고/저/평균 종가(원, 토스 일봉 adjusted=true 수정주가). truncated=분기 첫 거래일이 늦음(상장·자료 시작)",
                   "naver_check": "같은 기준일 네이버 일봉 종가(정규장)와 aik close 의 차이 %"},
        "roster_n": len(codes), "ok_n": len(ok), "error_n": len(err), "errors": err,
        "naver_check": naver_summary(rows) if naver else {"skipped": True},
        "history": {"attempted": toss is not None, "available_n": hist_ok, "failed_n": hist_fail,
                    "reason": why, "source": "~/phalanx/toss_api.py candles_history (토큰 캐시 존재 여부만 확인)" if toss is not None else None,
                    "years": HISTORY_YEARS, "pages": pages,
                    "window_from": history_since(today), "truncated_grace_days": TRUNCATED_GRACE_DAYS,
                    "note": "history_quarterly 는 토스 일봉(adjusted=true 수정주가) 집계, 창은 5년 전이 속한 분기의 첫날부터(분기 경계 정렬). "
                            "같은 날 토스 종가와 aik close 가 수십 원~수 % 다를 수 있다(history_meta.close_check 에 기록) — 검증(2026-09-30)에서 "
                            "토스 종가는 네이버 정규장 종가와 같았고 어긋난 쪽은 aik 였다. 이력은 밴드(고/저/평균)용, 스칼라 종가 계약은 close(aik) 다."},
        "rows": rows,
    }
    return out


def carry_history(out, prev):
    """토스 이력을 새로 만들지 못한 행에 기존 prices.json(prev)의 history_quarterly 를 이어 붙인다.

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
        h["carried_note"] = ("토스 일봉을 새로 받지 못해 기존 prices.json(%s 기준)의 history_quarterly 를 이어 붙였다 — "
                             "history_meta.carried_from 참조" % prev.get("as_of"))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="종목코드 콤마 목록")
    ap.add_argument("--no-history", action="store_true")
    ap.add_argument("--no-naver", action="store_true", help="네이버 일봉 종가 대조 생략")
    ap.add_argument("--no-carry", action="store_true", help="이력을 못 만든 행에 기존 파일 이력을 이어 붙이지 않음")
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--pages", type=int, default=HISTORY_PAGES)
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
    out = collect(codes, meta, today, with_history=not a.no_history, sleep=a.sleep, pages=a.pages, naver=not a.no_naver)
    p = os.path.join(ASSETS, OUT)
    prev = load_asset(OUT) if os.path.exists(p) else None
    if prev and not a.no_carry:
        n = carry_history(out, prev)
        if n:
            print("이력 이어붙임: %d 종목 (기존 %s 기준)" % (n, prev.get("as_of")))
    if a.only:
        # 부분 실행은 기존 파일의 다른 행을 보존한다
        if prev:
            merged = dict(prev.get("rows", {}))
            merged.update(out["rows"])
            out["rows"] = dict(sorted(merged.items()))
            out["roster_n"] = len(out["rows"])
            out["ok_n"] = sum(1 for r in out["rows"].values() if "error" not in r)
            out["error_n"] = len(out["rows"]) - out["ok_n"]
            out["errors"] = sorted(s for s, r in out["rows"].items() if "error" in r)
    write_asset(OUT, out)
    h = out["history"]
    print("prices.json: 성공 %d · 실패 %d%s · 이력 %s(가용 %d·실패 %d·이어붙임 %d%s)" % (
        out["ok_n"], out["error_n"], (" " + ",".join(out["errors"])) if out["errors"] else "",
        "시도" if h["attempted"] else "미시도", h["available_n"], h["failed_n"], h.get("carried_n", 0),
        (" · " + h["reason"]) if h["reason"] else ""))
    nc = out.get("naver_check") or {}
    if not nc.get("skipped"):
        print("네이버 종가 대조: %d종목 · 일치 %d · |차이|>1%% %d · 최대 %s" % (
            nc.get("checked_n", 0), nc.get("equal_n", 0), nc.get("abs_gt_1pct_n", 0), json.dumps(nc.get("max_abs"), ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
