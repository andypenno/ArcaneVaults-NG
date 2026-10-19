"""Compare pinned production paths under identical fixture and compiler conditions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from support.data import ROOT, load_json
from support.performance import compare_times, compare_work


def verify(render_before, render_after, loans, policy):
    results = []
    def render_groups(report):
        if not report.get('complete') or report.get('responsiveness_regressions'):
            raise ValueError('Incomplete or unresponsive render probe')
        return {(r['model'], r['size'], r['entry'], r['shape'], r['archives_populated']): r for r in report['summary']}
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
        if any(len(rows) != policy['samples'] for rows in variants.values()):
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
            results.append({'case': list(case), 'metric': key, **compare_work(left[case], right[case], policy['work'])})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    policy = load_json(args.baseline.read_text())
    if policy['version'] != 1:
        raise ValueError('Unsupported performance policy')
    args.output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    affinity = None
    if hasattr(os, 'sched_getaffinity'):
        affinity = min(os.sched_getaffinity(0))
        os.sched_setaffinity(0, {affinity})
    compiler = subprocess.check_output(['g++', '--version'], text=True).splitlines()[0]
    report = {'complete': False, 'passed': False, 'policy_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
              'baseline': policy['revision'], 'compiler': compiler, 'host': platform.platform(), 'cpu_affinity': affinity, 'boundaries':
              'Host fixture elapsed time and declared simulated native costs, not measured Skyrim performance.'}
    target = args.output / 'report.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    def execute(name, arguments):
        with (args.output / (name + '.log')).open('w') as log:
            subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    for label, revision in [('baseline', policy['revision']), ('working', None)]:
        command = ['tests/regression/check_quick_transfer_pipeline.py', '--render-probe', '--sizes', *map(str, policy['sizes']),
                   '--cost-models', 'zero', 'distributed', 'slow-read', 'slow-remove', 'slow-bulk', 'slow-preflight',
                   '--samples', '2', '--output', str(args.output / (label + '-render.json'))]
        if revision:
            command += ['--source-ref', revision]
        execute(label + '-render', command)
        print(f'Completed {label} rendering/work probes', flush=True)
    execute('loans', ['tests/performance/bench_crafting_loans.py', '--baseline', policy['revision'], '--sizes', *map(str, policy['sizes']),
                      '--samples', str(policy['samples']), '--output', str(args.output / 'loans.json')])
    execute('loans-all', ['tests/performance/bench_crafting_loans.py', '--all-materials', '--baseline', policy['revision'], '--sizes', *map(str, policy['sizes']), '--samples', str(policy['samples']), '--output', str(args.output / 'loans-all.json')])
    execute('quicksort', ['tests/performance/bench_quicksort.py', '--baseline', policy['revision'], '--output', str(args.output / 'quicksort.json')])
    results = verify(load_json((args.output / 'baseline-render.json').read_text()), load_json((args.output / 'working-render.json').read_text()),
                     {'samples': load_json((args.output / 'loans.json').read_text())['samples'] + load_json((args.output / 'loans-all.json').read_text())['samples']}, policy)
    quick = load_json((args.output / 'quicksort.json').read_text())
    cases = {(s['items'], s['phase']) for b in quick['batches'] for s in b['samples']}
    if not cases:
        raise ValueError('Missing Quick Transfer host timings')
    for case in sorted(cases):
        variants = {label: [s['microseconds'] / 1000 for b in quick['batches'] if b['version'] == label for s in b['samples'] if (s['items'], s['phase']) == case] for label in ('before', 'after')}
        results.append({'case': list(case), 'metric': 'quicksort_host_elapsed_ms', **compare_times(variants['before'], variants['after'], policy['timing'])})
    if any(row.get('status') == 'inconclusive' for row in results):
        print('Timing noise requires the declared repeated loan comparison', flush=True)
        for name, extra in [('loans-repeat', []), ('loans-all-repeat', ['--all-materials'])]:
            execute(name, ['tests/performance/bench_crafting_loans.py', *extra, '--baseline', policy['revision'], '--sizes', *map(str, policy['sizes']),
                           '--samples', str(policy['retry_samples']), '--output', str(args.output / (name + '.json'))])
        repeated = verify(load_json((args.output / 'baseline-render.json').read_text()), load_json((args.output / 'working-render.json').read_text()),
                          {'samples': load_json((args.output / 'loans-repeat.json').read_text())['samples'] + load_json((args.output / 'loans-all-repeat.json').read_text())['samples']},
                          {**policy, 'samples': policy['retry_samples']})
        results = repeated + [row for row in results if row['metric'] == 'quicksort_host_elapsed_ms']
        report['loan_repeated_samples'] = policy['retry_samples']
    report.update(complete=True, passed=all(r['passed'] for r in results), comparisons=results)
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(f"Performance decisions: {len(results)}; failures: {sum(not r['passed'] for r in results)}; {target}")
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
