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

- 사전(발전원 5·공급계층 8·부품 소분류 18·실루엣 2/영역 16) 생성·교차검증 통과.
- 모집단: ①KIND 7 + ②지정 8 = 15사 확정, ③ 본문 탐색 승격분이 더해진다.
- 파이프라인 코드 일습(계약·정기보고서·공급망·허브/회사/커버리지/인포그래픽) 작성 완료.
- DART 수집(`--collect`)과 최종 페이지 생성 후 테스트·site.json 공개는 재현 명령대로.

## ③ 남은 일 / 알아둘 것

1. DART 는 IP 단위로 30~60분 끊는다(COMMON §2). 수집이 막히면 시간을 두고 다시 돌린다 —
   캐시가 있으면 빠진 것만 받는다. `knuke_scan.py` 는 II절을 못 읽은 회사는 승격하지 않는다(fail-closed).
2. 수주표 도급형(award)은 한전기술·한전KPS·오르비텍에 있다. 다른 회사는 부문 합계·잔액 한 줄일 수 있고,
   그때는 호기 타임라인·발주처 집중도가 비고 그 사실을 화면에 적는다.
3. SMR 은 별도 축이 아니라 계약명 태그(`smr=True`)로만 남긴다(스펙 §왜수주기반 5).
4. 부품 분류 정밀화 — 정기보고서 「II-2 주요 제품」 절을 따로 수집해 제품 문구로 분류하면 더 넓어진다.

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
