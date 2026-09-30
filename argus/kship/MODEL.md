# 한국조선(kship) 실적 모델 — 무엇이 어떻게 만들어졌는가 (2026-09-30)

사용자의 애널리스트 모델 3개(세진중공업 075580 · 삼성중공업 010140 · HD현대미포 010620 의 `subQ` xlsx)를 **레퍼런스**로,
모집단 57사(회사 폴더 56 + 지주 HD한국조선해양 009540)에 같은 골격의 분기 실적 모델을 만들고 회사 페이지에 싣는다.
설계 계약(스키마·계정명·레인 소유)은 [MODEL_SPEC.md](MODEL_SPEC.md), 이 문서는 **실제로 만들어진 것**과 그 재현·한계다.
아래 숫자는 전부 2026-09-30 **21:50 KST 시점** 산출 파일을 열어 읽은 값이다(레인 보고 문구가 아니다) — 1차 구축(17:45) 뒤 2차 검증·수정(20:40~21:50, §10)이 fin 파서·모델 엔진·패치 도구를 고치고 fin(21:18)·sls(21:08)·prices(21:10)·models/xlsx(21:47)를 재생성했다. 회사 페이지·허브(21:28~21:39)는 그보다 앞서 빌드돼 §7 ⑥ 재실행이 남아 있다.

- 레퍼런스 원본은 사용자 사유 파일 — `~/phalanx/jem_data/kship_models/reference/`(맥미니 로컬)에만 있고 레포에 없다.
- 우리 산출(json·xlsx·html)은 DART 공개 자료 + 우리 추정이라 레포(`argus/kship/`)에 실린다.
- **모델 산출값은 목표주가·추천이 아니다.** 추정 셀은 전부 `kind:"estimate"` + `basis` 를 갖고 화면에 '추정' 음영으로 보인다.

## 1. 레퍼런스 해부 → 우리 대응

| 레퍼런스 시트 | 하는 일 | 우리 산출 | 생성기 |
|---|---|---|---|
| `변수` | 가정 시계열 — 환율 8행(원/달러·원/100엔·원/유로·원/위안 × 평균·기말), 후판·하우스 환율 | `tools/assets/fx.json` (+ 일별 캐시 `fx_daily_cache.json`) | `kship_fx.py` |
| `BS연결` `BS별도` (세진은 `BS일승(별도)` `BS동방선기(별도)` 도) | **FnGuide 계정 덤프**(백만원) — 사용자가 말한 "박힌 것" | `tools/assets/fin/<stock>.json` (DART 재무제표를 FnGuide 계정명으로) | `kship_fin.py` |
| `subQ` | 분기 서브모델(억원). 확정치는 `VLOOKUP($D, BS연결/BS별도, MATCH(...))/U`, 추정치는 사업부 빌드업 | `tools/assets/models/<stock>.json` 의 `rows`·`segments`·`assumptions` | `kship_model.py` |
| `SLS` (미포·삼성중) | 클락슨식 선표 피벗(백만$) → 헤지환율/건조시점환율(HEDGE 70%) → 원화 → 수주업황 코호트별 타겟 OPM | `tools/assets/sls/<stock>.json` (조선사 5 + 지주 1) — 클락슨 대신 **척당 계약 공시 원장** | `kship_sls.py` |
| `분기` `연간예상` `보고서로` | subQ 를 보고서 표로 요약 | 모델 `views` | `kship_model.py` |
| `TP_PE PB` `TP_BPS` `TP_EBITDA` `RIM` | 밸류에이션 | 모델 `valuation` — PER·PBR·EV/EBITDA 를 **구간(lo/mid/hi)** 으로, 단일 목표주가 없음 | `kship_model.py` |
| `외화` `→답` | 외화 순노출 × Δ기말환율 | 모델 `fx_pnl` (노출 공시가 없는 회사는 0 + 표기) | `kship_model.py` |
| 회사 특유(`풍력e` `LNG-Fuel` `드릴쉽` `도크` `한조모델로→` …) | 회사 모듈 | 모델 `modules[]` (세진 `wind`·`lng_lpg`, 조선사 `forecast_panel`) | `kship_model.py` |
| (파일 전체) | 애널리스트가 가정을 바꿔 재계산하는 xlsx | `models/<stock>_model.xlsx` — 확정 행은 진짜 `VLOOKUP`, 추정 행은 `변수` 셀 참조 수식 | `kship_model_xlsx.py` |
| (원본 3개) | 박힌 데이터 최신화 | `reference/<이름>_<stock>_subQ_2026Q2.xlsx` — zip/XML 수준 제자리 패치(로컬 전용) | `kship_xlsx_patch.py` |
| (없음) | 회사 페이지 「실적 모델」 섹션 · 섹터 허브 | `<stock>/index.html` 하단 섹션, `models.html` | `kship_model_section.py` + `kship_page.py`/`kship_parts.py` 의 `_model_section` 훅 |

레퍼런스 세 파일의 계산 사슬(행 번호까지)과 회사 특유 파라미터는 MODEL_SPEC §0-1·§4 에 실측으로 적혀 있다.

## 2. 데이터 원천 — 전부 키 없음

| 데이터 | 원천 | 비고 |
|---|---|---|
| 재무제표(연결/별도 BS·IS·CF), 주식의 총수, 배당 | DART 뷰어 3단계 — `argus/kce/tools/kce_fetch.py` `search_reports → pick_report → toc → fetch_section` | **프로세스 하나만**, 요청 간격 0.7s 파일락(`kce_fetch._pace`). 병렬이면 IP 차단 30~60분. 원문 HTML 은 `tools/assets/fin_cache/<stock>/<quarter>_{cons,sep,shares,div}.html` + `_meta.json` 에 캐시(체크포인트, **레포에 커밋하지 않음**) |
| 시세·시총·발행주식수·PER/PBR(TTM) | `https://aikstockdata.com/data/public/s/<code>.json` — 금융위 확정 종가 T+1 | 라이선스 `aiksd-public-1.1`: **출처 표기 · 비영리 인용·이용 · 상업적 재배포 불허**. 응답의 `license`·`citation` 을 `prices.json` 에 그대로 보존하고 페이지 각주가 인용한다. 인용 문구: "자료: 한국주식데이터(aikstockdata.com) — 원천: 금융감독원 DART · 금융위원회 공공데이터포털" |
| 분기 종가 밴드(기말/고/저/평균) | `~/phalanx/toss_api.py candles_history` (토스 일봉, 수정주가) — **맥미니 로컬에서만**, 토큰 캐시 파일 존재만 확인 | 없으면 `history_unavailable:true`. 같은 날 종가가 금융위 확정 종가와 수십 원 다를 수 있어(`close_check`) 밴드용으로만 쓰고 정본은 aik `close` |
| 환율 일별 → 분기 평균/기말 | ECB 참조환율 `api.frankfurter.app`(2005~), 최신 대조 `api.stock.naver.com marketindex` | 교차환율은 **일별로 먼저** 만들고 평균(비율의 평균). 레퍼런스 `변수` 는 서울외환시장 종가라 2005Q1 원/달러 평균 −0.31원·기말 +0.05원 차이 — 맞추지 않고 기록만 |
| 척당 계약(선종·척수·금액·기간) | `tools/assets/contracts.json` (KIND 단일판매ㆍ공급계약체결) | 종료일 = 마지막 호선 인도. HD한국조선해양↔HD현대重 21건 동일 계약(합산 금지) |
| 부문 수주 롤포워드·부문 매출·환노출·헤지 | `tools/assets/yards_cache/<stock>/<quarter>.json` | 조선사 5 × 19분기 |
| 기자재→조선사 연결 | `tools/assets/suppliers.json` | 근거 등급 있음 |
| 기존 Y+2 수주 시나리오 | `tools/assets/forecast_panel.json.gz` | 모델 옆에 모듈로 나란히 둘 뿐, 합산하지 않음 |
| 모집단 | `tools/assets/universe.json` 57행(업종 13 · 제품 6 · 지정 22 · 탐색 16; 지주 009540 포함) | 9/12 주간 스캔이 승격 16을 지운 회귀(57→41)를 9/30 21:38 복구 — §6-16, `kship_scan.carry_forward` |

DART_API_KEY 류 인증키는 쓰지도 만들지도 않는다. 비밀 파일은 읽지 않는다.

## 3. 계산 사슬

```
DART ─kship_fin─▶ fin/<stock>.json ─┐
ECB  ─kship_fx──▶ fx.json ──────────┼─▶ kship_sls ─▶ sls/<stock>.json ─┐
aik  ─kship_price▶ prices.json ─────┤                                    ├─▶ kship_model ─▶ models/<stock>.json + summary.json
contracts.json · yards_cache ───────┘                                    │        │
                                                                         │        ├─▶ kship_model_xlsx ─▶ models/<stock>_model.xlsx
                                                                         │        └─▶ kship_model_section ─▶ 회사 페이지 섹션 · models.html
                                                                         └─▶ kship_xlsx_patch ─▶ reference/*_subQ_2026Q2.xlsx (로컬)
```

### 3-1. fin — DART 재무제표를 FnGuide 계정으로 (`kship_fin.py`)
- 표는 **캡션**(`연결 재무상태표 / 제 N 기 … / (단위 : 원)`)으로 식별하고 단위를 읽어 백만원으로 환산한다. BS 는 당기 열, IS 는 **3개월 열**을 그대로 쓴다(FnGuide 는 누적 차분 — 정정분이 있는 분기는 어긋남, §6).
- Q4 손익·현금흐름 = 사업보고서 연간 − 그 해 3Q 누적(`derivation: annual_minus_9M`). 2021Q4 를 만들기 위해 2021Q3 를 보조 수집한다(산출물에는 넣지 않음).
- 라벨 정규화 `norm_label` → `ACCOUNT_MAP`(정규식 → FnGuide 계정명). 매핑 못 한 라벨은 `raw_labels` 에 남긴다. 합성 계정은 `synth_basis` 에 정의를 적는다(총차입금·순차입금·이자발생자산·금융손익·이자손익·기타영업외손익·매출총이익·CAPEX…).
- 골든 대조에서 배운 FnGuide 관행을 매핑에 반영했다: 단기금융부채 = 파생+확정계약+리스+기타금융부채(차입 제외), 단기금융자산 = 단기금융상품+파생+확정계약(FVPL 제외), 사용권자산 → 기타비유동자산, face 라벨 '단기/장기금융부채'(차입금 총액 표기 회사) → 단기/장기차입금으로 편입 + `issues.borrowings_face_label`.
- 부호·구조 정규화(2차 검증에서 추가 — `kship_fin.py` 머리말): ① face 가 비용을 괄호(음수)로 찍는 표(성광벤드·한국카본 FY2024~, 금강공업 2024Q1~, STX엔진 2024Q2~, 동성화인텍·인화정공 FY2025~, 현대리바트 사업보고서, 원일티엔아이 전 분기, 삼미금속 2022Q4 = 9사 91표)는 매출액>0·매출원가<0 이면 매출원가·판관비·기타영업(외)비용·금융비용·이자비용·외환차손·외화환산손실·파생상품손실·법인세비용 부호를 뒤집는다(`issues.expense_sign_negative` 91) — 안 하면 매출−원가≠GP 이고 Q4 = 연간(−) − 9M(+) 로 두 배 어긋난다(성광벤드 2024Q4 매출원가 −258,551 → 42,757.68). ② '…의 귀속' 블록의 계속·중단영업이익(지배주주분)은 총액으로 쓰지 않는다(세진 FY2023 계속영업이익 17,757 오매핑 수리, KCC '계속영업반기순이익' 라벨 추가). ③ 중단영업이 연간에만 있으면 Q4 중단사업이익 = 연간값(9M 은 0; 한화시스템·인화정공·영흥·HD현대마린엔진·금강공업·메디콕스·HJ중공업 9건). ④ 매출총이익~영업이익 사이의 매핑 안 된 영업비용 줄(금강공업 '물류비'·영흥 '대손상각비')은 잔차가 그 줄들로 설명될 때만 판관비에 더한다(`issues.sga_absorbed_op_lines` 162, `raw_labels` 에는 그대로 남음).
- 법인세 부호: '법인세비용(수익)' 양수 표기 법인세수익은 세전−법인세=순이익 항등식으로 뒤집고 `issues.tax_sign_flipped`(214 → 93 — 비용 음수 표기 수리 뒤 진짜 법인세수익만 남음).
- 주식의 총수: 열 머리가 '의결권 있는 주식/없는 주식/합계'(KCC·현대리바트·한국선재 — 각주 "의결권 있는 주식은 보통주")·'-'(한신기계, 위치 기반 `col_basis:positional`)인 표도 읽는다. 하위 소절 '해당사항 없습니다' 에 오탐하던 생략 판정도 고쳐 `shares_table_not_found` 55 → 0. 분기 기재 생략은 직전 값 이월 `kind:estimate` + `carried_from`(138건 전부).
- `checks`: 자산=부채+자본(1,812건 중 실패 1 — HD현대마린엔진 2025Q3 별도, 회사 공시 자체 73백만원 불일치 §6-13), 누적차분==3개월(869/868/856건 중 실패 8/13/13 — 전부 후속 보고서의 전기 재작성 §6-7), 세전−법인세=순이익(1,630 중 실패 1 — 한국주강 2023Q2 별도 −2.05), CF 절대값 부호(연간 vs 9M 표시 차이 기록용).

### 3-2. fx — ECB 일별 → 분기 8행 (`kship_fx.py`)
2005Q1~현재 전 분기(87개) + 연간(22개). 예측 구간 `forward` 는 `flat_last_end` — 마지막 ECB 관측치(2026-09-29 원/달러 1,353.36)를 2028Q4 까지 평평하게 두고 `kind:estimate` 표기. 선도환율·컨센서스 아님. 오늘(9/30) 값은 14:15 CET 이후 게시라 재실행 시 2026Q3 가 완결로 바뀌고 forward 가 2026Q4 부터 시작한다(설계 의도). 2차 검증: forward 루프가 마지막 완결 분기 ≥ 지평(2029 이후 실행)일 때 무한루프였던 것을 `q <= q_to` 종료로 고쳤다 — fx.json 자체는 16:21 산출 그대로(재실행 불필요).

### 3-3. prices — 시세 (`kship_price.py`)
57사 전부 aik 에서 종가·시총·주식수·PER/PBR(TTM)·최신 정기보고서 주요계정(fin 대조용). 종목당 0.5s 간격. 실패는 `rows[code].error` 로 남기고 전체를 실패시키지 않는다. 2차 검증에서 붙인 것: `naver_check` — 같은 기준일 네이버 정규장 종가 대조(9/29 기준 57종목 중 같은 값 8 · 1% 초과 8 · 최대 −3.45%(079430, aik 5,600 vs 5,800); 시가·고가·저가·거래량은 같고 **종가만** 다르다). `close` 는 계약대로 aik 값을 두고 차이를 기록만 한다 — 어느 쪽이 '확정'인지 판정하지 않는다(§6-15). 이력 창은 5년 전이 속한 분기의 첫날(2021-07-01)로 정렬(사흘짜리 첫 분기 방지), 토스 이력이 없을 때는 직전 파일에서 이어 붙인다(`history_meta.carried_from`, `--no-carry`로 끔). 21:10 재실행은 `--no-history` 라 57행 이력이 전부 `carried_from: 2026-09-30`(삼성重 행 기준 토스 일봉 1,394개, 2021-01-21~2026-09-30).

### 3-4. sls — 선표 매출인식 (`kship_sls.py`)
1. 원장 계약(선종·척수·금액·수주일·종료일)을 **계약기간 안에 선형 배분**(`curve: linear`)해 분기 매출$ 를 만든다(종료일 '-' 은 같은 선종 계약기간 중위로 추정 `end_estimated`).
2. 헤지 적용 원화 = 매출$ × (헤지비율 × 헤지환율 + (1−헤지비율) × 건조시점 spot). 헤지비율은 회사가 약정환율을 공시했을 때만 실측 — 한화오션 0.1717(`usd_sell_m 3,850.75 ÷ (기말 잔고 33,008,410백만원 ÷ 평균약정환율 1,472.04)`), 나머지 4사·지주는 레퍼런스 SLS 시트의 HEDGE 70% 가정. spot 은 fx.json(과거 실측, 미래 forward).
3. 코호트(①적자~⑤초호황)는 척당 금액을 선종별 연도 중위와 비교한 **원장 내부 상대등급**(`year_index` 2024 1.0 / 2025 1.0056 / 2026 0.9299) — 신조선가 지수를 갖고 있지 않다. 코호트 OPM 표 ①−5% ②0 ③5 ④10 ⑤15% (가정, 화면·xlsx 에 표기) → 분기 `target_opm`. 회사 실측 OPM(fin 연결) − 코호트 타겟의 중위를 `calibration.calibrated_shift` 로 잰다 — 1차 빌드는 fin 부재로 null 이었고 21:08 재빌드에서 삼성重 +3.59%p · 한화오션 +4.39 · HD현대重 +6.41 · HJ +4.32 · 대한조선 +22.46 · 지주 +10.32 로 채워졌다.
4. 화해: `ratio = SLS 원화 ÷ 정기보고서 해양 부문 매출 3개월분`(최근 4분기 중위)과 `backlog_coverage_at_origin = 원장 잔여 원화 ÷ 공시 해양 기말잔고`. 원장이 2024~ 공시분이라 과거 ratio 는 낮게 나오고, 미래 배율은 잔고 커버리지 쪽이 덜 편향된다(파일 `reconcile_summary.warning`).
5. 지주 009540 은 HD현대重과 동일한 21건을 `counted:false` 로 두어 합산을 막는다(판정 키는 rcp 가 아니라 선종·척수·금액·수주일 — 두 회사가 각각 접수해 rcp 가 다르다).

### 3-5. model — 역할별 전략 (`kship_model.py`)
- 실적 구간(2021Q4~2026Q2)은 fin 값을 **그대로**(`kind:actual`, `src`), 추정 구간(2026Q3~2028Q4, FY2026E~2028E)은 전부 `kind:estimate` + `basis`. 단위 억원(백만원/100).
- `yard`(조선사 5): 매출조선 = **SLS 해양 원화 + (공시 해양 잔고 − 원장 잔여) 를 최근 4분기 '부문매출 − SLS' 중위 속도로 소진**(`sls_marine_plus_uncovered_backlog_runoff`). 스펙의 '1/ratio 배율' 은 한화오션에서 4.8배가 되어 공시 잔고를 넘어서므로 채택하지 않았고 대안값은 `driver.scale_alternatives` 에 동봉. 기타 부문은 최근 4분기 중위 유지. OPM = SLS 코호트 타겟 + 회사 캘리브레이션(실측 OPM − 타겟).
- `engine`/`equip`/`steel`(기자재 51): 매출 = f(Σ 고객 조선사 매출_(t−lag) × 비중) — 2차(F2)에서 **격자 탐색**으로 바꿨다: 가중치 후보(suppliers.json 비중·균등·레퍼런스 weighted …) × 시차 0~4분기 × 회귀 창 8/12/19분기 × 변환(수준·YoY·4분기 이동합)에서 상관 최대 조합을 원점 회귀로 채택(`CORR_MIN` 0.30, 추정 구간을 다 덮는 조합만; `customer_yard_revenue_weighted`), 미달·고객 연결 없음이면 매출 추세 + 계절성(`trend_seasonal`, 전년동기 × (1+g), g 감쇠 — subQ r440~442 방식). 후보표(세진 180개)·선택 경로·p<0.05 임계 r(df=n−2)·과적합 경고("다중비교 보정 없음 · 4분기 이동합은 평활로 상관이 부풀 수 있음")를 `driver.grid`·`driver.significance` 에 그대로 남긴다. 채택 29사(1차 7) — 예: KCC 시차 4 · 창 12 · 4Q합 r 0.63, 오리엔탈정공 시차 0 · 창 19 r 0.95, 케이프 시차 0 · 창 8 r 0.94.
- `holding`(009540): 매출 = HD현대重(329180) 모델 매출 × 실측 연결/자회사 비율(합병 후 분기), OPM = 자회사 OPM + 실측 차이(`subsidiary_yard_scaled`) — 1차는 329180 fin 부재로 추세 폴백이었다.
- 세진 특수: 연결 = 별도 + 일승(333430) 모델 + 동방선기(099410) 모델 + 잔차(세진베트남 미공시 → `연결조정`). 조선기자재 = 별도 매출 전체(부문 분리는 face 에 없음). 고객지수 가중치는 레퍼런스 `연간예상` weighted(미포 0.9 · HD현대重 0.2 계열)를 후보로 넣어 격자에서 고른다 — 채택 `ref_base`(미포 0.8182 · HD현대重 0.1818) · 시차 1 · 4분기 이동합 · 창 8 · r 0.9111(단일검정 임계 0.7067) · 비례계수 0.0507; 미포는 2025Q4 부터 HD현대重에 합병돼 체인링크(`driver.merger_rule`). 풍력/LNG-LPG 는 레퍼런스 가정을 `modules` 로 나란히 두고 합산하지 않는다.
- 공통: 판관비율(최근 4분기 중위), 이자손익(평균 잔액 × CF 이자수취/지급 기반 실측 이자율), 환관련손익(외화 순노출 × Δ기말환율, 노출 공시 없으면 0 + 표기), 법인세율(최근 12분기 유효세율을 5~27% 클립), 지배주주 비중(실측), EPS = 지배NI ÷ 유통주식수, BPS 롤(+NI −배당), DPS 최근 실측 유지. 연결 손익이 없는 분기는 별도로 보충하고 표기(`quality.sep_filled`, 셀 `src`), 비영업손익 급등 분기는 `assumptions.one_offs_detected` + '일회성 의심' 경고만(숫자는 바꾸지 않음).
- 밸류에이션: PER 밴드 × 12M fwd EPS, PBR = ROE/COE(0.09) × BPS, EV/EBITDA(감가상각비 있는 회사만) → lo/mid/hi 구간. 과거 PER 중위가 3~40배 밖이면(턴어라운드 왜곡) 레퍼런스 `TP_PE PB` 예시 밴드 10/15/20배로 대체하고 원값을 `hist_band_raw` 에 보관.
- 항등식: 매출−원가=GP, GP−판관±기타=OP, 세전−법인세=NI, 자산=부채+자본 롤 — 추정 구간은 허용 0.05억, 실적 구간은 매출 1% 초과를 major 로 기록.
- 백테스트: 2025Q2 에서 동결(선표·잔고·고객지수도 동결 시점 정보로 재구성)하고 4분기(2025Q3~2026Q2) 매출·OP WAPE — 실측(`kind:actual`) 분기만 짝을 짓는다. **단일 회사 4분기 — 통계 아님.**

### 3-6. xlsx (`kship_model_xlsx.py`) · 레퍼런스 패치 (`kship_xlsx_patch.py`)
- 생성 xlsx: 시트 `README`·`변수`·`BS연결`·`BS별도`·`subQ`·`SLS`(조선사)·`분기`·`연간예상`·`TP`·`외화`. 레퍼런스 헤더 규약 그대로 — 행1 `4Q21`/연간 숫자, 행4 `2021.12`/`2021.12A`, E열 시작, 4분기 뒤 연간 열, 이름정의 `SUBQH`·`BS연결H`…. 확정 행은 `VLOOKUP($D행, BS연결, MATCH(…))/U`, 추정 행은 `변수` 시트 드라이버 셀 참조(노란 셀, 메모에 역산법·basis). 매출원가·매출총이익·세전·순이익·자산총계·EPS·BPS 는 항등식 수식.
- 레퍼런스 패치: 원본 zip 멤버를 바이트 그대로 옮기고 BS 시트의 새 기간 열(2023Q4~2026Q2, 세진·삼성重; 미포는 2025Q1~2025Q3)에만 셀을 끼운다. 기본 동작은 기존 값 셀 **무변경 + conflicts 보고**, 행3 `UPDATE: 26-09-30`, 이름정의 `종가`·라벨은 명시 허용 교체, `calcPr fullCalcOnLoad`. 2차(V6)에서 옵트인 두 가지를 붙였고 **현재 패치본 3개는 둘을 켠 산출**이다(§5-6): `--overwrite-placeholders` — 새 기간 열에 애널리스트가 미발표 분기용으로 넣어 둔 가이던스·잠정치 셀을 fin 실적으로 바꾸고 원문을 보고 `sheets[].replaced[].was` 에 보존(삼성重 4Q23·2023A 11셀: 매출액 8,009,400 → 8,009,429.91 · 영업이익 233,300 → 233,344.77 · 세전 −295,700 → −295,712.43 · 당기순이익 −155,600 → −155,556.38 · 지배NI −155,600 → −148,272.72 등; 미포 1Q25 잠정 9셀: 매출액 1,183,800 → 1,183,823.02 · 매출원가 1,076,800 → 1,076,844.94 · 영업이익 68,500 → 68,484.09 등; 세진 0 = **20셀**). 공유수식 그룹은 그룹 전 셀이 함께 바뀔 때만(앵커만 지우면 의존 셀이 고아). `--fx-actuals` — `변수` 환율 8행의 같은 기간 열(세진·삼성重 14열 = 112셀, 미포 3열 = 24셀)에 남은 애널리스트 가정을 fx.json 실측으로 교체(예: 삼성重 원/달러 평균 2024Q2 1,305 → 1,371.28), 행 배율은 과거 실적 구간 시트값/fx 중앙값 비율(레퍼런스 ` 원/100Y` 행은 라벨과 달리 원/엔이라 0.01), `partial` 분기(2026Q3~)는 건드리지 않음, 전후는 `fx.replaced[]`. 미포 출력이 `_2025Q3` 인 이유: 2025Q4 부터 HD현대重 합병으로 보고서가 없어 fin 마지막 분기가 2025Q3 이고 target 기본값이 그것(prices 에도 010620 이 없어 종가 셀은 `error`). 검증(`--verify`): ① zip 무결 ② 재오픈 시트·수식 수 원본과 동일(교체한 수식 자리표시자 — 삼성重 6 · 미포 3 — 만 감소 허용) ③ 패치 셀 목록 ④ 원본 셀 전부 동일(교체 셀은 반드시 새 기간 열 안 — 보고의 replaced 를 그대로 믿지 않는다) ⑤ subQ VLOOKUP 사슬을 파이썬으로 흉내내 새 분기 `매출액(수익)` == fin.

### 3-7. 페이지 (`kship_model_section.py`)
회사 페이지 하단 「실적 모델」 섹션 8개(KPI 스트립 · 분기 손익표 8A+10E · 사업부 차트 · 조선사 선표/코호트 차트 · 가정 패널 · 밸류에이션 스트립 · xlsx 다운로드 · 각주). 모델 json 이 없으면 **섹션을 만들지 않는다**(빈 칸으로 흉내 내지 않음). 허브 `models.html` 은 모집단 57행 표(정렬·검색; 미포는 모집단 밖이라 없음) + `index.html` 칩. 섹션이 붙은 회사 페이지 57장(조선사 5 · 지주 1 · 엔진 5 · 기자재 41 · 강재 5) — 9/12 모집단 회귀로 1차 빌드 때 40장에만 붙던 것이 복구 뒤 57장. **단, 페이지(21:28~21:39)·허브(21:39)는 모델 재빌드(21:47) 전 산출이라 28장·허브 21행이 이전 모델 값**(KCC 페이지 FY2026E 매출 66,191억 vs 현재 모델 77,851억) — §7 ⑥ 재실행.

## 4. 가정 표 (전부 파일에 `kind:estimate`/`basis` 로 박혀 있다)

| 가정 | 값 | 근거 | 위치 |
|---|---|---|---|
| 헤지비율 | 0.7 (한화오션만 실측 0.1717) | 레퍼런스 SLS 시트 HEDGE 70% / 한화 2026Q2 위험관리 절 약정환율 | `sls/<stock>.json` `hedge` |
| 헤지환율 | 계약별 수주시점 환율(약정환율 미공시 시) | fx.json 분기 평균 | `sls` `contracts[].fx_at_sign` |
| 선표 곡선 | linear (계약기간 균등) | 진행률 공시 없음 | `sls` `curve` |
| 코호트 OPM | ①−5% ②0 ③5 ④10 ⑤15 | 레퍼런스 코호트 구조에 대입한 가정 | `sls` `cohort_opm_table` |
| 코호트 판정 | 원장 내부 상대(year_index 2024 1.0 · 2025 1.0056 · 2026 0.9299) | 신조선가 지수 미보유 | `sls` `year_index` |
| 환율 forward | flat_last_end — 1,353.36원 (2026-09-29) 을 2028Q4 까지 | ECB 마지막 관측 | `fx.json` `forward` |
| 법인세율 | 최근 12분기 유효세율을 5~27% 클립 (삼성重 5%·세진 19.1%) | 레퍼런스 r291 | 모델 `assumptions.tax_rate/tax_basis` |
| 판관비율 | 최근 4분기 중위 (삼성重 4.46%) | subQ `/SALES` | `assumptions.sga_ratio` |
| 고객 연동 채택 | 격자(가중치 후보 × 시차 0~4 × 창 8/12/19 × 수준·YoY·4Q합) 최대 상관 ≥ 0.30 · 원점 회귀 | 세진 `연간예상` weighted 방식 + F2 격자(다중비교 보정 없음 — 과적합 경고 동봉) | `segments[].driver.corr/grid/significance` |
| 코호트 캘리브레이션 | 실측 OPM − 코호트 타겟 중위(삼성重 +3.59%p · 한화오션 +4.39 · HD현대重 +6.41 · HJ +4.32 · 대한조선 +22.46 · 지주 +10.32) | fin 연결 OPM | `sls` `calibration.calibrated_shift` |
| 성장·OPM 클립 | 성장 −30~+50%, OPM −20~+40% | 폭주 방지 | `kship_model.py` 상수 |
| COE | 0.09 | 레퍼런스 `TP_BPS` | `valuation.coe` |
| PER 밴드 | 과거 분기 PER 25/50/75 백분위; 중위가 3~40배 밖이면 10/15/20배 | 레퍼런스 `TP_PE PB` 예시 | `valuation.per_band` |
| 배당 | 최근 실측 DPS 유지 (세진 225원) | fin `dividend` | `rows.DPS` |
| 백테스트 | freeze 2025Q2 · 4분기 | — | `backtest` |
| 단위 | 억원(=백만원/100), EPS·BPS·DPS 원, PER/PBR 배 | 레퍼런스 subQ `U=100` | 전 파일 `unit` |

## 5. 검증 — 2026-09-30 실측

### 5-1. 골든 대조 (우리 DART 파서 vs 레퍼런스 BS 시트 FnGuide 값, 겹치는 전 기간, ±3 백만원)
| 회사 | match / compared | 비율 | 분기 | checks 실패 |
|---|---|---|---|---|
| 삼성중공업 010140 | 1,291 / 1,387 | 93.1% | 19 (2021Q4~2026Q2) | 4/124 (전부 `cf_abs_nonneg` — 연간 vs 9M 표시 차이) |
| HD현대미포 010620 | 1,909 / 2,011 | 94.9% | 16 (2025Q4·2026Q1·Q2 `no_report` — HD현대重 합병 소멸) | 0/112 |
| 세진중공업 075580 | 1,031 / 1,254 | 82.2% | 19 | 6/133 (`cf_abs_nonneg` 3 · `ytd_diff==3m` 3) |
| 일승 333430 | 533 / 581 | 91.7% | 19 (2021Q3 연결 없음) | 3/131 (`ytd_diff==3m` 2 · `cf_abs_nonneg` 1) |
| 동방선기 099410 | 392 / 428 | 91.6% | 19 (연결 없음 — sep 만) | 2/66 (`cf_abs_nonneg`) |
| **합계** | **5,156 / 5,661** | **91.1%** | | 1차 5,150 / 91.0% — 세진 81.7 → 82.2%(계속사업이익 오매핑 수리: FY2021 16,380.39 → 14,060.0 · 2021Q4 −10,998.72 → −9,705.37 = FnGuide) |

57사 전체 수집(17:45 KST 완주) → 파서 수리 후 21:18 KST `--build --all` 재빌드(캐시만, DART 무접촉): fin json 58개(57 + HD현대미포), `fin_collect.log` FAIL 0, 캐시 128MB(58 폴더). 분기 19 미만 10사의 사유(reports/issues + 캐시 meta + DART A001 검색 1회로 확정): HD현대미포 16(2025Q4~ 합병 소멸) · 범한퓨얼셀 17(2022-06 상장) · 한선엔지니어링 11(2023-10 상장) · 현대힘스 11(2024-01 상장, FY2023 사업보고서부터) · HD현대마린솔루션 9(2024-05 상장) · 삼미금속 8(코넥스 — 분·반기 면제, 사업보고서 FY2022~ + 2025 코스닥 이전 뒤 반기부터) · 대한조선 5(2025 상장) · 원일티엔아이 5(2025 상장) · 티엠씨 4(2025 하반기 상장) · 케이앤에스아이앤씨 1(2026 상장, 2026Q2 반기만) — 전부 `issues.no_report`. issues 합계(21:18): borrowings_face_label 551 · no_cons_statements 179 · sga_absorbed_op_lines 162 · shares_omitted_quarterly 138 · no_report 103 · tax_sign_flipped 93 · expense_sign_negative 91 · duplicate_label 83 · no_prior_ytd_cf 4 · no_prior_ytd 3(shares_table_not_found 55 → 0). 항등식 1% 초과 불일치(매출−원가=GP · GP−판관+기타영업=OP) 40+건 → 0건. §5-4 의 모델은 이 fin 으로 21:47 재빌드했다.

불일치의 원인(세진 최악 기간 `cons:2022.09` 39/65, `sep:2023.06` 48/58, `sep:2022.09` 48/60 의 상위 항목): 단기차입금 208,983 vs FnGuide 57,854 — 세진·일승은 face 에 '단기금융부채'(차입금 총액)만 있고 FnGuide 는 **주석**으로 단기차입금 + 유동성장기부채로 분해한다. face 만으로는 불가능해 전액 단기차입금으로 두고 `issues.borrowings_face_label` 로 표기했다. 그 외 매출채권및기타채권/단기금융자산·자본잉여금/기타자본 등 **같은 금액이 짝으로 어긋나는** 항목은 대여금·미수수익·자기주식처분이익 등 FnGuide 의 주석 기반 재분류다. 스펙 §2-1 의 '주석 선택 파싱'을 붙여야 좁혀진다(미착수). 삼성重 잔여도 같은 부류 — 2023.09 별도 자본잉여금 1,969,727 vs FnGuide 4,496,029 · 기타자본 1,556,045 vs −970,257(재평가잉여금·자기주식 분해; 기타포괄까지 세 항목 합은 4,586,102 vs 4,586,103 으로 같음).

### 5-2. 선표(SLS) — 6사, origin 2026Q2, 창 2026Q3~2028Q4
| 회사 | 계약(계수) | 창 합계 백만$ | 헤지적용 원화 백만원 | 2026Q3 백만$ → 원화 (적용환율) | 타겟 OPM 2026Q3 | 화해 ratio 4Q 중위 | 잔고 커버리지 | 헤지 |
|---|---|---|---|---|---|---|---|---|
| 삼성중공업 | 51(48) | 14,784.7 | 21,031,477 | 1,663.0 → 2,388,135 (1,436.04) | 6.42% | 0.612 | 0.623 | 0.7 가정 |
| 한화오션 | 34(34) | 10,378.4 | 14,317,276 | 1,092.7 → 1,561,073 (1,428.70) | 6.48% | 0.208 | 0.408 | **0.1717 실측** |
| HD현대중공업 | 43(43) | 14,253.0 | 20,344,769 | 1,558.3 → 2,243,576 (1,439.80) | 6.32% | 0.238 | 0.379 | 0.7 가정 |
| 대한조선 | 16(16) | 1,907.6 | 2,709,912 | 223.6 → 320,620 (1,433.73) | 4.53% | 0.539 | **1.164** (원장 잔여 27,541억 > 공시 잔고 23,665억 — 배율 상한 1 권고) | 0.7 가정 |
| HJ중공업 | 45(45, 공사 41) | 2,192.6 | 3,076,170 | 241.7 → 337,520 (1,396.38) | 4.65% | 0.227 (2026Q2 1개만 유효) | 0.518 | 0.7 가정 |
| HD한국조선해양(지주) | 41(20 — 21건 HD현대重 공유 제외) | 5,348.4 | 7,633,275 | 554.1 → 799,472 (1,442.82) | 4.95% | — | — | 0.7 가정 |

21:08 재빌드(`kship_sls.py`)에서 `calibration.calibrated_shift`(fin 연결 OPM − 코호트 타겟, 중위)가 채워졌다: 삼성重 +3.59%p · 한화오션 +4.39 · HD현대重 +6.41 · HJ +4.32 · 대한조선 +22.46 · 지주 +10.32(1차는 fin 부재로 null). `shared_pairs_n` 21 · `dropped_superseded` 0 · `fx_const` 1,350. sls 는 fin 21:18 재빌드보다 10분 앞선 산출 — 캘리브레이션이 읽는 조선사 연결 OPM 은 이번 수리 대상(비용 음수 표기 9사 · 중단영업 Q4 순이익)에 들지 않지만, 바이트 정합을 위해 §7 순서대로 ③을 다시 돌리는 편이 안전하다(값 불변은 미확인).

### 5-3. 환율·시세
- `fx.json`: 분기 87(2005Q1~2026Q3), 연간 22, forward 10분기, 일별 캐시 5,566일. **2026Q2 원/달러 평균 1,501.75 · 기말 1,550.89**(62일, 스펙 확인값과 일치), 원/100엔 942.16/954.75, 원/유로 1,746.09/1,767.09, 원/위안 220.80/228.56. 2026Q3 는 65일 부분(`partial:true`, 평균 1,419.72 · 기말 1,353.36). 네이버 대조: 2026Q2 기말 +0.187%, 최근 공통일 9/29 −0.01%.
- `prices.json`(21:10 재실행, as_of 2026-09-30): 57/57 성공 · 0 실패, 이력 57(`--no-history` 라 직전 파일에서 이어붙임 `history_meta.carried_from: 2026-09-30`; 삼성重 행은 토스 일봉 1,394개 2021-01-21~2026-09-30). 삼성重 종가 19,330원(2026-09-29), PER(TTM) 30.6 · PBR 3.61; `naver_check` 네이버 정규장 종가 19,500(−0.87%), `close_check` 9/28 토스 20,150 vs aik 20,100(+0.25%). 전체 `naver_check`: 57종목 중 같은 값 8 · 1% 초과 8 · 최대 −3.45%(079430, aik 5,600 vs 5,800) — 시가·고가·저가·거래량은 같고 종가만 다르다. 정본은 계약대로 aik `close`, 어느 쪽이 '확정'인지는 판정하지 않는다(§6-15). 레퍼런스 패치본(21:06)은 그 직전 prices(9/28 20,100)를 썼다.

### 5-4. 모델 (`assets/models/summary.json`, built 2026-09-30 21:47 — 수리된 fin 58사 · sls 21:08 · prices 21:10)
- 58행(57 + fin 만 있는 HD현대미포): **full 29 · partial 29 · no_fin 0**(1차 full 5 · partial 32 · no_fin 21). 회사 단위 드라이버: `customer_yard_revenue_weighted` 29(1차 7) · `trend_seasonal` 23 · `sls_marine_plus_uncovered_backlog_runoff` 5(조선사) · `subsidiary_yard_scaled` 1(지주). partial 사유(중복 집계): 감가상각비 미파싱 → EBITDA·EV/EBITDA 미산출 46 · 매출 드라이버 폴백(고객 연결 없음) 22 · 잔고 소진분만 5 · 부문>연결 경고 2(삼성重) · 지배NI 파생 2 · 일회성 의심 1. **실적 항등식 major 불일치 0사**(1차 8사 — fin 비용 부호 수리로 해소, `quality.identity_mismatches` 빈 목록). PER 밴드 `hist_quarterly`(토스 이력) 38 · `sector_default` 20; 환관련손익 노출 공시 2사(HD현대重·대한조선).
- 삼성중공업(full, yard): FY2025A 매출 106,500억 / OP 8,622 / EPS 639원 → **FY2026E 129,892 / 12,838 / 1,126 → FY2027E 135,096 / 13,570 / 1,487 → FY2028E 113,141 / 11,412 / 1,264**(1차와 동일 — 조선사 fin 은 수리 대상이 아니었다). OPM 2026E 9.9%. 2026Q2 매출 32,307.12억 = fin 3,230,712.01백만/100. PER(now) 12.96배(종가 19,330원 9/29 · 12M fwd EPS 1,491.6원) · PBR 3.46 · ROE fwd 26.7% · 적정 PBR 2.97 · PER 구간 14,900/22,400/29,800원(밴드 sector_default — 과거 PER 중위 46.2배가 3~40 밖). 법인세율 5%(12분기 유효세율 −65.5% 클립) · 판관비율 4.46%. 실적 항등식 76건·추정 50건 전부 통과.
- 세진중공업(**full**, equip): FY2025A 4,027 / 734 / 892원 → FY2026E 4,134 / 732 / 981 → FY2027E 4,872 / 821 / 942 → FY2028E 4,739 / 799 / 935. 드라이버 고객 연동 채택(1차는 HD현대重 fin 부재로 추세 폴백): 가중치 `ref_base`(미포 0.8182 · HD현대重 0.1818) · 시차 1 · 4분기 이동합 · 창 8 · r 0.9111 · 비례계수 0.0507. 연결 = 별도 + 일승 + 동방선기 + 연결조정. PER 10.86 · PBR 2.22 · 밴드 hist_quarterly 15분기 16,800/19,400/24,200원. 법인세율 19.1% · 판관비율 6.13% · DPS 225원 유지.
- 조선사: 한화오션(full) FY2025A 127,835 / 11,676 → FY2026E 169,951 / 20,872, PER 14.87 · PBR 3.20 · HD현대중공업(full) 175,806 / 20,375 → 254,552 / 36,224, PER 17.21 · PBR 4.27 · HJ중공업(full) 19,997 / 671 → 25,135 / 2,018, PER 6.87 · 대한조선(partial — 2025 상장으로 FY2025A 없음) FY2026E 13,087 / 3,522 · HD현대미포(partial, 추세, last_actual 2025Q3, 시세·SLS 없음) FY2026E 62,971 / 2,068.
- HD한국조선해양(**full**, holding, `subsidiary_yard_scaled` — 1차는 329180 fin 부재로 추세): FY2025A 299,332 / 39,045 / EPS 30,664원 → FY2026E 356,868 / 56,744 / 54,398, PER 6.71 · PBR 1.54.
- 기자재 격자 채택 예: KCC(002380) 시차 4 · 창 12 · 4Q합 r 0.63 → FY2026E 매출 77,851억(페이지는 아직 이전 모델 66,191억 — §3-7) · 오리엔탈정공 시차 0 · 창 19 r 0.95 · 케이프 시차 0 · 창 8 r 0.94.

### 5-5. 백테스트 (freeze 2025Q2 → 2025Q3~2026Q2 4분기 WAPE, n=56 — 티엠씨·케이앤에스아이앤씨는 freeze 이후 실적 없음)
매출 WAPE **중위 15.6%**(최소 1.5% 현대힘스 · 최대 62.3% 삼영엠텍), OP WAPE **중위 57.7%**(최소 0.8% 하이록코리아 · 최대 622.3% 화인베스틸). 삼성重 6.5 / 13.2 · 세진 6.6 / 55.0 · 한화오션 17.8 / 51.0 · HD현대重 24.0 / 44.4 · HD한국조선해양 9.8 / 34.4 · 대한조선 11.4 / 26.4 · HJ 19.4 / 100.0 · HD현대미포 3.5 / 85.0(n=1). 1차(fin 37사) 중위 14.6 / 59.2 에서 모집단이 56사로 늘며 바뀐 값이다. 소형주 OP 는 분기 한 건의 일회성으로 세 자리 %가 난다 — 그대로 보고하며 통계로 읽지 않는다.

### 5-6. xlsx · 테스트
- 생성 xlsx 58개(5.5MB, 21:47). `010140_model.xlsx` 129,725 bytes · 시트 10 · 수식 3,408 · 이름정의 9; `075580_model.xlsx` 113,691 bytes · 시트 9(SLS 없음) · 수식 3,632 · 이름정의 8; `009540_model.xlsx` 121,453 bytes. 재오픈(openpyxl) 통과, 같은 입력이면 바이트 동일(BS 행3 스탬프·문서 속성·zip 엔트리 시각을 모델 built_at 으로 고정 — 2차 확인). **Excel 실개봉은 미확인**(LibreOffice/Excel 없음 — 자체 수식 계산기로 VLOOKUP·추정 재계산만 검증).
- 레퍼런스 패치 3개(21:06, `--all --verify --overwrite-placeholders --fx-actuals --today 2026-09-30`, 원본 `*_orig.xlsx` 무손상):

  | 파일 | BS 새 기간 열 | BS 패치 셀 | 자리표시자 교체 | `변수` 환율 교체 | 종가 | 검증 ② 수식 수 | zip 멤버 |
  |---|---|---|---|---|---|---|---|
  | `세진중공업_075580_subQ_2026Q2.xlsx` (3,830,863 bytes) | 2023Q4~2026Q2 (14열) | BS연결 1,059 · BS별도 959 · BS일승(별도) 935 · BS동방선기(별도) 804 = 3,757 | 0 | 112 (8행 × 14열) | `TP_PE PB!B1` 9,990원(9/28) | 60,271 = 60,271 | 218 중 210 동일 |
  | `삼성중공업_010140_subQ_2026Q2.xlsx` (2,724,551) | 2023Q4~2026Q2 (14열) | BS연결 1,181 · BS별도 1,051 = 2,232 | **11**(4Q23·2023A 가이던스 — 매출액 CS69/CT69 · 영업이익 · 세전 · 법인세 · 당기순이익 · 지배NI) | 112 | `TP_BPS!C1` 20,100원(9/28) | 91,976 → 91,970 (−6 = 교체한 수식 자리표시자) | 148 중 142 동일 |
  | `HD현대미포_010620_subQ_2025Q3.xlsx` (5,520,402) | 2025Q1~2025Q3 (3열) | BS연결 208 · BS별도 187 = 395 | **9**(1Q25 잠정 — 매출액 · 매출원가 · 매출총이익 · 판관비 · 영업이익 · 세전 · 법인세 · 당기순이익 · 지배NI) | 24 (8행 × 3열) | 없음(prices 에 010620 없음 → `error`) | 88,706 → 88,703 (−3) | 218 중 213 동일 |

  검증 ①zip ②재오픈 ③패치 셀(3,871 · 2,346 · 419) ④원본 셀 동일(허용 예외만) ⑤subQ VLOOKUP 사슬 == fin 전부 ok. 교체 전 원문은 보고 `sheets[].replaced[].was`·`fx.replaced[].was_value` 에 있다(1차는 삼성重 1개, 표본 fin 기반). 종가 셀은 prices 21:10 재실행 전 값(9/28) — ⑤를 다시 돌리면 19,330(9/29).
- `python -m unittest discover -s tests -p 'test_*.py'`: **245 tests OK**(skipped 1, 26.8s) — fin 35 · fx 18 · sls 24 · model 42 · xlsx 19 · patch 45 · section 28(skip 1) · 기존 kship 21 · scan 13. 1차 162 → 2차 245(검증 레인이 잡은 결함마다 테스트 추가; 세션 중 한때 실패했던 `TestHub.test_build_models_hub_with_mocks`(td 20 ≠ th 21)는 L7 수리로 통과).

## 6. 한계 — 숫자를 읽기 전에

1. **진행률 vs 인도**: SLS 는 계약기간 선형 배분 모형이지 회계 진행률 매출이 아니다. 과거 분기도 `kind:estimate` 로 둔다. 원장이 2024~ 공시분이라 화해 ratio(한화 0.21·HD현대重 0.24)가 낮고, 미래 배율은 잔고 커버리지를 쓴다.
2. **코호트는 가정**이다 — OPM 표도, 등급 판정(원장 내부 상대지수)도. 2021 이후 절대 신조선가 호황을 반영하지 못한다. 외부 지수 도입은 사용자 결정.
3. **2028 매출은 2026Q2 잔고 소진분만**(신규 수주 미포함). 삼성重 FY2028E 113,141억 감소는 이 한계다. forecast_panel 신규수주 시나리오는 모듈로 나란히 둘 뿐이다.
4. **밸류에이션은 추천이 아니다.** PER 밴드는 대부분 sector_default(10/15/20배)이고, 삼성重 과거 밴드 원값은 43.5~79.1배(턴어라운드 왜곡).
5. **감가상각비·이자수익/비용·외환차손익·파생손익이 face 에 없는 회사가 대부분**(삼성重·미포 전 분기 null) → EBITDA·EV/EBITDA null, 이자율은 CF 이자수취/지급으로 대체, 일회성 분리 없음(`one_offs` 항상 []). 주석 파서가 후속이다.
6. **골든 91.1%** 의 나머지 8.9%는 FnGuide 주석 재분류(§5-1 — 자본잉여금/기타자본/기타포괄 분해, 단기금융부채 → 단기차입금/유동성장기부채, 대여금·미수수익). 세진 82.2%. 스펙 §2-1 '주석 선택 파싱' 없이는 좁혀지지 않는다.
7. **3개월 열 vs 누적 차분**: 우리는 보고서 '3개월' 열, FnGuide 는 누적 차분 — `checks.ytd_diff==3m` 실패 34건(매출 8 · 영업이익 13 · 당기순이익 13)은 전부 후속 보고서의 전기 재작성(정정·중단영업 재분류)이다: 두산에너빌리티 2022Q2 매출 −66,975 · KCC 2026Q2 −16,733(중단영업 첫 분류로 Q1 재작성) · KS인더스트리 2024Q2 −10,338 · 일승 2024Q2 −2,163 · 세진 2022Q3 +163 등. 어느 쪽이 정본인지 오너 결정 필요.
8. **HD현대미포**는 2025Q4 부터 보고서 없음(합병) → last_actual 2025Q3, 시세 없음, SLS 없음 — 참고용 partial.
9. **yards_cache 부문 매출 잡음**: 삼성重 2025Q2 조선 부문 31,509억 > 연결 매출 26,830억(2022Q1 도) — 부문표/파서 문제로 보이며 조선 부문 실적 행에 그대로 들어간다(경고 기록). yards 레인 확인 필요.
10. 주식의 총수는 분기보고서에 생략된 경우가 많아 직전 값 이월(`kind:estimate` + `carried_from`, 138건). KCC(002380)는 표가 없는 게 아니라 열 머리가 '의결권 있는 주식/없는 주식/합계'라 못 읽던 것 — 2차 수리로 19분기 전부 파싱(2026Q2 발행 8,592,896 · 자기 1,238,725 · 유통 7,354,171 = aik shares_outstanding 과 일치), aik 폴백 불필요.
11. GitHub Actions 러너에는 토스 일봉이 없어 `history_quarterly` 를 새로 만들 수 없다 — 워크플로가 직전 커밋의 이력을 이어 붙이고 `history_meta.carried_from` 을 남긴다(§8).
12. 환관련손익은 환위험표 '순 노출' USD 를 공시한 조선사(HD현대重·대한조선)만 — 2026Q3 는 Δ기말환율 −197원이라 큰 손실이 찍힌다. 헤지회계(OCI) 반영분은 알 수 없다.
13. **face 자체 오류는 그대로 둔다**: HD현대마린엔진(071970) 2025Q3 별도 재무상태표 자산총계 641,451.93 ≠ 부채 285,930.30 + 자본 355,594.63 = 641,524.93(73백만원 차, 유동+비유동 = 자산총계는 맞음) — 회사 공시 불일치, `checks.assets=liab+equity` 실패 1건으로 남김. 한국주강(025890) 2023Q2 별도 세전−법인세=순이익 −2.05 도 같은 부류.
14. **삼미금속(012210, 코넥스)** 은 2022Q4·2023Q4 가 사업보고서만 있어 9M 누적이 없다 → 그 분기 3개월 손익 없음(`issues.no_prior_ytd` 3 · `no_prior_ytd_cf` 4), BS·is_ytd 만. 모델은 이 회사를 연간 기준으로만 읽어야 한다.
15. **aik `close` 는 네이버·토스 정규장 종가와 다를 수 있다**(9/29 기준 57종목 중 49 상이, 최대 3.45%) — 시가·고가·저가·거래량은 같다. `close` 는 라이선스·T+1 확정 원천 표기 때문에 계약대로 aik 를 두고, 차이는 `naver_check`·`close_check` 에 기록한다. 어느 쪽이 '확정'인지 이 파일은 판정하지 않는다.
16. **모집단은 누적 판정이다**: 9/11 본문 탐색 승격 16사(41→57)를 9/12 주간 스캔(`kship_scan.py --scan`)이 후보 pool 에서 빼고(230→214) `universe_probe.promoted` 를 {} 로 덮어써 `kship_universe.py --write` 가 '탐색' 16행을 지웠다(9/19·9/26 스캔도 0). 정적 페이지 16장만 남아 1차 임베딩 때 모델 섹션이 40장에만 붙는 것으로 발견. 복구(21:35~21:39): `kship_scan.carry_forward`(직전 승격 이월, 강등은 fetch 성공 + 규칙 미달의 명시적 rejected 만, fetch 실패·빈 본문은 failed 보존, `carried_from` 표기) + `kship_universe.py --write` 2차 방어선 → universe 57 · probe promoted 16(carried 16, `carried_from: 2026-09-11`) → `kship_suppliers.py --build` → `kship_parts.py --all`. 주간 크론 커밋에서 모집단 행 수가 줄면 즉시 의심.
17. **하류 산출은 빌드 시각 순서가 계약이다**: 페이지·허브는 모델 json 을 임베드하므로 모델 재빌드 뒤에 반드시 ⑥을 다시 돌린다(현재 28장·허브 21행이 21:47 이전 값 — §3-7).

## 7. 재현 — 명령 순서

DART 를 두드리는 것은 ①만이고 **프로세스 하나로만** 돌린다(같은 시간에 `kship_contracts/yards/suppliers --collect` 도 띄우지 않는다).
②~⑥은 네트워크 없이(②만 ECB·aik) 캐시·산출물로 돈다. 순서가 중요하다 — ② 가 ③보다 앞이어야 SLS 가 fx.json 을 쓰고, ① 이 ④보다 앞이어야 모델이 실적을 쓰고, ④ 가 ⑥보다 앞이어야 페이지가 현재 모델을 싣는다(9/30 21:47 재빌드 뒤 ⑥ 미실행 — §3-7).

```bash
cd argus/kship/tools
PY=~/Library/phalanx_venv/bin/python          # 3.14 + openpyxl 3.1.5, 그 외 표준 라이브러리만

# ① 재무제표 — DART 단일 프로세스. 57사 × 20분기(보조 2021Q3 포함) ≈ 회사당 65초 → 첫 수집 ≈ 60분.
#    캐시(assets/fin_cache/)가 있으면 검색만 하고 건너뛴다. 백그라운드로 두고 진행을 본다.
nohup $PY kship_fin.py --collect --build --all >> assets/fin_collect.log 2>&1 &
tail -3 assets/fin_collect.log; ls assets/fin | wc -l; grep -c FAIL assets/fin_collect.log
$PY kship_fin.py --collect --build --stocks 075580,333430        # 일부만 다시(실패 회사 재개 — 캐시 체크포인트)
$PY kship_fin.py --golden --stocks 075580,010140,010620,333430,099410   # 골든 대조 표 출력(fin json 의 golden 갱신)

# ② 환율·시세 (키 없음)
$PY kship_fx.py                       # ECB → assets/fx.json + fx_daily_cache.json, 네이버 대조. --offline 이면 캐시로만
$PY kship_price.py                    # aik → assets/prices.json (토스 이력은 ~/phalanx/toss_api.py 가 있을 때만)

# ③ 선표 (contracts.json · yards_cache · fx.json → assets/sls/)
$PY kship_sls.py --all --report

# ④ 모델 + 생성 xlsx (fin·fx·prices·sls → assets/models/<stock>.json + summary.json, models/<stock>_model.xlsx)
$PY kship_model.py --build --all --xlsx --today 2026-09-30     # --today 로 built_at 고정 → 같은 입력이면 바이트 동일
$PY kship_model.py --report 010140 075580

# ⑤ 레퍼런스 원본 패치 — 맥미니 로컬 전용(원본 *_orig.xlsx 는 절대 덮지 않는다). 두 플래그는 옵트인(§3-6):
#    --overwrite-placeholders(가이던스·잠정치 20셀 → 실적, 원문은 보고 replaced[].was) · --fx-actuals(변수 환율 실적 분기 교체).
#    빼면 이전 동작(보존 + conflicts 보고). 현재 패치본 3개는 둘을 켜고 만든 것(§5-6). 미포는 fin 마지막 분기라 _2025Q3.
$PY kship_xlsx_patch.py --all --verify --overwrite-placeholders --fx-actuals --today 2026-09-30 --report /tmp/xlsx_patch_report.json

# ⑥ 페이지 — 훅이 assets/models 가 있는 회사에만 섹션을 붙인다. **④ 뒤에 반드시** 다시 돈다(페이지가 모델 값을 임베드).
#    모집단이 바뀌었으면(kship_scan.py --scan|--rejudge → kship_universe.py --write → kship_suppliers.py --build) 그 뒤에.
$PY kship_page.py --all && $PY kship_parts.py --all && $PY kship_model_section.py --hub

# 검증
$PY -m unittest discover -s tests -p 'test_*.py'
$PY kship_model_xlsx.py --model assets/models/010140.json --out /tmp/010140_check.xlsx --verify
$PY kship_model_section.py --check ../010140/index.html
```

빌드 결정론: sls·model·xlsx 는 같은 입력이면 바이트 동일(`built_at` 은 `--today` 로 고정 가능; 생성 xlsx 는 BS 행3 UPDATE 스탬프·문서 속성·zip 엔트리 시각까지 모델 built_at 날짜로 고정). fin json 의 `collected_at`, sls 의 `built_at` 은 실행일이 찍힌다.

## 8. 자동 갱신 — `.github/workflows/update-kship.yml` (매일 10:40 KST)

| 단계 | 하는 일 | 실패 시 |
|---|---|---|
| Tests (before) | kship·kce 단위 테스트 (`openpyxl==3.1.5` 설치 뒤) | job 실패 |
| Restore fin cache | `actions/cache` 에서 `fin_cache/` 복원(원문 HTML 은 git 에 넣지 않는다) | 없으면 빈 캐시 = 첫 수집 ≈ 60분 |
| Collect and build | 기존: universe · 계약 · 정기보고서(yards) · 기자재 · 사전 | continue-on-error |
| Financial statements | `kship_fin.py --collect --all --quarters 2021Q4..<기대 최신분기>` — 기대 분기는 분기말 +50일(사업보고서 +95일)로 계산, `quarter` 입력이 있으면 그것. 최신 2분기의 '보고서 없음' meta 는 지워 다시 찾는다(늦은 접수). **캐시 파일 목록이 바뀐 회사가 있을 때만** `--build --all` | continue-on-error, 회사 단위 재개 |
| Save fin cache | 바뀌었을 때(또는 단계 중단 시) 새 캐시 항목 저장 | always |
| FX and prices | `kship_fx.py` · `kship_price.py`, 직전 커밋 `prices.json` 의 `history_quarterly` 이어 붙임(`carried_from`) | continue-on-error |
| Models | 월요일 · fin 변경 · `models=true` 입력 · summary.json 부재 중 하나면 `kship_sls.py --all` → `kship_model.py --build --all --xlsx` (매일 돌리면 json 4.4MB + xlsx 3.5MB 가 날마다 git 이력에 쌓인다) | continue-on-error |
| Pages | `kship_page.py --all` · `kship_parts.py --all` · `kship_model_section.py --hub` · `inject_link.py --apply` | continue-on-error |
| Commit | `argus/kship` + `argus/index.html` — `fin_cache/`·`fin_collect.log` 제외 | 변경 없으면 no-op |
| Fail if errored | 어느 단계든 실패면 job 을 실패로 표시(성공한 산출물은 이미 커밋) | |

DART 는 이 job 안에서 순차 한 프로세스이며 `concurrency: kship-dart`(scan-kship 과 같은 그룹)로 다른 워크플로와도 겹치지 않는다. 주간 `scan-kship.yml` 은 워크플로 파일은 그대로고 스캐너(`kship_scan.py --scan`) 자체가 직전 승격을 이월하도록 바뀌었다(§6-16). `update-kship.yml` 은 17:42 1차 산출 그대로(2차에서 미수정).

## 9. 파일 지도

```
argus/kship/
  MODEL_SPEC.md              설계 계약(스키마·계정명 73·레인·회사 특유 파라미터)
  MODEL.md                   이 문서
  models.html                섹터 허브(57행)
  models/<stock>_model.xlsx  생성 xlsx 58개(fin 이 있는 회사 57 + HD현대미포, 5.5MB)
  <stock>/index.html         회사 페이지 — 하단 「실적 모델」 섹션(모델 있을 때만)
  tools/
    kship_fin.py             DART 재무제표 → assets/fin/<stock>.json (fin_cache/ 원문 캐시, fin_collect.log)
    kship_fx.py              ECB → assets/fx.json (+fx_daily_cache.json)
    kship_price.py           aik → assets/prices.json
    kship_sls.py             선표 → assets/sls/<stock>.json + summary.json
    kship_model.py           모델 엔진 → assets/models/<stock>.json + summary.json (--xlsx 로 xlsx 까지)
    kship_model_xlsx.py      모델 json → xlsx (--verify 재오픈·VLOOKUP·추정 재계산)
    kship_xlsx_patch.py      레퍼런스 원본 제자리 패치(로컬 전용)
    kship_model_section.py   섹션 렌더러 · models.html 빌더 · --check 태그 균형
    kship_page.py / kship_parts.py   _model_section 훅(가드 — 모델 없으면 섹션 없음)
    tests/test_kship_{fin,fx,sls,model,model_xlsx,xlsx_patch,model_section}.py
    tests/fixtures/fin/      DART 절 HTML 픽스처 4세트 + golden_fnguide.json(레퍼런스 BS 시트 값)
    kship_scan.py / kship_universe.py   모집단 ④ 본문 탐색(carry_forward 이월) · universe.json 쓰기(2차 방어선)
    tests/test_kship_scan.py             이월·강등 규칙 13건(DART 없이)
(레포 루트) .gitignore       argus/*/tools/assets/fin_cache/ · fin_collect.log · **/.collect.lock — 9/30 20:48 추가(원문 캐시 128MB·로그·락은 커밋 안 함)
~/phalanx/jem_data/kship_models/reference/   레퍼런스 원본(*_subQ_orig.xlsx) + 패치본(*_subQ_2026Q2.xlsx) — 레포 밖
```

## 10. 2차 검증·수정 기록 (2026-09-30 20:40~21:50 KST — 실측)

1차 구축(17:45) 산출을 레인별 검증자가 다시 열어 결함을 제자리에서 고치고 테스트를 붙였다(162 → 245). 아래는 fin 검증(V1) 보고 원문과 각 도구의 머리말·산출물에서 확인한 것이다.

| 대상 | 고친 것 | 증거(산출물) |
|---|---|---|
| fin — `kship_fin.py` (V1) | `EXPENSE_KEYS` + `normalize_expense_signs()` — 비용 괄호(음수) 표기 9사 91표 정규화(`expense_sign_negative`), 귀속 블록 계속·중단영업이익 오매핑 수리(세진 FY2023, KCC '계속영업반기순이익'), 중단영업이 연간에만 있을 때 Q4 규칙, 영업비용 줄 판관비 흡수(`sga_absorbed_op_lines`), `parse_shares` 열 머리('의결권 있는 주식'·'-')·생략 오탐 수리 | 항등식 1% 초과 40+ → 0 · `pretax-tax=ni` 실패 10 → 1 · `tax_sign_flipped` 214 → 93 · `shares_table_not_found` 55 → 0 · 골든 5,150 → 5,156 · 성광벤드 2024Q4 매출원가 −258,551 → 42,757.68 · 010140 2025Q4 Q4 도출 검산(연간 − 9M, 원문 표 직접 추출) 일치 · DART 접촉 1회(삼미금속 A001 검색) |
| fx·price — `kship_fx.py`·`kship_price.py` | forward 루프 종료 조건(`q <= q_to`) · 이력 창을 분기 첫날로 정렬 · `naver_check`(종가 대조) · 이력 이어붙임 `carried_from`/`--no-carry` | prices 21:10 재실행 57/57, naver 49/57 상이(최대 3.45%); fx.json 미변경(16:21) |
| sls — `kship_sls.py` | 캘리브레이션 실측(`calibrated_shift`, fin 연결 OPM) · `shared_pairs_n`·`dropped_superseded` 표기 | summary 21:08 — 삼성重 +3.59%p … 대한조선 +22.46 |
| model — `kship_model.py` (F2) | 고객 연동 **격자 탐색**(가중치 후보 × 시차 0~4 × 창 8/12/19 × 수준·YoY·4Q합, p<0.05 임계·과적합 경고 `driver.grid/significance`) · 지주 실측 비율(`subsidiary_yard_scaled`) · 별도 보충(`sep_filled`) · 일회성 탐지(`one_offs_detected`, 숫자 불변) · 백테스트를 동결 시점 정보·실측 분기만으로 · `--today` | summary 21:47 full 29 · partial 29 · no_fin 0, 고객 연동 7 → 29사, major 불일치 8 → 0사 |
| xlsx 생성 — `kship_model_xlsx.py` | 결정론 — 스탬프·문서 속성·zip 엔트리 시각을 built_at 으로 고정 | 58개 21:47, 두 번 생성 해시 동일(테스트) |
| xlsx 패치 — `kship_xlsx_patch.py` (V6) | `--overwrite-placeholders`(공유수식 그룹 보호, 수식 감소 허용분 계산) · `--fx-actuals`(행 배율 자동, partial 제외) · `--today` · 검증 ④ 강화(교체 셀은 새 기간 열 안이어야 — 보고를 믿지 않음) · 미포 `_2025Q3` 사유 명시 | 패치본 3개 21:06 검증 ①~⑤ ok(§5-6), 교체 20셀 |
| 섹션 — `kship_model_section.py` (L7) | 허브 표 th/td 열 수 불일치(20 ≠ 21) 수리 | `test_build_models_hub_with_mocks` 통과, 섹션 57장 |
| 모집단 — `kship_scan.py`·`kship_universe.py` | `carry_forward`(승격 이월 · 명시적 강등만 · fetch 실패 보존 · `carried_from`) + `--write` 2차 방어선 → probe promoted 16 복구 → suppliers 재빌드 → 기자재 51장 재생성 | universe 57(탐색 16), `tests/test_kship_scan.py` 13건, 섹션 40 → 57장 |
| 레포 | 루트 `.gitignore` 에 `argus/*/tools/assets/fin_cache/` · `fin_collect.log` · `**/.collect.lock` | 20:48 |

**남은 것**
- 하류 stale: 회사 페이지 28장 · 허브 21행(§3-7) — §7 ⑥ 재실행. sls 는 fin 재빌드보다 10분 앞 — ③ 재실행 권고(캘리브레이션 값 불변으로 보이나 미확인).
- 레퍼런스 패치본 종가 셀은 9/28 20,100(9/29 19,330 이 있는 prices 21:10 이전) — ⑤ 재실행 시 갱신.
- 골든 잔여 8.9%: 주석 재분류(§6-6) — 스펙 §2-1 주석 파싱 착수는 오너 결정.
- face 자체 오류 1건(HD현대마린엔진 2025Q3 별도 73백만원)·한국주강 2023Q2 −2.05 는 기록만(§6-13).
- 오너 결정: ⓐ 3개월 열 vs 누적 차분(34건 전부 전기 재작성) ⓑ·ⓒ 가이던스 셀 덮어쓰기·변수 환율 교체 — 플래그로 구현돼 현재 패치본에 **적용됨**(원문 보존, `_orig` 무손상) → 유지/원복 ⓓ 2028 신규수주 ⓔ 코호트 외부 지수 ⓖ 모델 재생성 주기 ⓗ 주석 파싱 착수 ⓘ 격자 다중비교 보정.

참고용 · 투자조언 아님.

## 11. 마감 — 2026-09-30 22:20 KST (오너 재실행·결정 반영, 실측)

§10 의 '남은 것' 중 하류 stale 은 전부 해소했다. 순서: `kship_price.py`(토스 이력 포함 재수집) → `kship_sls.py --all` → `kship_model.py --build --all --xlsx --today 2026-09-30` → `kship_xlsx_patch.py --all --verify --overwrite-placeholders --fx-actuals` → `kship_page.py --all && kship_parts.py --all && kship_model_section.py --hub` → 테스트 245 OK(skipped 1).

**오너 결정(코드에 반영)**
- **종가 정본 = 네이버 정규장 종가**(`prices.rows[].close`, `close_source=naver_regular_close`; aik 원값은 `aik_close`, 시총은 정규장 종가 × 발행주식수). 근거: 9/28·9/29 57종목 중 48~49종목에서 aik `close` 가 네이버·토스 정규장 종가와 달랐고(최대 4.4%) 시가·고가·저가·거래량은 세 원천이 같았다. 모델 `valuation.price.source` 에 aik 대조값을 함께 적는다. 삼성重 9/29: 19,500(네이버) vs 19,330(aik).
- **고객 연동 채택 조건 강화**(`kship_model.py`): 상관 ≥ 0.30 에 더해 단일 검정 5% 유의(r ≥ r_crit(df=n−2))와 n ≥ LINK_MIN_N 을 요구. F2 격자에서 비유의로 채택됐던 4사(현대리바트·KS인더스트리·원일티엔아이·티엠씨)가 폴백으로 돌아가 고객 연동 29 → **25사**, 추세 폴백 27사. 세진은 유지(레퍼런스 가중치 미포 0.818·HD현대重 0.182 · 시차 1 · 4분기 이동합 · n=8 · r=0.911, 임계 0.707).
- **PER 밴드 캡 5~30배**(`PER_BAND_CAP`): 밴드 중위까지 캡 밖이면 sector_default(10/15/20)로 대체하고 원값을 `hist_band_raw` 에 남긴다(17사 `band_capped`). HD현대重 원값 30.7/36.3/57.6배 → 10/15/20 → PER 적정가치 249,200~498,500원(종가 430,500). 밸류에이션은 추천이 아니다.
- 지주 009540 폴더는 만들지 않는다(렌더 확인 출력 삭제) — 허브 표에서 xlsx 만 링크.

**최종 산출(실측)**: models 58행 **full 27 · partial 31 · no_fin 0**(드라이버 고객연동 25 · 추세 27 · 선표 5 · 지주 1) · 백테스트 중위(n=56) 매출 WAPE **16.1%** · OP **56.4%**(그대로 보고 — 통계 아님) · xlsx 58개 · 섹션 **56/56장** + 허브 57행 · 레퍼런스 패치본 3개 ALL OK(교체 20셀 · 변수 환율 112/112/24셀 · 종가 9/29 세진 9,700 · 삼성重 19,500 · 미포 없음) · 테스트 245 OK.

주요 FY2026E(억원, 모델 산출 — 컨센서스 아님): 삼성重 매출 129,892 · OP 12,838 · EPS 1,126원(PER 13.1) / HD현대重 254,552 · 36,224 · 27,824원 / 한화오션 169,951 · 20,872 · 6,560원 / HD한국조선해양 356,867 · 56,744 · 54,398원 / 세진 4,135 · 732 · 981원(PER 11.0) / 한화엔진 15,317 · 1,621 · 1,933원. 2028E 는 2026Q2 잔고 소진분만(신규 수주 미포함 — 결정 ⓓ 미결).

미결(변경 없음): ⓐ 3개월 열 vs 누적차분 정본 ⓓ 2028 신규수주 ⓔ 코호트 외부 지수 ⓖ 모델 재생성 주기 ⓗ 골든 잔여 8.9% 주석 파싱 ⓘ 격자 다중비교 보정(유의성 조건은 넣었고 Bonferroni 류는 안 함).
