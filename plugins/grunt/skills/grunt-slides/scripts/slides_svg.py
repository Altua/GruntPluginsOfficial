#!/usr/bin/env python3
"""Download a Grunt chart SVG through its permanent asset manifest and make it ready for a
Claude Slides deck.

Read the source URL from stdin or --url-file; never put links in argv. The download itself is
grunt-pptx's download_chart.py (HTTPS only, allowlisted origins, no redirects, size and identity
checks), which must sit next to this skill in the same plugin.

Slides stores an uploaded SVG without its <style> blocks, comments and embedded images, and
keeps root data-* attributes. Grunt puts every text style in <style> classes and carries a
permanent link in data-grunt-src, so the downloaded file is changed before it is written:
each class rule moves into the elements' style attributes, and <style>, comments, class and
data-* attributes, scripts, foreignObject and external references are removed. The output
contains no link or token and is safe to upload to a deck. Diagnostics contain no URLs.
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOWNLOADER_DIR = HERE.parent.parent / "grunt-pptx" / "scripts"

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

# Grunt SVG sizes are in points (72/in; a 1109 px request is 831.75 wide). The Slides canvas is
# 1920 px across 13.333 in (144 px/in), so one point is 2 slide px; Grunt requests are CSS px (96/in).
SLIDE_PX_PER_POINT = 2.0
POINTS_PER_CSS_PX = 0.75
# Slides refuses inline drawings over 52 KB; uploads have room, but a chart this large is unusual.
LARGE_SVG_BYTES = 2 * 1024 * 1024

CLASS_RULE = re.compile(r"\.(-?[A-Za-z_][\w-]*)\s*\{([^{}]*)\}")
STYLE_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
REMOVED_ELEMENTS = {"script", "foreignObject", "style", "metadata"}


def local_name(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse_declarations(text):
    """CSS declarations as an ordered dict; a later duplicate wins, as in CSS."""
    declarations = {}
    for part in text.split(";"):
        name, separator, value = part.partition(":")
        name, value = name.strip(), value.strip()
        if separator and name and value:
            declarations[name] = value
    return declarations


def format_declarations(declarations):
    return ";".join(f"{name}:{value}" for name, value in declarations.items())


def collect_class_rules(root, warnings):
    rules = {}
    for element in root.iter():
        if local_name(element.tag) != "style":
            continue
        css = STYLE_COMMENT.sub("", element.text or "")
        for match in CLASS_RULE.finditer(css):
            rules.setdefault(match.group(1), {}).update(parse_declarations(match.group(2)))
        leftover = CLASS_RULE.sub("", css).strip()
        if leftover:
            warnings.append("A style rule that is not a single class rule was dropped; check the chart's text.")
    return rules


def is_external_reference(value):
    value = value.strip()
    return bool(value) and not value.startswith("#") and not value.startswith("data:")


def make_slides_safe(svg_bytes):
    """Return (bytes, warnings) for an SVG that Slides keeps intact and that carries no link."""
    try:
        root = ET.fromstring(svg_bytes)  # ElementTree drops comments while parsing.
    except ET.ParseError:
        raise ValueError("The SVG is malformed.") from None
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("The file is not an SVG document.")

    warnings = []
    rules = collect_class_rules(root, warnings)

    images = 0
    # Decide on a snapshot of the tree; removing while iterating would skip elements.
    for parent, child in [(parent, child) for parent in root.iter() for child in parent]:
        name = local_name(child.tag)
        if name in REMOVED_ELEMENTS or not isinstance(child.tag, str):
            parent.remove(child)
            if name in ("script", "foreignObject"):
                warnings.append(f"Removed a <{name}> element, which Slides does not keep.")
            continue
        references = [child.get("href"), child.get(f"{{{XLINK_NS}}}href")]
        if any(value and is_external_reference(value) for value in references):
            parent.remove(child)
            warnings.append("Removed an element that referenced an outside file.")
            continue
        if name == "image":
            images += 1

    for element in root.iter():
        classes = (element.attrib.pop("class", "") or "").split()
        if classes:
            merged = {}
            for name in classes:
                merged.update(rules.get(name, {}))
            merged.update(parse_declarations(element.get("style", "")))
            if merged:
                element.set("style", format_declarations(merged))
        for attribute in [key for key in element.attrib if local_name(key).startswith("data-") or local_name(key).startswith("on")]:
            del element.attrib[attribute]

    if images:
        warnings.append(f"The chart has {images} embedded image(s), such as a logo; Slides removes them from uploaded SVGs.")

    return ET.tostring(root, encoding="utf-8"), warnings


def svg_size(root):
    """Width and height in the SVG's own units (points for Grunt), from the root attributes or else the viewBox."""
    def number(value):
        match = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(px)?\s*", value or "")
        return float(match.group(1)) if match else None

    width, height = number(root.get("width")), number(root.get("height"))
    if width and height:
        return width, height
    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) == 4:
        return float(box[2]), float(box[3])
    return None, None


def slide_pixels(points):
    """Slide canvas pixels for an SVG length in points."""
    return int(points * SLIDE_PX_PER_POINT + 0.5)


def load_downloader():
    if not (DOWNLOADER_DIR / "download_chart.py").is_file():
        print(json.dumps({"error": "grunt-pptx's scripts/download_chart.py was not found next to this skill. "
                                   "Install the whole Grunt plugin."}))
        sys.exit(1)
    sys.path.insert(0, str(DOWNLOADER_DIR))
    import download_chart  # noqa: E402 - located at runtime
    return download_chart


def main():
    downloader = load_downloader()
    parser = downloader._NoEchoArgumentParser(
        description="Download a Grunt chart SVG for a Claude Slides deck. "
                    "The URL is never a command-line argument: pass --url-file or pipe it on stdin.")
    parser.add_argument("--output", required=True, help="Path for the Slides-ready SVG (contains no link).")
    parser.add_argument("--url-file", default=None,
                        help="File holding the asset URL (one line). Deleted right after it is read. "
                             "If omitted, the URL is read from stdin.")
    parser.add_argument("--trust-origin", action="append", default=[], type=downloader._validate_trust_origin,
                        metavar="ORIGIN", help="Another HTTPS asset-link origin to trust, as in download_chart.py.")
    parser.add_argument("--trust-delivery-origin", action="append", default=[],
                        type=downloader._validate_trust_origin, metavar="ORIGIN",
                        help="Another HTTPS origin for SVG delivery only, as in download_chart.py.")
    args = parser.parse_args()

    url = downloader.read_url(args)
    allowed = tuple(dict.fromkeys(downloader.DEFAULT_ASSET_LINK_ORIGINS + tuple(args.trust_origin)))

    # The downloaded SVG carries a permanent link: keep it in a private folder, then delete it.
    private = Path(tempfile.mkdtemp(prefix="grunt-slides-"))
    try:
        raw = downloader.download_svg(url, str(private / "source.svg"), allowed, args.trust_delivery_origin)
        identity = downloader.parse_svg_metadata(raw, extra_trusted_origins=tuple(args.trust_origin))
    finally:
        shutil.rmtree(private, ignore_errors=True)

    if not identity.get("asset_id") or not identity.get("asset_commit"):
        downloader.fail("The SVG does not name its asset and version, so the slide could not be tied to it.")

    try:
        safe, warnings = make_slides_safe(raw)
    except ValueError as error:
        downloader.fail(str(error))

    width, height = svg_size(ET.fromstring(safe))
    if not width or not height:
        downloader.fail("The SVG has no usable width and height.")
    if len(safe) > LARGE_SVG_BYTES:
        warnings.append("The SVG is unusually large; uploading it may be slow or refused.")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_bytes(safe)

    asset_id, commit = identity["asset_id"].lower(), identity["asset_commit"].lower()
    print(json.dumps({
        "svg_path": args.output,
        "asset_id": asset_id,
        "asset_commit": commit,
        "alt_marker": f"[grunt:{asset_id}@{commit}]",
        "grunt_width": round(width / POINTS_PER_CSS_PX, 2),
        "grunt_height": round(height / POINTS_PER_CSS_PX, 2),
        "slide_width": slide_pixels(width),
        "slide_height": slide_pixels(height),
        "file_size": len(safe),
        "font_families": downloader.svg_font_families(safe),
        "warnings": warnings,
    }, indent=2))


if __name__ == "__main__":
    main()
