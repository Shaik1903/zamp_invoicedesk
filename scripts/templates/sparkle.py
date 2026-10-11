"""Sparkle Commercial Cleaning (V003): small-business invoice built from a Word/Google-Docs template."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402

W, H = mf.W, mf.H
M = 54  # page margin
LAV = colors.HexColor("#EFE8F8")
GREY = colors.HexColor("#5F5A66")
LABELS = {"Invoice No.": "Invoice #", "Invoice Date": "Invoice date", "PO Number": "P.O. #",
          "Terms": "Terms", "Due Date": "Due date", "Service Period": "Service period"}


def _sparkle_mark(c, x, y, s, acc):
    c.setFillColor(acc)
    c.roundRect(x, y, s, s, s * 0.22, stroke=0, fill=1)
    c.setFillColor(colors.white)
    for cx, cy, r in ((x + s * 0.46, y + s * 0.48, s * 0.32), (x + s * 0.76, y + s * 0.76, s * 0.12)):
        p = c.beginPath()
        p.moveTo(cx, cy + r)
        for px, py in ((cx + r * .22, cy + r * .22), (cx + r, cy), (cx + r * .22, cy - r * .22), (cx, cy - r),
                       (cx - r * .22, cy - r * .22), (cx - r, cy), (cx - r * .22, cy + r * .22)):
            p.lineTo(px, py)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
    c.setFillColor(colors.black)


def _footer(c, d, page, total_pages):
    c.setFont("Helvetica", 7.5)
    c.setFillColor(GREY)
    c.drawCentredString(W / 2, 44, "Licensed, bonded & insured  ·  Serving Chicagoland restaurants since 2011  "
                                   "·  Nights, weekends & holidays")
    c.setFillColor(colors.black)
    mf.footer_pages(c, d, page, total_pages)


def render(c, d, total_pages):
    v, acc = d["v"], mf.hexc(d["v"]["accent"])
    title = d["title"] or "INVOICE"
    show_no = "invoice_no" not in d["hide"] and d["inv_no"]

    def cont(c, d, page):
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(acc)
        c.drawString(M, H - 48, v["name"])
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        c.drawRightString(W - M, H - 48, f"{title.title()} {d['inv_no']} (continued)" if show_no
                          else f"{title.title()} (continued)")
        _footer(c, d, page, total_pages)
        return H - 72

    pen = mf.Pen(c, d, cont)
    _footer(c, d, 1, total_pages)

    # ---- letterhead
    if not mf.draw_logo_image(c, d["vid"], M, H - 104, 50, 50):
        _sparkle_mark(c, M, H - 104, 50, acc)
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(M + 62, H - 66, v["name"])
    c.setFillColor(GREY)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(M + 62, H - 79, "Restaurant & commercial cleaning you can count on")
    c.setFillColor(colors.HexColor("#26232B"))
    c.setFont("Helvetica", 9)
    c.drawString(M + 62, H - 92, ", ".join(v["addr"]))
    c.drawString(M + 62, H - 103, f"{v['phone']}  ·  {v['email']}  ·  FEIN {v['tax_id']}")
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(W - M, H - 68, title)
    c.setStrokeColor(acc)
    c.setLineWidth(2)
    c.line(M, H - 116, W - M, H - 116)
    c.setFillColor(colors.black)

    # ---- bill to / service location / details table
    y = H - 140
    blocks = [("BILL TO", d["bill_to"], M), ("SERVICE LOCATION", mf.ship_lines(d), M + 172)]
    low = y
    for lab, lines, x in blocks:
        if not lines:
            continue
        c.setFillColor(acc)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, y, lab)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        for i, ln in enumerate(lines):
            c.drawString(x, y - 13 - i * 11.5, ln)
        low = min(low, y - 13 - (len(lines) - 1) * 11.5)
    bx, bw, lw, rh = W - M - 168, 168, 72, 16
    pairs = mf.meta_pairs(d)
    top = y + 9
    c.setStrokeColor(colors.HexColor("#C9B8E3"))
    c.setLineWidth(0.6)
    for i, (k, val) in enumerate(pairs):
        ry = top - (i + 1) * rh
        c.setFillColor(LAV)
        c.rect(bx, ry, lw, rh, stroke=0, fill=1)
        c.rect(bx, ry, bw, rh, stroke=1, fill=0)
        c.line(bx + lw, ry, bx + lw, ry + rh)
        c.setFillColor(acc)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(bx + 5, ry + 5, LABELS.get(k, k))
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8.8)
        c.drawRightString(bx + bw - 5, ry + 5, val)
    low = min(low, top - len(pairs) * rh)
    pen.y = low - 22

    # ---- service log
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(M, pen.y - 12, "Service log" + (f" — {d['service_period']}" if d["service_period"] else ""))
    c.setFillColor(GREY)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawString(M, pen.y - 25, "Work performed by the Sparkle crew at the service location above. "
                                "Supervisor walk-through completed on each visit.")
    c.setFillColor(colors.black)
    pen.y -= 34
    cols = [("Code", 58, "l"), ("Service performed", 252, "l"), ("Qty", 46, "r"), ("Rate", 74, "r"),
            ("Amount", 74, "r")]
    rows = [[l["sku"], l["desc"], mf.qty_s(l["qty"]), mf.num(l["price"], 4 if l["price"] < 1 else 2),
             mf.num(l["amount"])] for l in d["lines"]]
    mf.draw_table(pen, M, cols, rows, dict(size=9.2, hfill=LAV, htext=acc, hsize=8.5, grid=True,
                                           gridc=colors.HexColor("#D9CCEB"), pad=5))

    # ---- totals
    trows = mf.totals_rows(d)
    pen.need(len(trows) * 18 + 10)
    pen.y -= 8
    tx, tw = W - M - 200, 200
    for lab, val, bold in trows:
        if bold:
            c.setFillColor(acc)
            c.rect(tx, pen.y - 20, tw, 20, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 11)
            lab = "Total due" if lab == "TOTAL DUE" else lab
            c.drawString(tx + 8, pen.y - 14, lab)
            c.drawRightString(tx + tw - 6, pen.y - 14, val)
            pen.y -= 20
        else:
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 9.5)
            c.drawString(tx + 8, pen.y - 13, lab)
            c.drawRightString(tx + tw - 6, pen.y - 13, val)
            c.setStrokeColor(colors.HexColor("#D9CCEB"))
            c.line(tx, pen.y - 18, tx + tw, pen.y - 18)
            pen.y -= 18
    c.setFillColor(colors.black)
    if d["tax_mode"] == "inclusive":
        c.setFont("Helvetica", 8)
        c.drawRightString(W - M, pen.y - 11, f"All rates include {d['tax_rate'] * 100:.2f}% sales tax. "
                                             f"Tax included: {mf.money(d['tax'], d['currency'])}")
        pen.y -= 14

    # ---- how to pay + thank you / signature
    pen.need(118)
    pen.y -= 24
    y0 = pen.y
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(M, y0, "How to pay")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.6)
    pay = [f"Checks payable to {v['name']}, mailed to the address above.", "ACH / direct deposit:"]
    pay += ["    " + ln for ln in mf.remit_lines(d)]
    pay += [f"Terms: {v['terms'][0]}. Please write the invoice number on your check or ACH memo."]
    for i, ln in enumerate(pay):
        c.drawString(M, y0 - 14 - i * 11.5, ln)
    sx = W - M - 190
    c.setFillColor(acc)
    c.setFont("Helvetica-BoldOblique", 12)
    c.drawString(sx, y0, "Thank you for choosing Sparkle!")
    c.setFillColor(colors.HexColor("#1F2A6B"))
    c.setFont("apple", 17)
    c.drawString(sx + 6, y0 - 46, "Maria Delgado")
    c.setStrokeColor(GREY)
    c.setLineWidth(0.6)
    c.line(sx, y0 - 54, W - M, y0 - 54)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 8.5)
    c.drawString(sx, y0 - 65, "Maria Delgado, Owner")
    c.drawString(sx, y0 - 76, "Licensed, bonded & insured")
    c.setFillColor(colors.black)
    pen.y = y0 - 14 - len(pay) * 11.5

    # ---- notes, in a loud highlighted box right under the payment details (as bank-change letters do)
    if d["notes"]:
        pen.y -= 14
        tw = W - 2 * M - 24
        wrapped = [simpleSplit(n, "Helvetica-Bold", 9.5, tw) for n in d["notes"]]
        bh = 26 + sum(len(w) * 12.5 + 4 for w in wrapped)
        pen.need(bh + 4)
        c.setFillColor(colors.HexColor("#FFF3CD"))
        c.setStrokeColor(colors.HexColor("#B42318"))
        c.setLineWidth(1.2)
        c.rect(M, pen.y - bh, W - 2 * M, bh, stroke=1, fill=1)
        c.setFillColor(colors.HexColor("#B42318"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(M + 12, pen.y - 15, "PLEASE NOTE")
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 9.5)
        ty = pen.y - 30
        for w in wrapped:
            for ln in w:
                c.drawString(M + 12, ty, ln)
                ty -= 12.5
            ty -= 4
        pen.y -= bh + 18
