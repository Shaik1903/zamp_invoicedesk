"""What a perfect reader would extract from a fixture: built from the answer key (manifest truth).
Used by the offline TruthExtractor and by rule tests; never by the live Gemini path."""
from app.rules import FIELD_NAMES


def extraction_from_truth(truth):
    docs = truth if isinstance(truth, list) else [truth]
    t = docs[0]
    conf = "high" if t.get("legible", True) else "low"
    vals = {"vendor_name": t["vendor_name_printed"], "vendor_tax_id": t["vendor_tax_id_printed"],
            "remit_bank_account": t["remit_bank_account"], "remit_bank_routing": t["remit_bank_routing"],
            "invoice_number": t["invoice_number"], "invoice_date": t["invoice_date"], "due_date": t["due_date"],
            "po_number": t["po_number_printed"], "po_number_handwritten": t.get("po_number_handwritten"),
            "bill_to_name": t["bill_to_name"], "currency": t["currency"], "service_period": t["service_period"],
            "subtotal": t["subtotal"], "tax_amount": t["tax"], "tax_rate": t.get("tax_rate_printed"),
            "prices_include_tax": t["prices_include_tax"], "total": t["total_printed"]}
    fields = {n: {"value": vals.get(n), "confidence": conf,
                  "source_text": None if vals.get(n) is None else str(vals.get(n))} for n in FIELD_NAMES}
    lines = [{"sku": li["sku"], "description": li["description"], "qty": li["qty"], "unit_price": li["unit_price"],
              "amount": li["amount"], "confidence": conf, "source_text": None} for li in t["line_items"]]
    return {"document_type": t["document_type"], "document_count": t.get("document_count", len(docs)),
            "fields": fields, "line_items": lines, "stamps": list(t.get("stamps") or [])}


import asyncio
import random
from pathlib import Path


class TruthExtractor:
    """Offline extractor: answers from the answer key by filename (tests, UI dev without an API key)."""
    name = "truth"
    model = "answer-key"

    def __init__(self, manifest_files, delay=(0.0, 0.0)):
        self.by_file = {m["file"]: m for m in manifest_files}
        self.delay = delay

    async def extract(self, *, data, mime, layout_text, filename):
        await asyncio.sleep(random.uniform(*self.delay))
        m = self.by_file.get(Path(filename).name)
        if m is None:
            return {"document_type": "other", "document_count": 1, "line_items": [], "stamps": [],
                    "fields": {n: {"value": None, "confidence": "low", "source_text": None} for n in FIELD_NAMES}}
        return extraction_from_truth(m["truth"])

    async def reread_bank(self, *, data, mime, filename):
        m = self.by_file.get(Path(filename).name)
        t = (m["truth"][0] if isinstance(m["truth"], list) else m["truth"]) if m else {}
        acct = t.get("remit_bank_account")
        return {"account": acct, "routing": t.get("remit_bank_routing"),
                "digit_count": sum(c.isdigit() for c in acct) if acct else None, "source_text": acct}

    async def locate(self, *, data, mime, targets):
        return []  # offline mode has no vision: scans show the page without boxes

    async def summarize(self, *, decision, vendor_name, invoice_number, total):
        from app.extract import template_writeup

        return template_writeup(decision, vendor_name, invoice_number, total)
