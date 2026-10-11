"""Pure decision rules for InvoiceDesk.

No I/O and no LLM calls: every function takes plain dicts (see the plan's data contracts) and returns
StageResult / Reason objects. The AI reads the invoice; this module decides.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

STAGES = ("intake", "extract", "validate", "vendor", "po_match", "three_way", "duplicates", "decision")
FIELD_NAMES = ("vendor_name", "vendor_tax_id", "vendor_address", "remit_bank_account", "remit_bank_routing",
               "invoice_number", "invoice_date", "due_date", "po_number", "po_number_handwritten", "bill_to_name",
               "ship_to", "currency", "service_period", "subtotal", "tax_amount", "tax_rate", "prices_include_tax",
               "total")

# code: (severity, owner, plain-English title). Dict order is the priority used to pick the primary reason.
REASONS = {
    "DUPLICATE": ("reject", "AP clerk", "Already processed: same vendor and invoice number"),
    "VENDOR_BLOCKED": ("reject", "Procurement", "Vendor is blocked"),
    "NOT_AN_INVOICE": ("reject", "AP clerk", "Not an invoice (quote, statement or other document)"),
    "NOT_ADDRESSED_TO_US": ("reject", "Vendor", "Billed to a different company"),
    "UNREADABLE_FILE": ("hold", "AP clerk", "File cannot be opened"),
    "EXTRACTION_FAILED": ("hold", "AP clerk", "Invoice could not be read"),
    "LOW_CONFIDENCE_EXTRACTION": ("hold", "AP clerk", "Key values could not be read with confidence"),
    "MULTIPLE_DOCUMENTS": ("hold", "AP clerk", "More than one document in the file"),
    "CREDIT_NOTE": ("hold", "AP clerk", "Credit note: apply it, do not pay it"),
    "BANK_DETAILS_CHANGED": ("hold", "Security", "Bank details differ from the vendor master"),
    "TAX_ID_MISMATCH": ("hold", "Security", "Tax ID differs from the vendor master"),
    "VENDOR_NOT_FOUND": ("hold", "Procurement", "Vendor is not in the vendor master"),
    "CURRENCY_NOT_SUPPORTED": ("hold", "AP clerk", "Invoice is not in USD"),
    "MISSING_INVOICE_NUMBER": ("hold", "Vendor", "No invoice number"),
    "INVALID_DATE": ("hold", "AP clerk", "Invoice is dated in the future"),
    "ARITHMETIC_MISMATCH": ("hold", "Vendor", "Line items, tax and total do not add up"),
    "TAX_MISMATCH": ("hold", "Vendor", "Tax amount does not match the stated rate"),
    "PROBABLE_DUPLICATE": ("hold", "AP clerk", "Looks like an invoice already processed"),
    "PO_INVALID": ("hold", "Buyer", "PO not found, closed, or belongs to another vendor"),
    "PO_NOT_IDENTIFIED": ("hold", "AP clerk", "Cannot tell which PO this invoice is for"),
    "PO_OVERRUN": ("hold", "Buyer", "Billing would exceed the PO"),
    "PRICE_VARIANCE": ("hold", "Buyer", "Unit price above the PO price"),
    "QTY_NOT_RECEIVED": ("hold", "Buyer", "Billed for more than was received"),
    "UNMATCHED_LINE": ("hold", "Buyer", "Charge or item not on the PO"),
    "VENDOR_ALIAS_MATCHED": ("note", None, "Vendor matched by tax ID or alias"),
    "PO_INFERRED": ("note", None, "PO identified from the line items"),
    "PO_FROM_ANNOTATION": ("note", None, "PO taken from a handwritten note"),
    "PRICE_VARIANCE_WITHIN_TOLERANCE": ("note", None, "Price differs from the PO within tolerance"),
    "PARTIAL_DELIVERY": ("note", None, "Partial delivery billed correctly"),
    "UNMATCHED_LINE_WITHIN_TOLERANCE": ("note", None, "Small charge not on the PO"),
    "UNMATCHED_CREDIT_LINE": ("note", None, "Credit line not on the PO"),
    "BUNDLED_LINES": ("note", None, "Bundled line matched to the PO total"),
    "RECURRING_CHARGE_NOT_DUPLICATE": ("note", None, "Same amount as a past invoice, new service period"),
    "STAMP_IGNORED": ("note", None, "Stamps on the document were ignored"),
    "DATE_DEFAULTED": ("note", None, "No invoice date; received date used"),
    "TOTAL_COMPUTED": ("note", None, "No total printed; computed from the lines"),
    "TAX_INCLUSIVE_PRICES": ("note", None, "Prices include tax; tax backed out for the PO comparison"),
}
PRIORITY = {code: i for i, code in enumerate(REASONS)}


@dataclass
class Reason:
    code: str
    message: str
    action: str | None = None
    amount_at_risk: float = 0.0

    @property
    def severity(self):
        return REASONS[self.code][0]

    @property
    def owner(self):
        return REASONS[self.code][1]

    def to_dict(self):
        return {"code": self.code, "severity": self.severity, "owner": self.owner, "title": REASONS[self.code][2],
                "message": self.message, "action": self.action, "amount_at_risk": round(self.amount_at_risk, 2)}


@dataclass
class StageResult:
    stage: str
    status: str  # pass | warn | fail | skip
    summary: str
    details: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    ms: int = 0

    def to_dict(self):
        return {"stage": self.stage, "status": self.status, "summary": self.summary, "details": self.details,
                "reasons": [r.to_dict() for r in self.reasons], "ms": self.ms}


def stage_status(reasons):
    if any(r.severity != "note" for r in reasons):
        return "fail"
    return "warn" if reasons else "pass"


def fv(x, name):
    return (x["fields"].get(name) or {}).get("value")


def fconf(x, name):
    return (x["fields"].get(name) or {}).get("confidence", "low")


def norm_text(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).split())


def similarity(a, b):
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()


def norm_invoice_no(s):
    s = re.sub(r"[^A-Z0-9]", "", str(s or "").upper())
    return re.sub(r"\d+", lambda m: str(int(m.group())), s)


def digits(s):
    return re.sub(r"\D", "", str(s or ""))


def money_str(v):
    return "n/a" if v is None else (f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}")


def parse_date(s):
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def total_tolerance(amount, policy):
    """Allowed overrun on a PO total: the greater of total_tolerance_pct and total_tolerance_abs."""
    return max(abs(amount) * policy["total_tolerance_pct"] / 100.0, policy["total_tolerance_abs"])


def _flat(s):
    return re.sub(r"[\s,$]", "", str(s or "")).casefold()


def ground(x, layout_text):
    """Digital PDFs only: every money value, the invoice number and the bank account must appear in the
    PDF's own text. Anything not found is downgraded to low confidence. Returns (copy, unverified names)."""
    g = copy.deepcopy(x)
    text = _flat(layout_text)

    def found(v, is_money):
        if is_money:
            return f"{abs(float(v)):.2f}" in text or f"{abs(float(v)):.4f}" in text
        return _flat(v) in text

    unverified = []
    for name, is_money in (("invoice_number", False), ("remit_bank_account", False), ("subtotal", True),
                           ("tax_amount", True), ("total", True)):
        v = g["fields"][name]["value"]
        if v in (None, "", 0, 0.0):
            continue
        if not found(v, is_money):
            g["fields"][name]["confidence"] = "low"
            unverified.append(name)
    for i, li in enumerate(g["line_items"]):
        if li["amount"] not in (None, 0, 0.0) and not found(li["amount"], True):
            li["confidence"] = "low"
            unverified.append(f"line {i + 1} amount")
    return g, unverified


def _num(v):
    return None if v is None else float(v)


def validate_document(x, company, today, received):
    """Stage 3: document type, addressee, currency, dates, completeness, arithmetic, tax and confidence."""
    reasons, checks = [], []
    dt = x["document_type"]
    if x.get("document_count", 1) > 1:
        reasons.append(Reason("MULTIPLE_DOCUMENTS", f"The file contains {x['document_count']} separate documents.",
                              "Split the file and submit each invoice separately"))
    if dt == "credit_note":
        reasons.append(Reason("CREDIT_NOTE", "This is a credit memo, not a request for payment.",
                              "Apply the credit against the vendor's next payment"))
    elif dt != "invoice":
        reasons.append(Reason("NOT_AN_INVOICE", f"This document is a {dt.replace('_', ' ')}, not an invoice.",
                              "No payment action. File it for reference"))
    bill = fv(x, "bill_to_name")
    if bill and max(similarity(bill, n) for n in company["bill_to_names"]) < 0.8:
        reasons.append(Reason("NOT_ADDRESSED_TO_US", f"Bill-to is '{bill}', not {company['name']}.",
                              "Return to the vendor: not our invoice"))
    currency = str(fv(x, "currency") or company["base_currency"]).upper()
    if currency != company["base_currency"]:
        reasons.append(Reason("CURRENCY_NOT_SUPPORTED", f"Invoice is in {currency}; we pay in {company['base_currency']}.",
                              "Confirm the exchange rate and payment method with treasury"))
    if x.get("stamps"):
        reasons.append(Reason("STAMP_IGNORED", "Stamps seen and ignored: " + ", ".join(x["stamps"]) +
                              ". Payment status comes from the ledger, not from stamps."))
    if dt == "invoice" and not fv(x, "invoice_number"):
        reasons.append(Reason("MISSING_INVOICE_NUMBER", "No invoice number is printed, so duplicate checks are unsafe.",
                              "Ask the vendor to reissue the invoice with a number"))
    inv_date = parse_date(fv(x, "invoice_date"))
    if inv_date is None:
        reasons.append(Reason("DATE_DEFAULTED", f"No invoice date found; using the received date {received}."))
        inv_date = received
    elif inv_date > today:
        reasons.append(Reason("INVALID_DATE", f"Invoice is dated {inv_date}, after today ({today}).",
                              "Confirm the date with the vendor before scheduling payment"))

    lines = x["line_items"]
    subtotal, tax, total = _num(fv(x, "subtotal")), _num(fv(x, "tax_amount")) or 0.0, _num(fv(x, "total"))
    incl = bool(fv(x, "prices_include_tax"))
    rate = _num(fv(x, "tax_rate"))
    if rate and rate > 1:
        rate /= 100.0
    amounts = [li["amount"] for li in lines if li["amount"] is not None]
    line_sum = round(sum(amounts), 2) if amounts else None
    if subtotal is None:
        subtotal = line_sum
    if dt in ("invoice", "credit_note"):
        if total is None and subtotal is not None:
            total = round(subtotal + (0.0 if incl else tax), 2)
            reasons.append(Reason("TOTAL_COMPUTED", f"No total printed; computed {money_str(total)} from the lines."))
        problems = []
        for i, li in enumerate(lines):
            q, p, a = li["qty"], li["unit_price"], li["amount"]
            if None not in (q, p, a) and abs(q * p - a) > abs(q) * 0.005 + 0.011:
                problems.append(f"line {i + 1}: {q:g} x {p:g} = {q * p:,.2f}, but the line says {a:,.2f}")
        if line_sum is not None and subtotal is not None and abs(line_sum - subtotal) > 0.02:
            problems.append(f"lines add up to {money_str(line_sum)} but the subtotal says {money_str(subtotal)}")
        expected_total = None if subtotal is None else round(subtotal if incl else subtotal + tax, 2)
        if total is not None and expected_total is not None and abs(expected_total - total) > 0.02:
            problems.append(f"subtotal {money_str(subtotal)} + tax {money_str(0.0 if incl else tax)} = "
                            f"{money_str(expected_total)}, but the total says {money_str(total)}")
        if problems:
            reasons.append(Reason("ARITHMETIC_MISMATCH", "; ".join(problems).capitalize() + ".",
                                  "Ask the vendor for a corrected invoice"))
        else:
            checks.append("lines, subtotal, tax and total reconcile")
        if not incl and rate and subtotal and tax and abs(tax - subtotal * rate) > max(0.05, 0.002 * abs(subtotal)):
            reasons.append(Reason("TAX_MISMATCH", f"Tax is {money_str(tax)}, but {rate * 100:.2f}% of "
                                  f"{money_str(subtotal)} is {money_str(subtotal * rate)}.",
                                  "Ask the vendor to correct the tax line"))
        if incl:
            reasons.append(Reason("TAX_INCLUSIVE_PRICES", f"Prices include tax ({money_str(tax)} included); "
                                  "tax is backed out before comparing with the PO."))

    critical = [n for n in ("vendor_name", "invoice_number", "subtotal", "tax_amount", "total")
                if fv(x, n) is not None and fconf(x, n) == "low"]
    critical += [f"line {i + 1}" for i, li in enumerate(lines) if li["amount"] is not None and li["confidence"] == "low"]
    if critical or (fv(x, "vendor_name") is None and total is None):
        what = ", ".join(critical) if critical else "vendor and total"
        # A document we cannot read cannot be classified either: never REJECT it as a non-invoice, HOLD for a clearer copy.
        if any(r.code == "NOT_AN_INVOICE" for r in reasons):
            reasons = [r for r in reasons if r.code != "NOT_AN_INVOICE"]
            what += f"; document type ('{dt}') is uncertain too"
        reasons.append(Reason("LOW_CONFIDENCE_EXTRACTION", f"Could not read with confidence: {what}.",
                              "Request a clearer copy from the vendor"))

    net_factor = 1.0 / (1.0 + (rate or company["tax_rate"])) if incl else 1.0
    money = {"subtotal": subtotal, "tax": tax, "total": total,
             "net_amount": None if subtotal is None else round(subtotal * net_factor, 2), "net_factor": net_factor,
             "tax_inclusive": incl, "tax_rate": rate, "currency": currency, "invoice_date": str(inv_date)}
    blocking = [r for r in reasons if r.severity != "note"]
    summary = (blocking[0].message if blocking else
               f"{dt.replace('_', ' ').capitalize()} for {money_str(total)}; " + (checks[0] if checks else "checked"))
    details = {"document_type": dt, "line_sum": line_sum, **{k: money[k] for k in ("subtotal", "tax", "total")},
               "checks": checks}
    return StageResult("validate", stage_status(reasons), summary, details, reasons), money


def check_vendor(x, vendors, total=0.0):
    """Stage 4: match on tax ID, else fuzzy name/alias; then status, tax ID and bank account vs the master."""
    total = total or 0.0
    name, tax = fv(x, "vendor_name"), digits(fv(x, "vendor_tax_id"))
    vendor, how = next(((v, "tax ID") for v in vendors if tax and digits(v["tax_id"]) == tax), (None, None))
    if vendor is None and name:
        score, best = max(((max(similarity(name, n) for n in [v["name"], *v["aliases"]]), v) for v in vendors),
                          key=lambda t: t[0])
        if score >= 0.85:
            vendor, how = best, f"name ({score:.0%} match)"
    if vendor is None:
        r = Reason("VENDOR_NOT_FOUND", f"'{name or 'Unknown vendor'}' is not in the vendor master.",
                   "Send the vendor an onboarding request: W-9, bank verification letter, certificate of insurance")
        return StageResult("vendor", "fail", r.message, {"printed_name": name}, [r]), None
    reasons = []
    if how != "tax ID" and tax and digits(vendor["tax_id"]) != tax:
        reasons.append(Reason("TAX_ID_MISMATCH", f"Invoice shows tax ID {fv(x, 'vendor_tax_id')}; the vendor master has "
                              f"{vendor['tax_id']}. This is a common sign of an impersonated vendor.",
                              f"Do not pay. Call {vendor['name']} on {vendor['phone']} (number on file) to confirm",
                              amount_at_risk=total))
    if name and similarity(name, vendor["name"]) < 0.95:
        reasons.append(Reason("VENDOR_ALIAS_MATCHED", f"Printed as '{name}'; matched to {vendor['name']} by {how}."))
    if vendor["status"] == "blocked":
        reasons.append(Reason("VENDOR_BLOCKED", f"{vendor['name']} is blocked: {vendor.get('block_reason') or 'no reason given'}.",
                              "Reject; procurement owns any exception", amount_at_risk=total))
    acct, on_file = digits(fv(x, "remit_bank_account")), digits(vendor["bank"]["account"])
    if acct and acct != on_file:
        reasons.append(Reason("BANK_DETAILS_CHANGED", f"Invoice asks for payment to account ending {acct[-4:]}; the vendor "
                              f"master has account ending {on_file[-4:]}.",
                              f"Do not pay. Verify by calling {vendor['phone']} (the number on file), never the number "
                              "on the invoice", amount_at_risk=total))
    details = {"vendor_id": vendor["id"], "vendor_name": vendor["name"], "matched_by": how, "status": vendor["status"],
               "bank_on_file_last4": on_file[-4:], "bank_on_invoice_last4": acct[-4:] if acct else None}
    blocking = [r for r in reasons if r.severity != "note"]
    summary = blocking[0].message if blocking else f"{vendor['name']} ({vendor['id']}), matched by {how}; bank on file"
    return StageResult("vendor", stage_status(reasons), summary, details, reasons), vendor


def norm_po(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def desc_similarity(desc, po_desc):
    """Best of the whole description and each of its lines: readers often append serial, lot or asset lines."""
    return max(similarity(part, po_desc) for part in [desc, *str(desc or "").splitlines()])


def _line_match_score(lines, po_lines):
    if not lines:
        return 0.0
    skus = {norm_po(pl.get("sku")) for pl in po_lines if pl.get("sku")}
    hits = 0
    for li in lines:
        if li.get("sku") and norm_po(li["sku"]) in skus:
            hits += 1
        elif li.get("description") and max((desc_similarity(li["description"], pl["desc"]) for pl in po_lines), default=0) >= 0.85:
            hits += 1
    return hits / len(lines)


def rank_pos(x, vendor, ref, money):
    amount = money.get("net_amount") or 0.0
    out = []
    for p in ref["pos"].values():
        if p["vendor_id"] != vendor["id"] or p["status"] != "open":
            continue
        lines = _line_match_score(x["line_items"], p["lines"])
        closeness = max(0.0, 1 - abs(amount - p["total"]) / max(p["total"], 1.0))
        out.append({"po_number": p["po_number"], "score": round(0.6 * lines + 0.4 * closeness, 3),
                    "lines": round(lines, 3), "amount": round(closeness, 3)})
    return sorted(out, key=lambda c: -c["score"])


def match_po(x, vendor, ref, money):
    """Stage 5: printed (or handwritten) PO must exist, belong to this vendor and be open; otherwise infer one."""
    printed, hand = fv(x, "po_number"), fv(x, "po_number_handwritten")
    wanted = printed or hand
    by_norm = {norm_po(k): p for k, p in ref["pos"].items()}
    names = {v["id"]: v["name"] for v in ref["vendors"]}
    if wanted:
        p = by_norm.get(norm_po(wanted))
        if p is None and printed and hand and by_norm.get(norm_po(hand)):
            # The "printed PO" is some other reference (customer/order no.) that is not a PO; the pen note is.
            p, printed = by_norm[norm_po(hand)], None
        if p and p["vendor_id"] != vendor["id"]:
            r = Reason("PO_INVALID", f"{p['po_number']} belongs to {names.get(p['vendor_id'], p['vendor_id'])}, "
                       f"not {vendor['name']}.", "Ask the buyer for the correct PO")
            return StageResult("po_match", "fail", r.message, {"po_number": p["po_number"]}, [r]), None
        if p and p["status"] != "open":
            r = Reason("PO_INVALID", f"{p['po_number']} is closed.", "Ask the buyer to issue a new PO or reopen this one")
            return StageResult("po_match", "fail", r.message, {"po_number": p["po_number"]}, [r]), None
        if p:
            reasons = [] if printed else [Reason("PO_FROM_ANNOTATION", f"No PO printed; using {p['po_number']}, "
                                                 "written by hand on the document.")]
            summary = f"{p['po_number']}: {p['type']} PO for {money_str(p['total'])}"
            return StageResult("po_match", stage_status(reasons), summary,
                               {"po_number": p["po_number"], "source": "printed" if printed else "handwritten"},
                               reasons), p
    pol = ref["policy"]
    cands = rank_pos(x, vendor, ref, money)
    if cands and cands[0]["score"] >= pol["po_infer_min_score"] and (
            len(cands) == 1 or cands[0]["score"] - cands[1]["score"] >= pol["po_infer_margin"]):
        p = ref["pos"][cands[0]["po_number"]]
        why = f"'{wanted}' does not exist; " if wanted else "No PO printed; "
        r = Reason("PO_INFERRED", why + f"matched {p['po_number']} from the line items (score {cands[0]['score']:.2f}).")
        return StageResult("po_match", "warn", r.message, {"po_number": p["po_number"], "source": "inferred",
                                                          "candidates": cands[:3]}, [r]), p
    top = cands[:3]
    if wanted:
        r = Reason("PO_INVALID", f"PO '{wanted}' does not exist and no open PO matches the line items.",
                   "Ask the buyer for the correct PO")
    elif top:
        r = Reason("PO_NOT_IDENTIFIED", "No PO printed, and the line items fit more than one open PO: " +
                   ", ".join(c["po_number"] for c in top) + ".", "Ask the buyer which PO this invoice is for")
    else:
        r = Reason("PO_NOT_IDENTIFIED", f"No PO printed and {vendor['name']} has no open PO matching these lines.",
                   "Ask the buyer which PO this invoice is for")
    return StageResult("po_match", "fail", r.message, {"candidates": top}, [r]), None


BILLED_STATUSES = ("approved", "paid")


def _match_line(li, po_lines, price_tol_pct, net_factor):
    """Same SKU wins. A different printed SKU only matches on a near-identical description AND price
    (an OCR slip, not a substitution). No SKU: best description match."""
    sku = norm_po(li.get("sku"))
    if sku:
        for pl in po_lines:
            if norm_po(pl.get("sku")) == sku:
                return pl
    if not po_lines:
        return None
    best = max(po_lines, key=lambda pl: desc_similarity(li.get("description"), pl["desc"]))
    sim = desc_similarity(li.get("description"), best["desc"])
    if not sku:
        return best if sim >= 0.6 else None
    price = li.get("unit_price")
    if sim >= 0.9 and price is not None and abs(price * net_factor - best["unit_price"]) <= best["unit_price"] * price_tol_pct / 100:
        return best
    return None


def three_way_match(x, money, po, ref):
    """Stage 6: PO balance (all POs), then line prices, quantities vs goods received, unplanned and bundled lines."""
    pol, reasons = ref["policy"], []
    po_no = po["po_number"]
    billed_by = [{"invoice_number": e["invoice_number"], "invoice_date": e["invoice_date"], "amount": e["subtotal"] or 0,
                  "status": e["status"], "run_id": e.get("run_id")}
                 for e in ref["ledger"] if e["po_number"] == po_no and e["status"] in BILLED_STATUSES]
    if po.get("opening_billed"):
        billed_by.insert(0, {"invoice_number": None, "invoice_date": None, "amount": po["opening_billed"], "status": "opening balance",
                             "run_id": None})
    billed = sum(b["amount"] for b in billed_by)
    this = money["net_amount"] or 0.0
    after = billed + this
    if after > po["total"] + total_tolerance(po["total"], pol):
        over, remaining = round(after - po["total"], 2), round(max(po["total"] - billed, 0.0), 2)
        reasons.append(Reason("PO_OVERRUN", f"{po_no} is {money_str(po['total'])} and {money_str(billed)} is already billed. "
                              f"This invoice ({money_str(this)}) takes it to {money_str(after)}, {money_str(over)} over.",
                              f"Approve the {money_str(remaining)} left on the PO and ask the vendor for a "
                              f"{money_str(over)} credit note", amount_at_risk=over))
    details = {"po_number": po_no, "po_total": po["total"], "billed_before": round(billed, 2), "this_invoice": this,
               "after": round(after, 2), "billed_by": billed_by, "lines": []}
    if po.get("type") == "blanket":
        summary = reasons[0].message if reasons else (f"Blanket PO: {money_str(billed)} billed before, "
                                                      f"{money_str(after)} after, of {money_str(po['total'])}")
        return StageResult("three_way", stage_status(reasons), summary, details, reasons)

    receipts = ref["receipts"].get(po_no)  # None for services: treated as received
    ordered, billed_qty, price_of = {}, {}, {}
    for pl in po["lines"]:
        ordered[pl["sku"]] = ordered.get(pl["sku"], 0) + pl["qty"]
    unmatched, matched_any = [], False
    for li in x["line_items"]:
        pl = _match_line(li, po["lines"], pol["price_tolerance_pct"], money["net_factor"])
        row = {"description": li.get("description"), "qty": li.get("qty"), "unit_price": li.get("unit_price"),
               "amount": li.get("amount"), "po_sku": pl["sku"] if pl else None}
        details["lines"].append(row)
        if pl is None:
            unmatched.append(li)
            continue
        matched_any = True
        if li.get("unit_price") is not None and pl["unit_price"]:
            net_price = li["unit_price"] * money["net_factor"]
            diff = (net_price - pl["unit_price"]) / pl["unit_price"] * 100
            row["price_diff_pct"] = round(diff, 2)
            if diff > pol["price_tolerance_pct"]:
                extra = round((net_price - pl["unit_price"]) * (li.get("qty") or 0), 2)
                reasons.append(Reason("PRICE_VARIANCE", f"{li.get('description')}: billed {money_str(net_price)} vs PO "
                                      f"{money_str(pl['unit_price'])} (+{diff:.1f}%, limit {pol['price_tolerance_pct']:g}%).",
                                      f"Ask the vendor for a {money_str(extra)} credit note, or have the buyer approve "
                                      "the new price", amount_at_risk=extra))
            elif abs(diff) > 0.5:
                reasons.append(Reason("PRICE_VARIANCE_WITHIN_TOLERANCE", f"{li.get('description')}: {diff:+.1f}% vs the "
                                      f"PO price, within the {pol['price_tolerance_pct']:g}% tolerance."))
        billed_qty[pl["sku"]] = billed_qty.get(pl["sku"], 0) + (li.get("qty") or 0)
        price_of[pl["sku"]] = pl["unit_price"]
    if receipts is not None:
        for sku, q in billed_qty.items():
            rec = receipts.get(sku, 0)
            if q > rec + 1e-6:
                amt = round((q - rec) * price_of[sku], 2)
                reasons.append(Reason("QTY_NOT_RECEIVED", f"{sku}: billed {q:g}, but only {rec:g} received.",
                                      f"Pay for the {rec:g} received and ask the vendor to credit {money_str(amt)}",
                                      amount_at_risk=amt))
            elif q < ordered.get(sku, 0) - 1e-6:
                reasons.append(Reason("PARTIAL_DELIVERY", f"{sku}: {q:g} of {ordered[sku]:g} ordered billed, matching "
                                      f"the {rec:g} received. The rest stays open on the PO."))
    if unmatched and not matched_any and abs(this - po["total"]) <= total_tolerance(po["total"], pol):
        reasons.append(Reason("BUNDLED_LINES", f"{len(unmatched)} bundled line(s) billed against {len(po['lines'])} PO "
                              f"lines; the amount {money_str(this)} matches the PO total."))
        unmatched = []
    credits = [li for li in unmatched if (li.get("amount") or 0) < 0]
    extras = [li for li in unmatched if (li.get("amount") or 0) >= 0]
    if credits:
        reasons.append(Reason("UNMATCHED_CREDIT_LINE", "Credit not on the PO (reduces the amount payable): " +
                              ", ".join(f"{li.get('description')} ({money_str(li.get('amount'))})" for li in credits) + "."))
    if extras:
        extra_sum = round(sum(li.get("amount") or 0 for li in extras) * money["net_factor"], 2)
        listed = ", ".join(f"{li.get('description')} ({money_str(li.get('amount'))})" for li in extras)
        if extra_sum <= pol["total_tolerance_abs"]:
            reasons.append(Reason("UNMATCHED_LINE_WITHIN_TOLERANCE", f"Not on {po_no} but under the "
                                  f"{money_str(pol['total_tolerance_abs'])} allowance: {listed}."))
        else:
            reasons.append(Reason("UNMATCHED_LINE", f"Not on {po_no}: {listed}.",
                                  "Buyer to approve the extra charge, or ask the vendor to remove it",
                                  amount_at_risk=extra_sum))
    blocking = [r for r in reasons if r.severity != "note"]
    summary = blocking[0].message if blocking else (f"{len(x['line_items'])} line(s) match {po_no} on price and "
                                                    f"quantity; {money_str(after)} of {money_str(po['total'])} billed")
    return StageResult("three_way", stage_status(reasons), summary, details, reasons)


def _line_similarity(lines, ledger_lines):
    """Share of lines that pair up on amount (to the cent) and a similar description."""
    if not lines or not ledger_lines:
        return 0.0
    pool = [(round(l["qty"] * l["unit_price"], 2), l["desc"]) for l in ledger_lines]
    hits = 0
    for li in lines:
        for j, (amt, desc) in enumerate(pool):
            if li.get("amount") is not None and abs(amt - li["amount"]) <= 0.01 and similarity(li.get("description"), desc) >= 0.6:
                hits += 1
                pool.pop(j)
                break
    return hits / max(len(lines), len(ledger_lines))


def _original(e):
    return {k: e.get(k) for k in ("id", "run_id", "invoice_number", "invoice_date", "total", "status")}


def check_duplicates(x, money, vendor, ref):
    """Stage 7: exact (vendor + normalised number, any status) then fuzzy (amount, date window, lines)."""
    pol = ref["policy"]
    inv_no = fv(x, "invoice_number")
    key = norm_invoice_no(inv_no) if inv_no else None
    mine = [e for e in ref["ledger"] if e["vendor_id"] == vendor["id"]]
    for e in mine:
        if key and norm_invoice_no(e["invoice_number"]) == key:
            r = Reason("DUPLICATE", f"{e['invoice_number']} dated {e['invoice_date']} is already in the ledger ({e['status'].replace('_', ' ')}).",
                       "Reject and tell the vendor it was already processed", amount_at_risk=money.get("total") or 0.0)
            return StageResult("duplicates", "fail", r.message, {"original": _original(e)}, [r])
    total, inv_date = money.get("total"), parse_date(money.get("invoice_date"))
    notes = []
    for e in mine:
        if total is None or e["total"] is None or not inv_date or not parse_date(e["invoice_date"]):
            continue
        if abs(e["total"] - total) > pol["fuzzy_dup_amount_pct"] / 100 * max(abs(total), abs(e["total"])) + 0.005:
            continue
        days = abs((inv_date - parse_date(e["invoice_date"])).days)
        if days > pol["duplicate_window_days"]:
            continue
        if _line_similarity(x["line_items"], e["lines"]) < pol["fuzzy_dup_line_similarity"]:
            continue
        sp, esp = fv(x, "service_period"), e.get("service_period")
        if sp and esp and norm_text(sp) != norm_text(esp):
            notes.append(Reason("RECURRING_CHARGE_NOT_DUPLICATE", f"Same {money_str(total)} as {e['invoice_number']} "
                                f"({esp}), but this one is for {sp}: a new period, not a duplicate."))
            continue
        r = Reason("PROBABLE_DUPLICATE", f"Same amount and near-identical lines as {e['invoice_number']} "
                   f"({e['status'].replace('_', ' ')}), {days} days apart, under a different invoice number.",
                   "Compare with the original side by side; reject if it is the same delivery", amount_at_risk=total)
        return StageResult("duplicates", "fail", r.message, {"original": _original(e)}, [r])
    summary = notes[0].message if notes else f"No earlier invoice from {vendor['name']} matches ({len(mine)} checked)"
    return StageResult("duplicates", stage_status(notes), summary, {"checked": len(mine)}, notes)


def decide(stages, money):
    """Stage 8: REJECT beats HOLD beats APPROVE; the primary reason sets the owner and next action."""
    reasons = sorted((r for s in stages for r in s.reasons), key=lambda r: PRIORITY[r.code])
    blocking = [r for r in reasons if r.severity != "note"]
    decision = "REJECT" if any(r.severity == "reject" for r in blocking) else "HOLD" if blocking else "APPROVE"
    primary = blocking[0] if blocking else None
    if primary:
        next_action = primary.action or f"{primary.owner} to review"
    else:
        next_action = f"Schedule {money_str((money or {}).get('total'))} for payment"
    return {"decision": decision, "primary": primary.to_dict() if primary else None,
            "reasons": [r.to_dict() for r in reasons], "owner": primary.owner if primary else None,
            "next_action": next_action,
            "amount_at_risk": round(max((r.amount_at_risk for r in blocking), default=0.0), 2)}


def apply_bank_reread(x, second_account, on_file):
    """Scanned documents only: a second read of the remit-to account. Fails closed: the first read is replaced only when
    the second read matches the account on file exactly; a different or empty second read keeps the first read (and
    so the BANK_DETAILS_CHANGED hold). Returns (extraction, cleared)."""
    if not second_account or digits(second_account) != digits(on_file):
        return x, False
    fields = dict(x["fields"])
    fields["remit_bank_account"] = {"value": second_account, "confidence": "medium", "source_text": second_account}
    return {**x, "fields": fields}, True
