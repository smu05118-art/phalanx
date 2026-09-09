#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_render — DATA에서 파생 페이지를 재생성한다 (matrix.html · trace.html).

index.html의 `const DATA`만 갱신하면 matrix/trace는 옛 데이터로 남는다(UPDATE.md §7).
이 모듈이 그 둘을 DATA로부터 다시 만들어 스테일을 없앤다.

정합성 근거: 재생성 결과가 현재 저장된 원본과 **바이트 단위로 동일**함을 17사 전부에서 확인했다
(tools/tests/test_render.py). 즉 렌더 규칙이 원 빌더와 동치다.

상류(encprojects)가 7사 → 17사로 늘면서 페이지 스키마도 함께 바뀌었다. 저장된 페이지가 정본이고
이 모듈이 따라간다 — 반대가 아니다. 이번에 따라잡은 것:
  · matrix tbody 선두에 `<tr class="grp tot">` 총합계 행이 생겼고, 앞뒤 여백이 3줄로 늘었다
  · 라벨 셀에 플래그(⚑) 토글과 배지 3종(관계사·다수현장·해외법인)이 붙고,
    배지 개수가 `it b<N>` 클래스로, 묶음(list_pin)이 `pin/pt/pb`로 나온다.
    법인 접두(`<b>법인</b> · `)는 배지와 자리가 겹쳐 전 행에서 빠졌다(title에는 남는다)
  · xi1 셀이 실측과 구분되는 자기 표식(`flx`)을 얻었다 — UPDATE.md §8이 예고한 그 변경이다
  · trace SITES가 6칸 → 10칸. III-8이 별도/연결 두 벌로 갈라지고 pin·lump·eb가 붙었다

backtest.html(워크포워드 재실행 필요)·curve.html(곡선 재적합)은 미구현.
"""
import html as _html
import re

from kce_lib import atomic_write, extract_data

# ── 공통 ────────────────────────────────────────────────────

# 셀 표식은 클래스 6종(fl · flx · fli · ffc · fm · fe)이고, matrix 범례도 그 여섯을 싣는다.
# 아래 표는 그중 rev.src에서 오는 다섯이다(fcst·bcst는 문구만 다르고 같은 ffc를 쓴다).
# 'xi1'은 예전엔 테두리 없이 실측처럼 그렸지만, 상류가 matrix에도 민트 점선
# `.flx`를 들여오면서 자기 표식을 얻었다(UPDATE.md §8이 "재복제 시 함께 갱신"이라 예고한 건).
# 'bcst' 문구도 '착공일' → '시작일'로 바뀌었다 — XI-1발 사업장은 착공일이 아니라 계약시작일이
# 기준이라 한쪽 출처만 가리키는 말을 뺀 것이다.
FILL_CLS = {
    "p8":     ("fl",  "III-8 교차참조 추정값"),
    "interp": ("fli", "선형보간 추정값"),
    "fcst":   ("ffc", "S-curve 예측값(미래 또는 장기 미보고 구간)"),
    "bcst":   ("ffc", "시작일 기준 S-curve 역산 추정값(첫 공시 이전 구간)"),
    "xi1":    ("flx", "XI-1 교차참조 확정값(판매공급 누적 기반)"),
}
MANUAL_CLS = ("fm", "수동 정정값(원문 오류로 판단되어 사용자 확인 후 교정)")
MANUAL_E_CLS = ("fe", "추정 배분값(원문에 정답이 없어 인접 실측 보간으로 추정)")

# 배지 3종의 title. 같은 문구를 index·matrix·trace가 공유하므로 여기 한 곳에만 적는다
# (원본에서는 site_style.py가 세 페이지에 같은 것을 주입한다).
LUMP_TITLE = ("다수현장 — 여러 현장이 한 행으로 묶여 공시된 사업장입니다. 단일 현장이 아니라 "
              "계약이 드나들므로 보전·예측 등 어떤 추정도 하지 않고, 분기 매출인식액도 "
              "만들지 않습니다. 계약잔액은 공시값이라 그대로 합산됩니다.")
EB_TITLE = ("해외법인 — 원문이 이 사업장을 「%s」 표에 실었습니다. "
            "좌측 목록과 집계는 모회사 기준으로 묶습니다.")
RP_TITLE = "관계사 발주 — %s"


def esc(s):
    """원 빌더와 동일한 이스케이프.

    17사 산출물에 실제로 나타나는 엔티티는 &amp;·&#39;·&quot; 셋이다. 큰따옴표는
    자이에스앤디 XSD-11-0001(계약명이 따옴표로 시작한다)에서 나오는데, 이 값이
    title 속성 안에 들어가므로 &quot;를 빼면 속성이 그 자리에서 끊긴다."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def bn(v):
    """백만원 → 십억원 문자열(소수 1자리, 천단위 콤마). None이면 None."""
    if v is None:
        return None
    x = v / 1000.0
    return "{:,.1f}".format(x)


def year_break(fqF):
    """Q1 열 앞에 연도 경계선(yb) — 첫 열은 제외."""
    return [i > 0 and q.endswith("Q1") for i, q in enumerate(fqF)]


def flags_html(has):
    out = []
    for i, on in enumerate(has):
        out.append('<span class="f%d">O</span>' % (i + 1) if on
                   else '<span class="fx">X</span>')
    return '<span class="flags">%s</span>' % "".join(out)


def _badges(s):
    """배지 마크업 목록 — 순서는 관계사 · 다수현장 · 해외법인으로 고정(원본 라벨과 동일)."""
    out = []
    if s.get("rp"):
        out.append('<span class="rpb" title="%s">%s</span>'
                   % (esc(RP_TITLE % s["rp"]), esc(s["rp"])))
    if s.get("lump"):
        out.append('<span class="lmb" title="%s">다수현장</span>' % esc(LUMP_TITLE))
    if s.get("eb"):
        out.append('<span class="ebb" title="%s">%s</span>'
                   % (esc(EB_TITLE % s["eb"]), esc(s["eb"])))
    return out


def label_cell(s, pin_prev=None, pin_next=None):
    """사업장 라벨 셀.

    클래스는 `it [b<배지수>] [pin [pt] [pb]]`. `b<N>`은 CSS가 배지 개수만큼 이름 폭을
    줄이는 데 쓰고, `pin`은 묶음(list_pin) 구간을 한 덩어리로 칠하는 데 쓴다 —
    묶음의 위/아래 모서리(pt·pb)는 **화면에 그려지는 이웃 행**과 비교해 정한다.
    그래서 앞뒤 사업장의 pin 값을 인자로 받는다(그룹 머리행은 이웃으로 세지 않는다).
    """
    badges = _badges(s)
    cls = "it" + (" b%d" % len(badges) if badges else "")
    pin = s.get("pin") or None
    if pin:
        cls += " pin" + (" pt" if pin != pin_prev else "") \
                      + (" pb" if pin != pin_next else "")
    parts = ['<div class="%s">' % cls,
             '<span class="star" data-id="%s" title="즐겨찾기 (다시 확인할 프로젝트 표시)">☆</span>'
             % esc(s["id"]),
             '<span class="flag" data-id="%s" title="플래그 (별표와 별개로 표시)">⚐</span>'
             % esc(s["id"]),
             '<span class="cid" title="사업장 코드">%s</span>' % esc(s["id"])]
    parts += badges
    # 법인 접두(`<b>법인</b> · `)는 이제 어느 행에도 붙지 않는다 — 배지와 같은 자리라
    # 법인이 관계사 배지로 읽혔다(상류 2026-09-07 변경). 전체 문구는 title에 그대로 남는다.
    parts.append('<span class="t" title="%s · %s">%s</span>'
                 % (esc(s["ent"]), esc(s["nm"]), esc(s["nm"])))
    parts.append(flags_html(s["has"]))
    parts.append("</div>")
    return "".join(parts)


def replace_data(path, D):
    """index.html의 `const DATA`를 교체한 **전체 내용 문자열**(쓰지 않는다)."""
    from kce_lib import _blob_span, json_for_html
    import json as _json
    with open(path, encoding="utf-8") as f:
        h = f.read()
    s, e = _blob_span(h)
    blob = json_for_html(D)
    _json.loads(blob)                      # round-trip 검증
    return h[:s] + blob + h[e:]


# ── matrix.html ─────────────────────────────────────────────

def _groups(D):
    """(ent, reg, seg2) 등장 순서로 그룹을 만든다 — DATA.sites가 이미 그룹 정렬돼 있다."""
    order, gid = [], {}
    for s in D["sites"]:
        key = (s["ent"], s["reg"], s.get("seg2"))
        if key not in gid:
            gid[key] = len(order)
            order.append(key)
    return order, gid


def _grp_label(key, n):
    ent, reg, seg = key
    lab = "%s · %s" % (esc(ent), esc(reg))
    if seg:
        lab += " · %s" % esc(seg)
    return '<span class="gt">▾</span>%s <span class="gc">(%d)</span>' % (lab, n)


def _cell(val, yb, fill_cls, title):
    if val is None:
        return '<td class="na%s">–</td>' % (" yb" if yb else "")
    cls = ("yb" if yb else "") + ((" " + fill_cls) if fill_cls else "")
    return '<td class="%s" title="%s">%s</td>' % (cls, esc(title or ""), val)


def _fill_of(s, k):
    """셀 표식 우선순위: 수동정정 > 추정배분 > sFilled 계열."""
    rev = s.get("rev") or {}
    if (rev.get("manual") or [])[k:k + 1] == [True]:
        return MANUAL_CLS
    if (rev.get("manualE") or [])[k:k + 1] == [True]:
        return MANUAL_E_CLS
    src = (rev.get("src") or [None])[k] if rev.get("src") else None
    return FILL_CLS.get(src, ("", ""))


def _sum_cells(mem, nk, ybs):
    """합계 행의 값 셀 — 소속 사업장 rev.diff 합(값이 한 칸도 없으면 –)."""
    tds = []
    for k in range(nk):
        vals = [s["rev"]["diff"][k] for s in mem
                if s.get("rev") and s["rev"]["diff"][k] is not None]
        cls = "gs yb" if ybs[k] else "gs"
        tds.append('<td class="%s">%s</td>' % (cls, bn(sum(vals)) if vals else "–"))
    return "".join(tds)


# tbody 앞뒤 여백은 3줄이다. 원본 페이지는 마크업 줄 사이가 전부 `\n\n\n`이라
# tbody 안쪽 경계도 같은 폭을 따른다(행과 행 사이만 `\n` 하나).
_PAD = ["", "", ""]


def render_matrix_body(D):
    """<tbody id="tb"> 내부 문자열(앞뒤 여백 3줄 포함)."""
    fqF = D["fqF"]
    nk = len(fqF)
    ybs = year_break(fqF)
    order, gid = _groups(D)
    members = {}
    for s in D["sites"]:
        members.setdefault(gid[(s["ent"], s["reg"], s.get("seg2"))], []).append(s)

    lines = list(_PAD)
    # 총합계 행 — 회사 전체 한 줄. 그룹 행과 달리 data-gid가 없어서 접기 대상이 아니고,
    # 펼침 화살표 자리는 빈 칸으로 남긴다(누를 것이 없다).
    lines.append('<tr class="grp tot"><td class="lbl"><span class="gt"> </span>총합계 '
                 '<span class="gc">(%d)</span></td>%s</tr>'
                 % (len(D["sites"]), _sum_cells(D["sites"], nk, ybs)))

    # 묶음 모서리는 그룹을 가로질러 이어진 **행 순서**로 판정한다 — 화면에 그려지는 순서와
    # 같아야 덩어리가 끊기지 않는다.
    flat = [s for g in range(len(order)) for s in members.get(g, [])]
    pins = [s.get("pin") or None for s in flat]
    i = 0
    for g, key in enumerate(order):
        mem = members.get(g, [])
        lines.append('<tr class="grp" data-gid="%d"><td class="lbl">%s</td>%s</tr>'
                     % (g, _grp_label(key, len(mem)), _sum_cells(mem, nk, ybs)))
        for s in mem:
            rev = s.get("rev") or {}
            diff = rev.get("diff") or [None] * nk
            # data-v는 %g 포맷(유효숫자 6) — 원 빌더와 동일. 1003131 → '1.00313e+06'
            dv = ",".join("" if v is None else "%g" % v for v in diff)
            q = " ".join([s["ent"], s["nm"], s.get("cl") or "", s["id"]]).lower()
            tds = []
            for k in range(nk):
                fc, ttl = _fill_of(s, k)
                tds.append(_cell(bn(diff[k]), ybs[k], fc, ttl))
            lbl = label_cell(s, pins[i - 1] if i > 0 else None,
                             pins[i + 1] if i + 1 < len(pins) else None)
            lines.append(
                '<tr data-gid="%d" data-ent="%s" data-q="%s" data-v="%s" '
                'data-id="%s" data-has="%s"><td class="lbl">%s</td>%s</tr>'
                % (g, esc(s["ent"]), esc(q), dv, esc(s["id"]),
                   "".join(str(x) for x in s["has"]), lbl, "".join(tds)))
            i += 1
    lines += _PAD
    return "\n".join(lines)


# ── trace.html ──────────────────────────────────────────────

def _id_key(s):
    """'SCT-2-0007' → ('SCT', 2, 7) — 문자열 정렬이 아니라 숫자 정렬."""
    p = s["id"].split("-")
    try:
        return (p[0], int(p[1]), int(p[2]))
    except (IndexError, ValueError):
        return (p[0], 0, 0)


def _strip(arr, n):
    """분기 축 배열을 실측 구간(n = len(fq))에 맞춘다.

    DATA의 시계열은 예측 4분기를 포함한 fqF 길이(보통 23)인데 trace의 띠는 실측 분기만
    그린다. 짧으면 None으로 채우고, 빈 문자열은 null로 눕힌다 — 화면은 둘을 같게 취급하고
    (`if(!v)`), '없음'은 null로 적는 것이 정직하다.
    """
    a = arr or []
    return [(a[k] if k < len(a) and a[k] else None) for k in range(n)]


def _join_pair(a_arr, b_arr, n):
    """`A · B` 결합 띠 — B가 없으면 A만, A가 없으면 null."""
    out = []
    for k in range(n):
        a = a_arr[k] if k < len(a_arr) else None
        b = b_arr[k] if k < len(b_arr) else None
        out.append(("%s · %s" % (a, b)) if a and b else (a or None))
    return out


def render_trace_sites(D):
    """trace.html의 `SITES` 배열을 재생성.

    SITES[i] = [id, 표시명, r2, r3s, r3c, r11, rp, pin, lump, eb] — 10칸.
    페이지 쪽 구조분해(`SITES.forEach(([id,name,r2,r3s,r3c,r11,rp,pin,lump,eb])`)와
    같은 순서다. 띠 4개는 **그 분기 원문에 실제로 적힌 표기 문자열**이다(없으면 null):
      r2  = evFull.공사명[k]                        — II-4 원문 공사명
      r3s = p8Full._sepNm[k]                        — III-8 별도 기준 원문(품목 · 발주처)
      r3c = p8Full._conNm[k]                        — III-8 연결 기준 원문(품목 · 발주처)
      r11 = xipFull.계약명[k] + ' · ' + 계약상대방[k] — XI-1 원문(계약상대방 병기)

    III-8을 별도/연결 두 벌로 나눈 것이 이번 스키마의 핵심이다. 두 기준의 표기가 갈리는
    분기가 실제로 있어(삼성물산 UAE 원전의 발주처 공백 유무) 한 벌로 합치면 그 사실이 사라진다.
    이미 결합된 문자열이라 여기서 다시 품목·발주처를 붙이지 않는다.

    꼬리 4칸은 배지·묶음 정보로, index/matrix 라벨과 같은 값을 쓴다.
    """
    n = len(D["fq"])
    out = []
    # trace는 그룹 순서가 아니라 **사업장 코드 순**으로 정렬한다(출처별 공백 구간을
    # 위아래로 훑어 비교하는 화면이라 코드 순이 자연스럽다).
    for s in sorted(D["sites"], key=_id_key):
        has = s.get("has") or [0, 0, 0]
        # 출처 보유 플래그로 잠근다. II-4 이력이 없는 사업장(III-8 전용 레코드, has[0]=0)에도
        # evFull에 값이 남아 있을 수 있는데, 그건 원문이 아니라 III-8에서 역채움한 흔적이다
        # (대우건설 DWE-3-0009의 2022Q2·Q3 — sFilled가 'interp'다). '원문이 어디 있었나'를
        # 그리는 지도에 그걸 칠하면 없는 원문을 있다고 말하게 된다. kce_build도 II-4 채움
        # 대상을 같은 플래그로 가른다.
        ef = s.get("evFull") or {}
        r2 = _strip(ef.get("공사명"), n) if has[0] else [None] * n

        pf = s.get("p8Full") or {}
        r3s = _strip(pf.get("_sepNm"), n) if has[1] else [None] * n
        r3c = _strip(pf.get("_conNm"), n) if has[1] else [None] * n

        xf = s.get("xipFull") or {}
        r11 = (_join_pair(xf.get("계약명") or [], xf.get("계약상대방") or [], n)
               if has[2] else [None] * n)

        out.append([s["id"], s["nm"], r2, r3s, r3c, r11,
                    s.get("rp") or "", s.get("pin") or "",
                    1 if s.get("lump") else 0, s.get("eb") or ""])
    return out


def render_trace_consts(D):
    """`const FQ=[...],SITES=[...]` — 종결 세미콜론은 붙이지 않는다.

    이 선언 뒤에는 같은 문장으로 `,WT={…},RAWN={…};`이 이어진다. 그 둘은 DATA에서
    재생성하지 않고 페이지에 있던 것을 그대로 둬야 하므로, 여기서 만드는 것은
    `,WT=` 바로 앞까지다(_TRACE의 매치 경계와 짝을 이룬다).
    """
    import json
    return "const FQ=%s,SITES=%s" % (
        json.dumps(D["fq"], ensure_ascii=False, separators=(",", ":")),
        json.dumps(render_trace_sites(D), ensure_ascii=False, separators=(",", ":")))


# ── 파일 갱신 ────────────────────────────────────────────────

_TB = re.compile(r'(<tbody id="tb">)(.*?)(</tbody>)', re.S)

# 종결자를 세미콜론으로 잡으면 안 된다. SITES 뒤에는 같은 문장으로 `,WT={…},RAWN={…};`이
# 이어지고, 그 다음 JS 첫 줄이 `const wOf=(src,k)=>{const m=WT[src];` 라서 `\]);`에 처음
# 걸리는 곳이 거기다 — 매치가 WT·RAWN 바인딩과 JS 앞머리까지 통째로 삼킨다(17사 실측 4.7~13.5KB).
# 갈아끼우면 그만큼이 조용히 사라져 페이지가 죽는다. 경계를 WT 시작 지점에 못 박고,
# 소비하지 않도록 전방탐색으로 둔다(m.end()가 `,WT=`의 쉼표 앞에 선다).
_TRACE = re.compile(r'const FQ=(\[.*?\]),SITES=(\[.*?\])(?=,WT=)', re.S)


def render_matrix_html(path, D):
    """현재 matrix.html에 새 tbody를 끼운 **전체 내용 문자열**(쓰지 않는다)."""
    with open(path, encoding="utf-8") as f:
        h = f.read()
    m = _TB.search(h)
    if not m:
        raise ValueError("matrix tbody 를 찾지 못함: %s" % path)
    out = h[:m.start(2)] + render_matrix_body(D) + h[m.end(2):]
    # 제목 부제의 사업장 수도 갱신
    return re.sub(r"(\d+)개 사업장 × (\d+)개 분기",
                  "%d개 사업장 × %d개 분기" % (len(D["sites"]), len(D["fqF"])), out)


def update_matrix(path, D):
    out = render_matrix_html(path, D)
    atomic_write(path, out)
    return len(out)


def matrix_matches(path, D):
    """재생성 결과가 현재 파일과 동일한지(바이트) 검사 — 렌더 규칙 회귀 확인용."""
    with open(path, encoding="utf-8") as f:
        h = f.read()
    m = _TB.search(h)
    if not m:
        raise ValueError("matrix tbody 를 찾지 못함: %s" % path)
    return m.group(2) == render_matrix_body(D)


def render_trace_html(path, D):
    """현재 trace.html에 새 FQ/SITES를 끼운 전체 내용 문자열(쓰지 않는다)."""
    with open(path, encoding="utf-8") as f:
        h = f.read()
    m = _TRACE.search(h)
    if not m:
        raise ValueError("trace const FQ/SITES 를 찾지 못함: %s" % path)
    out = h[:m.start()] + render_trace_consts(D) + h[m.end():]
    # 부제의 분기 수도 함께 갱신한다 — 사업장 수만 고치면 새 분기가 붙은 뒤 띠는 20칸인데
    # 제목은 "19개 분기"라고 말하는, 이 모듈이 없애려는 바로 그 스테일이 남는다.
    # matrix와 달리 trace는 실측 분기만 그리므로 fqF가 아니라 fq 길이다.
    return re.sub(r"(\d+)개 사업장 × (\d+)개 분기",
                  "%d개 사업장 × %d개 분기" % (len(D["sites"]), len(D["fq"])),
                  out, count=1)


def update_trace(path, D):
    out = render_trace_html(path, D)
    atomic_write(path, out)
    return len(out)


_HDR_D = re.compile(r"(const D\s*=\s*)")


def _blob_end(html, start):
    depth, i, instr, esc, q = 0, start, False, False, ""
    while i < len(html):
        ch = html[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == q:
                instr = False
        else:
            if ch in "\"'":
                instr, q = True, ch
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ValueError("괄호 불균형")


def render_headers_html(path, co, quarter, headers):
    """headers.html('파서 머리행 지도')에 이번 분기 머리행을 기록한다.

    headers = kce_build 리포트의 rep['headers'] — {'ii4': [{cols,n,lead}], 'p8': [{cols,n,basis}]}.
    이 페이지는 '표를 새로 찾는 게 아니라 파서의 탐색 로직을 그대로 태운' 회귀 감시 장치이므로,
    우리 파서가 실제로 채택한 표를 그대로 남기는 것이 원 설계와 같은 의미를 갖는다.
    """
    import json
    with open(path, encoding="utf-8") as f:
        h = f.read()
    m = _HDR_D.search(h)
    if not m:
        raise ValueError("headers.html 의 const D 를 찾지 못함")
    s = m.end()
    e = _blob_end(h, s)
    D = json.loads(h[s:e])
    if co not in D:
        raise ValueError("headers.html 에 없는 회사: %s" % co)
    if quarter not in D[co]["fq"]:
        D[co]["fq"].append(quarter)
    for key, items in (("ii4", headers.get("ii4") or []),
                       ("p8", headers.get("p8") or [])):
        sec = D[co]["sections"].setdefault(key, {})
        sec[quarter] = [{"tag": (it.get("basis") or ""), "cols": it["cols"],
                         "n": it["n"], "lead": it.get("lead", ""), "pick": True}
                        for it in items]
    from kce_lib import json_for_html
    return h[:s] + json_for_html(D) + h[e:]


def update_headers(path, co, quarter, headers):
    out = render_headers_html(path, co, quarter, headers)
    atomic_write(path, out)
    return len(out)


def trace_matches(path, D):
    """SITES 배열이 재생성 결과와 같은지(JSON 동치) 검사."""
    import json
    with open(path, encoding="utf-8") as f:
        h = f.read()
    m = _TRACE.search(h)
    if not m:
        raise ValueError("trace const FQ/SITES 를 찾지 못함: %s" % path)
    return (json.loads(m.group(1)) == D["fq"]
            and json.loads(m.group(2)) == render_trace_sites(D))


if __name__ == "__main__":
    import argparse
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--co", required=True)
    ap.add_argument("--check", action="store_true", help="쓰지 않고 동일성만 확인")
    a = ap.parse_args()
    kce = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    D = extract_data(os.path.join(kce, a.co, "index.html"))
    mp = os.path.join(kce, a.co, "matrix.html")
    tp = os.path.join(kce, a.co, "trace.html")
    if a.check:
        print("%s matrix 동일: %s · trace 동일: %s"
              % (a.co, matrix_matches(mp, D), trace_matches(tp, D)))
    else:
        print("%s 재생성: matrix %d · trace %d bytes"
              % (a.co, update_matrix(mp, D), update_trace(tp, D)))
