#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_parse — 반도체장비 정기보고서 절 → 이 탭의 축.

표 추출(머리행 평탄화·셀 병합 전개)은 `kce_parse.parse_tables` 를 그대로 쓴다.
여기서 새로 만드는 것은 **그 위의 네 가지 추출기**다.

| 함수 | 절 | 뽑는 것 |
|---|---|---|
| `orders` | II-4 다. 수주상황 | 수주총액·기납품액·수주잔고(품목별) + 미공시 사유 |
| `sales` | II-4 가. 매출실적 | 제품·품목별 매출, 수출/내수(또는 국내/해외) |
| `revenue_basis` | III 주석 「고객과의 계약에서 생기는 수익」 | 인식 시점(인도/설치완료/진행기준) + **원문 인용** |
| `customers` | III 주석 「영업부문 — 주요 고객에 대한 공시」 | 10% 이상 고객별 매출(익명 포함) |

## 왜 `kce_parse.parse_ii4` 를 쓰지 않는가 (원문 두 건이 그렇게 만들었다)

1. **단위 캡션이 열 머리행 셀 안에 들어간다.** 한미반도체 2026 반기 수주상황표의 금액
   열 이름은 `금 액 (단위: 원)` 이고, 표 앞 문맥(lead)에도 첫 머리행에도 단위가 없다.
   `parse_ii4` 는 표 단위 하나만 보므로 `44,200,000,000`(=442억) 을 백만원으로 읽어
   **44.2조**가 된다. → 단위는 **열마다** 읽고(`unit_of`), 표 단위와 다르면 열 단위가 이긴다.
   어디서도 못 읽으면 `unit_seen=False` 로 남기고 **금액을 쓰지 않는다**(fail-closed).
2. **머리행이 두 줄인데 둘째 줄이 데이터 행으로 내려온다.** 같은 표의 첫 머리행은
   `수주총액|수주총액|기납품액|…` 처럼 상위 라벨만 반복되고, `수 량|금 액` 은 첫
   데이터 행에 있다. 평탄화가 안 되면 `수주총액`이 두 열에 같은 이름으로 걸려
   **먼저 나오는 수량 열**이 금액으로 매핑된다(값이 `-` 라 조용히 사라진다).
   → `resolve_header` 가 머리행을 끝까지 걷어 `수주총액 금 액` 으로 합친다.
3. **합계 행이 곧 알맹이다.** 원익IPS 수주상황표는 품목이 `반도체/Display 장비` 한 줄이고
   합계가 같은 값이다. 건설(kce)은 현장 행이 목적이라 합계를 버리지만, 장비사는 잔고
   **총계**가 KPI다. → 합계 행을 버리지 않고 `total=True` 로 남겨 부문합과 대조한다
   (COMMON §2 — 합계 셀이 깨진 원문이 실제로 있다).

열 이름 → 표준 필드 사전은 `kce_lib.COL_ALIAS` 를 쓴다(표준 제조업형 수주상황표
`품목|수주일자|납기|수주총액(수량,금액)|기납품액(수량,금액)|수주잔고(수량,금액)` 이
이미 들어 있다 — 두 벌로 갈라지면 한쪽만 고쳐진다).

규약: stdlib 전용 · fail-closed · 추정 금지.
"""
import html as _html
import re

from ksemi_lib import COL_ALIAS, norm_col, num_of, parse_tables
from kce_parse import _UNIT_RE, _UNIT_SCALE

# ── 머리행 해소 ─────────────────────────────────────────────

# 머리행 판정 어휘. 숫자가 없다는 조건만으로는 '-'만 찬 데이터 행을 머리행으로 오인한다.
_HDR_WORDS = (
    "품목", "품 목", "구분", "구 분", "용도", "매출유형", "수주", "납기", "납 기",
    "기납품", "잔고", "수량", "수 량", "금액", "금 액", "매출", "수출", "내수",
    "국내", "해외", "합계", "합 계", "기간", "계약", "비고", "지역", "고객", "단위",
    "부문", "제품", "상품", "용역", "기타", "당기", "전기", "수익",
)
_PERIOD = re.compile(r"제\s*\d+\s*기|(?:19|20)\d{2}\s*년|당[기반]기|전[기반]기|반기|분기")
_SUM_LABEL = ("합계", "합 계", "총계", "소계", "계", "부문합계", "제품과용역합계")


def _txt(s):
    return re.sub(r"[\s\xa0]+", " ", _html.unescape(s or "")).strip()


def is_header_row(cells):
    """이 행이 머리행의 이어지는 줄인가."""
    vals = [_txt(c) for c in cells if _txt(c)]
    if not vals:
        return False
    if any(num_of(v) is not None for v in vals):
        return False
    joined = " ".join(vals)
    return any(w in joined for w in _HDR_WORDS) or bool(_PERIOD.search(joined))


def resolve_header(t):
    """parse_tables 결과 한 장 → (cols, ncols, fields, rows).

    `cols` 가 비면 첫 행을 머리행으로 올리고, `cols` 가 있어도 첫 행이 머리행의
    이어지는 줄이면 **세로로 이어 붙인다**(`수주총액` + `금 액` → `수주총액 금 액`).
    머리행을 걷다 데이터가 한 행도 안 남으면 걷기를 되돌린다 — 머리행만 있는 표
    (단위 캡션 전용 표)를 데이터 표로 착각하지 않기 위해.
    """
    cols = [_txt(c) for c in (t.get("cols") or [])]
    rows = [[_txt(c) for c in r] for r in (t.get("rows") or [])]
    while rows and is_header_row(rows[0]) and len(rows) > 1:
        head = rows.pop(0)
        n = max(len(cols), len(head))
        # 같은 라벨을 두 번 이어 붙이지 않는다. 병합 셀이 전개되면 상위 라벨이 아래
        # 줄에도 복제돼 오는 회사가 있어(한미반도체 `품 목`/`품 목`) 그대로 합치면
        # `품목품목` 이 되고 COL_ALIAS 에서 nm 매핑이 사라진다 — 품목 열이 통째로 빈다.
        merged = []
        for i in range(n):
            parts = [x for x in (cols[i] if i < len(cols) else "",
                                 head[i] if i < len(head) else "") if x]
            uniq = []
            for p in parts:
                if norm_col(p) not in [norm_col(u) for u in uniq]:
                    uniq.append(p)
            merged.append(" ".join(uniq).strip())
        cols = merged
    ncols = [norm_col(c) for c in cols]
    fields = [COL_ALIAS.get(c) for c in ncols]
    return cols, ncols, fields, rows


# ── 단위 ───────────────────────────────────────────────────

def _scale_of(text):
    """'(단위 : 천원)' → 백만원 환산 배수. 캡션이 없으면 None(있는데 모르면 1.0 아님)."""
    m = _UNIT_RE.findall(text or "")
    if not m:
        return None
    s = m[-1].replace(" ", "")
    for name, mul in _UNIT_SCALE:          # 긴 단위부터(십억원 > 억원 > 원)
        if name in s:
            return mul
    return None


def unit_of(t, cols):
    """표 단위와 **열별 단위**. 반환 `{"scale","seen","raw","per_col":{i:scale}}`.

    표 단위는 lead → 머리행 전체 순으로 찾는다. 열별 단위는 그 열 이름 안의 캡션이며,
    표 단위와 다르면 **열 단위가 이긴다**(한미반도체 `금 액 (단위: 원)`).
    """
    lead = _txt(t.get("lead"))
    scale = _scale_of(lead)
    raw = None
    if scale is not None:
        m = _UNIT_RE.findall(lead)
        raw = m[-1].strip() if m else None
    per = {}
    for i, c in enumerate(cols):
        s = _scale_of(c)
        if s is not None:
            per[i] = s
    if scale is None and per:
        # 표 단위는 없고 열 단위만 있다 — 그 열 단위를 표 단위로도 쓰지 않는다.
        # (수량 열과 금액 열의 단위가 다르기 때문이다)
        pass
    return {"scale": scale, "seen": scale is not None or bool(per),
            "raw": raw, "per_col": per}


def _money(cell, i, unit):
    """셀 → 백만원. 단위를 어디서도 못 읽었으면 None(값을 쓰지 않는다)."""
    v = num_of(cell)
    if v is None:
        return None
    sc = unit["per_col"].get(i, unit["scale"])
    if sc is None:
        return None                      # fail-closed: 단위 미확인 금액은 버린다
    if sc == 1.0:
        return v
    if sc >= 1 and float(sc).is_integer():
        x = v * int(sc)                  # 억원→백만원: 정수배(오차 없음)
    else:
        x = round(v * sc, 6)             # 천원·원→백만원
    return int(x) if float(x).is_integer() else x


def is_total(label):
    return norm_col(label) in [norm_col(s) for s in _SUM_LABEL]


# ── II-4 다. 수주상황 ───────────────────────────────────────

_ORDER_NEED = ("amt", "cmp", "bal")
# 수주 절을 찾는 문맥 낱말. 매출실적 표와 같은 절에 있으므로 표마다 구분해야 한다.
_ORDER_MARK = ("수주상황", "수주현황", "수주잔고", "수주총액")
# 수주표가 없을 때 그 **이유**로 인정할 원문 문구(지어내지 않기 위해 원문에서 찾는다).
_NODISC_MARK = ("기재하지 않", "기재를 생략", "해당사항 없", "해당 사항 없",
                "공시하지 않", "작성하지 않", "영업기밀", "노출될 수 있어")


def orders(html):
    """II-4 절 HTML → 수주상황.

    반환:
      `{"tables":[{lead,cols,unit,rows:[{nm,sd,ed,amt,cmp,bal,total}]}],
        "backlog":합계잔고, "order_amt":합계수주총액, "delivered":합계기납품,
        "grain":"item|total", "disclosed":bool, "unit_seen":bool,
        "note":미공시 사유 인용, "unknown_headers":[...]}`

    합계는 **원문 합계 행을 우선 신뢰**하고, 합계 행이 없으면 품목 행을 더한다.
    둘 다 있으면 대조해 1% 넘게 어긋나면 `recon` 에 남긴다(조용히 고르지 않는다).
    """
    out = {"tables": [], "backlog": None, "order_amt": None, "delivered": None,
           "grain": None, "disclosed": False, "unit_seen": False, "note": "",
           "unknown_headers": [], "recon": None}
    body = _txt(re.sub(r"<[^>]+>", " ", html or ""))
    for t in parse_tables(html):
        lead = _txt(t.get("lead"))
        cols, ncols, fields, rows = resolve_header(t)
        if not rows:
            continue
        idx = {}
        for i, f in enumerate(fields):
            if f and f not in idx:
                idx[f] = i
        if not all(f in idx for f in _ORDER_NEED):
            if sum(1 for f in fields if f in ("amt", "cmp", "bal")) >= 2:
                out["unknown_headers"].append({"cols": cols, "n": len(rows)})
            continue
        # 수주표인지 매출표인지는 **열 이름**으로 가른다(lead는 절 전체가 섞여 온다).
        if not any(m in " ".join(ncols) for m in ("수주총액", "수주잔고", "기납품액")):
            continue
        unit = unit_of(t, cols)
        recs = []
        for r in rows:
            def cell(f):
                i = idx.get(f)
                return r[i] if i is not None and i < len(r) else ""
            nm = cell("nm")
            # 합계 판정은 품목 열만 보지 않는다. 병합 셀이 전개되면 합계 행의 라벨이
            # 여러 열에 복제되고(원익IPS `합 계|합 계|합 계|…`), 품목 열 매핑이 실패한
            # 표에서는 품목 칸이 빈다 — 그때 합계 행을 품목 행으로 세면 잔고가 두 배가
            # 된다(한미반도체 44,200 → 88,400 실사고).
            rec = {"nm": nm, "sd": cell("sd"), "ed": cell("ed"),
                   "amt": _money(cell("amt"), idx.get("amt"), unit),
                   "cmp": _money(cell("cmp"), idx.get("cmp"), unit),
                   "bal": _money(cell("bal"), idx.get("bal"), unit),
                   "total": any(is_total(c) for c in r)}
            if not nm and rec["amt"] is None and rec["bal"] is None:
                continue
            recs.append(rec)
        if not recs:
            continue
        out["tables"].append({"lead": lead[-160:], "cols": cols, "unit": unit,
                              "rows": recs})
        out["unit_seen"] = out["unit_seen"] or unit["seen"]
    # 합계 확정
    tot_rows = [r for tb in out["tables"] for r in tb["rows"] if r["total"]]
    item_rows = [r for tb in out["tables"] for r in tb["rows"] if not r["total"]]
    if out["tables"]:
        out["disclosed"] = True
        out["grain"] = "item" if item_rows else "total"
        for key in ("amt", "cmp", "bal"):
            field = {"amt": "order_amt", "cmp": "delivered", "bal": "backlog"}[key]
            t_sum = _sum([r[key] for r in tot_rows])
            i_sum = _sum([r[key] for r in item_rows])
            out[field] = t_sum if t_sum is not None else i_sum
            if t_sum is not None and i_sum is not None and t_sum:
                gap = abs(t_sum - i_sum) / abs(t_sum)
                if gap > 0.01:
                    out["recon"] = out["recon"] or {}
                    out["recon"][field] = {"total_row": t_sum, "item_sum": i_sum,
                                           "gap_pct": round(100 * gap, 2)}
    else:
        for m in _NODISC_MARK:
            i = body.find(m)
            if i >= 0 and any(k in body[max(0, i - 300):i + 100] for k in _ORDER_MARK):
                out["note"] = body[max(0, i - 200):i + 120].strip()
                break
    return out


def _sum(vals):
    vs = [v for v in vals if v is not None]
    if not vs:
        return None
    s = sum(vs)
    return int(s) if float(s).is_integer() else s


# ── II-4 가. 매출실적 ───────────────────────────────────────

_CH_EXPORT = ("수출", "해외", "국외")
_CH_DOMESTIC = ("내수", "국내")
_CH_TOTAL = ("합계", "합 계", "계", "총계")


def _channel(cells):
    """행에서 수출/내수/합계 구분 셀을 찾는다. 반환 (kind, 'exp|dom|tot', 라벨).

    **수출·내수가 합계보다 세다.** 앞에서부터 처음 걸리는 것을 쓰면 원익IPS 별도표의
    총계 행(`합 계|합 계|합 계|수 출`)이 '합계'로 분류돼 수출 총액이 통째로 사라진다 —
    이 행이 바로 수출 비중의 분자다.
    """
    exp = dom = tot = None
    for c in cells:
        n = norm_col(c)
        if exp is None and n in [norm_col(x) for x in _CH_EXPORT]:
            exp = c
        elif dom is None and n in [norm_col(x) for x in _CH_DOMESTIC]:
            dom = c
        elif tot is None and n in [norm_col(x) for x in _CH_TOTAL]:
            tot = c
    if exp is not None:
        return ("국내해외" if norm_col(exp) in ("해외", "국외") else "수출내수"), "exp", exp
    if dom is not None:
        return ("국내해외" if norm_col(dom) == "국내" else "수출내수"), "dom", dom
    if tot is not None:
        return None, "tot", tot
    return None, None, None


def sales(html):
    """II-4 매출실적 절 → 제품·품목별 매출과 수출/내수.

    회사마다 표가 여러 벌이다(원익IPS는 연결 제품/기타 + 연결 국내/해외 + 별도 품목별).
    **한 벌을 고르지 않고 전부 담고**, 대표값은 `수출내수` 구분이 붙은 표에서 뽑는다
    (`국내해외` 는 지역 정보라 수출 비중과 뜻이 다르다 — 섞으면 안 된다).
    """
    out = {"tables": [], "export": None, "domestic": None, "total": None,
           "channel_kind": None, "unit_seen": False, "recon": None,
           "period_label": None}
    for t in parse_tables(html):
        lead = _txt(t.get("lead"))
        cols, ncols, fields, rows = resolve_header(t)
        if not rows or len(cols) < 2:
            continue
        per = [i for i, c in enumerate(cols) if _PERIOD.search(c)]
        if not per:
            continue
        unit = unit_of(t, cols)
        if not unit["seen"]:
            # 매출실적 표에 단위가 없는 일은 드물다. 조용히 1.0으로 두면 천원 표가
            # 1000배로 실린다 — 표를 담되 금액은 비우고 표시한다.
            pass
        recs = []
        for r in rows:
            labels = [r[i] for i in range(len(cols))
                      if i not in per and i < len(r) and r[i]]
            kind, ch, chlabel = _channel([r[i] for i in range(len(cols))
                                          if i not in per and i < len(r)])
            vals = {}
            for i in per:
                vals[cols[i]] = _money(r[i] if i < len(r) else "", i, unit)
            if all(v is None for v in vals.values()):
                continue
            # 표 전체의 총계 행인가 — **구분 셀은 빼고** 본다. 구분이 '합 계'인 행
            # (품목별 수출+내수 소계)까지 총계로 세면 합계가 두 번 더해진다.
            rest = list(labels)
            if chlabel in rest:
                rest.remove(chlabel)
            recs.append({"labels": labels, "channel": ch, "channel_label": chlabel,
                         "channel_kind": kind, "vals": vals,
                         "total": any(is_total(x) for x in rest)})
        if not recs:
            continue
        out["tables"].append({"lead": lead[-160:], "cols": cols, "unit": unit,
                              "periods": [cols[i] for i in per], "rows": recs})
        out["unit_seen"] = out["unit_seen"] or unit["seen"]
    # 대표 수출/내수 — '수출내수' 구분이 있는 표를 우선, 없으면 '국내해외'
    for want in ("수출내수", "국내해외"):
        for tb in out["tables"]:
            if not tb["periods"]:
                continue
            p = tb["periods"][0]                  # 첫 기간 열 = 당기(공시 관례)
            rows = [r for r in tb["rows"] if r["channel_kind"] == want
                    or (r["channel"] == "tot" and want == (r["channel_kind"] or want))]
            if not any(r["channel"] in ("exp", "dom") for r in rows):
                continue
            tot_rows = [r for r in rows if r["total"]]
            src = tot_rows or rows
            exp = _sum([r["vals"].get(p) for r in src if r["channel"] == "exp"])
            dom = _sum([r["vals"].get(p) for r in src if r["channel"] == "dom"])
            tot = _sum([r["vals"].get(p) for r in src if r["channel"] == "tot"])
            if exp is None and dom is None:
                continue
            out.update({"export": exp, "domestic": dom,
                        "total": tot if tot is not None else _sum([exp, dom]),
                        "channel_kind": want, "period_label": p})
            if tot is not None and exp is not None and dom is not None and tot:
                gap = abs((exp + dom) - tot) / abs(tot)
                if gap > 0.01:
                    out["recon"] = {"exp_plus_dom": exp + dom, "total_row": tot,
                                    "gap_pct": round(100 * gap, 2)}
            return out
    return out


# ── III 주석 「수익」 — 매출인식 시점 ────────────────────────

# 인식 시점 축. **순서가 판정 우선순위**다 — 진행기준 문구가 있으면 그것이 지배적이다.
# 낱말은 원익IPS 2025 사업보고서 주석 3-18에서 실제로 읽은 표현에서 시작했다
# ("설비의 판매 수익은 자산에 대한 통제가 고객에게 이전되는 시점인 설치완료 시점에 인식").
BASIS_RULES = [
    ("진행기준", ("진행기준", "기간에 걸쳐 인식", "기간에 걸쳐 수익", "투입법", "산출법",
                  "진행률", "기간에걸쳐")),
    ("설치완료", ("설치완료", "설치가 완료", "설치완료시점", "설치 완료", "검수",
                  "SAT", "시운전 완료", "설치용역이 완료")),
    ("인도", ("인도되는 시점", "인도시점", "인도 시점", "고객에게 인도", "선적",
              "인수증", "통제가 고객에게 이전되는 시점")),
]
# 수익 주석의 시작점. 회계정책 절 전체(3만자)를 그냥 훑으면 엉뚱한 문단이 걸린다 —
# '선적'은 금융자산 제거 문단에도 나오고 '진행률'은 공사계약과 무관한 데서도 나온다.
_REV_ANCHOR = ("고객과의 계약에서 생기는 수익", "고객과의계약에서생기는수익",
               "수익인식", "수익 인식", "수익의 인식", "고객과의 계약에서 발생하는 수익")
_REV_SCOPE = 6000          # 앵커 이후 이 길이까지만 본다
_QUOTE_MUST = ("수익", "매출", "인식", "판매", "이전")


def revenue_basis(html):
    """주석 본문 → 인식 시점과 **원문 인용**.

    반환 `{"bases":[{"key","phrase","quote"}], "primary":key|None, "found":bool,
           "scoped":bool}`. 추정하지 않는다 — 어느 낱말도 안 걸리면 `primary=None`,
    `found=False` 로 남기고 화면에는 '원문에서 확인 못 함'으로 뜬다.

    반기·분기보고서에는 이 주석이 없다(원익IPS 2026 반기의 「중요한 회계정책」 절은
    4.2KB로 축약돼 수익 문단이 통째로 빠져 있다). **사업보고서에서만** 받는다.
    """
    text = _txt(re.sub(r"<[^>]+>", " ", html or ""))
    out = {"bases": [], "primary": None, "found": False, "scoped": False}
    scope = text
    for a in _REV_ANCHOR:
        i = text.find(a)
        if i >= 0:
            scope = text[i:i + _REV_SCOPE]
            out["scoped"] = True
            break
    for key, words in BASIS_RULES:
        for w in words:
            i = scope.find(w)
            if i < 0:
                continue
            # 그 낱말을 담은 문장을 인용으로 남긴다(마침표 경계, 최대 320자).
            s = scope.rfind(".", 0, i) + 1
            e = scope.find(".", i)
            quote = scope[s:(e + 1 if e > 0 else min(len(scope), i + 320))].strip()
            if not any(m in quote for m in _QUOTE_MUST):
                continue          # 수익과 무관한 문단에 묻어 온 낱말 — 버린다
            quote = quote[:320]
            # **한 문장은 한 번만 판정한다.** 원익IPS 주석의 *"설비의 판매 수익은 자산에
            # 대한 통제가 고객에게 이전되는 시점인 설치완료 시점에 인식됩니다"* 한 문장에는
            # `설치완료` 와 `통제가 고객에게 이전되는 시점`(인도 낱말)이 같이 있다. 그냥
            # 두면 **같은 인용이 「설치완료」와 「인도」로 두 번** 화면에 실린다. 위의
            # 우선순위가 이미 지배 낱말을 골랐으므로 같은 문장은 다시 세지 않는다.
            if any(b["quote"] == quote for b in out["bases"]):
                break
            out["bases"].append({"key": key, "phrase": w, "quote": quote})
            break
    if out["bases"]:
        out["found"] = True
        out["primary"] = out["bases"][0]["key"]
    return out


# ── III 주석 영업부문 — 주요 고객 ───────────────────────────

# 익명 고객 열 이름. 회사마다 방언이 다르다 — 원익IPS `A사`, 한미반도체 `거래처 A`.
# 실명(삼성전자·SK하이닉스)이면 여기 안 걸리고 `anonymous=False` 로 남는다.
_ANON = re.compile(r"^(?:[A-Z]{1,2}사|거래처[A-Z0-9]{1,2}|고객[A-Z0-9]{1,2}"
                   r"|주요고객\d+|[가-하]사)$")
_CUST_MARK = ("주요 고객", "주요고객")
_REV_ROW = ("수익(매출액)", "수익", "매출액", "매출", "외부고객으로부터의수익")
# 고객 표의 매출 행·비율 행 판정. 한미반도체 2025 사업보고서의 행 이름은
# `주요 고객에 대한 수익(매출액), 매출액의 10% 이상 비중` 이고 바로 아래 행이
# `기업전체 수익에 대한 비율` 로 **비중을 원문이 직접 적어 준다** — 그 값을 쓴다.
_RATIO_ROW = re.compile(r"비율|비중")
_AMT_ROW = re.compile(r"수익|매출")
_TOTAL_COL = ("합계", "총계", "고객합계")


def customers(html):
    """영업부문 주석 → 10% 이상 주요 고객별 매출(당기).

    **당기·전기 비교표가 나란히 온다.** 전기 표를 같이 더하면 값이 두 배가 된다
    (COMMON §2의 삼성중공업 헤지 사고와 같은 종류). 판정은 표 앞 문맥의 `당기`/`전기`
    표지로 한다 — 원익IPS 2025 사업보고서에서 당기 표의 lead 는
    `주요 고객에 대한 공시 당기 (단위 : 천원)`, 전기 표는 `전기 (단위 : 천원)` 이다.
    """
    out = {"rows": [], "anonymous": None, "period": None, "unit_seen": False,
           "found": False, "skipped_prior": 0, "customers_total": None,
           "share_source": None}
    for t in parse_tables(html):
        lead = _txt(t.get("lead"))
        cols, ncols, fields, rows = resolve_header(t)
        if not rows or len(cols) < 2:
            continue
        if not any(m in lead for m in _CUST_MARK):
            # 전기 표의 lead 는 '전기 (단위 : 천원)' 뿐이어서 고객 표지가 없다.
            # 그래도 열 이름이 익명 고객(A사·거래처 A)이면 고객 표로 본다.
            if not any(_ANON.match(norm_col(c)) for c in cols[1:] if c):
                continue
        rev = ratio = None
        for r in rows:
            lab = norm_col(r[0])
            if ratio is None and _RATIO_ROW.search(lab) and not _AMT_ROW.search(lab):
                ratio = r
            elif rev is None and (lab in [norm_col(x) for x in _REV_ROW]
                                  or _AMT_ROW.search(lab)):
                rev = r
        if rev is None:
            continue
        period = "당기" if "당기" in lead else ("전기" if "전기" in lead else None)
        if period == "전기" or (out["found"] and period != "당기"):
            out["skipped_prior"] += 1
            continue
        unit = unit_of(t, cols)
        recs, total = [], None
        for i, lab in enumerate(cols[1:], start=1):
            v = _money(rev[i] if i < len(rev) else "", i, unit)
            if v is None or not lab:
                continue
            if any(w in norm_col(lab) for w in _TOTAL_COL):
                total = v                 # '고객 합계' 열 — 고객이 아니라 소계다
                continue
            sh = None
            if ratio is not None and i < len(ratio):
                x = num_of(ratio[i])
                if x is not None:
                    # 원문이 0.4396(비율)로 적거나 43.96(%)으로 적는다 — 1 이하면 비율.
                    sh = round(100.0 * x, 1) if abs(x) <= 1 else round(x, 1)
            recs.append({"label": lab, "amount": v,
                         "anonymous": bool(_ANON.match(norm_col(lab))),
                         "share": sh})
        if not recs:
            continue
        out.update({"rows": recs, "period": period or "당기",
                    "unit_seen": unit["seen"], "found": True,
                    "customers_total": total,
                    "share_source": "원문" if any(r["share"] is not None
                                                  for r in recs) else None,
                    "anonymous": all(r["anonymous"] for r in recs)})
        return out
    return out


def segment_revenue(html):
    """영업부문 주석의 당기 부문 매출 합계(고객 집중도의 분모).

    반환 `{"total":백만원|None,"quote":열이름}`. 합계 열을 못 찾으면 None —
    분모를 추정하지 않는다(비중이 없으면 화면에 비중을 안 쓴다).

    **고객 표를 부문 표로 착각하면 안 된다.** 원익IPS 별도 영업부문 절은 부문 표가 아예
    없고(단일부문) 고객 표부터 시작하는데, lead 에 `6. 영업부문` 이 남아 있어 'lead에
    영업부문이 있으면 부문 표'로 두면 마지막 고객(C사 956억)을 전체 매출로 읽는다.
    그래서 **합계/총계 열이 이름으로 확인될 때만** 값을 쓴다.
    """
    for t in parse_tables(html):
        lead = _txt(t.get("lead"))
        cols, ncols, fields, rows = resolve_header(t)
        if not rows or not cols:
            continue
        if "전기" in lead and "당기" not in lead:
            continue
        heads = [c for c in cols[1:] if c]
        # 익명 고객 열이 **하나라도** 있으면 고객 표다. 한미반도체 고객 표의 마지막
        # 열은 `고객 합계` 라서 '합계 열이 있으면 부문 표' 규칙에 걸린다 — 그 값
        # (3,390억)을 전체 매출로 읽으면 최대고객 비중이 75%로 부풀어 오른다.
        if any(_ANON.match(norm_col(c)) for c in heads):
            continue
        if any(m in lead[-120:] for m in _CUST_MARK):
            continue
        rev = None
        for r in rows:
            if norm_col(r[0]) in [norm_col(x) for x in _REV_ROW]:
                rev = r
                break
        if rev is None:
            continue
        unit = unit_of(t, cols)
        for i in range(len(cols) - 1, 0, -1):
            if any(w in norm_col(cols[i]) for w in ("합계", "총계")):
                v = _money(rev[i] if i < len(rev) else "", i, unit)
                if v is not None:
                    return {"total": v, "quote": cols[i]}
    return {"total": None, "quote": ""}
