#!/usr/bin/env python3
"""Build the append-only Nebius equal-family GPU spot price index.

Only completed hourly METHOD_LAST_PRICE observations are consumed.  The index
is chain linked, so a composition change never introduces a price-level jump.
"""

import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile


INDEX_ID = 'nebius-gpu-spot-equal-family-price-index'
INDEX_NAME = 'Nebius GPU Spot Equal-Family Price Index'
LAST = 'METHOD_LAST_PRICE'
HOUR = 'GRANULARITY_HOUR_1'
SERIES = 'https://api.nebius.cloud/billing/v1alpha1/spot-price/list-series'
SCHEMA_VERSION = 1
METHODOLOGY_VERSION = 'equal-family-chain-v1'
DECIMAL_PRECISION = 80
FILE_LIMIT = 5 * 1024 * 1024
PRICE_RE = re.compile(r'-?(?:0|[1-9]\d{0,30})(?:\.\d{1,30})?')
INDEX_NUMBER_RE = re.compile(r'(?:0|[1-9]\d{0,30})(?:\.\d{1,100})?')
STAMP_RE = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z')
SHA_RE = re.compile(r'[0-9a-f]{64}')
PLATFORM_RE = re.compile(r'gpu-[a-z0-9]+(?:-[a-z0-9]+)*')
FAMILY_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9 .+_-]{0,63}')
ROW_FIELDS = {
    'sku_id', 'product_title', 'region', 'platform', 'family', 'currency',
    'unit', 'price', 'interval_start', 'interval_end', 'method',
    'granularity', 'source_snapshot_time', 'collected_time',
    'source_endpoint', 'source_sha256',
}
TOP_FIELDS = {
    'schema_version', 'index_id', 'name', 'currency', 'unit', 'granularity',
    'source_method', 'base', 'latest_timestamp', 'processed_through',
    'methodology_version', 'methodology', 'source', 'catalog',
    'composition_epochs', 'levels', 'gaps',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def object_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(payload):
    require(len(payload) <= FILE_LIMIT, 'JSON file exceeds 5 MiB')
    return json.loads(
        payload,
        object_pairs_hook=object_pairs,
        parse_constant=lambda value: require(False, 'invalid JSON constant: ' + value),
    )


def encode(value):
    payload = (json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        allow_nan=False,
    ) + '\n').encode()
    require(len(payload) <= FILE_LIMIT, 'gpu index exceeds 5 MiB')
    return payload


def read_bytes(path):
    require(not path.is_symlink(), 'symlink rejected: ' + str(path))
    payload = path.read_bytes()
    require(len(payload) <= FILE_LIMIT, 'JSON file exceeds 5 MiB: ' + str(path))
    return payload


def stamp(value, field='timestamp'):
    require(type(value) is str and STAMP_RE.fullmatch(value) is not None,
            'invalid UTC ' + field)
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('invalid UTC ' + field) from exc
    require(parsed.tzinfo == dt.timezone.utc, 'timestamp must be UTC')
    return parsed


def hour_text(value):
    require(value.tzinfo == dt.timezone.utc and
            value.minute == value.second == value.microsecond == 0,
            'unaligned hourly timestamp')
    return value.strftime('%Y-%m-%dT%H:%M:%SZ')


def positive_decimal(value, field='price', pattern=PRICE_RE):
    require(type(value) is str and pattern.fullmatch(value) is not None,
            'invalid Decimal ' + field)
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid Decimal ' + field) from exc
    require(number.is_finite() and number > 0, 'nonpositive ' + field)
    return number


def decimal_text(value):
    require(value.is_finite() and value > 0, 'nonpositive index level')
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text


def text(value, field, pattern=None):
    require(type(value) is str and 0 < len(value) <= 512 and
            all(ord(char) >= 32 for char in value), 'invalid ' + field)
    if pattern is not None:
        require(pattern.fullmatch(value) is not None, 'invalid ' + field)
    return value


def rational(value):
    require(type(value) is Fraction and value > 0, 'invalid rational weight')
    return {'numerator': value.numerator, 'denominator': value.denominator}


def parse_rational(value, field='weight'):
    require(type(value) is dict and set(value) == {'numerator', 'denominator'},
            'invalid ' + field)
    numerator, denominator = value['numerator'], value['denominator']
    require(type(numerator) is int and type(denominator) is int and
            numerator > 0 and denominator > 0, 'invalid ' + field)
    result = Fraction(numerator, denominator)
    require(result.numerator == numerator and result.denominator == denominator,
            'weight must be reduced')
    return result


def validate_row(row, archive_collected_time=None):
    require(type(row) is dict and set(row) == ROW_FIELDS,
            'history row fields mismatch')
    for key in ('sku_id', 'product_title', 'region'):
        text(row[key], key)
    text(row['platform'], 'platform', PLATFORM_RE)
    text(row['family'], 'family', FAMILY_RE)
    require(row['currency'] == 'USD' and row['unit'] == 'USD/GPU-hour',
            'history currency/unit mismatch')
    require(row['method'] == LAST and row['granularity'] == HOUR,
            'history must be hourly METHOD_LAST_PRICE')
    require(row['source_endpoint'] == SERIES, 'history endpoint mismatch')
    require(type(row['source_sha256']) is str and
            SHA_RE.fullmatch(row['source_sha256']) is not None,
            'invalid source hash')
    price = positive_decimal(row['price'])
    start = stamp(row['interval_start'], 'interval_start')
    end = stamp(row['interval_end'], 'interval_end')
    snapshot = stamp(row['source_snapshot_time'], 'source_snapshot_time')
    collected = stamp(row['collected_time'], 'collected_time')
    require(end - start == dt.timedelta(hours=1) and
            end.minute == end.second == end.microsecond == 0,
            'history interval is not one completed UTC hour')
    require(end <= snapshot <= collected, 'future or incomplete history row')
    if archive_collected_time is not None:
        require(collected <= archive_collected_time,
                'row collected after archive collection time')
    return {
        'sku_id': row['sku_id'], 'family': row['family'], 'region': row['region'],
        'platform': row['platform'], 'product_title': row['product_title'],
        'price': price, 'interval_start': start, 'interval_end': end,
        'collected_time': collected,
    }


def _safe_manifest_path(root, value):
    require(type(value) is str and value, 'invalid shard path')
    relative = PurePosixPath(value)
    require(not relative.is_absolute() and '..' not in relative.parts and
            relative.parts and relative.parts[0] == 'history',
            'LAST shard must be below history/')
    path = root.joinpath(*relative.parts)
    require(path.parent.resolve().is_relative_to(root.resolve()),
            'shard escapes archive root')
    return path


def read_archive(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'invalid archive directory')
    index_path = root / 'index.json'
    index_payload = read_bytes(index_path)
    index = decode(index_payload)
    required = {
        'schema_version', 'collected_time', 'method', 'granularity', 'shards',
        'latest_complete_timestamp',
    }
    require(type(index) is dict and required <= set(index), 'archive index fields')
    require(index['schema_version'] == 2 and index['method'] == LAST and
            index['granularity'] == HOUR, 'archive index contract mismatch')
    archive_collected = stamp(index['collected_time'], 'archive collected_time')
    require(type(index['shards']) is list and
            all(type(entry) is dict for entry in index['shards']),
            'archive shards must be an array of objects')
    selected = [entry for entry in index['shards']
                if type(entry) is dict and entry.get('method') == LAST]
    require(selected, 'archive has no METHOD_LAST_PRICE shard')
    rows, keys, paths = [], set(), set()
    for entry in selected:
        require(set(entry) == {'count', 'end', 'method', 'path', 'sha256', 'start'},
                'LAST shard manifest fields mismatch')
        require(type(entry['count']) is int and entry['count'] > 0,
                'invalid shard count')
        require(type(entry['sha256']) is str and
                SHA_RE.fullmatch(entry['sha256']) is not None, 'invalid shard hash')
        path = _safe_manifest_path(root, entry['path'])
        require(entry['path'] not in paths, 'duplicate shard path')
        paths.add(entry['path'])
        payload = read_bytes(path)
        require(hashlib.sha256(payload).hexdigest() == entry['sha256'],
                'shard hash mismatch: ' + entry['path'])
        document = decode(payload)
        require(type(document) is dict and set(document) == {'schema_version', 'observations'} and
                document['schema_version'] == 2 and type(document['observations']) is list,
                'shard document contract mismatch')
        shard_rows = []
        for raw in document['observations']:
            row = validate_row(raw, archive_collected)
            key = (row['sku_id'], row['interval_end'])
            require(key not in keys, 'duplicate LAST observation: ' + repr(key))
            keys.add(key)
            shard_rows.append(row)
        require(len(shard_rows) == entry['count'], 'shard count mismatch')
        require(shard_rows, 'empty LAST shard')
        require(hour_text(min(row['interval_start'] for row in shard_rows)) == entry['start'] and
                hour_text(max(row['interval_end'] for row in shard_rows)) == entry['end'],
                'shard range mismatch')
        rows.extend(shard_rows)
    rows.sort(key=lambda row: (row['interval_end'], row['sku_id']))
    latest = hour_text(max(row['interval_end'] for row in rows))
    require(index['latest_complete_timestamp'] == latest,
            'archive latest_complete_timestamp mismatch')
    return rows, {
        'archive': 'index.json',
        'source_index_sha256': hashlib.sha256(index_payload).hexdigest(),
        'latest_complete_timestamp': latest,
    }


def methodology():
    return {
        'activation_observations': 24,
        'activation_schedule': 'next_utc_00:00_after_qualification',
        'bootstrap_policy': 'initial reviewed basket is retrospectively backcast before first publication',
        'calculation': 'chain-linked hierarchical geometric price relatives',
        'family_weighting': 'equal',
        'gap_linking_policy': 'resume from last complete basket over the full elapsed interval',
        'late_discovery_policy': 'after bootstrap, season from first unpublished endpoint; never backdate',
        'missing_policy': 'record missing endpoints; no interpolation or forward fill',
        'nonpositive_policy': 'reject',
        'region_weighting': 'equal within family',
        'sku_weighting': 'equal within region',
    }


def catalog_facts(rows):
    facts = {}
    prices = {}
    for row in rows:
        sku = row['sku_id']
        fact = facts.get(sku)
        if fact is None:
            fact = {
                'sku_id': sku, 'family': row['family'], 'region': row['region'],
                'platforms': set(), 'product_titles': set(),
                'discovered_at': row['collected_time'],
                'first_observation_end': row['interval_end'],
            }
            facts[sku] = fact
        require(fact['family'] == row['family'] and fact['region'] == row['region'],
                'SKU changed family or region: ' + sku)
        fact['platforms'].add(row['platform'])
        fact['product_titles'].add(row['product_title'])
        fact['discovered_at'] = min(fact['discovered_at'], row['collected_time'])
        fact['first_observation_end'] = min(
            fact['first_observation_end'], row['interval_end'])
        prices.setdefault(sku, {})[row['interval_end']] = row['price']
    return facts, prices


def qualification_time(price_map, discovered_at):
    run = 0
    previous = None
    for endpoint in sorted(time for time in price_map if time > discovered_at):
        run = run + 1 if previous is not None and endpoint - previous == dt.timedelta(hours=1) else 1
        previous = endpoint
        if run == 24:
            return endpoint
    return None


def has_qualification_run(price_map, seasoning_start, qualified_at):
    first = qualified_at - dt.timedelta(hours=23)
    return first > seasoning_start and all(
        first + dt.timedelta(hours=offset) in price_map
        for offset in range(24)
    )


def next_midnight(value):
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + dt.timedelta(days=1)


def make_epoch(effective_time, reason, active_ids, catalog_by_id):
    grouped = {}
    for sku in sorted(active_ids):
        entry = catalog_by_id[sku]
        grouped.setdefault(entry['family'], {}).setdefault(entry['region'], []).append(sku)
    require(grouped, 'composition cannot be empty')
    family_count = len(grouped)
    families = []
    for family in sorted(grouped):
        regions_map = grouped[family]
        region_count = len(regions_map)
        regions = []
        for region in sorted(regions_map):
            skus = sorted(regions_map[region])
            sku_count = len(skus)
            regions.append({
                'region': region,
                'weight_within_family': rational(Fraction(1, region_count)),
                'effective_weight': rational(Fraction(1, family_count * region_count)),
                'skus': [{
                    'sku_id': sku,
                    'weight_within_region': rational(Fraction(1, sku_count)),
                    'effective_weight': rational(
                        Fraction(1, family_count * region_count * sku_count)),
                } for sku in skus],
            })
        families.append({
            'family': family,
            'effective_weight': rational(Fraction(1, family_count)),
            'regions': regions,
        })
    return {
        'effective_time': hour_text(effective_time),
        'methodology_version': METHODOLOGY_VERSION,
        'reason': reason,
        'families': families,
    }


def epoch_ids(epoch):
    return {
        sku['sku_id']
        for family in epoch['families']
        for region in family['regions']
        for sku in region['skus']
    }


def price_return(prices, active_ids, catalog_by_id, start, end):
    by_family = {}
    for sku in active_ids:
        if start not in prices.get(sku, {}) or end not in prices.get(sku, {}):
            return None
        entry = catalog_by_id[sku]
        by_family.setdefault(entry['family'], {}).setdefault(entry['region'], []).append(sku)
    require(by_family, 'active basket is empty')
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        family_logs = []
        for family in sorted(by_family):
            region_logs = []
            for region in sorted(by_family[family]):
                sku_logs = []
                for sku in sorted(by_family[family][region]):
                    ratio = prices[sku][end] / prices[sku][start]
                    require(ratio > 0, 'nonpositive price relative')
                    sku_logs.append(ratio.ln(context=context))
                region_logs.append(sum(sku_logs, Decimal(0)) / Decimal(len(sku_logs)))
            family_logs.append(sum(region_logs, Decimal(0)) / Decimal(len(region_logs)))
        total_log = sum(family_logs, Decimal(0)) / Decimal(len(family_logs))
        return total_log.exp(context=context)


def validate_catalog_entry(entry):
    fields = {
        'sku_id', 'family', 'region', 'platforms', 'product_titles',
        'discovered_at', 'seasoning_start', 'first_observation_end',
        'bootstrap', 'status', 'qualified_at', 'activation_time',
    }
    require(type(entry) is dict and set(entry) == fields, 'catalog fields mismatch')
    text(entry['sku_id'], 'sku_id')
    text(entry['family'], 'family', FAMILY_RE)
    text(entry['region'], 'region')
    require(type(entry['platforms']) is list and entry['platforms'] == sorted(set(entry['platforms'])) and
            entry['platforms'], 'invalid catalog platforms')
    for platform in entry['platforms']:
        text(platform, 'platform', PLATFORM_RE)
    require(type(entry['product_titles']) is list and
            entry['product_titles'] == sorted(set(entry['product_titles'])) and
            entry['product_titles'], 'invalid catalog product titles')
    for title in entry['product_titles']:
        text(title, 'product_title')
    discovered = stamp(entry['discovered_at'], 'discovered_at')
    seasoning = stamp(entry['seasoning_start'], 'seasoning_start')
    first = stamp(entry['first_observation_end'], 'first_observation_end')
    require(seasoning >= discovered, 'seasoning starts before discovery')
    require(first.minute == first.second == first.microsecond == 0,
            'first observation is not hourly')
    require(type(entry['bootstrap']) is bool and entry['status'] in ('active', 'pending'),
            'invalid catalog status')
    qualified = None if entry['qualified_at'] is None else stamp(entry['qualified_at'], 'qualified_at')
    activation = None if entry['activation_time'] is None else stamp(entry['activation_time'], 'activation_time')
    if entry['bootstrap']:
        require(qualified is None and activation is not None, 'invalid bootstrap lifecycle')
    else:
        require((qualified is None) == (activation is None), 'invalid pending lifecycle')
        if qualified is not None:
            require(qualified > seasoning and
                    qualified.minute == qualified.second == qualified.microsecond == 0 and
                    activation == next_midnight(qualified),
                    'invalid qualification schedule')
    return discovered, seasoning, first, qualified, activation


def validate_existing(document):
    require(type(document) is dict and set(document) == TOP_FIELDS,
            'gpu index top-level fields mismatch')
    require(document['schema_version'] == SCHEMA_VERSION and
            document['index_id'] == INDEX_ID and document['name'] == INDEX_NAME and
            document['currency'] == 'USD' and document['unit'] == 'index_points' and
            document['granularity'] == HOUR and document['source_method'] == LAST,
            'gpu index identity mismatch')
    require(document['methodology_version'] == METHODOLOGY_VERSION,
            'gpu index methodology version mismatch')
    require(document['methodology'] == methodology(), 'gpu index methodology mismatch')
    require(type(document['base']) is dict and set(document['base']) == {'timestamp', 'value'} and
            document['base']['value'] == '100', 'invalid index base')
    base = stamp(document['base']['timestamp'], 'base timestamp')
    processed = stamp(document['processed_through'], 'processed_through')
    require(base.minute == base.second == base.microsecond == 0 and processed >= base,
            'invalid processed range')
    require(type(document['catalog']) is list and document['catalog'], 'empty catalog')
    require([entry.get('sku_id') for entry in document['catalog']] ==
            sorted(entry.get('sku_id') for entry in document['catalog']),
            'catalog is not sorted')
    catalog = {}
    for entry in document['catalog']:
        _, _, _, _, activation = validate_catalog_entry(entry)
        if entry['bootstrap']:
            require(activation == base, 'bootstrap activation must equal base')
        require(entry['sku_id'] not in catalog, 'duplicate catalog SKU')
        catalog[entry['sku_id']] = entry
    require(type(document['composition_epochs']) is list and
            document['composition_epochs'], 'empty composition epochs')
    epochs = document['composition_epochs']
    times = [stamp(epoch.get('effective_time'), 'epoch effective_time')
             for epoch in epochs]
    require(times == sorted(set(times)) and times[0] == base and times[-1] <= processed,
            'invalid composition epoch ordering')
    require(epoch_ids(epochs[0]) == {
        sku for sku, entry in catalog.items() if entry['bootstrap']
    }, 'bootstrap epoch/catalog membership mismatch')
    active = set()
    for number, (epoch, effective) in enumerate(zip(epochs, times)):
        reason = 'bootstrap' if number == 0 else 'qualified_addition'
        ids = epoch_ids(epoch)
        require(ids and ids <= set(catalog),
                'composition contains an invalid catalog SKU')
        require((number == 0 and not active) or ids > active,
                'each composition epoch must add at least one SKU')
        require(epoch == make_epoch(effective, reason, ids, catalog),
                'composition epoch weights mismatch')
        for sku in ids - active:
            require(catalog[sku]['activation_time'] == hour_text(effective),
                    'catalog/epoch activation mismatch')
        active = ids
    for sku, entry in catalog.items():
        activation = stamp(entry['activation_time'], 'activation_time') \
            if entry['activation_time'] is not None else None
        expected_status = 'active' if sku in active else 'pending'
        require(entry['status'] == expected_status, 'catalog status mismatch')
        require(activation is None or activation > processed or sku in active,
                'elapsed activation missing composition epoch')
    require(type(document['levels']) is list and document['levels'], 'empty index levels')
    require(type(document['gaps']) is list, 'gaps must be an array')
    levels = {}
    for level in document['levels']:
        require(type(level) is dict and set(level) == {'timestamp', 'value'},
                'level fields mismatch')
        when = stamp(level['timestamp'], 'level timestamp')
        require(when.minute == when.second == when.microsecond == 0 and
                base <= when <= processed,
                'level outside processed hourly grid')
        require(when not in levels, 'duplicate level timestamp')
        positive_decimal(level['value'], 'index level', INDEX_NUMBER_RE)
        levels[when] = level
    require(list(levels) == sorted(levels), 'levels are not sorted')
    gaps = {}
    for gap in document['gaps']:
        require(type(gap) is dict and set(gap) == {'timestamp', 'reason'} and
                gap['reason'] == 'missing_active_observation', 'gap fields mismatch')
        when = stamp(gap['timestamp'], 'gap timestamp')
        require(when.minute == when.second == when.microsecond == 0 and
                base <= when <= processed,
                'gap outside processed hourly grid')
        require(when not in gaps and when not in levels, 'duplicate level/gap timestamp')
        gaps[when] = gap
    require(list(gaps) == sorted(gaps), 'gaps are not sorted')
    require(base in levels and levels[base]['value'] == '100', 'base level missing')
    cursor = base
    while cursor < processed:
        cursor += dt.timedelta(hours=1)
        require(cursor in levels or cursor in gaps, 'unrecorded processed timestamp')
    require(max(levels) <= processed and max(gaps, default=base) <= processed,
            'published value after processed_through')
    latest = hour_text(max(levels))
    require(document['latest_timestamp'] == latest, 'latest_timestamp mismatch')
    require(type(document['source']) is dict and
            set(document['source']) == {'archive', 'source_index_sha256', 'latest_complete_timestamp'} and
            document['source']['archive'] == 'index.json' and
            SHA_RE.fullmatch(document['source']['source_index_sha256'] or '') is not None,
            'invalid source metadata')
    stamp(document['source']['latest_complete_timestamp'], 'source latest timestamp')
    return base, processed, catalog, levels, gaps, epochs


def replay_existing(document, prices, catalog_by_id):
    base, processed, _, levels, gaps, epochs = validate_existing(document)
    events = {stamp(epoch['effective_time']): epoch for epoch in epochs}
    active = epoch_ids(events[base])
    require(all(base in prices.get(sku, {}) for sku in active),
            'source no longer contains bootstrap prices')
    last_value = Decimal('100')
    last_level_time = base
    cursor = base
    while cursor < processed:
        endpoint = cursor + dt.timedelta(hours=1)
        relative = price_return(
            prices, active, catalog_by_id, last_level_time, endpoint)
        if endpoint in levels:
            require(relative is not None, 'published level lacks source observations')
            with localcontext() as context:
                context.prec = DECIMAL_PRECISION
                expected = decimal_text(last_value * relative)
            require(expected == levels[endpoint]['value'],
                    'published level would change at ' + hour_text(endpoint))
            last_value = Decimal(expected)
            last_level_time = endpoint
        else:
            require(endpoint in gaps, 'published history has an unrecorded timestamp')
        if endpoint in events:
            require(endpoint in levels,
                    'composition activation lacks a linked index level')
            next_active = epoch_ids(events[endpoint])
            require(all(endpoint in prices.get(sku, {})
                        for sku in next_active - active),
                    'published activating SKU missing price at composition endpoint')
            active = next_active
        cursor = endpoint
    return active, last_value, last_level_time


def build_document(rows, source, existing=None):
    require(type(rows) is list and rows, 'empty LAST history')
    facts, prices = catalog_facts(rows)
    latest_source = max(row['interval_end'] for row in rows)
    require(source['latest_complete_timestamp'] == hour_text(latest_source),
            'source metadata latest timestamp mismatch')

    existing_catalog = {}
    if existing is not None:
        _, processed, existing_catalog, _, _, existing_epochs = validate_existing(existing)
        require(latest_source >= processed, 'source history truncated before published index')
        require(set(existing_catalog) <= set(facts), 'published catalog SKU disappeared')
        base = stamp(existing['base']['timestamp'], 'base timestamp')
    else:
        processed, existing_epochs = None, []
        bootstrap_ids = set(facts)
        common = set.intersection(*(set(prices[sku]) for sku in sorted(bootstrap_ids)))
        require(common, 'bootstrap basket has no common completed endpoint')
        base = min(common)
        require(base <= latest_source, 'invalid base endpoint')

    catalog = []
    for sku in sorted(facts):
        fact = facts[sku]
        previous = existing_catalog.get(sku)
        if previous is not None:
            require(previous['family'] == fact['family'] and
                    previous['region'] == fact['region'],
                    'published SKU identity changed: ' + sku)
            discovered = stamp(previous['discovered_at'], 'discovered_at')
            seasoning = stamp(previous['seasoning_start'], 'seasoning_start')
            first_observation = stamp(previous['first_observation_end'], 'first_observation_end')
            bootstrap = previous['bootstrap']
            qualified = (None if previous['qualified_at'] is None else
                         stamp(previous['qualified_at'], 'qualified_at'))
            activation = (None if previous['activation_time'] is None else
                          stamp(previous['activation_time'], 'activation_time'))
            platforms = sorted(set(previous['platforms']) | fact['platforms'])
            titles = sorted(set(previous['product_titles']) | fact['product_titles'])
        else:
            discovered = fact['discovered_at']
            seasoning = max(discovered, processed) if processed is not None else discovered
            first_observation = fact['first_observation_end']
            bootstrap = existing is None
            qualified = None
            activation = base if bootstrap else None
            platforms = sorted(fact['platforms'])
            titles = sorted(fact['product_titles'])
        if not bootstrap and qualified is None:
            candidate = qualification_time(prices[sku], seasoning)
            if (candidate is not None and processed is not None and
                    next_midnight(candidate) <= processed):
                # Newly backfilled evidence cannot create a past composition.
                seasoning = processed
                candidate = qualification_time(prices[sku], seasoning)
            if candidate is not None:
                qualified = candidate
                activation = next_midnight(candidate)
        status = 'active' if activation is not None and (
            (processed is None and activation <= latest_source) or
            (processed is not None and activation <= processed)
        ) else 'pending'
        catalog.append({
            'sku_id': sku,
            'family': fact['family'],
            'region': fact['region'],
            'platforms': platforms,
            'product_titles': titles,
            'discovered_at': previous['discovered_at'] if previous else
                             fact['discovered_at'].isoformat().replace('+00:00', 'Z'),
            'seasoning_start': seasoning.isoformat().replace('+00:00', 'Z'),
            'first_observation_end': previous['first_observation_end'] if previous else
                                     hour_text(first_observation),
            'bootstrap': bootstrap,
            'status': status,
            'qualified_at': None if qualified is None else hour_text(qualified),
            'activation_time': None if activation is None else hour_text(activation),
        })
    catalog_by_id = {entry['sku_id']: entry for entry in catalog}
    for entry in catalog:
        if not entry['bootstrap'] and entry['qualified_at'] is not None:
            require(has_qualification_run(
                prices[entry['sku_id']],
                stamp(entry['seasoning_start'], 'seasoning_start'),
                stamp(entry['qualified_at'], 'qualified_at')),
                'qualified SKU lacks 24 consecutive completed observations')

    if existing is None:
        active = {entry['sku_id'] for entry in catalog if entry['bootstrap']}
        epochs = [make_epoch(base, 'bootstrap', active, catalog_by_id)]
        levels = [{'timestamp': hour_text(base), 'value': '100'}]
        gaps = []
        last_value = Decimal('100')
        last_level_time = base
        processed = base
    else:
        # Replay proves that current source evidence cannot rewrite published levels.
        replay_catalog = dict(catalog_by_id)
        active, last_value, last_level_time = replay_existing(
            existing, prices, replay_catalog)
        epochs = list(existing_epochs)
        levels = list(existing['levels'])
        gaps = list(existing['gaps'])

    events = {}
    published_times = {stamp(epoch['effective_time']) for epoch in epochs}
    for entry in catalog:
        if entry['activation_time'] is None:
            continue
        effective = stamp(entry['activation_time'], 'activation_time')
        if effective > processed and effective <= latest_source:
            events.setdefault(effective, set()).add(entry['sku_id'])
        elif effective <= processed:
            require(entry['sku_id'] in active or any(
                entry['sku_id'] in epoch_ids(epoch) for epoch in epochs),
                'active catalog SKU absent from published composition')

    cursor = processed
    while cursor < latest_source:
        endpoint = cursor + dt.timedelta(hours=1)
        relative = price_return(
            prices, active, catalog_by_id, last_level_time, endpoint)
        if relative is None:
            gaps.append({'timestamp': hour_text(endpoint),
                         'reason': 'missing_active_observation'})
        else:
            with localcontext() as context:
                context.prec = DECIMAL_PRECISION
                last_value = last_value * relative
            levels.append({'timestamp': hour_text(endpoint),
                           'value': decimal_text(last_value)})
            last_level_time = endpoint
        if endpoint in events:
            require(last_level_time == endpoint,
                    'composition activation lacks a linked index level')
            require(all(endpoint in prices.get(sku, {}) for sku in events[endpoint]),
                    'activating SKU missing price at composition endpoint')
            active |= events[endpoint]
            require(endpoint not in published_times, 'duplicate composition epoch')
            epochs.append(make_epoch(
                endpoint, 'qualified_addition', active, catalog_by_id))
            published_times.add(endpoint)
        cursor = endpoint

    active_final = epoch_ids(epochs[-1])
    for entry in catalog:
        entry['status'] = 'active' if entry['sku_id'] in active_final else 'pending'

    document = {
        'schema_version': SCHEMA_VERSION,
        'index_id': INDEX_ID,
        'name': INDEX_NAME,
        'currency': 'USD',
        'unit': 'index_points',
        'granularity': HOUR,
        'source_method': LAST,
        'base': {'timestamp': hour_text(base), 'value': '100'},
        'latest_timestamp': levels[-1]['timestamp'],
        'processed_through': hour_text(latest_source),
        'methodology_version': METHODOLOGY_VERSION,
        'methodology': methodology(),
        'source': source,
        'catalog': catalog,
        'composition_epochs': epochs,
        'levels': levels,
        'gaps': gaps,
    }
    validate_existing(document)
    return document


def read_existing(path):
    if not path.exists():
        return None
    require(path.is_file() and not path.is_symlink(), 'invalid gpu index output')
    document = decode(read_bytes(path))
    validate_existing(document)
    return document


def write_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.is_symlink(), 'symlink gpu index output rejected')
    if path.exists() and path.read_bytes() == payload:
        return False
    descriptor, temporary = tempfile.mkstemp(
        prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return True


def build_index(data, output=None, check=False):
    data = Path(data)
    output = Path(output) if output is not None else data / 'gpu-index.json'
    rows, source = read_archive(data)
    existing = read_existing(output)
    document = build_document(rows, source, existing)
    payload = encode(document)
    if check:
        require(existing is not None, 'gpu index is missing')
        require(payload == encode(existing), 'gpu index is stale')
        return False
    return write_atomic(output, payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/neocloud_spot'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', action='store_true', help='validate without writing')
    args = parser.parse_args(argv)
    try:
        build_index(args.data, args.output, args.check)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
