# T9 — 국가 큐브 core_set 샤딩 (data_jp_country.js 8.92MB → 세트당 54KB)

2026-09-21 작성. AGENTS.md 8항(파일당 5MB) 위반 3건 중 첫 번째 건의 실행 스펙.
**트랙 구분: 수집기가 아니라 빌더 출력 형태 변경이다. 로컬 `jem_site_build.py` 반영이 필요하다.**

## 왜

`data_jp_country.js`는 8.92MB로 한도를 3.9MB 넘긴다. 내용은 `core_set` 142개의 국가 큐브인데,
프론트 소비 지점은 `index.html`의 `countrySrc()` 하나뿐이고 **언제나 세트 하나만 본다**:

```js
function countrySrc(){ const sk=setKey();
  return (cflow()==='imp' && (P.country_i||{})[sk]) ? P.country_i[sk] : (P.country||{})[sk]; }
```

`P.country` 전체를 훑는 코드는 레포 어디에도 없다(`index.html` 4회·`ui/patch.js` 병합부가 전부).
세트 단위로 쪼개면 **최대 335KB · 중앙값 54KB**다. 한도 준수와 별개로, 국가뷰 진입 때
사용자가 받는 양이 8.92MB에서 수십 KB로 떨어지는 게 실익이 더 크다.

0 압축은 답이 아니다. 원소의 62%가 0이지만 `0,`은 2바이트라, 전구간 0 시계열 제거 −4%,
앞뒤 0 트리밍까지 해도 8.92→7.61MB(−15%)로 한도에 못 미친다. 실측했다.

## 산출물 계약

### 1. 샤드 파일 — `data_<reg>_country/<setkey>.js`

```js
var PSHC=window.PSHC||(window.PSHC={});(function(){var R=PSHC["JP"]||(PSHC["JP"]={});
(R.country||(R.country={}))["probe_core"]={…};
(R.country_i||(R.country_i={}))["probe_core"]={…};})();
```

- 로드 순서 무관·중복 로드 안전(멱등). `country_i`에만 있는 세트도 자기 파일을 갖는다.
- 세트 키는 파일명이 되므로 `^[A-Za-z0-9][A-Za-z0-9_.-]*$`만 허용(경로 조작 차단, fail-closed).
- JSON은 `sort_keys=True, ensure_ascii=False, separators=(",",":")` — 같은 데이터면 같은 바이트.

### 2. manifest 리전 필드 (신규 2개)

```js
region.cdir  = "data_jp_country/"          // 샤드 디렉토리
region.csets = ["abrasive_core", …]        // 존재하는 세트 키(없는 세트 404 방지)
```

`region.cfile`은 **지우지 마라.** cdir 미적용 리전의 폴백 경로로 계속 쓴다.

### 3. 참조 구현 — `tools/split_country_sets.py`

```
python3 tools/split_country_sets.py data_jp_country.js JP data_jp_country --verify
```

`--verify`는 샤드를 다시 합쳐 원본 큐브와 바이트 단위로 같은지 확인한 뒤에만 성공한다.
`_index.json`의 `sets` 배열을 그대로 `region.csets`에 넣으면 된다.
전 리전 18개에 돌려 라운드트립을 확인했다(빈 큐브 12개는 세트 0개로 정상 통과).

## 프론트는 이미 준비돼 있다

`ui/patch.js` 모듈 8이 이번 변경으로 4가지 상태를 모두 처리한다. **빌더보다 먼저 배포돼 있어도 안전하다.**

| 상태 | manifest | 동작 |
|---|---|---|
| (a) 빌더 미적용 | 없음 | 폴백 — 동작 변화 없음 |
| (b) 1단계 | `topc`만 | 상위 수출국 칩을 사전계산값으로 |
| (c) 2단계 | `cfile` | 국가뷰 진입 시 리전 큐브 통째로 |
| **(d) 3단계** | **`cdir`+`csets`** | **국가뷰 진입 시 현재 세트 하나만** |

(d)에서 세트는 LRU 12개까지 메모리에 두고 그 위는 놓아준다(최악 1MB 미만).
404가 한 번 나면 그 세트는 재시도하지 않는다 — 렌더마다 요청이 쌓이지 않게.

## 빌더 쪽 할 일 (맥스튜디오)

1. `jem_site_build.py`가 `data_<reg>_country.js`를 쓰던 자리에서 `tools/split_country_sets.py`의
   `shard_js()`·`write_atomic()` 로직을 호출해 `data_<reg>_country/` 디렉토리로 쓴다.
2. manifest의 해당 리전에 `cdir`·`csets`를 넣는다.
3. **전환 기간**: `cfile`(단일 파일)도 당분간 같이 내보내면 롤백이 즉시 된다.
   `cdir`이 있으면 프론트가 그쪽을 먼저 타므로 둘이 공존해도 충돌하지 않는다.
   단 한도 위반 해소가 목적이므로, (d)가 안정되면 단일 파일은 지워야 한다.
4. 크론이 이전 샤드를 지우지 않으면 없어진 세트 파일이 남는다 — 디렉토리를 비우고 다시 쓰거나
   `_index.json`과 대조해 잔여 파일을 정리할 것.

## 검증

```
python3 -m unittest discover -s tools/tests -v     # 14건 (라운드트립·fail-closed·프론트 계약)
node --check ui/patch.js
```

## 남은 2건

`data_kpi.js`(7.39MB)와 `korea_trade.html`(9.84MB)은 별건이다.
조사 결과와 실측 축소안은 프로젝트 파일 `oversize-files-report.md` 참조.
