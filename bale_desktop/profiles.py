"""Persistent profile names and isolated storage paths; preserve the original login."""
import json
import os
from pathlib import Path
import re
from uuid import uuid4


class ProfileStore:
    def __init__(self, data_root, cache_root):
        self.data_root, self.cache_root = Path(data_root), Path(cache_root)
        self.data_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.data_root / 'profiles.json'
        if self.path.exists():
            try:
                config = json.loads(self.path.read_text())
                self.items = config['profiles']
                self.active = config['active']
                ids = [p['id'] for p in self.items]
                if (not self.items or len(ids) != len(set(ids)) or 'default' not in ids
                        or self.active not in ids or any(not self.valid_id(i) for i in ids)
                        or any(not isinstance(p['name'], str) or not p['name'].strip()
                               or len(p['name']) > 32 for p in self.items)):
                    raise ValueError('Invalid profile configuration')
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError('فهرست پروفایل‌ها قابل خواندن نیست؛ فایل profiles.json را بررسی کنید.') from error
        else:
            self.items = [{'id': 'default', 'name': 'حساب اصلی'}]
            self.active = 'default'
            self.save()

    @staticmethod
    def valid_id(value):
        return isinstance(value, str) and (value == 'default' or re.fullmatch(r'[a-f0-9]{32}', value) is not None)

    def get(self, profile_id):
        return next(p for p in self.items if p['id'] == profile_id)

    def storage(self, profile_id):
        self.get(profile_id)
        # The first account uses exactly the previous version's paths and cookies.
        if profile_id == 'default':
            return self.data_root, self.cache_root
        return (self.data_root / 'profiles' / profile_id,
                self.cache_root / 'profiles' / profile_id)

    def check_name(self, name, excluding=None):
        name = name.strip()
        if not name or len(name) > 32 or any(ord(c) < 32 for c in name):
            raise ValueError('نام پروفایل باید بین ۱ تا ۳۲ نویسه باشد.')
        if any(p['id'] != excluding and p['name'].casefold() == name.casefold() for p in self.items):
            raise ValueError('این نام قبلاً استفاده شده است.')
        return name

    def add(self, name):
        item = {'id': uuid4().hex, 'name': self.check_name(name)}
        self.items.append(item)
        try:
            self.save()
        except OSError:
            self.items.pop()
            raise
        return item['id']

    def rename(self, profile_id, name):
        item = self.get(profile_id)
        old_name = item['name']
        item['name'] = self.check_name(name, profile_id)
        try:
            self.save()
        except OSError:
            item['name'] = old_name
            raise

    def select(self, profile_id):
        self.get(profile_id)
        previous = self.active
        self.active = profile_id
        try:
            self.save()
        except OSError:
            self.active = previous
            raise

    def save(self):
        temporary = self.path.with_suffix('.json.tmp')
        with temporary.open('w', encoding='utf-8') as output:
            os.chmod(temporary, 0o600)
            json.dump({'profiles': self.items, 'active': self.active}, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self.path)
