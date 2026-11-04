"""render_deck.py with LibreOffice stood in for: PDF hand-off, PNG pages and failures."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pypdfium2

import render_deck

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def pdf_bytes(pages):
    with tempfile.TemporaryDirectory() as tmp:
        document = pypdfium2.PdfDocument.new()
        for _ in range(pages):
            document.new_page(960, 540)
        path = Path(tmp) / "deck.pdf"
        document.save(str(path))
        document.close()
        return path.read_bytes()


def fake_soffice(pdf):
    """Answer `soffice --convert-to pdf --outdir <dir> <deck>` by writing the given PDF."""
    def run(command, **kwargs):
        outdir = Path(command[command.index("--outdir") + 1])
        (outdir / (Path(command[-1]).stem + ".pdf")).write_bytes(pdf)
        return subprocess.CompletedProcess(command, 0, "", "")
    return run


class RenderDeckTests(unittest.TestCase):
    def render(self, tmp, run):
        pptx = Path(tmp) / "deck.pptx"
        pptx.write_bytes(b"")
        with patch.object(render_deck.subprocess, "run", side_effect=run):
            return render_deck.render(pptx, Path(tmp) / "render", soffice="soffice")

    def test_writes_the_pdf_and_one_png_per_slide(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.render(tmp, fake_soffice(pdf_bytes(2)))
            self.assertEqual(result["renderer"], "LibreOffice")
            self.assertTrue(Path(result["pdf"]).is_file())
            self.assertEqual([Path(page).name for page in result["pages"]], ["deck-slide01.png", "deck-slide02.png"])
            for page in result["pages"]:
                self.assertEqual(Path(page).read_bytes()[:8], PNG_SIGNATURE)

    def test_without_pypdfium2_returns_the_pdf_and_a_note(self):
        pdf = pdf_bytes(1)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"pypdfium2": None}):
            result = self.render(tmp, fake_soffice(pdf))
            self.assertTrue(Path(result["pdf"]).is_file())
            self.assertEqual(result["pages"], [])
            self.assertIn("pypdfium2", result["note"])

    def test_failed_conversion_is_reported(self):
        def failing(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, "", "")
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(RuntimeError, "conversion failed"):
            self.render(tmp, failing)

    def test_missing_libreoffice_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(render_deck, "find_soffice", return_value=None), \
                self.assertRaisesRegex(RuntimeError, "LibreOffice was not found"):
            render_deck.render(Path(tmp) / "deck.pptx", Path(tmp) / "render")


if __name__ == "__main__":
    unittest.main()
