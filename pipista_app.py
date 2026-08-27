# -*- coding: utf-8 -*-
"""Touch-first Pythonista interface for Pipista."""

import os
import threading

import console
import ui
import webbrowser
from urllib.parse import quote

from github_projects import GitHubProjectManager
from pipista_engine import (
    ModifiedFilesError,
    PackageManager,
    PipistaError,
)


BACKGROUND = '#0d1220'
PANEL = '#171f31'
PANEL_ALT = '#202a40'
TEXT = '#f5f7ff'
MUTED = '#9ca9bf'
CYAN = '#51d6df'
VIOLET = '#9b83ff'
GREEN = '#62d99c'
AMBER = '#f2be63'
CORAL = '#ff7f78'
BORDER = '#2b3852'


def make_label(
    parent,
    text='',
    frame=(0, 0, 100, 30),
    size=14,
    color=TEXT,
    bold=False,
    lines=1,
):
    label = ui.Label(frame=frame)
    label.text = str(text)
    label.text_color = color
    label.font = (
        '<System-Bold>' if bold else '<System>',
        size,
    )
    label.number_of_lines = lines
    label.background_color = 'clear'
    parent.add_subview(label)
    return label


def make_button(
    parent,
    title,
    action,
    frame=(0, 0, 100, 40),
    background=VIOLET,
    color=TEXT,
):
    button = ui.Button(frame=frame)
    button.title = title
    button.action = action
    button.background_color = background
    button.tint_color = color
    button.font = ('<System-Bold>', 14)
    button.corner_radius = 10
    parent.add_subview(button)
    return button


def card_view(parent, frame):
    card = ui.View(frame=frame)
    card.background_color = PANEL
    card.corner_radius = 14
    card.border_width = 1
    card.border_color = BORDER
    parent.add_subview(card)
    return card


def short_sha(value):
    return str(value or '')[:12]


class PipistaApp(ui.View):
    def __init__(
        self,
        package_target=None,
        projects_dir=None,
        state_dir=None,
    ):
        super().__init__()

        self.name = 'Pipista'
        self.background_color = BACKGROUND
        self.flex = 'WH'

        self.package_manager = PackageManager(
            target_dir=package_target,
            state_dir=state_dir,
        )
        self.project_manager = GitHubProjectManager(
            projects_dir=projects_dir,
            state_dir=state_dir,
        )

        self.busy = False
        self.selected_candidate = None
        self.selected_source = None

        self.title_label = make_label(
            self,
            'Pipista',
            size=28,
            bold=True,
        )
        self.title_label.text_color = CYAN

        self.subtitle_label = make_label(
            self,
            'Pythonista packages and projects',
            size=13,
            color=MUTED,
        )

        self.tabs = ui.SegmentedControl()
        self.tabs.segments = [
            'PyPI',
            'GitHub',
            'Installed',
        ]
        self.tabs.selected_index = 0
        self.tabs.tint_color = VIOLET
        self.tabs.action = self._tab_changed
        self.add_subview(self.tabs)

        self.search_field = ui.TextField()
        self.search_field.placeholder = 'Package name'
        self.search_field.text_color = TEXT
        self.search_field.tint_color = CYAN
        self.search_field.background_color = PANEL
        self.search_field.corner_radius = 10
        self.search_field.clear_button_mode = 'while_editing'
        self.search_field.return_key_type = 'search'
        self.search_field.action = self._search
        self.search_field.font = ('<System>', 15)
        self.add_subview(self.search_field)

        self.search_button = make_button(
            self,
            'Inspect',
            self._search,
            background=VIOLET,
        )

        self.content = ui.ScrollView()
        self.content.background_color = 'clear'
        self.content.flex = 'WH'
        self.add_subview(self.content)

        self.status_panel = ui.View()
        self.status_panel.background_color = PANEL
        self.status_panel.corner_radius = 10
        self.add_subview(self.status_panel)

        self.status_dot = ui.View()
        self.status_dot.background_color = GREEN
        self.status_dot.corner_radius = 4
        self.status_panel.add_subview(self.status_dot)

        self.status_label = make_label(
            self.status_panel,
            'Ready',
            size=12,
            color=MUTED,
        )

        self._show_welcome()

    def layout(self):
        width = self.width
        height = self.height
        pad = 16

        self.title_label.frame = (
            pad,
            18,
            width - pad * 2,
            34,
        )
        self.subtitle_label.frame = (
            pad,
            50,
            width - pad * 2,
            24,
        )
        self.tabs.frame = (
            pad,
            82,
            width - pad * 2,
            34,
        )

        search_y = 128
        button_width = 92

        self.search_field.frame = (
            pad,
            search_y,
            width - pad * 3 - button_width,
            42,
        )
        self.search_button.frame = (
            width - pad - button_width,
            search_y,
            button_width,
            42,
        )

        content_y = 182
        status_height = 38
        status_y = height - status_height - 12

        self.content.frame = (
            0,
            content_y,
            width,
            max(80, status_y - content_y - 8),
        )
        self.status_panel.frame = (
            pad,
            status_y,
            width - pad * 2,
            status_height,
        )
        self.status_dot.frame = (12, 15, 8, 8)
        self.status_label.frame = (
            30,
            4,
            self.status_panel.width - 40,
            30,
        )

    def _clear_content(self):
        for subview in list(self.content.subviews):
            self.content.remove_subview(subview)

        self.content.content_offset = (0, 0)
        self.content.content_size = (
            self.content.width,
            self.content.height,
        )

    def _set_status(self, text, kind='ready'):
        colors = {
            'ready': GREEN,
            'busy': AMBER,
            'error': CORAL,
            'success': CYAN,
        }
        self.status_dot.background_color = colors.get(kind, GREEN)
        self.status_label.text = str(text)

    def _set_busy(self, busy, message=''):
        self.busy = bool(busy)
        self.search_button.enabled = not self.busy
        self.search_field.enabled = not self.busy

        if self.busy:
            self.search_button.title = 'Working…'
            self._set_status(message or 'Working…', 'busy')
        else:
            self.search_button.title = 'Inspect'

    def _run_job(self, message, operation, completion):
        if self.busy:
            return

        self._set_busy(True, message)

        def work():
            try:
                result = operation()
            except BaseException as exc:
                error_text = '{}: {}'.format(
                    exc.__class__.__name__,
                    exc,
                )

                def deliver_error():
                    self._set_busy(False)
                    self._set_status(error_text, 'error')

                ui.delay(deliver_error, 0)
                return

            def deliver_success():
                self._set_busy(False)
                completion(result)

            ui.delay(deliver_success, 0)

        thread = threading.Thread(target=work)
        thread.daemon = True
        thread.start()

    def _tab_changed(self, sender):
        index = sender.selected_index
        self.selected_candidate = None
        self.selected_source = None

        if index == 0:
            self.search_field.hidden = False
            self.search_button.hidden = False
            self.search_field.placeholder = 'Package name'
            self.search_field.text = ''
            self._show_welcome()
        elif index == 1:
            self.search_field.hidden = False
            self.search_button.hidden = False
            self.search_field.placeholder = 'owner/repository or GitHub URL'
            self.search_field.text = ''
            self._show_welcome()
        else:
            self.search_field.hidden = True
            self.search_button.hidden = True
            self._show_installed()

    def _show_welcome(self):
        self._clear_content()
        width = max(self.width, 320)
        card = card_view(
            self.content,
            (16, 10, width - 32, 210),
        )

        make_label(
            card,
            'Find something useful',
            (18, 14, card.width - 36, 28),
            size=19,
            bold=True,
        )

        if self.tabs.selected_index == 1:
            body = (
                'Enter a public GitHub repository. Pipista resolves its '
                'current commit, downloads a safe snapshot and installs it '
                'as a managed Pythonista project.'
            )
            examples = 'Try: clvLabs/PyATEMMax'
            accent = VIOLET
        else:
            body = (
                'Enter an exact PyPI project name. Pipista checks for a '
                'compatible universal wheel or a conservative pure-Python '
                'source installation.'
            )
            examples = 'Try: wikipedia'
            accent = CYAN

        make_label(
            card,
            body,
            (18, 54, card.width - 36, 82),
            size=14,
            color=MUTED,
            lines=0,
        )
        example = make_label(
            card,
            examples,
            (18, 150, card.width - 36, 30),
            size=13,
            color=accent,
            bold=True,
        )
        example.alignment = ui.ALIGN_CENTER

        self.content.content_size = (
            width,
            236,
        )
        self._set_status('Ready', 'ready')

    def _search(self, sender):
        if self.busy:
            return

        query = str(self.search_field.text or '').strip()

        if not query:
            self._set_status('Enter something to inspect', 'error')
            return

        if self.tabs.selected_index == 0:
            self._run_job(
                'Checking PyPI…',
                lambda: self.package_manager.inspect_pypi(query),
                lambda result: self._show_candidate(
                    'pypi',
                    result,
                ),
            )
        elif self.tabs.selected_index == 1:
            self._run_job(
                'Checking GitHub…',
                lambda: self.project_manager.inspect(query),
                lambda result: self._show_candidate(
                    'github',
                    result,
                ),
            )

    def _show_candidate(self, source, candidate):
        self.selected_source = source
        self.selected_candidate = candidate
        self._clear_content()

        width = max(self.width, 320)
        card = card_view(
            self.content,
            (16, 10, width - 32, 380),
        )

        if source == 'pypi':
            name = candidate.get('name') or ''
            version = candidate.get('version') or 'unknown'
            summary = candidate.get('summary') or 'No description provided.'
            kind = candidate.get('kind') or 'unknown'
            dependencies = candidate.get('dependencies') or []

            make_label(
                card,
                name,
                (18, 14, card.width - 36, 30),
                size=21,
                bold=True,
            )
            make_label(
                card,
                'PyPI · {} · {}'.format(version, kind),
                (18, 46, card.width - 36, 24),
                size=13,
                color=CYAN,
                bold=True,
            )
            make_label(
                card,
                summary,
                (18, 80, card.width - 36, 72),
                size=14,
                color=MUTED,
                lines=0,
            )

            if kind == 'wheel':
                compatibility = 'Compatible universal wheel'
                compatibility_color = GREEN
            else:
                compatibility = 'Source archive — safely inspected on install'
                compatibility_color = AMBER

            make_label(
                card,
                compatibility,
                (18, 166, card.width - 36, 25),
                size=13,
                color=compatibility_color,
                bold=True,
            )
            dependency_text = '{} declared dependenc{}'.format(
                len(dependencies),
                'y' if len(dependencies) == 1 else 'ies',
            )

            if dependencies:
                dependency_text += ' · not auto-installed yet'

            make_label(
                card,
                dependency_text,
                (18, 196, card.width - 36, 42),
                size=12,
                color=AMBER if dependencies else MUTED,
                bold=bool(dependencies),
                lines=0,
            )
        else:
            name = candidate.get('full_name') or ''
            description = (
                candidate.get('description')
                or 'No description provided.'
            )

            make_label(
                card,
                name,
                (18, 14, card.width - 36, 30),
                size=21,
                bold=True,
            )
            make_label(
                card,
                'GitHub · {} · {}'.format(
                    candidate.get('requested_ref') or '',
                    short_sha(candidate.get('commit_sha')),
                ),
                (18, 46, card.width - 36, 24),
                size=13,
                color=VIOLET,
                bold=True,
            )
            make_label(
                card,
                description,
                (18, 80, card.width - 36, 72),
                size=14,
                color=MUTED,
                lines=0,
            )
            make_label(
                card,
                '{} stars · license {}'.format(
                    candidate.get('stars') or 0,
                    candidate.get('license') or 'not declared',
                ),
                (18, 166, card.width - 36, 25),
                size=13,
                color=MUTED,
            )
            make_label(
                card,
                'Installs as a managed, editable project snapshot',
                (18, 196, card.width - 36, 24),
                size=13,
                color=GREEN,
                bold=True,
            )

        link_title = (
            'View on GitHub ↗'
            if source == 'github'
            else 'View on PyPI ↗'
        )
        link = make_button(
            card,
            link_title,
            self._open_selected_source,
            frame=(18, 242, card.width - 36, 36),
            background=PANEL_ALT,
            color=VIOLET if source == 'github' else CYAN,
        )
        link.font = ('<System-Bold>', 13)

        install_title = 'Install'
        if (
            source == 'pypi'
            and (candidate.get('dependencies') or [])
        ):
            install_title = 'Review & Install'

        install = make_button(
            card,
            install_title,
            self._install_selected,
            frame=(18, 294, card.width - 36, 48),
            background=VIOLET if source == 'github' else CYAN,
            color=BACKGROUND,
        )
        install.font = ('<System-Bold>', 16)

        self.content.content_size = (
            width,
            406,
        )
        self._set_status('Inspection complete', 'success')

    def _open_external_url(self, url):
        try:
            opened = webbrowser.open(url)
            if opened is False:
                raise RuntimeError('Pythonista could not open the URL')
            self._set_status('Opening browser…', 'success')
        except Exception as exc:
            self._set_status(
                'Could not open browser: {}'.format(exc),
                'error',
            )

    def _open_selected_source(self, sender):
        candidate = self.selected_candidate or {}

        if self.selected_source == 'github':
            full_name = candidate.get('full_name') or ''
            if not full_name:
                self._set_status('GitHub repository is unavailable', 'error')
                return

            url = 'https://github.com/{}'.format(
                quote(str(full_name), safe='/')
            )
        else:
            name = (
                candidate.get('name')
                or candidate.get('requested_name')
                or ''
            )
            if not name:
                self._set_status('PyPI package name is unavailable', 'error')
                return

            url = 'https://pypi.org/project/{}/'.format(
                quote(str(name), safe='')
            )

        self._open_external_url(url)

    def _open_package_record(self, sender, record):
        name = record.get('name') or ''
        if not name:
            self._set_status('PyPI package name is unavailable', 'error')
            return

        self._open_external_url(
            'https://pypi.org/project/{}/'.format(
                quote(str(name), safe='')
            )
        )

    def _open_project_record(self, sender, record):
        full_name = record.get('full_name') or ''
        if not full_name:
            self._set_status('GitHub repository is unavailable', 'error')
            return

        self._open_external_url(
            'https://github.com/{}'.format(
                quote(str(full_name), safe='/')
            )
        )

    def _install_selected(self, sender):
        if self.busy or not self.selected_candidate:
            return

        candidate = self.selected_candidate
        source = self.selected_source

        if source == 'pypi':
            name = candidate.get('name') or candidate.get(
                'requested_name'
            )

            self._run_job(
                'Installing {}…'.format(name),
                lambda: self.package_manager.install_pypi(name),
                self._installation_complete,
            )
        else:
            full_name = candidate.get('full_name')
            ref = candidate.get('requested_ref')

            self._run_job(
                'Installing {}…'.format(full_name),
                lambda: self.project_manager.install(
                    full_name,
                    ref=ref,
                ),
                self._installation_complete,
            )

    def _installation_complete(self, record):
        name = (
            record.get('name')
            or record.get('full_name')
            or 'Item'
        )
        self._set_status('{} installed'.format(name), 'success')
        self.tabs.selected_index = 2
        self.search_field.hidden = True
        self.search_button.hidden = True
        self._show_installed()

    def _show_installed(self):
        self._clear_content()
        width = max(self.width, 320)
        packages = self.package_manager.installed()
        projects = self.project_manager.installed()
        y = 10

        make_label(
            self.content,
            'Managed by Pipista',
            (16, y, width - 32, 32),
            size=21,
            bold=True,
        )
        y += 44

        if not packages and not projects:
            card = card_view(
                self.content,
                (16, y, width - 32, 126),
            )
            message = make_label(
                card,
                'Nothing installed yet.\nUse PyPI or GitHub to find something.',
                (18, 20, card.width - 36, 80),
                size=14,
                color=MUTED,
                lines=0,
            )
            message.alignment = ui.ALIGN_CENTER
            y += 142

        for record in packages:
            card = card_view(
                self.content,
                (16, y, width - 32, 166),
            )
            make_label(
                card,
                record.get('name') or '',
                (16, 12, card.width - 132, 28),
                size=18,
                bold=True,
            )
            make_label(
                card,
                'PyPI · {} · {}'.format(
                    record.get('version') or 'unknown',
                    record.get('artifact_kind') or '',
                ),
                (16, 42, card.width - 132, 22),
                size=12,
                color=CYAN,
                bold=True,
            )
            dependencies = record.get('dependencies') or []
            resolved = record.get('resolved_dependencies') or []
            required_by = record.get('required_by') or []
            package_detail = (
                record.get('summary')
                or 'Installed Python package'
            )

            if record.get('metadata_only'):
                package_detail += '\nForwarding package'

            skipped_native = (
                record.get('skipped_native_files') or []
            )
            if skipped_native:
                package_detail += (
                    '\n{} incompatible binary file{} omitted'.format(
                        len(skipped_native),
                        '' if len(skipped_native) == 1 else 's',
                    )
                )

            if resolved:
                package_detail += (
                    '\n{} dependenc{} resolved'.format(
                        len(resolved),
                        'y' if len(resolved) == 1 else 'ies',
                    )
                )
            elif dependencies:
                package_detail += (
                    '\n{} declared dependenc{} · not managed'.format(
                        len(dependencies),
                        'y' if len(dependencies) == 1 else 'ies',
                    )
                )

            if required_by:
                package_detail += (
                    '\nRequired by {}'.format(
                        ', '.join(required_by[:3])
                    )
                )

            make_label(
                card,
                package_detail,
                (16, 70, card.width - 132, 82),
                size=11,
                color=MUTED,
                lines=0,
            )
            make_button(
                card,
                'View ↗',
                lambda sender, item=record: self._open_package_record(
                    sender,
                    item,
                ),
                frame=(card.width - 108, 12, 92, 32),
                background=PANEL_ALT,
                color=CYAN,
            )
            make_button(
                card,
                'Uninstall',
                lambda sender, item=record: self._confirm_uninstall_package(
                    item
                ),
                frame=(card.width - 108, 54, 92, 42),
                background=PANEL_ALT,
                color=CORAL,
            )
            y += 178

        for record in projects:
            card = card_view(
                self.content,
                (16, y, width - 32, 142),
            )
            make_label(
                card,
                record.get('full_name') or '',
                (16, 12, card.width - 132, 28),
                size=18,
                bold=True,
            )
            make_label(
                card,
                'GitHub · {} · {}'.format(
                    record.get('requested_ref') or '',
                    short_sha(record.get('commit_sha')),
                ),
                (16, 42, card.width - 132, 22),
                size=12,
                color=VIOLET,
                bold=True,
            )
            make_label(
                card,
                record.get('destination') or '',
                (16, 70, card.width - 132, 50),
                size=12,
                color=MUTED,
                lines=0,
            )
            make_button(
                card,
                'View ↗',
                lambda sender, item=record: self._open_project_record(
                    sender,
                    item,
                ),
                frame=(card.width - 108, 12, 92, 32),
                background=PANEL_ALT,
                color=VIOLET,
            )
            make_button(
                card,
                'Uninstall',
                lambda sender, item=record: self._confirm_uninstall_project(
                    item
                ),
                frame=(card.width - 108, 54, 92, 42),
                background=PANEL_ALT,
                color=CORAL,
            )
            y += 154

        self.content.content_size = (
            width,
            max(self.content.height, y + 14),
        )
        self._set_status(
            '{} package{}, {} project{}'.format(
                len(packages),
                '' if len(packages) == 1 else 's',
                len(projects),
                '' if len(projects) == 1 else 's',
            ),
            'ready',
        )

    def _confirm_uninstall_package(self, record):
        name = record.get('name') or ''

        try:
            answer = console.alert(
                'Uninstall package?',
                '{} {} will be removed.'.format(
                    name,
                    record.get('version') or '',
                ),
                'Keep',
                'Uninstall',
                hide_cancel_button=True,
            )
        except KeyboardInterrupt:
            return

        if answer != 2:
            return

        self._run_job(
            'Uninstalling {}…'.format(name),
            lambda: self.package_manager.uninstall(name),
            lambda result: self._uninstall_complete(
                result.get('name') or name
            ),
        )

    def _confirm_uninstall_project(self, record):
        full_name = record.get('full_name') or ''

        try:
            answer = console.alert(
                'Uninstall project?',
                (
                    '{} will be removed only if it has no local edits '
                    'or untracked files.'
                ).format(full_name),
                'Keep',
                'Uninstall',
                hide_cancel_button=True,
            )
        except KeyboardInterrupt:
            return

        if answer != 2:
            return

        self._run_job(
            'Checking and uninstalling {}…'.format(full_name),
            lambda: self.project_manager.uninstall(full_name),
            lambda result: self._uninstall_complete(full_name),
        )

    def _uninstall_complete(self, name):
        self._set_status('{} uninstalled'.format(name), 'success')
        self._show_installed()


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