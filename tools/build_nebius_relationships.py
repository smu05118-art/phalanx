#!/usr/bin/env python3
"""Build reviewed relationship artifacts offline; publish index.json last."""
import argparse
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import tempfile

import nebius_relationships_contract as contract

DEFAULT_DATA = Path(__file__).resolve().parents[1] / 'data/nebius_relationships'


def write_atomic(path, payload):
    path = contract.safe_path(path)
    if path.exists() and contract.read_bytes(path) == payload:
        return False
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.' + path.name + '.', dir=path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        # Persist each directory entry before publishing the manifest.
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def build(input_path, output_dir, check=False):
    input_path = contract.safe_path(input_path)
    document, payload = contract.load_reviewed(input_path)
    manifest, shard = contract.artifacts(document, payload)
    root = contract.safe_path(output_dir)
    shard_path = contract.safe_path(root / manifest['shards'][0]['path'])
    index_path = contract.safe_path(root / 'index.json')
    public_source_path = contract.safe_path(root / manifest['source']['path'])
    contract.require(not contract.same_file(input_path, shard_path) and
                     not contract.same_file(input_path, index_path), 'input/output collision')
    if check:
        contract.validate_bundle(input_path, root)
        return False
    # Validate every existing destination before changing anything. Never repair
    # a corrupt content-addressed object in place.
    if public_source_path.exists():
        contract.require(contract.read_bytes(public_source_path) == payload,
                         'published reviewed source differs from input')
    else:
        contract.require(not index_path.exists(),
                         'published manifest exists without reviewed source')
    if shard_path.exists():
        contract.require(contract.read_bytes(shard_path) == shard, 'existing shard is corrupt')
    root.mkdir(parents=True, exist_ok=True)
    shard_path.parent.mkdir(exist_ok=True)
    changed = write_atomic(public_source_path, payload)
    changed = write_atomic(shard_path, shard) or changed
    changed = write_atomic(index_path, contract.encode(manifest)) or changed
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_DATA / 'reviewed.json')
    parser.add_argument('--output', type=Path, default=DEFAULT_DATA, help='artifact directory')
    parser.add_argument('--check', action='store_true', help='read-only exact-byte verification')
    args = parser.parse_args(argv)
    try:
        changed = build(args.input, args.output, args.check)
    except (ValueError, OSError) as exc:
        print('nebius relationships: ' + str(exc), file=sys.stderr)
        return 1
    print('updated' if changed else 'verified/unchanged')
    return 0


if __name__ == '__main__':
    sys.exit(main())
