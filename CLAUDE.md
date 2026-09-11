# Reconvene

ABOUTME: Map of this repo's docs, and the one hazard that is not written down anywhere else.
ABOUTME: README.md covers install, usage and testing. This file is orientation.

Reconvene resumes Claude Code sessions from a browser tab. It reads ccrider's session database,
ranks projects by recent activity, and lets you pick a session to continue. It is the public,
PII-free web spinoff of `pickup`.

## Where to look

- **`README.md`** for requirements, install, usage and how to run the tests.
- **`docs/debugging/2026-08-10-resume-picker-root-cause.md`** for why Resume was impossible on
  topic and loose groups, what changed, and the regression guards. Read it before touching the
  resume picker. It records a standing decision: groups preselect their latest session and keep
  showing the full picker. **Do not reintroduce the disabled Resume button.** If preselection ever
  becomes risky again, fix it with a clearer affordance, because the disabled state was invisible,
  offered no discoverable way to enable it, and read to the user as "I cannot resume at all".
- **`docs/superpowers/plans/`** for the implementation plans behind shipped features.

## Running it against real data

`_send_static` in `reconvene/web/server.py` resolves and reads each file per request, so edits to
`app.js` and `style.css` land on a hard browser refresh. Python changes still need a restart.

The installed entry point is an editable install pointing at this working copy. `pip show
reconvene` reports a stale version, so confirm what you are actually running with
`python3.11 -c "import reconvene; print(reconvene.__file__)"` rather than trusting it.

🚨 **Never click Resume from an automated browser script.** It launches a real terminal session,
configured in `~/.config/reconvene/config.json`, which by default passes
`--dangerously-skip-permissions`. Screenshot and assert against the page as much as you like, but
that one control has a side effect outside the browser.

## A bug class this codebase has already had

An interactive state painted with the same CSS token as its container renders as a state that
changes nothing. Both rules are individually correct and the bug lives only in their relationship,
so neither the Python suite nor a CSS linter can see it. When styling hover or selected states,
check the computed background of the container, not just the token name. The guards are in
`tests/e2e/test_journal_page.py` and compare `getComputedStyle` values.
