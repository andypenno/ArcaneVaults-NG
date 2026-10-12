"""Validate the packaged records and compiled script contracts."""

import json
import hashlib
from pathlib import Path
import re
import struct
import zipfile

from esp import field_bytes, import_esp, walk
from pex import inspect_pex


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pe_exports(data):
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    require(struct.unpack_from("<H", data, offset + 24)[0] == 0x20B, "DLL is not PE32+")
    sections = struct.unpack_from("<H", data, offset + 6)[0]
    optional_size = struct.unpack_from("<H", data, offset + 20)[0]
    table = offset + 24 + optional_size

    def position(rva):
        for i in range(sections):
            virtual_size, virtual, raw_size, raw = struct.unpack_from("<IIII", data, table + i * 40 + 8)
            if virtual <= rva < virtual + max(virtual_size, raw_size):
                require(rva - virtual < raw_size, "Export RVA has no file data")
                return raw + rva - virtual
        raise ValueError("Export RVA is outside DLL sections")

    directory, size = struct.unpack_from("<II", data, offset + 24 + 112)
    require(directory and size >= 40, "DLL export directory is missing")
    entry = position(directory)
    count = struct.unpack_from("<I", data, entry + 24)[0]
    names = position(struct.unpack_from("<I", data, entry + 32)[0])
    result = set()
    for i in range(count):
        start = position(struct.unpack_from("<I", data, names + i * 4)[0])
        end = data.index(b"\0", start)
        result.add(data[start:end].decode("ascii"))
    return result


def effect_property(payload):
    offset = 6

    def string():
        nonlocal offset
        size = struct.unpack_from("<H", payload, offset)[0]
        offset += 2
        text = payload[offset:offset + size].decode("utf-8")
        offset += size
        return text

    require(struct.unpack_from("<HHH", payload) == (5, 2, 1), "Unexpected magic-effect VMAD header")
    script = string()
    flags, count = struct.unpack_from("<BH", payload, offset)
    offset += 3
    prop = string()
    kind, status, value = struct.unpack_from("<BBi", payload, offset)
    offset += 6
    require(script.lower() == "arcanespells" and count == 1 and prop == "SpellType"
            and kind == 3 and status == 1 and offset == len(payload), "Unexpected spell script property")
    return value


def validate_esp(root, data):
    source = import_esp(data)
    nodes = list(walk(source["records"]))
    by_id = {int(node["form_id"], 16): node for node in nodes}
    header = nodes[0]
    require(header["type"] == "TES4" and header["form_id"] == "0x00000000", "Missing ESP header")
    masters = [field["text"] for field in header["fields"] if field["type"] == "MAST"]
    require(masters == ["Skyrim.esm"], "Unexpected ESP masters")
    h = next(field_bytes(field) for field in header["fields"] if field["type"] == "HEDR")

    def group_count(items):
        return sum(1 + group_count(node["children"]) for node in items if node["type"] == "GRUP")

    _, count, next_id = struct.unpack("<fII", h)
    require(count == len(nodes) - 1 + group_count(source["records"]), "ESP header record/group count is stale")
    require(next_id > max(key & 0xFFFFFF for key in by_id), "ESP next form ID would collide")
    registry = (root / "src/Utility.cpp").read_text()
    registered = [int(value, 16) for value in re.findall(
        r"AddContainer\(dataHandler,\s*Container::\w+,\s*RE::FormID\((0x[0-9A-Fa-f]+)\)", registry)]
    references = [node for node in nodes if node["type"] == "REFR"]
    require(registered and len(set(registered)) == len(registered), "Duplicate or missing C++ container registry IDs")
    require({int(node["form_id"], 16) & 0xFFFFFF for node in references} == set(registered),
            "ESP storage references differ from the C++ registry")

    origin_keyword = by_id.get(0x01000DE0)
    require(origin_keyword is not None and origin_keyword["type"] == "KYWD" and
            any(field.get("text") == "AV_StolenOrigin" for field in origin_keyword["fields"] if field["type"] == "EDID"),
            "Stolen Items origin keyword is missing or invalid")

    def check_cells(items, cell=None):
        for node in items:
            if node["type"] == "GRUP":
                owner = cell
                if node["group_type"] == 6:
                    owner = struct.unpack("<I", bytes.fromhex(node["label_hex"]))[0]
                    require(owner in by_id and by_id[owner]["type"] == "CELL", "Reference group has no cell")
                check_cells(node["children"], owner)
            elif node["type"] == "REFR":
                require(cell is not None, "Storage reference is outside a cell group")

    check_cells(source["records"])
    for node in references:
        target = next(int(field["form_id"], 16) for field in node["fields"] if field["type"] == "NAME")
        require(target in by_id and by_id[target]["type"] == "CONT", "Storage reference has no container base")
        require(node["flags"] & 0x400, "Storage reference must be persistent")
        container_data = next(field_bytes(field) for field in by_id[target]["fields"] if field["type"] == "DATA")
        require(len(container_data) == 5 and not container_data[0] & 2, "Storage container must not respawn")
    for local_id, spell_type in [(0xDC0, 0), (0xDC1, 1)]:
        spell = by_id.get(0x01000000 | local_id)
        require(spell is not None and spell["type"] == "SPEL", "Required configuration spell is missing")
        effect_id = next(struct.unpack("<I", field_bytes(field))[0] for field in spell["fields"] if field["type"] == "EFID")
        effect = by_id[effect_id]
        require(effect["type"] == "MGEF", "Spell effect points at the wrong record type")
        vmad = next(field_bytes(field) for field in effect["fields"] if field["type"] == "VMAD")
        require(effect_property(vmad) == spell_type, "Spell dispatch property differs from its native action")
    return len(nodes)


def dispatch(code, variable, spell_type):
    values = {variable: spell_type}
    calls = []
    pc = 0
    for _ in range(100):
        if pc == len(code):
            return calls
        require(0 <= pc < len(code), "PEX branch leaves the function")
        opcode, args = code[pc]
        if opcode == 15:
            values[args[0]] = values[args[1]] == args[2]
        elif opcode == 22:
            if not values[args[0]]:
                pc += args[1]
                continue
        elif opcode == 20:
            pc += args[0]
            continue
        elif opcode == 25:
            require(args[0].lower() == "arcanevaults" and len(args) == 3, "Unexpected native dispatch")
            calls.append(args[1])
        elif opcode == 26:
            return calls
        else:
            raise ValueError(f"Spell dispatcher validation needs support for opcode {opcode}")
        pc += 1
    raise ValueError("Spell dispatcher did not terminate")


def validate_files(root, files):
    manifest = json.loads((root / "release/inputs.json").read_text())
    expected = set(manifest["copies"]) | set(manifest["generated"])
    require(set(files) == expected, f"Package paths differ: missing {sorted(expected - set(files))}, extra {sorted(set(files) - expected)}")
    require(all(files.values()), "Empty package file")
    count = validate_esp(root, files["ArcaneVaults-LinkedStorage.esp"])
    native = inspect_pex(files["Scripts/ArcaneVaults.pex"])["objects"]["ArcaneVaults"]
    require(native["parent"] == "", "Native bridge has an unexpected parent")
    registrations = re.findall(r'RegisterFunction\("(\w+)"', (root / "src/Papyrus.cpp").read_text())
    for name in registrations:
        function = native["states"][""][name]
        require(function["flags"] == 3 and not function["parameters"] and function["return"].lower() == "none",
                f"Compiled native signature differs from C++: {name}")
    spells = inspect_pex(files["Scripts/ArcaneSpells.pex"])["objects"]["ArcaneSpells"]
    require(spells["parent"].lower() == "activemagiceffect", "Spell script has the wrong parent")
    prop = spells["properties"]["SpellType"]
    require(prop["type"].lower() == "int" and prop["flags"] & 4, "SpellType is not an automatic integer property")
    function = spells["states"][""]["OnEffectStart"]
    require([kind.lower() for _, kind in function["parameters"]] == ["actor", "actor"], "Effect event parameters differ")
    for value, calls in [(0, ["ContainerRedirect"]), (1, ["OffloadItems"]), (2, [])]:
        require(dispatch(function["code"], prop["auto_variable"], value) == calls, "Compiled SpellType dispatch differs")
    dll = files["SKSE/Plugins/ArcaneVaults-NG.dll"]
    require(dll[:2] == b"MZ", "DLL is not a PE file")
    offset = struct.unpack_from("<I", dll, 0x3C)[0]
    require(dll[offset:offset + 4] == b"PE\0\0" and struct.unpack_from("<H", dll, offset + 4)[0] == 0x8664,
            "DLL is not Windows x64")
    require(struct.unpack_from("<H", dll, offset + 22)[0] & 0x2000, "PE file is not a DLL")
    require({"SKSEPlugin_Load", "SKSEPlugin_Query", "SKSEPlugin_Version"} <= pe_exports(dll),
            "Required SKSE exports are absent")
    json.loads(files["SKSE/Plugins/ArcaneVault/ArcaneVaultTranslation.json"])
    for name in ["UILIB_1_ListMenu.swf", "buttonArt.swf"]:
        require(files[f"Interface/uilib/{name}"][:3] in (b"FWS", b"CWS"), "Invalid SkyUILib movie")
        expected_hash = manifest["skyui_lib"]["files"][f"assets/skyui-lib/uilib/{name}"]
        require(hashlib.sha256(files[f"Interface/uilib/{name}"]).hexdigest() == expected_hash,
                "Packaged SkyUILib movie differs from its pinned hash")
    return {"files": len(files), "esp_records": count, "spell_dispatch": "0=assign, 1=offload, 2=no call"}


def validate_zip(root, path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate ZIP paths")
        require(archive.testzip() is None, "ZIP CRC check failed")
        files = {name: archive.read(name) for name in names}
    return validate_files(root, files)


if __name__ == "__main__":
    import sys
    print(json.dumps(validate_zip(Path(__file__).resolve().parents[2], Path(sys.argv[1])), indent=2))
