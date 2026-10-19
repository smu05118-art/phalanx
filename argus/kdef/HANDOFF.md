# 한국방산 (KDEF) — 인수인계

## ① 무엇이 어디서 오는가

| 화면 값 | 원천 | 코드 |
|---|---|---|
| 수주잔고·기초·기납품·수주총액 | 정기보고서 II-4 수주상황 (5갈래 표) | `kdef_reports.parse_orders_table` → `assets/reports_cache/<종목>/<분기>.json` |
| 잔고 커버리지(년) | 잔고 ÷ **직전 사업연도** 매출 열 | `kdef_reports._fy_revenue` / `_fy_segsales` |
| 방산비중·수출비중 | II-4 매출실적 / 사업부문별 매출 | `parse_revenue_table` · `parse_segment_sales` · `seg_kind` |
| 주요 거래처(부품사 연결의 최상급 근거) | II-4 「주요 매출처」 | `parse_customers` |
| 계약(사업명·계통·유형·금액·기간·상대) | 수시공시 I001 「단일판매ㆍ공급계약체결」 | `kdef_contracts` → `assets/contracts/<종목>/<rcp>.json` → `contracts.json` |
| 계통·계약유형·부품 소분류·SVG 영역 | 코드에서 생성하는 사전 | `build_dicts.py` → `assets/{domains,contract_types,parts_taxonomy,svg_regions}.json` |
| 제품 서술(부품 분류 근거) | 정기보고서 II-2 「주요 제품 및 서비스」 | `kdef_products.py` → `assets/products/<종목>.json` |
| 부품 분류·납품 관계(근거 등급) | 위 사전 + 계약명 + 제품 절 + II절 인용문 + KIND 문구 | `kdef_suppliers.py` → `assets/suppliers.json` |
| 모집단 네 겹 | KIND 상장법인목록 + ④ 본문 탐색 | `kdef_universe.py` · `kdef_scan.py` → `universe.json` · `universe_probe.json` |
| 계약별 진행(공급·수령 누적) | 반기·사업보고서 XI-1 「나. 단일판매ㆍ공급계약 진행 현황」 | 공용 `kce/tools/xi1_sector.py kdef` → `assets/xi1/progress.json` · 화면 `kce/tools/xi1_view.py` |
| 페이지 | 위 JSON만 읽는다(수집 없음) | `kdef_page.py`(허브·회사·커버리지) · `kdef_parts.py`(인포그래픽) |

## ② 지금 상태 (2026-09-11)

- 모집단 **71종목**(체계 7 · 부품 57 · 소재 5 · 용역 2). 출처: 업종 14 · 제품문구 18 · 지정 12 · ④탐색 27.
- 정기보고서 **71사 수집**(체계업체 8분기, 나머지 최근 2분기) · 분기레코드 219.
  잔고 실측: 한화에어로 114.9조 · 한화오션 33.0조 · KAI 25.8조 · LIG 24.6조 · 현대로템 12.8조 ·
  한화시스템 11.3조 · 풍산 1.8조. 커버리지 1.5~7.1년.
- 계약 공시 **699건 전수**(방산 551건·88조 / 민수 148건은 CIVIL 로 갈라 집계에서 제외).
  최대 계약: 폴란드 K2전차 2차 8.98조(현대로템) · KF-X 체계개발 7.92조(KAI) · 폴란드 FA-50 4.21조.
- 제품 절 71사 수집 · 부품 분류 58사 · 체계업체 연결 38사(주요고객 13 · 계약공시 55 · 본문 언급 5).
- 페이지: 허브·커버리지·인포그래픽 + 회사 70쪽. 테스트 **23건** 통과.
- **고친 공용 버그**: `kce_fetch._decode` — 코스닥 거래소공시(rcpNo 9번째 자리 `9`)가 EUC-KR인데
  UTF-8로 읽혀 계약공시 366건이 깨진 글자로 캐시됐다. 선언 charset → rcpNo 규칙 → UTF-8 엄격 순으로
  판정하게 고치고 깨진 캐시를 다시 받았다. **다른 탭(kce·kship)도 이 수정의 수혜자다.**
- **고친 금액 오독**: 정정공시의 뭉쳐 온 행(값에 숫자 3개)이 금액으로 읽혀 868억 계약이
  8.7×10^24 원이 됐다. `_find` 의 공백 처리와 숫자 토큰 수 검사로 막았다(테스트 있음).

## ③ 남은 일

- (2026-10 디테일화로 처리) 계통 축에 **우주(SPACE)** 를 신설하고(발사체·위성체·누리호·KSLV; 색 슬롯 9 =
  `kdef.css --s9` = `kdef_orders_views.DOMAINS`, 세 벌 일치를 테스트가 지킨다), `군위성`을 유도무기에서
  C4I 로 옮기고, 민수 어휘(민항기 프로그램·철도 신호·은행 IT·선박 엔진·제조장비)를 늘리되 `TICN용`·`해군`·
  국방 조달기관 상대면 되짚는다. 그래도 남는 미상은 **부품 이름이 있으면 '부품(계통 미상)'** 으로 따로 센다.
  실측(2026-10-13, 해지 포함 방산 기준): 계통 미상 198건 17.1조 → 75건(부품명만 34) 7.4조, 방산 559건 88.8조 → 469건 81.6조.
- (처리) **수출은 판로**로 따로 판정한다 — 상대(G2G·해외기업·해외 익명) ∨ 공급지역 해외(국내 화이트리스트에
  안 걸릴 때만) ∨ 체계업체 상대 + 계약명 '수출'(간접수출). 107건 31.5조 → 107건 36.1조(해지 제외; 직 77·간접 30).
  유형 낱말 없는 G2G·`수출사업/이행계약/실행계약` 은 계약유형 **수출사업 이행(EXPORT_EXEC)**(17건 26.6조). 유형 미상 160건 13.5조.
- (처리) 허브 「계약유형 × 계약상대」 매트릭스 · 수주 상세 「종료연도별 인도 일정」(유형·상대 분해) ·
  회사 「II-4 납기 일정」(품목 행 납기 열, 끝 연도) · 「수량 축」(raw_tables 의 수량·중량 열, 캡션 단위) ·
  해지 공시 pill(건수·금액 집계 제외). 전부 기존 캐시만 읽는다(추가 수집 0).
- 계약명이 `-` 인 10건은 **공시유보**로 표시했다(사유·기한 표기). 원본 계약명을 물려받게 하는 방법도 있다.
- 남은 계통 미상 41건(부품명 없음)은 `방산수출 이행약정`(KOTRA, 1.73조)·`MC, MFD, ACCS, IRST`(약어만)·
  `OOOO 시스템`(익명) 같은 것들이라 사전으로는 풀리지 않는다.
- 한화에어로스페이스 발주 `MCS Plant 구축 공사`(한화오션 4,245억)·`MCS Plant 지능화 물류 시스템 구축`
  (한화시스템 967억)은 **민수로 단정하지 않고 계통 미상(방산 집계 안)에 둔다** — 공시에 용도가 없고 방산
  생산설비일 수 있다(`kdef_contracts._CIVIL_HOLD`). 사람 판정 큐(hdrmap 큐) 후보. 판정이 나면 _CIVIL_HOLD 한 줄.
- 판정 회귀 게이트: `tools/tests/fixtures/contracts_sample.json`(실데이터 60행 — 이름·상대·지역 → 계통·유형·상대·수출
  기대값). 사전·판정을 고치면 이 픽스처가 먼저 깨진다 — 기대값을 바꾸면 `why` 도 함께 고친다. 2026-10-12 판정 교정:
  G2G 는 EXPORT_EXEC 를 SUPPLY 앞에(폴란드 FA-50 4.21조) · PRIME 상대는 EXPORT_EXEC 금지(T-50 엔진 등 4건 → 유형 미상,
  판로는 간접수출 pill) · `정부`는 이름 끝에서만 G2G(국내 `정부○○`는 GOV) · KARI≠KAI(12건 PRIME→GOV) · LIG D&A·한화디펜스
  별칭(10건 → PRIME) · 국내 법인의 괄호 영문 병기는 FOREIGN 이 아님(현대위아·기아·HD현대중공업·SK오션플랜트·강남 7건,
  직수출에서 빠짐). 허브 실측: 방산 461→463건(MCS Plant 2건이 미상으로 편입) · 수출 112→108건 · EXPORT_EXEC 20→17건.
- (처리 2026-10-13) '진행중'을 가르는 기준일은 실행 날짜가 아니라 **원장 최신 공시 접수일**(`kdef_page.ledger_asof`,
  rcpNo 앞 8자리)이다 — 데이터가 같은 날 페이지 diff 가 생기지 않는다. 간트 기준선 라벨도 '기준일'.
- (처리 2026-10-13) 법인 접미 없이 괄호에만 영문을 병기한 한글 상대(`현대중공업 (HYUNDAI HEAVY…)`·`한국철도공사(KORAIL)`)는
  공급지역이 국내면 DOMESTIC(`_ko_paren_domestic`). `호주 정부`=G2G(`주 정부` 지방정부 규칙 제외)·`중앙정부`=국내·
  대문자 `GOVERNMENT OF …`=G2G. 해외 체계업체(L&T·HSW) 상대 '수출사업' 부품 계약은 이름대로 EXPORT_EXEC 로 둔다 —
  상대가 해외라 판로·유형 모두 수출 이행으로 읽힌다(국내 체계업체 상대만 금지).
- 수량 표의 금액·수량 단위가 캡션 하나에 함께 온다(`M/T, 백만원`·포메탈 `EA / 백만원`·`수량-EA/금액-백만원`).
  토큰 분리는 `,`·`·` 기준이고 `/`는 한쪽이 금액 단위일 때만 가른다(`M/T`는 한 단위) —
  `(단위 : 백만원, 개)` 꼴에서 수량 열이 금액으로 집계되는 kdef_reports 쪽 위험(`_UNIT_QTY` seen=False
  조건)은 그대로다. 병합 머리행 `수주잔고 수량금액`(대양전기공업 2025Q1)은 수량 열로 읽지 않는다.
- 인포그래픽의 영역별 관련도(계통 선택 시 농도)는 kship 처럼 `rel` 표를 만들면 더 읽힌다 — 지금은
  '상장사가 있는 영역'만 강조한다.

## ④ 재현 명령

```sh
cd argus/kdef/tools
python3 build_dicts.py --write
python3 kdef_universe.py --write                    # ④ 탐색 결과(universe_probe.json)를 합친다
python3 kdef_scan.py --scan                         # 모집단 ④ 재탐색(무겁다, 주 1회면 충분)
python3 kdef_contracts.py --collect && python3 kdef_contracts.py --build
PRIMES=$(python3 -c "import json;print(','.join(r['stock'] for r in json.load(open('assets/universe.json'))['rows'] if r['role']=='prime'))")
python3 kdef_reports.py --collect --n 8 --only "$PRIMES"
python3 kdef_reports.py --build --n 8
python3 kdef_products.py --collect
python3 kdef_suppliers.py --build
python3 kdef_page.py --all && python3 kdef_parts.py
python3 -m unittest discover -s tests
```

파서를 고친 뒤에는 `--force` 로 **필요한 회사만** 다시 받는다(DART는 IP 단위로 막는다).
원문 표는 `reports_cache` 에 `cols·rows·lead` 그대로 남아 있어 대부분은 재수집 없이 `--build` 만으로 된다.

## 2026-09-18 원장 19분기 · Y+2 추정

- 원장을 **2021Q4~2026Q2 19분기**로 확장했다(이전 6~8분기). 재현: `python3 tools/kdef_reports.py --collect --quarter 2026Q2 --n 19`
  → `--build` → `tools/kdef_page.py --all`. (조선은 `kship_yards.py --collect --quarter <분기>` 를 분기마다.)
- 스튜디오 Codex(gpt-6-astra/ultra)가 만든 **Y+2 추정**(분기 T+1~T+10 · 연간 FY2026~FY2028)이 있으면
  `tools/assets/forecast_panel.json.gz` + `tools/kdef_forecast_section.py` 로 회사 페이지에 실린다.
  산출이 없거나 회사가 빠지면 **섹션을 만들지 않는다**. 렌더러 파일명에 탭 접두가 붙은 이유는 그 파일 머리에 적었다.
- 추정에는 시나리오 3종·잔고분/신규분 분해·민감도 구간이 붙고 `calibrated=false` 로 표기된다 —
  통계적 신뢰구간이 아니며, 회계 매출이 아니라 수주원장 기준 대용치다.

## 2026-10-19 계약 진행(XI-1)

- 공용 층(`argus/kce/tools/xi1_sector.py` 수집·해석·원장 연결·지표, `xi1_view.py` 화면 조각 — **여기서 고치지 않는다**)을 붙였다.
  데이터 `tools/assets/xi1/{status.json, parsed/<종목>/<분기>.json, progress.json}`(원문 HTML `_raw/` 는 커밋하지 않음).
  정의·임계는 `argus/kce/UPDATE.md` §6-C, 이 탭의 규칙은 LOGIC §7.
- 붙인 자리(`kdef_page.py`): `load_all()["xi1"] = load_xi1(모집단)` · `contracts_table` 의 '진행(XI-1)' 열(금액 바로 뒤, 회사 표와
  허브 '최근 대형 계약' 둘 다, rcp + `supersedes` 사슬로 찾음) · 회사 페이지 계약 공시 표 바로 아래 `xi1_company`(id `xi1`) ·
  허브 '최근 대형 계약' 아래 `xi1_hub`(회사 페이지가 있는 종목만 링크) · 커버리지 `xi1_coverage`(id `xi1cov`) · 내비 `#xi1` ·
  꼬리말 원천(`kdef_lib.page(foot=)`). 조각 CSS 는 그 페이지 `<style>` 로 한 번.
- **fail-soft**: import·읽기 실패, `progress.json` 없음 → `data["xi1"]=None` → 열·섹션·꼬리말 없이 **지금과 같은 바이트**
  (`tests/test_xi1_pages.py` 가 지킨다). 렌더 중 예외도 그 조각만 뺀다. 모집단 밖 종목이 섞이면 `xi1_sector.subset` 으로 맞춘다.
- 민수: XI-1 절은 회사의 XI-1 계약 전부라 CIVIL 을 빼지 않는다 — 섹션 첫 줄에 원장으로 확인한 민수 건수와 XI 전용(미판정) 건수.
- 워크플로: `kdef_reports.py --build` 뒤·`kdef_headers.py --write` 앞에 `python3 ../../kce/tools/xi1_sector.py kdef --collect --build`
  (실패해도 경고만 — 직전 progress.json 으로 페이지를 만든다). 커밋 메시지·Step Summary 에 `XI-1 n건(확정·추정·지연)`.
  build 가 머리행 지도에 role `xi` 를 남기므로 `kdef_headers --check` 의 회귀 게이트가 xi 표에도 걸린다(직전 반기에 읽히던
  XI 표가 미지로 바뀌면 빨강).
- 로컬 재현(DART 0): `cd tools && python3 ../../kce/tools/xi1_sector.py kdef --build --no-hdr && python3 kdef_page.py --all`.
  `--collect` 는 로컬에서 돌리지 않는다(DART IP 차단). 실측 2026Q2: 회사 72 중 표 있음 35 · 계약 625(최신 501) ·
  연결 확정 357/추정 31 · XI 전용 237 · 지연 의심 33. 회사 섹션 35쪽, 원장 표 진행 칸 714(값 있음 244).
