"""Generate InvoiceDesk synthetic fixtures.

Outputs (all derived from the SCENARIOS list at the bottom, so they never disagree):
  data/seed.json              procurement system: vendors, POs, goods receipts, invoice ledger, policy
  fixtures/invoices/*         66 invoice files (digital, scanned, fax, phone photo, handwritten, broken...)
  fixtures/manifest.json      answer key: kind, quality, scenario, expected decision, ground-truth fields
  fixtures/MANIFEST.md        the same, human-readable

Run:  python scripts/make_fixtures.py
Deterministic: fixed seeds, so re-running produces the same files.
"""
import io
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "fixtures" / "invoices"
FONT_DIR = Path(__file__).resolve().parent / "fonts"
TODAY = date(2026, 10, 9)

HANDS = {
    "kalam": "Kalam-Regular.ttf",
    "apple": "HomemadeApple-Regular.ttf",
    "nothing": "NothingYouCouldDo.ttf",
    "reenie": "ReenieBeanie.ttf",
    "another": "JustAnotherHand-Regular.ttf",
    "shadows": "ShadowsIntoLight.ttf",
}
for _name, _file in HANDS.items():
    pdfmetrics.registerFont(TTFont(_name, str(FONT_DIR / _file)))

# --------------------------------------------------------------------------------------------
# Buyer, vendors, catalogs
# --------------------------------------------------------------------------------------------
BUYER = ["Copperleaf Restaurant Group", "Attn: Accounts Payable", "1200 W Fulton Market, Suite 400",
         "Chicago, IL 60607"]
LOCATIONS = {
    "FUL": ["Copperleaf Fulton Market", "1210 W Fulton Market", "Chicago, IL 60607"],
    "WKP": ["Copperleaf Wicker Park", "1544 N Milwaukee Ave", "Chicago, IL 60622"],
    "EVN": ["Copperleaf Evanston", "812 Church St", "Evanston, IL 60201"],
    "LSQ": ["Copperleaf Logan Square", "2630 N Kedzie Ave", "Chicago, IL 60647"],
    "OKP": ["Copperleaf Oak Park", "1035 Lake St", "Oak Park, IL 60301"],
}
TAX_RATE = 0.1025  # Chicago combined sales tax on taxable supplies

VENDORS = {
    "V001": dict(name="GreenLeaf Produce Co.", aliases=["Greenleaf Produce Company", "GreenLeaf Produce"],
                 tax_id="36-4418207", addr=["2400 S Blue Island Ave", "Chicago, IL 60608"],
                 phone="(312) 555-0141", email="billing@greenleafproduce.com",
                 bank=dict(bank="Wintrust Bank", routing="071925334", account="300458817"),
                 status="approved", category="goods", taxable=False, design="greenleaf", template="classic", terms=("Net 15", 15),
                 accent="#2F6B3B", datefmt="%b %d, %Y"),
    "V002": dict(name="PackRight Packaging LLC", aliases=["PackRight Packaging", "Pack Right Packaging LLC"],
                 tax_id="27-3390514", addr=["7850 W 47th St", "Lyons, IL 60534"],
                 phone="(708) 555-0177", email="ar@packrightpkg.com",
                 bank=dict(bank="BMO Bank N.A.", routing="071904779", account="5520147736"),
                 status="approved", category="goods", taxable=True, design="packright", template="qb", terms=("Net 30", 30),
                 accent="#1D7A74", datefmt="%m/%d/%Y"),
    "V003": dict(name="Sparkle Commercial Cleaning Inc.", aliases=["Sparkle Commercial Cleaning", "Sparkle Cleaning"],
                 tax_id="81-2204613", addr=["611 W Roosevelt Rd, Unit 3", "Chicago, IL 60607"],
                 phone="(312) 555-0118", email="accounts@sparklecc.com",
                 bank=dict(bank="Fifth Third Bank", routing="071923903", account="7730018842"),
                 status="approved", category="services", taxable=False, design="sparkle", template="letter", terms=("Net 30", 30),
                 accent="#6B3FA0", datefmt="%B %d, %Y"),
    "V004": dict(name="Northgate Kitchen Equipment Rentals", aliases=["Northgate Equipment Rentals", "Northgate KER"],
                 tax_id="46-1187320", addr=["3300 N Elston Ave", "Chicago, IL 60618"],
                 phone="(773) 555-0190", email="invoices@northgate-ker.com",
                 bank=dict(bank="PNC Bank", routing="071921891", account="4410276650"),
                 status="approved", category="services", taxable=False, design="northgate", template="modern", terms=("Net 30", 30),
                 accent="#C2410C", datefmt="%d %b %Y"),
    "V005": dict(name="Bluewave IT Services", aliases=["Bluewave IT", "BlueWave IT Services LLC"],
                 tax_id="83-0912455", addr=["180 N LaSalle St, Floor 12", "Chicago, IL 60601"],
                 phone="(312) 555-0163", email="billing@bluewaveit.com",
                 bank=dict(bank="JPMorgan Chase Bank", routing="071000999", account="882014550"),
                 status="approved", category="services", taxable=False, design="bluewave", template="letter", terms=("Net 15", 15),
                 accent="#1E4FD8", datefmt="%Y-%m-%d"),
    "V006": dict(name="Rapid Linen Supply", aliases=["Rapid Linen"], tax_id="36-3005871",
                 addr=["940 W Cermak Rd", "Chicago, IL 60608"], phone="(312) 555-0102",
                 email="ar@rapidlinen.com", bank=dict(bank="Byline Bank", routing="071900111", account="1100293348"),
                 status="blocked", block_reason="Contract terminated 2026-08-31 after repeated billing disputes",
                 category="services", taxable=False, design="rapidlinen", template="qb", terms=("Net 30", 30), accent="#8B1E3F",
                 datefmt="%m/%d/%Y"),
    "V007": dict(name="Lakeshore Meats & Provisions", aliases=["Lakeshore Meats", "Lakeshore Meat & Provision Co"],
                 tax_id="36-2981144", addr=["1155 W Randolph St", "Chicago, IL 60607"],
                 phone="(312) 555-0129", email="ar@lakeshoremeats.com",
                 bank=dict(bank="Old National Bank", routing="086300999", account="2209814451"),
                 status="approved", category="goods", taxable=False, design="lakeshore", template="distrib", terms=("Net 21", 21),
                 accent="#7F1D1D", datefmt="%m/%d/%y"),
    "V008": dict(name="Midwest Dairy Cooperative", aliases=["Midwest Dairy Co-op", "Midwest Dairy"],
                 tax_id="39-0447812", addr=["N2190 County Rd K", "Elkhorn, WI 53121"],
                 phone="(262) 555-0155", email="routes@midwestdairy.coop",
                 bank=dict(bank="Associated Bank", routing="075900999", account="6630192207"),
                 status="approved", category="goods", taxable=False, template="ticket", terms=("Net 14", 14),
                 accent="#000000", datefmt="%m/%d/%Y"),
    "V009": dict(name="Great Lakes Beverage Distributors", aliases=["Great Lakes Beverage", "GLBD"],
                 tax_id="36-4790031", addr=["4501 W 47th St", "Chicago, IL 60632"],
                 phone="(773) 555-0136", email="credit@glbd.com",
                 bank=dict(bank="U.S. Bank", routing="071904999", account="1530077742"),
                 status="approved", category="goods", taxable=False, design="glbd", template="distrib", terms=("Net 30", 30),
                 accent="#0F4C81", datefmt="%m/%d/%Y"),
    "V010": dict(name="Tony's Handyman & Repair", aliases=["Tonys Handyman", "Tony's Repair"],
                 tax_id="47-5512908", addr=["2217 W Belmont Ave", "Chicago, IL 60618"],
                 phone="(773) 555-0184", email="tonysrepair@mailbox.com",
                 bank=dict(bank="Chase", routing="071000999", account="6011842239"),
                 status="approved", category="services", taxable=False, template="hand", terms=("Due on receipt", 0),
                 accent="#1F2A6B", datefmt="%m/%d/%y"),
    "V011": dict(name="Prairie Pest Control", aliases=["Prairie Pest", "Prairie Pest Control LLC"],
                 tax_id="20-8834716", addr=["5150 S Pulaski Rd", "Chicago, IL 60632"],
                 phone="(773) 555-0122", email="office@prairiepest.com",
                 bank=dict(bank="First Midwest Bank", routing="071901604", account="3381109924"),
                 status="approved", category="services", taxable=False, design="prairie", template="modern", terms=("Net 30", 30),
                 accent="#4D7C0F", datefmt="%b %d, %Y"),
    "V012": dict(name="Maritime Seafood Exporters Ltd.", aliases=["Maritime Seafood Exporters", "Maritime Seafood"],
                 tax_id="BN 81442 7730 RT0001", addr=["88 Lower Water St", "Halifax, NS B3J 1S5, Canada"],
                 phone="+1 (902) 555-0147", email="ar@maritimeseafood.ca",
                 bank=dict(bank="Royal Bank of Canada", routing="00003-003", account="1044728"),
                 status="approved", category="goods", taxable=False, design="maritime", template="classic", terms=("Net 30", 30),
                 accent="#0E5A7A", datefmt="%d/%m/%Y"),
}
# Vendor that sends an invoice but is NOT in the vendor master.
UNKNOWN_VENDORS = {
    "X001": dict(name="Harborview Florals", tax_id="88-1029374", addr=["1420 N Wells St", "Chicago, IL 60610"],
                 phone="(312) 555-0199", email="hello@harborviewflorals.com",
                 bank=dict(bank="Chase", routing="071000999", account="7734100982"), category="goods",
                 taxable=False, design="harborview", template="modern", terms=("Due on receipt", 0), accent="#BE185D",
                 datefmt="%B %d, %Y"),
}
ALL_VENDORS = {**VENDORS, **UNKNOWN_VENDORS}

CATALOG = {
    "V001": [("GL-1102", "Roma tomatoes, 25 lb case", "cs", 31.50), ("GL-1140", "Romaine hearts 3ct x 12", "cs", 38.75),
             ("GL-1205", "Yellow onions, 50 lb sack", "bag", 27.40), ("GL-1311", "Hass avocados 48ct", "cs", 62.00),
             ("GL-1420", "Lemons 165ct", "cs", 44.20), ("GL-1502", "Cilantro 30 bunch", "cs", 24.90),
             ("GL-1610", "Russet potatoes 50 lb", "bag", 29.80), ("GL-1733", "Baby spinach 4 lb", "cs", 21.60),
             ("GL-1820", "Red bell peppers 11 lb", "cs", 34.25), ("GL-1905", "Limes 200ct", "cs", 41.10),
             ("GL-2011", "Micro greens mix 2 lb", "cs", 48.00), ("GL-2104", "Peeled garlic 5 lb jar", "ea", 19.95),
             ("GL-2150", "English cucumbers 12ct", "cs", 22.40), ("GL-2203", "Jalapenos 10 lb", "cs", 18.70)],
    "V002": [("KB-08", "Kraft fold-top takeout box #8 (200/cs)", "cs", 46.80),
             ("CUP-16", "16 oz PET cold cup (1000/cs)", "cs", 88.40),
             ("LID-16", "Flat lid for 16 oz cup (1000/cs)", "cs", 41.25),
             ("NAP-D", "Dinner napkin 2-ply kraft (3000/cs)", "cs", 52.60),
             ("GLV-L", "Nitrile gloves black, size L (1000/cs)", "cs", 74.90),
             ("BAG-12", "Paper SOS bag #12 (500/bdl)", "bdl", 36.15),
             ("FOIL-18", "Aluminum foil roll 18in x 500ft", "ea", 32.70),
             ("CLAM-9", "Molded fiber clamshell 9x9 (200/cs)", "cs", 58.30),
             ("STR-W", "Wrapped paper straws (3200/cs)", "cs", 63.90),
             ("TISS-12", "Deli tissue sheets 12x12 (5000/cs)", "cs", 27.80),
             ("CUT-K", "Compostable cutlery kit (250/cs)", "cs", 44.60),
             ("SOUP-12", "Paper soup cup 12 oz w/ lid (500/cs)", "cs", 71.20)],
    "V003": [("SVC-HD", "Kitchen hood degrease (quarterly)", "ea", 640.00),
             ("SVC-FW", "Floor strip & wax, dining room", "ea", 425.00),
             ("SVC-WIN", "Exterior window cleaning", "ea", 180.00),
             ("SUP-CH", "Chemical & consumables restock", "ea", 136.50),
             ("SVC-GT", "Grease trap pump-out", "ea", 295.00),
             ("SVC-UP", "Upholstery steam clean, booths", "ea", 360.00)],
    "V007": [("10442", "Beef tenderloin PSMO, Choice", "lb", 18.95), ("10457", "Beef short rib boneless, Choice", "lb", 12.40),
             ("20118", "Chicken thigh boneless skinless", "lb", 3.65), ("20131", "Chicken breast airline 8 oz", "lb", 5.80),
             ("30210", "Pork belly skin-off", "lb", 5.25), ("30244", "Pork shoulder bone-in", "lb", 2.95),
             ("40102", "Lamb rack frenched 8-bone", "lb", 21.30), ("50077", "Bacon thick-cut applewood 15 lb", "cs", 68.50),
             ("50091", "Italian sausage links 10 lb", "cs", 42.75), ("60015", "Ground beef 80/20 10 lb", "cs", 48.90),
             ("60022", "Duck breast, Magret", "lb", 14.60), ("70300", "Salmon fillet, skin-on", "lb", 11.85),
             ("10480", "Ribeye lip-on, Choice", "lb", 13.75), ("20160", "Whole chicken 3.5 lb", "lb", 2.45)],
    "V008": [("WM-G", "Whole milk 1 gal", "gal", 4.15), ("HC-Q", "Heavy cream 40% qt", "qt", 5.60),
             ("BTR-36", "Butter unsalted 36 x 1 lb", "cs", 142.20), ("EGG-15", "Large eggs 15 dz", "cs", 46.50),
             ("YOG-32", "Greek yogurt plain 32 oz", "ea", 6.85), ("PRM-W", "Parmesan wedge", "lb", 15.90),
             ("MOZ-5", "Fresh mozzarella 5 lb", "ea", 27.40), ("SC-5", "Sour cream 5 lb", "ea", 11.30)],
    "V009": [("KEG-IPA", "House IPA 1/2 bbl keg", "keg", 189.00), ("KEG-PIL", "Pilsner 1/6 bbl keg", "keg", 92.00),
             ("CS-SPK", "Sparkling water 24 x 500 ml", "cs", 21.60), ("CS-COLA", "Cola 24 x 12 oz glass", "cs", 31.20),
             ("CS-GB", "Ginger beer 24 x 12 oz", "cs", 33.90), ("WN-PG", "Pinot grigio 12 x 750 ml", "cs", 118.80),
             ("WN-CS", "Cabernet sauvignon 12 x 750 ml", "cs", 164.40), ("SP-VOD", "Vodka 6 x 1 L", "cs", 132.00),
             ("BIB-5", "Soda syrup bag-in-box 5 gal", "ea", 86.50), ("CS-TON", "Tonic water 24 x 200 ml", "cs", 26.40)],
    "V011": [("PC-RS", "Rodent bait station replacement", "ea", 18.50), ("PC-FL", "Fly light unit service", "ea", 65.00),
             ("PC-INS", "Follow-up inspection", "ea", 95.00), ("PC-DR", "Drain fly treatment", "ea", 120.00)],
}

# --------------------------------------------------------------------------------------------
# Procurement-system state (written to data/seed.json)
# --------------------------------------------------------------------------------------------
POS, RECEIPTS, LEDGER = {}, [], []
_po_seq = iter(range(1101, 2000))


def r2(x):
    return float(round(x + 1e-9, 2))


def L(sku, desc, unit, price, qty):
    return dict(sku=sku, desc=desc, unit=unit, price=price, qty=qty)


def from_catalog(vid, picks):
    """picks: list of (catalog_index, qty)."""
    return [L(*CATALOG[vid][i], qty) for i, qty in picks]


def make_po(vid, lines, *, po=None, loc="FUL", status="open", kind="standard", total=None,
            opening_billed=0.0, created=None, received=None):
    """Create a PO (and, for goods vendors, its goods receipt). received: {sku: qty} or None for full."""
    po = po or f"PO-{next(_po_seq)}"
    po_lines = [dict(sku=l["sku"], desc=l["desc"], unit=l["unit"], qty=l["qty"], unit_price=l["price"]) for l in lines]
    POS[po] = dict(po_number=po, vendor_id=vid, location=loc, status=status, type=kind,
                   created=str(created or TODAY - timedelta(days=30)), lines=po_lines,
                   total=r2(total if total is not None else sum(l["qty"] * l["price"] for l in lines)),
                   opening_billed=opening_billed)
    if VENDORS.get(vid, {}).get("category") == "goods" and kind == "standard":
        rec_date = str((created or TODAY - timedelta(days=30)) + timedelta(days=5))
        for l in lines:
            q = l["qty"] if received is None else received.get(l["sku"], l["qty"])
            RECEIPTS.append(dict(po_number=po, sku=l["sku"], qty_received=q, received_date=rec_date))
    return po


def ledger_add(vid, inv_no, inv_date, po, lines, status="paid", service_period=None):
    sub = r2(sum(r2(l["qty"] * l["price"]) for l in lines))
    LEDGER.append(dict(vendor_id=vid, invoice_number=inv_no, invoice_date=str(inv_date), po_number=po,
                       subtotal=sub, tax=0.0, total=sub, status=status, service_period=service_period,
                       lines=[dict(desc=l["desc"], qty=l["qty"], unit_price=l["price"]) for l in lines]))


# --------------------------------------------------------------------------------------------
# Invoice document model
# --------------------------------------------------------------------------------------------
def doc(vid, lines, *, inv_no, inv_date, po=None, loc="FUL", title=None, tax_mode=None, currency="USD",
        vendor_over=None, bill_to=None, notes=(), service_period=None, hide=(), total_delta=0.0,
        tax_rate_charged=None, fees=(), doc_type="invoice", printed_po=None, extra=None):
    """Build a renderable document + its ground truth.

    tax_mode: None -> vendor default ('separate' if taxable else 'none'); 'inclusive'; 'none'.
    hide: subset of {'invoice_no','date','total','ship_to','po'} -> not printed.
    total_delta: printed total differs from the true sum (arithmetic error on the document).
    fees: extra lines not on the PO (freight, deposits, discounts) -> appended to lines.
    """
    v = dict(ALL_VENDORS[vid])
    v.update(vendor_over or {})
    lines = [dict(l) for l in lines] + [dict(f) for f in fees]
    if tax_mode is None:
        tax_mode = "separate" if v.get("taxable") else "none"
    rate = TAX_RATE if tax_mode in ("separate", "inclusive") else 0.0
    if tax_mode == "inclusive":
        for l in lines:
            l["price"] = r2(l["price"] * (1 + TAX_RATE))
    for l in lines:
        l["amount"] = l.get("amount_override", r2(l["qty"] * l["price"]))
    subtotal = r2(sum(l["amount"] for l in lines))
    if tax_mode == "separate":
        tax = r2(subtotal * (tax_rate_charged if tax_rate_charged is not None else rate))
        total = r2(subtotal + tax)
    elif tax_mode == "inclusive":
        tax = r2(subtotal - subtotal / (1 + rate))
        total = subtotal
    else:
        tax, total = 0.0, subtotal
    printed_total = r2(total + total_delta)
    due = (inv_date + timedelta(days=v["terms"][1])) if inv_date else None
    d = dict(vid=vid, v=v, lines=lines, inv_no=inv_no, inv_date=inv_date, due=due,
             po=printed_po if printed_po is not None else po, loc=loc, title=title, tax_mode=tax_mode,
             tax_rate=rate, tax_rate_printed=rate, subtotal=subtotal, tax=tax, total=printed_total,
             currency=currency, bill_to=bill_to or BUYER, notes=list(notes), service_period=service_period,
             hide=set(hide), doc_type=doc_type, extra=extra or {})
    d["truth"] = dict(
        document_type=doc_type, vendor_name_printed=v["name"], vendor_id=vid if vid in VENDORS else None,
        vendor_tax_id_printed=None if (v.get("design") is None and v["template"] in ("ticket", "hand")) else v["tax_id"], invoice_number=None if "invoice_no" in d["hide"] else inv_no,
        invoice_date=None if ("date" in d["hide"] or not inv_date) else str(inv_date),
        due_date=None if ("date" in d["hide"] or not due) else str(due),
        po_number_printed=None if ("po" in d["hide"] or not d["po"]) else d["po"],
        currency=currency, bill_to_name=d["bill_to"][0],
        remit_bank_account=v["bank"]["account"], remit_bank_routing=v["bank"]["routing"],
        line_items=[dict(sku=l["sku"], description=l["desc"], qty=l["qty"], unit_price=l["price"],
                         amount=l["amount"]) for l in lines],
        subtotal=subtotal, tax=tax, prices_include_tax=tax_mode == "inclusive",
        total_printed=None if "total" in d["hide"] else printed_total, total_true=total,
        service_period=service_period,
        tax_rate_printed=d["tax_rate_printed"] if tax_mode != "none" else None)
    return d


# --------------------------------------------------------------------------------------------
# Rendering helpers (ReportLab canvas, letter size unless the template says otherwise)
# --------------------------------------------------------------------------------------------
W, H = letter


def money(x, cur="USD"):
    sym = {"USD": "$", "CAD": "C$"}[cur]
    s = f"{sym}{abs(x):,.2f}"
    return f"-{s}" if x < 0 else s


def num(x, dec=2):
    return f"{x:,.{dec}f}"


def qty_s(q):
    return f"{q:,.2f}" if isinstance(q, float) and q != int(q) else f"{int(q):,}"


def fdate(d, fmt):
    return d.strftime(fmt) if d else ""


def hexc(h):
    return colors.HexColor(h)


class Pen:
    """Tracks the y cursor and handles page breaks with a continuation header."""

    def __init__(self, c, d, cont_header, bottom=70, top=None):
        self.c, self.d, self.cont_header, self.bottom = c, d, cont_header, bottom
        self.page, self.y = 1, top or H - 50

    def need(self, h):
        if self.y - h < self.bottom:
            self.c.showPage()
            self.page += 1
            self.y = self.cont_header(self.c, self.d, self.page)
            return True
        return False


def footer_pages(c, d, page, total_pages, font="Helvetica", size=7.5, y=30):
    c.setFont(font, size)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawCentredString(W / 2, y, f"Page {page} of {total_pages}")
    c.setFillColor(colors.black)


def draw_table(pen, x, cols, rows, st, header_cb=None):
    """cols: [(header, width, align)], rows: list of cell lists. Wraps text; repeats header on new page."""
    c = pen.c
    fs, font, hfont = st.get("size", 9), st.get("font", "Helvetica"), st.get("hfont", "Helvetica-Bold")
    pad, lh = st.get("pad", 4), st.get("size", 9) + 2.6
    width = sum(cw for _, cw, _ in cols)

    def header():
        hh = fs + 2 * pad + 2
        if st.get("hfill"):
            c.setFillColor(st["hfill"])
            c.rect(x, pen.y - hh, width, hh, stroke=0, fill=1)
        c.setFillColor(st.get("htext", colors.black))
        c.setFont(hfont, st.get("hsize", fs))
        cx = x
        for h, cw, a in cols:
            ty = pen.y - pad - fs + 1
            if a == "r":
                c.drawRightString(cx + cw - pad, ty, h)
            elif a == "c":
                c.drawCentredString(cx + cw / 2, ty, h)
            else:
                c.drawString(cx + pad, ty, h)
            cx += cw
        if st.get("hline"):
            c.setStrokeColor(st["hline"])
            c.setLineWidth(st.get("hline_w", 0.8))
            c.line(x, pen.y - hh, x + width, pen.y - hh)
        pen.y -= hh
        c.setFillColor(colors.black)

    header()
    for i, row in enumerate(rows):
        wrapped = [simpleSplit(str(cell), font, fs, cw - 2 * pad) or [""] for cell, (_, cw, _) in zip(row, cols)]
        rh = max(len(w) for w in wrapped) * lh + 2 * pad - 2
        if pen.need(rh + 2):
            if header_cb:
                header_cb()
            header()
        if st.get("zebra") and i % 2 == 1:
            c.setFillColor(st["zebra"])
            c.rect(x, pen.y - rh, width, rh, stroke=0, fill=1)
        c.setFillColor(st.get("text", colors.black))
        c.setFont(font, fs)
        cx = x
        for w_lines, (_, cw, a) in zip(wrapped, cols):
            ty = pen.y - pad - fs + 1
            for ln in w_lines:
                if a == "r":
                    c.drawRightString(cx + cw - pad, ty, ln)
                elif a == "c":
                    c.drawCentredString(cx + cw / 2, ty, ln)
                else:
                    c.drawString(cx + pad, ty, ln)
                ty -= lh
            cx += cw
        if st.get("grid"):
            c.setStrokeColor(st.get("gridc", colors.HexColor("#BBBBBB")))
            c.setLineWidth(0.5)
            c.line(x, pen.y - rh, x + width, pen.y - rh)
        pen.y -= rh
    if st.get("box"):
        pass
    return pen.y


def totals_rows(d):
    cur = d["currency"]
    rows = []
    if d["tax_mode"] == "separate":
        rows.append(("Subtotal", money(d["subtotal"], cur), False))
        rows.append((f"Sales Tax ({d['tax_rate_printed'] * 100:.2f}%)", money(d["tax"], cur), False))
    elif d["tax_mode"] == "inclusive":
        rows.append(("Subtotal (tax incl.)", money(d["subtotal"], cur), False))
    else:
        rows.append(("Subtotal", money(d["subtotal"], cur), False))
    if "total" not in d["hide"]:
        rows.append((d["extra"].get("total_label", "TOTAL DUE"), money(d["total"], cur), True))
    return rows


def draw_totals(pen, x_lab, x_val, d, font="Helvetica", bold="Helvetica-Bold", size=10, rule=None):
    c = pen.c
    rows = totals_rows(d)
    pen.need(len(rows) * (size + 7) + 30)
    pen.y -= 6
    for lab, val, b in rows:
        if b and rule:
            c.setStrokeColor(rule)
            c.setLineWidth(1)
            c.line(x_lab - 90, pen.y + 2, x_val, pen.y + 2)
            pen.y -= 4
        c.setFont(bold if b else font, size + (2 if b else 0))
        c.drawRightString(x_lab, pen.y - size, lab)
        c.drawRightString(x_val, pen.y - size, val)
        pen.y -= size + 7
    if d["tax_mode"] == "inclusive":
        c.setFont(font, size - 2)
        c.drawRightString(x_val, pen.y - size + 2,
                          f"All prices include {d['tax_rate'] * 100:.2f}% sales tax. Tax included: {money(d['tax'], d['currency'])}")
        pen.y -= size + 4


def remit_lines(d):
    b = d["v"]["bank"]
    if d["currency"] == "CAD":
        return [f"Bank: {b['bank']}", f"Transit/Institution: {b['routing']}   Account: {b['account']}",
                "SWIFT: ROYCCAT2   Please quote invoice number on remittance."]
    return [f"Bank: {b['bank']}", f"ACH Routing (ABA): {b['routing']}   Account No.: {b['account']}",
            f"Remittance advice to: {d['v']['email']}"]


def meta_pairs(d):
    v = d["v"]
    out = []
    if "invoice_no" not in d["hide"] and d["inv_no"]:
        out.append(("Invoice No.", d["inv_no"]))
    if "date" not in d["hide"] and d["inv_date"]:
        out.append(("Invoice Date", fdate(d["inv_date"], v["datefmt"])))
    if "po" not in d["hide"] and d["po"]:
        out.append(("PO Number", d["po"]))
    out.append(("Terms", v["terms"][0]))
    if "date" not in d["hide"] and d["due"] and v["terms"][1]:
        out.append(("Due Date", fdate(d["due"], v["datefmt"])))
    if d["service_period"]:
        out.append(("Service Period", d["service_period"]))
    return out


def ship_lines(d):
    return [] if "ship_to" in d["hide"] else LOCATIONS[d["loc"]]


def logo(c, x, y, kind, color, text=""):
    c.setFillColor(color)
    c.setStrokeColor(color)
    if kind == "leaf":
        p = c.beginPath()
        p.moveTo(x, y)
        p.curveTo(x + 6, y + 26, x + 30, y + 30, x + 34, y + 30)
        p.curveTo(x + 34, y + 8, x + 18, y - 2, x, y)
        c.drawPath(p, fill=1, stroke=0)
    elif kind == "circle":
        c.circle(x + 15, y + 15, 15, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(x + 15, y + 10, text)
    elif kind == "square":
        c.rect(x, y, 30, 30, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(x + 15, y + 10, text)
    elif kind == "wave":
        c.setLineWidth(3)
        for k in range(3):
            p = c.beginPath()
            p.moveTo(x, y + 8 + k * 8)
            p.curveTo(x + 10, y + 16 + k * 8, x + 20, y + k * 8, x + 32, y + 8 + k * 8)
            c.drawPath(p, fill=0, stroke=1)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)


def notes_block(pen, x, d, font="Helvetica", size=8.5, width=None):
    if not d["notes"]:
        return
    c = pen.c
    width = width or (W - 2 * x)
    pen.y -= 8
    for n in d["notes"]:
        lines = simpleSplit(n, font, size, width)
        pen.need(len(lines) * (size + 3) + 4)
        c.setFont(font, size)
        for ln in lines:
            c.drawString(x, pen.y - size, ln)
            pen.y -= size + 3
        pen.y -= 3


# ---- template: classic (serif, boxed meta, grid table) -------------------------------------
def t_classic(c, d, total_pages):
    v, acc = d["v"], hexc(d["v"]["accent"])
    serif, serif_b = "Times-Roman", "Times-Bold"

    def cont(c, d, page):
        c.setFont(serif_b, 12)
        c.drawString(50, H - 50, v["name"])
        c.setFont(serif, 9)
        c.drawRightString(W - 50, H - 50, f"{d['title'] or 'INVOICE'} {d['inv_no'] or ''} (continued)")
        footer_pages(c, d, page, total_pages, serif)
        return H - 75

    pen = Pen(c, d, cont)
    logo(c, 50, H - 82, "leaf" if d["vid"] == "V001" else "wave", acc)
    c.setFont(serif_b, 19)
    c.drawString(92, H - 62, v["name"])
    c.setFont(serif, 9.5)
    for i, ln in enumerate(v["addr"] + [f"Tel {v['phone']}  |  {v['email']}", f"Tax ID: {v['tax_id']}"]):
        c.drawString(92, H - 76 - i * 11.5, ln)
    c.setFillColor(acc)
    c.setFont(serif_b, 26)
    c.drawRightString(W - 50, H - 66, d["title"] or "INVOICE")
    c.setFillColor(colors.black)
    pairs = meta_pairs(d)
    bx, by, bw = W - 230, H - 86, 180
    c.setStrokeColor(acc)
    c.rect(bx, by - 14 * len(pairs) - 4, bw, 14 * len(pairs) + 4, stroke=1, fill=0)
    for i, (k, val) in enumerate(pairs):
        c.setFont(serif_b, 9)
        c.drawString(bx + 6, by - 12 - i * 14, k)
        c.setFont(serif, 9)
        c.drawRightString(bx + bw - 6, by - 12 - i * 14, val)
    y = H - 175 - max(0, len(pairs) - 5) * 14
    for j, (lab, lines) in enumerate((("BILL TO", d["bill_to"]), ("SHIP TO", ship_lines(d)))):
        if not lines:
            continue
        x = 50 + j * 260
        c.setFillColor(acc)
        c.setFont(serif_b, 9.5)
        c.drawString(x, y, lab)
        c.setFillColor(colors.black)
        c.setFont(serif, 9.5)
        for i, ln in enumerate(lines):
            c.drawString(x, y - 13 - i * 11.5, ln)
    pen.y = y - 75
    cols = [("Item", 62, "l"), ("Description", 220, "l"), ("Qty", 48, "r"), ("Unit", 40, "c"),
            ("Unit Price", 70, "r"), ("Amount", 72, "r")]
    rows = [[l["sku"], l["desc"], qty_s(l["qty"]), l["unit"], num(l["price"]), num(l["amount"])] for l in d["lines"]]
    draw_table(pen, 50, cols, rows, dict(font=serif, hfont=serif_b, size=9.5, hfill=acc, htext=colors.white,
                                         grid=True, gridc=colors.HexColor("#C8CCC8")))
    draw_totals(pen, W - 140, W - 54, d, serif, serif_b, 10, rule=acc)
    pen.need(70)
    pen.y -= 14
    c.setFont(serif_b, 9.5)
    c.drawString(50, pen.y, "Remit payment to")
    c.setFont(serif, 9)
    for i, ln in enumerate(remit_lines(d)):
        c.drawString(50, pen.y - 13 - i * 11, ln)
    pen.y -= 50
    notes_block(pen, 50, d, serif, 9)
    footer_pages(c, d, pen.page, total_pages, serif)


# ---- template: qb (QuickBooks-like) ---------------------------------------------------------
def t_qb(c, d, total_pages):
    v, acc = d["v"], hexc(d["v"]["accent"])

    def cont(c, d, page):
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, H - 48, v["name"])
        footer_pages(c, d, page, total_pages)
        return H - 70

    pen = Pen(c, d, cont)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, H - 60, v["name"])
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(v["addr"] + [v["phone"], v["email"]]):
        c.drawString(50, H - 74 - i * 11, ln)
    logo(c, W - 82, H - 80, "square", acc, "".join(w[0] for w in v["name"].split()[:2]))
    c.setFillColor(acc)
    c.setFont("Helvetica", 24)
    c.drawString(50, H - 150, d["title"] or "Invoice")
    c.setFillColor(colors.black)
    y = H - 175
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(50, y, "BILL TO")
    if ship_lines(d):
        c.drawString(210, y, "SHIP TO")
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(d["bill_to"]):
        c.drawString(50, y - 12 - i * 11, ln)
    for i, ln in enumerate(ship_lines(d)):
        c.drawString(210, y - 12 - i * 11, ln)
    for i, (k, val) in enumerate(meta_pairs(d)):
        c.setFont("Helvetica-Bold", 8.5)
        c.drawRightString(W - 140, y - i * 13, k.upper())
        c.setFont("Helvetica", 9)
        c.drawString(W - 132, y - i * 13, val)
    pen.y = y - 80
    c.setStrokeColor(acc)
    c.setLineWidth(2)
    c.line(50, pen.y + 6, W - 50, pen.y + 6)
    cols = [("DATE", 62, "l"), ("ACTIVITY", 250, "l"), ("QTY", 55, "r"), ("RATE", 70, "r"), ("AMOUNT", 75, "r")]
    dt = fdate(d["inv_date"], "%m/%d/%Y") if d["inv_date"] and "date" not in d["hide"] else ""
    rows = [[dt, f"{l['sku']}  {l['desc']}", qty_s(l["qty"]), num(l["price"], 4 if l["price"] < 1 else 2),
             num(l["amount"])] for l in d["lines"]]
    draw_table(pen, 50, cols, rows, dict(size=9, hfill=colors.HexColor("#E8F1F0"), htext=acc, grid=True,
                                         gridc=colors.HexColor("#DDDDDD")))
    pen.need(110)
    pen.y -= 10
    c.setStrokeColor(colors.HexColor("#999999"))
    c.setDash(1, 2)
    c.line(50, pen.y, W - 50, pen.y)
    c.setDash()
    draw_totals(pen, W - 150, W - 54, d, size=9.5)
    if "total" not in d["hide"]:
        c.setFont("Helvetica", 9)
        c.drawRightString(W - 150, pen.y - 14, "BALANCE DUE")
        c.setFont("Helvetica-Bold", 16)
        c.drawRightString(W - 54, pen.y - 16, money(d["total"], d["currency"]))
        pen.y -= 30
    pen.y -= 10
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(50, pen.y, "PAYMENT DETAILS")
    c.setFont("Helvetica", 8.5)
    for i, ln in enumerate(remit_lines(d)):
        c.drawString(50, pen.y - 12 - i * 10.5, ln)
    pen.y -= 46
    notes_block(pen, 50, d)
    footer_pages(c, d, pen.page, total_pages)


# ---- template: letter (services letterhead, prose-ish) --------------------------------------
def t_letter(c, d, total_pages):
    v, acc = d["v"], hexc(d["v"]["accent"])

    def cont(c, d, page):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(60, H - 48, f"{v['name']}  -  Invoice {d['inv_no'] or ''}")
        footer_pages(c, d, page, total_pages)
        return H - 70

    pen = Pen(c, d, cont)
    c.setFillColor(acc)
    c.rect(0, H - 14, W, 14, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(W / 2, H - 52, v["name"].upper())
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(W / 2, H - 66, "  |  ".join(v["addr"] + [v["phone"]]))
    c.drawCentredString(W / 2, H - 77, f"{v['email']}   EIN {v['tax_id']}")
    c.setFillColor(colors.black)
    c.setStrokeColor(acc)
    c.line(60, H - 88, W - 60, H - 88)
    y = H - 115
    c.setFont("Helvetica-Bold", 13)
    c.drawString(60, y, d["title"] or "INVOICE")
    c.setFont("Helvetica", 9.5)
    for i, (k, val) in enumerate(meta_pairs(d)):
        c.drawString(60, y - 18 - i * 13, f"{k}:")
        c.drawString(150, y - 18 - i * 13, val)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(340, y - 18, "Billed to:")
    c.setFont("Helvetica", 9.5)
    for i, ln in enumerate(d["bill_to"]):
        c.drawString(340, y - 31 - i * 12, ln)
    if ship_lines(d):
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(340, y - 88, "Service location:")
        c.setFont("Helvetica", 9.5)
        c.drawString(340, y - 101, ", ".join(ship_lines(d)[:2]))
    pen.y = y - 18 - max(len(meta_pairs(d)) * 13, 100) - 10
    cols = [("Description of services", 300, "l"), ("Qty / Hrs", 60, "r"), ("Rate", 70, "r"), ("Amount", 62, "r")]
    rows = [[l["desc"], qty_s(l["qty"]), num(l["price"]), num(l["amount"])] for l in d["lines"]]
    draw_table(pen, 60, cols, rows, dict(size=9.5, hline=acc, hline_w=1.2, grid=True,
                                         gridc=colors.HexColor("#E2E2E2")))
    draw_totals(pen, W - 150, W - 64, d, size=10, rule=acc)
    pen.need(80)
    pen.y -= 18
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(60, pen.y, "Payment by ACH is appreciated. Please reference the invoice number with your payment.")
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(remit_lines(d)):
        c.drawString(60, pen.y - 14 - i * 11, ln)
    pen.y -= 52
    notes_block(pen, 60, d, "Helvetica", 9)
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(acc)
    c.drawCentredString(W / 2, 46, "Thank you for your business!")
    c.setFillColor(colors.black)
    footer_pages(c, d, pen.page, total_pages)


# ---- template: modern (side band, big amount due) -------------------------------------------
def t_modern(c, d, total_pages):
    v, acc = d["v"], hexc(d["v"]["accent"])

    def band():
        c.setFillColor(acc)
        c.rect(0, 0, 22, H, stroke=0, fill=1)
        c.setFillColor(colors.black)

    def cont(c, d, page):
        band()
        c.setFont("Helvetica-Bold", 10)
        c.drawString(60, H - 48, v["name"])
        footer_pages(c, d, page, total_pages)
        return H - 70

    pen = Pen(c, d, cont)
    band()
    c.setFont("Helvetica-Bold", 22)
    c.drawString(60, H - 70, (d["title"] or "Invoice").title() if d["title"] else "Invoice")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(60, H - 86, f"from {v['name']}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(W - 50, H - 58, v["name"])
    c.setFont("Helvetica", 8.5)
    for i, ln in enumerate(v["addr"] + [v["phone"], v["email"]]):
        c.drawRightString(W - 50, H - 72 - i * 10.5, ln)
    y = H - 150
    pairs = meta_pairs(d)
    for i, (k, val) in enumerate(pairs):
        cx = 60 + (i % 3) * 165
        cy = y - (i // 3) * 34
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#777777"))
        c.drawString(cx, cy, k.upper())
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(cx, cy - 13, val)
    y -= 34 * ((len(pairs) + 2) // 3) + 10
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#777777"))
    c.drawString(60, y, "BILL TO")
    if ship_lines(d):
        c.drawString(225, y, "LOCATION")
    if "total" not in d["hide"]:
        c.drawString(390, y, "AMOUNT DUE")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(d["bill_to"]):
        c.drawString(60, y - 13 - i * 11, ln)
    for i, ln in enumerate(ship_lines(d)):
        c.drawString(225, y - 13 - i * 11, ln)
    if "total" not in d["hide"]:
        c.setFillColor(acc)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(390, y - 30, money(d["total"], d["currency"]))
        c.setFillColor(colors.black)
    pen.y = y - 70
    cols = [("Description", 280, "l"), ("Qty", 55, "r"), ("Price", 80, "r"), ("Total", 82, "r")]
    rows = [[l["desc"], qty_s(l["qty"]), num(l["price"]), num(l["amount"])] for l in d["lines"]]
    draw_table(pen, 60, cols, rows, dict(size=9.5, hsize=8, htext=colors.HexColor("#777777"),
                                         hline=colors.HexColor("#DDDDDD"), zebra=colors.HexColor("#F6F6F6")))
    draw_totals(pen, W - 150, W - 54, d, size=10)
    pen.need(70)
    pen.y -= 16
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(60, pen.y, "HOW TO PAY")
    c.setFont("Helvetica", 8.5)
    for i, ln in enumerate(remit_lines(d)):
        c.drawString(60, pen.y - 12 - i * 10.5, ln)
    pen.y -= 46
    notes_block(pen, 60, d)
    footer_pages(c, d, pen.page, total_pages)


# ---- template: distrib (dense distributor invoice, ordered vs shipped) ----------------------
def t_distrib(c, d, total_pages):
    v, acc = d["v"], hexc(d["v"]["accent"])
    mono = d["vid"] == "V007"
    font, bold = ("Courier", "Courier-Bold") if mono else ("Helvetica", "Helvetica-Bold")

    def head(c, page):
        c.setFillColor(acc)
        c.rect(36, H - 74, W - 72, 40, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(46, H - 52, v["name"].upper())
        c.setFont("Helvetica", 8)
        c.drawString(46, H - 66, f"{', '.join(v['addr'])}   {v['phone']}")
        c.setFont("Helvetica-Bold", 13)
        c.drawRightString(W - 46, H - 52, d["title"] or "INVOICE")
        c.setFont("Helvetica", 8.5)
        c.drawRightString(W - 46, H - 66, f"No. {d['inv_no']}" if "invoice_no" not in d["hide"] else "")
        c.setFillColor(colors.black)
        footer_pages(c, d, page, total_pages, font)

    def cont(c, d, page):
        head(c, page)
        return H - 90

    pen = Pen(c, d, cont, bottom=60)
    head(c, 1)
    y = H - 92
    c.setFont(font, 8)
    info = [("CUSTOMER #", "CLRG-0042"), ("INVOICE DATE", fdate(d["inv_date"], v["datefmt"]) if "date" not in d["hide"] else ""),
            ("CUST PO", d["po"] or "" if "po" not in d["hide"] else ""), ("TERMS", v["terms"][0]),
            ("ROUTE", "R-14 / DRV 22"), ("SALESREP", "M. KOWALSKI")]
    for i, (k, val) in enumerate(info):
        cx = 40 + (i % 3) * 180
        cy = y - (i // 3) * 22
        c.setFont(bold, 7.5)
        c.drawString(cx, cy, k)
        c.setFont(font, 8.5)
        c.drawString(cx, cy - 10, val)
    y -= 52
    for j, (lab, lines) in enumerate((("SOLD TO", d["bill_to"]), ("SHIP TO", ship_lines(d)))):
        if not lines:
            continue
        c.setFont(bold, 8)
        c.drawString(40 + j * 270, y, lab)
        c.setFont(font, 8.5)
        for i, ln in enumerate(lines):
            c.drawString(40 + j * 270, y - 11 - i * 10, ln)
    pen.y = y - 62
    cols = [("ITEM#", 50, "l"), ("DESCRIPTION", 196, "l"), ("ORD", 38, "r"), ("SHIP", 40, "r"), ("U/M", 32, "c"),
            ("PRICE", 60, "r"), ("EXTENSION", 72, "r")]
    rows = [[l["sku"], l["desc"], qty_s(l.get("ordered", l["qty"])), qty_s(l["qty"]), l["unit"],
             num(l["price"]), num(l["amount"])] for l in d["lines"]]
    draw_table(pen, 38, cols, rows, dict(font=font, hfont=bold, size=8, pad=3, hline=colors.black,
                                         zebra=colors.HexColor("#F1F1F1")))
    draw_totals(pen, W - 140, W - 44, d, font, bold, 9, rule=colors.black)
    pen.need(60)
    pen.y -= 10
    c.setFont(font, 7.5)
    for i, ln in enumerate(remit_lines(d) + ["Claims for shortages must be made at time of delivery. 1.5%/mo late charge."]):
        c.drawString(40, pen.y - i * 10, ln)
    pen.y -= 46
    notes_block(pen, 40, d, font, 8)


# ---- template: ticket (narrow thermal delivery ticket) --------------------------------------
def ticket_size(d):
    return (3.4 * inch, (5.2 + 0.33 * len(d["lines"]) + 0.16 * len(d["notes"])) * inch)


def t_ticket(c, d, total_pages):
    v = d["v"]
    tw, th = ticket_size(d)
    y = th - 22
    c.setFont("Courier-Bold", 10)
    c.drawCentredString(tw / 2, y, v["name"].upper())
    c.setFont("Courier", 7.5)
    for ln in v["addr"] + [v["phone"]]:
        y -= 10
        c.drawCentredString(tw / 2, y, ln)
    y -= 16
    c.setFont("Courier-Bold", 9)
    c.drawCentredString(tw / 2, y, "DELIVERY TICKET / INVOICE")
    c.setFont("Courier", 7.8)
    rows = []
    if "invoice_no" not in d["hide"]:
        rows.append(f"TICKET#  {d['inv_no']}")
    if "date" not in d["hide"]:
        rows.append(f"DATE     {fdate(d['inv_date'], v['datefmt'])}")
    if d["po"] and "po" not in d["hide"]:
        rows.append(f"PO#      {d['po']}")
    rows += [f"CUST     {d['bill_to'][0].upper()}", f"ACCT     CLRG-{d['loc']}", f"STOP     {', '.join(LOCATIONS[d['loc']][:1])}", f"TERMS    {v['terms'][0]}"]
    for r in rows:
        y -= 11
        c.drawString(10, y, r)
    y -= 8
    c.drawString(10, y, "-" * 44)
    y -= 10
    c.setFont("Courier-Bold", 7.6)
    c.drawString(10, y, "QTY  ITEM                 PRICE    EXT")
    c.setFont("Courier", 7.6)
    for l in d["lines"]:
        y -= 11
        c.drawString(10, y, f"{qty_s(l['qty']):>3}  {l['desc'][:19]:<19}{l['price']:>8.2f}{l['amount']:>8.2f}")
        y -= 9
        c.drawString(25, y, f"{l['desc'][19:].strip()} {l['sku']} /{l['unit']}".strip())
    y -= 8
    c.drawString(10, y, "-" * 44)
    for lab, val, b in totals_rows(d):
        y -= 12
        c.setFont("Courier-Bold" if b else "Courier", 8.5 if b else 7.8)
        c.drawString(10, y, lab)
        c.drawRightString(tw - 10, y, val)
    y -= 18
    c.setFont("Courier", 7)
    for ln in [f"ACH {v['bank']['bank']}", f"RTN {v['bank']['routing']} ACCT {v['bank']['account']}"] + d["notes"]:
        for part in simpleSplit(ln, "Courier", 7, tw - 20):
            c.drawString(10, y, part)
            y -= 9
    y -= 14
    c.drawString(10, y, "RECEIVED BY: ____________________")
    y -= 12
    c.drawString(10, y, "TEMP AT DELIVERY: 37F   DRIVER: 0714")


# ---- template: hand (carbon-book handwritten invoice) ---------------------------------------
HAND_SIZE = (5.5 * inch, 8.5 * inch)


HAND_SCALE = 6  # px per pt when rasterising handwriting
WRITER_SLANT = {"kalam": 0.10, "nothing": 0.22, "reenie": 0.18, "another": 0.06, "shadows": 0.12, "apple": 0.25}


def _field(shape, sigma, r):
    from scipy.ndimage import gaussian_filter
    n = gaussian_filter(r.standard_normal(shape), sigma)
    return n / (np.abs(n).max() + 1e-9)


def hand_image(text, font, size, seed, ink=(28, 40, 120)):
    """Rasterise text as natural handwriting. Every glyph varies in size, angle, spacing and baseline (a font
    repeats each letter identically, a hand never does), strokes vary in pen pressure, ballpoint ink skips,
    and the whole word is elastically warped. Returns (RGBA image, baseline y in px)."""
    from scipy.ndimage import gaussian_filter, map_coordinates
    r = np.random.default_rng(seed)
    S, px = HAND_SCALE, int(size * HAND_SCALE)
    fonts = {}

    def F(sz):
        return fonts.setdefault(int(sz), pil_font(font, int(sz)))

    W, H = int(px * (0.8 * len(text) + 3)), int(px * 2.6)
    img = Image.new("L", (W, H), 0)
    base, x, drift, tilt = px * 1.6, px * 0.6, 0.0, r.normal(0, 0.015)
    for ch in text:
        num = ch in "0123456789$.,/"
        f = F(px * r.normal(1.0, 0.05 if num else 0.09) * (1.35 if ch in ".," else 1.0))
        adv = f.getlength(ch)
        if ch == " ":
            x += adv * r.uniform(0.9, 1.6)
            continue
        drift = 0.65 * drift + r.normal(0, px * 0.04)
        tile = Image.new("L", (int(px * 2.4), int(px * 2.8)), 0)
        ImageDraw.Draw(tile).text((px * 0.6, px * 1.8), ch, font=f, fill=255, anchor="ls")
        tile = tile.rotate(r.normal(0, 2.5 if num else 5.5), resample=Image.BICUBIC, center=(px * 0.6, px * 1.8))
        img.paste(255, (int(x - px * 0.6), int(base + drift + tilt * x - px * 1.8)), tile)
        x += adv * (r.normal(1.10, 0.04) if num else r.normal(1.0, 0.08))
        x += px * (0.18 if ch == "$" else 0.10 if ch == "1" else 0.0)  # keep "$6" and "11" apart
    img = img.crop((0, 0, int(min(W, x + px * 0.8)), H))
    sl = WRITER_SLANT.get(font, 0.12) + r.normal(0, 0.02)
    pad = int(abs(sl) * H)
    img = img.transform((img.width + pad, H), Image.AFFINE, (1, sl, -sl * base, 0, 1, 0), Image.BICUBIC)
    a = np.asarray(img).astype(np.float32) / 255.0
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]].astype(np.float32)
    amp = px * 0.07
    a = map_coordinates(a, [yy + _field(a.shape, px * 0.4, r) * amp, xx + _field(a.shape, px * 0.4, r) * amp],
                        order=1, mode="constant")
    thick = np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) / 255.0
    w = (_field(a.shape, px * 0.6, r) + 1) / 2  # pen pressure
    a = a * (1 - w) + thick * w
    skips = np.clip(0.82 + 0.35 * _field(a.shape, 2.2, r), 0.35, 1.0)  # ballpoint ink skips / grain
    a = gaussian_filter(a * skips, 0.7)
    rgba = np.zeros(a.shape + (4,), np.uint8)
    rgba[..., :3] = ink
    rgba[..., 3] = np.clip(a * 245, 0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA"), base


def hand_write(c, x, y, text, font, size, rng, ink=(0.16, 0.18, 0.52)):
    from reportlab.lib.utils import ImageReader
    img, base = hand_image(str(text), font, size, rng.randrange(1 << 30), tuple(int(v * 255) for v in ink))
    S = HAND_SCALE
    c.drawImage(ImageReader(img), x - 0.6 * size + rng.uniform(-1, 1), y - (img.height - base) / S,
                width=img.width / S, height=img.height / S, mask="auto")


def t_hand(c, d, total_pages):
    v = d["v"]
    hw, hh = HAND_SIZE
    rng = random.Random(d["inv_no"] or "hand")
    font = d["extra"].get("hand_font", "nothing")
    navy = colors.HexColor("#22305E")
    c.setFillColor(colors.HexColor("#FBF7E9"))
    c.rect(0, 0, hw, hh, stroke=0, fill=1)
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(24, hh - 36, v["name"])
    c.setFont("Helvetica", 7.5)
    c.drawString(24, hh - 48, f"{v['addr'][0]}, {v['addr'][1]}  -  {v['phone']}")
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(hw - 24, hh - 36, "INVOICE")
    c.setFillColor(colors.HexColor("#B91C1C"))
    c.setFont("Courier-Bold", 13)
    c.drawRightString(hw - 24, hh - 52, f"No. {d['inv_no']}")
    c.setFillColor(navy)
    c.setStrokeColor(navy)
    c.setLineWidth(0.6)
    labels = [("DATE", hh - 82), ("SOLD TO", hh - 104), ("ADDRESS", hh - 126), ("PO / JOB", hh - 148)]
    for lab, y in labels:
        c.setFont("Helvetica", 7)
        c.drawString(24, y, lab)
        c.line(72, y - 2, hw - 24, y - 2)
    top = hh - 170
    c.rect(24, 150, hw - 48, top - 150, stroke=1, fill=0)
    cols_x = [24, 58, 250, 310, hw - 24]
    for x in cols_x[1:-1]:
        c.line(x, 150, x, top)
    c.setFont("Helvetica-Bold", 7)
    for lab, x0, x1 in zip(["QTY", "DESCRIPTION", "PRICE", "AMOUNT"], cols_x, cols_x[1:]):
        c.drawCentredString((x0 + x1) / 2, top - 11, lab)
    c.line(24, top - 15, hw - 24, top - 15)
    row_h = 21
    for i in range(1, int((top - 165) / row_h) + 1):
        c.setStrokeColor(colors.HexColor("#9AA5C7"))
        c.line(24, top - 15 - i * row_h, hw - 24, top - 15 - i * row_h)
    c.setStrokeColor(navy)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(310 - 6, 132, "TOTAL")
    c.rect(310, 122, hw - 24 - 310, 22, stroke=1, fill=0)
    c.setFont("Helvetica", 6.5)
    c.drawString(24, 100, "Make checks payable to Tony's Handyman & Repair. ACH accepted:")
    c.drawString(24, 90, f"{v['bank']['bank']}  RTN {v['bank']['routing']}  ACCT {v['bank']['account']}")
    c.drawString(24, 60, "Customer signature ______________________")
    c.setFillColor(colors.black)
    # handwriting
    hand_write(c, 80, hh - 82, fdate(d["inv_date"], v["datefmt"]), font, 13, rng)
    hand_write(c, 80, hh - 104, d["bill_to"][0], font, 13, rng)
    hand_write(c, 80, hh - 126, ", ".join(LOCATIONS[d["loc"]][1:]), font, 12, rng)
    if d["po"]:
        hand_write(c, 80, hh - 148, f"{d['po']}  -  {d['extra'].get('job', '')}", font, 12, rng)
    for i, l in enumerate(d["lines"]):
        y = top - 15 - (i + 1) * row_h + 6
        hand_write(c, 30, y, qty_s(l["qty"]), font, 12, rng)
        hand_write(c, 63, y, l["desc"], font, 11.5, rng)
        hand_write(c, 256, y, f"{l['price']:,.2f}", font, 12, rng)
        hand_write(c, 316, y, f"{l['amount']:,.2f}", font, 12, rng)
    if "total" not in d["hide"]:
        hand_write(c, 316, 128, f"${d['total']:,.2f}", font, 15, rng)
    if d["notes"]:
        hand_write(c, 30, 165, d["notes"][0], font, 11, rng)
    hand_write(c, 120, 62, "Tony R.", "apple", 13, rng)


# ---- other documents: statement of account --------------------------------------------------
def t_statement(c, d, total_pages):
    v, acc = d["v"], hexc(d["v"]["accent"])
    pen = Pen(c, d, lambda *a: H - 60)
    logo(c, 50, H - 82, "leaf", acc)
    c.setFont("Times-Bold", 19)
    c.drawString(92, H - 62, v["name"])
    c.setFont("Times-Roman", 9.5)
    for i, ln in enumerate(v["addr"] + [v["phone"]]):
        c.drawString(92, H - 76 - i * 11.5, ln)
    c.setFillColor(acc)
    c.setFont("Times-Bold", 16)
    c.drawRightString(W - 50, H - 110, "STATEMENT OF ACCOUNT")
    c.setFillColor(colors.black)
    c.setFont("Times-Roman", 10)
    c.drawRightString(W - 50, H - 126, f"Statement date: {fdate(d['inv_date'], v['datefmt'])}")
    c.drawRightString(W - 50, H - 139, "Account: CLRG-0042")
    c.drawRightString(W - 50, H - 152, f"Statement No.: {d['inv_no']}")
    for i, ln in enumerate(d["bill_to"]):
        c.drawString(50, H - 165 - i * 12, ln)
    pen.y = H - 235
    cols = [("Date", 80, "l"), ("Reference", 120, "l"), ("Description", 140, "l"), ("Charges", 60, "r"),
            ("Payments", 60, "r"), ("Balance", 52, "r")]
    draw_table(pen, 50, cols, d["extra"]["rows"], dict(font="Times-Roman", hfont="Times-Bold", size=9.5, hfill=acc,
                                                        htext=colors.white, grid=True))
    pen.y -= 20
    c.setFont("Times-Bold", 12)
    c.drawRightString(W - 54, pen.y, f"Balance forward: {money(d['total'])}")
    pen.y -= 30
    c.setFont("Times-Roman", 9)
    c.drawString(50, pen.y, "Aging:  Current $1,734.60   31-60 days $0.00   61-90 days $0.00   Over 90 $0.00")
    c.drawString(50, pen.y - 14, "This is a statement of your account, not an invoice. Please pay from invoice.")
    c.setFont("Times-Bold", 9)
    c.drawString(50, pen.y - 40, "Remit to")
    c.setFont("Times-Roman", 9)
    for i, ln in enumerate(remit_lines(d)):
        c.drawString(50, pen.y - 53 - i * 11, ln)


ASSETS = Path(__file__).resolve().parent / "assets"


def draw_logo_image(c, vid, x, y, w, h):
    """Draw scripts/assets/logos/<vid>.png into the box (x, y bottom-left). Returns False if no logo exists."""
    f = ASSETS / "logos" / f"{vid}.png"
    if not f.exists():
        return False
    c.drawImage(str(f), x, y, width=w, height=h, preserveAspectRatio=True, anchor="c", mask="auto")
    return True


def get_template(d):
    """Vendor-specific design from scripts/templates/<design>.py if present, else the generic layout."""
    import importlib
    import sys
    name = d["extra"].get("template") or d["v"].get("design")
    if name and (Path(__file__).resolve().parent / "templates" / f"{name}.py").exists():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        return importlib.import_module(f"templates.{name}").render
    return TEMPLATES[d["extra"].get("template") or d["v"]["template"]]


TEMPLATES = dict(classic=t_classic, qb=t_qb, letter=t_letter, modern=t_modern, distrib=t_distrib,
                 ticket=t_ticket, hand=t_hand, statement=t_statement)


def page_size(d):
    fn = get_template(d)
    mod = __import__(fn.__module__, fromlist=["x"]) if fn.__module__.startswith("templates.") else None
    if mod is not None and hasattr(mod, "page_size"):
        return mod.page_size(d)
    t = d["extra"].get("template") or d["v"]["template"]
    return {"ticket": ticket_size(d), "hand": HAND_SIZE}.get(t, letter)


def render_docs(docs, encrypt=None):
    """Render one or more documents into a single PDF (bytes). Two passes to know total page count."""
    def once(total_pages_list):
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=page_size(docs[0]), encrypt=encrypt() if encrypt else None)
        c.setTitle(docs[0]["title"] or "Invoice")
        c.setAuthor(docs[0]["v"]["name"])
        counts = []
        for i, d in enumerate(docs):
            c.setPageSize(page_size(d))
            before = c.getPageNumber()
            get_template(d)(c, d, total_pages_list[i])
            c.showPage()
            counts.append(c.getPageNumber() - before)
        c.save()
        return buf.getvalue(), counts

    _, counts = once([1] * len(docs))
    pdf, _ = once(counts)
    return pdf


# --------------------------------------------------------------------------------------------
# Degradation effects (rendered page images -> scanned / faxed / photographed look)
# --------------------------------------------------------------------------------------------
STAMP_FONT = "C:/Windows/Fonts/arialbd.ttf"


def pil_font(path_or_hand, size):
    p = FONT_DIR / HANDS[path_or_hand] if path_or_hand in HANDS else Path(path_or_hand)
    try:
        return ImageFont.truetype(str(p), size)
    except OSError:
        return ImageFont.truetype(str(FONT_DIR / HANDS["kalam"]), size)


def rasterize(pdf_bytes, dpi=200):
    pdf = pdfium.PdfDocument(pdf_bytes)
    return [pdf[i].render(scale=dpi / 72).to_pil().convert("RGB") for i in range(len(pdf))]


def fx_noise(img, rng, sigma=9):
    a = np.asarray(img).astype(np.int16)
    a = a + rng.normal(0, sigma, a.shape[:2])[..., None].astype(np.int16)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def fx_scan(img, rng, skew=1.0, noise=7, gray=True, blur=0.4, tone=(246, 244, 238)):
    if gray:
        img = img.convert("L").convert("RGB")
    a = np.asarray(img).astype(np.float32) / 255.0
    paper = np.array(tone, np.float32) / 255.0
    a = a * paper + (1 - paper) * 0.02
    img = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    img = img.rotate(skew, resample=Image.BICUBIC, expand=False, fillcolor=(38, 38, 40) if abs(skew) > 2 else tone)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return fx_noise(img, rng, noise)


def fx_fax(img, rng):
    g = img.convert("L")
    g = g.resize((g.width // 2, g.height // 2), Image.BILINEAR)
    g = g.rotate(rng.uniform(-0.8, 0.8), fillcolor=255)
    a = np.asarray(g).astype(np.int16) + rng.normal(0, 22, (g.height, g.width)).astype(np.int16)
    b = np.where(a > 165, 255, 0).astype(np.uint8)
    specks = rng.random(b.shape) < 0.0025
    b[specks] = 0
    for _ in range(3):  # horizontal transmission streaks
        y = int(rng.integers(0, b.shape[0] - 2))
        b[y:y + 1, :] = np.where(rng.random(b.shape[1]) < 0.6, 0, b[y, :])
    top = Image.new("L", (b.shape[1], 18), 255)
    d = ImageDraw.Draw(top)
    d.text((8, 3), "OCT 03 2026 09:14  FROM: 7735550184  TO: 3125550100   P.01/01", fill=0,
           font=pil_font(STAMP_FONT, 11))
    out = Image.new("L", (b.shape[1], b.shape[0] + 18), 255)
    out.paste(top, (0, 0))
    out.paste(Image.fromarray(b), (0, 18))
    return out.convert("RGB")


def persp_coeffs(dst, src):
    A, B = [], []
    for (x, y), (X, Y) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -X * x, -X * y])
        A.append([0, 0, 0, x, y, 1, -Y * x, -Y * y])
        B += [X, Y]
    return np.linalg.solve(np.array(A, float), np.array(B, float)).tolist()


def _bend(page, rng, amp):
    """Paper is never flat in a photo: sag/curl it with a smooth vertical displacement along x."""
    w, h = page.size
    amp = max(int(amp), 1)
    def f(x):
        return amp * (1 + math.sin(math.pi * x / w))

    n = 24
    mesh = []
    for i in range(n):
        x0, x1 = int(i * w / n), int((i + 1) * w / n)
        mesh.append(((x0, 0, x1, h + 2 * amp),
                     (x0, -f(x0), x0, h + 2 * amp - f(x0), x1, h + 2 * amp - f(x1), x1, -f(x1))))
    out = page.transform((w, h + 2 * amp), Image.MESH, mesh, Image.BICUBIC, fillcolor=(0, 0, 0, 0))
    a = np.asarray(out).astype(np.float32)
    slope = np.gradient(np.array([f(x) for x in range(w)]))
    a[..., :3] *= (0.97 - 0.9 * np.clip(slope, -0.12, 0.12))[None, :, None]  # light falls off on the curl
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def _cover(tex, size):
    tw, th = size
    sc = max(tw / tex.width, th / tex.height)
    tex = tex.resize((math.ceil(tex.width * sc), math.ceil(tex.height * sc)), Image.BICUBIC)
    left, top = (tex.width - tw) // 2, (tex.height - th) // 2
    return tex.crop((left, top, left + tw, top + th))


def fx_photo(img, rng, strength=1.0, bg=(118, 92, 66), shadow=True, crumple=False, surface=None):
    """A phone photo of a paper invoice lying on a surface: curled paper, keystone perspective, contact shadow,
    hand/phone shadow, lamp glare, vignetting, warm white balance and camera softness."""
    from scipy.ndimage import gaussian_filter
    w, h = img.size
    cw, ch = int(w * 1.32), int(h * 1.24)
    tex = ASSETS / "surfaces" / f"{surface}.jpg" if surface else None
    if tex is not None and tex.exists():
        canvas = _cover(Image.open(tex).convert("RGB"), (cw, ch)).convert("RGBA")
    else:
        bgarr = np.ones((ch, cw, 3), np.float32) * np.array(bg, np.float32)
        bgarr += gaussian_filter(rng.normal(0, 30, (ch, cw)), 3)[..., None]
        canvas = Image.fromarray(np.clip(bgarr, 0, 255).astype(np.uint8)).convert("RGBA")
    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    a[..., :3] *= np.array([0.97, 0.96, 0.93])  # paper is never pure white
    if crumple:  # creases: each fold splits the paper into a lighter and a darker facet with a sharp crease line
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        shade = np.zeros((h, w), np.float32)
        for _ in range(12):
            th = rng.uniform(0, math.pi)
            nx, ny = math.cos(th), math.sin(th)
            x0, y0 = rng.uniform(0.1, 0.9) * w, rng.uniform(0.1, 0.9) * h
            dist = (xx - x0) * nx + (yy - y0) * ny
            along = (xx - x0) * -ny + (yy - y0) * nx
            win = np.exp(-(along / (rng.uniform(0.25, 0.7) * max(w, h))) ** 2)
            amp = rng.uniform(0.045, 0.09) * rng.choice([-1, 1])
            shade += win * (amp * np.tanh(dist / rng.uniform(20, 60)) - abs(amp) * 1.6 * np.exp(-(dist / 2.2) ** 2))
        a[..., :3] *= (1 + shade)[..., None]
    page = _bend(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA"), rng, h * 0.007 * strength)
    pw, ph = page.size
    ang = math.radians(rng.uniform(-5, 5) * strength)
    k = rng.uniform(0.03, 0.08) * strength  # keystone: phone tilted, far edge narrower
    hw, hh = pw * 0.88 / 2, ph * 0.88 / 2
    cx, cy = cw / 2 + rng.uniform(-0.02, 0.02) * cw, ch / 2 + rng.uniform(-0.02, 0.02) * ch
    quad = []
    for dx, dy in [(-hw * (1 - k), -hh), (hw * (1 - k), -hh), (hw, hh), (-hw, hh)]:
        dx += rng.uniform(-0.012, 0.012) * pw * strength
        dy += rng.uniform(-0.012, 0.012) * ph * strength
        quad.append((cx + dx * math.cos(ang) - dy * math.sin(ang), cy + dx * math.sin(ang) + dy * math.cos(ang)))
    sh = Image.new("L", (cw, ch), 0)  # contact shadow under the paper
    ImageDraw.Draw(sh).polygon([(x + cw * 0.008, y + ch * 0.012) for x, y in quad], fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(cw * 0.012))
    canvas = Image.composite(Image.new("RGBA", (cw, ch), (0, 0, 0, 255)), canvas, sh)
    warped = page.transform((cw, ch), Image.PERSPECTIVE, persp_coeffs(quad, [(0, 0), (pw, 0), (pw, ph), (0, ph)]),
                            Image.BICUBIC, fillcolor=(0, 0, 0, 0))
    canvas.alpha_composite(warped)
    a = np.asarray(canvas.convert("RGB")).astype(np.float32)
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    lx, ly = rng.uniform(0.2, 0.5), rng.uniform(0.15, 0.4)  # lamp position
    light = 1.08 - 0.45 * ((xx / cw - lx) ** 2 + (yy / ch - ly) ** 2)
    if shadow:  # soft shadow of the hand/phone reaching in from one corner
        corner = [(0, 0), (1, 0), (1, 1), (0, 1)][int(rng.integers(0, 4))]
        dist = np.sqrt((xx / cw - corner[0]) ** 2 + (yy / ch - corner[1]) ** 2)
        light *= 1 - 0.38 * np.clip(1 - dist / rng.uniform(0.45, 0.6), 0, 1) ** 1.5
    glare = np.exp(-(((xx / cw - lx - 0.12) / 0.10) ** 2 + ((yy / ch - ly - 0.1) / 0.07) ** 2))
    a = a * light[..., None] + 38 * glare[..., None]
    a *= np.array([1.05, 1.0, 0.88])  # warm indoor white balance
    a += gaussian_filter(rng.normal(0, 7, a.shape[:2]), 0.6)[..., None] + rng.normal(0, 3, a.shape)
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
    return out.resize((int(cw * 0.72), int(ch * 0.72)), Image.LANCZOS)


def overlay_text(img, text, rel, angle, font, size, color, box=False, width=6):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    f = pil_font(font, size)
    tmp = Image.new("RGBA", (int(size * len(text) * 0.75) + 60, int(size * 2.2)), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    bb = td.textbbox((30, 10), text, font=f)
    td.text((30, 10), text, font=f, fill=color)
    if box:
        td.rounded_rectangle((bb[0] - 14, bb[1] - 10, bb[2] + 14, bb[3] + 10), radius=10, outline=color, width=width)
    tmp = tmp.crop((0, 0, bb[2] + 30, bb[3] + 20))
    if box:  # rubber stamps never ink evenly
        from scipy.ndimage import gaussian_filter
        t = np.asarray(tmp).astype(np.float32)
        rr = np.random.default_rng(len(text) * 31 + size)
        t[..., 3] *= np.clip(0.75 + 0.5 * gaussian_filter(rr.standard_normal(t.shape[:2]), 2.0) * 4, 0.25, 1.0)
        tmp = Image.fromarray(np.clip(t, 0, 255).astype(np.uint8), "RGBA")
    tmp = tmp.rotate(angle, expand=True, resample=Image.BICUBIC)
    layer.alpha_composite(tmp, (int(rel[0] * img.width), int(rel[1] * img.height)))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def fx_stamp(img, text, rel, angle=-12, color=(196, 32, 38, 175), size=64):
    return overlay_text(img, text, rel, angle, STAMP_FONT, size, color, box=True)


def fx_ink(img, text, rel, angle=4, size=58, font="nothing", color=(22, 44, 140, 235)):
    """Pen annotation added by staff: same natural-handwriting renderer as the handwritten invoices."""
    import zlib
    him, _ = hand_image(text, font, size / HAND_SCALE, zlib.crc32(text.encode()), ink=color[:3])
    him = him.rotate(angle, expand=True, resample=Image.BICUBIC)
    out = img.convert("RGBA")
    out.alpha_composite(him, (int(rel[0] * img.width), int(rel[1] * img.height)))
    return out.convert("RGB")


def fx_coffee(img, rel, r=130):
    """Mug ring: brown tint inside, darker irregular tide-line, a couple of drips."""
    rr = np.random.default_rng(int(r * 7 + rel[0] * 1000))
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = rel[0] * img.width, rel[1] * img.height
    d.ellipse((cx - r, cy - r * 0.93, cx + r, cy + r * 0.93), fill=(156, 108, 58, 40))
    for k in range(7):  # uneven tide-line
        j = rr.uniform(-5, 5, 4)
        d.ellipse((cx - r + j[0], cy - r * 0.93 + j[1], cx + r + j[2], cy + r * 0.93 + j[3]),
                  outline=(112, 70, 32, int(rr.uniform(40, 90))), width=int(rr.integers(3, 9)))
    for _ in range(3):
        a = rr.uniform(0, 2 * math.pi)
        px_, py_ = cx + math.cos(a) * r * 1.15, cy + math.sin(a) * r * 1.05
        s_ = rr.uniform(8, 18)
        d.ellipse((px_ - s_, py_ - s_, px_ + s_, py_ + s_), fill=(140, 92, 48, 70))
    layer = layer.filter(ImageFilter.GaussianBlur(2.5))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def fx_crease(img, rel_y):
    """Fold line: soft shadow on one side, highlight on the other, slight brightness step across the fold."""
    a = np.asarray(img).astype(np.float32)
    h = a.shape[0]
    y0 = rel_y * h
    yy = np.arange(h, dtype=np.float32)[:, None]
    dist = yy - y0
    shade = 1 - 0.16 * np.exp(-((dist + 6) / 9) ** 2) + 0.06 * np.exp(-((dist - 5) / 6) ** 2) - 0.03 * (dist > 0)
    a *= shade[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def fx_blur_heavy(img, rng):
    # Motion blur + defocus: layout and headings still visible, digits unreadable.
    small = img.resize((img.width // 6, img.height // 6), Image.BILINEAR)
    img = small.resize(img.size, Image.BILINEAR)
    a = np.asarray(img).astype(np.float32)
    n = max(6, img.width // 90)
    a = sum(np.roll(a, k, axis=1) for k in range(-n, n + 1)) / (2 * n + 1)  # horizontal hand-shake
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.6))
    return fx_noise(img, rng, 10)


def apply_fx(images, steps, seed):
    rng = np.random.default_rng(seed)
    out = []
    for p, img in enumerate(images):
        for name, kw in steps:
            if kw.get("page") not in (None, p):
                continue
            kw = {k: v for k, v in kw.items() if k != "page"}
            if name == "scan":
                img = fx_scan(img, rng, **kw)
            elif name == "fax":
                img = fx_fax(img, rng)
            elif name == "photo":
                img = fx_photo(img, rng, **kw)
            elif name == "stamp":
                img = fx_stamp(img, **kw)
            elif name == "ink":
                img = fx_ink(img, **kw)
            elif name == "coffee":
                img = fx_coffee(img, **kw)
            elif name == "crease":
                img = fx_crease(img, **kw)
            elif name == "rotate90":
                img = img.rotate(90, expand=True)
            elif name == "blur_heavy":
                img = fx_blur_heavy(img, rng)
            elif name == "jpeg":
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=kw.get("q", 70))
                img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        out.append(img)
    return out


def write_images_pdf(path, images, dpi):
    images[0].save(path, "PDF", resolution=dpi, save_all=True, append_images=images[1:], quality=72)


# --------------------------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------------------------
SCEN = []
ORIGINALS = {}


def S(id_, slug, docs, *, kind, quality=(), category, title, scenario, expect, expect_batch=None, fx=(),
      dpi=200, ext="pdf", special=None, similar_to=None):
    SCEN.append(dict(id=id_, slug=slug, docs=docs if isinstance(docs, list) else [docs], kind=kind,
                     quality=list(quality), category=category, title=title, scenario=scenario,
                     expect=expect, expect_batch=expect_batch or expect, fx=list(fx), dpi=dpi, ext=ext,
                     special=special, similar_to=similar_to))


def D(day):  # date helper: day offset in 2026
    return date(2026, *day) if isinstance(day, tuple) else day


def build():
    rnd = random.Random(7)

    def pick(vid, k, qty_range=(1, 12)):
        idx = rnd.sample(range(len(CATALOG[vid])), k)
        return from_catalog(vid, [(i, rnd.randint(*qty_range)) for i in idx])

    # ----- seeded history the scenarios depend on ------------------------------------------
    gl2207 = from_catalog("V001", [(0, 12), (1, 8), (3, 6), (4, 3), (5, 2)])
    make_po("V001", gl2207, po="PO-1040", loc="FUL", created=D((9, 10)))
    ledger_add("V001", "INV-GL-2207", D((9, 22)), "PO-1040", gl2207)
    ORIGINALS["INV-GL-2207"] = doc("V001", gl2207, inv_no="INV-GL-2207", inv_date=D((9, 22)), po="PO-1040")

    ng_hist = [L("RNT-PKG", "Kitchen equipment rental package incl. install", "mo", 19000.00, 1)]
    make_po("V004", [L("RNT-BLK", "Kitchen equipment rental - FY26 blanket", "lot", 50000.00, 1)], po="PO-1043",
            kind="blanket", loc="FUL", created=D((7, 20)))
    ledger_add("V004", "NG-0301", D((8, 1)), "PO-1043", ng_hist)
    ledger_add("V004", "NG-0302", D((9, 1)), "PO-1043", ng_hist)

    def bw_ret(month):
        return [L("MS-RET", f"Managed IT support retainer - {month} 2026", "mo", 2400.00, 1),
                L("POS-SUP", f"POS support & monitoring - {month} 2026", "mo", 650.00, 1),
                L("M365", "Microsoft 365 Business licences", "user", 12.50, 44)]
    make_po("V005", [L("RET-FY26", "Managed services retainer FY2026 (12 mo)", "lot", 43200.00, 1)], po="PO-1044",
            kind="blanket", created=D((1, 5)), opening_billed=28800.00)
    ledger_add("V005", "BW-2026-09", D((9, 1)), "PO-1044", bw_ret("September"), service_period="September 2026")

    pr4512 = from_catalog("V002", [(2, 6), (4, 3)])
    make_po("V002", pr4512, po="PO-1041", loc="WKP", created=D((8, 28)))
    ledger_add("V002", "PR-104512", D((9, 12)), "PO-1041", pr4512)

    make_po("V003", [L("SVC-N", "Nightly janitorial service - August 2026", "mo", 1850.00, 1)], po="PO-1039",
            status="closed", loc="FUL", created=D((7, 25)))
    gl1046 = from_catalog("V001", [(6, 10), (8, 6), (9, 4), (11, 5)])
    make_po("V001", gl1046, po="PO-1046", loc="EVN", created=D((9, 26)))

    # ----- 01-13: clean digital invoices ------------------------------------------------------
    l = pick("V001", 6)
    p = make_po("V001", l, loc="WKP", created=D((9, 20)))
    S(1, "greenleaf_clean", doc("V001", l, inv_no="INV-GL-2228", inv_date=D((9, 29)), po=p, loc="WKP"),
      kind="digital_pdf", category="happy_path", title="Clean produce invoice",
      scenario="Text PDF, PO printed, every line matches the PO price and goods receipt.",
      expect=("APPROVE", []))

    l = pick("V002", 5, (2, 10))
    p = make_po("V002", l, loc="LSQ", created=D((9, 15)))
    S(2, "packright_clean", doc("V002", l, inv_no="PR-104871", inv_date=D((9, 24)), po=p, loc="LSQ"),
      kind="digital_pdf", category="happy_path", title="Clean packaging invoice, tax itemised",
      scenario="QuickBooks-style layout; 10.25% sales tax shown as a separate line.", expect=("APPROVE", []))

    l = [L("SVC-N", "Nightly janitorial service - September 2026", "mo", 1850.00, 1),
         L("SVC-HD", "Kitchen hood degrease (quarterly)", "ea", 640.00, 1)]
    p = make_po("V003", l, loc="WKP", created=D((8, 30)))
    S(3, "sparkle_clean", doc("V003", l, inv_no="SCC-2026-0412", inv_date=D((9, 30)), po=p, loc="WKP",
                              service_period="September 2026"),
      kind="digital_pdf", category="happy_path", title="Clean cleaning-services invoice",
      scenario="Letterhead-style services invoice; services are treated as received.", expect=("APPROVE", []))

    ng03 = [L("RNT-COMBI", "Combi oven rental - October 2026", "mo", 4200.00, 1),
            L("RNT-WIC", "Walk-in cooler rental - October 2026", "mo", 3100.00, 1),
            L("RNT-DISH", "Dish machine rental - October 2026", "mo", 1700.00, 1)]
    S(4, "northgate_blanket_within_balance",
      doc("V004", ng03, inv_no="NG-0303", inv_date=D((10, 1)), po="PO-1043", service_period="October 2026"),
      kind="digital_pdf", category="happy_path", title="Third invoice on a split blanket PO, within balance",
      scenario="PO-1043 is $50,000 with $38,000 already billed (NG-0301, NG-0302). This $9,000 invoice fits.",
      expect=("APPROVE", []))

    S(5, "bluewave_recurring_retainer_october",
      doc("V005", bw_ret("October"), inv_no="BW-2026-10", inv_date=D((10, 1)), po="PO-1044",
          service_period="October 2026"),
      kind="digital_pdf", category="edge_matching", title="Recurring retainer: identical amount is NOT a duplicate",
      scenario="Same vendor, same $3,600, same lines as September's BW-2026-09, 30 days apart. Service "
               "period differs (October vs September), so it is a new charge, not a duplicate.",
      expect=("APPROVE", ["RECURRING_CHARGE_NOT_DUPLICATE"]), similar_to="BW-2026-09")

    lm = []
    for wk, day in enumerate([(9, 14), (9, 17), (9, 21), (9, 24), (9, 28)]):
        for i in rnd.sample(range(len(CATALOG["V007"])), 8 if wk < 4 else 6):
            sku, desc, unit, price = CATALOG["V007"][i]
            q = round(rnd.uniform(8, 60), 1) if unit == "lb" else rnd.randint(1, 6)
            lm.append(L(sku, f"{desc} (dlv {day[0]:02d}/{day[1]:02d})", unit, price, q))
    p = make_po("V007", lm, loc="FUL", created=D((9, 10)))
    S(6, "lakeshore_weekly_multipage", doc("V007", lm, inv_no="LM 558213", inv_date=D((9, 30)), po=p),
      kind="digital_pdf", quality=["multi_page", "catch_weight_decimals"], category="happy_path",
      title="Two-page consolidated meat invoice",
      scenario="38 catch-weight lines across five deliveries; table spans two pages, totals on page 2.",
      expect=("APPROVE", []))

    l = pick("V008", 6, (2, 14))
    p = make_po("V008", l, loc="OKP", created=D((9, 28)))
    S(7, "dairy_delivery_ticket", doc("V008", l, inv_no="77812", inv_date=D((10, 2)), po=p, loc="OKP"),
      kind="digital_pdf", quality=["narrow_receipt_format"], category="happy_path",
      title="Narrow delivery-ticket style invoice",
      scenario="Thermal-printer style ticket (3.4in wide) in monospace; invoice number is the ticket number.",
      expect=("APPROVE", []))

    l = pick("V009", 5, (1, 8))
    p = make_po("V009", l, loc="LSQ", created=D((9, 22)))
    S(8, "beverage_clean", doc("V009", l, inv_no="GLBD-90231", inv_date=D((9, 26)), po=p, loc="LSQ"),
      kind="digital_pdf", category="happy_path", title="Clean beverage distributor invoice",
      scenario="Distributor layout with ordered vs shipped columns, all shipped in full.", expect=("APPROVE", []))

    l = [L("PC-MO", "Monthly pest control service - Fulton Market", "mo", 145.00, 1),
         L("PC-FL", "Fly light unit service", "ea", 65.00, 2)]
    p = make_po("V011", l, loc="FUL", created=D((9, 1)))
    S(9, "pest_clean", doc("V011", l, inv_no="PPC-3391", inv_date=D((9, 25)), po=p, service_period="September 2026"),
      kind="digital_pdf", category="happy_path", title="Clean pest-control invoice",
      scenario="Modern minimal layout with a large 'amount due' figure.", expect=("APPROVE", []))

    l = pick("V001", 5)
    p = make_po("V001", l, loc="LSQ", created=D((9, 18)))
    S(10, "greenleaf_name_variant",
      doc("V001", l, inv_no="INV-GL-2219", inv_date=D((9, 19)), po=p, loc="LSQ",
          vendor_over=dict(name="Greenleaf Produce Company", addr=["2400 South Blue Island Avenue", "Chicago IL 60608"])),
      kind="digital_pdf", category="edge_matching", title="Vendor name printed differently",
      scenario="Printed as 'Greenleaf Produce Company' with a reformatted address; same tax ID and bank. "
               "Must match vendor V001 by tax ID / alias, not by exact name.",
      expect=("APPROVE", ["VENDOR_ALIAS_MATCHED"]))

    l = [L("PCUP-2", "Portion cup 2 oz w/ lid, each", "ea", 0.4167, 2400),
         L("TISS-12", "Deli tissue sheets 12x12 (5000/cs)", "cs", 27.80, 4)]
    p = make_po("V002", l, loc="EVN", created=D((9, 16)))
    dd = doc("V002", l, inv_no="PR-104902", inv_date=D((9, 27)), po=p, loc="EVN")
    S(11, "packright_unit_price_rounding", dd, kind="digital_pdf", category="edge_matching",
      title="Fractional unit price (display rounding)",
      scenario="2,400 cups at $0.4167 = $1,000.08. Qty x price must reconcile with sub-cent unit prices "
               "without raising a false arithmetic error.", expect=("APPROVE", []))

    lm_po = from_catalog("V007", [(0, 40), (2, 60), (4, 30)])
    p = make_po("V007", lm_po, loc="WKP", created=D((9, 25)), received={"10442": 30, "20118": 60, "30210": 18})
    lm_inv = [dict(x) for x in lm_po]
    lm_inv[0].update(qty=30, ordered=40)
    lm_inv[2].update(qty=18, ordered=30)
    S(12, "lakeshore_partial_delivery", doc("V007", lm_inv, inv_no="LM 558377", inv_date=D((10, 2)), po=p, loc="WKP"),
      kind="digital_pdf", category="edge_matching", title="Partial delivery billed correctly",
      scenario="Ordered 40 lb tenderloin and 30 lb pork belly, shipped and billed 30 and 18. Billed qty equals "
               "received qty, so it is payable; the PO stays open for the balance.",
      expect=("APPROVE", ["PARTIAL_DELIVERY"]))

    l = pick("V009", 4, (2, 10))
    p = make_po("V009", l, loc="OKP", created=D((9, 23)))
    S(13, "beverage_promo_credit_line",
      doc("V009", l, inv_no="GLBD-90377", inv_date=D((9, 30)), po=p, loc="OKP",
          fees=[L("PROMO", "Promotional allowance - Q3 volume program", "ea", -84.00, 1)]),
      kind="digital_pdf", category="edge_matching", title="Negative promotional line not on the PO",
      scenario="A -$84.00 allowance line has no PO line. Credits reduce what we pay, so they are accepted with a note.",
      expect=("APPROVE", ["UNMATCHED_CREDIT_LINE"]))

    # ----- 14-25: scanned / photographed / handwritten but payable ---------------------------
    l = pick("V001", 5)
    p = make_po("V001", l, loc="OKP", created=D((9, 24)))
    S(14, "greenleaf_scan_clean", doc("V001", l, inv_no="INV-GL-2226", inv_date=D((9, 27)), po=p, loc="OKP"),
      kind="scanned_pdf", quality=["200dpi", "grayscale", "skew 0.8deg"], category="happy_path",
      title="Office-scanner scan of a clean invoice", scenario="No text layer; must be read from the image.",
      expect=("APPROVE", []), fx=[("scan", dict(skew=0.8))])

    l = pick("V002", 4, (2, 9))
    p = make_po("V002", l, loc="FUL", created=D((9, 19)))
    S(15, "packright_scan_skewed", doc("V002", l, inv_no="PR-104890", inv_date=D((9, 26)), po=p),
      kind="scanned_pdf", quality=["skew 3.6deg", "noise", "grayscale"], category="happy_path",
      title="Crooked scan with noise", scenario="Fed into the scanner at an angle; speckle noise.",
      expect=("APPROVE", []), fx=[("scan", dict(skew=-3.6, noise=14, blur=0.7))])

    l = [L("SVC-N", "Nightly janitorial service - September 2026", "mo", 1850.00, 1),
         L("SVC-FW", "Floor strip & wax, dining room", "ea", 425.00, 1)]
    p = make_po("V003", l, loc="LSQ", created=D((8, 29)))
    S(16, "sparkle_fax", doc("V003", l, inv_no="SCC-2026-0419", inv_date=D((9, 30)), po=p, loc="LSQ",
                             service_period="September 2026"),
      kind="fax_pdf", quality=["100dpi", "bitonal", "transmission streaks", "fax header"], category="happy_path",
      title="Faxed invoice", scenario="Black-and-white 100 dpi fax with streaks and a fax header line.",
      expect=("APPROVE", []), fx=[("fax", {})])

    l = pick("V008", 5, (2, 12))
    p = make_po("V008", l, loc="EVN", created=D((9, 29)))
    S(17, "dairy_phone_photo", doc("V008", l, inv_no="77903", inv_date=D((10, 3)), po=p, loc="EVN"),
      kind="photo_jpg", quality=["phone photo", "perspective", "shadow", "wood table background"],
      category="happy_path", title="Phone photo of a delivery ticket (JPG)",
      scenario="Driver's ticket photographed on a table at an angle and emailed as a .jpg.",
      expect=("APPROVE", []), fx=[("photo", dict(strength=1.0, surface="wood")), ("jpeg", dict(q=80))], dpi=420, ext="jpg")

    l = [L("PC-MO", "Monthly pest control service - Wicker Park", "mo", 145.00, 1),
         L("PC-RS", "Rodent bait station replacement", "ea", 18.50, 4)]
    p = make_po("V011", l, loc="WKP", created=D((9, 2)))
    S(18, "pest_phone_photo_pdf", doc("V011", l, inv_no="PPC-3402", inv_date=D((9, 29)), po=p, loc="WKP",
                                      service_period="September 2026"),
      kind="photo_pdf", quality=["phone photo", "perspective", "wooden desk with pen, laptop, mug"], category="happy_path",
      title="Phone photo saved as PDF", scenario="Scanner-app PDF of a photo: one image, no text layer.",
      expect=("APPROVE", []), fx=[("photo", dict(strength=1.0, bg=(92, 96, 102), surface="desk")), ("jpeg", dict(q=72))],
      dpi=220)

    l = pick("V009", 4, (1, 6))
    p = make_po("V009", l, loc="WKP", created=D((9, 25)))
    S(19, "beverage_scan_rotated", doc("V009", l, inv_no="GLBD-90288", inv_date=D((9, 28)), po=p, loc="WKP"),
      kind="scanned_pdf", quality=["rotated 90deg", "grayscale"], category="happy_path",
      title="Page scanned sideways", scenario="Whole page rotated 90 degrees in the scan.",
      expect=("APPROVE", []), fx=[("scan", dict(skew=0.5)), ("rotate90", {})])

    lm2 = []
    for day in [(9, 15), (9, 19), (9, 22), (9, 26)]:
        for i in rnd.sample(range(len(CATALOG["V007"])), 8):
            sku, desc, unit, price = CATALOG["V007"][i]
            q = round(rnd.uniform(6, 45), 1) if unit == "lb" else rnd.randint(1, 5)
            lm2.append(L(sku, f"{desc} (dlv {day[0]:02d}/{day[1]:02d})", unit, price, q))
    p = make_po("V007", lm2, loc="LSQ", created=D((9, 12)))
    S(20, "lakeshore_scan_multipage", doc("V007", lm2, inv_no="LM 558240", inv_date=D((9, 30)), po=p, loc="LSQ"),
      kind="scanned_pdf", quality=["multi_page", "grayscale", "skew"], category="happy_path",
      title="Two-page scanned invoice", scenario="Totals only on page 2; both pages must be read together.",
      expect=("APPROVE", []), fx=[("scan", dict(skew=1.2, page=0)), ("scan", dict(skew=-0.9, page=1))])

    hl = [L("LAB", "Labor - walk-in door hinge", "hr", 95.00, 3), L("PRT-H", "Hinge kit, heavy duty", "ea", 186.00, 1),
          L("PRT-G", "Door gasket 30x78", "ea", 169.00, 1)]
    p = make_po("V010", hl, loc="FUL", created=D((9, 27)))
    S(21, "handyman_handwritten_scan",
      doc("V010", hl, inv_no="0147", inv_date=D((10, 2)), po=p, extra=dict(job="walk-in door")),
      kind="handwritten_scan", quality=["handwritten", "carbon-book form", "scan"], category="happy_path",
      title="Handwritten carbon-book invoice", scenario="Small vendor fills a pre-printed invoice book by hand.",
      expect=("APPROVE", []), fx=[("scan", dict(skew=-1.1, gray=False, noise=6))])

    l = pick("V001", 4)
    p = make_po("V001", l, loc="FUL", created=D((9, 25)))
    S(22, "greenleaf_scan_stamped",
      doc("V001", l, inv_no="INV-GL-2229", inv_date=D((9, 30)), po=p),
      kind="scanned_pdf", quality=["RECEIVED stamp", "handwritten initials", "grayscale"], category="happy_path",
      title="Scan with receiving stamp and initials",
      scenario="Kitchen manager stamped RECEIVED and initialled it before forwarding. Stamps/notes are not invoice data.",
      expect=("APPROVE", []),
      fx=[("stamp", dict(text="RECEIVED  OCT 01 2026", rel=(0.52, 0.30))),
          ("ink", dict(text="ok - M.R.", rel=(0.62, 0.40), angle=8)), ("scan", dict(skew=0.6))])

    l = [L("RNT-FRY", "Countertop fryer rental (catering event)", "ea", 380.00, 2), L("DEL", "Delivery & pickup", "ea", 90.00, 1)]
    p = make_po("V004", l, loc="EVN", created=D((9, 20)))
    S(23, "northgate_scan_coffee_stain", doc("V004", l, inv_no="NG-0298", inv_date=D((9, 27)), po=p, loc="EVN"),
      kind="scanned_pdf", quality=["coffee stain", "fold crease across line items", "colour scan"], category="happy_path",
      title="Stained, folded invoice scan", scenario="Coffee ring over the header and a fold crease across the table.",
      expect=("APPROVE", []),
      fx=[("coffee", dict(rel=(0.70, 0.16), r=170)), ("crease", dict(rel_y=0.41)), ("scan", dict(skew=-0.7, gray=False))])

    S(24, "greenleaf_no_po_handwritten_note",
      doc("V001", gl1046, inv_no="INV-GL-2233", inv_date=D((10, 3)), po=None, loc="EVN"),
      kind="scanned_pdf", quality=["handwritten annotation", "grayscale"], category="edge_matching",
      title="PO number written in pen by staff",
      scenario="Vendor printed no PO; the receiving manager wrote 'PO-1046' on it before scanning. "
               "Handwritten PO must be used, then confirmed against PO-1046's lines.",
      expect=("APPROVE", ["PO_FROM_ANNOTATION"]),
      fx=[("ink", dict(text="PO-1046", rel=(0.125, 0.172), angle=3, size=46, font="kalam")), ("scan", dict(skew=0.9))])

    l = [L("WIFI-S", "Wi-Fi site survey - Logan Square", "ea", 450.00, 1),
         L("AP-INST", "Wireless access point install", "ea", 210.00, 3)]
    p = make_po("V005", l, loc="LSQ", created=D((9, 18)))
    S(25, "bluewave_screenshot_png", doc("V005", l, inv_no="BW-P-1182", inv_date=D((9, 25)), po=p, loc="LSQ"),
      kind="screenshot_png", quality=["crisp image", "no text layer"], category="happy_path",
      title="Invoice sent as a PNG screenshot", scenario="Vendor exported the invoice from their portal as an image.",
      expect=("APPROVE", []), fx=[], dpi=150, ext="png")

    # ----- 26-39: PO & three-way-match edge cases ---------------------------------------------
    ng05 = [L("RNT-WIF", "Walk-in freezer rental - Q4 2026 (prepaid)", "qtr", 11400.00, 1),
            L("DEL", "Delivery, install & removal", "ea", 3600.00, 1)]
    S(26, "northgate_po_overrun",
      doc("V004", ng05, inv_no="NG-0305", inv_date=D((10, 6)), po="PO-1043"),
      kind="digital_pdf", category="edge_matching", title="EC1: split PO overrun",
      scenario="PO-1043 $50,000, $38,000 already billed. This $15,000 invoice alone looks fine but takes the PO "
               "to $53,000 (6% over). Suggest paying the $12,000 remaining and requesting a $3,000 credit note.",
      expect=("HOLD", ["PO_OVERRUN"]))

    ng04 = [L("RNT-BLC", "Blast chiller rental - October 2026", "mo", 3800.00, 1),
            L("RNT-ICE", "Ice machine rental - October 2026", "mo", 2200.00, 1)]
    S(27, "northgate_split_second_in_batch",
      doc("V004", ng04, inv_no="NG-0304", inv_date=D((10, 3)), po="PO-1043", service_period="October 2026"),
      kind="digital_pdf", category="edge_matching", title="Batch race trap: second invoice on the same PO",
      scenario="Alone: $38,000 + $6,000 fits the $50,000 PO. In a batch after file 04 ($9,000) it would reach "
               "$53,000. If both were decided in parallel, both would see $12,000 left and both would pay.",
      expect=("APPROVE", []), expect_batch=("HOLD", ["PO_OVERRUN"]))

    pr_ec4 = from_catalog("V002", [(0, 8), (1, 3), (2, 3), (7, 5)])
    p = make_po("V002", pr_ec4, loc="OKP", created=D((9, 21)))
    S(28, "packright_photo_no_po_tax_inclusive",
      doc("V002", pr_ec4, inv_no="PR-104936", inv_date=D((9, 30)), po=None, loc="OKP", tax_mode="inclusive"),
      kind="photo_pdf", quality=["phone photo", "skewed", "no PO printed", "tax-inclusive prices"],
      category="edge_matching", title="EC4: messy photo, no PO, tax-inclusive - still payable",
      scenario=f"No PO number; unit prices include 10.25% tax. Must infer {p} from vendor + line items, back out "
               "the tax to compare with PO prices, then approve with notes.",
      expect=("APPROVE", ["PO_INFERRED", "TAX_INCLUSIVE_PRICES"]),
      fx=[("photo", dict(strength=1.25, surface="steel")), ("jpeg", dict(q=72))], dpi=220)

    l = pick("V002", 3, (2, 8))
    p = make_po("V002", l, loc="WKP", created=D((9, 20)))
    S(29, "packright_po_typo",
      doc("V002", l, inv_no="PR-104911", inv_date=D((9, 28)), po=p, printed_po=p.replace("1", "l", 1).replace("0", "O"),
          loc="WKP"),
      kind="digital_pdf", category="edge_matching", title="PO number mistyped (letter O for zero)",
      scenario=f"Printed PO '{p.replace('1', 'l', 1).replace('0', 'O')}' does not exist. Lookup fails, line-item "
               f"inference finds {p}; approve with a warning.",
      expect=("APPROVE", ["PO_INFERRED"]))

    l = [L("SVC-N", "Nightly janitorial service - September 2026", "mo", 1850.00, 1)]
    S(30, "sparkle_closed_po", doc("V003", l, inv_no="SCC-2026-0421", inv_date=D((9, 30)), po="PO-1039",
                                   service_period="September 2026"),
      kind="digital_pdf", category="edge_matching", title="Invoice against a closed PO",
      scenario="References PO-1039 (August, closed). Buyer must issue a new PO or reopen.",
      expect=("HOLD", ["PO_INVALID"]))

    l = [L("PC-DR", "Drain fly treatment", "ea", 120.00, 3)]
    S(31, "pest_wrong_vendor_po", doc("V011", l, inv_no="PPC-3419", inv_date=D((10, 1)), po="PO-1046"),
      kind="digital_pdf", category="edge_matching", title="PO belongs to a different vendor",
      scenario="Prints PO-1046, which is GreenLeaf's produce PO. Never pay against another vendor's PO.",
      expect=("HOLD", ["PO_INVALID"]))

    standing = from_catalog("V001", [(0, 6), (2, 4), (9, 3), (12, 4)])
    pa = make_po("V001", standing, loc="WKP", created=D((9, 29)))
    pb = make_po("V001", standing, loc="LSQ", created=D((9, 29)))
    S(32, "greenleaf_ambiguous_po",
      doc("V001", standing, inv_no="INV-GL-2235", inv_date=D((10, 5)), po=None, hide={"ship_to"}),
      kind="digital_pdf", category="edge_matching", title="Two identical open POs, no PO or ship-to printed",
      scenario=f"Standing weekly order: {pa} (Wicker Park) and {pb} (Logan Square) have identical lines. With no PO "
               "and no ship-to, the PO cannot be determined; show both candidates to the AP clerk.",
      expect=("HOLD", ["PO_NOT_IDENTIFIED"]))

    def bump(lines, i, pct):
        out = [dict(x) for x in lines]
        out[i]["price"] = r2(out[i]["price"] * (1 + pct))
        return out

    l = from_catalog("V002", [(3, 6), (5, 10), (8, 4)])
    p = make_po("V002", l, loc="FUL", created=D((9, 22)))
    S(33, "packright_price_within_tolerance", doc("V002", bump(l, 1, 0.015), inv_no="PR-104925", inv_date=D((10, 1)), po=p),
      kind="digital_pdf", category="edge_matching", title="Unit price +1.5% (inside 2% tolerance)",
      scenario="Paper bags billed at $36.69 vs PO $36.15. Inside tolerance: approve, note the variance.",
      expect=("APPROVE", ["PRICE_VARIANCE_WITHIN_TOLERANCE"]))

    l = from_catalog("V002", [(1, 4), (6, 6), (9, 8)])
    p = make_po("V002", l, loc="EVN", created=D((9, 23)))
    S(34, "packright_price_over_tolerance", doc("V002", bump(l, 0, 0.06), inv_no="PR-104931", inv_date=D((10, 2)), po=p, loc="EVN"),
      kind="digital_pdf", category="edge_matching", title="Unit price +6% (outside tolerance)",
      scenario="Cold cups billed at $93.70 vs PO $88.40. Hold for the buyer; suggest a credit note for the difference.",
      expect=("HOLD", ["PRICE_VARIANCE"]))

    l = from_catalog("V002", [(10, 100), (11, 12)])
    l[0]["unit"] = "kit"
    p = make_po("V002", l, loc="WKP", created=D((9, 24)), received={"CUT-K": 80})
    S(35, "packright_billed_more_than_received", doc("V002", l, inv_no="PR-104940", inv_date=D((10, 2)), po=p, loc="WKP"),
      kind="digital_pdf", category="edge_matching", title="Billed 100, only 80 received",
      scenario="Goods receipt shows 80 cutlery kits received; invoice bills 100. Suggest paying for 80.",
      expect=("HOLD", ["QTY_NOT_RECEIVED"]))

    l = pick("V009", 3, (1, 5))
    p = make_po("V009", l, loc="FUL", created=D((9, 27)))
    S(36, "beverage_small_keg_deposit",
      doc("V009", l, inv_no="GLBD-90410", inv_date=D((10, 2)), po=p,
          fees=[L("DEP-KEG", "Keg deposit (refundable)", "ea", 15.00, 2)]),
      kind="digital_pdf", category="edge_matching", title="Small charge not on the PO ($30 keg deposit)",
      scenario="Unplanned $30 line is under the $50 tolerance: approve, flag it.",
      expect=("APPROVE", ["UNMATCHED_LINE_WITHIN_TOLERANCE"]))

    l = pick("V009", 4, (2, 8))
    p = make_po("V009", l, loc="EVN", created=D((9, 27)))
    S(37, "beverage_unplanned_fuel_surcharge",
      doc("V009", l, inv_no="GLBD-90415", inv_date=D((10, 3)), po=p, loc="EVN",
          fees=[L("FSC", "Fuel & delivery surcharge", "ea", 185.00, 1)]),
      kind="digital_pdf", category="edge_matching", title="$185 fuel surcharge not on the PO",
      scenario="Unplanned charge above tolerance. Hold for buyer: accept it or ask the vendor to remove it.",
      expect=("HOLD", ["UNMATCHED_LINE"]))

    l = from_catalog("V007", [(0, 20), (6, 12), (11, 25)])
    p = make_po("V007", l, loc="OKP", created=D((9, 26)))
    inv = [dict(x) for x in l]
    inv[0].update(sku="10443", desc="Beef tenderloin PSMO, PRIME (sub)", price=27.40)
    S(38, "lakeshore_substituted_item", doc("V007", inv, inv_no="LM 558402", inv_date=D((10, 3)), po=p, loc="OKP"),
      kind="digital_pdf", category="edge_matching", title="Substituted item at a higher grade/price",
      scenario="Ordered Choice tenderloin at $18.95/lb; vendor substituted Prime at $27.40/lb. Item does not match "
               "the PO line; needs buyer approval.", expect=("HOLD", ["UNMATCHED_LINE"]))

    po_l = [L("POS-INST", "POS terminal installation", "ea", 385.00, 6), L("NET-CAB", "Network cabling drop", "ea", 145.00, 12),
            L("TRN", "Staff POS training session", "hr", 95.00, 8)]
    p = make_po("V005", po_l, loc="EVN", created=D((9, 8)))
    S(39, "bluewave_bundled_project_line",
      doc("V005", [L("PRJ", "POS rollout project - Evanston, complete per SOW #BW-114", "lot", 4810.00, 1)],
          inv_no="BW-P-1190", inv_date=D((10, 1)), po=p, loc="EVN"),
      kind="digital_pdf", category="edge_matching", title="One bundled line vs an itemised PO",
      scenario="PO has 3 itemised lines ($4,810); invoice bills one lump sum of $4,810. Line-level match is "
               "impossible, total matches exactly: approve with a 'bundled' note.",
      expect=("APPROVE", ["BUNDLED_LINES"]))

    # ----- 40-45: duplicates --------------------------------------------------------------------
    S(40, "greenleaf_exact_duplicate", doc("V001", gl2207, inv_no="INV-GL-2207", inv_date=D((9, 22)), po="PO-1040"),
      kind="digital_pdf", category="edge_duplicate", title="Exact duplicate of a paid invoice",
      scenario="INV-GL-2207 was paid on 2026-09-30 and is re-sent unchanged.",
      expect=("REJECT", ["DUPLICATE", "PO_OVERRUN"]), similar_to="INV-GL-2207")

    S(41, "greenleaf_duplicate_reformatted_number",
      doc("V001", gl2207, inv_no="INV GL 02207", inv_date=D((9, 22)), po="PO-1040",
          notes=["REPRINT - customer copy"]),
      kind="scanned_pdf", quality=["grayscale"], category="edge_duplicate",
      title="Same invoice number, different formatting",
      scenario="'INV GL 02207' normalises to the same number as 'INV-GL-2207' (case, separators, leading zeros).",
      expect=("REJECT", ["DUPLICATE", "PO_OVERRUN"]), fx=[("scan", dict(skew=0.4))], similar_to="INV-GL-2207")

    S(42, "greenleaf_disguised_duplicate_rescan",
      doc("V001", gl2207, inv_no="INV-GL-2231", inv_date=D((10, 1)), po="PO-1040"),
      kind="scanned_pdf", quality=["phone-scanner app", "grayscale"], category="edge_duplicate",
      title="EC2: duplicate in disguise (new number, rescanned)",
      scenario="Same lines and total as paid INV-GL-2207, 9 days later, under a new number. File hash and number "
               "differ; only a content fingerprint catches it. HOLD, not reject: a human confirms.",
      expect=("HOLD", ["PROBABLE_DUPLICATE", "PO_OVERRUN"]),
      fx=[("scan", dict(skew=-1.6, noise=11, blur=0.8))], similar_to="INV-GL-2207")

    l = pick("V002", 4, (2, 9))
    p = make_po("V002", l, loc="LSQ", created=D((9, 25)))
    batch_dup = doc("V002", l, inv_no="PR-104990", inv_date=D((10, 4)), po=p, loc="LSQ")
    S(43, "packright_batch_original", batch_dup, kind="digital_pdf", category="happy_path",
      title="Original of an in-batch duplicate pair", scenario="Normal invoice. File 44 is a copy of it.",
      expect=("APPROVE", []))
    S(44, "packright_batch_duplicate_scan", dict(batch_dup), kind="scanned_pdf", quality=["grayscale"],
      category="edge_duplicate", title="Same invoice arriving twice in one batch",
      scenario="A scan of file 43 (same number). Alone it is payable; in the same batch it must be rejected "
               "because file 43 was decided first.",
      expect=("APPROVE", []), expect_batch=("REJECT", ["DUPLICATE"]), fx=[("scan", dict(skew=1.4))],
      similar_to="PR-104990")

    l = pick("V008", 4, (2, 10))
    p = make_po("V008", l, loc="WKP", created=D((9, 30)))
    S(45, "dairy_paid_stamp_not_paid",
      doc("V008", l, inv_no="77955", inv_date=D((10, 4)), po=p, loc="WKP"),
      kind="scanned_pdf", quality=["PAID stamp", "grayscale"], category="edge_duplicate",
      title="'PAID' stamp on an unpaid invoice",
      scenario="Someone stamped PAID (driver's copy). The ledger, not the stamp, decides: not in the ledger, so payable; "
               "note the stamp.", expect=("APPROVE", ["STAMP_IGNORED"]),
      fx=[("stamp", dict(text="PAID", rel=(0.30, 0.70), angle=14, size=105)), ("scan", dict(skew=0.7))])

    # ----- 46-50: vendor / fraud / currency -----------------------------------------------------
    l = [L("SVC-N", "Nightly janitorial service - September 2026", "mo", 1850.00, 1),
         L("SVC-GT", "Grease trap pump-out", "ea", 295.00, 1)]
    p = make_po("V003", l, loc="EVN", created=D((8, 30)))
    S(46, "sparkle_bank_details_changed",
      doc("V003", l, inv_no="SCC-2026-0425", inv_date=D((9, 30)), po=p, loc="EVN", service_period="September 2026",
          vendor_over=dict(bank=dict(bank="Metro Federal Credit Union", routing="271070999", account="9917002456")),
          notes=["IMPORTANT: We have moved our banking. Please update your records and remit all payments to the "
                 "new account shown above effective immediately."]),
      kind="digital_pdf", category="edge_fraud", title="EC3: bank details changed",
      scenario="Perfect invoice (approved vendor, valid PO, services delivered) but the remit-to account differs from "
               "the vendor master. Classic payment-diversion fraud: verify by phone using the contact on file.",
      expect=("HOLD", ["BANK_DETAILS_CHANGED"]))

    l = pick("V002", 4, (3, 9))
    p = make_po("V002", l, loc="FUL", created=D((9, 26)))
    S(47, "packright_lookalike_vendor",
      doc("V002", l, inv_no="PR-104951", inv_date=D((10, 3)), po=p,
          vendor_over=dict(tax_id="27-3390541", email="billing@packright-payments.com", phone="(708) 555-0919",
                           bank=dict(bank="Sutton Bank", routing="041215999", account="70014839921"))),
      kind="digital_pdf", category="edge_fraud", title="Look-alike vendor (spoofed PackRight)",
      scenario="Name matches PackRight but tax ID has two digits swapped, email domain is different, bank differs. "
               "Real PO number copied from an earlier invoice.",
      expect=("HOLD", ["BANK_DETAILS_CHANGED", "TAX_ID_MISMATCH"]))

    l = [L("LN-NAP", "Napkin rental 20x20 white", "dz", 3.40, 60), L("LN-APR", "Bib apron rental", "ea", 0.85, 120)]
    S(48, "rapidlinen_blocked_vendor",
      doc("V006", l, inv_no="RLS-88214", inv_date=D((9, 30)), po=None, loc="WKP"),
      kind="digital_pdf", category="edge_fraud", title="Blocked vendor",
      scenario="Rapid Linen was blocked on 2026-08-31 (contract terminated). Any new invoice is rejected.",
      expect=("REJECT", ["VENDOR_BLOCKED"]))

    l = [L("FL-CP", "Table centerpiece, seasonal", "ea", 38.00, 18), L("FL-ENT", "Entrance arrangement", "ea", 165.00, 1),
         L("FL-DEL", "Delivery", "ea", 25.00, 1)]
    S(49, "harborview_unknown_vendor",
      doc("X001", l, inv_no="HF-1024", inv_date=D((10, 2)), po=None, loc="FUL"),
      kind="digital_pdf", category="edge_fraud", title="Vendor not in the vendor master",
      scenario="Florist the GM booked directly. Not onboarded: hold and draft an onboarding request (W-9, bank letter).",
      expect=("HOLD", ["VENDOR_NOT_FOUND"]))

    l = [L("MS-LOB", "Live lobster 1.25 lb", "lb", 19.80, 40), L("MS-SCL", "Digby scallops U10", "lb", 31.50, 15),
         L("MS-OYS", "Malpeque oysters 100ct", "cs", 112.00, 2)]
    p = make_po("V012", l, loc="FUL", created=D((9, 25)))
    S(50, "maritime_cad_currency",
      doc("V012", l, inv_no="MSE-24-118", inv_date=D((10, 4)), po=p, currency="CAD"),
      kind="digital_pdf", quality=["DD/MM/YYYY date"], category="edge_document",
      title="Invoice in Canadian dollars",
      scenario="Approved vendor, valid PO, but billed in CAD (C$). Date printed 04/10/2026 means 4 October. "
               "Multi-currency is out of scope: hold for AP to confirm the FX treatment.",
      expect=("HOLD", ["CURRENCY_NOT_SUPPORTED"]))

    # ----- 51-57: document-level problems -------------------------------------------------------
    l = [L("SVC-N", "Nightly janitorial service - September 2026", "mo", 1850.00, 1),
         L("SVC-WIN", "Exterior window cleaning", "ea", 180.00, 1)]
    p = make_po("V003", l, loc="OKP", created=D((8, 31)))
    S(51, "sparkle_missing_invoice_number",
      doc("V003", l, inv_no="SCC-2026-0428", inv_date=D((9, 30)), po=p, loc="OKP", hide={"invoice_no"},
          service_period="September 2026"),
      kind="digital_pdf", category="edge_document", title="No invoice number",
      scenario="Without an invoice number the duplicate check is unsafe. Hold and ask the vendor to reissue.",
      expect=("HOLD", ["MISSING_INVOICE_NUMBER"]))

    l = [L("PC-MO", "Monthly pest control service - Evanston", "mo", 145.00, 1), L("PC-INS", "Follow-up inspection", "ea", 95.00, 1)]
    p = make_po("V011", l, loc="EVN", created=D((9, 3)))
    S(52, "pest_missing_date",
      doc("V011", l, inv_no="PPC-3425", inv_date=D((10, 2)), po=p, loc="EVN", hide={"date"}),
      kind="digital_pdf", category="edge_document", title="No invoice date",
      scenario="Date missing; use the received date and flag it. Everything else matches.",
      expect=("APPROVE", ["DATE_DEFAULTED"]))

    l = [L("LAP-SET", "Laptop setup & imaging", "ea", 120.00, 8), L("M365", "Microsoft 365 Business licences (new)", "user", 12.50, 8)]
    p = make_po("V005", l, loc="FUL", created=D((9, 22)))
    S(53, "bluewave_missing_total",
      doc("V005", l, inv_no="BW-P-1194", inv_date=D((10, 2)), po=p, hide={"total"}),
      kind="digital_pdf", category="edge_document", title="No total printed",
      scenario="Only line items and subtotal are printed. Total is computed from the lines and flagged.",
      expect=("APPROVE", ["TOTAL_COMPUTED"]))

    l = pick("V001", 5)
    p = make_po("V001", l, loc="WKP", created=D((9, 27)))
    S(54, "greenleaf_lines_dont_add_up",
      doc("V001", l, inv_no="INV-GL-2237", inv_date=D((10, 5)), po=p, loc="WKP", total_delta=90.00),
      kind="digital_pdf", category="edge_document", title="Lines do not add up to the printed total",
      scenario="Printed total is $90.00 more than the sum of the lines. Hold and ask the vendor for a corrected invoice.",
      expect=("HOLD", ["ARITHMETIC_MISMATCH"]))

    l = pick("V002", 3, (3, 8))
    p = make_po("V002", l, loc="OKP", created=D((9, 28)))
    S(55, "packright_tax_overcharged",
      doc("V002", l, inv_no="PR-104958", inv_date=D((10, 4)), po=p, loc="OKP", tax_rate_charged=0.125),
      kind="digital_pdf", category="edge_document", title="Tax line does not match the stated rate",
      scenario="Says 'Sales Tax (10.25%)' but the tax amount is 12.5% of the subtotal.",
      expect=("HOLD", ["TAX_MISMATCH"]))

    l = pick("V009", 3, (2, 6))
    p = make_po("V009", l, loc="LSQ", created=D((9, 29)))
    S(56, "beverage_future_dated",
      doc("V009", l, inv_no="GLBD-90433", inv_date=D((12, 15)), po=p, loc="LSQ"),
      kind="digital_pdf", category="edge_document", title="Invoice dated in the future",
      scenario="Dated 15 Dec 2026. Either a typo or pre-billing; hold for AP to confirm before scheduling payment.",
      expect=("HOLD", ["INVALID_DATE"]))

    l = from_catalog("V007", [(1, 30), (8, 4)])
    S(57, "lakeshore_billed_to_other_company",
      doc("V007", l, inv_no="LM 558990", inv_date=D((10, 3)), po="CG-8812", hide={"ship_to"},
          bill_to=["Copperhead Grill LLC", "455 S Main St", "Naperville, IL 60540"]),
      kind="digital_pdf", category="edge_document", title="Invoice addressed to another company",
      scenario="Bill-to is 'Copperhead Grill LLC' (a different customer of the same vendor) with their PO. "
               "Not our liability: reject and tell the vendor.", expect=("REJECT", ["NOT_ADDRESSED_TO_US"]))

    # ----- 58-61: not (exactly) an invoice ----------------------------------------------------
    cn = doc("V002", [L("LID-16", "Return credit: flat lids damaged in transit (ref PR-104512)", "cs", -41.25, 5),
                      L("RSTK", "Restocking fee waived", "ea", 0.00, 1)],
             inv_no="CM-2207", inv_date=D((10, 2)), po="PO-1041", loc="WKP", title="Credit Memo",
             doc_type="credit_note", extra=dict(total_label="CREDIT TOTAL"))
    S(58, "packright_credit_memo", cn, kind="digital_pdf", category="non_invoice", title="Credit memo",
      scenario="Negative amounts against paid invoice PR-104512. Not payable: route to AP to apply the credit.",
      expect=("HOLD", ["CREDIT_NOTE"]))

    q = doc("V004", [L("BLC-40", "Blast chiller 40 lb capacity, purchase", "ea", 14900.00, 1)], inv_no="Q-2026-118",
            inv_date=D((10, 1)), po=None, title="QUOTATION", doc_type="quote",
            notes=["This quotation is valid for 30 days. Not a request for payment."],
            extra=dict(total_label="QUOTE TOTAL"))
    S(59, "northgate_quotation", q, kind="digital_pdf", category="non_invoice", title="Quote sent to the AP inbox",
      scenario="A quotation, not an invoice. Nothing to pay.", expect=("REJECT", ["NOT_AN_INVOICE"]))

    st = doc("V001", [], inv_no="STMT-0930", inv_date=D((9, 30)), title="STATEMENT OF ACCOUNT", doc_type="statement",
             extra=dict(template="statement", rows=[
                 ["09/01/2026", "Balance forward", "", "", "", "0.00"],
                 ["09/22/2026", "INV-GL-2207", "Invoice", "1,242.40", "", "1,242.40"],
                 ["09/29/2026", "INV-GL-2228", "Invoice", "1,734.60", "", "2,977.00"],
                 ["09/30/2026", "ACH 0930-114", "Payment - thank you", "", "1,242.40", "1,734.60"]]))
    st["total"] = 1734.60
    st["truth"].update(total_printed=1734.60, total_true=1734.60, line_items=[])
    S(60, "greenleaf_statement_of_account", st, kind="digital_pdf", category="non_invoice",
      title="Statement of account", scenario="Lists invoices and payments. Used for reconciliation, never paid from.",
      expect=("REJECT", ["NOT_AN_INVOICE"]))

    l1 = pick("V001", 3)
    p1 = make_po("V001", l1, loc="OKP", created=D((9, 28)))
    l2 = pick("V002", 2, (2, 6))
    p2 = make_po("V002", l2, loc="OKP", created=D((9, 28)))
    S(61, "two_invoices_one_pdf",
      [doc("V001", l1, inv_no="INV-GL-2240", inv_date=D((10, 6)), po=p1, loc="OKP"),
       doc("V002", l2, inv_no="PR-105003", inv_date=D((10, 6)), po=p2, loc="OKP")],
      kind="digital_pdf", quality=["2 documents in 1 file"], category="non_invoice",
      title="Two different vendors' invoices merged into one PDF",
      scenario="Someone combined attachments. Hold: split into separate documents before processing.",
      expect=("HOLD", ["MULTIPLE_DOCUMENTS"]))

    # ----- 62-66: hard-to-read and broken files ----------------------------------------------
    l = pick("V008", 4, (2, 10))
    p = make_po("V008", l, loc="LSQ", created=D((10, 1)))
    S(62, "dairy_blurry_unreadable", doc("V008", l, inv_no="77988", inv_date=D((10, 5)), po=p, loc="LSQ"),
      kind="photo_jpg", quality=["severe motion blur", "low resolution"], category="unreadable",
      title="Too blurry to read reliably",
      scenario="Amounts cannot be read with confidence. Must NOT guess: hold and request a clearer copy.",
      expect=("HOLD", ["LOW_CONFIDENCE_EXTRACTION"]),
      fx=[("photo", dict(strength=0.8)), ("blur_heavy", {}), ("jpeg", dict(q=60))], dpi=230, ext="jpg")

    hl2 = [L("LAB", "Labor - ice machine repair", "hr", 95.00, 4), L("PRT-V", "Water inlet valve", "ea", 142.00, 1),
           L("PRT-F", "Filter cartridge", "ea", 54.00, 1)]
    p = make_po("V010", hl2, loc="WKP", created=D((9, 29)))
    S(63, "handyman_handwritten_math_error",
      doc("V010", hl2, inv_no="0152", inv_date=D((10, 4)), po=p, loc="WKP", total_delta=100.00,
          extra=dict(job="ice machine", hand_font="shadows")),
      kind="handwritten_photo", quality=["handwritten (technician, different hand)", "phone photo"], category="edge_document",
      title="Handwritten invoice with an addition error",
      scenario="Lines add to $576.00 but the handwritten total says $676.00. Could be a misread or a real error: hold.",
      expect=("HOLD", ["ARITHMETIC_MISMATCH"]),
      fx=[("photo", dict(strength=0.9, bg=(170, 170, 165), surface="granite")), ("jpeg", dict(q=74))], dpi=260)

    l = [L("SVC-N", "Nightly janitorial service - September 2026", "mo", 1850.00, 1),
         L("SVC-UP", "Upholstery steam clean, booths", "ea", 360.00, 1)]
    p = make_po("V003", l, loc="FUL", created=D((8, 31)))
    S(64, "sparkle_password_protected",
      doc("V003", l, inv_no="SCC-2026-0431", inv_date=D((9, 30)), po=p, service_period="September 2026"),
      kind="encrypted_pdf", quality=["password required to open"], category="unreadable",
      title="Password-protected PDF", scenario="Cannot be opened without a password. Hold; ask vendor for an unprotected copy.",
      expect=("HOLD", ["UNREADABLE_FILE"]), special="encrypt")

    l = pick("V001", 4)
    S(65, "corrupted_download", doc("V001", l, inv_no="INV-GL-2241", inv_date=D((10, 6)), po=None),
      kind="corrupted_pdf", quality=["truncated file"], category="unreadable", title="Corrupted / truncated PDF",
      scenario="Download cut off half-way. Cannot be parsed; hold for AP to get a fresh copy.",
      expect=("HOLD", ["UNREADABLE_FILE"]), special="corrupt")

    hl3 = [L("LAB", "Labor - hood fan belt", "hr", 95.00, 2), L("PRT-B", "Fan belt A-48", "ea", 38.50, 2),
           L("PRT-P", "Pulley set screw kit", "ea", 22.00, 1)]
    p = make_po("V010", hl3, loc="EVN", created=D((10, 1)))
    S(66, "handyman_crumpled_photo",
      doc("V010", hl3, inv_no="0155", inv_date=D((10, 6)), po=p, loc="EVN", extra=dict(job="hood fan", hand_font="nothing")),
      kind="handwritten_photo", quality=["handwritten", "crumpled paper", "phone photo", "shadow"], category="happy_path",
      title="Crumpled handwritten invoice photographed on a counter",
      scenario="Messiest payable input: crumpled carbon copy, photographed with a shadow. Still legible and correct.",
      expect=("APPROVE", []),
      fx=[("photo", dict(strength=1.1, bg=(60, 62, 66), crumple=True, surface="counter")), ("jpeg", dict(q=74))], dpi=260)

    # ----- 67: scenario 46's diverted bank account, but scanned (exercises the bank re-read) ---------
    l = [L("SVC-HD", "Kitchen hood degrease (quarterly)", "ea", 640.00, 1),
         L("SVC-UP", "Upholstery steam clean, booths", "ea", 360.00, 1)]
    p = make_po("V003", l, loc="LSQ", created=D((9, 15)))
    S(67, "sparkle_bank_details_changed_scan",
      doc("V003", l, inv_no="SCC-2026-0436", inv_date=D((10, 2)), po=p, loc="LSQ",
          vendor_over=dict(bank=dict(bank="Metro Federal Credit Union", routing="271070999", account="9917002456")),
          notes=["IMPORTANT: We have moved our banking. Please update your records and remit all payments to the "
                 "new account shown above effective immediately."]),
      kind="scanned_pdf", quality=["200dpi", "grayscale", "skew 0.7deg"], category="edge_fraud",
      title="Bank details changed, scanned copy",
      scenario="Same payment-diversion pattern as file 46 on a different invoice, but scanned: there is no text layer "
               "to check the account against, so a second AI read confirms the account before the hold stands.",
      expect=("HOLD", ["BANK_DETAILS_CHANGED"]), fx=[("scan", dict(skew=0.7))])


# --------------------------------------------------------------------------------------------
# Sanity checks: no accidental near-duplicates, intended ones are declared
# --------------------------------------------------------------------------------------------
def check_no_accidental_duplicates():
    rows = [(s["id"], d["vid"], d["inv_no"], d["inv_date"], d["truth"]["total_true"], s["similar_to"])
            for s in SCEN for d in s["docs"] if d["doc_type"] == "invoice" and d["inv_date"]]
    rows += [(0, e["vendor_id"], e["invoice_number"], date.fromisoformat(e["invoice_date"]), e["total"], None)
             for e in LEDGER]
    problems = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a[1] != b[1] or a[0] == b[0]:
                continue
            close_amt = abs(a[4] - b[4]) <= 0.005 * max(abs(a[4]), abs(b[4]), 1)
            close_date = abs((a[3] - b[3]).days) <= 30
            declared = a[5] in (b[2],) or b[5] in (a[2],) or (a[5] and a[5] == b[5])
            if close_amt and close_date and not declared:
                problems.append((a[:3], b[:3]))
    assert not problems, f"accidental near-duplicates: {problems}"


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------
REASONS = {
    "PO_OVERRUN": "Billed-to-date plus this invoice exceeds the PO total beyond tolerance",
    "PO_INVALID": "Printed PO does not exist, is closed, or belongs to another vendor",
    "PO_NOT_IDENTIFIED": "No PO printed and line-item inference is ambiguous",
    "PO_INFERRED": "(note) PO not printed or mistyped; inferred from vendor + line items",
    "PO_FROM_ANNOTATION": "(note) PO taken from a handwritten annotation and confirmed by line items",
    "PRICE_VARIANCE": "A unit price exceeds the PO price by more than the price tolerance",
    "PRICE_VARIANCE_WITHIN_TOLERANCE": "(note) Unit price differs from PO but within tolerance",
    "QTY_NOT_RECEIVED": "Billed quantity exceeds goods received",
    "PARTIAL_DELIVERY": "(note) Billed qty equals received qty, less than ordered",
    "UNMATCHED_LINE": "A charge or item not on the PO, above tolerance (fees, substitutions)",
    "UNMATCHED_LINE_WITHIN_TOLERANCE": "(note) Small unplanned charge within the total tolerance",
    "UNMATCHED_CREDIT_LINE": "(note) Negative line not on PO; reduces the amount payable",
    "BUNDLED_LINES": "(note) Single lump-sum line matched to an itemised PO by total",
    "RECURRING_CHARGE_NOT_DUPLICATE": "(note) Same amount as a prior invoice but a different service period",
    "DUPLICATE": "Same vendor + normalised invoice number already in the ledger",
    "PROBABLE_DUPLICATE": "Same vendor, near-identical amount, date and lines under a different number",
    "STAMP_IGNORED": "(note) PAID/RECEIVED stamps are not trusted; the ledger decides",
    "BANK_DETAILS_CHANGED": "Remit-to bank account differs from the vendor master",
    "TAX_ID_MISMATCH": "Printed tax ID differs from the vendor master",
    "VENDOR_ALIAS_MATCHED": "(note) Vendor matched via alias / tax ID, not exact name",
    "VENDOR_BLOCKED": "Vendor is blocked in the vendor master",
    "VENDOR_NOT_FOUND": "Vendor not in the vendor master; onboarding required",
    "CURRENCY_NOT_SUPPORTED": "Invoice currency is not USD",
    "MISSING_INVOICE_NUMBER": "No invoice number; duplicate check is unsafe",
    "DATE_DEFAULTED": "(note) No invoice date; received date used",
    "TOTAL_COMPUTED": "(note) No total printed; computed from lines",
    "ARITHMETIC_MISMATCH": "Line items, tax and total do not reconcile",
    "TAX_MISMATCH": "Tax amount does not match the stated tax rate",
    "TAX_INCLUSIVE_PRICES": "(note) Prices include tax; tax backed out before PO comparison",
    "INVALID_DATE": "Invoice dated in the future",
    "NOT_ADDRESSED_TO_US": "Bill-to is a different company",
    "CREDIT_NOTE": "Document is a credit note/memo; apply, do not pay",
    "NOT_AN_INVOICE": "Document is a quote, statement or other non-invoice",
    "MULTIPLE_DOCUMENTS": "File contains more than one invoice",
    "LOW_CONFIDENCE_EXTRACTION": "Key fields could not be read with confidence",
    "UNREADABLE_FILE": "File is encrypted, corrupted or not a readable document",
}


def write_all(out_dir=OUT_DIR, only=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*"):
        f.unlink()
    manifest = []
    for s in SCEN:
        if only and s["id"] not in only:
            continue
        fname = f"{s['id']:02d}_{s['slug']}.{s['ext']}"
        path = out_dir / fname
        if s["special"] == "encrypt":
            pdf = render_docs(s["docs"], encrypt=lambda: StandardEncryption("sparkle2026", ownerPassword="own3r", canPrint=1))
            path.write_bytes(pdf)
        elif s["special"] == "corrupt":
            pdf = render_docs(s["docs"])
            path.write_bytes(pdf[: int(len(pdf) * 0.45)] + b"\n%%EOF-broken\x00\x13")
        else:
            pdf = render_docs(s["docs"])
            if not s["fx"] and s["ext"] == "pdf":
                path.write_bytes(pdf)
            else:
                pages = rasterize(pdf, s["dpi"])
                in_long = max(pages[0].size)
                if s["kind"] in ("scanned_pdf",) and not s["fx"]:
                    s["fx"] = [("scan", {})]
                if s["kind"] == "handwritten_scan" and not s["fx"]:
                    s["fx"] = [("scan", dict(gray=False))]
                pages = apply_fx(pages, s["fx"], seed=s["id"])
                if s["ext"] == "pdf":  # keep the physical page size when an effect changed the pixel size
                    write_images_pdf(path, pages, s["dpi"] * max(pages[0].size) / in_long)
                elif s["ext"] == "jpg":
                    pages[0].save(path, "JPEG", quality=82)
                else:
                    pages[0].save(path, "PNG", optimize=True)
        stamps = [kw["text"] for name, kw in s["fx"] if name == "stamp"]
        inks = [kw["text"] for name, kw in s["fx"] if name == "ink"]
        hand_po = next((t for t in inks if t.upper().startswith("PO-")), None)
        legible = not (s["category"] == "unreadable" and s["kind"].startswith("photo"))
        truth = []
        for d in s["docs"]:
            t = dict(d["truth"])
            t.update(document_count=len(s["docs"]), stamps=stamps, po_number_handwritten=hand_po, legible=legible)
            truth.append(t)
        manifest.append(dict(
            id=s["id"], file=fname, kind=s["kind"], quality=s["quality"], category=s["category"],
            title=s["title"], scenario=s["scenario"],
            expected=dict(alone=dict(decision=s["expect"][0], reasons=s["expect"][1]),
                          in_batch=dict(decision=s["expect_batch"][0], reasons=s["expect_batch"][1])),
            vendor=s["docs"][0]["v"]["name"], vendor_id=s["docs"][0]["truth"]["vendor_id"],
            similar_to=s["similar_to"], truth=truth[0] if len(truth) == 1 else truth))
        print(f"  {fname:<52} {s['expect'][0]:<8} {', '.join(s['expect'][1])}")
    return manifest


def write_seed():
    (ROOT / "data").mkdir(exist_ok=True)
    vendors = []
    for vid, v in VENDORS.items():
        vendors.append(dict(id=vid, name=v["name"], aliases=v["aliases"], tax_id=v["tax_id"], address=v["addr"],
                            phone=v["phone"], email=v["email"], bank=v["bank"], status=v["status"],
                            block_reason=v.get("block_reason"), category=v["category"], taxable=v["taxable"],
                            payment_terms=v["terms"][0]))
    seed = dict(
        company=dict(name=BUYER[0], bill_to_names=[BUYER[0], "Copperleaf Restaurant Grp", "Copperleaf"],
                     locations={k: v for k, v in LOCATIONS.items()}, base_currency="USD", tax_rate=TAX_RATE,
                     as_of=str(TODAY)),
        policy=dict(price_tolerance_pct=2.0, total_tolerance_pct=1.0, total_tolerance_abs=50.0,
                    duplicate_window_days=30, fuzzy_dup_amount_pct=0.5, fuzzy_dup_line_similarity=0.8,
                    po_infer_min_score=0.75, po_infer_margin=0.10, clerk_minutes_per_invoice=12),
        vendors=vendors, purchase_orders=list(POS.values()), goods_receipts=RECEIPTS, invoice_ledger=LEDGER)
    (ROOT / "data" / "seed.json").write_text(json.dumps(seed, indent=2))


def write_markdown(manifest):
    cats = {}
    for m in manifest:
        cats.setdefault(m["category"], 0)
        cats[m["category"]] += 1
    dec = {}
    for m in manifest:
        dec[m["expected"]["alone"]["decision"]] = dec.get(m["expected"]["alone"]["decision"], 0) + 1
    kinds = {}
    for m in manifest:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    out = ["# InvoiceDesk test invoices", "",
           f"{len(manifest)} synthetic files generated by `scripts/make_fixtures.py` (deterministic). "
           "The procurement data they are checked against is `data/seed.json`. The full answer key, including "
           "every ground-truth field, is `manifest.json`.", "",
           "**Expected (alone)** = processed by itself on a fresh copy of the seed data. "
           "**Expected (batch)** = the whole folder uploaded at once and decided in file order; it differs only "
           "where the order matters (marked in bold).", "",
           "## Mix", "",
           "| By input type | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(kinds.items())] + [
           "", "| By category | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(cats.items())] + [
           "", "| By expected decision (alone) | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(dec.items())] + [
           "", "## Files", "",
           "| # | File | Input type | Quality / noise | Vendor | Scenario | Expected (alone) | Expected (batch) |",
           "|---|---|---|---|---|---|---|---|"]
    for m in manifest:
        a, b = m["expected"]["alone"], m["expected"]["in_batch"]
        fa = f"{a['decision']}" + (f" ({', '.join(a['reasons'])})" if a["reasons"] else "")
        fb = f"{b['decision']}" + (f" ({', '.join(b['reasons'])})" if b["reasons"] else "")
        if fb != fa:
            fb = f"**{fb}**"
        out.append(f"| {m['id']} | `{m['file']}` | {m['kind']} | {', '.join(m['quality']) or '-'} | {m['vendor']} | "
                   f"**{m['title']}.** {m['scenario']} | {fa} | {fb} |")
    out += ["", "## Reason codes", "", "Codes marked (note) never block payment on their own.", "",
            "| Code | Meaning |", "|---|---|"] + [f"| `{k}` | {v} |" for k, v in REASONS.items()]
    out += ["", "## Notes for testers", "",
            "- File 64 password (to inspect it manually): `sparkle2026`. The system is expected NOT to know it.",
            "- Scenarios depend on seeded history: INV-GL-2207 (paid), NG-0301/NG-0302 on PO-1043, "
            "BW-2026-09 on PO-1044, PR-104512 (paid), closed PO-1039.",
            "- To swap in real invoices: add the vendor to `vendors`, its PO to `purchase_orders` and receipts to "
            "`goods_receipts` in `data/seed.json`; the pipeline reads nothing else."]
    (ROOT / "fixtures" / "MANIFEST.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    import sys
    build()
    check_no_accidental_duplicates()
    if "--samples" in sys.argv:  # render a review pack only; leaves fixtures/invoices and the answer key untouched
        ids = {int(x) for x in sys.argv[sys.argv.index("--samples") + 1].split(",")}
        sample_dir = ROOT / "fixtures" / "samples"
        manifest = write_all(sample_dir, ids)
        (sample_dir / "SAMPLES.md").write_text("\n".join(
            ["| # | File | Input type | Quality / noise | Scenario | Expected (alone) |", "|---|---|---|---|---|---|"]
            + [f"| {m['id']} | `{m['file']}` | {m['kind']} | {', '.join(m['quality']) or '-'} | **{m['title']}.** "
               f"{m['scenario']} | {m['expected']['alone']['decision']} {', '.join(m['expected']['alone']['reasons'])} |"
               for m in manifest]), encoding="utf-8")
        print(f"\n{len(manifest)} samples -> {sample_dir}")
        sys.exit(0)
    manifest = write_all()
    (ROOT / "fixtures" / "manifest.json").write_text(json.dumps(
        dict(reason_codes=REASONS, files=manifest), indent=2, default=str))
    write_seed()
    odir = ROOT / "fixtures" / "originals"
    odir.mkdir(exist_ok=True)
    for inv_no, d in ORIGINALS.items():
        (odir / f"{inv_no}.pdf").write_bytes(render_docs([d]))
    write_markdown(manifest)
    print(f"\n{len(manifest)} files -> {OUT_DIR}")
