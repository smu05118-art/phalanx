# ARGUS 산업 탭 — 공통 규약 (새 탭을 만드는 에이전트가 먼저 읽는다)

이미 만든 두 탭이 본보기다. **먼저 읽어라.**
- `argus/kce/` 한국건설 — `LOGIC.md`, `README.md`
- `argus/kship/` 한국조선 — `LOGIC.md`, `README.md`, `HANDOFF.md`, `tools/*.py`

두 탭의 교훈이 이 문서다. 새 탭은 **산업 특성이 다르면 축도 달라야 한다** — 건설은 현장·공정률,
조선은 선종·선표·환헤지. 형식을 베끼되 축은 그 산업의 원문에서 다시 찾아라.

## 0. 절대 규칙

1. **원문이 지지하는 것만 싣는다.** 추정은 화면에 `추정`이라 적고 근거 등급을 남긴다. 모르면 빈칸.
2. **fail-closed.** 파싱 실패·단위 미확인·대조 실패는 조용히 넘기지 말고 표시하거나 수집을 멈춘다.
3. **표준 라이브러리만.** 외부 패키지 설치 금지(`pip install` 금지). 파이썬 3.9에서 돌아야 한다.
4. **원문 캐시를 보존한다.** 파싱 결과만 저장하지 말고 원문 라벨·값을 같이 남겨, 파서가 자라면
   재수집 없이 다시 뽑을 수 있게 한다(kship_contracts 의 `kv` 가 본보기).
5. **API 키를 쓰지 않는다.** DART 무키 3단계 경로만 쓴다. 키를 받지도, 만들지도 말 것.
6. 사람 이름·비공개 정보를 추정해 쓰지 않는다. 계약상대가 익명이면 익명이라 적는다.

## 1. 재사용할 코드 (새로 만들지 말 것)

| 쓸 것 | 어디 | 무엇 |
|---|---|---|
| DART 수집 | `argus/kce/tools/kce_fetch.py` | 무키 3단계(detailSearch.ax → dsaf001 TOC → viewer.do), 재시도, **프로세스 간 요청 게이트**, EUC-KR 판정(rcpNo[8]=='8'), allowlist |
| 표 파싱 | `argus/kce/tools/kce_parse.py` | 표 추출·머리행 평탄화·정규화 |
| 상장사 목록 | `argus/kce/tools/kce_universe.py` | KIND 전 상장사(업종·주요제품) |
| 페이지·차트·표 | `argus/kship/tools/kship_lib.py` | `page()`(외부 스크립트를 `<main>` 앞에 넣는다), `CHART_DEFAULTS_JS`, `TABLE_JS`(정렬·필터·툴팁), `fmt_eok` 등 |
| 디자인 | `argus/kship/assets/kship.css` | 다크 디자인 시스템(토큰·KPI·카드·칩·표·타임라인·패널). 새 탭은 이 CSS를 복사해 `argus/<slug>/assets/<slug>.css` 로 두고 필요한 것만 더한다 |
| 모집단 탐색 | `argus/kship/tools/kship_scan.py` | KIND 어휘 후보 → 정기보고서 II절 본문 증거 → 승격/제외(`--rejudge`) |
| 부품 인포그래픽 | `argus/kship/tools/kship_parts.py`, `build_dicts.py` | 분류(대분류/소분류) + SVG 영역 + 관련도 + 회사 연결. **구조만** 베끼고 그림·분류는 그 산업 것으로 다시 만든다 |

`sys.path` 를 kce/kship tools 로 붙이는 방법은 `argus/kship/tools/kship_lib.py` 맨 위에 있다.

## 2. DART 다루기 (사고로 배운 것)

- DART는 **공인 IP 단위**로 막는다(30~60분). 이제 `kce_fetch` 가 **파일 락으로 프로세스 사이
  요청 간격까지 묶으므로** 수집기를 여러 개 띄워도 총 요청률은 유지된다 — 그래도 한 웨이브가
  수천 건을 한 번에 긁지 말고, 캐시를 쓰고 실패는 캐시하지 말 것(다시 돌리면 빠진 것만 받는다).
- `--force` 대량 재수집은 파서를 고친 뒤 꼭 필요한 범위만.
- 거래소 수시공시(rcpNo 9번째 자리 `8`)는 EUC-KR. 정기보고서는 UTF-8.
- 정기보고서 검색은 publicType A001/A002/A003, 수시공시는 I001.
- 표의 단위 캡션(`(단위: 백만원)`·`억원`·`천달러`)을 표마다 읽어 정규화하고, 못 읽으면 `unit_seen=false`.
- 합계 행을 버리지 말고 `total=True` 로 남겨 부문합과 대조한다(합계 셀이 깨진 원문이 실제로 있다).
- 주석 표는 **당기·전기 비교표**가 나란히 온다. 전기 표를 더하면 값이 두 배가 된다(삼성중공업 헤지 사고).

## 3. 산출물 구조

```
argus/<slug>/
  index.html            허브 — KPI·회사 카드·진입
  coverage.html         모집단 전수와 편입 근거·수록 상태(빠진 것도 이유와 함께 보인다)
  <종목코드>/index.html  회사 상세 — 그 산업의 축으로
  parts.html            (부품이 있는 산업) 인포그래픽 — 클릭 → 부품 → 회사
  assets/<slug>.css     디자인 시스템
  site.json             {"label": "<이모지> <이름>", "order": N} — ARGUS 헤더 링크 자동 생성
  README.md LOGIC.md HANDOFF.md
  tools/                파이프라인 + tools/tests/ + tools/assets/(캐시·사전·산출 JSON)
```

- `_config.yml` 의 exclude 에 `argus/<slug>/tools/` 를 추가한다(Pages 배포 제외).
- `.github/workflows/update-<slug>.yml` — 일 1회, **`concurrency: group: kship-dart`**(DART는 IP 하나).
- 파일 5MB 이하. 커밋 전 `python3 -m unittest discover -s tests` 통과 필수.

## 4. 테스트 (형식이 아니라 계약)

원문 fixture를 `tools/tests/fixtures/` 에 넣고, 파서가 뽑은 값이 화면에 실린 값과 같은지 검증한다.
최소: 단위 정규화 · 합계/소계 판정 · 핵심 표 1종의 원문 대조 · 분류 사전 교차참조 · 승격 규칙(있다면).

## 5. 커밋·푸시

- 각 웨이브는 **자기 디렉터리만** 커밋한다(`git add -A -- argus/<slug> .github/workflows/update-<slug>.yml`).
- `git pull --rebase origin main` 후 push, 실패하면 다시 pull --rebase(최대 5회).
- 커밋 메시지는 한국어 한 줄 + 본문(무엇을 왜). 끝에:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```
- 진행 중에도 **자주 커밋·푸시**한다(웨이브가 죽어도 살아남게).

## 6. 보고

작업이 끝나면 `argus/<slug>/HANDOFF.md` 에 ① 무엇이 어디서 오는가 표 ② 지금 상태 ③ 남은 일 ④ 재현 명령을
적는다. 그리고 `/tmp/<wave>.done` 에 한 줄 요약을 남긴다(감시자가 이 파일로 완료를 안다).
