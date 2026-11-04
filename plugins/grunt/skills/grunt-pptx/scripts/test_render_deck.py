"""render_deck.py with PowerPoint and LibreOffice stood in for: hand-off, fallback and failures."""
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
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


class Programs:
    """Answers subprocess.run for PowerShell (PowerPoint), soffice and taskkill."""

    def __init__(self, powerpoint=0, pages=2):
        self.powerpoint, self.pages, self.calls = powerpoint, pages, []

    def __call__(self, command, **kwargs):
        program = Path(command[0]).name.lower()
        self.calls.append(program)
        if program == "powershell.exe":
            if self.powerpoint == "timeout":
                raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
            if self.powerpoint != 0:
                return subprocess.CompletedProcess(command, self.powerpoint, "", "Class not registered\n")
            out = Path(kwargs["env"]["GRUNT_RENDER_DIR"])
            (out / "deck.pdf").write_bytes(pdf_bytes(self.pages))
            for index in range(1, self.pages + 1):
                (out / f"slide{index:03d}.png").write_bytes(PNG_SIGNATURE)
            return subprocess.CompletedProcess(command, 0, "", "")
        if program == "taskkill":
            return subprocess.CompletedProcess(command, 0, "", "")
        outdir = Path(command[command.index("--outdir") + 1])
        (outdir / (Path(command[-1]).stem + ".pdf")).write_bytes(pdf_bytes(self.pages))
        return subprocess.CompletedProcess(command, 0, "", "")


class RenderDeckTests(unittest.TestCase):
    def render(self, tmp, programs, platform="win32", **options):
        pptx = Path(tmp) / "deck.pptx"
        pptx.write_bytes(b"")
        with ExitStack() as stack:
            stack.enter_context(patch.object(render_deck.subprocess, "run", side_effect=programs))
            stack.enter_context(patch.object(render_deck.sys, "platform", platform))
            stack.enter_context(patch.object(render_deck.shutil, "which",
                                             side_effect=lambda name: name if name == "powershell.exe" else None))
            stack.enter_context(patch.object(render_deck, "_powerpoint_pids", side_effect=options.pop("pids", None)
                                             or (lambda: set())))
            return render_deck.render(pptx, Path(tmp) / "render", soffice="soffice", **options)

    def test_powerpoint_writes_the_pdf_and_one_png_per_slide(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.render(tmp, Programs(pages=2))
            self.assertEqual(result["renderer"], "PowerPoint")
            self.assertTrue(Path(result["pdf"]).is_file())
            self.assertEqual([Path(page).name for page in result["pages"]], ["deck-slide01.png", "deck-slide02.png"])
            self.assertEqual([path.name for path in (Path(tmp) / "render").iterdir() if path.is_dir()], [])

    def test_unavailable_powerpoint_falls_back_to_libreoffice(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs = Programs(powerpoint=render_deck.POWERPOINT_UNAVAILABLE, pages=1)
            result = self.render(tmp, programs)
            self.assertEqual(result["renderer"], "LibreOffice")
            self.assertIn("could not be started", result["powerpoint_error"])
            self.assertEqual(Path(result["pages"][0]).read_bytes()[:8], PNG_SIGNATURE)

    def test_a_deck_powerpoint_cannot_render_is_an_error_not_a_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs = Programs(powerpoint=1)
            with self.assertRaisesRegex(RuntimeError, "could not render the deck"):
                self.render(tmp, programs)
            self.assertEqual(programs.calls, ["powershell.exe"])

    def test_timeout_stops_only_a_powerpoint_this_run_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs = Programs(powerpoint="timeout")
            killed = []
            original = programs.__call__

            def record(command, **kwargs):
                if Path(command[0]).name.lower() == "taskkill":
                    killed.append(command[2])
                return original(command, **kwargs)

            with self.assertRaises(render_deck.PowerPointUnavailable):
                self.render(tmp, record, renderer="powerpoint", pids=[{100}, {100, 200}])
            self.assertEqual(killed, ["200"])

    def test_libreoffice_only_off_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs = Programs(pages=1)
            result = self.render(tmp, programs, platform="linux")
            self.assertEqual(result["renderer"], "LibreOffice")
            self.assertNotIn("powerpoint_error", result)
            self.assertNotIn("powershell.exe", programs.calls)

    def test_libreoffice_without_pypdfium2_returns_the_pdf_and_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs = Programs(pages=1)
            with patch.dict(sys.modules, {"pypdfium2": None}):
                result = self.render(tmp, programs, renderer="libreoffice")
            self.assertTrue(Path(result["pdf"]).is_file())
            self.assertEqual(result["pages"], [])
            self.assertIn("pypdfium2", result["note"])

    def test_failed_libreoffice_conversion_is_reported(self):
        def failing(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, "", "")
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(RuntimeError, "conversion failed"):
            self.render(tmp, failing, renderer="libreoffice")

    def test_missing_both_renderers_names_both(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(render_deck, "find_soffice", return_value=None), \
                self.assertRaisesRegex(RuntimeError, "could not be started.*LibreOffice was not found"):
            self.render(tmp, Programs(powerpoint=render_deck.POWERPOINT_UNAVAILABLE))


if __name__ == "__main__":
    unittest.main()
