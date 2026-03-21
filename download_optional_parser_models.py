#!/usr/bin/env python
"""
Optional parser warmup script.

Purpose:
1) Verify optional parser dependencies can be imported.
2) Trigger model/resource preparation for Pix2Text if possible.
3) Print actionable diagnostics without crashing the main service.
"""

from __future__ import annotations

import traceback


def check_marker_pdf() -> bool:
    try:
        import importlib

        importlib.import_module("marker.converters.pdf")
        importlib.import_module("marker.models")
        print("[OK] PDF Marker import check passed")
        return True
    except Exception as exc:
        print(f"[WARN] PDF Marker unavailable: {exc}")
        return False


def warmup_pix2text() -> bool:
    try:
        from pix2text import Pix2Text

        print("[INFO] Pix2Text import check passed")
        # Constructing Pix2Text triggers internal model/resource preparation.
        # If network/model path is unavailable, this will raise and provide details.
        Pix2Text()
        print("[OK] Pix2Text init check passed")
        return True
    except Exception as exc:
        print(f"[WARN] Pix2Text init failed: {exc}")
        print("[HINT] Common causes:")
        print("       1) Missing optional deps (try: pip install -r requirements.optional-parser.txt)")
        print("       2) Torch/Optimum mismatch")
        print("       3) Layout model download failed or local model file missing")
        print("[TRACE]", traceback.format_exc(limit=2).strip())
        return False


def main() -> int:
    print("=== Optional Parser Warmup ===")
    marker_ok = check_marker_pdf()
    pix_ok = warmup_pix2text()

    print("=== Summary ===")
    print(f"PDF Marker: {'OK' if marker_ok else 'UNAVAILABLE'}")
    print(f"Pix2Text: {'OK' if pix_ok else 'UNAVAILABLE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
