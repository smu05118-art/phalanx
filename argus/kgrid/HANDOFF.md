# KGRID 인수인계

## ① 무엇이 어디서 오는가

| 화면의 값 | 원천(DART) | 파서 | fail-closed |
|---|---|---|---|
| 수주잔고 · 기초 · 신규 · 기납품 | 정기보고서 II-4「수주상황」 | `kgrid_reports.parse_orders_table` (roll·gross·item·balance) | 단위 캡션 미확인 또는 수량 단위면 **금액으로 안 싣는다** |
| 잔고 통화 | 같은 표의 `(단위 : …)` 캡션 | `kship_parse.unit_of`(공용) | 통화 못 읽으면 `unit_seen=false` |
| 커버리지(년) | 잔고 ÷ **직전 사업연도** 매출 | `kgrid_lib.coverage` | **통화가 다르면 만들지 않는다**(일진전기) |
| 잔고 성격(장납기/회전) | 배수 1.0년 | `kgrid_lib.backlog_kind` | 배수 없으면 `미상`(추정 금지) |
| 내수/수출, 부문 매출 | II-4「매출실적」 | `parse_revenue_table` | 수량·비중·외화 열은 값에서 뺀다 |
| 제품군별 매출 | II-4「주요 제품군별 매출실적」 | `parse_segment_sales` | 판매경로·판매전략 표는 거른다 |
| 지역별 매출 | II-4「지역별 매출 현황」 | `parse_region_table` | 일진전기 등 일부 회사만 공시한다 |
| 주요 매출처·비중 | II-4「주요매출처」 | `parse_customers` + 근거 등급 | 실명/익명/고객분류/관계회사를 배지로 가른다 |
| 관계회사 판정 | **같은 보고서의 종속회사 목록**(수주표 라벨·매출실적 구분 열) | `_related_names` | 이름만으로 잇지 않는다 |
| 계약명·상대·금액·기간 | 수시공시「단일판매ㆍ공급계약체결」(I001) | `kgrid_contracts` | 공시유보는 유보로, 해지는 해지로 표시 |
| 계약금액 원화 환산 | **공시가 적은 환율**(`fx_src` 에 문구 보존) | `kgrid_contracts` | 근거 없으면 원문 통화로 둔다 |
| 수요 축(데이터센터·북미·HVDC…) | II절 본문 | `demand_quotes` | 표 덤프는 인용하지 않는다 |
| 모집단·편입 근거 | KRX KIND 업종·주요제품 + II절 본문 | `kgrid_universe` · `kgrid_scan` | 승격은 본문 인용이 있을 때만 |

원문 캐시: `tools/assets/reports_cache/<종목>/<분기>.json` 의 `raw_tables` 에 표의
`cols`·`rows`·`lead` 가 그대로 있다. 파서를 고치면 **`--reparse`** 로 DART 재요청 없이 다시 뽑는다.

## ② 지금 상태

- 모집단 **32종목** — 업종 13 · 지정 15 · 제품 1 · 지주 3(집계에서 제외).
- 정기보고서 **32사 × 6분기 = 189 레코드, 실패 0**. 수주잔고를 공시하는 회사 **20사**.
- 배수 중앙값 **0.71년**, **장납기 8사 : 회전 10사** — 스펙의 이분 가설이 전수로 확인됐다.
- 외화로 잔고를 공시하는 회사 1사(일진전기 `천USD`) — 환산하지 않고 배수를 비웠다.
- 계약 공시 원장 수록(회사 페이지·허브 수요처/지역 집계).
- 페이지 35장(허브·단선도·커버리지 + 회사 32). 테스트 **97건 통과**.
- 탭 공개: `site.json` `{"label": "⚡ 한국전력기기", "order": 60}`.
- 자동 갱신: `.github/workflows/update-kgrid.yml` (11:40 KST, `concurrency: kship-dart`).

### 스펙과 달랐던 것 (원문이 이긴다)

1. 스펙은 엘에스일렉트릭 수주표가 `사업본부|품목|수주일자|납기` 3열이라 했지만 **2026Q2에는 12열
   롤포워드**다 — 신규수주까지 읽는다.
2. 스펙 §6은 "HVDC는 원문에서 확인 못 함"이라 했지만 **2026Q2 본문에는 나온다** —
   엘에스일렉트릭·일진전기가 서해안·동해안 HVDC를 이름까지 적었다. 축으로 세우고 인용했다.
3. 스펙 §3의 회사별 배수(제룡전기 0.67 등)와 우리 값이 다르다 — 우리는 **직전 사업연도** 매출을
   분모로 쓰고 주체를 맞춘다(정찰은 표에 있는 값을 그대로 썼다). 화면에 분모 열 이름을 적는다.
4. `산일전기` 종목코드는 **062040**이다(스펙 본문에 코드가 없어 KIND로 확인했다).

## ③ 남은 일

`tools/PROGRESS.md` 의 「남은 일」과 같다. 요약하면:

1. 제품군 분류 정밀화 — II-2「주요 제품 및 서비스」 절을 따로 수집한다.
2. `변압기(전압 계급 미상)` 줄이기 — II-2 본문에 `초고압`·`345kV` 가 있으면 `ehv` 로 올린다.
3. 수주표가 없는 7사를 계약 공시로 보완할 수 있는지 확인.
4. 매출처 표의 종속회사 귀속(엘에스일렉트릭 11장 표에 대괄호 라벨이 없다).

## ④ 재현 명령

```sh
cd argus/kgrid/tools
python3 kgrid_dicts.py --write
python3 kgrid_universe.py --write
python3 kgrid_scan.py --probe && python3 kgrid_scan.py --build
python3 kgrid_contracts.py --collect && python3 kgrid_contracts.py --build
python3 kgrid_reports.py --collect --n 6
python3 kgrid_reports.py --reparse --build --n 6     # 파서를 고쳤을 때: DART 요청 0건
python3 kgrid_page.py --all
python3 -m unittest discover -s tests                # 97건
```

한 회사만 보려면 `--only 267260`. 원문을 눈으로 보려면
`python3 ../../_specs/scout_tools/scout_peek.py 267260 --quarter 2026Q2 --sec "매출 및 수주상황"`.

**주의**: DART는 공인 IP 단위로 막는다(30~60분). 수집기는 동시에 3개를 넘기지 마라 —
`kce_fetch` 가 파일 락으로 프로세스 간 요청 간격(0.7초)을 묶지만 캐시 경합은 피해야 한다.
`--force` 대량 재수집은 파서를 고친 뒤 꼭 필요한 범위만(대개 `--reparse` 로 충분하다).
