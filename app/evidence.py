"""Where each extracted value sits on the page, and which values a decision depends on.

Digital PDFs: exact boxes from LiteParse word positions (no AI). Scans and photos: boxes from one Gemini
locate call per page, made after the decision. Boxes are [ymin, xmin, ymax, xmax] normalised to 0-1000.
"""
import os
import re
import tempfile

LABELS = {"vendor_name": "Vendor", "vendor_tax_id": "Tax ID", "invoice_number": "Invoice number",
          "invoice_date": "Invoice date", "po_number": "PO number", "po_number_handwritten": "Handwritten PO",
          "bill_to_name": "Billed to", "remit_bank_account": "Bank account", "remit_bank_routing": "Routing number",
          "subtotal": "Subtotal", "tax_amount": "Tax", "total": "Total"}
# Which check each value belongs to: the UI reveals a box once that check has finished.
STAGE_OF = {"vendor_name": "vendor", "vendor_tax_id": "vendor", "remit_bank_account": "vendor",
            "remit_bank_routing": "vendor", "invoice_number": "duplicates", "invoice_date": "validate",
            "bill_to_name": "validate", "subtotal": "validate", "tax_amount": "validate", "total": "validate",
            "po_number": "po_match", "po_number_handwritten": "po_match", "line": "three_way", "stamp": "validate",
            "document_type": "validate"}
# How each non-invoice document names itself in its heading: the evidence for CREDIT_NOTE and NOT_AN_INVOICE.
DOC_TITLES = {"credit_note": ["Credit Memo", "Credit Note"], "quote": ["Quotation", "Quote", "Estimate"],
              "statement": ["Statement of Account", "Statement"]}
REASON_KEYS = {
    "BANK_DETAILS_CHANGED": ["remit_bank_account", "remit_bank_routing"], "TAX_ID_MISMATCH": ["vendor_tax_id"],
    "VENDOR_BLOCKED": ["vendor_name"], "VENDOR_NOT_FOUND": ["vendor_name"], "VENDOR_ALIAS_MATCHED": ["vendor_name"],
    "NOT_ADDRESSED_TO_US": ["bill_to_name"], "CURRENCY_NOT_SUPPORTED": ["total"], "INVALID_DATE": ["invoice_date"],
    "ARITHMETIC_MISMATCH": ["subtotal", "tax_amount", "total", "@lines"], "TAX_MISMATCH": ["tax_amount", "subtotal"],
    "TOTAL_COMPUTED": ["subtotal"], "TAX_INCLUSIVE_PRICES": ["total"], "CREDIT_NOTE": ["document_type", "total"], "NOT_AN_INVOICE": ["document_type"],
    "PO_INVALID": ["po_number", "po_number_handwritten"], "PO_INFERRED": ["@lines"],
    "PO_FROM_ANNOTATION": ["po_number_handwritten"], "PO_OVERRUN": ["total"],
    "DUPLICATE": ["invoice_number", "total"], "PROBABLE_DUPLICATE": ["invoice_number", "total", "@lines"],
    "RECURRING_CHARGE_NOT_DUPLICATE": ["total"], "STAMP_IGNORED": ["@stamps"], "BUNDLED_LINES": ["@lines"],
    "UNMATCHED_LINE": ["@unmatched_pos"], "UNMATCHED_LINE_WITHIN_TOLERANCE": ["@unmatched_pos"],
    "UNMATCHED_CREDIT_LINE": ["@unmatched_neg"], "PRICE_VARIANCE": ["@price_over"],
    "PRICE_VARIANCE_WITHIN_TOLERANCE": ["@price_within"], "QTY_NOT_RECEIVED": ["@qty"], "PARTIAL_DELIVERY": ["@qty"],
    "LOW_CONFIDENCE_EXTRACTION": ["@low"],
}
RANK = {"reject": 0, "hold": 1, "note": 2}


def _flat(s):
    return re.sub(r"[\s,$]", "", str(s or "")).casefold()


def _money_word(s):
    """-$227.39 and (227.39) are the same printed amount as 227.39."""
    return _flat(s).strip("()").lstrip("-−")


def _is_money(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def targets(x):
    out = []
    for key, label in LABELS.items():
        f = x["fields"].get(key) or {}
        if f.get("value") in (None, ""):
            continue
        out.append({"key": key, "label": label, "text": str(f.get("source_text") or f["value"]), "value": f["value"]})
    for i, li in enumerate(x["line_items"]):
        if li.get("amount") is not None:
            out.append({"key": f"line:{i}", "label": f"Line {i + 1}: {(li.get('description') or '')[:48]}",
                        "text": f"{li['amount']:,.2f}", "value": li["amount"]})
    for j, s in enumerate(x.get("stamps") or []):
        out.append({"key": f"stamp:{j}", "label": f"Stamp: {s}", "text": s, "value": s})
    titles = DOC_TITLES.get(x.get("document_type"), [])
    if titles:  # only the heading (first hit), not every "Credit Memo #" label
        out.append({"key": "document_type", "label": f"Document type: {titles[0].lower()}", "text": titles[0],
                    "value": titles[0], "forms": {_flat(t) for t in titles}, "max_hits": 1})
    return out


def _forms(t):
    if t.get("forms"):
        return t["forms"]
    if _is_money(t["value"]):
        return {f"{abs(t['value']):.2f}", f"{abs(t['value']):.4f}"}
    return {_flat(t["value"]), _flat(t["text"])} - {""}


def locate_in_words(tgts, pages, max_span=8, max_hits=3):
    """Exact boxes for digital PDFs: a value matches 1..max_span consecutive words whose characters (ignoring
    spaces, commas and $) equal it. Money matches whole words only, so 54.80 never matches inside 354.80."""
    boxes = []
    for t in tgts:
        forms, hits, limit = _forms(t), 0, t.get("max_hits", max_hits)
        norm = _money_word if _is_money(t["value"]) else _flat
        for pn, pg in enumerate(pages, start=1):
            words, W, H = pg["words"], pg["width"], pg["height"]
            for i in range(len(words)):
                acc = ""
                for j in range(i, min(i + max_span, len(words))):
                    acc += norm(words[j][0])
                    if acc in forms:
                        span = words[i:j + 1]
                        x0, y0 = min(w[1] for w in span), min(w[2] for w in span)
                        x1, y1 = max(w[1] + w[3] for w in span), max(w[2] + w[4] for w in span)
                        boxes.append({"key": t["key"], "label": t["label"], "page": pn,
                                      "box": [round(y0 / H * 1000), round(x0 / W * 1000), round(y1 / H * 1000), round(x1 / W * 1000)]})
                        hits += 1
                        break
                    if not any(f.startswith(acc) for f in forms):
                        break
                if hits >= limit:
                    break
            if hits >= limit:
                break
    return boxes


def flags(decision, x, three_way_details, price_tol):
    """Map every reason in the decision to the values it is about: {key: worst severity}."""
    rows = (three_way_details or {}).get("lines") or []
    lines = x["line_items"]
    groups = {
        "@lines": [f"line:{i}" for i in range(len(lines))],
        "@stamps": [f"stamp:{j}" for j in range(len(x.get("stamps") or []))],
        "@unmatched_pos": [f"line:{i}" for i, r in enumerate(rows) if r.get("po_sku") is None and (lines[i].get("amount") or 0) >= 0],
        "@unmatched_neg": [f"line:{i}" for i, r in enumerate(rows) if r.get("po_sku") is None and (lines[i].get("amount") or 0) < 0],
        "@price_over": [f"line:{i}" for i, r in enumerate(rows) if (r.get("price_diff_pct") or 0) > price_tol],
        "@price_within": [f"line:{i}" for i, r in enumerate(rows) if 0.5 < abs(r.get("price_diff_pct") or 0) <= price_tol],
        "@qty": [f"line:{i}" for i, r in enumerate(rows) if r.get("po_sku")],
        "@low": [k for k, f in x["fields"].items() if f.get("value") is not None and f.get("confidence") == "low"]
                + [f"line:{i}" for i, li in enumerate(lines) if li.get("confidence") == "low"],
    }
    out = {}
    for r in decision.get("reasons", []):
        for k in REASON_KEYS.get(r["code"], []):
            for key in groups.get(k, [k]):
                if key not in out or RANK[r["severity"]] < RANK[out[key]]:
                    out[key] = r["severity"]
    return out


def pdf_words(data):
    from liteparse import LiteParse

    p = LiteParse(ocr_enabled=False, output_format="text", quiet=True, emit_word_boxes=True, max_pages=10)
    try:
        res = p.parse(data)
        return [{"width": pg.width, "height": pg.height,
                 "words": [[w.text, w.x, w.y, w.width, w.height] for item in pg.text_items for w in (item.words or [])]}
                for pg in res.pages]
    finally:
        p.close()


def render_pages(data):
    """One PNG per PDF page (LiteParse screenshots need a file path)."""
    from liteparse import LiteParse

    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        p = LiteParse(ocr_enabled=False, quiet=True, dpi=110, max_pages=10)  # crisp on screen, much smaller PNGs
        try:
            return [s.image_bytes for s in sorted(p.screenshot(path), key=lambda s: s.page_num)]
        finally:
            p.close()
    finally:
        os.remove(path)
