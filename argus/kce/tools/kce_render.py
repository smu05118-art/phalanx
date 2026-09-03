#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_render — DATA에서 파생 페이지를 재생성한다 (matrix.html · trace.html).

index.html의 `const DATA`만 갱신하면 matrix/trace는 옛 데이터로 남는다(UPDATE.md §7).
이 모듈이 그 둘을 DATA로부터 다시 만들어 스테일을 없앤다.

정합성 근거: 재생성 결과가 현재 저장된 원본과 **바이트 단위로 동일**함을 7사 전부에서 확인했다
(tools/tests/test_render.py). 즉 렌더 규칙이 원 빌더와 동치다.

backtest.html(워크포워드 재실행 필요)·curve.html(곡선 재적합)·headers.html(파서 로그)은 미구현.
"""
import html as _html
import re

from kce_lib import atomic_write, extract_data

# ── 공통 ────────────────────────────────────────────────────

# matrix 범례는 5종뿐이다 — 'xi1'(XI-1 교차참조 확정값)은 원문 확정값이라 실측과 같이
# 테두리 없이 그린다(index.html 상세표에서만 민트 점선 .flx로 구분). 원본 대조로 확인.
FILL_CLS = {
    "p8":     ("fl",  "III-8 교차참조 추정값"),
    "interp": ("fli", "선형보간 추정값"),
    "fcst":   ("ffc", "S-curve 예측값(미래 또는 장기 미보고 구간)"),
    "bcst":   ("ffc", "착공일 기준 S-curve 역산 추정값(첫 공시 이전 구간)"),
}
MANUAL_CLS = ("fm", "수동 정정값(원문 오류로 판단되어 사용자 확인 후 교정)")
MANUAL_E_CLS = ("fe", "추정 배분값(원문에 정답이 없어 인접 실측 보간으로 추정)")


def esc(s):
    """원 빌더와 동일한 이스케이프. 실제 산출물에 쓰인 엔티티는 &amp;와 &#39; 둘뿐이며
    큰따옴표를 포함한 데이터는 7사 전체에 존재하지 않는다(전수 확인)."""
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


def label_cell(s):
    """사업장 라벨 셀(matrix·trace 공통 구조)."""
    rp = s.get("rp")
    div = '<div class="it rps">' if rp else '<div class="it">'
    parts = [div,
             '<span class="star" data-id="%s" title="즐겨찾기 (다시 확인할 프로젝트 표시)">☆</span>'
             % esc(s["id"]),
             '<span class="cid" title="사업장 코드">%s</span>' % esc(s["id"])]
    if rp:
        parts.append('<span class="rpb" title="관계사 발주 — %s">%s</span>'
                     % (esc(rp), esc(rp)))
    # 관계사 배지가 붙는 행은 법인 접두를 생략한다(배지가 폭을 먹어 공사명이 잘림).
    # title에는 항상 법인을 유지 — LOGIC.md §6-7.
    body = (esc(s["nm"]) if rp
            else "<b>%s</b> · %s" % (esc(s["ent"]), esc(s["nm"])))
    parts.append('<span class="t" title="%s · %s">%s</span>'
                 % (esc(s["ent"]), esc(s["nm"]), body))
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


def render_matrix_body(D):
    """<tbody id="tb"> 내부 문자열(선두 개행 포함, 말미 개행 포함)."""
    fqF = D["fqF"]
    ybs = year_break(fqF)
    order, gid = _groups(D)
    members = {}
    for s in D["sites"]:
        members.setdefault(gid[(s["ent"], s["reg"], s.get("seg2"))], []).append(s)

    lines = [""]
    for g, key in enumerate(order):
        mem = members.get(g, [])
        # 그룹 합계 = 소속 사업장 rev.diff 합(값이 하나도 없으면 –)
        tds = []
        for k in range(len(fqF)):
            vals = [s["rev"]["diff"][k] for s in mem
                    if s.get("rev") and s["rev"]["diff"][k] is not None]
            cls = "gs yb" if ybs[k] else "gs"
            tds.append('<td class="%s">%s</td>'
                       % (cls, bn(sum(vals)) if vals else "–"))
        lines.append('<tr class="grp" data-gid="%d"><td class="lbl">%s</td>%s</tr>'
                     % (g, _grp_label(key, len(mem)), "".join(tds)))
        for s in mem:
            rev = s.get("rev") or {}
            diff = rev.get("diff") or [None] * len(fqF)
            # data-v는 %g 포맷(유효숫자 6) — 원 빌더와 동일. 1003131 → '1.00313e+06'
            dv = ",".join("" if v is None else "%g" % v for v in diff)
            q = " ".join([s["ent"], s["nm"], s.get("cl") or "", s["id"]]).lower()
            tds = []
            for k in range(len(fqF)):
                fc, ttl = _fill_of(s, k)
                tds.append(_cell(bn(diff[k]), ybs[k], fc, ttl))
            lines.append(
                '<tr data-gid="%d" data-ent="%s" data-q="%s" data-v="%s" '
                'data-id="%s" data-has="%s"><td class="lbl">%s</td>%s</tr>'
                % (g, esc(s["ent"]), esc(q), dv, esc(s["id"]),
                   "".join(str(x) for x in s["has"]), label_cell(s), "".join(tds)))
    lines.append("")
    return "\n".join(lines)


# ── trace.html ──────────────────────────────────────────────

def _id_key(s):
    """'SCT-2-0007' → ('SCT', 2, 7) — 문자열 정렬이 아니라 숫자 정렬."""
    p = s["id"].split("-")
    try:
        return (p[0], int(p[1]), int(p[2]))
    except (IndexError, ValueError):
        return (p[0], 0, 0)

def render_trace_sites(D):
    """trace.html의 `SITES` 배열을 재생성.

    SITES[i] = [id, 표시명, r2(II-4), r3(III-8), r11(XI-1), rp]
    각 칸은 **그 분기 원문에 실제로 적힌 표기 문자열**이다(없으면 null):
      r2  = evFull.공사명[k]                       — II-4 원문 공사명(실측 분기만 값이 있음)
      r3  = p8Full.품목[k] + ' · ' + 발주처[k]      — III-8 원문(발주처 병기)
      r11 = xipFull.계약명[k] + ' · ' + 계약상대방[k] — XI-1 원문(계약상대방 병기)
    """
    n = len(D["fq"])
    out = []
    # trace는 그룹 순서가 아니라 **사업장 코드 순**으로 정렬한다(출처별 공백 구간을
    # 위아래로 훑어 비교하는 화면이라 코드 순이 자연스럽다).
    for s in sorted(D["sites"], key=_id_key):
        ef = s.get("evFull") or {}
        r2 = list((ef.get("공사명") or [None] * n))[:n]

        pf = s.get("p8Full") or {}
        item, cl = pf.get("품목") or [], pf.get("발주처") or []
        r3 = []
        for k in range(n):
            a = item[k] if k < len(item) else None
            b = cl[k] if k < len(cl) else None
            r3.append(("%s · %s" % (a, b)) if a and b else (a or None))

        xf = s.get("xipFull") or {}
        nmv, cpv = xf.get("계약명") or [], xf.get("계약상대방") or []
        r11 = []
        for k in range(n):
            a = nmv[k] if k < len(nmv) else None
            b = cpv[k] if k < len(cpv) else None
            r11.append(("%s · %s" % (a, b)) if a and b else (a or None))

        out.append([s["id"], s["nm"], r2, r3, r11, s.get("rp") or ""])
    return out


def render_trace_consts(D):
    """`const FQ=[...],SITES=[...];` 한 줄."""
    import json
    return "const FQ=%s,SITES=%s;" % (
        json.dumps(D["fq"], ensure_ascii=False, separators=(",", ":")),
        json.dumps(render_trace_sites(D), ensure_ascii=False, separators=(",", ":")))


# ── 파일 갱신 ────────────────────────────────────────────────

_TB = re.compile(r'(<tbody id="tb">)(.*?)(</tbody>)', re.S)
_TRACE = re.compile(r'const FQ=(\[.*?\]),SITES=(\[.*?\]);', re.S)


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
    return m.group(2) == render_matrix_body(D)


def render_trace_html(path, D):
    """현재 trace.html에 새 FQ/SITES를 끼운 전체 내용 문자열(쓰지 않는다)."""
    with open(path, encoding="utf-8") as f:
        h = f.read()
    m = _TRACE.search(h)
    if not m:
        raise ValueError("trace const FQ/SITES 를 찾지 못함: %s" % path)
    out = h[:m.start()] + render_trace_consts(D) + h[m.end():]
    return re.sub(r"(\d+)개 사업장", "%d개 사업장" % len(D["sites"]), out, count=1)


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
