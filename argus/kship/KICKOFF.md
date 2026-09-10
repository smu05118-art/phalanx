# 한국조선 — 남은 과정 착수 지시서 (맥미니 / 맥스튜디오용)

2026-09-10 21:50 KST 기준. 코드·캐시·페이지·문서는 전부 `main`에 있다(`git pull` 한 번이면 같은 상태).
남은 일은 **DART 재수집 → 빌드 → 페이지 재생성 → 커밋**뿐이다. 아래 순서와 제약을 지키면 어느 머신에서 해도 같다.

## 제약 하나 — DART는 공인 IP 하나당 프로세스 하나

DART(dart.fss.or.kr)는 같은 공인 IP에서 프로세스 2~3개가 동시에 두드리면 연결을 끊고(HTTP 000·RemoteDisconnected)
30~60분 차단한다. 맥북에어가 쓰던 IP(180.228.166.44)는 9/10 저녁 내내 차단 상태였다.
그러므로 **병렬은 "공인 IP가 다른 머신끼리"만** 된다. 같은 공유기 뒤의 맥미니·맥스튜디오는 공인 IP가 같으니
둘이 동시에 수집하면 둘 다 막힌다 — 한 대만 수집하고, 다른 한 대는 수집이 아닌 일(검증·페이지·문서)을 맡긴다.
시작 전에 `curl -s https://api.ipify.org` 로 IP를 확인하고, `curl -s -o /dev/null -w "%{http_code}\n" -X POST
https://dart.fss.or.kr/dsab007/detailSearch.ax -d "textCrpNm=009540&currentPage=1&maxResults=1&publicType=I001"`
가 200이어야 수집을 시작한다(000이면 차단 중 — 기다린다).

## 수집 레인 (한 IP에서는 A → B → C 순서로 하나씩, IP가 다르면 A·B·C 동시)

```bash
cd argus/kship/tools

# A. 척당 계약 공시 — 정정공시 23건 재수집(EUC-KR 판정 수정 후 캐시를 지웠다)
python3 kship_contracts.py --collect && python3 kship_contracts.py --build

# B. 기자재 35사 — 5사 미수집 + 비중→금액 오독 캐시 교정(--force 한 번에 둘 다)
python3 kship_suppliers.py --collect --force && python3 kship_suppliers.py --build

# C. 조선사 정기보고서 — 삼성重 헤지 확정(--force) 뒤 과거 분기를 최신부터 하나씩
python3 kship_yards.py --collect --quarter 2026Q2 --only 010140 --force
for q in 2026Q1 2025Q4 2025Q3 2025Q2 2025Q1 2024Q4 2024Q3; do python3 kship_yards.py --collect --quarter $q; done
```

각 스크립트는 요청 간격 0.7초·재시도 5회를 내장하고, 일시 실패는 캐시하지 않는다(다시 돌리면 빠진 것만 받는다).
중간에 000이 연속으로 나오면 즉시 멈추고 30분 뒤 같은 명령을 다시 — 억지로 계속하면 차단이 길어진다.

## 수집 뒤 (수집 IP와 무관 — 아무 머신)

```bash
cd argus/kship/tools
python3 -m unittest discover -s tests          # 12건 전부 OK 여야 한다
python3 build_dicts.py                          # 사전 교차참조(실패하면 페이지를 만들지 않는다)
python3 kship_page.py --all && python3 kship_parts.py --all
python3 inject_link.py --apply                  # argus/index.html 에 ⚓ 진입 링크(크론이 지우면 재주입)
cd ../../.. && git add -A -- argus/kship argus/index.html && git commit -m "kship: 재수집 반영" && git pull --rebase origin main && git push origin main
```

## 확인할 것 (수집이 끝난 뒤 사람이 또는 검증 에이전트가)

1. **삼성중공업 통화선도 USD 매도 명목액** — `assets/yards_cache/010140/2026Q2.json` 의 `hedge.items[*].col`(열 머리)을 본다.
   482억달러(전기 열 합산 의심)가 아니라 당기 열만의 합(약 250억달러 안팎으로 추정)이어야 하고, 그래도 잔고(원화 35조)와
   견줘 말이 되는지 적는다. 다르면 `kship_yards.py parse_hedge_any` 의 note-label 분기에서 열 선택 규칙을 고친다.
2. `assets/contracts.json` — 정정공시 23건이 `supersedes` 로 원본을 덮었는지, 선종 `null` 이 0건인지.
3. `assets/suppliers.json` — 한국카본 등 `share` 가 0~100 범위인지, 35사 전부 `confirmed`/캐시 여부.
4. 조선사 5사 × 8분기 롤포워드가 연속인지(기말 = 다음 분기 기초 ± 신규증감의 환율효과), 화면의 누적 막대가 그것을 보여 주는지.
5. 대한조선·HJ중공업의 헤지 공시가 실제로 없는지(주석에 '파생' 표가 없으면 화면에 '공시 없음'으로 남긴다).
6. 라이브: https://smu05118-art.github.io/phalanx/argus/kship/index.html 과 ⚓ 진입 링크(https://smu05118-art.github.io/phalanx/argus/index.html).

## 맥스튜디오 클로드에 그대로 붙여 넣을 프롬프트

```
/Users/…/phalanx 레포에서 git pull 뒤 argus/kship/KICKOFF.md 를 읽고 그 순서대로 남은 과정을 끝내 줘.
규칙: DART 수집은 이 머신에서 프로세스 하나만(레인 A→B→C 순서로 하나씩). 수집이 아닌 일(테스트·사전·페이지·문서·검증 6항목)은
에이전트를 최대한 병렬로 띄워도 된다. 수집이 끝날 때마다 빌드→페이지 재생성→커밋→push 하고, 마지막에 KICKOFF '확인할 것' 6항목을
검증 에이전트들로 병렬 점검해서 결과를 HANDOFF.md '지금 상태'에 적고 push 해 줘. API 키는 필요 없고, 받아서도 안 된다.
```

문서: [HANDOFF.md](HANDOFF.md)(현황·원천 표) · [LOGIC.md](LOGIC.md)(판정 규칙) · [README.md](README.md)(화면).
