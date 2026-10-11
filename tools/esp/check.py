#!/usr/bin/env python3
"""Exercise the ESP tool against an external plugin without changing that input."""

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib


def records(data):
    result = {}
    groups = []

    def scan(start, end, parents=()):
        while start < end:
            assert start + 24 <= end, "Truncated header"
            header = data[start:start + 24]
            tag, size = struct.unpack_from("<4sI", header)
            if tag == b"GRUP":
                assert size >= 24 and start + size <= end, "Invalid group size"
                group = header[8:]
                groups.append((parents, group))
                scan(start + 24, start + size, parents + (group,))
                start += size
                continue
            assert start + 24 + size <= end, "Truncated record"
            payload = data[start + 24:start + 24 + size]
            if struct.unpack_from("<I", header, 8)[0] & 0x40000:
                expected_size = struct.unpack_from("<I", payload)[0]
                payload = zlib.decompress(payload[4:])
                assert len(payload) == expected_size, "Invalid compressed record"
            key = (tag, struct.unpack_from("<I", header, 12)[0])
            assert key not in result, "Duplicate form ID"
            result[key] = (header[8:], payload, parents)
            start += 24 + size
        assert start == end

    scan(0, len(data))
    return result, groups


def rename_payload(payload, name):
    output = bytearray()
    offset = 0
    found = 0
    while offset < len(payload):
        tag, size = struct.unpack_from("<4sH", payload, offset)
        value = payload[offset + 6:offset + 6 + size]
        assert len(value) == size, "Truncated subrecord"
        if tag == b"FULL":
            value = name.encode("cp1252") + b"\0"
            found += 1
        output.extend(struct.pack("<4sH", tag, len(value)) + value)
        offset += 6 + size
    assert found == 1, "Expected one embedded container name"
    return bytes(output)


if len(sys.argv) != 3:
    raise SystemExit("Usage: python3 tools/esp/check.py DOTNET INPUT_ESP")
dotnet, input_path = sys.argv[1], Path(sys.argv[2]).resolve()
dll = Path(__file__).parent / "bin/Release/net10.0/ArcaneVaults.Esp.dll"
original = input_path.read_bytes()


def run(*args, success=True):
    result = subprocess.run([dotnet, str(dll), *map(str, args)], capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stdout + result.stderr
    return result.stdout


before = json.loads(run("inspect", input_path))
target = before["containers"][0]
name = "ESP code check"
with tempfile.TemporaryDirectory(prefix="arcanevault-esp-check-") as temporary:
    output = Path(temporary) / input_path.name
    run("rename-container", input_path, output, target["id"], name)
    after = json.loads(run("inspect", output))
    expected = json.loads(json.dumps(before))
    expected["containers"][0]["name"] = name
    assert after == expected, "Reopened plugin differs beyond the chosen label"

    source_records, source_groups = records(original)
    output_records, output_groups = records(output.read_bytes())
    keys = [key for key in source_records if key[0] == b"CONT" and key[1] & 0xFFFFFF == int(target["id"], 16)]
    assert len(keys) == 1
    key = keys[0]
    header, payload, parents = source_records[key]
    source_records[key] = (header, rename_payload(payload, name), parents)
    assert output_records == source_records, "Unintended record change"
    assert output_groups == source_groups, "Group metadata or placement changed"

    saved = output.read_bytes()
    run("rename-container", input_path, output, target["id"], "Overwrite", success=False)
    assert output.read_bytes() == saved, "Existing output was overwritten"
    run("rename-container", input_path, input_path, target["id"], "In place", success=False)
    fresh = Path(temporary) / "fresh" / input_path.name
    for bad_id, bad_name in [("GG", name), ("1000000", name), ("FFFFFF", name), (target["id"], " ")]:
        run("rename-container", input_path, fresh, bad_id, bad_name, success=False)
        assert not fresh.exists(), "Rejected edit created output"
    run("rename-container", input_path, Path(temporary) / "Wrong.esp", target["id"], name, success=False)
    run("rename-container", input_path, success=False)
    run("unknown", input_path, success=False)

assert input_path.read_bytes() == original, "Source plugin changed"
print(f"PASS: edited and reopened {len(output_records)} records; only CONT {target['id']} FULL changed; input and overwrite guards preserved")
