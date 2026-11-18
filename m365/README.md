# Grunt for Microsoft 365 Copilot

This folder builds the Grunt plugin as a Microsoft 365 Copilot plugin: one ZIP
that Copilot Cowork, Copilot Chat and Copilot in PowerPoint can install. Its
skills come from [`agent-plugins/grunt`](../agent-plugins/grunt), the generated
plugin for harnesses other than Claude and Codex.

**Status, 18 November 2026: a test package. It has not been installed in a
tenant yet.** The manifest validates against Microsoft's 1.29 schema and the
package follows the rules Microsoft documents for upload, but only a tenant
shows whether it works. [What to test](#what-to-test) lists the open questions.

## What the package contains

| Part | In the ZIP | Comes from |
| --- | --- | --- |
| Manifest | `manifest.json` | `build.py`; the version is the plugin's |
| Icons | `color.png` (192 x 192), `outline.png` (32 x 32, white) | this folder, drawn from `plugins/grunt/assets/logo.png` |
| Skills | `skills/grunt-powerpoint`, `skills/grunt-pptx`, `skills/grunt-html` | `agent-plugins/grunt/skills`, with the change below |
| Connector | `agentConnectors` in the manifest: Grunt's MCP server | `--mcp-url` |
| Tool list | `tools/grunt-tools.json` | `toolDescription.json`, read from the server |
| Widget domains | `validDomains` in the manifest | `widgetDomains.json`, read from the server |

The Claude plugin brings no MCP server, because a Claude organization connects
Grunt itself and may point it at its own installation. A Microsoft 365 plugin
has no such separate connector, so this package names the server. Build one
package per Grunt address.

The skills arrive from `agent-plugins/grunt` already fit for Microsoft 365:

- **Their names have a `grunt-` prefix.** Microsoft 365 lists skills by their
  bare name, with no plugin namespace, and Cowork has built-in skills called
  PowerPoint and Word.
- **The Claude-only `slides` skill is left out,** and so are each skill's Codex
  card and icons, the helpers' tests and hidden files. A skill may hold 20
  files besides `SKILL.md`.

`build.py` changes one thing: **`CONNECT.md` is replaced** by
[the one in this folder](CONNECT.md), which gives the steps for Microsoft 365
Copilot instead of the other apps.

## Build

From the repository root, with Python 3.10 or later and nothing else. If you
changed a skill, regenerate `agent-plugins/grunt` first:

```sh
python agent-plugins/build.py
python m365/build.py
```

It writes `m365/dist/grunt-m365-<version>.zip` for Grunt's cloud service.

| Option | Use |
| --- | --- |
| `--mcp-url <address>` | Another Grunt, for example `https://grunt.example.com/mcp`. The package then gets its own app id and the name "Grunt (test)", so it installs beside the cloud one, and the file is `grunt-m365-test-<version>.zip`. |
| `--oauth-reference-id <id>` | The OAuth registration to sign in with; see [Sign-in](#sign-in). |
| `--skills grunt-powerpoint` | Only some skills. |
| `--no-tool-description` | Leave the tool list out. |

`toolDescription.json` and `widgetDomains.json` are copies of what the server
states about itself. Refresh them when its tools or its widget change, then
rebuild:

```sh
python m365/fetch_connector.py --url http://localhost:5044/mcp
```

A local development server needs no sign-in. For a deployed server, put an
access token in the `GRUNT_MCP_TOKEN` environment variable first. The files in
this folder were read on 18 November 2026 from a local build of the server with
production's tool switches. They list the same 30 tool names that Grunt's cloud
connector showed that day.

## Sign-in

Users sign in with their own Grunt account. Copilot keeps the tokens in
Microsoft's token store, which needs an OAuth client with a secret. Grunt's
sign-in server issues those on request (RFC 7591), and the cloud service
advertises the registration endpoint.

There are two ways to get the client, and the package is built differently for
each:

1. **The host registers itself (the default build).** The manifest names no
   authorization, and Cowork registers a client when the user first connects.
   Microsoft documents this for Cowork only. Grunt's sign-in server accepts a
   registration only for callback addresses on its allow-list. If connecting
   fails, look in the sign-in
   server's log for a refused `/register` call: the callback Cowork asked for
   must be added to the list.
2. **A registration you make once (`--oauth-reference-id`).** Needed for
   Copilot Chat, and the route to fall back on if 1 fails.
   1. Ask Grunt's sign-in server for a client. The answer holds a `client_id`
      and a `client_secret`, shown once. Keep the secret out of files and chats.

      ```sh
      curl -X POST https://auth.grunt.io/register -H "Content-Type: application/json" -d '{"client_name":"Microsoft 365 Copilot","redirect_uris":["https://teams.microsoft.com/api/platform/v1.0/oAuthRedirect"],"grant_types":["authorization_code","refresh_token"],"response_types":["code"],"token_endpoint_auth_method":"client_secret_post","scope":"mcp.access offline_access"}'
      ```

   2. In the [Teams Developer Portal](https://dev.teams.microsoft.com/tools/oauth-configuration),
      choose **Tools** > **OAuth client registration**, add a registration and
      enter:

      | Field | Value |
      | --- | --- |
      | Base URL | `https://mcp.grunt.io` |
      | Restrict usage by organization | **My organization only** for a test; **Any Microsoft 365 organization** for a package other tenants install |
      | Client ID, Client secret | from step 1 |
      | Authorization endpoint | `https://auth.grunt.io/authorize` |
      | Token endpoint, Refresh endpoint | `https://auth.grunt.io/token` |
      | Scope | `mcp.access offline_access` |
      | PKCE | on |

   3. Build with the registration id the portal shows:
      `python m365/build.py --oauth-reference-id <id>`.

   For another Grunt, use the sign-in server that
   `https://<its host>/.well-known/oauth-protected-resource/mcp` names, with the
   same paths, and build with `--mcp-url`.

## Install in a test tenant

You need a tenant where the tester has a Microsoft 365 Copilot licence, and
either the right to upload custom apps or an administrator's help. For the
PowerPoint tests you also need PowerPoint for Windows with the Grunt add-in
signed in to the same Grunt account.

| Route | Steps | Reaches |
| --- | --- | --- |
| Cowork upload | In Cowork: **Customize** > **Plugins** > **Add** > **Upload**, choose the ZIP, share with **Only you**. | You |
| Agents Toolkit | `npm install -g @microsoft/m365agentstoolkit-cli`, `atk auth login`, then `atk install --file-path <zip> --scope Personal`. | You |
| Admin center | [admin.cloud.microsoft](https://admin.cloud.microsoft): **Agents** > **All agents** > **...** > **Add agent**, upload the ZIP and choose the users. Check it under **Agents** > **Tools**. | The users you choose |

To remove a personal install: Teams > **Apps** > **Manage your apps** > Grunt >
the bin icon.

## What to test

Write down for each step: the app and platform, what happened, the exact text of
any error, and how long a tool call took. Keep two presentations open during the
PowerPoint steps, so a change that lands in the wrong one shows.

| # | Where | Do | Shows |
| --- | --- | --- | --- |
| 1 | Upload | Install the package by one of the routes above. | Whether Microsoft's validation accepts it. |
| 2 | Cowork | Open the plugin: three skills and the Grunt connector should be listed. Choose **Connect** and sign in. | Whether sign-in route 1 works. If not, rebuild with route 2. |
| 3 | Cowork | "Make a Grunt bar chart of revenue by quarter: 10, 12, 15, 19." | Whether Cowork calls `create_or_update_bar_chart`, asks to confirm, and draws the chart widget, shows text only, or shows a "widget network blocked" card. |
| 4 | Cowork, PowerPoint open | "Which presentations do I have open?" then "Put that chart on slide 2 of <name>." | Whether `deck_get_context` and `deck_insert_asset` reach PowerPoint through the add-in, and the chart lands once, in the right deck, as a Grunt object. |
| 5 | Copilot in PowerPoint | **+** > **Manage plugins**: is Grunt listed? **+** > **Choose skills**: is `grunt-powerpoint` listed? Then "Add a waterfall chart of this profit bridge to this slide: ...". | Whether plugins have reached the tenant, whether the pane calls Grunt's tools or draws its own chart, and what lands on the slide. This is the main question. |
| 6 | Copilot in PowerPoint | Select the chart from step 5 and ask "Make the bars orange." | Whether a change goes through Grunt (`deck_read_slide`, then a replace) or Copilot edits the picture. |
| 7 | Copilot Chat | Add Grunt under **Plugins** and repeat step 3. | Whether Chat uses the connector. Expect it to need sign-in route 2. |
| 8 | Cowork | "Build a three-slide deck about X with a Grunt chart on slide 2, as a .pptx file." | Whether `grunt-pptx` can run: it installs Python packages and downloads from Grunt's asset address, which Cowork's sandbox may not allow. |

## Known gaps

- **Tool calls must answer within 30 seconds** in a Copilot plugin. Grunt's
  deck tools wait up to 50 seconds for PowerPoint. Slow inserts may be cut off;
  note any in step 4.
- **Every chart tool will ask for confirmation.** Cowork asks before any tool
  that is not marked read-only, which includes all the chart tools. Microsoft
  is still rolling this out, so it may not show in every tenant yet.
- **The chart tools have no `readOnlyHint`.** Microsoft's connector gallery
  wants a title and an explicit `readOnlyHint` on every tool. All 30 tools have
  titles; the 12 `create_or_update_*` tools leave the hint out.
- **30 tools.** Microsoft's guidance for agents says answers get worse above
  about 10 tools. A later package may need a smaller tool set for PowerPoint.
- **`validDomains` lists ChatGPT's domains.** The widget declares them to every
  host, and Cowork flags a widget whose declared domains are not all listed.
  Before a store submission, the server should declare them to ChatGPT only.
- **Widgets get at most 64 KiB of a tool's result** in Cowork; a larger result
  arrives without its data.
- **The `grunt-powerpoint` skill still names Claude for PowerPoint** as its
  example host. It applies to any host with the `deck_*` tools, but if step 5
  shows Copilot passing it over, its description is the first thing to change.
- **Publishing** to other tenants goes through Partner Center and Microsoft's
  review. Nothing here does that.

## Tests

```sh
python -m unittest discover -s tests -p "test_*.py"
```

`tests/test_m365_package.py` builds the package and checks it against the
limits above, and that every tool the skills name is in the tool list.
