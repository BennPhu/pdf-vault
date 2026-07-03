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
import urllib.request
import zipfile
from pathlib import Path

from pdf_core import GITHUB_REPO, __version__

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
REQUEST_TIMEOUT = 10


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
    request = urllib.request.Request(
        API_URL, headers={"Accept": "application/vnd.github+json",
                          "User-Agent": f"pdf-vault/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as resp:
            release = json.load(resp)
    except Exception as e:
        raise UpdateError(f"Update check failed: {e}")

    latest = _parse_version(release.get("tag_name", ""))
    current = _parse_version(__version__)
    if latest is None or current is None or latest <= current:
        return None

    zip_url = None
    for asset in release.get("assets", []):
        if asset.get("name", "").endswith(".zip"):
            zip_url = asset.get("browser_download_url")
            break
    if not zip_url:
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


def _running_app_bundle():
    """Path to the .app bundle we are running from, or None if run from source."""
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def download_and_install(update, progress_cb=None):
    """Download the release zip, verify checksum, and install.

    When running as a packaged .app, replaces the bundle and returns the
    path to relaunch. When running from source, downloads to ~/Downloads
    and returns that path for the user to install manually.
    """
    def report(msg):
        if progress_cb:
            progress_cb(msg)

    report("Downloading update\u2026")
    tmp_dir = Path(tempfile.mkdtemp(prefix="pdf-vault-update-"))
    zip_path = tmp_dir / "update.zip"
    try:
        request = urllib.request.Request(
            update["zip_url"], headers={"User-Agent": f"pdf-vault/{__version__}"})
        with urllib.request.urlopen(request, timeout=60) as resp, open(zip_path, "wb") as f:
            shutil.copyfileobj(resp, f)
    except Exception as e:
        raise UpdateError(f"Download failed: {e}")

    if update.get("sha256"):
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
    extract_dir = tmp_dir / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
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
        raise UpdateError(f"Install failed, rolled back: {e}")
    shutil.rmtree(backup, ignore_errors=True)
    return app_bundle


def relaunch(app_bundle):
    """Open the freshly installed app and exit this process."""
    subprocess.Popen(["open", str(app_bundle)])
    sys.exit(0)
