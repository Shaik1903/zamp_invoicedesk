from app import rules
from tests.conftest import fresh_ref, money_of, truth_x

REF = fresh_ref()


def dup(file, ref=REF):
    x = truth_x(file)
    m = money_of(x)
    _, v = rules.check_vendor(x, ref["vendors"])
    return rules.check_duplicates(x, m, v, ref)


def codes(st):
    return [r.code for r in st.reasons]


def test_exact_and_reformatted_duplicates():
    st = dup("40_greenleaf_exact_duplicate.pdf")
    assert codes(st) == ["DUPLICATE"] and st.details["original"]["invoice_number"] == "INV-GL-2207"
    assert codes(dup("41_greenleaf_duplicate_reformatted_number.pdf")) == ["DUPLICATE"]


def test_disguised_duplicate_and_recurring_charge():
    assert codes(dup("42_greenleaf_disguised_duplicate_rescan.pdf")) == ["PROBABLE_DUPLICATE"]
    assert codes(dup("05_bluewave_recurring_retainer_october.pdf")) == ["RECURRING_CHARGE_NOT_DUPLICATE"]


def test_new_invoice_is_not_a_duplicate():
    assert codes(dup("01_greenleaf_clean.pdf")) == []


def test_invoice_number_normalisation():
    assert rules.norm_invoice_no("INV GL 02207") == rules.norm_invoice_no("inv-gl-2207") == "INVGL2207"


def test_decide_precedence_owner_and_risk():
    hold = rules.StageResult("three_way", "fail", "", reasons=[rules.Reason("PO_OVERRUN", "m", "a", amount_at_risk=3000.0)])
    rej = rules.StageResult("duplicates", "fail", "", reasons=[rules.Reason("DUPLICATE", "m", None, amount_at_risk=1242.4)])
    note = rules.StageResult("po_match", "warn", "", reasons=[rules.Reason("PO_INFERRED", "m")])
    d = rules.decide([note, hold, rej], {"total": 1242.4})
    assert d["decision"] == "REJECT" and d["primary"]["code"] == "DUPLICATE" and d["owner"] == "AP clerk"
    assert d["amount_at_risk"] == 3000.0 and [r["code"] for r in d["reasons"]] == ["DUPLICATE", "PO_OVERRUN", "PO_INFERRED"]
    d = rules.decide([note, hold], {"total": 1.0})
    assert d["decision"] == "HOLD" and d["owner"] == "Buyer" and d["next_action"] == "a"
    d = rules.decide([note], {"total": 99.5})
    assert d["decision"] == "APPROVE" and d["primary"] is None and "$99.50" in d["next_action"]


def test_bank_reread_fails_closed():
    x = truth_x("19_beverage_scan_rotated.pdf")
    x["fields"]["remit_bank_account"]["value"] = "153007742"  # first read dropped one of the repeated 7s
    on_file = "1530077742"
    for second in ("153007742", None):  # the re-read still differs, or read nothing: the hold stays
        y, cleared = rules.apply_bank_reread(x, second, on_file)
        assert cleared is False and y is x
    y, cleared = rules.apply_bank_reread(x, "1530 0777 42", on_file)  # exact match with the master: cleared
    assert cleared is True and y["fields"]["remit_bank_account"] == {"value": "1530 0777 42", "confidence": "medium",
                                                                     "source_text": "1530 0777 42"}
    assert x["fields"]["remit_bank_account"]["value"] == "153007742"  # input not mutated
    assert codes(rules.check_vendor(x, REF["vendors"])[0]) == ["BANK_DETAILS_CHANGED"]
    assert codes(rules.check_vendor(y, REF["vendors"])[0]) == []
