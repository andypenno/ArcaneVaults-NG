"""Provision the documented Wine/MSVC environment without using a local installation."""
import argparse
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'docker.io/library/ubuntu@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55'
LABEL = 'io.arcanevaults.ci-bootstrap'


def validate_container(info, root, work):
    expected = {'/repo': root, '/work': work, '/root/.xmake/packages': work / 'xmake-packages'}
    mounts = {item['Destination']: Path(item['Source']).resolve() for item in info['Mounts']}
    if (mounts != expected or (info['Config'].get('Labels') or {}).get(LABEL) != '1'
            or info.get('ImageName') != IMAGE or '_CL_=/Z7' not in info['Config'].get('Env', [])):
        raise ValueError('Existing container is not this checkout\'s CI toolchain')


def bootstrap(container, work, output):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('The Wine build requires Linux x86_64')
    work, output = Path(work).resolve(), Path(output).resolve()
    if work == ROOT or not output.is_relative_to(ROOT / 'results'):
        raise ValueError('Use a separate work directory and put reports under results/')
    output.mkdir(parents=True, exist_ok=False)
    report = {'complete': False, 'passed': False, 'image': IMAGE, 'container': container, 'work': str(work)}
    report_path = output / 'report.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Bootstrap log: {output / "bootstrap.log"}', flush=True)
    try:
        (work / 'xmake-packages').mkdir(parents=True, exist_ok=True)
        with (output / 'bootstrap.log').open('w') as log:
            def run(args, capture=False):
                return subprocess.run(args, cwd=ROOT, check=True, text=True,
                                      stdout=subprocess.PIPE if capture else log, stderr=log)
            exists = subprocess.run(['podman', 'container', 'exists', container], stdout=log, stderr=log)
            if exists.returncode not in (0, 1):
                raise RuntimeError('Podman could not inspect the container')
            if exists.returncode == 1:
                run(['podman', 'pull', '--platform', 'linux/amd64', IMAGE])
                run(['podman', 'run', '-d', '--init', '--name', container, '--label', LABEL + '=1',
                     '-e', '_CL_=/Z7',
                     '-v', f'{ROOT}:/repo', '-v', f'{work}:/work',
                     '-v', f'{work / "xmake-packages"}:/root/.xmake/packages', IMAGE, 'sleep', 'infinity'])
            info = json.loads(run(['podman', 'inspect', container], capture=True).stdout)[0]
            validate_container(info, ROOT, work)
            if not info['State']['Running']:
                run(['podman', 'start', container])
            run(['podman', 'exec', container, 'bash', '/repo/tools/ci/provision_wine.sh'])
            report['packages'] = run(['podman', 'exec', container, 'dpkg-query', '-W',
                                      'wine', 'wine64', 'g++', 'cmake', 'ninja-build'], capture=True).stdout
        report.update(complete=True, passed=True)
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Wine/MSVC bootstrap passed: {report_path}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', default='arcanevault-ci')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'results/ci/bootstrap')
    args = parser.parse_args()
    bootstrap(args.container, args.work_dir, args.output)
