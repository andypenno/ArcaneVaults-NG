"""Compile the complete production InventoryStacks translation unit against shared boundaries."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from support.engine import ROOT
from support.scenarios import scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    cases = [scenario(p.read_text()) for p in sorted((ROOT / 'tests/fixtures/inventories').glob('*.json'))]
    if not cases:
        raise ValueError('No inventory scenarios found')
    with tempfile.TemporaryDirectory(prefix='av-inventories-') as directory:
        root = Path(directory)
        (root / 'common.hpp').write_text((ROOT / 'tests/support/engine.hpp').read_text())
        flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
        subprocess.run(['g++', '-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', *flags, '-I', str(root), '-I', str(ROOT),
                        '-include', str(root / 'common.hpp'), str(ROOT / 'src/InventoryStacks.cpp'),
                        str(ROOT / 'tests/integration/inventory.cpp'), '-o', str(root / 'inventory')], check=True, timeout=90)
        for case in cases:
            path = root / 'scenario.json'
            path.write_text(json.dumps(case))
            subprocess.run([str(root / 'inventory'), str(path)], check=True, timeout=15)


if __name__ == '__main__':
    main()
