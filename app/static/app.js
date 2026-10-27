/* ============================================================
   Vinotag — frontend logic (vanilla JS, no dependencies)
   ============================================================ */

const $ = (id) => document.getElementById(id);

const state = {
  shelves: [],
  bottles: [],
  view: "fridge",
  search: "",
  currentImage: "",
  selectedShelf: "",
  analyzing: false,
  analyzeTimer: null,
  analyzeStarted: 0,
};

document.addEventListener("DOMContentLoaded", init);

/* ---------------- init ---------------- */

async function init() {
  bindEvents();
  // Deep-link support: /?view=add|fridge|list|settings (handy for QR codes)
  const initial = new URLSearchParams(location.search).get("view");
  if (initial && ["fridge", "list", "add", "settings"].includes(initial)) {
    state.view = initial;
  }
  await loadConfig();
  await loadBottles();
  renderAll();
  showView(state.view);
}

function bindEvents() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });
  $("settingsBtn").addEventListener("click", () => showView("settings"));
  $("modeToggle").addEventListener("click", toggleMode);
  $("searchInput").addEventListener("input", (e) => {
    state.search = e.target.value.trim().toLowerCase();
    renderAll();
  });
  $("photoInput").addEventListener("change", handlePhotoChange);
  $("analyzeBtn").addEventListener("click", analyzePhoto);
  $("saveBtn").addEventListener("click", saveCurrentWine);
  $("resetBtn").addEventListener("click", resetAddForm);
  $("fab").addEventListener("click", () => showView("add"));
  $("llmCheckBtn").addEventListener("click", checkLlm);
  $("importBundledBtn").addEventListener("click", () => runImport(null));
  $("importFileBtn").addEventListener("click", () => $("importFileInput").click());
  $("importFileInput").addEventListener("change", () => {
    const f = $("importFileInput").files[0];
    if (f) runImport(f);
    $("importFileInput").value = "";
  });
  $("sheetBackdrop").addEventListener("click", closeSheet);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSheet();
  });
}

/* ---------------- data loading ---------------- */

async function loadConfig() {
  try {
    const cfg = await api("/api/config");
    state.shelves = cfg.shelves || [];
    $("llmUrl").textContent = cfg.llm.server;
    $("llmModel").textContent = cfg.llm.model;
    $("shelfList").textContent = cfg.shelves.join(", ");
    $("bottleCount").textContent = String(cfg.bottleCount);
    renderShelfPicker();
  } catch (err) {
    toast("Could not load app config: " + err.message);
  }
}

async function loadBottles() {
  try {
    state.bottles = await api("/api/bottles");
  } catch (err) {
    toast("Could not load inventory: " + err.message);
    state.bottles = [];
  }
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data.detail) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch (_) { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

/* ---------------- wine type classification (dot colors) ---------------- */

function wineType(bottle) {
  const text = ((bottle.variety || "") + " " + (bottle.wine || "")).toLowerCase();
  // Order matters: rosé first (e.g. "Pinot Noir Rosé"), then red before white
  // so "Cabernet Sauvignon" is not caught by the "sauvignon" white keyword.
  if (/(ros[eé]|blush)/.test(text)) return "rose";
  if (/(red|cabernet|merlot|sangiovese|nebbiolo|amarone|brunello|barolo|barbera|montepulciano|zinfandel|syrah|shiraz|pinot noir|grenache|tempranillo|malbec|mourvedre|petit verdot|dolcetto|aglianico|frappato|nerello|corvina|corvinone|rondinella|carignan|cinsault|tannat|durif|gamay|pinotage|touriga|arnanca|cencu|sagrantino|pignolo)/.test(text)) return "red";
  if (/(white|blanc|sauvignon|chardonnay|chenin|riesling|pinot grigio|pinot gris|pinot blanc|albari|vermentino|viognier|moscato|prosecco|cava|champagne|sparkling|frascati|soave|gavi|cortese|torront|assyrtiko|fiano|greco|verdeca|vino blanco)/.test(text)) return "white";
  return "other";
}

function matchesSearch(b) {
  if (!state.search) return true;
  const haystack = [b.wine, b.variety, b.vintage, b.vineyard_producer, b.shelf, b.notes]
    .join(" ")
    .toLowerCase();
  return state.search.split(/\s+/).every((term) => haystack.includes(term));
}

function fridgeShelves() {
  const known = new Set(state.shelves);
  const extra = [...new Set(state.bottles.map((b) => b.shelf).filter((s) => s && !known.has(s)))];
  return [...state.shelves, ...extra];
}

/* ---------------- rendering ---------------- */

function renderAll() {
  renderFridge();
  renderList();
}

function renderFridge() {
  const body = $("fridgeBody");
  body.querySelectorAll(".shelf-row, .fridge-empty").forEach((el) => el.remove());

  if (!state.bottles.length) {
    const empty = document.createElement("div");
    empty.className = "fridge-empty";
    empty.textContent = "Your fridge is empty. Tap + to add your first bottle.";
    body.appendChild(empty);
    return;
  }

  fridgeShelves().forEach((shelf) => {
    const items = state.bottles.filter((b) => b.shelf === shelf);

    const row = document.createElement("div");
    row.className = "shelf-row";

    // per-shelf counts by wine type
    const counts = document.createElement("div");
    counts.className = "shelf-counts";
    const byType = { red: 0, white: 0, rose: 0, other: 0 };
    items.forEach((b) => { byType[wineType(b)] += 1; });
    ["red", "white", "rose"].forEach((type) => counts.appendChild(countEl(type, byType[type])));
    if (byType.other > 0) counts.appendChild(countEl("other", byType.other));
    row.appendChild(counts);

    // shelf unit: dots sitting on the shelf bar
    const unit = document.createElement("div");
    unit.className = "shelf-unit";

    const wineRow = document.createElement("div");
    wineRow.className = "shelf-wine";
    if (!items.length) {
      const none = document.createElement("span");
      none.className = "shelf-empty-hint";
      none.textContent = "·";
      wineRow.appendChild(none);
    }
    items.forEach((b) => {
      const dot = document.createElement("button");
      dot.className = "bottle-dot " + wineType(b) + (matchesSearch(b) ? "" : " dim");
      const label = [b.wine, b.vintage, b.vineyard_producer].filter(Boolean).join(" · ");
      dot.title = label;
      dot.setAttribute("aria-label", label);
      dot.addEventListener("click", () => openSheet(b.id));
      wineRow.appendChild(dot);
    });

    const shelfLabel = document.createElement("div");
    shelfLabel.className = "shelf-label";
    shelfLabel.textContent = shelf.toUpperCase();

    unit.appendChild(wineRow);
    unit.appendChild(shelfLabel);
    row.appendChild(unit);
    body.appendChild(row);
  });
}

function countEl(type, n) {
  const el = document.createElement("span");
  el.className = "c";
  const mini = document.createElement("span");
  mini.className = "dot-mini " + type;
  el.appendChild(mini);
  el.appendChild(document.createTextNode(n + "x"));
  return el;
}

function renderList() {
  const wrap = $("listContent");
  wrap.innerHTML = "";
  let any = false;

  fridgeShelves().forEach((shelf) => {
    const items = state.bottles.filter((b) => b.shelf === shelf && matchesSearch(b));
    if (!items.length) return;
    any = true;

    const section = document.createElement("div");
    section.className = "list-section";
    const title = document.createElement("div");
    title.className = "list-section-title";
    title.textContent = `${shelf.toUpperCase()} (${items.length})`;
    section.appendChild(title);
    items.forEach((b) => section.appendChild(listRow(b)));
    wrap.appendChild(section);
  });

  if (!any) {
    wrap.innerHTML = '<p class="empty-msg">No bottles match.</p>';
  }
}

function listRow(b) {
  const row = document.createElement("div");
  row.className = "list-row";
  row.addEventListener("click", () => openSheet(b.id));

  const thumb = document.createElement("div");
  thumb.className = "list-thumb";
  if (b.has_image) {
    const img = document.createElement("img");
    img.src = `/api/bottles/${b.id}/image`;
    img.alt = "";
    img.loading = "lazy";
    thumb.appendChild(img);
  } else {
    const mini = document.createElement("span");
    mini.className = "dot-mini " + wineType(b);
    thumb.appendChild(mini);
  }

  const info = document.createElement("div");
  info.className = "list-info";
  const name = document.createElement("div");
  name.className = "list-name";
  name.textContent = b.wine;
  const meta = document.createElement("div");
  meta.className = "list-meta";
  meta.textContent = [b.vintage, b.variety, b.vineyard_producer].filter(Boolean).join(" · ");
  info.appendChild(name);
  info.appendChild(meta);

  row.appendChild(thumb);
  row.appendChild(info);
  return row;
}

/* ---------------- views ---------------- */

function showView(name) {
  state.view = name;
  ["fridge", "list", "add", "settings"].forEach((v) => {
    $(v + "View").classList.toggle("hidden", v !== name);
  });
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  $("toolbar").classList.toggle("hidden", name === "add" || name === "settings");
  $("fab").classList.toggle("hidden", name !== "fridge");
  $("modeToggle").querySelector("span").textContent =
    name === "list" ? "Fridge mode" : "List mode";
  if (name === "settings") refreshSettings();
  if (name === "list") renderList();
  window.scrollTo({ top: 0 });
}

function toggleMode() {
  showView(state.view === "list" ? "fridge" : "list");
}

/* ---------------- bottle detail sheet ---------------- */

function openSheet(bottleId) {
  const b = state.bottles.find((x) => x.id === bottleId);
  if (!b) return;

  const content = $("sheetContent");
  content.innerHTML = "";

  if (b.has_image) {
    const img = document.createElement("img");
    img.className = "sheet-photo";
    img.src = `/api/bottles/${b.id}/image`;
    img.alt = "Label photo";
    content.appendChild(img);
  }

  const name = document.createElement("h3");
  name.className = "sheet-name";
  name.textContent = b.wine;
  content.appendChild(name);

  const meta = document.createElement("div");
  meta.className = "sheet-meta";
  meta.textContent = [b.vintage, b.variety, b.vineyard_producer].filter(Boolean).join(" · ");
  content.appendChild(meta);

  if (b.notes) {
    const notes = document.createElement("p");
    notes.className = "sheet-notes";
    notes.textContent = b.notes;
    content.appendChild(notes);
  }

  const added = document.createElement("div");
  added.className = "sheet-added";
  added.textContent = "Added " + (b.date_added || "");
  content.appendChild(added);

  const moveLabel = document.createElement("div");
  moveLabel.className = "sheet-move-label";
  moveLabel.textContent = "Move to shelf";
  content.appendChild(moveLabel);

  const chips = document.createElement("div");
  chips.className = "chip-row";
  fridgeShelves().forEach((shelf) => {
    const chip = document.createElement("button");
    chip.className = "chip" + (shelf === b.shelf ? " current" : "");
    chip.textContent = shelf;
    chip.addEventListener("click", async () => {
      if (shelf === b.shelf) return;
      try {
        await api(`/api/bottles/${b.id}`, { method: "PATCH", body: { shelf } });
        toast(`Moved to ${shelf}`);
        await loadBottles();
        renderAll();
        closeSheet();
      } catch (err) {
        toast(err.message);
      }
    });
    chips.appendChild(chip);
  });
  content.appendChild(chips);

  const del = document.createElement("button");
  del.className = "btn danger full";
  del.textContent = "Remove from fridge";
  del.addEventListener("click", async () => {
    if (!confirm(`Remove "${b.wine}" from the inventory?`)) return;
    try {
      await api(`/api/bottles/${b.id}`, { method: "DELETE" });
      toast("Bottle removed");
      await loadBottles();
      renderAll();
      closeSheet();
    } catch (err) {
      toast(err.message);
    }
  });
  content.appendChild(del);

  $("sheet").classList.remove("hidden");
  $("sheetBackdrop").classList.remove("hidden");
}

function closeSheet() {
  $("sheet").classList.add("hidden");
  $("sheetBackdrop").classList.add("hidden");
}

/* ---------------- add flow ---------------- */

function handlePhotoChange(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    resizeImage(e.target.result, 1600, 0.82, (dataUrl) => {
      state.currentImage = dataUrl;
      const preview = $("preview");
      preview.src = dataUrl;
      preview.classList.remove("hidden");
      $("photoPlaceholder").classList.add("hidden");
      $("analyzeBtn").disabled = false;
    });
  };
  reader.readAsDataURL(file);
}

function resizeImage(dataUrl, maxDimension, quality, done) {
  const img = new Image();
  img.onload = () => {
    const scale = Math.min(1, maxDimension / Math.max(img.width, img.height));
    const width = Math.round(img.width * scale);
    const height = Math.round(img.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d").drawImage(img, 0, 0, width, height);
    done(canvas.toDataURL("image/jpeg", quality));
  };
  img.src = dataUrl;
}

async function analyzePhoto() {
  if (!state.currentImage || state.analyzing) return;
  state.analyzing = true;
  state.analyzeStarted = Date.now();
  setAnalyzeBusy(true);
  const status = $("analyzeStatus");
  status.className = "status info";
  tickAnalyzeStatus();
  state.analyzeTimer = setInterval(tickAnalyzeStatus, 1000);

  try {
    const result = await api("/api/analyze", {
      method: "POST",
      body: { image: state.currentImage },
    });
    $("fWine").value = result.wine || "";
    $("fVariety").value = result.variety || "";
    $("fVintage").value = result.vintage || "";
    $("fProducer").value = result.vineyardProducer || "";
    $("fNotes").value = result.notes || "";

    const badge = $("confidenceBadge");
    if (result.confidence) {
      badge.textContent = "AI confidence: " + result.confidence;
      badge.className = "badge " + result.confidence;
    } else {
      badge.className = "badge hidden";
    }

    status.className = "status info hidden";
    status.textContent = "";
    $("resultCard").classList.remove("hidden");
    renderShelfPicker();
    setTimeout(() => {
      $("resultCard").scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  } catch (err) {
    status.className = "status error";
    status.textContent = err.message;
  } finally {
    state.analyzing = false;
    clearInterval(state.analyzeTimer);
    setAnalyzeBusy(false);
  }
}

function tickAnalyzeStatus() {
  const secs = Math.round((Date.now() - state.analyzeStarted) / 1000);
  $("analyzeStatus").textContent =
    `Asking the model… ${secs}s — local models can take a while on a big photo.`;
}

function setAnalyzeBusy(busy) {
  const btn = $("analyzeBtn");
  btn.disabled = busy || !state.currentImage;
  btn.innerHTML = busy
    ? '<span class="spinner"></span> Identifying…'
    : "Identify wine";
}

function renderShelfPicker() {
  const wrap = $("shelfPicker");
  wrap.innerHTML = "";
  state.shelves.forEach((shelf) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip" + (state.selectedShelf === shelf ? " current" : "");
    btn.textContent = shelf;
    btn.addEventListener("click", () => {
      state.selectedShelf = shelf;
      renderShelfPicker();
      $("saveBtn").disabled = false;
    });
    wrap.appendChild(btn);
  });
}

async function saveCurrentWine() {
  const payload = {
    wine: $("fWine").value.trim(),
    variety: $("fVariety").value.trim(),
    vintage: $("fVintage").value.trim(),
    vineyard_producer: $("fProducer").value.trim(),
    shelf: state.selectedShelf,
    notes: $("fNotes").value.trim(),
  };
  if (!payload.wine) { toast("Please enter a wine name."); return; }
  if (!payload.shelf) { toast("Choose a shelf first."); return; }
  if (state.currentImage) payload.label_image = state.currentImage;

  const btn = $("saveBtn");
  btn.disabled = true;
  try {
    await api("/api/bottles", { method: "POST", body: payload });
    toast("Bottle saved");
    await loadBottles();
    resetAddForm();
    renderAll();
    showView("fridge");
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = !state.selectedShelf;
  }
}

function resetAddForm() {
  state.currentImage = "";
  state.selectedShelf = "";
  $("photoInput").value = "";
  const preview = $("preview");
  preview.classList.add("hidden");
  preview.src = "";
  $("photoPlaceholder").classList.remove("hidden");
  $("analyzeBtn").disabled = true;
  $("analyzeBtn").textContent = "Identify wine";
  $("resultCard").classList.add("hidden");
  ["fWine", "fVariety", "fVintage", "fProducer", "fNotes"].forEach((id) => { $(id).value = ""; });
  $("confidenceBadge").className = "badge hidden";
  $("saveBtn").disabled = true;
  const status = $("analyzeStatus");
  status.className = "status info hidden";
  status.textContent = "";
  renderShelfPicker();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------------- settings ---------------- */

async function refreshSettings() {
  const el = $("llmStatus");
  el.textContent = "Checking…";
  el.className = "kv-val";
  try {
    const status = await api("/api/llm/status");
    if (status.reachable) {
      el.textContent = status.model_loaded ? "Server up · model loaded" : "Server up · model NOT loaded";
      el.className = "kv-val " + (status.model_loaded ? "ok" : "warn");
    } else {
      el.textContent = "Unreachable";
      el.className = "kv-val err";
    }
  } catch (_) {
    el.textContent = "Unreachable";
    el.className = "kv-val err";
  }
}

async function checkLlm() {
  const btn = $("llmCheckBtn");
  btn.disabled = true;
  await refreshSettings();
  btn.disabled = false;
}

/* ---------------- spreadsheet import ---------------- */

async function runImport(file) {
  const status = $("importStatus");
  const btns = [$("importBundledBtn"), $("importFileBtn")];
  btns.forEach((b) => (b.disabled = true));
  status.className = "status info";
  status.textContent = "Importing…";
  try {
    let res;
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      res = await fetch("/api/import", { method: "POST", body: fd });
    } else {
      res = await fetch("/api/import", { method: "POST" });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Import failed (${res.status})`);
    status.className = "status success";
    status.textContent =
      `Imported ${data.added} new bottle(s)` +
      (data.skipped ? `, ${data.skipped} already present` : "") +
      `. Total: ${data.total}`;
    await loadConfig();
    renderAll();
  } catch (err) {
    status.className = "status error";
    status.textContent = err.message;
  } finally {
    btns.forEach((b) => (b.disabled = false));
  }
}

/* ---------------- toast ---------------- */

let toastTimer = null;
function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}
