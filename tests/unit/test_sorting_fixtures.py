import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from support.data import ROOT
from support.sorting import catalog, enum_names, scenario


class SortingFixtureTests(unittest.TestCase):
    def test_every_category_and_registered_vault_has_representative_data(self):
        items = catalog()
        categories = {name for item in items.values() for name in item['categories']}
        self.assertEqual(categories, set(enum_names('ItemCategory')) - {'None'})
        registered = set(re.findall(r'AddContainer\(dataHandler, Container::(\w+), RE::FormID\([^)]*\), ContainerGroup::(?:Vault|Archive)',
                                    (ROOT / 'src/Utility.cpp').read_text()))
        covered = {name for item in items.values() for name in item['vaults']}
        self.assertTrue(registered)
        self.assertEqual(covered, registered)
        cases = [scenario(path) for path in (ROOT / 'tests/fixtures/sorting').glob('*.json') if path.stem != 'catalog']
        self.assertEqual({row['base'] for case in cases for row in case['rows']}, set(items))
        self.assertTrue(any(case['no_transfers'] and len(case['rows']) >= 20 for case in cases))
        for size in (500, 1000):
            case = next(case for case in cases if case['name'] == f'large-mixed-{size}')
            self.assertEqual(sum(row['inventory'] == 'player' for row in case['rows']), size)
            self.assertGreater(len({row['base'] for row in case['rows']}), 40)

    def test_malformed_expected_state_and_flags_fail(self):
        original = json.loads((ROOT / 'tests/fixtures/sorting/protected-adventurer-loadout.json').read_text())
        for problem in ('conservation', 'unknown_destination', 'duplicate', 'flag', 'setting', 'copies', 'no_transfer', 'charge', 'soul', 'owner'):
            value = copy.deepcopy(original)
            row = value['inventories']['player'][0]
            if problem == 'conservation':row['after']['player'] += 1
            elif problem == 'unknown_destination':row['after'] = {'NotAVault': row['count']}
            elif problem == 'duplicate':value['inventories']['player'].append(copy.deepcopy(row))
            elif problem == 'flag':row['favorite'] = 'yes'
            elif problem == 'setting':value['settings']['GSC_NotASetting'] = True
            elif problem == 'copies':row['copies'] = -1
            elif problem == 'charge':row['charge'] = -1
            elif problem == 'soul':row['soul'] = 6
            elif problem == 'owner':row['owner'] = ''
            else:row['after'] = {'Weapon': row['count']}
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.json';path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):scenario(path)
