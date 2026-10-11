from app import rules
from tests.conftest import fresh_ref, money_of, truth_x

REF = fresh_ref()


def match(file, ref=REF):
    x = truth_x(file)
    m = money_of(x)
    _, v = rules.check_vendor(x, ref["vendors"])
    _, p = rules.match_po(x, v, ref, m)
    return rules.three_way_match(x, m, p, ref)


def codes(st):
    return sorted(r.code for r in st.reasons)


def test_clean_lines_pass():
    for f in ("01_greenleaf_clean.pdf", "06_lakeshore_weekly_multipage.pdf", "11_packright_unit_price_rounding.pdf",
              "03_sparkle_clean.pdf", "20_lakeshore_scan_multipage.pdf"):
        assert codes(match(f)) == [], f


def test_blanket_po_balance():
    assert codes(match("04_northgate_blanket_within_balance.pdf")) == []
    st = match("26_northgate_po_overrun.pdf")
    assert codes(st) == ["PO_OVERRUN"]
    r = st.reasons[0]
    assert r.amount_at_risk == 3000.0 and "$12,000.00" in r.action and "$3,000.00" in r.action


def test_overrun_counts_approved_runs_not_holds():
    ref = fresh_ref()
    ref["ledger"].append({"vendor_id": "V004", "invoice_number": "NG-0303", "invoice_date": "2026-10-01",
                          "po_number": "PO-1043", "subtotal": 9000.0, "total": 9000.0, "status": "approved",
                          "service_period": None, "lines": []})
    assert codes(match("27_northgate_split_second_in_batch.pdf", ref)) == ["PO_OVERRUN"]
    ref["ledger"][-1]["status"] = "on_hold"
    assert codes(match("27_northgate_split_second_in_batch.pdf", ref)) == []


def test_price_tolerance():
    assert codes(match("33_packright_price_within_tolerance.pdf")) == ["PRICE_VARIANCE_WITHIN_TOLERANCE"]
    assert codes(match("34_packright_price_over_tolerance.pdf")) == ["PRICE_VARIANCE"]


def test_quantity_vs_receipts():
    assert codes(match("35_packright_billed_more_than_received.pdf")) == ["QTY_NOT_RECEIVED"]
    assert codes(match("12_lakeshore_partial_delivery.pdf")) == ["PARTIAL_DELIVERY", "PARTIAL_DELIVERY"]


def test_unplanned_lines():
    assert codes(match("36_beverage_small_keg_deposit.pdf")) == ["UNMATCHED_LINE_WITHIN_TOLERANCE"]
    assert "UNMATCHED_LINE" in codes(match("37_beverage_unplanned_fuel_surcharge.pdf"))
    assert "UNMATCHED_LINE" in codes(match("38_lakeshore_substituted_item.pdf"))
    assert codes(match("13_beverage_promo_credit_line.pdf")) == ["UNMATCHED_CREDIT_LINE"]


def test_bundled_line_and_tax_inclusive():
    assert codes(match("39_bluewave_bundled_project_line.pdf")) == ["BUNDLED_LINES"]
    assert codes(match("28_packright_photo_no_po_tax_inclusive.pdf")) == []


def test_asset_or_serial_line_in_description_still_matches_the_po_line():
    x = truth_x("03_sparkle_clean.pdf")
    for li in x["line_items"]:
        li["sku"], li["description"] = None, f"Asset tag CPL-EQ-000417 / serial 88A-2291-K\n{li['description']}"
    m = money_of(x)
    _, v = rules.check_vendor(x, REF["vendors"])
    _, p = rules.match_po(x, v, REF, m)
    assert codes(rules.three_way_match(x, m, p, REF)) == []
