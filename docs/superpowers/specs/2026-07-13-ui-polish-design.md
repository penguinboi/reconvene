# UI Polish — Design

## What it is

A visual pass over both pages (`index.html` journal, `settings.html`) and their stylesheet.
Today's UI is unstyled system-font HTML: plain native buttons/inputs/selects, an unstyled
settings table, no color palette beyond gray borders, a hardcoded white background, and a bare
"Loading…" text with no empty-state handling. This gives Reconvene a considered, dev-tool-specific
identity without adding any new runtime dependency (no webfonts, no JS framework, no build step —
stays consistent with the stdlib-only philosophy).

Approved through the brainstorming visual companion against real rendered mockups of the journal
page (not abstract swatches).

## Visual direction: "Terminal"

Grounded in the app's actual subject (git/Claude Code sessions) rather than a generic AI dark
mode — the palette borrows GitHub's own dark/light theme language, since that's where these
sessions' artifacts already live.

**Color tokens** (CSS custom properties on `:root`, swapped via `prefers-color-scheme`):

| Token | Dark | Light |
|---|---|---|
| `--bg` | `#0d1117` | `#ffffff` |
| `--card-bg` | `#161b22` | `#f6f8fa` |
| `--border` | `#30363d` | `#d0d7de` |
| `--text` | `#e6edf3` | `#1f2328` |
| `--text-muted` | `#8b949e` | `#57606a` |
| `--accent` | `#238636` | `#1a7f37` |
| `--accent-hover` | `#2ea043` | `#22903f` |
| `--link` | `#58a6ff` | `#0969da` |

Follows system light/dark automatically — no in-app toggle (one less thing to build/maintain;
`prefers-color-scheme` already does this correctly for a single-user local tool).

**Typography** — a deliberate pairing, no external fonts (offline/local-first, no network
dependency at page load):
- Headings and the "Reconvene" wordmark: `ui-monospace, "SF Mono", Menlo, monospace` — ties the
  app's identity to a terminal from the first glance.
- Body copy (recap paragraphs — now up to 600 words per the recent verbosity change): system sans
  (`-apple-system, "Segoe UI", sans-serif`) — readability over identity at that length.
- Metadata (session counts, last-active): monospace, muted color, smaller size.

**Signature element:** a recency dot before each project name, colored by `last_active`:
- Bright green (`--accent`) — active within 24h
- Amber (`#d29922` / `#9a6700`) — active within 7 days
- Dim gray (`--text-muted`) — older

This is real data already available on each project (`last_active`), not decoration — it mirrors
how `tmux`/iTerm session lists already use colored status dots, so it reads as native to the
domain. Paired with a blinking cursor (`▊`) after the "Reconvene" wordmark, styled as a CSS
`@keyframes` blink — a terminal prompt waiting for input, which is literally what the app is
waiting for (a session to resume). Respects `prefers-reduced-motion: reduce` (static, no
animation, when set).

The bucketing itself is real logic, computed server-side (not in JS): a `recency_bucket(last_active,
now=None)` function in `journal.py` (mirrors `classify_category`'s pattern — pure function, `now`
injectable for testability, defaults to `datetime.now()`), returning `"active"` (within 24h),
`"recent"` (within 7 days), or `"stale"` (older). `_project_summary` in `server.py` exposes it as a
`recency` field; `app.js` renders the dot via a CSS class (`.dot-active` / `.dot-recent` /
`.dot-stale`) keyed off that field rather than computing dates in JavaScript.

## Component styling

- **Buttons** (`Resume`, `Cancel`, `Save`): solid `--accent` background, white text,
  `border-radius: 6px`, `--accent-hover` on hover. Replaces today's fully unstyled native buttons.
- **Inputs / select / textarea**: `--border` border, `--card-bg` background, `--text` color, focus
  ring in `--accent`.
- **Settings table**: bordered rows, `--border` dividers, comfortable cell padding
  (`0.5rem 0.75rem`), project names in the same mono-metadata style as the journal cards.
- **Project cards**: `--card-bg` background, `--border` border, `border-radius: 6px`, recency dot,
  mono metadata line, sans recap paragraph.
- **Modal**: re-themed to the same tokens (already has `max-height`/scroll from the earlier
  truncation fix — unchanged).
- **Error banner**: re-themed (currently hardcoded red-on-pink; becomes a themed error token pair,
  same semantic color logic, works in both light and dark).

## Loading & empty states

- **Loading**: replace the bare "Loading…" text with a centered, `--text-muted` placeholder. No
  spinner — keeps this dependency-free and consistent with the rest of the no-JS-library
  approach.
- **Empty** (zero real projects returned by `/api/journal`): centered message in `--text-muted`:
  "No projects yet — resume some Claude Code sessions and they'll show up here." Written in the
  interface's own voice (an invitation to act, not an apology), per the same plain/active-voice
  principle already used elsewhere in the app (e.g., the resume-failure error text).

## Non-goals

- No manual light/dark toggle — system preference only.
- No new runtime dependency (no webfonts, no icon library, no CSS framework, no JS framework).
- No layout/IA changes — same pages, same routes, same DOM structure/IDs that `app.js`/`settings.js`
  and the existing E2E tests already select against. This is a re-skin, not a redesign of
  structure.
- No changes to backend logic, recap generation, or resume mechanics — purely `style.css` plus the
  markup needed to add the recency dot and cursor span.

## Testing

Existing E2E tests (`tests/e2e/test_journal_page.py`, `tests/e2e/test_settings_page.py`) assert
against element IDs/classes and text content, not colors or fonts — they should continue to pass
unchanged, proving the re-skin didn't break structure or behavior. One new thing worth a test: the
recency-dot color classification (given a `last_active` timestamp, which of the three states is
chosen) is real logic, not pure CSS, so it gets a unit test the same way `classify_category` does.
The empty-state message is also worth an E2E assertion (zero-project journal renders the
invitation text, not a blank `<div>`).
