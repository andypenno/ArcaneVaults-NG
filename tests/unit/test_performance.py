import unittest
from support.performance import compare_times, compare_work


class PerformancePolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = {'absolute_ms': 1, 'relative_increase': .25, 'noise_multiplier': 2}

    def test_material_slowdown_fails(self):
        self.assertFalse(compare_times([10, 10.1, 10, 10.1], [20, 20.1, 20, 20.1], self.policy)['passed'])

    def test_noise_and_small_costs(self):
        self.assertTrue(compare_times([10, 13], [12, 14], self.policy)['passed'])
        self.assertTrue(compare_times([.01, .02], [.1, .2], self.policy)['passed'])

    def test_work_budget(self):
        policy = {'relative_increase': .1, 'absolute_calls': 8}
        self.assertTrue(compare_work(100, 110, policy)['passed'])
        self.assertFalse(compare_work(100, 1000, policy)['passed'])

    def test_invalid_samples(self):
        with self.assertRaises(ValueError):
            compare_times([], [1], self.policy)

    def test_material_but_noisy_is_not_a_pass(self):
        result = compare_times([10, 10], [15, 25], self.policy)
        self.assertEqual(result['status'], 'inconclusive')
        self.assertFalse(result['passed'])

    def test_complete_matrix_and_missing_samples(self):
        import copy
        from performance.gate import verify
        policy = {'sizes': [0], 'samples': 2, 'render_gap_ms': 50, 'timing': self.policy,
                  'work': {'relative_increase': .1, 'absolute_calls': 8}}
        models = ('zero', 'distributed', 'slow-read', 'slow-remove', 'slow-bulk', 'slow-preflight')
        rows = [{'model': model, 'size': 0, 'entry': entry, 'shape': shape, 'archives_populated': archived,
                 'max_render_gap_simulated_ms': {'max': 20}} for model in models for entry in range(3) for shape in range(7) for archived in (False, True)]
        render = {'complete': True, 'responsiveness_regressions': [], 'summary': rows,
                  'samples': [{'model': model, 'size': 0, 'cases': [{**row, 'charged_native_calls': 10} for row in rows if row['model'] == model]} for model in models]}
        samples = [{'bench': bench, 'size': 0, 'mode': mode, 'phase': phase, 'scenario': 0, 'all_materials': materials,
                    'variant': variant, 'validated': True, 'ms': 1, 'inventory_calls': 2, 'entries_visited': 3,
                    'entries_copied': 1, 'moves': 1, 'bulk_calls': 1}
                   for bench in range(1, 6) for mode in (0, 1) for phase in ('take', 'return') for materials in (False, True)
                   for variant in ('baseline', 'working') for _ in range(2)]
        self.assertTrue(all(r['passed'] for r in verify(render, render, {'samples': samples}, policy)))
        with self.assertRaises(ValueError):
            verify(render, render, {'samples': samples[:-1]}, policy)
        broken = copy.deepcopy(render)
        broken['summary'].pop()
        with self.assertRaises(ValueError):
            verify(broken, broken, {'samples': samples}, policy)
        slower = copy.deepcopy(samples)
        for sample in slower:
            if sample['variant'] == 'working':
                sample['ms'] = 100
        self.assertFalse(all(r['passed'] for r in verify(render, render, {'samples': slower}, policy)))
        sliced_policy = {**policy, 'render_archive_native_calls_per_base': 3}
        archived = copy.deepcopy(render)
        for sample in archived['samples']:
            for row in sample['cases']:
                row['archive_input_bases'] = 5 if row['archives_populated'] else 0
        candidate = copy.deepcopy(archived)
        for sample in candidate['samples']:
            for row in sample['cases']:
                if row['archives_populated']:
                    row['charged_native_calls'] += 15
        self.assertTrue(all(r['passed'] for r in verify(archived, candidate, {'samples': samples}, sliced_policy)))
        unrelated = copy.deepcopy(candidate)
        for sample in unrelated['samples']:
            for row in sample['cases']:
                row['charged_native_calls'] += 30
        self.assertFalse(all(r['passed'] for r in verify(archived, unrelated, {'samples': samples}, sliced_policy)))
        candidate['samples'][0]['cases'][0]['archive_input_bases'] = 999
        with self.assertRaises(ValueError):
            verify(archived, candidate, {'samples': samples}, sliced_policy)
