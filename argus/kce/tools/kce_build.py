#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_build — 한국건설 DATA 증분 갱신 빌더 (v1).

kce_fetch가 받은 절 HTML을 파싱해 argus/kce/<co>/index.html의 `const DATA`를 갱신한다.
갱신 로직 전체 설계는 UPDATE.md, 데이터 계약은 LOGIC.md. v1 범위:
  · II-4 실측값(amt/cmp/bal/pr) 갱신·신규 사업장 생성·변경 이벤트(ev) 감지
  · III-8(p8) 연결/별도 값 갱신 — 별도=연결 동일값이면 연결 생략(원 빌더 규칙),
    표의 연결/별도 배정은 직전 분기와의 연속성 점수로 판정(순서 관행이 회사·분기별로 뒤집힘)
  · rev.diff / summary / revSummary 재집계 (수치검증된 규칙: 실측 bal·agg 제외·명시행 합)
  · 분기축 확장(fq 19→20, fqF 23→24)과 S-curve 리베이스 예측(fcst) 재계산
  · --apply 시 matrix.html·trace.html 재생성(kce_render — 바이트 단위 동치 검증됨)
  · fail-closed: 검증 실패 시 파일을 건드리지 않고 비정상 종료. --apply 없으면 dry-run.
v1 미범위(UPDATE.md §5·§6 로드맵): coRev(실제 매출)·XI-1 수시공시 반영, interp/bcst 재계산,
prC/prCv 갱신, backtest·curve·headers 재생성(갱신 후 스테일 — 경고 출력).

사용례:
  python3 kce_fetch.py --co sct --quarter 2026Q3 --out raw/
  python3 kce_build.py --co sct --quarter 2026Q3 --raw raw/ --apply
"""
import argparse
import datetime
import json
import os
import re
import sys

import kce_render
from kce_lib import CORP, atomic_write, extract_data, inject_data, norm_col, q_next
from kce_parse import parse_ii4, parse_p8, region_of

HERE = os.path.dirname(os.path.abspath(__file__))
KCE = os.path.dirname(HERE)
with open(os.path.join(HERE, "assets", "curve_D.json"), encoding="utf-8") as _f:
    CURVE = json.load(_f)

# III-8 표는 공사명 끝에 공종을 덧붙이는 회사가 있다(`GTPP (화공플랜트)`).
# 그 접미만 떼어 II-4 이름과 잇되, 별개 계약을 구분하는 접미는 남겨야 한다
# (삼성E&A `CC-7`과 `CC-7 (Eng'g&PRM Service)`는 서로 다른 계약이다).
_PAREN_TAIL = re.compile(r"\(([^)]*)\)$")
_SEG_WORDS = ("플랜트", "화공", "토목", "건축", "주택", "인프라", "전력",
              "발전", "신사업", "기타")


def strip_seg_suffix(key):
    """정규화된 이름 끝의 괄호 접미가 **공종 표기일 때만** 떼어낸다."""
    m = _PAREN_TAIL.search(key)
    if not m:
        return key
    tail = m.group(1)
    if not tail or not all("가" <= c <= "힣" for c in tail):
        return key                      # 영문·기호가 섞이면 계약 구분으로 본다
    if not any(w in tail for w in _SEG_WORDS):
        return key
    return key[:m.start()]

_AGG_NM = re.compile(r"(합계|^기타|^계$|^소계$|외\d*개현장)")


def _norm_nm(s):
    return norm_col(s or "")


def _is_agg(rec):
    return bool(_AGG_NM.search(_norm_nm(rec.get("nm"))))


def _qend(q):
    y, n = int(q[:4]), int(q[5])
    return datetime.date(y, n * 3, 28)


def _date(s):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    return datetime.date(*map(int, m.groups())) if m else None


def _last_day(y, m):
    return (datetime.date(y + (m == 12), m % 12 + 1, 1)
            - datetime.timedelta(days=1)).day


def norm_date(s, end=False):
    """원문 날짜 표기 → 'YYYY-MM-DD'. 'YYYY년 M월'은 착공=1일, 완공=말일 관행(dwe 검증).
    해석 불가 시 원문 유지."""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})\s*일?\.?$", s)
    if m:
        return "%04d-%02d-%02d" % tuple(map(int, m.groups()))
    m = re.match(r"^(\d{4})[.\-/년]\s*(\d{1,2})\s*월?\.?$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return "%04d-%02d-%02d" % (y, mo, _last_day(y, mo) if end else 1)
    return s


# ── S-curve 리베이스 예측 (fcst) ─────────────────────────────

def _p50(key, x):
    tab = CURVE.get(key) or CURVE["전체"]
    rows = [(r[0], r[3]) for r in tab]           # (버킷중심, p50)
    if x <= rows[0][0]:
        return rows[0][1] * 100
    for (x0, y0), (x1, y1) in zip(rows, rows[1:]):
        if x <= x1:
            return (y0 + (y1 - y0) * (x - x0) / (x1 - x0)) * 100
    return rows[-1][1] * 100


def _fcst_pr(site, k_anchor, k_target, fqF):
    """앵커 분기의 실측 진행률에 곡선을 리베이스해 미래 진행률 추정."""
    sd, ed = _date(site.get("sd")), _date(site.get("ed"))
    if not sd or not ed or ed <= sd:
        return None
    span = (ed - sd).days
    xa = (_qend(fqF[k_anchor]) - sd).days / span
    xt = (_qend(fqF[k_target]) - sd).days / span
    key = site.get("reg") if site.get("reg") in ("국내", "해외") else "전체"
    pa = site["s"]["pr"][k_anchor]
    if pa is None:
        return None
    delta = pa - _p50(key, xa)
    return max(0.0, min(100.0, _p50(key, xt) + delta))


# ── II-4 갱신 ────────────────────────────────────────────────

def _site_index(D):
    """정규화 공사명(현재 nm + names 이력) → site 목록."""
    idx = {}
    for s in D["sites"]:
        keys = {_norm_nm(s["nm"])}
        for pair in s.get("names") or []:
            keys.add(_norm_nm(pair[1]))
        pf = s.get("p8Full") or {}
        for v in pf.get("품목") or []:
            keys.add(_norm_nm(v))
        if s.get("xip") and s["xip"].get("nm"):
            keys.add(_norm_nm(s["xip"]["nm"]))
        for key in keys:
            if key:
                idx.setdefault(key, []).append(s)
    return idx


# 법인명 대조용 정규화 — III-8 표는 `지에스건설㈜`, 집계 라벨은 `GS건설`처럼
# 법인격 표기와 한글 음차가 갈린다.
_ENT_DROP = re.compile(
    r"(㈜|\(주\)|주식회사|유한회사|Co\.?,?\s*Ltd\.?|Pty\.?|Ltd\.?|Inc\.?"
    r"|SoleProprietorship|Corporation|Corp\.?)", re.I)
_ENT_KO2EN = (("지에스", "GS"), ("디엘", "DL"), ("에이치디씨", "HDC"),
              ("에스케이", "SK"), ("엘지", "LG"), ("현대이엔지", "현대엔지니어링"))


def _ent_key(s):
    """법인명 비교 키. `지에스건설㈜` → `GS건설`."""
    x = _norm_nm(s)
    x = _ENT_DROP.sub("", x)
    for ko, en in _ENT_KO2EN:
        x = x.replace(ko, en)
    return x.upper()


def _tag_ent(lead, ents):
    """표 앞 문맥에서 법인을 판정한다. 현대건설의 '1) 현대건설', GS의 '2) 자이에스앤디'처럼
    lead에 법인명이 박혀 있으면 그 법인, 없으면 None(대표 법인으로 귀속)."""
    tail = (lead or "")[-300:]
    hit = [e for e in ents if e and e in tail]
    return max(hit, key=len) if hit else None


def _src_at(D, ent, k):
    """법인의 그 분기 summary.src. **새 분기 칸은 None이므로 직전 분기 값을 승계한다.**

    `_extend_axes`가 새 칸을 None으로 채우는데, None은 '공시총계'에도 ''에도 걸리지 않아
    가드가 통째로 무력화된다 — 현대건설 수주잔고가 사이트 합(공시총계보다 훨씬 작다)으로
    덮여 헤드라인이 −58% 나는 경로다. 동일분기 재적재에서는 값이 남아 있어 드러나지 않는다.
    """
    arr = D["summary"]["src"].get(ent) or []
    for i in range(min(k, len(arr) - 1), -1, -1):
        if arr[i] is not None:
            return arr[i]
    return None


def _agg_ents(D, k):
    """그 분기 실제 집계 대상 법인(summary.src가 빈 문자열이 아닌 법인)."""
    return [e for e in D["summary"]["ents"] if _src_at(D, e, k) != ""]


def _apply_ii4(D, parsed, k, q, rep):
    idx = _site_index(D)
    n = len(D["fqF"])
    ents = D["summary"]["ents"]
    live = _agg_ents(D, k)          # 집계 대상 법인(비집계 법인 사업장은 여기로 넘긴다)
    matched, created = set(), []
    for t in parsed["tables"]:
        tag_ent = _tag_ent(t.get("lead"), ents)
        for rec in t["rows"]:
            if _is_agg(rec):
                rep["agg_rows"].append(rec)
                continue
            amt, bal = rec.get("amt"), rec.get("bal")
            cmp_ = rec.get("cmp")
            if cmp_ is None and amt is not None and bal is not None:
                cmp_ = 0                       # 미착공('-') 관행 → 0 (dwe 검증)
            if amt is None and bal is None:
                continue
            key = _norm_nm(rec.get("nm"))
            cands = [s for s in idx.get(key, []) if id(s) not in matched]
            if len(cands) > 1:
                # 동명 다건 — 1순위 직전 실측 도급액 연속성, 2순위 발주처 일치
                cl = _norm_nm(rec.get("cl"))

                def rank(s):
                    p = _last_meas(s, k)
                    prev = s["s"]["amt"][p] if p is not None else None
                    cont = (abs(prev - amt)
                            if prev is not None and amt is not None else float("inf"))
                    return (cont, 0 if cl and _norm_nm(s.get("cl")) == cl else 1)
                cands = sorted(cands, key=rank)[:1]
            if cands:
                s = cands[0]
                matched.add(id(s))
                prev = _last_meas(s, k)
                _detect_ev(s, rec, prev, q, rep,
                           stale=_has_later_obs(s, k, len(D["fq"])))
            else:
                s = _new_site(D, rec, n, q)
                created.append(s["id"])
                idx.setdefault(key, []).append(s)
                matched.add(id(s))
            s["s"]["amt"][k] = amt
            s["s"]["cmp"][k] = cmp_
            s["s"]["bal"][k] = bal
            s["s"]["pr"][k] = (round(cmp_ / amt * 100, 2)
                               if amt and cmp_ is not None else None)
            sf = s.setdefault("sFilled", [None] * n)
            sf[k] = None                       # 실측
            # 집계 귀속은 정규화 라벨(ent)이 아니라 **이번 분기 원문 표의 법인**이다.
            # 표에서 법인을 못 읽으면 원래 라벨을 쓰되, 그 법인이 이번 분기 비집계
            # (src='')면 집계 대상 대표 법인으로 넘긴다 — GS이니마 사업장이 2025Q1
            # 표 개편 후 GS건설 표에 실려 GS건설로 집계되는 케이스.
            entq = tag_ent or s["ent"]
            if live and entq not in live:
                entq = live[0]
            # 직전 분기의 표시법인은 **_entq를 세우기 전에** 읽어야 한다 —
            # _disp_ent가 _entq를 최우선으로 보므로, 먼저 세우면 항상 "변경 없음"이 된다.
            prev_disp = _disp_ent(D, s, k - 1) if k else s["ent"]
            s["_entq"] = entq
            # 지역도 그 분기 원문이 명시하면 그것을 쓴다. 사이트의 reg는 공사명 기준으로
            # 굳은 표시용 값이라, 시공지는 해외지만 발주처가 한국 법인인 원전 수출 같은
            # 건에서 원본 집계와 갈린다(삼성물산 3건 148,706).
            rq = region_of(t.get("lead"), rec.get("cl"))
            if rq:
                s["_regq"] = rq
            # 표시법인이 바뀌면 이력으로 남긴다 — 다음 분기에 이 사업장이 표에서 빠져도
            # _disp_ent가 승계할 근거가 된다(승계 이력이 없으면 원래 라벨로 되돌아간다).
            if entq != prev_disp and not any(
                    e.get("fq") == q and e.get("f") == "표시법인"
                    for e in s.setdefault("ev", [])):
                s["ev"].append({"fq": q, "f": "표시법인",
                                "o": prev_disp, "n": entq, "d": ""})
                rep["events"] += 1
            nm_raw = (rec.get("nm") or "").strip()
            names = s.setdefault("names", [])
            if (nm_raw and not _has_later_obs(s, k, len(D["fq"]))
                    and (not names or names[-1][1] != nm_raw)):
                names.append([q, nm_raw])
    rep["created"] = created
    rep["_matched"] = matched          # 백필 대상 판정에 쓴다(_backfill_p8)
    # 직전 분기 실측인데 이번 분기 미등장 → 공백(보고 누락) 경고
    for s in D["sites"]:
        if id(s) in matched or k == 0:
            continue
        sf = s.get("sFilled") or [None] * n
        if s["s"]["bal"][k - 1] is not None and sf[k - 1] is None:
            rep["disappeared"].append(s["id"])


def _backfill_p8(D, k, rep):
    """II-4 표에 없는 사업장의 II-4 값을 III-8에서 역채움한다(`sFilled='p8'`).

    회사는 매출 5% 미만 현장을 II-4 상세표에서 빼면서도 III-8에는 계속 싣는다.
    원 빌더는 그 구간을 III-8 수주총액·진행률로 채운다 — 임베드 데이터에서 규칙을 역산했다:
        amt = p8[basis].tot,  pr = p8[basis].pr,  cmp = round(tot × pr / 100),  bal = tot − cmp
    (별도 우선, 없으면 연결). 이 패스가 없으면 새 분기에 그 사업장들이 통째로 비고,
    "이번 분기 활성" 신호가 사라져 III-8 동명 매칭까지 흔들린다.
    """
    matched = rep.get("_matched") or set()
    n = len(D["fqF"])
    done = []
    for s in D["sites"]:
        if id(s) in matched or s["s"]["amt"][k] is not None:
            continue
        # II-4 이력이 있는 사업장만 채운다. III-8 전용 레코드(`-3-`, has[0]=0)는
        # 애초에 II-4 계열이 없으므로 원 빌더도 채우지 않는다(7사 전수 확인).
        if not (s.get("has") or [0])[0]:
            continue
        p8 = s.get("p8") or {}
        b = None
        for basis in ("별도", "연결"):
            cand = p8.get(basis)
            if cand and cand["tot"][k] is not None and cand["pr"][k] is not None:
                b = cand
                break
        if b is None:
            continue
        tot, pr = b["tot"][k], b["pr"][k]
        cmp_ = round(tot * pr / 100)
        s["s"]["amt"][k] = tot
        s["s"]["cmp"][k] = cmp_
        s["s"]["bal"][k] = tot - cmp_
        s["s"]["pr"][k] = pr
        s.setdefault("sFilled", [None] * n)[k] = "p8"
        done.append(s["id"])
    rep["backfilled"] = done
    # 백필된 사업장은 '사라짐'이 아니다
    rep["disappeared"] = [x for x in rep["disappeared"] if x not in set(done)]

    # II-4 표에 없어 `_entq`가 없는 사업장(이번에 백필했든, 이미 p8로 차 있든)은
    # **III-8 표의 '회사명' 열**이 유일한 귀속 근거다 — GS건설 싱가포르 지하철
    # (GSE-2-0027)처럼 라벨이 `GS이니마`로 굳었지만 실제로는 지에스건설㈜인 건이 바로잡힌다.
    sf_key = "sFilled"
    for s in D["sites"]:
        p8ent = _ent_key(s.pop("_p8ent", "") or "")
        if not p8ent or s.get("_entq"):
            continue
        if (s.get(sf_key) or [None] * n)[k] != "p8":
            continue
        for e in D["summary"]["ents"]:
            ek = _ent_key(e)
            if ek and (ek == p8ent or ek in p8ent):
                s["_entq"] = e
                break


def _has_later_obs(s, k, n_meas):
    """k 이후 **실측 분기**에 관측이 있는가(미래 예측 칸은 관측이 아니다).

    `nm`·`cl`·`sd`·`ed`는 시계열이 아니라 **최신 관측값**을 담는 스칼라다. 과거 분기를
    재적재할 때 이 필드를 그 분기 원문으로 덮으면 최신 값이 과거로 되돌아가고,
    최신값과 과거 원문을 비교하느라 허위 변경 이벤트까지 쌓인다.

    n_meas는 `len(fq)`(실측 축)여야 한다 — `len(fqF)`를 넘기면 미래 4분기의 `fcst`가
    '이후 관측'으로 잡혀 **최신 분기 재적재에서도 스칼라가 갱신되지 않는다.**
    """
    sf = s.get("sFilled") or [None] * len(s["s"]["amt"])
    for i in range(k + 1, min(n_meas, len(s["s"]["amt"]))):
        if s["s"]["amt"][i] is not None and sf[i] != "fcst":
            return True
    return False


def _last_meas(s, k):
    sf = s.get("sFilled") or [None] * len(s["s"]["amt"])
    for i in range(k - 1, -1, -1):
        if s["s"]["amt"][i] is not None and sf[i] is None:
            return i
    return None


def _detect_ev(s, rec, prev_k, q, rep, stale=False):
    ev = s.setdefault("ev", [])
    new_sd = norm_date(rec.get("sd"))
    new_ed = norm_date(rec.get("ed"), end=True)
    # 원문 오기 방어: 착공일이 완공예정일보다 뒤면 그 행의 날짜는 믿지 않는다.
    # DART 원문에 계약일·완공예정일을 같은 값으로 적어 둔 행이 실재하고
    # (삼성물산 튀르키예 Nakkas 도로: 둘 다 2027-02-28), 가드가 없으면 저장된
    # 정상 착공일을 미래 날짜로 덮어쓰고 허위 이벤트를 남긴다.
    d_sd, d_ed = _date(new_sd), _date(new_ed)
    if d_sd and d_ed and d_sd >= d_ed:      # 같은 날짜도 오기다(공기 0일인 공사는 없다)
        rep.setdefault("bad_dates", []).append(
            {"id": s["id"], "sd": new_sd, "ed": new_ed})
        new_sd = new_ed = None
    checks = [("기본도급액", s["s"]["amt"][prev_k] if prev_k is not None else None,
               rec.get("amt"))] if prev_k is not None else []
    checks += [("공사착공일", s.get("sd"), new_sd),
               ("완공예정일", s.get("ed"), new_ed),
               ("발주처", s.get("cl"), rec.get("cl"))]
    for f, old, new in checks:
        if new in (None, "") or old in (None, ""):
            continue
        if f in ("공사착공일", "완공예정일") and not _date(new):
            continue                       # '미정' 등 비날짜 표기는 기존값 유지
        if f == "발주처" and str(new) != str(old) and str(old).startswith(str(new)):
            continue                       # 원문이 법인격을 줄여 적은 것(…유한회사 → …) — 상세한 기존값 유지
        if str(old) != str(new):
            d = (new - old) if isinstance(old, (int, float)) and isinstance(new, (int, float)) else ""
            if not stale and not any(e["fq"] == q and e["f"] == f for e in ev):
                ev.append({"fq": q, "f": f, "o": str(old) if f != "기본도급액" else old,
                           "n": str(new) if f != "기본도급액" else new, "d": d})
                rep["events"] += 1
            if stale:
                continue          # 과거 분기 재적재 — 최신 스칼라를 덮지 않는다
            if f == "공사착공일":
                s["sd"] = new
            elif f == "완공예정일":
                s["ed"] = new
            elif f == "발주처":
                s["cl"] = new


def _new_site(D, rec, n, q):
    pref = D["sites"][0]["id"].split("-")[0] if D["sites"] else "NEW"
    mx = 0
    for s in D["sites"]:
        m = re.match(r"^%s-2-(\d+)$" % pref, s["id"])
        if m:
            mx = max(mx, int(m.group(1)))
    ent = D["summary"]["ents"][0] if D["summary"]["ents"] else ""
    site = {
        "id": "%s-2-%04d" % (pref, mx + 1), "ent": ent,
        "nm": (rec.get("nm") or "").strip(), "reg": "미표기",
        "cl": (rec.get("cl") or "").strip(), "sd": norm_date(rec.get("sd")),
        "ed": norm_date(rec.get("ed"), end=True), "seg2": None, "rp": None,
        "has": [1, 0, 0], "gap": "N", "note": None,
        "s": {"amt": [None] * n, "cmp": [None] * n, "bal": [None] * n,
              "pr": [None] * n, "prC": [None] * n, "prCv": []},
        "sFilled": [None] * n, "mfq": [False] * n, "mfqE": [False] * n,
        "p8": {}, "p8Full": None, "xip": None, "xipFull": None, "xifill": None,
        "ev": [], "evFull": None, "names": [[q, (rec.get("nm") or "").strip()]],
        "rev": {"diff": [None] * n, "src": [None] * n, "filled": [False] * n,
                "manual": [False] * n, "manualE": [False] * n},
    }
    D["sites"].append(site)
    return site


# ── III-8 갱신 ───────────────────────────────────────────────

def _apply_p8(D, parsed, k, rep):
    tabs = [t for t in parsed["tables"] if t["rows"]]
    if not tabs:
        return
    idx = _site_index(D)
    n = len(D["fqF"])

    def score(tab, basis):
        """직전 실측 분기 p8[basis]와의 (tot 존재·근사) 연속성 점수."""
        pts = 0
        for rec in tab["rows"]:
            for s in idx.get(_norm_nm(rec.get("nm")), []):
                b = (s.get("p8") or {}).get(basis)
                if b and any(v is not None for v in b["tot"][:k]):
                    pts += 1
                    break
        return pts

    if len(tabs) >= 2:
        a, b = tabs[0], tabs[1]
        # 배정 조합 중 연속성 점수 합이 큰 쪽 채택 (lead 앵커는 parse_p8이 이미 반영)
        s1 = score(a, a["basis"] or "연결") + score(b, b["basis"] or "별도")
        s2 = score(a, b["basis"] or "별도") + score(b, a["basis"] or "연결")
        if s2 > s1:
            a["basis"], b["basis"] = (b["basis"] or "별도"), (a["basis"] or "연결")
    elif len(tabs) == 1 and tabs[0]["basis"] is None:
        # 표가 하나뿐이고 lead로 판정이 안 되면 직전 분기에 어느 기준이 있었는지로 정한다
        # (HDC현산은 2023Q4부터 연결 표만 낸다 — '별도'로 단정하면 전량 오배정된다)
        tabs[0]["basis"] = ("연결" if score(tabs[0], "연결") >= score(tabs[0], "별도")
                            else "별도")
    sep_vals = {}
    used = set()                                # (site, basis) 중복 배정 방지
    for tab in sorted(tabs, key=lambda t: t["basis"] != "별도"):   # 별도 먼저
        basis = tab["basis"] or "별도"
        for rec in tab["rows"]:
            if rec.get("amt") is None or _is_agg(rec):
                continue
            # 후보 수집: 정확 키 + 공종 접미를 뗀 키.
            # III-8 표는 공사명에 공종을 덧붙이는 회사가 있다(`GTPP (화공플랜트)`).
            # 그 이름으로 만들어진 III-8 전용 레코드(-3-)와 II-4 실사업장(-2-)이 공존하는데,
            # 정확 키만 보면 전용 레코드로 고정돼 실사업장의 계열에 구멍이 난다.
            key = _norm_nm(rec.get("nm"))
            keys = [key, strip_seg_suffix(key)]
            cands, seen_ids = [], set()
            for kk in keys:
                for s in idx.get(kk, []):
                    if (id(s), basis) in used or id(s) in seen_ids:
                        continue
                    seen_ids.add(id(s))
                    cands.append(s)
            if not cands:
                rep["p8_unmatched"].append(rec.get("nm"))
                continue

            def cont(s):
                # 직전 분기까지의 p8[basis].tot(없으면 II-4 amt)와의 수주총액 연속성
                b = (s.get("p8") or {}).get(basis)
                prev = None
                if b:
                    prev = next((v for v in reversed(b["tot"][:k]) if v is not None), None)
                if prev is None:
                    p = _last_meas(s, k)
                    prev = s["s"]["amt"][p] if p is not None else None
                return abs(prev - rec["amt"]) if prev is not None else float("inf")

            # 랭킹: ① III-8 표의 '회사명' 열과 법인 일치 ② 이번 분기 II-4 실측 보유
            #       ③ 과거 수주총액 연속성
            # ①은 같은 공사가 법인별로 갈릴 때의 정확한 판별자다 — 현대건설 우즈베키스탄
            # 현장은 별도 표가 '현대건설', 연결 표가 '현대엔지니어링'으로 서로 다른 사업장에
            # 붙는다. ②는 III-8 전용 레코드보다 살아 있는 실사업장을 우선한다(DL이앤씨).
            p8ent = _norm_nm(rec.get("p8_ent"))

            def rank_p8(s):
                ent_hit = 0 if (p8ent and _norm_nm(s.get("ent")) == p8ent) else 1
                # II-4 이력이 있는 실사업장을 III-8 전용 레코드보다 우선한다.
                # '이번 분기 실측'이 아니라 '이력 보유'로 보는 이유: III-8에서 역채움된
                # 사업장은 sFilled='p8'이라 실측 판정에서 빠진다(DL이앤씨 Maaden 사례).
                has_ii4 = 0 if (s.get("has") or [0])[0] else 1
                return (ent_hit, has_ii4, cont(s))
            if len(cands) > 1:
                cands = sorted(cands, key=rank_p8)
            s = cands[0]
            used.add((id(s), basis))
            if rec.get("p8_ent"):
                s["_p8ent"] = rec["p8_ent"]     # 백필 귀속 판정용(임시)
            tup = (rec.get("amt"), rec.get("pr"), rec.get("ub"),
                   rec.get("ubimp"), rec.get("rc"), rec.get("allw"))
            if basis == "연결" and sep_vals.get(id(s)) == tup:
                continue                        # 별도=연결 동일 → 연결 생략(원 빌더 규칙)
            if basis == "별도":
                sep_vals[id(s)] = tup
            p8 = s.setdefault("p8", {})
            b = p8.get(basis)
            if not b:
                b = p8[basis] = {f: [None] * n for f in
                                 ("tot", "pr", "ub", "ubimp", "rc", "allw", "dl")}
            pr = rec.get("pr")
            b["tot"][k] = rec.get("amt")
            b["pr"][k] = float(pr) if pr is not None else None   # 원본은 항상 float

            # 손상차손누계·대손충당금은 **양수로 정규화**해 저장한다. 원문 표기가 회사·분기별로
            # `(528)` 괄호음수와 `528` 양수를 오가는데, 임베드 DATA는 7사 전체에서 음수가
            # 한 건도 없다(차트가 |ubimp|+|allw|로 그리는 것과 별개로 저장 규약이 양수다).
            b["ub"][k] = rec.get("ub")
            b["rc"][k] = rec.get("rc")
            b["ubimp"][k] = abs(rec["ubimp"]) if rec.get("ubimp") is not None else None
            b["allw"][k] = abs(rec["allw"]) if rec.get("allw") is not None else None
            b["dl"][k] = norm_date(rec.get("p8_dl"), end=True) or None
            s["has"][1] = 1
            rep["p8_cells"] += 1


# ── 재집계·예측·검증 ─────────────────────────────────────────

# rev.diff[k]는 cmp[k−1]과 cmp[k] 두 칸에서 나오므로, 그 출처는 **둘 중 더 추정적인 쪽**을 쓴다.
# 앞이 강함(더 추정적). 7사 임베드 데이터 전수 대조로 역산한 순서.
_SRC_PRI = ["fcst", "bcst", "interp", "p8", "xi1"]


def _worse_src(a, b):
    ia = _SRC_PRI.index(a) if a in _SRC_PRI else len(_SRC_PRI)
    ib = _SRC_PRI.index(b) if b in _SRC_PRI else len(_SRC_PRI)
    return a if ia <= ib else b


def _disp_ent(D, s, k):
    """그 분기의 '표시법인'(원문 표 법인).

    이번 분기 표에 있으면 `_entq`, 없으면 `ev`의 표시법인 이력에서 직전 값을 승계하고,
    그것도 없으면 정규화 라벨을 쓴다. **승계가 핵심이다** — GS건설은 2025Q1 표 개편으로
    법인 헤더가 사라져 II-4에 실린 사업장이 전부 GS건설로 귀속되는데, 그때 옮겨졌지만
    이번 분기 표에서 빠진 사업장을 원래 라벨로 되돌리면 매출이 엉뚱한 법인으로 간다.
    """
    if s.get("_entq"):
        return s["_entq"]
    pos = {q: i for i, q in enumerate(D["fqF"])}
    cur = None
    evs = sorted((e for e in (s.get("ev") or []) if e.get("f") == "표시법인"),
                 key=lambda e: pos.get(e["fq"], 0))
    for e in evs:
        if pos.get(e["fq"], 10 ** 9) > k:
            if cur is None:
                cur = e.get("o")          # 첫 이벤트 이전 구간
            break
        cur = e.get("n")
    return cur or s["ent"]


def _ovs_never_split(D, ent, k):
    """그 법인이 다른 전 분기에서 ovs=0이면 회사가 해외를 분리 공시하지 않는 것이다.
    원문에 해외 표지가 아예 없는 HDC현산이 이 경우 — 새 분기도 전액 국내로 둔다."""
    SUM = D["summary"]
    if ent not in SUM.get("ovs", {}):
        return False
    ks = [i for i in range(len(D["fqF"]))
          if i != k and SUM["rows"][ent][i] is not None]
    return bool(ks) and all((SUM["ovs"][ent][i] or 0) == 0 for i in ks)


def _recompute(D, k):
    n = len(D["fqF"])
    for s in D["sites"]:
        rev = s.get("rev")
        if rev is None:
            continue
        sf = s.get("sFilled") or [None] * n
        for i in (k, k + 1):
            if i < 1 or i >= n:
                continue
            a, b = s["s"]["cmp"][i - 1], s["s"]["cmp"][i]
            if a is None or b is None:
                rev["diff"][i] = None
                rev["src"][i] = None
                rev["filled"][i] = False
                continue
            d = b - a
            rev["diff"][i] = int(d) if float(d).is_integer() else d
            rev["src"][i] = _worse_src(sf[i - 1], sf[i])
            rev["filled"][i] = bool(rev["src"][i])
    SUM, REV = D["summary"], D["revSummary"]

    def _belongs(s, ent):
        """이번 분기 원문 표 법인(_entq)이 있으면 그것으로, 없으면 정규화 라벨로 귀속."""
        return (s.get("_entq") or s["ent"]) == ent

    for ent in SUM["ents"]:
        mine = [s for s in D["sites"] if _belongs(s, ent) and not s.get("agg")]
        meas = [s for s in mine
                if (s.get("sFilled") or [None] * n)[k] is None
                and s["s"]["bal"][k] is not None]
        src = _src_at(D, ent, k)          # 새 분기 칸은 None이므로 직전 값을 승계한다
        # src가 산출 방식을 정한다(LOGIC.md §2.3):
        #   '명시+기타(계산)' → 개별 명시 사업장 합 (+ 원문 '기타' 행 — v1 미반영, 리포트로)
        #   '공시총계'/'공시총계(단일)' → 회사가 공시한 총계. 사이트 합이 아니므로 손대지 않는다
        #   ''(빈 문자열) → 그 분기 집계 대상 아님. rows는 None으로 남아야 한다
        if src == "":
            continue
        if src in ("공시총계", "공시총계(단일)"):
            # 이 법인은 원문 합계행에서 읽어야 한다(v1 미구현). 새 분기라면 값이 비어
            # 있으므로, 조용히 사이트 합으로 채우는 대신 리포트에 남긴다.
            if SUM["rows"][ent][k] is None:
                D.setdefault("_missing_total", []).append(ent)
            continue
        SUM["rows"][ent][k] = sum(s["s"]["bal"][k] for s in meas) if meas else None
        never = _ovs_never_split(D, ent, k)
        for key, reg in (("dom", "국내"), ("ovs", "해외")):
            sub = [s for s in meas
                   if ("국내" if never else (s.get("_regq") or s.get("reg"))) == reg]
            if ent in SUM.get(key, {}):
                # 그 법인에 실측이 있으면 한쪽 지역이 비어도 0으로 채운다(원본 규약).
                SUM[key][ent][k] = (sum(s["s"]["bal"][k] for s in sub) if sub
                                    else (0 if meas else None))
    # revSummary도 계약잔액 summary와 같이 **원문 표 법인**으로 귀속하되, 이번 분기
    # 표에 없는 사업장은 직전 표시법인을 승계한다(_disp_ent). 7사 전 분기 대조로 확인.
    for ent in REV["ents"]:
        mine = [s for s in D["sites"]
                if _disp_ent(D, s, k) == ent and not s.get("agg")]
        vals = [s["rev"]["diff"][k] for s in mine
                if s.get("rev") and s["rev"]["diff"][k] is not None]
        REV["rows"][ent][k] = sum(vals) if vals else None
        REV["filled"][ent][k] = any(
            s.get("rev") and s["rev"]["diff"][k] is not None and s["rev"]["filled"][k]
            for s in mine)
        for key, reg in (("dom", "국내"), ("ovs", "해외")):
            if ent in REV.get(key, {}):
                sub = [s["rev"]["diff"][k] for s in mine
                       if s.get("reg") == reg and s.get("rev")
                       and s["rev"]["diff"][k] is not None]
                REV[key][ent][k] = sum(sub) if sub else None
        for seg in (REV.get("segList") or {}).get(ent, []):
            sub = [s["rev"]["diff"][k] for s in mine
                   if s.get("seg2") == seg and s.get("rev")
                   and s["rev"]["diff"][k] is not None]
            REV["seg"][ent][seg][k] = sum(sub) if sub else None
    def _num(v):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v
    for agg in (SUM, REV):
        for e in agg["ents"]:
            agg["rows"][e][k] = _num(agg["rows"][e][k])
            for key in ("dom", "ovs"):
                if e in agg.get(key, {}):
                    agg[key][e][k] = _num(agg[key][e][k])
        if agg is REV:
            for e in (agg.get("seg") or {}):
                for sg in agg["seg"][e]:
                    agg["seg"][e][sg][k] = _num(agg["seg"][e][sg][k])
        vals = [agg["rows"][e][k] for e in agg["ents"]]
        agg["total"][k] = (_num(sum(v or 0 for v in vals))
                           if any(v is not None for v in vals) else None)


def _extend_axes(D, q):
    """fq에 q 추가, fqF = fq + 4 미래분기. 전 시계열 배열을 새 축으로 재배열."""
    old_fqF = D["fqF"]
    nfq = D["fq"] + [q]
    nfqF = list(nfq)
    while len(nfqF) < len(nfq) + 4:
        nfqF.append(q_next(nfqF[-1]))
    pos = {fq: i for i, fq in enumerate(old_fqF)}

    def remap(arr, fill=None):
        return [arr[pos[fq]] if fq in pos else fill for fq in nfqF]

    def walk(obj, key=None):
        # `_`로 시작하는 키는 시계열이 아니다 — p8Full의 `_dropQ`·`_onlyCon`은
        # **분기 인덱스 목록**이라, 길이가 우연히 len(fqF)와 같아지는 순간
        # 축으로 오인돼 remap된다(값이 하나씩 밀리고 None이 붙는다).
        if isinstance(key, str) and key.startswith("_"):
            return obj
        if isinstance(obj, dict):
            return {k: walk(v, k) for k, v in obj.items()}
        if isinstance(obj, list) and len(obj) == len(old_fqF):
            return remap(obj)
        if isinstance(obj, list):
            return [walk(v) for v in obj]
        return obj

    for s in D["sites"]:
        for key in ("s", "sFilled", "mfq", "mfqE", "p8", "p8Full",
                    "xip", "xipFull", "rev", "evFull"):
            if s.get(key) is not None:
                s[key] = walk(s[key], key)
        for c in s["s"].get("prCv") or []:
            if isinstance(c.get("v"), list) and len(c["v"]) == len(old_fqF):
                c["v"] = remap(c["v"])
    for key in ("summary", "revSummary", "coRev"):
        D[key] = walk(D[key])
    D["fq"], D["fqF"] = nfq, nfqF


def _forecast(D, rep):
    n = len(D["fqF"])
    n_meas = len(D["fq"])
    for s in D["sites"]:
        sf = s.setdefault("sFilled", [None] * n)
        anchor = _last_meas(s, n_meas)
        if anchor is None or not s["s"]["amt"][anchor]:
            continue
        amt = s["s"]["amt"][anchor]
        for k in range(n_meas, n):
            if s["s"]["pr"][anchor] is not None and s["s"]["pr"][anchor] >= 100:
                break
            pr = _fcst_pr(s, anchor, k, D["fqF"])
            if pr is None:
                break
            pr = max(pr, s["s"]["pr"][anchor])
            s["s"]["pr"][k] = round(pr, 2)
            s["s"]["cmp"][k] = round(amt * pr / 100)
            s["s"]["bal"][k] = amt - s["s"]["cmp"][k]
            s["s"]["amt"][k] = amt
            sf[k] = "fcst"
            rep["fcst_cells"] += 1


def _validate(D):
    n = len(D["fqF"])
    assert D["fqF"][:len(D["fq"])] == D["fq"], "fqF 접두 불일치"
    assert len(D["fqF"]) == len(D["fq"]) + 4, "fqF 길이 규칙 위반"
    for s in D["sites"]:
        for key in ("amt", "cmp", "bal", "pr", "prC"):
            assert len(s["s"][key]) == n, ("배열 길이", s["id"], key)
    for k in range(n):
        vals = [D["summary"]["rows"][e][k] for e in D["summary"]["ents"]]
        if any(v is not None for v in vals):
            assert D["summary"]["total"][k] == sum(v or 0 for v in vals), ("total", k)
    json.dumps(D)


def update_quarter(co, q, raw_dir, apply=False, forecast=False):
    path = os.path.join(KCE, co, "index.html")
    D = extract_data(path)
    rep = {"co": co, "quarter": q, "events": 0, "p8_cells": 0, "fcst_cells": 0,
           "agg_rows": [], "created": [], "disappeared": [], "p8_unmatched": [],
           # 이번 분기 파서가 실제로 채택한 표의 머리행 — headers.html('파서 머리행 지도')의
           # 입력이자, 회사가 열 이름을 바꿨을 때의 감시 로그다(UPDATE.md §7).
           "headers": {"ii4": [], "p8": []}}
    if q in D["fq"]:
        k = D["fq"].index(q)                      # 재적재(정정 반영)
    elif q == q_next(D["fq"][-1]):
        _extend_axes(D, q)
        k = D["fq"].index(q)
    else:
        raise RuntimeError("갱신 가능한 분기가 아님: %s (마지막 %s)" % (q, D["fq"][-1]))

    # 본문(ii4)과 상세표(ii4x) 후보를 **둘 다 파싱해** 행수가 큰 쪽을 채택한다.
    # 한쪽만 보고 판단하면 안 된다 — GS건설의 XII 상세표에는 수주 표가 아예 없어서
    # 표 0개·미지헤더 0개로 '조용히' 통과하고, 실측 90건이 통째로 사라진다.
    cands = []
    for suf in ("ii4x", "ii4"):
        p = os.path.join(raw_dir, "%s_%s.html" % (co, suf))
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            pr = parse_ii4(f.read())
        cands.append((sum(t["n"] for t in pr["tables"]), suf, pr))
    if not cands:
        raise RuntimeError("II-4 원문 파일이 없다: %s_{ii4x,ii4}.html" % co)
    cands.sort(key=lambda x: -x[0])
    nrows, used, parsed = cands[0]
    # 채택된 쪽의 미지 헤더만 fail-closed 대상이다(다른 절의 무관한 표는 제외)
    if parsed["unknown_headers"]:
        raise RuntimeError("미지 헤더 — 파서 사전 갱신 필요(%s): %s"
                           % (used, parsed["unknown_headers"][:2]))
    if nrows == 0:
        raise RuntimeError(
            "II-4 표를 한 건도 파싱하지 못했다(%s). 절 선택 또는 열 별칭을 확인하라." % co)
    rep["ii4_source"] = used
    rep["headers"]["ii4"] = [{"cols": t["cols"], "n": t["n"],
                              "lead": (t["lead"] or "")[-120:]}
                             for t in parsed["tables"]]
    _apply_ii4(D, parsed, k, q, rep)

    p8_path = os.path.join(raw_dir, "%s_p8.html" % co)
    if os.path.exists(p8_path):
        with open(p8_path, encoding="utf-8") as f:
            pp = parse_p8(f.read())
        if pp["unknown_headers"]:
            raise RuntimeError("III-8 미지 헤더: %s" % pp["unknown_headers"][:2])
        rep["headers"]["p8"] = [{"cols": t["cols"], "n": t["n"],
                                 "basis": t["basis"]} for t in pp["tables"]]
        _apply_p8(D, pp, k, rep)
        _backfill_p8(D, k, rep)

    # 붕괴 감시: 직전 분기 실측 사업장 중 이번에 사라진 비율이 임계치를 넘으면 중단한다.
    # 준공으로 빠지는 건 소수이고, 대량 소실은 표를 놓쳤다는 신호다(GS건설 99/90 사례).
    prev_meas = sum(1 for s in D["sites"]
                    if k > 0 and s["s"]["bal"][k - 1] is not None
                    and (s.get("sFilled") or [None] * len(D["fqF"]))[k - 1] is None)
    if prev_meas and len(rep["disappeared"]) / prev_meas > 0.30:
        raise RuntimeError(
            "직전 분기 실측 %d건 중 %d건이 이번 분기에 사라졌다(%.0f%%) — "
            "표 누락이 의심된다. dry-run 리포트의 disappeared를 확인하라."
            % (prev_meas, len(rep["disappeared"]),
               100.0 * len(rep["disappeared"]) / prev_meas))

    _recompute(D, k)
    # 예측(fcst)은 기본 비활성. 원 빌더의 '어느 사업장을 어디까지 예측하는가' 중단 조건이
    # 완전히 역산되지 않았고(장기 미보고·완공 임박 사업장에서 우리 쪽이 과잉 생성),
    # 잘못된 미래 수치를 새로 만드는 것보다 기존 예측을 보존하는 편이 안전하다.
    # 축이 밀려도 예측 셀은 분기 라벨 기준으로 따라가고, 실측이 들어오면 그 칸만 덮인다.
    if forecast and q == D["fq"][-1]:
        _forecast(D, rep)
    for s in D["sites"]:
        s.pop("_entq", None)      # 임시 귀속 필드는 저장하지 않는다
        s.pop("_regq", None)
        s.pop("_p8ent", None)
    D.pop("_missing_total", None)
    _validate(D)
    D["codeGen"] = datetime.date.today().isoformat()
    if apply:
        # 네 파일을 **전부 메모리에서 만들고 검증한 뒤** 한꺼번에 쓴다.
        # 파일별 atomic_write는 파일 하나의 원자성만 보장한다 — 중간에 렌더가 실패하면
        # index.html만 갱신된 반쪽 상태로 끝나고, 리포트에는 성공 표시조차 남지 않는다.
        co_dir = os.path.join(KCE, co)
        pending = [(path, kce_render.replace_data(path, D)),
                   (os.path.join(co_dir, "matrix.html"),
                    kce_render.render_matrix_html(os.path.join(co_dir, "matrix.html"), D)),
                   (os.path.join(co_dir, "trace.html"),
                    kce_render.render_trace_html(os.path.join(co_dir, "trace.html"), D)),
                   (os.path.join(KCE, "headers.html"),
                    kce_render.render_headers_html(os.path.join(KCE, "headers.html"),
                                                   co, q, rep["headers"]))]
        for p, text in pending:
            atomic_write(p, text)
        rep["applied"] = True
        rep["rerendered"] = ["matrix.html", "trace.html", "../headers.html"]
        # 나머지는 재생성기 미구현 — 갱신 후 옛 데이터로 남는다(UPDATE.md §7)
        rep["stale_pages"] = ["backtest.html", "../curve.html"]
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--co", required=True, choices=sorted(CORP))
    ap.add_argument("--quarter", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--forecast", action="store_true",
                    help="미래 4분기 S-curve 예측 재생성(실험적 — 원 빌더보다 과잉 생성한다)")
    a = ap.parse_args()
    rep = update_quarter(a.co, a.quarter, a.raw, a.apply, a.forecast)
    rep.pop("_matched", None)
    rep["agg_rows"] = len(rep["agg_rows"])
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if rep.get("applied"):
        print("주의: 파생 페이지 스테일 —", " ".join(rep["stale_pages"]), file=sys.stderr)


if __name__ == "__main__":
    main()
