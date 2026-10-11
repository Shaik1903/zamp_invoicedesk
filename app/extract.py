"""AI reads: Gemini turns a document into the Extraction contract, and writes the plain-English
summary/email for a decision that is already final. Nothing here decides anything."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from app.rules import FIELD_NAMES, fv, money_str

log = logging.getLogger("invoicedesk.extract")
Conf = Literal["high", "medium", "low"]
RETRYABLE = {429, 500, 502, 503, 504}


class ExtractionError(Exception):
    pass


def load_env(path=".env"):
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class TextField(BaseModel):
    value: Optional[str]
    confidence: Conf
    source_text: Optional[str]


class NumberField(BaseModel):
    value: Optional[float]
    confidence: Conf
    source_text: Optional[str]


class BoolField(BaseModel):
    value: Optional[bool]
    confidence: Conf
    source_text: Optional[str]


class LineItem(BaseModel):
    sku: Optional[str]
    description: Optional[str]
    qty: Optional[float]
    unit_price: Optional[float]
    amount: Optional[float]
    confidence: Conf
    source_text: Optional[str]


# No default values anywhere: the Gemini API rejects defaults in response schemas. Every key is required
# and may be null, so the model always returns the full shape.
class InvoiceExtraction(BaseModel):
    document_type: Literal["invoice", "credit_note", "quote", "statement", "other"]
    document_count: int
    vendor_name: TextField
    vendor_tax_id: TextField
    vendor_address: TextField
    remit_bank_account: TextField
    remit_bank_routing: TextField
    invoice_number: TextField
    invoice_date: TextField
    due_date: TextField
    po_number: TextField
    po_number_handwritten: TextField
    bill_to_name: TextField
    ship_to: TextField
    currency: TextField
    service_period: TextField
    subtotal: NumberField
    tax_amount: NumberField
    tax_rate: NumberField
    prices_include_tax: BoolField
    total: NumberField
    line_items: list[LineItem]
    stamps: list[str]


class BankRead(BaseModel):
    account: Optional[str]
    routing: Optional[str]
    digit_count: Optional[int]
    source_text: Optional[str]


class Writeup(BaseModel):
    summary: str
    email_to: Optional[str]
    email_subject: Optional[str]
    email_body: Optional[str]


class Box(BaseModel):
    key: str
    box_2d: Optional[list[int]]


class Boxes(BaseModel):
    boxes: list[Box]


LOCATE_PROMPT = """Locate each value below on this document image. Return one entry per key with box_2d =
[ymin, xmin, ymax, xmax] normalised to 0-1000 (top-left origin), drawn tightly around the printed value only;
box_2d is null if the value is not visible on this page. Values (key: text):
"""


PROMPT = """You are the data-entry clerk of an accounts-payable team. Read the document and fill in the schema.
Rules:
- Copy exactly what is printed. Never infer, compute or guess a missing value: use null.
- document_type: invoice | credit_note (credit memo) | quote (quotation/estimate) | statement (statement of account) | other.
  For a quote or statement, invoice_number and invoice_date are the quote/statement number and date.
- document_count: how many separate invoices or documents the file contains.
- Dates as YYYY-MM-DD, with source_text = the date exactly as printed. Numeric dates from US vendors are month-first:
  10/02/26 is 2026-10-02 and 09/28/2026 is 2026-09-28; a two-digit year means 20YY. Read a numeric date day-first only
  when the vendor is Canadian (C$/CAD, Canadian address) or the first number is above 12.
- Money as plain numbers, no currency symbols or thousands separators. Credits are negative.
- Copy every amount as written even when the arithmetic does not add up: never correct a total, subtotal or line to
  make it reconcile. Wrong or missing arithmetic is exactly what the downstream checks need to see.
- total: the grand total printed on the document (Total, Total Due, Amount Due, Balance Due). If no total line is
  printed, total is null even if it would equal the subtotal: never copy the subtotal into total and never add
  numbers up yourself.
- tax_amount: only a tax amount printed on its own line; never derive it as total minus subtotal.
- tax_rate as a fraction (10.25% -> 0.1025). prices_include_tax is true only if the document says prices include tax.
- currency as an ISO code. "$" alone means USD; "C$" or "CAD" means CAD.
- po_number: the purchase-order number printed by the vendor (labelled PO, P.O. or Purchase Order). On a handwritten
  invoice form, what the vendor wrote in the form's own boxes (for example "PO / JOB") counts as printed: put it here.
  Never a customer number, account number, order number, job number or rental agreement number. Return the PO number
  itself only (for example PO-1119), without job text or words written after it.
- po_number_handwritten: only a PO number that someone else added later in pen on top of a typed or printed invoice
  (an annotation); null if there is none. Same format rule as po_number.
- remit_bank_account / remit_bank_routing: the account and routing/transit number the vendor asks to be paid into.
- Digit-critical fields (remit_bank_account, remit_bank_routing, po_number, po_number_handwritten, invoice_number,
  vendor_tax_id): read them character by character and copy every character, including repeated digits
  ("77", "00", "11"); count the digits and make value and source_text identical. If the page is rotated or
  sideways, read it in its own orientation. Set confidence "low" whenever any single character is uncertain.
- bill_to_name: the company being billed (first line of the bill-to / sold-to block).
- service_period: the period a recurring service covers (for example "October 2026") if printed.
- stamps: the text of any rubber stamps (PAID, RECEIVED ...). They are not invoice data.
- line_items: every billed line in order, including fees, deposits and credits.
  qty is the billed quantity that unit_price is charged on, so qty x unit_price = amount. When an item is priced per
  LB/KG, qty is the shipped weight, not the piece count (PCS), case count or ordered quantity.
  sku: the vendor's item/product code only, not an asset tag, serial number or lot number (null if there is no item code).
  description: the item description text only, without serial numbers, lot numbers or asset tags.
- confidence per value: high = clearly printed and read; medium = readable but partly obscured or unusual;
  low = you cannot read it reliably. If a value is illegible return null with low confidence instead of guessing.
- source_text: the exact characters you read for that value."""

BANK_REREAD_PROMPT = """Find the remittance / payment instructions on this document (where the vendor asks to be paid).
Read the bank ACCOUNT number and the ROUTING / ABA / transit number character by character, including every repeated
digit. The page may be rotated or sideways. Copy only what is printed; null if absent. Report digit_count = the number of
digits you counted in the account number."""

WRITEUP_PROMPT = """You write short, plain-English notes for an accounts-payable team. A rules engine has already made the
decision below; do not change, soften or second-guess it, and use only the facts given.
Return: summary (2-3 sentences a non-technical manager understands), email_to (who should act: use the owner),
email_subject, email_body (a polite, specific email to that owner asking for the next action; sign it
"Copperleaf Accounts Payable"). Facts:
"""


async def with_retry(call, is_retryable, tries=4, base=1.0):
    for attempt in range(tries):
        try:
            return await call()
        except Exception as e:  # noqa: BLE001 - classified below
            if is_retryable(e) and attempt < tries - 1:
                await asyncio.sleep(base * 2 ** attempt + random.random() * base)
                continue
            raise ExtractionError(f"{type(e).__name__}: {str(e)[:200]}") from e


NUM_DATE = re.compile(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})\s*$")


def fix_dates(x):
    """Re-derive numeric dates from the printed text (source_text) instead of trusting the model's conversion:
    month-first (US) unless a number > 12 settles it or the invoice is in CAD (day-first)."""
    day_first = str(fv(x, "currency") or "").upper() == "CAD"
    for name in ("invoice_date", "due_date"):
        f = x["fields"][name]
        m = NUM_DATE.match(f.get("source_text") or "")
        if not m:
            continue
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 100 else 0
        mo, d = (b, a) if a > 12 or (day_first and b <= 12) else (a, b)
        try:
            f["value"] = date(y, mo, d).isoformat()
        except ValueError:
            f["value"], f["confidence"] = None, "low"
    return x


def to_internal(p):
    d = p.model_dump()
    return fix_dates({"document_type": d["document_type"], "document_count": max(1, d.get("document_count") or 1),
                      "fields": {n: d[n] for n in FIELD_NAMES}, "line_items": d["line_items"], "stamps": d["stamps"] or []})


OWNER_TO = {"Vendor": "{vendor}, accounts receivable", "Buyer": "Purchasing (buyer for this PO)",
            "Security": "Finance controller (payment security)", "Procurement": "Procurement (vendor onboarding)",
            "AP clerk": "Accounts payable team"}


def template_writeup(decision, vendor_name, invoice_number, total):
    who, ref = vendor_name or "Unknown vendor", invoice_number or "(no number)"
    if decision["decision"] == "APPROVE":
        notes = " ".join(r["message"] for r in decision["reasons"])
        return {"summary": f"Approved: {who} invoice {ref} for {money_str(total)} matches its PO and goods received."
                           + (f" Notes: {notes}" if notes else ""), "email_to": None, "email_subject": None, "email_body": None}
    p = decision["primary"]
    others = " ".join(r["message"] for r in decision["reasons"] if r["severity"] != "note" and r["code"] != p["code"])
    verb = "Rejected" if decision["decision"] == "REJECT" else "On hold"
    summary = f"{verb}: {p['title']}. {p['message']}" + (f" Also: {others}" if others else "")
    to = OWNER_TO.get(p["owner"], p["owner"] or "Accounts payable team").format(vendor=who)
    if p["owner"] == "Vendor":
        body = (f"Hello,\n\nWe cannot pay invoice {ref} ({money_str(total)}) yet.\n\nReason: {p['message']}\n\n"
                f"Next step: {decision['next_action']}.\n\nThank you,\nCopperleaf Accounts Payable")
    else:
        body = (f"Hi,\n\n{who} invoice {ref} ({money_str(total)}) is {verb.lower()}.\n\nReason: {p['message']}\n\n"
                f"Please: {decision['next_action']}.\n\nThanks,\nCopperleaf Accounts Payable")
    return {"summary": summary, "email_to": to, "email_subject": f"Invoice {ref} from {who}: {p['title']}", "email_body": body}


class GeminiExtractor:
    name = "gemini"

    def __init__(self, api_key=None, model=None, summary_model=None, reread_model=None):
        from google import genai

        self.client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.reread_model = reread_model or os.getenv("GEMINI_REREAD_MODEL", "gemini-3.8-flash")
        self.summary_model = summary_model or os.getenv("GEMINI_SUMMARY_MODEL", "gemini-3.5-flash-lite")

    @staticmethod
    def _retryable(e):
        from google.genai import errors

        return isinstance(e, errors.APIError) and getattr(e, "code", None) in RETRYABLE

    async def _generate(self, model, contents, schema):
        from google.genai import types

        # HIGH: at the default resolution Gemini downsamples PDF pages and drops repeated digits in bank accounts.
        # No thinking_config: every model runs with its default thinking.
        cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0,
                                          media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH)

        async def call():
            resp = await self.client.aio.models.generate_content(model=model, contents=contents, config=cfg)
            if resp.parsed is None:
                raise ExtractionError("model returned no parseable JSON")
            return resp.parsed

        return await with_retry(call, self._retryable)

    async def extract(self, *, data, mime, layout_text, filename):
        from google.genai import types

        doc = (f"Document text (layout preserved):\n{layout_text}" if layout_text
               else types.Part.from_bytes(data=data, mime_type=mime))
        parsed = await self._generate(self.model, [PROMPT, doc], InvoiceExtraction)
        return to_internal(parsed)

    async def reread_bank(self, *, data, mime, filename):
        """Second, narrow read of the remit-to account by a stronger model. It never sees the account on file."""
        from google.genai import types

        b = await self._generate(self.reread_model, [BANK_REREAD_PROMPT, types.Part.from_bytes(data=data, mime_type=mime)],
                                 BankRead)
        return b.model_dump()

    async def locate(self, *, data, mime, targets):
        from google.genai import types

        listing = "\n".join(f"{t['key']}: {t['text']}" for t in targets)
        r = await self._generate(self.summary_model, [LOCATE_PROMPT + listing, types.Part.from_bytes(data=data, mime_type=mime)], Boxes)
        return [{"key": b.key, "box": b.box_2d} for b in r.boxes if b.box_2d and len(b.box_2d) == 4]

    async def summarize(self, *, decision, vendor_name, invoice_number, total):
        facts = json.dumps({"decision": decision["decision"], "owner": decision["owner"], "next_action": decision["next_action"],
                            "reasons": [{k: r[k] for k in ("title", "message", "severity")} for r in decision["reasons"]],
                            "vendor": vendor_name, "invoice_number": invoice_number, "total": total})
        w = await self._generate(self.summary_model, [WRITEUP_PROMPT + facts], Writeup)
        return w.model_dump()
