import shutil
import subprocess

import pytest

from tests.conftest import ROOT

STATIC = ROOT / "app" / "static"


def test_shell_links_assets_and_routes():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/app.css">' in html and '<script src="/app.js"></script>' in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for view in ("VIEWS.new", "VIEWS.batch", "VIEWS.run", "VIEWS.dashboard", "VIEWS.data", "VIEWS.tests", "VIEWS.assumptions"):
        assert view in js


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_app_js_parses():
    subprocess.run(["node", "--check", str(STATIC / "app.js")], check=True)


def test_document_viewer_present():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for name in ("function docViewer", "function wireEvidence", "function compareOriginal", "data-key"):
        assert name in js
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    for cls in (".ev.bad", ".page.scanning", "@keyframes glow"):
        assert cls in css


def test_stage_dot_colour_is_not_overridden_by_base_rule():
    # .dot is declared after the .st-* status colours; a background on it would paint every dot grey.
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    dot_rule = css[css.index(".dot {"):css.index("}", css.index(".dot {"))]
    assert "background" not in dot_rule and ".dot.st-pending" in css


def test_evidence_wired_after_timeline_rows_exist():
    # The evidence table rows live inside the timeline; wiring before it renders leaves them without hover links.
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    run_view = js[js.index("VIEWS.run = "):js.index("// ---------- Dashboard")]
    assert run_view.index('$("#timeline").innerHTML') < run_view.index("wireEvidence(el")


def test_batch_tiles_update_in_place_instead_of_being_rebuilt():
    # Rebuilding every tile on each 400 ms snapshot replays their fade-in animation: the page blinks with the timer.
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    batch_view = js[js.index("VIEWS.batch = "):js.index("// ---------- Live run")]
    assert '$("#tiles").innerHTML' not in batch_view and "tileHtml.get(" in batch_view


def test_uploads_show_progress_and_ignore_a_second_drop():
    # Uploading a dozen invoices takes seconds on a slow link; without feedback the page looks frozen and people drop again.
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    new_view = js[js.index("VIEWS.new = "):js.index("// ---------- Batch")]
    assert "upload.onprogress" in js and "uploading" in new_view and "if (uploading) return" in new_view


def test_pages_draw_from_a_prefetched_cache():
    # Switching pages should not start from a blank screen and wait for the server every time.
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "const CACHE = {}" in js and "function prefetch" in js and "prefetch()" in js
    for path in ("/api/fixtures", "/api/assumptions", "/api/reference"):
        assert f'cachedApi("{path}"' in js
