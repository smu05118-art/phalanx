#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_fx — 레퍼런스 모델 `변수` 시트 행 5~14 의 환율 6행을 ECB 일별 환율에서 만든다.

  원/달러(평균·기말) · 원/100Y(평균·기말) · W/Euro(평균·기말) · 원/중국원(평균·기말)

원천은 ECB 참조환율(api.frankfurter.app — `.dev/v1` 로 301 리다이렉트되므로 따라간다).
ECB 는 USD 기준 KRW·JPY·EUR·CNY 를 하루 한 값(14:15 CET) 주므로 교차환율은 **일별로**
먼저 만들고(원/100엔 = 100 × KRW/JPY, 원/유로 = KRW/EUR, 원/위안 = KRW/CNY) 그 다음 분기
평균·기말을 잡는다 — 평균의 비율이 아니라 비율의 평균이다.

레퍼런스 `변수` 시트는 서울외환시장 종가(2005Q1 원/달러 평균 1022.84·기말 1015.45)라서
ECB 와 수 원 차이가 난다. 이 차이는 fx.json `reference_check`·`note` 에 적고 값을 맞추지
않는다(원천을 바꿔 끼우면 재현이 깨진다). 최근 분기 기말은 네이버 marketindex(서울 종가)로
대조해 차이 % 를 `naver_check` 에 남긴다.

캐시: 일별 원자료는 assets/fx_daily_cache.json 에 두고, 재실행 시 지난 연도 구간은 건너뛰고
올해만 마지막 캐시일부터 증분 요청한다(요청은 1년 단위 구간, 실패 시 3회 재시도).

    python3 kship_fx.py                 # 증분 수집 + fx.json 생성
    python3 kship_fx.py --offline       # 네트워크 없이 캐시로만 fx.json 재생성
    python3 kship_fx.py --no-naver      # 네이버 대조 생략
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

from kship_lib import ASSETS, atomic_write, load_asset, write_asset

FRANKFURTER = "https://api.frankfurter.app/%s..%s?from=USD&to=KRW,JPY,EUR,CNY"
NAVER = "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=%d&pageSize=60"
CACHE = "fx_daily_cache.json"
OUT = "fx.json"
SYMBOLS = ("KRW", "JPY", "EUR", "CNY")
PAIRS = ("USDKRW", "JPY100KRW", "EURKRW", "CNYKRW")
FIRST_YEAR = 2005
FORWARD_LAST = "2028Q4"
UA = "phalanx-argus-kship/0.1 (+ECB reference rates via frankfurter)"

# 레퍼런스 `변수` 시트(세진 075580 subQ, 서울외환시장 기준) 2005Q1 — 원천 차이 확인용.
REFERENCE_2005Q1 = {"USDKRW_avg": 1022.84, "USDKRW_end": 1015.45,
                    "source": "레퍼런스 subQ `변수` 시트 행 5~6(서울외환시장 종가 기준)"}


# ── HTTP ────────────────────────────────────────────────────

def _get(url, tries=3, timeout=40):
    """GET → bytes. 301/302 는 urllib HTTPRedirectHandler 로 따라가고(frankfurter .app→.dev),
    실패는 3회까지 지수 백오프로 재시도한다. 끝내 실패하면 예외를 그대로 올린다."""
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with opener.open(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last = e
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError("GET 실패 %s: %s" % (url, last))


def fetch_range(start, end):
    """ECB 일별 환율 [start, end] (YYYY-MM-DD 포함 구간) → {date: {KRW, JPY, EUR, CNY}}.

    frankfurter 는 start 가 비영업일이면 **그 직전 영업일**을 첫 행으로 끼워 준다(2005-01-01
    요청에 2004-12-31 이 온다) — 구간 밖 날짜는 버린다."""
    raw = json.loads(_get(FRANKFURTER % (start, end)).decode("utf-8"))
    out = {}
    for d, rates in (raw.get("rates") or {}).items():
        if d < start or d > end:
            continue
        if not all(k in rates for k in SYMBOLS):
            continue
        out[d] = {k: float(rates[k]) for k in SYMBOLS}
    return out


# ── 캐시 ────────────────────────────────────────────────────

def load_cache():
    p = os.path.join(ASSETS, CACHE)
    if not os.path.exists(p):
        return {"source": "ECB reference rates via api.frankfurter.app", "base": "USD",
                "symbols": list(SYMBOLS), "ranges": [], "days": {}}
    return load_asset(CACHE)


MIN_DAYS_FULL_YEAR = 200                               # ECB 영업일은 연 ≈255일 — 이보다 적게 오면 완결 구간으로 적지 않는다


def update_cache(cache, today, log=print):
    """지난 연도는 완결 구간이 캐시에 있으면 건너뛰고, 올해는 마지막 캐시일부터 today 까지만 받는다.

    지난 연도 응답이 비거나 짧으면(HTTP 200 에 rates 없음·일부만) `ranges` 에 완결로 적지 않는다 — 적어 두면 그 해 ~250일이
    영구히 빠진 채 다시 받지 않게 된다(분기 평균이 조용히 틀어짐). 받은 날은 그대로 캐시에 넣고 다음 실행이 다시 시도한다."""
    done = {(r[0], r[1]) for r in cache["ranges"]}
    days = cache["days"]
    for y in range(FIRST_YEAR, today.year + 1):
        start = "%d-01-01" % y
        end = "%d-12-31" % y
        if y < today.year:
            if (start, end) in done:
                continue
        else:
            end = today.isoformat()
            have = sorted(d for d in days if d >= start)
            if have:
                start = have[-1]                  # 마지막 캐시일을 다시 받아 값 정정도 흡수
        got = fetch_range(start, end)
        days.update(got)
        if y < today.year:
            if len(got) >= MIN_DAYS_FULL_YEAR:
                cache["ranges"].append([start, end, today.isoformat()])
            else:
                log("  !! %s..%s 응답 %d일 < %d — 완결 구간으로 기록하지 않음(다음 실행에 재요청)" % (start, end, len(got), MIN_DAYS_FULL_YEAR))
        log("  %s..%s  %d일" % (start, end, len(got)))
        time.sleep(0.3)
    cache["ranges"] = sorted({tuple(r[:2]): r for r in cache["ranges"]}.values())
    cache["days"] = dict(sorted(days.items()))
    cache["updated_at"] = today.isoformat()
    return cache


# ── 집계 ────────────────────────────────────────────────────

def cross(day):
    """USD 기준 일별 4통화 → 레퍼런스 4쌍(원/달러·원/100엔·원/유로·원/위안)."""
    krw = day["KRW"]
    return {"USDKRW": krw, "JPY100KRW": 100.0 * krw / day["JPY"],
            "EURKRW": krw / day["EUR"], "CNYKRW": krw / day["CNY"]}


def quarter_of(date):
    """'YYYY-MM-DD' → 'YYYYQn'."""
    return "%sQ%d" % (date[:4], (int(date[5:7]) - 1) // 3 + 1)


def last_weekday_of_quarter(q):
    y, n = int(q[:4]), int(q[5])
    m = n * 3
    d = datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.isoformat()


def _agg(group):
    """{date: cross} 한 묶음 → 평균·기말(마지막 영업일)·일수. 소수 2자리(레퍼런스 표기)."""
    dates = sorted(group)
    out = {}
    for p in PAIRS:
        vals = [group[d][p] for d in dates]
        out[p + "_avg"] = round(sum(vals) / len(vals), 2)
        out[p + "_end"] = round(group[dates[-1]][p], 2)
    out["days"] = len(dates)
    out["end_date"] = dates[-1]
    return out


def _is_partial(end_date, q, today):
    """진행 중 분기 판정. 마지막 평일 값이 아직 없고 **오늘이 그 평일을 지나지 않았을 때**만 partial.

    지난 분기에서 마지막 평일 값이 없는 것은 ECB 휴장(성금요일 3/29·3/30 등)이지 미완이 아니다 —
    2013Q1·2018Q1·2024Q1 이 그렇다(실측)."""
    lw = last_weekday_of_quarter(q)
    return end_date < lw and today.isoformat() <= lw


def quarterize(days, today=None):
    """일별 {date: {KRW,JPY,EUR,CNY}} → {'2005Q1': {USDKRW_avg, USDKRW_end, …, days, end_date, partial}}.

    partial: 진행 중 분기(오늘 기준 마지막 평일 값이 아직 없음)."""
    today = today or datetime.date.today()
    groups = {}
    for d, r in days.items():
        groups.setdefault(quarter_of(d), {})[d] = cross(r)
    out = {}
    for q in sorted(groups):
        rec = _agg(groups[q])
        rec["partial"] = _is_partial(rec["end_date"], q, today)
        out[q] = rec
    return out


def annualize(days, today=None):
    """일별 → 연간 평균·기말. 진행 중인 해는 partial."""
    today = today or datetime.date.today()
    groups = {}
    for d, r in days.items():
        groups.setdefault(d[:4], {})[d] = cross(r)
    out = {}
    for y in sorted(groups):
        rec = _agg(groups[y])
        rec["partial"] = _is_partial(rec["end_date"], y + "Q4", today)
        out[y] = rec
    return out


def q_next(q):
    y, n = int(q[:4]), int(q[5])
    return "%dQ%d" % (y + (n == 4), n % 4 + 1)


def forward(quarters, daily_last, q_to=FORWARD_LAST):
    """마지막 완결 분기 다음부터 q_to 까지 flat. 값은 **마지막 일별 관측치**(가장 최근 기말).

    진행 중인 분기(partial)가 있으면 그 분기의 평균은 분기누적 실측 평균을 쓰고(basis 표기),
    기말은 마지막 관측치로 둔다. 전부 kind=estimate."""
    complete = [q for q, r in quarters.items() if not r["partial"]]
    if not complete:
        return {"method": "flat_last_end"}
    q = q_next(complete[-1])
    out = {"method": "flat_last_end",
           "flat_value_date": daily_last["date"],
           "note": "가정 — 마지막 ECB 관측치를 %s 까지 평평하게 둔다. 선도환율·컨센서스 아님." % q_to}
    # 'YYYYQn' 은 사전순 == 시간순. 마지막 완결 분기가 q_to 이상이면(2029 이후 실행) 분기 키 없이 끝낸다 —
    # `while True … if q == q_to: break` 는 q 가 q_to 를 이미 지나 있으면 영원히 돈다(검증에서 잡음).
    if q > q_to:
        out["note"] += " 마지막 완결 분기 %s 가 지평 %s 이상 — 예측 분기 없음(FORWARD_LAST 연장 필요)." % (complete[-1], q_to)
        return out
    while q <= q_to:
        rec = {"kind": "estimate"}
        part = quarters.get(q) if quarters.get(q, {}).get("partial") else None
        for p in PAIRS:
            rec[p + "_avg"] = round(part[p + "_avg"] if part else daily_last[p], 2)
            rec[p + "_end"] = round(daily_last[p], 2)
        rec["basis"] = ("분기누적 실측 평균(%d일, ~%s) + 기말은 마지막 관측치" % (part["days"], part["end_date"])
                        if part else "마지막 관측치 %s flat" % daily_last["date"])
        out[q] = rec
        q = q_next(q)
    return out


# ── 대조 ────────────────────────────────────────────────────

def fetch_naver(pages=2):
    """네이버 marketindex USDKRW 종가 {date: close} — 60행 × pages(최근 약 반년)."""
    out = {}
    for pg in range(1, pages + 1):
        rows = json.loads(_get(NAVER % pg).decode("utf-8"))
        for r in rows:
            d, c = r.get("localTradedAt"), r.get("closePrice")
            if d and c:
                out[d] = float(str(c).replace(",", ""))
        time.sleep(0.3)
    return out


def naver_check(quarters, days, naver):
    """네이버 창 안에 들어오는 분기 기말과 최근 공통 일자의 USDKRW 를 대조한다(차이 %)."""
    ecb_last = max(days)
    common = sorted(d for d in naver if d in days)
    out = {"source": "api.stock.naver.com marketindex FX_USDKRW (서울외환시장 종가)",
           "window": [min(naver), max(naver)] if naver else None,
           "naver_last": {"date": max(naver), "USDKRW": naver[max(naver)]} if naver else None,
           "ecb_last": {"date": ecb_last, "USDKRW": round(days[ecb_last]["KRW"], 2)},
           "quarter_ends": [], "latest_common": None}
    for q, r in quarters.items():
        d = r["end_date"]
        if d in naver:
            nv = naver[d]
            out["quarter_ends"].append({"quarter": q, "date": d, "ecb_end": r["USDKRW_end"], "naver_close": nv,
                                        "diff_pct": round(100.0 * (r["USDKRW_end"] - nv) / nv, 3),
                                        "partial": r["partial"]})
    if common:
        d = common[-1]
        e = round(days[d]["KRW"], 2)
        out["latest_common"] = {"date": d, "ecb": e, "naver": naver[d],
                                "diff_pct": round(100.0 * (e - naver[d]) / naver[d], 3)}
    return out


def reference_check(quarters):
    q = quarters.get("2005Q1")
    if not q:
        return {"ok": False, "reason": "2005Q1 없음"}
    return {"quarter": "2005Q1", "reference": REFERENCE_2005Q1,
            "ecb": {"USDKRW_avg": q["USDKRW_avg"], "USDKRW_end": q["USDKRW_end"]},
            "diff_avg": round(q["USDKRW_avg"] - REFERENCE_2005Q1["USDKRW_avg"], 2),
            "diff_end": round(q["USDKRW_end"] - REFERENCE_2005Q1["USDKRW_end"], 2)}


# ── 조립 ────────────────────────────────────────────────────

def build(cache, today, naver=None):
    days = cache["days"]
    quarters = quarterize(days, today)
    annual = annualize(days, today)
    last_d = max(days)
    daily_last = {"date": last_d, **{p: round(v, 2) for p, v in cross(days[last_d]).items()}}
    ref = reference_check(quarters)
    fx = {
        "source": "ECB via api.frankfurter.app; Naver marketindex cross-check",
        "as_of": today.isoformat(),
        "unit": {"USDKRW": "원/달러", "JPY100KRW": "원/100엔 (=100×KRW/JPY)", "EURKRW": "원/유로 (=KRW/EUR)",
                 "CNYKRW": "원/위안 (=KRW/CNY)"},
        "reference_rows": {"USDKRW_avg": " 원/달러(평균)", "USDKRW_end": " 원/달러(기말)",
                           "JPY100KRW_avg": " 원/100Y(평균)", "JPY100KRW_end": " 원/100Y(기말)",
                           "EURKRW_avg": " W/Euro(평균)", "EURKRW_end": " W/Euro(기말)",
                           "CNYKRW_avg": " 원/중국원(평균)", "CNYKRW_end": " 원/중국원(기말)"},
        "method": "ECB 14:15 CET 참조환율(USD 기준) → 일별 교차환율 → 분기/연간 산술평균·마지막 영업일 기말. "
                  "avg 는 비율의 일별 평균(평균의 비율 아님). 소수 2자리.",
        "daily_last": daily_last,
        "daily_cache": "tools/assets/%s (%d일, %s~%s)" % (CACHE, len(days), min(days), last_d),
        "quarters": quarters,
        "forward": forward(quarters, daily_last),
        "annual": annual,
        "reference_check": ref,
        "naver_check": naver_check(quarters, days, naver) if naver else {"skipped": True},
        "note": ("레퍼런스 `변수` 시트는 서울외환시장 종가(2005Q1 원/달러 평균 1022.84·기말 1015.45)이고 "
                 "이 파일은 ECB 참조환율이라 2005Q1 평균 %+.2f원·기말 %+.2f원 차이가 난다. 값을 맞추지 않고 "
                 "차이만 기록한다. 원/100엔·원/유로·원/위안은 ECB USD 기준 교차환율." % (ref.get("diff_avg", 0), ref.get("diff_end", 0))),
        "license": "ECB reference rates — 자유 이용(출처 표기). frankfurter.app 은 무키 공개 API.",
    }
    return fx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="네트워크 없이 캐시로만 fx.json 재생성")
    ap.add_argument("--no-naver", action="store_true")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (기본 오늘)")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    cache = load_cache()
    if not a.offline:
        print("ECB 일별 수집(캐시 %d일):" % len(cache["days"]))
        update_cache(cache, today)
        atomic_write(os.path.join(ASSETS, CACHE), json.dumps(cache, ensure_ascii=False, indent=1) + "\n")
    if not cache["days"]:
        print("일별 캐시가 비어 있다 — --offline 을 빼고 다시 실행", file=sys.stderr)
        return 2
    naver = None
    if not a.offline and not a.no_naver:
        try:
            naver = fetch_naver()
        except Exception as e:                           # noqa: BLE001 — 대조는 선택, 본체는 계속
            print("네이버 대조 실패: %s" % e, file=sys.stderr)
    fx = build(cache, today, naver)
    write_asset(OUT, fx)
    qs = fx["quarters"]
    q2 = qs.get("2026Q2", {})
    print("fx.json: 분기 %d개 (%s~%s), 연간 %d개, forward %d분기, 일별 %d일" % (
        len(qs), min(qs), max(qs), len(fx["annual"]),
        sum(1 for k in fx["forward"] if k[:2] == "20"), len(cache["days"])))
    print("2026Q2 USDKRW avg %s / end %s (%s, %d일)" % (q2.get("USDKRW_avg"), q2.get("USDKRW_end"),
                                                      q2.get("end_date"), q2.get("days", 0)))
    print("2005Q1 대 레퍼런스: %s" % json.dumps(fx["reference_check"], ensure_ascii=False))
    nc = fx["naver_check"]
    if not nc.get("skipped"):
        for r in nc["quarter_ends"]:
            print("네이버 대조 %s %s: ECB %s vs 네이버 %s (%+.3f%%)%s" % (
                r["quarter"], r["date"], r["ecb_end"], r["naver_close"], r["diff_pct"],
                " [진행중]" if r["partial"] else ""))
        if nc["latest_common"]:
            c = nc["latest_common"]
            print("네이버 대조 최근 공통일 %s: ECB %s vs 네이버 %s (%+.3f%%)" % (c["date"], c["ecb"], c["naver"], c["diff_pct"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
