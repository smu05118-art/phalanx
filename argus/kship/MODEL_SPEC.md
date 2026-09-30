# 한국조선(kship) 실적 모델 시스템 — 설계 계약 (2026-09-30)

사용자 요청 세 가지를 한 체계로 푼다.
① 세진중공업(075580)·삼성중공업(010140)·HD현대미포(010620) — 사용자가 준 애널리스트 subQ 모델 3개를 **레퍼런스**로 같은 구조의 모델을 만든다.
② 그 세 파일에 **박힌 데이터(BS연결/BS별도 FnGuide 계정, 환율, 종가)를 2026Q2까지 최신화**하고, ARGUS 조선 탭의 데이터(수주·선표·헤지·재무)가 모델에 흘러들도록 조직한다.
③ 나머지 조선사·기자재·엔진·강재 **56사 전부**에 같은 모델링 시스템을 만들어 회사 페이지에 임베딩한다.

레퍼런스 원본은 사용자 사유 파일이라 **공개 레포에 넣지 않는다** — `~/phalanx/jem_data/kship_models/reference/` (맥미니 로컬)에만 둔다.
우리가 생성한 모델(xlsx·json·html)은 DART 공개 자료 + 우리 추정이므로 레포(`argus/kship/`)에 실린다.

---

## 0. 레퍼런스 모델 해부 (세 파일 공통 골격 — 실측)

| 시트 | 역할 | 우리 대응 |
|---|---|---|
| `변수` | 가정 시계열. 행 5~14 환율(원/달러 평균·기말, 원/100엔, 원/유로, 원/위안), 수주시점 환율, 후판 가격(원/톤·$/톤), 하우스 환율 | `assets/fx.json` + 모델 `assumptions` |
| `BS연결` `BS별도` (`BS일승(별도)` `BS동방선기(별도)` — 세진) | **FnGuide DataGuide 계정 덤프** (`A110000.IC 자산총계` … 188계정, **백만원**). 헤더: 행1 `1Q05…2031`(분기+연간), 행4 `2005.03 … 2023.09`·`2005.12A`(연간), 행3 `UPDATE: 24-01-07`. 이것이 "박힌 것" | `kship_fin.py` → `assets/fin/<stock>.json`; 패치는 `kship_xlsx_patch.py` |
| `subQ` | 분기 서브모델(억원, `U=100`=백만원→억원). 열 E~ED = 2005Q1…2030(분기 4개 뒤 연간 1열). 모든 확정치는 `VLOOKUP($D행, BS연결/BS별도, MATCH(SUBQH, BS연결H,0),0)/U` 로 BS 시트에서 끌어오고, 추정치는 사업부 빌드업(`매출조선`·`OP조선`… 이름정의)으로 만든다. 아래 0-1 | `kship_model.py` |
| `SLS` (미포·삼성중) | 클락슨식 **선표 피벗**(백만$): ①미래/확정 × Yard × 선종(Type_UU) × 연·분기 인도 매출, `← 당겨옴 / 다음해로 미룸 →` 조정, 매출$ → **환헤지 환율**(헤지환율·건조시점환율·HEDGE 70%·open 30%·적용환율) → 원화 매출, ②호황/불황 **수주업황 코호트**(①적자 ②BEP ③중마진 ④호황 ⑤초호황)별 매출 비중 → 타겟 OPM(`SLSOPM조선연결`), ③선종별 | `kship_sls.py` → `assets/sls/<stock>.json` (계약공시 원장 기반) |
| `분기` / `연간예상` / `보고서로` / `INPUT→` | subQ 를 보고서 표 형태로 요약(VLOOKUP by 이름) | 모델 json `views` + 섹션 렌더 |
| `TP_PE PB` / `TP_EBITDA` / `TP_BPS` / `RIM` | 밸류에이션: PER 밴드 × EPS, PBR=ROE/COE × BPS, EV/EBITDA, RIM | 모델 `valuation` (배 표기·추천 아님) |
| `외화` / `→답` | 외화 자산·부채 × 환율 QoQ → 외화환산손익·외환차손 추정, 회귀(환절편+환기울기) | 모델 `fx_pnl` |
| 회사 특유 | 세진: `풍력e`(프로젝트별 MW·Floater ASP), `LNG-Fuel수주이력`·`연료탱커ASP`·`TypeC탱커`, `토지 캐파`, `기타사업`, `연간예상` 의 **weighted 현중+미포 매출 → 세진 조선기자재 매출** 비례식. 미포: `도크`(4도크·안벽), `지분법`(비나신 등), `한조모델로→`(지주 모델로 넘기는 표). 삼성중: `드릴쉽`(리세일·소송), `수주목표.평`, `일회성` | 모델 `modules[]` (있는 회사만) |

### 0-1. subQ 의 계산 사슬 (세진 파일 행 번호)
- 매출: `매출조선`(r446 `=확매출블럭`) + `매출풍력`(r517) → 별도 매출 → 연결 매출(r13/r15, 종속사 일승 r771·동방선기 r778 을 BS일승/BS동방선기에서 VLOOKUP, `연결/별도 ↕` 비율 r437)
- 원가/GP/판관/OP: 사업부별 `원가조선 = 매출조선 − GP조선`, `GP조선 = OP조선 + 판관조선 − 기타영업이익`, `판관조선 = 매출조선 × /SALES`, `OP조선 = 매출조선 × 타겟OPM`, 타겟OPM = `OPM추` + ⓐ모델오차 + ⓑ알려진 일회성(r492~496). 재료비/노무비/외주가공비/기타경비 = 원가 × 비중(r455~462)
- 영업외: 이자손익(이자율 × 평균 이자발생자산/총차입금, r201~208), 환관련손익(`외화답`, r110), 외환거래 3합(①외환차손 ②외화환산 ③기타영업외 환, r215~254), 파생상품(r259), 지분법(r275~279)
- 세전(r281) → 법인세율(r291) → 당기순이익(r306) → 지배주주(r314) → 주식수(r323~326) → EPS(r329) → PER 4종(종가 기말/고/저/평균, r330~333, r392~395) → BPS(r374/376) → DPS·배당성향(r382~385) → EBITDA(r296)
- 채권/채무 회전(r404~422), 감가상각률·CAPEX(r851~857)
- 미포·삼성중 추가: `건조량(CGT)`·`/CGT` 원가(노무·재료·후판·장비·기타경비 ÷ 건조량, 미포 r451~489), `매출미포달러 = 매출/헤지환율`(r898), `알잔액전체`(IR 수주잔량 백만$) → `헤지비율`(r869), `SLSOPM` 타겟 + ②미지 일회성 + ③알려진 일회성(공손충) + ④환율 영향(r512~541), 삼성중 `공사손실충당부채`(r92)·`SLS해양비중`(r556)·`신규수주(추)/수주잔액(추)` 롤(r577~583)

### 0-2. 모델이 참조하는 FnGuide 계정명 (형식 VLOOKUP($D, BS연결…) 전집 73 — 이 이름으로 우리 fin 을 맞춘다)
```
(지배주주지분)당기순이익 CAPEX 감가상각비 건설중인자산 계속사업이익 금융비용 금융손익 금융수익 기말발행주식수(백만주) 기말자기주식수(백만주)
기타영업비용 기타영업손익 기타영업수익 기타영업외비용 기타영업외수익 기타유형자산 기타자본 기타포괄이익누계액 당기순이익 매입채무및기타채무
매출액(수익) 매출원가 매출채권및기타채권 매출채권의감소및매입채무의증가 매출총이익 배당금손익 배당금수익 법인세비용 법인세비용차감전계속사업이익
보통주시가총액(기말/최고/최저/평균, 십억원) 부채총계 비지배주주지분 사채 선급금 선수금 설비자산 수정DPS(보통주, 기말현금) 수정기말발행주식수 순차입금
영업이익 외화환산손실 외화환산이익 외환거래손실_기타 외환거래이익_기타 외환차손 외환차익 유동부채 유동자산 이연법인세자산 이익잉여금 이자발생자산
이자비용 이자손익 이자수익 자본금 자본잉여금 자본총계 장기매입채무및기타채무 장기매출채권및기타채권 장기차입금 재고자산
종속기업,공동지배기업및관계기업관련손익 지분법관련손익 중단사업이익 지배주주지분 총차입금 충당부채 토지 파생상품손실 파생상품손익 파생상품이익 판관비
현금및현금성자산 단기금융자산 단기금융부채 단기사채 단기차입금 유동성장기부채 장기금융부채 외환거래이익 외환거래손실 금융자산평가손익 매도가능금융자산평가손익
```
골든 값: `tools/tests/fixtures/fin/golden_fnguide.json` — 세 파일의 BS 시트 2021.03~최신(세진·삼성중 2023.09, 미포 2024.12A) 전 계정 값(백만원). **우리 DART 파서는 겹치는 분기에서 이 값과 맞아야 한다**(허용오차 0-3).

### 0-3. 단위·기간 규약
- fin·골든·BS 시트: **백만원**. 모델 표·페이지: **억원**(백만원/100). 달러: 백만$.
- 분기키 `2026Q2`. FnGuide 열키 `2026.06`(분기), `2025.12A`(연간). 손익은 **3개월분**(Q4 = 연간 − 3Q누적). BS 는 시점. 현금흐름은 누적→차분.
- 예측 구간: T+1~T+10 분기(2026Q3~2028Q4) + FY2026E~FY2028E(Y+2). 실적/추정 구분 `kind: actual|estimate`.
- 회계연도 12월 결산만 취급(모집단 전부 12월 확인 필요 — 아니면 `fiscal_year_end_month` 표기하고 보류).

---

## 1. 데이터 원천 (전부 키 없음 — DART_API_KEY 사용·생성 금지, 비밀값 읽기·출력 금지)

| 데이터 | 경로 | 비고 |
|---|---|---|
| 재무제표(연결/별도 BS·IS·CIS·CF), 주식의 총수, 배당 | DART 뷰어 3단계(`argus/kce/tools/kce_fetch.py`: `search_reports(name, start, end, 'A001'|'A002'|'A003')` → `pick_report(reports, 'YYYYQn')` → `toc(rcp)` → `fetch_section(node)`). 목차 제목 정규식: `^\s*2\.\s*연결재무제표\s*$`(연결 전체 한 번에), `^\s*4\.\s*재무제표\s*$`(별도), `주식의 총수`, `배당에 관한 사항`. 연결이 없는 회사는 `2. 재무제표` 만 있을 수 있다(제목으로 판별). | 표: BS 2열(당기/전기), IS 4열(당기 3개월·누적 / 전기 3개월·누적; 사업보고서는 연간 2열). 단위 캡션 `(단위 : 원)` 확인 후 백만원 환산. 픽스처 `tools/tests/fixtures/fin/*.html`(삼성중 2026Q2·2025Q4, 세진 2026Q2, 한라IMS 2026Q2) |
| DART 속도 | **프로세스 하나만**. `kce_fetch._pace()` 0.7s 파일락 게이트 사용. 병렬 금지(IP 차단 30~60분) | 수집은 백그라운드 1개, 다른 레인은 캐시·픽스처만 |
| 시세·시총·발행주식수·PER/PBR(TTM) | `https://aikstockdata.com/data/public/s/<code>.json` (금융위 T+1 종가, 출처표기 조건) `quote.close/shares_outstanding/market_cap_krw/as_of`, `valuation.pe_ttm/pb`, `financials`(DART 주요계정 — 대조용) | 비영리·출처표기. 페이지에 출처 문구 |
| 환율 일별 → 분기 평균/기말 | `https://api.frankfurter.app/<from>..<to>?from=USD&to=KRW,JPY,EUR,CNY` (ECB, `-L` 리다이렉트 따라감, 2005~) ; 최신 대조 `https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=1&pageSize=60` | 원/100엔 = 100/JPY×KRW … 레퍼런스 `변수` 행 5~14 와 같은 6행 |
| 척당 계약(선종·척수·금액·기간·상대) | `tools/assets/contracts.json` (230행, `type/ships/amt_krw_m/start/end/signed/party_anon/supersedes`) | 종료일 = 마지막 호선 인도. HD한국조선해양↔HD현대重 21건 공유(합산 금지) |
| 부문 수주 롤포워드·부문 매출·환노출·헤지 | `tools/assets/yards_cache/<stock>/<quarter>.json` (5 조선사 × 19분기, 백만원; `hedge.usd_sell_m`, `avg_rate`) | |
| 기자재→조선사 연결·제품 | `tools/assets/suppliers.json` | 근거 등급 있음 |
| 기존 Y+2 수주 추정(신규수주·잔고 시나리오) | `tools/assets/forecast_panel.json.gz` `companies[]` (5사 추정) | 매출 모델과 나란히 표시, 대체하지 않음 |
| 모집단 | `tools/assets/universe.json`(41) + 폴더 56개(승격 16 포함). 이름·역할(yard/holding/engine/equip/steel) | HD한국조선해양(009540)은 폴더 없음 — 지주 |

---

## 2. 산출물 스키마 (레인 간 계약 — 바꾸려면 여기 먼저 고친다)

### 2-1. `tools/assets/fin/<stock>.json` (kship_fin.py)
```json
{"stock":"010140","name":"삼성중공업","unit":"KRW_million","collected_at":"2026-09-30",
 "quarters":["2021Q4","...","2026Q2"],
 "reports":{"2026Q2":{"rcp":"20260814003496","title":"반기보고서 (2026.06)","kind":"A002","has_cons":true,"has_sep":true,
                      "sections":{"cons":"fin_cache/010140/2026Q2_cons.html","sep":"...","shares":"..."}}},
 "cons":{"bs":{"2026Q2":{"자산총계":..., "...":...}}, "is":{"2026Q2":{"매출액(수익)":..., "...":...}}, "cf":{"2026Q2":{...}},
         "is_ytd":{"2026Q2":{...}}, "raw_labels":{"2026Q2":{"bs":[["유동 자산",9684057.19,...]], "is":[...]}}},
 "sep":{ 같은 구조 },
 "shares":{"2026Q2":{"issued":880000000,"treasury":0,"outstanding":880000000,"common_issued":...}},
 "dividend":{"2025Q4":{"dps_common":0,"payout_pct":null}},
 "derivation":{"2025Q4":{"is":"annual_minus_9M","cf":"annual_minus_9M"}},
 "checks":[{"quarter":"2026Q2","scope":"cons","rule":"assets=liab+equity","ok":true,"diff":0.0}],
 "golden":{"2023Q3":{"compared":61,"mismatch":[{"acct":"...","ours":..,"fnguide":..}]}},
 "issues":[{"quarter":"2022Q1","code":"no_cons_statements","detail":"..."}]}
```
- `bs/is/cf` 키는 **0-2 의 FnGuide 계정명**을 쓴다(매핑 표는 `kship_fin.py` 상단 `ACCOUNT_MAP`; DART 라벨 정규식 → 계정명; 합성 계정: `총차입금 = 단기차입금+단기사채+유동성장기부채+장기차입금+사채(+리스부채는 별도 키 `리스부채`)`, `순차입금 = 총차입금 − 현금및현금성자산 − 단기금융자산`, `이자발생자산 = 현금+단기금융자산+장기금융자산`, `금융손익 = 금융수익 − 금융비용`, `이자손익`, `기타영업외손익`, `기타영업손익`). 매핑 못 한 원 라벨은 `raw_labels` 에 남긴다(버리지 않음).
- `is` 는 3개월 값. Q4 = 사업보고서 연간 − 그 해 3Q 누적(`derivation` 기록). 누적 정합 검사: `is_ytd[Q2] − is_ytd[Q1] == is[Q2]`.
- 주석(금융수익 세부: 이자수익/외환차익/외화환산/파생상품)은 **선택**: `3. 연결재무제표 주석` 안의 「금융수익」「금융원가」「기타수익」「기타비용」 표를 찾으면 채우고, 못 찾으면 그 계정은 null + `issues`.
- 계정명 정규화 함수 `norm_label`: 공백 제거, `(주석 N)`·괄호 숫자 제거, `Ⅰ.`류 접두 제거, 전각→반각.

### 2-2. `tools/assets/fx.json` (kship_fx.py)
```json
{"source":"ECB via api.frankfurter.app; Naver marketindex cross-check","as_of":"2026-09-30","daily_last":{"USDKRW":1354.4,"date":"2026-09-30"},
 "quarters":{"2026Q2":{"USDKRW_avg":..,"USDKRW_end":..,"JPY100KRW_avg":..,"JPY100KRW_end":..,"EURKRW_avg":..,"EURKRW_end":..,"CNYKRW_avg":..,"CNYKRW_end":..,"days":62}},
 "forward":{"method":"flat_last_end","2026Q3":{"USDKRW_avg":..,"USDKRW_end":..},"...":{}},
 "annual":{"2025":{"USDKRW_avg":..,"USDKRW_end":..}}}
```
2005Q1~현재 전 분기. 레퍼런스 `변수` 행 5~14 라벨과 1:1(` 원/달러(평균)`,` 원/달러(기말)`,` 원/100Y(평균)`,` 원/100Y(기말)`,` W/Euro(평균)`,` W/Euro(기말)`,` 원/중국원(평균)`,` 원/중국원(기말)`).

### 2-3. `tools/assets/prices.json` (kship_price.py)
```json
{"as_of":"2026-09-30","source":"aikstockdata.com(금융위 확정종가 T+1) — 출처표기·비영리","rows":{"010140":{"close":20100,"as_of":"20260928","shares_outstanding":880000000,"market_cap_krw":..,"pe_ttm":31.8,"pb":3.76,
  "financials_ref":{"period":"2026H1","revenue":..,"operating_income":..,"net_income":..},
  "history_quarterly":{"2024Q3":{"close_end":..,"high":..,"low":..,"avg":..}}}}}
```
`history_quarterly` 는 선택(로컬 `~/phalanx/toss_api.py candles_history` 가 인증돼 있으면; 워커는 비밀값을 읽거나 출력하지 않고 함수만 호출. 없으면 `history_unavailable:true`).

### 2-4. `tools/assets/sls/<stock>.json` (kship_sls.py, 조선사 5 + 지주 1)
```json
{"stock":"010140","origin":"2026Q2","unit":"USD_million | KRW_million",
 "contracts":[{"rcp":"...","type":"LNGC","ships":4,"amt_krw_m":..,"amt_usd_m":..,"fx_at_sign":1350.2,"signed":"2024-06-30","start":"...","end":"2028-08-31",
               "cohort":"⑤초호황","cohort_basis":"amt_per_ship vs type-year median (contracts.json), 신조선가 지수 미보유","schedule":{"2026Q3":12.3,"...":..},"curve":"linear_progress|s_curve","estimated_series":false}],
 "by_quarter":{"2026Q3":{"usd_m":..,"by_type":{"LNGC":..},"by_cohort":{"⑤초호황":..},"hedged_krw_m":..,"applied_rate":..,"hedge_ratio":0.7,"hedge_rate":..,"spot_assumed":..}},
 "by_year":{"2026":{...}},
 "reconcile":{"2025Q3":{"sls_krw_m":..,"reported_segment_rev_m":..,"ratio":0.82,"note":"공시된 척당 계약만 → 계약 미공시·반복건조·기타매출은 잔차"}},
 "target_opm":{"2026Q3":{"opm":0.09,"basis":"cohort mix × cohort OPM table (assumption)"}},
 "warnings":["종료일=마지막 호선 인도; 진행률 매출 분기와 다름","HD한국조선해양과 HD현대重 21건 동일 — 합산 금지"]}
```
코호트 표(가정, 화면·xlsx에 명시): ①적자 −5% ②BEP 0% ③중마진 5% ④호황 10% ⑤초호황 15% — 회사별로 실측 OPM(yards_cache 부문 OP/매출) 로 **캘리브레이션**해 `calibrated_shift` 기록.

### 2-5. `tools/assets/models/<stock>.json` (kship_model.py)
```json
{"stock":"075580","name":"세진중공업","role":"equip","origin":"2026Q2","unit":"KRW_100M(억원)","built_at":"...",
 "periods":{"quarters":["2021Q4","...","2028Q4"],"annual":["2021","...","2028"],"last_actual":"2026Q2"},
 "rows":[{"key":"매출액","label":"매출액","group":"손익","unit":"억원","q":{"2026Q2":{"v":1234.5,"kind":"actual","src":"fin.cons.is"},"2026Q3":{"v":..,"kind":"estimate","basis":"segments_sum"}},"a":{"2026":{"v":..,"kind":"mixed"}}},
         {"key":"매출조선기자재", ...}, {"key":"OP조선기자재",...}, {"key":"영업이익",...}, {"key":"EPS",...}, {"key":"BPS",...}, {"key":"PER",...}],
 "segments":[{"key":"조선기자재","driver":{"type":"customer_yard_revenue_weighted","weights":{"329180":0.5,"010620":0.5},"lag_q":1,"ratio_hist":{...},"ratio_used":..},"opm_path":{...}}],
 "assumptions":{"fx":{"USDKRW_avg":{"2026Q3":..}}, "tax_rate":0.22,"sga_ratio":..,"interest_rate_debt":..,"interest_rate_asset":..,"minority_share":..,"payout":..,"one_offs":[{"q":"2026Q1","amt":-40,"note":"..."}]},
 "fx_pnl":{"net_usd_exposure_m":..,"method":"외화 순노출 × Δ기말환율 (외화 시트 방식)","by_q":{...}},
 "valuation":{"price":{"close":..,"as_of":"..."},"eps_fwd12m":..,"bps_latest":..,"per_now":..,"pbr_now":..,"per_band":{"lo":..,"mid":..,"hi":..,"basis":"hist_quarterly|sector_default"},"roe_fwd":..,"coe":0.09,"fair_pbr":..,"fair_value_per":{"lo":..,"mid":..,"hi":..},"fair_value_pbr":..,"ev_ebitda":..,"note":"모델 산출값 — 목표주가·추천 아님"},
 "consolidation":{"method":"separate_plus_subsidiaries","subsidiaries":[{"stock":"333430","name":"일승","stake":..,"from":"2021"},{"stock":"099410","name":"동방선기","stake":..,"from":"2022"}]},
 "modules":[{"key":"wind","label":"풍력/플랜트","rows":[...]}],
 "backtest":{"freeze":"2025Q2","horizon":4,"revenue_wape_pct":..,"op_wape_pct":..,"n":4,"note":"단일 회사 4분기 — 통계 아님"},
 "views":{"분기":[["매출액",...]],"연간예상":[...],"보고서로":[...]},
 "quality":{"fin_quarters":19,"missing":[],"identities_ok":true,"warnings":[...]}}
```
`summary.json`: 회사별 FY2025A·FY2026E·FY2027E·FY2028E 매출/OP/OPM/지배NI/EPS/BPS/PER/PBR, `status: full|partial|no_fin`.

역할별 전략(`kship_model.py` 안 STRATEGIES):
- `yard`: 매출조선 = SLS 헤지적용 원화 × 화해 계수(reconcile ratio, 최근 4분기 중위) + 기타부문(정기보고서 부문 매출 비중 유지); OPM = SLS 타겟(코호트) + 알려진 일회성 + 회사 캘리브레이션; 공사손실충당부채 환입은 일회성 행.
- `holding`(009540): 종속 조선사 3사(329180·010620·삼호 비상장) 합산 − 내부거래 비율(실측 연결/합산 비율) → 지분법·연결.
- `engine`/`equip`/`steel`: 매출 = Σ(고객 조선사 매출_(t−lag) × 비중) × 비례계수(실측 회귀, 최근 8분기) — 세진 `연간예상` 의 weighted 방식과 동일; 고객 연결이 없으면 자기 II-4 수주 롤포워드(있으면) 또는 매출 추세 + 계절성(subQ r440~442 `계절성 적용`). 세진은 조선기자재+풍력/플랜트 2부문, 종속사 일승·동방선기(둘 다 모집단 — 그들의 fin 으로 연결 재구성).
- 공통: 판관비율(최근 4분기 중위), 이자손익(평균 잔액 × 실측 이자율), 환관련손익(외화 순노출 × Δ기말환율, 노출이 없으면 0 + 표기), 법인세율(3년 유효세율 5~27% 클립), 지배주주 비중(실측 평균), EPS=지배NI/유통주식수, BPS=지배주주지분/유통주식수(자본 롤: +NI −배당), EBITDA=OP+감가상각비.

### 2-6. xlsx
- `argus/kship/models/<stock>_model.xlsx` (kship_model_xlsx.py): 시트 `변수`·`BS연결`·`BS별도`·`subQ`·`SLS`(조선사)·`분기`·`연간예상`·`TP`·`외화`·`README`. **레퍼런스와 같은 헤더 규약**(행1 `1Q05…`, 행4 `YYYY.MM`, 열 E 부터, 연간 열 4분기 뒤, 이름정의 `SUBQH` `BS연결H`…). subQ 확정 행은 진짜 `VLOOKUP` 수식, 추정 행은 가정 셀 참조 수식(사용자가 가정 바꾸면 재계산). 2021Q4~2028 범위(레퍼런스는 2005~ — 우리는 fin 이 있는 구간만).
- `~/phalanx/jem_data/kship_models/reference/<이름>_<stock>_subQ_2026Q2.xlsx` (kship_xlsx_patch.py): **원본을 zip/XML 수준에서 그대로 두고** 셀만 채운다 — `BS연결`/`BS별도`(세진은 `BS일승(별도)`·`BS동방선기(별도)` 도, 각각 333430·099410 fin) 행4 기간 라벨 추가(`2023.12`, `2023.12A`…`2026.06`), 계정 행 값(백만원, 코드→계정명 매핑, 없는 계정은 비움), 행3 `UPDATE: 26-09-30`, `변수` 환율 6행 새 분기, `분기!C2`·`TP_PE PB!B1` 종가·날짜, `workbook.xml` `<calcPr fullCalcOnLoad="1">`. 공유문자열(`t="s"`)이 필요한 라벨은 sharedStrings 에 추가. 도형·차트·수식·스타일은 바이트 그대로. 검증: 재오픈(openpyxl, 도형 우회) → 수식 개수 원본과 동일, 패치 셀 개수·목록 리포트, 겹치는 기존 셀 무변경, subQ 의 `VLOOKUP` 사슬을 파이썬으로 흉내내어 2026Q2 `매출액(수익)` 이 fin 값과 같은지 확인(LibreOffice 없음).

### 2-7. 페이지
- `kship_model_section.py` `render_model_section(entry, model, fin, price, sls=None) -> html`: (1) KPI 스트립 FY2026E~28E 매출/OP/OPM/EPS + 현재 PER/PBR (2) 분기 손익표 최근 8A+10E(추정 음영, 근거 툴팁) (3) 사업부 매출·OPM 차트 (4) 조선사: 선표 매출인식(백만$→원화)·코호트 비중 차트 (5) 가정 패널(환율·헤지·OPM·세율·판관비율) (6) 밸류에이션 스트립(PER/PBR 밴드·적정가치 구간, "모델 산출값·추천 아님") (7) 다운로드 `models/<stock>_model.xlsx` (8) 각주: 출처(DART·aikstockdata·ECB)·한계·백테스트. 회사 페이지: `kship_page.py`(조선사) `kship_parts.py`(기자재) 에 `_model_section(stock)` 가드 삽입(모델 없으면 섹션 없음). 허브: `argus/kship/models.html` 섹터 표(정렬·검색) + `index.html` 칩 링크.

---

## 3. 레인(파일 소유 — 한 파일은 한 레인만 쓴다)

| 레인 | 소유 파일 | 완료 기준 |
|---|---|---|
| L1 fin | `tools/kship_fin.py`, `tools/tests/test_kship_fin.py`, `tools/assets/fin_cache/`, `tools/assets/fin/` | 픽스처 4세트 파싱 통과; 골든 대조(세진·삼성중 2023Q3 / 미포 2024Q4) 계정 ≥50개 일치(±3 백만원, 매핑 불가 계정은 목록으로); `--collect` 체크포인트(있으면 건너뜀)·단일 프로세스; 57사×19분기 수집은 **백그라운드 1개**로 시작하고 진행 로그 `assets/fin_collect.log` |
| L2 fx+price | `tools/kship_fx.py`, `tools/kship_price.py`, `assets/fx.json`, `assets/prices.json` | 2005Q1~2026Q3 분기 평균/기말 6행; 2026Q2 USDKRW 기말 1550.89(ECB 6/30) 확인; 56사 시세 |
| L3 sls | `tools/kship_sls.py`, `assets/sls/`, `tests/test_kship_sls.py` | 5 조선사 스케줄·코호트·헤지 적용·화해 비율; 공유 계약 합산 금지 검사 |
| L4 model | `tools/kship_model.py`, `tests/test_kship_model.py`, `assets/models/` | 픽스처 fin(삼성중·세진)으로 전 행 산출·항등식(매출−원가=GP, GP−판관±기타=OP, 세전−법인세=NI, 자산=부채+자본 롤) 통과; 역할 5종 전략; 백테스트 |
| L5 xlsx-gen | `tools/kship_model_xlsx.py` | 모델 json → xlsx, 재오픈 시 수식·이름정의 유효, 셀 ≤ 20MB |
| L6 xlsx-patch | `tools/kship_xlsx_patch.py`, `tests/test_kship_xlsx_patch.py` | 원본 3개 무손상 패치(2-6 검증 전부) |
| L7 section | `tools/kship_model_section.py`, `kship_page.py`/`kship_parts.py` 의 `_model_section` 훅(그 두 파일은 L7 만 수정), `models.html` 빌더, `index.html` 칩 | 모의 모델로 렌더, 실제 모델로 재렌더; HTML 유효; 다크 대응(기존 page() 셸) |
| L8 docs | `MODEL.md`, `UPDATE.md` 항목, `HANDOFF.md` 절, `README.md`, `.github/workflows/update-kship.yml` 단계 추가 | 재현 명령 순서·DART 단일 프로세스 명시 |

공통 규칙: 파이썬은 `~/Library/phalanx_venv/bin/python`(3.14, openpyxl 3.1.5) — 표준 라이브러리 + openpyxl 만. `kce_fetch` 는 `sys.path` 에 `argus/kce/tools` 추가해 import(`kship_lib` 참고). 추정치는 항상 `kind:"estimate"` 와 `basis` 를 갖고 화면에 '추정'을 표시한다. 숫자는 출처 없이 만들지 않는다 — 가정이면 가정이라고 적는다. 검증 통과 문구가 아니라 **실제 실행 결과**(명령·출력)로 보고한다.

---

## 4. 회사 특유 파라미터 — 레퍼런스 xlsx 에서 읽은 값 (L4 model 이 `modules`/전략에 쓴다; 출처는 사용자 애널리스트 모델, 화면에는 '레퍼런스 가정' 으로 표기)

### 4-1. 세진중공업(075580) — 조선기자재 비례식 + 풍력/플랜트 + 종속사
- **조선기자재 매출 = weighted 고객 매출 비례**(`연간예상` r19~r26): 가중치 = HD현대重 매출 × HHI ratio(0.2; 데크하우스 0.3→0.4, 어퍼데크 0) + 미포 매출 × HMsb ratio(0.9; 데크하우스 1.0, 어퍼데크 0.7). 'Weighted 매출: 미포70%~100%, 현중 0%~30%'. 세진 조선매출 YoY ≈ weighted 매출 YoY(`weighted현중`)로 추정. 우리 구현: 두 고객의 fin 매출(연결)로 weighted 지수를 만들고, 세진 조선기자재 매출/weighted 비율(최근 8분기 중위)을 곱한다. 계절성은 subQ r440~442(분기/연간 비중 3년 평균).
- **LPG탱커**(`연간예상` r76~98): HHI그룹 LPG선 도크 탑재 척수(울산·군산·삼호·미포) × 가중(VLGC 2, 미포 1) × 미포환산 ASP(억원/척: 2018 20→2023 30 가정). 우리: contracts.json 의 HD현대重·미포·삼호 LPG/VLGC/LPGC 계약 척수와 인도 분기로 대체(ship_types.json 의 타입 코드 확인).
- **LNG-Fuel 연료탱크**(r109~113): 대당 8→10억원 × 연 5척 = 40~50억원/년. **소형LNG(Type-C)** r105: 연 100억원(2019~2022) 이후 0. ⓓ기타 r101~102.
- **풍력/플랜트**(`풍력e`): ASPperMW 20억원/MW(200MW=4,000억원), Floater당 200억원(UnitASP), 터빈 10MW, 캐파 Floater 12~13기/년(=2,667억원/년, 건조 캐파 1.5조원 상한), M/S 가정 25%("우리가 1/2 하고 절반 지연"). 프로젝트 표: 울산 200MW 실증(COD 2024, 4,000억·Floater 20기 → 매출 2026 1,800 / 2027 1,800), CIP#1(COD 2025, 500MW 8,000억 → 2026 1,000·2027 4,000·2028 5,000), CIP#2(COD 2026 → 2027 2,000·2028 4,000·2029 4,000), CIP#3(COD 2027, M/S 0.5 → 2028 2,000·2029 4,000·2030 4,000), Equinor 동해-1(COD 2025, 200MW → 2026 400·2027 1,400·2028 2,200), Equinor 반딧불(COD 2026 800MW 12,800억 → 2027 4,000·2028 6,000·2029 6,000), KFW(COD 2028 1,000MW → 2029 6,000…). 합계 `매출추풍력`: 2026 900 · 2027 2,400 · 2028 4,200 · 2029 4,000 · 2030 5,000(억원); 가이던스 대비 할인 50%. **이 표는 2024년 초 레퍼런스의 가정이라 현재 실적(fin 의 풍력/플랜트 부문 매출 — 정기보고서 부문표는 yards_cache 가 아닌 세진 자체 II-4/부문 주석에 있음; 없으면 별도 매출 − 조선기자재 추정 = 잔차)으로 재정렬해 쓰고, 그대로 쓰지 않는다.** 풍력 OPM 가정 5~6%(r552~563 타겟 OPM 구조).
- **종속사**: 일승(333430, 2021.10 인수; 연간예상 r117~120 OPM 5% 가정, 분뇨·HRSG·LNG재기화) · 동방선기(099410, 2022~; r125~128 OPM 6% 가정, 배관). 연결 = 별도 + 일승 + 동방선기 + 베트남(세진베트남, 비상장·미공시 → 연결−합산 잔차로 표기). `연결/별도 ↕` 비율 r437 로 내부거래 반영.
- 원가 구성(r455~462): 재료비·노무비·외주가공비·기타경비 = 원가 × 비중(과거 실측 비중 유지). 토지 재평가·캐파(`토지 캐파`: 원산 587,639㎡ 등 합산 730,217㎡) 는 표시용.

### 4-2. 삼성중공업(010140)
- 부문: 조선(조선해양) + 건설(토건), 수출/내수 분리. `SLSOPM조선해양` 타겟 + `SLS해양비중`(해양 OPM 별도) + ② 미지 일회성/오차 + ③ 알려진 일회성(`확충당금설정`) → 타겟OPM2(r569). 공사손실충당부채(r92, BS갭) 전입/환입은 일회성 행.
- **일회성 표**(`일회성`, 억원): 영업단 — 임단협 −40, TransOcean 충당금 −190, PDC1·Seadrill2 장부가 −40, 취소 RIG 5기 Lay-off −30, 해양 원가 선투입/환입 +35, 건설 하자보증 −9; 영업외 — ENSCO 중재 −80, PDC 평가손실 −15. (과거 항목 — 우리 모델은 fin 의 기타영업외·충당부채 변동에서 새 일회성을 뽑고 이 표는 사례로만)
- **드릴쉽**(`드릴쉽`): 리세일 5기 잔존가 240백만$/기(합 1,270), 연 30백만$/8년 상각 가정, 소송(STENA 매각 $505m, PACD 환입 1,340억원, ENSCO 패소 $180m+벌금 $75m). 현재는 대부분 종결 — 모델은 BS `기타(확정계약평가)`·충당부채 잔액만 표시.
- **수주목표 평가**(`수주목표.평`, 백만$): 목표 9,700; 가능성 8,420~11,250 = LNG 카타르 15척(230/척=3,450) + 카타르 외 7~10척(250~260) + FLNG 모잠비크 1~2기(2,500~4,000) + VLAC 4~6척(120) + 셔틀탱커 2~4척(120). 우리: forecast_panel 의 신규수주 시나리오(P25/50/75)와 나란히.
- 수주잔액(추) 롤 r577~583: 잔액_t = 잔액_{t−1} + 신규수주(추) − 매출. 선수금/수주잔액 비율 r780. 헤지비율 = 헤지 명목/잔량(백만$) r716, 헤지환율 = 수주시점 원/달러 평균(`변수` 수주환율·상선/해양 분리).

### 4-3. HD현대미포(010620)
- 부문: 조선(울산 별도) + 비나신(HM_VNS, 베트남 종속 55% → 연결) + 기타/금융(과거). SLS: 확정 HM·HM_VNS + 미래, `← 당겨옴/미룸`, 매출비나신$·매출미포별도$·매출미포연결$ → 원화(헤지환율 HEDGE 70%·open 30%). SLS 실제 OPM 행: 미포_OPM 2024Q3 6.1% → 2026 ~10.3~10.9%, 비나신_OPM 5.4% → 9.7%, 비나신 비중 9~45%.
- 코호트 매출(`SLS` r71~76, 백만$ 연간): 2024 ①적자 157 ②BEP 8 ③중마진 485 ④호황 1,305 ⑤초호황 1,647; 2025 ⑤ 3,018·④ 78·② 84; 2026 ⑤ 6,522·② 270; 2027 ⑤ 5,857 → 고마진 물량 비중 2025~ 100%. 우리 코호트 규칙은 이 결과와 방향이 같아야 한다(2021 이후 수주 = ④~⑤).
- `도크`: 4도크(400k DWT ×3, 350k ×1, 380×65m), 안벽 2,360m, 4척 동시건조. `건조량(CGT)`·`/CGT` 원가(노무·재료·후판·장비·기타경비, r451~489) — 우리는 CGT 데이터가 없어 척수 가중(계약 ships)로 대체하고 표기.
- 지분법(`지분법E/T`): 비나신 55%(NPM 25% 가정), 하이투자증권 76→83%·하이자산운용 7.6%(과거, 현재 매각) — 현재 관계기업은 fin 의 `종속기업,공동지배기업및관계기업관련손익` 로만.
- `한조모델로→`: 지주 HD한국조선해양(009540) 모델로 넘기는 표(매출·원가·GP·OP·영업외·세전·순이익·지배NI·매출미포·OP미포·일회성·자본·감가·CAPEX·매출채권·매입채무, 십억원) — holding 전략이 종속 3사에서 모으는 항목 목록으로 그대로 쓴다.

### 4-4. 공통 밸류에이션(`TP_PE PB`·`TP_EBITDA`·`TP_BPS`·`RIM`)
- PER: 적정 PER(과거 밴드 10/15/20 배 예시) × FWD EPS(2개년 가중 Weight) → ROUND(-2/-3). PBR: 적정 PBR = ROE/COE(COE = ROE/PBR 역산, 고·평·저 밴드), 주당 적정가치 = BPS × 적정PBR. EV/EBITDA: 영업가치 = EBITDA(FWD 2Y 평균) × 배수 − 순차입금 → 주당. 상승여력 = 적정/종가 − 1. 우리는 세 방식을 모두 계산해 **구간(lo/mid/hi)** 으로 보이고 단일 목표주가는 내지 않는다.
