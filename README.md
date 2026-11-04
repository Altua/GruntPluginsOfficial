# Grunt plugins

Official Grunt plugins for coding agents. The same plugin installs in
[Claude Code](https://code.claude.com) and the Codex CLI, and its skills work in
any agent that reads `SKILL.md` folders and can call MCP tools.

| Plugin | What you get |
| --- | --- |
| [`grunt`](plugins/grunt) | The **Grunt** MCP server (charts, tables and visual grids) plus three skills: **grunt-powerpoint** makes and changes Grunt charts and tables inside PowerPoint, **grunt-pptx** builds .pptx files with Grunt objects outside PowerPoint, **grunt-html** builds interactive, self-contained HTML reports. |

## Install

### Claude Code

Add this marketplace and install the plugin:

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

### Codex CLI

```sh
codex plugin marketplace add Altua/GruntPluginsOfficial
codex plugin add grunt@grunt-plugins
```

### Other agents

Add the Grunt MCP server (`https://mcp.grunt.io/mcp`, streamable HTTP) in the
agent's MCP settings, and copy the folders in
[`plugins/grunt/skills`](plugins/grunt/skills) to wherever the agent loads skills
from. Keep each skill folder whole; the scripts and runtimes are part of it.

## Connect your Grunt account

Each user signs in to the Grunt MCP server with their own Grunt account:

- **Claude Code:** run `/mcp`, select **plugin:grunt:Grunt** and complete the
  sign-in in your browser.
- **Codex CLI:** run `codex mcp list` to find the Grunt server's name, then
  `codex mcp login <name>`.
- **Other agents:** sign in from the agent's MCP or connector settings.

Some apps show the new tools only in a new session or after a restart.
**grunt-pptx** and **grunt-html** check the connection before they start and tell
you what to do if Grunt is not connected;
[`CONNECT.md`](plugins/grunt/skills/grunt-pptx/CONNECT.md) lists the steps they
give. **grunt-powerpoint** uses the Grunt connector of the PowerPoint host it runs
in, and tells you if Grunt's tools are missing.

## Use

Ask in plain language, or name the skill in your request (in Claude Code you can
also invoke it directly):

- `/grunt:grunt-pptx` — "Create a Grunt bar chart of quarterly revenue by region and put it on slide 2 of deck.pptx."
- `/grunt:grunt-html` — "Build an HTML report with a Grunt line chart of monthly customers and a KPI table."
- **grunt-powerpoint**, in Claude for PowerPoint or another host with Grunt's
  `deck_*` tools — "Add a waterfall chart of this year's profit bridge to slide 3."

Requirements on your machine:

- **grunt-powerpoint:** PowerPoint with Grunt running and signed in. Nothing
  else to install.
- **grunt-pptx:** Python 3.10+. The skill installs its Python packages from
  `requirements.txt` on first use (python-pptx, lxml, resvg-py, PyMuPDF).
  LibreOffice is used to render decks for checking.
- **grunt-html:** Node.js 22.22+. No `npm install` needed.

## Share with a team (Claude Code)

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

- **Claude Code:** run `/plugin` → **Marketplaces** to update, or
  `claude plugin update grunt@grunt-plugins`. Third-party marketplaces do not
  auto-update unless you enable it.
- **Codex CLI:** run `codex plugin marketplace upgrade grunt-plugins`.

## Maintainers

- Each plugin lives in `plugins/<name>/` and is listed in both
  `.claude-plugin/marketplace.json` (Claude Code) and
  `.agents/plugins/marketplace.json` (Codex).
- Each plugin has a Claude Code manifest (`.claude-plugin/plugin.json`) and a
  Codex manifest (`.codex-plugin/plugin.json`). Bump `version` in both for every
  release; users on a pinned version receive changes only when it changes.
- Write skills for any agent: refer to the skill's folder as `<skill-dir>`
  rather than a host variable, and describe tools by what they do rather than by
  one host's tool names. The connection check and `CONNECT.md` are shared by
  the file-building skills (grunt-pptx, grunt-html) and must stay identical.
  grunt-powerpoint runs inside PowerPoint on the host's Grunt connector and has
  neither; keep its body short, because the host loads it on most chart requests.
- Before pushing, run:

  ```sh
  claude plugin validate .
  claude plugin validate ./plugins/grunt
  python -m unittest discover -s tests -p "test_*.py"
  python -m unittest discover -s plugins/grunt/skills/grunt-pptx/scripts -p "test_*.py"
  python plugins/grunt/skills/grunt-pptx/scripts/test_scripts.py
  ```
