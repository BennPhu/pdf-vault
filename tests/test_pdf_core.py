import json

import pytest
from pypdf import PdfReader, PdfWriter

import pdf_core
from pdf_core import PDFError


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Isolated config + storage in a temp dir."""
    monkeypatch.setattr(pdf_core, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(pdf_core, "_config", None)
    storage = tmp_path / "vault"
    pdf_core.set_storage_dir(storage)
    return tmp_path


def make_pdf(directory, name, pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    path = directory / name
    with open(path, "wb") as f:
        writer.write(f)
    return path


# ------------------------------------------------------------------- config

def test_set_storage_dir_creates_structure(vault):
    assert pdf_core.is_configured()
    assert pdf_core.library_dir().is_dir()


def test_config_rejects_invalid_values(vault, monkeypatch):
    pdf_core.CONFIG_FILE.write_text(json.dumps(
        {"storage_dir": "../relative/escape", "last_output_dir": 42, "junk": "x"}))
    monkeypatch.setattr(pdf_core, "_config", None)
    cfg = pdf_core.load_config()
    assert "storage_dir" not in cfg
    assert "last_output_dir" not in cfg
    assert "junk" not in cfg


def test_config_survives_corrupt_json(vault, monkeypatch):
    pdf_core.CONFIG_FILE.write_text("{not json")
    monkeypatch.setattr(pdf_core, "_config", None)
    assert pdf_core.load_config() == {}


def test_last_output_dir_fallback(vault):
    assert pdf_core.last_output_dir()  # falls back to home
    out = vault / "outputs"
    out.mkdir()
    pdf_core.set_last_output_dir(out)
    assert pdf_core.last_output_dir() == str(out)


# ---------------------------------------------------------------- add_pdf

def test_add_pdf(vault):
    src = make_pdf(vault, "doc.pdf", 3)
    entry = pdf_core.add_pdf(src)
    assert entry["pages"] == 3
    assert pdf_core.library_path("doc.pdf").exists()
    assert len(pdf_core.load_index()) == 1


def test_add_pdf_no_master_created(vault):
    pdf_core.add_pdf(make_pdf(vault, "doc.pdf"))
    root_pdfs = list(pdf_core.storage_dir().glob("*.pdf"))
    assert root_pdfs == []


def test_add_pdf_duplicate_names(vault):
    src = make_pdf(vault, "dup.pdf")
    pdf_core.add_pdf(src)
    entry = pdf_core.add_pdf(src)
    assert entry["filename"] == "dup_1.pdf"


def test_add_pdf_rejects_non_pdf(vault):
    bad = vault / "evil.txt"
    bad.write_text("hi")
    with pytest.raises(PDFError):
        pdf_core.add_pdf(bad)


def test_add_pdf_rejects_symlink(vault):
    real = make_pdf(vault, "real.pdf")
    link = vault / "link.pdf"
    link.symlink_to(real)
    with pytest.raises(PDFError, match="Symlink"):
        pdf_core.add_pdf(link)


def test_add_pdf_rejects_oversized(vault, monkeypatch):
    monkeypatch.setattr(pdf_core, "MAX_FILE_SIZE_MB", 0)
    with pytest.raises(PDFError, match="too large"):
        pdf_core.add_pdf(make_pdf(vault, "big.pdf"))


def test_add_pdf_rejects_too_many_pages(vault, monkeypatch):
    monkeypatch.setattr(pdf_core, "MAX_PAGES", 2)
    with pytest.raises(PDFError, match="Too many pages"):
        pdf_core.add_pdf(make_pdf(vault, "long.pdf", 3))


# ------------------------------------------------------- sanitize_filename

@pytest.mark.parametrize("raw,expected_suffix", [
    ("normal.pdf", "normal.pdf"),
    ("../../etc/passwd.pdf", "passwd.pdf"),
    ("we|ird*name?.pdf", "weirdname.pdf"),
    ("", "unnamed.pdf"),
    ("noext", "noext.pdf"),
])
def test_sanitize_filename(raw, expected_suffix):
    assert pdf_core.sanitize_filename(raw) == expected_suffix


# ------------------------------------------------------------ merge/split

def test_merge(vault):
    a = make_pdf(vault, "a.pdf", 2)
    b = make_pdf(vault, "b.pdf", 3)
    out = vault / "merged.pdf"
    pdf_core.merge_pdfs([a, b], out)
    assert len(PdfReader(str(out)).pages) == 5


def test_merge_requires_two(vault):
    a = make_pdf(vault, "a.pdf")
    with pytest.raises(PDFError):
        pdf_core.merge_pdfs([a], vault / "out.pdf")


def test_extract_pages(vault):
    src = make_pdf(vault, "doc.pdf", 5)
    out = vault / "range.pdf"
    pdf_core.extract_pages(src, 2, 4, out)
    assert len(PdfReader(str(out)).pages) == 3


def test_extract_pages_invalid_range(vault):
    src = make_pdf(vault, "doc.pdf", 5)
    with pytest.raises(PDFError, match="Invalid page range"):
        pdf_core.extract_pages(src, 4, 99, vault / "bad.pdf")


def test_split_pdf_per_page(vault):
    src = make_pdf(vault, "doc.pdf", 4)
    files = pdf_core.split_pdf(src, vault / "pages", 2, 3)
    assert len(files) == 2
    assert all(len(PdfReader(str(f)).pages) == 1 for f in files)


# ---------------------------------------------------------------- master

def test_build_master(vault):
    pdf_core.add_pdf(make_pdf(vault, "a.pdf", 2))
    pdf_core.add_pdf(make_pdf(vault, "b.pdf", 3))
    out = vault / "master.pdf"
    pdf_core.build_master(out)
    assert len(PdfReader(str(out)).pages) == 5


def test_build_master_empty_library(vault):
    with pytest.raises(PDFError, match="empty"):
        pdf_core.build_master(vault / "master.pdf")


# ---------------------------------------------------------------- index

def test_index_atomic_write(vault):
    pdf_core.save_index([{"filename": "x.pdf"}])
    assert not pdf_core.index_file_path().with_suffix(".json.tmp").exists()
    assert pdf_core.load_index() == [{"filename": "x.pdf"}]


# ------------------------------------------------------------- security

@pytest.mark.parametrize("bad", [
    "../escape.pdf",
    "../../etc/passwd",
    "/etc/passwd",
    "sub/dir.pdf",
    "..",
    "",
])
def test_library_path_rejects_traversal(vault, bad):
    with pytest.raises(PDFError, match="Invalid filename"):
        pdf_core.library_path(bad)


def test_library_path_accepts_normal_names(vault):
    path = pdf_core.library_path("My Notes (v2) + more.pdf")
    assert path.parent == pdf_core.library_dir()


def test_restore_rejects_traversal_entry(vault):
    with pytest.raises(PDFError, match="Invalid filename"):
        pdf_core.restore_pdf({"filename": "../evil.pdf"})


# ------------------------------------------------------------ thumbnails

def test_thumbnail_cached_on_disk(vault):
    entry = pdf_core.add_pdf(make_pdf(vault, "doc.pdf", 1))
    thumb = pdf_core.get_thumbnail_b64(entry["filename"])
    assert thumb
    cached = list(pdf_core.thumbs_dir().glob("doc.pdf.*.jpg"))
    assert len(cached) == 1
    # Second call must serve the exact cached bytes
    assert pdf_core.get_thumbnail_b64(entry["filename"]) == thumb


def test_thumbnail_pruned_when_file_removed(vault):
    entry = pdf_core.add_pdf(make_pdf(vault, "doc.pdf", 1))
    pdf_core.get_thumbnail_b64(entry["filename"])
    pdf_core.library_path(entry["filename"]).unlink()
    pdf_core.sync_index()
    assert list(pdf_core.thumbs_dir().glob("*.jpg")) == []


def test_thumbnail_missing_file_returns_none(vault):
    assert pdf_core.get_thumbnail_b64("nope.pdf") is None


# ----------------------------------------------------------- housekeeping

def test_purge_trash_removes_old_files(vault):
    import os
    import time
    pdf_core.trash_dir().mkdir(parents=True, exist_ok=True)
    old = pdf_core.trash_dir() / "old.pdf"
    old.write_bytes(b"x")
    ancient = time.time() - 40 * 86400
    os.utime(old, (ancient, ancient))
    fresh = pdf_core.trash_dir() / "fresh.pdf"
    fresh.write_bytes(b"x")
    assert pdf_core.purge_trash(max_age_days=30) == 1
    assert not old.exists()
    assert fresh.exists()


def test_log_rotation(vault):
    log = pdf_core.log_file_path()
    log.write_text("x" * (pdf_core.LOG_MAX_BYTES + 1))
    pdf_core.log_event("test", "rotation trigger")
    assert log.with_suffix(".log.1").exists()
    assert log.stat().st_size < pdf_core.LOG_MAX_BYTES


def test_sync_index_survives_unreadable_folder(vault, monkeypatch):
    pdf_core.save_index([{"filename": "keep.pdf"}])

    def deny(_):
        raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(pdf_core.os, "listdir", deny)
    assert pdf_core.sync_index() == [{"filename": "keep.pdf"}]
