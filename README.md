# Grunt plugins

Official Grunt plugins for AI agents. One repository serves every harness: add
it as a plugin marketplace in yours, and you get the version made for it.

| Plugin | What you get |
| --- | --- |
| [`grunt`](plugins/grunt) | Skills that put Grunt charts, tables and visual grids into presentations and reports: **powerpoint** makes and changes Grunt charts and tables inside PowerPoint, **pptx** builds .pptx files with Grunt objects outside PowerPoint, **html** builds interactive, self-contained HTML reports, and **slides** (Claude only) puts them into Claude Slides decks and changes them in place. |

What each harness gets:

| Harness | Skills | Grunt MCP server | It reads |
| --- | --- | --- | --- |
| Claude Code and the Claude apps | powerpoint, pptx, html, slides | Not included. They use the Grunt connector your organization has connected. | `.claude-plugin/marketplace.json` → [`plugins/grunt`](plugins/grunt) |
| Codex CLI and ChatGPT | powerpoint, pptx, html | Included | `.agents/plugins/marketplace.json` → [`plugins/grunt`](plugins/grunt) |
| GitHub Copilot CLI and VS Code | grunt-powerpoint, grunt-pptx, grunt-html | Included | `.github/plugin/marketplace.json` → [`agent-plugins/grunt`](agent-plugins/grunt) |
| Cursor | grunt-powerpoint, grunt-pptx, grunt-html | Included | `.cursor-plugin/marketplace.json` → [`agent-plugins/grunt`](agent-plugins/grunt) |
| Microsoft 365 Copilot | grunt-powerpoint, grunt-pptx, grunt-html | Included | A package built by [`m365`](m365) |
| Other harnesses | grunt-powerpoint, grunt-pptx, grunt-html | Included | The [`agent-plugins/grunt`](agent-plugins/grunt) folder ([Agent Plugins](https://agent-plugins.org) format) |

Claude and Codex list a plugin's skills under its name, so there they are
`grunt:powerpoint`, `grunt:pptx`, `grunt:html` and `grunt:slides`. The other
harnesses list skills by their bare name, so there the names carry the prefix.

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

### Codex CLI and ChatGPT

```sh
codex plugin marketplace add Altua/GruntPluginsOfficial
codex plugin add grunt@grunt-plugins
codex mcp login grunt
```

The ChatGPT desktop app uses the same marketplaces and plugins as the Codex CLI.
A ChatGPT workspace administrator can add the marketplace for everyone under
**Admin > Plugins > Add > Import marketplace**, with this repository's address.
ChatGPT on the web and on phones does not run plugins that bring an MCP server.

### GitHub Copilot CLI

```sh
copilot plugin marketplace add Altua/GruntPluginsOfficial
copilot plugin install grunt@grunt-plugins
```

Then run `/mcp` in a session, choose **grunt** and sign in.

### VS Code

Turn on `chat.plugins.enabled`, add the marketplace to your settings, and
install **grunt** from the plugin list in the Chat view:

```json
"chat.plugins.marketplaces": ["Altua/GruntPluginsOfficial"]
```

VS Code also uses the plugins you installed with GitHub Copilot CLI.

### Cursor

A team administrator adds the marketplace in the Cursor dashboard: **Plugins &
MCPs > Team Marketplaces > Add Marketplace > Import from Repo**, with this
repository's address.

### Microsoft 365 Copilot

[`m365`](m365) builds the plugin as a Microsoft 365 Copilot package for Copilot
Cowork, Copilot Chat and Copilot in PowerPoint. It is a test package, not yet
installed in a tenant; [`m365/README.md`](m365/README.md) says how to build,
install and test it.

### Other harnesses

A harness that reads the [Agent Plugins](https://agent-plugins.org) format can
install the [`agent-plugins/grunt`](agent-plugins/grunt) folder of this
repository. For anything else, copy the folders in
[`agent-plugins/grunt/skills`](agent-plugins/grunt/skills) to wherever the agent
loads skills from, and add Grunt's server as described below. Keep each skill
folder whole; the scripts and runtimes are part of it.

A harness that only knows Claude's files (`.claude-plugin`) gets the Claude
version: all four skills and no server. Add the server yourself there.

## Connect Grunt

The skills work through a Grunt connector: an MCP connection to Grunt's cloud
service (`https://mcp.grunt.io/mcp`, streamable HTTP) or to a Grunt your
organization runs itself. Each user signs in with their own Grunt account.
Below, `<address>` is the address of the Grunt your organization uses.

- **Claude Code, Claude Desktop, claude.ai, Cowork and Claude for PowerPoint:**
  the plugin brings no server. Connect your organization's Grunt connector in
  **Customize > Connectors**. In a chat, turn it on under **+** > **Connectors**;
  in Claude Code, run `/mcp` in a new session to check that it is listed. If
  your organization has set up managed authorization for the connector, it
  connects without a sign-in page.
- **Claude Code without an account connector:** add the server yourself with
  `claude mcp add --transport http grunt <address>`, then run `/mcp`, select it
  and complete the sign-in in your browser.
- **Every other harness:** the plugin brings a server called `grunt` for Grunt's
  cloud service. Sign in to it as the install steps above say. If your
  organization runs its own Grunt, add that server in the harness's MCP settings
  with `<address>`; the skills use the one that is signed in.

Versions before 0.3.8 added their own server for Grunt's cloud service in Claude
too (**plugin:grunt:Grunt** in Claude Code). Updating the plugin removes it;
connect Grunt as above if you signed in to that server only.

Some apps show the new tools only in a new session or after a restart.
**pptx**, **html** and **slides** check the connection before they start and tell
you what to do if Grunt is not connected;
[`CONNECT.md`](plugins/grunt/skills/pptx/CONNECT.md) lists the steps they
give. **powerpoint** uses the Grunt connector of the PowerPoint host it runs
in, and tells you if Grunt's tools are missing.

## Use

Ask in plain language, or name the skill in your request (in Claude Code you can
also invoke it directly):

- `/grunt:pptx` — "Create a Grunt bar chart of quarterly revenue by region and put it on slide 2 of deck.pptx."
- `/grunt:html` — "Build an HTML report with a Grunt line chart of monthly customers and a KPI table."
- **slides**, in a conversation with a Claude Slides deck — "Add a Grunt bar chart of revenue by quarter to slide 3", or select a chart on a slide and ask "Make the 2026 bars orange."
- **powerpoint**, in Claude for PowerPoint or another host with Grunt's
  `deck_*` tools — "Add a waterfall chart of this year's profit bridge to slide 3."

Requirements on your machine:

- **powerpoint:** PowerPoint with Grunt running and signed in. Nothing
  else to install.
- **pptx:** Python 3.10+. On first use the skill installs its pinned
  Python packages from `requirements.txt` (python-pptx, lxml, resvg-py,
  pypdfium2; about 40 MB) into a virtual environment. Decks are rendered for
  checking with PowerPoint on Windows, or else with LibreOffice.
- **html:** Node.js 22.22+. No `npm install` needed.
- **slides:** Python 3.10+ with network access to your Grunt's asset address (`assets.grunt.io` for the cloud service). It uses the pptx skill's downloader, so install the whole plugin.

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
- **Codex CLI and ChatGPT:** run `codex plugin marketplace upgrade grunt-plugins`.
  Codex also refreshes Git marketplaces when it starts.
- **GitHub Copilot CLI:** run `copilot plugin update grunt`.
- **VS Code:** run **Chat: Update Plugins**, or leave extension auto-update on.
- **Cursor:** the team marketplace refreshes from the repository.

## Maintainers

- [`plugins/grunt`](plugins/grunt) is the plugin, and the only place to edit
  skills. Claude reads it through `.claude-plugin/plugin.json` and Codex through
  `.codex-plugin/plugin.json`. Bump `version` in both for every release; users
  on a pinned version receive changes only when it changes.
- Each harness reads its own marketplace file before any other, which is how
  one repository gives each the right version. Do not add a `marketplace.json`
  at the root or in `.plugin`: GitHub Copilot CLI and VS Code would read it
  before `.github/plugin`.
- **Claude gets no MCP server:** no `.mcp.json` in `plugins/grunt`, and no
  `mcpServers` in the Claude manifest. In Claude a bundled server takes the
  place of the organization's Grunt connector, which can be an installation the
  organization runs itself. Codex gets the server from
  `.codex-plugin/mcp.json`, which Claude does not read.
- **Claude-only skills** are named in `CLAUDE_ONLY_SKILLS` in
  [`agent-plugins/build.py`](agent-plugins/build.py). The Codex manifest lists
  the other skills by folder, so add a new skill there too.
- [`agent-plugins/grunt`](agent-plugins/grunt) and the marketplace files in
  `.github/plugin` and `.cursor-plugin` are generated. After changing a skill or
  the version, run `python agent-plugins/build.py` and commit the result. The
  Agent Plugins format loads every folder under `skills/` and cannot leave one
  out, which is why those harnesses get a folder of their own. Do not put a
  root `plugin.json` in `plugins/grunt`: Codex would read it before its own
  manifest.
- The Microsoft 365 Copilot package is built from `agent-plugins/grunt` by
  `m365/build.py`. When the server's tools change, refresh the package's tool
  list as [`m365/README.md`](m365/README.md) describes.
- Skill names have no `grunt-` prefix in `plugins/grunt`. The plugin's name
  namespaces them in Claude and Codex, so `pptx` lists as `grunt:pptx`; the
  generator adds the prefix for harnesses that list skills bare. A skill's
  folder and its `name` must be the same, and `slides` finds the `pptx` skill's
  downloader by that folder name.
- Write skills for any agent: refer to the skill's folder as `<skill-dir>`
  rather than a host variable, and describe tools by what they do rather than by
  one host's tool names. Only `CONNECT.md` names the cloud service's address.
  The connection check and `CONNECT.md` are shared by the file-building skills
  (pptx, html, slides) and must stay identical. The powerpoint skill runs inside
  PowerPoint on the host's Grunt connector and has neither; keep its body short,
  because the host loads it on most chart requests.
- Before pushing, run:

  ```sh
  python agent-plugins/build.py --check
  claude plugin validate .
  claude plugin validate ./plugins/grunt
  python -m unittest discover -s tests -p "test_*.py"
  python -m unittest discover -s plugins/grunt/skills/pptx/scripts -p "test_*.py"
  python plugins/grunt/skills/pptx/scripts/test_scripts.py
  python -m unittest discover -s plugins/grunt/skills/slides/scripts -p "test_*.py"
  ```
