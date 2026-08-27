# -*- coding: utf-8 -*-
"""Compact, searchable local index of every registered PyPI project."""

import gzip
import html
import os
import re
import sqlite3
import time
from urllib import request


INDEX_URL = 'https://pypi.org/simple/'
INDEX_ACCEPT = 'application/vnd.pypi.simple.v1+html'
USER_AGENT = 'Pipista-PyPI-Index/0.1'
LINK_PATTERN = re.compile(r'>([^<]+)</a>', re.I)
NORMALIZE_PATTERN = re.compile(r'[-_.]+')


class PyPIIndexError(Exception):
    pass


def canonical_name(value):
    return NORMALIZE_PATTERN.sub(
        '-',
        str(value or ''),
    ).lower().strip('-')


class PyPIIndex:
    def __init__(self, state_dir=None):
        if state_dir is None:
            state_dir = os.path.join(
                os.path.expanduser('~/Documents'),
                '.pipista',
            )

        self.state_dir = os.path.abspath(state_dir)
        self.cache_dir = os.path.join(
            self.state_dir,
            'cache',
        )
        self.database_path = os.path.join(
            self.cache_dir,
            'pypi-index.sqlite3',
        )
        os.makedirs(self.cache_dir, exist_ok=True)

    def _request(self, method='GET'):
        req = request.Request(INDEX_URL, method=method)
        req.add_header('User-Agent', USER_AGENT)
        req.add_header('Accept', INDEX_ACCEPT)
        req.add_header('Accept-Encoding', 'gzip')
        return req

    def remote_status(self):
        try:
            with request.urlopen(
                self._request('HEAD'),
                timeout=30,
            ) as response:
                return {
                    'serial': response.headers.get(
                        'X-PyPI-Last-Serial'
                    ) or '',
                    'etag': response.headers.get('ETag') or '',
                    'compressed_bytes': int(
                        response.headers.get('Content-Length')
                        or 0
                    ),
                }
        except Exception as exc:
            raise PyPIIndexError(
                'Could not check the PyPI index: {}'.format(exc)
            )

    def _metadata(self, connection):
        try:
            rows = connection.execute(
                'SELECT key, value FROM metadata'
            ).fetchall()
        except sqlite3.Error:
            return {}

        return {
            str(key): str(value)
            for key, value in rows
        }

    def status(self):
        if not os.path.isfile(self.database_path):
            return {
                'ready': False,
                'count': 0,
                'serial': '',
                'etag': '',
                'updated_at': 0.0,
                'database_bytes': 0,
            }

        try:
            connection = sqlite3.connect(self.database_path)
            metadata = self._metadata(connection)
            count = connection.execute(
                'SELECT COUNT(*) FROM projects'
            ).fetchone()[0]
            connection.close()
        except Exception:
            return {
                'ready': False,
                'count': 0,
                'serial': '',
                'etag': '',
                'updated_at': 0.0,
                'database_bytes': 0,
            }

        return {
            'ready': bool(count),
            'count': int(count),
            'serial': metadata.get('serial') or '',
            'etag': metadata.get('etag') or '',
            'updated_at': float(
                metadata.get('updated_at') or 0.0
            ),
            'database_bytes': os.path.getsize(
                self.database_path
            ),
        }

    def needs_refresh(self):
        local = self.status()

        if not local['ready']:
            return True

        remote = self.remote_status()

        return (
            remote.get('serial')
            and remote.get('serial') != local.get('serial')
        )

    def sync(self, progress=None, force=False):
        local = self.status()
        remote = self.remote_status()

        if (
            local['ready']
            and not force
            and remote.get('serial') == local.get('serial')
        ):
            return local

        temporary = self.database_path + '.building'

        if os.path.isfile(temporary):
            os.remove(temporary)

        connection = sqlite3.connect(temporary)

        try:
            connection.execute('PRAGMA journal_mode=OFF')
            connection.execute('PRAGMA synchronous=OFF')
            connection.execute('PRAGMA temp_store=MEMORY')
            connection.execute(
                'CREATE TABLE projects ('
                'normalized TEXT NOT NULL, '
                'name TEXT NOT NULL'
                ')'
            )
            connection.execute(
                'CREATE TABLE metadata ('
                'key TEXT PRIMARY KEY, '
                'value TEXT NOT NULL'
                ')'
            )

            req = self._request('GET')
            count = 0
            batch = []
            response_serial = remote.get('serial') or ''
            response_etag = remote.get('etag') or ''

            with request.urlopen(req, timeout=60) as response:
                response_serial = (
                    response.headers.get('X-PyPI-Last-Serial')
                    or response_serial
                )
                response_etag = (
                    response.headers.get('ETag')
                    or response_etag
                )

                if (
                    response.headers.get(
                        'Content-Encoding',
                        '',
                    ).lower() == 'gzip'
                ):
                    stream = gzip.GzipFile(fileobj=response)
                else:
                    stream = response

                for raw_line in stream:
                    line = raw_line.decode(
                        'utf-8',
                        'replace',
                    )

                    for match in LINK_PATTERN.finditer(line):
                        name = html.unescape(
                            match.group(1)
                        ).strip()

                        if not name:
                            continue

                        normalized = canonical_name(name)

                        if not normalized:
                            continue

                        batch.append((normalized, name))
                        count += 1

                        if len(batch) >= 5000:
                            connection.executemany(
                                'INSERT INTO projects '
                                '(normalized, name) '
                                'VALUES (?, ?)',
                                batch,
                            )
                            batch = []

                        if (
                            progress is not None
                            and count % 10000 == 0
                        ):
                            progress(count)

                if batch:
                    connection.executemany(
                        'INSERT INTO projects '
                        '(normalized, name) '
                        'VALUES (?, ?)',
                        batch,
                    )

            if count == 0:
                raise PyPIIndexError(
                    'PyPI returned an empty project index'
                )

            if progress is not None:
                progress(count)

            connection.execute(
                'CREATE INDEX projects_normalized '
                'ON projects(normalized)'
            )

            values = {
                'serial': response_serial,
                'etag': response_etag,
                'updated_at': str(time.time()),
                'count': str(count),
            }

            connection.executemany(
                'INSERT INTO metadata (key, value) '
                'VALUES (?, ?)',
                sorted(values.items()),
            )
            connection.commit()
            connection.close()
            connection = None

            os.replace(temporary, self.database_path)

        except BaseException:
            if connection is not None:
                connection.close()

            if os.path.isfile(temporary):
                os.remove(temporary)

            raise

        return self.status()

    def search(self, query, limit=40):
        query = canonical_name(query)

        if not query or not self.status()['ready']:
            return []

        lower = query
        upper = query + '\uffff'

        connection = sqlite3.connect(self.database_path)

        try:
            rows = connection.execute(
                'SELECT name FROM projects '
                'WHERE normalized >= ? AND normalized < ? '
                'ORDER BY normalized '
                'LIMIT ?',
                (lower, upper, int(limit)),
            ).fetchall()
        finally:
            connection.close()

        return [row[0] for row in rows]