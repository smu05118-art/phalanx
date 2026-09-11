# KNUKE 진행 체크포인트 — 원자력·발전기자재 (argus/knuke)

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/knuke` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 축 (원문에서 확인한 것 — `_specs/knuke.md`)
- **발전원(domain)**: 원자력·화력·신재생·송변전·기타산업설비
- **공급 계층(tier)**: 주기기·보조기기·계측제어·설계엔지니어링·정비O&M·검사방사선·해체방폐물·기자재공급
- **발주 성격(party)**: 관급(한수원·한전·발전5사) · 민간IPP · 해외(EPC 하도·직수출)
- 차별점: II-4 수주표에 **발주처 실명·사업명·계약기간**이 행마다 있다(한전기술 23행·한전KPS) →
  '호기별 타임라인'·'발주처 집중도'를 만들 수 있다(조선의 익명 선주 문제가 없다).

## 완료
- [x] `_specs/COMMON.md`·`knuke.md`·scout_tools(probe/contracts)·kdef 본보기 정독
- [x] `knuke_lib.py` · `assets/knuke.css`(kdef.css 복제) · vendor/chart · .gitignore · `_config.yml` exclude
- [x] `build_dicts.py` — 발전원 5·공급계층 8·부품 9/18·SVG 실루엣 2/영역 16 (교차검증 통과)
- [x] `knuke_scan.py` — II절 본문 탐색: 후보 69 · 승격 10 · 제외 57 · 실패 2 → universe_probe.json
- [x] `knuke_universe.py` — 네 겹 **25종목**(KIND 7·지정 8·탐색 10)
- [x] `knuke_contracts.py`·`knuke_reports.py`·`knuke_suppliers.py`·`knuke_page.py`·`knuke_parts.py` 작성
- [x] `tools/tests`(11건 통과) · `update-knuke.yml`(concurrency kship-dart) · README/LOGIC/HANDOFF
- [x] 템플릿 스모크: 회사 22쪽·허브·커버리지·parts 생성(계약/보고서 수집 전 상태)

## 진행 중 / 남은 일
1. [~] `knuke_contracts.py --collect` (DART 백그라운드, 1/25 — DART IP 게이트로 느림) → `--build`
2. [ ] `knuke_reports.py --collect --n 8` (DART) → `--build`  ※ 계약 수집 끝난 뒤(동시 금지)
3. [ ] `knuke_suppliers.py --build && knuke_page.py --all && knuke_parts.py` 재생성
4. [ ] site.json 공개 · 커밋 · `/tmp/knuke.done`

## 다음 명령
```sh
cd argus/knuke/tools
python3 build_dicts.py --write && python3 knuke_universe.py --write
python3 knuke_scan.py --scan && python3 knuke_universe.py --write
python3 knuke_contracts.py --collect && python3 knuke_contracts.py --build
python3 knuke_reports.py --collect --n 8 && python3 knuke_reports.py --build
python3 knuke_suppliers.py --build && python3 knuke_page.py --all && python3 knuke_parts.py
python3 -m unittest discover -s tests
```
