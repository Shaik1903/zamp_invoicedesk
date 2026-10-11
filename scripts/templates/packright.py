"""PackRight Packaging LLC (V002): mid-size distributor ERP print (NetSuite/Acumatica-like, unbranded).

Header with barcode + date/number box, bill/ship boxes, two-row order info grid, gridded item table,
remit + totals side by side, fine-print terms, detachable remittance stub (credit memos get a notice instead).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402
from reportlab.graphics.barcode import code128  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402

W, H = mf.W, mf.H
M = 36                      # page margin
STUB_TOP = 186              # remittance stub occupies y < STUB_TOP on the last page
GRAY = colors.HexColor("#E6E8EA")
LINE = colors.HexColor("#9AA1A8")
DARK = colors.HexColor("#22272B")
CUSTOMER_NO = "C-10427"

TERMS = ("Terms & conditions: Payment due per terms stated above. Past-due balances accrue a finance charge of "
         "1.5% per month (18% APR). Shortages or damage must be noted on the delivery receipt and reported within "
         "48 hours; returns require an RMA number and are accepted within 30 days in original, unopened cases. "
         "Special-order and printed items are non-returnable. Title passes at FOB point. "
         "Questions about this invoice: contact Accounts Receivable at the phone or email above.")


def _digits(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit()) or "0"


def _price(p):
    return mf.num(p, 4 if 0 < abs(p) < 1 else 2)


def _is_credit(d):
    return (d["title"] or "").lower().startswith("credit") or d["doc_type"] == "credit_note"


def _fallback_logo(c, x, y, s, acc):
    """Isometric carton mark."""
    cx, top = x + s / 2, y + s
    pts = {"t": (cx, top), "l": (x + 2, y + s * 0.74), "r": (x + s - 2, y + s * 0.74), "c": (cx, y + s * 0.48),
           "bl": (x + 2, y + s * 0.26), "br": (x + s - 2, y + s * 0.26), "b": (cx, y)}

    def poly(names, fill):
        p = c.beginPath()
        p.moveTo(*pts[names[0]])
        for n in names[1:]:
            p.lineTo(*pts[n])
        p.close()
        c.setFillColor(fill)
        c.drawPath(p, fill=1, stroke=0)
    poly(["t", "r", "c", "l"], colors.HexColor("#5FB3AD"))
    poly(["l", "c", "b", "bl"], acc)
    poly(["c", "r", "br", "b"], colors.HexColor("#145955"))
    c.setFillColor(colors.black)


def _footer(c, d, page, total_pages):
    v = d["v"]
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#666666"))
    ref = f"{d['title'] or 'Invoice'} {d['inv_no']}" if "invoice_no" not in d["hide"] else (d["title"] or "Invoice")
    c.drawString(M, 20, f"{v['name']}  |  {ref}")
    c.drawRightString(W - M, 20, f"Page {page} of {total_pages}")
    c.setFillColor(colors.black)


def _cell_grid(c, x, y, w, pairs, lab_h=11, val_h=15):
    """One row of label/value cells with a shaded label strip. Returns the bottom y."""
    if not pairs:
        return y
    cw = w / len(pairs)
    c.setFillColor(GRAY)
    c.rect(x, y - lab_h, w, lab_h, stroke=0, fill=1)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.rect(x, y - lab_h - val_h, w, lab_h + val_h, stroke=1, fill=0)
    c.line(x, y - lab_h, x + w, y - lab_h)
    for i, (k, val) in enumerate(pairs):
        cx = x + i * cw
        if i:
            c.line(cx, y, cx, y - lab_h - val_h)
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 6.8)
        c.drawString(cx + 4, y - 8, k)
        c.setFont("Helvetica", 8.4)
        c.drawString(cx + 4, y - lab_h - 11, val)
    c.setFillColor(colors.black)
    return y - lab_h - val_h


def _addr_box(c, x, y, w, title, lines):
    h = 21 + 11 * max(len(lines), 4)
    c.setFillColor(GRAY)
    c.rect(x, y - 13, w, 13, stroke=0, fill=1)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.rect(x, y - h, w, h, stroke=1, fill=0)
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x + 5, y - 9.5, title)
    c.setFont("Helvetica", 8.8)
    for i, ln in enumerate(lines):
        c.drawString(x + 6, y - 25 - i * 11, ln)
    c.setFillColor(colors.black)
    return y - h


def render(c, d, total_pages):
    v, acc = d["v"], mf.hexc(d["v"]["accent"])
    credit = _is_credit(d)
    title = d["title"] or "Invoice"
    show_no = "invoice_no" not in d["hide"] and d["inv_no"]
    show_date = "date" not in d["hide"] and d["inv_date"]
    dig = _digits(d["inv_no"])
    domain = v["email"].split("@")[-1]

    cols = [("Item", 62, "l"), ("Description", 214, "l"), ("Qty", 50, "r"), ("UOM", 36, "c"),
            ("Unit Price", 70, "r"), ("Tx", 24, "c"), ("Amount", 84, "r")]

    def cont(c, d, page):
        c.setFont("Helvetica-Bold", 11)
        c.drawString(M, H - 44, v["name"])
        c.setFont("Helvetica", 8.5)
        c.drawRightString(W - M, H - 44, f"{title} {d['inv_no'] if show_no else ''} (continued)".replace("  ", " "))
        c.setStrokeColor(acc)
        c.setLineWidth(1.2)
        c.line(M, H - 52, W - M, H - 52)
        _footer(c, d, page, total_pages)
        return H - 64

    pen = mf.Pen(c, d, cont, bottom=44)

    # --- header: vendor block -----------------------------------------------------------------
    if not mf.draw_logo_image(c, d["vid"], M, H - 88, 52, 52):
        _fallback_logo(c, M, H - 86, 48, acc)
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(M + 62, H - 50, v["name"])
    c.setFont("Helvetica", 8.3)
    vend = v["addr"] + [f"Phone {v['phone']}", f"{v['email']}  |  www.{domain}", f"Federal Tax ID: {v['tax_id']}"]
    for i, ln in enumerate(vend):
        c.drawString(M + 62, H - 63 - i * 10.2, ln)

    # --- header: title, date/number box, barcode ------------------------------------------------
    c.setFillColor(colors.HexColor("#B42318") if credit else acc)
    c.setFont("Helvetica-Bold", 22)
    c.drawRightString(W - M, H - 54, title)
    c.setFillColor(colors.black)
    box = []
    if show_date:
        box.append(("Date", mf.fdate(d["inv_date"], v["datefmt"])))
    if show_no:
        box.append(("Credit Memo #" if credit else "Invoice #", d["inv_no"]))
    bw = 190
    _cell_grid(c, W - M - bw, H - 64, bw, box)
    if show_no:
        bc = code128.Code128(str(d["inv_no"]), barHeight=18, barWidth=0.85)
        bc.drawOn(c, W - M - bc.width + 10, H - 116)

    # --- bill to / ship to --------------------------------------------------------------------
    y = H - 134
    ship = mf.ship_lines(d)
    bw2 = 262
    b1 = _addr_box(c, M, y, bw2, "BILL TO", d["bill_to"])
    b2 = _addr_box(c, W - M - bw2, y, bw2, "SHIP TO", ship) if ship else b1
    y = min(b1, b2) - 10

    # --- order info grid (two rows) -------------------------------------------------------------
    po = d["po"] if d["po"] and "po" not in d["hide"] else None
    due = mf.fdate(d["due"], v["datefmt"]) if show_date and d["due"] and v["terms"][1] else None
    if credit:
        row1 = [("Customer #", CUSTOMER_NO), ("RMA #", f"RA-{dig[-5:]:0>5}"), ("PO #", po),
                ("Terms", v["terms"][0]), ("Due Date", due), ("Sales Rep", "J. Ostrowski")]
        row2 = [("Return Type", "Customer return"), ("Return Method", "PackRight Truck pickup"),
                ("Warehouse", "Lyons DC (LYN)"), ("Service Period", d["service_period"])]
    else:
        ship_dt = mf.fdate(d["inv_date"] - mf.timedelta(days=1), v["datefmt"]) if show_date else None
        row1 = [("Customer #", CUSTOMER_NO), ("Sales Order #", f"SO{(int(dig) * 13 + 52211) % 1000000:06d}"),
                ("PO #", po), ("Terms", v["terms"][0]), ("Due Date", due), ("Sales Rep", "J. Ostrowski")]
        row2 = [("Ship Date", ship_dt), ("Ship Via", "PackRight Truck"), ("FOB", "Destination"),
                ("Tracking / BOL #", f"BOL-LYN-{(int(dig) * 37 + 4021) % 1000000:06d}"), ("Warehouse", "Lyons DC (LYN)"),
                ("Service Period", d["service_period"])]
    y = _cell_grid(c, M, y, W - 2 * M, [p for p in row1 if p[1]])
    y = _cell_grid(c, M, y - 6, W - 2 * M, [p for p in row2 if p[1]])
    _footer(c, d, 1, total_pages)

    # --- line items -----------------------------------------------------------------------------
    pen.y = y - 14
    tx = {"separate": "Y", "inclusive": "I", "none": "N"}[d["tax_mode"]]
    rows = [[l["sku"], l["desc"], mf.qty_s(l["qty"]), l["unit"], _price(l["price"]), tx, mf.num(l["amount"])]
            for l in d["lines"]]
    mf.draw_table(pen, M, cols, rows, dict(size=8.6, pad=4, hfill=DARK, htext=colors.white, hsize=8,
                                          grid=True, gridc=colors.HexColor("#C9CED3"),
                                          zebra=colors.HexColor("#F5F7F8")))

    # --- remit (left) + totals (right) ----------------------------------------------------------
    cur = d["currency"]
    trows = mf.totals_rows(d)
    incl = d["tax_mode"] == "inclusive"
    th = len(trows) * 17 + (24 if incl else 0) + 12
    pen.need(max(th, 70) + 10)
    top = pen.y - 10
    tw, tx0 = 230, W - M - 230
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    ty = top
    for lab, val, bold in trows:
        rh = 19 if bold else 16
        if bold:
            c.setFillColor(colors.HexColor("#FDECEA") if credit else colors.HexColor("#E3F1F0"))
            c.rect(tx0, ty - rh, tw, rh, stroke=0, fill=1)
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 8.8)
        c.drawString(tx0 + 6, ty - rh + 5.5, lab)
        c.drawRightString(W - M - 6, ty - rh + 5.5, val)
        c.line(tx0, ty - rh, W - M, ty - rh)
        ty -= rh
    c.rect(tx0, ty, tw, top - ty, stroke=1, fill=0)
    if incl:
        stmt = (f"All prices include {d['tax_rate'] * 100:.2f}% sales tax. "
                f"Tax included: {mf.money(d['tax'], cur)}")
        c.setFont("Helvetica-Oblique", 7.6)
        for i, ln in enumerate(simpleSplit(stmt, "Helvetica-Oblique", 7.6, tw)):
            c.drawRightString(W - M, ty - 11 - i * 9.5, ln)
        ty -= 10 + 9.5 * len(simpleSplit(stmt, "Helvetica-Oblique", 7.6, tw))
    # remit block on the left
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 7.8)
    c.drawString(M, top - 9, "BANK DETAILS ON FILE" if credit else "REMIT TO / ACH PAYMENT")
    c.setFont("Helvetica", 8)
    ry = top - 21
    for ln in [v["name"], ", ".join(v["addr"])] + mf.remit_lines(d):
        c.drawString(M, ry, ln)
        ry -= 10
    c.setFillColor(colors.black)
    pen.y = min(ty, ry) - 6

    # --- comments / notes -----------------------------------------------------------------------
    if d["notes"]:
        pen.need(14)
        c.setFont("Helvetica-Bold", 7.8)
        c.drawString(M, pen.y - 8, "COMMENTS")
        pen.y -= 10
        mf.notes_block(pen, M, d, "Helvetica", 8.2, W - 2 * M)

    # --- fine print -----------------------------------------------------------------------------
    fp = simpleSplit(TERMS, "Helvetica", 6.4, W - 2 * M)
    pen.need(len(fp) * 7.6 + 10)
    pen.y -= 8
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont("Helvetica", 6.4)
    for ln in fp:
        c.drawString(M, pen.y - 6, ln)
        pen.y -= 7.6
    c.setFillColor(colors.black)

    # --- remittance stub / credit notice at the bottom of the last page -------------------------
    if pen.y < STUB_TOP + 6:
        pen.need(10 ** 4)  # force a fresh page for the stub
    if credit:
        _credit_notice(c, d)
    else:
        _stub(c, d, show_no, show_date, due, po)


def _stub(c, d, show_no, show_date, due, po):
    v, cur = d["v"], d["currency"]
    y = STUB_TOP
    c.setStrokeColor(colors.HexColor("#777777"))
    c.setDash(3, 3)
    c.setLineWidth(0.7)
    c.line(M, y, W - M, y)
    c.setDash()
    c.setFont("Helvetica", 6.6)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawCentredString(W / 2, y + 3, "PLEASE DETACH AND RETURN THIS PORTION WITH YOUR PAYMENT")
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(M, y - 18, "REMITTANCE")
    c.setFont("Helvetica", 7.6)
    c.drawString(M, y - 30, "Make checks payable to:")
    c.setFont("Helvetica-Bold", 8.6)
    c.drawString(M, y - 42, v["name"])
    c.setFont("Helvetica", 8.4)
    for i, ln in enumerate(v["addr"]):
        c.drawString(M, y - 53 - i * 10, ln)
    c.setFont("Helvetica", 7.6)
    c.drawString(M, y - 86, "Remitted by:")
    c.setFont("Helvetica", 8.4)
    c.drawString(M, y - 97, f"{d['bill_to'][0]}   (Customer # {CUSTOMER_NO})")
    pairs = [("Customer #", CUSTOMER_NO)]
    if show_no:
        pairs.append(("Invoice #", d["inv_no"]))
    if show_date:
        pairs.append(("Invoice Date", mf.fdate(d["inv_date"], v["datefmt"])))
    if due:
        pairs.append(("Due Date", due))
    if po:
        pairs.append(("PO #", po))
    if "total" not in d["hide"]:
        pairs.append(("Amount Due", mf.money(d["total"], cur)))
    gx, gw = 318, W - M - 318
    gy = y - 12
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    for k, val in pairs:
        c.setFillColor(GRAY)
        c.rect(gx, gy - 14, 92, 14, stroke=0, fill=1)
        c.rect(gx, gy - 14, gw, 14, stroke=1, fill=0)
        c.line(gx + 92, gy, gx + 92, gy - 14)
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 7.4)
        c.drawString(gx + 4, gy - 10, k)
        c.setFont("Helvetica-Bold" if k == "Amount Due" else "Helvetica", 8.4)
        c.drawRightString(gx + gw - 5, gy - 10, val)
        gy -= 14
    c.setFont("Helvetica-Bold", 8.6)
    c.drawString(gx, gy - 20, "Amount enclosed:  ____________________")
    c.setFillColor(colors.black)
    if show_no:
        bc = code128.Code128(str(d["inv_no"]), barHeight=16, barWidth=0.8)
        bc.drawOn(c, M - 10, 40)


def _credit_notice(c, d):
    y = STUB_TOP
    c.setStrokeColor(colors.HexColor("#B42318"))
    c.setLineWidth(1)
    c.rect(M, y - 74, W - 2 * M, 74, stroke=1, fill=0)
    c.setFillColor(colors.HexColor("#B42318"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(M + 10, y - 18, "CREDIT MEMO - THIS IS NOT A REQUEST FOR PAYMENT. DO NOT REMIT.")
    c.setFillColor(DARK)
    c.setFont("Helvetica", 8.2)
    msg = ("The credit total shown above has been posted to your account and will be applied against open "
           "invoices, or refunded on request. Please reference the credit memo number when applying this credit "
           f"in your accounts payable system. Questions: {d['v']['email']}  |  {d['v']['phone']}")
    for i, ln in enumerate(simpleSplit(msg, "Helvetica", 8.2, W - 2 * M - 20)):
        c.drawString(M + 10, y - 34 - i * 10.5, ln)
    c.setFillColor(colors.black)
