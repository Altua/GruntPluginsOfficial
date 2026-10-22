---
name: grunt-pptx
description: Insert Grunt charts and tables into PowerPoint (.pptx) decks as tagged Grunt objects, using the bundled Grunt MCP, permanent edit links, exact-size SVG downloads, batch slide assembly and rendered-deck checks. Use whenever Grunt assets go into a PPTX.
---

# Grunt charts and tables in PowerPoint

Every Grunt chart or table in a deck is a vector SVG picture (with a PNG fallback)
tagged with its Grunt asset ID, pinned commit and permanent edit link. A Grunt
add-in that supports web assets can use those tags to load the complete Grunt
model for editing. Without that add-in the object is a static picture. Do not
claim native editing unless you tested it in the add-in.

The helpers live in this skill's `scripts/` directory. Always call them by
absolute path, for example `python "${CLAUDE_SKILL_DIR}/scripts/insert_chart.py"`,
and keep the user's working files (SVGs, manifests, decks) in their own
directory, never in the plugin folder.

## One-time setup

Python 3.10+ is required. Install the helper dependencies once:

```sh
python -m pip install -r "${CLAUDE_SKILL_DIR}/requirements.txt"
```

`resvg-py` renders the PNG fallback without system libraries. CairoSVG (with the
native Cairo library) is used only if resvg-py is absent. LibreOffice is needed
for `render_deck.py`. The Grunt MCP tools come from this plugin's **Grunt**
server; if they are missing, ask the user to authenticate it with `/mcp`.

## Workflow

1. **Plan each placement first.** Decide every asset's final slide rectangle in
   inches (a 16:9 slide is 13.333 × 7.5 in). The render size in CSS pixels is
   inches × 96: a 7.5 × 4.6 in placement is 720 × 442 px. A table across a
   widescreen slide is about 12.1 in (1162 px) wide.
2. **Create the assets** with the Grunt MCP `create_or_update_*` tools. Keep each
   `assetId` and the latest `assetCommit`.
3. **Mint one edit link per asset per deck**: `create_asset_link` with
   `permission: "edit"`. Reuse it for repeated placements of that asset in the
   same deck; mint a new one for a different deck. Its `assetUrl` is the
   permanent JSON manifest source, pinned to the commit current when it was
   minted, so mint links after the asset is final.
4. **Download the SVG at the placement size.** Append `&width=<px>&height=<px>`
   to the `assetUrl` and write it to a private file with the Write tool — never
   put the URL on a command line or in logs:

   ```sh
   python "${CLAUDE_SKILL_DIR}/scripts/download_chart.py" --url-file private/revenue.url --output assets/revenue.svg
   ```

   The helper follows the manifest's `links.svg.href`, checks HTTPS, response
   types, redirects, size and identity, deletes the URL file after reading it,
   and prints no tokens. It reports `svg_width`/`svg_height` in points
   (px × 0.75) and the SVG's `font_families`; confirm both match the plan.
5. **Prepare the deck skeleton** (the user's template, or python-pptx). Leave the
   chart rectangles empty.
6. **Insert all assets in one operation.** Write a placements manifest; paths are
   relative to the manifest, positions and sizes are inches, slides are
   zero-based:

   ```json
   [
     {"svg": "assets/revenue.svg", "slide": 0, "left": 0.6, "top": 1.7, "width": 7.5, "height": 4.6},
     {"svg": "assets/kpi-table.svg", "slide": 1, "left": 0.6, "top": 1.7, "width": 12.1, "height": 4.4}
   ]
   ```

   ```sh
   python "${CLAUDE_SKILL_DIR}/scripts/insert_chart.py" --pptx skeleton.pptx --output final.pptx --manifest placements.json --revision-policy pinned
   ```

   The helper validates the whole batch, embeds the SVG bytes unchanged, writes
   the `GRUNT-WEB-*` tags, and saves atomically. `--fit contain` (default)
   centers without distortion; `--fit exact` requires a matching aspect ratio.
   Unknown fields, off-slide placements and invalid indexes are rejected — fix
   the request rather than bypassing validation.
7. **Verify the saved deck.**

   ```sh
   python "${CLAUDE_SKILL_DIR}/scripts/restore_assets.py" --pptx final.pptx --manifest final-assets.json
   python "${CLAUDE_SKILL_DIR}/scripts/render_deck.py" --pptx final.pptx --output-dir render
   ```

   `restore_assets.py` inventories asset IDs, commits, policy, edit-link presence
   and placements without printing tokens. Then work through
   [ACCEPTANCE.md](ACCEPTANCE.md):
   - values, units and headline claims match the source data;
   - every rendered slide is readable at presentation size, with no clipping,
     distortion or overlap with slide text;
   - fonts render as intended or the substitution is acceptable;
   - every asset has the intended commit, revision policy and edit link.

   Build and check one chart slide and one table slide before scaling up a large
   deck. Tell the user which renderer you used (LibreOffice results do not prove
   PowerPoint rendering) and whether native editing was tested.

For a single asset, `insert_chart.py --svg chart.svg --pptx in.pptx --output
out.pptx --slide 0 --left 0.6 --top 1.3 --width 8 --height 4` is equivalent.

## Sizing rules

Ask Grunt to lay out each asset at its real placement size so labels, ticks and
legends adapt. Do not shrink a full-slide SVG into a half-slide box or enlarge a
compact one; the same asset at substantially different sizes needs separate
downloads of the same pinned commit. Matching aspect ratio alone is not enough.

## Fonts and colors

Fonts inside the SVG do not follow the slide theme. Grunt sets them in the SVG's
`<style>` rules, which `download_chart.py` reports as `font_families`; PowerPoint
substitutes families the viewer has not installed. Production charts currently
render axis and legend text in Noto Sans TC, which many PCs lack. Data-label
`style` tokens (for example `"style": "Segoe UI"` on `segmentLabels`) and
`settings.font.fontFamily` on tables do set the family; axis and legend text
keep the default. Check the rendered slide and tell the user about any
substitution that matters. When the server exposes `get_rendering_fonts`, call it before choosing
a brand font and read its warnings. Otherwise prefer widely installed families
(for example Segoe UI, Arial or Calibri) and confirm the rendered result.

Choose the chart palette when authoring the Grunt asset (theme color names or
explicit colors). Keep the original series colors and SVG bytes in the deck.
Grunt's orange hover and teal selection are editing feedback, never data colors;
put lasting emphasis in the chart or an annotation.

## Link and identity rules

- Use only the plain SVG advertised by the permanent manifest. Never insert
  browser snapshot SVGs with `data-grunt-scope` CSS (the helper rejects them) and
  never strip or rewrite SVG bytes to get past a check.
- The SVG's `data-grunt-src` carries the permanent pinned source; the helper
  copies it into `GRUNT-WEB-LINK`. Never replace it with a delivery URL.
- `pinned` (default) imports the saved commit. Pass `--revision-policy latest`
  only when the deck should adopt the latest version at first native import.
- `https://assets.grunt.io` is trusted by default. Other capability origins need
  an explicit `--trust-origin`; a separate SVG delivery host needs
  `--trust-delivery-origin`. Never trust an origin because it appears in a
  response.
- `asset_id`/`asset_commit` manifest overrides (or `--asset-id`/`--asset-commit`)
  are a last resort for SVGs without a carrier; they intentionally omit the link.
- Edit links are permanent bearer capabilities: anyone holding the deck can use
  them. Tell the user when a delivered deck contains edit links. Treat
  downloaded and recovered SVGs as private files.

## Recovery

`restore_assets.py --output-dir <dir>` writes the exact embedded SVGs back out for
rebuilding a deck after the original downloads are gone. Grouped Grunt shapes
must be ungrouped first. If asset-project tools are available, keep one project
per deliverable and stamp its ID in the final file.

For a paired HTML report, see [HTML.md](HTML.md) and the `grunt-html` skill.

## Tests

```sh
python "${CLAUDE_SKILL_DIR}/scripts/test_scripts.py"
python -m unittest discover -s "${CLAUDE_SKILL_DIR}/scripts" -p "test_*.py"
```
