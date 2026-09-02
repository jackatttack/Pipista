# -*- coding: utf-8 -*-
"""
Managed GitHub project snapshots for Pipista.

Public repositories can be installed without a token or local git executable.
Each installation records its exact commit and file hashes. Local edits and
untracked files are detected before uninstall.
"""

import os
import re
import shutil
import time
import uuid
from urllib import parse

from .engine import (
    InstallConflictError,
    ModifiedFilesError,
    PipistaError,
    _atomic_json,
    _load_json,
    extract_archive,
    fetch_bytes,
    fetch_json,
    sha256_bytes,
    sha256_file,
)


GITHUB_API = 'https://api.github.com'
MAX_REPOSITORY_BYTES = 50 * 1024 * 1024
IGNORED_NAMES = {
    '.DS_Store',
}
IGNORED_DIRECTORIES = {
    '__MACOSX',
    '__pycache__',
    '.git',
}


def parse_github_repository(value):
    """Return owner, repository, and optional ref from common GitHub forms."""
    raw = str(value or '').strip()

    if not raw:
        raise ValueError('GitHub repository is required')

    if '://' not in raw:
        parts = [part for part in raw.strip('/').split('/') if part]

        if len(parts) != 2:
            raise ValueError(
                'Use owner/repository or a GitHub repository URL'
            )

        owner, repository = parts
        ref = ''
    else:
        parsed = parse.urlparse(raw)

        if parsed.netloc.lower() not in ('github.com', 'www.github.com'):
            raise ValueError('Only github.com repository URLs are supported')

        parts = [part for part in parsed.path.split('/') if part]

        if len(parts) < 2:
            raise ValueError('GitHub URL does not identify a repository')

        owner = parts[0]
        repository = parts[1]
        ref = ''

        if len(parts) >= 4 and parts[2] == 'tree':
            ref = '/'.join(parts[3:])
        elif len(parts) > 2:
            raise ValueError(
                'Use a repository URL or a /tree/<branch> URL'
            )

    if repository.endswith('.git'):
        repository = repository[:-4]

    valid = re.compile(r'^[A-Za-z0-9_.-]+$')

    if not valid.match(owner) or not valid.match(repository):
        raise ValueError('Invalid GitHub owner or repository name')

    return owner, repository, ref


def inspect_github(repository, ref=None):
    """Resolve repository metadata and a ref to one exact commit."""
    owner, repo, url_ref = parse_github_repository(repository)
    requested_ref = str(ref or url_ref or '').strip()

    repo_url = '{}/repos/{}/{}'.format(
        GITHUB_API,
        parse.quote(owner, safe=''),
        parse.quote(repo, safe=''),
    )
    metadata = fetch_json(repo_url)

    default_branch = metadata.get('default_branch') or 'main'
    resolved_ref = requested_ref or default_branch

    commit_url = '{}/commits/{}'.format(
        repo_url,
        parse.quote(resolved_ref, safe=''),
    )
    commit = fetch_json(commit_url)
    commit_sha = commit.get('sha') or ''

    if not commit_sha:
        raise PipistaError(
            'GitHub did not return a commit for {}'.format(resolved_ref)
        )

    archive_url = '{}/zipball/{}'.format(repo_url, commit_sha)
    license_info = metadata.get('license') or {}

    return {
        'source': 'github',
        'owner': metadata.get('owner', {}).get('login') or owner,
        'repository': metadata.get('name') or repo,
        'full_name': metadata.get('full_name') or '{}/{}'.format(
            owner,
            repo,
        ),
        'description': metadata.get('description') or '',
        'html_url': metadata.get('html_url') or '',
        'default_branch': default_branch,
        'requested_ref': resolved_ref,
        'commit_sha': commit_sha,
        'archive_url': archive_url,
        'license': license_info.get('spdx_id') or '',
        'stars': metadata.get('stargazers_count') or 0,
        'private': bool(metadata.get('private')),
    }


def _safe_folder_name(value):
    name = re.sub(r'[^A-Za-z0-9_. -]+', '-', str(value or '')).strip()

    if name in ('', '.', '..'):
        raise ValueError('Invalid destination folder name')

    return name


def _single_archive_root(directory):
    names = [
        name for name in os.listdir(directory)
        if name not in IGNORED_DIRECTORIES
    ]

    if len(names) == 1:
        candidate = os.path.join(directory, names[0])

        if os.path.isdir(candidate):
            return candidate

    return directory


def _iter_project_files(directory):
    for root, dirs, files in os.walk(directory):
        dirs[:] = [
            name for name in dirs
            if name not in IGNORED_DIRECTORIES
        ]

        for filename in files:
            if filename in IGNORED_NAMES:
                continue

            path = os.path.join(root, filename)
            relative = os.path.relpath(path, directory).replace(os.sep, '/')
            yield relative, path


def _project_analysis(directory):
    python_files = []
    native_files = []
    entrypoints = []

    for relative, _path in _iter_project_files(directory):
        lower = relative.lower()

        if lower.endswith('.py'):
            python_files.append(relative)

        if lower.endswith(('.so', '.dylib', '.dll', '.pyd')):
            native_files.append(relative)

        if relative in (
            'main.py',
            'app.py',
            'run.py',
            'setup.py',
        ):
            entrypoints.append(relative)

    return {
        'python_files': sorted(python_files),
        'native_files': sorted(native_files),
        'entrypoints': sorted(entrypoints),
        'appears_python': bool(python_files),
        'pythonista_compatible': bool(python_files) and not native_files,
    }


class GitHubProjectManager:
    def __init__(self, projects_dir=None, state_dir=None):
        documents = os.path.expanduser('~/Documents')

        self.projects_dir = os.path.abspath(
            projects_dir
            or os.path.join(documents, 'Pipista Projects')
        )
        self.state_dir = os.path.abspath(
            state_dir
            or os.path.join(documents, '.pipista')
        )
        self.staging_dir = os.path.join(
            self.state_dir,
            'github-staging',
        )
        self.database_path = os.path.join(
            self.state_dir,
            'projects.json',
        )

        os.makedirs(self.projects_dir, exist_ok=True)
        os.makedirs(self.staging_dir, exist_ok=True)

    def inspect(self, repository, ref=None):
        return inspect_github(repository, ref=ref)

    def installed(self):
        database = _load_json(self.database_path, {})

        return [
            database[key]
            for key in sorted(database)
        ]

    def _key(self, full_name):
        return str(full_name or '').strip().lower()

    def _destination(self, folder_name):
        safe_name = _safe_folder_name(folder_name)
        destination = os.path.abspath(
            os.path.join(self.projects_dir, safe_name)
        )

        if os.path.commonpath(
            [self.projects_dir, destination]
        ) != self.projects_dir:
            raise PipistaError('Project destination escapes project root')

        return destination

    def install(self, repository, ref=None, folder_name=None):
        candidate = self.inspect(repository, ref=ref)

        if candidate['private']:
            raise PipistaError(
                'Private repository authentication is not yet enabled'
            )

        key = self._key(candidate['full_name'])
        database = _load_json(self.database_path, {})

        if key in database:
            raise InstallConflictError(
                '{} is already managed by Pipista'.format(
                    candidate['full_name']
                )
            )

        chosen_folder = folder_name or candidate['repository']
        destination = self._destination(chosen_folder)

        if os.path.lexists(destination):
            raise InstallConflictError(
                'Destination already exists: {}'.format(destination)
            )

        archive = fetch_bytes(
            candidate['archive_url'],
            timeout=45,
            maximum=MAX_REPOSITORY_BYTES,
        )
        archive_hash = sha256_bytes(archive)

        stage = os.path.join(
            self.staging_dir,
            uuid.uuid4().hex,
        )
        extracted = os.path.join(stage, 'archive')
        os.makedirs(extracted)

        try:
            extract_archive(
                archive,
                candidate['repository'] + '.zip',
                extracted,
            )
            project_root = _single_archive_root(extracted)
            analysis = _project_analysis(project_root)

            if not analysis['appears_python']:
                raise PipistaError(
                    'Repository does not appear to contain a Python project'
                )

            shutil.copytree(
                project_root,
                destination,
                ignore=shutil.ignore_patterns(
                    '__pycache__',
                    '*.pyc',
                    '*.pyo',
                    '.DS_Store',
                    '__MACOSX',
                    '.git',
                ),
            )

            file_hashes = {}

            for relative, path in _iter_project_files(destination):
                file_hashes[relative] = sha256_file(path)

            record = {
                'source': 'github',
                'owner': candidate['owner'],
                'repository': candidate['repository'],
                'full_name': candidate['full_name'],
                'description': candidate['description'],
                'html_url': candidate['html_url'],
                'default_branch': candidate['default_branch'],
                'requested_ref': candidate['requested_ref'],
                'commit_sha': candidate['commit_sha'],
                'license': candidate['license'],
                'stars': candidate['stars'],
                'archive_sha256': archive_hash,
                'folder_name': os.path.basename(destination),
                'destination': destination,
                'installed_at': time.time(),
                'analysis': analysis,
                'files': file_hashes,
            }

            database[key] = record
            _atomic_json(self.database_path, database)

            return record

        except BaseException:
            if os.path.isdir(destination):
                shutil.rmtree(destination)
            raise

        finally:
            if os.path.isdir(stage):
                shutil.rmtree(stage)

    def get(self, repository):
        owner, repo, _ref = parse_github_repository(repository)
        key = self._key('{}/{}'.format(owner, repo))
        database = _load_json(self.database_path, {})

        record = database.get(key)

        if record is None:
            for value in database.values():
                if (
                    value.get('owner', '').lower() == owner.lower()
                    and value.get('repository', '').lower() == repo.lower()
                ):
                    return value

            raise PipistaError(
                '{} is not managed by Pipista'.format(repository)
            )

        return record

    def status(self, repository):
        record = self.get(repository)
        destination = self._destination(record['folder_name'])
        expected = record.get('files') or {}

        modified = []
        missing = []

        for relative, expected_hash in expected.items():
            path = os.path.join(
                destination,
                *relative.split('/'),
            )

            if not os.path.isfile(path):
                missing.append(relative)
            elif sha256_file(path) != expected_hash:
                modified.append(relative)

        current = {
            relative
            for relative, _path in _iter_project_files(destination)
        } if os.path.isdir(destination) else set()

        untracked = sorted(current.difference(expected))

        return {
            'full_name': record['full_name'],
            'destination': destination,
            'exists': os.path.isdir(destination),
            'clean': not modified and not missing and not untracked,
            'modified': sorted(modified),
            'missing': sorted(missing),
            'untracked': untracked,
            'commit_sha': record.get('commit_sha') or '',
            'requested_ref': record.get('requested_ref') or '',
        }

    def uninstall(self, repository, force=False):
        record = self.get(repository)
        status = self.status(repository)

        risky = []
        risky.extend(
            'modified:' + path
            for path in status['modified']
        )
        risky.extend(
            'untracked:' + path
            for path in status['untracked']
        )

        if risky and not force:
            raise ModifiedFilesError(risky)

        destination = self._destination(record['folder_name'])

        if os.path.isdir(destination):
            shutil.rmtree(destination)

        database = _load_json(self.database_path, {})
        key = self._key(record['full_name'])
        database.pop(key, None)
        _atomic_json(self.database_path, database)

        return {
            'full_name': record['full_name'],
            'destination': destination,
            'forced': bool(force),
            'removed_files': len(record.get('files') or {}),
        }
