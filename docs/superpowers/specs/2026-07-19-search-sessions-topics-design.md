# Search, Per-Session Resume, and Topic Clustering — Design

Three features, motivated by a real failure: a 1396-message NAS/Pi-Hole session was
unfindable because (a) reconvene has no search, (b) it only resumes a project's latest
session, and (c) sessions launched from bare `~/Code` collapse into one meaningless
`code` project holding 23 unrelated threads.

Both frontends (web GUI and fzf TUI) get all three features. Python 3.11+ stdlib only.

## 1. Search

### Core: `reconvene/search.py`

ccrider's DB already contains `messages_fts`, an FTS5 external-content index
(`content=messages`, `tokenize='porter unicode61'`) over `messages.text_content`,
maintained by ccrider on every sync. Search queries it read-only — reconvene builds
and stores nothing. Measured: ~9ms for a ranked query over the real 376MB DB.

```python
@dataclass(frozen=True)
class SearchHit:
    session_id: str
    project_path: str
    updated_at: str
    message_count: int
    hits: int         # matching messages in this session
    snippet: str      # one snippet(), match terms wrapped in « »

def search_sessions(db_path, query, limit=30) -> list[SearchHit]
```

- **Sanitization:** split the user's query on whitespace, strip embedded `"` from each
  token, wrap each token in double quotes, join with spaces (implicit AND). Example:
  `pi-hole nas` → `"pi-hole" "nas"`. FTS5 syntax errors become impossible; porter
  stemming still applies. A query that is empty after sanitizing returns `[]`.
- **SQL shape:** join `messages_fts` → `messages` (on `messages.id = messages_fts.rowid`)
  → `sessions`; `GROUP BY sessions.id`; select `count(*)` as hits and one
  `snippet(messages_fts, 0, '«', '»', '…', 10)` per session (whichever grouped row
  SQLite picks — acceptable); `ORDER BY hits DESC, sessions.updated_at DESC LIMIT ?`.
- **Missing index:** if `messages_fts` does not exist, raise `RuntimeError` with a
  message naming the table and suggesting `ccrider sync` / version mismatch — the
  same fail-loudly stance as `db.py`. No silent LIKE fallback.
- Search results are NOT filtered by classification — dropped/hidden/bot sessions are
  all findable (search is a recovery tool; hiding results would recreate the original
  problem).

### Web UI

- Topbar gains a search input (all pages share the topbar; the input lives on the
  journal page `index.html`).
- Typing (debounced 250ms) calls `GET /api/search?q=<urlencoded>` and swaps the
  journal grid for a results panel; clearing the input (or Esc) restores the journal
  without a reload.
- `GET /api/search` response:
  `{"results": [{"session_id", "project", "cwd", "updated_at", "relative", "message_count", "hits", "snippet"}]}`
  where `project` = `canonical_name(project_path)`, `cwd` = `abbreviate_home(project_path)`,
  `relative` = `relative_time(updated_at)`. Existing Host/Origin trust checks apply.
- A result row shows: project badge · relative date · message count · snippet with the
  `«»` regions rendered bold (build DOM via `textContent` splitting on the markers —
  never innerHTML with untrusted text).
- Clicking a row opens the existing confirm modal (session context + snippet as the
  body when no recap applies) and Resume calls the existing `POST /api/resume/<sid>`,
  which already resumes arbitrary sids.

### TUI

- New module `reconvene/_search.py` (same pattern as `_preview.py`): invoked as
  `python -m reconvene._search <query> <db_path>`; prints one line per SearchHit:
  `<sid>\t<project> · <relative> · <hits>✓ · <snippet-with-«»-stripped>` (tab-delimited,
  sid hidden by `--with-nth 2..`).
- Search mode = fzf with `--disabled` (fzf does no filtering) and
  `--bind "change:reload:<python -m reconvene._search {q} <db>>"` for live FTS-backed
  results as the user types, plus the existing per-session preview (below).
- Entry points: `ctrl-f` from the project picker (captured via `--expect`), or
  `reconvene -s "initial query"` / `--search "…"` from the CLI (opens search mode
  directly, query pre-filled via `--query`).
- `enter` resumes the selected session (execvp, session's own cwd); `esc` returns to
  the project picker (loop in `run_tui`).

## 2. Per-session drill-in

### Web

- New endpoint `GET /api/sessions/<project-name>` (name matched the same way
  `/api/recap/<name>` matches):
  `{"sessions": [{"session_id", "updated_at", "relative", "message_count", "first_msg"}]}`
  ordered newest-first; `first_msg` = `first_user_message(...)` (≤90 chars, existing
  helper).
- The confirm modal, when opened from a project card, fetches that list and renders it
  as selectable rows with the latest preselected. Resume resumes the selected sid.
  (Opened from a search result, the modal shows just that one session — no list fetch.)

### TUI

- In the project picker, `ctrl-s` (via `--expect`) drills into the highlighted
  project: a second fzf lists its sessions, one line each:
  `<sid>\t<relative> · <N> msgs · <first_msg>`; `enter` resumes that session; `esc`
  returns to the project list.
- Per-session preview: `_preview.py` gains a session mode (flag argument) that prints
  the session's date/count/path header plus its first user message and ccrider's
  stored `summary` (if non-empty) — no recap generation at session granularity.

## 3. Topic clustering of loose (root-launched) sessions

### Root detection — automatic, no config

A `project_path` P is a **root** when P (rstrip `/`, plus `/`) is a proper prefix of
≥3 distinct *other* `project_path` values in the DB, **excluding** child paths that
contain a worktree marker (`WORKTREE_MARKERS`) — otherwise a repo with three
`.claude-worktrees/` subpaths would falsely count as a root. This detects `~/Code`
today and any similar parent directory automatically; ordinary projects stay
untouched.

Root detection runs on the full session list before classification; classification
(`drop`/`hidden`/`bot` rules) still applies to loose sessions afterward, except the
name-based rules use the topic name once assigned.

### Sticky assignments — `TopicCache`

- New table `topic_assignments(session_id TEXT PRIMARY KEY, topic TEXT NOT NULL)` in
  the existing reconvene cache DB file (alongside `recaps`), managed by a `TopicCache`
  class in a new `reconvene/cluster.py`.
- An assignment, once written, is never changed by clustering (manual re-organize of
  everything is out of scope; deleting rows by hand is the escape hatch).

### The organize step — explicit, never blocking

- Journal loads NEVER call claude for clustering. Loose sessions without a cached
  assignment render under a single fallback group named `~/Code (loose sessions)`
  (label uses the abbreviated root path; one fallback group per detected root).
- Clustering runs only on demand:
  - Web: the fallback card shows an **Organize** button → `POST /api/topics/refresh`
    (Origin-checked like other POSTs) → runs clustering synchronously → responds with
    `{"assigned": N}` → client reloads the journal.
  - CLI: `reconvene --organize` runs the same and prints a per-topic summary, then exits.
- Clustering call: one `claude -p --model sonnet` prompt (reuses `claude_runner` and
  its auth-mode env handling) containing, per unassigned loose session: sid, date,
  first user message (≤200 chars), and ccrider `summary` if present — plus the list of
  existing topic names with the instruction to reuse one when it fits and otherwise
  coin a new 2–4 word Title Case topic. Response format: one `sid: Topic Name` line
  per session; unparseable/missing lines are simply left unassigned (they stay in the
  fallback group; nothing is invented).
- `recap_auth_mode == "none"`: organize endpoints report that clustering needs Claude
  (HTTP 409 with a message / CLI stderr), fallback grouping remains.

### Display & behavior of topic groups

- A topic group renders as a normal ranked journal card/TUI row: name = topic, session
  list = its assigned sessions (newest first), recency rank among real projects.
- Marked visually as a topic: web card shows a small `topic` tag; TUI line appends
  `· topic`.
- Recaps, drill-in, search, and resume all work identically; each session resumes with
  its own real `project_path` as cwd.
- `hidden_names` matching applies to the lowercased topic name, so topics can be
  hidden from Settings like any project.

## 4. Error handling

| Failure | Behavior |
|---|---|
| `messages_fts` missing | RuntimeError → web: 500 JSON + dismissible error banner; TUI: message in results area |
| FTS syntax risk | Prevented by tokenize-and-quote sanitization |
| Empty/whitespace query | `[]` — empty results, no error |
| claude fails during organize | Web: 502 JSON + banner; CLI: stderr + exit 1; fallback group persists |
| organize with auth mode `none` | 409 / stderr message; no claude call attempted |
| Unparseable topic lines | Those sessions stay unassigned (fallback group); parse what's valid |

## 5. Testing

- **Fixtures:** `tests/conftest.py` gains `messages_fts` creation (real FTS5
  external-content table) and `add_message` populates it
  (`INSERT INTO messages_fts(rowid, text_content) …`), so search tests exercise
  genuine FTS5 semantics including porter stemming.
- **Unit:** sanitization (hyphens, embedded quotes, empty), ranking (hits desc),
  snippet markers, missing-FTS error; root detection (≥3 rule, boundary at exactly 3,
  prefix must be path-segment-aligned); TopicCache stickiness (existing assignment
  never overwritten); organize parsing (valid, partial, garbage responses) with a fake
  runner; fallback grouping; `/api/search`, `/api/sessions/<name>`,
  `/api/topics/refresh` (success, 409, 502) via the existing test-server harness;
  TUI drill-in and search modes via injected pickers; `_search.py` output format.
- **E2E (Playwright):** type a query → results appear → click → modal → fake resume
  called with the right sid; open a project card → pick an older session → fake
  resume gets that sid; organize button flow with a fake runner.
- TDD (RED→GREEN) throughout; run via `.venv/bin/python -m pytest`.

## Out of scope (YAGNI)

- Manual topic re-assignment UI; renaming/merging topics (delete cache rows by hand).
- Search filters (by project/date), pagination, regex mode.
- Session-level recap generation.
- Any write to ccrider's DB (unchanged invariant: read-only, `mode=ro`).
