"""PDF Vault - local drag-and-drop PDF collector with merge/split tools."""

import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import pdf_core
from pdf_core import PDFError

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


class PDFVaultApp:
    def __init__(self, root):
        self.root = root
        root.title("PDF Vault")
        root.geometry("640x560")
        root.minsize(520, 460)

        # Drop zone
        self.drop_zone = tk.Label(
            root,
            text="Drop PDFs here" if DND_AVAILABLE else "Drag-and-drop unavailable\nUse '+ Add PDFs' below",
            relief="groove",
            borderwidth=2,
            font=("Helvetica", 16),
            fg="#555",
            height=5,
        )
        self.drop_zone.pack(fill="x", padx=12, pady=(12, 6))
        if DND_AVAILABLE:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self.on_drop)

        # Add button
        add_btn = ttk.Button(root, text="+ Add PDFs", command=self.add_via_dialog)
        add_btn.pack(padx=12, pady=(0, 6))

        # Library list
        lib_frame = ttk.LabelFrame(root, text="Library")
        lib_frame.pack(fill="both", expand=True, padx=12, pady=6)

        columns = ("filename", "added", "pages", "size")
        self.tree = ttk.Treeview(lib_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("filename", text="File")
        self.tree.heading("added", text="Added")
        self.tree.heading("pages", text="Pages")
        self.tree.heading("size", text="Size")
        self.tree.column("filename", width=240)
        self.tree.column("added", width=150)
        self.tree.column("pages", width=60, anchor="e")
        self.tree.column("size", width=80, anchor="e")
        scrollbar = ttk.Scrollbar(lib_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Action buttons
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill="x", padx=12, pady=6)
        ttk.Button(btn_frame, text="Merge Selected", command=self.merge_selected).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Split Selected", command=self.split_selected).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Open Master PDF", command=self.open_master).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Open Library Folder", command=self.open_library).pack(side="left", padx=6)

        # Status bar
        self.status = tk.StringVar(value="Ready.")
        status_bar = ttk.Label(root, textvariable=self.status, relief="sunken", anchor="w")
        status_bar.pack(fill="x", side="bottom")

        pdf_core.ensure_dirs()
        self.refresh_library()

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
            self.set_status(f"Added {added} PDF(s). Master updated.")

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
        )
        if not output:
            return
        try:
            pdf_core.merge_pdfs(paths, output)
            self.set_status(f"Merged {len(paths)} PDFs into {output}")
        except PDFError as e:
            messagebox.showerror("Merge failed", str(e))

    def split_selected(self):
        paths = self.selected_paths()
        if len(paths) != 1:
            messagebox.showinfo("Split", "Select exactly one PDF in the library list.")
            return
        source = paths[0]
        page_range = simpledialog.askstring(
            "Split PDF",
            "Page range to split (e.g. 1-5), or leave blank for all pages:",
            parent=self.root,
        )
        start = end = None
        if page_range:
            try:
                if "-" in page_range:
                    start_s, end_s = page_range.split("-", 1)
                    start, end = int(start_s), int(end_s)
                else:
                    start = end = int(page_range)
            except ValueError:
                messagebox.showerror("Split", f"Invalid page range: {page_range}")
                return
        output_dir = filedialog.askdirectory(title="Choose folder for split pages")
        if not output_dir:
            return
        try:
            written = pdf_core.split_pdf(source, output_dir, start, end)
            self.set_status(f"Split into {len(written)} page file(s) in {output_dir}")
        except PDFError as e:
            messagebox.showerror("Split failed", str(e))

    def open_master(self):
        if pdf_core.MASTER_PDF.exists():
            subprocess.run(["open", str(pdf_core.MASTER_PDF)])
        else:
            messagebox.showinfo("Master PDF", "No master.pdf yet — add a PDF first.")

    def open_library(self):
        pdf_core.ensure_dirs()
        subprocess.run(["open", str(pdf_core.LIBRARY_DIR)])


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
