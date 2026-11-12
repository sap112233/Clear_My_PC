# Accessibility

DesktopKeeper helps people organize files and start work with their installed
apps and favorite websites. These tasks should be usable by as many people as
possible, and people should be able to contribute without encountering
avoidable barriers. This document describes the project's current
accessibility goals, contributor guidance, known gaps, and how to report a
barrier.

## Priorities

We aim to make the desktop app understandable and usable with different ways
of interacting with a computer. In particular, we want to improve:

- Clear labels and instructions for controls and actions.
- Predictable keyboard navigation and visible focus.
- Readable text, sufficient contrast, and useful light and dark themes.
- Clear feedback when an action succeeds, fails, or needs confirmation.
- Plain-language help and error messages.

These are goals, not a claim that the app conforms to an accessibility
standard. We have not completed a formal accessibility evaluation.

## Contributor expectations

When changing user-facing behavior:

- Prefer descriptive text labels over icons alone. Give controls and dialogs
  clear names and explain consequential actions before they happen.
- Preserve a logical keyboard focus order and make the current focus visible.
  Do not make an action available only through a mouse or pointer.
- Keep text readable in both themes. Do not rely on color alone to communicate
  status or meaning.
- Check that errors and confirmations explain what happened and what the user
  can do next.
- Include accessibility considerations in pull request descriptions. For UI
  changes, describe the keyboard and visual checks performed and note any
  known gaps. Screenshots may help explain a visual change but are optional.
- If a change adds a known barrier, explain who may be affected and record a
  follow-up issue or an alternative where possible.

The current GitHub Actions workflow runs the project's unit tests and builds
for Windows, macOS, and Linux. It does not currently run automated
accessibility checks or assistive-technology tests. Contributors should not
describe those checks as passing unless they have actually been performed.

## Reporting accessibility issues

Report a barrier through
[GitHub Issues](https://github.com/sap112233/Clear_My_PC/issues/new). Start
the title with **Accessibility:** so maintainers can identify the report.

Useful details include:

- What you were trying to do and where you encountered the barrier.
- What you expected to happen and what happened instead.
- Your DesktopKeeper version and operating system/version.
- The input method or assistive technology involved, if you wish to share it.

Screenshots or recordings are optional. Please do not include passwords,
private files, or other sensitive information. You do not need to disclose a
disability or explain why you use a particular setup.

### Severity

You do not need to assign a severity. Maintainers can confirm it during
triage. These descriptions help explain the impact:

- **Blocking:** A user cannot complete an important task and there is no
  reasonable workaround; for example, a required confirmation cannot be
  reached or operated.
- **Major:** A key task is possible only with a substantial workaround or
  assistance; for example, essential information is unavailable to the
  user's chosen assistive technology.
- **Moderate:** A task is possible, but a barrier causes significant
  difficulty or repeated extra effort; for example, focus order makes a
  multi-step workflow hard to follow.
- **Minor:** A barrier is inconvenient or confusing but does not usually
  prevent task completion; for example, a nonessential label is unclear.

These are triage descriptions, not guaranteed response or resolution times.

### How we respond

Accessibility reports are handled through the project's public GitHub issue
tracker. A maintainer will review the report as capacity allows, may ask
follow-up questions, and may update its status or suggest a workaround.
There is no dedicated accessibility response team or guaranteed response
time. When a fix is available, reporters are welcome to verify it in their
environment and share whether the barrier is resolved.

## Ownership and maintenance

The project maintainers are responsible for reviewing accessibility reports,
considering accessibility in user-facing changes, and keeping this document
accurate. There is no separate accessibility team. Maintainers should revisit
this statement when the app's supported platforms or accessibility practices
change and when responsibility for project maintenance changes.

## Supported environments

DesktopKeeper provides desktop builds for Windows and macOS, with initial
Linux support. The project does not currently publish a tested matrix of
operating-system versions, display settings, input methods, or assistive
technologies.

The app is built with CustomTkinter. Keyboard, screen-reader, voice-control,
high-contrast, magnification, and other assistive-technology combinations
have not been systematically evaluated on any platform. Their support should
not be assumed; reports about specific setups are welcome.

## Known limitations

- The app has not had a formal accessibility audit or a systematic keyboard
  and screen-reader evaluation.
- The project has no documented compatibility results for screen readers,
  voice control, high-contrast settings, or magnification.
- The current automated tests check application behavior and safety, not
  accessibility.

These gaps do not mean that every workflow is inaccessible. They mean that
the project does not yet have evidence to make broader compatibility claims.
If you encounter a barrier, report it using the process above.

## Feedback and improvements

Suggestions for improving this statement or the project's accessibility
practices are welcome as a GitHub issue or pull request. Please use the
accessibility reporting process above for a barrier affecting the app itself.
