/* Dependency-free minimal DOM harness; no real browser/layout coverage claimed. */
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const ROOT = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(ROOT, 'ui/patch.js'), 'utf8');
const code = source.slice(source.indexOf('/* Nebius GPU spot tracker'));
const seed = JSON.parse(fs.readFileSync(path.join(ROOT, 'tools/tests/fixtures/neocloud_spot/archive/index.json'), 'utf8'));
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.parentNode = null; this.attributes = {}; this._text = ''; this.className = ''; this.style = {setProperty() {}}; this.classList = {contains: s => this.className.split(' ').includes(s)}; }
  get textContent() { return this._text + this.children.map(n => n.textContent).join(' '); }
  set textContent(s) { this.replaceChildren(); this._text = String(s); }
  get isConnected() { return this.tagName === 'body' || !!(this.parentNode && this.parentNode.isConnected); }
  get nextSibling() { return this.parentNode ? this.parentNode.children[this.parentNode.children.indexOf(this) + 1] || null : null; }
  appendChild(n) { this.children.push(n); n.parentNode = this; return n; }
  insertBefore(n, a) { if (!a) return this.appendChild(n); this.children.splice(this.children.indexOf(a), 0, n); n.parentNode = this; return n; }
  replaceChildren(...nodes) { this.children.forEach(n => n.parentNode = null); this.children = []; this._text = ''; nodes.forEach(n => this.appendChild(n)); }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  removeAttribute(k) { delete this.attributes[k]; }
  querySelectorAll(s) { return this.children.flatMap(n => [(s.startsWith('.') ? n.classList.contains(s.slice(1)) : n.tagName === s) ? n : null, ...n.querySelectorAll(s)]).filter(Boolean); }
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
}
const tick = () => new Promise(resolve => setTimeout(resolve, 200));
const raw = () => ({snapshotTime:seed.snapshot_time,items:seed.current.map(r=>({skuId:r.sku_id,productTitle:r.product_title,region:r.region,computeInstance:{platform:r.platform},price:{value:r.price,currency:'usd',unitTitle:'GPU hour'},effectiveTime:r.effective_time}))});
function setup({data = seed, failArchive = false, failLive = true, chart = false, badShard = false, liveData = raw()} = {}) {
  const body = new Element('body'), main = new Element('main'), root = new Element('div'), overview = new Element('div');
  root.className='nc';overview.className='nc-panel';body.appendChild(main);main.appendChild(root);
  function render(){const head=new Element('div');head.className='nc-head';root.replaceChildren(head,overview);return 'normal';} render();
  const stats={requests:[],created:0,destroyed:0,failArchive,failLive};
  const document={body,documentElement:new Element('html'),readyState:'complete',createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t),querySelectorAll:s=>s==='#main .nc'?main.querySelectorAll('.nc'):body.querySelectorAll(s)};
  const context={document,console,setTimeout,clearTimeout,URL,AbortController,TextDecoder,TextEncoder,Uint8Array,crypto:require('node:crypto').webcrypto,location:{href:'https://phalanx.test/index.html',origin:'https://phalanx.test'},getComputedStyle:()=>({color:'#ccc'}),fetch:async(url,options)=>{
    stats.requests.push(url);assert.equal(options.credentials,'omit');assert.equal(options.referrerPolicy,'no-referrer');assert.equal(options.redirect,'error');assert(options.signal);
    let payload;
    if(url.startsWith('https://api.nebius.cloud/')){if(stats.failLive)throw Error('CORS/offline');payload=JSON.stringify(liveData);}
    else {if(stats.failArchive)throw Error('archive offline');payload=url.endsWith('index.json')?JSON.stringify(data):fs.readFileSync(path.join(ROOT,'tools/tests/fixtures/neocloud_spot/archive',url.replace('data/neocloud_spot/','')),'utf8');if(badShard&&!url.endsWith('index.json'))payload+=' ';}
    const bytes=new TextEncoder().encode(payload);let done=false;return {ok:true,url:new URL(url,context.location.href).href,body:{getReader:()=>({read:async()=>done?{done:true}:(done=true,{done:false,value:bytes}),cancel:async()=>{}})}};
  },renderAI2:render,renderNeocloud:render};context.window=context;
  if(chart)context.Chart=function(_,config){stats.created++;stats.config=config;this.destroy=()=>stats.destroyed++;};
  vm.createContext(context);vm.runInContext(code,context);
  return {context,root,main,stats,panel:()=>root.querySelector('.ncs-tracker')};
}
function selector(e,name){return e.panel().querySelectorAll('select').find(s=>s.attributes['aria-label']===name);}
(async()=>{
  let count=0;async function test(name,fn){await fn();count++;console.log('PASS '+name);}
  await test('static contract and scoped workflow',()=>{
    for(const token of ['renderAI2','renderNeocloud','data/neocloud_spot/','index.json','api.nebius.cloud','/list-series','GPU spot 데이터 미로드','B300','B200','H200','H100','RTX PRO 6000','https://nebius.com/spot-prices','https://docs.nebius.com/signup-billing/spot-prices','METHOD_LAST_PRICE','METHOD_AVG_PRICE','지역 / SKU','1d','7d','30d','전체 보관'])assert(code.includes(token),token);
    for(const token of ['history.json','legacy-user-chart','8.16','3.92','1.87','1.18'])assert(!code.includes(token),token);
    const wf=fs.readFileSync(path.join(ROOT,'.github/workflows/update-neocloud-spot.yml'),'utf8');
    for(const token of ['schedule:','workflow_dispatch:','contents: write','cancel-in-progress: false','git add -- data/neocloud_spot/index.json','git pull --rebase origin main'])assert(wf.includes(token));
    assert(!/git add (?:\.|-A|--all)/.test(wf));
  });
  await test('archive first five accessible cards with exact lowest price region',async()=>{
    const e=setup();await tick();const cards=e.panel().querySelectorAll('.ncs-card');assert.equal(cards.length,5);assert.equal(e.stats.requests[0],'data/neocloud_spot/index.json');
    ['B300','B200','H200','H100','RTX PRO 6000'].forEach((family,i)=>{const win=seed.current.filter(r=>r.family===family).sort((a,b)=>e.context.PHXNeoCloudSpot.compare(a.price,b.price)||a.region.localeCompare(b.region)||a.sku_id.localeCompare(b.sku_id))[0];if(win){assert(cards[i].textContent.includes('$'+win.price));assert(cards[i].textContent.includes(win.region));}assert(cards[i].textContent.includes(family));});
    assert(e.panel().textContent.includes('보관 폴백'));assert(e.panel().textContent.includes('공식 Nebius Spot Prices'));assert.equal(e.panel().querySelectorAll('select').length,4);
    assert.equal(e.root.children[1],e.panel());assert(e.panel().querySelector('svg'));
  });
  await test('rerender and duplicate mount preserve one panel and cached requests',async()=>{
    const e=setup();await tick();const n=e.stats.requests.length;e.context.PHXNeoCloudSpot.mount();e.context.PHXNeoCloudSpot.mount();await tick();assert.equal(e.root.querySelectorAll('.ncs-tracker').length,1);
    assert.equal(e.context.renderAI2(),'normal');await tick();assert.equal(e.root.querySelectorAll('.ncs-tracker').length,1);assert.equal(e.stats.requests.length,n);
    e.context.renderNeocloud();await tick();assert.equal(e.root.querySelectorAll('.ncs-tracker').length,1);
  });
  await test('live enhancement retains archive and exact effective time',async()=>{
    const d=raw();d.items[0].price.value='0.1234567890123456789';const e=setup({failLive:false,liveData:d});await tick();assert(e.panel().textContent.includes('실시간'));assert(e.panel().textContent.includes('$0.1234567890123456789'));assert(e.stats.requests.some(s=>s.startsWith('https://api.nebius.cloud/')));
  });
  await test('both sources fail then retry succeeds',async()=>{
    const e=setup({failArchive:true});await tick();assert(e.panel().textContent.includes('GPU spot 데이터 미로드'));e.stats.failArchive=false;e.panel().querySelector('button').onclick();await tick();assert.equal(e.panel().querySelectorAll('.ncs-card').length,5);
  });
  await test('archive failure allows live only cards',async()=>{
    const e=setup({failArchive:true,failLive:false});await tick();assert.equal(e.panel().querySelectorAll('.ncs-card').length,5);assert(e.panel().textContent.includes('보관 이력 미로드'));
  });
  await test('bad official currency falls back without breaking cards',async()=>{
    const d=raw();d.items[0].price.currency='eur';const e=setup({failLive:false,liveData:d});await tick();assert(e.panel().textContent.includes('보관 폴백'));assert.equal(e.panel().querySelectorAll('.ncs-card').length,5);
  });
  await test('hash failure leaves current fallback and labels missing history',async()=>{
    const e=setup({badShard:true});await tick();const method=selector(e,'이력 방법');method.value='METHOD_AVG_PRICE';method.onchange();const range=selector(e,'기간');range.value='all';range.onchange();await tick();assert(e.panel().textContent.includes('보관 이력 미로드'));assert.equal(e.panel().querySelectorAll('.ncs-card').length,5);
  });
  await test('AVG layer stays separate with full exact source table',async()=>{
    const e=setup();await tick();const method=selector(e,'이력 방법');method.value='METHOD_AVG_PRICE';method.onchange();const range=selector(e,'기간');range.value='all';range.onchange();await tick();assert(e.panel().textContent.includes('AVG_PRICE 가져오기'));assert(e.panel().querySelector('table'));assert(e.panel().querySelectorAll('tr').length>2);assert(e.panel().textContent.includes('현재 · 완료 구간 아님'));
  });
  await test('Chart rendering disposal and SVG fallback',async()=>{
    const e=setup({chart:true});await tick();assert(e.stats.created>0);assert.equal(e.stats.config.data.datasets[0].spanGaps,false);assert.equal(e.stats.config.data.datasets[1].showLine,false);
    const destroyed=e.stats.destroyed;e.context.renderNeocloud();await tick();assert(e.stats.destroyed>destroyed);e.main.replaceChildren();e.context.PHXNeoCloudSpot.mount();await tick();assert.equal(e.stats.created,e.stats.destroyed);
    const f=setup();f.context.Chart=function(){throw Error('unsupported');};await tick();assert(f.panel().querySelector('svg'));
  });
  await test('gap insertion never forward fills or fabricates zeroes',async()=>{
    const e=setup();await tick();const p=e.context.PHXNeoCloudSpot.gaps([{interval_end:'2026-10-20T01:00:00Z',price:'2'},{interval_end:'2026-10-20T03:00:00Z',price:'3'}]);assert.equal(p.length,3);assert.equal(p[1].y,null);assert.equal(p[0].y,2);
  });
  await test('strict parser duplicate keys invalid dates and precision comparison',async()=>{
    const e=setup();await tick();const api=e.context.PHXNeoCloudSpot;
    for(const s of ['{"a":1,"a":2}','{"a":{"b":1,"b":2}}','[NaN]'])assert.throws(()=>api.strictJSON(s));
    assert.equal(api.strictJSON('{"a":[1,true,null,"é"]}').a[3],'é');assert(api.compare('1.000000000000000001','1.000000000000000002')<0);
    for(const mutate of [d=>d.current[0].unit='CPU hour',d=>d.current[0].platform='unknown',d=>d.current[0].effective_time='2026-02-30T00:00:00Z',d=>d.current.push(d.current[0]),d=>d.schema_version=1,d=>d.shards[0].path='../secret']){const d=structuredClone(seed);mutate(d);assert.throws(()=>api.validate(d));}
  });
  await test('exact host allowlist rejects before fetch',async()=>{
    const e=setup();await tick();const n=e.stats.requests.length;
    for(const url of ['https://evil.test/','https://api.nebius.cloud.evil/','http://api.nebius.cloud/','https://user@api.nebius.cloud/','https://api.nebius.cloud:444/'])await assert.rejects(e.context.PHXNeoCloudSpot.request(url,true));
    assert.equal(e.stats.requests.length,n);
  });
  await test('light and mobile styles are confined to tracker',()=>{
    const css=fs.readFileSync(path.join(ROOT,'ui/patch.css'),'utf8');assert(css.includes(':root[data-theme="light"] .ncs-tracker'));assert(css.includes('@media(max-width:520px)'));assert(css.includes('.ncs-tracker .ncs-controls'));
  });
  console.log(`${count} DOM/static contract tests passed`);
})().catch(e=>{console.error(e);process.exitCode=1;});
