# 한국건설 (KCE) — ARGUS 하위 대시보드

DART 정기보고서의 **II-4 수주상황 · III-8 진행률적용 수주계약 · XI-1 단일판매공급계약**을
사업장(공사현장) 단위로 교차 연결한 **국내 상장 건설사** 분기 시계열 대시보드.
원본 https://encprojects.vercel.app/ 을 복제해 ARGUS 안에 편입한 것이다.

진입: [`argus/index.html`](../index.html) 헤더의 **🏗 한국건설** → [`index.html`](index.html)
커버리지 전체 지도: [`coverage.html`](coverage.html)

## 모집단 — 무엇을 다루는가

KRX KIND 상장법인목록에서 **표준산업분류 건설업**(건물 건설업 · 토목 건설업 ·
실내건축 및 건축마무리 공사업 · 기반조성 및 시설물 축조관련 전문공사업)에 속한 전 종목,
여기에 업종 밖이지만 건설 실질이 큰 **삼성물산 · 삼성E&A · 자이에스앤디**를 지정 추가한다.
이름으로 임의 배제하지 않는다 — 배제는 **원문을 열어 수주 표가 없음을 확인한 경우**에만 한다.

수록 등급은 추정하지 않고 매 분기 원문을 열어 다시 매긴다([`kce_probe.py`](tools/kce_probe.py)):

| 등급 | 뜻 | 화면 |
|---|---|---|
| `site` | 착공일·완공예정일이 붙은 **개별 현장 행**이 파싱된다 | 현장별 데이터 |
| `segment` | 수주표는 있으나 `건축부문/토목부문`처럼 **사업부문 합계**만 공시 | 부문별 데이터(고지 표시) |
| `agg` | 정기보고서에 인식 가능한 수주 표가 없다 | 미수록 — 사유를 커버리지에 표기 |

부문 단위 회사에 "현장별"이라고 쓰지 않는다. 없는 정밀도를 주장하지 않는 것이 이 프로젝트의
핵심 계약이다.

## 두 갈래 파이프라인

**정밀 경로 (CORP)** — 상류(encprojects) 복제본. II-4/III-8/XI-1 삼중 교차검증, S-curve 예측,
워크포워드 백테스트, 실적 대비까지 갖춘다. 페이지가 4장(index/matrix/trace/backtest)이고
[`kce_build.py`](tools/kce_build.py)가 분기 증분으로 갱신, [`kce_render.py`](tools/kce_render.py)가
파생 페이지를 **바이트 동일**하게 재생성한다. 비상장 자회사(현대엔지니어링·자이씨앤에이·DL건설)도
모회사 보고서를 통해 들어오므로 여기 포함된다.

**lite 경로** — 우리가 DART에서 처음부터 만든 것. 시드가 없으므로 **원문이 지지하는 것만**
만든다: 분기별 수주표를 모아 계약을 이어 붙인 실측 시계열. 예측·백테스트·실적대비는 만들지
않는다(없는 자산을 빈 칸으로 흉내 내면 화면이 거짓말을 한다).
[`kce_series.py`](tools/kce_series.py)가 수집·시계열을, [`kce_page.py`](tools/kce_page.py)가
페이지·커버리지 지도·회사 선택 화면을 만든다.

lite 경로에는 **대조율(recon)** 이 붙는다 — 우리가 센 잔고 ÷ 원문이 스스로 밝힌 합계.
100%가 목표이고, 초과는 중복 계상, 미달은 상세표에 개별 기재되지 않은 소규모 현장 몫이다.
회사 화면 KPI에 "공시 총계 / 수록분이 N%"로 그대로 노출한다.

## 구성

```
index.html                  회사 선택 (정밀 경로 카드 + lite 카드)
coverage.html               모집단 전 종목의 수록 등급과 그 근거
curve.html                  공정 진행 곡선 (지역 × 공종 분위수 S-curve)
headers.html                파서 머리행 지도 (DART 표 구조 변화 추적)
srcmap.html                 매출 출처 지도 (II-4 매출실적 · III-3 주석 위치)
entitycmp.html              모·자회사 공시 대조
dc/index.html               데이터센터 사업장 모음 (회사 경계 없이)
<co>/index.html             정밀 경로 — 사업장 목록·집계·차트 (const DATA 임베드)
<co>/matrix.html            현장별 분기매출 매트릭스
<co>/trace.html             원본위치확인 (출처 × 분기 원문 표기 매핑)
<co>/backtest.html          예측 성적표 (원본 7사만)
<종목코드>/index.html         lite 경로 — 현장/부문 목록·잔고 추이·분기 매트릭스
vendor/chart.umd.min.js     Chart.js 4.4.1 (CDN 대신 벤더링)
tools/                      DART 자체 갱신 파이프라인
tools/assets/universe.json  모집단 (KIND에서 확정)
tools/assets/probe_*.json   분기별 수록 등급 관측
tools/assets/series_cache/  lite 경로의 분기별 원행 — **중간 캐시가 아니라 시계열 원장이다**
```

`series_cache`는 커밋한다. 이게 없으면 Action이 최신 분기 하나만 보게 되어 lite 회사의
과거 시계열을 다시 만들 수 없다(전 분기 재수집에 1시간이 든다).

## 문서

- **[LOGIC.md](LOGIC.md)** — 내부 로직 해부. 데이터 사전(`const DATA` 계약), 계산식
  (III-8 분해·XI-1 분해·진행률·공기 대비 배지·S-curve), 집계 규칙, 수치검증 결과.
- **[UPDATE.md](UPDATE.md)** — 우리가 직접 갱신하는 방법. 모집단 규칙, DART 수집 경로,
  머리행 정규화 규칙, 빌더 단계별 로직, 운영 절차, 필드별 커버리지.

## 갱신 — 자동

GitHub Action [`update-kce.yml`](../../.github/workflows/update-kce.yml)이 매일 10:00 KST에 돌며
**새 정기보고서가 뜨면 자동으로 감지해 반영**한다(없으면 no-op). 평시에는 손댈 일이 없다.
모집단 재확정 → 수록 등급 관측 → lite 분기 수집 → 페이지 생성까지 한 실행에서 처리한다.

직접 돌릴 때:

```bash
cd tools
python3 kce_watch.py                # 정밀 경로 감지만 — 무엇이 갱신될지 확인
python3 kce_watch.py --apply        # 정밀 경로 갱신
python3 kce_universe.py --write     # 모집단 재확정 (KIND)
python3 kce_probe.py                # 수록 등급 관측
python3 kce_series.py --collect --new-only   # lite 분기 수집(캐시된 칸은 건너뜀)
python3 kce_page.py --all           # lite 페이지 + coverage + 회사 선택 재생성
python3 -m unittest discover -s tests
```

파이썬 stdlib만 쓰며(레포 규약), 검증 실패 시 파일을 건드리지 않고 중단한다.
DART 요청은 전역 게이트로 요청률을 묶고 레인만 늘려 병렬화한다 — `KCE_LANES`로 조정한다.

## 배포

main 푸시 → GitHub Pages 자동 리빌드(1~2분).
라이브: `https://smu05118-art.github.io/phalanx/argus/kce/index.html`

## 참고용 · 투자조언 아님

원문에 없는 구간은 화면에서 보전·예측으로 구분 표시된다(테두리 없는 값 = 원문 실측).
예측(S-curve)은 진행률 80% 이상 구간에서 과대 편향이 크다 — `backtest.html` 참조.
lite 경로에는 예측이 없다.
