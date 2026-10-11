"""Prairie Pest Control: field service ticket = invoice + pest control service report."""
import random
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.utils import simpleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402

W, H = mf.W, mf.H
M = 36
CW = W - 2 * M
DARK = colors.HexColor("#1A2E05")
GREY = colors.HexColor("#5B6352")
BOX = colors.HexColor("#9CA88C")
PALE = colors.HexColor("#F2F6EA")
PEN_INK = colors.HexColor("#1E3A8A")
RED = colors.HexColor("#B91C1C")

TECH = ("Marcus Delgado", "041-018273")

# sku -> (products applied, areas, findings ticked, comment)
PRODUCTS = {
    "PC-MO": [("Cockroach gel bait (indoxacarb 0.6%)", "352-652", "German cockroach", "Crack & crevice, cook line", "14 g"),
              ("Insect growth regulator (pyriproxyfen)", "2724-351", "Cockroach", "Floor/wall voids, dish area", "2 fl oz")],
    "PC-RS": [("Rodenticide bait block (bromadiolone 0.005%)", "12455-79", "Norway rat, house mouse",
               "Tamper-resistant exterior stations", "16 blocks")],
    "PC-DR": [("Drain fly foam (pyrethrins 0.5%)", "1021-1569", "Drain flies", "Floor drains, bar sinks - foam", "24 fl oz"),
              ("Microbial drain gel (Bacillus spp.)", "73049-424", "Drain fly larvae", "Floor drains - pour", "1 qt")],
}
AREAS = ["Kitchen / cook line", "Dish area", "Dry storage", "Walk-in coolers", "Dining room", "Bar",
         "Restrooms", "Floor drains", "Dumpster enclosure", "Exterior perimeter"]
AREAS_BY_SKU = {
    "PC-MO": {"Kitchen / cook line", "Dish area", "Dry storage", "Walk-in coolers", "Restrooms", "Exterior perimeter"},
    "PC-FL": {"Kitchen / cook line", "Dining room", "Bar"},
    "PC-RS": {"Dumpster enclosure", "Exterior perimeter"},
    "PC-DR": {"Floor drains", "Bar", "Dish area"},
    "PC-INS": {"Kitchen / cook line", "Dry storage", "Floor drains"},
}
COMMENTS = {
    "PC-MO": "Routine service completed; interior monitors checked and gel bait applied at harbourage points.",
    "PC-FL": "Fly light units cleaned, glue boards replaced, UV tubes tested and working.",
    "PC-RS": "Damaged exterior bait stations replaced and re-anchored; fresh bait installed.",
    "PC-DR": "Drain fly breeding in floor drains; drains foamed and gel applied. Please brush drains nightly.",
    "PC-INS": "Follow-up inspection of previously treated areas; activity reduced.",
}


def unit_price(p):
    return mf.num(p, 4 if p < 1 else 2)


def check(c, x, y, on, size=7.5):
    c.setStrokeColor(DARK)
    c.setLineWidth(0.7)
    c.rect(x, y, size, size, stroke=1, fill=0)
    if on:
        c.setStrokeColor(PEN_INK)
        c.setLineWidth(1.4)
        p = c.beginPath()
        p.moveTo(x + 1.2, y + size * 0.5)
        p.lineTo(x + size * 0.42, y + 1.2)
        p.lineTo(x + size + 2, y + size + 2.5)
        c.drawPath(p, stroke=1, fill=0)


def field_box(c, x, y, w, h, lab, val, vfont="Helvetica-Bold", vsize=9.5, vcol=colors.black):
    c.setStrokeColor(BOX)
    c.setLineWidth(0.7)
    c.rect(x, y - h, w, h, stroke=1, fill=0)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 6.3)
    c.drawString(x + 4, y - 8, lab.upper())
    c.setFillColor(vcol)
    c.setFont(vfont, vsize)
    c.drawString(x + 4, y - h + 6, val)
    c.setFillColor(colors.black)


def section_bar(c, y, text, acc):
    c.setFillColor(acc)
    c.rect(M, y - 14, CW, 14, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(M + 6, y - 10, text)
    c.setFillColor(colors.black)
    return y - 14


def fallback_mark(c, x, y, s, acc):
    """Wheat stalk inside a circle."""
    c.setFillColor(acc)
    c.circle(x + s / 2, y + s / 2, s / 2, stroke=0, fill=1)
    c.setStrokeColor(colors.white)
    c.setFillColor(colors.white)
    c.setLineWidth(1.6)
    cx = x + s / 2
    c.line(cx, y + s * 0.15, cx, y + s * 0.8)
    for k in range(4):
        yy = y + s * (0.38 + k * 0.11)
        c.ellipse(cx - s * 0.17, yy, cx - s * 0.02, yy + s * 0.08, stroke=0, fill=1)
        c.ellipse(cx + s * 0.02, yy, cx + s * 0.17, yy + s * 0.08, stroke=0, fill=1)


def footer(c, page, total_pages):
    c.setFont("Helvetica", 6.8)
    c.setFillColor(GREY)
    c.drawString(M, 30, "Pesticide labels and Safety Data Sheets for all products applied are available on request. "
                        "Keep treated areas clear until dry.")
    c.drawRightString(W - M, 18, f"Page {page} of {total_pages}")
    c.setFillColor(colors.black)


def render(c, d, total_pages):
    v, acc = d["v"], mf.hexc(d["v"]["accent"])
    hide = d["hide"]
    skus = [l["sku"] for l in d["lines"]]
    rng = random.Random(d["inv_no"] or "prairie")
    title = d["title"] or "SERVICE INVOICE"
    ticket = d["inv_no"] if "invoice_no" not in hide and d["inv_no"] else ""

    def cont(c, d, page):
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(DARK)
        c.drawString(M, H - 40, v["name"])
        c.setFont("Helvetica", 8.5)
        c.drawRightString(W - M, H - 40, f"{title} {ticket} - continued")
        c.setStrokeColor(acc)
        c.line(M, H - 46, W - M, H - 46)
        c.setFillColor(colors.black)
        footer(c, page, total_pages)
        return H - 60

    pen = mf.Pen(c, d, cont, bottom=50)
    footer(c, 1, total_pages)

    # ---- header -----------------------------------------------------------------------------
    if not mf.draw_logo_image(c, d["vid"], M, H - 96, 58, 58):
        fallback_mark(c, M + 2, H - 94, 54, acc)
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(M + 68, H - 52, v["name"])
    c.setFont("Helvetica", 8.3)
    c.setFillColor(GREY)
    c.drawString(M + 68, H - 65, f"{', '.join(v['addr'])}   Tel {v['phone']}")
    c.drawString(M + 68, H - 76, f"{v['email']}   FEIN {v['tax_id']}")
    c.drawString(M + 68, H - 87, "IDPH Structural Pest Control Business License No. 0612-B")
    c.setFillColor(colors.black)
    bw, bx = 176, W - M - 176
    c.setFillColor(acc)
    c.rect(bx, H - 64, bw, 28, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12.5)
    c.drawCentredString(bx + bw / 2, H - 51, title)
    c.setFont("Helvetica", 7)
    c.drawCentredString(bx + bw / 2, H - 60, "& PEST CONTROL SERVICE REPORT")
    c.setStrokeColor(acc)
    c.setLineWidth(1)
    c.rect(bx, H - 96, bw, 60, stroke=1, fill=0)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 6.3)
    c.drawString(bx + 6, H - 73, "TICKET / INVOICE NO.")
    if ticket:
        c.setFillColor(RED)
        c.setFont("Courier-Bold", 15)
        c.drawRightString(bx + bw - 8, H - 91, ticket)
    c.setFillColor(colors.black)

    # ---- form fields --------------------------------------------------------------------------
    y = H - 108
    fields = []
    if "date" not in hide and d["inv_date"]:
        fields.append(("Invoice date", mf.fdate(d["inv_date"], v["datefmt"])))
    if "date" not in hide and d["due"]:
        fields.append(("Due date", mf.fdate(d["due"], v["datefmt"])))
    fields.append(("Terms", v["terms"][0]))
    if "po" not in hide and d["po"]:
        fields.append(("Customer PO", d["po"]))
    if d["service_period"]:
        fields.append(("Service period", d["service_period"]))
    fields.append(("Account no.", f"CPR-{d['loc']}-0417"))
    fw = CW / len(fields)
    for i, (k, val) in enumerate(fields):
        field_box(c, M + i * fw, y, fw, 26, k, val)
    y -= 34

    ship = mf.ship_lines(d)
    blocks = [("Bill to", d["bill_to"])] + ([("Service location", ship)] if ship else [])
    bh = max(len(b[1]) for b in blocks) * 11 + 18
    for i, (lab, lines) in enumerate(blocks):
        x = M + i * (CW / 2 + 4)
        w = CW / 2 - 4
        c.setStrokeColor(BOX)
        c.rect(x, y - bh, w, bh, stroke=1, fill=0)
        c.setFillColor(GREY)
        c.setFont("Helvetica", 6.3)
        c.drawString(x + 4, y - 8, lab.upper())
        c.setFillColor(colors.black)
        for j, ln in enumerate(lines):
            c.setFont("Helvetica-Bold" if j == 0 else "Helvetica", 9)
            c.drawString(x + 6, y - 20 - j * 11, ln)
    y -= bh + 8

    t_in = rng.randint(6 * 60 + 30, 9 * 60 + 30)
    t_out = t_in + rng.randint(35, 70)
    hm = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    stype = "Routine - monthly" if "PC-MO" in skus else ("Follow-up / callback" if "PC-INS" in skus else "Special treatment")
    techf = [("Technician", TECH[0], 140), ("IL structural pest control lic. no.", f"Tech. Lic. {TECH[1]}", 160),
             ("Time in / time out", f"{hm(t_in)} / {hm(t_out)}", 110), ("Service type", stype, CW - 410)]
    x = M
    for lab, val, w in techf:
        field_box(c, x, y, w, 26, lab, val, "Helvetica", 9)
        x += w
    pen.y = y - 36

    # ---- charges ----------------------------------------------------------------------------
    pen.y = section_bar(c, pen.y, "CHARGES", acc) - 2
    cols = [("CODE", 62, "l"), ("SERVICE / MATERIAL", 268, "l"), ("QTY", 50, "r"), ("UNIT PRICE", 76, "r"),
            ("AMOUNT", CW - 456, "r")]
    body = [[l["sku"], l["desc"], mf.qty_s(l["qty"]), unit_price(l["price"]), mf.num(l["amount"])] for l in d["lines"]]
    mf.draw_table(pen, M, cols, body, dict(size=9, hsize=7.2, hfill=PALE, htext=DARK, grid=True, gridc=BOX))
    tot = mf.totals_rows(d)
    remit = mf.remit_lines(d)
    rh = len(remit) * 10.5 + 18
    th = len(tot) * 18 + (12 if d["tax_mode"] == "inclusive" else 0)
    pen.need(max(rh, th) + 14)
    pen.y -= 6
    top = pen.y
    # remit box (left of totals)
    rw = CW - 210 - 16
    c.setFillColor(PALE)
    c.rect(M, top - rh, rw, rh, stroke=0, fill=1)
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(M + 6, top - 10, f"PLEASE REMIT TO {v['name'].upper()}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.3)
    for i, ln in enumerate(remit):
        c.drawString(M + 6, top - 21 - i * 10.5, ln)
    tx = W - M - 210
    for lab, val, bold in tot:
        if bold:
            c.setStrokeColor(DARK)
            c.setLineWidth(1.2)
            c.rect(tx, pen.y - 18, 210, 18, stroke=1, fill=0)
            c.setFont("Helvetica-Bold", 10.5)
        else:
            c.setFont("Helvetica", 9)
        c.drawString(tx + 6, pen.y - 12.5, lab)
        c.drawRightString(W - M - 6, pen.y - 12.5, val)
        pen.y -= 18
    if d["tax_mode"] == "inclusive":
        c.setFont("Helvetica", 7)
        c.drawRightString(W - M, pen.y - 9, f"Prices include {d['tax_rate'] * 100:.2f}% sales tax "
                                            f"({mf.money(d['tax'], d['currency'])}).")
    pen.y = top - max(rh, th) - 12

    # ---- service report ---------------------------------------------------------------------
    pen.need(14 + 16 + 3 * 13 + 10)
    pen.y = section_bar(c, pen.y, "SERVICE REPORT", acc) - 6
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(M, pen.y - 8, "AREAS SERVICED")
    pen.y -= 14
    done = set().union(*(AREAS_BY_SKU.get(s, set()) for s in skus)) or {"Kitchen / cook line"}
    for i, a in enumerate(AREAS):
        x = M + (i % 4) * (CW / 4)
        yy = pen.y - (i // 4) * 13
        check(c, x, yy - 8, a in done)
        c.setFont("Helvetica", 8.3)
        c.drawString(x + 12, yy - 7.5, a)
    pen.y -= ((len(AREAS) + 3) // 4) * 13 + 8

    prods = [p for s in dict.fromkeys(skus) for p in PRODUCTS.get(s, [])]
    if not prods:
        prods = [("None applied - inspection and monitoring only", "-", "-", "-", "-")]
    pen.need(60)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(M, pen.y - 8, "PRODUCTS APPLIED")
    pen.y -= 12
    pcols = [("PRODUCT", 190, "l"), ("EPA REG. NO.", 70, "l"), ("TARGET PEST", 100, "l"),
             ("SITE / METHOD", 120, "l"), ("QTY USED", CW - 480, "r")]
    mf.draw_table(pen, M, pcols, [list(p) for p in prods],
                  dict(size=8, hsize=6.8, pad=3, hline=DARK, hline_w=0.6, grid=True, gridc=BOX))
    pen.y -= 10

    level = 1 if "PC-DR" in skus or "PC-RS" in skus else 0
    findings = [
        ("Interior monitoring devices inspected", True),
        ("Exterior bait stations inspected / serviced", "PC-RS" in skus or "PC-MO" in skus),
        ("Fly light units cleaned, glue boards replaced", "PC-FL" in skus),
        ("Drain fly activity at floor drains - treated", "PC-DR" in skus),
        ("Live rodent activity observed", False),
        ("Sanitation conditions acceptable", "PC-DR" not in skus),
        ("Structural / exclusion repairs recommended", False),
        ("Door sweeps and seals intact", True),
    ]
    pen.need(14 + 4 * 13 + 18)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(M, pen.y - 8, "FINDINGS")
    c.setFont("Helvetica", 8)
    c.drawString(M + 250, pen.y - 8, "Activity level:")
    for i, lab in enumerate(["None", "Low", "Moderate", "High"]):
        x = M + 312 + i * 58
        check(c, x, pen.y - 9, i == level)
        c.drawString(x + 11, pen.y - 8, lab)
    pen.y -= 16
    for i, (lab, on) in enumerate(findings):
        x = M + (i % 2) * (CW / 2)
        yy = pen.y - (i // 2) * 13
        check(c, x, yy - 8, on)
        c.setFont("Helvetica", 8.3)
        c.drawString(x + 12, yy - 7.5, lab)
    pen.y -= ((len(findings) + 1) // 2) * 13 + 6

    comment = " ".join(COMMENTS[s] for s in dict.fromkeys(skus) if s in COMMENTS)
    clines = simpleSplit(comment, "Helvetica-Oblique", 8.3, CW - 10)
    pen.need(len(clines) * 10.5 + 22)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(M, pen.y - 8, "TECHNICIAN COMMENTS")
    pen.y -= 12
    c.setStrokeColor(BOX)
    c.rect(M, pen.y - len(clines) * 10.5 - 6, CW, len(clines) * 10.5 + 6, stroke=1, fill=0)
    c.setFont("Helvetica-Oblique", 8.3)
    for i, ln in enumerate(clines):
        c.drawString(M + 5, pen.y - 10 - i * 10.5, ln)
    pen.y -= len(clines) * 10.5 + 14

    # ---- signatures -----------------------------------------------------------------
    pen.need(44)
    for i, (who, sig, font, sub) in enumerate((("Customer signature", "J. Moreno", "reenie", "Print name: J. Moreno"),
                                              ("Technician signature", "M. Delgado", "shadows",
                                               f"{TECH[0]}, Tech. Lic. {TECH[1]}"))):
        x = M + i * (CW / 2 + 10)
        c.setFillColor(PEN_INK)
        c.setFont(font, 17)
        c.drawString(x + 10, pen.y - 19, sig)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.6)
        c.line(x, pen.y - 26, x + CW / 2 - 20, pen.y - 26)
        c.setFillColor(GREY)
        c.setFont("Helvetica", 6.8)
        c.drawString(x, pen.y - 36, f"{who}   {sub}")
        c.setFillColor(colors.black)
    pen.y -= 46

    mf.notes_block(pen, M, d, "Helvetica-Bold", 8.5, CW)
