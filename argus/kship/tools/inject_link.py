#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_link — ARGUS ↔ 한국조선 왕복 진입 링크를 재주입한다(멱등).

`argus/index.html`은 로컬 `argus_build.py`가 매일 재생성하는 산출물이라 손으로 넣은 링크가
크론 커밋에 덮인다(한국건설 탭에서 실제로 반복 발생 — argus/kce/tools/inject_kce_link.py).
같은 발상으로 Action이 매일 재주입한다. 한국건설 링크 **바로 뒤**에 붙여 탭 순서가 고정되게 한다.

    python3 inject_link.py            # 검사만 (둘 다 있으면 0)
    python3 inject_link.py --apply
"""
import argparse
import os
import re
import sys

from kship_lib import ARGUS, KSHIP, atomic_write

TARGET = os.path.join(ARGUS, "index.html")
BACK_TARGET = os.path.join(KSHIP, "index.html")

LINK = ('<a href="kship/index.html" style="font-size:11px;font-weight:700;'
        'color:var(--accent);text-decoration:none;border:1px solid var(--accent);'
        'border-radius:999px;padding:3px 10px;white-space:nowrap">⚓ 한국조선</a>')

# 붙일 자리: 한국건설 링크 뒤 → MOCK DATA 배지 뒤 → 우측 고지문 앞
_ANCHORS = (
    re.compile(r'(<a href="kce/index.html"[^>]*>[^<]*</a>)'),
    re.compile(r'(<span id="mockBadge">.*?</span>)', re.S),
    re.compile(r'(?=<span class="disc">)'),
)
_BODY = re.compile(r'<body[^>]*>')


def has_link(html):
    return 'href="kship/index.html"' in html


def inject(html):
    if has_link(html):
        return html, False
    for i, pat in enumerate(_ANCHORS):
        m = pat.search(html)
        if not m:
            continue
        if i < 2:
            return html[:m.end(1)] + "\n  " + LINK + html[m.end(1):], True
        return html[:m.start()] + LINK + "\n  " + html[m.start():], True
    raise RuntimeError("argus/index.html에서 링크를 넣을 자리를 찾지 못했다 — 템플릿이 바뀌었다")


def has_backlink(html):
    return 'href="../index.html"' in html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ok = True
    with open(TARGET, encoding="utf-8") as f:
        html = f.read()
    out, changed = inject(html)
    if changed:
        ok = False
        if a.apply:
            atomic_write(TARGET, out)
            print("한국조선 진입 링크 재주입: %s" % TARGET)
        else:
            print("진입 링크 없음: %s" % TARGET)
    else:
        print("진입 링크 있음 — 변경 없음: %s" % TARGET)
    if os.path.exists(BACK_TARGET):
        with open(BACK_TARGET, encoding="utf-8") as f:
            if not has_backlink(f.read()):
                ok = False
                print("ARGUS 복귀 링크 없음: %s (생성기 템플릿을 확인하라)" % BACK_TARGET)
    return 0 if (ok or a.apply) else 1


if __name__ == "__main__":
    sys.exit(main())
