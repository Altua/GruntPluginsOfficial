---
name: grunt-html
description: Build self-contained, interactive HTML reports from Grunt charts and tables, using the bundled Grunt MCP, exact-size SVG snapshots, hover/keyboard value inspection, one-click chart updates and durable HTML saves. Use for HTML reports, dashboards and offline report files with Grunt assets.
---

# Grunt HTML reports

Use the **Grunt** MCP server bundled with this plugin to create the charts and
tables, then assemble the report with the bundled CLI:
`node "${CLAUDE_SKILL_DIR}/scripts/report.mjs"`. It is not a script in the user's
project. Read [PACKAGED.md](PACKAGED.md) for setup and the production origins, and
[RUNTIME.md](RUNTIME.md) for the full runtime reference. If the Grunt tools are
missing, ask the user to authenticate the Grunt server with `/mcp`.

The managed report assembler handles ordinary HTML/SVG. It keeps author
layout/source and original SVG snapshots, discovers representations through
permanent asset manifests, and provides **Save updated HTML**. React is not
required. Request interaction data for explorable charts and tables.

The managed report format supports static author HTML, inline CSS, embedded
raster images, and explicit chart slots. Do not promise round-trip support for
arbitrary scripts, widgets, or hand-edited rendered SVG. Preserve the user's
original file during import.

## Size the layout before requesting charts

Determine each chart's actual content rectangle in CSS pixels first, after page
padding, grid gaps, card padding and borders, headings and legends. Request that
width and height from Grunt. For example, a two-column report with 1,040 px of
content, a 24 px gap, 28 px card padding and 1 px borders has 450 px per chart,
not a 1,040 px chart to shrink afterward. Put those dimensions in the
placement's `render` request.

Do not use a full-page render as the half-page chart by reducing CSS width,
changing viewBox, scaling an SVG group or shrinking its fonts. Grunt must lay out
the chart at the intended size so labels, ticks, legends and mark spacing adapt.
Do not enlarge a compact chart for an expanded view either: request a separate
detail render.

**Responsive reports.** The runtime fits each SVG to its slot width, so a wide
render on a phone becomes unreadably small. Give each breakpoint its own slot and
placement that share the same binding, and show one per breakpoint:

```html
<figure class="wide" data-grunt-slot="revenue"></figure>
<figure class="narrow" data-grunt-slot="revenue-narrow"></figure>
```

```css
.narrow { display: none; }
@media (max-width: 760px) { .wide { display: none; } .narrow { display: block; } }
```

Dense tables may need a readable native width inside a horizontal scroll
container rather than tiny type: wrap the slot in `<div style="overflow-x:auto">`,
give the slot `min-width` equal to its render width, and set `min-width: 0` on
grid or flex items that contain it so the page itself does not scroll sideways.
Check narrow renders for colliding data labels; when labels collide, use a
separate asset with fewer labels or another orientation for the narrow layout.

Verify a representative wide and narrow render at their intended display sizes
before rendering the complete set. PowerPoint follows the same principle using its
final slide rectangle (see the `grunt-pptx` skill).

For stacked bar and column charts, explicitly set `settings.seriesLabels.visible`
to `false` when showing a value axis or a legend. Series-name labels default to
visible and can overlap the axis or repeat the legend. This is separate from
`segmentLabels` (individual values) and `totalLabels` (stack totals); choose those
independently for the reading task.

## Prepare assets

1. Create/update the requested Grunt assets using MCP. Retain each `assetId`,
   concrete `assetCommit`, permanent view `assetUrl`, and nonsecret `linkId`.
   Creation returns a view link. Updates return only a new commit: call
   `create_asset_link` (`permission: "view"`) to get a link pinned to it.
2. Reuse a gallery asset project for organization when that capability is
   available. Its project ID is separate from the report ID and is not report
   storage or publication authority.
3. Keep view and edit grants separate. Default reports use genuine view links;
   owner editing happens in Grunt. Only use `mode: "draft"` with an explicit edit
   grant for a private editable working copy. Possession of that draft grants
   editing of the shared asset. An edit is not an implicit independent copy.

Do not print capability URLs/tokens in diagnostics, comments, or visible report
text. They belong only in the configuration file, the managed link records and
the permanent SVG carriers.

## Assemble

Write static author HTML containing empty named slots, for example:

```html
<figure class="chart-wide" data-grunt-slot="prices"></figure>
```

Reset the default `figure` margin in the report CSS. Then write a JSON
configuration file with the Write tool (keep capability URLs out of command-line
arguments and logs):

```json
{
  "template": "report-template.html",
  "mode": "linked-view",
  "bindings": {
    "prices": {
      "assetId": "<asset ID>",
      "commit": "<concrete commit>",
      "view": { "source": "<permanent view assetUrl>", "linkId": "<link ID>" },
      "policy": "pinned"
    }
  },
  "placements": {
    "prices": {
      "bindingId": "prices",
      "render": { "width": 800, "height": 450 },
      "alt": "US steel prices",
      "interaction": true,
      "controls": { "edit": true, "refresh": true }
    }
  },
  "config": {
    "assetOrigins": ["https://assets.grunt.io"],
    "deliveryOrigins": ["https://assets.grunt.io"],
    "editorOrigin": "https://app.grunt.io"
  }
}
```

Placements are keyed by slot name. Several placements can share one binding (for
example wide and narrow layouts). Run:

```sh
node "${CLAUDE_SKILL_DIR}/scripts/report.mjs" assemble report.json report.html
```

Template paths resolve from the working directory. The assembler verifies view
scope, follows the manifest's opaque SVG link, validates identity/safety, and
embeds exact original snapshots plus one pinned runtime. Network requests are
paced, so a report with several charts takes a few seconds per placement. It
refuses to overwrite an existing output.

Use `"interaction": true` on placements for hover tooltips, category guides and
click/keyboard/touch selection. The assembler follows the manifest's `links.export`
and `links.data` unchanged for the same commit after requesting
`interaction=data-elements` on the source manifest. The saved file retains
validated geometry and values for offline use. Values come from the renderer's
data; gaps stay gaps. If this capability is unavailable, report that limitation
and produce an explicitly static placement rather than inventing geometry from
the SVG.

## Verify

Serve the report from a local HTTP server (for example `python -m http.server`
bound to 127.0.0.1) and open it in a browser; some preview panes render local
files as static snapshots without scripts. Check that:

- every slot shows its SVG at its native render width and no console errors appear;
- hover and keyboard focus show value tooltips, and Escape dismisses them;
- the layout has no horizontal page scroll at the narrowest intended width;
- no capability token appears in visible text;
- **Save updated HTML** produces a file that reopens with working charts.

## Interaction and visual design

Plan the object controls alongside the chart and document theme. The runtime
provides styled **Edit chart** and compact update controls on each object;
they appear on object hover or keyboard focus. The update icon appears only when
a newer version is known, with the tooltip **Update chart to latest version**.
Touch devices without hover keep them reachable. Do not add a separate toolbar
script or CSS that hides them from keyboard or touch users. **Edit chart**
appears only when the retained manifest advertises a supported editor on the
configured trusted origin. Production manifests do not advertise one yet, so the
button stays hidden there; edit charts through the Grunt MCP tools and use the
update control or `regenerate` to adopt the new commit.

Choose `controls: {edit, refresh}` for each placement deliberately.
Keep editing available for working reports; set `edit: false` for a read-only
presentation. Enable `refresh` when readers should be able to load the latest
version of an evolving chart with one click when an update is available. Usually
disable it for historical, final or offline deliverables. Both options default to
`true`, so record the intended choice rather than relying on that default.
`checkForUpdates` is a legacy alias for `refresh`; use `refresh` in new reports.
Control visibility does not change the binding's revision policy: use
`policy: "pinned"` when the report should make no automatic startup requests.

Use the default button style or theme it through `--grunt-control-background`,
`--grunt-control-color`, `--grunt-control-border`,
`--grunt-control-hover-background`, `--grunt-control-hover-color`,
`--grunt-control-focus-ring` and `--grunt-control-radius` on a report ancestor.
Choose these colors with the document palette and keep readable contrast and a
visible focus ring. Review the buttons over the actual chart on hover and focus,
including any dark theme, and confirm that they remain reachable on touch.
Keep the controls clear of important labels and marks. When the top of a chart
is crowded, reserve room in the document layout, for example with
`.grunt-chart-frame { padding-block-start: 64px; }`, and check that wrapped
controls also fit at the narrowest intended width. Do not move SVG content to
make room for the toolbar.

Use a restrained report palette and keep original series colors and line styles.
Grunt's default warm hover and dark teal selection are separate reading states.
Set `--grunt-interaction-accent` on the report to theme both, or override
`--grunt-interaction-hover` and `--grunt-interaction-selection` independently.
Set `--grunt-interaction-surface` to the chart paper color. Tooltip background,
text, muted text and border use `--grunt-tooltip-background`, `--grunt-tooltip-color`,
`--grunt-tooltip-muted` and `--grunt-tooltip-border`. Check contrast against the
actual chart, including when surrounding page chrome is dark.

Use grouped category values for aligned line plots, precise mark contours for
bars/slices/cells, and a stronger persistent selection. Let the runtime own those
states and positioning. Do not write a second hover script, paint interaction
colors into the original SVG, or fabricate swatches for unknown series colors.
Keep ordinary text selection/copy working. Verify pointer, keyboard and touch
inspection, Escape/outside dismissal, viewport edges, resizing and offline reopen.

Choose legend disclosure for the chart's reading task. Use `interactionOptions`
on the placement (or in `mountInteraction`) with `legend: {mode, maxRows,
categoryIndexes, description}`. `auto` shows up to six observations, otherwise a
summary. Prefer `summary` for dense charts, scatter groups and legends whose main
purpose is identifying a series. Use `values` for short meaningful comparisons;
set `categoryIndexes` to renderer category indexes for an authored shortlist such
as opening/latest or selected milestones. `maxRows` is bounded to 1–12, and
`description` is optional plain text (240 characters). Choose deliberately; do
not expose a whole large series on hover or invent an aggregate. Full data remains
available through the report's data view. These choices persist in saved reports.

Dumbbell connector inspection should emphasize the line and both endpoints.
Use the renderer's category connector region; never infer one from two dots.
The runtime presents endpoints in source series order and a labelled signed
change when exactly two numeric endpoints have matching formats. Percentage
values use percentage-point differences. Hovering a dot still inspects that dot.

For waterfall charts, give opening/closing totals a shared theme color distinct
from movement bars. Request totals as calculated totals where appropriate and
apply point colors using the full renderer series/category indexes, including
headers. Keep that total/movement distinction across report themes.

For richer visual grids, use native Grunt table gauges, conditional fills and
fixed scales. Scope each modifier to its intended data columns/rows, excluding
headers. Keep numbers visible alongside color; explain each scale and use enough
width for labels. Do not replace native graphics with hand-drawn approximations.

Current renderer `extendedRegions` add Gantt dates, scatter legend groups,
Sankey nodes/ribbons and valuation ranges. Keep these alongside ordinary regions
in renderer paint order. Use the matching runtime to join their identities to
data; never substitute bounding-box guesses or inferred labels. Pinned Sankey
node levels can retain a label without an aggregate when an exact join is absent.

When demonstrating several report themes, render each chart in each chosen
palette; CSS interaction tokens alone do not change the chart palette. Retain
matching geometry/data for every rendered variant. Keep the values identical
across themes.

For a host page that renders Grunt SVGs itself, use the standalone
`GruntInteraction.mountInteraction` API from `dist/` and destroy its handle before
replacing an SVG. See [RUNTIME.md](RUNTIME.md) for the API.

## Revision policy

Several placements can share a binding and update together. A historical view of
the same asset must use another binding with its own commit. `pinned` makes no
automatic startup requests; `notify` checks metadata without adopting updates.
Hovering or focusing an object with updates enabled also silently checks its
manifest, throttled to once every 30 seconds, including for pinned bindings.
If no newer version is known, there is no update icon or background status message.
When a newer version is found, the icon appears with the tooltip and accessible
name **Update chart to latest version**. Clicking it rechecks, fetches, verifies
and applies the latest chart in one step.

## Editing and durable saving

After a chart is updated, the report shows the new picture and reminds the reader
to check that the report text still matches. Use **Save updated HTML** to retain
accepted changes in a new file. A manual update temporarily disables saving.
Pending editor changes are not silently included; the user can explicitly
download the current snapshot instead. Review the report text after a chart
update so that its analysis still matches the displayed values.

Verify the actual downloaded file after closing the original and reopening
offline. Check the chart, unchanged author text/layout, and permanent pinned
source. A download starting does not prove a disk write completed.

For agent regeneration, use
`node "${CLAUDE_SKILL_DIR}/scripts/report.mjs" regenerate old.html new.html commits.json`,
where the JSON maps binding IDs to concrete commits. Omitted bindings stay
pinned. No LLM layout recreation or live DOM serialization is needed. Do not
claim chart updates refresh prose or existing PowerPoint files; review the
report's analysis and regenerate derivatives from the chosen commit.

For distribution, `view-copy` (or a draft's **Download view copy**) verifies
separate view grants online and removes managed edit grants. `detach` (or
**Download detached copy**) removes all managed capability links, including SVG
carriers, leaving a static offline report. Neither action automatically revokes
the author's working grant. These guarantees cover this managed profile, not
arbitrary secrets encoded in imported content.

Hosted publishing and selected-file overwrite are separate integrations. Keep
untrusted authored HTML in its existing sandbox; never give its scripts account
credentials or an arbitrary authenticated fetch proxy.
