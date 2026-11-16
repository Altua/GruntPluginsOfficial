"""Manifest discovery and source preservation across downloaded SVG/PPTX inputs."""
import base64
import copy
import io
import json
import re
import tempfile
import unittest
import zipfile
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


PLACED_SOURCE = SOURCE + "&x=48&y=96&width=720&height=442"
PPTX_DELIVERY = f"{ORIGIN}/assets/pptx?assetId={ASSET}&commit={COMMIT}&token={TOKEN}&x=48&y=96&width=720&height=442"
OBJECT_KEY = "0f8fad5b-d9cb-469f-a165-70867728950e"
OBJECT_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="720" height="442">'
              '<style>.a{font-family:Segoe UI}</style><rect width="720" height="442"/></svg>')
PAGE_OBJECT = base64.b64encode(b"serialized page object " * 4).decode()
DATA_SERVICE = base64.b64encode(b"serialized data service").decode()
RESOURCES = base64.b64encode(b"serialized resources").decode()
SHAPE_BOUNDS = base64.b64encode(b"serialized rectangle").decode()
RENDER_HASH = "0123456789abcdef0123456789abcdef-svg"


def edit_manifest():
    body = manifest()
    body["scope"] = "edit"
    body["links"]["pptx"] = {"href": PPTX_DELIVERY, "type": "application/json", "schemaVersion": 1}
    return body


def native_object(**changes):
    item = {"pageObjectKey": OBJECT_KEY, "objectType": "Line plot Chart", "svg": OBJECT_SVG,
            "svgBounds": {"x": 36.0, "y": 72.0, "width": 540.0, "height": 331.5},
            "pageObjectBase64": PAGE_OBJECT, "dataServiceBase64": DATA_SERVICE, "resourcesBase64": RESOURCES,
            "shapeBoundsBase64": SHAPE_BOUNDS}
    item.update(changes)
    return item


def placement(*objects, **changes):
    body = {"schemaVersion": 1, "assetId": ASSET, "projectCommitKey": COMMIT,
            "objects": list(objects) or [native_object()]}
    body.update(changes)
    return body


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

    def test_svg_mode_ignores_the_native_link_of_an_edit_manifest(self):
        self.assertEqual(self.run_download(edit_manifest()), [SOURCE, DELIVERY])


class NativePlacementDownloadTests(unittest.TestCase):
    """--format pptx: links.pptx is followed like links.svg and saved as one private JSON file."""

    @staticmethod
    def serve(manifest_body, placement_body, calls):
        class Opener:
            def open(self, request, timeout):
                calls.append(request.full_url)
                body = manifest_body if len(calls) == 1 else placement_body
                return Response(body if isinstance(body, bytes) else json.dumps(body).encode(), "application/json")
        return patch.object(dc, "build_opener", return_value=Opener())

    def download(self, manifest_body=None, placement_body=None, delivery_origins=()):
        calls = []
        with tempfile.TemporaryDirectory() as tmp, \
                self.serve(manifest_body or edit_manifest(), placement_body or placement(), calls):
            output = Path(tmp) / "revenue.pptx.json"
            result = dc.download_pptx(PLACED_SOURCE, str(output), dc.DEFAULT_ASSET_LINK_ORIGINS, delivery_origins)
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(saved, result)
        return calls, saved

    def assert_rejected(self, manifest_body=None, placement_body=None, expected_calls=2, message=None,
                        delivery_origins=()):
        calls, stream = [], io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, \
                self.serve(manifest_body or edit_manifest(), placement_body or placement(), calls):
            output = Path(tmp) / "revenue.pptx.json"
            output.write_bytes(b"previous placement")
            with redirect_stderr(stream), redirect_stdout(stream), self.assertRaises(SystemExit):
                dc.download_pptx(PLACED_SOURCE, str(output), dc.DEFAULT_ASSET_LINK_ORIGINS, delivery_origins)
            self.assertEqual(output.read_bytes(), b"previous placement")
        for secret in (TOKEN, PAGE_OBJECT, DATA_SERVICE, RESOURCES):
            self.assertNotIn(secret, stream.getvalue())
        self.assertEqual(len(calls), expected_calls)
        if message:
            self.assertIn(message, stream.getvalue())

    def test_follows_pptx_link_exactly_and_saves_the_pinned_source(self):
        calls, saved = self.download()
        self.assertEqual(calls, [PLACED_SOURCE, PPTX_DELIVERY])
        self.assertEqual(saved["source"], SOURCE)
        self.assertEqual((saved["assetId"], saved["projectCommitKey"]), (ASSET, COMMIT))
        self.assertEqual(saved["objects"], [native_object()])

    def test_cli_reads_and_deletes_the_url_file_and_prints_no_tokens_or_payloads(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp, self.serve(edit_manifest(), placement(), calls):
            url_file, output = Path(tmp) / "revenue.url", Path(tmp) / "revenue.pptx.json"
            url_file.write_text(PLACED_SOURCE + "\n", encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(dc.sys, "argv", ["download_chart.py", "--format", "pptx", "--url-file", str(url_file),
                                               "--output", str(output)]), redirect_stdout(stdout):
                dc.main()
            self.assertFalse(url_file.exists())
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["source"], SOURCE)
        for secret in (TOKEN, PAGE_OBJECT, DATA_SERVICE, RESOURCES, "<svg"):
            self.assertNotIn(secret, stdout.getvalue())
        summary = json.loads(stdout.getvalue())
        self.assertEqual((summary["asset_id"], summary["asset_commit"], summary["object_count"]), (ASSET, COMMIT, 1))
        self.assertEqual(summary["objects"], [{"page_object_key": OBJECT_KEY, "object_type": "Line plot Chart",
                                               "bounds_inches": {"left": 0.5, "top": 1.0, "width": 7.5, "height": 4.604}}])
        self.assertEqual(summary["font_families"], ["Segoe UI"])
        self.assertEqual(calls, [PLACED_SOURCE, PPTX_DELIVERY])

    def test_failed_placement_points_to_the_svg_fallback(self):
        # 404: an oversized placement. 401: an asset host without the placement route.
        for status in (404, 401):
            with self.subTest(status=status):
                class Opener:
                    def __init__(self):
                        self.calls = 0

                    def open(self, request, timeout):
                        self.calls += 1
                        if self.calls == 1:
                            return Response(json.dumps(edit_manifest()).encode(), "application/json")
                        raise dc.HTTPError(request.full_url, status, "Error", {}, None)

                stream = io.StringIO()
                with tempfile.TemporaryDirectory() as tmp, patch.object(dc, "build_opener", return_value=Opener()), \
                        redirect_stderr(stream), redirect_stdout(stream), self.assertRaises(SystemExit):
                    dc.download_pptx(PLACED_SOURCE, str(Path(tmp) / "revenue.pptx.json"), dc.DEFAULT_ASSET_LINK_ORIGINS)
                self.assertIn(f"status {status}", stream.getvalue())
                self.assertIn("use the SVG fallback", stream.getvalue())
                self.assertNotIn(TOKEN, stream.getvalue())

    def test_missing_pptx_link_points_to_the_svg_flow(self):
        body = edit_manifest()
        del body["links"]["pptx"]
        self.assert_rejected(body, expected_calls=1, message="Use the SVG flow")

    def test_view_scope_is_refused_even_with_a_pptx_link(self):
        for scope in ("view", None):
            with self.subTest(scope=scope):
                body = edit_manifest()
                body["scope"] = scope
                self.assert_rejected(body, expected_calls=1, message="needs an edit link")

    def test_invalid_pptx_link_is_refused_before_download(self):
        for change in ({"type": "image/svg+xml"}, {"schemaVersion": 2}, {"href": None}):
            with self.subTest(change=change):
                body = edit_manifest()
                body["links"]["pptx"].update(change)
                self.assert_rejected(body, expected_calls=1)

    def test_identity_mismatch_never_replaces_previous_output(self):
        for changes in ({"assetId": "11111111-2222-3333-4444-555555555555"}, {"projectCommitKey": LATEST},
                        {"projectCommitKey": COMMIT.upper()}, {"schemaVersion": 2}, {"schemaVersion": True}):
            with self.subTest(changes=changes):
                self.assert_rejected(placement_body=placement(**changes))

    def test_bad_base64_payloads_are_rejected_without_echoing_them(self):
        for changes in ({"pageObjectBase64": "not base64!"}, {"pageObjectBase64": ""}, {"pageObjectBase64": None},
                        {"dataServiceBase64": ""}, {"dataServiceBase64": "abc"}, {"resourcesBase64": "@@@@"},
                        {"resourcesBase64": PAGE_OBJECT[:-1]}):
            with self.subTest(changes=changes):
                self.assert_rejected(placement_body=placement(native_object(**changes)), message="base64")

    def test_invalid_objects_are_rejected(self):
        scoped = OBJECT_SVG.replace("<svg ", '<svg data-grunt-scope="x" ')
        for body in (placement(objects=[]), placement(objects={}), b"not json",
                     placement(native_object(svg=scoped)), placement(native_object(svg="<html/>")),
                     placement(native_object(objectType="")), placement(native_object(pageObjectKey="key")),
                     placement(native_object(svgBounds={"x": 0, "y": 0, "width": 0, "height": 10})),
                     placement(native_object(svgBounds={"x": 0, "y": float("nan"), "width": 1, "height": 1})),
                     placement(native_object(), native_object())):
            with self.subTest(body=str(body)[:80]):
                self.assert_rejected(placement_body=body)

    def test_response_cap_is_16_mib(self):
        large = placement(native_object(pageObjectBase64="A" * (11 * 1024 * 1024)))
        self.assertEqual(len(self.download(placement_body=large)[1]["objects"][0]["pageObjectBase64"]), 11 * 1024 * 1024)
        with patch.object(dc, "MAX_PPTX_RESPONSE_BYTES", 256):
            self.assert_rejected(message="256-byte cap")

    def test_pptx_delivery_follows_the_svg_origin_rules(self):
        for href in ("https://evil.test/assets/pptx", "http://assets.grunt.io/assets/pptx",
                     PPTX_DELIVERY + "#fragment", "https://user:pass@assets.grunt.io/assets/pptx"):
            with self.subTest(href=href):
                body = edit_manifest()
                body["links"]["pptx"]["href"] = href
                self.assert_rejected(body, expected_calls=1)
        body = edit_manifest()
        body["links"]["pptx"]["href"] = "https://api.grunt.io/assets/pptx?signature=opaque"
        self.assert_rejected(body, expected_calls=1)
        calls, _ = self.download(body, delivery_origins=("https://api.grunt.io",))
        self.assertEqual(calls, [PLACED_SOURCE, "https://api.grunt.io/assets/pptx?signature=opaque"])

    def test_absent_optional_payloads_are_not_saved(self):
        item = native_object(dataServiceBase64=None)
        del item["resourcesBase64"], item["shapeBoundsBase64"]
        _, saved = self.download(placement_body=placement(item))
        self.assertEqual(set(saved["objects"][0]),
                         {"pageObjectKey", "objectType", "svg", "svgBounds", "pageObjectBase64"})

    def test_multi_object_asset_keeps_every_object(self):
        legend = native_object(pageObjectKey="7c9e6679-7425-40de-944b-e07fc1f90ae7", objectType="Legend",
                               svgBounds={"x": 600, "y": 72, "width": 120, "height": 60})
        _, saved = self.download(placement_body=placement(native_object(), legend))
        self.assertEqual([item["objectType"] for item in saved["objects"]], ["Line plot Chart", "Legend"])

    def test_render_hash_is_saved_and_a_malformed_one_is_rejected(self):
        _, saved = self.download(placement_body=placement(native_object(renderHash=RENDER_HASH)))
        self.assertEqual(saved["objects"][0]["renderHash"], RENDER_HASH)
        for value in ("", "two words", 'quote"', 7, "a" * 101):
            with self.subTest(value=value):
                self.assert_rejected(placement_body=placement(native_object(renderHash=value)), message="renderHash")

    def test_theme_font_of_the_followed_link_is_saved(self):
        body = edit_manifest()
        body["links"]["pptx"]["href"] += "&themeFont=Aptos%20Display"
        self.assertEqual(self.download(body)[1]["themeFont"], "Aptos Display")
        # A server that does not know themeFont yet leaves it out of the link.
        self.assertNotIn("themeFont", self.download()[1])


class DeckThemeFontTests(unittest.TestCase):
    """--deck and --slide: the slide's theme font goes to the server as themeFont."""

    def deck(self, directory, heading_font):
        """A two-slide deck whose theme names heading_font, as (latin, east asian, complex script)."""
        from pptx import Presentation
        presentation = Presentation()
        for _ in range(2):
            presentation.slides.add_slide(presentation.slide_layouts[6])
        original, path = Path(directory) / "original.pptx", Path(directory) / "deck.pptx"
        presentation.save(original)
        fonts = "".join(f'<a:{script} typeface="{name}"/>' for script, name in zip(("latin", "ea", "cs"), heading_font))
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(path, "w") as target:
            for item in source.infolist():
                data = source.read(item)
                if item.filename.startswith("ppt/theme/theme"):
                    data = re.sub(rb"<a:majorFont>.*?</a:majorFont>",
                                  f"<a:majorFont>{fonts}</a:majorFont>".encode(), data, flags=re.S)
                target.writestr(item, data)
        return str(path)

    def test_heading_font_is_latin_then_east_asian_then_complex_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            for fonts, expected in ((("Aptos Display", "Yu Gothic", ""), "Aptos Display"), (("", "Yu Gothic", "Arial"), "Yu Gothic"),
                                    (("", "", "Arial"), "Arial"), (("", "", ""), None)):
                with self.subTest(fonts=fonts):
                    self.assertEqual(dc.deck_theme_font(self.deck(tmp, fonts), 1), expected)

    def test_source_url_gets_the_font_once_and_keeps_one_it_has(self):
        self.assertEqual(dc.with_theme_font(PLACED_SOURCE, "Aptos Display"), PLACED_SOURCE + "&themeFont=Aptos%20Display")
        self.assertEqual(dc.with_theme_font(PLACED_SOURCE + "&themeFont=Arial", "Calibri"), PLACED_SOURCE + "&themeFont=Arial")
        self.assertEqual(dc.with_theme_font(PLACED_SOURCE, "R&D Sans"), PLACED_SOURCE + "&themeFont=R%26D%20Sans")

    def run_cli(self, tmp, *arguments):
        calls, stream = [], io.StringIO()
        url_file, output = Path(tmp) / "revenue.url", Path(tmp) / "revenue.pptx.json"
        url_file.write_text(PLACED_SOURCE, encoding="utf-8")
        body = edit_manifest()
        body["links"]["pptx"]["href"] += "&themeFont=Aptos%20Display"
        argv = ["download_chart.py", "--url-file", str(url_file), "--output", str(output), *arguments]
        with NativePlacementDownloadTests.serve(body, placement(native_object(renderHash=RENDER_HASH)), calls), \
                patch.object(dc.sys, "argv", argv), redirect_stdout(stream), redirect_stderr(stream):
            try:
                dc.main()
            except SystemExit:
                return calls, None, url_file.exists(), stream.getvalue()
        return calls, json.loads(stream.getvalue()), url_file.exists(), stream.getvalue()

    def test_cli_sends_the_slides_theme_font_and_reports_what_the_server_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck = self.deck(tmp, ("Aptos Display", "", ""))
            calls, summary, _, output = self.run_cli(tmp, "--format", "pptx", "--deck", deck, "--slide", "1")
        self.assertEqual(calls[0], PLACED_SOURCE + "&themeFont=Aptos%20Display")
        self.assertEqual((summary["theme_font"], summary["render_hash"]), ("Aptos Display", True))
        self.assertNotIn(TOKEN, output)

    def test_cli_without_a_deck_sends_no_font(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls, _, _, _ = self.run_cli(tmp, "--format", "pptx")
        self.assertEqual(calls[0], PLACED_SOURCE)

    def test_wrong_deck_arguments_stop_before_the_url_file_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck = self.deck(tmp, ("Calibri", "", ""))
            for arguments in (("--format", "pptx", "--deck", deck), ("--format", "pptx", "--slide", "0"),
                              ("--deck", deck, "--slide", "0"), ("--format", "pptx", "--deck", deck, "--slide", "2"),
                              ("--format", "pptx", "--deck", str(Path(tmp) / "missing.pptx"), "--slide", "0")):
                with self.subTest(arguments=arguments[:4]):
                    calls, summary, url_file_kept, output = self.run_cli(tmp, *arguments)
                    self.assertEqual((calls, summary, url_file_kept), ([], None, True))
                    self.assertNotIn(TOKEN, output)


if __name__ == "__main__":
    unittest.main()
