# Pipista

A friendly, touch-first package and project manager built specifically for
[Pythonista](https://omz-software.com/pythonista/) on iPhone and iPad.

Pipista is designed to make useful pure-Python software accessible without
requiring StaSh, a local `pip` command, subprocesses, or a desktop computer.

> **Status:** The first public beta is being prepared. The source code and
> installer will be published here after the release audit is complete.

## What Pipista does

- Searches the full PyPI project index with live filtering
- Inspects package metadata before installation
- Installs compatible universal Python wheels
- Conservatively installs suitable pure-Python source archives
- Resolves active runtime dependencies before installation
- Shows a complete dependency plan for confirmation
- Recognises packages already available in Pythonista
- Installs public GitHub repository snapshots as editable projects
- Tracks packages and projects managed by Pipista
- Shows the wider Pythonista package environment read-only
- Supports fullscreen and Pythonista panel presentation
- Opens the relevant PyPI or GitHub page in a browser

## Safety model

Pipista takes a deliberately conservative approach:

- Downloads are verified against PyPI SHA-256 metadata
- Archives are checked for path traversal, links and unsafe expansion
- Download size, expanded size and file-count limits are enforced
- `setup.py`, build backends, shell commands and downloaded installers are
  never executed
- Installations are staged before files enter `site-packages`
- Existing unmanaged files are never intentionally overwritten
- Installed imports are verified
- Dependency installations are transactional and roll back as a group
- Dependencies cannot be removed while another managed package requires them
- Modified files are detected before uninstall
- Incompatible foreign binaries are omitted and reported
- Native-only packages are rejected

## Important limitations

Pipista is not a replacement for a full desktop Python environment.

Packages that require compiled extensions, native libraries, Rust, system
commands, build tools or unsupported platform services may not work in
Pythonista.

Some packages are only partly useful on iOS. For example, a pure-Python package
may include an optional feature that depends on a platform-specific binary.
Pipista reports when incompatible binary files have been omitted.

Packages already supplied by Pythonista may be recognised by their import name
when reliable distribution metadata is unavailable. In that case, the exact
installed version may not be verifiable.

## Trust and installed code

Pipista does not run package build scripts, but successful installation is
verified by importing the installed Python module. Importing a package executes
that package's Python code.

Only install packages and repositories you trust.

## Proven test cases

Development testing currently includes:

- PyATEMMax installed from its pure-Python source archive
- `discord` resolved through `discord.py`
- Existing `aiohttp` recognised from the Pythonista environment
- A metadata-only forwarding package
- Foreign Windows DLLs safely omitted from a universal wheel
- Transaction rollback after a dependency failure
- Dependency-aware uninstall protection
- Public GitHub snapshot installation and modification detection
- Fullscreen and panel presentation routes

## Planned first public beta

The initial release will include:

- A one-tap Pythonista installer
- Full source code
- User documentation
- A curated compatibility catalogue
- Automated smoke tests
- Release notes and version information

## License

Pipista is released under the MIT License.

## Project independence

Pipista is an independent community project. It is not affiliated with PyPI,
the Python Software Foundation, Pythonista, or omz:software.