import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.truth import TruthExtractor
from tests.conftest import FIX_DIR, MANIFEST


@pytest.fixture
def client():
    with TestClient(create_app(db_path=":memory:", extractor=TruthExtractor(MANIFEST))) as c:
        yield c


def wait_batch(c, batch_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        snap = c.get(f"/api/batches/{batch_id}").json()
        if snap["finished"]:
            return snap
        time.sleep(0.1)
    raise AssertionError("batch did not finish")


def upload(c, *names):
    files = [("files", (n, (FIX_DIR / n).read_bytes(), "application/octet-stream")) for n in names]
    r = c.post("/api/batches", files=files)
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_two_files_and_poll(client):
    b = upload(client, "01_greenleaf_clean.pdf", "48_rapidlinen_blocked_vendor.pdf")
    snap = wait_batch(client, b["batch_id"])
    assert snap["counts"]["approved"] == 1 and snap["counts"]["rejected"] == 1
    run = client.get(f"/api/runs/{b['run_ids'][0]}").json()
    assert run["decision"]["decision"] == "APPROVE" and run["summary"].startswith("Approved")
    f = client.get(f"/api/runs/{b['run_ids'][0]}/file")
    assert f.status_code == 200 and f.content[:5] == b"%PDF-" and f.headers["content-type"] == "application/pdf"


def test_demo_fixture_and_fixture_list(client):
    fx = client.get("/api/fixtures").json()
    assert len(fx["files"]) == 67 and fx["demo"][0]["label"] == "Happy path"
    r = client.post("/api/batches", data={"fixture": "26_northgate_po_overrun.pdf"}).json()
    snap = wait_batch(client, r["batch_id"])
    assert snap["runs"][0]["decision"] == "HOLD" and snap["runs"][0]["code"] == "PO_OVERRUN"
    assert snap["runs"][0]["title"] == "Billing would exceed the PO"  # tiles show the reason in plain English
    assert client.post("/api/batches", data={"fixture": "nope.pdf"}).status_code == 400
    assert client.post("/api/batches").status_code == 400


def test_events_for_finished_batch_close_immediately(client):
    b = upload(client, "01_greenleaf_clean.pdf")
    wait_batch(client, b["batch_id"])
    start = time.time()
    with client.stream("GET", f"/api/batches/{b['batch_id']}/events") as r:
        body = "".join(r.iter_text())
    assert "event: done" in body and '"finished": true' in body and time.time() - start < 3
    with client.stream("GET", f"/api/runs/{b['run_ids'][0]}/events") as r:
        assert "event: done" in "".join(r.iter_text())


def test_reference_policy_runs_and_reset(client):
    ref = client.get("/api/reference").json()
    assert {p["po_number"]: p for p in ref["pos"]}["PO-1043"]["billed"] == 38000.0
    assert client.put("/api/policy", json={"price_tolerance_pct": -1}).status_code == 422
    assert client.put("/api/policy", json={"price_tolerance_pct": 3}).json()["price_tolerance_pct"] == 3
    b = upload(client, "01_greenleaf_clean.pdf")
    wait_batch(client, b["batch_id"])
    rows = client.get("/api/runs").json()
    assert rows["kpis"]["runs"] == 1 and rows["runs"][0]["invoice_number"] == "INV-GL-2228"
    assert client.post("/api/demo/reset").json() == {"ok": True}
    assert client.get("/api/runs").json()["kpis"]["runs"] == 0
    assert client.get("/api/reference").json()["policy"]["price_tolerance_pct"] == 2.0


def test_health_assumptions_and_static(client):
    assert client.get("/api/health").json()["offline"] is True
    assert len(client.get("/api/assumptions").json()) >= 9
    assert "InvoiceDesk" in client.get("/").text


def test_run_list_carries_money_at_risk_for_the_dashboard_charts(client):
    b = upload(client, "01_greenleaf_clean.pdf", "48_rapidlinen_blocked_vendor.pdf")
    wait_batch(client, b["batch_id"])
    rows = {r["id"]: r for r in client.get("/api/runs").json()["runs"]}
    assert rows[b["run_ids"][0]]["at_risk"] == 0
    assert rows[b["run_ids"][1]]["at_risk"] > 0


def test_clear_invoices_removes_only_processed_invoices(client):
    seeded = len(client.get("/api/reference").json()["ledger"])
    client.put("/api/policy", json={"price_tolerance_pct": 3})
    b = upload(client, "01_greenleaf_clean.pdf", "04_northgate_blanket_within_balance.pdf")
    wait_batch(client, b["batch_id"])
    assert len(client.get("/api/reference").json()["ledger"]) == seeded + 2

    assert client.post("/api/invoices/clear").json() == {"ok": True}
    ref = client.get("/api/reference").json()
    assert client.get("/api/runs").json()["runs"] == [] and len(ref["ledger"]) == seeded
    assert ref["policy"]["price_tolerance_pct"] == 3  # procurement data and policy edits stay
    assert {p["po_number"]: p for p in ref["pos"]}["PO-1043"]["billed"] == 38000.0
    b = upload(client, "01_greenleaf_clean.pdf")  # the same invoice is new again, not a duplicate
    wait_batch(client, b["batch_id"])
    assert client.get(f"/api/runs/{b['run_ids'][0]}").json()["decision"]["decision"] == "APPROVE"


def test_responses_are_compressed_but_live_streams_are_not(client):
    js = client.get("/app.js", headers={"Accept-Encoding": "gzip"})
    assert js.status_code == 200 and js.headers.get("content-encoding") == "gzip"
    assert client.get("/api/fixtures", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding") == "gzip"
    b = upload(client, "01_greenleaf_clean.pdf")
    wait_batch(client, b["batch_id"])
    with client.stream("GET", f"/api/runs/{b['run_ids'][0]}/events", headers={"Accept-Encoding": "gzip"}) as s:
        assert s.headers["content-type"].startswith("text/event-stream") and "content-encoding" not in s.headers
