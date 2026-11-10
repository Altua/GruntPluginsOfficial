"""Run with python -m unittest discover -s skills/pptx/scripts -p test_pptx_quality.py."""
import copy
import json
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
import insert_chart
from pptx_validation import validate_ppt_svg, fit_placement, svg_viewport
from restore_assets import related_parts, tags_for
from test_manifest_download import (ASSET, COMMIT, LATEST, ORIGIN, SOURCE, TOKEN, OBJECT_KEY, OBJECT_SVG, PAGE_OBJECT,
                                    DATA_SERVICE, RESOURCES, SHAPE_BOUNDS, native_object, placement)

SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" width="720pt" height="360pt">
<!-- assetId:11111111-1111-1111-1111-111111111111,commitId:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->
<rect width="720" height="360" fill="#234"/><text x="20" y="60" fill="white" font-size="24">EUR millions</text></svg>'''


class PowerPointQualityTests(unittest.TestCase):
    def test_rejects_browser_snapshot_with_export_guidance(self):
        for svg in (SVG.replace(b'width="720pt"', b'data-grunt-scope="table1" width="720pt"'),
                    SVG.replace(b'<rect', b'<style>svg[data-grunt-scope="x"] .t {font-size:52px}</style><rect')):
            with self.subTest(svg=svg):
                with self.assertRaisesRegex(ValueError, 'download_chart.py'):
                    validate_ppt_svg(svg)

    def test_low_level_inserter_cannot_bypass_snapshot_guard(self):
        with self.assertRaisesRegex(ValueError, 'Browser snapshot'):
            insert_chart.add_grunt_web_chart_shape(None, None,
                SVG.replace(b'width="720pt"', b'data-grunt-scope="x" width="720pt"'),
                b'', 0, 0, 1, 1, 'test', {})

    def test_dimensions_respect_units_and_contain_without_distortion(self):
        root = validate_ppt_svg(SVG)
        self.assertEqual((960, 480), svg_viewport(root))
        self.assertEqual((1, 2, 8, 4), fit_placement(root, 1, 1, 8, 6))
        with self.assertRaisesRegex(ValueError, 'distort'):
            fit_placement(root, 1, 1, 8, 6, 'exact')

    def test_rejects_negative_nan_and_infinite_placements(self):
        for values in ((-1, 0, 8, 4), (0, 0, 0, 4), (0, 0, float('nan'), 4), (0, float('inf'), 8, 4)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                fit_placement(validate_ppt_svg(SVG), *values)

    def test_batch_is_atomic_loads_once_and_caches_rasterization(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            deck = directory / 'deck.pptx'
            output = directory / 'out.pptx'
            svg = directory / 'chart.svg'
            svg.write_bytes(SVG)
            presentation = Presentation()
            presentation.slide_width, presentation.slide_height = Inches(12), Inches(7)
            for _ in range(2):
                presentation.slides.add_slide(presentation.slide_layouts[6])
            presentation.save(deck)
            placements = [dict(svg='chart.svg', slide=n, left=1, top=1, width=8, height=4) for n in range(2)]
            # Use the real rasterizer once; inspect the actual saved package, not just function calls.
            with patch.object(insert_chart, 'Presentation', wraps=Presentation) as load, \
                    patch.object(insert_chart, 'svg_to_png', wraps=insert_chart.svg_to_png) as raster:
                result = insert_chart.insert_charts(deck, output, placements, base_dir=directory)
                self.assertEqual(1, load.call_count)
                self.assertEqual(1, raster.call_count)
            self.assertEqual(2, result['inserted'])
            with zipfile.ZipFile(output) as archive:
                svgs = [archive.read(name) for name in archive.namelist() if name.endswith('.svg')]
                self.assertEqual([SVG, SVG], svgs)
            saved = output.read_bytes()
            placements[1]['slide'] = -1
            with self.assertRaisesRegex(ValueError, 'slide index'):
                insert_chart.insert_charts(deck, output, placements, base_dir=directory)
            self.assertEqual(saved, output.read_bytes())

    def test_out_of_bounds_and_unknown_manifest_field_fail_before_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            deck, output = directory / 'deck.pptx', directory / 'out.pptx'
            p = Presentation()
            p.slides.add_slide(p.slide_layouts[6])
            p.save(deck)
            (directory / 'chart.svg').write_bytes(SVG)
            item = dict(svg='chart.svg', slide=0, left=8, top=1, width=8, height=4)
            with self.assertRaisesRegex(ValueError, 'beyond'):
                insert_chart.insert_charts(deck, output, [item], base_dir=directory)
            item['left'], item['widht'] = 1, 8
            with self.assertRaisesRegex(ValueError, 'Unknown fields'):
                insert_chart.insert_charts(deck, output, [item], base_dir=directory)
            self.assertFalse(output.exists())

    def test_preview_records_actual_size_and_no_capabilities(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            deck = directory / 'deck.pptx'
            p = Presentation()
            p.slides.add_slide(p.slide_layouts[6])
            p.save(deck)
            (directory / 'chart.svg').write_bytes(SVG)
            result = insert_chart.insert_charts(deck, directory / 'out.pptx',
                [dict(svg='chart.svg', slide=0, left=1, top=1, width=8, height=5)],
                base_dir=directory, preview_dir=directory / 'preview')
            from PIL import Image
            with Image.open(directory / 'preview/placement-001.png') as image:
                self.assertEqual((1152, 576), image.size)
            info = json.loads((directory / 'preview/placements.json').read_text())
            self.assertEqual(4, info['placements'][0]['placement_inches']['height'])
            self.assertNotIn('data-grunt-src', json.dumps(result))


P, A = 'http://schemas.openxmlformats.org/presentationml/2006/main', 'http://schemas.openxmlformats.org/drawingml/2006/main'
NATIVE_TAGS = {'GRUNT-PAGEOBJECT': OBJECT_KEY, 'GRUNT-X-PAGEOBJECT': PAGE_OBJECT, 'GRUNT-X-DATASERVICE': DATA_SERVICE,
               'GRUNT-X-RESOURCES': RESOURCES, 'GRUNT-X-SHAPEBOUNDS': SHAPE_BOUNDS, 'GRUNT-WEB-ASSETID': ASSET,
               'GRUNT-WEB-ASSETCOMMIT': COMMIT, 'GRUNT-WEB-LINK': SOURCE}
SVG_TAGS = {'GRUNT-WEB-ASSETID': '11111111-1111-1111-1111-111111111111', 'GRUNT-WEB-ASSETCOMMIT': 'a' * 64,
            'GRUNT-WEB-REVISION-POLICY': 'pinned'}
LEGEND_KEY, KPI_KEY = '7c9e6679-7425-40de-944b-e07fc1f90ae7', '3f2504e0-4f89-41d3-9a0c-0305e82c3301'
COPY_ASSET = '9b2f3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
NEW_CHART_KEY, NEW_LEGEND_KEY = '6fa459ea-ee8a-4ca4-894e-db77e160355e', '16fd2706-8baf-433b-82eb-8c7fada847da'


def read_chunked(tags, key):
    """ChunkedTagAdapter.GetValueWithChunks, as the add-in reads a tag back."""
    value = tags[key]
    if len(value) > 2 and value[0] == '-':
        count = value[1:].split('-', 1)[0]
        value = value[len(count) + 2:] + ''.join(tags[f'{key}-{index}'] for index in range(1, int(count)))
    return value


class NativePlacementTests(unittest.TestCase):
    """{"pptx": FILE, "slide": N} placements from download_chart.py --format pptx."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.deck, self.output = self.root / 'deck.pptx', self.root / 'out.pptx'
        presentation = Presentation()  # 10 x 7.5 in = 720 x 540 pt
        for _ in range(2):
            presentation.slides.add_slide(presentation.slide_layouts[6])
        presentation.save(self.deck)
        (self.root / 'chart.svg').write_bytes(SVG)

    def native_file(self, *objects, name='revenue.pptx.json', source=SOURCE, **changes):
        document = placement(*objects, **changes)
        if source is not None:
            document['source'] = source
        (self.root / name).write_text(json.dumps(document), encoding='utf-8')
        return name

    def legend_file(self, name='with-legend.pptx.json', **changes):
        """A chart and its separate legend, the two objects of a chart with a side legend."""
        legend = native_object(pageObjectKey=LEGEND_KEY, objectType='Chart Legend',
                               svgBounds={'x': 600.75, 'y': 30.25, 'width': 100.5, 'height': 60})
        return self.native_file(native_object(), legend, name=name, **changes)

    def edit_output(self, change):
        """Applies change(deck) to the saved output and returns the edited copy's path."""
        deck, edited = Presentation(self.output), self.root / 'edited.pptx'
        change(deck)
        deck.save(edited)
        return edited

    def add_in_object(self, deck, slide, key):
        """A shape as the add-in creates it, such as a legend added there: GRUNT-PAGEOBJECT and no asset ID."""
        shape = deck.slides[slide].shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, 1, 1)
        insert_chart.add_tags_to_element(deck.slides[slide].part, shape._element.nvSpPr.nvPr, {'GRUNT-PAGEOBJECT': key})

    def insert(self, placements, **options):
        return insert_chart.insert_charts(self.deck, self.output, placements, base_dir=self.root, **options)

    def shapes(self, slide=0):
        """[(EMU rectangle, tags, embedded SVG bytes)] for each tagged shape on a saved slide."""
        with zipfile.ZipFile(self.output) as archive:
            part = f'ppt/slides/slide{slide + 1}.xml'
            relationships = related_parts(archive, part)
            result = []
            for shape in ET.fromstring(archive.read(part)).iter(f'{{{P}}}sp'):
                tags = tags_for(archive, shape, relationships)
                if tags:
                    off, ext = shape.find(f'{{{P}}}spPr/{{{A}}}xfrm/{{{A}}}off'), shape.find(f'{{{P}}}spPr/{{{A}}}xfrm/{{{A}}}ext')
                    svg = shape.find('.//{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip')
                    embed = svg.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                    rectangle = tuple(int(v) for v in (off.get('x'), off.get('y'), ext.get('cx'), ext.get('cy')))
                    result.append((rectangle, tags, archive.read(relationships[embed])))
            return result

    def test_native_shape_has_the_add_in_tags_at_the_exact_svg_bounds(self):
        result = self.insert([{'pptx': self.native_file(), 'slide': 1}])
        [(rectangle, tags, svg)] = self.shapes(1)
        self.assertEqual((36 * 12700, 72 * 12700, 540 * 12700, 4210050), rectangle)
        self.assertEqual(NATIVE_TAGS, tags)
        self.assertEqual(OBJECT_SVG.encode(), svg)
        self.assertEqual(self.shapes(0), [])
        self.assertTrue(result['native'] and result['web_link_tag_written'])
        self.assertEqual({'left': 0.5, 'top': 1.0, 'width': 7.5, 'height': 4.6042}, result['placement_inches'])
        for secret in (SOURCE, PAGE_OBJECT, DATA_SERVICE, RESOURCES):
            self.assertNotIn(secret, json.dumps(result))

    def test_absent_optional_payloads_write_no_tags(self):
        item = native_object(dataServiceBase64=None)
        del item['resourcesBase64'], item['shapeBoundsBase64']
        self.insert([{'pptx': self.native_file(item), 'slide': 0}])
        [(_, tags, _)] = self.shapes()
        self.assertEqual({key: NATIVE_TAGS[key] for key in NATIVE_TAGS if key not in
                          ('GRUNT-X-DATASERVICE', 'GRUNT-X-RESOURCES', 'GRUNT-X-SHAPEBOUNDS')}, tags)

    def test_an_object_is_placed_at_most_once_per_slide(self):
        # A repeated chart is cloned on load, but its cloned legend stays bound to the first chart.
        name = self.native_file()
        with self.assertRaisesRegex(ValueError, 'already placed on slide 1'):
            self.insert([{'pptx': name, 'slide': 0}, {'pptx': name, 'slide': 0}])
        self.assertFalse(self.output.exists())
        self.assertEqual(2, self.insert([{'pptx': name, 'slide': 0}, {'pptx': name, 'slide': 1}])['inserted'])

    def test_an_asset_with_a_separate_legend_is_placed_once_per_deck(self):
        # Seen live: a repeated legend on another slide was bound to that slide's other chart.
        name = self.legend_file()
        with self.assertRaisesRegex(ValueError, 'already placed on slide 1. An asset with several objects'):
            self.insert([{'pptx': name, 'slide': 0}, {'pptx': name, 'slide': 1}])
        self.assertFalse(self.output.exists())

    def test_a_chart_only_version_conflicts_with_a_version_with_a_legend_in_either_order(self):
        # Versions keep the chart key, and a new legend beside a re-keyed chart loses its chart.
        chart_only, with_legend = self.native_file(), self.legend_file()
        for first, second in ((chart_only, with_legend), (with_legend, chart_only)):
            with self.subTest(first=first), self.assertRaisesRegex(ValueError, 'appears once per deck'):
                self.insert([{'pptx': first, 'slide': 0}, {'pptx': second, 'slide': 1}])
        self.assertFalse(self.output.exists())

    def test_a_duplicated_asset_is_named_with_its_original(self):
        copy = self.legend_file(name='copy.pptx.json', assetId=COPY_ASSET)
        with self.assertRaisesRegex(ValueError, f'asset {COPY_ASSET} has the object keys of asset {ASSET}, '
                                                'already placed on slide 1'):
            self.insert([{'pptx': self.legend_file(), 'slide': 0}, {'pptx': copy, 'slide': 1}])

    def test_objects_already_in_the_deck_count_toward_both_rules(self):
        with_legend = self.legend_file()
        kpis = self.native_file(native_object(pageObjectKey=KPI_KEY), name='kpis.pptx.json', assetId=COPY_ASSET)
        self.insert([{'pptx': with_legend, 'slide': 0}, {'pptx': kpis, 'slide': 0}])
        again = self.root / 'again.pptx'
        for item, message in (({'pptx': with_legend, 'slide': 1}, 'appears once per deck'),
                              ({'pptx': kpis, 'slide': 0}, 'once per slide')):
            with self.subTest(item=item), self.assertRaisesRegex(ValueError, f'already placed on slide 1. .*{message}'):
                insert_chart.insert_charts(self.output, again, [item], base_dir=self.root)
        self.assertFalse(again.exists())
        # A single object may still repeat on another slide in a later run.
        result = insert_chart.insert_charts(self.output, again, [{'pptx': kpis, 'slide': 1}], base_dir=self.root)
        self.assertEqual(1, result['inserted'])

    def test_a_version_with_new_object_keys_still_counts_as_the_asset(self):
        legend = native_object(pageObjectKey=NEW_LEGEND_KEY, objectType='Chart Legend')
        version = self.native_file(native_object(pageObjectKey=NEW_CHART_KEY), legend, name='v2.pptx.json',
                                   projectCommitKey=LATEST, source=None)
        for first, second in ((self.legend_file(), version), (self.native_file(), version),
                              (version, self.native_file())):
            with self.subTest(first=first), self.assertRaisesRegex(ValueError, f'asset {ASSET} is already placed '
                                                                              'on slide 1. .*appears once per deck'):
                self.insert([{'pptx': first, 'slide': 0}, {'pptx': second, 'slide': 1}])
        self.assertFalse(self.output.exists())

    def test_an_add_in_object_without_an_asset_id_counts_as_placed_with_the_others_on_its_slide(self):
        chart = self.native_file()
        self.insert([{'pptx': chart, 'slide': 1}])
        edited, again = self.edit_output(lambda deck: self.add_in_object(deck, 1, LEGEND_KEY)), self.root / 'again.pptx'
        with self.assertRaisesRegex(ValueError, 'already placed on slide 2. .*appears once per deck'):
            insert_chart.insert_charts(edited, again, [{'pptx': chart, 'slide': 0}], base_dir=self.root)
        self.assertFalse(again.exists())

    def test_an_add_in_object_with_the_same_key_is_named_as_a_grunt_object(self):
        self.insert([{'pptx': self.native_file(native_object(pageObjectKey=KPI_KEY), name='kpis.pptx.json'),
                      'slide': 0}])
        edited = self.edit_output(lambda deck: self.add_in_object(deck, 1, OBJECT_KEY))
        with self.assertRaisesRegex(ValueError, 'shares object keys with a Grunt object on slide 2. Place an asset'):
            insert_chart.insert_charts(edited, self.root / 'again.pptx', [{'pptx': self.native_file(), 'slide': 1}],
                                       base_dir=self.root)

    def test_a_copy_of_an_object_on_the_same_slide_is_not_a_second_object(self):
        # PowerPoint copies the tags, and the add-in re-keys the copy's model but not its GRUNT-PAGEOBJECT.
        chart = self.native_file()
        self.insert([{'pptx': chart, 'slide': 1}])

        def copy_chart(deck):
            tree = deck.slides[1].shapes._spTree
            tree.append(copy.deepcopy(tree[-1]))

        for name, change in (('copy', copy_chart),
                             ('copy without an asset ID', lambda deck: self.add_in_object(deck, 1, OBJECT_KEY))):
            with self.subTest(name):
                result = insert_chart.insert_charts(self.edit_output(change), self.root / 'again.pptx',
                                                    [{'pptx': chart, 'slide': 0}], base_dir=self.root)
                self.assertEqual(1, result['inserted'])

    def test_multi_object_asset_becomes_one_shape_per_object(self):
        legend_key = '7c9e6679-7425-40de-944b-e07fc1f90ae7'
        legend = native_object(pageObjectKey=legend_key, objectType='Legend', resourcesBase64=None,
                               svgBounds={'x': 600.75, 'y': 30.25, 'width': 100.5, 'height': 60})
        result = self.insert([{'pptx': self.native_file(native_object(), legend), 'slide': 0}])
        self.assertEqual(2, result['inserted'])
        (chart_rectangle, chart, _), (legend_rectangle, legend_tags, _) = self.shapes()
        self.assertEqual((OBJECT_KEY, legend_key), (chart['GRUNT-PAGEOBJECT'], legend_tags['GRUNT-PAGEOBJECT']))
        self.assertEqual((7629525, 384175, 1276350, 762000), legend_rectangle)
        self.assertNotIn('GRUNT-X-RESOURCES', legend_tags)
        self.assertEqual(ASSET, legend_tags['GRUNT-WEB-ASSETID'])

    def test_chunking_matches_the_add_in_at_its_digit_boundaries(self):
        # With 10-character pieces: "-9-" + 87 fills 9 pieces, "-10-" + 88..96 fills 10, "-11-" + 97 needs 11.
        for length, chunks in ((10, 1), (11, 2), (87, 9), (88, 10), (96, 10), (97, 11)):
            with self.subTest(length=length):
                value = ''.join(chr(65 + n % 26) for n in range(length))
                pieces = insert_chart.chunk_tag_value('KEY', value, max_size=10)
                self.assertEqual(['KEY'] + [f'KEY-{n}' for n in range(1, chunks)], list(pieces))
                self.assertTrue(all(len(piece) <= 10 for piece in pieces.values()))
                self.assertEqual(value, read_chunked(pieces, 'KEY'))
        limit = insert_chart.MAX_TAG_CHUNK_LENGTH
        self.assertEqual(5242800, limit)
        self.assertEqual({'KEY': 'A' * limit}, insert_chart.chunk_tag_value('KEY', 'A' * limit))

    def test_payload_just_over_the_limit_is_chunked_in_the_saved_deck(self):
        limit = insert_chart.MAX_TAG_CHUNK_LENGTH
        payload = 'A' * (limit + 4)  # valid base64, one piece too long
        self.insert([{'pptx': self.native_file(native_object(pageObjectBase64=payload)), 'slide': 0}])
        [(_, tags, _)] = self.shapes()
        self.assertEqual(('-2-' + payload)[:limit], tags['GRUNT-X-PAGEOBJECT'])
        self.assertEqual('AAAAAAA', tags['GRUNT-X-PAGEOBJECT-1'])
        self.assertNotIn('GRUNT-X-PAGEOBJECT-2', tags)
        self.assertEqual(payload, read_chunked(tags, 'GRUNT-X-PAGEOBJECT'))
        self.assertEqual(DATA_SERVICE, tags['GRUNT-X-DATASERVICE'])

    def test_mixed_manifest_leaves_the_svg_path_unchanged(self):
        svg_item = dict(svg='chart.svg', slide=0, left=1, top=1, width=8, height=4)
        name = self.native_file()
        for policy in ('pinned', 'latest'):
            with self.subTest(policy=policy):
                svg_only = self.insert([svg_item], revision_policy=policy)
                [svg_alone] = [(rectangle, tags) for rectangle, tags, _ in self.shapes()]
                mixed = self.insert([svg_item, {'pptx': name, 'slide': 0}, {'pptx': name, 'slide': 1}],
                                    revision_policy=policy)
                (svg_rectangle, svg_tags, _), (_, native_tags, _) = self.shapes()
                self.assertEqual(svg_alone, (svg_rectangle, svg_tags))
                self.assertEqual(SVG_TAGS | {'GRUNT-WEB-REVISION-POLICY': policy}, svg_tags)
                self.assertEqual(NATIVE_TAGS, native_tags)
                self.assertEqual([NATIVE_TAGS], [tags for _, tags, _ in self.shapes(1)])
                self.assertEqual(svg_only['placements'][0], mixed['placements'][0])
                self.assertEqual(3, mixed['inserted'])
                self.assertEqual(policy == 'latest', 'note' in mixed)

    def test_native_entries_take_no_rectangle_or_unknown_fields(self):
        name = self.native_file()
        for item in ({'pptx': name, 'slide': 0, 'left': 1, 'top': 1},
                     {'pptx': name, 'slide': 0, 'width': 4, 'height': 3},
                     {'pptx': name, 'svg': 'chart.svg', 'slide': 0}, {'pptx': name}):
            with self.subTest(item=item), self.assertRaisesRegex(ValueError, 'only pptx and slide'):
                self.insert([item])
        with self.assertRaisesRegex(ValueError, 'local file path'):
            self.insert([{'pptx': '', 'slide': 0}])
        with self.assertRaisesRegex(ValueError, 'slide index'):
            self.insert([{'pptx': name, 'slide': 2}])
        self.assertFalse(self.output.exists())

    def test_off_slide_or_invalid_objects_fail_before_save(self):
        for bounds in ({'x': 500, 'y': 0, 'width': 300, 'height': 100}, {'x': 0, 'y': 500, 'width': 100, 'height': 100},
                       {'x': -1, 'y': 0, 'width': 100, 'height': 100}):
            with self.subTest(bounds=bounds), self.assertRaisesRegex(ValueError, 'beyond the slide'):
                self.insert([{'pptx': self.native_file(native_object(svgBounds=bounds)), 'slide': 0}])
        with self.assertRaisesRegex(ValueError, 'base64.*--format pptx'):
            self.insert([{'pptx': self.native_file(native_object(pageObjectBase64='not base64')), 'slide': 0}])
        self.assertFalse(self.output.exists())
        # The full slide is allowed: 720 x 540 pt.
        self.insert([{'pptx': self.native_file(native_object(svgBounds={'x': 0, 'y': 0, 'width': 720, 'height': 540})),
                      'slide': 0}])
        self.assertEqual([(0, 0, 9144000, 6858000)], [rectangle for rectangle, _, _ in self.shapes()])

    def test_export_float_noise_at_the_slide_edge_is_not_off_slide(self):
        # The export reports a stacked bar at the slide origin as x = -7e-15, y = -1.4e-05 pt.
        bounds = {'x': -7.105427357601002e-15, 'y': -1.359738791251175e-05, 'width': 440, 'height': 215.0000136}
        self.insert([{'pptx': self.native_file(native_object(svgBounds=bounds)), 'slide': 0}])
        self.assertEqual([(0, 0, 440 * 12700, 2730500)], [rectangle for rectangle, _, _ in self.shapes()])

    def test_an_untrusted_origin_stops_the_batch_and_names_the_flag(self):
        # Seen in an E2E run against staging: a warning in the JSON went unnoticed, and the deck lost its links.
        origin = 'https://localhost:7299'
        local = SOURCE.replace(ORIGIN, origin)
        name = self.native_file(name='local.pptx.json', source=local)
        with self.assertRaises(ValueError) as raised:
            self.insert([{'pptx': self.native_file(), 'slide': 0}, {'pptx': name, 'slide': 1}])
        message = str(raised.exception)
        self.assertIn(f'Placement 1: its asset link is on {origin}, which is not a trusted origin', message)
        self.assertIn(f'pass --trust-origin {origin} to insert_chart.py', message)
        self.assertNotIn(TOKEN, message)
        self.assertFalse(self.output.exists())
        result = self.insert([{'pptx': name, 'slide': 0}], trusted_origins=(origin,))
        self.assertEqual(local, self.shapes()[0][1]['GRUNT-WEB-LINK'])
        self.assertNotIn('warning', result)

    def test_a_source_that_is_no_link_to_this_version_omits_the_link_with_a_warning(self):
        # No --trust-origin would bring these links back, so the placement goes in without one.
        local = SOURCE.replace(ORIGIN, 'https://localhost:7299')
        for source in (SOURCE.replace(COMMIT, LATEST), local.replace(COMMIT, LATEST), SOURCE + '#fragment',
                       'not a url', None):
            with self.subTest(source=source and source[:40]):
                result = self.insert([{'pptx': self.native_file(source=source), 'slide': 0}])
                [(_, tags, _)] = self.shapes()
                self.assertNotIn('GRUNT-WEB-LINK', tags)
                self.assertEqual(ASSET, tags['GRUNT-WEB-ASSETID'])
                self.assertIn('No GRUNT-WEB-LINK', result['warning'])


if __name__ == '__main__':
    unittest.main()
