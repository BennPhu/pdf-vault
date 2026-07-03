# Changelog

All notable changes to PDF Vault are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com); versions follow [SemVer](https://semver.org).

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
