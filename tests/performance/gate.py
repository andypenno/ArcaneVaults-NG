"""Check current production paths against approved measurements without historical source lookups."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from support.data import ROOT, load_json
from support.performance import calibration_scale, compare_times, compare_work


def verify(render_before, render_after, loans, policy):
    results = []
    def render_groups(report):
        if not report.get('complete') or report.get('responsiveness_regressions'):
            raise ValueError('Incomplete or unresponsive render probe')
        rows = {(r['model'], r['size'], r['entry'], r['shape'], r['archives_populated']): r for r in report['summary']}
        if len(rows) != len(report['summary']):
            raise ValueError('Duplicate render scenarios')
        return rows
    before, after = render_groups(render_before), render_groups(render_after)
    if not before or before.keys() != after.keys():
        raise ValueError('Render scenario populations differ')
    expected_render = {(model, size, entry, shape, archived) for model in ('zero', 'distributed', 'slow-read', 'slow-remove', 'slow-bulk', 'slow-preflight')
                       for size in policy['sizes'] for entry in range(3) for shape in range(7) for archived in (False, True)}
    if set(after) != expected_render:
        raise ValueError('Incomplete render scenario matrix')
    for key, row in after.items():
        if key[0] == 'distributed':
            gap = row['max_render_gap_simulated_ms']['max']
            results.append({'case': list(key), 'metric': 'render_gap_simulated_ms', 'passed': gap <= policy['render_gap_ms'], 'candidate': gap})
    samples = loans['samples']
    if not samples or any(not s['validated'] for s in samples) or loans.get('timeouts'):
        raise ValueError('Missing or unvalidated loan round trips')
    groups = {}
    for sample in samples:
        key = tuple(sample[k] for k in ('bench', 'size', 'mode', 'phase', 'scenario', 'all_materials'))
        groups.setdefault(key, {}).setdefault(sample['variant'], []).append(sample)
    expected_loans = {(bench, size, mode, phase, scenario, materials) for bench in range(1, 6) for size in policy['sizes']
                      for mode in (0, 1) for phase in ('take', 'return') for scenario in range(3)
                      for materials in (False, True) if size or scenario == 0}
    if set(groups) != expected_loans:
        raise ValueError('Incomplete loan scenario matrix')
    for key, variants in groups.items():
        if set(variants) != {'baseline', 'working'}:
            raise ValueError('Missing baseline/candidate loan samples')
        if len(variants['working']) != policy['samples'] or len(variants['baseline']) != policy.get('reference_samples', policy['samples']):
            raise ValueError('Incomplete loan samples')
        result = compare_times([s['ms'] for s in variants['baseline']], [s['ms'] for s in variants['working']], policy['timing'])
        results.append({'case': list(key), 'metric': 'host_elapsed_ms', **result})
        for metric in ('inventory_calls', 'entries_visited', 'entries_copied', 'moves', 'bulk_calls'):
            values = {}
            for name, rows in variants.items():
                counts = {s[metric] for s in rows}
                if len(counts) != 1:
                    raise ValueError(f'Non-deterministic work counter: {key} {metric}')
                values[name] = counts.pop()
            results.append({'case': list(key), 'metric': metric, **compare_work(values['baseline'], values['working'], policy['work'])})
    for key in ('charged_native_calls',):
        def native(report):
            result = {}
            for s in report['samples']:
                for c in s['cases']:
                    case = (s['model'], s['size'], c['entry'], c['shape'], c['archives_populated'])
                    result[case] = max(result.get(case, 0), c[key])
            return result
        left, right = native(render_before), native(render_after)
        if left.keys() != right.keys():
            raise ValueError('Native-call scenario populations differ')
        for case in right:
            result = compare_work(left[case], right[case], policy['work'])
            per_base = policy.get('render_archive_native_calls_per_base', 0)
            if per_base:
                expected_bases = (5 + (case[1] if case[3] == 3 else 0)) if case[4] else 0
                for report in (render_before, render_after):
                    for sample in report['samples']:
                        if (sample['model'], sample['size']) != case[:2]:
                            continue
                        for row in sample['cases']:
                            if (row['entry'], row['shape'], row['archives_populated']) == case[2:] and row.get('archive_input_bases') != expected_bases:
                                raise ValueError('Archive input population differs from the declared fixture')
                result['archive_slicing_allowance'] = per_base * expected_bases
                result['limit'] += result['archive_slicing_allowance']
                result['passed'] = right[case] <= result['limit']
            results.append({'case': list(case), 'metric': key, **result})
    return results



MODELS = ('zero', 'distributed', 'slow-read', 'slow-remove', 'slow-bulk', 'slow-preflight')
CASE_FIELDS = ('bench', 'size', 'mode', 'phase', 'scenario', 'all_materials')
WORK_FIELDS = ('inventory_calls', 'entries_visited', 'entries_copied', 'moves', 'bulk_calls')


def measurement_profile():
    control = ROOT / 'tests/performance/calibration.cpp'
    return {'machine': platform.machine(),
        'compiler_major': subprocess.check_output(['g++', '-dumpversion'], text=True).strip().split('.')[0],
        'calibration_sha256': hashlib.sha256(control.read_bytes()).hexdigest(), 'flags': ['-O2', '-std=c++20']}


def measure(output, policy):
    output.mkdir(parents=True, exist_ok=False)
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    control = ROOT / 'tests/performance/calibration.cpp'
    report = {'complete': False, 'profile': measurement_profile(),
        'compiler': subprocess.check_output(['g++', '--version'], text=True).splitlines()[0], 'calibration': {}}
    target = output / 'measurement.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='av-calibration-') as directory:
        binary = Path(directory) / 'calibrate'
        subprocess.run(['g++', '-O2', '-std=c++20', str(control), '-o', str(binary)], check=True, timeout=60)
        def execute(name, arguments, timed=True):
            calibration = {}
            if timed:
                calibration['before'] = list(map(float, subprocess.check_output([str(binary)], text=True, timeout=30).splitlines()))
            with (output / (name + '.log')).open('w') as log:
                subprocess.run([sys.executable, *arguments], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
            if timed:
                calibration['after'] = list(map(float, subprocess.check_output([str(binary)], text=True, timeout=30).splitlines()))
                report['calibration'][name] = calibration
                calibration_scale(calibration['before'], calibration['after'], policy['calibration_relative_noise'])
            target.write_text(json.dumps(report, indent=2) + '\n')
            print('Completed ' + name, flush=True)
        execute('render', ['tests/regression/check_quick_transfer_pipeline.py', '--render-probe', '--sizes', *map(str, policy['sizes']),
                '--cost-models', *MODELS, '--samples', '2', '--output', str(output / 'render.json')], timed=False)
        for name, extra in [('loans', []), ('loans-all', ['--all-materials'])]:
            execute(name, ['tests/performance/bench_crafting_loans.py', *extra, '--sizes', *map(str, policy['sizes']),
                    '--samples', str(policy['samples']), '--output', str(output / (name + '.json'))])
        execute('quicksort', ['tests/performance/bench_quicksort.py', '--output', str(output / 'quicksort.json')])
    report['complete'] = True
    target.write_text(json.dumps(report, indent=2) + '\n')
    return report


def read_measurements(output):
    return {name: load_json((output / (name + '.json')).read_text()) for name in ('measurement', 'render', 'loans', 'loans-all', 'quicksort')}


def make_reference(measured, policy):
    if not measured['measurement']['complete']:
        raise ValueError('Incomplete measurement')
    render = measured['render']
    if measured['loans']['harness_sha256'] != measured['loans-all']['harness_sha256']:
        raise ValueError('Loan measurement fixtures differ')
    reference = {'version': 1, 'profile': measured['measurement']['profile'], 'samples': policy['samples'],
        'calibration': measured['measurement']['calibration'], 'fixture_sha256': render['fixture_sha256'],
        'loan_harness': measured['loans']['harness_sha256'], 'quicksort_harness': measured['quicksort']['harness_sha256'],
        'render': [], 'loans': [], 'quicksort': []}
    native = {}
    render_samples = set()
    for sample in render['samples']:
        identity = (sample['model'], sample['size'], sample['sample'])
        if identity in render_samples:
            raise ValueError('Duplicated render sample')
        render_samples.add(identity)
        cases = {(case['entry'], case['shape'], case['archives_populated']) for case in sample['cases']}
        expected_cases = {(entry, shape, archived) for entry in range(3) for shape in range(7) for archived in (False, True)}
        if cases != expected_cases or len(sample['cases']) != len(cases):
            raise ValueError('Incomplete render sample')
        for case in sample['cases']:
            key = (sample['model'], sample['size'], case['entry'], case['shape'], case['archives_populated'])
            expected = (5 + (sample['size'] if case['shape'] == 3 else 0)) if case['archives_populated'] else 0
            if case['archive_input_bases'] != expected:
                raise ValueError('Render archive population changed')
            native[key] = max(native.get(key, 0), case['charged_native_calls'])
    if render_samples != {(model, size, sample) for model in MODELS for size in policy['sizes'] for sample in range(2)}:
        raise ValueError('Incomplete render samples')
    for row in render['summary']:
        gap = row['max_render_gap_simulated_ms']['max']
        if not math.isfinite(gap) or gap < 0:
            raise ValueError('Invalid render gap')
        case = [row[k] for k in ('model', 'size', 'entry', 'shape', 'archives_populated')]
        reference['render'].append({'case': case, 'calls': native[tuple(case)], 'gap_ms': gap})
    groups = {}
    for name in ('loans', 'loans-all'):
        for sample in measured[name]['samples']:
            if not sample['validated'] or sample['variant'] != 'working' or measured[name].get('timeouts'):
                raise ValueError('Incomplete or unexpected loan measurements')
            groups.setdefault(tuple(sample[k] for k in CASE_FIELDS), []).append(sample)
    for case, rows in sorted(groups.items()):
        work = [rows[0][k] for k in WORK_FIELDS]
        if any(type(count) is not int or count < 0 for count in work):
            raise ValueError('Invalid reference work counts')
        if any([row[k] for k in WORK_FIELDS] != work for row in rows):
            raise ValueError('Non-deterministic reference work counts')
        reference['loans'].append({'case': list(case), 'elapsed_ms': [row['ms'] for row in rows], 'work': work})
    quick = measured['quicksort']
    if not quick.get('complete') or len(quick['batches']) != 2:
        raise ValueError('Incomplete Quick Transfer measurements')
    groups = {}
    for batch in quick['batches']:
        if batch['version'] != 'after':
            raise ValueError('Reference recording must measure current sources only')
        for sample in batch['samples']:
            groups.setdefault((sample['items'], sample['phase']), []).append(sample['microseconds'] / 1000)
    for case, samples in sorted(groups.items()):
        reference['quicksort'].append({'case': list(case), 'elapsed_ms': samples})
    return reference


def compare_reference(reference, measured, policy):
    current = make_reference(measured, policy)
    if reference['version'] != 1 or reference['profile'] != current['profile']:
        raise ValueError('Unapproved measurement profile or reference version')
    for key in ('fixture_sha256', 'loan_harness', 'quicksort_harness'):
        if reference[key] != current[key]:
            raise ValueError('Measurement fixtures changed: ' + key)
    scales = {}
    for name in ('loans', 'loans-all', 'quicksort'):
        before = reference['calibration'][name]
        after = current['calibration'][name]
        scales[name] = calibration_scale(before['before'] + before['after'], after['before'] + after['after'], policy['calibration_relative_noise'])
    ref_render = {'complete': True, 'responsiveness_regressions': [], 'summary': [], 'samples': []}
    for row in reference['render']:
        model, size, entry, shape, archived = row['case']
        ref_render['summary'].append({'model': model, 'size': size, 'entry': entry, 'shape': shape, 'archives_populated': archived,
                'max_render_gap_simulated_ms': {'max': row['gap_ms']}})
        ref_render['samples'].append({'model': model, 'size': size, 'cases': [{'entry': entry, 'shape': shape,
                'archives_populated': archived, 'charged_native_calls': row['calls']}]})
    samples = []
    for row in reference['loans']:
        for elapsed in row['elapsed_ms']:
            samples.append({**dict(zip(CASE_FIELDS, row['case'], strict=True)), **dict(zip(WORK_FIELDS, row['work'], strict=True)),
                            'ms': elapsed, 'variant': 'baseline', 'validated': True})
    for name in ('loans', 'loans-all'):
        for sample in measured[name]['samples']:
            samples.append({**sample, 'ms': sample['ms'] * scales[name]})
    results = verify(ref_render, measured['render'], {'samples': samples}, {**policy, 'reference_samples': reference['samples']})
    quick_cases = {(size, phase) for size in (100, 1000) for phase in ('snapshot', 'snapshot_and_transfer')}
    left = {tuple(row['case']): row['elapsed_ms'] for row in reference['quicksort']}
    right = {tuple(row['case']): row['elapsed_ms'] for row in current['quicksort']}
    if set(left) != quick_cases or set(right) != quick_cases or len(reference['quicksort']) != len(left):
        raise ValueError('Incomplete or duplicated Quick Transfer matrix')
    for case in sorted(quick_cases):
        expected = 12 if case[1] == 'snapshot' else 4
        if len(left[case]) != expected or len(right[case]) != expected:
            raise ValueError('Incomplete Quick Transfer samples')
        results.append({'case': list(case), 'metric': 'quicksort_calibrated_ms',
            **compare_times(left[case], [value * scales['quicksort'] for value in right[case]], policy['timing'])})
    for row in results:
        if row['metric'] == 'host_elapsed_ms':
            row['metric'] = 'loan_calibrated_ms'
    return results, scales


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    policy = load_json(args.baseline.read_text())
    if policy['version'] != 2 or 'revision' in policy:
        raise ValueError('A version 2 data baseline without a Git revision is required')
    reference = load_json((args.baseline.parent / policy['reference']).read_text())
    if reference['version'] != 1 or reference['profile'] != measurement_profile():
        raise ValueError('No approved data for this compiler, architecture or calibration schema')
    measure(args.output, policy)
    target = args.output / 'report.json'
    report = {'complete': False, 'passed': False, 'policy_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        'reference_sha256': hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest(),
        'boundary': 'Current production under engine stubs; host timing calibrated to approved data, not Skyrim frame measurements.'}
    target.write_text(json.dumps(report, indent=2) + '\n')
    results, scales = compare_reference(reference, read_measurements(args.output), policy)
    report.update(complete=True, passed=all(row['passed'] for row in results), calibration_scales=scales, comparisons=results)
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(f"Performance decisions: {len(results)}; failures: {sum(not row['passed'] for row in results)}; {target}", flush=True)
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
