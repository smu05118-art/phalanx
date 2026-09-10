# 한국조선(argus/kship) — 인수인계 (2026-09-10)

다른 머신(맥미니)에서 이어가기 위한 상태 기록. 코드·데이터·페이지는 전부 `main`에 있다.
`git pull` 뒤 아래 순서로 돌리면 같은 화면이 나온다(파이썬 3.9+ 표준 라이브러리만).
**남은 과정만 바로 착수하려면 [KICKOFF.md](KICKOFF.md)** — 레인 A/B/C·IP 제약·검증 6항목·붙여넣을 프롬프트.

```bash
cd argus/kship/tools
python3 kship_universe.py --write          # KIND → 모집단 41종목 (조선사 5·지주 1·엔진 4·기자재 29·강재 2)
python3 kship_contracts.py --collect       # 척당 계약 공시 캐시(assets/contracts/) — 있는 건 건너뜀
python3 kship_contracts.py --build         # → assets/contracts.json
python3 kship_yards.py --collect           # 조선사 정기보고서 최신 분기(롤포워드·매출·환노출·헤지)
python3 kship_suppliers.py --collect       # 기자재사 정기보고서 II 절(제품·조선사 언급)
python3 kship_suppliers.py --build         # → assets/suppliers.json (+ unclassified.csv)
python3 build_dicts.py                     # 부품 분류 54·SVG 영역 35 재생성(교차참조 검증)
python3 kship_page.py --all                # 허브·커버리지·조선사 5장
python3 kship_parts.py --all               # parts.html 인포그래픽 + 기자재사 35장
python3 inject_link.py --apply             # argus/index.html 에 ⚓ 한국조선 진입 링크(크론이 지우면 재주입)
```

로컬 미리보기: 레포 루트에서 `python3 -m http.server 8902` → `http://localhost:8902/argus/kship/index.html`.

## 무엇이 어디서 오는가 (실측으로 확정)

| 축 | 원천 | 비고 |
|---|---|---|
| 수주잔고·신규·기납품(부문) | 정기보고서 II-4 수주상황 — **부문 롤포워드**(원화, 삼성重 억원) | 선종·척수 없음. 신규증감에 환율효과 포함 |
| 선종·척수·인도시점·상대·지역·대금조건 | 수시공시 「단일판매ㆍ공급계약체결」 | 상대 81% 익명('○○ 소재 선사'). 종료일=마지막 호선 인도 |
| 매출실적(부문×수출/내수) | 정기보고서 II-4 | |
| 환노출(통화별 자산·부채, 계약자산) | II-5 위험관리 및 파생거래 | HD현대重·대한조선만 표 형식 |
| 통화선도 명목액·평균만기·건수 | 주석 「파생금융상품」 또는 II-5 | 3사 3형식(주석 라벨형/4열 쌍/USD매도 행) 모두 파싱 |
| 반복건조(시리즈) | **추정** — 같은 선종·상대 표기·지역, 수주일 180일 이내 | 화면에 '추정' 표시 |
| 기자재 부품 분류 | 정기보고서 II-2 주요제품 + KIND 문구 → 키워드 규칙 | 미분류는 `assets/unclassified.csv`, 수동 지정은 `parts_override.csv` |
| 기자재→조선사 연결 | II 절 본문의 조선사 이름 언급(횟수), 비중은 적힌 경우만 | 근거 등급을 화면에 표시(주요고객 주석 > 계약 공시 > 본문 언급 > KIND) |

## 지금 상태 (2026-09-11 01:45 KST — 맥미니에서 재수집 완료)

- **수집 완료**: 척당 계약 278건 캐시 → 225건(정정 25건 supersedes, 선종 미판정 0) · 기자재 35사 재수집(--force, 조선사 언급 확인 18사, 비중 0~100 검증) · 조선사 5사 × 8분기(2024Q3~2026Q2; 대한조선은 2025Q2~, HJ중공업 2024Q4·2025Q4 사업보고서는 수주 절 제목이 달라 미수록).
- **환헤지 확정**: 삼성重 482억달러는 주석 오독이었다 — ① '전기말' 비교표 합산 ② 목적별 3열+합계 열 합산 ③ 멤버별 합계+총합계 열 합산. 셋 다 고쳐 시계열 223→219→227→219→221→227→230→**255억달러**(2026Q2, 잔고 35조≈250억달러와 정합). HD현대重 148→208억달러, 한화오션 9→39억달러. 대한조선·HJ중공업은 헤지 공시 없음('헤지 공시를 찾지 못함' 표시).
- **롤포워드**: 기초=연초, 신규·기납품=연초 누계(실측). 표에 '대조' 열(같은 해 기초 = 전년 Q4 기말) · 합계행이 부문합과 어긋나면 부문합 사용(삼성重 2024Q4·2025Q1 합계 셀 깨짐).
- 신형 거래소 서식(2025~ '판매ㆍ공급계약 구분/세부내용', '계약(수주)일') 파싱 추가. 빌드가 캐시 원문 라벨에서 필드를 다시 뽑는다.
- `site.json` — 맥미니 ARGUS 빌더(`argus_build.py inject_subsite_links`)가 크론마다 ⚓ 링크를 재생성하므로 되쓰기 경쟁이 끝났다.
- 테스트 15건 `cd tools && python3 -m unittest discover -s tests`. 자동 갱신 `.github/workflows/update-kship.yml` 매일 10:40 KST.
- 남은 일(선택): 인포그래픽 미분류 제품 39건(`tools/assets/unclassified.csv` → `parts_override.csv`), HJ중공업 사업보고서 수주 절 제목 대응, 진행률(매출인식) 기준을 주석 「수익」에서 읽기.

## DART 주의

DART는 병렬 프로세스 2~3개가 동시에 두드리면 IP 단위로 연결을 끊는다(RemoteDisconnected, 30~60분).
수집기는 **하나씩** 돌려라. kce_fetch 가 요청 간격 0.7초·재시도 5회를 내장한다.
