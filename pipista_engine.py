
# -*- coding: utf-8 -*-

"""

Pipista package engine.

Pure-standard-library package inspection, staged installation, verification,

tracking, recovery, and uninstall for Pythonista.

"""

import hashlib

import importlib

import io

import json

import os

import posixpath

import re

import shutil

import sys

import tarfile

import time

import uuid

import zipfile

from email.parser import Parser

from urllib import request

USER_AGENT = 'Pipista/0.1'

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024

MAX_EXPANDED_BYTES = 100 * 1024 * 1024

MAX_ARCHIVE_FILES = 5000

NATIVE_SUFFIXES = (

    '.so',

    '.dylib',

    '.dll',

    '.pyd',

)

BUILD_SOURCE_SUFFIXES = (

    '.c',

    '.cc',

    '.cpp',

    '.cxx',

    '.h',

    '.hpp',

    '.m',

    '.mm',

    '.pyx',

    '.rs',

)

class PipistaError(Exception):

    pass

class NetworkError(PipistaError):

    pass

class CompatibilityError(PipistaError):

    pass

class ArchiveSafetyError(PipistaError):

    pass

class InstallConflictError(PipistaError):

    pass

class VerificationError(PipistaError):

    pass

class DependencyInUseError(PipistaError):
    """Raised when another managed package still needs this package."""


class ModifiedFilesError(PipistaError):

    def __init__(self, files):

        self.files = list(files)

        message = 'Managed files were modified: {}'.format(', '.join(self.files))

        super().__init__(message)

def canonical_name(name):

    return re.sub(r'[-_.]+', '-', str(name or '')).lower().strip('-')

def default_site_packages():

    documents = os.path.expanduser('~/Documents')

    modern = os.path.join(documents, 'site-packages-3')

    legacy = os.path.join(documents, 'site-packages')

    if os.path.isdir(modern):

        return modern

    if os.path.isdir(legacy):

        return legacy

    return modern

def sha256_bytes(data):

    return hashlib.sha256(data).hexdigest()

def sha256_file(path):

    digest = hashlib.sha256()

    with open(path, 'rb') as handle:

        while True:

            chunk = handle.read(64 * 1024)

            if not chunk:

                break

            digest.update(chunk)

    return digest.hexdigest()

def safe_relative_path(name):

    value = str(name or '').replace('\\', '/')

    if not value or value.startswith('/'):

        raise ArchiveSafetyError('Unsafe archive path: {!r}'.format(name))

    if len(value) >= 2 and value[1] == ':':

        raise ArchiveSafetyError('Drive-qualified archive path: {!r}'.format(name))

    normal = posixpath.normpath(value)

    parts = normal.split('/')

    if normal in ('', '.', '..'):

        raise ArchiveSafetyError('Unsafe archive path: {!r}'.format(name))

    if normal.startswith('../') or '..' in parts:

        raise ArchiveSafetyError('Archive path escapes its root: {!r}'.format(name))

    return normal

def _read_response(response, maximum):

    declared = response.headers.get('Content-Length')

    if declared:

        try:

            if int(declared) > maximum:

                raise NetworkError(

                    'Download is too large: {} bytes'.format(declared)

                )

        except ValueError:

            pass

    chunks = []

    total = 0

    while True:

        chunk = response.read(64 * 1024)

        if not chunk:

            break

        total += len(chunk)

        if total > maximum:

            raise NetworkError(

                'Download exceeded {} bytes'.format(maximum)

            )

        chunks.append(chunk)

    return b''.join(chunks)

def fetch_bytes(url, timeout=30, maximum=MAX_DOWNLOAD_BYTES):

    req = request.Request(url)

    req.add_header('User-Agent', USER_AGENT)

    try:

        with request.urlopen(req, timeout=timeout) as response:

            return _read_response(response, maximum)

    except PipistaError:

        raise

    except Exception as exc:

        raise NetworkError('Request failed for {}: {}'.format(url, exc))

def fetch_json(url, timeout=20):

    data = fetch_bytes(url, timeout=timeout)

    try:

        return json.loads(data.decode('utf-8'))

    except Exception as exc:

        raise NetworkError('Invalid JSON from {}: {}'.format(url, exc))

def _wheel_tags(filename):

    if not filename.endswith('.whl'):

        return None

    parts = filename[:-4].split('-')

    if len(parts) < 5:

        return None

    return parts[-3], parts[-2], parts[-1]

def wheel_is_compatible(filename):

    tags = _wheel_tags(filename)

    if tags is None:

        return False

    python_tag, abi_tag, platform_tag = tags

    if abi_tag != 'none' or platform_tag != 'any':

        return False

    major = sys.version_info[0]

    minor = sys.version_info[1]

    accepted = {

        'py{}'.format(major),

        'py{}{}'.format(major, minor),

        'cp{}{}'.format(major, minor),

    }

    for tag in python_tag.split('.'):

        if tag in accepted:

            return True

    return False

def _distribution_choice(meta):

    urls = [

        item for item in (meta.get('urls') or [])

        if not item.get('yanked')

    ]

    wheels = [

        item for item in urls

        if item.get('packagetype') == 'bdist_wheel'

        and wheel_is_compatible(item.get('filename') or '')

    ]

    wheels.sort(key=lambda item: item.get('filename') or '')

    if wheels:

        return 'wheel', wheels[0]

    sources = [

        item for item in urls

        if item.get('packagetype') == 'sdist'

        and (item.get('filename') or '').endswith(

            ('.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.tar', '.zip')

        )

    ]

    sources.sort(key=lambda item: item.get('filename') or '')

    if sources:

        return 'sdist', sources[0]

    raise CompatibilityError(

        'No compatible universal wheel or supported source archive was found'

    )

def inspect_pypi(package):

    package = str(package or '').strip()

    if not package:

        raise ValueError('Package name is required')

    url = 'https://pypi.org/pypi/{}/json'.format(package)

    meta = fetch_json(url)

    info = meta.get('info') or {}

    kind, artifact = _distribution_choice(meta)

    return {

        'source': 'pypi',

        'requested_name': package,

        'name': info.get('name') or package,

        'canonical_name': canonical_name(info.get('name') or package),

        'version': info.get('version') or '',

        'summary': info.get('summary') or '',

        'requires_python': info.get('requires_python') or '',

        'dependencies': info.get('requires_dist') or [],

        'project_url': info.get('project_url') or '',

        'kind': kind,

        'filename': artifact.get('filename') or '',

        'url': artifact.get('url') or '',

        'sha256': (artifact.get('digests') or {}).get('sha256') or '',

        'size': artifact.get('size'),

    }

def _validate_archive_entries(entries):

    if len(entries) > MAX_ARCHIVE_FILES:

        raise ArchiveSafetyError(

            'Archive contains too many files: {}'.format(len(entries))

        )

    total = 0

    seen = set()

    for name, size, kind in entries:

        safe = safe_relative_path(name)

        if safe in seen:

            raise ArchiveSafetyError(

                'Archive contains a duplicate path: {}'.format(safe)

            )

        seen.add(safe)

        if kind not in ('file', 'directory'):

            raise ArchiveSafetyError(

                'Archive contains unsupported link or special entry: {}'.format(

                    safe

                )

            )

        if kind == 'file':

            total += int(size or 0)

            if total > MAX_EXPANDED_BYTES:

                raise ArchiveSafetyError(

                    'Expanded archive exceeds {} bytes'.format(

                        MAX_EXPANDED_BYTES

                    )

                )

def _extract_zip(data, destination):

    with zipfile.ZipFile(io.BytesIO(data)) as archive:

        entries = []

        for item in archive.infolist():

            mode = (item.external_attr >> 16) & 0o170000

            if item.is_dir():

                kind = 'directory'

            elif mode == 0o120000:

                kind = 'symlink'

            else:

                kind = 'file'

            entries.append((item.filename, item.file_size, kind))

        _validate_archive_entries(entries)

        for item in archive.infolist():

            relative = safe_relative_path(item.filename)

            target = os.path.join(destination, *relative.split('/'))

            if item.is_dir():

                os.makedirs(target, exist_ok=True)

                continue

            parent = os.path.dirname(target)

            os.makedirs(parent, exist_ok=True)

            with archive.open(item) as source, open(target, 'wb') as output:

                shutil.copyfileobj(source, output)

def _extract_tar(data, destination):

    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:

        entries = []

        for member in archive.getmembers():

            if member.isdir():

                kind = 'directory'

            elif member.isfile():

                kind = 'file'

            else:

                kind = 'special'

            entries.append((member.name, member.size, kind))

        _validate_archive_entries(entries)

        for member in archive.getmembers():

            relative = safe_relative_path(member.name)

            target = os.path.join(destination, *relative.split('/'))

            if member.isdir():

                os.makedirs(target, exist_ok=True)

                continue

            parent = os.path.dirname(target)

            os.makedirs(parent, exist_ok=True)

            source = archive.extractfile(member)

            if source is None:

                raise ArchiveSafetyError(

                    'Could not read archive member: {}'.format(relative)

                )

            with source, open(target, 'wb') as output:

                shutil.copyfileobj(source, output)

def extract_archive(data, filename, destination):

    os.makedirs(destination, exist_ok=True)

    if filename.endswith('.whl') or filename.endswith('.zip'):

        _extract_zip(data, destination)

        return

    if filename.endswith(

        ('.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.tar')

    ):

        _extract_tar(data, destination)

        return

    raise CompatibilityError(

        'Unsupported archive format: {}'.format(filename)

    )

def _single_archive_root(directory):

    names = [

        name for name in os.listdir(directory)

        if name not in ('__MACOSX',)

    ]

    if len(names) == 1:

        candidate = os.path.join(directory, names[0])

        if os.path.isdir(candidate):

            return candidate

    return directory

def _contains_forbidden_native_files(directory):

    matches = []

    for root, _dirs, files in os.walk(directory):

        for filename in files:

            lower = filename.lower()

            if lower.endswith(NATIVE_SUFFIXES + BUILD_SOURCE_SUFFIXES):

                matches.append(os.path.join(root, filename))

    return matches

def _copy_tree_files(source, destination):

    copied = []

    for root, dirs, files in os.walk(source):

        dirs[:] = [

            name for name in dirs

            if name not in ('__pycache__', '.git')

        ]

        relative_root = os.path.relpath(root, source)

        if relative_root == '.':

            relative_root = ''

        for filename in files:

            if filename.endswith(('.pyc', '.pyo')):

                continue

            source_path = os.path.join(root, filename)

            relative = os.path.join(relative_root, filename)

            target_path = os.path.join(destination, relative)

            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            shutil.copy2(source_path, target_path)

            copied.append(relative.replace(os.sep, '/'))

    return copied

def _metadata_from_source(source_root):

    candidates = []

    for root, _dirs, files in os.walk(source_root):

        if 'PKG-INFO' in files:

            candidates.append(os.path.join(root, 'PKG-INFO'))

    candidates.sort(key=lambda path: (path.count(os.sep), len(path)))

    if not candidates:

        return '', {}

    with open(candidates[0], 'r', encoding='utf-8', errors='replace') as handle:

        text = handle.read()

    message = Parser().parsestr(text)

    return text, {

        'name': message.get('Name', ''),

        'version': message.get('Version', ''),

        'requires_python': message.get('Requires-Python', ''),

        'dependencies': message.get_all('Requires-Dist') or [],

    }

def _top_level_payload(source_root):

    bases = [source_root]

    src_base = os.path.join(source_root, 'src')

    if os.path.isdir(src_base):

        bases.insert(0, src_base)

    detected = []

    for base in bases:

        packages = []

        modules = []

        for name in sorted(os.listdir(base)):

            path = os.path.join(base, name)

            if os.path.isdir(path):

                if os.path.isfile(os.path.join(path, '__init__.py')):

                    packages.append(name)

            elif (

                name.endswith('.py')

                and name not in ('setup.py',)

                and not name.startswith('test_')

            ):

                modules.append(name)

        if packages or modules:

            detected.append((base, packages, modules))

    if len(detected) != 1:

        raise CompatibilityError(

            'Source archive layout is ambiguous; a reviewed recipe is required'

        )

    return detected[0]

def _write_text(path, text):

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, 'w', encoding='utf-8') as handle:

        handle.write(text)

def _prepare_sdist(candidate, archive_root, payload_root):

    source_root = _single_archive_root(archive_root)

    forbidden = _contains_forbidden_native_files(source_root)

    if forbidden:

        relative = [

            os.path.relpath(path, source_root)

            for path in forbidden[:10]

        ]

        raise CompatibilityError(

            'Source archive contains native/build files: {}'.format(

                ', '.join(relative)

            )

        )

    metadata_text, archive_metadata = _metadata_from_source(source_root)

    base, packages, modules = _top_level_payload(source_root)

    imports = list(packages)

    imports.extend(os.path.splitext(name)[0] for name in modules)

    copied = []

    for package in packages:

        source = os.path.join(base, package)

        destination = os.path.join(payload_root, package)

        copied.extend(

            [

                '{}/{}'.format(package, path)

                for path in _copy_tree_files(source, destination)

            ]

        )

    for module in modules:

        source = os.path.join(base, module)

        destination = os.path.join(payload_root, module)

        shutil.copy2(source, destination)

        copied.append(module)

    dist_name = re.sub(

        r'[-.]+',

        '_',

        candidate.get('name') or candidate.get('requested_name') or 'package',

    )

    version = candidate.get('version') or '0'

    dist_info = '{}-{}.dist-info'.format(dist_name, version)

    dist_root = os.path.join(payload_root, dist_info)

    if not metadata_text:

        metadata_text = (

            'Metadata-Version: 2.1\n'

            'Name: {name}\n'

            'Version: {version}\n'

            'Summary: {summary}\n'

        ).format(

            name=candidate.get('name') or '',

            version=version,

            summary=candidate.get('summary') or '',

        )

    _write_text(os.path.join(dist_root, 'METADATA'), metadata_text)

    _write_text(os.path.join(dist_root, 'INSTALLER'), 'pipista\n')

    _write_text(

        os.path.join(dist_root, 'PIPISTA_SOURCE.json'),

        json.dumps(

            {

                'source': candidate.get('source'),

                'url': candidate.get('url'),

                'sha256': candidate.get('sha256'),

                'filename': candidate.get('filename'),

            },

            indent=2,

            sort_keys=True,

        ) + '\n',

    )

    copied.extend([

        dist_info + '/METADATA',

        dist_info + '/INSTALLER',

        dist_info + '/PIPISTA_SOURCE.json',

    ])

    record_lines = [

        '{},,'.format(path.replace(os.sep, '/'))

        for path in sorted(copied)

    ]

    record_lines.append('{}/RECORD,,'.format(dist_info))

    _write_text(

        os.path.join(dist_root, 'RECORD'),

        '\n'.join(record_lines) + '\n',

    )

    copied.append(dist_info + '/RECORD')

    return {

        'imports': imports,

        'files': sorted(set(copied)),

        'archive_metadata': archive_metadata,

    }

def _prepare_wheel(candidate, archive_root, payload_root):
    forbidden = _contains_forbidden_native_files(archive_root)
    skipped_native_files = []

    for path in forbidden:
        relative = os.path.relpath(
            path,
            archive_root,
        ).replace(os.sep, '/')
        skipped_native_files.append(relative)

        if os.path.isfile(path):
            os.remove(path)

    data_dirs = [
        name
        for name in os.listdir(archive_root)
        if name.endswith('.data')
    ]

    if data_dirs:
        raise CompatibilityError(
            'Wheel uses a .data installation layout; support is not yet enabled'
        )

    copied = _copy_tree_files(archive_root, payload_root)
    imports = []

    for name in sorted(os.listdir(payload_root)):
        path = os.path.join(payload_root, name)

        if name.endswith('.dist-info'):
            continue

        if (
            os.path.isdir(path)
            and os.path.isfile(os.path.join(path, '__init__.py'))
        ):
            imports.append(name)
        elif os.path.isfile(path) and name.endswith('.py'):
            imports.append(os.path.splitext(name)[0])

    metadata_only = not imports

    if metadata_only and skipped_native_files:
        raise CompatibilityError(
            'Wheel only exposes incompatible native or build files'
        )

    if metadata_only and not (candidate.get('dependencies') or []):
        raise CompatibilityError(
            'Wheel contains no importable package and declares no dependencies'
        )

    return {
        'imports': imports,
        'files': sorted(set(copied)),
        'archive_metadata': {},
        'metadata_only': metadata_only,
        'skipped_native_files': sorted(skipped_native_files),
    }

def _atomic_json(path, value):

    os.makedirs(os.path.dirname(path), exist_ok=True)

    temporary = path + '.tmp'

    with open(temporary, 'w', encoding='utf-8') as handle:

        json.dump(value, handle, indent=2, sort_keys=True)

        handle.write('\n')

    os.replace(temporary, path)

def _load_json(path, default):

    if not os.path.isfile(path):

        return default

    with open(path, 'r', encoding='utf-8') as handle:

        return json.load(handle)

class PackageManager:

    def __init__(self, target_dir=None, state_dir=None):

        self.target_dir = os.path.abspath(

            target_dir or default_site_packages()

        )

        if state_dir is None:

            state_dir = os.path.join(

                os.path.expanduser('~/Documents'),

                '.pipista',

            )

        self.state_dir = os.path.abspath(state_dir)

        self.staging_dir = os.path.join(self.state_dir, 'staging')

        self.database_path = os.path.join(

            self.state_dir,

            'installed.json',

        )

        self.transaction_path = os.path.join(

            self.state_dir,

            'transaction.json',

        )

        os.makedirs(self.target_dir, exist_ok=True)

        os.makedirs(self.staging_dir, exist_ok=True)

        if self.target_dir not in sys.path:

            sys.path.insert(0, self.target_dir)

        self.recover_interrupted_install()

    def inspect_pypi(self, package):

        return inspect_pypi(package)

    def installed(self):

        database = _load_json(self.database_path, {})

        return [

            database[key]

            for key in sorted(database)

        ]

    def _target_path(self, relative):

        relative = safe_relative_path(relative)

        target = os.path.abspath(

            os.path.join(self.target_dir, *relative.split('/'))

        )

        if os.path.commonpath([self.target_dir, target]) != self.target_dir:

            raise ArchiveSafetyError(

                'Managed path escapes site-packages: {}'.format(relative)

            )

        return target

    def _remove_files(self, relative_files):

        directories = set()

        for relative in sorted(relative_files, reverse=True):

            target = self._target_path(relative)

            if os.path.isfile(target) or os.path.islink(target):

                os.remove(target)

            parent = os.path.dirname(target)

            while (

                parent

                and os.path.commonpath([self.target_dir, parent])

                == self.target_dir

            ):

                if parent == self.target_dir:

                    break

                directories.add(parent)

                parent = os.path.dirname(parent)

        for directory in sorted(

            directories,

            key=lambda value: len(value),

            reverse=True,

        ):

            try:

                if os.path.isdir(directory) and not os.listdir(directory):

                    os.rmdir(directory)

            except OSError:

                pass

    def recover_interrupted_install(self):

        if not os.path.isfile(self.transaction_path):

            return False

        transaction = _load_json(self.transaction_path, {})

        package_key = transaction.get('package_key') or ''

        database = _load_json(self.database_path, {})

        if package_key and package_key in database:

            os.remove(self.transaction_path)

            return False

        planned = transaction.get('planned_files') or []

        self._remove_files(planned)

        if os.path.isfile(self.transaction_path):

            os.remove(self.transaction_path)

        return True

    def install_pypi(self, package, import_name=None):
        candidate = self.inspect_pypi(package)
        package_key = candidate['canonical_name']
        database = _load_json(self.database_path, {})

        if package_key in database:
            raise InstallConflictError(
                '{} is already managed by Pipista'.format(candidate['name'])
            )

        archive = fetch_bytes(candidate['url'])
        expected_hash = candidate.get('sha256') or ''
        actual_hash = sha256_bytes(archive)

        if not expected_hash:
            raise ArchiveSafetyError(
                'PyPI did not provide a SHA-256 digest'
            )

        if actual_hash != expected_hash:
            raise ArchiveSafetyError(
                'Downloaded archive hash does not match PyPI metadata'
            )

        token = uuid.uuid4().hex
        stage = os.path.join(self.staging_dir, token)
        archive_root = os.path.join(stage, 'archive')
        payload_root = os.path.join(stage, 'payload')
        os.makedirs(archive_root)
        os.makedirs(payload_root)

        try:
            extract_archive(
                archive,
                candidate['filename'],
                archive_root,
            )

            if candidate['kind'] == 'wheel':
                prepared = _prepare_wheel(
                    candidate,
                    archive_root,
                    payload_root,
                )
            else:
                prepared = _prepare_sdist(
                    candidate,
                    archive_root,
                    payload_root,
                )

            imports = prepared['imports']
            metadata_only = bool(prepared.get('metadata_only'))
            verify_name = import_name or (imports[0] if imports else '')

            if not verify_name and not metadata_only:
                raise VerificationError(
                    'No import name could be detected'
                )

            relative_files = prepared['files']
            conflicts = []

            for relative in relative_files:
                target = self._target_path(relative)
                if os.path.lexists(target):
                    conflicts.append(relative)

            if conflicts:
                raise InstallConflictError(
                    'Installation would overwrite unmanaged files: {}'.format(
                        ', '.join(conflicts[:12])
                    )
                )

            transaction = {
                'package_key': package_key,
                'started_at': time.time(),
                'planned_files': relative_files,
            }
            _atomic_json(self.transaction_path, transaction)

            for relative in relative_files:
                source = os.path.join(
                    payload_root,
                    *relative.split('/')
                )
                target = self._target_path(relative)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)

            importlib.invalidate_caches()
            imported = None

            if verify_name:
                prefix = verify_name + '.'

                for key in list(sys.modules):
                    if key == verify_name or key.startswith(prefix):
                        sys.modules.pop(key, None)

                try:
                    imported = importlib.import_module(verify_name)
                except BaseException as exc:
                    raise VerificationError(
                        "Installed files, but import '{}' failed: {}".format(
                            verify_name,
                            exc,
                        )
                    )

            file_hashes = {}

            for relative in relative_files:
                file_hashes[relative] = sha256_file(
                    self._target_path(relative)
                )

            verified_module = ''
            if imported is not None:
                verified_module = getattr(
                    imported,
                    '__name__',
                    verify_name,
                )

            record = {
                'name': candidate['name'],
                'canonical_name': package_key,
                'version': candidate['version'],
                'summary': candidate['summary'],
                'source': 'pypi',
                'source_url': candidate['url'],
                'artifact': candidate['filename'],
                'artifact_kind': candidate['kind'],
                'artifact_sha256': actual_hash,
                'import_name': verify_name,
                'detected_imports': imports,
                'dependencies': candidate['dependencies'],
                'requires_python': candidate['requires_python'],
                'installed_at': time.time(),
                'target_dir': self.target_dir,
                'files': file_hashes,
                'verified_module': verified_module,
                'metadata_only': metadata_only,
                'skipped_native_files': (
                    prepared.get('skipped_native_files') or []
                ),
                'resolved_dependencies': [],
                'dependency_status': {},
                'required_by': [],
                'install_reason': 'direct',
            }

            database[package_key] = record
            _atomic_json(self.database_path, database)

            if os.path.isfile(self.transaction_path):
                os.remove(self.transaction_path)

            return record

        except BaseException:
            transaction = _load_json(self.transaction_path, {})
            self._remove_files(
                transaction.get('planned_files') or []
            )

            if os.path.isfile(self.transaction_path):
                os.remove(self.transaction_path)

            raise
        finally:
            if os.path.isdir(stage):
                shutil.rmtree(stage)

    def uninstall(self, package, force=False):
        package_key = canonical_name(package)
        database = _load_json(self.database_path, {})
        record = database.get(package_key)

        if record is None:
            raise PipistaError(
                '{} is not managed by Pipista'.format(package)
            )

        active_required_by = [
            key
            for key in record.get('required_by') or []
            if key in database
        ]

        if active_required_by and not force:
            names = [
                database[key].get('name') or key
                for key in active_required_by
            ]
            raise DependencyInUseError(
                '{} is still required by {}'.format(
                    record.get('name') or package,
                    ', '.join(names),
                )
            )

        modified = []

        for relative, expected_hash in record.get('files', {}).items():
            target = self._target_path(relative)

            if not os.path.isfile(target):
                continue

            if sha256_file(target) != expected_hash:
                modified.append(relative)

        if modified and not force:
            raise ModifiedFilesError(modified)

        self._remove_files(record.get('files', {}).keys())

        import_name = record.get('import_name') or ''
        prefix = import_name + '.'

        for key in list(sys.modules):
            if key == import_name or (
                import_name and key.startswith(prefix)
            ):
                sys.modules.pop(key, None)

        importlib.invalidate_caches()
        database.pop(package_key, None)

        for other_record in database.values():
            required_by = [
                key
                for key in other_record.get('required_by') or []
                if key != package_key
            ]
            resolved = [
                key
                for key in other_record.get('resolved_dependencies') or []
                if key != package_key
            ]

            other_record['required_by'] = required_by
            other_record['resolved_dependencies'] = resolved

            dependency_status = dict(
                other_record.get('dependency_status') or {}
            )
            dependency_status.pop(package_key, None)
            other_record['dependency_status'] = dependency_status

        orphaned = []

        for other_record in database.values():
            if (
                other_record.get('install_reason') == 'dependency'
                and not (other_record.get('required_by') or [])
            ):
                orphaned.append(
                    other_record.get('name')
                    or other_record.get('canonical_name')
                    or ''
                )

        _atomic_json(self.database_path, database)

        return {
            'name': record.get('name') or package,
            'version': record.get('version') or '',
            'removed_files': len(record.get('files', {})),
            'forced': bool(force),
            'orphaned_dependencies': sorted(
                name for name in orphaned if name
            ),
        }
