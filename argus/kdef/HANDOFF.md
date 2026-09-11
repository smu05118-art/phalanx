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
| 페이지 | 위 JSON만 읽는다(수집 없음) | `kdef_page.py`(허브·회사·커버리지) · `kdef_parts.py`(인포그래픽) |

## ② 지금 상태 (2026-09-11)

- 모집단 **71종목**(체계 7 · 부품 57 · 소재 5 · 용역 2). 출처: 업종 14 · 제품문구 18 · 지정 12 · ④탐색 27.
- 정기보고서 **71사 수집**(체계업체 8분기, 나머지 최근 2분기) · 분기레코드 219.
  잔고 실측: 한화에어로 114.9조 · 한화오션 33.0조 · KAI 25.8조 · LIG 24.6조 · 현대로템 12.8조 ·
  한화시스템 11.3조 · 풍산 1.8조. 커버리지 1.5~7.1년.
- 계약 공시 **352건**(민수 100건은 CIVIL 로 갈라 집계에서 제외) — 계통 미상 56건(16%).
- 부품 분류 42사 · 체계업체 연결 20사(주요고객 13 · 계약공시 22 · 본문 언급 10 — 회사당 중복 포함).
- 페이지: 허브·커버리지·인포그래픽 + 회사 70쪽. 테스트 21건 통과.
- **고친 공용 버그**: `kce_fetch._decode` — 코스닥 거래소공시(rcpNo 9번째 자리 `9`)가 EUC-KR인데
  UTF-8로 읽혀 계약공시 366건이 깨진 글자로 캐시됐다. 선언 charset → rcpNo 규칙 → UTF-8 엄격 순으로
  판정하게 고치고 깨진 캐시를 다시 받았다. **다른 탭(kce·kship)도 이 수정의 수혜자다.**

## ③ 남은 일

- 계통 '미상' 56건 중 10건은 **계약명이 빈칸/'-'** 인 정정공시다 — 정정 대상 원본의 계약명을 물려받게
  하면 줄어든다(`supersedes` 관계를 역방향으로 쓰면 된다).
- 부품 분류의 근거가 `본문 인용문` 하나뿐인 회사는 오탐이 남는다(마음AI '동체', 나인테크 '이차전지').
  정기보고서 「II-2 주요 제품」 절을 따로 받아 제품 문구로 분류하면 정밀해진다(`SECTIONS` 에 이미 정의만 있음).
- 풍산·한화에어로처럼 **수량 단위 표**를 함께 공시하는 회사는 수량 축(발주량 M/T)을 따로 보여 줄 수 있다.
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
