"""Strict readers for committed test and installer data."""
import configparser
import json
import math
import re
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(text):
    def invalid(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f'Non-finite JSON number: {value}')
        return parsed
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid, parse_float=number)


def translations(text, required=(), signatures=None):
    if any(not line.strip() for line in text.splitlines()):
        raise ValueError("Translations contain a blank line")
    values = load_json(text)
    if not isinstance(values, dict) or not values:
        raise ValueError("Translations must be a nonempty object")
    for key, value in values.items():
        if not key.strip() or not isinstance(value, str) or not value.strip():
            raise ValueError(f"Empty or invalid translation: {key}")
        fields = [field for _, field, _, _ in string.Formatter().parse(value) if field is not None]
        if signatures is not None and sorted(fields) != sorted(signatures.get(key, [])):
            raise ValueError(f"Translation placeholders differ: {key}")
    missing = set(required) - values.keys()
    if missing:
        raise ValueError(f"Missing translations: {sorted(missing)}")
    return values


def overrides(text, categories):
    parser = configparser.ConfigParser(interpolation=None, strict=True, delimiters=('=',))
    parser.optionxform = str
    parser.read_string(text)
    if parser.defaults() or parser.sections() != ['Overrides']:
        raise ValueError("Expected only the Overrides section")
    result = {}
    for key, value in parser['Overrides'].items():
        match = re.fullmatch(r'([^|\s]+\.(?:esm|esp|esl))\|0x([0-9a-f]{1,6})', key, re.I)
        if not match or not int(match[2], 16):
            raise ValueError(f"Invalid plugin/local form: {key}")
        identity = (match[1].casefold(), int(match[2], 16))
        names = [part.strip() for part in value.split(',')]
        if identity in result or not all(name in categories for name in names) or len(set(names)) != len(names):
            raise ValueError(f"Duplicate override or invalid categories: {key} = {value}")
        result[identity] = names
    return result


def validate_static(files=None, root=ROOT):
    manifest = load_json((root / 'release/inputs.json').read_text())
    def read(source):
        if files is None:
            return (root / source).read_text()
        target = next(name for name, path in manifest['copies'].items() if path == source)
        expected = (root / source).read_bytes()
        if files[target] != expected:
            raise ValueError(f"Packaged source differs: {target}")
        return files[target].decode('utf-8')
    contract = load_json((root / 'tests/fixtures/translations.json').read_text())
    sources = '\n'.join(p.read_text() for p in (root / 'src').glob('*') if p.suffix in ('.h', '.cpp'))
    required = {key for call in re.findall(r'\bTranslate\(([^;]*?)\)', sources) for key in re.findall(r'"([^"]+)"', call) if not key.endswith('.')}
    required.update(re.findall(r'case Container::\w+:\s*return "([^"]+)"', sources))
    values = translations(read('ini/ArcaneVaultTranslation.json'), required, contract['placeholders'])
    unused = set(values) - set(re.findall(r'"([^"\n]+)"', sources)) - contract['retained'].keys()
    if unused:
        raise ValueError(f"Unused translations without a retained-key reason: {sorted(unused)}")
    if any(not reason.strip() for reason in contract['retained'].values()):
        raise ValueError("Retained keys require reasons")
    categories = set(re.findall(r'\{\s*"(\w+)"\s*,\s*ItemCategory::', (root / 'src/ItemClass.h').read_text()))
    overrides(read('ini/ArcaneVaultOverrides.ini'), categories)
    return {'translations': len(values), 'categories': len(categories)}
