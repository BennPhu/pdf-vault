"""Core PDF logic for PDF Vault: config, add/append, merge, split, and index management."""

import base64
import json
import shutil
from datetime import datetime
from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter

__version__ = "1.1.0"
GITHUB_REPO = "BennPhu/pdf-vault"

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = Path.home() / ".pdf_vault_config.json"

# Security limits for untrusted PDF input
MAX_FILE_SIZE_MB = 500
MAX_PAGES = 10000

_config = None


class PDFError(Exception):
    """Raised when a PDF operation fails."""


# --------------------------------------------------------------------- config

def _atomic_write_json(path, data):
    """Write JSON atomically (temp file + rename) to prevent corruption."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def _validate_config(cfg):
    """Drop untrusted/invalid config values instead of trusting them blindly."""
    if not isinstance(cfg, dict):
        return {}
    clean = {}
    storage = cfg.get("storage_dir")
    if isinstance(storage, str):
        p = Path(storage)
        if p.is_absolute() and (p.is_dir() or not p.exists()):
            clean["storage_dir"] = storage
    out = cfg.get("last_output_dir")
    if isinstance(out, str) and Path(out).is_absolute():
        clean["last_output_dir"] = out
    return clean


def load_config():
    """Load config from disk (cached). Returns dict or empty dict if unset."""
    global _config
    if _config is None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    _config = _validate_config(json.load(f))
            except (json.JSONDecodeError, OSError):
                _config = {}
        else:
            _config = {}
    return _config


def save_config(**updates):
    """Update and persist the config atomically."""
    cfg = load_config()
    cfg.update(updates)
    _atomic_write_json(CONFIG_FILE, cfg)
    return cfg


def is_configured():
    """True if the user has chosen a storage folder."""
    return bool(load_config().get("storage_dir"))


def set_storage_dir(path):
    """Set the storage folder and create its structure."""
    path = Path(path).expanduser().resolve()
    save_config(storage_dir=str(path))
    ensure_dirs()
    return path


def storage_dir():
    """The user-chosen storage folder (falls back to the project data dir)."""
    cfg = load_config()
    return Path(cfg.get("storage_dir", DEFAULT_DATA_DIR))


def library_dir():
    return storage_dir() / "library"


def index_file_path():
    return storage_dir() / "index.json"


def last_output_dir():
    """Last folder the user saved merge/split output to (or home)."""
    path = load_config().get("last_output_dir")
    if path and Path(path).is_dir():
        return path
    return str(Path.home())


def set_last_output_dir(path):
    save_config(last_output_dir=str(path))


def ensure_dirs():
    library_dir().mkdir(parents=True, exist_ok=True)


def load_index():
    index_file = index_file_path()
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_index(index):
    ensure_dirs()
    _atomic_write_json(index_file_path(), index)


def sanitize_filename(name):
    """Strip path separators and control characters from a filename."""
    name = Path(name).name  # drop any directory components
    name = "".join(c for c in name if c.isprintable() and c not in '\\/:*?"<>|')
    name = name.strip(". ")
    if not name or name == ".pdf":
        name = "unnamed.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def _validate_pdf(path):
    """Return a PdfReader if the file is a safe, readable PDF, else raise PDFError."""
    path = Path(path)
    if not path.exists():
        raise PDFError(f"File not found: {path}")
    if path.is_symlink():
        raise PDFError(f"Symlinks are not allowed: {path.name}")
    if not path.is_file():
        raise PDFError(f"Not a regular file: {path.name}")
    if path.suffix.lower() != ".pdf":
        raise PDFError(f"Not a PDF file: {path.name}")
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise PDFError(
            f"File too large ({size_mb:.0f} MB > {MAX_FILE_SIZE_MB} MB limit): {path.name}")
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise PDFError(f"PDF is password-protected: {path.name}")
        if len(reader.pages) > MAX_PAGES:
            raise PDFError(
                f"Too many pages ({len(reader.pages)} > {MAX_PAGES} limit): {path.name}")
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


def add_pdf(source_path):
    """Add a PDF: copy to library and update the index.

    Returns the index entry dict.
    """
    ensure_dirs()
    source_path = Path(source_path)
    reader = _validate_pdf(source_path)

    dest = _unique_dest(library_dir(), sanitize_filename(source_path.name))
    shutil.copy2(source_path, dest)

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


def extract_pages(source_path, start, end, output_path):
    """Extract a 1-based inclusive page range into a single new PDF file."""
    reader = _validate_pdf(source_path)
    total = len(reader.pages)
    if not (1 <= start <= end <= total):
        raise PDFError(f"Invalid page range {start}-{end} (document has {total} pages).")
    writer = PdfWriter()
    for i in range(start - 1, end):
        writer.add_page(reader.pages[i])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path


def build_master(output_path):
    """Combine every PDF in the library (index order) into one master PDF.

    Only runs when the user explicitly asks for it.
    """
    index = load_index()
    if not index:
        raise PDFError("Library is empty — add some PDFs first.")
    writer = PdfWriter()
    missing = []
    for entry in index:
        path = library_path(entry["filename"])
        if not path.exists():
            missing.append(entry["filename"])
            continue
        reader = _validate_pdf(path)
        for page in reader.pages:
            writer.add_page(page)
    if missing:
        raise PDFError("Missing library files: " + ", ".join(missing))
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
    return library_dir() / filename


def page_count(path):
    """Number of pages in a PDF."""
    return len(_validate_pdf(path).pages)


def render_page_b64(path, page_number=1, max_px=900):
    """Render a 1-based page as a base64 PNG data string for the web UI.

    Returns (data, total_pages) where data is a base64-encoded PNG.
    """
    path = Path(path)
    if not path.exists():
        raise PDFError(f"File not found: {path}")
    try:
        with fitz.open(str(path)) as doc:
            total = len(doc)
            if not (1 <= page_number <= total):
                raise PDFError(f"Page {page_number} out of range (1-{total}).")
            page = doc[page_number - 1]
            zoom = min(max_px / page.rect.width, max_px / page.rect.height, 4.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            return base64.b64encode(pix.tobytes("png")).decode("ascii"), total
    except PDFError:
        raise
    except Exception as e:
        raise PDFError(f"Cannot render '{path.name}': {e}")
