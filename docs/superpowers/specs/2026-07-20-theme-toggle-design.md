# Light / Dark Mode Toggle — Design

Add a manual theme toggle to reconvene's web UI. Today the CSS only *follows* the
system preference (`@media (prefers-color-scheme: dark)`) with no way to override.
Add an **Auto / Light / Dark** cycle; Auto (system-follow) stays the default so
current behavior is unchanged for anyone who doesn't touch the toggle.

Pure frontend — the Python backend and the existing palettes are unchanged; only how
the palettes are *selected* changes.

## Control

A `<button id="themeToggle" class="theme-toggle">` at the right of the topbar, in a new
`<div class="topbar-right">` wrapper that also holds the existing right-hand link
(Settings on the journal page, Journal on the settings page). Both pages get it.

- Cycles **Auto → Light → Dark → Auto** on click.
- Its text content is the current-mode icon: `🖥` (auto), `☀️` (light), `🌙` (dark).
- `aria-label` / `title` describes state + next, e.g. `Theme: Auto (follows system) — click for Light`.
- Styled minimal: transparent background, no border, `cursor: pointer`, sized to the
  topbar, muted color; hover slightly brightens. No layout shift between icons.

## State & behavior

- `localStorage['reconvene-theme']` holds `light` | `dark` | `auto`. Missing or `auto`
  ⇒ auto.
- **Applying** (shared logic): `light`/`dark` ⇒ `document.documentElement.dataset.theme =
  value`; `auto` ⇒ `delete document.documentElement.dataset.theme` (media query takes over).
- **Click** advances the cycle, writes `localStorage`, applies, and updates the button
  icon + label.
- **No flash:** a tiny inline script in `<head>` of both pages (before the stylesheet)
  reads `localStorage` and sets `data-theme` before first paint. It must be inline —
  an external script would still flash. The same read is duplicated by the toggle
  wiring after load to sync the button icon.

## CSS restructure (`style.css`)

Keep both existing palettes; change only the selectors:

```css
:root { /* existing light vars — unchanged */ }

@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) { /* existing dark vars — AUTO: follow the OS */ }
}

:root[data-theme="dark"] { /* the SAME dark vars — explicit override */ }
```

- Explicit **light** needs no rule: `data-theme="light"` makes the media query's
  `:root:not([data-theme])` stop matching, so the base light `:root` wins.
- The dark var block is duplicated once (media query + attribute rule). CSS custom
  properties can't be shared across a media-query boundary and a plain rule, so this
  duplication is the standard, readable trade. A comment marks the two blocks as a pair
  to keep in sync.

## Files

- `reconvene/web/static/index.html` — inline head theme script; wrap right controls +
  toggle button.
- `reconvene/web/static/settings.html` — same head script; wrap Journal link + toggle.
- `reconvene/web/static/theme.js` (new) — the cycle/click wiring + `applyTheme`/`nextTheme`
  helpers, loaded on both pages. (The pre-paint apply stays inline in `<head>`; this file
  handles the button after load. Two `ABOUTME:` lines.)
- `reconvene/web/static/style.css` — the selector restructure + `.topbar-right` +
  `.theme-toggle` styles.
- `pyproject.toml` `package-data` already ships `static/*.js`; no change.

## Testing (TDD, Playwright)

`tests/e2e/test_theme_toggle.py`:
- Toggle button is present in the topbar.
- Clicking cycles `data-theme`: auto (no attr) → `light` → `dark` → auto, and the
  button icon changes accordingly.
- `localStorage['reconvene-theme']` reflects each state.
- **Persistence across reload:** set to `light`, reload, assert the page renders light —
  by the computed `background-color` of `<body>` (proves the pre-paint script ran), not
  just the attribute.
- With no stored preference, no `data-theme` attribute is set (auto path intact).

## Non-goals (YAGNI)

- A duplicate control on the settings page's form / a dropdown.
- Theme transition animations.
- Syncing theme to server config or across devices (it's a local single-user tool).
- Changing the palettes themselves.
