# Connecting to Grunt

The Grunt skills work through a Grunt connector: an MCP connection to Grunt in
the user's app. The plugin does not bring one. Normally it is the organization's
connector, called just "Grunt", and it points at one of:

- Grunt's cloud service: `https://mcp.grunt.io/mcp` (streamable HTTP)
- a Grunt the organization runs itself: the address its Grunt administrator
  gives

Sign-in is OAuth in the browser, with the user's own Grunt account. In Claude,
an organization can also set up managed authorization for the connector; it then
connects without a sign-in page.

Use these steps when you tell the user how to connect. `<address>` is the
address of the Grunt their organization uses; do not assume the cloud service.

| App | Steps |
| --- | --- |
| Claude Desktop, claude.ai and Cowork | Open **Customize > Connectors** (**Settings > Connectors** in older versions), find **Grunt** and choose **Connect**, then sign in with your Grunt account. In a chat, choose **+** > **Connectors** and check that Grunt is on. If Grunt is not listed, ask an organization owner to add it under **Organization settings > Connectors** with `<address>`; on a personal plan, choose **Add custom connector** and enter it yourself. |
| Claude for PowerPoint | The add-in uses the connectors of your Claude account, so connect Grunt there first, as above. Then, in the Claude pane, choose **+** > **Connectors** and check that Grunt is on. |
| Claude Code | Claude Code uses the connectors of your Claude account. Connect Grunt as in the first row, start a new session and run `/mcp` to check that it is listed. Without an account connector, add the server yourself: `claude mcp add --transport http grunt <address>`, then run `/mcp`, choose it and choose **Authenticate**. |
| Codex CLI | Run `codex mcp list` to see whether a Grunt server is set up. If not, add it: `codex mcp add grunt --url <address>`. Then run `codex mcp login <name>` with the server's name. |
| Other apps | Add `<address>` in the app's MCP or connector settings, then sign in when the app asks. |

## More than one Grunt connector

An app can list several, for example one for Grunt's cloud service and one for a
Grunt the organization runs itself or a test environment. Each is a separate
Grunt with its own assets and its own sign-in.

- The skills use the one the user names. If they name none, the one that is
  signed in; if several are signed in, the one called just "Grunt"; otherwise
  they ask.
- They don't ask the user to sign in to a second one while one works.
- They keep to one connector for a whole deck or report, so every asset is in
  the same Grunt.

## Plugin versions before 0.3.8

Earlier versions of the plugin added their own server for Grunt's cloud service
(`plugin:grunt:Grunt` in Claude Code), with a sign-in of its own. Claude Code
used it in place of an account connector at the same address. Updating the
plugin removes it.

Some apps load a newly connected server's tools only in a new session or after a
restart.
