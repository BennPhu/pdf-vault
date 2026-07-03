import pytest
from pypdf import PdfWriter

import pdf_core
from api import Api


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_core, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(pdf_core, "_config", None)
    pdf_core.set_storage_dir(tmp_path / "vault")
    return tmp_path


def make_pdf(directory, name, pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    path = directory / name
    with open(path, "wb") as f:
        writer.write(f)
    return path


def test_get_state(vault):
    api = Api()
    state = api.get_state()
    assert state["ok"] and state["configured"]
    assert state["version"] == pdf_core.__version__


def test_add_paths_and_list(vault):
    api = Api()
    res = api.add_paths([str(make_pdf(vault, "a.pdf", 2))])
    assert res["ok"] and res["added"] == ["a.pdf"] and res["errors"] == []

    listing = api.list_library()
    assert listing["ok"] and len(listing["entries"]) == 1
    entry = listing["entries"][0]
    assert entry["pages"] == 2
    assert entry["thumb"]  # base64 thumbnail present
    assert not entry["missing"]


def test_add_paths_collects_errors(vault):
    bad = vault / "bad.txt"
    bad.write_text("nope")
    api = Api()
    res = api.add_paths([str(bad)])
    assert res["ok"] and res["added"] == [] and len(res["errors"]) == 1


def test_render_page(vault):
    api = Api()
    api.add_paths([str(make_pdf(vault, "doc.pdf", 3))])
    res = api.render_page("doc.pdf", 2)
    assert res["ok"] and res["total"] == 3 and res["page"] == 2
    assert len(res["image"]) > 100


def test_render_page_out_of_range(vault):
    api = Api()
    api.add_paths([str(make_pdf(vault, "doc.pdf", 1))])
    res = api.render_page("doc.pdf", 5)
    assert not res["ok"]


def test_merge_requires_two(vault):
    api = Api()
    res = api.merge(["only-one.pdf"])
    assert not res["ok"]


def test_render_page_b64_core(vault):
    src = make_pdf(vault, "r.pdf", 2)
    data, total = pdf_core.render_page_b64(src, 1, max_px=100)
    assert total == 2 and len(data) > 100
    with pytest.raises(pdf_core.PDFError):
        pdf_core.render_page_b64(src, 99)
