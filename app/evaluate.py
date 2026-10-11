"""The fixture test suite: every file alone (fresh world each, in parallel) plus the whole set as one batch,
scored against the answer key; plus field-level extraction accuracy."""
import asyncio
import os
import time

from app import db, rules
from app.pipeline import Pipeline

FIELDS = ("vendor", "invoice_number", "invoice_date", "po_number", "subtotal", "total", "bank_account", "currency",
          "line_count")


def _close(a, b):
    return (a is None and b is None) or (a is not None and b is not None and abs(float(a) - float(b)) <= 0.011)


def field_accuracy(x, truth, kind=""):
    t = truth[0] if isinstance(truth, list) else truth
    single = t["document_type"] == "invoice" and not isinstance(truth, list)
    no_subtotal_line = kind.startswith("handwritten")  # the carbon-book form prints only a TOTAL
    f = {k: v["value"] for k, v in x["fields"].items()}
    vendor_ok = (rules.digits(f["vendor_tax_id"]) == rules.digits(t["vendor_tax_id_printed"]) and t["vendor_tax_id_printed"]) \
        or rules.similarity(f["vendor_name"], t["vendor_name_printed"]) >= 0.85
    acc = {"vendor": bool(vendor_ok),
           "invoice_number": rules.norm_invoice_no(f["invoice_number"]) == rules.norm_invoice_no(t["invoice_number"]),
           "invoice_date": (f["invoice_date"] or None) == t["invoice_date"],
           "po_number": rules.norm_po(f["po_number"]) == rules.norm_po(t["po_number_printed"]),
           "subtotal": _close(f["subtotal"], t["subtotal"]) or (f["subtotal"] is None and (no_subtotal_line or not t["line_items"])),
           "total": _close(f["total"], t["total_printed"]),
           "bank_account": rules.digits(f["remit_bank_account"]) == rules.digits(t["remit_bank_account"]),
           "currency": str(f["currency"] or "USD").upper() == t["currency"],
           "line_count": len(x["line_items"]) == len(t["line_items"])}
    if not single:  # statements, quotes, credit notes, multi-document files: total and line count are not comparable
        del acc["total"], acc["line_count"]
    return acc


def _actual(run):
    d = run["decision"]
    return {"decision": d["decision"], "codes": [r["code"] for r in d["reasons"]]}


def _passes(actual, expected):
    return actual["decision"] == expected["decision"] and set(expected["reasons"]) <= set(actual["codes"])


async def evaluate(manifest, fixtures_dir, seed, store, extractor, sem=None):
    t0 = time.time()
    sem = sem or asyncio.Semaphore(int(os.getenv("EXTRACT_CONCURRENCY", "32")))

    def world():
        w = db.connect()
        db.load_seed(w, seed)
        return w

    async def alone(m):
        p = Pipeline(world(), store, extractor, sem=sem)
        return (await p.run_batch([(m["file"], (fixtures_dir / m["file"]).read_bytes())]))[0]

    ordered = sorted(manifest, key=lambda m: m["id"])
    alone_runs = await asyncio.gather(*(alone(m) for m in ordered))
    batch_runs = await Pipeline(world(), store, extractor, sem=sem).run_batch(
        [(m["file"], (fixtures_dir / m["file"]).read_bytes()) for m in ordered])

    rows, field_hits = [], {k: [0, 0] for k in FIELDS}
    for m, ra, rb in zip(ordered, alone_runs, batch_runs):
        fields = None
        if ra.get("extraction") and m["truth"] and (m["truth"][0] if isinstance(m["truth"], list) else m["truth"]).get("legible", True):
            fields = field_accuracy(ra["extraction"], m["truth"], m["kind"])
            for k, ok in fields.items():
                field_hits[k][0] += ok
                field_hits[k][1] += 1
        aa, ab = _actual(ra), _actual(rb)
        rows.append({"id": m["id"], "file": m["file"], "title": m["title"], "category": m["category"], "kind": m["kind"],
                     "expected_alone": m["expected"]["alone"], "actual_alone": aa, "pass_alone": _passes(aa, m["expected"]["alone"]),
                     "expected_batch": m["expected"]["in_batch"], "actual_batch": ab,
                     "pass_batch": _passes(ab, m["expected"]["in_batch"]), "cached": ra.get("cached", False),
                     "seconds": round((ra["finished"] or 0) - ra["created"], 1), "fields": fields})

    def score(key):
        n = sum(r[key] for r in rows)
        return {"passed": n, "total": len(rows), "rate": round(n / len(rows), 3) if rows else 0.0}

    return {"status": "done", "finished": time.time(), "elapsed_s": round(time.time() - t0, 1),
            "extractor": extractor.name, "model": getattr(extractor, "model", extractor.name),
            "alone": score("pass_alone"), "batch": score("pass_batch"),
            "fields": {k: {"correct": c, "total": n, "rate": round(c / n, 3) if n else 0.0} for k, (c, n) in field_hits.items()},
            "rows": rows}
