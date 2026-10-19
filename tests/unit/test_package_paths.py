import tempfile
import unittest
from pathlib import Path
import warnings
import zipfile
from support.data import ROOT, load_json, validate_static
from validate import validate_zip


class PackagePathsTests(unittest.TestCase):
    def test_unsafe_and_colliding_paths(self):
        for paths in [['../escape'], ['/absolute'], ['Data\\bad'], ['C:bad'], ['a//b'], ['a/./b'], ['same', 'same'], ['Same', 'same']]:
            with self.subTest(paths=paths), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.zip'
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    with zipfile.ZipFile(path, 'w') as archive:
                        for name in paths:
                            archive.writestr(name, b'content')
                with self.assertRaises(ValueError):
                    validate_zip(ROOT, path)

    def test_stale_installer_bytes(self):
        manifest = load_json((ROOT / 'release/inputs.json').read_text())
        files = {name: (ROOT / source).read_bytes() for name, source in manifest['copies'].items()}
        self.assertGreater(validate_static(files)['translations'], 0)
        for name in [n for n in files if n.endswith(('.json', '.ini'))]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_static({**files, name: files[name] + b' '})
