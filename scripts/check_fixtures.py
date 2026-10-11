"""Quality checks for the generated fixtures.

(b) every file opens, except the ones that are meant to be broken
(c) answer-key self-check: on every digital PDF, each ground-truth value is actually printed

    python scripts/check_fixtures.py
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_fixtures as mf  # noqa: E402

MEANT_BROKEN = {"encrypted_pdf", "corrupted_pdf"}


def norm(s):
    return re.sub(r"[\s,$]", "", str(s)).casefold()


def money_forms(x):
    a = abs(float(x))
    return {f"{a:.2f}", f"{a:.4f}"}


def pdf_text(path):
    pdf = pdfium.PdfDocument(str(path))
    return "".join(p.get_textpage().get_text_bounded() for p in pdf)


def expected_values(t, vendor):
    """(label, acceptable normalised forms) for every printed truth value."""
    out = [("vendor", {norm(t["vendor_name_printed"])}), ("bank account", {norm(t["remit_bank_account"])}),
           ("routing", {norm(t["remit_bank_routing"])}), ("bill-to", {norm(t["bill_to_name"])})]
    if t["invoice_number"]:
        out.append(("invoice no", {norm(t["invoice_number"])}))
    if t["po_number_printed"]:
        out.append(("PO", {norm(t["po_number_printed"])}))
    if t["invoice_date"]:
        out.append(("invoice date", {norm(mf.fdate(date.fromisoformat(t["invoice_date"]), vendor["datefmt"]))}))
    for k in ("subtotal", "total_printed"):
        if t.get(k) is not None:
            out.append((k, money_forms(t[k])))
    if t.get("tax"):
        out.append(("tax", money_forms(t["tax"])))
    for i, li in enumerate(t["line_items"]):
        if li["amount"]:
            out.append((f"line {i + 1} amount", money_forms(li["amount"])))
        out.append((f"line {i + 1} price", money_forms(li["unit_price"])))
    return out


def main():
    man = json.loads((ROOT / "fixtures" / "manifest.json").read_text())["files"]
    fails, checked_values = [], 0
    for m in man:
        path = ROOT / "fixtures" / "invoices" / m["file"]
        # (b) opens
        try:
            if path.suffix == ".pdf":
                n = len(pdfium.PdfDocument(str(path)))
            else:
                Image.open(path).verify()
                n = 1
            opened = True
        except Exception:
            opened, n = False, 0
        if opened == (m["kind"] in MEANT_BROKEN):
            fails.append(f"{m['file']}: opened={opened} but kind={m['kind']}")
            continue
        # (c) truth values printed (digital PDFs only; scans/photos have no text layer by design)
        if m["kind"] != "digital_pdf":
            continue
        text = norm(pdf_text(path))
        truths = m["truth"] if isinstance(m["truth"], list) else [m["truth"]]
        for t in truths:
            vendor = mf.ALL_VENDORS[t["vendor_id"] or "X001"]
            for label, forms in expected_values(t, vendor):
                checked_values += 1
                if not any(f in text for f in forms):
                    fails.append(f"{m['file']}: {label} {sorted(forms)} not printed")
    print(f"files: {len(man)}   truth values checked on digital PDFs: {checked_values}")
    if fails:
        print(f"FAILURES ({len(fails)}):")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
