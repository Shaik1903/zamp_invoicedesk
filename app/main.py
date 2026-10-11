"""InvoiceDesk web app: JSON API, SSE snapshots for live views, and the static UI."""
import asyncio
import json
import logging
import os
import re
import time
from urllib.parse import quote
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import db, evaluate, evidence
from app.extract import GeminiExtractor, load_env
from app.pipeline import Pipeline
from app.truth import TruthExtractor

ROOT = Path(__file__).resolve().parent.parent
FIX_DIR = ROOT / "fixtures" / "invoices"
ORIG_DIR = ROOT / "fixtures" / "originals"
MANIFEST = json.loads((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))["files"]
MAN_BY_FILE = {m["file"]: m for m in MANIFEST}
SEED = json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))
DEMO = [("Happy path", [1]), ("EC1: split PO overrun", [26]), ("EC2: duplicate in disguise", [42]),
        ("EC3: bank details changed", [46]), ("EC4: messy photo, no PO", [28])]
MAX_FILES, MAX_BYTES = 100, 14 * 1024 * 1024  # 14 MB stays under Gemini's inline request limit once base64-encoded
MAX_TOTAL_BYTES = 60 * 1024 * 1024  # whole batch: keeps a 512 MB instance alive
ASSUMPTIONS = [
    "Invoices are in USD, and one invoice references at most one PO.",
    "Price tolerance is 2% per line. A PO may be overbilled by the greater of 1% or $50; unplanned charges up to $50 are accepted with a note. All editable.",
    "Held invoices do not use up a PO's balance; approved and paid ones do.",
    "The vendor master is the source of truth for bank details. A change is verified by phone using the number on file. On a scan, a changed account is read a second time by a stronger model first; only an exact match with the master clears it.",
    "A probable duplicate is held, not rejected. Only the same vendor plus the same invoice number is rejected automatically.",
    "Goods receipts exist for goods. Services (IT, cleaning, rentals, repairs) are treated as received.",
    "Stamps such as PAID or RECEIVED are ignored; payment status comes from the ledger.",
    "Within a batch, invoices are read in parallel but decided one at a time in upload order.",
    "The AI only reads documents and writes explanations. Every decision is made by fixed, testable rules.",
    "A clerk takes about 12 minutes per invoice (used for the hours-saved figure).",
    "Email intake, sign-in, multi-currency and ERP posting are out of scope for this case study.",
]
log = logging.getLogger("invoicedesk")


def make_extractor():
    if os.getenv("EXTRACTOR", "gemini") == "truth":
        return TruthExtractor(MANIFEST)
    if not os.getenv("GEMINI_API_KEY"):
        log.warning("GEMINI_API_KEY not set: running OFFLINE with the answer-key extractor")
        return TruthExtractor(MANIFEST)
    return GeminiExtractor()


def sse(snapshot, is_done):
    async def gen():
        while True:
            snap = snapshot()
            if snap is None:
                yield "event: error\ndata: {}\n\n"
                return
            yield f"data: {json.dumps(snap, default=str)}\n\n"
            if is_done(snap):
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(0.4)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def create_app(db_path=None, extractor=None):
    load_env(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    S = {}

    def new_pipeline():
        S["pipeline"] = Pipeline(S["conn"], S["conn"], S["extractor"], sem=S["sem"])

    def busy():
        return any(not f.done() for f in S["pipeline"]._futures.values()) or S.get("tests_task") and not S["tests_task"].done()

    @asynccontextmanager
    async def lifespan(app):
        conn = db.connect(db_path or os.getenv("DB_PATH", str(ROOT / "data" / "invoicedesk.db")))
        if db.get_policy(conn) is None:
            db.load_seed(conn, SEED)
        cache_file = ROOT / "data" / "extraction_cache.json"
        if cache_file.exists():
            for sha, v in json.loads(cache_file.read_text(encoding="utf-8")).items():
                if db.cache_get(conn, sha) is None:
                    db.cache_put(conn, sha, v["extraction"], v["layout_text"])
        S.update(conn=conn, extractor=extractor or make_extractor(), tests=None,
                 sem=asyncio.Semaphore(int(os.getenv("EXTRACT_CONCURRENCY", "32"))))
        new_pipeline()
        yield
        conn.close()

    app = FastAPI(title="InvoiceDesk", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        ex = S["extractor"]
        return {"extractor": ex.name, "model": getattr(ex, "model", ex.name), "offline": ex.name != "gemini"}

    @app.post("/api/batches")
    async def create_batch(files: list[UploadFile] = File(default=[]), fixture: str | None = Form(None),
                           fixture_ids: str | None = Form(None), fixture_set: str | None = Form(None),
                           reextract: bool = Form(False), label: str = Form("")):
        items = []
        for f in files:
            if f.size is not None and f.size > MAX_BYTES:
                raise HTTPException(400, f"{f.filename} is larger than 14 MB")
            data = await f.read()
            if len(data) > MAX_BYTES:
                raise HTTPException(400, f"{f.filename} is larger than 14 MB")
            if sum(len(d) for _, d in items) + len(data) > MAX_TOTAL_BYTES:
                raise HTTPException(400, "the batch is larger than 60 MB; upload it in smaller parts")
            items.append((f.filename or "upload", data))
        names = []
        if fixture:
            names.append(fixture)
        if fixture_ids:
            by_id = {m["id"]: m["file"] for m in MANIFEST}
            names += [by_id.get(int(i), f"#{i}") for i in fixture_ids.split(",") if i.strip()]
        if fixture_set == "all":
            names += [m["file"] for m in sorted(MANIFEST, key=lambda m: m["id"])]
        for n in names:
            if n not in MAN_BY_FILE:
                raise HTTPException(400, f"unknown fixture {n}")
            items.append((n, (FIX_DIR / n).read_bytes()))
        if not items:
            raise HTTPException(400, "no files")
        if len(items) > MAX_FILES:
            raise HTTPException(400, f"at most {MAX_FILES} files per batch")
        label = label or (names[0] if len(items) == 1 and names else f"{len(items)} invoices")
        batch = await S["pipeline"].submit(items, label=label, reextract=reextract)
        return {"batch_id": batch["id"], "run_ids": batch["run_ids"]}

    @app.get("/api/batches/{batch_id}")
    def batch(batch_id: str):
        snap = S["pipeline"].batch_snapshot(batch_id)
        if snap is None:
            raise HTTPException(404)
        return snap

    @app.get("/api/batches/{batch_id}/events")
    def batch_events(batch_id: str):
        return sse(lambda: S["pipeline"].batch_snapshot(batch_id), lambda s: s["finished"])

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        r = S["pipeline"].get_run(run_id)
        if r is None:
            raise HTTPException(404)
        return r

    @app.get("/api/runs/{run_id}/related")
    def run_related(run_id: str):
        r = S["pipeline"].get_run(run_id)
        if r is None:
            raise HTTPException(404)
        return S["pipeline"].related(r)

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: str):
        return sse(lambda: S["pipeline"].get_run(run_id), lambda r: r["phase"] == "done")

    @app.get("/api/runs/{run_id}/file")
    def run_file(run_id: str):
        r = S["pipeline"].get_run(run_id)
        got = r and db.file_get(S["conn"], r["sha256"])
        if not got:
            raise HTTPException(404)
        return Response(got[0], media_type=got[1], headers={"Content-Disposition": "inline; filename*=UTF-8''" + quote(r["filename"])})

    @app.get("/api/runs")
    def runs():
        rows = []
        for r in db.list_runs(S["conn"]):
            d = r.get("decision") or {}
            x = r.get("extraction") or {"fields": {}}
            rows.append({"id": r["id"], "batch_id": r["batch_id"], "created": r["created"], "filename": r["filename"],
                         "vendor": r.get("vendor"), "invoice_number": (x["fields"].get("invoice_number") or {}).get("value"),
                         "total": (r.get("money") or {}).get("total"), "decision": d.get("decision"),
                         "code": (d.get("primary") or {}).get("code"), "title": (d.get("primary") or {}).get("title"),
                         "at_risk": d.get("amount_at_risk") or 0,
                         "seconds": round(r["finished"] - r["created"], 1) if r.get("finished") else None})
        return {"runs": rows, "kpis": db.kpis(S["conn"])}

    @app.get("/api/reference")
    def reference():
        ref = db.load_ref(S["conn"])
        receipts = [{"po_number": po, "sku": sku, "qty_received": q} for po, m in ref["receipts"].items() for sku, q in m.items()]
        return {"company": ref["company"], "policy": ref["policy"], "vendors": ref["vendors"],
                "pos": db.po_balances(S["conn"]), "receipts": receipts, "ledger": ref["ledger"]}

    @app.put("/api/policy")
    async def put_policy(request: Request):
        try:
            return db.set_policy(S["conn"], await request.json())
        except (ValueError, AttributeError) as e:
            raise HTTPException(422, str(e))

    @app.get("/api/fixtures")
    def fixtures():
        by_id = {m["id"]: m["file"] for m in MANIFEST}
        return {"demo": [{"label": lbl, "ids": ids, "files": [by_id[i] for i in ids]} for lbl, ids in DEMO],
                "files": [{k: m[k] for k in ("id", "file", "title", "category", "kind", "expected")} for m in MANIFEST]}

    @app.post("/api/demo/reset")
    def reset():
        if busy():
            raise HTTPException(409, "wait for the running batch to finish")
        db.load_seed(S["conn"], SEED)
        new_pipeline()
        return {"ok": True}

    @app.post("/api/invoices/clear")
    def clear_invoices():
        if busy():
            raise HTTPException(409, "wait for the running batch to finish")
        db.clear_invoices(S["conn"])
        new_pipeline()
        return {"ok": True}

    @app.post("/api/tests/run")
    async def tests_run(ids: str | None = None):
        if S.get("tests_task") and not S["tests_task"].done():
            raise HTTPException(409, "a test run is already in progress")
        chosen = MANIFEST if not ids else [m for m in MANIFEST if str(m["id"]) in ids.split(",")]

        async def go():
            S["tests"] = {"status": "running", "started": time.time()}
            try:
                S["tests"] = await evaluate.evaluate(chosen, FIX_DIR, SEED, S["conn"], S["extractor"], sem=S["sem"])
            except Exception as e:  # noqa: BLE001 - surface in the UI instead of dying silently
                log.exception("test run failed")
                S["tests"] = {"status": "error", "error": str(e)}

        S["tests_task"] = asyncio.create_task(go())
        return {"started": True}

    @app.get("/api/tests/latest")
    def tests_latest():
        return S["tests"] or {"status": "never"}

    @app.get("/api/assumptions")
    def assumptions():
        return ASSUMPTIONS

    @app.get("/api/runs/{run_id}/pages/{n}")
    def run_page(run_id: str, n: int):
        r = S["pipeline"].get_run(run_id)
        got = r and db.file_get(S["conn"], f"{r['sha256']}:p{n}")
        if not got:
            raise HTTPException(404)
        return Response(got[0], media_type="image/png")

    def _original(inv):
        if not re.fullmatch(r"[A-Za-z0-9-]+", inv):  # an invoice number, never a path
            raise HTTPException(404)
        f = ORIG_DIR / f"{inv}.pdf"
        if not f.exists():
            raise HTTPException(404)
        return f.read_bytes()

    @app.get("/api/originals/{inv}")
    def original(inv: str):
        data = _original(inv)
        entry = next((e for e in db.load_ref(S["conn"])["ledger"] if e["invoice_number"] == inv), None)
        x = {"fields": {"invoice_number": {"value": inv, "source_text": inv},
                        "total": {"value": entry["total"] if entry else None, "source_text": None}},
             "line_items": [{"amount": round(l["qty"] * l["unit_price"], 2), "description": l["desc"]} for l in (entry or {}).get("lines", [])],
             "stamps": []}
        boxes = evidence.locate_in_words(evidence.targets(x), evidence.pdf_words(data))
        return {"url": f"/api/originals/{inv}/page", "boxes": boxes}

    @app.get("/api/originals/{inv}/page")
    def original_page(inv: str):
        return Response(evidence.render_pages(_original(inv))[0], media_type="image/png")

    app.mount("/", StaticFiles(directory=ROOT / "app" / "static", html=True), name="static")
    return app


app = create_app()
