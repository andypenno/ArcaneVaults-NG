"""Check source round-trips, compiler corrections, and the assembled archive."""

import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import zipfile

from build_release import write_zip
from esp import generate_esp, import_esp, walk
from pex import inspect_pex, normalize_pex
from validate import validate_esp, validate_files, validate_zip

ROOT = Path(__file__).resolve().parents[2]
baseline = json.loads((ROOT / "release/upstream/esp.json").read_text())
provenance = json.loads((ROOT / "release/upstream/release.json").read_text())
data = generate_esp(baseline)
assert hashlib.sha256(data).hexdigest() == provenance["files"]["ArcaneVaults-LinkedStorage.esp"]
assert import_esp(data) == baseline
assert len(list(walk(baseline["records"]))) == 70

working = json.loads((ROOT / "release/ArcaneVaults-LinkedStorage.json").read_text())
assert validate_esp(ROOT, generate_esp(working)) == len(list(walk(working["records"])))

changed = copy.deepcopy(baseline)
container = next(node for node in walk(changed["records"]) if node["type"] == "CONT")
name = next(field for field in container["fields"] if field["type"] == "FULL")
name["text"] = "Generated label check"
round_trip = import_esp(generate_esp(changed))
assert next(field["text"] for node in walk(round_trip["records"]) if node["form_id"] == container["form_id"]
            for field in node["fields"] if field["type"] == "FULL") == name["text"]
cell = next(node for node in walk(changed["records"]) if node["type"] == "CELL")
assert cell["flags"] & 0x40000
next(field for field in cell["fields"] if field["type"] == "EDID")["text"] = "ChangedCell"
compressed_round_trip = import_esp(generate_esp(changed))
assert next(field["text"] for node in walk(compressed_round_trip["records"]) if node["type"] == "CELL"
            for field in node["fields"] if field["type"] == "EDID") == "ChangedCell"


def fails(operation):
    try:
        operation()
    except (ValueError, KeyError, struct.error, IndexError):
        return
    raise AssertionError("Invalid input was accepted")


fails(lambda: import_esp(data[:-1]))
fails(lambda: import_esp(b""))
duplicate = copy.deepcopy(baseline)
duplicate["records"].append(copy.deepcopy(next(walk(duplicate["records"]))))
fails(lambda: generate_esp(duplicate))
temporary_storage = copy.deepcopy(working)
reference = next(node for node in walk(temporary_storage["records"]) if node["form_id"] == "0x01000DC5")
reference["flags"] &= ~0x400
fails(lambda: validate_esp(ROOT, generate_esp(temporary_storage)))
respawning_storage = copy.deepcopy(working)
base = next(node for node in walk(respawning_storage["records"]) if node["form_id"] == "0x01000DC4")
next(field for field in base["fields"] if field["type"] == "DATA")["hex"] = "0200000000"
fails(lambda: validate_esp(ROOT, generate_esp(respawning_storage)))
archive = ROOT / "build/releases/ArcaneVaults-NG.zip"
checks = validate_zip(ROOT, archive)
with zipfile.ZipFile(archive) as zipped:
    files = {name: zipped.read(name) for name in zipped.namelist()}
    entries = zipped.infolist()
assert len(files) == 10 and [entry.filename for entry in entries] == sorted(files)
assert all(entry.date_time == (1980, 1, 1, 0, 0, 0) and entry.external_attr == 0o100644 << 16 for entry in entries)
assert files["ArcaneVaults-LinkedStorage.esp"] == generate_esp(json.loads((ROOT / "release/ArcaneVaults-LinkedStorage.json").read_text()))
for name, source in json.loads((ROOT / "release/inputs.json").read_text())["copies"].items():
    assert files[name] == (ROOT / source).read_bytes()
for name in ["ArcaneVaults", "ArcaneSpells"]:
    compiled = files[f"Scripts/{name}.pex"]
    info = inspect_pex(compiled)
    assert info["metadata"] == [name + ".psc", "", ""] and info["timestamp"] == 315532800
    assert normalize_pex(compiled, name + ".psc") == compiled
    broken = bytearray(compiled)
    for position, size in info["size_fields"]:
        struct.pack_into("<I", broken, position, size - 4)
    fails(lambda: inspect_pex(broken))
    assert normalize_pex(broken, name + ".psc") == compiled

missing = files.copy()
del missing["Scripts/ArcaneSpells.pex"]
fails(lambda: validate_files(ROOT, missing))
extra = {**files, "Scripts/Actor.pex": b"compile-only imports must not ship"}
fails(lambda: validate_files(ROOT, extra))
with tempfile.TemporaryDirectory(prefix="arcanevault-release-check-") as temporary:
    one, two = Path(temporary) / "one.zip", Path(temporary) / "two.zip"
    write_zip(one, files)
    write_zip(two, dict(reversed(list(files.items()))))
    assert one.read_bytes() == two.read_bytes() == archive.read_bytes()
    assert validate_zip(ROOT, one) == checks
print("PASS: baseline SHA/record round-trip, editable/compressed records, PEX correction and dispatch, exact 10-path ZIP, deterministic archive bytes, missing/extra rejection")
