"""Exercise owned inspection preview callbacks and rendering through production hooks."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sanitize', action='store_true')
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='av-preview-') as directory:
    binary = str(Path(directory) / 'preview')
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, '-I', str(ROOT),
                    str(ROOT / 'tests/support/inventory_preview.cpp'), '-o', binary], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=15)
print('Preview ownership, request suppression, rendering and restoration checks passed')
