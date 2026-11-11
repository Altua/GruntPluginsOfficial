"""Tests for slides_svg.py's offline conversion. Run from the repository root:
    python -m unittest discover -s plugins/grunt/skills/slides/scripts -p "test_*.py"
"""

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slides_svg  # noqa: E402

NS = {"s": "http://www.w3.org/2000/svg"}
TOKEN = "11111111111111111111111111111111.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
GRUNT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
  viewBox="0 0 831.75 360" width="831.75" height="360" data-grunt-link-version="1"
  data-grunt-src="https://assets.grunt.io/17be130b-3032-4002-a696-fe1a5410796b?commit={'a' * 64}&amp;token={TOKEN}">
<!-- assetId:17be130b-3032-4002-a696-fe1a5410796b,commitId:{'a' * 64} -->
<g transform="translate(0 47.75)"><svg viewBox="24 71.75 831.75 312.24" width="831.75" height="312.24">
<style>
/* fonts */
.f1a2b0{{font-size:44px;font-family:Noto Sans TC, sans-serif;fill:#000000}}
.f1a2b1{{font-size:44px;font-family:Noto Sans TC, sans-serif;fill:#ffffff;font-weight:bold;}}
</style>
<rect x="66" y="171" width="59" height="192" style="fill:#07272e;stroke-width:0" />
<g><text transform="translate(121,380) scale(0.25)"><tspan class="f1a2b0">Q1</tspan></text></g>
<g><text transform="translate(87,166) scale(0.25)"><tspan class="f1a2b1" style="fill:#ff0000">120</tspan></text></g>
<symbol id="i1"><image width="100" height="100" href="data:image/jpeg;base64,AAAA"/></symbol>
<image href="https://example.com/logo.png" width="10" height="10"/>
<script>alert(1)</script>
</svg></g></svg>""".encode("utf-8")


class MakeSlidesSafeTests(unittest.TestCase):
    def setUp(self):
        self.output, self.warnings = slides_svg.make_slides_safe(GRUNT_SVG)
        self.text = self.output.decode("utf-8")
        self.root = ET.fromstring(self.output)

    def test_text_styles_move_into_style_attributes(self):
        spans = self.root.findall(".//s:tspan", NS)
        self.assertEqual(spans[0].get("style"), "font-size:44px;font-family:Noto Sans TC, sans-serif;fill:#000000")
        # The element's own style wins over its class rule, as in CSS.
        self.assertEqual(spans[1].get("style"),
                         "font-size:44px;font-family:Noto Sans TC, sans-serif;fill:#ff0000;font-weight:bold")
        self.assertTrue(all(span.get("class") is None for span in spans))

    def test_no_link_or_identity_comment_survives(self):
        for fragment in ("data-grunt", "assets.grunt.io", TOKEN, "commitId", "<style", "class=", "<script", "example.com"):
            self.assertNotIn(fragment, self.text)

    def test_shapes_and_embedded_images_stay_with_a_warning(self):
        self.assertEqual(len(self.root.findall(".//s:rect", NS)), 1)
        self.assertEqual(len(self.root.findall(".//s:image", NS)), 1)
        self.assertTrue(any("embedded image" in warning for warning in self.warnings))
        self.assertTrue(any("<script>" in warning for warning in self.warnings))
        self.assertTrue(any("outside file" in warning for warning in self.warnings))

    def test_output_keeps_the_default_svg_namespace(self):
        self.assertTrue(self.text.startswith('<svg xmlns="http://www.w3.org/2000/svg"'))

    def test_size_comes_from_the_root(self):
        self.assertEqual(slides_svg.svg_size(self.root), (831.75, 360.0))

    def test_slide_box_is_twice_the_svg_points(self):
        # A 1109 x 480 px request arrives as 831.75 x 360 pt and fills 1664 x 720 slide px.
        self.assertEqual((slides_svg.slide_pixels(831.75), slides_svg.slide_pixels(360)), (1664, 720))

    def test_rejects_other_documents(self):
        with self.assertRaises(ValueError):
            slides_svg.make_slides_safe(b"<html/>")
        with self.assertRaises(ValueError):
            slides_svg.make_slides_safe(b"<svg")


def size_of(attributes):
    return slides_svg.svg_size(ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg" {attributes}/>'))


class SvgSizeTests(unittest.TestCase):
    def test_unitless_lengths_are_grunt_points(self):
        self.assertEqual(size_of('width="831.75" height="360"'), (831.75, 360.0))

    def test_absolute_units_convert_to_points(self):
        self.assertEqual(size_of('width="800pt" height="450pt"'), (800.0, 450.0))
        self.assertEqual(size_of('width="1109px" height="480px" viewBox="0 0 10 10"'), (831.75, 360.0))
        self.assertEqual(size_of('width="2in" height="1in"'), (144.0, 72.0))
        self.assertEqual(size_of('width="3pc" height="6pc"'), (36.0, 72.0))
        width, height = size_of('width="2.54cm" height="25.4mm"')
        self.assertAlmostEqual(width, 72.0)
        self.assertAlmostEqual(height, 72.0)

    def test_relative_or_missing_sides_use_the_viewbox(self):
        self.assertEqual(size_of('width="100%" height="100%" viewBox="0 0 400 300"'), (400.0, 300.0))
        self.assertEqual(size_of('width="800pt" viewBox="0 0 400 300"'), (800.0, 600.0))
        self.assertEqual(size_of('height="150pt" viewBox="0 0 400 300"'), (200.0, 150.0))
        self.assertEqual(size_of('width="0" height="10"'), (None, None))


class ExternalUrlTests(unittest.TestCase):
    SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">
<style>.outside{fill:url(http://x.test/paint);stroke:#123456}</style>
<defs><linearGradient id="grad"><stop offset="0" stop-color="#000"/></linearGradient></defs>
<rect id="a" fill="url(https://example.com/a)" width="10" height="10"/>
<rect id="b" style="fill:url('https://e.test/b');stroke:#000000" width="10" height="10"/>
<rect id="c" fill="url(#grad)" filter="url( &quot;https://e.test/f&quot; )" width="10" height="10"/>
<rect id="d" class="outside" width="10" height="10"/>
<rect id="e" style="fill:url(https://e.test/only)" width="10" height="10"/>
</svg>"""

    def setUp(self):
        output, self.warnings = slides_svg.make_slides_safe(self.SVG)
        self.text = output.decode("utf-8")
        self.rects = {r.get("id"): r for r in ET.fromstring(output).findall(".//s:rect", NS)}

    def test_no_outside_url_survives(self):
        for fragment in ("example.com", "e.test", "x.test"):
            self.assertNotIn(fragment, self.text)
        self.assertTrue(any("outside file" in warning for warning in self.warnings))

    def test_local_references_and_other_styles_stay(self):
        self.assertEqual(self.rects["c"].get("fill"), "url(#grad)")
        self.assertIsNone(self.rects["c"].get("filter"))
        self.assertIsNone(self.rects["a"].get("fill"))
        self.assertEqual(self.rects["b"].get("style"), "stroke:#000000")
        self.assertEqual(self.rects["d"].get("style"), "stroke:#123456")
        self.assertIsNone(self.rects["e"].get("style"))


if __name__ == "__main__":
    unittest.main()
