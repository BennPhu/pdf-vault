"""JS-facing API bridge for the pywebview UI.

Every public method returns a JSON-serializable dict:
{"ok": True, ...} on success or {"ok": False, "error": "..."} on failure.
"""

import subprocess
from pathlib import Path

import webview

import pdf_core
import updater
from pdf_core import PDFError, __version__


def _ok(**data):
    return {"ok": True, **data}


def _err(message):
    return {"ok": False, "error": str(message)}


class Api:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    # ----------------------------------------------------------- app state

    def get_state(self):
        """Version, storage location, and whether first-run setup is needed."""
        return _ok(
            version=__version__,
            configured=pdf_core.is_configured(),
            storage_dir=str(pdf_core.storage_dir()),
            folder_access=pdf_core.folder_access_ok(),
            dev_mode=pdf_core.dev_mode(),
        )

    def choose_storage_dir(self):
        """Native folder picker for the storage location."""
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG, directory=str(Path.home()))
        if not result:
            return _err("cancelled")
        pdf_core.set_storage_dir(result[0] if isinstance(result, (list, tuple)) else result)
        return self.get_state()

    def use_default_storage(self):
        pdf_core.set_storage_dir(pdf_core.DEFAULT_DATA_DIR)
        return self.get_state()

    # ------------------------------------------------------------- library

    def list_library(self):
        """Index entries plus a small page-1 thumbnail for each."""
        entries = []
        for entry in pdf_core.sync_index():
            item = dict(entry)
            path = pdf_core.library_path(entry["filename"])
            item["missing"] = not path.exists()
            if not item["missing"]:
                item["thumb"] = pdf_core.get_thumbnail_b64(entry["filename"])
            entries.append(item)
        return _ok(entries=entries)

    def add_pdfs_dialog(self):
        """Native file picker, then add the chosen PDFs or images."""
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=("PDFs and images (*.pdf;*.png;*.jpg;*.jpeg;*.webp)",
                        "PDF files (*.pdf)"))
        if not result:
            return _err("cancelled")
        return self.add_paths(list(result))

    def add_paths(self, paths):
        """Add PDFs/images by absolute path (drag-and-drop and the picker)."""
        added, errors = [], []
        if len(paths) > pdf_core.MAX_ADD_BATCH:
            errors.append(f"Too many files at once (limit {pdf_core.MAX_ADD_BATCH}); "
                          f"only the first {pdf_core.MAX_ADD_BATCH} were considered.")
            paths = paths[:pdf_core.MAX_ADD_BATCH]
        for p in paths:
            try:
                entry = pdf_core.add_any(p)
                added.append(entry["filename"])
            except PDFError as e:
                errors.append(str(e))
        return _ok(added=added, errors=errors)

    def rename(self, filename, new_name):
        """Rename a library PDF."""
        try:
            entry = pdf_core.rename_pdf(filename, new_name)
            return _ok(entry=entry)
        except PDFError as e:
            return _err(e)

    def rotate_page(self, filename, page_number):
        try:
            return _ok(entry=pdf_core.rotate_page(filename, int(page_number)))
        except (PDFError, ValueError, TypeError) as e:
            return _err(e)

    def delete_page(self, filename, page_number):
        try:
            return _ok(entry=pdf_core.delete_page(filename, int(page_number)))
        except (PDFError, ValueError, TypeError) as e:
            return _err(e)

    def move_page(self, filename, page_number, direction):
        try:
            return _ok(entry=pdf_core.move_page(
                filename, int(page_number), int(direction)))
        except (PDFError, ValueError, TypeError) as e:
            return _err(e)

    def compress(self, filenames):
        """Compress the given library PDFs in place; reports bytes saved."""
        before = after = 0
        errors = []
        for filename in filenames:
            try:
                result = pdf_core.compress_pdf(filename)
                before += result["before"]
                after += result["after"]
            except PDFError as e:
                errors.append(str(e))
        return _ok(before=before, after=after, errors=errors)

    def render_page(self, filename, page_number):
        """Full-size render of a library PDF page for the preview panel."""
        try:
            data, total = pdf_core.render_page_b64(
                pdf_core.library_path(filename), page_number)
            return _ok(image=data, total=total, page=page_number)
        except PDFError as e:
            return _err(e)

    # ------------------------------------------------------------- actions

    def merge(self, filenames):
        if len(filenames) < 2:
            return _err("Select at least two PDFs to merge.")
        output = self._save_dialog("merged.pdf")
        if not output:
            return _err("cancelled")
        try:
            paths = [pdf_core.library_path(f) for f in filenames]
            pdf_core.merge_pdfs(paths, output)
            pdf_core.set_last_output_dir(Path(output).parent)
            return _ok(message=f"Merged {len(paths)} PDFs into {Path(output).name}")
        except PDFError as e:
            return _err(e)

    def split_range(self, filename, start, end):
        """Extract pages start-end into one new PDF (Split Selected)."""
        stem = Path(filename).stem
        output = self._save_dialog(f"{stem}_pages_{start}-{end}.pdf")
        if not output:
            return _err("cancelled")
        try:
            pdf_core.extract_pages(pdf_core.library_path(filename), int(start), int(end), output)
            pdf_core.set_last_output_dir(Path(output).parent)
            return _ok(message=f"Saved pages {start}-{end} to {Path(output).name}")
        except PDFError as e:
            return _err(e)

    def split_individual(self, filename, start, end):
        """One file per page in the range (Individual Splits)."""
        folder = self._window.create_file_dialog(
            webview.FOLDER_DIALOG, directory=pdf_core.last_output_dir())
        if not folder:
            return _err("cancelled")
        folder = folder[0] if isinstance(folder, (list, tuple)) else folder
        try:
            written = pdf_core.split_pdf(
                pdf_core.library_path(filename), folder, int(start), int(end))
            pdf_core.set_last_output_dir(folder)
            return _ok(message=f"Split into {len(written)} one-page file(s)")
        except PDFError as e:
            return _err(e)

    def create_master(self):
        output = self._save_dialog("master.pdf")
        if not output:
            return _err("cancelled")
        try:
            pdf_core.build_master(output)
            pdf_core.set_last_output_dir(Path(output).parent)
            return _ok(message=f"Master PDF created: {Path(output).name}")
        except PDFError as e:
            return _err(e)

    # -------------------------------------------- developer mode (local only)

    def dev_info(self):
        """Diagnostics for the developer panel (PDFVAULT_DEV=1 only)."""
        if not pdf_core.dev_mode():
            return _err("Developer mode is not enabled.")
        return _ok(info=pdf_core.dev_info())

    def dev_rebuild_thumbs(self):
        if not pdf_core.dev_mode():
            return _err("Developer mode is not enabled.")
        removed = pdf_core.dev_rebuild_thumbs()
        return _ok(message=f"Cleared {removed} cached thumbnails")

    def dev_sync_now(self):
        if not pdf_core.dev_mode():
            return _err("Developer mode is not enabled.")
        entries = pdf_core.sync_index()
        return _ok(message=f"Index synced ({len(entries)} files)")

    def open_library_folder(self):
        pdf_core.ensure_dirs()
        subprocess.run(["/usr/bin/open", str(pdf_core.library_dir())], check=False)
        return _ok()

    def delete(self, filenames):
        """Move PDFs to trash; returns the removed entries for undo."""
        deleted, errors = [], []
        for filename in filenames:
            try:
                deleted.append(pdf_core.delete_pdf(filename))
            except PDFError as e:
                errors.append(str(e))
        pdf_core.purge_trash()
        return _ok(deleted=deleted, errors=errors)

    def restore(self, entries):
        """Undo deletions: move PDFs back from trash and re-index them."""
        restored, errors = [], []
        for entry in entries:
            try:
                restored.append(pdf_core.restore_pdf(entry))
            except PDFError as e:
                errors.append(str(e))
        return _ok(restored=restored, errors=errors)

    # ------------------------------------------------------ activity & stats

    def get_activity(self):
        """Recent activity log + program/storage stats for the settings page."""
        try:
            return _ok(log=pdf_core.get_log(), stats=pdf_core.get_stats())
        except Exception as e:
            return _err(e)

    def get_full_log(self):
        """Persisted activity.log tail (newest first) for the full log view."""
        try:
            lines = pdf_core.read_log_tail()
            log_path = pdf_core.log_file_path()
            size_kb = round(log_path.stat().st_size / 1024, 1) if log_path.exists() else 0
            return _ok(lines=lines, size_kb=size_kb, path=str(log_path))
        except Exception as e:
            return _err(e)

    # ------------------------------------------------------------- updates

    def check_updates(self):
        try:
            update = updater.check_for_update()
        except updater.UpdateError as e:
            return _err(e)
        if update is None:
            return _ok(update=None)
        return _ok(update={"version": update["version"], "notes": update["notes"][:500]})

    def install_update(self):
        try:
            update = updater.check_for_update()
            if update is None:
                return _err("Already up to date.")
            result = updater.download_and_install(update)
            if str(result).endswith(".app"):
                updater.relaunch(result)
            return _ok(message=f"Update downloaded to {result}")
        except updater.UpdateError as e:
            return _err(e)

    # ------------------------------------------------------------- helpers

    def _save_dialog(self, default_name):
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory=pdf_core.last_output_dir(),
            save_filename=default_name,
        )
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result
