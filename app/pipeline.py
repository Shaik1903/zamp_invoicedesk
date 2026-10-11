"""Runs invoices through the 8 stages.

Phase A (intake, extract, validate) runs in parallel, bounded by a semaphore (the AI rate limit). On scanned documents
a bank account that differs from the vendor master is read a second time before it is trusted.
Phase B (vendor, PO, three-way, duplicates, decision + ledger posting) runs under one lock in upload
order: PO balances and the duplicate ledger are shared state, so two invoices must never be decided at
once. Phase C writes the summary/email after the decision is final. AI reads, rules decide.
"""
import asyncio
import hashlib
import logging
import os
import time
import uuid
from collections import Counter
from datetime import date

from app import db, evidence, rules
from app.extract import template_writeup

log = logging.getLogger("invoicedesk.pipeline")
STAGE_TITLES = {"intake": "Intake", "extract": "Read (AI)", "validate": "Validate document", "vendor": "Vendor check",
                "po_match": "PO match", "three_way": "Three-way match", "duplicates": "Duplicate check",
                "decision": "Decision"}
MAX_PAGES = 10  # invoices are short; a long upload is read and rendered up to here
LEDGER_STATUS = {"APPROVE": "approved", "HOLD": "on_hold", "REJECT": "rejected"}


def sniff(data):
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return None


def parse_pdf(data):
    from liteparse import LiteParse

    parser = LiteParse(ocr_enabled=False, output_format="text", quiet=True, max_pages=MAX_PAGES)
    try:
        return [pg.text or "" for pg in parser.parse(data).pages]
    finally:
        parser.close()


def new_run(batch_id, seq, filename, data):
    return {"id": uuid.uuid4().hex[:12], "batch_id": batch_id, "seq": seq, "filename": filename,
            "sha256": hashlib.sha256(data).hexdigest(), "mime": None, "size": len(data), "created": time.time(),
            "finished": None, "phase": "queued",
            "stages": {s: {"stage": s, "title": STAGE_TITLES[s], "status": "pending", "summary": "", "details": {},
                           "reasons": [], "ms": 0} for s in rules.STAGES},
            "extraction": None, "money": None, "vendor": None, "vendor_id": None, "po_number": None, "cached": False,
            "path": None, "decision": None, "decided_at": None, "summary": None, "email": None}


class Pipeline:
    def __init__(self, world, store, extractor, sem=None, today=None):
        self.world, self.store, self.extractor = world, store, extractor
        self.sem = sem or asyncio.Semaphore(int(os.getenv("EXTRACT_CONCURRENCY", "32")))
        self.lock = asyncio.Lock()
        self.today = today
        self.ai_timeout = float(os.getenv("AI_TIMEOUT", "90"))  # a hung AI call must never freeze the batch
        self._page_tasks = {}
        self.runs, self.batches, self._futures = {}, {}, {}
        self._tail = None  # done-event of the most recently submitted run: deciding is first in, first decided

    def _today(self):
        return self.today or date.today()

    async def submit(self, files, label="", reextract=False):
        batch = {"id": uuid.uuid4().hex[:10], "created": time.time(), "label": label, "run_ids": []}
        coros = []
        for i, (filename, data) in enumerate(files):
            run = new_run(batch["id"], i, filename, data)
            self.runs[run["id"]] = run
            batch["run_ids"].append(run["id"])
            db.file_put(self.store, run["sha256"], data, sniff(data) or "application/octet-stream")
            db.save_run(self.world, run)
            prev, done = self._tail, asyncio.Event()
            self._tail = done
            coros.append(self._run_one(run, data, prev, done, reextract))
        self.batches[batch["id"]] = batch
        db.save_batch(self.world, batch)
        self._futures[batch["id"]] = asyncio.ensure_future(asyncio.gather(*coros))
        return batch

    async def wait(self, batch_id):
        await self._futures[batch_id]

    async def run_batch(self, files, **kw):
        batch = await self.submit(files, **kw)
        await self.wait(batch["id"])
        return [self.runs[r] for r in batch["run_ids"]]

    def get_run(self, run_id):
        return self.runs.get(run_id) or db.get_run(self.world, run_id)

    # ---- stage bookkeeping -------------------------------------------------------------------
    def _set(self, run, result, t0):
        d = result.to_dict()
        d["title"], d["ms"] = STAGE_TITLES[result.stage], int((time.perf_counter() - t0) * 1000)
        run["stages"][result.stage] = d
        db.save_run(self.world, run)

    def _running(self, run, stage):
        run["stages"][stage]["status"] = "running"

    def _skip(self, run, stage, why):
        self._set(run, rules.StageResult(stage, "skip", why), time.perf_counter())

    # ---- orchestration -----------------------------------------------------------------------
    async def _run_one(self, run, data, prev, done, reextract):
        t0 = time.time()
        try:
            ctx = await self._phase_a(run, data, reextract)
            run["phase"] = "waiting"
            if prev is not None:
                await prev.wait()
            async with self.lock:
                run["phase"] = "deciding"
                self._phase_b(run, ctx)
        except Exception as e:  # one broken invoice must never stall the batch
            log.exception("run %s crashed", run["id"])
            if prev is not None:
                await prev.wait()  # even a crashed run is decided in upload order, never ahead of earlier invoices
            self._crash(run, e)
        finally:
            done.set()
        await self._phase_c(run, data)
        d = run["decision"]
        log.info("%-48s %-7s %-26s %5.1fs  %s", run["filename"][:48], d["decision"],
                 (d["primary"] or {}).get("code", ""), time.time() - t0,
                 " ".join(f"{s}={run['stages'][s]['ms']}" for s in rules.STAGES))

    def _crash(self, run, e):
        for s in rules.STAGES[:-1]:
            if run["stages"][s]["status"] in ("pending", "running"):
                self._skip(run, s, "Stopped by an internal error")
        r = rules.Reason("EXTRACTION_FAILED", f"Internal error while processing: {type(e).__name__}: {str(e)[:120]}",
                         "Retry, or key the invoice in manually")
        run["decision"] = rules.decide([rules.StageResult("intake", "fail", "", reasons=[r])], run.get("money"))
        run["decided_at"] = time.time()
        self._set(run, rules.StageResult("decision", "warn", "HOLD: internal error"), time.perf_counter())

    async def _phase_a(self, run, data, reextract):
        ctx = {"results": [], "x": None, "money": None}
        run["phase"] = "reading"
        t = time.perf_counter()
        self._running(run, "intake")
        mime = sniff(data)
        run["mime"] = mime or "application/octet-stream"
        pages, problem = None, None
        if not data:
            problem = "The file is empty."
        elif mime is None:
            problem = "This is not a PDF, JPG or PNG file."
        elif mime == "application/pdf":
            try:
                pages = await asyncio.to_thread(parse_pdf, data)
            except Exception as e:  # noqa: BLE001 - any parser failure means unreadable
                problem = ("The PDF is password-protected." if "password" in str(e).lower()
                           else f"The PDF cannot be opened ({str(e)[:80]}).")
        else:
            pages = [""]
        if problem:
            r = rules.StageResult("intake", "fail", problem, {"mime": run["mime"], "bytes": len(data)},
                                  [rules.Reason("UNREADABLE_FILE", problem, "Ask the vendor to resend the invoice as a normal PDF")])
            ctx["results"].append(r)
            self._set(run, r, t)
            for s in ("extract", "validate"):
                self._skip(run, s, "The file could not be opened")
            return ctx
        scanned = any(len(p.split()) < 20 for p in pages)
        run["path"] = "scanned" if scanned else "digital"
        layout = None if scanned else "\n\n".join(pages)
        self._page_tasks[run["id"]] = asyncio.ensure_future(self._pages(run, data, mime))  # never delays the decision
        kind = "PDF" if mime == "application/pdf" else "Image"
        r = rules.StageResult("intake", "pass", f"{kind}, {len(pages)} page(s): " +
                              ("no text layer, read by AI vision" if scanned else "text layer found, read from text"),
                              {"mime": mime, "pages": len(pages), "path": run["path"], "sha256": run["sha256"][:12],
                               "bytes": len(data)})
        ctx["results"].append(r)
        self._set(run, r, t)

        t = time.perf_counter()
        self._running(run, "extract")
        hit = None if reextract else db.cache_get(self.store, run["sha256"])
        reread = None
        try:
            if hit:
                x, run["cached"] = hit["extraction"], True
            else:
                async with self.sem:
                    x = await asyncio.wait_for(self.extractor.extract(data=data, mime=mime, layout_text=layout,
                                                                      filename=run["filename"]), self.ai_timeout)
                    if not layout:
                        x, reread = await self._bank_reread(x, data, mime, run["filename"])
                db.cache_put(self.store, run["sha256"], x, layout or "")
        except Exception as e:  # noqa: BLE001 - extractor failures become a HOLD, never a crash
            msg = f"The AI reader failed: {str(e)[:160]}"
            r = rules.StageResult("extract", "fail", msg, {}, [rules.Reason("EXTRACTION_FAILED", msg,
                                                                            "Retry, or key the invoice in manually")])
            ctx["results"].append(r)
            self._set(run, r, t)
            self._skip(run, "validate", "Nothing was extracted")
            return ctx
        unverified = []
        if layout:
            x, unverified = rules.ground(x, layout)
        ctx["x"] = run["extraction"] = x
        n = sum(1 for f in x["fields"].values() if f["value"] not in (None, ""))
        summary = f"{n} fields and {len(x['line_items'])} line(s) read" + (" (cached)" if run["cached"] else "")
        if layout:
            summary += f"; {len(unverified)} value(s) not found in the PDF text" if unverified else \
                "; every key value verified against the PDF text"
        if reread:
            summary += ("; bank account read again by a second model: it matches the vendor master, so the first read "
                        "was a misread" if reread["cleared"] else
                        "; bank account read again by a second model: it still differs from the vendor master")
        r = rules.StageResult("extract", "warn" if unverified else "pass", summary,
                              {"model": getattr(self.extractor, "model", self.extractor.name), "cached": run["cached"],
                               "path": run["path"], "unverified": unverified, "bank_reread": reread})
        ctx["results"].append(r)
        self._set(run, r, t)

        t = time.perf_counter()
        self._running(run, "validate")
        company = db.load_ref(self.world)["company"]
        r, money = rules.validate_document(x, company, self._today(), self._today())
        ctx["money"] = run["money"] = money
        ctx["results"].append(r)
        self._set(run, r, t)
        return ctx

    async def _bank_reread(self, x, data, mime, filename):
        """Scanned documents have no text layer to ground the bank account against, and a misread account looks exactly
        like payment diversion. If the account read differs from the matched vendor's account on file, a second, narrow
        read must match the master exactly before the first read is discarded (fail closed: otherwise the hold stands)."""
        _, vendor = rules.check_vendor(x, db.load_ref(self.world)["vendors"])
        first = rules.fv(x, "remit_bank_account")
        if vendor is None or not rules.digits(first) or rules.digits(first) == rules.digits(vendor["bank"]["account"]):
            return x, None
        try:
            second = (await asyncio.wait_for(self.extractor.reread_bank(data=data, mime=mime, filename=filename),
                                             self.ai_timeout))["account"]
        except Exception as e:  # noqa: BLE001 - a failed re-read keeps the first read, and so the hold
            log.warning("bank re-read failed for %s: %s", filename, e)
            second = None
        x, cleared = rules.apply_bank_reread(x, second, vendor["bank"]["account"])
        return x, {"first_read": first, "second_read": second, "cleared": cleared,
                   "model": getattr(self.extractor, "reread_model", self.extractor.name)}

    def _phase_b(self, run, ctx):
        ref = db.load_ref(self.world)
        x, money, results = ctx["x"], ctx["money"], ctx["results"]
        vendor = po = None
        if x is None:
            for s in ("vendor", "po_match", "three_way", "duplicates"):
                self._skip(run, s, "Nothing was extracted")
        else:
            t = time.perf_counter()
            self._running(run, "vendor")
            r, vendor = rules.check_vendor(x, ref["vendors"], money["total"])
            results.append(r)
            self._set(run, r, t)
            single = x["document_type"] == "invoice" and x.get("document_count", 1) == 1
            why = ("Not a single invoice" if not single else "Vendor not identified" if vendor is None
                   else "Vendor is blocked" if vendor["status"] == "blocked" else None)
            if why:
                for s in ("po_match", "three_way", "duplicates"):
                    self._skip(run, s, why)
            else:
                t = time.perf_counter()
                self._running(run, "po_match")
                r, po = rules.match_po(x, vendor, ref, money)
                results.append(r)
                self._set(run, r, t)
                if po:
                    t = time.perf_counter()
                    self._running(run, "three_way")
                    r = rules.three_way_match(x, money, po, ref)
                    for b in r.details.get("billed_by", []):  # name the files that used up the PO
                        if b.get("run_id"):
                            b["filename"] = (self.get_run(b["run_id"]) or {}).get("filename")
                    results.append(r)
                    self._set(run, r, t)
                else:
                    self._skip(run, "three_way", "No PO to match against")
                t = time.perf_counter()
                self._running(run, "duplicates")
                r = rules.check_duplicates(x, money, vendor, ref)
                orig = r.details.get("original")
                if orig and orig.get("run_id"):  # name the earlier file so a person can open and check it
                    prior = self.get_run(orig["run_id"]) or {}
                    orig["filename"], orig["processed_at"] = prior.get("filename"), prior.get("created")
                results.append(r)
                self._set(run, r, t)
        t = time.perf_counter()
        decision = rules.decide(results, money)
        run["decision"], run["decided_at"] = decision, time.time()
        run["vendor"] = vendor["name"] if vendor else (rules.fv(x, "vendor_name") if x else None)
        run["vendor_id"] = vendor["id"] if vendor else None
        run["po_number"] = po["po_number"] if po else None
        primary = decision["primary"]
        self._set(run, rules.StageResult("decision", {"APPROVE": "pass", "HOLD": "warn", "REJECT": "fail"}[decision["decision"]],
                                         f"{decision['decision']}: " + (primary["title"] if primary else "every check passed"),
                                         {"owner": decision["owner"], "next_action": decision["next_action"]}), t)
        if x is not None and vendor is not None and x["document_type"] == "invoice" and x.get("document_count", 1) == 1:
            db.post_ledger(self.world, {
                "run_id": run["id"], "vendor_id": vendor["id"], "invoice_number": rules.fv(x, "invoice_number"),
                "invoice_date": money["invoice_date"], "po_number": po["po_number"] if po else None,
                "subtotal": money["net_amount"], "total": money["total"], "status": LEDGER_STATUS[decision["decision"]],
                "service_period": rules.fv(x, "service_period"),
                "lines": [{"desc": li.get("description") or "", "qty": li.get("qty") or 0, "unit_price": li.get("unit_price") or 0}
                          for li in x["line_items"]]})

    async def _phase_c(self, run, data):
        run["phase"] = "writing"
        d, x = run["decision"], run.get("extraction")
        inv = rules.fv(x, "invoice_number") if x else None
        total = (run.get("money") or {}).get("total")
        async def writeup():
            w = template_writeup(d, run.get("vendor"), inv, total)
            if d["decision"] != "APPROVE":
                try:
                    w = await asyncio.wait_for(self.extractor.summarize(decision=d, vendor_name=run.get("vendor"),
                                                                        invoice_number=inv, total=total), 30)
                except Exception as e:  # noqa: BLE001 - prose is optional; the template stands in
                    log.warning("write-up failed for %s: %s", run["id"], e)
            run["summary"] = w["summary"]
            run["email"] = ({"to": w["email_to"], "subject": w["email_subject"], "body": w["email_body"]}
                            if w.get("email_body") else None)

        # The explanation and the evidence overlay are independent: run them side by side.
        await asyncio.gather(writeup(), self._evidence(run, data))
        run["phase"], run["finished"] = "done", time.time()
        db.save_run(self.world, run)

    async def _pages(self, run, data, mime):
        """Render page images as soon as the file opens (the UI shows them while the AI reads)."""
        ev = {"status": "pending", "pages": [], "boxes": [], "flags": {}}
        run["evidence"] = ev
        try:
            if mime == "application/pdf":
                known = db.file_get(self.store, f"{run['sha256']}:pages")
                if known:  # rendered before (same file bytes): reuse
                    count = int(known[0])
                else:
                    pngs = await asyncio.to_thread(evidence.render_pages, data)
                    for n, png in enumerate(pngs, start=1):
                        db.file_put(self.store, f"{run['sha256']}:p{n}", png, "image/png")
                    count = len(pngs)
                    db.file_put(self.store, f"{run['sha256']}:pages", str(count).encode(), "text/plain")
                ev["pages"] = [{"n": n, "url": f"/api/runs/{run['id']}/pages/{n}"} for n in range(1, count + 1)]
            else:
                ev["pages"] = [{"n": 1, "url": f"/api/runs/{run['id']}/file"}]
        except Exception as e:  # noqa: BLE001 - the viewer is optional
            log.warning("page render failed for %s: %s", run["id"], e)

    async def _evidence(self, run, data):
        """Value boxes + decision flags. Never affects the decision; failures only lose the overlay."""
        task = self._page_tasks.pop(run["id"], None)
        if task is not None:
            await task
        ev = run.get("evidence") or {"status": "pending", "pages": [], "boxes": [], "flags": {}}
        run["evidence"] = ev
        x, mime = run.get("extraction"), run.get("mime")
        if not x or not ev["pages"]:
            ev["status"] = "none"
            return
        ev["status"] = "locating"
        try:
            if mime == "application/pdf":
                images = [(db.file_get(self.store, f"{run['sha256']}:p{p['n']}")[0], "image/png") for p in ev["pages"]]
            else:
                images = [(data, mime)]
            tg = evidence.targets(x)
            if run.get("path") == "digital":
                ev["boxes"] = evidence.locate_in_words(tg, await asyncio.to_thread(evidence.pdf_words, data))
            else:
                labels = {t["key"]: t["label"] for t in tg}
                for n, (img, img_mime) in enumerate(images, start=1):
                    async with self.sem:
                        found = await asyncio.wait_for(self.extractor.locate(data=img, mime=img_mime, targets=tg),
                                                       self.ai_timeout)
                    ev["boxes"] += [{"key": b["key"], "label": labels.get(b["key"], b["key"]), "page": n, "box": b["box"]}
                                    for b in found if b["key"] in labels]
            tol = (db.get_policy(self.world) or {}).get("price_tolerance_pct", 2.0)
            ev["flags"] = evidence.flags(run["decision"], x, run["stages"]["three_way"].get("details"), tol)
            ev["status"] = "ready"
        except Exception as e:  # noqa: BLE001 - the overlay is optional
            log.warning("evidence failed for %s: %s", run["id"], e)
            ev["status"] = "failed"

    # ---- views -------------------------------------------------------------------------------
    def related(self, run):
        """Everything this invoice is linked to, as of now: its vendor, its PO and every invoice billed on it
        (before and after this one, by ledger order), the vendor's other invoices, and a duplicate's original."""
        ref = db.load_ref(self.world)
        mine = next((e["id"] for e in ref["ledger"] if e["run_id"] == run["id"]), None)

        def entry(e):
            prior = self.get_run(e["run_id"]) if e["run_id"] else None
            pos = None if mine is None else "this" if e["id"] == mine else "before" if e["id"] < mine else "after"
            return {"invoice_number": e["invoice_number"], "invoice_date": e["invoice_date"], "po_number": e["po_number"],
                    "total": e["total"], "subtotal": e["subtotal"], "status": e["status"], "run_id": e["run_id"],
                    "filename": prior and prior["filename"], "position": pos}

        vendor = next((v for v in ref["vendors"] if v["id"] == run.get("vendor_id")), None)
        out = {"vendor": None, "po": None, "vendor_invoices": [],
               "original": ((run["stages"].get("duplicates") or {}).get("details") or {}).get("original")}
        if vendor:
            x = run.get("extraction") or {"fields": {}}
            on_invoice = rules.digits((x["fields"].get("remit_bank_account") or {}).get("value"))
            on_file = rules.digits(vendor["bank"]["account"])
            out["vendor"] = {"id": vendor["id"], "name": vendor["name"], "status": vendor["status"], "tax_id": vendor["tax_id"],
                             "phone": vendor["phone"], "matched_by": ((run["stages"].get("vendor") or {}).get("details") or {}).get("matched_by"),
                             "bank_on_file_last4": on_file[-4:], "bank_on_invoice_last4": on_invoice[-4:] or None,
                             "bank_matches": None if not on_invoice else on_invoice == on_file}
            out["vendor_invoices"] = [entry(e) for e in reversed(ref["ledger"])
                                      if e["vendor_id"] == vendor["id"] and e["id"] != mine][:25]
        po = ref["pos"].get(run.get("po_number"))
        if po:
            on_po = [e for e in ref["ledger"] if e["po_number"] == po["po_number"]]
            out["po"] = {"po_number": po["po_number"], "type": po.get("type"), "status": po["status"], "total": po["total"],
                         "billed_now": round(po.get("opening_billed", 0.0) + sum(e["subtotal"] or 0 for e in on_po
                                                                                if e["status"] in rules.BILLED_STATUSES), 2),
                         "lines": po["lines"], "received": ref["receipts"].get(po["po_number"]),
                         "invoices": [entry(e) for e in on_po]}
        return out

    @staticmethod
    def compact(run):
        d = run.get("decision") or {}
        return {"id": run["id"], "seq": run["seq"], "filename": run["filename"], "phase": run["phase"],
                "statuses": [run["stages"][s]["status"] for s in rules.STAGES], "decision": d.get("decision"),
                "code": (d.get("primary") or {}).get("code"), "title": (d.get("primary") or {}).get("title"),
                "vendor": run.get("vendor"), "total": (run.get("money") or {}).get("total"), "cached": run.get("cached", False)}

    def batch_snapshot(self, batch_id):
        batch = self.batches.get(batch_id) or db.get_batch(self.world, batch_id)
        if batch is None:
            return None
        runs = [r for r in (self.get_run(i) for i in batch["run_ids"]) if r]
        phases = Counter(r["phase"] for r in runs)
        decs = Counter(r["decision"]["decision"] for r in runs if r.get("decision"))
        decided = sum(decs.values())
        done = phases["done"]
        finished = done == len(runs)
        # The timer and throughput follow decisions; explanations and overlays finish just after.
        end = max((r.get("decided_at") or 0) for r in runs) if runs and decided == len(runs) else time.time()
        elapsed = max(end - batch["created"], 0.001)
        minutes = (db.get_policy(self.world) or {}).get("clerk_minutes_per_invoice", 12)
        return {"id": batch["id"], "label": batch.get("label", ""), "created": batch["created"], "total": len(runs),
                "done": done, "decided": decided, "finished": finished,
                "counts": {"queued": phases["queued"], "reading": phases["reading"], "waiting": phases["waiting"],
                           "deciding": phases["deciding"], "approved": decs["APPROVE"],
                           "held": decs["HOLD"], "rejected": decs["REJECT"]},
                "elapsed_s": round(elapsed, 1), "per_minute": round(decided / elapsed * 60, 1),
                "manual_minutes": len(runs) * minutes, "runs": [self.compact(r) for r in runs]}
