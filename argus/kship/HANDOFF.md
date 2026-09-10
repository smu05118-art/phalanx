# 한국조선(argus/kship) — 인수인계 (2026-09-10)

다른 머신(맥미니)에서 이어가기 위한 상태 기록. 코드·데이터·페이지는 전부 `main`에 있다.
`git pull` 뒤 아래 순서로 돌리면 같은 화면이 나온다(파이썬 3.9+ 표준 라이브러리만).

```bash
cd argus/kship/tools
python3 kship_universe.py --write          # KIND → 모집단 41종목 (조선사 5·지주 1·엔진 4·기자재 29·강재 2)
python3 kship_contracts.py --collect       # 척당 계약 공시 캐시(assets/contracts/) — 있는 건 건너뜀
python3 kship_contracts.py --build         # → assets/contracts.json
python3 kship_yards.py --collect           # 조선사 정기보고서 최신 분기(롤포워드·매출·환노출·헤지)
python3 kship_suppliers.py --collect       # 기자재사 정기보고서 II 절(제품·조선사 언급)
python3 kship_suppliers.py --build         # → assets/suppliers.json (+ unclassified.csv)
python3 build_dicts.py                     # 부품 분류 54·SVG 영역 35 재생성(교차참조 검증)
python3 kship_page.py --all                # 허브·커버리지·조선사 5장
python3 kship_parts.py --all               # parts.html 인포그래픽 + 기자재사 35장
python3 inject_link.py --apply             # argus/index.html 에 ⚓ 한국조선 진입 링크(크론이 지우면 재주입)
```

로컬 미리보기: 레포 루트에서 `python3 -m http.server 8902` → `http://localhost:8902/argus/kship/index.html`.

## 무엇이 어디서 오는가 (실측으로 확정)

| 축 | 원천 | 비고 |
|---|---|---|
| 수주잔고·신규·기납품(부문) | 정기보고서 II-4 수주상황 — **부문 롤포워드**(원화, 삼성重 억원) | 선종·척수 없음. 신규증감에 환율효과 포함 |
| 선종·척수·인도시점·상대·지역·대금조건 | 수시공시 「단일판매ㆍ공급계약체결」 | 상대 81% 익명('○○ 소재 선사'). 종료일=마지막 호선 인도 |
| 매출실적(부문×수출/내수) | 정기보고서 II-4 | |
| 환노출(통화별 자산·부채, 계약자산) | II-5 위험관리 및 파생거래 | HD현대重·대한조선만 표 형식 |
| 통화선도 명목액·평균만기·건수 | 주석 「파생금융상품」 또는 II-5 | 3사 3형식(주석 라벨형/4열 쌍/USD매도 행) 모두 파싱 |
| 반복건조(시리즈) | **추정** — 같은 선종·상대 표기·지역, 수주일 180일 이내 | 화면에 '추정' 표시 |
| 기자재 부품 분류 | 정기보고서 II-2 주요제품 + KIND 문구 → 키워드 규칙 | 미분류는 `assets/unclassified.csv`, 수동 지정은 `parts_override.csv` |
| 기자재→조선사 연결 | II 절 본문의 조선사 이름 언급(횟수), 비중은 적힌 경우만 | 근거 등급을 화면에 표시(주요고객 주석 > 계약 공시 > 본문 언급 > KIND) |

## 지금 상태 (2026-09-10 저녁)

- 페이지: 허브 · 커버리지 · 조선사 5 · 기자재 35 · parts.html 인포그래픽(375px 점검 완료). ARGUS 진입 링크 주입됨.
- 문서: README.md(화면) · LOGIC.md(판정 규칙) · 이 문서. 테스트 12건 `cd tools && python3 -m unittest discover -s tests`.
- 자동 갱신: `.github/workflows/update-kship.yml` 매일 10:40 KST — 수집기 하나씩, 테스트 전후, 성공분만 커밋.
- 조선사 5사 **2026Q2만** 수집됨. 과거 분기는 DART 차단으로 미수집 — 복구되면
  `python3 kship_yards.py --collect --quarter 2026Q1`(… 2025Q4 … 2024Q3) **하나씩**.
- 척당 계약 189건(2024~) 집계. **정정공시 23건은 인코딩 버그로 캐시를 지웠다** — `kship_contracts.py --collect`가 다시 받는다(EUC-KR 판정 수정됨). 선종 미판정 12건은 `contracts.json`에서 `type=null`로 남아 있다(추정하지 않음).
- 기자재 35사 중 30사 캐시. 5사 미수집(범한퓨얼셀·현대힘스·케이앤에스아이앤씨·한국선재·화인베스틸)과 **비중→금액 오독 캐시**(한국카본 등)는 `kship_suppliers.py --collect --force` 한 번이면 둘 다 해결 → `--build`.
- 삼성중공업 통화선도 매도 USD 482억달러는 주석 표 그대로 — 잔고(원화 35조≈240억달러)보다 커서 **원문 대조 필요**(롤오버 누적일 수 있음).
- 남은 일: 위 재수집 후 `kship_page.py --all` · `kship_parts.py --all` · 커밋. 대한조선·HJ중공업 헤지 공시 확인. 진행률(매출인식) 기준을 주석 「수익」에서 읽기. 인포그래픽에서 관련도 0인 소분류 흐리게.

## DART 주의

DART는 병렬 프로세스 2~3개가 동시에 두드리면 IP 단위로 연결을 끊는다(RemoteDisconnected, 30~60분).
수집기는 **하나씩** 돌려라. kce_fetch 가 요청 간격 0.7초·재시도 5회를 내장한다.
