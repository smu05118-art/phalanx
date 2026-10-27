# tools/solder_ball — 솔더볼 묶음 원천 수집기

앙상블 기판 섹터 › 솔더볼 묶음(`codex_tasks/ensemble_substrate_solder.md`)의 공개 원천을 만든다.
지금은 덕산하이메탈(077360) 한 곳이다.

## duksan_dart.py

| 항목 | 내용 |
|---|---|
| 원천 | DART 정기보고서(분기·반기·사업) 「II. 사업의 내용」 2·3·4절 — `https://dart.fss.or.kr/report/viewer.do` (공개, 키 불필요) |
| 범위 | 2024 1분기보고서부터 최신 정기보고서까지 |
| 주기 | 주 1회(`.github/workflows/update-solder-ball.yml`, 월 13:40 KST) + 수동 실행. 새 보고서는 분기마다 한 번 생긴다 |
| 출력 | `data/solder_ball/077360.json` (정규화 JSON: sort_keys·indent=1·끝 개행, 원자적 쓰기) |
| 캐시 | `tools/solder_ball/cache/` (절 원문 HTML·검색 색인, 커밋하지 않음 — Actions 캐시로 이어 감) |

### 원문이 실제로 적는 것

- **II-2 주요 제품 현황(연결기준)**: 법인별 한 줄. `덕산하이메탈(주) · 솔더볼 外` 의 금액과 비중이 한 칸에 들어 있다. SB·MSB·CSB 제품선 분해는 **정기보고서에 없다**(회사 IR 자료에만 있다).
- **II-3 생산실적·가동률**: 법인별 제조원가 금액(백만원)과 가동가능·실제 가동시간(누계). 생산능력·원재료·가격변동은 **표 없이 서술만** 있어서 `notes` 에 인용으로 남긴다.
- **II-4 매출실적**: 법인별 수출·내수·합계.

### 출력 계약 (`data/solder_ball/077360.json`)

| 키 | 내용 |
|---|---|
| `reports[]` | `{rcp_no, title, period, filed, sections_in_toc, chapter_fallback}` — period 는 `YYYY-Q1/H1/Q3/FY`(누계) |
| `product_sales[]` | `{period, scope, product, entity, labels, amount(백만원), unit, unit_seen, share_pct, total, source_rcp, …}` |
| `capacity[]` | `{period, scope, item, output(제조원가 백만원), output_basis, utilization_pct, util_detail{가동가능시간, 실제가동시간}, …}` |
| `sales[]` | 보고서별 II-4 표(`tables[].rows[]{labels, channel: exp/dom/tot, vals, scope}`) |
| `notes[]` | 표가 없는 소절(가격변동추이·원재료·생산능력)의 원문 인용 |
| `quarterly[]` | **하이메탈 부문 분기 단독값**(누계 차분): `{quarter, revenue, export, domestic, production_cost, avail_hours, actual_hours, util_pct, basis}` |
| `issues[]` | 미공시 분기·못 읽은 절 등 |

`scope` 는 `연결` / `별도` / `하이메탈 부문` / `미상` 이다. 연결 실체에는 덕산넵코어스(방산)·덕산에테르씨티(가스용기)가
들어 있으므로 솔더볼 묶음은 **`하이메탈 부문` 행만** 쓴다. 이 값은 회사 IR 의 별도 매출과 분기마다 일치한다
(2024Q2~2026Q2 9개 분기 대조 — 예: 2026Q2 57,710백만원 = IR 577억).

### DART 규칙

DART 는 **공인 IP 단위**로 막는다. 요청은 `argus/kce/tools/kce_fetch`(allowlist·페이싱·프로세스 간 게이트) 위의
`argus/ksemi/tools/ksemi_fetch` 로만, 한 프로세스에서 순차로 보낸다. Action 은 kship·ksemi·kdef 등 DART 탭과 같은
`kship-dart` concurrency 그룹에서 돈다. 이미 JSON 에 있는 보고서는 다시 받지 않는다(`--refresh` 로 강제).

### 실행

```bash
python3 tools/solder_ball/duksan_dart.py --root .            # 수집·파싱·기록
python3 tools/solder_ball/duksan_dart.py --root . --dump     # 캐시 원문의 표 목록(무접속)
cd tools/solder_ball && python3 -m unittest discover -s tests -p 'test_*.py'   # 무접속 테스트
```
