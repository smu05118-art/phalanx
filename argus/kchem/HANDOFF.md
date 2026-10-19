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
| 페이지 6종 + 종목 11 | 위 전부 | `tools/kchem_page.py` | `index/spreads/matrix/chains/coverage.html`, `<종목>/index.html` |
| 살아 있는 프록시 15(中선물·무역통계 단가) | `connections.js` × `aliases.live_proxies` | `Registry.live_proxies` | registry `proxies`, index 프록시 표 |
| 체인 보기(원장 as-of vs 허브) | registry 행 + 허브 `chains[]` | `Registry.chain_view` | registry `chain_view`, index 체인 카드 |
| 원장 편집 추적 | `ledger_last` | `build()` `summary.editions` | 고지·KPI |
| 입력 fingerprint | 입력 4종 sha256 + 내용 해시 | `kchem_inputs.load_all`·`content_fingerprint` | `tools/assets/fingerprint.json`, 각 페이지 꼬리 |
| 원장 누락 텔레그램 | `jem_data/argus/inbox_receipt.json` | Mini `argus/argus_ledger_watch.py`(argus_daily.sh) | `jem_data/argus/ledger_watch_state.json` |

## ② 지금 상태 (2026-10-16 리뷰 보강 반영)

- 2026-10-16 리뷰 보강: 재현 **189/209(전부 exact)** · 고유 스프레드 179(복제 27그룹) · 이월 18행/25주 제외 · 크랙 USD/bbl · 일시 이탈 진단 2(PPG−PO, PC−BPA) ·
  살아 있는 프록시 15(게이트 통과 1) · 체인 보기 · 편집 누락 6(asof 기준) · 종목 페이지 11(비화학 10폴더 삭제) · 내용 fingerprint·커밋 게이트·`--check` · 테스트 34.
  Mini 에 원장 누락 텔레그램(`argus_ledger_watch.py`) — 레포 밖.

### 2026-10-09 기준(이력)

- 행 242(스프레드 209 · 가격 12 · 中선물 18 · PPI 3), 재현 183/209, 파생 47/47, 종목 페이지 21, 페이지 전부 5MB 이하(최대 spreads.html 404KB, data js 620KB).
- 플래그: composite_extra_feed 10 · feed_unspecified 8 · feed_mismatch 2 · formula_changed 3 · missing_product_as_zero 1 · insufficient_overlap 14 · product_series_missing 3 · unit_conversion_unverified 7.
- 원장 정지 6주(마지막 2026-08-24). 살아 있는 스프레드 0. 이 상태는 화면 맨 위 고지로 보인다.
- 테스트 21건 통과(`python3 -m unittest discover -s tests`, Python 3.9.6 CLT). 같은 입력으로 두 번 빌드 → 바이트 동일 확인.
- 허브 헤더 링크는 `site.json`(`🧪 한국화학`, order 80)으로 맥미니 빌더가 다음 빌드(07:40 KST)에 자동 생성한다 — `argus/index.html` 은 건드리지 않았다.
- 워크플로 `.github/workflows/update-kchem.yml`: 09:10 KST, 네트워크 없음, 입력이 같으면 커밋 없음.

## ③ 남은 일 · 운영자 확인 항목

1. **`_config.yml`** — 해결(2026-10-09, Mini). `argus/*/tools/` glob 은 GitHub Pages(Jekyll 3)에서 **동작하지 않는다**: glob 으로만 덮인 `argus/ui/tools/*` 3개가 라이브에서 200, 명시 줄이 있는 `argus/kce/tools/*` 는 404. 그래서 COMMON.md §3 대로 `argus/kchem/tools/` 명시 줄을 다른 탭 줄 뒤에 추가했다(남의 줄은 건드리지 않음). `argus/ui/tools/` 노출은 별건.
2. **`site.json` 라벨·순서** — `🧪 한국화학` / 80. 라벨 문구는 운영자 확인.
3. **원장 결함 보고(수정은 Mini 작업, 이 탭은 표시만)** — BR−BD(한국): BR 가격 2026-04-06 정지 후 스프레드가 −BD 로 계산됨 · PX−자일렌(대만): 2025-12-29 부터 PX − Naphtha 일본(다른 5지역은 −1.25×자일렌) · 에틸렌−납사(미국): 2026-01-12 부터 Ethylene − Ethane · MEG−EO(대만): 2024-11-11 산식 변경 · 2026-08-10 주 다수 시리즈 단주 이상치.
4. **원장 재가동** — 수동 Weekly xlsm 드롭(`~/phalanx/jem_data/argus/inbox/`)이 `Weekly_260827.xlsm` 이후 없다. 최신본 1개면 누적 복구된다.
   ARGUS 일일 실행이 병합 → 허브 빌더 커밋 → push 트리거로 이 탭이 재조립된다(코드 변경 불필요). 누락 중에는 새 편집마다 텔레그램 1줄.
5. **빌더 반영 제안("로컬 빌더 반영 필요", `argus/_specs/kchem.md` §6)** — 청크 `region` 필드 · 카드 m4 표시 · `spread.series[].stocks` · 청크 축을 live 소스 기준으로 확장 · chain None 51 배정 · BR−BD 결측 null 처리·PX(대만) 참조 검사 · 스프레드 카드 → kchem 딥링크. Mini `task_claim` 후 빌더(`~/phalanx/argus/`)에서.
6. **미재현 20** — 겹침 없음 14(크랙 6·VAM 5·BA 2·에틸렌−납사 유럽) · 제품 시리즈 없음 3 · PPG−PO·PC−BPA(일시 이탈 진단만) · PU−MDI&PPG. 원장 수식이나 2022 이전 관측 없이는 못 푼다.
7. **원장값 csv 재배포 금지** 유지(라이선스 확인 전). DART 분기 앵커·회사별 가중 마진·가동률(R7·R8·R11·R28)은 `kce_fetch` 경로의 DART robots 충돌을 운영자가 결정한 뒤.
8. 월간 한국 네이티브 레이어(관세청 HS 확장·日 e-Stat PX/벤젠/SM)는 tradedata robots·약관 본문을 1회 수동 확인한 뒤 별도 fetcher 로(ECOS 는 키 예외 승인 시에만).

## ④ 재현 명령

```sh
cd argus/kchem/tools
python3 -m unittest discover -s tests -p 'test_*.py'
python3 kchem_page.py            # 입력 검증 → 레지스트리 → data/kchem_data.js → 페이지 17장
python3 kchem_page.py --check    # 같은 입력 재빌드가 바이트 동일한지(쓰지 않음)
python3 kchem_page.py --gate old_fp.json   # 커밋 필요 여부(내용 변경 또는 ISO 주 변경) → commit=1/0
python3 kchem_registry.py --list-unreproduced --list-flagged   # 역산 결과만 보기(쓰지 않음)
```

푸시 절차는 phalanx 규약대로(Studio 격리 클론은 로컬 커밋·브랜치 푸시까지, main 반영은 Mini `jem_push` 또는 PR 머지).
