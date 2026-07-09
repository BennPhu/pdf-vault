"""PDF Vault - entrypoint for the pywebview desktop app.

The UI lives in web/ (HTML/CSS/JS); Python logic is exposed via api.Api.
The legacy tkinter UI is kept in app_tk.py for one release as a fallback.
"""

import json
import sys
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from api import Api
from pdf_core import __version__


def web_dir():
    """Locate the web assets both in dev and inside a PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "web"
    return Path(__file__).resolve().parent / "web"


def bind_drag_drop(window, api):
    """Native drag & drop: file paths are only exposed on the Python side.

    JS drop events cannot see real filesystem paths on macOS, so we handle
    the drop here via pywebview's DOM API and push the result back to JS.
    """

    def on_drop(e):
        files = e.get("dataTransfer", {}).get("files", [])
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if not paths:
            return
        result = api.add_paths(paths)
        try:
            window.evaluate_js(
                f"window.onNativeDrop && window.onNativeDrop({json.dumps(result)})")
        except Exception:
            pass  # JS fallback in app.js refreshes the library on drop anyway

    def on_drag(e):
        pass  # prevent_default is what matters here

    window.dom.document.events.dragover += DOMEventHandler(on_drag, True, True)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)


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
    webview.start(bind_drag_drop, (window, api))


if __name__ == "__main__":
    main()
