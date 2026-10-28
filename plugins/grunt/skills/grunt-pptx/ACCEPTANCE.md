# Final deliverable acceptance

- Check chart/table values, headline claims, currency and units against the source.
- Review one table slide and one chart slide before scaling up the deck.
- Inspect every saved slide in the intended renderer at presentation size: text,
  headers, labels, clipping, aspect ratio, placement and margins. Record the
  renderer used. PNG fallback previews alone do not prove SVG compatibility.
- Check requested formatting and font substitutions. Verify number formats and
  label visibility after a follow-up edit as well as initial creation.
- Choose and record pinned/latest revision policy. Recover an asset from the saved
  PPTX with restore_assets.py and verify its identity and original bytes.
- Test Office add-in open/edit/save/reopen before claiming native editing. Record
  compound-object limitations separately from static SVG appearance.
- For an asset kept connected to Excel, confirm with `inspect_object`
  (`dataStructure: "Source"`) that `dataConnection.filePath` names the workbook
  on the user's computer, not a sandbox copy. Record whether a refresh from the
  workbook was seen in PowerPoint with Grunt, or not tested.
- For HTML, test live edit, replacement of an SVG, keyboard focus, wide/narrow
  resizing, print view and the actual PowerPoint download. See HTML.md.
- Inventory final asset IDs/commits and project membership where supported. Keep
  tokens out of logs and manifests. Retain original evidence when making repairs.
