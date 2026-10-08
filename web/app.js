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
const saveAllBtn = document.getElementById("save-all-btn");

let settingsOpen = false;
let currentDashboardUrl = ""; // base URL from config, without the ?theme= param

// --------------------------------------------------------------
// Gear teeth -- drawn programmatically so index.html doesn't need
// 6 hand-positioned <rect> tags.
//
// The ring in index.html is r=20/stroke-width=10, so it visually spans
// radius 15 (inner edge) to 25 (outer edge) from center (50,50). Each
// tooth's inner edge sits at radius 17 -- inside that band, guaranteeing
// overlap with no gap -- and only extends out to radius 30, a short
// protrusion past the ring rather than long floating rays (which is what
// made the first version read as a sun instead of a gear). Thicker
// (width 14) and only 6 of them so adjacent teeth don't crowd each other.
// --------------------------------------------------------------
function buildGearTeeth() {
  const g = document.getElementById("gear-teeth");
  const toothCount = 6;
  for (let i = 0; i < toothCount; i++) {
    const angle = (360 / toothCount) * i;
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", "43");
    rect.setAttribute("y", "20");
    rect.setAttribute("width", "14");
    rect.setAttribute("height", "13");
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

  document.getElementById("app-version").textContent = "v" + (cfg.version || "?");

  currentDashboardUrl = cfg.dashboard_url;
  return cfg;
}

// --------------------------------------------------------------
// One consolidated Save button -- saves URL + token together (per
// request: "instead of many save buttons, one save button that saves
// ALL the settings"). Voice/theme/toggles are separate control types
// (dropdown, icon buttons, switches) that apply as soon as you interact
// with them, same as most apps' instant-effect controls -- only the two
// text fields batch under this one button.
// --------------------------------------------------------------
saveAllBtn.addEventListener("click", async () => {
  const url = document.getElementById("field-url").value.trim();
  const token = document.getElementById("field-token").value.trim();
  await window.pywebview.api.save_setting("url", url);
  await window.pywebview.api.save_setting("token", token);
  showStatus("Сохранено");
});

// --------------------------------------------------------------
// Voice: picking a different option saves it immediately -- this is
// what real lesson announcements actually use, not just the test button.
// --------------------------------------------------------------
document.getElementById("field-voice").addEventListener("change", async (e) => {
  await window.pywebview.api.save_setting("voice", e.target.value);
  showStatus("Голос сохранён");
});

document.getElementById("voice-test-btn").addEventListener("click", async () => {
  const voice = document.getElementById("field-voice").value;
  showStatus("Проверка голоса...");
  const ok = await window.pywebview.api.test_voice(voice);
  showStatus(ok ? "Готово" : "Ошибка воспроизведения");
});

// --------------------------------------------------------------
// Theme buttons -- icon color itself flips via the [data-theme] CSS
// variables (--icon-color), so this only needs to set the attribute
// and persist it. Also re-points the dashboard iframe with a ?theme=
// param so the embedded page can match (see loadDashboard/reloadDashboard
// below) -- the dashboard itself needs a small matching change on its
// side to actually read that param; flagged separately.
// --------------------------------------------------------------
async function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  await window.pywebview.api.save_setting("theme", theme);
  reloadDashboard(theme);
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
//
// The ?theme= query param is this app's half of theme syncing with the
// embedded page: napominalki-dashboard is a DIFFERENT origin (GitHub
// Pages), so cross-origin rules block reaching into its DOM/CSS directly
// -- a URL param (or postMessage) is the only channel that reaches it.
// This app always sends it; the dashboard repo needs a small matching
// change to read `?theme=` and apply a dark stylesheet when present
// (today it only follows Telegram's own theme variables, which aren't
// set at all when opened in this iframe instead of inside Telegram).
// --------------------------------------------------------------
function reloadDashboard(theme) {
  if (!currentDashboardUrl) return;
  const sep = currentDashboardUrl.includes("?") ? "&" : "?";
  const url = currentDashboardUrl + sep + "theme=" + encodeURIComponent(theme);
  dashboardFrame.src = "about:blank";
  dashboardFrame.src = url;
}

async function loadDashboard() {
  const theme = document.documentElement.getAttribute("data-theme") || "light";
  reloadDashboard(theme);
}

function startDashboardRefresh() {
  setInterval(() => {
    const theme = document.documentElement.getAttribute("data-theme") || "light";
    reloadDashboard(theme);
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
    await window.pywebview.api.apply_update(info.download_url, info.size);
    return; // app is about to close + relaunch
  }
  updateBtn.textContent = `Обновить до v${info.version}`;
  updateBtn.classList.remove("hidden");
}

updateBtn.addEventListener("click", async () => {
  const info = await window.pywebview.api.check_for_update();
  if (info && info.available) {
    updateBtn.textContent = "Обновление...";
    await window.pywebview.api.apply_update(info.download_url, info.size);
  }
});

// --------------------------------------------------------------
// Startup
// --------------------------------------------------------------
// pywebview injects window.pywebview.api asynchronously, AFTER this page's
// own scripts have already started running -- calling the bridge before
// it's ready (which the previous version did, unconditionally, at the
// bottom of this file) silently fails every api.* call. That was the
// actual cause of both "voices list is empty" and "dashboard doesn't
// load": loadSettings()/loadDashboard() were running before the bridge
// existed. Fix: wait for the 'pywebviewready' event pywebview fires once
// it's actually available, falling back to running immediately in the
// rare case that event already fired before this listener was attached.
async function refreshStatus() {
  try {
    const s = await window.pywebview.api.get_status();
    document.getElementById("app-status").textContent = (s && s.lines ? s.lines : []).join("\n");
  } catch (e) { /* status line is best-effort */ }
}

async function init() {
  buildGearTeeth();
  await loadSettings();
  refreshStatus();
  setInterval(refreshStatus, 5000);
  await loadDashboard();
  startDashboardRefresh();
  checkForUpdate();
  setInterval(checkForUpdate, UPDATE_CHECK_MS);
}

if (window.pywebview && window.pywebview.api) {
  init();
} else {
  window.addEventListener("pywebviewready", init);
}
