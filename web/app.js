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
let searchQuery = "";      // live library filter
let editFile = null;       // filename open in the page editor
let editPage = 1;
let editTotal = 1;

/* ------------------------------------------------------------ bootstrap */

window.addEventListener("pywebviewready", init);

let devMode = false;

async function init() {
  const state = await window.pywebview.api.get_state();
  $("version").textContent = "v" + state.version;
  devMode = !!state.dev_mode;
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
  pruneThumbCache();
  renderLibrary();
}

/* Lazy thumbnails: cards render instantly without images; each thumbnail
   is fetched only when its card scrolls into view, then cached. */
const thumbCache = new Map();

function thumbKey(entry) {
  return `${entry.filename}|${entry.size_bytes || 0}|${entry.pages}`;
}

function pruneThumbCache() {
  const live = new Set(library.map(thumbKey));
  for (const key of thumbCache.keys()) {
    if (!live.has(key)) thumbCache.delete(key);
  }
}

const thumbObserver = new IntersectionObserver((observations) => {
  for (const obs of observations) {
    if (!obs.isIntersecting) continue;
    thumbObserver.unobserve(obs.target);
    loadThumb(obs.target);
  }
}, { rootMargin: "200px" });

async function loadThumb(img) {
  const key = img.dataset.key;
  const filename = img.dataset.filename;
  if (thumbCache.has(key)) {
    img.src = "data:image/jpeg;base64," + thumbCache.get(key);
    return;
  }
  const res = await window.pywebview.api.get_thumb(filename);
  if (res.ok && res.thumb) {
    thumbCache.set(key, res.thumb);
    img.src = "data:image/jpeg;base64," + res.thumb;
  }
}

function visibleLibrary() {
  if (!searchQuery) return library;
  const q = searchQuery.toLowerCase();
  return library.filter((e) => e.filename.toLowerCase().includes(q));
}

function renderLibrary() {
  const grid = $("library");
  grid.innerHTML = "";
  const shown = visibleLibrary();
  $("empty-state").hidden = library.length > 0;

  if (library.length > 0 && shown.length === 0) {
    const none = document.createElement("p");
    none.className = "muted no-results";
    none.textContent = `No PDFs match \u201C${searchQuery}\u201D`;
    grid.appendChild(none);
  }

  for (const entry of shown) {
    const card = document.createElement("div");
    card.className = "card" + (selected.has(entry.filename) ? " selected" : "");
    card.title = entry.filename + " (double-click name to rename)";

    const img = document.createElement("img");
    img.className = "card-thumb";
    img.dataset.filename = entry.filename;
    img.dataset.key = thumbKey(entry);
    if (thumbCache.has(img.dataset.key)) {
      img.src = "data:image/jpeg;base64," + thumbCache.get(img.dataset.key);
    } else if (!entry.missing) {
      thumbObserver.observe(img);
    }
    card.appendChild(img);

    const name = document.createElement("div");
    name.className = "card-name";
    name.textContent = entry.filename;
    name.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      renameEntry(entry.filename);
    });
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

$("search").addEventListener("input", (e) => {
  searchQuery = e.target.value.trim();
  renderLibrary();
});

async function renameEntry(filename) {
  const stem = filename.replace(/\.pdf$/i, "");
  const input = prompt("Rename PDF:", stem);
  if (input === null) return;
  const newName = input.trim();
  if (!newName || newName === stem) return;
  const res = await window.pywebview.api.rename(filename, newName);
  if (!res.ok) { toast(res.error, "error"); return; }
  if (selected.has(filename)) {
    selected.delete(filename);
    selected.add(res.entry.filename);
  }
  if (previewFile === filename) previewFile = res.entry.filename;
  toast(`Renamed to ${res.entry.filename}`, "success");
  refreshLibrary();
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
  const changed = previewFile !== filename;
  previewFile = filename;
  previewPage = res.page;
  previewTotal = res.total;
  $("preview-img").src = "data:image/jpeg;base64," + res.image;
  $("preview-img").hidden = false;
  $("preview-placeholder").hidden = true;
  $("preview-nav").hidden = false;
  $("page-label").textContent = `${previewPage} / ${previewTotal}`;
  $("preview-info-btn").hidden = false;
  if (changed && !$("file-info-panel").hidden) refreshFileInfoPanel();
}

function clearPreview() {
  previewFile = null;
  $("preview-img").hidden = true;
  $("preview-placeholder").hidden = false;
  $("preview-nav").hidden = true;
  $("preview-info-btn").hidden = true;
  $("info-tooltip").hidden = true;
  $("file-info-panel").hidden = true;
}

/* ------------------------------------------------ file info dot & panel */

const FI_LABELS = {
  filename: "Name", pages: "Pages", size_bytes: "Size", added: "Added",
  modified: "Modified", page_size: "Page size", encrypted: "Encrypted",
  title: "Title", author: "Author", creator: "Creator",
  producer: "Producer", format: "PDF version",
};

function fmtSize(bytes) {
  return bytes < 1048576
    ? (bytes / 1024).toFixed(1) + " KB"
    : (bytes / 1048576).toFixed(2) + " MB";
}

function fiFormat(key, value) {
  if (key === "size_bytes") return fmtSize(value);
  if (key === "encrypted") return value ? "Yes" : "No";
  if (key === "added" || key === "modified") return String(value).replace("T", " ");
  return String(value);
}

$("preview-info-btn").addEventListener("mouseenter", () => {
  const entry = library.find((x) => x.filename === previewFile);
  if (!entry) return;
  const tip = $("info-tooltip");
  tip.textContent = "";
  const facts = [
    entry.filename,
    `${entry.pages} page${entry.pages === 1 ? "" : "s"} \u00b7 ${fmtSize(entry.size_bytes || 0)}`,
    "Added " + String(entry.added || "").replace("T", " "),
  ];
  for (const f of facts) {
    const line = document.createElement("div");
    line.textContent = f;
    tip.appendChild(line);
  }
  tip.hidden = false;
});
$("preview-info-btn").addEventListener("mouseleave", () => { $("info-tooltip").hidden = true; });

async function refreshFileInfoPanel() {
  const res = await window.pywebview.api.get_file_info(previewFile);
  if (!res.ok) { toast(res.error, "error"); return; }
  const rows = $("file-info-rows");
  rows.innerHTML = "";
  for (const [key, label] of Object.entries(FI_LABELS)) {
    if (res.info[key] === undefined || res.info[key] === "") continue;
    const row = document.createElement("div");
    row.className = "file-info-row";
    const l = document.createElement("div");
    l.className = "fi-label";
    l.textContent = label;
    const v = document.createElement("div");
    v.className = "fi-value";
    v.textContent = fiFormat(key, res.info[key]);
    row.append(l, v);
    rows.appendChild(row);
  }
}

$("preview-info-btn").addEventListener("click", async () => {
  const panel = $("file-info-panel");
  if (!panel.hidden) { panel.hidden = true; return; }
  if (!previewFile) return;
  panel.hidden = false;
  await refreshFileInfoPanel();
});
$("file-info-close").addEventListener("click", () => { $("file-info-panel").hidden = true; });

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
window.onNativeDropPaths = function (paths) {
  nativeDropHandled = true;
  dropzone.classList.remove("dragover");
  dropzone.classList.add("bounce");
  setTimeout(() => dropzone.classList.remove("bounce"), 450);
  addPathsWithProgress(paths);
};

dropzone.addEventListener("click", browse);
$("btn-browse").addEventListener("click", (e) => { e.stopPropagation(); browse(); });

async function browse() {
  const res = await window.pywebview.api.pick_files();
  if (!res.ok) return; // cancelled
  await addPathsWithProgress(res.paths);
}

/* Add files one API call at a time so the window never freezes and the
   user sees live progress on big batches. */
let importing = false;
async function addPathsWithProgress(paths) {
  if (importing || !paths || !paths.length) return;
  importing = true;
  const overlay = $("import-overlay");
  const bar = $("import-bar");
  const label = $("import-label");
  overlay.hidden = false;
  bar.style.width = "0%";
  let added = 0;
  const errors = [];
  try {
    for (let i = 0; i < paths.length; i++) {
      const name = paths[i].split("/").pop();
      label.textContent = `Adding ${i + 1} / ${paths.length} \u2014 ${name}`;
      bar.style.width = `${((i + 1) / paths.length) * 100}%`;
      const res = await window.pywebview.api.add_paths([paths[i]]);
      if (res.ok) {
        added += (res.added || []).length;
        errors.push(...(res.errors || []));
      } else {
        errors.push(res.error);
      }
    }
  } finally {
    overlay.hidden = true;
    importing = false;
  }
  if (added) {
    toast(`Added ${added} file${added > 1 ? "s" : ""} to the vault`, "success");
  }
  errors.slice(0, 5).forEach((err) => toast(err, "error"));
  if (errors.length > 5) toast(`\u2026and ${errors.length - 5} more errors`, "error");
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
    else if (!$("edit-modal").hidden) closeEditModal();
    else if (searchQuery) {
      $("search").value = "";
      searchQuery = "";
      renderLibrary();
    } else unselectAll();
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

$("btn-compress").addEventListener("click", async () => {
  if (selected.size === 0) { toast("Select PDFs to compress first", "error"); return; }
  toast("Compressing\u2026");
  const res = await window.pywebview.api.compress([...selected]);
  if (!res.ok) { toast(res.error, "error"); return; }
  (res.errors || []).forEach((err) => toast(err, "error"));
  const savedMB = (res.before - res.after) / 1048576;
  if (savedMB > 0.005) {
    toast(`Saved ${savedMB.toFixed(2)} MB (a copy of the originals is kept in trash)`, "success");
    celebrate();
  } else {
    toast("Already optimal \u2014 nothing to shrink", "success");
  }
  refreshLibrary();
});

/* ----------------------------------------------------------- page editor */

let editDirty = false;

$("btn-edit").addEventListener("click", async () => {
  const filename = selectedOne();
  if (!filename) return;
  const snap = await window.pywebview.api.begin_edit(filename);
  if (!snap.ok) { toast(snap.error, "error"); return; }
  const entry = library.find((x) => x.filename === filename);
  editFile = filename;
  editTotal = entry ? entry.pages : 1;
  editDirty = false;
  $("edit-discard").disabled = true;
  $("edit-title").textContent = `Edit Pages \u2014 ${filename}`;
  $("edit-modal").hidden = false;
  await showEditPage(1);
});

async function showEditPage(page) {
  const res = await window.pywebview.api.render_page(editFile, page);
  if (!res.ok) { toast(res.error, "error"); return; }
  editPage = res.page;
  editTotal = res.total;
  $("edit-img").src = "data:image/jpeg;base64," + res.image;
  $("edit-page-label").textContent = `${editPage} / ${editTotal}`;
  $("edit-delete-page").disabled = editTotal <= 1;
  $("edit-move-left").disabled = editPage <= 1;
  $("edit-move-right").disabled = editPage >= editTotal;
}

$("edit-prev").addEventListener("click", () => { if (editPage > 1) showEditPage(editPage - 1); });
$("edit-next").addEventListener("click", () => { if (editPage < editTotal) showEditPage(editPage + 1); });

async function editOp(promise, followPage) {
  const res = await promise;
  if (!res.ok) { toast(res.error, "error"); return; }
  editDirty = true;
  $("edit-discard").disabled = false;
  if (res.entry && res.entry.pages) editTotal = res.entry.pages;
  await showEditPage(Math.max(1, Math.min(followPage, editTotal)));
}

$("edit-rotate").addEventListener("click", () =>
  editOp(window.pywebview.api.rotate_page(editFile, editPage), editPage));

// Inline two-click confirm (native confirm() is unreliable in pywebview).
let deleteConfirmTimer = null;
function resetDeleteConfirm() {
  clearTimeout(deleteConfirmTimer);
  const btn = $("edit-delete-page");
  btn.classList.remove("confirming");
  btn.innerHTML = "&#10005; Delete Page";
}
$("edit-delete-page").addEventListener("click", () => {
  const btn = $("edit-delete-page");
  if (!btn.classList.contains("confirming")) {
    btn.classList.add("confirming");
    btn.textContent = "Click again to confirm";
    deleteConfirmTimer = setTimeout(resetDeleteConfirm, 3000);
    return;
  }
  resetDeleteConfirm();
  editOp(window.pywebview.api.delete_page(editFile, editPage), editPage);
});
$("edit-move-left").addEventListener("click", () =>
  editOp(window.pywebview.api.move_page(editFile, editPage, -1), editPage - 1));
$("edit-move-right").addEventListener("click", () =>
  editOp(window.pywebview.api.move_page(editFile, editPage, 1), editPage + 1));

/* --------------------------------------- reorder view (drag & drop grid) */

let dragTile = null;       // tile element being dragged
let reorderTotal = 0;      // page count reported by the backend
let reorderLoadToken = 0;  // cancels a chunk-loading loop when view closes

$("edit-reorder").addEventListener("click", openReorderView);
$("reorder-back").addEventListener("click", closeReorderView);

/* Thumbnails load in small chunks so the grid appears instantly and the
   window never blocks, even on very large PDFs. Tiles are built once and
   reordered by moving DOM nodes — no re-render, no image re-decode. */
async function openReorderView() {
  const grid = $("reorder-grid");
  grid.innerHTML = "";
  $("edit-single-view").hidden = true;
  $("edit-reorder-view").hidden = false;
  $("reorder-apply").disabled = true;
  reorderTotal = editTotal;
  const token = ++reorderLoadToken;
  let first = 1;
  while (first <= reorderTotal) {
    const res = await window.pywebview.api.get_page_thumbs(editFile, first, 12);
    if (token !== reorderLoadToken) return; // view closed mid-load
    if (!res.ok) { toast(res.error, "error"); return; }
    reorderTotal = res.total;
    res.thumbs.forEach((thumb, i) => grid.appendChild(makeReorderTile(thumb, first + i)));
    if (!res.thumbs.length) break;
    first += res.thumbs.length;
  }
}

function closeReorderView() {
  reorderLoadToken++;
  $("edit-reorder-view").hidden = true;
  $("edit-single-view").hidden = false;
  showEditPage(Math.min(editPage, editTotal));
}

function makeReorderTile(thumb, pageNum) {
  const tile = document.createElement("div");
  tile.className = "reorder-tile";
  tile.draggable = true;
  tile.dataset.page = String(pageNum);

  const img = document.createElement("img");
  img.src = "data:image/jpeg;base64," + thumb;
  img.draggable = false;
  tile.appendChild(img);

  const badge = document.createElement("span");
  badge.className = "reorder-badge";
  badge.textContent = String(pageNum);
  tile.appendChild(badge);

  tile.addEventListener("dragstart", () => {
    dragTile = tile;
    tile.classList.add("dragging");
  });
  tile.addEventListener("dragend", () => {
    dragTile = null;
    tile.classList.remove("dragging");
    $("reorder-grid").querySelectorAll(".drop-target")
      .forEach((t) => t.classList.remove("drop-target"));
  });
  tile.addEventListener("dragover", (e) => {
    e.preventDefault();
    if (dragTile && dragTile !== tile) tile.classList.add("drop-target");
  });
  tile.addEventListener("dragleave", () => tile.classList.remove("drop-target"));
  tile.addEventListener("drop", (e) => {
    e.preventDefault();
    tile.classList.remove("drop-target");
    if (!dragTile || dragTile === tile) return;
    const tiles = [...$("reorder-grid").children];
    if (tiles.indexOf(dragTile) < tiles.indexOf(tile)) tile.after(dragTile);
    else tile.before(dragTile);
    syncReorderState();
  });
  return tile;
}

function currentReorderOrder() {
  return [...$("reorder-grid").children].map((t) => Number(t.dataset.page));
}

function syncReorderState() {
  const order = currentReorderOrder();
  const unchanged = order.every((p, i) => p === i + 1);
  // Apply stays disabled until every page chunk has loaded.
  $("reorder-apply").disabled = unchanged || order.length !== reorderTotal;
}

$("reorder-apply").addEventListener("click", async () => {
  const order = currentReorderOrder();
  if (order.length !== reorderTotal || order.every((p, i) => p === i + 1)) return;
  const res = await window.pywebview.api.reorder_pages(editFile, order);
  if (!res.ok) { toast(res.error, "error"); return; }
  // Tiles are already displayed in the new order — just renumber them
  // in place instead of re-rendering every thumbnail.
  [...$("reorder-grid").children].forEach((tile, i) => {
    tile.dataset.page = String(i + 1);
    tile.querySelector(".reorder-badge").textContent = String(i + 1);
  });
  $("reorder-apply").disabled = true;
  editDirty = true;
  $("edit-discard").disabled = false;
  toast("Pages reordered", "success");
});

function closeEditModal() {
  resetDeleteConfirm();
  reorderLoadToken++; // cancel any in-flight thumbnail loading
  $("edit-modal").hidden = true;
  $("edit-reorder-view").hidden = true;
  $("edit-single-view").hidden = false;
  editFile = null;
  editDirty = false;
  refreshLibrary();
  if (previewFile) showPreview(previewFile, 1);
}

$("edit-done").addEventListener("click", () => {
  if (editFile) window.pywebview.api.commit_edit(editFile);
  closeEditModal();
});

$("edit-discard").addEventListener("click", async () => {
  if (!editFile || !editDirty) return;
  const res = await window.pywebview.api.discard_edit(editFile);
  if (!res.ok) { toast(res.error, "error"); return; }
  toast("Changes discarded \u2014 file restored", "success");
  closeEditModal();
});

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
  $("split-img").src = "data:image/jpeg;base64," + res.image;
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
  await refreshDevPanel();
}

async function refreshActivity() {
  const res = await window.pywebview.api.get_activity();
  if (!res.ok) { toast(res.error, "error"); return; }
  const s = res.stats;

  const cards = [
    ["Version", "v" + s.version],
    ["Uptime", fmtUptime(s.uptime_seconds)],
    ["Memory", s.memory_mb + " MB"],
    ["Peak memory", s.peak_memory_mb + " MB"],
    ["CPU time", s.cpu_seconds + " s"],
    ["Library", `${s.library_files} files · ${s.library_mb} MB`],
    ["Trash", `${s.trash_files} files · ${s.trash_mb} MB`],
    ["Thumbnail cache", `${s.thumb_files} files · ${s.thumbs_mb} MB`],
    ["Render cache", s.render_cache_mb + " MB"],
    ["Total footprint", s.footprint_mb + " MB"],
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

// Two-click confirm wrapper (same pattern as Edit Pages delete).
function armConfirm(btn, label, action) {
  let timer = null;
  btn.addEventListener("click", async () => {
    if (!btn.classList.contains("confirming")) {
      btn.classList.add("confirming");
      btn.textContent = "Click again to confirm";
      timer = setTimeout(() => {
        btn.classList.remove("confirming");
        btn.textContent = label;
      }, 3000);
      return;
    }
    clearTimeout(timer);
    btn.classList.remove("confirming");
    btn.textContent = label;
    await action();
  });
}

async function doClearLog(afterRefresh) {
  const res = await window.pywebview.api.clear_log();
  if (!res.ok) { toast(res.error, "error"); return; }
  toast(`Log cleared \u2014 ${res.freed_kb} KB freed`, "success");
  await afterRefresh();
}

armConfirm($("activity-clear"), "Clear Log", () => doClearLog(refreshActivity));
armConfirm($("log-clear"), "Clear Log", () => doClearLog(refreshFullLog));

/* ------------------------------------------------- full-window log view */

async function refreshFullLog() {
  const res = await window.pywebview.api.get_full_log();
  if (!res.ok) { toast(res.error, "error"); return; }
  $("log-meta").textContent = `${res.lines.length} entries \u00b7 ${res.size_kb} KB`;
  const body = $("log-overlay-body");
  body.innerHTML = "";
  if (!res.lines.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No activity recorded yet.";
    body.appendChild(empty);
    return;
  }
  for (const line of res.lines) {
    const row = document.createElement("div");
    row.className = "log-line";
    row.textContent = line;
    body.appendChild(row);
  }
}

$("btn-full-log").addEventListener("click", async () => {
  $("activity-modal").hidden = true;
  $("log-overlay").hidden = false;
  await refreshFullLog();
});
$("log-back").addEventListener("click", () => {
  $("log-overlay").hidden = true;
  openActivityModal();
});
$("log-refresh").addEventListener("click", refreshFullLog);
$("log-copy").addEventListener("click", async () => {
  const res = await window.pywebview.api.get_full_log();
  if (!res.ok) { toast(res.error, "error"); return; }
  try {
    await navigator.clipboard.writeText(res.lines.join("\n"));
    toast("Log copied to clipboard", "success");
  } catch (_) {
    toast("Clipboard unavailable", "error");
  }
});

/* ------------------------------------------------------------ info modal */

$("btn-info").addEventListener("click", () => { $("info-modal").hidden = false; });
$("info-close").addEventListener("click", () => { $("info-modal").hidden = true; });
for (const tab of document.querySelectorAll(".info-tab")) {
  tab.addEventListener("click", () => {
    for (const t of document.querySelectorAll(".info-tab")) t.classList.remove("active");
    tab.classList.add("active");
    for (const panel of document.querySelectorAll(".info-panel")) {
      panel.hidden = panel.id !== tab.dataset.tab;
    }
  });
}

/* ------------------------------------------- developer panel (local only) */

async function refreshDevPanel() {
  $("dev-panel").hidden = !devMode;
  if (!devMode) return;
  const res = await window.pywebview.api.dev_info();
  if (!res.ok) { $("dev-info").textContent = res.error; return; }
  $("dev-info").textContent = JSON.stringify(res.info, null, 2);
}

$("dev-copy-log").addEventListener("click", async () => {
  const res = await window.pywebview.api.get_activity();
  if (!res.ok) { toast(res.error, "error"); return; }
  const text = res.log.map((ev) => `${ev.time}  ${ev.action}  ${ev.detail}`).join("\n");
  try {
    await navigator.clipboard.writeText(text);
    toast("Log copied to clipboard", "success");
  } catch (_) {
    toast("Clipboard unavailable", "error");
  }
});

$("dev-rebuild-thumbs").addEventListener("click", async () => {
  const res = await window.pywebview.api.dev_rebuild_thumbs();
  toast(res.ok ? res.message : res.error, res.ok ? "success" : "error");
  if (res.ok) refreshLibrary();
});

$("dev-sync").addEventListener("click", async () => {
  const res = await window.pywebview.api.dev_sync_now();
  toast(res.ok ? res.message : res.error, res.ok ? "success" : "error");
  if (res.ok) { refreshLibrary(); refreshActivity(); }
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
  const state = await window.pywebview.api.get_state();
  $("storage-path").textContent = state.storage_dir || "(not set)";
  $("storage-modal").hidden = false;
});
$("storage-cancel").addEventListener("click", () => { $("storage-modal").hidden = true; });
$("storage-reveal").addEventListener("click", async () => {
  const res = await window.pywebview.api.reveal_storage();
  if (!res.ok) toast(res.error, "error");
});
$("storage-change").addEventListener("click", async () => {
  const res = await window.pywebview.api.choose_storage_dir();
  if (res.ok) {
    $("storage-modal").hidden = true;
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
  message = String(message);
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  const text = document.createElement("span");
  text.textContent = message;
  const close = document.createElement("button");
  close.className = "toast-close";
  close.title = "Dismiss";
  close.textContent = "\u00d7";
  el.append(text, close);
  $("toasts").appendChild(el);

  // Duration scales with length: ~1s for short messages, up to 4s.
  let duration = Math.min(4000, 1000 + message.length * 35);
  if (kind === "error") duration = Math.max(duration, 2500);

  let timer = null;
  const dismiss = () => {
    clearTimeout(timer);
    el.style.transition = "opacity 0.4s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 400);
  };
  const arm = (ms) => { timer = setTimeout(dismiss, ms); };
  close.addEventListener("click", dismiss);
  el.addEventListener("mouseenter", () => clearTimeout(timer));
  el.addEventListener("mouseleave", () => arm(1500));
  arm(duration);
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
