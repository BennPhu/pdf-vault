import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

import updater
from updater import UpdateError


def test_parse_version():
    assert updater._parse_version("v1.2.3") == (1, 2, 3)
    assert updater._parse_version("1.2.3") == (1, 2, 3)
    assert updater._parse_version("nonsense") is None
    assert updater._parse_version("v1.2") is None


def _fake_release(tag, body="", assets=None):
    return {
        "tag_name": tag,
        "body": body,
        "assets": assets if assets is not None else [
            {"name": "PDF-Vault.zip", "browser_download_url": "https://github.com/BennPhu/pdf-vault/releases/download/v99.0.0/x.zip"}
        ],
    }


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_check_for_update_newer(monkeypatch):
    release = _fake_release("v99.0.0", body="notes\nSHA256: " + "a" * 64)
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(json.dumps(release).encode()))
    update = updater.check_for_update()
    assert update["version"] == "99.0.0"
    assert update["sha256"] == "a" * 64
    assert update["zip_url"] == "https://github.com/BennPhu/pdf-vault/releases/download/v99.0.0/x.zip"


def test_check_for_update_same_version(monkeypatch):
    release = _fake_release(f"v{updater.__version__}")
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(json.dumps(release).encode()))
    assert updater.check_for_update() is None


def test_check_for_update_no_zip_asset(monkeypatch):
    release = _fake_release("v99.0.0", assets=[])
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(json.dumps(release).encode()))
    assert updater.check_for_update() is None


def test_check_for_update_offline(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    with pytest.raises(UpdateError):
        updater.check_for_update()


def test_download_rejects_bad_checksum(monkeypatch, tmp_path):
    payload = b"fake zip bytes"
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(payload))
    update = {
        "version": "99.0.0",
        "zip_url": "https://github.com/BennPhu/pdf-vault/releases/download/v99.0.0/x.zip",
        "sha256": "0" * 64,  # wrong on purpose
    }
    with pytest.raises(UpdateError, match="Checksum"):
        updater.download_and_install(update)


def test_check_for_update_rejects_untrusted_host(monkeypatch):
    release = _fake_release("v99.0.0", body="SHA256: " + "a" * 64, assets=[
        {"name": "evil.zip", "browser_download_url": "https://evil.example.com/x.zip"}])
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(json.dumps(release).encode()))
    assert updater.check_for_update() is None


def test_download_requires_checksum():
    update = {"version": "99.0.0",
              "zip_url": "https://github.com/x/y/releases/download/v99.0.0/x.zip",
              "sha256": None}
    with pytest.raises(UpdateError, match="SHA256"):
        updater.download_and_install(update)


def test_download_rejects_http_url():
    update = {"version": "99.0.0",
              "zip_url": "http://github.com/x.zip",  # not https
              "sha256": "a" * 64}
    with pytest.raises(UpdateError, match="trusted"):
        updater.download_and_install(update)


def test_download_rejects_oversized(monkeypatch):
    monkeypatch.setattr(updater, "MAX_DOWNLOAD_BYTES", 10)
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(b"x" * 100))
    update = {"version": "99.0.0",
              "zip_url": "https://github.com/x/y/releases/download/v99.0.0/x.zip",
              "sha256": "a" * 64}
    with pytest.raises(UpdateError, match="size limit"):
        updater.download_and_install(update)


def test_zip_safety_rejects_traversal(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../outside.txt", "x")
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf, \
            pytest.raises(UpdateError, match="Unsafe path"):
        updater._check_zip_safety(zf)


def test_zip_safety_rejects_bomb(monkeypatch):
    monkeypatch.setattr(updater, "MAX_UNCOMPRESSED_BYTES", 10)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("big.bin", "x" * 100)
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf, \
            pytest.raises(UpdateError, match="large"):
        updater._check_zip_safety(zf)


def test_download_from_source_saves_to_downloads(monkeypatch, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("PDF Vault.app/Contents/dummy", "x")
    payload = buf.getvalue()
    digest = hashlib.sha256(payload).hexdigest()

    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: FakeResponse(payload))
    monkeypatch.setattr(updater, "_running_app_bundle", lambda: None)
    monkeypatch.setattr(updater.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Downloads").mkdir()

    update = {"version": "99.0.0", "sha256": digest,
              "zip_url": "https://github.com/BennPhu/pdf-vault/releases/download/v99.0.0/x.zip"}
    result = updater.download_and_install(update)
    assert Path(result).exists()
    assert result.name == "PDF-Vault-99.0.0.zip"
