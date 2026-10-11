"""Great Lakes Beverage Distributors (V009): wholesale beverage invoice / delivery receipt.

Barcoded invoice number, Illinois liquor licensing block, cases/bottles split, driver + route,
"Received by" signature box and the Illinois 30-day credit law notice.
"""
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402
from reportlab.graphics.barcode import code128  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402

W, H = mf.W, mf.H
M = 42                                       # side margin
NAVY = colors.HexColor("#0F4C81")
TINT = colors.HexColor("#E8EFF6")
GREY = colors.HexColor("#5B6573")
RULE = colors.HexColor("#B8C4D2")
F, B = "Helvetica", "Helvetica-Bold"

DIST_LIC = "IL Distributor License No. 1D-0047813"
FED_PERMIT = "TTB Basic Permit IL-I-15327"
RETAILER_LIC = {"FUL": "1R-0218841", "WKP": "1R-0220917", "EVN": "1R-0231175", "LSQ": "1R-0224460",
                "OKP": "1R-0236602"}
ROUTE = {"FUL": ("22", "06"), "WKP": ("22", "11"), "EVN": ("31", "03"), "LSQ": ("27", "08"), "OKP": ("35", "04")}
CREDIT_LAW = ("ILLINOIS CREDIT LAW: Retailer must pay within 30 days per 235 ILCS 5/6-5. Accounts not paid "
              "when due are reported to the Illinois Liquor Control Commission and placed on cash-on-delivery "
              "until paid in full.")


def price_s(p):
    return mf.num(p, 4 if abs(p) < 1 else 2)


def cs_btl(l):
    """Cases / bottles split as printed text. Kegs, equipment and charges have no case count."""
    if l["unit"] == "cs":
        return mf.qty_s(l["qty"]), "0"
    if l["unit"] == "btl":
        return "0", mf.qty_s(l["qty"])
    return "--", "--"


def footer(c, page, total_pages):
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(M, 44, W - M, 44)
    c.setFont(F, 6.8)
    c.setFillColor(GREY)
    c.drawString(M, 34, "Count cases at time of delivery. Shortages, breakage and returns must be noted on this "
                        "receipt and initialed by the driver.")
    c.drawString(M, 25, "Empty kegs, CO2 cylinders and returnable shells must be returned to your driver.")
    c.setFont(B, 7.5)
    c.drawRightString(W - M, 25, f"Page {page} of {total_pages}")
    c.setFillColor(colors.black)


def barcode(c, value, x_right, y, h=26):
    b = code128.Code128(value, barHeight=h, barWidth=0.85, quiet=False)
    b.drawOn(c, x_right - b.width, y)
    c.setFont("Courier", 7.5)
    c.drawCentredString(x_right - b.width / 2, y - 9, value)


def render(c, d, total_pages):
    v, hide = d["v"], d["hide"]
    inv_no = d["inv_no"] if "invoice_no" not in hide and d["inv_no"] else ""
    show_date = "date" not in hide and d["inv_date"]
    title = d["title"] or "INVOICE"
    acct = f"{zlib.crc32(d['bill_to'][0].encode()) % 90000 + 10000}-{d['loc']}"
    route, stop = ROUTE.get(d["loc"], ("22", "01"))

    def cont(c, d, page):
        c.setFillColor(NAVY)
        c.rect(0, H - 10, W, 10, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.setFont(B, 11)
        c.drawString(M, H - 38, v["name"])
        c.setFont(F, 8.5)
        c.drawString(M, H - 51, f"{title} {inv_no}  (continued)  -  Account {acct}")
        if inv_no:
            barcode(c, inv_no, W - M, H - 52, h=18)
        footer(c, page, total_pages)
        return H - 72

    pen = mf.Pen(c, d, cont, bottom=58)
    footer(c, 1, total_pages)

    # ---- letterhead ------------------------------------------------------------------------
    c.setFillColor(NAVY)
    c.rect(0, H - 10, W, 10, stroke=0, fill=1)
    if not mf.draw_logo_image(c, d["vid"], M, H - 82, 54, 54):
        c.setFillColor(NAVY)                 # fallback mark: bottle in a roundel
        c.circle(M + 27, H - 55, 26, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.roundRect(M + 21, H - 74, 12, 26, 3, stroke=0, fill=1)
        c.rect(M + 24.5, H - 50, 5, 13, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont(B, 16)
    c.drawString(M + 64, H - 40, v["name"])
    c.setFillColor(colors.black)
    c.setFont(F, 8.5)
    for i, ln in enumerate([", ".join(v["addr"]), f"Tel {v['phone']}   |   {v['email']}",
                            f"FEIN {v['tax_id']}"]):
        c.drawString(M + 64, H - 54 - i * 11, ln)
    c.setFont(F, 7.5)
    c.setFillColor(GREY)
    c.drawString(M + 64, H - 89, f"{DIST_LIC}   |   {FED_PERMIT}")
    c.setFillColor(colors.black)

    c.setFont(B, 22)
    c.setFillColor(NAVY)
    c.drawRightString(W - M, H - 42, title.upper())
    c.setFillColor(colors.black)
    if inv_no:
        barcode(c, inv_no, W - M, H - 84)

    # ---- banner ------------------------------------------------------------------------------
    y = H - 118
    c.setFillColor(NAVY)
    c.rect(M, y, W - 2 * M, 18, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(B, 10)
    c.drawString(M + 8, y + 5.5, "DELIVERY RECEIPT — CUSTOMER COPY")
    c.setFont(F, 8)
    c.drawRightString(W - M - 8, y + 5.5, "Keep this copy for your ILCC records")
    c.setFillColor(colors.black)

    # ---- meta grid ---------------------------------------------------------------------------
    pairs = []
    if inv_no:
        pairs.append(("INVOICE NO.", inv_no))
    if show_date:
        pairs.append(("INVOICE DATE", mf.fdate(d["inv_date"], v["datefmt"])))
        if d["due"] and v["terms"][1]:
            pairs.append(("PAYMENT DUE", mf.fdate(d["due"], v["datefmt"])))
    if d["po"] and "po" not in hide:
        pairs.append(("CUSTOMER PO", d["po"]))
    pairs += [("ACCOUNT NO.", acct), ("TERMS", v["terms"][0]), ("ROUTE / STOP", f"{route} / {stop}"),
              ("SALES REP", "D. Kaminski (07)")]
    if d["service_period"]:
        pairs.append(("SERVICE PERIOD", d["service_period"]))
    ncol, cw_, ch = 4, (W - 2 * M) / 4, 26
    y -= 4
    for i, (k, val) in enumerate(pairs):
        x, yy = M + (i % ncol) * cw_, y - (i // ncol + 1) * ch
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.rect(x, yy, cw_, ch, stroke=1, fill=0)
        c.setFont(F, 6.5)
        c.setFillColor(GREY)
        c.drawString(x + 5, yy + ch - 9, k)
        c.setFillColor(colors.black)
        c.setFont(B, 9.5)
        c.drawString(x + 5, yy + 6, val)
    y -= ((len(pairs) + ncol - 1) // ncol) * ch + 14

    # ---- parties -----------------------------------------------------------------------------
    ship = mf.ship_lines(d)
    boxes = [("SOLD TO", d["bill_to"])]
    if ship:
        boxes.append(("DELIVER TO", ship))
    boxes.append(("RETAILER LICENSE", [f"IL Retailer Lic. {RETAILER_LIC.get(d['loc'], '1R-0218841')}",
                                       "Local liquor license on file", "Tax-exempt resale: No"]))
    bw = (W - 2 * M - 12 * (len(boxes) - 1)) / len(boxes)
    bh = 14 + 11 * max(len(b[1]) for b in boxes) + 6
    for j, (lab, lines) in enumerate(boxes):
        x = M + j * (bw + 12)
        c.setFillColor(TINT)
        c.rect(x, y - bh, bw, bh, stroke=0, fill=1)
        c.setFillColor(NAVY)
        c.setFont(B, 7.5)
        c.drawString(x + 7, y - 11, lab)
        c.setFillColor(colors.black)
        c.setFont(F, 8.8)
        for i, ln in enumerate(lines):
            c.drawString(x + 7, y - 24 - i * 11, ln)
    pen.y = y - bh - 14

    # ---- line items --------------------------------------------------------------------------
    cols = [("ITEM", 54, "l"), ("DESCRIPTION", 186, "l"), ("ORD", 34, "r"), ("CS", 32, "r"), ("BTL", 32, "r"),
            ("QTY", 38, "r"), ("U/M", 30, "c"), ("UNIT PRICE", 60, "r"), ("AMOUNT", 62, "r")]
    rows = []
    for l in d["lines"]:
        cs, bt = cs_btl(l)
        rows.append([l["sku"], l["desc"], mf.qty_s(l.get("ordered", l["qty"])), cs, bt, mf.qty_s(l["qty"]),
                     l["unit"].upper(), price_s(l["price"]), mf.num(l["amount"])])
    mf.draw_table(pen, M, cols, rows, dict(size=8.5, hsize=7.5, pad=4, hfill=NAVY, htext=colors.white,
                                           grid=True, gridc=RULE, zebra=colors.HexColor("#F4F7FA")))

    # ---- totals + receiving block ------------------------------------------------------------
    trows = mf.totals_rows(d)
    incl = d["tax_mode"] == "inclusive"
    pen.need(118)
    top = pen.y - 10
    # receiving box (left)
    bx, bw2, bh2 = M, 300, 104
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    c.rect(bx, top - bh2, bw2, bh2, stroke=1, fill=0)
    c.setFillColor(NAVY)
    c.rect(bx, top - 14, bw2, 14, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(B, 7.5)
    c.drawString(bx + 6, top - 10, "RECEIVED IN GOOD ORDER BY")
    c.setFillColor(colors.black)
    cases = sum(int(l["qty"]) for l in d["lines"] if l["unit"] == "cs")
    kegs = sum(int(l["qty"]) for l in d["lines"] if l["unit"] == "keg")
    c.setFont(F, 7.5)
    c.drawString(bx + 6, top - 28, f"Cases delivered: {cases}     Kegs delivered: {kegs}     Empties returned: ____")
    c.setStrokeColor(RULE)
    c.line(bx + 6, top - 62, bx + 186, top - 62)
    c.line(bx + 196, top - 62, bx + bw2 - 6, top - 62)
    c.line(bx + 6, top - 88, bx + 186, top - 88)
    c.line(bx + 196, top - 88, bx + bw2 - 6, top - 88)
    c.setFont(F, 6.5)
    c.setFillColor(GREY)
    c.drawString(bx + 6, top - 70, "Signature")
    c.drawString(bx + 196, top - 70, "Time")
    c.drawString(bx + 6, top - 96, "Print name")
    c.drawString(bx + 196, top - 96, "Driver / Truck")
    c.setFillColor(colors.black)
    c.setFont(F, 8.5)
    c.drawString(bx + 198, top - 84, f"#{route}14 R. Delgado / T-{stop}")
    if d["inv_date"] and d["inv_date"] <= mf.TODAY:   # pre-billed (future-dated) invoices are not signed
        c.setFillColorRGB(0.10, 0.16, 0.48)
        c.setFont("another", 22)
        c.drawString(bx + 14, top - 58, "M. Alvarez")
        c.setFont("kalam", 10)
        c.drawString(bx + 14, top - 85, "MARIA ALVAREZ")
        c.drawString(bx + 198, top - 58, "10:42 AM")
        c.setFillColor(colors.black)
    # totals (right)
    tx_l, tx_r = W - M - 92, W - M - 6
    ty = top - 4
    for lab, val, big in trows:
        if big:
            c.setFillColor(NAVY)
            c.rect(W - M - 210, ty - 20, 210, 22, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(B, 11)
            c.drawRightString(tx_l, ty - 13, lab.upper())
            c.drawRightString(tx_r, ty - 13, val)
            c.setFillColor(colors.black)
            ty -= 26
        else:
            c.setFont(F, 9)
            c.drawRightString(tx_l, ty - 10, lab)
            c.drawRightString(tx_r, ty - 10, val)
            ty -= 16
    if incl:
        for i, ln in enumerate(simpleSplit(f"All prices include {d['tax_rate'] * 100:.2f}% sales tax. Tax included: "
                                           f"{mf.money(d['tax'], d['currency'])}", F, 7, 210)):
            c.setFont(F, 7)
            c.drawRightString(tx_r, ty - 8 - i * 9, ln)
    pen.y = top - bh2 - 14

    # ---- credit law + remittance + notes -----------------------------------------------------
    law = simpleSplit(CREDIT_LAW, B, 7.8, W - 2 * M - 16)
    pen.need(len(law) * 10 + 12)
    c.setStrokeColor(NAVY)
    c.setLineWidth(1)
    c.rect(M, pen.y - len(law) * 10 - 8, W - 2 * M, len(law) * 10 + 8, stroke=1, fill=0)
    c.setFont(B, 7.8)
    for i, ln in enumerate(law):
        c.drawString(M + 8, pen.y - 11 - i * 10, ln)
    pen.y -= len(law) * 10 + 20

    rem = mf.remit_lines(d)
    pen.need(14 + 11 * len(rem))
    c.setFillColor(NAVY)
    c.setFont(B, 8)
    c.drawString(M, pen.y, f"REMIT TO  {v['name']}, {', '.join(v['addr'])}")
    c.setFillColor(colors.black)
    c.setFont(F, 8.5)
    for i, ln in enumerate(rem):
        c.drawString(M, pen.y - 13 - i * 11, ln)
    pen.y -= 13 + 11 * len(rem)
    mf.notes_block(pen, M, d, F, 8.5)
