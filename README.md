# Grunt plugins for Claude Code

Official [Claude Code](https://code.claude.com) plugins from Grunt.

| Plugin | What you get |
| --- | --- |
| [`grunt`](plugins/grunt) | The **Grunt** MCP server (charts, tables and visual grids) plus two skills: **grunt-pptx** puts Grunt objects into PowerPoint decks, **grunt-html** builds interactive, self-contained HTML reports. |

## Install

In Claude Code, add this marketplace and install the plugin:

```text
/plugin marketplace add Altua/GruntPluginsOfficial
/plugin install grunt@grunt-plugins
```

On Claude Code 2.1.275 or later you can do both in one step:

```text
/plugin install grunt --marketplace Altua/GruntPluginsOfficial
```

From a terminal:

```sh
claude plugin marketplace add Altua/GruntPluginsOfficial
claude plugin install grunt@grunt-plugins
```

Then connect your Grunt account: run `/mcp`, select **plugin:grunt:Grunt** and
complete the sign-in in your browser. Restart Claude Code or run
`/reload-plugins` if the skills do not appear right away.

## Use

Ask in plain language, or invoke a skill directly:

- `/grunt:grunt-pptx` — "Create a Grunt bar chart of quarterly revenue by region and put it on slide 2 of deck.pptx."
- `/grunt:grunt-html` — "Build an HTML report with a Grunt line chart of monthly customers and a KPI table."

Requirements on your machine:

- **grunt-pptx:** Python 3.10+. The skill installs its Python packages from
  `requirements.txt` on first use (python-pptx, lxml, resvg-py, PyMuPDF).
  LibreOffice is used to render decks for checking.
- **grunt-html:** Node.js 22.22+. No `npm install` needed.

## Share with a team

Commit this to a project's `.claude/settings.json` so teammates are offered the
marketplace and plugin when they trust the folder:

```json
{
  "extraKnownMarketplaces": {
    "grunt-plugins": {
      "source": { "source": "github", "repo": "Altua/GruntPluginsOfficial" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "grunt@grunt-plugins": true
  }
}
```

## Updates

Run `/plugin` → **Marketplaces** to update, or
`claude plugin update grunt@grunt-plugins`. Third-party marketplaces do not
auto-update unless you enable it.

## Maintainers

- Each plugin lives in `plugins/<name>/` and is listed in
  `.claude-plugin/marketplace.json`.
- Bump `version` in `plugins/grunt/.claude-plugin/plugin.json` for every release;
  users on a pinned version receive changes only when it changes.
- Before pushing, run:

  ```sh
  claude plugin validate .
  claude plugin validate ./plugins/grunt
  python -m unittest discover -s plugins/grunt/skills/grunt-pptx/scripts -p "test_*.py"
  python plugins/grunt/skills/grunt-pptx/scripts/test_scripts.py
  ```
