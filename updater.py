"""Auto-update support: checks GitHub Releases and installs new versions.

This is the only code in PDF Vault that touches the network. It talks
exclusively to the GitHub API/downloads over HTTPS and sends no user data.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from pdf_core import GITHUB_REPO, __version__

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
REQUEST_TIMEOUT = 10
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024   # refuse absurdly large "updates"
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # zip-bomb guard
ALLOWED_DOWNLOAD_HOSTS = {"github.com", "objects.githubusercontent.com",
                          "release-assets.githubusercontent.com"}


class UpdateError(Exception):
    """Raised when an update check or install fails."""


def _parse_version(tag):
    """'v1.2.3' -> (1, 2, 3). Returns None if unparseable."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def check_for_update():
    """Query GitHub for the latest release.

    Returns a dict with 'version', 'zip_url', 'sha256' (may be None), and
    'notes' if a newer version exists, else None. Raises UpdateError on
    network failure so callers can stay silent when offline.
    """
    request = urllib.request.Request(  # noqa: S310 (constant https URL)
        API_URL, headers={"Accept": "application/vnd.github+json",
                          "User-Agent": f"pdf-vault/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as resp:  # noqa: S310
            release = json.load(resp)
    except Exception as e:
        raise UpdateError(f"Update check failed: {e}") from e

    latest = _parse_version(release.get("tag_name", ""))
    current = _parse_version(__version__)
    if latest is None or current is None or latest <= current:
        return None

    zip_url = None
    for asset in release.get("assets", []):
        if asset.get("name", "").endswith(".zip"):
            zip_url = asset.get("browser_download_url")
            break
    if not zip_url or not _url_allowed(zip_url):
        return None

    # Checksum published in the release notes as: SHA256: <hex>
    sha256 = None
    match = re.search(r"SHA256:\s*([0-9a-fA-F]{64})", release.get("body") or "")
    if match:
        sha256 = match.group(1).lower()

    return {
        "version": release["tag_name"].lstrip("v"),
        "zip_url": zip_url,
        "sha256": sha256,
        "notes": (release.get("body") or "").strip(),
    }


def _url_allowed(url):
    """Only HTTPS downloads from GitHub-owned hosts are acceptable."""
    try:
        parts = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parts.scheme == "https" and parts.hostname in ALLOWED_DOWNLOAD_HOSTS


def _check_zip_safety(zf):
    """Reject archives with traversal members or excessive uncompressed size."""
    total = 0
    for info in zf.infolist():
        name = info.filename
        if name.startswith("/") or ".." in Path(name).parts:
            raise UpdateError(f"Unsafe path in update archive: {name}")
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise UpdateError("Update archive is unreasonably large — rejected.")


def _running_app_bundle():
    """Path to the .app bundle we are running from, or None if run from source."""
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def _download_zip(update, dest_path):
    """Stream the release zip to dest_path with a hard size bound."""
    chunk_size = 1024 * 1024
    max_chunks = MAX_DOWNLOAD_BYTES // chunk_size + 1  # provable loop bound
    try:
        # zip_url passed _url_allowed(): https + GitHub hosts only
        request = urllib.request.Request(  # noqa: S310
            update["zip_url"], headers={"User-Agent": f"pdf-vault/{__version__}"})
        with urllib.request.urlopen(request, timeout=60) as resp, \
                open(dest_path, "wb") as f:  # noqa: S310
            for _ in range(max_chunks + 1):
                chunk = resp.read(chunk_size)
                if not chunk:
                    return
                if f.tell() + len(chunk) > MAX_DOWNLOAD_BYTES:
                    raise UpdateError("Update download exceeds size limit — rejected.")
                f.write(chunk)
        raise UpdateError("Update download exceeds size limit — rejected.")
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError(f"Download failed: {e}") from e


def _install_zip(zip_path, tmp_dir, app_bundle):
    """Extract the verified zip and swap the running .app bundle."""
    extract_dir = tmp_dir / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        _check_zip_safety(zf)
        zf.extractall(extract_dir)
    new_apps = list(extract_dir.glob("*.app"))
    if not new_apps:
        raise UpdateError("Release zip does not contain an .app bundle.")
    new_app = new_apps[0]

    backup = app_bundle.with_suffix(".app.old")
    if backup.exists():
        shutil.rmtree(backup)
    app_bundle.rename(backup)
    try:
        shutil.move(str(new_app), str(app_bundle))
    except Exception as e:
        backup.rename(app_bundle)  # roll back
        raise UpdateError(f"Install failed, rolled back: {e}") from e
    shutil.rmtree(backup, ignore_errors=True)
    return app_bundle


def download_and_install(update, progress_cb=None):
    """Download the release zip, verify checksum, and install.

    When running as a packaged .app, replaces the bundle and returns the
    path to relaunch. When running from source, downloads to ~/Downloads
    and returns that path for the user to install manually.
    """
    def report(msg):
        if progress_cb:
            progress_cb(msg)

    if not update.get("sha256"):
        raise UpdateError(
            "Release has no SHA256 checksum in its notes — update rejected for safety.")
    if not _url_allowed(update["zip_url"]):
        raise UpdateError("Update download URL is not a trusted GitHub host — rejected.")

    report("Downloading update\u2026")
    tmp_dir = Path(tempfile.mkdtemp(prefix="pdf-vault-update-"))
    zip_path = tmp_dir / "update.zip"
    _download_zip(update, zip_path)

    report("Verifying checksum\u2026")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if digest != update["sha256"]:
        raise UpdateError("Checksum verification FAILED \u2014 update rejected for safety.")

    app_bundle = _running_app_bundle()
    if app_bundle is None:
        dest = Path.home() / "Downloads" / f"PDF-Vault-{update['version']}.zip"
        shutil.move(str(zip_path), dest)
        return dest

    report("Installing\u2026")
    return _install_zip(zip_path, tmp_dir, app_bundle)


def relaunch(app_bundle):
    """Open the freshly installed app and exit this process."""
    subprocess.Popen(["/usr/bin/open", str(app_bundle)])
    sys.exit(0)
