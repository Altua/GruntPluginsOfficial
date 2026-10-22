"""PowerPoint export preflight. Reads SVG without changing the bytes embedded in PPTX."""
import math
import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"


def validate_ppt_svg(svg_bytes):
    if b"<!DOCTYPE" in svg_bytes.upper() or b"<!ENTITY" in svg_bytes.upper():
        raise ValueError("SVG declarations/entities are not supported; download a plain Grunt SVG.")
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        raise ValueError("Invalid SVG XML; re-download the Grunt SVG.") from None
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("Expected a standalone SVG document.")
    if (root.get("data-grunt-scope") is not None or any(
            "data-grunt-scope" in (element.text or "")
            for element in root.iter(f"{{{SVG_NS}}}style"))):
        raise ValueError(
            "Browser snapshot SVG cannot be inserted into PowerPoint: scoped CSS can lose text "
            "size and color in slide renderers. Do not use export_asset(format='svg') for PPTX. "
            "Download the plain SVG from the asset capability URL with width and height using "
            "download_chart.py. Keep the original bytes; do not strip CSS selectors to bypass this check.")
    if any(True for _ in root.iter(f"{{{SVG_NS}}}foreignObject")):
        raise ValueError("HTML inside SVG is not supported by PowerPoint; download a plain Grunt SVG.")
    return root


def svg_viewport(root):
    """Return physical viewport in CSS px, respecting SVG absolute units and viewBox fallback."""
    units = {"": 1, "px": 1, "pt": 96 / 72, "in": 96, "cm": 96 / 2.54, "mm": 96 / 25.4, "pc": 16}

    def length(value):
        match = re.fullmatch(r"\s*([+]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*(px|pt|in|cm|mm|pc)?\s*", value or "")
        return float(match[1]) * units[match[2] or ""] if match else None

    width, height = length(root.get("width")), length(root.get("height"))
    if width is None or height is None:
        try:
            viewbox = [float(v) for v in re.split(r"[\s,]+", (root.get("viewBox") or "").strip())]
        except ValueError:
            viewbox = []
        if len(viewbox) != 4:
            raise ValueError("SVG needs absolute width/height or a valid viewBox for slide sizing.")
        ratio = viewbox[2] / viewbox[3] if viewbox[3] > 0 else 0
        if ratio <= 0:
            raise ValueError("SVG viewBox dimensions must be positive.")
        width, height = (height * ratio, height) if height is not None else (
            (width, width / ratio) if width is not None else (viewbox[2], viewbox[3]))
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError("SVG dimensions must be finite and positive.")
    return width, height


def svg_dimensions_points(root):
    """Use the same physical viewport for metadata and PowerPoint placement."""
    width, height = svg_viewport(root)
    return width * 72 / 96, height * 72 / 96


def fit_placement(root, left, top, width, height, fit="contain"):
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (left, top, width, height)) or min(left, top) < 0 or min(width, height) <= 0:
        raise ValueError("Slide positions must be finite and non-negative; width and height must be positive inches.")
    source_width, source_height = svg_viewport(root)
    scale = min(width / source_width, height / source_height)
    actual_width, actual_height = source_width * scale, source_height * scale
    if fit == "exact":
        if abs(width / height / (source_width / source_height) - 1) > 0.001:
            raise ValueError("Placement would distort the SVG. Use fit='contain' or export it at the target aspect ratio.")
        return left, top, width, height
    if fit != "contain":
        raise ValueError("fit must be 'contain' or 'exact'.")
    return left + (width - actual_width) / 2, top + (height - actual_height) / 2, actual_width, actual_height
