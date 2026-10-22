import unittest
from support.data import ROOT, load_json, overrides
from support.sorting import enum_names


class MapsTests(unittest.TestCase):
    def test_fishing_defaults_and_display_names(self):
        fixture = load_json((ROOT / 'tests/fixtures/fishing-maps.json').read_text())
        expected = {(fixture['plugin'].casefold(), int(row['local_id'], 16)) for row in fixture['maps']}
        self.assertEqual(len(expected), 8)
        defaults = overrides((ROOT / 'ini/ArcaneVaultOverrides.ini').read_text(), set(enum_names('ItemCategory')))
        actual = {identity for identity, categories in defaults.items() if identity[0] == fixture['plugin'].casefold() and categories == ['Map']}
        self.assertEqual(actual, expected)
        strings = load_json((ROOT / 'ini/ArcaneVaultTranslation.json').read_text())
        self.assertEqual(strings['Vault.Maps'], 'Maps')
        from esp import walk
        definition = load_json((ROOT / 'release/ArcaneVaults-LinkedStorage.json').read_text())
        container = next(node for node in walk(definition['records']) if node['form_id'] == '0x01000DDC')
        self.assertEqual(next(field['text'] for field in container['fields'] if field['type'] == 'FULL'), 'Maps Vault')
        self.assertEqual(next(field['text'] for field in container['fields'] if field['type'] == 'EDID'), 'AV_Maps')
