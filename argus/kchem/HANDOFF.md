# 한국화학 — 인계 (HANDOFF)

## ① 무엇이 어디서 오는가

| 화면 요소 | 원천(전부 레포 안 빌더 산출물, 읽기 전용) | 생성 코드 | 산출 |
|---|---|---|---|
| 242 시리즈 목록·pos·m4·신선도·last | `argus/data/argus_data.js` `spread.series`(화학 13 카테고리) | `tools/kchem_inputs.py` | — |
| 5년 추이(255주) | `argus/data/chunk_<카테고리>.js` 13개 `series[].v` | `kchem_page.build_data_js` | `data/kchem_data.js` |
| 산식 역산(k·참조 지역·잔차·이상치·산식 변경) | `argus/data/connections.js` `rows[].observations`(주간 104) | `tools/kchem_registry.py` | `tools/assets/registry.json` |
| 제품·원료 사전, 체인 추정, 中선물 매핑, 파생 정의 | `tools/assets/aliases.json`(수기) | — | — |
| 체인 pos·mom·종목 라벨 | `argus_data.js` `chains[]` | `kchem_registry` | registry `chains` |
| lane·reason·basis 문구 | `connections.js` | — | registry 행 |
| 맵 존재 여부·링크 | `argus/data_map.js` `items[]` | — | `in_map`, `map.html#series=` |
| 中선물·PPI 추이(축 잘림 우회) | `connections.js` observations | `build_data_js` | `data/kchem_data.js` |
| 파생 스프레드 47 | 원장 가격 관측(connections) × `aliases.derived` | `Registry.derived_rows` | registry `derived`, data js |
| 페이지 6종 + 종목 21 | 위 전부 | `tools/kchem_page.py` | `index/spreads/matrix/chains/coverage.html`, `<종목>/index.html` |
| 입력 fingerprint | 입력 4종 sha256 | `kchem_inputs.load_all` | `tools/assets/fingerprint.json`, 각 페이지 꼬리 |

## ② 지금 상태 (2026-10-09, ARGUS asof 2026-10-05 빌드 입력)

- 행 242(스프레드 209 · 가격 12 · 中선물 18 · PPI 3), 재현 183/209, 파생 47/47, 종목 페이지 21, 페이지 전부 5MB 이하(최대 spreads.html 404KB, data js 620KB).
- 플래그: composite_extra_feed 10 · feed_unspecified 8 · feed_mismatch 2 · formula_changed 3 · missing_product_as_zero 1 · insufficient_overlap 14 · product_series_missing 3 · unit_conversion_unverified 7.
- 원장 정지 6주(마지막 2026-08-24). 살아 있는 스프레드 0. 이 상태는 화면 맨 위 고지로 보인다.
- 테스트 21건 통과(`python3 -m unittest discover -s tests`, Python 3.9.6 CLT). 같은 입력으로 두 번 빌드 → 바이트 동일 확인.
- 허브 헤더 링크는 `site.json`(`🧪 한국화학`, order 80)으로 맥미니 빌더가 다음 빌드(07:40 KST)에 자동 생성한다 — `argus/index.html` 은 건드리지 않았다.
- 워크플로 `.github/workflows/update-kchem.yml`: 09:10 KST, 네트워크 없음, 입력이 같으면 커밋 없음.

## ③ 남은 일 · 운영자 확인 항목

1. **`_config.yml`** — `argus/*/tools/` glob 이 이미 있어 `argus/kchem/tools/` 는 배포에서 빠진다. COMMON.md §3 은 "줄을 추가하라"지만 파일 주석("이 블록은 건드리지 마라")에 따라 **수정하지 않았다**. 둘 중 어느 쪽이 정본인지 확인.
2. **`site.json` 라벨·순서** — `🧪 한국화학` / 80. 라벨 문구는 운영자 확인.
3. **원장 결함 보고(수정은 Mini 작업, 이 탭은 표시만)** — BR−BD(한국): BR 가격 2026-04-06 정지 후 스프레드가 −BD 로 계산됨 · PX−자일렌(대만): 2025-12-29 부터 PX − Naphtha 일본(다른 5지역은 −1.25×자일렌) · 에틸렌−납사(미국): 2026-01-12 부터 Ethylene − Ethane · MEG−EO(대만): 2024-11-11 산식 변경 · 2026-08-10 주 다수 시리즈 단주 이상치.
4. **원장 재가동** — 수동 Weekly xlsm 드롭(`~/phalanx/jem_data/argus/inbox/` + `argus_run.sh`)이 2026-08-24 주차 이후 없다. 재가동되면 이 탭은 다음 빌드에 자동 반영된다(코드 변경 불필요).
5. **빌더 반영 제안("로컬 빌더 반영 필요", `argus/_specs/kchem.md` §6)** — 청크 `region` 필드 · 카드 m4 표시 · `spread.series[].stocks` · 청크 축을 live 소스 기준으로 확장 · chain None 51 배정 · BR−BD 결측 null 처리·PX(대만) 참조 검사 · 스프레드 카드 → kchem 딥링크. Mini `task_claim` 후 빌더(`~/phalanx/argus/`)에서.
6. **미재현 26** — 페놀−벤젠 미국/인도(상수 잔차), LDPE−에틸렌(유럽), PC−BPA, PPG−PO, PU, Crude C4, 나프타 크랙(환산계수), dead 계열. 원장 수식을 보지 않고는 못 푼다.
7. **원장값 csv 재배포 금지** 유지(라이선스 확인 전). DART 분기 앵커·회사별 가중 마진·가동률(R7·R8·R11·R28)은 `kce_fetch` 경로의 DART robots 충돌을 운영자가 결정한 뒤.
8. 월간 한국 네이티브 레이어(관세청 HS 확장·日 e-Stat PX/벤젠/SM)는 tradedata robots·약관 본문을 1회 수동 확인한 뒤 별도 fetcher 로(ECOS 는 키 예외 승인 시에만).

## ④ 재현 명령

```sh
cd argus/kchem/tools
python3 -m unittest discover -s tests -p 'test_*.py'
python3 kchem_page.py            # 입력 검증 → 레지스트리 → data/kchem_data.js → 페이지 27장
python3 kchem_registry.py --list-unreproduced --list-flagged   # 역산 결과만 보기(쓰지 않음)
```

푸시 절차는 phalanx 규약대로(Studio 격리 클론은 로컬 커밋·브랜치 푸시까지, main 반영은 Mini `jem_push` 또는 PR 머지).
