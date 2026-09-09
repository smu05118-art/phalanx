#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_kce_link — argus/index.html에 한국건설 진입 링크를 재주입한다(멱등).

`argus/index.html`은 로컬 `argus_build.py`가 매일 재생성하는 산출물이라, 직접 넣은
링크가 크론 커밋에 덮여 사라진다(2026-09-04 `argus daily` 커밋에서 실제로 발생).
레포 규약이 권하는 방식대로 **Action이 매일 재주입**해 복구한다 —
`tools/inject_ui_patch.py`가 index.html의 ui-patch 훅을 재주입하는 것과 같은 발상이다.

근본 해결은 로컬 빌더 템플릿에 링크를 넣는 것이고, 그때는 이 스크립트가 no-op이 된다.

    python3 inject_kce_link.py            # 검사만 (있으면 0, 없으면 1)
    python3 inject_kce_link.py --apply
"""
import argparse
import os
import re
import sys

from kce_lib import atomic_write

HERE = os.path.dirname(os.path.abspath(__file__))          # argus/kce/tools
ARGUS = os.path.dirname(os.path.dirname(HERE))             # argus/
TARGET = os.path.join(ARGUS, "index.html")

LINK = ('<a href="kce/index.html" style="font-size:11px;font-weight:700;'
        'color:var(--accent);text-decoration:none;border:1px solid var(--accent);'
        'border-radius:999px;padding:3px 10px;white-space:nowrap">🏗 한국건설</a>')

# 링크를 넣을 자리: MOCK DATA 배지 뒤, 없으면 우측 고지문 앞.
_ANCHORS = (
    re.compile(r'(<span id="mockBadge">.*?</span>)', re.S),
    re.compile(r'(?=<span class="disc">)'),
)


def has_link(html):
    return 'href="kce/index.html"' in html


def inject(html):
    """링크를 넣은 HTML. 이미 있으면 그대로 돌려준다."""
    if has_link(html):
        return html, False
    m = _ANCHORS[0].search(html)
    if m:
        return html[:m.end(1)] + "\n  " + LINK + html[m.end(1):], True
    m = _ANCHORS[1].search(html)
    if m:
        return html[:m.start()] + LINK + "\n  " + html[m.start():], True
    raise RuntimeError("주입 위치를 찾지 못했다 — argus/index.html 구조가 바뀌었다")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--path", default=TARGET)
    a = ap.parse_args()
    with open(a.path, encoding="utf-8") as f:
        html = f.read()
    if has_link(html):
        print("한국건설 링크 있음 — 변경 없음")
        return 0
    out, changed = inject(html)
    if not a.apply:
        print("한국건설 링크 없음 — --apply 로 재주입 필요")
        return 1
    atomic_write(a.path, out)
    print("한국건설 링크 재주입 완료: %s" % a.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
