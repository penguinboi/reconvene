// ABOUTME: Light/dark/auto theme toggle — cycles Auto → Light → Dark and persists the choice.
// ABOUTME: The pre-paint apply is inline in each page's <head>; this only wires the topbar button.
(function () {
  const KEY = "reconvene-theme";
  const ORDER = ["auto", "light", "dark"];
  const ICON = { auto: "🖥", light: "☀️", dark: "🌙" };
  const LABEL = {
    auto: "Theme: Auto (follows system) — click for Light",
    light: "Theme: Light — click for Dark",
    dark: "Theme: Dark — click for Auto",
  };

  function current() {
    const v = localStorage.getItem(KEY);
    return ORDER.includes(v) ? v : "auto";
  }

  function apply(mode) {
    // "auto" removes the attribute so the prefers-color-scheme media query takes over.
    if (mode === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = mode;
  }

  function render(btn, mode) {
    btn.textContent = ICON[mode];
    btn.setAttribute("aria-label", LABEL[mode]);
    btn.title = LABEL[mode];
  }

  const btn = document.getElementById("themeToggle");
  if (!btn) return;
  render(btn, current());
  btn.addEventListener("click", () => {
    const next = ORDER[(ORDER.indexOf(current()) + 1) % ORDER.length];
    localStorage.setItem(KEY, next);
    apply(next);
    render(btn, next);
  });
})();
