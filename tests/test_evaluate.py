import asyncio

from app import db, evaluate
from app.truth import TruthExtractor, extraction_from_truth
from tests.conftest import FIX_DIR, MAN_BY_FILE, MANIFEST, SEED


def test_field_accuracy_perfect_and_wrong():
    t = MAN_BY_FILE["01_greenleaf_clean.pdf"]["truth"]
    x = extraction_from_truth(t)
    assert all(evaluate.field_accuracy(x, t).values())
    x["fields"]["total"]["value"] = 1.0
    x["fields"]["invoice_number"]["value"] = "inv gl 02228"
    acc = evaluate.field_accuracy(x, t)
    assert acc["total"] is False and acc["invoice_number"] is True


def test_field_accuracy_handwritten_subtotal_and_non_invoices():
    m = MAN_BY_FILE["21_handyman_handwritten_scan.pdf"]
    x = extraction_from_truth(m["truth"])
    x["fields"]["subtotal"]["value"] = None  # the carbon-book form prints only a TOTAL
    assert evaluate.field_accuracy(x, m["truth"], m["kind"])["subtotal"] is True
    assert evaluate.field_accuracy(x, m["truth"])["subtotal"] is False
    m = MAN_BY_FILE["60_greenleaf_statement_of_account.pdf"]
    acc = evaluate.field_accuracy(extraction_from_truth(m["truth"]), m["truth"], m["kind"])
    assert "total" not in acc and "line_count" not in acc and all(acc.values())


def test_evaluate_subset_with_truth_extractor():
    subset = [m for m in MANIFEST if m["id"] in (1, 4, 26, 27, 44, 43, 64)]
    rep = asyncio.run(evaluate.evaluate(subset, FIX_DIR, SEED, db.connect(), TruthExtractor(MANIFEST)))
    assert rep["status"] == "done" and rep["alone"] == {"passed": 7, "total": 7, "rate": 1.0}
    assert rep["batch"]["rate"] == 1.0
    assert [r["id"] for r in rep["rows"]] == [1, 4, 26, 27, 43, 44, 64]
    row27 = next(r for r in rep["rows"] if r["id"] == 27)
    assert row27["actual_alone"]["decision"] == "APPROVE" and row27["actual_batch"]["decision"] == "HOLD"
    assert rep["fields"]["total"]["rate"] == 1.0
