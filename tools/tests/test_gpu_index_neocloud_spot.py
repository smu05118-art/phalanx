import copy
import datetime as dt
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/neocloud_spot'
SPEC = importlib.util.spec_from_file_location(
    'gpu_index', ROOT / 'tools/build_neocloud_gpu_index.py')
gpu = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gpu)
UTC = dt.timezone.utc


def when(value):
    if isinstance(value, dt.datetime):
        return value
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def source(rows, marker='a'):
    return {
        'archive': 'index.json',
        'source_index_sha256': marker * 64,
        'latest_complete_timestamp': gpu.hour_text(
            max(row['interval_end'] for row in rows)),
    }


def row(sku, family, region, endpoint, price='1', collected=None,
        platform=None, title=None):
    endpoint = when(endpoint)
    collected = when(collected) if collected else endpoint + dt.timedelta(minutes=5)
    return {
        'sku_id': sku,
        'family': family,
        'region': region,
        'platform': platform or 'gpu-' + family.lower().replace(' ', '-'),
        'product_title': title or 'Preemptible NVIDIA ' + family,
        'price': Decimal(price),
        'interval_start': endpoint - dt.timedelta(hours=1),
        'interval_end': endpoint,
        'collected_time': collected,
    }


def raw_row(sku='sku-a', family='A100', region='r1',
            endpoint='2026-01-01T01:00:00Z', price='1',
            snapshot='2026-01-01T01:01:00Z',
            collected='2026-01-01T01:02:00Z', method=gpu.LAST):
    end = when(endpoint)
    return {
        'sku_id': sku,
        'product_title': 'Preemptible NVIDIA A100',
        'region': region,
        'platform': 'gpu-a100',
        'family': family,
        'currency': 'USD',
        'unit': 'USD/GPU-hour',
        'price': price,
        'interval_start': gpu.hour_text(end - dt.timedelta(hours=1)),
        'interval_end': gpu.hour_text(end),
        'method': method,
        'granularity': gpu.HOUR,
        'source_snapshot_time': snapshot,
        'collected_time': collected,
        'source_endpoint': gpu.SERIES,
        'source_sha256': '1' * 64,
    }


def bootstrap_rows(families, start, end, price='1'):
    start, end = when(start), when(end)
    collected = end + dt.timedelta(minutes=10)
    rows = []
    cursor = start
    while cursor <= end:
        for number, family in enumerate(families):
            rows.append(row(
                'sku-' + family.lower(), family, 'region-' + str(number),
                cursor, price, collected=collected,
            ))
        cursor += dt.timedelta(hours=1)
    return rows


def sku_weights(epoch):
    return {
        member['sku_id']: Fraction(
            member['effective_weight']['numerator'],
            member['effective_weight']['denominator'],
        )
        for family in epoch['families']
        for region in family['regions']
        for member in region['skus']
    }


class CurrentArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.source = gpu.read_archive(DATA)
        cls.published = json.loads((DATA / 'gpu-index.json').read_text())
        cls.generated = gpu.build_document(cls.rows, cls.source, cls.published)

    def test_current_archive_reproducibility(self):
        self.assertEqual(self.generated, self.published)
        self.assertEqual(gpu.encode(self.generated),
                         (DATA / 'gpu-index.json').read_bytes())
        self.assertEqual(self.generated['base'], {
            'timestamp': '2026-09-21T16:00:00Z', 'value': '100'})
        self.assertEqual(self.generated['processed_through'],
                         self.source['latest_complete_timestamp'])
        self.assertEqual(self.generated['methodology_version'],
                         gpu.METHODOLOGY_VERSION)
        self.assertTrue(all(
            epoch['methodology_version'] == gpu.METHODOLOGY_VERSION
            for epoch in self.generated['composition_epochs']))
        self.assertIn('retrospectively backcast',
                      self.generated['methodology']['bootstrap_policy'])
        self.assertIn('full elapsed interval',
                      self.generated['methodology']['gap_linking_policy'])
        base = when(self.generated['base']['timestamp'])
        processed = when(self.generated['processed_through'])
        expected_slots = int((processed - base) / dt.timedelta(hours=1)) + 1
        self.assertEqual(len(self.generated['levels']) + len(self.generated['gaps']),
                         expected_slots)

    def test_weights_sum_and_equal_family(self):
        epoch = self.generated['composition_epochs'][0]
        self.assertEqual(
            {family['family']: Fraction(
                family['effective_weight']['numerator'],
                family['effective_weight']['denominator'])
             for family in epoch['families']},
            {family: Fraction(1, 5) for family in
             ('B200', 'B300', 'H100', 'H200', 'RTX PRO 6000')},
        )
        self.assertEqual(sum(sku_weights(epoch).values(), Fraction()), Fraction(1))

    def test_schema_is_json_and_names_the_contract(self):
        schema = json.loads((ROOT / 'tools/neocloud_gpu_index.schema.json').read_text())
        self.assertEqual(schema['properties']['name']['const'], gpu.INDEX_NAME)
        self.assertEqual(schema['properties']['methodology_version']['const'],
                         gpu.METHODOLOGY_VERSION)
        self.assertFalse(schema['additionalProperties'])
        number = re.compile(schema['$defs']['decimal']['pattern'])
        self.assertFalse(number.fullmatch('0'))
        self.assertFalse(number.fullmatch('0.0'))
        self.assertTrue(all(number.fullmatch(level['value'])
                            for level in self.published['levels']))
        gpu.validate_existing(self.published)
        zero = copy.deepcopy(self.published)
        zero['levels'][0]['value'] = '0'
        with self.assertRaisesRegex(ValueError, 'nonpositive'):
            gpu.validate_existing(zero)
        unreduced = copy.deepcopy(self.published)
        unreduced['composition_epochs'][0]['families'][0]['effective_weight'] = {
            'numerator': 2, 'denominator': 10}
        with self.assertRaisesRegex(ValueError, 'weights mismatch'):
            gpu.validate_existing(unreduced)
        wrong_version = copy.deepcopy(self.published)
        wrong_version['methodology_version'] = 'future-v2'
        with self.assertRaisesRegex(ValueError, 'methodology version mismatch'):
            gpu.validate_existing(wrong_version)
        wrong_epoch_version = copy.deepcopy(self.published)
        wrong_epoch_version['composition_epochs'][0]['methodology_version'] = 'future-v2'
        with self.assertRaisesRegex(ValueError, 'weights mismatch'):
            gpu.validate_existing(wrong_epoch_version)

    def test_published_timestamps_must_be_on_processed_hourly_grid(self):
        before = copy.deepcopy(self.published)
        before['levels'].insert(0, {
            'timestamp': '2026-09-21T15:00:00Z', 'value': '100'})
        with self.assertRaisesRegex(ValueError, 'outside processed hourly grid'):
            gpu.validate_existing(before)
        off_grid = copy.deepcopy(self.published)
        off_grid['levels'].insert(1, {
            'timestamp': '2026-09-21T16:30:00Z', 'value': '100'})
        with self.assertRaisesRegex(ValueError, 'outside processed hourly grid'):
            gpu.validate_existing(off_grid)

    def test_each_post_bootstrap_epoch_strictly_adds_members(self):
        duplicate = copy.deepcopy(self.published)
        effective = when(duplicate['base']['timestamp']) + dt.timedelta(hours=1)
        active = gpu.epoch_ids(duplicate['composition_epochs'][0])
        catalog = {entry['sku_id']: entry for entry in duplicate['catalog']}
        duplicate['composition_epochs'].append(gpu.make_epoch(
            effective, 'qualified_addition', active, catalog))
        with self.assertRaisesRegex(ValueError, 'must add at least one SKU'):
            gpu.validate_existing(duplicate)

    def test_bootstrap_epoch_exactly_matches_catalog_bootstrap_flags(self):
        base = when('2026-01-10T00:00:00Z')
        rows = [row('sku-a', 'A', 'r-a', base),
                row('sku-b', 'B', 'r-b', base)]
        document = gpu.build_document(rows, source(rows))
        entry = next(item for item in document['catalog']
                     if item['sku_id'] == 'sku-b')
        entry['bootstrap'] = False
        entry['discovered_at'] = '2026-01-08T00:00:00Z'
        entry['seasoning_start'] = '2026-01-08T00:00:00Z'
        entry['qualified_at'] = '2026-01-09T23:00:00Z'
        with self.assertRaisesRegex(
                ValueError, 'bootstrap epoch/catalog membership mismatch'):
            gpu.validate_existing(document)


class MethodologyTests(unittest.TestCase):
    def test_first_publication_bootstraps_every_observed_sku(self):
        start = when('2026-01-01T00:00:00Z')
        rows = [
            row('sku-a', 'A', 'r-a', start, collected=when('2026-01-01T01:00:00Z')),
            row('sku-b', 'B', 'r-b', start, collected=when('2026-01-02T01:00:00Z')),
        ]
        document = gpu.build_document(rows, source(rows))
        self.assertEqual(document['base']['timestamp'], gpu.hour_text(start))
        self.assertTrue(all(entry['bootstrap'] for entry in document['catalog']))
        self.assertEqual(sku_weights(document['composition_epochs'][0]), {
            'sku-a': Fraction(1, 2), 'sku-b': Fraction(1, 2),
        })

    def test_new_family_seasons_then_changes_five_to_six_without_jump(self):
        families = ['A100', 'B100', 'C100', 'D100', 'E100']
        first_start = when('2026-01-01T00:00:00Z')
        first_end = when('2026-01-03T00:00:00Z')
        initial = bootstrap_rows(families, first_start, first_end)
        old = gpu.build_document(initial, source(initial, 'a'))
        old_levels = copy.deepcopy(old['levels'])
        old_epochs = copy.deepcopy(old['composition_epochs'])

        discovery = when('2026-01-03T00:30:00Z')
        pending_rows = bootstrap_rows(
            families, first_start, when('2026-01-03T23:00:00Z'))
        # A pre-discovery completed point records first collection; it cannot
        # count toward the 24-observation seasoning run.
        pending_rows.append(row('sku-f100', 'F100', 'region-f', first_end,
                                '999', collected=discovery))
        for offset in range(1, 24):
            endpoint = first_end + dt.timedelta(hours=offset)
            pending_rows.append(row(
                'sku-f100', 'F100', 'region-f', endpoint, '999',
                collected=endpoint + dt.timedelta(minutes=5),
            ))
        pending = gpu.build_document(pending_rows, source(pending_rows, 'b'), old)
        pending_entry = next(
            item for item in pending['catalog'] if item['sku_id'] == 'sku-f100')
        self.assertEqual(pending_entry['status'], 'pending')
        self.assertIsNone(pending_entry['qualified_at'])
        self.assertEqual(len(pending['composition_epochs']), 1)

        extended = bootstrap_rows(
            families, first_start, when('2026-01-05T01:00:00Z'))
        extended.append(row('sku-f100', 'F100', 'region-f', first_end,
                            '999', collected=discovery))
        for offset in range(1, 50):
            endpoint = first_end + dt.timedelta(hours=offset)
            if endpoint > when('2026-01-05T01:00:00Z'):
                break
            extended.append(row(
                'sku-f100', 'F100', 'region-f', endpoint, '999',
                collected=endpoint + dt.timedelta(minutes=5),
            ))
        new = gpu.build_document(extended, source(extended, 'c'), pending)

        self.assertEqual(new['levels'][:len(old_levels)], old_levels)
        self.assertEqual(new['composition_epochs'][:len(old_epochs)], old_epochs)
        self.assertEqual(new['levels'][:len(pending['levels'])], pending['levels'])
        entry = next(item for item in new['catalog'] if item['sku_id'] == 'sku-f100')
        self.assertEqual(entry['discovered_at'], '2026-01-03T00:30:00Z')
        self.assertEqual(entry['qualified_at'], '2026-01-04T00:00:00Z')
        self.assertEqual(entry['activation_time'], '2026-01-05T00:00:00Z')
        self.assertEqual(entry['status'], 'active')
        self.assertEqual(len(new['composition_epochs'][-1]['families']), 6)
        self.assertTrue(all(
            Fraction(item['effective_weight']['numerator'],
                     item['effective_weight']['denominator']) == Fraction(1, 6)
            for item in new['composition_epochs'][-1]['families']))
        levels = {item['timestamp']: item['value'] for item in new['levels']}
        self.assertEqual(levels['2026-01-04T23:00:00Z'],
                         levels['2026-01-05T00:00:00Z'])
        self.assertEqual(levels['2026-01-05T00:00:00Z'],
                         levels['2026-01-05T01:00:00Z'])

    def test_hierarchy_uses_family_then_region_then_sku_and_alias_is_not_member(self):
        t0, t1 = when('2026-02-01T00:00:00Z'), when('2026-02-01T01:00:00Z')
        collected = when('2026-02-01T02:00:00Z')
        rows = [
            row('a1', 'A', 'r1', t0, '1', collected, 'gpu-a-old'),
            row('a2', 'A', 'r1', t0, '1', collected, 'gpu-a'),
            row('a3', 'A', 'r2', t0, '1', collected, 'gpu-a'),
            row('b1', 'B', 'r1', t0, '1', collected, 'gpu-b'),
            row('a1', 'A', 'r1', t1, '4', collected, 'gpu-a-new'),
            row('a2', 'A', 'r1', t1, '1', collected, 'gpu-a'),
            row('a3', 'A', 'r2', t1, '1', collected, 'gpu-a'),
            row('b1', 'B', 'r1', t1, '1', collected, 'gpu-b'),
        ]
        document = gpu.build_document(rows, source(rows))
        weights = sku_weights(document['composition_epochs'][0])
        self.assertEqual(weights, {
            'a1': Fraction(1, 8), 'a2': Fraction(1, 8),
            'a3': Fraction(1, 4), 'b1': Fraction(1, 2),
        })
        a1 = next(item for item in document['catalog'] if item['sku_id'] == 'a1')
        self.assertEqual(a1['platforms'], ['gpu-a-new', 'gpu-a-old'])
        with localcontext() as context:
            context.prec = gpu.DECIMAL_PRECISION
            expected = Decimal(100) * (Decimal(4).ln(context=context) /
                                       Decimal(8)).exp(context=context)
        self.assertEqual(document['levels'][-1]['value'], gpu.decimal_text(expected))

    def test_missing_hours_are_explicit_gaps_and_never_forward_filled(self):
        t0 = when('2026-03-01T00:00:00Z')
        collected = when('2026-03-02T00:00:00Z')
        rows = [row('a', 'A', 'r', t0, '1', collected),
                row('b', 'B', 'r', t0, '1', collected)]
        for offset in (1, 2, 3):
            endpoint = t0 + dt.timedelta(hours=offset)
            rows.append(row('a', 'A', 'r', endpoint, str(2 ** offset), collected))
            if offset != 1:
                rows.append(row('b', 'B', 'r', endpoint, '1', collected))
        document = gpu.build_document(rows, source(rows))
        self.assertEqual([gap['timestamp'] for gap in document['gaps']],
                         ['2026-03-01T01:00:00Z'])
        self.assertNotIn('2026-03-01T01:00:00Z',
                         {item['timestamp'] for item in document['levels']})
        levels = {item['timestamp']: item['value'] for item in document['levels']}
        # The first level after the gap links from the last successful endpoint,
        # capturing the full 1 -> 4 move without inventing the missing hour.
        self.assertEqual(levels['2026-03-01T02:00:00Z'], '200')
        self.assertEqual(document['levels'][-1]['timestamp'],
                         '2026-03-01T03:00:00Z')

    def test_composition_change_without_linked_activation_level_fails_closed(self):
        start = when('2026-03-10T00:00:00Z')
        discovery = when('2026-03-12T00:30:00Z')
        activation = when('2026-03-14T00:00:00Z')
        initial = bootstrap_rows(['A'], start, when('2026-03-12T00:00:00Z'))
        old = gpu.build_document(initial, source(initial, 'a'))
        rows = []
        cursor = start
        while cursor <= when('2026-03-14T01:00:00Z'):
            if cursor != activation:
                rows.append(row('sku-a', 'A', 'region-0', cursor, '1',
                                collected=max(cursor + dt.timedelta(minutes=5),
                                              when('2026-03-12T00:10:00Z'))))
            cursor += dt.timedelta(hours=1)
        rows.append(row('sku-b', 'B', 'region-b', when('2026-03-12T00:00:00Z'),
                        '1', collected=discovery))
        for offset in range(1, 50):
            endpoint = when('2026-03-12T00:00:00Z') + dt.timedelta(hours=offset)
            if endpoint > when('2026-03-14T01:00:00Z'):
                break
            rows.append(row('sku-b', 'B', 'region-b', endpoint, '1',
                            collected=endpoint + dt.timedelta(minutes=5)))
        with self.assertRaisesRegex(ValueError, 'activation lacks a linked'):
            gpu.build_document(rows, source(rows, 'b'), old)

    def test_activating_sku_requires_price_at_composition_endpoint(self):
        start = when('2026-03-20T00:00:00Z')
        published_end = when('2026-03-22T00:00:00Z')
        activation = when('2026-03-24T00:00:00Z')
        initial = bootstrap_rows(['A'], start, published_end)
        old = gpu.build_document(initial, source(initial, 'a'))
        rows = bootstrap_rows(['A'], start, when('2026-03-24T01:00:00Z'))
        discovery = when('2026-03-22T00:30:00Z')
        rows.append(row('sku-b', 'B', 'region-b', published_end, '1',
                        collected=discovery))
        cursor = published_end + dt.timedelta(hours=1)
        while cursor <= when('2026-03-24T01:00:00Z'):
            if cursor != activation:
                rows.append(row('sku-b', 'B', 'region-b', cursor, '1',
                                collected=cursor + dt.timedelta(minutes=5)))
            cursor += dt.timedelta(hours=1)
        with self.assertRaisesRegex(
                ValueError, 'activating SKU missing price at composition endpoint'):
            gpu.build_document(rows, source(rows, 'b'), old)

    def test_later_backfill_does_not_move_published_qualification(self):
        start = when('2026-03-25T00:00:00Z')
        published_end = when('2026-03-27T23:00:00Z')
        initial = bootstrap_rows(['A'], start, start)
        old = gpu.build_document(initial, source(initial, 'a'))
        rows = bootstrap_rows(['A'], start, published_end)
        discovery = when('2026-03-25T00:30:00Z')
        rows.append(row('sku-b', 'B', 'region-b', start, '1',
                        collected=discovery))
        cursor = start + dt.timedelta(hours=1)
        missing = start + dt.timedelta(hours=12)
        while cursor <= published_end:
            if cursor != missing:
                rows.append(row('sku-b', 'B', 'region-b', cursor, '1',
                                collected=cursor + dt.timedelta(minutes=5)))
            cursor += dt.timedelta(hours=1)
        pending = gpu.build_document(rows, source(rows, 'b'), old)
        before = next(item for item in pending['catalog'] if item['sku_id'] == 'sku-b')
        self.assertEqual(before['qualified_at'], '2026-03-26T12:00:00Z')
        self.assertEqual(before['activation_time'], '2026-03-27T00:00:00Z')

        # The backfill creates an earlier valid run, but an already published
        # lifecycle remains immutable while its original run is still valid.
        backfilled = rows + [row('sku-b', 'B', 'region-b', missing, '1',
                                 collected=missing + dt.timedelta(minutes=5))]
        rebuilt = gpu.build_document(backfilled, source(backfilled, 'c'), pending)
        after = next(item for item in rebuilt['catalog'] if item['sku_id'] == 'sku-b')
        self.assertEqual(after['qualified_at'], before['qualified_at'])
        self.assertEqual(after['activation_time'], before['activation_time'])

    def test_published_epoch_rejects_lost_new_sku_anchor(self):
        start = when('2026-03-30T00:00:00Z')
        discovery = when('2026-03-30T00:30:00Z')
        activation = when('2026-04-01T00:00:00Z')
        initial = bootstrap_rows(['A'], start, start)
        old = gpu.build_document(initial, source(initial, '0'))
        rows = bootstrap_rows(['A'], start, activation)
        rows.append(row('sku-b', 'B', 'region-b', start, '1',
                        collected=discovery))
        cursor = start + dt.timedelta(hours=1)
        while cursor <= activation:
            rows.append(row('sku-b', 'B', 'region-b', cursor, '1',
                            collected=cursor + dt.timedelta(minutes=5)))
            cursor += dt.timedelta(hours=1)
        published = gpu.build_document(rows, source(rows, 'a'), old)
        self.assertEqual(published['composition_epochs'][-1]['effective_time'],
                         gpu.hour_text(activation))

        regressed = [item for item in rows
                     if not (item['sku_id'] == 'sku-b' and
                             item['interval_end'] == activation)]
        extension = activation + dt.timedelta(hours=1)
        regressed.extend([
            row('sku-a', 'A', 'region-0', extension, '1'),
            row('sku-b', 'B', 'region-b', extension, '1'),
        ])
        with self.assertRaisesRegex(
                ValueError, 'published activating SKU missing price'):
            gpu.build_document(regressed, source(regressed, 'b'), published)

    def test_backfill_does_not_rewrite_a_published_gap(self):
        t0 = when('2026-04-01T00:00:00Z')
        collected = when('2026-04-02T00:00:00Z')
        rows = [row('a', 'A', 'r', t0, '1', collected),
                row('b', 'B', 'r', t0, '1', collected)]
        for offset in (1, 2):
            endpoint = t0 + dt.timedelta(hours=offset)
            rows.append(row('a', 'A', 'r', endpoint, '1', collected))
            if offset == 2:
                rows.append(row('b', 'B', 'r', endpoint, '1', collected))
        old = gpu.build_document(rows, source(rows, 'a'))
        backfilled = rows + [row(
            'b', 'B', 'r', t0 + dt.timedelta(hours=1), '1', collected)]
        new = gpu.build_document(backfilled, source(backfilled, 'b'), old)
        self.assertEqual(new['levels'], old['levels'])
        self.assertEqual(new['gaps'], old['gaps'])
        self.assertEqual(new['composition_epochs'], old['composition_epochs'])

    def test_late_new_sku_seasons_only_after_unpublished_boundary(self):
        start = when('2026-07-01T00:00:00Z')
        published_end = when('2026-07-05T00:00:00Z')
        initial = bootstrap_rows(['A'], start, published_end)
        old = gpu.build_document(initial, source(initial, 'a'))
        extended_end = when('2026-07-06T00:00:00Z')
        rows = bootstrap_rows(['A'], start, extended_end)
        source_discovery = when('2026-07-02T00:30:00Z')
        cursor = start
        while cursor <= extended_end:
            rows.append(row(
                'sku-b', 'B', 'region-b', cursor, '1',
                collected=max(source_discovery, cursor + dt.timedelta(minutes=5))))
            cursor += dt.timedelta(hours=1)
        document = gpu.build_document(rows, source(rows, 'b'), old)
        entry = next(item for item in document['catalog'] if item['sku_id'] == 'sku-b')
        self.assertEqual(entry['discovered_at'], '2026-07-02T00:30:00Z')
        self.assertEqual(entry['seasoning_start'], '2026-07-05T00:00:00Z')
        self.assertEqual(entry['qualified_at'], '2026-07-06T00:00:00Z')
        self.assertEqual(entry['activation_time'], '2026-07-07T00:00:00Z')
        self.assertEqual(entry['status'], 'pending')
        self.assertEqual(document['composition_epochs'], old['composition_epochs'])

    def test_zero_negative_and_future_rows_fail_closed(self):
        for price in ('0', '-1'):
            with self.subTest(price=price), self.assertRaisesRegex(ValueError, 'nonpositive'):
                gpu.validate_row(raw_row(price=price))
        with self.assertRaisesRegex(ValueError, 'future or incomplete'):
            gpu.validate_row(raw_row(
                endpoint='2026-01-01T02:00:00Z',
                snapshot='2026-01-01T01:59:00Z',
                collected='2026-01-01T02:01:00Z'))


class PropertySweepTests(unittest.TestCase):
    def test_hierarchical_effective_weights_sum_exactly_for_varied_shapes(self):
        effective = when('2026-06-01T00:00:00Z')
        for family_count in range(1, 9):
            for region_count in range(1, 5):
                for sku_count in range(1, 4):
                    with self.subTest(
                            families=family_count, regions=region_count,
                            skus=sku_count):
                        catalog = {}
                        for family_number in range(family_count):
                            for region_number in range(region_count):
                                for sku_number in range(sku_count):
                                    sku = f's-{family_number}-{region_number}-{sku_number}'
                                    catalog[sku] = {
                                        'family': f'F{family_number}',
                                        'region': f'R{region_number}',
                                    }
                        epoch = gpu.make_epoch(
                            effective, 'bootstrap', set(catalog), catalog)
                        weights = sku_weights(epoch)
                        self.assertEqual(sum(weights.values(), Fraction()), Fraction(1))
                        for family in epoch['families']:
                            family_weight = Fraction(
                                family['effective_weight']['numerator'],
                                family['effective_weight']['denominator'])
                            self.assertEqual(family_weight,
                                             Fraction(1, family_count))
                            member_sum = sum((
                                weights[member['sku_id']]
                                for region in family['regions']
                                for member in region['skus']
                            ), Fraction())
                            self.assertEqual(member_sum, family_weight)

    def test_epoch_serialization_is_permutation_invariant(self):
        effective = when('2026-06-01T00:00:00Z')
        entries = {
            'z': {'family': 'B', 'region': 'r2'},
            'a': {'family': 'A', 'region': 'r1'},
            'm': {'family': 'A', 'region': 'r1'},
        }
        forward = gpu.make_epoch(effective, 'bootstrap', set(entries), entries)
        reverse = gpu.make_epoch(
            effective, 'bootstrap', set(reversed(entries)),
            dict(reversed(list(entries.items()))))
        self.assertEqual(forward, reverse)


class ArchiveAndIOTests(unittest.TestCase):
    def write_archive(self, root):
        history = root / 'history'
        average = root / 'imported-average'
        history.mkdir(parents=True)
        average.mkdir()
        last_rows = [raw_row(endpoint='2026-05-01T01:00:00Z',
                             snapshot='2026-05-01T01:01:00Z',
                             collected='2026-05-01T01:02:00Z'),
                     raw_row(endpoint='2026-05-01T02:00:00Z', price='2',
                             snapshot='2026-05-01T02:01:00Z',
                             collected='2026-05-01T02:02:00Z')]
        avg_rows = [dict(raw_row(), method='METHOD_AVG_PRICE', price='999')]
        last_payload = gpu.encode({'schema_version': 2, 'observations': last_rows})
        avg_payload = gpu.encode({'schema_version': 2, 'observations': avg_rows})
        (history / '2026-05.json').write_bytes(last_payload)
        (average / '2026-05.json').write_bytes(avg_payload)
        manifest = [
            {'count': 2, 'end': '2026-05-01T02:00:00Z', 'method': gpu.LAST,
             'path': 'history/2026-05.json',
             'sha256': hashlib.sha256(last_payload).hexdigest(),
             'start': '2026-05-01T00:00:00Z'},
            {'count': 1, 'end': '2026-05-01T01:00:00Z',
             'method': 'METHOD_AVG_PRICE', 'path': 'imported-average/2026-05.json',
             'sha256': hashlib.sha256(avg_payload).hexdigest(),
             'start': '2026-05-01T00:00:00Z'},
        ]
        index = {
            'schema_version': 2,
            'collected_time': '2026-05-01T02:02:00Z',
            'method': gpu.LAST,
            'granularity': gpu.HOUR,
            'shards': manifest,
            'latest_complete_timestamp': '2026-05-01T02:00:00Z',
        }
        (root / 'index.json').write_bytes(gpu.encode(index))

    def test_archive_reads_last_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_archive(root)
            rows, _ = gpu.read_archive(root)
            self.assertEqual([row['price'] for row in rows],
                             [Decimal('1'), Decimal('2')])

    def test_deterministic_atomic_noop_and_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'gpu-index.json'
            with self.assertRaisesRegex(ValueError, 'missing'):
                gpu.build_index(DATA, output, check=True)
            self.assertTrue(gpu.build_index(DATA, output))
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            before = output.read_bytes(), output.stat().st_mtime_ns
            self.assertFalse(gpu.build_index(DATA, output))
            self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), before)
            self.assertFalse(gpu.build_index(DATA, output, check=True))
            self.assertEqual(gpu.main([
                '--data', str(DATA), '--output', str(output), '--check']), 0)

    def test_atomic_replace_failure_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'out.json'
            path.write_bytes(b'old\n')
            with patch.object(gpu.os, 'replace', side_effect=OSError('boom')):
                with self.assertRaises(OSError):
                    gpu.write_atomic(path, b'new\n')
            self.assertEqual(path.read_bytes(), b'old\n')
            self.assertEqual(list(path.parent.glob('.out.json.*')), [])


if __name__ == '__main__':
    unittest.main()
