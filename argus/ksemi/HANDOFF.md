# 한국반도체장비 — 인수인계

## ① 무엇이 어디서 오는가

| 화면의 값 | 원천 | 모듈 → 산출 |
|---|---|---|
| 수주총액·기납품·수주잔고 (8분기) | 정기보고서 II-4 「수주상황」 | `ksemi_reports.py` → `assets/reports.json` |
| 제품별 매출·수출/내수 | 정기보고서 II-4 「매출실적」 | 〃 |
| 매출인식 기준(원문 인용) | III 주석 「수익」 — **사업보고서만** | 〃 (`basis`) |
| 주요 고객·집중도 | III 주석 「주요 고객에 대한 정보」 — **당기만** | 〃 (`customers`, `segment_total`) |
| 대형 수주(상대·금액·기간·지역) | 수시공시 I001 「단일판매ㆍ공급계약체결」 | `ksemi_contracts.py` → `assets/contracts.json` |
| 모집단 후보 154종목 | KRX KIND 상장법인목록 | `ksemi_universe.py` → `assets/universe.json` |
| 편입/보류/배제 판정 | 후보의 정기보고서 II절 본문 | `ksemi_scan.py` → `assets/scan.json` |
| 공정 13단계·부품 사전, 종목 태그 | 위 둘 + 지정 사유 | `build_dicts.py` → `assets/stages.json`, `stage_tags.json` |
| 색 | kship 검증 팔레트 | `assets/palette.json` |

페이지는 `ksemi_page.py --all`(허브·회사·커버리지)과 `ksemi_parts.py --write`(공정 흐름)가 만든다.
**수집과 렌더가 분리돼 있다** — `reports.json` 이 없거나 일부만 있어도 페이지는 렌더된다.

## ② 지금 상태

- 모집단 154종목(어휘 133 · 지정 21). ④ 본문 탐색: **편입 79 · 보류 7 · 배제 67 · 오류 1**.
- 공정 단계 태그 **121/154사**, 단계 미분류 0. 13단계 + 부품 사전.
- 파서 계약 테스트 **68건 전부 통과**(오프라인, 원문 픽스처 5종).
- 페이지: 허브 · 회사 79 · 커버리지 · `parts.html` 생성됨.
- **`site.json` 은 아직 추적에서 빠져 있다**(감독 메모). 허브가 실제 데이터로 채워진 것을
  확인한 뒤 `git add argus/ksemi/site.json` 하면 ARGUS 헤더에 탭이 걸린다.

### 원문으로 확인한 것 (가설이 아니다)

| 산업 특성 | 확인 |
|---|---|
| 1. 수주잔고 공시 | **확인** — 원익IPS 총액형(잔고 634,590백만원), 단 한미반도체는 단일계약형이고 잔고 칸이 `-` |
| 2. 매출인식 시점 | **확인** — 원익IPS 「설치완료 시점에 인식」(SAT). 반기보고서엔 이 주석이 없다 |
| 3. 고객 집중 | **확인** — 원익IPS A사 49.0%, 익명 표기 |
| 6. 수출/내수 | **확인** — II-4 매출실적에 수출·내수 행이 나뉘어 있다 |

자세한 근거와 rcpNo는 `tools/PROGRESS.md` §1, 방법은 `LOGIC.md`.

## ③ 남은 일

1. **정기보고서·계약공시 수집 완주.** 두 수집기는 캐시를 먼저 보므로 **다시 돌리면 빠진 것만
   받는다**. 끝나면 `ksemi_page.py --all` 과 `ksemi_parts.py --write` 를 다시 돌려야 잔고·
   인식기준·고객이 화면에 붙는다(그 전에는 카드가 '미공시'로만 뜬다).
2. **`site.json` 재추가** — 허브가 볼 만해진 뒤.
3. **보류 7종목 재판정.** 대표적으로 **리노공업**은 본문에 「TEST SOCKET」이 24회 나오는데
   장비 낱말 점수 9가 편입선 12에 못 미쳐 보류다 — 테스트 소켓 부품사가 통째로 빠진다.
   `ksemi_scan.py --rejudge` 로 재수집 없이 다시 볼 수 있다.
4. **원문에서 아직 못 댄 구멍**(화면에 그대로 표시돼 있다):
   - 계측/검사 단계의 부품 연결 0건 — 정밀 스테이지·지그를 만든다고 원문에 적은 상장사를 못 찾음.
   - 러셀·엔투텍·제이엔비·포인트엔지니어링은 본문에 「게이트 밸브」·「진공펌프」·「프로브 카드」가
     있으나 특정 부품에 잇지 않고 「부품 종류 원문 미특정」으로 남겼다.
   - 노광기(스캐너)·EUV 본체는 국내 상장사가 없다.
5. **부품사–장비사 연결은 납품 관계가 아니다.** 공정 단계–부품 사전으로 이은 것이고 화면에
   그렇게 적혀 있다. 원문에서 납품을 확인하려면 정기보고서 II절에서 장비사 이름 언급을 세는
   단계(kship `suppliers` 에 해당)가 더 필요하다 — 아직 없다.

## ④ 재현 명령

```sh
cd argus/ksemi/tools
python3 -m unittest discover -s tests          # 먼저 통과하는지 본다

python3 ksemi_universe.py --write              # KIND → 후보 154
python3 ksemi_scan.py --write                  # II절 본문 → 편입/보류/배제
python3 ksemi_scan.py --rejudge                #   (재수집 없이 재판정만)
python3 build_dicts.py --write                 # 13단계·부품 사전 + 태그
python3 build_dicts.py --check                 #   (쓰지 않고 교차검증만)
python3 ksemi_contracts.py --all --write       # I001 계약공시
python3 ksemi_reports.py --write               # 8분기 수주상황·매출실적 + 사업보고서 주석
python3 ksemi_reports.py --reparse --write     #   (요청 없이 캐시만 다시 파싱 — 파서 고친 뒤)
python3 ksemi_page.py --all                    # 허브·회사·커버리지
python3 ksemi_parts.py --write                 # 공정 흐름
```

### 주의

- 파이썬 3.9, **표준 라이브러리만**. `pip install` 금지. **API 키를 쓰지 않는다.**
- DART는 **공인 IP 단위**로 막는다(30~60분). `kce_fetch` 의 파일 락이 프로세스 사이 요청
  간격까지 묶지만 **동시에 3개를 넘기지 마라**. 두 수집기를 같이 돌리면 서로 느려진다 —
  계약공시를 먼저 끝내고 정기보고서를 돌리는 편이 벽시계로 빠르다.
- **원문 HTML 캐시(`tools/assets/cache/`)는 커밋하지 않는다**(`.gitignore`). 커밋하는 것은
  파싱 결과 JSON이다. 파서를 고치면 `--reparse` 로 재수집 없이 다시 뽑는다.
- 파서를 고칠 때는 `tools/tests/` 를 같이 키워라 — 이 탭의 덫(단위 캡션이 둘째 머리행 안에
  있는 것, 당기/전기 비교표, EUC-KR `rcpNo[8]=='9'`)은 전부 테스트로 고정돼 있다.
