# Codex 교차 검증 결과 — thyrsus/index.html

## 실행 정보
- 실행 일시: 2026-08-31 (맥스튜디오, MACSTUDIO-CODEX.md 방법 A)
- 도구: OpenAI Codex CLI v0.150.1 · 모델 `gpt-5.6-sol` · reasoning effort **xhigh**
- 샌드박스: `read-only` (index.html 수정 불가 보장) · approval: never
- 세션: `01a0582f-f93f-7b21-b60b-100c01c26c20`
- 입력: `codex-review-packet.md` 전문 + 기수정 16건 재보고 금지 지시
- 검토 대상 커밋: `b5ea4d3` (claude/trouble-brewing-script-1sv6lg)
- Codex 자체 검증: HTML 내 실행 스크립트 추출 후 `node --check` 통과 확인. Playwright 스위트는 저장소에 없어 미실행 — 재현 조건은 코드 경로 기준.
- 공식 근거: TPI roles.json / nightsheet.json + 공식 위키

## 요약 (맥스튜디오 Claude 정리)

**신규 결함 15건** (Critical 2 · High 6 · Medium 6 · Low 1). 기수정 16건 목록과 대조한 결과 **중복 보고 없음** — 인접 영역 4건은 아래 표 비고 참조.

| # | 심각도 | 결함 | 위치(라인) | 비고 |
|---|--------|------|-----------|------|
| 1 | Critical | 승리 차단 상태(주모자 연장전·사악한 쌍둥이)가 `null` 반환으로 기존 선 승리 판정에 떨어짐 | 4314, 4366, 4407 | 기수정 "악 승리 미감지"와 별개 — 이번엔 **선 승리 오판정** 방향 |
| 2 | Critical | 푸카가 `doPoison()` 재사용 → 중독 만료·지연 사망·오작동 판정 전부 오동작 | 1663, 3172 | 기수정 "중독 중복"과 별개 — 푸카 수명주기 자체 문제 |
| 3 | High | 커스텀 캐릭터 `ko`/`id` 무탈출 → 영속 DOM XSS | 1018, 1092, 2185, 2206 | 기수정 "이름 따옴표 XSS"와 다른 벡터(커스텀 캐릭터 경로) |
| 4 | High | 진영을 `charId`에서 유도 → 이발사 교환·건달·팡 구 진영 오염 | 844, 3551, 3377 | `alignment` 필드 부재가 근본 원인 |
| 5 | High | 공통 사망 판정기 부재 → 찻집·악마의 변호사·어릿광대·시장 보호/처형 분기 오류 | 1718, 1675, 1988 | 기수정 "암살자-어릿광대"와 별개 — 판정기 구조 문제 |
| 6 | High | 상태에 `sourcePid` 없음 → 출처 사망/변경 시 중독·취함 잔존, `drunkS` 만료 없음 | 852, 870, 3847, 723 | 기수정 "낮 보호 토큰 잔존"과 별개 — 출처 연동 문제 |
| 7 | High | 비고르모르티스가 죽인 하수인이 능력 상실 (밤 단계 스킵·마녀 판정 제외) | 1718, 1428, 1855, 3395 | |
| 8 | High | BMR·SV 첫밤 순서 공식과 불일치 + `renderSheet()`가 정보 단계 강제 선두 배치 | 803, 806, 1260 | BMR: 하수인→미치광이→악마, SV: 철학자→하수인→악마가 공식 |
| 9 | Medium | 셋업 구성 보정이 남작만 지원 (대부±1·팡 구+1·비고르모르티스−1 누락) | 1043, 1202 | |
| 10 | Medium | 지명 취소 시 소비된 사망 투표 토큰 미복원 | 1960, 1987 | |
| 11 | Medium | 집사 무효표가 경고만 뜨고 실제 집계에 포함됨 | 1956, 1977 | |
| 12 | Medium | 밤 위저드 대상 필터 오류 (꿈꾸는 자-여행자 허용, 재봉사 자기 선택, 사망자 선택 불가 등) | 2777, 3314, 3333, 3349, 3371 | 기수정 "위저드 씬 전역 오염"과 별개 — 필터 규칙 문제 |
| 13 | Medium | 미치광이 밤 지목의 악마 전달을 "재량"으로 오안내 (공식은 필수) | 637, 3155 | |
| 14 | Medium | 노 다시 독 대상을 사망 시 재계산하라고 오안내 (생사 무관 최근접 주민이 공식) | 791, 2713, 3383 | |
| 15 | Low | 곡예사를 "2일 밤" 고정 처리 → 도중 생성된 곡예사 능력 사용 불가 | 733, 3430 | |

### 수정 우선순위 제안
1. **#1, #2** (Critical): 승패 판정과 악마 능력 직결 — 최우선.
2. **#3** (XSS): `onclick` 문자열 보간 제거 + `esc()` 적용. HTML 이스케이프만으로 JS 문자열 문맥은 못 막는다는 지적 유의.
3. **#4~#6**: 공통 구조 문제(진영 필드, 사망 판정기, 상태 출처 연동). 개별 패치보다 구조 도입이 재발 방지에 유리 — #5·#6·#7이 모두 여기서 파생.
4. **#8**: 밤 순서 데이터 수정은 저위험 — 배열 교체로 즉시 해결.
5. 나머지 Medium/Low는 위저드 안내문·필터 수정 위주.

### 주의사항
- 원문 내 파일 링크는 맥스튜디오 로컬 절대경로 포함(원문 보존 차원에서 유지). 라인 번호는 커밋 `b5ea4d3` 기준.
- #11(집사)·#12(위저드 필터) 일부는 하우스룰 의도와 겹칠 수 있음 — 수정 세션에서 의도 여부 판단 필요.
- Codex는 실행 검증 없이 코드 경로 분석만 수행. 수정 후 Playwright 회귀 필수.

---

## Codex 원문 출력 (verbatim)

검토 결과, 제외 목록과 알려진 제약을 빼고도 추가 결함 15건을 확인했습니다. 파일은 수정하지 않았으며, HTML의 실행 스크립트를 추출한 `node --check`는 통과했습니다. 제공되지 않은 Playwright 스위트는 실행하지 못해 아래 재현은 코드 경로 기준입니다.

공식 기준은 TPI의 [역할 데이터](https://release.botc.app/resources/data/roles.json)와 [밤 순서 데이터](https://release.botc.app/resources/data/nightsheet.json)를 사용했습니다.

## Critical

1. **승리 차단 상태가 `null`로 표현되어 오히려 기존 선 승리 판정으로 떨어짐**

   - 위치/요약: [thyrsus/index.html:4314](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:4314), [thyrsus/index.html:4366](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:4366), [thyrsus/index.html:4407](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:4407). `evalWinEvent()`가 탕녀·주모자·사악한 쌍둥이로 게임이 계속될 때 `null`을 반환하지만, 래퍼는 이를 일반 미판정으로 보고 `_orig()`를 호출합니다. `_orig()`는 마지막 악마가 죽었다며 선 승리를 선언합니다.
   - 재현: 정상 작동하는 주모자가 살아 있는 BMR에서 악마를 처형하거나, 두 쌍둥이가 살아 있는 SV에서 마지막 악마를 죽입니다. `return null` 뒤 기존 `checkEndConditions()`가 실행되어 `showGameOver('good')`까지 도달합니다.
   - 기대 동작: 주모자는 정확히 하루의 연장전을 시작해야 하며, 다음 낮에는 “죽었는지”가 아니라 어느 팀 플레이어가 처형됐는지로 승패를 결정해야 합니다. 사악한 쌍둥이는 지정된 선한 쌍둥이와 둘 다 살아 있을 때만 선 승리를 막아야 합니다. [공식 주모자 규칙](https://wiki.bloodontheclocktower.com/Mastermind)
   - 제안 패치: 승리·계속·미판정을 구분하고 상태를 저장하십시오.
     ```js
     // 예시
     return {kind:'continue', reason:'mastermind'};
     
     if (res?.kind === 'win') return askWin(res);
     if (res?.kind === 'continue') {
       if (res.reason === 'mastermind') {
         S.mastermindDay = S.phase.n + 1;
       }
       save();
       return;
     }
     _orig(cause, aliveBefore);
     ```
     `goodTwinPid`, `mastermindDay`를 영속 상태로 저장하고, 다음 낮 무처형/선 처형/악 처형을 별도 종결 이벤트로 처리해야 합니다.

2. **푸카가 독살범 로직을 재사용해 중독·사망 시점과 오작동 판정이 모두 깨짐**

   - 위치/요약: [thyrsus/index.html:1663](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1663), [thyrsus/index.html:3172](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3172). 푸카도 `doPoison()`을 호출하지만 이 함수는 독살범만 검사하고, 토큰을 다음 밤 시작 즉시 만료시킵니다. 위저드는 또한 이전 희생자의 죽음을 새 지목보다 먼저 안내합니다.
   - 재현: 첫날 푸카가 A를 고르면 A의 독은 밤 2 시작의 `expireStatuses()`에서 먼저 사라집니다. 푸카가 궁정대신 등에 의해 취해 있어도 `poisoner`를 찾지 못하므로 새 대상 B가 중독됩니다. 이전 대상 ID도 저장되지 않아 지연 사망을 자동 판정할 수 없습니다.
   - 기대 동작: 푸카는 새 대상을 지목해 중독시킨 직후 이전 중독자가 죽고 건강해집니다. 푸카가 현재 오작동이면 새 중독은 생기지 않고 이전 독의 사망도 보류되며, 정상으로 돌아오면 이어집니다. [공식 푸카 규칙](https://wiki.bloodontheclocktower.com/Pukka)
   - 제안 패치: `doPukkaPick()`을 분리하고 `S.pukkaVictimId`와 출처를 저장하십시오. 푸카 정상 작동 시 “새 독 부여 → 이전 희생자 사망 시도 → 이전 독 해제” 순으로 처리하고, 오작동 시 기존 희생자를 그대로 유지해야 합니다. 푸카 독에는 페이즈 기반 `expiresAt`을 넣으면 안 됩니다.

## High

3. **커스텀 캐릭터를 통한 영속 DOM XSS**

   - 위치/요약: [thyrsus/index.html:1018](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1018), [thyrsus/index.html:1092](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1092), [thyrsus/index.html:2185](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:2185), [thyrsus/index.html:2206](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:2206). 커스텀 `ko`가 `innerHTML`에 무탈출 삽입되고, 가져온 `id`는 검증 없이 `onclick="... '${c.id}' ..."`에 들어갑니다.
   - 재현: 커스텀 이름으로 `<img src=x onerror=alert(1)>`을 저장하고 스크립트 화면을 렌더합니다. 또는 `id`가 `x');alert(1);//`인 JSON을 가져온 뒤 삭제 버튼을 누릅니다. localStorage와 클라우드 스냅샷에도 payload가 남습니다.
   - 기대 동작: 표시 문자열은 텍스트로만 렌더되고, 가져온 JSON이 실행 가능한 HTML/JS 문맥에 들어가지 않아야 합니다.
   - 제안 패치: `S.customs.map(c => esc(c.ko))`로 표시값을 이스케이프하고, 가져오기 시 ID·타입·필드 길이를 검증하십시오. `onclick` 문자열 보간은 제거하고 `data-char-id`와 `addEventListener`를 사용해야 합니다. HTML escaping만으로 JS 문자열 문맥을 안전하게 만들 수는 없습니다.

4. **플레이어 진영을 캐릭터 타입에서 계산해 캐릭터 변경 후 진영이 오염됨**

   - 위치/요약: [thyrsus/index.html:844](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:844), [thyrsus/index.html:3551](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3551), [thyrsus/index.html:3377](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3377). `isEvil()`은 현재 `charId`만 보며, 이발사 교환도 `charId`만 맞바꿉니다. 건달·팡 구의 진영 변경을 저장할 필드도 없습니다.
   - 재현: 이발사가 죽은 뒤 선한 꿈꾸는 자와 악한 마녀의 캐릭터를 교환합니다. 이후 전자는 악, 후자는 선으로 잘못 집계되어 예언자·재봉사·얼뜨기·승리 판정 등이 뒤집힙니다. 팡 구 점프도 새 팡 구의 악 진영과 1회 사용 여부를 기록할 수 없습니다.
   - 기대 동작: 이발사 교환은 진영을 보존하며 악마 자신도 교환 대상으로 선택할 수 있고, “다른 악마”만 금지됩니다. [공식 이발사 규칙](https://wiki.bloodontheclocktower.com/Barber)
   - 제안 패치: 플레이어에 독립적인 `alignment`를 추가하고 `isEvil(p)`가 이를 읽게 하십시오. 이발사는 캐릭터만, 뱀 조련사는 캐릭터와 진영을, 건달·팡 구는 해당 플레이어의 진영만 명시적으로 갱신해야 합니다. 구버전 저장본에는 스키마 버전과 마이그레이션을 추가하고, 이미 교환된 게임은 진영 확인을 요청하는 편이 안전합니다. 752·3404행의 “악마 자신은 스왑 불가” 안내도 수정해야 합니다.

5. **공통 사망 판정기가 없어 보호 우선순위와 ‘처형됐지만 살았다’ 상태가 잘못 처리됨**

   - 위치/요약: [thyrsus/index.html:1718](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1718), [thyrsus/index.html:1675](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1675), [thyrsus/index.html:1988](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1988).
   - 재현:
     - 찻집 여인 보호 시 취소를 누르면 `executedToday`가 설정되지 않아 “처형 자체가 없었던 날”이 됩니다. 확인을 누르면 정상 작동하는 보호를 무시하고 죽일 수도 있습니다.
     - 악마의 변호사 단계는 안내문만 있고 상태 토큰/처형 분기가 없어 보호 대상이 죽습니다.
     - `doStepKill()`은 멀쩡한 선원과 여관 주인 보호를 검사하지 않습니다.
     - 정상·미소진 어릿광대에서 확인창을 취소하면 첫 생존 능력을 임의로 무시하고 죽일 수 있습니다. 공식 능력은 강제입니다. [공식 어릿광대 규칙](https://wiki.bloodontheclocktower.com/Fool)
     - 시장 대체 희생자는 살아 있는 사람만 고를 수 있고, 군인·수도사 보호도 무시합니다. 공식적으로 죽은 사람이나 보호된 사람을 대체 대상으로 고르면 아무도 죽지 않을 수 있습니다. [공식 시장 규칙](https://wiki.bloodontheclocktower.com/Mayor)
   - 기대 동작: “처형 발생”과 “사망 발생”은 분리되어야 합니다. 보호 우선순위를 적용한 뒤 실제로 죽을 때만 어릿광대 능력을 소진해야 합니다.
   - 제안 패치: 모든 경로가 사용하는 `attemptDeath(target, context)`와 `executePlayer()`를 만드십시오. 반환값을 `{executed, died, preventedBy}`로 만들고, 처형은 사망 여부와 무관하게 `executedToday`를 기록하십시오. 악마의 변호사·여관 주인 보호는 출처와 만료가 있는 상태로 실제 부여해야 합니다.

6. **상태가 출처 능력과 연결되지 않고 임시 취함도 영구 상태로만 표현됨**

   - 위치/요약: [thyrsus/index.html:852](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:852), [thyrsus/index.html:870](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:870), [thyrsus/index.html:3847](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3847), [thyrsus/index.html:723](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:723). 상태에는 사람이 읽는 `source` 문자열만 있고 `sourcePid`가 없습니다. `killPlayer()`도 출처가 사라진 효과를 정리하지 않으며, `drunkS`에는 만료가 없습니다.
   - 재현: 독살범이 A를 중독시킨 뒤 낮에 죽거나 다른 캐릭터가 되어도 A는 다음 밤까지 중독입니다. 선원·여관 주인·건달의 취함을 수동 토글하면 황혼에 해제되지 않습니다. 철학자가 죽거나 취해도 원래 능력 보유자의 “영구 취함”이 남습니다.
   - 기대 동작: 독살범이 더 이상 독살범 능력을 가지지 않으면 독이 즉시 끝나야 합니다. 철학자가 능력을 잃으면 원 보유자는 즉시 깨어나며, 선원·여관 주인·건달은 황혼, 궁정대신은 3밤+3낮에 끝나야 합니다. [독살범](https://wiki.bloodontheclocktower.com/Poisoner), [철학자](https://wiki.bloodontheclocktower.com/Philosopher), [건달](https://wiki.bloodontheclocktower.com/Goon)
   - 제안 패치: 상태를 `{key, sourcePid, sourceRole, expiryPolicy}`로 구조화하고 `phase`, `sourceAbility`, `duration` 만료 정책을 분리하십시오. 사망·캐릭터 변경·중독/취함 변경 때 `reconcileStatuses()`로 출처 의존 효과를 재평가해야 합니다.

7. **비고르모르티스가 죽인 하수인이 실제로는 능력을 잃음**

   - 위치/요약: [thyrsus/index.html:1718](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1718), [thyrsus/index.html:1428](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1428), [thyrsus/index.html:1855](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1855), [thyrsus/index.html:3395](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3395). 살해 함수는 하수인을 평범하게 죽이고, 밤 단계는 좀버얼을 제외한 모든 죽은 보유자를 건너뜁니다. 마녀 판정도 살아 있는 마녀만 찾습니다.
   - 재현: 비고르모르티스가 마녀를 죽입니다. 다음 밤 마녀 단계가 “사망 — 깨우지 않음”으로 건너뛰어지고, 기존 저주도 다음 밤 만료됩니다.
   - 기대 동작: 비고르모르티스가 죽인 모든 하수인은 비고르모르티스가 능력을 유지하는 동안 능력을 계속 가지며, 각각 주민 이웃 하나를 중독시킵니다. [공식 비고르모르티스 규칙](https://wiki.bloodontheclocktower.com/Vigormortis)
   - 제안 패치: 살해 시 `vigorAbility` 상태와 중독 대상 ID를 기록하고, `stepSkipReason()`과 마녀·쌍둥이 등 수동 판정은 `alive || hasActiveAbility(p)`를 사용하십시오. 비고르모르티스가 죽거나 오작동하면 연결된 능력·독을 재평가해야 합니다.

8. **BMR·SV 첫날 밤 순서가 공식 순서와 다르고 시트 렌더러가 배열 수정도 무시함**

   - 위치/요약: [thyrsus/index.html:803](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:803), [thyrsus/index.html:806](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:806), [thyrsus/index.html:1260](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1260).
   - 재현: BMR 첫밤은 `악마 정보 → 미치광이`로 표시되며, SV는 `하수인 정보 → 악마 정보 → 철학자`로 표시됩니다. `renderSheet()`는 어떤 에디션이든 정보 단계를 맨 앞에 다시 붙입니다.
   - 기대 동작: 공식 순서는 BMR이 `하수인 정보 → 미치광이 → 악마 정보`, SV가 `철학자 → 하수인 정보 → 악마 정보`입니다. [공식 밤 순서](https://release.botc.app/resources/data/nightsheet.json)
   - 제안 패치:
     ```js
     bmr.first = ['minioninfo','lunatic','demoninfo', /* ... */];
     sv.first  = ['philosopher','minioninfo','demoninfo', /* ... */];
     const firstFull = ed.first;
     ```

## Medium

9. **셋업 구성 계산이 남작만 지원함**

   - 위치/요약: [thyrsus/index.html:1043](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1043), [thyrsus/index.html:1202](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1202). 대부 ±1, 팡 구 +1, 비고르모르티스 −1 외지인 보정이 검증과 무작위 배정에 반영되지 않습니다.
   - 재현: 팡 구가 포함된 정상 구성에서 외지인을 하나 늘리면 “구성 불일치”가 나오며, SV 무작위 배정도 기본 구성으로 팡 구를 뽑을 수 있습니다.
   - 기대 동작: 역할의 공식 셋업 수정치를 반영해야 합니다. [공식 역할 데이터](https://release.botc.app/resources/data/roles.json)
   - 제안 패치: 선택된 역할 목록으로 `setupDelta`를 계산하고 주민/외지인 수에 적용하십시오. 대부는 `S.godfatherOutsiderDelta = -1 | 1` 선택값을 저장해야 합니다.

10. **지명 취소 시 해당 지명에서 소비한 사망 투표 토큰이 복원되지 않음**

   - 위치/요약: [thyrsus/index.html:1960](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1960), [thyrsus/index.html:1987](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1987). `castVote()`는 `deadVote=false`로 만들지만 `cancelNom()`은 지명만 삭제합니다.
   - 재현: 사망자가 찬성 또는 반대표를 낸 뒤 “지명 취소”를 누릅니다. 투표 기록은 사라지지만 토큰은 소진된 상태로 남습니다.
   - 기대 동작: 투표 자체가 취소되었으므로 그 지명에서 소비된 토큰도 복원되어야 합니다.
   - 제안 패치:
     ```js
     function cancelNom(nid) {
       const n = findNom(nid);
       for (const pid of n?.deadVoters || []) {
         const p = playerOf(pid);
         if (p) p.deadVote = true;
       }
       S.noms = S.noms.filter(x => x.id !== nid);
       // ...
     }
     ```

11. **집사의 무효 표가 경고만 표시되고 실제 집계에는 포함됨**

   - 위치/요약: [thyrsus/index.html:1956](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1956), [thyrsus/index.html:1977](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1977). UI는 주인이 투표하지 않았다고 경고하지만 `n.hands.length`와 모든 `yes`를 그대로 셉니다.
   - 재현: 과반까지 한 표 부족한 상황에서 집사만 거수/찬성하고 주인은 참여하지 않습니다. 두 단계 모두 집사 표로 통과할 수 있습니다.
   - 기대 동작: 정상 작동하는 집사의 표는 같은 단계에서 주인도 투표할 때만 유효해야 합니다. [공식 집사 능력](https://release.botc.app/resources/data/roles.json)
   - 제안 패치: 마감 시 `validHands`와 `validYes`를 계산하거나, 집사가 선택할 때 주인의 동시 참여가 없으면 입력을 거부하십시오. 현재 2단계 UI 의미대로라면 주인의 찬성 여부를 기준으로 일관되게 집계해야 합니다.

12. **밤 위저드 대상 필터가 공식 선택 범위를 체계적으로 위반함**

   - 위치/요약: [thyrsus/index.html:2777](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:2777), [thyrsus/index.html:3314](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3314), [thyrsus/index.html:3333](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3333), [thyrsus/index.html:3349](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3349), [thyrsus/index.html:3371](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3371).
   - 재현:
     - 꿈꾸는 자는 여행자를 선택할 수 있습니다.
     - 재봉사는 자기 자신을 두 명 중 하나로 고를 수 있습니다.
     - 마귀할멈·세레노버스·도박사 및 여러 악마는 공식적으로 “플레이어”를 고르지만 위저드는 생존자만 보여줍니다.
     - 세레노버스의 광기 캐릭터 풀은 주민만 있어 외지인을 선택할 수 없습니다.
   - 기대 동작: 역할별로 `notSelf`, `notTraveller`, `aliveOnly`를 독립 적용해야 합니다. 꿈꾸는 자 제한과 재봉사 자기 제외 등은 [공식 역할 데이터](https://release.botc.app/resources/data/roles.json)에 명시되어 있습니다.
   - 제안 패치: 문자열 하나짜리 필터 대신 `{aliveOnly, excludeSelf, excludeTravellers}` 조건을 사용하고, `good` 캐릭터 풀을 주민+외지인으로 추가하십시오. 죽은 대상을 고른 살해는 “합법적인 선택이나 사망 없음”으로 기록해야 합니다.

13. **미치광이의 밤 지목을 진짜 악마에게 알려주는 것을 재량으로 안내함**

   - 위치/요약: [thyrsus/index.html:637](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:637), [thyrsus/index.html:3155](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3155).
   - 재현: 미치광이가 살해 대상을 고른 뒤 안내대로 진짜 악마에게 이를 전달하지 않고 진행합니다.
   - 기대 동작: 진짜 악마는 미치광이와 그가 밤에 고른 대상을 알아야 합니다. 선택적으로 그대로 죽일 수 있을 뿐, 대상 전달 자체는 재량이 아닙니다. [공식 미치광이 데이터](https://release.botc.app/resources/data/roles.json)
   - 제안 패치: “재량으로 전달”을 삭제하고, 미치광이를 재운 다음 진짜 악마를 깨워 미치광이 토큰과 대상 모두를 보여주는 필수 장면을 추가하십시오.

14. **노 다시 독 대상을 사망 때마다 재계산하라고 잘못 안내함**

   - 위치/요약: [thyrsus/index.html:791](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:791), [thyrsus/index.html:2713](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:2713), [thyrsus/index.html:3383](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3383).
   - 재현: 노 다시의 가장 가까운 주민 이웃이 죽으면 안내에 따라 그다음 살아 있는 주민으로 독 토큰을 옮깁니다.
   - 기대 동작: 생사와 관계없이 양방향의 가장 가까운 주민이 계속 중독됩니다. 캐릭터 타입 또는 노 다시 보유자가 바뀔 때만 대상이 달라질 수 있습니다. [공식 노 다시 규칙](https://wiki.bloodontheclocktower.com/No_Dashii)
   - 제안 패치: 세 안내문의 “사망 변동”을 삭제하고 “캐릭터 변경·노 다시 변경 시 재계산”으로 교체하십시오.

## Low

15. **곡예사를 고정된 둘째 밤에만 처리해 도중 생성된 곡예사가 능력을 못 씀**

   - 위치/요약: [thyrsus/index.html:733](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:733), [thyrsus/index.html:3430](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3430). “2일 밤에만”으로 고정되어 있습니다.
   - 재현: 마귀할멈이 셋째 밤에 플레이어를 곡예사로 만듭니다. 그 플레이어의 첫 낮 이후 밤에도 위저드는 둘째 밤 전용이라고 안내합니다.
   - 기대 동작: 곡예사는 게임의 첫날이 아니라 자신이 곡예사로서 맞는 첫날에 추측하고 그날 밤 결과를 받습니다. [공식 곡예사 능력](https://release.botc.app/resources/data/roles.json)
   - 제안 패치: `jugglerFirstDay`와 추측 기록을 플레이어별로 저장하고, 캐릭터 획득 다음 낮을 첫날로 설정하십시오. 고정된 `S.phase.n===2` 조건은 제거해야 합니다.
---

# 2차 Codex 교차 검증 — 맥미니 로컬 세션

## 실행 정보
- 실행 일시: 2026-09-01 (맥미니, MACMINI-CODEX.md 방법 A)
- 도구: OpenAI Codex CLI **v0.152.0** · 샌드박스 `read-only`(index.html 수정 불가 보장)
- 입력: `codex-review-packet.md` 전문 (1차와 동일 조건, 기수정 16건 재보고 금지)
- 검토 대상 커밋: `757a81a` — index.html 내용은 1차와 동일(`b5ea4d3` 시점) 
- 토큰: 125,345 · 공식 근거: TPI roles.json / nightsheet.json + 공식 위키
- 1차(맥스튜디오)와 **독립 실행** — 1차 결과를 입력으로 주지 않았음

## 요약 (맥미니 Claude 정리)

**결함 13건** (Critical 4 · High 4 · Medium 5). 1차 15건과 교차하면 **독립 재현된 4건**이 특히 신뢰도가 높다.

| # | 심각도 | 결함 | 위치(라인) | 1차 대조 |
|---|--------|------|-----------|----------|
| 1 | Critical | 탕녀 계승이 상태에 미반영 — `charId` 미변경으로 이후 악마 없이 게임 진행 | 910, 4365 | **신규**. 1차 #1과 같은 `return null` 지점의 반대편 증상 |
| 2 | Critical | 중독·취한 좀버얼도 첫 사망을 무조건 무효화 (`fakedead` 선부여) | 873 | **신규** |
| 3 | Critical | `doStepKill()`이 군인 면역·여관주인 보호·선원을 무시 | 1718 | 1차 #5와 **독립 재현** |
| 4 | Critical | 커스텀 캐릭터 `id`가 `onclick`에 무검증 삽입 → 저장형 XSS | 2183, 2206 | 1차 #3과 **독립 재현** |
| 5 | High | 어릿광대 첫 생존을 확인창 취소로 무산 가능 (강제 능력인데 재량 처리) | 881 | 신규 |
| 6 | High | BMR·SV 첫날 밤 순서 불일치 (BMR: 하수인→미치광이→악마 / SV: 철학자→하수인→악마) | 803, 806 | 1차 #8과 **독립 재현·동일 결론** |
| 7 | High | 낮에 부여한 보호가 정작 쓸 밤 시작에 만료 (`{kind:'night',n+1}` 오류) | 1368, 3854 | 1차 #6 인접(다른 벡터) |
| 8 | High | 좀버얼 첫 사망에서 `checkEndConditions()` 자체를 건너뜀 | 874 | 신규 |
| 9 | Medium | 사망자 투표 토큰이 선택 변경·기권 시 복원됨 | 1963 | 1차 #10 인접(취소 vs 변경) |
| 10 | Medium | 동일인 재지명 최고율 2회를 "동률 처형 없음"으로 오처리 | 1803 | 신규 |
| 11 | Medium | 화가 안내가 정상 작동 중에도 무응답을 허용 | 727 | 신규 |
| 12 | Medium | 구버전 저장본 마이그레이션이 최상위 `Object.assign`뿐 — `deadVoters` 누락 시 예외 | 832, 1967, 3080 | 신규 |
| 13 | Medium | `cloudBuildDoc()`가 `#winask`·`#gameover` 오버레이를 비우지 않음 | 3037, 3040 | 1차 미보고 |

### 1·2차 종합 Critical 집합 (배포 전 필수 수정)
- **A.** 승리 차단(주모자·사악한 쌍둥이)이 `null` 반환 → `_orig()`가 "선한 팀 승리" 오선언 (1차 #1)
- **B.** 푸카가 `doPoison()` 재사용 → 중독 수명·지연 사망·오작동 판정 붕괴 (1차 #2)
- **C.** 탕녀 계승 미반영 → 악마 없는 게임 진행 (2차 #1)
- **D.** 오작동 좀버얼도 첫 사망 무효화 (2차 #2)
- **E.** `doStepKill()`이 군인·보호·선원 무시 (1차 #5 = 2차 #3, 독립 재현)
- **F.** 커스텀 캐릭터 `id` 저장형 XSS (1차 #3 = 2차 #4, 독립 재현)

### 주의사항
- Codex는 실행 검증 없이 정적 코드 경로 분석만 수행. 수정 후 브라우저 회귀 필수.
- 2차는 TB의 밤 순서 배열과 BMR/SV의 "그 외 밤" 배열에서는 추가 불일치를 찾지 못했다고 명시.

---

## Codex 원문 출력 (verbatim, 2차)

읽기 전용으로 검토했으며 파일은 수정하지 않았습니다. 공식 역할 데이터와 공식 밤 순서 JSON을 기준으로 대조했습니다. 자동 테스트 스위트는 저장소에 없어 정적 코드 경로 분석으로 재현 조건을 확인했습니다.

## 치명적

### 1. 탕녀 계승이 상태에 반영되지 않아 이후 게임이 악마 없이 진행됨

위치: [thyrsus/index.html:910](thyrsus/index.html:910), [thyrsus/index.html:4365](thyrsus/index.html:4365)

1. 결함 요약: 계승 조건을 감지해 안내만 할 뿐 탕녀의 `charId`를 죽은 악마로 변경하지 않는다. 이후 `demonAlive`는 계속 false이고 밤 순서에도 악마가 나타나지 않는다.
2. 재현 조건: 생존자 5명 이상에서 정상 작동 중인 탕녀가 있고 임프를 처형하거나 처단자로 죽인다.
3. 기대 동작: 탕녀가 즉시 임프로 바뀌고 이후 악마로 등록·행동해야 한다. 공식 규칙도 탕녀 토큰을 임프 토큰으로 교체하라고 명시한다. [Scarlet Woman 공식 위키](https://www.wiki.bloodontheclocktower.com/Scarlet_Woman)
4. 제안 패치: 계승을 별도 `promoteScarletWoman(deadDemonId)` 사건으로 구현해 `sw.charId=deadDemonId`와 관련 밤 순서·상태를 원자적으로 갱신한다. 단, 팡 구 점프 징크스는 이 경로를 호출하지 않아야 한다.

### 2. 중독·취한 좀버얼도 첫 사망을 무조건 무효화함

위치: [thyrsus/index.html:873](thyrsus/index.html:873)

1. 결함 요약: `killPlayer()`가 오작동 여부를 확인하기 전에 무조건 `fakedead`를 부여한다.
2. 재현 조건: 중독 또는 취한 좀버얼이 처음 죽는다.
3. 기대 동작: 오작동 상태에서는 첫 사망 생존 능력이 없으므로 실제로 죽고 선한 팀 승리를 판정해야 한다. [Zombuul 공식 위키](https://wiki.bloodontheclocktower.com/Zombuul)
4. 제안 패치: 첫 분기를 `p.charId==='zombuul' && !hasStatus(...,'fakedead') && !isMalfunctioning(p)`로 제한한다.

### 3. BMR/SV 악마 살해 자동화가 주요 생존·보호 능력을 무시함

위치: [thyrsus/index.html:1718](thyrsus/index.html:1718)

1. 결함 요약: `doStepKill()`은 찻집 여인만 자동 검사하고 곧바로 `killPlayer()`를 호출한다. 따라서 군인, 여관 주인 보호, 정상 선원 등이 샤발로스·포·팡 구 등에게 잘못 죽는다. 반대로 암살자만 찻집 여인을 관통하도록 특별 처리돼 있어 UI가 일부 자동화된 것처럼 보인다.
2. 재현 조건: 커스텀 시트의 군인을 BMR/SV 악마가 지목하거나, 여관 주인이 보호한 대상을 BMR 악마가 지목한다.
3. 기대 동작: 모든 악마 살해는 군인 면역과 해당 밤 보호를 적용해야 한다. 정상 선원은 사망 원인을 불문하고 죽지 않는다. 암살자만 이러한 방어를 관통한다. [Assassin 공식 위키](https://wiki.bloodontheclocktower.com/Assassin)
4. 제안 패치: `resolveDeathAttempt(target,{source,sourceType,bypassProtection})` 하나로 보호 우선순위를 통합하고 `doImpKill`과 `doStepKill`이 모두 사용하게 한다.

### 4. 가져온 커스텀 캐릭터 ID를 통한 저장형 XSS

위치: [thyrsus/index.html:2183](thyrsus/index.html:2183), [thyrsus/index.html:2206](thyrsus/index.html:2206)

1. 결함 요약: `importScript()`가 `customs`를 스키마 검증 없이 저장하고, `c.id`를 `onclick="delCustom('${c.id}')"`에 직접 삽입한다.
2. 재현 조건: `id`가 `x');alert(document.domain);//` 같은 커스텀 JSON을 가져온 뒤 커스텀 탭을 렌더링한다.
3. 기대 동작: 가져온 데이터는 HTML·JS 문맥을 탈출할 수 없어야 한다.
4. 제안 패치: 인라인 이벤트를 제거하고 `data-id`+`addEventListener`를 사용한다. 가져오기 시 ID를 안전한 내부 ID로 재발급하거나 `/^[A-Za-z0-9_-]+$/`로 제한하고 필드 타입·길이도 검증한다.

## 높음

### 5. 어릿광대의 첫 생존을 임의로 취소할 수 있음

위치: [thyrsus/index.html:881](thyrsus/index.html:881)

1. 결함 요약: 확인창에서 취소하면 정상 작동 중인 미사용 어릿광대가 그대로 죽는다.
2. 재현 조건: 정상 어릿광대의 첫 사망에서 확인창의 취소를 선택한다.
3. 기대 동작: “처음 죽게 될 때 죽지 않는다”는 강제 능력이다. 사회자 재량이 아니다. 암살자 또는 오작동처럼 능력을 우회하는 원인만 예외다. [Fool 공식 위키](https://wiki.bloodontheclocktower.com/Fool)
4. 제안 패치: 정상적인 첫 사망에서는 확인 없이 자동으로 `spent`를 부여하고 사망을 막는다. 확인창은 진단 안내만 제공하거나 제거한다.

### 6. 공식 밤 순서와 다른 첫날 밤 배열

위치: [thyrsus/index.html:803](thyrsus/index.html:803), [thyrsus/index.html:806](thyrsus/index.html:806)

1. 결함 요약:
   - BMR은 `minioninfo → demoninfo → lunatic`이지만 공식 순서는 `minioninfo → lunatic → demoninfo`.
   - SV는 `minioninfo → demoninfo → philosopher`이지만 공식 순서는 `philosopher → minioninfo → demoninfo`.
2. 재현 조건: BMR 또는 SV 첫날 밤 위저드를 실행한다.
3. 기대 동작: 공식 전체 밤 순서에서 해당 에디션 역할만 필터링한 순서와 같아야 한다. [공식 nightsheet.json](https://release.botc.app/resources/data/nightsheet.json)
4. 제안 패치:
   - BMR 시작부를 `['minioninfo','lunatic','demoninfo', ...]`
   - SV 시작부를 `['philosopher','minioninfo','demoninfo', ...]`
   로 변경한다.

### 7. 낮에 수동 부여한 보호가 사용할 밤 시작과 동시에 만료됨

위치: [thyrsus/index.html:1368](thyrsus/index.html:1368), [thyrsus/index.html:3854](thyrsus/index.html:3854)

1. 결함 요약: 낮에 보호를 추가하면 만료를 `{kind:'night', n:ph.n+1}`로 설정한다. `advancePhase()`가 바로 그 밤 시작에 `expireStatuses()`를 호출하므로 보호가 한 번도 작동하지 않는다.
2. 재현 조건: 낮 1에 보호 토큰을 수동 추가하고 밤 2로 진행한다.
3. 기대 동작: 밤 2 동안 유지되고 낮 2 시작에 해제돼야 한다.
4. 제안 패치: 낮에 다음 밤용으로 부여할 때 `{kind:'day', n:ph.n+1}`을 사용한다. 두 중복 구현을 공통 만료 계산 함수로 합친다.

### 8. 좀버얼 첫 사망에서 승리·생존 2인 판정 자체를 건너뜀

위치: [thyrsus/index.html:874](thyrsus/index.html:874)

1. 결함 요약: 죽은 척 처리 후 즉시 `return`하여 `checkEndConditions()`를 부르지 않는다.
2. 재현 조건: 겉보기 생존자가 좀버얼 포함 3명일 때 좀버얼이 처음 “죽는다”. 타운스퀘어상 생존자는 2명만 남는다.
3. 기대 동작: 좀버얼 특례에 따라 게임은 계속되지만, 일반 “악마 생존+생존 2인” 자동 승리와 명확히 구분해 판정해야 한다. 현재는 우연히 판정 전체를 생략해 작동한다.
4. 제안 패치: `evalWinEvent`에 `zombuulFakeDeath` 사건을 명시하고, 일반 2인 승리 규칙의 예외로 처리한다. 숨은 생존 여부를 `alive`와 별도 필드로 모델링하는 편이 안전하다.

## 중간

### 9. 사망자의 투표 선택 취소·기권 시 이미 쓴 토큰이 복원됨

위치: [thyrsus/index.html:1963](thyrsus/index.html:1963)

1. 결함 요약: 사망자가 찬성/반대를 누른 뒤 같은 선택을 취소하거나 기권으로 바꾸면 `deadVote=true`로 복원된다.
2. 재현 조건: 사망자가 2차 투표에서 찬성을 누른 뒤 다시 찬성 또는 기권을 누른다.
3. 기대 동작: 요청된 하우스룰의 “사망 토큰 1회 소진”이라면 유효 투표를 행사한 순간 영구 소진돼야 한다. UI 수정은 가능하되 토큰은 복원하지 않아야 한다.
4. 제안 패치: `deadVote`와 현재 선택을 분리한다. 최초 yes/no에 `deadVote=false`를 고정하고 이후 선택 변경은 `votes[pid]`만 변경한다.

### 10. 동일 피지명자의 동일 최고율 결과도 “동률 처형 없음”으로 처리됨

위치: [thyrsus/index.html:1803](thyrsus/index.html:1803)

1. 결함 요약: 동률을 지명 레코드 단위로 계산한다. 같은 사람을 재지명해 같은 최고 찬성률을 두 번 받으면 서로 다른 처형 후보가 아닌데도 `tie=true`가 된다.
2. 재현 조건: A를 두 번 지명하고 두 투표 모두 같은 최고 찬성률로 통과시킨다.
3. 기대 동작: “찬성률 최고자”가 한 명이면 A가 처형 후보여야 한다. 서로 다른 피지명자가 최고율일 때만 동률이다.
4. 제안 패치: 최고율 레코드들의 `nominee`를 `Set`으로 모아 서로 다른 ID가 2개 이상일 때만 동률로 처리한다.

### 11. 화가 안내가 정상 작동 중에도 사회자의 무응답을 허용함

위치: [thyrsus/index.html:727](thyrsus/index.html:727)

1. 결함 요약: `warn`에 “예/아니오/고개젓기(무응답)”라고 적혀 있다.
2. 재현 조건: 정상 작동 중인 화가가 유효한 예/아니오 질문을 한다.
3. 기대 동작: 사회자는 진실한 예 또는 아니오를 제공해야 한다. 질문이 유효한 예/아니오 질문이 아니면 재질문을 요청해야지 무응답을 규칙상 제3의 답으로 사용하면 안 된다. 공식 능력 원문은 “you learn a truthful answer”다. [공식 roles.json](https://release.botc.app/resources/data/roles.json)
4. 제안 패치: “유효한 질문이면 반드시 진실한 예/아니오. 형식이 부적절하면 다시 질문하도록 안내”로 교체한다.

### 12. 구버전 활성 지명 저장본은 투표 시 예외가 날 수 있음

위치: [thyrsus/index.html:832](thyrsus/index.html:832), [thyrsus/index.html:1967](thyrsus/index.html:1967), [thyrsus/index.html:3080](thyrsus/index.html:3080)

1. 결함 요약: 마이그레이션이 최상위 `Object.assign`뿐이다. 구버전 진행 중 지명에 `deadVoters`가 없으면 사망자 투표 시 `n.deadVoters.includes(...)`에서 예외가 발생한다. 클라우드 복원도 동일하다.
2. 재현 조건: `noms` 내 활성 지명에 `deadVoters`가 없는 구 저장본을 로드한 뒤 사망자가 찬성/반대한다.
3. 기대 동작: 신규 필드가 누락된 저장본도 기본값을 보충해 정상 동작해야 한다.
4. 제안 패치: `migrateState(raw)`에서 플레이어와 지명 각각을 정규화한다. 최소한 `statuses`, `notes`, `deadVote`, `hands`, `votes`, `deadVoters`, `closed`, `stage`를 타입 검사 후 기본값으로 채운다.

### 13. 클라우드 문서가 승리 확인·게임 종료 오버레이를 비우지 않음

위치: [thyrsus/index.html:3037](thyrsus/index.html:3037), [thyrsus/index.html:3040](thyrsus/index.html:3040)

1. 결함 요약: `cloudBuildDoc()`는 탭·wizard·pmodal만 정리한다. `#winask`와 `#gameover`의 동적 `innerHTML` 및 표시 상태는 복제본에 남는다.
2. 재현 조건: 승리 확인창 또는 게임 종료 화면이 열린 상태에서 클라우드 저장한다.
3. 기대 동작: 발행 문서는 정적 셸과 `cloudstate`만 포함하고 모든 일시적 오버레이는 숨김·비움 상태여야 한다.
4. 제안 패치: 동적 루트 allowlist 대신 `#wizard,#pmodal,#winask,#gameover`를 모두 `hidden=true; innerHTML=''`로 정규화하고, 저장 결과 문서에 열린 오버레이가 없는지 계약 테스트를 추가한다.

참고로 플레이어 이름과 메모의 일반 렌더링은 대부분 `esc()`를 통과했습니다. 가장 직접적인 XSS 경로는 검증되지 않은 커스텀 `id`와 저장·복원된 내부 ID가 인라인 이벤트 속성에 들어가는 부분입니다. 또한 공식 밤 순서 기준으로 TB의 배열과 BMR/SV의 그 외 밤 배열에서는 추가 순서 불일치를 발견하지 못했습니다.

---

# 수정 현황 (2026-09-01, 맥미니)

## 배포 전 수정 완료 — 종합 Critical 6건 (A~F)

| 코드 | 결함 | 수정 내용 |
|------|------|-----------|
| A | 승리 차단이 `null` → `_orig()`가 "선한 팀 승리" 오선언 | `evalWinEvent`가 `{kind:'continue', why}` 를 반환하도록 변경. `isWinRes()`/`announceContinue()` 신설, 호출부 4곳 모두 분기. 주모자 연장전은 `S.mastermindDay` 로 영속화하고 **연장된 낮의 처형 결과(악 처형=선 승리 / 무처형·선 처형=악 승리)를 dayEnd 에서 실제 판정** |
| B | 푸카가 `doPoison()` 재사용 | `doPukkaPick()` 신설. 페이즈 만료 없는 독 부여 → 이전 희생자 사망·해독 순서, `S.pukkaVictimId` 영속화, 오작동 시 신규 중독·지연 사망 모두 보류. 위저드 first/other 를 신규 함수로 교체 |
| C | 탕녀 계승이 안내뿐이라 악마 없는 게임 진행 | `promoteScarletWoman()` 신설 — `killPlayer()` 안에서 `charId` 를 실제 전환. 다른 악마 생존 시(팡 구 점프) 미발동, 별 넘기기 경로는 `skipSuccession` 으로 중복 계승 차단, 오작동 탕녀는 계승 불발 안내 |
| D | 오작동 좀버얼도 첫 사망 무효화 | `killPlayer()` 의 좀버얼 분기에 `!isMalfunctioning(p)` 추가 |
| E | `doStepKill()` 이 군인·보호·선원 무시 | `deathBlockReason()` 공용 판정 신설 — `doImpKill`·`doStepKill` 양쪽이 동일 규칙 사용. 암살자만 관통 |
| F | 커스텀 캐릭터 `id` 저장형 XSS | 인라인 `onclick` 제거 → `data-delcustom` + 위임 리스너. `importScript()` 에 스키마·타입·길이 검증과 안전 id 재발급(`/^[A-Za-z0-9_-]{1,64}$/`) 추가 |

부수 변경: `blank()` 에 `pukkaVictimId`·`mastermindDay`·`executedTodayPid` 추가(구 저장본은 `Object.assign` 으로 기본값 보충), `executeNominee` 가 처형자 pid 기록.

## 검증
- `node --check`: HTML 내 스크립트 블록 19개 전부 통과
- 브라우저 시나리오 회귀 **28건 전부 통과** — A~F 타깃 테스트 21건 + 기존 기능 회귀 7건
  (전 탭 렌더, 3개 에디션 밤 순서, 지명→거수→찬반 투표, 별 넘기기 악마 유일성, 상태 직렬화 왕복, 차단 요소 없을 때의 정상 선 승리 경로)

## 미수정 — 후속 과제
1·2차 종합 High 이하 **22건**은 이번 배포에 포함하지 않았다. 우선순위 상위:
- 진영을 `charId` 에서 유도(이발사 교환·건달·팡 구 진영 오염) — `alignment` 필드 도입 필요
- 상태에 `sourcePid` 없음 → 출처 사망 시 중독·취함 잔존
- BMR·SV 첫날 밤 순서(1·2차 독립 동일 결론): BMR `하수인→미치광이→악마`, SV `철학자→하수인→악마`
- 낮에 부여한 보호가 쓸 밤 시작에 만료
- 어릿광대 첫 생존이 확인창 취소로 무산 가능(강제 능력)
- 좀버얼 첫 사망에서 `checkEndConditions()` 자체를 건너뜀
- 구버전 저장본 마이그레이션이 최상위 `Object.assign` 뿐(`deadVoters` 누락 시 예외)

---

# 3차 Codex 정밀 검증 — 맥스튜디오 (밤 진행 · 캐릭터 구현 전수)

## 실행 정보
- 실행 일시: 2026-09-01 (맥스튜디오, `codex exec --sandbox read-only -c model_reasoning_effort=xhigh`)
- 도구: OpenAI Codex CLI v0.150.1 · 모델 `gpt-5.6-sol` · reasoning effort **xhigh**
- 검토 대상 커밋: `34b385b` (PR #6 머지 = **1·2차 Critical 6건 수정 반영본**)
- 초점: 1·2차의 엔진 수준 결함이 아니라 **밤 순서 인덱스 단위 대조 · 캐릭터 72종 전수 · 위저드 씬 전수 · 상태 수명주기**
- 기수정 22건 + 백로그 16건을 재보고 금지로 명시 — 아래는 전부 신규

## 요약

**신규 결함 23건** (Critical 3 · High 9 · Medium 8 · Low 3).

### 밤 순서 대조 결론
- **TB 첫날·이후 배열 모두 공식과 완전 일치** (누락·여분·역전 0)
- **BMR 이후 밤 19단계, SV 이후 밤 19단계도 완전 일치**
- 불일치는 **BMR·SV 첫날 밤의 3자 배치뿐** — 이미 백로그인 건과 동일. 다만 `renderSheet()`가 첫날 배열을 무시하고 `minioninfo`·`demoninfo`를 강제 선두 배치하므로 **배열만 고쳐도 시트는 계속 틀린다**
- 캐릭터 72종의 `first`/`other` 플래그는 공식 `roles.json` 과 **전부 일치**

### Critical 3건 — ⚠ 2건은 이번 세션(A~F) 수정분의 결함
| # | 결함 | 비고 |
|---|------|------|
| 1 | 푸카 희생자의 독을 **사망 전에** 제거 + 그 사망 경로에 보호 판정 없음 | **A~F의 B 수정분 결함.** 공식은 "죽고 나서 건강해진다" — 독이 살아 있어야 어릿광대 1회 생존이 막히고 까마귀지기·현자가 거짓 정보를 받는다 |
| 2 | 처형과 사망을 혼동 — 선원·악마의 변호사·평화주의자 미확인, 찻집 여인 보호가 처형 자체를 취소해 `executedToday` 미기록(보르톡스 오판정), 장의사가 "처형됐지만 안 죽은" 대상을 봄 | 기존 결함 |
| 3 | `deathBlockReason()`이 **대상이 오작동이면 외부 보호까지 무효화** | **A~F의 E 수정분 결함.** 공식: 취하거나 중독된 대상에게 사용된 *다른 플레이어의* 능력은 정상 작동. 수도사는 악마로부터만, 여관 주인은 모든 밤 사망으로부터 보호 |

### High 9건
사망 트리거 역할이 밤 실행 큐에서 누락·반복 · 구마사제 판정이 악마 단계와 미연결 · 달의 자손 오작동 판정 시점·주체 · 팡 구 점프가 "죽였는가"가 아니라 "외지인 지목"으로 발동 · 꿈꾸는 자 WIZ 대상·토큰 계약 위반 · 세레노버스가 사망자·외지인 광기 선택 불가 · 이발사 안내가 악마 자신의 스왑 금지 · 백치천재의 보르톡스 지침이 정반대 · 임시 취함을 영구 상태로만 표현

### Medium 8 / Low 3
오작동 정보 "반드시 거짓" 전역 오안내 · 다수 `pick-player`가 공식상 가능한 사망자 숨김 · 샤발로스·포 중복 선택 · 수학자 범위 과대 집계 · 도박사 경고에 없는 등록 재량 · 캐릭터 변경 시 타 능력 상태 일괄 삭제 · 밤 순서 미리보기가 에디션 무시하고 TB 표시 · 철학자·재봉사·사랑꾼 선택 검증 불완전 / 음유시인 여행자 예외 누락 · 중독된 암살자 소진을 재량으로 안내 · 시트의 이후 밤 행이 첫날 가이드 표시

---

## Codex 원문 출력 (verbatim, 3차)

읽기 전용으로 전수 검증했다. 파일은 수정하지 않았다.

결론부터 말하면 신규 결함은 **Critical 3건, High 9건, Medium 8건, Low 3건**이다. 이미 완료·백로그로 명시된 항목은 제외했다. 기준 데이터는 TPI 공식 [`nightsheet.json`](https://release.botc.app/resources/data/nightsheet.json), [`roles.json`](https://release.botc.app/resources/data/roles.json), [공식 위키](https://wiki.bloodontheclocktower.com/)다.

## A. 밤 순서 전수 대조

황혼·새벽은 배열 밖에서 렌더러가 삽입하므로 역할 인덱스에서는 제외했다.

### Trouble Brewing

| 밤 | 공식 순서 | 현재 배열 | 판정 |
|---|---|---|---|
| 첫날 | 1 `minioninfo` → 2 `demoninfo` → 3 `poisoner` → 4 `washerwoman` → 5 `librarian` → 6 `investigator` → 7 `chef` → 8 `empath` → 9 `fortuneteller` → 10 `butler` → 11 `spy` | 동일 | 누락·여분·역전 없음 |
| 이후 | 1 `poisoner` → 2 `monk` → 3 `scarletwoman` → 4 `imp` → 5 `ravenkeeper` → 6 `empath` → 7 `fortuneteller` → 8 `undertaker` → 9 `butler` → 10 `spy` | 동일 | 누락·여분·역전 없음 |

현재 배열: [thyrsus/index.html:554](thyrsus/index.html:554)

### Bad Moon Rising

| 밤 | 공식 순서 | 현재 배열 | 판정 |
|---|---|---|---|
| 첫날 | 1 `minioninfo` → 2 `lunatic` → 3 `demoninfo` → 4 `sailor` → 5 `courtier` → 6 `godfather` → 7 `devilsadvocate` → 8 `pukka` → 9 `grandmother` → 10 `chambermaid` | 1 `minioninfo` → 2 `demoninfo` → 3 `lunatic` → 나머지 동일 | `lunatic`/`demoninfo` 역전. 이미 백로그인 3자 배치 건 |
| 이후 | 1 `sailor` → 2 `courtier` → 3 `innkeeper` → 4 `gambler` → 5 `devilsadvocate` → 6 `lunatic` → 7 `exorcist` → 8 `zombuul` → 9 `pukka` → 10 `shabaloth` → 11 `po` → 12 `assassin` → 13 `godfather` → 14 `gossip` → 15 `professor` → 16 `tinker` → 17 `moonchild` → 18 `grandmother` → 19 `chambermaid` | 동일 | 누락·여분·역전 없음 |

현재 배열: [thyrsus/index.html:802](thyrsus/index.html:802)

### Sects & Violets

| 밤 | 공식 순서 | 현재 배열 | 판정 |
|---|---|---|---|
| 첫날 | 1 `philosopher` → 2 `minioninfo` → 3 `demoninfo` → 4 `snakecharmer` → 5 `eviltwin` → 6 `witch` → 7 `cerenovus` → 8 `clockmaker` → 9 `dreamer` → 10 `seamstress` → 11 `mathematician` | 1 `minioninfo` → 2 `demoninfo` → 3 `philosopher` → 나머지 동일 | `philosopher`가 두 정보 단계 뒤로 이동. 이미 백로그인 3자 배치 건 |
| 이후 | 1 `philosopher` → 2 `snakecharmer` → 3 `witch` → 4 `cerenovus` → 5 `pithag` → 6 `fanggu` → 7 `nodashii` → 8 `vortox` → 9 `vigormortis` → 10 `barber` → 11 `sweetheart` → 12 `sage` → 13 `dreamer` → 14 `flowergirl` → 15 `towncrier` → 16 `oracle` → 17 `seamstress` → 18 `juggler` → 19 `mathematician` | 동일 | 누락·여분·역전 없음 |

현재 배열: [thyrsus/index.html:805](thyrsus/index.html:805)

`renderSheet()`가 첫날 배열을 무시하고 `minioninfo`·`demoninfo`를 강제로 선두 배치한다([thyrsus/index.html:1292](thyrsus/index.html:1292)). 따라서 배열만 고쳐도 BMR/SV 시트는 계속 틀린다. 이 부분은 명시된 기존 백로그와 동일하므로 신규 finding으로 세지 않았다.

`nightSteps()`는 기본 배열을 재정렬하지 않으며, 커스텀 역할과 TB 주정뱅이 위장 단계만 위치 삽입한다([thyrsus/index.html:1412](thyrsus/index.html:1412)).

### `first` / `other` 플래그

공식 `roles.json`의 `firstNightReminder`/`otherNightReminder` 존재 여부와 **72종 전부 일치**했다.

| 에디션 | 첫날만 | 둘 다 | 이후만 | 밤 플래그 없음 |
|---|---|---|---|---|
| TB | 세탁부, 사서, 수사관, 요리사 | 초공감자, 점쟁이, 집사, 독살범, 첩자 | 장의사, 수도사, 까마귀지기(조건부), 탕녀(조건부), 임프 | 성결자, 처단자, 군인, 시장, 주정뱅이, 은둔자, 성자, 남작 |
| BMR | 없음 | 할머니, 선원, 객실 청소부, 궁정대신, 미치광이, 대부, 악마의 변호사, 푸카 | 구마사제, 여관 주인, 도박사, 험담꾼, 교수, 땜장이, 달의 자손, 암살자, 좀버얼, 샤발로스, 포 | 음유시인, 찻집 여인, 평화주의자, 어릿광대, 건달, 주모자 |
| SV | 시계공, 사악한 쌍둥이 | 꿈꾸는 자, 뱀 조련사, 수학자, 재봉사, 철학자, 마녀, 세레노버스 | 꽃팔이 소녀, 포고꾼, 예언자, 곡예사, 현자, 사랑꾼, 이발사, 마귀할멈, 팡 구, 노 다시, 보르톡스, 비고르모르티스 | 백치천재, 화가, 변종, 얼뜨기 |

조건부 플래그의 존재 자체도 맞다. 문제는 아래 High finding처럼 실행 큐가 그 조건을 제대로 추적하지 않는다는 점이다.

---

## Critical

### 1. 푸카 희생자의 독을 사망 전에 제거한다

[thyrsus/index.html:1702](thyrsus/index.html:1702), [thyrsus/index.html:1715](thyrsus/index.html:1715)

1. **결함:** 이전 희생자의 푸카 독을 먼저 제거한 뒤 `resolveNightDeath()`를 호출한다. 또한 이 경로는 여관 주인·찻집 여인 같은 밤 사망 보호를 전혀 확인하지 않는다.
2. **재현:** 푸카가 어릿광대를 중독시킨 뒤 다음 밤 새 대상을 문다. 현재는 어릿광대의 독이 먼저 풀려 1회 생존이 작동할 수 있다. 푸카가 현자·까마귀지기를 죽인 경우에도 건강한 상태로 사망 능력이 처리된다. 여관 주인 보호 대상도 직접 사망한다.
3. **기대:** 푸카 희생자는 **사망 순간까지 중독**되어 있어 어릿광대 능력이 작동하지 않고, 현자 등은 거짓 정보를 받을 수 있다. 보호되어 죽지 않은 경우에도 이후 건강해진다. [Pukka 공식 위키](https://wiki.bloodontheclocktower.com/Pukka)
4. **제안 패치:** 새 대상을 먼저 중독시키고, 이전 대상에게 공용 밤 사망 보호 판정을 적용한 뒤, 독을 유지한 상태로 사망·사망 능력을 전부 해결하고 마지막에 푸카 독만 제거한다. `pukkaVictimId`와 독 토큰을 별도 pending-effect 구조로 관리한다.

### 2. 처형과 사망을 혼동해 BMR 핵심 능력을 무시한다

[thyrsus/index.html:1937](thyrsus/index.html:1937), [thyrsus/index.html:2053](thyrsus/index.html:2053)

1. **결함:** 일반 처형과 성결자 처형 모두 `killPlayer()`를 바로 호출한다. 정상 선원, 악마의 변호사 보호, 평화주의자 재량을 확인하지 않는다. 찻집 여인 보호는 반대로 “처형 자체”를 취소하고 `executedToday`도 기록하지 않는다. 어릿광대처럼 처형됐지만 살지 않은 대상은 장의사에게 잘못 안내된다.
2. **재현:** 정상 선원을 처형하면 죽는다. 악마의 변호사가 보호한 대상을 처형해도 죽는다. 찻집 여인 이웃 처형에서 취소를 선택하면 보르톡스 기준으로 “오늘 처형 없음”이 된다. 어릿광대가 처형을 버텨도 장의사에게 해당 토큰을 보여주라고 안내한다.
3. **기대:** 처형은 사망과 별개다. 보호되어 살아도 그날 처형은 소모되고 보르톡스 조건을 만족한다. 장의사는 **처형으로 실제 죽은** 캐릭터만 본다. [States](https://wiki.bloodontheclocktower.com/States), [Undertaker](https://wiki.bloodontheclocktower.com/Undertaker), [Pacifist](https://wiki.bloodontheclocktower.com/Pacifist), [Sailor](https://wiki.bloodontheclocktower.com/Sailor)
4. **제안 패치:** `resolveExecution()`을 만들고 `executionOccurred`, `diedByExecutionPid`를 분리한다. 선원·악마의 변호사·찻집 여인·평화주의자·어릿광대 판정을 한 곳에서 처리하며, 성결자 경로도 동일 함수를 사용한다. 장의사는 `diedByExecutionPid`만 참조해야 한다.

### 3. 대상의 중독·취함이 외부 보호까지 무효화한다

[thyrsus/index.html:873](thyrsus/index.html:873), [thyrsus/index.html:1775](thyrsus/index.html:1775)

1. **결함:** `deathBlockReason()`이 대상이 오작동 상태면 즉시 `null`을 반환한다. 따라서 수도사·여관 주인이 준 외부 보호도 함께 사라진다. 반대로 `doStepKill()`은 살해 출처를 구분하지 않아 군인·수도사 보호가 험담꾼·대부·달의 자손 같은 비악마 사망도 막을 수 있다.
2. **재현:** 여관 주인이 두 명을 보호하고 그중 한 명을 취하게 한 뒤 악마가 그 취한 플레이어를 공격하면 현재 사망한다. 교차 스크립트에서는 수도사 보호 대상이 중독돼도 같은 문제가 난다.
3. **기대:** 취하거나 중독된 **대상에게 사용된 다른 플레이어의 능력은 정상 작동**한다. 수도사는 악마로부터만, 여관 주인은 모든 밤 사망으로부터 보호한다. [States](https://wiki.bloodontheclocktower.com/States), [Monk](https://wiki.bloodontheclocktower.com/Monk), [Innkeeper](https://wiki.bloodontheclocktower.com/Innkeeper)
4. **제안 패치:** 외부 보호와 대상 자신의 면역을 분리한다. `deathBlockReason(target, {sourceType, atNight, ignoresProtection})` 형태로 살해 출처를 전달하고, 대상 오작동은 군인·선원 같은 자기 능력에만 적용한다.

---

## High

### 4. 사망 트리거 역할이 전체 밤 실행에서 누락되거나 반복된다

[thyrsus/index.html:1460](thyrsus/index.html:1460), [thyrsus/index.html:2838](thyrsus/index.html:2838), [thyrsus/index.html:4011](thyrsus/index.html:4011)

1. **결함:** 사망한 까마귀지기는 “오늘 밤 사망” 여부와 무관하게 이후 매일 실행 가능하다. 반면 사망한 현자·이발사·사랑꾼·달의 자손은 일반 사망 필터로 전체 밤 큐에서 빠진다. `startWiz()`도 살아있는 holder만 찾는다.
2. **재현:** 2일 밤 까마귀지기가 죽고 발동한 뒤 3일 밤 전체 진행을 시작하면 다시 큐에 들어간다. 같은 밤 악마에게 죽은 현자는 큐에서 제외된다.
3. **기대:** 까마귀지기와 현자는 사망 즉시/해당 밤 한 번만, 이발사·사랑꾼은 오늘 죽었을 때 한 번만 처리되어야 한다. [Abilities](https://wiki.bloodontheclocktower.com/Abilities), [Ravenkeeper](https://wiki.bloodontheclocktower.com/Ravenkeeper), [Barber](https://wiki.bloodontheclocktower.com/Barber)
4. **제안 패치:** 사망 이벤트에 `phase`, `night`, `cause`, `resolvedTriggers`를 기록한다. `stepSkipReason()`은 현재 생존 여부가 아니라 미해결 이벤트를 검사하고, 위저드 holder도 해당 이벤트의 사망자를 사용한다.

### 5. 구마사제 판정이 실제 악마 단계에 연결되지 않는다

[thyrsus/index.html:1664](thyrsus/index.html:1664), [thyrsus/index.html:3245](thyrsus/index.html:3245)

1. **결함:** `doExorcist()`는 토스트만 띄우고 악마 단계 차단 상태를 기록하지 않는다. 전체 밤 큐는 이후 악마 위저드를 정상 실행한다. 푸카를 구마한 경우 “새 중독은 없음, 이전 독 피해는 사망”이어야 하지만 현재 두 효과가 `doPukkaPick()` 하나에 결합돼 있다.
2. **재현:** 구마사제가 실제 악마를 골라 판정한 뒤 전체 진행을 계속하면 해당 악마 WIZ가 열린다. 푸카 WIZ를 닫으면 이전 희생자도 죽지 않고, 실행하면 새 희생자까지 중독된다.
3. **기대:** 선택된 악마는 깨어나 자신의 능력을 사용하지 않는다. 단, 푸카의 이전 공격으로 인한 사망은 계속 해결된다. [Exorcist](https://wiki.bloodontheclocktower.com/Exorcist), [Pukka](https://wiki.bloodontheclocktower.com/Pukka)
4. **제안 패치:** `demonBlockedNight`를 저장해 큐에서 악마의 선택·공격 장면만 건너뛴다. 푸카는 `resolvePendingPukkaDeath()`와 `chooseNewPukkaVictim()`을 분리한다.

### 6. 달의 자손 오작동 판정 시점과 선택 주체가 틀리다

[thyrsus/index.html:644](thyrsus/index.html:644), [thyrsus/index.html:3316](thyrsus/index.html:3316)

1. **결함:** “중독 상태로 죽었으면 발동 없음”이라고 하지만 실제 판정 시점은 대상이 죽는 **그날 밤**이다. WIZ도 사회자가 선택하는 장면(`who:'st'`)으로 표시한다.
2. **재현:** 달의 자손이 중독 상태로 낮에 죽어 대상을 지목한 뒤 밤에 건강해지면 현재 불발 안내지만 공식상 대상은 죽는다. 반대 상황도 역전된다.
3. **기대:** 달의 자손이 사망 사실을 알게 된 직후 직접 생존자 한 명을 공개 선택한다. 대상의 선악은 선택 시점, 달의 자손의 건강은 밤 사망 해결 시점 기준이다. [Moonchild](https://wiki.bloodontheclocktower.com/Moonchild)
4. **제안 패치:** `moonchildChoice={pid,targetPid,alignmentAtChoice}`를 저장하고 밤에 source의 현재 오작동 상태를 검사한다. WIZ 선택 주체는 `player`로 바꾼다.

### 7. 팡 구 점프가 “죽였는가”가 아니라 “외지인을 지목했는가”로 발동한다

[thyrsus/index.html:778](thyrsus/index.html:778), [thyrsus/index.html:3463](thyrsus/index.html:3463)

1. **결함:** 외지인 지목 즉시 일반 사망 판정을 건너뛰고 점프하라고 안내한다.
2. **재현:** 여관 주인 등으로 보호된 외지인을 팡 구가 공격하면 현재 새 팡 구가 생기고 기존 팡 구가 죽는다.
3. **기대:** 첫 외지인을 **팡 구가 죽였을 때만** 점프한다. 외지인이 죽지 않았다면 점프도 없다. [Fang Gu](https://wiki.bloodontheclocktower.com/Fang_Gu)
4. **제안 패치:** 먼저 Demon 사망 판정을 수행해 실제 `alive→dead` 전이가 가능한지 확인하고, 성공했을 때 그 사망을 점프로 치환한다.

### 8. 꿈꾸는 자 WIZ가 대상·토큰 계약을 모두 위반할 수 있다

[thyrsus/index.html:692](thyrsus/index.html:692), [thyrsus/index.html:3419](thyrsus/index.html:3419)

1. **결함:** 죽은 플레이어를 선택할 수 없고 여행자를 선택할 수 있다. 선·악 토큰 풀이 둘 다 `any`라서 같은 진영 둘을 고르거나 실제 캐릭터가 없는 쌍을 보여줄 수 있다. 능력 요약도 여행자 제외를 누락했다.
2. **재현:** 죽은 플레이어는 버튼에 나타나지 않는다. `goodTok`에서 악마, `evilTok`에서 주민을 선택할 수 있다.
3. **기대:** 자신과 여행자를 제외한 살아있거나 죽은 플레이어를 고르고, 선한 캐릭터 하나와 악한 캐릭터 하나를 보여주며 둘 중 하나는 대상의 실제 캐릭터여야 한다. [Dreamer](https://wiki.bloodontheclocktower.com/Dreamer)
4. **제안 패치:** `any-not-self-not-traveller`, `good-characters`, `evil-characters` 필터를 추가하고 건강한 경우 실제 토큰 하나를 자동 고정한다. 보르톡스/오작동 때만 올바른 거짓 계약을 별도로 계산한다.

### 9. 세레노버스가 죽은 대상과 외지인 광기를 선택할 수 없다

[thyrsus/index.html:3400](thyrsus/index.html:3400)

1. **결함:** 대상 필터가 `alive`, 캐릭터 풀이 `townsfolk`뿐이다.
2. **재현:** 죽은 플레이어를 광기 대상으로 고를 수 없고 변종·사랑꾼·이발사·얼뜨기 광기를 줄 수 없다.
3. **기대:** 아무 플레이어와 아무 선한 캐릭터, 즉 주민 또는 외지인을 선택할 수 있다. 죽은 대상도 광기 위반으로 처형될 수 있다. [Cerenovus](https://wiki.bloodontheclocktower.com/Cerenovus)
4. **제안 패치:** 대상은 `any`, 캐릭터 풀은 `good-characters`로 변경한다.

### 10. 이발사 안내가 악마 자신의 스왑을 금지한다

[thyrsus/index.html:749](thyrsus/index.html:749), [thyrsus/index.html:3487](thyrsus/index.html:3487)

1. **결함:** “악마 자신은 스왑 불가”라고 명시한다.
2. **재현:** 보르톡스가 자신과 마녀의 캐릭터를 교환하려 할 때 도구가 불법이라고 안내한다.
3. **기대:** 선택하는 악마는 자신을 고를 수 있다. 금지되는 것은 **다른 악마 플레이어**다. [Barber](https://wiki.bloodontheclocktower.com/Barber)
4. **제안 패치:** 문구를 “악마 자신은 가능, 다른 악마는 불가”로 수정하고, 둘 이상의 악마가 있을 때만 다른 악마를 선택 목록에서 제외한다.

### 11. 백치천재의 보르톡스 지침이 정반대다

[thyrsus/index.html:715](thyrsus/index.html:715)

1. **결함:** 보르톡스 게임에서도 “참/거짓 구조 유지”라고 안내한다.
2. **재현:** 보르톡스가 살아 있는 날 백치천재에게 참 1개·거짓 1개를 제공한다.
3. **기대:** 보르톡스 아래 주민 정보는 전부 거짓이므로 백치천재의 두 문장 모두 거짓이어야 한다. [Vortox](https://wiki.bloodontheclocktower.com/Vortox), [Savant](https://wiki.bloodontheclocktower.com/Savant)
4. **제안 패치:** 보르톡스 분기를 별도로 두어 “두 정보 모두 거짓”을 강제한다. 중독·취함만 두 참/두 거짓/통상 구조 모두 허용한다.

### 12. 임시 취함을 전부 영구 상태로만 표현한다

[thyrsus/index.html:560](thyrsus/index.html:560), [thyrsus/index.html:3191](thyrsus/index.html:3191), [thyrsus/index.html:3933](thyrsus/index.html:3933)

1. **결함:** `drunkS`는 항상 `expiresAt:null`인 영구 취함이다. 선원·여관 주인·건달·음유시인·궁정대신의 임시 취함에 동일 버튼을 사용하면 자동 해제되지 않는다.
2. **재현:** 여관 주인 WIZ 안내에 따라 대상에게 취함 버튼을 누르고 다음 황혼으로 진행해도 상태가 남는다.
3. **기대:** 선원·여관 주인·건달·음유시인은 다음 황혼, 궁정대신은 3일 밤+3일 낮 뒤 만료된다. 주정뱅이·사랑꾼·뱀 조련사 독은 영구다. [Innkeeper](https://wiki.bloodontheclocktower.com/Innkeeper), [`roles.json`](https://release.botc.app/resources/data/roles.json)
4. **제안 패치:** `drunkS`에 `source`별 만료 정책을 지원한다. 궁정대신은 선택한 밤 `n+3`, 다음 황혼까지 역할은 `night n+1`, 영구 취함은 `null`로 저장한다.

---

## Medium

### 13. 오작동 정보가 “반드시 거짓”이라고 전역 안내된다

[thyrsus/index.html:488](thyrsus/index.html:488), [thyrsus/index.html:1570](thyrsus/index.html:1570), [thyrsus/index.html:2858](thyrsus/index.html:2858), [thyrsus/index.html:3350](thyrsus/index.html:3350), [thyrsus/index.html:3503](thyrsus/index.html:3503)

1. **결함:** 주정뱅이와 중독·취함 정보 역할에게 반드시 거짓을 주라고 한다. 꽃팔이 소녀, 예언자, 재봉사 제안도 중독과 보르톡스를 같은 규칙으로 묶는다.
2. **재현:** 중독된 꽃팔이 소녀의 실제 답이 “예”인 상황에서 “예”를 줄 수 없다고 안내한다.
3. **기대:** 중독·취함은 정보가 임의이므로 참도 거짓도 가능하다. 반드시 거짓인 것은 살아있는 보르톡스가 영향을 주는 주민 정보뿐이다. [States](https://wiki.bloodontheclocktower.com/States), [Poisoner](https://wiki.bloodontheclocktower.com/Poisoner), [Vortox](https://wiki.bloodontheclocktower.com/Vortox)
4. **제안 패치:** 배너를 “참 또는 거짓 가능”으로 바꾸고, 보르톡스 전용 `mustBeFalse` 표시를 분리한다. 세탁부·사서·수사관의 풀도 오작동·등록 시 실제 인플레이 풀로 제한하지 않는다.

### 14. 다수 `pick-player`가 공식상 가능한 사망자를 숨긴다

[thyrsus/index.html:3007](thyrsus/index.html:3007), [thyrsus/index.html:3061](thyrsus/index.html:3061), [thyrsus/index.html:3210](thyrsus/index.html:3210), [thyrsus/index.html:3245](thyrsus/index.html:3245), [thyrsus/index.html:3252](thyrsus/index.html:3252), [thyrsus/index.html:3388](thyrsus/index.html:3388), [thyrsus/index.html:3457](thyrsus/index.html:3457)

1. **결함:** 독살범, 집사, 수도사, 여관 주인, 도박사, 구마사제, 좀버얼, 푸카, 샤발로스, 포, 암살자, 대부, 마녀, 마귀할멈, 사랑꾼 및 대부분 악마 WIZ가 `alive`/`alive-not-self`를 사용한다.
2. **재현:** 도박사가 죽은 플레이어를 추측하거나 구마사제가 죽은 척한 좀버얼을 선택하려 해도 목록에 없다. 집사는 죽은 주인을 고를 수 없다.
3. **기대:** 능력에 “alive”가 명시되지 않은 `choose a player`는 사망자도 가능하다. 선원·객실 청소부·뱀 조련사·악마의 변호사·달의 자손만 명시된 생존 제한을 유지해야 한다. [Abilities](https://wiki.bloodontheclocktower.com/Abilities), [Gambler](https://wiki.bloodontheclocktower.com/Gambler), [Exorcist](https://wiki.bloodontheclocktower.com/Exorcist), [Butler](https://wiki.bloodontheclocktower.com/Butler)
4. **제안 패치:** 해당 장면을 `any`로 바꾸고 자기 제외가 필요한 집사·수도사는 `any-not-self`를 추가한다.

### 15. 샤발로스·포가 같은 플레이어를 중복 선택할 수 있다

[thyrsus/index.html:3270](thyrsus/index.html:3270), [thyrsus/index.html:3278](thyrsus/index.html:3278)

1. **결함:** 샤발로스는 두 개의 독립 `storeAs`를 써 같은 대상을 두 번 선택할 수 있다. 포는 3명 선택 장면 없이 “이전으로 돌아가 세 번 반복”하게 한다.
2. **재현:** 샤발로스 첫 공격이 보호로 막힌 뒤 같은 플레이어를 두 번째 희생자로 다시 선택할 수 있다. 충전 포도 같은 대상 반복을 막지 않는다.
3. **기대:** “2 players”, “3 players”는 서로 다른 플레이어를 한 번에 선택한다. [`roles.json`](https://release.botc.app/resources/data/roles.json)
4. **제안 패치:** 샤발로스는 `n:2` 단일 장면, 충전 포는 `n:3` 단일 장면으로 만들고 각 대상에 순차 판정을 실행한다.

### 16. 수학자 능력 범위가 과대 집계된다

[thyrsus/index.html:700](thyrsus/index.html:700), [thyrsus/index.html:3448](thyrsus/index.html:3448)

1. **결함:** “오늘 밤+낮 오작동한 플레이어”라고만 해 `since dawn`, `다른 캐릭터 능력 때문에` 조건을 누락한다. 수학자 자신의 오작동 및 중독됐지만 우연히 정상 결과를 받은 역할도 셀 수 있는 문구다.
2. **재현:** 중독된 초공감자가 우연히 정확한 숫자를 받은 경우 현재 안내대로면 카운트할 수 있다.
3. **기대:** 새벽 이후 다른 캐릭터 능력 때문에 비정상 작동한 능력만 센다. 수학자 자신과 정상 결과는 제외한다. [Mathematician](https://wiki.bloodontheclocktower.com/Mathematician)
4. **제안 패치:** 능력·가이드 문구를 공식 조건으로 교체하고 `abnormalSinceDawn` 이벤트를 역할별 1회 기록한다.

### 17. 도박사 경고에 존재하지 않는 등록 재량과 불가능한 중독 사망이 적혀 있다

[thyrsus/index.html:597](thyrsus/index.html:597)

1. **결함:** 미치광이·건달의 “등록 재량”이 정답 판정에 영향을 준다고 하며, 중독된 도박사가 정답이어도 죽을 수 있다고 한다.
2. **재현:** 미치광이를 악마로 추측하거나 건달을 다른 역할로 추측해 정답 처리할 수 있다고 오해할 수 있다.
3. **기대:** 도박사는 실제 캐릭터를 추측한다. 미치광이는 미치광이, 건달은 건달이다. 중독된 도박사는 능력이 없으므로 자신의 추측 때문에 죽지 않는다. [Gambler](https://wiki.bloodontheclocktower.com/Gambler), [States](https://wiki.bloodontheclocktower.com/States)
4. **제안 패치:** 등록 관련 경고를 제거하고 “중독이면 정오답과 무관하게 도박사 능력으로 죽지 않지만 사용 절차는 평소처럼 진행”으로 바꾼다.

### 18. 캐릭터 변경 시 다른 능력이 준 상태까지 일괄 삭제할 수 있다

[thyrsus/index.html:3628](thyrsus/index.html:3628), [thyrsus/index.html:3632](thyrsus/index.html:3632)

1. **결함:** “상태 토큰 정리 후 적용”이 대상의 모든 상태를 삭제한다.
2. **재현:** 중독된 플레이어를 마귀할멈이 다른 캐릭터로 바꿀 때 정리 버튼을 누르면 중독이 사라진다.
3. **기대:** 플레이어의 중독·취함 같은 상태는 캐릭터와 독립적이므로 캐릭터가 바뀌어도 유지된다. 다만 옛 캐릭터 능력이 만든 지속 효과는 별도로 끝날 수 있다. [States](https://wiki.bloodontheclocktower.com/States), [Abilities](https://wiki.bloodontheclocktower.com/Abilities)
4. **제안 패치:** 일괄 삭제 버튼을 제거하고, `sourceAbilityId`가 옛 캐릭터인 지속 효과만 선택적으로 해제한다.

### 19. 밤 순서 미리보기가 선택 에디션과 무관하게 TB를 표시한다

[thyrsus/index.html:1526](thyrsus/index.html:1526)

1. **결함:** `previewNightOrders()`가 항상 `FIRST_NIGHT_ORDER`/`OTHER_NIGHT_ORDER`, 즉 TB 상수를 사용한다.
2. **재현:** BMR 또는 SV를 선택한 뒤 낮/준비 화면에서 밤 순서 미리보기를 열면 독살범·세탁부 등 TB 순서가 나온다.
3. **기대:** 선택한 에디션의 공식 순서를 보여줘야 한다. [`nightsheet.json`](https://release.botc.app/resources/data/nightsheet.json)
4. **제안 패치:** `editionOf().first`와 `.other`를 사용한다.

### 20. 철학자·재봉사·사랑꾼 WIZ의 선택 검증이 불완전하다

[thyrsus/index.html:3360](thyrsus/index.html:3360), [thyrsus/index.html:3435](thyrsus/index.html:3435), [thyrsus/index.html:3492](thyrsus/index.html:3492)

1. **결함:** 철학자는 악한 캐릭터도 고를 수 있다. 재봉사는 자신을 두 대상 중 하나로 선택할 수 있다. 사랑꾼은 죽은 플레이어를 취하게 할 수 없게 제한된다.
2. **재현:** 철학자 WIZ에서 보르톡스를 선택하거나 재봉사 본인을 선택할 수 있다.
3. **기대:** 철학자는 선한 캐릭터만, 재봉사는 자신 외 두 플레이어, 사랑꾼은 아무 플레이어를 선택한다. [`roles.json`](https://release.botc.app/resources/data/roles.json), [Sweetheart](https://wiki.bloodontheclocktower.com/Sweetheart)
4. **제안 패치:** `good-characters`, `any-not-self`, `any` 풀을 각각 사용한다.

---

## Low

### 21. 음유시인 능력에서 여행자 예외가 빠졌다

[thyrsus/index.html:614](thyrsus/index.html:614)

1. **결함:** 하수인이 처형돼 죽으면 “다른 모든 플레이어”가 취한다고 적었다.
2. **재현:** 여행자가 있는 게임에서 여행자까지 취한 것으로 처리할 수 있다.
3. **기대:** 음유시인 자신과 여행자를 제외한 모든 플레이어가 다음 황혼까지 취한다. [Minstrel](https://wiki.bloodontheclocktower.com/Minstrel)
4. **제안 패치:** 능력·경고에 “여행자 제외”를 명시한다.

### 22. 중독된 암살자의 1회 능력 소진을 재량이라고 안내한다

[thyrsus/index.html:660](thyrsus/index.html:660)

1. **결함:** “소진은 재량”과 “공식: 소진됨”이 한 문장에 공존한다.
2. **재현:** 중독 암살자가 발동을 시도한 뒤 사회자가 미소진으로 남길 수 있다.
3. **기대:** 중독·취함 상태에서 1회성 능력을 시도하면 효과는 없지만 능력은 반드시 소진된다. [States](https://wiki.bloodontheclocktower.com/States)
4. **제안 패치:** “살해는 불발하지만 능력은 반드시 소진”으로 단정하고 WIZ 완료 시 `spent`를 기록한다.

### 23. 시트의 이후 밤 행이 첫날 가이드를 표시한다

[thyrsus/index.html:1262](thyrsus/index.html:1262)

1. **결함:** `nightRow()`가 첫날/이후 밤 구분을 받지 않고, `first:true`인 역할은 이후 밤 시트에서도 `guideFirst`를 선택한다.
2. **재현:** 독살범·집사·초공감자 등 양쪽 밤 역할의 이후 밤 탭을 열면 첫날 진행 문구 첫 줄이 표시된다.
3. **기대:** 이후 밤 탭에서는 `guideOther`가 우선되어야 한다.
4. **제안 패치:** `nightRow(ed,id,{firstNight})`처럼 명시적 인자를 전달해 가이드를 선택한다.

---

## 상태 수명주기 전수 결과

| 상태 | 현재 `expiresAt` | 판정 |
|---|---|---|
| 독살범 중독 | 다음 `night n+1` 시작 | 정확 |
| 푸카 중독 | `null`, 다음 지목 때 수동 해제 | 사망 전 제거 문제로 Critical 1 |
| 수도사/여관 주인 보호 | 다음 `day n` 시작 | 밤 부여 기준 기간은 정확. 대상 오작동 처리만 Critical 3 |
| 집사 주인 | 다음 `night n+1` | 정확 |
| 마녀 저주 | 다음 `night n+1` | 정확 |
| 세레노버스 광기 | 다음 `night n+1` | 정확 |
| 소진 | 영구 | 정확 |
| 좀버얼 죽은 척 | 두 번째 사망 전까지 | 정확 |
| 주정뱅이·사랑꾼 등 영구 취함 | 영구 | 정확 |
| 선원·여관 주인·건달·음유시인·궁정대신 임시 취함 | 영구로만 입력 가능 | High 12 |

정상 UI 경로에서는 독 중복 방지와 단일 주인·저주·광기 갱신이 작동해 추가 이중 부여는 재현되지 않았다. `wiz.vars`는 매 시작 시 새 객체로 만들고 씬 임시값도 제거하므로 이전 WIZ 선택값 잔존이나 전역 선택값 오염도 재현되지 않았다.

## 72종 완전성 확인

`CHARACTERS`는 정확히 TB 22 + BMR 25 + SV 25 = 72종이다.

- 아이콘 ID, 한글명, 영문명 매핑: 72종 모두 불일치 없음.
- 셋업 보정값: 남작 `+2 Outsider`, 대부 `±1`, 팡 구 `+1`, 비고르모르티스 `-1` 모두 정확.
- 소환사·정치인은 72종 `CHARACTERS` 구성원이 아니므로 이번 72종 배열의 `setupNote` 검증 대상에는 없었다.
- 캐릭터 데이터 자체에서 결함이 확인된 항목은 주정뱅이, 장의사, 도박사, 음유시인, 암살자, 달의 자손, 수학자, 꿈꾸는 자, 백치천재, 팡 구, 이발사다.
- 나머지 61종의 `ability`·`guideFirst`·`guideOther`·`warn`·`remind`에서는 위 WIZ/공용 엔진 결함과 별개인 의미상 오류를 추가로 찾지 못했다.

---

## 3차 Critical 3건 수정 완료 (2026-09-01, 맥미니)

| # | 결함 | 수정 내용 |
|---|------|-----------|
| 1 | 푸카 희생자의 독을 사망 전에 제거 + 보호 미적용 | 순서를 **새 대상 중독 → 보호 판정 → (독 유지한 채) 사망 → 해독** 으로 교정. 보호로 살아남은 경우에도 해독은 수행. 이제 중독된 어릿광대는 1회 생존이 발동하지 않고, 까마귀지기·현자는 거짓 정보를 받는다 |
| 2 | 처형과 사망 혼동 | `resolveExecution()` 신설 — 일반 처형·성결자 발동이 공유. 보호로 살아남아도 `executedToday` 가 기록되어 보르톡스·시장 판정이 성립하고, 장의사는 신설 `S.executedDiedToday`(→ 밤 전환 시 `executedPrevDay`)로 **처형으로 실제 죽은** 캐릭터만 본다. 찻집 여인은 처형 자체가 아니라 사망만 막는다 |
| 3 | `deathBlockReason()` 이 대상 오작동 시 외부 보호까지 무효화 | 외부 보호와 자기 면역을 분리. 보호 토큰·찻집 여인은 **대상이 취하거나 중독돼도 정상 작동**(다른 플레이어의 능력이므로). 수도사 출처는 악마 살해에만, 여관 주인 등은 모든 밤 사망에 적용. 군인·선원 자기 면역만 오작동의 영향을 받고, 군인은 `sourceType==='demon'` 일 때만 면역 — `doStepKill` 이 살해 출처(악마/비악마)를 구분해 전달 |

부수: `blank()` 에 `executedDiedToday` 추가. `deathBlockReason(t,{sourceType,bypass})` 로 시그니처 변경(암살자=`bypass`).

### 검증
- `node --check` 스크립트 블록 19/19 통과
- 브라우저 시나리오 **33건 전부 통과** — 3차 타깃 19건 + 1·2차 회귀 14건
  (취한/중독 대상의 외부 보호 유지, 수도사 vs 여관 주인 적용 범위, 군인의 악마 한정 면역, 중독된 어릿광대의 1회 생존 불발, 보호된 푸카 희생자의 생존·해독, 선원 처형 시 처형 소모·장의사 미표시, 정상 처형의 장의사 이월, 주모자 연장전, 탕녀 계승, 좀버얼, 암살자 관통, XSS, 전 탭 렌더, 지명→거수→찬반→처형, 별 넘기기)

**High 이하 20건은 미수정** — 목록은 위 3차 원문 참조. 최우선은 사망 트리거 역할의 밤 실행 큐 누락·반복, 구마사제-악마 단계 미연결, 팡 구 점프 발동 조건, `renderSheet()` 의 첫날 정보 단계 강제 선두 배치(BMR/SV 밤 순서 배열만 고쳐서는 시트가 계속 틀림).

---

## 4차 수정 (2026-09-02, 맥미니) — High·Medium 백로그 구조 수정 15건

| 영역 | 수정 |
|------|------|
| 밤 순서 | BMR 첫날 `하수인→미치광이→악마`, SV 첫날 `철학자→하수인→악마` (공식 nightsheet). `renderSheet()` 의 정보 단계 강제 선두 배치 제거 — 배열 순서 그대로 렌더 |
| 시트 에디션 | `sheetEd` 초기값을 `S.edition` 으로, 밤 전환 시 자동 동기화 (3차 #19) |
| 진영 | `p.alignment` 독립 필드 + `isEvil()` 우선 참조. `doSwapChars()`(이발사: 캐릭터만 교환·진영 보존), `doSnakeSwap()`(뱀 조련사: 캐릭터+진영 교환·새 조련사 영구 중독) 신설, WIZ 에 판정 연결. 이발사 "악마 자신 교환 가능·다른 악마만 불가"로 문구 교정 (3차 #10, 2차 백로그 alignment) |
| 사망 트리거 | `p.diedAt={kind,n,cause}` 기록. `DEATH_TRIGGER_STEPS`(까마귀지기·현자=그 밤, 이발사·사랑꾼·달의 자손=오늘) 로 `stepSkipReason()` 재작성 — 죽은 까마귀지기가 매일 재진입하던 것, 죽은 현자·이발사가 큐에서 빠지던 것 모두 해소 (3차 #4) |
| 구마사제 | `S.demonBlockedNight/Pid` 저장, 밤 큐가 해당 악마 단계를 실제로 스킵 (3차 #5) |
| 팡 구 | `doFangGuAttack()` 신설 — **실제로 죽였을 때만** 점프(보호 시 점프 없음), `S.fangGuJumped` 게임당 1회, 새 팡 구 `alignment='evil'` (3차 #7) |
| 어릿광대 | 확인창 제거 — 강제 능력이므로 자동 발동 (3차 #5-계열) |
| 좀버얼 | 죽은 척 시에도 `checkEndConditions()` 실행. 겉보기 생존 2인 + 죽은 척 좀버얼 = 자동 악 승리 대신 `continue(zombuul)` (2차 #8) |
| 보호 만료 | 낮 부여 보호 `{kind:'day', n+1}` — 쓸 밤 시작에 만료되던 문제 (2차 #7, 두 지점 모두) |
| 달의 자손 | 선택 주체 `player` 로, 오작동 판정 시점=밤 사망 해결 시점으로 안내 교정 (3차 #6) |
| 꿈꾸는 자 | 대상 `not-self-not-traveler`(사망자 가능), 토큰 풀 `good-characters`/`evil-characters` 분리 (3차 #8) |
| 세레노버스 | 대상 `any`(사망자 포함), 풀 `good-characters`(주민+외지인) (3차 #9) |
| 상태 보존 | `setChar()` 가 주정뱅이 출처 취함만 제거 — 사랑꾼·건달 등 외부 취함 보존 (3차 #18) |
| 중복 지목 | 샤발로스·포 두 희생자 상이 강제(사망자 재지목 차단) (3차 #15) |
| 마이그레이션 | `migrateState()` — 플레이어·지명 단위 기본값 보충(`deadVoters` 등), localStorage·클라우드 복원 공용 (2차 #12) |
| 클라우드 | `#winask`·`#gameover`·`#wizard`·`#pmodal` 오버레이 전부 숨김+비움 (2차 #13) |

검증: node --check 19/19 · 브라우저 시나리오 44건 통과(신규 37 + 회귀 7 계열 통합 18) — 이발사 진영 보존, 팡 구 3분기, 구마 봉인 큐 스킵, 사망 트리거 6분기, 좀버얼 2인 예외, 낮 보호 만료 3단계, 마이그레이션 방어, 시트 순서(BMR·SV), 에디션 동기화, setChar 보존, 전 에디션×전 탭×시트 3뷰 렌더.

---

## 공식 캐릭터 아이콘 도입 (2026-09-04)

### 정정
PR #20 본문에 "teeroz 아이콘은 제3자 저작물이라 복제하지 않았다"고 적었는데 **틀렸다**.
teeroz 가 쓰는 것은 The Pandemonium Institute 의 공식 캐릭터 아트이고, 공식 스크립트 툴
(`script.bloodontheclocktower.com`)이 그대로 배포한다. `clocktower.online`, `bra1n/townsquare`
등 커뮤니티 도구도 같은 자산을 쓴다. 그 잘못된 전제 위에서 손그림 SVG 세트를 만들었고,
이번에 공식 아트로 전면 교체했다. 손그림 SVG 는 폴백으로 남는다.

### 출처와 매핑
- 캐릭터 목록: `roles181.json` (181종) — **이미지 필드가 없다**
- 경로는 공식 툴 번들 `sbotc.js` 를 파싱해 얻었다
  - 팀 변형이 있는 156종: `/assets/{id}_{g|e}-{hash}.webp`
  - 우화·여행자 등 25종: `/assets/{id}-{hash}.webp` (예: `djinn-SYNTW9dK.webp`)
- 팀 기준으로 변형 선택 — 하수인·악마는 `_e`(적), 나머지는 `_g`(청)
- 매핑 결과 **181/181, 미매핑 0**

### 동봉 방식
| 선택지 | 판단 |
|---|---|
| data URI 인라인 | 4MB → 단일 HTML 이 감당 못 함. 기각 |
| **별도 파일 + 상대경로** | 채택 — `thyrsus/icons/{id}.webp`, 평균 22KB |

`loading="lazy"` 로 백과사전 181개 동시 렌더의 첫 페인트를 지킨다.

### 폴백
`officialIconHTML()` 이 폴백 마크업(기존 인라인 SVG → 이모지 → sysIcon)을 base64 로
`data-fb` 에 실어 두고, `onerror` 에서 `outerHTML` 을 통째로 갈아끼운다.
→ `index.html` 만 떼어 오프라인으로 열어도 아이콘 없이 그대로 동작한다.

### 크기 규칙
SVG 용으로 이미 브레이크포인트별 튜닝이 끝나 있던 `:has(svg)` 사다리(18곳)를
`:has(svg,.cicon-img)` 로 확장해 그대로 재사용했다. 공식 아트는 손그림보다 시각 밀도가
높아 `1.35em` 을 곱해 토큰 지름의 **54~66%** 를 차지한다 (SVG 는 40~48% 였다).

측정값: 원탁 64% · 그리모어 65% · 위저드 대형토큰 66% · 캐릭터확인 61% · 백과사전 64%

### 검증
- `node --check` 스크립트 블록 32/32
- 시나리오 더미 220명 — 실패 런 0
- 퍼저 400판 — 위반 0
- 돌연변이 37종 — 검출 35 · 미검출 0 · masked 2 · 앵커부실 0
- 브라우저 실측 — `img.cicon-img` 188개 로드, 깨진 이미지 0, 잔존 SVG 0,
  모바일(375px) 가로 오버플로 없음
