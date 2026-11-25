// Progressive enhancement. Every page works without this file except Add,
// which needs it to poll the extraction job.
"use strict";

const FETCH_HEADERS = { "X-Requested-With": "fetch" };

async function post(form) {
  const resp = await fetch(form.action, {
    method: "POST",
    body: new FormData(form),
    headers: FETCH_HEADERS,
  });
  if (!resp.ok && resp.status !== 204) throw new Error(`HTTP ${resp.status}`);
  return resp;
}

function setWeekBadge(delta) {
  const tab = document.querySelector('.tabs a[href="/week"]');
  if (!tab) return;
  let badge = tab.querySelector("[data-week-count]");
  const next = (badge ? parseInt(badge.textContent, 10) : 0) + delta;
  if (next <= 0) { badge?.remove(); return; }
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "badge";
    badge.dataset.weekCount = "";
    tab.append(" ", badge);
  }
  badge.textContent = String(next);
}

// --- Recipes: add/remove from this week without reloading ---------------------
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!form.matches("[data-week-toggle]")) return;
  event.preventDefault();
  const button = form.querySelector("button");
  const card = form.closest(".card");
  const adding = button.getAttribute("aria-pressed") !== "true";
  try {
    await post(form);
  } catch {
    form.submit();
    return;
  }
  const name = card.querySelector(".card-name").textContent;
  button.setAttribute("aria-pressed", String(adding));
  button.setAttribute("aria-label", adding ? `Remove ${name} from this week` : `Add ${name} to this week`);
  card.classList.toggle("in-week", adding);
  form.action = form.action.replace(adding ? "/week/add/" : "/week/remove/", adding ? "/week/remove/" : "/week/add/");
  setWeekBadge(adding ? 1 : -1);
});

// --- This week: tick items you already have ------------------------------------
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!form.matches("[data-check]")) return;
  event.preventDefault();
  const button = form.querySelector("button");
  const nowChecked = button.value === "1";
  const data = new FormData(form);
  data.set("checked", button.value);
  try {
    const resp = await fetch(form.action, { method: "POST", body: data, headers: FETCH_HEADERS });
    if (!resp.ok) throw new Error();
  } catch {
    return;
  }
  button.setAttribute("aria-checked", String(nowChecked));
  button.value = nowChecked ? "" : "1";
  updateNotesText();
});

function updateNotesText() {
  const area = document.querySelector("[data-notes-text]");
  if (!area) return;
  const out = [];
  document.querySelectorAll(".aisle").forEach((aisle) => {
    const lines = [...aisle.querySelectorAll('.check[aria-checked="false"] .line')].map((l) => l.textContent.trim());
    if (lines.length) out.push(aisle.querySelector("h3").textContent.trim(), ...lines);
  });
  area.value = out.join("\n");
}

// --- Confirm destructive actions --------------------------------------------------
document.addEventListener("submit", (event) => {
  const message = event.target.dataset?.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
}, true);

// --- Copy list ---------------------------------------------------------------------
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  // Plain-HTTP fallback (LAN without Tailscale): select a textarea and copy.
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.cssText = "position:fixed;top:0;left:0;opacity:0;font-size:16px";
  document.body.append(area);
  area.focus();
  area.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  area.remove();
  return ok;
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  const text = document.querySelector("[data-notes-text]").value;
  const toast = document.querySelector("[data-toast]");
  let ok = false;
  try { ok = text ? await copyText(text) : false; } catch { ok = false; }
  if (!text) {
    toast.textContent = "Nothing to copy. Everything is ticked.";
  } else if (ok) {
    toast.textContent = "Copied. Paste it into Notes.";
  } else {
    // Last resort: show the text so it can be selected by hand.
    const area = document.querySelector("[data-notes-text]");
    area.classList.remove("visually-hidden");
    area.removeAttribute("aria-hidden");
    area.rows = Math.min(20, text.split("\n").length + 1);
    area.focus();
    area.select();
    toast.textContent = "Couldn't copy automatically. Select the text above and copy it.";
  }
  toast.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.hidden = true; }, 4000);
});

// --- Editor: add and remove ingredient rows -----------------------------------------
document.addEventListener("click", (event) => {
  const add = event.target.closest("[data-add-row]");
  if (add) {
    const form = add.closest("[data-editor]");
    const row = form.querySelector("[data-row-template]").content.firstElementChild.cloneNode(true);
    form.querySelector("[data-rows]").append(row);
    row.querySelector(".qty").focus();
    return;
  }
  const remove = event.target.closest("[data-remove-row]");
  if (remove) remove.closest(".ing-row").remove();
});

// --- Add: start a job and poll it ------------------------------------------------------
function initAdd() {
  const form = document.querySelector("[data-add-form]");
  if (!form) return;
  const progress = document.querySelector("[data-progress]");
  const stage = document.querySelector("[data-stage]");
  const error = document.querySelector("[data-error]");
  const button = form.querySelector("button");

  function fail(message) {
    progress.hidden = true;
    error.textContent = message;
    error.hidden = false;
    button.disabled = false;
    button.textContent = "Try again";
  }

  async function poll(id) {
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      let job;
      try {
        const resp = await fetch(`/api/jobs/${id}`, { headers: FETCH_HEADERS });
        if (resp.status === 401) { window.location = `/login?next=${encodeURIComponent(location.pathname + location.search)}`; return; }
        job = await resp.json();
      } catch {
        continue; // flaky Wi-Fi: keep trying
      }
      if (job.stage) stage.textContent = job.stage;
      if (job.status === "done") { window.location = `/review/${id}`; return; }
      if (job.status === "failed") { fail(job.error); return; }
    }
  }

  async function start() {
    error.hidden = true;
    progress.hidden = false;
    stage.textContent = "Starting…";
    button.disabled = true;
    try {
      const resp = await fetch("/api/jobs", { method: "POST", body: new FormData(form), headers: FETCH_HEADERS });
      const body = await resp.json();
      if (!resp.ok) { fail(body.detail || "Couldn't start. Try again."); return; }
      poll(body.id);
    } catch {
      fail("Couldn't reach the app. Check your Wi-Fi and try again.");
    }
  }

  form.addEventListener("submit", (event) => { event.preventDefault(); start(); });
  if (form.hasAttribute("data-autostart")) start();
}

initAdd();
