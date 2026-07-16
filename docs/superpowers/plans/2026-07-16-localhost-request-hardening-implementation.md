# Localhost Request-Origin Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject cross-origin and DNS-rebinding requests to Reconvene's localhost server with a server-side guard, without changing the served pages, client JS, or CLI.

**Architecture:** Add two methods to the `Handler` class in `reconvene/web/server.py` — `_request_is_trusted()` (a Host-header allowlist on every request plus an Origin check on POSTs) and `_forbidden()` (sends a 403). Call the guard as the first statement of both `do_GET` and `do_POST`; on rejection, send 403 and return before any routing, DB access, config mutation, or resumer call.

**Tech Stack:** Python 3.11+ standard library only (`http.server`), pytest with real HTTP requests via `urllib.request`.

## Global Constraints

- Standard library only — no new dependencies.
- Do not change the served pages (`reconvene/web/static/*`), the client JS, `reconvene/cli.py`, or the port-selection logic. This task touches only `reconvene/web/server.py` and `tests/test_web_server.py`.
- Host allowlist applies to **every** request (GET and POST): the `Host` header's hostname must be `127.0.0.1` or `localhost`, and its port must equal the bound port (`self.server.server_port` — the port floats, never hardcode it).
- Origin check applies to **state-changing POST only**: if an `Origin` header is present it must exactly match `http://127.0.0.1:<port>` or `http://localhost:<port>`. **Absent `Origin` is allowed** (non-browser clients are not a CSRF vector; the Host allowlist already covers rebinding).
- A rejected request returns `403 Forbidden`: JSON `{"error": "forbidden"}` for `/api/...` paths, a bare 403 otherwise. No indication of which check failed.
- All existing tests in `tests/test_web_server.py` and `tests/e2e/` must continue to pass unmodified (`urllib.request` sends a valid `Host` but no `Origin`; Playwright sends both).
- Run every test with the project venv: `.venv/bin/python -m pytest <path> -v`.

---

### Task 1: Request-origin guard on the HTTP handler

**Files:**
- Modify: `reconvene/web/server.py` (the `Handler` class inside `make_handler`, and its `do_GET`/`do_POST`)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Produces (on the `Handler` class): `_request_is_trusted(self) -> bool` and `_forbidden(self) -> None`. These are internal to the handler; no other module consumes them.
- The guard reads `self.headers.get("Host")`, `self.headers.get("Origin")`, `self.command` (the HTTP method, set by `BaseHTTPRequestHandler` — `"GET"` or `"POST"`), and `self.server.server_port` (the actually-bound port).

- [ ] **Step 1: Write the failing attack-simulation tests**

Add these tests to `tests/test_web_server.py`. The file already imports `json`, `urllib.request`, `pytest`, and `HTTPError`, and already defines the function-scoped `running_server` fixture that yields `(base_url, resumed, config)` where `base_url` is `http://127.0.0.1:<port>` and the fixture pre-seeds a project named `myproject`. Add nothing to the imports.

```python
def test_post_with_foreign_origin_is_forbidden(running_server):
    # Classic CSRF: a cross-origin POST carries the attacker's Origin. It must be rejected
    # before the config is touched.
    base_url, _, config = running_server
    before = set(config.bot_names)
    payload = json.dumps({
        "bot_names": ["myproject"], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
    )
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 403
    assert config.bot_names == before  # config was not poisoned


def test_get_with_foreign_host_is_forbidden(running_server):
    # DNS rebinding: the rebound request still carries the attacker's hostname in Host.
    base_url, _, _ = running_server
    req = urllib.request.Request(f"{base_url}/api/journal", headers={"Host": "evil.example"})
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 403


def test_post_with_foreign_host_is_forbidden(running_server):
    # The Host allowlist guards writes too, not just reads.
    base_url, _, config = running_server
    before = set(config.bot_names)
    payload = json.dumps({
        "bot_names": ["myproject"], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json", "Host": "evil.example"},
    )
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 403
    assert config.bot_names == before
```

- [ ] **Step 2: Run the attack tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -k "foreign" -v`
Expected: all three FAIL — with no guard, the foreign-Origin and foreign-Host requests currently return `200`, so `pytest.raises(HTTPError)` gets no exception (and the CSRF test also shows `config.bot_names == {"myproject"}`, i.e. the config was poisoned).

- [ ] **Step 3: Add the guard and rejection helper to the `Handler` class**

In `reconvene/web/server.py`, inside the `Handler` class in `make_handler`, add these two methods immediately after `_send_json` (before `_send_static`):

```python
        def _request_is_trusted(self):
            # Reject cross-origin and DNS-rebinding requests. The Host allowlist (all requests)
            # stops rebinding -- a rebound request still carries the attacker's hostname; the
            # Origin check (state-changing POSTs) stops classic CSRF. Absent Origin is allowed:
            # only non-browser clients omit it, and they aren't a CSRF vector.
            port = self.server.server_port
            allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in allowed_hosts:
                return False
            if self.command == "POST":
                origin = self.headers.get("Origin")
                allowed_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
                if origin is not None and origin not in allowed_origins:
                    return False
            return True

        def _forbidden(self):
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                self._send_json(403, {"error": "forbidden"})
            else:
                self.send_response(403)
                self.end_headers()
```

- [ ] **Step 4: Call the guard first in both handlers**

In `reconvene/web/server.py`, make the guard the first statement of `do_GET`. Change:

```python
        def do_GET(self):
            path = urlparse(self.path).path
```

to:

```python
        def do_GET(self):
            if not self._request_is_trusted():
                self._forbidden()
                return
            path = urlparse(self.path).path
```

Then make it the first statement of `do_POST`. Change:

```python
        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
```

to:

```python
        def do_POST(self):
            if not self._request_is_trusted():
                self._forbidden()
                return
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
```

(The server's default `protocol_version` is HTTP/1.0, so the connection closes after each response and an unread request body on a rejected POST is harmless.)

- [ ] **Step 5: Run the attack tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -k "foreign" -v`
Expected: all three PASS.

- [ ] **Step 6: Add the legit-flow regression tests**

These prove the guard does not break the real same-origin UI flow. Add to `tests/test_web_server.py`:

```python
def test_post_with_matching_origin_succeeds(running_server):
    # The real UI flow: a same-origin POST carrying the correct Host and a matching Origin.
    base_url, _, config = running_server
    port = base_url.rsplit(":", 1)[1]
    payload = json.dumps({
        "bot_names": ["myproject"], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
    assert config.bot_names == {"myproject"}


def test_post_without_origin_succeeds(running_server):
    # Non-browser clients omit Origin; the Host allowlist still applies, but absence of Origin
    # is deliberately allowed (documented choice).
    base_url, _, _ = running_server
    payload = json.dumps({
        "bot_names": [], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
```

- [ ] **Step 7: Run the full server suite to confirm nothing regressed**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -v`
Expected: all tests PASS — the five new ones plus every pre-existing test (which use plain `urllib`, sending a valid `Host` and no `Origin`).

- [ ] **Step 8: Run the e2e suite to confirm the real browser flow still works**

Run: `.venv/bin/python -m pytest tests/e2e/ -v`
Expected: all PASS — Playwright drives a real same-origin browser that sends both a valid `Host` and a matching `Origin`, so the resume/settings flows are unaffected.

- [ ] **Step 9: Commit**

```bash
git add reconvene/web/server.py tests/test_web_server.py
git commit -m "fix: reject cross-origin and DNS-rebinding requests to the local server

Add a server-side guard: a Host-header allowlist on every request (defeats
DNS rebinding) plus an Origin check on state-changing POSTs (defeats classic
CSRF). Absent Origin is allowed -- only non-browser clients omit it and they
are not a CSRF vector. Rejected requests get a 403. No changes to the served
pages, client JS, or CLI."
```
