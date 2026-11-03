# Agent handoff: resume any session in Claude, Codex or Antigravity

Date: 2026-11-02. Status: approved by Skyler in conversation, pending the written-design review.

## Why

Skyler runs three coding agents: Claude Code, Codex and Antigravity. When one runs out of usage he
wants to keep working on another without losing the thread. Today he does this by hand. He asks the
outgoing agent to write a handoff doc, then tells the incoming agent to read it. ccrider's history
holds several such handoffs between August and October 2026, in both directions between Claude and
Codex. That only works while the outgoing agent still has usage left to write the doc.

There is also a plain bug. ccrider (verified at 1.15.0 on 2026-11-02) imports sessions from every
agent, and its `sessions.provider` column says which. Reconvene ignores that column, so 1,694 Codex
and 13 Antigravity sessions show in project cards, and `resume.py` runs `claude --resume <id>` on
them, which fails. Because groups preselect their latest session, a project whose newest session is
a Codex run preselects one Resume cannot open.

## Goals

1. **Native resume per agent.** A session reopens in the agent that created it. Fixes the bug above,
   in both the web page and the TUI.
2. **Handoff.** From the web page, Skyler can open any session in a different agent. The new agent
   starts fresh in the old session's directory, with a first prompt that carries a summary of the old
   session and paths to its full record.

## Non-goals

- No `agentctl`. Skyler has it installed, and its provider switching had problems in a 2026-09-30
  test. The handoff is plain text.
- No conversion of one agent's history into another agent's native format.
- No handoff in the TUI in this version. The TUI gets native resume only. (Claude's call, YAGNI.)

## Anti-goals

- A handoff that launches without its summary and does not say so. If the summary step fails,
  nothing launches and the error is shown.
- Any change that makes the normal case (resume a session in its own agent) take more than one click.

## The three agents (facts checked 2026-11-02)

| | Claude Code | Codex (codex-cli 0.166.0) | Antigravity (`agy`) |
|---|---|---|---|
| ccrider `provider` | `claude` | `codex` | `antigravity` |
| Native resume | `claude --resume <id> [prompt]` | `codex resume <uuid> [prompt]` | `agy --conversation <id>` |
| Fresh interactive session with a first prompt | `claude "<prompt>"` | `codex "<prompt>"` | `agy -i "<prompt>"` (`--prompt-interactive`) |
| Headless one-shot | `claude -p "<prompt>"` | `codex exec "<prompt>"` | `agy -p "<prompt>"` (`--print`) |
| Raw transcript | `~/.claude/projects/<cwd with / as ->/<id>.jsonl` | `~/.codex/sessions/YYYY/MM/DD/<session_id>.jsonl` | `~/.gemini/antigravity-cli/conversations/<id>.db` (SQLite) |

Notes for the builder:
- A Codex `session_id` in ccrider is the rollout file name, e.g.
  `rollout-2026-11-01T19-54-00-01a19a64-6dff-7983-9653-7af460dbd4e9`. `codex resume` wants the
  trailing UUID.
- ccrider 1.14.0 added `sessions.resume_via`. When it is non-empty (only Codex multi-agent v2
  sub-agents), resume that root thread id instead, because Codex refuses to resume those sub-agents
  directly. It is an empty string on every other row.
- **Hide sub-agent rows (`resume_via` non-empty) from the session picker.** (Claude's call.) All 65
  such rows on 2026-11-02 have their root thread in the database as its own session, and resuming a
  sub-agent reopens that root anyway, so showing them would put several rows that open the same
  thread in the list, and one could be preselected as "latest". Hiding them means handoff always
  summarizes a root thread. Keep them in full-text search results, since their messages are real.
- Whether `agy --conversation <id>` accepts an initial prompt the way `claude --resume` does is not
  verified. Check it. If it cannot, native Antigravity resume goes without the resume-context prompt.

## Behavior

### Native resume

The selected session reopens with its own agent's resume command, in the session's directory, with
the existing resume-context prompt ("Resuming session from ... check git status ..."). Everything
else about Resume stays as it is: the picker, latest-session preselection (see
`docs/debugging/2026-08-10-resume-picker-root-cause.md`, do not reintroduce the disabled button),
and the new terminal window.

The TUI's `exec_resume` uses the same per-agent command.

### The Resume window (Skyler chose layout A from the mockups)

- Each session row shows an agent badge: Claude, Codex or Antigravity.
- Under the session list, an **"Open in"** three-way switch: Claude, Codex, Antigravity. It follows
  the selected session's agent, so selecting a row resets the switch to that row's agent.
- One button whose label says what will happen: "Resume in Codex" when the switch matches the
  session's agent, "Hand off to Claude" when it does not.
- An agent whose binary is not on PATH is greyed out in the switch and cannot be picked.
  (Claude's call.)

### Handoff

When Skyler clicks "Hand off to X":

1. **Export.** `ccrider export <session_id> --output <path>` writes the old session as markdown to a
   reconvene-owned folder, `~/.config/reconvene/handoffs/`, never into the project repo, so it cannot
   land in a commit. (Claude's call.)
2. **Summarize with the incoming agent.** Run agent X headlessly (table above) with a prompt asking
   for a summary of the old session: the task, what got done, findings, the current state, and next
   steps. **The incoming agent writes it** (Skyler's decision): the outgoing agent is likely the one
   out of usage. The button shows a working state such as "Summarizing with Claude…" meanwhile;
   expect 20 to 60 seconds. The modal stays open until the launch or the error.
   - **The transcript goes in the prompt, not as a path to read.** (Claude's call.) A headless agent
     has no one to approve reading a file outside its directory, and each agent's permission rules
     differ. Build the excerpt from ccrider's `messages` table, as `recap.build_session_prompt`
     does, but take the first user message (the original task) plus the most recent messages up to
     a character cap, because the latest state is what a handoff needs. `build_session_prompt`
     takes the first 200 messages, which is the wrong end for this. The cap value is the builder's.
   - **Run it in the system temp directory**, as `recap.claude_runner` does, never in the project
     directory. (Claude's call.) Otherwise ccrider imports the summary run as the newest session in
     the project card, and the picker would preselect it.
   - **Claude's summary run follows the existing auth handling** in `claude_runner`: subscription
     mode drops an inherited `ANTHROPIC_API_KEY`, `api_key` mode sets it. Reuse that code rather than
     copying it. `recap_auth_mode: none` does not block a handoff, since Skyler asks for the summary
     by clicking. (Claude's call.)
3. **Launch.** Open a terminal in the old session's directory and start a fresh interactive session
   of agent X. Its first prompt contains:
   - a line saying this continues work begun in a <old agent> session, handed over because that
     agent ran out of usage;
   - the summary from step 2;
   - the path to the exported markdown and the path to the old agent's raw transcript file;
   - the existing warning to check `git status` and avoid overwriting work in progress.

Directory: use the session's own working directory, as native resume does today. Skyler asked that
the new agent start in the same directory as the old session.

**Failure:** if the export or the summary step exits non-zero or times out, show the agent's error
in the Resume window and launch nothing (anti-goal above). If the old session's directory no longer
exists, fail the same way native resume does today (`FileNotFoundError`).

The new session is an ordinary session of agent X. ccrider imports it on its next sync and it shows
in the same project card.

### Settings

Each agent gets its own extra-arguments field, the way `claude_extra_args` works today. Keep
`claude_extra_args` as is and add `codex_extra_args` and `antigravity_extra_args`, so existing config
files need no migration. Extra args apply to both native resume and the handoff launch, and not to
the headless summary step. (Claude's call.)

## Constraints

- Read-only on ccrider's database, as today (`db.py`).
- 🚨 Never click Resume or Hand off from an automated browser test against the real config: it opens
  a real terminal running a real agent (see `CLAUDE.md`). E2E tests must use an injected runner.
- TDD, real data where possible, no mocks of the behavior under test (global rules).
- Python changes need a server restart; static files reload on refresh.

## Left to the builder

- Exact prompt wording for the summary request and the first prompt.
- The summary step's timeout value, and how the working state looks.
- The API shape between `app.js` and the server (e.g. an `agent` field on the existing resume POST,
  or a separate handoff endpoint).
- How search results (`search.py`) show the agent badge, if at all.
- Badge colors, within the existing theme and the CSS-token-collision guard in
  `tests/e2e/test_journal_page.py`.
