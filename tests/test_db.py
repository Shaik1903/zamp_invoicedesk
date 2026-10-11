import pytest

from app import db
from tests.conftest import SEED


def world():
    conn = db.connect()
    db.load_seed(conn, SEED)
    return conn


def test_ref_snapshot_shape():
    ref = db.load_ref(world())
    assert {v["id"] for v in ref["vendors"]} >= {"V001", "V006", "V012"}
    assert ref["pos"]["PO-1043"]["type"] == "blanket"
    assert ref["receipts"]["PO-1040"]["GL-1102"] == 12
    assert ref["policy"]["price_tolerance_pct"] == 2.0
    assert ref["ledger"][0]["invoice_number"] == "INV-GL-2207" and ref["ledger"][0]["lines"]


def test_post_ledger_and_balances():
    conn = world()
    db.post_ledger(conn, {"run_id": "r1", "vendor_id": "V004", "invoice_number": "NG-0303", "invoice_date": "2026-10-01",
                          "po_number": "PO-1043", "subtotal": 9000.0, "total": 9000.0, "status": "approved",
                          "service_period": None, "lines": []})
    bal = {b["po_number"]: b for b in db.po_balances(conn)}["PO-1043"]
    assert bal["billed"] == 47000.0 and bal["remaining"] == 3000.0


def test_on_hold_does_not_consume_balance():
    conn = world()
    db.post_ledger(conn, {"run_id": "r1", "vendor_id": "V004", "invoice_number": "X", "invoice_date": "2026-10-01",
                          "po_number": "PO-1043", "subtotal": 9000.0, "total": 9000.0, "status": "on_hold",
                          "service_period": None, "lines": []})
    assert {b["po_number"]: b for b in db.po_balances(conn)}["PO-1043"]["billed"] == 38000.0


def test_policy_validation():
    conn = world()
    assert db.set_policy(conn, {"price_tolerance_pct": 5})["price_tolerance_pct"] == 5
    with pytest.raises(ValueError):
        db.set_policy(conn, {"price_tolerance_pct": -1})
    with pytest.raises(ValueError):
        db.set_policy(conn, {"nope": 1})


def test_runs_cache_files_and_reseed_keeps_cache():
    conn = world()
    db.save_run(conn, {"id": "r1", "batch_id": "b1", "seq": 0, "filename": "a.pdf", "sha256": "s", "mime": "application/pdf",
                       "created": 1.0, "finished": 2.0, "phase": "done", "decision": {"decision": "APPROVE"}, "summary": "ok"})
    db.save_batch(conn, {"id": "b1", "created": 1.0, "label": "x", "run_ids": ["r1"]})
    assert db.get_run(conn, "r1")["decision"]["decision"] == "APPROVE"
    assert db.get_batch(conn, "b1")["run_ids"] == ["r1"]
    db.cache_put(conn, "s", {"document_type": "invoice"}, "text")
    db.file_put(conn, "s", b"%PDF", "application/pdf")
    db.load_seed(conn, SEED)
    assert db.get_run(conn, "r1") is None
    assert db.cache_get(conn, "s")["extraction"]["document_type"] == "invoice"
    assert db.file_get(conn, "s") == (b"%PDF", "application/pdf")


def test_kpis_on_empty_and_after_runs():
    conn = world()
    assert db.kpis(conn)["runs"] == 0
    db.save_run(conn, {"id": "r1", "batch_id": "b", "seq": 0, "filename": "a", "sha256": "s", "mime": "m", "created": 0.0,
                       "decided_at": 2.0, "finished": 3.0, "phase": "done", "summary": "",
                       "decision": {"decision": "REJECT", "amount_at_risk": 100.0}, "money": {"total": 100.0}})
    k = db.kpis(conn)
    # Time is upload to decision (the write-up after it doesn't count), the same clock as the batch page.
    assert k["runs"] == 1 and k["rejected"] == 1 and k["dollars_stopped"] == 100.0 and k["avg_seconds"] == 2.0
    db.save_run(conn, {"id": "r2", "batch_id": "b", "seq": 1, "created": 0.0, "decided_at": 4.0, "finished": 9.0,
                       "decision": {"decision": "APPROVE"}})
    db.save_run(conn, {"id": "r3", "batch_id": "c", "seq": 0, "created": 100.0, "decided_at": 102.0,
                       "decision": {"decision": "APPROVE"}})
    # Throughput: 3 invoices decided over 4 s (batch b) + 2 s (batch c) of batch time = 30 per minute.
    assert db.kpis(conn)["per_minute"] == 30.0
