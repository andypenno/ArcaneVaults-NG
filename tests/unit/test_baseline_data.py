import copy
import json
import unittest
from support.data import ROOT
from support.performance import calibration_scale, compare_times, compare_work
from performance.gate import compare_reference, make_reference


def observations(reference):
    render = {'complete': True, 'responsiveness_regressions': [], 'fixture_sha256': reference['fixture_sha256'], 'summary': [], 'samples': []}
    render_samples = {}
    for row in reference['render']:
        model, size, entry, shape, archived = row['case']
        render['summary'].append({'model': model, 'size': size, 'entry': entry, 'shape': shape,
            'archives_populated': archived, 'max_render_gap_simulated_ms': {'max': row['gap_ms']}})
        render_samples.setdefault((model, size), []).append({'entry': entry, 'shape': shape,
            'archives_populated': archived, 'charged_native_calls': row['calls'],
            'archive_input_bases': (5 + (size if shape == 3 else 0)) if archived else 0})
    for (model, size), cases in render_samples.items():
        for sample in range(2):
            render['samples'].append({'model': model, 'size': size, 'sample': sample, 'cases': copy.deepcopy(cases)})
    from performance.gate import CASE_FIELDS, WORK_FIELDS
    loans = {name: {'samples': [], 'harness_sha256': reference['loan_harness']} for name in ('loans', 'loans-all')}
    for row in reference['loans']:
        name = 'loans-all' if row['case'][-1] else 'loans'
        for elapsed in row['elapsed_ms']:
            loans[name]['samples'].append({**dict(zip(CASE_FIELDS, row['case'], strict=True)),
                **dict(zip(WORK_FIELDS, row['work'], strict=True)), 'ms': elapsed, 'variant': 'working', 'validated': True})
    quick = {'complete': True, 'harness_sha256': reference['quicksort_harness'], 'batches': []}
    for batch in (0, 1):
        samples = []
        for row in reference['quicksort']:
            middle = len(row['elapsed_ms']) // 2
            samples.extend({'items': row['case'][0], 'phase': row['case'][1], 'microseconds': ms * 1000}
                for ms in row['elapsed_ms'][batch * middle:(batch + 1) * middle])
        quick['batches'].append({'version': 'after', 'samples': samples})
    return {'measurement': {'complete': True, 'profile': reference['profile'], 'calibration': copy.deepcopy(reference['calibration'])},
        'render': render, **loans, 'quicksort': quick}


class BaselineDataTests(unittest.TestCase):
    def test_invalid_measurements_cannot_pass(self):
        for value in (-1, float('inf'), float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare_times([1, 1], [value, value], {})
        for value in (-1, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare_work(1, value, {})

    def test_calibration_compensates_host_speed_but_rejects_noise(self):
        self.assertEqual(calibration_scale([10] * 8, [20] * 8, .25), .5)
        for samples in ([], [0] * 8, [10, 20, 10, 20], [float('nan')] * 8):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                calibration_scale([10] * 8, samples, .25)

    def test_policy_and_required_commands_do_not_pin_history(self):
        policy = json.loads((ROOT / 'tests/baselines/approved.json').read_text())
        self.assertEqual(policy['version'], 2)
        self.assertNotIn('revision', policy)
        quick = (ROOT / 'tests/performance/bench_quicksort.py').read_text()
        self.assertNotIn('default=BASELINE', quick)
        from performance import gate
        import inspect
        self.assertNotIn('--source-ref', inspect.getsource(gate.measure))
        self.assertNotIn('--baseline', inspect.getsource(gate.measure))

    def test_approved_data_is_complete_and_detects_regressions(self):
        # Recorded metrics exercise the policy without rebuilding historical code.
        reference_path = ROOT / 'tests/baselines/approved-metrics.json'
        self.assertTrue(reference_path.is_file())
        reference = json.loads(reference_path.read_text())
        self.assertEqual(reference['version'], 1)
        self.assertTrue(reference['render'])
        self.assertTrue(reference['loans'])
        self.assertEqual(len(reference['quicksort']), 4)
        policy = json.loads((ROOT / 'tests/baselines/approved.json').read_text())
        measured = observations(reference)
        results, _ = compare_reference(reference, measured, policy)
        self.assertTrue(all(row['passed'] for row in results))
        self.assertEqual(make_reference(measured, policy)['loans'], reference['loans'])
        for defect in ('slow', 'work', 'gap', 'missing', 'render-sample', 'duplicate-render', 'profile', 'fixture', 'calibration'):
            with self.subTest(defect=defect):
                changed = copy.deepcopy(measured)
                if defect == 'slow':
                    for row in changed['loans']['samples']: row['ms'] = row['ms'] * 100 + 100
                elif defect == 'work':
                    for row in changed['loans']['samples']: row['inventory_calls'] += 100000
                elif defect == 'gap':
                    for row in changed['render']['summary']:
                        if row['model'] == 'distributed': row['max_render_gap_simulated_ms']['max'] = 1000
                elif defect == 'missing': changed['loans']['samples'].pop()
                elif defect == 'render-sample': changed['render']['samples'].pop()
                elif defect == 'duplicate-render': changed['render']['summary'].append(changed['render']['summary'][0])
                elif defect == 'profile': changed['measurement']['profile'] = {}
                elif defect == 'fixture': changed['render']['fixture_sha256'] = {}
                else: changed['measurement']['calibration']['loans']['before'][0] *= 100
                if defect in ('slow', 'work', 'gap'):
                    results, _ = compare_reference(reference, changed, policy)
                    self.assertFalse(all(row['passed'] for row in results))
                else:
                    with self.assertRaises(ValueError): compare_reference(reference, changed, policy)

    def test_recording_cannot_overwrite_approved_data(self):
        from unittest.mock import patch
        from performance import record_baseline
        with patch('sys.argv', ['record', '--output', str(ROOT / 'tests/baselines')]), self.assertRaises(ValueError):
            record_baseline.main()
