import asyncio
import os

import pytest

from app import extract
from app.truth import TruthExtractor
from tests.conftest import FIX_DIR, MANIFEST

DEC_HOLD = {"decision": "HOLD", "next_action": "Ask the vendor for a corrected invoice", "owner": "Vendor",
            "primary": {"code": "ARITHMETIC_MISMATCH", "severity": "hold", "owner": "Vendor",
                        "title": "Line items, tax and total do not add up", "message": "Lines add up to $813.00 but the total says $903.00.",
                        "action": "Ask the vendor for a corrected invoice", "amount_at_risk": 0.0},
            "reasons": [], "amount_at_risk": 0.0}


def test_template_writeup_hold_goes_to_vendor_and_approve_has_no_email():
    DEC_HOLD["reasons"] = [DEC_HOLD["primary"]]
    w = extract.template_writeup(DEC_HOLD, "GreenLeaf Produce Co.", "INV-GL-2237", 903.0)
    assert w["summary"].startswith("On hold") and "GreenLeaf" in w["email_to"] and "INV-GL-2237" in w["email_subject"]
    ok = extract.template_writeup({"decision": "APPROVE", "primary": None, "reasons": [], "next_action": "Schedule $5.00",
                                   "owner": None, "amount_at_risk": 0.0}, "V", "1", 5.0)
    assert ok["summary"].startswith("Approved") and ok["email_body"] is None


def test_with_retry_retries_then_succeeds_and_gives_up_on_fatal():
    calls = {"n": 0}

    class Busy(Exception):
        pass

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Busy()
        return "ok"

    assert asyncio.run(extract.with_retry(flaky, lambda e: isinstance(e, Busy), base=0.001)) == "ok"
    assert calls["n"] == 3

    async def fatal():
        raise ValueError("bad request")

    with pytest.raises(extract.ExtractionError):
        asyncio.run(extract.with_retry(fatal, lambda e: False, base=0.001))


def test_to_internal_has_every_contract_key():
    blank = {"value": None, "confidence": "low", "source_text": None}
    p = extract.InvoiceExtraction.model_validate({
        "document_type": "invoice", "document_count": 1, "stamps": [],
        "line_items": [{"sku": None, "description": "x", "qty": None, "unit_price": None, "amount": 1.0,
                        "confidence": "high", "source_text": None}],
        **{n: dict(blank) for n in extract.FIELD_NAMES}})
    x = extract.to_internal(p)
    assert set(x) == {"document_type", "document_count", "fields", "line_items", "stamps"}
    assert set(x["fields"]) == set(extract.FIELD_NAMES) and x["document_count"] == 1


def test_truth_extractor_known_and_unknown_files():
    te = TruthExtractor(MANIFEST)
    x = asyncio.run(te.extract(data=b"", mime="application/pdf", layout_text=None, filename="01_greenleaf_clean.pdf"))
    assert x["fields"]["invoice_number"]["value"] == "INV-GL-2228"
    y = asyncio.run(te.extract(data=b"", mime="application/pdf", layout_text=None, filename="menu.pdf"))
    assert y["document_type"] == "other" and y["fields"]["total"]["value"] is None
    b = asyncio.run(te.reread_bank(data=b"", mime="application/pdf", filename="67_sparkle_bank_details_changed_scan.pdf"))
    assert b == {"account": "9917002456", "routing": "271070999", "digit_count": 10, "source_text": "9917002456"}
    assert asyncio.run(te.reread_bank(data=b"", mime="application/pdf", filename="menu.pdf"))["account"] is None


def test_fix_dates_reads_numeric_dates_from_the_printed_text():
    def x(printed, currency="USD"):
        return {"fields": {"invoice_date": {"value": "1999-01-01", "confidence": "high", "source_text": printed},
                           "due_date": {"value": None, "confidence": "high", "source_text": None},
                           "currency": {"value": currency, "confidence": "high", "source_text": currency}}}

    def inv(printed, currency="USD"):
        return extract.fix_dates(x(printed, currency))["fields"]["invoice_date"]

    assert inv("10/03/2026")["value"] == "2026-10-03"  # US: month first
    assert inv("10/02/26")["value"] == "2026-10-02"  # two-digit year means 20YY
    assert inv("04/10/2026", "CAD")["value"] == "2026-10-04"  # Canadian vendor: day first
    assert inv("28/09/2026")["value"] == "2026-09-28"  # a first number above 12 can only be the day
    assert inv("02/30/2026") == {"value": None, "confidence": "low", "source_text": "02/30/2026"}  # no such date
    assert inv("Sep 29, 2026")["value"] == "1999-01-01"  # not numeric: the model's value stands


@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="live Gemini smoke test needs GEMINI_API_KEY")
def test_live_gemini_reads_a_digital_and_a_scanned_invoice():
    from liteparse import LiteParse

    g = extract.GeminiExtractor()
    pdf = (FIX_DIR / "01_greenleaf_clean.pdf").read_bytes()
    text = LiteParse(ocr_enabled=False, output_format="text", quiet=True).parse(pdf).text
    scan = (FIX_DIR / "14_greenleaf_scan_clean.pdf").read_bytes()
    sideways = (FIX_DIR / "19_beverage_scan_rotated.pdf").read_bytes()

    async def main():  # one event loop: the client's async session cannot outlive the loop it was created on
        return (await g.extract(data=pdf, mime="application/pdf", layout_text=text, filename="01.pdf"),
                await g.extract(data=scan, mime="application/pdf", layout_text=None, filename="14.pdf"),
                await g.reread_bank(data=sideways, mime="application/pdf", filename="19.pdf"))

    x, y, b = asyncio.run(main())
    assert x["fields"]["invoice_number"]["value"] == "INV-GL-2228" and abs(x["fields"]["total"]["value"] - 1317.95) < 0.01
    assert y["fields"]["invoice_number"]["value"] == "INV-GL-2226"
    assert "".join(c for c in b["account"] if c.isdigit()) == "1530077742"  # the re-read model, sideways scan
