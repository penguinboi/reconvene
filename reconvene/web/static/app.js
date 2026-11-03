// ABOUTME: Renders the journal page — project cards, async recap fill-in, resume confirm modal.
// ABOUTME: Talks to /api/journal, /api/recap/<name>, and /api/resume/<session> on the local server.
function showError(message) {
  let el = document.getElementById("error");
  if (!el) {
    el = document.createElement("div");
    el.id = "error";
    el.className = "error";
    document.body.insertBefore(el, document.getElementById("journal"));
  }
  el.textContent = message;
}

const fullRecaps = new Map(); // project name -> full recap text, populated only once actually fetched

// The agents the "Open in" switch offers, in display order: [{name, label, installed}].
let agentsPromise = null;
function loadAgents() {
  if (!agentsPromise) {
    // A failed fetch is dropped so the next call retries instead of replaying the failure.
    agentsPromise = fetch("/api/agents").then((r) => r.json()).then((data) => data.agents)
      .catch((err) => { agentsPromise = null; throw err; });
  }
  return agentsPromise;
}

// The modal carries two agent names: dataset.provider (who made the selected session) and
// dataset.agent (who the user wants to open it in). Different means a handoff.
function confirmLabel(agents, modal) {
  const target = agents.find((a) => a.name === modal.dataset.agent);
  if (!target) return "Resume";
  return modal.dataset.agent === modal.dataset.provider
    ? `Resume in ${target.label}` : `Hand off to ${target.label}`;
}

// True from the handoff request until it settles. Unlike dataset.working it survives a modal
// reset, so the modal cannot be closed and reopened to fire a second handoff.
let handoffInFlight = false;

// While a handoff request is in flight (dataset.working) the button is busy and the switch
// is locked, so the label and target cannot change under the pending request.
function refreshConfirmButton(agents, modal) {
  const button = document.getElementById("modalConfirm");
  document.getElementById("modalCancel").disabled = handoffInFlight;
  const working = modal.dataset.working === "1";
  const target = agents.find((a) => a.name === modal.dataset.agent);
  button.disabled = working;
  button.textContent = working ? `Summarizing with ${target.label}…` : confirmLabel(agents, modal);
}

function renderAgentSwitch(agents) {
  const modal = document.getElementById("confirmModal");
  const switchEl = document.getElementById("modalAgentSwitch");
  switchEl.innerHTML = "";
  const label = document.createElement("span");
  label.className = "agent-switch-label";
  label.textContent = "Open in";
  switchEl.appendChild(label);
  for (const a of agents) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.agent = a.name;
    btn.textContent = a.label;
    btn.disabled = !a.installed || modal.dataset.working === "1";
    if (a.name === modal.dataset.agent) btn.classList.add("selected");
    btn.addEventListener("click", () => {
      modal.dataset.agent = a.name;
      renderAgentSwitch(agents);
    });
    switchEl.appendChild(btn);
  }
  switchEl.classList.remove("hidden");
  refreshConfirmButton(agents, modal);
}

// Points the switch at a session: its own agent is the default target.
function selectSessionAgent(provider) {
  const modal = document.getElementById("confirmModal");
  modal.dataset.provider = provider;
  modal.dataset.agent = provider;
  return loadAgents().then(renderAgentSwitch)
    .catch((err) => showError(`Couldn't load the agent list: ${err.message}`));
}

function clearAgentSwitch() {
  const modal = document.getElementById("confirmModal");
  modal.dataset.provider = "";
  modal.dataset.agent = "";
  delete modal.dataset.working;
  document.getElementById("modalAgentSwitch").classList.add("hidden");
  document.getElementById("modalConfirm").textContent = "Resume";
  document.getElementById("modalConfirm").disabled = false;
  document.getElementById("modalError").classList.add("hidden");
}

function showConfirmModal(project) {
  // Resume defaults to the latest session. A loose/topic group aggregates unrelated sessions, so
  // its latest may not be the one wanted -- those always show the full picker to override it.
  const isGroup = project.kind === "loose" || project.kind === "topic";
  document.getElementById("modalProjectName").textContent = project.name;
  document.getElementById("modalFullRecap").textContent =
    fullRecaps.get(project.name) || "Loading full summary…";
  const modal = document.getElementById("confirmModal");
  modal.dataset.projectName = project.name;
  modal.dataset.sessionId = project.latest_session_id;
  const list = document.getElementById("modalSessions");
  list.innerHTML = "";
  clearAgentSwitch();
  fetch(`/api/sessions/${encodeURIComponent(project.name)}`)
    .then((r) => r.json())
    .then((data) => {
      if (!data.sessions) return;
      const current = data.sessions.find((s) => s.session_id === modal.dataset.sessionId);
      if (current) selectSessionAgent(current.provider);
      if (!isGroup && data.sessions.length < 2) return; // one session, real project: nothing to pick
      const hint = document.createElement("div");
      hint.className = "session-hint";
      hint.textContent = "Pick a session to resume:";
      list.appendChild(hint);
      for (const s of data.sessions) {
        const row = document.createElement("div");
        row.className = "session-row";
        if (s.session_id === modal.dataset.sessionId) row.classList.add("selected");
        const badge = document.createElement("span");
        badge.className = `agent-badge agent-${s.provider}`;
        badge.textContent = s.agent_label;
        row.append(badge, `${s.relative} · ${s.message_count} msgs · ${s.first_msg}`);
        row.addEventListener("click", () => {
          if (modal.dataset.working === "1") return; // locked during a handoff
          modal.dataset.sessionId = s.session_id;
          selectSessionAgent(s.provider);
          list.querySelectorAll(".session-row.selected")
            .forEach((n) => n.classList.remove("selected"));
          row.classList.add("selected");
        });
        list.appendChild(row);
      }
    })
    .catch((err) => console.error(`Failed to fetch sessions for ${project.name}:`, err));
  modal.classList.remove("hidden");
}

function hideConfirmModal() {
  document.getElementById("confirmModal").classList.add("hidden");
}

async function loadJournal() {
  const res = await fetch("/api/journal");
  const data = await res.json();
  const el = document.getElementById("journal");
  el.innerHTML = "";
  el.classList.remove("placeholder");

  if (data.real.length === 0) {
    el.classList.add("placeholder");
    el.textContent = "No projects yet — resume some Claude Code sessions and they'll show up here.";
    return;
  }

  for (const project of data.real) {
    const div = document.createElement("div");
    div.className = "project";
    div.dataset.sessionId = project.latest_session_id;
    const metaLineEl = document.createElement("div");
    metaLineEl.className = "meta-line";
    metaLineEl.textContent = `${project.last_active_relative} · ${project.cwd}`;
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = project.oneline;
    const dot = document.createElement("span");
    dot.className = `dot dot-${project.recency}`;
    const nameEl = document.createElement("strong");
    nameEl.textContent = project.name;  // untrusted directory name — set as text, never HTML
    const countEl = document.createElement("span");
    countEl.className = "count";
    countEl.textContent = ` · ${project.count} sessions`;
    div.append(dot, nameEl, countEl);
    if (project.kind === "topic") {
      const tag = document.createElement("span");
      tag.className = "kind-tag";
      tag.textContent = "topic";
      div.appendChild(tag);
    }
    if (project.kind === "loose") {
      const btn = document.createElement("button");
      btn.className = "organize-btn";
      btn.textContent = "Organize into topics";
      btn.addEventListener("click", async (e) => {
        e.stopPropagation(); // don't open the resume modal
        btn.disabled = true;
        btn.textContent = "Organizing…";
        const res = await fetch("/api/topics/refresh", { method: "POST" });
        if (!res.ok) {
          const data = await res.json();
          showError(`Organize failed: ${data.error}`);
          btn.disabled = false;
          btn.textContent = "Organize into topics";
          return;
        }
        loadJournal();
      });
      div.appendChild(btn);
    }
    div.appendChild(metaLineEl);
    div.appendChild(metaEl);
    div.addEventListener("click", () => showConfirmModal(project));
    el.appendChild(div);
    fetch(`/api/recap/${encodeURIComponent(project.name)}`)
      .then((r) => r.json())
      .then((recap) => {
        metaEl.textContent = recap.excerpt;
        fullRecaps.set(project.name, recap.full);
        const modal = document.getElementById("confirmModal");
        if (!modal.classList.contains("hidden") && modal.dataset.projectName === project.name) {
          document.getElementById("modalFullRecap").textContent = recap.full;
        }
      })
      .catch((err) => console.error(`Failed to fetch recap for ${project.name}:`, err));
  }
}

function agentRequestBody(agent) {
  return agent ? { method: "POST", headers: { "Content-Type": "application/json" },
                   body: JSON.stringify({ agent }) } : { method: "POST" };
}

async function resumeProject(sessionId, agent) {
  try {
    const res = await fetch(`/api/resume/${sessionId}`, agentRequestBody(agent));
    if (!res.ok) {
      const data = await res.json().catch(() => ({})); // a non-JSON error body has no message
      throw new Error(data.error || `HTTP ${res.status}`);
    }
  } catch (err) {
    showError(`Couldn't resume: ${err.message}`);
  }
}

// A handoff has the target agent write a summary first, which takes a while: keep the modal
// open with the button busy so the click visibly did something, and show a failure in place.
async function handOff(modal) {
  const errorEl = document.getElementById("modalError");
  errorEl.classList.add("hidden");
  let agents = null;
  try {
    agents = await loadAgents();
    handoffInFlight = true;
    modal.dataset.working = "1";
    renderAgentSwitch(agents);
    const res = await fetch(`/api/resume/${modal.dataset.sessionId}`, agentRequestBody(modal.dataset.agent));
    if (!res.ok) {
      const data = await res.json(); // a non-JSON error body throws and is shown below
      throw new Error(data.error);
    }
    hideConfirmModal();
  } catch (err) {
    errorEl.textContent = `Couldn't hand off: ${err.message}`;
    errorEl.classList.remove("hidden");
  } finally {
    handoffInFlight = false;
    delete modal.dataset.working;
    if (agents) renderAgentSwitch(agents);
  }
}

document.getElementById("modalConfirm").addEventListener("click", () => {
  const modal = document.getElementById("confirmModal");
  if (modal.dataset.agent && modal.dataset.agent !== modal.dataset.provider) {
    handOff(modal);
    return;
  }
  const { sessionId, agent } = modal.dataset;
  hideConfirmModal();
  resumeProject(sessionId, agent);
});

document.getElementById("modalCancel").addEventListener("click", () => {
  if (handoffInFlight) return;
  hideConfirmModal();
});

// --- search -----------------------------------------------------------------
const searchBox = document.getElementById("searchBox");
let searchTimer = null;

searchBox.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 250);
});
searchBox.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    searchBox.value = "";
    runSearch();
  }
});

async function runSearch() {
  const q = searchBox.value.trim();
  if (!q) {
    loadJournal();
    return;
  }
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) {
    const data = await res.json();
    showError(`Search failed: ${data.error}`);
    return;
  }
  const data = await res.json();
  renderResults(data.results, q);
}

function snippetNode(snippet) {
  // «…» regions become <strong>. Built via textContent — snippet text is untrusted.
  const span = document.createElement("span");
  const parts = snippet.split("«");
  span.appendChild(document.createTextNode(parts[0]));
  for (const part of parts.slice(1)) {
    const close = part.indexOf("»");
    const strong = document.createElement("strong");
    strong.textContent = close === -1 ? part : part.slice(0, close);
    span.appendChild(strong);
    if (close !== -1) span.appendChild(document.createTextNode(part.slice(close + 1)));
  }
  return span;
}

function renderResults(results, q) {
  const el = document.getElementById("journal");
  el.innerHTML = "";
  el.classList.remove("placeholder");
  if (results.length === 0) {
    el.classList.add("placeholder");
    el.textContent = `No sessions matching “${q}”.`;
    return;
  }
  for (const r of results) {
    const div = document.createElement("div");
    div.className = "project search-hit";
    const nameEl = document.createElement("strong");
    nameEl.textContent = r.project;
    const metaLine = document.createElement("div");
    metaLine.className = "meta-line";
    metaLine.textContent =
      `${r.relative} · ${r.message_count} msgs · ${r.hits} match${r.hits === 1 ? "" : "es"} · ${r.cwd}`;
    const snip = document.createElement("div");
    snip.className = "meta";
    snip.appendChild(snippetNode(r.snippet));
    div.append(nameEl, metaLine, snip);
    div.addEventListener("click", () => showSessionModal(r));
    el.appendChild(div);
  }
}

function showSessionModal(hit) {
  document.getElementById("modalProjectName").textContent = hit.project;
  const recapEl = document.getElementById("modalFullRecap");
  recapEl.innerHTML = "";
  recapEl.appendChild(snippetNode(hit.snippet));               // the search match, shown immediately
  const loading = document.createElement("div");
  loading.className = "recap-loading";
  loading.textContent = "Generating summary…";
  recapEl.appendChild(loading);
  const modal = document.getElementById("confirmModal");
  modal.dataset.sessionId = hit.session_id;
  modal.dataset.projectName = hit.project;
  document.getElementById("modalSessions").innerHTML = "";
  clearAgentSwitch(); // a search hit carries no agent, so it resumes natively
  modal.classList.remove("hidden");
  // Fetch the per-session recap and fill it in below the snippet (guard against a stale response if
  // the user has since opened a different session's modal).
  fetch(`/api/session-recap/${encodeURIComponent(hit.session_id)}`)
    .then((r) => r.json())
    .then((data) => {
      if (modal.dataset.sessionId !== hit.session_id) return;
      loading.textContent = data.full || "(no summary)";
      loading.classList.remove("recap-loading");
    })
    .catch(() => { loading.textContent = ""; });
}

loadJournal();
