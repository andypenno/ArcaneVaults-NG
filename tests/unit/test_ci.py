import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from support.data import ROOT

spec = importlib.util.spec_from_file_location('bootstrap_wine', ROOT / 'tools/ci/bootstrap_wine.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


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
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
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
