let projects = [];

async function loadSettings() {
  const res = await fetch("/api/settings");
  const data = await res.json();
  projects = data.projects;
  const table = document.getElementById("projects");
  table.innerHTML = "";
  for (const p of projects) {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${p.name}</td><td>
      <select data-name="${p.name}">
        <option value="real" ${p.category === "real" ? "selected" : ""}>Real</option>
        <option value="bot" ${p.category === "bot" ? "selected" : ""}>Automated</option>
        <option value="drop" ${p.category === "drop" ? "selected" : ""}>Hidden</option>
      </select></td>`;
    table.appendChild(row);
  }
  const authRadio = document.querySelector(`input[name="auth"][value="${data.config.recap_auth_mode}"]`);
  if (authRadio) authRadio.checked = true;
  document.getElementById("apiKey").value = data.config.api_key || "";
  document.getElementById("hiddenPathSubstrings").value = data.config.hidden_path_substrings.join("\n");
}

document.getElementById("save").addEventListener("click", async () => {
  const botNames = [];
  const hiddenNames = [];
  for (const select of document.querySelectorAll("#projects select")) {
    if (select.value === "bot") botNames.push(select.dataset.name);
    if (select.value === "drop") hiddenNames.push(select.dataset.name);
  }
  const hiddenPathSubstrings = document.getElementById("hiddenPathSubstrings").value
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const authMode = document.querySelector('input[name="auth"]:checked').value;
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bot_names: botNames,
      hidden_names: hiddenNames,
      hidden_path_substrings: hiddenPathSubstrings,
      recap_auth_mode: authMode,
      api_key: document.getElementById("apiKey").value || null,
    }),
  });
});

loadSettings();
