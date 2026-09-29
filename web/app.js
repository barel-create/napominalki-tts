/* ============================================================
   Napominalki TTS -- GUI shell logic.
   Talks to Python exclusively through window.pywebview.api.* (the bridge
   gui_api.py exposes). Every api call returns a Promise (pywebview's JS
   bridge is async), so everything here is async/await.
   ============================================================ */

const DASHBOARD_REFRESH_MS = 60 * 1000; // matches the bot's own ~1min cache cadence
const UPDATE_CHECK_MS = 60 * 60 * 1000; // check for a new version hourly

const gearBtn = document.getElementById("gear-btn");
const gearIcon = document.getElementById("gear-icon");
const settingsPanel = document.getElementById("settings-panel");
const statusEl = document.getElementById("settings-status");
const dashboardFrame = document.getElementById("dashboard-frame");
const updateBtn = document.getElementById("update-btn");

let settingsOpen = false;

// --------------------------------------------------------------
// Gear teeth -- drawn programmatically so index.html doesn't need
// 8 hand-positioned <rect> tags.
// --------------------------------------------------------------
function buildGearTeeth() {
  const g = document.getElementById("gear-teeth");
  const toothCount = 8;
  for (let i = 0; i < toothCount; i++) {
    const angle = (360 / toothCount) * i;
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", "46");
    rect.setAttribute("y", "4");
    rect.setAttribute("width", "8");
    rect.setAttribute("height", "16");
    rect.setAttribute("fill", "currentColor");
    rect.setAttribute("transform", `rotate(${angle} 50 50)`);
    g.appendChild(rect);
  }
}

// --------------------------------------------------------------
// Settings panel open/close (gear click, gear click again, or Esc)
// --------------------------------------------------------------
function openSettings() {
  settingsOpen = true;
  settingsPanel.classList.add("open");
  settingsPanel.setAttribute("aria-hidden", "false");
  gearIcon.classList.add("open");
}

function closeSettings() {
  settingsOpen = false;
  settingsPanel.classList.remove("open");
  settingsPanel.setAttribute("aria-hidden", "true");
  gearIcon.classList.remove("open");
}

gearBtn.addEventListener("click", () => {
  settingsOpen ? closeSettings() : openSettings();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && settingsOpen) closeSettings();
});

// --------------------------------------------------------------
// Status line helper (brief confirmation after Save / voice test / etc.)
// --------------------------------------------------------------
let statusTimer = null;
function showStatus(msg) {
  statusEl.textContent = msg;
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => { statusEl.textContent = ""; }, 3000);
}

// --------------------------------------------------------------
// Load current settings into the panel on startup.
// --------------------------------------------------------------
async function loadSettings() {
  const cfg = await window.pywebview.api.get_settings();

  document.getElementById("field-url").value = cfg.web_app_url || "";
  document.getElementById("field-token").value = cfg.tts_token || "";

  const voiceSelect = document.getElementById("field-voice");
  voiceSelect.innerHTML = "";
  (cfg.voices || []).forEach(([value, label]) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    if (value === cfg.voice) opt.selected = true;
    voiceSelect.appendChild(opt);
  });

  document.documentElement.setAttribute("data-theme", cfg.theme || "light");

  document.getElementById("field-borderless").setAttribute(
    "aria-checked", cfg.borderless ? "true" : "false"
  );
  document.getElementById("field-autoupdate").setAttribute(
    "aria-checked", cfg.autoupdate ? "true" : "false"
  );
}

// --------------------------------------------------------------
// Save handlers (URL / token)
// --------------------------------------------------------------
document.querySelectorAll(".save-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const which = btn.dataset.save;
    const field = document.getElementById(which === "url" ? "field-url" : "field-token");
    const value = field.value.trim();
    if (!value) return;
    await window.pywebview.api.save_setting(which, value);
    showStatus("Сохранено");
  });
});

// --------------------------------------------------------------
// Voice test
// --------------------------------------------------------------
document.getElementById("voice-test-btn").addEventListener("click", async () => {
  const voice = document.getElementById("field-voice").value;
  showStatus("Проверка голоса...");
  const ok = await window.pywebview.api.test_voice(voice);
  showStatus(ok ? "Готово" : "Ошибка воспроизведения");
});

// --------------------------------------------------------------
// Theme buttons -- icon color itself flips via the [data-theme] CSS
// variables (--icon-color), so this only needs to set the attribute
// and persist it.
// --------------------------------------------------------------
async function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  await window.pywebview.api.save_setting("theme", theme);
}
document.getElementById("theme-light-btn").addEventListener("click", () => setTheme("light"));
document.getElementById("theme-dark-btn").addEventListener("click", () => setTheme("dark"));

// --------------------------------------------------------------
// Toggle switches (borderless window, autoupdate)
// --------------------------------------------------------------
function wireToggle(id, onChange) {
  const el = document.getElementById(id);
  el.addEventListener("click", async () => {
    const next = el.getAttribute("aria-checked") !== "true";
    el.setAttribute("aria-checked", next ? "true" : "false");
    await onChange(next);
  });
}

wireToggle("field-borderless", async (checked) => {
  // Applies immediately -- the window briefly recreates itself on the
  // Python side (a real OS window's frame style can't change without
  // that on Windows), see gui_api.py::set_borderless.
  await window.pywebview.api.set_borderless(checked);
});

wireToggle("field-autoupdate", async (checked) => {
  await window.pywebview.api.save_setting("autoupdate", checked);
  if (checked) checkForUpdate(); // apply right away if one's already available
});

// --------------------------------------------------------------
// Dashboard: load once, then reload on an interval so it reflects
// new lesson/status data without the user doing anything. The
// dashboard page itself is a plain one-shot fetch-on-load page (see
// napominalki-dashboard repo), so reloading the iframe is what makes
// it "live" here -- roughly matches how often the bot's own cache
// updates anyway, so there's no point polling faster.
// --------------------------------------------------------------
async function loadDashboard() {
  const cfg = await window.pywebview.api.get_settings();
  dashboardFrame.src = cfg.dashboard_url;
}

function startDashboardRefresh() {
  setInterval(() => {
    // Re-set src (not .reload()) so a same-URL frame still forces a refetch.
    const url = dashboardFrame.src;
    dashboardFrame.src = "about:blank";
    dashboardFrame.src = url;
  }, DASHBOARD_REFRESH_MS);
}

// --------------------------------------------------------------
// Update button (manual path -- shown only when autoupdate is off
// and a newer release exists)
// --------------------------------------------------------------
async function checkForUpdate() {
  const cfg = await window.pywebview.api.get_settings();
  const info = await window.pywebview.api.check_for_update();
  if (!info || !info.available) {
    updateBtn.classList.add("hidden");
    return;
  }
  if (cfg.autoupdate) {
    await window.pywebview.api.apply_update(info.download_url);
    return; // app is about to close + relaunch
  }
  updateBtn.textContent = `Обновить до v${info.version}`;
  updateBtn.classList.remove("hidden");
}

updateBtn.addEventListener("click", async () => {
  const info = await window.pywebview.api.check_for_update();
  if (info && info.available) {
    updateBtn.textContent = "Обновление...";
    await window.pywebview.api.apply_update(info.download_url);
  }
});

// --------------------------------------------------------------
// Startup
// --------------------------------------------------------------
(async function init() {
  buildGearTeeth();
  await loadSettings();
  await loadDashboard();
  startDashboardRefresh();
  checkForUpdate();
  setInterval(checkForUpdate, UPDATE_CHECK_MS);
})();
