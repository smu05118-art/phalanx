#!/usr/bin/env python3
"""index.html에 ui/ 패치 레이어 훅을 주입한다 (멱등·원자적·fail-closed).

크론이 index.html을 재생성하면 훅이 사라지므로, GitHub Action
(.github/workflows/ui-patch-inject.yml)이 push마다 이 스크립트로 재주입한다.
빌더(jem_site_build.py) 템플릿에 HEAD_BLOCK/BODY_BLOCK을 직접 넣으면
이 스크립트와 Action은 은퇴시켜도 된다. 문서: ui/README.md
"""
import os
import sys

MARK = "ui-patch:v1"
HEAD_BLOCK = (
    "<!-- ui-patch:v1 head (자동 주입 — tools/inject_ui_patch.py, ui/README.md 참고) -->\n"
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">\n'
    '<link rel="stylesheet" href="ui/patch.css">\n'
)
BODY_BLOCK = (
    "<!-- ui-patch:v1 body -->\n"
    '<script src="ui/patch.js"></script>\n'
)


def main(path: str) -> int:
    with open(path, encoding="utf-8", newline="") as f:  # 개행 무변환 — 훅 3줄 외 diff 방지
        html = f.read()

    if MARK in html:
        print("ui-patch: 이미 주입됨 — 변경 없음")
        return 0

    if html.count("</head>") != 1 or html.count("</body>") != 1:
        print("ui-patch: </head>/</body> 앵커가 정확히 1개가 아님 — 주입 중단(fail-closed)", file=sys.stderr)
        return 1

    html = html.replace("</head>", HEAD_BLOCK + "</head>", 1)
    html = html.replace("</body>", BODY_BLOCK + "</body>", 1)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(html)
    os.replace(tmp, path)
    print("ui-patch: 주입 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "index.html"))
