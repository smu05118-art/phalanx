# 티르소스 독립 적대적 검증 보고서

- 대상: `thyrsus/index.html` (3,836줄 / 313KB, 단일 HTML)
- 검증 일자: 2026-08-31
- 방법: 코드 정독 + Playwright(Chromium, `file://`, `confirm/prompt/alert` 스텁, `localStorage` 초기화)로 **모든 항목 실기 재현**
- 원칙: 재현하지 못한 것은 보고하지 않음. `index.html`은 수정하지 않음.

## 집계

| 심각도 | 건수 | 번호 |
|---|---|---|
| 치명 | 2 | C-1, C-2 |
| 높음 | 5 | H-1 ~ H-5 |
| 보통 | 7 | M-1 ~ M-7 |
| 낮음 | 5 | L-1 ~ L-5 |
| 검증했으나 이상 없음 | 8 | V-1 ~ V-8 |

---

# 치명

## C-1. 사망자가 투표하는 순간 그 표가 화면에서 사라지고, 분자·분모가 마감값과 어긋난다

- **위치**: `renderNomOpen` — index.html:1868 / `castVote` — index.html:1914~1919 / `closeBallot` — index.html:1930~1941

**결함 요약**
2차 찬반 화면의 투표권자 목록은 `p.deadVote!==false`(=토큰 보유)로 만든다(1868줄).
그런데 `castVote`는 사망자가 찬성/반대를 누른 **즉시** `p.deadVote=false`로 토큰을 소진시킨다(1920줄).
따라서 다음 `renderAll()`에서 그 사망자는 목록에서 **완전히 사라지고**, 분모가 1 줄고, 그 표는 분자에도 잡히지 않는다.
반면 `closeBallot`은 `n.deadVoters`를 근거로 그 사람을 다시 분모·분자에 넣는다(1932~1936줄).
결과적으로 **투표 진행 중 화면의 숫자와 마감 후 확정 숫자가 다르고**, 사망자는 자기 표를 되돌릴 UI 수단을 잃는다.

**재현 절차** (실측)
```js
// 6인, D·E 사망(토큰 보유), 낮 1, A→B 지명이 2단계에 진입한 상태
S.noms.push({id:'n1',day:1,nominator:'p0',nominee:'p1',hands:['p0','p1','p2','p5'],
             stage:2,votes:{},closed:false,deadVoters:[]});
renderAll();
// 화면: 행 = [A, B, C, F, D👻, E👻] / 분모 6
castVote('n1','p3','yes');            // 사망자 D가 찬성
// 화면: 행 = [A, B, C, F, E👻]  ← D 행이 사라짐
//       분자 0 / 분모 5 / 과반 기준 3 / 찬성률 0.0%
closeBallot('n1');
// 확정: {yes:1, den:6, need:4, ratio:0.1667, deadVoters:['D']}
```
실측 출력:
```
AFTER D(dead) votes yes:  rows=[A,B,C,F,E👻]  deadVote D=false
denominator shown in UI: 찬성(분자)0 / 반대0 / 투표권(분모)5 / 과반 기준3 / 찬성률0.0%
closed nom: {yes:1, den:6, need:4, ratio:0.1667, result:'yesFail', deadVoters:['D']}
```

**기대 동작**
사망자가 이번 지명에서 표를 던지면 그 행이 그대로 남아 `찬성` 상태로 표시되고, 분자·분모·찬성률이 실시간으로 마감값과 동일해야 한다. 토글로 취소·변경도 가능해야 한다.

**제안 패치**
```diff
@@ index.html:1868 (renderNomOpen 2단계)
-  const dead=S.players.filter(p=>!p.alive&&p.deadVote!==false);
+  // 이 지명에서 이미 표를 던져 토큰이 소진된 사망자도 계속 노출한다
+  const dead=S.players.filter(p=>!p.alive && (p.deadVote!==false || nom.votes[p.id]!==undefined));
```
그리고 `closeBallot`의 분모 산출도 같은 기준으로 통일한다(이름 기반 `deadVoters` 매칭 제거 — L-3 참조):
```diff
@@ index.html:1930
 function closeBallot(nid){
   const n=findNom(nid);
-  const alive=alivePlayers(); const dead=S.players.filter(p=>!p.alive&&(n.deadVoters.includes(p.name)||p.deadVote!==false));
-  const eligible=alive.concat(S.players.filter(p=>!p.alive&&p.deadVote!==false), S.players.filter(p=>!p.alive&&n.deadVoters.includes(p.name)));
-  const uniq=[...new Set(eligible)];
+  const uniq=S.players.filter(p=>p.alive || p.deadVote!==false || n.votes[p.id]!==undefined);
   const den=uniq.length, need=majority(den);
```

---

## C-2. 탕녀 계승 판정이 1명 어긋나고, 같은 화면의 낮 패널 안내와 정면으로 모순된다

- **위치**: `checkEndConditions` — index.html:891~906 (특히 895줄 `const aliveN = alivePlayers().length;`) / `voteNotices` — index.html:1716

**결함 요약**
`voteNotices`(낮 패널)는 **악마가 살아있는 시점**의 `alivePlayers().length`로 "5+"를 판정하고,
`checkEndConditions`는 **악마가 죽은 뒤**의 `alivePlayers().length`로 같은 "5+"를 판정한다.
같은 기준을 서로 다른 시점에 재기 때문에 생존 5명(악마 포함) 구간에서 두 안내가 정반대가 된다.
사회자는 "계승되니 게임 계속"이라는 안내를 보고 처형을 확정한 직후 "선한 팀 승리"라는 토스트를 받는다.

**재현 절차** (실측)
```js
// 5인 전원 생존: P0=임프, P1=탕녀, P2=요리사, P3=초공감자, P4=수도사, 낮 1
voteNotices(null).filter(x=>x.includes('탕녀'));
// → "🔴 탕녀 생존 + 생존자 5명(5+) — 지금 악마가 처형돼도 게임은 끝나지 않습니다(계승)."
killPlayer(playerOf('p0'),'처형');
// → toast: "🏆 악마가 죽었습니다 — 선한 팀 승리! (탕녀 계승 조건 없음)"
```
대조군(6인 전원 생존)에서는 처형 후 생존 5명이 되어 정상적으로 계승 토스트가 뜬다.

**기대 동작**
공식 탕녀 규칙의 "5명 이상 생존"은 **죽는 악마를 포함해서** 세는 것이 통상 해석이다.
어느 해석을 택하든 두 곳이 같은 시점·같은 기준을 써야 하며, 지금처럼 한 화면 안에서 상반된 결론을 내면 안 된다.

**제안 패치**
`killPlayer`가 사망 처리 **전** 생존 수를 넘겨준다.
```diff
@@ index.html:868
-function killPlayer(p, cause){
+function killPlayer(p, cause){
+  const aliveBefore = alivePlayers().length;   // 죽는 본인 포함
@@ index.html:886
-  p.alive=false; log(`💀 ${p.name}(${charName(p)}) 사망 — ${cause}`);
-  checkEndConditions(cause);
+  p.alive=false; log(`💀 ${p.name}(${charName(p)}) 사망 — ${cause}`);
+  checkEndConditions(cause, aliveBefore);
 }
@@ index.html:891
-function checkEndConditions(cause){
+function checkEndConditions(cause, aliveBefore){
@@ index.html:895
-    const aliveN = alivePlayers().length;
+    const aliveN = (aliveBefore!==undefined? aliveBefore : alivePlayers().length+1);
```
(반대 해석을 택한다면 1716줄을 `alivePlayers().length>=6`으로 바꾸고 문구를 "악마 제외 5명"으로 고칠 것.)

---

# 높음

## H-1. `window.__stepKiller`가 렌더 부작용으로 정해져, BMR/SV에서 살해 시전자가 뒤바뀌고 찻집 여인 보호가 우회된다

- **위치**: `stepWidget` — index.html:1563 (`if(c && c.killer && S.edition!=='tb'){ window.__stepKiller=c.id; ... }`) / `doStepKill` — index.html:1681~1695

**결함 요약**
`__stepKiller`는 **밤 시트를 그리는 도중** 각 살해형 캐릭터 위젯이 렌더될 때마다 덮어써진다.
`renderAll()`은 모든 단계를 한 번에 그리므로, 최종값은 항상 **그 밤 순서에서 마지막으로 렌더된 살해형 캐릭터**가 된다.
`doStepKill`은 이 전역값으로 (a) 시전자 오작동 판정, (b) 로그의 시전자 이름, (c) **암살자면 찻집 여인 보호를 관통** 분기를 결정한다.
따라서 실제로 클릭한 단계와 무관한 캐릭터가 시전자로 잡힌다.

**재현 절차 A — 시전자 오귀속** (실측)
```js
// BMR, 좌석: P0=푸카, P1=암살자, P2=대부, P3=찻집여인, P4=요리사, P5=초공감자, P6=군인
switchTab('night'); renderAll();
window.__stepKiller;        // → 'godfather'   (밤 순서상 대부가 마지막 렌더)
doStepKill('p4');           // 사회자는 "푸카" 단계에서 P4 살해를 기록
S.log;                      // → "💀 P4(요리사) 사망 — 대부의 공격"
```

**재현 절차 B — 찻집 여인 보호 우회** (실측, 더 치명적)
```js
// BMR, 좌석: P0=암살자, P1=푸카, P2=요리사, P3=찻집여인, P4=초공감자, P5=군인
switchTab('night'); renderAll();
window.__stepKiller;                 // → 'assassin'
teaLadyBlock(playerOf('p2'));        // → P3  (P2는 보호받아야 함)
doStepKill('p2');                    // 푸카 단계에서 기록
playerOf('p2').alive;                // → false  ❌ 보호 무시하고 사망
// 대조: window.__stepKiller='pukka'; doStepKill('p2');
//   → "🍵 P2은(는) 찻집 여인(P3)의 살아있는 선한 이웃 — 사망하지 않습니다(불발)" / alive=true
```

**기대 동작**
살해 판정은 클릭한 단계의 캐릭터를 시전자로 삼아야 한다. 렌더 순서에 좌우되면 안 된다.

**제안 패치** — 전역 대신 인자로 전달한다.
```diff
@@ index.html:1563
-  if(c && c.killer && S.edition!=='tb'){ window.__stepKiller=c.id;
+  if(c && c.killer && S.edition!=='tb'){
@@ index.html:1573 (selPlayers 호출부)
-    return `<h3>🗡 살해 기록 (${esc(c.ko)})</h3>${extra}<p class="hint">…</p>`+selPlayers('doStepKill', p=>p.alive, c.ko+'가 지목한 대상');
+    return `<h3>🗡 살해 기록 (${esc(c.ko)})</h3>${extra}<p class="hint">…</p>`
+      +`<div class="row" style="margin-top:8px">
+          <select id="sel-doStepKill-${c.id}">…</select>
+          <button class="small primary" onclick="doStepKill(document.getElementById('sel-doStepKill-${c.id}').value,'${c.id}')">적용</button>
+        </div>`;
@@ index.html:1681
-function doStepKill(pid){ if(!pid)return; const t=playerOf(pid);
-  const actor=S.players.find(q=>(q.alive || (q.charId==='zombuul'&&hasStatus(q,'fakedead'))) && q.charId===window.__stepKiller);
+function doStepKill(pid, killerId){ if(!pid)return; const t=playerOf(pid);
+  const kid = killerId || window.__stepKiller;
+  const actor=S.players.find(q=>(q.alive || (q.charId==='zombuul'&&hasStatus(q,'fakedead'))) && q.charId===kid);
@@ index.html:1686
-  if(window.__stepKiller!=='assassin'){
+  if(kid!=='assassin'){
@@ index.html:1693
-  if(window.__stepKiller==='po' && S.poCharged){ …
+  if(kid==='po' && S.poCharged){ …
```
`wizEffect`(2845줄)도 `window[sc.fn](tgt)` 대신 `doStepKill(tgt, charOf(wiz.stepId)?.id)`를 넘기도록 맞춘다.

---

## H-2. 좀버얼의 두 번째(진짜) 사망 뒤에도 `fakedead` 토큰이 남아, 선한 팀 승리를 영원히 판정하지 않는다

- **위치**: `killPlayer` — index.html:869~877 / `checkEndConditions` — index.html:892

**결함 요약**
`checkEndConditions`의 악마 생존 판정은
`(p.alive || (p.charId==='zombuul' && hasStatus(p,'fakedead')))`
인데, 두 번째 사망 경로(886줄)는 `fakedead` 토큰을 **제거하지 않는다**.
따라서 좀버얼이 진짜로 죽어도 `demonAlive===true`가 유지되어 승리 판정이 영구히 실행되지 않는다.

**재현 절차** (실측)
```js
// BMR, P0=좀버얼 외 5인
killPlayer(playerOf('p0'),'밤 살해');
// → "🪦 좀버얼의 첫 사망 …" (정상)
killPlayer(playerOf('p0'),'처형');
// → toast 없음. 승리 안내 없음.
hasStatus(playerOf('p0'),'fakedead');   // → true  ❌ 남아 있음
S.players.some(p=>(p.alive||(p.charId==='zombuul'&&hasStatus(p,'fakedead')))
                 && charOf(p.charId)?.type==='demon');  // → true ❌
```

**기대 동작**
두 번째 사망 시 `fakedead`를 제거하고, 다른 악마가 없으면 선한 팀 승리를 안내해야 한다.

**제안 패치**
```diff
@@ index.html:886
-  p.alive=false; log(`💀 ${p.name}(${charName(p)}) 사망 — ${cause}`);
+  if(p.charId==='zombuul'){
+    const i=(p.statuses||[]).findIndex(s=>s.key==='fakedead');
+    if(i>=0){ p.statuses.splice(i,1);
+      log(`🪦 ${p.name}(좀버얼) 두 번째 사망 — 죽은 척 해제, 실제 사망`); }
+  }
+  p.alive=false; log(`💀 ${p.name}(${charName(p)}) 사망 — ${cause}`);
   checkEndConditions(cause);
```

---

## H-3. 별 넘기기(임프 자살) 직후 "선한 팀 승리" 오안내가 뜬다

- **위치**: `doImpKill` — index.html:1642~1653 / `killPlayer`→`checkEndConditions` — index.html:887, 891

**결함 요약**
임프 자살 분기에서 `killPlayer()`를 먼저 호출하므로 **하수인 승격 이전에** 종료 판정이 돈다.
그 시점에 생존 악마가 없으므로 "🏆 악마가 죽었습니다 — 선한 팀 승리!"가 표시되고,
곧바로 "P1이(가) 새 임프입니다"가 이어진다. 게임의 종료 여부를 두고 사회자에게 정반대 지시가 연속으로 뜬다.

**재현 절차** (실측)
```js
// TB, P0=임프, P1=남작, P2=첩자, 그 외 선 4인, 밤 2
window.__promptAnswer='P1';
doImpKill('p0');   // 임프가 자기 자신을 지목
// toasts:
//   1) "🏆 악마가 죽었습니다 — 선한 팀 승리! (탕녀 계승 조건 없음)"   ❌
//   2) "P1이(가) 새 임프입니다. 지금 깨워 임프 토큰을 보여주세요."
```

**기대 동작**
별 넘기기는 악마가 계속 존재하는 상황이므로 승리 판정을 하지 않아야 한다.

**제안 패치** — 승격을 먼저 하거나, 종료 판정을 억제한다.
```diff
@@ index.html:1642
   if(t===imp){ // 자살 → 별 넘기기
-    killPlayer(t,'임프 자살(★ 별 넘기기)');
     const minions=S.players.filter(q=>q.alive && charOf(q.charId)?.type==='minion');
     if(minions.length){
       const sw=minions.find(m=>m.charId==='scarletwoman');
       const pick=prompt(…, (sw||minions[0]).name);
       const np=minions.find(m=>m.name===pick)||sw||minions[0];
-      np.charId='imp'; log(`★ ${np.name}이(가) 새 임프가 됨 …`);
+      np.charId='imp'; log(`★ ${np.name}이(가) 새 임프가 됨 …`);   // 먼저 승격
       toast(`${np.name}이(가) 새 임프입니다. …`,'warn');
     }
+    killPlayer(t,'임프 자살(★ 별 넘기기)');   // 그 다음 사망 → 종료 판정이 새 임프를 본다
     save(); renderAll(); return;
   }
```

---

## H-4. 밤 위저드의 씬 상태(`_shown`/`_val`)가 전역 상수 `NIGHT_FLOW`에 눌러붙어, 재실행 시 지난 밤 답을 그대로 표시한다

- **위치**: `wizShowVal` — index.html:2841 / `renderWiz` show-number·show-answer 분기 — index.html:2811~2822 / `startWiz` — index.html:2706

**결함 요약**
`startWiz`는 `scenes`로 **`NIGHT_FLOW`의 씬 객체 참조를 그대로** 담는다(2712줄).
`wizShowVal`은 그 객체에 `_val`/`_shown`을 직접 기록한다.
`closeWiz`는 이 필드를 지우지 않는다.
같은 (first|other) 플로우를 두 번째로 실행하면 `_shown===true` 상태로 시작해, **숫자·답 선택 화면을 건너뛰고 지난번 값을 전체화면으로 표시**한다.
사회자는 그 화면을 그대로 플레이어에게 보여주게 되므로, 잘못된 정보가 그대로 전달된다.

**재현 절차** (실측 — 점쟁이)
```js
// TB, 점쟁이 인플레이. 밤 2에서 위저드 실행
startWiz('fortuneteller');
// show-answer 씬: 선택 그리드 표시 (_shown=false) — 정상
wizShowVal('예');  closeWiz(true);
advancePhase(); advancePhase();      // 밤 3
startWiz('fortuneteller');
// show-answer 씬: _shown=true, .wiz-biganswer === "예"   ❌ 지난 밤 답이 즉시 표시됨
```
`chef`(첫날 밤 전용)로도 동일하게 확인:
```
NIGHT_FLOW.chef → {"first":[{"t":"wake"},
  {"t":"show-number","suggest":"chefPairs","caption":"…","_val":3,"_shown":true},{"t":"sleep"}]}
```
상수 자체가 오염된다.

**기대 동작**
위저드를 열 때마다 씬은 초기 상태여야 하고, 표시값은 실행 인스턴스에만 남아야 한다.

**제안 패치** — 씬을 깊은 복사해서 인스턴스화한다.
```diff
@@ index.html:2706
 function startWiz(stepId){
-  const scenes=flowFor(stepId); if(!scenes) return;
+  const src=flowFor(stepId); if(!src) return;
+  const scenes=src.map(s=>Object.assign({}, s));   // 씬별 얕은 복사(내부 배열은 읽기 전용)
   const c=charOf(stepId);
@@ index.html:2714
 function startCustomWiz(title, scenes){
-  wiz={stepId:'__custom', custom:true, title, idx:0, vars:{}, holder:null, scenes};
+  wiz={stepId:'__custom', custom:true, title, idx:0, vars:{}, holder:null,
+       scenes:scenes.map(s=>Object.assign({}, s))};
```

---

## H-5. 플레이어 이름의 작은따옴표 하나가 사망/소생/토큰 버튼을 전부 무력화하며, 임의 JS 실행까지 가능하다

- **위치**: 그리모어 카드 — index.html:1318, 1320, 1321, 1322 / 플레이어 모달 — index.html:3784, 3785, 3788, 3789

**결함 요약**
`esc()`는 `'`를 `&#39;`로 바꾸지만, 이 값이 들어가는 자리는 **HTML 속성 안의 JS 문자열 리터럴**이다.
브라우저는 속성값을 먼저 HTML 디코드한 뒤 JS로 파싱하므로 `&#39;`는 다시 `'`가 되어 문자열을 탈출한다.
즉 `esc()`는 이 컨텍스트에서 아무 보호도 하지 못한다.

**재현 절차 1 — 실사용 파손(가장 흔한 경우)** (실측)
```js
// 플레이어 이름을 "O'Brien" 으로 입력하고 그리모어(카드 뷰)로 이동
// 생성된 속성: onclick="if(confirm('O&#39;Brien 사망 처리?')){…}"
//           → 디코드 후: if(confirm('O'Brien 사망 처리?')){…}
```
| 클릭한 버튼 | 결과 |
|---|---|
| 사망 (그리모어) | `SyntaxError: missing ) after argument list` / `alive` 그대로 `true` |
| 소생 (그리모어) | 동일 오류 / `alive` 그대로 `false` |
| 토큰 소진·복원 | 동일 오류 / `deadVote` 변화 없음 |
| 💀 사망 (모달) | 동일 오류 / `alive` 그대로 `true` |

**아무 오류 메시지도 화면에 뜨지 않는다.** 사회자는 버튼을 눌렀는데 아무 일도 일어나지 않는 상태를 게임 중에 만나게 된다.

**재현 절차 2 — 임의 코드 실행** (실측)
```js
// 이름을  ')||1){window.__pwned=1};//   으로 입력
// 최종 속성: if(confirm('')||1){window.__pwned=1};// 사망 처리?')){killPlayer(…)}
// 사망 버튼 클릭 → window.__pwned === 1, 그리고 killPlayer는 실행되지 않음
```

**기대 동작**
이름은 HTML로도 JS로도 안전하게 삽입되어야 하며, 어떤 이름이든 버튼은 정상 동작해야 한다.

**제안 패치** — 인라인 문자열 보간을 제거하고 이름은 런타임에 조회한다.
```diff
@@ index.html:1318
-        <button class="small danger" onclick="if(confirm('${esc(p.name)} 사망 처리?')){killPlayer(playerOf('${p.id}'),'사회자 수동 처리');save();renderAll();}">사망</button>
+        <button class="small danger" onclick="uiKill('${p.id}')">사망</button>
@@ index.html:1320
-        <button class="small" onclick="playerOf('${p.id}').alive=true;log('${esc(p.name)} 소생(수동)');save();renderAll()">소생</button>
+        <button class="small" onclick="uiRevive('${p.id}')">소생</button>
@@ index.html:1321-1322
-        …onclick="playerOf('${p.id}').deadVote=false;log('${esc(p.name)} 투표 토큰 수동 소진');save();renderAll()"…
-        …onclick="playerOf('${p.id}').deadVote=true;log('${esc(p.name)} 투표 토큰 복원');save();renderAll()"…
+        …onclick="uiToken('${p.id}',false)"… / …onclick="uiToken('${p.id}',true)"…
```
공용 헬퍼(신규):
```js
function uiKill(pid, after){ const p=playerOf(pid); if(!p) return;
  if(!confirm(`${p.name} 사망 처리?`)) return;
  killPlayer(p,'사회자 수동 처리'); save(); (after||renderAll)(); }
function uiRevive(pid, after){ const p=playerOf(pid); if(!p) return;
  p.alive=true; log(`${p.name} 소생(수동)`); save(); (after||renderAll)(); }
function uiToken(pid, has, after){ const p=playerOf(pid); if(!p) return;
  p.deadVote=has; log(`${p.name} 투표 토큰 ${has?'복원':'소진'}`); save(); (after||renderAll)(); }
```
모달(3784~3789줄)은 `uiKill('${p.id}', closePlayerModal)` / `uiToken('${p.id}',false,()=>openPlayerModal('${p.id}'))` 형태로 콜백만 바꿔 재사용한다.

---

# 보통

## M-1. 낮에 부여한 🛡보호 토큰이 영구히 남아, 이후 모든 밤의 살해를 계속 무효화한다

- **위치**: `addStatusUI` — index.html:1332 / `togglePStatus` — index.html:3801 / `expireStatuses` — index.html:856

**결함 요약**
두 곳 모두 보호의 만료를 `{kind:'day', n:ph.n}`으로 설정한다.
**이미 시작된 낮**에 토큰을 붙이면 그 페이즈 전환은 다시 오지 않으므로 `expireStatuses`가 영원히 매칭하지 않는다.
사회자가 낮에 "수도사가 어제 X를 보호했지"라고 뒤늦게 기록하는 것은 자연스러운 동작인데, 그 토큰이 이후 게임 내내 남아 `doImpKill`의 보호 분기(1656줄)를 계속 발동시킨다.

**재현 절차** (실측)
```js
S.phase={kind:'day',n:1};
togglePStatus('p2','protect');
// → {"key":"protect","source":"사회자 수동","expiresAt":{"kind":"day","n":1}}
advancePhase(); advancePhase(); advancePhase(); advancePhase();   // 낮 3까지 진행
hasStatus(playerOf('p2'),'protect');   // → true  ❌ 그대로 남아 있음
// 이 상태에서 doImpKill('p2') → "수도사의 보호 중 — 사망 없음"
```

**기대 동작**
낮에 붙인 보호는 **그 낮이 끝날 때**(=다음 밤 시작) 해제되어야 한다. 밤에 붙인 것은 새벽(그 낮 시작)에 해제.

**제안 패치**
```diff
@@ index.html:1332
-  if(key==='protect'){ exp={kind:'day', n:ph.n}; }
+  if(key==='protect'){ exp = ph.kind==='night'? {kind:'day', n:ph.n} : {kind:'night', n:ph.n+1}; }
@@ index.html:3801
-    if(key==='protect') exp={kind:'day', n:ph.n};
+    if(key==='protect') exp = ph.kind==='night'? {kind:'day', n:ph.n} : {kind:'night', n:ph.n+1};
```
(추가 안전장치로 `expireStatuses`에 "지나간 페이즈" 정리 로직을 넣는 것도 좋다:
`if(s.expiresAt && (s.expiresAt.n < ph.n || (s.expiresAt.n===ph.n && s.expiresAt.kind===ph.kind))) remove;`)

---

## M-2. 밤 위저드 제목이 `esc()`를 거치지 않아, 플레이어 이름으로 스크립트가 실행된다

- **위치**: `wizTitle` — index.html:2718~2723 / `renderWiz` — index.html:2762 (`$('#wizhead').innerHTML=...`)

**결함 요약**
`wizTitle()`은 `` `${glyph(c.id)} ${c.ko}` + (wiz.holder? ` — ${wiz.holder.name}`:'') `` 로 이름을 **이스케이프 없이** 반환하고, 호출부에서 `innerHTML`로 삽입한다.
전 화면 XSS 스윕(타운스퀘어·그리모어·모달·투표·밤 시트·체크리스트·설정·리플레이·캐릭터 변경·캐릭터 확인 위저드) 중 **여기만** HTML 주입이 성립했다.

**재현 절차** (실측)
```js
S.players[1].name = `<img src=x onerror="window.__pwned2=1">`;
startWiz('poisoner');
document.getElementById('wizhead').innerHTML;
// → <span class="wtitle">☠️ 독살범 — <img src="x" onerror="window.__pwned2=1"></span>…
window.__pwned2;   // → 1  ❌ 실행됨
```

**기대 동작** 이름은 이스케이프되어 텍스트로만 보여야 한다.

**제안 패치**
```diff
@@ index.html:2718
 function wizTitle(){
-  if(wiz.custom) return wiz.title||'';
+  if(wiz.custom) return esc(wiz.title||'');
   const c=charOf(wiz.stepId);
-  if(c) return `${glyph(c.id)} ${c.ko}` + (wiz.holder? ` — ${wiz.holder.name}`:'');
-  return INFO_STEPS[wiz.stepId]? '👥 '+INFO_STEPS[wiz.stepId].ko : wiz.stepId;
+  if(c) return `${glyph(c.id)} ${esc(c.ko)}` + (wiz.holder? ` — ${esc(wiz.holder.name)}`:'');
+  return INFO_STEPS[wiz.stepId]? '👥 '+esc(INFO_STEPS[wiz.stepId].ko) : esc(wiz.stepId);
 }
```
주의: `wizShowVal`(2842줄)이 `log(\`${wizTitle()} 위저드: …\`)`로 제목을 로그에 넣으므로, 이스케이프된 문자열이 기록에 이중 이스케이프로 남는다.
로그용은 원문을 쓰도록 `wizTitleRaw()`를 분리하는 편이 깔끔하다.

---

## M-3. 체크리스트 체크박스의 `onchange` 속성이 이름의 큰따옴표로 탈출된다

- **위치**: `renderCheck` — index.html:2107

**결함 요약**
```js
onchange="S.checks['${i.key.replace(/'/g,"\\'")}']=this.checked;save()"
```
작은따옴표만 처리하고 **HTML 이스케이프를 하지 않는다**. `i.key`에는 `buildChecklist`(2062줄, 붉은 청어 플레이어 이름)와 (2093줄, 커스텀 캐릭터 이름)이 그대로 들어간다.
이름에 `"`가 있으면 속성이 조기 종료되어 임의 이벤트 핸들러를 붙일 수 있고, 악의가 없어도 **체크박스 상태가 저장되지 않는다**.

**재현 절차** (실측)
```js
// 붉은 청어 플레이어 이름:  x" onfocus="window.__pw3=1" autofocus="
S.redHerringId='p2'; switchTab('check');
// 생성된 DOM:
// <input type="checkbox" onchange="S.checks['셋업|점쟁이|붉은 청어 지정(현재: x"
//        onfocus="window.__pw3=1" autofocus=") — 게임 내내 유지']=this.checked;save()">
window.__pw3;   // → 1  ❌ 자동 실행
```
커스텀 캐릭터 이름에 `"`를 넣은 경우도 동일하게 속성이 깨지고, 클릭해도 `S.checks`에 저장되지 않음을 확인.

**기대 동작** 어떤 이름이든 체크 상태가 정확히 저장되어야 하고 코드가 실행되어서는 안 된다.

**제안 패치** — 키를 인라인에 넣지 말고 인덱스로 참조한다.
```diff
@@ index.html:2100 (renderCheck)
   const items=buildChecklist();
+  window.__ckItems=items;                     // 렌더 시점의 목록을 보관
@@ index.html:2107
-    <div class="checkitem"><input type="checkbox" ${S.checks[i.key]?'checked':''} onchange="S.checks['${i.key.replace(/'/g,"\\'")}']=this.checked;save()">
+    <div class="checkitem"><input type="checkbox" ${S.checks[i.key]?'checked':''} onchange="toggleCheck(${items.indexOf(i)},this.checked)">
```
```js
function toggleCheck(idx, v){ const it=(window.__ckItems||[])[idx]; if(!it) return;
  S.checks[it.key]=v; save(); }
```

---

## M-4. `cloudBuildDoc`이 열려 있는 플레이어 모달을 그대로 스냅샷에 굽는다

- **위치**: `CLOUD_DYNAMIC_IDS` — index.html:2987 / `cloudBuildDoc` — index.html:2988~3001

**결함 요약**
`CLOUD_DYNAMIC_IDS`에 `pmodal`이 빠져 있다. `#pmodal`은 열려 있으면 `hidden`이 없는 상태이므로, 저장된 문서를 다른 기기에서 열면 **직전에 보던 플레이어의 캐릭터 모달이 전체화면으로 떠 있는 채로** 로드된다.

**재현 절차** (실측)
```js
openPlayerModal('p0');                 // P0 = 임프
const doc = cloudBuildDoc();
doc.match(/<div id="pmodal"[^>]*>[\s\S]*?(?=<script>)/)[0];
// → <div id="pmodal"><div class="pmcard" …><h3>임프</h3>…   ❌
// 모달을 닫은 상태에서는  <div id="pmodal" hidden=""></div>   (정상)
```
`#wizard`는 `hidden=true`로 정리되고 `#wizbody`도 비워짐을 확인(정상).

**기대 동작** 저장 문서에는 동적 오버레이가 남지 않아야 한다.

**제안 패치**
```diff
@@ index.html:2987
-const CLOUD_DYNAMIC_IDS=['sidenav','subtabs','quickstats','wizhead','wizbody','wizfoot','log'];
+const CLOUD_DYNAMIC_IDS=['sidenav','subtabs','quickstats','wizhead','wizbody','wizfoot','log','pmodal'];
@@ index.html:2991
   const wz=body.querySelector('#wizard'); if(wz) wz.hidden=true;
+  const pm=body.querySelector('#pmodal'); if(pm) pm.hidden=true;
```

---

## M-5. 설정 3단계의 "‹ 돌아가서 마저 준비하기" 버튼이 `ReferenceError`로 아무 동작도 하지 않는다

- **위치**: `renderSetup` — index.html:1123

**결함 요약**
```js
onclick="gotoSetupStep(issues[0].includes('플레이어')?1:2)"
```
`issues`는 `renderSetup` 안의 지역 상수(1121줄)라 클릭 시점의 전역 스코프에는 없다.

**재현 절차** (실측)
```js
S=blank();
['가','나','다','라','마'].forEach((n,i)=>S.players.push({id:'q'+i,name:n,charId:'',alive:true,deadVote:true,statuses:[],notes:''}));
S.setupStep=3; switchTab('setup');
// 버튼 클릭 → pageerror: "ReferenceError: issues is not defined"
// S.setupStep 은 3 그대로
```

**기대 동작** 미완료 항목 종류에 따라 1단계 또는 2단계로 이동해야 한다.

**제안 패치**
```diff
@@ index.html:1123
-      <div class="bigactions"><button onclick="gotoSetupStep(issues[0].includes('플레이어')?1:2)">‹ 돌아가서 마저 준비하기</button></div>`
+      <div class="bigactions"><button onclick="gotoSetupStep(${issues[0].includes('플레이어')?1:2})">‹ 돌아가서 마저 준비하기</button></div>`
```
(렌더 시점에 값을 확정해 넣는다.)

---

## M-6. 사망자 투표 기록이 **이름 문자열** 기반이라 동명이인이 있으면 표가 통째로 사라진다

- **위치**: `castVote` — index.html:1918, 1921, 1923 / `closeBallot` — index.html:1932~1933

**결함 요약**
`n.deadVoters`에 `p.name`을 넣고 `filter(x=>x!==p.name)`로 뺀다. 같은 이름이 둘이면 한 사람이 기권으로 바꿀 때 **두 항목이 모두 제거**된다.
`closeBallot`은 `n.deadVoters.includes(p.name)`으로 분모·분자 대상을 다시 만들기 때문에, 실제로 찬성표를 던지고 토큰까지 소진한 사람이 집계에서 빠진다.

**재현 절차** (실측)
```js
// 6인, p3·p4 둘 다 이름 "홍길동", 둘 다 사망·토큰 보유
castVote('n1','p3','yes');  castVote('n1','p4','yes');
// deadVoters = ["홍길동","홍길동"] / tokens = [false,false]
castVote('n1','p3','abs');            // p3만 기권으로 변경
// deadVoters = []            ❌ p4 항목까지 제거
// tokens = [true,false]      (p4는 토큰 소진 상태 유지)
closeBallot('n1');
// {yes:0, den:5, need:3}     ❌ votes.p4==='yes' 인데 분자 0, p4가 분모에도 없음
```

**기대 동작** 투표 기록은 플레이어 `id`로 관리되어야 한다.

**제안 패치**
```diff
@@ index.html:1918
-    if(prev===v){ delete n.votes[pid]; if(v!=='abs'){ p.deadVote=true; n.deadVoters=n.deadVoters.filter(x=>x!==p.name); …
+    if(prev===v){ delete n.votes[pid]; if(v!=='abs'){ p.deadVote=true; n.deadVoters=n.deadVoters.filter(x=>x!==pid); …
@@ index.html:1921
-      p.deadVote=false; n.deadVoters.push(p.name); …
+      p.deadVote=false; n.deadVoters.push(pid); …
@@ index.html:1923
-    if((prev==='yes'||prev==='no') && v==='abs'){ p.deadVote=true; n.deadVoters=n.deadVoters.filter(x=>x!==p.name); …
+    if((prev==='yes'||prev==='no') && v==='abs'){ p.deadVote=true; n.deadVoters=n.deadVoters.filter(x=>x!==pid); …
```
표시부(index.html:1791 `n.deadVoters.map(esc).join(', ')`)는 `n.deadVoters.map(id=>esc(playerOf(id)?.name||'?'))`로 바꾼다.
기존 저장본 호환이 필요하면 로드 시 이름→id 변환을 한 번 수행한다.

---

## M-7. 악한 팀 승리(생존 2인 + 악마 생존)를 전혀 감지·안내하지 않는다

- **위치**: `checkEndConditions` — index.html:891~906

**결함 요약**
종료 판정 함수에 **선한 팀 승리 분기만** 있다. 공식 규칙의 "생존자가 2명이고 그중 하나가 악마면 악한 팀 승리"에 해당하는 코드가 없다.
성자 처형(악 승리)만 `executeNominee`에서 별도 토스트로 처리된다(1955줄).

**재현 절차** (실측)
```js
// TB, P0=임프, P1=독살범, P2~P4 = 선
['p2','p3','p4'].forEach(id=>killPlayer(playerOf(id),'처형'));
alivePlayers();          // → [P0/imp, P1/poisoner]
// toast 없음, S.log 에 "승리" 문구 없음   ❌
```

**기대 동작** 생존 2인 이하 + 악마 생존이면 악한 팀 승리를 안내해야 한다.

**제안 패치**
```diff
@@ index.html:891
 function checkEndConditions(cause){
   const demonAlive = S.players.some(p=>(p.alive || (p.charId==='zombuul'&&hasStatus(p,'fakedead'))) && charOf(p.charId)?.type==='demon');
+  const aliveN = alivePlayers().length;
+  if(demonAlive && aliveN<=2){
+    toast(`☠ 생존자 ${aliveN}명 + 악마 생존 — 악한 팀 승리! (여행자 제외 기준, 최종 확인은 사회자 재량)`,'warn');
+    log(`악한 팀 승리 조건 충족 — 생존 ${aliveN}명, 악마 생존`);
+    return;
+  }
   if(!demonAlive){ … }
```

---

# 낮음

## L-1. 이미 죽은 피지명자에게 "처형 확정" 버튼이 그대로 남아 있고, 누르면 재사망 처리된다

- **위치**: `renderDay` — index.html:1795 / `executeNominee` — index.html:1943~1957

**재현 절차** (실측)
```js
// A→B 지명이 과반 통과(찬성 4/6)한 뒤, B가 마녀 저주/성결자 등으로 이미 사망
playerOf('p1').alive=false; renderAll();
// "⚔ P1 처형 확정" 버튼 여전히 존재      ❌
executeNominee(e1);
// S.executedToday = "P1 (독살범)"  /  log: "💀 P1(독살범) 사망 — 처형 (찬성 4/6, 66.7%)"
```
**기대 동작**: 사망한 피지명자는 처형 후보에서 제외되고 버튼이 숨어야 한다.

**제안 패치**
```diff
@@ index.html:1795
-        ${isBest&&!S.executedToday?`<button class="small danger" …>⚔ … 처형 확정</button>`:''}
+        ${isBest&&!S.executedToday&&playerOf(n.nominee)?.alive?`<button class="small danger" …>⚔ … 처형 확정</button>`:''}
@@ index.html:1943
 function executeNominee(nid){
   const n=findNom(nid); const p=playerOf(n.nominee);
+  if(!p||!p.alive){ toast('이미 사망한 대상입니다 — 처형 처리하지 않습니다.','warn'); return; }
```
`best` 산출(1766줄)도 `passed.filter(n=>playerOf(n.nominee)?.alive)` 기준으로 좁히는 편이 안전하다.

## L-2. 독살범 위젯의 "적용"을 두 번 누르면 중독 토큰이 겹쳐 쌓이고, 모달 칩 한 번으로는 해제되지 않는다

- **위치**: `addStatus` — index.html:850 (중복 검사 없음) / `doPoison` — index.html:1629 / `togglePStatus` — index.html:3794

**재현 절차** (실측)
```js
doPoison('p2'); doPoison('p2');
playerOf('p2').statuses;
// → [{key:'poison',…},{key:'poison',…}]   토큰 2개
togglePStatus('p2','poison');              // 모달 ☠중독 칩 1회 클릭
playerOf('p2').statuses;                   // → 아직 1개 남음
isMalfunctioning(playerOf('p2'));          // → true   ❌
// 칩은 여전히 .on 상태로 보인다 (hasStatus 가 true 이므로)
```
**기대 동작**: 같은 키의 상태는 하나만 유지되거나, 칩 1회로 전부 해제되어야 한다.

**제안 패치**
```diff
@@ index.html:850
 function addStatus(p, key, source, expiresAt){
   p.statuses = p.statuses||[];
+  const UNIQUE=['poison','protect','master','curse','mad','drunkS','herring','fakedead','spent','virginUsed','slayerUsed'];
+  if(UNIQUE.includes(key)) p.statuses=p.statuses.filter(s=>s.key!==key);
   p.statuses.push({key, source:source||'', expiresAt:expiresAt||null});
@@ index.html:3796 (togglePStatus)
-  const idx=(p.statuses||[]).findIndex(s=>s.key===key);
-  if(idx>=0){ removeStatus(p,idx); }
+  if(hasStatus(p,key)){
+    while(true){ const i=(p.statuses||[]).findIndex(s=>s.key===key); if(i<0) break; removeStatus(p,i); }
+  }
```

## L-3. 후반전 교착: 침묵한 사망 토큰 보유자가 분모에 들어가 생존자 만장일치로도 처형이 불가능해진다

- **위치**: `renderNomOpen` — index.html:1868~1870 / `closeBallot` — index.html:1932~1935

**재현 절차** (실측)
```js
// 7인 중 생존 3(A·B·C), 사망 4명 전원 투표 토큰 보유. 사망자는 아무도 투표하지 않음
['p0','p1','p2'].forEach(id=>castVote('n1',id,'yes'));   // 생존자 만장일치
closeBallot('n1');
// → {yes:3, den:7, need:4, ratio:0.4286, result:'yesFail'}   ❌ 처형 불가
```
**설명**: 하우스 룰 문서(index.html:1752~1757)는 "생존자 전원 + 투표 토큰 보유 사망자"를 분모로 규정하므로 **의도된 설계일 수 있다**. 다만 후반전에 사망자가 쌓이면 생존자가 만장일치여도 구조적으로 처형이 불가능해지는 것은 게임 진행을 막는다. 의도가 아니라면 분모는 생존자 수로 두고 사망자 표는 분자에만 더하는 편이 공식 규칙과도 일치한다.

**제안 패치**(공식 규칙 정렬을 택할 경우)
```diff
@@ index.html:1930 closeBallot
-  const den=uniq.length, need=majority(den);
+  const den=alivePlayers().length, need=majority(den);   // 분모는 생존자 수
   const yes=uniq.filter(p=>n.votes[p.id]==='yes').length;  // 분자는 사망자 표 포함
```
`renderNomOpen`(1870줄)의 `den2`도 같은 기준으로 맞춘다.

## L-4. 암살자의 공격에 어릿광대 1회 생존이 발동한다

- **위치**: `killPlayer` — index.html:878~885 / `doStepKill` — index.html:1686 (암살자 예외는 찻집 여인에만 적용)

**재현 절차** (실측)
```js
// BMR, P1=암살자, P2=어릿광대
window.__stepKiller='assassin'; doStepKill('p2');
// → confirm("🃏 P2은(는) 어릿광대입니다 — 1회 생존 발동?") 후
//    toast "🃏 P2 생존 — 어릿광대 1회 능력 소진. 사망하지 않습니다."  / alive = true
```
**기대 동작**: 암살자는 "어떤 이유로 죽지 않는 경우에도" 죽이는 능력이므로, 어릿광대·군인·수도사 보호를 관통해야 한다. 최소한 사회자에게 이 예외를 고지해야 한다.
`doStepKill`에는 이미 `kid!=='assassin'` 예외가 있으나 **찻집 여인 분기에만** 적용되고, `resolveNightDeath → killPlayer`의 어릿광대 분기에는 전달되지 않는다.

**제안 패치**
```diff
@@ index.html:868
-function killPlayer(p, cause){
+function killPlayer(p, cause, opts){
+  const pierce = !!(opts&&opts.pierce);   // 암살자 등 '죽지 않는 경우에도' 살해
@@ index.html:878
-  if(p.charId==='fool' && p.alive && !hasStatus(p,'spent') && !isMalfunctioning(p)){
+  if(!pierce && p.charId==='fool' && p.alive && !hasStatus(p,'spent') && !isMalfunctioning(p)){
@@ index.html:1668 (resolveNightDeath)
-function resolveNightDeath(t, cause){
-  killPlayer(t, cause);
+function resolveNightDeath(t, cause, opts){
+  killPlayer(t, cause, opts);
@@ index.html:1694 (doStepKill 마지막)
-  resolveNightDeath(t, (actor?charName(actor):'악마')+'의 공격');
+  resolveNightDeath(t, (actor?charName(actor):'악마')+'의 공격', {pierce: kid==='assassin'});
```

## L-5. 별 넘기기·시장 대체 사망·처단자 지목이 `prompt` 이름 문자열 매칭이라 동명이인·오타에 취약하다

- **위치**: `doImpKill` — index.html:1647~1648(별 넘기기), 1660~1661(시장 대체) / `doSlayer` — index.html:1961

**재현 절차** (실측)
```js
// 시장 대체 사망 — 존재하지 않는 이름 입력
window.__confirmAnswer=true; window.__promptAnswer='존재하지않음';
doImpKill('p2');   // P2=시장
// → toast "대상을 찾지 못해 시장 사망으로 처리합니다." (기대대로 동작하지만 재시도 기회가 없음)
```
동명이인이면 `S.players.find(q=>q.name===alt&&q.alive)`가 **좌석 순서상 먼저인 사람**을 말없이 고른다.
별 넘기기(1648줄)도 오타 시 조용히 `minions[0]`로 폴백한다.

**기대 동작**: `prompt` 대신 위저드/오버레이의 플레이어 그리드(이미 `wizPlayers`·`wiz-pickbtn` 구현이 있음)로 좌석 번호와 함께 선택하게 해야 한다.

**제안 패치**(최소 조치 — 좌석 번호 병기 + 실패 시 재시도)
```diff
@@ index.html:1660
-      const alt=prompt('대신 죽을 플레이어 이름:'); const ap=S.players.find(q=>q.name===alt&&q.alive);
+      const list=S.players.map((q,i)=>`${i+1}. ${q.name}${q.alive?'':' 💀'}`).join('\n');
+      const alt=prompt(`대신 죽을 플레이어의 좌석 번호:\n${list}`);
+      const ap=S.players[parseInt(alt,10)-1];
+      if(ap && !ap.alive){ toast('이미 사망한 좌석입니다 — 시장 사망으로 처리합니다.','warn'); }
+      else if(ap){ resolveNightDeath(ap, '임프(시장 대체 사망)'); save(); renderAll(); return; }
```
별 넘기기(1647줄)·처단자(1961줄)도 동일하게 좌석 번호 방식으로 통일한다.

---

# 검증했으나 이상 없음

## V-1. 구버전 localStorage 스키마 로드
`customs / nightDone / checks / noms / nomSeq / edition / statuses / deadVote` 가 전부 빠진 저장본을 `thyrsus.tb.v1`에 심고 로드.
- `Object.assign(blank(), JSON.parse(raw))`(index.html:830)로 최상위 신규 필드가 모두 채워짐.
- 8개 탭(scripts/setup/sheet/grim/night/day/check/custom/guide) 전환 시 `pageerror` **0건**.
- `statuses`가 `undefined`인 플레이어에게 `togglePStatus`·`addStatus` 호출 → `p.statuses = p.statuses||[]`(851줄) 및 각 사용처의 `(p.statuses||[])` 가드로 정상 동작.
- `deadVote`가 `undefined`인 사망자는 `p.deadVote!==false`가 참이라 "투표 토큰 보유"로 올바르게 표시됨.
- 구버전 상태에서 지명 개시 → `S.noms`에 신규 스키마로 정상 생성.
→ **마이그레이션 결함 없음.**

## V-2. 밤 순서 배열과 캐릭터 플래그의 정합성
세 에디션 전부에 대해 기계적으로 대조:
```
tb/bmr/sv 모두: missingFirst=[] missingOther=[] orderNotChar=[]
                firstFalseButInOrder=[] otherFalseButInOrder=[] dupInOrder=[]
```
- `first:true`/`other:true`인데 밤 순서 배열에 없는 캐릭터: **0건** (= 절대 안 깨우는 캐릭터 없음)
- 밤 순서 배열에 있는데 `first/other:false`인 캐릭터: **0건**
- 배열에 존재하지 않는 id / 중복 id: **0건**
- TB `FIRST_NIGHT_ORDER`·`OTHER_NIGHT_ORDER`(index.html:552~553)는 공식 순서와 일치.
- BMR/SV의 **세부 순서**(예: 여관 주인 ↔ 궁정 신하 선후)는 이 환경에서 공식 문서를 대조할 수단이 없어 **판정 보류**. 추측으로 결함을 보고하지 않는다.

## V-3. 투표 경계조건 (사망자 표 관련 결함 C-1 제외)
| 시나리오 | 결과 |
|---|---|
| 0표 거수 마감 (5인) | `{hands:[], closed:true, result:'handsFail'}` — 정상 |
| 전원 기권 (2단계, 5인) | `{yes:0, den:5, need:3, ratio:0, result:'yesFail'}`, 처형 후보 미표시 — 정상 |
| 같은 날 3회 지명, 찬성률 동률(4/6 · 4/6 · 3/6) | "⚖ 최고 찬성률 동률 — 처형 없음" 표시, 처형 버튼 0개 — 정상 |
| 4번째 지명(5/6)으로 동률 해소 | 동률 안내 사라지고 "⚔ P4 처형 확정" 단독 노출 — 정상 |
| 생존 3인 지명·투표 | 거수 기준 2, 정상 진행 |
| 생존 2인 지명 | 거수 기준 2, 1표는 미달 부결 — 정상 |
| 사망자 표 취소 → 토큰 복원 → 재투표 | `deadVote` 복원·재소진·`deadVoters` 갱신 모두 정상(동명이인 제외, M-6) |
`best`/`tie` 산출 로직(index.html:1766)은 `[0.5,0.5,0.9]`·`[0.9,0.5,0.9]`·`[0.5,0.9,0.5]` 순열 전부에서 올바르게 판정.

## V-4. 상태 만료 정상 경로
- 중독: 밤 n 부여 → `{kind:'night', n:n+1}` → 밤 n+1 시작 시 자동 해제 확인.
- 보호: 밤 n 부여 → `{kind:'day', n:n}` → 낮 n 시작 시 자동 해제 확인(밤→낮→밤 왕복 검증).
- 주인/저주/광기: 부여 시 기존 동종 토큰을 전원에서 제거한 뒤 1개만 유지(index.html:1636, 1677, 1679) — 정상.
- 같은 밤에 중독을 두 번 부여해도 만료 시점이 같아 다음 밤 시작 시 **양쪽 모두** 해제됨.
- (낮에 수동 부여한 보호만 예외 → M-1)

## V-5. 판정 자동화 정상 경로
| 시나리오 | 결과 |
|---|---|
| 군인 + 중독 상태에서 임프 공격 | 사망 처리 — 정상(공식 규칙 일치) |
| 시장 대체 사망(정상 대상 지정) | 시장 생존, 지정 대상 사망 — 정상 |
| 시장 대체 사망(대상 미발견) | "대상을 찾지 못해 시장 사망으로 처리합니다" 후 시장 사망 — 정상 |
| 좀버얼 첫 사망 | `fakedead` 부여 + 겉사망 + 경고 토스트 — 정상 (두 번째 사망은 H-2) |
| 팡 구 점프 2회 시도 | 1회차 `spent` 기록, 2회차 "대상이 없거나 이미 소진되었습니다" 거부 — 정상 |
| 찻집 여인 이웃 보호(시전자 정상 지정 시) | 살해 불발 + 은닉 안내 — 정상 (H-1의 전역 오염만 문제) |
| 성결자 발동 → 장의사 연계 | `executedToday`→`executedPrevDay` 전달, 밤 힌트에 "어제 처형: P3 (요리사) — 성결자 발동" 표시 — 정상 |
| 탕녀 오작동 시 계승 불발 안내 | 정상 (경계값 자체는 C-2) |

## V-6. 위저드 엔진 (씬 상태 오염 H-4 제외)
- 씬 중간에 `closeWiz(false)` 후 재시작: `wiz.vars={}`, `wiz.idx=0`으로 초기화 — 정상.
- `pick` 개수 초과 선택: `n=3`에 5개 클릭 시 FIFO로 밀려 항상 3개 유지(`wizTogglePick`, index.html:2835) — 정상.
- `effect` 대상 미선택: "대상이 선택되지 않았습니다 — 이전 단계에서 선택하세요." 토스트 후 진행 차단 — 정상.
- 능력 보유자가 사망해 `holder=null`인 상태로 위저드 실행: 제목·`wake` 씬 모두 널 가드 동작 — 정상.
- `ovOpen`(index.html:3423)의 위저드 진행 중 중복 오픈 차단 — 정상.

## V-7. XSS 전 화면 스윕
플레이어 이름·메모·게임 기록·`executedPrevDay`에 `<img src=x onerror=…>`를 심고 각 화면 렌더 후 실행 여부 측정:

| 화면 | 실행 |
|---|---|
| 타운스퀘어 / 그리모어(원탁) | 0 |
| 그리모어(카드) | 0 |
| 게임 기록(log) | 0 |
| 낮·투표 패널 | 0 |
| 지명 진행중(1단계 / 2단계) | 0 / 0 |
| 지명 결과 카드 | 0 |
| 플레이어 모달 | 0 |
| 밤 진행 시트 | 0 |
| 체크리스트 | 0 |
| 설정 | 0 |
| 리플레이 요약 | 0 |
| 캐릭터 변경 다이얼로그 | 0 |
| 캐릭터 확인 위저드 | 0 |
| **밤 위저드(제목)** | **1** → M-2 |

`esc()` 자체(index.html:836)는 `& < > " '` 5문자를 모두 처리하며 HTML 텍스트 컨텍스트에서는 완전하다.
결함은 `esc()`가 **부적합한 컨텍스트**(속성 안의 JS 문자열 — H-5, HTML 속성값 — M-3)에 쓰이거나 **아예 빠진 곳**(M-2)에 국한된다.

## V-8. 클라우드 저장 문서 정리 (모달 누락 M-4 제외)
- `.tabpane` 전체 `innerHTML` 비움 + `active` 제거 — 정상.
- `sidenav/subtabs/quickstats/wizhead/wizbody/wizfoot/log` 비움 — 정상.
- `#wizard` → `hidden=true`, `#wizbody` → 빈 문자열 확인.
- `#toast` 제거, 기존 `#cloudstate` 제거 후 재생성, `phaselabel` 초기화 — 정상.
- `</`를 `<\/`로 이스케이프해 `<script type="application/json">` 조기 종료 방지 — 정상.
- 모달을 닫은 상태의 스냅샷은 `<div id="pmodal" hidden=""></div>` 로 깨끗함.

---

## 부록 — 재현 환경

```
Chromium: /opt/pw-browsers/chromium (--no-sandbox)
Playwright: /opt/node22/lib/node_modules/playwright/index.mjs
URL: file:///home/user/phalanx/thyrsus/index.html
스텁: window.confirm → 항상 true(또는 window.__confirmAnswer),
      window.prompt  → window.__promptAnswer,
      window.alert   → 수집만
전처리: localStorage.clear(), file:// 이외 요청 abort(웹폰트 차단)
주의: 최상위 `let S` / `function` 선언은 `window.S` 가 아니라 전역 렉시컬 환경에 있으므로
      page.evaluate 안에서 `S`, `blank()`, `advancePhase()` 등을 **베어 식별자**로 호출해야 한다.
```

상태 주입 헬퍼(모든 시나리오 공통):
```js
S = blank(); S.edition = 'tb';               // 또는 'bmr' / 'sv'
chars.forEach((c,i)=>S.players.push({
  id:'p'+i, name:'P'+i, charId:c, alive:true, deadVote:true, statuses:[], notes:''}));
S.phase = {kind:'night', n:2};               // 또는 {kind:'day', n:1}
save(); renderAll();
```
