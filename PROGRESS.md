# PDF Vault — Progress & Roadmap

**End goal:** a program that is beautiful in UI/UX *and* rock-solid in functionality for managing a daily-growing PDF collection.

_Last updated: Jul 3, 2026_

## Current status: MVP 1 final — functionality complete; next phase is UI/UX

### Done — v1 (MVP)
- [x] Drag-and-drop window to add PDFs (tkinter + tkinterdnd2)
- [x] Library folder with `index.json` catalog (filename, date, pages, size)
- [x] Growing `master.pdf` — every added PDF is appended automatically
- [x] Merge selected PDFs into a new file
- [x] Split a PDF into per-page files (full or page range)
- [x] Fixed macOS arm64 tkdnd/Tcl-9 incompatibility (swapped in Tk 8.6 binary)
- [x] GitHub repo: https://github.com/BennPhu/pdf-vault

### Done — v2
- [x] `PDF Vault.command` double-clickable launcher (auto-installs deps)
- [x] First-run setup: user chooses the storage folder (`~/.pdf_vault_config.json`)
- [x] "Change Storage Folder…" button
- [x] Visual preview panel (PyMuPDF rendering, ◀/▶ page navigation)
- [x] Split dialog with live page preview + from/to spinboxes
- [x] Merge/split output saved wherever the user chooses; last folder remembered
- [x] Unselect button + Escape key

### Done — MVP 1 final
- [x] Two dedicated split buttons, each with its own preview dialog:
      *Split Selected* (pages x-y → one new PDF, user picks save location) and
      *Individual Splits* (each page in range → its own one-page file)
- [x] Master PDF is no longer created automatically — *Create Master PDF…* builds it
      on demand at a user-chosen location (no junk files in the storage folder)

### Done — Deployment readiness (v1.0.0)
- [x] Security hardening: filename sanitization, symlink rejection, size/page limits,
      config validation, atomic config/index writes
- [x] Versioning (`__version__` = 1.0.0), MIT LICENSE, pinned dependencies
- [x] pytest suite (31 tests) in `tests/`
- [x] PyInstaller packaging (`build.sh` → `PDF Vault.app` + release zip + SHA-256)
- [x] Auto-updater (`updater.py`): checks GitHub Releases on launch, checksum-verified install
- [x] GitHub Actions: tests + pip-audit on push; tag push builds & publishes a Release
- [x] Docs: CHANGELOG.md, RELEASING.md, SECURITY.md, user install instructions

## Roadmap to the end goal

### Phase 3 — UI/UX polish (beautiful)
- [ ] Modern visual design: consistent spacing, typography, color palette, dark mode
      (evaluate `customtkinter` or migrating to a web-based UI e.g. Tauri/Electron-style)
- [ ] Thumbnail grid view of the library (not just a table)
- [ ] Drag-to-reorder pages and PDFs before merging
- [ ] Toast notifications instead of popup dialogs; smoother error handling
- [ ] App icon + proper macOS `.app` bundle (py2app), dock/menu-bar presence

### Phase 4 — Functionality depth
- [ ] Search & filter the library (by name, date, page count)
- [ ] Tags/categories for PDFs
- [ ] Delete/remove from library with master.pdf rebuild + undo
- [ ] Watch folder: auto-import any PDF dropped in a chosen folder
- [ ] Duplicate detection (same content hash)
- [ ] Page-level operations: rotate, reorder, extract selected pages from preview

### Phase 5 — Robustness
- [ ] Automated test suite (pytest) wired to CI (GitHub Actions)
- [ ] Handle very large masters efficiently (incremental append instead of full rewrite)
- [ ] Backup/export of the whole vault

## Known issues
- Rebuilding `.venv` from scratch reinstalls the incompatible tkdnd binary on macOS arm64;
  the app falls back to the file-picker automatically (see README for the manual fix).
- `master.pdf` is fully rewritten on each append — fine for now, slow for very large vaults (Phase 5).
