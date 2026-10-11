from tests.conftest import FIX_DIR, MAN_BY_FILE, ROOT


def t(f):
    x = MAN_BY_FILE[f]["truth"]
    return x[0] if isinstance(x, list) else x


def test_new_truth_keys():
    assert t("24_greenleaf_no_po_handwritten_note.pdf")["po_number_handwritten"] == "PO-1046"
    assert t("45_dairy_paid_stamp_not_paid.pdf")["stamps"] == ["PAID"]
    assert t("22_greenleaf_scan_stamped.pdf")["stamps"] == ["RECEIVED  OCT 01 2026"]
    assert t("61_two_invoices_one_pdf.pdf")["document_count"] == 2
    assert t("55_packright_tax_overcharged.pdf")["tax_rate_printed"] == 0.1025
    assert t("01_greenleaf_clean.pdf")["tax_rate_printed"] is None
    assert t("62_dairy_blurry_unreadable.jpg")["legible"] is False
    assert t("17_dairy_phone_photo.jpg")["legible"] is True


def test_fixture_67_is_a_scanned_bank_change():
    m = MAN_BY_FILE["67_sparkle_bank_details_changed_scan.pdf"]
    assert m["kind"] == "scanned_pdf" and m["vendor_id"] == "V003"
    assert m["expected"]["alone"] == m["expected"]["in_batch"] == {"decision": "HOLD", "reasons": ["BANK_DETAILS_CHANGED"]}
    assert t(m["file"])["remit_bank_account"] == "9917002456" and t(m["file"])["po_number_printed"] == "PO-1151"


def test_shipped_read_cache_covers_every_readable_test_invoice():
    # The deployed demo relies on these pre-read results; a regenerated invoice changes its fingerprint and would
    # silently fall back to a slow live read on the server.
    import hashlib
    import json
    cache = json.loads((ROOT / "data" / "extraction_cache.json").read_text(encoding="utf-8"))
    unreadable = {"64_sparkle_password_protected.pdf", "65_corrupted_download.pdf"}  # never reach the AI
    missing = [f.name for f in sorted(FIX_DIR.iterdir())
               if f.name not in unreadable and hashlib.sha256(f.read_bytes()).hexdigest() not in cache]
    assert not missing, f"re-export data/extraction_cache.json; stale for {len(missing)} files, e.g. {missing[:3]}"
