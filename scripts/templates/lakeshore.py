"""Lakeshore Meats & Provisions (V007): line-printer invoice on continuous green-bar stock.

Everything is set on a fixed character grid (Courier 8.5 pt, 6 lines per inch) the way an impact
printer driven by a distributor mainframe would print it. Tractor-feed strips on both edges.
"""
import sys
import textwrap
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_fixtures as mf  # noqa: E402
from reportlab.lib import colors  # noqa: E402

W, H = mf.W, mf.H
FS, LH = 8.5, 12.0           # font size, line pitch (6 lpi)
CW = FS * 0.6                # Courier advance width
X0 = 52                      # first print column
TOP = H - 46                 # baseline of line 0
NLINES = int((TOP - 44) / LH)
INK = colors.HexColor("#1E1E1E")
BAR = colors.HexColor("#DCEBDD")
USDA_EST = "EST. 2177"

# Typical piece / package weight per item, used for the PCS column on catch-weight lines.
PIECE_LB = {"10442": 6.0, "10443": 6.0, "10457": 3.5, "20118": 10.0, "20131": 5.0, "30210": 11.0,
            "30244": 8.5, "40102": 2.0, "60022": 1.0, "70300": 3.0, "10480": 14.0, "20160": 3.5}

# Table layout in characters: (header, width, align)
COLS = [("ITEM#", 6, "l"), ("DESCRIPTION", 34, "l"), ("LOT", 5, "l"), ("ORD", 7, "r"), ("SHIP", 7, "r"),
        ("", 1, "l"), ("U/M", 3, "l"), ("PCS", 4, "r"), ("PRICE", 9, "r"), ("EXTENSION", 11, "r")]
RW = 96  # report width in characters (sum of COLS widths + separators)


def _ctr(s):
    return zlib.crc32(s.encode())


class Printer:
    def __init__(self, c, d, total_pages):
        self.c, self.d, self.total = c, d, total_pages
        self.page, self.line = 1, 0
        self.paper()

    # -- paper ----------------------------------------------------------------------------
    def paper(self):
        c = self.c
        c.setFillColor(colors.HexColor("#FBFCF8"))
        c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setFillColor(BAR)
        for k in range(0, NLINES + 3, 6):          # bands of three lines, alternating
            c.rect(40, TOP - (k + 2) * LH - 3.5, W - 80, 3 * LH, stroke=0, fill=1)
        c.setStrokeColor(colors.HexColor("#C9CFC4"))
        c.setLineWidth(0.4)
        c.setDash(2, 2)
        for x in (36, W - 36):                     # tractor-strip perforations + sprocket holes
            c.line(x, 0, x, H)
        c.setDash()
        c.setFillColor(colors.white)
        y = H - 18
        while y > 0:
            for x in (18, W - 18):
                c.circle(x, y, 5, stroke=1, fill=1)
            y -= 36
        c.setFillColor(INK)

    # -- printing on the grid -------------------------------------------------------------
    def y(self, line=None):
        return TOP - (self.line if line is None else line) * LH

    def put(self, col, s, bold=False, size=FS, right=False):
        self.c.setFont("Courier-Bold" if bold else "Courier", size)
        self.c.setFillColor(INK)
        x = X0 + col * CW
        if right:
            self.c.drawRightString(x, self.y(), s)
        else:
            self.c.drawString(x, self.y(), s)

    def nl(self, n=1):
        self.line += n

    def rule(self, ch="-", n=RW):
        self.put(0, ch * n)
        self.nl()

    def left(self):
        return NLINES - self.line

    def footer(self, more):
        save = self.line
        self.line = NLINES + 1
        if more:
            self.put(30, "*** CONTINUED ON NEXT PAGE ***", bold=True)
        self.put(RW, f"PAGE {self.page} OF {self.total}", right=True)
        self.line = save

    def new_page(self):
        self.footer(more=True)
        self.c.showPage()
        self.page += 1
        self.line = 0
        self.paper()


def fmt_row(cells):
    out, col = [], 0
    for (h, w, a), s in zip(COLS, cells):
        out.append((col, s.rjust(w) if a == "r" else s.ljust(w)))
        col += w + 1
    return "".join(s + " " for _, s in out).rstrip()


def price_s(p):
    return mf.num(p, 4 if abs(p) < 1 else 2)


def render(c, d, total_pages):
    v = d["v"]
    hide = d["hide"]
    p = Printer(c, d, total_pages)
    title = (d["title"] or "INVOICE").upper()
    inv_no = d["inv_no"] if "invoice_no" not in hide and d["inv_no"] else ""
    show_date = "date" not in hide and d["inv_date"]
    cust_no = f"{_ctr(d['bill_to'][0]) % 900000 + 100000:06d}"
    order_no = f"SO{_ctr('order' + (d['inv_no'] or d['bill_to'][0])) % 900000 + 100000}"  # unrelated to inv no
    route = {"FUL": "07/03", "WKP": "07/11", "EVN": "12/02", "LSQ": "09/06", "OKP": "15/04"}.get(d["loc"], "07/01")

    # ---- page-1 heading -----------------------------------------------------------------
    p.put(0, v["name"], bold=True, size=15)
    p.put(62, " ".join(title), bold=True, size=13)
    p.nl(2)
    hdr_left = [a.upper() for a in v["addr"]] + [
        f"TEL {v['phone']}   {v['email'].upper()}",
        f"FED TAX ID {v['tax_id']}   USDA {USDA_EST}"]
    hdr_right = []
    if inv_no:
        hdr_right.append(("INVOICE NO.", inv_no))
    if show_date:
        hdr_right.append(("INVOICE DATE", mf.fdate(d["inv_date"], v["datefmt"])))
        if d["due"] and v["terms"][1]:
            hdr_right.append(("DUE DATE", mf.fdate(d["due"], v["datefmt"])))
    hdr_right.append(("PAGE", f"{p.page} OF {total_pages}"))
    for i in range(max(len(hdr_left), len(hdr_right))):
        if i < len(hdr_left):
            p.put(0, hdr_left[i])
        if i < len(hdr_right):
            p.put(62, f"{hdr_right[i][0]:<13}{hdr_right[i][1]}", bold=i == 0 and bool(inv_no))
        p.nl()
    p.rule("=")
    p.put(0, "CUSTOMER NO  ORDER NO   CUST P.O. NUMBER   TERMS     SALESMAN        ROUTE/STOP  SHIP VIA", bold=True)
    p.nl()
    po = d["po"] if d["po"] and "po" not in hide else ""
    p.put(0, f"{cust_no:<13}{order_no:<11}{po:<19}{v['terms'][0].upper():<10}{'14 PRZYBYLSKI':<16}"
             f"{route:<12}OUR TRUCK")
    p.nl()
    if d["service_period"]:
        p.put(0, f"SERVICE PERIOD: {d['service_period']}")
        p.nl()
    p.rule("=")
    ship = mf.ship_lines(d)
    p.put(0, "SOLD TO:", bold=True)
    if ship:
        p.put(48, "SHIP TO:", bold=True)
    p.nl()
    for i in range(max(len(d["bill_to"]), len(ship))):
        if i < len(d["bill_to"]):
            p.put(3, d["bill_to"][i].upper())
        if i < len(ship):
            p.put(51, ship[i].upper())
        p.nl()
    p.nl()

    # ---- line items -----------------------------------------------------------------------
    def table_header():
        p.rule("-")
        p.put(0, fmt_row([h for h, _, _ in COLS]), bold=True)
        p.nl()
        p.rule("-")

    def cont_header():
        p.put(0, v["name"].upper(), bold=True)
        p.put(RW, f"{title} {inv_no}".strip() + "  (CONTINUED)", right=True)
        p.nl()
        p.put(0, f"CUSTOMER NO {cust_no}   SOLD TO {d['bill_to'][0].upper()}")
        if show_date:
            p.put(RW, f"INVOICE DATE {mf.fdate(d['inv_date'], v['datefmt'])}", right=True)
        p.nl(2)

    table_header()
    short, pcs_total, lbs_total = False, 0, 0.0
    for l in d["lines"]:
        ordered = l.get("ordered", l["qty"])
        flag = "S" if ordered != l["qty"] else ""
        short = short or bool(flag)
        if l["unit"] == "lb":
            pcs = max(1, round(l["qty"] / PIECE_LB.get(l["sku"], 5.0)))
            lbs_total += l["qty"]
        else:
            pcs = max(1, int(abs(l["qty"])))
        pcs_total += pcs
        lot = f"{_ctr(l['sku'] + (d['inv_no'] or '')) % 90000 + 10000}"
        desc = textwrap.wrap(l["desc"].upper(), COLS[1][1]) or [""]
        cells = [l["sku"], desc[0], lot, mf.qty_s(ordered), mf.qty_s(l["qty"]), flag, l["unit"].upper(),
                 str(pcs), price_s(l["price"]), mf.num(l["amount"])]
        if p.left() < len(desc):
            p.new_page()
            cont_header()
            table_header()
        p.put(0, fmt_row(cells))
        p.nl()
        for extra in desc[1:]:
            p.put(COLS[0][1] + 1, extra)
            p.nl()

    # ---- totals (last page only) ------------------------------------------------------------
    rows = mf.totals_rows(d)
    tail = 4 + len(rows) + (1 if d["tax_mode"] == "inclusive" else 0) + (1 if short else 0)
    if p.left() < tail:
        p.new_page()
        cont_header()
    p.rule("-")
    p.put(0, f"TOTAL PCS {pcs_total:>5}" + (f"    TOTAL LBS {mf.num(lbs_total, 1):>9}" if lbs_total else ""))
    p.put(42, f"LINES {len(d['lines']):>3}")
    for lab, val, big in rows:
        p.put(RW - 14, lab.upper(), bold=big, right=True)
        p.put(RW, val, bold=big, right=True)
        p.nl()
    if d["tax_mode"] == "inclusive":
        p.put(30, f"ALL PRICES INCLUDE {d['tax_rate'] * 100:.2f}% SALES TAX. TAX INCLUDED: "
                  f"{mf.money(d['tax'], d['currency'])}")
        p.nl()
    if short:
        p.put(0, "S = SHORT SHIPPED. BALANCE REMAINS ON OPEN ORDER - NOT BILLED.")
        p.nl()
    p.rule("=")

    # ---- certification, remittance, receiving ---------------------------------------------
    block = [
        ("PRODUCT TEMP AT DELIVERY: 34 F   TRAILER TEMP: 33 F   KEEP REFRIGERATED 28-40 F", True),
        (f"INSPECTED AND PASSED BY U.S. DEPARTMENT OF AGRICULTURE  {USDA_EST}", False),
        ("CLAIMS FOR SHORTAGE, DAMAGE OR TEMPERATURE MUST BE NOTED AT TIME OF DELIVERY.", False),
        ("", False),
        (f"REMIT TO: {v['name'].upper()}, {', '.join(a.upper() for a in v['addr'])}", True),
    ] + [("          " + r.upper(), False) for r in mf.remit_lines(d)] + [
        ("", False),
        ("RECEIVED BY ______________________   DRIVER 22   CHECKED IN BY ____________", False),
    ]
    for s, b in block:
        if p.left() < 1:
            p.new_page()
            cont_header()
        if s:
            p.put(0, s, bold=b)
        p.nl()
    for note in d["notes"]:
        wrapped = textwrap.wrap(note, RW) or [""]
        if p.left() < len(wrapped) + 1:
            p.new_page()
            cont_header()
        p.nl()
        for s in wrapped:
            p.put(0, s)
            p.nl()
    p.footer(more=False)
