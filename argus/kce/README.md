# 한국건설 (KCE) — ARGUS 하위 대시보드

DART 정기보고서의 **II-4 수주상황 · III-8 진행률적용 수주계약 · XI-1 단일판매공급계약**을
사업장(공사현장) 단위로 교차 연결한 7대 건설사 분기 시계열 대시보드.
원본 https://encprojects.vercel.app/ 을 복제해 ARGUS 안에 편입한 것이다.

진입: [`argus/index.html`](../index.html) 헤더의 **🏗 한국건설** → [`index.html`](index.html)

## 구성

```
index.html                  회사 선택 (7사 카드)
curve.html                  공정 진행 곡선 (7사 통합 S-curve, 지역×공종 분위수)
headers.html                파서 머리행 지도 (DART 표 구조 변화 추적)
<co>/index.html             현장별 데이터 — 사업장 목록·집계 4종·차트 4종 (const DATA 임베드)
<co>/matrix.html            현장별 분기매출 매트릭스 (사업장 × 23분기)
<co>/trace.html             원본위치확인 (출처 × 분기 원문 표기 매핑)
<co>/backtest.html          예측 성적표 (워크포워드 백테스트)
vendor/chart.umd.min.js     Chart.js 4.4.1 (CDN 대신 벤더링)
tools/                      DART 자체 갱신 파이프라인
```

회사 코드: `sct` 삼성물산 · `hec` 현대건설 · `sea` 삼성E&A · `dwe` 대우건설 ·
`gse` GS건설 · `dle` DL이앤씨 · `ipark` HDC현대산업개발.

## 문서

- **[LOGIC.md](LOGIC.md)** — 내부 로직 전체 해부. 데이터 사전(`const DATA` 계약), 계산식
  (III-8 분해·XI-1 분해·진행률·공기 대비 배지·S-curve), 집계 규칙, 7사 전수 수치검증 결과.
- **[UPDATE.md](UPDATE.md)** — 우리가 직접 데이터를 갱신하는 방법. DART 수집 경로,
  머리행 정규화 규칙, 빌더 단계별 로직, 운영 절차, 필드별 커버리지.

## 갱신

```bash
cd tools
python3 kce_fetch.py --co sct --quarter 2026Q3 --out /tmp/kce_raw
python3 kce_build.py --co sct --quarter 2026Q3 --raw /tmp/kce_raw          # dry-run
python3 kce_build.py --co sct --quarter 2026Q3 --raw /tmp/kce_raw --apply
python3 -m unittest discover -s tests
```

파이썬 stdlib만 쓰며(레포 규약), 검증 실패 시 파일을 건드리지 않고 중단한다.
`--apply`는 `matrix.html`·`trace.html`까지 재생성한다. `backtest`·`curve`·`headers`는
아직 스테일로 남으며 경고가 뜬다(UPDATE.md §7).

2026Q2를 DART 원문에서 다시 빌드해 임베드 데이터와 전필드 대조한 결과
**7사 중 5사가 차이 0**(완전 재현)이고, 삼성물산 2셀·GS건설 6셀만 남는다.
둘 다 우리 로직 결함이 아니다 — 삼성물산 건은 원본이 원문과 다르고(우리가 원문에 충실),
GS건설 건은 원본 데이터에 표시법인 이관 이력이 빠져 있다(UPDATE.md §9).
matrix/trace 재생성물은 7사 모두 원본과 바이트 동일하다.

## 참고용 · 투자조언 아님

원문에 없는 구간은 화면에서 보전·예측으로 구분 표시된다(테두리 없는 값 = 원문 실측).
예측(S-curve)은 진행률 80% 이상 구간에서 과대 편향이 크다 — `backtest.html` 참조.
