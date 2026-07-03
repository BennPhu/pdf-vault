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
