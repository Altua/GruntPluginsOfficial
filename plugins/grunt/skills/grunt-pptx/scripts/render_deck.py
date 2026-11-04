#!/usr/bin/env python3
"""Render a saved PPTX to PDF and PNG pages, with PowerPoint or LibreOffice.

On Windows with PowerPoint installed, PowerPoint renders the deck: the renderer the
recipient uses. It is driven through PowerShell, opens the deck read-only without a
window, and leaves an instance the user already had open running. Otherwise, or when
PowerPoint fails, LibreOffice renders it (PNG pages need pypdfium2). LibreOffice
results establish LibreOffice compatibility only. This checks the assembled deck,
not individual assets.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.com",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.com",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
)
TIMEOUT_SECONDS = 300
POWERPOINT_UNAVAILABLE = 3


class PowerPointUnavailable(RuntimeError):
    """PowerPoint could not be used at all, so another renderer may stand in.
    A deck PowerPoint opens but cannot render is an error of the deck, not this."""

# Paths arrive in environment variables, so nothing from the caller is parsed as script.
POWERPOINT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$running = @(Get-Process POWERPNT -ErrorAction SilentlyContinue).Count -gt 0
try { $app = New-Object -ComObject PowerPoint.Application }
catch { [Console]::Error.WriteLine($_.Exception.Message); exit 3 }  # PowerPoint unavailable
$alerts = $app.DisplayAlerts
$deck = $null
try {
    $app.DisplayAlerts = 1  # ppAlertsNone
    $deck = $app.Presentations.Open($env:GRUNT_RENDER_PPTX, -1, 0, 0)  # read-only, untitled off, no window
    $deck.SaveAs((Join-Path $env:GRUNT_RENDER_DIR 'deck.pdf'), 32)  # ppSaveAsPDF
    $dpi = [int]$env:GRUNT_RENDER_DPI
    $width = [int][Math]::Round($deck.PageSetup.SlideWidth / 72 * $dpi)
    $height = [int][Math]::Round($deck.PageSetup.SlideHeight / 72 * $dpi)
    foreach ($slide in $deck.Slides) {
        $slide.Export((Join-Path $env:GRUNT_RENDER_DIR ('slide{0:D3}.png' -f $slide.SlideIndex)), 'PNG', $width, $height)
    }
} finally {
    if ($deck) { $deck.Saved = -1; $deck.Close() }
    $app.DisplayAlerts = $alerts
    if (-not $running -and $app.Presentations.Count -eq 0) { $app.Quit() }
}
"""


def find_soffice(explicit=None):
    if explicit:
        return explicit
    for name in ("soffice.com", "soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    return next((path for path in CANDIDATES if os.path.exists(path)), None)


def _powerpoint_pids():
    listed = subprocess.run(["tasklist", "/FI", "IMAGENAME eq POWERPNT.EXE", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, timeout=30).stdout
    return {int(row[1]) for row in csv.reader(listed.splitlines()) if len(row) > 1 and row[1].isdigit()}


def render_with_powerpoint(pptx, output_dir, dpi):
    powershell = shutil.which("powershell.exe")
    if sys.platform != "win32" or not powershell:
        raise PowerPointUnavailable("PowerPoint rendering needs Windows.")
    with tempfile.TemporaryDirectory(prefix=".grunt-render-", dir=output_dir) as temporary:
        env = dict(os.environ, GRUNT_RENDER_PPTX=str(pptx), GRUNT_RENDER_DIR=temporary, GRUNT_RENDER_DPI=str(dpi))
        before = _powerpoint_pids()
        try:
            completed = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", POWERPOINT_SCRIPT],
                capture_output=True, text=True, env=env, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # Stop only a PowerPoint this run started; an instance the user had open stays.
            for pid in _powerpoint_pids() - before:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=30)
            raise PowerPointUnavailable("PowerPoint did not finish in time (a dialog may be open in PowerPoint).") from None
        reason = next((line.strip() for line in completed.stderr.splitlines() if line.strip()), "no error text")[:300]
        if completed.returncode == POWERPOINT_UNAVAILABLE:
            raise PowerPointUnavailable(f"PowerPoint could not be started: {reason}")
        if completed.returncode != 0:
            raise RuntimeError(f"PowerPoint could not render the deck: {reason}")
        pages = sorted(Path(temporary).glob("slide*.png"))
        if not (Path(temporary) / "deck.pdf").is_file() or not pages:
            raise RuntimeError("PowerPoint did not write the PDF and slide images.")
        pdf = output_dir / (pptx.stem + ".pdf")
        os.replace(Path(temporary) / "deck.pdf", pdf)
        result = {"renderer": "PowerPoint", "pdf": str(pdf), "pages": []}
        for index, page in enumerate(pages, start=1):
            png = output_dir / f"{pptx.stem}-slide{index:02d}.png"
            os.replace(page, png)
            result["pages"].append(str(png))
    return result


def render_with_libreoffice(pptx, output_dir, soffice, dpi):
    executable = find_soffice(soffice)
    if not executable:
        raise RuntimeError("LibreOffice was not found. Install it or pass --soffice with its path.")
    pdf = output_dir / (pptx.stem + ".pdf")
    with tempfile.TemporaryDirectory(prefix=".grunt-render-", dir=output_dir) as temporary:
        completed = subprocess.run(
            [executable, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", temporary, str(pptx)],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
        converted_pdf = Path(temporary) / pdf.name
        if completed.returncode != 0 or not converted_pdf.is_file():
            raise RuntimeError(f"LibreOffice conversion failed (exit {completed.returncode}). "
                               "Close other LibreOffice windows and retry.")
        os.replace(converted_pdf, pdf)
    result = {"renderer": "LibreOffice", "pdf": str(pdf), "pages": []}
    try:
        import pypdfium2
    except ImportError:
        result["note"] = "Install the skill's requirements.txt (pypdfium2) for PNG pages, or read the PDF directly."
        return result
    document = pypdfium2.PdfDocument(str(pdf))
    try:
        for index, page in enumerate(document, start=1):
            png = output_dir / f"{pptx.stem}-slide{index:02d}.png"
            page.render(scale=dpi / 72).to_pil().save(png)
            result["pages"].append(str(png))
    finally:
        document.close()
    return result


def render(pptx, output_dir, soffice=None, dpi=110, renderer="auto"):
    pptx, output_dir = Path(pptx).resolve(), Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    powerpoint_error = None
    if renderer == "powerpoint" or (renderer == "auto" and sys.platform == "win32"):
        try:
            return render_with_powerpoint(pptx, output_dir, dpi)
        except PowerPointUnavailable as error:
            if renderer == "powerpoint":
                raise
            powerpoint_error = str(error)
    try:
        result = render_with_libreoffice(pptx, output_dir, soffice, dpi)
    except RuntimeError as error:
        raise RuntimeError(f"{powerpoint_error} {error}" if powerpoint_error else str(error)) from None
    if powerpoint_error:
        result["powerpoint_error"] = powerpoint_error
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--renderer", choices=("auto", "powerpoint", "libreoffice"), default="auto",
                        help="auto: PowerPoint on Windows, else or on failure LibreOffice")
    parser.add_argument("--soffice", help="Path to soffice (soffice.com on Windows)")
    parser.add_argument("--dpi", type=int, default=110)
    args = parser.parse_args()
    try:
        print(json.dumps(render(args.pptx, args.output_dir, args.soffice, args.dpi, args.renderer), indent=2))
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        sys.exit(f"ERROR: {error}")


if __name__ == "__main__":
    main()
