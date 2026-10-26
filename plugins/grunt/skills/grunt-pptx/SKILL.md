---
name: grunt-pptx
description: For agents that build PowerPoint (.pptx) files programmatically, outside PowerPoint. Inserts Grunt charts and tables into .pptx files as tagged Grunt objects, using the Grunt MCP server, permanent edit links, exact-size SVG downloads, batch slide assembly and rendered-deck checks. Not for use inside PowerPoint (Claude for PowerPoint, or any host with Grunt's deck_* tools), where grunt-powerpoint applies. Requires a signed-in Grunt MCP connection, which the skill checks first.
---

# Grunt charts and tables in .pptx files

This skill is for agents that build .pptx files with code, outside PowerPoint.
Inside PowerPoint (Claude for PowerPoint, or any host with Grunt's `deck_*` tools),
use the `grunt-powerpoint` skill instead.

Every Grunt chart or table in a deck is a vector SVG picture (with a PNG fallback)
tagged with its Grunt asset ID, pinned commit and permanent edit link. A Grunt
add-in that supports web assets can use those tags to load the complete Grunt
model for editing. Without that add-in the object is a static picture. Do not
claim native editing unless you tested it in the add-in.

The helpers live in this skill's `scripts/` folder. In the commands below,
`<skill-dir>` stands for the absolute path of the folder that contains this
SKILL.md; replace it yourself, because it is not an environment variable. Keep
the user's working files (SVGs, manifests, decks) in their own directory, never
in the skill or plugin folder.

## Before you start: check the Grunt connection

Do this before planning, installing anything or writing files. The Grunt MCP
server is `https://mcp.grunt.io/mcp`, and each user signs in with their own Grunt
account.

1. **Find the Grunt tools.** Look for tools whose names are, or end with,
   `create_or_update_bar_chart`, `create_asset_link` and `get_rendering_fonts`.
   Apps add their own prefixes to MCP tool names, so match the end of the name,
   not the server's name. If your app loads tools on demand or lets you search
   for tools, search for `create_asset_link` before deciding the tools are
   missing.
2. **Confirm the sign-in.** Call `get_rendering_fonts` once with no arguments. It
   only reads; it creates and changes nothing.
   - A list of font names: you are connected. Keep the list for choosing fonts.
   - An authentication error (for example 401, 403, "unauthorized", "sign in" or
     an expired token): you are not signed in. Go to step 3.
   - Any other error: try once more. If it fails again, tell the user that Grunt
     is not responding, quote the error, and stop.
3. **If the tools are missing or you are not signed in, stop.** Do not draw the
   charts another way, write placeholder images, install dependencies or go on
   to later steps. Tell the user:
   - Grunt isn't connected in this session.
   - To connect, they add or turn on the Grunt MCP server
     (`https://mcp.grunt.io/mcp`) in their app's MCP or connector settings and
     sign in with their Grunt account. If you know the exact steps for the app
     you are running in, give them; [CONNECT.md](CONNECT.md) lists some.
   - They should tell you when they are done.

   You cannot complete the sign-in yourself. Never ask the user for a password,
   token, code or callback URL.
4. **When the user says they are done,** repeat steps 1 and 2 once. If the tools
   still don't appear, tell the user that the app may need to reload its MCP
   servers (a new session or an app restart), and stop. Do not keep checking.

If more than one Grunt server is connected, choose one and use it for the whole
deliverable, so every asset is created and updated under the same account.

## One-time setup

Python 3.10+ is required. Install the helper dependencies once:

```sh
python -m pip install -r "<skill-dir>/requirements.txt"
```

`resvg-py` renders the PNG fallback without system libraries. CairoSVG (with the
native Cairo library) is used only if resvg-py is absent. LibreOffice is needed
for `render_deck.py`.

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
   to the `assetUrl` and write it to a private file with a file-writing tool, not
   a shell command — never put the URL on a command line or in logs:

   ```sh
   python "<skill-dir>/scripts/download_chart.py" --url-file private/revenue.url --output assets/revenue.svg
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
   python "<skill-dir>/scripts/insert_chart.py" --pptx skeleton.pptx --output final.pptx --manifest placements.json --revision-policy pinned
   ```

   The helper validates the whole batch, embeds the SVG bytes unchanged, writes
   the `GRUNT-WEB-*` tags, and saves atomically. `--fit contain` (default)
   centers without distortion; `--fit exact` requires a matching aspect ratio.
   Unknown fields, off-slide placements and invalid indexes are rejected — fix
   the request rather than bypassing validation.
7. **Verify the saved deck.**

   ```sh
   python "<skill-dir>/scripts/restore_assets.py" --pptx final.pptx --manifest final-assets.json
   python "<skill-dir>/scripts/render_deck.py" --pptx final.pptx --output-dir render
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

## Excel workbooks on the user's computer

When the user wants a chart or table from an Excel workbook on their computer
kept connected, linked or updating, give the asset a connection to that file.
Grunt in PowerPoint on that computer then refreshes it from the workbook.

1. **Use the workbook's full path on the user's computer**, such as
   `C:\Users\name\Documents\Sales.xlsx`. A path in a sandbox or cloud workspace,
   such as an uploaded copy, is not on their computer: ask the user where the
   original is, or make the asset without a connection and say so.
2. **Read the range yourself**, header row included, with the values exactly as
   the workbook holds them: no totals, reordering or rounding. With openpyxl,
   open the workbook with `data_only=True` so formulas give their last calculated
   values.
3. **Create the asset** with those values as `data` (for a table, `cells`) and
   `"dataImportDefinition": {"$type": "excel", "filePath": "<full path>", "range": "Sales!A1:E5"}`.
   The range is worksheet-qualified, or a named range, and matches the data's
   rows and columns.
4. **Check the connection.** `inspect_object` with `dataStructure: "Source"` shows
   `dataConnection.filePath`. If the create tool refuses `filePath`, this Grunt
   server cannot keep local connections yet: create the asset without
   `dataImportDefinition` and tell the user it is not connected.
5. **Tell the user** that the chart shows the values read now, and that Grunt in
   PowerPoint replaces them from the workbook when it refreshes, on the computer
   where the file is. Moving or renaming the workbook breaks the connection;
   Grunt's Data Connection Manager in PowerPoint can point it at the new place.

Never send `dataImportDefinition` without `filePath` or `workbookUrl`: the server
refuses it rather than make an asset that only looks connected.

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
substitution that matters. Before choosing a brand font, check it against the
`get_rendering_fonts` list from the connection check; the renderer substitutes
families it lacks and reports them as warnings. Prefer families that are also
widely installed (for example Segoe UI, Arial or Calibri) and confirm the
rendered result.

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
python "<skill-dir>/scripts/test_scripts.py"
python -m unittest discover -s "<skill-dir>/scripts" -p "test_*.py"
```
