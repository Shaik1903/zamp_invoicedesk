from app import rules
from tests.conftest import fresh_ref, money_of, truth_x, xt

REF = fresh_ref()


def codes(st):
    return [r.code for r in st.reasons]


def vendor(file):
    x = truth_x(file)
    return rules.check_vendor(x, REF["vendors"], money_of(x)["total"])


def test_vendor_by_tax_id_clean():
    st, v = vendor("01_greenleaf_clean.pdf")
    assert v["id"] == "V001" and st.status == "pass" and codes(st) == []


def test_vendor_alias_name_noted():
    st, v = vendor("10_greenleaf_name_variant.pdf")
    assert v["id"] == "V001" and codes(st) == ["VENDOR_ALIAS_MATCHED"]


def test_vendor_matched_by_name_without_tax_id():
    st, v = vendor("21_handyman_handwritten_scan.pdf")
    assert v["id"] == "V010" and codes(st) == []


def test_unknown_blocked_bank_change_lookalike():
    st, v = vendor("49_harborview_unknown_vendor.pdf")
    assert v is None and codes(st) == ["VENDOR_NOT_FOUND"]
    st, v = vendor("48_rapidlinen_blocked_vendor.pdf")
    assert codes(st) == ["VENDOR_BLOCKED"]
    st, v = vendor("46_sparkle_bank_details_changed.pdf")
    assert codes(st) == ["BANK_DETAILS_CHANGED"] and st.reasons[0].amount_at_risk == 2145.0
    assert "555-0118" in st.reasons[0].action
    st, v = vendor("47_packright_lookalike_vendor.pdf")
    assert v["id"] == "V002" and set(codes(st)) == {"TAX_ID_MISMATCH", "BANK_DETAILS_CHANGED"}


def po(file):
    x = truth_x(file)
    _, v = rules.check_vendor(x, REF["vendors"])
    return rules.match_po(x, v, REF, money_of(x))


def test_printed_po_found():
    st, p = po("01_greenleaf_clean.pdf")
    assert p["po_number"] == "PO-1101" and st.status == "pass"


def test_po_of_other_vendor_and_closed_po_invalid():
    st, p = po("31_pest_wrong_vendor_po.pdf")
    assert p is None and codes(st) == ["PO_INVALID"] and "GreenLeaf" in st.reasons[0].message
    st, p = po("30_sparkle_closed_po.pdf")
    assert p is None and codes(st) == ["PO_INVALID"] and "closed" in st.reasons[0].message


def test_handwritten_po_used():
    st, p = po("24_greenleaf_no_po_handwritten_note.pdf")
    assert p["po_number"] == "PO-1046" and codes(st) == ["PO_FROM_ANNOTATION"]


def test_mistyped_po_inferred_and_missing_po_inferred():
    st, p = po("29_packright_po_typo.pdf")
    assert p["po_number"] == "PO-1124" and codes(st) == ["PO_INFERRED"]
    st, p = po("28_packright_photo_no_po_tax_inclusive.pdf")
    assert p is not None and codes(st) == ["PO_INFERRED"]


def test_ambiguous_standing_orders_not_identified():
    st, p = po("32_greenleaf_ambiguous_po.pdf")
    assert p is None and codes(st) == ["PO_NOT_IDENTIFIED"] and len(st.details["candidates"]) >= 2


def test_unknown_po_with_no_matching_lines_invalid():
    x = xt({"vendor_name": "GreenLeaf Produce Co.", "po_number": "PO-9999", "total": 10.0}, [("ZZ", "Gold bars", 1, 10.0)])
    st, p = rules.match_po(x, REF["vendors"][0], REF, money_of(x))
    assert p is None and codes(st) == ["PO_INVALID"]


def test_non_po_reference_falls_back_to_the_handwritten_po():
    x = truth_x("24_greenleaf_no_po_handwritten_note.pdf")
    x["fields"]["po_number"]["value"] = "CUST-20931"  # a customer number the reader took for the PO
    _, v = rules.check_vendor(x, REF["vendors"])
    st, p = rules.match_po(x, v, REF, money_of(x))
    assert p["po_number"] == "PO-1046" and codes(st) == ["PO_FROM_ANNOTATION"]


def test_serial_line_in_description_still_infers_the_po():
    assert rules.desc_similarity("Serial PKR-2026-0042-77812 / lot 22871-B\nCombi oven", "Combi oven") == 1.0
    x = truth_x("28_packright_photo_no_po_tax_inclusive.pdf")
    for li in x["line_items"]:
        li["sku"], li["description"] = None, f"Serial PKR-2026-0042-77812 / lot 22871-B\n{li['description']}"
    _, v = rules.check_vendor(x, REF["vendors"])
    st, p = rules.match_po(x, v, REF, money_of(x))
    assert p is not None and codes(st) == ["PO_INFERRED"]
