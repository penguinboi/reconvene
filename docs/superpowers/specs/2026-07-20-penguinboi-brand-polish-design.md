# Penguinboi Software Brand Polish — Design

Add tasteful Penguinboi Software identity + attribution across reconvene, without
disrupting its deliberate GitHub-dark, functional dev-tool aesthetic. Brand level:
"a bit more visible" (the penguin is actually seen, not just in the browser tab).

## Non-goals (explicit restraint)

- No games-brand fonts (Press Start 2P, Tangerine) — they clash with a dev tool.
- No navy repaint — reconvene keeps its GitHub-dark palette (`#0d1117` / green accent).
- No OG/social-card meta — reconvene runs on `127.0.0.1`; nobody shares localhost links.
- No branding inside the fzf preview/pickers — they already carry key-hint headers.
- LICENSE copyright stays "Skyler Lister Aley" (correct).

## Surfaces

### 1. Favicon (sourced from the landing page)
Copy the existing penguin+d20 favicon set from `../landing/` into
`reconvene/web/static/`: `favicon.png`, `favicon-16x16.png`, `favicon-32x32.png`,
`apple-touch-icon.png`. Reference them in the `<head>` of both `index.html` and
`settings.html`. Add them to `pyproject.toml` `[tool.setuptools.package-data]` so an
installed copy serves them too.

### 2. Topbar logo mark
A ~22px penguin logo (`favicon.png`) immediately left of the `Reconvene▊` wordmark in
the topbar, on both pages. `alt="Penguinboi Software"`. A `.topbar-logo` style sizes it
and aligns it with the `h1` baseline; the blinking `▊` cursor stays.

### 3. Footer (both pages)
A single quiet line, in reconvene's own muted palette (`--text-muted`, small, centered,
top border) — NOT the landing's bordered/blurred card:

> 🐧 A **Penguinboi Software** tool · Made with ❤️ and 🧠

"Penguinboi Software" links to `https://penguinboisoftware.com`
(`rel="noopener noreferrer"`). Shared markup in `index.html` and `settings.html`
(a `<footer class="site-footer">`).

### 4. theme-color meta
`<meta name="theme-color" content="#0d1117">` in both pages' `<head>` — matches
reconvene's actual dark background (kept consistent with the real page rather than
forcing the brand navy).

### 5. README footer
Append a footer section:

> ---
> 🐧 A [Penguinboi Software](https://penguinboisoftware.com) tool. Made with ❤️ and 🧠.

### 6. Authorship (`pyproject.toml`)
- `authors = [{ name = "Skyler Lister Aley", email = "penguinboisoftware@gmail.com" }]`
- Add to `[project.urls]`: `"Penguinboi Software" = "https://penguinboisoftware.com"`

### 7. CLI byline
The startup chooser's first printed line becomes:
`Reconvene — a Penguinboi Software tool`
(the only CLI branding; the `[1] Web view / [2] TUI` prompt is unchanged).

## Testing

- **Unit (`test_cli.py`):** the chooser output contains "Penguinboi Software"
  (capture the `_choose_frontend` / chooser print via the injected `input_fn`).
- **E2E (`test_journal_page.py`):** the journal page shows a `.site-footer` linking to
  `penguinboisoftware.com`, and the topbar has an `img.topbar-logo`.
- **Static check:** `index.html` and `settings.html` both reference `favicon.png` and
  the `theme-color` meta (a small unit test reading the static files, or fold into the
  e2e assertions).
- Favicons are binary assets (no test); confirm they're byte-identical copies of the
  landing set and served (200) by the server.

## Out of scope (YAGNI)
Animated mascot, a web manifest / installable PWA, dark/light logo variants, a settings
"About" page.
