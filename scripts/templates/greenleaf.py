"""GreenLeaf Produce Co. (V001): produce-distributor invoice printed from a wholesale ERP.

Boxed header grid (customer / route / driver), greenbar line table with COOL + lot columns,
receiving signature box, PACA trust statement, detachable remittance stub at the page bottom.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402
from reportlab.graphics.barcode import code128  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402

W, H = mf.W, mf.H
M = 36                      # side margin
CW = W - 2 * M              # content width
GREEN = colors.HexColor("#2F6B3B")
GREENBAR = colors.HexColor("#E7F1E4")
GRAY = colors.HexColor("#5B5B5B")
LABEL_BG = colors.HexColor("#EEF3EC")
STUB_H = 104                # remittance stub height, anchored above the footer
STUB_Y = 34

PACA = ("The perishable agricultural commodities listed on this invoice are sold subject to the statutory trust "
        "authorized by section 5(c) of the Perishable Agricultural Commodities Act, 1930 (7 U.S.C. 499e(c)). The "
        "seller of these commodities retains a trust claim over these commodities, all inventories of food or other "
        "products derived from these commodities, and any receivables or proceeds from the sale of these "
        "commodities until full payment is received.")
TERMS = ("Past due balances are subject to a finance charge of 1.5% per month (18% per annum). Shortages, damage or "
         "quality claims must be noted on this invoice and confirmed with the driver at the time of delivery; no "
         "credit will be issued once the driver has left. Buyer agrees to pay all costs of collection, including "
         "reasonable attorney's fees, which are sums owing in connection with this transaction under PACA.")

# Country of origin (COOL) by item; anything unknown is domestic.
COOL = {"GL-1102": "MEX", "GL-1140": "USA", "GL-1205": "USA", "GL-1311": "MEX", "GL-1420": "USA",
        "GL-1502": "MEX", "GL-1610": "USA", "GL-1733": "USA", "GL-1820": "CAN", "GL-1905": "MEX",
        "GL-2011": "USA", "GL-2104": "USA", "GL-2150": "CAN", "GL-2203": "MEX"}
ROUTES = {"FUL": ("104", "07"), "WKP": ("112", "03"), "EVN": ("131", "11"), "LSQ": ("112", "09"),
          "OKP": ("127", "05")}
DRIVERS = ["R. OCHOA #22", "D. BAKER #31", "J. NOWAK #17", "L. PRICE #08"]


def _txt(c, x, y, s, font="Helvetica", size=8.5, color=colors.black, align="l"):
    c.setFont(font, size)
    c.setFillColor(color)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[align](x, y, s)
    c.setFillColor(colors.black)


def _footer(c, d, page, total_pages):
    c.setStrokeColor(colors.HexColor("#BBBBBB"))
    c.setLineWidth(0.4)
    c.line(M, 28, W - M, 28)
    _txt(c, M, 18, "ProduceLink ERP 8.2  |  form INV-R3", size=6.5, color=GRAY)
    _txt(c, W / 2, 18, f"Page {page} of {total_pages}", size=7.5, color=GRAY, align="c")
    _txt(c, W - M, 18, "www.greenleafproduce.com", size=6.5, color=GRAY, align="r")


def _logo(c, d, x, y, s):
    if not mf.draw_logo_image(c, d["vid"], x, y, s, s):
        c.setFillColor(GREEN)
        p = c.beginPath()
        p.moveTo(x + 6, y + 6)
        p.curveTo(x + 8, y + s - 6, x + s - 10, y + s - 4, x + s - 4, y + s - 4)
        p.curveTo(x + s - 4, y + 14, x + s / 2, y + 2, x + 6, y + 6)
        c.drawPath(p, fill=1, stroke=0)
        c.setFillColor(colors.black)


def _cell(c, x, y, w, h, label, value, vsize=8.5):
    """Labelled ERP box: grey label strip on top, value below. (x, y) = top-left."""
    c.setFillColor(LABEL_BG)
    c.rect(x, y - 11, w, 11, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor("#7A8A78"))
    c.setLineWidth(0.6)
    c.rect(x, y - h, w, h, stroke=1, fill=0)
    _txt(c, x + 3, y - 8, label, "Helvetica-Bold", 6, GRAY)
    _txt(c, x + 3, y - h + 5, value, "Helvetica", vsize)


def render(c, d, total_pages):
    v = d["v"]
    rng = random.Random(f"greenleaf-{d['inv_no']}-{d['loc']}")
    title = d["title"] or "INVOICE"
    show_no = "invoice_no" not in d["hide"] and d["inv_no"]
    show_date = "date" not in d["hide"] and d["inv_date"]
    route, stop = ROUTES.get(d["loc"], ("100", "01"))
    cust_no = f"40712-{d['loc']}"

    def cont(c, d, page):
        _txt(c, M, H - 44, v["name"], "Helvetica-Bold", 11, GREEN)
        ref = f"{title} {d['inv_no']}" if show_no else title
        _txt(c, W - M, H - 44, f"{ref}  (continued)", "Helvetica", 8.5, align="r")
        c.setStrokeColor(GREEN)
        c.setLineWidth(1)
        c.line(M, H - 50, W - M, H - 50)
        _footer(c, d, page, total_pages)
        return H - 62

    pen = mf.Pen(c, d, cont, bottom=40)
    _footer(c, d, 1, total_pages)

    # --- vendor block --------------------------------------------------------------------
    _logo(c, d, M, H - 98, 60)
    nsize = 17
    while mf.pdfmetrics.stringWidth(v["name"], "Helvetica-Bold", nsize) > W - M - 190 - (M + 68):
        nsize -= 0.5
    _txt(c, M + 68, H - 52, v["name"], "Helvetica-Bold", nsize, GREEN)
    _txt(c, M + 68, H - 64, "Wholesale Fruits & Vegetables  -  Serving Chicagoland since 1987",
         "Helvetica-Oblique", 7.5, GRAY)
    info = [", ".join(v["addr"]), f"Tel {v['phone']}   |   {v['email']}",
            f"Fed. Tax ID {v['tax_id']}   |   PACA License No. 20190457"]
    for i, ln in enumerate(info):
        _txt(c, M + 68, H - 77 - i * 10.5, ln, size=8)

    # --- title / number box --------------------------------------------------------------
    bx, bw = W - M - 178, 178
    c.setFillColor(GREEN)
    c.rect(bx, H - 58, bw, 22, stroke=0, fill=1)
    tsize = 15 if len(title) <= 14 else 11
    _txt(c, bx + bw / 2, H - 52, title, "Helvetica-Bold", tsize, colors.white, "c")
    rows = []
    if show_no:
        rows.append(("INVOICE NO.", d["inv_no"]))
    if show_date:
        rows.append(("INVOICE DATE", mf.fdate(d["inv_date"], v["datefmt"])))
    y = H - 58
    for lab, val in rows:
        c.setStrokeColor(GREEN)
        c.setLineWidth(0.8)
        c.rect(bx, y - 17, bw, 17, stroke=1, fill=0)
        c.line(bx + 70, y - 17, bx + 70, y)
        _txt(c, bx + 4, y - 12, lab, "Helvetica-Bold", 7, GRAY)
        _txt(c, bx + bw - 5, y - 12.5, val, "Helvetica-Bold", 10, align="r")
        y -= 17
    if show_no:
        bc = code128.Code128(d["inv_no"], barHeight=20, barWidth=0.75)
        bc.drawOn(c, bx + (bw - bc.width) / 2, y - 25)

    # --- order info strip ----------------------------------------------------------------
    y = H - 134
    po = d["po"] if d["po"] and "po" not in d["hide"] else ""
    due = mf.fdate(d["due"], v["datefmt"]) if show_date and d["due"] and v["terms"][1] else ""
    strip = [("CUSTOMER NO.", cust_no, 70), ("CUSTOMER P.O.", po, 86), ("TERMS", v["terms"][0], 58),
             ("DUE DATE", due, 76), ("ROUTE / STOP", f"{route} / {stop}", 66), ("DRIVER", rng.choice(DRIVERS), 86),
             ("SALESPERSON", "K. MURPHY (14)", 98)]
    x = M
    for lab, val, w in strip:
        _cell(c, x, y, w, 27, lab, val)
        x += w

    # --- sold to / ship to ---------------------------------------------------------------
    y -= 37
    half = CW / 2 - 5
    ship = mf.ship_lines(d)
    boxes = [("SOLD TO", d["bill_to"])]
    boxes.append(("SHIP TO", ship) if ship else
                 ("DELIVERY INSTRUCTIONS", ["Deliver to rear receiving door, 5:00-7:00 AM.",
                                            "Keep refrigerated 34-38°F. Driver to obtain signature."]))
    bh = 14 + 11 * max(len(b[1]) for b in boxes) + 6
    for j, (lab, lines) in enumerate(boxes):
        x = M + j * (half + 10)
        c.setFillColor(GREEN)
        c.rect(x, y - 12, half, 12, stroke=0, fill=1)
        _txt(c, x + 5, y - 9, lab, "Helvetica-Bold", 7.5, colors.white)
        c.setStrokeColor(GREEN)
        c.setLineWidth(0.8)
        c.rect(x, y - bh, half, bh, stroke=1, fill=0)
        for i, ln in enumerate(lines):
            _txt(c, x + 6, y - 24 - i * 11, ln, "Helvetica-Bold" if i == 0 and lab != "DELIVERY INSTRUCTIONS"
                 else "Helvetica", 8.5)
    pen.y = y - bh - 14
    if d["service_period"]:
        _txt(c, M, pen.y, f"SERVICE PERIOD: {d['service_period']}", "Helvetica-Bold", 8.5)
        pen.y -= 12

    # --- line items ----------------------------------------------------------------------
    cols = [("ITEM NO.", 52, "l"), ("DESCRIPTION", 168, "l"), ("COOL", 36, "c"), ("LOT NO.", 62, "l"),
            ("QTY", 40, "r"), ("U/M", 32, "c"), ("UNIT PRICE", 66, "r"), ("EXTENSION", 84, "r")]
    rows = []
    for l in d["lines"]:
        lot = f"LT{rng.randint(240000, 269999)}"
        rows.append([l["sku"], l["desc"], COOL.get(l["sku"], "USA"), lot, mf.qty_s(l["qty"]), l["unit"],
                     mf.num(l["price"], 4 if l["price"] < 1 else 2), mf.num(l["amount"])])
    mf.draw_table(pen, M, cols, rows, dict(size=8.5, hsize=7.5, pad=4, hfill=GREEN, htext=colors.white,
                                           zebra=GREENBAR))
    c.setStrokeColor(GREEN)
    c.setLineWidth(1)
    c.line(M, pen.y, W - M, pen.y)

    # --- totals + receiving box ----------------------------------------------------------
    trows = mf.totals_rows(d)
    incl = d["tax_mode"] == "inclusive"
    incl_lines = simpleSplit(f"All prices include {d['tax_rate'] * 100:.2f}% sales tax. Tax included: "
                             f"{mf.money(d['tax'], d['currency'])}", "Helvetica-Oblique", 7, 200) if incl else []
    th = 18 * len(trows) + 9 * len(incl_lines)
    pen.need(max(th, 70) + 14)
    pen.y -= 8
    top = pen.y
    tx, tw = W - M - 210, 210
    y = top
    for lab, val, bold in trows:
        if bold:
            c.setFillColor(GREEN)
            c.rect(tx, y - 18, tw, 18, stroke=0, fill=1)
            _txt(c, tx + 6, y - 13, lab, "Helvetica-Bold", 9.5, colors.white)
            _txt(c, tx + tw - 6, y - 13.5, val, "Helvetica-Bold", 11, colors.white, "r")
        else:
            c.setStrokeColor(colors.HexColor("#9DB39A"))
            c.setLineWidth(0.6)
            c.rect(tx, y - 18, tw, 18, stroke=1, fill=0)
            _txt(c, tx + 6, y - 12.5, lab.upper(), "Helvetica-Bold", 7.5, GRAY)
            _txt(c, tx + tw - 6, y - 12.5, val, "Helvetica", 9.5, align="r")
        y -= 18
    for ln in incl_lines:
        _txt(c, tx + tw, y - 9, ln, "Helvetica-Oblique", 7, align="r")
        y -= 9
    pkgs = sum(l["qty"] for l in d["lines"])
    _txt(c, M, top - 9, f"TOTAL PACKAGES: {mf.qty_s(pkgs)}      LINES: {len(d['lines'])}", "Helvetica-Bold", 7.5)
    rx, rw, rh = M, 300, 54
    ry = top - 16
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.7)
    c.rect(rx, ry - rh, rw, rh, stroke=1, fill=0)
    _txt(c, rx + 5, ry - 10, "RECEIVED IN GOOD CONDITION BY:", "Helvetica-Bold", 7)
    c.setLineWidth(0.5)
    c.line(rx + 5, ry - 30, rx + 190, ry - 30)
    _txt(c, rx + 5, ry - 38, "Signature / print name", size=6, color=GRAY)
    c.line(rx + 200, ry - 30, rx + rw - 5, ry - 30)
    _txt(c, rx + 200, ry - 38, "Time / temp at delivery", size=6, color=GRAY)
    _txt(c, rx + 5, ry - 49, "Note any shortage or damage above before signing.", "Helvetica-Oblique", 6, GRAY)
    pen.y = min(y, ry - rh) - 10

    # --- remarks (notes) -----------------------------------------------------------------
    if d["notes"]:
        wrapped = [simpleSplit(n, "Helvetica-Bold", 9, CW - 16) for n in d["notes"]]
        nh = 16 + sum(len(w) * 11 for w in wrapped)
        pen.need(nh + 6)
        c.setStrokeColor(GREEN)
        c.setLineWidth(1)
        c.rect(M, pen.y - nh, CW, nh, stroke=1, fill=0)
        _txt(c, M + 6, pen.y - 10, "REMARKS", "Helvetica-Bold", 6.5, GRAY)
        yy = pen.y - 21
        for w in wrapped:
            for ln in w:
                _txt(c, M + 8, yy, ln, "Helvetica-Bold", 9)
                yy -= 11
        pen.y -= nh + 8

    # --- PACA trust + terms fine print ---------------------------------------------------
    fine = simpleSplit(PACA, "Helvetica", 6.4, CW - 12) + [""] + simpleSplit("TERMS AND CONDITIONS: " + TERMS,
                                                                                  "Helvetica", 6.4, CW - 12)
    fh = 8 + len(fine) * 7.6
    if pen.y - fh - 6 < STUB_Y + STUB_H + 28:
        pen.need(10 ** 6)   # fine print moves with the stub so the stub never sits alone on a page
    c.setStrokeColor(colors.HexColor("#999999"))
    c.setLineWidth(0.5)
    c.rect(M, pen.y - fh, CW, fh, stroke=1, fill=0)
    yy = pen.y - 9
    for ln in fine:
        _txt(c, M + 6, yy, ln, "Helvetica", 6.4, colors.HexColor("#333333"))
        yy -= 7.6
    pen.y -= fh + 6

    # --- remittance stub (anchored at the bottom of the last page) -----------------------
    if pen.y < STUB_Y + STUB_H + 28:
        pen.need(10 ** 6)   # force a new page: the stub never shares space with content above
    top = STUB_Y + STUB_H
    c.setStrokeColor(GRAY)
    c.setLineWidth(0.6)
    c.setDash(3, 2)
    c.line(M, top + 8, W - M, top + 8)
    c.setDash()
    _txt(c, W / 2, top + 11, "PLEASE DETACH AND RETURN THIS PORTION WITH YOUR PAYMENT", "Helvetica-Bold", 6.5,
         GRAY, "c")
    _txt(c, M, top - 10, "REMIT TO", "Helvetica-Bold", 7, GRAY)
    _txt(c, M, top - 22, v["name"], "Helvetica-Bold", 9)
    for i, ln in enumerate(v["addr"]):
        _txt(c, M, top - 33 - i * 10, ln, size=8)
    for i, ln in enumerate(mf.remit_lines(d)):
        _txt(c, M, top - 60 - i * 10, ln, size=7.5)
    sx, sw = W - M - 260, 260
    stub = [("CUSTOMER NO.", cust_no), ("INVOICE NO.", d["inv_no"] if show_no else ""),
            ("INVOICE DATE", mf.fdate(d["inv_date"], v["datefmt"]) if show_date else ""),
            ("AMOUNT DUE", mf.money(d["total"], d["currency"]) if "total" not in d["hide"] else "")]
    for i, (lab, val) in enumerate(stub):
        _cell(c, sx + (i % 2) * (sw / 2), top - 4 - (i // 2) * 30, sw / 2, 28, lab, val, 9)
    _txt(c, sx, STUB_Y + 18, "AMOUNT ENCLOSED:  $ ______________________", "Helvetica-Bold", 8.5)
    _txt(c, sx, STUB_Y + 6, "Make checks payable to " + v["name"], "Helvetica-Oblique", 6.5, GRAY)
