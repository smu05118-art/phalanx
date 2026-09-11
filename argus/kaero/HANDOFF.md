# 한국우주항공 (KAERO) — 인수인계

## ① 무엇이 어디서 오는가

| 산출 | 만드는 것 | 원천 | 캐시 |
|---|---|---|---|
| `tools/assets/universe.json` | `kaero_universe.py --write` | KRX KIND 상장법인목록 + `universe_probe.json` | — |
| `tools/assets/universe_probe.json` | `kaero_scan.py --scan` | 정기보고서 II절 본문·II-4 표 | — |
| `tools/assets/reports.json` | `kaero_reports.py --collect/--build` | 정기보고서 「II-4 매출 및 수주상황」 + 「XII 상세표 4. 수주상황(상세)」 | `assets/reports_cache/<종목>/<분기>.json` (비커밋) |
| `tools/assets/contracts.json` | `kaero_contracts.py --collect/--build` | 수시공시 「단일판매ㆍ공급계약체결」(I001) | `assets/contracts/<종목>/<rcpNo>.json` |
| `tools/assets/suppliers.json` | `kaero_suppliers.py --build` | 위 셋 + `parts_taxonomy.json` (수집 없음) | — |
| `tools/assets/{domains,natures,tiers,parts_taxonomy,svg_regions}.json` | `build_dicts.py --write` | 코드 안의 표(교차참조 검증) | — |
| `index.html` `coverage.html` `<종목>/index.html` | `kaero_page.py --all` | 위 전부 | — |
| `parts.html` | `kaero_parts.py` | `parts_taxonomy` + `svg_regions` + `suppliers` | — |

수집 층(DART 무키 3단 경로·요청 게이트·EUC-KR 판정·표 파싱·KIND)은 `argus/kce/tools` 를,
차트/표 JS는 `argus/kship/tools/kship_lib.py` 를 **import** 한다. 복사본이 없다.

## ② 지금 상태 (2026-09-11)

- 모집단 **20종목** — 업종 11 · 제품 7 · 탐색 2(대한항공 003490 · 아이쓰리시스템 214430).
  ③ 지정 8사는 전부 ① 업종 안에 있어 사유만 남겼다.
- 정기보고서 **6분기**(2025Q1~2026Q2) · 분기레코드 **109건**(실패 0). 회사 페이지 **20쪽**.
- 계약 줄(정기보고서 II-4) **107건** · 수시공시 계약 **237건**.
- 통화별 잔고: 원화 **54.6조** · **USD 2,728백만달러**(17사). 합산 KPI는 없다.
- 부품 분류된 회사 16 · 고객 연결 17.
- 겸업사 부문 필터: 한화에어로 공시 수주표 114.9조 → 항공 **32.3조**,
  해양 33.0조(kship)·방산 46.8조(kdef)·IT 2.8조는 뺐다(커버리지 페이지에 표로 있다).
  KAI 도 25.8조 중 국내방산 10.2조가 kdef 몫으로 빠져 **15.5조**만 실린다.
- 커버리지의 분모는 **분자와 같은 범위**다 — 겸업사는 부문 매출로 나누고 화면에 `추정`을 단다
  (한화에어로 12.5년 · KAI 15.7년). 대한항공은 부문 매출을 못 읽어 만들지 않았다.
- 테스트 **50건** 통과. 픽스처는 DART 원문 절(`tools/tests/fixtures/*.json`).

### 못 읽은 것 (화면에도 그대로 적혀 있다)

- **켄코아에어로스페이스(274090)** — 매출실적 캡션이 `(단위 : USD, 천원)` 이고 행마다
  `$` 로 통화가 갈린다. 금액을 만들지 않고 행 이름만 남겼다.
- **케이피항공산업(288180)·컨텍(451760)·비츠로넥스텍(488900)** — 수주표가 없다.
  매출처 표·부문 매출만 실린다.
- **환헤지** — II-4 절 본문에서 `통화선도`·`환위험` 문구를 찾지 못했다(III. 재무 주석에 있다).
  scout 표본 8사 플래그도 `fx: 0%` 였다. 환 축은 **표 단위 통화**로만 세웠다.
- **수량(shipset)** — 수주표 수량 열이 전부 `-` 이거나 '상세내역 참조'다. 금액만 쓴다.

## ③ 남은 일

1. **공용 층 2건은 고치지 않고 보고만 했다**(감독 메모 2 — 공용 파일은 읽기만).
   근거는 `tools/FINDINGS.md` §8 에 있다:
   ① `kce_fetch.pick_report` 가 `[첨부정정] 사업보고서` 를 1순위로 준다(II절이 없는 문서다).
   ② 표 복구 3함수(`_headered`·`_two_row_header`·`_carry_units`)가 kdef 와 두 벌이다 —
     `kce_parse` 가 제 집이고, kaero 가 보탠 **제목 물림**도 함께 가야 한다.
2. **`kaero_scan.py --scan` 은 자동 갱신에서 기본으로 돌지 않는다**(후보 74사, 느리다).
   `workflow_dispatch` 의 `scan: yes` 로 분기마다 한 번 돌리면 된다.
3. **영역이 `기타·미상`인 잔고**가 남아 있다(한화에어로 항공 부문의 `상세내역 참조` 행 등).
   「II-2 주요 제품 및 서비스」 절을 따로 수집해 제품 문구로 더 가를 수 있다.
4. **고객 약칭**(`ACM`·`BTC`·`SAMC`)은 각주가 풀어 주는 회사만 이름을 붙였다.
   각주 표(`(주1) …는 …입니다`)를 파싱하면 등급 B로 더 붙일 수 있다.
5. 계약 원장의 `납기` 칸이 `400대` 처럼 수량인 건이 있다 — 지금은 기간을 만들지 않는다.
   인도 스케줄(선표에 해당)을 만들려면 이 칸의 방언을 더 모아야 한다.
6. **대한항공 커버리지**를 못 만든다. 매출표가 `1. 항공운송사업 / 2. 항공우주사업` 아래
   `총매출액·연결조정액·순매출액` 세 줄로 내려가는 모양이라 부문 행을 못 잡는다.
   그 표를 따로 읽으면 분모가 생긴다(지금은 만들지 않고 이유를 화면에 적는다).
7. **KAI 커버리지 15.7년은 범위가 살짝 어긋난다.** 분자(수주표 kaero)에는 완제기 수출이
   들어 있고 분모(매출표 kaero)는 `기체부품 및 민수`뿐이다 — 그래서 `추정`을 달았다.
   수주표 부문 이름과 매출표 부문 이름을 잇는 사전을 만들면 정확해진다.

## ④ 재현 명령

```sh
cd argus/kaero/tools
python3 build_dicts.py --write
python3 kaero_scan.py --scan                      # ④ 탐색(느리다 · 후보 74사)
python3 kaero_universe.py --write
python3 kaero_contracts.py --collect && python3 kaero_contracts.py --build
python3 kaero_reports.py --collect --n 6 && python3 kaero_reports.py --build --n 6
python3 kaero_suppliers.py --build
python3 kaero_page.py --all && python3 kaero_parts.py
python3 -m unittest discover -s tests
```

원문을 눈으로 볼 때:

```sh
python3 ../../_specs/scout_tools/scout_peek.py 067390 --quarter 2025Q4 --sec "매출 및 수주"
```

`--force` 는 파싱 결과를 버리고 다시 읽는다(DART 를 다시 두드린다 — 20사 6분기 약 25분).
파서를 고쳤을 때만 쓴다. 원문 캐시 `assets/reports_cache/` 는 커밋하지 않는다.
