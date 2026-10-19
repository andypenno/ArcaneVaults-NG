"""Check production category and destination declarations without an engine fake."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='av-categories-') as directory:
    binary = Path(directory) / 'categories'
    cpp = Path(directory) / 'categories.cpp'
    source = (ROOT / 'src/ItemClass.cpp').read_text()
    methods = source[source.index('CategoryMask ToMask('):source.index('namespace {')]
    cpp.write_text('#include <algorithm>\n#include <ranges>\nnamespace logger {template<class... T> void warn(const char*,T...) {}}\n' +
                   (ROOT / 'tests/unit/categories.cpp').read_text() + '\n' + methods)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT),
                    str(cpp), '-o', str(binary)], check=True, timeout=60)
    subprocess.run([str(binary)], check=True, timeout=10)
print('PASS: unique production categories and every destination translation key')
