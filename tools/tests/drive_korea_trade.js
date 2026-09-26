/* korea_trade.html 드릴다운 브라우저 검증 (수동 — playwright 필요)
   ----------------------------------------------------------------
   shrink_korea_trade.py 로 줄인 페이지가 원본과 똑같이 그려지는지 확인한다.
   원본과 축소본을 각각 열어 같은 드릴다운 3종을 펼치고 텍스트를 비교한다:
     1) 급등·급락 표 첫 행 펼침 (최신월)
     2) 월 선택을 최신월이 아닌 달로 바꾼 뒤 다시 펼침
        — "최신월만 남기면 된다"는 오판을 잡는 회귀 테스트다
     3) 분류 탭에서 HS6까지 내려가 행 펼침

     npm i playwright
     mkdir orig && cp korea_trade.html orig/
     mkdir new  && cp korea_trade.html new/ && python3 tools/shrink_korea_trade.py new/korea_trade.html
     node tools/tests/drive_korea_trade.js orig > a.json
     node tools/tests/drive_korea_trade.js new  > b.json
     diff a.json b.json        # 비어야 한다

   2026-09-21 실행 결과: 3종 전부 문자 단위로 일치. */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');

const DIR = process.argv[2];
const TYPES = { '.html':'text/html', '.json':'application/json' };

function serve(root){
  return new Promise(res=>{
    const s = http.createServer((req,rs)=>{
      const p = path.join(root, decodeURIComponent(req.url.split('?')[0]));
      if(!p.startsWith(root) || !fs.existsSync(p) || fs.statSync(p).isDirectory()){
        rs.writeHead(404); return rs.end('nf'); }
      rs.writeHead(200, {'content-type': TYPES[path.extname(p)] || 'text/plain'});
      fs.createReadStream(p).pipe(rs);
    }).listen(0, '127.0.0.1', () => res(s));
  });
}

(async () => {
  const srv = await serve(DIR);
  const port = srv.address().port;
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const page = await browser.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if(m.type()==='error') errs.push('console: ' + m.text()); });

  await page.goto(`http://127.0.0.1:${port}/korea_trade.html`, { waitUntil: 'networkidle' });

  const out = { errs };

  /* 1) 랭킹 표 첫 행을 펼쳐 수출국별 막대의 라벨+값을 읽는다 */
  await page.waitForSelector('#body tr.dat', { timeout: 15000 });
  out.hs = await page.$eval('#body tr.dat td.hs', e => e.textContent.trim());
  await page.click('#body tr.dat');
  await page.waitForSelector('tr.exprow', { timeout: 15000 });
  await page.waitForFunction(() => {
    const b = document.querySelector('tr.exprow');
    return b && b.textContent.includes('수출국별');
  }, null, { timeout: 15000 });
  await page.waitForTimeout(400);
  out.rank = await page.$eval('tr.exprow', e => e.innerText.replace(/\s+/g,' ').trim().slice(0,400));

  /* 2) 월을 바꿔도 드릴다운이 살아 있나 — 최신월이 아닌 달 */
  const months = await page.$$eval('#month option', os => os.map(o => o.value));
  out.months = months.length;
  const older = months[months.length - 3];
  out.older = older;
  await page.selectOption('#month', older);
  await page.waitForTimeout(300);
  await page.click('#body tr.dat');
  await page.waitForSelector('tr.exprow', { timeout: 15000 });
  await page.waitForTimeout(400);
  out.rankOld = await page.$eval('tr.exprow', e => e.innerText.replace(/\s+/g,' ').trim().slice(0,400));

  /* 3) 분류 탭에서 HS6까지 내려가 행을 펼친다 */
  await page.evaluate(() => { switchTab('browse'); brGo(0,null,null); });
  await page.waitForTimeout(300);
  await page.evaluate(() => { const c = document.querySelector('#brbody .ovc'); if(c) c.click(); });
  await page.waitForTimeout(300);
  await page.evaluate(() => { const r = document.querySelector('#brbody tr.dat'); if(r) r.click(); });
  await page.waitForTimeout(300);
  out.browseHs = await page.evaluate(() => {
    const r = document.querySelector('#brbody tr.dat'); return r ? r.innerText.split('\n')[0] : null; });
  await page.evaluate(() => { const r = document.querySelector('#brbody tr.dat'); if(r) r.click(); });
  await page.waitForFunction(() => {
    const b = document.querySelector('#brbody tr.exprow');
    return b && b.textContent.includes('수출국별');
  }, null, { timeout: 15000 }).catch(()=>{});
  await page.waitForTimeout(500);
  out.browse = await page.evaluate(() => {
    const e = document.querySelector('#brbody tr.exprow');
    return e ? e.innerText.replace(/\s+/g,' ').trim().slice(0,400) : null; });

  await browser.close(); srv.close();
  console.log(JSON.stringify(out, null, 1));
})().catch(e => { console.error('HARNESS FAIL', e); process.exit(1); });
