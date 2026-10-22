# Portable Grunt HTML reports

Ordinary HTML and inline SVG, without React. A managed report contains retained
author source, explicit chart bindings/placements, original verified view SVGs,
and one versioned runtime. Saving concatenates compiled source parts and accepted
snapshots. It never serializes the running page or fetches latest during a save.

## Run

```sh
node "${CLAUDE_SKILL_DIR}/scripts/report.mjs" assemble report.json output.html
node "${CLAUDE_SKILL_DIR}/scripts/report.mjs" regenerate output.html updated.html commits.json
node "${CLAUDE_SKILL_DIR}/scripts/report.mjs" view-copy output.html view-copy.html
node "${CLAUDE_SKILL_DIR}/scripts/report.mjs" detach output.html detached.html
```

Node 22.22 or newer is required; the CLI is bundled and needs no `npm install`.

`report.json` contains `template` (path relative to the working directory),
`bindings`, `placements`, and `config`; see SKILL.md for a complete
example. Author source uses empty `<figure data-grunt-slot="prices"></figure>`
slots. A binding contains `assetId`, a concrete 64-character `commit`,
`view: {source, linkId}`, and `policy: "pinned" | "notify"`. A placement contains
`bindingId`, `render: {width, height}`, and `alt`. Multiple placements can share
one binding; intentionally historical versions use separate bindings.

Optional placement `controls: {edit: true, refresh: true}` selects the
object actions. Each flag defaults to `true` when omitted; use `false` to suppress
that action. Editing also requires a supported, trusted editor capability from
the manifest. These options survive updates, saving and regeneration. They do
not change the binding's `policy`: use `pinned` for no automatic startup requests.
`checkForUpdates` remains a legacy alias for `refresh`; use `refresh` in new
reports. If both flags are present, `refresh` takes precedence.

Use the permanent `assetUrl` from the MCP handoff. The assembler fetches its
manifest and follows `links.svg.href` unchanged. `config` explicitly lists trusted
HTTPS `assetOrigins`, `deliveryOrigins`, and one `editorOrigin`. Representation
URLs cannot extend those trust boundaries. The permanent URL returns metadata
only; SVG rendering uses a separate advertised API route such as `/assets/svg`.
When `AssetLink:DeliveryBaseUrl` uses another host, include that HTTPS origin in
`deliveryOrigins`. Saved bindings and SVG carriers still reference `assetOrigins`. Editor discovery requires the manifest's
`links.editor` relation; this package does not invent editor routes. Production
manifests do not advertise it yet, so **Edit chart** stays hidden there.
No service is deployed by this package.

`commits.json` is an explicit binding-to-commit map, for example
`{"prices":"<64-character commit>"}`. Omitted bindings stay unchanged. CLI
outputs are new-file-only and use exclusive creation. An existing output is never
silently overwritten. Regeneration accepts only the runtime bundled with this CLI version;
a changed runtime requires re-importing author source. CLI network requests are paced.
Compilation does not execute author code.

## Browser behavior

* Object controls have a built-in button style and appear on object hover or
  keyboard focus. They remain available on devices without hover and are omitted
  from print. The runtime hides unavailable editing rather than offering a dead
  editor action.
* **Edit chart** opens the advertised editor. Successful nonsecret notifications
  are verified against editor origin, opened window, random session and asset.
  Manifest/SVG validation precedes atomic adoption of all sizes in that binding.
* A compact update icon appears only when a newer version is known. Its tooltip
  and accessible name are **Update chart to latest version**. Clicking it
  rechecks, fetches, verifies and applies the latest chart in one step.
  Brief feedback reports **Updating chart…**, **Already up
  to date**, **Chart updated**, or failure without shifting the layout. A failed
  refresh keeps the previous snapshot intact.
* `notify` bindings make a bounded, silent metadata check on startup. Enabled
  objects also check their manifest on hover or focus, throttled to once every
  30 seconds. These checks never adopt a new chart; clicking the update icon
  does. Pinned reports make no automatic startup requests but can check after
  hover or focus. An unchanged chart or a failed background check shows no status
  UI. Without a known newer version, the update icon stays hidden.
  Editing starts bounded polling with backoff for up to 30 minutes; Stop checking
  ends it explicitly, including when COOP severs the opener. Unrelated updates
  require the reader's update action. Requests share a page-wide rate budget.
* **Save updated HTML** freezes accepted state and starts a Blob download.
  A manual chart update temporarily disables saving without changing the toolbar
  layout. Pending editor saves or adoptions also expose an explicit
  current-snapshot download. Download initiation is not confirmation of a disk
  write. Reopen the downloaded file to verify persistence. Later changes remain
  marked as needing another download.
* Offline reopening uses retained SVGs. Chart updates and cloud editing need network
  access. Analysis is marked for review and prior derived decks stale after an
  update; the report reminds readers to check that its text matches the updated
  chart. Prose and PowerPoint files are not rewritten automatically.

Choose the actions while designing the report. Keep **Edit chart** for working
reports and suppress it for a read-only presentation. The update action is
useful for evolving source data; historical, final and offline deliverables
usually suppress it. For example, a historical placement can use
`controls: {edit: false, refresh: false}` with a pinned binding.

Style the controls with the document palette or retain the built-in defaults.
CSS custom properties on a report ancestor apply to the runtime's buttons:

```css
.report {
  --grunt-control-background: #ffffff;
  --grunt-control-color: #173f4b;
  --grunt-control-border: #b8cbd0;
  --grunt-control-hover-background: #e9f2f4;
  --grunt-control-hover-color: #102f38;
  --grunt-control-focus-ring: #25788c;
  --grunt-control-radius: 0.5rem;
}
```

Check normal, hover and keyboard-focus contrast against the actual object and
document background. Preserve focus and touch access when adding author CSS;
use the runtime controls rather than adding a second toolbar implementation.
Keep the toolbar clear of important labels and marks. A crowded chart can reserve
space above its SVG with `.grunt-chart-frame { padding-block-start: 64px; }` in
document CSS; verify wrapped controls at the narrowest intended width.

## Hover, tooltips and selection

Set `"interaction": true` on a placement to retain the renderer's interaction data
with that snapshot. The assembler then requests the manifest with the documented
`interaction=data-elements` input, follows `links.export` and `links.data` unchanged,
checks both `projectCommitKey`s against the pinned commit, and stores a validated,
values-only projection: per object the `viewBox` coordinate space and hit
regions, precise sectors/polygons and presentation-only series paths; per chart/table
the dense cell values, number formats and resolved
series direction. Regions are never derived from SVG paths. Refresh and
regeneration restage this data with the new commit; detach keeps the
accepted interaction snapshot. A manifest without the export/data
relations fails closed. Nothing is fetched at view time, so offline copies keep
working.

The runtime mounts one interaction layer per interactive placement as sibling
elements that mirror the composed object viewports; the retained SVG is not
mutated and series colors stay untouched. Hover is transient. Click, Enter or a
touch tap selects persistently; the same target toggles, Escape or an outside click
clears. Pointer tooltips track the pointer and flip at viewport edges; pinned and
keyboard tooltips anchor to the selected marks. The tooltip uses `textContent`
only: a header, labeled values and a swatch when the series color is explicitly
known. It never samples SVG pixels or invents a series color. Cell formats retain
units, and renderer-resolved values take precedence for calculated totals. Missing
values show as a dash, never zero. Aligned line/area datum anchors support grouped
category inspection; incompatible or horizontal anchors remain individual.

The passive overlay is a `listbox` with arrow-key navigation and
`aria-activedescendant`. Native SVG text remains selectable. Renderer sectors retain
donut holes; polygons retain their actual closed contours, and legend selections
can display translucent series paths without changing the original stroke. Older
renderers that supply only rectangles retain rectangular interaction. Additive
extended regions retain renderer paint order, Gantt activity dates, scatter legend
groups, Sankey nodes/ribbons and valuation ranges. Group legends highlight matching
points; series legends highlight matching marks and contours. Sankey values join
encoded renderer identities to the edge list; pinned/repeated-level nodes show
their label without a guessed aggregate. Scrolling dismisses
transient inspection; selection persists. Interaction overlays do not print.

Size each placement before requesting the SVG and export: account for page/card
padding and grid gaps, then set its `render.width`/`render.height` in CSS pixels.
Grunt must recompute the layout at that size; scaling a full-page SVG down to a
half-page slot also shrinks its type and does not change ticks or label layout.
Use separate native renders for responsive card sizes and expanded views, with
matching interaction data per size: give each breakpoint its own slot and
placement sharing the binding, and show one slot per breakpoint with a media
query. Dense tables keep a readable native width inside a horizontal scroll
container.

Dumbbell category connectors highlight the relationship and both endpoint marks.
Their tooltip shows source-series order and a signed difference for two numeric
endpoints with matching formats (percentage formats use percentage points).
Endpoint marks take priority over the connector's narrow acquisition area.

Authors control legend disclosure per placement with, for example,
`interactionOptions: {legend: {mode: 'values', maxRows: 3, categoryIndexes: [1, 4],
description: 'Opening and latest'}}`. `mode` is `auto` (default), `summary` or
`values`. Auto shows the values only when they fit `maxRows` (default 6; range
1–12), otherwise the observation count and a prompt to inspect marks. Selected
`categoryIndexes` are renderer indexes, not renumbered display ordinals. Lists
remain bounded even in values mode; an omitted-value count prevents a partial
list appearing complete. Description is plain text, at most 240 characters.
The same policy governs tooltips, accessible labels and callbacks; retained data
remains complete. Options survive refresh/save and require `interaction: true`.

Theme through CSS custom properties on any ancestor (defaults in parentheses):
`--grunt-interaction-accent` (optional shared override), `--grunt-interaction-hover`
(#D97B2F) and `--grunt-interaction-selection` (#0A3C47). Each state falls back to
the shared accent when it is supplied. `--grunt-interaction-surface`
(#FFFFFF), `--grunt-tooltip-background` (#0F2233), `--grunt-tooltip-color`
(#FFFFFF), `--grunt-tooltip-muted` (#B7C7D4), `--grunt-tooltip-border` (#314759).

Hosts that render composed Grunt SVG themselves can use the standalone build
(`dist/grunt-interaction.js` exposes `GruntInteraction`, `dist/grunt-interaction.mjs`
is ESM). `buildInteraction(exportJson, dataJson, commit, svgRoot)` turns the two
renderer responses into the retained snapshot form; `mountInteraction({container,
svg, interaction, interactionOptions, label, onHoverChange, onSelectionChange})` returns a handle with
`destroy()`, `getSelection()`, `select(target)` and `clearSelection()`. Call
`destroy()` before replacing the SVG. This package does not integrate with any
external product; adopters validate in their own host.

For example, `.report { --grunt-interaction-accent: #D04A02; }` uses one brand
orange for both interaction states. Weight and tint still distinguish selection. Set the
surface token to the chart's paper color, even when surrounding report chrome is
dark. Choose contrast against the actual drawing. The tokens do not recolor a
baked SVG or PowerPoint's native editing controls. See [PACKAGED.md](PACKAGED.md)
for the bundled CLI and offline visual review fixtures.

## Modes and supported profile

The first format is `managed-static-v1`: ordinary static HTML, inline CSS, embedded
raster images and typed empty chart slots. Arbitrary author scripts, widgets,
external resources and manually edited rendered charts need an explicit import or
a future versioned adapter. Rejecting them avoids pretending arbitrary DOM state
can be round-tripped. The existing legacy interactive demo is not this format.

`linked-view` is the default. Assembly verifies every source's actual view scope.
Owner editing occurs in the separately authenticated editor; a view link grants
no write rights. A private `draft` may have a distinct managed edit source. A
fresh **Download view copy** conversion verifies view grants online, then removes
edit grants. It does not revoke the working draft's grants. A **detached** copy
removes managed links and SVG source carriers. These conversions apply to
credentials managed by this profile, not arbitrary secrets someone encoded in
author content. Re-saving an existing offline file is a copy, not fresh scope
certification; any hosted publisher must revalidate grants and reject draft mode.

SVG accepts a bounded passive subset with local references only, no scripts,
foreignObject, animations or external resources. Original carrier SVG bytes stay
immutable; display IDs and references are namespaced per placement. Unsupported
SVG is rejected while the previous snapshot remains. Runtime and snapshot digests
detect corruption, not authorship. A mismatching rendered fallback disables
managed operations. Keep reports from untrusted authors in a sandbox.

Limits: 16 MiB final HTML, 8 MiB package, 4 MiB retained SVGs plus interaction
data, 1 MiB per SVG, 1 MiB interaction data per snapshot (8 MiB export and 4 MiB
data responses while assembling),
100 placements, 20,000 nodes per SVG, 100,000 rendered SVG elements per report,
depth 100, 128 KiB manifest, 20-second bounded streamed requests,
24 requests per minute (excess requests wait) and one active refresh job. Render
dimensions are at most 4000 px per side and 8 million pixels in total. Offline SVG bytes are stable;
pixel appearance can still depend on fonts/browser.

## Validation and release boundaries

The runtime and CLI are tested upstream with unit and Edge browser suites,
including repeated download/reopen cycles. Validate each delivered report
yourself: open it, inspect the charts, save, and reopen the saved file.

Selected-file overwrite and hosted artifact publishing are separate integrations.
Keep authored HTML sandboxed and never give its scripts account credentials.
