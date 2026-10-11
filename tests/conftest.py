import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX_DIR = ROOT / "fixtures" / "invoices"
SEED = json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))["files"]
MAN_BY_FILE = {m["file"]: m for m in MANIFEST}


@pytest.fixture
def seed():
    return copy.deepcopy(SEED)


from app.rules import FIELD_NAMES


def xt(fields=None, lines=(), doc_type="invoice", count=1, stamps=(), conf="high"):
    """Build an Extraction dict (plan contract) for rule tests."""
    f = {n: {"value": None, "confidence": conf, "source_text": None} for n in FIELD_NAMES}
    for k, v in (fields or {}).items():
        f[k] = {"value": v, "confidence": conf, "source_text": None if v is None else str(v)}
    items = []
    for ln in lines:
        sku, desc, qty, price = ln[:4]
        amount = ln[4] if len(ln) > 4 else round(qty * price, 2)
        items.append({"sku": sku, "description": desc, "qty": qty, "unit_price": price, "amount": amount,
                      "confidence": conf, "source_text": None})
    return {"document_type": doc_type, "document_count": count, "fields": f, "line_items": items,
            "stamps": list(stamps)}


from datetime import date

from app import db, rules
from app.truth import extraction_from_truth


def fresh_ref():
    conn = db.connect()
    db.load_seed(conn, SEED)
    return db.load_ref(conn)


def truth_x(file):
    return extraction_from_truth(MAN_BY_FILE[file]["truth"])


def money_of(x):
    return rules.validate_document(x, SEED["company"], date(2026, 10, 10), date(2026, 10, 9))[1]
