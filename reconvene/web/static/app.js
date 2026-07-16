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
    div.appendChild(metaLineEl);
    div.appendChild(metaEl);
    div.addEventListener("click", () => showConfirmModal(project));
    el.appendChild(div);
    fetch(`/api/recap/${project.name}`)
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

loadJournal();
