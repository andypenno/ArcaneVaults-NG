"""Run committed suites and keep every result outside release ZIP directories."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools/release'), str(ROOT / 'tests')]
from support.data import load_json


def fingerprint(root=ROOT):
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root).decode().split('\0')
    digest = hashlib.sha256()
    for name in sorted(set(paths)):
        path = root / name
        if name == 'docs/TODO.md' or not path.is_file() or name.startswith(('extern/', 'lib/')):
            continue
        digest.update(name.encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def select(manifest, suites, names):
    known = {suite for item in manifest['tests'] for suite in item['suites']} | {'all', 'release'}
    if set(suites) - known:
        raise ValueError(f"Unknown suites: {set(suites) - known}")
    population = {item['id']: item for item in manifest['tests']}
    if len(population) != len(manifest['tests']) or set(names) - population.keys():
        raise ValueError('Duplicate or unknown test ID')
    selected = [item for item in manifest['tests'] if (not names or item['id'] in names) and
                ('all' in suites or ('release' in suites and item.get('release', True)) or set(suites) & set(item['suites']))]
    if not selected:
        raise ValueError('No tests selected')
    return selected


def run(suites, output=None, names=(), zip_path=None, sanitize=False, baseline=None):
    manifest = load_json((ROOT / 'tests/manifest.json').read_text())
    selected = select(manifest, suites, names)
    output = Path(output or ROOT / 'results/tests' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])).resolve()
    if output.is_relative_to(ROOT / 'build') or output.is_relative_to(ROOT / '.build'):
        raise ValueError('Test results must be outside build/ and .build/')
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / 'results'):
        raise ValueError('Repository test output must be under results/')
    output.mkdir(parents=True, exist_ok=False)
    report = {'complete': False, 'source_sha256': fingerprint(), 'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT).strip()),
              'suites': suites, 'results': [], 'runner_pid': os.getpid(), 'active_child_pid': None}
    report_path = output / 'report.json'
    def save():
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(str(ROOT / p) for p in ('tests', 'tests/regression', 'tests/performance', 'tools/release'))
    env.pop('PYTHONOPTIMIZE', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['TMPDIR'] = str(output / 'temporary')
    Path(env['TMPDIR']).mkdir()
    replacements = {'{python}': sys.executable, '{results}': str(output), '{zip}': str(zip_path or ROOT / 'build/ArcaneVaults-NG.zip'),
                    '{baseline}': str(baseline or ROOT / 'tests/baselines/approved.json')}
    def interrupted(_sig, _frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, interrupted)
    save()
    try:
        for item in selected:
            command = [replacements.get(arg, arg.replace('{results}', str(output))) for arg in item['command']]
            if sanitize and item.get('sanitize'):
                command.append('--sanitize')
            log = output / (item['id'] + '.log')
            result = {'id': item['id'], 'status': 'running', 'command': command, 'log': str(log)}
            report['results'].append(result)
            print(f"RUN {item['id']}", flush=True)
            with log.open('w') as stream, subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True) as child:
                report['active_child_pid'] = child.pid
                save()
                try:
                    code = child.wait(timeout=item['timeout_seconds'])
                    result['status'] = 'passed' if code == 0 else 'failed'
                    result['exit_code'] = code
                    stream.flush()
                    if item['id'] == 'unit' and 'Ran 0 tests' in log.read_text():
                        result['status'] = 'failed'
                        result['error'] = 'Unit discovery found no test cases'
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    result['status'] = 'timeout' if not isinstance(sys.exc_info()[1], KeyboardInterrupt) else 'cancelled'
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                    if result['status'] == 'cancelled':
                        raise
                finally:
                    report['active_child_pid'] = None
                    save()
            print(f"{result['status'].upper()} {item['id']}", flush=True)
        report['complete'] = True
        report['passed'] = all(row['status'] == 'passed' for row in report['results'])
        if report['source_sha256'] != fingerprint():
            report['passed'] = False
            report['error'] = 'Source changed during the test run'
        save()
    finally:
        signal.signal(signal.SIGTERM, previous)
        save()
    print(f"Report: {report_path}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', nargs='+', default=['unit', 'static-data'])
    parser.add_argument('--test', nargs='*', default=[])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    if args.list:
        for item in load_json((ROOT / 'tests/manifest.json').read_text())['tests']:
            print(item['id'], ','.join(item['suites']))
        return
    try:
        report = run(args.suite, args.output, args.test, args.zip, args.sanitize, args.baseline)
    except (ValueError, OSError, KeyboardInterrupt) as error:
        raise SystemExit(f'Test run failed: {error}')
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
