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

    def test_enchanted_loadouts_use_haul_items_and_have_spares(self):
        root = ROOT / 'tests/fixtures/sorting'
        haul = scenario(root / 'enchanted-haul-and-bare-spares.json')
        loot = {(r['base'], r.get('enchantment')) for r in haul['rows'] if r['id'].startswith('enchanted-loot-')}
        for name in ('enchanted-warrior-loadout', 'enchanted-mage-and-mixed-loot', 'enchanted-archer-and-spares'):
            case = scenario(root / (name + '.json'))
            worn = [r for r in case['rows'] if r.get('worn')]
            self.assertEqual(len(worn), 4)
            self.assertTrue(all((r['base'], r.get('enchantment')) in loot for r in worn))
            self.assertTrue(all(r['after'] == {'player': r['count']} for r in worn))
        case = scenario(root / 'enchanted-archer-and-spares.json')
        for worn in (r for r in case['rows'] if r.get('worn')):
            spares = [r for r in case['rows'] if r['base'] == worn['base'] and r['after'] != {'player': r['count']}]
            self.assertTrue(any(r.get('bare') for r in spares))
            self.assertTrue(any(r.get('enchantment') == worn['enchantment'] for r in spares))

    def test_bare_stacks_reject_metadata_and_ambiguous_identities(self):
        value = json.loads((ROOT / 'tests/fixtures/sorting/mixed-loot-and-bare-stacks.json').read_text())
        for problem in ('owner', 'favorite', 'copies', 'flag', 'duplicate_base'):
            data = copy.deepcopy(value)
            row = next(r for r in data['inventories']['player'] if r.get('bare'))
            if problem == 'duplicate_base':
                duplicate = copy.deepcopy(row)
                duplicate['id'] += '-duplicate'
                data['inventories']['player'].append(duplicate)
            elif problem == 'flag': row['bare'] = 'yes'
            else: row[problem] = {'owner': 'owner', 'favorite': True, 'copies': 2}[problem]
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.json'
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError): scenario(path)
