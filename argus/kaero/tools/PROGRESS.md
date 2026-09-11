# KAERO 진행 체크포인트 — 우주·항공부품 (`argus/kaero`)

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/kaero` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 완료

- [x] `argus/_specs/COMMON.md`·`kaero.md` 정독 · 본보기 코드(kdef/kship/kce) 확인
- [x] **원문 실측 7건** → `tools/FINDINGS.md`
      (아스트 USD/원 분리표 · 한화에어로 수주상황(상세) RSP 원장 · 겸업사 중복계상 ·
       하이즈 캡션 물림 · 켄코아 표 안 통화 혼재 · 케이피 수주표 없음 · `[첨부정정]` 목차 함정)
- [x] `kaero_lib.py` — kce/kship import 층 + 통화 표기 + 영역 팔레트 + `open_sections`
      (정정본이 1순위로 와 II절이 없는 문제를 후보 순회로 막는다)
- [x] `assets/kaero.css` (kdef 것을 복사, 경로만 kaero)
- [x] `kaero_universe.py` — 네 겹 모집단 → `assets/universe.json`
- [x] `kaero_scan.py` — ④ 탐색. **표 근거(II-4 부문·품목 이름)가 문구 근거를 이기는** 승격 규칙
- [x] `kaero_reports.py` — **통화별** 수주표 · 상세표(계약 원장) · 부문 필터(중복 계상) ·
      영역/계약성격/고객 판정 · 매출처 표 · 연매출 열
- [x] `kaero_contracts.py` — I001 얇은 원장(외화 계약금액 통화 보존)
- [x] `build_dicts.py` — 영역 6 · 계약성격 6 · 고객계층 4 · 부품 6/23 · 실루엣 4/영역 25

## 진행 중

- [ ] `kaero_scan.py --scan` 74사 (백그라운드 `/tmp/kaero_scan2.log`)
- [ ] `kaero_reports.py --collect` 6분기 (백그라운드 `/tmp/kaero_collect.log`)

## 남은 일

1. [ ] 스캔 끝나면 `kaero_universe.py --write` → 늘어난 회사만 `--collect`
2. [ ] `kaero_suppliers.py` — 부품 분류 · 고객(OEM/체계업체) 연결
3. [ ] `kaero_contracts.py --collect --build`
4. [ ] `kaero_page.py` — 허브 · 회사 · 커버리지(겸업사 kdef/kship 중복 표시)
5. [ ] `kaero_parts.py` — `parts.html`
6. [ ] `tools/tests` · `site.json` · `_config.yml` exclude · `update-kaero.yml` · `vendor/chart.umd.min.js`
7. [ ] README/LOGIC/HANDOFF · `/tmp/kaero.done`

## 다음 명령

```sh
cd argus/kaero/tools
tail -f /tmp/kaero_scan2.log /tmp/kaero_collect.log
python3 kaero_universe.py --write && python3 kaero_reports.py --collect --n 6
python3 kaero_reports.py --build
```
