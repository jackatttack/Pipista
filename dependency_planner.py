# -*- coding: utf-8 -*-
"""Read-only dependency planning for Pipista.

The planner evaluates PyPI Requires-Dist entries, discovers packages already
available to Pythonista, and produces a dependency-first installation plan.
It never installs or removes files.
"""

import importlib.util
import platform
import re
import sys

from pipista_engine import (
    _atomic_json,
    _load_json,
    canonical_name,
)


try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    PACKAGING_AVAILABLE = True
except Exception:
    default_environment = None
    Requirement = None
    SpecifierSet = None
    Version = None
    PACKAGING_AVAILABLE = False


MAX_PLAN_PACKAGES = 50
MAX_PLAN_DEPTH = 12


IMPORT_OVERRIDES = {
    'beautifulsoup4': 'bs4',
    'cachecontrol': 'cachecontrol',
    'discord-py': 'discord',
    'google-auth': 'google.auth',
    'jsonpickle': 'jsonpickle',
    'pillow': 'PIL',
    'pyyaml': 'yaml',
    'python-dateutil': 'dateutil',
    'scikit-learn': 'sklearn',
    'typing-extensions': 'typing_extensions',
}


class DependencyPlanError(Exception):
    """Raised when Pipista cannot safely create a dependency plan."""


def _fallback_marker_applies(marker):
    marker = str(marker or '').strip()
    if not marker:
        return True

    if re.search(r'\bextra\b', marker, flags=re.I):
        return False

    environment = {
        'python_version': '{}.{}'.format(
            sys.version_info[0],
            sys.version_info[1],
        ),
        'python_full_version': platform.python_version(),
        'sys_platform': sys.platform,
        'platform_system': platform.system(),
    }

    clauses = re.split(r'\s+and\s+', marker, flags=re.I)

    for clause in clauses:
        clause = clause.strip().strip('() ')
        match = re.match(
            r'''^(python_version|python_full_version|sys_platform|platform_system)
                 \s*(==|!=|<=|>=|<|>)\s*["']([^"']+)["']$''',
            clause,
            flags=re.I | re.X,
        )
        if not match:
            raise DependencyPlanError(
                'Cannot safely evaluate dependency marker without '
                'the packaging module: {}'.format(marker)
            )

        key, operator, expected = match.groups()
        actual = environment[key.lower()]

        if key.lower().startswith('python_'):
            actual_value = tuple(
                int(part) for part in actual.split('.') if part.isdigit()
            )
            expected_value = tuple(
                int(part) for part in expected.split('.') if part.isdigit()
            )
        else:
            actual_value = actual.lower()
            expected_value = expected.lower()

        comparisons = {
            '==': actual_value == expected_value,
            '!=': actual_value != expected_value,
            '<': actual_value < expected_value,
            '<=': actual_value <= expected_value,
            '>': actual_value > expected_value,
            '>=': actual_value >= expected_value,
        }

        if not comparisons[operator]:
            return False

    return True


def parse_requirement(raw):
    raw = str(raw or '').strip()
    if not raw:
        raise DependencyPlanError('Empty dependency declaration')

    if PACKAGING_AVAILABLE:
        try:
            requirement = Requirement(raw)
            environment = default_environment()
            environment['extra'] = ''

            applies = (
                requirement.marker is None
                or requirement.marker.evaluate(environment)
            )

            return {
                'raw': raw,
                'name': requirement.name,
                'canonical_name': canonical_name(requirement.name),
                'specifier': str(requirement.specifier),
                'marker': (
                    str(requirement.marker)
                    if requirement.marker is not None
                    else ''
                ),
                'extras': sorted(requirement.extras),
                'url': requirement.url or '',
                'applies': bool(applies),
            }
        except Exception as exc:
            raise DependencyPlanError(
                'Invalid dependency declaration {!r}: {}'.format(raw, exc)
            )

    declaration, separator, marker = raw.partition(';')
    declaration = declaration.strip()
    marker = marker.strip() if separator else ''

    if '@' in declaration:
        left, url = declaration.split('@', 1)
        direct_url = url.strip()
    else:
        left = declaration
        direct_url = ''

    match = re.match(
        r'^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(.*)$',
        left.strip(),
    )
    if not match:
        raise DependencyPlanError(
            'Cannot parse dependency declaration {!r}'.format(raw)
        )

    name, specifier = match.groups()

    return {
        'raw': raw,
        'name': name,
        'canonical_name': canonical_name(name),
        'specifier': specifier.strip(),
        'marker': marker,
        'extras': [],
        'url': direct_url,
        'applies': _fallback_marker_applies(marker),
    }


def _version_matches(version, specifier):
    version = str(version or '').strip()
    specifier = str(specifier or '').strip()

    if not version or not specifier:
        return True

    if not PACKAGING_AVAILABLE:
        return None

    try:
        return Version(version) in SpecifierSet(specifier)
    except Exception:
        return None


def _python_matches(specifier):
    specifier = str(specifier or '').strip()
    if not specifier:
        return True

    if not PACKAGING_AVAILABLE:
        return None

    try:
        current = Version(platform.python_version())
        return current in SpecifierSet(specifier)
    except Exception:
        return None


def import_candidates(distribution_name):
    key = canonical_name(distribution_name)
    candidates = []

    override = IMPORT_OVERRIDES.get(key)
    if override:
        candidates.append(override)

    candidates.extend([
        key.replace('-', '_'),
        str(distribution_name or '').replace('-', '_'),
    ])

    result = []
    seen = set()

    for candidate in candidates:
        candidate = str(candidate or '').strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)

    return result


def find_external_import(distribution_name):
    for import_name in import_candidates(distribution_name):
        try:
            if importlib.util.find_spec(import_name) is not None:
                return import_name
        except Exception:
            continue

    return ''


def _record_blocker(blockers, package, message, requirement=''):
    item = {
        'package': package,
        'message': message,
        'requirement': requirement,
    }

    if item not in blockers:
        blockers.append(item)


def build_dependency_plan(
    package,
    manager,
    inspect_func=None,
    external_checker=None,
    max_packages=MAX_PLAN_PACKAGES,
    max_depth=MAX_PLAN_DEPTH,
):
    """Return a read-only dependency plan for a PyPI package."""

    inspect_func = inspect_func or manager.inspect_pypi
    external_checker = external_checker or find_external_import

    managed_records = {
        canonical_name(record.get('name')): record
        for record in manager.installed()
        if record.get('name')
    }

    nodes = {}
    order = []
    visiting = set()
    skipped = []
    blockers = []
    edges = []

    def append_order(key):
        if key not in order:
            order.append(key)

    def resolve(name, parsed=None, parent='', depth=0, is_root=False):
        if depth > max_depth:
            raise DependencyPlanError(
                'Dependency graph exceeded {} levels'.format(max_depth)
            )

        key = canonical_name(name)
        requirement_raw = parsed.get('raw') if parsed else str(name)
        specifier = parsed.get('specifier') if parsed else ''

        if key in nodes:
            node = nodes[key]
            if parent and parent not in node['required_by']:
                node['required_by'].append(parent)

            matches = _version_matches(
                node.get('version'),
                specifier,
            )
            if matches is False:
                _record_blocker(
                    blockers,
                    node.get('name') or name,
                    '{} does not satisfy {}'.format(
                        node.get('version') or 'unknown version',
                        specifier,
                    ),
                    requirement_raw,
                )

            if key in visiting:
                edges.append({
                    'parent': parent,
                    'child': key,
                    'requirement': requirement_raw,
                    'cycle': True,
                })

            return key

        if len(nodes) >= max_packages:
            raise DependencyPlanError(
                'Dependency graph exceeded {} packages'.format(max_packages)
            )

        required_by = [parent] if parent else []
        managed = managed_records.get(key)

        if managed is not None:
            node = {
                'name': managed.get('name') or name,
                'canonical_name': key,
                'version': managed.get('version') or '',
                'kind': managed.get('artifact_kind') or '',
                'status': 'managed',
                'reason': 'Already managed by Pipista',
                'import_name': managed.get('import_name') or '',
                'required_by': required_by,
                'dependencies': [],
                'candidate': None,
            }
            nodes[key] = node

            matches = _version_matches(node['version'], specifier)
            if matches is False:
                node['status'] = 'blocked'
                node['reason'] = (
                    'Managed version {} does not satisfy {}'.format(
                        node['version'] or 'unknown',
                        specifier,
                    )
                )
                _record_blocker(
                    blockers,
                    node['name'],
                    node['reason'],
                    requirement_raw,
                )

            append_order(key)
            return key

        if not is_root:
            external_import = external_checker(name)
            if external_import:
                node = {
                    'name': name,
                    'canonical_name': key,
                    'version': '',
                    'kind': 'environment',
                    'status': 'external',
                    'reason': (
                        'Available in Pythonista as {} '
                        '(version not verified)'
                    ).format(external_import),
                    'import_name': external_import,
                    'required_by': required_by,
                    'dependencies': [],
                    'candidate': None,
                }
                nodes[key] = node
                append_order(key)
                return key

        try:
            candidate = inspect_func(name)
        except Exception as exc:
            node = {
                'name': name,
                'canonical_name': key,
                'version': '',
                'kind': '',
                'status': 'blocked',
                'reason': 'PyPI inspection failed: {}'.format(exc),
                'import_name': '',
                'required_by': required_by,
                'dependencies': [],
                'candidate': None,
            }
            nodes[key] = node
            append_order(key)
            _record_blocker(
                blockers,
                name,
                node['reason'],
                requirement_raw,
            )
            return key

        actual_name = candidate.get('name') or name
        actual_key = canonical_name(actual_name)
        if actual_key != key and actual_key not in nodes:
            key = actual_key

        node = {
            'name': actual_name,
            'canonical_name': key,
            'version': candidate.get('version') or '',
            'kind': candidate.get('kind') or '',
            'status': 'install',
            'reason': 'Will be installed from PyPI',
            'import_name': '',
            'required_by': required_by,
            'dependencies': [],
            'candidate': candidate,
        }
        nodes[key] = node

        matches = _version_matches(node['version'], specifier)
        if matches is False:
            node['status'] = 'blocked'
            node['reason'] = '{} does not satisfy {}'.format(
                node['version'] or 'unknown version',
                specifier,
            )
            _record_blocker(
                blockers,
                node['name'],
                node['reason'],
                requirement_raw,
            )

        python_matches = _python_matches(
            candidate.get('requires_python') or ''
        )
        if python_matches is False:
            node['status'] = 'blocked'
            node['reason'] = (
                'Requires Python {}; this device runs {}'.format(
                    candidate.get('requires_python'),
                    platform.python_version(),
                )
            )
            _record_blocker(
                blockers,
                node['name'],
                node['reason'],
                requirement_raw,
            )

        visiting.add(key)

        for raw_dependency in candidate.get('dependencies') or []:
            try:
                dependency = parse_requirement(raw_dependency)
            except DependencyPlanError as exc:
                _record_blocker(
                    blockers,
                    node['name'],
                    str(exc),
                    raw_dependency,
                )
                continue

            if not dependency['applies']:
                skipped.append({
                    'parent': key,
                    'requirement': raw_dependency,
                    'reason': 'Marker or extra does not apply',
                })
                continue

            if dependency['url']:
                message = (
                    'Direct URL dependencies are not automatically installed'
                )
                _record_blocker(
                    blockers,
                    dependency['name'],
                    message,
                    raw_dependency,
                )
                continue

            child_key = resolve(
                dependency['name'],
                parsed=dependency,
                parent=key,
                depth=depth + 1,
                is_root=False,
            )

            if child_key not in node['dependencies']:
                node['dependencies'].append(child_key)

            edges.append({
                'parent': key,
                'child': child_key,
                'requirement': raw_dependency,
                'cycle': child_key in visiting,
            })

        visiting.discard(key)
        append_order(key)
        return key

    root_key = resolve(
        package,
        parent='',
        depth=0,
        is_root=True,
    )

    items = [
        nodes[key]
        for key in order
        if key in nodes
    ]

    return {
        'root': root_key,
        'items': items,
        'install': [
            item for item in items
            if item.get('status') == 'install'
        ],
        'satisfied': [
            item for item in items
            if item.get('status') in ('managed', 'external')
        ],
        'blocked': [
            item for item in items
            if item.get('status') == 'blocked'
        ],
        'skipped': skipped,
        'blockers': blockers,
        'edges': edges,
        'packaging_available': PACKAGING_AVAILABLE,
        'can_install': not blockers,
    }


class DependencyInstallError(Exception):
    """Raised when a dependency transaction cannot complete cleanly."""


def _annotate_dependency_graph(
    manager,
    plan,
    newly_installed=None,
):
    database = _load_json(manager.database_path, {})
    newly_installed = newly_installed or []
    newly_installed_keys = {
        canonical_name(
            record.get('canonical_name')
            or record.get('name')
        )
        for record in newly_installed
    }
    statuses = {
        item.get('canonical_name'): item.get('status')
        for item in plan.get('items') or []
        if item.get('canonical_name')
    }

    for edge in plan.get('edges') or []:
        parent = canonical_name(edge.get('parent'))
        child = canonical_name(edge.get('child'))

        if not parent or not child:
            continue

        parent_record = database.get(parent)
        child_record = database.get(child)

        if parent_record is not None:
            resolved = list(
                parent_record.get('resolved_dependencies') or []
            )
            if child not in resolved:
                resolved.append(child)

            dependency_status = dict(
                parent_record.get('dependency_status') or {}
            )
            dependency_status[child] = statuses.get(child) or 'unknown'

            parent_record['resolved_dependencies'] = sorted(resolved)
            parent_record['dependency_status'] = dependency_status

        if child_record is not None:
            required_by = list(
                child_record.get('required_by') or []
            )
            if parent not in required_by:
                required_by.append(parent)

            child_record['required_by'] = sorted(required_by)

    root_key = canonical_name(plan.get('root'))
    for key, record in database.items():
        if key == root_key:
            record['install_reason'] = 'direct'
        elif (
            key in newly_installed_keys
            and record.get('required_by')
        ):
            record['install_reason'] = 'dependency'
        elif (
            record.get('required_by')
            and not record.get('install_reason')
        ):
            record['install_reason'] = 'dependency'

    _atomic_json(manager.database_path, database)
    return database


def execute_dependency_plan(plan, manager, progress=None):
    """Install a completed plan and roll back all new packages on failure."""

    blockers = plan.get('blockers') or []
    if blockers:
        raise DependencyInstallError(
            'Dependency plan has {} blocker(s)'.format(len(blockers))
        )

    install_items = list(plan.get('install') or [])
    newly_installed = []
    rollback_errors = []

    try:
        total = len(install_items)

        for index, item in enumerate(install_items, 1):
            if progress is not None:
                progress(index, total, item)

            record = manager.install_pypi(item.get('name'))
            newly_installed.append(record)

        database = _annotate_dependency_graph(
            manager,
            plan,
            newly_installed=newly_installed,
        )
        root_key = canonical_name(plan.get('root'))
        root_record = database.get(root_key)

        if root_record is None and newly_installed:
            root_record = newly_installed[-1]

        return {
            'root_record': root_record or {},
            'installed': newly_installed,
            'installed_count': len(newly_installed),
            'satisfied_count': len(plan.get('satisfied') or []),
            'plan': plan,
        }

    except BaseException as original_error:
        for record in reversed(newly_installed):
            name = record.get('name') or record.get('canonical_name')

            try:
                manager.uninstall(name, force=True)
            except BaseException as rollback_error:
                rollback_errors.append(
                    '{}: {}'.format(name, rollback_error)
                )

        if rollback_errors:
            raise DependencyInstallError(
                'Install failed: {}. Rollback also failed: {}'.format(
                    original_error,
                    '; '.join(rollback_errors),
                )
            )

        raise


def format_plan(plan):
    labels = {
        'install': 'INSTALL',
        'managed': 'MANAGED',
        'external': 'AVAILABLE',
        'blocked': 'BLOCKED',
    }
    lines = []

    for item in plan.get('items') or []:
        label = labels.get(item.get('status'), 'UNKNOWN')
        version = item.get('version') or ''
        suffix = ' {}'.format(version) if version else ''

        lines.append(
            '{}: {}{} — {}'.format(
                label,
                item.get('name') or '',
                suffix,
                item.get('reason') or '',
            )
        )

    if plan.get('skipped'):
        lines.append(
            'SKIPPED: {} inactive marker/extra requirement(s)'.format(
                len(plan['skipped'])
            )
        )

    if plan.get('blockers'):
        lines.append('BLOCKERS:')
        for blocker in plan['blockers']:
            lines.append(
                '- {}: {}'.format(
                    blocker.get('package') or '',
                    blocker.get('message') or '',
                )
            )

    return '\n'.join(lines)