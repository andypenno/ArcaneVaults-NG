"""Read the Skyrim PEX format and remove compiler machine metadata."""

import io
import struct

ARG_COUNTS = (0, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 3, 3, 3,
              3, 3, 1, 2, 2, 3, 2, 3, 1, 3, 3, 3, 2, 2, 3, 3, 4, 4)


def inspect_pex(data, allow_caprica_size=False):
    stream = io.BytesIO(data)

    def read(fmt):
        size = struct.calcsize(">" + fmt)
        raw = stream.read(size)
        if len(raw) != size:
            raise ValueError("Truncated PEX")
        return struct.unpack(">" + fmt, raw)[0]

    def string():
        size = read("H")
        raw = stream.read(size)
        if len(raw) != size:
            raise ValueError("Truncated PEX string")
        return raw.decode("utf-8")

    if read("I") != 0xFA57C0DE or (read("B"), read("B"), read("H")) != (3, 2, 1):
        raise ValueError("Expected Skyrim PEX 3.2, game ID 1")
    timestamp = read("Q")
    metadata = [string() for _ in range(3)]
    header_end = stream.tell()
    strings = [string() for _ in range(read("H"))]

    def reference():
        return strings[read("H")]

    def value():
        kind = read("B")
        if kind == 0:
            return None
        if kind in (1, 2):
            return reference()
        if kind == 3:
            return read("i")
        if kind == 4:
            return read("f")
        if kind == 5:
            return bool(read("B"))
        raise ValueError(f"Unsupported PEX value type {kind}")

    debug = read("B")
    if debug == 1:
        read("Q")
        for _ in range(read("H")):
            reference(), reference(), reference(), read("B")
            for _ in range(read("H")):
                read("H")
    elif debug != 0:
        raise ValueError("Invalid PEX debug-info marker")
    for _ in range(read("H")):
        reference(), read("B")

    def function():
        result = {"return": reference(), "doc": reference(), "user_flags": read("I"), "flags": read("B")}
        result["parameters"] = [(reference(), reference()) for _ in range(read("H"))]
        result["locals"] = [(reference(), reference()) for _ in range(read("H"))]
        code = []
        for _ in range(read("H")):
            opcode = read("B")
            if opcode >= len(ARG_COUNTS):
                raise ValueError(f"Invalid Skyrim opcode {opcode}")
            operands = [value() for _ in range(ARG_COUNTS[opcode])]
            if opcode in (23, 24, 25):
                count = value()
                if type(count) is not int or count < 0:
                    raise ValueError("Invalid PEX call argument count")
                operands.extend(value() for _ in range(count))
            code.append((opcode, operands))
        result["code"] = code
        return result

    objects = {}
    size_fields = []
    for _ in range(read("H")):
        name = reference()
        size_position = stream.tell()
        size = read("I")
        obj = {"parent": reference(), "doc": reference(), "user_flags": read("I"), "state": reference()}
        obj["variables"] = {}
        for _ in range(read("H")):
            variable = reference()
            obj["variables"][variable] = {"type": reference(), "flags": read("I"), "value": value()}
        obj["properties"] = {}
        for _ in range(read("H")):
            prop_name = reference()
            prop = {"type": reference(), "doc": reference(), "user_flags": read("I"), "flags": read("B")}
            if prop["flags"] & 4:
                prop["auto_variable"] = reference()
            else:
                if prop["flags"] & 1:
                    prop["read"] = function()
                if prop["flags"] & 2:
                    prop["write"] = function()
            obj["properties"][prop_name] = prop
        obj["states"] = {}
        for _ in range(read("H")):
            state = reference()
            functions = {}
            for _ in range(read("H")):
                function_name = reference()
                functions[function_name] = function()
            obj["states"][state] = functions
        actual_size = stream.tell() - size_position
        if size != actual_size:
            reversed_size = struct.unpack("<I", struct.pack(">I", size))[0]
            if not allow_caprica_size or reversed_size != actual_size - 4:
                raise ValueError(f"PEX object size mismatch: header {size}, payload {actual_size}")
        size_fields.append((size_position, actual_size))
        objects[name] = obj
    if stream.tell() != len(data):
        raise ValueError("Unexpected PEX trailing data")
    return {"timestamp": timestamp, "metadata": metadata, "header_end": header_end,
            "debug": debug, "objects": objects, "size_fields": size_fields}


def normalize_pex(data, source_name):
    info = inspect_pex(data, allow_caprica_size=True)
    if info["debug"]:
        raise ValueError("Compile with debug info disabled before normalizing PEX")
    header = data[:8] + struct.pack(">Q", 315532800)
    for text in (source_name, "", ""):
        value = text.encode("utf-8")
        header += struct.pack(">H", len(value)) + value
    payload = bytearray(data)
    for position, size in info["size_fields"]:
        struct.pack_into(">I", payload, position, size)
    return header + payload[info["header_end"]:]
