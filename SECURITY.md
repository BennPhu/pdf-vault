# Security Policy

## Security posture

- **Local-only by design.** PDF Vault stores everything on your machine.
  The only network activity is the update check: an HTTPS request to the
  GitHub API and, if you accept an update, an HTTPS download from GitHub
  Releases. No telemetry, no analytics, no user data ever leaves your device.
- **Update integrity.** Updates install only if the release notes publish a
  SHA-256 checksum that matches the download; downloads are restricted to
  HTTPS GitHub hosts, size-capped, and the archive is checked for path
  traversal and zip-bomb characteristics before extraction.
  Threat model note: the checksum lives next to the download, so it protects
  against corrupted/tampered transfers, not a fully compromised GitHub
  account. Release signing may be added if the project grows.
- **Untrusted input handling.** Added PDFs are validated: symlinks rejected,
  filenames sanitized, file-size (500 MB) and page-count (10,000) limits
  enforced, encrypted PDFs refused, and parser errors contained.
- **UI bridge hardening.** All filenames crossing the JS↔Python bridge are
  rejected if they contain path separators or traversal components, so the
  web layer can only ever touch files inside the library folder. The UI
  enforces a strict Content-Security-Policy.
- **macOS folder permissions.** Storage folders under Documents/Desktop are
  subject to macOS privacy consent (TCC); the app detects denial, warns the
  user, and never destroys index state based on an unreadable folder.
- **Crash-safe state.** The library index and config are written atomically
  so they cannot be corrupted by a crash mid-write.
- **Dependencies** are pinned to exact versions and audited in CI with
  `pip-audit` on every push.

## Resource footprint

The app idles around ~200 MB of memory. This is the fixed cost of the
embedded WebKit rendering engine (the same one that powers Safari) plus the
Python runtime and PDF libraries — measured at ~70 MB before a window even
opens. Your PDFs are never held in memory: they live on disk and are opened,
processed, and closed per operation, and the PDF engine's internal render
cache is emptied after every heavy action (visible as the "Render cache"
stat in Activity). Note that macOS reports memory conservatively: pages
freed after a peak may remain attributed to the process until it restarts.

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Open a private security advisory on GitHub
(https://github.com/BennPhu/pdf-vault/security/advisories) or open an issue
if the problem is not sensitive. Please include steps to reproduce.
