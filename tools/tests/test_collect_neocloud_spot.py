"""Offline contracts. Synthetic LAST tests never relabel the supplied AVG import."""
import copy
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('collector', ROOT / 'tools/collect_neocloud_spot.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
FIX = ROOT / 'tools/tests/fixtures/neocloud_spot'
NOW = '2026-10-20T15:32:42Z'


def fixture(name):
    return c.fixture(FIX / (name + '.json'))


def current():
    return c.parse_current(fixture('current'), NOW)


def history(method=c.AVG):
    return c.parse_history(fixture('series'), method, NOW)


class ParserTests(unittest.TestCase):
    def test_current_exact_decimal_and_metadata(self):
        rows = current()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['price'], '1.1')
        self.assertEqual(rows[0]['family'], 'H200')
        self.assertEqual(rows[1]['price'], '0.79')

    def test_current_effective_can_follow_earliest_response_snapshot(self):
        pages = fixture('current')
        pages[0][0]['snapshotTime'] = '2026-10-20T15:00:00Z'
        pages[0][0]['items'][0]['effectiveTime'] = '2026-10-20T15:01:00Z'
        self.assertEqual(c.parse_current(pages, NOW)[0]['effective_time'], '2026-10-20T15:01:00Z')

    def test_history_import_keeps_avg(self):
        rows = history()
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(r['method'] == c.AVG for r in rows))
        self.assertEqual(rows[0]['interval_start'], '2026-09-20T15:00:00Z')

    def test_dynamic_sku_and_region(self):
        pages = fixture('current')
        pages[0][0]['items'][0]['skuId'] = 'new-dynamic-sku'
        pages[0][0]['items'][0]['region'] = 'future-region9'
        self.assertEqual(c.parse_current(pages, NOW)[0]['region'], 'future-region9')

    def test_family_aliases(self):
        for platform, family in c.FAMILIES.items():
            pages = fixture('current')
            pages[0][0]['items'][0]['computeInstance']['platform'] = platform
            self.assertEqual(c.parse_current(pages, NOW)[0]['family'], family)

    def test_bad_currency_unit_platform(self):
        for field, value in [('currency', 'USD'), ('unitTitle', 'CPU hour'), ('value', 1.1)]:
            pages = fixture('current')
            pages[0][0]['items'][0]['price'][field] = value
            with self.assertRaises(ValueError):
                c.parse_current(pages, NOW)
        for mode in ('current', 'series'):
            pages = fixture(mode)
            pages[0][0]['items'][0]['computeInstance']['platform'] = 'gpu-unknown'
            with self.assertRaises(ValueError):
                c.parse_current(pages, NOW) if mode == 'current' else c.parse_history(pages, c.LAST, NOW)
        for k in ('currency', 'unitTitle'):
            pages = fixture('series')
            pages[0][0]['items'][0][k] = 'invalid'
            with self.assertRaises(ValueError):
                c.parse_history(pages, c.LAST, NOW)

    def test_decimal_lossless(self):
        value = '0.12345678901234567890123456789'
        self.assertEqual(c.price(value), value)
        self.assertEqual(c.price('1.1000'), '1.1')
        self.assertEqual(c.price('0.0'), '0')
        self.assertEqual(c.price('0.000'), '0')
        for bad in [True, 1.1, '-1', 'NaN', 'Infinity', '1e3', '01', '']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                c.price(bad)

    def test_boundary_month_uses_interval_start(self):
        pages = fixture('series')
        pages[0][0]['items'][0]['points'] = [{'timestamp': '2026-10-01T00:00:00Z', 'value': '1'}]
        row = c.parse_history(pages, c.LAST, NOW)[0]
        self.assertEqual(row['interval_start'], '2026-09-30T23:00:00Z')
        self.assertEqual(c.shard_path(row), 'history/2026-09.json')

    def test_incomplete_excluded_not_zeroed(self):
        pages = fixture('series')
        pages[0][0]['items'] = pages[0][0]['items'][:1]
        pages[0][0]['items'][0]['points'] = [{'timestamp':'2026-10-20T15:00:00Z','value':'2'}, {'timestamp':'2026-10-20T16:00:00Z','value':'3'}]
        rows = c.parse_history(pages, c.LAST, NOW)
        self.assertEqual([r['price'] for r in rows], ['2'])

    def test_unaligned_and_malformed_partial_parse(self):
        for value in ['2026-10-20T14:30:00Z', '2026-02-30T00:00:00Z', None]:
            pages = fixture('series')
            pages[0][0]['items'][-1]['points'][-1]['timestamp'] = value
            with self.assertRaises(ValueError):
                c.parse_history(pages, c.LAST, NOW)

    def test_schema_fields_and_types(self):
        for mutate in [lambda x: x.update(items={}), lambda x: x.update(unexpected=True), lambda x: x.pop('snapshotTime'), lambda x: x.update(nextPageToken=42)]:
            d = fixture('current'); mutate(d[0][0])
            with self.assertRaises(ValueError):
                c.parse_current(d, NOW)

    def test_duplicate_json_keys(self):
        for data in [b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"a":NaN}']:
            with self.assertRaises(ValueError):
                c.decode(data)

    def test_identical_overlap_preserves_first_evidence(self):
        old = history(); new = copy.deepcopy(old)
        for r in new:
            r['collected_time'] = '2026-10-21T00:00:00Z'
            r['source_sha256'] = 'a' * 64
        self.assertEqual(c.merge(old, new), old)

    def test_conflicting_price_and_identity(self):
        for k, v in [('price','2.46'),('region','other'),('platform','gpu-b300-sxm'),('product_title','other')]:
            old=history(); new=copy.deepcopy(old);new[0][k]=v
            with self.subTest(k=k), self.assertRaisesRegex(ValueError,'immutable observation conflict'):
                c.merge(old,new)

    def test_avg_and_last_are_separate_keys(self):
        self.assertEqual(len(c.merge(history(), history(c.LAST))), 40)

    def test_partial_fixture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'partial.json';d=fixture('current')[0][0];d['nextPageToken']='next';p.write_bytes(c.encode(d))
            with self.assertRaisesRegex(ValueError,'partial'):
                c.fixture(p)

    def test_fixture_method_provenance_is_digest_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_path = root / 'current.json'
            series_path = root / 'series.json'
            current_path.write_bytes((FIX / 'current.json').read_bytes())
            series_path.write_bytes((FIX / 'series.json').read_bytes())
            args = c.argparse.Namespace(data=root / 'archive', mode='fixture-last', collected_at=NOW,
                                        current_fixture=current_path, series_fixture=series_path)
            with patch.object(c, 'VERIFIED_CURRENT_SHA256', c.digest(current_path.read_bytes())), \
                    patch.dict(c.VERIFIED_FIXTURE_SHA256, {c.LAST: c.digest(series_path.read_bytes())}):
                c.collect(args)
            data = json.loads(series_path.read_text())
            series_path.write_bytes(c.encode(data))
            with self.assertRaisesRegex(ValueError, 'provenance-approved'):
                c.collect(args)

    def test_fixture_current_provenance_is_digest_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current_path = root / 'current.json'
            series_path = root / 'series.json'
            current_path.write_bytes((FIX / 'current.json').read_bytes())
            series_path.write_bytes((FIX / 'series.json').read_bytes())
            data = json.loads(current_path.read_text())
            data['items'][0]['price']['value'] = '999'
            current_path.write_bytes(c.encode(data))
            args = c.argparse.Namespace(data=root / 'archive', mode='import-avg', collected_at=NOW,
                                        current_fixture=current_path, series_fixture=series_path)
            with patch.dict(c.VERIFIED_FIXTURE_SHA256, {c.AVG: c.digest(series_path.read_bytes())}), \
                    self.assertRaisesRegex(ValueError, 'current fixture'):
                c.collect(args)


class PropertySweepTests(unittest.TestCase):
    """Dependency-free deterministic properties; the production collector remains stdlib-only."""

    def test_decimal_normalization_is_idempotent_and_value_preserving(self):
        rng = random.Random(261021)
        examples = ['0.0', '0.000', '1.0', '10.00', '0.' + '0' * 29 + '1']
        for _ in range(1000):
            whole = str(rng.randrange(0, 10**11))
            width = rng.randrange(1, 31)
            fraction = ''.join(str(rng.randrange(10)) for _ in range(width))
            examples.append(whole + '.' + fraction)
        for raw in examples:
            canonical = c.price(raw)
            with self.subTest(raw=raw):
                self.assertEqual(c.price(canonical), canonical)
                self.assertEqual(c.Decimal(raw), c.Decimal(canonical))
                self.assertNotRegex(canonical, r'\.0+$|\.$')

    def test_json_roundtrip_preserves_generated_values(self):
        rng = random.Random(614)
        for _ in range(250):
            obj = {'text': ''.join(chr(97 + rng.randrange(26)) for _ in range(rng.randrange(20))),
                   'ints': [rng.randrange(-10**6, 10**6) for _ in range(rng.randrange(20))],
                   'flags': [rng.choice([True, False, None]) for _ in range(rng.randrange(10))]}
            self.assertEqual(c.decode(c.encode(obj)), obj)

    def test_merge_is_idempotent_and_commutative_for_disjoint_keys(self):
        rows = history(c.LAST)
        left, right = rows[::2], rows[1::2]
        self.assertEqual(c.merge(rows, rows), rows)
        self.assertEqual(c.merge(left, right), c.merge(right, left))


class NetworkTests(unittest.TestCase):
    def test_allowlist_exact(self):
        self.assertEqual(c.allowed(c.CURRENT), c.CURRENT)
        for url in ['http://api.nebius.cloud/x','https://api.nebius.cloud.evil/x','https://evil/x','https://user@api.nebius.cloud/x','https://api.nebius.cloud:444/x']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                c.allowed(url)

    def test_redirect_revalidation(self):
        req=urllib.request.Request(c.CURRENT)
        for target in ('https://evil.test/', c.CURRENT+'?p=2', 'https://api.nebius.cloud/unrelated-json'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'redirect rejected'):
                c.Redirect().redirect_request(req,None,302,'m',{},target)

    def response(self, data=b'{}', url=c.CURRENT):
        class Response(io.BytesIO):
            def geturl(self): return url
        return Response(data)

    def test_overflow(self):
        class Opener:
            def open(s,req,timeout):return self.response(b' '*(c.RESPONSE_LIMIT+1))
        with self.assertRaisesRegex(ValueError,'overflow'):
            c.fetch(c.CURRENT,Opener())

    def test_final_host_and_timeout(self):
        outer=self
        class Opener:
            def open(s,req,timeout):
                outer.assertEqual(timeout,20)
                outer.assertNotIn('Authorization',req.headers)
                return outer.response(b'{}','https://evil.test')
        with self.assertRaises(ValueError):c.fetch(c.CURRENT,Opener())

    def test_retry_after_and_5xx(self):
        for code in [429,500,503]:
            responses=[urllib.error.HTTPError(c.CURRENT,code,'retry',{'Retry-After':'2'},None),self.response()]
            class Opener:
                def open(s,*args,**kwargs):
                    v=responses.pop(0)
                    if isinstance(v,Exception):raise v
                    return v
            with patch.object(c.time,'sleep') as sleep:
                self.assertEqual(c.fetch(c.CURRENT,Opener()),b'{}')
                sleep.assert_called_once_with(2)

    def test_retry_bound_and_http_date(self):
        self.assertEqual(c.retry_delay(None,2),4)
        future=c.email.utils.format_datetime(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=30))
        self.assertTrue(0<c.retry_delay(future,0)<=30)
        with self.assertRaises(ValueError):c.retry_delay('121',0)
        calls=[]
        class Opener:
            def open(s,*a,**kw):calls.append(1);raise urllib.error.HTTPError(c.CURRENT,503,'retry',{},None)
        with patch.object(c.time,'sleep'), self.assertRaises(urllib.error.HTTPError):c.fetch(c.CURRENT,Opener())
        self.assertEqual(len(calls),4)

    def test_invalid_retry_after_closes_http_error_body(self):
        body=io.BytesIO(b'retry')
        error=urllib.error.HTTPError(c.CURRENT,503,'retry',{'Retry-After':'121'},body)
        class Opener:
            def open(s,*a,**kw):raise error
        with self.assertRaisesRegex(ValueError,'Retry-After'):
            c.fetch(c.CURRENT,Opener())
        self.assertTrue(body.closed)

    def test_pagination_and_cycles(self):
        first=fixture('current')[0][0];original=first['snapshotTime'];second=copy.deepcopy(first);first['nextPageToken']='abc'
        seen=[]
        def getter(url):seen.append(url);return c.encode(first if len(seen)==1 else second)
        self.assertEqual(len(c.pages(c.CURRENT,{'pageSize':100},getter)),2)
        self.assertIn('pageToken=abc',seen[1])
        with self.assertRaisesRegex(ValueError,'cycle'):c.pages(c.CURRENT,{},lambda _:c.encode(first))

    def test_pagination_pages_retain_individual_snapshot_times(self):
        first=fixture('current')[0][0];original=first['snapshotTime'];second=copy.deepcopy(first);first['nextPageToken']='abc'
        second['snapshotTime']='2026-10-20T15:31:00Z'
        replies=[first,second]
        result=c.pages(c.CURRENT,{},lambda _:c.encode(replies.pop(0)))
        self.assertEqual([page['snapshotTime'] for page,_ in result],
                         [original,'2026-10-20T15:31:00Z'])

    def test_fetch_duplicate_keys_fails(self):
        class Opener:
            def open(s,*a,**kw):return self.response(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):c.fetch(c.CURRENT,Opener())


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)/'data'
        c.publish(self.root,c.build(self.root,current(),history()))

    def snapshot(self):
        return {str(p.relative_to(self.root)):(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*.json')}

    def test_check_and_shard_hashes(self):
        index,rows=c.read_archive(self.root);self.assertEqual(len(rows),20);self.assertIsNone(index['latest_complete_timestamp'])
        self.assertEqual(c.main(['--data',str(self.root),'--check']),0)

    def test_noop_bytes_and_mtimes(self):
        before=self.snapshot();self.assertEqual(c.publish(self.root,c.build(self.root,current(),history())),0);self.assertEqual(self.snapshot(),before)
        later=current()
        for r in later:r['collected_time']='2026-10-21T00:00:00Z'
        self.assertEqual(c.publish(self.root,c.build(self.root,later,history())),0)

    def test_same_snapshot_change_conflicts_but_new_snapshot_refreshes(self):
        same = current()
        same[0]['price'] = '9'
        with self.assertRaisesRegex(ValueError, 'current snapshot conflict'):
            c.build(self.root, same, history())
        newer = current()
        for row in newer:
            row['source_snapshot_time'] = '2026-10-20T15:25:00Z'
            row['collected_time'] = '2026-10-20T15:26:00Z'
        files = c.build(self.root, newer, history())
        c.publish(self.root, files)
        index, _ = c.read_archive(self.root)
        self.assertEqual(index['snapshot_time'], '2026-10-20T15:25:00Z')

    def test_duplicate_current_is_rejected_before_reconciliation(self):
        duplicate = current() + [copy.deepcopy(current()[0])]
        with self.assertRaisesRegex(ValueError, 'duplicate current'):
            c.build(self.root, duplicate, history())

    def test_conflict_preserves_every_byte(self):
        before=self.snapshot();rows=history();rows[-1]['price']='99'
        with self.assertRaises(ValueError):c.publish(self.root,c.build(self.root,current(),rows))
        self.assertEqual(self.snapshot(),before)

    def test_schema_failure_preserves_every_byte(self):
        before=self.snapshot();rows=history();rows[-1]['unit']='USD/CPU-hour'
        with self.assertRaises(ValueError):c.publish(self.root,c.build(self.root,current(),rows))
        self.assertEqual(self.snapshot(),before)

    def test_archive_rejects_effective_time_after_collection(self):
        index = json.loads((self.root / 'index.json').read_text())
        index['current'][0]['effective_time'] = '2026-10-20T15:33:00Z'
        (self.root / 'index.json').write_bytes(c.encode(index))
        with self.assertRaisesRegex(ValueError, 'effective time after collection'):
            c.read_archive(self.root)

    def test_size_overflow_preserves_every_byte(self):
        before=self.snapshot()
        with patch.object(c,'LIMIT',10),self.assertRaises(ValueError):c.publish(self.root,c.build(self.root,current(),history()))
        self.assertEqual(self.snapshot(),before)

    def test_io_failure_rolls_back(self):
        before={k:v[0] for k,v in self.snapshot().items()};files=c.build(self.root,current(),history(c.LAST));real=c.atomic;count=0
        def fail_second(p,b):
            nonlocal count
            count+=1
            if count==2:raise OSError('injected')
            real(p,b)
        with patch.object(c,'atomic',fail_second),self.assertRaises(OSError):c.publish(self.root,files)
        self.assertEqual({k:v[0] for k,v in self.snapshot().items()},before)

    def test_atomic_replace_failure_cleans_tmp(self):
        before=self.snapshot()
        with patch.object(c.os,'replace',side_effect=OSError('injected')),self.assertRaises(OSError):c.atomic(self.root/'index.json',b'x')
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(list(self.root.glob('.index.json*')),[])

    def test_tampered_hash_rejected(self):
        p=next(self.root.glob('imported-average/*.json'));p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'hash'):c.read_archive(self.root)

    def test_unreferenced_shard_rejected_and_publish_removes_it(self):
        files = c.build(self.root, current(), history())
        stale = self.root / 'history/2020-01.json'
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'unreferenced'):
            c.read_archive(self.root)
        c.publish(self.root, files)
        self.assertFalse(stale.exists())
        c.read_archive(self.root)

    def test_archive_layout_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / 'target'
            target.mkdir()
            root_link = base / 'root-link'
            root_link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink archive root'):
                c.read_archive(root_link)
            root = base / 'root'
            root.mkdir()
            layer_target = base / 'layer-target'
            layer_target.mkdir()
            (root / 'history').symlink_to(layer_target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink archive layer'):
                c.read_archive(root)

    def test_current_advances_and_cannot_regress(self):
        rows=current()
        for r in rows:r['source_snapshot_time']='2026-10-20T15:25:00Z';r['price']='2'
        c.publish(self.root,c.build(self.root,rows,history()))
        with self.assertRaisesRegex(ValueError,'regression'):c.build(self.root,current(),history())

    def test_refresh_first_run_backfills_last(self):
        args=c.argparse.Namespace(data=self.root,mode='refresh',collected_at=NOW,current_fixture=None,series_fixture=None)
        queries=[]
        def fake(endpoint,params):queries.append((endpoint,params));return fixture('current' if endpoint==c.CURRENT else 'series')
        with patch.object(c,'pages',fake):files=c.collect(args)
        q=queries[1][1]
        self.assertEqual(q['aggregation.method'],c.LAST)
        self.assertEqual(c.stamp(q['filters.endTime'])-c.stamp(q['filters.startTime']),dt.timedelta(days=29))
        self.assertIn('history/2026-09.json',files)

    def test_refresh_overlaps_two_days(self):
        c.publish(self.root,c.build(self.root,current(),history(c.LAST)))
        args=c.argparse.Namespace(data=self.root,mode='refresh',collected_at='2026-09-22T15:32:42Z',current_fixture=None,series_fixture=None)
        queries=[]
        def fake(endpoint,params):queries.append(params);return fixture('current' if endpoint==c.CURRENT else 'series')
        with patch.object(c,'pages',fake):c.collect(args)
        self.assertEqual(queries[1]['filters.startTime'],'2026-09-19T01:00:00Z')

    def test_network_failure_does_not_touch_archive(self):
        before=self.snapshot()
        with patch.object(c,'pages',side_effect=OSError('offline')):
            self.assertEqual(c.main(['--data',str(self.root)]),1)
        self.assertEqual(self.snapshot(),before)

    def test_bad_fixture_partial_parse_does_not_touch_archive(self):
        bad=fixture('series')[0][0];bad['items'][-1]['points'][-1]['value']=False
        path=Path(self.temp.name)/'bad.json';path.write_bytes(c.encode(bad));before=self.snapshot()
        self.assertEqual(c.main(['--data',str(self.root),'--mode','import-avg','--current-fixture',str(FIX/'current.json'),'--series-fixture',str(path),'--collected-at',NOW]),1)
        self.assertEqual(self.snapshot(),before)

    def test_monthly_parts_bound_size_and_roundtrip(self):
        with patch.object(c, 'SHARD_LIMIT', 3000):
            files = c.build(self.root, current(), history())
        self.assertIn('imported-average/2026-09-02.json', files)
        c.publish(self.root, files)
        index, rows = c.read_archive(self.root)
        self.assertEqual(len(rows), 20)
        self.assertTrue(all((self.root / s['path']).stat().st_size < 3000 for s in index['shards']))
        parts = [s for s in index['shards'] if s['method'] == c.AVG]
        for left, right in zip(parts, parts[1:]):
            self.assertLessEqual(left['end'], right['start'])
        collapsed = c.build(self.root, current(), history())
        c.publish(self.root, collapsed)
        index, rows = c.read_archive(self.root)
        self.assertEqual(len(rows), 20)
        self.assertFalse(any('-02.json' in s['path'] for s in index['shards']))

    def test_incremental_build_reads_only_touched_month_of_twenty_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'archive'
            template = history(c.LAST)[0]
            initial = []
            for offset in range(24):
                year, month = 2024 + offset // 12, offset % 12 + 1
                start = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
                row = copy.deepcopy(template)
                row['interval_start'] = c.iso(start)
                row['interval_end'] = c.iso(start + dt.timedelta(hours=1))
                initial.append(row)
            c.publish(root, c.build(root, current(), initial))
            untouched = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                         for p in root.glob('history/*.json') if p.name != '2024-01.json'}
            incoming = copy.deepcopy(initial[0])
            incoming['interval_start'] = '2024-01-01T01:00:00Z'
            incoming['interval_end'] = '2024-01-01T02:00:00Z'
            with patch.object(c, 'read_entries', wraps=c.read_entries) as reader:
                files = c.build(root, current(), [incoming])
            loaded = reader.call_args.args[1]
            self.assertEqual([e['path'] for e in loaded], ['history/2024-01.json'])
            self.assertEqual(set(files), {'history/2024-01.json', 'index.json'})
            index = c.decode(files['index.json'])
            self.assertEqual(index['latest_complete_timestamp'], '2025-12-01T01:00:00Z')
            c.publish(root, files)
            self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in untouched}, untouched)
            _, rows = c.read_archive(root)
            self.assertEqual(len(rows), 25)

    def test_public_archive_legacy_separation(self):
        index,rows=c.read_archive(ROOT/'data/neocloud_spot')
        self.assertGreater(len(index['current']),0)
        self.assertTrue(all(r['method'] in (c.AVG,c.LAST) for r in rows))
        legacy=json.loads((ROOT/'data/neocloud_spot/legacy-user-chart-261020.json').read_text())
        self.assertEqual(legacy['classification'],'legacy_unverified_derived_chart')
        self.assertEqual({r['product']:r['price'] for r in legacy['observations']},{'B300':8.16,'B200':3.92,'H200':1.87,'H100':.79,'RTX PRO 6000':1.18})
        self.assertFalse((ROOT/'data/neocloud_spot/history.json').exists())


if __name__=='__main__':unittest.main()
