import json
from datetime import date

from app import rules
from tests.conftest import ROOT, SEED, xt

CO = SEED["company"]
TODAY, RECEIVED = date(2026, 10, 10), date(2026, 10, 9)
BASE = {"vendor_name": "GreenLeaf Produce Co.", "invoice_number": "INV-1", "invoice_date": "2026-10-01",
        "bill_to_name": "Copperleaf Restaurant Group", "currency": "USD"}


def codes(stage):
    return [r.code for r in stage.reasons]


def run(fields, lines, **kw):
    return rules.validate_document(xt({**BASE, **fields}, lines, **kw), CO, TODAY, RECEIVED)


def test_catalog_covers_answer_key_codes():
    manifest_codes = json.loads((ROOT / "fixtures" / "manifest.json").read_text())["reason_codes"]
    assert set(manifest_codes) | {"EXTRACTION_FAILED"} == set(rules.REASONS)


def test_clean_invoice_passes_and_reports_money():
    st, money = run({"subtotal": 100.0, "total": 100.0}, [("A", "Tomatoes", 4, 25.0)])
    assert st.status == "pass" and codes(st) == []
    assert money["total"] == 100.0 and money["net_amount"] == 100.0 and money["net_factor"] == 1.0


def test_printed_total_does_not_match_lines():
    st, _ = run({"subtotal": 813.0, "total": 903.0}, [("A", "x", 1, 813.0)])
    assert codes(st) == ["ARITHMETIC_MISMATCH"] and st.status == "fail"


def test_fractional_unit_price_reconciles():
    st, _ = run({"subtotal": 1000.08, "total": 1000.08}, [("PC", "Portion cup", 2400, 0.4167, 1000.08)])
    assert "ARITHMETIC_MISMATCH" not in codes(st)


def test_tax_inclusive_prices_back_out_tax():
    st, money = run({"subtotal": 110.25, "total": 110.25, "tax_amount": 10.25, "tax_rate": 0.1025,
                     "prices_include_tax": True}, [("A", "Box", 1, 110.25)])
    assert codes(st) == ["TAX_INCLUSIVE_PRICES"]
    assert abs(money["net_amount"] - 100.0) < 0.01 and money["tax_inclusive"]


def test_tax_amount_not_matching_rate():
    st, _ = run({"subtotal": 951.0, "tax_amount": 118.88, "tax_rate": 0.1025, "total": 1069.88},
                [("A", "x", 1, 951.0)])
    assert "TAX_MISMATCH" in codes(st)


def test_tax_rate_given_as_percent_is_normalised():
    st, _ = run({"subtotal": 100.0, "tax_amount": 10.25, "tax_rate": 10.25, "total": 110.25}, [("A", "x", 1, 100.0)])
    assert "TAX_MISMATCH" not in codes(st)


def test_missing_total_is_computed():
    st, money = run({"subtotal": 1060.0, "total": None}, [("A", "x", 1, 1060.0)])
    assert codes(st) == ["TOTAL_COMPUTED"] and money["total"] == 1060.0


def test_missing_date_defaults_and_future_date_holds():
    st, money = run({"invoice_date": None, "subtotal": 5.0, "total": 5.0}, [("A", "x", 1, 5.0)])
    assert codes(st) == ["DATE_DEFAULTED"] and money["invoice_date"] == "2026-10-09"
    st, _ = run({"invoice_date": "2026-12-15", "subtotal": 5.0, "total": 5.0}, [("A", "x", 1, 5.0)])
    assert codes(st) == ["INVALID_DATE"]


def test_missing_invoice_number_holds():
    st, _ = run({"invoice_number": None, "subtotal": 5.0, "total": 5.0}, [("A", "x", 1, 5.0)])
    assert codes(st) == ["MISSING_INVOICE_NUMBER"]


def test_other_company_and_foreign_currency():
    st, _ = run({"bill_to_name": "Copperhead Grill LLC", "subtotal": 5.0, "total": 5.0}, [("A", "x", 1, 5.0)])
    assert codes(st) == ["NOT_ADDRESSED_TO_US"]
    st, _ = run({"bill_to_name": "COPPERLEAF RESTAURANT GROUP", "currency": "CAD", "subtotal": 5.0, "total": 5.0},
                [("A", "x", 1, 5.0)])
    assert codes(st) == ["CURRENCY_NOT_SUPPORTED"]


def test_document_types_and_stamps():
    assert codes(run({"subtotal": -5.0, "total": -5.0}, [("A", "x", 1, -5.0)], doc_type="credit_note")[0]) == ["CREDIT_NOTE"]
    assert codes(run({"total": 14900.0}, [], doc_type="quote")[0]) == ["NOT_AN_INVOICE"]
    assert codes(run({"total": 1734.6}, [], doc_type="statement")[0]) == ["NOT_AN_INVOICE"]
    assert "MULTIPLE_DOCUMENTS" in codes(run({"subtotal": 5.0, "total": 5.0}, [("A", "x", 1, 5.0)], count=2)[0])
    assert codes(run({"subtotal": 5.0, "total": 5.0}, [("A", "x", 1, 5.0)], stamps=["PAID"])[0]) == ["STAMP_IGNORED"]


def test_low_confidence_on_money_holds():
    for name in ("total", "tax_amount"):
        x = xt({**BASE, "subtotal": 5.0, "tax_amount": 0.5, "tax_rate": 0.1, "total": 5.5}, [("A", "x", 1, 5.0)])
        x["fields"][name]["confidence"] = "low"
        st, _ = rules.validate_document(x, CO, TODAY, RECEIVED)
        assert "LOW_CONFIDENCE_EXTRACTION" in codes(st) and name in st.reasons[-1].message


def test_nothing_readable_holds():
    st, _ = rules.validate_document(xt({}, []), CO, TODAY, RECEIVED)
    assert "LOW_CONFIDENCE_EXTRACTION" in codes(st)


def test_unreadable_document_is_held_not_rejected_as_non_invoice():
    st, _ = rules.validate_document(xt({}, [], doc_type="other", conf="low"), CO, TODAY, RECEIVED)
    assert "LOW_CONFIDENCE_EXTRACTION" in codes(st) and "NOT_AN_INVOICE" not in codes(st)
    assert "uncertain" in st.reasons[-1].message and st.status == "fail"
    assert codes(run({"vendor_name": "Lou's Diner"}, [], doc_type="other")[0]) == ["NOT_AN_INVOICE"]


def test_grounding_downgrades_values_not_in_text():
    x = xt({**BASE, "total": 1317.95, "remit_bank_account": "300458817"}, [("A", "x", 1, 1317.95)])
    text = "INVOICE NO. INV-1 ... TOTAL DUE $1,317.95 ... Account No.: 300 458 817"
    g, unverified = rules.ground(x, text)
    assert unverified == [] and g["fields"]["total"]["confidence"] == "high"
    g, unverified = rules.ground(x, "INVOICE NO. INV-1 TOTAL DUE $1,371.95")
    assert "total" in unverified and g["fields"]["total"]["confidence"] == "low"
    assert x["fields"]["total"]["confidence"] == "high"  # input not mutated
