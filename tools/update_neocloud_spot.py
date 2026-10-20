#!/usr/bin/env python3
"""Legacy chart-only updater; never use for official observations."""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

PRODUCTS = ('B300', 'B200', 'H200', 'H100', 'RTX PRO 6000')
HEADER = {'schema_version': 1, 'currency': 'USD', 'unit': 'USD/GPU-hour', 'cadence': 'daily_avg'}
LIMIT = 5 * 1024 * 1024
PROVENANCE = {'source_type', 'source_file', 'source_start', 'source_end', 'captured_date', 'atlas_date'}
FIELDS = {'product', 'effective_date', 'price', 'quality', 'uncertainty', 'provenance'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def date(value):
    require(isinstance(value, str), 'date must be an ISO string')
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError('invalid ISO date') from None
    require(parsed.isoformat() == value, 'date must be YYYY-MM-DD')
    return parsed


def short_date(value):
    require(isinstance(value, str) and len(value) == 6 and value.isascii() and value.isdigit(), 'invalid YYMMDD date')
    return date('20' + value[:2] + '-' + value[2:4] + '-' + value[4:])


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def canonical_number(value):
    """Return one stable JSON representation for numerically equal values."""
    require(number(value), 'invalid number')
    return int(value) if type(value) is float and value.is_integer() else value


def validate(raw):
    require(type(raw) is dict and set(raw) == set(HEADER) | {'observations'}, 'invalid top-level schema')
    for key, value in HEADER.items():
        require(type(raw[key]) is type(value) and raw[key] == value, 'invalid ' + key)
    require(type(raw['observations']) is list, 'observations must be an array')
    unique = {}
    for row in raw['observations']:
        require(type(row) is dict and set(row) <= FIELDS and FIELDS - {'price'} <= set(row), 'invalid observation schema')
        require(row['product'] in PRODUCTS, 'invalid product')
        effective = date(row['effective_date'])
        price = row.get('price')
        require(price is None or number(price), 'invalid price')
        if price is not None:
            price = canonical_number(price)
        prov = row['provenance']
        require(type(prov) is dict and set(prov) == PROVENANCE, 'invalid provenance schema')
        require(prov['source_type'] == 'user_supplied_chart_image', 'invalid source_type')
        filename = prov['source_file']
        require(isinstance(filename, str) and 0 < len(filename) <= 255 and '/' not in filename and '\\' not in filename and all(ord(c) >= 32 for c in filename) and filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')), 'invalid source_file')
        start, end = date(prov['source_start']), date(prov['source_end'])
        require(start <= effective <= end, 'effective date outside source period')
        captured = short_date(prov['captured_date'])
        atlas = short_date(prov['atlas_date'])
        require(end <= captured <= atlas, 'invalid capture/Atlas chronology')
        quality, uncertainty = row['quality'], row['uncertainty']
        require(quality in ('exact_printed_label', 'approximate_from_chart', 'missing'), 'invalid quality')
        if price is None:
            require(quality == 'missing' and uncertainty is None, 'null/missing price requires missing quality')
        elif quality == 'exact_printed_label':
            require(uncertainty is None, 'exact observation cannot have uncertainty')
        else:
            require(quality == 'approximate_from_chart' and number(uncertainty) and uncertainty > 0, 'approximate price requires positive absolute uncertainty')
            uncertainty = canonical_number(uncertainty)
        normalized = dict(row, price=price, uncertainty=uncertainty, provenance=dict(prov))
        key = (row['effective_date'], row['product'])
        require(key not in unique or unique[key] == normalized, 'conflicting duplicate product/date: ' + repr(key))
        unique[key] = normalized
    return dict(HEADER, observations=[unique[k] for k in sorted(unique)])


def merge(existing, snapshot):
    a, b = validate(existing), validate(snapshot)
    return validate(dict(HEADER, observations=a['observations'] + b['observations']))


def reject_pairs(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, 'duplicate JSON key: ' + k)
        result[k] = v
    return result


def read(path):
    with Path(path).open('rb') as stream:
        payload = stream.read(LIMIT + 1)
    require(len(payload) <= LIMIT, 'input exceeds 5 MiB')
    return validate(json.loads(payload, object_pairs_hook=reject_pairs))


def encode(data):
    result = (json.dumps(validate(data), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    require(len(result) <= LIMIT, 'output exceeds 5 MiB')
    return result


def write_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', delete=False) as stream:
            temp = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, (path.stat().st_mode & 0o777) if path.exists() else 0o644)
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None:
            os.unlink(temp)


@contextmanager
def data_lock(path):
    """Serialize the complete read/merge/replace transaction for one data path."""
    resolved = str(Path(path).resolve()).encode('utf-8')
    lock_root = Path(tempfile.gettempdir()) / ('phalanx-neocloud-spot-locks-' + str(os.getuid()))
    lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(lock_root.is_dir() and not lock_root.is_symlink(), 'unsafe lock directory')
    lock_path = lock_root / (hashlib.sha256(resolved).hexdigest() + '.lock')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        with os.fdopen(fd, 'r+b') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def transaction(args):
    if args.data.exists():
        existing = read(args.data)
    else:
        require(args.snapshot is not None, 'data file does not exist')
        existing = dict(HEADER, observations=[])
    result = merge(existing, read(args.snapshot)) if args.snapshot else existing
    payload = encode(result)
    if not args.check:
        if not args.data.exists() or args.data.read_bytes() != payload:
            write_atomic(args.data, payload)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--check', action='store_true', help='validate merged result without any writes')
    args = parser.parse_args(argv)
    try:
        if not args.check:
            require(args.snapshot is not None, 'use --snapshot to update or --check to validate')
            with data_lock(args.data):
                result = transaction(args)
        else:
            result = transaction(args)
        print(('CHECK OK' if args.check else 'MERGE OK') + ': ' + str(len(result['observations'])) + ' observations')
        return 0
    except (ValueError, TypeError, OSError, OverflowError) as exc:
        print('ERROR: ' + str(exc), file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
