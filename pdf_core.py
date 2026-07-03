"""Core PDF logic for PDF Vault: add/append, merge, split, and index management."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LIBRARY_DIR = DATA_DIR / "library"
MASTER_PDF = DATA_DIR / "master.pdf"
INDEX_FILE = DATA_DIR / "index.json"


class PDFError(Exception):
    """Raised when a PDF operation fails."""


def ensure_dirs():
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


def load_index():
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_index(index):
    ensure_dirs()
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def _validate_pdf(path):
    """Return a PdfReader if the file is a readable PDF, else raise PDFError."""
    path = Path(path)
    if not path.exists():
        raise PDFError(f"File not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise PDFError(f"Not a PDF file: {path.name}")
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise PDFError(f"PDF is password-protected: {path.name}")
        _ = len(reader.pages)
        return reader
    except PDFError:
        raise
    except Exception as e:
        raise PDFError(f"Cannot read PDF '{path.name}': {e}")


def _unique_dest(directory, filename):
    """Return a destination path in directory, renaming on clashes."""
    dest = directory / filename
    stem, suffix = dest.stem, dest.suffix
    counter = 1
    while dest.exists():
        dest = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return dest


def _append_to_master(reader):
    """Append all pages of reader to master.pdf (created if missing)."""
    writer = PdfWriter()
    if MASTER_PDF.exists():
        master_reader = PdfReader(str(MASTER_PDF))
        for page in master_reader.pages:
            writer.add_page(page)
    for page in reader.pages:
        writer.add_page(page)
    tmp = MASTER_PDF.with_suffix(".pdf.tmp")
    with open(tmp, "wb") as f:
        writer.write(f)
    tmp.replace(MASTER_PDF)


def add_pdf(source_path):
    """Add a PDF: copy to library, append to master, update index.

    Returns the index entry dict.
    """
    ensure_dirs()
    source_path = Path(source_path)
    reader = _validate_pdf(source_path)

    dest = _unique_dest(LIBRARY_DIR, source_path.name)
    shutil.copy2(source_path, dest)

    try:
        _append_to_master(reader)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise PDFError(f"Failed to append to master.pdf: {e}")

    entry = {
        "filename": dest.name,
        "added": datetime.now().isoformat(timespec="seconds"),
        "pages": len(reader.pages),
        "size_bytes": dest.stat().st_size,
    }
    index = load_index()
    index.append(entry)
    save_index(index)
    return entry


def merge_pdfs(paths, output_path):
    """Merge the given PDFs (in order) into output_path."""
    if len(paths) < 2:
        raise PDFError("Select at least two PDFs to merge.")
    writer = PdfWriter()
    for p in paths:
        reader = _validate_pdf(p)
        for page in reader.pages:
            writer.add_page(page)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path


def split_pdf(source_path, output_dir, start=None, end=None):
    """Split a PDF into one file per page, written into output_dir.

    start/end are 1-based inclusive page numbers; defaults to all pages.
    Returns list of written file paths.
    """
    reader = _validate_pdf(source_path)
    total = len(reader.pages)
    start = 1 if start is None else start
    end = total if end is None else end
    if not (1 <= start <= end <= total):
        raise PDFError(f"Invalid page range {start}-{end} (document has {total} pages).")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source_path).stem
    written = []
    for i in range(start - 1, end):
        writer = PdfWriter()
        writer.add_page(reader.pages[i])
        out = output_dir / f"{stem}_page_{i + 1}.pdf"
        with open(out, "wb") as f:
            writer.write(f)
        written.append(out)
    return written


def library_path(filename):
    """Absolute path of a file stored in the library."""
    return LIBRARY_DIR / filename
