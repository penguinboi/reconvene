# Agent Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resume every ccrider session in the agent that made it (Claude, Codex, Antigravity), and let the web page hand a session to a different agent with a summary written by that agent.

**Architecture:** A new `agents.py` holds the per-agent facts (binaries, argv shapes, transcript locations). `resume.py` uses it for native resume and exposes a generic terminal launcher. A new `handoff.py` exports the session, has the incoming agent summarize it headlessly in the temp dir, then launches the incoming agent in the session's directory. The server picks resume or handoff from an `agent` field on the existing resume POST; the Resume modal gains an "Open in" switch.

**Tech Stack:** Python 3.11+ stdlib, vanilla JS, pytest + pytest-playwright.

**Spec:** `docs/superpowers/specs/2026-11-02-agent-handoff-design.md`

## Global Constraints

- Every new code file starts with two `# ABOUTME: ` lines (JS: `// ABOUTME: `).
- ccrider DB access stays read-only (`mode=ro`).
- 🚨 No test may open a real terminal or run a real agent. Inject `runner`, `launcher`, `which`, `execvp`, as the existing tests do.
- Agent names are ccrider's `provider` values: `claude`, `codex`, `antigravity`. Labels: `Claude`, `Codex`, `Antigravity`. Binaries: `claude`, `codex`, `agy`.
- Handoff exports go to `~/.config/reconvene/handoffs/`, never the project repo.
- The summary step runs with `cwd=tempfile.gettempdir()` and never receives the per-agent extra args.
- Keep `claude_extra_args`; add `codex_extra_args` and `antigravity_extra_args` (default `""`). No config migration.
- Do not reintroduce the disabled Resume button (`docs/debugging/2026-08-10-resume-picker-root-cause.md`).
- Commits: no AI attribution lines. Never `--no-verify`.
- Run tests: `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/pytest tests/ -q`. Output must be clean apart from the known pytest-playwright `base_url` deprecation warning.

## Review Focus

1. **Session directory deleted:** a handoff must fail before the summary step runs, so no usage is spent (Task 4, `test_handoff_missing_directory_fails_before_summary`).
2. **Summary agent exits 0 with blank output:** treat as failure and launch nothing (Task 4, `test_handoff_blank_summary_launches_nothing`).
3. **Codex ids:** a `rollout-...-<uuid>` session id resumes by its trailing UUID, and a non-empty `resume_via` wins (Task 2, `test_codex_resume_uses_trailing_uuid`, `test_codex_resume_prefers_resume_via`).
4. **Summary text with quotes, backslashes and newlines** must survive shell quoting and AppleScript escaping into the terminal (Task 4, `test_handoff_prompt_with_quotes_survives_terminal_script`).
5. **Double click during the 20 to 60 second wait** must not start two handoffs (Task 6, `test_handoff_button_disabled_while_working`).

---

### Task 1: Sessions carry their agent; sub-agent rows hidden

**Files:**
- Modify: `reconvene/db.py`
- Modify: `tests/conftest.py` (schema gets `resume_via TEXT`; `add_session` gains `provider="claude", resume_via=""`)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `Session` gains `provider: str` and `resume_via: str` as its last two fields (NULL provider → `"claude"`, NULL resume_via → `""`). `REQUIRED_SESSION_COLS` adds `"provider"`, `"resume_via"`.
- Produces: `load_sessions(db_path) -> list[Session]` excludes rows whose `resume_via` is non-empty.
- Produces: `find_session(db_path, session_id: str) -> Session | None`, which includes sub-agent rows.
- Produces: `session_messages(db_path, session_id, limit=40, newest=False)`. With `newest=True` it returns the last `limit` messages, still in sequence order.

- [ ] **Step 1: Write failing tests** in `tests/test_db.py`:
  - `test_load_sessions_reports_provider`: add a `codex` session and a session with provider NULL; assert `.provider` is `"codex"` and `"claude"`.
  - `test_load_sessions_hides_subagent_rows`: add a codex row with `resume_via="01a0f33f-f98b-7121-81e4-10e170c054b4"`; assert it is absent from `load_sessions` and present via `find_session`, with `.resume_via` set.
  - `test_probe_schema_requires_provider_and_resume_via`: drop the columns from a DB; assert `RuntimeError` naming them.
  - `test_session_messages_newest_returns_tail_in_order`: 5 messages, `limit=2, newest=True` → messages 4 and 5, in that order.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_db.py -q`. Expected: the four new tests FAIL.
- [ ] **Step 3: Implement** the interfaces above in `reconvene/db.py`.
- [ ] **Step 4: Run** the full suite. Expected: PASS (fix any test that built `Session` positionally).
- [ ] **Step 5: Commit** `feat: sessions carry their agent; hide Codex sub-agent rows`.

### Task 2: Agent registry and argv builders

**Files:**
- Create: `reconvene/agents.py`
- Modify: `reconvene/config.py` (two new fields, in `from_dict` too)
- Test: `tests/test_agents.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `Session` from Task 1; `MODEL` from `constants.py`.
- Produces:
  - `@dataclass(frozen=True) class Agent: name: str; label: str; binary: str`
  - `AGENTS: dict[str, Agent]` in the order claude, codex, antigravity.
  - `get_agent(name: str) -> Agent`, raising `ValueError(f"unknown agent {name!r}")`.
  - `extra_args_for(name: str, config) -> list[str]` (shlex-split of that agent's config field; `[]` when config is None).
  - `native_session_id(session) -> str`: `resume_via` if set; for codex, the trailing 36-char UUID of `session_id`; otherwise `session_id`.
  - `resume_argv(session, prompt: str, extra: list[str]) -> list[str]`
  - `fresh_argv(name: str, prompt: str, extra: list[str]) -> list[str]`
  - `headless_argv(name: str, prompt: str, output_file: str) -> list[str]`
  - `transcript_path(session, home: Path) -> Path | None` (first match, else None)
  - `installed_agents(which=shutil.which) -> dict[str, bool]`

Exact argv shapes (from the spec's table; options before positionals):

| | claude | codex | antigravity |
|---|---|---|---|
| resume | `claude --resume <id> *extra <prompt>` | `codex resume *extra <id> <prompt>` | `agy --conversation <id> *extra` (no prompt: unverified that it accepts one) |
| fresh | `claude *extra <prompt>` | `codex *extra <prompt>` | `agy *extra -i <prompt>` |
| headless | `claude -p --model <MODEL> --no-session-persistence <prompt>` | `codex exec --ephemeral --skip-git-repo-check -s read-only -o <output_file> <prompt>` | `agy -p <prompt>` |

Transcript globs under `home`: claude `.claude/projects/*/<session_id>.jsonl`; codex `.codex/sessions/*/*/*/<session_id>.jsonl`; antigravity `.gemini/antigravity-cli/conversations/<session_id>.db`.

- [ ] **Step 1: Write failing tests** in `tests/test_agents.py`, one per argv cell above with exact lists, plus:
  - `test_codex_resume_uses_trailing_uuid`: `session_id="rollout-2026-11-01T19-54-00-01a19a64-6dff-7983-9653-7af460dbd4e9"` → id `01a19a64-6dff-7983-9653-7af460dbd4e9`.
  - `test_codex_resume_prefers_resume_via`.
  - `test_get_agent_rejects_unknown`.
  - `test_transcript_path_finds_each_agent` (build the three layouts under `tmp_path`) and `test_transcript_path_missing_returns_none`.
  - `test_installed_agents_uses_which` with a fake `which`.
  - In `tests/test_config.py`: `test_config_round_trips_agent_extra_args`, and that a config dict without the new keys loads them as `""`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_agents.py tests/test_config.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `reconvene/agents.py` and the config fields.
- [ ] **Step 4: Run** the same tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: agent registry for Claude, Codex and Antigravity`.

### Task 3: Native resume per agent

**Files:**
- Modify: `reconvene/resume.py`, `reconvene/tui.py`, `reconvene/cli.py`, `reconvene/web/server.py` (resume route only)
- Test: `tests/test_resume.py`, `tests/test_tui.py`, `tests/test_web_server.py`, `tests/e2e/conftest.py` (fake resumer signature)

**Interfaces:**
- Consumes: `resume_argv`, `extra_args_for`, `get_agent` (Task 2); `find_session` (Task 1).
- Produces:
  - `resume_command(session, extra: list[str] = (), now=None) -> list[str]`: `resume_argv(session, resume_prompt(session.updated_at, now), list(extra))`.
  - `launch_in_terminal(argv: list[str], cwd: str, config=None, runner=subprocess.run, path_exists=os.path.isdir, system=None, which=shutil.which, env=None) -> None`: the body of today's `open_terminal_and_resume`, taking a ready argv. Same `FileNotFoundError` on a missing `cwd`.
  - `open_terminal_and_resume(session, config=None, now=None, **launch_kwargs) -> None`: `launch_in_terminal(resume_command(...), session.project_path, config, ...)`.
  - `exec_resume(session, config=None, path_exists=..., chdir=..., execvp=...) -> None`: execs `get_agent(session.provider).binary`.
  - Server resumer callable signature becomes `resumer(session)`. The `/api/resume/` route looks the session up with `find_session` (so search hits on sub-agent rows still resume).
  - TUI resumer signature becomes `resumer(session, config)`.

- [ ] **Step 1: Update and add failing tests:**
  - Rewrite the existing `resume_command`/`open_terminal_and_resume`/`exec_resume` tests to pass a `Session`; expected argv for claude is unchanged from today.
  - `test_resume_command_codex_session` and `test_exec_resume_execs_codex_binary` (fake `execvp` records `"codex"`).
  - `test_open_terminal_and_resume_uses_agent_extra_args`: config `codex_extra_args="--full-auto"` appears for a codex session, `claude_extra_args` does not.
  - `test_resume_route_finds_subagent_row` in `tests/test_web_server.py`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_resume.py tests/test_tui.py tests/test_web_server.py -q`. Expected: new and rewritten tests FAIL.
- [ ] **Step 3: Implement** the interfaces and update the three callers (`cli.py` builds `resumer = lambda session: open_terminal_and_resume(session, config)`).
- [ ] **Step 4: Run** the full suite including e2e. Expected: PASS.
- [ ] **Step 5: Commit** `fix: resume each session with the agent that created it`.

### Task 4: Handoff engine

**Files:**
- Create: `reconvene/handoff.py`
- Modify: `reconvene/recap.py` (extract `claude_env(config) -> dict` from `claude_runner`, which then uses it)
- Modify: `reconvene/constants.py` (`HANDOFF_DIR = HOME / ".config" / "reconvene" / "handoffs"`)
- Test: `tests/test_handoff.py`, `tests/test_recap.py`

**Interfaces:**
- Consumes: Task 1 `session_messages(newest=True)`, `first_user_message` (recap.py); Task 2 everything; Task 3 `launch_in_terminal`, `resume_prompt`.
- Produces:
  - `handoff_excerpt(db_path, session_id, char_cap: int = 40000) -> str`: the first user message, a line `[... earlier messages omitted ...]` when anything was cut, then the newest messages as `sender: body`, taken from the end until the cap is reached.
  - `summary_request(excerpt: str, from_label: str) -> str`: asks for a summary covering the task, what got done, findings, the current state and next steps, in under 500 words, plain text.
  - `handoff_prompt(from_label: str, summary: str, export_path: Path, transcript: Path | None, updated_at: str, now=None) -> str`: says this continues work from a `<from_label>` session handed over because that agent ran out of usage; includes the summary, `Full conversation (markdown): <export_path>`, `Raw <from_label> transcript: <path>` or `Raw <from_label> transcript: not found`, then the text of `resume_prompt(updated_at, now)`'s IMPORTANT paragraph.
  - `export_session(session_id: str, dest_dir: Path, runner=subprocess.run) -> Path`: runs `ccrider export <id> --output <dest_dir>/<id>.md --force` with `check=True`; creates `dest_dir`.
  - `summarize(name: str, prompt: str, config, runner=subprocess.run, timeout: int = 180) -> str`: runs `headless_argv` with `cwd=tempfile.gettempdir()`; `env=claude_env(config)` for claude, else `os.environ`; reads stdout, or the `-o` file for codex (a temp file). Raises `RuntimeError(f"{label} could not write the summary: <stderr, first 300 chars>")` on non-zero exit, timeout, or blank output.
  - `perform_handoff(session, target: str, config, db_path, runner=subprocess.run, launcher=launch_in_terminal, path_exists=os.path.isdir, home: Path | None = None, handoff_dir: Path = HANDOFF_DIR, now=None) -> None`. Order: validate `target` and that it differs from `session.provider`; check `path_exists(session.project_path)` (raise `FileNotFoundError` as resume does); export; summarize; build prompt; `launcher(fresh_argv(target, prompt, extra_args_for(target, config)), session.project_path, config, runner=runner)`.

- [ ] **Step 1: Write failing tests** in `tests/test_handoff.py` (fake runner records argv/cwd/env and returns canned `CompletedProcess`; `ccrider_db` fixture for messages):
  - `test_handoff_excerpt_keeps_first_task_and_newest_messages` (60 messages, small cap: first user message present, omission marker present, last message present, an early-middle message absent).
  - `test_handoff_excerpt_short_session_has_no_omission_marker`.
  - `test_summarize_runs_in_temp_dir_without_extra_args` (config has `claude_extra_args`; argv equals `headless_argv` exactly; cwd is `tempfile.gettempdir()`).
  - `test_summarize_claude_drops_inherited_api_key_in_subscription_mode`.
  - `test_summarize_codex_reads_output_file`.
  - `test_summarize_raises_with_stderr_on_failure` and `test_handoff_blank_summary_launches_nothing`.
  - `test_summarize_timeout_raises` (runner raises `subprocess.TimeoutExpired`).
  - `test_export_session_argv` (exact `ccrider export ... --output ... --force`).
  - `test_handoff_missing_directory_fails_before_summary` (runner records zero calls).
  - `test_handoff_launches_target_fresh_in_session_directory`: codex session handed to claude; launcher gets `["claude", *claude extra, prompt]` and `session.project_path`; prompt contains the summary, the export path and `Raw Codex transcript:`.
  - `test_handoff_rejects_same_agent`.
  - `test_handoff_prompt_with_quotes_survives_terminal_script`: a summary containing `"`, `\` and newlines, sent through the real `launch_in_terminal` with `system="Darwin"` and a recording runner; the AppleScript passed to `osascript` contains the escaped forms (use `_applescript_escape` on `shlex.quote(prompt)` to build the expectation).
  - In `tests/test_recap.py`: `test_claude_env_subscription_drops_key`, `test_claude_env_api_key_mode_sets_key`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_handoff.py tests/test_recap.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `handoff.py`, `claude_env`, `HANDOFF_DIR`.
- [ ] **Step 4: Run** the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat: hand a session to another agent with a summary it writes`.

### Task 5: Server API and CLI wiring

**Files:**
- Modify: `reconvene/web/server.py`, `reconvene/cli.py`, `tests/e2e/conftest.py` (fixtures pass a fake `handoff` and `which`)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: Task 3 `resumer(session)`; Task 4 `perform_handoff`; Task 2 `AGENTS`, `installed_agents`.
- Produces:
  - `make_handler(..., resumer, recap_runner=None, handoff=None, which=shutil.which)` and the same keywords on `serve`. `handoff(session, target)` is the injected callable.
  - `GET /api/sessions/<name>`: each row adds `"provider"`.
  - `GET /api/agents` → `{"agents": [{"name", "label", "installed"}]}` in `AGENTS` order.
  - `POST /api/resume/<id>` with optional JSON `{"agent": "<name>"}`: absent or equal to the session's provider → `resumer(session)` and `{"status": "resumed"}`; another known agent → `handoff(session, agent)` and `{"status": "handed_off"}`; unknown agent → 400; handoff requested but `handoff is None` → 501 `{"error": "handoff isn't available in this server"}`; any exception → 500 `{"error": str(e)}`.
  - `GET/POST /api/settings` read and write `codex_extra_args` and `antigravity_extra_args` like `claude_extra_args`.
  - `cli.py` passes `handoff=lambda session, target: perform_handoff(session, target, config, db)`.

- [ ] **Step 1: Write failing tests** in `tests/test_web_server.py`: `test_sessions_rows_include_provider`, `test_agents_endpoint_reports_installed` (fake `which`), `test_resume_without_agent_resumes_natively`, `test_resume_with_other_agent_hands_off`, `test_resume_with_unknown_agent_is_400`, `test_handoff_failure_returns_500_with_message`, `test_handoff_unconfigured_is_501`, `test_settings_saves_agent_extra_args`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_web_server.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat: resume API accepts a target agent`.

### Task 6: Resume window "Open in" switch and settings fields

**Files:**
- Modify: `reconvene/web/static/index.html`, `app.js`, `style.css`, `settings.html`, `settings.js`, `README.md` (usage: handoff, per-agent extra args)
- Test: `tests/e2e/test_journal_page.py`, `tests/e2e/test_settings_page.py`

**Interfaces:**
- Consumes: Task 5 endpoints.
- Produces (DOM, for tests): each `.session-row` contains `.agent-badge.agent-<name>`; `#modalAgentSwitch` holds one `button[data-agent]` per agent, the chosen one has class `selected`, uninstalled ones are `disabled`; `#modalConfirm` text is `Resume in <Label>` or `Hand off to <Label>`, and `Summarizing with <Label>…` (disabled) while a handoff request is in flight; `#modalError` shows failures inside the modal; settings inputs `#codexExtraArgs`, `#antigravityExtraArgs`.

Behavior: the switch always shows, including for single-session projects that skip the picker; it resets to the selected row's provider whenever a row is selected. Native resume closes the modal immediately as today. A handoff keeps the modal open until the POST returns: success closes it, failure shows the error in `#modalError` and re-enables the button.

- [ ] **Step 1: Write failing e2e tests** (fixtures from Task 5; the fake handoff records calls; a slow fake handoff uses a `threading.Event` to hold the request open):
  - `test_session_rows_show_agent_badges`.
  - `test_open_in_switch_follows_selected_session` (codex latest preselected → `Resume in Codex`; click a claude row → `Resume in Claude`).
  - `test_switching_agent_changes_button_to_hand_off`.
  - `test_uninstalled_agent_is_disabled` (fake `which` without `agy`).
  - `test_hand_off_posts_target_agent` (fake handoff called with the session and `"claude"`; fake resumer not called).
  - `test_handoff_button_disabled_while_working` (during the held request the button reads `Summarizing with Claude…` and is disabled; a second click adds no call).
  - `test_handoff_error_shows_in_modal_and_reenables`.
  - `test_selected_agent_button_is_visible_against_switch`: computed background of `#modalAgentSwitch button.selected` differs from the switch container's and from an unselected button's (the CSS token-collision guard in `CLAUDE.md`).
  - In `test_settings_page.py`: `test_settings_saves_codex_and_antigravity_args`.
- [ ] **Step 2: Run** `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/pytest tests/e2e -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the UI and README section.
- [ ] **Step 4: Run** the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Open in switch for resume and handoff`.

### Task 7: Real-data check (no terminal launch)

- [ ] **Step 1:** Against the real DB, run `summarize` once per installed agent on one recent session's `handoff_excerpt`, with the real runner and no launcher. Expected: non-empty text from each. Record any agent whose headless mode fails, with its stderr, and stop for Skyler if one does. This spends a little usage on each agent.
- [ ] **Step 2:** Run `export_session` for one Codex and one Antigravity session into a temp dir. Expected: non-empty markdown files.
- [ ] **Step 3:** Hand Skyler the manual check: restart reconvene, open a project whose latest session is a Codex run, confirm "Resume in Codex" opens the Codex session, then try one "Hand off to Claude". Only Skyler clicks these (CLAUDE.md hazard).
