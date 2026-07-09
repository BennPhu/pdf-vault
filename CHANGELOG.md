# Changelog

All notable changes to PDF Vault are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com); versions follow [SemVer](https://semver.org).

## [1.4.2] - 2026-07-09

### Fixed
- UI was unresponsive: the Content-Security-Policy added in 1.4.0 blocked
  pywebview's injected JS bridge; CSP now permits the inline bridge while
  still blocking all remote script/style/network loading

## [1.4.1] - 2026-07-09

### Fixed
- Crash at launch when macOS blocks access to the storage folder before the
  permission prompt (trash purge now tolerates unreadable folders)

## [1.4.0] - 2026-07-09 — Security and Memory Optimization

### Security
- Path-traversal protection: filenames from the UI can no longer reference
  anything outside the library folder
- Auto-updater hardened: SHA-256 checksum now mandatory, downloads restricted
  to HTTPS GitHub hosts and size-capped, archives checked for unsafe paths
  and zip-bomb size before extraction
- Strict Content-Security-Policy on the UI
- CI: least-privilege workflow permissions, actions pinned to commit SHAs,
  Dependabot enabled; removed legacy app_tk.py
- SECURITY.md expanded with the full threat model

### Performance
- Thumbnails are rendered once and cached on disk (.thumbs/) as small JPEGs
  instead of being re-rendered as PNGs on every refresh
- Page previews now use JPEG (~5-10x smaller payloads and WebView memory)
- Activity page shows real current memory usage (previous number was the
  all-time peak, which never goes down)

### Storage
- Trash auto-purges files older than 30 days
- activity.log rotates at 512KB
- Thumbnail cache cleans itself when files leave the library

## [1.3.1] - 2026-07-09

### Fixed
- macOS permission denial (TCC) on Documents/Desktop folders no longer makes
  the library look empty or wipes the index: sync now detects unreadable
  folders and leaves the index untouched
- App warns at startup when macOS is blocking access to the storage folder
- Info.plist now includes folder usage descriptions so macOS shows a proper
  permission prompt

## [1.3.0] - 2026-07-09

### Added
- Activity & Stats page (📊 Activity button in the top bar): live program
  stats (memory, CPU time, uptime, disk usage, library/trash size) and a
  running log of every action touching the storage folder (add, delete,
  restore, merge, split, master, index sync)
- Activity log also persisted to `activity.log` in the storage folder

## [1.2.2] - 2026-07-09

### Fixed
- Library index now self-heals: the library folder is the source of truth,
  so PDFs added or removed outside the app (Finder, drop races) always show
  up correctly in the UI

## [1.2.1] - 2026-07-09

### Fixed
- Library grid now refreshes reliably after a drag-and-drop (added a JS
  fallback refresh in case the native drop callback is missed)

## [1.2.0] - 2026-07-09

### Added
- Delete button: remove selected PDFs from the library (moved to a trash
  folder, not permanently destroyed)
- Undo / Redo buttons to reverse deletions back and forth

### Fixed
- Drag-and-drop now works on macOS: drops are handled natively on the Python
  side, since WKWebView never exposes real file paths to JavaScript

## [1.1.0] - 2026-07-03

Complete UI redesign: playful, modern web interface.

### Added
- New web-based UI (pywebview): white + terracotta design, rounded corners,
  soft shadows, Nunito typography
- Library shown as a thumbnail card grid (real page-1 previews)
- Toast notifications replace popup dialogs; confetti on merge/split success
- Mascot empty state and animated drop zone
- In-app modals for first-run setup and both split flows (with live page preview)

### Changed
- Drag-and-drop now uses native HTML5 events (tkinterdnd2 workaround no longer needed)
- Legacy tkinter UI preserved as `app_tk.py` for one release

### Removed
- tkinterdnd2 dependency from the packaged app

## [1.0.0] - 2026-07-03

First release-ready version.

### Added
- Drag-and-drop (or file picker) PDF library with `index.json` catalog
- Visual preview panel with page navigation (PyMuPDF)
- Split Selected: extract pages x-y into one new PDF
- Individual Splits: one file per page in a chosen range
- Merge Selected: combine PDFs into one file
- Create Master PDF on demand (never automatic)
- User-chosen storage folder (first-run setup + change anytime)
- Auto-update: checks GitHub Releases on launch, verifies SHA-256, installs
- `PDF Vault.command` launcher and PyInstaller `.app` packaging (`build.sh`)
- Security hardening: filename sanitization, symlink rejection, file-size and
  page-count limits, config validation, atomic index/config writes
- Test suite (pytest) and CI/CD via GitHub Actions
