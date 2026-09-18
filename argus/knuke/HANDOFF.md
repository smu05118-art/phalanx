# KNUKE 인수인계

## ① 무엇이 어디서 오는가

| 화면 값 | 원천 | 파일 |
|---|---|---|
| 수주잔고·롤포워드·표 모양 | 정기보고서 II-4 매출·수주상황 | `knuke_reports.py` → `reports.json` |
| 발주처·사업명·계약기간(호기 타임라인·발주처 집중도) | II-4 도급형 수주표(award) | `knuke_reports.parse_orders_table` |
| 발전원별 잔고 구성 | award 표 계약잔액을 발전원으로 묶음 | `reports.build` `dom_backlog` |
| 부문 매출(발전원 × 내수/수출)·연매출 | II-4 매출실적 | `knuke_reports.parse_revenue_table`/`parse_segment_sales` |
| 잔고 커버리지 | 잔고 ÷ 연매출(직전 사업연도 열) | `knuke_page.summary` |
| 사업 단위 계약(발주처·발전원·계층·금액·기간) | 수시공시 「단일판매ㆍ공급계약체결」 I001 | `knuke_contracts.py` → `contracts.json` |
| 모집단 편입 근거 | KIND 업종·제품 · 지정 · II절 본문 탐색 | `knuke_universe.py`·`knuke_scan.py` |
| 부품·대형사 연결 | 계약명·본문·KIND 문구 낱말(근거 등급) | `knuke_suppliers.py` → `suppliers.json` |

## ② 지금 상태

**한 바퀴 다 돌았다.** 수집·빌드·페이지·테스트·`site.json` 까지.

- 사전 발전원 5 · 공급계층 9(EPC 포함) · 부품 소분류 18 · 실루엣 2/영역 16, 교차검증 통과.
- 모집단 **25종목**(①KIND 7 + ②지정 8 + ③본문 탐색 승격 10). 제외 57사도 근거와 함께 커버리지에 있다.
- 계약 공시 **317건**(2020~, 0건 2사 포함) · 정기보고서 **193 분기레코드**(25사 × 8분기).
- 허브 수주잔고 합 38.5조 · 회사 25쪽 · 호기 타임라인 66행 · 발주처 실명 40곳.
- 표 모양 다섯 갈래가 실제로 나온다 — award(한전기술·한전KPS·오르비텍·KC코트렐·금양그린파워) ·
  roll(두산에너빌리티) · item · gross · balance.
- 원문 대조: 한전기술 2026Q2(rcp 20260814001293) `(단위 : 억원)` 18행 도급형 —
  신한울3,4 종합설계 2016-03-18~2033-10-31 계약잔액 2,205억, 합계 6,936억이 화면 값과 같다.
- 테스트 14건 통과. `python3 -m unittest discover -s tests`.

## ③ 남은 일 / 알아둘 것

1. DART 는 IP 단위로 30~60분 끊는다(COMMON §2). 수집이 막히면 시간을 두고 다시 돌린다 —
   캐시가 있으면 빠진 것만 받는다. `knuke_scan.py` 는 II절을 못 읽은 회사는 승격하지 않는다(fail-closed).
2. 수주표 도급형(award)은 5사뿐이다. 나머지는 부문 합계·잔액 한 줄이라 호기 타임라인·발주처
   집중도가 비고, 화면에 그 사실을 적는다.
3. **외화 수주표는 금액을 싣지 않는다.** 이성씨엔아이 수주표가 `(단위: 천달러)`다 —
   환율을 쓰지 않으므로 억원 칸을 비우고 이유를 적는다. 커버리지 분모도 같은 기준.
4. 분류 미상으로 남은 계약은 대체로 **발전이 아닌 계약**이다(STX엔진의 함정 소나·전차 엔진,
   오르비텍의 항공 부품, 강원에너지의 양극재 설비). 추정해 채우지 않는다.
   연료를 알 수 없는 `… Independent Power Project` 류도 발전원을 비워 둔다.
5. SMR 은 별도 축이 아니라 계약명 태그(`smr=True`)로만 남긴다(스펙 §왜수주기반 5).
6. 다음에 넓힐 곳 — ⓐ 정기보고서 「II-2 주요 제품」 절을 따로 수집해 부품 분류를 넓히기,
   ⓑ award 표가 없는 회사의 발주처를 계약 공시 상대에서 역으로 채우기,
   ⓒ 계약 공시 `kv` 에 남겨 둔 「판매ㆍ공급지역」으로 수출 지역 축 만들기.

## ④ 재현 명령

```sh
cd argus/knuke/tools
python3 build_dicts.py --write
python3 knuke_scan.py --scan
python3 knuke_universe.py --write
python3 knuke_contracts.py --collect && python3 knuke_contracts.py --build
python3 knuke_reports.py --collect --n 8 && python3 knuke_reports.py --build
python3 knuke_suppliers.py --build && python3 knuke_page.py --all && python3 knuke_parts.py
python3 -m unittest discover -s tests
```

자동 갱신은 `.github/workflows/update-knuke.yml`(일 1회 11:40 KST, `concurrency: kship-dart`).
