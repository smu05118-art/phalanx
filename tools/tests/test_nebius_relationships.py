"""Offline contract, integrity and publication failure regression tests."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import build_nebius_relationships as builder
import nebius_relationships_contract as c

SEED = ROOT / 'data/nebius_relationships/reviewed.json'
SCHEMA = ROOT / 'tools/nebius_relationships.schema.json'


class RelationshipsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'reviewed.json'
        self.source.write_bytes(SEED.read_bytes())
        self.output = self.root / 'generated'
        self.document = c.decode(SEED.read_bytes())

    def build(self, check=False):
        return builder.build(self.source, self.output, check)

    def snapshot(self):
        return {str(p.relative_to(self.output)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.output.rglob('*') if p.is_file()}

    def test_valid_build_check_and_deterministic_noop(self):
        self.assertTrue(self.build())
        before = self.snapshot()
        self.assertFalse(self.build())
        self.assertFalse(self.build(check=True))
        self.assertEqual(before, self.snapshot())
        self.assertEqual((self.output / 'reviewed.json').read_bytes(), self.source.read_bytes())
        manifest = c.validate_bundle(self.source, self.output)
        self.assertEqual(manifest['source']['sha256'], c.digest(self.source.read_bytes()))
        entry = manifest['shards'][0]
        payload = (self.output / entry['path']).read_bytes()
        self.assertEqual(entry['sha256'], c.digest(payload))
        self.assertEqual(entry['bytes'], len(payload))
        self.assertEqual(entry['record_count'], 2)
        self.assertEqual(payload, c.encode(c.decode(payload)))

    def test_cli_and_read_only_missing_check(self):
        self.assertEqual(builder.main(['--input', str(self.source), '--output', str(self.output), '--check']), 1)
        self.assertFalse(self.output.exists())
        self.build()
        before = self.snapshot()
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/validate_nebius_relationships.py'),
                                 '--input', str(self.source), '--output', str(self.output)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_approved_seed_bytes(self):
        # Frozen approved seed: any metadata/summary change requires review.
        self.assertEqual(c.digest(SEED.read_bytes()),
                         'd9941548ab7c434e323daa90f973321ee1733e42642f813489289b3ccbbb0855')

    def test_documentation_schema_matches_runtime_contract(self):
        schema = c.decode(SCHEMA.read_bytes())
        defs = schema['$defs']
        record = defs['record']
        self.assertEqual(set(record['properties']), c.RECORD_FIELDS)
        self.assertEqual(set(record['required']), c.RECORD_FIELDS)
        for key, choices in c.ENUMS.items():
            self.assertEqual(tuple(record['properties'][key]['enum']), choices)
        source = record['properties']['source']
        self.assertEqual(set(source['properties']), c.SOURCE_FIELDS)
        self.assertEqual(set(source['required']), c.SOURCE_FIELDS)
        self.assertEqual(defs['records']['properties']['record_count']['const'], 2)
        self.assertEqual(defs['records']['properties']['records']['minItems'], 2)
        self.assertEqual(defs['records']['properties']['records']['maxItems'], 2)
        self.assertEqual(defs['manifest']['properties']['record_count']['const'], 2)
        self.assertEqual(defs['manifest']['properties']['shards']['minItems'], 1)
        self.assertEqual(defs['manifest']['properties']['shards']['maxItems'], 1)

    def test_fsync_failure_before_replace_preserves_file(self):
        path = self.root / 'atomic.json'
        path.write_bytes(b'old')
        with patch.object(builder.os, 'fsync', side_effect=OSError('flush failure')):
            with self.assertRaises(OSError): builder.write_atomic(path, b'new')
        self.assertEqual(path.read_bytes(), b'old')
        self.assertEqual(list(self.root.glob('.atomic.json.*')), [])

    def test_duplicate_and_out_of_order_ids(self):
        for rows in ([self.document['records'][0]] * 2, self.document['records'][::-1]):
            with self.subTest(rows=rows):
                doc = dict(self.document, records=rows)
                with self.assertRaises(ValueError): c.validate_records(doc)

    def test_duplicate_keys_and_dangerous_keys(self):
        for payload in (b'{"a":1,"a":2}', b'{"source":{"x":1,"x":2}}',
                        b'{"__proto__":1}', b'{"constructor":1}', b'{"prototype":1}'):
            with self.subTest(payload=payload), self.assertRaises(ValueError): c.decode(payload)

    def test_floats_nonfinite_and_invalid_utf8(self):
        for payload in (b'1.0', b'1e2', b'NaN', b'Infinity', b'-Infinity', b'"\xff"', b'null'):
            with self.subTest(payload=payload), self.assertRaises(ValueError): c.decode(payload)
        doc = copy.deepcopy(self.document)
        doc['record_count'] = 2.0
        with self.assertRaises(ValueError): c.validate_records(doc)

    def test_invalid_fields_dates_hashes_counts_and_enums(self):
        mutations = [
            ('event_date', '2025-02-29'), ('event_date', '2026-3-16'),
            ('event_date', '2026-03-17'), ('display_date', '260317'),
            ('display_date', '260231'), ('display_date', 260316),
            ('service_live_status', 'ACTIVE'), ('name', ''), ('extra', 'UNKNOWN'),
            ('source.published', '2026-02-30T00:00:00Z'),
            ('source.updated', '2026-10-05T25:00:00Z'),
            ('source.collected', '2026-01-01T00:00:00Z'),
            ('source.updated', '2026-10-05T11:21:16+00:00'),
            ('source.response_sha256', 'A' * 64), ('source.response_sha256', 'a' * 63),
            ('source.response_bytes', 0), ('source.response_bytes', True),
            ('source.provider_terms_apply', 1), ('source.extra', 'UNKNOWN'),
        ]
        for field, value in mutations:
            doc = copy.deepcopy(self.document)
            target = doc['records'][0]
            if field.startswith('source.'):
                target = target['source']
            target[field.split('.')[-1]] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): c.validate_records(doc)
        for field, value in [('record_count', 1), ('schema_version', True), ('extra', 1), ('records', {})]:
            doc = dict(self.document, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError): c.validate_records(doc)

    def test_url_allowlist(self):
        for value in ('http://nebius.com/x', 'https://nebius.com.evil.test/x',
                      'https://evilnebius.com/x', 'https://nebius.com@evil.test/x',
                      'https://evil.test@nebius.com/x', 'https://nebius.com:443/x',
                      'https://NEBIUS.COM/x', 'https://nebius.com./x',
                      '//nebius.com/x', 'https://nebius.com?x', 'https://nebius.com#x',
                      'https://nebius.com\\@evil.test/x',
                      'https://nebius.com/ x', 'https://nebius.com\n/x'):
            with self.subTest(url=value), self.assertRaises(ValueError): c.url(value)
        for value in ('https://nebius.com/newsroom/a', 'https://www.nebius.com/newsroom/a',
                      'https://nebius.com/newsroom/a?x=1#part'):
            c.url(value)

    def test_unsafe_text(self):
        for char in ('\x00', '\x1f', '\x7f', '\x85', '\u202e', '\u2066', '\u200f', '\ud800', '\u2028'):
            doc = copy.deepcopy(self.document)
            doc['records'][0]['summary_ko'] += char
            with self.subTest(char=repr(char)), self.assertRaises(ValueError): c.validate_records(doc)

    def test_canonical_input_and_check_drift(self):
        self.build()
        before = self.snapshot()
        self.source.write_bytes(self.source.read_bytes() + b'\n')
        with self.assertRaises(ValueError): self.build()
        self.assertEqual(before, self.snapshot())

    def test_tampered_manifest_and_source_bindings(self):
        self.build()
        path = self.output / 'index.json'
        original = path.read_bytes()
        mutations = [('sha256', 'a' * 64), ('bytes', 1), ('record_count', 1), ('path', '../reviewed.json')]
        for section in ('source', 'shards'):
            for field, value in mutations:
                doc = c.decode(original)
                target = doc['source'] if section == 'source' else doc['shards'][0]
                target[field] = value
                path.write_bytes(c.encode(doc))
                before = self.snapshot()
                with self.subTest(section=section, field=field), self.assertRaises(ValueError): self.build(check=True)
                self.assertEqual(before, self.snapshot())
        path.write_bytes(original + b' ')
        with self.assertRaises(ValueError): self.build(check=True)
        path.write_bytes(original)
        doc = copy.deepcopy(self.document)
        doc['records'][0]['summary_ko'] += ' 검토'
        self.source.write_bytes(c.encode(doc))
        with self.assertRaises(ValueError): self.build(check=True)

    def test_tampered_shard(self):
        self.build()
        path = next((self.output / 'shards').glob('*.json'))
        path.write_bytes(path.read_bytes() + b' ')
        before = self.snapshot()
        with self.assertRaises(ValueError): self.build(check=True)
        with self.assertRaises(ValueError): self.build()
        self.assertEqual(before, self.snapshot())

    def test_missing_or_tampered_declared_reviewed_source_fails_check(self):
        self.build()
        public_source = self.output / 'reviewed.json'
        original = public_source.read_bytes()
        public_source.unlink()
        with self.assertRaises((ValueError, OSError)):
            self.build(check=True)
        public_source.write_bytes(b'{}\n')
        with self.assertRaises(ValueError):
            self.build(check=True)
        public_source.write_bytes(original)
        self.assertFalse(self.build(check=True))

    def test_invalid_input_never_writes(self):
        self.build()
        before = self.snapshot()
        self.source.write_bytes(b'{"records":[],"records":[]}')
        with self.assertRaises(ValueError): self.build()
        self.assertEqual(before, self.snapshot())

    def test_atomic_replace_failure_and_cleanup(self):
        path = self.root / 'atomic.json'
        path.write_bytes(b'old\n')
        with patch.object(builder.os, 'replace', side_effect=OSError('injected')):
            with self.assertRaises(OSError): builder.write_atomic(path, b'new\n')
        self.assertEqual(path.read_bytes(), b'old\n')
        self.assertEqual(list(self.root.glob('.atomic.json.*')), [])

    def test_manifest_published_last_and_failure_preserves_old_bundle(self):
        self.build()
        index = self.output / 'index.json'
        stale = c.decode(index.read_bytes())
        stale['source']['sha256'] = 'a' * 64
        old_manifest = c.encode(stale)
        index.write_bytes(old_manifest)
        real_replace = builder.os.replace
        destinations = []
        def fail_manifest(src, dst):
            destinations.append(Path(dst))
            if Path(dst).name == 'index.json': raise OSError('manifest failure')
            return real_replace(src, dst)
        with patch.object(builder.os, 'replace', side_effect=fail_manifest):
            with self.assertRaises(OSError): self.build()
        self.assertEqual([p.parent.name for p in destinations], ['generated'])
        self.assertEqual(index.read_bytes(), old_manifest)
        self.assertFalse(list(self.output.rglob('.*.json.*')))

    def test_first_shard_failure_does_not_publish_manifest(self):
        real_replace = builder.os.replace
        def fail_shard(src, dst):
            if Path(dst).parent.name == 'shards': raise OSError('shard failure')
            return real_replace(src, dst)
        with patch.object(builder.os, 'replace', side_effect=fail_shard):
            with self.assertRaises(OSError): self.build()
        self.assertFalse((self.output / 'index.json').exists())
        self.assertFalse(list((self.output / 'shards').glob('*.json')))
        self.assertEqual((self.output / 'reviewed.json').read_bytes(), self.source.read_bytes())

    def test_existing_manifest_without_reviewed_source_is_not_repaired(self):
        self.build()
        (self.output / 'reviewed.json').unlink()
        before = self.snapshot()
        with self.assertRaises(ValueError): self.build()
        self.assertEqual(before, self.snapshot())

    def test_symlink_and_size_limit(self):
        self.output.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): self.build()
        with self.assertRaises(ValueError): c.decode(b' ' * (c.LIMIT + 1))

    def test_parent_traversal_rejected_before_any_filesystem_mutation(self):
        trusted = self.root / 'trusted'
        escape = self.root / 'escape'
        trusted.mkdir()
        escape.mkdir()
        (trusted / 'link').symlink_to(escape, target_is_directory=True)
        output = trusted / 'new' / '..' / 'link'
        with self.assertRaises(ValueError):
            builder.build(self.source, output)
        self.assertFalse((trusted / 'new').exists())
        self.assertEqual(list(escape.iterdir()), [])

    def test_hardlink_input_output_alias_is_rejected_without_overwrite(self):
        self.output.mkdir()
        index = self.output / 'index.json'
        os.link(self.source, index)
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse((self.output / 'shards').exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'case-alias behavior is filesystem-specific')
    def test_case_alias_input_output_collision_on_case_insensitive_volume(self):
        self.output.mkdir()
        alias = self.output / 'INDEX.JSON'
        alias.write_bytes(self.source.read_bytes())
        if not (self.output / 'index.json').exists():
            self.skipTest('volume is case-sensitive')
        before = alias.read_bytes()
        with self.assertRaises(ValueError):
            builder.build(alias, self.output)
        self.assertEqual(alias.read_bytes(), before)
        self.assertFalse((self.output / 'shards').exists())


if __name__ == '__main__':
    unittest.main()
