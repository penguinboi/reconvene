# Localhost Request-Origin Hardening — Design

## What it is

Reconvene runs an HTTP server bound to `127.0.0.1` on a predictable port (default 4242,
floating up to 4251 via `find_free_port`). Its endpoints have no `Host`/`Origin` validation, so
while reconvene is running, any web page the user visits can attack it:

- **Classic CSRF** — a cross-origin `POST` to `http://127.0.0.1:4242/api/settings` (a "simple"
  request needing no preflight; the handler `json.loads` the body regardless of Content-Type)
  poisons the persisted config (e.g. sets `claude_extra_args` to `--dangerously-skip-permissions`,
  which the next resume then passes to `claude`). A `POST /api/resume/<id>` opens a terminal
  running a command. The attacker can't read the responses, but these attacks don't need to.
- **DNS rebinding** — `attacker.com` re-resolves to `127.0.0.1`, so the malicious page becomes
  same-origin with the server and *can* read `/api/journal` (session ids) and `/api/settings`,
  then drive `/api/resume`.

This design adds server-side request-origin validation that closes both, with no changes to the
served pages or client JS, staying stdlib-only.

Approved through the brainstorming process; the defense combination (Host allowlist + Origin
check, over a per-session token) was chosen explicitly for a single-user local tool that serves
static files.

## Threat model and why these two checks suffice

| Attack | Request carries | Stopped by |
|---|---|---|
| Classic CSRF (cross-origin POST) | attacker's `Origin`, valid `Host: 127.0.0.1:<port>` | Origin check |
| DNS rebinding (read journal/settings) | `Host: attacker.com` | Host allowlist |

The Host allowlist applies to every request (GET and POST), covering both the rebinding read path
and write path. The Origin check applies to state-changing requests (POST), covering classic CSRF.

## Check 1 — Host allowlist (all requests)

Reject any request whose `Host` header does not name a loopback host on the bound port:

- Hostname part must be `127.0.0.1` or `localhost`.
- Port part must equal the actually-bound port (`self.server.server_port`) — the port is not
  fixed, so it must be read from the running server, not hardcoded.

`localhost` is accepted alongside `127.0.0.1` because a user may manually navigate to
`localhost:<port>` even though the CLI opens `127.0.0.1:<port>`. A request whose `Host` names any
other hostname (the DNS-rebinding case) is rejected.

## Check 2 — Origin check (state-changing POST only)

For `POST` requests, if an `Origin` header is present, reject unless it exactly matches one of:

- `http://127.0.0.1:<bound-port>`
- `http://localhost:<bound-port>`

A cross-origin attacker POST carries the attacker's origin and is rejected.

### Deliberate choice: absent Origin is allowed

CSRF is by definition a browser-driven attack, and every modern browser sends `Origin` on `POST`
(including same-origin requests). The only requests that arrive with no `Origin` at all are
non-browser clients (curl, a local script), which are not a CSRF vector and already have full
local access anyway (they can read `~/.config/reconvene/config.json` or invoke `claude`
directly). Allowing absent `Origin` is the OWASP-standard posture for this scenario, adds no real
exposure (the Host allowlist already blocks the rebinding read path), and keeps the existing
`urllib`-based unit tests valid — `urllib.request` sends `Host` automatically but not `Origin`.

Failing closed on absent `Origin` would be marginally stricter but buys nothing here and would
break non-browser use for no security gain.

## Rejection behavior

A rejected request returns `403 Forbidden` with a minimal body and no explanation of which check
failed (no information leak):

- API paths (`/api/...`): JSON `{"error": "forbidden"}`.
- Other paths: bare `403`.

## Implementation shape

A single guard on the handler class, e.g. `_request_is_trusted() -> bool`, called as the first
statement of both `do_GET` and `do_POST`. On `False`, the handler sends `403` and returns before
any routing, DB access, config mutation, or resumer call happens. The guard reads
`self.headers.get("Host")` / `self.headers.get("Origin")` and `self.server.server_port`; the
method (`self.command`) determines whether the Origin check applies. This keeps all validation in
one place, testable via real HTTP requests like the rest of `server.py`.

## Testing

New cases in `tests/test_web_server.py`, exercised via real HTTP requests against a live server:

1. **CSRF simulation** — a `POST /api/settings` with a mismatched `Origin`
   (`https://evil.example`) returns `403` and the server's config is unchanged.
2. **Rebinding simulation** — a `GET /api/journal` (and a `POST`) with a mismatched `Host`
   (`evil.example`) returns `403`.
3. **Legit same-origin POST** — a `POST` carrying the correct `Host` and a matching `Origin`
   succeeds (proves the guard doesn't break the real UI flow).
4. **Absent-Origin POST** — a `POST` with a valid `Host` and no `Origin` still succeeds
   (documents and locks in the deliberate allow-absent choice).

Existing `test_web_server.py` and `tests/e2e/` tests must continue to pass unmodified: `urllib`
requests already send a valid `Host`, and Playwright drives a real same-origin browser that sends
both `Host` and `Origin`.

## Non-goals

- No per-session token — rejected during brainstorming as over-engineering that would force the
  static HTML/JS to become token-aware, eroding the app's static-file simplicity.
- No TLS or authentication — the server is loopback-only and single-user.
- No CORS headers — cross-origin reads are never wanted; the point is to reject them.
- No changes to the served pages, client JS, `cli.py`, or the port-selection logic.
- Does not address the separate correctness findings (recap URL-encoding, un-hiding hidden
  projects, silent recap-cache degradation, false-success resume) — those are a follow-up.
