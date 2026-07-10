"""Core PDF logic for PDF Vault: config, add/append, merge, split, and index management."""

import base64
import contextlib
import json
import os
import resource
import shutil
import subprocess
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter

__version__ = "1.5.4"
GITHUB_REPO = "BennPhu/pdf-vault"

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = Path.home() / ".pdf_vault_config.json"

# Security limits for untrusted PDF input
MAX_FILE_SIZE_MB = 500
MAX_PAGES = 10000
MAX_ADD_BATCH = 100  # bound on files accepted per drop/dialog

# Image types accepted for image -> PDF conversion
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Storage housekeeping
TRASH_RETENTION_DAYS = 30
LOG_MAX_BYTES = 512 * 1024

_config = None

_APP_START = datetime.now()
_activity_log = deque(maxlen=500)  # in-memory ring buffer of recent events


class PDFError(Exception):
    """Raised when a PDF operation fails."""


# ------------------------------------------------------------ activity log

def log_file_path():
    return storage_dir() / "activity.log"


def log_event(action, detail=""):
    """Record an event touching the user's folder (in memory + on disk)."""
    event = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "detail": str(detail),
    }
    _activity_log.append(event)
    try:
        log_path = log_file_path()
        if log_path.exists() and log_path.stat().st_size > LOG_MAX_BYTES:
            log_path.replace(log_path.with_suffix(".log.1"))  # keep one generation
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{event['time']}  {action:<10} {event['detail']}\n")
    except OSError:
        pass  # logging must never break the app
    return event


def get_log(limit=200):
    """Most recent events, newest first."""
    return list(_activity_log)[-limit:][::-1]


def clear_log():
    """Delete the persisted log (and its rotation) and empty the in-memory
    ring buffer. Logs one fresh marker event so the reset is auditable.
    Returns the number of bytes freed on disk.
    """
    freed = 0
    for path in (log_file_path(), log_file_path().with_suffix(".log.1")):
        with contextlib.suppress(OSError):
            if path.exists():
                freed += path.stat().st_size
                path.unlink()
    _activity_log.clear()
    log_event("log", "activity log cleared by user")
    return freed


def read_log_tail(max_lines=1000):
    """Last max_lines of the persisted activity.log, newest first.

    Bounded read: at most LOG_MAX_BYTES + one rotation generation.
    Returns a list of raw text lines (already formatted by log_event).
    """
    lines = []
    for path in (log_file_path().with_suffix(".log.1"), log_file_path()):
        try:
            if path.exists() and path.stat().st_size <= 2 * LOG_MAX_BYTES:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines.extend(f.read().splitlines())
        except OSError:
            continue
    return lines[-max_lines:][::-1]


def _dir_size(path):
    """Total size in bytes of all files under path (0 if missing)."""
    total = 0
    if path.is_dir():
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
    return total


def dev_mode():
    """Local-only developer mode; enabled by launching with PDFVAULT_DEV=1.

    Never toggleable from the UI and never transmits anything anywhere —
    it only unlocks extra diagnostics in the Activity panel.
    """
    return os.environ.get("PDFVAULT_DEV") == "1"


def dev_info():
    """Extra local diagnostics for the developer panel."""
    tdir = thumbs_dir()
    thumbs = list(tdir.glob("*.jpg")) if tdir.is_dir() else []
    log_path = log_file_path()
    try:
        log_bytes = log_path.stat().st_size if log_path.exists() else 0
    except OSError:
        log_bytes = 0
    return {
        "config": load_config(),
        "config_file": str(CONFIG_FILE),
        "storage_dir": str(storage_dir()),
        "library_dir": str(library_dir()),
        "trash_dir": str(trash_dir()),
        "thumbs_dir": str(tdir),
        "thumb_count": len(thumbs),
        "thumb_kb": round(sum(t.stat().st_size for t in thumbs) / 1024, 1),
        "log_file": str(log_path),
        "log_kb": round(log_bytes / 1024, 1),
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version.split()[0],
    }


def dev_rebuild_thumbs():
    """Drop every cached thumbnail; they regenerate on next library load."""
    tdir = thumbs_dir()
    removed = 0
    if tdir.is_dir():
        for thumb in tdir.glob("*.jpg"):
            with contextlib.suppress(OSError):
                thumb.unlink()
                removed += 1
    log_event("dev", f"thumbnail cache cleared ({removed} files)")
    return removed


def _current_rss_mb():
    """Current resident memory in MB (peak != current; ask ps)."""
    try:
        out = subprocess.run(
            ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())],
            capture_output=True, text=True, timeout=5, check=False)
        return round(int(out.stdout.strip()) / 1024, 1)  # ps reports KB
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def get_stats():
    """Program + storage statistics for the settings log page."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # ru_maxrss is bytes on macOS
    peak_mb = usage.ru_maxrss / (1024 * 1024)
    memory_mb = _current_rss_mb()
    lib, trash, thumbs = library_dir(), trash_dir(), thumbs_dir()
    lib_files = list(lib.glob("*.pdf")) if lib.is_dir() else []
    trash_files = list(trash.glob("*.pdf")) if trash.is_dir() else []
    thumb_files = list(thumbs.glob("*.jpg")) if thumbs.is_dir() else []
    lib_bytes = _dir_size(lib)
    trash_bytes = _dir_size(trash)
    thumb_bytes = _dir_size(thumbs)
    try:
        log_bytes = log_file_path().stat().st_size if log_file_path().exists() else 0
    except OSError:
        log_bytes = 0
    uptime = datetime.now() - _APP_START
    return {
        "version": __version__,
        "uptime_seconds": int(uptime.total_seconds()),
        "memory_mb": memory_mb if memory_mb is not None else round(peak_mb, 1),
        "peak_memory_mb": round(peak_mb, 1),
        "cpu_seconds": round(usage.ru_utime + usage.ru_stime, 1),
        "storage_dir": str(storage_dir()),
        "library_files": len(lib_files),
        "library_mb": round(lib_bytes / (1024 * 1024), 2),
        "trash_files": len(trash_files),
        "trash_mb": round(trash_bytes / (1024 * 1024), 2),
        "thumb_files": len(thumb_files),
        "thumbs_mb": round(thumb_bytes / (1024 * 1024), 2),
        "log_kb": round(log_bytes / 1024, 1),
        "index_entries": len(load_index()),
        "footprint_mb": round(
            (lib_bytes + trash_bytes + thumb_bytes + log_bytes) / (1024 * 1024), 2),
        "render_cache_mb": round(render_cache_bytes() / (1024 * 1024), 1),
        "log_events": len(_activity_log),
    }


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
    # Module-level cache: read once per process, patched directly in tests.
    global _config  # noqa: PLW0603
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


def trash_dir():
    return storage_dir() / ".trash"


def thumbs_dir():
    return storage_dir() / ".thumbs"


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


def folder_access_ok():
    """True if the app is allowed to read the library folder.

    macOS (TCC) can silently deny access to protected folders like
    ~/Documents; pathlib.glob swallows the PermissionError, which would
    make the folder look empty. Check explicitly instead.
    """
    try:
        os.listdir(library_dir())
        return True
    except FileNotFoundError:
        return True  # not created yet is fine
    except OSError:
        return False


def sync_index():
    """Reconcile the index with the library folder (self-healing).

    The folder is the source of truth: PDFs on disk that are missing from
    the index get added, and index entries whose file is gone get dropped.
    This keeps the UI correct even if files are added or removed outside
    the app (Finder, drag-and-drop races, etc.). Returns the fresh index.

    If the folder cannot be read (macOS permission denial), the index is
    returned untouched — never wiped based on a folder we cannot see.
    """
    index = load_index()
    changed = False
    lib = library_dir()
    try:
        names = os.listdir(lib) if lib.is_dir() else []
    except OSError:
        log_event("error", "cannot read library folder (permission denied?)")
        return index
    on_disk = {n for n in names if n.lower().endswith(".pdf")}

    # Drop entries whose file has disappeared
    kept = [e for e in index if e["filename"] in on_disk]
    if len(kept) != len(index):
        index = kept
        changed = True

    # Add PDFs on disk that are not indexed yet
    known = {e["filename"] for e in index}
    for name in sorted(on_disk - known):
        path = lib / name
        try:
            reader = _validate_pdf(path)
        except PDFError:
            continue  # skip unreadable strays
        index.append({
            "filename": name,
            "added": datetime.fromtimestamp(
                path.stat().st_mtime).isoformat(timespec="seconds"),
            "pages": len(reader.pages),
            "size_bytes": path.stat().st_size,
        })
        changed = True

    if changed:
        save_index(index)
        log_event("sync", f"index reconciled with folder ({len(index)} files)")
        _prune_thumbs(on_disk)
    return index


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
                raise PDFError(
                    f"PDF is password-protected: {path.name}") from None
        if len(reader.pages) > MAX_PAGES:
            raise PDFError(
                f"Too many pages ({len(reader.pages)} > {MAX_PAGES} limit): {path.name}")
        return reader
    except PDFError:
        raise
    except Exception as e:
        raise PDFError(f"Cannot read PDF '{path.name}': {e}") from e


def _unique_dest(directory, filename):
    """Return a destination path in directory, renaming on clashes."""
    dest = directory / filename
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for counter in range(1, 100000):  # bounded (P10 rule 2)
        dest = directory / f"{stem}_{counter}{suffix}"
        if not dest.exists():
            return dest
    raise PDFError(f"Too many name clashes for '{filename}'.")


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
    log_event("add", f"{dest.name} ({entry['pages']} pages)")
    return entry


def delete_pdf(filename):
    """Move a library PDF to the trash folder and drop it from the index.

    Returns the removed index entry so the deletion can be undone.
    """
    path = library_path(filename)
    index = load_index()
    entry = next((e for e in index if e["filename"] == filename), None)
    if entry is None:
        raise PDFError(f"Not in the library index: {filename}")
    if path.exists():
        trash_dir().mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(trash_dir() / filename))
    save_index([e for e in index if e["filename"] != filename])
    log_event("delete", f"{filename} -> trash")
    return entry


def restore_pdf(entry):
    """Undo a delete: move the file back from trash and re-add its index entry."""
    filename = entry["filename"]
    dest = library_path(filename)  # validates the filename (no traversal)
    trash_path = trash_dir() / filename
    if not trash_path.exists():
        raise PDFError(f"Cannot restore (no longer in trash): {filename}")
    ensure_dirs()
    shutil.move(str(trash_path), str(dest))
    index = load_index()
    if not any(e["filename"] == filename for e in index):
        index.append(entry)
        save_index(index)
    log_event("restore", f"{filename} <- trash")
    return entry


def rename_pdf(old_name, new_name):
    """Rename a library PDF; returns the updated index entry."""
    src = library_path(old_name)
    if not src.exists():
        raise PDFError(f"Not in the library: {old_name}")
    cleaned = sanitize_filename(new_name)
    if cleaned == old_name:
        entry = next((e for e in load_index() if e["filename"] == old_name), None)
        if entry is None:
            raise PDFError(f"Not in the library index: {old_name}")
        return entry
    dest = _unique_dest(library_dir(), cleaned)
    src.rename(dest)
    index = load_index()
    entry = next((e for e in index if e["filename"] == old_name), None)
    if entry is None:  # index out of sync — self-heal with a fresh entry
        entry = {
            "filename": dest.name,
            "added": datetime.now().isoformat(timespec="seconds"),
            "pages": page_count(dest),
            "size_bytes": dest.stat().st_size,
        }
        index.append(entry)
    else:
        entry["filename"] = dest.name
    save_index(index)
    for thumb in thumbs_dir().glob(f"{old_name}.*.jpg"):
        thumb.unlink(missing_ok=True)
    log_event("rename", f"{old_name} -> {dest.name}")
    return entry


def _atomic_pdf_replace(path, writer):
    """Write a PdfWriter to path atomically (temp file + replace)."""
    tmp = path.with_suffix(".pdf.tmp")
    try:
        with open(tmp, "wb") as f:
            writer.write(f)
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _refresh_entry(filename):
    """Re-read pages/size for a rewritten library file; returns the entry."""
    path = library_path(filename)
    reader = _validate_pdf(path)
    index = load_index()
    entry = next((e for e in index if e["filename"] == filename), None)
    if entry is None:
        raise PDFError(f"Not in the library index: {filename}")
    entry["pages"] = len(reader.pages)
    entry["size_bytes"] = path.stat().st_size
    save_index(index)
    return entry


def rotate_page(filename, page_number, degrees=90):
    """Rotate one page (1-based) by a multiple of 90 degrees, in place."""
    if degrees % 90 != 0:
        raise PDFError("Rotation must be a multiple of 90 degrees.")
    path = library_path(filename)
    reader = _validate_pdf(path)
    total = len(reader.pages)
    if not (1 <= page_number <= total):
        raise PDFError(f"Page {page_number} out of range (1-{total}).")
    writer = PdfWriter()
    for i in range(total):
        page = reader.pages[i]
        if i == page_number - 1:
            page.rotate(degrees)
        writer.add_page(page)
    _atomic_pdf_replace(path, writer)
    entry = _refresh_entry(filename)
    log_event("edit", f"{filename}: rotated page {page_number} by {degrees}°")
    return entry


def delete_page(filename, page_number):
    """Remove one page (1-based) from a library PDF, in place."""
    path = library_path(filename)
    reader = _validate_pdf(path)
    total = len(reader.pages)
    if not (1 <= page_number <= total):
        raise PDFError(f"Page {page_number} out of range (1-{total}).")
    if total == 1:
        raise PDFError("Cannot delete the only page of a PDF.")
    writer = PdfWriter()
    for i in range(total):
        if i != page_number - 1:
            writer.add_page(reader.pages[i])
    _atomic_pdf_replace(path, writer)
    entry = _refresh_entry(filename)
    log_event("edit", f"{filename}: deleted page {page_number}")
    return entry


def move_page(filename, page_number, direction):
    """Swap a page (1-based) with its neighbor; direction is -1 or +1."""
    if direction not in (-1, 1):
        raise PDFError("Direction must be -1 (earlier) or +1 (later).")
    path = library_path(filename)
    reader = _validate_pdf(path)
    total = len(reader.pages)
    target = page_number + direction
    if not (1 <= page_number <= total) or not (1 <= target <= total):
        raise PDFError(f"Cannot move page {page_number} to position {target}.")
    order = list(range(total))
    order[page_number - 1], order[target - 1] = order[target - 1], order[page_number - 1]
    writer = PdfWriter()
    for i in order:
        writer.add_page(reader.pages[i])
    _atomic_pdf_replace(path, writer)
    entry = _refresh_entry(filename)
    log_event("edit", f"{filename}: moved page {page_number} to {target}")
    return entry


def _edit_backup_dir():
    return storage_dir() / ".edit_backup"


def begin_page_edit(filename):
    """Snapshot a library PDF so an editing session can be discarded."""
    path = library_path(filename)
    _validate_pdf(path)
    bdir = _edit_backup_dir()
    bdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, bdir / filename)


def discard_page_edit(filename):
    """Restore the pre-edit snapshot, undoing every edit in the session."""
    backup = _edit_backup_dir() / filename
    if not backup.exists():
        raise PDFError("No edit session to discard.")
    shutil.move(str(backup), str(library_path(filename)))
    entry = _refresh_entry(filename)
    log_event("edit", f"{filename}: changes discarded")
    return entry


def commit_page_edit(filename):
    """End an editing session, keeping the changes."""
    with contextlib.suppress(OSError):
        (_edit_backup_dir() / filename).unlink(missing_ok=True)


def clear_edit_backups():
    """Remove stale edit snapshots (e.g. after a crash mid-edit)."""
    bdir = _edit_backup_dir()
    if bdir.is_dir():
        shutil.rmtree(bdir, ignore_errors=True)


def compress_pdf(filename):
    """Rewrite a library PDF with PyMuPDF's optimizations, in place.

    Keeps a pre-compression copy in the trash for undo. Returns a dict
    with before/after sizes in bytes.
    """
    path = library_path(filename)
    _validate_pdf(path)
    before = path.stat().st_size
    tmp = path.with_suffix(".pdf.tmp")
    try:
        with fitz.open(str(path)) as doc:
            doc.save(str(tmp), garbage=4, deflate=True, clean=True)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise PDFError(f"Cannot compress '{filename}': {e}") from e
    after = tmp.stat().st_size
    if after >= before:
        tmp.unlink(missing_ok=True)
        log_event("compress", f"{filename}: already optimal")
        return {"filename": filename, "before": before, "after": before}
    trash_dir().mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, _unique_dest(trash_dir(), filename))
    tmp.replace(path)
    _refresh_entry(filename)
    log_event("compress",
              f"{filename}: {before / 1048576:.2f} MB -> {after / 1048576:.2f} MB")
    return {"filename": filename, "before": before, "after": after}


def add_image(source_path):
    """Convert an image file to a 1-page PDF and add it to the library."""
    src = Path(source_path)
    if not src.exists():
        raise PDFError(f"File not found: {src}")
    if src.is_symlink():
        raise PDFError(f"Symlinks are not allowed: {src.name}")
    if not src.is_file():
        raise PDFError(f"Not a regular file: {src.name}")
    if src.suffix.lower() not in IMAGE_EXTS:
        raise PDFError(f"Unsupported image type: {src.name}")
    size_mb = src.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise PDFError(
            f"File too large ({size_mb:.0f} MB > {MAX_FILE_SIZE_MB} MB limit): {src.name}")
    try:
        with fitz.open(str(src)) as img:
            pdf_bytes = img.convert_to_pdf()
    except Exception as e:
        raise PDFError(f"Cannot convert image '{src.name}': {e}") from e
    ensure_dirs()
    dest = _unique_dest(library_dir(), sanitize_filename(src.stem + ".pdf"))
    dest.write_bytes(pdf_bytes)
    try:
        reader = _validate_pdf(dest)
    except PDFError:
        dest.unlink(missing_ok=True)
        raise
    entry = {
        "filename": dest.name,
        "added": datetime.now().isoformat(timespec="seconds"),
        "pages": len(reader.pages),
        "size_bytes": dest.stat().st_size,
    }
    index = load_index()
    index.append(entry)
    save_index(index)
    log_event("add", f"{dest.name} (from image {src.name})")
    return entry


def add_any(source_path):
    """Add a PDF or an image (converted to PDF) to the library."""
    if Path(source_path).suffix.lower() in IMAGE_EXTS:
        return add_image(source_path)
    return add_pdf(source_path)


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
    log_event("merge", f"{len(paths)} PDFs -> {output_path.name}")
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
    log_event("split", f"pages {start}-{end} -> {output_path.name}")
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
    log_event("master", f"{len(index)} PDFs -> {output_path.name}")
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
    log_event("split", f"{stem}: {len(written)} pages -> {output_dir.name}/")
    return written


def library_path(filename):
    """Absolute path of a file stored in the library.

    Rejects path traversal: the JS bridge passes filenames, and nothing
    it sends may escape the library folder.
    """
    filename = str(filename)
    if (not filename or filename != Path(filename).name
            or filename in (".", "..") or filename.startswith("/")):
        raise PDFError(f"Invalid filename: {filename!r}")
    return library_dir() / filename


def page_count(path):
    """Number of pages in a PDF."""
    return len(_validate_pdf(path).pages)


def shrink_render_cache():
    """Empty MuPDF's global object/render store.

    MuPDF caches decoded pages up to ~256 MB and never trims on its own;
    after batch imports this dominated the app's memory. Rendered data is
    simply re-decoded from disk the next time it is needed.
    """
    # Cache trimming must never break an operation.
    with contextlib.suppress(Exception):
        fitz.TOOLS.store_shrink(100)


def render_cache_bytes():
    """Current size of MuPDF's render store in bytes."""
    try:
        return int(fitz.TOOLS.store_size)
    except Exception:
        return 0


def get_file_info(filename):
    """Full metadata for one library PDF (for the file-info panel)."""
    path = library_path(filename)
    if not path.exists():
        raise PDFError(f"File not found: {filename}")
    entry = next(
        (e for e in load_index() if e.get("filename") == filename), {})
    stat = path.stat()
    info = {
        "filename": filename,
        "size_bytes": stat.st_size,
        "added": entry.get("added", ""),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "pages": entry.get("pages", 0),
    }
    # Partial info beats an error dialog: metadata extraction is best-effort.
    with contextlib.suppress(Exception), fitz.open(str(path)) as doc:
        info["pages"] = len(doc)
        info["encrypted"] = bool(doc.needs_pass)
        rect = doc[0].rect if len(doc) else None
        if rect:
            info["page_size"] = (
                f"{rect.width:.0f} x {rect.height:.0f} pt "
                f"({rect.width / 72:.1f} x {rect.height / 72:.1f} in)")
        meta = doc.metadata or {}
        for key in ("title", "author", "creator", "producer", "format"):
            if meta.get(key):
                info[key] = meta[key]
    shrink_render_cache()
    return info


def render_page_b64(path, page_number=1, max_px=900):
    """Render a 1-based page as a base64 JPEG data string for the web UI.

    JPEG keeps the base64 payload (and WebView memory) ~5-10x smaller
    than PNG. Returns (data, total_pages).
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
            data = pix.tobytes("jpeg", jpg_quality=80)
            pix = None
            return base64.b64encode(data).decode("ascii"), total
    except PDFError:
        raise
    except Exception as e:
        raise PDFError(f"Cannot render '{path.name}': {e}") from e


def get_thumbnail_b64(filename, max_px=240):
    """Base64 JPEG thumbnail of page 1, cached on disk in .thumbs/.

    Cache key includes the source file's mtime so edited files re-render.
    Returns None if the file cannot be rendered.
    """
    path = library_path(filename)
    if not path.exists():
        return None
    try:
        mtime = int(path.stat().st_mtime)
    except OSError:
        return None
    thumb_path = thumbs_dir() / f"{filename}.{mtime}.jpg"
    if thumb_path.exists():
        try:
            return base64.b64encode(thumb_path.read_bytes()).decode("ascii")
        except OSError:
            pass
    try:
        with fitz.open(str(path)) as doc:
            page = doc[0]
            zoom = min(max_px / page.rect.width, max_px / page.rect.height, 4.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            data = pix.tobytes("jpeg", jpg_quality=75)
            pix = None
    except Exception:
        return None
    try:
        thumbs_dir().mkdir(parents=True, exist_ok=True)
        # Drop stale generations of this file's thumbnail first
        for old in thumbs_dir().glob(f"{filename}.*.jpg"):
            old.unlink(missing_ok=True)
        thumb_path.write_bytes(data)
    except OSError:
        pass  # cache is best-effort
    return base64.b64encode(data).decode("ascii")


def purge_trash(max_age_days=TRASH_RETENTION_DAYS):
    """Delete trashed PDFs older than max_age_days. Returns count removed."""
    tdir = trash_dir()
    if not tdir.is_dir():
        return 0
    cutoff = datetime.now().timestamp() - max_age_days * 86400
    removed = 0
    try:
        items = list(tdir.iterdir())
    except OSError:
        return 0  # folder unreadable (e.g. macOS TCC denial) — never crash
    for item in items:
        try:
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        log_event("purge", f"{removed} file(s) older than {max_age_days} days removed from trash")
    return removed


def _prune_thumbs(valid_filenames):
    """Delete cached thumbnails whose source file left the library."""
    tdir = thumbs_dir()
    if not tdir.is_dir():
        return
    for thumb in tdir.glob("*.jpg"):
        # thumb name: <filename>.<mtime>.jpg
        source = thumb.name.rsplit(".", 2)[0]
        if source not in valid_filenames:
            with contextlib.suppress(OSError):
                thumb.unlink()
