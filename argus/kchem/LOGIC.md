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

## 2. 산식 역산 (`kchem_registry.py`)

원장 스프레드는 이름(`제품-원료 스프레드(지역)`)만 있고 계수·참조 지역은 어디에도 없다. 그래서:

1. **이름 분해** — 괄호 밖 마지막 `-` 로 제품/원료(`S-SBR-BD` → `S-SBR`,`BD`), `&` 는 복합, `크랙` 은 원유 대비, `-` 없음은 원료 미표기.
   접미사 `(지역)` 이 지역. `가격(지역)` 은 가격 행.
2. **제품·원료 시리즈 찾기** — `assets/aliases.json` 의 한글→영문 사전(`에틸렌`→`Ethylene`, `자일렌(이성체)`→`Xylene(이성질체)`…)으로
   `connections.js` 의 이름 `"<영문> <지역>"` 을 찾는다. 원료의 참조 지역 후보는 `ref_region_order`
   (같은 지역 → 일본 → 한국 → 동북아 → 중국 → …) 전부.
3. **최소제곱** — `스프레드 = 제품 − Σ kᵢ×원료ᵢ`, 절편 없음, 적합 창 = 스프레드·제품·원료 관측이 모두 있는 공통 날짜(connections 주간, 최대 104주),
   최소 24주. |잔차| > 1.5 USD/MT 인 주를 빼고 2회 재적합(원장에 한 주짜리 결측·정정이 실제로 있다 — 2026-08-10 주 다수).
4. **재현 판정** — 전체 창에서 |잔차| ≤ 1.5 인 주가 90% 이상이고, 마지막 주가 안에 들며 마지막 4주 중 3주 이상이 안에 든다.
   1.5 의 근거: 원장 값이 0.5 단위로 반올림돼 있어 계수 합 ≤ 1 이면 누적 반올림 오차 상한이 약 1 이다.
5. **산식 변경 탐지** — 전체 창에서 안 되면 최근 26주로 다시 적합. 거기서 재현되면 끝에서부터 거슬러 올라가 연속 이상치 3주를
   만나기 전까지를 현재 산식의 구간으로 잡고 `formula_changed` + `regime_start` 를 남긴다.
6. **원료 보강·탐침** — 이름의 원료로 안 되면 `composite_extra_feeds`(ABS+AN, SBR·S-SBR·SBS·SB라텍스+SM, NBR·NB라텍스+AN)를 더해 보고
   (`composite_extra_feed`), 그래도 안 되면 `probe_feeds`(나프타 일본·에틸렌·프로필렌·벤젠·SM·에탄 — 같은 지역/한국)로 단일 원료를 탐침해
   맞으면 `feed_mismatch`(이름과 다른 원료) 또는 `feed_unspecified`(이름에 원료 없음).
7. **결함 탐지** — 제품 가격이 스프레드보다 먼저 끊겼는데 그 뒤 스프레드가 `−Σk×원료` 와 같으면 `missing_product_as_zero`
   (BR−BD(한국): BR 가격 2026-04-06 정지 후 스프레드 = −BD).
8. 후보가 여럿이면 재현 > 안쪽 비율 > 잔차 > 지역 순서로 고른다. 미재현끼리는 잔차 RMS 가 작은 것을 표시한다.

### 2026-10-05 빌드 결과 (재현 183 / 209)

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

## 5. 화면 규칙

- 사이클 위치(pos)·4주 변화(m4)는 허브 값을 그대로 쓴다(m4 는 허브 카드에서 렌더되지 않는 값을 여기서 표시).
- 추이: 원장 시리즈는 청크 255주, 파생은 104주, 中선물·PPI 는 청크 축이 2026-08-24 에 고정돼 최근 주가 잘리므로 connections 관측으로 그린다.
- 지역은 시리즈 이름 접미사에서 파생했다(필드가 없다). 매트릭스 열 순서는 한국·대만·일본·동남아·동북아·중국·중국 Huadong/Huanan·인도·미국·유럽·나프타 허브.
- 밸류체인 그림은 외부 지식이 아니라 레지스트리의 원료→제품 관계로 자동 생성한다(단계는 원유 0·나프타 1 뿌리에서 유도, 모르면 "단계 미상").
- stale 시리즈에 시그널·사냥 배지를 새로 만들지 않는다(허브가 "stale 시그널 화면 누출"을 결함으로 고친 이력).
- 원장 값의 csv/JSON 재배포는 하지 않는다(라이선스 확인 전).
