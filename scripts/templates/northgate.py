"""Northgate Kitchen Equipment Rentals: rental-counter invoice (and quotation) with asset/serial numbers."""
import random
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.utils import simpleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402

W, H = mf.W, mf.H
M = 40
INK = colors.HexColor("#1F2328")
GREY = colors.HexColor("#6B7280")
RULE = colors.HexColor("#D1D5DB")
TINT = colors.HexColor("#F3F4F6")

WAIVER = ("DAMAGE WAIVER & RETURN CONDITION. Damage waiver, where elected on the rental agreement, covers "
          "accidental damage to rented equipment during normal commercial kitchen use. It does not cover loss, "
          "theft, misuse, operation contrary to the manufacturer's instructions, or damage caused by gas, water or "
          "electrical connections made by others. Equipment must be returned clean, drained and defrosted, with all "
          "racks, shelves, hoses and manuals. Units returned dirty, incomplete or damaged will be cleaned, repaired "
          "or replaced at prevailing rates. Report any malfunction within 24 hours and do not attempt repairs. "
          "Rental charges continue until the equipment is called off for pickup.")
QUOTE_TERMS = ("QUOTE TERMS. Prices are firm until the valid-until date shown above and exclude rigging, permits "
               "and utility connections not listed. Equipment ships new in the original crate with full "
               "manufacturer warranty; Northgate provides start-up and a one-hour operator orientation. Title "
               "passes on payment in full. This quotation is not an invoice; an invoice is issued after delivery.")


def is_quote(d):
    return d["title"] == "QUOTATION" or d["doc_type"] == "quote"


def unit_price(p):
    return mf.num(p, 4 if p < 1 else 2)


def meta_rows(d, quote, rng):
    v, hide = d["v"], d["hide"]
    rows = []
    if "invoice_no" not in hide and d["inv_no"]:
        rows.append(("Quote No." if quote else "Invoice No.", d["inv_no"]))
    if "date" not in hide and d["inv_date"]:
        rows.append(("Quote Date" if quote else "Invoice Date", mf.fdate(d["inv_date"], v["datefmt"])))
    if "date" not in hide and d["due"]:
        rows.append(("Valid Until" if quote else "Due Date", mf.fdate(d["due"], v["datefmt"])))
    rows.append(("Payment Terms", v["terms"][0]))
    if "po" not in hide and d["po"]:
        rows.append(("Customer PO", d["po"]))
    if d["service_period"]:
        rows.append(("Rental Period", d["service_period"]))
    rows.append(("Customer No.", "C-20417"))
    if not quote:
        rows.append(("Rental Agreement", f"RA-{rng.randint(240000, 249999)}"))
    return rows


def asset_cell(l, quote, d):
    if quote:
        return f"Model {l['sku']}N\nNew, crated"
    if not l["sku"].startswith("RNT-"):
        return "Service"
    r = random.Random(f"{d['inv_no']}|{l['sku']}")
    letters = "".join(r.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(2))
    return f"Asset NG-{r.randint(10000, 39999)}\nS/N {letters}{r.randint(1000000, 9999999)}"


def fallback_mark(c, x, y, s, acc):
    """Gate: two posts and a lintel, in the accent colour."""
    c.setFillColor(acc)
    c.rect(x + s * 0.12, y + s * 0.12, s * 0.18, s * 0.62, stroke=0, fill=1)
    c.rect(x + s * 0.70, y + s * 0.12, s * 0.18, s * 0.62, stroke=0, fill=1)
    c.rect(x + s * 0.04, y + s * 0.74, s * 0.92, s * 0.14, stroke=0, fill=1)
    c.setStrokeColor(acc)
    c.setLineWidth(2)
    for k in range(3):
        xx = x + s * (0.38 + k * 0.08)
        c.line(xx, y + s * 0.12, xx, y + s * 0.62)


def header(c, d, acc, quote):
    v = d["v"]
    c.setFillColor(INK)
    c.rect(0, H - 92, W, 92, stroke=0, fill=1)
    c.setFillColor(acc)
    c.rect(0, H - 98, W, 6, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.roundRect(M, H - 80, 56, 56, 6, stroke=0, fill=1)
    if not mf.draw_logo_image(c, d["vid"], M + 4, H - 76, 48, 48):
        fallback_mark(c, M + 6, H - 74, 44, acc)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(M + 70, H - 40, v["name"])
    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#D1D5DB"))
    c.drawString(M + 70, H - 55, "  |  ".join(v["addr"]))
    c.drawString(M + 70, H - 67, f"{v['phone']}  |  {v['email']}")
    c.drawString(M + 70, H - 79, f"FEIN {v['tax_id']}")
    title = d["title"] or "RENTAL INVOICE"
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(W - M, H - 62, title)
    c.setFillColor(colors.HexColor("#D1D5DB"))
    c.setFont("Helvetica", 8)
    c.drawRightString(W - M, H - 74, "Equipment Sales Desk" if quote else "Equipment Rental Billing")
    c.drawRightString(W - M, H - 84, "Branch CHI-02  Elston Ave")
    c.setFillColor(colors.black)


def label(c, x, y, text, acc):
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x, y, text)
    c.setFillColor(colors.black)


def addr_block(c, x, y, lab, lines, w, acc):
    label(c, x, y, lab, acc)
    y -= 12
    for i, ln in enumerate(lines):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 9)
        for part in simpleSplit(ln, "Helvetica-Bold" if i == 0 else "Helvetica", 9, w):
            c.drawString(x, y, part)
            y -= 11
    return y


def footer(c, d, page, total_pages, acc):
    c.setStrokeColor(acc)
    c.setLineWidth(1.2)
    c.line(M, 46, W - M, 46)
    c.setFont("Helvetica", 7)
    c.setFillColor(GREY)
    c.drawString(M, 34, "All rentals are subject to the Northgate Rental Terms & Conditions (form NG-RA-7). "
                        "Equipment remains the property of Northgate.")
    c.drawRightString(W - M, 22, f"Page {page} of {total_pages}")
    c.setFillColor(colors.black)


def render(c, d, total_pages):
    v, acc = d["v"], mf.hexc(d["v"]["accent"])
    quote = is_quote(d)
    rng = random.Random(d["inv_no"] or "northgate")
    title = d["title"] or "RENTAL INVOICE"

    def cont(c, d, page):
        c.setFillColor(INK)
        c.rect(0, H - 40, W, 40, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(M, H - 25, v["name"])
        c.setFont("Helvetica", 8.5)
        ref = d["inv_no"] if "invoice_no" not in d["hide"] else ""
        c.drawRightString(W - M, H - 25, f"{title} {ref} (continued)")
        c.setFillColor(colors.black)
        footer(c, d, page, total_pages, acc)
        return H - 62

    pen = mf.Pen(c, d, cont, bottom=62)
    header(c, d, acc, quote)
    footer(c, d, 1, total_pages, acc)

    # meta grid (right)
    rows = meta_rows(d, quote, rng)
    bw, rh = 228, 15
    bx, top = W - M - bw, H - 114
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    for i, (k, val) in enumerate(rows):
        yy = top - i * rh
        if i % 2 == 0:
            c.setFillColor(TINT)
            c.rect(bx, yy - rh, bw, rh, stroke=0, fill=1)
        c.setFillColor(GREY)
        c.setFont("Helvetica", 8)
        c.drawString(bx + 6, yy - 10.5, k)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(bx + bw - 6, yy - 10.5, val)
    c.rect(bx, top - rh * len(rows), bw, rh * len(rows), stroke=1, fill=0)
    meta_bottom = top - rh * len(rows)

    # bill to / job site (left)
    colw = (bx - M - 20) / 2
    y1 = addr_block(c, M, top - 8, "BILL TO", d["bill_to"], colw - 6, acc)
    y2 = top
    if mf.ship_lines(d):
        y2 = addr_block(c, M + colw + 10, top - 8, "JOB SITE / DELIVER TO", mf.ship_lines(d), colw - 6, acc)
    y = min(y1, y2, meta_bottom) - 14

    # delivery / pickup strip
    if quote:
        cells = [("BRANCH", "CHI-02 Elston Ave"), ("LEAD TIME", "2-3 weeks after acceptance"),
                 ("DELIVERY", "Set in place, dock to kitchen"), ("SALES REP", "D. Kowalczyk")]
    else:
        cells = [("BRANCH", "CHI-02 Elston Ave"), ("DELIVERY", "Truck 07, rear service door"),
                 ("PICKUP", "On call-off, 48 hr notice"), ("ORDERED BY", "Executive Chef")]
    cw = (W - 2 * M) / len(cells)
    c.setFillColor(TINT)
    c.rect(M, y - 30, W - 2 * M, 30, stroke=0, fill=1)
    for i, (k, val) in enumerate(cells):
        x = M + i * cw + 8
        c.setFillColor(GREY)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(x, y - 11, k)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8.5)
        c.drawString(x, y - 23, val)
        if i:
            c.setStrokeColor(RULE)
            c.line(M + i * cw, y - 26, M + i * cw, y - 4)
    pen.y = y - 44

    # equipment table
    cols = [("QTY", 36, "r"), ("EQUIPMENT / SERIAL" if not quote else "MODEL", 110, "l"),
            ("DESCRIPTION", 196, "l"), ("U/M", 36, "c"), ("RATE", 74, "r"), ("AMOUNT", 80, "r")]
    body = [[mf.qty_s(l["qty"]), asset_cell(l, quote, d), l["desc"], l["unit"], unit_price(l["price"]),
             mf.num(l["amount"])] for l in d["lines"]]
    mf.draw_table(pen, M, cols, body, dict(size=8.8, hsize=7.5, pad=5, hfill=INK, htext=colors.white,
                                           grid=True, gridc=RULE))
    c.setStrokeColor(acc)
    c.setLineWidth(1.5)
    c.line(M, pen.y, W - M, pen.y)

    # terms paragraph (left) + totals box (right), side by side
    tot = mf.totals_rows(d)
    tw = 228
    tx = W - M - tw
    para = simpleSplit(QUOTE_TERMS if quote else WAIVER, "Helvetica", 7.3, tx - M - 22)
    th = len(tot) * 18 + 8
    ph = len(para) * 9 + 4
    pen.need(max(th, ph) + 18)
    y = pen.y - 12
    for i, (lab, val, bold) in enumerate(tot):
        yy = y - i * 18
        if bold:
            c.setFillColor(acc)
            c.rect(tx, yy - 18, tw, 20, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 11)
        else:
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 9)
        c.drawString(tx + 8, yy - 12, lab)
        c.drawRightString(W - M - 8, yy - 12, val)
    c.setFillColor(colors.black)
    if d["tax_mode"] == "inclusive":
        c.setFont("Helvetica", 7)
        c.drawRightString(W - M, y - len(tot) * 18 - 8,
                          f"Prices include {d['tax_rate'] * 100:.2f}% sales tax ({mf.money(d['tax'], d['currency'])}).")
    c.setFont("Helvetica", 7.3)
    c.setFillColor(colors.HexColor("#374151"))
    for i, ln in enumerate(para):
        c.drawString(M, y - 8 - i * 9, ln)
    c.setFillColor(colors.black)
    pen.y = y - max(th, ph) - 16

    # remit
    remit = mf.remit_lines(d)
    pen.need(len(remit) * 11 + 40)
    label(c, M, pen.y, "PAYMENT ON ACCEPTANCE - REMIT TO" if quote else "REMIT TO", acc)
    c.setFont("Helvetica", 8.5)
    for i, ln in enumerate(remit + [f"Checks payable to {v['name']}, {', '.join(v['addr'])}"]):
        c.drawString(M, pen.y - 13 - i * 11, ln)
    pen.y -= 13 + (len(remit) + 1) * 11 + 6

    mf.notes_block(pen, M, d, "Helvetica-Bold", 8.5, W - 2 * M)

    # signatures
    pen.need(80)
    pen.y -= 14
    if quote:
        c.setStrokeColor(acc)
        c.setLineWidth(1)
        c.rect(M, pen.y - 66, W - 2 * M, 66, stroke=1, fill=0)
        label(c, M + 8, pen.y - 13, "ACCEPT QUOTE", acc)
        c.setFont("Helvetica", 7.5)
        c.drawString(M + 8, pen.y - 24, "Sign and return to accept this quotation and authorise Northgate to order "
                                        "and schedule delivery.")
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        for x, w, lab in ((M + 8, 200, "Authorized signature"), (M + 222, 170, "Printed name & title"),
                          (M + 406, 118, "Date")):
            c.line(x, pen.y - 50, x + w, pen.y - 50)
            c.setFont("Helvetica", 7)
            c.setFillColor(GREY)
            c.drawString(x, pen.y - 59, lab)
            c.setFillColor(colors.black)
        pen.y -= 80
        pen.need(30)
        c.setFont("Helvetica", 7.5)
        c.drawString(M, pen.y - 10, "Prepared by:")
        c.setFillColor(colors.HexColor("#1E3A8A"))
        c.setFont("nothing", 13)
        c.drawString(M + 52, pen.y - 11, "D. Kowalczyk")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 7.5)
        c.drawString(M + 150, pen.y - 10, "Branch Sales, CHI-02")
    else:
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.line(M, pen.y - 24, M + 220, pen.y - 24)
        c.setFont("Helvetica", 7)
        c.setFillColor(GREY)
        c.drawString(M, pen.y - 33, "Equipment received in working order by (customer)")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 7.5)
        c.drawString(M + 260, pen.y - 21, "Questions about this invoice? Call rental billing at "
                                          f"{v['phone']}.")
        pen.y -= 40
