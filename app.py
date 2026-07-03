"""PDF Vault - local drag-and-drop PDF collector with preview, merge/split tools."""

import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import fitz

import pdf_core
from pdf_core import PDFError

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


class PreviewPanel(ttk.Frame):
    """Renders PDF pages as images with prev/next navigation."""

    def __init__(self, parent, width=340, height=440):
        super().__init__(parent)
        self.doc = None
        self.page_index = 0
        self.render_width = width
        self.render_height = height
        self._photo = None

        self.canvas = tk.Canvas(self, bg="#e8e8e8", highlightthickness=1,
                                highlightbackground="#ccc")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.render())

        nav = ttk.Frame(self)
        nav.pack(fill="x", pady=4)
        self.prev_btn = ttk.Button(nav, text="\u25c0", width=3, command=self.prev_page)
        self.prev_btn.pack(side="left", padx=4)
        self.page_label = ttk.Label(nav, text="No PDF selected", anchor="center")
        self.page_label.pack(side="left", expand=True, fill="x")
        self.next_btn = ttk.Button(nav, text="\u25b6", width=3, command=self.next_page)
        self.next_btn.pack(side="right", padx=4)

    def load(self, pdf_path):
        self.clear()
        try:
            self.doc = fitz.open(str(pdf_path))
            self.page_index = 0
            self.render()
        except Exception as e:
            self.page_label.config(text=f"Preview failed: {e}")

    def clear(self):
        if self.doc is not None:
            self.doc.close()
            self.doc = None
        self._photo = None
        self.canvas.delete("all")
        self.page_label.config(text="No PDF selected")

    def prev_page(self):
        if self.doc and self.page_index > 0:
            self.page_index -= 1
            self.render()

    def next_page(self):
        if self.doc and self.page_index < len(self.doc) - 1:
            self.page_index += 1
            self.render()

    def goto(self, page_number):
        """Jump to a 1-based page number."""
        if self.doc and 1 <= page_number <= len(self.doc):
            self.page_index = page_number - 1
            self.render()

    def render(self):
        self.canvas.delete("all")
        if self.doc is None:
            return
        page = self.doc[self.page_index]
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        zoom = min(cw / page.rect.width, ch / page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        self._photo = tk.PhotoImage(data=pix.tobytes("ppm"))
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo)
        self.page_label.config(text=f"Page {self.page_index + 1} of {len(self.doc)}")


class BaseSplitDialog(tk.Toplevel):
    """Shared dialog: live page preview + from/to range fields + one action."""

    dialog_title = "Split"
    action_label = "OK"

    def __init__(self, parent, pdf_path, status_cb):
        super().__init__(parent)
        self.pdf_path = Path(pdf_path)
        self.status_cb = status_cb
        self.title(f"{self.dialog_title} \u2014 {self.pdf_path.name}")
        self.geometry("460x560")
        self.transient(parent)
        self.grab_set()

        try:
            self.total_pages = pdf_core.page_count(self.pdf_path)
        except PDFError as e:
            messagebox.showerror(self.dialog_title, str(e), parent=parent)
            self.destroy()
            return

        self.preview = PreviewPanel(self)
        self.preview.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        self.preview.load(self.pdf_path)

        range_frame = ttk.Frame(self)
        range_frame.pack(pady=4)
        ttk.Label(range_frame, text="From page:").pack(side="left")
        self.start_var = tk.StringVar(value="1")
        start_spin = ttk.Spinbox(range_frame, from_=1, to=self.total_pages, width=5,
                                 textvariable=self.start_var)
        start_spin.pack(side="left", padx=(4, 12))
        ttk.Label(range_frame, text="To page:").pack(side="left")
        self.end_var = tk.StringVar(value=str(self.total_pages))
        end_spin = ttk.Spinbox(range_frame, from_=1, to=self.total_pages, width=5,
                               textvariable=self.end_var)
        end_spin.pack(side="left", padx=4)
        self.start_var.trace_add("write", lambda *a: self._jump(self.start_var))
        self.end_var.trace_add("write", lambda *a: self._jump(self.end_var))

        btns = ttk.Frame(self)
        btns.pack(pady=(4, 10))
        ttk.Button(btns, text=self.action_label,
                   command=self.do_action).pack(side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=6)

    def _jump(self, var):
        try:
            self.preview.goto(int(var.get()))
        except ValueError:
            pass

    def _get_range(self):
        try:
            return int(self.start_var.get()), int(self.end_var.get())
        except ValueError:
            messagebox.showerror(self.dialog_title, "Page numbers must be integers.", parent=self)
            return None

    def do_action(self):
        raise NotImplementedError


class SplitRangeDialog(BaseSplitDialog):
    """Split Selected: extract pages x-y into one new PDF file."""

    dialog_title = "Split \u2014 pages x to y into one PDF"
    action_label = "Save as One PDF\u2026"

    def do_action(self):
        page_range = self._get_range()
        if page_range is None:
            return
        start, end = page_range
        output = filedialog.asksaveasfilename(
            title="Save extracted pages as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"{self.pdf_path.stem}_pages_{start}-{end}.pdf",
            initialdir=pdf_core.last_output_dir(),
            parent=self,
        )
        if not output:
            return
        try:
            pdf_core.extract_pages(self.pdf_path, start, end, output)
            pdf_core.set_last_output_dir(Path(output).parent)
            self.status_cb(f"Saved pages {start}-{end} to {output}")
            self.destroy()
        except PDFError as e:
            messagebox.showerror("Split failed", str(e), parent=self)


class IndividualSplitsDialog(BaseSplitDialog):
    """Individual Splits: one file per page in the chosen range."""

    dialog_title = "Individual Splits \u2014 one file per page"
    action_label = "Split to Files\u2026"

    def do_action(self):
        page_range = self._get_range()
        if page_range is None:
            return
        start, end = page_range
        output_dir = filedialog.askdirectory(
            title="Choose folder for the one-page files",
            initialdir=pdf_core.last_output_dir(),
            parent=self,
        )
        if not output_dir:
            return
        try:
            written = pdf_core.split_pdf(self.pdf_path, output_dir, start, end)
            pdf_core.set_last_output_dir(output_dir)
            self.status_cb(f"Split into {len(written)} one-page file(s) in {output_dir}")
            self.destroy()
        except PDFError as e:
            messagebox.showerror("Split failed", str(e), parent=self)


class PDFVaultApp:
    def __init__(self, root):
        self.root = root
        root.title("PDF Vault")
        root.geometry("980x620")
        root.minsize(760, 500)

        self.first_run_setup()

        # Drop zone
        self.drop_zone = tk.Label(
            root,
            text="Drop PDFs here" if DND_AVAILABLE else "Drag-and-drop unavailable\nUse '+ Add PDFs' below",
            relief="groove",
            borderwidth=2,
            font=("Helvetica", 16),
            fg="#555",
            height=4,
        )
        self.drop_zone.pack(fill="x", padx=12, pady=(12, 6))
        if DND_AVAILABLE:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self.on_drop)

        # Top buttons
        top_btns = ttk.Frame(root)
        top_btns.pack(fill="x", padx=12, pady=(0, 6))
        ttk.Button(top_btns, text="+ Add PDFs", command=self.add_via_dialog).pack(side="left")
        ttk.Button(top_btns, text="Unselect", command=self.unselect).pack(side="left", padx=6)
        ttk.Button(top_btns, text="Change Storage Folder\u2026", command=self.change_storage).pack(side="right")

        # Two-pane: library list | preview
        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=12, pady=6)

        lib_frame = ttk.LabelFrame(paned, text="Library")
        paned.add(lib_frame, weight=3)

        columns = ("filename", "added", "pages", "size")
        self.tree = ttk.Treeview(lib_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("filename", text="File")
        self.tree.heading("added", text="Added")
        self.tree.heading("pages", text="Pages")
        self.tree.heading("size", text="Size")
        self.tree.column("filename", width=220)
        self.tree.column("added", width=140)
        self.tree.column("pages", width=55, anchor="e")
        self.tree.column("size", width=75, anchor="e")
        scrollbar = ttk.Scrollbar(lib_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        preview_frame = ttk.LabelFrame(paned, text="Preview")
        paned.add(preview_frame, weight=2)
        self.preview = PreviewPanel(preview_frame)
        self.preview.pack(fill="both", expand=True, padx=6, pady=6)

        # Action buttons
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill="x", padx=12, pady=6)
        ttk.Button(btn_frame, text="Merge Selected", command=self.merge_selected).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Split Selected", command=self.split_selected).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Individual Splits", command=self.individual_splits).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Create Master PDF\u2026", command=self.create_master).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Open Library Folder", command=self.open_library).pack(side="left", padx=6)

        # Status bar
        self.status = tk.StringVar(value=f"Storage: {pdf_core.storage_dir()}")
        status_bar = ttk.Label(root, textvariable=self.status, relief="sunken", anchor="w")
        status_bar.pack(fill="x", side="bottom")

        root.bind("<Escape>", lambda e: self.unselect())

        pdf_core.ensure_dirs()
        self.refresh_library()

    # ------------------------------------------------------------------ setup

    def first_run_setup(self):
        if pdf_core.is_configured():
            return
        messagebox.showinfo(
            "Welcome to PDF Vault",
            "Choose the folder where PDF Vault will store your PDFs\n"
            "(library, master.pdf, and index).",
            parent=self.root,
        )
        chosen = filedialog.askdirectory(
            title="Choose PDF Vault storage folder",
            initialdir=str(pdf_core.DEFAULT_DATA_DIR.parent),
            parent=self.root,
        )
        if chosen:
            pdf_core.set_storage_dir(chosen)
        else:
            pdf_core.set_storage_dir(pdf_core.DEFAULT_DATA_DIR)
            messagebox.showinfo(
                "PDF Vault",
                f"No folder chosen \u2014 using default:\n{pdf_core.DEFAULT_DATA_DIR}",
                parent=self.root,
            )

    def change_storage(self):
        chosen = filedialog.askdirectory(
            title="Choose new PDF Vault storage folder",
            initialdir=str(pdf_core.storage_dir()),
            parent=self.root,
        )
        if not chosen:
            return
        pdf_core.set_storage_dir(chosen)
        self.refresh_library()
        self.preview.clear()
        self.set_status(f"Storage: {pdf_core.storage_dir()}")

    # ------------------------------------------------------------------ utils

    def set_status(self, msg):
        self.status.set(msg)

    def refresh_library(self):
        self.tree.delete(*self.tree.get_children())
        for entry in pdf_core.load_index():
            size_kb = entry.get("size_bytes", 0) / 1024
            self.tree.insert(
                "",
                "end",
                values=(
                    entry["filename"],
                    entry.get("added", ""),
                    entry.get("pages", ""),
                    f"{size_kb:,.0f} KB",
                ),
            )

    def selected_paths(self):
        paths = []
        for item in self.tree.selection():
            filename = self.tree.item(item, "values")[0]
            paths.append(pdf_core.library_path(filename))
        return paths

    def unselect(self):
        self.tree.selection_remove(self.tree.selection())
        self.preview.clear()
        self.set_status("Selection cleared.")

    def on_select(self, event=None):
        paths = self.selected_paths()
        if len(paths) == 1 and paths[0].exists():
            self.preview.load(paths[0])
        elif not paths:
            self.preview.clear()

    # ---------------------------------------------------------------- actions

    def on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        self.add_pdfs(paths)

    def add_via_dialog(self):
        paths = filedialog.askopenfilenames(
            title="Select PDFs to add", filetypes=[("PDF files", "*.pdf")]
        )
        if paths:
            self.add_pdfs(paths)

    def add_pdfs(self, paths):
        added, errors = 0, []
        for p in paths:
            try:
                entry = pdf_core.add_pdf(p)
                added += 1
                self.set_status(f"Added {entry['filename']} ({entry['pages']} pages).")
            except PDFError as e:
                errors.append(str(e))
        self.refresh_library()
        if errors:
            messagebox.showwarning("Some files failed", "\n".join(errors))
        if added:
            self.set_status(f"Added {added} PDF(s) to the library.")

    def merge_selected(self):
        paths = self.selected_paths()
        if len(paths) < 2:
            messagebox.showinfo("Merge", "Select at least two PDFs in the library list.")
            return
        output = filedialog.asksaveasfilename(
            title="Save merged PDF as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile="merged.pdf",
            initialdir=pdf_core.last_output_dir(),
        )
        if not output:
            return
        try:
            pdf_core.merge_pdfs(paths, output)
            pdf_core.set_last_output_dir(Path(output).parent)
            self.set_status(f"Merged {len(paths)} PDFs into {output}")
        except PDFError as e:
            messagebox.showerror("Merge failed", str(e))

    def split_selected(self):
        """Extract pages x-y of the selected PDF into one new PDF."""
        paths = self.selected_paths()
        if len(paths) != 1:
            messagebox.showinfo("Split", "Select exactly one PDF in the library list.")
            return
        SplitRangeDialog(self.root, paths[0], self.set_status)

    def individual_splits(self):
        """Split pages of the selected PDF into one file per page."""
        paths = self.selected_paths()
        if len(paths) != 1:
            messagebox.showinfo("Individual Splits", "Select exactly one PDF in the library list.")
            return
        IndividualSplitsDialog(self.root, paths[0], self.set_status)

    def create_master(self):
        """Build the combined master PDF only when the user asks for it."""
        output = filedialog.asksaveasfilename(
            title="Save master PDF as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile="master.pdf",
            initialdir=pdf_core.last_output_dir(),
        )
        if not output:
            return
        try:
            pdf_core.build_master(output)
            pdf_core.set_last_output_dir(Path(output).parent)
            self.set_status(f"Master PDF created: {output}")
            if messagebox.askyesno("Master PDF", "Master PDF created. Open it now?"):
                subprocess.run(["open", output])
        except PDFError as e:
            messagebox.showerror("Create Master failed", str(e))

    def open_library(self):
        pdf_core.ensure_dirs()
        subprocess.run(["open", str(pdf_core.library_dir())])


def main():
    global DND_AVAILABLE
    root = None
    if DND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
        except RuntimeError:
            DND_AVAILABLE = False
    if root is None:
        root = tk.Tk()
    PDFVaultApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
