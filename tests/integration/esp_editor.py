"""Build the pinned ESP editor and verify independent binary edits on both definitions."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from esp import generate_esp
from support.data import ROOT, load_json

dotnet = os.environ.get('AV_DOTNET') or shutil.which('dotnet')
if not dotnet:
    dotnet = str(Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'arcanevault-esp-tools/dotnet/dotnet')
if not Path(dotnet).is_file():
    raise SystemExit('Install the documented .NET 10 SDK or set AV_DOTNET')
environment = {**os.environ, 'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1'}
project = ROOT / 'tools/esp/ArcaneVaults.Esp.csproj'
output = ROOT / '.build/esp'
subprocess.run([dotnet, 'build', str(project), '--configuration', 'Release', '-o', str(output),
                f'-p:BaseIntermediateOutputPath={ROOT / ".build/esp-obj"}/', '-p:RestoreLockedMode=true'],
               env=environment, check=True, timeout=180)
for definition in ('release/upstream/esp.json', 'release/ArcaneVaults-LinkedStorage.json'):
    with tempfile.TemporaryDirectory(prefix='av-esp-editor-') as directory:
        path = Path(directory) / 'ArcaneVaults-LinkedStorage.esp'
        path.write_bytes(generate_esp(load_json((ROOT / definition).read_text())))
        subprocess.run([sys.executable, str(ROOT / 'tests/packaging/esp_editor_check.py'), dotnet,
                        str(output / 'ArcaneVaults.Esp.dll'), str(path)], env=environment, check=True, timeout=60)
