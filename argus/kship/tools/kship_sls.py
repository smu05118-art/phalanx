#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_sls — 조선사 선표 매출인식(SLS): 척당 계약 원장 → 분기 진행률 매출(백만$) → 헤지 적용 원화.

레퍼런스(HD현대미포·삼성重 subQ 의 `SLS` 시트)는 클락슨 선표를 Yard×선종×인도분기로 피벗해 매출$ 를 만들고,
헤지환율·건조시점환율을 HEDGE 70% / open 30% 로 섞어 원화 매출을 낸 뒤, 수주업황 코호트(①적자~⑤초호황)
비중으로 타겟 OPM 을 뽑는다. 우리는 클락슨이 없다 — **척당 계약 공시 원장**(assets/contracts.json)이 선표다.

  진행률   계약기간 시작~종료(종료 = 마지막 호선 인도)를 분기로 쪼개 일수 비례(linear, 옵션 s_curve)로 배분.
           종료일이 '-' 인 계약은 같은 선종의 계약기간 중위로 종료를 추정하고 end_estimated 로 표시한다.
  달러화   amt_usd_m = amt_krw_m ÷ 수주시점 환율. 환율 우선순위: 공시 본문의 "USD 1 = 1,383.70원" 고시환율 >
           assets/fx.json 분기 평균 > 그 회사 yards_cache 의 헤지 평균약정환율(약정환율, 현물 아님) > 상수 1350.
           어느 것을 썼는지 계약마다 fx_source 에 남긴다.
  헤지     applied_rate = hedge_ratio × hedge_rate + (1 − hedge_ratio) × spot(건조시점 환율 가정).
           hedge_ratio 는 최신 분기 통화선도 매도 명목액(usd_sell_m) ÷ (기말 수주잔고 원화 ÷ 평균약정환율) 로
           회사별 실측(kship_page.yard_summary 방식). 약정환율이 공시에 없으면 계산하지 않고 0.7 가정으로 표기한다.
           hedge_rate 는 회사 평균약정환율, 없으면 계약별 수주시점 환율(헤지는 보통 수주 무렵에 건다 — 가정).
  코호트   같은 선종·같은 수주연도 안에서 척당 금액(amt_usd_m/ships)의 중위 대비 위치 + 그 연도의 시장 수준
           (원장 안 선종별 연도 중위의 추세만 — 외부 신조선가 지수 없음) → ①~⑤. 기준 문장은 cohort_method 에.
  화해     분기 SLS 원화(해양 계약만) ÷ 정기보고서 부문 매출 3개월분(누계 차분; Q1 = 누계, Q4 = 연간 − 3Q 누계).
           매출표가 없는 회사는 기납품 누계 차분(HD현대重·대한조선·한화오션 방식), HJ 는 프로젝트 누계라 같은 해 차분만.
  타겟OPM  코호트 표(①−5% ②0 ③5 ④10 ⑤15 — 가정) × 매출 비중. 회사 실측 OPM 이 있으면(assets/fin) shift 를 잰다.

한계를 숨기지 않는다: 원장은 2024~ 공시분이라 그 전에 수주한 물량(2024~26 매출의 대부분)이 없다 — 화해 ratio 는
낮고 시간이 갈수록 오른다. 절대 신조선가 수준(2021 이후 호황)은 원장 안에서 알 수 없어 코호트는 상대 등급이다.
HD한국조선해양(009540)이 「자회사의 주요경영사항」으로 낸 계약 중 HD현대重(329180) 자체 공시와 같은 계약은
(선종·척수·금액·수주일)로 짝을 찾아 두 쪽에 shared_with 를 적고, 지주 파일의 합계에서는 뺀다(합산 금지).

    python3 kship_sls.py --all [--curve linear|s_curve] [--spot 1350] [--report]
    python3 kship_sls.py --stock 010140 --report
"""
import argparse
import collections
import datetime
import json
import os
import re
import statistics
import sys

from kship_lib import ASSETS, load_asset, write_asset, q_next, q_of, q_range
from kship_page import series_groups            # 반복건조(시리즈) 추정 — 정의를 한 곳에만 둔다

YARDS_CACHE = os.path.join(ASSETS, "yards_cache")
SLS_DIR = os.path.join(ASSETS, "sls")
YARDS = ["010140", "042660", "329180", "439260", "097230"]
HOLDING = "009540"
HOLDING_SHARES_WITH = "329180"
NAMES = {"010140": "삼성중공업", "042660": "한화오션", "329180": "HD현대중공업", "439260": "대한조선",
         "097230": "HJ중공업", "009540": "HD한국조선해양"}
FX_CONST = 1350.0
HEDGE_RATIO_DEFAULT = 0.7
FORECAST_WINDOW = ("2026Q3", "2028Q4")
COHORT_LABELS = {1: "①적자", 2: "②BEP", 3: "③중마진", 4: "④호황", 5: "⑤초호황"}
COHORT_OPM = {"①적자": -0.05, "②BEP": 0.0, "③중마진": 0.05, "④호황": 0.10, "⑤초호황": 0.15}
COHORT_METHOD = ("척당 금액 = amt_usd_m ÷ ships. (1) 연도 시장 수준: 선종별로 표본 2건 이상인 연도의 척당 중위를 "
                 "그 선종의 첫 연도 중위로 나눈 비율의 선종 간 중위 = year_index(각 선종의 첫 표본 연도 = 1.0 이라 여러 연도가 1.0 일 수 있다). "
                 "year_index <0.90 → ②, 0.90~1.10 → ③, 1.10~1.25 → ④, ≥1.25 → ⑤ 가 연도 기본등급. "
                 "(2) 셀 위치: 같은 선종·같은 수주연도(표본 2건 이상) 중위 대비 <0.90 → −1, >1.10 → +1 (표본 부족이면 "
                 "선종 전체 중위 ÷ year_index 로 대체). 1~5 로 자름. 외부 신조선가 지수 없음 — 원장(2024~ 공시) 안의 "
                 "상대 등급이며 2021 이후 절대 호황 수준은 반영하지 못한다. 척수 없는 계약(공사·해양 EPC 등)은 등급 없음.")
# 정기보고서 II-4 기납품 열의 성격(kship_forecast.load_reports 와 같은 판정): HJ·삼성重 은 프로젝트 누계(같은 해 차분만),
# 나머지는 연초 누계(YTD). 삼성重 은 매출표가 있어 기납품을 쓰지 않는다.
DELIVERED_STYLE = {"097230": "project_cumulative", "010140": "project_cumulative"}
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_NOTE_FX = re.compile(r"(?:USD|US\$)\s*1\s*=\s*([0-9,]+(?:\.\d+)?)\s*원")


# ── 날짜·분기 ───────────────────────────────────────────────

def _date(s):
    m = _DATE.match((s or "").strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def q_of_date(d):
    return q_of(d.year, d.month)


def q_bounds(q):
    y, n = int(q[:4]), int(q[5])
    s = datetime.date(y, 3 * (n - 1) + 1, 1)
    m = 3 * n
    e = datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    return s, e


def q_prev(q):
    y, n = int(q[:4]), int(q[5])
    return "%dQ%d" % (y - (n == 1), 4 if n == 1 else n - 1)


# ── 진행률 스케줄 ───────────────────────────────────────────

def _smoothstep(t):
    return t * t * (3.0 - 2.0 * t)


def round_schedule(sched, amt, nd=3):
    """분기값을 nd 자리로 반올림하고 잔차를 마지막 분기에 얹어 합이 amt(반올림)와 정확히 같게 한다
    (93분기짜리 장기 공사에서 반올림 누적이 0.03 백만$ 까지 벌어진다)."""
    out = collections.OrderedDict((q, round(v, nd)) for q, v in sched.items())
    if out and amt is not None:
        last = next(reversed(out))
        out[last] = round(out[last] + (round(amt, nd) - sum(out.values())), nd)
    return out


def schedule(start, end, amt, curve="linear"):
    """start~end(둘 다 포함)를 분기로 쪼개 amt 를 배분한다. 합 = amt(부동소수 오차만).
    linear: 일수 비례. s_curve: 누적 진행률 F(t) = 3t² − 2t³ (초·후반 완만, 중반 집중 — 가정)."""
    if amt is None or start is None or end is None or end < start:
        return collections.OrderedDict()
    total = (end - start).days + 1
    out = collections.OrderedDict()
    for q in q_range(q_of_date(start), q_of_date(end)):
        qs, qe = q_bounds(q)
        a, b = max(qs, start), min(qe, end)
        t0 = (a - start).days / total
        t1 = ((b - start).days + 1) / total
        f = (t1 - t0) if curve == "linear" else (_smoothstep(t1) - _smoothstep(t0))
        out[q] = amt * f
    return out


# ── 원장 정리: 정정·공유 ────────────────────────────────────

def apply_supersedes(rows):
    """정정공시가 가리키는 원본(supersedes)이 원장에 남아 있으면 지운다 — 새 판만 남긴다.
    kship_contracts --build 가 이미 지웠으면 아무 일도 없다. 반환: (남은 행, 지운 rcp 목록)."""
    superseded = {r["supersedes"] for r in rows if r.get("supersedes")}
    present = {r["rcp"] for r in rows}
    kept = [r for r in rows if r["rcp"] not in superseded]
    return kept, sorted(superseded & present)


def _share_key(r):
    return (r.get("type"), r.get("ships"), round(r.get("amt_krw_m") or 0.0, 1), r.get("signed"))


def mark_shared(rows, holding=HOLDING, yard=HOLDING_SHARES_WITH):
    """지주(009540)가 「자회사의 주요경영사항」으로 낸 계약과 HD현대重(329180) 자체 공시가 같은 계약이면
    (선종·척수·금액·수주일)로 짝짓는다 — rcp 는 두 회사가 각각 접수해 서로 다르다. 두 쪽 다 shared_with 를 적고
    지주 쪽에는 shared_owner 를 둔다(합계에서 뺄 표지). 반환: [(지주 rcp, 조선사 rcp)] 정렬."""
    yard_rows = collections.defaultdict(list)
    for r in sorted(rows, key=lambda r: r["rcp"]):
        if r["stock"] == yard:
            yard_rows[_share_key(r)].append(r)
    pairs = []
    for r in sorted(rows, key=lambda r: r["rcp"]):
        if r["stock"] != holding:
            continue
        cands = yard_rows.get(_share_key(r)) or []
        if not cands:
            continue
        y = cands[0]
        r["shared_with"] = "%s:%s" % (yard, y["rcp"])
        r["shared_owner"] = yard
        y["shared_with"] = "%s:%s" % (holding, r["rcp"])
        pairs.append((r["rcp"], y["rcp"]))
    return sorted(pairs)


_SUB_YARD = re.compile(r"(현대삼호|현대미포|현대중공업)")
CONTRACTS_CACHE = os.path.join(ASSETS, "contracts")


def sub_yard_of(row):
    """지주 공시의 실제 건조 조선소. 공시 머리 '자회사인 에이치디현대삼호(주)의 주요경영사항신고' 가 원문 캐시
    (assets/contracts/<stock>/<rcp>.json, kv 첫 항목)에 남아 있다 — 그것을 먼저, 없으면 본문 note 의
    '최근매출액은 …(주)의' 를 읽는다(읽기만 한다). 없으면 None."""
    p = os.path.join(CONTRACTS_CACHE, row["stock"], "%s.json" % row["rcp"])
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                kv = json.load(f).get("kv") or []
        except (OSError, ValueError):
            kv = []
        for it in kv:
            lab = it[0] if isinstance(it, (list, tuple)) and it else ""
            if "자회사" in lab:
                m = _SUB_YARD.search(lab)
                if m:
                    return m.group(1)
    m = _SUB_YARD.search(row.get("note") or "")
    return m.group(1) if m else None


# ── 환율 ────────────────────────────────────────────────────

def load_fx():
    p = os.path.join(ASSETS, "fx.json")
    return load_asset("fx.json") if os.path.exists(p) else None


def fx_quarter(fx, q, const):
    """분기 USDKRW 평균: fx.json quarters(과거) → forward(미래) → daily_last → 상수. (값, 출처).
    const=None 이면 상수 폴백 없이 (None, None) — fx_at_sign 이 다음 우선순위(약정환율·상수)로 넘어가게 한다
    (전에는 '%g' % None 으로 죽었다: fx.json 에 없는 분기에 수주한 계약 하나가 빌드 전체를 멈춘다)."""
    if fx:
        v = ((fx.get("quarters") or {}).get(q) or {}).get("USDKRW_avg")
        if v:
            return float(v), "fx.json quarters"
        v = ((fx.get("forward") or {}).get(q) or {}).get("USDKRW_avg")
        if v:
            return float(v), "fx.json forward"
        v = (fx.get("daily_last") or {}).get("USDKRW")
        if v:
            return float(v), "fx.json daily_last(flat)"
    if const is None:
        return None, None
    return const, "const_%g" % const


def fx_quarter_end(fx, q):
    """분기 기말 원/달러: fx.json quarters → forward → daily_last. 없으면 (None, None). 잔고(시점 값) 환산용."""
    if fx:
        for key, src in (("quarters", "fx.json quarters USDKRW_end"), ("forward", "fx.json forward USDKRW_end")):
            v = ((fx.get(key) or {}).get(q) or {}).get("USDKRW_end")
            if v:
                return float(v), src
        v = (fx.get("daily_last") or {}).get("USDKRW")
        if v:
            return float(v), "fx.json daily_last"
    return None, None


def fx_at_sign(row, fx, yq, const):
    """수주시점 환율. 공시 본문 고시환율 > fx.json > 회사 헤지 평균약정환율(약정, 현물 아님) > 상수."""
    m = _NOTE_FX.search(row.get("note") or "")
    if m:
        return float(m.group(1).replace(",", "")), "disclosure_note"
    d = _date(row.get("signed")) or _date(row.get("start"))
    q = q_of_date(d) if d else None
    if q and fx:
        v, src = fx_quarter(fx, q, None)
        if v:
            return v, src
    if q and q in yq:
        rate = ((yq[q].get("hedge") or {}).get("avg_rate"))
        if rate:
            return float(rate), "yards_cache hedge.avg_rate(약정환율)"
    return const, "const_%g" % const


# ── yards_cache 읽기 ────────────────────────────────────────

def load_yards():
    out = {}
    if not os.path.isdir(YARDS_CACHE):
        return out
    for stock in sorted(os.listdir(YARDS_CACHE)):
        d = os.path.join(YARDS_CACHE, stock)
        if not os.path.isdir(d):
            continue
        qs = {}
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                x = json.load(fh)
            if x.get("ok"):
                qs[x["quarter"]] = x
        out[stock] = qs
    return out


def closing_total(snapshot):
    """기말 수주잔고 합계(백만원). 합계 행이 부문합과 1% 넘게 어긋나면 부문합(kship_page.yard_summary 와 같은 판정)."""
    o = (snapshot or {}).get("orders") or {}
    rows = o.get("rows") or []
    tot = [r for r in rows if r.get("total")]
    segs = [r for r in rows if not r.get("total")]
    seg_sum = sum((r.get("closing") or 0) for r in segs) if any(r.get("closing") is not None for r in segs) else None
    closing = tot[0].get("closing") if tot else seg_sum
    if tot and seg_sum and closing is not None and abs(closing - seg_sum) > 0.01 * seg_sum:
        closing = seg_sum
    return closing


def hedge_params(stock, yq, default_ratio=HEDGE_RATIO_DEFAULT, fx=None):
    """헤지비율 실측: 최신 분기 usd_sell_m ÷ (기말잔고 원화 ÷ 평균약정환율). 약정환율이 없으면 가정 0.7.
    약정환율이 없어도 명목액이 공시돼 있으면 fx.json 기말 현물로 환산한 참고치를 hedge_ratio_implied_spot 에 둔다
    (적용값은 아니다 — 삼성重 은 이 참고치가 1.0 안팎, HD현대重 은 0.45 안팎으로 0.7 가정과 다르다는 것을 숨기지 않기 위해)."""
    qs = sorted(yq)
    latest = yq[qs[-1]] if qs else None
    hedge = (latest or {}).get("hedge") or {}
    usd_sell, rate = hedge.get("usd_sell_m"), hedge.get("avg_rate")
    closing = closing_total(latest)
    base = {"quarter": qs[-1] if qs else None, "usd_sell_m": usd_sell, "backlog_krw_m": closing, "hedge_rate": rate,
            "hedge_ratio_implied_spot": None, "implied_spot_rate": None, "implied_basis": None}
    if usd_sell and rate and closing:
        raw = usd_sell / (closing / rate)
        base.update(hedge_ratio=round(min(max(raw, 0.0), 1.0), 4), hedge_ratio_raw=round(raw, 4), kind="measured",
                    basis="usd_sell_m ÷ (기말 수주잔고 원화 ÷ 평균약정환율), %s 정기보고서 위험관리 절 — kship_page.yard_summary 방식" % qs[-1])
    else:
        why = "약정환율 미공시" if usd_sell else "통화선도 공시 없음"
        base.update(hedge_ratio=default_ratio, hedge_ratio_raw=None, kind="estimate",
                    basis="%s → 레퍼런스 SLS 시트의 HEDGE 70%% 가정. hedge_rate 는 계약별 수주시점 환율로 대체" % why)
        if usd_sell and closing and qs:
            spot_end, spot_src = fx_quarter_end(fx, qs[-1])
            if spot_end:
                base.update(hedge_ratio_implied_spot=round(usd_sell / (closing / spot_end), 4), implied_spot_rate=spot_end,
                            implied_basis=("usd_sell_m ÷ (기말 수주잔고 원화 ÷ %s 기말 원/달러 %.2f, %s) — 약정환율이 아닌 현물 환산 "
                                           "참고치(kind estimate). 적용 hedge_ratio 는 %.2f 가정 그대로" % (qs[-1], spot_end, spot_src, default_ratio)))
    return base


def _norm_seg(s):
    return re.sub(r"\s+|\(\*\)|\*", "", s or "")


def _marine_pred(stock):
    if stock == "010140":
        return lambda s: s == "조선해양"
    if stock == "042660":
        return lambda s: s.startswith("상선") or "특수선" in s
    if stock == "329180":
        return lambda s: s in ("조선", "해양플랜트")
    if stock == "439260":
        return lambda s: s == "선박"
    if stock == "097230":
        return lambda s: s in ("특수선", "상선", "신조선", "방산")
    return lambda s: s and not any(k in s for k in ("기타", "토건", "합계", "엔진", "건설", "플랜트"))


def reported_marine_3m(stock, yq):
    """정기보고서 부문 매출의 **3개월분**(백만원): 매출표(첫 열 = 당해 누계)가 있으면 그것을, 없으면 기납품 누계를
    쓴다. 누계 → Q1 은 그대로, 그 외는 직전 분기 누계와의 차분(Q4 = 연간 − 3Q 누계). 프로젝트 누계(HJ)는 같은 해
    차분만 쓰고 Q1 은 비운다(kship_forecast.recognition 과 같은 규칙). 반환 {q: {"value", "source", "segments"}}."""
    pred = _marine_pred(stock)
    style = DELIVERED_STYLE.get(stock, "ytd")
    cum = {}
    for q in sorted(yq):
        j = yq[q]
        rev = j.get("revenue") or {}
        val, segs, src = None, [], None
        if rev.get("rows") and (rev.get("cur") or "KRW") == "KRW":
            groups = collections.defaultdict(list)
            for r in rev["rows"]:
                groups[_norm_seg(r.get("seg"))].append(r)
            tot, ok = 0.0, False
            for seg in sorted(groups):
                if not seg or seg == "합계" or not pred(seg):
                    continue
                rs = groups[seg]
                t = [r for r in rs if r.get("kind") == "합계" and r.get("vals") and r["vals"][0] is not None]
                if t:
                    v = t[0]["vals"][0]
                else:
                    ch = [r["vals"][0] for r in rs if r.get("kind") != "합계" and r.get("vals") and r["vals"][0] is not None]
                    v = sum(ch) if ch else None
                if v is not None:
                    tot, ok = tot + v, True
                    segs.append(seg)
            if ok:
                val, src = tot, "revenue_table_ytd"
        if val is None:
            o = j.get("orders") or {}
            rows = [r for r in (o.get("rows") or []) if not r.get("total")]
            if rows and (o.get("cur") or "KRW") == "KRW":
                tot, ok = 0.0, False
                for r in sorted(rows, key=lambda r: _norm_seg(r.get("seg"))):
                    seg = _norm_seg(r.get("seg"))
                    if pred(seg) and r.get("delivered") is not None:
                        tot, ok = tot + r["delivered"], True
                        segs.append(seg)
                if ok:
                    val, src = tot, ("delivered_%s" % style)
        if val is not None:
            cum[q] = {"cum": val, "source": src, "segments": segs}
    out = {}
    for q in sorted(cum):
        c = cum[q]
        p = cum.get(q_prev(q))
        same_year = p is not None and q_prev(q)[:4] == q[:4]
        if c["source"] == "delivered_project_cumulative":
            v = (c["cum"] - p["cum"]) if same_year else None
        elif q.endswith("Q1"):
            v = c["cum"]
        else:
            v = (c["cum"] - p["cum"]) if same_year else None
        if v is not None:
            out[q] = {"value": round(v, 1), "source": c["source"], "segments": c["segments"], "cum": c["cum"]}
    return out


# ── 코호트 ──────────────────────────────────────────────────

def _median(xs):
    return statistics.median(xs) if xs else None


def cohorts(contracts):
    """원장 전체(공유 중복 제외)에서 척당 금액으로 ①~⑤ 를 매긴다. 반환 {rcp: {"cohort", ...근거}}, year_index."""
    elig = [c for c in contracts if c.get("type") not in (None, "OTHER") and c.get("ships") and c.get("amt_usd_m")
            and c.get("year") and not c.get("shared_owner")]
    cell = collections.defaultdict(list)
    type_all = collections.defaultdict(list)
    for c in elig:
        ps = c["amt_usd_m"] / c["ships"]
        cell[(c["type"], c["year"])].append(ps)
        type_all[c["type"]].append(ps)
    ratios = collections.defaultdict(list)
    for t in sorted(type_all):
        years = sorted(y for (tt, y) in cell if tt == t and len(cell[(tt, y)]) >= 2)
        if len(years) < 2:
            continue
        base = _median(cell[(t, years[0])])
        for y in years:
            ratios[y].append(_median(cell[(t, y)]) / base)
    year_index = {y: round(_median(ratios[y]), 4) for y in sorted(ratios)}
    out = {}
    for c in elig:
        t, y = c["type"], c["year"]
        ps = c["amt_usd_m"] / c["ships"]
        level = year_index.get(y, 1.0)
        base_grade = 2 if level < 0.90 else 3 if level < 1.10 else 4 if level < 1.25 else 5
        cell_n = len(cell[(t, y)])
        if cell_n >= 2:
            ref, ref_kind = _median(cell[(t, y)]), "type_year_median"
            rel = ps / ref
        else:
            ref, ref_kind = _median(type_all[t]), "type_all_median/year_index"
            rel = ps / ref / level if ref else 1.0
        adj = -1 if rel < 0.90 else 1 if rel > 1.10 else 0
        g = min(5, max(1, base_grade + adj))
        out[c["rcp"]] = {"cohort": COHORT_LABELS[g], "per_ship_usd_m": round(ps, 2), "ref_usd_m": round(ref, 2),
                         "ref_kind": ref_kind, "cell_n": cell_n, "rel": round(rel, 3), "year_index": level}
    return out, year_index


# ── 회사별 조립 ─────────────────────────────────────────────

def _duration_medians(rows):
    """선종별 계약기간(일) 중위 — 종료일 '-' 인 계약의 종료 추정에 쓴다."""
    d = collections.defaultdict(list)
    for r in rows:
        s, e = _date(r.get("start")) or _date(r.get("signed")), _date(r.get("end"))
        if s and e and e > s:
            d[r.get("type") or "OTHER"].append((e - s).days)
            d["_all"].append((e - s).days)
    return {k: int(_median(v)) for k, v in sorted(d.items())}


def prepare_contracts(rows, yards, fx, const):
    """원장 → 계약 레코드(달러화·기간 확정). 코호트·스케줄은 아직."""
    dur = _duration_medians(rows)
    out = []
    for r in sorted(rows, key=lambda r: (r["stock"], r["rcp"])):
        yq = yards.get(r["stock"]) or {}
        start = _date(r.get("start")) or _date(r.get("signed"))
        end = _date(r.get("end"))
        end_est = False
        if start and not end:
            days = dur.get(r.get("type") or "OTHER") or dur.get("_all")
            if days:
                end, end_est = start + datetime.timedelta(days=days), True
        rate, src = fx_at_sign(r, fx, yq, const)
        amt = r.get("amt_krw_m")
        signed = _date(r.get("signed")) or start
        c = {"rcp": r["rcp"], "stock": r["stock"], "name": r.get("name"), "type": r.get("type") or "OTHER",
             "ships": r.get("ships"), "amt_krw_m": amt, "fx_at_sign": round(rate, 2), "fx_source": src,
             "amt_usd_m": round(amt / rate, 3) if amt else None,
             "signed": r.get("signed"), "year": signed.year if signed else None,
             "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
             "end_estimated": end_est, "party_anon": bool(r.get("party_anon")), "party": r.get("party"),
             "option_hint": bool(r.get("option_hint")), "corrected": bool(r.get("corrected")),
             "supersedes": r.get("supersedes")}
        if r.get("shared_with"):
            c["shared_with"] = r["shared_with"]
        if r.get("shared_owner"):
            c["shared_owner"] = r["shared_owner"]
        if r["stock"] == HOLDING:
            c["sub_yard"] = sub_yard_of(r)
        out.append(c)
    # 반복건조(시리즈) 추정 표시 — kship_page.series_groups(est) 와 같은 묶음
    in_series = set()
    for g in series_groups([r for r in rows if r.get("type") not in (None, "OTHER")]):
        in_series.update(g["items"])
    for c in out:
        c["estimated_series"] = c["rcp"] in in_series or c["option_hint"]
    return out


def build(stock, contracts, cohort_map, year_index, yards, fx, curve, const, origin):
    """한 회사의 sls json 을 만든다. contracts 는 prepare_contracts 결과 전체(모든 회사)."""
    yq = yards.get(stock) or {}
    mine = [dict(c) for c in contracts if c["stock"] == stock]
    hedge = hedge_params(stock, yq, fx=fx)
    hr = hedge["hedge_ratio"]
    fx_cache = {}

    def spot(q):
        if q not in fx_cache:
            fx_cache[q] = fx_quarter(fx, q, const)
        return fx_cache[q]

    by_q = collections.defaultdict(lambda: {"usd_m": 0.0, "marine_usd_m": 0.0, "by_type": collections.defaultdict(float),
                                            "by_cohort": collections.defaultdict(float), "hedged_krw_m": 0.0,
                                            "marine_hedged_krw_m": 0.0, "_rate_w": 0.0, "_hrate_w": 0.0, "n_active": 0})
    warnings, skipped = [], []
    n_counted, n_shared_excluded = 0, 0
    for c in mine:
        s, e = _date(c["start"]), _date(c["end"])
        sched = schedule(s, e, c["amt_usd_m"], curve)
        c["schedule"] = round_schedule(sched, c["amt_usd_m"])
        c["curve"] = "linear_progress" if curve == "linear" else "s_curve"
        info = cohort_map.get(c["rcp"])
        c["cohort"] = info["cohort"] if info else None
        c["cohort_detail"] = info
        c["cohort_basis"] = ("amt_per_ship vs type-year median (contracts.json) × year_index; 신조선가 지수 미보유"
                             if info else "척수 없음 또는 금액·연도 없음 → 등급 없음")
        c["progress_at_origin"] = round(sum(v for q, v in sched.items() if q <= origin) / c["amt_usd_m"], 4) if sched and c["amt_usd_m"] else None
        c["remaining_usd_m_at_origin"] = round(sum(v for q, v in sched.items() if q > origin), 3) if sched else None
        if not sched:
            skipped.append({"rcp": c["rcp"], "why": "금액 없음" if not c["amt_usd_m"] else "기간 없음"})
            continue
        if c.get("shared_owner"):
            n_shared_excluded += 1
            c["counted"] = False
            continue
        c["counted"] = True
        n_counted += 1
        hedge_rate_c = hedge["hedge_rate"] or c["fx_at_sign"]
        marine = c["type"] != "OTHER"
        for q, usd in sched.items():
            sp, _ = spot(q)
            applied = hr * hedge_rate_c + (1.0 - hr) * sp
            b = by_q[q]
            b["usd_m"] += usd
            b["by_type"][c["type"]] += usd
            b["by_cohort"][c["cohort"] or "등급없음"] += usd
            b["hedged_krw_m"] += usd * applied
            b["_rate_w"] += usd * applied
            b["_hrate_w"] += usd * hedge_rate_c
            b["n_active"] += 1
            if marine:
                b["marine_usd_m"] += usd
                b["marine_hedged_krw_m"] += usd * applied
    by_quarter = collections.OrderedDict()
    for q in sorted(by_q):
        b = by_q[q]
        sp, sp_src = spot(q)
        graded = {k: v for k, v in b["by_cohort"].items() if k in COHORT_OPM}
        gsum = sum(graded.values())
        by_quarter[q] = {
            "usd_m": round(b["usd_m"], 3), "marine_usd_m": round(b["marine_usd_m"], 3),
            "by_type": collections.OrderedDict((k, round(v, 3)) for k, v in sorted(b["by_type"].items())),
            "by_cohort": collections.OrderedDict((k, round(v, 3)) for k, v in sorted(b["by_cohort"].items())),
            "hedged_krw_m": round(b["hedged_krw_m"], 1), "marine_hedged_krw_m": round(b["marine_hedged_krw_m"], 1),
            "applied_rate": round(b["_rate_w"] / b["usd_m"], 2) if b["usd_m"] else None,
            "hedge_ratio": hr, "hedge_rate": round(b["_hrate_w"] / b["usd_m"], 2) if b["usd_m"] else None,
            "spot_assumed": round(sp, 2), "spot_source": sp_src, "n_active": b["n_active"],
            "kind": "estimate", "past": q <= origin,
            "basis": "공시 계약기간 안 %s 배분 × 헤지 적용 환율" % ("선형 진행률" if curve == "linear" else "S-커브 진행률"),
            "target_opm": round(sum(v * COHORT_OPM[k] for k, v in graded.items()) / gsum, 4) if gsum else None,
            "graded_share": round(gsum / b["usd_m"], 4) if b["usd_m"] else None}
    by_year = collections.OrderedDict()
    for q, b in by_quarter.items():
        y = by_year.setdefault(q[:4], {"usd_m": 0.0, "marine_usd_m": 0.0, "hedged_krw_m": 0.0, "marine_hedged_krw_m": 0.0,
                                       "by_type": collections.defaultdict(float), "by_cohort": collections.defaultdict(float), "quarters": 0})
        for k in ("usd_m", "marine_usd_m", "hedged_krw_m", "marine_hedged_krw_m"):
            y[k] += b[k]
        for k, v in b["by_type"].items():
            y["by_type"][k] += v
        for k, v in b["by_cohort"].items():
            y["by_cohort"][k] += v
        y["quarters"] += 1
    for y in by_year.values():
        for k in ("usd_m", "marine_usd_m"):
            y[k] = round(y[k], 3)
        for k in ("hedged_krw_m", "marine_hedged_krw_m"):
            y[k] = round(y[k], 1)
        y["by_type"] = collections.OrderedDict((k, round(v, 3)) for k, v in sorted(y["by_type"].items()))
        y["by_cohort"] = collections.OrderedDict((k, round(v, 3)) for k, v in sorted(y["by_cohort"].items()))

    # 화해: 분기 SLS 원화(해양) vs 정기보고서 부문 매출 3개월분
    reported = reported_marine_3m(stock, yq)
    fin_is = _fin_is(stock)
    reconcile = collections.OrderedDict()
    for q in sorted(reported):
        if q > origin or q not in by_quarter:
            continue
        sls = by_quarter[q]["marine_hedged_krw_m"]
        rep = reported[q]["value"]
        # 교차검사: 부문 매출 3개월분이 연결 매출(fin)보다 1% 넘게 크면 부문표(내부거래 제거 전) 또는 파서 문제 — 표시만 하고 ratio 는 둔다
        cons_rev = ((fin_is or {}).get(q) or {}).get("매출액(수익)")
        exceeds = round((rep / cons_rev - 1.0) * 100, 2) if (cons_rev and rep > cons_rev * 1.01) else None
        issue = None
        if rep <= 0:
            issue = "보고 매출 3개월분이 0 이하(프로젝트 누계 차분에서 완료 계약이 표에서 빠진 경우) — 비교 불가"
        elif sls <= 0:
            issue = "그 분기에 진행 중인 원장 계약 없음 — 비교 불가"
        reconcile[q] = {"sls_krw_m": sls, "reported_segment_rev_m": rep, "reported_source": reported[q]["source"],
                        "segments": reported[q]["segments"],
                        "consolidated_rev_m": cons_rev, "exceeds_consolidated_pct": exceeds,
                        "ratio": round(sls / rep, 4) if issue is None else None, "issue": issue,
                        "note": "공시된 척당 계약(2024~)만 → 그 전 수주 물량·계약 미공시·반복건조·기타매출은 잔차"}
    used = [q for q in sorted(reconcile) if reconcile[q]["ratio"] is not None][-4:]
    med = _median([reconcile[q]["ratio"] for q in used]) if used else None
    # 잔고 커버리지: origin 분기말까지 수주된 계약의 잔여 스케줄(해양) vs 그 분기 정기보고서 해양 부문 기말잔고.
    # origin 뒤에 수주한 계약은 그 잔고에 없으므로 뺀다(대한조선 2026Q3 수주분이 2026Q2 잔고를 넘게 만들었다).
    latest_q = sorted(yq)[-1] if yq else None
    _, origin_end = q_bounds(origin)
    pred = _marine_pred(stock)
    marine_closing = None
    if latest_q:
        segs = [r for r in ((yq[latest_q].get("orders") or {}).get("rows") or []) if not r.get("total")]
        vals = [r["closing"] for r in segs if pred(_norm_seg(r.get("seg"))) and r.get("closing") is not None]
        marine_closing = sum(vals) if vals else None
    closing = closing_total(yq[latest_q]) if latest_q else None
    reported_segs = [_norm_seg(r.get("seg")) for r in segs] if latest_q else []
    # 원장 신규 vs 수주표 신규증감(연초 누계, 해양 부문): 두 공시의 계약 인식 기준(발효·선수금·환율·범위)이 같은지 보는 진단.
    # 대한조선은 원장 2025H2 1.41조 vs 수주표 FY2025 신규 0.69조 — 커버리지 > 1 의 배경이 여기 있다.
    ledger_vs_new = None
    if latest_q:
        new_vals = [r["new"] for r in segs if pred(_norm_seg(r.get("seg"))) and r.get("new") is not None]
        if new_vals and sum(new_vals) > 0:
            y0, (_, lq_end) = datetime.date(int(latest_q[:4]), 1, 1), q_bounds(latest_q)
            led_new = 0.0
            for c in mine:
                d = _date(c.get("signed")) or _date(c.get("start"))
                if c.get("counted") and c["type"] != "OTHER" and d and y0 <= d <= lq_end:
                    led_new += c["amt_krw_m"] or 0
            ledger_vs_new = {"quarter": latest_q, "ledger_new_krw_m": round(led_new, 1), "reported_new_krw_m": round(sum(new_vals), 1),
                             "ratio": round(led_new / sum(new_vals), 4),
                             "basis": "%s~%s 수주 해양 계약의 원장 원화 공시금액 ÷ 정기보고서 %s 해양 부문 신규증감(연초 누계, 환율효과 포함)"
                                      % (y0.isoformat(), lq_end.isoformat(), latest_q)}

    def _signed_by_origin(c):
        d = _date(c.get("signed")) or _date(c.get("start"))
        return d is not None and d <= origin_end
    def _remaining_krw(c):
        # 원장 원화 금액 × 미진행 비율 — 달러 왕복 환산(수주시점 환율 → 건조시점 spot)을 피해 공시 잔고와 같은 원화 장부 기준
        return (c["amt_krw_m"] or 0) * (1.0 - (c["progress_at_origin"] or 0))
    cands = [c for c in mine if c.get("counted") and _signed_by_origin(c)]
    remaining_marine_usd = sum(c["remaining_usd_m_at_origin"] or 0 for c in cands if c["type"] != "OTHER")
    remaining_all_usd = sum(c["remaining_usd_m_at_origin"] or 0 for c in cands)
    remaining_marine_krw = sum(_remaining_krw(c) for c in cands if c["type"] != "OTHER")
    remaining_all_krw = sum(_remaining_krw(c) for c in cands)
    backlog_cov = (remaining_marine_krw / marine_closing) if marine_closing else None
    backlog_cov_all = (remaining_all_krw / closing) if closing else None
    reconcile_summary = {
        "definition": "ratio = SLS 해양 원화(헤지 적용) ÷ 정기보고서 해양 부문 매출 3개월분. scale_to_reported = 1/ratio (모델: 매출조선 = SLS 원화 × scale)",
        "quarters_used": used, "median_ratio_4q": round(med, 4) if med else None,
        "median_scale_to_reported_4q": round(1.0 / med, 4) if med else None,
        "backlog_coverage_at_origin": round(backlog_cov, 4) if backlog_cov is not None else None,
        "backlog_coverage_basis": "%s 분기말까지 수주된 해양 계약의 원장 원화 금액 × 미진행 비율 ÷ 정기보고서 %s 해양 부문 기말잔고 원화 (환산 없음)" % (origin, latest_q or "—"),
        "backlog_coverage_all_segments": round(backlog_cov_all, 4) if backlog_cov_all is not None else None,
        "remaining_usd_m_at_origin": round(remaining_all_usd, 3), "remaining_marine_usd_m_at_origin": round(remaining_marine_usd, 3),
        "remaining_krw_m_at_origin": round(remaining_all_krw, 1), "remaining_marine_krw_m_at_origin": round(remaining_marine_krw, 1),
        "reported_backlog_krw_m": closing, "reported_marine_backlog_krw_m": marine_closing,
        "reported_backlog_segments": reported_segs, "ledger_vs_reported_new": ledger_vs_new,
        "warning": "원장은 2024~ 공시분 — 과거 분기 ratio 는 그 전 수주 물량이 빠져 낮다. 미래 구간 배율은 backlog_coverage 쪽이 덜 편향된다."}

    # 타겟 OPM + 캘리브레이션 자리(실측 OPM 은 assets/fin 이 있어야 — 없으면 null)
    target_opm = collections.OrderedDict()
    for q, b in by_quarter.items():
        if b["target_opm"] is not None:
            target_opm[q] = {"opm": b["target_opm"], "graded_share": b["graded_share"],
                             "basis": "cohort mix × cohort OPM table (assumption: ①−5% ②0 ③5 ④10 ⑤15)"}
    calib = calibration(stock, target_opm, origin, fin_is)

    total_window = [q for q in q_range(*FORECAST_WINDOW) if q in by_quarter]
    warnings.append("종료일 = 마지막 호선 인도 예정; 진행률 매출 분기는 계약기간 안에 선형 배분(가정)")
    if stock == HOLDING:
        warnings.append("HD한국조선해양과 HD현대重 동일 계약 %d건 — shared_owner=329180 로 표시하고 이 파일의 합계에서 제외(합산 금지)" % n_shared_excluded)
    if stock == HOLDING_SHARES_WITH:
        n_sh = sum(1 for c in mine if c.get("shared_with"))
        warnings.append("HD한국조선해양(009540) 공시와 동일 계약 %d건(shared_with) — 두 파일을 합산하지 말 것" % n_sh)
    if hedge["kind"] == "estimate":
        warnings.append("헤지비율 0.7 은 가정(%s)" % hedge["basis"])
        imp = hedge.get("hedge_ratio_implied_spot")
        if imp is not None and abs(imp - hr) > 0.15:
            warnings.append("공시 통화선도 매도 명목액 %.0f백만$ 을 현물(%s 기말 %.2f원)로 잔고 대비 환산하면 %.2f — 가정 %.2f 과 %+.2f 차이. "
                            "약정환율 미공시라 적용하지 않음(참고치 hedge.hedge_ratio_implied_spot; 채택은 사용자 결정)"
                            % (hedge["usd_sell_m"], hedge["quarter"], hedge["implied_spot_rate"], imp, hr, imp - hr))
    # 코호트 방향 — 레퍼런스(HD현대미포 SLS 시트: 2025~ 물량 100% ⑤초호황)와 견줘 원장 내부 상대 등급의 한계를 적는다
    recent = collections.Counter()
    for c in mine:
        if c.get("counted") and c.get("cohort") and c.get("year") and c["year"] >= 2025:
            recent[c["cohort"]] += c["amt_usd_m"] or 0
    tot_recent = sum(recent.values())
    if tot_recent:
        top = max(sorted(recent.items()), key=lambda kv: kv[1])[0]
        mix = ", ".join("%s %.0f%%" % (k, 100 * v / tot_recent) for k, v in sorted(recent.items()))
        warnings.append("코호트는 원장 내부 상대 등급(신조선가 지수 없음): 2025~ 수주 물량(백만$) 판정 %s — 최다 %s. 레퍼런스 HD현대미포 SLS 는 "
                        "2025~ 물량을 100%% ⑤초호황으로 두어 방향이 다르다(2021 이후 절대 호황 수준 미반영). 타겟 OPM 은 회사 calibrated_shift 로 "
                        "실측 OPM 에 맞추고, 외부 지수 도입은 사용자 결정" % (mix, top))
    else:
        warnings.append("코호트는 원장 내부 상대 등급(신조선가 지수 없음) — 2025~ 등급 있는 수주 없음. 레퍼런스 HD현대미포 SLS(2025~ 100% ⑤초호황)와 "
                        "직접 비교 불가; 2021 이후 절대 호황 수준 미반영")
    if not fx:
        warnings.append("assets/fx.json 없음 — 수주시점·건조시점 환율은 공시 고시환율/약정환율/상수 %g 로 대체(fx_source 참조)" % const)
    if skipped:
        warnings.append("스케줄 불가 %d건(금액·기간 없음) — contracts[].schedule 비움" % len(skipped))
    n_end_est = sum(1 for c in mine if c["end_estimated"])
    if n_end_est:
        warnings.append("종료일 '-' %d건은 같은 선종 계약기간 중위로 종료 추정(end_estimated)" % n_end_est)
    if not reconcile:
        warnings.append("정기보고서 부문 매출(3개월분)을 만들 수 없어 화해 없음")
    if backlog_cov is not None and backlog_cov > 1.0:
        warnings.append("원장 잔여(%.0f억) > 공시 해양 기말잔고(%.0f억), 커버리지 %.2f — 선형 진행 가정이 실제 진행보다 느리거나 "
                        "공시 잔고 범위(환율·취소·범위)가 다르다. 모델은 배율 1 을 상한으로 볼 것"
                        % (remaining_marine_krw / 100, marine_closing / 100, backlog_cov))
    if backlog_cov_all is not None and backlog_cov_all > 1.0 and (backlog_cov is None or backlog_cov <= 1.0):
        warnings.append("비해양(OTHER: 공사·플랜트 등) 포함 원장 잔여 %.0f억 > 정기보고서 수주표 기말잔고 %.0f억(전부문 커버리지 %.2f) — "
                        "수주표는 조선 부문 범위(%s)만 담아 비교 범위가 다르다. backlog_coverage_all_segments 는 배율로 쓰지 말 것"
                        % (remaining_all_krw / 100, closing / 100, backlog_cov_all, "·".join(reported_segs) or "—"))
    over = [q for q in reconcile if reconcile[q]["exceeds_consolidated_pct"] is not None]
    if over:
        warnings.append("정기보고서 부문 매출 3개월분 > 연결 매출(fin) %d분기(%s; 최대 +%.1f%%) — 부문표가 내부거래 제거 전이거나 파서 문제(yards 레인). "
                        "reconcile[q].exceeds_consolidated_pct 에 표시, ratio 는 그대로"
                        % (len(over), ", ".join(over[-4:]), max(reconcile[q]["exceeds_consolidated_pct"] for q in over)))
    if ledger_vs_new and not (0.75 <= ledger_vs_new["ratio"] <= 1.25):
        warnings.append("원장 신규 %.0f억 vs 수주표 신규증감 %.0f억(%s 연초 누계) — 비율 %.2f: 두 공시의 계약 인식 기준(발효·선수금·환율·범위)이 "
                        "다르다. backlog_coverage 해석 시 참고(reconcile_summary.ledger_vs_reported_new)"
                        % (ledger_vs_new["ledger_new_krw_m"] / 100, ledger_vs_new["reported_new_krw_m"] / 100, ledger_vs_new["quarter"], ledger_vs_new["ratio"]))

    fx_sources = collections.Counter(c["fx_source"] for c in mine)
    return collections.OrderedDict([
        ("stock", stock), ("name", NAMES.get(stock, stock)), ("origin", origin),
        ("unit", "USD_million | KRW_million"), ("curve", "linear_progress" if curve == "linear" else "s_curve"),
        ("built_at", datetime.date.today().isoformat()),
        ("counts", {"contracts": len(mine), "counted": n_counted, "shared_excluded": n_shared_excluded,
                    "skipped": len(skipped), "end_estimated": n_end_est,
                    "estimated_series": sum(1 for c in mine if c["estimated_series"]),
                    "schedule_quarters": len(by_quarter),
                    "forecast_window": {"from": FORECAST_WINDOW[0], "to": FORECAST_WINDOW[1], "quarters": len(total_window),
                                        "usd_m": round(sum(by_quarter[q]["usd_m"] for q in total_window), 3),
                                        "hedged_krw_m": round(sum(by_quarter[q]["hedged_krw_m"] for q in total_window), 1)}}),
        ("fx", {"source_counts": collections.OrderedDict(sorted(fx_sources.items())), "fx_json": bool(fx), "const": const,
                "spot_policy": "건조시점 환율 = fx.json quarters/forward, 없으면 상수(가정)"}),
        ("hedge", hedge),
        ("cohort_method", COHORT_METHOD), ("cohort_opm_table", COHORT_OPM), ("year_index", year_index),
        ("contracts", mine), ("by_quarter", by_quarter), ("by_year", by_year),
        ("reconcile", reconcile), ("reconcile_summary", reconcile_summary),
        ("target_opm", target_opm), ("calibration", calib),
        ("skipped", skipped), ("warnings", warnings)])


def _fin_is(stock):
    """assets/fin/<stock>.json 의 손익(3개월분, 백만원) — 연결 우선, 없으면 별도. 파일이 없거나 못 읽으면 None."""
    p = os.path.join(ASSETS, "fin", "%s.json" % stock)
    if not os.path.exists(p):
        return None
    try:
        fin = load_asset(os.path.join("fin", "%s.json" % stock))
    except (OSError, ValueError):
        return None
    return ((fin.get("cons") or {}).get("is")) or ((fin.get("sep") or {}).get("is")) or {}


def calibration(stock, target_opm, origin, is_=None):
    """회사 실측 OPM(assets/fin/<stock>.json cons.is 영업이익/매출액, **회사 전체 — 부문 아님**) − 타겟 OPM 의 최근 4분기 중위
    = calibrated_shift. fin 이 아직 없으면 null 로 자리만 둔다(yards_cache 에는 부문 영업이익이 없다)."""
    out = {"calibrated_shift": None, "actual_opm": {}, "basis": "fin 미수집 — yards_cache 에 부문 OP 없음 → 캘리브레이션 보류"}
    if is_ is None:
        is_ = _fin_is(stock)
    if is_ is None:
        return out
    diffs = []
    for q in sorted(is_):
        rev, op = is_[q].get("매출액(수익)"), is_[q].get("영업이익")
        if rev and op is not None and q <= origin:
            a = op / rev
            out["actual_opm"][q] = round(a, 4)
            if q in target_opm:
                diffs.append((q, a - target_opm[q]["opm"]))
    used = diffs[-4:]
    if used:
        out["calibrated_shift"] = round(_median([d for _, d in used]), 4)
        out["quarters_used"] = [q for q, _ in used]
        out["basis"] = "실측 OPM(fin cons.is 영업이익/매출액, 회사 전체 — 부문 아님) − 타겟 OPM, 최근 %d분기 중위" % len(used)
    else:
        out["basis"] = "fin 있음, 겹치는 분기 없음"
    return out


# ── 실행 ────────────────────────────────────────────────────

def run(stocks, curve="linear", const=FX_CONST, origin=None, write=True):
    ledger = load_asset("contracts.json")["rows"]
    rows, dropped = apply_supersedes([dict(r) for r in ledger])
    pairs = mark_shared(rows)
    yards = load_yards()
    fx = load_fx()
    origin = origin or max((max(qs) for qs in yards.values() if qs), default="2026Q2")
    contracts = prepare_contracts(rows, yards, fx, const)
    cohort_map, year_index = cohorts(contracts)
    outs = {}
    for stock in stocks:
        o = build(stock, contracts, cohort_map, year_index, yards, fx, curve, const, origin)
        o["dropped_superseded"] = dropped
        if stock in (HOLDING, HOLDING_SHARES_WITH):
            o["shared_pairs"] = [{"holding_rcp": a, "yard_rcp": b} for a, b in pairs]
        outs[stock] = o
        if write:
            os.makedirs(SLS_DIR, exist_ok=True)
            write_asset(os.path.join("sls", "%s.json" % stock), o)
    if write:
        write_asset(os.path.join("sls", "summary.json"), summary(outs, origin, curve, const, dropped, pairs))
    return outs


def summary(outs, origin, curve, const, dropped, pairs):
    rows = []
    for stock in sorted(outs):
        o = outs[stock]
        rs = o["reconcile_summary"]
        rows.append(collections.OrderedDict([
            ("stock", stock), ("name", o["name"]), ("contracts", o["counts"]["contracts"]), ("counted", o["counts"]["counted"]),
            ("shared_excluded", o["counts"]["shared_excluded"]), ("schedule_quarters", o["counts"]["schedule_quarters"]),
            ("window_usd_m", o["counts"]["forecast_window"]["usd_m"]), ("window_hedged_krw_m", o["counts"]["forecast_window"]["hedged_krw_m"]),
            ("median_ratio_4q", rs["median_ratio_4q"]), ("backlog_coverage_at_origin", rs["backlog_coverage_at_origin"]),
            ("hedge_ratio", o["hedge"]["hedge_ratio"]), ("hedge_kind", o["hedge"]["kind"]),
            ("calibrated_shift", o["calibration"]["calibrated_shift"])]))
    return collections.OrderedDict([("origin", origin), ("curve", curve), ("fx_const", const), ("window", list(FORECAST_WINDOW)),
                                    ("dropped_superseded", dropped), ("shared_pairs_n", len(pairs)), ("rows", rows)])


def report(outs):
    print("%-7s %-10s %4s %4s %4s %5s %12s %14s %8s %8s %6s" % ("stock", "name", "n", "cnt", "shr", "nQ", "26Q3-28Q4 M$", "원화(백만)", "ratio4q", "bklgcov", "hedge"))
    for stock in sorted(outs):
        o = outs[stock]
        w, rs = o["counts"]["forecast_window"], o["reconcile_summary"]
        print("%-7s %-10s %4d %4d %4d %5d %12.1f %14.0f %8s %8s %6s" % (
            stock, o["name"], o["counts"]["contracts"], o["counts"]["counted"], o["counts"]["shared_excluded"],
            o["counts"]["schedule_quarters"], w["usd_m"], w["hedged_krw_m"],
            ("%.3f" % rs["median_ratio_4q"]) if rs["median_ratio_4q"] is not None else "—",
            ("%.3f" % rs["backlog_coverage_at_origin"]) if rs["backlog_coverage_at_origin"] is not None else "—",
            "%.2f%s" % (o["hedge"]["hedge_ratio"], "m" if o["hedge"]["kind"] == "measured" else "e")))
        for q in sorted(o["reconcile"]):
            r = o["reconcile"][q]
            print("    %s sls %10.0f  reported %10.0f  ratio %s  (%s)" % (q, r["sls_krw_m"], r["reported_segment_rev_m"],
                  ("%.3f" % r["ratio"]) if r["ratio"] is not None else "—", r["reported_source"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="조선사 5 + 지주 1")
    ap.add_argument("--stock", action="append", default=[])
    ap.add_argument("--curve", choices=("linear", "s_curve"), default="linear")
    ap.add_argument("--spot", type=float, default=FX_CONST, help="fx.json 이 없을 때 쓰는 원/달러 상수")
    ap.add_argument("--origin", default=None, help="기준 분기(기본: yards_cache 최신)")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않는다")
    a = ap.parse_args(argv)
    stocks = a.stock or (YARDS + [HOLDING] if a.all else [])
    if not stocks:
        ap.error("--all 또는 --stock")
    outs = run(stocks, curve=a.curve, const=a.spot, origin=a.origin, write=not a.dry_run)
    if a.report:
        report(outs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
