# 🧪 한국화학 (argus/kchem)

ARGUS 원장의 석유화학 스프레드를 **산식·지역·신선도** 축으로 다시 조립한 서브사이트. 허브(`argus/index.html`)의 스프레드 패널은
카드 그리드라 산식도 지역도 표도 없다 — 여기서는 242 시리즈를 표·매트릭스·밸류체인·종목 역참조로 본다.
라이브: `https://smu05118-art.github.io/phalanx/argus/kchem/`

| 페이지 | 내용 |
|---|---|
| `index.html` | KPI(시리즈·재현·살아 있는 스프레드·원장 정지 주·파생·플래그) · **원장 정지 고지** · 카테고리 칩 · 체인 카드(허브 값 읽기 전용 + 종목 칩) |
| `spreads.html` | 242 + 파생 47 행 표. 열 머리 정렬, 검색·레이어·지역·카테고리 필터. 열: 역산 산식 · 원료(k·참조 지역) · 최신 · 4W% · 사이클 위치 · 신선도(정지 주) · 5년 추이 · 中선물 참고 · 판정·플래그·종목 · 허브 연결/맵 링크 |
| `matrix.html` | 제품−원료 × 지역. 셀 = 최신값·관측 연월, 바탕 = 사이클 위치(초록 바닥권·붉음 천장권). 셀 클릭 → 지역별 겹침 차트 |
| `chains.html` | 밸류체인 다이어그램(레지스트리 원료→제품 관계 자동 생성). 노드 클릭 → 스프레드 목록·차트·종목 |
| `coverage.html` | 모집단 전수와 판정 규칙, 결함 의심·산식 변경·원료 불일치, 미재현, 체인 미배정, 장기 미갱신, 자동 소스 |
| `<종목코드>/index.html` | 허브 체인 종목 21개 → 매핑된 체인의 스프레드 목록(체인 단위 참고 라벨) |

## 읽는 법

- **원장 정지 N주** 배지가 떠 있으면 아래 주간 스프레드는 전부 그 날짜에 멈춘 값이다(2026-10 현재 2026-08-24 주차 이후 미갱신, 살아 있는 스프레드 0).
  값은 그대로 보이되 신선도가 <오래됨>/<장기 미갱신> 으로 표시된다. 살아 있는 화학 입력은 中 선물(일간)·PPI(월)뿐이다.
- 산식(`Ethylene 한국 − 1×Naphtha 일본`)은 이름과 주간 관측으로 **역산한 추정**이다. `재현` 배지는 최소제곱이 원장 값을 |잔차|≤1.5 로 되돌린다는 뜻이지 원장 수식을 봤다는 뜻이 아니다.
  `미재현` 은 산식을 못 찾은 것(겹침 부족·상수 잔차·단위 환산 미확인)이며 값 자체는 원장 그대로다.
- 플래그: `이름에 없는 원료 추가`(ABS 에 AN, SBR 에 SM …) · `이름과 다른 원료로 재현`(PX−자일렌 대만 = PX − 나프타) · `창 안에서 산식 변경`(regime_start) ·
  `제품 결측을 0으로 계산(결함 의심)`(BR−BD) · `파생(공개 관행 계수·추정)`.
- 종목 칩은 허브 `chains[].stocks` 의 **체인 단위 참고 라벨**이다. 점선 칩은 체인 추정 배정(`chain_est`) 경유.
- 中선물 열은 방향 참고다(CNY/t·증치세·선물 — 원장과 기준이 달라 같은 산식에 넣지 않는다).
- 이 탭은 wj-stock 등 회원 전용 화면의 값·산식·회사 목록을 쓰지 않는다. 원장 값은 csv 로 재배포하지 않는다.

## 입력과 실행

입력은 맥미니 ARGUS 빌더가 커밋하는 산출물 4종(`argus/data/argus_data.js`·`chunk_<카테고리>.js`·`connections.js`, `argus/data_map.js`)뿐이다.
네트워크·DART·API 키를 쓰지 않는다. 표준 라이브러리만(Python 3.9+).

```sh
cd argus/kchem/tools
python3 -m unittest discover -s tests -p 'test_*.py'   # 합성 fixture + 실제 입력 계약
python3 kchem_inputs.py                                 # 입력 검증·fingerprint 만
python3 kchem_registry.py --list-unreproduced --list-flagged   # 역산 결과(쓰지 않음)
python3 kchem_page.py                                   # 레지스트리 + data/kchem_data.js + 페이지 전부 (--dry-run 가능)
```

같은 입력이면 산출물 바이트가 같다(빌드 시각 미기록, `tools/assets/fingerprint.json` 에 입력 sha256). 일일 재조립은 `.github/workflows/update-kchem.yml`(09:10 KST, 네트워크 없음).
판정 규칙은 [LOGIC.md](LOGIC.md), 상태·남은 일·운영자 확인 항목은 [HANDOFF.md](HANDOFF.md), 설계·빌더 반영 제안은 `argus/_specs/kchem.md`.
