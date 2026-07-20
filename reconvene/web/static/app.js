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

function showConfirmModal(project) {
  document.getElementById("modalProjectName").textContent = project.name;
  document.getElementById("modalFullRecap").textContent =
    fullRecaps.get(project.name) || "Loading full summary…";
  const modal = document.getElementById("confirmModal");
  modal.dataset.sessionId = project.latest_session_id;
  modal.dataset.projectName = project.name;
  const list = document.getElementById("modalSessions");
  list.innerHTML = "";
  fetch(`/api/sessions/${encodeURIComponent(project.name)}`)
    .then((r) => r.json())
    .then((data) => {
      if (!data.sessions || data.sessions.length < 2) return; // one session: nothing to pick
      for (const s of data.sessions) {
        const row = document.createElement("div");
        row.className = "session-row";
        if (s.session_id === modal.dataset.sessionId) row.classList.add("selected");
        row.textContent = `${s.relative} · ${s.message_count} msgs · ${s.first_msg}`;
        row.addEventListener("click", () => {
          modal.dataset.sessionId = s.session_id;
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

async function resumeProject(sessionId) {
  const res = await fetch(`/api/resume/${sessionId}`, { method: "POST" });
  if (!res.ok) {
    const data = await res.json();
    showError(`Couldn't resume: ${data.error}`);
  }
}

document.getElementById("modalConfirm").addEventListener("click", () => {
  const sessionId = document.getElementById("confirmModal").dataset.sessionId;
  hideConfirmModal();
  resumeProject(sessionId);
});

document.getElementById("modalCancel").addEventListener("click", hideConfirmModal);

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
  recapEl.appendChild(snippetNode(hit.snippet));
  const modal = document.getElementById("confirmModal");
  modal.dataset.sessionId = hit.session_id;
  modal.dataset.projectName = hit.project;
  document.getElementById("modalSessions").innerHTML = "";
  modal.classList.remove("hidden");
}

loadJournal();
