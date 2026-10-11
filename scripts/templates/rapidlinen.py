"""Rapid Linen Supply (V006): route-service invoice from older linen/uniform rental software.

Pre-printed-form look: maroon form rules with tiny caps labels, data printed in Courier, route/stop grid,
par-level rental table, signature line, agreement fine print, payment box at the foot of the last page.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402

W, H = mf.W, mf.H
M = 40
PAY_TOP = 132               # payment box occupies y < PAY_TOP on the last page
DATA, DATA_B = "Courier", "Courier-Bold"
ROUTES = {"FUL": ("07", "11"), "WKP": ("07", "23"), "EVN": ("12", "04"), "LSQ": ("09", "17"), "OKP": ("12", "19")}

AGREEMENT = ("SERVICE AGREEMENT NOTICE: Items are furnished under the Customer Rental Service Agreement on file and "
             "remain the sole property of Rapid Linen Supply. Customer is responsible for rental items in its "
             "possession; items lost, damaged, stained beyond reclaim or used for unintended purposes (e.g. grease or "
             "chemical cleanup) are charged at the current replacement schedule. Par levels may be adjusted by "
             "written request 7 days before the scheduled service day. The agreement renews automatically for "
             "successive terms unless cancelled in writing 90 days before expiry. Accounts past due are subject to a "
             "service charge of 1.5% per month and suspension of route service. Billing questions must be raised "
             "within 15 days of the invoice date.")


def _price(p):
    return mf.num(p, 4 if 0 < abs(p) < 1 else 2)


def _fallback_logo(c, x, y, s, acc):
    """Folded-towel stack mark."""
    c.setFillColor(acc)
    for i in range(3):
        c.roundRect(x + i * 2, y + i * (s * 0.3), s - i * 4, s * 0.24, 3, stroke=0, fill=1)
    c.setFillColor(colors.white)
    for i in range(3):
        c.rect(x + s * 0.62, y + i * (s * 0.3), 2.2, s * 0.24, stroke=0, fill=1)
    c.setFillColor(colors.black)


def _field(c, x, y, w, h, label, value, acc, size=9):
    c.setStrokeColor(acc)
    c.setLineWidth(0.7)
    c.rect(x, y - h, w, h, stroke=1, fill=0)
    c.setFillColor(acc)
    c.setFont("Helvetica", 5.8)
    c.drawString(x + 3, y - 7, label.upper())
    c.setFillColor(colors.black)
    c.setFont(DATA_B, size)
    c.drawString(x + 4, y - h + 5, value)


def _addr(c, x, y, w, label, lines, acc):
    h = 18 + 11 * max(len(lines), 4)
    c.setStrokeColor(acc)
    c.setLineWidth(0.7)
    c.rect(x, y - h, w, h, stroke=1, fill=0)
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(x + 4, y - 8, label)
    c.setFillColor(colors.black)
    c.setFont(DATA, 9)
    for i, ln in enumerate(lines):
        c.drawString(x + 8, y - 21 - i * 11, ln)
    return y - h


def render(c, d, total_pages):
    v, acc = d["v"], mf.hexc(d["v"]["accent"])
    title = d["title"] or "Route Service Invoice"
    show_no = "invoice_no" not in d["hide"] and d["inv_no"]
    show_date = "date" not in d["hide"] and d["inv_date"]
    route, stop = ROUTES.get(d["loc"], ("07", "01"))
    acct = f"{route}{stop}-{d['loc']}"
    dig = int("".join(ch for ch in str(d["inv_no"] or "") if ch.isdigit()) or 0)

    def page_tag(page):
        c.setFont("Helvetica", 7)
        c.setFillColor(acc)
        c.drawRightString(W - M, 22, f"Page {page} of {total_pages}")
        c.setFillColor(colors.black)

    def cont(c, d, page):
        c.setFillColor(acc)
        c.setFont("Times-Bold", 13)
        c.drawString(M, H - 46, v["name"].upper())
        c.setFillColor(colors.black)
        c.setFont(DATA, 8.5)
        ref = f"INVOICE {d['inv_no']}  " if show_no else ""
        c.drawRightString(W - M, H - 46, f"{ref}ACCT {acct}  - CONTINUED -")
        c.setStrokeColor(acc)
        c.setLineWidth(1.5)
        c.line(M, H - 54, W - M, H - 54)
        c.setLineWidth(0.5)
        c.line(M, H - 57, W - M, H - 57)
        page_tag(page)
        return H - 70

    pen = mf.Pen(c, d, cont, bottom=48)

    # --- letterhead ---------------------------------------------------------------------------
    if not mf.draw_logo_image(c, d["vid"], M, H - 90, 50, 50):
        _fallback_logo(c, M + 2, H - 86, 44, acc)
    c.setFillColor(acc)
    c.setFont("Times-Bold", 20)
    c.drawString(M + 58, H - 56, v["name"].upper())
    c.setFont("Times-Italic", 9.5)
    c.drawString(M + 58, H - 69, "Linen, Uniform & Mat Rental  -  Weekly Route Service")
    c.setFillColor(colors.black)
    c.setFont("Times-Roman", 8.8)
    c.drawString(M + 58, H - 82, f"{', '.join(v['addr'])}")
    c.drawString(M + 58, H - 93, f"Tel {v['phone']}   {v['email']}")
    c.drawString(M + 58, H - 104, f"Fed. ID No. {v['tax_id']}")

    # --- title box with route grid ------------------------------------------------------------
    bx, bw, by = W - M - 220, 220, H - 40
    c.setFillColor(acc)
    c.rect(bx, by - 16, bw, 16, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawCentredString(bx + bw / 2, by - 11.5, title.upper())
    c.setFillColor(colors.black)
    svc_day = d["inv_date"].strftime("%A").upper() if show_date else ""
    due = mf.fdate(d["due"], v["datefmt"]) if show_date and d["due"] and v["terms"][1] else ""
    grid = [("Invoice No.", d["inv_no"] if show_no else ""),
            ("Invoice Date", mf.fdate(d["inv_date"], v["datefmt"]) if show_date else ""),
            ("Account No.", acct), ("Due Date", due),
            ("Route No.", route), ("Stop No.", stop),
            ("Service Day", svc_day), ("Delivery Ticket", f"DT {(dig * 7 + 30411) % 100000:05d}")]
    fh = 22
    for i, (k, val) in enumerate(grid):
        _field(c, bx + (i % 2) * bw / 2, by - 16 - (i // 2) * fh, bw / 2, fh, k, val, acc)
    # data fields with no value stay as empty form boxes (realistic pre-printed form)

    # --- bill to / deliver to -----------------------------------------------------------------
    y = H - 156
    ship = mf.ship_lines(d)
    hw = (W - 2 * M - 12) / 2
    b1 = _addr(c, M, y, hw, "BILL TO", d["bill_to"], acc)
    b2 = _addr(c, M + hw + 12, y, hw, "DELIVER TO / SERVICE LOCATION", ship, acc) if ship else b1
    y = min(b1, b2) - 8

    # --- service line -------------------------------------------------------------------------
    po = d["po"] if d["po"] and "po" not in d["hide"] else None
    line = [("Customer P.O.", po), ("Terms", v["terms"][0]), ("Agreement No.", f"RLS-SA-{route}{stop}7"),
            ("Route Sales Rep", "D. NOWAK #31"), ("Frequency", "WEEKLY"), ("Service Period", d["service_period"])]
    line = [p for p in line if p[1]]
    fw = (W - 2 * M) / len(line)
    for i, (k, val) in enumerate(line):
        _field(c, M + i * fw, y, fw, 22, k, val, acc, 8.5)
    page_tag(1)

    # --- rental items -------------------------------------------------------------------------
    pen.y = y - 46
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(M, pen.y + 6, "RENTAL ITEMS")
    c.setFillColor(colors.black)
    cols = [("ITEM CODE", 66, "l"), ("DESCRIPTION", 186, "l"), ("PAR", 40, "r"), ("BILLED QTY", 66, "r"),
            ("U/M", 34, "c"), ("RATE", 62, "r"), ("EXTENSION", 78, "r")]
    rows = [[l["sku"], l["desc"], str(int(math.ceil(abs(l["qty"]) / 10.0) * 10)), mf.qty_s(l["qty"]), l["unit"],
             _price(l["price"]), mf.num(l["amount"])] for l in d["lines"]]
    c.setStrokeColor(acc)
    c.setLineWidth(1.2)
    c.line(M, pen.y, W - M, pen.y)
    mf.draw_table(pen, M, cols, rows, dict(font=DATA, hfont="Helvetica-Bold", size=8.6, hsize=7, pad=4,
                                          htext=acc, hline=acc, hline_w=0.8))
    c.setStrokeColor(acc)
    c.setLineWidth(1.2)
    c.line(M, pen.y - 2, W - M, pen.y - 2)
    pen.y -= 4

    # --- totals (right) + delivery acknowledgement (left) ---------------------------------------
    trows = mf.totals_rows(d)
    incl = d["tax_mode"] == "inclusive"
    th = 18 * len(trows) + (16 if incl else 0) + 14
    pen.need(max(th, 74) + 8)
    top = pen.y - 10
    tx0, tw = W - M - 210, 210
    ty = top
    for lab, val, bold in trows:
        if bold:
            c.setStrokeColor(acc)
            c.setLineWidth(0.8)
            c.line(tx0, ty - 1, W - M, ty - 1)
            c.line(tx0, ty - 3, W - M, ty - 3)
            ty -= 4
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 8.5 if bold else 7.8)
        c.setFillColor(acc if bold else colors.black)
        c.drawString(tx0 + 2, ty - 12, lab.upper())
        c.setFillColor(colors.black)
        c.setFont(DATA_B if bold else DATA, 10.5 if bold else 9)
        c.drawRightString(W - M - 2, ty - 12, val)
        ty -= 18
    if incl:
        c.setFont("Helvetica", 6.8)
        c.drawRightString(W - M, ty - 6, f"All prices include {d['tax_rate'] * 100:.2f}% sales tax. "
                                         f"Tax included: {mf.money(d['tax'], d['currency'])}")
        ty -= 16
    # acknowledgement
    c.setFillColor(acc)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(M, top - 6, "RECEIVED IN GOOD ORDER / CUSTOMER SIGNATURE")
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.line(M, top - 38, M + 230, top - 38)
    c.setFillColorRGB(0.12, 0.18, 0.45)
    c.setFont("kalam", 15)
    c.drawString(M + 10, top - 34, "M. Delgado")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 6.5)
    c.drawString(M, top - 47, "PRINT NAME:  M. DELGADO (KITCHEN MGR)")
    c.drawString(M + 160, top - 47, "RSR INITIALS:")
    c.setFillColorRGB(0.12, 0.18, 0.45)
    c.setFont("apple", 11)
    c.drawString(M + 210, top - 49, "DN")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 6.5)
    c.drawString(M, top - 60, "Soiled linen picked up and counted at stop. Count disputes within 48 hrs.")
    pen.y = min(ty, top - 66) - 6

    # --- notes --------------------------------------------------------------------------------
    if d["notes"]:
        mf.notes_block(pen, M, d, DATA, 8.2, W - 2 * M)

    # --- agreement fine print -----------------------------------------------------------------
    fp = simpleSplit(AGREEMENT, "Times-Roman", 6.6, W - 2 * M - 12)
    bh = len(fp) * 7.8 + 10
    pen.need(bh + 8)
    pen.y -= 6
    c.setStrokeColor(acc)
    c.setLineWidth(0.5)
    c.rect(M, pen.y - bh, W - 2 * M, bh, stroke=1, fill=0)
    c.setFont("Times-Roman", 6.6)
    for i, ln in enumerate(fp):
        c.drawString(M + 6, pen.y - 10 - i * 7.8, ln)
    pen.y -= bh

    # --- payment box at the foot of the last page ---------------------------------------------
    if pen.y < PAY_TOP + 6:
        pen.need(10 ** 4)
    _payment(c, d, acc, acct, show_no)


def _payment(c, d, acc, acct, show_no):
    v = d["v"]
    y, h = PAY_TOP, 92
    c.setStrokeColor(acc)
    c.setLineWidth(1.2)
    c.rect(M, y - h, W - 2 * M, h, stroke=1, fill=0)
    c.setFillColor(acc)
    c.rect(M, y - 14, W - 2 * M, 14, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(M + 6, y - 10, "PAYMENT INFORMATION")
    c.drawRightString(W - M - 6, y - 10, f"PLEASE REFERENCE ACCOUNT {acct}" +
                      (f" AND INVOICE {d['inv_no']}" if show_no else ""))
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(M + 8, y - 28, "MAIL CHECKS PAYABLE TO")
    c.drawString(M + 236, y - 28, "ELECTRONIC PAYMENT (ACH)")
    c.setFont(DATA, 8.6)
    for i, ln in enumerate([v["name"]] + v["addr"]):
        c.drawString(M + 8, y - 41 - i * 11, ln)
    for i, ln in enumerate(mf.remit_lines(d)):
        for j, part in enumerate(simpleSplit(ln, DATA, 8.2, W - 2 * M - 244)):
            c.setFont(DATA, 8.2)
            c.drawString(M + 236, y - 41 - i * 11 - j * 10, part)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(acc)
    c.drawString(M + 8, y - h + 6, "Thank you for your business. Route service questions: call your Route Sales Rep "
                                   "or our customer service desk.")
    c.setFillColor(colors.black)
