/* Dependency-free minimal DOM harness; no real browser/layout coverage claimed. */
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const ROOT = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(ROOT, 'ui/patch.js'), 'utf8');
const code = source.slice(source.indexOf('/* Nebius GPU spot tracker'));
const seed = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/neocloud_spot/history.json'), 'utf8'));
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
const tick = () => new Promise(resolve => setTimeout(resolve, 15));
function setup({data = seed, fail = false, chart = false} = {}) {
  const body = new Element('body'), main = new Element('main'), root = new Element('div'), overview = new Element('div');
  root.className = 'nc'; overview.className = 'nc-panel'; body.appendChild(main); main.appendChild(root);
  function render() { const head = new Element('div'), method = new Element('div'); head.className = 'nc-head'; method.className = 'nc-panel'; root.replaceChildren(head, overview, method); return 'normal'; }
  render();
  const stats = {fetches: 0, created: 0, destroyed: 0, fail};
  const document = {body, documentElement: new Element('html'), readyState: 'complete', createElement: t => new Element(t), createElementNS: (_, t) => new Element(t), querySelectorAll: s => s === '#main .nc' ? main.querySelectorAll('.nc') : body.querySelectorAll(s)};
  const context = {document, console, setTimeout, clearTimeout, getComputedStyle: () => ({color: '#eee'}), fetch: async url => { assert.equal(url, 'data/neocloud_spot/history.json'); stats.fetches++; if (stats.fail) throw Error('offline'); return {ok: true, text: async () => JSON.stringify(data)}; }, renderAI2: render, renderNeocloud: render};
  context.window = context;
  if (chart) context.Chart = function (_, config) { stats.created++; stats.config = config; this.destroy = () => stats.destroyed++; };
  vm.createContext(context); vm.runInContext(code, context);
  return {context, root, overview, main, stats, panel: () => root.querySelector('.ncs-tracker')};
}
(async () => {
  let count = 0;
  async function test(name, fn) { await fn(); count++; console.log('PASS ' + name); }
  await test('static contract', () => {
    for (const token of ['renderAI2', 'renderNeocloud', 'data/neocloud_spot/history.json', 'GPU spot 데이터 미로드', 'user_supplied_chart_image', '공식 Nebius API 피드 아님', 'B300', 'B200', 'H200', 'H100', 'RTX PRO 6000']) assert(source.includes(token), token);
    assert(fs.readFileSync(path.join(ROOT, 'ui/patch.css'), 'utf8').includes(':root[data-theme="light"] .ncs-tracker'));
  });
  await test('five exact rendered endpoint labels, provenance, placement and SVG', async () => {
    const e = setup(); await tick(); const cards = e.panel().querySelectorAll('.ncs-card'); assert.equal(cards.length, 5);
    ['B300 $8.16', 'B200 $3.92', 'H200 $1.87', 'H100 $0.79', 'RTX PRO 6000 $1.18'].forEach((s, i) => assert(cards[i].textContent.includes(s), s));
    assert(e.panel().textContent.includes('260919–261020')); assert(e.panel().textContent.includes('user_chart_261020.jpg'));
    assert.equal(e.panel().querySelectorAll('svg').length, 1); assert.equal(e.panel().querySelectorAll('circle').length, 5);
    assert.equal(e.root.children[e.root.children.indexOf(e.overview) + 1], e.panel());
  });
  await test('repeat mount and render idempotency', async () => {
    const e = setup(); await tick(); e.context.PHXNeoCloudSpot.mount(); e.context.PHXNeoCloudSpot.mount(); await tick(); assert.equal(e.root.querySelectorAll('.ncs-tracker').length, 1);
    assert.equal(e.context.renderAI2(), 'normal'); await tick(); assert.equal(e.root.querySelectorAll('.ncs-tracker').length, 1); assert.equal(e.stats.fetches, 1);
  });
  await test('fetch failure and retry', async () => {
    const e = setup({fail: true}); await tick(); assert(e.panel().textContent.includes('GPU spot 데이터 미로드')); assert.equal(e.root.children.length, 4);
    e.stats.fail = false; e.panel().querySelector('button').onclick(); await tick(); assert(e.panel().textContent.includes('$8.16')); assert.equal(e.stats.fetches, 2);
  });
  await test('conflicting duplicate fails closed', async () => {
    const data = structuredClone(seed); data.observations.push({...data.observations[0], price: 99}); const e = setup({data}); await tick();
    assert(e.panel().textContent.includes('GPU spot 데이터 미로드')); assert.equal(e.panel().querySelectorAll('.ncs-card').length, 0);
  });
  await test('identical duplicate accepted once', async () => {
    const data = structuredClone(seed); data.observations.push(structuredClone(data.observations[0])); const e = setup({data}); await tick(); assert.equal(e.panel().querySelectorAll('circle').length, 5);
  });
  await test('Chart.js path and disposal', async () => {
    const e = setup({chart: true}); await tick(); assert.equal(e.stats.created, 1); assert.equal(e.stats.config.data.datasets.length, 5);
    const observed = Date.parse('2026-10-20T00:00:00Z'), day = 86400000;
    assert.equal(e.stats.config.options.scales.x.min, observed - day);
    assert.equal(e.stats.config.options.scales.x.max, observed + day);
    assert.equal(e.stats.config.options.scales.x.ticks.stepSize, day);
    assert.equal(e.stats.config.options.scales.y.min, 0);
    assert.equal(e.stats.config.options.plugins.vizScale.axes.y.class, 'zero_anchored');
    assert.equal(e.stats.config.options.plugins.vizScale.axes.y.unit, 'USD/GPU-hour');
    e.context.renderNeocloud(); await tick(); assert.equal(e.stats.destroyed, 1); assert.equal(e.stats.created, 2);
    e.main.replaceChildren(); e.context.PHXNeoCloudSpot.mount(); await tick(); assert.equal(e.stats.destroyed, 2);
  });
  await test('Chart.js failure falls back', async () => {
    const e = setup(); e.context.Chart = function () { throw Error('unsupported'); }; await tick(); assert.equal(e.panel().querySelectorAll('svg').length, 1);
  });
  await test('approximation uncertainty remains visible', async () => {
    const data = structuredClone(seed); data.observations[0].quality = 'approximate_from_chart'; data.observations[0].uncertainty = .1;
    const e = setup({data, chart: true}); await tick(); assert(e.panel().textContent.includes('≈$')); assert(e.panel().textContent.includes('±$0.10')); assert.equal(e.stats.created, 0); assert.equal(e.panel().querySelectorAll('svg').length, 1);
  });
  await test('missing prices never turn into zeros', async () => {
    const data = structuredClone(seed); data.observations.forEach(r => { delete r.price; r.quality = 'missing'; }); const e = setup({data}); await tick();
    assert(e.panel().textContent.includes('관측값 없음')); assert(!e.panel().textContent.includes('$0.00'));
  });
  await test('absent days are explicit chart gaps', async () => {
    const data = structuredClone(seed), earlier = structuredClone(data.observations[0]); earlier.effective_date = '2026-10-18'; data.observations.push(earlier);
    const e = setup({data, chart: true}); await tick();
    const series = e.stats.config.data.datasets.find(d => d.label === earlier.product);
    assert.equal(series.data.length, 3); assert.equal(series.data[1].y, null); assert.equal(series.spanGaps, false);
  });
  await test('provenance-conflicting duplicate is unavailable', async () => {
    const data = structuredClone(seed), other = structuredClone(data.observations[0]); other.provenance.source_file = 'other.png'; data.observations.push(other);
    const e = setup({data}); await tick(); assert(e.panel().textContent.includes('GPU spot 데이터 미로드'));
  });
  await test('JS schema validation', () => {
    const e = setup();
    for (const change of [r => r.price = -1, r => r.price = true, r => r.product = 'A100', r => r.effective_date = '2026-02-30', r => r.provenance.source_type = 'official_api', r => r.provenance.captured_date = '261019']) {
      const data = structuredClone(seed); change(data.observations[0]); assert.throws(() => e.context.PHXNeoCloudSpot.validate(data));
    }
    for (const key of ['currency', 'unit', 'cadence']) { const data = structuredClone(seed); data[key] = 'bad'; assert.throws(() => e.context.PHXNeoCloudSpot.validate(data)); }
    const unicode = structuredClone(seed); unicode.observations[0].provenance.source_file = '😀'.repeat(251) + '.jpg';
    assert.doesNotThrow(() => e.context.PHXNeoCloudSpot.validate(unicode));
    unicode.observations[0].provenance.source_file = '😀'.repeat(252) + '.jpg';
    assert.throws(() => e.context.PHXNeoCloudSpot.validate(unicode));
  });
  console.log(`${count} DOM/static contract tests passed`);
})().catch(error => { console.error(error); process.exitCode = 1; });
