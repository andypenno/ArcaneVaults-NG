import copy
import contextlib
import io
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from support.data import ROOT

spec = importlib.util.spec_from_file_location('bootstrap_wine', ROOT / 'tools/ci/bootstrap_wine.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


pipeline_spec = importlib.util.spec_from_file_location('ci_pipeline', ROOT / 'tools/ci/pipeline.py')
pipeline = importlib.util.module_from_spec(pipeline_spec)
pipeline_spec.loader.exec_module(pipeline)


class CITests(unittest.TestCase):
    def test_manifest_update_exit_codes(self):
        spec = importlib.util.spec_from_file_location('ci_manifest', ROOT / 'tools/ci/manifest.py')
        manifest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manifest)
        for codes, notify, expected in [([1, 0], True, 187), ([0], True, 0),
                ([42], True, 42), ([1, 42], True, 42), ([1], False, 1)]:
            with self.subTest(codes=codes, notify=notify):
                args = ['/manifest', 'input', '/out:output'] + (['/notify_update'] if notify else [])
                with patch.object(manifest.subprocess, 'run', side_effect=[
                        subprocess.CompletedProcess([], code) for code in codes]) as run:
                    self.assertEqual(manifest.manifest(args), expected)
                    self.assertEqual(run.call_count, len(codes))
                    if len(codes) == 2:
                        self.assertNotIn('/notify_update', run.call_args.args[0])
                        self.assertEqual(run.call_args.args[0][1:], args[:-1])

    def container(self, root, work):
        return {'Mounts': [{'Destination': destination, 'Source': str(source)} for destination, source in
                          (('/repo', root), ('/work', work), ('/root/.xmake/packages', work / 'xmake-packages'))],
                'Config': {'Labels': {ci.LABEL: '1'}, 'Env': ['_CL_=/Z7']},
                'State': {'Running': False}, 'ImageName': ci.IMAGE}

    def test_container_ownership_and_mounts(self):
        root, work = Path('/repo-checkout'), Path('/tools')
        original = self.container(root, work)
        ci.validate_container(original, root, work)
        for mutation in ('repo', 'cache', 'label', 'labels-none', 'image', 'compiler-flags', 'extra'):
            info = copy.deepcopy(original)
            if mutation == 'repo': info['Mounts'][0]['Source'] = '/another-checkout'
            elif mutation == 'cache': info['Mounts'][2]['Source'] = '/another-cache'
            elif mutation == 'label': info['Config']['Labels'].clear()
            elif mutation == 'labels-none': info['Config']['Labels'] = None
            elif mutation == 'image': info['ImageName'] = 'another-image'
            elif mutation == 'compiler-flags': info['Config']['Env'] = []
            else: info['Mounts'].append({'Destination': '/extra', 'Source': '/extra'})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                ci.validate_container(info, root, work)

    def test_bootstrap_cold_reuse_and_failure(self):
        for mode in ('cold', 'reuse', 'running', 'failure', 'wrong-container', 'podman-error'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
                root, work = Path(directory) / 'repo', Path(directory) / 'work'
                output = root / 'results/bootstrap'
                root.mkdir()
                info = self.container(root, work)
                if mode == 'running': info['State']['Running'] = True
                if mode == 'wrong-container': info['Config']['Labels'].clear()
                commands = []
                def run(args, **kwargs):
                    commands.append(args)
                    if args[1:3] == ['container', 'exists']:
                        return subprocess.CompletedProcess(args, 125 if mode == 'podman-error' else int(mode == 'cold'))
                    if args[1] == 'inspect': return subprocess.CompletedProcess(args, 0, json.dumps([info]))
                    if 'provision_wine.sh' in args[-1] and mode == 'failure':
                        raise subprocess.CalledProcessError(17, args)
                    return subprocess.CompletedProcess(args, 0, 'wine\t9.0\n')
                with patch.object(ci, 'ROOT', root), patch.object(ci.platform, 'system', return_value='Linux'), \
                     patch.object(ci.platform, 'machine', return_value='x86_64'), patch.object(ci.subprocess, 'run', side_effect=run):
                    if mode in ('failure', 'wrong-container', 'podman-error'):
                        with self.assertRaises((subprocess.CalledProcessError, ValueError, RuntimeError)):
                            ci.bootstrap('test-ci', work, output)
                    else:
                        ci.bootstrap('test-ci', work, output)
                    report = json.loads((output / 'report.json').read_text())
                    self.assertEqual(report['passed'], mode in ('cold', 'reuse', 'running'))
                    self.assertEqual(report['complete'], report['passed'])
                    if mode == 'cold':
                        create = next(args for args in commands if args[1] == 'run')
                        self.assertIn(ci.IMAGE, create)
                        self.assertIn('--init', create)
                        self.assertIn('_CL_=/Z7', create)
                        self.assertIn(f'{work / "xmake-packages"}:/root/.xmake/packages', create)
                    if mode == 'reuse': self.assertIn(['podman', 'start', 'test-ci'], commands)
                    if mode == 'running': self.assertNotIn(['podman', 'start', 'test-ci'], commands)
                    if mode in ('wrong-container', 'podman-error'):
                        self.assertFalse(any(args[1] in ('start', 'exec') for args in commands))

    def test_bootstrap_rejects_wrong_host_paths_and_existing_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root, work = Path(directory) / 'repo', Path(directory) / 'tools'
            output = root / 'results/bootstrap'
            for system, machine, target, report in [('Windows', 'x86_64', work, output),
                    ('Linux', 'aarch64', work, output), ('Linux', 'x86_64', root, output),
                    ('Linux', 'x86_64', work, root / 'build/report')]:
                with patch.object(ci, 'ROOT', root), patch.object(ci.platform, 'system', return_value=system), \
                     patch.object(ci.platform, 'machine', return_value=machine), patch.object(ci.subprocess, 'run') as run:
                    with self.assertRaises(ValueError): ci.bootstrap('test-ci', target, report)
                    run.assert_not_called()
            output.mkdir(parents=True)
            (output / 'report.json').write_text('previous result')
            with patch.object(ci, 'ROOT', root), patch.object(ci.platform, 'system', return_value='Linux'), \
                 patch.object(ci.platform, 'machine', return_value='x86_64'), patch.object(ci.subprocess, 'run') as run:
                with self.assertRaises(FileExistsError): ci.bootstrap('test-ci', work, output)
                self.assertEqual((output / 'report.json').read_text(), 'previous result')
                run.assert_not_called()

    def test_recipe_pin_matches_locked_directxtk(self):
        import re
        lock = (ROOT / 'xmake-requires.lock').read_text()
        revision = re.search(r'\["directxtk [^"]+"\].*?commit = "([a-f0-9]+)"', lock, re.S).group(1)
        provision = (ROOT / 'tools/ci/provision_wine.sh').read_text()
        self.assertIn('checkout https://gitlab.com/tboox/xmake-repo.git ' + revision, provision)

    def test_parallel_matrix_accounts_for_every_release_check(self):
        checks = [row['check'] for row in pipeline.matrix()['include']]
        self.assertEqual(len(checks), len(set(checks)))
        self.assertEqual(set(checks) | {'wine-toolchain'}, pipeline.required_checks())
        self.assertNotIn('wine-toolchain', checks)
        self.assertIn('performance', checks)
        self.assertNotIn('packaging', checks)

    def test_verification_waits_for_candidate_build(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        verification = workflow.split('  verify:', 1)[1].split('  release:', 1)[0]
        self.assertIn('needs: [plan, build]', verification)

    def check_report(self, names):
        return {'complete': True, 'passed': True, 'commit': 'commit', 'source_sha256': 'source',
                'results': [{'id': name, 'status': 'passed'} for name in sorted(names)]}

    def candidate_report(self):
        return {'stage': 'candidate', 'complete': True, 'passed': False, 'commit': 'commit',
                'source_sha256': 'source', 'windows_inventory_scenarios': True}

    def test_publication_rejects_missing_failed_duplicate_and_stale_checks(self):
        candidate = self.candidate_report()
        report = self.check_report(pipeline.required_checks())
        pipeline.validate_reports(candidate, [report], 'commit', 'source')
        for defect in ('missing', 'failed', 'incomplete', 'duplicate', 'commit', 'source', 'empty',
                       'candidate-commit', 'candidate-source', 'candidate-verified', 'windows', 'unknown', 'malformed-id'):
            meta, result = copy.deepcopy(candidate), copy.deepcopy(report)
            if defect == 'missing': result['results'].pop()
            elif defect == 'failed': result['results'][0]['status'] = 'failed'
            elif defect == 'incomplete': result['complete'] = False
            elif defect == 'duplicate': result['results'].append(result['results'][0])
            elif defect == 'commit': result['commit'] = 'other'
            elif defect == 'source': result['source_sha256'] = 'other'
            elif defect == 'empty': result['results'] = []
            elif defect == 'candidate-commit': meta['commit'] = 'other'
            elif defect == 'candidate-source': meta['source_sha256'] = 'other'
            elif defect == 'candidate-verified': meta['passed'] = True
            elif defect == 'unknown': result['results'][0]['id'] = 'unknown-check'
            elif defect == 'malformed-id': result['results'][0]['id'] = {}
            else: meta['windows_inventory_scenarios'] = False
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                pipeline.validate_reports(meta, [result], 'commit', 'source')

    def test_candidate_never_replaces_verified_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verified = root / 'build/ArcaneVaults-NG.zip'
            verified.parent.mkdir()
            verified.write_bytes(b'previous')
            def check(_suites, output, **kwargs):
                self.assertEqual(kwargs['names'], ['wine-toolchain'])
                output.mkdir(parents=True)
                report = self.check_report({'wine-toolchain'})
                (output / 'report.json').write_text(json.dumps(report))
                return report
            def assemble(_container, _output, history):
                history.mkdir(parents=True)
                archive = history / 'ArcaneVaults-NG.zip'
                archive.write_bytes(b'candidate')
                return {'candidate': str(archive), 'windows_inventory_scenarios': True}
            with patch.object(pipeline, 'ROOT', root), patch.object(pipeline, 'fingerprint', return_value='source'), \
                 patch.object(pipeline.subprocess, 'check_output', return_value='commit\n'), \
                 patch.object(pipeline, 'release_id', return_value='run'), \
                 patch.object(pipeline, 'run_suites', side_effect=check), \
                 patch.object(pipeline, 'assemble', side_effect=assemble), patch.object(pipeline, 'promote') as promote:
                pipeline.candidate('test-wine')
            promote.assert_not_called()
            self.assertEqual(verified.read_bytes(), b'previous')
            bundle = root / '.build/ci/candidate'
            self.assertEqual((bundle / 'ArcaneVaults-NG.zip').read_bytes(), b'candidate')
            self.assertIs(json.loads((bundle / 'candidate.json').read_text())['passed'], False)

    def test_publication_preserves_previous_zip_until_all_gates_pass(self):
        for defect in ('none', 'missing', 'checksum', 'packaging', 'source'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bundle = root / '.build/ci/candidate'
                bundle.mkdir(parents=True)
                archive = bundle / 'ArcaneVaults-NG.zip'
                payload = {'SKSE/Plugins/ArcaneVaults-NG.dll': b'candidate', 'Scripts/ArcaneVaults.pex': b'script'}
                with zipfile.ZipFile(archive, 'w') as package:
                    for name, data in payload.items(): package.writestr(name, data)
                candidate_bytes = archive.read_bytes()
                meta = {**self.candidate_report(), 'checks': {'files': 1},
                        'zip_sha256': hashlib.sha256(candidate_bytes).hexdigest()}
                (bundle / 'candidate.json').write_text(json.dumps(meta))
                (bundle / 'toolchain.json').write_text(json.dumps(self.check_report({'wine-toolchain'})))
                checks = root / 'results/ci/checks/unit'
                checks.mkdir(parents=True)
                if defect != 'missing': (checks / 'report.json').write_text(json.dumps(self.check_report({'unit'})))
                verified = root / 'build/ArcaneVaults-NG.zip'
                verified.parent.mkdir()
                verified.write_bytes(b'previous')
                if defect == 'checksum': archive.write_bytes(b'changed')
                with patch.object(pipeline, 'ROOT', root), \
                     patch.object(pipeline, 'fingerprint', side_effect=['source', 'changed' if defect == 'source' else 'source']), \
                     patch.object(pipeline.subprocess, 'check_output', return_value='commit\n'), \
                     patch.object(pipeline, 'release_id', return_value='run'), \
                     patch.object(pipeline, 'required_checks', return_value={'unit', 'wine-toolchain'}), \
                     patch.object(pipeline, 'validate_zip', return_value={'files': 1}), \
                     patch.object(pipeline, 'run_suites', return_value={'passed': defect != 'packaging'}):
                    if defect == 'none': pipeline.publish()
                    else:
                        with self.assertRaises(ValueError): pipeline.publish()
                self.assertEqual(verified.read_bytes(), candidate_bytes if defect == 'none' else b'previous')
                install = root / '.build/ci/install'
                files = {p.relative_to(install).as_posix(): p.read_bytes() for p in install.rglob('*') if p.is_file()}
                self.assertEqual(files, payload if defect == 'none' else {})

    def test_cleanup_requires_uploaded_install_and_deletes_only_current_handoffs(self):
        env = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123',
               'GITHUB_SHA': 'commit', 'AV_INSTALL_ARTIFACT_ID': '3'}
        artifacts = [{'id': 1, 'name': 'candidate-commit', 'expired': False},
                     {'id': 2, 'name': 'check-commit-unit', 'expired': False},
                     {'id': 3, 'name': 'ArcaneVaults-NG-commit-2', 'expired': False},
                     {'id': 4, 'name': 'candidate-another-commit', 'expired': False},
                     {'id': 5, 'name': 'check-commit-unknown', 'expired': False},
                     {'id': 6, 'name': 'ArcaneVaults-NG-commit-1', 'expired': False}]
        for defect in ('none', 'missing-install', 'expired', 'wrong-name', 'previous-attempt', 'partial', 'empty'):
            rows = copy.deepcopy(artifacts)
            if defect == 'missing-install': rows.pop(2)
            elif defect == 'expired': rows[2]['expired'] = True
            elif defect == 'wrong-name': rows[2]['name'] = 'ArcaneVaults-NG-another-commit-2'
            elif defect == 'previous-attempt':
                rows[2]['name'] = 'ArcaneVaults-NG-commit-1'
                rows.pop(5)
            elif defect == 'partial': rows = rows[1:]
            elif defect == 'empty': rows = rows[2:]
            with self.subTest(defect=defect), patch.dict('os.environ', env), \
                 patch.object(pipeline, 'required_checks', return_value={'unit', 'wine-toolchain'}), \
                 patch.object(pipeline.subprocess, 'check_output', return_value='\n'.join(map(json.dumps, rows))) as listing, \
                 patch.object(pipeline.subprocess, 'run') as delete, contextlib.redirect_stdout(io.StringIO()) as output:
                if defect in ('missing-install', 'expired', 'wrong-name'):
                    with self.assertRaises(ValueError): pipeline.cleanup()
                    delete.assert_not_called()
                else:
                    pipeline.cleanup()
                    expected = [1, 2] if defect in ('none', 'previous-attempt') else [2] if defect == 'partial' else []
                    self.assertEqual([call.args[0] for call in delete.call_args_list], [
                        ['gh', 'api', '--method', 'DELETE', f'repos/owner/repo/actions/artifacts/{identity}']
                        for identity in expected])
                    self.assertTrue(all(call.kwargs['check'] for call in delete.call_args_list))
                    self.assertIn('Keeping ArcaneVaults-NG-commit-', output.getvalue())
                    self.assertNotIn('candidate-another-commit', output.getvalue())
                command = listing.call_args.args[0]
                self.assertIn('--paginate', command)
                self.assertIn('repos/owner/repo/actions/runs/123/artifacts?per_page=100', command)

    def test_cleanup_propagates_delete_errors_for_retry(self):
        env = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '123',
               'GITHUB_SHA': 'commit', 'AV_INSTALL_ARTIFACT_ID': '2'}
        rows = [{'id': 1, 'name': 'candidate-commit', 'expired': False},
                {'id': 2, 'name': 'ArcaneVaults-NG-commit-1', 'expired': False}]
        with patch.dict('os.environ', env), \
             patch.object(pipeline.subprocess, 'check_output', return_value='\n'.join(map(json.dumps, rows))), \
             patch.object(pipeline.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'gh')):
            with self.assertRaises(subprocess.CalledProcessError): pipeline.cleanup()

    def test_local_release_keeps_full_source_and_package_gates(self):
        import build_release as builder
        for defect in ('none', 'source', 'packaging', 'changed'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                verified = root / 'build/ArcaneVaults-NG.zip'
                verified.parent.mkdir()
                verified.write_bytes(b'previous')
                calls = []
                def suites(names, output, **kwargs):
                    calls.append(names)
                    return {'passed': defect != ('source' if names == ['release'] else 'packaging'),
                            'commit': 'commit', 'dirty': False}
                def assemble(_container, _output, history):
                    history.mkdir(parents=True)
                    archive = history / 'ArcaneVaults-NG.zip'
                    archive.write_bytes(b'candidate')
                    return {'candidate': str(archive), 'zip_sha256': hashlib.sha256(b'candidate').hexdigest(),
                            'checks': {'files': 1, 'esp_records': 1}}
                with patch.object(builder, 'ROOT', root), patch.object(builder, 'release_id', return_value='run'), \
                     patch('run.fingerprint', side_effect=['source', 'changed' if defect == 'changed' else 'source']), \
                     patch('run.run', side_effect=suites), patch.object(builder, 'assemble', side_effect=assemble) as built, \
                     patch.object(builder, 'validate_zip', return_value={}):
                    if defect == 'none': builder.build('test-wine')
                    else:
                        with self.assertRaises(ValueError): builder.build('test-wine')
                    if defect == 'source': built.assert_not_called()
                self.assertEqual(calls, [['release']] if defect == 'source' else [['release'], ['packaging']])
                self.assertEqual(verified.read_bytes(), b'candidate' if defect == 'none' else b'previous')
