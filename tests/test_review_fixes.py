"""Regression tests for the final-review findings (each one reproduces the reported failure)."""
import asyncio
import time

from fastapi.testclient import TestClient

import app.main as main_mod
from app import db, evidence
from app.main import create_app
from app.pipeline import Pipeline
from app.truth import TruthExtractor
from tests.conftest import FIX_DIR, MANIFEST, ROOT, SEED


def pipeline(extractor, store=None):
    world = db.connect()
    db.load_seed(world, SEED)
    return Pipeline(world, store or db.connect(), extractor)


def files(*names):
    return [(n, (FIX_DIR / n).read_bytes()) for n in names]


def codes(run):
    return [r["code"] for r in run["decision"]["reasons"]]


def test_crash_while_reading_keeps_upload_order():
    class Broken(TruthExtractor):
        async def extract(self, *, data, mime, layout_text, filename):
            if filename.startswith("04_"):
                await asyncio.sleep(0.6)  # the first invoice is slow to read
            x = await super().extract(data=data, mime=mime, layout_text=layout_text, filename=filename)
            if filename.startswith("01_"):
                del x["line_items"]  # malformed read: validation raises inside phase A
            return x

    r04, r01, r27 = asyncio.run(pipeline(Broken(MANIFEST)).run_batch(
        files("04_northgate_blanket_within_balance.pdf", "01_greenleaf_clean.pdf", "27_northgate_split_second_in_batch.pdf")))
    assert r01["decision"]["decision"] == "HOLD" and codes(r01) == ["EXTRACTION_FAILED"]
    assert r04["decision"]["decision"] == "APPROVE"
    assert r27["decision"]["decision"] == "HOLD" and "PO_OVERRUN" in codes(r27)


def test_hung_reader_and_locator_time_out(monkeypatch):
    monkeypatch.setenv("AI_TIMEOUT", "0.3")

    class Hung(TruthExtractor):
        async def extract(self, *, data, mime, layout_text, filename):
            if filename.startswith("02_"):
                await asyncio.sleep(30)
            return await super().extract(data=data, mime=mime, layout_text=layout_text, filename=filename)

        async def locate(self, *, data, mime, targets):
            await asyncio.sleep(30)

    t0 = time.time()
    r02, r14 = asyncio.run(pipeline(Hung(MANIFEST)).run_batch(files("02_packright_clean.pdf", "14_greenleaf_scan_clean.pdf")))
    assert time.time() - t0 < 10
    assert r02["decision"]["decision"] == "HOLD" and codes(r02) == ["EXTRACTION_FAILED"]
    assert r14["decision"]["decision"] == "APPROVE" and r14["evidence"]["status"] == "failed"


def test_page_rendering_never_delays_the_decision_and_is_done_once(monkeypatch):
    calls = {"n": 0}
    real = evidence.render_pages

    def slow_render(data):
        calls["n"] += 1
        time.sleep(1.0)
        return real(data)

    monkeypatch.setattr(evidence, "render_pages", slow_render)
    store = db.connect()
    run = asyncio.run(pipeline(TruthExtractor(MANIFEST), store).run_batch(files("01_greenleaf_clean.pdf")))[0]
    assert run["decided_at"] - run["created"] < 0.8 and run["evidence"]["pages"]
    asyncio.run(pipeline(TruthExtractor(MANIFEST), store).run_batch(files("01_greenleaf_clean.pdf")))
    assert calls["n"] == 1


def test_overlay_failures_never_change_the_decision(monkeypatch):
    def broken_render(data):
        raise RuntimeError("renderer crashed")

    monkeypatch.setattr(evidence, "render_pages", broken_render)
    run = asyncio.run(pipeline(TruthExtractor(MANIFEST)).run_batch(files("01_greenleaf_clean.pdf")))[0]
    assert run["decision"]["decision"] == "APPROVE" and run["phase"] == "done"
    assert run["evidence"]["status"] == "none" and run["evidence"]["pages"] == []


def test_batch_counters_never_exceed_the_total():
    class SlowWriter(TruthExtractor):
        async def summarize(self, **kw):
            await asyncio.sleep(1.0)
            return await super().summarize(**kw)

    async def main():
        p = pipeline(SlowWriter(MANIFEST))
        b = await p.submit(files("48_rapidlinen_blocked_vendor.pdf"))
        for _ in range(200):
            snap = p.batch_snapshot(b["id"])
            if snap["decided"] == 1:
                break
            await asyncio.sleep(0.02)
        await p.wait(b["id"])
        return snap

    snap = asyncio.run(main())
    assert not snap["finished"] and sum(snap["counts"].values()) == snap["total"]


def test_api_filenames_upload_limits_and_original_paths(monkeypatch):
    with TestClient(create_app(db_path=":memory:", extractor=TruthExtractor(MANIFEST))) as c:
        name = "Screenshot 2026-10-10 at 10.15.32 AM.jpg"
        data = (FIX_DIR / "17_dairy_phone_photo.jpg").read_bytes()
        r = c.post("/api/batches", files=[("files", (name, data, "image/jpeg"))]).json()
        got = c.get(f"/api/runs/{r['run_ids'][0]}/file")
        assert got.status_code == 200 and got.content[:3] == b"\xff\xd8\xff"

        monkeypatch.setattr(main_mod, "MAX_TOTAL_BYTES", 1000)
        two = [("files", ("a.pdf", b"%PDF-" + b"x" * 600, "application/pdf")),
               ("files", ("b.pdf", b"%PDF-" + b"x" * 600, "application/pdf"))]
        assert c.post("/api/batches", files=two).status_code == 400

        assert c.get("/api/originals/..%5Cinvoices%5C01_greenleaf_clean").status_code == 404
        assert c.get("/api/originals/..%5Cinvoices%5C01_greenleaf_clean/page").status_code == 404


def test_ui_stops_reconnecting_to_a_vanished_run_and_tiles_stop_reading():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "e.data !== undefined" in js and "onGone" in js
    assert 'r.vendor || (r.decision ? "—" : "Reading...")' in js


def test_duplicate_names_the_original_file():
    store = db.connect()
    p = pipeline(TruthExtractor(MANIFEST), store)
    first = asyncio.run(p.run_batch(files("55_packright_tax_overcharged.pdf")))[0]
    again = asyncio.run(p.run_batch(files("55_packright_tax_overcharged.pdf")))[0]
    orig = again["stages"]["duplicates"]["details"]["original"]
    assert codes(again)[0] == "DUPLICATE" and orig["run_id"] == first["id"]
    assert orig["filename"] == "55_packright_tax_overcharged.pdf" and orig["processed_at"] == first["created"]


def test_po_overrun_lists_what_was_billed_before():
    # In a batch, 04 ($9,000) is approved first on the same blanket PO; 26 must show where its $47,000 came from.
    r04, r26 = asyncio.run(pipeline(TruthExtractor(MANIFEST)).run_batch(
        files("04_northgate_blanket_within_balance.pdf", "26_northgate_po_overrun.pdf")))
    det = r26["stages"]["three_way"]["details"]
    assert det["billed_before"] == 47000.0
    by = {b["invoice_number"]: b for b in det["billed_by"]}
    assert len(det["billed_by"]) == 3 and {"NG-0301", "NG-0302"} <= set(by)
    assert sum(b["amount"] for b in det["billed_by"]) == det["billed_before"]
    mine = [b for b in det["billed_by"] if b.get("run_id") == r04["id"]]
    assert len(mine) == 1 and mine[0]["filename"] == "04_northgate_blanket_within_balance.pdf" and mine[0]["amount"] == 9000.0
    assert by["NG-0301"]["status"] == "paid" and by["NG-0301"].get("filename") is None
