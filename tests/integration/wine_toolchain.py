"""Check the pinned Wine shader compiler's success and failure exit statuses."""
import json
import os
from pathlib import Path
import subprocess
from support.data import ROOT

container = os.environ.get('AV_WINE_CONTAINER', 'arcanevault-wine-build')
info = json.loads(subprocess.check_output(['podman', 'inspect', container], text=True))[0]
mounts = {item['Destination']: Path(item['Source']).resolve() for item in info['Mounts']}
if mounts.get('/repo') != ROOT or '/work' not in mounts:
    raise SystemExit('Wine container must mount this repository at /repo and its tools at /work')
if not info['State']['Running']:
    subprocess.run(['podman', 'start', container], check=True)
subprocess.run(['podman', 'exec', container, 'python3', '/repo/tests/integration/shaders.py'], check=True, timeout=90)
