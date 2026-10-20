import copy
import importlib.util
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('spot', ROOT / 'tools/update_neocloud_spot.py')
spot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spot)


def dataset():
    return json.loads((ROOT / 'tools/tests/fixtures/neocloud_spot/legacy.json').read_text())


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.data = dataset()

    def mutate(self, field, value):
        data = copy.deepcopy(self.data)
        data['observations'][0][field] = value
        return data

    def test_seed_exact_endpoints(self):
        self.assertEqual({r['product']: r['price'] for r in self.data['observations']},
                         {'B300': 8.16, 'B200': 3.92, 'H200': 1.87, 'H100': 0.79, 'RTX PRO 6000': 1.18})
        self.assertTrue(all(r['quality'] == 'exact_printed_label' and r['effective_date'] == '2026-10-20' for r in self.data['observations']))

    def test_valid_merge(self):
        snapshot = self.mutate('effective_date', '2026-10-19')
        snapshot['observations'] = snapshot['observations'][:1]
        merged = spot.merge(self.data, snapshot)
        self.assertEqual(len(merged['observations']), 6)
        self.assertEqual(merged['observations'][0]['effective_date'], '2026-10-19')

    def test_ordering(self):
        data = copy.deepcopy(self.data)
        data['observations'].reverse()
        self.assertEqual(spot.encode(data), spot.encode(self.data))
        rows = spot.validate(data)['observations']
        self.assertEqual([(r['effective_date'], r['product']) for r in rows], sorted((r['effective_date'], r['product']) for r in rows))

    def test_duplicate_idempotency(self):
        self.assertEqual(spot.encode(self.data), spot.encode(spot.merge(self.data, self.data)))

    def test_numeric_representation_is_canonical(self):
        integer = self.mutate('price', 1)
        floating = self.mutate('price', 1.0)
        negative_zero = self.mutate('price', -0.0)
        self.assertEqual(spot.encode(integer), spot.encode(floating))
        self.assertEqual(spot.encode(integer), spot.encode(spot.merge(integer, floating)))
        self.assertEqual(spot.validate(negative_zero)['observations'][0]['price'], 0)

    def test_duplicate_conflict(self):
        with self.assertRaises(ValueError):
            spot.merge(self.data, self.mutate('price', 42))

    def test_duplicate_provenance_conflict(self):
        data = copy.deepcopy(self.data)
        data['observations'][0]['provenance']['source_file'] = 'other.png'
        with self.assertRaises(ValueError):
            spot.merge(self.data, data)

    def test_duplicate_quality_conflict(self):
        data = self.mutate('quality', 'approximate_from_chart')
        data['observations'][0]['uncertainty'] = .1
        with self.assertRaises(ValueError):
            spot.merge(self.data, data)

    def test_invalid_product(self):
        for value in ['A100', '', None, ['B300']]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                spot.validate(self.mutate('product', value))

    def test_invalid_date(self):
        for value in ['261020', '2026-02-30', '20261020', '2026-9-20', '2026-10-21', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                spot.validate(self.mutate('effective_date', value))

    def test_invalid_headers(self):
        for key, value in [('unit', 'USD/hour'), ('currency', 'KRW'), ('cadence', 'spot'), ('schema_version', True), ('schema_version', 2)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                spot.validate(dict(self.data, **{key: value}))

    def test_invalid_value(self):
        for value in [-1, float('nan'), float('inf'), -float('inf'), True, '8.16', {}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                spot.validate(self.mutate('price', value))

    def test_invalid_provenance(self):
        for key, value in [('source_type', 'official_api'), ('source_file', '../a.jpg'), ('source_file', ''), ('source_start', '2026-10-21'), ('source_end', '2026-10-19'), ('captured_date', '261019'), ('atlas_date', '261019'), ('captured_date', '2026-10-20'), ('atlas_date', '260230')]:
            data = copy.deepcopy(self.data)
            data['observations'][0]['provenance'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                spot.validate(data)
        with self.assertRaises(ValueError):
            spot.validate(self.mutate('provenance', {}))

    def test_source_filename_unicode_length_matches_ui(self):
        data = copy.deepcopy(self.data)
        data['observations'][0]['provenance']['source_file'] = '😀' * 251 + '.jpg'
        self.assertEqual(spot.validate(data)['observations'][0]['provenance']['source_file'], '😀' * 251 + '.jpg')
        data['observations'][0]['provenance']['source_file'] = '😀' * 252 + '.jpg'
        with self.assertRaises(ValueError):
            spot.validate(data)

    def test_null_missing(self):
        data = self.mutate('price', None)
        data['observations'][0]['quality'] = 'missing'
        normalized = spot.validate(data)
        del data['observations'][0]['price']
        self.assertEqual(spot.validate(data), normalized)
        self.assertIsNone(normalized['observations'][0]['price'])
        with self.assertRaises(ValueError):
            spot.merge(self.data, data)
        with self.assertRaises(ValueError):
            spot.validate(self.mutate('price', None))

    def test_approximate_uncertainty(self):
        data = self.mutate('quality', 'approximate_from_chart')
        for value in [None, 0, -1, True, float('nan')]:
            data['observations'][0]['uncertainty'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                spot.validate(data)
        data['observations'][0]['uncertainty'] = .05
        self.assertEqual(spot.validate(data)['observations'][0]['uncertainty'], .05)
        with self.assertRaises(ValueError):
            spot.validate(self.mutate('uncertainty', .1))

    def test_unknown_missing_fields(self):
        with self.assertRaises(ValueError):
            spot.validate(dict(self.data, surprise=1))
        for field in ['quality', 'uncertainty', 'provenance']:
            data = copy.deepcopy(self.data)
            del data['observations'][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                spot.validate(data)

    def test_empty(self):
        self.assertEqual(spot.merge(self.data, dict(spot.HEADER, observations=[])), spot.validate(self.data))


class CLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'history.json'
        self.snapshot = Path(temp.name) / 'snapshot.json'
        self.path.write_bytes(spot.encode(dataset()))
        self.snapshot.write_bytes(spot.encode(dataset()))

    def cli(self, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return spot.main(['--data', str(self.path), *args])

    def write_snapshot(self, path, product, price):
        data = dataset()
        row = copy.deepcopy(next(r for r in data['observations'] if r['product'] == product))
        row['effective_date'] = '2026-10-19'
        row['price'] = price
        path.write_bytes(spot.encode(dict(spot.HEADER, observations=[row])))

    def start_cli(self, snapshot):
        return subprocess.Popen(
            [sys.executable, str(ROOT / 'tools/update_neocloud_spot.py'), '--data', str(self.path), '--snapshot', str(snapshot)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def finish(self, processes):
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            results.append((process.returncode, stdout, stderr))
        return results

    def test_check_only(self):
        before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.assertEqual(self.cli('--check'), 0)
        self.assertEqual(self.cli('--check', '--snapshot', str(self.snapshot)), 0)
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)

    def test_check_no_create(self):
        self.path.unlink()
        self.assertEqual(self.cli('--check', '--snapshot', str(self.snapshot)), 0)
        self.assertFalse(self.path.exists())

    def test_atomic_validation_failure(self):
        before = self.path.read_bytes()
        data = dataset()
        data['observations'][0]['price'] = -1
        self.snapshot.write_text(json.dumps(data))
        self.assertEqual(self.cli('--snapshot', str(self.snapshot)), 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('.history.json.*')), [])

    def test_atomic_replace_failure(self):
        before = self.path.read_bytes()
        with patch.object(spot.os, 'replace', side_effect=OSError('simulated failure')):
            with self.assertRaises(OSError):
                spot.write_atomic(self.path, b'new bytes')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('.history.json.*')), [])

    def test_cli_merge_idempotency(self):
        data = dataset()
        data['observations'][0]['effective_date'] = '2026-10-19'
        self.snapshot.write_bytes(spot.encode(data))
        self.assertEqual(self.cli('--snapshot', str(self.snapshot)), 0)
        self.assertEqual(len(spot.read(self.path)['observations']), 6)
        before = self.path.stat().st_mtime_ns
        self.assertEqual(self.cli('--snapshot', str(self.snapshot)), 0)
        self.assertEqual(self.path.stat().st_mtime_ns, before)

    def test_concurrent_distinct_appends_are_both_preserved(self):
        first = self.path.parent / 'first.json'
        second = self.path.parent / 'second.json'
        self.write_snapshot(first, 'B300', 7.11)
        self.write_snapshot(second, 'B200', 3.22)
        with spot.data_lock(self.path):
            processes = [self.start_cli(first), self.start_cli(second)]
            time.sleep(.35)
            self.assertTrue(all(process.poll() is None for process in processes), 'writers must wait for the target lock')
        results = self.finish(processes)
        self.assertEqual([result[0] for result in results], [0, 0], results)
        rows = spot.read(self.path)['observations']
        self.assertEqual(len(rows), 7)
        self.assertEqual({(r['product'], r['price']) for r in rows if r['effective_date'] == '2026-10-19'}, {('B300', 7.11), ('B200', 3.22)})

    def test_concurrent_conflict_fails_closed(self):
        first = self.path.parent / 'conflict-first.json'
        second = self.path.parent / 'conflict-second.json'
        self.write_snapshot(first, 'B300', 7.11)
        self.write_snapshot(second, 'B300', 7.12)
        with spot.data_lock(self.path):
            processes = [self.start_cli(first), self.start_cli(second)]
            time.sleep(.35)
            self.assertTrue(all(process.poll() is None for process in processes), 'writers must wait for the target lock')
        results = self.finish(processes)
        self.assertEqual(sorted(result[0] for result in results), [0, 1], results)
        rows = [r for r in spot.read(self.path)['observations'] if r['effective_date'] == '2026-10-19' and r['product'] == 'B300']
        self.assertEqual(len(rows), 1)
        self.assertIn(rows[0]['price'], (7.11, 7.12))

    def test_bad_existing(self):
        self.path.write_text('{bad')
        self.assertEqual(self.cli('--snapshot', str(self.snapshot)), 1)
        self.assertEqual(self.path.read_text(), '{bad')

    def test_duplicate_json_keys(self):
        self.snapshot.write_text('{"schema_version":1,"schema_version":1}')
        self.assertEqual(self.cli('--snapshot', str(self.snapshot)), 1)

    def test_missing_data(self):
        self.path.unlink()
        self.assertEqual(self.cli('--check'), 1)

    def test_oversized_input(self):
        self.snapshot.write_bytes(b' ' * (spot.LIMIT + 1))
        with self.assertRaises(ValueError):
            spot.read(self.snapshot)


if __name__ == '__main__':
    unittest.main()
