# Releasing a New Version

How to ship an update to users (the auto-updater picks it up automatically).

## Steps

1. **Bump the version** in `pdf_core.py`:
   ```python
   __version__ = "1.1.0"
   ```
   Use [SemVer](https://semver.org): MAJOR.MINOR.PATCH
   (breaking change / new feature / bug fix).

2. **Update `CHANGELOG.md`** with a new section for the version.

3. **Commit, tag, and push:**
   ```bash
   git add -A
   git commit -m "Release v1.1.0"
   git tag v1.1.0
   git push && git push --tags
   ```

4. **GitHub Actions does the rest** (`.github/workflows/release.yml`):
   runs the tests, builds `PDF Vault.app`, computes the SHA-256 checksum,
   and publishes a GitHub Release with the zip attached.

5. **Users get it automatically** — the app checks for updates on launch,
   verifies the checksum, and installs.

## Pre-open-source checklist (one-time, before making the repo public)

1. **Scan for secrets/personal info:** `brew install gitleaks && gitleaks detect`.
   Commit history contains local folder paths (e.g. `/Users/<name>/...`) in
   messages/diffs — if that matters to you, squash to a fresh initial commit:
   ```bash
   git checkout --orphan public && git add -A && git commit -m "PDF Vault v1.4.0"
   git branch -M public main && git push -f origin main
   ```
2. **Verify ignores:** `data/`, `dist/`, `build/`, `.venv/` must stay untracked.
3. **Confirm LICENSE** (MIT) and that `SECURITY.md` reflects the current design.

## Your free "admin dashboard" (GitHub stats)

No telemetry needed — GitHub already tracks everything relevant:

- **Downloads per release:** each release page shows asset download counts, or
  query `https://api.github.com/repos/BennPhu/pdf-vault/releases` (see
  `assets[].download_count`).
- **Traffic** (unique visitors, clones, referrers): repo → **Insights → Traffic**.
- **Stars/watchers/issues:** the repo home page; enable notification emails for
  new issues to hear about bugs.

## Homebrew cask (optional distribution channel)

`Casks/pdf-vault.rb` is a template. One-time setup: create a public repo named
`homebrew-tap`, copy the cask file into `Casks/` there. Each release, update
its `version` and `sha256`. Users install with:

```bash
brew tap BennPhu/tap && brew install --cask pdf-vault
```

## Manual build (optional)

```bash
./build.sh                       # unsigned build
CODESIGN_ID="Developer ID Application: Your Name (TEAMID)" ./build.sh   # signed
```

The script prints the `SHA256:` line — if you create a release by hand,
paste that line into the release notes so the auto-updater can verify it.

## Signing & notarization (when you have an Apple Developer account)

1. Create a "Developer ID Application" certificate in Xcode/developer portal.
2. Build with `CODESIGN_ID` set (see above).
3. Notarize: `xcrun notarytool submit dist/PDF-Vault-*-macos.zip --keychain-profile <profile> --wait`
4. Staple: `xcrun stapler staple "dist/PDF Vault.app"` and re-zip.

Until then, users must right-click → Open the app on first launch.
