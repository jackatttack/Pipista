# -*- coding: utf-8 -*-
"""Read-only inventory of importable Pythonista modules."""

import os
import re
import sys


DOCUMENTS = os.path.abspath(os.path.expanduser('~/Documents'))
SKIP_DIRECTORIES = {
    '__pycache__',
    '.git',
    '__MACOSX',
}
VERSION_PATTERN = re.compile(
    r'''__version__\s*=\s*["']([^"']+)["']'''
)


def canonical_name(value):
    return re.sub(r'[-_.]+', '-', str(value or '')).lower().strip('-')


def _location_kind(path):
    absolute = os.path.abspath(path)

    if absolute.startswith(DOCUMENTS):
        return 'user'

    if '.app/' in absolute or '/Frameworks/' in absolute:
        return 'bundled'

    return 'other'


def _read_version(path):
    if os.path.isdir(path):
        candidate = os.path.join(path, '__init__.py')
    else:
        candidate = path

    if not os.path.isfile(candidate):
        return ''

    try:
        with open(
            candidate,
            'r',
            encoding='utf-8',
            errors='replace',
        ) as handle:
            text = handle.read(64 * 1024)
    except Exception:
        return ''

    match = VERSION_PATTERN.search(text)
    return match.group(1) if match else ''


def _candidates(path):
    if not os.path.isdir(path):
        return []

    found = []

    for name in sorted(os.listdir(path), key=str.lower):
        if name.startswith('.') or name in SKIP_DIRECTORIES:
            continue

        lower = name.lower()

        if lower.endswith((
            '.dist-info',
            '.egg-info',
            '.data',
        )):
            continue

        full_path = os.path.join(path, name)

        if (
            os.path.isdir(full_path)
            and os.path.isfile(
                os.path.join(full_path, '__init__.py')
            )
        ):
            found.append((name, full_path))
        elif os.path.isfile(full_path) and name.endswith('.py'):
            found.append((name[:-3], full_path))

    return found


def scan_environment(managed_records=None):
    managed_records = managed_records or []
    managed_imports = set()

    for record in managed_records:
        import_names = record.get('detected_imports') or []
        import_name = record.get('import_name') or ''

        for name in list(import_names) + [import_name]:
            if name:
                managed_imports.add(canonical_name(name))

    groups = {
        'user': {},
        'bundled': {},
        'other': {},
    }

    seen_paths = set()

    for raw_path in sys.path:
        if 'site-packages' not in str(raw_path):
            continue

        path = os.path.abspath(raw_path)

        if path in seen_paths:
            continue

        seen_paths.add(path)
        kind = _location_kind(path)

        for name, full_path in _candidates(path):
            key = canonical_name(name)
            existing = groups[kind].get(key)

            item = {
                'name': name,
                'version': _read_version(full_path),
                'kind': kind,
                'location': os.path.basename(path),
                'path': full_path,
                'managed': key in managed_imports,
            }

            if existing is None:
                groups[kind][key] = item
            else:
                locations = set(
                    str(existing.get('location') or '').split(', ')
                )
                locations.add(item['location'])
                existing['location'] = ', '.join(
                    sorted(value for value in locations if value)
                )
                existing['managed'] = (
                    existing.get('managed')
                    or item['managed']
                )

    return {
        kind: sorted(
            values.values(),
            key=lambda item: item['name'].lower(),
        )
        for kind, values in groups.items()
    }