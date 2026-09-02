# -*- coding: utf-8 -*-
"""Polished Pipista interface with discovery and environment inventory."""

import os
import threading
import time

import ui
from objc_util import on_main_thread

from .catalog import (
    CATALOG,
    canonical_name,
    catalogue_matches,
)
from .environment import scan_environment
from .pypi import PyPIIndex
from .dependencies import (
    build_dependency_plan,
    execute_dependency_plan,
)
from .app_base import (
    AMBER,
    BACKGROUND,
    BORDER,
    CORAL,
    CYAN,
    GREEN,
    MUTED,
    PANEL,
    PANEL_ALT,
    TEXT,
    VIOLET,
    PipistaApp as BasePipistaApp,
    card_view,
    make_button,
    make_label,
)



@on_main_thread
def _dispatch_main(callback, *args, **kwargs):
    """Run one UI callback on Pythonista's main thread."""
    return callback(*args, **kwargs)


INPUT_TEXT = '#111827'
CONTROL_BACKGROUND = '#d5dbe6'


class PipistaApp(BasePipistaApp):
    def __init__(
        self,
        package_target=None,
        projects_dir=None,
        state_dir=None,
    ):
        self._polish_ready = False
        self._inventory_cache = None

        super().__init__(
            package_target=package_target,
            projects_dir=projects_dir,
            state_dir=state_dir,
        )

        self.search_field.text_color = INPUT_TEXT
        self.search_field.background_color = 'white'
        self.search_field.tint_color = VIOLET
        self.search_field.delegate = self

        self.tabs.background_color = CONTROL_BACKGROUND
        self.tabs.tint_color = VIOLET

        self.close_button = make_button(
            self,
            'Close',
            self._close,
            background=PANEL_ALT,
            color=TEXT,
        )

        self.installed_toggle = ui.SegmentedControl()
        self.installed_toggle.segments = [
            'Managed',
            'Environment',
        ]
        self.installed_toggle.selected_index = 0
        self.installed_toggle.background_color = CONTROL_BACKGROUND
        self.installed_toggle.tint_color = CYAN
        self.installed_toggle.action = self._installed_mode_changed
        self.installed_toggle.hidden = True
        self.add_subview(self.installed_toggle)

        self.pypi_index = PyPIIndex(state_dir=state_dir)

        self._polish_ready = True
        self._show_welcome()

    def layout(self):
        super().layout()

        pad = 16
        close_width = 78
        top = 40

        self.title_label.frame = (
            pad,
            top,
            self.width - pad * 3 - close_width,
            34,
        )
        self.close_button.frame = (
            self.width - pad - close_width,
            top,
            close_width,
            34,
        )
        self.subtitle_label.frame = (
            pad,
            top + 34,
            self.width - pad * 2,
            24,
        )
        self.tabs.frame = (
            pad,
            top + 68,
            self.width - pad * 2,
            34,
        )

        search_y = top + 114
        button_width = 92

        self.search_field.frame = (
            pad,
            search_y,
            self.width - pad * 3 - button_width,
            42,
        )
        self.search_button.frame = (
            self.width - pad - button_width,
            search_y,
            button_width,
            42,
        )
        self.installed_toggle.frame = (
            pad,
            search_y,
            self.width - pad * 2,
            42,
        )

        content_y = top + 168
        status_height = 38
        status_y = self.height - status_height - 12

        self.content.frame = (
            0,
            content_y,
            self.width,
            max(80, status_y - content_y - 8),
        )
        self.status_panel.frame = (
            pad,
            status_y,
            self.width - pad * 2,
            status_height,
        )
        self.status_dot.frame = (12, 15, 8, 8)
        self.status_label.frame = (
            30,
            4,
            self.status_panel.width - 40,
            30,
        )

    def _close(self, sender):
        self.close()

    def _run_job(self, message, operation, completion):
        if self.busy:
            return

        self._set_busy(True, message)

        def work():
            try:
                result = operation()
            except BaseException as exc:
                error_type = exc.__class__.__name__
                error_message = str(exc)
                error_text = '{}: {}'.format(
                    error_type,
                    error_message,
                )

                def deliver_error():
                    self._set_busy(False)
                    self.last_error = error_text
                    self._show_error(
                        error_type,
                        error_message,
                    )

                _dispatch_main(
                    deliver_error
                )
                return

            def deliver_success():
                self._set_busy(False)
                self.last_error = ''
                completion(result)

            _dispatch_main(
                deliver_success
            )

        thread = threading.Thread(
            target=work
        )
        thread.daemon = True
        thread.start()

    def _friendly_error(self, error_type, message):
        lower = str(message or '').lower()

        if 'wheel does not expose' in lower:
            return (
                'This distribution contains metadata but no directly '
                'importable Python package. It may be a mirror or '
                'meta-package whose real code is supplied by a dependency. '
                'Pipista does not resolve dependency chains yet.'
            )

        if 'no compatible universal wheel' in lower:
            return (
                'PyPI does not provide a universal Python wheel or a source '
                'archive that Pipista can install safely on this device.'
            )

        if 'native' in lower or 'build-language' in lower:
            return (
                'This package appears to require compiled native code or a '
                'build step that Pythonista cannot run on iOS.'
            )

        if 'overwrite unmanaged files' in lower:
            return (
                'Files with these names already exist outside Pipista’s '
                'management. Pipista refused to overwrite them.'
            )

        if 'import' in lower:
            return (
                'The files were staged, but Pythonista could not import the '
                'package successfully. Pipista rolled the installation back.'
            )

        if (
            'network' in lower
            or 'request failed' in lower
            or error_type == 'NetworkError'
        ):
            return (
                'The package service or network request failed. No partial '
                'installation was kept.'
            )

        return (
            'Pipista stopped safely and did not claim the installation '
            'succeeded. The technical detail below can help diagnose why.'
        )

    def _show_error(self, error_type, message):
        self._clear_content()
        width = max(self.width, 320)

        card = card_view(
            self.content,
            (16, 10, width - 32, 384),
        )

        make_label(
            card,
            'Installation failed',
            (18, 14, card.width - 36, 32),
            size=21,
            color=CORAL,
            bold=True,
        )
        make_label(
            card,
            self._friendly_error(error_type, message),
            (18, 56, card.width - 36, 104),
            size=14,
            color=MUTED,
            lines=0,
        )

        make_label(
            card,
            'Technical detail',
            (18, 172, card.width - 36, 24),
            size=13,
            bold=True,
        )

        detail = ui.TextView(
            frame=(18, 202, card.width - 36, 104)
        )
        detail.text = '{}: {}'.format(
            error_type,
            message,
        )
        detail.text_color = TEXT
        detail.background_color = PANEL_ALT
        detail.font = ('<System>', 12)
        detail.editable = False
        detail.corner_radius = 9
        card.add_subview(detail)

        make_button(
            card,
            'Back to package',
            self._restore_after_error,
            frame=(18, 322, card.width - 36, 44),
            background=PANEL_ALT,
            color=CYAN,
        )

        self.content.content_size = (
            width,
            410,
        )
        self._set_status(
            'Installation failed — details shown above',
            'error',
        )

    def _restore_after_error(self, sender):
        if self.selected_candidate and self.selected_source:
            self._show_candidate(
                self.selected_source,
                self.selected_candidate,
            )
        else:
            self._show_welcome()

    def _tab_changed(self, sender):
        if not self._polish_ready:
            return super()._tab_changed(sender)

        index = sender.selected_index
        self.selected_candidate = None
        self.selected_source = None

        if index == 0:
            self.search_field.hidden = False
            self.search_button.hidden = False
            self.installed_toggle.hidden = True
            self.search_field.placeholder = 'Package name'
            self.search_field.text = ''
            self._show_welcome()
        elif index == 1:
            self.search_field.hidden = False
            self.search_button.hidden = False
            self.installed_toggle.hidden = True
            self.search_field.placeholder = 'owner/repository or GitHub URL'
            self.search_field.text = ''
            self._show_welcome()
        else:
            self.search_field.hidden = True
            self.search_button.hidden = True
            self.installed_toggle.hidden = False
            self._show_installed()

    def _show_welcome(self):
        if not self._polish_ready:
            return super()._show_welcome()

        if self.tabs.selected_index == 1:
            self._show_github_tutorial()
        elif self.tabs.selected_index == 2:
            self._show_installed()
        else:
            self._show_suggestions('')

    def _show_github_tutorial(self):
        self._clear_content()
        width = max(self.width, 320)
        card = card_view(
            self.content,
            (16, 10, width - 32, 322),
        )

        make_label(
            card,
            'Install from GitHub',
            (18, 14, card.width - 36, 30),
            size=20,
            bold=True,
        )
        make_label(
            card,
            '1',
            (18, 58, 28, 28),
            size=16,
            color=VIOLET,
            bold=True,
        )
        make_label(
            card,
            'Paste owner/repository or a full GitHub URL.',
            (50, 56, card.width - 68, 40),
            size=14,
            color=MUTED,
            lines=0,
        )
        make_label(
            card,
            '2',
            (18, 108, 28, 28),
            size=16,
            color=VIOLET,
            bold=True,
        )
        make_label(
            card,
            'Inspect the branch, commit, license and Python files.',
            (50, 106, card.width - 68, 42),
            size=14,
            color=MUTED,
            lines=0,
        )
        make_label(
            card,
            '3',
            (18, 160, 28, 28),
            size=16,
            color=VIOLET,
            bold=True,
        )
        make_label(
            card,
            'Install a managed snapshot. Local edits are protected.',
            (50, 158, card.width - 68, 42),
            size=14,
            color=MUTED,
            lines=0,
        )

        make_label(
            card,
            'This is a snapshot, not a full Git clone with history.',
            (18, 214, card.width - 36, 28),
            size=12,
            color=AMBER,
            bold=True,
        )

        example = make_button(
            card,
            'Try clvLabs/PyATEMMax',
            self._use_github_example,
            frame=(18, 256, card.width - 36, 44),
            background=PANEL_ALT,
            color=VIOLET,
        )
        example.font = ('<System-Bold>', 14)

        destination = self.project_manager.projects_dir

        make_label(
            self.content,
            'Projects install to:\n{}'.format(destination),
            (24, 348, width - 48, 52),
            size=11,
            color=MUTED,
            lines=0,
        )

        self.content.content_size = (
            width,
            416,
        )
        self._set_status('Paste a public repository', 'ready')

    def _use_github_example(self, sender):
        self.search_field.text = 'clvLabs/PyATEMMax'
        self._search(sender)

    def textfield_did_begin_editing(self, textfield):
        if self.tabs.selected_index == 0 and not self.busy:
            self._show_suggestions(textfield.text)

    def textfield_should_change(
        self,
        textfield,
        range_value,
        replacement,
    ):
        if (
            self.tabs.selected_index == 0
            and not self.busy
        ):
            current = str(
                textfield.text
                or ''
            )

            try:
                start = int(
                    range_value[0]
                )
                length = int(
                    range_value[1]
                )

                proposed = (
                    current[:start]
                    + str(replacement or '')
                    + current[start + length:]
                )
            except Exception:
                proposed = current

            self._show_suggestions(
                proposed
            )

        return True

    def _show_suggestions(self, query):
        self._clear_content()
        width = max(self.width, 320)
        query = str(query or '').strip()
        index_status = self.pypi_index.status()
        catalogue = {
            canonical_name(item['name']): item
            for item in CATALOG
        }
        y = 10

        index_card_height = 82 if index_status['ready'] else 118
        index_card = card_view(
            self.content,
            (16, y, width - 32, index_card_height),
        )

        if index_status['ready']:
            make_label(
                index_card,
                'Full PyPI index',
                (16, 10, index_card.width - 118, 25),
                size=17,
                bold=True,
            )

            age_seconds = max(
                0,
                time.time() - index_status['updated_at'],
            )
            age_days = int(age_seconds / 86400)

            if age_days == 0:
                age_text = 'synced today'
            elif age_days == 1:
                age_text = 'synced yesterday'
            else:
                age_text = 'synced {} days ago'.format(age_days)

            make_label(
                index_card,
                '{:,} projects · {}'.format(
                    index_status['count'],
                    age_text,
                ),
                (16, 38, index_card.width - 118, 25),
                size=11,
                color=GREEN,
                bold=True,
            )

            def refresh_index(sender):
                def progress(count):
                    def update_status():
                        self._set_status(
                            'Refreshing {:,} projects…'.format(
                                count
                            ),
                            'busy',
                        )

                    _dispatch_main(update_status)

                def complete(result):
                    self._show_suggestions(
                        self.search_field.text
                    )
                    self._set_status(
                        '{:,} PyPI projects refreshed'.format(
                            result['count']
                        ),
                        'success',
                    )

                self._run_job(
                    'Checking the PyPI index…',
                    lambda: self.pypi_index.sync(
                        progress=progress,
                    ),
                    complete,
                )

            make_button(
                index_card,
                'Refresh',
                refresh_index,
                frame=(index_card.width - 98, 20, 82, 42),
                background=PANEL_ALT,
                color=CYAN,
            )
        else:
            make_label(
                index_card,
                'Search all of PyPI',
                (16, 10, index_card.width - 126, 25),
                size=17,
                bold=True,
            )
            make_label(
                index_card,
                (
                    'One optional ~7 MB sync makes every registered '
                    'project searchable on-device.'
                ),
                (16, 38, index_card.width - 126, 58),
                size=12,
                color=MUTED,
                lines=0,
            )

            def start_sync(sender):
                def progress(count):
                    def update_status():
                        self._set_status(
                            'Indexing {:,} projects…'.format(count),
                            'busy',
                        )

                    _dispatch_main(update_status)

                def complete(result):
                    self._show_suggestions(
                        self.search_field.text
                    )
                    self._set_status(
                        '{:,} PyPI projects ready'.format(
                            result['count']
                        ),
                        'success',
                    )

                self._run_job(
                    'Downloading the PyPI index…',
                    lambda: self.pypi_index.sync(
                        progress=progress,
                    ),
                    complete,
                )

            make_button(
                index_card,
                'Sync',
                start_sync,
                frame=(index_card.width - 98, 30, 82, 48),
                background=VIOLET,
                color=TEXT,
            )

        y += index_card_height + 12

        if query and index_status['ready']:
            names = self.pypi_index.search(
                query,
                limit=50,
            )
            items = []

            for name in names:
                known = catalogue.get(canonical_name(name))

                if known is not None:
                    items.append(dict(known))
                else:
                    items.append({
                        'name': name,
                        'description': (
                            'PyPI project · compatibility not yet checked.'
                        ),
                        'status': 'unverified',
                    })

            heading = 'PyPI matches'
        else:
            items = catalogue_matches(
                query,
                limit=50,
            )
            heading = (
                'Catalogue matches'
                if query
                else 'Featured packages'
            )

        make_label(
            self.content,
            '{} ({})'.format(heading, len(items)),
            (16, y, width - 32, 28),
            size=17,
            bold=True,
        )
        y += 34

        if not items:
            empty = card_view(
                self.content,
                (16, y, width - 32, 88),
            )
            message = make_label(
                empty,
                (
                    'No matching project name.\n'
                    'You can still tap Inspect for an exact lookup.'
                ),
                (16, 12, empty.width - 32, 62),
                size=13,
                color=MUTED,
                lines=0,
            )
            message.alignment = ui.ALIGN_CENTER
            y += 100

        for item in items:
            row = card_view(
                self.content,
                (16, y, width - 32, 82),
            )
            name_width = row.width - 112

            make_label(
                row,
                item['name'],
                (14, 10, name_width, 24),
                size=16,
                bold=True,
            )
            make_label(
                row,
                item.get('description') or '',
                (14, 36, name_width, 34),
                size=11,
                color=MUTED,
                lines=0,
            )

            tested = item.get('status') == 'tested'

            button = make_button(
                row,
                'Tested' if tested else 'Inspect',
                lambda sender, name=item['name']: self._inspect_suggestion(
                    name
                ),
                frame=(row.width - 92, 20, 78, 42),
                background=PANEL_ALT,
                color=GREEN if tested else CYAN,
            )
            button.font = ('<System-Bold>', 12)
            y += 92

        self.content.content_size = (
            width,
            max(self.content.height, y + 12),
        )

        if query and index_status['ready']:
            status_text = (
                'Showing {} PyPI name match{}'.format(
                    len(items),
                    '' if len(items) == 1 else 'es',
                )
            )
        elif index_status['ready']:
            status_text = '{:,} PyPI projects searchable'.format(
                index_status['count']
            )
        else:
            status_text = 'Sync the full index or use exact lookup'

        self._set_status(status_text, 'ready')

    def _inspect_suggestion(self, name):
        self.search_field.text = name
        self._search(self.search_button)

    def _install_selected(self, sender):
        if self.busy or not self.selected_candidate:
            return

        if self.selected_source != 'pypi':
            return super()._install_selected(sender)

        dependencies = (
            self.selected_candidate.get('dependencies') or []
        )

        if not dependencies:
            return super()._install_selected(sender)

        package = (
            self.selected_candidate.get('name')
            or self.selected_candidate.get('requested_name')
            or ''
        )

        self._run_job(
            'Resolving dependencies for {}…'.format(package),
            lambda: build_dependency_plan(
                package,
                self.package_manager,
            ),
            self._show_dependency_plan,
        )

    def _show_dependency_plan(self, plan):
        self.pending_dependency_plan = plan
        self._clear_content()

        width = max(self.width, 320)
        install_count = len(plan.get('install') or [])
        satisfied_count = len(plan.get('satisfied') or [])
        skipped_count = len(plan.get('skipped') or [])
        blockers = plan.get('blockers') or []
        y = 10

        header = card_view(
            self.content,
            (16, y, width - 32, 142),
        )

        make_label(
            header,
            'Review installation',
            (18, 14, header.width - 36, 30),
            size=20,
            bold=True,
        )

        summary = (
            '{} package{} to install · {} already available'
        ).format(
            install_count,
            '' if install_count == 1 else 's',
            satisfied_count,
        )

        make_label(
            header,
            summary,
            (18, 50, header.width - 36, 24),
            size=13,
            color=CYAN if not blockers else CORAL,
            bold=True,
        )

        detail = (
            'Dependencies install first. If any step fails, '
            'Pipista rolls back every new package.'
        )

        if skipped_count:
            detail += (
                '\n{} inactive marker or optional-extra '
                'requirement{} ignored.'
            ).format(
                skipped_count,
                '' if skipped_count == 1 else 's',
            )

        make_label(
            header,
            detail,
            (18, 80, header.width - 36, 48),
            size=11,
            color=MUTED,
            lines=0,
        )

        y += 154

        status_titles = {
            'install': 'Will install',
            'managed': 'Managed',
            'external': 'Available',
            'blocked': 'Blocked',
        }
        status_colors = {
            'install': CYAN,
            'managed': GREEN,
            'external': GREEN,
            'blocked': CORAL,
        }

        for item in plan.get('items') or []:
            status = item.get('status') or 'blocked'
            card = card_view(
                self.content,
                (16, y, width - 32, 96),
            )

            name = item.get('name') or ''
            version = item.get('version') or ''
            title = name
            if version:
                title += ' {}'.format(version)

            make_label(
                card,
                title,
                (16, 10, card.width - 132, 26),
                size=16,
                bold=True,
            )

            badge = make_label(
                card,
                status_titles.get(status, status.title()),
                (card.width - 116, 10, 100, 26),
                size=11,
                color=status_colors.get(status, MUTED),
                bold=True,
            )
            badge.alignment = ui.ALIGN_RIGHT

            make_label(
                card,
                item.get('reason') or '',
                (16, 42, card.width - 32, 42),
                size=11,
                color=MUTED,
                lines=0,
            )

            y += 108

        if blockers:
            blocker = card_view(
                self.content,
                (16, y, width - 32, 96),
            )

            make_label(
                blocker,
                'Installation blocked',
                (16, 10, blocker.width - 32, 26),
                size=16,
                color=CORAL,
                bold=True,
            )

            blocker_text = '\n'.join(
                '{}: {}'.format(
                    item.get('package') or 'Dependency',
                    item.get('message') or '',
                )
                for item in blockers[:3]
            )

            make_label(
                blocker,
                blocker_text,
                (16, 40, blocker.width - 32, 46),
                size=10,
                color=MUTED,
                lines=0,
            )

            y += 108

        if not blockers and install_count:
            install = make_button(
                self.content,
                'Install {} package{}'.format(
                    install_count,
                    '' if install_count == 1 else 's',
                ),
                self._install_dependency_plan,
                frame=(16, y, width - 32, 48),
                background=CYAN,
                color=BACKGROUND,
            )
            install.font = ('<System-Bold>', 15)
            y += 60

        make_button(
            self.content,
            'Back to package',
            self._cancel_dependency_plan,
            frame=(16, y, width - 32, 42),
            background=PANEL_ALT,
            color=TEXT,
        )
        y += 54

        self.content.content_size = (
            width,
            max(self.content.height, y + 12),
        )

        if blockers:
            self._set_status(
                'Dependency plan has {} blocker{}'.format(
                    len(blockers),
                    '' if len(blockers) == 1 else 's',
                ),
                'error',
            )
        elif install_count:
            self._set_status(
                'Review the plan, then confirm installation',
                'ready',
            )
        else:
            self._set_status(
                'Everything required is already available',
                'success',
            )

    def _install_dependency_plan(self, sender):
        if self.busy:
            return

        plan = getattr(
            self,
            'pending_dependency_plan',
            None,
        )

        if not plan or not plan.get('can_install'):
            self._set_status(
                'This dependency plan cannot be installed',
                'error',
            )
            return

        count = len(plan.get('install') or [])

        self._run_job(
            'Installing {} package{}…'.format(
                count,
                '' if count == 1 else 's',
            ),
            lambda: execute_dependency_plan(
                plan,
                self.package_manager,
            ),
            self._dependency_install_complete,
        )

    def _dependency_install_complete(self, result):
        self.pending_dependency_plan = None
        record = result.get('root_record') or {}

        if record:
            self._installation_complete(record)
            return

        self.tabs.selected_index = 2
        self.search_field.hidden = True
        self.search_button.hidden = True
        self._show_installed()

    def _cancel_dependency_plan(self, sender):
        self.pending_dependency_plan = None

        if self.selected_candidate and self.selected_source:
            self._show_candidate(
                self.selected_source,
                self.selected_candidate,
            )
        else:
            self._show_welcome()

    def _installed_mode_changed(self, sender):
        self._show_installed()

    def _show_installed(self):
        if not self._polish_ready:
            return super()._show_installed()

        self.installed_toggle.hidden = False

        if self.installed_toggle.selected_index == 0:
            return super()._show_installed()

        self._show_environment()

    def _show_environment(self):
        self._clear_content()
        width = max(self.width, 320)
        managed = self.package_manager.installed()

        self._inventory_cache = scan_environment(managed)
        user_items = self._inventory_cache.get('user') or []
        bundled_items = self._inventory_cache.get('bundled') or []

        y = 10

        make_label(
            self.content,
            'Pythonista environment',
            (16, y, width - 32, 30),
            size=21,
            bold=True,
        )
        y += 36

        make_label(
            self.content,
            (
                'Read-only inventory. Pipista only offers uninstall for '
                'items it installed and can account for safely.'
            ),
            (16, y, width - 32, 50),
            size=12,
            color=MUTED,
            lines=0,
        )
        y += 62

        y = self._add_environment_group(
            'User site-packages',
            user_items,
            y,
            width,
            CYAN,
        )
        y = self._add_environment_group(
            'Bundled with Pythonista',
            bundled_items,
            y,
            width,
            VIOLET,
        )

        self.content.content_size = (
            width,
            max(self.content.height, y + 20),
        )
        self._set_status(
            '{} user, {} bundled imports'.format(
                len(user_items),
                len(bundled_items),
            ),
            'ready',
        )

    def _add_environment_group(
        self,
        title,
        items,
        y,
        width,
        accent,
    ):
        make_label(
            self.content,
            '{} ({})'.format(title, len(items)),
            (16, y, width - 32, 28),
            size=16,
            color=accent,
            bold=True,
        )
        y += 34

        group = ui.View(
            frame=(
                16,
                y,
                width - 32,
                max(54, len(items) * 50),
            )
        )
        group.background_color = PANEL
        group.corner_radius = 14
        group.border_width = 1
        group.border_color = BORDER
        self.content.add_subview(group)

        for index, item in enumerate(items):
            row_y = index * 50

            make_label(
                group,
                item['name'],
                (14, row_y + 4, group.width - 132, 24),
                size=14,
                bold=True,
            )

            detail = item.get('version') or item.get('location') or ''

            if item.get('managed'):
                detail = '{} · managed'.format(detail or 'Pipista')

            make_label(
                group,
                detail,
                (14, row_y + 26, group.width - 28, 18),
                size=10,
                color=MUTED,
            )

            if index < len(items) - 1:
                line = ui.View(
                    frame=(
                        14,
                        row_y + 49,
                        group.width - 28,
                        1,
                    )
                )
                line.background_color = BORDER
                group.add_subview(line)

        return y + group.height + 18


def main(presentation='fullscreen'):
    presentation = str(presentation or 'fullscreen').strip().lower()

    if presentation not in ('fullscreen', 'panel'):
        raise ValueError(
            'Pipista presentation must be fullscreen or panel'
        )

    screen_width, screen_height = ui.get_screen_size()
    view = PipistaApp()
    view.frame = (
        0,
        0,
        screen_width,
        screen_height,
    )
    view.present(
        presentation,
        hide_title_bar=True,
        animated=True,
    )
    return view


if __name__ == '__main__':
    main()