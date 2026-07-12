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

async function loadJournal() {
  const res = await fetch("/api/journal");
  const data = await res.json();
  const el = document.getElementById("journal");
  el.innerHTML = "";
  for (const project of data.real) {
    const div = document.createElement("div");
    div.className = "project";
    div.dataset.sessionId = project.latest_session_id;
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = project.oneline;
    div.innerHTML = `<strong>${project.name}</strong> · ${project.count} sessions`;
    div.appendChild(metaEl);
    div.addEventListener("click", () => resumeProject(project.latest_session_id));
    el.appendChild(div);
    fetch(`/api/recap/${project.name}`)
      .then((r) => r.json())
      .then((recap) => { metaEl.textContent = recap.oneline; })
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

loadJournal();
