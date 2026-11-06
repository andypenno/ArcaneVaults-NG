"""Build an unverified CI candidate and publish it only after matching check reports pass."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/release'), str(ROOT / 'tests')]
from artifacts import promote, release_id
from build_release import assemble, digest
from run import fingerprint, run as run_suites, select
from support.data import load_json
from validate import require, validate_zip


def required_checks():
    return {row['id'] for row in select(load_json((ROOT / 'tests/manifest.json').read_text()), ['release'], [])}


def matrix():
    return {'include': [{'check': name} for name in sorted(required_checks() - {'wine-toolchain'})]}


def candidate(container):
    output = ROOT / 'results/ci/build'
    output.mkdir(parents=True, exist_ok=False)
    before = fingerprint()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    os.environ['AV_WINE_CONTAINER'] = container
    toolchain = run_suites(['release'], output / 'toolchain', names=['wine-toolchain'], sanitize=True)
    require(toolchain['passed'], 'Wine toolchain verification failed')
    assembled = assemble(container, output, ROOT / 'build/history' / release_id(ROOT))
    require(fingerprint() == before, 'Source changed during candidate assembly')
    bundle = ROOT / '.build/ci/candidate'
    bundle.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(assembled['candidate'], bundle / 'ArcaneVaults-NG.zip')
    shutil.copyfile(output / 'toolchain/report.json', bundle / 'toolchain.json')
    report = {**assembled, 'stage': 'candidate', 'complete': True, 'passed': False,
              'commit': commit, 'source_sha256': before}
    (bundle / 'candidate.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Unverified candidate: {bundle}', flush=True)


def validate_reports(candidate_report, reports, commit, source):
    require(candidate_report.get('stage') == 'candidate' and candidate_report.get('complete') is True
            and candidate_report.get('passed') is False, 'Expected an unverified, complete candidate')
    require(candidate_report.get('commit') == commit and candidate_report.get('source_sha256') == source,
            'Candidate belongs to a different commit or source tree')
    require(candidate_report.get('windows_inventory_scenarios') is True, 'Missing Windows inventory checks')
    expected = required_checks()
    verified = set()
    for report in reports:
        require(report.get('complete') is True and report.get('passed') is True, 'Incomplete or failed check report')
        require(report.get('commit') == commit and report.get('source_sha256') == source,
                'Check report belongs to a different commit or source tree')
        require(bool(report.get('results')), 'Empty check report')
        for result in report['results']:
            name = result.get('id')
            require(isinstance(name, str) and name in expected and result.get('status') == 'passed'
                    and name not in verified, 'Failed, unknown or duplicate check result')
            verified.add(name)
    require(verified == expected, f'Required check population differs: {sorted(verified ^ expected)}')


def publish():
    bundle = ROOT / '.build/ci/candidate'
    report = load_json((bundle / 'candidate.json').read_text())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    before = fingerprint()
    paths = sorted((ROOT / 'results/ci/checks').glob('*/report.json'))
    reports = [load_json((bundle / 'toolchain.json').read_text())]
    reports.extend(load_json(path.read_text()) for path in paths)
    validate_reports(report, reports, commit, before)
    archive = bundle / 'ArcaneVaults-NG.zip'
    require(digest(archive.read_bytes()) == report.get('zip_sha256'), 'Candidate ZIP checksum differs')
    require(validate_zip(ROOT, archive) == report.get('checks'), 'Candidate ZIP validation differs')
    output = ROOT / 'results/ci/publish'
    output.mkdir(parents=True, exist_ok=False)
    history = ROOT / 'build/history' / release_id(ROOT)
    history.mkdir(parents=True, exist_ok=False)
    archived = history / 'ArcaneVaults-NG.zip'
    shutil.copyfile(archive, archived)
    package = run_suites(['packaging'], output / 'packaging', zip_path=archived)
    require(package['passed'], 'Candidate packaging verification failed')
    require(fingerprint() == before, 'Source changed during final verification')
    report.update(stage='verified', passed=True, candidate=str(archived),
                  tests=[str(path) for path in paths], packaging=str(output / 'packaging/report.json'))
    (output / 'artifact.json').write_text(json.dumps(report, indent=2) + '\n')
    final = promote(ROOT, archived, report, validate_zip)
    print(f'Verified {final}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['matrix', 'candidate', 'publish'])
    parser.add_argument('--container', default='arcanevault-ci')
    args = parser.parse_args()
    if args.stage == 'matrix':
        print(json.dumps(matrix(), separators=(',', ':')))
    elif args.stage == 'candidate':
        candidate(args.container)
    else:
        publish()
