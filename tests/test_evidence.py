import asyncio

from fastapi.testclient import TestClient

from app import db, evidence
from app.main import create_app
from app.pipeline import Pipeline
from app.truth import TruthExtractor, extraction_from_truth
from tests.conftest import FIX_DIR, MAN_BY_FILE, MANIFEST, SEED


def test_locate_in_words_matches_money_multiword_and_split_values():
    pages = [{"width": 600.0, "height": 800.0, "words": [
        ["Sparkle", 10, 10, 40, 10], ["Commercial", 52, 10, 60, 10], ["Cleaning", 114, 10, 50, 10], ["Inc.", 166, 10, 20, 10],
        ["TOTAL", 400, 700, 40, 12], ["$2,145.00", 450, 700, 60, 12], ["Account", 10, 400, 40, 10], ["300", 60, 400, 15, 10],
        ["458", 77, 400, 15, 10], ["817", 94, 400, 15, 10], ["$354.80", 450, 300, 50, 10]]}]
    t = [{"key": "vendor_name", "label": "Vendor", "text": "Sparkle Commercial Cleaning Inc.", "value": "Sparkle Commercial Cleaning Inc."},
         {"key": "total", "label": "Total", "text": "2145.0", "value": 2145.0},
         {"key": "remit_bank_account", "label": "Bank", "text": "300458817", "value": "300458817"},
         {"key": "line:0", "label": "Line 1", "text": "54.80", "value": 54.80}]
    got = {b["key"]: b for b in evidence.locate_in_words(t, pages)}
    assert got["vendor_name"]["box"] == [12, 17, 25, 310]
    assert got["total"]["box"] == [875, 750, 890, 850] and got["total"]["page"] == 1
    assert got["remit_bank_account"]["box"] == [500, 100, 512, 182]
    assert "line:0" not in got  # 54.80 must not match inside 354.80


def test_real_digital_pdf_bank_box_and_flags():
    data = (FIX_DIR / "46_sparkle_bank_details_changed.pdf").read_bytes()
    pages = evidence.pdf_words(data)
    x = extraction_from_truth(MAN_BY_FILE["46_sparkle_bank_details_changed.pdf"]["truth"])
    boxes = {b["key"]: b for b in evidence.locate_in_words(evidence.targets(x), pages)}
    ymin, xmin, ymax, xmax = boxes["remit_bank_account"]["box"]
    assert 560 <= ymin <= 590 and xmin < xmax
    dec = {"reasons": [{"code": "BANK_DETAILS_CHANGED", "severity": "hold"}]}
    assert evidence.flags(dec, x, {}, 2.0)["remit_bank_account"] == "hold"


def test_flags_point_at_offending_lines():
    x = extraction_from_truth(MAN_BY_FILE["37_beverage_unplanned_fuel_surcharge.pdf"]["truth"])
    n = len(x["line_items"])
    details = {"lines": [{"po_sku": "A", "price_diff_pct": 0.0}] * (n - 1) + [{"po_sku": None, "price_diff_pct": None}]}
    f = evidence.flags({"reasons": [{"code": "UNMATCHED_LINE", "severity": "hold"}]}, x, details, 2.0)
    assert f == {f"line:{n - 1}": "hold"}


def test_pipeline_attaches_evidence_digital_and_scanned():
    class Locating(TruthExtractor):
        async def locate(self, *, data, mime, targets):
            return [{"key": t["key"], "box": [100, 100, 120, 300]} for t in targets[:2]]

    world = db.connect()
    db.load_seed(world, SEED)
    p = Pipeline(world, db.connect(), Locating(MANIFEST))
    runs = asyncio.run(p.run_batch([(n, (FIX_DIR / n).read_bytes()) for n in
                                    ("46_sparkle_bank_details_changed.pdf", "14_greenleaf_scan_clean.pdf")]))
    ev = runs[0]["evidence"]
    assert ev["status"] == "ready" and ev["pages"][0]["url"].endswith("/pages/1")
    assert any(b["key"] == "remit_bank_account" for b in ev["boxes"]) and ev["flags"]["remit_bank_account"] == "hold"
    ev2 = runs[1]["evidence"]
    assert ev2["status"] == "ready" and len(ev2["boxes"]) == 2 and ev2["boxes"][0]["page"] == 1


def test_page_image_and_original_endpoints():
    with TestClient(create_app(db_path=":memory:", extractor=TruthExtractor(MANIFEST))) as c:
        r = c.post("/api/batches", data={"fixture": "40_greenleaf_exact_duplicate.pdf"}).json()
        import time
        for _ in range(100):
            run = c.get(f"/api/runs/{r['run_ids'][0]}").json()
            if run["phase"] == "done":
                break
            time.sleep(0.1)
        png = c.get(f"/api/runs/{r['run_ids'][0]}/pages/1")
        assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
        orig = c.get("/api/originals/INV-GL-2207").json()
        assert orig["url"].endswith("/page") and any(b["key"] == "invoice_number" for b in orig["boxes"])
        assert c.get(orig["url"]).content[:8] == b"\x89PNG\r\n\x1a\n"
        assert c.get("/api/originals/NOPE").status_code == 404


def test_credit_memo_shows_its_title_and_negative_total_in_red():
    # 58 prints amounts as -$227.39; a credit memo is held because of what the document is, so the title is the evidence.
    world = db.connect()
    db.load_seed(world, SEED)
    run = asyncio.run(Pipeline(world, db.connect(), TruthExtractor(MANIFEST)).run_batch(
        [("58_packright_credit_memo.pdf", (FIX_DIR / "58_packright_credit_memo.pdf").read_bytes())]))[0]
    ev = run["evidence"]
    keys = {b["key"] for b in ev["boxes"]}
    assert {"total", "document_type"} <= keys
    assert ev["flags"]["document_type"] == "hold" and ev["flags"]["total"] == "hold"
    title = [b for b in ev["boxes"] if b["key"] == "document_type"]
    assert len(title) == 1 and title[0]["box"][0] < 150  # the heading at the top, not the "Credit Memo #" label
