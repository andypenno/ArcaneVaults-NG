import unittest
from support.data import ROOT, load_json, overrides
from support.sorting import enum_names


class RemainsTests(unittest.TestCase):
    def test_defaults_and_exclusions(self):
        defaults = overrides((ROOT / 'ini/ArcaneVaultOverrides.ini').read_text(), set(enum_names('ItemCategory')))
        expected = {('skyrim.esm', value) for value in (0x3ADA4, 0x3ADA3, 0x3AD6C, 0x3AD68, 0x319E4, 0xAF5FD)}
        expected |= {('dragonborn.esm', 0x20DCF), ('hearthfires.esm', 0x303F)}
        actual = {identity for identity, categories in defaults.items() if 'Remains' in categories}
        self.assertEqual(actual, expected)
        for identity in expected:
            self.assertEqual(defaults[identity], ['Remains'])
        for value in (0x319E3, 0x319E5):
            self.assertEqual(defaults[('skyrim.esm', value)], ['Junk'])
        for value in (0x3AD52, 0x3AD70, 0x34CDD):
            self.assertNotIn('Remains', defaults.get(('skyrim.esm', value), []))

    def test_archive_definition_and_registration(self):
        from esp import walk
        records = {int(node['form_id'], 16) & 0xFFFFFF: node for node in walk(
            load_json((ROOT / 'release/ArcaneVaults-LinkedStorage.json').read_text())['records'])}
        base, ref = records[0xDF1], records[0xDF2]
        self.assertEqual((base['type'], ref['type']), ('CONT', 'REFR'))
        self.assertEqual(next(f['text'] for f in base['fields'] if f['type'] == 'FULL'), 'Remains Vault')
        self.assertEqual(int(next(f['form_id'] for f in ref['fields'] if f['type'] == 'NAME'), 16) & 0xFFFFFF, 0xDF1)
        self.assertTrue(ref['flags'] & 0x400)
        self.assertEqual(load_json((ROOT / 'ini/ArcaneVaultTranslation.json').read_text())['Vault.Remains'], 'Remains')
