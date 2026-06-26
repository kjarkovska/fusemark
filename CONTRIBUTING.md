# Contributing to FuseMark

Thanks for your interest in contributing. FuseMark is a small solo-maintained project, so contributions are reviewed manually and selectively merged.

## Before you open a PR

- Open an issue first and wait for a response before writing code. This avoids wasted effort on changes that won't be accepted.
- PRs submitted without a prior issue discussion will generally be closed.
- Automated or bot submissions are not welcome and will be closed immediately.

## What is in scope

- Bug fixes for confirmed issues (linked to an open issue)
- Small, targeted improvements — one concern per PR
- Windows 11 / Python 3.11+ only — do not submit cross-platform abstractions

## What is out of scope

- New features not discussed in an issue
- Refactors of working code
- Dependency swaps for libraries already chosen in the tech stack
- CI/CD, tooling, or workflow changes

## PR requirements

- The PR must reference the issue it closes (`Closes #N`)
- All existing tests must pass (`pytest`)
- New behaviour must be covered by a test
- No new files outside the established project structure (`app/`, `tests/`, `templates/`, `static/`)
- No new top-level scripts or utility files

## Review process

All PRs from external contributors require manual approval before any CI runs. First review may take a few days. If you don't hear back within two weeks, feel free to ping the issue thread.

## Security issues

Do not open a public issue for security vulnerabilities. Email [karla@jarkovska.eu](mailto:karla@jarkovska.eu) instead.
