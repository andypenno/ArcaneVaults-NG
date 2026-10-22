"""Expand representative inventories without computing their expected sorting decisions."""
import re
import math
from pathlib import Path
from support.data import ROOT, load_json


def enum_names(name):
    text = (ROOT / 'src/ItemClass.h').read_text()
    return re.findall(r'\b(\w+)\s*,?', text.split('enum class ' + name + ' :')[1].split('{', 1)[1].split('}', 1)[0])


def catalog():
    values = load_json((ROOT / 'tests/fixtures/sorting/catalog.json').read_text())
    categories, containers = set(enum_names('ItemCategory')), set(enum_names('Container'))
    for key, item in values.items():
        if set(item) != {'name', 'kind', 'categories', 'vaults'} or not item['name'] or item['kind'] not in ('item', 'weapon', 'armor', 'soulgem'):
            raise ValueError(f'Invalid catalog item: {key}')
        if not item['categories'] or set(item['categories']) - categories or set(item['vaults']) - containers:
            raise ValueError(f'Unknown catalog classification: {key}')
    return values


def scenario(path):
    data = load_json(Path(path).read_text())
    if set(data) != {'version', 'name', 'description', 'settings', 'inventories', 'no_transfers'} or data['version'] != 1:
        raise ValueError('Invalid sorting scenario fields/version')
    if any(not isinstance(data[field], str) or not data[field].strip() for field in ('name', 'description')):
        raise ValueError('Sorting scenarios need a name and description')
    bases = catalog()
    containers = set(enum_names('Container')) - {'None', 'Master', 'QuickTransfer'}
    options = {name: kind for kind, name in re.findall(r'\b(bool|int)\s+(GSC_\w+)\s*\{', (ROOT / 'src/Settings.h').read_text())}
    for name, value in data['settings'].items():
        if name not in options or type(value) is not (bool if options[name] == 'bool' else int) or (type(value) is int and value < 0):
            raise ValueError('Invalid scenario setting')
    if type(data['no_transfers']) is not bool or 'player' not in data['inventories'] or set(data['inventories']) - (containers | {'player'}):
        raise ValueError('Invalid scenario inventories')
    rows, seen = [], set()
    for inventory, entries in data['inventories'].items():
        for row in entries:
            allowed = {'id', 'base', 'count', 'after', 'copies', 'favorite', 'worn', 'quest', 'ignored', 'name', 'enchantment', 'owner', 'charge', 'temper', 'soul'}
            if set(row) - allowed or not {'id', 'base', 'count', 'after'} <= row.keys() or row['base'] not in bases:
                raise ValueError('Invalid sorting row')
            if not isinstance(row['id'], str) or not row['id']:
                raise ValueError('Invalid physical identity')
            if type(row['count']) is not int or not 1 <= row['count'] <= 32767 or type(row.get('copies', 1)) is not int or not 1 <= row.get('copies', 1) <= 1000:
                raise ValueError('Invalid sorting quantity')
            if set(row['after']) - (containers | {'player'}) or any(type(n) is not int or n <= 0 for n in row['after'].values()) or sum(row['after'].values()) != row['count']:
                raise ValueError('Expected sorting state violates conservation')
            for field in ('favorite', 'worn', 'quest', 'ignored'):
                if field in row and type(row[field]) is not bool:
                    raise ValueError('Invalid protection flag')
            for field in ('charge', 'temper'):
                if field in row and (type(row[field]) not in (int, float) or not math.isfinite(row[field]) or row[field] < 0):
                    raise ValueError('Invalid numeric metadata')
            if 'soul' in row and (type(row['soul']) is not int or not 0 <= row['soul'] <= 5):
                raise ValueError('Invalid soul level')
            for field in ('name', 'enchantment', 'owner'):
                if field in row and (not isinstance(row[field], str) or not row[field]):
                    raise ValueError('Invalid metadata identity')
            for index in range(row.get('copies', 1)):
                identity = row['id'] + (f'-{index:04}' if 'copies' in row else '')
                if identity in seen:
                    raise ValueError('Duplicate physical identity')
                seen.add(identity)
                rows.append({**row, 'id': identity, 'inventory': inventory})
    if not rows or len(rows) > 10000:
        raise ValueError('Sorting scenario needs 1 to 10000 physical stacks')
    if data['no_transfers'] and any(row['after'] != {row['inventory']: row['count']} for row in rows):
        raise ValueError('No-transfer scenario expects moved items')
    return {**data, 'bases': bases, 'rows': rows}


def definitions():
    text = ''
    for enum in ('Container', 'ItemCategory'):
        pairs = ','.join('{"' + name + '",' + enum + '::' + name + '}' for name in enum_names(enum))
        text += 'const std::map<std::string,' + enum + '> ' + enum.lower() + 'Names{' + pairs + '};\n'
    settings = re.findall(r'\b(bool|int)\s+(GSC_\w+)\s*\{', (ROOT / 'src/Settings.h').read_text())
    text += 'void Configure(Settings* settings,const nlohmann::json& data){\n'
    for kind, name in settings:
        text += f'if(data.contains("{name}"))settings->{name}=data.at("{name}").get<{kind}>();\n'
    return text + '}\n'
