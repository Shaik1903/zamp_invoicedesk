"""Harborview Florals: small-business invoice in the style of Square/Wave online invoices (unbranded)."""
import math
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.utils import simpleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402

W, H = mf.W, mf.H
X0, X1 = 100, W - 100  # centred content column
INK = colors.HexColor("#1F1F23")
MUTED = colors.HexColor("#6E6E78")
HAIR = colors.HexColor("#E4E4E8")
TINT = colors.HexColor("#FDF2F8")
MESSAGE = ("Thank you for choosing Harborview Florals! Arrangements are designed the morning of delivery; "
           "keep vases out of direct sun and top up the water daily.")


def unit_price(l, cur):
    sym = {"USD": "$", "CAD": "C$"}[cur]
    return f"{sym}{mf.num(l['price'], 4 if l['price'] < 1 else 2)}"


def fallback_mark(c, cx, cy, r, acc):
    """Five-petal flower on a tinted disc."""
    c.setFillColor(TINT)
    c.circle(cx, cy, r, stroke=0, fill=1)
    c.setFillColor(acc)
    for k in range(5):
        a = math.radians(90 + k * 72)
        c.circle(cx + math.cos(a) * r * 0.32, cy + math.sin(a) * r * 0.32, r * 0.24, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.circle(cx, cy, r * 0.14, stroke=0, fill=1)


def hr(c, y):
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.8)
    c.line(X0, y, X1, y)


def footer(c, d, page, total_pages):
    v = d["v"]
    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawCentredString(W / 2, 40, f"{v['name']}  ·  {', '.join(v['addr'])}  ·  EIN {v['tax_id']}")
    c.drawCentredString(W / 2, 29, f"Questions? Contact us at {v['email']} or {v['phone']}")
    c.drawRightString(X1, 16, f"Page {page} of {total_pages}")
    c.setFillColor(colors.black)


def render(c, d, total_pages):
    v, acc, cur = d["v"], mf.hexc(d["v"]["accent"]), d["currency"]
    hide = d["hide"]
    title = d["title"] or "Invoice"
    show_no = "invoice_no" not in hide and d["inv_no"]
    show_date = "date" not in hide and d["inv_date"]
    show_total = "total" not in hide

    def cont(c, d, page):
        c.setFillColor(TINT)
        c.rect(0, H - 44, W, 44, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(X0, H - 27, v["name"])
        c.setFont("Helvetica", 9)
        c.setFillColor(MUTED)
        c.drawRightString(X1, H - 27, f"{title} {d['inv_no'] if show_no else ''} (continued)")
        footer(c, d, page, total_pages)
        return H - 70

    pen = mf.Pen(c, d, cont, bottom=64)
    footer(c, d, 1, total_pages)

    # ---- friendly header ----------------------------------------------------------------------
    c.setFillColor(TINT)
    c.rect(0, H - 134, W, 134, stroke=0, fill=1)
    if not mf.draw_logo_image(c, d["vid"], W / 2 - 28, H - 80, 56, 56):
        fallback_mark(c, W / 2, H - 52, 28, acc)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 102, v["name"])
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawCentredString(W / 2, H - 117, f"{', '.join(v['addr'])}  ·  {v['phone']}")

    y = H - 162
    c.setFont("Helvetica", 10.5)
    c.drawCentredString(W / 2, y, f"{title} #{d['inv_no']}" if show_no else title)
    if show_total:
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(W / 2, y - 40, mf.money(d["total"], cur))
        y -= 40
    if show_date and d["due"]:
        c.setFont("Helvetica", 10.5)
        c.setFillColor(MUTED)
        c.drawCentredString(W / 2, y - 20, f"Due {mf.fdate(d['due'], v['datefmt'])}")
        y -= 20
    # Pay invoice button
    bw, bh = 210, 36
    c.setFillColor(acc)
    c.roundRect(W / 2 - bw / 2, y - 26 - bh, bw, bh, 8, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W / 2, y - 26 - bh / 2 - 4, "Pay invoice")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W / 2, y - bh - 40, "Card, Apple Pay or bank transfer accepted")
    y -= bh + 64
    hr(c, y + 12)

    # ---- billed to / details -----------------------------------------------------------------
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(X0, y - 4, "BILLED TO")
    c.drawString(W / 2 + 10, y - 4, "INVOICE DETAILS")
    c.setFillColor(INK)
    for i, ln in enumerate(d["bill_to"]):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 9.5)
        c.drawString(X0, y - 19 - i * 12.5, ln)
    det = []
    if show_no:
        det.append(("Invoice number", d["inv_no"]))
    if show_date:
        det.append(("Invoice date", mf.fdate(d["inv_date"], v["datefmt"])))
        if d["due"]:
            det.append(("Due date", mf.fdate(d["due"], v["datefmt"])))
    det.append(("Payment terms", v["terms"][0]))
    if "po" not in hide and d["po"]:
        det.append(("PO number", d["po"]))
    if d["service_period"]:
        det.append(("Service period", d["service_period"]))
    for i, (k, val) in enumerate(det):
        c.setFont("Helvetica", 9.5)
        c.setFillColor(MUTED)
        c.drawString(W / 2 + 10, y - 19 - i * 14, k)
        c.setFillColor(INK)
        c.drawRightString(X1, y - 19 - i * 14, val)
    y -= max(len(d["bill_to"]) * 12.5, len(det) * 14) + 26

    ship = mf.ship_lines(d)
    if ship:
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(X0, y, "DELIVERY")
        c.setFillColor(INK)
        c.setFont("Helvetica", 9.5)
        for i, ln in enumerate(simpleSplit("Deliver to " + ", ".join(ship), "Helvetica", 9.5, X1 - X0)):
            c.drawString(X0, y - 14 - i * 12, ln)
            y -= 12
        y -= 24
    hr(c, y + 4)

    # ---- items --------------------------------------------------------------------------------
    pen.y = y - 8
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(X0, pen.y - 6, "ITEMS")
    pen.y -= 16

    def items_cont():
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(X0, pen.y - 6, "ITEMS (continued)")
        pen.y -= 16

    for l in d["lines"]:
        name = simpleSplit(l["desc"], "Helvetica-Bold", 10.5, X1 - X0 - 110)
        h = len(name) * 13 + 26
        if pen.need(h):
            items_cont()
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10.5)
        for i, ln in enumerate(name):
            c.drawString(X0, pen.y - 12 - i * 13, ln)
        c.drawRightString(X1, pen.y - 12, mf.money(l["amount"], cur))
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(X0, pen.y - 12 - len(name) * 13 - 2, f"{mf.qty_s(l['qty'])} × {unit_price(l, cur)}")
        pen.y -= h
        hr(c, pen.y + 6)

    # ---- totals (right) + bank transfer details (left) ----------------------------------------
    tot = mf.totals_rows(d)
    bank = d["v"]["bank"]
    pay = [("Bank", bank["bank"]), ("Routing (ABA)", bank["routing"]), ("Account", bank["account"])]
    th = sum(22 if b else 18 for _, _, b in tot) + (14 if d["tax_mode"] == "inclusive" else 0)
    ph = 14 + len(pay) * 13
    pen.need(max(th, ph) + 20)
    pen.y -= 6
    top = pen.y
    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(X0, top - 10, "PAY BY BANK TRANSFER")
    for i, (k, val) in enumerate(pay):
        c.setFont("Helvetica", 9)
        c.setFillColor(MUTED)
        c.drawString(X0, top - 24 - i * 13, k)
        c.setFillColor(INK)
        c.drawString(X0 + 72, top - 24 - i * 13, val)
    for lab, val, bold in tot:
        if bold and lab == "TOTAL DUE":
            lab = "Total due"
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 13 if bold else 10)
        c.drawString(W / 2 + 10, pen.y - 12, lab)
        c.drawRightString(X1, pen.y - 12, val)
        pen.y -= 22 if bold else 18
    if d["tax_mode"] == "inclusive":
        c.setFont("Helvetica", 8)
        c.setFillColor(MUTED)
        c.drawRightString(X1, pen.y - 8, f"Prices include {d['tax_rate'] * 100:.2f}% sales tax "
                                         f"({mf.money(d['tax'], cur)}).")
    pen.y = top - max(th, ph) - 12
    hr(c, pen.y)
    pen.y -= 4

    if d["notes"]:
        pen.y -= 4
        mf.notes_block(pen, X0, d, "Helvetica-Bold", 9, X1 - X0)
    msg = simpleSplit(MESSAGE, "Helvetica-Oblique", 9, X1 - X0 - 24)
    pen.need(len(msg) * 12 + 30)
    pen.y -= 10
    bh = len(msg) * 12 + 14
    c.setFillColor(TINT)
    c.roundRect(X0, pen.y - bh, X1 - X0, bh, 6, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont("Helvetica-Oblique", 9)
    for i, ln in enumerate(msg):
        c.drawString(X0 + 12, pen.y - 15 - i * 12, ln)
    pen.y -= bh
