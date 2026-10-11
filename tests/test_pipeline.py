import asyncio
from datetime import date

from app import db
from app.pipeline import Pipeline
from app.truth import TruthExtractor
from tests.conftest import FIX_DIR, MANIFEST, SEED

TODAY = date(2026, 10, 10)


def world_pipeline(extractor=None):
    world = db.connect()
    db.load_seed(world, SEED)
    return Pipeline(world, db.connect(), extractor or TruthExtractor(MANIFEST), today=TODAY)


def files(*names):
    return [(n, (FIX_DIR / n).read_bytes()) for n in names]


def codes(run):
    return [r["code"] for r in run["decision"]["reasons"]]


def check(run, expected):
    assert run["decision"]["decision"] == expected["decision"], (run["filename"], run["decision"])
    assert set(expected["reasons"]) <= set(codes(run)), (run["filename"], codes(run))


def test_every_fixture_alone_matches_the_answer_key():
    async def one(m):
        return (await world_pipeline().run_batch(files(m["file"])))[0], m

    async def main():
        return await asyncio.gather(*(one(m) for m in MANIFEST))

    for run, m in asyncio.run(main()):
        check(run, m["expected"]["alone"])
        assert run["phase"] == "done" and all(s["status"] != "pending" for s in run["stages"].values())


def test_whole_folder_as_one_batch_matches_in_batch_answers():
    ordered = sorted(MANIFEST, key=lambda m: m["id"])
    runs = asyncio.run(world_pipeline().run_batch(files(*[m["file"] for m in ordered])))
    for run, m in zip(runs, ordered):
        check(run, m["expected"]["in_batch"])


def test_decisions_follow_upload_order_under_random_timing():
    slow = TruthExtractor(MANIFEST, delay=(0.0, 0.05))
    a, b = "04_northgate_blanket_within_balance.pdf", "27_northgate_split_second_in_batch.pdf"
    for _ in range(20):
        r1, r2 = asyncio.run(world_pipeline(slow).run_batch(files(a, b)))
        assert (r1["decision"]["decision"], r2["decision"]["decision"]) == ("APPROVE", "HOLD")
        assert "PO_OVERRUN" in codes(r2)
    r1, r2 = asyncio.run(world_pipeline(slow).run_batch(files(b, a)))
    assert (r1["decision"]["decision"], r2["decision"]["decision"]) == ("APPROVE", "HOLD")


def test_random_document_is_rejected_not_crashed():
    class Menu(TruthExtractor):  # an "other" document with a readable name and no invoice fields
        async def extract(self, *, data, mime, layout_text, filename):
            x = await super().extract(data=data, mime=mime, layout_text=layout_text, filename=filename)
            x["fields"]["vendor_name"] = {"value": "Lou's Diner", "confidence": "high", "source_text": "Lou's Diner"}
            return x

    p = world_pipeline(Menu(MANIFEST))
    before = len(db.load_ref(p.world)["ledger"])
    run = asyncio.run(p.run_batch([("menu.pdf", (FIX_DIR / "01_greenleaf_clean.pdf").read_bytes())]))[0]
    assert run["decision"]["decision"] == "REJECT" and run["decision"]["primary"]["code"] == "NOT_AN_INVOICE"
    assert len(db.load_ref(p.world)["ledger"]) == before
    # nothing readable at all (the offline extractor's answer for an unknown file): the type is a guess, so HOLD
    run = asyncio.run(world_pipeline().run_batch([("blank.pdf", (FIX_DIR / "01_greenleaf_clean.pdf").read_bytes())]))[0]
    assert run["decision"]["decision"] == "HOLD" and run["decision"]["primary"]["code"] == "LOW_CONFIDENCE_EXTRACTION"
    assert "NOT_AN_INVOICE" not in codes(run)


def test_unsupported_and_empty_files_hold():
    runs = asyncio.run(world_pipeline().run_batch([("notes.docx", b"PK\x03\x04 word"), ("empty.pdf", b"")]))
    for run in runs:
        assert run["decision"]["decision"] == "HOLD" and codes(run) == ["UNREADABLE_FILE"]
        assert run["stages"]["vendor"]["status"] == "skip"


def test_extraction_failure_does_not_block_batch():
    class Flaky(TruthExtractor):
        async def extract(self, *, data, mime, layout_text, filename):
            if filename.startswith("02_"):
                raise RuntimeError("503 service unavailable")
            return await super().extract(data=data, mime=mime, layout_text=layout_text, filename=filename)

    r1, r2 = asyncio.run(world_pipeline(Flaky(MANIFEST)).run_batch(files("02_packright_clean.pdf", "01_greenleaf_clean.pdf")))
    assert r1["decision"]["decision"] == "HOLD" and codes(r1) == ["EXTRACTION_FAILED"]
    assert r2["decision"]["decision"] == "APPROVE"


def test_identical_file_twice_in_batch():
    r1, r2 = asyncio.run(world_pipeline().run_batch(files("01_greenleaf_clean.pdf", "01_greenleaf_clean.pdf")))
    assert r1["decision"]["decision"] == "APPROVE"
    assert r2["decision"]["decision"] == "REJECT" and "DUPLICATE" in codes(r2)


def test_batch_snapshot_counts():
    async def main():
        p = world_pipeline()
        b = await p.submit(files("01_greenleaf_clean.pdf", "48_rapidlinen_blocked_vendor.pdf"))
        await p.wait(b["id"])
        return p.batch_snapshot(b["id"])

    snap = asyncio.run(main())
    assert snap["finished"] and snap["counts"]["approved"] == 1 and snap["counts"]["rejected"] == 1
    assert [r["code"] for r in snap["runs"]] == [None, "VENDOR_BLOCKED"] and snap["manual_minutes"] == 24


class Misread(TruthExtractor):
    """Drops one of the repeated 7s in file 19's account (what Gemini did on a downsampled scan); the second,
    narrow read returns `second`."""

    def __init__(self, second):
        super().__init__(MANIFEST)
        self.second, self.rereads = second, 0

    async def extract(self, *, data, mime, layout_text, filename):
        x = await super().extract(data=data, mime=mime, layout_text=layout_text, filename=filename)
        x["fields"]["remit_bank_account"]["value"] = "153007742"
        return x

    async def reread_bank(self, *, data, mime, filename):
        self.rereads += 1
        return {"account": self.second, "routing": None, "digit_count": None, "source_text": self.second}


def test_bank_reread_clears_a_misread_but_never_a_real_change():
    run = asyncio.run(world_pipeline(Misread("1530077742")).run_batch(files("19_beverage_scan_rotated.pdf")))[0]
    assert run["decision"]["decision"] == "APPROVE"
    rr = run["stages"]["extract"]["details"]["bank_reread"]
    assert rr["first_read"] == "153007742" and rr["second_read"] == "1530077742" and rr["cleared"] is True
    assert "matches the vendor master" in run["stages"]["extract"]["summary"]

    ex = Misread("153007742")
    run = asyncio.run(world_pipeline(ex).run_batch(files("19_beverage_scan_rotated.pdf")))[0]
    assert run["decision"]["decision"] == "HOLD" and codes(run) == ["BANK_DETAILS_CHANGED"]
    assert run["stages"]["extract"]["details"]["bank_reread"]["cleared"] is False
    assert "still differs" in run["stages"]["extract"]["summary"] and ex.rereads == 1

    asyncio.run(world_pipeline(ex).run_batch(files("01_greenleaf_clean.pdf")))  # digital: grounded, never re-read
    assert ex.rereads == 1


def test_counts_and_timer_follow_decisions_not_writeups():
    class SlowWriter(TruthExtractor):
        async def summarize(self, **kw):
            await asyncio.sleep(1.0)
            return await super().summarize(**kw)

    async def main():
        p = world_pipeline(SlowWriter(MANIFEST))
        b = await p.submit(files("48_rapidlinen_blocked_vendor.pdf"))
        for _ in range(200):
            snap = p.batch_snapshot(b["id"])
            if snap["decided"] == 1:
                break
            await asyncio.sleep(0.02)
        mid = p.batch_snapshot(b["id"])
        await p.wait(b["id"])
        return mid

    mid = asyncio.run(main())
    assert mid["decided"] == 1 and not mid["finished"] and mid["counts"]["rejected"] == 1


def test_writeup_and_evidence_run_concurrently():
    import time

    class Slow(TruthExtractor):
        async def summarize(self, **kw):
            await asyncio.sleep(0.8)
            return await super().summarize(**kw)

        async def locate(self, *, data, mime, targets):
            await asyncio.sleep(0.8)
            return []

    run = asyncio.run(world_pipeline(Slow(MANIFEST)).run_batch(files("42_greenleaf_disguised_duplicate_rescan.pdf")))[0]
    assert run["decision"]["decision"] == "HOLD"
    assert run["finished"] - run["decided_at"] < 1.4  # sequential would take at least 1.6 s
