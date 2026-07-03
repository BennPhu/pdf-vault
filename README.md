# PDF Vault

A local drag-and-drop desktop app for collecting PDFs. Drop PDFs into the window and they are:

1. Copied into a `library/` folder inside your chosen storage location
2. Recorded in `index.json` (filename, date added, page count, size)

Features:

- **Visual preview panel** — click a PDF in the library to see its rendered pages, with ◀/▶ page navigation
- **Merge** — combine selected PDFs into one new file, saved wherever you choose
- **Split** — dialog with live page preview and a from/to page range, offering two actions:
  - *Save Range as One PDF…* — extract e.g. pages 1-10 into a single new file, saved wherever you choose
  - *Split Each Page to Files…* — write each page in the range as its own one-page PDF
- **Create Master PDF…** — combines your whole library into one PDF, only when you ask for it, saved wherever you choose (nothing is generated automatically)
- **Unselect** button (or press `Escape`) to clear the selection and preview
- **Storage folder setup** — on first launch you pick where PDF Vault stores its files; change it anytime via *Change Storage Folder…* (setting saved in `~/.pdf_vault_config.json`)

Everything runs fully locally — no internet, no server.

## Install

```bash
cd pdf-vault
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Double-click **`PDF Vault.command`** in Finder (it creates the venv and installs dependencies automatically on first use).

Or from a terminal:

```bash
.venv/bin/python app.py
```

- On first launch, choose the folder where PDF Vault should store your files.
- Drag PDFs onto the drop zone (or click **+ Add PDFs** to use a file picker).
- Click a library entry to preview it; select entries and use **Merge Selected** or **Split Selected**.
- **Create Master PDF…** builds the combined library PDF on demand; **Open Library Folder** opens the storage folder.

## Notes

- If drag-and-drop doesn't work on your system (tkinterdnd2 issue), the app falls back automatically and the **+ Add PDFs** button provides the same functionality.
- Known issue: `tkinterdnd2` ships a Tcl 9 binary for macOS arm64 which fails on Tk 8.6 ("incompatible stubs mechanism"). Fix applied here: the Tk 8.6-compatible `tkdnd` binary from the `tkinterdnd2-universal` package was copied into `.venv/.../tkinterdnd2/tkdnd/osx-arm64/`. If you rebuild the venv, repeat that step or just use the file-picker fallback.
- Your PDFs live in the storage folder you chose (default `pdf-vault/data/`). Delete `~/.pdf_vault_config.json` to re-run the first-launch setup.
