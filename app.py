"""PDF Vault - entrypoint for the pywebview desktop app.

The UI lives in web/ (HTML/CSS/JS); Python logic is exposed via api.Api.
The legacy tkinter UI is kept in app_tk.py for one release as a fallback.
"""

import sys
from pathlib import Path

import webview

from api import Api
from pdf_core import __version__


def web_dir():
    """Locate the web assets both in dev and inside a PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "web"
    return Path(__file__).resolve().parent / "web"


def main():
    api = Api()
    window = webview.create_window(
        f"PDF Vault {__version__}",
        str(web_dir() / "index.html"),
        js_api=api,
        width=1080,
        height=720,
        min_size=(820, 560),
    )
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    main()
