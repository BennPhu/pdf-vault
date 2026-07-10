# Changelog

All notable changes to PDF Vault are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com); versions follow [SemVer](https://semver.org).

## [1.6.1] - 2026-07-10

### Fixed
- Reorder view lag: opening it rendered every page thumbnail in a single
  blocking call, every drag rebuilt the whole grid (re-decoding all images),
  and Apply re-rendered everything from scratch. Thumbnails now load in
  chunks of 12 (the grid appears instantly and fills in progressively),
  dragging moves DOM tiles without any re-render, and Apply just renumbers
  the tiles in place. Loading is cancelled if the view closes mid-fetch.

## [1.6.0] - 2026-07-10 — The Finished Release

### Added
- Import progress bar: files are added one at a time with a live
  "Adding 12 / 78 — name.pdf" overlay — the window never freezes on big
  drops; errors are collected and summarized at the end
- Drag-and-drop page reordering: new ⇅ Reorder view in Edit Pages shows
  every page as a draggable tile; Apply Order rewrites the file in a single
  disk write (previously: one write per single-step move); fully compatible
  with Discard Changes
- README: tech-stack table, badges, and the mission up top

### Changed
- Lazy thumbnails: the library list no longer ships every thumbnail in one
  payload — each card fetches its thumbnail only when it scrolls into view,
  so large libraries open instantly
- README no longer references internal coding guidelines

## [1.5.5] - 2026-07-10

### Fixed
- Critical: the packaged app's "Use default folder" stored your PDFs INSIDE
  the .app bundle, where every update would silently destroy them. The
  default is now ~/Documents/PDF Vault, and on launch the app automatically
  rescues any files from a bundle-internal storage folder and repoints the
  config (the migration is logged to Activity).

## [1.5.4] - 2026-07-10 — Storage Modal, Mission, Clear Log

### Fixed
- Storage picker "forgot" the chosen folder: the path was always saved, but
  the picker opened at the home folder and the UI never showed the current
  location. Storage now opens a modal showing the current path, with
  Change Folder… (picker starts there), Reveal in Finder, and Cancel.

### Added
- Clear Log (Activity modal + full log view, two-click confirm): deletes
  activity.log and its rotated backup, empties the in-memory list, and
  reports the KB freed
- Memory-baseline note in About → Mission and SECURITY.md ("Resource
  footprint"): ~200 MB idle is engine cost, files are never held in memory

### Changed
- Mission rewritten: PDF Vault is not about merging (macOS does that) — it
  is about controlling and editing PDFs entirely on your machine, sitting
  between the native tools and the cloud-based ones, and being open source
  so anyone can verify it
- Topbar reordered: About · Check for Updates · Storage · Activity

## [1.5.3] - 2026-07-09 — Memory, About, File Info

### Fixed
- High memory usage (~500 MB after large imports): MuPDF's internal render
  cache grows up to ~256 MB and never trims itself — it is now emptied after
  every heavy operation (imports, previews, thumbnails, merge/split,
  compress, master). Pages are simply re-decoded from disk when needed.
  A new "Render cache" stat in Activity lets you verify it stays near zero.

### Added
- File info next to Preview: hover the ⓘ for quick facts (name, pages,
  size, added); click it to slide out a full details panel (dates, page
  dimensions, PDF metadata, encryption status)

### Changed
- "Info" button renamed to "About"; modal titled "About PDF Vault"
- File sizes shown in KB when under 1 MB

## [1.5.2] - 2026-07-09

### Added
- Edit Pages: "Discard Changes" button — undoes every rotate/move/delete
  made in the session and restores the file exactly as it was when the
  editor opened (snapshot taken on open; stale snapshots cleaned at launch)

## [1.5.1] - 2026-07-09 — UI/UX Polish

### Added
- Full-window Activity Log view ("Open Full Log"): reads the persisted
  activity.log history, monospace, with Back / Refresh / Copy Log
- Info section (topbar): How to Use guide, project Mission, and MIT
  License terms in a tabbed modal
- Toast notifications now have a close (×) button and pause on hover

### Changed
- Toast duration scales with message length (~1s short, up to 4s long;
  errors always ≥ 2.5s)
- Activity stats are now program-only: removed whole-computer "Disk free";
  added Thumbnail cache and Total footprint (library + trash + thumbs + log)

### Fixed
- Edit Pages modal no longer overflows off-screen: preview box sized like
  the main Preview pane, nav + edit actions grouped in one boxed toolbar,
  Done always visible (all modals now cap at 92% of window height)
- Edit Pages "Delete Page" used a native confirm() dialog that is
  unreliable under pywebview — replaced with an inline two-click confirm

## [1.5.0] - 2026-07-09 — Features, Power of 10, Shippability

### Added
- Live library search (top of the library pane; Esc clears)
- Rename PDFs (double-click a file's name)
- Page editor: rotate, delete, and reorder pages inside any PDF
- Compress PDFs in place (originals kept in trash for undo)
- Images → PDF: drop PNG/JPEG/WebP files to convert them into the library
- Local-only developer panel (launch with PDFVAULT_DEV=1): diagnostics,
  log copy, thumbnail rebuild, manual index sync — no telemetry, ever

### Code quality (NASA/JPL "Power of 10", adapted for Python)
- No function exceeds 60 lines; no recursion; all loops provably bounded;
  no dynamic code execution — enforced permanently by tests/test_power_of_10.py
- ruff linting with a zero-warning policy, wired into CI
- Batch add capped at 100 files per drop

### Shipping & repo hygiene
- README rewritten for end users (install, verify, build-from-source)
- Friendlier release notes template with step-by-step install
- Homebrew cask template (Casks/pdf-vault.rb) + tap instructions
- GitHub-stats guide in RELEASING.md (downloads/traffic/stars — no telemetry)
- Removed dead files: PDF Vault.command, PROGRESS.md, 2 unused images

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
