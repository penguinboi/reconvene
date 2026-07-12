# Reconvene — Design

## What it is

A standalone, public, open-source local web app that generalizes pickup's project-journal
concept: it reads ccrider's session database, ranks and classifies projects (real work vs.
automated runs vs. noise), and lets you resume a Claude Code session — through a browser tab
instead of fzf.

pickup (a private tool) proved out the hard problems: grouping ccrider's flat session list into
ranked projects, telling genuine multi-turn work apart from one-shot automated/scripted calls,
and generating LLM recaps cheaply. Reconvene ports that logic and removes everything that was
hardcoded to one person's machine, so it can be released publicly with no PII and no assumptions
about the user's specific projects.

## Non-goals (v1)

- Not multi-agent. Claude Code only — ccrider tracks 5 agent CLIs (Claude Code, Codex, Copilot,
  OpenCode, Pi), but the resume/recap logic only knows how to drive Claude Code. Multi-agent
  support is a plausible future iteration, not v1.
- Not cross-platform. The resume action opens a new terminal window via a macOS-specific
  mechanism. Linux/Windows support is out of scope for v1.
- Not a rewrite of ccrider. Reconvene depends on ccrider (MIT licensed, github.com/neilberkman/ccrider)
  for session discovery, sync, and storage. It does not re-implement transcript parsing.

## Architecture

A single Python process starts a local web server bound to `127.0.0.1` (never exposed to the
network) and opens the user's default browser to it. Stdlib-only, no third-party pip
dependencies — matching pickup's existing philosophy (`http.server`/`ThreadingHTTPServer` with
hand-rolled routing; static HTML/CSS/vanilla JS, no build step). The alternative considered was a
FastAPI+uvicorn stack (the pattern used by Pebblebook, another local-web-UI project by the same
author) — rejected for v1 because Reconvene's surface area is small (4-5 endpoints) and staying
dependency-free keeps install as simple as pickup's today.

## Components

Mapping pickup's modules onto Reconvene:

- **`db.py`** — ported as-is. Read-only ccrider access; nothing personal in here (the ccrider DB
  path convention, `~/.config/ccrider/sessions.db`, is ccrider's own default).
- **`classify.py`** — same classification logic, but `classify_category` takes a `Config` object
  instead of reading module-level `BOT_NAMES`/`DROP_NAMES` constants. The message-count
  thresholds (`BOT_PROMOTE_MESSAGE_COUNT = 30`, `NOISE_MESSAGE_FLOOR = 2`) stay as built-in
  defaults — validated heuristics, not personal to any one user.
- **`journal.py`** — same grouping/ranking, takes a `Config` in.
- **`recap.py`** — same `claude_runner`/fallback-chain logic, carrying forward the neutral-cwd
  fix already shipped in pickup (`cwd=tempfile.gettempdir()` on the `claude -p` subprocess, so
  recap generation never pollutes the user's own project session history). Auth mode (see below)
  comes from `Config`.
- **`config.py`** (new) — a `Config` dataclass persisted to `~/.config/reconvene/config.json`:
  per-project classification overrides (Real / Automated / Hidden), recap auth mode, optional API
  key. This is the generalization layer that replaces pickup's hardcoded `constants.py`.
- **`resume.py`** — ported as-is (`claude --resume <id>`, Claude-Code-only).
- **`web/`** (new) — `server.py` (stdlib HTTP routes: journal page, resume action, settings page)
  + static assets (HTML/CSS/vanilla JS). Replaces `cli.py`'s fzf picker entirely.

## Data flow & onboarding

- **Zero-config default.** The message-count heuristic alone classifies every project the
  moment ccrider has synced. A new user with no `config.json` gets a working, sensibly-classified
  journal immediately — no mandatory setup wizard.
- **Settings page (optional, anytime).** Lists every detected project with its computed
  classification and stats (session count, last active, avg message count). The user can pin an
  explicit override — Real / Automated / Hidden — per project name. Overrides persist to
  `config.json` and take precedence over the heuristic. This exists for the cases where the
  heuristic gets something wrong for a specific user's setup (e.g. a scheduled-agent repo whose
  calls happen to run long).
- **Main page request flow:** browser hits `/` → server loads `Config`, pulls sessions from
  ccrider's DB, runs `build_journal` → returns ranked HTML immediately using the cheap
  `first_user_message` fallback → client-side JS fetches `/recap/<project>` per card
  asynchronously to fill in full recaps as they complete. (This is strictly better UX than
  pickup's CLI, which has to generate every recap before showing the picker at all.)
- **Resume flow:** click a project card → `POST /resume/<session_id>` → server opens a new
  terminal window (macOS `open -a Terminal`/AppleScript) running `claude --resume <id>` in the
  session's project directory. Chosen over (a) showing a copy-pasteable command or (b) a full
  embedded terminal (xterm.js + PTY bridge) — (a) is lower value than automating it, (b) is much
  bigger scope than v1 needs.

## Error handling

- `ccrider` not installed/on PATH → clear startup error with the install instruction
  (`brew install neilberkman/tap/ccrider`), not a stack trace.
- `claude` CLI not installed/not logged in → resume attempt surfaces an inline UI error, not a
  silent failure.
- Recap generation failures → same fallback chain `recap.py` already has (derive from first
  message → `"(recap failed)"`).
- Local web server port conflict → try a few ports in sequence; fail loudly with a clear message
  if none are free (no silent fallback to an unannounced port).

## Testing

Mirrors pickup's existing pytest suite structure: per-module unit tests, a shared `ccrider_db`
fixture. New coverage needed for:
- `config.py` — load/save round-trip, override-precedence-over-heuristic behavior.
- `web/server.py` — route tests via real HTTP requests against a test server instance, with an
  injected fake resumer (same pattern pickup's CLI tests already use for the picker).

Vanilla JS stays thin enough that it likely doesn't need its own test framework for v1 — revisit
if the frontend grows real client-side logic.

## Distribution & PII

This is the section that motivated the whole project:

- Fresh repo (`penguinboi/reconvene`), clean git history from day one, MIT license, plus a
  `THIRD_PARTY_LICENSES` note crediting ccrider (MIT, Neil Berkman,
  github.com/neilberkman/ccrider).
- `config.json` (project-name overrides, etc.) lives in `~/.config/reconvene/`, **never
  committed to the repo.** This is what actually solves the original problem: pickup's
  `constants.py` baked real project names into git; Reconvene's equivalent data never enters git
  at all.
- Design docs written generically — no references to a specific person by name, unlike pickup's
  own design docs.
- Commit author name/email is the user's call at implementation time — not decided by this spec.

## Naming

Project name: **Reconvene** — checked against GitHub (no exact-match repo) and PyPI (name
unclaimed) on 2026-07-12. "pickup" itself was considered and rejected: the exact PyPI package
name is already taken by an unrelated "modular backup script" package.
