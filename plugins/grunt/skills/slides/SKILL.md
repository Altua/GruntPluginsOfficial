---
name: slides
description: Put Grunt charts and tables into Claude Slides decks (the claude.ai Slides artifact) and change them in place, using the Grunt MCP server. Use when a Slides deck needs a chart or table, or when the user selects a Grunt chart on a slide and asks for a change. Each chart is an uploaded picture whose alt text names its Grunt asset and version, so the PowerPoint download can become editable Grunt objects again in the Grunt add-in. Requires a signed-in Grunt MCP connection, which the skill checks first.
---

# Grunt charts in Claude Slides

A Claude Slides deck is a set of files: `project/deck.json` and one
`project/slides/<id>.html` per slide, with pictures uploaded to the deck and
referenced as `/_blob/<id>`. The deck type's own instructions decide the slide
format and how to read, write and publish the deck; follow them. This skill adds
how a Grunt chart or table goes on a slide, how to change one the user points
at, and what the PowerPoint download does with it.

In the commands below, `<skill-dir>` stands for the absolute path of the folder
that contains this SKILL.md; replace it yourself, because it is not an
environment variable. The helper uses the pptx skill's downloader, so the whole Grunt
plugin must be installed.

## Before you start: check the Grunt connection

Do this before planning, installing anything or writing files. The plugin brings
no Grunt server of its own: the skill works through the Grunt connector that is
connected in this session, normally the organization's connector, called just
"Grunt". It can be Grunt's cloud service or a Grunt the organization runs itself,
and each user signs in with their own Grunt account. Work with the Grunt that is
connected. Never add, suggest or switch to another server address on your own.

1. **Find the Grunt tools.** Look for tools whose names are, or end with,
   `create_or_update_bar_chart`, `create_asset_link` and `get_rendering_fonts`.
   Apps add their own prefixes to MCP tool names, and a connector can have
   another name than "Grunt", so match the end of the name, not the server's
   name. If your app loads tools on demand or lets you search for tools, search
   for `create_asset_link` before deciding the tools are missing.
2. **Confirm the sign-in.** Call `get_rendering_fonts` once with no arguments. It
   only reads; it creates and changes nothing.
   - A list of font names: you are connected. Keep the list for choosing fonts.
   - An authentication error (for example 401, 403, "unauthorized", "sign in" or
     an expired token): you are not signed in to that connector. If step 1 found
     another Grunt connector, check it the same way; if none is signed in, go to
     step 3.
   - Any other error: try once more. If it fails again, tell the user that Grunt
     is not responding, quote the error, and stop.
3. **If the tools are missing or you are not signed in, stop.** Do not draw the
   charts another way, write placeholder images, install dependencies or go on
   to later steps. Tell the user:
   - Grunt isn't connected in this session.
   - To connect, they turn on their organization's Grunt connector in their
     app's connector or MCP settings and sign in with their Grunt account. If
     their organization has no Grunt connector yet, an administrator adds one
     with the address of the Grunt the organization uses. If you know the exact
     steps for the app you are running in, give them; [CONNECT.md](CONNECT.md)
     lists some.
   - They should tell you when they are done.

   You cannot complete the sign-in yourself. Never ask the user for a password,
   token, code or callback URL.
4. **When the user says they are done,** repeat steps 1 and 2 once. If the tools
   still don't appear, tell the user that the app may need to reload its MCP
   servers (a new session or an app restart), and stop. Do not keep checking.

An app can list more than one Grunt connector, for example one for Grunt's cloud
service and one for a Grunt the organization runs itself or a test environment.
Each is a separate Grunt with its own assets. Use the one the user names. If
they name none, use the one that is signed in; if several are signed in, use the
one called just "Grunt", and if that does not settle it, ask. Do not ask the
user to sign in to another while one works. Then use only that connector for the
whole deliverable, so every asset is created, linked and updated in the same
Grunt, and tell the user which one you used when there was a choice. Asset links
come from that Grunt's own asset address, which is not always the cloud
service's; the steps below say when to ask the user about it.
[CONNECT.md](CONNECT.md) lists the steps to connect in each app.

## How a Grunt chart sits on a slide

One `<img>` per chart or table, never inline `<svg>` code:

```html
<img src="/_blob/<id>" alt="Revenue by quarter, 2025 vs 2026 [grunt:<assetId>@<assetCommit>]"
     style="width:1664px;height:720px;object-fit:contain">
```

- **The alt text** says what the chart shows, then ends with exactly one marker,
  `[grunt:<assetId>@<assetCommit>]`: the asset ID and the 64-character commit
  that the picture shows. The helper prints it as `alt_marker`. The marker is
  how you find the chart again and how the Grunt add-in rebuilds it after a
  PowerPoint download. It names the asset but grants nothing: only someone who
  can open the asset in Grunt can use it.
- **Never put a Grunt link into the deck.** Edit and view links are bearer
  capabilities, and anyone who can open the deck can read its files, alt text
  and speaker notes. Mint only view links, use them only for the download, and
  never write them into a slide.
- **One asset per placement.** To show the same chart twice, create a second
  asset; two pictures of one asset version would give the add-in two objects
  with the same keys.

## Size the chart before requesting it

The Slides canvas is 1920 × 1080 px for a 13.333 × 7.5 in slide, 144 px per
inch. Grunt lays charts out in CSS pixels, 96 per inch. Decide the chart's box on
the slide first, after margins, headings and gaps, then request two thirds of it
from Grunt: a box of W × H slide pixels is `width=round(W × 2/3)` and
`height=round(H × 2/3)`. A full-width chart inside the 128 px margins, 1664 ×
720, is a 1109 × 480 request. Let Grunt lay the chart out at that size; do not
scale a chart made for another size.

## Add a chart or table to a deck

1. **Create the asset** with the Grunt `create_or_update_*` tools. Keep the
   `assetId` and the latest `assetCommit`.
2. **Mint a view link** with `create_asset_link` and `permission: "view"`. Its
   `assetUrl` is pinned to the commit that is current when it is minted, so mint
   it after the chart is final, and mint a new one after every change.
3. **Download it for Slides.** Append `&width=<px>&height=<px>` to the
   `assetUrl` and write it to a private file with a file-writing tool, not a
   shell command; never put the URL on a command line or in logs. Then run:

   ```sh
   python "<skill-dir>/scripts/slides_svg.py" --url-file private/revenue.url --output slides-assets/revenue.svg
   ```

   The helper downloads through the asset manifest with the pptx skill's checked
   downloader and deletes the URL file. It moves Grunt's text styles into each
   label, because Slides strips `<style>` blocks from uploaded SVGs and the
   labels would otherwise shrink to a few pixels. It removes the link Grunt
   embeds in the SVG. It prints `asset_id`, `asset_commit`, `alt_marker`,
   `slide_width`, `slide_height`, `font_families` and `warnings`. Tell the user
   about any warning, such as a logo that Slides will drop.

   The helper trusts asset links on `https://assets.grunt.io`, the asset address
   of Grunt's cloud service. When the `assetUrl` is on another origin, as with a
   Grunt the organization runs itself or a test environment, ask the user once
   to confirm that it is their Grunt's asset address, then add
   `--trust-origin <origin>` (`https://host` or `https://host:port`). That
   covers pictures delivered from the same origin. If the helper then stops
   because the manifest's delivery link is outside the trusted origins, that
   Grunt delivers its pictures from a separate host: ask the user for that
   delivery origin, which their Grunt administrator has, and add
   `--trust-delivery-origin <origin>` as well. Never add an origin only because
   it appears in a link or a response. If the download cannot reach the asset
   address from your environment, tell the user and stop; do not draw the chart
   another way.
4. **Upload the SVG** to the deck the way the deck type uploads images, and put
   the returned address in `src` exactly as given.
5. **Write the `<img>`** with `width:<slide_width>px;height:<slide_height>px`
   and `object-fit:contain`, so the picture fills its box exactly, and the alt
   text described above. Then publish as the deck type says.

## Change a chart the user points at

The deck tells you what the viewer has selected: its view context lists the
selected element ids, and a picture's label reads `Image — <alt text>`. Resolve
the id against the slide file you read; ask if it does not resolve.

1. **Read the marker** from the `<img>` alt text. Without one it is not a Grunt
   chart; say so rather than redrawing it.
2. **Make the change** with the Grunt tools on that `assetId`. Build on the
   asset's latest version. If the latest commit is not the marker's, tell the
   user the chart had changed since it was placed on the slide.
3. **Refresh the slide.** Mint a new view link, download at the same size (the
   `<img>` width and height × 2/3), upload, and change only that `<img>`: its
   `src`, the marker's commit and, if the content changed, the description.
   Publish only that slide's file.

The user can also edit the chart in the Grunt editor (the chart card's
**Expand**) in the conversation. Each save there is a new version of the same
asset. When they tell you they have edited it, or Grunt reports a newer commit
for an asset on a slide, use `fetch_latest_asset` for the `assetId` and refresh
the slide as in step 3.

## Downloads

- **PowerPoint.** The deck's PowerPoint download carries each chart as a picture
  with its alt text. A Grunt add-in that supports these pictures finds the
  marker, loads that asset version as the signed-in Grunt user, and replaces the
  picture with editable Grunt objects, the chart and its legend, in the same
  place. Someone who cannot open the asset in Grunt, or an older add-in, keeps
  the picture. Once the owner saves the file, the objects are ordinary Grunt
  objects for everyone who opens it.
- **PDF and slides as pictures** keep only pictures.
