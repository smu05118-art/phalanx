# 한국방산 (KDEF) — ARGUS 하위 대시보드

국내 상장 **방산 체계업체와 부품사**의 수주를 이 산업의 축으로 읽는다. 건설(`argus/kce`)·조선
(`argus/kship`) 탭의 DART 수집·표 파서·디자인 시스템을 그대로 재사용하고, 방산에만 있는 축을 새로 만들었다.

진입: [`argus/index.html`](../index.html) 헤더의 **🛡 한국방산** → [`index.html`](index.html)
인수인계·실행 순서: [HANDOFF.md](HANDOFF.md) · 판정 규칙: [LOGIC.md](LOGIC.md)

## 왜 축이 조선과 다른가 (원문 실측)

| 실측 | 조선과의 차이 | 화면에서 |
|---|---|---|
| 계약상대가 **공개**다 — 방위사업청·체계업체·해외 정부 | 조선은 81%가 '○○ 소재 선사'(익명) | 계약 표에 상대 이름과 갈래(정부·체계업체·G2G·해외기업) |
| 수주표가 **보안 때문에 얇다** — 잔액 한 줄(LIG)·기초/기말만(KAI) | 조선은 부문 롤포워드가 온다 | 표 모양을 화면에 적고, 못 읽은 것은 못 읽었다고 적는다 |
| 다년도 계약 — 계약기간 3~10년 | 조선은 선표(인도 스케줄) | **잔고 커버리지(잔고 ÷ 연매출, 년)** 가 1차 축 |
| 계약명에 **유형**이 적힌다(체계개발·최초양산·후속양산·성능개량·PBL) | 조선엔 없는 축 | 계약 유형 구성 — 유형마다 이익 성격이 다르다 |
| 방산/민수, 내수/수출이 부문으로 갈려 공시된다 | 조선은 선종 | 부문 매출 표 · 방산비중·수출비중 KPI |

## 축 — 무엇을 어디서 읽는가

| 축 | 원천 | 화면 |
|---|---|---|
| 수주잔고·기납품·기초 | 정기보고서 II-4 수주상황 (표 모양 5갈래: `roll`·`openclose`·`gross`·`item`·`balance`) | 회사 페이지 잔고 추이·롤포워드 표 |
| 연매출(커버리지 분모) | 같은 절 매출실적/부문별 매출의 **직전 사업연도 열** | 커버리지 KPI(분모와 열 이름을 함께 표시) |
| 방산/민수 · 내수/수출 | II-4 매출실적 — 부문 이름은 회사마다 다르다 | 부문 매출 표(원문 이름 + def/civil/mixed 판정) |
| 사업 단위 계약 | 수시공시 「단일판매ㆍ공급계약체결」(I001) — 유가·코스닥 양식 둘 다 | 계약 표(사업명·계통·유형·금액·기간·상대)·계통/유형 차트 |
| 무기체계 계통 8 + 민수 | 계약명 → `assets/domains.json`(체계 이름 prio 90 > 일반 어휘 50) | 계통 칩·차트 |
| 부품 분류(대분류 11·소분류 31) | 계약명 · 정기보고서 「주요 제품」 절 · II절 본문 · KIND 문구 | `parts.html` 인포그래픽·회사 페이지 부품 칩(근거 표시) |
| 부품사 → 체계업체 | 주요고객 주석 > 계약공시 상대 > 본문 언급 | 근거 등급 배지와 근거 문장 |
| 계약별 진행(XI-1) | 반기·사업보고서 XI-1 「나. 단일판매ㆍ공급계약 진행 현황」(2024Q4~, Q2·Q4) | 계약 표 '진행(XI-1)' 열 · 회사/허브 「계약 진행」 섹션 · 커버리지 수집 상태 |

모집단은 네 겹 전수다 — ① KIND 업종(항공기·우주선/무기·총포탄) · ② KIND 제품 문구의 방산 어휘 ·
③ 사유를 적은 지정(종목코드는 KIND 조회로 확인) · ④ **정기보고서 본문 탐색**(`tools/kdef_scan.py`).
편입 근거는 종목마다 남기고, 제외도 근거와 함께 커버리지 페이지에 남긴다.

## 화면

```
index.html            허브 — 체계업체 카드(잔고·커버리지·방산비중) · 계통/유형 차트 · 최근 대형 계약 · 계약 진행(#xi1)
parts.html            무기체계 인포그래픽 — 전차·전투기·함정·유도탄 실루엣 → 영역 → 부품 → 회사
coverage.html         모집단의 역할·수록 상태·편입 근거 · ④ 탐색 승격/제외 · 계약 진행 수집 상태(#xi1cov)
<종목코드>/index.html  회사 — 잔고 추이·롤포워드 · 부문 매출 · 계약 목록 · 계약 진행(#xi1) · 계약 상대 · 납품 관계 · 각주
```

### 계약 진행(XI-1)

원천은 반기·사업보고서 XI-1 「공시내용 진행 및 변경사항 › 나. 단일판매ㆍ공급계약 진행 현황」. 수집·해석·원장 연결·지표는
6개 수주 섹터 탭 공용 층(`argus/kce/tools/xi1_sector.py`, 화면 조각 `xi1_view.py`)이 하고, 이 탭은 붙이기만 한다
(`kdef_page.load_xi1`·`xi1_company`·`xi1_hub`·`xi1_coverage`·`contracts_table` 의 열). 데이터:
`tools/assets/xi1/{status.json, parsed/<종목>/<분기>.json, progress.json}`. **진행 = 판매ㆍ공급 누적 ÷ 계약금액**,
수령 진척 = 대금수령 누적 ÷ 계약금액, 매출채권(순) = 공급 − 수령(음수면 선수금), 지연 = 탭 표준 곡선 대비,
원장 연결 등급 확정/추정/XI 전용, 외화는 환산하지 않는다 — 정의 전문은 [`argus/kce/UPDATE.md` §6-C](../kce/UPDATE.md).
XI-1 절은 회사의 XI-1 계약 **전부**를 싣는다 — 방산 집계와 달리 민수(CIVIL)를 빼지 않고, 섹션 첫 줄에 그 사실과
원장으로 확인한 민수 건수를 적는다. `progress.json` 이 없거나 읽기·렌더가 실패하면 열·섹션 없이 지금 화면 그대로 나온다.

## 만들기

```sh
cd tools
python3 build_dicts.py --write            # 계통·계약유형·부품·SVG 사전
python3 kdef_universe.py --write          # 모집단(④ 탐색 결과를 합친다)
python3 kdef_contracts.py --collect --build
python3 kdef_reports.py --collect --n 8 --only <체계업체들>
python3 kdef_reports.py --collect --n 2 --only <나머지>
python3 kdef_reports.py --build --n 8
python3 kdef_products.py --collect         # 「II-2 주요 제품」 절(회사당 한 번)
python3 kdef_suppliers.py --build          # 부품 분류 + 체계업체 연결(수집 없음)
python3 ../../kce/tools/xi1_sector.py kdef --collect --build   # 계약 진행(XI-1) — 로컬은 --build --no-hdr 만(DART 0)
python3 kdef_page.py --all && python3 kdef_parts.py
python3 -m unittest discover -s tests
```

자동 갱신: `.github/workflows/update-kdef.yml`(매일 11:20 KST, concurrency `kship-dart`).
