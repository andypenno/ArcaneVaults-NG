"""Lossless source representation of the companion Skyrim SE plugin."""

import argparse
import json
from pathlib import Path
import struct
import zlib

TEXT_FIELDS = {"EDID", "FULL", "DESC", "MODL", "MAST"}


def import_esp(data):
    if len(data) < 24 or data[:4] != b"TES4":
        raise ValueError("ESP must begin with a TES4 header")

    def read(start, end):
        nodes = []
        while start < end:
            if start + 24 > end:
                raise ValueError("Truncated ESP header")
            header = data[start:start + 24]
            tag, size = struct.unpack_from("<4sI", header)
            if tag == b"GRUP":
                if size < 24 or start + size > end:
                    raise ValueError("Invalid ESP group size")
                nodes.append({"type": "GRUP", "label_hex": header[8:12].hex(),
                              "group_type": struct.unpack_from("<i", header, 12)[0],
                              "stamp_hex": header[16:].hex(),
                              "children": read(start + 24, start + size)})
                start += size
                continue
            if start + 24 + size > end:
                raise ValueError("Truncated ESP record")
            flags, form_id, revision, version, unknown = struct.unpack_from("<IIIHH", header, 8)
            payload = data[start + 24:start + 24 + size]
            compressed = payload if flags & 0x40000 else None
            if compressed is not None:
                expected_size = struct.unpack_from("<I", payload)[0]
                payload = zlib.decompress(payload[4:])
                if len(payload) != expected_size:
                    raise ValueError("Invalid compressed ESP record size")
            fields = []
            offset = 0
            while offset < len(payload):
                if offset + 6 > len(payload):
                    raise ValueError("Truncated ESP subrecord header")
                field_tag, field_size = struct.unpack_from("<4sH", payload, offset)
                field_tag = field_tag.decode("ascii")
                if field_tag == "XXXX":
                    raise ValueError("Extended subrecords require explicit importer support")
                value = payload[offset + 6:offset + 6 + field_size]
                if len(value) != field_size:
                    raise ValueError("Truncated ESP subrecord")
                field = {"type": field_tag, "hex": value.hex()}
                if field_tag in TEXT_FIELDS and value.endswith(b"\0") and b"\0" not in value[:-1]:
                    try:
                        field = {"type": field_tag, "text": value[:-1].decode("cp1252")}
                    except UnicodeDecodeError:
                        pass
                if tag == b"REFR" and field_tag == "NAME" and len(value) == 4:
                    field = {"type": field_tag, "form_id": f"0x{struct.unpack('<I', value)[0]:08X}"}
                fields.append(field)
                offset += 6 + field_size
            node = {"type": tag.decode("ascii"), "flags": flags,
                    "form_id": f"0x{form_id:08X}", "revision": revision,
                    "version": version, "unknown": unknown, "fields": fields}
            if compressed is not None:
                node["compressed_hex"] = compressed.hex()
            nodes.append(node)
            start += 24 + size
        return nodes

    source = {"schema": 1, "records": read(0, len(data))}
    if generate_esp(source) != data:
        raise ValueError("ESP import did not preserve the original bytes")
    return source


def field_bytes(field):
    kinds = [key for key in ("text", "hex", "form_id") if key in field]
    if len(kinds) != 1:
        raise ValueError("Subrecord needs exactly one of text, hex, or form_id")
    if kinds[0] == "text":
        if "\0" in field["text"]:
            raise ValueError("Embedded NUL in ESP string")
        return field["text"].encode("cp1252") + b"\0"
    if kinds[0] == "form_id":
        return struct.pack("<I", int(field["form_id"], 16))
    return bytes.fromhex(field["hex"])


def walk(nodes):
    for node in nodes:
        if node["type"] == "GRUP":
            yield from walk(node["children"])
        else:
            yield node


def generate_esp(source):
    if source["schema"] != 1:
        raise ValueError("Unsupported ESP source schema")
    seen = set()

    def write(nodes):
        output = bytearray()
        for node in nodes:
            tag = node["type"].encode("ascii")
            if len(tag) != 4:
                raise ValueError("ESP signatures must contain four ASCII characters")
            if tag == b"GRUP":
                children = write(node["children"])
                label, stamp = bytes.fromhex(node["label_hex"]), bytes.fromhex(node["stamp_hex"])
                if len(label) != 4 or len(stamp) != 8:
                    raise ValueError("Invalid ESP group metadata")
                output.extend(struct.pack("<4sI4si", tag, len(children) + 24, label, node["group_type"]) + stamp + children)
                continue
            form_id = int(node["form_id"], 16)
            if form_id in seen:
                raise ValueError(f"Duplicate ESP form ID {node['form_id']}")
            seen.add(form_id)
            payload = bytearray()
            for field in node["fields"]:
                value = field_bytes(field)
                field_tag = field["type"].encode("ascii")
                if len(field_tag) != 4 or field_tag == b"XXXX":
                    raise ValueError("Invalid or unsupported subrecord signature")
                payload.extend(struct.pack("<4sH", field_tag, len(value)) + value)
            if node["flags"] & 0x40000:
                original = bytes.fromhex(node.get("compressed_hex", ""))
                if original and zlib.decompress(original[4:]) == payload:
                    if struct.unpack_from("<I", original)[0] != len(payload):
                        raise ValueError("Invalid original compressed ESP size")
                    payload = original
                else:
                    payload = struct.pack("<I", len(payload)) + zlib.compress(payload, level=9)
            output.extend(struct.pack("<4sIIIIHH", tag, len(payload), node["flags"], form_id,
                                      node["revision"], node["version"], node["unknown"]) + payload)
        return bytes(output)

    return write(source["records"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["import", "generate"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.operation == "import":
        result = (json.dumps(import_esp(args.input.read_bytes()), indent=2) + "\n").encode()
    else:
        result = generate_esp(json.loads(args.input.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(result)
