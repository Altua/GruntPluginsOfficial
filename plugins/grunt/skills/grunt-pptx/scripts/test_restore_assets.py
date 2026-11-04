import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from pptx import Presentation
import restore_assets as ra
from insert_chart import add_grunt_web_chart_shape, insert_charts
from restore_assets import read_assets, restore_assets
from test_manifest_download import (ASSET, COMMIT, SOURCE, TOKEN, OBJECT_KEY, OBJECT_SVG, PAGE_OBJECT, DATA_SERVICE,
                                    RESOURCES, native_object, placement)
from test_pptx_quality import SVG


class RestoreAssetsTests(unittest.TestCase):
    def test_restores_exact_svg_and_safe_manifest_after_downloads_are_gone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = Presentation()
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            # The token-looking text must remain only in the recovered SVG, never the manifest.
            svg = b'<svg xmlns="http://www.w3.org/2000/svg" data-grunt-src="secret-capability"><text>Chart + legend</text></svg>'
            tags = {"GRUNT-WEB-ASSETID": "12345678-1234-1234-1234-123456789abc",
                    "GRUNT-WEB-ASSETCOMMIT": "a" * 64, "GRUNT-WEB-LINK": "secret-capability",
                    "GRUNT-WEB-REVISION-POLICY": "pinned"}
            add_grunt_web_chart_shape(slide, slide.part, svg, b"fallback", 10, 20, 300, 200, "Chart", tags)
            source = root / "source.pptx"
            deck.save(source)
            manifest = restore_assets(source, root / "restored", root / "manifest.json")
            self.assertEqual(len(manifest["charts"]), 1)
            chart = manifest["charts"][0]
            self.assertEqual(chart["boundsEmu"], {"left": 10, "top": 20, "width": 300, "height": 200})
            self.assertEqual(chart["revisionPolicy"], "pinned")
            self.assertEqual((root / "restored" / chart["filename"]).read_bytes(), svg)
            self.assertNotIn("secret-capability", json.dumps(manifest))
            self.assertEqual(len(manifest["finalAssetIds"]), 1)
            self.assertEqual(read_assets(source)[0], manifest)

    def test_invalid_identity_cannot_be_used_as_an_output_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = Presentation()
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            add_grunt_web_chart_shape(slide, slide.part, b'<svg xmlns="http://www.w3.org/2000/svg"/>', b"fallback",
                                     10, 20, 30, 40, "Chart", {"GRUNT-WEB-ASSETID": "../escape"})
            path = Path(directory) / "invalid.pptx"
            deck.save(path)
            with self.assertRaisesRegex(ValueError, "Invalid Grunt identity"):
                restore_assets(path, Path(directory) / "restored")

    def test_inventories_native_shapes_without_payloads_or_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = Presentation()
            deck.slides.add_slide(deck.slide_layouts[6])
            deck.save(root / "deck.pptx")
            (root / "chart.svg").write_bytes(SVG)
            legend_key, legend_svg = "7c9e6679-7425-40de-944b-e07fc1f90ae7", OBJECT_SVG.replace("720", "120")
            legend = native_object(pageObjectKey=legend_key, objectType="Legend", svg=legend_svg,
                                   svgBounds={"x": 600, "y": 72, "width": 90, "height": 45})
            (root / "revenue.pptx.json").write_text(json.dumps(placement(native_object(), legend) | {"source": SOURCE}))
            insert_charts(root / "deck.pptx", root / "final.pptx",
                          [dict(svg="chart.svg", slide=0, left=1, top=1, width=6, height=3),
                           {"pptx": "revenue.pptx.json", "slide": 0}], base_dir=root)
            manifest = restore_assets(root / "final.pptx", root / "restored", root / "final-assets.json")
            svg_chart, chart, legend_chart = manifest["charts"]
            self.assertEqual((False, "pinned"), (svg_chart["native"], svg_chart["revisionPolicy"]))
            self.assertNotIn("pageObjectKey", svg_chart)
            for entry, key in ((chart, OBJECT_KEY), (legend_chart, legend_key)):
                self.assertEqual((True, None, True, ASSET, COMMIT, key),
                                 (entry["native"], entry["revisionPolicy"], entry["hasEditLink"],
                                  entry["assetId"], entry["commit"], entry["pageObjectKey"]))
            self.assertEqual({"left": 600 * 12700, "top": 72 * 12700, "width": 90 * 12700, "height": 45 * 12700},
                             legend_chart["boundsEmu"])
            self.assertEqual(OBJECT_SVG.encode(), (root / "restored" / chart["filename"]).read_bytes())
            self.assertEqual(legend_svg.encode(), (root / "restored" / legend_chart["filename"]).read_bytes())
            self.assertEqual(sorted([ASSET, "11111111-1111-1111-1111-111111111111"]), manifest["finalAssetIds"])
            stdout = io.StringIO()
            with patch.object(sys, "argv", ["restore_assets.py", "--pptx", str(root / "final.pptx"),
                                               "--manifest", str(root / "again.json")]), redirect_stdout(stdout):
                ra.main()
            self.assertEqual({"charts": 3, "native": 2, "assets": 2, "projectStamped": False}, json.loads(stdout.getvalue()))
            for text in (stdout.getvalue(), (root / "final-assets.json").read_text()):
                for secret in (TOKEN, PAGE_OBJECT, DATA_SERVICE, RESOURCES):
                    self.assertNotIn(secret, text)

    def test_invalid_native_object_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = Presentation()
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            add_grunt_web_chart_shape(slide, slide.part, OBJECT_SVG.encode(), b"fallback", 10, 20, 30, 40, "Chart",
                                      {"GRUNT-PAGEOBJECT": "../escape", "GRUNT-X-PAGEOBJECT": PAGE_OBJECT,
                                       "GRUNT-WEB-ASSETID": ASSET, "GRUNT-WEB-ASSETCOMMIT": COMMIT})
            path = Path(directory) / "invalid.pptx"
            deck.save(path)
            with self.assertRaisesRegex(ValueError, "Invalid Grunt object key"):
                read_assets(path)


if __name__ == "__main__":
    unittest.main()
