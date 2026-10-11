"""Maritime Seafood Exporters Ltd. (V012): bilingual (EN/FR) Canadian export invoice in CAD.

Centered letterhead over a navy rule, bilingual meta grid, shipment/export block (Incoterms, CFIA
certificate, HS codes), hairline-ruled line table with two-line bilingual headings, origin
declaration with signature, payment instructions and a boxed remittance advice.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402

W, H = mf.W, mf.H
M = 42
CW = W - 2 * M
NAVY = colors.HexColor("#0E5A7A")
INK = colors.HexColor("#1B2733")
GRAY = colors.HexColor("#5F6B75")
RULE = colors.HexColor("#B9C6CF")
TINT = colors.HexColor("#EEF4F7")

# HS (harmonized system) codes by item; fallback is "other fish/seafood, fresh or chilled".
HS = {"MS-LOB": "0306.32", "MS-SCL": "0307.21", "MS-OYS": "0307.11"}
COLS = [("Item", "Article", 54, "l"), ("Description", "Description", 186, "l"), ("Origin", "Origine", 42, "c"),
        ("Qty", "Qté", 44, "r"), ("Unit", "Unité", 38, "c"), ("Unit price", "Prix unitaire", 74, "r"),
        ("Amount", "Montant", 90, "r")]


def _t(c, x, y, s, font="Helvetica", size=8.5, color=INK, align="l"):
    c.setFont(font, size)
    c.setFillColor(color)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[align](x, y, s)
    c.setFillColor(colors.black)


def _bi(c, x, y, en, fr, align="l", size=6.5):
    """Bilingual label: English bold, French italic, on one line."""
    if align == "r":
        _t(c, x, y, fr, "Helvetica-Oblique", size, GRAY, "r")
        x -= stringWidth(fr, "Helvetica-Oblique", size) + 3
        _t(c, x, y, en + " /", "Helvetica-Bold", size, GRAY, "r")
    else:
        _t(c, x, y, en + " /", "Helvetica-Bold", size, GRAY)
        _t(c, x + stringWidth(en + " / ", "Helvetica-Bold", size), y, fr, "Helvetica-Oblique", size, GRAY)


def _footer(c, d, page, total_pages):
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.6)
    c.line(M, 32, W - M, 32)
    _t(c, M, 22, f"{d['v']['name']}  -  CFIA registered establishment no. 1874  -  www.maritimeseafood.ca",
       size=6.5, color=GRAY)
    _t(c, W - M, 22, f"Page {page} of {total_pages}  /  Page {page} de {total_pages}", size=7, color=GRAY,
       align="r")


def _table_header(c, y):
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.4)
    c.line(M, y, W - M, y)
    x = M
    for en, fr, w, a in COLS:
        tx = {"l": x + 4, "r": x + w - 4, "c": x + w / 2}[a]
        _t(c, tx, y - 11, en, "Helvetica-Bold", 7.5, NAVY, a)
        _t(c, tx, y - 20, fr, "Helvetica-Oblique", 6.5, GRAY, a)
        x += w
    c.setLineWidth(0.6)
    c.line(M, y - 25, W - M, y - 25)
    return y - 25


def render(c, d, total_pages):
    v = d["v"]
    rng = random.Random(f"maritime-{d['inv_no']}")
    cur = d["currency"]
    title = d["title"] or "INVOICE"
    show_no = "invoice_no" not in d["hide"] and d["inv_no"]
    show_date = "date" not in d["hide"] and d["inv_date"]

    in_table = [False]   # cont() repeats the table header only while lines are still flowing

    def cont(c, d, page):
        _t(c, M, H - 44, v["name"], "Times-Bold", 12, NAVY)
        ref = f"{title} / FACTURE {d['inv_no']}" if show_no and not d["title"] else (
            f"{title} {d['inv_no']}" if show_no else title)
        _t(c, W - M, H - 44, ref + "  (cont.)", size=8.5, align="r")
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.8)
        c.line(M, H - 50, W - M, H - 50)
        _footer(c, d, page, total_pages)
        return _table_header(c, H - 62) if in_table[0] else H - 62

    pen = mf.Pen(c, d, cont, bottom=44)
    _footer(c, d, 1, total_pages)

    # --- letterhead (left) + bilingual title (right) -----------------------------------------
    c.setFillColor(NAVY)
    c.rect(0, H - 10, W, 10, stroke=0, fill=1)
    if not mf.draw_logo_image(c, d["vid"], M, H - 84, 58, 58):
        c.setStrokeColor(NAVY)
        c.setLineWidth(2.5)
        for k in range(3):
            p = c.beginPath()
            p.moveTo(M + 4, H - 70 + k * 12)
            p.curveTo(M + 20, H - 60 + k * 12, M + 36, H - 80 + k * 12, M + 54, H - 70 + k * 12)
            c.drawPath(p, fill=0, stroke=1)
    nsize = 17
    while stringWidth(v["name"], "Times-Bold", nsize) > 290:
        nsize -= 0.5
    _t(c, M + 68, H - 42, v["name"], "Times-Bold", nsize, NAVY)
    _t(c, M + 68, H - 54, "Live & fresh Atlantic shellfish  -  Fruits de mer frais de l'Atlantique",
       "Times-Italic", 8.5, GRAY)
    for i, ln in enumerate([", ".join(v["addr"]), f"Tel. / Tél. {v['phone']}   {v['email']}"]):
        _t(c, M + 68, H - 67 - i * 10.5, ln, size=8)
    _bi(c, M + 68, H - 89, "Business No.", "No d'entreprise", size=7)
    _t(c, M + 68 + stringWidth("Business No. / No d'entreprise  ", "Helvetica-Bold", 7), H - 89, v["tax_id"],
       "Helvetica-Bold", 8)

    if d["title"]:
        avail = W - M - (M + 68 + 300) - 10   # right of the name/tagline column
        tsize = 20
        while stringWidth(title, "Times-Bold", tsize) > avail and tsize > 9:
            tsize -= 0.5
        _t(c, W - M, H - 48, title, "Times-Bold", tsize, NAVY, "r")
    else:
        _t(c, W - M, H - 46, "INVOICE", "Times-Bold", 24, NAVY, "r")
        _t(c, W - M, H - 64, "FACTURE", "Times-Italic", 15, GRAY, "r")
    _t(c, W - M, H - 82, "Export sale  /  Vente à l'exportation", "Helvetica-Oblique", 7.5, GRAY, "r")

    # --- bilingual meta grid (2 rows x 4 cells) ------------------------------------------------
    po = d["po"] if d["po"] and "po" not in d["hide"] else ""
    due = mf.fdate(d["due"], v["datefmt"]) if show_date and d["due"] and v["terms"][1] else ""
    grid = [("Invoice No.", "No de facture", d["inv_no"] if show_no else ""),
            ("Invoice date", "Date de facture", mf.fdate(d["inv_date"], v["datefmt"]) if show_date else ""),
            ("Due date", "Échéance", due),
            ("Customer PO", "Bon de commande", po),
            ("Terms", "Conditions", v["terms"][0]),
            ("Incoterms 2020", "Incoterms 2020", "FCA Halifax"),
            ("Currency", "Devise", cur),
            ("Customer No.", "No de client", "C-US-0318")]
    y0, cw, ch = H - 102, CW / 4, 30
    c.setFillColor(TINT)
    c.rect(M, y0 - 2 * ch, CW, 2 * ch, stroke=0, fill=1)
    for i, (en, fr, val) in enumerate(grid):
        x, y = M + (i % 4) * cw, y0 - (i // 4) * ch
        _bi(c, x + 6, y - 10, en, fr) if en != fr else _t(c, x + 6, y - 10, en, "Helvetica-Bold", 6.5, GRAY)
        _t(c, x + 6, y - 24, val, "Helvetica-Bold", 10)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.rect(M, y0 - 2 * ch, CW, 2 * ch, stroke=1, fill=0)
    c.line(M, y0 - ch, W - M, y0 - ch)
    for k in range(1, 4):
        c.line(M + k * cw, y0, M + k * cw, y0 - 2 * ch)

    # --- parties + shipment ---------------------------------------------------------------------
    y = y0 - 2 * ch - 18
    ship = mf.ship_lines(d)
    blocks = [(("Sold to", "Vendu à"), d["bill_to"])]
    if ship:
        blocks.append((("Ship to / Consignee", "Destinataire"), ship))
    cert = f"CFIA-EX-{rng.randint(260000, 269999)}"
    shipment = [("Carrier", "Day & Ross (reefer)"),
                ("Bill of lading", f"DR-{rng.randint(7100000, 7199999)}"),
                ("Port of exit", "Woodstock NB"),
                ("CFIA export cert.", cert),
                ("Temp. control", "0 to 4 °C (32 to 39 °F)"),
                ("Country of origin", "Canada")]
    bw = (CW - 20) / 3
    for j, ((en, fr), lines) in enumerate(blocks):
        x = M + j * (bw + 10)
        _bi(c, x, y, en, fr, size=7)
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.8)
        c.line(x, y - 4, x + bw, y - 4)
        for i, ln in enumerate(lines):
            _t(c, x, y - 16 - i * 10.5, ln, "Helvetica-Bold" if i == 0 else "Helvetica", 8.3)
    sx = M + len(blocks) * (bw + 10)
    sw = W - M - sx
    _bi(c, sx, y, "Shipment", "Expédition", size=7)
    c.line(sx, y - 4, sx + sw, y - 4)
    for i, (k, val) in enumerate(shipment):
        _t(c, sx, y - 16 - i * 10.5, k, "Helvetica-Bold", 7, GRAY)
        _t(c, sx + 74, y - 16 - i * 10.5, val, size=7.5)
    depth = max(max(len(b[1]) for b in blocks), len(shipment))
    pen.y = y - 16 - depth * 10.5 - 14
    if d["service_period"]:
        _bi(c, M, pen.y, "Service period", "Période de service", size=7.5)
        _t(c, M + 150, pen.y, d["service_period"], "Helvetica-Bold", 8.5)
        pen.y -= 14

    # --- line items -----------------------------------------------------------------------------
    pen.y = _table_header(c, pen.y)
    in_table[0] = True
    for l in d["lines"]:
        desc = simpleSplit(l["desc"], "Helvetica", 8.5, COLS[1][2] - 8) or [""]
        rh = 9 + 10.5 * len(desc) + 9
        pen.need(rh + 2)
        y = pen.y - 11
        x = M
        cells = [l["sku"], None, "CA", mf.qty_s(l["qty"]), l["unit"],
                 mf.num(l["price"], 4 if l["price"] < 1 else 2), mf.num(l["amount"])]
        for val, (_, _, w, a) in zip(cells, COLS):
            if val is None:
                for i, ln in enumerate(desc):
                    _t(c, x + 4, y - i * 10.5, ln, size=8.5)
                _t(c, x + 4, y - len(desc) * 10.5, f"HS {HS.get(l['sku'], '0302.89')}", size=6.5, color=GRAY)
            else:
                tx = {"l": x + 4, "r": x + w - 4, "c": x + w / 2}[a]
                _t(c, tx, y, val, size=8.5, align=a)
            x += w
        pen.y -= rh
        c.setStrokeColor(RULE)
        c.setLineWidth(0.4)
        c.line(M, pen.y, W - M, pen.y)
    in_table[0] = False
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.2)
    c.line(M, pen.y, W - M, pen.y)

    # --- totals (right) + currency / tax statement (left) ----------------------------------------
    labels = {"Subtotal": ("Subtotal", "Sous-total"), "Subtotal (tax incl.)": ("Subtotal, tax incl.", "Sous-total, TTC")}
    trows = mf.totals_rows(d)
    incl = d["tax_mode"] == "inclusive"
    incl_lines = simpleSplit(f"All prices include {d['tax_rate'] * 100:.2f}% sales tax. Tax included: "
                             f"{mf.money(d['tax'], cur)}", "Helvetica-Oblique", 7, 230) if incl else []
    pen.need(22 * len(trows) + 10 * len(incl_lines) + 20)
    top = pen.y - 6
    tx = W - M - 236
    y = top
    for lab, val, bold in trows:
        if bold:
            c.setFillColor(NAVY)
            c.rect(tx, y - 24, 236, 24, stroke=0, fill=1)
            if lab == "TOTAL DUE":
                _t(c, tx + 8, y - 11, "TOTAL DUE", "Helvetica-Bold", 9, colors.white)
                _t(c, tx + 8, y - 20, f"Montant dû ({cur})", "Helvetica-Oblique", 7, colors.white)
            else:
                _t(c, tx + 8, y - 15.5, lab, "Helvetica-Bold", 9, colors.white)
            _t(c, W - M - 8, y - 16, val, "Helvetica-Bold", 12, colors.white, "r")
            y -= 24
        else:
            en, fr = labels.get(lab, (lab, "Taxe de vente" if lab.startswith("Sales Tax") else ""))
            if fr:
                _bi(c, tx + 8, y - 13, en, fr, size=7.5)
            else:
                _t(c, tx + 8, y - 13, lab, "Helvetica-Bold", 7.5, GRAY)
            _t(c, W - M - 8, y - 13, val, size=9.5, align="r")
            c.setStrokeColor(RULE)
            c.setLineWidth(0.4)
            c.line(tx, y - 19, W - M, y - 19)
            y -= 19
    for ln in incl_lines:
        _t(c, W - M, y - 9, ln, "Helvetica-Oblique", 7, align="r")
        y -= 9
    left = (["Amounts in Canadian dollars (CAD).", "Montants exprimés en dollars canadiens (CAD)."] if cur == "CAD"
            else [f"Amounts in US dollars ({cur}).", f"Montants exprimés en dollars américains ({cur})."])
    if d["tax_mode"] == "none":
        left += ["", "Zero-rated export: GST/HST not charged", "(Excise Tax Act, Sch. VI, Part V).",
                 "Exportation détaxée : TPS/TVH non perçue."]
    for i, ln in enumerate(left):
        _t(c, M, top - 12 - i * 9.5, ln, "Helvetica-Bold" if i == 0 else "Helvetica", 7.5,
           INK if i == 0 else GRAY)
    pen.y = min(y, top - 12 - len(left) * 9.5) - 12

    # --- notes ----------------------------------------------------------------------------------
    for n in d["notes"]:
        lines = simpleSplit(n, "Helvetica-Bold", 8.5, CW)
        pen.need(len(lines) * 11 + 6)
        for ln in lines:
            _t(c, M, pen.y - 9, ln, "Helvetica-Bold", 8.5)
            pen.y -= 11
        pen.y -= 4

    # --- declaration + payment instructions (side by side) --------------------------------------
    pen.need(96)
    y = pen.y - 4
    hw = (CW - 16) / 2
    _bi(c, M, y - 8, "Declaration", "Déclaration", size=7)
    decl = simpleSplit("We certify that this invoice is true and correct, that the goods described are of Canadian "
                       "origin, and that they were inspected and certified for export by the Canadian Food "
                       "Inspection Agency.", "Helvetica", 7, hw)
    for i, ln in enumerate(decl):
        _t(c, M, y - 19 - i * 8.5, ln, size=7, color=GRAY)
    sy = y - 19 - len(decl) * 8.5 - 22
    _t(c, M + 8, sy + 4, "D. MacIsaac", "another", 20, colors.HexColor("#1F3B8C"))
    c.setStrokeColor(INK)
    c.setLineWidth(0.5)
    c.line(M, sy, M + 200, sy)
    _t(c, M, sy - 9, "Authorized signature / Signature autorisée  -  Export Manager", size=6.5, color=GRAY)

    px = M + hw + 16
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    c.rect(px, y - 74, hw, 74, stroke=1, fill=0)
    _bi(c, px + 6, y - 11, "Payment instructions", "Instructions de paiement", size=7)
    pay = [f"Beneficiary: {v['name']}"] + mf.remit_lines(d)
    for i, ln in enumerate(pay):
        _t(c, px + 6, y - 24 - i * 10, ln, size=7.6)
    _t(c, px + 6, y - 24 - len(pay) * 10 - 1, "Overdue accounts bear interest at 2% per month (26.82% per annum).",
       "Helvetica-Oblique", 6.3, GRAY)
    pen.y = min(sy - 12, y - 74) - 14

    # --- remittance advice ------------------------------------------------------------------------
    rh = 58
    pen.need(rh + 14)
    y = pen.y
    c.setDash(2, 2)
    c.setStrokeColor(GRAY)
    c.setLineWidth(0.6)
    c.rect(M, y - rh, CW, rh, stroke=1, fill=0)
    c.setDash()
    _bi(c, M + 6, y - 11, "REMITTANCE ADVICE - return with payment", "AVIS DE PAIEMENT - à joindre au paiement",
        size=7)
    stub = [("Invoice No.", "No de facture", d["inv_no"] if show_no else ""),
            ("Customer No.", "No de client", "C-US-0318"),
            ("Amount due", "Montant dû", mf.money(d["total"], cur) if "total" not in d["hide"] else ""),
            ("Amount paid", "Montant payé", "C$ ________________")]
    sw = CW / 4
    for i, (en, fr, val) in enumerate(stub):
        x = M + 6 + i * sw
        _bi(c, x, y - 28, en, fr, size=6.3)
        _t(c, x, y - 44, val, "Helvetica-Bold", 9.5)
    pen.y -= rh + 6
