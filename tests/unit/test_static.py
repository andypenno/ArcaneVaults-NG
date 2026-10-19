import configparser
import unittest
from support.data import load_json, overrides, translations, validate_static


class StaticDataTests(unittest.TestCase):
    def test_repository(self):
        self.assertGreater(validate_static()['translations'], 0)

    def test_bad_json(self):
        for value in ('{"a":1,"a":1}', '{"a":NaN}', '{"a":1e999}', '{"a":1,}', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                load_json(value)

    def test_bad_translations(self):
        for value in ('[]', '{}', '{"a":""}', '{"a":1}', '{"":"x"}', '{\n\n"a":"x"}', '{"a":"{"}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                translations(value)
        with self.assertRaises(ValueError):
            translations('{"a":"x"}', required=['missing'])
        with self.assertRaises(ValueError):
            translations('{"a":"{1}"}', signatures={'a': ['0']})
        self.assertEqual(translations('{"a":"{{text}} {0}"}', signatures={'a': ['0']})['a'], '{{text}} {0}')

    def test_override_identity(self):
        for body in ('Skyrim.esm|0x1 = Junk\nskyrim.ESM|0x000001 = Gear', 'Skyrim.esm|0x1 = Junk\nSkyrim.esm|0x1 = Junk',
                     'Skyrim.esm|0x1000000 = Junk', 'Skyrim.esm|0x0 = Junk', 'bad|0x1 = Junk',
                     'Skyrim.esm|0x1 = Unknown', 'Skyrim.esm|0x1 = ', 'Skyrim.esm|0x1 = Junk,Junk'):
            with self.subTest(body=body), self.assertRaises((ValueError, configparser.Error)):
                overrides('[Overrides]\n' + body, {'Junk', 'Gear'})
        self.assertEqual(len(overrides('[Overrides]\nSkyrim.esm|0x1 = Junk, Gear', {'Junk', 'Gear'})), 1)


if __name__ == '__main__':
    unittest.main()
