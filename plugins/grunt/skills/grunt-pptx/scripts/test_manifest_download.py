"""Manifest discovery and source preservation across downloaded SVG/PPTX inputs."""
import base64
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import download_chart as dc

ASSET = "557db558-1234-4abc-9def-0123456789ab"
COMMIT = "a" * 64
LATEST = "b" * 64
TOKEN = "a" * 32 + "." + base64.b32encode(bytes(range(32))).decode().rstrip("=")
ORIGIN = "https://assets.grunt.io"
SOURCE = f"{ORIGIN}/{ASSET}?commit={COMMIT}&token={TOKEN}"
DELIVERY = ORIGIN + "/render-service-2031/opaque?signature=delivery-only"


def svg(source=SOURCE):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" '
            f'data-grunt-link-version="1" data-grunt-src="{source.replace("&", "&amp;")}">'
            '<rect width="400" height="200"/></svg>').encode()


def manifest():
    return {"schemaVersion": 1, "assetId": ASSET, "resolvedCommit": COMMIT,
            "latestCommit": LATEST, "scope": "view", "links": {
                "self": {"href": SOURCE, "type": "application/json", "schemaVersion": 1},
                "svg": {"href": DELIVERY, "type": "image/svg+xml"}
            }}


class Response(io.BytesIO):
    def __init__(self, content, content_type):
        super().__init__(content)
        self.headers = {"Content-Type": content_type}


class ManifestDownloadTests(unittest.TestCase):
    def run_download(self, body=None, image=None, url=SOURCE, delivery_origins=()):
        calls = []
        response = manifest() if body is None else body
        image = svg() if image is None else image

        class Opener:
            def open(self, request, timeout):
                calls.append(request.full_url)
                if len(calls) == 1:
                    return Response(json.dumps(response).encode(), "application/json")
                return Response(image, "image/svg+xml")

        with tempfile.TemporaryDirectory() as tmp, patch.object(dc, "build_opener", return_value=Opener()):
            output = Path(tmp) / "chart.svg"
            result = dc.download_svg(url, str(output), dc.DEFAULT_ASSET_LINK_ORIGINS, delivery_origins)
            self.assertEqual(output.read_bytes(), image)
            self.assertEqual(result, image)
        return calls

    def assert_rejected(self, body, image=None, expected_calls=1, delivery_origins=(), url=SOURCE):
        calls = []
        class Opener:
            def open(self, request, timeout):
                calls.append(request.full_url)
                if len(calls) == 1:
                    return Response(json.dumps(body).encode(), "application/json")
                return Response(svg() if image is None else image, "image/svg+xml")

        with tempfile.TemporaryDirectory() as tmp, patch.object(dc, "build_opener", return_value=Opener()):
            output = Path(tmp) / "chart.svg"
            output.write_bytes(b"previous usable SVG")
            error = io.StringIO()
            with redirect_stderr(error), redirect_stdout(error), self.assertRaises(SystemExit):
                dc.download_svg(url, str(output), dc.DEFAULT_ASSET_LINK_ORIGINS, delivery_origins)
            self.assertEqual(output.read_bytes(), b"previous usable SVG")
            self.assertNotIn(TOKEN, error.getvalue())
        self.assertEqual(len(calls), expected_calls)

    def test_follows_moved_url_exactly_and_preserves_permanent_reference(self):
        self.assertEqual(self.run_download(), [SOURCE, DELIVERY])
        self.assertNotIn(TOKEN, DELIVERY)

    def test_separate_delivery_host_requires_explicit_trust(self):
        body = manifest()
        delivery = "https://api.grunt.io/assets/svg?signature=opaque&w=300"
        body["links"]["svg"]["href"] = delivery
        self.assert_rejected(body)
        self.assertEqual(self.run_download(body, delivery_origins=("https://api.grunt.io",)), [SOURCE, delivery])

    def test_cli_explicit_delivery_origin_downloads_without_exposing_urls(self):
        body = manifest()
        delivery = "https://api.grunt.io/assets/svg?signature=opaque"
        body["links"]["svg"]["href"] = delivery
        calls = []
        class Opener:
            def open(self, request, timeout):
                calls.append(request.full_url)
                return (Response(json.dumps(body).encode(), "application/json") if len(calls) == 1
                        else Response(svg(), "image/svg+xml"))
        with tempfile.TemporaryDirectory() as tmp, patch.object(dc, "build_opener", return_value=Opener()):
            output = Path(tmp) / "chart.svg"
            result = io.StringIO()
            with patch.object(dc.sys, "argv", ["download_chart.py", "--output", str(output),
                    "--trust-delivery-origin", "https://api.grunt.io"]), \
                    patch.object(dc.sys, "stdin", io.StringIO(SOURCE)), redirect_stdout(result):
                dc.main()
            self.assertEqual(output.read_bytes(), svg())
            self.assertTrue(json.loads(result.getvalue())["carrier_found"])
            self.assertNotIn(TOKEN, result.getvalue())
            self.assertNotIn(delivery, result.getvalue())
        self.assertEqual(calls, [SOURCE, delivery])

    def test_delivery_trust_does_not_trust_a_relocated_permanent_source(self):
        body = manifest()
        relocated = SOURCE.replace(ORIGIN, "https://api.grunt.io")
        body["links"]["self"]["href"] = relocated
        self.assert_rejected(body, delivery_origins=("https://api.grunt.io",))
        self.assert_rejected(manifest(), svg(relocated), expected_calls=2,
                             delivery_origins=("https://api.grunt.io",))

    def test_removed_representation_selector_fails_before_network(self):
        for value in ("svg", "project", "data", "export"):
            self.assert_rejected(manifest(), url=SOURCE + "&format=" + value, expected_calls=0)

    def test_explicit_manifest_selector_still_discovers_svg(self):
        self.assertEqual(self.run_download(url=SOURCE + "&format=manifest"), [SOURCE + "&format=manifest", DELIVERY])

    def test_uppercase_input_guid_accepts_canonical_lowercase_source(self):
        source = SOURCE.replace(ASSET, ASSET.upper())
        self.assertEqual(self.run_download(url=source), [source, DELIVERY])

    def test_initial_latest_resolves_to_pinned_svg_once(self):
        source = f"{ORIGIN}/{ASSET}?token={TOKEN}"
        self.assertEqual(self.run_download(url=source), [source, DELIVERY])

    def test_bad_manifest_identity_never_downloads_or_replaces_svg(self):
        for field, value in [("schemaVersion", 2), ("schemaVersion", True),
                             ("assetId", "another"), ("assetId", None),
                             ("resolvedCommit", LATEST), ("links", [])]:
            with self.subTest(field=field, value=value):
                body = manifest()
                body[field] = value
                self.assert_rejected(body)

    def test_delivery_origin_credentials_fragment_and_scheme_are_rejected(self):
        for url in ["https://evil.test/render", "http://assets.grunt.io/render",
                    "https://user:pass@assets.grunt.io/render", DELIVERY + "#fragment", "javascript:bad"]:
            with self.subTest(url=url):
                body = manifest()
                body["links"]["svg"]["href"] = url
                self.assert_rejected(body)

    def test_wrong_self_and_svg_commit_fail_without_replacing_previous_output(self):
        body = manifest()
        body["links"]["self"]["href"] = SOURCE.replace(COMMIT, LATEST)
        self.assert_rejected(body)
        self.assert_rejected(manifest(), svg(SOURCE.replace(COMMIT, LATEST)), expected_calls=2)

    def test_delivery_link_cannot_become_svg_source(self):
        self.assert_rejected(manifest(), svg(DELIVERY), expected_calls=2)

    def test_non_svg_xml_never_replaces_previous_file(self):
        wrong_root = svg().replace(b"<svg ", b"<html ").replace(b"</svg>", b"</html>")
        self.assert_rejected(manifest(), wrong_root, expected_calls=2)

    def test_missing_svg_carrier_fails_for_connected_manifest(self):
        self.assert_rejected(manifest(), b'<svg xmlns="http://www.w3.org/2000/svg"/>', expected_calls=2)

    def test_image_representation_is_not_a_valid_carrier(self):
        self.assertIsNone(dc.parse_carrier_url(SOURCE + "&format=svg", dc.DEFAULT_ASSET_LINK_ORIGINS))


if __name__ == "__main__":
    unittest.main()
