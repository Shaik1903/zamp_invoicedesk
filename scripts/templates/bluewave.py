"""Bluewave IT Services (V005): hosted billing-platform style invoice (Stripe/Zoho-like, unbranded)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402
from reportlab.graphics import renderPDF  # noqa: E402
from reportlab.graphics.barcode import qr  # noqa: E402
from reportlab.graphics.shapes import Drawing  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402

W, H = mf.W, mf.H
M = 56
INK = colors.HexColor("#1A1F36")
MUTED = colors.HexColor("#5B6274")
RULE = colors.HexColor("#E3E8EE")
LABELS = {"Invoice No.": "Invoice number", "Invoice Date": "Date of issue", "Due Date": "Date due",
          "PO Number": "PO number", "Terms": "Payment terms", "Service Period": "Service period"}
X_QTY, X_PRICE, X_AMT = M + 350, M + 425, W - M  # right edges of numeric columns


def _mark(c, x, y, s, acc):
    c.setFillColor(acc)
    c.roundRect(x, y, s, s, s * 0.2, stroke=0, fill=1)
    c.setStrokeColor(colors.white)
    c.setLineWidth(s * 0.07)
    for k in range(3):
        p = c.beginPath()
        yy = y + s * (0.3 + k * 0.2)
        p.moveTo(x + s * 0.18, yy)
        p.curveTo(x + s * 0.38, yy + s * 0.12, x + s * 0.58, yy - s * 0.12, x + s * 0.82, yy)
        c.drawPath(p, fill=0, stroke=1)


def _qr(c, url, x, y, size):
    w = qr.QrCodeWidget(url)
    x0, y0, x1, y1 = w.getBounds()
    dr = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    dr.add(w)
    renderPDF.draw(dr, c, x, y)


def _price(x, cur):
    s = mf.money(x, cur)
    return s if abs(x) >= 1 else s.replace(mf.num(abs(x)), mf.num(abs(x), 4))


def render(c, d, total_pages):
    v, acc, cur = d["v"], mf.hexc(d["v"]["accent"]), d["currency"]
    show_no = "invoice_no" not in d["hide"] and d["inv_no"]
    show_total = "total" not in d["hide"]
    show_date = "date" not in d["hide"] and d["due"]
    title = d["title"] or "Invoice"
    url = f"https://pay.bluewaveit.com/i/{d['inv_no']}" if show_no else None
    due_s = mf.fdate(d["due"], v["datefmt"]) if show_date else None

    def footer(page):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        bits = [d["inv_no"] if show_no else title]
        if show_total:
            bits.append(f"{mf.money(d['total'], cur)} due {due_s}" if due_s else f"{mf.money(d['total'], cur)} due")
        c.drawString(M, 34, "  ·  ".join(bits))
        c.drawRightString(W - M, 34, f"Page {page} of {total_pages}")
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.line(M, 46, W - M, 46)
        c.setFillColor(INK)

    def head_row():
        c.setFont("Helvetica", 8)
        c.setFillColor(MUTED)
        c.drawString(M, pen.y - 10, "Description")
        c.drawRightString(X_QTY, pen.y - 10, "Qty")
        c.drawRightString(X_PRICE, pen.y - 10, "Unit price")
        c.drawRightString(X_AMT, pen.y - 10, "Amount")
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.line(M, pen.y - 16, W - M, pen.y - 16)
        c.setFillColor(INK)
        pen.y -= 16

    def cont(c, d, page):
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(INK)
        c.drawString(M, H - 50, f"{title} {d['inv_no']}" if show_no else title)
        c.setFont("Helvetica", 9)
        c.setFillColor(MUTED)
        c.drawRightString(W - M, H - 50, v["name"])
        footer(page)
        return H - 70

    pen = mf.Pen(c, d, cont)
    footer(1)

    # ---- title + logo
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(M, H - 74, title)
    if not mf.draw_logo_image(c, d["vid"], W - M - 40, H - 86, 40, 40):
        _mark(c, W - M - 40, H - 86, 40, acc)

    # ---- meta list
    y = H - 104
    for i, (k, val) in enumerate(mf.meta_pairs(d)):
        c.setFont("Helvetica", 9)
        c.setFillColor(MUTED)
        c.drawString(M, y - i * 14, LABELS.get(k, k))
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold" if k == "Invoice No." else "Helvetica", 9)
        c.drawString(M + 100, y - i * 14, val)
    y -= len(mf.meta_pairs(d)) * 14 + 14

    # ---- from / bill to / site
    cols = [("From", [v["name"]] + v["addr"] + [v["phone"], v["email"], f"Tax ID {v['tax_id']}"], M),
            ("Bill to", d["bill_to"], M + 180), ("Site", mf.ship_lines(d), M + 345)]
    low = y
    for lab, lines, x in cols:
        if not lines:
            continue
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(INK)
        c.drawString(x, y, lab)
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#3C4257"))
        for i, ln in enumerate(lines):
            c.drawString(x, y - 14 - i * 12, ln)
        low = min(low, y - 14 - (len(lines) - 1) * 12)
    c.setFillColor(INK)

    # ---- amount due block with pay link + QR
    bh = 84
    by = low - 22 - bh
    c.setFillColor(colors.HexColor("#F4F7FE"))
    c.roundRect(M, by, W - 2 * M, bh, 6, stroke=0, fill=1)
    tx = M + 16
    if show_total:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(tx, by + bh - 20, "Amount due")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 22)
        amt = mf.money(d["total"], cur)
        c.drawString(tx, by + bh - 44, amt)
        if due_s:
            c.setFont("Helvetica", 10)
            c.setFillColor(MUTED)
            c.drawString(tx + mf.pdfmetrics.stringWidth(amt, "Helvetica-Bold", 22) + 8, by + bh - 44,
                         f"{cur} due {due_s}")
    else:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(tx, by + bh - 20, "Payment")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(tx, by + bh - 42, f"Due {due_s}" if due_s else "Due on receipt")
    c.setFont("Helvetica", 9)
    if url:
        c.setFillColor(INK)
        c.drawString(tx, by + 14, "Pay online:")
        ux = tx + mf.pdfmetrics.stringWidth("Pay online: ", "Helvetica", 9)
        c.setFillColor(acc)
        c.drawString(ux, by + 14, url)
        uw = mf.pdfmetrics.stringWidth(url, "Helvetica", 9)
        c.setStrokeColor(acc)
        c.setLineWidth(0.5)
        c.line(ux, by + 12.5, ux + uw, by + 12.5)
        c.linkURL(url, (ux, by + 11, ux + uw, by + 23), relative=0)
        _qr(c, url, W - M - 76, by + 8, 68)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        c.drawRightString(W - M - 82, by + 14, "Scan to pay by card or bank")
    else:
        c.setFillColor(INK)
        c.drawString(tx, by + 14, "Pay by bank transfer using the details below.")
    c.setFillColor(INK)
    pen.y = by - 18

    # ---- summary row
    users = sum(l["qty"] for l in d["lines"] if l["unit"] == "user")
    summary = [f"{len(d['lines'])} line item{'s' if len(d['lines']) != 1 else ''}"]
    if d["service_period"]:
        summary.append(f"Service period {d['service_period']}")
    if d["po"] and "po" not in d["hide"]:
        summary.append(d["po"])
    summary.append(f"Billed in {cur}")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M, pen.y, "Summary")
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawString(M + 50, pen.y, "  ·  ".join(summary))
    c.setFillColor(INK)
    pen.y -= 18

    # ---- line items
    head_row()
    for l in d["lines"]:
        dl = simpleSplit(l["desc"], "Helvetica", 9.5, 280)
        rh = len(dl) * 12 + (11 if l["sku"] else 0) + 12
        if pen.need(rh + 2):
            head_row()
        ty = pen.y - 15
        c.setFont("Helvetica", 9.5)
        c.setFillColor(INK)
        for ln in dl:
            c.drawString(M, ty, ln)
            ty -= 12
        if l["sku"]:
            c.setFont("Helvetica", 7.5)
            c.setFillColor(MUTED)
            c.drawString(M, ty + 1, l["sku"])
        c.setFont("Helvetica", 9.5)
        c.setFillColor(INK)
        c.drawRightString(X_QTY, pen.y - 15, mf.qty_s(l["qty"]))
        c.drawRightString(X_PRICE, pen.y - 15, _price(l["price"], cur))
        c.drawRightString(X_AMT, pen.y - 15, mf.money(l["amount"], cur))
        pen.y -= rh
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.line(M, pen.y, W - M, pen.y)
    if users:
        pen.need(16)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(MUTED)
        c.drawString(M, pen.y - 13, f"Licence count this period: {mf.qty_s(users)} user"
                                    f"{'s' if users != 1 else ''} (billed per user, per month)")
        c.setFillColor(INK)
        pen.y -= 16

    # ---- totals
    trows = mf.totals_rows(d)
    pen.need(len(trows) * 20 + 12)
    pen.y -= 8
    lx = X_PRICE - 60
    for lab, val, bold in trows:
        if bold:
            c.setStrokeColor(INK)
            c.setLineWidth(0.8)
            c.line(lx, pen.y - 2, W - M, pen.y - 2)
            pen.y -= 2
            lab = "Amount due" if lab == "TOTAL DUE" else lab
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10.5 if bold else 9.5)
        c.setFillColor(INK if bold else colors.HexColor("#3C4257"))
        c.drawString(lx, pen.y - 15, lab)
        c.drawRightString(W - M, pen.y - 15, val)
        pen.y -= 20
    c.setFillColor(INK)
    if d["tax_mode"] == "inclusive":
        c.setFont("Helvetica", 8)
        c.drawRightString(W - M, pen.y - 10, f"Prices include {d['tax_rate'] * 100:.2f}% sales tax. "
                                             f"Tax included: {mf.money(d['tax'], cur)}")
        pen.y -= 14

    # ---- payment methods
    rl = mf.remit_lines(d)
    pen.need(30 + len(rl) * 12)
    pen.y -= 22
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M, pen.y, "Pay by bank transfer (ACH)")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#3C4257"))
    for i, ln in enumerate(rl):
        c.drawString(M, pen.y - 14 - i * 12, ln)
    pen.y -= 14 + len(rl) * 12
    c.setFillColor(INK)

    # ---- memo / notes
    if d["notes"]:
        pen.need(30)
        pen.y -= 14
        c.setFont("Helvetica-Bold", 9)
        c.drawString(M, pen.y, "Memo")
        pen.y -= 4
        for n in d["notes"]:
            for ln in simpleSplit(n, "Helvetica", 9, W - 2 * M):
                pen.need(13)
                c.setFont("Helvetica", 9)
                c.drawString(M, pen.y - 10, ln)
                pen.y -= 12

    pen.need(30)
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawString(M, pen.y - 22, f"Questions about this invoice? Contact {v['name']} at {v['email']} or {v['phone']}.")
    c.setFillColor(INK)
