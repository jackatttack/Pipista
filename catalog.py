# -*- coding: utf-8 -*-
"""Small curated catalogue for instant Pipista filtering."""

import re


CATALOG = [
    {
        'name': 'PyATEMMax',
        'description': 'Control Blackmagic Design ATEM video switchers.',
        'status': 'tested',
    },
    {
        'name': 'chardet',
        'description': 'Universal character encoding detection.',
        'status': 'tested',
    },
    {
        'name': 'attrs',
        'description': 'Declarative Python classes with less boilerplate.',
        'status': 'candidate',
    },
    {
        'name': 'boltons',
        'description': 'A collection of practical pure-Python utilities.',
        'status': 'candidate',
    },
    {
        'name': 'cachetools',
        'description': 'Extensible memoising collections and decorators.',
        'status': 'candidate',
    },
    {
        'name': 'click',
        'description': 'Composable command-line interface utilities.',
        'status': 'candidate',
    },
    {
        'name': 'cloudpickle',
        'description': 'Extended serialisation support for Python objects.',
        'status': 'candidate',
    },
    {
        'name': 'colorama',
        'description': 'Cross-platform terminal colour helpers.',
        'status': 'candidate',
    },
    {
        'name': 'decorator',
        'description': 'Helpers for creating signature-preserving decorators.',
        'status': 'candidate',
    },
    {
        'name': 'feedparser',
        'description': 'Parse RSS and Atom feeds.',
        'status': 'candidate',
    },
    {
        'name': 'humanize',
        'description': 'Human-friendly numbers, dates and file sizes.',
        'status': 'candidate',
    },
    {
        'name': 'Markdown',
        'description': 'Convert Markdown text into HTML.',
        'status': 'candidate',
    },
    {
        'name': 'more-itertools',
        'description': 'Additional building blocks for Python iteration.',
        'status': 'candidate',
    },
    {
        'name': 'packaging',
        'description': 'Python version and package metadata utilities.',
        'status': 'candidate',
    },
    {
        'name': 'pyasn1',
        'description': 'Pure-Python ASN.1 types and codecs.',
        'status': 'candidate',
    },
    {
        'name': 'python-dateutil',
        'description': 'Powerful extensions to Python date handling.',
        'status': 'candidate',
    },
    {
        'name': 'six',
        'description': 'Python compatibility utilities.',
        'status': 'candidate',
    },
    {
        'name': 'tabulate',
        'description': 'Render attractive plain-text tables.',
        'status': 'candidate',
    },
    {
        'name': 'tenacity',
        'description': 'General-purpose retrying support.',
        'status': 'candidate',
    },
    {
        'name': 'tomli',
        'description': 'A small TOML parser.',
        'status': 'candidate',
    },
    {
        'name': 'tqdm',
        'description': 'Progress bars for loops and iterables.',
        'status': 'candidate',
    },
    {
        'name': 'typing-extensions',
        'description': 'Backported and experimental typing features.',
        'status': 'candidate',
    },
    {
        'name': 'urllib3',
        'description': 'HTTP connection pooling and request utilities.',
        'status': 'candidate',
    },
]


def canonical_name(value):
    return re.sub(r'[-_.]+', '-', str(value or '')).lower().strip('-')


def catalogue_matches(query='', limit=50):
    query = str(query or '').strip().lower()

    if not query:
        tested = [
            item for item in CATALOG
            if item.get('status') == 'tested'
        ]
        others = [
            item for item in CATALOG
            if item.get('status') != 'tested'
        ]
        return (tested + others)[:limit]

    prefix = []
    contains = []

    for item in CATALOG:
        name = item['name'].lower()
        description = item.get('description', '').lower()

        if name.startswith(query):
            prefix.append(item)
        elif query in name or query in description:
            contains.append(item)

    ordered = sorted(
        prefix,
        key=lambda item: item['name'].lower(),
    )
    ordered.extend(
        sorted(
            contains,
            key=lambda item: item['name'].lower(),
        )
    )

    return ordered[:limit]