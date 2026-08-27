# Security policy

## Supported version

Security fixes currently target the latest public beta.

## Reporting a vulnerability

Please do not publish a working exploit or sensitive vulnerability details in a
public issue.

Contact the repository owner privately through GitHub where possible. Include:

- the affected Pipista version;
- the package or repository involved;
- the smallest reproducible sequence;
- the security impact;
- whether files, credentials or user data were exposed; and
- any suggested mitigation.

Do not include GitHub tokens, Pythonista secrets or private source code.

## Security boundaries

Pipista validates downloads and avoids executing package build systems, but
installed Python code is not sandboxed. Import verification executes the
installed package's Python code with the permissions available to Pythonista.

Only install software you trust.