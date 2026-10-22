"""Record candidate reference data under results/ for review; never overwrite approved budgets."""
import argparse
import json
from pathlib import Path
from performance.gate import compare_reference, make_reference, measure, read_measurements
from support.data import ROOT, load_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--policy', type=Path, default=ROOT / 'tests/baselines/approved.json')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / 'results'):
        raise ValueError('Candidate baseline data must be recorded under results/')
    policy = load_json(args.policy.read_text())
    if policy['version'] != 2 or 'revision' in policy:
        raise ValueError('A version 2 data baseline without a Git revision is required')
    measure(args.output, policy)
    measured = read_measurements(args.output)
    reference = make_reference(measured, policy)
    results, _ = compare_reference(reference, measured, policy)
    if not all(row['passed'] for row in results):
        raise ValueError('Candidate measurements fail their own behavior or responsiveness checks')
    (args.output / 'reference.json').write_text(json.dumps(reference, indent=2) + '\n')
    print('Candidate data recorded for review; approved baseline unchanged', flush=True)


if __name__ == '__main__':
    main()
