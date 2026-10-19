import os
from pathlib import Path
import subprocess
import tempfile

os.environ.update(WINEPREFIX="/work/wine", WINEDEBUG="-all", WINEDLLOVERRIDES="d3dcompiler_47=n")
with tempfile.TemporaryDirectory(dir="/work") as temporary:
    directory = Path(temporary)
    source = directory / "check.hlsl"
    batch = directory / "check.cmd"
    command = (
        '"Z:/work/msvc/kits/10/bin/10.0.26100.0/x64/fxc.exe" '
        f'"Z:{source}" /nologo /Tps_4_0 /Emain /Fo"Z:{directory}/check.bin"'
    )
    batch.write_text(
        "@echo off\nset error=0\nset fxc=" + command +
        "\n%fxc%\nif errorlevel 1 set error=1\nexit /b %error%\n"
    )
    for text, expected in [("float4 main() : SV_TARGET { return 0; }", 0), ("invalid shader", 1)]:
        source.write_text(text)
        result = subprocess.run(
            ["/work/wine-bin/wine", "cmd", "/c", f"Z:{batch}"],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == expected, (expected, result.returncode, result.stdout, result.stderr)
        print(f"Shader error check returned {result.returncode}, expected {expected}")
