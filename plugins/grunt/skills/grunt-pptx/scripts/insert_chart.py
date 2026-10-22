#!/usr/bin/env python3
"""
Insert a Grunt web chart SVG into a PowerPoint file as an editable shape.

Attaches four small tags to the shape:

    GRUNT-WEB-ASSETID     -- the Grunt cloud asset identifier
    GRUNT-WEB-ASSETCOMMIT -- the specific version/commit of the asset
    GRUNT-WEB-REVISION-POLICY -- pinned (default), or explicit latest import
    GRUNT-WEB-LINK        -- the asset's canonical capability URL (design
                              docs/superpowers/specs/2026-08-27-grunt-asset-links-design.md
                              §6), i.e. the exact `data-grunt-src` value the SVG
                              itself carries. NEW in v2. Absent (not present at
                              all, never an empty string) when the SVG has no
                              valid carrier.

The Grunt add-in resolves GRUNT-WEB-LINK to its JSON manifest and follows
links.project with an edit capability to load the full native project. It checks
the asset ID and commit against the tags, then saves the model locally for
offline editing. No WSL route, development user, or API key is embedded.
Without the add-in, PowerPoint renders the SVG (with PNG fallback) as a static
image. Inspect the final deck in the intended slide renderer before delivery.

v2 fix (P0 finding, design doc §2.3): the PRIOR version of this script stripped
the SVG's `<!-- assetId:...,commitId:... -->` comment before embedding it into the
pptx, on the theory that ElementTree needed "clean" XML to parse dimensions from.
The 2026-08-27 P0 spike proved that's false -- ElementTree parses comments (in-root
or otherwise) without any issue -- so the stripping was both unnecessary AND a bug:
it silently mangled the embedded SVG bytes relative to what the server actually
served. This version parses dimensions/identity from a COPY of the bytes and
embeds the ORIGINAL bytes, untouched, byte-for-byte.

Identity (assetId/assetCommit/link) is parsed directly from the SVG file's own
root `data-grunt-src` carrier attribute (primary, fully structurally validated --
a port of @grunt-io/react's carrier.ts) or legacy in-root comment (fallback for
assetId/assetCommit only, parsed from a retained XML comment node -- never a
regex over raw bytes; see the parsing block below). --asset-id/--asset-commit CLI
flags remain as a last-resort override, but the default (and recommended) path
needs neither: the file is now the single source of truth for its own identity,
which eliminates the bash-variable-expansion failure class the old version of
this skill's Troubleshooting section warned about. Any override IS validated
(strict GUID/64-hex pattern) before use -- a malformed override is rejected with
a clear error, never silently embedded as a tag. There is no --link CLI override,
deliberately: the link carries a bearer token, and a CLI flag would put it in
argv (visible to other processes/users on the machine) -- see download_chart.py's
docstring for the same rule.

The embedded carrier's own origin must appear in an allowlist (DEFAULT_ASSET_LINK_ORIGINS,
`https://assets.grunt.io` by default) before GRUNT-WEB-LINK is written at all --
against any OTHER capability server, pass the repeatable --trust-origin flag
(e.g. `--trust-origin https://localhost:7299`) to extend that allowlist.
Origins are not secrets, so this is safe on argv. An origin is NEVER
auto-trusted merely because it appears inside the SVG being parsed -- trust
comes only from this flag or the built-in default, which is what keeps the
allowlist meaningful as a security boundary.

The shape structure matches the Grunt add-in's native format:
  - <p:sp> shape (not <p:pic>)
  - <a:blipFill> inside <p:spPr> with PNG fallback + asvg:svgBlip extension
  - Shape named "Grunt object {assetId}"
  - Tags linked via <p:custDataLst>

Usage:
    python insert_chart.py \\
        --svg chart.svg \\
        --pptx template.pptx \\
        --output output.pptx \\
        --slide 0 \\
        --left 1.0 --top 1.0 --width 8.0 --height 4.5

    # Against a non-default capability server (e.g. local dev), add
    # --trust-origin (repeatable) or GRUNT-WEB-LINK is silently never written:
    python insert_chart.py \\
        --svg chart.svg \\
        --pptx template.pptx \\
        --output output.pptx \\
        --slide 0 \\
        --left 1.0 --top 1.0 --width 8.0 --height 4.5 \\
        --trust-origin https://localhost:7299

Dependencies:
    pip install python-pptx lxml "cairosvg>=2.7.0" --break-system-packages

(cairosvg>=2.7.0 specifically: that release disabled external-resource/XML-entity
access by default as a security fix -- this script also passes `unsafe=False`
explicitly to `cairosvg.svg2png` below, rather than relying only on the library's
own default, so a future default change upstream can't silently re-enable it here.)
"""

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.util import Inches

import json
import uuid
import os
import tempfile
from pptx_validation import validate_ppt_svg, fit_placement, svg_viewport, svg_dimensions_points


# ---------------------------------------------------------------------------
# XML Namespaces
# ---------------------------------------------------------------------------

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ASVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
A16_NS = "http://schemas.microsoft.com/office/drawing/2014/main"

TAG_REL_TYPE = f"{R_NS}/tags"
TAG_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.tags+xml"
)
SVG_CONTENT_TYPE = "image/svg+xml"
SVG_EXT_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
CREATION_ID_URI = "{FF2B5EF4-FFF2-40B4-BE49-F238E27FC236}"


# ---------------------------------------------------------------------------
# SVG identity + dimension parsing
#
# NOTE: kept in sync (by hand -- these are self-contained skill scripts with no
# cross-file imports) with the equivalent block in download_chart.py and
# get_svg_info.py (both in this same scripts/ directory). If you change
# parsing behavior here, change it there too.
# ---------------------------------------------------------------------------

CARRIER_SRC_ATTR = "data-grunt-src"
CARRIER_VERSION_ATTR = "data-grunt-link-version"
CARRIER_VERSION = "1"

# The production capability origin -- @grunt-io/react's own default. This
# script has no implicit "download context" to also trust (unlike
# download_chart.py, which additionally trusts the origin it just downloaded
# from). --trust-origin (see main(), below) is the explicit equivalent here:
# any additional origin the caller wants trusted must be named on the command
# line -- never auto-trusted merely because it appears inside the SVG being
# parsed, which would defeat the allowlist entirely.
DEFAULT_ASSET_LINK_ORIGINS = ("https://assets.grunt.io",)

GUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
ASSET_PATH_PATTERN = re.compile(
    r"^/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)
COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

TOKEN_ID_LENGTH = 32
TOKEN_SECRET_TEXT_LENGTH = 52
TOKEN_SECRET_BYTE_LENGTH = 32
TOKEN_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def is_canonical_base32_secret(text: str) -> bool:
    """See download_chart.py's identically-named function for the full
    docstring; kept in sync by hand."""
    output_bytes = 0
    buffer = 0
    bits_in_buffer = 0

    for raw_char in text:
        folded = raw_char.upper() if "a" <= raw_char <= "z" else raw_char
        try:
            value = BASE32_ALPHABET.index(folded)
        except ValueError:
            return False

        buffer = ((buffer << 5) | value) & 0x1FFF
        bits_in_buffer += 5

        if bits_in_buffer >= 8:
            bits_in_buffer -= 8
            if output_bytes >= TOKEN_SECRET_BYTE_LENGTH:
                return False
            output_bytes += 1

    if output_bytes != TOKEN_SECRET_BYTE_LENGTH:
        return False

    if bits_in_buffer > 0:
        leftover_mask = (1 << bits_in_buffer) - 1
        if buffer & leftover_mask:
            return False

    return True


def is_structurally_valid_token(token_text: str) -> bool:
    """See download_chart.py's identically-named function for the full
    docstring; kept in sync by hand."""
    if not token_text:
        return False

    first_dot = token_text.find(".")
    if first_dot < 0 or token_text.find(".", first_dot + 1) >= 0:
        return False

    id_segment = token_text[:first_dot]
    secret_segment = token_text[first_dot + 1:]

    if len(id_segment) != TOKEN_ID_LENGTH or not TOKEN_ID_PATTERN.match(id_segment):
        return False
    if len(secret_segment) != TOKEN_SECRET_TEXT_LENGTH:
        return False

    return is_canonical_base32_secret(secret_segment)


def parse_carrier_url(url: str, allowed_origins) -> dict | None:
    """See download_chart.py's identically-named function for the full
    docstring; kept in sync by hand."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    host = parsed.hostname or ""
    try:
        # `.port` is a property that re-parses/validates the port text on
        # every access (not just at urlsplit() time) and raises ValueError
        # for one that's out of range -- e.g. a hostile carrier URL with a
        # 6+ digit port. That must fail closed (carrier not found) like any
        # other malformed input here, never escape as an uncaught exception.
        port = parsed.port
    except ValueError:
        return None
    # `port == 0` is a valid, distinct port value (falsy in Python, but NOT
    # "no port was given") -- comparing `is not None` (never bare truthiness)
    # is what keeps e.g. `https://assets.grunt.io:0/...` from reconstructing to
    # the SAME origin string as the bare default `https://assets.grunt.io`,
    # which would otherwise let it pass the allowlist check below as an
    # impostor of the real default origin (verified live).
    origin = f"{parsed.scheme}://{host}" + (f":{port}" if port is not None else "")
    if parsed.scheme != "https" or origin not in allowed_origins:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.fragment:
        return None

    path_match = ASSET_PATH_PATTERN.match(parsed.path)
    if not path_match:
        return None
    path_asset_id = path_match.group(1).lower()

    # keep_blank_values=True: parse_qs's DEFAULT behavior silently DROPS a
    # blank query value (`commit=` contributes nothing to the parsed dict),
    # which would let `commit=<valid>&commit=` (or the same for `token`)
    # slip past the "appears exactly once" checks below -- the blank
    # duplicate vanishes instead of being counted, leaving exactly one
    # (valid-looking) value. keep_blank_values=True counts it, so a blank
    # duplicate is correctly rejected as duplicate, not silently ignored.
    query = parse_qs(parsed.query, keep_blank_values=True)

    formats = query.get("format", [])
    if len(formats) > 1 or (formats and formats[0] != "manifest"):
        return None

    query_asset_id_values = query.get("assetId", [])
    if len(query_asset_id_values) > 1:
        return None
    if len(query_asset_id_values) == 1 and query_asset_id_values[0].lower() != path_asset_id:
        return None

    commit_values = query.get("commit", [])
    if len(commit_values) != 1 or not COMMIT_PATTERN.match(commit_values[0]):
        return None
    commit = commit_values[0].lower()

    token_values = query.get("token", [])
    if len(token_values) != 1 or not is_structurally_valid_token(token_values[0]):
        return None
    token = token_values[0]
    link_id = token[:token.index(".")].lower()

    return {
        "asset_id": path_asset_id,
        "asset_commit": commit,
        "token": token,
        "link_id": link_id,
    }


def _parse_legacy_comment_identity(svg_bytes: bytes) -> tuple:
    """See download_chart.py's identically-named function for the full
    docstring (retained XML comment nodes, direct children of root only --
    never regex-over-bytes); kept in sync by hand."""
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    try:
        root = ET.fromstring(svg_bytes, parser=parser)
    except ET.ParseError:
        return None, None

    for child in list(root):
        if child.tag is ET.Comment and child.text:
            match = re.match(r"^\s*assetId:([^,]+),\s*commitId:(\S+?)\s*$", child.text)
            if match:
                return match.group(1).strip(), match.group(2).strip()
    return None, None


def parse_svg_metadata(svg_bytes: bytes, extra_trusted_origins=()) -> dict:
    """Parse identity (assetId/assetCommit/link) + dimensions from a COPY of the
    SVG bytes via a real XML parser. Deliberately does NOT strip comments first
    (see module docstring: the 2026-08-27 P0 spike proved ElementTree doesn't
    need that, and stripping was the pre-existing embed-time bug). The CALLER is
    responsible for embedding the ORIGINAL bytes this was parsed from, unmodified
    -- this function only ever reads. The final assetId/assetCommit -- from
    EITHER the carrier or the legacy comment fallback -- is always validated
    against strict GUID/64-hex patterns before being trusted.

    `extra_trusted_origins` (from the repeatable --trust-origin CLI flag, zero
    or more, already validated and normalized by _validate_trust_origin) is
    trusted in ADDITION to DEFAULT_ASSET_LINK_ORIGINS when validating the
    embedded carrier's own origin -- never an origin merely found inside the
    SVG itself, which would defeat the allowlist's whole purpose.
    """
    allowed_origins = DEFAULT_ASSET_LINK_ORIGINS
    for origin in extra_trusted_origins:
        if origin not in allowed_origins:
            allowed_origins = allowed_origins + (origin,)

    result = {
        "asset_id": None,
        "asset_commit": None,
        "link": None,
        "width": None,
        "height": None,
    }

    root = None
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        pass

    if root is not None:
        src = root.get(CARRIER_SRC_ATTR)
        version = root.get(CARRIER_VERSION_ATTR)
        if version == CARRIER_VERSION and src:
            carrier = parse_carrier_url(src, allowed_origins)
            if carrier is not None:
                result["asset_id"] = carrier["asset_id"]
                result["asset_commit"] = carrier["asset_commit"]
                result["link"] = src  # verbatim -- the exact bytes the server sent

        try:
            result["width"], result["height"] = svg_dimensions_points(root)
        except ValueError:
            pass

    if result["asset_id"] is None or result["asset_commit"] is None:
        legacy_asset_id, legacy_commit = _parse_legacy_comment_identity(svg_bytes)
        result["asset_id"] = result["asset_id"] or legacy_asset_id
        result["asset_commit"] = result["asset_commit"] or legacy_commit

    if result["asset_id"] is not None and not GUID_PATTERN.match(result["asset_id"]):
        result["asset_id"] = None
    if result["asset_commit"] is not None and not COMMIT_PATTERN.match(result["asset_commit"]):
        result["asset_commit"] = None
    # If either identity half got invalidated above, an already-captured `link`
    # (which requires BOTH to have parsed successfully via parse_carrier_url in
    # the first place) is still internally consistent -- but guard explicitly
    # against ever emitting a link whose assetId/commit didn't survive final
    # validation, for defense in depth against a future change to this function.
    if result["asset_id"] is None or result["asset_commit"] is None:
        result["link"] = None

    return result


EXTERNAL_RESOURCE_ERROR = "SVG resources must be embedded data URLs; external resources are not supported."
SVG_STYLE_TAG = "{http://www.w3.org/2000/svg}style"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
CSS_URL_PATTERN = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)


def _is_embedded_reference(reference: str) -> bool:
    reference = reference.strip()
    return not reference or reference.startswith("#") or reference[:5].lower() == "data:"


def require_embedded_resources(svg_bytes: bytes) -> None:
    """Allow only same-document fragments and data: URLs, whichever rasterizer runs."""
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        raise ValueError("Invalid SVG XML; re-download the Grunt SVG.") from None
    for element in root.iter():
        for name in ("href", XLINK_HREF):
            if not _is_embedded_reference(element.get(name) or ""):
                raise ValueError(EXTERNAL_RESOURCE_ERROR)
        css = list(element.attrib.values())
        if element.tag == SVG_STYLE_TAG:
            css.append(element.text or "")
            if "@import" in (element.text or "").lower():
                raise ValueError(EXTERNAL_RESOURCE_ERROR)
        for text in css:
            if any(not _is_embedded_reference(match.group(2)) for match in CSS_URL_PATTERN.finditer(text)):
                raise ValueError(EXTERNAL_RESOURCE_ERROR)


def svg_to_png(svg_bytes: bytes, width: int = 2500) -> bytes:
    """Rasterize original bytes for the PNG fallback, allowing only embedded resources.

    resvg-py is preferred because it is a self-contained wheel on Windows, macOS and
    Linux. CairoSVG is used when resvg-py is absent and the native Cairo library loads.
    """
    require_embedded_resources(svg_bytes)
    try:
        import resvg_py
    except ImportError:
        return _cairosvg_png(svg_bytes, width)
    try:
        svg_text = svg_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("SVG must be UTF-8 encoded; re-download the Grunt SVG.") from None
    # dpi=96 resolves pt/in/cm sizes; resvg-py's default of 0 rejects them as invalid.
    return bytes(resvg_py.svg_to_bytes(svg_string=svg_text, width=width, dpi=96))


def _cairosvg_png(svg_bytes: bytes, width: int) -> bytes:
    try:
        from cairosvg.surface import PNGSurface
        from cairosvg.url import fetch
    except (ImportError, OSError) as error:
        raise ValueError("No SVG rasterizer for the PNG fallback. Install resvg-py "
                         "(pip install resvg-py), or CairoSVG >= 2.7 with the native Cairo library.") from error

    def embedded_resource(url, resource_type):
        if urlsplit(url).scheme.lower() != "data":
            raise ValueError(EXTERNAL_RESOURCE_ERROR)
        return fetch(url, resource_type)

    return PNGSurface.convert(bytestring=svg_bytes, output_width=width, unsafe=False,
                              url_fetcher=embedded_resource)


# ---------------------------------------------------------------------------
# Part numbering helpers
# ---------------------------------------------------------------------------

def _next_part_number(package, pattern: str, extension: str) -> int:
    """Find the next available part number for media files."""
    max_num = 0
    for part in package.iter_parts():
        pn = str(part.partname)
        if pattern in pn and pn.endswith(f".{extension}"):
            try:
                suffix = pn.split(pattern)[1]
                num = int(suffix.split(".")[0])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                pass
    return max_num + 1


def _next_tag_number(package) -> int:
    """Find the next available tag part number."""
    max_num = 0
    for part in package.iter_parts():
        pn = str(part.partname)
        if "/tags/tag" in pn:
            try:
                num = int(pn.split("/tags/tag")[1].split(".")[0])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                pass
    return max_num + 1


# ---------------------------------------------------------------------------
# Tag attachment
# ---------------------------------------------------------------------------

def add_tags_to_element(slide_part, nv_pr_element, tags_dict: dict) -> None:
    """
    Attach PowerPoint tags to a shape via OpenXML tag parts.

    Creates a /ppt/tags/tagN.xml part and links it to the shape through
    <p:custDataLst> inside the given <p:nvPr> element.
    """
    nsmap = {"p": P_NS, "r": R_NS}
    tag_lst = etree.Element(f"{{{P_NS}}}tagLst", nsmap=nsmap)
    for name, value in tags_dict.items():
        el = etree.SubElement(tag_lst, f"{{{P_NS}}}tag")
        el.set("name", name)
        el.set("val", value)

    tag_xml = etree.tostring(
        tag_lst, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    tag_num = _next_tag_number(slide_part.package)
    tag_uri = PackURI(f"/ppt/tags/tag{tag_num}.xml")
    tag_part = Part(
        tag_uri, TAG_CONTENT_TYPE, blob=tag_xml, package=slide_part.package
    )

    r_id = slide_part.relate_to(tag_part, TAG_REL_TYPE)

    cust_data_lst = etree.SubElement(nv_pr_element, f"{{{P_NS}}}custDataLst")
    tags_ref = etree.SubElement(cust_data_lst, f"{{{P_NS}}}tags")
    tags_ref.set(f"{{{R_NS}}}id", r_id)


# ---------------------------------------------------------------------------
# Shape construction — matches Grunt add-in structure
# ---------------------------------------------------------------------------

def add_grunt_web_chart_shape(
    slide, slide_part, svg_bytes, png_bytes,
    left, top, width, height, shape_name, tags_dict
):
    """
    Add a Grunt chart as a <p:sp> shape with blipFill.

    Structure matches the Grunt add-in's native format:
    - <p:sp> (not <p:pic>)
    - <a:blipFill> inside <p:spPr> with PNG + asvg:svgBlip extension
    - <p:custDataLst> with tag reference
    - <a16:creationId> extension
    - <p:style> and <p:txBody>

    `svg_bytes` MUST be the exact original bytes read from disk -- this function
    performs no transformation on them, it only writes them into a new media part.
    """
    validate_ppt_svg(svg_bytes)
    package = slide_part.package

    # Add PNG as media part (fallback for older PowerPoint versions)
    png_num = _next_part_number(package, "/media/image", "png")
    png_uri = PackURI(f"/ppt/media/image{png_num}.png")
    png_part = Part(png_uri, "image/png", blob=png_bytes, package=package)
    png_r_id = slide_part.relate_to(png_part, RT.IMAGE)

    # Add SVG as media part (renders in modern PowerPoint / Microsoft 365) --
    # svg_bytes is embedded verbatim, byte-for-byte, exactly as downloaded.
    svg_num = _next_part_number(package, "/media/image", "svg")
    svg_uri = PackURI(f"/ppt/media/image{svg_num}.svg")
    svg_part = Part(svg_uri, SVG_CONTENT_TYPE, blob=svg_bytes, package=package)
    svg_r_id = slide_part.relate_to(svg_part, RT.IMAGE)

    # Find spTree and determine next shape ID
    sp_tree = slide._element.find(f".//{{{P_NS}}}spTree")
    existing_ids = []
    for el in sp_tree.iter():
        id_attr = el.get("id")
        if id_attr and id_attr.isdigit():
            existing_ids.append(int(id_attr))
    next_id = max(existing_ids, default=1) + 1

    creation_id = "{" + str(uuid.uuid4()).upper() + "}"

    # Build <p:sp>
    sp = etree.SubElement(sp_tree, f"{{{P_NS}}}sp")

    # --- nvSpPr (non-visual shape properties) ---
    nv_sp_pr = etree.SubElement(sp, f"{{{P_NS}}}nvSpPr")

    c_nv_pr = etree.SubElement(nv_sp_pr, f"{{{P_NS}}}cNvPr")
    c_nv_pr.set("id", str(next_id))
    c_nv_pr.set("name", shape_name)

    # Creation ID extension
    ext_lst_cnv = etree.SubElement(c_nv_pr, f"{{{A_NS}}}extLst")
    ext_cnv = etree.SubElement(ext_lst_cnv, f"{{{A_NS}}}ext")
    ext_cnv.set("uri", CREATION_ID_URI)
    creation_el = etree.SubElement(ext_cnv, f"{{{A16_NS}}}creationId")
    creation_el.set("id", creation_id)

    etree.SubElement(nv_sp_pr, f"{{{P_NS}}}cNvSpPr")

    nv_pr = etree.SubElement(nv_sp_pr, f"{{{P_NS}}}nvPr")

    # Attach Grunt web tags to this shape
    add_tags_to_element(slide_part, nv_pr, tags_dict)

    # --- spPr (shape properties) ---
    sp_pr = etree.SubElement(sp, f"{{{P_NS}}}spPr")

    # Transform (position and size in EMU)
    xfrm = etree.SubElement(sp_pr, f"{{{A_NS}}}xfrm")
    off = etree.SubElement(xfrm, f"{{{A_NS}}}off")
    off.set("x", str(left))
    off.set("y", str(top))
    ext_el = etree.SubElement(xfrm, f"{{{A_NS}}}ext")
    ext_el.set("cx", str(width))
    ext_el.set("cy", str(height))

    # Geometry (rectangle)
    prst_geom = etree.SubElement(sp_pr, f"{{{A_NS}}}prstGeom")
    prst_geom.set("prst", "rect")
    etree.SubElement(prst_geom, f"{{{A_NS}}}avLst")

    # BlipFill inside spPr — this is the key difference from <p:pic>
    blip_fill = etree.SubElement(sp_pr, f"{{{A_NS}}}blipFill")
    blip = etree.SubElement(blip_fill, f"{{{A_NS}}}blip")
    blip.set(f"{{{R_NS}}}embed", png_r_id)

    # SVG extension — CRITICAL: use svgBlip (not svgBlob!)
    ext_lst_blip = etree.SubElement(blip, f"{{{A_NS}}}extLst")
    ext_blip = etree.SubElement(ext_lst_blip, f"{{{A_NS}}}ext")
    ext_blip.set("uri", SVG_EXT_URI)
    svg_blip = etree.SubElement(ext_blip, f"{{{ASVG_NS}}}svgBlip")
    svg_blip.set(f"{{{R_NS}}}embed", svg_r_id)

    stretch = etree.SubElement(blip_fill, f"{{{A_NS}}}stretch")
    etree.SubElement(stretch, f"{{{A_NS}}}fillRect")

    # Line (no fill, matching real Grunt output)
    ln = etree.SubElement(sp_pr, f"{{{A_NS}}}ln")
    ln.set("w", "25400")
    ln.set("cap", "flat")
    ln.set("cmpd", "sng")
    ln.set("algn", "ctr")
    etree.SubElement(ln, f"{{{A_NS}}}noFill")
    prst_dash = etree.SubElement(ln, f"{{{A_NS}}}prstDash")
    prst_dash.set("val", "solid")

    # --- style ---
    style = etree.SubElement(sp, f"{{{P_NS}}}style")
    for ref_name, idx, clr_val in [
        ("lnRef", "2", "accent1"),
        ("fillRef", "1", "accent1"),
        ("effectRef", "0", "accent1"),
        ("fontRef", None, None),
    ]:
        ref = etree.SubElement(style, f"{{{A_NS}}}{ref_name}")
        if ref_name == "fontRef":
            ref.set("idx", "minor")
            sc = etree.SubElement(ref, f"{{{A_NS}}}schemeClr")
            sc.set("val", "lt1")
        else:
            ref.set("idx", idx)
            sc = etree.SubElement(ref, f"{{{A_NS}}}schemeClr")
            sc.set("val", clr_val)
            if ref_name == "lnRef":
                shade = etree.SubElement(sc, f"{{{A_NS}}}shade")
                shade.set("val", "15000")

    # --- txBody ---
    tx_body = etree.SubElement(sp, f"{{{P_NS}}}txBody")
    body_pr = etree.SubElement(tx_body, f"{{{A_NS}}}bodyPr")
    body_pr.set("rtlCol", "0")
    body_pr.set("anchor", "ctr")
    etree.SubElement(tx_body, f"{{{A_NS}}}lstStyle")
    p_el = etree.SubElement(tx_body, f"{{{A_NS}}}p")
    p_pr = etree.SubElement(p_el, f"{{{A_NS}}}pPr")
    p_pr.set("algn", "ctr")
    end_para = etree.SubElement(p_el, f"{{{A_NS}}}endParaRPr")
    end_para.set("lang", "en-US")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _validate_trust_origin(value: str) -> str:
    """argparse `type=` callback for --trust-origin. Validates that `value` is
    a well-formed HTTPS origin -- scheme://host[:port], no userinfo, no path
    beyond an optional trailing slash, no query, no fragment, no whitespace or
    control characters -- and normalizes it to the same scheme://host[:port]
    shape parse_carrier_url's own allowlist membership check compares against
    (host/scheme lowercased via urlsplit, a port suffix only when one was
    explicit). Mirrors download_chart.py's own HTTPS-only, no-credentials,
    no-fragment rules exactly -- this is not a more permissive check for e.g.
    localhost; https is required unconditionally.

    Allowlist membership (here and in parse_carrier_url) is EXACT string
    equality, not semantic origin equivalence: `https://assets.grunt.io` and
    `https://assets.grunt.io:443` are different allowlist entries even though a
    browser would treat them as the same origin -- default-port folding is
    deliberately NOT implemented (fail-closed exact matching is this v1's
    accepted contract). An IDN/Unicode host must be given exactly as the
    carrier's own URL presents it; no punycode normalization is performed
    either.

    Raises ArgumentTypeError (argparse turns this into a clean CLI error, not
    a traceback) rather than silently accepting a malformed value or treating
    it as a no-op. Deliberately NEVER includes the candidate `value` itself in
    any error message -- unlike an origin, `value` could be an entire
    capability URL a caller pasted here by mistake (bearer token included),
    and echoing it back would leak that token to stderr. Every rejection below
    is a fixed, category-only message, mirroring this skill's existing
    token-redaction discipline elsewhere (see download_chart.py's
    `redact_url`/`fail`). For the same reason, `parsed.port` -- whose access
    can itself raise a raw ValueError for an out-of-range port, which argparse
    would otherwise report by quoting the original argv value verbatim -- is
    resolved inside this function's own protected block, never left to
    propagate past it."""
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise argparse.ArgumentTypeError(
            "--trust-origin must not contain whitespace or control characters."
        )

    try:
        parsed = urlsplit(value)
    except ValueError:
        raise argparse.ArgumentTypeError("--trust-origin is not a valid URL.")

    if parsed.scheme != "https":
        raise argparse.ArgumentTypeError(
            "--trust-origin must use https -- this mirrors the scripts' own "
            "HTTPS-only carrier validation, with no exception for localhost "
            "or any other host."
        )
    if not parsed.hostname:
        raise argparse.ArgumentTypeError("--trust-origin has no host.")
    if parsed.username is not None or parsed.password is not None:
        raise argparse.ArgumentTypeError("--trust-origin must not contain embedded credentials.")
    if parsed.path not in ("", "/"):
        raise argparse.ArgumentTypeError("--trust-origin must not contain a path.")
    if parsed.query:
        raise argparse.ArgumentTypeError("--trust-origin must not contain a query string.")
    if parsed.fragment:
        raise argparse.ArgumentTypeError("--trust-origin must not contain a fragment.")

    try:
        port = parsed.port
    except ValueError:
        raise argparse.ArgumentTypeError("--trust-origin has an invalid port.")

    # `port == 0` is a valid, distinct port value (falsy in Python, but NOT
    # "no port was given") -- comparing `is not None` (never bare truthiness)
    # is what keeps `--trust-origin https://host:0` from silently normalizing
    # down to `https://host`, which would incorrectly widen trust to the
    # default-port origin instead of the (unusual but distinct) `:0` origin
    # the caller actually typed.
    return f"{parsed.scheme}://{parsed.hostname}" + (f":{port}" if port is not None else "")


def insert_charts(pptx, output, placements, *, base_dir=Path('.'), trusted_origins=(),
                  revision_policy="pinned", fit="contain", preview_dir=None):
    """Preflight the whole manifest, then load/save once. SVGs remain byte-identical."""
    if not isinstance(placements, list) or not placements:
        raise ValueError("Manifest must be a non-empty JSON array of placements.")
    if revision_policy not in ("pinned", "latest"):
        raise ValueError("revision_policy must be 'pinned' or 'latest'.")
    prs = Presentation(pptx)
    prepared = []
    allowed = {"svg", "slide", "left", "top", "width", "height", "asset_id", "asset_commit", "fit"}
    required = {"svg", "slide", "left", "top", "width", "height"}
    for index, placement in enumerate(placements):
        if not isinstance(placement, dict) or set(placement) - allowed or required - set(placement):
            raise ValueError(f"Placement {index}: expected svg, slide, left, top, width, height; "
                             "optional asset_id, asset_commit, fit. Unknown fields are not accepted.")
        slide_index = placement["slide"]
        if isinstance(slide_index, bool) or not isinstance(slide_index, int) or not 0 <= slide_index < len(prs.slides):
            raise ValueError(f"Placement {index}: slide index must be between 0 and {len(prs.slides) - 1}.")
        if not isinstance(placement["svg"], str) or not placement["svg"]:
            raise ValueError(f"Placement {index}: svg must be a local file path.")
        svg_path = Path(base_dir) / placement["svg"]
        svg_bytes = svg_path.read_bytes()
        root = validate_ppt_svg(svg_bytes)
        metadata = parse_svg_metadata(svg_bytes, tuple(trusted_origins))
        has_override = "asset_id" in placement or "asset_commit" in placement
        if has_override and not {"asset_id", "asset_commit"} <= placement.keys():
            raise ValueError(f"Placement {index}: asset_id and asset_commit overrides must be supplied together.")
        asset_id = placement["asset_id"] if has_override else metadata["asset_id"]
        asset_commit = placement["asset_commit"] if has_override else metadata["asset_commit"]
        if not isinstance(asset_id, str) or not GUID_PATTERN.fullmatch(asset_id):
            raise ValueError(f"Placement {index}: asset_id must be a well-formed GUID. Re-download with download_chart.py.")
        if not isinstance(asset_commit, str) or not COMMIT_PATTERN.fullmatch(asset_commit):
            raise ValueError(f"Placement {index}: asset_commit must be 64 hex characters. Re-download with download_chart.py.")
        link = None if has_override else metadata["link"]
        left, top, width, height = fit_placement(root, *(placement[key] for key in ("left", "top", "width", "height")),
                                                fit=placement.get("fit", fit))
        if left + width > prs.slide_width / 914400 + 0.0001 or top + height > prs.slide_height / 914400 + 0.0001:
            raise ValueError(f"Placement {index}: SVG extends beyond the slide. Adjust its position or size.")
        tags = {"GRUNT-WEB-ASSETID": asset_id, "GRUNT-WEB-ASSETCOMMIT": asset_commit,
                "GRUNT-WEB-REVISION-POLICY": revision_policy}
        if link:
            tags["GRUNT-WEB-LINK"] = link
        info = {"slide": slide_index, "asset_id": asset_id, "asset_commit": asset_commit,
                "shape_name": f"Grunt object {asset_id}", "web_link_tag_written": bool(link),
                "position": f'{left}" x {top}"', "size": f'{width}" x {height}"',
                "placement_inches": {"left": left, "top": top, "width": width, "height": height},
                "svg_viewport_px": list(svg_viewport(root)), "aspect_ratio_preserved": True}
        if not link:
            info["warning"] = "No GRUNT-WEB-LINK tag: carrier is absent, untrusted or manually overridden."
        prepared.append((svg_bytes, tags, info))

    # Preflight every item before rasterizing or writing any output. Cache reused SVGs.
    rasters = {}
    previews = []
    for svg_bytes, tags, info in prepared:
        if svg_bytes not in rasters:
            rasters[svg_bytes] = svg_to_png(svg_bytes)
        position = info["placement_inches"]
        slide = prs.slides[info["slide"]]
        add_grunt_web_chart_shape(slide, slide.part, svg_bytes, rasters[svg_bytes],
                                 *(Inches(position[key]) for key in ("left", "top", "width", "height")),
                                 info["shape_name"], tags)
        if preview_dir:
            previews.append(svg_to_png(svg_bytes, max(1, round(position["width"] * 144))))

    result = {"status": "ok", "output": str(output), "inserted": len(prepared),
              "placements": [item[2] for item in prepared]}
    if len(prepared) == 1:
        result.update(prepared[0][2])
    if preview_dir:
        result["preview_note"] = "144 dpi asset previews. Render the assembled PPTX separately in the target application."

    # Complete requested previews before committing the deck, including input == output.
    output_path = Path(output)
    descriptor, temporary = tempfile.mkstemp(suffix=".pptx", dir=output_path.resolve().parent)
    os.close(descriptor)
    try:
        prs.save(temporary)
        if preview_dir:
            directory = Path(preview_dir)
            directory.mkdir(parents=True, exist_ok=True)
            for index, preview in enumerate(previews):
                (directory / f"placement-{index + 1:03d}.png").write_bytes(preview)
            (directory / "placements.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        os.replace(temporary, output_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Insert a Grunt web chart SVG into a PowerPoint file"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--svg", help="Path to one plain Grunt SVG")
    source.add_argument("--manifest", help="JSON array of SVG placements; loads and saves the PPTX once")
    parser.add_argument("--fit", choices=("contain", "exact"), default="contain")
    parser.add_argument("--preview-dir", help="Optional final-size PNG previews at 144 dpi and token-free diagnostics")
    parser.add_argument("--pptx", required=True, help="Path to input PPTX")
    parser.add_argument("--output", required=True, help="Path to output PPTX")
    parser.add_argument("--revision-policy", choices=("pinned", "latest"), default="pinned",
                        help="pinned imports the saved version (default); latest adopts the latest version at first native import")
    parser.add_argument(
        "--slide", type=int, default=0, help="Slide index, 0-based (default: 0)"
    )
    parser.add_argument(
        "--left", type=float, default=1.0, help="Left position in inches (default: 1.0)"
    )
    parser.add_argument(
        "--top", type=float, default=1.0, help="Top position in inches (default: 1.0)"
    )
    parser.add_argument(
        "--width", type=float, default=8.0, help="Width in inches (default: 8.0)"
    )
    parser.add_argument(
        "--height", type=float, default=4.5, help="Height in inches (default: 4.5)"
    )
    parser.add_argument(
        "--asset-id", default=None,
        help="Override: Grunt asset ID (must be a well-formed GUID). Normally "
        "auto-derived from the SVG's own data-grunt-src carrier attribute -- "
        "only pass this if the SVG has no carrier and no legacy identity comment.",
    )
    parser.add_argument(
        "--asset-commit", default=None,
        help="Override: Grunt asset commit (must be 64 hex characters). Same "
        "caveat as --asset-id.",
    )
    parser.add_argument(
        "--trust-origin", action="append", default=[], dest="trust_origin",
        type=_validate_trust_origin, metavar="ORIGIN",
        help=(
            "Additional HTTPS origin to trust for the SVG's embedded "
            "data-grunt-src carrier, in ADDITION to the built-in default "
            "(https://assets.grunt.io). Repeatable. Origins are not secrets, so "
            "this is safe on the command line -- e.g. against a local "
            "capability server: --trust-origin https://localhost:7299. "
            "Without this, a carrier from any other origin is treated as "
            "absent (not an error) and no GRUNT-WEB-LINK tag is written. "
            "Matching is EXACT (e.g. https://assets.grunt.io:443 is a different "
            "entry than the default, fail-closed); give an IDN/Unicode host "
            "exactly as the carrier presents it."
        ),
    )
    args = parser.parse_args()

    if args.manifest:
        if args.asset_id or args.asset_commit:
            parser.error("Identity overrides belong in each manifest item, not global CLI flags.")
        manifest_path = Path(args.manifest)
        placements = json.loads(manifest_path.read_text(encoding="utf-8"))
        base_dir = manifest_path.parent
    else:
        placements = [{"svg": args.svg, "slide": args.slide, "left": args.left, "top": args.top,
                       "width": args.width, "height": args.height}]
        if args.asset_id is not None:
            placements[0]["asset_id"] = args.asset_id
        if args.asset_commit is not None:
            placements[0]["asset_commit"] = args.asset_commit
        base_dir = Path.cwd()
    try:
        result = insert_charts(args.pptx, args.output, placements, base_dir=base_dir,
                               trusted_origins=args.trust_origin, revision_policy=args.revision_policy,
                               fit=args.fit, preview_dir=args.preview_dir)
    except (ValueError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
