# Pipista

A friendly, touch-first package and project manager built specifically for
[Pythonista](https://omz-software.com/pythonista/) on iPhone and iPad.

Pipista makes useful pure-Python software accessible without requiring StaSh,
a local `pip` command, subprocess support or a desktop computer.

> **Status:** Pipista Public Beta 1 is being prepared. Please treat the current
> code as pre-release software until the first tagged release is published.

## Features

- Search the complete PyPI project index with live filtering
- Inspect package metadata before installation
- Install compatible universal Python wheels
- Conservatively install suitable pure-Python source archives
- Resolve active runtime dependencies before installation
- Review and confirm the complete dependency plan
- Recognise packages already available in Pythonista
- Install public GitHub repositories as managed, editable projects
- Track packages and projects installed through Pipista
- Inspect the wider Pythonista package environment without modifying it
- Open package and project pages in a web browser
- Run in fullscreen or Pythonista panel mode

## Quick installation

Create a temporary Python file in Pythonista, paste the following code and run
it once:

```python
from urllib.request import urlopen

url = (
    'https://raw.githubusercontent.com/'
    'jackatttack/Pipista/main/install_pipista.py'
)
source = urlopen(url).read()
exec(compile(source, 'install_pipista.py', 'exec'))
```

The installer downloads the repository, extracts only an explicit allowlist of
release files, checks that every Python source file compiles, stages the new
application and backs up an existing Pipista installation before replacing it.

After installation, run:

- `~/Documents/Pipista/Pipista.py` for fullscreen mode
- `~/Documents/Pipista/Pipista_Panel.py` for panel mode

You can also download and review
[`install_pipista.py`](install_pipista.py) before running it.

## Where Pipista stores things

All locations are calculated for the current Pythonista user:

| Purpose | Location |
| --- | --- |
| Pipista application | `~/Documents/Pipista` |
| Fullscreen launcher | `~/Documents/Pipista/Pipista.py` |
| Panel launcher | `~/Documents/Pipista/Pipista_Panel.py` |
| Pipista state and cache | `~/Documents/.pipista` |
| Installed GitHub projects | `~/Documents/Pipista Projects` |
| Installed Python packages | Pythonista's user `site-packages` directory |

Pipista does not contain hard-coded device container identifiers or paths from
the developer's iPhone.

## Using Pipista

### PyPI packages

1. Open the **PyPI** tab.
2. Tap **Sync PyPI index** the first time you use Pipista.
3. Start typing a project name.
4. Select a result and tap **Inspect**.
5. Review compatibility and dependency information.
6. Tap **Install**.
7. Confirm the dependency plan when dependencies are required.

The local PyPI index is refreshed only when you press the sync button. Pipista
checks PyPI's serial number and avoids rebuilding the database when the cached
index is already current.

### GitHub projects

1. Open the **GitHub** tab.
2. Enter `owner/repository`, or paste a public GitHub URL.
3. Inspect the repository and requested branch or reference.
4. Install the repository as a managed project snapshot.

GitHub projects are stored separately from packages and remain editable.

### Installed items

The **Managed** view contains packages and projects installed by Pipista.
Dependency relationships are recorded so a required dependency cannot be
removed while another managed package still needs it.

The **Environment** view is a read-only inventory of importable packages
already available to Pythonista, including bundled and independently installed
modules.

## Dependency handling

Pipista evaluates active runtime requirements and displays its proposed actions
before installation.

A dependency may be:

- installed from PyPI;
- recognised as already managed by Pipista;
- recognised as already importable in Pythonista;
- skipped because its environment marker or optional extra is inactive; or
- blocked when Pipista cannot resolve it safely.

Dependency installations are transactional. If one package fails, packages
installed during that operation are rolled back.

The optional `packaging` module provides the richest PEP 508 requirement and
marker evaluation. Pipista has a conservative fallback for environments where
that module is unavailable and blocks requirements it cannot interpret safely.

## Safety model

Pipista deliberately avoids behaving like a full desktop `pip` installation:

- PyPI downloads are verified against SHA-256 metadata
- archive paths, links, expansion size and file counts are checked
- `setup.py`, build backends and downloaded installer scripts are not executed
- installations are staged before files enter `site-packages`
- existing unmanaged files are not intentionally overwritten
- installed imports are verified
- dependency groups roll back together after failure
- dependencies required by other managed packages are protected from uninstall
- modified files are detected before removal
- incompatible foreign binaries are omitted and reported
- native-only packages are rejected

## Trust warning

Installing Python software always requires trust.

Pipista does not execute package build scripts, but it verifies an installation
by importing the installed package. Importing a package executes that package's
Python code.

Only install packages and repositories you trust.

## Limitations

Pipista is not a replacement for a complete desktop Python environment.

Packages requiring compiled extensions, unsupported native libraries, Rust,
system commands, build tools or platform services unavailable on iOS may not
work in Pythonista.

Some pure-Python projects can install successfully while individual optional
features remain unavailable on iOS. Pipista reports omitted incompatible binary
files where possible.

Pythonista does not always provide conventional distribution metadata for its
bundled modules. Pipista can often recognise these modules by import name, but
their exact version may not be verifiable.

## Updating Pipista

Run the quick-install snippet again. The installer stages the new copy and moves
the current installation into:

`~/Documents/.pipista/backups`

Pipista's package registry, PyPI index cache and managed-project information
remain in `~/Documents/.pipista` and are not replaced with the application.

## Development and testing

The public repository contains the application, documentation and installer.
Development smoke tests are maintained separately and are not included in the
public release bundle.

Current development coverage includes:

- safe wheel and source-archive installation
- PyATEMMax source installation
- dependency planning and transactional rollback
- a real `discord` and `discord.py` dependency installation
- existing Pythonista `aiohttp` detection
- metadata-only forwarding packages
- incompatible Windows DLL omission
- native-only package rejection
- dependency-aware uninstall protection
- GitHub snapshot installation and modification detection
- fullscreen and panel presentation

## Security

Please read [SECURITY.md](SECURITY.md) before reporting a vulnerability.

## License

Pipista is released under the MIT License. See [LICENSE](LICENSE).

## Independence

Pipista is an independent community project. It is not affiliated with PyPI,
the Python Software Foundation, Pythonista or omz:software.