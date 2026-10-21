/* Dependency-free synthetic DOM/transport tests. No browser layout claim. */
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const rootPath = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(rootPath, 'ui/patch.js'), 'utf8');
const marker = '/* NEBIUS CUSTOMER RELATIONSHIP MAP';
assert(source.includes(marker));
const code = source.slice(source.indexOf(marker));
const spotCode = source.slice(source.indexOf('/* Nebius GPU spot tracker'), source.indexOf(marker));
const prefix = 'data/nebius_relationships/';
const hash = text => createHash('sha256').update(text).digest('hex');
const clone = x => JSON.parse(JSON.stringify(x));
const canonical = value => {
  const ordered = item => Array.isArray(item) ? item.map(ordered) :
    item && typeof item === 'object' ? Object.fromEntries(Object.keys(item).sort().map(key => [key, ordered(item[key])])) : item;
  return JSON.stringify(ordered(value), null, 2) + '\n';
};
const reviewed = JSON.parse(fs.readFileSync(path.join(rootPath, 'data/nebius_relationships/reviewed.json'), 'utf8'));
const actualIndexText = fs.readFileSync(path.join(rootPath, prefix, 'index.json'), 'utf8');
const actualIndex = JSON.parse(actualIndexText);
const actualShardText = fs.readFileSync(path.join(rootPath, prefix, actualIndex.shards[0].path), 'utf8');
const seed = clone(reviewed.records);
seed[0].name += ' <script>alert(1)</script>';
seed[0].summary_ko += ' <img src=x onerror="globalThis.pwned=1"> & literal text';
seed[0].source.title = '<script>pwned=1</script>';
function setup(options = {}) {
  let mutationQueued = false;
  const observers = [], timers = new Set();
  const stats = {requests:[], reads:0, cancels:0, warnings:[], renders:0};
  function mutation() {
    if (mutationQueued || !observers.length) return;
    mutationQueued = true; queueMicrotask(() => {mutationQueued = false; observers.forEach(fn => fn());});
  }
  class Element {
    constructor(tag) { this.tagName=tag;this.children=[];this.parentNode=null;this.attributes={};this.className='';this._text='';this.value='';this.style={setProperty(){}};this.classList={contains:c=>this.className.split(' ').includes(c)}; }
    get textContent(){return this._text+this.children.map(n=>n.textContent).join(' ');}
    set textContent(s){this.replaceChildren();this._text=String(s);}
    set innerHTML(_){throw Error('HTML interpolation forbidden');}
    get isConnected(){return this.tagName==='body'||!!(this.parentNode&&this.parentNode.isConnected);}
    get nextSibling(){return this.parentNode?this.parentNode.children[this.parentNode.children.indexOf(this)+1]||null:null;}
    appendChild(n){return this.insertBefore(n,null);}
    insertBefore(n,a){if(n===a)return n;if(n.parentNode)n.remove();const i=a?this.children.indexOf(a):this.children.length;assert(i>=0);this.children.splice(i,0,n);n.parentNode=this;mutation();return n;}
    remove(){if(this.parentNode){const p=this.parentNode;p.children.splice(p.children.indexOf(this),1);this.parentNode=null;mutation();}}
    replaceChildren(...nodes){this.children.forEach(n=>n.parentNode=null);this.children=[];this._text='';nodes.forEach(n=>this.appendChild(n));mutation();}
    setAttribute(k,v){this.attributes[k]=String(v);}
    removeAttribute(k){delete this.attributes[k];}
    querySelectorAll(s){return this.children.flatMap(n=>[(s.startsWith('.')?n.classList.contains(s.slice(1)):n.tagName===s)?n:null,...n.querySelectorAll(s)]).filter(Boolean);}
    querySelector(s){return this.querySelectorAll(s)[0]||null;}
  }
  const body=new Element('body'), main=new Element('main'), root=new Element('div');root.className='nc';body.appendChild(main);main.appendChild(root);
  function render(...args){stats.renders++;stats.receiver=this;stats.args=args;if(options.throwRender)throw options.throwRender;const head=new Element('div');head.className='nc-head';root.replaceChildren(head);return options.returnValue||'normal';}
  render.feature=true; Object.defineProperty(render,'hidden',{value:42});const symbol=Symbol('prop');render[symbol]='symbol';render();
  const rows=clone(options.rows||seed);
  const shard=canonical({dataset:'nebius-relationships',record_count:rows.length,records:rows,schema_version:options.shardVersion||1});
  const sha=hash(shard), shardBytes=Buffer.byteLength(shard), shardPath='shards/'+sha+'.json';
  const manifest=options.manifest||{dataset:'nebius-relationships',record_count:rows.length,schema_version:1,
    shards:rows.length?[{bytes:shardBytes,path:shardPath,record_count:rows.length,sha256:sha}]:[],
    source:{bytes:shardBytes,path:'reviewed.json',record_count:rows.length,sha256:sha}};
  if(options.mutate)options.mutate(manifest);
  const context={console:{warn:(...x)=>stats.warnings.push(x)},URL,AbortController,TextDecoder,TextEncoder,Uint8Array,crypto:options.noCrypto?null:webcrypto,
    location:{href:'https://phalanx.test/project/index.html',origin:'https://phalanx.test'},
    setTimeout:(fn,ms)=>{const id=setTimeout(()=>{timers.delete(id);fn();},ms);timers.add(id);return id;},clearTimeout:id=>{clearTimeout(id);timers.delete(id);},
    MutationObserver:class{constructor(fn){this.fn=fn;}observe(){observers.push(this.fn);}},
    document:{body,documentElement:new Element('html'),readyState:'complete',createElement:t=>new Element(t),querySelectorAll:s=>s==='#main .nc'?main.querySelectorAll('.nc'):body.querySelectorAll(s)},
    renderAI2:render, renderNeocloud:render, featureFlag:'unchanged',
    fetch:async(url,opts)=>{
      stats.requests.push(url);assert.equal(opts.credentials,'omit');assert.equal(opts.redirect,'error');assert.equal(opts.referrerPolicy,'no-referrer');assert(opts.signal);
      if(options.offline||!url.includes(prefix))throw Error('offline synthetic transport');
      if(options.delay)await new Promise(r=>setTimeout(r,options.delay));
      const isIndex=url.endsWith('/index.json');
      let payload=isIndex?(options.rawIndex||canonical(manifest)):(options.rawShard||shard);
      if(!isIndex&&options.badHash)payload=payload.replace('nebius-relationships','nebius-relatiOnships');
      if(isIndex&&options.duplicateIndex)payload=payload.replace('  "record_count": '+rows.length, '  "record_count": '+rows.length+',\n  "record_count": '+rows.length);
      if(!isIndex&&options.duplicateShard)payload=payload.replace('  "record_count": '+rows.length, '  "record_count": '+rows.length+',\n  "record_count": '+rows.length);
      const bytes=new TextEncoder().encode(payload);let done=false;
      return {ok:true,url:options.redirect||url,headers:{get:()=>options.largeHeader?'99999999':null},body:{getReader:()=>({
        read:async()=>{stats.reads++;if(done)return {done:true};done=true;return {done:false,value:options.largeBody?new Uint8Array(5242881):bytes};},
        cancel:async()=>{stats.cancels++;}
      })}};
    }
  };context.window=context;
  vm.createContext(context);if(options.coexist)vm.runInContext(spotCode,context);vm.runInContext(code,context);
  return {context,root,main,stats,symbol,Element,manifest, panel:()=>root.querySelector('.ncm-panel'),
    dispose:()=>{observers.length=0;timers.forEach(clearTimeout);timers.clear();}};
}
const tick=()=>new Promise(r=>setTimeout(r,40));
const controls=e=>({query:e.panel().querySelector('input'),selects:e.panel().querySelectorAll('select'),reset:e.panel().querySelector('button')});
const cards=e=>e.panel().querySelectorAll('.ncm-card');
let passed=0;
async function test(name,fn){await fn();passed++;console.log('PASS '+name);}
async function withEnv(options,fn){const e=setup(options);try{await tick();await fn(e);}finally{e.dispose();}}
(async()=>{
  await test('loading then verified render, literal text, scope and UNKNOWN',async()=>{
    const e=setup({delay:25});try{await new Promise(r=>setTimeout(r,5));assert.equal(e.panel().attributes['data-state'],'loading');await new Promise(r=>setTimeout(r,90));assert.equal(cards(e).length,2);
      assert(e.panel().textContent.includes(seed[0].summary_ko));assert(e.panel().textContent.includes(seed[0].name));assert.equal(e.panel().querySelectorAll('script').length,0);assert.equal(e.panel().querySelectorAll('img').length,0);assert(!e.context.pwned);
      assert(!e.panel().textContent.includes(seed[0].source.title));assert(e.panel().textContent.includes('전체 고객 목록이 아닙니다'));assert(e.panel().textContent.includes('서비스 가동 상태: 미확인 (UNKNOWN)'));assert(e.panel().textContent.includes('근거 분류: 공급자 1차 출처'));assert(e.panel().textContent.includes('공개 분류: Nebius 공개'));
      assert(e.panel().textContent.includes('출처 발행: 260316'));assert(!e.panel().textContent.includes('2026-10-21'));
      assert.equal(e.panel().attributes['aria-busy'],undefined);assert.equal(e.stats.requests.length,2);assert(e.stats.requests.every(u=>u.startsWith('https://phalanx.test/project/'+prefix)));
    }finally{e.dispose();}
  });
  await test('generated index and declared shard bytes pass the production loader',()=>withEnv({
    rows:clone(reviewed.records),rawIndex:actualIndexText,rawShard:actualShardText
  },async e=>{
    assert.equal(e.panel().attributes['data-state'],'ready');assert.equal(cards(e).length,2);assert.equal(e.stats.requests.length,2);
  }));
  await test('search, each filter, combined no-result, reset and visible count',()=>withEnv({},async e=>{
    const c=controls(e);c.query.value='  META ';c.query.oninput();assert.equal(cards(e).length,1);assert(e.panel().querySelector('.ncm-count').textContent.startsWith('1개'));
    c.reset.onclick();for(const [i,value,count] of [['0','HYPERSCALER',1],['1','AI_INFRASTRUCTURE',2],['2','AI_COMPUTE_UNSPECIFIED',2],['3','NEBIUS_ANNOUNCED',2]]){c.selects[Number(i)].value=value;c.selects[Number(i)].onchange();assert.equal(cards(e).length,count);c.reset.onclick();}
    c.query.value='Meta';c.query.oninput();c.selects[0].value='HYPERSCALER';c.selects[0].onchange();assert.equal(cards(e).length,0);assert(e.panel().textContent.includes('조건에 맞는 관계가 없습니다'));c.reset.onclick();assert.equal(cards(e).length,2);assert.equal(c.query.value,'');
    assert.equal(e.panel().querySelectorAll('label').length,5);
  }));
  await test('evidence links are safe and never fetched; timeline newest first',()=>withEnv({},async e=>{
    for(const a of e.panel().querySelectorAll('a')){assert.equal(a.attributes.target,'_blank');assert.equal(a.attributes.rel,'noopener noreferrer');assert(a.attributes['aria-label'].endsWith('(새 창)'));assert(a.attributes.href.startsWith('https://nebius.com/'));}
    const changes=e.panel().querySelectorAll('.ncm-change');assert(changes[0].textContent.startsWith('260316'));assert(changes[1].textContent.startsWith('250908'));assert(!e.stats.requests.some(u=>new URL(u).hostname==='nebius.com'));
  }));
  await test('reject all unsafe manifest paths before shard fetch',async()=>{
    const bad=['https://phalanx.test/'+prefix+'shards/a.json','https://evil.test/x','//evil.test/x','/data/nebius_relationships/x','../x',prefix+'shards/../index.json',prefix+'shards/%2e%2e/x',prefix+'shards/%2fsecret.json',prefix+'shards/%5csecret.json',prefix+'shards/%252fsecret.json',prefix+'shards/a.json?x',prefix+'shards/a.json#x',prefix+'shards\\x.json','data/neocloud_spot/index.json'];
    for(const badPath of bad)await withEnv({mutate:m=>m.shards[0].path=badPath},async e=>{assert.equal(e.panel().attributes['data-state'],'integrity');assert.equal(e.stats.requests.length,1);assert.equal(cards(e).length,0);});
  });
  await test('reject unsafe evidence URLs without fetching them',async()=>{
    for(const url of ['javascript:alert(1)','http://nebius.com/a','https://NEBIUS.COM/a','https://nebius.com:443/a','https://nebius.com?x','https://nebius.com#x','https://nebius.com.evil/a','https://nebius.com@evil.test/a','https://user@nebius.com/a','https://nebius.com:444/a','https://nebius.com/\\evil']){
      const rows=clone(seed);rows[0].source.url=url;await withEnv({rows},async e=>{assert.equal(e.panel().attributes['data-state'],'integrity');assert.equal(cards(e).length,0);assert.equal(e.stats.requests.length,2);});
    }
  });
  await test('hash failure, crypto absence, redirected response and byte bounds fail closed',async()=>{
    for(const opt of [{badHash:true},{noCrypto:true},{redirect:'https://evil.test/x'},{largeHeader:true}])await withEnv(opt,async e=>{assert.equal(e.panel().attributes['data-state'],'integrity');assert.equal(cards(e).length,0);});
    await withEnv({largeBody:true},async e=>{assert.equal(e.panel().attributes['data-state'],'integrity');assert.equal(cards(e).length,0);assert.equal(e.stats.cancels,1);});
  });
  await test('count limits, duplicate records and inconsistent display dates',async()=>{
    for(const mutate of [m=>m.record_count=3,m=>m.shards[0].record_count++,m=>m.shards[0].bytes++,m=>m.shards.push(m.shards[0])])await withEnv({mutate},async e=>assert.equal(e.panel().attributes['data-state'],'integrity'));
    for(const mutate of [r=>r.push(r[0]),r=>r[1].id=r[0].id,r=>r[0].display_date='261099',r=>r[0].event_date='2026-02-30',r=>r.reverse()]){const rows=clone(seed);mutate(rows);await withEnv({rows},async e=>assert.equal(e.panel().attributes['data-state'],'integrity'));}
  });
  await test('strict v1 keys, enums, source bindings, canonical JSON and safe text',async()=>{
    for(const mutate of [m=>m.extra=true,m=>m.dataset='other',m=>m.source.path='../reviewed.json',m=>m.source.bytes++,m=>m.source.sha256='a'.repeat(64)])await withEnv({mutate},async e=>assert.equal(e.panel().attributes['data-state'],'integrity'));
    for(const mutate of [r=>r[0].extra=true,r=>r[0].delivery_mode='DEDICATED_AND_RESALE',r=>r[0].source.extra=true,r=>r[0].source.provider_terms_apply=false,r=>r[0].source.updated='2025-01-01T00:00:00Z',r=>{r[0].source.updated='2026-10-05T11:21:16.000900Z';r[0].source.collected='2026-10-05T11:21:16.000100Z';},r=>r[0].source.published='0000-03-16T00:00:00Z',r=>r[0].name+='\ud800',r=>r[0].name='😀'.repeat(4097)]){
      const rows=clone(seed);mutate(rows);await withEnv({rows},async e=>assert.equal(e.panel().attributes['data-state'],'integrity'));
    }
    const unicodeRows=clone(seed);unicodeRows[0].name='😀'.repeat(4096);
    await withEnv({rows:unicodeRows},async e=>assert.equal(e.panel().attributes['data-state'],'ready'));
    for(const opt of [{duplicateIndex:true},{duplicateShard:true},{rawShard:'{}\n'},{rawIndex:'\ufeff'+canonical({})}])await withEnv(opt,async e=>assert.equal(e.panel().attributes['data-state'],'integrity'));
    await withEnv({rawIndex:'{}\n'},async e=>assert.equal(e.panel().attributes['data-state'],'schema'));
  });
  await test('empty drift, unavailable with retry, unsupported manifest and shard schema',async()=>{
    await withEnv({rows:[]},async e=>{assert.equal(e.panel().attributes['data-state'],'integrity');assert.equal(cards(e).length,0);});
    const retryOptions={offline:true};
    await withEnv(retryOptions,async e=>{assert.equal(e.panel().attributes['data-state'],'unavailable');retryOptions.offline=false;e.panel().querySelector('button').onclick();await tick();assert.equal(e.panel().attributes['data-state'],'ready');assert.equal(e.stats.requests.length,3);assert.equal(e.root.querySelectorAll('.ncm-panel').length,1);});
    for(const opt of [{mutate:m=>m.schema_version=99},{shardVersion:99}])await withEnv(opt,async e=>{assert.equal(e.panel().attributes['data-state'],'schema');assert.equal(cards(e).length,0);});
  });
  await test('coalesced mutation/mount, multi-root, cached rerender and preserved function properties',()=>withEnv({},async e=>{
    const api=e.context.PHXNebiusCustomers, wrapped=e.context.renderAI2;assert.equal(wrapped.feature,true);assert.equal(wrapped.hidden,42);assert.equal(wrapped[e.symbol],'symbol');assert.equal(e.context.featureFlag,'unchanged');
    for(let i=0;i<30;i++)api.mount();vm.runInContext(code,e.context);await tick();assert.equal(e.context.PHXNebiusCustomers,api);assert.equal(e.context.renderAI2,wrapped);assert.equal(e.root.querySelectorAll('.ncm-panel').length,1);assert.equal(e.stats.requests.length,2);
    const receiver={test:true};assert.equal(wrapped.call(receiver,'prop',17),'normal');await tick();assert.equal(e.stats.receiver,receiver);assert.deepEqual(e.stats.args,['prop',17]);assert.equal(cards(e).length,2);assert.equal(e.stats.requests.length,2);
    const other=new e.Element('div');other.className='nc';e.main.appendChild(other);await tick();assert.equal(other.querySelectorAll('.ncm-panel').length,1);assert.equal(e.stats.requests.length,2);assert.equal(e.stats.warnings.length,0);
    assert.equal(e.root.children[1],e.panel());
  }));
  await test('wrapper preserves exact return values and exceptions',async()=>{
    const sentinel={value:1};await withEnv({returnValue:sentinel},async e=>assert.equal(e.context.renderAI2(),sentinel));
    await withEnv({},async e=>{const error=Error('original failure');function broken(){throw error;}e.context.renderAI2=broken;e.context.PHXNebiusCustomers.mount();await tick();assert.throws(()=>e.context.renderAI2(),x=>x===error);});
  });
  await test('actual GPU module coexists before and after rerender; late spot anchor moves panel',async()=>{
    await withEnv({coexist:true},async e=>{assert(e.context.PHXNeoCloudSpot);assert.equal(cards(e).length,2);assert.equal(e.root.querySelectorAll('.ncs-tracker').length,1);assert.equal(e.root.querySelector('.ncs-tracker').nextSibling,e.panel());assert.equal(e.context.renderNeocloud(),'normal');await tick();assert.equal(e.root.querySelectorAll('.ncs-tracker').length,1);assert.equal(e.root.querySelectorAll('.ncm-panel').length,1);assert.equal(e.root.querySelector('.ncs-tracker').nextSibling,e.panel());assert.equal(e.stats.requests.filter(u=>u.includes(prefix)).length,2);});
    await withEnv({},async e=>{const panel=e.panel(),spot=new e.Element('section');spot.className='ncs-tracker';e.root.appendChild(spot);await tick();assert.equal(spot.nextSibling,panel);assert.equal(e.root.querySelectorAll('.ncm-panel').length,1);});
  });
  await test('scoped CSS and mobile structural contract',async()=>{
    const css=fs.readFileSync(path.join(rootPath,'ui/patch.css'),'utf8').split(marker+' */')[1];assert(css);
    assert(css.includes('@media(max-width:720px)'));assert(css.includes('@media(max-width:420px)'));assert(css.includes('minmax(0,1fr)'));assert(css.includes('overflow-wrap:anywhere'));assert(css.includes(':focus-visible'));assert(css.includes('var(--a2,#3d8bfd)'));
    for(const selector of css.matchAll(/([^{}]+)\{/g)){const s=selector[1].trim();if(s.startsWith('@media'))continue;assert(s.split(',').every(x=>x.trim().startsWith('.ncm-')),s);}
    assert(!code.includes('innerHTML'));assert(!code.includes('fetch(r.source'));assert(!spotCode.includes('PHXNebiusCustomers'));
  });
  console.log(passed+' Nebius DOM/static tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
