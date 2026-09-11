# KGRID 진행 체크포인트

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/kgrid` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 완료

- [x] `COMMON.md`·`kgrid.md` 정독 · **원문 실측 5사** → `tools/FINDINGS.md`
- [x] **공용 층 수정** `kship_parse.unit_of` — `천USD`·`백만USD`·`천EUR` 표기 + 원화 병기 판정
      (일진전기 잔고가 1000배 작아지던 것)
- [x] `kgrid_lib.py`(제품군 10슬롯 색·잔고 성격·통화 보존 표기·커버리지 fail-closed) · `assets/kgrid.css`
- [x] `kgrid_universe.py` — 모집단 **40종목**(업종 13·지정 15·제품 1·**탐색 8**·지주 3)
- [x] `kgrid_dicts.py` — 제품군 10 · 수요처 6 · 전력망 단선도 영역 6(교차 검증)
- [x] `kgrid_reports.py` — 40사 × 6분기 수집(**실패 0**) · 수주표 4갈래 ·
      표마다 통화 · 종속회사 표 분리 · `--reparse`(DART 재요청 없이 재파싱)
- [x] `kgrid_scan.py` — 본문 탐색(부품사 승격·오탐 재판정) → `assets/universe_probe.json`
- [x] `kgrid_contracts.py` — I001 계약 공시 → `assets/contracts.json`
- [x] `kgrid_page.py` — 허브 · 전력망 단선도 · 커버리지 · 회사 40쪽 ·
      계약 원장(지주·모회사의 자회사 재공시 분리)
- [x] `tools/tests` **101건 통과** · `site.json` · `_config.yml` exclude ·
      `.github/workflows/update-kgrid.yml` · README/LOGIC/HANDOFF

## 남은 일

1. [ ] 제품군 분류 정밀화 — II-2「주요 제품 및 서비스」 절을 따로 수집해 제품 문구로 분류
       (지금은 KIND 문구·수주표 품목·제품군별 매출 행만 본다)
2. [ ] `tr_unknown`(전압 계급 미상 변압기) 줄이기 — II-2 본문에 `초고압`·`345kV` 가 있으면 `ehv` 로 올린다
3. [ ] 수주표가 없는 7사(선도전기·파워넷·티씨머티리얼즈·미창석유공업·보성파워텍·티에스넥스젠·
       옴니시스템)는 매출만 싣는다 — 계약 공시로 잔고를 대신할 수 있는지 확인
4. [ ] 매출처 표의 종속회사 귀속 — 엘에스일렉트릭은 표가 11장인데 대괄호 라벨이 없어 `entity` 가 비었다.
       `사업부문` 열 값으로 귀속을 추정할 수 있는지(추정이면 표시)
5. [ ] 한전KPS 수주표에는 **`발주처`·`공사명` 열이 있다**(한국동서발전·한국수력원자력·한국전력공사).
       지금은 라벨이 밀려 `구분`과 날짜만 들어온다 — 발주처를 살리면 이 회사만 계약 단위 원장이 된다.
6. [ ] 스펙의 수요처 6갈래에 **아시아·유럽 전력청이 없다**(싱가포르 전력청·노르웨이 Statnett·
       영국 National Grid). 지금은 `전력회사 · 아시아` 처럼 지역과 합쳐 보인다 — 키 확장을 검토

## 다음 명령

```sh
cd argus/kgrid/tools
python3 kgrid_universe.py --write
python3 kgrid_contracts.py --collect && python3 kgrid_contracts.py --build
python3 kgrid_reports.py --collect --n 6 && python3 kgrid_reports.py --reparse --build --n 6
python3 kgrid_page.py --all
python3 -m unittest discover -s tests
```
