# -*- coding: utf-8 -*-
"""
Install Pipista into Pythonista.

This installer downloads the public GitHub repository, extracts only Pipista's
explicit application-file allowlist, compiles every Python file, stages the
installation, backs up an existing copy and then opens Pipista.py.
"""

from __future__ import print_function

import io
import os
import shutil
import stat
import time
import uuid
import zipfile
from urllib.request import Request, urlopen


ARCHIVE_URL = (
    'https://github.com/jackatttack/Pipista/'
    'archive/refs/heads/main.zip'
)

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024

APP_FILES = (
    'Pipista.py',
    'Pipista_Panel.py',
    'catalog.py',
    'dependency_planner.py',
    'environment_inventory.py',
    'github_projects.py',
    'pipista_app.py',
    'pipista_app_polished.py',
    'pipista_engine.py',
    'pipista_version.py',
    'pypi_index.py',
)

DOCUMENT_FILES = (
    'README.md',
    'LICENSE',
    'CHANGELOG.md',
    'SECURITY.md',
)

INSTALL_FILES = APP_FILES + DOCUMENT_FILES


def documents_path():
    """Return the current Pythonista user's Documents directory."""
    return os.path.abspath(os.path.expanduser('~/Documents'))


def target_path():
    return os.path.join(documents_path(), 'Pipista')


def state_path():
    return os.path.join(documents_path(), '.pipista')


def _download():
    request = Request(
        ARCHIVE_URL,
        headers={'User-Agent': 'Pipista-Installer/0.1'},
    )

    with urlopen(request, timeout=45) as response:
        declared = response.headers.get('Content-Length')

        if declared:
            try:
                if int(declared) > MAX_ARCHIVE_BYTES:
                    raise RuntimeError(
                        'Repository archive is larger than the installer limit'
                    )
            except ValueError:
                pass

        data = response.read(MAX_ARCHIVE_BYTES + 1)

    if len(data) > MAX_ARCHIVE_BYTES:
        raise RuntimeError(
            'Repository archive is larger than the installer limit'
        )

    return data


def _member_mode(member):
    return (member.external_attr >> 16) & 0xFFFF


def _archive_files(data):
    selected = {}

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except Exception as exc:
        raise RuntimeError(
            'Downloaded repository is not a valid ZIP archive: {}'.format(exc)
        )

    with archive:
        for member in archive.infolist():
            name = member.filename.replace('\\', '/')
            parts = [part for part in name.split('/') if part]

            if member.is_dir():
                continue

            if len(parts) != 2:
                continue

            relative = parts[1]

            if relative not in INSTALL_FILES:
                continue

            if relative in selected:
                raise RuntimeError(
                    'Repository archive contains duplicate file: {}'.format(
                        relative
                    )
                )

            if stat.S_ISLNK(_member_mode(member)):
                raise RuntimeError(
                    'Repository archive contains a link: {}'.format(relative)
                )

            if member.file_size > MAX_FILE_BYTES:
                raise RuntimeError(
                    'Repository file is too large: {}'.format(relative)
                )

            raw = archive.read(member)

            if len(raw) != member.file_size:
                raise RuntimeError(
                    'Repository file size changed while reading: {}'.format(
                        relative
                    )
                )

            selected[relative] = raw

    missing = [
        relative
        for relative in INSTALL_FILES
        if relative not in selected
    ]

    if missing:
        raise RuntimeError(
            'Repository is missing required release files: {}'.format(
                ', '.join(missing)
            )
        )

    return selected


def _write_staged_application(stage, files):
    application = os.path.join(stage, 'Pipista')
    os.makedirs(application)

    for relative in INSTALL_FILES:
        destination = os.path.join(application, relative)

        with open(destination, 'wb') as output:
            output.write(files[relative])

    for relative in APP_FILES:
        source = os.path.join(application, relative)

        try:
            with open(source, 'rb') as stream:
                code = stream.read()
            compile(code, relative, 'exec')
        except Exception as exc:
            raise RuntimeError(
                '{} did not compile: {}'.format(relative, exc)
            )

    return application


def _backup_name(backups):
    stamp = time.strftime('%Y%m%d-%H%M%S')
    candidate = os.path.join(backups, 'Pipista-' + stamp)
    suffix = 1

    while os.path.exists(candidate):
        candidate = os.path.join(
            backups,
            'Pipista-{}-{}'.format(stamp, suffix),
        )
        suffix += 1

    return candidate


def install():
    documents = documents_path()
    state = state_path()
    backups = os.path.join(state, 'backups')
    staging_root = os.path.join(state, 'installer-staging')
    stage = os.path.join(staging_root, uuid.uuid4().hex)
    destination = target_path()
    backup = None

    os.makedirs(backups, exist_ok=True)
    os.makedirs(stage)

    print('Downloading Pipista...')
    data = _download()
    print('Downloaded {} bytes.'.format(len(data)))

    files = _archive_files(data)
    print('Validated {} release files.'.format(len(files)))

    staged_application = _write_staged_application(stage, files)
    print('Python source compilation passed.')

    try:
        if os.path.exists(destination):
            backup = _backup_name(backups)
            os.replace(destination, backup)
            print('Existing installation backed up to:')
            print('  ' + backup)

        os.replace(staged_application, destination)

    except BaseException:
        if os.path.exists(destination):
            shutil.rmtree(destination)

        if backup and os.path.exists(backup):
            os.replace(backup, destination)

        raise

    finally:
        if os.path.isdir(stage):
            shutil.rmtree(stage)

    launcher = os.path.join(destination, 'Pipista.py')

    print('')
    print('Pipista installed successfully.')
    print('Application:')
    print('  ' + destination)
    print('Launcher:')
    print('  ' + launcher)
    print('')
    print('Run Pipista.py for fullscreen mode.')
    print('Run Pipista_Panel.py for panel mode.')

    try:
        import editor
        editor.open_file(launcher)
    except Exception:
        pass

    return destination


if __name__ == '__main__':
    install()