# Security Policy

## Security posture

- **Local-only by design.** PDF Vault stores everything on your machine.
  The only network activity is the update check: an HTTPS request to the
  GitHub API and, if you accept an update, an HTTPS download from GitHub
  Releases. No telemetry, no analytics, no user data ever leaves your device.
- **Update integrity.** Downloads are verified against a SHA-256 checksum
  published in the release notes before installation; mismatches are rejected.
- **Untrusted input handling.** Added PDFs are validated: symlinks rejected,
  filenames sanitized, file-size (500 MB) and page-count (10,000) limits
  enforced, encrypted PDFs refused, and parser errors contained.
- **Crash-safe state.** The library index and config are written atomically
  so they cannot be corrupted by a crash mid-write.
- **Dependencies** are pinned to exact versions and audited in CI with
  `pip-audit` on every push.

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Open a private security advisory on GitHub
(https://github.com/BennPhu/pdf-vault/security/advisories) or open an issue
if the problem is not sensitive. Please include steps to reproduce.
