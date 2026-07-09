"""JS-facing API bridge for the pywebview UI.

Every public method returns a JSON-serializable dict:
{"ok": True, ...} on success or {"ok": False, "error": "..."} on failure.
"""

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
                try:
                    thumb, _ = pdf_core.render_page_b64(path, 1, max_px=240)
                    item["thumb"] = thumb
                except PDFError:
                    item["thumb"] = None
            entries.append(item)
        return _ok(entries=entries)

    def add_pdfs_dialog(self):
        """Native file picker, then add the chosen PDFs."""
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=("PDF files (*.pdf)",))
        if not result:
            return _err("cancelled")
        return self.add_paths(list(result))

    def add_paths(self, paths):
        """Add PDFs by absolute path (used by drag-and-drop and the picker)."""
        added, errors = [], []
        for p in paths:
            try:
                entry = pdf_core.add_pdf(p)
                added.append(entry["filename"])
            except PDFError as e:
                errors.append(str(e))
        return _ok(added=added, errors=errors)

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

    def open_library_folder(self):
        import subprocess
        pdf_core.ensure_dirs()
        subprocess.run(["open", str(pdf_core.library_dir())])
        return _ok()

    def delete(self, filenames):
        """Move PDFs to trash; returns the removed entries for undo."""
        deleted, errors = [], []
        for filename in filenames:
            try:
                deleted.append(pdf_core.delete_pdf(filename))
            except PDFError as e:
                errors.append(str(e))
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

    # ------------------------------------------------------------- updates

    def check_updates(self):
        try:
            update = updater.check_for_update()
        except updater.UpdateError as e:
            return _err(e)
        if update is None:
            return _ok(update=None)
        return _ok(update={"version": update["version"], "notes": update["notes"][:500]},
                   _raw=update)

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
