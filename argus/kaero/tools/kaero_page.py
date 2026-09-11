#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero_page — 한국우주항공 탭의 페이지를 만든다.

  index.html            허브 — 회사 카드(잔고·배수·통화·고객) · 영역별 잔고 구성 ·
                        USD 잔고와 원/달러 민감도 각주
  coverage.html         모집단 전수(네 겹)와 편입 근거 · ④ 본문 탐색 · **못 읽은 것 목록**
  <종목코드>/index.html  회사 — 잔고 롤포워드 · 부문 매출 · 커버리지(년) · 고객 구성 ·
                        통화 구성 · 계약 원장 · **kdef·kship 중복 표시**

축이 조선·방산과 다른 이유는 원문에 있다(FINDINGS):
  · **통화가 표마다 다르다.** 합산 KPI를 만들지 않는다 — 통화별로 나란히 싣고 환산하지 않는다.
  · **계약 원장이 정기보고서 안에 있다.** 수시공시는 연 0.75건뿐이라 뼈대가 못 된다.
  · **겸업사는 부문을 갈라야 한다.** 한화에어로 잔고 114.9조 중 항공은 32.3조뿐이다.

    python3 kaero_page.py --all
"""
import argparse
import collections
import os
import sys

from kaero_lib import (CUR_ORDER, CURRENCIES, E, KAERO, CHART_DEFAULTS_JS, TABLE_JS,
                       atomic_write, cur_unit, domain_color, domain_label, fmt_money,
                       fmt_money_u, fmt_n, fmt_x, json_for_html, load_asset, page, pct)
from kaero_universe import load as load_universe
import kaero_contracts
import kaero_reports
import kaero_suppliers

DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s"
ROLE_KO = {"prime": "체계업체", "struct": "기체구조물", "engine": "엔진·부품", "space": "우주",
           "part": "부품", "service": "정비·용역", "material": "소재"}
TAB_KO = {"kdef": "🛡 한국방산(kdef)", "kship": "⚓ 한국조선(kship)", "other": "이 탭 밖(민수 기타)"}
TAB_HREF = {"kdef": "../../kdef/index.html", "kship": "../../kship/index.html", "other": ""}
SHAPE_KO = {"roll": "기초+신규−기납품", "openclose": "기초·기말만", "gross": "총액−기납품",
            "item": "품목·계약별", "balance": "잔액 한 줄"}
GRADE_KO = {"A": "공시 표에 그대로", "B": "공시 본문 문구", "C": "약칭을 사전으로 폄(추정)"}


def load_all():
    uni = load_universe()
    reports = kaero_reports.load()
    here = os.path.dirname(os.path.abspath(__file__))
    probe_p = os.path.join(here, "assets", "universe_probe.json")
    return {
        "uni": uni,
        "by_stock": {r["stock"]: r for r in uni},
        "doms": load_asset("domains.json")["domains"],
        "natures": load_asset("natures.json")["natures"],
        "tiers": {t["id"]: t for t in load_asset("tiers.json")["tiers"]},
        "tax": load_asset("parts_taxonomy.json"),
        "contracts": kaero_contracts.load(),
        "reports": reports.get("companies", {}),
        "quarters": reports.get("quarters", []),
        "sup": {c["stock"]: c for c in kaero_suppliers.load().get("cos", [])},
        "probe": load_asset("universe_probe.json") if os.path.exists(probe_p) else {},
    }


def nature_ko(data, nid):
    for n in data["natures"]:
        if n["id"] == nid:
            return n["ko"]
    return nid


# 계약 성격의 색은 영역 색과 **다른 팔레트**를 쓴다 — 같은 색을 돌려쓰면 한 화면에서
# `RSP`와 `민수 기체구조물`이 같은 파랑으로 보인다. 슬롯에 고정한다(필터로 줄어도 재배색 금지).
NATURE_HEX = {"RSP": "#c084fc", "PBL": "#2dd4bf", "DEV": "#fbbf24",
              "MRO": "#60a5fa", "LTA": "#fb7185", "BATCH": "#7c8698"}


def nature_color(data, nid):
    return NATURE_HEX.get(nid, "#5d6675")


def tier_ko(data, tid):
    t = data["tiers"].get(tid)
    return t["ko"] if t else "미상"


# ── 회사 집계 ───────────────────────────────────────────────

def summary(stock, data):
    rec = data["by_stock"][stock]
    comp = data["reports"].get(stock) or {}
    qs = [q for q in sorted((comp.get("quarters") or {})) if comp["quarters"][q].get("ok")]
    latest = comp["quarters"][qs[-1]] if qs else None
    cons = [c for c in data["contracts"] if c["stock"] == stock]
    backlog = (latest or {}).get("backlog") or {}
    curs = [c for c in CUR_ORDER if backlog.get(c)]
    dom_amt = collections.defaultdict(lambda: collections.defaultdict(float))
    for did, per in ((latest or {}).get("domains") or {}).items():
        for cur, v in per.items():
            dom_amt[did][cur] += v
    nat_amt = collections.defaultdict(lambda: collections.defaultdict(float))
    for nid, per in ((latest or {}).get("natures") or {}).items():
        for cur, v in per.items():
            nat_amt[nid][cur] += v
    exp = (latest or {}).get("revenue_export")
    dom_rev = (latest or {}).get("revenue_domestic")
    sup = data["sup"].get(stock) or {}
    return {
        "stock": stock, "rec": rec, "comp": comp, "qs": qs, "latest_q": qs[-1] if qs else None,
        "latest": latest, "contracts": cons,
        "backlog": backlog, "curs": curs,
        "fy": (latest or {}).get("revenue_fy"), "fy_cur": (latest or {}).get("revenue_cur"),
        "coverage": (latest or {}).get("coverage_years"),
        "coverage_note": (latest or {}).get("coverage_note") or "",
        "exp_share": pct(exp, (exp or 0) + (dom_rev or 0)) if latest else None,
        "dom_amt": dom_amt, "nat_amt": nat_amt,
        "ledger": (latest or {}).get("contracts") or [],
        "dup": (latest or {}).get("dup_segments") or [],
        "customers": sup.get("customers") or [],
        "cats": sup.get("cats") or [],
        "notes": (latest or {}).get("notes") or [],
        "security": bool((latest or {}).get("security_note")),
        "domains_src": (latest or {}).get("domains_src") or "",
    }


def has_page(s):
    """페이지를 만들 만한 회사인가 — 공시에서 무언가를 읽었어야 한다."""
    return bool(s["qs"] or s["contracts"] or s["customers"] or s["cats"])


def dom_guess(s):
    """수주표·매출표 어느 쪽에서도 영역이 안 나온 회사 — KIND 주요제품으로 **추정**한다.

    하이즈항공이 그렇다. 수주표 품목은 `조립`·`부품`, 부문은 `조립사업부`·`부품사업부`뿐인데
    KIND 주요제품은 `B787 날개구조물 등` 이다. 추정이라고 화면에 적는다(COMMON §0-1)."""
    if s["dom_amt"] and set(s["dom_amt"]) != {"other"}:
        return None
    did = kaero_reports.domain_of(s["rec"].get("product") or "")
    return did if did != "other" else None


# ── 조각 ───────────────────────────────────────────────────

def _chip(label, color=None, n=None, href=None, title=""):
    sw = '<i class="sw" style="background:%s"></i>' % E(color) if color else ""
    nn = ' <span class="n">%s</span>' % E(str(n)) if n is not None else ""
    inner = "%s%s%s" % (sw, E(label), nn)
    tt = ' title="%s"' % E(title) if title else ""
    if href:
        return '<a class="chip" href="%s"%s>%s</a>' % (E(href), tt, inner)
    return '<span class="chip"%s>%s</span>' % (tt, inner)


def _sw(color):
    return ('<i style="display:inline-block;width:9px;height:9px;border-radius:3px;'
            'background:%s;margin-right:6px;vertical-align:-1px"></i>' % E(color))


def _pill(txt, cls="", title=""):
    return '<span class="pill %s"%s>%s</span>' % (cls, (' title="%s"' % E(title)) if title else "",
                                                  E(txt))


def money_cell(per, key=None):
    """통화별 금액을 한 칸에 — **더하지 않는다**(FINDINGS §1)."""
    if not per:
        return "—"
    bits = []
    for cur in CUR_ORDER:
        v = per.get(cur)
        if v:
            bits.append('%s<small> %s</small>' % (fmt_money(v, cur), cur_unit(cur)))
    return " · ".join(bits) or "—"


def ledger_table(rows, tid="lg", show_company=False, by_stock=None, rel="../"):
    """계약 원장 — 정기보고서 II-4(와 상세표)의 계약 줄. 수량은 싣지 않는다(스펙 ⑥)."""
    tr = []
    for c in rows:
        who = ""
        if show_company:
            nm = (by_stock or {}).get(c["stock"], {}).get("name", c.get("stock", ""))
            who = ('<td class="l"><a href="%s%s/index.html">%s</a></td>'
                   % (rel, E(c.get("stock", "")), E(nm)))
        cust = " ".join(_chip(h["name"], None, title="근거 등급 %s — %s"
                              % (h.get("grade", "B"), GRADE_KO.get(h.get("grade", "B"), "")))
                        for h in (c.get("customers") or [])) or '<span class="mut">—</span>'
        tr.append(
            '<tr><td class="l">%s%s</td>%s<td class="l">%s</td><td class="l">%s</td>'
            '<td class="l">%s</td><td class="l">%s</td>'
            '<td data-v="%.3f">%s</td><td data-v="%.3f">%s</td><td data-v="%.3f"><b>%s</b></td>'
            '<td class="l">%s</td><td class="l">%s</td></tr>'
            % (_sw(domain_color(c["domain"])), E((c["label"] or "")[:74]), who,
               E(domain_label(c["domain"])), E(_nature_ko(c["nature"])),
               E(c.get("order_date") or "—"), E(c.get("due") or "—"),
               (c.get("gross") or 0), fmt_money(c.get("gross"), c["cur"]),
               (c.get("delivered") or 0), fmt_money(c.get("delivered"), c["cur"]),
               (c.get("closing") or 0), fmt_money(c.get("closing"), c["cur"]),
               "%s %s" % (E(c["cur"]), E(cur_unit(c["cur"]))), cust))
    head = ('<tr><th class="l">계약·품목(원문)</th>%s<th class="l">영역</th><th class="l">성격</th>'
            '<th class="l">수주</th><th class="l">납기</th><th>수주총액</th><th>기납품</th>'
            '<th>잔고</th><th class="l">통화</th><th class="l">고객</th></tr>'
            % ('<th class="l">회사</th>' if show_company else ""))
    return ('<div class="ctl"><input data-filter="#%s" type="search" '
            'placeholder="계약명·영역·성격·고객 검색"></div>'
            '<div class="wrap tall"><table id="%s" data-sortable><thead>%s</thead>'
            '<tbody>%s</tbody></table></div>' % (tid, tid, head, "".join(tr)))


def _nature_ko(nid):
    return kaero_reports.NATURE_LABEL.get(nid, nid or "—")


# ── 회사 페이지 ─────────────────────────────────────────────

def company_html(s, data):
    rec, latest = s["rec"], s["latest"]
    kpi = []
    if s["curs"]:
        first = s["curs"][0]
        kpi.append('<div class="hero"><b>%s<small>%s</small></b><span>수주잔고 · 정기보고서 %s</span>%s</div>'
                   % (fmt_money(s["backlog"][first], first), E(cur_unit(first)),
                      E(s["latest_q"] or "—"),
                      ('<i class="mut">%s</i>' % E(" · ".join(
                          "%s %s" % (fmt_money(s["backlog"][c], c), cur_unit(c))
                          for c in s["curs"][1:])) if len(s["curs"]) > 1 else "")))
    else:
        why = " · ".join(s["notes"][:2]) or "정기보고서 II-4 수주표를 찾지 못함"
        kpi.append('<div class="hero"><b class="mut">—</b><span>수주잔고</span>'
                   '<i class="mut">%s</i></div>' % E(why))
    if s["coverage"] is not None:
        kpi.append('<div><b>%s<small>년</small></b><span>잔고 커버리지 = 잔고 ÷ 연매출</span>'
                   '<i class="mut">분모 %s(%s)</i></div>'
                   % (fmt_x(s["coverage"]), fmt_money_u(s["fy"], s["fy_cur"] or "KRW"),
                      E((latest or {}).get("revenue_fy_col") or "직전 사업연도")))
    else:
        kpi.append('<div><b class="mut">—</b><span>잔고 커버리지</span>'
                   '<i class="mut">%s</i></div>'
                   % E(s["coverage_note"] or "잔고 또는 연매출 열을 못 읽음"))
    if s["exp_share"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>수출 비중(내수/수출 표)</span></div>'
                   % s["exp_share"])
    rsp = s["nat_amt"].get("RSP") or {}
    if rsp:
        kpi.append('<div><b>%s</b><span>RSP 잔고 <i>수익분배</i></span>'
                   '<i class="mut">엔진 인도 수십 년에 걸쳐 회수</i></div>' % money_cell(rsp))
    kpi.append('<div><b>%d<small>건</small></b><span>계약 줄(정기보고서 II-4)</span>'
               '<i class="mut">수시공시 계약 %d건은 따로</i></div>'
               % (len(s["ledger"]), len(s["contracts"])))

    # 잔고 롤포워드 — 통화별로 한 줄씩
    roll = []
    for q in s["qs"]:
        v = s["comp"]["quarters"][q]
        curs = [c for c in CUR_ORDER if (v.get("backlog") or {}).get(c) is not None]
        if not curs:
            roll.append('<tr><td class="l">%s</td><td class="l mut" colspan="6">%s</td>'
                        '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                        % (E(q), E(" · ".join(v.get("notes") or []) or "수주표 없음"),
                           E(DART % (v.get("rcp") or ""))))
            continue
        for i, c in enumerate(curs):
            roll.append('<tr><td class="l">%s</td><td class="l">%s</td><td>%s</td><td>%s</td>'
                        '<td>%s</td><td><b>%s</b></td><td class="l mut">%s</td>'
                        '<td class="l">%s</td></tr>'
                        % (E(q if i == 0 else ""), E("%s(%s)" % (c, cur_unit(c))),
                           fmt_money((v.get("opening") or {}).get(c), c),
                           fmt_money((v.get("gross") or {}).get(c), c),
                           fmt_money((v.get("delivered") or {}).get(c), c),
                           fmt_money((v.get("backlog") or {}).get(c), c),
                           E(SHAPE_KO.get((v.get("shapes") or {}).get(c),
                                          (v.get("shapes") or {}).get(c) or "—")),
                           E(DART % (v.get("rcp") or "")) if i == 0 else ""))
    roll_html = ('<div class="wrap"><table><thead><tr><th class="l">분기</th><th class="l">통화</th>'
                 '<th>기초</th><th>수주총액</th><th>기납품</th><th>수주잔고</th>'
                 '<th class="l">표 모양</th><th class="l">출처</th></tr></thead>'
                 '<tbody>%s</tbody></table></div>' % "".join(roll)) if roll else \
        '<p class="mut">이 회사의 정기보고서에서 수주표를 찾지 못했습니다.</p>'

    # 겸업사 중복 표시
    dup_html = ""
    if s["dup"]:
        rows = "".join(
            '<tr><td class="l">%s</td><td class="l">%s</td><td>%s</td><td>%s</td></tr>'
            % (E(d["seg"]),
               ('<a href="%s">%s</a>' % (E(TAB_HREF[d["tab"]]), E(TAB_KO[d["tab"]])))
               if TAB_HREF.get(d["tab"]) else E(TAB_KO.get(d["tab"], d["tab"])),
               E(str(d.get("n", 1))), fmt_money_u(d["closing"], d["cur"]))
            for d in sorted(s["dup"], key=lambda d: -(d["closing"] or 0)))
        tot = collections.defaultdict(float)
        for d in s["dup"]:
            tot[d["cur"]] += d["closing"] or 0
        dup_html = ('<section class="card"><h2>다른 탭과 겹치는 부문 '
                    '<em>이 회사의 공시 수주표에는 우주항공이 아닌 부문이 함께 들어 있습니다 — '
                    '이 탭 집계에서 뺐습니다</em></h2>'
                    '<div class="wrap"><table><thead><tr><th class="l">부문(원문)</th>'
                    '<th class="l">어느 탭 몫인가</th><th>계약 줄</th><th>수주잔고</th></tr></thead>'
                    '<tbody>%s</tbody></table></div>'
                    '<p class="mut" style="font-size:12px;margin-top:10px">공시 수주표 전체 %s 중 '
                    '우주항공 부문은 <b>%s</b> 입니다. 세 탭이 같은 돈을 세 번 세지 않도록 '
                    '부문으로 나눴습니다.</p></section>'
                    % (rows, money_cell(latest.get("backlog_all") or {}), money_cell(s["backlog"])))

    # 부문 매출
    seg_html = ""
    segs = (latest or {}).get("revenue_segments") or []
    ssegs = (latest or {}).get("sales_segments") or []
    if segs or ssegs:
        rows = []
        for r in segs:
            rows.append('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s%s</td>'
                        '<td class="l">%s</td><td data-v="%.3f">%s</td></tr>'
                        % (E(r["seg"] or "(부문 표기 없음)"), E((r["item"] or "")[:40]),
                           _sw(domain_color(r["domain"])), E(domain_label(r["domain"])),
                           E(r["kind"]), r["val"] or 0,
                           fmt_money(r["val"], (latest or {}).get("revenue_cur") or "KRW")))
        for r in ssegs:
            rows.append('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s%s</td>'
                        '<td class="l">%s</td><td data-v="%.3f">%s</td></tr>'
                        % (E(r["seg"] or "(부문 표기 없음)"), E((r["item"] or "")[:40]),
                           _sw(domain_color(r["domain"])), E(domain_label(r["domain"])),
                           ("비중 %.1f%%" % r["pct"]) if r.get("pct") else
                           (("행 통화 %s" % r["row_cur"]) if r.get("row_cur") else "—"),
                           r["val"] or 0,
                           fmt_money(r["val"], r.get("row_cur")
                                     or (latest or {}).get("revenue_cur") or "KRW")))
        seg_html = ('<section class="card"><h2>부문 매출 <em>%s · 부문 이름은 원문 그대로, '
                    '영역 판정은 이름에서(추정)</em></h2><div class="wrap"><table data-sortable>'
                    '<thead><tr><th class="l">부문(원문)</th><th class="l">품목</th>'
                    '<th class="l">영역</th><th class="l">구분</th><th>금액</th></tr></thead>'
                    '<tbody>%s</tbody></table></div></section>'
                    % (E(s["latest_q"] or ""), "".join(rows)))

    # 고객
    cust_html = ""
    if s["customers"]:
        rows = "".join(
            '<tr><td class="l">%s%s</td><td class="l">%s</td><td class="l">%s %s</td>'
            '<td class="l mut">%s</td></tr>'
            % (('<a href="../%s/index.html">%s</a>' % (E(c["stock"]), E(c["name"])))
               if c.get("stock") and c["stock"] in data["by_stock"] else E(c["name"]),
               (' %s' % _pill("추정")) if c.get("evidence") == "C" else "",
               E(tier_ko(data, c.get("tier"))),
               _pill(c["basis_ko"], "up" if c["grade"] <= 2 else ""),
               "", E((c.get("detail") or "")[:110]))
            for c in s["customers"])
        cust_html = ('<section class="card"><h2>고객 <em>근거 등급: 매출처 표 &gt; 수주표 품목 &gt; '
                     '계약공시 상대 &gt; 본문 언급. 약칭을 사전으로 편 것은 <b>추정</b>으로 적습니다</em></h2>'
                     '<div class="wrap"><table data-sortable><thead><tr><th class="l">고객</th>'
                     '<th class="l">계층</th><th class="l">근거</th><th class="l">근거 내용</th>'
                     '</tr></thead><tbody>%s</tbody></table></div></section>' % rows)

    parts_html = ""
    if s["cats"]:
        chips = " ".join(_chip(cat_ko(data, h["cat"]), None, href="../parts.html#" + h["cat"],
                               title="근거: %s 「%s」"
                               % (kaero_suppliers.SRC_KO.get(h["src"], h["src"]), h["kw"]))
                         for h in s["cats"])
        parts_html = ('<section class="card"><h2>부품 분류 <em>공시 품목명·계약명·II절 본문·'
                      'KIND 주요제품 문구에서 읽은 낱말 — 칩에 근거가 붙어 있습니다</em></h2>'
                      '<div class="chips">%s</div></section>' % chips)

    # 수시공시 계약(얇은 원장)
    con_html = ""
    if s["contracts"]:
        rows = "".join(
            '<tr><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td>'
            '<td class="l">%s</td><td>%s</td><td class="l">%s</td>'
            '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
            % (E(c["signed"] or c["start"] or "—"), E((c["name"] or "—")[:60]),
               E(domain_label(c["domain"])), E(_nature_ko(c["nature"])),
               fmt_money_u(c["amount"], c["cur"] or "KRW"), E((c["party"] or "—")[:36]),
               E(DART % c["rcp"]))
            for c in sorted(s["contracts"], key=lambda c: (c["signed"] or c["start"] or ""),
                            reverse=True))
        con_html = ('<section class="card"><h2>수시공시 계약 <em>「단일판매ㆍ공급계약체결」 %d건 — '
                    '이 산업은 LTA가 자동 연장돼 새 공시가 드뭅니다(표본 중앙값 연 0.75건)</em></h2>'
                    '<div class="wrap"><table data-sortable><thead><tr><th class="l">수주일</th>'
                    '<th class="l">계약명</th><th class="l">영역</th><th class="l">성격</th>'
                    '<th>금액</th><th class="l">상대</th><th class="l">출처</th></tr></thead>'
                    '<tbody>%s</tbody></table></div></section>' % (len(s["contracts"]), rows))

    notes = []
    if len(s["curs"]) > 1:
        notes.append("이 회사의 수주표는 <b>통화가 나뉘어</b> 공시됩니다. 환산하지 않고 통화별로 "
                     "싣습니다 — 원/달러가 10원 오르면 %s 잔고의 원화 환산액이 그만큼 움직입니다."
                     % ("·".join(c for c in s["curs"] if c != "KRW")))
    if s["coverage_note"]:
        notes.append(E(s["coverage_note"]))
    if s["security"]:
        notes.append("이 회사는 정기보고서에 <b>보안·영업비밀로 수주 상세를 생략한다</b>고 적었습니다.")
    for n in s["notes"]:
        notes.append(E(n))
    if s["domains_src"] == "매출품목":
        notes.append("수주표 품목 열이 <b>발주처 이름</b>이라 영역을 못 가릅니다 — 영역 구성은 "
                     "수주잔고가 아니라 <b>매출 품목</b>으로 만들었습니다.")
    notes.append("잔고 커버리지는 '몇 년치 일감'을 보는 값입니다. 이 산업의 장기공급계약(LTA)은 "
                 "기종이 단종될 때까지 자동 연장되는 관행이 있어 <b>프로그램 누적 총액</b>이 "
                 "잔고로 잡히는 회사가 있습니다 — 배수가 10년을 넘으면 그렇게 읽으십시오.")

    dom_rows = [(d, dict(s["dom_amt"][d])) for d in [x["id"] for x in data["doms"]]
                if s["dom_amt"].get(d)]
    nat_rows = [(n, dict(s["nat_amt"][n])) for n in [x["id"] for x in data["natures"]]
                if s["nat_amt"].get(n)]
    main_cur = s["curs"][0] if s["curs"] else "KRW"
    chart = {
        "cur": main_cur, "unit": cur_unit(main_cur), "div": CURRENCIES[main_cur]["div"],
        "roll": [{"q": q, "v": (s["comp"]["quarters"][q].get("backlog") or {}).get(main_cur)}
                 for q in s["qs"]],
        "doms": [{"ko": domain_label(d), "color": domain_color(d), "amt": per.get(main_cur, 0)}
                 for d, per in dom_rows],
        "nats": [{"ko": nature_ko(data, n), "color": nature_color(data, n),
                  "amt": per.get(main_cur, 0)} for n, per in nat_rows],
    }
    body = """
<div class="kpi">%s</div>
<div class="grid2" style="margin-top:20px">
 <section class="card" style="margin-top:0"><h2>수주잔고 추이 <em>%s · %s</em></h2>
  <div class="chart"><canvas id="cRoll"></canvas></div></section>
 <section class="card" style="margin-top:0"><h2>영역 구성 <em>%s · %s</em></h2>
  <div class="chart"><canvas id="cDom"></canvas></div></section>
</div>
<section class="card"><h2>수주 롤포워드 <em>통화마다 한 줄입니다 — 합치지 않습니다</em></h2>%s</section>
%s
<section class="card"><h2>계약 원장 <em>정기보고서 II-4(와 상세표)의 계약 줄 %d건 · 수량은 공시가 '-' 라 싣지 않습니다</em></h2>%s</section>
<div class="grid2">
 <section class="card"><h2>계약 성격 <em>RSP·PBL·LTA·개발 — 이익 성격이 다릅니다</em></h2>
  <div class="chart"><canvas id="cNat"></canvas></div>
  <p class="mut" style="font-size:12px;margin-top:10px">RSP는 개발비를 분담하고 엔진 인도 수십 년에 걸쳐
   회수하는 구조라 일반 수주와 성격이 다릅니다. LTA는 기종 단종까지 자동 연장되는 장기공급계약입니다.
   문구에서 못 읽으면 '양산·단발'입니다.</p></section>
 <section class="card"><h2>통화 구성 <em>환산하지 않습니다</em></h2>%s</section>
</div>
%s
%s
%s
%s
<div class="note info">%s</div>
<script>const DATA=%s;</script>
<script>%s</script>
<script>
(function(){
  var div=DATA.div||1;
  function scale(v){return v==null?null:Math.round(v/div)}
  if(DATA.roll.length){
    new Chart(document.getElementById('cRoll'),{type:'line',data:{labels:DATA.roll.map(function(r){return r.q}),
      datasets:[{label:'수주잔고('+DATA.unit+')',data:DATA.roll.map(function(r){return scale(r.v)}),
        borderColor:'#3987e5',backgroundColor:'rgba(57,135,229,.18)',fill:true,tension:.25,spanGaps:true}]},
      options:{scales:{y:{ticks:{callback:function(v){return v.toLocaleString()}}},x:{grid:{display:false}}}}});
  }
  if(DATA.doms.length){
    new Chart(document.getElementById('cDom'),{type:'bar',data:{labels:DATA.doms.map(function(d){return d.ko}),
      datasets:[{label:DATA.unit,data:DATA.doms.map(function(d){return scale(d.amt)}),
        backgroundColor:DATA.doms.map(function(d){return d.color})}]},
      options:{indexAxis:'y',plugins:{legend:{display:false}},
        scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
  }
  if(DATA.nats.length){
    new Chart(document.getElementById('cNat'),{type:'doughnut',data:{labels:DATA.nats.map(function(d){return d.ko}),
      datasets:[{data:DATA.nats.map(function(d){return scale(d.amt)}),
        backgroundColor:DATA.nats.map(function(d){return d.color})}]},
      options:{plugins:{tooltip:{callbacks:{label:function(c){
        return c.label+': '+(c.parsed||0).toLocaleString()+' '+DATA.unit}}}}}});
  }
})();
</script>
<script>%s</script>
""" % ("".join(kpi), E(s["latest_q"] or ""), E(cur_unit(main_cur)),
       E("수주잔고 기준" if s["domains_src"] == "수주표" else "매출 품목 기준(잔고가 영역별로 안 나옴)"),
       E(cur_unit(main_cur)),
       roll_html, dup_html, len(s["ledger"]),
       ledger_table(s["ledger"], tid="lg%s" % s["stock"]),
       cur_html(s), seg_html, cust_html, parts_html, con_html,
       " ".join("<p>%s</p>" % n for n in notes),
       json_for_html(chart), CHART_DEFAULTS_JS, TABLE_JS)
    tags = (rec["stock"], rec["market"], ROLE_KO.get(rec["role"], rec["role"]), rec["industry"])
    dart = DART % ((latest or {}).get("rcp") or "")
    return page("%s — 우주항공 수주" % rec["name"], body, depth=1, h1=rec["name"], tags=tags,
                nav=(("허브", "../index.html"), ("인포그래픽", "../parts.html"),
                     ("커버리지", "../coverage.html"),
                     ("DART 원문 ↗", dart if latest else "https://dart.fss.or.kr")),
                crumbs=(("ARGUS", "../../index.html"), ("한국우주항공", "../index.html"),
                        (rec["name"], None)),
                scripts=("../vendor/chart.umd.min.js",),
                lead="수주잔고·부문매출·고객은 정기보고서 II-4에서 읽었습니다. 이 산업은 수주표의 "
                     "<b>통화가 표마다 다르고</b>(USD 표와 원화 표가 나뉩니다) 계약이 기종 단종까지 "
                     "가는 장기공급이라, 통화를 환산하지 않고 나란히 싣습니다.")


def cur_html(s):
    if not s["curs"]:
        return '<p class="mut">수주표에서 금액을 읽지 못했습니다.</p>'
    rows = "".join('<tr><td class="l">%s</td><td class="l">%s</td><td>%s</td></tr>'
                   % (E(c), E(CURRENCIES[c]["label"]), fmt_money_u(s["backlog"][c], c))
                   for c in s["curs"])
    usd = s["backlog"].get("USD")
    note = ""
    if usd:
        # 환율은 공시에 없다 — **민감도만** 적고 환산액 자체는 싣지 않는다(스펙 §화면 각주).
        note = ('<p class="mut" style="font-size:12px;margin-top:10px">원/달러가 <b>10원</b> 오르면 '
                'USD 잔고의 원화 환산액은 <b>%s억원</b>만큼 움직입니다(잔고 %s백만달러 × 10원 ÷ 1억). '
                '공시에 환율이 적혀 있지 않아 환산액 자체는 싣지 않습니다.</p>'
                % (fmt_n(round(usd * 1e6 * 10 / 1e8)), fmt_money(usd, "USD")))
    return ('<div class="wrap"><table><thead><tr><th class="l">통화</th><th class="l">표기</th>'
            '<th>수주잔고</th></tr></thead><tbody>%s</tbody></table></div>%s' % (rows, note))


def cat_ko(data, cid):
    for c in data["tax"]["cats"]:
        if c["id"] == cid:
            return c["ko"]
    return cid


# ── 허브 ───────────────────────────────────────────────────

# 카드 정렬용 어림값 — 백만달러를 백만원 몇 개로 볼 것인가. **정렬에만** 쓰고 화면
# 어디에도 환산 금액을 싣지 않는다. 공시에 환율이 없어 환산은 추정이기 때문이다(LOGIC §1).
# 이 값이 틀려도 순서만 조금 바뀔 뿐 어떤 숫자도 달라지지 않는다.
_SORT_FX = 1300.0


def _card_order(s):
    """허브 카드 순서 — 잔고가 큰 회사부터. 잔고가 없으면 계약 줄 수로 민다."""
    b = s["backlog"]
    mag = (b.get("KRW") or 0) + (b.get("USD") or 0) * _SORT_FX + (b.get("EUR") or 0) * _SORT_FX
    return (-mag, -len(s["ledger"]), s["stock"])


def hub_html(data, sums):
    have = [s for s in sums if s["curs"] or s["ledger"] or s["customers"]]
    tot = collections.defaultdict(float)
    for s in have:
        for c, v in s["backlog"].items():
            tot[c] += v or 0
    dom_amt = collections.defaultdict(lambda: collections.defaultdict(float))
    nat_amt = collections.defaultdict(lambda: collections.defaultdict(float))
    for s in have:
        for d, per in s["dom_amt"].items():
            for c, v in per.items():
                dom_amt[d][c] += v
        for n, per in s["nat_amt"].items():
            for c, v in per.items():
                nat_amt[n][c] += v
    cust_amt = collections.defaultdict(lambda: {"n": 0, "tier": None, "amt": collections.defaultdict(float)})
    for s in have:
        for c in s["customers"]:
            k = c["name"]
            cust_amt[k]["n"] += 1
            cust_amt[k]["tier"] = cust_amt[k]["tier"] or c.get("tier")
            for cur, v in (c.get("backlog") or {}).items():
                cust_amt[k]["amt"][cur] += v

    cards = []
    for s in sorted(sums, key=_card_order):
        if not has_page(s):
            continue
        rec = s["rec"]
        top = sorted(s["dom_amt"].items(),
                     key=lambda kv: -sum(kv[1].values()))[:3]
        chips = "".join(_chip(domain_label(d), domain_color(d)) for d, _ in top)
        if not chips:
            g = dom_guess(s)
            if g:
                chips = _chip(domain_label(g) + " (추정)", domain_color(g),
                              title="수주표·매출표에서 영역을 못 읽어 KIND 주요제품으로 추정")
        cust = " ".join(_chip(c["name"]) for c in s["customers"][:3])
        cards.append('<a class="cardlink" href="%s/index.html"><div class="t"><b>%s</b>'
                     '<span class="code">%s</span></div><p>%s</p>'
                     '<div class="chips" style="margin-top:8px">%s</div>'
                     '<div class="stat"><div><b>%s</b><span>수주잔고(%s)</span></div>'
                     '<div><b>%s</b><span>커버리지(년)</span></div>'
                     '<div><b>%s</b><span>수출비중</span></div>'
                     '<div><b>%d</b><span>계약 줄</span></div></div>'
                     '<div class="chips" style="margin-top:8px">%s</div>'
                     '<div class="go">회사 데이터 →</div></a>'
                     % (E(rec["stock"]), E(rec["name"]), E(rec["stock"]),
                        E((rec["product"] or "")[:70]), chips,
                        money_cell(s["backlog"]), E(s["latest_q"] or "—"),
                        fmt_x(s["coverage"]) if s["coverage"] else "—",
                        ("%.0f%%" % s["exp_share"]) if s["exp_share"] is not None else "—",
                        len(s["ledger"]), cust or '<span class="mut">고객 미확인</span>'))

    big = sorted([c for s in have for c in
                  [dict(x, stock=s["stock"]) for x in s["ledger"]]],
                 key=lambda c: -(c["closing"] or 0))[:30]
    names = {r["stock"]: r for r in data["uni"]}
    ncat = sum(1 for c in data["sup"].values() if c.get("cats"))
    nlink = sum(1 for c in data["sup"].values() if c.get("customers"))
    usd = tot.get("USD") or 0
    body = """
<div class="kpi">
 <div class="hero"><b>%s<small>억</small></b><span>원화 수주잔고 합 · %d사</span>
  <i class="mut">통화가 다른 잔고는 더하지 않습니다</i></div>
 <div><b>%s<small>백만$</small></b><span>USD 수주잔고 합</span>
  <i class="mut">원/달러 10원 → %s억원</i></div>
 <div><b>%d</b><span>모집단 종목(네 겹 전수)</span><i class="mut">부품 분류 %d · 고객 연결 %d</i></div>
 <div><b>%d</b><span>계약 줄(정기보고서 II-4)</span><i class="mut">수시공시 계약은 연 0.75건뿐입니다</i></div>
</div>
<h2 class="sec">회사<span>잔고 순 · 칩은 영역과 고객</span></h2>
<div class="cards">%s</div>
<div class="grid2">
 <section class="card"><h2>영역별 수주잔고 <em>원화 표 기준 · 억원</em></h2>
  <div class="chart"><canvas id="cDom"></canvas></div></section>
 <section class="card"><h2>계약 성격별 수주잔고 <em>원화 표 기준 · 억원</em></h2>
  <div class="chart"><canvas id="cNat"></canvas></div></section>
</div>
<section class="card"><h2>고객 <em>OEM·Tier-1·국내 체계업체 — 이 산업은 고객이 세계에 몇 곳뿐이라 실명으로 공시됩니다</em></h2>%s</section>
<section class="card"><h2>큰 계약 줄 <em>잔고 상위 30건 · 통화를 섞지 않고 각자 통화로 적습니다</em></h2>%s</section>
<h2 class="sec">더 보기<span>부품 인포그래픽과 모집단 근거</span></h2>
<div class="cards">
 <a class="cardlink" href="parts.html"><div class="t"><b>🛠 부품 인포그래픽</b></div>
  <p>여객기·터보팬 엔진·위성·발사체 그림에서 영역을 누르면 그 부품을 만드는 상장사로 갑니다.</p>
  <div class="go">인포그래픽 →</div></a>
 <a class="cardlink" href="coverage.html"><div class="t"><b>커버리지</b></div>
  <p>모집단 %d종목이 어떤 근거로 들어왔는지, 무엇을 <b>못 읽었는지</b>.</p>
  <div class="go">커버리지 →</div></a>
</div>
<div class="note info"><p>이 탭은 <b>통화를 환산하지 않습니다.</b> 아스트처럼 국외수주(USD)와
 국내수주(원) 표를 나눠 싣는 회사가 있고, 공시에 환율이 적혀 있지 않아 환산하면 추정이 되기 때문입니다.
 그래서 합계 KPI도 통화별로 따로 둡니다.</p>
 <p>한화에어로스페이스처럼 <b>겸업사</b>는 수주표 안에 해양(한국조선 탭)·방산(한국방산 탭) 부문이
 함께 들어 있습니다. 부문으로 갈라 이 탭에는 항공·우주만 실었고, 무엇이 어느 탭 몫으로 빠졌는지
 회사 페이지에 적었습니다.</p></div>
<script>const DATA=%s;</script>
<script>%s</script>
<script>
(function(){
 new Chart(document.getElementById('cDom'),{type:'bar',data:{labels:DATA.doms.map(function(d){return d.ko}),
  datasets:[{label:'억원',data:DATA.doms.map(function(d){return Math.round(d.amt/100)}),
   backgroundColor:DATA.doms.map(function(d){return d.color})}]},
  options:{indexAxis:'y',plugins:{legend:{display:false}},
   scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
 new Chart(document.getElementById('cNat'),{type:'bar',data:{labels:DATA.nats.map(function(d){return d.ko}),
  datasets:[{label:'억원',data:DATA.nats.map(function(d){return Math.round(d.amt/100)}),
   backgroundColor:DATA.nats.map(function(d){return d.color})}]},
  options:{plugins:{legend:{display:false}},
   scales:{y:{ticks:{callback:function(v){return v.toLocaleString()}}},x:{grid:{display:false}}}}});
})();
</script>
<script>%s</script>
""" % (fmt_money(tot.get("KRW"), "KRW"), len(have),
       fmt_money(usd, "USD"), fmt_n(round(usd * 1e6 * 10 / 1e8)),
       len(data["uni"]), ncat, nlink,
       sum(len(s["ledger"]) for s in have),
       "".join(cards),
       customers_table(cust_amt, data),
       ledger_table(big, tid="cbig", show_company=True, by_stock=names, rel=""),
       len(data["uni"]),
       json_for_html({
           "doms": [{"ko": domain_label(d["id"]), "color": domain_color(d["id"]),
                     "amt": dom_amt[d["id"]].get("KRW", 0)} for d in data["doms"]
                    if dom_amt.get(d["id"])],
           "nats": [{"ko": nature_ko(data, n["id"]), "color": nature_color(data, n["id"]),
                     "amt": nat_amt[n["id"]].get("KRW", 0)} for n in data["natures"]
                    if nat_amt.get(n["id"])]}),
       CHART_DEFAULTS_JS, TABLE_JS)
    return page("한국우주항공 — 수주·고객·부품", body, depth=0, h1="🚀 한국우주항공",
                scripts=("vendor/chart.umd.min.js",),
                nav=(("← ARGUS", "../index.html"), ("🏗 한국건설", "../kce/index.html"),
                     ("⚓ 한국조선", "../kship/index.html"), ("🛡 한국방산", "../kdef/index.html")),
                lead="국내 상장 우주항공 기업의 수주를 이 산업의 축으로 읽습니다 — "
                     "<b>통화</b>(USD 표와 원화 표가 나뉩니다), <b>영역</b>(민수 기체구조물·엔진/RSP·"
                     "MRO·방산 항공·우주), <b>계약 성격</b>(RSP·LTA·PBL·개발), 그리고 "
                     "<b>고객</b>(Boeing·Embraer·GE·P&amp;W가 공시에 실명으로 나옵니다). "
                     "체계업체뿐 아니라 부품사까지 전수로 담습니다.")


def customers_table(cust_amt, data):
    if not cust_amt:
        return '<p class="mut">공시에서 고객 이름을 읽지 못했습니다.</p>'
    rows = []
    for name, v in sorted(cust_amt.items(), key=lambda kv: (-sum(kv[1]["amt"].values()), kv[0])):
        rows.append('<tr><td class="l">%s</td><td class="l">%s</td><td>%d</td><td>%s</td></tr>'
                    % (E(name), E(tier_ko(data, v["tier"])), v["n"],
                       money_cell(dict(v["amt"])) if v["amt"] else "—"))
    return ('<div class="wrap"><table data-sortable><thead><tr><th class="l">고객</th>'
            '<th class="l">계층</th><th>거래 회사 수</th><th>연결된 수주잔고</th></tr></thead>'
            '<tbody>%s</tbody></table></div>' % "".join(rows))


# ── 커버리지 ───────────────────────────────────────────────

def coverage_html(data, sums):
    by = {s["stock"]: s for s in sums}
    rows = []
    for r in data["uni"]:
        s = by.get(r["stock"])
        st = r["stock"]
        bits = []
        if s and s["qs"]:
            bits.append("정기보고서 %d분기" % len(s["qs"]))
        if s and s["curs"]:
            bits.append("잔고 " + "·".join(s["curs"]))
        if s and s["ledger"]:
            bits.append("계약 줄 %d" % len(s["ledger"]))
        if s and s["customers"]:
            bits.append("고객 %d" % len(s["customers"]))
        if s and s["cats"]:
            bits.append("부품 %d" % len(s["cats"]))
        status = " · ".join(bits) or "원문에서 수치를 찾지 못함"
        cls = "up" if (s and s["curs"]) else ("wn" if bits else "mut")
        link = ('<a href="%s/index.html">%s</a>' % (E(st), E(r["name"]))
                if s and has_page(s) else E(r["name"]))
        rows.append('<tr><td class="l">%s</td><td class="mut">%s</td><td class="l">%s</td>'
                    '<td class="l mut">%s</td><td class="l"><b class="%s">%s</b></td>'
                    '<td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                    % (link, E(st), E(ROLE_KO.get(r["role"], r["role"])),
                       E((r["industry"] or "")[:22]), cls, E(status), E(r["source"]),
                       E((r.get("reason") or r.get("product") or "")[:80])))

    # 못 읽은 것 — fail-closed 로 버린 표를 그대로 보인다
    missed = []
    for s in sums:
        for q in s["qs"]:
            for n in (s["comp"]["quarters"][q].get("notes") or []):
                missed.append((s["rec"]["name"], q, n))
    miss_html = ""
    if missed:
        seen, tr = set(), []
        for nm, q, n in missed:
            if (nm, n) in seen:
                continue
            seen.add((nm, n))
            tr.append('<tr><td class="l">%s</td><td>%s</td><td class="l mut">%s</td></tr>'
                      % (E(nm), E(q), E(n)))
        miss_html = ('<section class="card"><h2>못 읽은 것 <em>단위·통화를 확인하지 못해 '
                     '금액으로 싣지 않은 표 — 조용히 넘기지 않습니다(COMMON §0-2)</em></h2>'
                     '<div class="wrap"><table data-sortable><thead><tr><th class="l">회사</th>'
                     '<th>분기</th><th class="l">이유</th></tr></thead><tbody>%s</tbody></table>'
                     '</div></section>' % "".join(tr))

    probe = data.get("probe") or {}
    rej = probe.get("rejected") or []
    scan = ""
    if probe:
        rj = "".join('<tr><td class="l">%s</td><td>%s</td><td class="l">%s</td><td>%d</td>'
                     '<td>%d</td><td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                     % (E(x["name"]), E(x["stock"]), E((x.get("industry") or "")[:20]),
                        x.get("hits", 0), x.get("struct", 0),
                        E(", ".join(list(x.get("oem") or {}))[:40]),
                        E((x.get("product") or "")[:44]))
                     for x in sorted(rej, key=lambda x: -x.get("hits", 0))[:60])
        fails = "".join('<tr><td class="l">%s</td><td>%s</td><td class="l mut">%s</td></tr>'
                        % (E(x["name"]), E(x["stock"]), E(x.get("note", "")))
                        for x in (probe.get("failed") or []))
        scan = ('<section class="card"><h2>④ 본문 탐색 <em>%s 정기보고서 · 후보 %d사 · 승격 %d · '
                '검토·제외 %d · 원문 못 읽음 %d</em></h2>'
                '<p style="font-size:12px;color:var(--tx2);line-height:1.8">기준: %s</p>'
                '<details><summary style="cursor:pointer;font-size:12px">검토·제외 상위 60사'
                '</summary><div class="wrap"><table data-sortable><thead><tr>'
                '<th class="l">회사</th><th>종목코드</th><th class="l">업종</th><th>항공·우주 낱말</th>'
                '<th>기체구조물 낱말</th><th class="l">OEM 언급</th><th class="l">주요제품</th>'
                '</tr></thead><tbody>%s</tbody></table></div></details>'
                '<details><summary style="cursor:pointer;font-size:12px">원문을 못 읽은 %d사'
                '</summary><div class="wrap"><table><thead><tr><th class="l">회사</th>'
                '<th>종목코드</th><th class="l">이유</th></tr></thead><tbody>%s</tbody></table>'
                '</div></details></section>'
                % (E(probe.get("quarter", "")), probe.get("n_cand", 0),
                   len(probe.get("promoted") or {}), len(rej), len(probe.get("failed") or []),
                   E(probe.get("rule", "")), rj, len(probe.get("failed") or []), fails))

    body = """
<section class="card" style="margin-top:0"><h2>모집단 규칙 <em>재현 가능한 네 겹 · 이름으로 넣지 않습니다</em></h2>
<p style="font-size:12px;color:var(--tx2);line-height:1.8">
① KIND 업종 <b>항공기·우주선 및 부품 제조업</b> 전 종목 ·
② KIND 주요제품 문구의 항공·우주 어휘(항공기·기체구조·동체·발사체·인공위성·탑재체·지상국…).
   <b>짧은 낱말은 쓰지 않습니다</b> — `위성` 하나면 위성방송·위성DMB 중계기가, `기체` 하나면
   <b>기체분리막</b>(기체=gas)이, `엔진부품` 하나면 자동차·선박 엔진부품사가 들어옵니다 ·
③ 사유를 적은 지정(스펙이 이름으로 든 8사) ·
④ 그래도 빠지는 회사를 <b>정기보고서 II-4 표의 부문·품목 이름</b>으로 찾습니다.
   문구 세기만 쓰면 반도체 회사의 "항공기 관련 LiDAR" 한 줄이 승격되고, 정작 대한항공은
   운송 낱말에 밀려 떨어집니다 — 표 근거를 1순위로 둔 이유입니다.
항공 <b>운송</b>(여객·화물)·여행업은 ② 경로에서 뺍니다. 다만 운송사 안에 제조 사업부가 있는
회사(대한항공 항공우주사업본부)는 ④가 표로 확인해 올립니다.
kdef·kship과 겹치는 회사는 빼지 않고 <b>부문 단위로 갈라</b> 싣고, 회사 페이지에 중복임을 적습니다.</p></section>
<section class="card"><h2>종목별 상태 <em>%d종목</em></h2><div class="wrap"><table data-sortable>
<thead><tr><th class="l">회사</th><th>종목코드</th><th class="l">역할</th><th class="l">업종</th>
<th class="l">수록 상태</th><th class="l">편입 근거</th><th class="l">사유·주요제품</th></tr></thead>
<tbody>%s</tbody></table></div></section>
%s
%s
<div class="note info">
<p><b>통화.</b> 수주표는 표마다 통화가 다릅니다(아스트 국외수주 USD · 국내수주 원). 환산하지 않고
 통화별로 싣습니다 — 공시에 환율이 적혀 있지 않아 환산하면 추정이 됩니다. 캡션에 통화가 둘 이상이거나
 (켄코아 <code>(단위 : USD, 천원)</code>) 행마다 <code>$</code>가 붙어 갈리지 않으면 금액으로 싣지 않습니다.</p>
<p><b>환헤지는 싣지 않습니다.</b> II-4 절 본문에서 <code>통화선도</code>·<code>환위험</code> 문구를
 찾지 못했습니다(그 문구는 III. 재무 주석에 있습니다). 확인하지 못한 것을 있는 것처럼 적지 않습니다.</p>
<p><b>수량은 싣지 않습니다.</b> 기체구조물 물량(shipset)은 수주표 수량 열이 <code>-</code> 이거나
 '상세내역 참조'로 갈음됩니다. 금액만 씁니다.</p>
<p><b>배수의 뜻.</b> 장기공급계약(LTA)은 기종이 단종될 때까지 자동 연장되는 관행이 있어
 프로그램 <b>누적 총액</b>이 잔고로 잡히는 회사가 있습니다. 커버리지가 10년을 넘으면 그렇게 읽으십시오.</p></div>
<script>%s</script>
""" % (len(data["uni"]), "".join(rows), miss_html, scan, TABLE_JS)
    return page("한국우주항공 커버리지", body, depth=0, h1="커버리지",
                nav=(("허브", "index.html"), ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국우주항공", "index.html"),
                        ("커버리지", None)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    data = load_all()
    want = set(a.only.split(",")) if a.only else None
    sums, made = [], 0
    for r in data["uni"]:
        s = summary(r["stock"], data)
        sums.append(s)
        if want and r["stock"] not in want:
            continue
        if not has_page(s):
            continue
        d = os.path.join(KAERO, r["stock"])
        os.makedirs(d, exist_ok=True)
        atomic_write(os.path.join(d, "index.html"), company_html(s, data))
        made += 1
    print("회사 페이지 %d개" % made)
    if a.all:
        atomic_write(os.path.join(KAERO, "index.html"), hub_html(data, sums))
        atomic_write(os.path.join(KAERO, "coverage.html"), coverage_html(data, sums))
        print("index.html · coverage.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
