# Grunt plugin

Four skills that place Grunt charts and tables into presentations and reports.
The folder has a manifest for Claude (`.claude-plugin`) and one for Codex and
ChatGPT (`.codex-plugin`), and each gets its own version of the plugin:

- **Claude** gets all four skills and no Grunt server: it works through the
  Grunt connector your organization has connected.
- **Codex and ChatGPT** get `powerpoint`, `pptx` and `html`, and Grunt's MCP
  server (`.codex-plugin/mcp.json`).

Other harnesses use [`agent-plugins/grunt`](../../agent-plugins/grunt), which is
generated from this folder.

## Install

```text
/plugin install grunt --marketplace Altua/GruntPluginsOfficial
```

```sh
codex plugin marketplace add Altua/GruntPluginsOfficial
codex plugin add grunt@grunt-plugins
codex mcp login grunt
```

See the [repository README](../../README.md) for other ways to install and for
connecting Grunt.

## Contents

| Component | Description |
| --- | --- |
| Grunt connector | The skills use the Grunt connector that is connected in the user's app: Grunt's cloud service or a Grunt the organization runs itself. In Claude it is not bundled and is normally the organization's, called just "Grunt"; elsewhere the plugin brings a server called `grunt` for the cloud service. Its tools create and update bar, line, area, combined, scatter/bubble, pie/donut, mekko, dumbbell and waterfall charts and formatted tables, and mint permanent asset links. Each user signs in with their own Grunt account; `pptx`, `html` and `slides` check the connection first, and [`CONNECT.md`](skills/pptx/CONNECT.md) lists the steps to connect in common apps. |
| Skill `powerpoint` | For use inside PowerPoint (Claude for PowerPoint, or any host with Grunt's `deck_*` tools). Makes every chart and table a Grunt object by default, places it on the slide with `deck_insert_asset`, and moves, resizes, replaces and deletes Grunt objects in any open presentation. |
| Skill `pptx` | For agents that build .pptx files outside PowerPoint. Downloads each asset at its exact slide size through a permanent edit link and inserts it as a tagged Grunt object (SVG with PNG fallback, asset ID, pinned commit and link), then inventories and renders the saved deck for checking. |
| Skill `slides` (Claude only) | Puts Grunt charts and tables into Claude Slides decks as uploaded pictures whose alt text names the asset version, with text styles kept and no links in the deck. Changes a chart the user selects on a slide and refreshes it after edits in the Grunt editor. The deck's PowerPoint download can become editable Grunt objects again in a Grunt add-in that supports it. |
| Skill `html` | Assembles a self-contained HTML report with exact-size SVG snapshots, hover and keyboard value inspection, one-click chart updates, durable **Save updated HTML**, regeneration and detached copies. |

## Notes

- Edit links that the `pptx` skill embeds in decks are permanent bearer
  capabilities: anyone with the file can use them. HTML reports default to view links.
- A Grunt PowerPoint add-in that supports web assets can load the full Grunt
  model from a deck's links. Without it, inserted objects are static pictures.
- **Edit chart** in HTML reports appears only when the asset manifest advertises
  an editor. Production manifests do not yet, so edit charts through the MCP
  tools and use the report's update control or the CLI `regenerate` command.

Bundled third-party components are listed in
[`skills/html/THIRD-PARTY-NOTICES.txt`](skills/html/THIRD-PARTY-NOTICES.txt).
