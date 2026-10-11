"""Run the fixture test suite and print a scorecard.

    PYTHONIOENCODING=utf-8 uv run python scripts/run_eval.py            # real Gemini
    PYTHONIOENCODING=utf-8 uv run python scripts/run_eval.py --truth    # offline answer-key extractor
    ... --ids 1,26,42 --export-cache                                    # subset; save the Gemini cache for deploy
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import db, evaluate  # noqa: E402
from app.extract import GeminiExtractor, load_env  # noqa: E402
from app.truth import TruthExtractor  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", action="store_true")
    ap.add_argument("--ids")
    ap.add_argument("--export-cache", action="store_true")
    a = ap.parse_args()
    load_env(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    manifest = json.loads((ROOT / "fixtures" / "manifest.json").read_text(encoding="utf-8"))["files"]
    if a.ids:
        manifest = [m for m in manifest if str(m["id"]) in a.ids.split(",")]
    seed = json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))
    store = db.connect(str(ROOT / "data" / ("eval_truth.db" if a.truth else "eval_store.db")))
    ex = TruthExtractor(manifest) if a.truth else GeminiExtractor()
    rep = asyncio.run(evaluate.evaluate(manifest, ROOT / "fixtures" / "invoices", seed, store, ex))
    (ROOT / "data" / "eval_report.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(f"\nDecisions alone: {rep['alone']['passed']}/{rep['alone']['total']}   "
          f"in batch: {rep['batch']['passed']}/{rep['batch']['total']}   ({rep['elapsed_s']}s, {rep['model']})")
    print("Field accuracy: " + "  ".join(f"{k} {v['rate']:.0%}" for k, v in rep["fields"].items()))
    for r in rep["rows"]:
        if not (r["pass_alone"] and r["pass_batch"]):
            print(f"  FAIL {r['file']}: expected {r['expected_alone']} got {r['actual_alone']} | "
                  f"batch expected {r['expected_batch']} got {r['actual_batch']}")
    if a.export_cache and not a.truth:
        import hashlib
        out = {}
        for m in manifest:
            sha = hashlib.sha256((ROOT / "fixtures" / "invoices" / m["file"]).read_bytes()).hexdigest()
            hit = db.cache_get(store, sha)
            if hit:
                out[sha] = hit
        (ROOT / "data" / "extraction_cache.json").write_text(json.dumps(out), encoding="utf-8")
        print(f"exported {len(out)} cached extractions -> data/extraction_cache.json")


if __name__ == "__main__":
    main()
