"""Strict offline contract for the reviewed Nebius relationship dataset."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

LIMIT = 5 * 1024 * 1024
DATASET = 'nebius-relationships'
ENUMS = {
    'category': ('HYPERSCALER', 'MODEL_DEVELOPER'),
    'service': ('AI_INFRASTRUCTURE',),
    'workload': ('AI_COMPUTE_UNSPECIFIED',),
    'delivery_mode': ('DEDICATED',),
    'disclosure_class': ('NEBIUS_ANNOUNCED',),
    'evidence_class': ('PRIMARY_FIRST_PARTY_PROVIDER',),
    'relationship_status': ('ANNOUNCED_CONTRACT', 'ANNOUNCED_EXPANSION'),
    'service_live_status': ('UNKNOWN',),
    'event_role': ('RELATIONSHIP_ANNOUNCEMENT', 'RELATIONSHIP_EXPANSION_ANNOUNCEMENT'),
    'change_kind': ('INITIAL_PUBLICATION',),
}
SOURCE_FIELDS = set('url publisher type title published updated collected response_sha256 response_bytes locator effective expires source_license provider_terms_apply redistribution_scope'.split())
RECORD_FIELDS = set(ENUMS) | {'id', 'name', 'summary_ko', 'event_date', 'display_date', 'source'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_text(value):
    require(type(value) is str and 0 < len(value) <= 4096, 'invalid text')
    require(all(unicodedata.category(c) not in ('Cc', 'Cf', 'Cs', 'Zl', 'Zp')
                for c in value), 'unsafe control/bidi text')


def safe_tree(value):
    if type(value) is dict:
        for key, child in value.items():
            safe_text(key)
            require(key not in ('__proto__', 'prototype', 'constructor'), 'dangerous object key')
            safe_tree(child)
    elif type(value) is list:
        for child in value:
            safe_tree(child)
    elif type(value) is str:
        safe_text(value)
    else:
        require(type(value) in (int, bool), 'unsupported JSON value (including float/null)')


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def reject_number(value):
    raise ValueError('float/nonfinite number rejected: ' + value)


def decode(payload):
    require(len(payload) <= LIMIT, 'file exceeds 5 MiB')
    try:
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs,
                           parse_float=reject_number, parse_constant=reject_number)
        safe_tree(value)
        return value
    except (UnicodeError, RecursionError) as exc:
        raise ValueError('invalid UTF-8 or excessive nesting') from exc


def encode(value):
    safe_tree(value)
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                          allow_nan=False) + '\n').encode('utf-8')
    require(len(payload) <= LIMIT, 'file exceeds 5 MiB')
    return payload


def safe_path(path):
    raw = os.fspath(path)
    require('..' not in Path(raw).parts, 'parent traversal rejected')
    path = Path(os.path.normpath(os.path.abspath(raw)))
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink rejected')
    return path


def same_file(left, right):
    left, right = safe_path(left), safe_path(right)
    if left == right:
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def read_bytes(path):
    path = safe_path(path)
    with path.open('rb') as stream:
        payload = stream.read(LIMIT + 1)
    require(len(payload) <= LIMIT, 'file exceeds 5 MiB')
    return payload


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected), 'unknown or missing keys')


def integer(value, minimum=1, maximum=LIMIT):
    require(type(value) is int and minimum <= value <= maximum, 'invalid count/version')


def sha(value):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value), 'invalid SHA-256')


def date(value):
    require(type(value) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value), 'invalid date')
    return dt.date.fromisoformat(value)


def stamp(value):
    require(type(value) is str and re.fullmatch(
        r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z', value), 'invalid UTC timestamp')
    return dt.datetime.fromisoformat(value[:-1] + '+00:00')


def url(value):
    safe_text(value)
    require(re.fullmatch(r'https://(?:www\.)?nebius\.com(?:/[^\s\\]*)?', value),
            'unsafe URL')
    parsed = urlsplit(value)
    require(parsed.scheme == 'https' and parsed.netloc in ('nebius.com', 'www.nebius.com')
            and parsed.hostname in ('nebius.com', 'www.nebius.com')
            and parsed.username is None and parsed.password is None
            and parsed.port is None, 'URL must use exact HTTPS Nebius host')


def validate_records(document):
    safe_tree(document)
    fields(document, ('schema_version', 'dataset', 'record_count', 'records'))
    integer(document['schema_version'], 1, 1)
    require(document['dataset'] == DATASET, 'wrong dataset')
    integer(document['record_count'], 2, 2)
    rows = document['records']
    require(type(rows) is list and len(rows) == document['record_count'], 'record count mismatch')
    ids = []
    for row in rows:
        fields(row, RECORD_FIELDS)
        require(type(row['id']) is str and re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', row['id']), 'invalid ID')
        ids.append(row['id'])
        for key, choices in ENUMS.items():
            require(type(row[key]) is str and row[key] in choices, 'invalid enum: ' + key)
        for key in ('name', 'summary_ko'):
            safe_text(row[key])
        event = date(row['event_date'])
        require(type(row['display_date']) is str and
                row['display_date'] == row['event_date'][2:].replace('-', ''), 'invalid display date')
        source = row['source']
        fields(source, SOURCE_FIELDS)
        url(source['url'])
        require(source['publisher'] == 'Nebius Group' and source['type'] == 'COMPANY_NEWSROOM_PRIMARY', 'invalid publisher/type')
        safe_text(source['title'])
        published, updated, collected = [stamp(source[key]) for key in ('published', 'updated', 'collected')]
        require(published <= updated <= collected and event == published.date(), 'inconsistent date roles')
        sha(source['response_sha256'])
        integer(source['response_bytes'])
        for key in ('locator', 'effective', 'expires', 'source_license'):
            require(source[key] == 'UNKNOWN', 'unsupported source field: ' + key)
        require(source['provider_terms_apply'] is True and
                source['redistribution_scope'] == 'FACTUAL_PARAPHRASE_AND_LINK_ONLY', 'invalid rights metadata')
    require(len(set(ids)) == len(ids), 'duplicate IDs')
    require(ids == sorted(ids), 'records must be sorted by ID')
    require(ids == ['meta', 'microsoft'], 'initial release requires exactly the approved IDs')
    return document


def load_reviewed(path):
    payload = read_bytes(path)
    document = validate_records(decode(payload))
    require(payload == encode(document), 'reviewed input is not canonical JSON')
    return document, payload


def artifacts(document, source_payload):
    validate_records(document)
    require(source_payload == encode(document), 'source bytes mismatch')
    shard = encode(document)
    sha256 = digest(shard)
    manifest = {
        'schema_version': 1, 'dataset': DATASET, 'record_count': len(document['records']),
        'source': {'path': 'reviewed.json', 'sha256': digest(source_payload),
                   'bytes': len(source_payload), 'record_count': len(document['records'])},
        'shards': [{'path': 'shards/' + sha256 + '.json', 'sha256': sha256,
                    'bytes': len(shard), 'record_count': len(document['records'])}],
    }
    return manifest, shard


def validate_manifest(manifest):
    safe_tree(manifest)
    fields(manifest, ('schema_version', 'dataset', 'record_count', 'source', 'shards'))
    integer(manifest['schema_version'], 1, 1)
    integer(manifest['record_count'], 2, 2)
    require(manifest['dataset'] == DATASET, 'wrong dataset')
    require(type(manifest['shards']) is list and len(manifest['shards']) == 1, 'invalid shard count')
    for item in [manifest['source'], *manifest['shards']]:
        fields(item, ('path', 'sha256', 'bytes', 'record_count'))
        sha(item['sha256'])
        integer(item['bytes'])
        integer(item['record_count'], 2, 2)
    require(manifest['source']['path'] == 'reviewed.json', 'invalid source path')
    item = manifest['shards'][0]
    require(item['path'] == 'shards/' + item['sha256'] + '.json', 'invalid shard path')


def validate_bundle(input_path, output_dir):
    document, payload = load_reviewed(input_path)
    expected, shard = artifacts(document, payload)
    root = safe_path(output_dir)
    index_bytes = read_bytes(root / 'index.json')
    manifest = decode(index_bytes)
    validate_manifest(manifest)
    require(index_bytes == encode(expected), 'index/source hash/count or canonical bytes mismatch')
    published_source = read_bytes(root / manifest['source']['path'])
    published_document = validate_records(decode(published_source))
    require(published_source == payload and published_source == encode(published_document),
            'declared reviewed source is missing, noncanonical, or mismatched')
    require(digest(published_source) == manifest['source']['sha256'] and
            len(published_source) == manifest['source']['bytes'],
            'declared reviewed source hash/bytes mismatch')
    actual = read_bytes(root / manifest['shards'][0]['path'])
    validate_records(decode(actual))
    require(actual == shard, 'shard hash/bytes/content mismatch')
    return manifest
