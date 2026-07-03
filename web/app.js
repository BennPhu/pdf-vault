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

/* ------------------------------------------------------------ bootstrap */

window.addEventListener("pywebviewready", init);

async function init() {
  const state = await window.pywebview.api.get_state();
  $("version").textContent = "v" + state.version;
  if (!state.configured) {
    $("setup-modal").hidden = false;
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

dropzone.addEventListener("drop", async (e) => {
  const paths = [];
  for (const file of e.dataTransfer.files) {
    // pywebview exposes the real filesystem path on dropped files
    const p = file.pywebviewFullPath || file.path;
    if (p) paths.push(p);
  }
  if (!paths.length) {
    toast("Could not read dropped files — use 'click to browse' instead", "error");
    return;
  }
  dropzone.classList.add("bounce");
  setTimeout(() => dropzone.classList.remove("bounce"), 450);
  await addPaths(paths);
});

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
