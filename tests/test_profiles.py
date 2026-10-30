from pathlib import Path
import json
import tempfile
import unittest
from bale_desktop.profiles import ProfileStore


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / 'data'
        self.cache = Path(self.temporary.name) / 'cache'
        self.store = ProfileStore(self.data, self.cache)

    def test_existing_login_paths_preserved(self):
        cookie = self.data / 'cookies.sqlite'
        cookie.write_bytes(b'original session')
        self.assertEqual(self.store.storage('default'), (self.data, self.cache))
        self.store.add('کاری')
        self.assertEqual(cookie.read_bytes(), b'original session')

    def test_isolation_and_persistence(self):
        work = self.store.add('کاری')
        personal = self.store.add('شخصی')
        self.assertNotEqual(self.store.storage(work), self.store.storage(personal))
        self.assertNotEqual(self.store.storage(work), self.store.storage('default'))
        self.store.select(work)
        self.store.rename(work, 'دفتر')
        restored = ProfileStore(self.data, self.cache)
        self.assertEqual(restored.active, work)
        self.assertEqual(restored.get(work)['name'], 'دفتر')
        self.assertEqual(len(restored.items), 3)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)

    def test_names_are_not_paths(self):
        profile = self.store.add('../Work')
        self.assertTrue(self.store.storage(profile)[0].is_relative_to(self.data))
        self.assertNotIn('Work', str(self.store.storage(profile)[0]))
        for name in ['', ' ', 'a' * 33, 'line\nbreak', '../Work']:
            with self.assertRaises(ValueError):
                self.store.add(name)

    def test_invalid_config_never_overwritten(self):
        broken = {'active': '../../escape', 'profiles': [{'id': '../../escape', 'name': 'bad'}]}
        self.store.path.write_text(json.dumps(broken))
        original = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            ProfileStore(self.data, self.cache)
        self.assertEqual(original, self.store.path.read_bytes())

    def test_unknown_profile_rejected(self):
        with self.assertRaises(StopIteration):
            self.store.storage('../escape')
        self.assertEqual(self.store.active, 'default')
