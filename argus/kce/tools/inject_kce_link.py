#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inject_kce_link — ARGUS ↔ 한국건설 **왕복** 진입 링크를 재주입한다(멱등).

두 방향 모두 생성물 위에 있어서 손으로 넣은 링크가 재생성에 덮인다.

  ① 내려가는 길  argus/index.html → kce/index.html
     `argus/index.html`은 로컬 `argus_build.py`가 매일 재생성하는 산출물이라, 직접 넣은
     링크가 크론 커밋에 덮여 사라진다(2026-09-04 `argus daily` 커밋에서 실제로 발생).

  ② 올라가는 길  argus/kce/index.html → argus/index.html
     한국건설 회사 선택 화면에는 ARGUS로 돌아가는 링크가 아예 없어 **편도 진입**이었다
     (2026-09-10 내비 감사). 이 화면은 `kce_page.py`가 `tools/assets/picker_base.html`
     원형에서 매번 새로 만든다 — 그래서 링크의 단일소스는 그 원형이고, 여기서는
     원형이 어떤 이유로 링크를 잃었을 때를 대비해 같은 블록을 다시 넣는다.
     Action은 `kce_page.py --all` **다음에** 이 스크립트를 돌리므로 순서가 맞다.

레포 규약이 권하는 방식대로 **Action이 매일 재주입**해 복구한다 —
`tools/inject_ui_patch.py`가 index.html의 ui-patch 훅을 재주입하는 것과 같은 발상이다.

근본 해결은 각 생성기 템플릿에 링크를 넣는 것이고, 그때는 이 스크립트가 no-op이 된다.

    python3 inject_kce_link.py            # 검사만 (둘 다 있으면 0, 하나라도 없으면 1)
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
KCE_TARGET = os.path.join(ARGUS, "kce", "index.html")

LINK = ('<a href="kce/index.html" style="font-size:11px;font-weight:700;'
        'color:var(--accent);text-decoration:none;border:1px solid var(--accent);'
        'border-radius:999px;padding:3px 10px;white-space:nowrap">🏗 한국건설</a>')

# 링크를 넣을 자리: MOCK DATA 배지 뒤, 없으면 우측 고지문 앞.
_ANCHORS = (
    re.compile(r'(<span id="mockBadge">.*?</span>)', re.S),
    re.compile(r'(?=<span class="disc">)'),
)

# ② 올라가는 길. `picker_base.html`에 들어 있는 것과 **바이트가 같아야** 한다 —
# 다르면 kce_page.py 재생성분과 이 주입분이 매일 서로를 되쓰며 커밋 노이즈를 만든다.
BACKLINK = (
    '\n<!-- 이 화면은 argus/index.html 헤더의 「🏗 한국건설」로만 들어오는데 돌아가는 길이\n'
    '     없어 편도였다(2026-09-10 내비 감사). coverage.html 머리줄의 ARGUS 버튼과 같은\n'
    '     대상을 가리킨다. 클래스 없이 인라인 스타일로 쓴다 — kce_page.picker_html이\n'
    '     이 파일을 글자 그대로 복사해 index.html을 만들기 때문에 스타일 블록 위치에\n'
    '     의존하지 않는 편이 안전하다. -->\n'
    '<div style="width:100%;max-width:940px;margin:0 0 22px;font-size:12px">'
    '<a href="../index.html" style="color:var(--tx2);text-decoration:none">← ARGUS</a></div>')

_BODY = re.compile(r'<body[^>]*>')


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


def has_backlink(html):
    # 회사 선택 화면의 다른 링크는 전부 아래로 내려가는 상대경로(`sct/index.html`,
    # `coverage.html`)라 `../index.html`은 이 되돌아가는 링크에만 쓰인다.
    return 'href="../index.html"' in html


def inject_backlink(html):
    """ARGUS로 돌아가는 링크를 <body> 바로 뒤에 넣은 HTML."""
    if has_backlink(html):
        return html, False
    m = _BODY.search(html)
    if not m:
        raise RuntimeError("주입 위치를 찾지 못했다 — argus/kce/index.html에 <body>가 없다")
    out = html[:m.end()] + BACKLINK + html[m.end():]
    # fail-closed: 회사 카드를 하나라도 잃었으면 쓰지 않는다.
    if out.count('<a class="card"') != html.count('<a class="card"'):
        raise RuntimeError("주입 중 회사 카드가 변했다 — 쓰지 않는다")
    return out, True


def _one(path, checker, injector, name, apply_):
    """한 파일을 검사(·주입)한다. 링크가 이미 있으면 True, 없으면 False를 준다."""
    with open(path, encoding="utf-8") as f:
        html = f.read()
    if checker(html):
        print("%s 링크 있음 — 변경 없음: %s" % (name, path))
        return True
    out, changed = injector(html)
    if not apply_:
        print("%s 링크 없음 — --apply 로 재주입 필요: %s" % (name, path))
        return False
    atomic_write(path, out)
    print("%s 링크 재주입 완료: %s" % (name, path))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--path", default=TARGET, help="argus/index.html 경로 재정의")
    ap.add_argument("--kce-path", default=KCE_TARGET,
                    help="argus/kce/index.html 경로 재정의")
    a = ap.parse_args()
    ok = _one(a.path, has_link, inject, "한국건설", a.apply)
    # 한쪽이 실패해도 다른 쪽은 손본다 — 왕복 중 한 방향만 끊긴 상태를 남기지 않는다.
    ok = _one(a.kce_path, has_backlink, inject_backlink, "ARGUS", a.apply) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
