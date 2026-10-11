"""SQLite storage. World tables (reseeded by demo reset) + store tables (cache, files: kept)."""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS vendors (id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS pos (po_number TEXT PRIMARY KEY, vendor_id TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS receipts (po_number TEXT, sku TEXT, qty REAL);
CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, vendor_id TEXT,
  invoice_number TEXT, invoice_date TEXT, po_number TEXT, subtotal REAL, total REAL, status TEXT,
  service_period TEXT, lines TEXT);
CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, created REAL, data TEXT);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, batch_id TEXT, seq INTEGER, created REAL, data TEXT);
CREATE TABLE IF NOT EXISTS cache (sha256 TEXT PRIMARY KEY, extraction TEXT, layout_text TEXT);
CREATE TABLE IF NOT EXISTS files (sha256 TEXT PRIMARY KEY, mime TEXT, data BLOB);
"""
WORLD_TABLES = ("kv", "vendors", "pos", "receipts", "ledger", "batches", "runs")
BILLED = ("approved", "paid")


def connect(path=":memory:"):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def load_seed(conn, seed):
    with conn:
        for t in WORLD_TABLES:
            conn.execute(f"DELETE FROM {t}")
        conn.execute("INSERT INTO kv VALUES ('company', ?)", (json.dumps(seed["company"]),))
        conn.execute("INSERT INTO kv VALUES ('policy', ?)", (json.dumps(seed["policy"]),))
        conn.executemany("INSERT INTO vendors VALUES (?, ?)", [(v["id"], json.dumps(v)) for v in seed["vendors"]])
        conn.executemany("INSERT INTO pos VALUES (?, ?, ?)",
                         [(p["po_number"], p["vendor_id"], json.dumps(p)) for p in seed["purchase_orders"]])
        conn.executemany("INSERT INTO receipts VALUES (?, ?, ?)",
                         [(r["po_number"], r["sku"], r["qty_received"]) for r in seed["goods_receipts"]])
    for e in seed["invoice_ledger"]:
        post_ledger(conn, {**e, "run_id": None})


def clear_invoices(conn):
    """Forget every processed invoice: runs, batches and the ledger entries they posted. Vendors, POs, goods
    received, the policy and the opening ledger history stay; cached AI reads stay too, so reruns are instant."""
    with conn:
        conn.execute("DELETE FROM runs")
        conn.execute("DELETE FROM batches")
        conn.execute("DELETE FROM ledger WHERE run_id IS NOT NULL")


def _kv(conn, key):
    row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def get_policy(conn):
    return _kv(conn, "policy")


def set_policy(conn, updates):
    policy = get_policy(conn)
    for k, v in updates.items():
        if k not in policy:
            raise ValueError(f"unknown policy key: {k}")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            raise ValueError(f"{k} must be a number >= 0")
        policy[k] = v
    with conn:
        conn.execute("UPDATE kv SET value=? WHERE key='policy'", (json.dumps(policy),))
    return policy


def _ledger_rows(conn):
    out = []
    for r in conn.execute("SELECT * FROM ledger ORDER BY id"):
        d = dict(r)
        d["lines"] = json.loads(d["lines"] or "[]")
        out.append(d)
    return out


def load_ref(conn):
    receipts = {}
    for r in conn.execute("SELECT po_number, sku, SUM(qty) q FROM receipts GROUP BY po_number, sku"):
        receipts.setdefault(r["po_number"], {})[r["sku"]] = r["q"]
    return {"company": _kv(conn, "company"), "policy": get_policy(conn),
            "vendors": [json.loads(r["data"]) for r in conn.execute("SELECT data FROM vendors ORDER BY id")],
            "pos": {r["po_number"]: json.loads(r["data"]) for r in conn.execute("SELECT po_number, data FROM pos")},
            "receipts": receipts, "ledger": _ledger_rows(conn)}


def post_ledger(conn, e):
    with conn:
        cur = conn.execute(
            "INSERT INTO ledger (run_id, vendor_id, invoice_number, invoice_date, po_number, subtotal, total, status, "
            "service_period, lines) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (e.get("run_id"), e["vendor_id"], e.get("invoice_number"), e.get("invoice_date"), e.get("po_number"),
             e.get("subtotal"), e.get("total"), e["status"], e.get("service_period"), json.dumps(e.get("lines") or [])))
    return cur.lastrowid


def po_balances(conn):
    ref = load_ref(conn)
    names = {v["id"]: v["name"] for v in ref["vendors"]}
    out = []
    for po in ref["pos"].values():
        billed = po.get("opening_billed", 0.0) + sum(e["subtotal"] or 0 for e in ref["ledger"]
                                                     if e["po_number"] == po["po_number"] and e["status"] in BILLED)
        out.append({**po, "vendor_name": names.get(po["vendor_id"], po["vendor_id"]), "billed": round(billed, 2),
                    "remaining": round(po["total"] - billed, 2)})
    return sorted(out, key=lambda p: p["po_number"])


def save_run(conn, run):
    with conn:
        conn.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?)",
                     (run["id"], run["batch_id"], run["seq"], run["created"], json.dumps(run, default=str)))


def get_run(conn, run_id):
    row = conn.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_runs(conn, limit=500):
    return [json.loads(r["data"]) for r in
            conn.execute("SELECT data FROM runs ORDER BY created DESC, seq DESC LIMIT ?", (limit,))]


def save_batch(conn, batch):
    with conn:
        conn.execute("INSERT OR REPLACE INTO batches VALUES (?, ?, ?)", (batch["id"], batch["created"], json.dumps(batch)))


def get_batch(conn, batch_id):
    row = conn.execute("SELECT data FROM batches WHERE id=?", (batch_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def cache_get(conn, sha256):
    row = conn.execute("SELECT extraction, layout_text FROM cache WHERE sha256=?", (sha256,)).fetchone()
    return {"extraction": json.loads(row["extraction"]), "layout_text": row["layout_text"]} if row else None


def cache_put(conn, sha256, extraction, layout_text):
    with conn:
        conn.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (sha256, json.dumps(extraction), layout_text or ""))


def file_put(conn, sha256, data, mime):
    with conn:
        conn.execute("INSERT OR IGNORE INTO files VALUES (?, ?, ?)", (sha256, mime, data))


def file_get(conn, sha256):
    row = conn.execute("SELECT data, mime FROM files WHERE sha256=?", (sha256,)).fetchone()
    return (bytes(row["data"]), row["mime"]) if row else None


def kpis(conn):
    runs = [r for r in list_runs(conn, 100000) if r.get("decision")]
    dec = [r["decision"]["decision"] for r in runs]
    n = len(runs)
    secs = [r["decided_at"] - r["created"] for r in runs if r.get("decided_at")]
    span = {}                                                  # batch -> (upload, last decision), as the batch page times it
    for r in runs:
        if r.get("decided_at"):
            a, b = span.get(r["batch_id"], (r["created"], r["decided_at"]))
            span[r["batch_id"]] = (min(a, r["created"]), max(b, r["decided_at"]))
    busy = sum(b - a for a, b in span.values())
    approved = dec.count("APPROVE")
    minutes = (get_policy(conn) or {}).get("clerk_minutes_per_invoice", 12)
    return {"runs": n, "approved": approved, "held": dec.count("HOLD"), "rejected": dec.count("REJECT"),
            "touchless_rate": round(approved / n, 3) if n else 0.0,
            "avg_seconds": round(sum(secs) / len(secs), 1) if secs else 0.0,
            "per_minute": round(len(secs) / busy * 60, 1) if busy > 0 else 0.0,
            "dollars_stopped": round(sum(r["decision"].get("amount_at_risk") or 0 for r in runs), 2),
            "hours_saved": round(approved * minutes / 60, 1)}
