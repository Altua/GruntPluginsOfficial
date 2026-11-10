"""Placeholders whose own <a:xfrm> PowerPoint reads differently from LibreOffice and python-pptx.

python-pptx writes only the part of a placeholder's transform that is set. PowerPoint then draws a
missing position at the slide's top-left corner and a missing size as zero, while LibreOffice and
python-pptx take both from the layout, so neither shows the problem.
"""
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.oxml import parse_xml
from pptx.util import Inches

import insert_chart
from pptx_validation import placeholder_geometry_problems
from test_pptx_quality import SVG

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
FUTURE = "http://example.com/presentationml/future"
TITLE_ONLY = 5  # a layout of python-pptx's default template
WIDTH_ONLY = 'Slide 1, placeholder "Title 1" (idx 0): no position, height 0.'
WIDTH_ONLY_ALTERNATE = 'Slide 1, placeholder "Title 1" (idx 0) in mc:AlternateContent: no position, height 0.'
LEFT_ONLY_ALTERNATE = 'Slide 1, placeholder "Title 1" (idx 0) in mc:AlternateContent: no size.'


def widen(title):
    title.width = Inches(9)


def move(title):
    title.left = Inches(2)


def set_all_four(title):
    title.left, title.top, title.width, title.height = title.left, title.top, Inches(9), title.height


def add_title_slide(presentation, change=None):
    slide = presentation.slides.add_slide(presentation.slide_layouts[TITLE_ONLY])
    slide.shapes.title.text = "Quarterly revenue by region"
    if change:
        change(slide.shapes.title)
    return slide


def save(presentation, directory):
    path = Path(directory) / "deck.pptx"
    presentation.save(path)
    return path


def title_xml(change):
    return add_title_slide(Presentation(), change).shapes.title._element.xml


def save_alternate_title(directory, choices, fallback):
    """A deck whose title is an mc:AlternateContent: an mc:Choice per (Requires, change), then the mc:Fallback.

    The prefixes p14 (an Office extension) and future (one no PowerPoint knows) are declared on the
    mc:AlternateContent.
    """
    presentation = Presentation()
    title = add_title_slide(presentation).shapes.title._element
    branches = "".join(f'<mc:Choice Requires="{requires}">{title_xml(change)}</mc:Choice>'
                       for requires, change in choices)
    title.getparent().replace(title, parse_xml(
        f'<mc:AlternateContent xmlns:mc="{MC}" xmlns:p14="{P14}" xmlns:future="{FUTURE}">{branches}'
        f'<mc:Fallback>{title_xml(fallback)}</mc:Fallback></mc:AlternateContent>'))
    return save(presentation, directory)


class PlaceholderGeometryTests(unittest.TestCase):
    def test_partial_and_zero_transforms_are_named_by_slide_and_shape(self):
        def rotate(title):
            title.rotation = 5

        def all_but_height(title):
            title.left, title.top, title.width = title.left, title.top, Inches(9)

        presentation = Presentation()
        for change in (widen, move, rotate, all_but_height, set_all_four, None):
            add_title_slide(presentation, change)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(placeholder_geometry_problems(save(presentation, tmp)), [
                WIDTH_ONLY,
                'Slide 2, placeholder "Title 1" (idx 0): no size.',
                'Slide 3, placeholder "Title 1" (idx 0): no position, no size.',
                'Slide 4, placeholder "Title 1" (idx 0): height 0.',
            ])

    def test_slides_are_numbered_in_the_order_the_deck_shows_them(self):
        presentation = Presentation()
        add_title_slide(presentation)
        add_title_slide(presentation, widen)
        slides = presentation.slides._sldIdLst
        second = slides[1]
        slides.remove(second)
        slides.insert(0, second)  # slide2.xml now comes first
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(placeholder_geometry_problems(save(presentation, tmp)), [WIDTH_ONLY])

    def test_shapes_that_are_not_placeholders_may_have_no_height(self):
        presentation = Presentation()
        slide = add_title_slide(presentation)
        slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(1), Inches(2), Inches(9), Inches(2))
        slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(3), Inches(8), 0)
        slide.shapes.add_textbox(Inches(1), Inches(4), Inches(8), Inches(1)).text_frame.text = "Source: Grunt"
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(placeholder_geometry_problems(save(presentation, tmp)), [])

    def test_a_graphic_frame_placeholder_is_checked_by_its_own_transform(self):
        presentation = Presentation()
        slide = add_title_slide(presentation)
        slide.shapes._spTree.append(parse_xml(
            f'<p:graphicFrame xmlns:p="{P}" xmlns:a="{A}"><p:nvGraphicFramePr><p:cNvPr id="9" name="Table 8"/>'
            '<p:cNvGraphicFramePr/><p:nvPr><p:ph idx="13"/></p:nvPr></p:nvGraphicFramePr>'
            '<p:xfrm><a:ext cx="914400" cy="914400"/></p:xfrm><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table"/></a:graphic>'
            '</p:graphicFrame>'))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(placeholder_geometry_problems(save(presentation, tmp)),
                             ['Slide 1, placeholder "Table 8" (idx 13): no position.'])

    def test_every_alternate_content_branch_is_checked(self):
        cases = [
            # The branch PowerPoint draws depends on the extensions its version knows, so each one counts.
            ([("p14", widen)], set_all_four, [WIDTH_ONLY_ALTERNATE]),
            ([("p14", set_all_four)], widen, [WIDTH_ONLY_ALTERNATE]),
            ([("future", widen), ("p14", set_all_four)], set_all_four, [WIDTH_ONLY_ALTERNATE]),
            ([("p14", widen)], move, [WIDTH_ONLY_ALTERNATE, LEFT_ONLY_ALTERNATE]),
            # A shape copied into several branches with the same problem is listed once.
            ([("p14", widen), ("future", widen)], widen, [WIDTH_ONLY_ALTERNATE]),
            ([("p14", set_all_four), ("future", set_all_four)], set_all_four, []),
        ]
        for choices, fallback, expected in cases:
            label = [(requires, change.__name__) for requires, change in choices], fallback.__name__
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(placeholder_geometry_problems(save_alternate_title(tmp, choices, fallback)), expected)

    def test_an_unreadable_deck_is_a_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            path.write_bytes(b"not a deck")
            with self.assertRaisesRegex(ValueError, "Could not read the deck"):
                placeholder_geometry_problems(path)


class InsertChartPlaceholderTests(unittest.TestCase):
    def insert(self, directory, change):
        presentation = Presentation()
        add_title_slide(presentation, change)
        deck = save(presentation, directory)
        (Path(directory) / "chart.svg").write_bytes(SVG)
        placement = dict(svg="chart.svg", slide=0, left=1, top=2, width=8, height=4)
        return insert_chart.insert_charts(deck, Path(directory) / "out.pptx", [placement], base_dir=Path(directory))

    def test_stops_before_saving_and_names_the_placeholder_and_the_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as caught:
                self.insert(tmp, widen)
            message = str(caught.exception)
            self.assertIn(WIDTH_ONLY, message)
            self.assertIn("top-left corner", message)
            self.assertIn("Fix: set all four together", message)
            self.assertFalse((Path(tmp) / "out.pptx").exists())

    def test_a_placeholder_with_its_whole_transform_is_accepted(self):
        def all_four(title):
            title.left, title.top, title.width, title.height = Inches(0.5), Inches(0.3), Inches(9), Inches(1.2)

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.insert(tmp, all_four)["inserted"], 1)


if __name__ == "__main__":
    unittest.main()
