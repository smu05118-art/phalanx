"""Browser contracts for the shared explorer. Requires Playwright + Chromium.

Run: python -m unittest discover -s argus/ui/tests -v
Serves only the repository under test; no live data or external browser state.
"""
import functools
import http.server
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
INDUSTRIES = ('ksemi', 'kship', 'kdef', 'knuke', 'kaero')


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class ExplorerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def open(self, name, anchor=''):
        self.page.goto(self.base + f'/argus/{name}/parts.html' + anchor)

    def test_five_industries_drilldown_search_evidence_and_reset(self):
        for name in INDUSTRIES:
            with self.subTest(industry=name):
                self.open(name)
                self.assertTrue(self.page.locator('.ix-welcome').is_visible())
                trigger = '#fab [data-stage=depo]' if name == 'ksemi' else '#groups .chip'
                self.page.locator(trigger).first.click()
                self.assertGreater(self.page.locator('.ix-child').count(), 0)
                self.assertEqual(self.page.locator('.ix-company').count(), 0)
                self.page.locator('.ix-child:not(.ix-unverified)').first.press('Enter')
                self.assertGreater(self.page.locator('.ix-company').count(), 0)
                self.assertEqual(self.page.evaluate('document.activeElement.className'), 'ix-title')
                search = self.page.locator('.ix-search input')
                search.fill('NO_MATCH_000')
                self.assertEqual(self.page.locator('.ix-company').count(), 0)
                self.assertIn('검색 결과가 없습니다', self.page.locator('.ix-empty').inner_text())
                search.fill('')
                if self.page.locator('.ix-more').count():
                    before = self.page.locator('.ix-company').count()
                    self.page.locator('.ix-more').click()
                    self.assertGreater(self.page.locator('.ix-company').count(), before)
                if self.page.locator('.ix-evidence').count():
                    self.page.locator('.ix-evidence summary').first.press('Space')
                    self.assertTrue(self.page.locator('.ix-evidence[open] blockquote').first.is_visible())
                hrefs = self.page.locator('a.ix-company-name').evaluate_all('(links)=>links.map(a=>a.getAttribute("href"))')
                self.assertTrue(all((ROOT / 'argus' / name / href).is_file() for href in hrefs))
                self.page.locator('.ix-back').click()
                self.assertEqual(self.page.locator('.ix-company').count(), 0)
                self.page.locator('#reset').click()
                self.assertTrue(self.page.locator('.ix-welcome').is_visible())
                self.assertEqual(self.page.evaluate('location.hash'), '')

    def test_semiconductor_step_coverage_and_unverified_bucket(self):
        self.open('ksemi', '#depo')
        self.assertTrue(self.page.locator('[data-child=unspecified]').is_visible())
        rows = self.page.evaluate('P.cos.depo.map(c=>c.stock)')
        observed = set()
        ids = self.page.locator('[data-child^=step-], [data-child=unspecified]').evaluate_all('(xs)=>xs.map(x=>x.dataset.child)')
        for child in ids:
            self.page.locator(f'[data-child="{child}"]').click()
            while self.page.locator('.ix-more').count():
                self.page.locator('.ix-more').click()
            observed.update(self.page.locator('.ix-stock').all_text_contents())
            self.page.locator('.ix-back').click()
        self.assertEqual(set(rows), observed)
        self.page.locator('[data-fb=back]').click()
        self.page.locator('[data-child=step-0]').click()
        shown = set(self.page.locator('.ix-stock').all_text_contents())
        valid = set(self.page.evaluate('P.cos.depo.filter(c=>["후공정","공통","전후공정 겸업"].includes(c.fb)).map(c=>c.stock)'))
        self.assertTrue(shown.issubset(valid))

    def test_ship_engine_keyboard_and_type_filter(self):
        self.open('kship')
        self.page.locator('[data-id=R_MAIN_ENGINE]').press('Enter')
        self.assertTrue(self.page.locator('#engine').is_visible())
        self.page.locator('#eregions [role=button]').first.press('Enter')
        self.assertGreater(self.page.locator('.ix-child').count(), 0)
        self.page.locator('#types .chip').first.click()
        self.assertIn('관련도', self.page.locator('.ix-child-meta').first.inner_text())
        self.page.locator('#reset').click()
        self.assertTrue(self.page.locator('#engine').is_hidden())

    def test_existing_category_deep_links(self):
        for name in ('kdef', 'knuke', 'kaero'):
            self.open(name)
            cat = self.page.evaluate('P.cats.find(c=>(P.idx[c.id]||[]).length).id')
            self.open(name, '#' + cat)
            self.assertGreater(self.page.locator('.ix-company').count(), 0)
        self.open('kship', '#PIPE')
        self.assertGreater(self.page.locator('.ix-child').count(), 0)

    def test_mobile_layout_and_reduced_motion(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        for name in INDUSTRIES:
            with self.subTest(industry=name):
                self.open(name)
                trigger = '#fab [data-stage=depo]' if name == 'ksemi' else '#groups .chip'
                self.page.locator(trigger).first.click()
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                self.assertEqual(self.page.locator('.ix-content').evaluate('(e)=>getComputedStyle(e).animationName'), 'none')
                self.page.locator('.ix-child:not(.ix-unverified)').first.click()
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))


if __name__ == '__main__':
    unittest.main()
