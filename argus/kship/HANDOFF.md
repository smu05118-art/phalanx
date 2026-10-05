# 한국조선(argus/kship) — 인수인계 (2026-09-10)

다른 머신(맥미니)에서 이어가기 위한 상태 기록. 코드·데이터·페이지는 전부 `main`에 있다.
`git pull` 뒤 아래 순서로 돌리면 같은 화면이 나온다(파이썬 3.9+ 표준 라이브러리만).
**남은 과정만 바로 착수하려면 [KICKOFF.md](KICKOFF.md)** — 레인 A/B/C·IP 제약·검증 6항목·붙여넣을 프롬프트.

```bash
cd argus/kship/tools
python3 kship_universe.py --write          # KIND → 모집단(2026-09-30: 57종목 = 조선사 5·지주 1·엔진 5·기자재 41·강재 5; '탐색' 승격은 universe_probe 에서 이월 — 아래 9/30 절)
python3 kship_contracts.py --collect       # 척당 계약 공시 캐시(assets/contracts/) — 있는 건 건너뜀
python3 kship_contracts.py --build         # → assets/contracts.json
python3 kship_yards.py --collect           # 조선사 정기보고서 최신 분기(롤포워드·매출·환노출·헤지)
python3 kship_suppliers.py --collect       # 기자재사 정기보고서 II 절(제품·조선사 언급)
python3 kship_suppliers.py --build         # → assets/suppliers.json (+ unclassified.csv)
python3 build_dicts.py                     # 부품 분류 54·SVG 영역 35 재생성(교차참조 검증)
python3 kship_page.py --all                # 허브·커버리지·조선사 5장
python3 kship_parts.py --all               # parts.html 인포그래픽 + 기자재사 35장
python3 inject_link.py --apply             # argus/index.html 에 ⚓ 한국조선 진입 링크(크론이 지우면 재주입)
```

로컬 미리보기: 레포 루트에서 `python3 -m http.server 8902` → `http://localhost:8902/argus/kship/index.html`.

## 무엇이 어디서 오는가 (실측으로 확정)

| 축 | 원천 | 비고 |
|---|---|---|
| 수주잔고·신규·기납품(부문) | 정기보고서 II-4 수주상황 — **부문 롤포워드**(원화, 삼성重 억원) | 선종·척수 없음. 신규증감에 환율효과 포함 |
| 선종·척수·인도시점·상대·지역·대금조건 | 수시공시 「단일판매ㆍ공급계약체결」 | 상대 81% 익명('○○ 소재 선사'). 종료일=마지막 호선 인도 |
| 매출실적(부문×수출/내수) | 정기보고서 II-4 | |
| 환노출(통화별 자산·부채, 계약자산) | II-5 위험관리 및 파생거래 | HD현대重·대한조선만 표 형식 |
| 통화선도 명목액·평균만기·건수 | 주석 「파생금융상품」 또는 II-5 | 3사 3형식(주석 라벨형/4열 쌍/USD매도 행) 모두 파싱 |
| 반복건조(시리즈) | **추정** — 같은 선종·상대 표기·지역, 수주일 180일 이내 | 화면에 '추정' 표시 |
| 기자재 부품 분류 | 정기보고서 II-2 주요제품 + KIND 문구 → 키워드 규칙 | 미분류는 `assets/unclassified.csv`, 수동 지정은 `parts_override.csv` |
| 기자재→조선사 연결 | II 절 본문의 조선사 이름 언급(횟수), 비중은 적힌 경우만 | 근거 등급을 화면에 표시(주요고객 주석 > 계약 공시 > 본문 언급 > KIND) |

## 지금 상태 (2026-09-11 01:45 KST — 맥미니에서 재수집 완료)

- **수집 완료**: 척당 계약 278건 캐시 → 225건(정정 25건 supersedes, 선종 미판정 0) · 기자재 35사 재수집(--force, 조선사 언급 확인 18사, 비중 0~100 검증) · 조선사 5사 × 8분기(2024Q3~2026Q2; 대한조선은 2025Q2~, HJ중공업 2024Q4·2025Q4 사업보고서는 수주 절 제목이 달라 미수록).
- **환헤지 확정**: 삼성重 482억달러는 주석 오독이었다 — ① '전기말' 비교표 합산 ② 목적별 3열+합계 열 합산 ③ 멤버별 합계+총합계 열 합산. 셋 다 고쳐 시계열 223→219→227→219→221→227→230→**255억달러**(2026Q2, 잔고 35조≈250억달러와 정합). HD현대重 148→208억달러, 한화오션 9→39억달러. 대한조선·HJ중공업은 헤지 공시 없음('헤지 공시를 찾지 못함' 표시).
- **롤포워드**: 기초=연초, 신규·기납품=연초 누계(실측). 표에 '대조' 열(같은 해 기초 = 전년 Q4 기말) · 합계행이 부문합과 어긋나면 부문합 사용(삼성重 2024Q4·2025Q1 합계 셀 깨짐).
- 신형 거래소 서식(2025~ '판매ㆍ공급계약 구분/세부내용', '계약(수주)일') 파싱 추가. 빌드가 캐시 원문 라벨에서 필드를 다시 뽑는다.
- `site.json` — 맥미니 ARGUS 빌더(`argus_build.py inject_subsite_links`)가 크론마다 ⚓ 링크를 재생성하므로 되쓰기 경쟁이 끝났다.
- 테스트 15건 `cd tools && python3 -m unittest discover -s tests`. 자동 갱신 `.github/workflows/update-kship.yml` 매일 10:40 KST.
- **모집단 ④ 본문 탐색(9/11 02:50)**: `tools/kship_scan.py` 가 KIND 기자재 어휘 후보 230사의 정기보고서 II 절을 읽어 16사 승격
  (나노·DSR·한국주강·케이씨씨·금강공업·한일철강·한선엔지니어링·영흥·해성에어로보틱스·서암기계공업·원일티엔아이·에스앤더블류·삼영엠텍·
  한화시스템·HD현대마린솔루션·서호전기) → 모집단 41→57, 기자재 51사(조선사 언급 확인 26). 기준: 조선 낱말 ≥6 또는 (조선사 언급 ≥2 ∧ 낱말 ≥3),
  고객 업종(가스공사) 제외. 제외 214사는 커버리지 페이지 '④' 접힘 표. 기준 변경 시 `--rejudge`(DART 불필요). 주 1회 `scan-kship.yml`.
  케이프(064820)·한화엔진(082740)은 처음부터 모집단에 있었다. 근접 제외: 디케이락(낱말 4·HD현대重 1) — EXTRA 로 지정해도 승격은 증거 기준.
- 남은 일(선택): 인포그래픽 미분류 제품 39건(`tools/assets/unclassified.csv` → `parts_override.csv`), HJ중공업 사업보고서 수주 절 제목 대응, 진행률(매출인식) 기준을 주석 「수익」에서 읽기.

## DART 주의

DART는 병렬 프로세스 2~3개가 동시에 두드리면 IP 단위로 연결을 끊는다(RemoteDisconnected, 30~60분).
수집기는 **하나씩** 돌려라. kce_fetch 가 요청 간격 0.7초·재시도 5회를 내장한다.

## 2026-09-18 원장 19분기 · Y+2 추정

- 원장을 **2021Q4~2026Q2 19분기**로 확장했다(이전 6~8분기). 재현: `python3 tools/kship_reports.py --collect --quarter 2026Q2 --n 19`
  → `--build` → `tools/kship_page.py --all`. (조선은 `kship_yards.py --collect --quarter <분기>` 를 분기마다.)
- 스튜디오 Codex(gpt-6-astra/ultra)가 만든 **Y+2 추정**(분기 T+1~T+10 · 연간 FY2026~FY2028)이 있으면
  `tools/assets/forecast_panel.json.gz` + `tools/kship_forecast_section.py` 로 회사 페이지에 실린다.
  산출이 없거나 회사가 빠지면 **섹션을 만들지 않는다**. 렌더러 파일명에 탭 접두가 붙은 이유는 그 파일 머리에 적었다.
- 추정에는 시나리오 3종·잔고분/신규분 분해·민감도 구간이 붙고 `calibrated=false` 로 표기된다 —
  통계적 신뢰구간이 아니며, 회계 매출이 아니라 수주원장 기준 대용치다.

## 2026-09-30 실적 모델 — 레퍼런스 subQ 3개 → 57사 (MODEL_SPEC.md · MODEL.md)

사용자 애널리스트 모델(세진·삼성중·HD현대미포 `subQ` xlsx, 사유 파일 → `[private local path]` 로컬 전용)을 레퍼런스로
분기 실적 모델 시스템을 8레인으로 만들었다. 설계 계약은 [MODEL_SPEC.md](MODEL_SPEC.md)(스키마·FnGuide 계정명 73·레인 소유), 만들어진 것·가정·한계·재현은 [MODEL.md](MODEL.md).

**파이프라인(순서가 계약이다)**: ① `kship_fin.py --collect --build --all`(DART, **단일 프로세스**, 캐시 체크포인트 `assets/fin_cache/`, 57사 × 20분기 ≈ 60분)
→ ② `kship_fx.py` · `kship_price.py`(ECB·aik, 키 없음) → ③ `kship_sls.py --all`(계약 원장 → 선표 → 헤지 원화 → 코호트 OPM) → ④ `kship_model.py --build --all --xlsx`
(→ `assets/models/<stock>.json` + `summary.json` + `models/<stock>_model.xlsx`) → ⑤ `kship_xlsx_patch.py --all --verify`(레퍼런스 원본 제자리 패치, 로컬 전용)
→ ⑥ `kship_page.py --all && kship_parts.py --all && kship_model_section.py --hub`(훅이 모델 있는 회사에만 섹션을 붙인다). 전체 명령은 MODEL.md §7.

**2026-09-30 21:50 KST 상태(실측 — 2차 검증·수정 뒤)**
- fin: 58 json(57 + HD현대미포), 파서 수리 후 21:18 `--build --all` 재빌드(캐시만; DART 접촉은 삼미금속 사유 확정용 A001 검색 1회). 로그 FAIL 0, 캐시 128MB(58 폴더, `.gitignore` 로 제외). 골든 5사 **5,156/5,661 = 91.1%**(삼성重 93.1 · 미포 94.9 · 세진 82.2 · 일승 91.7 · 동방선기 91.6). 항등식 1% 초과 불일치 0건(1차 40+건 — 비용 괄호(음수) 표기 9사·91표가 주범). issues: borrowings_face_label 551 · no_cons_statements 179 · sga_absorbed_op_lines 162 · shares_omitted_quarterly 138 · no_report 103 · tax_sign_flipped 93 · expense_sign_negative 91 · duplicate_label 83 · no_prior_ytd(_cf) 3/4; shares_table_not_found 55 → 0(KCC 등 열 머리 수리). 분기 19 미만 10사 사유 확정(MODEL.md §5-1).
  재확인: `ls assets/fin | wc -l`(58) · `grep -c " FAIL " assets/fin_collect.log`(0) · `$PY kship_fin.py --golden --stocks 075580,010140,010620,333430,099410`.
- fx 87분기(16:21 산출 그대로; forward 무한루프 가드만 코드 수정) · prices 57/57(21:10, `--no-history` 이어붙임, `naver_check` 57종목 중 49 상이·최대 3.45%) · sls 6사(21:08, `calibrated_shift` 채워짐) · **models 58행 full 29 · partial 29 · no_fin 0**(21:47; 드라이버 고객연동 29 · 추세 23 · 선표 5 · 지주 1; 항등식 major 0사) · xlsx 58개(5.5MB) · **테스트 245 OK**(skipped 1, 26.8s).
- 모집단 회귀 복구(21:35~21:39): 9/12 주간 스캔이 승격 16사를 지워 universe 41 이었던 것을 `kship_scan.carry_forward` + `kship_universe.py --write` 2차 방어선으로 57 복구 → `suppliers.json` 재빌드 → 기자재 페이지 51장 재생성. 섹션이 붙은 페이지 40 → **57장**(조선사 5·지주 1·엔진 5·기자재 41·강재 5). 원인·규칙은 MODEL.md §6-16.
- 레퍼런스 패치본 3개(21:06, `--overwrite-placeholders --fx-actuals`): 세진 `_2026Q2`(BS 4시트 3,757셀, 자리표시자 교체 0) · 삼성重 `_2026Q2`(2,232셀, 가이던스 11셀 교체: 4Q23 매출액 8,009,400 → 8,009,429.91 등) · 미포 `_2025Q3`(395셀, 1Q25 잠정 9셀 교체; 2025Q4~ 합병으로 보고서 없음) + `변수` 환율 112·112·24셀 실측 교체. 검증 ①~⑤ ok(수식 수 60,271 = 60,271 · 91,976 → 91,970(−6 자리표시자) · 88,706 → 88,703(−3)). 종가 셀은 9/28 20,100(prices 21:10 재실행 전) — 다시 돌리면 19,330(9/29).
- **페이지·허브는 모델 재빌드(21:47) 전 산출**(21:28~21:39): 57장 중 28장·허브 21행이 이전 모델 값(KCC FY2026E 매출 66,191 vs 모델 77,851억). 아래 재개 ⑥ 이 필요하다.

**재개 — 이 순서로(네트워크 불필요, 1~2분)**
```bash
cd argus/kship/tools && PY=[private local path]
$PY kship_sls.py --all --report                               # (선택) fin 21:18 재빌드와 바이트 정합 — 캘리브레이션 값은 같을 것으로 보이나 미확인
$PY kship_model.py --build --all --xlsx --today 2026-09-30    # sls 를 다시 돌렸을 때만
$PY kship_page.py --all && $PY kship_parts.py --all && $PY kship_model_section.py --hub   # **필수** — 28장·허브 21행 stale
$PY -m unittest discover -s tests -p 'test_*.py'              # 245 OK 확인
$PY kship_model_section.py --check ../002380/index.html
```
확인: KCC 페이지 KPI 의 FY2026E 매출이 `assets/models/002380.json` 의 77,851억과 같아야 한다.

**커밋 전 확인**: 루트 `.gitignore` 에 `argus/*/tools/assets/fin_cache/` · `fin_collect.log` · `**/.collect.lock` 을 추가했다(9/30 20:48 — 결정 ⓕ 해소). 커밋 대상 신규: tools/kship_{fin,fx,price,sls,model,model_xlsx,xlsx_patch,model_section}.py, tests 7종 + fixtures/fin·model_mock*, assets/{fin(58),fx.json,fx_daily_cache.json,prices.json,sls,models}, models/*.xlsx(58, 5.5MB), models.html, MODEL_SPEC.md, MODEL.md, UPDATE.md; 수정: kship_scan.py·kship_universe.py(이월)·universe.json·universe_probe.json·suppliers.json·unclassified.csv·kship_page.py·kship_parts.py·tests/test_kship{,_scan}.py·회사 페이지 57장·index/parts/coverage.html·이 문서·README·.gitignore·update-kship.yml. 레퍼런스 원본·패치본(`[private local path]`)은 레포 밖.

**DART 주의(재확인)**: fin 수집도 `kce_fetch._pace` 0.7s 파일락을 타지만 **프로세스는 하나**여야 한다 — 백그라운드 fin 이 도는 동안 `kship_contracts/yards/suppliers --collect` 를 띄우지 마라. `assets/fin_cache/.collect.lock` 이 단일 프로세스 락이다. 2차 검증은 DART 를 1회(삼미금속 A001 검색)만 두드렸다.

**2차 검증이 고친 것(코드 — 파일 머리말·산출물로 확인, 상세 MODEL.md §10)**: fin 파서 비용 음수 표기 정규화·귀속 블록 오매핑·중단영업 Q4·판관비 흡수·주식수 열 머리 / fx forward 무한루프 가드 / prices 네이버 대조·이력 창 분기 정렬·이어붙임 / sls 캘리브레이션 실측 / model 고객 연동 격자 탐색(시차·창·변환)·지주 실측 비율·별도 보충·일회성 탐지 / xlsx 생성 결정론(스탬프·zip 시각 고정) / 패치 `--overwrite-placeholders`·`--fx-actuals`·검증 ④ 강화 / 섹션 허브 테스트(td/th) / 스캔 이월.

**오너 결정 대기**: ⓐ 3개월 열 vs FnGuide 누적차분 정본(`ytd_diff==3m` 34건 전부 후속 보고서의 전기 재작성) ⓑ 레퍼런스 가이던스 셀 덮어쓰기 · ⓒ 변수 환율 실적 분기 교체 — 둘 다 **플래그로 구현돼 현재 패치본에 적용됨**(원문은 보고 `replaced[].was`·`fx.replaced[]` 에 보존, `_orig.xlsx` 무손상) → 그대로 둘지 플래그 없이 다시 만들지 ⓓ 2028 신규수주 반영 ⓔ 코호트 외부 신조선가 지수 ⓖ 모델 재생성 주기(워크플로 기본: 월요일 + fin 변경 + 수동) ⓗ 골든 잔여 8.9%(주석 재분류) 파싱 착수 ⓘ 격자 탐색 다중비교 보정(현재 경고만).

## 2026-09-30 22:20 마감 (오너)

위 '재개' 블록은 실행 완료 — 시세 재수집(토스 이력 포함) → sls → model(--xlsx) → 레퍼런스 패치(`--overwrite-placeholders --fx-actuals`) → 페이지·허브 → 테스트 245 OK. 결정 3건(정규장 종가 정본 · 고객 연동 유의성 조건 · PER 밴드 캡)과 최종 수치는 MODEL.md §11. `argus/kship/009540/` 는 만들지 않는다(삭제). 커밋 대상에서 009540/ 을 빼고 읽어라. 다음 분기(2026Q3 보고서, 11월 중순~)엔 `kship_fin.py --collect --build --all --quarters 2021Q4..2026Q3` 부터.

## 2026-10-02 마감 (라운드 3·4 — 남은 결정 실행 · 주석 부모 절 폴백 · 결함 D1~D10)

상세는 MODEL.md §12(결정·근거·영향 표, 결함→조치→영향 표, 재현, 한계). 여기에는 다시 시작하는 데 필요한 것만 적는다.
라운드 3(지시서 기재: 2026-10-01, 커밋 `be8e1c63` — 이 문서의 입력 파일로는 확인 못 함)은 MODEL_SPEC §5 계약대로 ⓐⓓⓔⓗⓘ 를 실행했다.
라운드 4(2026-10-02)는 스튜디오 큐가 `external_session_busy` 로 3시간 열리지 않아 **맥미니 헤드리스 Opus 5.5** 로 돌렸다. 스튜디오 큐에 같은 작업 6건이 남아 있다(취소 CLI 없음) — 열리면 중복 실행이 되지 않게 먼저 확인한다.

**지금 상태(파일 실측)**
- fin: 부모 절 주석 786분기 수집 완료(실패 0, 오너 실행). `fin_cache` 333MB(git 밖). 이자수익 638/946분기 · 51/58사 채움. 골든 5사 **5,378/5,900 = 91.2%**(세진 82.6 · 삼성重 93.4 · 미포 94.7 · 일승 91.7 · 동방선기 90.2; 9/30 5,156/5,661 = 91.1%).
- models: `summary.json` built 2026-10-02 · 58행 **full 48 · partial 10 · no_fin 0**(status 는 이제 데이터 완전성만 — D7). 드라이버 추세 36 · 고객 연동 16 · 선표 5 · 지주 1. `driver_fallback` none 22 · no_link 23 · oos 9 · significance 4. identities_ok 58/58. 백테스트 중위(n=56) 매출 15.8% · OP 59.25%.
- 조선사 FY2026E / 2027E / 2028E 매출(억원): 삼성重 127,235 / 155,098 / 192,093(EPS 1,031.3 / 1,560.4 / 1,975.9원) · HD현대重 253,983 / 298,688 / 372,841 · 한화오션 169,965 / 163,334 / 92,554(패널 없음) · HJ 25,135 / 21,886 / 16,350(패널 없음) · 대한조선 11,970 / 13,295 / 17,837 · 지주 356,065 / 421,089 / 525,629. 모델 산출값이며 추천이 아니다.
- 코드: T1(`kship_fin.py` 부모 절 폴백) · T4(`kship_model.py` 영업외 세부 행) · T6(`kship_model.py`·`kship_sls.py` D1~D10)를 오너가 정본에 올렸다. 오너는 그 위에 status 최신 완결 분기 판정(제출기한 45/90일)과 렌더러 `PNL_ORDER`(외환손익·기타금융손익)를 고쳤다. `update-kship.yml` 에 주석 단계를 추가했다(**러너 미실행**).

**재개 — 이 순서로**
```bash
cd argus/kship/tools && PY=[private local path]
[private local path] track preflight --host mini --cwd "$PWD" --owner <내 세션 ID>    # 스튜디오 큐 잔여 6건·다른 세션 먼저 확인
$PY -m unittest discover -s tests -p 'test_*.py'          # 10-05 실측 343 OK(skipped 24) — MODEL.md §5-6 ▶ 10-05 · §13
$PY kship_fin.py --build --all --golden                   # TOTAL ALL 5378/5900 = 91.2% 재현 확인(캐시만, DART 무접촉)
$PY kship_sls.py --all --report                           # 레포 sls 는 10-02 커밋(2dbb8e26)에 재생성돼 post_origin 키가 이미 있다(10-05 확인) — 다시 돌리면 바이트 정합만 본다
$PY kship_model.py --build --all --xlsx --today 2026-10-02
$PY kship_xlsx_patch.py --all --verify --overwrite-placeholders --fx-actuals --is-convention 3m --today 2026-10-02   # 로컬 전용, 레포 밖
$PY kship_page.py --all && $PY kship_parts.py --all && $PY kship_model_section.py --hub
```
확인할 것: summary `counts` 가 full 48 · partial 10 그대로인지(sls 재생성 뒤 바뀌면 원인 기록). 새 행 4개(이자·외환·파생·기타금융손익)가 생성 xlsx 에서 어떻게 나오는지 — 레인이 확인하지 않았다. ⑤ 패치본: 10-02 재생성 여부는 기록이 없고, 10-05 09:13 에 세 파일이 다시 쓰여 있다(파일 안 `UPDATE: 26-10-05` 스탬프, 원본 `*_orig` 9/30 16:02 그대로 — 다른 레인 작업으로 보인다).

**커밋 전 확인**
- `git status --ignored` 로 `!! assets/fin_cache/` 확인. 주석 캐시(`*_note_*.html`, `*_note_parent_*.html`)가 커밋 대상에 섞이지 않아야 한다(333MB).
- 커밋 대상(라운드 3·4): tools/kship_fin.py · kship_sls.py · kship_model.py · kship_xlsx_patch.py · kship_model_section.py, tests(test_kship_fin 71 · test_kship_model · test_kship_sls) + `tests/fixtures/fin/hanil_2023Q4_note_parent_{cons,sep}.html`, assets/fin(58) · sls · models, models/*.xlsx, 회사 페이지·models.html, MODEL.md · MODEL_SPEC.md · HANDOFF.md · UPDATE.md · README.md, `.github/workflows/update-kship.yml`. 레인 작업 디렉터리(`output/_run/`, `t6pkg/`)는 옮기지 않는다.
- 테스트 한 건 주의: T6 스냅숏 B 에서 `test_real_sejin_2026q2_detail` 이 실패했다(레포 fin 이 05:01 다시 쓰여 세진 주석이 1 → 9분기. 수정 전 코드에서도 같음). 10-05 단독 실행 OK — 단언이 주석 분기 수(4 기준)로 갈라지는 형태라 데이터 표류에 흔들리지 않는다(`python -m unittest tests.test_kship_model -k test_real_sejin_2026q2_detail`).
- `argus/kship/009540/` 는 여전히 만들지 않는다.

**오너 결정 기록**
- 확정(라운드 3·4): ⓐ 모델 `is` · 패치 운영 `--is-convention 3m`(누적차분은 재작성 분기에 음수 매출 — 일승 2024Q2 −100.58억) · ⓓ 신규수주 base 포함, 보수/낙관은 시나리오(한화·HJ 는 패널 값 없음 → 공시 수주만) · ⓔ 코호트 `reference_anchor` 기본 · `ledger_relative` 대안, 대한조선 잔고 캡 0.8593 · ⓗ 주석 하위 노드(999분기 중 786 하위 노드 없음) → 부모 절 폴백 · ⓘ OOS 선택 규칙(`WAPE_link > WAPE_trend × 1.10` 이면 미채택; 라운드 3 채택 18 · 기각 7 · 유의성 기각 4 → 라운드 4 채택 16(판정 불가 2 포함) · OOS 기각 9 · 유의성 기각 4).
- 대기(MODEL.md §12-8): ① D1 공시 수주와 패널 신규의 인식 시점 불일치 ② D2 이월결손 회사 세율(한화·HJ 실제 약 1% vs 22%) ③ D3 보완 폭(삼성重 2028E OP +2,829억) ④ D5(c) 판정 불가 = 연동 채택 유지 여부 ⑤ D7 화면 라벨·`driver_fallback` 표시 ⑥ 레포 sls 재생성 시점 ⑦ 주석 이자비용 연율 클립(009540 debt 13.1%) ⑧ 별도 주석 추가 수집(약 625요청) ⓖ 모델 재생성 주기(워크플로: 월요일 + 재무·주석 변경 + 수동).
- 알려진 결함(미수정): kship_fin 의 KCC·한화시스템 비용 계정 음수 저장(모델이 반전으로 우회) · 한화오션 `총차입금` 공백(2024Q3 → 2026Q2) · KCC FY2026E 지배NI 31,166억(2026Q2 금융손익 3.6조 일회성).

**다음 분기(2026Q3 보고서, 분기말 +45일 = 11월 중순~)** — 10-05 V9 체크리스트로 대체(아래 절).

## 2026-10-05 V9 — 문서·워크플로 검증 (실측 · MODEL.md §13)

레인 소유는 문서 5개·워크플로 2개 + 신규 `tools/run_all.sh`·`tools/tests/test_run_all.py`. 기준 산출은 main 816207cb(10-02 빌드). 같은 날 다른 레인이 작업 트리의 모델·sls·fx·prices·페이지를 재생성했으니(09:29~09:35, summary built 2026-10-05 · counts 48/10/0 그대로) 통합 뒤 `./run_all.sh --only check` 로 다시 잰다.

**지금 상태(파일 실측)**
- 문서 수치: §5·§12 의 summary·sls·fin 골든·시나리오·백테스트 수치는 전부 HEAD 산출과 일치했다. 틀렸거나 비어 있던 것 — 테스트 건수(245/기록 없음 → **343 OK, skipped 24**) · `--cohort-mode`(미확인 → CLI 인자 확인) · "레포 sls 구버전"(이미 10-02 재생성) · "러너 미실행"(러너는 10-01·03·04 돌았고 재무·주석이 캐시 폴더 부재로 수집 전 실패 → 89f95231) · 이자수익 "638/946" 은 어느 정의로도 재현 안 됨(cons.is 575/828 · cons∪sep 675/997 · 52사 — §13-1 병기).
- 러너: fin 캐시가 저장된 적이 없다. 수정 뒤 첫 실행 = **10-05 10:40 KST(월요일 → 모델 재생성도 겹침)**. 첫 수집 ≈ 60분 + 주석 ≤ 75분. 성공 판정은 커밋 메시지의 단계 outcome(10-05 부터 `재무✗`·`(변경)` 식)과 Actions 요약·fin json 변경 유무로 — 이 레인은 Actions 로그를 보지 않았다.
- 워크플로 수정: update-kship — 재무 단계 제한 90분 · job 240 · 커밋 메시지 outcome 기반 · 게이트 `${WHY}·`(bash 3.2 호환). scan-kship — openpyxl 설치(없으면 unittest ImportError → 10-04 일요일 커밋 없음) · 분기 규칙으로 `--quarter` 전달 · 3.11 · 명시 pathspec add · 메시지에 승격·이월·제외·실패 수.
- `.collect.lock`(pid 61123, 죽음) 파일이 남아 있다 — `kship_fin._SingleProcess` 는 flock 이라 무해, 지우지 않아도 된다.
- 맥 기본 bash 3.2 함정: `"$VAR·…"` 처럼 변수 바로 뒤에 멀티바이트 글자가 오면 변수 이름에 붙여 읽어 값이 빈다(`${VAR}·` 로 쓴다). run_all.sh·워크플로는 그렇게 고쳤고 `test_run_all` 이 지킨다.

**재현 한 줄**
```bash
cd argus/kship/tools
./run_all.sh --help                       # 단계·플래그
./run_all.sh --dry-run --net --patch      # 실행할 명령만(아무것도 안 바꿈)
./run_all.sh                              # 오프라인: sls → model(+xlsx) → pages·hub → link → tests → check
./run_all.sh --only check                 # 산출 요약만(summary counts · sls origin · fx/prices as_of · fin 골든 합계 · xlsx·섹션 수)
```

**다음 분기(2026Q3 보고서 — 분기·반기 제출기한 분기말 +45일, 워크플로·run_all 의 규칙은 +50일 = 11-19 부터) 체크리스트**
1. `./run_all.sh --print-quarter` 가 `2026Q3` 을 찍는지(11-19 이후). 그 전에 억지로 돌리려면 `--quarter 2026Q3`.
2. 다른 DART 수집기(`kship_contracts/yards/suppliers --collect`, 러너 10:40 KST 실행 포함)가 돌고 있지 않은지 — `/Users/kioxia/.local/bin/phx-agent track preflight` · `ps` 로 확인. DART 는 IP 당 프로세스 하나.
3. `./run_all.sh --collect --fin --notes --skip sls,model,pages,link,tests,check` — 모집단·계약·정기보고서(2026Q3)·기자재 → ① 재무제표 2021Q4..2026Q3 → ①′ 주석. 끝에 `fin json 58개 · FAIL 0건` 과 `notes parent` 로그 두 줄을 그대로 적는다. 캐시 목록이 바뀌면 fin json 이 재생성된다(`collected_at` 변경).
4. `$PY kship_fin.py --golden --stocks 075580,010140,010620,333430,099410` — TOTAL 이 5,378/5,900(91.2%) 에서 어떻게 움직였는지(분모가 커진다). 세진 `cons:2022.09` 최악 기간이 그대로인지.
5. `./run_all.sh --market` → fx 2026Q3 완결값(평균 1,418.75 · 기말 1,355.40) 이 유지되고 2026Q4 가 partial 로 쌓이는지, prices 57/57 · `close_source` 네이버 정규장.
6. `./run_all.sh --today <실행일>` — sls origin 이 **2026Q3** 으로 넘어갔는지(`--only check` 의 "sls origin"). 모델 `last_actual` 2026Q3 57사(미포 제외) · summary counts 변화와 원인 기록. 생성 xlsx 58 · 섹션 56장 · 허브.
7. **forecast_panel 정렬**: 패널(`assets/forecast_panel.json.gz`)은 origin 2026Q2 산출이다. `kship_model._panel_new_orders` 는 분기 **라벨**로 맞추므로(`row.quarter ∈ fq`) origin 이 2026Q3 이 되면 2026Q4~ 값만 쓰고 `new_orders.panel_origin` 에 2026Q2 를 남긴다 — 시점이 한 분기 어긋나는 것이 아니라 **2026Q3 공시 수주(D1 `post_origin`)와 패널 2026Q4 신규의 중복 여부**를 사람이 판단해야 한다. 패널이 재산출되기 전에는 조선사 2027E~28E 의 `매출조선신규` 를 읽지 않는다.
8. `--patch`(맥미니 로컬 전용): 미포는 2025Q3 그대로(합병 소멸), 세진·삼성重 `_2026Q3`. 검증 ①~⑤ ok 와 교체 셀 수를 보고에 적는다. `*_orig.xlsx` 수정 금지.
9. 커밋 전 `git status --ignored --short argus/kship | grep '!!'` 로 `fin_cache/`·`fin_collect.log`·`__pycache__` 만 무시되는지, 주석 캐시(`*_note_*`)가 커밋 대상에 없는지. `argus/kship/009540/` 는 만들지 않는다.
10. 러너: 그 주 월요일 커밋 메시지에 `재무(변경)`·`주석(변경)`·`모델` 이 찍히는지, Actions 요약의 "모델: … (why)" 와 fin json 변경 유무. 캐시 저장이 안 됐으면(첫 실행 60분 초과·단계 제한) 다음 날 체크포인트에서 이어받는다.
11. 분기 뒤 문서: MODEL.md §5-1·§5-4·§12-5 에 ▶ 날짜 줄로 새 수치(골든 합계·counts·조선사 FY 표)를 붙이고, 틀린 옛 수치는 지우지 말고 날짜를 붙여 둔다.

참고용 · 투자조언 아님.

## 2026-10-05 통합 마감 (10레인 검증·수정 → 전 파이프라인 재생성 · 실측 · MODEL.md §14)

레인 10개가 소유 파일을 고친 작업 트리(수정 276 · 신규 56 파일, 커밋 없음) 위에서 통합 레인이 전 테스트 → 재생성 → 문서를 돌렸다. 아래 숫자는 통합 세션 명령 출력이다(10:29~10:50 KST). 레인 보고 원문은 V1·V2 만 입력에 있었고 나머지는 파일로 판정했다(§14-1).

**지금 상태(파일 실측)**
- 테스트 **489 OK(skipped 2, 130.7s)** — 1차 488 · FAIL 1(현대힘스 가중치 저장값 합 1.0001)을 `kship_model.r4_weights` 로 고치고 테스트 1건 추가. HEAD 343 → 489.
- fin 58 json(`collected_at` 2026-10-05, V1 수리 반영) · 골든 **5,378/5,900 = 91.2%**(불변) · checks 항등식 4규칙 상주(`fin=fi-fe` 실패 2 = 한신기계 원문 모순) · 비용은 양수 · 한화오션 총차입금 19/19 · KCC 2026Q2 이자손익 −65,673.91백만.
- prices as_of 2026-10-05 · 57/57 · 행 as_of 20261002 · 이력 네이버 일봉 57/57(토스 제거) · fx 88분기(2026Q3 완결 1,418.75 / 1,355.40).
- sls 6사(built 2026-10-05, 삼성重 53(50), 대한조선 캡 0.8593, `opm_table` assumed — reference_calibrated 10.8% 병기).
- models `summary.json` built 2026-10-05 · **full 48 · partial 10 · no_fin 0** · 드라이버 추세 34 · 연동 18 · 선표 5 · 지주 1 · 경고 183 · identities_ok 58/58 · 백테스트 중위 15.8 / 59.25. 한화오션 FY2026E EPS 6,083.1(10-02 6,295.5 — debt 연율 생김). 조선사 FY 표는 §14-3.
- xlsx 58(조선사 4사 `시나리오` 시트 11시트) · 레퍼런스 패치본 3개 10-05 10:37 ALL OK(교체 0/11/9 · 환율 112/112/24 · 종가 10/2 세진 10,010 · 삼성重 19,920 · 미포 없음; `*_orig` 9/30 16:02 그대로) · 회사 페이지 56장 섹션 · 허브 58행.
- `selfcheck_models.py`(V10) 486,140건 · consistency 실패 **19**(전부 `fin_model_mislabel` — 지배주주순이익 파생 셀의 src 표기, 값 일치, 모델 레인 결함) · freshness 0 · rc 1.

**재개 — 이 순서로(네트워크 없음, 약 1분)**
```bash
cd argus/kship/tools && PY=~/Library/phalanx_venv/bin/python
/Users/kioxia/.local/bin/phx-agent track preflight --host mini --cwd "$PWD" --owner <내 세션 ID>
$PY -m unittest discover -s tests -p 'test_*.py'          # 489 OK(skipped 2) 기대
./run_all.sh --today 2026-10-05                           # sls → model(+xlsx) → pages·hub → link → tests → check (오프라인) — counts 48/10/0 · 골든 5378/5900 · xlsx 58 · 섹션 56
$PY selfcheck_models.py --max-detail 3                    # 실패 19 = fin_model_mislabel 만이어야 한다(다른 그룹이 실패하면 stale 또는 결함)
./run_all.sh --patch --only patch --today 2026-10-05      # 로컬 전용(레퍼런스 폴더 있을 때만)
```

**커밋 전 확인(이 작업 트리)**
- `git status --short | grep -v fin_cache` 332건(10-05 10:50): 수정 — tools 12(`kship_fin/fx/price/sls/model/model_xlsx/xlsx_patch/model_section/parts/suppliers.py` · `build_dicts.py`) · tests 9 · assets(fin 58 · models 58+summary · sls 6+summary · fx · fx_daily_cache · prices · suppliers · parts_taxonomy · parts_override · unclassified) · models/*.xlsx 58 · 회사 페이지 56 · models/parts/index/coverage.html · 문서 5 · 워크플로 2; 신규 — `tools/run_all.sh` · `tools/selfcheck_models.py` · `tests/test_pipeline_e2e.py` · `tests/test_run_all.py` · `tests/fixtures/suppliers_products_033500_2026Q2.html` · `assets/suppliers_cache/<stock>/notes.json` 51. `git status --ignored` 로 `fin_cache/`·`fin_collect.log`·`__pycache__` 만 무시되는지, `*_note_*` 캐시가 커밋 대상에 없는지 본다. `argus/kship/009540/` 는 만들지 않는다.
- 커밋 메시지에 적을 것: 테스트 489 · 골든 5,378/5,900 · summary 48/10/0 · selfcheck 19(mislabel) — 성공 문구 대신 숫자.

**오너 결정 대기 · 남은 결함(§14-6)**
- 결정: V3 `--opm-table reference_calibrated`(2026Q3 타겟 15% → 10.8%) 적용 여부 · V6 `--extend-formulas` 운영 플래그 포함 여부 · 신규 연동 2사(한라IMS·한화시스템 → 한화오션; `related` 링크의 연동 후보 자격) · §12-8 의 대기 항목(D1 인식 시점 · 이월결손 세율 · D3 폭 · undetermined · 이자비용 연율 클립 · 별도 주석 625요청).
- 결함(모델 레인): `_actual_series` 지배NI 파생 셀 src 표기 · `_fin_detail` 부호 반전 휴리스틱 제거(환입 3사 오반전) · `_suppliers_weights` share 0.0/건수 혼합. 유통주식수 기준일 차이 2사(KS인더스트리·케이앤에스) 확인(V2·V4). 러너 10-05 10:40 첫 실행 결과는 보지 않았다(§13-3).

참고용 · 투자조언 아님.
