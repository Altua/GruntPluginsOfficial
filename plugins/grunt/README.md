# Grunt plugin

Bundles the **Grunt** MCP server with three skills that place Grunt charts and
tables into presentations and reports. It has manifests for Claude Code (`.claude-plugin`) and
Codex (`.codex-plugin`); the skills themselves work in any agent that can call
MCP tools.

## Install

```text
/plugin install grunt --marketplace Altua/GruntPluginsOfficial
```

```sh
codex plugin marketplace add Altua/GruntPluginsOfficial
codex plugin add grunt@grunt-plugins
```

See the [repository README](../../README.md) for other ways to install and for
signing in.

## Contents

| Component | Description |
| --- | --- |
| MCP server `Grunt` | `https://mcp.grunt.io/mcp` (HTTP). Creates and updates bar, line, area, combined, scatter/bubble, pie/donut, mekko, dumbbell and waterfall charts and formatted tables, and mints permanent asset links. Each user signs in with their own Grunt account; `grunt-pptx` and `grunt-html` check the connection first, and [`CONNECT.md`](skills/grunt-pptx/CONNECT.md) lists the sign-in steps for common apps. |
| Skill `grunt-powerpoint` | For use inside PowerPoint (Claude for PowerPoint, or any host with Grunt's `deck_*` tools). Makes every chart and table a Grunt object by default, places it on the slide with `deck_insert_asset`, and moves, resizes, replaces and deletes Grunt objects in any open presentation. |
| Skill `grunt-pptx` | For agents that build .pptx files outside PowerPoint. Downloads each asset at its exact slide size through a permanent edit link and inserts it as a tagged Grunt object (SVG with PNG fallback, asset ID, pinned commit and link), then inventories and renders the saved deck for checking. |
| Skill `grunt-html` | Assembles a self-contained HTML report with exact-size SVG snapshots, hover and keyboard value inspection, one-click chart updates, durable **Save updated HTML**, regeneration and detached copies. |

## Notes

- Edit links that `grunt-pptx` embeds in decks are permanent bearer
  capabilities: anyone with the file can use them. HTML reports default to view links.
- A Grunt PowerPoint add-in that supports web assets can load the full Grunt
  model from a deck's links. Without it, inserted objects are static pictures.
- **Edit chart** in HTML reports appears only when the asset manifest advertises
  an editor. Production manifests do not yet, so edit charts through the MCP
  tools and use the report's update control or the CLI `regenerate` command.

Bundled third-party components are listed in
[`skills/grunt-html/THIRD-PARTY-NOTICES.txt`](skills/grunt-html/THIRD-PARTY-NOTICES.txt).
