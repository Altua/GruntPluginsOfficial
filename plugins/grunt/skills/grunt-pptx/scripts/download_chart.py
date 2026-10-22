#!/usr/bin/env python3
"""Download a Grunt SVG through its permanent asset manifest.

Read the source URL from stdin or --url-file; never put bearer tokens in argv.
Source URLs return JSON. Follow the advertised trusted SVG delivery link
without modifying it, and require a matching permanent pinned source in the SVG.
Keep downloaded SVG bytes unchanged.

HTTPS origins must be allowlisted (production: assets.grunt.io; --trust-origin
opts in others). Redirects, wrong response types, oversized bodies, and identity
mismatches fail before writing output. Diagnostics contain no capability URLs.
The saved SVG may contain a bearer capability and is written as a private file.
"""

import argparse
import os
import re
import tempfile
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from pptx_validation import svg_dimensions_points
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, parse_qs, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import json

# 10 MiB is generous headroom for even a very dense multi-object chart SVG while
# still bounding memory/disk use against a misbehaving or malicious endpoint.
MAX_RESPONSE_BYTES = 10 * 1024 * 1024

CARRIER_SRC_ATTR = "data-grunt-src"
CARRIER_VERSION_ATTR = "data-grunt-link-version"
CARRIER_VERSION = "1"

# The production capability origin -- @grunt-io/react's own default
# (`carrier.ts`'s DEFAULT_ASSET_LINK_ORIGINS). This ONE allowlist gates TWO
# separate checks: (1) `download_svg` (below) refuses to issue ANY request
# for a URL whose own origin isn't in this allowlist -- checked before any
# `Request`/opener object is constructed, so an untrusted URL never reaches
# urllib at all (closes an SSRF gap: a hostile or merely wrong URL used to
# be fetched from ANY https origin, then have that same origin auto-trusted
# for check (2) below regardless) -- and (2) the downloaded SVG's own
# embedded `data-grunt-src` carrier is validated against this same allowlist
# (`parse_svg_metadata`, defense in depth against a compromised/misconfigured
# endpoint's response). `--trust-origin` (see `main`, below) extends this one
# allowlist for BOTH checks at once; an origin is NEVER trusted merely
# because it's the origin a URL happened to point at -- trust comes only
# from this default or the explicit flag.
DEFAULT_ASSET_LINK_ORIGINS = ("https://assets.grunt.io",)

GUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
ASSET_PATH_PATTERN = re.compile(
    r"^/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)
COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

# --- Token shape validation -------------------------------------------------
#
# A Python port of the SHAPE-only rules from @grunt-io/react's carrier.ts
# (`isCanonicalBase32Secret`/`isStructurallyValidAssetLinkToken`), which itself
# ports apps/WebServiceLayer/.../AssetLinkTokenCodec.cs's `TryParse` (frozen by
# the P0 spike -- design §2.3/§2.9): exactly one '.', a 32-hex-char id segment,
# and a 52-char, case-folded, CANONICALLY-padded Base32 secret segment. This
# script never computes or verifies the token's HASH (that's the server's job)
# -- only whether the TEXT is well-formed enough to plausibly be real, which is
# all client-side carrier validation needs.

TOKEN_ID_LENGTH = 32
TOKEN_SECRET_TEXT_LENGTH = 52
TOKEN_SECRET_BYTE_LENGTH = 32
TOKEN_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def is_canonical_base32_secret(text: str) -> bool:
    """Port of carrier.ts's `isCanonicalBase32Secret`: ASCII-only case fold
    (never Python's `.upper()` on the whole string at once is wrong either --
    it IS ASCII-safe for this fixed alphabet, but we fold char-by-char to keep
    this a line-for-line port of the reference implementation), rejects any
    character outside the 32-symbol alphabet, and rejects a NONCANONICAL final
    symbol (nonzero padding bits) so a single secret can't have more than one
    valid text encoding."""
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
    """Port of carrier.ts's `isStructurallyValidAssetLinkToken`."""
    if not token_text:
        return False

    first_dot = token_text.find(".")
    if first_dot < 0 or token_text.find(".", first_dot + 1) >= 0:
        return False  # must contain exactly one '.'

    id_segment = token_text[:first_dot]
    secret_segment = token_text[first_dot + 1:]

    if len(id_segment) != TOKEN_ID_LENGTH or not TOKEN_ID_PATTERN.match(id_segment):
        return False
    if len(secret_segment) != TOKEN_SECRET_TEXT_LENGTH:
        return False

    return is_canonical_base32_secret(secret_segment)


# ---------------------------------------------------------------------------
# Secret-safe error formatting
# ---------------------------------------------------------------------------

def redact_url(url: str) -> str:
    """Strip the query string, fragment, and any embedded userinfo credentials
    from a URL before it ever reaches an error message or stdout. The query
    string carries the bearer token; per the design doc's redaction checklist
    ("never log query strings/URLs"), only a bare scheme://host[:port]/path is
    safe to surface, even for debugging. `urlsplit().hostname`/`.port` already
    exclude userinfo, so reconstructing netloc from them (rather than reusing
    `parsed.netloc` verbatim) is what actually strips `user:password@`.

    Deliberately TOTAL -- never raises, and never falls through to printing
    any unvalidated URL component. `.port` is a property that re-parses/
    validates the port text on EVERY access (not just at urlsplit() time) and
    raises a raw ValueError for one that's out of range (e.g. an
    attacker-chosen 6+ digit port) -- exactly the shape of URL the pre-fetch
    rejection path (download_svg, via parse_carrier_url) redacts before
    printing. An uncaught exception here would put Python's own exception
    message -- which echoes the offending port text verbatim -- onto stderr,
    defeating the entire point of redaction. Falls back to the SAME fixed,
    fully generic placeholder used for an unparseable URL in that case --
    never any URL component, not even a truncated one.

    `parsed.port == 0` is a valid, distinct port value (falsy in Python, but
    NOT "no port was given") -- comparing `is not None` here (never bare
    truthiness) is what keeps `https://host:0/...` from being redacted down
    to `https://host/...`, silently dropping a real part of the URL's own
    identity."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "<unparseable URL>"
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        return "<unparseable URL>"
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def fail(message: str):
    print(json.dumps({"error": message}))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Download (HTTPS-only, no redirects, size-capped, MIME-checked, fail-closed)
# ---------------------------------------------------------------------------

class _NoRedirectHandler(HTTPRedirectHandler):
    """Refuses every redirect response. `build_opener` replaces the default
    HTTPRedirectHandler with this one (it detects the subclass relationship), so
    the resulting opener never follows a 301/302/303/307/308 -- mirrors the
    design's `redirect:"error"` link-client rule. Since no redirect is ever
    followed, the request can never end up at a different host than the one in
    the URL we were given -- that's the "host pinning" requirement, satisfied by
    construction rather than by a separate allow/deny check."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "redirect refused (redirects are never followed)", headers, fp)


def _write_private_file(path: str, content: bytes) -> None:
    """Atomically replace the destination with a new private file.

    mkstemp sets POSIX mode 0600 before any capability bytes are written.
    Windows inherits the containing directory's ACL; use a private directory.
    Replacing the directory entry never follows a destination symlink.
    """
    destination = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".grunt-", dir=destination.absolute().parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _fetch_bytes(url: str, media_type: str) -> bytes:
    content: bytes
    try:
        opener = build_opener(_NoRedirectHandler())
        req = Request(url, headers={"User-Agent": "GruntSkill/2.0", "Accept": media_type})

        with opener.open(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if content_type.split(";")[0].strip().lower() != media_type:
                fail(f"Unexpected response Content-Type")

            content_length = resp.headers.get("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > MAX_RESPONSE_BYTES:
                        fail(f"Response Content-Length exceeds the {MAX_RESPONSE_BYTES}-byte cap")
                except ValueError:
                    pass  # Malformed header; fall through to the read-time cap below.

            content = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(content) > MAX_RESPONSE_BYTES:
                fail(f"Response exceeded the {MAX_RESPONSE_BYTES}-byte cap")
    except HTTPError as e:
        fail(f"HTTP error (status {e.code})")
    except URLError as e:
        category = "Timed out" if isinstance(e.reason, TimeoutError) else "Connection failed"
        fail(f"{category}")
    except TimeoutError:
        fail(f"Timed out")
    except Exception:
        # Catch-all: anything else (a read-time socket error, an unexpected
        # header-parsing failure, ...) still fails closed with only the
        # redacted URL -- never the exception's own message/repr, which could
        # otherwise surface request internals a hostile endpoint controls.
        fail(f"Download failed")

    return content


def _checked_delivery_url(url, allowed_origins):
    if not isinstance(url, str):
        fail("Manifest link is not a URL.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        candidate = f"{parsed.scheme}://{parsed.hostname}" + (f":{port}" if port is not None else "")
        if (parsed.scheme != "https" or candidate not in allowed_origins or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or any(c.isspace() or ord(c) < 32 for c in url)):
            fail("Manifest delivery link is outside the configured trusted origins.")
    except ValueError:
        fail("Manifest delivery URL is malformed.")
    return url


def download_svg(url: str, output_path: str, allowed_origins, delivery_origins=()) -> bytes:
    """Resolve a permanent manifest, then fetch its opaque SVG link.
    The output is byte-identical to the SVG response; no temporary delivery
    URL is substituted for the SVG's permanent pinned source reference.
    Additional delivery origins must be explicitly configured by the caller.
    """
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
    except ValueError:
        fail("Malformed source URL.")
    formats = query.pop("format", [])
    if len(formats) > 1 or (formats and formats[0] != "manifest"):
        fail("Unsupported source representation.")
    source = urlunsplit(parsed._replace(query=urlencode(query, doseq=True)))
    identity = parse_carrier_url(source, allowed_origins, require_commit=False)
    if identity is None:
        fail("Refusing to fetch an invalid or untrusted asset source URL.")
    body = _fetch_bytes(url, "application/json")
    try:
        manifest = json.loads(body)
    except (ValueError, UnicodeError):
        fail("Invalid asset manifest JSON.")
    if (not isinstance(manifest, dict) or type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1
            or not isinstance(manifest.get("assetId"), str)
            or manifest["assetId"].lower() != identity["asset_id"]
            or not isinstance(manifest.get("resolvedCommit"), str)
            or not COMMIT_PATTERN.fullmatch(manifest["resolvedCommit"])
            or (identity["asset_commit"] is not None
                and manifest["resolvedCommit"].lower() != identity["asset_commit"])):
        fail("Asset manifest does not match the requested asset version.")
    links = manifest.get("links")
    if not isinstance(links, dict):
        fail("Asset manifest is missing its representation links.")
    self_link, svg_link = links.get("self"), links.get("svg")
    if (not isinstance(self_link, dict) or self_link.get("type") != "application/json"
            or self_link.get("schemaVersion", 1) != 1
            or not isinstance(svg_link, dict) or svg_link.get("type") != "image/svg+xml"):
        fail("Asset manifest contains invalid representation links.")
    port = parsed.port
    origin = f"{parsed.scheme}://{parsed.hostname}" + (f":{port}" if port is not None else "")
    pinned_source = _checked_delivery_url(self_link.get("href"), (origin,))
    pinned = parse_carrier_url(pinned_source, allowed_origins)
    if (pinned is None or pinned["asset_id"] != identity["asset_id"]
            or pinned["asset_commit"] != manifest["resolvedCommit"].lower()
            or pinned["token"].lower() != identity["token"].lower()):
        fail("Asset manifest self link does not match the resolved asset version.")
    identity = pinned
    delivery = _checked_delivery_url(svg_link.get("href"), (origin,) + tuple(delivery_origins))
    content = _fetch_bytes(delivery, "image/svg+xml")

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        fail("Downloaded SVG is malformed.")
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        fail("Downloaded content is not an SVG document.")
    _checked_delivery_url(root.get(CARRIER_SRC_ATTR, ""), (origin,))
    carried = parse_carrier_url(root.get(CARRIER_SRC_ATTR, ""), allowed_origins)
    if (root.get(CARRIER_VERSION_ATTR) != CARRIER_VERSION or carried is None
            or carried["asset_id"] != identity["asset_id"]
            or carried["asset_commit"] != identity["asset_commit"]
            or carried["token"].lower() != identity["token"].lower()):
        fail("Downloaded SVG does not carry the resolved permanent source.")
    _write_private_file(output_path, content)
    return content


# ---------------------------------------------------------------------------
# SVG identity + dimension parsing
#
# NOTE: kept in sync (by hand for carrier validation) with the equivalent block in insert_chart.py and
# get_svg_info.py (both in this same scripts/ directory). If you change
# parsing behavior here, change it there too.
# ---------------------------------------------------------------------------

def parse_carrier_url(url: str, allowed_origins, require_commit=True) -> dict | None:
    """Full structural validation mirroring @grunt-io/react's carrier.ts
    `parseCarrierUrl` (design §6/§8): origin allowlist membership (which
    subsumes the "must be HTTPS" rule), no embedded credentials, no fragment,
    a `/{guid}` path (+ query `assetId` agreement if one happens to be
    present), a well-formed 64-hex `commit` appearing exactly once, and a
    structurally valid `token` appearing exactly once. Returns None on ANY
    failure -- never a partial/best-effort result. Does NOT validate the
    token's HASH (only the server can, from the raw secret bytes) -- see
    `is_structurally_valid_token`'s own docstring for what "structural" means
    here."""
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
        return None  # duplicate
    if len(query_asset_id_values) == 1 and query_asset_id_values[0].lower() != path_asset_id:
        return None  # path/query assetId disagreement

    commit_values = query.get("commit", [])
    if len(commit_values) > 1 or (commit_values and not COMMIT_PATTERN.fullmatch(commit_values[0])):
        return None
    if require_commit and not commit_values:
        return None
    commit = commit_values[0].lower() if commit_values else None

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
    """Extracts assetId/commitId from the legacy `<!-- assetId:...,commitId:...
    -->` fallback comment -- but ONLY from an actual XML comment node that is a
    DIRECT CHILD of the parsed root `<svg>` element, never by regex-scanning
    raw/decoded bytes. Regex-over-bytes could match lookalike text inside a
    CDATA section (expat merges CDATA into ordinary text -- it is never turned
    into a comment node, so this approach can't be fooled by one), inside a
    <script>/<style> block, in the document prolog/epilog (a comment before or
    after the root element entirely -- also never a child of the returned root
    Element), or nested arbitrarily deep inside a child element (excluded here
    by iterating `list(root)`, i.e. direct children only, not `root.iter()`).

    ElementTree drops comments by default; `TreeBuilder(insert_comments=True)`
    is what makes it retain them as nodes at all (tagged `ET.Comment`) instead
    of silently discarding them during parsing.
    """
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
    """Parse identity + dimensions from SVG bytes via a real XML parser.

    2026-08-27 P0 spike finding: ElementTree does NOT choke on `<!-- ... -->`
    comments, in-root or otherwise -- there is no need to strip them before
    parsing (the prior version of this skill did, and that stripping is exactly
    the bug that made insert_chart.py embed mangled bytes -- see insert_chart.py).
    So this function parses directly from `svg_bytes`, unmodified.

    `extra_trusted_origins` (from the repeatable --trust-origin CLI flag, zero
    or more, already validated and normalized by _validate_trust_origin) is
    trusted in ADDITION to `DEFAULT_ASSET_LINK_ORIGINS` when validating the
    embedded `data-grunt-src` carrier's own origin. This is deliberately NOT
    the origin the URL happened to be downloaded from: auto-trusting that was
    a confused-deputy/SSRF gap (a hostile or merely wrong download URL got
    fetched from ANY https origin, and that same origin was then trusted for
    this exact check) -- `download_svg` (above) now validates the download
    URL's origin against this SAME allowlist before ever issuing the request,
    so trust flows from the allowlist in both directions, never from
    whatever the URL itself happened to say.

    The final assetId/assetCommit -- from EITHER the carrier or the legacy
    comment fallback -- is always validated against strict GUID/64-hex patterns
    before being trusted; a value that fails this is treated the same as if it
    had never been found at all (never silently passed through as a tag/output
    value).
    """
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

    # Final validation: whatever source it came from, an identity value that
    # doesn't match its strict pattern is treated as absent, never passed
    # through as a tag/output value.
    if result["asset_id"] is not None and not GUID_PATTERN.match(result["asset_id"]):
        result["asset_id"] = None
    if result["asset_commit"] is not None and not COMMIT_PATTERN.match(result["asset_commit"]):
        result["asset_commit"] = None

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def read_url(args: argparse.Namespace) -> str:
    if args.url_file:
        url_path = Path(args.url_file)
        url = url_path.read_text(encoding="utf-8").strip()
        # Delete the URL file immediately after reading it -- it carries a
        # bearer token and has no reason to persist on disk any longer than
        # it takes to read it once. Best-effort: a deletion failure here must
        # never block the actual download.
        try:
            url_path.unlink()
        except OSError:
            pass
    else:
        url = sys.stdin.read().strip()

    if not url:
        fail("No URL provided. Pass --url-file, or pipe the URL on stdin.")
    return url


def _validate_trust_origin(value: str) -> str:
    """argparse `type=` callback for --trust-origin. Validates that `value` is
    a well-formed HTTPS origin -- scheme://host[:port], no userinfo, no path
    beyond an optional trailing slash, no query, no fragment, no whitespace or
    control characters -- and normalizes it to the same scheme://host[:port]
    shape parse_carrier_url's own allowlist membership check compares against
    (host/scheme lowercased via urlsplit, a port suffix only when one was
    explicit). Mirrors this script's own HTTPS-only, no-credentials,
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
    is a fixed, category-only message, mirroring this script's existing
    token-redaction discipline elsewhere (see `redact_url`/`fail`). For the
    same reason, `parsed.port` -- whose access can itself raise a raw
    ValueError for an out-of-range port, which argparse would otherwise
    report by quoting the original argv value verbatim -- is resolved inside
    this function's own protected block, never left to propagate past it."""
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


class _NoEchoArgumentParser(argparse.ArgumentParser):
    """A plain argparse.ArgumentParser subclass whose ONLY change is to
    `error()`. This script deliberately has NO positional `url` argument --
    the URL is read from stdin/--url-file specifically so it never touches
    argv at all (see read_url()'s own docstring: argv is visible to any other
    process/user on the machine via `ps`/Task Manager). But argparse's OWN
    default handling of a leftover/unrecognized positional argument builds
    its error message by joining the RAW argv values verbatim
    (`'unrecognized arguments: %s' % ' '.join(argv)`) and printing that to
    stderr -- so a caller who mistakenly passes the URL positionally (instead
    of via stdin/--url-file) would have its bearer token echoed to stderr by
    argparse ITSELF, bypassing every redaction convention this script
    otherwise follows (verified live). Every OTHER error path -- a missing
    required flag, this script's own --trust-origin ArgumentTypeError
    messages (which already never echo their candidate value -- see
    _validate_trust_origin's own docstring) -- is left completely untouched;
    only the "unrecognized arguments" message (the one built by joining raw
    argv) is replaced with a fixed, category-only message that never repeats
    any argument value."""

    def error(self, message):
        if message.startswith("unrecognized arguments"):
            message = "Unrecognized command-line arguments were given."
        super().error(message)


CSS_FONT_FAMILY_PATTERN = re.compile(r"""font-family\s*:\s*((?:"[^"]*"|'[^']*'|[^;}"'])+)""", re.IGNORECASE)


def svg_font_families(svg_bytes: bytes) -> list:
    """Font-family values from attributes, style attributes and <style> rules, in first-seen order."""
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return []
    values = []
    for element in root.iter():
        if element.get("font-family"):
            values.append(element.get("font-family"))
        css = [element.get("style") or ""]
        if element.tag in ("style", "{http://www.w3.org/2000/svg}style"):
            css.append(element.text or "")
        for text in css:
            values.extend(match.group(1) for match in CSS_FONT_FAMILY_PATTERN.finditer(text))
    families = []
    for value in values:
        family = " ".join(value.replace('"', "").replace("'", "").split())
        if family and family not in families:
            families.append(family)
    return families


def main():
    parser = _NoEchoArgumentParser(
        description="Download a Grunt chart SVG and extract identity metadata. "
        "The URL is never a command-line argument -- pass --url-file or pipe it on stdin."
    )
    parser.add_argument("--output", required=True, help="Output path for the SVG file")
    parser.add_argument(
        "--url-file", default=None,
        help="Path to a file containing the download URL (one line). Deleted "
        "immediately after being read. If omitted, the URL is read from stdin.",
    )
    parser.add_argument(
        "--trust-origin", action="append", default=[], dest="trust_origin",
        type=_validate_trust_origin, metavar="ORIGIN",
        help=(
            "Additional HTTPS origin to trust, in ADDITION to the built-in "
            "default (https://assets.grunt.io). Repeatable. Gates BOTH: (1) the "
            "origin the download URL itself may target -- a URL to any other "
            "origin is refused before any network request is made -- and (2) "
            "the downloaded SVG's own embedded data-grunt-src carrier. "
            "Origins are not secrets, so this is safe on the command line -- "
            "e.g. against a local capability server: --trust-origin "
            "https://localhost:7299. Matching is EXACT (e.g. "
            "https://assets.grunt.io:443 is a different entry than the default, "
            "fail-closed); give an IDN/Unicode host exactly as the URL "
            "presents it."
        ),
    )
    parser.add_argument(
        "--trust-delivery-origin", action="append", default=[],
        type=_validate_trust_origin, metavar="ORIGIN",
        help="Additional HTTPS origin for manifest-advertised SVG delivery only. "
             "Repeatable. Does not trust permanent sources or SVG carriers. "
             "Same-origin delivery is allowed by default.",
    )
    args = parser.parse_args()

    url = read_url(args)
    trusted_origins = tuple(args.trust_origin)
    allowed_origins = DEFAULT_ASSET_LINK_ORIGINS
    for origin in trusted_origins:
        if origin not in allowed_origins:
            allowed_origins = allowed_origins + (origin,)

    svg_bytes = download_svg(url, args.output, allowed_origins, args.trust_delivery_origin)
    metadata = parse_svg_metadata(svg_bytes, extra_trusted_origins=trusted_origins)

    result = {
        "svg_path": args.output,
        "asset_id": metadata["asset_id"],
        "asset_commit": metadata["asset_commit"],
        "carrier_found": metadata["carrier_found"],
        "svg_width": metadata["width"],
        "svg_height": metadata["height"],
        "aspect_ratio": (
            round(metadata["width"] / metadata["height"], 4)
            if metadata["width"] and metadata["height"]
            else None
        ),
        "file_size": len(svg_bytes),
        "font_families": svg_font_families(svg_bytes),
    }

    if metadata["asset_id"] is None or metadata["asset_commit"] is None:
        result["warning"] = (
            "Could not determine asset_id/asset_commit: the SVG has no valid "
            "data-grunt-src carrier attribute and no legacy identity comment "
            "(or what was found failed strict validation). insert_chart.py "
            "will not be able to auto-tag this chart."
        )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
