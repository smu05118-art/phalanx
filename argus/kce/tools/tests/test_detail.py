"""원문에서 수주총액을 생략한 공시, 단위와 기준·매칭·재수집 경계를 검증한다."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import kce_detail as KD


def node():
    return {'text': '8. 기타 재무에 관한 사항', 'rcpNo': '20260814000001',
            'dcmNo': '123', 'eleId': '1', 'offset': '0', 'length': '100', 'dtd': 'dart4.xsd'}


class OfficialFixtures(unittest.TestCase):
    def test_hanshin_without_contract_amount_is_retained(self):
        text = (TOOLS/'tests/fixtures/hanshin_progress_2026Q2.html').read_text()
        d = KD.parse_source(text, node(), 'p8')
        rows = [r for t in d['tables'] for r in t['rows']]
        self.assertGreater(len(rows), 20)
        self.assertTrue(any(r.get('pr') is not None and r.get('ub') is not None for r in rows))
        self.assertTrue(all(r.get('amt') is None for r in rows))
        self.assertTrue(all(t['source_unit'] in ('천원','백만원') for t in d['tables']))

    def test_taeyoung_header_embedded_unit(self):
        text = (TOOLS/'tests/fixtures/taeyoung_progress_2026Q2.html').read_text()
        d = KD.parse_source(text, node(), 'p8')
        self.assertGreaterEqual(len(d['tables']), 2)
        self.assertTrue(all(t['source_unit']=='천원' for t in d['tables']))
        self.assertGreater(sum(len(t['rows']) for t in d['tables']), 40)

    def test_sangji_contract_assets_and_liabilities_are_separate(self):
        text=(TOOLS/'tests/fixtures/sangji_progress_2026Q2.html').read_text()
        d=KD.parse_source(text,node(),'p8')
        self.assertEqual({t['basis'] for t in d['tables']},{'연결','별도'})
        rows=[r for t in d['tables'] for r in t['rows']]
        site=next(r for r in rows if r['nm']=='임실 정주활력센터 건립 건축공사')
        self.assertIsNone(site['ub'])
        self.assertAlmostEqual(site['contract_liability'],931.114)
        self.assertEqual(site['pr'],1.88)

    def test_unknown_unit_never_defaults_to_million(self):
        text='<html><table><tr><th>공사명</th><th>진행률</th><th>미청구공사 총액</th><th>공사미수금 총액</th></tr><tr><td>가현장</td><td>50</td><td>9000</td><td>1000</td></tr></table></html>'
        d=KD.parse_source(text,node(),'p8')
        r=d['tables'][0]['rows'][0]
        self.assertIsNone(r['ub']);self.assertIsNone(r['rc']);self.assertEqual(r['pr'],50)
        self.assertEqual(d['tables'][0]['basis'],'미확인')

    def test_foreign_currency_is_not_krw(self):
        self.assertIsNone(KD.unit_of('(단위: USD)',[]))
        self.assertIsNone(KD.unit_of('',[]))
        self.assertEqual(KD.unit_of('(단위: 천원)',[]),'천원')


class Linking(unittest.TestCase):
    def site(self, sid='s1'):
        return {'id':sid,'agg':False,'observations':[{'nm':'가현장','cl':'발주처',
                'sd':'2025.01.03','table_lead':'남광토건'}],
                's':{'amt':[100],'cmp':[20],'bal':[80],'pr':[20]}}

    def test_missing_amount_can_match_with_client(self):
        s=self.site();row={'nm':'가현장','cl':'발주처','pr':20,'amt':None}
        self.assertIs(KD.match_row(row,[s],0,'남광토건')[0],s)

    def test_no_fuzzy_name_or_ambiguous_join(self):
        row={'nm':'가현장','cl':'발주처','amt':100}
        self.assertIsNone(KD.match_row(row,[self.site(),self.site('s2')],0)[0])
        self.assertIsNone(KD.match_row(dict(row,nm='가현장2'),[self.site()],0)[0])

    def test_abbreviation_needs_client_date_and_amount(self):
        row={'nm':'가현장 약칭','cl':'발주처','amt':100,'sd':'2025.01.03'}
        self.assertIsNotNone(KD.match_row(row,[self.site()],0)[0])
        row['cl']='다른발주처'
        self.assertIsNone(KD.match_row(row,[self.site()],0)[0])

    def test_zero_and_consolidated_separate_never_sum_into_backlog(self):
        with tempfile.TemporaryDirectory() as tmp:
            d={'stock':'001260','co':'남광토건','fq':['2026Q2'],'src':{'2026Q2':'20260814000001'},
               'sites':[self.site()], 'summary':{'bal':[80]}}
            source={'title':'III-8','url':'https://dart.fss.or.kr/report/viewer.do',
                    'sha256':'a'*64,'status':'tables_found','tables':[]}
            for b in ['연결','별도']:
                source['tables'].append({'id':b,'basis':b,'source_unit':'백만원',
                    'rows':[{'nm':'가현장','cl':'발주처','amt':100,'pr':0,'ub':0,'rc':None}]})
            doc={'rcpNo':'20260814000001','status':'checked','report_url':'https://dart.fss.or.kr',
                 'sources':[source]}
            p=Path(tmp)/'001260/2026Q2.json';p.parent.mkdir();p.write_text(json.dumps(doc))
            out=KD.enrich(d,tmp)
            self.assertEqual(out['summary']['bal'],[80])
            self.assertEqual(len(out['detail']['observations']),2)
            self.assertEqual(out['detail']['observations'][0]['ub'],0)
            self.assertIsNone(out['detail']['observations'][0]['rc'])
            self.assertEqual(out['detail']['ledger'][0]['matched'],2)
            out['src']['2026Q2']='20260901000001'
            self.assertEqual(KD.enrich(out,tmp)['detail']['ledger'][0]['status'],'report_changed')

    def test_failed_fetch_preserves_existing_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(KD,'CACHE',Path(tmp)):
                p=Path(tmp)/'001260/2026Q2.json';p.parent.mkdir();p.write_text('original')
                with patch.object(KD,'toc',side_effect=TimeoutError('offline')):
                    with self.assertRaises(TimeoutError):
                        KD.collect_one(('001260','2026Q2',{'rcpNo':'20260814000001'}),force=True)
                self.assertEqual(p.read_text(),'original')


if __name__=='__main__':
    unittest.main()
