---
name: grunt-pptx
description: For agents that build PowerPoint (.pptx) files programmatically, outside PowerPoint. Inserts Grunt charts and tables into .pptx files as native Grunt objects, using the Grunt MCP server, permanent edit links, exact-placement downloads, batch slide assembly and rendered-deck checks. Not for use inside PowerPoint (Claude for PowerPoint, or any host with Grunt's deck_* tools), where grunt-powerpoint applies. Requires a signed-in Grunt MCP connection, which the skill checks first.
---

# Grunt charts and tables in .pptx files

This skill is for agents that build .pptx files with code, outside PowerPoint.
Inside PowerPoint (Claude for PowerPoint, or any host with Grunt's `deck_*` tools),
use the `grunt-powerpoint` skill instead.

Every Grunt chart or table in a deck is a vector SVG picture (with a PNG fallback)
tagged with its Grunt asset ID, pinned commit and permanent edit link. By default
each one also carries the Grunt add-in's own object tags, so the deck opens like
one the add-in saved: nothing is downloaded on first open, so large decks do not
freeze, the deck works offline, and every Grunt add-in user can edit the charts
without the `FetchWebAssetsOnLoad` flag. When the server offers no native
placement, use the [SVG fallback](#svg-fallback). Without the add-in every object
is a static picture. Do not claim native editing unless you tested it in the add-in.

The helpers live in this skill's `scripts/` folder. In the commands below,
`<skill-dir>` stands for the absolute path of the folder that contains this
SKILL.md; replace it yourself, because it is not an environment variable. Keep
the user's working files (downloads, manifests, decks) in their own directory,
never in the skill or plugin folder.

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

The helpers need Python 3.10+ and the packages in `requirements.txt`, pinned to
the versions they are tested with. Check whether your Python has them:

```sh
python -c "import pptx, lxml, resvg_py, pypdfium2"
```

If it does not, create a virtual environment in the user's working folder, not
in the skill folder, and install them there (about 40 MB):

```sh
python -m venv .grunt-venv
.grunt-venv/bin/python -m pip install -r "<skill-dir>/requirements.txt"
```

On Windows the interpreter is `.grunt-venv\Scripts\python.exe`. Use it wherever
the commands below say `python`. The helpers also run under `python -I`.

`resvg-py` renders each picture's PNG fallback, and `pypdfium2` turns a
LibreOffice render into PNG pages.

On Windows, `render_deck.py` renders the deck with the user's PowerPoint, the
renderer the recipient uses. It opens the deck read-only without a window, loads
the user's add-ins (Grunt included), and leaves a PowerPoint the user already
has open, and their presentations, as they were. Without PowerPoint (on macOS,
on Linux, or when PowerPoint cannot be started) it falls back to LibreOffice, a
large separate install: ask the user before installing it
(`winget install TheDocumentFoundation.LibreOffice`,
`brew install --cask libreoffice` or `sudo apt-get install libreoffice-impress`).
Do not add LibreOffice's program folder to `PATH`, because it has its own
`python`; pass `--soffice` when the helper does not find it. With neither, skip
`render_deck.py` and tell the user the slides were not rendered.

## Workflow

1. **Plan each placement first.** Decide every asset's final slide rectangle in
   inches (a 16:9 slide is 13.333 × 7.5 in). Positions and sizes in CSS pixels
   are inches × 96, rounded: a 7.5 × 4.6 in chart 0.6 in from the left and 1.7 in
   from the top is `x=58&y=163&width=720&height=442`. A table across a
   widescreen slide is about 12.1 in (1162 px) wide.
2. **Create the assets** with the Grunt MCP `create_or_update_*` tools. Keep each
   `assetId` and the latest `assetCommit`.
3. **Mint one edit link per asset per deck**: `create_asset_link` with
   `permission: "edit"`. Reuse it for repeated placements of that asset in the
   same deck; mint a new one for a different deck. Its `assetUrl` is the
   permanent JSON manifest source, pinned to the commit current when it was
   minted, so mint links after the asset is final.
4. **Download each placement.** Append `&x=<px>&y=<px>&width=<px>&height=<px>`
   to the `assetUrl` and write it to a private file with a file-writing tool, not
   a shell command — never put the URL on a command line or in logs:

   ```sh
   python "<skill-dir>/scripts/download_chart.py" --format pptx --url-file private/revenue.url --output assets/revenue.pptx.json
   ```

   The helper follows the manifest's `links.pptx.href` unchanged, checks HTTPS,
   response types, redirects, size and identity, deletes the URL file after
   reading it, and prints no tokens or chart data. It reports each object's type
   and slide rectangle in inches and the SVG `font_families`; confirm both match
   the plan. One asset can return several objects (for example a chart and its
   legend); each becomes its own shape. Every placement of an asset, including a
   repeat on another slide, needs its own download at its own position. Place an
   asset at most once per slide, and an asset with several objects at most once
   per deck, counting its other versions and duplicates: the add-in can bind a
   repeated legend to another chart. For another copy, create a new asset (a
   duplicate keeps the original's object keys). If the helper reports no
   `links.pptx` (an older server), or the native download fails with any HTTP
   error (a 404 for an asset too large for a native placement, another status
   from an asset host that cannot place assets yet), use the
   [SVG fallback](#svg-fallback) for that asset and tell the user.
5. **Prepare the deck skeleton** (the user's template, or python-pptx). Leave the
   chart rectangles empty.
6. **Insert all assets in one operation.** Write a placements manifest; paths are
   relative to the manifest and slides are zero-based. The rectangle comes from
   the download, so entries take no position or size:

   ```json
   [
     {"pptx": "assets/revenue.pptx.json", "slide": 0},
     {"pptx": "assets/kpi-table.pptx.json", "slide": 1}
   ]
   ```

   ```sh
   python "<skill-dir>/scripts/insert_chart.py" --pptx skeleton.pptx --output final.pptx --manifest placements.json
   ```

   The helper validates the whole batch, also against the native objects already
   in the input deck, embeds each object's SVG unchanged at its exact rectangle,
   writes the native and `GRUNT-WEB-*` tags, and saves atomically. Unknown
   fields, off-slide rectangles and invalid indexes are rejected — re-download
   to move or resize, rather than bypassing validation.
7. **Verify the saved deck.**

   ```sh
   python "<skill-dir>/scripts/restore_assets.py" --pptx final.pptx --manifest final-assets.json
   python "<skill-dir>/scripts/render_deck.py" --pptx final.pptx --output-dir render
   ```

   `restore_assets.py` inventories asset IDs, commits, native object keys,
   policy, edit-link presence and placements without printing tokens or chart
   data. Then work through [ACCEPTANCE.md](ACCEPTANCE.md):
   - values, units and headline claims match the source data;
   - every rendered slide is readable at presentation size, with no clipping,
     distortion or overlap with slide text;
   - fonts render as intended or the substitution is acceptable;
   - every asset is native (or a deliberate fallback) with the intended commit
     and edit link.

   `render_deck.py` reports its `renderer`. If PowerPoint opens the deck but
   cannot render it, the helper stops rather than fall back: the recipient's
   PowerPoint would fail too, so fix the deck. `--renderer libreoffice` skips
   PowerPoint.

   Build and check one chart slide and one table slide before scaling up a large
   deck. Tell the user which renderer you used (LibreOffice results do not prove
   PowerPoint rendering) and whether native editing was tested; a PowerPoint
   render is not a test of editing.

## SVG fallback

Use it only when the manifest has no `links.pptx` or the native download of that
asset fails. The fallback shapes carry just
the `GRUNT-WEB-*` tags: an add-in with web-asset support downloads each model on
first open, one at a time while PowerPoint waits, so large fallback decks are
slow to open. Tell the user.

- Append only `&width=<px>&height=<px>` and omit `--format`. The helper follows
  `links.svg` and reports `svg_width`/`svg_height` in points (px × 0.75) and
  `font_families`:

  ```sh
  python "<skill-dir>/scripts/download_chart.py" --url-file private/revenue.url --output assets/revenue.svg
  ```

- Placements give the rectangle in inches, and may sit in the same manifest as
  native ones:
  `{"svg": "assets/revenue.svg", "slide": 0, "left": 0.6, "top": 1.7, "width": 7.5, "height": 4.6}`.
  `--fit contain` (default) centers without distortion; `--fit exact` requires a
  matching aspect ratio.
- `--revision-policy pinned` (default) imports the saved commit; `latest` adopts
  the latest version at first import. It does not apply to native shapes.
- For a single asset, `insert_chart.py --svg chart.svg --pptx in.pptx --output
  out.pptx --slide 0 --left 0.6 --top 1.3 --width 8 --height 4` is equivalent.

## Excel workbooks on the user's computer

When the user wants a chart or table from an Excel workbook on their computer
kept connected, linked or updating, give the asset a connection to that file.
Grunt in PowerPoint on that computer then refreshes it from the workbook.

1. **Use the workbook's full path on the user's computer**, such as
   `C:\Users\name\Documents\Sales.xlsx`. A path in a sandbox or cloud workspace,
   such as an attached file's copy, is not on their computer; if you have only a
   copy, see "Only a copy" below.
2. **Read the range yourself**, header row included, with the values exactly as
   the workbook holds them: no totals, reordering or rounding. With openpyxl,
   open the workbook with `data_only=True` so formulas give their last calculated
   values.
3. **Create the asset** with those values as `data` (for a table, `cells.values`) and
   `"dataImportDefinition": {"$type": "excel", "filePath": "<full path>", "range": "Sales!A1:E5"}`.
   The range is worksheet-qualified, or a named range, and matches the data's
   rows and columns.
4. **Check the connection.** `inspect_object` with `dataStructure: "Source"` shows
   `dataConnection.filePath`. If the create tool refuses `filePath`, this Grunt
   server cannot keep local connections yet: create the asset without
   `dataImportDefinition` and tell the user it is not connected.
5. **Download and insert as usual.** The connection is stored in the asset, so
   the edit link, `download_chart.py` and `insert_chart.py` carry it; the
   placements manifest needs nothing extra.
6. **Tell the user** that the deck shows the values read now. The connection
   takes effect only when the deck is opened in PowerPoint, on the computer
   where the workbook is, with a Grunt add-in that supports web assets: it
   imports the picture as a Grunt object, and from then on refreshes it from the
   workbook. Until then the object is a static picture. Unless you opened the
   deck in PowerPoint with Grunt yourself, say that you have not seen it
   refresh. Moving or renaming the workbook breaks the connection; Grunt's Data
   Connection Manager in PowerPoint can point it at the new place.

**Only a copy.** When you have the workbook only as a copy, such as a file the
user attached in a chat app, you cannot read the original yourself.

- If the Grunt tools include `register_local_excel_connection`, call it with the
  range and either the `filePath` the user gave or the copy's `fileName` and the
  SHA-256 of its bytes. It works through Grunt running in the user's PowerPoint,
  finds the original and returns the range's `data` and a `dataImportDefinition`
  that names it. Pass both unchanged to the create tool (for a table, `data.values`
  are its `cells.values`), then go on from step 4.
- Some chat apps rename the copy, for example replacing spaces with
  underscores. If the tool finds no file and the copy's name has underscores,
  try once more with spaces in their place.
- If the tool is missing or still finds nothing, ask the user for the
  original's full path. Pass it to the tool as `filePath`, or, without the tool,
  use it with the copy's values from steps 2 and 3. If they cannot give it, make
  the asset without a connection and say so. Never use the copy's path.

Never send `dataImportDefinition` without `filePath` or `workbookUrl`: the server
refuses it rather than make an asset that only looks connected.

## Sizing rules

Ask Grunt to lay out each asset at its real placement size so labels, ticks and
legends adapt; a native download is always laid out at its planned rectangle. In
the fallback, do not shrink a full-slide SVG into a half-slide box or enlarge a
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

- Use only the representations advertised by the permanent manifest
  (`links.pptx`, or `links.svg` in the fallback), and never edit or construct
  their URLs. Never insert browser snapshot SVGs with `data-grunt-scope` CSS (the
  helpers reject them) and never strip or rewrite SVG bytes to get past a check.
- The manifest's pinned permanent source (`links.self`, which a fallback SVG
  carries as `data-grunt-src`) goes into `GRUNT-WEB-LINK`. Never replace it with
  a delivery URL.
- A native shape is a snapshot of the asset's commit when the deck was built.
  Later edits to the asset do not reach it; rebuild the placement to update it.
- `https://assets.grunt.io` is trusted by default. Other capability origins need
  an explicit `--trust-origin`; a separate SVG or placement delivery host needs
  `--trust-delivery-origin`. Never trust an origin because it appears in a
  response.
- `asset_id`/`asset_commit` manifest overrides (or `--asset-id`/`--asset-commit`)
  are a last resort for SVGs without a carrier; they intentionally omit the link.
- Edit links are permanent bearer capabilities, and native shapes carry each
  chart's full model, which the edit link already grants: anyone holding the deck
  can use both. Tell the user when a delivered deck contains them. Treat
  `.pptx.json` downloads and downloaded or recovered SVGs as private files.

## Recovery

`restore_assets.py --output-dir <dir>` writes the exact embedded SVGs back out for
rebuilding a deck after the original downloads are gone. It never exports native
model data; download native placements again to rebuild native shapes. Grouped
Grunt shapes must be ungrouped first. If asset-project tools are available, keep
one project per deliverable and stamp its ID in the final file.

For a paired HTML report, see [HTML.md](HTML.md) and the `grunt-html` skill.

## Tests

```sh
python "<skill-dir>/scripts/test_scripts.py"
python -m unittest discover -s "<skill-dir>/scripts" -p "test_*.py"
```
