# 한국화학 캐파 — 인계 (HANDOFF)

## ① 무엇이 어디서 오는가

| 화면 요소 | 원천 | 생성 코드 | 산출 |
|---|---|---|---|
| 후보 모집단(업종·어휘·시드·제외 사유) | KRX KIND 상장법인목록(`kce_universe.KIND_URL`, 1요청) | `tools/kcap_universe.py` | `tools/assets/universe.json` |
| 생산능력·생산실적·가동률(품목·사업소·회사별, 기간 열) | DART 정기보고서 「II-3. 원재료 및 생산설비」 절 — 무키 3단계(`kce_fetch`, 종목코드 검색) | `tools/kcap_capacity.py` | 원문 캐시 `tools/assets/cache/<stock>/<q>_cap.html` (git 제외) |
| 회사별 캐파 원장(연도별 연간 열·당기 연환산·가동률 이력·변동) | 위 캐시 전 분기 | `tools/kcap_build.py` | `tools/assets/capacity/<stock>.json`, `tools/assets/ledger.json` |
| 이벤트 공시(신규시설투자등·생산중단·생산재개·영업정지·유형자산 양도/취득·영업양도/양수, 정정 supersede) | 거래소 수시공시(I001, 연도 창 검색) | `tools/kcap_events.py` | `tools/assets/events/<stock>.json` (+캐시 `ev_<rcp>.html`) |
| 분기 매출액·영업이익(연결 우선, 3개월 열 → 누적차분, 손실 라벨 복구) | 정기보고서 「연결재무제표」 절 → `kship_fin.parse_fin_section` | `tools/kcap_fin.py` | `tools/assets/fin/<stock>.json` (+캐시 `<q>_fin.html`) |
| 제품→스프레드 매핑·바스켓 구성비·운영자 분해 입력·체인 합산 | 수기 사전 | `tools/assets/product_map.json` | — |
| 스프레드 분기평균·신선도 | `argus/kchem/tools/assets/registry.json`, `argus/kchem/data/kchem_data.js`(원장 주간 시리즈, 역산 레지스트리) | `tools/kcap_model.py` | `tools/assets/model.json` |
| 환율(원/달러 분기평균) | `argus/kship/tools/assets/fx.json` | 〃 | 〃 |
| 페이지(허브·회사 66·제품·변동·커버리지) | 위 전부 | `tools/kcap_page.py` | `index.html` 등 |

## ② 지금 상태 (2026-10-17, Studio 격리 클론 · 브랜치 `claude/argus-kcap-20261017`, main 38a6ee08 기준)

- KIND 2,753 → 후보 68(제외 48, 사유 기록) → 2026Q2 생산설비 절 수집 65(정기보고서 없음 2: 금양·에스제이켐) → 핵심 33사는 2024Q2·2024Q4·2025Q2·2025Q4·2026Q1 이력도 수집(165건 전부 성공).
- 원장: 회사 66 · 톤 단위 생산능력 품목 186 · **연간 열 변동 71건**(산출근거·증감 열 누수와 중복을 걸러낸 뒤). **편입 12사**(스프레드 매핑 가능한 톤 제품 보유): 롯데케미칼·금호석유화학·대한유화·한화솔루션·티케이지휴켐스·SKC·GS·S-Oil·OCI·SH에너지화학·국도화학·DL — 매핑 캐파 29,668 kt, 미매핑 화학 16,921 kt.
- 재무·이벤트: 편입사 + 주요 후보 21사의 2024Q3~2026Q2 연결손익(8분기 전부, 손실 분기 '영업손실' 라벨 복구 포함)과 2024~ 이벤트 공시 65건(정정 반영 뒤 유효 47: 신규시설투자 20·생산중단 21·영업양도 14·유형자산 취득 5·영업정지 3·생산재개 2).
- 모델: 편입 12사 전부 보정(n=8 분기 쌍)과 2026Q3·Q4 추정이 있다. 보정 표시 문턱(R² ≥ 0.3·커버리지 ≥ 30%·규모 ≥ 0.2)을 넘는 곳은 **대한유화 1곳**(R² 0.60 — 2026Q3 보정 영업이익 539 억원, 범위 160~918); 나머지 11곳은 같은 수치를 사유와 함께 '참고만' 으로 보인다.
  (GS·S-Oil·DL 은 정유·지주 손익이 지배, 국도화학·OCI·한화솔루션은 커버리지 부족, 롯데·금호·휴켐스·SKC·SH 는 설명력 부족.) 첫 버전의 정직한 상태다 — 스프레드 원장 재가동·바스켓 교정·분기 누적이 쌓이면 올라간다.
- 테스트: `python3 -m unittest discover -s tests -p 'test_kcap_*.py'` — 파서 16 · 원장/모델 11 · 이벤트/재무 44 = **65건 통과**(Python 3.9.6, 네트워크 없음). 빌드→모델→페이지 두 번 실행 바이트 동일. 페이지 70개 전부 5MB 이하, 생성 JS 없음(차트는 인라인 SVG).
- `_config.yml` 에 `argus/kcap/tools/` 명시 줄 추가(kchem 선례 — Pages Jekyll 3 에서 glob 이 동작하지 않음). `site.json`(`🏭 한국화학 캐파`, 85) 로 허브 헤더 링크는 다음 빌드에 자동.
- 워크플로 `.github/workflows/update-kcap.yml`: 09:40 KST, DART 순차·`kship-dart` 그룹, 원문 캐시는 actions/cache, 입력이 같으면 커밋 없음. 첫 실행은 `workflow_dispatch` 의 `history=true` 로(캐시 비어 있음).

## ③ 남은 일 · 운영자 확인 항목

1. **금액 기준·뭉뚱그린 공시의 분해** — LG화학(석유화학부문 백만원)·효성화학·코오롱인더(백만원), SK이노베이션 '화학제품'(6,174kt 뭉침), 태광산업 '석유화학제품'(1,741kt 뭉침)은 원문에 톤 분해가 없어 미편입/부분 편입이다. 근거(IR 자료 등)를 적어 `product_map.json` 의 `company_overrides` 에 넣으면 '운영자 입력(추정)' 으로 반영된다.
2. **바스켓 구성비·체인 검토** — NC(에틸렌 6 : 프로필렌 4), BTX(5:2:3), 합성고무(SBR·BR·NBR 5:4:1), 금호 합성수지(PS·ABS·EPS 3:5:2), LATEX(NB·SB 6:4), S-Oil Polymer(PP·PO 6:4)는 공개 설비 구성에서 유추한 추정값이다. GS PX 의 체인 합산(PX-자일렌 + 자일렌(이성체)-납사)도 같은 성격의 가정 — 회사 IR 로 교정할 것.
3. **스프레드 원장 재가동** — argus/kchem 원장이 2026-08-24 이후 멈춰 2026Q3 이후 프록시는 최근 13주 평균 가정이다. 재가동되면 코드 변경 없이 다음 빌드에 반영.
4. **보정 문턱** — `kcap_model.py` 의 `MIN_R2`(0.3)·`MIN_COVERAGE`(30%)·`MIN_SCALE`(0.2)은 첫 설정이다. 분기 쌍이 12개 이상 쌓이면 다시 보고, 문턱을 바꾸면 LOGIC.md §5 도 같이.
5. **원문 불일치 1건** — 한화솔루션 LDPE 2026 반기 누적 생산실적(164kt)이 1분기(173kt)보다 작다. 차분을 버리고 보고 가동률(35.2%, 계산값)을 썼지만 그 값도 의심스럽다 — 원문(2026 반기보고서 생산설비 절)을 사람이 확인.
6. **이벤트 서식 fixture 보강** — 유형자산 양도/취득·영업양도/양수·생산재개 서식은 실제 fixture 가 적어 라벨이 추정이다(값은 못 읽으면 null). 실제 공시를 하나씩 fixture 로 받아 확인.
7. **종속회사 중복** — 모회사 보고서에 종속회사 캐파가 함께 실린다(롯데케미칼 보고서의 롯데정밀화학 가성소다·롯데에너지머티리얼즈 Elecfoil, 금호석유의 금호피앤비). 제품 페이지의 합산은 이 중복을 안고 있다 — 필요하면 `entity` 로 걸러 모회사 자체분만 집계하도록 옵션 추가.
8. **가동률 폴백** — 분기 보고서가 없는 분기는 같은 해 뒤 보고서의 기간 가동률 → 사업장 집계 → 회사 중앙값 → 80% 가정이다. 누적차분이 가능한 분기(1Q·반기·3Q·연간 네 보고서가 모두 있을 때)만 정밀하다 — 이력 수집(`--history`)을 첫 실행 뒤에도 주기적으로.
9. **DART 접근** — `kce_fetch` 경로는 DART robots.txt 의 Disallow 목록과 겹친다(kchem 반영안 L3 실측). 이 탭도 다른 산업 탭과 같은 경로를 쓴다. 운영자 결정 사항.
10. `tools/assets/cache/`(≈25MB)는 git 에 넣지 않는다 — 러너는 actions/cache 가 비면(첫 실행·7일 미사용) 68사 × 1분기 + 편입사 이력을 다시 받는다(`workflow_dispatch` 의 `history` 옵션).

## ④ 재현 명령

```sh
cd argus/kcap/tools
python3 -m unittest discover -s tests -p 'test_kcap_*.py'
python3 kcap_run.py --daily --history          # KIND → 생산설비 절(후보 전수·편입사 이력) → 이벤트 → 재무 (DART 순차)
python3 kcap_build.py --changes && python3 kcap_model.py --list && python3 kcap_page.py
```

푸시 절차는 phalanx 규약대로(Studio 격리 클론은 로컬 커밋·번들까지, 브랜치 푸시·PR 은 Mini). 번들·패치·PR 본문·적용 절차: `~/Downloads/phalanx_kcap_20261017/`(`MINI_APPLY.md`).
