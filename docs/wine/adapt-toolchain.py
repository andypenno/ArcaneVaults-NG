from pathlib import Path

work = Path("/work")
wine = work / "wine-bin/wine"
wine.parent.mkdir(parents=True, exist_ok=True)
wine.write_text(
    '#!/usr/bin/python3\nimport os\nimport sys\n'
    'os.closerange(3, 65536)\n'
    'os.execv("/usr/lib/wine/wine64", ["wine64", *sys.argv[1:]])\n'
)
wine.chmod(0o755)
wine64 = wine.with_name("wine64")
if not wine64.is_symlink():
    assert not wine64.exists(), wine64
    wine64.symlink_to("wine")
assert wine64.resolve() == wine.resolve()

changes = [
    (
        work / "xmake-install/share/xmake/modules/detect/tools/find_rc.lua",
        'is_host("windows")',
        'is_host("windows", "linux")',
    ),
    (
        work / "msvc/bin/x64/cl.exe",
        '"$(dirname "$0")"/wine-msvc.sh "$BINDIR"/cl.exe "$@"',
        '"$(dirname "$0")"/wine-msvc.sh "$BINDIR"/cl.exe "$@" /cgthreads1',
    ),
]
for path, old, new in changes:
    source = path.read_text()
    if new not in source:
        assert source.count(old) == 1, path
        path.write_text(source.replace(old, new))
    assert path.read_text().count(new) == 1, path
print("Wine launcher, resource detector, and compiler-thread adapters verified")
