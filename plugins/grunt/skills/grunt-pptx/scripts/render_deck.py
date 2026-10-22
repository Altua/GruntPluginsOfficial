#!/usr/bin/env python3
"""Render a saved PPTX to PDF (and PNG pages when PyMuPDF is installed) with LibreOffice.

This checks the assembled deck, not individual assets. LibreOffice results establish
LibreOffice compatibility only; inspect the deck in PowerPoint separately when the
recipient uses PowerPoint.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.com",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.com",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
)


def find_soffice(explicit=None):
    if explicit:
        return explicit
    for name in ("soffice.com", "soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    return next((path for path in CANDIDATES if os.path.exists(path)), None)


def render(pptx, output_dir, soffice=None, dpi=110):
    pptx, output_dir = Path(pptx).resolve(), Path(output_dir).resolve()
    executable = find_soffice(soffice)
    if not executable:
        raise RuntimeError("LibreOffice was not found. Install it or pass --soffice with its path.")
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [executable, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(output_dir), str(pptx)],
        capture_output=True, text=True, timeout=300)
    pdf = output_dir / (pptx.stem + ".pdf")
    if completed.returncode != 0 or not pdf.exists():
        raise RuntimeError(f"LibreOffice conversion failed (exit {completed.returncode}). "
                           "Close other LibreOffice windows and retry.")
    result = {"renderer": "LibreOffice", "pdf": str(pdf), "pages": []}
    try:
        import pymupdf
    except ImportError:
        result["note"] = "Install PyMuPDF for PNG pages, or read the PDF directly."
        return result
    with pymupdf.open(pdf) as document:
        for index, page in enumerate(document, start=1):
            png = output_dir / f"{pptx.stem}-slide{index:02d}.png"
            page.get_pixmap(dpi=dpi).save(png)
            result["pages"].append(str(png))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--soffice", help="Path to soffice (soffice.com on Windows)")
    parser.add_argument("--dpi", type=int, default=110)
    args = parser.parse_args()
    try:
        print(json.dumps(render(args.pptx, args.output_dir, args.soffice, args.dpi), indent=2))
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        sys.exit(f"ERROR: {error}")


if __name__ == "__main__":
    main()
