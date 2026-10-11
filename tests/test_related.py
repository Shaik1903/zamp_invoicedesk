"""The Related tab: everything an invoice is connected to through the vendor master, its PO and the ledger."""
from tests.test_api import client, upload, wait_batch  # noqa: F401  (client is a fixture)


def related(c, run_id):
    r = c.get(f"/api/runs/{run_id}/related")
    assert r.status_code == 200, r.text
    return r.json()


def test_invoices_on_one_po_see_each_other_before_and_after(client):  # noqa: F811
    b = upload(client, "04_northgate_blanket_within_balance.pdf", "26_northgate_po_overrun.pdf", "27_northgate_split_second_in_batch.pdf")
    wait_batch(client, b["batch_id"])
    r04, r26, r27 = b["run_ids"]

    rel = related(client, r26)
    assert rel["vendor"]["name"] == "Northgate Kitchen Equipment Rentals" and rel["vendor"]["bank_matches"] is True
    po = rel["po"]
    assert po["po_number"] == "PO-1043" and po["total"] == 50000.0 and po["billed_now"] == 47000.0
    pos = {e.get("run_id"): e["position"] for e in po["invoices"]}
    assert pos[r04] == "before" and pos[r26] == "this" and pos[r27] == "after"
    seeded = [e for e in po["invoices"] if e["run_id"] is None]
    assert {e["invoice_number"] for e in seeded} == {"NG-0301", "NG-0302"} and all(e["filename"] is None for e in seeded)
    assert next(e for e in po["invoices"] if e["run_id"] == r04)["filename"] == "04_northgate_blanket_within_balance.pdf"

    # 04 was approved first: from its page you can see the two invoices that were held on the same PO afterwards
    later = [e for e in related(client, r04)["po"]["invoices"] if e["position"] == "after"]
    assert {e["run_id"] for e in later} == {r26, r27} and all(e["status"] == "on_hold" for e in later)
    assert all(e["run_id"] != r26 for e in rel["vendor_invoices"])  # never lists itself


def test_related_without_vendor_or_po_and_unknown_run(client):  # noqa: F811
    b = upload(client, "49_harborview_unknown_vendor.pdf")
    wait_batch(client, b["batch_id"])
    rel = related(client, b["run_ids"][0])
    assert rel["vendor"] is None and rel["po"] is None and rel["vendor_invoices"] == []
    assert client.get("/api/runs/nope/related").status_code == 404
