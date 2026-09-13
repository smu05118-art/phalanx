"""Run with Playwright/Chromium: python -m unittest discover -s argus/ui/tests -v."""
import functools
import http.server
from pathlib import Path
import threading
import unittest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
INDUSTRIES = ('ksemi','kship','kdef','knuke','kaero')


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass


class PartsExplorerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.p = sync_playwright().start()
        cls.browser = cls.p.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.p.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        self.errors=[]
        self.page.on('pageerror',lambda e:self.errors.append(str(e)))

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors,[])

    def open(self,name,hash=''):
        self.page.goto(self.base+f'/argus/{name}/parts.html'+hash)

    def select(self,name):
        target='#fab [data-stage=depo]' if name=='ksemi' else '#groups .chip'
        self.page.locator(target).first.click()

    def test_overview_stays_in_place_and_leaf_filters_companies(self):
        for name in INDUSTRIES:
            with self.subTest(industry=name):
                self.open(name)
                diagram=self.page.locator('.ig > div').first
                svg=diagram.locator('svg').first
                before=svg.bounding_box()
                self.select(name)
                self.assertGreater(self.page.locator('.px-leaf').count(),0)
                after=svg.bounding_box()
                self.assertEqual(before,after)
                left=diagram.bounding_box();right=self.page.locator('#panel').bounding_box()
                self.assertGreater(right['x'],left['x']+left['width'])
                leaf=self.page.locator('.px-leaf:not(.px-unverified)').first
                expected=int(leaf.locator('small').inner_text().removesuffix('사'))
                leaf.press('Enter')
                self.assertEqual(self.page.locator('.px-company').count(),expected)
                self.assertEqual(svg.bounding_box(),before)
                self.assertTrue(self.page.locator('.px-leaf[aria-pressed=true]').is_visible())
                search=self.page.locator('.px-search input')
                search.fill('UNMATCHED_TEST');self.assertEqual(self.page.locator('.px-company').count(),0)
                search.fill('');self.assertEqual(self.page.locator('.px-company').count(),expected)
                self.page.locator('.px-proof summary').first.press('Space')
                self.assertTrue(self.page.locator('.px-proof[open]').first.is_visible())
                hrefs=self.page.locator('.px-co-head a').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))')
                self.assertTrue(all((ROOT/'argus'/name/h).is_file() for h in hrefs))
                self.page.locator('#reset').click()
                self.assertEqual(self.page.locator('.px-leaf').count(),0)

    def test_all_silhouettes_keep_source_geometry_and_clear_label_collisions(self):
        for name in ('kdef','knuke','kaero'):
            self.open(name)
            buttons=self.page.locator('#sils .chip')
            for i in range(buttons.count()):
                buttons.nth(i).click()
                result=self.page.evaluate('''() => {
                  const sil=document.querySelector('#sils [aria-pressed=true]').dataset.sil;
                  const expected=P.regions.filter(r=>r.silhouette===sil).map(r=>r.points);
                  const actual=[...document.querySelectorAll('#regions polygon')].map(p=>p.getAttribute('points'));
                  const boxes=[...document.querySelectorAll('#labels text')].map(t=>t.getBBox());
                  let overlaps=0;
                  boxes.forEach((a,i)=>boxes.slice(i+1).forEach(b=>{if(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y)overlaps++;}));
                  return {geometry:JSON.stringify(actual)===JSON.stringify(expected),overlaps};
                }''')
                self.assertTrue(result['geometry'],(name,i))
                self.assertEqual(result['overlaps'],0,(name,i))

    def test_semiconductor_coverage_and_original_deep_links(self):
        self.open('ksemi','#depo')
        expected=set(self.page.evaluate('P.cos.depo.map(c=>c.stock)'))
        actual=set()
        ids=self.page.locator('.px-leaf').evaluate_all('(xs)=>xs.map(x=>x.dataset.child)')
        for id in ids:
            self.page.locator(f'[data-child="{id}"]').click()
            actual.update(self.page.locator('.px-stock').all_text_contents())
        self.assertEqual(actual,expected)
        self.page.get_by_role('button',name='구성 부품',exact=True).click()
        self.assertGreater(self.page.locator('[data-child^=part-]').count(),0)
        for name in ('kdef','knuke','kaero'):
            self.open(name)
            cat=self.page.evaluate('P.cats.find(c=>(P.idx[c.id]||[]).length).id')
            self.open(name,'#'+cat)
            self.assertEqual(self.page.locator('.px-leaf[aria-pressed=true]').get_attribute('data-child'),cat)

    def test_ship_engine_filter_and_empty_category(self):
        self.open('kship')
        self.page.locator('[data-id=R_MAIN_ENGINE]').press('Enter')
        self.assertTrue(self.page.locator('#engine').is_visible())
        self.page.locator('#eregions [role=button]').first.press('Enter')
        self.page.locator('#types .chip').first.click()
        self.assertIn('관련도',self.page.locator('.px-leaf').first.get_attribute('title'))
        self.page.locator('#reset').click()
        self.assertTrue(self.page.locator('#engine').is_hidden())
        self.open('kaero')
        cid=self.page.evaluate('P.cats.find(c=>!(P.idx[c.id]||[]).length).id')
        self.open('kaero','#'+cid)
        self.assertEqual(self.page.locator('.px-company').count(),0)
        self.assertIn('확인하지 못했습니다',self.page.locator('.px-empty').inner_text())

    def test_viewports_and_reduced_motion(self):
        for width,height in [(1440,900),(1920,1080),(390,844)]:
            self.page.set_viewport_size({'width':width,'height':height})
            for name in INDUSTRIES:
                self.open(name);self.select(name)
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,width))
                self.assertEqual(self.page.locator('.px-lens').evaluate('(e)=>getComputedStyle(e).animationName'),'none')
                if width>900:
                    self.assertTrue(self.page.evaluate('document.querySelector("#panel").getBoundingClientRect().x>document.querySelector(".ig").getBoundingClientRect().x+100'))


if __name__=='__main__':
    unittest.main()
