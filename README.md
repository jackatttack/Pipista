# Pipista

Pipista is a small package manager for
[Pythonista](https://omz-software.com/pythonista/) on iPhone and iPad.

It gives you one simple place to find, install and remove Python packages from
PyPI, or download public GitHub projects. It is aimed at people who do not want
to set up StaSh or work from a command line.

Pipista is currently a public beta.

## Install

Create a new Python file in Pythonista, paste this in and run it once:

```python
from urllib.request import urlopen

url = (
    'https://raw.githubusercontent.com/'
    'jackatttack/Pipista/main/install_pipista.py'
)
source = urlopen(url).read()
exec(compile(source, 'install_pipista.py', 'exec'))
```

The installer creates a `Pipista` folder in your Pythonista Documents and opens
the main launcher when it is finished.

You can also read
[`install_pipista.py`](install_pipista.py) before running it.

## Launching Pipista

Run `Pipista.py` to launch Pipista.

`pipista_app.py` contains the application interface used by the launcher. Most
users only need to open `Pipista.py`.

## Try humanize

Open Pipista, stay on the **PyPI** tab and choose `humanize`.

Tap **Inspect**, then **Install**. Pipista will show you what it plans to do
before changing anything.

You can test the installed package in a separate Pythonista file:

```python
import humanize

number = humanize.intcomma(1234567)
print(number)
```

This should print `1,234,567`.

Humanize is the standard Pipista example because it is pure Python, useful and
easy to check without relying on another web service.

## Searching PyPI

Pipista can download PyPI's project-name index so you can filter the full list
as you type. Press **Sync** the first time you want this.

Syncing is manual. The list is only refreshed when you press **Refresh** or
**Sync** again.

You can still enter an exact package name and inspect it without syncing the
full list.

## GitHub projects

Open the **GitHub** tab and enter:

`owner/repository`

You can also paste a public GitHub URL. Pipista downloads the repository as a
managed, editable project.

GitHub projects are kept separate from installed Python packages.

## Installed items

The **Managed** view shows packages and projects installed through Pipista and
lets you remove them again.

The **Environment** view shows other modules already available in Pythonista.
It is read-only, so Pipista will not remove things it did not install.

Pipista also keeps track of dependencies. It installs them in the order they are
needed and will not remove one while another managed package still depends on
it.

## Where files go

- Pipista: `~/Documents/Pipista`
- Pipista data and PyPI index: `~/Documents/.pipista`
- GitHub projects: `~/Documents/Pipista Projects`
- Python packages: Pythonista's user `site-packages`

These paths are worked out for the current Pythonista user. They are not tied
to the developer's device.

## A few limits

Pipista is intentionally more cautious than desktop `pip`.

It works best with pure-Python packages. Packages that need compiled extensions,
system tools or unsupported iOS features may not work.

Pipista checks archives, verifies PyPI downloads, avoids overwriting unmanaged
files and rolls back dependency installs when something fails. It does not run
downloaded build scripts such as `setup.py`.

It does import a package after installation to check that it works. Importing
Python code executes that code, so only install packages and repositories you
trust.

## Updating Pipista

Run the installation snippet again.

Your existing app is moved into `~/Documents/.pipista/backups` before the new
copy replaces it. Pipista's package records and PyPI index are kept.

## Uninstalling Pipista itself

Delete the `~/Documents/Pipista` folder.

If you also want to remove Pipista's saved data and index, delete
`~/Documents/.pipista`. Packages already installed into `site-packages` are not
removed by deleting the app.

## License

MIT. See [LICENSE](LICENSE).

Pipista is an independent community project and is not affiliated with
Pythonista, PyPI or the Python Software Foundation.
