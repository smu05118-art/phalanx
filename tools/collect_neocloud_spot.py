#!/usr/bin/env python3
"""Public Nebius prices. All parsing/merging completes before any archive write."""
import argparse
from contextlib import contextmanager
import datetime as dt
from decimal import Decimal
import email.utils
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = 'api.nebius.cloud'
CURRENT = 'https://' + HOST + '/billing/v1alpha1/spot-price'
SERIES = CURRENT + '/list-series'
PAGE = 'https://nebius.com/spot-prices'
DOCS = 'https://docs.nebius.com/signup-billing/spot-prices'
HOUR = 'GRANULARITY_HOUR_1'
LAST = 'METHOD_LAST_PRICE'
AVG = 'METHOD_AVG_PRICE'
LIMIT = 5 * 1024 * 1024 - 1
RESPONSE_LIMIT = 16 * 1024 * 1024
SHARD_LIMIT = 4 * 1024 * 1024
ARCHIVE_ROW_LIMIT = 5_000_000
ARCHIVE_BYTE_LIMIT = 1024 * 1024 * 1024
FAMILIES = {'gpu-b300-sxm': 'B300', 'gpu-b200-sxm': 'B200', 'gpu-b200-sxm-a': 'B200',
            'gpu-h200-sxm': 'H200', 'gpu-h100-sxm': 'H100', 'gpu-rtx6000': 'RTX PRO 6000',
            'gpu-rtx6000-a': 'RTX PRO 6000'}
PLATFORM_RE = re.compile(r'gpu-[a-z0-9]+(?:-[a-z0-9]+)*')
TITLE_RE = re.compile(r'Preemptible NVIDIA(?:®)?\s+(.+?)(?:\s+NVLink)?')
FAMILY_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9 .+_-]{0,63}')
VERIFIED_FIXTURE_SHA256 = {
    AVG: '1594b1e56042e2762a9cc9656ebbc6ca8f24bd1cf2a7c1ff7df5e58f4e6df909',
    LAST: '614ef24e7449a27c016d3bedd2284c210858e4404e8ed94ad3568433dcf40c67',
}
VERIFIED_CURRENT_SHA256 = 'e5053b8dccf4a2a1843abaad5accfbbb52ef7416c65606b677907ad09deb1098'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(obj, required, optional=()):
    require(type(obj) is dict and set(required) <= set(obj) <= set(required) | set(optional),
            'schema fields mismatch: ' + str(required))


def string(value):
    require(type(value) is str and 0 < len(value) <= 512 and all(ord(c) >= 32 for c in value), 'invalid string')
    return value


def stamp(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z', value), 'invalid UTC timestamp')
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def iso(value):
    return value.isoformat().replace('+00:00', 'Z')


def price(value):
    require(type(value) is str and re.fullmatch(r'(?:0|[1-9]\d{0,10})(?:\.\d{1,30})?', value), 'invalid Decimal price')
    return format(Decimal(value), 'f').rstrip('0').rstrip('.') if '.' in value else value


def pairs(items):
    result = {}
    for k, v in items:
        require(k not in result, 'duplicate JSON key: ' + k)
        result[k] = v
    return result


def decode(payload, limit=RESPONSE_LIMIT):
    require(len(payload) <= limit, 'response overflow')
    return json.loads(payload, object_pairs_hook=pairs, parse_constant=lambda x: require(False, 'invalid JSON constant'))


def encode(obj):
    payload = (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    require(len(payload) <= LIMIT, 'public file exceeds 5 MiB; split design must be reviewed')
    return payload


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def allowed(url):
    p = urllib.parse.urlsplit(url)
    require(p.scheme == 'https' and p.hostname == HOST and p.port in (None, 443)
            and not p.username and not p.password and not p.fragment, 'URL host not allowed')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect rejected')


def retry_delay(header, attempt):
    if header:
        try:
            seconds = float(header)
        except ValueError:
            try:
                seconds = (email.utils.parsedate_to_datetime(header) - dt.datetime.now(dt.timezone.utc)).total_seconds()
            except (ValueError, TypeError):
                seconds = 2 ** attempt
        require(0 <= seconds <= 120, 'Retry-After outside bounded retry budget')
        return seconds
    return 2 ** attempt


def fetch(url, opener=None):
    allowed(url)
    # No auth, cookie jar, environment proxy, or credential lookup.
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect())
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Phalanx-Nebius-Spot/2'})
            with opener.open(req, timeout=20) as response:
                allowed(response.geturl())
                payload = response.read(RESPONSE_LIMIT + 1)
                decode(payload)
                return payload
        except urllib.error.HTTPError as exc:
            if (exc.code != 429 and not 500 <= exc.code <= 599) or attempt == 3:
                if getattr(exc, 'fp', None) is not None:
                    exc.close()
                raise
            try:
                delay = retry_delay(exc.headers.get('Retry-After'), attempt)
            finally:
                if getattr(exc, 'fp', None) is not None:
                    exc.close()
            time.sleep(delay)
    raise ValueError('retry exhaustion')


def pages(endpoint, params, getter=fetch):
    result, seen = [], set()
    for _ in range(100):
        payload = getter(endpoint + '?' + urllib.parse.urlencode(params, doseq=True))
        obj = decode(payload)
        envelope(obj)
        result.append((obj, digest(payload)))
        token = obj.get('nextPageToken', '')
        if not token:
            return result
        require(token not in seen, 'pagination cycle')
        seen.add(token)
        params = dict(params, pageToken=token)
    raise ValueError('pagination page limit')


def envelope(obj):
    fields(obj, ('items', 'snapshotTime'), ('nextPageToken',))
    stamp(obj['snapshotTime'])
    require(type(obj['items']) is list, 'items must be array')
    require(type(obj.get('nextPageToken', '')) is str, 'invalid pagination token')


def validate_pages(all_pages):
    require(all_pages, 'empty page set')
    for obj, _ in all_pages:
        envelope(obj)


def units(currency, unit):
    require(currency == 'usd' and unit == 'GPU hour', 'invalid currency/unit')


def product_family(platform, product_title):
    """Derive a stable family from Nebius' official product identity."""
    string(platform)
    title = string(product_title)
    require(PLATFORM_RE.fullmatch(platform) is not None, 'unsupported GPU platform: ' + platform)
    match = TITLE_RE.fullmatch(title)
    require(match is not None, 'unsupported GPU product title: ' + title)
    label = match.group(1).strip()
    require(FAMILY_RE.fullmatch(label) is not None, 'invalid GPU family label: ' + label)
    known = FAMILIES.get(platform)
    require(known is None or known == label, 'platform/title family mismatch: ' + platform)
    return known or label


def metadata(row):
    fields(row['computeInstance'], ('platform',))
    platform = string(row['computeInstance']['platform'])
    title = string(row['productTitle'])
    return dict(sku_id=string(row['skuId']), product_title=title,
                region=string(row['region']), platform=platform, family=product_family(platform, title),
                currency='USD', unit='USD/GPU-hour')


def parse_current(all_pages, collected):
    stamp(collected)
    validate_pages(all_pages)
    rows = {}
    for obj, sha in all_pages:
        envelope(obj)
        require(stamp(obj['snapshotTime']) <= stamp(collected), 'snapshot after collection')
        for item in obj['items']:
            fields(item, ('skuId', 'productTitle', 'region', 'computeInstance', 'price', 'effectiveTime'))
            fields(item['price'], ('value', 'currency', 'unitTitle'))
            units(item['price']['currency'], item['price']['unitTitle'])
            require(stamp(item['effectiveTime']) <= stamp(collected), 'effective time after collection')
            row = dict(metadata(item), price=price(item['price']['value']), effective_time=item['effectiveTime'],
                       source_snapshot_time=obj['snapshotTime'], collected_time=collected, source_endpoint=CURRENT, source_sha256=sha)
            key = row['sku_id']
            require(key not in rows or rows[key] == row, 'conflicting current SKU: ' + key)
            rows[key] = row
    require(rows, 'empty current response')
    return [rows[k] for k in sorted(rows)]


def parse_history(all_pages, method, collected):
    require(method in (AVG, LAST), 'unsupported method')
    validate_pages(all_pages)
    cutoff = stamp(collected).replace(minute=0, second=0, microsecond=0)
    rows = []
    for obj, sha in all_pages:
        envelope(obj)
        require(stamp(obj['snapshotTime']) <= stamp(collected), 'snapshot after collection')
        complete = min(cutoff, stamp(obj['snapshotTime']).replace(minute=0, second=0, microsecond=0))
        for item in obj['items']:
            fields(item, ('skuId', 'productTitle', 'region', 'computeInstance', 'currency', 'unitTitle', 'points'))
            units(item['currency'], item['unitTitle'])
            meta = metadata(item)
            require(type(item['points']) is list, 'points must be array')
            for point in item['points']:
                fields(point, ('timestamp', 'value'))
                end = stamp(point['timestamp'])
                value = price(point['value'])
                require(end.minute == end.second == end.microsecond == 0, 'unaligned hourly endpoint')
                if end > complete:
                    continue
                rows.append(dict(meta, price=value, interval_start=iso(end - dt.timedelta(hours=1)), interval_end=iso(end),
                                 method=method, granularity=HOUR, source_snapshot_time=obj['snapshotTime'],
                                 collected_time=collected, source_endpoint=SERIES, source_sha256=sha))
    return merge([], rows)


def key(row):
    return (row['sku_id'], row['interval_end'], row['granularity'], row['method'])


def identity(row):
    return {k: v for k, v in row.items() if k not in ('source_snapshot_time', 'collected_time', 'source_sha256')}


def current_identity(row):
    return {k: v for k, v in row.items() if k not in ('collected_time', 'source_sha256')}


def merge(old, new):
    result = {key(r): r for r in old}
    require(len(result) == len(old), 'duplicate stored observation')
    for row in new:
        k = key(row)
        require(k not in result or identity(result[k]) == identity(row), 'immutable observation conflict: ' + repr(k))
        if k not in result:
            result[k] = row
    return [result[k] for k in sorted(result)]


META = {'sku_id', 'product_title', 'region', 'platform', 'family', 'currency', 'unit', 'price',
        'source_snapshot_time', 'collected_time', 'source_endpoint', 'source_sha256'}


def validate_row(row, history):
    fields(row, META | ({'interval_start', 'interval_end', 'method', 'granularity'} if history else {'effective_time'}))
    require(row['family'] == product_family(row['platform'], row['product_title']), 'family mismatch')
    require(row['currency'] == 'USD' and row['unit'] == 'USD/GPU-hour', 'archive unit mismatch')
    for k in ('sku_id', 'product_title', 'region'):
        string(row[k])
    require(price(row['price']) == row['price'], 'noncanonical price')
    require(re.fullmatch('[0-9a-f]{64}', row['source_sha256']), 'invalid source hash')
    snap, collected = stamp(row['source_snapshot_time']), stamp(row['collected_time'])
    require(snap <= collected, 'invalid chronology')
    require(row['source_endpoint'] == (SERIES if history else CURRENT), 'invalid source endpoint')
    if history:
        start, end = stamp(row['interval_start']), stamp(row['interval_end'])
        require(end - start == dt.timedelta(hours=1) and end.minute == end.second == end.microsecond == 0, 'invalid interval')
        require(end <= snap and end <= collected, 'incomplete stored interval')
        require(row['method'] in (LAST, AVG) and row['granularity'] == HOUR, 'invalid method/granularity')
    else:
        require(stamp(row['effective_time']) <= collected, 'effective time after collection')


def shard_path(row):
    layer = 'history' if row['method'] == LAST else 'imported-average'
    return layer + '/' + row['interval_start'][:7] + '.json'


def safe_archive_layout(root):
    require(not root.is_symlink(), 'symlink archive root rejected')
    if root.exists():
        require(root.is_dir(), 'archive root is not a directory')
    index = root / 'index.json'
    require(not index.is_symlink(), 'symlink index rejected')
    if index.exists():
        require(index.is_file(), 'index is not a regular file')
    for layer in ('history', 'imported-average'):
        directory = root / layer
        require(not directory.is_symlink(), 'symlink archive layer rejected: ' + layer)
        if directory.exists():
            require(directory.is_dir(), 'archive layer is not a directory: ' + layer)


SHARD_RE = re.compile(r'(?P<layer>history|imported-average)/(?P<month>\d{4}-\d{2})(?P<suffix>-[0-9]{2,})?\.json')
LAYER_METHOD = {'history': LAST, 'imported-average': AVG}


def row_group(row):
    return row['method'], row['interval_start'][:7]


def entry_group(entry):
    match = SHARD_RE.fullmatch(entry['path']) if type(entry.get('path')) is str else None
    require(match is not None, 'invalid shard path')
    require(entry['method'] == LAYER_METHOD[match['layer']], 'shard layer/method mismatch')
    part = 1 if match['suffix'] is None else int(match['suffix'][1:])
    base = match['layer'] + '/' + match['month'] + '.json'
    expected = base if part == 1 else base[:-5] + '-%02d.json' % part
    require(part >= 1 and entry['path'] == expected, 'noncanonical shard part')
    return (entry['method'], match['month']), part, base


def read_index(root):
    safe_archive_layout(root)
    index_path = root / 'index.json'
    if not index_path.exists():
        require(not list(root.glob('history/*.json')) and not list(root.glob('imported-average/*.json')), 'orphan archive without index')
        return None
    index = decode(index_path.read_bytes(), LIMIT)
    fields(index, ('schema_version', 'source_urls', 'supported_families', 'current', 'snapshot_time', 'collected_time',
                   'method', 'granularity', 'shards', 'latest_complete_timestamp', 'imported_average_latest_timestamp'))
    require(type(index['schema_version']) is int and index['schema_version'] == 2, 'schema version')
    require(index['source_urls'] == [PAGE, DOCS, CURRENT, SERIES], 'source contract')
    require(type(index['supported_families']) is list and index['supported_families'] and
            index['supported_families'] == sorted(set(index['supported_families'])) and
            all(type(value) is str and FAMILY_RE.fullmatch(value) is not None
                for value in index['supported_families']), 'family catalogue contract')
    require(index['method'] == LAST and index['granularity'] == HOUR, 'index aggregation')
    require(type(index['current']) is list and index['current'], 'current missing')
    for r in index['current']:
        validate_row(r, False)
    require(len({r['sku_id'] for r in index['current']}) == len(index['current']), 'duplicate current')
    require(index['snapshot_time'] == min((r['source_snapshot_time'] for r in index['current']), key=stamp) and
            index['collected_time'] == max((r['collected_time'] for r in index['current']), key=stamp), 'index timestamps')
    require(type(index['shards']) is list, 'shards must be array')
    seen, groups = set(), {}
    aggregate_rows = 0
    aggregate_bytes = 0
    for entry in index['shards']:
        fields(entry, ('path', 'sha256', 'count', 'method', 'start', 'end'))
        p = entry['path']
        require(type(p) is str and p not in seen, 'invalid shard path')
        group, part, _ = entry_group(entry)
        require(type(entry['count']) is int and entry['count'] > 0, 'shard count')
        require(type(entry['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', entry['sha256']), 'invalid shard hash')
        require(stamp(entry['start']) < stamp(entry['end']), 'invalid shard range')
        seen.add(p)
        target = root / p
        require(not target.is_symlink() and target.is_file(), 'missing or unsafe shard: ' + p)
        shard_size = target.stat().st_size
        require(shard_size <= LIMIT, 'stored shard exceeds size limit: ' + p)
        aggregate_rows += entry['count']
        aggregate_bytes += shard_size
        require(aggregate_rows <= ARCHIVE_ROW_LIMIT,
                'aggregate archive row limit exceeded')
        require(aggregate_bytes <= ARCHIVE_BYTE_LIMIT,
                'aggregate archive byte limit exceeded')
        groups.setdefault(group, []).append((part, entry))
    for parts in groups.values():
        parts.sort(key=lambda item: item[0])
        require([part for part, _ in parts] == list(range(1, len(parts) + 1)), 'noncontiguous shard parts')
        for (_, left), (_, right) in zip(parts, parts[1:]):
            require(stamp(left['end']) <= stamp(right['start']), 'overlapping shard parts')
    stored = {str(p.relative_to(root)) for layer in ('history', 'imported-average')
              for p in (root / layer).glob('*.json')}
    require(stored == seen, 'unreferenced or missing shard files')
    for method, field in [(LAST, 'latest_complete_timestamp'), (AVG, 'imported_average_latest_timestamp')]:
        require(index[field] == max((e['end'] for e in index['shards'] if e['method'] == method), default=None),
                'latest timestamp mismatch')
    return index


def read_entries(root, entries):
    rows = []
    for entry in entries:
        p = entry['path']
        group, _, base = entry_group(entry)
        target = root / p
        require(not target.is_symlink() and target.is_file(), 'missing or unsafe shard: ' + p)
        payload = target.read_bytes()
        require(digest(payload) == entry['sha256'], 'shard hash mismatch: ' + p)
        data = decode(payload, LIMIT)
        fields(data, ('schema_version', 'observations'))
        require(type(data['schema_version']) is int and data['schema_version'] == 2 and type(data['observations']) is list and data['observations'], 'shard schema')
        for row in data['observations']:
            validate_row(row, True)
            require(shard_path(row) == base and row_group(row) == group, 'wrong shard group')
        require(type(entry['count']) is int and entry['count'] == len(data['observations']), 'shard count')
        require(entry['start'] == min(r['interval_start'] for r in data['observations']) and entry['end'] == max(r['interval_end'] for r in data['observations']), 'shard range')
        rows.extend(data['observations'])
    return merge(rows, [])


def read_archive(root):
    index = read_index(root)
    if index is None:
        return None, []
    rows = read_entries(root, index['shards'])
    for method, field in [(LAST, 'latest_complete_timestamp'), (AVG, 'imported_average_latest_timestamp')]:
        require(index[field] == max((r['interval_end'] for r in rows if r['method'] == method), default=None), 'latest timestamp mismatch')
    observed_families = sorted(
        {r['family'] for r in index['current']} | {r['family'] for r in rows})
    require(index['supported_families'] == observed_families,
            'family catalogue/archive mismatch')
    return index, rows


def reconcile_current(old_index, current):
    require(current, 'current missing')
    for row in current:
        validate_row(row, False)
    require(len({r['sku_id'] for r in current}) == len(current), 'duplicate current')
    if old_index:
        old_current = {r['sku_id']: r for r in old_index['current']}
        new_current = {r['sku_id']: r for r in current}
        require(min(stamp(r['source_snapshot_time']) for r in current) >= stamp(old_index['snapshot_time']),
                'current snapshot regression')
        for sku_id in old_current.keys() & new_current.keys():
            old_row, new_row = old_current[sku_id], new_current[sku_id]
            old_time, new_time = stamp(old_row['source_snapshot_time']), stamp(new_row['source_snapshot_time'])
            require(new_time >= old_time, 'current SKU snapshot regression: ' + sku_id)
            if new_time == old_time:
                require(current_identity(new_row) == current_identity(old_row),
                        'current snapshot conflict: ' + sku_id)
                new_current[sku_id] = old_row
        if min(stamp(r['source_snapshot_time']) for r in current) == stamp(old_index['snapshot_time']):
            require(new_current.keys() == old_current.keys(), 'current membership conflict at unchanged snapshot')
        current = [new_current[k] for k in sorted(new_current)]
    return sorted(current, key=lambda row: row['sku_id'])


def encode_group(group, observations):
    require(observations and all(row_group(row) == group for row in observations), 'mixed shard group')
    observations.sort(key=lambda row: (row['interval_start'], row['sku_id']))
    buckets = []
    for row in observations:
        if not buckets or buckets[-1][0]['interval_start'] != row['interval_start']:
            buckets.append([])
        buckets[-1].append(row)
    parts, part, size = [], [], 100
    for bucket in buckets:
        bucket_size = sum(len(encode(row)) + 1 for row in bucket)
        require(bucket_size + 100 <= SHARD_LIMIT, 'observation time bucket too large')
        if part and size + bucket_size > SHARD_LIMIT:
            parts.append(part)
            part, size = [], 100
        part.extend(bucket)
        size += bucket_size
    if part:
        parts.append(part)
    base_path = ('history/' if group[0] == LAST else 'imported-average/') + group[1] + '.json'
    files, entries = {}, []
    for number, rows in enumerate(parts, 1):
        path = base_path if number == 1 else base_path[:-5] + '-%02d.json' % number
        payload = encode(dict(schema_version=2, observations=rows))
        files[path] = payload
        entries.append(dict(path=path, sha256=digest(payload), count=len(rows), method=group[0],
                            start=min(r['interval_start'] for r in rows), end=max(r['interval_end'] for r in rows)))
    return files, entries


_UNSET = object()


def build(root, current, incoming, old_index=_UNSET, old_rows=_UNSET):
    if old_index is _UNSET:
        old_index, old_rows = read_archive(root)
    else:
        require(old_rows is not _UNSET,
                'old archive rows must accompany old index')
    current = reconcile_current(old_index, current)
    require(incoming, 'no incoming observations')
    for row in incoming:
        validate_row(row, True)
    touched = {row_group(row) for row in incoming}
    old_entries = old_index['shards'] if old_index else []
    replaced_entries = [entry for entry in old_entries if entry_group(entry)[0] in touched]
    carried_entries = [entry for entry in old_entries if entry_group(entry)[0] not in touched]
    replaced_groups = {entry_group(entry)[0] for entry in replaced_entries}
    carried_groups = {entry_group(entry)[0] for entry in carried_entries}
    replaced_rows = [row for row in old_rows if row_group(row) in replaced_groups]
    carried_rows = [row for row in old_rows if row_group(row) in carried_groups]
    require(len(replaced_rows) + len(carried_rows) == len(old_rows),
            'old archive rows do not match manifest groups')
    rows = merge(replaced_rows, incoming)
    require(all(row_group(row) in touched for row in rows), 'unexpected touched shard group')
    files, new_entries = {}, []
    for group in sorted(touched):
        group_files, group_entries = encode_group(group, [row for row in rows if row_group(row) == group])
        files.update(group_files)
        new_entries.extend(group_entries)
    shards = sorted(carried_entries + new_entries,
                    key=lambda entry: (entry_group(entry)[2], entry_group(entry)[1]))
    require(sum(entry['count'] for entry in shards) <= ARCHIVE_ROW_LIMIT,
            'aggregate archive row limit exceeded')
    aggregate_bytes = sum(len(payload) for payload in files.values())
    aggregate_bytes += sum((root / entry['path']).stat().st_size
                           for entry in carried_entries)
    require(aggregate_bytes <= ARCHIVE_BYTE_LIMIT,
            'aggregate archive byte limit exceeded')
    supported = {r['family'] for r in current}
    supported.update(r['family'] for r in rows)
    supported.update(r['family'] for r in carried_rows)
    index = dict(schema_version=2, source_urls=[PAGE, DOCS, CURRENT, SERIES], supported_families=sorted(supported),
                 current=current, snapshot_time=min((r['source_snapshot_time'] for r in current), key=stamp),
                 collected_time=max((r['collected_time'] for r in current), key=stamp), method=LAST, granularity=HOUR, shards=shards,
                 latest_complete_timestamp=max((e['end'] for e in shards if e['method'] == LAST), default=None),
                 imported_average_latest_timestamp=max((e['end'] for e in shards if e['method'] == AVG), default=None))
    files['index.json'] = encode(index)
    return files


def atomic(path, payload):
    require(not path.is_symlink() and not path.parent.is_symlink(), 'symlink output path rejected')
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name, delete=False) as f:
            name = f.name
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def publish(root, files):
    # Every fetch/parse/conflict/size check has already succeeded. Index goes last.
    safe_archive_layout(root)
    index = decode(files['index.json'], LIMIT)
    entries = {entry['path']: entry for entry in index['shards']}
    expected = {root / path for path in entries}
    supplied = set(files) - {'index.json'}
    require(supplied <= set(entries), 'supplied shard absent from new manifest')
    for path in supplied:
        require(digest(files[path]) == entries[path]['sha256'], 'supplied shard hash mismatch')
    for path in set(entries) - supplied:
        target = root / path
        require(not target.is_symlink() and target.is_file(), 'missing or unsafe carried shard: ' + path)
    stale = sorted({p for layer in ('history', 'imported-average') for p in (root / layer).glob('*.json')} - expected)
    require(all(not p.is_symlink() and p.is_file() for p in stale), 'unsafe stale shard path')
    changed = [(root / p, b) for p, b in files.items() if p != 'index.json'
               and (not (root / p).exists() or (root / p).read_bytes() != b)]
    changed.extend((p, None) for p in stale)
    index_path = root / 'index.json'
    if not index_path.exists() or index_path.read_bytes() != files['index.json']:
        changed.append((index_path, files['index.json']))
    backups = {p: p.read_bytes() if p.exists() else None for p, _ in changed}
    applied = []
    try:
        for p, b in changed:
            if b is None:
                p.unlink()
            else:
                atomic(p, b)
            applied.append(p)
    except OSError:
        for p in reversed(applied):
            if backups[p] is None:
                p.unlink()
            else:
                atomic(p, backups[p])
        raise
    return len(changed)


@contextmanager
def lock(root):
    directory = Path(tempfile.gettempdir()) / ('phalanx-nebius-spot-' + str(os.getuid()))
    directory.mkdir(mode=0o700, exist_ok=True)
    info = os.lstat(directory)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
            'unsafe lock directory')
    path = directory / (digest(str(root.resolve()).encode()) + '.lock')
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def fixture(path):
    payload = path.read_bytes()
    obj = decode(payload)
    envelope(obj)
    require(not obj.get('nextPageToken'), 'partial fixture capture')
    return [(obj, digest(payload))]


def collect(args):
    now = args.collected_at or iso(dt.datetime.now(dt.timezone.utc))
    stamp(now)
    old_index, old_rows = read_archive(args.data)
    if args.mode in ('import-avg', 'fixture-last'):
        require(args.current_fixture and args.series_fixture, 'both fixture paths required')
        cp, hp = fixture(args.current_fixture), fixture(args.series_fixture)
        method = AVG if args.mode == 'import-avg' else LAST
        require(len(cp) == 1 and cp[0][1] == VERIFIED_CURRENT_SHA256,
                'current fixture is not the provenance-approved capture')
        require(len(hp) == 1 and hp[0][1] == VERIFIED_FIXTURE_SHA256[method],
                'fixture is not the provenance-approved capture for ' + method)
    else:
        # First scheduled run always backfills LAST, even with an imported AVG layer.
        end = stamp(now).replace(minute=0, second=0, microsecond=0)
        start = end - dt.timedelta(days=29)
        if args.mode == 'refresh' and old_index and old_index['latest_complete_timestamp']:
            start = max(start, stamp(old_index['latest_complete_timestamp']) - dt.timedelta(days=2))
        cp = pages(CURRENT, {'pageSize': 100})
        hp = pages(SERIES, {'pageSize': 100, 'filters.startTime': iso(start), 'filters.endTime': iso(end),
                           'aggregation.granularity': HOUR, 'aggregation.method': LAST})
        method = LAST
        now = iso(dt.datetime.now(dt.timezone.utc))
    current = parse_current(cp, now)
    rows = parse_history(hp, method, now)
    require(rows, 'no completed history observations')
    return build(args.data, current, rows, old_index, old_rows)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, default=Path('data/neocloud_spot'))
    p.add_argument('--mode', choices=['backfill', 'refresh', 'import-avg', 'fixture-last'], default='refresh')
    p.add_argument('--current-fixture', type=Path)
    p.add_argument('--series-fixture', type=Path)
    p.add_argument('--collected-at', help='explicit reproducible ingestion time; must not predate source')
    p.add_argument('--check', action='store_true', help='validate existing archive offline; no fetch or writes')
    args = p.parse_args(argv)
    try:
        with lock(args.data):
            if args.check:
                index, rows = read_archive(args.data)
                require(index is not None, 'missing index')
                print('CHECK OK:', len(rows), 'observations')
            else:
                files = collect(args)
                print('COLLECT OK:', publish(args.data, files), 'changed files')
        return 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
