# Contributing to DesktopKeeper

Thanks for considering a contribution. Bug reports, thoughtful feature
proposals, documentation improvements, and code changes are welcome.

## Before you start

- For a significant change, open an issue first to discuss the problem and
  approach. This helps avoid work that does not fit the project's direction.
- For a small, clear fix, you can open a pull request directly.
- Check existing issues and pull requests for related work.
- Be respectful in project discussions and follow the
  [Code of Conduct](./CODE_OF_CONDUCT.md).

## Development setup

The project requires Python 3.9 or newer. From the repository root:

```bash
python3 -m venv .venv
```

Activate the environment, then install dependencies and run the test suite:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -v
```

On systems where Tk is not included with Python, install the operating
system's Tk package before running the GUI. To start the app from source:

```bash
python gui.py
```

The GitHub Actions workflow runs tests and builds on Windows, macOS, and
Linux. Run the tests relevant to your change locally; if you cannot test on
every platform, say which platform you did test and what remains unverified.

## Making a change

- Keep changes focused and consistent with existing patterns.
- Add or update tests when behavior changes.
- Preserve safety properties: preview consequential file operations, avoid
  overwriting user data, and validate paths and external input.
- Do not include secrets, personal data, generated build output, or unrelated
  changes.
- For interface changes, consider keyboard use, focus, readable text, and
  error feedback. See [Accessibility](./ACCESSIBILITY.md).
- For security-sensitive changes, see [Security Policy](./SECURITY.md).

## Pull requests

Before opening a pull request:

1. Run `python -m unittest discover -v`.
2. Review your diff for unrelated files, accidental data, and whitespace
   errors.
3. Describe the problem and the change, link related issues, and explain any
   behavior or configuration impact.
4. Report the tests and platforms you actually checked. Do not claim checks
   that you did not run.
5. Add screenshots for visual changes when useful; screenshots are optional.

The pull request template is a checklist to help reviewers. It is fine to
mark an item as not applicable and explain why.

## Reporting bugs and requesting features

Use the repository's GitHub issue forms for bug reports, feature requests,
and accessibility barriers. Do not report security vulnerabilities in a
public issue; follow the private reporting instructions in
[SECURITY.md](./SECURITY.md).
