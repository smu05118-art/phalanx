#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xi1_view — 계약 진행(XI-1) 화면 조각. 6개 수주 섹터 탭이 같은 모양으로 쓴다(xi1_sector.progress.json 을 읽는다).

JS 없이 서버에서 그린다 — 표는 탭의 TABLE_JS(data-sortable·td[data-v])가 정렬하고, 그림은 인라인 SVG 와 <title> 툴팁.
색은 kce 사업장 상세의 XI-1 분해와 같은 뜻을 쓴다(사람이 탭을 넘나들어도 같은 색 = 같은 돈):
  수령(대금수령 누적) 보라 #8b5cf6 · 매출채권(순, 공급−수령) 노랑 #eab308 · 선수금(순, 수령−공급) 청록 #06b6d4 ·
  잔여(계약−공급) 회색 #3f4b5f · 표준 곡선(탭 진행 계약의 경과 구간별 중앙값) 흰 선.
  어두운 면(#171a21) 위 CVD(제1·2·3색맹) 쌍별 ΔE(OKLab×100) 최소 12 — 2026-10-16 계산(UPDATE.md §6-C).
상태(지연 의심·납기 경과·지연 전망·정체)는 색만으로 말하지 않는다 — 늘 글자 칩을 함께 단다.

모든 함수는 데이터가 없으면 '' 를 돌려준다(탭 페이지는 섹션을 만들지 않는다 — 각 탭 HANDOFF 의 fail-soft 규칙).
"""
import html
import math

C_RECV, C_AR, C_ADV, C_REM, C_EXP = "#8b5cf6", "#eab308", "#06b6d4", "#3f4b5f", "#e2e8f0"
C_LAG, C_WARN = "#f87171", "#fbbf24"
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s"

FLAG_LABEL = {"lag": ("지연 의심", "dn", "같은 탭 표준 곡선보다 20%p 이상 뒤처짐(경과 20~100%)"),
              "overdue": ("납기 경과", "dn", "계약 종료일이 보고 기간 말보다 앞인데 공급 95% 미만"),
              "slip": ("지연 전망", "wn", "최근 공급 속도(월)로 잔여를 채우면 종료일보다 6개월 이상 늦음(경과 60% 이상만)"),
              "stalled": ("정체", "wn", "이미 시작한(진행 5%↑·경과 30%↑) 계약이 직전 보고 이후 공급 0"),
              "reversal": ("매출 역진", "dn", "당기 판매ㆍ공급 금액이 음수 — 매출 취소·계약 감액"),
              "cum_drop": ("누적 감소", "wn", "판매ㆍ공급 누적이 직전 보고보다 줄었다 — 재분류·오기 가능, 원문 대조"),
              "over": ("초과", "wn", "공급 누적이 계약금액의 105% 초과 — 금액 변경 미반영 또는 단위"),
              "unit_suspect": ("단위 의심", "wn", "표 금액 단위를 확인 못함 — 합계에서 뺐다"),
              "fx": ("외화", "", "외화 계약금액 — 우리는 환산하지 않는다"),
              "withheld": ("유보", "", "계약금액 공시유보"),
              "amt_ledger": ("원장 금액", "", "표에 계약금액 열이 없어(공급 열을 '계약금액'으로 적은 표) 체결 공시의 금액을 썼다"),
              "dup": ("자회사 계약", "", "자회사가 같은 계약을 자기 표에도 싣는다 — 탭 합계·곡선에서는 자회사 쪽 1번만 센다"),
              "cell_fix": ("칸 단위 보정", "", "공급·수령 한 칸이 계약금액의 2배를 넘어 천·백만 단위로 옮기거나 비웠다(원문 대조)")}
STATUS_LABEL = {"active": "진행", "new": "신규", "done": "완료(표에서 빠짐·직전 95%↑)",
                "dropped": "이탈(표에서 빠짐·직전 95%↓)"}
TIER_LABEL = {"A": ("확정", "신고일 = 원장 접수일 + 금액·이름·상대방 근거"),
              "B": ("추정", "신고일 근사·이름·금액 중 둘 — 원문 대조 권장")}

CSS = """
.xi1{--xr:%s;--xa:%s;--xv:%s;--xm:%s;--xe:%s}
.xi1 .xk{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:8px 0 12px}
.xi1 .xk>div{background:var(--pn2,rgba(255,255,255,.03));border:1px solid var(--ln,#2a2f3a);border-radius:8px;padding:8px 10px}
.xi1 .xk b{display:block;font-size:18px;color:var(--tx,#e6e9ef);font-variant-numeric:tabular-nums}
.xi1 .xk span{font-size:12px;color:var(--tx2,#9aa3b2)}
.xi1 .xg{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.xi1 figure{margin:0}
.xi1 figcaption{font-size:12px;color:var(--tx2,#9aa3b2);margin:4px 0 8px}
.xi1 svg{max-width:100%%;height:auto;display:block}
.xi1 svg text{fill:var(--tx2,#9aa3b2);font-size:11px;font-family:var(--sans,inherit)}
.xi1 svg .t1{fill:var(--tx,#e6e9ef)}
.xi1 .lg{display:flex;flex-wrap:wrap;gap:10px;font-size:12px;color:var(--tx2,#9aa3b2);margin:4px 0}
.xi1 .lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.xi1 .chipx{display:inline-block;font-size:11px;padding:1px 6px;border-radius:9px;border:1px solid var(--ln,#2a2f3a);
 color:var(--tx2,#9aa3b2);margin:0 2px 2px 0;white-space:nowrap}
.xi1 .chipx.dn{border-color:%s;color:%s}.xi1 .chipx.wn{border-color:%s;color:%s}
.xi1 .tbw{overflow-x:auto}
.xi1 table{width:100%%;border-collapse:collapse;font-size:12.5px}
.xi1 th,.xi1 td{padding:5px 6px;border-bottom:1px solid var(--ln,#2a2f3a);text-align:left;vertical-align:top}
.xi1 td.n,.xi1 th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.xi1 .mut{color:var(--tx3,#6b7280)}
.xi1 .minis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:6px 0 10px}
.xi1 .minis svg{border:1px solid var(--ln,#2a2f3a);border-radius:6px}
.xi1 .feed ul{margin:6px 0 12px;padding-left:18px;font-size:13px;line-height:1.7}
.xi1 .feed li b{font-weight:600}
.xi1 .note{font-size:12px;color:var(--tx2,#9aa3b2);line-height:1.6;background:none;border:0;padding:0;margin:8px 0;
 border-radius:0;box-shadow:none}
.xi1c{white-space:nowrap}
.xi1c .xb{display:inline-block;width:56px;height:7px;border-radius:2px;background:%s;position:relative;overflow:hidden;
 vertical-align:middle;margin-right:5px}
.xi1c .xb i{position:absolute;top:0;bottom:0}
.xi1c .xb s{position:absolute;top:-1px;bottom:-1px;width:2px;background:%s;text-decoration:none}
""" % (C_RECV, C_AR, C_ADV, C_REM, C_EXP, C_LAG, C_LAG, C_WARN, C_WARN, C_REM, C_EXP)


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def eok(v, unit=True):
    """백만원 → 억(정수, 10억 미만은 소수 1자리). 1조 이상은 money() 를 쓴다."""
    if v is None:
        return "—"
    x = v / 100.0
    s = "{:,.1f}".format(x) if abs(x) < 10 else "{:,.0f}".format(x)
    return s + ("억" if unit else "")


def money(v):
    """백만원 → 1조 이상은 '12.3조', 아래는 억."""
    if v is None:
        return "—"
    if abs(v) >= 1e6:
        return "{:,.1f}조".format(v / 1e6)
    return eok(v)


def pct(x, d=0):
    return "—" if x is None else ("{:.%df}%%" % d).format(x * 100)


def _short(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def chips(c):
    out = []
    new = set(c.get("new_sig") or [])
    for f in c.get("flags") or []:
        lab, cls, tip = FLAG_LABEL.get(f, (f, "", ""))
        if f in new:
            lab, tip = lab + " · 신규", tip + " — 직전 보고에는 없던 신호"
        out.append('<span class="chipx %s" title="%s">%s</span>' % (cls, e(tip), e(lab)))
    if c.get("note"):
        out.append('<span class="chipx" title="회사가 적은 진행상황">%s</span>' % e(_short(c["note"], 24)))
    return "".join(out)


def _by_id(prog):
    return {c["id"]: c for c in prog.get("contracts") or []}


def contract_of(prog, rcps):
    """원장 rcp(또는 그 정정 사슬) → 진행 계약. 없으면 None."""
    if not prog:
        return None
    br = prog.get("by_rcp") or {}
    ids = _by_id(prog)
    for r in ([rcps] if isinstance(rcps, str) else rcps or []):
        if r and r in br:
            return ids.get(br[r])
    return None


def _segs(c):
    """막대 조각(0~1 비율) — kce xipDecomp 와 같은 네 조각, 합 = 계약금액 100%:
    수령(min(공급, 수령)) · 매출채권(공급 − 수령, 양수일 때) · 선수금(수령 − 공급, 양수일 때) · 잔여(계약 − max(공급, 수령))."""
    m = c["m"]
    amt = m.get("amt")
    h = c["hist"].get(m["q"]) or [None] * 5
    sup, recv = h[2], h[4]
    if not amt or sup is None:
        return None
    sup_r = min(sup / amt, 1.0)
    recv_r = min((recv if recv is not None else 0) / amt, 1.0)
    got = min(recv_r, sup_r)
    return {"recv": got, "ar": max(sup_r - got, 0), "rem": max(1 - max(sup_r, recv_r), 0),
            "adv": max(recv_r - sup_r, 0)}


def amt_s(c, v):
    """계약 단위 금액 — fx_native(외화 비율만) 이면 통화 표기, 아니면 억·조."""
    u = c["m"].get("unit")
    if v is None:
        return "—"
    return "%s %s" % (u, "{:,.0f}".format(v)) if u else money(v)


def tip(c, prog=None):
    m = c["m"]
    parts = ["XI-1 %s" % m["q"], "계약 %s%s" % (amt_s(c, m.get("amt")), {"ledger_krw": " (원장 원화)", "fx_native": " (외화 비율)"}.get(m.get("basis"), ""))]
    if m.get("prog") is not None:
        parts.append("공급 %s" % pct(m["prog"]))
    if m.get("recv_prog") is not None:
        parts.append("수령 %s" % pct(m["recv_prog"]))
    if m.get("elapsed") is not None:
        parts.append("경과 %s" % pct(m["elapsed"]))
    if m.get("exp") is not None:
        parts.append("표준 곡선 %s" % pct(m["exp"]))
    if m.get("rem") is not None:
        parts.append("잔여 %s" % amt_s(c, m["rem"]))
    if c.get("cur") and c.get("amt_fx"):
        parts.append("%s %s" % (c["cur"], "{:,.0f}".format(c["amt_fx"])))
    return " · ".join(parts)


def progress_th():
    return ('<th class="n" title="반기·사업보고서 XI-1 진행 현황 — 막대 = 계약금액 100%: 보라 수령, 노랑 매출채권(순), '
            '청록 선수금(순), 회색 잔여, 흰 눈금 = 탭 표준 곡선. 숫자 = 판매ㆍ공급 누적 ÷ 계약금액">진행(XI-1)</th>')


def progress_cell(prog, rcps, tag="td"):
    """원장 표 한 칸. 진행 계약이 없으면 '—'(0 이 아니다). data-v = 공급 진행률(정렬)."""
    c = contract_of(prog, rcps)
    if not c:
        return '<%s class="n xi1c mut" data-v="-1">—</%s>' % (tag, tag)
    m = c["m"]
    sg = _segs(c)
    if not sg:
        lab = c.get("cur") or ("유보" if "withheld" in c["flags"] else "—")
        return '<%s class="n xi1c mut" data-v="-1" title="%s">%s</%s>' % (tag, e(tip(c)), e(lab), tag)
    bar = ('<span class="xb"><i style="left:0;width:%.1f%%;background:%s"></i>'
           '<i style="left:%.1f%%;width:%.1f%%;background:%s"></i><i style="left:%.1f%%;width:%.1f%%;background:%s"></i>'
           % (sg["recv"] * 100, C_RECV, sg["recv"] * 100, sg["ar"] * 100, C_AR,
              (sg["recv"] + sg["ar"]) * 100, sg["adv"] * 100, C_ADV))
    if m.get("exp") is not None:
        bar += '<s style="left:calc(%.1f%% - 1px)"></s>' % (min(m["exp"], 1) * 100)
    bar += "</span>"
    warn = "".join("⚠" for f in c["flags"] if f in ("lag", "overdue"))[:1]
    return '<%s class="n xi1c" data-v="%.4f" title="%s">%s%s%s</%s>' % (
        tag, m["prog"], e(tip(c)), bar, pct(m["prog"]), (" " + warn) if warn else "", tag)


# ── SVG ─────────────────────────────────────────────────────────

def _bars_svg(rows, title):
    """계약별 진행 막대(계약금액 = 100%). rows: [contract]. 왼쪽 이름, 가운데 막대, 오른쪽 진행·잔여."""
    W, LW, RW, H, G = 760, 200, 190, 14, 8
    BW = W - LW - RW
    h = 26 + len(rows) * (H + G)
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s" xmlns="http://www.w3.org/2000/svg">' % (W, h, e(title))]
    for x in (0, 0.25, 0.5, 0.75, 1.0):
        X = LW + BW * x
        out.append('<line x1="%.1f" y1="16" x2="%.1f" y2="%d" stroke="currentColor" stroke-opacity=".12"/>' % (X, X, h - 4))
        out.append('<text x="%.1f" y="11" text-anchor="middle">%d%%</text>' % (X, x * 100))
    for i, c in enumerate(rows):
        y = 22 + i * (H + G)
        sg = _segs(c) or {"recv": 0, "ar": 0, "rem": 1, "adv": 0}
        m = c["m"]
        out.append('<g><title>%s · %s</title>' % (e(c["nm"]), e(tip(c))))
        out.append('<text class="t1" x="%d" y="%d" text-anchor="end">%s</text>' % (LW - 8, y + 11, e(_short(c["nm"], 18))))
        x = LW
        for k, col in (("recv", C_RECV), ("ar", C_AR), ("adv", C_ADV), ("rem", C_REM)):
            w = BW * sg[k]
            if w > 0.2:
                out.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="%s"/>' % (x, y, max(w - (1 if k != "rem" else 0), 0.5), H, col))
            x += w
        if m.get("exp") is not None:
            ex = LW + BW * min(m["exp"], 1)
            out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="2"/>' % (ex, y - 3, ex, y + H + 3, C_EXP))
        lab = "%s · 잔여 %s" % (pct(m.get("prog")), amt_s(c, m.get("rem")))
        fl = [FLAG_LABEL[f][0] for f in c["flags"] if f in ("lag", "overdue", "reversal", "slip", "stalled", "cum_drop")]
        if fl:
            lab += " · " + fl[0]
        out.append('<text x="%d" y="%d">%s</text></g>' % (LW + BW + 8, y + 11, e(lab)))
    out.append("</svg>")
    return "".join(out)


def _series_svg(series, periods, title):
    """반기별 누적 분해(계약금액 = 수령 + 매출채권 + 잔여). 같은 색 = 같은 돈(계약 막대와 동일)."""
    qs = [q for q in periods if q in series]
    if not qs:
        return ""
    W, H, L, B, T = 520, 220, 56, 28, 14
    top = max(series[q]["amt"] for q in qs) or 1
    mag = 10 ** math.floor(math.log10(top))
    step = next(s * mag for s in (0.2, 0.25, 0.5, 1, 2, 2.5, 5) if top / (s * mag) <= 5)
    ymax = step * math.ceil(top / step)
    bw = min(56, (W - L - 10) / len(qs) * 0.6)
    gap = (W - L - 10) / len(qs)
    sy = lambda v: T + (H - T - B) * (1 - v / ymax)          # noqa: E731
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s" xmlns="http://www.w3.org/2000/svg">' % (W, H, e(title))]
    jo = ymax >= 1e6
    v = 0
    while v <= ymax + 1e-9:
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" stroke-opacity=".12"/>' % (L, sy(v), W - 6, sy(v)))
        out.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (
            L - 6, sy(v) + 4, ("{:,.0f}".format(v / 1e6) if step >= 1e6 else "{:,.1f}".format(v / 1e6)) if jo else eok(v, False)))
        v += step
    out.append('<text x="%d" y="10">%s</text>' % (4, "조원" if jo else "억원"))
    for i, q in enumerate(qs):
        s = series[q]
        sb = s.get("sup_both", s["sup"])          # 수령이 함께 적힌 계약의 공급 — 수령 없는 계약까지 넣으면 매출채권이 부푼다
        recv = min(s["recv"], sb)
        ar = max(sb - s["recv"], 0)
        adv = max(s["recv"] - sb, 0)
        recv += max(s["sup"] - sb, 0)             # 수령 칸 없는 계약의 공급은 공급(보라)으로만 — 분해 불가
        bal = max(s["amt"] - max(s["sup"], s["sup"] - sb + s["recv"]), 0)
        x = L + gap * i + (gap - bw) / 2
        y0 = sy(0)
        for val, col, lab in ((recv, C_RECV, "수령"), (ar, C_AR, "매출채권(순)"), (adv, C_ADV, "선수금(순)"), (bal, C_REM, "잔여")):
            if val <= 0:
                continue
            hh = (H - T - B) * val / ymax
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"><title>%s %s %s</title></rect>'
                       % (x, y0 - hh, bw, max(hh - 1, 0.5), col, q, lab, money(val)))
            y0 -= hh
        out.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x + bw / 2, H - 12, q))
        out.append('<text x="%.1f" y="%d" text-anchor="middle" class="t1">%d건</text>' % (x + bw / 2, H - 1, s["n"]))
    out.append("</svg>")
    return "".join(out)


def _scatter_svg(points, curve, title, labels=0):
    """경과율(x) × 공급 진행률(y). 점 크기 ∝ √계약금액, 흰 선 = 탭 표준 곡선, 빨강 = 지연 의심·납기 경과."""
    W, H, L, B, T, R = 520, 300, 40, 30, 10, 12
    pw, ph = W - L - R, H - T - B
    sx = lambda x: L + pw * min(x, 1.5) / 1.5           # noqa: E731
    sy = lambda y: T + ph * (1 - min(y, 1.2) / 1.2)     # noqa: E731
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s" xmlns="http://www.w3.org/2000/svg">' % (W, H, e(title))]
    for gx in (0, 0.5, 1.0, 1.5):
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="currentColor" stroke-opacity="%s"/>'
                   % (sx(gx), T, sx(gx), H - B, ".35" if gx == 1 else ".12"))
        out.append('<text x="%.1f" y="%d" text-anchor="middle">%d%%</text>' % (sx(gx), H - B + 14, gx * 100))
    for gy in (0, 0.5, 1.0):
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" stroke-opacity=".12"/>' % (L, sy(gy), W - R, sy(gy)))
        out.append('<text x="%d" y="%.1f" text-anchor="end">%d%%</text>' % (L - 4, sy(gy) + 4, gy * 100))
    out.append('<text x="%d" y="%d" text-anchor="end">계약기간 경과 →</text>' % (W - R, H - 2))
    out.append('<text x="%d" y="%d">↑ 공급 진행</text>' % (L + 4, T + 10))
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="3 3"/>'
               % (sx(0), sy(0), sx(1), sy(1)))
    if curve:
        pts = [(0, 0)] + [(p["x"], p["y"]) for p in curve]
        out.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"><title>탭 표준 곡선 — 경과 구간별 진행률 중앙값</title></polyline>'
                   % (C_EXP, " ".join("%.1f,%.1f" % (sx(x), sy(y)) for x, y in pts)))
    amax = max((p["amt"] for p in points if p["amt"]), default=1)
    ordered = sorted(points, key=lambda p: -(p["amt"] or 0))
    for p in ordered:
        r = 2.5 + 9 * math.sqrt((p["amt"] or 0) / amax)
        hot = p["hot"]
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="%s" stroke="#171a21" stroke-width="1"><title>%s</title></circle>'
                   % (sx(p["x"]), sy(p["y"]), r, C_LAG if hot else C_RECV, ".85" if hot else ".55", e(p["tip"])))
    placed = []
    for p in [q for q in ordered if q["hot"]]:
        if len(placed) >= labels:
            break
        x0, y0 = sx(p["x"]) + 6, sy(p["y"]) - 6
        if x0 > W - 90:
            x0 -= 100
        if any(abs(x0 - a) < 90 and abs(y0 - b) < 13 for a, b in placed):
            continue
        placed.append((x0, y0))
        out.append('<text x="%.1f" y="%.1f" class="t1">%s</text>' % (x0, y0, e(_short(p["label"], 14))))
    out.append("</svg>")
    return "".join(out)


def _bridge_svg(f, title):
    """잔여 다리(폭포): 시작 잔여 → +신규 → ±금액 변동 → −공급 → −이탈 → 끝 잔여. 원화 계약, 두 기간 모두 표가 있는 회사만."""
    steps = [("%s 잔여" % f["from"], f["start"], "base"), ("+신규 %d건" % f["new_n"], f["new"], "up"),
             ("금액 변동", f["chg"], "up" if f["chg"] >= 0 else "dn"), ("−공급", -f["supplied"], "dn"),
             ("−이탈·완료 %d건" % f["exit_n"], -f["exit"], "dn"), ("끝 잔여", f["end"], "base")]
    W, H, L, B, T = 560, 230, 64, 34, 14
    run, tops = 0.0, []
    for lab, v, kind in steps:
        if kind == "base":
            tops.append((0, v))
            run = v
        else:
            tops.append((run, run + v))
            run += v
    ymax = max(max(a, b) for a, b in tops) * 1.08 or 1
    sy = lambda v: T + (H - T - B) * (1 - v / ymax)        # noqa: E731
    gw = (W - L - 10) / len(steps)
    bw = gw * 0.62
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s" xmlns="http://www.w3.org/2000/svg">' % (W, H, e(title))]
    out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="currentColor" stroke-opacity=".25"/>' % (L, sy(0), W - 6, sy(0)))
    for i, ((lab, v, kind), (a, b)) in enumerate(zip(steps, tops)):
        x = L + gw * i + (gw - bw) / 2
        lo, hi = min(a, b), max(a, b)
        col = C_REM if kind == "base" else (C_ADV if kind == "up" else C_AR)
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"><title>%s %s</title></rect>'
                   % (x, sy(hi), bw, max(sy(lo) - sy(hi), 0.8), col, e(lab), money(v)))
        out.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="t1">%s</text>' % (x + bw / 2, sy(hi) - 4, money(v)))
        out.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x + bw / 2, H - 18, e(lab)))
        if i < len(steps) - 1:
            nx = L + gw * (i + 1) + (gw - bw) / 2
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="currentColor" stroke-opacity=".3" stroke-dasharray="2 2"/>'
                       % (x + bw, sy(b), nx, sy(b)))
    out.append('<text x="%d" y="%d">끝수 %s(초과 공급·반올림)</text>' % (L, H - 2, money(f.get("resid"))))
    out.append("</svg>")
    return "".join(out)


def _parties_table(parties, tid):
    if not parties:
        return ""
    tr = "".join('<tr><td>%s</td><td class="n" data-v="%s">%s</td>%s</tr>'
                 % (e(_short(p[0], 40)), p[1], money(p[1]), ('<td class="n">%d</td>' % p[2]) if len(p) > 2 else "")
                 for p in parties)
    extra = '<th class="n">회사</th>' if len(parties[0]) > 2 else ""
    return ('<div class="tbw"><table id="%s" data-sortable><thead><tr><th>계약상대</th><th class="n">잔여</th>%s</tr></thead>'
            '<tbody>%s</tbody></table></div>' % (e(tid), extra, tr))


def _timeline_svg(rows, asof, title):
    """계약 기간 막대(시작~종료) 안에 공급 진행만큼 채움 + 기간 말 세로선 + 표준 곡선 눈금. 종료일이 지났는데 95% 미만이면
    빨간 테두리(납기 경과). 연도 눈금은 같은 축 — 언제 무엇이 끝나야 하는지(납기 달력)를 한 그림에서 본다."""
    import datetime as _d
    rows = [c for c in rows if c["m"].get("start") and c["m"].get("end")]
    if not rows:
        return ""
    ds = lambda s: _d.date(int(s[:4]), int(s[5:7]), int(s[8:10]))       # noqa: E731
    lo = min(ds(c["m"]["start"]) for c in rows)
    hi = max(ds(c["m"]["end"]) for c in rows)
    lo = max(lo, _d.date(asof.year - 6, 1, 1))
    hi = max(min(hi, _d.date(asof.year + 6, 12, 31)), asof)
    W, LW, RW, H, G, T = 760, 200, 86, 12, 7, 22
    BW = W - LW - RW
    span = (hi - lo).days or 1
    sx = lambda d: LW + BW * min(max((d - lo).days / span, 0), 1)        # noqa: E731
    h = T + len(rows) * (H + G) + 20
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s" xmlns="http://www.w3.org/2000/svg">' % (W, h, e(title))]
    for y in range(lo.year + 1, hi.year + 1):
        x = sx(_d.date(y, 1, 1))
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="currentColor" stroke-opacity=".12"/>' % (x, T - 6, x, h - 4))
        out.append('<text x="%.1f" y="%d" text-anchor="middle">%d</text>' % (x, T - 9, y))
    ax = sx(asof)
    for i, c in enumerate(rows):
        m = c["m"]
        y = T + i * (H + G)
        s0, e0 = ds(m["start"]), ds(m["end"])
        x0, x1 = sx(s0), sx(e0)
        w = max(x1 - x0, 2)
        hot = "overdue" in c["flags"]
        out.append('<g><title>%s · %s ~ %s · %s</title>' % (e(c["nm"]), m["start"], m["end"], e(tip(c))))
        out.append('<text class="t1" x="%d" y="%d" text-anchor="end">%s</text>' % (LW - 8, y + 10, e(_short(c["nm"], 18))))
        out.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="%s"%s/>'
                   % (x0, y, w, H, C_REM, (' stroke="%s" stroke-width="1.5"' % C_LAG) if hot else ""))
        if m.get("prog") is not None:
            out.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="%s"/>' % (x0, y, max(w * min(m["prog"], 1), 0.5), H, C_RECV))
        if m.get("exp") is not None:
            ex = x0 + w * min(m["exp"], 1)
            out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="2"/>' % (ex, y - 2, ex, y + H + 2, C_EXP))
        out.append('<text x="%.1f" y="%d">%s</text></g>' % (W - RW + 6, y + 10, e(m["end"][:7].replace("-", "."))))
    out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1.5" stroke-dasharray="4 3"/>'
               % (ax, T - 6, ax, h - 16, C_EXP))
    out.append('<text x="%.1f" y="%d" text-anchor="middle" class="t1">%s 말 기준</text>' % (ax, h - 3, asof.strftime("%Y.%m")))
    out.append("</svg>")
    return "".join(out)


def _sched_table(items):
    rows = [c for c in items if c.get("sched")]
    if not rows:
        return ""
    labs = []
    for c in rows:
        for b, _v in c["sched"]["buckets"]:
            if b not in labs:
                labs.append(b)
    head = "".join('<th class="n">%s</th>' % e(b) for b in labs)
    tr = []
    for c in rows:
        sc = c["sched"]
        vals = dict((b, v) for b, v in sc["buckets"])
        tr.append('<tr><td>%s</td><td title="%s">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td>%s</tr>'
                  % (e(c.get("dt") or "—"), e(c["nm"]), e(_short(c["nm"], 30)), money(sc["amt"]), money(sc.get("recv")),
                     money(sc.get("unrecv")), "".join('<td class="n">%s</td>' % money(vals.get(b)) for b in labs)))
    return ('<h3>대금수령 예정 <span class="mut">(회사가 XI-1 부표에 적은 앞으로의 수령 일정 — %s 말 기준)</span></h3>'
            '<div class="tbw"><table data-sortable><thead><tr><th>신고일</th><th>계약</th><th class="n">계약금액</th><th class="n">수령</th>'
            '<th class="n">미수령</th>%s</tr></thead><tbody>%s</tbody></table></div>' % (e(rows[0]["sched"]["q"]), head, "".join(tr)))


def _feed(prog, cur, co_cell, limit=12):
    """신호 피드 — 직전 보고 이후 새로 생긴 신호·새로 실린 큰 계약·표에서 빠진 계약."""
    new_sig = sorted([c for c in cur if c.get("new_sig")], key=lambda c: -(c["m"].get("rem") or 0))[:limit]
    new_ct = sorted([c for c in cur if c["status"] == "new" and c["m"].get("amt") and c["m"].get("basis") == "xi"],
                    key=lambda c: -c["m"]["amt"])[:6]
    left = [c for c in prog["contracts"] if c.get("left") and "dup" not in c["flags"]]
    if not (new_sig or new_ct or left):
        return ""
    li = []
    for c in new_sig:
        labs = " · ".join(FLAG_LABEL.get(f, (f,))[0] for f in c["new_sig"])
        li.append('<li><b>%s</b> %s — %s <span class="mut">(진행 %s · 표준 %s · 잔여 %s)</span></li>'
                  % (co_cell(c), e(_short(c["nm"], 30)), e(labs), pct(c["m"].get("prog")), pct(c["m"].get("exp")), money(c["m"].get("rem"))))
    for c in new_ct:
        li.append('<li><b>%s</b> %s — 새로 실린 계약 <span class="mut">(%s · 진행 %s)</span></li>'
                  % (co_cell(c), e(_short(c["nm"], 30)), money(c["m"]["amt"]), pct(c["m"].get("prog"))))
    done = sum(1 for c in left if c["status"] == "done")
    if left:
        li.append('<li class="mut">표에서 빠진 계약 %d건 — 완료(직전 95%%↑) %d · 이탈 %d</li>' % (len(left), done, len(left) - done))
    return ('<div class="feed"><h3>이번 보고에서 달라진 것 <span class="mut">(직전 보고와 같은 규칙으로 다시 계산해 비교)</span></h3>'
            '<ul>%s</ul></div>' % "".join(li))


TAB_LABEL = {"kship": "조선", "kdef": "방산", "knuke": "원전", "kgrid": "전력기기", "kaero": "항공우주", "ksemi": "반도체장비"}


def _mini_curve(curve, label, hot, W=150, H=110):
    L, B, T, R = 22, 16, 18, 6
    pw, ph = W - L - R, H - T - B
    sx = lambda x: L + pw * min(x, 1.25) / 1.25          # noqa: E731
    sy = lambda y: T + ph * (1 - y)                      # noqa: E731
    pts = [(0.0, 0.0)] + [(p["x"], p["y"]) for p in curve or []]
    col = C_EXP if hot else C_RECV
    return ('<svg viewBox="0 0 %d %d" role="img" aria-label="%s 표준 곡선" xmlns="http://www.w3.org/2000/svg">'
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="2 2"/>'
            '<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="currentColor" stroke-opacity=".2"/>'
            '<polyline fill="none" stroke="%s" stroke-width="%s" points="%s"/>'
            '<text x="%d" y="12" class="%s">%s</text><text x="%.1f" y="%d" text-anchor="middle">100%%</text></svg>'
            % (W, H, e(label), sx(0), sy(0), sx(1), sy(1), sx(1), T, sx(1), H - B, col, "2.5" if hot else "1.6",
               " ".join("%.1f,%.1f" % (sx(x), sy(y)) for x, y in pts), L, "t1" if hot else "", e(label), sx(1), H - 3))


def compare_section(prog, peers=None, href=None):
    """다른 수주 탭과 비교 — 6개 탭의 progress.json 섹터 요약(이 탭 줄은 굵게)·표준 곡선 작은 다중.
    peers 가 없으면 같은 레포의 다른 탭 progress.json 을 읽는다(그 탭이 마지막으로 커밋한 값 — 하루 정도 늦을 수 있다)."""
    if not prog:
        return ""
    if peers is None:
        try:
            import xi1_sector as _S
            peers = {}
            for t in _S.TABS:
                pp = prog if t == prog.get("tab") else _S.load_progress(t)
                if pp:
                    peers[t] = {"sector": pp["sector"], "curve": pp.get("curve"), "asof": pp.get("asof")}
        except Exception:                       # noqa: BLE001 — 비교는 부가 조각
            return ""
    if len(peers) < 2:
        return ""
    href = href or (lambda t: "../%s/index.html#xi1" % t)
    me = prog.get("tab")
    tr = []
    for t, pv in peers.items():
        s = pv["sector"]
        c55 = next((p["y"] for p in pv.get("curve") or [] if abs(p["x"] - 0.55) < 1e-6), None)
        nm = TAB_LABEL.get(t, t)
        cell = ('<b>%s</b>' % e(nm)) if t == me else '<a href="%s">%s</a>' % (e(href(t)), e(nm))
        tr.append('<tr%s><td>%s</td><td class="n" data-v="%s">%d</td><td class="n" data-v="%s">%s</td><td class="n" data-v="%s">%s</td>'
                  '<td class="n" data-v="%s">%s</td><td class="n" data-v="%s">%s</td><td class="n" data-v="%s">%s</td>'
                  '<td class="n" data-v="%s">%d</td><td class="mut">%s</td></tr>'
                  % (' style="font-weight:600"' if t == me else "", cell, s["n"], s["n"], s["rem"], money(s["rem"]),
                     s.get("prog_w") or -1, pct(s.get("prog_w")), s.get("pace_y") or -1, money(s.get("pace_y")),
                     s.get("burn_y") or -1, ("%.1f년" % s["burn_y"]) if s.get("burn_y") else "—",
                     c55 if c55 is not None else -1, pct(c55), s["lag"] + s.get("overdue", 0), s["lag"] + s.get("overdue", 0),
                     e(pv.get("asof") or "")))
    minis = "".join('<div class="mini">%s</div>' % _mini_curve(pv.get("curve"), TAB_LABEL.get(t, t), t == me)
                    for t, pv in peers.items())
    return ('<h3>다른 수주 탭과 비교 <span class="mut">(같은 공용 규칙 — 업종마다 계약이 매출이 되는 모양이 다르다)</span></h3>'
            '<div class="minis">%s</div><div class="tbw"><table id="xi1cmp" data-sortable><thead><tr><th>탭</th><th class="n">진행 계약</th>'
            '<th class="n">잔여</th><th class="n">가중 진행</th><th class="n">연 공급</th><th class="n">잔여 소진</th>'
            '<th class="n" title="계약기간 55%%가 지났을 때 진행률 중앙값(표준 곡선)">경과 55%% 진행</th><th class="n">지연·납기 경과</th>'
            '<th>기준</th></tr></thead><tbody>%s</tbody></table></div>' % (minis, "".join(tr)))


def _legend():
    return ('<div class="lg"><span><i style="background:%s"></i>대금수령</span><span><i style="background:%s"></i>매출채권(순)</span>'
            '<span><i style="background:%s"></i>선수금(순)</span><span><i style="background:%s"></i>잔여</span>'
            '<span><i style="background:%s;height:2px;vertical-align:3px"></i>탭 표준 곡선</span></div>'
            % (C_RECV, C_AR, C_ADV, C_REM, C_EXP))


def _kpis(tiles):
    return '<div class="xk">%s</div>' % "".join('<div><b>%s</b><span>%s</span></div>' % (v, l) for v, l in tiles)


def _contract_table(rows, tid, show_co=None, link_rcp=True):
    head = ["신고일", "계약명"] + (["회사"] if show_co else []) + ["상대", "계약금액", "공급 누적", "진행", "표준 대비",
                                                               "수령 진척", "매출채권(순)", "반기 공급", "계약기간", "예상 완료",
                                                               "원장", "상태"]
    num = {"계약금액", "공급 누적", "진행", "표준 대비", "수령 진척", "매출채권(순)", "반기 공급"}
    out = ['<div class="tbw"><table id="%s" data-sortable><thead><tr>%s</tr></thead><tbody>'
           % (e(tid), "".join('<th%s>%s</th>' % (' class="n"' if h in num else "", h) for h in head))]
    for c in rows:
        m = c["m"]
        h = c["hist"].get(m["q"]) or [None] * 5
        a_s = amt_s(c, m.get("amt")) if m.get("amt") else (("%s %s" % (c["cur"], "{:,.0f}".format(c["amt_fx"])))
                                                          if c.get("cur") and c.get("amt_fx") else "—")
        if m.get("basis") == "ledger_krw":
            a_s += ' <span class="mut" title="외화 계약 — 원장(공시)의 원화 계약금액을 분모로 씀(추정)">원장</span>'
        elif m.get("basis") == "fx_native":
            a_s += ' <span class="mut" title="외화 계약 — 공급·수령도 같은 외화로 적힌 표, 비율만 쓰고 원화 합계에서 뺀다">외화</span>'
        lk = c.get("link")
        if lk:
            lab, t = TIER_LABEL[lk["tier"]]
            led = '<a href="%s" target="_blank" rel="noopener" title="%s · %s">%s</a>' % (DART % lk["rcp"], e(t), e(lk["basis"]), lab) \
                if link_rcp else e(lab)
        else:
            led = '<span class="mut" title="탭 원장(단일판매ㆍ공급계약체결 공시)에서 근거 있는 짝을 못 찾음 — 억지로 붙이지 않는다">XI 전용</span>'
        span = ("%s ~ %s" % (m["start"][:7], m["end"][:7])) if m.get("start") else (c.get("period") or "—")
        eta = "—"
        if m.get("eta_m") is not None and m.get("rem"):
            eta = "+%.0f개월" % m["eta_m"]
            if m.get("slip_m") is not None:
                eta += " (%s%.0f)" % ("+" if m["slip_m"] >= 0 else "", m["slip_m"])
        status = STATUS_LABEL.get(c["status"], c["status"])
        cells = [
            '<td data-v="%s">%s</td>' % (e(c.get("dt") or ""), e(c.get("dt") or "—")),
            '<td title="%s">%s</td>' % (e(c["nm"]), e(_short(c["nm"], 34))),
        ]
        if show_co:
            cells.append('<td>%s</td>' % show_co(c))
        cells += [
            '<td title="%s">%s</td>' % (e(c.get("cl") or ""), e(_short(c.get("cl") or "—", 16))),
            '<td class="n" data-v="%s">%s</td>' % (m.get("amt") or -1, a_s),
            '<td class="n" data-v="%s">%s</td>' % (h[2] if h[2] is not None else -1, amt_s(c, h[2])),
            '<td class="n" data-v="%s">%s</td>' % (m["prog"] if m.get("prog") is not None else -1, pct(m.get("prog"))),
            '<td class="n" data-v="%s">%s</td>' % (m["gap_c"] if m.get("gap_c") is not None else -9,
                                                   ("%+.0f%%p" % (m["gap_c"] * 100)) if m.get("gap_c") is not None else "—"),
            '<td class="n" data-v="%s">%s</td>' % (m["recv_prog"] if m.get("recv_prog") is not None else -1, pct(m.get("recv_prog"))),
            '<td class="n" data-v="%s">%s</td>' % (((m.get("ar") or 0) - (m.get("adv") or 0)) if m.get("ar") is not None else -1e12,
                                                   (amt_s(c, m["ar"]) if m.get("ar") else ("선수 " + amt_s(c, m["adv"]) if m.get("adv") else amt_s(c, m.get("ar"))))),
            '<td class="n" data-v="%s">%s</td>' % (h[1] if h[1] is not None else -1, amt_s(c, h[1])),
            '<td>%s</td>' % e(span),
            '<td class="n" data-v="%s">%s</td>' % (m.get("slip_m") if m.get("slip_m") is not None else -999, eta),
            '<td>%s</td>' % led,
            '<td>%s %s</td>' % (e(status), chips(c)),
        ]
        out.append("<tr>%s</tr>" % "".join(cells))
    out.append("</tbody></table></div>")
    return "".join(out)


def _notes(prog):
    r = prog.get("rules") or {}
    return ('<p class="note">원천: %s. 금액은 원화 백만원을 억으로 표시한다. <b>진행</b> = 판매ㆍ공급 누적 ÷ 계약금액, '
            '<b>수령 진척</b> = 대금수령 누적 ÷ 계약금액, <b>매출채권(순)</b> = 공급 − 수령(음수면 선수금). '
            '<b>표준 곡선</b> = 이 탭에서 진행 중인 계약들의 경과 구간별 진행률 중앙값(단조 보정) — 진행은 시간에 선형이 아니라서 '
            '직선 대신 이 곡선과 비교한다(지연 의심 = %d%%p 이상 뒤처짐). <b>예상 완료</b> = 잔여 ÷ 최근 월 공급 속도(괄호 = 계약 종료일 대비 개월). '
            '외화 계약금액은 환산하지 않는다 — 원장 공시에 회사가 적은 원화 금액이 연결된 경우에만 그 값을 분모로 쓰고 \'원장\'으로 표시한다. '
            '<b>원장</b> 열: 확정 = 신고일이 탭 원장(단일판매ㆍ공급계약체결 공시) 접수일과 같고 금액·이름·상대방 근거가 있음, '
            '추정 = 근사 근거, XI 전용 = 원장에 근거 있는 짝 없음. 판매공급 누적은 매출·수주잔고(II-4)와 다른 축이라 더하지 않는다.</p>'
            % (e(prog.get("source")), abs(r.get("lag", -0.2)) * 100))


def company_section(prog, stock, title="계약 진행 — 반기·사업보고서 XI-1", anchor="xi1", limit=14):
    """회사 페이지 섹션. 진행 계약이 없으면 ''."""
    if not prog:
        return ""
    co = (prog.get("companies") or {}).get(stock)
    if not co:
        return ""
    items = [c for c in prog["contracts"] if c["stock"] == stock]
    if not items:
        return ""
    a = co["agg"]
    q = co.get("latest") or prog.get("asof")
    cur = [c for c in items if c["m"]["q"] == q]
    fx = ", ".join("%s %d" % kv for kv in sorted((a.get("fx") or {}).items()))
    tiles = [("%d건" % a["n"], "%s 진행 공시 계약%s" % (q, (" · 외화 " + fx) if fx else "")),
             (money(a["amt"]), "계약금액 합(원화 %d건)" % a["n_krw"]),
             ("%s · %s" % (money(a["sup"]), pct(a.get("prog_w"))), "판매ㆍ공급 누적 · 가중 진행"),
             (money(a["rem"]), "잔여(계약 − 공급)"),
             ("%s / %s" % (money(a["ar"]), money(a["adv"])), "매출채권(순) / 선수금(순)"),
             ("%s · %s년" % (money(a.get("pace_y")), ("%.1f" % a["burn_y"]) if a.get("burn_y") else "—"),
              "연 공급 속도 · 잔여 소진"),
             ("%d · %d · %d" % (a["lag"], a.get("overdue", 0), a["slip6"]), "지연 의심 · 납기 경과 · 지연 전망")]
    if a.get("rev_y"):
        tiles.append(("%s · %s배" % (pct(a.get("pace_rev")), ("%.1f" % a["rem_rev"]) if a.get("rem_rev") is not None else "—"),
                      "연 공급 ÷ 매출 · 잔여 ÷ 매출(매출 %s, 체결 공시 기재 · 추정)" % money(a["rev_y"])))
    bars = sorted([c for c in cur if _segs(c)], key=lambda c: -(c["m"].get("rem") or 0))[:limit]
    pts = [{"x": c["m"]["elapsed"], "y": c["m"]["prog"], "amt": c["m"].get("amt"), "label": c["nm"], "tip": "%s · %s" % (c["nm"], tip(c)),
            "hot": bool({"lag", "overdue"} & set(c["flags"]))}
           for c in cur if c["m"].get("elapsed") is not None and c["m"].get("prog") is not None]
    figs = []
    if bars:
        figs.append('<figure>%s<figcaption>계약별 진행(막대 = 계약금액 100%%, 잔여 큰 순 %d건) — 흰 눈금은 같은 경과의 탭 표준 진행</figcaption></figure>'
                    % (_bars_svg(bars, "계약별 진행 막대"), len(bars)))
    tl_rows = sorted([c for c in cur if c["m"].get("start") and c["m"].get("end") and c["m"].get("rem")],
                     key=lambda c: -(c["m"].get("rem") or 0))[:limit]
    tl_rows.sort(key=lambda c: c["m"]["end"])
    if tl_rows:
        import datetime as _d
        asof = _d.date(int(q[:4]), {"1": 3, "2": 6, "3": 9, "4": 12}[q[5]], 30 if q[5] in "23" else 31)
        figs.append('<figure>%s<figcaption>계약 기간과 공급 진행(채움) — 점선 = 보고 기간 말, 흰 눈금 = 같은 경과의 탭 표준 진행, '
                    '빨간 테두리 = 종료일이 지났는데 공급 95%% 미만. 잔여 큰 %d건을 종료일 순으로</figcaption></figure>'
                    % (_timeline_svg(tl_rows, asof, "계약 기간 타임라인"), len(tl_rows)))
    side = []
    ser = _series_svg(co.get("series") or {}, sorted(co.get("periods") or prog["periods"]), "반기별 계약금액 분해")
    if ser:
        side.append('<figure>%s<figcaption>보고 기간별 표에 실린 원화 계약의 분해 — 막대 높이 = 계약금액 합(건수는 아래)</figcaption></figure>' % ser)
    fl = co.get("flows") or {}
    if fl:
        lq = max(fl)
        side.append('<figure>%s<figcaption>%s → %s 잔여 다리(원화 계약)</figcaption></figure>'
                    % (_bridge_svg(fl[lq], "잔여 다리"), e(fl[lq]["from"]), e(lq)))
    if len(pts) >= 3:
        side.append('<figure>%s<figcaption>경과율 × 진행률(점 크기 = 계약금액, 빨강 = 지연 의심·납기 경과) — 흰 선은 탭 표준 곡선</figcaption></figure>'
                    % _scatter_svg(pts, prog.get("curve"), "경과율 대비 진행률 산점도", labels=3))
    order = sorted(items, key=lambda c: (c["status"] in ("done", "dropped"), -(c["m"].get("rem") or 0), c.get("dt") or ""))
    per = co.get("periods") or {}
    src = " · ".join('<a href="%s" target="_blank" rel="noopener">%s</a>' % (DART % p["rcp"], q2) if p.get("rcp") else q2
                     for q2, p in sorted(per.items()) if p.get("status") in ("ok", "unknown_headers"))
    return ('<section class="card xi1" id="%s"><h2>%s</h2>%s%s%s<div class="xg">%s</div>'
            '<h3>계약별 진행 표 <span class="mut">(%d건 · 완료·이탈 포함)</span></h3>%s%s%s'
            '<p class="note">보고서 원문: %s%s</p></section>'
            % (e(anchor), e(title), _kpis(tiles), _legend(), "".join(figs), "".join(side),
               len(items), _contract_table(order, "xi1t" + stock), _sched_table(cur), _notes(prog), src or "—",
               (" · %d월 결산 — 반기·사업보고서 기간이 달력 반기와 다르다" % co["fy"]) if co.get("fy") else ""))


def hub_section(prog, co_href=None, title="계약 진행 — 반기·사업보고서 XI-1", anchor="xi1", limit=15, peers=None,
                compare=True):
    """탭 첫 화면 섹션: 섹터 추이·회사별 잔여·산점도·주의 계약·금액 변동."""
    if not prog or not prog.get("contracts"):
        return ""
    s = prog["sector"]
    cos = prog["companies"]
    q = prog.get("asof")
    href = co_href or (lambda st: None)

    def co_cell(c):
        h = href(c["stock"])
        nm = cos.get(c["stock"], {}).get("name") or c["stock"]
        return '<a href="%s">%s</a>' % (e(h), e(nm)) if h else e(nm)

    tiles = [("%d / %d" % (s["cos_with_rows"], len(cos)), "진행 표가 있는 회사 / 모집단"),
             ("%d건" % s["n"], "최신 보고 진행 계약"),
             (money(s["rem"]), "잔여 합(원화)"),
             (pct(s.get("prog_w")), "가중 진행(공급 ÷ 계약)"),
             ("%s / %s" % (money(s["ar"]), money(s["adv"])), "매출채권(순) / 선수금(순)"),
             ("%s · %s년" % (money(s.get("pace_y")), ("%.1f" % s["burn_y"]) if s.get("burn_y") else "—"),
              "연 공급 속도 · 잔여 소진(최근 속도 기준)"),
             ("%d · %d · %d" % (s["lag"], s.get("overdue", 0), s["slip6"]), "지연 의심 · 납기 경과 · 지연 전망")]
    cur = [c for c in prog["contracts"] if c["status"] in ("active", "new") and "dup" not in c["flags"]]
    feed = _feed(prog, cur, co_cell)
    rows = sorted(((st, co) for st, co in cos.items() if co["agg"]["rem"] > 0), key=lambda x: -x[1]["agg"]["rem"])[:limit]
    figs = []
    ser = _series_svg(s.get("series") or {}, prog["periods"], "탭 반기별 계약금액 분해")
    if ser:
        figs.append('<figure>%s<figcaption>보고 기간별 합(그 기간 표가 있는 회사만 — 회사 수가 기간마다 다르다)</figcaption></figure>' % ser)
    pts = [{"x": c["m"]["elapsed"], "y": c["m"]["prog"], "amt": c["m"].get("amt"),
            "label": "%s %s" % (cos[c["stock"]]["name"], c["nm"]), "tip": "%s · %s · %s" % (cos[c["stock"]]["name"], c["nm"], tip(c)),
            "hot": bool({"lag", "overdue"} & set(c["flags"]))}
           for c in cur if c["m"].get("elapsed") is not None and c["m"].get("prog") is not None
           and "unit_suspect" not in c["flags"]]
    if len(pts) >= 3:
        figs.append('<figure>%s<figcaption>진행 계약 %d건의 경과율 × 진행률 — 흰 선 = 탭 표준 곡선, 빨강 = 지연 의심·납기 경과</figcaption></figure>'
                    % (_scatter_svg(pts, prog.get("curve"), "탭 경과율 대비 진행률", labels=5), len(pts)))
    fl = s.get("flows") or {}
    if fl:
        lq = max(fl)
        figs.append('<figure>%s<figcaption>%s → %s 잔여 다리 — 두 기간 모두 표가 있는 %d사 원화 계약</figcaption></figure>'
                    % (_bridge_svg(fl[lq], "잔여 다리"), e(fl[lq]["from"]), e(lq), fl[lq]["cos"]))
    cobar = ""
    if rows:
        top = rows[0][1]["agg"]["amt"] or 1
        W, LW, RW, H, G = 720, 150, 170, 14, 7
        BW = W - LW - RW
        hh = 8 + len(rows) * (H + G)
        sv = ['<svg viewBox="0 0 %d %d" role="img" aria-label="회사별 XI-1 잔여" xmlns="http://www.w3.org/2000/svg">' % (W, hh)]
        for i, (st, co) in enumerate(rows):
            a = co["agg"]
            y = 4 + i * (H + G)
            tot = BW * a["amt"] / top
            recv = max(a["sup"] - a["ar"], 0)
            x = LW
            sv.append('<g><title>%s · 계약 %s · 공급 %s(%s) · 잔여 %s · 매출채권 %s</title>' % (
                e(co["name"]), eok(a["amt"]), eok(a["sup"]), pct(a.get("prog_w")), eok(a["rem"]), eok(a["ar"])))
            sv.append('<text class="t1" x="%d" y="%d" text-anchor="end">%s</text>' % (LW - 8, y + 11, e(_short(co["name"], 12))))
            for val, col in ((recv, C_RECV), (a["ar"], C_AR), (a["adv"], C_ADV), (max(a["rem"] - a["adv"], 0), C_REM)):
                w = tot * (val / a["amt"]) if a["amt"] else 0
                if w > 0.2:
                    sv.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="%s"/>' % (x, y, max(w - 1, 0.5), H, col))
                x += max(w, 0)
            sv.append('<text x="%.1f" y="%d">잔여 %s · %s</text></g>' % (LW + tot + 8, y + 11, money(a["rem"]), pct(a.get("prog_w"))))
        sv.append("</svg>")
        cobar = ('<figure>%s<figcaption>회사별 원화 계약 합(막대 길이 = 계약금액, 조각 = 수령·매출채권·잔여), 잔여 큰 순 %d사</figcaption></figure>'
                 % ("".join(sv), len(rows)))
    watch = sorted([c for c in cur if {"lag", "overdue", "slip", "stalled", "reversal"} & set(c["flags"])],
                   key=lambda c: -(c["m"].get("rem") or 0))[:25]
    chg = sorted([c for c in cur if c["m"].get("chg_xi") or c["m"].get("chg_led")],
                 key=lambda c: -abs((c["m"].get("chg_xi") or c["m"].get("chg_led") or 0) * (c["m"].get("amt") or 0)))[:15]
    chg_html = ""
    if chg:
        tr = []
        for c in chg:
            m = c["m"]
            v = m.get("chg_xi") if m.get("chg_xi") is not None else m.get("chg_led")
            base = "직전 보고 대비" if m.get("chg_xi") is not None else "체결 공시 대비"
            tr.append('<tr><td>%s</td><td title="%s">%s</td><td class="n" data-v="%s">%s</td><td class="n" data-v="%s">%+.1f%%</td><td>%s</td></tr>'
                      % (co_cell(c), e(c["nm"]), e(_short(c["nm"], 34)), m.get("amt") or -1, eok(m.get("amt")), v, v * 100, base))
        chg_html = ('<h3>계약금액 변동 <span class="mut">(XI-1 계약금액이 이전 보고·체결 공시와 1%% 넘게 다른 진행 계약)</span></h3>'
                    '<div class="tbw"><table id="xi1chg" data-sortable><thead><tr><th>회사</th><th>계약</th><th class="n">현재 계약금액</th>'
                    '<th class="n">변동</th><th>기준</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(tr))
    ptab = _parties_table(s.get("parties") or [], "xi1p")
    if ptab:
        cobar += ('<h3>계약상대별 잔여 <span class="mut">(표기 묶음 — `(주)`·띄어쓰기·영문/한글 표기 차이를 합친다. '
                  '익명 상대는 같은 문구끼리만 묶여 실제 같은 상대인지는 모른다)</span></h3>' + ptab)
    return ('<section class="card xi1" id="%s"><h2>%s <span class="mut">%s</span></h2>%s%s%s<div class="xg">%s</div>%s'
            '<h3>주의 계약 <span class="mut">(지연 의심·납기 경과·지연 전망·정체·매출 역진, 잔여 큰 순 %d건)</span></h3>%s%s%s</section>'
            % (e(anchor), e(title), e(q), _kpis(tiles), feed, _legend(), "".join(figs), cobar, len(watch),
               _contract_table(watch, "xi1w", show_co=co_cell) if watch else '<p class="note">해당 계약 없음</p>',
               chg_html + (compare_section(prog, peers) if compare else ""), _notes(prog)))


def coverage_rows(prog):
    """coverage.html 용 표 — 회사 × 보고 기간 상태, 연결 품질, 원장 대응률."""
    if not prog:
        return ""
    qs = prog["periods"]
    lab = {"ok": "표", "no_table": "표 없음", "no_section": "절 없음", "no_report": "보고서 없음",
           "unknown_headers": "못 읽은 표", "error": "오류"}
    tr = []
    for st, co in sorted(prog["companies"].items()):
        a = co["agg"]
        cells = []
        for q in qs:
            p = co["periods"].get(q)
            if not p:
                cells.append('<td class="mut">—</td>')
                continue
            t = lab.get(p["status"], p["status"])
            if co.get("fy") and p["status"] == "no_report":
                t = "결산월 다름"
            if p.get("n"):
                t += " %d" % p["n"]
            if p.get("unit_fix"):
                t += " ·단위보정"
            if p.get("unit_suspect"):
                t += " ·단위의심"
            if p.get("sup_blank"):
                t += " ·공급 미기재"
            cls = "" if p["status"] == "ok" else ' class="mut"'
            cells.append('<td%s>%s</td>' % (cls, e(t)))
        cov = ("%d/%d" % (a["ledger_found"], a["ledger_live"])) if a.get("ledger_live") else "—"
        note = ""
        if co.get("fy"):
            own = [(q2, p2) for q2, p2 in sorted(co["periods"].items()) if q2 not in qs]
            note = "%d월 결산 — " % co["fy"] + ", ".join("%s %s" % (q2, lab.get(p2["status"], p2["status"])) for q2, p2 in own)
        tr.append('<tr><td>%s</td><td>%s</td>%s<td class="n">%d</td><td class="n">%d</td><td class="n">%d</td><td class="n">%s</td>'
                  '<td class="mut">%s</td></tr>'
                  % (e(st), e(co["name"]), "".join(cells), a["linkA"], a["linkB"], a["xi_only"], cov, e(note)))
    return ('<section class="card xi1" id="xi1cov"><h2>계약 진행(XI-1) 수집 상태</h2>'
            '<div class="tbw"><table id="xi1cv" data-sortable><thead><tr><th>종목</th><th>회사</th>%s'
            '<th class="n">원장 확정</th><th class="n">원장 추정</th><th class="n">XI 전용</th>'
            '<th class="n" title="탭 원장의 진행 기간 계약(2024년 이후 종료·해지 아님) 중 XI-1 에서 찾은 비율">원장 대응</th>'
            '<th>비고</th></tr></thead>'
            '<tbody>%s</tbody></table></div><p class="note">표 = 진행 현황 표를 읽음(숫자 = 계약 행), 표 없음 = 절은 있으나 '
            '판매ㆍ공급계약 진행 표가 없음(증자·해명 공시만 있는 회사), 절 없음·보고서 없음 = 그 기간 보고서에 XI-1 절이 없거나 보고서 미접수, '
            '공급 미기재 = 표는 있으나 판매ㆍ공급·대금수령 칸을 대부분 비움(진행률 없음 — 0 으로 보지 않는다). '
            '12월이 아닌 결산 회사는 그 회사의 반기·사업보고서 기간을 따로 받아 비고에 적는다(3S 3월 결산 → 9월·3월). '
            '못 읽은 표는 머리행 대기열(hdr_queue.json, role xi)로 간다.</p></section>'
            % ("".join("<th>%s</th>" % q for q in qs), "".join(tr)))
