"""Import an upstream baseline without replacing local authored inputs."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from esp import import_esp

parser = argparse.ArgumentParser()
parser.add_argument("zip", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
if args.output.exists():
    raise SystemExit("Output directory already exists; use a new candidate directory")
with zipfile.ZipFile(args.zip) as archive:
    names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate ZIP paths")
    files = {name: archive.read(name) for name in names}
    source = import_esp(files["ArcaneVaults-LinkedStorage.esp"])
    scripts = {name: files[f"Scripts/Source/{name}"] for name in ["ArcaneVaults.psc", "ArcaneSpells.psc"]}
metadata = {"zip_sha256": hashlib.sha256(args.zip.read_bytes()).hexdigest(),
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
args.output.mkdir(parents=True)
(args.output / "esp.json").write_text(json.dumps(source, indent=2) + "\n")
(args.output / "release.json").write_text(json.dumps(metadata, indent=2) + "\n")
for name, data in scripts.items():
    (args.output / name).write_bytes(data)
print(f"Imported {len(names)} upstream paths; recovered ESP definition and two PSC sources")
