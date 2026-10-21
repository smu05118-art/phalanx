# 한국화학 — 판정 규칙 (LOGIC)

파이프라인이 ARGUS 빌더 산출물에서 화면까지 무엇을 어떻게 결정하는지. 코드(`tools/kchem_registry.py`)가 최종 근거이며
이 문서는 그 요약이다. 실행 순서·현재 상태는 [HANDOFF.md](HANDOFF.md), 화면 안내는 [README.md](README.md).

## 0. 이 탭의 성격 — 수집기가 아니라 재조립기

- 입력은 **ARGUS 빌더 산출물 4종**(`argus/data/argus_data.js`·`chunk_<카테고리>.js` 13개·`connections.js`, `argus/data_map.js`)뿐이다.
  네트워크·DART·API 키를 쓰지 않는다. 산출물은 읽기 전용이며(AGENTS.md "생성물 직접 수정 금지") 빌드 시 python3 로
  파싱하는 **단일 경로**다 — 페이지가 런타임에 `../data/chunk_*.js` 를 교차 로드하지 않는다(스키마가 바뀌면 fail-closed 검증을
  우회해 화면에서 조용히 깨지기 때문).
- 모집단은 상장사가 아니라 **스프레드 시리즈**다: 스프레드 패널의 화학 13 카테고리(나프타·기초유분·올레핀·아로마틱·염소체인·
  초산체인·우레탄·화섬·솔벤트·폴리머·아크릴·고무·화학PPI) 전수. 2026-10-05 빌드 기준 242(스프레드 209·가격 12·中선물 18·PPI 3).
- 원장 값은 **불가침**이다. 결함으로 보이는 것도 수정하지 않고 플래그로만 표시한다(원장은 Weekly xlsm 수동 드롭, Platts류 유료 스팟).
- wj-stock 등 회원 전용 화면의 값·산식·회사 목록은 입력이 아니다(robots `ai-input=no`).

## 1. 입력 계약 (`kchem_inputs.py`) — fail-closed

| 입력 | 검증 |
|---|---|
| `argus_data.js` | `version == 2`, `asof` 날짜, `spread.series[]` 12필드(`sid name cat chain unit sp pos m4 hunt last_date freshness last`), `chains[]`(id·label·pos·mom·n·hunts·members·stocks), `chunks.spread` |
| `chunk_<cat>.js` | `kind == "spread"`, `key == cat`, `axis` 오름차순 날짜, 모든 `series[].v` 길이 = axis 길이, 값은 숫자 또는 null |
| `connections.js` | `total == len(rows)`, 행 14필드, `observations` 는 `[날짜, 값]` 오름차순 |
| `data_map.js` | `version == 1`, `counts.tiles == len(items)`, 아이템 14필드 |
| 교차 | 패널의 화학 시리즈 집합 == 청크의 시리즈 집합 |

하나라도 어긋나면 `InputError` 로 멈추고 기존 산출물을 건드리지 않는다. 입력 파일 sha256 을 모아 `fingerprint` 를 만든다 —
빌드 시각은 어디에도 쓰지 않으므로 **입력이 같으면 모든 산출물의 바이트가 같다**(테스트 `test_pages_contract_and_determinism`).

- **내용 fingerprint**(`fingerprint.content`, `kchem_inputs.content_fingerprint`): 파일 sha256 은 허브가 매 빌드 `asof`·`built` 를
  바꾸기만 해도 달라진다. 그래서 이 탭이 실제로 읽는 부분만(화학 패널·화학 체인·화학 청크·`sp_`/`p_`/패널/中선물/라이브 프록시
  connections 행·그 맵 아이템·`aliases.json`) 정규 JSON 으로 해시한다.
- **커밋 게이트**(`kchem_page.py --gate <이전 fingerprint.json>`): 내용 fingerprint 가 바뀌었거나 ISO 주가 바뀌었을 때만 커밋
  (주 경계는 `weeks_since`·편집 누락 수 갱신용). 워크플로는 `--check`(같은 입력 재빌드 = 바이트 동일) 뒤 게이트를 통과해야 커밋한다.
- 빌더 산출물이 main 에 들어오면(`argus/data/*.js`, `data_map.js`) push 트리거로 즉시 재조립한다. 09:10 KST 일정은 백업.
- `kchem_lib` 은 `kce_lib` 만 import 하고 kship 표 JS 는 `ast` 로 읽는다 — 모듈 import 만으로 네트워크 코드가 실리지 않는다(테스트 `TestNoNetworkImport`).

## 2. 산식 역산 (`kchem_registry.py`)

원장 스프레드는 이름(`제품-원료 스프레드(지역)`)만 있고 계수·참조 지역은 어디에도 없다. 그래서:

1. **이름 분해** — 괄호 밖 마지막 `-` 로 제품/원료(`S-SBR-BD` → `S-SBR`,`BD`), `&` 는 복합, `크랙` 은 원유 대비, `-` 없음은 원료 미표기.
   접미사 `(지역)` 이 지역. `가격(지역)` 은 가격 행.
2. **제품·원료 시리즈 찾기** — `assets/aliases.json` 의 한글→영문 사전(`에틸렌`→`Ethylene`, `자일렌(이성체)`→`Xylene(이성질체)`…)으로
   `connections.js` 의 이름 `"<영문> <지역>"` 을 찾는다. 원료의 참조 지역 후보는 `ref_region_order`
   (같은 지역 → 일본 → 한국 → 동북아 → 중국 → …) 전부.
3. **최소제곱** — `스프레드 = 제품 − Σ kᵢ×원료ᵢ`, 절편 없음, 적합 창 = 스프레드·제품·원료 관측이 모두 있는 공통 날짜(connections 주간, 최대 104주),
   최소 24주. |잔차| > 1.5 USD/MT 인 주를 빼고 2회 재적합(원장에 한 주짜리 결측·정정이 실제로 있다 — 2026-08-10 주 다수).
   - **이월 주 제외**(`carry_weeks`): 원장이 끊긴 뒤 스프레드·제품·원료가 전부 전주 값 그대로인 꼬리 주는 관측이 아니라 이월이다.
     적합 창에서 빼고 `carry_forward` + `effective_last`(실제 마지막 관측일)를 남긴다(18행 · 25주). 화면의 정지 주는 이 날짜 기준.
   - **두 출발점**: LS 해와 단일 원료의 **주별 함의 k 중앙값** 두 곳에서 robust 재적합을 돌려 (재현 여부, 안쪽 비율, RMS) 순으로 고른다.
     몇 주의 큰 이탈이 LS 해를 끌어 미재현이 되던 페놀−벤젠 미국/인도·LDPE−에틸렌(유럽)이 중앙값 출발로 재현된다.
   - **선행 레짐 검사**(`leading_regime`): 중앙값 출발이 창 앞쪽의 다른 산식 구간을 덮어 버리지 않게, 앞쪽 연속 구간의 k 가
     본 k 와 다르면 `formula_changed` 로 남긴다(MEG−EO 대만 2024-11-11).
4. **재현 판정** — 전체 창에서 |잔차| ≤ 1.5 인 주가 90% 이상이고, 마지막 주가 안에 들며 마지막 4주 중 3주 이상이 안에 든다.
   1.5 의 근거: 원장 값이 0.5 단위로 반올림돼 있어 계수 합 ≤ 1 이면 누적 반올림 오차 상한이 약 1 이다.
   재현 행은 `grade` 를 단다: 안쪽 주 최대 잔차 ≤ 0.01 이면 `exact`(바이트 수준 일치), 아니면 `approx`. 2026-10 빌드는 189 전부 exact.
4b. **나프타 크랙 단위** — `납사−Dubai 크랙` 은 USD/MT 로 안 맞으면 `P/CRACK_C`(CRACK_C = 1000/108 = 9.2593 bbl/MT)로 납사를 USD/bbl 로
   바꿔 `S = Naphtha/9.2593 − Dubai` 를 다시 맞춘다. 맞으면 `crack_usd_bbl`, `unit_hint = USD/bbl`(일본 1행 재현; 나머지 6은 2022 정지로 겹침 없음).
5. **산식 변경 탐지** — 전체 창에서 안 되면 최근 26주로 다시 적합. 거기서 재현되면 끝에서부터 거슬러 올라가 연속 이상치 3주를
   만나기 전까지를 현재 산식의 구간으로 잡고 `formula_changed` + `regime_start` 를 남긴다.
6. **원료 보강·탐침** — 이름의 원료로 안 되면 `composite_extra_feeds`(ABS+AN, SBR·S-SBR·SBS·SB라텍스+SM, NBR·NB라텍스+AN)를 더해 보고
   (`composite_extra_feed`), 그래도 안 되면 `probe_feeds`(나프타 일본·에틸렌·프로필렌·벤젠·SM·에탄 — 같은 지역/한국)로 단일 원료를 탐침해
   맞으면 `feed_mismatch`(이름과 다른 원료) 또는 `feed_unspecified`(이름에 원료 없음).
7. **결함 탐지** — 제품 가격이 스프레드보다 먼저 끊겼는데 그 뒤 스프레드가 `−Σk×원료` 와 같으면 `missing_product_as_zero`
   (BR−BD(한국): BR 가격 2026-04-06 정지 후 스프레드 = −BD).
8. 후보가 여럿이면 재현 > 안쪽 비율 > 잔차 > 지역 순서로 고른다. 미재현끼리는 잔차 RMS 가 작은 것을 표시한다.
9. **일시 이탈 진단**(`episode_diag`, 진단 전용 — 재현 수에 넣지 않는다) — 단일 원료 미재현 행에서 주별 함의 k 의 중앙값을 기준으로
   |k − 기준| > 0.1 인 연속 구간이 8주 이상이고 마지막 4주가 다시 기준이면 `formula_episode` 와 구간을 `k_source` 에 남긴다.
   PPG−PO(한국) 기준 1.05 → 2026-02-02~07-13 24주 이탈 · PC−BPA(한국) 0.93 → 같은 구간 23주 이탈(0.45~0.72) 후 복귀.
10. **지역 간 복제**(`mark_duplicates`) — 서로 다른 지역 시리즈의 값 열이 바이트 동일하면 `ref_region_order` 가 앞선 지역을 정본으로,
   나머지에 `dup_of`·`dup_of_region`·`dup_group` 을 단다. 화학 209 중 27그룹 → **고유 179**, 파생 47 중 7그룹 → 고유 34.
   매트릭스 셀은 `=지역` 으로 표시하고 집계(체인 중앙값 등)에서 뺀다.

### 2026-10-05 빌드 결과 (재현 183 / 209 — 2026-10-16 보강 후 189 / 209, 전부 exact)

> 아래 표는 10-05 판정이다. 10-16 보강(이월 제외·중앙값 출발·크랙 USD/bbl)으로 페놀−벤젠 미국/인도·LDPE−에틸렌(유럽)·나프타 크랙(일본)·Crude C4−납사 미국/유럽 6행이
> 추가 재현됐고, PPG−PO·PC−BPA 는 미재현으로 두되 일시 이탈 구간을 진단으로 남긴다. 미재현은 20(아래 목록에서 재현된 것 제외).

| 분류 | 수 | 예 |
|---|---|---|
| 1:1 단순 차감 | 다수 | PE/PP/PS−모노머, BTX−납사, SM−벤젠, 페놀−벤젠, PVC−VCM, OX−자일렌(솔벤트) |
| 계수형(역산) | ~60 | EDC−에틸렌 0.30 · VCM−EDC 1.64 · TPA−PX 0.67 · AN−프로필렌 1.05 · PX−자일렌(솔벤트) 1.25 · PA−OX 0.91 · BPA−페놀 0.88 · PET−TPA 0.88 · PO−프로필렌 0.80 · MDI−벤젠 0.80 · TDI−톨루엔 0.76 · MEG−EO 0.75 · PG−PO 0.77 · VAM−에틸렌 0.40 · PVC−납사 0.70 · 카프로락탐−톨루엔 0.96 · 아크릴산−AN 0.82 · MMA−아세톤 0.70 |
| 복합(이름에 없는 원료 추가, 10) | ABS = BD 0.19 + SM 0.54 + **AN 0.27**(4지역) · SBR/S-SBR/SBS = BD 0.73 + **SM 0.23** · SB라텍스 = BD 0.42 + SM 0.22 · NBR = BD 0.65 + **AN 0.35** · NB라텍스 = BD 0.30 + AN 0.15 — 전부 잔차 0.0 |
| 원료 미표기 → 탐침(8) | 아세톤 = Acetone − 0.85×Propylene(같은 지역, 6) · IPA(유럽) − 0.82×Propylene · 에틸아세테이트(미국) − 0.39×Ethylene |
| 산식 변경(3) | MEG−EO(대만) 0.75 는 2024-11-11 이후 · PX−자일렌(대만)은 2025-12-29 이후 **PX − 1.0×Naphtha 일본**(이름과 다른 원료) · 에틸렌−납사(미국)은 2026-01-12 이후 Ethylene − 1.0×**Ethane 미국** |
| 결함 의심(1) | BR−BD(한국) 결측 제품을 0 으로 계산 |
| 참조 지역 규칙(역산) | 모든 −납사는 지역 불문 **Naphtha 일본**(Naphtha 한국 시리즈 없음) · 중국 Huadong/Huanan·동북아 제품은 한국 원료 · EO 는 중국 1지역 |

미재현 26: 납사−Dubai 크랙 7(USD/MT − k×USD/bbl 환산계수 미확인, 6개는 2022 정지로 겹침 없음) · VAM−에틸렌 5 + 부틸아크릴레이트−초산 2(2024-10 정지, 겹침 없음) ·
에틸렌−납사(유럽) 겹침 없음 · 제품 시리즈 없음 3(IPA 미국·에틸아세테이트 중국·MMA) · Crude C4−납사 2(원료값 727 — 맵에 없는 시리즈) ·
페놀−벤젠 미국·인도(k=1 에 상수 잔차 +3~4) · LDPE−에틸렌(유럽)(상수 잔차 −3) · PC−BPA(k 0.93 에 상수 −129) · PPG−PO(k 가 0.77→1.05 로 연속 변동) · PU−MDI&PPG.
전부 `coverage.html` 에 이유와 함께 보이고 `registry.json` `fit` 에 2시점 k·잔차·이상치 주가 남는다.

## 3. 레지스트리 스키마 (`tools/assets/registry.json`)

행(`rows[]`): `sid name cat chain chain_est unit sp kind(spread|price|proxy_cnfut|index|other) layer(integrated|step|composite|crack|price|proxy|index|unknown)
product product_sid feeds[{token sid name ref_region k}] region formula formula_version k_source fit{n n_in frac resid_max_in resid_max_all resid_rms window outliers k_2pt [regime_start full_n]}
reproduced flags[] freshness last_date last pos m4 hunt expected_cadence stale_after_days days_since weeks_since lane reason basis_note source in_map stocks[{t n note est}] cnfut{sid name last last_date unit freshness}`.
파생(`derived[]`): 같은 꼴 + `values[]`(축 `axis2y`). `summary` 에 집계, `rules` 에 위 상수, `chains` 에 허브 체인 pos·mom·stocks.

- `chain_est` 는 패널에 체인이 없는 51개(화섬·초산체인·아크릴·기초유분)에 `aliases.json.chain_est` 로 붙인 **추정** 배정(AN·EO·MEG·VAM·아크릴·MTBE→ncc, TPA·카프로락탐→aromatics, MMA→solvents, 가성소다→vinyls; 메탄올·PTMEG 는 미배정).
- `stocks` 는 허브 `chains[].stocks` 를 체인 단위로 조인한 **참고 라벨**이다(스프레드별 감도·매출 비중 아님). `chain_est` 경유면 `est=true`(점선 칩).
- `cnfut` 는 제품→中 선물(quheqihuo) 사전 매핑. 기준(CNY/t·증치세·선물)이 달라 **같은 산식에 넣지 않고** 참고 열로만 쓴다. `cf_polyethylene`(塑料)은 LLDPE 계약이라 HDPE/LDPE 에는 근사.
- 신선도 등급은 패널 값을 그대로 쓰고, `expected_cadence`(connections `freq`)·`stale_after_days`(D 7 · W 14 · T 20 · M 45)·`weeks_since`(평가일 `asof` 기준) 를 덧붙인다.
  `원장 정지 N주` = `asof − max(sp_ last_date)`. 평가일은 `argus_data.asof` 이지 빌드 당일이 아니다(결정성).

## 4. 파생 스프레드 (`aliases.json.derived`) — 원장에 없는 것을 이 탭이 계산

공개 관행 계수가 1:1 이거나 널리 쓰이는 것만: HDPE(사출/필름)·LDPE·LLDPE·PP(호모/필름)−납사 통합, PX−납사(1:1), 카프로락탐−벤젠(1:1, 벤젠 중국 시리즈가 없어 한국 벤젠 참조), PVC−0.5×에틸렌.
전부 `derived:` 접두 sid, `basis` 는 원장끼리(USD/MT), 축은 최근 104주(`axis2y`), 화면에 **추정** 배지. SM·BTX·MEG−에틸렌·PET·BPA 복합·복합 정제마진은 계수 근거가 없어 넣지 않았다(가설로 남김).

## 4b. 살아 있는 프록시 (`aliases.json.live_proxies`) — 원장 정지 중 방향만

원장이 멈춘 동안 살아 있는 입력은 中 선물(DCE·CZCE 일간)과 무역통계 단가(월간)뿐이다. 15개를 원장 시리즈와 짝지어 두되
**원장 산식에는 절대 넣지 않는다**(기준·통화·증치세가 다르다 — 테스트 `test_proxies_never_feed_ledger_math`).

- 게이트(`LIVE_GATE`): 원장 겹침 구간을 앞 70% 학습 / 뒤 30% 검증으로 나눠 **검증 구간에서** 주(월)별 방향 적중 ≥ 0.70, 상관 r ≥ 0.60,
  짝 ≥ 8. 월간 프록시는 시차 0/1개월 중 학습 r 이 큰 쪽을 쓰고, 정지 후 창도 그 시차만큼 밀어 정지 전 움직임이 섞이지 않게 한다.
- 게이트 통과분만 체인 카드의 `정지 후` 변화에 쓴다(2026-10 빌드 15 중 1 통과 — MEG 한국 ← CZCE MEG, 정지 후 −3.52%).
  미통과분도 `proxies` 표에 적중·r 과 함께 보이되 집계에는 쓰지 않는다.

## 4c. 체인 보기(`chain_view`)와 원장 편집 추적(`editions`)

- 체인 카드는 두 값을 나란히 둔다: **원장 as-of 중앙 pos**(원장 마지막 관측 21일 안에 살아 있던 비복제 행의 pos 중앙값)와
  **허브 pos**(허브가 그 체인에 쓰는 소스 구성 `hub_basis` — 中선물·NBS 순보 등 — 를 `basis_kind` 로 분류해 같이 표시).
  허브 pos 가 원장 기반이 아닐 때는 `hub_has_ledger=false` 로 밝힌다.
- 원장은 목요일 이름의 `Weekly_YYMMDD.xlsm` 이다. `last_edition = ledger_last + 3일`, 다음 기대 편집 = +7일,
  `missing` = 평가일(asof) 전날까지 도착했어야 할 목요일 수. 최신본 1개가 누적형이라 복구는 파일 1개다.
  Mini 의 `argus/argus_ledger_watch.py`(argus_daily.sh 매 회차)가 같은 규칙을 빌드 당일 기준으로 계산해 **새로 누락된 편집이 생긴 회차에만**
  텔레그램 1줄을 보낸다(상태 `jem_data/argus/ledger_watch_state.json`, 발송 성공 시에만 갱신).

## 4d. 사용자 가격표로 원장 뒤 잇기 (`kchem_supplement.py`, 2026-10-21)

- 입력: 사용자가 준 주간 제품 가격표(`화학제품 가격.xlsx` — 시트 1장, 머리 3줄 분류·제품(단위)·지역, A 열 일련번호 날짜, 2000-01~).
  `--import` 가 표준 라이브러리(zip+XML)로 읽어 `tools/assets/supplement/prices.json` 에 남긴다. 빌드는 이 해석 결과만 읽는다.
- 매핑: `assets/supplement_map.json` — 머리행 **글자**(제품(단위)·지역)로 원장 제품 가격 시리즈(connections `p_…`)에 맞춘다. 열 위치가 아니다.
- 검증(잇는 조건): 겹치는 원장 관측 24주 이상, ±1% 일치 90% 이상, **정확 일치 50% 이상**. 2026-10-21 가져오기: 40열 매핑 중 39 통과
  (겹침 102주, 4,182 관측 중 3,946 정확), 에탄은 ±1% 92% 지만 정확 0 — 가격표가 $/gal 을 거칠게 환산해 잇지 않는다. 카프로락탐은
  가격표가 한국, 원장이 중국이라 매핑하지 않았다(가격 페이지에만).
- 잇기: 원장 관측이 있는 날짜는 그대로, 시리즈마다 원장 마지막 관측 **뒤** 날짜만 붙인다. 스프레드는 1차 레지스트리(원장만)에서
  재현(정확·근사)된 행 중 제품·원료가 전부 이어진 행만 `S = P − Σk×F`(크랙은 P/9.2593)로 계산해 청크 축 빈칸을 채운다 —
  209 중 36(원료가 Dubai 유가·메탄올처럼 가격표에 없거나 미재현인 행은 원장 날짜에 멈춤). 4W% 는 허브와 같은 식, 사이클 위치는
  허브 정의(장기 원장)를 몰라 kchem 5년 백분위로 다시 계산한다(`pos_src = kchem_5y`).
- 2차 레지스트리는 이은 입력으로 다시 적합한다(이은 값은 같은 산식이라 적합이 바뀌지 않는다). 파생 스프레드는 이은 제품 가격으로 자동 연장.
- 정지 사실은 숨기지 않는다: 요약의 `ledger_last`·`ledger_stale_weeks`·`editions` 는 1차(원장만) 값, 이은 범위는 `summary.supplement`.
- fingerprint 에 가격표 sha256 을 더한다. 재배포 최소화 — 커밋하는 관측은 5년 창(2021-10-25~)뿐, 2000년 이후 장기 통계는 최소·최대·백분위 숫자만.
- 새 가격표가 오면: `python3 kchem_supplement.py --import "<xlsx>" --name "<원래 이름>"` → `python3 kchem_page.py`. 원장이 재가동되면
  원장 날짜가 앞서므로 가격표 몫은 저절로 줄어든다(코드 변경 없음).

## 5. 화면 규칙

- 사이클 위치(pos)·4주 변화(m4)는 허브 값을 그대로 쓴다(m4 는 허브 카드에서 렌더되지 않는 값을 여기서 표시).
- 추이: 원장 시리즈는 청크 255주, 파생은 104주, 中선물·PPI 는 청크 축이 2026-08-24 에 고정돼 최근 주가 잘리므로 connections 관측으로 그린다.
- 지역은 시리즈 이름 접미사에서 파생했다(필드가 없다). 매트릭스 열 순서는 한국·대만·일본·동남아·동북아·중국·중국 Huadong/Huanan·인도·미국·유럽·나프타 허브.
- 밸류체인 그림은 외부 지식이 아니라 레지스트리의 원료→제품 관계로 자동 생성한다(단계는 원유 0·나프타 1 뿌리에서 유도, 모르면 "단계 미상").
- stale 시리즈에 시그널·사냥 배지를 새로 만들지 않는다(허브가 "stale 시그널 화면 누출"을 결함으로 고친 이력).
  stale/dead 행의 4W% 는 `—(정지)`, dead 행의 pos 는 흐리게 두고 정렬값을 비운다(멈춘 값을 현재 위치처럼 정렬하지 않게). 매트릭스의 dead 셀은 색을 칠하지 않는다.
- 사냥 시그널 `bottom_turn` 은 원장 이력에서 적중 63.0% 로 기저율 63.9% 와 같다 — 부가가치가 없다는 고지를 붙인다.
- 종목 페이지는 `chem_chains`(refining·ncc·aromatics·butadiene·vinyls·urethane·solvents) 종목 중 스프레드 1행 이상이 걸린 것만 만든다(11).
  예전 빌드가 남긴 비화학 종목 폴더는 표지 문자열(`— 화학 스프레드 역참조</title>`)이 있을 때만 지운다.
- 표의 각 행은 `#r-<sid>` 앵커가 있고, 검색은 공백으로 나눈 토큰의 AND 다.
- 원장 값의 csv/JSON 재배포는 하지 않는다(라이선스 확인 전).
