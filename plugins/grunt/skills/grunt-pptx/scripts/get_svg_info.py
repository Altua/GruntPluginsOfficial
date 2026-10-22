#!/usr/bin/env python3
"""
Get dimensions and identity metadata from a local Grunt SVG file.

Use this when you already have the SVG on disk (e.g. from download_chart.py) and
need its dimensions for PowerPoint layout planning, without re-downloading it.

Usage:
    python get_svg_info.py chart.svg

    # Against a non-default capability server (e.g. local dev), trust its
    # origin explicitly -- repeatable, and required or the embedded carrier
    # is treated as absent (see --trust-origin's own help for why):
    python get_svg_info.py chart.svg --trust-origin https://localhost:7299

Output (JSON to stdout):
    {
        "svg_width": 600,
        "svg_height": 337.5,
        "aspect_ratio": 1.7778,
        "asset_id": "557db558-...",
        "asset_commit": "9a337151...",
        "carrier_found": true,
        "file_size": 12345
    }

Dimensions are reported in points. Absolute SVG units and viewBox fallbacks
use the same conversion as PowerPoint placement (one CSS pixel = 0.75 points).
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from pptx_validation import svg_dimensions_points
from urllib.parse import parse_qs, urlsplit

# ---------------------------------------------------------------------------
# NOTE: this parsing block is kept in sync (by hand for carrier validation) with this skill's own
# download_chart.py and insert_chart.py (same scripts/ directory). If you
# change parsing behavior here, change it there too.
# ---------------------------------------------------------------------------

CARRIER_SRC_ATTR = "data-grunt-src"
CARRIER_VERSION_ATTR = "data-grunt-link-version"
CARRIER_VERSION = "1"

# The production capability origin -- @grunt-io/react's own default. This
# standalone script has no implicit "download context" to also trust (unlike
# download_chart.py, which additionally trusts the origin it just downloaded
# from). --trust-origin (see main(), below) is the explicit equivalent for a
# standalone script: any additional origin the caller wants trusted must be
# named on the command line -- never auto-trusted merely because it appears
# inside the SVG being parsed, which would defeat the allowlist entirely.
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
    """See download_chart.py's identically-named function for the full
    docstring (in particular: no comment-stripping -- ElementTree parses fine
    with comments present; final GUID/64-hex validation on the assembled
    identity regardless of source); kept in sync by hand. This standalone
    script has no implicit download context, so `extra_trusted_origins` (from
    the repeatable --trust-origin CLI flag, zero or more, already validated
    and normalized by _validate_trust_origin) is trusted in ADDITION to
    DEFAULT_ASSET_LINK_ORIGINS -- never an origin merely found inside the SVG
    itself, which would defeat the allowlist's whole purpose."""
    allowed_origins = DEFAULT_ASSET_LINK_ORIGINS
    for origin in extra_trusted_origins:
        if origin not in allowed_origins:
            allowed_origins = allowed_origins + (origin,)

    result = {
        "asset_id": None,
        "asset_commit": None,
        "carrier_found": False,
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
                result["carrier_found"] = True

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

    return result


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


def main():
    parser = argparse.ArgumentParser(
        description="Get dimensions and identity metadata from a Grunt SVG file"
    )
    parser.add_argument("svg", help="Path to SVG file")
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
            "absent (not an error), and identity falls back to the legacy "
            "comment or is left blank. Matching is EXACT (e.g. "
            "https://assets.grunt.io:443 is a different entry than the default, "
            "fail-closed); give an IDN/Unicode host exactly as the carrier "
            "presents it."
        ),
    )
    args = parser.parse_args()

    try:
        svg_bytes = Path(args.svg).read_bytes()
    except FileNotFoundError:
        print(json.dumps({"error": f"File not found: {args.svg}"}))
        sys.exit(1)

    metadata = parse_svg_metadata(svg_bytes, extra_trusted_origins=tuple(args.trust_origin))

    print(json.dumps({
        "svg_width": metadata["width"],
        "svg_height": metadata["height"],
        "aspect_ratio": (
            round(metadata["width"] / metadata["height"], 4)
            if metadata["width"] and metadata["height"]
            else None
        ),
        "asset_id": metadata["asset_id"],
        "asset_commit": metadata["asset_commit"],
        "carrier_found": metadata["carrier_found"],
        "file_size": len(svg_bytes),
    }, indent=2))


if __name__ == "__main__":
    main()
