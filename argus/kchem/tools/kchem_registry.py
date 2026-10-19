#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kchem_registry — 화학 스프레드 레지스트리.

ARGUS 원장의 스프레드는 이름 문자열(`제품-원료 스프레드(지역)`)뿐이고 산식·계수·참조 지역은
데이터 어디에도 없다. 이 모듈은 이름을 분해하고, 원장 관측치(connections.js 의 주간 observations)로
`스프레드 = 제품 − Σ kᵢ × 원료ᵢ` 의 kᵢ 를 **최소제곱으로 역산**한다. 원장 xlsm 의 수식을 본 것이
아니므로 결과는 전부 '역산 추정' 이며, 재현되지 않는 것은 그대로 '미재현' 으로 남긴다(fail-closed).

판정 규칙(LOGIC.md §2 와 같아야 한다):
  · 적합 창 = 스프레드·제품·원료 관측이 모두 있는 공통 날짜(최대 104주), 최소 MIN_POINTS 개.
  · 절편 없는 최소제곱 → |잔차| > TOL_ABS 인 날짜를 빼고 다시 적합(2회). 이상치 날짜는 outliers 로 남긴다.
  · 재현 = 전체 날짜 중 |잔차| ≤ TOL_ABS 인 비율이 MIN_FRAC 이상이고, 마지막 주가 안에 들며 마지막 4주 중 3주 이상이 안에 든다
    (원장에 한 주짜리 결측·정정이 실제로 있다 — 2026-08-10 주 다수).
  · 전체 창에서 안 되면 마지막 RECENT 주만으로 다시 본다 — 거기서 재현되면 `formula_changed`
    (원장 산식이 창 안에서 바뀜) 로 표시하고 regime_start(그 산식이 성립하는 첫 주)를 적는다.
  · 참조 지역은 같은 지역 → 일본(나프타) → 한국 → … 순으로 후보를 전부 적합해 가장 잘 맞는 것.
  · 이름의 원료만으로 안 맞으면 composite_extra_feeds(ABS+AN, SBR+SM …)를 더해 보고, 그래도 안 되면
    probe_feeds(나프타 일본·에틸렌·프로필렌·벤젠·SM·에탄)로 탐침 — 맞으면 `feed_mismatch`(이름과 다른 원료)
    또는 `feed_unspecified`(이름에 원료 없음).
  · 제품 가격이 스프레드보다 먼저 끊겼는데 이후 스프레드가 −Σk×원료 와 같으면 `missing_product_as_zero`.
출력: tools/assets/registry.json (정규화 JSON) — 빌드 시각 없음, 입력 fingerprint 만.
"""
import datetime
import json
import re
import sys

from kchem_lib import load_asset, write_asset
import kchem_inputs

TOL_ABS = 1.5          # USD/MT — 재현 판정의 안쪽 기준(근사 허용 상한). 실측 재현은 전부 잔차 < 0.01 이라 등급을 따로 둔다
EXACT_TOL = 0.01       # 안쪽 최대 잔차가 이 이하면 '정확 재현'(exact), TOL_ABS 이하면 '근사 재현'(approx)
CRACK_C = 1000.0 / 108.0   # 나프타 USD/MT → USD/bbl (1 MT ≈ 9.2593 bbl). 원유 크랙 = 나프타/c − k×Dubai($/bbl)
EPISODE_MIN = 8        # 이탈 주가 이만큼 이어지고 다시 기준 k 로 돌아오면 '일시 에피소드'(진단 전용 — 재현 수에 넣지 않음)
LIVE_GATE = {"hit": 0.70, "r": 0.60, "min_hold": 8, "hold_frac": 0.3}   # 프록시 '정지 후 방향' 표시 게이트(홀드아웃)
EPISODE_DK = 0.1       # 주별 implied-k 가 기준(중앙값)에서 이만큼 벗어나면 이탈 주
MIN_POINTS = 24        # 반년 미만 겹침으로는 계수를 단정하지 않는다
MIN_FRAC = 0.9         # 이상치 주(원장 단주 결측·정정)를 10% 까지 허용
RECENT = 26            # 산식 변경 탐지용 최근 창(주)
STALE_AFTER = {"D": 7, "W": 14, "T": 20, "M": 45, "Q": 120}
NAME_RE = re.compile(r"^(?P<lhs>.+?) (?P<crack>크랙 )?스프레드\((?P<region>[^)]+)\)$")
PRICE_RE = re.compile(r"^(?P<prod>.+?) 가격\((?P<region>[^)]+)\)$")


# ── 이름 분해 ───────────────────────────────────────────────

def split_last_dash(s):
    """괄호 밖의 마지막 '-' 로 (제품, 원료) 를 나눈다. 'S-SBR-BD' → ('S-SBR','BD'), 'PS(GP)-SM' → ('PS(GP)','SM')."""
    depth, idx = 0, -1
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "-" and depth == 0:
            idx = i
    return (s[:idx], s[idx + 1:]) if idx >= 0 else (s, None)


def parse_name(name):
    """스프레드/가격 이름 → {kind, product, feeds, region}. 못 읽으면 kind=None."""
    m = NAME_RE.match(name)
    if m:
        product, feed = split_last_dash(m.group("lhs"))
        feeds = [t for t in feed.split("&")] if feed else []
        return {"kind": "crack" if m.group("crack") else "spread", "product": product,
                "feeds": feeds, "region": m.group("region")}
    m = PRICE_RE.match(name)
    if m:
        return {"kind": "price", "product": m.group("prod"), "feeds": [], "region": m.group("region")}
    return {"kind": None, "product": None, "feeds": [], "region": None}


# ── 최소제곱 ────────────────────────────────────────────────

def solve(A, b):
    """작은 정방 행렬 가우스 소거(부분 피벗). 특이면 None."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def lstsq(X, y):
    """y ≈ X·k (절편 없음). X: 행 목록."""
    n = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) for j in range(n)] for i in range(n)]
    b = [sum(r[i] * y[t] for t, r in enumerate(X)) for i in range(n)]
    return solve(A, b)


def common_dates(S, P, feeds):
    sets = [set(S), set(P)] + [set(f) for f in feeds]
    dates = sorted(set.intersection(*sets))
    return [d for d in dates if S[d] is not None and P[d] is not None and all(f[d] is not None for f in feeds)]


def fit(S, P, feeds, dates=None, min_points=MIN_POINTS):
    """S,P: {date: value}, feeds: [{date: value}]. 돌려줌: {k, n, dates} 또는 None."""
    if not feeds:
        return None
    dates = list(dates) if dates is not None else common_dates(S, P, feeds)
    if len(dates) < min_points:
        return None
    X = [[float(f[d]) for f in feeds] for d in dates]
    y = [float(P[d]) - float(S[d]) for d in dates]
    k = lstsq(X, y)
    if k is None:
        return None
    return {"k": k, "n": len(dates), "dates": dates}


def residuals(k, S, P, feeds, dates):
    return [float(S[d]) - (float(P[d]) - sum(k[i] * float(feeds[i][d]) for i in range(len(feeds)))) for d in dates]


def carry_weeks(S, P, feeds):
    """원장 이월(carry-forward) 주 — 스프레드·제품 값이 전주와 같은데 원료만 바뀐 주.

    스프레드가 실제로는 갱신되지 않고 전주 값이 이어 쓰인 것이라 산식 적합에서 뺀다
    (Crude C4−납사 2026-08-03·08-17·08-24 등). 돌려줌: 이월 주 날짜 목록."""
    ds = [d for d in sorted(S) if S[d] is not None and P.get(d) is not None]
    out = []
    for a, b in zip(ds, ds[1:]):
        if S[a] == S[b] and P[a] == P[b] and any(
                f.get(a) is not None and f.get(b) is not None and f[a] != f[b] for f in feeds):
            out.append(b)
    return out


def fit_dates(S, P, feeds):
    """적합 창 = 공통 관측 날짜에서 이월 주를 뺀 것."""
    carry = set(carry_weeks(S, P, feeds))
    return [d for d in common_dates(S, P, feeds) if d not in carry]


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _robust_from(start, S, P, feeds, all_dates):
    """시작 계수에서 이상치를 걷어내며 2회 재적합."""
    cur, keep = start, all_dates
    for _ in range(2):
        res = residuals(cur["k"], S, P, feeds, keep)
        inl = [d for d, r in zip(keep, res) if abs(r) <= TOL_ABS]
        if len(inl) == len(keep) or len(inl) < MIN_POINTS:
            break
        keep = inl
        nxt = fit(S, P, feeds, keep)
        if nxt is None:
            break
        cur = nxt
    return cur


def robust_fit(S, P, feeds, dates=None):
    """이상치를 걷어내며 2회 재적합. 돌려줌: {k, n, n_in, frac, resid_max_in, outliers, dates, last4_ok, reproduced}.

    시작점은 두 개다 — 전체 최소제곱, 그리고 단일 원료면 주별 implied-k 의 **중앙값**.
    최소제곱 시작은 이상치 주가 많으면 안쪽이 MIN_POINTS 미만으로 무너져 포기하는데(페놀−벤젠 미국·인도,
    LDPE−에틸렌 유럽), 중앙값 시작은 이상치에 끌리지 않는다. 더 잘 맞는 쪽을 쓴다(재현 > 안쪽 비율 > 잔차)."""
    base = fit(S, P, feeds, dates)
    if base is None:
        return None
    all_dates = base["dates"]
    starts = [base]
    if len(feeds) == 1:
        ks = [(float(P[d]) - float(S[d])) / float(feeds[0][d]) for d in all_dates if abs(float(feeds[0][d])) > 1e-9]
        if ks:
            starts.append({"k": [_median(ks)], "n": len(all_dates), "dates": all_dates})
    best = None
    for st in starts:
        r = _evaluate(_robust_from(st, S, P, feeds, all_dates)["k"], S, P, feeds, all_dates)
        key = (not r["reproduced"], -r["frac"], round(r["resid_rms"], 9))
        if best is None or key < best[0]:
            best = (key, r)
    return best[1]


def _evaluate(k, S, P, feeds, all_dates):
    res = residuals(k, S, P, feeds, all_dates)
    inliers = [d for d, r in zip(all_dates, res) if abs(r) <= TOL_ABS]
    outliers = [d for d, r in zip(all_dates, res) if abs(r) > TOL_ABS]
    in_res = [abs(r) for r in res if abs(r) <= TOL_ABS]
    inl_set = set(inliers)
    last4_ok = (all_dates[-1] in inl_set) and sum(1 for d in all_dates[-4:] if d in inl_set) >= 3
    frac = len(inliers) / float(len(all_dates))
    rms = (sum(r * r for r in res) / len(res)) ** 0.5
    return {"k": k, "n": len(all_dates), "n_in": len(inliers), "frac": frac,
            "resid_max_in": max(in_res) if in_res else None, "resid_max_all": max(abs(r) for r in res),
            "resid_rms": rms, "outliers": outliers, "dates": all_dates, "last4_ok": last4_ok,
            "reproduced": frac >= MIN_FRAC and last4_ok}


def regime_fit(S, P, feeds):
    """전체 창에서 안 맞을 때 — 최근 RECENT 주로 적합해 성립하면 그 산식이 시작된 주를 찾는다."""
    dates = fit_dates(S, P, feeds)
    if len(dates) < RECENT:
        return None
    r = robust_fit(S, P, feeds, dates[-RECENT:])
    if r is None or not r["reproduced"]:
        return None
    res = residuals(r["k"], S, P, feeds, dates)
    # 끝에서부터 거슬러 올라가며 연속 이상치 3주를 만나면 멈춘다 → 그 뒤가 현재 산식의 구간
    start_idx, bad_run = len(dates) - 1, 0
    for i in range(len(dates) - 1, -1, -1):
        if abs(res[i]) <= TOL_ABS:
            bad_run = 0
            start_idx = i
        else:
            bad_run += 1
            if bad_run >= 3:
                break
    regime = dates[start_idx:]
    rr = robust_fit(S, P, feeds, regime)
    if rr is None or not rr["reproduced"]:
        return None
    rr["regime_start"] = regime[0]
    rr["full_n"] = len(dates)
    return rr


def episode_diag(S, P, feed):
    """일시 이탈(에피소드) 진단 — 재현 판정이 아니라 **설명**이다. 단일 원료만.

    주별 implied-k 의 중앙값을 기준 k 로 두고 |k_t − 기준| > EPISODE_DK 인 주를 이탈 주로 본다. 이탈 주가 한 덩어리로
    EPISODE_MIN 주 이상 이어지고 마지막 4주가 기준으로 돌아와 있으면 '에피소드 후 복귀'다(영구 산식 변경도, 상수 잔차도 아님).
    실측: PC−BPA(한국) k 0.93 → 2026-02~07 0.45~0.72 이탈 → 0.93 복귀 · PPG−PO(한국) ~1.05 → 2026-02~07 0.77 → 복귀.
    에피소드 밖이 기준 k 로 재현되는지도 함께 적는다(PPG−PO 는 밖도 1.04~1.06 로 흔들려 재현 안 됨)."""
    dates = fit_dates(S, P, [feed])
    kt = [(d, (float(P[d]) - float(S[d])) / float(feed[d])) for d in dates if abs(float(feed[d])) > 1e-9]
    if len(kt) < MIN_POINTS:
        return None
    base = _median([k for _, k in kt])
    exc = [abs(k - base) > EPISODE_DK for _, k in kt]
    if any(exc[-4:]):
        return None
    best, i = None, 0
    while i < len(exc):                      # 가장 긴 이탈 덩어리(사이에 정상 1주까지 허용)
        if not exc[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(exc) and (exc[j + 1] or (j + 2 < len(exc) and exc[j + 2])):
            j += 1
        if best is None or j - i > best[1] - best[0]:
            best = (i, j)
        i = j + 1
    if best is None or best[1] - best[0] + 1 < EPISODE_MIN:
        return None
    a, b = best
    inside = [k for (_, k), e in zip(kt[a:b + 1], exc[a:b + 1]) if e]
    outside_dates = [d for (d, _), e in zip(kt, exc) if not e]
    out_fit = robust_fit(S, P, [feed], outside_dates) if len(outside_dates) >= MIN_POINTS else None
    return {"start": kt[a][0], "end": kt[b][0], "n": b - a + 1, "base_k": round(base, 4),
            "k_min": round(min(inside), 4), "k_max": round(max(inside), 4),
            "isolated": sum(1 for (idx, e) in enumerate(exc) if e and not (a <= idx <= b)),
            "outside_reproduced": bool(out_fit and out_fit["reproduced"]),
            "outside_frac": round(out_fit["frac"], 4) if out_fit else None}


def leading_regime(S, P, feeds, r):
    """재현된 적합에서 창 **초반**에 다른 산식이 있었는지 — 끝에서 거슬러 올라가 연속 이상치 3주를 만나는 곳.

    중앙값 시작은 창 초반 몇 주의 다른 산식을 이상치로 흡수해 '재현' 으로 통과시킨다. 그 구간이 실제 산식 변경이면
    (앞부분이 절반 이상 이상치) regime_start 를 남긴다 — MEG−EO(대만) 2024-11-11."""
    dates = r["dates"]
    res = residuals(r["k"], S, P, feeds, dates)
    start_idx, bad_run = len(dates) - 1, 0
    for i in range(len(dates) - 1, -1, -1):
        if abs(res[i]) <= TOL_ABS:
            bad_run, start_idx = 0, i
        else:
            bad_run += 1
            if bad_run >= 3:
                break
    if start_idx < 3 or bad_run < 3:
        return None
    pre = res[:start_idx]
    if sum(1 for x in pre if abs(x) > TOL_ABS) < 0.5 * len(pre):
        return None
    return dates[start_idx]


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx < 1e-12 or sy < 1e-12:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _monthly(obs):
    """{date: v} → [(YYYY-MM, 그 달 마지막 값)]"""
    out = {}
    for d in sorted(obs):
        if obs[d] is not None:
            out[d[:7]] = float(obs[d])
    return sorted(out.items())


def _weekly_align(px, lg):
    """주간 프록시 날짜마다 ±3일 안의 원장 관측을 짝짓는다. → [(날짜, 프록시, 원장)]"""
    lg_dates = sorted(d for d, v in lg.items() if v is not None)
    out = []
    for d in sorted(px):
        if px[d] is None:
            continue
        dd = datetime.date.fromisoformat(d)
        near = [x for x in lg_dates if abs((datetime.date.fromisoformat(x) - dd).days) <= 3]
        if near:
            out.append((d, float(px[d]), float(lg[min(near, key=lambda x: abs((datetime.date.fromisoformat(x) - dd).days))])))
    return out


def proxy_check(px, lg, freq):
    """프록시 Δ% 가 원장 제품 가격 Δ% 의 방향을 맞추는가 — 홀드아웃 적중·상관. 월간은 시차 0/1 중 학습 구간 r 이 큰 쪽."""
    if freq == "M":
        pm, lm = dict(_monthly(px)), dict(_monthly(lg))
        keys = sorted(set(pm))
        best = None
        for lag in (0, 1):
            pairs = []
            for a, b in zip(keys, keys[1:]):
                la, lb = _shift_month(a, -lag), _shift_month(b, -lag)
                if la in lm and lb in lm and pm[a] and lm[la]:
                    pairs.append((b, pm[b] / pm[a] - 1.0, lm[lb] / lm[la] - 1.0))
            st = _split_stats(pairs)
            if st and (best is None or (st["r_train"] or -9) > (best["r_train"] or -9)):
                st["lag"] = lag
                best = st
        return best
    al = _weekly_align(px, lg)
    pairs = []
    for (d1, p1, l1), (d2, p2, l2) in zip(al, al[1:]):
        gap = (datetime.date.fromisoformat(d2) - datetime.date.fromisoformat(d1)).days
        if gap <= 10 and p1 and l1:
            pairs.append((d2, p2 / p1 - 1.0, l2 / l1 - 1.0))
    st = _split_stats(pairs)
    if st:
        st["lag"] = 0
    return st


def _shift_month(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) + k
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return "%04d-%02d" % (y, m)


def _split_stats(pairs):
    if len(pairs) < LIVE_GATE["min_hold"] * 2:
        return None
    nh = max(LIVE_GATE["min_hold"], int(round(len(pairs) * LIVE_GATE["hold_frac"])))
    tr, ho = pairs[:-nh], pairs[-nh:]

    def stats(ps):
        sg = [(a > 0) == (b > 0) for _, a, b in ps if abs(a) > 1e-9 and abs(b) > 1e-9]
        return (sum(sg) / float(len(sg)) if sg else None), _pearson([a for _, a, _ in ps], [b for _, _, b in ps])
    hit_tr, r_tr = stats(tr)
    hit_ho, r_ho = stats(ho)
    ok = (hit_ho is not None and r_ho is not None and len(ho) >= LIVE_GATE["min_hold"]
          and hit_ho >= LIVE_GATE["hit"] and r_ho >= LIVE_GATE["r"])
    rd = lambda x: None if x is None else round(x, 3)
    return {"n_pairs": len(pairs), "n_train": len(tr), "n_hold": len(ho), "hold_from": ho[0][0], "hold_to": ho[-1][0],
            "hit_train": rd(hit_tr), "r_train": rd(r_tr), "hit_hold": rd(hit_ho), "r_hold": rd(r_ho), "gate": bool(ok)}


def k_two_point(S, P, feeds, dates):
    """마지막 두 공통 날짜의 2시점 k (단일 원료일 때만, L1 보고서와 대조용)."""
    if len(feeds) != 1 or len(dates) < 2:
        return None
    out = []
    for d in dates[-2:]:
        f = float(feeds[0][d])
        if abs(f) < 1e-9:
            return None
        out.append((float(P[d]) - float(S[d])) / f)
    return out


def _fk(k):
    r = round(k, 2)
    return "%d" % round(r) if abs(r - round(r)) < 1e-9 else ("%.2f" % r).rstrip("0").rstrip(".")


def _count(it):
    out = {}
    for x in it:
        key = "null" if x is None else str(x)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


# ── 레지스트리 ───────────────────────────────────────────────

class Registry(object):
    def __init__(self, inputs, fingerprint, aliases=None):
        self.inp = inputs
        self.fp = fingerprint
        self.al = aliases or load_asset("aliases.json")
        self.argus = inputs["argus"]
        self.asof = datetime.date.fromisoformat(self.argus["asof"])
        conn = inputs["connections"]["rows"]
        self.conn = {r["sid"]: r for r in conn}
        self.by_name = {}
        for r in conn:
            self.by_name.setdefault(r["name"], r["sid"])
        self.obs_cache = {}
        self.map_items = {it["sid"]: it for it in inputs["data_map"]["items"]}
        self.chain_label = {c["id"]: c["label"] for c in self.argus["chains"]}
        self.chain_stocks = {c["id"]: c["stocks"] for c in self.argus["chains"]}
        self.chain_pos = {c["id"]: {"pos": c["pos"], "mom": c["mom"], "n": c["n"], "hunts": c["hunts"]} for c in self.argus["chains"]}

    # -- 관측치
    def obs(self, sid):
        if sid not in self.obs_cache:
            r = self.conn.get(sid)
            self.obs_cache[sid] = dict(r["observations"]) if r else None
        return self.obs_cache[sid]

    def sid_of(self, name_token, region):
        return self.by_name.get("%s %s" % (name_token, region))

    def region_p(self, region):
        return self.al["region_alias"].get(region, region)

    def regions_of(self, name_token):
        pre = name_token + " "
        return [n[len(pre):] for n in self.by_name if n.startswith(pre)]

    # -- 원료 후보
    def feed_candidates(self, token, region):
        """원료 토큰 → [(sid, ref_region, order)] 후보. 'sid:' 접두는 직접 지정."""
        names = self.al["feed_alias"].get(token)
        if not names:
            return []
        out = []
        for nm in names:
            if nm.startswith("sid:"):
                sid = nm[4:]
                if sid in self.conn:
                    out.append((sid, "직접", 0))
                continue
            for order, rr in enumerate(self.al["ref_region_order"]):
                rr2 = self.region_p(region) if rr == "$same" else rr
                sid = self.sid_of(nm, rr2)
                if sid and all(sid != o[0] for o in out):
                    out.append((sid, rr2, order))
        return out

    def _score(self, r, chosen):
        if r["reproduced"]:
            return (0, -r["frac"], round(r["resid_max_all"], 6), sum(c[2] for c in chosen))
        return (1, round(r["resid_rms"], 6), -r["frac"], sum(c[2] for c in chosen))

    def best_fit(self, S, P, feed_tokens, region):
        """원료 토큰별 후보 조합을 전부 적합해 가장 잘 맞는 것을 고른다 (재현 > 안쪽 비율 > 잔차 > 지역 순서)."""
        cands = [self.feed_candidates(t, region) for t in feed_tokens]
        if any(not c for c in cands):
            return None, None
        best = [None, None]

        def rec(i, chosen):
            if i == len(cands):
                feeds = [self.obs(c[0]) for c in chosen]
                if any(f is None for f in feeds):
                    return
                r = robust_fit(S, P, feeds, fit_dates(S, P, feeds))
                if r is None:
                    return
                if not r["reproduced"]:
                    rg = regime_fit(S, P, feeds)
                    if rg is not None:
                        r = rg
                key = self._score(r, chosen)
                if best[0] is None or key < best[0]:
                    best[0], best[1] = key, (r, list(chosen))
                return
            for c in cands[i]:
                rec(i + 1, chosen + [c])
        rec(0, [])
        return best[1] if best[1] else (None, None)

    # -- 행 하나
    def row_for(self, s, cat):
        name = s["name"]
        p = parse_name(name)
        sid = s["sid"]
        conn = self.conn.get(sid) or {}
        freq = conn.get("freq") or ("W" if sid.startswith("sp_") else None)
        last_date = s.get("last_date")
        days = (self.asof - datetime.date.fromisoformat(last_date)).days if last_date else None
        row = {
            "sid": sid, "name": name, "cat": cat, "chain": s.get("chain"), "unit": s.get("unit"),
            "sp": bool(s.get("sp")), "kind": None, "layer": None,
            "product": None, "product_sid": None, "feeds": [], "region": None, "formula": None,
            "formula_version": 1, "k_source": None, "fit": None, "reproduced": None, "flags": [],
            "freshness": s.get("freshness"), "last_date": last_date, "last": s.get("last"),
            "pos": s.get("pos"), "m4": s.get("m4"), "hunt": s.get("hunt") or [],
            "expected_cadence": freq, "stale_after_days": STALE_AFTER.get(freq), "days_since": days,
            "weeks_since": (days // 7) if days is not None else None,
            "lane": conn.get("lane"), "reason": conn.get("reason") or "", "basis_note": conn.get("basis") or "",
            "source": conn.get("source") or s.get("source"), "in_map": sid in self.map_items,
            "chain_est": None, "stocks": [], "cnfut": None,
            "grade": None, "unit_hint": None, "carry_weeks": [], "effective_last": None,
            "dup_of": None, "dup_group": None,
        }
        if sid.startswith("cf_"):
            row["kind"], row["layer"] = "proxy_cnfut", "proxy"
        elif sid.startswith("ppim_"):
            row["kind"], row["layer"] = "index", "index"
        elif p["kind"] == "price":
            row["kind"], row["layer"] = "price", "price"
            row["product"], row["region"] = p["product"], p["region"]
        elif p["kind"] in ("spread", "crack") and row["sp"]:
            row["kind"] = "spread"
            row["product"], row["region"] = p["product"], p["region"]
            self._fit_spread(row, p)
        else:
            row["kind"] = "other"
            row["flags"].append("name_unparsed")
        # 체인 추정 · 종목(체인 단위 라벨) · 中선물 프록시
        if not row["chain"] and row["product"] is not None:
            row["chain_est"] = self.al["chain_est"].get(row["product"])
        eff = row["chain"] or row["chain_est"]
        if eff:
            est = not row["chain"]
            row["stocks"] = [{"t": st["t"], "n": st["n"], "note": st.get("note", ""), "est": est}
                             for st in self.chain_stocks.get(eff, [])]
        if row["product"] is not None:
            cf = self.al["cnfut"].get(row["product"])
            if cf and cf in self.conn:
                c = self.conn[cf]
                row["cnfut"] = {"sid": cf, "name": c["name"], "last": c["last"], "last_date": c["last_date"],
                                "unit": c["unit"], "freshness": c["freshness"]}
        return row

    def _fit_spread(self, row, p):
        sid = row["sid"]
        product_name = self.al["product_alias"].get(p["product"])
        if product_name is None:
            row["flags"].append("product_alias_missing")
            row["reproduced"] = False
            return
        psid = self.sid_of(product_name, self.region_p(p["region"]))
        row["product_sid"] = psid
        S = self.obs(sid)
        P = self.obs(psid) if psid else None
        feed_tokens = list(p["feeds"])
        row["layer"] = ("crack" if p["kind"] == "crack" else
                        "composite" if len(feed_tokens) > 1 else
                        "integrated" if feed_tokens == ["납사"] and p["product"] != "납사" else
                        "step" if feed_tokens else "unknown")
        if not S or not P:
            row["flags"].append("product_series_missing" if not P else "spread_observations_missing")
            row["reproduced"] = False
            return
        r, sel = (None, None)
        P_fit = P
        if feed_tokens:
            r, sel = self.best_fit(S, P, feed_tokens, p["region"])
            if row["layer"] == "crack" and (r is None or not r["reproduced"]):
                # 원유 크랙은 USD/bbl 기준일 수 있다 — 나프타 USD/MT 를 bbl 로 환산해 다시 본다(납사−Dubai 일본 103/104)
                P_bbl = {d: (None if v is None else float(v) / CRACK_C) for d, v in P.items()}
                rb, selb = self.best_fit(S, P_bbl, feed_tokens, p["region"])
                if rb is not None and rb["reproduced"]:
                    r, sel, P_fit = rb, selb, P_bbl
                    row["unit_hint"] = "USD/bbl"
                    row["flags"].append("crack_usd_bbl")
            extra = self.al["composite_extra_feeds"].get(p["product"])
            if (r is None or not r["reproduced"]) and extra:
                r2, sel2 = self.best_fit(S, P, feed_tokens + extra, p["region"])
                if r2 is not None and r2["reproduced"]:
                    r, sel = r2, sel2
                    feed_tokens = feed_tokens + extra
                    row["flags"].append("composite_extra_feed")
                    if row["layer"] != "composite":
                        row["layer"] = "composite"
        reproduced = r is not None and r["reproduced"]
        if not reproduced:
            # 이름의 원료로 안 맞으면 흔한 원료로 탐침 — 맞으면 '이름과 다른 원료' 로 표시한다
            for pf in self.al["probe_feeds"]:
                if feed_tokens and pf["token"] in feed_tokens:
                    continue
                for rr in pf["regions"]:
                    rr2 = self.region_p(p["region"]) if rr == "$same" else rr
                    fsid = self.sid_of(pf["name"], rr2)
                    F = self.obs(fsid) if fsid else None
                    if not F:
                        continue
                    rp = robust_fit(S, P, [F], fit_dates(S, P, [F]))
                    if rp is not None and not rp["reproduced"]:
                        rp = regime_fit(S, P, [F]) or rp
                    if rp is not None and rp["reproduced"]:
                        r, sel, feed_tokens = rp, [(fsid, rr2, 99)], [pf["token"]]
                        row["flags"].append("feed_mismatch" if p["feeds"] else "feed_unspecified")
                        if row["layer"] == "unknown":
                            row["layer"] = "integrated" if pf["token"] == "납사" else "step"
                        reproduced = True
                        break
                if reproduced:
                    break
        row["reproduced"] = bool(reproduced)
        if r is not None and sel is not None:
            feeds_obs = [self.obs(c[0]) for c in sel]
            row["feeds"] = [{"token": feed_tokens[i], "sid": sel[i][0], "name": self.conn[sel[i][0]]["name"],
                             "ref_region": sel[i][1], "k": round(r["k"][i], 6)} for i in range(len(sel))]
            carry = carry_weeks(S, P_fit, feeds_obs)
            row["carry_weeks"] = carry
            s_dates = [d for d in sorted(S) if S[d] is not None]
            row["effective_last"] = next((d for d in reversed(s_dates) if d not in set(carry)), None)
            if carry and row["effective_last"] != (s_dates[-1] if s_dates else None):
                row["flags"].append("carry_forward")
            row["fit"] = {"n": r["n"], "n_in": r["n_in"], "frac": round(r["frac"], 4),
                          "resid_max_in": (round(r["resid_max_in"], 4) if r["resid_max_in"] is not None else None),
                          "resid_max_all": round(r["resid_max_all"], 4), "resid_rms": round(r["resid_rms"], 4),
                          "window": [r["dates"][0], r["dates"][-1]], "outliers": r["outliers"][:12],
                          "k_2pt": [round(x, 4) for x in (k_two_point(S, P_fit, feeds_obs, r["dates"]) or [])],
                          "carry_excluded": len(carry)}
            if r.get("regime_start"):
                row["fit"]["regime_start"] = r["regime_start"]
                row["fit"]["full_n"] = r["full_n"]
                row["flags"].append("formula_changed")
            if reproduced and not r.get("regime_start"):
                lead = leading_regime(S, P_fit, feeds_obs, r)
                if lead:
                    row["fit"]["regime_start"] = lead
                    row["flags"].append("formula_changed")
            if not reproduced and len(feeds_obs) == 1:
                ep = episode_diag(S, P_fit, feeds_obs[0])
                if ep:
                    row["fit"]["episode"] = ep
                    row["flags"].append("formula_episode")
            pname = self.conn[row["product_sid"]]["name"]
            if row.get("unit_hint") == "USD/bbl":
                pname = "%s/%s" % (pname, ("%.4f" % CRACK_C).rstrip("0").rstrip("."))
            row["formula"] = "%s − %s" % (pname, " − ".join("%s×%s" % (_fk(f["k"]), f["name"]) for f in row["feeds"]))
            if reproduced:
                row["grade"] = "exact" if (r["resid_max_in"] is not None and r["resid_max_in"] <= EXACT_TOL) else "approx"
                row["fit"]["grade"] = row["grade"]
                extra = []
                rs = r.get("regime_start") or row["fit"].get("regime_start")
                if rs:
                    extra.append("%s 이후 산식" % rs)
                row["k_source"] = "역산 %s(최소제곱 %d/%d주, 안쪽 최대 잔차 %s%s)" % (
                    "정확" if row["grade"] == "exact" else "근사", r["n_in"], r["n"],
                    ("%.3f" % r["resid_max_in"]) if r["resid_max_in"] is not None else "—",
                    (", " + ", ".join(extra)) if extra else "")
            else:
                row["k_source"] = "역산 실패(안쪽 %d/%d주, 최대 잔차 %.1f)" % (r["n_in"], r["n"], r["resid_max_all"])
                e = row["fit"].get("episode")
                if e:
                    row["k_source"] += (" — 일시 이탈: 기준 k %s 가 %s~%s %d주 동안 %s~%s 로 바뀐 뒤 복귀%s"
                                        % (_fk(e["base_k"]), e["start"], e["end"], e["n"], _fk(e["k_min"]), _fk(e["k_max"]),
                                           "(이탈 밖은 기준 k 로 재현)" if e["outside_reproduced"] else "(이탈 밖도 k 가 흔들려 미재현)"))
                row["flags"].append("unreproduced")
            self._missing_product_check(row, S, P_fit, r, feeds_obs)
        else:
            row["k_source"] = "역산 불가(공통 관측 %d주 미만 또는 원료 시리즈 없음)" % MIN_POINTS
            row["flags"].append("unreproduced")
            row["flags"].append("insufficient_overlap")
        if row["layer"] == "crack" and row.get("unit_hint") != "USD/bbl":
            row["flags"].append("unit_conversion_unverified")   # 재현 못 한 크랙: 단위 기준 미확인

    def _missing_product_check(self, row, S, P, r, feeds):
        """제품 가격이 먼저 끊긴 뒤 스프레드가 −Σk×원료 로 이어지는가(결측을 0 으로 계산한 결함)."""
        p_dates = [d for d, v in P.items() if v is not None]
        if not p_dates:
            return
        p_last = max(p_dates)
        s_dates = sorted(d for d, v in S.items() if v is not None and d > p_last)
        if len(s_dates) < 4:
            return
        resid = []
        for d in s_dates:
            if any(f.get(d) is None for f in feeds):
                continue
            pred = -sum(r["k"][i] * float(feeds[i][d]) for i in range(len(feeds)))
            resid.append(abs(float(S[d]) - pred))
        if len(resid) >= 4 and max(resid) <= TOL_ABS:
            row["flags"].append("missing_product_as_zero")
            row["product_last_date"] = p_last

    # -- 파생
    def derived_rows(self, axis2y):
        out = []
        for d in self.al["derived"]:
            for region in d["regions"]:
                psid = self.sid_of(d["product"], self.region_p(region))
                P = self.obs(psid) if psid else None
                feeds, ok = [], P is not None
                for f in d["feeds"]:
                    rr = self.region_p(region) if f["region"] == "$same" else f["region"]
                    fsid = self.sid_of(f["name"], rr)
                    F = self.obs(fsid) if fsid else None
                    if F is None:
                        ok = False
                    feeds.append({"token": f["name"], "sid": fsid, "name": (self.conn[fsid]["name"] if fsid else None),
                                  "ref_region": rr, "k": f["k"], "obs": F})
                sid = "derived:%s_%s" % (d["id"], self.region_p(region))
                row = {"sid": sid, "name": "%s(%s)" % (d["label"], region), "cat": "파생", "chain": None, "chain_est": None,
                       "unit": "USD/MT", "sp": True, "kind": "derived", "layer": d["layer"], "product": d["product"],
                       "product_sid": psid, "region": region, "formula_version": 1,
                       "feeds": [{k: v for k, v in f.items() if k != "obs"} for f in feeds],
                       "k_source": d["source"], "reproduced": None, "flags": ["derived_estimate"],
                       "formula": None, "values": None, "last": None, "last_date": None, "freshness": None,
                       "days_since": None, "weeks_since": None,
                       "expected_cadence": "W", "stale_after_days": STALE_AFTER["W"], "stocks": [], "cnfut": None}
                if ok:
                    row["formula"] = "%s − %s" % (self.conn[psid]["name"], " − ".join("%s×%s" % (_fk(f["k"]), f["name"]) for f in feeds))
                    vals = []
                    for dt in axis2y:
                        pv = P.get(dt)
                        fv = [f["obs"].get(dt) for f in feeds]
                        vals.append(None if (pv is None or any(v is None for v in fv))
                                    else round(float(pv) - sum(f["k"] * float(v) for f, v in zip(feeds, fv)), 2))
                    row["values"] = vals
                    nz = [(dt, v) for dt, v in zip(axis2y, vals) if v is not None]
                    if nz:
                        row["last_date"], row["last"] = nz[-1]
                        days = (self.asof - datetime.date.fromisoformat(row["last_date"])).days
                        row["days_since"], row["weeks_since"] = days, days // 7
                        row["freshness"] = "fresh" if days <= STALE_AFTER["W"] else ("dead" if days > 365 else "stale")
                    chain = self.map_items.get(psid, {}).get("chain")
                    chain = chain if chain and chain != "uncategorized" else None
                    row["chain"] = chain
                    if chain:
                        row["stocks"] = [{"t": st["t"], "n": st["n"], "note": st.get("note", ""), "est": False}
                                         for st in self.chain_stocks.get(chain, [])]
                    cf = self.al["cnfut"].get(d["product"]) or self.al["cnfut"].get(
                        {v: k for k, v in self.al["product_alias"].items()}.get(d["product"]))
                    if cf and cf in self.conn:
                        c = self.conn[cf]
                        row["cnfut"] = {"sid": cf, "name": c["name"], "last": c["last"], "last_date": c["last_date"],
                                        "unit": c["unit"], "freshness": c["freshness"]}
                else:
                    row["flags"].append("constituent_missing")
                out.append(row)
        return out

    # -- 살아 있는 프록시(원장 정지 중 방향 참고 — 원장 산식·pos·m4 에 넣지 않는다)
    def live_proxies(self, ledger_last):
        out = []
        for spec in self.al.get("live_proxies", []):
            c = self.conn.get(spec["sid"])
            if not c:
                continue
            px = self.obs(spec["sid"]) or {}
            lsid = self.by_name.get(spec["ledger"]) if spec.get("ledger") else None
            chk = proxy_check(px, self.obs(lsid) or {}, c["freq"]) if lsid else None
            pv = [(d, v) for d, v in sorted(px.items()) if v is not None]
            lag = (chk or {}).get("lag") or 0
            post = None
            if ledger_last and pv:
                if c["freq"] == "M":
                    # 시차 lag 개월인 프록시는 '원장 정지 달 + lag' 이후 값만 정지 후 정보다(그 전 값은 정지 전 원장을 비춘다)
                    base_m = _shift_month(ledger_last[:7], lag)
                    base = [x for x in pv if x[0][:7] <= base_m]
                    after = [x for x in pv if x[0][:7] > base_m]
                else:
                    base = [x for x in pv if x[0] <= ledger_last]
                    after = [x for x in pv if x[0] > ledger_last]
                if base and after and base[-1][1]:
                    post = {"from": base[-1][0], "to": after[-1][0], "lag": lag,
                            "pct": round((after[-1][1] / base[-1][1] - 1.0) * 100, 2)}
                elif lag:
                    post = None
            out.append({"sid": spec["sid"], "name": c["name"], "unit": c["unit"], "freq": c["freq"], "freshness": c["freshness"],
                        "last": c["last"], "last_date": c["last_date"], "product": spec["product"], "chain": spec.get("chain"),
                        "ledger_sid": lsid, "ledger_name": spec.get("ledger"), "check": chk,
                        "post_halt": post if (chk and chk["gate"]) else None,
                        "post_halt_ungated": post, "lag": lag, "kind": "proxy", "layer": "proxy_live"})
        return out

    # -- 지역 간 바이트 복제(원장이 한 시리즈를 여러 지역 이름으로 복사)
    def mark_duplicates(self, rows, values_of):
        order = {r: i for i, r in enumerate(self.al["ref_region_order"])}
        groups = {}
        for r in rows:
            v = values_of(r)
            if not v:
                continue
            key = json.dumps(v, sort_keys=True)
            groups.setdefault(key, []).append(r)
        n_groups = 0
        for rs in groups.values():
            if len(rs) < 2:
                continue
            n_groups += 1
            rs.sort(key=lambda r: (order.get(self.region_p(r.get("region") or ""), 99), r["name"]))
            canon = rs[0]
            sids = [r["sid"] for r in rs]
            for r in rs:
                r["dup_group"] = sids
                r["dup_of"] = None if r is canon else canon["sid"]
                r["dup_of_region"] = None if r is canon else canon.get("region")
        unique = sum(1 for r in rows if values_of(r) and not r.get("dup_of"))
        return n_groups, unique

    # -- 체인 카드(원장 as-of 위치 · 허브 pos 기준 구성 · 정지 후 방향)
    def chain_view(self, rows, proxies, ledger_last):
        basis = self.al["basis_kind"]
        out = {}
        for cid in self.al["chem_chains"]:
            c = next((x for x in self.argus["chains"] if x["id"] == cid), None)
            if c is None:
                continue
            comp = {}
            for m in c.get("members") or []:
                sid = m.get("sid") if isinstance(m, dict) else str(m)
                kind = basis.get(sid.split("_")[0], "기타")
                comp[kind] = comp.get(kind, 0) + 1
            live_from = (datetime.date.fromisoformat(ledger_last) - datetime.timedelta(days=21)).isoformat() if ledger_last else None
            # 원장 정지 시점(as-of)까지 살아 있던 시리즈만 — 2022 등에 끝난 열(dead)의 pos 는 '현재 위치' 가 아니다
            ledger = [r for r in rows if r["kind"] == "spread" and (r["chain"] or r["chain_est"]) == cid
                      and r.get("pos") is not None and not r.get("dup_of")
                      and live_from and (r.get("effective_last") or r.get("last_date") or "") >= live_from]
            poss = sorted(r["pos"] for r in ledger)
            gated = [p for p in proxies if p["chain"] == cid and p["post_halt"]]
            pcts = sorted(p["post_halt"]["pct"] for p in gated)
            out[cid] = {
                "label": c["label"], "hub_pos": c.get("pos"), "hub_n": c.get("n"), "hub_basis": dict(sorted(comp.items())),
                "hub_has_ledger": comp.get(basis["sp"], 0) > 0,
                "ledger_pos_median": (round(_median(poss), 1) if poss else None), "ledger_n": len(poss), "ledger_asof": ledger_last,
                "post_halt_median_pct": (round(_median(pcts), 2) if pcts else None), "post_halt_n": len(pcts),
                "post_halt_items": [{"sid": p["sid"], "product": p["product"], "pct": p["post_halt"]["pct"]} for p in gated],
                "hunts": c.get("hunts"), "stocks": c.get("stocks", []),
            }
        return out

    # -- 전체
    def build(self):
        rows = []
        for cat in self.inp["chem_cats"]:
            for s in self.inp["chunks"][cat]["series"]:
                rows.append(self.row_for(s, cat))
        rows.sort(key=lambda r: (self.inp["chem_cats"].index(r["cat"]), r["name"]))
        dates = set()
        for r in rows:
            if r["kind"] == "spread":
                dates.update((self.obs(r["sid"]) or {}).keys())
        axis2y = sorted(dates)[-104:]
        derived = self.derived_rows(axis2y)
        spreads = [r for r in rows if r["kind"] == "spread"]
        ledger_last = max((r["last_date"] for r in rows if r["sid"].startswith("sp_") and r["last_date"]), default=None)
        ledger_weeks = ((self.asof - datetime.date.fromisoformat(ledger_last)).days // 7) if ledger_last else None
        dup_groups, unique = self.mark_duplicates(
            spreads, lambda r: sorted((d, v) for d, v in (self.obs(r["sid"]) or {}).items() if v is not None))
        d_groups, d_unique = self.mark_duplicates(
            [d for d in derived if d["values"] is not None], lambda r: r["values"])
        proxies = self.live_proxies(ledger_last)
        chain_view = self.chain_view(rows, proxies, ledger_last)
        # 원장 편집: Weekly_YYMMDD.xlsm 은 그 주 월요일 관측의 목요일 이름(260827 ↔ 08-24). 평가일 전날까지 기대.
        editions = None
        if ledger_last:
            ed = datetime.date.fromisoformat(ledger_last) + datetime.timedelta(days=3)
            nxt = ed + datetime.timedelta(days=7)
            missing = []
            t = nxt
            while t <= self.asof - datetime.timedelta(days=1):
                missing.append(t.isoformat())
                t += datetime.timedelta(days=7)
            editions = {"last_edition": ed.isoformat(), "last_file": "Weekly_%s.xlsm" % ed.strftime("%y%m%d"),
                        "next_expected": nxt.isoformat(), "missing": len(missing), "missing_dates": missing,
                        "recover": "최신 Weekly_YYMMDD.xlsm 1개를 ~/phalanx/jem_data/argus/inbox/ 에 드롭(누적형 — 최신본 하나로 전 편집 복구)"}
        summary = {
            "rows": len(rows), "spreads": len(spreads),
            "reproduced": sum(1 for r in spreads if r["reproduced"]),
            "unreproduced": sum(1 for r in spreads if r["reproduced"] is False),
            "freshness": _count(r["freshness"] for r in rows),
            "spread_freshness": _count(r["freshness"] for r in spreads),
            "layers": _count(r["layer"] for r in rows),
            "flags": _count(f for r in rows for f in r["flags"]),
            "chain_missing": sum(1 for r in rows if not r["chain"]),
            "chain_est_assigned": sum(1 for r in rows if not r["chain"] and r["chain_est"]),
            "derived": len(derived), "derived_ok": sum(1 for d in derived if d["values"] is not None),
            "by_cat": _count(r["cat"] for r in rows),
            "regions": _count(r["region"] for r in rows if r["region"]),
            "ledger_last": ledger_last, "ledger_stale_weeks": ledger_weeks,
            "grades": _count(r.get("grade") for r in spreads if r.get("reproduced")),
            "dup_groups": dup_groups, "unique_spreads": unique, "derived_dup_groups": d_groups, "derived_unique": d_unique,
            "carry_rows": sum(1 for r in spreads if r.get("carry_weeks")),
            "carry_weeks": sum(len(r.get("carry_weeks") or []) for r in spreads),
            "proxies": len(proxies), "proxies_gated": sum(1 for p in proxies if p["post_halt"]),
            "editions": editions,
        }
        return {
            "version": 1, "fingerprint": self.fp["fingerprint"], "inputs": self.fp["inputs"],
            "argus_asof": self.argus["asof"], "argus_built": self.argus.get("built"),
            "rules": {"tol_abs": TOL_ABS, "exact_tol": EXACT_TOL, "crack_usd_bbl_c": round(CRACK_C, 6), "episode_min": EPISODE_MIN,
                      "episode_dk": EPISODE_DK, "live_gate": LIVE_GATE,
                      "min_points": MIN_POINTS, "min_frac": MIN_FRAC, "recent": RECENT,
                      "stale_after_days": STALE_AFTER,
                      "fit": "스프레드 = 제품 − Σk×원료, 절편 없는 최소제곱(이상치 2회 제거), 적합 창 = 공통 관측 날짜(connections.js 주간, 최대 104주)",
                      "ref_region_order": self.al["ref_region_order"]},
            "axis2y": axis2y,
            "chains": {cid: dict(self.chain_pos[cid], label=self.chain_label[cid], stocks=self.chain_stocks[cid]) for cid in self.chain_pos},
            "rows": rows, "derived": derived, "summary": summary,
            "proxies": proxies, "chain_view": chain_view,
        }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    inputs, fp = kchem_inputs.load_all()
    reg = Registry(inputs, fp).build()
    if "--write" in argv:
        write_asset("registry.json", reg)
    s = reg["summary"]
    print("rows %d · spreads %d · reproduced %d · unreproduced %d · derived %d/%d · ledger_last %s (%s주)"
          % (s["rows"], s["spreads"], s["reproduced"], s["unreproduced"], s["derived_ok"], s["derived"],
             s["ledger_last"], s["ledger_stale_weeks"]))
    print("flags", s["flags"])
    if "--list-unreproduced" in argv:
        for r in reg["rows"]:
            if r["kind"] == "spread" and not r["reproduced"]:
                print("  ✗", r["name"], "|", r["k_source"], r["flags"], (r["fit"] or {}).get("k_2pt"))
    if "--list-flagged" in argv:
        for r in reg["rows"]:
            if r["kind"] == "spread" and r["reproduced"] and any(f not in ("unit_conversion_unverified",) for f in r["flags"]):
                print("  ⚑", r["name"], "|", r["formula"], r["flags"], (r["fit"] or {}).get("regime_start"))
    return reg


if __name__ == "__main__":
    main()
