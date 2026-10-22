# Paired HTML and PowerPoint reports

Use the `grunt-html` skill for self-contained HTML and this skill for PowerPoint.
Both come from the same plugin and use the same Grunt assets. Older generated
reports keep their old inlined runtime; updating the plugin does not upgrade them.

Browser SVGs can include scoped CSS for isolation between assets. PowerPoint needs
the plain SVG advertised by the permanent manifest, as described in SKILL.md. Keep
that export unchanged; do not copy HTML interaction overlays into a deck or strip
scoped CSS to force compatibility.

The HTML runtime owns transient hover, persistent selection and value tooltips.
Use `--grunt-interaction-accent` for a report-wide accent, or
`--grunt-interaction-hover` and `--grunt-interaction-selection` for separate states.
`--grunt-interaction-surface` describes the chart paper, which can differ from the
surrounding page. These tokens do not recolor chart data or native PowerPoint UI.

Use the same asset commit in both deliverables. A verified HTML refresh does not
update its analysis or an already generated deck. Regenerate the derivative from
the chosen commit, then inspect the saved PPTX at final slide size.

HTML reports default to view links; decks use one edit link per asset per deck.
Keep capability URLs out of diagnostics in both.
