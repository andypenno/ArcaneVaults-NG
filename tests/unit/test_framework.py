import copy
import hashlib
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from artifacts import promote
from run import select
from support.data import ROOT
from support.scenarios import scenario


class FrameworkTests(unittest.TestCase):
    def test_baseline_enum_spelling_does_not_change_positions(self):
        from support.engine import rename_enum_references
        before = 'enum class Container {\nNone,\nOld,\n};\nenum class ItemCategory {\nOldItem,\nNone,\n};'
        after = before.replace('OldItem', 'Item').replace('Old', 'New')
        self.assertEqual(rename_enum_references('Container::Old; ItemCategory::OldItem;', before, after), 'Container::New; ItemCategory::Item;')
        self.assertEqual(rename_enum_references('Container::New;', after, after), 'Container::New;')
        self.assertEqual(rename_enum_references('Container::Old;', before, after.replace('New,\n', 'New,\nExtra,\n')), 'Container::New;')
        with self.assertRaises(ValueError):rename_enum_references('', before, after.replace('New,\n', ''))
        with self.assertRaises(ValueError):rename_enum_references('', '', after)
        with self.assertRaises(ValueError):
            rename_enum_references('', after, after.replace('New,\n', 'Extra,\nNew,\n'))
    def test_discovery_rejects_empty_unknown_duplicate(self):
        manifest = {'tests': [{'id': 'one', 'suites': ['unit']}]}
        self.assertEqual(len(select(manifest, ['unit'], [])), 1)
        for suites, names in [(['missing'], []), (['unit'], ['missing'])]:
            with self.assertRaises(ValueError):
                select(manifest, suites, names)
        with self.assertRaises(ValueError):
            select({'tests': []}, ['all'], [])
        with self.assertRaises(ValueError):
            select({'tests': manifest['tests'] * 2}, ['unit'], [])

    def test_migrated_population(self):
        from support.data import load_json
        manifest = load_json((ROOT / 'tests/manifest.json').read_text())
        selected = select(manifest, ['regression'], [])
        self.assertGreaterEqual(len(selected), 16)
        self.assertCountEqual([row['command'][1] for row in selected],
                              {str(p.relative_to(ROOT)) for p in (ROOT / 'tests/regression').glob('check_*.py')})
        self.assertEqual(len(list((ROOT / 'tests/performance').glob('bench_*.py'))), 3)

    def test_construction_hypothesis_is_not_a_release_requirement(self):
        from support.data import load_json
        manifest = load_json((ROOT / 'tests/manifest.json').read_text())
        release = {row['id'] for row in select(manifest, ['release'], [])}
        probe, = select(manifest, ['experiments'], ['construction-bulk-filter-probe'])
        self.assertIn('construction-loans', release)
        self.assertNotIn(probe['id'], release)
        self.assertIn('--bulk-skips-nonplayable', probe['command'])

    def test_runner_failure_timeout_and_success(self):
        import json
        from run import run
        for code, timeout, status in [('raise SystemExit(7)', 2, 'failed'), ('import time;time.sleep(10)', .05, 'timeout'), ('print("ok")', 2, 'passed')]:
            manifest = {'tests': [{'id': 'child', 'suites': ['unit'], 'command': ['{python}', '-c', code], 'timeout_seconds': timeout}]}
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory, patch('run.load_json', return_value=manifest):
                report = run(['unit'], Path(directory) / 'results')
                self.assertEqual(report['results'][0]['status'], status)
                self.assertEqual(report['passed'], status == 'passed')
                self.assertIsNone(json.loads((Path(directory) / 'results/report.json').read_text())['active_child_pid'])

    def test_scenario_validation(self):
        import json
        path = ROOT / 'tests/fixtures/inventories/same-base-worn-and-spare.json'
        original = scenario(path.read_text())
        for change in ('unknown', 'count', 'identity', 'conservation', 'version', 'action'):
            value = copy.deepcopy(original)
            if change == 'unknown':
                value['unknown'] = True
            elif change == 'count':
                value['inventories']['player'][0]['count'] = -1
            elif change == 'identity':
                value['inventories']['player'][1]['id'] = 'worn'
            elif change == 'conservation':
                value['expected']['player']['worn'] = 2
            elif change == 'version':
                value['version'] = 99
            else:
                value['actions'][0]['to'] = 'missing'
            with self.subTest(change=change), self.assertRaises(ValueError):
                scenario(json.dumps(value))

    def test_promotion_preserves_previous_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / 'build/history/commit/ArcaneVaults-NG.zip'
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b'new archive')
            verified = root / 'build/ArcaneVaults-NG.zip'
            verified.write_bytes(b'previous archive')
            report = {'complete': True, 'passed': True, 'zip_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest()}
            for field, value in [('complete', False), ('passed', False), ('zip_sha256', 'stale')]:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    promote(root, candidate, {**report, field: value}, lambda *_: None)
                self.assertEqual(verified.read_bytes(), b'previous archive')
            def invalid(*_):
                raise ValueError('Invalid archive')
            with self.assertRaises(ValueError):
                promote(root, candidate, report, invalid)
            self.assertEqual(verified.read_bytes(), b'previous archive')
            with self.assertRaises(ValueError):
                promote(root, verified, report, lambda *_: None)
            self.assertEqual(promote(root, candidate, report, lambda *_: None), verified)
            self.assertEqual(verified.read_bytes(), candidate.read_bytes())
            self.assertEqual(list(verified.parent.glob('*.zip')), [verified])
