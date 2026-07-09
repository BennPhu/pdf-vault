/* PDF Vault frontend logic (talks to Python via window.pywebview.api) */

"use strict";

const $ = (id) => document.getElementById(id);

let library = [];          // current index entries
let selected = new Set();  // selected filenames
let previewFile = null;    // filename shown in preview
let previewPage = 1;
let previewTotal = 1;
let splitMode = null;      // "range" | "individual"
let splitPage = 1;
let splitTotal = 1;
let undoStack = [];        // batches of deleted index entries
let redoStack = [];        // batches that can be re-deleted

/* ------------------------------------------------------------ bootstrap */

window.addEventListener("pywebviewready", init);

async function init() {
  const state = await window.pywebview.api.get_state();
  $("version").textContent = "v" + state.version;
  if (!state.configured) {
    $("setup-modal").hidden = false;
  }
  if (state.folder_access === false) {
    toast(
      "macOS is blocking access to your storage folder. Open System Settings → " +
      "Privacy & Security → Files and Folders and allow PDF Vault, or move your " +
      "storage folder outside Documents/Desktop.",
      "error"
    );
  }
  await refreshLibrary();
  checkUpdatesQuietly();
}

/* ------------------------------------------------------------- library */

async function refreshLibrary() {
  const res = await window.pywebview.api.list_library();
  library = res.entries || [];
  renderLibrary();
}

function renderLibrary() {
  const grid = $("library");
  grid.innerHTML = "";
  $("empty-state").hidden = library.length > 0;

  for (const entry of library) {
    const card = document.createElement("div");
    card.className = "card" + (selected.has(entry.filename) ? " selected" : "");
    card.title = entry.filename;

    const img = document.createElement("img");
    img.className = "card-thumb";
    if (entry.thumb) img.src = "data:image/png;base64," + entry.thumb;
    card.appendChild(img);

    const name = document.createElement("div");
    name.className = "card-name";
    name.textContent = entry.filename;
    card.appendChild(name);

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = (entry.added || "").slice(0, 10);
    card.appendChild(meta);

    const badge = document.createElement("span");
    badge.className = "pages-badge";
    badge.textContent = entry.pages + (entry.pages === 1 ? " page" : " pages");
    card.appendChild(badge);

    card.addEventListener("click", () => toggleSelect(entry.filename));
    grid.appendChild(card);
  }
  $("btn-unselect").hidden = selected.size === 0;
  $("btn-select-all").hidden = library.length === 0 || selected.size === library.length;
  $("btn-delete").hidden = selected.size === 0;
  $("btn-undo").hidden = undoStack.length === 0;
  $("btn-redo").hidden = redoStack.length === 0;
}

function toggleSelect(filename) {
  if (selected.has(filename)) {
    selected.delete(filename);
    if (previewFile === filename) clearPreview();
  } else {
    selected.add(filename);
    showPreview(filename, 1);
  }
  renderLibrary();
}

function unselectAll() {
  selected.clear();
  clearPreview();
  renderLibrary();
}

/* ------------------------------------------------------------- preview */

async function showPreview(filename, page) {
  const res = await window.pywebview.api.render_page(filename, page);
  if (!res.ok) { toast(res.error, "error"); return; }
  previewFile = filename;
  previewPage = res.page;
  previewTotal = res.total;
  $("preview-img").src = "data:image/png;base64," + res.image;
  $("preview-img").hidden = false;
  $("preview-placeholder").hidden = true;
  $("preview-nav").hidden = false;
  $("page-label").textContent = `${previewPage} / ${previewTotal}`;
}

function clearPreview() {
  previewFile = null;
  $("preview-img").hidden = true;
  $("preview-placeholder").hidden = false;
  $("preview-nav").hidden = true;
}

$("prev-page").addEventListener("click", () => {
  if (previewFile && previewPage > 1) showPreview(previewFile, previewPage - 1);
});
$("next-page").addEventListener("click", () => {
  if (previewFile && previewPage < previewTotal) showPreview(previewFile, previewPage + 1);
});

/* --------------------------------------------------------- drag & drop */

const dropzone = $("dropzone");

["dragenter", "dragover"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);

/* Fallback: JS can see the drop event (just not the file paths), so refresh
   the library shortly after any drop in case the Python callback is missed.
   Python processes the files first; these delayed refreshes pick them up. */
let nativeDropHandled = false;
document.addEventListener("drop", () => {
  nativeDropHandled = false;
  [600, 1500, 3000].forEach((ms) =>
    setTimeout(() => { if (!nativeDropHandled) refreshLibrary(); }, ms)
  );
});

/* Real file paths are not visible to JS on macOS — app.py intercepts the
   drop natively (pywebview DOM events) and calls onNativeDrop() with the
   result. The listeners above only provide the visual dragover feedback. */
window.onNativeDrop = function (res) {
  nativeDropHandled = true;
  dropzone.classList.remove("dragover");
  dropzone.classList.add("bounce");
  setTimeout(() => dropzone.classList.remove("bounce"), 450);
  handleAddResult(res);
};

dropzone.addEventListener("click", browse);
$("btn-browse").addEventListener("click", (e) => { e.stopPropagation(); browse(); });

async function browse() {
  const res = await window.pywebview.api.add_pdfs_dialog();
  handleAddResult(res);
}

async function addPaths(paths) {
  const res = await window.pywebview.api.add_paths(paths);
  handleAddResult(res);
}

function handleAddResult(res) {
  if (!res.ok) return; // cancelled
  if (res.added && res.added.length) {
    toast(`Added ${res.added.length} PDF${res.added.length > 1 ? "s" : ""} to the vault`, "success");
  }
  (res.errors || []).forEach((err) => toast(err, "error"));
  refreshLibrary();
}

/* -------------------------------------------------------------- actions */

$("btn-unselect").addEventListener("click", unselectAll);
$("btn-select-all").addEventListener("click", () => {
  library.forEach((entry) => selected.add(entry.filename));
  if (library.length && !previewFile) showPreview(library[0].filename, 1);
  renderLibrary();
  toast(`Selected all ${library.length} PDFs`, "success");
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!$("split-modal").hidden) closeSplitModal();
    else unselectAll();
  }
});

$("btn-delete").addEventListener("click", async () => {
  if (selected.size === 0) return;
  const n = selected.size;
  if (!confirm(`Delete ${n} PDF${n > 1 ? "s" : ""} from the vault?`)) return;
  const res = await window.pywebview.api.delete([...selected]);
  if (!res.ok) { toast(res.error, "error"); return; }
  if (res.deleted.length) {
    undoStack.push(res.deleted);
    redoStack = []; // a new delete clears the redo history
    toast(`Deleted ${res.deleted.length} PDF${res.deleted.length > 1 ? "s" : ""}`, "success");
  }
  (res.errors || []).forEach((err) => toast(err, "error"));
  selected.clear();
  clearPreview();
  refreshLibrary();
});

$("btn-undo").addEventListener("click", async () => {
  const batch = undoStack.pop();
  if (!batch) return;
  const res = await window.pywebview.api.restore(batch);
  if (!res.ok) { toast(res.error, "error"); return; }
  if (res.restored.length) {
    redoStack.push(res.restored);
    toast(`Restored ${res.restored.length} PDF${res.restored.length > 1 ? "s" : ""}`, "success");
  }
  (res.errors || []).forEach((err) => toast(err, "error"));
  refreshLibrary();
});

$("btn-redo").addEventListener("click", async () => {
  const batch = redoStack.pop();
  if (!batch) return;
  const res = await window.pywebview.api.delete(batch.map((e) => e.filename));
  if (!res.ok) { toast(res.error, "error"); return; }
  if (res.deleted.length) {
    undoStack.push(res.deleted);
    toast(`Deleted ${res.deleted.length} PDF${res.deleted.length > 1 ? "s" : ""} again`, "success");
  }
  (res.errors || []).forEach((err) => toast(err, "error"));
  refreshLibrary();
});

$("btn-merge").addEventListener("click", async () => {
  if (selected.size < 2) { toast("Select at least two PDFs to merge", "error"); return; }
  const res = await window.pywebview.api.merge([...selected]);
  if (res.ok) { toast(res.message, "success"); celebrate(); }
  else if (res.error !== "cancelled") toast(res.error, "error");
});

$("btn-split").addEventListener("click", () => openSplitModal("range"));
$("btn-individual").addEventListener("click", () => openSplitModal("individual"));

$("btn-master").addEventListener("click", async () => {
  const res = await window.pywebview.api.create_master();
  if (res.ok) { toast(res.message, "success"); celebrate(); }
  else if (res.error !== "cancelled") toast(res.error, "error");
});

$("btn-open-folder").addEventListener("click", () => window.pywebview.api.open_library_folder());

/* ---------------------------------------------------------- split modal */

function selectedOne() {
  if (selected.size !== 1) {
    toast("Select exactly one PDF first", "error");
    return null;
  }
  return [...selected][0];
}

async function openSplitModal(mode) {
  const filename = selectedOne();
  if (!filename) return;
  splitMode = mode;
  const entry = library.find((x) => x.filename === filename);
  splitTotal = entry ? entry.pages : 1;
  $("split-title").textContent =
    mode === "range" ? "Split — save pages as one PDF" : "Individual Splits — one file per page";
  $("split-confirm").textContent = mode === "range" ? "Save as One PDF…" : "Split to Files…";
  $("split-start").value = 1;
  $("split-start").max = splitTotal;
  $("split-end").value = splitTotal;
  $("split-end").max = splitTotal;
  $("split-modal").hidden = false;
  await showSplitPage(1);
}

async function showSplitPage(page) {
  const filename = [...selected][0];
  const res = await window.pywebview.api.render_page(filename, page);
  if (!res.ok) return;
  splitPage = res.page;
  $("split-img").src = "data:image/png;base64," + res.image;
  $("split-page-label").textContent = `${splitPage} / ${splitTotal}`;
}

$("split-prev").addEventListener("click", () => { if (splitPage > 1) showSplitPage(splitPage - 1); });
$("split-next").addEventListener("click", () => { if (splitPage < splitTotal) showSplitPage(splitPage + 1); });

$("split-start").addEventListener("input", (e) => {
  const v = parseInt(e.target.value);
  if (v >= 1 && v <= splitTotal) showSplitPage(v);
});
$("split-end").addEventListener("input", (e) => {
  const v = parseInt(e.target.value);
  if (v >= 1 && v <= splitTotal) showSplitPage(v);
});

$("split-cancel").addEventListener("click", closeSplitModal);
function closeSplitModal() { $("split-modal").hidden = true; splitMode = null; }

$("split-confirm").addEventListener("click", async () => {
  const filename = [...selected][0];
  const start = parseInt($("split-start").value);
  const end = parseInt($("split-end").value);
  if (!(start >= 1 && end >= start && end <= splitTotal)) {
    toast(`Enter a valid range between 1 and ${splitTotal}`, "error");
    return;
  }
  const api = window.pywebview.api;
  const res = splitMode === "range"
    ? await api.split_range(filename, start, end)
    : await api.split_individual(filename, start, end);
  if (res.ok) { toast(res.message, "success"); closeSplitModal(); celebrate(); }
  else if (res.error !== "cancelled") toast(res.error, "error");
});

/* ------------------------------------------------------ activity & stats */

function fmtUptime(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}h ${m}m` : m ? `${m}m ${s}s` : `${s}s`;
}

async function openActivityModal() {
  $("activity-modal").hidden = false;
  await refreshActivity();
}

async function refreshActivity() {
  const res = await window.pywebview.api.get_activity();
  if (!res.ok) { toast(res.error, "error"); return; }
  const s = res.stats;

  const cards = [
    ["Version", "v" + s.version],
    ["Uptime", fmtUptime(s.uptime_seconds)],
    ["Memory", s.memory_mb + " MB"],
    ["CPU time", s.cpu_seconds + " s"],
    ["Library", `${s.library_files} files · ${s.library_mb} MB`],
    ["Trash", `${s.trash_files} files · ${s.trash_mb} MB`],
    ["Indexed", s.index_entries + " entries"],
    ["Disk free", s.disk_free_gb != null ? `${s.disk_free_gb} / ${s.disk_total_gb} GB` : "n/a"],
  ];
  const grid = $("stats-grid");
  grid.innerHTML = "";
  for (const [label, value] of cards) {
    const el = document.createElement("div");
    el.className = "stat-card";
    const v = document.createElement("div");
    v.className = "stat-value";
    v.textContent = value;
    const l = document.createElement("div");
    l.className = "stat-label";
    l.textContent = label;
    el.append(v, l);
    grid.appendChild(el);
  }
  $("stats-storage").textContent = "Storage: " + s.storage_dir;

  const list = $("log-list");
  list.innerHTML = "";
  if (!res.log.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No activity yet this session.";
    list.appendChild(empty);
  }
  for (const ev of res.log) {
    const row = document.createElement("div");
    row.className = "log-row";
    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = ev.time.replace("T", " ");
    const action = document.createElement("span");
    action.className = "log-action log-" + ev.action;
    action.textContent = ev.action;
    const detail = document.createElement("span");
    detail.className = "log-detail";
    detail.textContent = ev.detail;
    row.append(time, action, detail);
    list.appendChild(row);
  }
}

$("btn-activity").addEventListener("click", openActivityModal);
$("activity-refresh").addEventListener("click", refreshActivity);
$("activity-close").addEventListener("click", () => { $("activity-modal").hidden = true; });

/* ------------------------------------------------------ storage / setup */

$("setup-choose").addEventListener("click", async () => {
  const res = await window.pywebview.api.choose_storage_dir();
  if (res.ok) { $("setup-modal").hidden = true; refreshLibrary(); }
});
$("setup-default").addEventListener("click", async () => {
  await window.pywebview.api.use_default_storage();
  $("setup-modal").hidden = true;
  refreshLibrary();
});

$("btn-storage").addEventListener("click", async () => {
  const res = await window.pywebview.api.choose_storage_dir();
  if (res.ok) {
    toast("Storage folder changed", "success");
    unselectAll();
    refreshLibrary();
  }
});

/* -------------------------------------------------------------- updates */

$("btn-updates").addEventListener("click", async () => {
  const res = await window.pywebview.api.check_updates();
  if (!res.ok) { toast(res.error, "error"); return; }
  if (!res.update) { toast("You are up to date!", "success"); return; }
  offerUpdate(res.update);
});

async function checkUpdatesQuietly() {
  try {
    const res = await window.pywebview.api.check_updates();
    if (res.ok && res.update) offerUpdate(res.update);
  } catch (_) { /* offline — stay quiet */ }
}

function offerUpdate(update) {
  if (confirm(`PDF Vault ${update.version} is available. Update now?`)) {
    toast("Downloading update…");
    window.pywebview.api.install_update().then((res) => {
      if (res.ok) toast(res.message || "Updated!", "success");
      else toast(res.error, "error");
    });
  }
}

/* --------------------------------------------------------------- toasts */

function toast(message, kind) {
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.textContent = message;
  $("toasts").appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity 0.4s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 400);
  }, 3200);
}

/* --------------------------------------------- tiny confetti celebration */

function celebrate() {
  const colors = ["#E07A5F", "#F4A259", "#7FB069", "#F2CC8F"];
  for (let i = 0; i < 18; i++) {
    const dot = document.createElement("div");
    const size = 6 + Math.random() * 6;
    Object.assign(dot.style, {
      position: "fixed",
      left: 45 + Math.random() * 10 + "%",
      top: "55%",
      width: size + "px",
      height: size + "px",
      borderRadius: "50%",
      background: colors[i % colors.length],
      pointerEvents: "none",
      zIndex: 200,
      transition: "transform 0.9s ease-out, opacity 0.9s",
    });
    document.body.appendChild(dot);
    requestAnimationFrame(() => {
      dot.style.transform = `translate(${(Math.random() - 0.5) * 320}px, ${-80 - Math.random() * 220}px)`;
      dot.style.opacity = "0";
    });
    setTimeout(() => dot.remove(), 1000);
  }
}
