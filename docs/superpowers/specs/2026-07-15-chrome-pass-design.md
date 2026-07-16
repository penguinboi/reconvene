# Chrome Pass — Design

## What it is

A visual polish pass over both pages (`index.html` journal, `settings.html`), built on top of the
existing "Terminal" design system (see `2026-07-13-ui-polish-design.md`). No new backend
functionality except one new per-card metadata line — everything else is CSS/markup chrome:
consistent navigation, elevation/depth on cards, and smoother interaction states.

Approved through the brainstorming visual companion against a real rendered before/after mockup of
both pages (not abstract swatches).

## Shared topbar

Both pages currently show a bare `<h1>` with a loose `<a>` link floating below the content
(`Settings` on the journal, `Back` on Settings) — two loose documents, not one app. Replaced with a
`.topbar` element on both pages:

- Left: the "Reconvene" wordmark + blinking cursor (unchanged from the existing UI polish),
  wrapped in `<a href="/">` so it doubles as a home link.
- Right: one contextual nav link — `Settings` from the journal page, `Journal` from the settings
  page.
- `border-bottom: 1px solid var(--border)` separates it from page content, with `padding-bottom` /
  `margin-bottom` giving it room to breathe.

No new routes, no new IDs beyond what's needed for this — same `app.js`/`settings.js` DOM
dependencies stay intact (this only touches `index.html`/`settings.html` markup and `style.css`).

## Card elevation

`.project` cards (journal) currently rely on `filter: brightness(1.1)` on hover, with a flat
`--border` outline and no shadow at rest. Replaced with:

- Resting `box-shadow: 0 1px 2px rgba(0,0,0,0.3)` (subtle depth, not a heavy card look).
- On hover: deeper `box-shadow: 0 4px 12px rgba(0,0,0,0.45)` plus `transform: translateY(-2px)`.
- `transition: box-shadow 0.15s ease, transform 0.15s ease`.

Under `@media (prefers-reduced-motion: reduce)`, the `transform` is dropped (no lift) but the
shadow/color transitions still run — consistent with how the existing cursor blink already
respects this setting.

A new `.panel` class (settings sections, below) shares this same elevation treatment so both
pages read as one visual language.

## Settings restructure

Settings currently is flat, flowing HTML: a bare table, then a sequence of `<h2>`/`<label>`/`<p>`
elements with no visual grouping. Each logical section — project overrides table, "Hide by path",
"Recap generation", "Resume" — gets wrapped in a `.panel` div (same background/border/radius/shadow
as `.project` cards), with its heading inside the panel rather than floating above it. Purely a
markup/CSS change: no section's *content* (fields, labels, table columns) changes, so
`settings.js`'s existing element-ID lookups (`#projects`, `#hiddenPathSubstrings`, `#terminalApp`,
etc.) are untouched.

## Interaction polish

- Buttons: `transition: background-color 0.15s ease, transform 0.1s ease`; hover keeps the
  existing `--accent-hover` background and adds a 1px lift (dropped under reduced-motion).
- Inputs/select/textarea: `transition: border-color 0.15s ease, box-shadow 0.15s ease`; focus
  becomes a `box-shadow` glow in the accent color (matching the mockup) rather than the current
  hard `outline`.
- Links: underline transition on hover instead of an instant snap.

## New per-card metadata: last-active time + CWD

Prompted mid-brainstorm: today's card shows the recency *dot* (color-only) and session count, but
no explicit last-active time or working directory — both are data ccrider already gives us and
aren't shown anywhere. Adds one new muted, monospace metadata line per card, between the
name/count row and the recap excerpt:

```
2h ago · ~/Code/penguinboisoftware/reconvene
```

- **Relative time**: a new `relative_time(last_active, now=None) -> str` function in
  `journal.py`, next to `recency_bucket()`. Buckets: `"just now"` (<60s), `"Nm ago"` (<1h), `"Nh
  ago"` (<24h), `"Nd ago"` (<30d), `"Nmo ago"` (<365d), `"Ny ago"` (else). **Must reuse
  `recency_bucket`'s existing timestamp-parsing fix** — truncate to the fixed-width leading 19
  characters (`last_active[:19]`) before `strptime`, and default `now` to
  `datetime.now(timezone.utc).replace(tzinfo=None)` — ccrider's real `updated_at` format
  (`"2026-07-13 10:12:17.839 +0000 UTC"`) already broke `recency_bucket` once over this exact
  mismatch (see `test-fixtures-mirror-real-schema` memory); `relative_time` must not reintroduce
  it. Tested the same way `recency_bucket` is, including a regression test against the real
  ccrider format.
- **CWD**: the latest session's `project_path`, with the user's home directory prefix collapsed to
  `~` (e.g. `/Users/you/Code/foo` → `~/Code/foo`). A small helper (`abbreviate_home(path, home=None)
  -> str`) — plain string-prefix replacement; `home` defaults to `str(Path.home())` but is
  injectable (mirroring `recency_bucket`'s `now` parameter) so tests assert against a fixed fake
  home directory rather than depending on whichever machine runs the suite.
- Both exposed as new fields on `_project_summary()` in `server.py`:
  `last_active_relative` and `cwd`. `app.js` renders them in a new `.meta-line` element styled
  like the existing `.count` (monospace, `--text-muted`, smaller size).

**Not included** (YAGNI): `created_at`, aggregate message counts across a project's sessions, or
any other ccrider-provided field — the ask was specifically time + CWD; anything further needs its
own concrete request.

## Non-goals

- No new routes, no new backend behavior beyond the two new read-only fields above.
- No changes to resume/recap mechanics, classification, or settings persistence.
- No manual light/dark toggle — still system-preference-only, unchanged from the prior polish pass.
- No new runtime dependency.
- Same DOM structure for anything `app.js`/`settings.js`/the existing E2E suite already depends on
  — this is additive chrome plus one new metadata line, not a restructure of existing selectors.

## Testing

- `relative_time()` gets unit tests mirroring `recency_bucket`'s style: each bucket boundary, plus
  the real-ccrider-timestamp-format regression case.
- `abbreviate_home()` gets a couple of direct unit tests (path under home → `~`-prefixed; path not
  under home → returned unchanged).
- `_project_summary()` gains an assertion (in `test_web_server.py`) that `last_active_relative` and
  `cwd` are present and correctly derived.
- The chrome itself (topbar, card/panel elevation, transitions) is pure CSS/HTML: the existing
  Playwright E2E suite must continue to pass unchanged (still selecting `.project`, `#modalConfirm`,
  `#save`, etc.), proving structure/behavior wasn't broken, plus a manual real-browser check in
  both light and dark mode.
