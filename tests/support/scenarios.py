"""Validate physical-instance fixtures before passing them to production C++ tests."""
from support.data import load_json
import math


def scenario(text):
    data = load_json(text)
    if not isinstance(data, dict):
        raise ValueError('Scenario must be an object')
    generators = data.pop('generators', [])
    if not isinstance(generators, list):
        raise ValueError('Generators must be a list')
    for generator in generators:
        fields = {'inventory', 'expected_inventory', 'base', 'prefix', 'copies', 'count'}
        if not isinstance(generator, dict) or set(generator) != fields or type(generator['copies']) is not int or not 1 <= generator['copies'] <= 1000:
            raise ValueError('Invalid scenario generator')
        if not isinstance(generator['prefix'], str) or not generator['prefix']:
            raise ValueError('Invalid generator prefix')
        if generator['inventory'] not in data['inventories'] or generator['expected_inventory'] not in data['expected']:
            raise ValueError('Unknown generator inventory')
        for index in range(generator['copies']):
            identity = generator['prefix'] + str(index)
            data['inventories'][generator['inventory']].append({'base': generator['base'], 'id': identity, 'name': identity, 'count': generator['count'], 'enchantment': identity})
            if identity in data['expected'][generator['expected_inventory']]:
                raise ValueError('Duplicate generated expectation')
            data['expected'][generator['expected_inventory']][identity] = generator['count']
    if set(data) != {'version', 'name', 'bases', 'inventories', 'actions', 'expected'} or data['version'] != 1:
        raise ValueError('Invalid scenario fields or version')
    if not isinstance(data['name'], str) or not data['name'] or not isinstance(data['bases'], list):
        raise ValueError('Invalid scenario name/bases')
    if len(set(data['bases'])) != len(data['bases']) or not all(isinstance(base, str) and base for base in data['bases']):
        raise ValueError('Duplicate/invalid base identity')
    if not isinstance(data['inventories'], dict) or not data['inventories']:
        raise ValueError('Inventories must be a nonempty object')
    identities = set()
    for inventory in data['inventories'].values():
        if not isinstance(inventory, list):
            raise ValueError('Inventory must be a list')
        for row in inventory:
            allowed = {'base', 'id', 'count', 'name', 'enchantment', 'owner', 'favorite', 'worn', 'charge', 'temper', 'soul'}
            if set(row) - allowed or not {'base', 'id', 'count'} <= row.keys():
                raise ValueError('Invalid physical stack fields')
            if row['base'] not in data['bases'] or not isinstance(row['id'], str) or not row['id'] or row['id'] in identities:
                raise ValueError('Unknown base or duplicate physical identity')
            if type(row['count']) is not int or not 0 < row['count'] <= 32767:
                raise ValueError('Invalid explicit stack count')
            for field in ('charge', 'temper'):
                if field in row and (type(row[field]) not in (int, float) or not math.isfinite(row[field]) or row[field] < 0):
                    raise ValueError('Invalid numeric metadata')
            if 'soul' in row and (type(row['soul']) is not int or not 0 <= row['soul'] <= 5):
                raise ValueError('Invalid soul level')
            for field in ('favorite', 'worn'):
                if field in row and type(row[field]) is not bool:
                    raise ValueError('Protection flags must be boolean')
            for field in ('name', 'enchantment', 'owner'):
                if field in row and (not isinstance(row[field], str) or not row[field]):
                    raise ValueError('Metadata identities must be nonempty strings')
            identities.add(row['id'])
    if not isinstance(data['actions'], list) or not isinstance(data['expected'], dict):
        raise ValueError('Invalid actions/expected state')
    for action in data['actions']:
        if set(action) - {'from', 'to', 'base', 'limit', 'refuse'} or not {'from', 'to', 'base'} <= action.keys():
            raise ValueError('Invalid action fields')
        if action['from'] not in data['inventories'] or action['to'] not in data['inventories'] or action['base'] not in data['bases']:
            raise ValueError('Unknown action reference')
        if 'limit' in action and (type(action['limit']) is not int or action['limit'] <= 0):
            raise ValueError('Invalid move limit')
        if 'refuse' in action and type(action['refuse']) is not bool:
            raise ValueError('Refusal must be boolean')
    if set(data['expected']) != set(data['inventories']):
        raise ValueError('Every inventory needs an expected state')
    totals = {identity: 0 for identity in identities}
    for inventory in data['inventories'].values():
        for row in inventory:
            totals[row['id']] += row['count']
    expected = {identity: 0 for identity in identities}
    for rows in data['expected'].values():
        if not isinstance(rows, dict):
            raise ValueError('Expected inventory must map instance IDs to counts')
        for identity, count in rows.items():
            if identity not in identities or type(count) is not int or count <= 0:
                raise ValueError('Invalid expected physical quantity')
            expected[identity] += count
    if expected != totals:
        raise ValueError('Expected state violates quantity conservation')
    return data
