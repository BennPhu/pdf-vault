# Changelog

All notable changes to PDF Vault are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com); versions follow [SemVer](https://semver.org).

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
