# KNUKE 진행 체크포인트 — 원자력·발전기자재 (argus/knuke)

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/knuke` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 축 (원문에서 확인한 것 — `_specs/knuke.md`)
- **발전원(domain)**: 원자력·화력·신재생·송변전·기타산업설비
- **공급 계층(tier)**: 주기기·보조기기·계측제어·설계엔지니어링·EPC건설설치·정비O&M·검사방사선·해체방폐물·기자재공급
- **발주 성격(party)**: 관급(한수원·한전·발전5사) · 민간IPP · 해외(EPC 하도·직수출)
- 차별점: II-4 수주표에 **발주처 실명·사업명·계약기간**이 행마다 있다(한전기술 23행·한전KPS) →
  '호기별 타임라인'·'발주처 집중도'를 만들 수 있다(조선의 익명 선주 문제가 없다).

## 완료
- [x] `_specs/COMMON.md`·`knuke.md`·scout_tools(probe/contracts)·kdef 본보기 정독
- [x] `knuke_lib.py` · `assets/knuke.css`(kdef.css 복제) · vendor/chart · .gitignore · `_config.yml` exclude
- [x] `build_dicts.py` — 발전원 5·공급계층 9(EPC 추가)·부품 9/18·SVG 실루엣 2/영역 16 (교차검증 통과)
- [x] `knuke_scan.py` — II절 본문 탐색: 후보 69 · 승격 10 · 제외 57 · 실패 2 → universe_probe.json
- [x] `knuke_universe.py` — 네 겹 **25종목**(KIND 7·지정 8·탐색 10)
- [x] `knuke_contracts.py`·`knuke_reports.py`·`knuke_suppliers.py`·`knuke_page.py`·`knuke_parts.py` 작성
- [x] `tools/tests`(14건 통과) · `update-knuke.yml`(concurrency kship-dart) · README/LOGIC/HANDOFF
- [x] 수출 계약명(영문) 사전 보강 · EPC 계층 신설 · 공시 「판매ㆍ공급계약 구분」 폴백(d8165ae)
- [x] 템플릿 스모크: 회사 22쪽·허브·커버리지·parts 생성(계약/보고서 수집 전 상태)

- [x] `knuke_contracts.py --collect` 25종목 전수 → **계약 317건**(e648f83)
- [x] `knuke_reports.py --collect --n 8` 25사 × 8분기 → **193 분기레코드**(71ba260)
- [x] 외화 수주표 fail-closed(이성씨엔아이 `천달러`) · 테스트가 진짜 산출물을 덮어쓰던 버그 수정
- [x] `knuke_suppliers.py`·`knuke_page.py --all`·`knuke_parts.py` 재생성 · `site.json` 공개
- [x] 테스트 14건 통과 · 원문 대조(한전기술 2026Q2 도급형 18행 = 화면 값)

## 남은 일 — **없음**(2026-09-11 기준 한 바퀴 완료)

다음에 넓힐 곳은 `HANDOFF.md` §③ 6번에 적었다(II-2 주요 제품 절 · 발주처 역채움 ·
「판매ㆍ공급지역」으로 수출 지역 축). 새로 이어받는 에이전트는 HANDOFF 부터 읽어라.

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
