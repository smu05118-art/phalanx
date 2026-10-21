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
LIFECYCLE_SCHEMA_VERSION = 2
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
        'latest_complete_timestamp', 'current', 'snapshot_time',
    }
    require(type(index) is dict and required <= set(index), 'archive index fields')
    require(index['schema_version'] == 2 and index['method'] == LAST and
            index['granularity'] == HOUR, 'archive index contract mismatch')
    archive_collected = stamp(index['collected_time'], 'archive collected_time')
    require(type(index['current']) is list and index['current'],
            'archive current membership missing')
    current_ids = []
    current_snapshots = []
    for current in index['current']:
        require(type(current) is dict and type(current.get('sku_id')) is str,
                'invalid archive current membership')
        current_ids.append(text(current['sku_id'], 'current sku_id'))
        current_snapshots.append(stamp(
            current.get('source_snapshot_time'), 'current source_snapshot_time'))
    require(len(current_ids) == len(set(current_ids)),
            'duplicate archive current SKU')
    snapshot_time = stamp(index['snapshot_time'], 'archive snapshot_time')
    require(snapshot_time == min(current_snapshots) and
            max(current_snapshots) <= archive_collected,
            'archive current snapshot mismatch')
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
        '_current_sku_ids': sorted(current_ids),
        '_current_snapshot_time': index['snapshot_time'],
    }


def public_source(source):
    fields = {'archive', 'source_index_sha256', 'latest_complete_timestamp'}
    require(type(source) is dict and fields <= set(source),
            'source metadata fields mismatch')
    result = {key: source[key] for key in fields}
    require(result['archive'] == 'index.json' and
            type(result['source_index_sha256']) is str and
            SHA_RE.fullmatch(result['source_index_sha256']) is not None,
            'invalid source metadata')
    stamp(result['latest_complete_timestamp'], 'source latest timestamp')
    return result


def source_membership(source):
    ids = source.get('_current_sku_ids') if type(source) is dict else None
    snapshot = source.get('_current_snapshot_time') if type(source) is dict else None
    require((ids is None) == (snapshot is None),
            'incomplete current membership evidence')
    if ids is None:
        return None
    require(type(ids) is list and ids == sorted(set(ids)) and ids,
            'invalid current membership evidence')
    for sku in ids:
        text(sku, 'current sku_id')
    return {
        'sku_ids': set(ids),
        'snapshot_time': stamp(snapshot, 'current snapshot_time'),
        'snapshot_text': snapshot,
        'source_index_sha256': public_source(source)['source_index_sha256'],
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
    collected_times = {}
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
        collected_times.setdefault(sku, {})[row['interval_end']] = row['collected_time']
    return facts, prices, collected_times


def ceiling_hour(value):
    hour = value.replace(minute=0, second=0, microsecond=0)
    return hour if value == hour else hour + dt.timedelta(hours=1)


def qualification_times(price_map, collected_map, seasoning_start):
    require(set(price_map) == set(collected_map),
            'price/collection evidence mismatch')
    run = []
    for endpoint in sorted(time for time in price_map if time > seasoning_start):
        if run and endpoint - run[-1] != dt.timedelta(hours=1):
            run = []
        run.append(endpoint)
        if len(run) > 24:
            run.pop(0)
        if len(run) == 24:
            # Qualification is an evidence-availability timestamp, not a
            # retrospective interval endpoint.  Aligning upward preserves the
            # hourly catalogue contract without preceding any completing row's
            # immutable collection timestamp.
            yield ceiling_hour(max(collected_map[time] for time in run))


def qualification_time(price_map, collected_map, seasoning_start):
    return min(qualification_times(
        price_map, collected_map, seasoning_start), default=None)


def has_qualification_run(price_map, collected_map, seasoning_start, qualified_at):
    return any(candidate == qualified_at for candidate in qualification_times(
        price_map, collected_map, seasoning_start))


def next_midnight(value):
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + dt.timedelta(days=1)


def next_completed_hour(value):
    """Return the first completed-hour boundary strictly after evidence time."""
    return value.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)


def make_epoch(effective_time, reason, active_ids, catalog_by_id,
               schema_version=SCHEMA_VERSION, link=None):
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
    epoch = {
        'effective_time': hour_text(effective_time),
        'methodology_version': METHODOLOGY_VERSION,
        'reason': reason,
        'families': families,
    }
    if schema_version == LIFECYCLE_SCHEMA_VERSION:
        epoch['link'] = link
    return epoch


def composition_reason(added, removed):
    require(added or removed, 'composition epoch must change membership')
    if added and removed:
        return 'membership_change'
    return 'qualified_addition' if added else 'confirmed_retirement'


def composition_link(from_time, basket):
    require(basket in ('previous', 'survivors'), 'invalid composition link basket')
    return {'from_timestamp': hour_text(from_time), 'basket': basket}


def upgrade_epochs(epochs, levels, catalog_by_id):
    """Add v2 link metadata without changing any published composition."""
    level_times = {
        stamp(level['timestamp'], 'level timestamp') for level in levels
    }
    result = []
    active = set()
    for number, epoch in enumerate(epochs):
        effective = stamp(epoch['effective_time'], 'epoch effective_time')
        ids = epoch_ids(epoch)
        if number == 0:
            reason, link = 'bootstrap', None
        else:
            previous_levels = [time for time in level_times if time < effective]
            require(previous_levels, 'composition link has no previous level')
            reason = composition_reason(ids - active, active - ids)
            link = composition_link(max(previous_levels), 'previous')
        result.append(make_epoch(
            effective, reason, ids, catalog_by_id,
            LIFECYCLE_SCHEMA_VERSION, link))
        active = ids
    return result


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


def validate_retirement_evidence(value):
    require(type(value) is list and len(value) <= 2,
            'invalid retirement evidence')
    parsed = []
    hashes = set()
    for evidence in value:
        require(type(evidence) is dict and
                set(evidence) == {'snapshot_time', 'source_index_sha256'},
                'retirement evidence fields mismatch')
        snapshot = stamp(evidence['snapshot_time'], 'retirement snapshot_time')
        source_hash = evidence['source_index_sha256']
        require(type(source_hash) is str and SHA_RE.fullmatch(source_hash) is not None and
                source_hash not in hashes, 'invalid retirement evidence hash')
        parsed.append(snapshot)
        hashes.add(source_hash)
    require(parsed == sorted(parsed), 'retirement evidence is not sorted')
    if len(parsed) == 2:
        require(parsed[1] - parsed[0] >= dt.timedelta(hours=1),
                'retirement evidence interval is too short')
    return parsed


def validate_catalog_entry(entry, schema_version=SCHEMA_VERSION):
    entry_fields = {
        'sku_id', 'family', 'region', 'platforms', 'product_titles',
        'discovered_at', 'seasoning_start', 'first_observation_end',
        'bootstrap', 'status', 'qualified_at', 'activation_time',
    }
    if schema_version == LIFECYCLE_SCHEMA_VERSION:
        entry_fields |= {'retirement_evidence', 'deactivation_time'}
    require(type(entry) is dict and set(entry) == entry_fields,
            'catalog fields mismatch')
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
    statuses = ('active', 'pending') if schema_version == SCHEMA_VERSION else (
        'active', 'pending', 'retired')
    require(type(entry['bootstrap']) is bool and entry['status'] in statuses,
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
    evidence = []
    deactivation = None
    if schema_version == LIFECYCLE_SCHEMA_VERSION:
        evidence = validate_retirement_evidence(entry['retirement_evidence'])
        deactivation = (None if entry['deactivation_time'] is None else
                        stamp(entry['deactivation_time'], 'deactivation_time'))
        if evidence:
            require(entry['status'] == 'active' or entry['status'] == 'retired',
                    'pending SKU has retirement evidence')
            require(activation is not None and evidence[0] >= activation,
                    'retirement evidence predates activation')
        if deactivation is not None:
            require(len(evidence) == 2 and entry['status'] == 'retired' and
                    deactivation.minute == deactivation.second ==
                    deactivation.microsecond == 0 and
                    deactivation > evidence[1],
                    'invalid deactivation lifecycle')
        require((entry['status'] == 'retired') == (deactivation is not None),
                'retired status/deactivation mismatch')
    return (discovered, seasoning, first, qualified, activation,
            evidence, deactivation)


def validate_existing(document):
    require(type(document) is dict and set(document) == TOP_FIELDS,
            'gpu index top-level fields mismatch')
    schema_version = document['schema_version']
    require(type(schema_version) is int and
            schema_version in (SCHEMA_VERSION, LIFECYCLE_SCHEMA_VERSION) and
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
    require(type(document['catalog']) is list and document['catalog'], 'empty catalog')
    require([entry.get('sku_id') for entry in document['catalog']] ==
            sorted(entry.get('sku_id') for entry in document['catalog']),
            'catalog is not sorted')
    catalog = {}
    for entry in document['catalog']:
        _, _, _, _, activation, _, _ = validate_catalog_entry(
            entry, schema_version)
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
    retired = set()
    activated = set()
    for number, (epoch, effective) in enumerate(zip(epochs, times)):
        ids = epoch_ids(epoch)
        require(ids and ids <= set(catalog),
                'composition contains an invalid catalog SKU')
        if number == 0:
            added, removed = ids, set()
            reason = 'bootstrap'
            require(not active, 'invalid bootstrap composition')
            link = None
        else:
            added, removed = ids - active, active - ids
            require(added or removed,
                    'each composition epoch must change membership')
            require(not (added & retired), 'retired SKU re-entered composition')
            if schema_version == SCHEMA_VERSION:
                require(added and not removed,
                        'v1 composition epoch must add at least one SKU')
                reason = 'qualified_addition'
                link = None
            else:
                reason = composition_reason(added, removed)
                require(type(epoch) is dict and 'link' in epoch,
                        'composition link missing')
                link = epoch['link']
                require(type(link) is dict and
                        set(link) == {'from_timestamp', 'basket'} and
                        link['basket'] in ('previous', 'survivors'),
                        'invalid composition link')
                from_time = stamp(link['from_timestamp'], 'link from_timestamp')
                prior_levels = [time for time in levels if time < effective]
                require(prior_levels and from_time == max(prior_levels),
                        'composition link is not from previous published level')
                if link['basket'] == 'survivors':
                    require(removed and active & ids,
                            'invalid survivor composition link')
        if schema_version == LIFECYCLE_SCHEMA_VERSION and number == 0:
            require(type(epoch) is dict and epoch.get('link', object()) is None,
                    'bootstrap link must be null')
        require(epoch == make_epoch(
            effective, reason, ids, catalog, schema_version, link),
                'composition epoch weights mismatch')
        require(effective in levels, 'composition epoch lacks a linked index level')
        for sku in added:
            require(catalog[sku]['activation_time'] == hour_text(effective),
                    'catalog/epoch activation mismatch')
            activated.add(sku)
        for sku in removed:
            require(schema_version == LIFECYCLE_SCHEMA_VERSION and
                    catalog[sku]['deactivation_time'] == hour_text(effective),
                    'catalog/epoch deactivation mismatch')
            retired.add(sku)
        active = ids
    for sku, entry in catalog.items():
        activation = stamp(entry['activation_time'], 'activation_time') \
            if entry['activation_time'] is not None else None
        deactivation = (stamp(entry['deactivation_time'], 'deactivation_time')
                        if schema_version == LIFECYCLE_SCHEMA_VERSION and
                        entry['deactivation_time'] is not None else None)
        expected_status = ('active' if sku in active else
                           'retired' if deactivation is not None else 'pending')
        require(entry['status'] == expected_status, 'catalog status mismatch')
        require(activation is None or activation > processed or
                sku in activated,
                'elapsed activation missing composition epoch')
        require((deactivation is None) == (sku not in retired),
                'catalog deactivation/epoch mismatch')
        if (schema_version == LIFECYCLE_SCHEMA_VERSION and
                len(entry['retirement_evidence']) == 2):
            ready = next_completed_hour(stamp(
                entry['retirement_evidence'][1]['snapshot_time'],
                'retirement snapshot_time'))
            if deactivation is not None:
                require(deactivation >= ready,
                        'deactivation predates confirmed retirement')
                boundary = deactivation
            else:
                boundary = processed + dt.timedelta(hours=1)
            cursor = ready
            while cursor < boundary and cursor <= processed:
                require(cursor in gaps,
                        'confirmed retirement skipped a published level')
                cursor += dt.timedelta(hours=1)
    require(type(document['source']) is dict and
            set(document['source']) == {'archive', 'source_index_sha256',
                                        'latest_complete_timestamp'},
            'invalid source metadata')
    source = public_source(document['source'])
    require(source['latest_complete_timestamp'] == hour_text(processed),
            'source/processed timestamp mismatch')
    return base, processed, catalog, levels, gaps, epochs


def replay_existing(document, prices, catalog_by_id):
    base, processed, _, levels, gaps, epochs = validate_existing(document)
    schema_version = document['schema_version']
    events = {stamp(epoch['effective_time']): epoch for epoch in epochs}
    active = epoch_ids(events[base])
    require(all(base in prices.get(sku, {}) for sku in active),
            'source no longer contains bootstrap prices')
    last_value = Decimal('100')
    last_level_time = base
    cursor = base
    while cursor < processed:
        endpoint = cursor + dt.timedelta(hours=1)
        event = events.get(endpoint)
        next_active = epoch_ids(event) if event is not None else active
        link_ids = active
        if (event is not None and schema_version == LIFECYCLE_SCHEMA_VERSION and
                event['link']['basket'] == 'survivors'):
            # The recorded basket is authoritative for an immutable published
            # transition.  A later backfill can make the old basket look
            # complete now, but must not rewrite or invalidate the original
            # survivor link.
            link_ids = active & next_active
            require(link_ids, 'survivor bridge basket is empty')
        relative = price_return(
            prices, link_ids, catalog_by_id, last_level_time, endpoint)
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
        if event is not None:
            require(endpoint in levels,
                    'composition activation lacks a linked index level')
            require(all(endpoint in prices.get(sku, {})
                        for sku in next_active - active),
                    'published activating SKU missing price at composition endpoint')
            active = next_active
        cursor = endpoint
    return active, last_value, last_level_time


def build_document(rows, source, trusted_existing_bytes=None,
                   trusted_existing_sha256=None,
                   trusted_source_index_sha256=None, bootstrap=False):
    """Build from an explicitly trusted prior document.

    Callers continuing an index must supply a separately trusted, canonical
    prior byte blob and its independently anchored SHA-256.  The mutable output
    file is never accepted as replay state.
    """
    require(type(rows) is list and rows, 'empty LAST history')
    existing = None
    if trusted_existing_bytes is not None:
        require(type(trusted_existing_bytes) is bytes,
                'trusted existing must be exact bytes')
        require(type(trusted_existing_sha256) is str and
                SHA_RE.fullmatch(trusted_existing_sha256) is not None,
                'trusted existing SHA-256 is required')
        require(hashlib.sha256(trusted_existing_bytes).hexdigest() ==
                trusted_existing_sha256,
                'trusted existing SHA-256 mismatch')
        existing = decode(trusted_existing_bytes)
        validate_existing(existing)
        require(encode(existing) == trusted_existing_bytes,
                'trusted existing is not canonical JSON')
    facts, prices, collected_times = catalog_facts(rows)
    latest_source = max(row['interval_end'] for row in rows)
    source_public = public_source(source)
    membership = source_membership(source)
    require(source_public['latest_complete_timestamp'] == hour_text(latest_source),
            'source metadata latest timestamp mismatch')
    if membership is not None:
        require(membership['snapshot_time'] >= latest_source,
                'current snapshot predates completed source history')

    existing_catalog = {}
    existing_version = SCHEMA_VERSION
    if existing is not None:
        require(not bootstrap, 'bootstrap cannot continue a prior document')
        _, processed, existing_catalog, _, _, existing_epochs = validate_existing(existing)
        require(type(trusted_source_index_sha256) is str and
                SHA_RE.fullmatch(trusted_source_index_sha256) is not None and
                existing['source']['source_index_sha256'] ==
                trusted_source_index_sha256,
                'trusted prior source index SHA-256 mismatch')
        existing_version = existing['schema_version']
        if existing_version == LIFECYCLE_SCHEMA_VERSION:
            require(membership is not None,
                    'v2 rebuild requires current membership evidence')
        require(latest_source >= processed, 'source history truncated before published index')
        require(set(existing_catalog) <= set(facts), 'published catalog SKU disappeared')
        base = stamp(existing['base']['timestamp'], 'base timestamp')
    else:
        require(bootstrap, 'explicit bootstrap is required without a prior document')
        require(trusted_existing_sha256 is None and
                trusted_source_index_sha256 is None,
                'trusted prior supplied without prior document')
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
            retirement_evidence = [
                dict(item) for item in previous.get('retirement_evidence', [])
            ]
            deactivation_time = previous.get('deactivation_time')
        else:
            discovered = fact['discovered_at']
            seasoning = max(discovered, processed) if processed is not None else discovered
            first_observation = fact['first_observation_end']
            bootstrap = existing is None
            qualified = None
            activation = base if bootstrap else None
            platforms = sorted(fact['platforms'])
            titles = sorted(fact['product_titles'])
            retirement_evidence = []
            deactivation_time = None
        if not bootstrap and qualified is None:
            candidate = qualification_time(
                prices[sku], collected_times[sku], seasoning)
            if (candidate is not None and processed is not None and
                    next_midnight(candidate) <= processed):
                # Newly backfilled evidence cannot create a past composition.
                seasoning = processed
                candidate = qualification_time(
                    prices[sku], collected_times[sku], seasoning)
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
            # Kept internally for one build.  They are removed again if no
            # lifecycle event has promoted the public document to schema v2.
            'retirement_evidence': retirement_evidence,
            'deactivation_time': deactivation_time,
        })
    catalog_by_id = {entry['sku_id']: entry for entry in catalog}
    for entry in catalog:
        if not entry['bootstrap'] and entry['qualified_at'] is not None:
            require(has_qualification_run(
                prices[entry['sku_id']],
                collected_times[entry['sku_id']],
                stamp(entry['seasoning_start'], 'seasoning_start'),
                stamp(entry['qualified_at'], 'qualified_at')),
                'qualified SKU lacks 24 consecutive collected observations')

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
        levels = list(existing['levels'])
        gaps = list(existing['gaps'])

    schema_version = existing_version
    if existing is not None and membership is not None:
        current_ids = membership['sku_ids']
        snapshot_time = membership['snapshot_time']
        source_hash = membership['source_index_sha256']
        retired_ids = {
            sku for sku, entry in catalog_by_id.items()
            if entry['deactivation_time'] is not None
        }
        require(not (retired_ids & current_ids),
                'retired SKU reappeared in complete current snapshot')
        for sku in retired_ids:
            evidence = catalog_by_id[sku]['retirement_evidence']
            require(evidence and snapshot_time >= stamp(
                evidence[-1]['snapshot_time'], 'retirement snapshot_time'),
                    'retirement evidence snapshot regressed')
        for sku in sorted(active):
            entry = catalog_by_id[sku]
            evidence = entry['retirement_evidence']
            if evidence:
                last_evidence = evidence[-1]
                last_snapshot = stamp(
                    last_evidence['snapshot_time'], 'retirement snapshot_time')
                require(snapshot_time >= last_snapshot,
                        'retirement evidence snapshot regressed')
            if sku in current_ids:
                require(len(evidence) < 2,
                        'confirmed retirement SKU reappeared')
                if evidence:
                    entry['retirement_evidence'] = []
                continue
            observation = {
                'snapshot_time': membership['snapshot_text'],
                'source_index_sha256': source_hash,
            }
            if not evidence:
                entry['retirement_evidence'] = [observation]
                schema_version = LIFECYCLE_SCHEMA_VERSION
                continue
            evidence_hashes = {
                item['source_index_sha256'] for item in evidence
            }
            if source_hash in evidence_hashes:
                require(source_hash == evidence[-1]['source_index_sha256'] and
                        membership['snapshot_text'] == evidence[-1]['snapshot_time'] and
                        source_hash == existing['source']['source_index_sha256'],
                        'retirement evidence payload regressed')
                continue
            if len(evidence) == 1 and (
                    snapshot_time - stamp(
                        evidence[0]['snapshot_time'], 'retirement snapshot_time') >=
                    dt.timedelta(hours=1)):
                entry['retirement_evidence'] = evidence + [observation]

    if schema_version == LIFECYCLE_SCHEMA_VERSION:
        if existing is not None and existing_version == SCHEMA_VERSION:
            epochs = upgrade_epochs(existing_epochs, levels, catalog_by_id)
        elif existing is not None:
            epochs = list(existing_epochs)
    else:
        epochs = ([make_epoch(base, 'bootstrap', active, catalog_by_id)]
                  if existing is None else list(existing_epochs))

    if existing is None:
        # Initial publication cannot retire constituents: there is no earlier
        # published active set against which two absences could be observed.
        epochs = [make_epoch(base, 'bootstrap', active, catalog_by_id)]

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
        additions = events.get(endpoint, set())
        removals = {
            sku for sku in active
            if (len(catalog_by_id[sku]['retirement_evidence']) == 2 and
                catalog_by_id[sku]['deactivation_time'] is None and
                next_completed_hour(stamp(
                    catalog_by_id[sku]['retirement_evidence'][1]['snapshot_time'],
                    'retirement snapshot_time')) <= endpoint)
        }
        next_active = (active - removals) | additions
        relative = price_return(
            prices, active, catalog_by_id, last_level_time, endpoint)
        link_basket = 'previous'
        if relative is None and removals:
            survivors = active & next_active
            require(survivors, 'survivor bridge basket is empty')
            relative = price_return(
                prices, survivors, catalog_by_id, last_level_time, endpoint)
            link_basket = 'survivors'
        if relative is None:
            gaps.append({'timestamp': hour_text(endpoint),
                         'reason': 'missing_active_observation'})
            require(not additions,
                    'composition activation lacks a linked index level')
        else:
            require(next_active, 'composition retirement would empty the basket')
            require(all(endpoint in prices.get(sku, {}) for sku in additions),
                    'activating SKU missing price at composition endpoint')
            link_from = last_level_time
            with localcontext() as context:
                context.prec = DECIMAL_PRECISION
                last_value = last_value * relative
            levels.append({'timestamp': hour_text(endpoint),
                           'value': decimal_text(last_value)})
            last_level_time = endpoint
        if relative is not None and (additions or removals):
            reason = composition_reason(additions, removals)
            link = (composition_link(link_from, link_basket)
                    if schema_version == LIFECYCLE_SCHEMA_VERSION else None)
            active = next_active
            require(endpoint not in published_times, 'duplicate composition epoch')
            epochs.append(make_epoch(
                endpoint, reason, active, catalog_by_id, schema_version, link))
            published_times.add(endpoint)
            for sku in removals:
                catalog_by_id[sku]['deactivation_time'] = hour_text(endpoint)
        cursor = endpoint

    active_final = active
    for entry in catalog:
        entry['status'] = ('retired' if entry['deactivation_time'] is not None else
                           'active' if entry['sku_id'] in active_final else
                           'pending')
        if schema_version == SCHEMA_VERSION:
            entry.pop('retirement_evidence')
            entry.pop('deactivation_time')

    document = {
        'schema_version': schema_version,
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
        'source': source_public,
        'catalog': catalog,
        'composition_epochs': epochs,
        'levels': levels,
        'gaps': gaps,
    }
    validate_existing(document)
    return document


def read_document(path, label):
    require(path.is_file() and not path.is_symlink(), 'invalid ' + label)
    payload = read_bytes(path)
    document = decode(payload)
    validate_existing(document)
    require(encode(document) == payload, label + ' is not canonical JSON')
    return document, payload


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


def build_index(data, output=None, check=False, trusted_existing=None,
                trusted_source_index=None, bootstrap=False):
    data = Path(data)
    output = Path(output) if output is not None else data / 'gpu-index.json'
    rows, source = read_archive(data)
    output_exists = output.exists()
    require(not output.is_symlink(), 'invalid gpu index output')
    output_payload = read_bytes(output) if output_exists else None

    trusted_document = None
    trusted_payload = None
    trusted_sha256 = None
    trusted_source_sha256 = None
    if trusted_existing is not None:
        require(trusted_source_index is not None,
                'trusted prior source index is required')
        trusted_path = Path(trusted_existing)
        trusted_source_path = Path(trusted_source_index)
        require(not (output_exists and
                    trusted_path.resolve() == output.resolve()),
                'trusted prior must be a separate byte snapshot')
        require(trusted_source_path.resolve() != (data / 'index.json').resolve(),
                'trusted prior source index must be a separate byte snapshot')
        trusted_document, trusted_payload = read_document(
            trusted_path, 'trusted prior gpu index')
        trusted_sha256 = hashlib.sha256(trusted_payload).hexdigest()
        trusted_source_payload = read_bytes(trusted_source_path)
        require(encode(decode(trusted_source_payload)) == trusted_source_payload,
                'trusted prior source index is not canonical JSON')
        trusted_source_sha256 = hashlib.sha256(
            trusted_source_payload).hexdigest()
    else:
        require(trusted_source_index is None,
                'trusted prior source index supplied without gpu index prior')
    if output_exists:
        require(trusted_document is not None,
                'trusted prior gpu index is required')
    else:
        require(trusted_document is None,
                'trusted prior supplied for missing gpu index output')

    document = build_document(
        rows, source, trusted_payload, trusted_sha256,
        trusted_source_sha256, bootstrap)
    payload = encode(document)
    if check:
        require(output_payload is not None, 'gpu index is missing')
        require(payload == output_payload, 'gpu index is stale')
        return False
    if output_payload is not None:
        require(output_payload in (trusted_payload, payload),
                'working gpu index matches neither trusted prior nor expected bytes')
    return write_atomic(output, payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/neocloud_spot'))
    parser.add_argument('--output', type=Path)
    parser.add_argument(
        '--trusted-existing', type=Path,
        help='separate exact-byte snapshot of the committed prior gpu index')
    parser.add_argument(
        '--trusted-source-index', type=Path,
        help='separate exact-byte snapshot of the same commit\'s source index')
    parser.add_argument(
        '--bootstrap', action='store_true',
        help='explicitly create the first gpu index when no prior/output exists')
    parser.add_argument('--check', action='store_true', help='validate without writing')
    args = parser.parse_args(argv)
    try:
        build_index(
            args.data, args.output, args.check, args.trusted_existing,
            args.trusted_source_index, args.bootstrap)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
