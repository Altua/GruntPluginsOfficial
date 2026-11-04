"""PowerPoint export preflight. Reads SVG without changing the bytes embedded in PPTX."""
import base64
import binascii
import math
import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
LOWERCASE_COMMIT = re.compile(r"[0-9a-f]{64}\Z")
NATIVE_BOUNDS = ("x", "y", "width", "height")
NATIVE_OPTIONAL_PAYLOADS = ("dataServiceBase64", "resourcesBase64", "shapeBoundsBase64")


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


def _is_base64(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return True


def validate_native_placement(document):
    """Check a native placement (the links.pptx response) and return its objects.

    Errors never quote values: the payloads are the customer's full chart model.
    Unknown fields are ignored so a newer server's response stays readable.
    """
    if (not isinstance(document, dict) or type(document.get("schemaVersion")) is not int
            or document["schemaVersion"] != 1):
        raise ValueError("Native placement must be schemaVersion 1.")
    if not isinstance(document.get("assetId"), str) or not GUID.match(document["assetId"]):
        raise ValueError("Native placement assetId must be a GUID.")
    if not isinstance(document.get("projectCommitKey"), str) or not LOWERCASE_COMMIT.match(document["projectCommitKey"]):
        raise ValueError("Native placement projectCommitKey must be 64 lowercase hex characters.")
    objects = document.get("objects")
    if not isinstance(objects, list) or not objects:
        raise ValueError("Native placement must contain at least one object.")
    keys = set()
    for number, item in enumerate(objects, 1):
        where = f"Native object {number}"
        if not isinstance(item, dict):
            raise ValueError(f"{where} is not a JSON object.")
        key = item.get("pageObjectKey")
        if not isinstance(key, str) or not GUID.match(key) or key.lower() in keys:
            raise ValueError(f"{where}: pageObjectKey must be a unique GUID.")
        keys.add(key.lower())
        if not isinstance(item.get("objectType"), str) or not item["objectType"].strip():
            raise ValueError(f"{where}: objectType must be a non-empty string.")
        if not isinstance(item.get("svg"), str):
            raise ValueError(f"{where}: svg must be a string.")
        try:
            validate_ppt_svg(item["svg"].encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError(f"{where}: svg is not valid UTF-8 text.") from None
        except ValueError as error:
            raise ValueError(f"{where}: {error}") from None
        bounds = item.get("svgBounds")
        if (not isinstance(bounds, dict) or not all(
                isinstance(bounds.get(name), (int, float)) and not isinstance(bounds[name], bool)
                and math.isfinite(bounds[name]) for name in NATIVE_BOUNDS)
                or min(bounds["width"], bounds["height"]) <= 0):
            raise ValueError(f"{where}: svgBounds needs finite x and y and a positive width and height, in points.")
        if not _is_base64(item.get("pageObjectBase64")):
            raise ValueError(f"{where}: pageObjectBase64 must be non-empty base64.")
        for name in NATIVE_OPTIONAL_PAYLOADS:
            if item.get(name) is not None and not _is_base64(item[name]):
                raise ValueError(f"{where}: {name} must be non-empty base64 when present.")
    return objects
