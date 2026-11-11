# Grunt plugins

Official Grunt plugins for coding agents. The same plugin installs in
[Claude Code](https://code.claude.com) and the Codex CLI, and its skills work in
any agent that reads `SKILL.md` folders and can call MCP tools.

| Plugin | What you get |
| --- | --- |
| [`grunt`](plugins/grunt) | Four skills that work through the Grunt connector your organization has connected (charts, tables and visual grids): **grunt-powerpoint** makes and changes Grunt charts and tables inside PowerPoint, **grunt-pptx** builds .pptx files with Grunt objects outside PowerPoint, **grunt-html** builds interactive, self-contained HTML reports, **grunt-slides** puts them into Claude Slides decks and changes them in place. |

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

Copy the folders in [`plugins/grunt/skills`](plugins/grunt/skills) to wherever
the agent loads skills from, and connect Grunt as described below. Keep each
skill folder whole; the scripts and runtimes are part of it.

## Connect Grunt

The plugin brings no Grunt server of its own. The skills work through the Grunt
connector that is connected in your app, normally your organization's connector,
called just "Grunt". It can point at Grunt's cloud service
(`https://mcp.grunt.io/mcp`, streamable HTTP) or at a Grunt your organization
runs itself, and the skills use whichever it is. Each user signs in with their
own Grunt account. Below, `<address>` is the address of the Grunt your
organization uses.

- **Claude Code, Claude Desktop, claude.ai, Cowork and Claude for PowerPoint:**
  connect your organization's Grunt connector in **Customize > Connectors**. In
  a chat, turn it on under **+** > **Connectors**; in Claude Code, run `/mcp` in
  a new session to check that it is listed. If your organization has set up
  managed authorization for the connector, it connects without a sign-in page.
- **Claude Code without an account connector:** add the server yourself with
  `claude mcp add --transport http grunt <address>`, then run `/mcp`, select it
  and complete the sign-in in your browser.
- **Codex CLI:** add the server with `codex mcp add grunt --url <address>`, then
  run `codex mcp login grunt`.
- **Other agents:** add `<address>` in the agent's MCP or connector settings and
  sign in there.

Versions before 0.3.8 added their own server for Grunt's cloud service
(**plugin:grunt:Grunt** in Claude Code). Updating the plugin removes it; connect
Grunt as above if you signed in to that server only.

Some apps show the new tools only in a new session or after a restart.
**grunt-pptx**, **grunt-html** and **grunt-slides** check the connection before they start and tell
you what to do if Grunt is not connected;
[`CONNECT.md`](plugins/grunt/skills/grunt-pptx/CONNECT.md) lists the steps they
give. **grunt-powerpoint** uses the Grunt connector of the PowerPoint host it runs
in, and tells you if Grunt's tools are missing.

## Use

Ask in plain language, or name the skill in your request (in Claude Code you can
also invoke it directly):

- `/grunt:grunt-pptx` — "Create a Grunt bar chart of quarterly revenue by region and put it on slide 2 of deck.pptx."
- `/grunt:grunt-html` — "Build an HTML report with a Grunt line chart of monthly customers and a KPI table."
- **grunt-slides**, in a conversation with a Claude Slides deck — "Add a Grunt bar chart of revenue by quarter to slide 3", or select a chart on a slide and ask "Make the 2026 bars orange."
- **grunt-powerpoint**, in Claude for PowerPoint or another host with Grunt's
  `deck_*` tools — "Add a waterfall chart of this year's profit bridge to slide 3."

Requirements on your machine:

- **grunt-powerpoint:** PowerPoint with Grunt running and signed in. Nothing
  else to install.
- **grunt-pptx:** Python 3.10+. On first use the skill installs its pinned
  Python packages from `requirements.txt` (python-pptx, lxml, resvg-py,
  pypdfium2; about 40 MB) into a virtual environment. Decks are rendered for
  checking with PowerPoint on Windows, or else with LibreOffice.
- **grunt-html:** Node.js 22.22+. No `npm install` needed.
- **grunt-slides:** Python 3.10+ with network access to your Grunt's asset address (`assets.grunt.io` for the cloud service). It uses grunt-pptx's downloader, so install the whole plugin.

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
- The plugin bundles no MCP server: no `.mcp.json`, and no `mcpServers` in either
  manifest. The skills work with whichever Grunt connector the user has, which
  can be an installation their organization runs itself, so keep fixed server
  addresses out of them. Only `CONNECT.md` names the cloud service's address.
- Write skills for any agent: refer to the skill's folder as `<skill-dir>`
  rather than a host variable, and describe tools by what they do rather than by
  one host's tool names. The connection check and `CONNECT.md` are shared by
  the file-building skills (grunt-pptx, grunt-html, grunt-slides) and must stay identical.
  grunt-powerpoint runs inside PowerPoint on the host's Grunt connector and has
  neither; keep its body short, because the host loads it on most chart requests.
- Before pushing, run:

  ```sh
  claude plugin validate .
  claude plugin validate ./plugins/grunt
  python -m unittest discover -s tests -p "test_*.py"
  python -m unittest discover -s plugins/grunt/skills/grunt-pptx/scripts -p "test_*.py"
  python plugins/grunt/skills/grunt-pptx/scripts/test_scripts.py
  python -m unittest discover -s plugins/grunt/skills/grunt-slides/scripts -p "test_*.py"
  ```
