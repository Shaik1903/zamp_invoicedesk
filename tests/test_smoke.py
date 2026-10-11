from tests.conftest import FIX_DIR, MANIFEST, SEED


def test_fixtures_and_seed_present():
    assert len(MANIFEST) == 67
    assert len(SEED["vendors"]) == 12
    assert all((FIX_DIR / m["file"]).exists() for m in MANIFEST)
