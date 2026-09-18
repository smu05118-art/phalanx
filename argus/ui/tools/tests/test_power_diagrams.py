"""Evidence boundaries and legacy link coverage for the illustrated power pages."""
import copy
import json
from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1]
ARGUS = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
from power_diagrams import grid_payload, plant_payload, markup


def company(stock, products):
    return dict(stock=stock, name='Fixture '+stock, role='maker',
                products=list(products), backlog=None,
                product_why=[dict(key=k, src='fixture', text=v) for k,v in products.items()])


class PowerEvidenceTest(unittest.TestCase):
    def test_pole_false_positive_and_generic_converter_do_not_become_specific_equipment(self):
        samples=[company('999991', {'dist_tr':'건설 주상복합 아파트'}),
                 company('999992', {'dist_tr':'주상변압기 제조'}),
                 company('999993', {'converter':'태양광 인버터 및 ESS PCS'}),
                 company('999994', {'cable':'HVDC 직류송전 케이블'}),
                 company('999995', {'tr_unknown':'변압기 제조'})]
        before=copy.deepcopy(samples)
        rows=grid_payload(samples,[])['rows']
        self.assertEqual([r['stock'] for r in rows['pole-transformer']],['999992'])
        self.assertEqual([r['stock'] for r in rows['hvdc-equipment']],['999994'])
        self.assertNotIn('999995',[r['stock'] for r in rows['step-transformer']])
        self.assertEqual([r['stock'] for r in rows['unknown-transformer']],['999995'])
        self.assertEqual(samples,before)

    def test_official_product_catalog_only_enriches_existing_nonholding_companies(self):
        empty=grid_payload([],[])['rows']
        self.assertTrue(all(not rows for rows in empty.values()))
        holding=company('033100',{});holding['role']='holding'
        self.assertTrue(all(not rows for rows in grid_payload([holding],[])['rows'].values()))
        maker=company('033100',{})
        rows=grid_payload([maker],[])['rows']
        for key in ('pole-transformer','pad-transformer'):
            self.assertEqual([r['stock'] for r in rows[key]],['033100'])
            self.assertTrue(rows[key][0]['proofs'][0]['url'].startswith('https://www.cheryongelec.com/'))

    def test_all_old_plant_category_links_and_companies_survive(self):
        tax=json.loads((ARGUS/'knuke/tools/assets/parts_taxonomy.json').read_text())
        idx={c['id']:[dict(stock=f'{i:06d}',nm='Fixture',src='kind',kw='제품',prod='원문')]
             for i,c in enumerate(tax['cats'])}
        payload=plant_payload(tax,idx,[])
        children={c['id'] for s in payload['scenes'] for n in s['nodes'] for c in n['children']}
        self.assertEqual(children,set(idx))
        self.assertEqual({r['stock'] for rows in payload['rows'].values() for r in rows},
                         {r['stock'] for rows in idx.values() for r in rows})
        ids=[n['id'] for s in payload['scenes'] for n in s['nodes']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all(s['width']>n['x']+83 and n['x']>=83 and s['height']>=n['y']+122
                            for s in payload['scenes'] for n in s['nodes']))

    def test_payload_cannot_close_script_or_inject_hero_markup(self):
        payload=grid_payload([company('999992',{'dist_tr':'주상변압기 </script><script>alert(1)</script>'})],[])
        out=markup(payload,'<img onerror=alert(1)>','A&B',[])
        self.assertNotIn('<img onerror',out)
        self.assertNotIn('</script><script>alert',out)
        self.assertIn('A&amp;B',out)


if __name__=='__main__':
    unittest.main()
