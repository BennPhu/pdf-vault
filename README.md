# PDF Vault

A local drag-and-drop desktop app for collecting PDFs. Drop PDFs into the window and they are:

1. Copied into a `data/library/` folder (your individual PDF library)
2. Appended to a single growing `data/master.pdf`
3. Recorded in `data/index.json` (filename, date added, page count, size)

Also includes **Merge** (combine selected PDFs into one new file) and **Split** (separate a PDF into individual pages or a page range).

Everything runs fully locally — no internet, no server.

## Install

```bash
cd pdf-vault
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

- Drag PDFs onto the drop zone (or click **+ Add PDFs** to use a file picker).
- Select entries in the library list, then use **Merge Selected** or **Split Selected**.
- **Open Master PDF** / **Open Library Folder** buttons open the combined file / storage folder.

## Notes

- If drag-and-drop doesn't work on your system (tkinterdnd2 issue), the app falls back automatically and the **+ Add PDFs** button provides the same functionality.
- Known issue: `tkinterdnd2` ships a Tcl 9 binary for macOS arm64 which fails on Tk 8.6 ("incompatible stubs mechanism"). Fix applied here: the Tk 8.6-compatible `tkdnd` binary from the `tkinterdnd2-universal` package was copied into `.venv/.../tkinterdnd2/tkdnd/osx-arm64/`. If you rebuild the venv, repeat that step or just use the file-picker fallback.
- Data lives in `pdf-vault/data/`. Delete that folder to start fresh.
